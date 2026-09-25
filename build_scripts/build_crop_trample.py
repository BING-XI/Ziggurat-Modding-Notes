#!/usr/bin/env python
r"""
build_crop_trample.py -- trampling enemy farmland always costs race relations, and a city's
farmland answers to the city's own race.  AoWEPACK.dpl, two instructions.  Owner ruling 2026-09-25.

TCrop.EndTurn @0x557A5CFC: an army of player P ends its turn on a crop whose owner structure
belongs to another player (owner > 0) at diplomatic relation 1 (war) -> owner.CropTrampled(P)
(VMT +0x240), then the crop is destroyed.  Two implementations:

    TPlayerCropStructure.CropTrampled @0x557A6108   (Farms inherit it)
        race = owner player's race [player+0xA5];  relation(race, P) += 5      <- vanilla: a BONUS
    TCity.CropTrampled @0x557AA78C
        race = owner player's race if owned, else city race [city+0x45];  relation(race, P) -= 5

PATCHES
    F  0x557A6157  83 E8 FB  sub eax,-5  ->  83 C0 FB  add eax,-5      farms: -5, like cities
    C  0x557AA79F  7E 21     jle 0x557AA7C2  ->  EB 21  jmp           cities: always the city's race

C leaves the owner-race block (0x557AA7A1-0x557AA7C1) dead.  Neither site carries a .reloc entry,
and there is no draw anywhere in either routine.

    python build_scripts/build_crop_trample.py            verify / dry run
    python build_scripts/build_crop_trample.py --apply
    python build_scripts/build_crop_trample.py --undo
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import run

F_SITE, C_SITE = 0x557A6157, 0x557AA79F
hooks = [(F_SITE, bytes.fromhex("83e8fb"), bytes.fromhex("83c0fb")),
         (C_SITE, bytes.fromhex("7e21"), bytes.fromhex("eb21"))]

if __name__ == "__main__":
    run("build_crop_trample", hooks, [], (F_SITE, F_SITE), [])
