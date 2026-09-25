#!/usr/bin/env python
r"""
build_ai_selfheal.py -- tactical AI units with Healing heal themselves.  AoWTCPCK.dpl, two caves.

Executor from Inioch's share8 patch_ai_selfheal_exec_v1.py.  The proposal is ours: his lives inside
his 1,500-line heal-priority package (patch_heal_ai_tcpck_v1.py cave F) and uses its scoring; ours
scores a self-heal exactly as vanilla scores healing anyone else.

VANILLA
    TCAI's friendly-target loop (0x41917A..0x41920C) calls CheckUnit(target, self) for every own
    unit.  With target == self the path search returns -1, so a unit never proposes healing itself.
    Even a proposed self-heal would die in phase 5: the touch executor walks a path to the destination
    and touches at its end, and drops any one-node path unexecuted (0x41ACE4
    `cmp [path+8],1 / jle 0x41AE17`).

THE FIX
    A  proposal -- hook 0x419212 (8 B, `mov eax,[ebp-0x30] / call TObject.Free`, just after the
       friendly loop) -> cave_prop.  If the mover [ebp-0x28] has movement left and Healing (0x2F) in
       its friendly-ability list [ebp-0x38]:
         ability = AbilityControl.GetAbility(0x2F);  CanTouch (VMT+0x11C)(ability, self, self);
         valuation (VMT+0xEC)(ability, self, self, &rec)  -- rec.DV = our heal amount x 100
           (build_ai_healvalue's min(10, missing) at AoWEPACK 0x5576C074); DV <= 0 -> nothing;
         DEV = MultDEV(tcDVtoDEV(DV, 0, self, self), maxHP, curHP)      -- vanilla's heal line 0x416F4E
         value = MultDEV(DEV, pct, 1), pct = 50 hero/leader (build_ai_touch_herovalue.py) else 100
         [cai+0x2C] += 1;  CreateMove(type 1, self, self, 0, 0x2F, value, dest = own hex)
       then replays the Free and resumes at 0x41921A.
    B  executor -- hook 0x41ACE4 (10 B) -> cave_exec.  One-node path, ability 0x2F, destination = the
       unit's own hex, movement >= 1 -> AbRangedTC(hs, x, y) (0x423860; the engine's own
       touch-without-moving path, used by AbTouchMoveTC for a one-node friendly touch), result to
       [ebp-0x31], resume at the post-execution tail 0x41ADD0.  Longer paths -> vanilla 0x41ACEE;
       anything else -> vanilla drop 0x41AE17.

    Heroes are no longer gated out of the friendly loop (build_ai_hero_gate.py), and the proposal is
    not gated either.

Rolls: none here; the heal itself runs through the tactical TE on every client.  PIC: cave A reads
two import slots (AbilityControl 0x46E8D0, THero 0x46E914) through a call/pop delta; cave B has no
absolute references.  Slot 0x0043A500-0x0043A6FF, exclusive.  Surgical --undo.
"""
import os, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

SLOT = (0x0043A500, 0x0043A700)
CAVE_A = 0x0043A500
HOOK_A, VAN_A, RESUME_A = 0x00419212, bytes.fromhex("8b45d0e8367efeff"), 0x0041921A
HOOK_B, VAN_B = 0x0041ACE4, bytes.fromhex("837808010f8e29010000")
EXEC_GO, EXEC_DROP, EXEC_TAIL = 0x0041ACEE, 0x0041AE17, 0x0041ADD0
TOBJ_FREE, ISCLASS, GETABIL = 0x00401050, 0x00401058, 0x00402704
DV2DEV, MULTDEV, CREATEMOVE, ABRANGEDTC = 0x00413664, 0x00414418, 0x004135B8, 0x00423860
IAT_ABILCTL, IAT_THERO = 0x0046E8D0, 0x0046E914
HEALING = 0x2F
HERO_PCT = 0x32          # = the live byte at 0x4171F5 (build_ai_touch_herovalue.py)


