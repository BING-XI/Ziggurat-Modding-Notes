#!/usr/bin/env python
r"""
build_ooze_extinguish.py -- Ooze puts out fires (burning ground and burning wooden walls) and
removes Burning from the unit on each hex its mud lands on.  AoWTCPCK.dpl.

From Inioch's share8 patch_ooze_extinguish_v1.py (idea + RE: ooze-extinguish-idea.md).  Ours hooks
10 bytes later, so no .reloc entry has to be neutralised.

VANILLA
    Ooze (spell 0x7C) fires 19 strikes (a radius-2 blob).  For each landed strike
    TCAbRangedTE.Execute's per-effect loop fetches the hex's field -- GetField(GetMapLevel(container,
    0), x=[ebp-0x28], y=[ebp-0x2C]) -- and, if the terrain allows, places a mud decal.  The first
    terrain test is 0x40C93E `cmp byte [eax+0x14],0 / je 0x40CAF2` with EAX = the field.

THE FIX
    Hook those 10 bytes (0x40C93E, relocation-free) -> cave_ooze.  Before the terrain checks, so wall
    and water hexes count too:
      * fire: while field.FindOwnedChild(ClassID 0x22054A, TCombatFire) (field VMT +0x80) ->
        TObject.Free (thunk 0x401050), at most 8 times.  A burning wooden wall IS a fire object on
        the wall's hex (TCityWall has no burn flag; the fire's per-turn message damages it), so it is
        put out too.  Same idiom as TCombatFire.NewTurn.
      * unit: FindOwnedChild(0x220104, TTacticalCombatUnitHS) -> [hs+0x1C] TTacticalCombatUnit; if its
        GetAbilityEnabled(0x7F Burning) (VMT +0xA8), AoWE.TAbstractUnit.RemoveAbility([cu+0x4C], 0x7F).
        RemoveAbility is reached through TCPCK's import slot of TCombatUnit.SetUnit (0x46E858) plus
        the fixed distance 0x5577F6EC - 0x55725194 (AoWEPACK rebases).
    then replays the test and resumes at 0x40C948, or takes vanilla's je.
    PIC: TCPCK rebases, so the import slot is read through a call/pop delta.

MULTIPLAYER / REPLAYS
    It runs inside the tactical TE, which executes on every client in the same order.  Auto-resolve
    (fast combat) gives Ooze no strikes, as vanilla, so nothing happens there.  No random draws.

Slot 0x0043A400-0x0043A4FF, exclusive (above build_group_move_tc.py's zone).  Surgical --undo.
"""
import os, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

SLOT = (0x0043A400, 0x0043A500)
CAVE = 0x0043A400
HOOK, RESUME, SKIP = 0x0040C93E, 0x0040C948, 0x0040CAF2
VAN = bytes.fromhex("807814000f84aa010000")     # cmp byte [eax+0x14],0 / je 0x40CAF2
TOBJ_FREE = 0x00401050
SLOT_SETUNIT = 0x0046E858
EP_SETUNIT, EP_REMOVEABILITY = 0x55725194, 0x5577F6EC
CID_FIRE, CID_UNITHS, AB_BURNING = 0x22054A, 0x220104, 0x7F


def build(va):
    head = asm("pushad\nmov esi, eax", va)
    anchor = va + len(head) + 5
    call = asm(f"call {anchor:#x}", va + len(head))
    body = asm(f"""
        pop ebx
        sub ebx, {anchor:#x}
        mov edi, 8
    o_fire:
        mov eax, esi
        mov edx, {CID_FIRE:#x}
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je o_unit
        call {TOBJ_FREE:#x}
        dec edi
        jne o_fire
    o_unit:
        mov eax, esi
        mov edx, {CID_UNITHS:#x}
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je o_done
        mov eax, dword ptr [eax + 0x1c]
        test eax, eax
        je o_done
        mov esi, eax
        mov edx, {AB_BURNING:#x}
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je o_done
        mov eax, dword ptr [esi + 0x4c]
        test eax, eax
        je o_done
        mov edx, {AB_BURNING:#x}
        mov ecx, dword ptr [ebx + {SLOT_SETUNIT:#x}]
        add ecx, {EP_REMOVEABILITY - EP_SETUNIT:#x}
        call ecx
    o_done:
        popad
        cmp byte ptr [eax + 0x14], 0
        je {SKIP:#x}
        jmp {RESUME:#x}
    """, anchor)
    return head + call + body


caves = [("cave_ooze", CAVE, build(CAVE))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), 0x0040C900, 0x0040C980)]

if __name__ == "__main__":
    run("build_ooze_extinguish", hooks, caves, SLOT, interior)
