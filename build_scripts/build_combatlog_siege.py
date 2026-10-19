#!/usr/bin/env python
r"""
build_combatlog_siege.py -- manual-combat log lines for missile interception, siege damage to walls,
gates and structures, and the breach.  AoWTCPCK.dpl + AoWEPACK.dpl.  Combat-log package P4, 2026-10-14.

    Archer's shot at Orc is intercepted by Swordsman  (30% chance)
    Wizard's Fire Bolt at Orc hits the Wall  (40% chance)
    Catapult hits Wall for 9 damage  (90%, 12 ATK vs 0 DEF)
    Catapult CRITS Gate for 14 damage  (90%, 12 ATK vs 0 DEF)
    Catapult misses Wall - fumble  (90%, 12 ATK vs 0 DEF)
    Wizard casts Tremors on Structure for 6 damage  (65%, 10 ATK vs 7 DEF)
    Wizard casts Great Hail but misses Wall  (90%, 14 ATK vs 0 DEF)
    Fire burns Wall for 2 damage  (90%, 20 ATK vs 0 DEF)
    The Wall is breached          The Gate is breached          The Structure is destroyed

Live manual battles only (cl_emit's gate); none of these events exists in auto-resolve as such
(auto-resolve has no interception, and its wall damage is a damage CA that the replay already logs).

WHY THEY WERE MISSING
    The live log is written at the TDamageCA.Generate tails.  None of these events builds a CA:
    * NextStrike (CombatTE.TCAbRangedTE.NextStrike @0x40D290) rolls each block record of a shot's
      path with TAoWHSMap.Random(100) (SYNCED, vanilla) and, on a hit, either retargets the strike
      to the blocking unit or nils its target (absorbed by a wall, gate, structure or terrain).
      An intercepted shot then logs as an ordinary hit on the new victim, with no note.
    * A siege shot, blast or fire tick that lands on a wall / gate / structure hex sends a map-field
      message; TCityWall.MapFieldMsgProc @0x405D04 and TCombatStructure.MapFieldMsgProc @0x432AA8
      roll inline (GetCombatInfo -> reseed -> ExecuteDamageRole(DAM, ATK - GetDefense)) and call
      SetHitPoints(HP - dealt).  TCombatTerrain.MapFieldMsgProc does the same but its SetHitPoints
      @0x410138 discards the value (trees never take damage).

THE HOOKS -- AoWTCPCK (all reloc-free; each scanned for foreign jumps into its interior, jump tables
included, with a skipdata disassembly of the whole function)
    0x40F079  6 B `mov eax,[ebp-0x54] ; mov eax,[eax+0x1C]`      intercepted (blocker is a
              TTacticalCombatUnitHS): cave_int.  Frame: [ebp-4] TE (+0x10 shooter combat unit),
              [ebp-0x10] the strike effect (+0x2C intended target, read before vanilla overwrites
              it; +0x14 ability id, 0x34 = a spell, then +0x18 = spell id; +0x34 category),
              [ebp-0x54] blocker HS (+0x1C its combat unit), [ebp-0x60] block record (+8 chance %).
              No line when the blocker IS the intended target.
    0x40F05E  8 B `mov eax,[ebp-0x10] ; xor edx,edx ; mov [eax+0x2C],edx`   absorbed: cave_abs.
              Blocker by IsClass of [ebp-0x54]: TCityWallDoor (cell 0x40526C) "Gate", TCityWall
              (0x404FC8) "Wall", TCombatStructure (0x43254C) "a Structure", else (TCombatTerrain or
              nil = terrain id 0xF/7, overlay 8) "an obstacle".  The door is tested first (it
              descends from TCityWall); TCombatStructure answers the same class id 0x220506 as the
              door, which is why the class test and not the message decides.
              Category 5 (Flame Throwing, the five breaths) is SKIPPED: its blocker is always nil,
              its target is nilled after the loop anyway, and 20 sweep strikes per breath would
              flood the log.  (0x40F04C is NOT used: .reloc at 0x40F051.)
    0x405AE4  6 B prologue of TCityWall.SetHitPoints      -> cave_wall -> sg_common (tkind 0/1)
    0x432930  6 B prologue of TCombatStructure.SetHitPoints -> cave_str -> sg_common (tkind 2)
              EAX = object, EDX = new HP (HP - dealt, unclamped), [obj+0x20] = old HP, EBP = the
              caller's frame.  sg_common looks the RETURN ADDRESS up in a per-function table that
              this script derives from the live MapFieldMsgProc (capstone, skipdata) and asserts
              against the expected list below:
                kind 1 ability, fixed id   ATK [ebp-0xD], DAM [ebp-0xC]
                kind 2 spell,   fixed id   ATK [ebp-0x16], DAM [ebp-0x15]; spell id in the table
                kind 4 ability, id [msg+0xC]   kind 5 spell, id [msg+0xC]     ([ebp-8] = message)
                kind 3 fire tick (0x31007)  ATK [[0x4693C4]+4] = TCAttack[1], DAM [[0x4693FC]+4]
              Source = [msg+8] (vanilla itself dereferences its +0x4C, so it is a TCombatUnit);
              the fire tick's source is a TCombatFire and is not read ("Fire").
              DEF: TCityWall.GetDefense 0x405ACC (constant 0, build_walldef0.py) / TCombatILTerrain.GetDefense
              0x404914 (signed byte [[obj+8]+0x45]) -- the same pure getters vanilla just called.
              Return addresses NOT in the table are left alone: Wall Crushing 0x40A29F (logged by
              build_combatlog_wallcrush.py, which also resets the roll), TCityWall.Activate
              0x4056FD/0x405727, TCombatStructure.Create/Activate (initialisation).
    0x410138  6 B prologue of TCombatTerrain.SetHitPoints -> cave_ter: cl_take_roll only (W3).

THE LINES -- AoWEPACK, fixed entries (each a jmp, 8 B):
    0x5589D000  sg_log(EAX = @rec)   rec: +0 source (0 = fire) +4 tkind (0 Wall, 1 Gate, 2 Structure)
                +8 spell id (-1 ability, -2 fire) +0xC old HP +0x10 new HP (raw) +0x14 ATK +0x18 DEF
                +0x1C DAM.  ALWAYS calls cl_take_roll first, so every inline wall/structure roll
                is consumed whatever happens next (W3).  DAM <= 0 -> ExecuteDamageRole drew nothing
                -> the roll is treated as none.  Nothing printed when old HP <= 0 (rubble) or not
                live.  dealt = old - new (the roll's damage, as unit lines show it, not clamped).
                Roll >= 18 -> CRITS (BURNS for fire); dealt 0 with roll <= 1 -> " - fumble".
                Spells read as the live logger's spell lines (" casts <Spell> on " / " but misses ").
                new <= 0 -> second line "The Wall/Gate is breached" / "The Structure is destroyed".
    0x5589D008  ms_log(EAX = @rec)   rec: +0 kind (1 intercepted, 2 absorbed) +4 shooter +8 intended
                target (0 = none) +0xC blocker combat unit (1) / blocker class 0..3 (2) +0x10 spell
                id (-1 = not a spell) +0x14 block chance %.
    Names via cl_name; spell names via TSpellControl.GetSpell ([AoWHSSet]+0x84, 0x55779AC8,
    +0x08 name) with every step nil/negative-guarded (GetSpell raises on a negative id).
    Reached from AoWTCPCK by the rebase delta: [IAT cell 0x46E7F4 = AoWE.ExecuteDamageRole 0x55725EAC]
    + (entry - 0x55725EAC), as build_combatlog_wallcrush.py does.

Rolls: none drawn, no game state written; the interception roll and every damage roll are vanilla's.
P1-P5 selection test: not applicable (no draw).  The only state touched is SCRATCH_R (cl_take_roll)
and the exe ring.  PIC: TC caves use one call/pop delta anchor each (class cells, TCAttack/TCDamage
cells and the IAT cell read through it; the table addresses are immediates plus the delta); AoWEPACK
bodies use one anchor each for literals, AoWHSSet and nothing else.  No absolute DLL operand.

Caves: AoWEPACK 0x5589D000-0x5589D7FF exclusive (stubs, literals 0x5589D010, sg_log 0x5589D290,
ms_log 0x5589D4F0); AoWTCPCK 0x0043B200-0x0043B5BF exclusive (cave_int 0x43B200, cave_abs 0x43B278,
cave_wall 0x43B34C, cave_str 0x43B368, cave_ter 0x43B384, sg_common 0x43B3AC, tables 0x43B4B4).
--apply writes AoWEPACK first; --undo unhooks AoWTCPCK first.  The AoWEPACK half has no hook, so its
dry run prints "state: VANILLA" even when installed -- read its "slot: our caves" line instead.
Applied 2026-10-14; --undo/--apply round trip, build_relocfix.py --audit (0) and rng_audit.py
--owners (no new site) clean.
No writable state (the TC BSS 0x46C920-0x46C9FF offered to P4 is NOT used).
Requires build_combatlog_lib.py (cl_* entries 0x5589AC00..) and build_combatlog_dll.py's roll capture.

FORWARD HAZARDS
  * Undo this script before build_combatlog_lib.py: its caves call cl_* by rel32 and the lib's
    --undo cannot see callers reached from another module by the delta.
  * The SetHitPoints dispatch tables are keyed on return addresses inside the two MapFieldMsgProcs:
    any later patch that moves or retargets a SetHitPoints call there must re-run this script (the
    scan asserts the expected list and aborts on any change).
  * build_combatlog_wallcrush.py owns the Wall Crushing call (return 0x40A29F); the two must stay
    disjoint -- do not add 0x40A29F to the table.

    python build_scripts/build_combatlog_siege.py            dry run + state, both modules
    python build_scripts/build_combatlog_siege.py --apply
    python build_scripts/build_combatlog_siege.py --undo
    python build_scripts/build_combatlog_siege.py --dis
"""
import os, re, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

