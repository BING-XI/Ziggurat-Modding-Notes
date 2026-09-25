#!/usr/bin/env python
r"""
build_defeat_enchant_guard.py -- defeat can no longer freeze the game on an enchantment whose unit
cannot be found.  AoWEPACK.dpl.

THE VANILLA LIVELOCK (diagnosed live by Inioch, share8 `mp-leader-kill-freeze.md`; every site
byte-checked vanilla in ours 2026-09-24)
    TPlayer.SetGameOverStatus -> TPlayerMagicControl.RemoveEnchantments 0x5577CB9C:
        while List.Count > 0 do ExecuteDispelEnchantment(Count-1)
    TUnitEnchantment.Dispel 0x55765E14:
        unit := TUnitControl.FindUnit([ench+0x18]);  if unit = nil then EXIT  <- stays in the list
    One enchantment whose unit id resolves to nothing, and the defeat cleanup spins forever on every
    machine (a whole-game hard lock).  His trigger was his own summoned-ability patch; ours could be
    `build_enchant_assert.py` (enchantments built on never-activated hidden defenders, id -1) --
    unproven, so this is defence in depth.

THE FIX (his two-part design; our Dispel hook is moved so it displaces no relocated bytes)
    1. RemoveEnchantments (whole 37-byte body) -> cave_rem: the same loop, but when Count did not
       drop after ExecuteDispelEnchantment 0x5577D43C, force-remove that last element through the
       engine's own TPlayerMagicControl.UnregisterEnchantment 0x5577D394; if even that does not
       shrink the list, stop.  Termination is guaranteed.
    2. Dispel's `test eax,eax / je fail / mov edx,[ebx+0x1C]` at 0x55765E2A (7 B, after the FindUnit
       call) -> cave_dis: found -> the vanilla path (resume 0x55765E31, RemoveAbility); not found and
       a caster ([ench+0xC] >= 0) -> unregister it from the caster's magic control
       ([[map+0x140] GetPlayers 0x557544D0]+0x54), so an orphan also vanishes when dispelled from
       the spell screen and stops charging upkeep; returns 0 like vanilla.  It also ends the
       OutOfMana non-termination recorded in 04-spells-modded.md (a zero-upkeep orphan that fails to
       dispel).
    His hook took the first 8 bytes of Dispel, whose `mov eax,[AoWHSMap]` imm32 at 0x55765E18
    carries a base relocation that he had to neutralise; hooking after the FindUnit call avoids it.

Deterministic, no roll: every peer runs the same cleanup on the same list.  Caves PIC (one
call/pop anchor for the map global 0x558FA040).  Slot 0x5584D100-0x5584D1FF, exclusive.

USAGE
    python build_defeat_enchant_guard.py            verify / dry run (writes nothing)
    python build_defeat_enchant_guard.py --dis      also disassemble the caves
    python build_defeat_enchant_guard.py --apply
    python build_defeat_enchant_guard.py --undo     surgical: both sites vanilla, slot zeroed
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D100, 0x5584D200)
CAVE_REM, CAVE_DIS = 0x5584D100, 0x5584D180
MAP_GLOBAL = 0x558FA040
EXECDISPEL, UNREGISTER, GETPLAYERS = 0x5577D43C, 0x5577D394, 0x557544D0

REM_HOOK = 0x5577CB9C
REM_VAN = bytes.fromhex("538bd8eb128b433c8b10ff52548bd04a8bc3e8890800008b433c8b10ff525485c075e25bc3")
DIS_FN = 0x55765E14
DIS_HOOK = 0x55765E2A
DIS_VAN = bytes.fromhex("85c0740d8b531c")      # test eax,eax / je +0xD / mov edx,[ebx+0x1C]
DIS_RESUME = 0x55765E31                          # mov ecx,[eax] / call [ecx+0x98] / pop ebx / ret

CAVE_REM_SRC = f"""
    push ebx
    push esi
    mov ebx, eax
r_loop:
    mov eax, [ebx+0x3C]
    mov edx, [eax]
    call dword ptr [edx+0x54]
    test eax, eax
    jz r_done
    mov esi, eax
    lea edx, [eax-1]
    mov eax, ebx
    call {EXECDISPEL:#x}
    mov eax, [ebx+0x3C]
    mov edx, [eax]
    call dword ptr [edx+0x54]
    cmp eax, esi
    jl r_loop
    mov eax, [ebx+0x3C]
    mov eax, [eax+8]
    mov eax, [eax+4]
    mov edx, [eax+esi*4-4]
    mov eax, ebx
    call {UNREGISTER:#x}
    mov eax, [ebx+0x3C]
    mov edx, [eax]
    call dword ptr [edx+0x54]
    cmp eax, esi
    jl r_loop
r_done:
    pop esi
    pop ebx
    ret
"""

CAVE_DIS_SRC = f"""
    test eax, eax
    jz d_orphan
    mov edx, [ebx+0x1C]
    jmp {DIS_RESUME:#x}
d_orphan:
    movsx edx, byte ptr [ebx+0xC]
    test edx, edx
    js d_fail
    call d_anchor
d_anchor:
    pop ecx
    sub ecx, d_anchor
    mov eax, [ecx+{MAP_GLOBAL:#x}]
    test eax, eax
    jz d_fail
    mov eax, [eax+0x140]
    call {GETPLAYERS:#x}
    test eax, eax
    jz d_fail
    mov eax, [eax+0x54]
    test eax, eax
    jz d_fail
    mov edx, ebx
    call {UNREGISTER:#x}
d_fail:
    xor eax, eax
    pop ebx
    ret
"""

caves = [("cave_rem", CAVE_REM, asm(CAVE_REM_SRC, CAVE_REM)),
         ("cave_dis", CAVE_DIS, asm(CAVE_DIS_SRC, CAVE_DIS))]
hooks = [(REM_HOOK, REM_VAN, jmp_to(REM_HOOK, CAVE_REM, len(REM_VAN))),
         (DIS_HOOK, DIS_VAN, jmp_to(DIS_HOOK, CAVE_DIS, len(DIS_VAN)))]
interior = [(REM_HOOK, REM_HOOK + len(REM_VAN), REM_HOOK, REM_HOOK + len(REM_VAN)),
            (DIS_HOOK, DIS_HOOK + len(DIS_VAN), DIS_FN, DIS_FN + 0x2B)]

if __name__ == "__main__":
    run("build_defeat_enchant_guard", hooks, caves, SLOT, interior)
