#!/usr/bin/env python3
r"""
build_wheel_editor.py -- mouse-wheel scrolling for the EDITOR's real Win32 scrollbars (vcl30.dpl).

Spec: Modding Resources/Zig notes/Mouse_Wheel_Scrolling.md, deliverable (B).
Reference (NEVER run it -- same target filename): Modding Resources/Inioch/share3/
mouse_wheel_scrolling_patch.py. Its algorithm is user-confirmed in his editor; its blob is NOT
position-independent (`ff 15 <abs>` IAT calls, `push 0x413A8400`), so this is a keystone rewrite of
the same algorithm with the `call $+5; pop; sub` delta, independent of build_wheel_vclpump.py.

WHAT IT DOES
------------
Delphi 3 predates VCL wheel support: TControl/TWinControl have no WM_MOUSEWHEEL handling, so the
wheel only ever worked where Windows itself scrolls a native control. At Forms.TApplication.Run
(entry 0x4133BC9C, 7-byte prologue stolen) an installer cave calls
SetWindowsHookExA(WH_MOUSE=7, MouseProc, 0, GetCurrentThreadId()) -- a thread-local hook on the UI
thread, installed once per process -- then replays the prologue and jumps to Run+7.

MouseProc(nCode, wParam, lParam), stdcall, ret 0xC:
  * passthrough (CallNextHookEx) unless nCode == 0 (HC_ACTION) and wParam == WM_MOUSEWHEEL;
  * delta = (short) HIWORD(MOUSEHOOKSTRUCTEX.mouseData) = word [lParam+0x16]; start window =
    WindowFromPoint(MOUSEHOOKSTRUCT.pt);
  * primary axis is horizontal iff GetKeyState(VK_SHIFT) & 0x8000, else vertical; FIND(mask) walks
    the GetParent chain testing GetWindowLongA(GWL_STYLE) against WS_VSCROLL 0x200000 /
    WS_HSCROLL 0x100000, primary mask first, then the other;
  * found -> 3 x SendMessageA(hwnd, WM_VSCROLL 0x115 / WM_HSCROLL 0x114, delta > 0 ? SB_LINEUP 0
    : SB_LINEDOWN 1, 0) then SB_ENDSCROLL 8; return 1 (swallow, so the native control does not
    scroll a second time);
  * nothing scrollable -> CallNextHookEx.

In the GAME this hook is inert: the game process receives no WM_MOUSEWHEEL at all (Inioch's
MessageBox diagnostic, share1 section 5), which is why the in-game path is the WH_MOUSE_LL design in
build_wheel_vclpump.py. In the editor the two never double-scroll: if this hook swallows a wheel the
pump never sees it. (!) The claim that the pump's latches "can never arm" in an editor was based on
a false import count (the editors import 23 aowInt symbols, including the TAOWWinManager VMT) and is
UNPROVEN -- if a latch does arm there, the LL proc swallows the wheel before this hook sees it and the
editor's Win32 scrollbars stop working. Check G_THREADED == 0 in AoWDevEd.exe with wheel_probe.py.

Caves: MouseProc 0x413A8400 (1 KB budget), installer 0x413A8800 (0x200); zone 0x413A8400..0x413A8A00
in vcl30's CODE zero tail (content ends 0x413A8306). build_wheel_vclpump.py owns 0x413A8A00 upward.
IAT slots (all already imported): GetCurrentThreadId 0x413E43E8, SetWindowsHookExA 0x413E463C,
WindowFromPoint 0x413E45FC, GetWindowLongA 0x413E4758, GetParent 0x413E4784, SendMessageA 0x413E468C,
CallNextHookEx 0x413E4894, GetKeyState 0x413E47B4. No globals. CODE file = VA - 0x41300C00.

Usage
  python build_scripts/build_wheel_editor.py            dry run + state
  python build_scripts/build_wheel_editor.py --apply    patch (backup vcl30.dpl.pre-wheeleditor,
                                                        once, only from a file this feature has not
                                                        touched -- it may already carry the pump)
  python build_scripts/build_wheel_editor.py --undo     surgical: restore Run's 7 bytes, zero the zone
  python build_scripts/build_wheel_editor.py --dis      disassemble both caves (read it!)
Independent of (A); apply/undo in any order relative to it.
"""
import os
import re
import shutil
import struct
import sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, x86

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
VCL = os.path.join(GAME, "vcl30.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(VCL) + ".pre-wheeleditor")

IMAGE_BASE = 0x41300000
MOD_LO, MOD_HI = 0x41300000, 0x41440000
PROC_VA, PROC_BUDGET = 0x413A8400, 0x400
INST_VA, INST_BUDGET = 0x413A8800, 0x200
OWN_CODE_LO, OWN_CODE_HI = 0x413A8400, 0x413A8A00

H6_SITE, H6_ORIG, H6_RESUME = 0x4133BC9C, bytes.fromhex("558bec518945fc"), 0x4133BCA3

IAT = dict(GetCurrentThreadId=0x413E43E8, SetWindowsHookExA=0x413E463C, WindowFromPoint=0x413E45FC,
           GetWindowLongA=0x413E4758, GetParent=0x413E4784, SendMessageA=0x413E468C,
           CallNextHookEx=0x413E4894, GetKeyState=0x413E47B4)

WH_MOUSE, WM_MOUSEWHEEL, VK_SHIFT, GWL_STYLE = 7, 0x20A, 0x10, -16
WS_VSCROLL, WS_HSCROLL, WM_VSCROLL, WM_HSCROLL = 0x200000, 0x100000, 0x115, 0x114
SB_LINEUP, SB_LINEDOWN, SB_ENDSCROLL, LINES = 0, 1, 8, 3

# info only: the pump half's hook, so the state report shows what else is on this file
PUMP_H5_SITE, PUMP_H5_ORIG = 0x4133BA6D, bytes.fromhex("837c240812")

KILL_HINT = ("the DLL is locked by a running AoW binary -- kill it and retry:\n"
             "  Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWCompat|AoWDevEd|AoWEd)$' }"
             " | Stop-Process -Force")

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)
cs.detail = True


