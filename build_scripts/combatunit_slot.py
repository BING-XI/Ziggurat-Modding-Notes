#!/usr/bin/env python
r"""
combatunit_slot.py -- the layout of the one extra dword build_combatunit_slot.py gives every
combat-unit object.  Not a build script.

Both combat-unit leaf classes grow by 4 bytes; the new dword sits at the old instance end.  Combat
objects are created per battle and zero-filled (InitInstance), so everything here starts at 0 in
every battle -- "resets at the end of a battle" for free.  No class inherits from either, so no
subclass field can be overlapped (scanned 2026-10-21).

    TTacticalCombatUnit  AoWTCPCK VMT 0x00412B4C  instance 0x68 -> 0x6C   dword at +0x68
    TFastCombatUnit      AoWEPACK VMT 0x5571D4BC  instance 0x64 -> 0x68   dword at +0x64

    byte 0  B_MIRROR    Mirror Image: images used this battle
    byte 1  B_SKIRMISH  Skirmisher: 1 = attacked this round (manual combat only)
    byte 2  B_MIRROR_DRAW  the draw marks of build_mirrorimage.py's Show wrapper (manual combat):
                   bit 0 the images are being drawn, bit 1 the unit is a statue (Stone Gaze),
                   bit 2 build_unit_vfx.py's header is present (Invisibility / Mistform look)
    byte 3  B_LUCKY     Lucky: 1 = its cheat-death is spent this battle

All four bytes are taken: the next stateful feature must grow the dword (build_combatunit_slot.py).
"""

TAC_VMT, TAC_SIZE_OLD, TAC_SIZE = 0x00412B4C, 0x68, 0x6C
FAST_VMT, FAST_SIZE_OLD, FAST_SIZE = 0x5571D4BC, 0x64, 0x68
TAC_SLOT, FAST_SLOT = TAC_SIZE_OLD, FAST_SIZE_OLD
B_MIRROR, B_SKIRMISH, B_MIRROR_DRAW, B_LUCKY = 0, 1, 2, 3
