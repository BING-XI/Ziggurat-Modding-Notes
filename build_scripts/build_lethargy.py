#!/usr/bin/env python
r"""
build_lethargy.py -- Slow becomes Lethargy (owner's design 2026-09-25).  AoWEPACK.dpl.

WHAT VANILLA SLOW DID
    One effect only: TAbstractUnit.CreateMovePointTable @0x5577FDC4 added +2 to every positive
    hex cost while the unit held ability 0x84 (open ground 4 -> 6, so two thirds of the range,
    not the half the text claimed).  No auto-combat effect, and never cast there:
    TCombatSpell.fcGetDamageValueEx scores it through StatisticsToLimitedDV with damage 0, so
    fcPrefetchCombatCommands @0x557F76BC drops every target.  Embrittle (spell 109) is a TSlow
    instance and inherited both.

WHAT LETHARGY DOES (status ability 0x84, removed at CombatDone as before)
    movement  the combat allowance is halved, rounded up, for the rest of combat, and the unit's
              remaining movement is halved (rounded up) the moment the spell lands.  The +2 hex
              cost is gone.
    strikes   one melee strike fewer when attacking (2 -> 1, Extra Strike 3 -> 2) and when
              defending (2 -> 1), never below one; a side with no strikes keeps none.
    HASTE     (added 2026-09-25) the mirror: one melee strike MORE when attacking and when
              defending, for any unit holding 0x98.  Applied before Lethargy's.
    50% ROLL  (owner 2026-10-14) in a REAL melee round each of those two changes lands with a 50%
              chance: one roll per side (attacker count, defender count) per modifier per round,
              Haste's roll first, Lethargy's second and only if the count is still above one.
              Hasted and lethargic together roll independently (2 -> 3, 2, 2 or 1).  Predictions
              (below) draw nothing and apply the full +-1.
    AI value  Lethargy and Embrittle both get a value, so heroes cast them in auto-resolve and the
              AI casts them in battles fought by hand.

SITES (vanilla bytes asserted; the only .reloc is the VMT slot's own, kept on purpose)
    M  0x55724FEE  TCombatUnit.GetMoves tail `movsx eax,al / pop ebx / ret` -> jmp cave_moves.
                   Every combat reader goes through this getter: AoWTCPCK's
                   TTacticalCombatUnit.NewTurn @0x41CF77 refills [cu+0x5C] from it (VMT +0x94),
                   the tactical AI reads it the same way, auto-resolve through TFastCombatUnit.
                   The ability test is the source unit's item-aware GetAbilityEnabled (VMT +0x148),
                   the same call CreateMovePointTable used.
    S  0x55767DE7  TMeleeRound.Calculate: `call CalculateStrikes` -> cave_str (tail-jumps to it).
                   Calculate builds the real melee round, tactical (AoWTCPCK imports it) and
                   auto-resolve, and two AI estimates (list below).  Counts [round+0x28]
                   attacker / [round+0x2C] defender; ability test via the combat object's VMT +0xA8.
                   A count above 1 means the host already called that object's VMT +0x64, so the
                   pointer is live -- the same guarantee covers walls.  Per side: +1 for Haste
                   0x98, then -1 for Lethargy 0x84 if the count is still above 1, each gated by
                   cave_roll.  Calculate has FOUR callers and only two are real rounds:
                       real  AoWTCPCK TCMeleeMoveTE.LastMove   call @0x00409208 (rel32 FFFF95FF)
                       real  AoWEPACK TStrikeAbility.fcExecuteCombatCommand @0x55766FF8 (rel 0D27)
                       est.  AoWTCPCK TCAI.CheckUnit           call @0x004154C6 (tactical AI)
                       est.  AoWEPACK TStrikeAbility.fcGetDamageValueEx @0x55766D7A (auto AI)
                   cave_str tells them apart by Calculate's return address ([esp+0x18] after its
                   two pushes): `E8` at ret-5 and the rel32 at ret-4 equal to one of the two real
                   sites' displacements.  A rel32 is invariant under rebasing, so this is PIC and
                   needs no knowledge of where AoWTCPCK loaded.  Both sites are asserted live
                   before any write.  Everything else, including any future caller, is treated as
                   an estimate.
    U  0x55767B15  TMeleeRound.CalculateUnit (the prediction twin): `call CalculateUnitStrikes` ->
                   cave_stru, fields +0x20/+0x24, strategic units' VMT +0x148.  Unchanged by the
                   2026-10-14 roll: it draws nothing.
    C  0x557F8868  TSlowCA.Execute: `call GetAbilityData` -> cave_cur.  Reached only when the
                   status was newly added (the host's `+0x94` AddAbility returned true), with
                   EDX = the id build_embrittle.py's selector chose, EDI = the target combat
                   object.  Only id 0x84 halves; only a TTacticalCombatUnit carries movement at
                   +0x5C (instance size 0x68), so the cave requires instance size > 0x5C (plain
                   TCombatUnit is 0x5C) and a VMT other than TFastCombatUnit's (0x5571D4BC, whose
                   +0x5C is an auto-resolve weight: 8 hero, 4 unit).
    P  0x5577FF9E  CreateMovePointTable: the 0x84 block's `je` -> `jmp` (74 -> EB).  The +2 cost
                   is gone for every caller: tactical paths, the tactical AI, the world map.
    V  0x557F4E98  TSlow VMT slot +0x98 (fcGetDamageValueEx), TCombatSpell's 0x557F7464 ->
                   cave_fcval: auto-resolve's value (fcPrefetchCombatCommands).
    T  0x557F4E84  TSlow VMT slot +0x84 (GetCombatDamageValueEx), TSlow's own all-zero
                   0x557F8948 -> cave_tcval: the manual-combat AI's value, reached through
                   TSpell.tcGetDamageValueEx @0x5577969C (+0x88).  TEntangle overrides this same
                   slot, which is why the AI casts Entangle and never cast Slow.
                   Only TSlow's table changes, i.e. Lethargy and Embrittle.

PREDICTION RULE (2026-10-14): every estimate -- cave_stru, and Calculate's two estimate callers --
applies the FULL +1 / -1, i.e. the 2026-09-25 behaviour.  An integer strike count cannot carry
the expected half strike; the full step and no step are each the real outcome half the time, and
the full step keeps the consumers pointing the right way: TStrikeAbility.GetDamageValue(Ex) (the
strategic AI's attack values), the raze/combat predictor at 0x5580C8E0, the tactical AI's
TCAI.CheckUnit and auto-resolve's fcPrefetchCombatCommands still see that Haste helps and
Lethargy hurts, at twice the average size.  Dropping the step would erase the signal entirely.

RNG: P1 SYNCED DRAW WITH RAW-SEED PRESERVATION (12-re-toolchain.md sections 4.4 and 4.10).
TAoWHSMap.Random(map, 2) in cave_roll, map from AoWE.AoWHSMap @0x558FA040 through a call/pop
anchor.  Random loads System.RandSeed from map[+0x230], draws, writes the new seed back to the
map and leaves RandSeed on the synced stream (0x55778298..0x557782B4).  In auto-resolve the raw
stream was anchored once by TCombat.Execute and feeds HitRole / ExecuteDamageRole, so a bare call
would rewind it to the synced seed after every rolled melee (repeating hit/miss patterns -- not a
desync, a correlation).  cave_roll therefore saves [[0x558FB720]] (IAT cell -> VCL30
System.RandSeed, asserted by preflight) before the call and restores it after: the synced stream
advances by one, the raw stream does not move.  Neither real host draws itself, so Q4 falls to
the siblings in the same context: AoWTCPCK's SYNC list holds TCMeleeMoveTE.ExecuteStrike
and TCAbTouchMoveTE.LastMove (the tactical TE runs synchronised; ExecuteStrike re-anchors
System.RandSeed from a synced draw before every strike, @0x00409B39), AoWEPACK's SYNC list holds
TBreathAbility / TRoundAttackAbility / TCombatSpell.fcExecuteCombatCommand.  NOT P2: at LastMove
the raw seed is not yet re-anchored -- the per-frame cosmetic raw draws (TfxHS.NewFrame ...) have
moved it differently on every machine -- so a raw draw there would desync tactical multiplayer.
Every draw is gated on replicated state only (ability flags, strike counts, an earlier synced
result), and the estimate paths draw nothing, so every peer makes the same draws.

cave_fcval / cave_tcval (EAX spell, ECX target, [ebp+8] out; fc also has [ebp+0xC] wall byte,
ret 8 vs ret 4 -- otherwise one body)
    The vanilla idiom is TEntangle.GetCombatDamageValueEx @0x557F8BAC:
        value = ROUND(HitRoleProbability(power - target RES) * HP * 100), out[1] = HP.
    Here the 100 becomes K_LETHARGY / K_EMBRITTLE -- the fraction of a disabled unit each
    status is worth to the auto-resolve AI.  THE tuning knobs.  Zero (never cast) when the target
    already has the status, and for Embrittle on a Physical Immunity target.  The wall-situation
    byte is ignored, as TCombatSpell's version does for range class 12.

Rolls: one synced draw site (cave_roll, above), raw seed preserved.  Auto-resolve builds more candidate commands, from
replicated state only, so every peer builds the same list.  PIC: rel32, register-relative, two
call/pop anchors (the TFastCombatUnit VMT in cave_cur, AoWE.AoWHSMap in cave_roll).
Slot 0x5584DF00-0x5584E1FF, exclusive:
    cave_moves 0x5584DF00, cave_str 0x5584DF20 (124 B, must end by 0x5584DFA0), cave_stru
    0x5584DFA0, cave_cur 0x5584E020, cave_fcval 0x5584E060, cave_tcval 0x5584E110, cave_roll
    0x5584E1C0 (55 B, ends 0x5584E1F7).
Addresses are pinned, not packed, so the 2026-10-14 re-tune moved no hook.

RE-TUNE / UNDO.  --apply over an earlier install rewrites the slot in place: before writing, the
slot must hold zero or exactly one of v1 (2026-09-25, no roll), v2 (2026-10-14, roll that rewound
the raw seed) or v3 (current), or the script aborts.  --undo restores all seven sites and zeroes
the slot, whichever version is installed.  No snapshot is taken.

Also part of the feature: build_resstr_names.py ("Slow" -> "Lethargy", one row covers the spell
and the status) and build_pfs_typos.py (Spells.pfs records 120 and 25, Ability.pfs records 142
and 162: Lethargy and Haste, both saying 50% since 2026-10-14).

Forward hazard: the real-round test keys on the call at AoWTCPCK 0x00409208 and AoWEPACK
0x55766FF8.  A script that retargets either call, or calls Calculate from a cave, turns that
round into an "estimate" (full +-1, no roll) without any error -- the asserts below catch the
first two at this script's next run, not at the other script's.

    python build_scripts/build_lethargy.py            dry run + state
    python build_scripts/build_lethargy.py --apply
    python build_scripts/build_lethargy.py --undo
    python build_scripts/build_lethargy.py --dis      disassemble the caves
"""
import struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584DF00, 0x5584E200)
CAVE = 0x5584DF00

