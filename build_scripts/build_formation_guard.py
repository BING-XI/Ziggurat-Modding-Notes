#!/usr/bin/env python
r"""
build_formation_guard.py -- an aura whose owner cannot be found no longer freezes its army.
AoWEPACK.dpl.  From Inioch's share8 patch_bag_ability_crash.py part B.

VANILLA
    TArmy.UpdateFormation 0x5578D034 walks the army's units; for ability 0x2E it asks the unit for
    the ability's owner (VMT+0x154, 0x5578D0DE) and dereferences the result unchecked at 0x5578D0E7
    (`mov ecx,[eax] / call [ecx+0x60]`).  A nil owner -- a level query widened without the matching
    owner query, as happened to Inioch's bag abilities -- is an access violation; TArmy.Update then
    leaks its lock and the army is wedged for the rest of the game, silently.  Ours is not known to
    be exposed (02-abilities-modded.md, 2026-09-10); this is the backstop.

THE FIX
    Hook the 6-byte call at 0x5578D0DE -> cave_formation: make the call; nil -> skip this unit
    (0x5578D11E, the loop's `dec esi`); otherwise resume at 0x5578D0E4.
    The cost: a future level/owner asymmetry shows up as a missing aura instead of a frozen army
    (aow1-level-owner-query-asymmetry).  build_leadership_others.py starts at 0x5578D128, after the loop.

Rolls: none.  PIC: rel32 only.  Slot 0x5584D8C0-0x5584D8DF, exclusive.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D8C0, 0x5584D8E0)
CAVE = 0x5584D8C0
HOOK, VAN = 0x5578D0DE, bytes.fromhex("ff9154010000")
RESUME, SKIP = 0x5578D0E4, 0x5578D11E


def build(va):
    return asm(f"""
        call dword ptr [ecx + 0x154]
        test eax, eax
        je {SKIP:#x}
        jmp {RESUME:#x}
    """, va)


caves = [("cave_formation", CAVE, build(CAVE))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), 0x5578D034, 0x5578D128)]

if __name__ == "__main__":
    run("build_formation_guard", hooks, caves, SLOT, interior)
