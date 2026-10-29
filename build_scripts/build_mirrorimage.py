#!/usr/bin/env python
r"""
build_mirrorimage.py -- Mirror Image (ability 0xC6): a multi-level ability, levels I..XX, 4 skill
points a level.  The holder starts every battle with one image per level.  Every strike and every
shot aimed at it misses and removes one image instead, until none are left; damage over time,
spells and touch abilities are not attacks and get through.  Manual combat draws the images left
as displaced half-transparent copies of the unit.  AoWEPACK.dpl + AoWTCPCK.dpl.  Owner's design
2026-10-21 ("All incoming attacks miss and delete an image"; "resets at the end of a battle").

STATE  combatunit_slot.py's dword, byte B_MIRROR = images used this battle (tactical [unit+0x68],
       auto-resolve [unit+0x64]).  Combat objects are built zero-filled for every battle, so the
       images come back with no code.  Byte B_MIRROR_DRAW [unit+0x6A] (tactical) is set only while
       the copies are being drawn.

THE MISS (AoWEPACK, both combat systems)
    Every attack's damage roll is the defender's ExecuteDamageRole (combat VMT +0x110), called from
    TDamageCA.Generate, or ExecuteDamageRoleEx (+0x114) from GenerateEx.  Both call sites:
        G   0x55729C4E  `call [edi+0x110]` (6 B) -> call cave_role + nop
        GX  0x55729CCA  `call [edi+0x114]` (6 B) -> call cave_roleex + nop
    cave_absorb (EAX = the CA in Generate's EBX, EDX = the defender): the CA is a TStrikeCA (every
    melee strike: first strikes, counters, Round Attack) or a TRangedAttackCA (every shot: missiles,
    bolts, breath, Extra Shots); the defender is a TCombatUnit with Mirror Image level L and
    used < L -> used + 1 and the roll returns 0 damage (`ret 4` / `ret 8` as the callee would).
    Zero damage skips the effect roll too (Generate stores no effects), so a poison or fire strike
    does nothing.  TTurnUndeadCA, TSelfDestructCA and TCombatSpellCA reach the same calls and pass.
    The epilogue hooks of the combat log (0x55729C8C / 0x55729D08) and the Shield / invisibility
    caves that enter Generate at 0x55729C46 all still run; the log shows the miss as 0 damage.

THE IMAGES (AoWTCPCK, manual combat)
    S   0x00412DB0  TTacticalCombatUnitHS VMT +0xA8 (Show, 0x00421EE0) -> cave_show.  For a live
                    unit with N = L - used > 0 images (at most 20): mark B_MIRROR_DRAW, call Show
                    N times with the origin moved by OFFSETS[N-1] .. OFFSETS[0], clear the mark,
                    then draw the unit itself on top.
    D   six body draws in Show's state switch (0x00422397 0x0042243E 0x004224E5 0x004225AB
        0x004226D8 0x00422732, each `call [ebx+0x84]` TLibraryImage.Show) -> call cave_draw + nop:
        while marked, the image is drawn through build_unit_vfx.py's vfx_core (0x0044C800) at
        COPY_OPACITY 128/256: the engine draws it normally and the changed pixels are blended
        half-way back to what was behind them, for every sprite class.  Fixed 2026-10-29: the
        copies used VMT +0x9C ShowTransparent (ILPACK's 50 % blend), which is TLibraryImage's empty
        stub (0x5520E85C, `ret 4`) for TRLESprite08 -- 16048 of the 17676 unit sprites (231 of the
        250 libraries under Images/UNITS hold some), so most units' copies were not drawn.  Without
        build_unit_vfx.py's header the copies fall back to that +0x9C draw.
    K   0x0042274B (6 B) -> cave_skip: while marked, jump past the overlays (hero marker, status
        effect animations, health bar) to the try block's normal exit 0x00422B00.
    The shadow is a separate method (ShowShadow), so the images have none.  Images left are read
    from the engine's own counter on every frame, so they vanish the moment one is hit.
    STATUES (build_stonegaze.py, 2026-10-22): this wrapper also owns Stone Gaze's look.  For a
    live unit holding Petrified (0xCC) while Stone Gaze's AoWTCPCK header ("SGZ1" at 0x0043C800) is
    present, cave_show sets bit 1 of the draw byte for the whole Show (copies included), and the
    dispatch draws it through vfx_core with Stone Gaze's colour table (0x0043CB00) as the colour
    map: opacity 256, or COPY_OPACITY for its copies.  Without build_unit_vfx.py's header it jumps
    to Stone Gaze's tint_draw (0x0043C810) instead, which tints TRLESprite16 only (and draws a
    statue's copies opaque).  Bit 0 is the copies' mark, and only bit 0 skips the overlays.
    INVISIBILITY / MISTFORM (build_unit_vfx.py, 2026-10-29): likewise, while that script's header
    ("UVX1" at 0x0044C000) is present, cave_show sets bit 2 for every live unit, and a body draw
    that is neither a statue nor a copy jumps to its vfx_tc (0x0044C010), which decides per unit.
    UNDO ORDER: none.  Any of the three scripts may be undone first: no unit is marked without its
    header, and cave_disp tests build_unit_vfx.py's header before calling vfx_core.  checks()
    refuses to apply this script while a header is present but vfx_core (0x0044C800) or Stone
    Gaze's colour table holds other bytes than those scripts build: apply them first.
    LAYOUT: cave_show 0x43C000 (the VMT cell), cave_draw 0x43C120 (the six draw sites) and
    cave_skip 0x43C150 are pinned, so a rewrite keeps every hook byte.  cave_draw is a jump to
    cave_disp (the dispatch: statue > copy > VFX > plain); the copies' offset table is cave_offs.

REGISTRATION (package init -- prove by launching the exe)
    0x557BCD0E  `call RegisterAbility` -> cave_reg: replay, TMultiLevelAbility.Create, id 0xC6, mask
    0x03FF, cap 20, Put(level, 4) for 1..20, then a run-time copy of TMultiLevelAbility's VMT
    (GetMem, VMT-0x40..VMT+0x110, parent link -> TMultiLevelAbility) with +0x10C GetLevelName ->
    cave_lname ("Mirror Image" at level 0, "Mirror Image I".."XX").  Record:
    build_mirrorimage_pfs.py.  LADDER 0xC7.  Hero Offers 0 %, Resistances column.

RNG none drawn.  An absorbed attack skips the defender's raw roll, decided from replicated state
(ability level and the per-battle counter, advanced identically by every peer's Generate), so the
draw count stays in step.

Slots: AoWEPACK 0x558B3400-0x558B37FF, AoWTCPCK 0x0043C000-0x0043C3FF, exclusive.  PIC.  Needs
build_combatunit_slot.py (asserted).  Surgical --undo (both modules).

    python build_scripts/build_mirrorimage.py            dry run + state
    python build_scripts/build_mirrorimage.py --apply
    python build_scripts/build_mirrorimage.py --undo
    python build_scripts/build_mirrorimage.py --dis
"""
import math, os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, ansistr
import combatunit_slot as S

