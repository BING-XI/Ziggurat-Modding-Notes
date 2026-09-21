"""dlg_geom.py — read a live AoW dialog's window rect, and optionally resize the game window
around it to see what the toolkit does to that rect.

    python dlg_geom.py                       dump THeroUpgradeDlg's geometry once
    python dlg_geom.py --resize 900 700      shrink the game window, dump, restore, dump

Why this exists: the hero level-up dialog is 960x860 and comes back mangled after the game
window is made smaller and then bigger again. Whether that is recoverable depends on WHERE the
860 goes -- ReAlign (aowInt 0x598030FC) recomputes Left/Top from the live parent size on every
resize but only recomputes Height for ahBoth/ahCenter, so a clamp elsewhere would be a
different fix from a negative Top. Reading it beats reasoning about it.

⚠ Only the MOD pair is searched (zigexe.EXES). The root's AoW.exe / AoWCompat.exe are VANILLA:
attaching to one would print vanilla geometry as though it were Ziggurat's, with no error.

Field map is the one decoded in Combat_Log_Implementation_Design.md:
  TAoWComponent  +0x7c W  +0x80 H  +0x84 Left  +0x88 Top  +0x75 visible  +0xcc parent
                 +0xd4 alignment  +0x154 MinW +0x158 MinH +0x15c MaxW +0x160 MaxH
  TAOWAlignment  +0x04 WidthPct +0x05 HeightPct +0x08/0c/10/14 L/R/T/B percents
                 +0x18/1c/20/24 L/R/T/B offsets  +0x28 AlignWidth  +0x29 AlignHeight
"""
import ctypes, ctypes.wintypes as w, os, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zignames import zigexe

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32d = ctypes.WinDLL("user32", use_last_error=True)
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

AW = ["awNone", "awLeft", "awRight", "awBoth", "awCenter"]
AH = ["ahNone", "ahTop", "ahBottom", "ahBoth", "ahCenter"]

# form instance globals (the CreateForm stanza's DATA slots), from HeroUpgradeDlg_Categories_Design.md
FORMS = {"THeroUpgradeDlg": 0x45B228}


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
    k32.CloseHandle(snap)
    return out


class Mem:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h:
            raise OSError("OpenProcess failed (run as admin?): %d" % ctypes.get_last_error())

    def read(self, a, n):
        buf = (ctypes.c_char * n)(); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def u32(self, a):
        b = self.read(a, 4); return struct.unpack("<I", b)[0] if b and len(b) == 4 else None

    def i32(self, a):
        b = self.read(a, 4); return struct.unpack("<i", b)[0] if b and len(b) == 4 else None

    def u8(self, a):
        b = self.read(a, 1); return b[0] if b else None


def find_win_field(m, inst):
    """The form's AOW window is a published field; find it rather than trusting one offset.
    A plausible control has a sane rect and points back at a parent that also has one."""
    for off in range(0x20, 0x120, 4):
        p = m.u32(inst + off)
        if not p or p < 0x10000:
            continue
        W, H = m.i32(p + 0x7c), m.i32(p + 0x80)
        par = m.u32(p + 0xcc)
        if None in (W, H) or not (32 <= W <= 8192 and 32 <= H <= 8192):
            continue
        if par and m.i32(par + 0x7c) and 32 <= (m.i32(par + 0x7c) or 0) <= 8192:
            return off, p
    return None, None


def rect(m, ctl, indent="  "):
    W, H, L, T = (m.i32(ctl + 0x7c), m.i32(ctl + 0x80), m.i32(ctl + 0x84), m.i32(ctl + 0x88))
    print("%sctl=%08X  vis=%s  Left=%s Top=%s W=%s H=%s" % (indent, ctl, m.u8(ctl + 0x75), L, T, W, H))
    print("%sMin/Max: %sx%s .. %sx%s" % (indent, m.i32(ctl + 0x154), m.i32(ctl + 0x158),
                                         m.i32(ctl + 0x15c), m.i32(ctl + 0x160)))
    par, al = m.u32(ctl + 0xcc), m.u32(ctl + 0xd4)
    if par:
        print("%sparent=%08X  parent %sx%s" % (indent, par, m.i32(par + 0x7c), m.i32(par + 0x80)))
    if al:
        aw, ah = m.u8(al + 0x28), m.u8(al + 0x29)
        print("%salign %s/%s  Wpct=%s Hpct=%s  off L=%s R=%s T=%s B=%s"
              % (indent, AW[aw] if aw is not None and aw < 5 else aw,
                 AH[ah] if ah is not None and ah < 5 else ah, m.u8(al + 4), m.u8(al + 5),
                 m.i32(al + 0x18), m.i32(al + 0x1c), m.i32(al + 0x20), m.i32(al + 0x24)))
    return W, H, L, T


