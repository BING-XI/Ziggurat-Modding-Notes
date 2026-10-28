#!/usr/bin/env python
r"""
build_blazing_moon_pfs.py -- the data half of Blazing Moon (build_blazing_moon.py): Spells.pfs record
105 (spell 95).

    python build_scripts/build_blazing_moon_pfs.py            dry run + state
    python build_scripts/build_blazing_moon_pfs.py --apply     write the record
    python build_scripts/build_blazing_moon_pfs.py --undo      remove it

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELL RECORD 105 = Astral Ward's record 75 (same class, TSpellWard: its cast effect and sound) with
  the description, mana 80, upkeep 20, research 240 (the single tier-4 figure: it prices Wizard's
  Tower offers), sphere 7 (dual), tier 3, caster family 4 (Ritualist) and book icon 172 (a full moon
  ringed by sun rays on the Air/Fire glow, build_dual_spell_icons.py; the owner's pick).
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

SPELL_REC, SPELL_DONOR = 95 + 10, 65 + 10
ICON = 172
MANA, UPKEEP, RESEARCH, SPHERE, TIER, FAMILY = 80, 20, 240, 7, 3, 4
TAG_UPKEEP = 0x0E
SPELL_DESC = ("Each turn, land on the surface and in the sky may dry a step toward desert, and ice may "
              "thaw. Every female unit gains +4 Damage.")


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


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    label, path, rec, donor = "Spells.pfs record %d" % SPELL_REC, E.SPELLS, SPELL_REC, SPELL_DONOR
    d = E.read(path)
    if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
        sys.exit("ABORT: %s CRC residue already wrong" % label)
    base, _ent, _ws, span = E.records(d)
    want = build_spell_body(E.body_of(d, base, span, donor))
    present = rec in span
    match = present and E.body_of(d, base, span, rec) == want
    print("  %s: %s" % (label, "present, matches" if match else "PRESENT, differs" if present else "absent"))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply to write, --undo to remove)")
        return
    if (apply_ and match) or (undo and not present):
        return
    out = bytearray(d)
    if present:
        out = E.remove(out, rec)
    if apply_:
        out = E.insert(out, rec, donor, build_spell_body)[0]
    E.fix_crc(out)
    problem = E.audit(d, out, rec, expect_present=apply_)
    if problem:
        sys.exit("ABORT: %s audit failed -- %s (nothing written)" % (label, problem))
    kill_aow()
    open(path, "wb").write(out)
    print("    %s (%d -> %d B, CRC repaired)" % ("WRITTEN" if apply_ else "REMOVED", len(d), len(out)))


if __name__ == "__main__":
    main()
