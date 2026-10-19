#!/usr/bin/env python
r"""
build_walldef0.py -- city walls have DEF 0 in manual combat, as they already do in auto-resolve.
AoWTCPCK.dpl, one immediate.  Owner's ruling 2026-10-18.

Two wall classes, two values before this script:
    auto-resolve   AoWEPACK TCombatWall.GetDefense @0x55725C04 / TWallUnit.GetDefense @0x55783658
                   `xor eax,eax` = 0 (vanilla too)
    manual combat  AoWTCPCK CityWall.TCityWall.GetDefense @0x405ACC  `mov [ebp-8],imm32`
                   vanilla -2, doubled to -4 by build_statdouble.py stage 9
This script sets the manual one to 0:

    0x405AD5  C7 45 F8 FC FF FF FF -> C7 45 F8 00 00 00 00     (mov dword [ebp-8], -4 -> 0)

The opcode bytes are part of the verify, so a wrong address aborts.  No .reloc entry on the
instruction.  --undo restores -4 (the pre-change live value, not vanilla -2).

WHO READS IT -- every reader is a direct `call 0x405ACC` (the method has no VMT slot), so gates
(TCityWallDoor descends from TCityWall) and walls move together:
    TCityWall.MapFieldMsgProc  11 calls, each `ExecuteDamageRole(DAM, ATK - GetDefense)` -- siege
                               shots, spells, blasts, fire ticks (0x405DC6 .. 0x4062BC)
    TCAbTouchMoveTE.LastMove   0x40A260, manual Wall Crushing
    combat-log caves           0x43B055 (build_combatlog_wallcrush.py), 0x43B48B
                               (build_combatlog_siege.py) -- they call the same getter, so wall
                               lines now print "vs 0 DEF" with no change of their own
The AI's Wall Crushing estimate (TWallCrushingAbility.tcGetDamageValueEx @0x557687C8) already used
the target's virtual GetDefense, i.e. the AoWEPACK wall's 0, so the AI now plans against the value
the manual roll uses.

NOT CHANGED: TCombatTerrain's DEF field (0x41093F, -4; scenery, which never takes damage) and
TCombatILTerrain.GetDefense (the terrain record's byte +0x45).

EFFECT (ExecuteDamageRole: r = RandInt(20), r <= 1 miss, r >= 18 full damage, else t = 10 - diff,
miss if t > r, damage 1 + (D-1)(r-t)/(18-t)).  Versus a wall t was 6 - ATK and is now 10 - ATK:
the 90 % cap needed ATK 4 and now needs ATK 8, so an attacker below 8 loses up to 20 points of hit
chance; damage per hit falls at every ATK, because the ramp keeps steepening as t goes below 2.

RNG: no draw added, removed or moved.  ExecuteDamageRole draws once whenever DAM >= 1, whatever the
difference; only the threshold changes.  Both peers run the same immediate.

COUPLING: fivepct_manifest.json (stage 9) records 0x405AD8 as -2 -> -4, so build_statdouble.py
counts this site UNEXPECTED -- it already aborts at stage 4 over later re-tunes (Terror and others).
Its --undo restores only sites still at its target, so it would leave this 0 in place.

    python build_scripts/build_walldef0.py            dry run + state
    python build_scripts/build_walldef0.py --apply
    python build_scripts/build_walldef0.py --undo
"""
import os, sys
sys.dont_write_bytecode = True
import aowepack_patch as P

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

SITE = 0x00405AD5
hooks = [(SITE, bytes.fromhex("c745f8fcffffff"), bytes.fromhex("c745f800000000"))]

if __name__ == "__main__":
    P.run("build_walldef0", hooks, [], (SITE, SITE), [])