# ============================================================ PE helpers
class Module:
    def __init__(self, path, image_base):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        d = self.d
        e = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[e:e + 4] == b"PE\0\0", "not a PE: %s" % path
        n = struct.unpack_from("<H", d, e + 6)[0]
        oh = struct.unpack_from("<H", d, e + 0x14)[0]
        self.image_base = struct.unpack_from("<I", d, e + 0x34)[0]
        assert self.image_base == image_base, "%s: image base %#x, expected %#x" % (
            path, self.image_base, image_base)
        self.secs = []
        for i in range(n):
            o = e + 0x18 + oh + i * 40
            name = d[o:o + 8].rstrip(b"\0").decode("latin1")
            vs, va, rs, ptr = struct.unpack_from("<IIII", d, o + 8)
            ch = struct.unpack_from("<I", d, o + 36)[0]
            self.secs.append((name, va, vs, rs, ptr, ch))
        self.reloc_dir = struct.unpack_from("<II", d, e + 0x18 + 96 + 5 * 8)

    def off(self, va, n=1, write=False):
        r = va - self.image_base
        for name, sva, vs, rs, ptr, ch in self.secs:
            if sva <= r < sva + max(vs, rs):
                if r + n - sva > rs:
                    raise ValueError("VA %#x+%#x runs past raw data of %s" % (va, n, name))
                if write and not (ch & 0x80000000):
                    raise ValueError("VA %#x is in %s which is not writable (%08X)" % (va, name, ch))
                return ptr + (r - sva)
        raise ValueError("VA %#x is in no section" % va)

    def read(self, va, n):
        o = self.off(va, n)
        return bytes(self.d[o:o + n])

    def write(self, va, blob):
        o = self.off(va, len(blob))
        self.d[o:o + len(blob)] = blob

    def rva2off(self, rva):
        for name, sva, vs, rs, ptr, ch in self.secs:
            if sva <= rva < sva + max(vs, rs):
                return ptr + rva - sva
        return None

    def reloc_hits(self, ranges):
        rrva, rsz = self.reloc_dir
        off = self.rva2off(rrva)
        if off is None or not rsz:
            return []
        franges = [(self.off(lo), self.off(lo) + (hi - lo)) for lo, hi in ranges]
        end, hits = off + rsz, []
        while off < end:
            page, blk = struct.unpack_from("<II", self.d, off)
            if blk < 8:
                break
            for i in range((blk - 8) // 2):
                w = struct.unpack_from("<H", self.d, off + 8 + i * 2)[0]
                if w >> 12 == 0:
                    continue
                fo = self.rva2off(page + (w & 0xFFF))
                if fo is None:
                    continue
                for lo, hi in franges:
                    if lo <= fo + 3 and fo < hi:
                        hits.append(fo)
            off += blk
        return hits


# ============================================================ assembler helpers
def asm(src, base):
    enc, _ = ks.asm(src, base)
    return bytes(enc)


def dis_lines(blob, base, title):
    out = ["  --- %s @ %08X (%d B) ---" % (title, base, len(blob))]
    for i in cs.disasm(blob, base):
        out.append("    %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    return out


def pic_lint(blob, base, title):
    bad, prev = [], None
    for i in cs.disasm(blob, base):
        rel = i.bytes[0] in (0xE8, 0xE9, 0xEB) or 0x70 <= i.bytes[0] <= 0x7F or (
            i.bytes[0] == 0x0F and 0x80 <= i.bytes[1] <= 0x8F)
        for op in i.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append("%s: %08X %s %s  (absolute memory operand)" % (title, i.address,
                                                                           i.mnemonic, i.op_str))
            if op.type == x86.X86_OP_IMM and MOD_LO <= (op.imm & 0xFFFFFFFF) < MOD_HI and not rel:
                delta_idiom = (i.mnemonic == "sub" and prev is not None and prev.mnemonic == "pop"
                               and (op.imm & 0xFFFFFFFF) == prev.address)
                if not delta_idiom:
                    bad.append("%s: %08X %s %s  (module VA as immediate)" % (
                        title, i.address, i.mnemonic, i.op_str))
        prev = i
    return bad


def check_push_imm8(blob, base, title, allowed_negative=()):
    """keystone trap: `push 0xFFFF` -> `6A FF`. The only negative imm8 push here is GWL_STYLE (-16)."""
    bad = []
    for i in cs.disasm(blob, base):
        if i.mnemonic == "push" and i.bytes[0] == 0x6A and i.bytes[1] >= 0x80:
            if struct.unpack("<b", i.bytes[1:2])[0] not in allowed_negative:
                bad.append("%s: %08X push imm8 sign-extended: %s" % (title, i.address, i.op_str))
    return bad


def pad(blob, budget, name):
    assert len(blob) <= budget, "%s is %d B, over its %d B budget" % (name, len(blob), budget)
    return blob + bytes(budget - len(blob))


def displaced(orig):
    return ".byte " + ", ".join("%#04x" % b for b in orig)


# ============================================================ the caves
def src_mouseproc():
    return "\n".join([
        "push ebp", "mov ebp, esp",
        "sub esp, 0x40",
        "push ebx",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",                  # ebx = load delta
        "mov eax, [ebp+8]",                                          # nCode
        "test eax, eax",
        "jnz Lpass",                                                 # != HC_ACTION (incl. < 0)
        "cmp dword ptr [ebp+0xC], %#x" % WM_MOUSEWHEEL,
        "jne Lpass",
        "mov edx, [ebp+0x10]",                                       # MOUSEHOOKSTRUCTEX*
        "movsx eax, word ptr [edx+0x16]",                            # HIWORD(mouseData) = delta
        "mov [ebp-8], eax",
        "push dword ptr [edx+4]",                                    # pt.y
        "push dword ptr [edx]",                                      # pt.x
        "call dword ptr [ebx+%#x]" % IAT["WindowFromPoint"],
        "mov [ebp-4], eax",                                          # start window
        "push %#x" % VK_SHIFT,
        "call dword ptr [ebx+%#x]" % IAT["GetKeyState"],
        "test ax, 0x8000",
        "jnz Lshift",
        "mov dword ptr [ebp-0xC], %#x" % WS_VSCROLL,                 # primary: vertical
        "mov dword ptr [ebp-0x10], %#x" % WM_VSCROLL,
        "mov dword ptr [ebp-0x14], %#x" % WS_HSCROLL,                # secondary: horizontal
        "mov dword ptr [ebp-0x18], %#x" % WM_HSCROLL,
        "jmp Lgo",
        "Lshift:",
        "mov dword ptr [ebp-0xC], %#x" % WS_HSCROLL,                 # Shift: horizontal first
        "mov dword ptr [ebp-0x10], %#x" % WM_HSCROLL,
        "mov dword ptr [ebp-0x14], %#x" % WS_VSCROLL,
        "mov dword ptr [ebp-0x18], %#x" % WM_VSCROLL,
        "Lgo:",
        "mov ecx, [ebp-0xC]",
        "call Lfind",
        "test eax, eax",
        "jz Ltry2",
        "mov ecx, [ebp-0x10]",
        "call Lscroll",
        "jmp Lhandled",
        "Ltry2:",
        "mov ecx, [ebp-0x14]",
        "call Lfind",
        "test eax, eax",
        "jz Lpass",
        "mov ecx, [ebp-0x18]",
        "call Lscroll",
        "Lhandled:",
        "mov eax, 1",                                                # swallow
        "jmp Lexit",
        "Lpass:",
        "push dword ptr [ebp+0x10]",
        "push dword ptr [ebp+0xC]",
        "push dword ptr [ebp+8]",
        "push 0",
        "call dword ptr [ebx+%#x]" % IAT["CallNextHookEx"],
        "Lexit:",
        "pop ebx",
        "mov esp, ebp", "pop ebp",
        "ret 0xC",
        # ---- FIND(ecx = style mask) -> eax = first window up the parent chain with it, or 0
        "Lfind:",
        "mov [ebp-0x20], ecx",
        "mov eax, [ebp-4]",
        "mov [ebp-0x1C], eax",
        "Lfloop:",
        "mov eax, [ebp-0x1C]",
        "test eax, eax",
        "jz Lfnone",
        "push %d" % GWL_STYLE,
        "push eax",
        "call dword ptr [ebx+%#x]" % IAT["GetWindowLongA"],
        "mov edx, [ebp-0x20]",
        "test eax, edx",
        "jnz Lffound",
        "push dword ptr [ebp-0x1C]",
        "call dword ptr [ebx+%#x]" % IAT["GetParent"],
        "mov [ebp-0x1C], eax",
        "jmp Lfloop",
        "Lffound:",
        "mov eax, [ebp-0x1C]",
        "ret",
        "Lfnone:",
        "xor eax, eax",
        "ret",
        # ---- SCROLL(eax = hwnd, ecx = WM_xSCROLL): LINES x SB_LINEUP/DOWN, then SB_ENDSCROLL
        "Lscroll:",
        "mov [ebp-0x24], eax",
        "mov [ebp-0x28], ecx",
        "mov edx, %d" % SB_LINEUP,
        "mov eax, [ebp-8]",
        "test eax, eax",
        "jg Lsdir",
        "mov edx, %d" % SB_LINEDOWN,
        "Lsdir:",
        "mov [ebp-0x2C], edx",
        "mov dword ptr [ebp-0x30], %d" % LINES,
        "Lsloop:",
        "push 0",
        "push dword ptr [ebp-0x2C]",
        "push dword ptr [ebp-0x28]",
        "push dword ptr [ebp-0x24]",
        "call dword ptr [ebx+%#x]" % IAT["SendMessageA"],
        "dec dword ptr [ebp-0x30]",
        "jnz Lsloop",
        "push 0",
        "push %d" % SB_ENDSCROLL,
        "push dword ptr [ebp-0x28]",
        "push dword ptr [ebp-0x24]",
        "call dword ptr [ebx+%#x]" % IAT["SendMessageA"],
        "ret",
    ])


def src_installer():
    return "\n".join([
        "pushad",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",
        "call dword ptr [ebx+%#x]" % IAT["GetCurrentThreadId"],
        "push eax",                                                  # dwThreadId (this thread)
        "push 0",                                                    # hMod (in-process, own thread)
        "lea eax, [ebx+%#x]" % PROC_VA,
        "push eax",                                                  # lpfn
        "push %d" % WH_MOUSE,
        "call dword ptr [ebx+%#x]" % IAT["SetWindowsHookExA"],       # result ignored (his design)
        "popad",
        displaced(H6_ORIG),                                          # push ebp; mov ebp,esp; push ecx;
        "jmp %#x" % H6_RESUME,                                       # mov [ebp-4],eax
    ])


def build_caves():
    proc = asm(src_mouseproc(), PROC_VA)
    inst = asm(src_installer(), INST_VA)
    tail = H6_ORIG + b"\xE9" + struct.pack("<i", H6_RESUME - (INST_VA + len(inst)))
    assert inst.endswith(tail), "installer must end with the displaced prologue + jmp Run+7"
    assert proc.count(b"\xC2\x0C\x00") == 1 and proc[0] == 0x55
    return {"MouseProc": (PROC_VA, PROC_BUDGET, proc), "installer": (INST_VA, INST_BUDGET, inst)}


def hook_bytes():
    return b"\xE9" + struct.pack("<i", INST_VA - (H6_SITE + 5)) + b"\x90\x90"


def main(argv):
    apply_, undo, show = "--apply" in argv, "--undo" in argv, ("--dis" in argv or "--show" in argv)
    for a in argv:
        if a not in ("--apply", "--undo", "--dis", "--show"):
            sys.exit("unknown flag %s" % a)
    caves = build_caves()

    problems = []
    for name, (va, budget, blob) in caves.items():
        pad(blob, budget, name)
        problems += pic_lint(blob, va, name)
        problems += check_push_imm8(blob, va, name, allowed_negative=(GWL_STYLE,))
        if re.search(rb"[A-Za-z]:\\", blob):
            problems.append("%s contains a drive-letter path" % name)
    if problems:
        print("\n".join(problems))
        sys.exit("ABORT: static checks failed")

    if show:
        print("  H6 %08X: %s -> %s" % (H6_SITE, H6_ORIG.hex(" "), hook_bytes().hex(" ")))
        for name, (va, budget, blob) in caves.items():
            print("\n".join(dis_lines(blob, va, name)))
        return 0

    mod = Module(VCL, IMAGE_BASE)
    hits = mod.reloc_hits([(H6_SITE, H6_SITE + 7), (OWN_CODE_LO, OWN_CODE_HI)])
    if hits:
        sys.exit("ABORT: .reloc entries inside our ranges at file offsets %s" % [hex(h) for h in hits])
    for slot in IAT.values():
        mod.off(slot, 4)

    print("build_wheel_editor")
    print("  file: %s" % VCL)
    cur = mod.read(H6_SITE, 7)
    st = "vanilla" if cur == H6_ORIG else "applied" if cur == hook_bytes() else "foreign"
    print("  %-42s %08X  %-8s %s" % ("H6 RUN  TApplication.Run entry", H6_SITE, st, cur.hex(" ")))
    if st == "foreign":
        sys.exit("ABORT: the hook site is neither vanilla nor ours -- someone else owns it.")
    for name, (va, budget, blob) in caves.items():
        z = mod.read(va, budget)
        zd = "zero" if set(z) <= {0} else "ours" if z == pad(blob, budget, name) else "nonzero"
        print("  %-42s %08X  %s  (%d B of %#x)" % ("cave " + name, va, zd, len(blob), budget))
    p = mod.read(PUMP_H5_SITE, 5)
    print("  %-42s %08X  %s" % ("(info) pump H5 site", PUMP_H5_SITE,
                                "vanilla" if p == PUMP_H5_ORIG else "applied" if p[0] == 0xE8 else "other"))

    if undo:
        if st == "vanilla":
            print("\nnothing to undo: H6 vanilla")
            return 0
        assert mod.read(H6_SITE, 7) == hook_bytes()
        mod.write(H6_SITE, H6_ORIG)
        mod.write(OWN_CODE_LO, bytes(OWN_CODE_HI - OWN_CODE_LO))
        try:
            open(VCL, "wb").write(bytes(mod.d))
        except PermissionError:
            sys.exit("ABORT: " + KILL_HINT)
        chk = Module(VCL, IMAGE_BASE)
        assert chk.read(H6_SITE, 7) == H6_ORIG
        assert set(chk.read(OWN_CODE_LO, OWN_CODE_HI - OWN_CODE_LO)) <= {0}
        print("\nundone: H6 restored, %08X..%08X zeroed; no backup touched." % (OWN_CODE_LO, OWN_CODE_HI))
        return 0

    plan = []
    fresh = st == "vanilla"
    if fresh:
        if set(mod.read(OWN_CODE_LO, OWN_CODE_HI - OWN_CODE_LO)) > {0}:
            sys.exit("ABORT: cave zone %08X..%08X is not zero -- someone else owns it." % (OWN_CODE_LO,
                                                                                            OWN_CODE_HI))
        for name, (va, budget, blob) in caves.items():
            plan.append((va, pad(blob, budget, name), "cave %s (%d B + zero pad)" % (name, len(blob))))
        plan.append((H6_SITE, hook_bytes(), "H6 jmp -> installer"))
    else:
        for name, (va, budget, blob) in caves.items():
            if mod.read(va, budget) != pad(blob, budget, name):
                plan.append((va, pad(blob, budget, name), "cave %s (rewrite in place)" % name))
    if not plan:
        print("\nalready applied -- nothing to write.")
        return 0
    print("\n%s -- %d region(s):" % ("fresh apply" if fresh else "rewrite in place", len(plan)))
    for va, new, desc in plan:
        print("   %08X  %4d B  %s" % (va, len(new), desc))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write.  (--dis shows the caves)")
        return 0

    if fresh and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(VCL, BACKUP)
        print("backup written: %s" % os.path.basename(BACKUP))
    elif fresh:
        print("backup already exists, left as-is: %s" % os.path.basename(BACKUP))
    else:
        print("re-tune over an existing install: no backup taken")

    for va, new, desc in plan:
        cur = mod.read(va, len(new))
        if fresh:
            if va == H6_SITE:
                assert cur == H6_ORIG, "verify-before-write: H6 changed"
            else:
                assert set(cur) <= {0}, "verify-before-write: zone at %08X changed" % va
        mod.write(va, new)
    try:
        open(VCL, "wb").write(bytes(mod.d))
    except PermissionError:
        sys.exit("ABORT: " + KILL_HINT)
    chk = Module(VCL, IMAGE_BASE)
    for va, new, desc in plan:
        assert chk.read(va, len(new)) == new, "read-back mismatch at %08X" % va
    print("written and read back: %d region(s)." % len(plan))
    print("\napplied, UNTESTED -- needs the user's test in AoWDevEd.exe (lists, treeviews, scroll boxes;"
          " Shift+wheel horizontal; no double-scroll) and a normal start of AoWEd.exe/AoWDevEd.exe.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
