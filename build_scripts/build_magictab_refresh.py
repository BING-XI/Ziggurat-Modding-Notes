#!/usr/bin/env python
r"""
build_magictab_refresh.py -- the Magic tab's research overview refreshes mid-turn.  AoWz.exe +
AoWzCompat.exe (lockstep, exe_patch.py).

From Inioch's share8 patch_spellbook_discounts_v1.py, its v3 and v4 only.  Nothing else in that
script is taken; 0x42ED93 belongs to build_tierresearch_exe.py.

VANILLA
    TMagicWin repaints its research overview (research power, turns to the current research) in
    0x42CDE8, reached only from 0x42D480 (PlayerMagicChanged), which bails at 0x42D497 unless the
    changed player is the one at the keyboard.  The mana-distribution / enchantment refresh 0x42D2CC
    runs on more events and does not rebuild the overview.  Research power changes mid-turn -- our
    Spellcasting x RES income moves it on a level-up or a hero's death -- so the line goes stale until
    the next turn.

THE FIX
    1. 0x42D2CC `55 8b ec 83 c4 f4 53 56` (8 B, prologue) -> jmp cave_magicrefresh + 3 NOP.  The cave
       calls 0x42CDE8 (eax = the window) with EAX/ECX/EDX preserved, replays the prologue and
       resumes at 0x42D2D4.  So every magic-tab refresh also rebuilds the overview.
    2. 0x42D497 `75 05` (jne) -> `90 90`: PlayerMagicChanged for ANY player repaints the overview.
       0x42CDE8 reads the player at the keyboard itself, so a hero lost during another player's turn
       now updates it too.  0x42D487's "tab visible" gate is untouched.

Cave 0x0062A440 in .hcol's free run; slot 0x0062A440-0x0062A47F, exclusive.

USAGE
    python build_magictab_refresh.py [--dis]   verify / dry run
    python build_magictab_refresh.py --apply
    python build_magictab_refresh.py --undo    surgical
"""
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, jmp_to, run

SLOT = (0x0062A440, 0x0062A480)
CAVE = 0x0062A440
HOOK, HOOK_VAN, RESUME = 0x0042D2CC, bytes.fromhex("558bec83c4f45356"), 0x0042D2D4
OVERVIEW = 0x0042CDE8
GATE, GATE_VAN, GATE_NEW = 0x0042D497, bytes.fromhex("7505"), bytes.fromhex("9090")

SRC = f"""
    push eax
    push ecx
    push edx
    call {OVERVIEW:#x}
    pop edx
    pop ecx
    pop eax
    push ebp
    mov ebp, esp
    add esp, -0xc
    push ebx
    push esi
    jmp {RESUME:#x}
"""

caves = [("cave_magicrefresh", CAVE, asm(SRC, CAVE))]
hooks = [(HOOK, HOOK_VAN, jmp_to(HOOK, CAVE, len(HOOK_VAN))),
         (GATE, GATE_VAN, GATE_NEW)]

if __name__ == "__main__":
    run("build_magictab_refresh", hooks, caves, SLOT)
