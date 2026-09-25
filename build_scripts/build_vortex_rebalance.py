#!/usr/bin/env python
r"""
build_vortex_rebalance.py -- Vortex hits harder, reaches every non-flying unit, and drains movement.
AoWEPACK.dpl.  From Inioch's share8 patch_vortex_v1.py sites A/B/C, in our (doubled) scale; his
site D, the re-seed, is ours already (build_vortex_reseed.py, 0x557A150C).

LIVE BEFORE (TVortexTE damage pass, token phase 0x50; EDI = the unit; flyers skipped earlier)
    rating 14 if Swimming (ability 2), else 20 if Sailing (0x17), else 0 (no roll at all);
    ExecuteDamageRole(ATK 16, rating, physical).  (Vanilla 7/10/0 and ATK 8, doubled by
    build_damhpdouble.py / build_statdouble.py.)

NEW (Inioch's rebalance x2; drains unchanged, movement points were never doubled)
    ATK 20; rating Sailing 14, Swimming 10, every other non-flying unit 4.  A unit that actually took
    damage also loses RandInt(N) movement points: N = 9 Sailing (0..8), 13 Swimming (0..12), 7 other
    (0..6), clamped to its current points (THero.SetMovePoints does not clamp negatives itself).
    Flyers (Flying / Floating / Wind Walking) are still skipped.

SITES
    A  0x557A1605..0x557A163A  the 54-byte ability classifier -> jmp cave_rating + NOPs
    B  0x557A1645              the ATK imm of `mov edx,10h` -> 14h (one byte)
    C  0x557A168C              `mov byte [ebp-0Ah],1 / jmp` (damage-dealt tail, 6 B) -> cave_drain
    ⚠ Sites A and B overwrite immediates listed in damhp_manifest.json (0x557A1619, 0x557A1633) and
    fivepct_manifest.json (0x557A1645); those doubling scripts will report them as foreign, like the
    other deliberate retunes they already list.

RNG: the drain is a raw System.@RandInt (0x55701080) in the same pass as the damage roll, after
build_vortex_reseed.py's entry re-anchor (RandSeed := synced Random), so every peer draws the same.
It is drawn only for a unit that took damage, which every peer agrees on.

Slot 0x5584D780-0x5584D87F, exclusive.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D780, 0x5584D880)
CAVE_RATING, CAVE_DRAIN = 0x5584D780, 0x5584D7C0
RANDINT = 0x55701080
A_LO, A_HI = 0x557A1605, 0x557A163B
A_VAN = bytes.fromhex(
    "ba02000000" "8bc7" "8b08" "ff9148010000" "84c0" "7407" "bb0e000000" "eb1c"
    "ba17000000" "8bc7" "8b08" "ff9148010000" "84c0" "7407" "bb14000000" "eb02" "33db")
assert len(A_VAN) == A_HI - A_LO
B_SITE = 0x557A1645
C_SITE, C_VAN, C_RESUME = 0x557A168C, bytes.fromhex("c645f601eb02"), 0x557A1694
FN = 0x557A13CC                         # TVortexTE.Execute
ATTACK = 20
R_SAIL, R_SWIM, R_OTHER = 14, 10, 4
D_SAIL, D_SWIM, D_OTHER = 9, 13, 7      # RandInt(N) -> 0..N-1


def has(ab, lbl):
    return f"""
        mov edx, {ab:#x}
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne {lbl}
    """


def cave_rating(va):
    return asm(has(2, "r_swim") + has(0x17, "r_sail") + f"""
        mov ebx, {R_OTHER}
        jmp r_done
    r_swim:
        mov ebx, {R_SWIM}
        jmp r_done
    r_sail:
        mov ebx, {R_SAIL}
    r_done:
        jmp {A_HI:#x}
    """, va)


def cave_drain(va):
    return asm("""
        mov byte ptr [ebp - 0xa], 1
        push ebx
    """ + has(2, "d_swim") + has(0x17, "d_sail") + f"""
        mov eax, {D_OTHER}
        jmp d_roll
    d_swim:
        mov eax, {D_SWIM}
        jmp d_roll
    d_sail:
        mov eax, {D_SAIL}
    d_roll:
        call {RANDINT:#x}
        mov ebx, eax
        test ebx, ebx
        je d_out
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xd8]
        movsx eax, al
        test eax, eax
        jle d_out
        cmp ebx, eax
        jle d_ok
        mov ebx, eax
    d_ok:
        sub eax, ebx
        mov edx, eax
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xdc]
    d_out:
        pop ebx
        jmp {C_RESUME:#x}
    """, va)


caves = [("cave_rating", CAVE_RATING, cave_rating(CAVE_RATING)),
         ("cave_drain", CAVE_DRAIN, cave_drain(CAVE_DRAIN))]
hooks = [(A_LO, A_VAN, jmp_to(A_LO, CAVE_RATING, len(A_VAN))),
         (B_SITE, b"\x10", bytes((ATTACK,))),
         (C_SITE, C_VAN, jmp_to(C_SITE, CAVE_DRAIN, len(C_VAN)))]
interior = [(A_LO, A_HI, FN, 0x557A16A0), (C_SITE, C_SITE + len(C_VAN), FN, 0x557A16A0)]

if __name__ == "__main__":
    run("build_vortex_rebalance", hooks, caves, SLOT, interior)
