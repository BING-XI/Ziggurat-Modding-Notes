#!/usr/bin/env python
r"""
build_surtrs_chasm_pfs.py -- the data half of Surtr's Chasm (build_surtrs_chasm.py): Spells.pfs
record 93 (spell 83).

    python build_scripts/build_surtrs_chasm_pfs.py            dry run + state
    python build_scripts/build_surtrs_chasm_pfs.py --apply     write the record
    python build_scripts/build_surtrs_chasm_pfs.py --undo      remove it

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELL RECORD 93 = Level Terrain's record 28 (same class, TLevelTerrain: its cast effect) with the
  description, mana 35, research 160 (the single tier-3 figure: it prices Wizard's Tower offers),
  sphere 7 (dual), tier 2, caster family 4 (Ritualist), the book icon 159 (Tremors' glyph mirrored,
  build_dual_spell_icons.py) and Tremors' sound list (record 122) with its one file,
  SFX\ZSP\TREMORS.WAV, swapped for SFX\ZSP\SURTRQK.WAV, a louder copy (build_chasm_sound.py; the
  path has the same length).  TLevelTerrainTE's PlayDefaultEffects plays it as cue 0; Level
  Terrain's own list is empty (owner 2026-10-25).  ICON = None would keep Level Terrain's icon.
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

SPELL_REC, SPELL_DONOR = 83 + 10, 0x12 + 10
SFX_FROM = 112 + 10                    # Tremors
TREMORS, LOUD = b"SFX\\ZSP\\TREMORS.WAV", b"SFX\\ZSP\\SURTRQK.WAV"   # build_chasm_sound.py
ICON = 159
MANA, RESEARCH, SPHERE, TIER, FAMILY = 35, 160, 7, 2, 4
SPELL_DESC = "Tears a jagged chasm into the ground. Climbers can scale its edges between map levels."


def tremors_sfx():
    d = E.read(E.SPELLS)
    base, _ent, _ws, span = E.records(d)
    sfx = DF.fields(E.body_of(d, base, span, SFX_FROM))[DF.TAG_SFX]
    assert sfx.count(TREMORS) == 1, "record %d's sounds are not Tremors'" % SFX_FROM
    return sfx.replace(TREMORS, LOUD)


def build_spell_body(donor):
    f = DF.fields(donor)
    f[DF.TAG_SFX] = tremors_sfx()
    assert f.get(E.TAG_SPHERE) == b"\x03", "donor is not Level Terrain's record (sphere %r)" % f.get(E.TAG_SPHERE)
    f[E.TAG_DESC] = E.pstr32(SPELL_DESC)
    f[E.TAG_MANA] = struct.pack("<I", MANA)
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
