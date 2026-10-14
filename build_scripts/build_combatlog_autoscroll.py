#!/usr/bin/env python
r"""
build_combatlog_autoscroll.py -- the combat log scrolls to its newest line.  AoWz.exe (exe_patch.py).
Owner request 2026-10-14.

VANILLA
    The log window is a clone of TChatWindow and keeps the chat's scroll handler: the memo's
    OnUpdate is TChatWindow.ChatMemoUpdate @0x41306C, which, when the form's flag [form+0x70] is
    set, calls TAOWScrollBar.SetFPos(ChatSB, Max + 1 - NumberVisible) and clears the flag.
    Whoever appends a line sets the flag (cave_drain in build_combatlog_exe.py, vanilla chat).
    But TAoWComponent.Update (aowInt 0x59803698) fires OnUpdate FIRST and only then runs Setup,
    which re-wraps the text (TAOWMemo.SetSize @0x598189C0, VMT +0x30) and sets the scrollbar's
    Max from the new line count.  Appending a line clears the memo's layout byte [memo+0x2E]
    (TStringList.OnChange -> TAoWComponent.OnChangeText @0x59802464); SetSize sets it back to 1
    (TAoWComponent.SetSize @0x598030B0).  So the scroll always used the Max from BEFORE the
    append, cleared the flag, and the view stopped one batch short of the newest lines.

THE FIX
    6 B at 0x41306F (`cmp byte [ebx+0x70],0 ; je 0x41308E`) -> jmp cave_chatscroll + nop.  The cave
    replays the flag test, then leaves the flag set and returns while the memo ([form+0x48]) still
    has [memo+0x2E] == 0; the scroll runs on the first update after the re-wrap, with the current
    Max.  Same frame order in live combat (ring drained from TMWindow.MapWindowUpdate) and in a
    replay (build_replaylog.py sets the flag after its own TStringList.Add).  The multiplayer chat
    window shares the handler and gets the same fix.

    No .reloc entry and no inbound branch inside the displaced bytes (checked 2026-10-14).
    Cave 0x0062AB00 in .hcol's free run 0x0062AB00..0x0062B000 (Zig notes/12-re-toolchain.md);
    slot 0x0062AB00-0x0062AB3F, exclusive.

USAGE
    python build_combatlog_autoscroll.py [--dis]     verify / dry run
    python build_combatlog_autoscroll.py --apply
    python build_combatlog_autoscroll.py --undo      surgical
"""
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, jmp_to, run

SLOT = (0x0062AB00, 0x0062AB40)
CAVE = 0x0062AB00
HOOK = 0x0041306F
HOOK_VAN = bytes.fromhex("807b700074" "19")    # cmp byte [ebx+0x70],0 ; je 0x41308E
SCROLL = 0x00413075                            # mov eax,[ebx+0x68] -- the SetFPos block
OUT = 0x0041308E                               # pop ebx ; ret

SRC = f"""
    cmp byte ptr [ebx+0x70], 0
    je {OUT:#x}
    mov eax, dword ptr [ebx+0x48]
    test eax, eax
    je {SCROLL:#x}
    cmp byte ptr [eax+0x2E], 0
    je {OUT:#x}
    jmp {SCROLL:#x}
"""

caves = [("cave_chatscroll", CAVE, asm(SRC, CAVE))]
hooks = [(HOOK, HOOK_VAN, jmp_to(HOOK, CAVE, len(HOOK_VAN)))]

if __name__ == "__main__":
    run("build_combatlog_autoscroll", hooks, caves, SLOT)
