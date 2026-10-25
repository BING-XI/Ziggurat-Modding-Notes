#!/usr/bin/env python3
r"""
build_demon_curse_pfs.py -- the data half of Enmity of Nine Hells (build_demon_curse.py): Spells.pfs record
92 (spell 82) and Ability.pfs record 101 (its enchantment, ability 0x5B).

    python build_scripts/build_demon_curse_pfs.py            dry run + state
    python build_scripts/build_demon_curse_pfs.py --apply     write both records
    python build_scripts/build_demon_curse_pfs.py --undo      remove both

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELL RECORD 92 = Dark Gift's record 87 (same class, TDarkGift: its cast animation and sounds) with
  the description, mana 40, upkeep 10, research 240 (the single tier-4 figure: it prices Wizard's
  Tower offers), sphere 7 (dual), tier 3, caster family 3 (Enchanter) and the book icon 158
  (build_dual_spell_icons.py).
ABILITY RECORD 101 = Dark Gift's enchantment record 179 (tag 9 = 00 00: never offered) with only the
  description.
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

SPELL_REC, SPELL_DONOR = 82 + 10, 77 + 10
ABIL_REC, ABIL_DONOR = 0x5B + 10, 0xA9 + 10
ICON = 158
MANA, UPKEEP, RESEARCH, SPHERE, TIER, FAMILY = 40, 10, 240, 7, 3, 3
TAG_UPKEEP = 0x0E
SPELL_DESC = ("Curses an enemy unit. Sooner or later demons manifest to hunt it down, striking it "
              "with +5 attack and damage.")
ABIL_DESC = "Demons hunt this unit and strike it with +5 attack and damage."


def build_spell_body(donor):
    f = DF.fields(donor)
    assert f.get(E.TAG_SPHERE) == b"\x02", "donor is not Dark Gift's record (sphere %r)" % f.get(E.TAG_SPHERE)
    f[E.TAG_DESC] = E.pstr32(SPELL_DESC)
    f[E.TAG_MANA] = struct.pack("<I", MANA)
    f[TAG_UPKEEP] = struct.pack("<I", UPKEEP)
    f[E.TAG_RESEARCH] = struct.pack("<I", RESEARCH)
    f[E.TAG_SPHERE] = bytes([SPHERE])
    f[E.TAG_TIER] = bytes([TIER])
    f[DF.TAG_FAMILY] = bytes([FAMILY])
    slots = DF.seq_parse(f[DF.TAG_IMG])
    icon = slots[10]
    assert icon is not None and icon["name"] == E.ICON_PATH and icon["kind"] == 0, "slot 10 is not the icon"
    icon["f20"] = ICON
    f[DF.TAG_IMG] = DF.seq_build(slots)
    assert DF.seq_parse(f[DF.TAG_IMG]) == slots
    return E.reserialise(f)


def build_abil_body(donor):
    f = DF.fields(donor)
    assert f.get(9) == b"\x00\x00", "donor's tag 9 is %r, expected 00 00 -- wrong donor" % f.get(9)
    f[E.ABIL_TAG_DESC] = E.pstr32(ABIL_DESC)
    return E.reserialise(f)


TARGETS = [
    ("Spells.pfs  record %d" % SPELL_REC, E.SPELLS, SPELL_REC, SPELL_DONOR, build_spell_body),
    ("Ability.pfs record %d" % ABIL_REC, E.ABILS, ABIL_REC, ABIL_DONOR, build_abil_body),
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
