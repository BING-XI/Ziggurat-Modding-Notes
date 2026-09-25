#!/usr/bin/env python
r"""
build_ai_hero_gate.py -- tactical AI considers heroes and leaders in every decision cycle.
AoWTCPCK.dpl, three in-place 2-byte NOPs.  From Inioch's share8 patch_ai_hero_gate_v1.py (plus the
friendly-loop gate his heal package removed as its hook G).

VANILLA
    TCAI counts attack proposals per cycle in [cai+0x2C].  While it is non-zero, every THero (heroes
    and leaders) is skipped in three target loops:
      0x418E8D  75 56  phase-1 enemy loop (melee / ranged / gaze / touch attacks)
      0x4191AE  75 56  friendly-target loop (heals and other friendly touches)
      0x4198D2  75 70  phase-2 spell-objective loop (leader spell casting)
    Phase 5 executes only the single best move per cycle and then re-evaluates, so a hero acted only
    once every ordinary unit had run out of attack options, however poor.

THE CHANGE
    The three jne become nop nop, so hero and leader moves compete on value every cycle.  Kept: the
    phase-4 regroup gate at 0x419F45 (regroup only when nobody attacks), and every hero-specific brake
    (UnitSafe-gated approaches, the x4 self value in the retaliation term, our x50 touch pct from
    build_ai_touch_herovalue.py).

Rolls: none.  No cave, no .reloc under the sites.  Surgical --undo restores the three jne.
"""
import os, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

hooks = [
    (0x00418E8D, bytes.fromhex("7556"), bytes.fromhex("9090")),
    (0x004191AE, bytes.fromhex("7556"), bytes.fromhex("9090")),
    (0x004198D2, bytes.fromhex("7570"), bytes.fromhex("9090")),
]

if __name__ == "__main__":
    run("build_ai_hero_gate", hooks, [], (0x00418E8D, 0x00418E8D), [])
