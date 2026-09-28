#!/usr/bin/env python
r"""
build_firmament_vision.py -- units on the Firmament (map level 3) see 3 hexes further.
AoWEPACK.dpl.  Owner request 2026-09-26.

THE SITE
    TAbstractUnit.VisibilityRange @0x55780EF8 computes sight = 3 + Vision level (build_vision9.py),
    reads the unit's level into the local byte [esp+2] via GetLocation, then either halves
    (0x55780F76 `inc esi / shr esi,1`) or not, and BOTH paths leave through one exit:
        55780F79  8B C6   mov eax, esi
        55780F7B  5A      pop edx          ; the local that holds x / y / level
        55780F7C  5E 5B C3  pop esi / pop ebx / ret
    The 6 bytes 0x55780F79..0x55780F7E (through the ret) become `E9 -> cave_fvis` + nop.  The cave
    re-reads the level byte, which is still at [esp+2] because the local has not been popped yet:
        level == 3 -> esi += 3, clamped to 15
    then replays the exit itself.  The bonus is added AFTER any halving, so it is a flat +3.
    Jumps INTO 0x55780F79 (from 0x55780F51, 0x55780F57, 0x55780F74) land on the hook's first byte
    and are fine; nothing jumps into its interior (checked by the run helper).

WHY THE CLAMP AT 15
    TArmy.UpdateVisibilityRanges @0x5578E10C packs the stack's maximum VisibilityRange into the LOW
    NIBBLE of [army+0x29] and TrueVisionRange into the high one, with no clamp
    (build_vision9.py, "RAISING MAX_LEVEL AGAIN").  Vision IX on the Firmament is 3 + 9 + 3 = 15,
    exactly the ceiling; anything that pushes a Vision level past 9 would otherwise spill into the
    army's true-sight nibble.  The clamp touches the Firmament path only.

COUPLINGS
    * TrueVisionRange @0x55780F80 returns VisibilityRange for a True Seeing (0x29) holder, so their
      true-sight range gets the +3 too.
    * build_maplevel4.py hooks 0x55780F32 / 0x55780F4C in this same function (Firmament = surface
      for the Night Vision / halving tests); build_vision9.py owns 0x55780F12.  No overlap.
    * Tactical combat (TCombatUnit.GetVisibilityRange 0x55724AD0) is not level-derived and is not
      touched.

Rolls: none.  PIC: register/stack + rel32 only.  Slot 0x5584F400-0x5584F43F, exclusive.
Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584F400, 0x5584F440)
CAVE = 0x5584F400
HOOK, VAN = 0x55780F79, bytes.fromhex("8bc65a5e5bc3")   # mov eax,esi / pop edx,esi,ebx / ret
FN_LO, FN_HI = 0x55780EF8, 0x55780F80                    # TAbstractUnit.VisibilityRange

FIRMAMENT = 3
BONUS = 3
NIBBLE_MAX = 15


def build(va):
    return asm(f"""
        cmp byte ptr [esp + 2], {FIRMAMENT}
        jne _done
        add esi, {BONUS}
        cmp esi, {NIBBLE_MAX}
        jbe _done
        mov esi, {NIBBLE_MAX}
    _done:
        mov eax, esi
        pop edx
        pop esi
        pop ebx
        ret
    """, va)


caves = [("cave_fvis", CAVE, build(CAVE))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), FN_LO, FN_HI)]

if __name__ == "__main__":
    run("build_firmament_vision", hooks, caves, SLOT, interior)
