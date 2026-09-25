#!/usr/bin/env python
r"""
build_customize_name.py -- in a multiplayer session, the name typed at leader customisation is
saved as the player name, so the next lobby already shows it.  AoWz.exe + AoWzCompat.exe.

From Inioch's share8 patch_customize_name_registry_v1.py (v2 design; customize-name-registry.md).

VANILLA
    The player name is registry General\strings\0 (TAoWRegistry.GetString/SetString id 0; the
    registry object is [[[0x45DF74]]+0x5C]).  The pre-lobby name dialog fills two TAOWEdits,
    [[0x45A598]]+0x90 and +0xC4, from it (0x4535C2..0x4535F2), and TMainForm.FormDestroy writes the
    +0x90 edit's text back on shutdown (0x45395C).
    TLeaderSetupWin's finish routine 0x416D9C pushes the customised name [[ctl+0x14]+0x60] to
    DirectPlay (0x41468C, only when TSetupControl.GetRemote says a network session is running), then
    calls ctl.Done (VMT+0x4C) and Release.  Nothing writes it to the registry, so it is lost.

THE FIX
    Hook the 7-byte `mov eax,esi / mov edx,[eax] / call [edx+0x4C]` at 0x416DD8 -> cave_custname:
    when a network session is running (the same GetRemote test as 0x41468C, so single-player and
    PBEM leader names never touch the player name) -> SetString(reg, 0, name), and SetGText(name) on
    both pre-lobby edits so FormDestroy's shutdown save writes the same name; then the displaced
    ctl.Done call and back to 0x416DDF.
    A bare SetString is not enough (Inioch's v1): FormDestroy overwrites it with the old edit text.

    build_pbem_leadersetup.py anchors TLeaderSetupWin.Finish; its X_ANCHORS entry now skips these
    7 bytes (split at 0x416DD8 / 0x416DDF).

Rolls: none.  Exe caves may use absolute addresses (fixed base).  .hcol slot 0x0062A480-0x0062A51F,
exclusive.  Both exes in lockstep via exe_patch.py.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, jmp_to, run

SLOT = (0x0062A480, 0x0062A520)
CAVE = 0x0062A480
HOOK, VAN, RESUME = 0x00416DD8, bytes.fromhex("8bc68b10ff524c"), 0x00416DDF
G_SETUP, G_APP, G_OPTWIN = 0x0045A454, 0x0045DF74, 0x0045A598
GETREMOTE, SETSTRING, SETGTEXT = 0x00402F4C, 0x00401F04, 0x0040326C


def build(va):
    return asm(f"""
        push edi
        mov eax, dword ptr [{G_SETUP:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        je n_done
        mov eax, dword ptr [eax + 0x48]
        test eax, eax
        je n_done
        call {GETREMOTE:#x}
        test al, al
        je n_done
        mov edi, dword ptr [esi + 0x14]
        test edi, edi
        je n_done
        mov edi, dword ptr [edi + 0x60]
        mov eax, dword ptr [{G_APP:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        je n_edits
        mov eax, dword ptr [eax + 0x5c]
        test eax, eax
        je n_edits
        mov ecx, edi
        xor edx, edx
        call {SETSTRING:#x}
    n_edits:
        mov eax, dword ptr [{G_OPTWIN:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        je n_done
        push eax
        mov eax, dword ptr [eax + 0x90]
        test eax, eax
        je n_edit2
        mov edx, edi
        call {SETGTEXT:#x}
    n_edit2:
        pop eax
        mov eax, dword ptr [eax + 0xc4]
        test eax, eax
        je n_done
        mov edx, edi
        call {SETGTEXT:#x}
    n_done:
        pop edi
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x4c]
        jmp {RESUME:#x}
    """, va)


caves = [("cave_custname", CAVE, build(CAVE))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]

if __name__ == "__main__":
    run("build_customize_name", hooks, caves, SLOT)
