"""Dump the LIVE geometry of TSpellBook's eight slots from a running AoWz.exe.

Why: the Research Book's visible entry (`SxPnl`) and its click target (`SxBtn`) are separate
controls, and `build_tierresearch_exe.py`'s cave_layout re-pitches only the panels. Reasoning
about which one ends up where from the DFM has now been wrong twice -- this prints what the
game ACTUALLY has (parent, alignment, and the live rect), which is the only reliable source.

Usage:
    1. Launch AoWz.exe, load a game, open the SPELLBOOK and switch it to RESEARCH.
    2. Leave the book on screen, then run:  python spellbook_geom.py

⚠ Only the MOD pair is searched (zigexe.EXES). The root's AoW.exe / AoWCompat.exe are VANILLA:
attaching to one would print vanilla geometry as though it were Ziggurat's, with no error.

Field map (same as live_ui.py):
    TAoWComponent: +0x75 visible  +0x7c W  +0x80 H  +0x84 Left  +0x88 Top
                   +0xcc parent   +0xd4 alignment
    TAOWAlignment: +0x20 TopOffset  +0x28 AlignWidth  +0x29 AlignHeight
"""
import ctypes, ctypes.wintypes as w, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zignames import zigexe

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_VM_READ = 0x0010; PROCESS_QUERY_INFORMATION = 0x0400
# ⚠ This build does NOT use the standard Delphi VMT metadata offsets. Decoded from the live
# image: classname ptr at VMT-0x20, INSTANCE SIZE at VMT-0x1C, parent class at VMT-0x18 (the
# VMT-0x1C instance-size convention is the one recorded in the project notes). For TSpellBook
# the classname ptr sits at 0x0042DD88 and instance size 0x248 at 0x0042DD8C => VMT 0x0042DDA8.
# Deriving it with the textbook vmtClassName = -44 gives 0x0042DDC0 and finds NOTHING.
VMT_SPELLBOOK = 0x0042DDA8
INSTANCE_SIZE = 0x248
MODE_OFF = 0x220

# slot -> (panel field, button field, icon field, title field)
SLOTS = [(0x4C, 0x114, 0x60, 0x50), (0x64, 0x140, 0x78, 0x68),
         (0x7C, 0x144, 0x90, 0x80), (0x94, 0x148, 0xA8, 0x98),
         (0xB4, 0x14C, 0xC8, 0xB8), (0xCC, 0x150, 0xE0, 0xD0),
         (0xE4, 0x154, 0xF8, 0xE8), (0xFC, 0x158, 0x110, 0x100)]
AH = ["ahNone", "ahTop", "ahBottom", "ahBoth", "ahCenter"]


def pids_by_name(name):
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", w.DWORD),
                    ("cntThreads", w.DWORD), ("th32ParentProcessID", w.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", w.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    e = PE32(); e.dwSize = ctypes.sizeof(PE32); out = []
    if k32.Process32First(snap, ctypes.byref(e)):
        while True:
            if e.szExeFile.decode(errors="replace").lower() == name.lower():
                out.append(e.th32ProcessID)
            if not k32.Process32Next(snap, ctypes.byref(e)):
                break
    k32.CloseHandle(snap); return out


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", w.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", w.DWORD), ("Protect", w.DWORD), ("Type", w.DWORD)]


class Mem:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h:
            raise OSError("OpenProcess failed (run as Administrator): %d" % ctypes.get_last_error())

    def read(self, a, n):
        buf = (ctypes.c_char * n)(); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
            return None
        return bytes(buf[:got.value])

    def u32(self, a):
        b = self.read(a, 4); return struct.unpack("<I", b)[0] if b and len(b) == 4 else None

    def i32(self, a):
        b = self.read(a, 4); return struct.unpack("<i", b)[0] if b and len(b) == 4 else None

    def u8(self, a):
        b = self.read(a, 1); return b[0] if b else None

    def regions(self):
        addr, mbi = 0, MBI()
        while addr < 0x7FFF0000:
            if not k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                      ctypes.sizeof(mbi)):
                break
            if mbi.State == 0x1000 and mbi.Protect not in (0x01, 0x100):   # committed, readable
                yield mbi.BaseAddress or 0, mbi.RegionSize
            addr = (mbi.BaseAddress or 0) + mbi.RegionSize
            if mbi.RegionSize == 0:
                break


