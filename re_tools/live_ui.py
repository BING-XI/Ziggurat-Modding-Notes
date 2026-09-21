"""Read the RUNNING AoWz.exe and dump the live UI geometry + combat-log ring state.

Why: the alignment model (TAoWComponent.ReAlign @aowInt 0x598030FC) recomputes every window's rect at
runtime from the parent's live size, so a DFM value can verify on disk yet never reach the screen. This
prints what the game ACTUALLY has, which beats reasoning about the DFM.

Usage:  python live_ui.py          (launch AoWz.exe first; open a tactical combat for the best data)

⚠ Only the MOD pair is searched (zigexe.EXES). The root's AoW.exe / AoWCompat.exe are VANILLA:
attaching to one would print vanilla geometry as though it were Ziggurat's, with no error.

Field map (decoded, see Combat_Log_Implementation_Design.md):
  TAoWComponent: +0x7c WinWidth  +0x80 WinHeight  +0x84 WinLeft  +0x88 WinTop
                 +0x75 visible   +0xcc parent     +0xd4 alignment  +0x1d8 winmanager
                 +0x154 MinWidth +0x158 MinHeight +0x15c MaxWidth +0x160 MaxHeight +0x170 UseManagerBorders
  TAOWAlignment: +0x04 WidthPercent(byte) +0x05 HeightPercent(byte) +0x08 LeftOffPct +0x0c RightOffPct
                 +0x10 TopOffPct +0x14 BottomOffPct +0x18 LeftOffset +0x1c RightOffset
                 +0x20 TopOffset +0x24 BottomOffset +0x28 AlignWidth +0x29 AlignHeight
  enums: 0=None 1=Left/Top 2=Right/Bottom 3=Both 4=Center
"""
import ctypes, ctypes.wintypes as w, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zignames import zigexe

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_VM_READ = 0x0010; PROCESS_QUERY_INFORMATION = 0x0400

def pids_by_name(name):
    TH32CS_SNAPPROCESS = 2
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize",w.DWORD),("cntUsage",w.DWORD),("th32ProcessID",w.DWORD),
                    ("th32DefaultHeapID",ctypes.POINTER(ctypes.c_ulong)),("th32ModuleID",w.DWORD),
                    ("cntThreads",w.DWORD),("th32ParentProcessID",w.DWORD),("pcPriClassBase",ctypes.c_long),
                    ("dwFlags",w.DWORD),("szExeFile",ctypes.c_char*260)]
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    e = PE32(); e.dwSize = ctypes.sizeof(PE32); out=[]
    if k32.Process32First(snap, ctypes.byref(e)):
        while True:
            if e.szExeFile.decode(errors="replace").lower() == name.lower():
                out.append(e.th32ProcessID)
            if not k32.Process32Next(snap, ctypes.byref(e)): break
    k32.CloseHandle(snap); return out

class Mem:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h: raise OSError("OpenProcess failed (try running as admin): %d"%ctypes.get_last_error())
    def read(self, addr, n):
        buf = (ctypes.c_char*n)(); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return bytes(buf[:got.value])
    def u32(self, a):
        b=self.read(a,4);  return struct.unpack("<I",b)[0] if b else None
    def i32(self, a):
        b=self.read(a,4);  return struct.unpack("<i",b)[0] if b else None
    def u8(self, a):
        b=self.read(a,1);  return b[0] if b else None

AW=["awNone","awLeft","awRight","awBoth","awCenter"]
AH=["ahNone","ahTop","ahBottom","ahBoth","ahCenter"]

