#!/usr/bin/env python
r"""
build_magictab_nonepnl.py -- the Magic tab hides "No spell is being researched" while a research is
set.  AoWz.exe (exe_patch.py).

VANILLA
    TMagicWin's research area holds two panels: SpellPnl [win+0xD4] (the current research) and
    NonePnl [win+0xF8] with its label NoneMsg [win+0xFC] ("No spell is being researched", DFM text,
    centred in RightPnl).  The overview routine 0x42CDE8 sets SpellPnl.Visible (vcall +0x6C) to
    [magic+0x34] <> 0 at 0x42D21B / 0x42D22D; nothing in the exe touches NonePnl, so it stays
    visible and relies on SpellPnl being painted over it.  Once a research is picked mid-turn the
    message shows under the research (owner report 2026-10-18).

THE FIX
    0x42D240, the `call 0x42CA38` both branches join at (eax = the window), is retargeted to
    cave_nonepnl (4-byte rel32, nothing displaced): NonePnl.SetVisible(not SpellPnl.Visible
    [+0x75]), then the vanilla 0x42CA38 with the window in eax.  Every caller of the overview,
    including build_magictab_refresh.py's per-refresh call, now keeps the two panels exclusive.

Cave 0x0062AD40 in .hcol's free run; slot 0x0062AD40-0x0062AD7F, exclusive.  No randomness.

USAGE
    python build_magictab_nonepnl.py [--dis]   verify / dry run
    python build_magictab_nonepnl.py --apply
    python build_magictab_nonepnl.py --undo    surgical
"""
import struct
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, run

SLOT = (0x0062AD40, 0x0062AD80)
CAVE = 0x0062AD40
SITE, VANILLA_TARGET = 0x0042D240, 0x0042CA38

SRC = f"""
    push eax
    mov edx, dword ptr [eax+0xd4]
    cmp byte ptr [edx+0x75], 0
    sete dl
    mov eax, dword ptr [eax+0xf8]
    test eax, eax
    je Lout
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
Lout:
    pop eax
    jmp {VANILLA_TARGET:#x}
"""


def call_to(site, dst):
    return b"\xE8" + struct.pack("<i", dst - (site + 5))


caves = [("cave_nonepnl", CAVE, asm(SRC, CAVE))]
hooks = [(SITE, call_to(SITE, VANILLA_TARGET), call_to(SITE, CAVE))]

if __name__ == "__main__":
    run("build_magictab_nonepnl", hooks, caves, SLOT)
