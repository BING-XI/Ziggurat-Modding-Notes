#!/usr/bin/env python
r"""
build_icestorm_gate25.py -- Ice Storm's terrain change takes effect on 25% of procs, not 75%.
AoWEPACK.dpl, one byte.  Owner ruling 2026-09-25.

cave_iceroll @0x5580DB40 (build_icestorm_lava.py; its RandInt call retargeted to the synced draw
0x55827000 by build_rng_lockstep.py) gates TIceStorm.ChangeStormTerrain on every proc:

    5580DB41  mov eax,4 / call 0x55827000       ; synced Random(4)
    5580DB4C  test eax,eax
    5580DB4E  je  0x5580DB5B                    ; 0 -> epilogue: SKIP  (was: skip 1 in 4)

This script flips 0x5580DB4E `74 0B` -> `75 0B` (jne): only a 0 takes effect, so each proc acts with
probability 1/4.  The draw is unchanged in count and order (P1 SYNCED, as before), so peers stay in
step.  The gate wraps the whole callback, so water->ice, land->snow, lava->wasteland and the
frozen-water spawns all thin to 25% per proc.  UpdateStorm applies the callback at radius 1..4
(frames 8/0xC/0x12/0x16): a centre hex gets four procs (1 - 0.75^4 = 68% chance of at least one),
an edge hex one (25%).

⚠ Do NOT re-run build_icestorm_lava.py --apply (it would unlink build_chasm_sky_spellguard.py's
chain); this byte is inside its cave and this script is the only thing that should touch it.

USAGE
    python build_icestorm_gate25.py            verify / dry run
    python build_icestorm_gate25.py --apply
    python build_icestorm_gate25.py --undo     back to 75% (je)
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import run

SITE = 0x5580DB4E
hooks = [(SITE, bytes.fromhex("740b"), bytes.fromhex("750b"))]

if __name__ == "__main__":
    run("build_icestorm_gate25", hooks, [], (SITE, SITE), [])
