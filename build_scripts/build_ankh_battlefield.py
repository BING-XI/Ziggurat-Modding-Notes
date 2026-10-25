#!/usr/bin/env python
r"""
build_ankh_battlefield.py -- the Commanded Undead ankh is drawn over the seized unit on the
manual-combat battlefield.  AoWTCPCK.dpl.

THE GAP
    build_turnundead_evilcommand.py gives a seized undead ability 0x89 (Commanded Undead), and
    build_commandedundead_pfs.py gives 0x89 an Ability.pfs record (key 147) whose tag 8 image list
    is a byte-identical clone of Turned Undead's (0x22, key 44): the SEFFECT.ILB ankh.  Its ShowEx
    block draws it on the unit panel and in auto-resolve.  But the manual-combat battlefield never
    calls ShowEx: TTacticalCombatUnitHS.Show draws overhead status icons from a FIXED list of 14
    ability ids in AoWTCPCK DATA, and 0x89 is not on it (owner, 2026-10-22: no ankh in manual
    combat for an evil priest's seized undead).  Found through Inioch's share9 (his Tame Animal
    note, README lesson 5).

    0x004227AA..0x004228A2, the loop (i in [ebp-0x30], 0..13):
        bound eax, [0x00422BCC]                    {0, 13}
        mov edx, [eax*4 + 0x004675B8]              the id      (twice: 0x4227B3 and 0x4227D9)
        [unit+0x1C] VMT +0xA8 GetAbilityEnabled(id) -> GetAbility(id) -> [ability+0x1C] image list,
        slot 0 -> drawn per frame
        cmp dword ptr [ebp-0x30], 0x0E             0x0042289E
    The list: 95 96 30 5C 5D 5E 5F 60 61 62 6B A3 7F 22.

THE PATCH
    the list, plus 0x89, copied to 0x0043C400 (15 dwords)
    0x004227B6, 0x004227DC   disp32 0x004675B8 -> 0x0043C400 (both carry a .reloc; a same-module
                             address, so the rebase delta still applies -- kept)
    0x00422BD0               the bound pair's upper limit 13 -> 14.  Only this loop's two `bound`s
                             (0x4227AD, 0x4227D3) use the pair at 0x422BCC (byte census).
    0x004228A1               loop count 0x0E -> 0x0F
    The vanilla list at 0x004675B8 is left untouched.

Slot 0x0043C400-0x0043C43F, exclusive.  No code: data and operands only.

RNG: none.  Drawing only.

Unproven, static checks cannot reach it: the ankh on screen.

    python build_scripts/build_ankh_battlefield.py            dry run + state
    python build_scripts/build_ankh_battlefield.py --apply
    python build_scripts/build_ankh_battlefield.py --undo     surgical
"""
import os
import struct
import sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import run

TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.TARGET, P.IMAGE_BASE = TCPCK, 0x00400000

OLD_LIST = 0x004675B8
IDS = (0x95, 0x96, 0x30, 0x5C, 0x5D, 0x5E, 0x5F, 0x60, 0x61, 0x62, 0x6B, 0xA3, 0x7F, 0x22)
ANKH = 0x89
SLOT = (0x0043C400, 0x0043C440)
NEW_LIST = SLOT[0]
REFS = (0x004227B6, 0x004227DC)                       # disp32 of `mov edx,[eax*4+list]`
BOUND_HI = 0x00422BD0                                 # {0,13} at 0x422BCC: the upper dword
COUNT = 0x004228A1                                    # `cmp dword ptr [ebp-0x30], 0x0E` imm8
LOOP = (0x004227AA, 0x004228A8)

d = open(TCPCK, "rb").read()
live = struct.unpack_from("<14I", d, P.va2off(d, OLD_LIST))
assert live == IDS, "the vanilla icon list moved or changed: %s" % [hex(x) for x in live]

blob = struct.pack("<15I", *IDS, ANKH)
caves = [("icon_list", NEW_LIST, blob)]
hooks = [(r, struct.pack("<I", OLD_LIST), struct.pack("<I", NEW_LIST)) for r in REFS] + [
    (BOUND_HI, struct.pack("<i", 13), struct.pack("<i", 14)),
    (COUNT, b"\x0e", b"\x0f")]
interior = [(r, r + 4, LOOP[0], LOOP[1]) for r in REFS] + [(COUNT, COUNT + 1, LOOP[0], LOOP[1])]

if __name__ == "__main__":
    run("build_ankh_battlefield", hooks, caves, SLOT, interior, reloc_ok=REFS)
