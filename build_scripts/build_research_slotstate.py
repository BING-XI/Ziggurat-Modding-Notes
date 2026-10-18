#!/usr/bin/env python
r"""
build_research_slotstate.py -- Research Book entries are always drawn normal and clickable; they no
longer inherit grey text and a hidden click button from the last spell-book view.  AoWz.exe
(exe_patch.py).

THE BUG (player report 2026-10-18; found statically, not reproduced)
    "X out of the research pick, open it again later: every entry grey, none clickable; reloading
    fixed it."  The X was incidental.  build_tierresearch_exe.py's cave_costskip (hook 0x42EAB1)
    sends modes 2/3 from 0x42EAB1 straight to 0x42ECB1 to drop the mana Cost/Upkeep text.  The range
    it jumps over also holds FillSlot's colour/enable block 0x42EB42-0x42EC4F -- the only code that
    sets a slot's four label colours (vcall +0x70) and shows or hides its click button (vcall +0x6C).
    The cast book and the research book are one TSpellBook, created once per process
    (Application.CreateForm at 0x459D81), sharing the eight slots, so a research entry kept whatever
    the last cast-mode population left in that slot.  Cast mode greys a slot (0x4C4C4C, button
    hidden, icon Tag |= 0x10) when, on the map, the spell has no global flag ([spell+0xC] bit 0: every
    entry under the Combat ribbon) or the leader is casting (THero.Casting, [hero+0x84] <> 0: every
    entry); in combat, when the spell has no combat flag (bit 1), the leader is casting, or
    CanCastSpellInstantly fails.  The state survived turns and reloads; a restart, or a cast view
    with a castable spell in that slot, cleared it.

    The same block holds vanilla's research lock (mode 2: grey every entry while
    [magic+0x34] <> 0), so the lock has never run in the mod and research can be switched mid-way
    (build_research_redraw.py relies on that).  Owner ruling 2026-10-18: keep entries always
    clickable; do not restore the lock.

THE FIX
    Hook 0x42ED55, 6 B `8A 86 20 02 00 00` (mov al,[esi+0x220]): the head of FillSlot's mode>=2
    tail, reached only from 0x42ECB9 (`jae`), no .reloc entry, claimed by no other script.  cave
    cave_slotstate: in modes 2/3 it runs vanilla's own normal-state block (0x42EC0F-0x42EC4F) --
    memo [ebp+0xC] and name [ebp+0x18] SetColor 0x13243C, class [ebp+0x14] (the research turns line)
    and cost (edi) SetColor 0x5A2734, button [ebp+0x1C] SetVisible(True), icon [ebp+8] Tag &= 0xF --
    then replays the displaced `mov al,[esi+0x220]` and jumps to 0x42ED5B.  Modes >= 4 pass straight
    through: they never skip vanilla's block.  ebx (the spell) is non-nil here (0x42E90E).

Slot 0x0062AF80-0x0062AFFF in .hcol.  No randomness; local UI state only, so multiplayer-neutral.
Couplings: build_tierresearch_exe.py's cave_costskip is what makes this necessary; if that cave is
ever removed, this one still runs after vanilla's block and overrides the research lock.

Unproven: not run in the game.  Repro of the bug: map spell book -> Combat ribbon -> close -> open
the research book.

USAGE
    python build_research_slotstate.py [--dis]   verify / dry run
    python build_research_slotstate.py --apply
    python build_research_slotstate.py --undo    surgical
"""
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, jmp_to, run

SLOT = (0x0062AF80, 0x0062B000)
CAVE = 0x0062AF80
HOOK, RESUME = 0x0042ED55, 0x0042ED5B
VANILLA = bytes.fromhex("8a 86 20 02 00 00".replace(" ", ""))
COL_TEXT, COL_SUB = 0x13243C, 0x5A2734     # FillSlot's normal colours, 0x42EC0F-0x42EC3F

SRC = f"""
    cmp byte ptr [esi+0x220], 2
    jb Lout
    cmp byte ptr [esi+0x220], 3
    ja Lout
    mov edx, {COL_TEXT:#x}
    mov eax, dword ptr [ebp+0xc]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x70]
    mov edx, {COL_TEXT:#x}
    mov eax, dword ptr [ebp+0x18]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x70]
    mov edx, {COL_SUB:#x}
    mov eax, dword ptr [ebp+0x14]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x70]
    mov edx, {COL_SUB:#x}
    mov eax, edi
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x70]
    mov dl, 1
    mov eax, dword ptr [ebp+0x1c]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
    mov eax, dword ptr [ebp+0x8]
    and dword ptr [eax+0xc], 0xf
Lout:
    mov al, byte ptr [esi+0x220]
    jmp {RESUME:#x}
"""

blob = asm(SRC, CAVE)
caves = [("cave_slotstate", CAVE, blob)]
hooks = [(HOOK, VANILLA, jmp_to(HOOK, CAVE, len(VANILLA)))]

if __name__ == "__main__":
    run("build_research_slotstate", hooks, caves, SLOT)
