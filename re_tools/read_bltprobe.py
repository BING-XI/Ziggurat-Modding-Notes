#!/usr/bin/env python3
r"""
read_bltprobe.py -- read the "Blt Error" probe out of the RUNNING game.

Install the probe first:   python build_scripts/build_bltprobe.py --apply
Then, with the error dialog STILL ON SCREEN (it is modal, so the process holds still):
                           python re_tools/read_bltprobe.py

The probe (aowInt cave at 0x59823000, hooked on the except arm at 0x59807D55) records raw values into
aowInt's DATA slack at link-time VA 0x5983E100. It deliberately dereferences almost nothing: a stray
read inside a Delphi except arm means a nested exception, which is a hard failure. So the pointer
chasing happens HERE instead, over ReadProcessMemory, which returns an error rather than faulting.

The DPL rebases, so the scratch is located as aowInt_load_base + 0x3E100.

Reads only -- never writes to the process.

⚠ Only the MOD binaries are searched (zigexe.ALL_EXES). The root's AoW.exe / AoWCompat.exe are
VANILLA and carry no probe, so attaching to one would report "this probe has not fired" for a
probe that is in fact installed -- a wrong answer with no error.
"""
import ctypes
import ctypes.wintypes as w
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zignames import zigexe

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

# 64-bit Python truncates HANDLE-returning calls to int32 unless restype is declared.
k32.OpenProcess.restype = w.HANDLE
k32.CreateToolhelp32Snapshot.restype = w.HANDLE

SCR_RVA = 0x3E100                   # 0x5983E100 - 0x59800000
SCR_LEN = 0x100
MAGIC = 0x50544C42                  # 'BLTP'
LINK_BASE = 0x59800000
STACK_OFF, STACK_N = 0x60, 40

FIELDS = [
    ("magic",        0x00), ("hits",         0x04), ("eax_at_entry", 0x08),
    ("rect_left",    0x0C), ("rect_top",     0x10), ("rect_right",   0x14),
    ("rect_bottom",  0x18), ("blt_index",    0x1C), ("blt_remaining", 0x20),
    ("self",         0x24), ("src_surface",  0x28), ("edx_arg",      0x2C),
    ("transparent",  0x30), ("rect_count",   0x34), ("ebp",          0x38),
    ("esp",          0x3C), ("dirty",        0x40), ("vmt",          0x44),
    ("vmt_9c",       0x48), ("post_code",    0x4C), ("post_data",    0x50),
    ("pre_code",     0x54), ("pre_data",     0x58), ("bltrect_list", 0x5C),
]


def pids_by_name(name):
    TH32CS_SNAPPROCESS = 2

    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", w.DWORD),
                    ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    e = PE32()
    e.dwSize = ctypes.sizeof(PE32)
    out = []
    if k32.Process32First(snap, ctypes.byref(e)):
        while True:
            if e.szExeFile.decode(errors="replace").lower() == name.lower():
                out.append(e.th32ProcessID)
            if not k32.Process32Next(snap, ctypes.byref(e)):
                break
    k32.CloseHandle(snap)
    return out