EPACK = P.TARGET
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
MIRROR, NAME = 0xC6, "Mirror Image"
MASK, LEVELS, COST = 0x03FF, 20, 4
ROMAN = ("I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX").split()
assert len(ROMAN) == LEVELS

# ---------------------------------------------------------------- AoWEPACK
E_SLOT = (0x558B3400, 0x558B3800)
R_SITE = 0x557BCD0E
REGISTER, ML_CREATE, GETMEM, PUT_FN = 0x55750238, 0x55765168, 0x55701008, 0x55702EB4
LSTRASG, LSTRCAT3, ISCLASS = 0x55701150, 0x55701190, 0x557010C0
VMT_STRIKECA, VMT_RANGEDCA = 0x5571E344, 0x5571E7EC
VMT_TCOMBATUNIT, VMT_FAST, VMT_ML = 0x55715A94, S.FAST_VMT, 0x5571DFD0
CELL_ML = VMT_ML - 0x40
VMT_NEG, ML_SLOTS, SLOT_LNAME = 0x40, 0x110, 0x10C
V_ROLE, V_ROLEEX, V_ABLEVEL = 0x110, 0x114, 0xB0
E_SITES = {   # name: (va, vanilla, function lo, hi)
    "role":   (0x55729C4E, bytes.fromhex("ff9710010000"), 0x55729C20, 0x55729C98),
    "roleex": (0x55729CCA, bytes.fromhex("ff9714010000"), 0x55729C98, 0x55729D10),
}
USED_TAC = S.TAC_SLOT + S.B_MIRROR               # [unit+0x68]
USED_FAST = S.FAST_SLOT + S.B_MIRROR             # [unit+0x64]
DRAWING = S.TAC_SLOT + S.B_MIRROR_DRAW           # [unit+0x6A]