K_LETHARGY = 33                 # value = P(land) * HP * K; Entangle (full disable) uses 100
K_EMBRITTLE = 50

SLOW_ABIL, EMB_ABIL, EMB_SPELL = 0x84, 0xB2, 109
HASTE_ABIL = 0x98               # THasteAbility (spell Haste, id 15)
PHYS_BIT = 0x80                 # GetImmunityTypes bit for Physical (build_embrittle.py)

M_SITE, M_VAN = 0x55724FEE, bytes.fromhex("0fbec05bc3")
S_SITE, CALC_STRIKES = 0x55767DE7, 0x55767B24
U_SITE, CALC_USTRIKES = 0x55767B15, 0x557677CC
C_SITE, GET_ABDATA = 0x557F8868, 0x5574F1C4
P_SITE, P_VAN, P_NEW = 0x5577FF9E, bytes.fromhex("7425"), bytes.fromhex("eb25")
V_SLOT, V_VAN = 0x557F4E98, 0x557F7464
T_SLOT, T_VAN = 0x557F4E84, 0x557F8948

FAST_VMT = 0x5571D4BC           # AoWE.TFastCombatUnit
HITPROB = 0x55725DCC            # AoWE.HitRoleProbability (EAX = diff -> ST0)
ROUND = 0x55701048              # thunk -> System.@ROUND (ST0 -> EAX)

