#!/usr/bin/env python
r"""
build_command_resroll.py -- Seduce, Dominate and Charm roll the commander's Resistance against the
target's, in place of the flat touch attack of 10.  AoWEPACK.dpl.  Owner's ruling 2026-09-25
(idea C in Zig notes/02-abilities-modded.md, "full RES").

A command lands on two rolls, both in TTouchAbility.CombatTouchRole @0x557681B0:
    1. HitRole(commander ATK - target DEF)
    2. HitRole(GetTouchAttack(level) - target RES)        <- this term becomes commander RES
Live HitRole: chance = clamp(50 + 5 x diff, 10, 90) percent.  GetTouchAttack is 10 for all
three (TDominateAbility @0x55770664, TCharmAbility @0x55770798, TSeduceAbility @0x55770978).

Every reader of that term is one `call dword ptr [ecx+0x10C]` (6 bytes, -> call cave + nop):
    0x557681ED  CombatTouchRole              the real roll        caster = EDI (combat object)
    0x55768270  CombatTouchRoleProbability   battle AI / odds     caster = ESI (combat object)
    0x55768171  TouchRoleProbability         strategic estimate   caster = ESI (strategic unit)
    0x557680EE  TTouchAbility.GetCombatInfo  info card ATK        owner  = [esp+4] (strategic)
These are TTouchAbility base methods shared by every touch ability, so each cave acts only for
ability ids 0x1C Dominate, 0x1D Seduce, 0x94 Charm and otherwise tail-jumps to the original
GetTouchAttack.  Combat RES = combat object VMT +0x74; strategic RES = unit VMT +0xCC.

⚠ The hidden evil-Turn-Undead controller 0x88 (build_turnundead_evilcommand.py) relies on
GetTouchAttack returning -10 at 0x55768270 so the AI never queues it; it is not one of the three
ids and keeps that sentinel.  The combat log's roll-2 wrapper (build_touchlog_gate.py) records the
operands at the HitRole call, so its "ATK" figure becomes the commander's RES.

No draw added or moved (the rolls are the engine's own).  Slot 0x5584F200-0x5584F300, exclusive.
PIC: rel32 and register-indirect only.  Surgical --undo.

    python build_scripts/build_command_resroll.py            dry run + state
    python build_scripts/build_command_resroll.py --apply
    python build_scripts/build_command_resroll.py --undo
    python build_scripts/build_command_resroll.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True

from aowepack_patch import asm, run

SLOT = (0x5584F200, 0x5584F300)
IDS = (0x1C, 0x1D, 0x94)
VAN = bytes.fromhex("ff910c010000")                  # call dword ptr [ecx+0x10C]


def build(va, getter):
    """getter: asm that loads the caster into EAX and its RES method into EDX's vtable call."""
    checks = "".join(f"""
        cmp dword ptr [eax + 0xC], {i:#x}
        je  rr_yes""" for i in IDS)
    return asm(f"""
        {checks}
        jmp dword ptr [ecx + 0x10C]
    rr_yes:
        {getter}
    """, va)


SITES = [
    ("c_role", 0x557681ED, "mov eax, edi\n mov edx, dword ptr [eax]\n jmp dword ptr [edx + 0x74]"),
    ("c_rolep", 0x55768270, "mov eax, esi\n mov edx, dword ptr [eax]\n jmp dword ptr [edx + 0x74]"),
    ("c_trp", 0x55768171, "mov eax, esi\n mov edx, dword ptr [eax]\n jmp dword ptr [edx + 0xCC]"),
    ("c_info", 0x557680EE, "mov eax, dword ptr [esp + 4]\n test eax, eax\n je rr_orig\n"
                           " mov edx, dword ptr [eax]\n jmp dword ptr [edx + 0xCC]\n"
                           "rr_orig:\n mov eax, esi\n mov ecx, dword ptr [eax]\n"
                           " jmp dword ptr [ecx + 0x10C]"),
]


def layout():
    va, caves = SLOT[0], []
    for name, _site, getter in SITES:
        blob = build(va, getter)
        caves.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    assert va <= SLOT[1], "caves overflow the slot"
    return caves


caves = layout()
at = {n: v for n, v, _b in caves}
hooks = [(site, VAN, b"\xE8" + struct.pack("<i", at[name] - (site + 5)) + b"\x90")
         for name, site, _g in SITES]

if __name__ == "__main__":
    run("build_command_resroll", hooks, caves, SLOT, [])
