#!/usr/bin/env python
r"""
build_group_move_map.py -- world-map multi-party moves are planned front first, and a party may
route through selected parties planned before it.  AoWEPACK.dpl.

Owner's rulings 2026-09-24 (memory aow1-group-move-design): plan sequentially in execution order,
front of the column first; merge on arrival while they fit; a later mover stops where an earlier
one blocks it, with no re-planning at execution.  The tactical half is build_group_move_tc.py.

VANILLA (all read on the pristine DLL)
    TSelectedArmy.SelectPath 0x55792B6C, multi-party branch: for idx 0..n-1 of the move list
    [sel+8] it calls CalculateMovePath (VMT+8) with the clicked hex.  Each party's route is planned
    as if every other party stood still: TArmyHS.CanMoveOver 0x55790E48 lets an army pass an own
    army's hex only if TArmy.CanCombine says the two fit in one stack (8 units); otherwise it
    returns 2 (may end there, may not pass).  So parties queued in a corridor detour around each
    other, or find no route, although the one in front is about to leave.
    ExecuteMove -> 0x5574AC68 already does the rest: CalculateMovePositions sends each party as far
    as its movement reaches ([ms+0x24] = MovePointsToPos), the settle callback 0x5574AAA4 merges
    parties on the target while the stack stays within 8 and backs the others off one hex at a
    time, and the TArmyDefaultMoveTEs go into one TMultiMoveTE in move-list order.

    NOT the fix: Inioch's 1-byte "dropped-party" patch at 0x55792A6C (7D 35 -> EB 35).  That branch
    runs only when [sel+0x18] == 1, which only TSelectedArmy.SelectBuildRoad sets: it is the
    road-construction check that a road must be finishable this turn, not the group move.

THE FIX
    A  hook 0x55792CE5 (8 B, `mov eax,[ebx+8] / mov edx,[eax] / call [edx+0x54]`, just before the
       multi-party loop) -> cave_order:
         pass 1: plan every party exactly as vanilla does (CalculateMovePath per index);
         insertion-sort the move list's TList by route length [[ms+8]+8], ascending, stable,
           no route = last -- so the front of the column is index 0;
         then vanilla's loop re-plans every party in that order (pass 2).
       [sel+0xC] (the single-party index) is -1 on this branch, so no stored index goes stale.
       Execution order follows, because the move TEs are created in move-list order.
    B  hook 0x55792D07 (10 B, the loop's `mov edx,[ebp-8] / mov eax,ebx / mov edi,[eax] /
       call [edi+8]`) -> cave_call: publish G_SEL = sel and G_IDX = idx in BSS around the call,
       clear G_SEL after it.
    C  hook TArmyHS.CanMoveOver entry 0x55790E48 (6 B) -> cave_over: while G_SEL is set, an army
       that is one of the selected parties at an index below G_IDX, will leave its hex this turn
       (MovePointsToPos(route, [ms+0x14]) < count-1) and belongs to the moving player, returns 1
       (can move over).
       Anything else runs vanilla.
    Merge on arrival and stop-where-blocked are vanilla (settle callback; TMoveArmyTE's per-step
    CanMoveNext against the real map at execution).

SCOPE / MULTIPLAYER
    Only the human's multi-party click reaches SelectPath's multi branch; G_SEL is zero everywhere
    else, so AI pathing and single-party moves are untouched.  Planning is local; the planned paths
    travel inside the move tokens, as vanilla.  No random draws.
    Pass 1 doubles the pathfinding cost of a multi-party click.

BSS G_SEL 0x558FAD10, G_IDX 0x558FAD14 (clear gap 0x558FAC04..0x558FAF1F).  PIC via call/pop.
Slot 0x5584D900-0x5584DAFF, exclusive.  Surgical --undo (the BSS needs no restore).
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D900, 0x5584DB00)
CAVE_A = 0x5584D900
HOOK_A, VAN_A, RESUME_A = 0x55792CE5, bytes.fromhex("8b43088b10ff5254"), 0x55792CED
HOOK_B, VAN_B, RESUME_B = 0x55792D07, bytes.fromhex("8b55f88bc38b38ff5708"), 0x55792D11
HOOK_C, VAN_C, RESUME_C = 0x55790E48, bytes.fromhex("535657558bfa"), 0x55790E4E
G_SEL, G_IDX = 0x558FAD10, 0x558FAD14
NOROUTE = 0x7FFFFFFF
MP2POS = 0x557638D8          # TMovepath.MovePointsToPos: index the budget reaches (count-1 = none)


def build_a(va):
    return asm(f"""
        pushad
        mov eax, dword ptr [ebx + 8]
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        push eax
        xor edi, edi
    a_plan:
        cmp edi, dword ptr [esp]
        jge a_sort
        movsx eax, byte ptr [ebp - 2]
        push eax
        movsx eax, byte ptr [ebp + 8]
        push eax
        mov cl, byte ptr [ebp - 1]
        mov edx, edi
        mov eax, ebx
        mov esi, dword ptr [eax]
        call dword ptr [esi + 8]
        inc edi
        jmp a_plan
    a_sort:
        pop eax
        mov eax, dword ptr [ebx + 8]
        mov eax, dword ptr [eax + 8]
        mov esi, dword ptr [eax + 4]
        mov ecx, dword ptr [eax + 8]
        mov edi, 1
    a_outer:
        cmp edi, ecx
        jge a_done
        mov eax, dword ptr [esi + edi*4]
        mov edx, dword ptr [eax + 8]
        mov edx, dword ptr [edx + 8]
        test edx, edx
        jne a_key
        mov edx, {NOROUTE:#x}
    a_key:
        mov ebx, edi
        push ecx
    a_inner:
        test ebx, ebx
        je a_place
        mov ecx, dword ptr [esi + ebx*4 - 4]
        mov ecx, dword ptr [ecx + 8]
        mov ecx, dword ptr [ecx + 8]
        test ecx, ecx
        jne a_prev
        mov ecx, {NOROUTE:#x}
    a_prev:
        cmp ecx, edx
        jle a_place
        mov ecx, dword ptr [esi + ebx*4 - 4]
        mov dword ptr [esi + ebx*4], ecx
        dec ebx
        jmp a_inner
    a_place:
        mov dword ptr [esi + ebx*4], eax
        pop ecx
        inc edi
        jmp a_outer
    a_done:
        popad
        mov eax, dword ptr [ebx + 8]
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        jmp {RESUME_A:#x}
    """, va)


def build_b(va):
    head = asm("push ecx", va)
    a1 = va + len(head) + 5
    call1 = asm(f"call {a1:#x}", va + len(head))
    mid = asm(f"""
        pop ecx
        sub ecx, {a1:#x}
        mov dword ptr [ecx + {G_SEL:#x}], ebx
        mov edx, dword ptr [ebp - 8]
        mov dword ptr [ecx + {G_IDX:#x}], edx
        pop ecx
        mov edx, dword ptr [ebp - 8]
        mov eax, ebx
        mov edi, dword ptr [eax]
        call dword ptr [edi + 8]
    """, a1)
    here = a1 + len(mid)
    a2 = here + 5
    call2 = asm(f"call {a2:#x}", here)
    tail = asm(f"""
        pop ecx
        sub ecx, {a2:#x}
        mov dword ptr [ecx + {G_SEL:#x}], 0
        jmp {RESUME_B:#x}
    """, a2)
    return head + call1 + mid + call2 + tail


def build_c(va):
    head = asm("push ecx\npush edx", va)
    a1 = va + len(head) + 5
    call1 = asm(f"call {a1:#x}", va + len(head))
    body = asm(f"""
        pop ecx
        sub ecx, {a1:#x}
        mov edx, dword ptr [ecx + {G_SEL:#x}]
        test edx, edx
        je o_van
        mov ecx, dword ptr [ecx + {G_IDX:#x}]
        push ebx
        mov ebx, dword ptr [esp + 4]
        mov ebx, dword ptr [ebx]
        mov bl, byte ptr [ebx + 9]
        push eax
        mov eax, dword ptr [eax + 0x1c]
        cmp bl, byte ptr [eax + 0x12]
        pop eax
        jne o_pop
        mov edx, dword ptr [edx + 8]
        mov edx, dword ptr [edx + 8]
        mov edx, dword ptr [edx + 4]
    o_scan:
        dec ecx
        js o_pop
        mov ebx, dword ptr [edx + ecx*4]
        cmp dword ptr [ebx + 0x10], eax
        jne o_scan
        push eax
        push ecx
        push edx
        mov eax, dword ptr [ebx + 8]
        mov edx, dword ptr [ebx + 0x14]
        call {MP2POS:#x}
        mov ebx, dword ptr [ebx + 8]
        mov ebx, dword ptr [ebx + 8]
        dec ebx
        cmp eax, ebx
        pop edx
        pop ecx
        pop eax
        jge o_pop
        pop ebx
        pop edx
        pop ecx
        mov eax, 1
        ret
    o_pop:
        pop ebx
    o_van:
        pop edx
        pop ecx
        push ebx
        push esi
        push edi
        push ebp
        mov edi, edx
        jmp {RESUME_C:#x}
    """, a1)
    return head + call1 + body


BLOB_A = build_a(CAVE_A)
CAVE_B = (CAVE_A + len(BLOB_A) + 0xF) & ~0xF
BLOB_B = build_b(CAVE_B)
CAVE_C = (CAVE_B + len(BLOB_B) + 0xF) & ~0xF
caves = [("cave_order", CAVE_A, BLOB_A), ("cave_call", CAVE_B, BLOB_B),
         ("cave_over", CAVE_C, build_c(CAVE_C))]
hooks = [(HOOK_A, VAN_A, jmp_to(HOOK_A, CAVE_A, len(VAN_A))),
         (HOOK_B, VAN_B, jmp_to(HOOK_B, CAVE_B, len(VAN_B))),
         (HOOK_C, VAN_C, jmp_to(HOOK_C, CAVE_C, len(VAN_C)))]
interior = [(HOOK_A, HOOK_A + len(VAN_A), 0x55792B6C, 0x55792D6E),
            (HOOK_B, HOOK_B + len(VAN_B), 0x55792B6C, 0x55792D6E),
            (HOOK_C, HOOK_C + len(VAN_C), 0x55790E48, 0x55790F5C)]

if __name__ == "__main__":
    run("build_group_move_map", hooks, caves, SLOT, interior)
