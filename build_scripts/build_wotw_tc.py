#!/usr/bin/env python
r"""
build_wotw_tc.py -- the AoWTCPCK half of Weight of the World (spell 91): the cast, the strike on
every unit within 6 hexes, the field mark, the battle AI and the target preview.  AoWEPACK half:
build_wotw.py.  The field's rules: build_wotw_field.py + build_wotw_field_tc.py.  Its animation:
build_wotw_anim.py.  Owner's design 2026-10-26 (05-spells-added.md).

THE CLASS  SpellTypes[91] = 0x1E, Geyser's: the burst drawn at the target hex, then the landing.
  N   0x0040F0C9  NextStrike's TE-kind test `sub eax,0x15 / je` (5 B) -> jmp cave_alias: for spell 91
      [fx+0x2C] = nil (Disease Cloud's way), so Geyser's class acts on no unit; independent of
      build_breath_line.py (0x0040F0B1), build_deathfire_tc.py (0x0040F0E3) and build_lethe_tc.py
      (0x0040F0E9).
  L   0x0040C868  the landing dispatch's tail `sub al,3 / je 0x40C8CD / jmp 0x40CAF2` (9 B; al = kind
      - 7 on every path, including build_lethe_tc.py's way back) -> jmp cave_land: for kind 0x1E, spell
      0x34 / 91:
        1. every hex within 6 of the target (HN 0..126; CenterHNtoHX is a closed-form ring walker),
           bounds-checked (TMapLevel.GetField has none): its unit, alive and enabled, takes one strike
           -- System.RandSeed := TAoWHSMap.Random(map, $FFFFFF), then the spell's CreateCA (+0x78,
           build_wotw.py's +50 % wrapper) with the caster, damage-type icons, the hurt action and
           blood, ExecuteCombatAction, free.  Friend and foe alike; walls, gates, terrain and
           structures are never touched.  The caster, when it stands in the area, is struck last.
        2. the field: bit 0x20 of [field+0x1B] on every hex of the area, bit 0x40 on the centre.  The
           combat map's fields are created zero-filled per battle, so the marks end with it; a bit
           cannot stack, so overlapping casts do not stack.  Readers: build_wotw_field*.py and
           build_wotw_anim.py.  Bits 0x01-0x10 are build_tactical_los.py's, 0x80 build_los_terrain.py's.
        3. the spell's sound cue 1.
      Other kinds and spells replay the tail.
  A   0x00415C19  TCAI.CheckUnit before the per-id switch (6 B) -> jmp cave_ai: for 91, Triple
      Fireball's case (0x75) widened to radius 6: the aimed unit's hex and its in-range neighbours,
      each scored by EvalPath and EvalArea127 (EvalArea 0x00414D14 to HN 126, bounds-checked) -- the
      enemy units in the area minus its own; a net value of 0 or less refuses the cast.  The scratch
      dwords the tail reads are restored, as build_satchels_tc.py's cave_ai does.
  P   0x00428275  the ranged preview's `call GetTCUnitHS` (5 B) -> call cave_preview: for 91 the
      preview image on every hex of the area (the 7- and 19-hex cases' own drawing), then the exit.
  S   0x0042E219  Geyser's spray count `mov eax,[ebp-0xC] / sub eax,1` (6 B) -> jmp cave_spray: for 91
      no spray particles (owner: an energy spell, no debris; the burst and loop are a faint amber glow,
      build_wotw_pfs.py).  The count's own random draw stays (display only).
RNG: P1 SYNCED, the bridge -- one synced Random reseeds System.RandSeed before each struck unit's
CA, whose raw RandInt rolls (the 0x31003 unit handler's own idiom).  Sites: RNG_SITES.
Slot 0x00444000-0x00444FFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_wotw_tc.py            dry run + state
    python build_scripts/build_wotw_tc.py --apply
    python build_scripts/build_wotw_tc.py --undo
    python build_scripts/build_wotw_tc.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, run
from piccave import pic

WOTW, RADIUS_HN = 91, 127
FIELD_BIT, CENTRE_BIT = 0x20, 0x40
SLOT = (0x00444000, 0x00445000)
SPELLTYPES, CLASS_GEYSER = 0x004672F4, 0x1E
GETXYZ, HPTOHX, HXTOHP, CENTERHN, DHXTORAD = 0x00402DF4, 0x004022C4, 0x004022BC, 0x004022AC, 0x004022A4
GETMAPLEVEL, GETFIELD, GETSPELL, SFXPLAY, RANDOM, EXEC_CA = 0x00401E64, 0x00401E54, 0x004029B4, 0x004022F4, 0x0040298C, 0x0040259C
VAR_CONTAINER, VAR_COMBATMAP, VAR_HSSET, VAR_MAP, VAR_SEED = 0x00469420, 0x0046C064, 0x0046E8D0, 0x0046E8D4, 0x0046DC08
UNIT_HS, L_W, L_H = 0x220104, 0x0C, 0x10
LANDING_DONE, LAND_8CD = 0x0040CAF2, 0x0040C8CD
DAMAGE_ICONS, SET_ACTION, HIT_BLOOD = 0x00407C30, 0x004236E0, 0x0040992C
GET_TCU, XYZ_COUNT, LIB_IMAGE, IMG_SHOW = 0x0041D2E8, 0x00402DFC, 0x004016F4, 0x004016A4
EVALPATH, EVALHEX, AI_TAIL, AI_GO = 0x00414DA8, 0x00414754, 0x004164C8, 0x00415C1F
N_GO, N_SPELL, N_DONE = 0x0040F0CE, 0x0040F0E0, 0x0040F227
PV_EXIT = 0x004285DE
SITES = {   # name: (va, vanilla bytes, kind)
    "alias":   (0x0040F0C9, "83e8157412", "jmp"),
    "land":    (0x0040C868, "2c037461e981020000", "jmp"),
    "ai":      (0x00415C19, "8b459c8945d8", "jmp"),
    "preview": (0x00428275, "e86e50ffff", "call"),
    "spray":   (0x0042E219, "8b45f483e801", "jmp"),
}
SPRAY_GO = 0x0042E21F
B = {}


def t_alias(va):
    return asm(f"""
        sub  eax, 0x15
        jne  {N_GO:#x}
        mov  eax, dword ptr [ebp - 4]
        cmp  dword ptr [eax + 0x18], {WOTW}
        jne  {N_SPELL:#x}
        mov  eax, dword ptr [ebp - 0x10]
        xor  edx, edx
        mov  dword ptr [eax + 0x2c], edx
        jmp  {N_DONE:#x}
    """, va)


# l_field: eax = x, edx = y -> eax = the field, or 0 off the level.
# l_unit: the same -> eax = its live, enabled unit, or 0.  (No `;` comments inside asm: keystone splits on them.)
FIELD_FN = f"""
    l_field:
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   f_no
        cmp  esi, dword ptr [eax + {L_W:#x}]
        jae  f_no
        cmp  edi, dword ptr [eax + {L_H:#x}]
        jae  f_no
        mov  edx, esi
        mov  ecx, edi
        call {GETFIELD:#x}
        jmp  f_out
    f_no:
        xor  eax, eax
    f_out:
        pop  edi
        pop  esi
        ret
    l_unit:
        call l_field
        test eax, eax
        je   u_no
        mov  edx, {UNIT_HS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je   u_no
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   u_no
        test byte ptr [eax + 0x47], 1
        jne  u_no
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        pop  eax
        jne  u_out
    u_no:
        xor  eax, eax
    u_out:
        ret
"""

CENTRE_HN = """
        lea  eax, [ebp - 0x14]
        push eax
        lea  eax, [ebp - 0x18]
        push eax
        mov  ecx, edi
        mov  edx, dword ptr [ebp - 0x2c]
        mov  eax, dword ptr [ebp - 0x28]
        call {CENTERHN:#x}""".format(CENTERHN=CENTERHN)


def t_land(va):
    """[ebp-0x20] the effect, [ebp-4] the TE ([+0x10] the caster); the host's scratch dwords are
    used as build_lethe_tc.py uses them: -0x10 spell, -0x14/-0x18 hex x/y, -0x24 CA, -0x28/-0x2C
    centre x/y, -0x30 the caster's own hex (x | y << 8 | 0x10000), -0x38 the struck object."""
    src = f"""
        sub  al, 3
        je   {LAND_8CD:#x}
        mov  eax, dword ptr [ebp - 0x20]
        cmp  byte ptr [eax + 0x34], 0x1e
        jne  l_done
        cmp  dword ptr [eax + 0x14], 0x34
        jne  l_done
        cmp  dword ptr [eax + 0x18], {WOTW}
        jne  l_done
        push ebx
        push esi
        push edi
        {{ANC}}
        lea  eax, [ebp - 0x2c]
        push eax
        mov  eax, dword ptr [ebp - 0x20]
        mov  eax, dword ptr [eax + 0x1c]
        xor  edx, edx
        call {GETXYZ:#x}
        mov  eax, dword ptr [eax + 8]
        push eax
        mov  eax, dword ptr [ebp - 0x20]
        mov  eax, dword ptr [eax + 0x1c]
        xor  edx, edx
        call {GETXYZ:#x}
        mov  eax, dword ptr [eax + 4]
        lea  ecx, [ebp - 0x28]
        pop  edx
        call {HPTOHX:#x}
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {WOTW}
        call {GETSPELL:#x}
        mov  dword ptr [ebp - 0x10], eax
        test eax, eax
        je   l_out
        mov  dword ptr [ebp - 0x30], 0
        xor  edi, edi
    l_hex:
        {CENTRE_HN}
        mov  eax, dword ptr [ebp - 0x14]
        mov  edx, dword ptr [ebp - 0x18]
        call l_unit
        test eax, eax
        je   l_skip
        mov  edx, dword ptr [ebp - 4]
        cmp  eax, dword ptr [edx + 0x10]
        jne  l_do
        mov  ecx, dword ptr [ebp - 0x18]
        shl  ecx, 8
        or   ecx, dword ptr [ebp - 0x14]
        or   ecx, 0x10000
        mov  dword ptr [ebp - 0x30], ecx
        jmp  l_skip
    l_do:
        call l_strike
    l_skip:
        inc  edi
        cmp  edi, {RADIUS_HN}
        jne  l_hex
        mov  ecx, dword ptr [ebp - 0x30]
        test ecx, 0x10000
        je   l_mark0
        movzx eax, cl
        mov  dword ptr [ebp - 0x14], eax
        movzx eax, ch
        mov  dword ptr [ebp - 0x18], eax
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        call l_strike
    l_mark0:
        xor  edi, edi
    l_mark:
        {CENTRE_HN}
        mov  eax, dword ptr [ebp - 0x14]
        mov  edx, dword ptr [ebp - 0x18]
        call l_field
        test eax, eax
        je   l_mnext
        or   byte ptr [eax + 0x1b], {FIELD_BIT:#x}
        test edi, edi
        jne  l_mnext
        or   byte ptr [eax + 0x1b], {CENTRE_BIT:#x}
    l_mnext:
        inc  edi
        cmp  edi, {RADIUS_HN}
        jne  l_mark
        mov  eax, dword ptr [ebx + {{COMBATMAP}}]
        cmp  byte ptr [eax + 0x129], 0
        je   l_out
        mov  eax, dword ptr [ebp - 0x10]
        mov  eax, dword ptr [eax + 0x28]
        mov  edx, 1
        call {SFXPLAY:#x}
    l_out:
        pop  edi
        pop  esi
        pop  ebx
    l_done:
        jmp  {LANDING_DONE:#x}

    l_strike:
        mov  dword ptr [ebp - 0x38], eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax]
        mov  edx, 0xffffff
        call {RANDOM:#x}
        mov  edx, dword ptr [ebx + {{SEED}}]
        mov  dword ptr [edx], eax
        push 0
        mov  ecx, dword ptr [ebp - 0x38]
        mov  edx, dword ptr [ebp - 4]
        mov  edx, dword ptr [edx + 0x10]
        mov  eax, dword ptr [ebp - 0x10]
        mov  esi, dword ptr [eax]
        call dword ptr [esi + 0x78]
        mov  dword ptr [ebp - 0x24], eax
        movzx esi, byte ptr [eax + 0x10]
        lea  eax, [ebp - 0x18]
        push eax
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        lea  ecx, [ebp - 0x14]
        call {HXTOHP:#x}
        mov  eax, dword ptr [ebp - 0x24]
        mov  cx, word ptr [eax + 0x13]
        not  ecx
        and  cx, word ptr [eax + 0x11]
        test cx, cx
        je   s_types
        push 0
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {DAMAGE_ICONS:#x}
    s_types:
        mov  eax, dword ptr [ebp - 0x24]
        mov  cx, word ptr [eax + 0x13]
        test cx, cx
        je   s_hurt
        push 1
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {DAMAGE_ICONS:#x}
    s_hurt:
        test esi, esi
        je   s_exec
        mov  eax, dword ptr [ebp - 0x38]
        mov  eax, dword ptr [eax + 0x60]
        mov  dl, 4
        call {SET_ACTION:#x}
        mov  eax, dword ptr [ebp - 0x38]
        mov  edx, esi
        call {HIT_BLOOD:#x}
    s_exec:
        mov  edx, dword ptr [ebp - 0x24]
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xe4]
        call {EXEC_CA:#x}
        mov  eax, dword ptr [ebp - 0x24]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        ret
    """ + FIELD_FN
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER, "COMBATMAP": VAR_COMBATMAP, "HSSET": VAR_HSSET,
                                "MAP": VAR_MAP, "SEED": VAR_SEED})


def t_ea127(va):
    """EvalArea 0x00414D14 widened to HN 0..126, with a bounds check before EvalHex (which has none).
    Same 9 stack arguments, ret 0x24."""
    src = f"""
        push ebp
        mov  ebp, esp
        add  esp, -0x18
        push ebx
        mov  dword ptr [ebp - 0xc], ecx
        mov  dword ptr [ebp - 8], edx
        mov  dword ptr [ebp - 4], eax
        {{ANC}}
        xor  eax, eax
        mov  dword ptr [ebp - 0x10], eax
    e_loop:
        lea  eax, [ebp - 0x14]
        push eax
        lea  eax, [ebp - 0x18]
        push eax
        mov  ecx, dword ptr [ebp - 0x10]
        mov  edx, dword ptr [ebp + 0x1c]
        mov  eax, dword ptr [ebp + 0x20]
        call {CENTERHN:#x}
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   e_next
        mov  edx, dword ptr [ebp - 0x14]
        cmp  edx, dword ptr [eax + {L_W:#x}]
        jae  e_next
        mov  edx, dword ptr [ebp - 0x18]
        cmp  edx, dword ptr [eax + {L_H:#x}]
        jae  e_next
        cmp  byte ptr [ebp + 0x14], 0
        jne  e_eval
        mov  eax, dword ptr [ebp + 0xc]
        mov  eax, dword ptr [eax + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        cmp  eax, dword ptr [ebp - 0x14]
        jne  e_eval
        mov  eax, dword ptr [ebp + 0xc]
        mov  eax, dword ptr [eax + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        cmp  eax, dword ptr [ebp - 0x18]
        je   e_next
    e_eval:
        push dword ptr [ebp + 0x24]
        push dword ptr [ebp - 0x14]
        push dword ptr [ebp - 0x18]
        push dword ptr [ebp - 8]
        movzx eax, byte ptr [ebp + 0x18]
        push eax
        movzx eax, byte ptr [ebp + 0x10]
        push eax
        push dword ptr [ebp + 0xc]
        push dword ptr [ebp + 8]
        mov  ecx, dword ptr [ebp + 0x28]
        mov  edx, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [ebp - 4]
        call {EVALHEX:#x}
    e_next:
        inc  dword ptr [ebp - 0x10]
        cmp  dword ptr [ebp - 0x10], {RADIUS_HN}
        jne  e_loop
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  0x24
    """
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER})


def ai_eval(x, y, out):
    """EvalPath (-> eax) then EvalArea127 (+= [out]) at hex ([ebp-x], [ebp-y]), as case 0x75 does."""
    return f"""
        push dword ptr [ebp - 0x5c]
        push dword ptr [ebp - 0x60]
        mov  eax, dword ptr [ebp + 0x14]
        mov  eax, dword ptr [eax + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        push eax
        mov  eax, dword ptr [ebp + 0x14]
        mov  eax, dword ptr [eax + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        push dword ptr [ebp - {x:#x}]
        push dword ptr [ebp - {y:#x}]
        push 1
        push dword ptr [ebp + 0x14]
        push dword ptr [ebp + 8]
        lea  edx, [ebp - {out:#x}]
        mov  ecx, dword ptr [ebp + 0x10]
        mov  eax, dword ptr [ebp - 4]
        call {EVALPATH:#x}
        push eax
        push dword ptr [ebp - 0x5c]
        push dword ptr [ebp - 0x60]
        push dword ptr [ebp - {x:#x}]
        push dword ptr [ebp - {y:#x}]
        push 1
        push 1
        push 1
        push dword ptr [ebp + 0x14]
        push dword ptr [ebp + 8]
        lea  edx, [ebp - {out:#x}]
        mov  ecx, dword ptr [ebp + 0x10]
        mov  eax, dword ptr [ebp - 4]
        call {B['ea127']:#x}
        pop  eax"""


SCRATCH = (0x14, 0x18, 0x2C, 0x30, 0x34, 0x38, 0x3C)
SAVE = "\n".join("        push dword ptr [ebp - %#x]" % o for o in SCRATCH)
RESTORE = "\n".join("        pop  dword ptr [ebp - %#x]" % o for o in reversed(SCRATCH))


def t_ai(va):
    return asm(f"""
        mov  eax, dword ptr [ebp - 0x64]
        mov  dword ptr [ebp - 0x28], eax
        cmp  dword ptr [ebp - 0x60], {WOTW}
        jne  {AI_GO:#x}
        mov  eax, dword ptr [ebp - 0x1c]
        cmp  eax, dword ptr [ebp - 0x24]
        jg   {AI_TAIL:#x}
{SAVE}
        {ai_eval(0x8, 0xc, 0x64)}
        mov  dword ptr [ebp - 0x58], eax
        mov  eax, dword ptr [ebp - 8]
        mov  dword ptr [ebp - 0x2c], eax
        mov  eax, dword ptr [ebp - 0xc]
        mov  dword ptr [ebp - 0x30], eax
        mov  dword ptr [ebp - 0x14], 1
    a_hex:
        lea  eax, [ebp - 0x38]
        push eax
        lea  eax, [ebp - 0x3c]
        push eax
        mov  ecx, dword ptr [ebp - 0x14]
        mov  edx, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [ebp - 8]
        call {CENTERHN:#x}
        push dword ptr [ebp - 0x3c]
        mov  eax, dword ptr [ebp + 0x14]
        mov  eax, dword ptr [eax + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        mov  eax, dword ptr [ebp + 0x14]
        mov  eax, dword ptr [eax + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        pop  edx
        mov  ecx, dword ptr [ebp - 0x38]
        call {DHXTORAD:#x}
        cmp  eax, dword ptr [ebp - 0x24]
        jg   a_next
        mov  eax, dword ptr [ebp - 0x28]
        mov  dword ptr [ebp - 0x34], eax
        {ai_eval(0x38, 0x3c, 0x34)}
        mov  dword ptr [ebp - 0x18], eax
        mov  eax, dword ptr [ebp - 0x34]
        cmp  eax, dword ptr [ebp - 0x64]
        jle  a_next
        mov  dword ptr [ebp - 0x64], eax
        mov  eax, dword ptr [ebp - 0x18]
        mov  dword ptr [ebp - 0x58], eax
        mov  eax, dword ptr [ebp - 0x38]
        mov  dword ptr [ebp - 0x2c], eax
        mov  eax, dword ptr [ebp - 0x3c]
        mov  dword ptr [ebp - 0x30], eax
    a_next:
        inc  dword ptr [ebp - 0x14]
        cmp  dword ptr [ebp - 0x14], 7
        jne  a_hex
        mov  eax, dword ptr [ebp - 0x64]
        cmp  eax, dword ptr [ebp - 0x28]
        jg   a_keep
        xor  eax, eax
        mov  dword ptr [ebp - 0x58], eax
        mov  dword ptr [ebp - 0x64], eax
    a_keep:
        mov  eax, dword ptr [ebp - 0x2c]
        mov  dword ptr [ebp - 8], eax
        mov  eax, dword ptr [ebp - 0x30]
        mov  dword ptr [ebp - 0xc], eax
{RESTORE}
        jmp  {AI_TAIL:#x}
    """, va)


def t_preview(va):
    """Replaces `call GetTCUnitHS` in the ranged preview; uses only eax/ecx/edx (the host saves only
    ebx)."""
    PATH = """
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x18]
        mov  eax, dword ptr [eax + 0x34]"""
    return asm(f"""
        call {GET_TCU:#x}
        cmp  dword ptr [eax + 0x38], {WOTW}
        je   p_ours
        ret
    p_ours:
        lea  esp, [esp + 4]
        {PATH}
        call {XYZ_COUNT:#x}
        lea  edx, [eax - 1]
        test edx, edx
        js   p_exit
        lea  eax, [ebp - 0x18]
        push eax
        push edx
        {PATH}
        call {GETXYZ:#x}
        pop  edx
        push dword ptr [eax + 8]
        {PATH}
        call {GETXYZ:#x}
        mov  eax, dword ptr [eax + 4]
        pop  edx
        lea  ecx, [ebp - 0x14]
        call {HPTOHX:#x}
        xor  eax, eax
        mov  dword ptr [ebp - 0x10], eax
    p_hex:
        lea  eax, [ebp - 0x28]
        push eax
        lea  eax, [ebp - 0x2c]
        push eax
        mov  ecx, dword ptr [ebp - 0x10]
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {CENTERHN:#x}
        lea  eax, [ebp - 0x34]
        push eax
        lea  ecx, [ebp - 0x30]
        mov  edx, dword ptr [ebp - 0x2c]
        mov  eax, dword ptr [ebp - 0x28]
        call {HXTOHP:#x}
        push dword ptr [ebp + 8]
        xor  edx, edx
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        call {LIB_IMAGE:#x}
        mov  ecx, dword ptr [ebp - 0x34]
        add  ecx, 2
        sub  ecx, dword ptr [ebp - 0xc]
        mov  edx, dword ptr [ebp - 0x30]
        sub  edx, 8
        sub  edx, dword ptr [ebp - 8]
        call {IMG_SHOW:#x}
        inc  dword ptr [ebp - 0x10]
        cmp  dword ptr [ebp - 0x10], {RADIUS_HN}
        jne  p_hex
    p_exit:
        jmp  {PV_EXIT:#x}
    """, va)


def t_spray(va):
    """S: Geyser's class draws a random count of spray particles ([ebp-0xC]) at the target; for spell 91
    the count is 0 (owner: no debris -- it is energy, not stone).  `sub eax,1` comes last so the
    following `jno` reads its flags, as vanilla's does."""
    return asm(f"""
        mov  eax, dword ptr [ebp - 0xc]
        mov  edx, dword ptr [ebp - 8]
        cmp  dword ptr [edx + 0x14], 0x34
        jne  s_go
        cmp  dword ptr [edx + 0x18], {WOTW}
        jne  s_go
        xor  eax, eax
    s_go:
        sub  eax, 1
        jmp  {SPRAY_GO:#x}
    """, va)


BUILDERS = [("alias", t_alias), ("preview", t_preview), ("ea127", t_ea127), ("ai", t_ai), ("land", t_land),
            ("spray", t_spray)]
RNG_SITES = (0x004444F8,)              # the synced Random in cave_land's l_strike


def layout():
    for n, _b in BUILDERS:
        B.setdefault(n, SLOT[0] + 0x800)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for n, b in BUILDERS:
            B[n] = va
            blob = b(va)
            blobs.append(("cave_" + n, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def interior_jumps(d, ranges):
    """Every branch in AoWTCPCK's CODE whose target is strictly inside one of `ranges`."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    lo, hi = 0x00401000, 0x00401000 + 0x65BAC
    o = P.va2off(bytearray(d), lo)
    bad = []
    for ins in md.disasm(bytes(d[o:o + (hi - lo)]), lo):
        if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            for a, b in ranges:
                if a < t < b and not (a <= ins.address < b):
                    bad.append((ins.address, t))
    return bad


def rng_sites(blobs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    return tuple(i.address for _n, va, blob in blobs for i in md.disasm(blob, va)
                 if i.mnemonic == "call" and i.op_str == "%#x" % RANDOM)


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    hooks = []
    for name, (va, van, kind) in SITES.items():
        van = bytes.fromhex(van)
        op = 0xE8 if kind == "call" else 0xE9
        new = bytes([op]) + struct.pack("<i", B[name] - (va + 5)) + b"\x90" * (len(van) - 5)
        hooks.append((va, van, new))
    hooks.append((SPELLTYPES + WOTW, b"\x00", bytes([CLASS_GEYSER])))
    bad = interior_jumps(d, [(va, va + len(bytes.fromhex(v))) for va, v, _k in SITES.values()])
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    print("  interior sweep: no branch lands inside a displaced range")
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in B.items()))
    if rng_sites(blobs) != RNG_SITES:
        sys.exit("ABORT: RNG_SITES are stale: %s" % " ".join("%08X" % a for a in rng_sites(blobs)))
    run("build_wotw_tc -- Weight of the World (AoWTCPCK)", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