E_SLOT = (0x5589D000, 0x5589D800)
T_SLOT = (0x0043B200, 0x0043B5C0)

# ---- AoWEPACK ------------------------------------------------------------------------------
EDR = 0x55725EAC                 # AoWE.ExecuteDamageRole (export; the rebase-delta reference)
CL = {"cl_emit": 0x5589AC00, "cl_name": 0x5589AC10, "cl_live": 0x5589AC20,
      "cl_take_roll": 0x5589AC28, "cl_cat_int": 0x5589AC30}
LSTRLASG = 0x55701158            # eax=@dest, edx=src value
LSTRCAT = 0x55701188             # eax=@dest, edx=src value
LSTRARRCLR = 0x55701148          # eax=@first, edx=count
AOWHSSET = 0x558FA044            # AoWE.AoWHSSet (a pointer cell); TSpellControl at +0x84
SPELLCTRL_OFF = 0x84
GETSPELL = 0x55779AC8            # TSpellControl.GetSpell(eax=ctrl, edx=id) -> TSpell / 0; raises if id < 0
SPELL_NAME = 0x08                # TSpell+0x08 = name LStr value
STUB_SG, STUB_MS = 0x5589D000, 0x5589D008
LIT_VA = 0x5589D010

LIT = [("FIRE", "Fire"),
       ("HITS", " hits "), ("CRITS", " CRITS "), ("MISSES", " misses "),
       ("BURNS", " burns "), ("BURNSC", " BURNS "), ("FAILBURN", " fails to burn "),
       ("CASTS", " casts "), ("ONTGT", " on "), ("BUTMISS", " but misses "),
       ("WALL", "Wall"), ("GATE", "Gate"), ("STRUCT", "Structure"),
       ("FOR", " for "), ("DAMAGE", " damage"), ("FUMBLE", " - fumble"),
       ("OPEN", "  ("), ("PCT", "%, "), ("ATKVS", " ATK vs "), ("VSDEF", " DEF)"),
       ("BR_WALL", "The Wall is breached"), ("BR_GATE", "The Gate is breached"),
       ("BR_STRUCT", "The Structure is destroyed"),
       ("POSS", "'s "), ("SHOT", "'s shot"), ("AT", " at "), ("INTBY", " is intercepted by "),
       ("H_WALL", " hits the Wall"), ("H_GATE", " hits the Gate"),
       ("H_STRUCT", " hits a Structure"), ("H_OBST", " hits an obstacle"),
       ("CHANCE", "% chance)")]