# 2026-10-14: the 50% roll
STR_CAVE = 0x5584DF20           # cave_str v2, must end by STRU_CAVE
STRU_CAVE = 0x5584DFA0
ROLL_CAVE = 0x5584E1C0          # cave_roll: the has/roll helpers, the one synced draw
SYNC_RANDOM = 0x5577827C        # AoWE.TAoWHSMap.Random (EAX map, EDX n; clobbers ECX)
HSMAP_VAR = 0x558FA040          # AoWE.AoWHSMap -> the map
RANDSEED_IAT = 0x558FB720       # IAT cell -> VCL30 System.RandSeed (asserted by preflight)
CALCULATE = 0x55767D24          # AoWE.TMeleeRound.Calculate
REAL_EP = 0x55766FF8            # TStrikeAbility.fcExecuteCombatCommand: call Calculate
EST_EP = 0x55766D7A             # TStrikeAbility.fcGetDamageValueEx: call Calculate
TC_THUNK, TC_IAT = 0x0040280C, 0x0046E668   # AoWTCPCK: jmp [IAT Calculate]
REAL_TC = 0x00409208            # AoWTCPCK TCMeleeMoveTE.LastMove: call Calculate
EST_TC = 0x004154C6             # AoWTCPCK TCAI.CheckUnit: call Calculate