def game_hwnd(pid):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    def cb(h, _l):
        p = w.DWORD()
        u32d.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32d.IsWindowVisible(h):
            r = w.RECT()
            u32d.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 200 and r.bottom - r.top > 200:
                found.append((h, r.right - r.left, r.bottom - r.top))
        return True

    u32d.EnumWindows(cb, 0)
    return found[0] if found else (None, 0, 0)


def field_names(m, inst):
    """{control pointer: published field name} for a Delphi form instance.

    The field table hangs off [VMT-0x2C]: u16 count, u32 classtab, then per entry
    {u32 offset, u16 classindex, shortstring name}. Reading it live means the dump is labelled
    with the DFM's own names (StatePnl, UpgradePnl, AvailAb3 ...) instead of raw pointers.
    """
    vmt = m.u32(inst)
    tab = m.u32(vmt - 0x2C) if vmt else None
    if not tab:
        return {}
    blob = m.read(tab, 0x2000) or b""
    if len(blob) < 6:
        return {}
    cnt = struct.unpack_from("<H", blob)[0]
    p, out = 6, {}
    for _ in range(cnt):
        if p + 7 > len(blob):
            break
        off = struct.unpack_from("<I", blob, p)[0]
        ln = blob[p + 6]
        name = blob[p + 7:p + 7 + ln].decode("latin1", "replace")
        p += 7 + ln
        ptr = m.u32(inst + off)
        if ptr:
            out[ptr] = name
    return out


def tree(m, ctl, depth=0, seen=None, names=None):
    """Walk the child list at +0xd0 (a Classes.TList: count at +8, items at +4) and print every
    rect. This is the shape TAoWComponent.SetSize itself iterates, so it is the real child set."""
    seen = seen if seen is not None else set()
    if ctl in seen or depth > 4:
        return
    seen.add(ctl)
    W, H, L, T = (m.i32(ctl + 0x7c), m.i32(ctl + 0x80), m.i32(ctl + 0x84), m.i32(ctl + 0x88))
    al = m.u32(ctl + 0xd4)
    a = ""
    if al:
        aw, ah = m.u8(al + 0x28), m.u8(al + 0x29)
        a = "  %s/%s" % (AW[aw] if aw is not None and aw < 5 else aw,
                         AH[ah] if ah is not None and ah < 5 else ah)
    print("%s%-14s %4sx%-4s @ %4s,%-4s  vis=%s%s"
          % ("    " * depth + ("+- " if depth else ""),
             (names or {}).get(ctl, "%08X" % ctl), W, H, L, T, m.u8(ctl + 0x75), a))
    lst = m.u32(ctl + 0xd0)
    if not lst:
        return
    n, items = m.i32(lst + 8), m.u32(lst + 4)
    if not n or not items or n > 400:
        return
    for i in range(n):
        c = m.u32(items + 4 * i)
        if c:
            tree(m, c, depth + 1, seen, names)


def snapshot(m, tag):
    print("\n---------- %s" % tag)
    for name, gvar in FORMS.items():
        inst = m.u32(gvar)
        if not inst:
            print("  %s: instance NIL" % name); continue
        off, ctl = find_win_field(m, inst)
        if not ctl:
            print("  %s: no window control found on the instance" % name); continue
        print("  %s  instance=%08X  window field +0x%02X" % (name, inst, off))
        r = rect(m, ctl)
        if "--tree" in sys.argv:
            print("  ---- child tree (design: Dlg 960x860, StatePnl 908x224 @26,53,"
                  " UpgradePnl 908x530 @26,285) ----")
            tree(m, ctl, names=field_names(m, inst))
        return r
    return None


def main():
    pids = []
    for name in zigexe.EXES:                       # the MOD pair only -- see the module docstring
        pids = pids_by_name(name)
        if pids:
            break
    if not pids:
        print("%s is not running." % " / ".join(zigexe.EXES)); return 1
    m = Mem(pids[0])
    hwnd, ww, wh = game_hwnd(pids[0])
    print("pid %d   game window %s  %dx%d" % (pids[0], hex(hwnd) if hwnd else "?", ww, wh))
    snapshot(m, "as-is")

    if "--resize" in sys.argv:
        i = sys.argv.index("--resize")
        nw, nh = int(sys.argv[i + 1]), int(sys.argv[i + 2])
        SWP = 0x0004 | 0x0010                      # NOZORDER | NOACTIVATE
        u32d.SetWindowPos(hwnd, 0, 0, 0, nw, nh, SWP); time.sleep(1.5)
        snapshot(m, "after shrink to %dx%d" % (nw, nh))
        u32d.SetWindowPos(hwnd, 0, 0, 0, ww, wh, SWP); time.sleep(1.5)
        snapshot(m, "after restore to %dx%d" % (ww, wh))
    return 0


if __name__ == "__main__":
    sys.exit(main())
