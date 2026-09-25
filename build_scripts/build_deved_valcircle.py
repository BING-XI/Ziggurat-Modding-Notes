#!/usr/bin/env python
r"""
build_deved_valcircle.py -- double-clicking a Map Validation entry also plays the shrinking-circle
highlight that Go-to plays.  AoWDevEd.exe (then build_zigeditor.py --apply).  From Inioch's share8
patch_devx_prune_unused_v2.py part 3.

VANILLA / OURS
    build_validation_goto.py's .vgo cave centres the view on the entry's hex with
    THSMEdit.CenterView (call at 0x5900E4: eax = THSMEdit, edx = [ebp-4] x, ecx = [ebp-8] y,
    push [ebp-0xC] level; callee ret 4).  Go-to (TMainForm.GotoItemClick 0x42CD69..0x42CD81)
    follows the same CenterView with TAbstractAoWHSMap.PlayCenterAnimation (thunk 0x401CF8,
    same argument shape, eax = the map).

THE CHANGE
    Retarget that call's rel32 to cave_circle, which replays CenterView with the same arguments,
    then calls PlayCenterAnimation(map = [[0x43289C]], x, y, level) from the .vgo frame, and
    returns with `ret 4` to consume the level pushed for the original call.  The .vgo cave reaches
    this call only after its own map check.

Placement: .ctp 0x0058F100-0x0058F13F, the slot above build_deved_heroprune.py's ZONE_CEIL
(that script's strip() stops there since 2026-09-25) and below build_deved_gamesettings_tab.py's
0x0058F280.  .vgo is full (build_taskbar_icon.py owns its tail).

Rolls: none.  Fixed-base exe, absolute addresses are fine.  Surgical --undo.
"""
import struct, sys
sys.dont_write_bytecode = True
import zigexe
from exe_patch import asm, run

SLOT = (0x0058F100, 0x0058F140)
CAVE = 0x0058F100
SITE = 0x005900E4
CENTERVIEW, PLAYCENTER, MAP_SLOT = 0x00402E28, 0x00401CF8, 0x0043289C


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def build(va):
    return asm(f"""
        push dword ptr [esp + 4]
        call {CENTERVIEW:#x}
        mov  eax, dword ptr [{MAP_SLOT:#x}]
        mov  eax, dword ptr [eax]
        test eax, eax
        je   c_out
        push dword ptr [ebp - 0xc]
        mov  dl, byte ptr [ebp - 4]
        mov  cl, byte ptr [ebp - 8]
        call {PLAYCENTER:#x}
    c_out:
        ret  4
    """, va)


caves = [("cave_circle", CAVE, build(CAVE))]
hooks = [(SITE, call_to(SITE, CENTERVIEW), call_to(SITE, CAVE))]

if __name__ == "__main__":
    run("build_deved_valcircle", hooks, caves, SLOT, targets=[zigexe.SRC_EDITOR])
