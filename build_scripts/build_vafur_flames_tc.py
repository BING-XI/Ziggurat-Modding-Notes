#!/usr/bin/env python
r"""
build_vafur_flames_tc.py -- the AoWTCPCK half of Vafur Flames (spell 97), a Fire tier-2 battle spell:
a jagged wall of fire, one hex thick, whose flames strike with a 10/5 fire strike.  AoWEPACK half:
build_vafur_flames.py.  Data: build_vafur_flames_pfs.py.  Owner's design 2026-10-29.

THE CLASS  SpellTypes[97] = 0x1E, Geyser's: the burst drawn at the target hex, then the landing.
  N   0x0040F227  NextStrike's common exit `mov eax,[ebp-4] / mov eax,[eax+0x10]` (6 B) -> jmp cave_ns:
      for a cast ([TE+0x14] = 0x34) of spell 97, [fx+0x2C] = nil, so Geyser's class strikes no unit and
      knocks nothing back; then the 6 bytes.  Independent of the per-id aliases before it
      (build_wotw_tc.py 0x40F0C9, build_deathfire_tc.py 0x40F0E3, build_lethe_tc.py 0x40F0E9).
  L   0x0040C6ED  the landing dispatch `cmp eax,0x2c / jg 0x40C712` (5 B; EAX = [fx+0x14]) -> jmp
      cave_land.  build_satchels_tc.py's cave at 0x40C6E7 resumes here.  For kind 0x34, class 0x1E,
      spell 97: vland, then the loop's next effect (0x40CAF2).  Otherwise the 5 bytes.
  S   0x0042E226  Geyser's spray loop entry `test eax,eax / jle 0x42E3A3` (8 B) -> jmp cave_spray: no
      spray particles for 97 (fire, no debris).  build_wotw_tc.py's count cave resumes before it.
THE WALL (vland, at the landing: TE [ebp-4], target hex [ebp-0x28] / [ebp-0x2C])
  A valid hex is open ground: in the map, the Walking move table (AoWEPACK MovePointTables + 0x100,
  through the rebase delta of the CreateMovePointTable import cell, as build_wotw_field_tc.py reads it)
  at its terrain and overlay is >= 0, and it holds no TCombatFire, no standing wall (TCityWall with HP
  > 0), no gate or structure, obstacle, workshop, town hall, house or main structure.  A unit on it
  does not matter.  The line starts at the target hex (on an invalid one nothing forms) and grows
  like Surtr's Chasm: each new hex a valid neighbour of the last that is not adjacent to an earlier
  one, picked by a synced draw, up to 6 hexes; it stops early when no candidate is left.
  Each hex gets a TCombatFire (TCombatFire.Create + THSMap.PlaceHX, CreateFire's own sequence) with
  three bytes in its alignment padding: +0x19 'V' (ours), +0x1A its age, +0x1B the caster's combat
  id ([obj+0xC]).  Activate sets +0x14 (the lighter: the caster's side) and the skip flag +0x18.
  FORM: every live, enabled unit on the line is struck once, friend and foe; the caster last.
  Then the spell's sound cue 1.
THE FLAMES (TCombatFire with +0x19 = 'V')
  T   0x004071EC  TCombatFire.MsgProc's `call NewTurn` (turn start, message 0x20021001) -> call
      cave_nt: vanilla fires go on to NewTurn (burn the hex, spread, die); ours go to vnt.  vnt: the
      first message after the cast is skipped (vanilla's +0x18); otherwise only on the caster's
      side's turn: age + 1; from age 3 (two full rounds after the cast) a synced 25 % roll puts the
      flame out (TObject.Free, as vanilla's NewTurn ends); a flame that stays strikes the unit on its
      hex.  Ours never spread, never burn walls or trees: no terrain change.
  D   0x00407255  TCombatFire.Show's `mov edx,0x3c` (5 B) -> call cave_seq: ours draw combat image
      sequence 23 (EFFECTS\FIRESM.ILB) or 24 (FIRELG.ILB) by the parity of x + y -- the art of the
      world map's TFire, Fire Barrier's flames.  Vanilla's 60 is FIRESM2.ILB.  (Indices read from
      the 71-sequence list at the end of Release.hss; TCOozeHS's 25-27 and THouse's 50 match it.)
  E   0x00408D56, 0x00408E9F  TCombatMoveTE.DefaultMove's two `call ExecuteDefaultMove` (the step
      into the next hex) -> call cave_step: after the step, a live mover whose new hex holds one of
      our flames is struck (blood and the damage-type icons, no hurt pose mid-walk); if the strike
      kills it the step reports 3, the end of the move, as a free swing's kill does.  Crossing costs
      nothing extra.  The battle AI's path planning prices our flames as it prices vanilla fire
      (TCombatFire.CanMoveOn: +20, +10 with Fire Protection, 0 with Fire Immunity), untouched.
THE STRIKE (strike): System.RandSeed := TAoWHSMap.Random(map, $FFFFFF), the spell's CreateCA (VMT
  +0x78: ATK 10, DMG 5, fire, build_vafur_flames.py) with the caster (found by its combat id for the
  turn-start and entry strikes), the damage-type icons, the hurt pose and blood, TCombat.
  ExecuteCombatAction, free.  Fire Immunity, Fire Protection and the fire strike's Burning roll are
  the generic damage handlers'.
TARGET  build_spell_unit_target.py's pred calls `valid` (pinned at 0x00449000) for spell 97 on an
  empty hex, so the cursor and the click refuse a hex that is not open ground.
AI  never cast: TCAI.CheckUnit sends 97 to its default case and build_vafur_flames.py's value
  overrides are 0 (Mist's recipe); auto-resolve queues nothing for it.
Ooze puts our flames out as it puts out vanilla fire (build_ooze_extinguish.py frees every
TCombatFire on its hex).
RNG: P1 SYNCED DRAW: the line's picks and the extinguish roll (srand: TAoWHSMap.Random with
System.RandSeed saved and restored, 12-re-toolchain.md section 4.4); each strike re-anchors the raw
stream from one synced draw first (the bridge, the 0x31003 unit handler's idiom).  Sites: RNG_SITES.
Slot 0x00449000-0x0044AFFF, exclusive.  PIC.  Surgical --undo.

Unproven in game: the placement of the FIRESM / FIRELG frames on a combat hex (they are the world
map's frames on the combat list's own offsets), and a flame's strike on a unit that dies mid-walk.

    python build_scripts/build_vafur_flames_tc.py            dry run + state
    python build_scripts/build_vafur_flames_tc.py --apply
    python build_scripts/build_vafur_flames_tc.py --undo
    python build_scripts/build_vafur_flames_tc.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, run
from piccave import pic

VAFUR, MARK, MAX_LEN, OUT_AGE, OUT_PCT = 97, 0x56, 6, 3, 25
SEQ_SMALL = 23                               # +1 = FIRELG
SLOT = (0x00449000, 0x0044B000)
SPELLTYPES, CLASS_GEYSER, KIND_CAST = 0x004672F4, 0x1E, 0x34
# AoWTCPCK thunks and code (preferred VAs)
GETMAPLEVEL, GETFIELD, GETSPELL, SFXPLAY, RANDOM = 0x00401E64, 0x00401E54, 0x004029B4, 0x004022F4, 0x0040298C
EXEC_CA, DAMAGE_ICONS, SET_ACTION, HIT_BLOOD = 0x0040259C, 0x00407C30, 0x004236E0, 0x0040992C
HXTOHP, CENTERHN, DHXTORAD, PLACEHX, FREE = 0x004022BC, 0x004022AC, 0x004022A4, 0x00402264, 0x00401050
GETCOUNT, GETOBJECTS = 0x0040262C, 0x00402634
FIRE_CREATE, FIRE_CLASS, FIRE_NEWTURN = 0x00406F68, 0x00406AE4, 0x004070CC
EXEC_DEFMOVE = 0x00408278
# data (reached PIC)
VAR_CONTAINER, VAR_COMBATMAP, VAR_HSSET, VAR_MAP, VAR_SEED = 0x00469420, 0x0046C064, 0x0046E8D0, 0x0046E8D4, 0x0046DC08
CELL_CMPT, CMPT_PREF, EP_WALKTABLE = 0x0046E590, 0x5577FDC4, 0x558EA040 + 0x100
# class ids
CID_UNIT, CID_FIRE, CID_WALL = 0x220104, 0x22054A, 0x220504
BLOCKERS = (0x220506, 0x22052A, 0x220508, 0x220510, 0x220512, 0x22051C)   # gate/structure, obstacle,
#                                       workshop, town hall, house, main structure
L_W, L_H = 0x0C, 0x10
# resume addresses
N_RESUME, L_DONE, L_GT, L_RESUME = 0x0040F22D, 0x0040CAF2, 0x0040C712, 0x0040C6F2
S_SKIP, S_RESUME = 0x0042E3A3, 0x0042E22E

SITES = {   # name: (va, vanilla bytes, kind, host function range for the interior check)
    "ns":    (0x0040F227, "8b45fc8b4010", "jmp", (0x0040D290, 0x0040F4B0)),
    "land":  (0x0040C6ED, "83f82c7f20", "jmp", (0x0040B2F8, 0x0040D290)),
    "spray": (0x0042E226, "85c00f8e75010000", "jmp", (0x00429E78, 0x0042F978)),
    "nt":    (0x004071EC, "e8dbfeffff", "call", None),
    "seq":   (0x00407255, "ba3c000000", "call", None),
    "step1": (0x00408D56, "e81df5ffff", "call", None),
    "step2": (0x00408E9F, "e8d4f3ffff", "call", None),
}
CAVE_OF = {"ns": "ns", "land": "land", "spray": "spray", "nt": "nt", "seq": "seq",
           "step1": "step", "step2": "step"}
B = {}


def b_valid(va):
    """eax = a combat map field -> eax 1 when it is open ground (see the docstring).  Pinned at
    SLOT[0]: build_spell_unit_target.py's pred calls it and first checks its first byte (0x55)."""
    blockers = "".join(f"""
        mov  eax, esi
        mov  edx, {cid:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jne  va_out""" for cid in BLOCKERS)
    src = f"""
        push ebp
        mov  ebp, esp
        push ebx
        push esi
        push edi
        mov  esi, eax
        xor  edi, edi
        {{ANC}}
        test esi, esi
        je   va_out
        mov  eax, dword ptr [ebx + {{CELL}}]
        sub  eax, {CMPT_PREF:#x}
        movsx edx, byte ptr [esi + 0x14]
        shl  edx, 4
        movsx ecx, byte ptr [esi + 0x15]
        add  edx, ecx
        movsx eax, byte ptr [eax + edx + {EP_WALKTABLE:#x}]
        test eax, eax
        js   va_out
        mov  eax, esi
        mov  edx, {CID_FIRE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jne  va_out
        mov  eax, esi
        mov  edx, {CID_WALL:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je   va_nowall
        cmp  dword ptr [eax + 0x20], 0
        jg   va_out
    va_nowall:
        {blockers}
        mov  edi, 1
    va_out:
        mov  eax, edi
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret
    """
    return pic(src, va, "ebx", {"CELL": CELL_CMPT})


