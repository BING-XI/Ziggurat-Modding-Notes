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
              defending, for any unit holding 0x98.  Applied before Lethargy's, so the two cancel.
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
                   Calculate is the one real melee round: tactical (AoWTCPCK imports it) and
                   auto-resolve (TStrikeAbility.fcExecuteCombatCommand).  Counts [round+0x28]
                   attacker / [round+0x2C] defender; ability test via the combat object's VMT +0xA8.
                   A count above 1 means the host already called that object's VMT +0x64, so the
                   pointer is live -- the same guarantee covers walls.  Per side: +1 for Haste
                   0x98, then -1 for Lethargy 0x84 if the count is still above 1.
    U  0x55767B15  TMeleeRound.CalculateUnit (the prediction twin): `call CalculateUnitStrikes` ->
                   cave_stru, fields +0x20/+0x24, strategic units' VMT +0x148.  Keeps the AI's and
                   the predictor's melee estimates honest.
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

cave_fcval / cave_tcval (EAX spell, ECX target, [ebp+8] out; fc also has [ebp+0xC] wall byte,
ret 8 vs ret 4 -- otherwise one body)
    The vanilla idiom is TEntangle.GetCombatDamageValueEx @0x557F8BAC:
        value = ROUND(HitRoleProbability(power - target RES) * HP * 100), out[1] = HP.
    Here the 100 becomes K_LETHARGY / K_EMBRITTLE -- the fraction of a disabled unit each
    status is worth to the auto-resolve AI.  THE tuning knobs.  Zero (never cast) when the target
    already has the status, and for Embrittle on a Physical Immunity target.  The wall-situation
    byte is ignored, as TCombatSpell's version does for range class 12.

Rolls: none added, none moved.  Auto-resolve now builds more candidate commands, from replicated
state only, so every peer builds the same list.  PIC: rel32, register-relative, one call/pop
anchor for the TFastCombatUnit VMT.  Slot 0x5584DF00-0x5584E1FF, exclusive.  Surgical --undo.

Also part of the feature: build_resstr_names.py ("Slow" -> "Lethargy", one row covers the spell
and the status) and build_pfs_typos.py (Spells.pfs record 120, Ability.pfs record 142).

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


def layout():
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
    run("build_lethargy", hooks, caves, SLOT, interior, reloc_ok=(V_SLOT, T_SLOT))
