#!/usr/bin/env python3
r"""
wheel_probe.py -- read the mouse-wheel plumbing's live state out of the RUNNING game (or editor).

Pairs with build_scripts/build_wheel_aowint.py and build_wheel_vclpump.py. The counters exist only
in `--diag` builds of those scripts; the globals, the contract header and the latch block are live
in every build, so this is worth running even against a plain build.

    python re_tools/wheel_probe.py            (with any of zigexe.ALL_EXES running)

Everything is located as module base + RVA through the process module list (the DPLs rebase).
Reads only -- never writes to the process.

⚠ Only the MOD binaries are searched. The root's AoW.exe / AoWCompat.exe are VANILLA and carry
none of this plumbing, so attaching to one would report "NOT LOADED" for a patch that is in fact
installed -- a wrong answer with no error.

vcl30.dpl  RVA 0xE7140  G_PENDING, G_HWND, G_THREADED, G_PID, G_AOWBASE, G_HHOOK
           RVA 0xE7180  --diag counters:
               +00 pump hits (every retrieved message)   +04 header-valid passes
               +08 CreateThread handle                   +0C helper calls
               +10 helper handled                        +14 last delta passed to a helper
               +18 LL callbacks (any mouse input)        +1C LL wheel events
               +20 gated: unarmed   +24 gated: foreground   +28 gated: under-cursor
               +2C queued (armed wheel events)           +30 SetWindowsHookExA result
               +34 last non-zero G_PENDING the pump saw  +38 notches drained
aowInt.dpl RVA 0x24000  contract header (magic 'AZWH', version, latch RVA/count, helper slots 0-3)
           RVA 0x3E040  latch block: [0] hover [1] facenext [2] faceprev [3] pslider [4] unext
                        [5] uprev [6] uarmed [7] spare
           RVA 0x3E060  --diag counters:
               +00 move sweeps (CLR)    +04 inside listbox (SET)   +08 inside memo (SET2)
               +0C inside image (SET3)  +10 WheelScroll entered    +14 WheelScroll handled
               +18 no-scrollbar fallback +1C wheel with no hover   +20 sibling scrollbar found
               +24 OnChange fired       +28 last hovered control   +2C memo inert returns
               +30 WheelPower entered   +34 WheelPower handled     +38 WheelUnit entered
               +3C WheelUnit handled
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
k32.OpenProcess.restype = w.HANDLE
k32.CreateToolhelp32Snapshot.restype = w.HANDLE

PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x0010, 0x0400
#: game pair + both editors -- the wheel patch lives in aowInt.dpl/vcl30.dpl, which all four load.
PROCS = tuple(zigexe.ALL_EXES)

VCL_GLOBALS_RVA, VCL_CNT_RVA = 0xE7140, 0xE7180
AOW_HDR_RVA, AOW_LATCH_RVA, AOW_CNT_RVA = 0x24000, 0x3E040, 0x3E060
MAGIC = 0x48575A41

VCL_CNT = ["pump hits", "header valid", "thread handle", "helper calls", "helper handled",
           "last delta", "LL callbacks", "LL wheel events", "gated: unarmed", "gated: foreground",
           "gated: under-cursor", "queued (armed)", "SetWindowsHookExA", "last pending seen",
           "notches drained", "(spare)"]
AOW_CNT = ["move sweeps (CLR)", "inside listbox", "inside memo", "inside image", "WheelScroll in",
           "WheelScroll handled", "no-scrollbar fallback", "wheel w/o hover", "sibling bar found",
           "OnChange fired", "last hovered ctrl", "memo inert", "WheelPower in", "WheelPower handled",
           "WheelUnit in", "WheelUnit handled"]
LATCH = ["hover", "facenext", "faceprev", "pslider", "unext", "uprev", "uarmed", "spare"]


def pids_by_name(name):
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", w.DWORD),
                    ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
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
        buf = (ctypes.c_char * n)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return bytes(buf[:got.value]) if got.value == n else None

    def dwords(self, addr, n):
        b = self.read(addr, 4 * n)
        return list(struct.unpack("<%dI" % n, b)) if b else None

    def modules(self):
        arr = (ctypes.c_void_p * 2048)()
        need = w.DWORD()
        if not psapi.EnumProcessModulesEx(self.h, arr, ctypes.sizeof(arr), ctypes.byref(need), 0x03):
            return {}
        out, buf = {}, ctypes.create_string_buffer(260)
        for i in range(min(2048, need.value // ctypes.sizeof(ctypes.c_void_p))):
            hm = arr[i]
            if not hm:
                continue
            psapi.GetModuleBaseNameA(self.h, ctypes.c_void_p(hm), buf, 260)
            out[buf.value.decode(errors="replace").lower()] = hm
        return out


def s32(x):
    return x - 0x100000000 if x >= 0x80000000 else x


def main():
    pid = exe = None
    for cand in PROCS:
        got = pids_by_name(cand)
        if got:
            pid, exe = got[0], cand
            break
    if not pid:
        sys.exit("[x] none of %s is running." % ", ".join(PROCS))
    print("process : %s  pid %d" % (exe, pid))
    m = Mem(pid)
    mods = m.modules()
    vcl, aow = mods.get("vcl30.dpl"), mods.get("aowint.dpl")
    print("vcl30.dpl  base %s" % ("%08X" % vcl if vcl else "NOT LOADED"))
    print("aowInt.dpl base %s" % ("%08X" % aow if aow else "NOT LOADED"))

    g = c = hdr = latch = ac = None
    if vcl:
        g = m.dwords(vcl + VCL_GLOBALS_RVA, 6)
        c = m.dwords(vcl + VCL_CNT_RVA, 16)
        if g:
            names = ["G_PENDING", "G_HWND", "G_THREADED", "G_PID", "G_AOWBASE", "G_HHOOK"]
            print("\n--- vcl30 globals ---")
            for n, v in zip(names, g):
                extra = ""
                if n == "G_PENDING":
                    extra = "  (%+d raw, %+d notches)" % (s32(v), int(s32(v) / 120))
                if n == "G_AOWBASE":
                    extra = ("  (unresolved)" if v == 0 else "  (ABSENT)" if v == 0xFFFFFFFF
                             else "  (matches module list)" if v == aow else "  (MISMATCH vs module list!)")
                if n == "G_PID":
                    extra = "  (== this pid)" if v == pid else ("  (!= pid %d)" % pid if v else "")
                print("  %-11s %08X%s" % (n, v, extra))
        if c:
            print("\n--- vcl30 --diag counters ---")
            for n, v in zip(VCL_CNT, c):
                print("  %-22s %d%s" % (n, v, "  (%+d)" % s32(v) if n == "last delta" else ""))
    if aow:
        hdr = m.dwords(aow + AOW_HDR_RVA, 8)
        latch = m.dwords(aow + AOW_LATCH_RVA, 8)
        ac = m.dwords(aow + AOW_CNT_RVA, 16)
        if hdr:
            print("\n--- aowInt contract header @ %08X ---" % (aow + AOW_HDR_RVA))
            ok = hdr[0] == MAGIC and (hdr[1] >> 16) == 1
            print("  magic %08X %s  version %d.%d  latch RVA %05X count %d  slots %s  -> %s"
                  % (hdr[0], "'AZWH'" if hdr[0] == MAGIC else "(not AZWH)", hdr[1] >> 16,
                     hdr[1] & 0xFFFF, hdr[2], hdr[3], ["%05X" % s for s in hdr[4:8]],
                     "VALID" if ok else "INVALID: pump never calls, thread never created"))
        if latch:
            print("\n--- aowInt latches (live) ---")
            print("  " + "  ".join("%s=%08X" % (n, v) for n, v in zip(LATCH, latch)))
        if ac:
            print("\n--- aowInt --diag counters ---")
            for n, v in zip(AOW_CNT, ac):
                print("  %-22s %s" % (n, "%08X" % v if n == "last hovered ctrl" else str(v)))

    # ---- reading the numbers
    print("\n--- verdict ---")
    if not vcl or not g:
        print("  vcl30.dpl not readable -> nothing to say.")
        return 1
    if aow and hdr and not (hdr[0] == MAGIC and (hdr[1] >> 16) == 1):
        print("  aowInt header INVALID -> build_wheel_aowint.py not applied (or a major bump). Fail-safe.")
        return 0
    if c and sum(c) == 0 and ac and sum(ac) == 0:
        print("  all counters zero: plain build (or nothing has happened yet). Rebuild both halves with"
              " --diag for the counters; the globals/latches above are still live.")
    if c and c[0] == 0 and sum(c) > 0:
        print("  pump hits = 0 -> the pump hook never runs (H5 not applied / wrong site).")
    if g[2] == 0:
        print("  G_THREADED = 0 -> the hook-owner thread was never created: nothing has been hovered"
              " yet (G1) -- move the cursor into a list, then re-run.")
    elif g[5] == 0:
        print("  G_THREADED = 1 but G_HHOOK = 0 -> SetWindowsHookExA failed (or the thread has not"
              " reached it yet).")
    if c and g[2] and g[5]:
        if c[6] == 0:
            print("  LL callbacks = 0 -> the hook is installed but not being serviced.")
        elif c[7] == 0:
            print("  LL wheel events = 0 -> no wheel reaches the hook (device / driver?).")
        else:
            if c[8]:
                print("  gated: unarmed %d -> wheel while no latch was set (cursor not inside a list at"
                      " that moment)." % c[8])
            if c[9]:
                print("  gated: foreground %d -> another application was in the foreground: passed"
                      " through, not swallowed (correct)." % c[9])
            if c[10]:
                print("  gated: under-cursor %d -> the window under GetCursorPos was not ours: another"
                      " window on top (correct), or a DPI-scaling mismatch (U2) if it happens with"
                      " the game alone on screen." % c[10])
            if c[11] and c[3] == 0:
                print("  queued > 0 but helper calls = 0 -> the pump never drained: wake-up post to"
                      " G_HWND failing, or |G_PENDING| < 120 (sub-notch deltas).")
            if c[3] and c[4] == 0:
                print("  helper calls > 0, handled = 0 -> every helper returned 0: see aowInt"
                      " counters (fallback / memo inert / no hover).")
            if c[4]:
                print("  handled %d -> scrolling happened; if nothing is visible the repaint is the"
                      " problem, not delivery." % c[4])
    return 0


if __name__ == "__main__":
    sys.exit(main())