def _check_contract():
    here = os.path.dirname(os.path.abspath(__file__))
    t = open(os.path.join(here, "build_combatlog_lib.py")).read()
    for n, va in CL.items():
        assert re.search(r"0x%X\s+%s\b" % (va, n), t), "lib entry %s moved" % n
    t = open(os.path.join(here, "build_combatlog_dll.py")).read()
    assert re.search(r"GETSPELL\s*=\s*0x55779AC8", t) and re.search(r"AOWHSSET\s*=\s*0x558FA044", t)


_check_contract()


def lstr(s):
    b = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def anchor(reg, at):
    return f"call 0x{at + 5:X}\npop {reg}\nsub {reg}, 0x{at + 5:X}\n"


def r(reg, va):
    return f"[{reg} + 0x{va:X}]"


def e_caves():
    data, lit = bytearray(), {}
    for k, s in LIT:
        lit[k] = LIT_VA + len(data) + 8
        data += lstr(s)
    L = lambda k: r("edi", lit[k])
    va = (LIT_VA + len(data) + 0xF) & ~0xF

    pre = """
        push ebp
        mov  ebp, esp
        sub  esp, 0x18
        push ebx
        push esi
        push edi
        mov  esi, eax
        xor  eax, eax
        mov  [ebp-0x04], eax
        mov  [ebp-0x08], eax
        mov  [ebp-0x0C], eax"""
    post = f"""
        lea  eax, [ebp-0x0C]
        mov  edx, 3
        call 0x{LSTRARRCLR:X}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret"""

    def cat(k):
        return f"lea eax, [ebp-0x04]\nlea edx, {L(k)}\ncall 0x{LSTRCAT:X}\n"

    def cat_int(src):
        return f"mov edx, {src}\nlea eax, [ebp-0x04]\ncall 0x{CL['cl_cat_int']:X}\n"

    def getspell(idsrc, tag):
        return f"""
        mov  edx, {idsrc}
        test edx, edx
        js   {tag}
        mov  eax, {r('edi', AOWHSSET)}
        test eax, eax
        jz   {tag}
        mov  eax, [eax+0x{SPELLCTRL_OFF:X}]
        test eax, eax
        jz   {tag}
        call 0x{GETSPELL:X}
        test eax, eax
        jz   {tag}
        mov  edx, [eax+0x{SPELL_NAME:X}]
        test edx, edx
        jz   {tag}
        lea  eax, [ebp-0x0C]
        call 0x{LSTRLASG:X}
    {tag}:"""

    # ---- sg_log ----
    sg_va = va
    at = sg_va + len(asm(pre, sg_va))
    sg = pre + "\n" + anchor("edi", at) + f"""
        call 0x{CL['cl_take_roll']:X}
        mov  [ebp-0x10], eax
        cmp  dword ptr [esi+0x1C], 0
        jg   sg_r
        mov  dword ptr [ebp-0x10], -1
    sg_r:
        cmp  dword ptr [esi+0x0C], 0
        jle  sg_done
        call 0x{CL['cl_live']:X}
        test eax, eax
        jz   sg_done
        mov  eax, [esi+0x0C]
        sub  eax, [esi+0x10]
        mov  [ebp-0x14], eax
        {getspell("[esi+0x08]", "sg_nosp")}
        mov  eax, [esi]
        test eax, eax
        jnz  sg_src
        lea  eax, [ebp-0x04]
        lea  edx, {L('FIRE')}
        call 0x{LSTRLASG:X}
        jmp  sg_verb
    sg_src:
        lea  edx, [ebp-0x04]
        call 0x{CL['cl_name']:X}
    sg_verb:
        cmp  dword ptr [ebp-0x0C], 0
        jne  sg_spell
        cmp  dword ptr [esi+0x08], -2
        je   sg_fire
        lea  edx, {L('MISSES')}
        cmp  dword ptr [ebp-0x14], 0
        jle  sg_cat
        lea  edx, {L('HITS')}
        cmp  dword ptr [ebp-0x10], 18
        jl   sg_cat
        lea  edx, {L('CRITS')}
        jmp  sg_cat
    sg_fire:
        lea  edx, {L('FAILBURN')}
        cmp  dword ptr [ebp-0x14], 0
        jle  sg_cat
        lea  edx, {L('BURNS')}
        cmp  dword ptr [ebp-0x10], 18
        jl   sg_cat
        lea  edx, {L('BURNSC')}
        jmp  sg_cat
    sg_spell:
        {cat('CASTS')}
        lea  eax, [ebp-0x04]
        mov  edx, [ebp-0x0C]
        call 0x{LSTRCAT:X}
        lea  edx, {L('BUTMISS')}
        cmp  dword ptr [ebp-0x14], 0
        jle  sg_cat
        lea  edx, {L('ONTGT')}
    sg_cat:
        lea  eax, [ebp-0x04]
        call 0x{LSTRCAT:X}
        lea  edx, {L('WALL')}
        cmp  dword ptr [esi+0x04], 1
        jne  sg_t2
        lea  edx, {L('GATE')}
    sg_t2:
        cmp  dword ptr [esi+0x04], 2
        jne  sg_t3
        lea  edx, {L('STRUCT')}
    sg_t3:
        lea  eax, [ebp-0x04]
        call 0x{LSTRCAT:X}
        cmp  dword ptr [ebp-0x14], 0
        jle  sg_miss
        {cat('FOR')}
        {cat_int('[ebp-0x14]')}
        {cat('DAMAGE')}
        jmp  sg_stats
    sg_miss:
        mov  eax, [ebp-0x10]
        test eax, eax
        js   sg_stats
        cmp  eax, 1
        jg   sg_stats
        {cat('FUMBLE')}
    sg_stats:
        {cat('OPEN')}
        mov  eax, [esi+0x14]
        sub  eax, [esi+0x18]
        imul eax, eax, 5
        add  eax, 50
        cmp  eax, 10
        jge  sg_p1
        mov  eax, 10
    sg_p1:
        cmp  eax, 90
        jle  sg_p2
        mov  eax, 90
    sg_p2:
        {cat_int('eax')}
        {cat('PCT')}
        {cat_int('[esi+0x14]')}
        {cat('ATKVS')}
        {cat_int('[esi+0x18]')}
        {cat('VSDEF')}
        mov  eax, [ebp-0x04]
        call 0x{CL['cl_emit']:X}
        cmp  dword ptr [esi+0x10], 0
        jg   sg_done
        lea  eax, {L('BR_WALL')}
        cmp  dword ptr [esi+0x04], 1
        jne  sg_b2
        lea  eax, {L('BR_GATE')}
    sg_b2:
        cmp  dword ptr [esi+0x04], 2
        jne  sg_b3
        lea  eax, {L('BR_STRUCT')}
    sg_b3:
        call 0x{CL['cl_emit']:X}
    sg_done:""" + post
    sg_blob = asm(sg, sg_va)

    # ---- ms_log ----
    ms_va = (sg_va + len(sg_blob) + 0xF) & ~0xF
    at = ms_va + len(asm(pre, ms_va))
    ms = pre + "\n" + anchor("edi", at) + f"""
        call 0x{CL['cl_live']:X}
        test eax, eax
        jz   ms_done
        mov  eax, [esi+0x04]
        lea  edx, [ebp-0x04]
        call 0x{CL['cl_name']:X}
        {getspell("[esi+0x10]", "ms_nosp")}
        cmp  dword ptr [ebp-0x0C], 0
        je   ms_shot
        {cat('POSS')}
        lea  eax, [ebp-0x04]
        mov  edx, [ebp-0x0C]
        call 0x{LSTRCAT:X}
        jmp  ms_at
    ms_shot:
        {cat('SHOT')}
    ms_at:
        mov  eax, [esi+0x08]
        test eax, eax
        jz   ms_kind
        lea  edx, [ebp-0x08]
        call 0x{CL['cl_name']:X}
        {cat('AT')}
        lea  eax, [ebp-0x04]
        mov  edx, [ebp-0x08]
        call 0x{LSTRCAT:X}
    ms_kind:
        cmp  dword ptr [esi], 1
        jne  ms_abs
        {cat('INTBY')}
        mov  eax, [esi+0x0C]
        lea  edx, [ebp-0x08]
        call 0x{CL['cl_name']:X}
        lea  eax, [ebp-0x04]
        mov  edx, [ebp-0x08]
        call 0x{LSTRCAT:X}
        jmp  ms_pct
    ms_abs:
        mov  eax, [esi+0x0C]
        lea  edx, {L('H_OBST')}
        cmp  eax, 0
        jne  ms_a1
        lea  edx, {L('H_WALL')}
    ms_a1:
        cmp  eax, 1
        jne  ms_a2
        lea  edx, {L('H_GATE')}
    ms_a2:
        cmp  eax, 2
        jne  ms_a3
        lea  edx, {L('H_STRUCT')}
    ms_a3:
        lea  eax, [ebp-0x04]
        call 0x{LSTRCAT:X}
    ms_pct:
        {cat('OPEN')}
        {cat_int('[esi+0x14]')}
        {cat('CHANCE')}
        mov  eax, [ebp-0x04]
        call 0x{CL['cl_emit']:X}
    ms_done:""" + post
    ms_blob = asm(ms, ms_va)

    stubs = jmp_to(STUB_SG, sg_va, 5) + b"\xCC" * 3 + jmp_to(STUB_MS, ms_va, 5) + b"\xCC" * 3
    return [("stubs", STUB_SG, stubs), ("literals", LIT_VA, bytes(data)),
            ("sg_log", sg_va, sg_blob), ("ms_log", ms_va, ms_blob)]


