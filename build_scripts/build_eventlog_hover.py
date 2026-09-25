#!/usr/bin/env python
r"""
build_eventlog_hover.py -- the event tab stops jumping to the newest entry while the cursor is over
the event list.  AoWz.exe + AoWzCompat.exe (lockstep, exe_patch.py).

Idea and site from Inioch's share8 patch_eventlog_hover_v1.py; the hover test is ours.

VANILLA
    The logbook window refreshes on every new event (TheMapLogbookChanged) via 0x423304: it refills
    its TAOWListBox ([win+0x54]) from the player's TEventLogbook and then scrolls to the last entry,
    `call TAOWListBox.SetListOff(eax=list, edx=count-1)` at 0x42336A (thunk 0x403664 = jmp
    [0x45EC94], aowInt.dpl).  Reading an older event while other players' moves arrive therefore
    keeps throwing you back to the bottom.

THE FIX
    Only the call's rel32 operand changes (0x42336A `e8 f5 02 fe ff` -> call cave_evhover); nothing is
    displaced.  build_wheel_aowint.py keeps latch[0] at aowInt 0x5983E040 = the TAOWListBox the
    cursor is inside (set in TAOWListBox.CheckMouseMove, cleared at every mouse-move sweep).  The cave
    finds that latch rebase-proof from the IAT slot of SetListOff ([0x45EC94] + (0x5983E040 -
    0x598168F4)) and skips the scroll when the latch is this list; otherwise it tail-jumps to the
    thunk, so the call returns to 0x42336F exactly as before.  Once the cursor leaves the list, the
    next event scrolls to the bottom again, as vanilla.
    ⚠ Needs build_wheel_aowint.py installed.  Without it the latch stays 0 and this is a no-op.

Cave 0x0062A400 in .hcol's free run (Zig notes/12-re-toolchain.md); slot 0x0062A400-0x0062A43F,
exclusive.

USAGE
    python build_eventlog_hover.py [--dis]     verify / dry run
    python build_eventlog_hover.py --apply
    python build_eventlog_hover.py --undo      surgical
"""
import struct, sys
sys.dont_write_bytecode = True
from exe_patch import asm, run

SLOT = (0x0062A400, 0x0062A440)
CAVE = 0x0062A400
HOOK = 0x0042336A
THUNK = 0x00403664                      # jmp [0x45EC94] -> aowInt TAOWListBox.SetListOff
IAT_SETLISTOFF = 0x0045EC94
SETLISTOFF_LINK = 0x598168F4            # aowInt preferred-base VA of SetListOff
LATCH_HOVER = 0x5983E040                # build_wheel_aowint.py latch[0]

SRC = f"""
    mov ecx, dword ptr [{IAT_SETLISTOFF:#x}]
    add ecx, {(LATCH_HOVER - SETLISTOFF_LINK) & 0xFFFFFFFF:#x}
    cmp dword ptr [ecx], eax
    je h_skip
    jmp {THUNK:#x}
h_skip:
    ret
"""


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


caves = [("cave_evhover", CAVE, asm(SRC, CAVE))]
hooks = [(HOOK, call_to(HOOK, THUNK), call_to(HOOK, CAVE))]
assert hooks[0][1] == bytes.fromhex("e8f502feff")

if __name__ == "__main__":
    run("build_eventlog_hover", hooks, caves, SLOT)