def rel(src, dst):
    return (dst - (src + 5)) & 0xFFFFFFFF


REL_REAL_EP, REL_REAL_TC = rel(REAL_EP, CALCULATE), rel(REAL_TC, TC_THUNK)
REL_EST_EP, REL_EST_TC = rel(EST_EP, CALCULATE), rel(EST_TC, TC_THUNK)
assert len({REL_REAL_EP, REL_REAL_TC, REL_EST_EP, REL_EST_TC}) == 4


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def build_moves(va):
    return asm("""
        movsx eax, al
        push  eax
        mov   eax, dword ptr [ebx + 0x4c]
        mov   edx, %d
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0x148]
        test  al, al
        pop   eax
        je    done
        inc   eax
        sar   eax, 1
    done:
        pop   ebx
        ret
    """ % SLOW_ABIL, va)


def build_strikes(va, att, dfn, slot, tail):
    """Per side: Haste adds one, then Lethargy takes one away (never below one).  A side the host
    left at 0 is skipped, which also guarantees the object pointer was already dereferenced."""
    def side(cnt, obj, tag):
        return """
        cmp   dword ptr [ebx + 0x%X], 0
        jle   %s_done
        mov   eax, dword ptr [ebx + 0x%X]
        mov   edx, %d
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0x%X]
        test  al, al
        je    %s_slow
        inc   dword ptr [ebx + 0x%X]
    %s_slow:
        cmp   dword ptr [ebx + 0x%X], 1
        jle   %s_done
        mov   eax, dword ptr [ebx + 0x%X]
        mov   edx, %d
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0x%X]
        test  al, al
        je    %s_done
        dec   dword ptr [ebx + 0x%X]
    %s_done:
        """ % (cnt, tag, obj, HASTE_ABIL, slot, tag, cnt, tag, cnt, tag, obj, SLOW_ABIL, slot,
               tag, cnt, tag)
    return asm("push eax; push edx;" + side(0x28, att, "a") + side(0x2C, dfn, "d")
               + "pop edx; pop eax; jmp 0x%X" % tail, va)


HAS_SRC = """
    has:
        mov   eax, esi
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0xa8]
        test  al, al
        ret
"""


def build_roll_v2(va):
    """The first 2026-10-14 cave_roll -- it let TAoWHSMap.Random leave System.RandSeed on the
    synced stream, rewinding auto-resolve's raw stream.  Kept only to recognise it on disk."""
    def src(delta):
        return HAS_SRC + """
    roll:
        test  bl, bl
        je    r_ret
        call  r_anchor
    r_anchor:
        pop   eax
        mov   eax, dword ptr [eax + 0x%X]
        mov   edx, 2
        call  0x%X
        test  eax, eax
    r_ret:
        ret
        """ % (delta & 0xFFFFFFFF, SYNC_RANDOM)
    probe = asm(src(0x11111111), va)
    anchor = va + probe.index(b"\xE8\x00\x00\x00\x00\x58") + 5
    blob = asm(src(HSMAP_VAR - anchor), va)
    assert len(blob) == len(probe)
    return blob


