#!/usr/bin/env python
r"""
build_mpresume_customize.py -- resuming a multiplayer save no longer hangs when Customize Leaders
is ticked.  AoWEPACK.dpl.

THE VANILLA HANG (RE'd by Inioch, share8 `mp-reload-customize-hang.md`; verified here 2026-09-24)
    The host's start barrier hValidateSetupMap 0x557E1168 passes a human slot only when it has
    loaded the map (TPlayerSetupSettings+0x19 bit 8) AND -- whenever Customize Leaders is on
    (TSetupSettings+0x2A) -- has customised its leader (bit 4).  But MapLoaded 0x557E0614 skips the
    customisation flow for a game in progress (TSetupSettings+0x20 != 0, set from the picked file for
    saves and autosaves), so bit 4 is never set, the barrier never passes, and every machine waits on
    "Waiting for other players" forever.  Vanilla never shows it only because it defaults Customize
    Leaders off.  Our lobby (AoWz.exe 0x410D44) greys the box for PBEM only, so a host who ticks it
    and resumes a network save hangs every machine.

THE FIX (his design)
    0x557E11AA `cmp byte [ebx+0x2A],0 / je 0x557E11C3` (6 B; ebx = TSetupSettings, loaded at
    0x557E11A7) -> cave: game in progress ([ebx+0x20] != 0) or Customize Leaders off -> requirement
    met (0x557E11C3); else the vanilla bit-4 check (0x557E11B0).  Register-relative only, PIC.
    No bearing on build_pbem_leadersetup.py, whose TLeaderSetupControl has no network handshake.
    Host-side logic; ships in AoWEPACK.dpl, which is identical on every machine.

Slot 0x5584D200-0x5584D23F, exclusive.

USAGE
    python build_mpresume_customize.py            verify / dry run (writes nothing)
    python build_mpresume_customize.py --dis
    python build_mpresume_customize.py --apply
    python build_mpresume_customize.py --undo     surgical
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D200, 0x5584D200 + 0x40)
CAVE = 0x5584D200
FN = 0x557E1168
HOOK = 0x557E11AA
VAN = bytes.fromhex("807b2a007413")          # cmp byte [ebx+0x2A],0 / je 0x557E11C3
ENFORCE, SATISFIED = 0x557E11B0, 0x557E11C3

SRC = f"""
    cmp dword ptr [ebx+0x20], 0
    jne m_ok
    cmp byte ptr [ebx+0x2A], 0
    je m_ok
    jmp {ENFORCE:#x}
m_ok:
    jmp {SATISFIED:#x}
"""

caves = [("cave_resume", CAVE, asm(SRC, CAVE))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), FN, FN + 0x80)]

if __name__ == "__main__":
    run("build_mpresume_customize", hooks, caves, SLOT, interior)
