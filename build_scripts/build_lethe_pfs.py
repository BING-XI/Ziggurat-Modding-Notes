#!/usr/bin/env python
r"""
build_lethe_pfs.py -- the data half of Curse of Lethe (build_lethe.py, build_lethe_tc.py):
Spells.pfs record 96 (spell 86) and Ability.pfs record 90 (Asleep, 0x50).

    python build_scripts/build_lethe_pfs.py            dry run + state
    python build_scripts/build_lethe_pfs.py --apply     write both records
    python build_scripts/build_lethe_pfs.py --undo      remove them

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELL RECORD 96 = Geyser's record 128 (class 0x1E, the burst Curse of Lethe draws, and its sounds)
  with the description, mana 12, upkeep 0, research 80 (the single tier-2 figure: it prices
  Wizard's Tower offers), sphere 7 (dual), tier 1, caster family 1 (Evoker) and book icon 162 (a
  crescent moon over waves on the Death/Water glow, build_dual_spell_icons.py; the owner's pick).
ABILITY RECORD 90 (Asleep) = Stunned's record 102 (tag 7 its sounds, tag 8 its dazed-stars frames,
  which the unit panel, auto-resolve and the battlefield list draw for Asleep) with a new
  description and tag 9 = 00 00 (a status, offered nowhere).  ⚠ build_ankh_battlefield.py may name
  0x50 only while this record carries tag 8: the battlefield draw reads its images unchecked.
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

SPELL_REC, SPELL_DONOR = 86 + 10, 118 + 10
ASLEEP_REC, ASLEEP_DONOR = 0x50 + 10, 0x5C + 10
ICON = 162
MANA, UPKEEP, RESEARCH, SPHERE, TIER, FAMILY = 12, 0, 80, 7, 1, 1
WATER = 6
TAG_UPKEEP = 0x0E
SPELL_DESC = "Puts units to sleep in an area. Damage will wake them."
ASLEEP_DESC = ("Asleep: the unit cannot act or retaliate and its Defense is 4 lower. It wakes after "
               "four of its own turns, or as soon as it takes damage.")


def build_spell_body(donor):
    f = DF.fields(donor)
    assert f.get(E.TAG_SPHERE) == bytes([WATER]), "donor is not Geyser's record (sphere %r)" % f.get(E.TAG_SPHERE)
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


def build_asleep_body(donor):
    f = DF.fields(donor)
    assert f.get(9) == b"\x7e\x00" and len(f.get(8, b"")) > 4, "donor is not Stunned's record"
    f[E.ABIL_TAG_DESC] = E.pstr32(ASLEEP_DESC)
    f[9] = b"\x00\x00"
    return E.reserialise(f)


TARGETS = [
    ("Spells.pfs  record %d" % SPELL_REC, E.SPELLS, SPELL_REC, SPELL_DONOR, build_spell_body),
    ("Ability.pfs record %d" % ASLEEP_REC, E.ABILS, ASLEEP_REC, ASLEEP_DONOR, build_asleep_body),
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