E_CAVES = e_caves()

# ---- AoWTCPCK ------------------------------------------------------------------------------
IAT_EDR = 0x0046E7F4             # IAT cell of AoWE.ExecuteDamageRole (thunk 0x4024F4)
IS_CLASS_T = 0x00401058          # VCL30 System.@IsClass thunk (eax=obj, edx=class) -> al
CELL_DOOR, CELL_WALL, CELL_STRUCT = 0x0040526C, 0x00404FC8, 0x0043254C   # class-ref cells (.reloc)
VMT_DOOR, VMT_WALL, VMT_STRUCT = 0x004052AC, 0x00405008, 0x0043258C
CELL_TCATTACK, CELL_TCDAMAGE = 0x004693C4, 0x004693FC                     # -> AoWTC.TCAttack/TCDamage
WALL_GETDEF, IL_GETDEF = 0x00405ACC, 0x00404914
SHP_EDR_THUNK = 0x004024F4
GETABILITY_T, GETSPELL_T = 0x00402704, 0x004029B4

H_INT, V_INT, R_INT = 0x0040F079, bytes.fromhex("8b45ac8b401c"), 0x0040F07F
H_ABS, V_ABS, R_ABS = 0x0040F05E, bytes.fromhex("8b45f033d289502c"), 0x0040F066
H_WALL, V_WALL, R_WALL = 0x00405AE4, bytes.fromhex("558bec83c4f0"), 0x00405AEA
H_STR, V_STR, R_STR = 0x00432930, bytes.fromhex("558bec83c4f0"), 0x00432936
H_TER, V_TER, R_TER = 0x00410138, bytes.fromhex("558bec83c4f8"), 0x0041013E
FN_NEXTSTRIKE = (0x0040D290, 0x0040F4B0)
FN_WALLSHP = (0x00405AE4, 0x00405CB2)
FN_STRSHP = (0x00432930, 0x00432A5E)
FN_TERSHP = (0x00410138, 0x0041014F)
MFMP_WALL = (0x00405D04, 0x004062FC)
MFMP_STR = (0x00432AA8, 0x004331CC)