def build_roll(va):
    """cave_roll v3: `has` (ESI object, EDX ability -> ZF=1 when absent) and `roll` (BL real flag
    -> ZF=1 when the modifier applies: always for an estimate, 1 in 2 for a real round).
    TAoWHSMap.Random loads System.RandSeed from map[+0x230] and never puts it back
    (0x55778298..0x557782B4), so `roll` saves the raw seed (through the IAT cell 0x558FB720 =
    VCL30 System.RandSeed) and restores it after the draw: the synced stream advances by one, the
    raw stream is left exactly where it was."""
    def src(d_map, d_seed):
        return HAS_SRC + """
    roll:
        test  bl, bl
        je    r_ret
        call  r_anchor
    r_anchor:
        pop   ecx
        mov   eax, dword ptr [ecx + 0x%X]
        mov   ecx, dword ptr [ecx + 0x%X]
        push  ecx
        push  dword ptr [ecx]
        mov   edx, 2
        call  0x%X
        pop   edx
        pop   ecx
        mov   dword ptr [ecx], edx
        test  eax, eax
    r_ret:
        ret
        """ % (d_map & 0xFFFFFFFF, d_seed & 0xFFFFFFFF, SYNC_RANDOM)
    probe = asm(src(0x11111111, 0x22222222), va)
    anchor = va + probe.index(b"\xE8\x00\x00\x00\x00\x59") + 5
    blob = asm(src(HSMAP_VAR - anchor, RANDSEED_IAT - anchor), va)
    assert len(blob) == len(probe)
    return blob


def roll_entries():
    has_len = len(asm(HAS_SRC, ROLL_CAVE))
    return ROLL_CAVE, ROLL_CAVE + has_len


def build_str2(va):
    """cave_str v2: BL := 1 for a real round (see the docstring), then each side through `side`
    with EDI = &count, ESI = the side's combat object.  EBX/ESI/EDI are free: Calculate pops all
    three right after this call returns, and CalculateStrikes saves its own."""
    has, roll = roll_entries()
    return asm("""
        push  eax
        push  edx
        mov   ecx, dword ptr [esp + 0x18]
        xor   ebx, ebx
        cmp   byte ptr [ecx - 5], 0xe8
        jne   go
        mov   ecx, dword ptr [ecx - 4]
        cmp   ecx, 0x%X
        je    real
        cmp   ecx, 0x%X
        jne   go
    real:
        inc   ebx
    go:
        mov   eax, dword ptr [esp + 4]
        lea   edi, [eax + 0x28]
        mov   esi, dword ptr [eax + 0x10]
        call  side
        mov   eax, dword ptr [esp + 4]
        lea   edi, [eax + 0x2c]
        mov   esi, dword ptr [eax + 0x14]
        call  side
        pop   edx
        pop   eax
        jmp   0x%X
    side:
        cmp   dword ptr [edi], 0
        jle   s_ret
        mov   edx, %d
        call  0x%X
        je    s_slow
        call  0x%X
        jne   s_slow
        inc   dword ptr [edi]
    s_slow:
        cmp   dword ptr [edi], 1
        jle   s_ret
        mov   edx, %d
        call  0x%X
        je    s_ret
        call  0x%X
        jne   s_ret
        dec   dword ptr [edi]
    s_ret:
        ret
    """ % (REL_REAL_EP, REL_REAL_TC, CALC_STRIKES, HASTE_ABIL, has, roll,
           SLOW_ABIL, has, roll), va)


def build_cur(va):
    def src(delta):
        return """
            cmp   edx, %d
            jne   go
            push  eax
            push  ecx
            push  edx
            mov   ecx, dword ptr [edi]
            cmp   dword ptr [ecx - 0x1c], 0x5c
            jle   skip
            call  anchor
        anchor:
            pop   eax
            add   eax, 0x%X
            cmp   ecx, eax
            je    skip
            mov   eax, dword ptr [edi + 0x5c]
            test  eax, eax
            jle   skip
            inc   eax
            sar   eax, 1
            mov   dword ptr [edi + 0x5c], eax
        skip:
            pop   edx
            pop   ecx
            pop   eax
        go:
            jmp   0x%X
        """ % (SLOW_ABIL, delta & 0xFFFFFFFF, GET_ABDATA)
    probe = asm(src(0x11111111), va)
    anchor = va + probe.index(b"\xE8\x00\x00\x00\x00\x58") + 5
    blob = asm(src(FAST_VMT - anchor), va)
    assert len(blob) == len(probe)
    return blob