def dump_window(m, label, gvar, winfield=0x44):
    inst = m.u32(gvar)
    print(f"\n=== {label} ===")
    print(f"  instance global [{gvar:08X}] = {inst:08X}" if inst else f"  instance global [{gvar:08X}] = NIL")
    if not inst: return
    ctl = m.u32(inst+winfield)
    if not ctl:
        print(f"  window ctl [+{winfield:#x}] = NIL"); return
    vis = m.u8(ctl+0x75)
    W,H,L,T = m.i32(ctl+0x7c), m.i32(ctl+0x80), m.i32(ctl+0x84), m.i32(ctl+0x88)
    print(f"  ctl={ctl:08X}  visible={vis}   rect: Left={L} Top={T} W={W} H={H}   (bottom={T+H if None not in (T,H) else '?'})")
    mnw,mnh,mxw,mxh = m.i32(ctl+0x154), m.i32(ctl+0x158), m.i32(ctl+0x15c), m.i32(ctl+0x160)
    print(f"  Min/Max: MinW={mnw} MinH={mnh} MaxW={mxw} MaxH={mxh}  UseManagerBorders={m.u8(ctl+0x170)}")
    par = m.u32(ctl+0xcc); al = m.u32(ctl+0xd4)
    if par:
        pw,ph = m.i32(par+0x7c), m.i32(par+0x80)
        print(f"  parent={par:08X}  parent W={pw} H={ph}")
        # Blt-bounds verdict. aowInt's blit path raises "Blt Error" when a window's rect does not
        # lie inside the surface it is being composited onto; our cloned log window owns an ABSOLUTE
        # cave-set rect (awNone/ahNone) derived for the map screen, so it can be perfectly valid
        # there and out of bounds once another window owns the surface. Flag it explicitly rather
        # than leaving four numbers to be eyeballed.
        if None not in (W,H,L,T,pw,ph):
            bad=[]
            if L < 0: bad.append(f"Left {L} < 0")
            if T < 0: bad.append(f"Top {T} < 0")
            if L+W > pw: bad.append(f"right {L+W} > parent W {pw}")
            if T+H > ph: bad.append(f"bottom {T+H} > parent H {ph}")
            if W <= 0 or H <= 0: bad.append(f"degenerate size {W}x{H}")
            print("  BLT-BOUNDS: " + ("*** OUT OF BOUNDS: " + "; ".join(bad) + " ***" if bad
                                      else "inside parent (ok)"))
    if al:
        aw,ah = m.u8(al+0x28), m.u8(al+0x29)
        print(f"  align: {AW[aw] if aw is not None and aw<5 else aw} / {AH[ah] if ah is not None and ah<5 else ah}"
              f"  WidthPct={m.u8(al+4)} HeightPct={m.u8(al+5)}")
        print(f"         offsets L={m.i32(al+0x18)} R={m.i32(al+0x1c)} T={m.i32(al+0x20)} B={m.i32(al+0x24)}"
              f"   offPct L={m.i32(al+8)} R={m.i32(al+0xc)} T={m.i32(al+0x10)} B={m.i32(al+0x14)}")

def main():
    pids, exe = [], None
    for name in zigexe.EXES:                       # the MOD pair only -- see the module docstring
        pids = pids_by_name(name)
        if pids:
            exe = name
            break
    if not pids:
        print("%s is not running. Launch the game (ideally into a tactical battle) and re-run."
              % " / ".join(zigexe.EXES))
        return 1
    print("attached to %s pid %d" % (exe, pids[0]))
    m = Mem(pids[0])
    if m.read(0x400000,2) != b"MZ":
        print("cannot read the image base -- try running this shell as Administrator."); return 1
    # ring state
    magic = m.read(0x60D000,4)
    print("\n=== combat-log ring @0x60D000 ===")
    print(f"  magic={magic!r} (want b'CLG1')  wrIdx={m.u32(0x60D004)}  rdIdx={m.u32(0x60D008)}  tacticalFlag={m.u32(0x60D00C)}")
    for i in range(3):
        p = 0x60D020 + i*128
        b = m.read(p,128)
        if b: print(f"  slot{i}: len={b[0]:3d} {b[1:1+min(b[0],90)]!r}")
    dump_window(m, "TCUnitWin (stock tactical unit card)", 0x45B1A8)
    dump_window(m, "TCombatLogWin (ours)",                 0x45B2E0)
    dump_window(m, "TFastCombatWindow (replay)",           0x45B1B0)
    dump_window(m, "TTCScanner (Battle Map)",              0x45B290)
    return 0

if __name__ == "__main__":
    sys.exit(main())