def b_fieldxy(va):
    """eax = x, edx = y -> eax = the combat field, or 0 off the level.  Keeps ebx/esi/edi."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        {{ANC}}
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
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER})


def b_unit_on(va):
    """eax = a field (or 0) -> eax = its live, enabled combat unit, or 0."""
    return asm(f"""
        test eax, eax
        je   u_no
        mov  edx, {CID_UNIT:#x}
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
    """, va)


def b_findobj(va):
    """eax = a combat id -> eax = the TCombatObject with that id ([obj+0xC]), or 0."""
    src = f"""
        push ebx
        push esi
        push edi
        movzx edi, al
        {{ANC}}
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xe4]
        test eax, eax
        je   o_no
        mov  ebx, dword ptr [eax + 0xc]
        test ebx, ebx
        je   o_no
        mov  eax, ebx
        call {GETCOUNT:#x}
        mov  esi, eax
    o_loop:
        dec  esi
        js   o_no
        mov  edx, esi
        mov  eax, ebx
        call {GETOBJECTS:#x}
        test eax, eax
        je   o_loop
        movzx ecx, byte ptr [eax + 0xc]
        cmp  ecx, edi
        jne  o_loop
        jmp  o_out
    o_no:
        xor  eax, eax
    o_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER})


def b_srand(va):
    """edx = n -> eax = a synced draw 0..n-1 (TAoWHSMap.Random); System.RandSeed saved and restored."""
    src = f"""
        push ebx
        push esi
        {{ANC}}
        mov  esi, dword ptr [ebx + {{SEED}}]
        push dword ptr [esi]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax]
        call {RANDOM:#x}
        pop  dword ptr [esi]
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"SEED": VAR_SEED, "MAP": VAR_MAP})


def b_strike(va):
    """eax = the struck unit, edx = the caster, ecx = the unit's field, [esp+4] = 1 for the hurt pose;
    ret 4.  WotW's l_strike as a function: reseed, CreateCA, icons, pose, blood, execute, free."""
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x1c
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        mov  dword ptr [ebp - 4], ecx
        {{ANC}}
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {VAFUR}
        call {GETSPELL:#x}
        test eax, eax
        je   s_out
        mov  dword ptr [ebp - 8], eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax]
        mov  edx, 0xffffff
        call {RANDOM:#x}
        mov  edx, dword ptr [ebx + {{SEED}}]
        mov  dword ptr [edx], eax
        mov  eax, dword ptr [ebp - 8]
        mov  ecx, dword ptr [eax]
        mov  ecx, dword ptr [ecx + 0x78]
        mov  dword ptr [ebp - 0xc], ecx
        push 0
        mov  ecx, esi
        mov  edx, edi
        call dword ptr [ebp - 0xc]
        mov  dword ptr [ebp - 0x10], eax
        lea  eax, [ebp - 0x18]
        push eax
        mov  eax, dword ptr [ebp - 4]
        movsx edx, byte ptr [eax + 0x11]
        movsx eax, byte ptr [eax + 0x10]
        lea  ecx, [ebp - 0x14]
        call {HXTOHP:#x}
        mov  eax, dword ptr [ebp - 0x10]
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
        mov  eax, dword ptr [ebp - 0x10]
        mov  cx, word ptr [eax + 0x13]
        test cx, cx
        je   s_hurt
        push 1
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {DAMAGE_ICONS:#x}
    s_hurt:
        mov  eax, dword ptr [ebp - 0x10]
        movzx eax, byte ptr [eax + 0x10]
        mov  dword ptr [ebp - 0x1c], eax
        test eax, eax
        je   s_exec
        cmp  byte ptr [ebp + 8], 0
        je   s_blood
        mov  eax, dword ptr [esi + 0x60]
        test eax, eax
        je   s_blood
        mov  dl, 4
        call {SET_ACTION:#x}
    s_blood:
        mov  eax, esi
        mov  edx, dword ptr [ebp - 0x1c]
        call {HIT_BLOOD:#x}
    s_exec:
        mov  edx, dword ptr [ebp - 0x10]
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xe4]
        call {EXEC_CA:#x}
        mov  eax, dword ptr [ebp - 0x10]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    s_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  4
    """
    return pic(src, va, "ebx", {"HSSET": VAR_HSSET, "MAP": VAR_MAP, "SEED": VAR_SEED,
                                "CONTAINER": VAR_CONTAINER})


def b_place(va):
    """eax = x, edx = y, ecx = the caster's combat id: one of our flames on the hex (CreateFire's
    Create + PlaceHX; freed again if PlaceHX refuses)."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        push ecx
        {{ANC}}
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{FIRECLS}}]
        call {FIRE_CREATE:#x}
        pop  ecx
        mov  byte ptr [eax + 0x19], {MARK:#x}
        mov  byte ptr [eax + 0x1a], 0
        mov  byte ptr [eax + 0x1b], cl
        push eax
        push edi
        push 0
        mov  edx, eax
        mov  ecx, esi
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        call {PLACEHX:#x}
        pop  edx
        test al, al
        jne  p_out
        mov  eax, edx
        call {FREE:#x}
    p_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"FIRECLS": FIRE_CLASS, "CONTAINER": VAR_CONTAINER})


# vland's frame: -4 TE, -8 count, -0xC candidates, -0x10 n, -0x14 j, -0x18/-0x1C CenterHN's x/y,
# -0x20 caster, -0x24 the caster's field when it stands on the line, -0x28 the caster's id;
# line x/y at -0x48/-0x60 + 4i, candidate x/y at -0x78/-0x90 + 4i (6 each).
LX, LY, NX, NY = 0x48, 0x60, 0x78, 0x90


def b_vland(va):
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x90
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - {LX:#x}], edx
        mov  dword ptr [ebp - {LY:#x}], ecx
        {{ANC}}
        mov  eax, edx
        mov  edx, ecx
        call {B['fieldxy']:#x}
        test eax, eax
        je   v_out
        call {B['valid']:#x}
        test al, al
        je   v_out
        mov  dword ptr [ebp - 8], 1
    v_grow:
        cmp  dword ptr [ebp - 8], {MAX_LEN}
        jge  v_place
        mov  dword ptr [ebp - 0xc], 0
        mov  dword ptr [ebp - 0x10], 1
    v_nb:
        mov  ecx, dword ptr [ebp - 8]
        dec  ecx
        lea  eax, [ebp - 0x18]
        push eax
        lea  eax, [ebp - 0x1c]
        push eax
        mov  edx, dword ptr [ebp + ecx*4 - {LY:#x}]
        mov  eax, dword ptr [ebp + ecx*4 - {LX:#x}]
        mov  ecx, dword ptr [ebp - 0x10]
        call {CENTERHN:#x}
        mov  eax, dword ptr [ebp - 0x18]
        mov  edx, dword ptr [ebp - 0x1c]
        call {B['fieldxy']:#x}
        test eax, eax
        je   v_nbnext
        call {B['valid']:#x}
        test al, al
        je   v_nbnext
        mov  dword ptr [ebp - 0x14], 0
    v_j:
        mov  ecx, dword ptr [ebp - 0x14]
        push dword ptr [ebp + ecx*4 - {LY:#x}]
        mov  ecx, dword ptr [ebp + ecx*4 - {LX:#x}]
        mov  edx, dword ptr [ebp - 0x1c]
        mov  eax, dword ptr [ebp - 0x18]
        call {DHXTORAD:#x}
        test eax, eax
        je   v_nbnext
        mov  ecx, dword ptr [ebp - 0x14]
        inc  ecx
        cmp  ecx, dword ptr [ebp - 8]
        je   v_jnext
        cmp  eax, 1
        jle  v_nbnext
    v_jnext:
        inc  dword ptr [ebp - 0x14]
        mov  eax, dword ptr [ebp - 0x14]
        cmp  eax, dword ptr [ebp - 8]
        jl   v_j
        mov  ecx, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [ebp - 0x18]
        mov  dword ptr [ebp + ecx*4 - {NX:#x}], eax
        mov  eax, dword ptr [ebp - 0x1c]
        mov  dword ptr [ebp + ecx*4 - {NY:#x}], eax
        inc  dword ptr [ebp - 0xc]
    v_nbnext:
        inc  dword ptr [ebp - 0x10]
        cmp  dword ptr [ebp - 0x10], 7
        jl   v_nb
        mov  edx, dword ptr [ebp - 0xc]
        test edx, edx
        je   v_place
        call {B['srand']:#x}
        mov  ecx, dword ptr [ebp - 8]
        mov  edx, dword ptr [ebp + eax*4 - {NX:#x}]
        mov  dword ptr [ebp + ecx*4 - {LX:#x}], edx
        mov  edx, dword ptr [ebp + eax*4 - {NY:#x}]
        mov  dword ptr [ebp + ecx*4 - {LY:#x}], edx
        inc  dword ptr [ebp - 8]
        jmp  v_grow
    v_place:
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        mov  dword ptr [ebp - 0x20], eax
        movzx eax, byte ptr [eax + 0xc]
        mov  dword ptr [ebp - 0x28], eax
        xor  esi, esi
    v_pl:
        mov  ecx, dword ptr [ebp - 0x28]
        mov  edx, dword ptr [ebp + esi*4 - {LY:#x}]
        mov  eax, dword ptr [ebp + esi*4 - {LX:#x}]
        call {B['place']:#x}
        inc  esi
        cmp  esi, dword ptr [ebp - 8]
        jl   v_pl
        mov  dword ptr [ebp - 0x24], 0
        xor  esi, esi
    v_st:
        mov  edx, dword ptr [ebp + esi*4 - {LY:#x}]
        mov  eax, dword ptr [ebp + esi*4 - {LX:#x}]
        call {B['fieldxy']:#x}
        mov  edi, eax
        call {B['unit_on']:#x}
        test eax, eax
        je   v_stnext
        cmp  eax, dword ptr [ebp - 0x20]
        jne  v_hit
        mov  dword ptr [ebp - 0x24], edi
        jmp  v_stnext
    v_hit:
        push 1
        mov  ecx, edi
        mov  edx, dword ptr [ebp - 0x20]
        call {B['strike']:#x}
    v_stnext:
        inc  esi
        cmp  esi, dword ptr [ebp - 8]
        jl   v_st
        mov  eax, dword ptr [ebp - 0x24]
        call {B['unit_on']:#x}
        test eax, eax
        je   v_snd
        cmp  eax, dword ptr [ebp - 0x20]
        jne  v_snd
        push 1
        mov  ecx, dword ptr [ebp - 0x24]
        mov  edx, eax
        call {B['strike']:#x}
    v_snd:
        mov  eax, dword ptr [ebx + {{COMBATMAP}}]
        test eax, eax
        je   v_out
        cmp  byte ptr [eax + 0x129], 0
        je   v_out
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {VAFUR}
        call {GETSPELL:#x}
        test eax, eax
        je   v_out
        mov  eax, dword ptr [eax + 0x28]
        mov  edx, 1
        call {SFXPLAY:#x}
    v_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """
    return pic(src, va, "ebx", {"COMBATMAP": VAR_COMBATMAP, "HSSET": VAR_HSSET})


def b_vnt(va):
    """Our flame's turn start (eax = the flame).  Reached by a jmp from cave_nt; returns to MsgProc,
    which touches the flame no more (vanilla's NewTurn may free it the same way)."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        {{ANC}}
        cmp  byte ptr [esi + 0x18], 0
        je   t_go
        mov  byte ptr [esi + 0x18], 0
        jmp  t_out
    t_go:
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        movsx eax, byte ptr [eax + 0xed]
        cmp  eax, dword ptr [esi + 0x14]
        jne  t_out
        cmp  byte ptr [esi + 0x1a], 0xff
        je   t_aged
        inc  byte ptr [esi + 0x1a]
    t_aged:
        cmp  byte ptr [esi + 0x1a], {OUT_AGE}
        jb   t_burn
        mov  edx, 100
        call {B['srand']:#x}
        cmp  eax, {OUT_PCT}
        jge  t_burn
        mov  eax, esi
        call {FREE:#x}
        jmp  t_out
    t_burn:
        mov  edi, dword ptr [esi + 4]
        mov  eax, edi
        call {B['unit_on']:#x}
        test eax, eax
        je   t_out
        push eax
        movzx eax, byte ptr [esi + 0x1b]
        call {B['findobj']:#x}
        mov  edx, eax
        pop  eax
        test edx, edx
        je   t_out
        push 1
        mov  ecx, edi
        call {B['strike']:#x}
    t_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER})


def b_ns(va):
    """N: only EAX is the 6 bytes' output; EDX is kept."""
    return asm(f"""
        push edx
        mov  eax, dword ptr [ebp - 4]
        cmp  dword ptr [eax + 0x14], {KIND_CAST:#x}
        jne  n_go
        cmp  dword ptr [eax + 0x18], {VAFUR}
        jne  n_go
        mov  edx, dword ptr [ebp - 0x10]
        test edx, edx
        je   n_go
        mov  dword ptr [edx + 0x2c], 0
    n_go:
        pop  edx
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        jmp  {N_RESUME:#x}
    """, va)


def b_land(va):
    """L: EAX = [fx+0x14] on entry; every register but EAX is kept on the vanilla path."""
    return asm(f"""
        cmp  eax, {KIND_CAST:#x}
        jne  l_van
        push ecx
        mov  ecx, dword ptr [ebp - 0x20]
        cmp  dword ptr [ecx + 0x18], {VAFUR}
        jne  l_pop
        cmp  byte ptr [ecx + 0x34], {CLASS_GEYSER:#x}
        jne  l_pop
        pop  ecx
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 0x28]
        mov  ecx, dword ptr [ebp - 0x2c]
        call {B['vland']:#x}
        jmp  {L_DONE:#x}
    l_pop:
        pop  ecx
    l_van:
        cmp  eax, 0x2c
        jg   {L_GT:#x}
        jmp  {L_RESUME:#x}
    """, va)


def b_spray(va):
    """S: EAX = the spray count minus 1; [ebp-8] = the effect.  ECX is kept."""
    return asm(f"""
        push ecx
        mov  ecx, dword ptr [ebp - 8]
        cmp  dword ptr [ecx + 0x14], {KIND_CAST:#x}
        jne  s_go
        cmp  dword ptr [ecx + 0x18], {VAFUR}
        jne  s_go
        pop  ecx
        jmp  {S_SKIP:#x}
    s_go:
        pop  ecx
        test eax, eax
        jle  {S_SKIP:#x}
        jmp  {S_RESUME:#x}
    """, va)


def b_nt(va):
    return asm(f"""
        cmp  byte ptr [eax + 0x19], {MARK:#x}
        jne  {FIRE_NEWTURN:#x}
        jmp  {B['vnt']:#x}
    """, va)


def b_seq(va):
    """Replaces Show's `mov edx,0x3c` (EAX = the sequence list, kept; [ebp-4] = the fire)."""
    return asm(f"""
        mov  edx, 0x3c
        push eax
        mov  eax, dword ptr [ebp - 4]
        cmp  byte ptr [eax + 0x19], {MARK:#x}
        jne  q_out
        mov  eax, dword ptr [eax + 4]
        test eax, eax
        je   q_out
        movsx edx, byte ptr [eax + 0x10]
        movsx eax, byte ptr [eax + 0x11]
        add  edx, eax
        and  edx, 1
        add  edx, {SEQ_SMALL}
    q_out:
        pop  eax
        ret
    """, va)


def b_step(va):
    """Replaces DefaultMove's `call ExecuteDefaultMove` (EAX = the move TE; AL = the step's result)."""
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        call {EXEC_DEFMOVE:#x}
        movzx edi, al
        mov  ebx, dword ptr [esi + 0x1c]
        test ebx, ebx
        je   st_out
        mov  eax, dword ptr [ebx + 0x60]
        test eax, eax
        je   st_out
        mov  esi, dword ptr [eax + 4]
        test esi, esi
        je   st_out
        mov  eax, esi
        mov  edx, {CID_FIRE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je   st_out
        cmp  byte ptr [eax + 0x19], {MARK:#x}
        jne  st_out
        test byte ptr [ebx + 0x47], 1
        jne  st_out
        push eax
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        pop  eax
        je   st_out
        movzx eax, byte ptr [eax + 0x1b]
        call {B['findobj']:#x}
        test eax, eax
        je   st_out
        push 0
        mov  ecx, esi
        mov  edx, eax
        mov  eax, ebx
        call {B['strike']:#x}
        test byte ptr [ebx + 0x47], 1
        jne  st_dead
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        jne  st_out
    st_dead:
        mov  edi, 3
    st_out:
        mov  eax, edi
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


BUILDERS = [("valid", b_valid), ("fieldxy", b_fieldxy), ("unit_on", b_unit_on), ("findobj", b_findobj),
            ("srand", b_srand), ("strike", b_strike), ("place", b_place), ("vland", b_vland),
            ("vnt", b_vnt), ("ns", b_ns), ("land", b_land), ("spray", b_spray), ("nt", b_nt),
            ("seq", b_seq), ("step", b_step)]
VALID_PIN = SLOT[0]
RNG_SITES = {"srand (line picks, extinguish)": 0x004491C8, "strike (reseed per strike)": 0x00449226}


def layout():
    for n, _b in BUILDERS:
        B.setdefault(n, SLOT[0] + 0x1000)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for n, b in BUILDERS:
            B[n] = va
            blob = b(va)
            blobs.append(("cave_" + n, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    assert B["valid"] == VALID_PIN and blobs[0][2][0] == 0x55, "valid is not pinned at the slot start"
    return blobs


def rng_sites(blobs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    return tuple(i.address for _n, va, blob in blobs for i in md.disasm(blob, va)
                 if i.mnemonic == "call" and i.op_str == "%#x" % RANDOM)


def main():
    blobs = layout()
    found = rng_sites(blobs)
    if found != tuple(RNG_SITES.values()):
        sys.exit("ABORT: RNG_SITES are stale: %s" % " ".join("%08X" % a for a in found))
    hooks, interior = [], []
    for name, (va, van, kind, fn) in SITES.items():
        van = bytes.fromhex(van)
        op = 0xE8 if kind == "call" else 0xE9
        new = bytes([op]) + struct.pack("<i", B[CAVE_OF[name]] - (va + 5)) + b"\x90" * (len(van) - 5)
        hooks.append((va, van, new))
        if fn:
            interior.append((va, va + len(van), fn[0], fn[1]))
    hooks.append((SPELLTYPES + VAFUR, b"\x00", bytes([CLASS_GEYSER])))
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in B.items()))
    print("  RNG sites (synced): " + ", ".join("%08X" % a for a in RNG_SITES.values()))
    run("build_vafur_flames_tc -- Vafur Flames (AoWTCPCK)", hooks, blobs, SLOT, interior)


if __name__ == "__main__":
    main()
