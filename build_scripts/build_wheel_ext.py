#!/usr/bin/env python3
r"""
build_wheel_ext.py -- mouse-wheel extensions (C): power-distribution slider + unit-window cycling.

Spec: Modding Resources/Zig notes/Mouse_Wheel_Scrolling.md, deliverable (C); decisions D3/D4.
Reference (NEVER run it): Modding Resources/Inioch/share4/patch scripts/build_wheel_power_slider.py.
aowInt.dpl ONLY -- vcl30.dpl is untouched: the LL proc ORs the whole latch block and the pump
iterates the contract header's helper slots, so an extension is two latches + two header slots.

REQUIRES build_wheel_aowint.py applied (asserts its contract header and H1). Adds:

  * H7 SLD  TAOWHScrollBar.CheckMouseMove entry 0x5981FA5C (steals the 5-byte prologue
        55 8B EC 51 53; eax = the scrollbar): if this bar's OnChange code pointer [sb+0x6C] is
        TPowerDlg.PowerSliderChange 0x42BF40 (AoW.exe, fixed base), latch[3] = the bar. A control
        receives CheckMouseMove only while its window is open and input-eligible, so open/close,
        modality and z-order come from the game's own dispatch. (TPowerDlg itself is a small
        controller object, not the window the manager dispatches to -- the bar is the only thing
        that identifies the dialog.)
  * H8 BTN  TAOWButton.CheckMouseMove entry 0x59811808 (same steal; eax = button, ecx = sweep X,
        [esp+4] = sweep Y): latch[4]/[5] when OnClick [btn+0x138] is TUnitWindow.PNextClick
        0x40AC9C / PPrevClick 0x40ABF0. When the second of the pair latches in the same sweep (the
        CLR hook zeroes all latches at sweep start) the preview zone is built from the two buttons'
        rects -- parent.left/top from [btn+0x10C] exactly as TAOWControl's own hit-test does --
        widened UNIT_GAP_SIDE left/right, UNIT_GAP_UP above (over the unit graphic), UNIT_GAP_DOWN
        below, and latch[6] = 1 iff the sweep cursor is inside it.
  * WheelPower(delta) 0x59824540 -> header slot 1: while latch[3] is set and nothing is hovered
        (latch[0] == 0): SetFPos(bar, FPos +/- STEP) and fire the bar's OnChange, exactly like
        dragging (PowerSliderChange recalculates the mana/research labels). Wheel up = +STEP toward
        research. eax = 1 handled.
  * WheelUnit(delta) 0x598245C0 -> header slot 2: while latch[6] is set and nothing is hovered:
        wheel up fires PPrev.OnClick (previous unit), wheel down PNext.OnClick. eax = 1 handled.

U3 (settled 2026-09-02 from the live AoW.exe DFM, after build_unitwin_ability.py's rebuild):
TUnitWindow still has `PNext : TAOWButton` (L600 T176), `PPrev : TAOWButton` (L480 T176) and
`T2Memo : TAOWMemo`; handler addresses verified from the published method table. Geometry is read
at runtime, so the zone follows whatever the buttons' rects are.

Caves (the 1 KB zone 0x59824400..0x59824800 reserved by the foundation script):
    0x59824400 SLD 0x40 | 0x59824440 BTN 0x100 | 0x59824540 WheelPower 0x80 | 0x598245C0 WheelUnit 0x80
Header slots written: 0x59824014 = RVA 0x24540, 0x59824018 = RVA 0x245C0. Latches [3..6] live at
0x5983E04C..0x5983E05B (zero on disk; cleared every sweep by CLR). --diag counters share the
foundation's block: 0x5983E090.. (+0x30..+0x3C).

Usage
  python build_scripts/build_wheel_ext.py            dry run + state
  python build_scripts/build_wheel_ext.py --apply    patch (backup aowInt.dpl.pre-wheelext, once)
  python build_scripts/build_wheel_ext.py --undo     surgical: restore H7/H8, zero the zone, zero
                                                     header slots 1-2 and latches 3-6
  python build_scripts/build_wheel_ext.py --dis      disassemble every cave (read it!)
Undo this BEFORE build_wheel_aowint.py --undo (which refuses while this is present).
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
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(INT) + ".pre-wheelext")

DIAG = "--diag" in sys.argv

# ---- tunables (decision D3) ----
STEP = 5                       # power-slider FPos per notch (range 0..100)
UNIT_GAP_UP = 110              # px above the arrow pair counted as preview zone
UNIT_GAP_DOWN = 8
UNIT_GAP_SIDE = 8

# ---- aowInt.dpl map (must agree with build_wheel_aowint.py) ----
IMAGE_BASE = 0x59800000
MOD_LO, MOD_HI = 0x59800000, 0x59852000
HDR_VA, MAGIC, MAJOR = 0x59824000, 0x48575A41, 1
SLOT1_VA, SLOT2_VA = HDR_VA + 0x14, HDR_VA + 0x18
LATCH = 0x5983E040
L_HOVER, L_PSLIDER, L_UNEXT, L_UPREV, L_UARMED = LATCH, LATCH + 0xC, LATCH + 0x10, LATCH + 0x14, LATCH + 0x18
CNT = 0x5983E060

SLD_VA, SLD_BUDGET = 0x59824400, 0x40
BTN_VA, BTN_BUDGET = 0x59824440, 0x100
WP_VA, WP_BUDGET = 0x59824540, 0x80
WU_VA, WU_BUDGET = 0x598245C0, 0x80
ZONE_LO, ZONE_HI = 0x59824400, 0x59824800

H7_SITE, H7_ORIG, H7_RESUME = 0x5981FA5C, bytes.fromhex("558bec5153"), 0x5981FA61
H8_SITE, H8_ORIG, H8_RESUME = 0x59811808, bytes.fromhex("558bec5153"), 0x5981180D
FOUND_H1_SITE, FOUND_H1_ORIG, FOUND_CLR_VA = 0x59807094, bytes.fromhex("558bec83c4f4"), 0x59824040

F_SETFPOS = 0x5980CA28
PWRSLIDERCHANGE, PNEXT_CLICK, PPREV_CLICK = 0x42BF40, 0x40AC9C, 0x40ABF0     # AoW.exe, COMPARED only
SB_FPOS, SB_EVT_CODE, SB_EVT_HIWD, SB_EVT_DATA = 0x148, 0x6C, 0x6E, 0x70
BTN_EVT_CODE, BTN_EVT_HIWD, BTN_EVT_DATA = 0x138, 0x13A, 0x13C
CTRL_PARENT, CTRL_LEFT, CTRL_TOP, CTRL_W, CTRL_H = 0x10C, 0x84, 0x88, 0x7C, 0x80

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
        assert self.image_base == image_base
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


def check_push_imm8(blob, base, title):
    bad = []
    for i in cs.disasm(blob, base):
        if i.mnemonic == "push" and i.bytes[0] == 0x6A and i.bytes[1] >= 0x80:
            bad.append("%s: %08X push imm8 sign-extended: %s" % (title, i.address, i.op_str))
    return bad


def pad(blob, budget, name):
    assert len(blob) <= budget, "%s is %d B, over its %d B budget" % (name, len(blob), budget)
    return blob + bytes(budget - len(blob))


def displaced(orig):
    return ".byte " + ", ".join("%#04x" % b for b in orig)


def cnt(reg, idx):
    return "inc dword ptr [%s+%#x]" % (reg, CNT + 4 * idx) if DIAG else ""


# ============================================================ the caves
def src_sld():
    return "\n".join([
        "push ebx", "pushfd",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",
        "cmp dword ptr [eax+%#x], %#x" % (SB_EVT_CODE, PWRSLIDERCHANGE),
        "jne Lskip",
        "mov [ebx+%#x], eax" % L_PSLIDER,
        "Lskip:",
        "popfd", "pop ebx",
        displaced(H7_ORIG),
        "jmp %#x" % H7_RESUME,
    ])


def src_btn():
    return "\n".join([
        "push ebx", "push esi", "push edi",                          # Y now at [esp+0x10]
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",
        "cmp dword ptr [eax+%#x], %#x" % (BTN_EVT_CODE, PNEXT_CLICK),
        "jne Lnotnext",
        "mov [ebx+%#x], eax" % L_UNEXT,
        "cmp dword ptr [ebx+%#x], 0" % L_UPREV,
        "jne Leval",
        "jmp Lout",
        "Lnotnext:",
        "cmp dword ptr [eax+%#x], %#x" % (BTN_EVT_CODE, PPREV_CLICK),
        "jne Lout",
        "mov [ebx+%#x], eax" % L_UPREV,
        "cmp dword ptr [ebx+%#x], 0" % L_UNEXT,
        "je Lout",
        "Leval:",                                                    # both arrows seen this sweep
        "push eax", "push ecx", "push edx",                          # Y now at [esp+0x1C]
        "mov esi, [ebx+%#x]" % L_UPREV,                              # PPrev (left)
        "mov edi, [ebx+%#x]" % L_UNEXT,                              # PNext (right)
        "mov edx, [esi+%#x]" % CTRL_PARENT,                          # coordinate parent (hit-test's)
        # ---- X: parent.left + prev.left - GAP <= X <= parent.left + next.left + next.w + GAP
        "mov eax, [edx+%#x]" % CTRL_LEFT,
        "add eax, [esi+%#x]" % CTRL_LEFT,
        "sub eax, %d" % UNIT_GAP_SIDE,
        "cmp ecx, eax",
        "jl Lmiss",
        "mov eax, [edx+%#x]" % CTRL_LEFT,
        "add eax, [edi+%#x]" % CTRL_LEFT,
        "add eax, [edi+%#x]" % CTRL_W,
        "add eax, %d" % UNIT_GAP_SIDE,
        "cmp ecx, eax",
        "jg Lmiss",
        # ---- Y: parent.top + prev.top - GAP_UP <= Y <= parent.top + prev.top + prev.h + GAP_DOWN
        "mov ecx, [esp+0x1C]",
        "mov eax, [edx+%#x]" % CTRL_TOP,
        "add eax, [esi+%#x]" % CTRL_TOP,
        "sub eax, %d" % UNIT_GAP_UP,
        "cmp ecx, eax",
        "jl Lmiss",
        "mov eax, [edx+%#x]" % CTRL_TOP,
        "add eax, [esi+%#x]" % CTRL_TOP,
        "add eax, [esi+%#x]" % CTRL_H,
        "add eax, %d" % UNIT_GAP_DOWN,
        "cmp ecx, eax",
        "jg Lmiss",
        "mov dword ptr [ebx+%#x], 1" % L_UARMED,
        "jmp Levald",
        "Lmiss:",
        "mov dword ptr [ebx+%#x], 0" % L_UARMED,
        "Levald:",
        "pop edx", "pop ecx", "pop eax",
        "Lout:",
        "pop edi", "pop esi", "pop ebx",
        displaced(H8_ORIG),
        "jmp %#x" % H8_RESUME,
    ])


def src_wheelpower():
    return "\n".join([
        "push ebp", "mov ebp, esp",
        "push ebx", "push esi", "push edi",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",
        cnt("ebx", 12),
        "mov edi, [ebx+%#x]" % L_PSLIDER,
        "test edi, edi",
        "jz Lfail",
        "cmp dword ptr [ebx+%#x], 0" % L_HOVER,                      # hover targets keep priority
        "jne Lfail",
        "mov edx, [edi+%#x]" % SB_FPOS,
        "mov ecx, [ebp+8]",
        "test ecx, ecx",
        "jle Ldown",
        "add edx, %d" % STEP,                                        # wheel up: toward research
        "jmp Ldoit",
        "Ldown:",
        "sub edx, %d" % STEP,                                        # wheel down: toward mana
        "Ldoit:",
        "mov eax, edi",
        "call %#x" % F_SETFPOS,                                      # clamps to the bar's range
        "cmp word ptr [edi+%#x], 0" % SB_EVT_HIWD,
        "je Lok",
        "mov edx, edi",
        "mov eax, [edi+%#x]" % SB_EVT_DATA,
        "call dword ptr [edi+%#x]" % SB_EVT_CODE,                    # PowerSliderChange
        "Lok:",
        cnt("ebx", 13),
        "mov eax, 1",
        "jmp Lexit",
        "Lfail:",
        "xor eax, eax",
        "Lexit:",
        "pop edi", "pop esi", "pop ebx", "pop ebp",
        "ret 4",
    ])


def src_wheelunit():
    return "\n".join([
        "push ebp", "mov ebp, esp",
        "push ebx", "push esi",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",
        cnt("ebx", 14),
        "cmp dword ptr [ebx+%#x], 0" % L_UARMED,
        "je Lfail",
        "cmp dword ptr [ebx+%#x], 0" % L_HOVER,
        "jne Lfail",
        "mov ecx, [ebp+8]",
        "test ecx, ecx",
        "jle Ldown",
        "mov esi, [ebx+%#x]" % L_UPREV,                              # wheel up: previous unit
        "jmp Lgo",
        "Ldown:",
        "mov esi, [ebx+%#x]" % L_UNEXT,                              # wheel down: next unit
        "Lgo:",
        "test esi, esi",
        "jz Lfail",
        "cmp word ptr [esi+%#x], 0" % BTN_EVT_HIWD,
        "je Lfail",
        "mov edx, esi",
        "mov eax, [esi+%#x]" % BTN_EVT_DATA,
        "call dword ptr [esi+%#x]" % BTN_EVT_CODE,
        cnt("ebx", 15),
        "mov eax, 1",
        "jmp Lexit",
        "Lfail:",
        "xor eax, eax",
        "Lexit:",
        "pop esi", "pop ebx", "pop ebp",
        "ret 4",
    ])


def build_caves():
    caves = {
        "SLD": (SLD_VA, SLD_BUDGET, asm(src_sld(), SLD_VA)),
        "BTN": (BTN_VA, BTN_BUDGET, asm(src_btn(), BTN_VA)),
        "WheelPower": (WP_VA, WP_BUDGET, asm(src_wheelpower(), WP_VA)),
        "WheelUnit": (WU_VA, WU_BUDGET, asm(src_wheelunit(), WU_VA)),
    }
    for name, orig, resume in (("SLD", H7_ORIG, H7_RESUME), ("BTN", H8_ORIG, H8_RESUME)):
        va, _, blob = caves[name]
        tail = orig + b"\xE9" + struct.pack("<i", resume - (va + len(blob)))
        assert blob.endswith(tail), "%s does not end with displaced bytes + jmp resume" % name
    for name in ("WheelPower", "WheelUnit"):
        blob = caves[name][2]
        assert blob[0] == 0x55 and blob.endswith(b"\xC2\x04\x00"), name
    return caves


HOOKS = [("H7 SLD  TAOWHScrollBar.CheckMouseMove", H7_SITE, H7_ORIG, "SLD"),
         ("H8 BTN  TAOWButton.CheckMouseMove", H8_SITE, H8_ORIG, "BTN")]


def hook_bytes(site, cave_va):
    return b"\xE9" + struct.pack("<i", cave_va - (site + 5))


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
    slots = struct.pack("<II", WP_VA - IMAGE_BASE, WU_VA - IMAGE_BASE)

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
        print("build variant: %s   STEP=%d  UNIT_GAP up/down/side=%d/%d/%d" % (
            variant, STEP, UNIT_GAP_UP, UNIT_GAP_DOWN, UNIT_GAP_SIDE))
        print("  header slots 1-2 @ %08X: %s" % (SLOT1_VA, slots.hex(" ")))
        for name, (va, budget, blob) in caves.items():
            print("\n".join(dis_lines(blob, va, name)))
        return 0

    mod = Module(INT, IMAGE_BASE)
    ranges = [(s, s + len(o)) for _, s, o, _ in HOOKS] + [(ZONE_LO, ZONE_HI), (SLOT1_VA, SLOT2_VA + 4),
                                                          (L_PSLIDER, L_UARMED + 4)]
    hits = mod.reloc_hits(ranges)
    if hits:
        sys.exit("ABORT: .reloc entries inside our ranges at file offsets %s" % [hex(h) for h in hits])

    print("build_wheel_ext  (%s build; STEP=%d, gaps %d/%d/%d)" % (variant, STEP, UNIT_GAP_UP,
                                                                    UNIT_GAP_DOWN, UNIT_GAP_SIDE))
    print("  file: %s" % INT)
    hdr = mod.read(HDR_VA, 0x20)
    magic, ver = struct.unpack_from("<II", hdr)
    h1 = mod.read(FOUND_H1_SITE, 6)
    found = (magic == MAGIC and (ver >> 16) == MAJOR and
             h1 == b"\xE9" + struct.pack("<i", FOUND_CLR_VA - (FOUND_H1_SITE + 5)) + b"\x90")
    print("  %-42s %08X  %s" % ("foundation (build_wheel_aowint.py)", HDR_VA,
                                "present (header v%d.%d)" % (ver >> 16, ver & 0xFFFF) if found else "ABSENT"))
    states = {}
    for label, site, orig, cname in HOOKS:
        cur = mod.read(site, len(orig))
        st = "vanilla" if cur == orig else "applied" if cur == hook_bytes(site, caves[cname][0]) else "foreign"
        states[cname] = st
        print("  %-42s %08X  %-8s %s" % (label, site, st, cur.hex(" ")))
    if "foreign" in states.values():
        sys.exit("ABORT: a hook site is neither vanilla nor ours -- someone else owns it.")
    cur_slots = mod.read(SLOT1_VA, 8)
    slot_state = "zero" if set(cur_slots) <= {0} else "ours" if cur_slots == slots else "nonzero"
    print("  %-42s %08X  %-8s %s" % ("header slots 1-2", SLOT1_VA, slot_state, cur_slots.hex(" ")))
    for name, (va, budget, blob) in caves.items():
        z = mod.read(va, budget)
        zd = "zero" if set(z) <= {0} else next(
            ("ours (%s)" % k for k, v in variants.items() if z == pad(v[name][2], budget, name)), "nonzero")
        print("  %-42s %08X  %s  (%d B of %#x)" % ("cave " + name, va, zd, len(blob), budget))
    rest = mod.read(WU_VA + WU_BUDGET, ZONE_HI - (WU_VA + WU_BUDGET))
    print("  %-42s %08X  %s" % ("rest of the (C) zone", WU_VA + WU_BUDGET, "zero" if set(rest) <= {0} else "NONZERO"))
    latches = mod.read(L_PSLIDER, 16)
    print("  %-42s %08X  %s" % ("latches 3-6 (on disk)", L_PSLIDER, "zero" if set(latches) <= {0} else "NONZERO"))

    all_applied = all(s == "applied" for s in states.values())
    all_vanilla = all(s == "vanilla" for s in states.values())
    if not (all_applied or all_vanilla):
        sys.exit("ABORT: partial install (one site ours, one vanilla). Fix by hand.")
    if all_vanilla and slot_state != "zero":
        sys.exit("ABORT: sites vanilla but header slots 1-2 are not zero -- someone else owns them.")
    if all_applied and slot_state != "ours":
        sys.exit("ABORT: sites ours but header slots 1-2 are not ours.")

    if undo:
        if all_vanilla:
            print("\nnothing to undo: H7/H8 vanilla")
            return 0
        for label, site, orig, cname in HOOKS:
            assert mod.read(site, len(orig)) == hook_bytes(site, caves[cname][0]), label
            mod.write(site, orig)
        mod.write(ZONE_LO, bytes(ZONE_HI - ZONE_LO))
        mod.write(SLOT1_VA, bytes(8))
        mod.write(L_PSLIDER, bytes(16))
        try:
            open(INT, "wb").write(bytes(mod.d))
        except PermissionError:
            sys.exit("ABORT: " + KILL_HINT)
        chk = Module(INT, IMAGE_BASE)
        for label, site, orig, cname in HOOKS:
            assert chk.read(site, len(orig)) == orig, label
        assert set(chk.read(ZONE_LO, ZONE_HI - ZONE_LO)) <= {0} and set(chk.read(SLOT1_VA, 8)) <= {0}
        print("\nundone: H7/H8 restored, %08X..%08X, header slots 1-2 and latches 3-6 zeroed; no backup touched."
              % (ZONE_LO, ZONE_HI))
        return 0

    if not found:
        sys.exit("\nABORT: the foundation (build_wheel_aowint.py) is not applied -- apply it first.")

    plan = []
    fresh = all_vanilla
    if fresh:
        if set(mod.read(ZONE_LO, ZONE_HI - ZONE_LO)) > {0}:
            sys.exit("ABORT: the (C) zone %08X..%08X is not zero -- someone else owns it." % (ZONE_LO, ZONE_HI))
        if set(latches) > {0}:
            sys.exit("ABORT: latches 3-6 are not zero on disk.")
        for name, (va, budget, blob) in caves.items():
            plan.append((va, pad(blob, budget, name), "cave %s (%d B + zero pad)" % (name, len(blob))))
        plan.append((SLOT1_VA, slots, "header slots 1-2 -> WheelPower / WheelUnit"))
        for label, site, orig, cname in HOOKS:
            plan.append((site, hook_bytes(site, caves[cname][0]), label))
    else:
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

    if fresh and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(INT, BACKUP)
        print("backup written: %s" % os.path.basename(BACKUP))
    elif fresh:
        print("backup already exists, left as-is: %s" % os.path.basename(BACKUP))
    else:
        print("re-tune over an existing install: no backup taken")

    for va, new, desc in plan:
        cur = mod.read(va, len(new))
        if fresh:
            if va in (H7_SITE, H8_SITE):
                assert cur == H7_ORIG, "verify-before-write: site %08X changed" % va
            else:
                assert set(cur) <= {0}, "verify-before-write: zone at %08X changed" % va
        mod.write(va, new)
    try:
        open(INT, "wb").write(bytes(mod.d))
    except PermissionError:
        sys.exit("ABORT: " + KILL_HINT)
    chk = Module(INT, IMAGE_BASE)
    for va, new, desc in plan:
        assert chk.read(va, len(new)) == new, "read-back mismatch at %08X" % va
    print("written and read back: %d region(s)." % len(plan))
    print("\napplied, UNTESTED -- needs the user's in-game test: power-distribution slider moves %d per"
          " notch with the labels updating; unit-window preview zone cycles units (up = previous)." % STEP)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
