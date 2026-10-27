#!/usr/bin/env python
r"""
build_satchels_pfs.py -- the data half of Dwarven Satchels (build_satchels.py): Spells.pfs record 94
(spell 84) and Ability.pfs records 88 (the enchantment 0x4E) and 89 (the attack 0x4F).

    python build_scripts/build_satchels_pfs.py            dry run + state
    python build_scripts/build_satchels_pfs.py --apply     write the three records
    python build_scripts/build_satchels_pfs.py --undo      remove them

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELL RECORD 94 = Enchant Weapon's record 26 (same class, TEnchantWeapon: its cast effect and sound)
  with the owner's description, mana 16, upkeep 0, research 80 (the single tier-2 figure: it prices
  Wizard's Tower offers), sphere 7 (dual), tier 1, caster family 3 (Enchanter).  Book icon 160:
  the satchel glyph on the Earth/Fire glow (build_dual_spell_icons.py; the owner's pick).
ABILITY RECORD 88 (E, "Dwarven Satchels") = Enchant Weapon's enchantment record 164 (tag 9 = 00 00:
  never offered, a status) with a new description.  Both ability texts call the flask "unwieldy" and
  give its damage (owner 2026-10-25): with the aiming numbers, that is how the scatter is told.
ABILITY RECORD 89 (F, "Throw Explosive Flask") = Hurl Flaming Skull's record 201 (41 image slots:
  slot 0 the flight sprite, slot 40 the auto-combat picture; Hurl Boulder's catapult sounds) with a
  new description, tag 9 = 00 00 (never offered: it comes only from E), and from Hurl Boulder's
  record 34: slot 0 (its tumbling boulder, TCOMBAT\OBJECTS\BALLS.ILB frames 7-14) and slot 40
  (Combat.ILB 110), so the flask looks like a boulder (owner 2026-10-25; Fire Cannon's ball,
  Combat.ILB 112, read as a cannonball).  The impact sound, the second sound entry, is
  SFX\ZATK\FLASKBURST.WAV (build_flask_sound.py: a shatter over a quieter explosion), a path as
  long as the A_PUNCH2.WAV it replaces.
"""
import importlib.util, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, alias):
    spec = importlib.util.spec_from_file_location(alias, os.path.join(HERE, name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = _load("build_embrittle_pfs.py", "_emb")
DF = _load("build_deathfire_pfs.py", "_df")
from aowepack_patch import kill_aow                          # noqa: E402

SPELL_REC, SPELL_DONOR = 84 + 10, 16 + 10
ENCH_REC, ENCH_DONOR = 0x4E + 10, 0x9A + 10
FLASK_REC, FLASK_DONOR = 0x4F + 10, 0xBF + 10
ICON = 160
MANA, UPKEEP, RESEARCH, SPHERE, TIER, FAMILY = 16, 0, 80, 7, 1, 3
TAG_UPKEEP = 0x0E
SKULL_IMAGE = 0x74
BOULDER_REC, BOULDER_SPRITE = 0x18 + 10, b"TCOMBAT\\OBJECTS\\BALLS.ILB"
IMPACT_OLD = b"\x17SFX\\ATTACK\\A_PUNCH2.WAV"    # same length: the sound entry keeps its size
IMPACT_NEW = b"\x17SFX\\ZATK\\FLASKBURST.WAV"   # build_flask_sound.py
SPELL_DESC = "Gives a unit one expendable alchemical flask which can be thrown in battle."
ENCH_DESC = ("Carries one unwieldy alchemical flask (10/15 fire) to throw in battle. Throwing it uses "
             "the satchel up.")
FLASK_DESC = ("Lobs an unwieldy alchemical flask (10/15 fire) up to 4 hexes. It bursts on every unit "
              "within one hex of where it lands. One throw.")


def build_spell_body(donor):
    f = DF.fields(donor)
    assert f.get(E.TAG_DESC, b"")[4:].startswith(b"A powerful enchantment"), "donor is not Enchant Weapon's record"
    f[E.TAG_DESC] = E.pstr32(SPELL_DESC)
    f[E.TAG_MANA] = struct.pack("<I", MANA)
    f[TAG_UPKEEP] = struct.pack("<I", UPKEEP)
    f[E.TAG_RESEARCH] = struct.pack("<I", RESEARCH)
    f[E.TAG_SPHERE] = bytes([SPHERE])
    f[E.TAG_TIER] = bytes([TIER])
    f[DF.TAG_FAMILY] = bytes([FAMILY])
    if ICON is not None:
        slots = DF.seq_parse(f[DF.TAG_IMG])
        icon = slots[10]
        assert icon is not None and icon["name"] == E.ICON_PATH and icon["kind"] == 0, "slot 10 is not the icon"
        icon["f20"] = ICON
        f[DF.TAG_IMG] = DF.seq_build(slots)
        assert DF.seq_parse(f[DF.TAG_IMG]) == slots
    return E.reserialise(f)


def build_ench_body(donor):
    f = DF.fields(donor)
    assert f.get(9) == b"\x00\x00", "donor's tag 9 is %r, expected 00 00 -- wrong donor" % f.get(9)
    f[E.ABIL_TAG_DESC] = E.pstr32(ENCH_DESC)
    return E.reserialise(f)


def boulder_slots():
    """Hurl Boulder's image slots, from the live Ability.pfs."""
    d = E.read(E.ABILS)
    base, _ent, _ws, span = E.records(d)
    return DF.seq_parse(DF.fields(E.body_of(d, base, span, BOULDER_REC))[8])


def build_flask_body(donor):
    f = DF.fields(donor)
    slots, hb = DF.seq_parse(f[8]), boulder_slots()
    for k in (0, 40):
        assert slots[k] is not None and slots[k]["name"] == b"COMBAT.ILB" and slots[k]["f20"] == SKULL_IMAGE,             "donor's slot %d is not the skull" % k
    assert hb[0] is not None and hb[0]["name"] == BOULDER_SPRITE, "Hurl Boulder's slot 0 is not its boulder"
    assert hb[40] is not None and hb[40]["name"] == b"COMBAT.ILB", "Hurl Boulder's slot 40 is not its picture"
    slots[0], slots[40] = hb[0], hb[40]
    f[8] = DF.seq_build(slots)
    assert DF.seq_parse(f[8]) == slots
    assert f[7].count(IMPACT_OLD) == 1, "donor's impact sound is not A_PUNCH2"
    f[7] = f[7].replace(IMPACT_OLD, IMPACT_NEW)
    f[E.ABIL_TAG_DESC] = E.pstr32(FLASK_DESC)
    f[9] = b"\x00\x00"
    return E.reserialise(f)


TARGETS = [
    ("Spells.pfs  record %d" % SPELL_REC, E.SPELLS, SPELL_REC, SPELL_DONOR, build_spell_body),
    ("Ability.pfs record %d" % ENCH_REC, E.ABILS, ENCH_REC, ENCH_DONOR, build_ench_body),
    ("Ability.pfs record %d" % FLASK_REC, E.ABILS, FLASK_REC, FLASK_DONOR, build_flask_body),
]


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    for label, path, rec, donor, builder in TARGETS:
        d = E.read(path)
        if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
            sys.exit("ABORT: %s CRC residue already wrong" % label)
        base, _ent, _ws, span = E.records(d)
        want = builder(E.body_of(d, base, span, donor))
        present = rec in span
        match = present and E.body_of(d, base, span, rec) == want
        print("  %s: %s" % (label, "present, matches" if match else "PRESENT, differs" if present else "absent"))
        if not (apply_ or undo) or (apply_ and match) or (undo and not present):
            continue
        out = bytearray(d)
        if present:
            out = E.remove(out, rec)
        if apply_:
            out = E.insert(out, rec, donor, builder)[0]
        E.fix_crc(out)
        problem = E.audit(d, out, rec, expect_present=apply_)
        if problem:
            sys.exit("ABORT: %s audit failed -- %s (nothing written)" % (label, problem))
        kill_aow()
        open(path, "wb").write(out)
        print("    %s (%d -> %d B, CRC repaired)" % ("WRITTEN" if apply_ else "REMOVED", len(d), len(out)))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply to write, --undo to remove)")


if __name__ == "__main__":
    main()