# ---------------------------------------------------------------- AoWTCPCK
T_SLOT = (0x0043C000, 0x0043C400)
SHOW, SHOW_END = 0x00421EE0, 0x00422B82
SHOW_CELL = 0x00412DB0                           # TTacticalCombatUnitHS VMT +0xA8
SKIP_SITE, SKIP_RESUME, SHOW_EXIT = 0x0042274B, 0x00422751, 0x00422B00
DRAW_SITES = (0x00422397, 0x0042243E, 0x004224E5, 0x004225AB, 0x004226D8, 0x00422732)
IMG_MODE, IMG_SHOW, IMG_SHOWTRANS = 0x38, 0x84, 0x9C
# Stone Gaze's statue tint (build_stonegaze.py), drawn from this Show wrapper: bit 1 of the draw
# byte marks a unit holding Petrified when Stone Gaze's AoWTCPCK header is present.
PETRIFIED, SG_MAGIC_VA, SG_MAGIC, SG_TINT, SG_LUT = 0xCC, 0x0043C800, 0x315A4753, 0x0043C810, 0x0043CB00
# build_unit_vfx.py's Invisibility pulse and Mistform haze: bit 2 marks a live unit while that
# script's header is present; the dispatch then hands plain body draws to its vfx_tc.  Its
# vfx_core draws the copies and the statues while the header is present.
VFX_MAGIC_VA, VFX_MAGIC, VFX_ENTRY, VFX_CORE = 0x0044C000, 0x31585655, 0x0044C010, 0x0044C800
DRAW_COPY, DRAW_STONE, DRAW_VFX = 1, 2, 4
COPY_OPACITY = 0x80                              # of 256: ILPACK's ShowTransparent is a 50 % blend
T_PINNED = {"show": 0x0043C000, "draw": 0x0043C120, "skip": 0x0043C150}


def offsets():
    """Image k (0-based) sits at OFFSETS[k]; the highest k is the first to go.  Three ellipses
    (x radius twice y), opposite pairs consecutive so the cloud stays balanced as it thins."""
    rings = ((10, 5, (0, 180, 60, 240, 120, 300)),
             (18, 9, (30, 210, 90, 270, 150, 330)),
             (26, 13, (0, 180, 45, 225, 90, 270, 135, 315)))
    out = []
    for rx, ry, angles in rings:
        for a in angles:
            out.append((round(rx * math.cos(math.radians(a))), round(ry * math.sin(math.radians(a)))))
    assert len(out) == LEVELS and len(set(out)) == LEVELS
    return out


OFFSETS = offsets()


