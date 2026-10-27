#!/usr/bin/env python
r"""
build_demon_curse.py -- Enmity of Nine Hells, the Death/Fire dual tier-3 world-map spell (built as
"Demon Curse", renamed by the owner 2026-10-25; the script keeps its file name).  AoWEPACK.dpl.
Owner's design 2026-10-25 (05-spells-added.md, "Death/Fire -- the first pair"): 40 mana, upkeep 10,
range 12, Enchanter; targets a unit of another player, never an independent, one curse per unit.
At the start of the caster's turn, while the upkeep is paid, it rolls: 0, 1/32, 1/16, 1/8, 1/4,
then 1/2 every turn, never reset.  Each success spawns d(X/2) Demons (X = turns active, capped d6)
on a random valid hex 8-16 hexes from the victim on its level (water legal; none if no hex).
Demons are independents on Hunt that chase every cursed unit regardless of odds and switch to
Raid when none remain; a Hunt party can never be recruited.  Any Demon gets +5 ATK / +5 DAM
against a cursed unit.  Dispel makes its normal roll; the caster's death lifts the curse.  The
cast is reported to both players; the demons' arrival is not.  The AI curses the strongest
enemy unit it can see in range.

THE SPELL (id 82) -- a TDarkGift INSTANCE (classref cell 0x557E675C, Create 0x557E83B0), registered
  at 0x557E8E23 (Cosmetic Surgery's `call RegisterSpell`, replayed first).  Name "Enmity of Nine
  Hells", id 82, mana 40, research 240, upkeep [+0x1C] 10, sphere 7 (dual: build_dual_sphere.py's TABLE
  holds Death+Fire), tier 3, enchantment level [+0x3C] 4 (dual tier 3 = single tier 4; the Dispel
  roll subtracts 10 per level).  Range 12, AI weight 0xE1: Dark Gift's.  SpellTypes[82] stays 0
  (not castable in battle).  Spells.pfs record 92: build_demon_curse_pfs.py.
THE ENCHANTMENT (ability 0x5B) -- a TUnitEnchantmentAbility INSTANCE (base ctor 0x55765518, class =
  VMT 0x55722364), name "Enmity of Nine Hells", registered at 0x557BCC56 (Free Movement's `call
  RegisterAbility`, replayed first).  0x5B: nil registry slot, no Ability.pfs record before ours
  (101), no `mov edx,0x5B` in AoWEPACK, AoWTCPCK, AoWz.exe or AoWzEd.exe.  Category 0 (inert),
  never offered (tag 9 = 0): a status, so no Hero Offers row.

STATE
  caster unit id  the TEnchantment padding +0x15..+0x17 (24 bits; TEnchantment's instance ends at
                  0x18, its last field is the level byte +0x14).  Saved as one rwInteger of the
                  dword at +0x14 under id 0x16 (TUnitEnchantment's chain uses 0xA-0xD, 0x14, 0x15),
                  for curse enchantments only, by repointing TUnitEnchantment's ReadWrite slot.
  turn counter    the ability data's +0xF (0xFF from its ctor, saved by vanilla id 0x11, untouched
                  by a duration-mode-0 enchantment): +1 per roll, 0xFF -> 0 on the first, capped
                  0x7F; X = counter + 1.
  demon group     byte 0xDC at TAIGroup's padding +0x4F (its last field is the byte +0x4E; no code
                  reads +0x4F), saved as rwByte id 0x21 by THuntAG and TRaidAG (TAIGroup uses
                  0x14-0x20), by repointing their ReadWrite slots.

SITES
  reg_ench  0x557BCC56  call RegisterAbility -> cave_reg_ench
  reg_spell 0x557E8E23  call RegisterSpell -> cave_reg_spell
  sel1/2    0x557E8499 / 0x557E84AC  Dark Gift ExecuteSpell `mov edx,0xA9` -> call cave_sel
            (EBX = the spell; id 82 -> 0x5B)
  post      0x557E84D2  ExecuteSpell's `mov al,[ebx+0x3C] / mov [esi+0x14],al` -> call cave_post
            + nop: id 82 stores the caster's id and posts "Enmity of Nine Hells cast on <unit>" to
            the caster's and the victim's logbooks (TLocationTextEventLog at the victim; no popup).
            The literal is cave_lit, the slot's last cave, so a renamed text moves no other cave.
  vtu       0x557E84E8  Dark Gift ValidTargetUnit entry -> jmp cave_vtu: id 82 refuses own,
            independent and already-cursed units, else TUnitSpell.ValidTargetUnit.
  vtp       0x5577B1CC  TUnitSpell.ValidTargetParty entry -> jmp cave_vtp: id 82 wants an army
            that is not fully concealed and belongs to neither the caster's player nor player 0.
  roll      0x5577CE4D  TPlayerMagicControl.NewTurn's `call SetMana` (after OutOfMana, so only
            paid curses roll) -> call cave_roll: each curse in the player's pmc+0x3C list,
            backwards: caster missing or killed -> Dispel (catch-all for removals that bypass
            Killed); else counter, roll, spawn.
  refresh   0x5573980F  THuntAGC.ProcessStates state 0 -> jmp cave_refresh: a marked group's
            target list is rebuilt from every curse in every player's list.
  raid      0x5573989B  the empty-list fallback `push 1` (Patrol) -> jmp cave_raid: a marked group
            gets CreateGroup(6 = TRaidAG) instead, and the new group is marked.
  cp        0x55739799  THuntAGC.TargetFoundEvent's SetupCP -> jmp cave_cp: a marked group skips
            the combat predictor (attacks regardless of odds).
  join      0x557821C4  TAbstractUnit.CanJoin's behaviour 2/3 gate -> jmp cave_join: also refuses
            behaviour 0xD (any Hunt party, owner's rule) and any marked group.
  death     0x557808A8  TAbstractUnit.Killed's `call UnregisterEnchantments` -> call cave_death:
            then Dispel (VMT+0x68) every curse whose stored caster id is the dying unit's.
  m3        0x55767C89  TMeleeRound.CalculateStrikes, the resume point every melee chain jumps to
            (ESI striker, EDI target, [EBX]/[EBX+4] ATK/DAM) -> jmp cave_m3: +5/+5.
  s1        0x557666DF  CreateStrikeCA after its CA is built (EBP attacker, ESI target, BL ATK,
            [ESP+3] DAM) -> jmp cave_s1: +5/+5.  The ranged builder is not hooked: Demons have no
            ranged attack.  Both covered sites serve manual and auto combat.
  ai        0x5577B460  TUnitSpell.AIRetrieveOptimalTargetUnit entry -> jmp cave_ai: id 82 scans
            every unit for one owned by a player at war (relation 1) with the caster's, not
            concealed, alive, not cursed, on the caster's level within range; keeps the highest
            GetStrengthMax(dtAll); score = level + [spell+0x40], as vanilla's.
  aiown     0x5577B6FD  AIExecuteCastSpellAction's `TE[+0x28] = caster's owner` -> call cave_aiown
            + nop: id 82 writes the target's owner, which TUnitSpellTE.Validate requires.
  info      0x5577AC94  TUnitSpell.GetCombatInfo's tail (8 B) -> jmp cave_info: id 82 sets the info's
            byte 7 to 2, so tactical targeting (TCombatUnitSelectionControl.MouseDownEvent's side
            test, 0x0041F5C3) takes enemy units; every unit spell reports 1 (friendly).  Battle
            casting itself is SpellTypes[82] = 7 (build_battlecast_unitspells.py, owner 2026-10-25);
            the cast still goes through ExecuteSpell, so vtu's refusals hold in battle.
  slots     0x557221B0 TUnitEnchantment +0x18, 0x5571B8E8 THuntAG +0x18, 0x557D87BC TRaidAG +0x18
            (ReadWrite, .reloc kept) -> cave_ench_rw / cave_hunt_rw / cave_raid_rw.

SPAWN (h_spawn): TArmyHS.Create, TArmy.SetPlayer(0), n x {TAbstractUnit.Create (TUnit), Demon
  resource 0xCD, AddUnit, Release}.  Pass 1 counts the hexes RadToHN(8)..RadToHN(17)-1 around the
  victim that are on the level, carry no blocking object (field VMT+0x80 0x20217), are unowned
  and CanPlace accepts; none -> free the army.  k = Random(count); PlaceEx (flags 0: that hex
  only) at candidate k, else the next ones, wrapping once.  Then Activate, CreateGroup(0xD),
  marker, AddUnits, the victim's id, Release.  Crusade's recipe (0x557ED340), without its 0x65.

RNG: P1 SYNCED DRAW (host TPlayerMagicControl.NewTurn is in rng_audit's SYNC list): the roll
  Random(32) at 0x558B748A, the count Random(min(X/2,6)) at 0x558B74A9 and the hex
  Random(candidates) at 0x558B72A7, all TAoWHSMap.Random 0x5577827C through AoWHSMap.

COUPLINGS: the m3 and s1 resume points end the melee chains of build_assassin.py,
  build_invis_penalty.py, build_trueseeing.py, build_magebane.py and build_shield.py; they jump
  there and land on this hook.  NewTurn's next call (0x5577CE54) is build_dual_sphere.py's grant.

Slot 0x558B7000-0x558B7FFF, exclusive.  PIC.  Surgical --undo (no other script chains onto it).

Unproven: the hunt target finder's 200-point search reaching 16 hexes over hard terrain; a Raid
group split by TAIGroupControl.Split loses the marker (and with it the recruitment block).

    python build_scripts/build_demon_curse.py            dry run + state
    python build_scripts/build_demon_curse.py --apply
    python build_scripts/build_demon_curse.py --undo
    python build_scripts/build_demon_curse.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 82, "Enmity of Nine Hells"
CURSE, CURSE_NAME = 0x5B, "Enmity of Nine Hells"
DARKGIFT_ENCH = 0xA9
MANA, UPKEEP, RESEARCH, SPHERE, TIER, LEVEL = 40, 10, 240, 7, 3, 4
DEMON_RES = 0xCD
MARK = 0xDC
TAG_CASTER, TAG_MARK = 0x16, 0x21
RING_LO, RING_HI = 8, 16
EVENT_TEXT = "Enmity of Nine Hells cast on "

SLOT = (0x558B7000, 0x558B8000)
EVENT_LIT = 0x558B7B40                  # cave_lit: EVENT_TEXT as an AnsiString literal

# data (reached through the anchor)
AOWHSMAP, AOWHSSET = 0x558FA040, 0x558FA044
DTALL = 0x558E8044
TUE_VMT = 0x55722198            # TUnitEnchantment
TUEA_VMT = 0x55722364           # TUnitEnchantmentAbility (its class pointer)
CU_CELL = 0x55715A54            # [.] = TCombatUnit
ARMYHS_CELL = 0x55713360        # [.] = TArmyHS
UNIT_CELL = 0x55710C6C          # [.] = TUnit
EVLOG_CELL = 0x557FC624         # [.] = TLocationTextEventLog
DARKGIFT_CELL = 0x557E675C      # [.] = TDarkGift

# code
REGISTER_ABIL, REGISTER_SPELL = 0x55750238, 0x55779B40
LSTRASG, LSTRCAT3, LSTRCLR = 0x55701150, 0x55701190, 0x55701140
ISCLASS, OBJ_FREE = 0x557010C0, 0x557010B8
TUEA_CREATE, DARKGIFT_CREATE = 0x55765518, 0x557E83B0
UNITSPELL_VTU = 0x5577ACAC
FINDUNIT, GETABILITYDATA, GETPLAYERS = 0x5577E948, 0x5574F1C4, 0x557544D0
RANDOM, GETLOCATION = 0x5577827C, 0x5577ED94
RADTOHN, CENTERHN, DHXTORAD = 0x55702684, 0x55702694, 0x5570266C
GETMAPLEVEL, LEVEL_GETFIELD, FIELD_GETPLAYER = 0x557020EC, 0x557020DC, 0x55771C98
CANPLACE, PLACEEX = 0x5578DDC4, 0x55791F58
ARMYHS_CREATE, SETPLAYER, AUNIT_CREATE = 0x557908BC, 0x5578D690, 0x5577EB28
GETUNITRES, SETUNITRES = 0x55785050, 0x55782BE4
UNITS2REL, CREATEGROUP = 0x5575BCA0, 0x55737EB4
ILIST_ADD, ILIST_CLEAR = 0x55702E74, 0x55702E7C
EVLOG_CREATE, SETLOCATION, ADD_EVENT = 0x557FDC74, 0x557FDCFC, 0x557FDB90
GETDIPREL, GETSTRENGTHMAX = 0x55754150, 0x5577F924
SETUPCP, SETMANA, UNREG_ENCH = 0x55738E8C, 0x5577C9B0, 0x5577F328
ENCH_RW, HUNT_RW, AIGROUP_RW = 0x55765B8C, 0x557396E4, 0x5573715C

# resume points
VTU_RESUME = 0x557E84EE
REFRESH_RESUME = 0x55739815
RAID_VANILLA, RAID_RESUME = 0x557398A3, 0x557398B6
CP_RESUME, CP_SKIP = 0x557397A3, 0x557397C7
JOIN_CONT, JOIN_REFUSE = 0x557821CE, 0x55782318
M3_RESUME, S1_RESUME = 0x55767C90, 0x557666E5
AI_RESUME = 0x5577B466

SITES = {   # name: (va, vanilla bytes, function lo, hi)
    "reg_ench":  (0x557BCC56, bytes.fromhex("e8dd35f9ff"), 0x557BC1CC, 0x557BCFCC),
    "reg_spell": (0x557E8E23, bytes.fromhex("e8180df9ff"), 0x557E8C84, 0x557E8E44),
    "sel1":      (0x557E8499, bytes.fromhex("baa9000000"), 0x557E8478, 0x557E84E8),
    "sel2":      (0x557E84AC, bytes.fromhex("baa9000000"), 0x557E8478, 0x557E84E8),
    "post":      (0x557E84D2, bytes.fromhex("8a433c884614"), 0x557E8478, 0x557E84E8),
    "vtu":       (0x557E84E8, bytes.fromhex("53568bf18bce"), 0x557E84E8, 0x557E851C),
    "vtp":       (0x5577B1CC, bytes.fromhex("8b411cf640"), 0x5577B1CC, 0x5577B1DC),
    "roll":      (0x5577CE4D, bytes.fromhex("e85efbffff"), 0x5577CC2C, 0x5577CE60),
    "refresh":   (0x5573980F, bytes.fromhex("8b7e0c8b4750"), 0x557397F4, 0x55739930),
    "raid":      (0x5573989B, bytes.fromhex("6a018b460c8a4834"), 0x557397F4, 0x55739930),
    "cp":        (0x55739799, bytes.fromhex("8b55f88bc6e8e9f6ffff"), 0x55739714, 0x557397F4),
    "join":      (0x557821C4, bytes.fromhex("04fe2c020f824a010000"), 0x557821AC, 0x55782324),
    "death":     (0x557808A8, bytes.fromhex("e87beaffff"), 0x5578087C, 0x557808DC),
    "m3":        (0x55767C89, bytes.fromhex("8bc78b10ff5270"), 0x55767B24, 0x55767D24),
    "s1":        (0x557666DF, bytes.fromhex("538a44240750"), 0x557665E4, 0x5576670C),
    "ai":        (0x5577B460, bytes.fromhex("558bec83c4e8"), 0x5577B460, 0x5577B550),
    "aiown":     (0x5577B6FD, bytes.fromhex("8a4624884728"), 0x5577B658, 0x5577B784),
    "info":      (0x5577AC94, bytes.fromhex("c64305ff5f5e5bc3"), 0x5577AC78, 0x5577AC9C),
}
VMT_SLOTS = {   # name: (slot va, vanilla target)
    "ench_rw": (0x557221B0, ENCH_RW),
    "hunt_rw": (0x5571B8E8, HUNT_RW),
    "raid_rw": (0x557D87BC, AIGROUP_RW),
}


# ---- helpers ------------------------------------------------------------------------------------
def build_cu(va):
    """EAX = combat object -> EAX = its strategic unit [+0x4C] if it is a TCombatUnit, else 0."""
    return pic("""
        test eax, eax
        je   c_none
        push ecx
        push edx
        push eax
        {ANC}
        mov  edx, dword ptr [ecx + {CUCELL}]
        mov  eax, dword ptr [esp]
        call %#x
        test al, al
        pop  eax
        je   c_no
        mov  eax, dword ptr [eax + 0x4c]
        pop  edx
        pop  ecx
        ret
    c_no:
        pop  edx
        pop  ecx
    c_none:
        xor  eax, eax
        ret
    """ % ISCLASS, va, "ecx", {"CUCELL": CU_CELL})


def build_dvc(va, at):
    """EAX = attacker, EDX = target (combat objects) -> AL = attacker is a Demon and the target is
    cursed.  Everything but EAX kept."""
    return pic(f"""
        push ebx
        push ecx
        push edx
        push esi
        push edi
        mov  edi, edx
        call {at['cu']:#x}
        test eax, eax
        je   d_no
        mov  esi, eax
        {{ANC}}
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax + 0x5c]
        mov  edx, {DEMON_RES:#x}
        call {GETUNITRES:#x}
        test eax, eax
        je   d_no
        cmp  eax, dword ptr [esi + 0x40]
        jne  d_no
        mov  eax, edi
        call {at['cu']:#x}
        test eax, eax
        je   d_no
        mov  edx, {CURSE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        jmp  d_out
    d_no:
        xor  eax, eax
    d_out:
        pop  edi
        pop  esi
        pop  edx
        pop  ecx
        pop  ebx
        ret
    """, va, "ebx", {"HSSET": AOWHSSET})


def build_isc(va):
    """EAX = enchantment -> ZF = it is a curse (a plain TUnitEnchantment of ability 0x5B).
    Every register kept."""
    return pic(f"""
        push ecx
        push edx
        {{ANC}}
        lea  edx, [ecx + {{TUEVMT}}]
        cmp  dword ptr [eax], edx
        jne  i_out
        cmp  dword ptr [eax + 0x1c], {CURSE:#x}
    i_out:
        pop  edx
        pop  ecx
        ret
    """, va, "ecx", {"TUEVMT": TUE_VMT})


def build_event(va):
    """EAX = victim, EDX = caster: EVENT_TEXT + <name> to both owners' logbooks."""
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x10
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        xor  eax, eax
        mov  dword ptr [ebp - 0xc], eax
        mov  dword ptr [ebp - 0x10], eax
        {{ANC}}
        lea  edx, [ebp - 0xc]
        mov  eax, dword ptr [ebp - 4]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xf8]
        lea  eax, [ebp - 0xe]
        push eax
        lea  ecx, [ebp - 0xf]
        lea  edx, [ebp - 0x10]
        mov  eax, dword ptr [ebp - 4]
        call {GETLOCATION:#x}
        mov  eax, dword ptr [ebp - 8]
        movzx edi, byte ptr [eax + 0x24]
        mov  eax, edi
        call e_post
        mov  eax, dword ptr [ebp - 4]
        movzx eax, byte ptr [eax + 0x24]
        cmp  eax, edi
        je   e_end
        call e_post
    e_end:
        lea  eax, [ebp - 0xc]
        call {LSTRCLR:#x}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    e_post:
        mov  edx, eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        call {GETPLAYERS:#x}
        test eax, eax
        je   e_pret
        mov  esi, eax
        cmp  dword ptr [esi + 0xd8], 0
        je   e_pret
        mov  eax, dword ptr [ebx + {{EVCELL}}]
        mov  dl, 1
        xor  ecx, ecx
        call {EVLOG_CREATE:#x}
        push eax
        mov  edx, dword ptr [ebp - 8]
        mov  dl, byte ptr [edx + 0x24]
        mov  byte ptr [eax + 0x10], dl
        movsx ecx, byte ptr [ebp - 0xe]
        push ecx
        mov  dl, byte ptr [ebp - 0x10]
        mov  cl, byte ptr [ebp - 0xf]
        call {SETLOCATION:#x}
        mov  eax, dword ptr [esp]
        add  eax, 0x18
        lea  edx, [ebx + {{LIT}}]
        mov  ecx, dword ptr [ebp - 0xc]
        call {LSTRCAT3:#x}
        mov  eax, dword ptr [esi + 0xd8]
        mov  edx, dword ptr [esp]
        call {ADD_EVENT:#x}
        pop  eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    e_pret:
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "EVCELL": EVLOG_CELL, "LIT": EVENT_LIT + 8})


def build_spawn(va):
    """EAX = victim, EDX = demon count (1-6).
    Frame: -4 victim, -8 count, -0xC army HS, -0x10 map, -0x14 map level, -0x18 / -0x1C ring hn
    lo / hi, -0x20 k, -0x24 / -0x28 hex x / y (dwords), -0x2C/-0x2B/-0x2A victim x/y/level,
    -0x30 lap."""
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x30
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        xor  eax, eax
        mov  dword ptr [ebp - 0x2c], eax
        {{ANC}}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  dword ptr [ebp - 0x10], eax
        lea  eax, [ebp - 0x2a]
        push eax
        lea  ecx, [ebp - 0x2b]
        lea  edx, [ebp - 0x2c]
        mov  eax, dword ptr [ebp - 4]
        call {GETLOCATION:#x}
        movsx edx, byte ptr [ebp - 0x2a]
        test edx, edx
        js   s_out
        mov  eax, dword ptr [ebp - 0x10]
        mov  eax, dword ptr [eax + 0x10]
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   s_out
        mov  dword ptr [ebp - 0x14], eax
        mov  eax, {RING_LO}
        call {RADTOHN:#x}
        mov  dword ptr [ebp - 0x18], eax
        mov  eax, {RING_HI + 1}
        call {RADTOHN:#x}
        mov  dword ptr [ebp - 0x1c], eax
        mov  eax, dword ptr [ebx + {{ARMYCELL}}]
        mov  dl, 1
        xor  ecx, ecx
        call {ARMYHS_CREATE:#x}
        mov  dword ptr [ebp - 0xc], eax
        mov  eax, dword ptr [eax + 0x1c]
        xor  edx, edx
        call {SETPLAYER:#x}
        mov  esi, dword ptr [ebp - 8]
    s_unit:
        mov  eax, dword ptr [ebx + {{UNITCELL}}]
        mov  dl, 1
        xor  ecx, ecx
        call {AUNIT_CREATE:#x}
        mov  edi, eax
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax + 0x5c]
        mov  edx, {DEMON_RES:#x}
        call {GETUNITRES:#x}
        mov  edx, eax
        mov  eax, edi
        call {SETUNITRES:#x}
        mov  eax, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [eax + 0x1c]
        mov  edx, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xac]
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        dec  esi
        jg   s_unit
        xor  edi, edi
        mov  esi, dword ptr [ebp - 0x18]
    s_p1:
        cmp  esi, dword ptr [ebp - 0x1c]
        jge  s_p1done
        call s_hexok
        test al, al
        je   s_p1n
        inc  edi
    s_p1n:
        inc  esi
        jmp  s_p1
    s_p1done:
        test edi, edi
        je   s_fail
        mov  eax, dword ptr [ebp - 0x10]
        mov  edx, edi
        call {RANDOM:#x}
        mov  dword ptr [ebp - 0x20], eax
        mov  dword ptr [ebp - 0x30], 0
    s_lap:
        xor  edi, edi
        mov  esi, dword ptr [ebp - 0x18]
    s_p2:
        cmp  esi, dword ptr [ebp - 0x1c]
        jge  s_lapdone
        call s_hexok
        test al, al
        je   s_p2n
        cmp  edi, dword ptr [ebp - 0x20]
        setge al
        xor  al, byte ptr [ebp - 0x30]
        inc  edi
        test al, al
        je   s_p2n
        movsx eax, byte ptr [ebp - 0x2a]
        push eax
        push 0
        mov  dl, byte ptr [ebp - 0x24]
        mov  cl, byte ptr [ebp - 0x28]
        mov  eax, dword ptr [ebp - 0xc]
        call {PLACEEX:#x}
        test al, al
        jne  s_placed
    s_p2n:
        inc  esi
        jmp  s_p2
    s_lapdone:
        inc  dword ptr [ebp - 0x30]
        cmp  dword ptr [ebp - 0x30], 2
        jb   s_lap
    s_fail:
        mov  eax, dword ptr [ebp - 0xc]
        call {OBJ_FREE:#x}
        jmp  s_out
    s_placed:
        mov  eax, dword ptr [ebp - 0xc]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        mov  eax, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [eax + 0x1c]
        mov  dl, 5
        call {UNITS2REL:#x}
        mov  ecx, eax
        push 0xd
        mov  eax, dword ptr [ebp - 0x10]
        mov  eax, dword ptr [eax + 0x130]
        xor  edx, edx
        call {CREATEGROUP:#x}
        test eax, eax
        je   s_out
        mov  esi, eax
        mov  byte ptr [esi + 0x4f], {MARK:#x}
        mov  edx, dword ptr [ebp - 0xc]
        mov  edx, dword ptr [edx + 0x1c]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xb4]
        mov  eax, dword ptr [esi + 0x50]
        mov  edx, dword ptr [ebp - 4]
        mov  edx, dword ptr [edx + 0x18]
        call {ILIST_ADD:#x}
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    s_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    s_hexok:
        lea  eax, [ebp - 0x24]
        push eax
        lea  eax, [ebp - 0x28]
        push eax
        movsx eax, byte ptr [ebp - 0x2c]
        movsx edx, byte ptr [ebp - 0x2b]
        mov  ecx, esi
        call {CENTERHN:#x}
        mov  eax, dword ptr [ebp - 0x24]
        test eax, eax
        js   h_no
        mov  edx, dword ptr [ebp - 0x14]
        cmp  eax, dword ptr [edx + 0xc]
        jge  h_no
        mov  ecx, dword ptr [ebp - 0x28]
        test ecx, ecx
        js   h_no
        cmp  ecx, dword ptr [edx + 0x10]
        jge  h_no
        mov  edx, eax
        mov  eax, dword ptr [ebp - 0x14]
        call {LEVEL_GETFIELD:#x}
        test eax, eax
        je   h_no
        push eax
        mov  edx, 0x20217
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        pop  eax
        jne  h_no
        call {FIELD_GETPLAYER:#x}
        cmp  al, 0xff
        jne  h_no
        movsx eax, byte ptr [ebp - 0x2a]
        push eax
        mov  dl, byte ptr [ebp - 0x24]
        mov  cl, byte ptr [ebp - 0x28]
        mov  eax, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [eax + 0x1c]
        call {CANPLACE:#x}
        ret
    h_no:
        xor  eax, eax
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "HSSET": AOWHSSET, "ARMYCELL": ARMYHS_CELL,
                                 "UNITCELL": UNIT_CELL})


def build_turn(va, at):
    """EAX = one curse enchantment of the player whose turn starts: lift it if its caster is gone,
    else count, roll and spawn."""
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 8
        push ebx
        push esi
        push edi
        mov  edi, eax
        {{ANC}}
        mov  edx, dword ptr [edi + 0x14]
        shr  edx, 8
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0xfc]
        call {FINDUNIT:#x}
        test eax, eax
        je   t_lift
        test byte ptr [eax + 0x25], 0x10
        jne  t_lift
        mov  edx, dword ptr [edi + 0x18]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0xfc]
        call {FINDUNIT:#x}
        test eax, eax
        je   t_out
        test byte ptr [eax + 0x25], 0x10
        jne  t_out
        mov  esi, eax
        mov  edx, {CURSE:#x}
        call {GETABILITYDATA:#x}
        test eax, eax
        je   t_out
        mov  cl, byte ptr [eax + 0xf]
        inc  cl
        cmp  cl, 0x7f
        jbe  t_c
        mov  cl, 0x7f
    t_c:
        mov  byte ptr [eax + 0xf], cl
        movzx ecx, cl
        inc  ecx
        mov  dword ptr [ebp - 8], ecx
        sub  ecx, 2
        jb   t_out
        cmp  ecx, 4
        jbe  t_k
        mov  ecx, 4
    t_k:
        mov  eax, 1
        shl  eax, cl
        mov  dword ptr [ebp - 4], eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, 32
        call {RANDOM:#x}
        cmp  eax, dword ptr [ebp - 4]
        jge  t_out
        mov  edx, dword ptr [ebp - 8]
        shr  edx, 1
        cmp  edx, 6
        jbe  t_n
        mov  edx, 6
    t_n:
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {RANDOM:#x}
        lea  edx, [eax + 1]
        mov  eax, esi
        call {at['spawn']:#x}
        jmp  t_out
    t_lift:
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x68]
    t_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP})


# ---- the spell's own sites ----------------------------------------------------------------------
def build_sel(va):
    return asm(f"""
        mov  edx, {DARKGIFT_ENCH:#x}
        cmp  dword ptr [ebx + 0x10], {SPELL_ID}
        jne  l_out
        mov  edx, {CURSE:#x}
    l_out:
        ret
    """, va)


def build_post(va, at):
    """Called from ExecuteSpell: EBX = spell, ESI = the new enchantment, [EBP-4] = the caster."""
    return pic(f"""
        mov  al, byte ptr [ebx + 0x3c]
        mov  byte ptr [esi + 0x14], al
        cmp  dword ptr [ebx + 0x10], {SPELL_ID}
        jne  p_ret
        pushad
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x18]
        shl  eax, 8
        mov  al, byte ptr [esi + 0x14]
        mov  dword ptr [esi + 0x14], eax
        {{ANC}}
        mov  edx, dword ptr [esi + 0x18]
        mov  eax, dword ptr [ecx + {{MAP}}]
        mov  eax, dword ptr [eax + 0xfc]
        call {FINDUNIT:#x}
        test eax, eax
        je   p_done
        mov  edx, dword ptr [ebp - 4]
        call {at['event']:#x}
    p_done:
        popad
    p_ret:
        ret
    """, va, "ecx", {"MAP": AOWHSMAP})


def build_vtu(va):
    """EAX = spell, EDX = caster, ECX = unit -> AL."""
    return asm(f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        jne  v_vanilla
        push ebx
        push esi
        mov  esi, ecx
        mov  bl, byte ptr [esi + 0x24]
        test bl, bl
        je   v_no
        cmp  bl, byte ptr [edx + 0x24]
        je   v_no
        call {UNITSPELL_VTU:#x}
        test al, al
        je   v_no
        mov  eax, esi
        mov  edx, {CURSE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  v_no
        mov  al, 1
        jmp  v_out
    v_no:
        xor  eax, eax
    v_out:
        pop  esi
        pop  ebx
        ret
    v_vanilla:
        push ebx
        push esi
        mov  esi, ecx
        mov  ecx, esi
        jmp  {VTU_RESUME:#x}
    """, va)


def build_vtp(va):
    """EAX = spell, EDX = caster, ECX = army HS -> AL."""
    return asm(f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        je   w_curse
        mov  eax, dword ptr [ecx + 0x1c]
        test byte ptr [eax + 0x10], 0x10
        setne al
        xor  al, 1
        ret
    w_curse:
        mov  eax, dword ptr [ecx + 0x1c]
        test byte ptr [eax + 0x10], 0x10
        jne  w_no
        mov  al, byte ptr [eax + 0x12]
        test al, al
        je   w_no
        cmp  al, byte ptr [edx + 0x24]
        je   w_no
        mov  al, 1
        ret
    w_no:
        xor  eax, eax
        ret
    """, va)


def build_roll(va, at):
    """Replaces NewTurn's `call SetMana` (EAX = ESI = the player's magic control)."""
    return asm(f"""
        call {SETMANA:#x}
        pushad
        mov  ebp, esi
        mov  eax, dword ptr [ebp + 0x3c]
        test eax, eax
        je   r_done
        mov  eax, dword ptr [eax + 8]
        test eax, eax
        je   r_done
        mov  esi, dword ptr [eax + 8]
    r_loop:
        dec  esi
        js   r_done
        mov  eax, dword ptr [ebp + 0x3c]
        mov  eax, dword ptr [eax + 8]
        cmp  esi, dword ptr [eax + 8]
        jge  r_loop
        mov  eax, dword ptr [eax + 4]
        mov  eax, dword ptr [eax + esi*4]
        test eax, eax
        je   r_loop
        call {at['isc']:#x}
        jne  r_loop
        call {at['turn']:#x}
        jmp  r_loop
    r_done:
        popad
        ret
    """, va)


def players_curses(label, body):
    """Loop over every curse in every player's enchantment list, backwards.  EBX = anchor holding
    {MAP}; EBP = player index, ESI = enchantment index, [ESP] = the TList; EAX = the curse at
    `body`, which must end by falling through (it may call out; Dispel is allowed)."""
    return f"""
        mov  eax, dword ptr [ebx + {{MAP}}]
        test eax, eax
        je   {label}_done
        mov  eax, dword ptr [eax + 0x140]
        test eax, eax
        je   {label}_done
        mov  eax, dword ptr [eax + 8]
        mov  ebp, dword ptr [eax + 8]
    {label}_pl:
        dec  ebp
        js   {label}_done
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        mov  edx, ebp
        call {GETPLAYERS:#x}
        test eax, eax
        je   {label}_pl
        mov  eax, dword ptr [eax + 0x54]
        test eax, eax
        je   {label}_pl
        mov  eax, dword ptr [eax + 0x3c]
        test eax, eax
        je   {label}_pl
        mov  eax, dword ptr [eax + 8]
        test eax, eax
        je   {label}_pl
        push eax
        mov  esi, dword ptr [eax + 8]
    {label}_en:
        dec  esi
        js   {label}_next
        mov  eax, dword ptr [esp]
        cmp  esi, dword ptr [eax + 8]
        jge  {label}_en
        mov  eax, dword ptr [eax + 4]
        mov  eax, dword ptr [eax + esi*4]
        test eax, eax
        je   {label}_en
        call {{ISC}}
        jne  {label}_en
{body}
        jmp  {label}_en
    {label}_next:
        pop  eax
        jmp  {label}_pl
    {label}_done:
"""


def build_refresh(va, at):
    """THuntAGC.ProcessStates state 0 (ESI = the control): a marked group's list = every curse."""
    body = """
        mov  edx, dword ptr [eax + 0x18]
        mov  eax, dword ptr [edi + 0x50]
        call %#x
""" % ILIST_ADD
    src = f"""
        mov  edi, dword ptr [esi + 0xc]
        cmp  byte ptr [edi + 0x4f], {MARK:#x}
        jne  f_out
        pushad
        mov  eax, dword ptr [edi + 0x50]
        call {ILIST_CLEAR:#x}
        {{ANC}}
""" + players_curses("f", body).replace("{ISC}", "%#x" % at["isc"]) + f"""
        popad
    f_out:
        mov  eax, dword ptr [edi + 0x50]
        jmp  {REFRESH_RESUME:#x}
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP})


def build_raid(va):
    """The empty-list fallback (ESI = the control).  EBX is dead here (0x557398B6 writes it)."""
    return pic(f"""
        {{ANC}}
        mov  eax, dword ptr [esi + 0xc]
        cmp  byte ptr [eax + 0x4f], {MARK:#x}
        jne  q_van
        push 6
        mov  cl, byte ptr [eax + 0x34]
        mov  dl, byte ptr [eax + 0x28]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x130]
        call {CREATEGROUP:#x}
        test eax, eax
        je   q_van
        mov  byte ptr [eax + 0x4f], {MARK:#x}
        jmp  {RAID_RESUME:#x}
    q_van:
        push 1
        mov  eax, dword ptr [esi + 0xc]
        mov  cl, byte ptr [eax + 0x34]
        jmp  {RAID_VANILLA:#x}
    """, va, "ebx", {"MAP": AOWHSMAP})


def build_cp(va):
    return asm(f"""
        mov  eax, dword ptr [esi + 0xc]
        cmp  byte ptr [eax + 0x4f], {MARK:#x}
        je   {CP_SKIP:#x}
        mov  edx, dword ptr [ebp - 8]
        mov  eax, esi
        call {SETUPCP:#x}
        jmp  {CP_RESUME:#x}
    """, va)


def build_join(va):
    """AL = the unit's group's Behavior, EBX = the group."""
    return asm(f"""
        cmp  al, 0xd
        je   {JOIN_REFUSE:#x}
        cmp  byte ptr [ebx + 0x4f], {MARK:#x}
        je   {JOIN_REFUSE:#x}
        add  al, 0xfe
        sub  al, 2
        jb   {JOIN_REFUSE:#x}
        jmp  {JOIN_CONT:#x}
    """, va)


def build_death(va, at):
    """Replaces Killed's `call UnregisterEnchantments` (EAX = EBX = the dying unit)."""
    body = """
        mov  edx, dword ptr [eax + 0x14]
        shr  edx, 8
        cmp  edx, edi
        jne  k_en
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x68]
"""
    src = f"""
        call {UNREG_ENCH:#x}
        pushad
        mov  edi, dword ptr [ebx + 0x18]
        and  edi, 0xffffff
        {{ANC}}
""" + players_curses("k", body).replace("{ISC}", "%#x" % at["isc"]) + """
        popad
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP})


def build_m3(va, at):
    return asm(f"""
        push eax
        push ecx
        push edx
        mov  eax, esi
        mov  edx, edi
        call {at['dvc']:#x}
        test al, al
        pop  edx
        pop  ecx
        pop  eax
        je   m_r
        add  dword ptr [ebx], 5
        add  dword ptr [ebx + 4], 5
    m_r:
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x70]
        jmp  {M3_RESUME:#x}
    """, va)


def build_s1(va, at):
    return asm(f"""
        push eax
        push ecx
        push edx
        mov  eax, ebp
        mov  edx, esi
        call {at['dvc']:#x}
        test al, al
        pop  edx
        pop  ecx
        pop  eax
        je   n_r
        add  bl, 5
        add  byte ptr [esp + 3], 5
    n_r:
        push ebx
        mov  al, byte ptr [esp + 7]
        push eax
        jmp  {S1_RESUME:#x}
    """, va)


def build_ai(va):
    """AIRetrieveOptimalTargetUnit(EAX spell, EDX hero, ECX army, push &unit, push &score) -> AL,
    ret 8.  Frame: -4 spell, -8 hero, -0xC best, -0x10 best strength, -0x14 map, -0x18 index,
    -0x1C/-0x1B/-0x1A hero x/y/level, -0x20/-0x1F/-0x1E unit x/y/level."""
    src = f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        je   a_curse
        push ebp
        mov  ebp, esp
        add  esp, -0x18
        jmp  {AI_RESUME:#x}
    a_curse:
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        xor  eax, eax
        mov  dword ptr [ebp - 0xc], eax
        mov  dword ptr [ebp - 0x10], -1
        {{ANC}}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  dword ptr [ebp - 0x14], eax
        lea  eax, [ebp - 0x1a]
        push eax
        lea  ecx, [ebp - 0x1b]
        lea  edx, [ebp - 0x1c]
        mov  eax, dword ptr [ebp - 8]
        call {GETLOCATION:#x}
        mov  eax, dword ptr [ebp - 0x14]
        mov  eax, dword ptr [eax + 0xfc]
        mov  eax, dword ptr [eax + 0x10]
        mov  ecx, dword ptr [eax + 8]
        mov  dword ptr [ebp - 0x18], ecx
    a_unit:
        dec  dword ptr [ebp - 0x18]
        js   a_done
        mov  eax, dword ptr [ebp - 0x14]
        mov  eax, dword ptr [eax + 0xfc]
        mov  eax, dword ptr [eax + 0x10]
        mov  eax, dword ptr [eax + 4]
        mov  edx, dword ptr [ebp - 0x18]
        mov  esi, dword ptr [eax + edx*4]
        test esi, esi
        je   a_unit
        test byte ptr [esi + 0x25], 0x10
        jne  a_unit
        mov  cl, byte ptr [esi + 0x24]
        test cl, cl
        je   a_unit
        mov  edx, dword ptr [ebp - 8]
        mov  dl, byte ptr [edx + 0x24]
        cmp  cl, dl
        je   a_unit
        mov  eax, dword ptr [ebp - 0x14]
        mov  eax, dword ptr [eax + 0x140]
        call {GETDIPREL:#x}
        cmp  al, 1
        jne  a_unit
        mov  eax, dword ptr [esi + 4]
        test eax, eax
        je   a_unit
        test byte ptr [eax + 0x10], 0x10
        jne  a_unit
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        test al, al
        je   a_unit
        mov  eax, esi
        mov  edx, {CURSE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  a_unit
        lea  eax, [ebp - 0x1e]
        push eax
        lea  ecx, [ebp - 0x1f]
        lea  edx, [ebp - 0x20]
        mov  eax, esi
        call {GETLOCATION:#x}
        mov  al, byte ptr [ebp - 0x1e]
        cmp  al, byte ptr [ebp - 0x1a]
        jne  a_unit
        mov  eax, dword ptr [ebp - 4]
        cmp  dword ptr [eax + 0x38], -1
        je   a_inrange
        movsx eax, byte ptr [ebp - 0x1f]
        push eax
        movsx ecx, byte ptr [ebp - 0x20]
        movsx edx, byte ptr [ebp - 0x1b]
        movsx eax, byte ptr [ebp - 0x1c]
        call {DHXTORAD:#x}
        mov  edx, dword ptr [ebp - 4]
        cmp  eax, dword ptr [edx + 0x38]
        jg   a_unit
    a_inrange:
        mov  eax, esi
        mov  dx, word ptr [ebx + {{DTALL}}]
        call {GETSTRENGTHMAX:#x}
        cmp  eax, dword ptr [ebp - 0x10]
        jle  a_unit
        mov  dword ptr [ebp - 0x10], eax
        mov  dword ptr [ebp - 0xc], esi
        jmp  a_unit
    a_done:
        mov  esi, dword ptr [ebp - 0xc]
        test esi, esi
        je   a_none
        mov  eax, dword ptr [ebp + 0xc]
        mov  dword ptr [eax], esi
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xa0]
        movsx eax, al
        mov  edx, dword ptr [ebp - 4]
        add  eax, dword ptr [edx + 0x40]
        mov  edx, dword ptr [ebp + 8]
        mov  dword ptr [edx], eax
        mov  al, 1
        jmp  a_ret
    a_none:
        xor  eax, eax
    a_ret:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  8
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "DTALL": DTALL})


def build_aiown(va):
    """AIExecuteCastSpellAction: EBX = spell, ESI = hero, EDI = the TE, [EBP-0xC] = the target."""
    return asm(f"""
        mov  al, byte ptr [esi + 0x24]
        cmp  dword ptr [ebx + 0x10], {SPELL_ID}
        jne  o_set
        mov  eax, dword ptr [ebp - 0xc]
        mov  al, byte ptr [eax + 0x24]
    o_set:
        mov  byte ptr [edi + 0x28], al
        ret
    """, va)


def build_rw(va, orig, op, ptr_off, tag, only_curse):
    """A ReadWrite slot target: the original, then one more property.  op 0x2C = rwInteger,
    0x30 = rwByte (EAX stream, EDX ptr, ECX id)."""
    gate = f"""
        cmp  dword ptr [ebx + 0x1c], {CURSE:#x}
        jne  w_out
""" if only_curse else ""
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        call {orig:#x}
{gate}
        lea  edx, [ebx + {ptr_off:#x}]
        mov  ecx, {tag:#x}
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + {op:#x}]
    w_out:
        pop  esi
        pop  ebx
        ret
    """, va)


def build_reg_ench(va):
    src = f"""
        call {REGISTER_ABIL:#x}
        {{ANC}}
        push ecx
        lea  eax, [ecx + {{VMT}}]
        xor  ecx, ecx
        mov  dl, 1
        call {TUEA_CREATE:#x}
        pop  ecx
        push eax
        lea  edx, [ecx + {{NAME}}]
        add  eax, 8
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0xc], {CURSE:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABIL:#x}
        ret
    """
    return pic(src, va, "ecx", {"VMT": TUEA_VMT, "NAME": ("TAIL", 8)}, ansistr(CURSE_NAME))


def build_reg_spell(va):
    src = f"""
        call {REGISTER_SPELL:#x}
        {{ANC}}
        push ecx
        mov  eax, dword ptr [ecx + {{CELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {DARKGIFT_CREATE:#x}
        pop  ecx
        push eax
        lea  edx, [ecx + {{NAME}}]
        add  eax, 8
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0x10], {SPELL_ID}
        mov  dword ptr [eax + 0x14], {MANA}
        mov  dword ptr [eax + 0x18], {RESEARCH}
        mov  dword ptr [eax + 0x1c], {UPKEEP}
        mov  byte ptr [eax + 0x20], {SPHERE}
        mov  byte ptr [eax + 0x21], {TIER}
        mov  byte ptr [eax + 0x3c], {LEVEL}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        ret
    """
    return pic(src, va, "ecx", {"CELL": DARKGIFT_CELL, "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


def build_info(va):
    """TUnitSpell.GetCombatInfo's tail (EBX = the info, ESI = the spell): id 82 targets enemies in
    battle (byte 7 = 2; every unit spell reports 1, friendly).  Register-only."""
    return asm(f"""
        mov  byte ptr [ebx + 5], 0xff
        cmp  dword ptr [esi + 0x10], {SPELL_ID}
        jne  i_out
        mov  byte ptr [ebx + 7], 2
    i_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


# ---- layout -------------------------------------------------------------------------------------
def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b, room=None):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        assert room is None or len(b) <= room, "cave_%s outgrew its room" % n
        va = va + room if room else (va + len(b) + 0xF) & ~0xF

    put("cu", build_cu(va))
    put("dvc", build_dvc(va, at))
    put("isc", build_isc(va))
    put("event", build_event(va), room=0x100)       # its text moved to cave_lit at the rename
    put("spawn", build_spawn(va))
    put("turn", build_turn(va, at))
    put("sel", build_sel(va))
    put("post", build_post(va, at))
    put("vtu", build_vtu(va))
    put("vtp", build_vtp(va))
    put("roll", build_roll(va, at))
    put("refresh", build_refresh(va, at))
    put("raid", build_raid(va))
    put("cp", build_cp(va))
    put("join", build_join(va))
    put("death", build_death(va, at))
    put("m3", build_m3(va, at))
    put("s1", build_s1(va, at))
    put("ai", build_ai(va))
    put("aiown", build_aiown(va))
    put("ench_rw", build_rw(va, ENCH_RW, 0x2C, 0x14, TAG_CASTER, True))
    put("hunt_rw", build_rw(va, HUNT_RW, 0x30, 0x4F, TAG_MARK, False))
    put("raid_rw", build_rw(va, AIGROUP_RW, 0x30, 0x4F, TAG_MARK, False))
    put("reg_ench", build_reg_ench(va))
    put("reg_spell", build_reg_spell(va))
    put("lit", ansistr(EVENT_TEXT))
    put("info", build_info(va))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    rb = lambda va, n: d[P.va2off(d, va):P.va2off(d, va) + n]
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for va, want, what in (
            (0x557BCC54, bytes.fromhex("8bc3"), "`mov eax,ebx` before the ability registration site"),
            (0x557E8E21, bytes.fromhex("8bc3"), "`mov eax,ebx` before the spell registration site"),
            (0x557E8484, bytes.fromhex("8bd8"), "ExecuteSpell's `mov ebx,eax` (EBX = the spell)"),
            (0x557E84B8, bytes.fromhex("8b7010"), "ExecuteSpell's `mov esi,[eax+0x10]` (ESI = enchantment)"),
            (0x5577CE4B, bytes.fromhex("8bc6"), "NewTurn's `mov eax,esi` before SetMana"),
            (0x5577B668, bytes.fromhex("8bd8"), "AIExecuteCastSpellAction's `mov ebx,eax`"),
            (0x557808A6, bytes.fromhex("8bc3"), "Killed's `mov eax,ebx`")):
        if rb(va, len(want)) != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))
    for cell in (DARKGIFT_CELL, CU_CELL, ARMYHS_CELL, UNIT_CELL, EVLOG_CELL):
        v = rd(cell)
        if rd(v - 0x40) != v:
            sys.exit("ABORT: %08X does not hold a class" % cell)
    for vmt, size in ((TUE_VMT, 0x20), (TUEA_VMT, 0x28)):
        if rd(vmt - 0x40) != vmt or rd(vmt - 0x1C) != size:
            sys.exit("ABORT: %08X is not the expected VMT" % vmt)
    if rd(0x5571B8D0 - 0x1C) != 0x54 or rd(0x557D87A4 - 0x1C) != 0x50:
        sys.exit("ABORT: THuntAG / TRaidAG instance sizes moved (the +0x4F marker needs 0x54 / 0x50)")
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # nobody else creates spell 82 or ability 0x5B
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i:i + 3] == b"\xc7\x40\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
            if d[i:i + 3] == b"\xc7\x40\x0c" and struct.unpack_from("<I", d, i + 3)[0] == CURSE:
                sys.exit("ABORT: %08X also stores ability id %#x" % (src, CURSE))
    dual = rb(0x558B6000, 0x100)
    if not any(struct.unpack_from("<HBB", dual, k) == (SPELL_ID, 2, 5) for k in range(0, 0xFC, 4)):
        sys.exit("ABORT: build_dual_sphere.py's TABLE does not list spell %d as Death/Fire" % SPELL_ID)


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
_call_sites = {"reg_ench": "reg_ench", "reg_spell": "reg_spell", "sel1": "sel", "sel2": "sel",
               "post": "post", "roll": "roll", "death": "death", "aiown": "aiown"}
_jmp_sites = {"vtu": "vtu", "vtp": "vtp", "refresh": "refresh", "raid": "raid", "cp": "cp",
              "join": "join", "m3": "m3", "s1": "s1", "ai": "ai", "info": "info"}
HOOKS = []
for name, (va, van, _lo, _hi) in SITES.items():
    if name in _call_sites:
        new = call_to(va, AT[_call_sites[name]])
        new += b"\x90" * (len(van) - len(new))
    else:
        new = jmp_to(va, AT[_jmp_sites[name]], len(van))
    HOOKS.append((va, van, new))
for name, (va, orig) in VMT_SLOTS.items():
    HOOKS.append((va, struct.pack("<I", orig), struct.pack("<I", AT[name])))
INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, lo, hi) in SITES.items()]
RELOC_OK = tuple(va for va, _o in VMT_SLOTS.values())
ENTRY = {"cu": 0x558B7000, "dvc": 0x558B7030, "isc": 0x558B7090, "event": 0x558B70B0,
         "spawn": 0x558B71B0, "turn": 0x558B73E0, "sel": 0x558B74D0, "post": 0x558B74F0,
         "vtu": 0x558B7540, "vtp": 0x558B7590, "roll": 0x558B75C0, "refresh": 0x558B7610,
         "raid": 0x558B76B0, "cp": 0x558B7700, "join": 0x558B7720, "death": 0x558B7750,
         "m3": 0x558B77F0, "s1": 0x558B7820, "ai": 0x558B7850, "aiown": 0x558B79D0,
         "ench_rw": 0x558B79F0, "hunt_rw": 0x558B7A20, "raid_rw": 0x558B7A40,
         "reg_ench": 0x558B7A60, "reg_spell": 0x558B7AC0, "lit": EVENT_LIT, "info": 0x558B7B70}
assert AT == ENTRY, "the cave layout moved (the docstring's RNG sites move with it)"
assert max(va + len(b) for _n, va, b in CAVES) <= SLOT[1]

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    print("  slot used: %d of %d B" % (max(va + len(b) for _n, va, b in CAVES) - SLOT[0], SLOT[1] - SLOT[0]))
    checks()
    run("build_demon_curse", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:], reloc_ok=RELOC_OK)
