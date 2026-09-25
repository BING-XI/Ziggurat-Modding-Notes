#!/usr/bin/env python
r"""
build_townquake_retune.py -- Town Quake retuned by wall type and level.  AoWEPACK.dpl.
From Inioch's share8 patch_town_quake_v1.py (RE: town-quake-spell.md), in our scale.

VANILLA (TTownQuake.ExecuteTE 0x557B1DFC, phase 0x32; EBX = the city)
    `map.Random(10) < 7` -> TCity.SetWallType(0): any wall falls 70% of the time.  Then every army in
    the city -> TriggerArmyDamage 0x557B1BF4: per unit ExecuteDamageRole(ATK, DMG 10, Physical),
    ATK `mov edx,0Eh` = 14 in ours (vanilla 7, doubled).

NEW RULES (Inioch's, adopted 2026-09-25)
    * walls: wood 80%, stone 50%; underground +10% each (90% / 60%); no walls -> nothing to destroy.
    * unit damage: underground cities with no wall or a wooden wall are hit at ATK 18 instead of 14
      (his +2 on vanilla's 7, doubled); stone walls keep 14.
    "Underground" = map level 1 or 2 ([city+0x12]).  His test was level != 0, which would also count
    our Firmament (level 3); ours does not.  Wall type [city+0x4C]: 0 none, 1 wood, 2 stone, 3 the
    editor's "Random" (replaced on the first day; treated as none).

THE PATCH
    A. 0x557B1E79 `mov edx,0Ah / call Random` (10 B) -> cave_walls: the same single synced
       map.Random(10) (P1, unchanged draw count); N = 8 wood / 5 stone / 0 none, +1 underground when
       N != 0; stores the ATK (14 or 18) in BSS G_ATK; `cmp eax,N` and resumes at vanilla's jge
       0x557B1E86 (walls fall when roll < N).
    B. 0x557B1CE7 `mov edx,0Eh` -> cave_atk: edx = G_ATK, or 14 if unset.
    G_ATK = BSS 0x558FAD00 (clear gap 0x558FAC04..0x558FAF1F), reached through a call/pop delta; it
    is written in phase 0x32 immediately before TriggerArmyDamage reads it, identically on every peer.

Slot 0x5584D700-0x5584D77F, exclusive.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D700, 0x5584D700 + 0x80)
MAP_RANDOM = 0x5577827C
G_ATK = 0x558FAD00
HA, HA_VAN, HA_RESUME = 0x557B1E79, bytes.fromhex("ba0a000000e8f963fcff"), 0x557B1E86
HB, HB_VAN, HB_RESUME = 0x557B1CE7, bytes.fromhex("ba0e000000"), 0x557B1CEC
CAVE_A = 0x5584D700
WOOD, STONE, UG_BONUS = 8, 5, 1
ATK_NORMAL, ATK_UG = 14, 18


def cave_walls(va):
    return asm(f"""
        push 10
        pop edx
        call {MAP_RANDOM:#x}
        movzx ecx, byte ptr [ebx + 0x4c]
        push {WOOD}
        pop edx
        cmp ecx, 1
        je w_have
        push {STONE}
        pop edx
        cmp ecx, 2
        je w_have
        xor edx, edx
    w_have:
        push eax
        push {ATK_NORMAL}
        pop eax
        push ecx
        movzx ecx, byte ptr [ebx + 0x12]
        dec ecx
        cmp ecx, 1
        pop ecx
        ja w_store
        test edx, edx
        je w_ug
        add edx, {UG_BONUS}
    w_ug:
        cmp ecx, 2
        je w_store
        push {ATK_UG}
        pop eax
    w_store:
        push ecx
        call w_here
    w_here:
        pop ecx
        sub ecx, w_here
        mov dword ptr [ecx + {G_ATK:#x}], eax
        pop ecx
        pop eax
        cmp eax, edx
        jmp {HA_RESUME:#x}
    """, va)


def cave_atk(va):
    return asm(f"""
        call a_here
    a_here:
        pop edx
        sub edx, a_here
        mov edx, dword ptr [edx + {G_ATK:#x}]
        test edx, edx
        jne a_ok
        mov edx, {ATK_NORMAL}
    a_ok:
        jmp {HB_RESUME:#x}
    """, va)


_walls = cave_walls(CAVE_A)
CAVE_B = (CAVE_A + len(_walls) + 3) & ~3         # directly after cave_walls, never overlapping
caves = [("cave_walls", CAVE_A, _walls), ("cave_atk", CAVE_B, cave_atk(CAVE_B))]
hooks = [(HA, HA_VAN, jmp_to(HA, CAVE_A, len(HA_VAN))), (HB, HB_VAN, jmp_to(HB, CAVE_B, len(HB_VAN)))]
interior = [(HA, HA + len(HA_VAN), 0x557B1DFC, 0x557B1EA0)]

if __name__ == "__main__":
    run("build_townquake_retune", hooks, caves, SLOT, interior)
