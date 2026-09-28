#!/usr/bin/env python
r"""
build_autocombat_roundcap.py -- auto-resolve ends after round 200; the attackers retreat.
AoWEPACK.dpl.  Owner request 2026-09-27.

WHY
    TFastCombat.Execute @0x55744A0C loops `ExecuteCombatRound / CheckTerminate` until [combat+0x34]
    is set, and vanilla has no round limit.  CheckTerminate @0x557274D8 ends the fight only when a
    side has no undestroyed conquer object or the flee list ([[combat+0xC]+0x2C]+8) is non-empty;
    ExecuteCombatRound's own exit fires only after a round in which NOBODY acted.  Two units that
    strike each other every round without either dying therefore loop forever -- observed live
    2026-09-27 at round 3,168,351: a flying, panicked hero (immune to the defender's ranged attack,
    no offensive melee) against a Reforming Flesh unit that heals back what it takes.  The game
    hangs with the main thread busy inside auto-resolve.

THE SITE
    55744A67  8B C3            mov  eax, ebx
    55744A69  E8 BE FD FF FF   call TFastCombat.ExecuteCombatRound @0x5574482C   <- retargeted
    55744A6E  EB 07            jmp  0x55744A77 -> CheckTerminate
    Only the rel32 changes; nothing is displaced.  cave_cap runs the round, then, if the round
    counter [[combat+0xC]+0x44] (bumped at the START of each round by TCombat.NewRound @0x5572A39F)
    has reached ROUND_CAP, tail-calls TCombat.Terminate @0x557274B8.  Terminate is a no-op if the
    round already ended the fight.

THE RESULT
    Terminate with both sides alive is the same path vanilla takes after a round with no actions:
    TCombat.UpdateStatus @0x557282E4 writes result 2 (both sides hold conquer objects),
    GetCombatResultText shows "cannot inflict damage", and the attackers retreat.  Nothing new is
    introduced downstream.

COUPLINGS
    * build_combatdiag.py (diagnostic) hooks TFastCombat.Execute's ENTRY @0x55744A0C; no overlap.
    * build_reformingflesh.py hooks the NewRound dispatch inside TCombat.NewRound; no overlap.
    * Manual tactical combat (AoWTCPCK) does not use this loop and is untouched.

Rolls: none; the cap is a round count, so every MP client stops on the same round.
PIC: rel32 only.  Slot 0x55851E00-0x55851E3F, exclusive.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, run

SLOT = (0x55851E00, 0x55851E40)
CAVE = 0x55851E00
HOOK = 0x55744A69
FN_LO, FN_HI = 0x55744A0C, 0x55744B13                      # TFastCombat.Execute
EXECUTE_ROUND = 0x5574482C                                 # TFastCombat.ExecuteCombatRound
TERMINATE = 0x557274B8                                     # TCombat.Terminate

ROUND_CAP = 200


def call_to(src, dst):
    return b"\xE8" + (dst - (src + 5)).to_bytes(4, "little", signed=True)


def build(va):
    return asm(f"""
        push eax
        call {EXECUTE_ROUND:#x}
        pop eax
        mov edx, dword ptr [eax + 0xC]
        cmp dword ptr [edx + 0x44], {ROUND_CAP}
        jl _done
        jmp {TERMINATE:#x}
    _done:
        ret
    """, va)


caves = [("cave_cap", CAVE, build(CAVE))]
hooks = [(HOOK, call_to(HOOK, EXECUTE_ROUND), call_to(HOOK, CAVE))]
interior = [(HOOK, HOOK + 5, FN_LO, FN_HI)]

if __name__ == "__main__":
    run("build_autocombat_roundcap", hooks, caves, SLOT, interior)
