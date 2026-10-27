#!/usr/bin/env python
r"""
build_awaken_volcano_pfs.py -- the data half of Awaken Volcano (build_awaken_volcano.py): Spells.pfs
record 95 (spell 85).

    python build_scripts/build_awaken_volcano_pfs.py            dry run + state
    python build_scripts/build_awaken_volcano_pfs.py --apply     write the record
    python build_scripts/build_awaken_volcano_pfs.py --undo      remove it

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELL RECORD 95 = Level Terrain's record 28 (same class, TLevelTerrain: its cast effect) with the
  owner's description, mana 40, upkeep 5, research 240 (the single tier-4 figure: it prices Wizard's
  Tower offers), sphere 7 (dual), tier 3, caster family 4 (Ritualist) and Surtr's Chasm's sound list
  (Tremors' list with SFX\ZSP\SURTRQK.WAV, build_chasm_sound.py), and the book icon 161 (draft A:
  a cone with a glowing crater, one lava stream and embers; build_dual_spell_icons.py).  ICON = None
  would keep Level Terrain's icon.
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
CH = _load("build_surtrs_chasm_pfs.py", "_chpfs")
from aowepack_patch import kill_aow                          # noqa: E402

SPELL_REC, SPELL_DONOR = 85 + 10, 0x12 + 10
ICON = 161
MANA, UPKEEP, RESEARCH, SPHERE, TIER, FAMILY = 40, 5, 240, 7, 3, 4
TAG_UPKEEP = 0x0E
SPELL_DESC = "Wakes a mountain into a volcano that spills lava over the land around it."


def build_spell_body(donor):
    f = DF.fields(donor)
    f[DF.TAG_SFX] = CH.tremors_sfx()
    assert f.get(E.TAG_SPHERE) == b"\x03", "donor is not Level Terrain's record (sphere %r)" % f.get(E.TAG_SPHERE)
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


TARGETS = [("Spells.pfs  record %d" % SPELL_REC, E.SPELLS, SPELL_REC, SPELL_DONOR, build_spell_body)]


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
