#!/usr/bin/env python
r"""
build_battlecast_unitspells.py -- our world-map unit spells become castable in battle, as every
vanilla unit enchantment but Cosmagic Scrying is (owner, 2026-10-25).  AoWTCPCK.dpl, data only.

THE BYTE
  AoWTC.SpellTypes[id] @0x004672F4 (05-spells-added.md, Embrittle) is the spell's tactical class;
  0 keeps it out of the combat spellbook.  Every vanilla unit enchantment is class 7 (single unit).
  The spells themselves already carry the combat flag ([spell+0xC] = 3 from TStoneSkin.Create /
  TDarkGift.Create / TEnchantWeapon.Create, which our instances keep), and a battle cast ends in
  the spell's own ExecuteSpell (TUnitSpell.ExecuteCA -> VMT +0xB4) on the units behind the combat
  units, whose first step is ValidTargetUnit (VMT +0x9C): every hook those spells have works in
  battle as on the map.  A refused target fizzles.
    79  Regeneration          (build_regen_spell.py)
    82  Enmity of Nine Hells  (build_demon_curse.py; its cave_info makes battle targeting take
                               enemies, byte 7 of TUnitSpell.GetCombatInfo = 2)
    84  Dwarven Satchels      (build_satchels.py; a TEnchantWeapon instance)
    88  Mistform              (build_airwater_ench.py; TWindWalking instances, as is 90)
    90  Static Shield
  build_spell_unit_target.py's UNIT_ONLY lists all five, so an empty hex refuses the cast.

THE AI: the tactical AI's spell loop (0x00418740) skips any spell whose combat info byte 7 lacks
  bit 2, i.e. every friendly unit spell (Regeneration, Satchels, Mistform, Static Shield); Enmity passes it and is then valued by
  tcGetDamageValueEx (VMT +0x8C), 0 for unit spells, so the AI casts none of them in battle.

Own-module DATA at a fixed base: no .reloc, no cave.  Surgical --undo.

    python build_scripts/build_battlecast_unitspells.py            dry run + state
    python build_scripts/build_battlecast_unitspells.py --apply
    python build_scripts/build_battlecast_unitspells.py --undo
"""
import os, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

SPELLTYPES = 0x004672F4
CLASS_UNIT = 7
SPELLS = (79, 82, 84, 88, 90)

HOOKS = [(SPELLTYPES + i, b"\x00", bytes([CLASS_UNIT])) for i in SPELLS]

if __name__ == "__main__":
    lo = SPELLTYPES + min(SPELLS)
    run("build_battlecast_unitspells", HOOKS, [], (lo, lo), [])
