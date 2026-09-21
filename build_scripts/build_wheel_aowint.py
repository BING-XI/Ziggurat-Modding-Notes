#!/usr/bin/env python3
r"""
build_wheel_aowint.py -- mouse-wheel scrolling, foundation half 1 of 2: aowInt.dpl.

Spec: Modding Resources/Zig notes/Mouse_Wheel_Scrolling.md (aow-pm, 2026-09-02).
Prior art (reference only -- NEVER run them, they target our filenames with GAME one level up):
  Modding Resources/Inioch/share5/patch scripts/build_wheel_aowint.py
  Modding Resources/Inioch/share4/patch scripts/build_memo_wheel_inert.py

WHAT THIS HALF DOES
-------------------
The in-game UI is aowInt's own widget toolkit (TAOWListBox / TAOWMemo / TAOWVScrollBar ...), not
Win32 controls, and the game never receives WM_MOUSEWHEEL at all (its render window is never the
focused window). So the wheel is delivered by a WH_MOUSE_LL hook owned by a dedicated thread in
vcl30.dpl (build_wheel_vclpump.py, half 2), which queues notches; the VCL message pump drains them
ON THE GAME THREAD by calling helper routines exported through a contract header in this module.

This half provides hover tracking and the scroll action, and is inert on its own:

  * latch block   0x5983E040 (DATA slack, 8 dwords):
        [0] g_hover     the TAOWListBox / TAOWMemo the cursor is inside, or 0
        [1] g_facenext  TLeaderSetupWin's FaceNextBtn while the cursor is on a TAOWImage of that
        [2] g_faceprev  window (portrait cycling), or 0
        [3..6]          build_wheel_ext.py (power slider, unit-window cycling)   [7] spare
  * H1 CLR  TAOWWinManager.CheckMouseMove entry 0x59807094 (steals 55 8B EC 83 C4 F4):
        zeroes the whole latch block at the start of every mouse-move sweep (gate G3).
  * H2 SET  TAOWListBox.CheckMouseMove+0x7D = 0x598175C5 (steals `mov [ebx+0x78],-1`, ebx = the
        listbox, reached only when the cursor is INSIDE the list): latch[0] = ebx.
  * H3 SET2 TAOWMemo.CheckMouseMove+0x9A = 0x5981A29A (same 7-byte marker, ebx = memo): latch[0].
  * H4 SET3 TAOWImage.CheckMouseMove+0x6A = 0x59815882 (steals `mov al,[ebx+0xC0]`, ebx = image):
        climbs <= 3 owner levels, scans each owner's children for TAOWButtons whose OnClick code
        pointer [btn+0x138] is TLeaderSetupWin.FaceNextBtnClick 0x416D54 / FacePrevBtnClick 0x416D0C
        (AoW.exe has no .reloc, so those are constants) and latches them in [1]/[2].
  * WheelScroll(delta) 0x59824200 -- stdcall(1), ret 4, eax = 1 handled / 0 not:
        1. hovered control owns a scrollbar ([lb+0x118] / [memo+0x120]) -> SetFPos(+/-LINES), fire
           its OnChange, Update the control;
        2. no own scrollbar -> find the governing sibling TAOWVScrollBar (the hero level-up /
           leader-setup shape: parallel lists driven by ONE bar through the form's OnChange) and
           drive THAT, so the cost column and the thumb move with the name column;
        3. neither: listbox -> SetListOff(+/-LINES); memo -> INERT (MEMO_NEEDS_SCROLLBAR, decision
           D2: city-view text boxes have no scrollbar and must not scroll). With the flag False a
           scrollbar-less memo takes SetListOff, which build_memo_clamp.py makes safe.
        Nothing hovered -> portrait cycling: wheel up fires FacePrevBtn.OnClick, down FaceNextBtn.
  * contract header 0x59824000 (CODE, constants) -- the ONLY thing the vcl30 half hard-codes:
        +00 'AZWH'  +04 version 0x00010000 (major 1)  +08 latch block RVA  +0C latch count
        +10 helper slot 0 = WheelScroll RVA   +14/+18/+1C helper slots 1-3 (extension, else 0)
    Helper ABI: stdcall(delta), ret 4, eax=1 handled; preserves ebx/esi/edi/ebp; runs on the game
    thread inside TApplication.ProcessMessage, so it may call any UI code.

U1 -- WHICH FIELD IS THE OWNING CONTAINER (settled statically 2026-09-02)
-----------------------------------------------------------------------
Inioch's caves walk `[ctrl+0x10C]` -> `[owner+0xD0]`; our herodlg live-memory work recorded the
parent at `+0xCC`. Both are right, and they are the same object for every control:

    AoWComp.TAoWComponent.SetOwner @0x59802480   (the only writer of +0xCC in aowInt)
        [self+0xCC] = owner; self is inserted into the owner's children TList [owner+0xD0]
        (data +4, count +8), z-ordered by [+0xA0]
    AoWControl.TAOWControl.SetOwner @0x5980B92C   (the only writer of +0x10C for a control)
        call TAoWComponent.SetOwner ; mov eax,[ebx+0xCC] ; mov [ebx+0x10C],eax

So +0x10C is TAOWControl's (instance size 0x114) alias of the TAoWComponent-level owner field
+0xCC (instance size 0x104), used by the hit-tests for coordinate translation. On the window-family
classes (TAOWWindowControl 0x1D0 / TAOWBaseWindow 0x1EC / TAOWPanel 0x1FC) +0x10C is a DIFFERENT
field. The sibling search and the <= 3-level portrait climb therefore walk +0xCC, which every object
reachable through it carries (every owner is a TAoWComponent, and TAoWComponent.Create @0x59802318
makes the +0xD0 list for all of them). Our 5-column level-up rebuild puts the five lists and their
five bars in UpgradePnl, so the search over [list+0xCC]=UpgradePnl finds each list's own bar
(nearest at/right of the list's left edge, vertical overlap required).

ADDRESSES (all verified on the live file; symbols from aowInt's export table)
--------------------------------------------------------------------------
  CODE file = VA - 0x59800C00, DATA file = VA - 0x59801A00 (section-aware va2off below).
  VMTs: TAOWListBox 0x59815F9C, TAOWMemo 0x5981848C, TAOWVScrollBar 0x5980C594, TAOWButton 0x59810DC0
  TAOWScrollBar.SetFPos 0x5980CA28 (eax=self, edx=pos; clamps), TAOWListBox.Update 0x59817138 /
  SetListOff 0x598168F4, TAOWMemo.Update 0x59819B18 / SetListOff 0x59819298 (lower-clamped by
  build_memo_clamp.py, applied 2026-08-28). Scrollbar: FPos +0x148, OnChange code/hiword/data
  +0x6C/+0x6E/+0x70. Button OnClick code/hiword/data +0x138/+0x13A/+0x13C. Control rect
  left/top/w/h +0x84/+0x88/+0x7C/+0x80. Listbox: scrollbar +0x118, top item +0x15C. Memo: scrollbar
  +0x120, top line +0x128.

  Caves (CODE zero tail, content ends 0x598227C6; reloc-free, collision-grepped 2026-09-02):
    0x59824000 header 0x40 | 0x59824040 CLR 0x80 | 0x598240C0 SET 0x40 | 0x59824100 SET2 0x40 |
    0x59824140 SET3 0xC0 | 0x59824200 WheelScroll 0x200 | 0x59824400..0x59824800 build_wheel_ext.py
  Do not touch 0x59822800..0x59823FFF (build_glowboost.py / build_bltprobe.py reservations + guard)
  or 0x5983E100..0x5983E1FF (bltprobe scratch). --diag counters: 0x5983E060 (16 dwords).

Every cave is position-independent (the DPL rebases): `call $+5; pop; sub reg,<VA>` delta, module
data via `lea/[reg+VA]`, intra-module calls rel32. The exe handler constants are COMPARED only.

Usage
  python build_scripts/build_wheel_aowint.py            dry run: site/cave state + cross-file chain
  python build_scripts/build_wheel_aowint.py --apply    patch (backup aowInt.dpl.pre-wheel, once,
                                                        only from a proven-unpatched file)
  python build_scripts/build_wheel_aowint.py --undo     surgical: restore H1-H4, zero own zones;
                                                        REFUSES while build_wheel_ext.py is present
  python build_scripts/build_wheel_aowint.py --dis      disassemble every cave (read it!)
  --diag   build with live counters (read with re_tools/wheel_probe.py); re-apply in place
Apply order: this script, then build_wheel_vclpump.py. Undo order: the reverse.
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
INT = os.path.join(GAME, "aowInt.dpl")
VCL = os.path.join(GAME, "vcl30.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(INT) + ".pre-wheel")

DIAG = "--diag" in sys.argv

# ---- build constants (decisions D2 / D3) ----
LINES = 3                       # list lines per wheel notch
MEMO_NEEDS_SCROLLBAR = True     # D2: a memo with no scrollbar (own or sibling) is inert

# ---- aowInt.dpl map ----
IMAGE_BASE = 0x59800000
MOD_LO, MOD_HI = 0x59800000, 0x59852000          # module extent, for the PIC lint

HDR_VA, HDR_BUDGET = 0x59824000, 0x40
CLR_VA, CLR_BUDGET = 0x59824040, 0x80
SET_VA, SET_BUDGET = 0x598240C0, 0x40
SET2_VA, SET2_BUDGET = 0x59824100, 0x40
SET3_VA, SET3_BUDGET = 0x59824140, 0xC0
WS_VA, WS_BUDGET = 0x59824200, 0x200
OWN_CODE_LO, OWN_CODE_HI = 0x59824000, 0x59824400
EXT_LO, EXT_HI = 0x59824400, 0x59824800           # build_wheel_ext.py's zone -- never written here

LATCH = 0x5983E040                                # 8 dwords (DATA slack)
LATCH_N = 8
CNT = 0x5983E060                                  # --diag counters, 16 dwords
OWN_DATA_LO, OWN_DATA_HI = 0x5983E040, 0x5983E0C0

MAGIC = 0x48575A41                                # 'AZWH'
VERSION = 0x00010000                              # major 1

H1_SITE, H1_ORIG, H1_RESUME = 0x59807094, bytes.fromhex("558bec83c4f4"), 0x5980709A
H2_SITE, H2_ORIG, H2_RESUME = 0x598175C5, bytes.fromhex("c74378ffffffff"), 0x598175CC
H3_SITE, H3_ORIG, H3_RESUME = 0x5981A29A, bytes.fromhex("c74378ffffffff"), 0x5981A2A1
H4_SITE, H4_ORIG, H4_RESUME = 0x59815882, bytes.fromhex("8a83c0000000"), 0x59815888

VMT_LISTBOX, VMT_MEMO, VMT_VSCROLLBAR, VMT_BUTTON = 0x59815F9C, 0x5981848C, 0x5980C594, 0x59810DC0
F_SETFPOS, F_LB_UPDATE, F_LB_SETLISTOFF = 0x5980CA28, 0x59817138, 0x598168F4
F_MEMO_UPDATE, F_MEMO_SETLISTOFF = 0x59819B18, 0x59819298
FACE_NEXT_CLICK, FACE_PREV_CLICK = 0x416D54, 0x416D0C           # AoW.exe, fixed base, COMPARED only

COMP_OWNER, COMP_CHILDREN = 0xCC, 0xD0                          # TAoWComponent (see U1 above)
CTRL_LEFT, CTRL_TOP, CTRL_W, CTRL_H = 0x84, 0x88, 0x7C, 0x80
LB_VSCROLL, LB_LISTOFF, MEMO_VSCROLL, MEMO_LISTOFF = 0x118, 0x15C, 0x120, 0x128
SB_FPOS, SB_EVT_CODE, SB_EVT_HIWD, SB_EVT_DATA = 0x148, 0x6C, 0x6E, 0x70
BTN_EVT_CODE, BTN_EVT_HIWD, BTN_EVT_DATA = 0x138, 0x13A, 0x13C

# vcl30 half, read only for the chain verdict
VCL_IMAGE_BASE = 0x41300000
VCL_H5_SITE, VCL_H5_ORIG, VCL_PUMP_VA = 0x4133BA6D, bytes.fromhex("837c240812"), 0x413A8A00

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
        """Section-aware VA -> file offset; the whole [va, va+n) must be raw-backed."""
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
        """File offsets of .reloc entries whose 4-byte fixup overlaps any (lo_va, hi_va)."""
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


def pic_lint(blob, base, title, allow_imm=()):
    """Return the instructions that would break under rebasing.

    Violations: any memory operand with no base/index register (absolute [imm32]); any immediate
    inside the module's extent, except the `sub reg, <VA>` right after the delta `pop`, the exe
    handler constants (below the module), and rel32 branch targets (encoded relative).
    """
    bad = []
    prev = None
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
                if not delta_idiom and (op.imm & 0xFFFFFFFF) not in allow_imm:
                    bad.append("%s: %08X %s %s  (module VA as immediate)" % (
                        title, i.address, i.mnemonic, i.op_str))
        prev = i
    return bad


def check_push_imm8(blob, base, title):
    """The keystone trap: `push 0xFFFF` silently assembles as `6A FF` (= -1). Flag every imm8 push
    whose operand is negative -- none of our caves pushes a negative constant on purpose except
    GWL_STYLE, which this module never uses."""
    bad = []
    for i in cs.disasm(blob, base):
        if i.mnemonic == "push" and i.bytes[0] == 0x6A and i.bytes[1] >= 0x80:
            bad.append("%s: %08X push imm8 sign-extended: %s" % (title, i.address, i.op_str))
    return bad


def hook_bytes(site, cave_va, n):
    return b"\xE9" + struct.pack("<i", cave_va - (site + 5)) + b"\x90" * (n - 5)


def pad(blob, budget, name):
    assert len(blob) <= budget, "%s is %d B, over its %d B budget" % (name, len(blob), budget)
    return blob + bytes(budget - len(blob))


# ============================================================ the caves
def cnt(reg, idx):
    """--diag counter increment, or nothing."""
    return "inc dword ptr [%s+%#x]" % (reg, CNT + 4 * idx) if DIAG else ""


def src_clr():
    return "\n".join([
        "pushad",
        "call Lp", "Lp:", "pop edx", "sub edx, Lp",           # edx = load delta
        "lea edi, [edx+%#x]" % LATCH,
        "xor eax, eax",
        "mov ecx, %d" % LATCH_N,
        "cld",
        "rep stosd",                                            # gate G3: every latch, every sweep
        cnt("edx", 0),
        "popad",
        displaced(H1_ORIG),                                     # push ebp; mov ebp,esp; add esp,-0xC
        "jmp %#x" % H1_RESUME,
    ])


def displaced(orig):
    """Replay the stolen bytes VERBATIM (keystone would pick `89 E5` for `mov ebp,esp` where the
    original is `8B EC` -- same instruction, different encoding, and the tail check wants the
    original bytes)."""
    return ".byte " + ", ".join("%#04x" % b for b in orig)


def src_set(resume, idx):
    return "\n".join([
        "push eax", "pushfd",
        "call Lp", "Lp:", "pop eax", "sub eax, Lp",
        "mov [eax+%#x], ebx" % (LATCH + 0),                     # latch[0] = hovered control
        cnt("eax", idx),
        ("mov [eax+%#x], ebx" % (CNT + 4 * 10)) if DIAG else "",
        "popfd", "pop eax",
        "mov dword ptr [ebx+0x78], -1",                         # displaced marker
        "jmp %#x" % resume,
    ])


def src_set3():
    return "\n".join([
        "pushad", "pushfd",
        "call Lp", "Lp:", "pop ebp", "sub ebp, Lp",             # ebp = load delta
        "mov dword ptr [ebp+%#x], 0" % (LATCH + 4),
        "mov dword ptr [ebp+%#x], 0" % (LATCH + 8),
        cnt("ebp", 3),
        "mov esi, ebx",                                         # node = the image
        "mov edi, 3",                                           # owner levels to climb
        "Llvl:",
        "mov esi, [esi+%#x]" % COMP_OWNER,                      # owner (TAoWComponent, see U1)
        "test esi, esi",
        "jz Ldone",
        "mov eax, [esi+%#x]" % COMP_CHILDREN,                   # children TList
        "test eax, eax",
        "jz Lnext",
        "mov ecx, [eax+8]",                                     # count
        "mov ebx, [eax+4]",                                     # data
        "Lchild:",
        "dec ecx",
        "js Lnext",
        "mov eax, [ebx+ecx*4]",
        "test eax, eax",
        "jz Lchild",
        "lea edx, [ebp+%#x]" % VMT_BUTTON,
        "cmp [eax], edx",                                       # exactly TAOWButton
        "jne Lchild",
        "mov edx, [eax+%#x]" % BTN_EVT_CODE,                    # OnClick code pointer
        "cmp edx, %#x" % FACE_NEXT_CLICK,
        "jne Lnotnext",
        "mov [ebp+%#x], eax" % (LATCH + 4),
        "jmp Lchild",
        "Lnotnext:",
        "cmp edx, %#x" % FACE_PREV_CLICK,
        "jne Lchild",
        "mov [ebp+%#x], eax" % (LATCH + 8),
        "jmp Lchild",
        "Lnext:",
        "dec edi",
        "jnz Llvl",
        "Ldone:",
        "popfd", "popad",
        "mov al, byte ptr [ebx+0xC0]",                          # displaced
        "jmp %#x" % H4_RESUME,
    ])


def src_wheelscroll():
    s = [
        "push ebp", "mov ebp, esp", "sub esp, 0x18",            # -0x14 kind, -0x10 best dx,
        "push ebx", "push esi", "push edi",                     # -0xC count, -8 data, -4 index
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",             # ebx = load delta
        cnt("ebx", 4),
        "mov esi, [ebx+%#x]" % (LATCH + 0),
        "test esi, esi",
        "jnz Lhave",
        # ---- nothing scrollable hovered: leader-setup portrait cycling (up = previous face)
        cnt("ebx", 7),
        "mov ecx, [ebp+8]",
        "test ecx, ecx",
        "jle Lfacedown",
        "mov edi, [ebx+%#x]" % (LATCH + 8),
        "jmp Lfacego",
        "Lfacedown:",
        "mov edi, [ebx+%#x]" % (LATCH + 4),
        "Lfacego:",
        "test edi, edi",
        "jz Lfail",
        "cmp word ptr [edi+%#x], 0" % BTN_EVT_HIWD,             # OnClick assigned?
        "je Lfail",
        "mov edx, edi",                                         # Sender
        "mov eax, [edi+%#x]" % BTN_EVT_DATA,                    # Self
        "call dword ptr [edi+%#x]" % BTN_EVT_CODE,
        "jmp Lok",
        # ---- classify the hovered control by VMT: 0 listbox / 1 memo / 2 other
        "Lhave:",
        "mov eax, [esi]",
        "lea ecx, [ebx+%#x]" % VMT_LISTBOX,
        "cmp eax, ecx",
        "jne Lnotlb",
        "mov dword ptr [ebp-0x14], 0",
        "mov edi, [esi+%#x]" % LB_VSCROLL,
        "jmp Lgotkind",
        "Lnotlb:",
        "lea ecx, [ebx+%#x]" % VMT_MEMO,
        "cmp eax, ecx",
        "jne Lnotmemo",
        "mov dword ptr [ebp-0x14], 1",
        "mov edi, [esi+%#x]" % MEMO_VSCROLL,
        "jmp Lgotkind",
        "Lnotmemo:",
        "mov dword ptr [ebp-0x14], 2",
        "xor edi, edi",
        "Lgotkind:",
        "test edi, edi",
        "jnz Lhavesb",
        # ---- case 2: the governing sibling TAOWVScrollBar (owner's children, see U1)
        "mov eax, [esi+%#x]" % COMP_OWNER,
        "test eax, eax",
        "jz Lfallback",
        "mov eax, [eax+%#x]" % COMP_CHILDREN,
        "test eax, eax",
        "jz Lfallback",
        "mov ecx, [eax+8]",
        "mov [ebp-0xC], ecx",
        "mov eax, [eax+4]",
        "mov [ebp-8], eax",
        "mov dword ptr [ebp-4], 0",
        "mov dword ptr [ebp-0x10], 0x7FFFFFFF",
        "Lscan:",
        "mov ecx, [ebp-4]",
        "cmp ecx, [ebp-0xC]",
        "jge Lscandone",
        "mov eax, [ebp-8]",
        "mov eax, [eax+ecx*4]",
        "test eax, eax",
        "jz Lnext",
        "mov edx, [eax]",
        "lea ecx, [ebx+%#x]" % VMT_VSCROLLBAR,
        "cmp edx, ecx",
        "jne Lnext",
        "mov edx, [eax+%#x]" % CTRL_TOP,                        # bar.top
        "mov ecx, [esi+%#x]" % CTRL_TOP,
        "add ecx, [esi+%#x]" % CTRL_H,                          # list.bottom
        "cmp edx, ecx",
        "jge Lnext",                                            # bar starts below the list
        "add edx, [eax+%#x]" % CTRL_H,                          # bar.bottom
        "cmp edx, [esi+%#x]" % CTRL_TOP,
        "jle Lnext",                                            # bar ends above the list
        "mov edx, [eax+%#x]" % CTRL_LEFT,
        "sub edx, [esi+%#x]" % CTRL_LEFT,                       # dx = bar.left - list.left
        "js Lnext",                                             # left of the list: another column's
        "cmp edx, [ebp-0x10]",
        "jge Lnext",
        "mov [ebp-0x10], edx",
        "mov edi, eax",                                         # nearest so far
        "Lnext:",
        "inc dword ptr [ebp-4]",
        "jmp Lscan",
        "Lscandone:",
        "test edi, edi",
        "jz Lfallback",
        cnt("ebx", 8),
        # ---- cases 1 and 2: move the scrollbar, fire its OnChange, refresh the control
        "Lhavesb:",
        "mov edx, [edi+%#x]" % SB_FPOS,
        "mov ecx, [ebp+8]",
        "test ecx, ecx",
        "jle Ldown",
        "sub edx, %d" % LINES,                                  # wheel up
        "jmp Ldoit",
        "Ldown:",
        "add edx, %d" % LINES,                                  # wheel down
        "Ldoit:",
        "mov eax, edi",
        "call %#x" % F_SETFPOS,
        "cmp word ptr [edi+%#x], 0" % SB_EVT_HIWD,
        "je Lnoevt",
        cnt("ebx", 9),
        "mov edx, edi",
        "mov eax, [edi+%#x]" % SB_EVT_DATA,
        "call dword ptr [edi+%#x]" % SB_EVT_CODE,               # the form's OnChange
        "Lnoevt:",
        "cmp dword ptr [ebp-0x14], 1",
        "je Lupmemo",
        "jg Lok",                                               # kind 2: nothing to refresh
        "mov eax, esi",
        "call %#x" % F_LB_UPDATE,
        "jmp Lok",
        "Lupmemo:",
        "mov eax, esi",
        "call %#x" % F_MEMO_UPDATE,
        "jmp Lok",
        # ---- case 3: no scrollbar anywhere
        "Lfallback:",
        cnt("ebx", 6),
        "cmp dword ptr [ebp-0x14], 1",
    ]
    if MEMO_NEEDS_SCROLLBAR:
        s += ["je Linert"]                                      # D2: scrollbar-less memo is inert
    else:
        s += ["je Lfmemo"]
    s += [
        "jg Lfail",                                             # kind 2: cannot scroll it
        "mov edx, [esi+%#x]" % LB_LISTOFF,
        "jmp Lfcalc",
    ]
    if not MEMO_NEEDS_SCROLLBAR:
        s += ["Lfmemo:", "mov edx, [esi+%#x]" % MEMO_LISTOFF]
    s += [
        "Lfcalc:",
        "mov ecx, [ebp+8]",
        "test ecx, ecx",
        "jle Lfdown",
        "sub edx, %d" % LINES,
        "jmp Lfdo",
        "Lfdown:",
        "add edx, %d" % LINES,
        "Lfdo:",
        "mov eax, esi",
    ]
    if MEMO_NEEDS_SCROLLBAR:
        s += ["call %#x" % F_LB_SETLISTOFF, "jmp Lok"]
    else:
        s += [
            "cmp dword ptr [ebp-0x14], 1",
            "je Lfsetmemo",
            "call %#x" % F_LB_SETLISTOFF,
            "jmp Lok",
            "Lfsetmemo:",
            "call %#x" % F_MEMO_SETLISTOFF,                     # lower-clamped by build_memo_clamp
        ]
    s += [
        "Lok:",
        cnt("ebx", 5),
        "mov eax, 1",
        "jmp Lexit",
    ]
    if MEMO_NEEDS_SCROLLBAR:
        s += ["Linert:", cnt("ebx", 11)]
    s += [
        "Lfail:",
        "xor eax, eax",
        "Lexit:",
        "pop edi", "pop esi", "pop ebx",
        "mov esp, ebp", "pop ebp",
        "ret 4",
    ]
    return "\n".join(s)


def header_bytes():
    return struct.pack("<8I", MAGIC, VERSION, LATCH - IMAGE_BASE, LATCH_N, WS_VA - IMAGE_BASE, 0, 0, 0)


def build_caves():
    """name -> (va, budget, blob) for the requested build variant."""
    caves = {
        "CLR": (CLR_VA, CLR_BUDGET, asm(src_clr(), CLR_VA)),
        "SET": (SET_VA, SET_BUDGET, asm(src_set(H2_RESUME, 1), SET_VA)),
        "SET2": (SET2_VA, SET2_BUDGET, asm(src_set(H3_RESUME, 2), SET2_VA)),
        "SET3": (SET3_VA, SET3_BUDGET, asm(src_set3(), SET3_VA)),
        "WheelScroll": (WS_VA, WS_BUDGET, asm(src_wheelscroll(), WS_VA)),
    }
    # structural assertions: every hook cave ends with its displaced bytes + jmp resume
    for name, orig, resume in (("CLR", H1_ORIG, H1_RESUME), ("SET", H2_ORIG, H2_RESUME),
                               ("SET2", H3_ORIG, H3_RESUME), ("SET3", H4_ORIG, H4_RESUME)):
        va, _, blob = caves[name]
        tail = orig + b"\xE9" + struct.pack("<i", resume - (va + len(blob)))
        assert blob.endswith(tail), "%s does not end with displaced bytes + jmp resume" % name
    ws = caves["WheelScroll"][2]
    assert ws.endswith(b"\xC2\x04\x00"), "WheelScroll must end with ret 4"
    assert ws[0] == 0x55, "WheelScroll prologue must start with push ebp"
    return caves


HOOKS = [
    ("H1 CLR  TAOWWinManager.CheckMouseMove", H1_SITE, H1_ORIG, "CLR"),
    ("H2 SET  TAOWListBox.CheckMouseMove+7D", H2_SITE, H2_ORIG, "SET"),
    ("H3 SET2 TAOWMemo.CheckMouseMove+9A", H3_SITE, H3_ORIG, "SET2"),
    ("H4 SET3 TAOWImage.CheckMouseMove+6A", H4_SITE, H4_ORIG, "SET3"),
]


def site_state(mod, site, orig, cave_va):
    cur = mod.read(site, len(orig))
    if cur == orig:
        return "vanilla", cur
    if cur == hook_bytes(site, cave_va, len(orig)):
        return "applied", cur
    return "foreign", cur


def zone_desc(mod, va, budget, blobs):
    """blobs: {variant: blob}. -> 'zero' | 'ours (<variant>)' | 'nonzero'"""
    z = mod.read(va, budget)
    if set(z) <= {0}:
        return "zero"
    for variant, blob in blobs.items():
        if z == pad(blob, budget, variant):
            return "ours (%s)" % variant
    return "nonzero"


def vcl_half_present():
    try:
        v = Module(VCL, VCL_IMAGE_BASE)
    except Exception as e:
        return None, "vcl30.dpl unreadable: %s" % e
    cur = v.read(VCL_H5_SITE, 5)
    if cur == VCL_H5_ORIG:
        return False, "vanilla"
    if cur == b"\xE8" + struct.pack("<i", VCL_PUMP_VA - (VCL_H5_SITE + 5)):
        return True, "applied"
    return None, "foreign (%s)" % cur.hex(" ")


def ext_present(mod):
    slots = mod.read(HDR_VA + 0x14, 12)
    zone = mod.read(EXT_LO, EXT_HI - EXT_LO)
    return not (set(slots) <= {0} and set(zone) <= {0})


def main(argv):
    apply_, undo, show = "--apply" in argv, "--undo" in argv, ("--dis" in argv or "--show" in argv)
    for a in argv:
        if a not in ("--apply", "--undo", "--dis", "--show", "--diag"):
            sys.exit("unknown flag %s" % a)

    global DIAG
    want_diag = DIAG
    variants = {}
    for DIAG in (False, True):
        variants["diag" if DIAG else "plain"] = build_caves()
    DIAG = want_diag
    variant = "diag" if DIAG else "plain"
    caves = variants[variant]
    hdr = header_bytes()

    # ---- static safety: budgets, PIC, keystone trap, no absolute path, no reloc in our ranges
    problems = []
    for name, (va, budget, blob) in caves.items():
        pad(blob, budget, name)
        problems += pic_lint(blob, va, name)
        problems += check_push_imm8(blob, va, name)
        if re.search(rb"[A-Za-z]:\\", blob):
            problems.append("%s contains a drive-letter path" % name)
    if problems:
        print("\n".join(problems))
        sys.exit("ABORT: static checks failed")

    if show:
        print("build variant: %s   LINES=%d   MEMO_NEEDS_SCROLLBAR=%s" % (variant, LINES,
                                                                          MEMO_NEEDS_SCROLLBAR))
        print("  header @ %08X: %s" % (HDR_VA, hdr.hex(" ")))
        for name, (va, budget, blob) in caves.items():
            print("\n".join(dis_lines(blob, va, name)))
        return 0

    mod = Module(INT, IMAGE_BASE)
    ranges = [(s, s + len(o)) for _, s, o, _ in HOOKS] + [(OWN_CODE_LO, OWN_CODE_HI),
                                                          (OWN_DATA_LO, OWN_DATA_HI)]
    hits = mod.reloc_hits(ranges)
    if hits:
        sys.exit("ABORT: .reloc entries inside our ranges at file offsets %s" % [hex(h) for h in hits])
    mod.off(OWN_DATA_LO, OWN_DATA_HI - OWN_DATA_LO, write=True)     # raw-backed AND writable

    # ---- current state
    print("build_wheel_aowint  (%s build; LINES=%d, MEMO_NEEDS_SCROLLBAR=%s)"
          % (variant, LINES, MEMO_NEEDS_SCROLLBAR))
    print("  file: %s" % INT)
    states = {}
    for label, site, orig, cname in HOOKS:
        st, cur = site_state(mod, site, orig, caves[cname][0])
        states[cname] = st
        print("  %-42s %08X  %-8s %s" % (label, site, st, cur.hex(" ")))
    if "foreign" in states.values():
        sys.exit("ABORT: a hook site is neither vanilla nor ours -- someone else owns it.")
    hdr_cur = mod.read(HDR_VA, HDR_BUDGET)
    hdr_state = ("zero" if set(hdr_cur) <= {0} else
                 "ours" if hdr_cur[:0x14] == hdr[:0x14] and set(hdr_cur[0x20:]) <= {0} else "nonzero")
    print("  %-42s %08X  %-8s %s" % ("contract header", HDR_VA, hdr_state, hdr_cur[:0x20].hex(" ")))
    for name, (va, budget, blob) in caves.items():
        zd = zone_desc(mod, va, budget, {k: v[name][2] for k, v in variants.items()})
        print("  %-42s %08X  %s  (%d B of %#x)" % ("cave " + name, va, zd, len(blob), budget))
    data_zero = set(mod.read(OWN_DATA_LO, OWN_DATA_HI - OWN_DATA_LO)) <= {0}
    print("  %-42s %08X  %s" % ("latch block + counters", OWN_DATA_LO, "zero" if data_zero else "NONZERO"))
    ext = ext_present(mod)
    print("  %-42s %08X  %s" % ("build_wheel_ext.py zone / header slots 1-3", EXT_LO,
                                "present" if ext else "absent"))

    all_applied = all(s == "applied" for s in states.values())
    all_vanilla = all(s == "vanilla" for s in states.values())
    if not (all_applied or all_vanilla):
        sys.exit("ABORT: partial install (some sites ours, some vanilla). Fix by hand.")
    if all_vanilla and hdr_state != "zero":
        sys.exit("ABORT: sites vanilla but the header zone is not zero -- someone else owns it.")
    if all_applied and hdr_state != "ours":
        sys.exit("ABORT: sites ours but the header is not ours (%s)." % hdr_cur[:0x20].hex(" "))

    vcl_ok, vcl_desc = vcl_half_present()
    aow_half = all_applied and hdr_state == "ours"
    if aow_half and vcl_ok:
        chain = "complete"
    elif aow_half and vcl_ok is False:
        chain = "aowInt half only, inert"
    elif (not aow_half) and vcl_ok:
        chain = "vcl30 half only, inert"
    elif vcl_ok is None:
        chain = "vcl30 site %s -- ABORT" % vcl_desc
    else:
        chain = "absent"
    print("  chain: %s   (vcl30 H5 %08X: %s)" % (chain, VCL_H5_SITE, vcl_desc))
    if vcl_ok is None:
        return 2

    # ---- undo
    if undo:
        if all_vanilla:
            print("\nnothing to undo: all sites vanilla")
            return 0
        if ext:
            sys.exit("\nREFUSED: build_wheel_ext.py is present (header slots 1-3 or its cave zone are "
                     "non-zero). Run build_wheel_ext.py --undo first.")
        if vcl_ok:
            print("\nNOTE: the vcl30 half is still applied; it is inert without this header, but the "
                  "undo order in the spec is vclpump first.")
        for label, site, orig, cname in HOOKS:
            assert mod.read(site, len(orig)) == hook_bytes(site, caves[cname][0], len(orig)), label
            mod.write(site, orig)
        mod.write(OWN_CODE_LO, bytes(OWN_CODE_HI - OWN_CODE_LO))
        mod.write(OWN_DATA_LO, bytes(OWN_DATA_HI - OWN_DATA_LO))
        try:
            open(INT, "wb").write(bytes(mod.d))
        except PermissionError:
            sys.exit("ABORT: " + KILL_HINT)
        chk = Module(INT, IMAGE_BASE)
        for label, site, orig, cname in HOOKS:
            assert chk.read(site, len(orig)) == orig, "read-back failed at " + label
        assert set(chk.read(OWN_CODE_LO, OWN_CODE_HI - OWN_CODE_LO)) <= {0}
        print("\nundone: H1-H4 restored, %08X..%08X and %08X..%08X zeroed; no backup touched."
              % (OWN_CODE_LO, OWN_CODE_HI, OWN_DATA_LO, OWN_DATA_HI))
        return 0

    # ---- plan the apply
    plan = []            # (va, new bytes, desc)
    if all_vanilla:
        for name, (va, budget, blob) in caves.items():
            z = mod.read(va, budget)
            if set(z) > {0}:
                sys.exit("ABORT: cave zone %s @%08X is not zero -- someone else owns it." % (name, va))
        if not data_zero:
            sys.exit("ABORT: latch/counter zone is not zero -- someone else owns it.")
        plan.append((HDR_VA, hdr, "contract header"))
        for name, (va, budget, blob) in caves.items():
            plan.append((va, pad(blob, budget, name), "cave %s (%d B + zero pad)" % (name, len(blob))))
        for label, site, orig, cname in HOOKS:
            plan.append((site, hook_bytes(site, caves[cname][0], len(orig)), label))
        fresh = True
    else:
        fresh = False
        if hdr_cur[:0x14] != hdr[:0x14]:
            plan.append((HDR_VA, hdr[:0x14], "contract header (first 5 dwords; slots 1-3 kept)"))
        for name, (va, budget, blob) in caves.items():
            if mod.read(va, budget) != pad(blob, budget, name):
                plan.append((va, pad(blob, budget, name), "cave %s (rewrite in place)" % name))

    if not plan:
        print("\nalready applied (%s build) -- nothing to write." % variant)
        return 0
    print("\n%s -- %d region(s):" % ("fresh apply" if fresh else "rewrite in place", len(plan)))
    for va, new, desc in plan:
        print("   %08X  %4d B  %s" % (va, len(new), desc))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write.  (--dis shows the caves)")
        return 0

    # ---- backup: only from a file PROVED to be unpatched by this feature (fresh apply)
    if fresh and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(INT, BACKUP)
        print("backup written: %s" % os.path.basename(BACKUP))
    elif fresh:
        print("backup already exists, left as-is: %s" % os.path.basename(BACKUP))
    else:
        print("re-tune over an existing install: no backup taken (the current file is our own output)")

    # ---- verify-before-write, then write
    for va, new, desc in plan:
        cur = mod.read(va, len(new))
        if fresh:
            if va == HDR_VA or va in (c[0] for c in caves.values()):
                assert set(cur) <= {0}, "verify-before-write: zone at %08X changed" % va
            else:
                orig = next(o for _, s, o, _ in HOOKS if s == va)
                assert cur == orig, "verify-before-write: site %08X changed" % va
        mod.write(va, new)
    try:
        open(INT, "wb").write(bytes(mod.d))
    except PermissionError:
        sys.exit("ABORT: " + KILL_HINT)
    chk = Module(INT, IMAGE_BASE)
    for va, new, desc in plan:
        assert chk.read(va, len(new)) == new, "read-back mismatch at %08X" % va
    print("written and read back: %d region(s)." % len(plan))
    print("\napplied, UNTESTED -- inert until build_wheel_vclpump.py is applied; the in-game checklist "
          "is in the spec's IN-GAME section.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
