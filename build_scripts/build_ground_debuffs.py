#!/usr/bin/env python
r"""
build_ground_debuffs.py -- Holy Ground inflicts Vertigo and Unholy Ground inflicts Cursed on the
units they burn.  AoWEPACK.dpl.  From Inioch's share8 patch_storm_debuff_sources_v1.py, sites B/C
(site A, Divine Storm -> Vertigo, we already have).

VANILLA
    THolyGround.TriggerArmyDamage 0x557C7E18 / TUnHolyGround.TriggerArmyDamage 0x557C8FA4: per unit
    (EBX) an alignment gate, ExecuteDamageRole (holy / death damage), then on damage > 0
    SetHitPoints via `call [ecx+0E4h]` at 0x557C7F9E / 0x557C910B.  No status effect at all.

THE FIX
    Each 6-byte `call [ecx+0E4h]` -> jmp cave + nop.  The cave replays SetHitPoints, then does what
    vanilla's own TPoisonPlant.TriggerArmyDamage does (0x557C41BB): if the unit is still alive
    (GetHitPoints, VMT +0xE0), `ExecuteDamageEffects(unit, dx=mask)` with 0x40 Vertigo (Holy) or 0x20
    Cursed (Unholy), then resumes at 0x557C7FA4 / 0x557C9111 (EAX/ECX/EDX are reloaded there).
    ExecuteDamageEffects is hooked by build_stormeffectroll.py: the effect is ROLLED against the
    unit's Resistance (and its protections/immunities, machines exempt from Vertigo) -- it does not
    land automatically.  It fires wherever the ground burns: on arrival and every turn.

RNG: the rolls are raw draws after each trigger's own entry re-anchor (RandSeed := synced Random,
0x557C7E4E / 0x557C8FDA), the same bridge Poison Plants and the storms use; every peer adds the same
draws in the same order.

Slot 0x5584D400-0x5584D47F, exclusive.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D400, 0x5584D400 + 0x80)
EFFECTS = 0x55781E28                    # TAbstractUnit.ExecuteDamageEffects (rolled by stormeffectroll)
VAN = bytes.fromhex("ff91e4000000")     # call [ecx+0xE4]  SetHitPoints
SITES = [("cave_holy", 0x557C7F9E, 0x557C7FA4, 0x40, 0x5584D400, 0x557C7E18),
         ("cave_unholy", 0x557C910B, 0x557C9111, 0x20, 0x5584D440, 0x557C8FA4)]


def cave(va, mask, resume):
    return asm(f"""
        call dword ptr [ecx + 0xe4]
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        test al, al
        je g_done
        mov dx, {mask:#x}
        mov eax, ebx
        call {EFFECTS:#x}
    g_done:
        jmp {resume:#x}
    """, va)


caves = [(n, cva, cave(cva, mask, res)) for n, hook, res, mask, cva, _fn in SITES]
hooks = [(hook, VAN, jmp_to(hook, cva, len(VAN))) for _n, hook, _r, _m, cva, _fn in SITES]
interior = [(hook, hook + len(VAN), fn, hook + 0x40) for _n, hook, _r, _m, _c, fn in SITES]

if __name__ == "__main__":
    run("build_ground_debuffs", hooks, caves, SLOT, interior)
