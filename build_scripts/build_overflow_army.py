#!/usr/bin/env python
r"""
build_overflow_army.py -- units that join the winner during combat no longer form a second army on
the winner's hex when its stack is full; they go to the nearest hex that takes them.  AoWEPACK.dpl.

THE DEFECT (vanilla; confirmed by the owner 2026-10-21)
    TCombat.Finalize 0x55727E38 calls TCombatUnit.Finalize 0x55724D44 (slot +0xD0) on every combat
    object three times.  Passes 0 and 1 return each survivor to its own party (Place flags 2, one hex).
    A unit that changed sides -- Seduce, Charm, Dominate, our evil Turn Undead -- or has no strategic
    party is placed in pass 2, at the COMBAT TARGET hex ([[cu+8]+0xC] +8/+0xC/+0x10), by
        TAbstractUnit.Place 0x557810FC (eax unit, edx x, ecx y; push level, player, flags; ret 0xC)
    with flags 1 (spiral allowed): the first hex CanPlace accepts gets the unit -- joining an own
    TArmyHS there or a new one.  The defender is dead, so the joiners form a new army ON the target.
    TArmyCombatMoveTE.ExecuteCombat 0x55749924 then splits the moving units ([unit+0x25] & 4, the
    constant at 0x55749F60) off the attacker's army and PlacePrivate's them (0x55749E78 ->
    0x55791278, no merge check) onto the same hex.  When the movers cannot absorb the joiners, two
    armies share one hex.  Moving the winner's stack off the hex avoids it, but a unit without the
    movement points to leave is stuck, and the second stack is wiped out the next turn (owner).
    Found by Inioch (share9, patch_overflow_army_v1.py, overflow-army.md); every byte below
    re-read in our DLL.

THE PATCH
    The three pass-2 `call Place` sites are retargeted to cave_place (operand only, 4 bytes each):
        0x55724EA9   player type 2 branch (player argument 0)
        0x55724ED1   the side-switch case
        0x55724F0E   the no-party case
    All three enter with ESI = the TCombatUnit and the vanilla arguments.  cave_place calls vanilla
    Place unchanged unless ALL of these hold:
        flags bit 0 set (spiral), player != 0xFF;
        (x, y) is the combat target;
        the army on the attacker hex ([[cu+8]+0xC] +0x14/+0x18/+0x1C, in map bounds) belongs to that
          player and holds at least one moving unit;
        the target hex holds no other player's army;
        moving units + the player's units already on the target + 1  >  TArmy.MaxSize 0x5578DEF4
          (of the attacker's army).
    Then it walks the engine's own hex spiral from ring 1 (HSEngine.InitHNWalk radius 1,
    WalkToNextHN; walk ring +0xC, x +0x10, y +0x14) and calls Place with flags & ~1 -- one hex,
    the same CanPlace rules -- on each hex until one succeeds, up to ring 30 as vanilla.  If none
    does, vanilla Place (the old behaviour).  A second joiner finds the first one's army on the
    adjacent hex and joins it.  When everything fits, nothing changes: the joiners stay on the
    target and merge as before.

    The map is [AoWHSMap 0x558FA040]; [map+0x10] = the TMapContainer (+0xC width, +0x10 height),
    reached through a call/pop delta.  GetField 0x557020FC, FindOwnedChild (field VMT +0x80, tag
    0x20217 TArmyHS), TUnitList.GetUnit 0x5578309C and Count (VMT +0x54).

Slot 0x558B3A00-0x558B3BFF, exclusive.  PIC: rel32 calls and one call/pop delta.  The retargeted
calls carry no .reloc (rel32).

RNG: none.  Placement depends on map state and the walk order only, identically on every peer.

Couplings: build_command_bond.py calls Place from its own cave; nothing else hooks these sites.

Unproven, static checks cannot reach it: the converts appearing on the adjacent hex in game.

    python build_scripts/build_overflow_army.py            dry run + state
    python build_scripts/build_overflow_army.py --apply
    python build_scripts/build_overflow_army.py --undo     surgical: the three calls back to Place
    python build_scripts/build_overflow_army.py --dis
"""
import struct
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, run

SLOT = (0x558B3A00, 0x558B3C00)
SITES = (0x55724EA9, 0x55724ED1, 0x55724F0E)          # pass-2 `call Place` in TCombatUnit.Finalize
FINALIZE = (0x55724D44, 0x55724F18)                   # TCombatUnit.Finalize, for the interior check
PLACE = 0x557810FC
GETFIELD = 0x557020FC                                 # thunk -> HSEngine.TMapContainer.GetField
GETUNIT, MAXSIZE = 0x5578309C, 0x5578DEF4
INITWALK, WALKNEXT = 0x557026D4, 0x557026DC           # thunks -> HSEngine.InitHNWalk / WalkToNextHN
G_MAP = 0x558FA040                                    # AoWE.AoWHSMap
ARMYHS = 0x20217
CAVE = SLOT[0]