AB, SP, FIRE, ABM, SPM = 1, 2, 3, 4, 5
EXPECT_WALL = [(0x405DF8, AB, 0x41), (0x405E76, AB, 0x18), (0x405EF4, AB, 0x2C), (0x405F6F, SP, 0x75),
               (0x405FFA, AB, 0x1F), (0x406082, SP, 0x71), (0x4060FD, SP, 0x74), (0x406178, SP, 0x7F),
               (0x406200, SP, 0x80), (0x40628B, SP, 0x70), (0x4062F7, FIRE, 0)]
EXPECT_STR = [(0x432BB3, AB, 0x41), (0x432C34, AB, 0x18), (0x432CB5, AB, 0x2C), (0x432D33, SP, 0x75),
              (0x432DB4, AB, 0x1F), (0x432E32, SP, 0x71), (0x432ECA, ABM, 0), (0x432F56, SPM, 0),
              (0x432FD4, SP, 0x74), (0x433052, SP, 0x7F), (0x4330D0, SP, 0x80), (0x43315E, SP, 0x70),
              (0x4331C4, FIRE, 0)]


def _tc_bytes():
    P.IMAGE_BASE = 0x400000
    return open(TCPCK, "rb").read()


def scan_table(d, fn, shp, expect):
    """Derive (ret, kind, atk_off, id) for every SetHitPoints call in a MapFieldMsgProc and assert
    the pattern vanilla uses: id -> GetAbility/GetSpell -> GetCombatInfo -> ExecuteDamageRole with
    ATK [ebp+off] / DAM [ebp+off+1], or the fire tick's TCAttack/TCDamage cells."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    o = P.va2off(d, fn[0])
    ins = list(md.disasm(bytes(d[o:o + fn[1] - fn[0]]), fn[0]))
    out, st, prev = [], {}, None
    for x in ins:
        s = "%s %s" % (x.mnemonic, x.op_str)
        if x.mnemonic == "call" and x.op_str in (hex(GETABILITY_T), hex(GETSPELL_T)):
            kind = AB if x.op_str == hex(GETABILITY_T) else SP
            if prev == "mov edx, dword ptr [edx + 0xc]":
                st = {"kind": kind + 3, "id": 0}
            else:
                m = re.fullmatch(r"mov edx, (0x[0-9a-f]+)", prev or "")
                assert m, "no id before GetAbility/GetSpell at %08X: %s" % (x.address, prev)
                st = {"kind": kind, "id": int(m.group(1), 16)}
        m = re.fullmatch(r"movsx edx, byte ptr \[ebp - (0x[0-9a-f]+)\]", s)
        if m:
            st["atk"] = -int(m.group(1), 16)
        m = re.fullmatch(r"movsx eax, byte ptr \[ebp - (0x[0-9a-f]+)\]", s)
        if m:
            st["dam"] = -int(m.group(1), 16)
        if s == "mov edx, dword ptr [0x%x]" % CELL_TCATTACK:
            st = {"kind": FIRE, "id": 0, "atk": 0, "dam": 1}
        if x.mnemonic == "call" and x.op_str == hex(SHP_EDR_THUNK):
            st["edr"] = True
        if x.mnemonic == "call" and x.op_str == hex(shp):
            assert st.get("edr") and "atk" in st and st.get("dam") == st["atk"] + 1, \
                "SetHitPoints call %08X: unexpected pattern %r" % (x.address, st)
            out.append((x.address + 5, st["kind"], st["atk"], st["id"]))
            st = {}
        if s.startswith("mov edx, ") or x.mnemonic == "call":
            prev = s                      # the last EDX load (or call) before the next call
    got = [(a, k, i) for a, k, _o, i in out]
    assert got == expect, "MapFieldMsgProc %08X changed:\n  got    %s\n  expect %s" % (
        fn[0], [(hex(a), k, hex(i)) for a, k, i in got], [(hex(a), k, hex(i)) for a, k, i in expect])
    return b"".join(struct.pack("<IBbH", a, k, off, i) for a, k, off, i in out) + b"\0" * 8


def t_caves():
    d = _tc_bytes()
    for cell, vmt in ((CELL_DOOR, VMT_DOOR), (CELL_WALL, VMT_WALL), (CELL_STRUCT, VMT_STRUCT)):
        assert struct.unpack_from("<I", d, P.va2off(d, cell))[0] == vmt and P.relocs_in(d, cell, cell + 4) == [cell]
    o = P.va2off(d, VMT_DOOR - 0x18)
    assert struct.unpack_from("<I", d, o)[0] == CELL_WALL, "TCityWallDoor no longer descends from TCityWall"
    tab_w = scan_table(d, MFMP_WALL, H_WALL, EXPECT_WALL)
    tab_s = scan_table(d, MFMP_STR, H_STR, EXPECT_STR)

    sg_off = (E_CAVES[0][1] - EDR) & 0xFFFFFFFF
    ms_off = (STUB_MS - EDR) & 0xFFFFFFFF
    tr_off = (CL["cl_take_roll"] - EDR) & 0xFFFFFFFF

    def ms_tail(tag):
        return f"""
        mov  eax, -1
        cmp  dword ptr [ecx+0x14], 0x34
        jne  {tag}
        mov  eax, [ecx+0x18]
    {tag}:
        mov  [esp+0x10], eax
        mov  eax, [ebp-0x60]
        mov  eax, [eax+8]
        mov  [esp+0x14], eax
        mov  eax, esp
        mov  ecx, [ebx+0x{IAT_EDR:X}]
        add  ecx, 0x{ms_off:X}
        call ecx"""

    def build(layout):
        caves, va = [], T_SLOT[0]
        srcs = {}
        # cave_int
        def c_int(va):
            pre = "pushad"
            at = va + len(asm(pre, va))
            return pre + "\n" + anchor("ebx", at) + f"""
        sub  esp, 0x18
        mov  dword ptr [esp], 1
        mov  eax, [ebp-4]
        mov  eax, [eax+0x10]
        mov  [esp+4], eax
        mov  ecx, [ebp-0x10]
        mov  eax, [ecx+0x2C]
        mov  [esp+8], eax
        mov  eax, [ebp-0x54]
        mov  eax, [eax+0x1C]
        mov  [esp+0x0C], eax
        cmp  eax, [esp+8]
        je   ci_skip
        {ms_tail("ci_sp")}
    ci_skip:
        add  esp, 0x18
        popad
        mov  eax, [ebp-0x54]
        mov  eax, [eax+0x1C]
        jmp  0x{R_INT:X}"""

        def c_abs(va):
            pre = "pushad"
            at = va + len(asm(pre, va))
            return pre + "\n" + anchor("ebx", at) + f"""
        mov  ecx, [ebp-0x10]
        cmp  byte ptr [ecx+0x34], 5
        je   ca_out
        sub  esp, 0x18
        mov  dword ptr [esp], 2
        mov  eax, [ebp-4]
        mov  eax, [eax+0x10]
        mov  [esp+4], eax
        mov  eax, [ecx+0x2C]
        mov  [esp+8], eax
        mov  dword ptr [esp+0x0C], 3
        mov  esi, [ebp-0x54]
        test esi, esi
        jz   ca_k
        mov  eax, esi
        mov  edx, [ebx+0x{CELL_DOOR:X}]
        call 0x{IS_CLASS_T:X}
        test al, al
        jz   ca_n1
        mov  dword ptr [esp+0x0C], 1
        jmp  ca_k
    ca_n1:
        mov  eax, esi
        mov  edx, [ebx+0x{CELL_WALL:X}]
        call 0x{IS_CLASS_T:X}
        test al, al
        jz   ca_n2
        mov  dword ptr [esp+0x0C], 0
        jmp  ca_k
    ca_n2:
        mov  eax, esi
        mov  edx, [ebx+0x{CELL_STRUCT:X}]
        call 0x{IS_CLASS_T:X}
        test al, al
        jz   ca_k
        mov  dword ptr [esp+0x0C], 2
    ca_k:
        mov  ecx, [ebp-0x10]
        {ms_tail("ca_sp")}
        add  esp, 0x18
    ca_out:
        popad
        mov  eax, [ebp-0x10]
        xor  edx, edx
        mov  [eax+0x2C], edx
        jmp  0x{R_ABS:X}"""

        def c_shp(tab, tkind, resume):
            def f(va):
                return f"""
        pushad
        mov  ecx, 0x{layout.get(tab, 0):X}
        mov  edx, {tkind}
        call 0x{layout.get('sg_common', va):X}
        popad
        push ebp
        mov  ebp, esp
        add  esp, -0x10
        jmp  0x{resume:X}"""
            return f

        def c_ter(va):
            pre = "pushad"
            at = va + len(asm(pre, va))
            return pre + "\n" + anchor("ebx", at) + f"""
        mov  ecx, [ebx+0x{IAT_EDR:X}]
        add  ecx, 0x{tr_off:X}
        call ecx
        popad
        push ebp
        mov  ebp, esp
        add  esp, -8
        jmp  0x{R_TER:X}"""

        def c_common(va):
            at = va
            return anchor("ebx", at) + f"""
        add  ecx, ebx
        mov  edi, ecx
        mov  esi, edx
        mov  eax, [esp+0x24]
        sub  eax, ebx
    sc_lk:
        mov  ecx, [edi]
        test ecx, ecx
        jz   sc_ret
        cmp  ecx, eax
        je   sc_found
        add  edi, 8
        jmp  sc_lk
    sc_found:
        sub  esp, 0x20
        mov  [esp+4], esi
        mov  esi, [esp+0x40]
        xor  eax, eax
        cmp  byte ptr [edi+4], {FIRE}
        je   sc_src
        mov  eax, [ebp-8]
        mov  eax, [eax+8]
    sc_src:
        mov  [esp], eax
        movzx ecx, byte ptr [edi+4]
        mov  eax, -1
        cmp  ecx, {FIRE}
        jne  sc_s1
        mov  eax, -2
        jmp  sc_s9
    sc_s1:
        cmp  ecx, {SP}
        jne  sc_s2
        movzx eax, word ptr [edi+6]
        jmp  sc_s9
    sc_s2:
        cmp  ecx, {SPM}
        jne  sc_s9
        mov  eax, [ebp-8]
        mov  eax, [eax+0x0C]
    sc_s9:
        mov  [esp+8], eax
        mov  eax, [esi+0x20]
        mov  [esp+0x0C], eax
        mov  eax, [esp+0x38]
        mov  [esp+0x10], eax
        cmp  byte ptr [edi+4], {FIRE}
        jne  sc_frame
        mov  eax, [ebx+0x{CELL_TCATTACK:X}]
        mov  eax, [eax+4]
        mov  [esp+0x14], eax
        mov  eax, [ebx+0x{CELL_TCDAMAGE:X}]
        mov  eax, [eax+4]
        mov  [esp+0x1C], eax
        jmp  sc_def
    sc_frame:
        movsx ecx, byte ptr [edi+5]
        movsx eax, byte ptr [ebp+ecx]
        mov  [esp+0x14], eax
        movsx eax, byte ptr [ebp+ecx+1]
        mov  [esp+0x1C], eax
    sc_def:
        cmp  dword ptr [esp+4], 2
        je   sc_sdef
        mov  eax, esi
        mov  edx, [ebx+0x{CELL_DOOR:X}]
        call 0x{IS_CLASS_T:X}
        test al, al
        jz   sc_wdef
        mov  dword ptr [esp+4], 1
    sc_wdef:
        mov  eax, esi
        call 0x{WALL_GETDEF:X}
        jmp  sc_d
    sc_sdef:
        mov  eax, esi
        call 0x{IL_GETDEF:X}
        movsx eax, al
    sc_d:
        mov  [esp+0x18], eax
        mov  eax, esp
        mov  ecx, [ebx+0x{IAT_EDR:X}]
        add  ecx, 0x{sg_off:X}
        call ecx
        add  esp, 0x20
    sc_ret:
        ret"""

        parts = [("cave_int", c_int), ("cave_abs", c_abs),
                 ("cave_wall", c_shp("tab_wall", 0, R_WALL)), ("cave_str", c_shp("tab_str", 2, R_STR)),
                 ("cave_ter", c_ter), ("sg_common", c_common)]
        for name, fn in parts:
            blob = asm(fn(va), va)
            caves.append((name, va, blob))
            layout[name] = va
            va = (va + len(blob) + 3) & ~3
        for name, tab in (("tab_wall", tab_w), ("tab_str", tab_s)):
            caves.append((name, va, tab))
            layout[name] = va
            va += len(tab)
        return caves

    layout = {}
    build(layout)                     # pass 1: sizes and addresses
    caves = build(layout)             # pass 2: final operands
    assert caves == build(dict(layout)), "layout did not converge"
    return caves


T_CAVES = t_caves()
CAVE = {n: va for n, va, _b in T_CAVES}


def check_pic():
    """Every anchor's sub constant equals its return address; no absolute DLL memory operand."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    code = [c for c in E_CAVES if c[0] in ("stubs", "sg_log", "ms_log")] + \
           [c for c in T_CAVES if not c[0].startswith("tab_")]
    for name, va, blob in code:
        ins = list(md.disasm(blob, va))
        if name != "stubs":
            assert sum(len(x.bytes) for x in ins) == len(blob), "%s does not disassemble cleanly" % name
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
                s = ins[i + 2]
                assert s.mnemonic == "sub" and int(s.op_str.split(",")[1], 16) == x.address + 5, name
            if re.search(r"ptr \[0x[0-9a-f]+\]", x.op_str):
                sys.exit("ABORT: %s absolute memory operand at %08X: %s" % (name, x.address, x.op_str))
            if x.mnemonic == "push" and x.op_str.startswith("0x"):
                sys.exit("ABORT: %s push imm at %08X (keystone imm8 trap)" % (name, x.address))


