#!/usr/bin/env python
r"""
build_ai_replan_cap.py -- an AI army group can re-plan at most 20 times per activation, so an
unexecutable target cannot spin the AI turn forever.  AoWEPACK.dpl.

From Inioch's share4 build_ai_group_restart_cap.py (aowx-ai-turn-hang.md, reproduced live and
proved by injection into a stuck game).  Ours also resets the counter in Activate, because the
group-control object outlives one activation.

VANILLA
    TAIGroupControl.MoveExecuterDone 0x55738C30: when the move executer reports result 5 (plan
    invalidated -- TAIMoveExecuter.InvalidateMove or an exception in Process) it resets the group's
    state machine [agc+0x16C] to 0 unconditionally (0x55738C66).  If the target selector then
    re-picks the same unexecutable plan (seen: a 0-MP party in the Depths whose raze target it can
    never reach), the pipeline restarts forever, ~1.7 s of pathfinding per pass, and the AI player
    never ends its turn.

THE FIX
    Counter = byte [agc+0x156], alignment padding after the word at +0x154 (no AoWEPACK code touches
    +0x155..+0x157 of any TAIGroupControl; the only +0x156 user is TAoWMapControl.)
      A  hook 0x55738C66 (10 B, `xor eax,eax / mov [ebx+0x16C],eax / pop ebx / ret`) -> cave_cap:
         inc the counter; below 20 -> the vanilla restart; at 20 -> TAIGroupControl.Done
         (0x557389B0: marks the group processed, state -1) and return.
      B  hook 0x55739067 (8 B, `xor eax,eax / mov [ebx+0x16C],eax` in TAIGroupControl.Activate)
         -> cave_reset: also zero the counter.  Activate is inherited by 19 AGC VMTs.
    A group that never converges now costs at most 20 passes once per activation.

Rolls: none.  PIC: ebx-relative and rel32 only.  Slot 0x5584D880-0x5584D8BF, exclusive.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D880, 0x5584D8C0)
CAVE_A, CAVE_B = 0x5584D880, 0x5584D8A8
HOOK_A, VAN_A = 0x55738C66, bytes.fromhex("33c089836c0100005bc3")
HOOK_B, VAN_B, RESUME_B = 0x55739067, bytes.fromhex("33c089836c010000"), 0x5573906F
AGC_DONE = 0x557389B0
CAP = 20


def build_a(va):
    return asm(f"""
        mov al, byte ptr [ebx + 0x156]
        inc al
        mov byte ptr [ebx + 0x156], al
        cmp al, {CAP}
        jb c_restart
        mov eax, ebx
        call {AGC_DONE:#x}
        pop ebx
        ret
    c_restart:
        xor eax, eax
        mov dword ptr [ebx + 0x16c], eax
        pop ebx
        ret
    """, va)


def build_b(va):
    return asm(f"""
        xor eax, eax
        mov dword ptr [ebx + 0x16c], eax
        mov byte ptr [ebx + 0x156], al
        jmp {RESUME_B:#x}
    """, va)


caves = [("cave_cap", CAVE_A, build_a(CAVE_A)), ("cave_reset", CAVE_B, build_b(CAVE_B))]
hooks = [(HOOK_A, VAN_A, jmp_to(HOOK_A, CAVE_A, len(VAN_A))),
         (HOOK_B, VAN_B, jmp_to(HOOK_B, CAVE_B, len(VAN_B)))]
interior = [(HOOK_A, HOOK_A + len(VAN_A), 0x55738C30, 0x55738C9A),
            (HOOK_B, HOOK_B + len(VAN_B), 0x55739064, 0x557390BC)]

if __name__ == "__main__":
    run("build_ai_replan_cap", hooks, caves, SLOT, interior)