SRC = f"""
    push ebp
    mov  ebp, esp
    sub  esp, 0x40
    push ebx
    push esi
    push edi
    mov  [ebp-4], eax
    mov  [ebp-8], edx
    mov  [ebp-0xc], ecx
    call L0
L0:
    pop  ebx
    sub  ebx, L0
    test byte ptr [ebp+8], 1
    jz   vanilla
    movzx eax, byte ptr [ebp+0xc]
    cmp  al, 0xff
    je   vanilla
    mov  [ebp-0x10], eax
    mov  eax, [esi+8]
    test eax, eax
    jz   vanilla
    mov  edi, [eax+0xc]
    test edi, edi
    jz   vanilla
    mov  eax, [ebp-8]
    cmp  eax, [edi+8]
    jne  vanilla
    mov  eax, [ebp-0xc]
    cmp  eax, [edi+0xc]
    jne  vanilla
    mov  edx, [edi+0x14]
    mov  ecx, [edi+0x18]
    test edx, edx
    jl   vanilla
    test ecx, ecx
    jl   vanilla
    mov  eax, [ebx+{G_MAP:#x}]
    mov  eax, [eax+0x10]
    cmp  edx, [eax+0xc]
    jge  vanilla
    cmp  ecx, [eax+0x10]
    jge  vanilla
    push dword ptr [edi+0x1c]
    call {GETFIELD:#x}
    test eax, eax
    jz   vanilla
    mov  edx, {ARMYHS:#x}
    mov  ecx, [eax]
    call dword ptr [ecx+0x80]
    test eax, eax
    jz   vanilla
    mov  eax, [eax+0x1c]
    test eax, eax
    jz   vanilla
    mov  [ebp-0x14], eax
    mov  dl, [eax+0x12]
    cmp  dl, byte ptr [ebp-0x10]
    jne  vanilla
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  [ebp-0x18], eax
    xor  esi, esi
    mov  dword ptr [ebp-0x20], 0
cnt:
    cmp  esi, [ebp-0x18]
    jge  cntdone
    mov  eax, [ebp-0x14]
    mov  edx, esi
    call {GETUNIT:#x}
    test eax, eax
    jz   cntnext
    test byte ptr [eax+0x25], 4
    jz   cntnext
    inc  dword ptr [ebp-0x20]
cntnext:
    inc  esi
    jmp  cnt
cntdone:
    cmp  dword ptr [ebp-0x20], 0
    je   vanilla
    mov  edx, [edi+8]
    mov  ecx, [edi+0xc]
    push dword ptr [edi+0x10]
    mov  eax, [ebx+{G_MAP:#x}]
    mov  eax, [eax+0x10]
    call {GETFIELD:#x}
    test eax, eax
    jz   vanilla
    mov  edx, {ARMYHS:#x}
    mov  ecx, [eax]
    call dword ptr [ecx+0x80]
    xor  esi, esi
    test eax, eax
    jz   havec2
    mov  eax, [eax+0x1c]
    test eax, eax
    jz   havec2
    mov  dl, [eax+0x12]
    cmp  dl, byte ptr [ebp-0x10]
    jne  vanilla
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  esi, eax
havec2:
    add  esi, [ebp-0x20]
    inc  esi
    mov  eax, [ebp-0x14]
    call {MAXSIZE:#x}
    cmp  esi, eax
    jle  vanilla
    push 1
    lea  eax, [ebp-0x40]
    mov  edx, [ebp-8]
    mov  ecx, [ebp-0xc]
    call {INITWALK:#x}
walk:
    cmp  dword ptr [ebp-0x34], 0x1e
    jge  vanilla
    push dword ptr [ebp+0x10]
    push dword ptr [ebp+0xc]
    movzx eax, byte ptr [ebp+8]
    and  al, 0xfe
    push eax
    mov  eax, [ebp-4]
    mov  edx, [ebp-0x30]
    mov  ecx, [ebp-0x2c]
    call {PLACE:#x}
    test eax, eax
    jnz  done
    lea  eax, [ebp-0x40]
    call {WALKNEXT:#x}
    jmp  walk
vanilla:
    push dword ptr [ebp+0x10]
    push dword ptr [ebp+0xc]
    push dword ptr [ebp+8]
    mov  eax, [ebp-4]
    mov  edx, [ebp-8]
    mov  ecx, [ebp-0xc]
    call {PLACE:#x}
done:
    pop  edi
    pop  esi
    pop  ebx
    mov  esp, ebp
    pop  ebp
    ret  0xc
"""


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


blob = asm(SRC, CAVE)
caves = [("cave_place", CAVE, blob)]
hooks = [(s, call_to(s, PLACE), call_to(s, CAVE)) for s in SITES]
interior = [(s, s + 5, FINALIZE[0], FINALIZE[1]) for s in SITES]

if __name__ == "__main__":
    run("build_overflow_army", hooks, caves, SLOT, interior)