def find_books(m):
    needle = struct.pack("<I", VMT_SPELLBOOK); out = []
    for base, size in m.regions():
        if size > 64 * 1024 * 1024:
            continue
        blob = m.read(base, size)
        if not blob:
            continue
        p = 0
        while True:
            k = blob.find(needle, p)
            if k < 0:
                break
            # Only heap objects are instances. Hits below 0x01000000 are static references to
            # the VMT inside the exe image itself (vmtSelfPtr, class-ref constants) -- not objects.
            if k % 4 == 0 and base + k >= 0x01000000:
                out.append(base + k)
            p = k + 4
    return out


def ctl(m, tag, addr, pnl=None):
    if not addr:
        print(f"    {tag:<6} NIL"); return
    vis = m.u8(addr + 0x75)
    W, H, L, T = m.i32(addr + 0x7c), m.i32(addr + 0x80), m.i32(addr + 0x84), m.i32(addr + 0x88)
    par, al = m.u32(addr + 0xcc), m.u32(addr + 0xd4)
    extra = ""
    if al:
        ah = m.u8(al + 0x29)
        extra = f" align={AH[ah] if ah is not None and ah < 5 else ah} TopOff={m.i32(al + 0x20)}"
    rel = ""
    if pnl and par is not None:
        rel = "  parent=THIS-PANEL" if par == pnl else f"  parent=OTHER({par:08X})"
    bot = "?" if None in (T, H) else T + H
    print(f"    {tag:<6} {addr:08X} vis={vis} L={L} T={T} W={W} H={H} "
          f"bottom={bot} parent={'None' if par is None else format(par, '08X')}{extra}{rel}")


def main():
    pids, exe = [], None
    for name in zigexe.EXES:                       # the MOD pair only -- see the module docstring
        pids = pids_by_name(name)
        if pids:
            exe = name
            break
    if not pids:
        print("%s is not running. Launch it, open the Spellbook in RESEARCH mode, re-run."
              % " / ".join(zigexe.EXES))
        return 1
    m = Mem(pids[0]); print("attached to %s pid %d" % (exe, pids[0]))
    if m.read(0x400000, 2) != b"MZ":
        print("cannot read image base -- run this shell as Administrator."); return 1

    # sanity-check the VMT against the live image before trusting the scan
    cname = m.u32(VMT_SPELLBOOK - 0x20); isize = m.u32(VMT_SPELLBOOK - 0x1C)
    nm = m.read(cname, 12) if cname else None
    print(f"VMT {VMT_SPELLBOOK:08X}: classname={nm!r} instsize={isize} (want 'TSpellBook'/{INSTANCE_SIZE})")

    books = find_books(m)
    print(f"TSpellBook instances found: {[hex(b) for b in books] or 'NONE'}")
    if not books:
        print("  (none -- is the Spellbook actually open? it is created on demand)")
    for b in books:
        mode = m.u8(b + MODE_OFF)
        pnl0 = m.u32(b + 0x4C)
        if mode is None or pnl0 in (None, 0):
            print(f"  {b:08X}: skipped (mode={mode} S1Pnl={pnl0})")
            continue
        print(f"\n=== book {b:08X}  mode=[{MODE_OFF:#x}]={mode} "
              f"({'CAST-global' if mode == 0 else 'CAST-combat' if mode == 1 else 'RESEARCH' if mode in (2, 3) else 'info'})"
              f"  page=[+0x228]={m.i32(b + 0x228)}  listcount=?")
        for i, (p, btn, icn, ttl) in enumerate(SLOTS):
            pnl = m.u32(b + p)
            print(f"  slot {i}:")
            ctl(m, "pnl", pnl)
            ctl(m, "btn", m.u32(b + btn), pnl)
            ctl(m, "icon", m.u32(b + icn), pnl)
            ctl(m, "title", m.u32(b + ttl), pnl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
