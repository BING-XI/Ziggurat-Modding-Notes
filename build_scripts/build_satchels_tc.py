#!/usr/bin/env python
r"""
build_satchels_tc.py -- the AoWTCPCK half of Dwarven Satchels: Throw Explosive Flask (ability 0x4F)
in manual combat.  DLL half (spell 84, the enchantment 0x4E, the attack 0x4F, auto-combat):
build_satchels.py.  Owner's design 2026-10-25 (05-spells-added.md, "Earth/Fire").

THE PLAYER  arms the flask from the unit's ability list (or Q), then clicks a hex within 4: an enemy
  or an empty hex.  Nothing arms an attack by itself (the only callers of SelectAbility are the
  panel, Q, the spellbook, the right-click cancel and the category-0 disarm), and the armed attack
  already fires at an empty hex: CalculateRangedPath 0x0041ED3B tests terrain 0xF, column 0, full
  moves and the range band, never a unit, and AbRangedTC 0x00423860 takes a hex.  F's combat info
  says "enemy" (flag 2), so a click on one of your own units selects it instead.
THE THROW  AbilTypes[0x4F] = 2 (Hurl Boulder's category; the relocated table 0x469440 and, so that
  build_abiltypes_relocate.py still reads its head as populated, the dead original 0x467248).
  The category picks the flight sprite: TfxHS's show (0x0042F978) draws a category-1 missile
  (arrows, bolts, javelins) from image slot [fx+0x20], its direction, and a category-2 one from
  slot 0.  The flask's record has slot 0 only, so as category 1 it flew unseen; the AI and the
  path code treat 1 and 2 alike.
  MakeAbilPath gives 0x4F Hurl Boulder's lob (0x00427298, arc 100).  NextStrike already puts the
  unit on the target hex in [fx+0x2C] (nil on an empty hex), and its interception loop (synced
  Random(100) per path point) truncates the path at a unit standing in the way and makes it the
  target, so the path's last point is always where the flask bursts.
THE SCATTER (owner 2026-10-25, after Myth's satchel charges: the flask is "unwieldy")  At the head
  of NextStrike's missile branch (S 0x0040ED2D), before MakeAbilPath and the target lookup read the
  TE's target hex [TE+0x20]/[TE+0x22], one synced map Random(10): 0-3 keep the aimed hex, 4-9 move
  it to neighbour HN 1-6.  A neighbour that is off the level, in column 0, Border terrain (0xF) or
  the thrower's own hex (cave_valid) keeps the aimed hex, so its tenth goes to the aimed hex.
  Execute rewrites the same two words for other attack kinds (0x0040B57D), and nothing after
  NextStrike reads them for a missile.
THE AIMING NUMBERS  The first click on a hex computes the ranged path and the preview routine
  0x00427EE4 draws it, with vanilla's interception chances as numbers (font AoWEngine+0x68,
  ImageLibraryFont.SetColor 0 / SetTextCentered at hex pixel +16/+12, each on the round sign,
  image 1 of the preview's library [+0xC], at +5/+5).  P 0x00428879 (its exit, still inside its
  try block): with the flask armed and a path drawn, the same sign and font show each landing
  chance on the aimed hex ([ctrl+0x24]/[ctrl+0x28]) and its valid neighbours: 10 on each, 40 plus
  10 per invalid neighbour on the aimed hex.  On a hex that already carries an interception sign,
  ours sits 12 px further right and down.
THE BURST  TCAbRangedTE.Execute's landing:
  - L1 0x0040C31F: a landed 0x4F goes to 0x0040C5A4, skipping the single-target CA (and its synced
    reseed at 0x0040C351); the landing hex is then computed into [ebp-0x28]/[ebp-0x2C] as usual,
    there is no CA in [fx+0x30], so control reaches the per-id dispatch.
  - L2 0x0040C6E7 (the dispatch head): for 0x4F, every standing unit on the landing hex and its six
    neighbours (CenterHNtoHX HN 0..6, each checked against the level's width and height; the unit
    is the field's 0x220104 HS, its object at +0x1C) is struck as vanilla strikes a missile's
    target (0x0040C351..0x0040C59D, 0x0040C636): a synced reseed of RandSeed from the map Random,
    CreateRangedAttackCA(F, thrower, unit), the damage-type icons (0x00407C30), on damage the
    flinch and blood (SetAction 4, 0x0040992C), TCombat.ExecuteCombatAction, the CA freed.  One
    strike each, 10 ATK vs DEF, 15 fire, own units and the thrower included; terrain, walls and
    structures are not touched.  (The first build sent Flame Throwing's message 0x31012 to the
    seven fields instead; in the owner's first test only the target was hurt, and the struck units
    showed no damage, so the burst could not be seen working either way.)
  - Then, the thrower still standing, E (0x4E) is removed from its unit (shooter VMT +0xB8, then
    GetAbility(0x4E) VMT +0xD4); E's Remove clears F (build_satchels.py).  Once per landed flask,
    so once per throw.  The TE deselects the shooter at its end, and the next selection rebuilds the
    ability list (CreateTCAbList 0x00423430) without F.
THE AI  TCAI.EvalBattle lists 0x4F by itself (HasAbility, AbilTypes <> 0, combat info flag 2).
  TCAI.CheckUnit's ability ladder (A 0x004175E8) sends 0x4F to cave_ai, Triple Fireball's case from
  the spell ladder (0x00415C98) re-typed for an ability: EvalPath (no wall flag) and EvalArea
  0x00414D14 (walls 0, the thrower's hex counted, own units counted against) at the aimed unit, then
  the same at each of its six neighbours in range, keeping the best centre in [ebp-8]/[ebp-0xC],
  which CheckUnit records and the executor (0x0041AEA2) throws at, empty or not.  Two differences
  from the spell case: the range test passes dHXtoRad 0x004022A4 its coordinates in order (the spell
  case passes (x, y') and (x', y)), and the CheckUnit locals the case uses as scratch ([ebp-0x14],
  -0x18, -0x2C..-0x3C) are restored, so the code after the ladder (0x004176FB) sees only the score
  [ebp-0x58], the value [ebp-0x64] and the centre.  The AI satchels only units without a ranged
  attack (build_satchels.py's cave_vtu).

HOOKS (vanilla bytes asserted; no .reloc under any)
    C1 0x0046948F  AbilTypes[0x4F] 00 -> 02            (relocated table)
    C2 0x00467297  00 -> 02                              (original table, unread since the move)
    M  0x0042723A  sub eax,0x37 / je 0x427261 (5 B) -> jmp cave_arc     0x4F -> 0x427298
    A  0x004175E8  cmp eax,0x3D / jge 0x4175FF (5 B) -> jmp cave_aisel  0x4F -> cave_ai
    L1 0x0040C31F  mov eax,[ebp-0x20] / cmp byte [eax+0xC],0 (7 B) -> jmp cave_land1
    L2 0x0040C6E7  mov eax,[ebp-0x20] / mov eax,[eax+0x14] (6 B) -> jmp cave_land2
    S  0x0040ED2D  mov eax,[ebp-4] / mov eax,[eax+0x10] (6 B) -> jmp cave_scatter
    P  0x00428879  xor eax,eax / pop edx / pop ecx / pop ecx (5 B) -> jmp cave_odds
  None shares a byte with build_flamingskull.py (0x004271FD, 0x004175AD, 0x0040C721),
  build_banejavelin.py (0x0042725C, 0x00417619), build_deathfire_tc.py (0x0040C856, 0x0042827A) or
  build_extrashots.py (0x0040F436), which hook the same routines elsewhere.

Randomness: P1 SYNCED DRAW in S: NextStrike is in AoWTCPCK's SYNC list (its own map Random at
0x0040D9E4 and the interception roll), so the scatter draws TAoWHSMap.Random through the 0x0046E8D4
cell; it is gated on the ability id alone, so every peer draws the same number of times.  P1 again
in L2 (0x0043F130): before each struck unit's CA, RandSeed := map Random(0xFFFFFF), vanilla's own
reseed (0x0040C351), which L1 skips for the flask's single target; the count depends only on which
hexes hold standing units, replicated state.  Auto-combat (build_satchels.py) does not scatter: a
flask landing beside its target still bursts on it.
Slot 0x0043F000-0x0043FBFF, exclusive; the six caves a hook jumps to are pinned (moved from
0x0043CC40 the same day, with the scatter).  PIC: rel32 to in-module code and thunks, call/pop
anchors for the data cells (0x00469420 the combat container, 0x0046E8D0 AoWHSSet, 0x0046E8D4
AoWHSMap, 0x0046E8CC AoWEngine, 0x0046DC08 RandSeed).
Surgical --undo.  Unproven, static checks cannot reach it: the flask's flight sprite (Combat.ILB
112, a placeholder), where the numbers sit on screen, and how the AI weighs a throw against walking
up to melee (its scoring ignores the scatter).

Couplings
  * build_extrashots.py excludes 0x4F from its missile set (one throw).
  * build_battlecast_unitspells.py sets SpellTypes[84] = 7 and build_spell_unit_target.py lists 84,
    so the spell is cast in battle on a unit; neither depends on this script.

    python build_scripts/build_satchels_tc.py            dry run + state
    python build_scripts/build_satchels_tc.py --apply
    python build_scripts/build_satchels_tc.py --undo
    python build_scripts/build_satchels_tc.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, jmp_to, run
from piccave import pic

FLASK, ENCH = 0x4F, 0x4E
CATEGORY = 2                            # Hurl Boulder's: one flight sprite, slot 0
ABILTYPES, ABILTYPES_OLD = 0x00469440, 0x00467248
ABILTYPES_REF = 0x0041EC66
SLOT = (0x0043F000, 0x0043FC00)
# The six caves a hook jumps to keep their addresses, so a re-tune applies over an install.
PINNED = {"cave_arc": 0x0043F000, "cave_aisel": 0x0043F020, "cave_land1": 0x0043F040,
          "cave_land2": 0x0043F080, "cave_valid": 0x0043F260, "cave_scatter": 0x0043F3C0,
          "cave_odds": 0x0043F480, "cave_ai": 0x0043F6A0}
AIMED, EACH = 40, 10                    # landing chances in percent: the aimed hex, each neighbour

# AoWTCPCK code and thunks
EVALPATH, EVALAREA = 0x00414DA8, 0x00414D14
CENTERHN, DHXTORAD = 0x004022AC, 0x004022A4
GETMAPLEVEL, GETFIELD, SENDMSG = 0x00401E64, 0x00401E54, 0x00401DDC
GETABILITY = 0x00402704                 # thunk -> TAbilityControl.GetAbility(eax=[set+0x80], edx=id)
VAR_CONTAINER, VAR_HSSET = 0x00469420, 0x0046E8D0
VAR_MAP, VAR_ENGINE = 0x0046E8D4, 0x0046E8CC   # import cells: AoWE.AoWHSMap, AoWE.AoWEngine
RANDOM = 0x0040298C                     # thunk -> TAoWHSMap.Random(map, n): synced
XYZ_COUNT, XYZ_GET, LIST_GET = 0x00402DFC, 0x00402DF4, 0x0040153C
HPTOHX, HXTOHP = 0x004022C4, 0x004022BC
GET_TCU = 0x0041D2E8                    # the move control's selected unit ([+0x34] the armed id)
INTTOSTR = 0x00401664
FONT_COLOUR, FONT_TEXT = 0x004016AC, 0x004016B4   # ImageLibraryFont.SetColor / SetTextCentered
LIB_IMAGE = 0x004016F4                  # image library -> image n (drawn by its VMT +0x84)
SIGN, SIGN_DX = 1, 5                    # the preview's round sign, at hex pixel +5/+5 (vanilla's)
TEXT_DX, TEXT_DY = 0x10, 0xC            # the number on it, at +16/+12 (vanilla's)
SHIFT = 0xC                             # both moved by this on a hex that has an interception sign
L_W, L_H = 0x0C, 0x10                   # TMapLevel width / height
UNIT_HS = 0x220104                      # a field's unit HS (field VMT +0x80), its object at +0x1C
VAR_SEED = 0x0046DC08                   # import cell: System.RandSeed
CREATE_RA_CA = 0x00402874               # thunk -> CreateRangedAttackCA(eax=ab, edx=shooter, ecx=target, [cover])
EXEC_CA = 0x0040259C                    # thunk -> TCombat.ExecuteCombatAction(eax=[map+0xE4], edx=CA)
DAMAGE_ICONS, SET_ACTION, HIT_BLOOD = 0x00407C30, 0x004236E0, 0x0040992C
SLOT_REMOVE = 0xD4

SITES = {   # name: (va, vanilla bytes, function lo, hi)
    "M":  (0x0042723A, bytes.fromhex("83e8377422"), 0x004271EC, 0x00427626),
    "A":  (0x004175E8, bytes.fromhex("83f83d7d12"), 0x004152A8, 0x00418170),
    "L1": (0x0040C31F, bytes.fromhex("8b45e080780c00"), 0x0040B2F8, 0x0040CB00),
    "L2": (0x0040C6E7, bytes.fromhex("8b45e08b4014"), 0x0040B2F8, 0x0040CB00),
    "S":  (0x0040ED2D, bytes.fromhex("8b45fc8b4010"), 0x0040D290, 0x0040F4B0),
    "P":  (0x00428879, bytes.fromhex("33c05a5959"), 0x00427EE4, 0x004288A0),
}
M_LOB, M_ARC50, M_NEXT = 0x00427298, 0x00427261, 0x0042723F
A_GE, A_NEXT, A_DONE = 0x004175FF, 0x004175ED, 0x004176FB
L1_LANDED, L1_NEXT = 0x0040C5A4, 0x0040C32C
L2_NEXT, LANDING_DONE = 0x0040C6ED, 0x0040CAF2
S_NEXT, P_NEXT = 0x0040ED33, 0x0042887E
A = dict(PINNED)


def c_arc(va):
    return asm(f"""
        cmp  eax, {FLASK:#x}
        je   {M_LOB:#x}
        sub  eax, 0x37
        je   {M_ARC50:#x}
        jmp  {M_NEXT:#x}
    """, va)


def c_aisel(va):
    return asm(f"""
        cmp  eax, {FLASK:#x}
        je   {A['cave_ai']:#x}
        cmp  eax, 0x3d
        jge  {A_GE:#x}
        jmp  {A_NEXT:#x}
    """, va)


def c_land1(va):
    return asm(f"""
        mov  eax, dword ptr [ebp - 0x20]
        cmp  byte ptr [eax + 0xc], 0
        je   {L1_LANDED:#x}
        cmp  dword ptr [eax + 0x14], {FLASK:#x}
        je   {L1_LANDED:#x}
        jmp  {L1_NEXT:#x}
    """, va)


def c_land2(va):
    """[ebp-4] the TE ([+0x10] the thrower), [ebp-0x20] the effect, [ebp-0x28]/[ebp-0x2C] the
    landing hex.  Scratch as vanilla's own hit uses it: [ebp-0x10] the damage, [ebp-0x14]/[ebp-0x18]
    the hex and then its pixel; [ebp-0x38] the struck object and [ebp-0x24] its CA (write-before-read
    temps of other Execute branches).  [ebp-0x1C], the effect loop, is not touched."""
    src = f"""
        mov  eax, dword ptr [ebp - 0x20]
        mov  eax, dword ptr [eax + 0x14]
        cmp  eax, {FLASK:#x}
        je   l_flask
        jmp  {L2_NEXT:#x}
    l_flask:
        push ebx
        push esi
        push edi
        {{ANC}}
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        mov  esi, eax
        test esi, esi
        je   l_consume
        xor  edi, edi
    l_hex:
        lea  eax, [ebp - 0x14]
        push eax
        lea  eax, [ebp - 0x18]
        push eax
        mov  ecx, edi
        mov  edx, dword ptr [ebp - 0x2c]
        mov  eax, dword ptr [ebp - 0x28]
        call {CENTERHN:#x}
        mov  edx, dword ptr [ebp - 0x14]
        cmp  edx, dword ptr [esi + {L_W:#x}]
        jae  l_skip
        mov  ecx, dword ptr [ebp - 0x18]
        cmp  ecx, dword ptr [esi + {L_H:#x}]
        jae  l_skip
        mov  eax, esi
        call {GETFIELD:#x}
        test eax, eax
        je   l_skip
        mov  edx, {UNIT_HS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je   l_skip
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   l_skip
        mov  dword ptr [ebp - 0x38], eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   l_skip
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax]
        mov  edx, 0xffffff
        call {RANDOM:#x}
        mov  edx, dword ptr [ebx + {{SEED}}]
        mov  dword ptr [edx], eax
        push 0
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, {FLASK:#x}
        call {GETABILITY:#x}
        mov  ecx, dword ptr [ebp - 0x38]
        mov  edx, dword ptr [ebp - 4]
        mov  edx, dword ptr [edx + 0x10]
        call {CREATE_RA_CA:#x}
        mov  dword ptr [ebp - 0x24], eax
        movzx eax, byte ptr [eax + 0x10]
        mov  dword ptr [ebp - 0x10], eax
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
        je   l_types
        push 0
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {DAMAGE_ICONS:#x}
    l_types:
        mov  eax, dword ptr [ebp - 0x24]
        mov  cx, word ptr [eax + 0x13]
        test cx, cx
        je   l_hurt
        push 1
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {DAMAGE_ICONS:#x}
    l_hurt:
        cmp  dword ptr [ebp - 0x10], 0
        jle  l_exec
        mov  eax, dword ptr [ebp - 0x38]
        mov  eax, dword ptr [eax + 0x60]
        mov  dl, 4
        call {SET_ACTION:#x}
        mov  eax, dword ptr [ebp - 0x38]
        mov  edx, dword ptr [ebp - 0x10]
        call {HIT_BLOOD:#x}
    l_exec:
        mov  edx, dword ptr [ebp - 0x24]
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xe4]
        call {EXEC_CA:#x}
        mov  eax, dword ptr [ebp - 0x24]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    l_skip:
        inc  edi
        cmp  edi, 7
        jne  l_hex
    l_consume:
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        test eax, eax
        je   l_out
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   l_out
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xb8]
        test eax, eax
        je   l_out
        mov  esi, eax
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, {ENCH:#x}
        call {GETABILITY:#x}
        test eax, eax
        je   l_out
        mov  edx, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {SLOT_REMOVE:#x}]
    l_out:
        pop  edi
        pop  esi
        pop  ebx
        jmp  {LANDING_DONE:#x}
    """
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER, "HSSET": VAR_HSSET, "MAP": VAR_MAP,
                                "SEED": VAR_SEED})


SHOOTER_XY = """
        mov  eax, dword ptr [ebp + 0x14]
        mov  eax, dword ptr [eax + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {slot:#x}]
        movsx eax, al"""


def evals(x, y, out):
    """EvalPath (score -> eax) then EvalArea (value += into [out]) at hex ([x], [y])."""
    return f"""
        push dword ptr [ebp - 0x5c]
        push dword ptr [ebp - 0x60]
        {SHOOTER_XY.format(slot=0x74)}
        push eax
        {SHOOTER_XY.format(slot=0x78)}
        push eax
        push dword ptr [ebp - {x:#x}]
        push dword ptr [ebp - {y:#x}]
        push 0
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
        push 0
        push 1
        push 1
        push dword ptr [ebp + 0x14]
        push dword ptr [ebp + 8]
        lea  edx, [ebp - {out:#x}]
        mov  ecx, dword ptr [ebp + 0x10]
        mov  eax, dword ptr [ebp - 4]
        call {EVALAREA:#x}
        pop  eax"""


SCRATCH = (0x14, 0x18, 0x2C, 0x30, 0x34, 0x38, 0x3C)


def c_ai(va):
    """TCAI.CheckUnit's frame: [ebp-4] the AI, [ebp+8], [ebp+0x10] the aimed object, [ebp+0x14] the
    thrower (TCU; +0x60 its object, VMT +0x74/+0x78 its x/y), [ebp-0x5C]/[ebp-0x60] ability/spell id,
    [ebp-8]/[ebp-0xC] the aimed hex, [ebp-0x24] the range, [ebp-0x28] the value before the attack,
    [ebp-0x58] the score, [ebp-0x64] the value.  Alternatives: x [ebp-0x38], y [ebp-0x3C], value
    [ebp-0x34], score [ebp-0x18]; best centre [ebp-0x2C]/[ebp-0x30]; HN [ebp-0x14]."""
    save = "\n".join("        push dword ptr [ebp - %#x]" % o for o in SCRATCH)
    restore = "\n".join("        pop  dword ptr [ebp - %#x]" % o for o in reversed(SCRATCH))
    return asm(f"""
{save}
        {evals(0x8, 0xc, 0x64)}
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
        {SHOOTER_XY.format(slot=0x78)}
        push eax
        {SHOOTER_XY.format(slot=0x74)}
        pop  edx
        mov  ecx, dword ptr [ebp - 0x38]
        call {DHXTORAD:#x}
        cmp  eax, dword ptr [ebp - 0x24]
        jg   a_next
        mov  eax, dword ptr [ebp - 0x28]
        mov  dword ptr [ebp - 0x34], eax
        {evals(0x38, 0x3c, 0x34)}
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
        mov  eax, dword ptr [ebp - 0x2c]
        mov  dword ptr [ebp - 8], eax
        mov  eax, dword ptr [ebp - 0x30]
        mov  dword ptr [ebp - 0xc], eax
{restore}
        jmp  {A_DONE:#x}
    """, va)


def c_valid(va):
    """Can the flask land on hex (EAX, EDX)?  ECX = the thrower's x | y << 16.  -> AL = 1 when the
    hex is on the level, past column 0, not Border terrain and not the thrower's own."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        movsx edx, cx
        sar  ecx, 16
        cmp  esi, edx
        jne  v_other
        cmp  edi, ecx
        je   v_no
    v_other:
        test esi, esi
        jle  v_no
        {{ANC}}
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   v_no
        cmp  esi, dword ptr [eax + {L_W:#x}]
        jae  v_no
        cmp  edi, dword ptr [eax + {L_H:#x}]
        jae  v_no
        mov  edx, esi
        mov  ecx, edi
        call {GETFIELD:#x}
        test eax, eax
        je   v_no
        cmp  byte ptr [eax + 0x14], 0xf
        je   v_no
        mov  al, 1
        jmp  v_out
    v_no:
        xor  eax, eax
    v_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER})


def c_scatter(va):
    """NextStrike's missile branch: [ebp-4] the TE ([+0x14] ability, +0x1C/+0x1E the thrower's
    hex, +0x20/+0x22 the aimed hex, words).  One synced Random(10) for the flask; 4..9 move the
    aimed hex to HN 1..6 when that hex is valid."""
    src = f"""
        mov  eax, dword ptr [ebp - 4]
        cmp  dword ptr [eax + 0x14], {FLASK:#x}
        jne  s_out
        push ebx
        push esi
        push edi
        {{ANC}}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax]
        mov  edx, 10
        call {RANDOM:#x}
        sub  eax, 3
        jle  s_done
        mov  esi, eax
        sub  esp, 8
        mov  edi, esp
        push edi
        lea  eax, [edi + 4]
        push eax
        mov  ecx, esi
        mov  eax, dword ptr [ebp - 4]
        movzx edx, word ptr [eax + 0x22]
        movzx eax, word ptr [eax + 0x20]
        call {CENTERHN:#x}
        mov  eax, dword ptr [ebp - 4]
        movzx ecx, word ptr [eax + 0x1e]
        shl  ecx, 16
        mov  cx, word ptr [eax + 0x1c]
        mov  eax, dword ptr [edi]
        mov  edx, dword ptr [edi + 4]
        call {A['cave_valid']:#x}
        test al, al
        je   s_pop
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [edi]
        mov  word ptr [eax + 0x20], dx
        mov  edx, dword ptr [edi + 4]
        mov  word ptr [eax + 0x22], dx
    s_pop:
        add  esp, 8
    s_done:
        pop  edi
        pop  esi
        pop  ebx
    s_out:
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        jmp  {S_NEXT:#x}
    """
    return pic(src, va, "ebx", {"MAP": VAR_MAP})


FONT = """
        mov  eax, dword ptr [ebx + {ENGINE}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x68]"""


def c_odds(va):
    """The preview routine's exit, inside its try block: [ebp-4] the preview ([+0x18] the move
    control: +0x24/+0x28 the aimed hex, +0x34 the path, +0x38 the interception records), [ebp-8] /
    [ebp-0xC] the scroll, [ebp+8] the surface, [ebp-0x40] its string (freed by its finally).  Its
    other locals are dead here and serve as scratch: [ebp-0x10] the thrower (x | y << 16), then the
    text's y offset; [ebp-0x14]/[ebp-0x18] the aimed hex; [ebp-0x1C] its chance; [ebp-0x20] the
    hexes to label (bit HN); [ebp-0x24] HN; [ebp-0x28]/[ebp-0x2C] the hex; [ebp-0x30]/[ebp-0x34] its
    pixel; [ebp-0x38]/[ebp-0x3C] an interception hex."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  eax, dword ptr [ebp - 4]
        mov  esi, dword ptr [eax + 0x18]
        test esi, esi
        je   o_out
        mov  eax, dword ptr [esi + 0x34]
        test eax, eax
        je   o_out
        call {XYZ_COUNT:#x}
        test eax, eax
        jle  o_out
        mov  eax, esi
        call {GET_TCU:#x}
        test eax, eax
        je   o_out
        cmp  dword ptr [eax + 0x34], {FLASK:#x}
        jne  o_out
        mov  edi, eax
        {{ANC}}
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        mov  dword ptr [ebp - 0x10], eax
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        shl  eax, 16
        mov  ax, word ptr [ebp - 0x10]
        mov  dword ptr [ebp - 0x10], eax
        mov  eax, dword ptr [esi + 0x24]
        mov  dword ptr [ebp - 0x14], eax
        mov  eax, dword ptr [esi + 0x28]
        mov  dword ptr [ebp - 0x18], eax
        mov  dword ptr [ebp - 0x1c], {AIMED}
        mov  dword ptr [ebp - 0x20], 1
        mov  dword ptr [ebp - 0x24], 1
    o_scan:
        lea  eax, [ebp - 0x28]
        push eax
        lea  eax, [ebp - 0x2c]
        push eax
        mov  ecx, dword ptr [ebp - 0x24]
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {CENTERHN:#x}
        mov  eax, dword ptr [ebp - 0x28]
        mov  edx, dword ptr [ebp - 0x2c]
        mov  ecx, dword ptr [ebp - 0x10]
        call {A['cave_valid']:#x}
        test al, al
        je   o_bad
        mov  ecx, dword ptr [ebp - 0x24]
        mov  eax, 1
        shl  eax, cl
        or   dword ptr [ebp - 0x20], eax
        jmp  o_snext
    o_bad:
        add  dword ptr [ebp - 0x1c], {EACH}
    o_snext:
        inc  dword ptr [ebp - 0x24]
        cmp  dword ptr [ebp - 0x24], 7
        jne  o_scan
        mov  dword ptr [ebp - 0x24], 0
    o_draw:
        mov  ecx, dword ptr [ebp - 0x24]
        mov  eax, dword ptr [ebp - 0x20]
        bt   eax, ecx
        jae  o_dnext
        lea  eax, [ebp - 0x28]
        push eax
        lea  eax, [ebp - 0x2c]
        push eax
        mov  ecx, dword ptr [ebp - 0x24]
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {CENTERHN:#x}
        mov  dword ptr [ebp - 0x10], 0
        mov  eax, dword ptr [esi + 0x38]
        test eax, eax
        je   o_px
        xor  edi, edi
    o_rec:
        mov  eax, dword ptr [esi + 0x38]
        cmp  edi, dword ptr [eax + 8]
        jge  o_px
        lea  eax, [ebp - 0x3c]
        push eax
        mov  edx, edi
        mov  eax, dword ptr [esi + 0x38]
        call {LIST_GET:#x}
        mov  edx, dword ptr [eax + 4]
        mov  eax, dword ptr [esi + 0x34]
        call {XYZ_GET:#x}
        mov  edx, dword ptr [eax + 8]
        mov  eax, dword ptr [eax + 4]
        lea  ecx, [ebp - 0x38]
        call {HPTOHX:#x}
        mov  eax, dword ptr [ebp - 0x38]
        cmp  eax, dword ptr [ebp - 0x28]
        jne  o_rnext
        mov  eax, dword ptr [ebp - 0x3c]
        cmp  eax, dword ptr [ebp - 0x2c]
        jne  o_rnext
        mov  dword ptr [ebp - 0x10], {SHIFT:#x}
        jmp  o_px
    o_rnext:
        inc  edi
        jmp  o_rec
    o_px:
        lea  eax, [ebp - 0x34]
        push eax
        lea  ecx, [ebp - 0x30]
        mov  edx, dword ptr [ebp - 0x2c]
        mov  eax, dword ptr [ebp - 0x28]
        call {HXTOHP:#x}
        push dword ptr [ebp + 8]
        mov  edx, {SIGN}
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0xc]
        call {LIB_IMAGE:#x}
        mov  ecx, dword ptr [ebp - 0x34]
        add  ecx, {SIGN_DX}
        add  ecx, dword ptr [ebp - 0x10]
        sub  ecx, dword ptr [ebp - 0xc]
        mov  edx, dword ptr [ebp - 0x30]
        add  edx, {SIGN_DX}
        add  edx, dword ptr [ebp - 0x10]
        sub  edx, dword ptr [ebp - 8]
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x84]
        {FONT.format(ENGINE="{ENGINE}")}
        xor  edx, edx
        call {FONT_COLOUR:#x}
        mov  eax, {EACH}
        cmp  dword ptr [ebp - 0x24], 0
        jne  o_val
        mov  eax, dword ptr [ebp - 0x1c]
    o_val:
        lea  edx, [ebp - 0x40]
        call {INTTOSTR:#x}
        push dword ptr [ebp - 0x40]
        push dword ptr [ebp + 8]
        mov  ecx, dword ptr [ebp - 0x34]
        add  ecx, {TEXT_DY}
        add  ecx, dword ptr [ebp - 0x10]
        sub  ecx, dword ptr [ebp - 0xc]
        mov  edx, dword ptr [ebp - 0x30]
        add  edx, {TEXT_DX}
        add  edx, dword ptr [ebp - 0x10]
        sub  edx, dword ptr [ebp - 8]
        {FONT.format(ENGINE="{ENGINE}")}
        call {FONT_TEXT:#x}
    o_dnext:
        inc  dword ptr [ebp - 0x24]
        cmp  dword ptr [ebp - 0x24], 7
        jne  o_draw
    o_out:
        pop  edi
        pop  esi
        pop  ebx
        xor  eax, eax
        pop  edx
        pop  ecx
        pop  ecx
        jmp  {P_NEXT:#x}
    """
    return pic(src, va, "ebx", {"ENGINE": VAR_ENGINE})


BUILDERS = [("cave_arc", c_arc), ("cave_aisel", c_aisel), ("cave_land1", c_land1),
            ("cave_land2", c_land2), ("cave_ai", c_ai), ("cave_valid", c_valid),
            ("cave_scatter", c_scatter), ("cave_odds", c_odds)]


def layout():
    blobs = [(name, A[name], b(A[name])) for name, b in BUILDERS]
    ends = sorted((va, va + len(blob), name) for name, va, blob in blobs)
    for (a0, a1, an), (b0, _b1, bn) in zip(ends, ends[1:] + [(SLOT[1], 0, "slot end")]):
        assert a1 <= b0, "%s (%d B) runs into %s -- move the pins" % (an, a1 - a0, bn)
    return blobs


def self_checks(blobs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for name, va, blob in blobs:
        code = blob.rstrip(b"\x90")
        ins = list(md.disasm(code, va))
        assert sum(i.size for i in ins) == len(code), "%s does not disassemble cleanly" % name
        for i in ins:
            if i.mnemonic == "push" and i.op_str.startswith("0x"):
                assert int(i.op_str, 16) in (0, 1), "%s %08X: push %s" % (name, i.address, i.op_str)
    # evals() pushes nine arguments for each evaluator and relies on the callee popping them
    d = open(P.TARGET, "rb").read()
    for fn, ret_at in ((EVALPATH, 0x0041511B), (EVALAREA, 0x00414DA4)):
        o = P.va2off(d, fn)
        assert d[o:o + 3] == b"\x55\x8b\xec", "%08X is not a function start" % fn
        o = P.va2off(d, ret_at)
        assert d[o:o + 3] == b"\xc2\x24\x00", "%08X no longer ends ret 0x24" % fn
    ref = d[P.va2off(d, ABILTYPES_REF):P.va2off(d, ABILTYPES_REF) + 6]
    if ref != bytes.fromhex("8a8040944600"):
        sys.exit("ABORT: AbilTypes is not at %08X -- apply build_abiltypes_relocate.py first" % ABILTYPES)


def main():
    blobs = layout()
    self_checks(blobs)
    hooks = [(ABILTYPES + FLASK, b"\x00", bytes([CATEGORY])),
             (ABILTYPES_OLD + FLASK, b"\x00", bytes([CATEGORY]))]
    target = {"M": "cave_arc", "A": "cave_aisel", "L1": "cave_land1", "L2": "cave_land2",
              "S": "cave_scatter", "P": "cave_odds"}
    interior = []
    for name, (va, van, flo, fhi) in SITES.items():
        hooks.append((va, van, jmp_to(va, A[target[name]], len(van))))
        interior.append((va, va + len(van), flo, fhi))
    run("build_satchels_tc -- Throw Explosive Flask in manual combat (AoWTCPCK)", hooks, blobs,
        SLOT, interior)


if __name__ == "__main__":
    main()
