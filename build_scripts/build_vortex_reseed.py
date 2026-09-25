#!/usr/bin/env python
r"""
build_vortex_reseed.py -- Vortex no longer deals identical damage on every cast.  AoWEPACK.dpl.

THE VANILLA BUG (found live by Inioch, share8 `aowx-vortex-spell.md`, his `patch_vortex_v1.py`
site D; verified here 2026-09-24)
    TVortexTE.ShowAnimation 0x557A1178, run every animation frame, sets
    `System.RandSeed := map[+0x22C]` (0x557A11EA) -- a per-game constant.  The damage pass
    (TVortexTE.Process phase 0x50) then calls ExecuteDamageRole 0x557A164B, which draws RAW, without
    re-seeding.  So every cast replays the same rolls: the first unit hit (the transporter, i.e.
    every ship) always takes the same damage.

THE FIX -- the engine's own bridge (the idiom IncommingStorm, TriggerFireDamage and the poison plant
use at entry): at the top of the damage pass,
    System.RandSeed := TAoWHSMap.Random(map, $FFFFFF)
guarded exactly as Random guards itself (0x5577827C): raw-mode flag [map+0x3C]&8 -> draw; else
GetSynchronised 0x55775608 must allow it, otherwise the re-seed is skipped rather than tripping
Random's "Invalid AoWHSMap.Random use" assertion.  Phase 0x50 runs inside the synchronised token
execution (vanilla TTornadoTE.Process draws synced in its own phase 0x50, 0x557A08AB), so every
peer makes the same one synced draw and the raw stream after it is replicated.  RNG pattern: P1
synced draw re-anchoring P2 raw -- CLAUDE.md's sanctioned bridge; draw count identical on every
peer.

    0x557A150C `mov ebx,[esi+0x2C] / test ebx,ebx` (5 B) -> cave -> replays both -> 0x557A1511 (je).
    EAX/ECX/EDX are dead there (overwritten before use after 0x557A1511); EDI (the phase) and ESI
    (the TE) are untouched.  System.RandSeed is reached through AoWEPACK's own import slot
    0x558FB720 (VCL30 System.RandSeed).  PIC: one call/pop anchor for the two globals.
    Only Inioch's site D: his sites A-C are a Vortex rebalance, not ported.

Slot 0x5584D240-0x5584D2BF, exclusive.

USAGE
    python build_vortex_reseed.py            verify / dry run (writes nothing)
    python build_vortex_reseed.py --dis
    python build_vortex_reseed.py --apply
    python build_vortex_reseed.py --undo     surgical
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D240, 0x5584D2C0)
CAVE = 0x5584D240
HOOK = 0x557A150C
VAN = bytes.fromhex("8b5e2c85db")           # mov ebx,[esi+0x2C] / test ebx,ebx
RESUME = 0x557A1511
MAP_GLOBAL, RANDSEED_IAT = 0x558FA040, 0x558FB720
MAP_RANDOM, GET_SYNCHRONISED = 0x5577827C, 0x55775608

SRC = f"""
    call v_anchor
v_anchor:
    pop ecx
    sub ecx, v_anchor
    mov eax, [ecx+{MAP_GLOBAL:#x}]
    test eax, eax
    jz v_done
    test byte ptr [eax+0x3C], 8
    jne v_draw
    push ecx
    push eax
    call {GET_SYNCHRONISED:#x}
    movzx edx, al
    pop eax
    pop ecx
    test edx, edx
    jz v_done
v_draw:
    push ecx
    mov edx, 0xFFFFFF
    call {MAP_RANDOM:#x}
    pop ecx
    mov edx, [ecx+{RANDSEED_IAT:#x}]
    mov [edx], eax
v_done:
    mov ebx, [esi+0x2C]
    test ebx, ebx
    jmp {RESUME:#x}
"""

caves = [("cave_reseed", CAVE, asm(SRC, CAVE))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), 0x557A14F6, 0x557A1740)]   # 0x557A14F6: an instruction boundary

if __name__ == "__main__":
    run("build_vortex_reseed", hooks, caves, SLOT, interior)