def build_value(va, ret):
    return asm("""
        push  ebp
        mov   ebp, esp
        sub   esp, 8
        push  ebx
        push  esi
        push  edi
        mov   ebx, eax
        mov   esi, ecx
        mov   edi, dword ptr [ebp + 8]
        xor   eax, eax
        mov   dword ptr [edi], eax
        mov   dword ptr [edi + 4], eax
        mov   dword ptr [edi + 8], eax
        mov   dword ptr [edi + 0xc], eax
        mov   word ptr [edi + 0x10], ax
        mov   edx, %d
        mov   ecx, %d
        cmp   dword ptr [ebx + 0x10], %d
        jne   sel
        mov   edx, %d
        mov   ecx, %d
    sel:
        mov   dword ptr [ebp - 4], ecx
        mov   eax, esi
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0xa8]
        test  al, al
        jne   done
        cmp   dword ptr [ebx + 0x10], %d
        jne   value
        mov   eax, esi
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0x7c]
        test  al, 0x%X
        jne   done
    value:
        mov   eax, esi
        mov   edx, dword ptr [eax]
        call  dword ptr [edx + 0x88]
        movsx eax, al
        mov   dword ptr [edi + 4], eax
        imul  eax, dword ptr [ebp - 4]
        mov   dword ptr [ebp - 8], eax
        mov   eax, esi
        mov   edx, dword ptr [eax]
        call  dword ptr [edx + 0x74]
        movsx edx, al
        movsx eax, byte ptr [ebx + 0x34]
        sub   eax, edx
        call  0x%X
        fild  dword ptr [ebp - 8]
        fmulp st(1)
        call  0x%X
        mov   dword ptr [edi], eax
        mov   ax, word ptr [ebx + 0x36]
        mov   word ptr [edi + 0x10], ax
    done:
        pop   edi
        pop   esi
        pop   ebx
        mov   esp, ebp
        pop   ebp
        ret   %d
    """ % (SLOW_ABIL, K_LETHARGY, EMB_SPELL, EMB_ABIL, K_EMBRITTLE, EMB_SPELL, PHYS_BIT,
           HITPROB, ROUND, ret), va)


def layout_v1():
    """The 2026-09-25 install, packed.  Kept only to recognise it for the in-place re-tune."""
    caves, va = [], CAVE
    def put(name, blob):
        nonlocal va
        caves.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    put("cave_moves", build_moves(va))
    put("cave_str", build_strikes(va, 0x10, 0x14, 0xA8, CALC_STRIKES))
    put("cave_stru", build_strikes(va, 0x20, 0x24, 0x148, CALC_USTRIKES))
    put("cave_cur", build_cur(va))
    put("cave_fcval", build_value(va, 8))
    put("cave_tcval", build_value(va, 4))
    return {n: v for n, v, _b in caves}, caves


def layout(roll=None):
    """v3 (2026-10-14): v1's addresses pinned, cave_str rewritten in place, cave_roll added.
    `roll=build_roll_v2` gives the superseded v2 image, for recognition only."""
    at1, caves1 = layout_v1()
    assert at1["cave_str"] == STR_CAVE and at1["cave_stru"] == STRU_CAVE
    caves = []
    for name, va, blob in caves1:
        if name == "cave_str":
            blob = build_str2(va)
            assert va + len(blob) <= STRU_CAVE, "cave_str v2 overruns cave_stru"
        caves.append((name, va, blob))
    assert caves[-1][1] + len(caves[-1][2]) <= ROLL_CAVE
    caves.append(("cave_roll", ROLL_CAVE, (roll or build_roll)(ROLL_CAVE)))
    assert ROLL_CAVE + len(caves[-1][2]) <= SLOT[1], "cave_roll overruns the slot"
    return {n: v for n, v, _b in caves}, caves


def image(caves):
    z = bytearray(SLOT[1] - SLOT[0])
    for _n, va, blob in caves:
        z[va - SLOT[0]:va - SLOT[0] + len(blob)] = blob
    return bytes(z)


