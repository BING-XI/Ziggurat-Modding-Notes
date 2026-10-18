#!/usr/bin/env python
r"""
build_research_redraw.py -- the Research Book's "Currently Researching" row repaints cleanly when the
research changes.  AoWz.exe (exe_patch.py).

THE BUG (owner, 2026-10-18; reproduced live)
    With a research running, the book's second blue ribbon opens the research grid (mode 2); a click
    there switches the research (TPlayerMagicControl.ResearchSpell, measured: [magic+0x34] 73 -> 39,
    Water I -> Earth I).  The "Currently Researching" page then shows the new group's member icons
    and names drawn over the old group's.  build_tierresearch_exe.py's cave_ricon draws that row
    transparently across a 262 px strip from ResearchIcnDraw 0x4310BC; nothing restores the
    parchment under it between paints, so the previous row stays.  Cancel then pick does not show
    it.

THE FIX
    A full window repaint clears it: TAOWBaseWindow.DrawSurface (aowInt 0x598076FC) redraws the whole
    window, background first, whenever [window+0xA4] is 0, and sets it back to 1 when done
    (0x59807ED2) -- which is why the request cannot come from inside cave_ricon's own draw.
    TSpellBook.DlgUpdate is the book's per-tick OnUpdate; its published-method entry (code dword at
    VA 0x42E666, 0x431270) is retargeted to cave_resredraw.  In research modes (2/3) the cave reads
    the keyboard player's research id [magic+0x34] and the book's mode-3 pick [book+0x234]; when
    either differs from what it saw last tick, it stores both and writes Dlg [book+0x1C4] +0xA4 := 0.
    Then the vanilla entry (0x431270, which build_tierresearch_exe.py's cave_dlgupd hooks) runs.
    Cost: one full book repaint per research change, and one on the first tick after it opens.

    The method dword carries its own HIGHLOW .reloc entry, as every published-method code pointer
    does; the exe never rebases (exe_patch.run's reloc_ok).

Slot 0x0062AD80-0x0062AE7F in .hcol (RWX): state G_ID 0x0062AD80, G_SEL 0x0062AD84, code
0x0062AD90.  No randomness; local UI state only.

USAGE
    python build_research_redraw.py [--dis]   verify / dry run
    python build_research_redraw.py --apply
    python build_research_redraw.py --undo    surgical
"""
import struct
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, run

SLOT = (0x0062AD80, 0x0062AE80)
G_ID, G_SEL, CAVE = 0x0062AD80, 0x0062AD84, 0x0062AD90
METHOD_DWORD, DLGUPDATE = 0x0042E666, 0x00431270
T_GETPLAYERS = 0x402464      # AoWE.TPlayerList.GetPlayers(eax=list, edx=index)
G_MAP = 0x45DF7C             # [[g]] = AoWHSMap; +0xA5 keyboard player, +0x140 player list

SRC = f"""
    pushad
    mov ebx, eax
    mov al, byte ptr [ebx+0x220]
    cmp al, 2
    jb Lout
    cmp al, 3
    ja Lout
    mov eax, dword ptr [{G_MAP:#x}]
    mov eax, dword ptr [eax]
    test eax, eax
    je Lout
    movsx edx, byte ptr [eax+0xa5]
    mov eax, dword ptr [eax+0x140]
    call {T_GETPLAYERS:#x}
    test eax, eax
    je Lout
    mov eax, dword ptr [eax+0x54]
    test eax, eax
    je Lout
    mov ecx, dword ptr [eax+0x34]
    mov edx, dword ptr [ebx+0x234]
    cmp ecx, dword ptr [{G_ID:#x}]
    jne Lchg
    cmp edx, dword ptr [{G_SEL:#x}]
    je Lout
Lchg:
    mov dword ptr [{G_ID:#x}], ecx
    mov dword ptr [{G_SEL:#x}], edx
    mov eax, dword ptr [ebx+0x1c4]
    test eax, eax
    je Lout
    mov byte ptr [eax+0xa4], 0
Lout:
    popad
    jmp {DLGUPDATE:#x}
"""

caves = [("state", G_ID, bytes(8)), ("cave_resredraw", CAVE, asm(SRC, CAVE))]
hooks = [(METHOD_DWORD, struct.pack("<I", DLGUPDATE), struct.pack("<I", CAVE))]

if __name__ == "__main__":
    run("build_research_redraw", hooks, caves, SLOT, reloc_ok=(METHOD_DWORD,))
