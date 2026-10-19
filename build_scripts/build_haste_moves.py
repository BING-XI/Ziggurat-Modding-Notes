#!/usr/bin/env python
r"""
build_haste_moves.py -- Haste (spell 15, status ability 0x98) gives +8 maximum movement points
instead of taking 1 off every hex cost.  AoWEPACK.dpl.  Owner's design 2026-10-19.  The extra
melee strike (build_lethargy.py's caves) is untouched.

WHY
    Vanilla Haste lowered every hex cost above 2 by 1, never below 2, in
    TAbstractUnit.CreateMovePointTable @0x5577FDC4.  It did nothing on a road Enchanted Roads had
    already brought to 2, and its worth swung with terrain: a quarter off open ground, a sixth off
    a 6-cost hex.  A flat +8 to the maximum is worth the same everywhere and stacks with any cost
    reduction.

WHAT CHANGES
    costs   C: the je over the 0x98 block becomes a jmp.  CreateMovePointTable is the one per-unit
            table builder and every cost reader calls it: MovePointCost (the real deduction), the
            move predictor cave (0x5580D7E5), TArmy.CreateMovePointTable / MoveOnMovePoints, the
            strategic AI (TAIGroupControl.UpdateGroupChanges, TAIMoveTargetSelector.ProcessStates)
            and AoWTCPCK through its import (TCAI.EvalBattle x6, TCombatUnitSelectionControl
            .CalculateMovePath / .Update).  So the path preview and both AIs lose the effect with
            the game.  re_tools/abquery.py --id 0x98 and idladder.py --id 0x98 find no other
            movement test for Haste in AoWEPACK.dpl, AoWTCPCK.dpl or AoWz.exe.
    moves   GetMoves is VMT +0xD4: TUnit.GetMoves 0x55782B84 (a call into build_medal_hpmv.py's
            0x5580BE00), THero.GetMoves 0x557885C0 (a jmp into build_item_hpmv.py's 0x5582B180),
            TLeader inherits THero's.  U/H/L repoint the three slots at wrappers that call the
            original, sign-extend AL (TUnit's bits 8-31 are its div remainder), add 8 while
            GetAbilityEnabled(0x98) (VMT +0x148, item-aware, the call the cost block used) and
            clamp at 127: MP is a signed byte and SetMovePoints clamps with a signed compare.
            Nothing calls either method directly, and no class in another module inherits these
            slots (no import of either), so every reader gets the bonus: NewTurn's refill,
            SetMovePoints' clamp, ValidTerrain, TCombatUnit.GetMoves (tactical refill, tactical AI,
            auto-resolve; Lethargy halves the hasted figure), the unit cards, the AI.  The bonus
            sits above the hero clamp of 80 (build_hero_clamps.py), so a hasted hero reaches 88.
    timing  The maximum rises the moment Haste lands; movement is refilled from it at the start
            of the unit's next turn, on the map or in battle.  The turn in progress is not topped
            up.
    RNG     none -- no draw; the result is a pure function of the unit's state.

HOOKS (bytes asserted; the only .reloc entries are the three slots' own, kept: the new values
are inside this image, so the rebase delta still applies to them)
    C  0x5577FF54  74 37 (je 0x5577FF8D) -> EB 37 (jmp)
    U  0x55710D80  TUnit   +0xD4  0x55782B84 -> cave_umoves
    H  0x557120C0  THero   +0xD4  0x557885C0 -> cave_hmoves
    L  0x5571230C  TLeader +0xD4  0x557885C0 -> cave_hmoves

Slot 0x558A0000-0x558A00FF, exclusive.  PIC: rel32 and register-relative only.  Surgical
--undo.  Couplings: none.  Undoing build_medal_hpmv.py or build_item_hpmv.py leaves the wrappers
calling the restored vanilla bodies, which are still GetMoves.

Texts: Spells.pfs record 25 and Ability.pfs record 162 (build_pfs_typos.py); manual
NEWMECH_LETHARGY and LATEST (build_ziggurat_manual.py).

    python build_scripts/build_haste_moves.py            dry run + state
    python build_scripts/build_haste_moves.py --apply
    python build_scripts/build_haste_moves.py --undo
    python build_scripts/build_haste_moves.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True

from aowepack_patch import asm, run

SLOT = (0x558A0000, 0x558A0100)
HASTE = 0x98
BONUS = 8

C_SITE = 0x5577FF54
C_VAN, C_NEW = bytes.fromhex("7437"), bytes.fromhex("eb37")
UNIT_GETMOVES, HERO_GETMOVES = 0x55782B84, 0x557885C0
U_SLOT, H_SLOT, L_SLOT = 0x55710D80, 0x557120C0, 0x5571230C

CAVE_U, CAVE_H, CAVE_COMMON = 0x558A0000, 0x558A0010, 0x558A0020


def build_entry(va, getter):
    """VMT +0xD4 entry: EAX = the unit.  Keep it in EBX across the original getter."""
    return asm(f"""
        push ebx
        mov  ebx, eax
        call {getter:#x}
        jmp  {CAVE_COMMON:#x}
    """, va)


def build_common(va):
    """AL = the original maximum, EBX = the unit, [esp] = the caller's EBX."""
    return asm(f"""
        movsx eax, al
        push eax
        mov  edx, {HASTE:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        pop  eax
        je   c_done
        add  eax, {BONUS}
        cmp  eax, 0x7f
        jle  c_done
        mov  eax, 0x7f
    c_done:
        pop  ebx
        ret
    """, va)


caves = [("cave_umoves", CAVE_U, build_entry(CAVE_U, UNIT_GETMOVES)),
         ("cave_hmoves", CAVE_H, build_entry(CAVE_H, HERO_GETMOVES)),
         ("cave_common", CAVE_COMMON, build_common(CAVE_COMMON))]
hooks = [(C_SITE, C_VAN, C_NEW),
         (U_SLOT, struct.pack("<I", UNIT_GETMOVES), struct.pack("<I", CAVE_U)),
         (H_SLOT, struct.pack("<I", HERO_GETMOVES), struct.pack("<I", CAVE_H)),
         (L_SLOT, struct.pack("<I", HERO_GETMOVES), struct.pack("<I", CAVE_H))]

if __name__ == "__main__":
    run("build_haste_moves", hooks, caves, SLOT, [], reloc_ok=(U_SLOT, H_SLOT, L_SLOT))
