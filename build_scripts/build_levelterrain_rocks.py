#!/usr/bin/env python
r"""
build_levelterrain_rocks.py -- Level Terrain leaves rocks matching the terrain on a flattened
mountain, hill or earth wall, instead of a bare hexagon.  AoWEPACK.dpl.

Ported from Inioch's share8 patch_level_terrain_rocks_v1.py (RE: level-terrain-rocks.md); the cave
bodies are his, relocated to our slot.

VANILLA
    TLevelTerrainTE.Execute 0x5579F16C -> worker 0x5579F068 walks the 7 hexes (EBX = TMapLevel,
    ESI = field, EDI = TE with level byte [+0x22]; x = [esp+0x10], y = [esp+0x14]).  Per valid hex:
    THSMap.ClearTerrain(map, x, y; -1, 0, level) (thunk 0x557025DC; frees EVERY terrain object on
    the hex) and, for an earth wall (terrain 7), map.ChangeTerrain (VMT +0xD0) to dirt (0xC).  A
    flattened mountain or hill is left bare.  The worker is byte-identical to vanilla in ours.

THE FIX
    Hook the 5-byte `movsx eax,[edi+0x22] / push eax` at 0x5579F109 (start of the ClearTerrain call)
    -> cave_lvl, which records the hex's pre-clear terrain and overlay, replays ClearTerrain and the
    earth->dirt branch, and, when the hex WAS a mountain (overlay 0), a hill (overlay 2) or an earth
    wall (terrain 7), calls cave_rocks(map, x, y, terrain after the dig, level); resumes at 0x5579F153.
    cave_rocks is TAoWHSMap.PlaceTerrain 0x55778EEC with a decoration filter: from the global
    resource list ([[0x558FA044]+0x24]+8) it gathers single-hex terrain objects (ClassID 0x20167,
    UsedTerrain 1) of that terrain with no overlay (0xFF, so no movement cost) whose decoration byte
    [res+0x44] is 1 (rocks) -- or 0 on dirt (0xC), whose underground rock set carries no decoration
    tag -- and places one with the resource's CreateAndPlace (VMT +0x68).  Terrains with no rock set
    (lava, ice, water) get nothing.  ⚠ The set comes from our Release.hss at run time; if a terrain
    has no matching resource, that hex simply stays bare.

RNG: P1 SYNCED, exactly like PlaceTerrain: RandSeed := map.Random(0xFFFFFF), then the pick is
map.Random(count), inside the TE.  Absolute data refs (map holder 0x558E9494, resource holder
0x558FA044, TList classref and RandSeed import slots) go through a call/pop delta; AoWEPACK rebases.

⚠ build_raiseterrain_mtn.py (SHELVED, never applied) would hook 0x5579F14D inside the span this
cave replays.  Do not apply it on top.

Slot 0x5584D480-0x5584D6FF, exclusive.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D480, 0x5584D480 + 0x280)
CAVE_LVL = 0x5584D480
HOOK, VAN, RESUME = 0x5579F109, bytes.fromhex("0fbe472250"), 0x5579F153
WORKER = 0x5579F068
G_MAP_HOLDER = 0x558E9494
G_RESHOLDER = 0x558FA044
IMP_TLIST = 0x558FB94C
IMP_RANDSEED = 0x558FB720
CLEAR_TERRAIN = 0x557025DC
TOBJ_CREATE, TOBJ_FREE = 0x557010A8, 0x557010B8
TLIST_CLEAR, TLIST_ADD, TLIST_GET = 0x55701624, 0x5570161C, 0x5570163C
TL_USED, TL_GETTERRAIN, TL_GETOVERLAY = 0x55701CA4, 0x55701C8C, 0x55701C94
MAP_RANDOM = 0x5577827C
CLASSID_TERRAINMO = 0x20167


def cave_lvl(va, rocks):
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 8
        call l_here
    l_here:
        pop eax
        sub eax, l_here
        mov dword ptr [ebp-4], eax
        movzx eax, byte ptr [esi+0x14]
        shl eax, 8
        mov al, byte ptr [esi+0x15]
        mov dword ptr [ebp-8], eax
        movsx eax, byte ptr [edi+0x22]
        push eax
        push 0
        push -1
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+{G_MAP_HOLDER:#x}]
        mov eax, dword ptr [eax]
        mov ecx, dword ptr [ebp+0x18]
        mov edx, dword ptr [ebp+0x14]
        call {CLEAR_TERRAIN:#x}
        movsx eax, byte ptr [esi+0x14]
        cmp ax, 7
        jne l_nodig
        push esi
        mov eax, dword ptr [ebp+0x18]
        push eax
        movsx eax, byte ptr [edi+0x22]
        push eax
        push 0
        push 0xc
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+{G_MAP_HOLDER:#x}]
        mov eax, dword ptr [eax]
        mov ecx, dword ptr [ebp+0x14]
        xor edx, edx
        mov esi, dword ptr [eax]
        call dword ptr [esi+0xd0]
        pop esi
    l_nodig:
        mov eax, dword ptr [ebp-8]
        cmp ah, 7
        je l_rocks
        cmp al, 0
        je l_rocks
        cmp al, 2
        jne l_done
    l_rocks:
        movsx eax, byte ptr [edi+0x22]
        push eax
        movzx eax, byte ptr [esi+0x14]
        push eax
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+{G_MAP_HOLDER:#x}]
        mov eax, dword ptr [eax]
        mov edx, dword ptr [ebp+0x14]
        mov ecx, dword ptr [ebp+0x18]
        call {rocks:#x}
    l_done:
        mov esp, ebp
        pop ebp
        jmp {RESUME:#x}
    """, va)


