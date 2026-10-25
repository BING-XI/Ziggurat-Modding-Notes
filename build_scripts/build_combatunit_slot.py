#!/usr/bin/env python
r"""
build_combatunit_slot.py -- one extra dword on every combat-unit object, for per-battle and
per-round state.  AoWTCPCK.dpl + AoWEPACK.dpl, data only (two instance-size dwords).  2026-10-21.
Layout and users: combatunit_slot.py (Skirmisher, Mirror Image).

    AoWTCPCK  0x00412B30  TTacticalCombatUnit [VMT-0x1C] instance size 0x68 -> 0x6C
    AoWEPACK  0x5571D4A0  TFastCombatUnit     [VMT-0x1C] instance size 0x64 -> 0x68

ClassCreate allocates and zero-fills [VMT-0x1C] bytes, so the dword exists, starts at 0 and dies
with the object at the end of every battle.  Combat objects are never streamed into a save.  Both
classes are leaves (no subclass anywhere could have a field at the old end); asserted by name and
self-pointer here.  The size dwords carry no .reloc.

Couplings: build_skirmisher.py, build_mirrorimage.py and build_lucky.py read/write the dword -- --undo them
first (this script refuses while any of them is installed).
⚠⚠ Any cave that tells TFastCombatUnit from TTacticalCombatUnit by instance size breaks when
these change.  build_shield.py did (size >= 0x68 = manual): a crash on every ranged hit on a
Shield unit in auto-resolve, fixed 2026-10-22 by testing the VMT.  Before changing a size again,
scan every modded cave for [vmt-0x1C] reads.

    python build_scripts/build_combatunit_slot.py            dry run + state
    python build_scripts/build_combatunit_slot.py --apply
    python build_scripts/build_combatunit_slot.py --undo
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import run
import combatunit_slot as S

EPACK = P.TARGET
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
USERS = ("build_skirmisher.py", "build_mirrorimage.py", "build_lucky.py")


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def check(path, base, vmt, name):
    module(path, base)
    d = open(path, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    cn = P.va2off(d, rd(vmt - 0x20))
    assert rd(vmt - 0x40) == vmt and d[cn + 1:cn + 1 + d[cn]] == name, "%s VMT not at %08X" % (name, vmt)


def users_installed():
    import subprocess
    out = []
    for u in USERS:
        p = os.path.join(HERE, u)
        if os.path.exists(p):
            r = subprocess.run([sys.executable, p], capture_output=True, text=True)
            if "state: INSTALLED" in r.stdout or "state: MIXED" in r.stdout:
                out.append(u)
    return out


T_HOOKS = [(S.TAC_VMT - 0x1C, struct.pack("<I", S.TAC_SIZE_OLD), struct.pack("<I", S.TAC_SIZE))]
E_HOOKS = [(S.FAST_VMT - 0x1C, struct.pack("<I", S.FAST_SIZE_OLD), struct.pack("<I", S.FAST_SIZE))]


def go(argv):
    module(TCPCK, 0x00400000)
    run("build_combatunit_slot [AoWTCPCK]", T_HOOKS, [], (T_HOOKS[0][0], T_HOOKS[0][0]), [], argv)
    module(EPACK, 0x55700000)
    run("build_combatunit_slot [AoWEPACK]", E_HOOKS, [], (E_HOOKS[0][0], E_HOOKS[0][0]), [], argv)


if __name__ == "__main__":
    check(TCPCK, 0x00400000, S.TAC_VMT, b"TTacticalCombatUnit")
    check(EPACK, 0x55700000, S.FAST_VMT, b"TFastCombatUnit")
    module(EPACK, 0x55700000)
    argv = sys.argv[1:]
    if "--undo" in argv:
        busy = users_installed()
        if busy:
            sys.exit("ABORT: %s still installed -- undo it first" % ", ".join(busy))
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])
        print("\n" + "=" * 60)
    go(argv)