def preflight():
    """Read-only checks the shared runner cannot make: the four Calculate call sites the
    real-round test keys on, the RandSeed IAT cell, and the slot holding nothing but zero / v1 /
    v2 / v3."""
    import os
    d = open(P.TARGET, "rb").read()
    def at_ep(va, n):
        o = P.va2off(d, va)
        return bytes(d[o:o + n])
    for va in (REAL_EP, EST_EP):
        assert at_ep(va, 5) == call_to(va, CALCULATE), \
            "ABORT: AoWEPACK %08X is no longer `call Calculate`" % va
    tc_path = os.path.join(P.GAME, "AoWTCPCK.dpl")
    t = open(tc_path, "rb").read()
    e = struct.unpack_from("<I", t, 0x3C)[0]
    tbase = struct.unpack_from("<I", t, e + 0x34)[0]
    nsec = struct.unpack_from("<H", t, e + 6)[0]
    opt = struct.unpack_from("<H", t, e + 20)[0]
    def tc(va, n):
        rva = va - tbase
        for i in range(nsec):
            vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", t, e + 24 + opt + 40 * i + 8)
            if vaddr <= rva < vaddr + max(vsize, rsize):
                o = raw + rva - vaddr
                return bytes(t[o:o + n])
        sys.exit("ABORT: AoWTCPCK VA %08X in no section" % va)
    assert tc(TC_THUNK, 6) == b"\xFF\x25" + struct.pack("<I", TC_IAT), \
        "ABORT: AoWTCPCK %08X is no longer jmp [Calculate IAT]" % TC_THUNK
    for va in (REAL_TC, EST_TC):
        assert tc(va, 5) == call_to(va, TC_THUNK), \
            "ABORT: AoWTCPCK %08X is no longer `call Calculate`" % va
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools"))
    from aowsyms import get_symbols
    iat = get_symbols("AoWEPACK.dpl")[3]
    assert str(iat.get(RANDSEED_IAT, "")).endswith("System.RandSeed"), \
        "ABORT: %08X is not the VCL30 System.RandSeed IAT cell (%r)" % (
            RANDSEED_IAT, iat.get(RANDSEED_IAT))
    print("  Calculate callers: real %08X (EP) / %08X (TC), estimate %08X (EP) / %08X (TC) -- as "
          "expected" % (REAL_EP, REAL_TC, EST_EP, EST_TC))
    o0, o1 = P.va2off(d, SLOT[0]), P.va2off(d, SLOT[1])
    zone = bytes(d[o0:o1])
    known = [("v1 (2026-09-25, no roll)", image(layout_v1()[1])),
             ("v2 (2026-10-14, roll that rewound the raw seed)",
              image(layout(build_roll_v2)[1])),
             ("v3 (2026-10-14, roll with raw-seed preservation)", image(caves))]
    ver = "zero" if not any(zone) else next((n for n, img in known if zone == img), None)
    if ver is None:
        sys.exit("ABORT: slot %08X-%08X holds neither zero, v1, v2 nor v3 -- foreign bytes"
                 % SLOT)
    print("  slot content: %s%s" % (ver, "" if ver == "zero" or ver.startswith("v3")
                                    else "  -> --apply rewrites it in place"))


at, caves = layout()
hooks = [(M_SITE, M_VAN, jmp_to(M_SITE, at["cave_moves"], 5)),
         (S_SITE, call_to(S_SITE, CALC_STRIKES), call_to(S_SITE, at["cave_str"])),
         (U_SITE, call_to(U_SITE, CALC_USTRIKES), call_to(U_SITE, at["cave_stru"])),
         (C_SITE, call_to(C_SITE, GET_ABDATA), call_to(C_SITE, at["cave_cur"])),
         (P_SITE, P_VAN, P_NEW),
         (V_SLOT, struct.pack("<I", V_VAN), struct.pack("<I", at["cave_fcval"])),
         (T_SLOT, struct.pack("<I", T_VAN), struct.pack("<I", at["cave_tcval"]))]
interior = [(M_SITE, M_SITE + 5, 0x55724FE0, 0x55724FF4)]

if __name__ == "__main__":
    preflight()
    run("build_lethargy", hooks, caves, SLOT, interior, reloc_ok=(V_SLOT, T_SLOT))