def cave_rocks(va):
    # cave_rocks(eax=map, edx=x, ecx=y; [ebp+8]=terrain, [ebp+0xC]=level) -> ret 8
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 0x14
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], eax
        mov dword ptr [ebp-8], edx
        mov dword ptr [ebp-0xc], ecx
        call r_here
    r_here:
        pop ebx
        sub ebx, r_here
        mov dl, 1
        mov eax, dword ptr [ebx+{IMP_TLIST:#x}]
        call {TOBJ_CREATE:#x}
        mov dword ptr [ebp-0x10], eax
        call {TLIST_CLEAR:#x}
        mov eax, dword ptr [ebx+{G_RESHOLDER:#x}]
        mov eax, dword ptr [eax+0x24]
        mov esi, dword ptr [eax+8]
        xor edi, edi
    r_loop:
        cmp edi, dword ptr [esi+8]
        jge r_pick
        mov eax, dword ptr [esi+4]
        mov eax, dword ptr [eax+edi*4]
        mov dword ptr [ebp-0x14], eax
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x24]
        cmp eax, {CLASSID_TERRAINMO:#x}
        jne r_next
        mov eax, dword ptr [ebp-0x14]
        mov eax, dword ptr [eax+0x28]
        call {TL_USED:#x}
        cmp eax, 1
        jne r_next
        mov eax, dword ptr [ebp-0x14]
        mov eax, dword ptr [eax+0x28]
        xor edx, edx
        call {TL_GETTERRAIN:#x}
        cmp al, byte ptr [ebp+8]
        jne r_next
        mov eax, dword ptr [ebp-0x14]
        mov eax, dword ptr [eax+0x28]
        xor edx, edx
        call {TL_GETOVERLAY:#x}
        cmp al, 0xff
        jne r_next
        mov eax, dword ptr [ebp-0x14]
        mov al, byte ptr [eax+0x44]
        cmp al, 1
        je r_add
        test al, al
        jne r_next
        cmp byte ptr [ebp+8], 0xc
        jne r_next
    r_add:
        mov edx, dword ptr [ebp-0x14]
        mov eax, dword ptr [ebp-0x10]
        call {TLIST_ADD:#x}
    r_next:
        inc edi
        jmp r_loop
    r_pick:
        mov eax, dword ptr [ebp-0x10]
        mov edx, dword ptr [eax+8]
        test edx, edx
        je r_free
        mov edx, 0xffffff
        mov eax, dword ptr [ebp-4]
        call {MAP_RANDOM:#x}
        mov edx, dword ptr [ebx+{IMP_RANDSEED:#x}]
        mov dword ptr [edx], eax
        mov eax, dword ptr [ebp-0x10]
        mov edx, dword ptr [eax+8]
        mov eax, dword ptr [ebp-4]
        call {MAP_RANDOM:#x}
        mov edx, eax
        mov eax, dword ptr [ebp-0x10]
        call {TLIST_GET:#x}
        mov edx, dword ptr [ebp-0xc]
        push edx
        mov edx, dword ptr [ebp+0xc]
        push edx
        mov ecx, dword ptr [ebp-8]
        mov edx, dword ptr [ebp-4]
        mov ebx, dword ptr [eax]
        call dword ptr [ebx+0x68]
    r_free:
        mov eax, dword ptr [ebp-0x10]
        call {TOBJ_FREE:#x}
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 8
    """, va)


_probe = cave_lvl(CAVE_LVL, CAVE_LVL)
CAVE_ROCKS = (CAVE_LVL + len(_probe) + 0xF) & ~0xF
caves = [("cave_lvl", CAVE_LVL, cave_lvl(CAVE_LVL, CAVE_ROCKS)),
         ("cave_rocks", CAVE_ROCKS, cave_rocks(CAVE_ROCKS))]
assert len(caves[0][2]) == len(_probe)
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE_LVL, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), WORKER, RESUME + 0x20)]

if __name__ == "__main__":
    run("build_levelterrain_rocks", hooks, caves, SLOT, interior)
