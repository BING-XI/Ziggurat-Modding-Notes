#!/usr/bin/env python
r"""
build_effectroll_res10.py -- the combat log's effect-roll lines print the target's real RES.
AoWEPACK.dpl, one byte.  Owner report 2026-10-14 ("frozen 90% vs res -3" on a RES 2 unit).

Since the stat doubling, each effect roll in TAbstractUnit.ExecuteDamageEffectsRole is
HitRole(10 - effectiveRES) (`mov eax,0xA / sub eax,edi`, cave 0x5584DC36; Weakness takes 4 off
RES first).  build_effectroll.py's emitter turns the roll's argument back into a RES with
`mov eax,5 / sub eax,diff` at 0x5580F700, the pre-doubling constant, so every line read RES 5
too low.  The odds it prints come from the argument itself and were already right.

    0x5580F701  imm32 05 00 00 00 -> 0A 00 00 00   (mov eax,5 -> mov eax,10)

Inside build_effectroll.py's cave, which that script can no longer re-apply (its entry stub
0x5580F605 is rerouted to 0x55810500); build_hitslope5.py patches 0x5580F6C3 in the same cave
the same way.  No .reloc entry on the immediate.  No roll, display only.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import run

SITE = 0x5580F701
hooks = [(SITE, bytes.fromhex("05000000"), bytes.fromhex("0a000000"))]

if __name__ == "__main__":
    run("build_effectroll_res10", hooks, [], (SITE, SITE), [])