def build_absorb(va):
    src = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  ebx, edx
        {{ANC}}
        mov  eax, esi
        lea  edx, [edi + {{STRIKE}}]
        call {ISCLASS:#x}
        test al, al
        jne  b_cls
        mov  eax, esi
        lea  edx, [edi + {{RANGED}}]
        call {ISCLASS:#x}
        test al, al
        je   b_no
    b_cls:
        test ebx, ebx
        je   b_no
        mov  eax, ebx
        lea  edx, [edi + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   b_no
        mov  eax, ebx
        mov  edx, {MIRROR:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABLEVEL:#x}]
        movzx eax, al
        test eax, eax
        je   b_no
        mov  edx, {USED_TAC:#x}
        lea  ecx, [edi + {{FAST}}]
        cmp  dword ptr [ebx], ecx
        jne  b_slot
        mov  edx, {USED_FAST:#x}
    b_slot:
        movzx ecx, byte ptr [ebx + edx]
        cmp  ecx, eax
        jae  b_no
        inc  byte ptr [ebx + edx]
        mov  al, 1
        jmp  b_out
    b_no:
        xor  eax, eax
    b_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "edi", {"STRIKE": VMT_STRIKECA, "RANGED": VMT_RANGEDCA,
                                "TCU": VMT_TCOMBATUNIT, "FAST": VMT_FAST})


def build_site(va, absorb_va, slot, nargs):
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  edx, eax
        mov  eax, ebx
        call {absorb_va:#x}
        test al, al
        pop  ecx
        pop  edx
        pop  eax
        jne  r_miss
        jmp  dword ptr [edi + {slot:#x}]
    r_miss:
        xor  eax, eax
        ret  {4 * nargs:#x}
    """, va)


def lname_tail():
    t = ansistr(NAME)
    t += b"\0" * (32 - len(t))
    for r in ROMAN:
        s = ansistr(" " + r)
        assert len(s) <= 16
        t += s + b"\0" * (16 - len(s))
    return t


def build_lname(va):
    src = f"""
        push ebx
        push esi
        mov  esi, ecx
        mov  ebx, edx
        {{ANC}}
        lea  edx, [eax + {{NAME}}]
        test ebx, ebx
        je   l_plain
        cmp  ebx, {LEVELS}
        ja   l_plain
        shl  ebx, 4
        lea  ecx, [eax + ebx + {{SUF}}]
        mov  eax, esi
        call {LSTRCAT3:#x}
        jmp  l_out
    l_plain:
        mov  eax, esi
        call {LSTRASG:#x}
    l_out:
        pop  esi
        pop  ebx
        ret
    """
    # suffix k (level k+1) has its characters at tail 32 + 16k + 8; level L * 16 lands there from 24
    return pic(src, va, "eax", {"NAME": ("TAIL", 8), "SUF": ("TAIL", 32 + 8 - 16)}, lname_tail())


def build_reg(va, lname_va):
    src = f"""
        call {REGISTER:#x}
        push ebp
        mov  ebp, esp
        push esi
        push edi
        {{ANC}}
        push eax
        lea  eax, [eax + {{MLVMT}}]
        xor  ecx, ecx
        mov  dl, 1
        call {ML_CREATE:#x}
        mov  esi, eax
        mov  dword ptr [esi + 0xc], {MIRROR:#x}
        mov  word ptr [esi + 0x20], {MASK:#x}
        mov  dword ptr [esi + 0x28], {LEVELS}
        lea  eax, [esi + 8]
        mov  edx, dword ptr [ebp - 0xc]
        lea  edx, [edx + {{NAME}}]
        call {LSTRASG:#x}
        mov  edi, 1
    c_put:
        mov  eax, dword ptr [esi + 0x2c]
        mov  edx, edi
        mov  ecx, {COST}
        call {PUT_FN:#x}
        inc  edi
        cmp  edi, {LEVELS}
        jle  c_put
        mov  eax, {VMT_NEG + ML_SLOTS:#x}
        call {GETMEM:#x}
        mov  edi, eax
        push esi
        mov  esi, dword ptr [esi]
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + ML_SLOTS) // 4:#x}
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop  esi
        lea  edx, [eax + {VMT_NEG:#x}]
        mov  dword ptr [eax], edx
        mov  ecx, dword ptr [ebp - 0xc]
        lea  edi, [ecx + {{LNAME}}]
        mov  dword ptr [edx + {SLOT_LNAME:#x}], edi
        lea  edi, [ecx + {{MLCELL}}]
        mov  dword ptr [edx - 0x18], edi
        mov  dword ptr [esi], edx
        mov  edx, esi
        mov  eax, ebx
        call {REGISTER:#x}
        pop  eax
        pop  edi
        pop  esi
        pop  ebp
        ret
    """
    return pic(src, va, "eax", {"MLVMT": VMT_ML, "NAME": ("TAIL", 8), "LNAME": lname_va,
                                "MLCELL": CELL_ML}, ansistr(NAME))


def e_layout():
    caves, va = [], E_SLOT[0]
    absorb = build_absorb(va)
    caves.append(("cave_absorb", va, absorb))
    va = (va + len(absorb) + 0xF) & ~0xF
    for n, slot, nargs in (("role", V_ROLE, 1), ("roleex", V_ROLEEX, 2)):
        b = build_site(va, E_SLOT[0], slot, nargs)
        caves.append(("cave_" + n, va, b))
        va = (va + len(b) + 0xF) & ~0xF
    lname = build_lname(va)
    caves.append(("cave_lname", va, lname))
    lname_va = va
    va = (va + len(lname) + 0xF) & ~0xF
    caves.append(("cave_reg", va, build_reg(va, lname_va)))
    return {n[5:]: v for n, v, _b in caves}, caves


def build_offs():
    """The copies' offsets, (dx, dy) signed bytes, image k at 2k."""
    return b"".join(struct.pack("<bb", dx, dy) for dx, dy in OFFSETS)


def build_show(va, offs_va):
    """Locals: -0x10 anchor, -0x14 images left."""
    src = f"""
        push ebp
        mov  ebp, esp
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  edi, ecx
        {{ANC}}
        push ecx
        push 0
        mov  eax, dword ptr [ebx + 0x1c]
        test eax, eax
        je   s_plain
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   s_plain
        mov  eax, dword ptr [ebx + 0x1c]
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je   s_vfx
        mov  ecx, dword ptr [ebp - 0x10]
        cmp  dword ptr [ecx + {{SGMAGIC}}], {SG_MAGIC:#x}
        jne  s_vfx
        mov  eax, dword ptr [ebx + 0x1c]
        or   byte ptr [eax + {DRAWING:#x}], {DRAW_STONE}
    s_vfx:
        mov  ecx, dword ptr [ebp - 0x10]
        cmp  dword ptr [ecx + {{VFXMAGIC}}], {VFX_MAGIC:#x}
        jne  s_img
        mov  eax, dword ptr [ebx + 0x1c]
        or   byte ptr [eax + {DRAWING:#x}], {DRAW_VFX}
    s_img:
        mov  eax, dword ptr [ebx + 0x1c]
        mov  edx, {MIRROR:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABLEVEL:#x}]
        movzx eax, al
        mov  edx, dword ptr [ebx + 0x1c]
        movzx ecx, byte ptr [edx + {USED_TAC:#x}]
        sub  eax, ecx
        jle  s_plain
        cmp  eax, {LEVELS}
        jbe  s_n
        mov  eax, {LEVELS}
    s_n:
        mov  dword ptr [ebp - 0x14], eax
        or   byte ptr [edx + {DRAWING:#x}], {DRAW_COPY}
    s_loop:
        dec  dword ptr [ebp - 0x14]
        js   s_done
        mov  eax, dword ptr [ebp - 0x14]
        mov  ecx, dword ptr [ebp - 0x10]
        movsx edx, byte ptr [ecx + eax*2 + {{TX}}]
        movsx ecx, byte ptr [ecx + eax*2 + {{TY}}]
        neg  edx
        add  edx, esi
        neg  ecx
        add  ecx, edi
        push dword ptr [ebp + 8]
        mov  eax, ebx
        call {SHOW:#x}
        jmp  s_loop
    s_done:
        mov  eax, dword ptr [ebx + 0x1c]
        and  byte ptr [eax + {DRAWING:#x}], {0xFF ^ DRAW_COPY:#x}
    s_plain:
        push dword ptr [ebp + 8]
        mov  eax, ebx
        mov  edx, esi
        mov  ecx, edi
        call {SHOW:#x}
        mov  eax, dword ptr [ebx + 0x1c]
        test eax, eax
        je   s_out
        and  byte ptr [eax + {DRAWING:#x}], {0xFF ^ (DRAW_STONE | DRAW_VFX):#x}
    s_out:
        add  esp, 8
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  4
    """
    return pic(src, va, "ecx", {"TX": offs_va, "TY": offs_va + 1, "SGMAGIC": SG_MAGIC_VA,
                                "VFXMAGIC": VFX_MAGIC_VA})


def build_draw(va, disp_va):
    """The six draw sites call this pinned address; the dispatch itself is cave_disp."""
    return asm(f"jmp {disp_va:#x}", va)


def build_disp(va):
    """Jumped to from cave_draw: [esp] = the return into Show, [esp+4] = the surface, EAX image,
    EDX x, ECX y, EBX the image's VMT, EBP Show's frame ([ebp-4] = the hotspot).
    Statue or copy, with build_unit_vfx.py's header present: vfx_core(opacity 256, or COPY_OPACITY
    for a copy; tint 0; map = Stone Gaze's colour table for a statue, else 0).  Without the header:
    a statue jumps to Stone Gaze's tint_draw, a copy of a show-mode-0 image is drawn through VMT
    +0x9C.  Otherwise VFX (marked) -> vfx_tc; plain -> VMT +0x84."""
    src = f"""
        push eax
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x1c]
        movzx eax, byte ptr [eax + {DRAWING:#x}]
        test al, {DRAW_STONE | DRAW_COPY}
        jne  d_look
        test al, {DRAW_VFX}
        pop  eax
        jne  d_vfx
    d_plain:
        jmp  dword ptr [ebx + {IMG_SHOW:#x}]
    d_vfx:
        jmp  {VFX_ENTRY:#x}
    d_look:
        push esi
        push edi
        mov  esi, eax
        {{ANC}}
        cmp  dword ptr [edi + {{VFXMAGIC}}], {VFX_MAGIC:#x}
        jne  d_legacy
        xor  eax, eax
        test esi, {DRAW_STONE}
        je   d_map
        lea  eax, [edi + {{SGLUT}}]
    d_map:
        push eax
        push 0
        mov  eax, 0x100
        test esi, {DRAW_COPY}
        je   d_op
        mov  eax, {COPY_OPACITY:#x}
    d_op:
        push eax
        push dword ptr [esp + 0x1c]
        mov  eax, dword ptr [esp + 0x18]
        call {VFX_CORE:#x}
        pop  edi
        pop  esi
        add  esp, 4
        ret  4
    d_legacy:
        mov  eax, esi
        pop  edi
        pop  esi
        test al, {DRAW_STONE}
        pop  eax
        jne  d_stone
        cmp  byte ptr [eax + {IMG_MODE:#x}], 0
        jne  d_plain
        jmp  dword ptr [ebx + {IMG_SHOWTRANS:#x}]
    d_stone:
        jmp  {SG_TINT:#x}
    """
    return pic(src, va, "edi", {"VFXMAGIC": VFX_MAGIC_VA, "SGLUT": SG_LUT})


def build_skip(va):
    return asm(f"""
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x1c]
        test byte ptr [eax + {DRAWING:#x}], {DRAW_COPY}
        jne  k_skip
        jmp  {SKIP_RESUME:#x}
    k_skip:
        jmp  {SHOW_EXIT:#x}
    """, va)


def t_layout():
    """show, draw and skip pinned (hook targets); disp and offs packed after skip."""
    skip = build_skip(T_PINNED["skip"])
    disp_va = (T_PINNED["skip"] + len(skip) + 0xF) & ~0xF
    disp = build_disp(disp_va)
    offs_va = (disp_va + len(disp) + 0xF) & ~0xF
    caves = [("cave_show", T_PINNED["show"], build_show(T_PINNED["show"], offs_va)),
             ("cave_draw", T_PINNED["draw"], build_draw(T_PINNED["draw"], disp_va)),
             ("cave_skip", T_PINNED["skip"], skip),
             ("cave_disp", disp_va, disp),
             ("cave_offs", offs_va, build_offs())]
    assert T_PINNED["show"] + len(caves[0][2]) <= T_PINNED["draw"], "cave_show overruns cave_draw"
    assert T_PINNED["draw"] + len(caves[1][2]) <= T_PINNED["skip"], "cave_draw overruns cave_skip"
    return {n[5:]: v for n, v, _b in caves}, caves


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def checks():
    import build_unit_vfx as UV, build_stonegaze as SG   # before module() moves P.TARGET
    module(TCPCK, 0x00400000)
    t = open(TCPCK, "rb").read()
    rt = lambda va: struct.unpack_from("<I", t, P.va2off(t, va))[0]
    bt = lambda va, n: t[P.va2off(t, va):P.va2off(t, va) + n]
    if rt(S.TAC_VMT - 0x1C) != S.TAC_SIZE:
        sys.exit("ABORT: TTacticalCombatUnit is not %#x bytes -- apply build_combatunit_slot.py first"
                 % S.TAC_SIZE)
    for va, want, what in ((0x00422B7E, bytes.fromhex("8be55dc20400"), "Show's `ret 4` epilogue"),
                           (SHOW_EXIT, bytes.fromhex("33c05a5959648910"), "Show's try-block exit"),
                           (SKIP_RESUME, bytes.fromhex("8b404c"), "the overlay block after the hook")):
        if bt(va, len(want)) != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))
    for va in DRAW_SITES:
        if bt(va - 2, 2) != bytes.fromhex("8b18"):
            sys.exit("ABORT: %08X is not preceded by `mov ebx,[eax]` (EBX = the image VMT)" % va)
    # the dispatch calls build_unit_vfx.py's vfx_core and reads Stone Gaze's colour table whenever
    # their headers are present: both must be the current scripts' bytes
    for magic_va, magic, va, mod, cave, script in (
            (VFX_MAGIC_VA, VFX_MAGIC, VFX_CORE, UV, "vfx_core", "build_unit_vfx.py"),
            (SG_MAGIC_VA, SG_MAGIC, SG_LUT, SG, "cave_lut", "build_stonegaze.py")):
        want = [b for n, v, b in mod.T_CAVES if n == cave and v == va]
        if len(want) != 1:
            sys.exit("ABORT: %s has no %s at %08X" % (script, cave, va))
        if rt(magic_va) == magic and bt(va, len(want[0])) != want[0]:
            sys.exit("ABORT: %s's header is present but %08X is not its %s -- run %s --apply first"
                     % (script, va, cave, script))
    module(EPACK, 0x55700000)
    d = open(EPACK, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for vmt, cname in ((VMT_STRIKECA, b"TStrikeCA"), (VMT_RANGEDCA, b"TRangedAttackCA"),
                       (VMT_TCOMBATUNIT, b"TCombatUnit"), (VMT_FAST, b"TFastCombatUnit"),
                       (VMT_ML, b"TMultiLevelAbility")):
        cn = P.va2off(d, rd(vmt - 0x20))
        if rd(vmt - 0x40) != vmt or d[cn + 1:cn + 1 + d[cn]] != cname:
            sys.exit("ABORT: %s VMT not at %08X" % (cname.decode(), vmt))
    if rd(VMT_ML - 0x20) - VMT_ML != ML_SLOTS:
        sys.exit("ABORT: TMultiLevelAbility's VMT is not %#x bytes of slots" % ML_SLOTS)
    if d[P.va2off(d, 0x55726A65):P.va2off(d, 0x55726A65) + 3] != bytes.fromhex("c20400"):
        sys.exit("ABORT: ExecuteDamageRole does not end `ret 4` at 55726A65")
    ex = d[P.va2off(d, 0x55726A6C):P.va2off(d, 0x55726B04)]
    if bytes.fromhex("c20800") not in ex:
        sys.exit("ABORT: ExecuteDamageRoleEx does not end `ret 8`")
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        blob = d[ra:ra + rs]
        for pat in (b"\xb8" + struct.pack("<I", MIRROR) + b"\xe8",):
            k = blob.find(pat)
            while k >= 0:
                src = P.IMAGE_BASE + sva + k
                tgt = src + 10 + struct.unpack_from("<i", blob, k + 6)[0]
                if tgt in (0x5576601C,) and not E_SLOT[0] <= src < E_SLOT[1]:
                    sys.exit("ABORT: %08X also registers %#x" % (src, MIRROR))
                k = blob.find(pat, k + 1)
        for modrm in (0x40, 0x41, 0x42, 0x43, 0x45, 0x46, 0x47):
            pat = bytes([0xC7, modrm, 0x0C]) + struct.pack("<I", MIRROR)
            k = blob.find(pat)
            while k >= 0:
                src = P.IMAGE_BASE + sva + k
                if not E_SLOT[0] <= src < E_SLOT[1]:
                    sys.exit("ABORT: %08X stores id %#x into an ability" % (src, MIRROR))
                k = blob.find(pat, k + 1)
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names
    if ability_names.names().get(MIRROR, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x another name" % MIRROR)


E_AT, E_CAVES = e_layout()
T_AT, T_CAVES = t_layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
call6 = lambda src, dst: call_to(src, dst) + b"\x90"
E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, E_AT["reg"]))] + \
    [(va, van, call6(va, E_AT[n])) for n, (va, van, _lo, _hi) in E_SITES.items()]
E_INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, lo, hi) in E_SITES.items()]
T_HOOKS = [(SHOW_CELL, struct.pack("<I", SHOW), struct.pack("<I", T_AT["show"])),
           (SKIP_SITE, bytes.fromhex("8b45fc8b401c"), jmp_to(SKIP_SITE, T_AT["skip"], 6))] + \
    [(va, bytes.fromhex("ff9384000000"), call6(va, T_AT["draw"])) for va in DRAW_SITES]
T_INTERIOR = [(va, va + 6, SHOW, SHOW_END) for va in (SKIP_SITE,) + DRAW_SITES]
# entry points, asserted (and read by rng_audit.py --owners)
ENTRY = {"absorb": 0x558B3400, "role": 0x558B3490, "roleex": 0x558B34B0, "lname": 0x558B34D0,
         "reg": 0x558B3670, "show": 0x0043C000, "draw": 0x0043C120, "skip": 0x0043C150,
         "disp": 0x0043C170, "offs": 0x0043C200}
assert {**E_AT, **T_AT} == ENTRY, "the cave layout moved"


def go(argv):
    module(EPACK, 0x55700000)
    run("build_mirrorimage [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_mirrorimage [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv,
        reloc_ok=(SHOW_CELL,))
    module(EPACK, 0x55700000)


if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in {**E_AT, **T_AT}.items()))
    checks()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])
        print("\n" + "=" * 60)
    go(argv)