def build_a(va):
    head = asm("pushad\nsub esp, 0x20", va)
    anchor = va + len(head) + 5
    call = asm(f"call {anchor:#x}", va + len(head))
    # [esp] rec (0x10) / [esp+0x10] ability / [esp+0x14] aux / [esp+0x18] value
    body = asm(f"""
        pop ebx
        sub ebx, {anchor:#x}
        mov esi, dword ptr [ebp - 0x28]
        test esi, esi
        je p_done
        cmp dword ptr [esi + 0x5c], 1
        jl p_done
        mov eax, dword ptr [ebp - 0x38]
        test eax, eax
        je p_done
        mov ecx, dword ptr [eax + 8]
        mov edx, dword ptr [eax + 4]
        xor edi, edi
    p_scan:
        cmp edi, ecx
        jge p_done
        mov eax, dword ptr [edx + edi*4]
        inc edi
        test eax, eax
        je p_scan
        cmp dword ptr [eax + 4], {HEALING:#x}
        jne p_scan
        mov dword ptr [esp + 0x14], 0
        mov eax, dword ptr [ebx + {IAT_ABILCTL:#x}]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax + 0x80]
        mov edx, {HEALING:#x}
        call {GETABIL:#x}
        test eax, eax
        je p_done
        mov dword ptr [esp + 0x10], eax
        mov edx, esi
        mov ecx, esi
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0x11c]
        test al, al
        je p_done
        xor eax, eax
        mov dword ptr [esp], eax
        mov dword ptr [esp + 4], eax
        mov dword ptr [esp + 8], eax
        mov dword ptr [esp + 0xc], eax
        push esp
        mov eax, dword ptr [esp + 0x14]
        mov edx, esi
        mov ecx, esi
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0xec]
        mov edx, dword ptr [esp]
        test edx, edx
        jle p_done
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x88]
        movsx eax, al
        test eax, eax
        jle p_done
        push eax
        push esi
        push esi
        mov edx, dword ptr [esp + 0xc]
        xor ecx, ecx
        mov eax, dword ptr [ebp - 4]
        call {DV2DEV:#x}
        mov edi, eax
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x84]
        movsx ecx, al
        mov edx, edi
        mov eax, dword ptr [ebp - 4]
        call {MULTDEV:#x}
        mov dword ptr [esp + 0x18], eax
        mov eax, dword ptr [esi + 0x4c]
        mov edx, dword ptr [ebx + {IAT_THERO:#x}]
        call {ISCLASS:#x}
        mov ecx, 0x64
        test al, al
        je p_pct
        mov ecx, {HERO_PCT:#x}
    p_pct:
        push 1
        mov edx, dword ptr [esp + 0x1c]
        mov eax, dword ptr [ebp - 4]
        call {MULTDEV:#x}
        mov dword ptr [esp + 0x18], eax
        mov eax, dword ptr [ebp - 4]
        inc dword ptr [eax + 0x2c]
        mov eax, dword ptr [esi + 0x60]
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        push dword ptr [esp + 0x1c]
        push {HEALING:#x}
        push dword ptr [esp + 0x20]
        push esi
        push esi
        mov eax, dword ptr [esi + 0x60]
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx ecx, al
        mov dl, 1
        mov eax, dword ptr [ebp - 4]
        call {CREATEMOVE:#x}
    p_done:
        add esp, 0x20
        popad
        mov eax, dword ptr [ebp - 0x30]
        call {TOBJ_FREE:#x}
        jmp {RESUME_A:#x}
    """, anchor)
    return head + call + body


def build_b(va):
    return asm(f"""
        cmp dword ptr [eax + 8], 1
        jg x_go
        jl x_drop
        mov edx, dword ptr [ebp - 0x20]
        movsx eax, word ptr [edx + 6]
        cmp eax, {HEALING:#x}
        jne x_drop
        mov ecx, dword ptr [edx + 0x14]
        mov ecx, dword ptr [ecx + 0x1c]
        cmp dword ptr [ecx + 0x5c], 1
        jl x_drop
        mov eax, dword ptr [edx + 0x14]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x74]
        movsx eax, al
        mov edx, dword ptr [ebp - 0x20]
        cmp ax, word ptr [edx + 0x1c]
        jne x_drop
        mov eax, dword ptr [edx + 0x14]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x78]
        movsx eax, al
        mov edx, dword ptr [ebp - 0x20]
        cmp ax, word ptr [edx + 0x1e]
        jne x_drop
        mov eax, dword ptr [edx + 0x14]
        mov cx, word ptr [edx + 0x1e]
        mov dx, word ptr [edx + 0x1c]
        call {ABRANGEDTC:#x}
        mov byte ptr [ebp - 0x31], al
        jmp {EXEC_TAIL:#x}
    x_go:
        jmp {EXEC_GO:#x}
    x_drop:
        jmp {EXEC_DROP:#x}
    """, va)


BLOB_A = build_a(CAVE_A)
CAVE_B = (CAVE_A + len(BLOB_A) + 0xF) & ~0xF
caves = [("cave_prop", CAVE_A, BLOB_A), ("cave_exec", CAVE_B, build_b(CAVE_B))]
hooks = [(HOOK_A, VAN_A, jmp_to(HOOK_A, CAVE_A, len(VAN_A))),
         (HOOK_B, VAN_B, jmp_to(HOOK_B, CAVE_B, len(VAN_B)))]
interior = [(HOOK_A, HOOK_A + len(VAN_A), 0x00419140, 0x00419260),
            (HOOK_B, HOOK_B + len(VAN_B), 0x0041ABD0, 0x0041AE20)]

if __name__ == "__main__":
    run("build_ai_selfheal", hooks, caves, SLOT, interior)
