#!/usr/bin/env python
r"""
build_blessing_stygia_pfs.py -- the data half of Blessing of Stygia (build_blessing_stygia.py):
Spells.pfs record 97 (spell 87) and Ability.pfs record 91 (the status 0x51).

    python build_scripts/build_blessing_stygia_pfs.py            dry run + state
    python build_scripts/build_blessing_stygia_pfs.py --apply     write both records
    python build_scripts/build_blessing_stygia_pfs.py --undo      remove them

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELL RECORD 97 = Astral Ward's record 75 (same class, TSpellWard: its cast effect and sound) with
  the description, mana 30, upkeep 5, research 160 (the single tier-3 figure: it prices Wizard's
  Tower offers), sphere 7 (dual), tier 2, caster family 4 (Ritualist) and book icon 163 (a goblet
  over waves on the Death/Water glow, build_dual_spell_icons.py; the owner's pick).
ABILITY RECORD 91 (Blessing of Stygia) = Nature's Blessing's record 109 (a day status: its empty
  sound and image lists, tag 9 = 00 00) with a new description.
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

SPELL_REC, SPELL_DONOR = 87 + 10, 65 + 10
STATUS_REC, STATUS_DONOR = 0x51 + 10, 0x63 + 10
ICON = 163
MANA, UPKEEP, RESEARCH, SPHERE, TIER, FAMILY = 30, 5, 160, 7, 2, 4
TAG_UPKEEP = 0x0E
SPELL_DESC = "Units which begin their turn next to or atop water gain Physical Protection for 1 turn."
STATUS_DESC = ("Blessing of Stygia: Physical Protection until the start of its next turn, renewed "
               "while the unit starts its turns on or beside water.")


def build_spell_body(donor):
    f = DF.fields(donor)
    assert f.get(E.TAG_DESC, b"")[4:].startswith(b"Wards the paths of the arcane"), "donor is not Astral Ward's record"
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


def build_status_body(donor):
    f = DF.fields(donor)
    assert f.get(E.ABIL_TAG_DESC, b"")[4:].startswith(b"Increases the unit's Defense"), "donor is not Nature's Blessing's record"
    assert f.get(9) == b"\x00\x00"
    f[E.ABIL_TAG_DESC] = E.pstr32(STATUS_DESC)
    return E.reserialise(f)


TARGETS = [
    ("Spells.pfs  record %d" % SPELL_REC, E.SPELLS, SPELL_REC, SPELL_DONOR, build_spell_body),
    ("Ability.pfs record %d" % STATUS_REC, E.ABILS, STATUS_REC, STATUS_DONOR, build_status_body),
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