check_pic()


def interior_ok(d, windows, fn):
    """Skipdata disassembly of the whole function (jump tables do not stop it) for any branch into a
    hook's interior, plus a raw dword scan of the function for jump-table entries pointing there."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    o = P.va2off(d, fn[0])
    buf = bytes(d[o:o + fn[1] - fn[0]])
    bad = []
    for x in md.disasm(buf, fn[0]):
        if x.mnemonic.startswith("j") or x.mnemonic == "call":
            try:
                t = int(x.op_str, 16)
            except ValueError:
                continue
            bad += [x.address for lo, hi in windows if lo < t < hi and not lo <= x.address < hi]
    for i in range(len(buf) - 3):
        v = struct.unpack_from("<I", buf, i)[0]
        bad += [fn[0] + i for lo, hi in windows if lo < v < hi]
    bad += [a for lo, hi in windows for a in P.rel32_into(d, lo, hi)]
    return bad


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


T_HOOKS = [(H_INT, V_INT, jmp_to(H_INT, CAVE["cave_int"], len(V_INT))),
           (H_ABS, V_ABS, jmp_to(H_ABS, CAVE["cave_abs"], len(V_ABS))),
           (H_WALL, V_WALL, jmp_to(H_WALL, CAVE["cave_wall"], len(V_WALL))),
           (H_STR, V_STR, jmp_to(H_STR, CAVE["cave_str"], len(V_STR))),
           (H_TER, V_TER, jmp_to(H_TER, CAVE["cave_ter"], len(V_TER)))]


def go(argv):
    d = _tc_bytes()
    for fn, hooks in ((FN_NEXTSTRIKE, (H_INT, H_ABS)), (FN_WALLSHP, (H_WALL,)), (FN_STRSHP, (H_STR,)),
                      (FN_TERSHP, (H_TER,))):
        wins = [(h, h + len(v)) for h, v, _n in T_HOOKS if h in hooks]
        bad = interior_ok(d, wins, fn)
        if bad:
            sys.exit("ABORT: branch/jump-table entry into a hook interior: %s" % ", ".join("%08X" % a for a in bad))
    module(EPACK, 0x55700000)
    e = open(EPACK, "rb").read()
    for n, va in CL.items():
        o = P.va2off(e, va)
        assert e[o] == 0xE9, "cl library entry %s (%08X) is not installed -- apply build_combatlog_lib.py first" % (n, va)

    def epack():
        module(EPACK, 0x55700000)
        run("build_combatlog_siege [AoWEPACK]", [], E_CAVES, E_SLOT, [], argv)

    def tcpck():
        module(TCPCK, 0x00400000)
        run("build_combatlog_siege [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, [], argv)

    # bodies before callers on --apply; callers unhooked before the bodies go on --undo
    for step in ((tcpck, epack) if "--undo" in argv else (epack, tcpck)):
        step()


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
