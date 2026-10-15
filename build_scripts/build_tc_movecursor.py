#!/usr/bin/env python
r"""
build_tc_movecursor.py -- the tactical move cursor no longer runs away for a unit with none of
Walking, Flying and Swimming.  AoWTCPCK.dpl.  Player report 2026-10-15 (Goblin Big Beetle hovering
a wooden wall: the cursor cycles through every cursor, then an error).

CAUSE
    TCombatUnitSelectionControl.UpdateMoveCursor @0x41F6E8, default action ([hs+0x34] = -1) on a
    hex with no unit, sets the movement glyph from GetMoveTypes @0x41D320 (TMoveTypes, RTTI
    0x557089B4: bit 0 mtWalking, 1 mtFlying, 2 mtSwimming, 3..7 Forestry, CaveCrawling,
    Mountaineering, LavaCrossing, Tunneling):
        0x41FB1C  bit 0 -> glyph 0x40     0x41FB3C  bit 2 -> 0x42     0x41FB5C  bit 1 -> 0x44
    and on a blocked hex (move cost <= 0: a wall that is not a door, or terrain the unit cannot
    enter) adds one at 0x41FCBD:  SetCursor(GetCursor + 1).  With none of the three bits no glyph
    is set, so the +1 accumulates on every update and steps through the whole cursor library,
    past its end.  Ziggurat's Unitres.pfs drops Walking from Sandworm (26), Giant Slug (60),
    Dwarf Mole (116) and Goblin Big Beetle (188), which vanilla gave Walking; the four ships
    (258..261) have no move ability in either.  The world map's TSelectedArmy.UpdateMoveCursor
    @0x55793440 makes the same three tests but marks "blocked" with `or 1`, so it cannot cycle.

FIX -- call retarget, nothing displaced
    0x41FB1C  E8 -> GetMoveTypes 0x41D320  becomes  E8 -> mc_types (zone 0x43B600..0x43B63F)
    mc_types calls GetMoveTypes and, when bits 0..2 are all clear, sets bit 0: the unit gets the
    walking glyph 0x40, and 0x41 on a blocked hex, as a walker does.  The second and third calls
    (0x41FB3C, 0x41FB5C) are reached only when bit 0 is clear and stay stock.  GetMoveTypes has
    exactly these three callers in AoWTCPCK; no other code sees the changed value.

Local input only: no game state, no random draws.  PIC (rel32 only).  Surgical --undo.

    python build_scripts/build_tc_movecursor.py            dry run + state
    python build_scripts/build_tc_movecursor.py --apply
    python build_scripts/build_tc_movecursor.py --undo
    python build_scripts/build_tc_movecursor.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

SLOT = (0x0043B600, 0x0043B640)
SITE = 0x0041FB1C                  # UpdateMoveCursor: the first `call GetMoveTypes`
GET_MOVE_TYPES = 0x0041D320
WALK_FLY_SWIM = 0x07
WALKING = 0x01


def call(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


CAVES = [("mc_types", SLOT[0], asm(f"""
        call {GET_MOVE_TYPES:#x}
        test al, {WALK_FLY_SWIM:#x}
        jne m_out
        or al, {WALKING:#x}
    m_out:
        ret
    """, SLOT[0]))]
HOOKS = [(SITE, call(SITE, GET_MOVE_TYPES), call(SITE, SLOT[0]))]

if __name__ == "__main__":
    run("build_tc_movecursor", HOOKS, CAVES, SLOT, [], sys.argv[1:])