class Mem:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h:
            raise OSError("OpenProcess failed (try an elevated shell): %d" % ctypes.get_last_error())

    def read(self, addr, n):
        if addr is None or addr < 0x10000 or n <= 0:
            return None
        buf = (ctypes.c_char * n)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return bytes(buf[:got.value]) if got.value == n else None

    def u32(self, a):
        b = self.read(a, 4)
        return struct.unpack("<I", b)[0] if b else None

    def i32(self, a):
        b = self.read(a, 4)
        return struct.unpack("<i", b)[0] if b else None

    def modules(self):
        """[(name, base, size)] for the 32-bit target."""
        n = 2048
        arr = (ctypes.c_void_p * n)()
        need = w.DWORD()
        fn = getattr(psapi, "EnumProcessModulesEx", None)
        ok = (fn(self.h, arr, ctypes.sizeof(arr), ctypes.byref(need), 0x03) if fn
              else psapi.EnumProcessModules(self.h, arr, ctypes.sizeof(arr), ctypes.byref(need)))
        if not ok:
            return []
        out = []
        buf = ctypes.create_string_buffer(260)

        class MODINFO(ctypes.Structure):
            _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", w.DWORD),
                        ("EntryPoint", ctypes.c_void_p)]

        for i in range(min(n, need.value // ctypes.sizeof(ctypes.c_void_p))):
            hm = arr[i]
            if not hm:
                continue
            psapi.GetModuleBaseNameA(self.h, ctypes.c_void_p(hm), buf, 260)
            mi = MODINFO()
            psapi.GetModuleInformation(self.h, ctypes.c_void_p(hm), ctypes.byref(mi),
                                       ctypes.sizeof(mi))
            out.append((buf.value.decode(errors="replace"), hm, mi.SizeOfImage))
        return out

    def shortstr(self, p):
        """Delphi ShortString: [len][chars]"""
        b = self.read(p, 1)
        if not b:
            return None
        n = b[0]
        if not 1 <= n <= 255:
            return None
        s = self.read(p + 1, n)
        return s.decode("latin1") if s else None

    def ansistr(self, p):
        """Delphi 2/3 long string: [refcount:-8][len:-4][chars...][#0]"""
        if not p:
            return ""
        n = self.i32(p - 4)
        if n is None or not 0 <= n <= 4096:
            return None
        s = self.read(p, n)
        return s.decode("latin1") if s is not None else None


def classname(m, vmt, mods):
    """Delphi 2/3 puts vmtClassName at VMT-32; Delphi 4+ at -44. Try both, report which."""
    for delta in (-32, -44, -40, -36, -48):
        p = m.u32(vmt + delta)
        if not p:
            continue
        s = m.shortstr(p)
        if s and 1 <= len(s) <= 63 and all(32 <= ord(c) < 127 for c in s):
            return s, delta
    return None, None


def owner(mods, addr):
    if not addr:
        return ""
    for name, base, size in mods:
        if base <= addr < base + size:
            return "%s+%X" % (name, addr - base)
    return "(heap/unknown)"


EXE_SCR = 0x0045A640                # game-exe DATA slack -- fixed base 0x400000, no rebasing
EXE_MAGIC = 0x32544C42              # 'BLT2'
EXE_STACK_OFF, EXE_STACK_N = 0x2C, 64
PUSHAD_ORDER = ["EDI", "ESI", "EBP", "ESP", "EBX", "EDX", "ECX", "EAX"]


def exception_candidates(m, mods, raw, off, n):
    """Scan a captured stack image for pointers whose Delphi class metadata validates."""
    out = []
    for i in range(n):
        p = struct.unpack_from("<I", raw, off + i * 4)[0]
        if p < 0x10000:
            continue
        vmt = m.u32(p)
        if not vmt or vmt < 0x10000 or "+" not in owner(mods, vmt):
            continue
        cn, _ = classname(m, vmt, mods)
        if not cn or not cn[0].isupper():
            continue
        msgp = m.u32(p + 4)
        msg = m.ansistr(msgp) if msgp else ""
        out.append((i * 4, p, cn, msg))
    return out


def read_exe_probe(m, mods):
    raw = m.read(EXE_SCR, 0x12C)
    if raw is None:
        print("\n[!] could not read the %s scratch at %08X" % (zigexe.GAME_EXE, EXE_SCR))
        return
    magic, hits = struct.unpack_from("<II", raw, 0)
    print("\n" + "=" * 78)
    print("%s probe -- FCWinDrawSurface except arm @0x435F26 (the ORIGINAL exception)"
          % zigexe.GAME_EXE)
    print("=" * 78)
    if magic != EXE_MAGIC:
        print("  magic %08X, expected %08X ('BLT2') -- this probe has not fired." % (magic, EXE_MAGIC))
        print("  Install it with:  python build_scripts/build_bltprobe_exe.py --apply")
        return
    print("  fired          : %d time(s)" % hits)
    regs = struct.unpack_from("<8I", raw, 8)
    print("  registers      : " + "  ".join("%s=%08X" % (n, v)
                                            for n, v in zip(PUSHAD_ORDER, regs)))
    print("  esp at handler : %08X" % struct.unpack_from("<I", raw, 0x28)[0])

    print("\n  --- the real exception ---")
    cands = exception_candidates(m, mods, raw, EXE_STACK_OFF, EXE_STACK_N)
    if cands:
        for delta, p, cn, msg in cands:
            print("    esp+%02X  obj %08X  class %-24s Message %r"
                  % (delta, p, cn, msg if msg is not None else "<unreadable>"))
    else:
        print("    no validating object found on the stack.")

    print("\n  --- return addresses (where it blew) ---")
    shown = 0
    for i in range(EXE_STACK_N):
        p = struct.unpack_from("<I", raw, EXE_STACK_OFF + i * 4)[0]
        own = owner(mods, p)
        if "+" not in own or p < 0x401000:
            continue
        # a return address points just past a call; require a call opcode shortly before it
        pre = m.read(p - 5, 5)
        if not pre or (pre[0] != 0xE8 and 0xFF not in pre[:3]):
            continue
        print("    esp+%02X  %08X  %s" % (i * 4, p, own))
        shown += 1
        if shown >= 14:
            break
    if not shown:
        print("    none identified -- raw stack:")
        for i in range(0, EXE_STACK_N, 4):
            words = struct.unpack_from("<4I", raw, EXE_STACK_OFF + i * 4)
            print("    esp+%02X  " % (i * 4) + "  ".join("%08X" % x for x in words))


def main():
    pid = exe = None
    for cand in zigexe.ALL_EXES:
        got = pids_by_name(cand)
        if got:
            pid, exe = got[0], cand
            break
    if not pid:
        sys.exit("[x] none of %s is running. Start the game and reproduce the error first."
                 % ", ".join(zigexe.ALL_EXES))
    print("process : %s  pid %d" % (exe, pid))

    m = Mem(pid)
    mods = m.modules()
    aow_int = next((x for x in mods if x[0].lower() == "aowint.dpl"), None)
    if not aow_int:
        sys.exit("[x] aowInt.dpl is not loaded in that process.")
    base = aow_int[1]
    scr = base + SCR_RVA
    print("aowInt  : base %08X  (link base %08X, delta %+#x)" % (base, LINK_BASE, base - LINK_BASE))
    print("scratch : %08X" % scr)

    read_exe_probe(m, mods)

    raw = m.read(scr, SCR_LEN)
    if raw is None:
        sys.exit("[x] Could not read the scratch page.")
    v = {name: struct.unpack_from("<I", raw, off)[0] for name, off in FIELDS}

    print("\n" + "=" * 78)
    print("aowInt probe -- 'Blt Error' except arm @0x59807D55 (the generic replacement)")
    print("=" * 78)
    if v["magic"] != MAGIC:
        print("\n[!] magic is %08X, expected %08X ('BLTP')." % (v["magic"], MAGIC))
        print("    The probe has not fired yet. Either it is not installed"
              " (build_bltprobe.py --apply),")
        print("    or this run has not hit the error. Reproduce it, leave the dialog up, re-run.")
        return 1

    def s32(x):
        return x - 0x100000000 if x >= 0x80000000 else x

    print("\n--- component ---")
    print("  fired          : %d time(s)" % v["hits"])
    print("  self           : %08X  %s" % (v["self"], owner(mods, v["self"])))
    nm = m.u32(v["self"] + 8)
    print("  self.Name      : %r" % (m.ansistr(nm) if nm else None))
    if v["vmt"]:
        cn, delta = classname(m, v["vmt"], mods)
        print("  self.ClassName : %s   (VMT %08X %s)"
              % (cn or "<unreadable>", v["vmt"], owner(mods, v["vmt"])))
    print("  dirty [+0x102] : %d %s" % (v["dirty"],
                                        "<- 0 = the VIRTUAL-CALL path" if not v["dirty"] else ""))
    print("  BltRect count  : %d   (list %08X)" % (s32(v["rect_count"]), v["bltrect_list"]))
    print("  source surface : %08X  %s" % (v["src_surface"], owner(mods, v["src_surface"])))

    print("\n--- which statement raised ---")
    if not v["dirty"]:
        print("  PATH: [self+0x102]==0 -> `call [self.VMT+0x9C]` at 59807D3D is the only")
        print("        statement in the try, so THAT is what raised.")
        print("    method [VMT+0x9C] : %08X  %s"
              % (v["vmt_9c"], owner(mods, v["vmt_9c"]) or "(not in any module!)"))
        print("    EDX arg [ebp-8]   : %08X  %s" % (v["edx_arg"], owner(mods, v["edx_arg"])))
    elif s32(v["rect_count"]) <= 0:
        print("  PATH: dirty set but count<=0 -- that exits the try WITHOUT executing anything,")
        print("        so it should be unreachable. Treat this capture as suspect.")
    else:
        L, T, R, B = (s32(v["rect_%s" % k]) for k in ("left", "top", "right", "bottom"))
        print("  PATH: dirty set, count %d -> the pre-event / blit loop / post-event path."
              % s32(v["rect_count"]))
        print("    rect            : L%d T%d R%d B%d  (%dx%d)" % (L, T, R, B, R - L, B - T))
        print("    BltRect index   : %d, %d remaining"
              % (s32(v["blt_index"]), s32(v["blt_remaining"])))
        print("    blit path       : %s" % ("colour-keyed [ebx+0x20]" if v["transparent"]
                                            else "plain [ebx+0x18]"))
    print("    pre-draw event  : code %08X %s  data %08X"
          % (v["pre_code"], owner(mods, v["pre_code"]), v["pre_data"]))
    print("    post-draw event : code %08X %s  data %08X"
          % (v["post_code"], owner(mods, v["post_code"]), v["post_data"]))

    # EAX is not the exception object for a bare `except` (measured: v1 got a non-VMT). Hunt the
    # stack instead -- the Delphi exception frame is in there.
    print("\n--- exception-object candidates on the stack ---")
    found = 0
    for i in range(STACK_N):
        p = struct.unpack_from("<I", raw, STACK_OFF + i * 4)[0]
        if p < 0x10000:
            continue
        vmt = m.u32(p)
        if not vmt or vmt < 0x10000 or not owner(mods, vmt).count("+"):
            continue
        cn, delta = classname(m, vmt, mods)
        if not cn or not cn[0].isupper():
            continue
        msgp = m.u32(p + 4)
        msg = m.ansistr(msgp) if msgp else ""
        print("  esp+%02X  obj %08X  class %-28s Message %r"
              % (i * 4, p, cn, msg if msg is not None else "<unreadable>"))
        found += 1
    if not found:
        print("  none found -- raw stack follows")
        for i in range(0, STACK_N, 4):
            words = struct.unpack_from("<4I", raw, STACK_OFF + i * 4)
            print("  esp+%02X  " % (i * 4) + "  ".join("%08X" % x for x in words))
    return 0


if __name__ == "__main__":
    sys.exit(main())
