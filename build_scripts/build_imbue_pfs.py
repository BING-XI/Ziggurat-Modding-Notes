#!/usr/bin/env python
r"""
build_imbue_pfs.py -- the data half of Imbue Altar and Imbue Spring (build_imbue.py): Spells.pfs
records 103 and 104 (spells 93 and 94).

    python build_scripts/build_imbue_pfs.py            dry run + state
    python build_scripts/build_imbue_pfs.py --apply     write both records
    python build_scripts/build_imbue_pfs.py --undo      remove them

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other record
proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

EACH RECORD = Level Terrain's record 28 (same class, TLevelTerrain) with the description, mana 60,
  research 160 (the single tier-3 figure: it prices Wizard's Tower offers), sphere 7 (dual), tier 2,
  caster family 4 (Ritualist), the book icon (build_dual_spell_icons.py: 170 the horned shrine on the
  Death/Earth glow, 171 a willow over a pool on the Life/Earth glow, the owner's picks), and:
  SOUND   one cue, SFX\ATTACK\ENCHP02.WAV -- the sound both structures play when they bless an army.
  IMAGES  slot 0, which TLevelTerrainTE's PlayDefaultEffects plays at the target: one sequence on
          EFFECTS\MAGIC.ILB, each image held two map frames, centred on the hex (the burst's
          brightness centroid on the anchor, 8 px up): the red-to-gold burst (20-31) for the altar,
          the green sparkle (40-45, twice) for the spring (owner's pick).  Level Terrain's explosion
          chain is dropped.
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

DONOR = 0x12 + 10                        # Level Terrain is spell 18
MANA, RESEARCH, SPHERE, TIER, FAMILY = 60, 160, 7, 2, 4
SOUND = b"SFX\\ATTACK\\ENCHP02.WAV"
MAGIC = b"EFFECTS\\MAGIC.ILB"
SPELLS = {   # record: (description, icon, frames, (xs, ys))
    93 + 10: ("Raises a Blood Shrine. Every army that enters it gains Bloodlust.", 170,
              list(range(20, 32)), (-32, -124)),
    94 + 10: ("Raises a Spring of Life, which heals and blesses every army that enters it. "
              "Not on snow or wasteland.", 171, list(range(40, 46)) * 2, (-88, -78)),
}


def sound_list():
    return (b"\x01\x01\x00\x01\x00\x00\x02\x00!\x00\x01\x01\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00" +
            bytes([len(SOUND)]) + SOUND)


def builder(rec):
    desc, icon_id, frames, (xs, ys) = SPELLS[rec]

    def build(donor):
        f = DF.fields(donor)
        assert f.get(E.TAG_SPHERE) == b"\x03", "donor is not Level Terrain's record"
        f[E.TAG_DESC] = E.pstr32(desc)
        f[E.TAG_MANA] = struct.pack("<I", MANA)
        f[E.TAG_RESEARCH] = struct.pack("<I", RESEARCH)
        f[E.TAG_SPHERE] = bytes([SPHERE])
        f[E.TAG_TIER] = bytes([TIER])
        f[DF.TAG_FAMILY] = bytes([FAMILY])
        f[DF.TAG_SFX] = sound_list()
        slots = DF.seq_parse(f[DF.TAG_IMG])
        assert slots[0] is not None and slots[0]["kind"] == 4, "Level Terrain's slot 0 moved"
        slots[0] = {"name": MAGIC, "f8": 0, "f18": 1, "kind": 4, "f20": 0, "xs": xs, "ys": ys,
                    "ft10": 0, "frames": frames, "chain": None}
        icon = slots[10]
        assert icon is not None and icon["name"] == E.ICON_PATH and icon["kind"] == 0, "slot 10 is not the icon"
        icon["f20"] = icon_id
        f[DF.TAG_IMG] = DF.seq_build(slots)
        assert DF.seq_parse(f[DF.TAG_IMG]) == slots
        return E.reserialise(f)
    return build


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    for rec in sorted(SPELLS):
        d = E.read(E.SPELLS)
        if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
            sys.exit("ABORT: Spells.pfs CRC residue already wrong")
        base, _ent, _ws, span = E.records(d)
        want = builder(rec)(E.body_of(d, base, span, DONOR))
        present = rec in span
        match = present and E.body_of(d, base, span, rec) == want
        print("  Spells.pfs record %d: %s" % (rec, "present, matches" if match else "PRESENT, differs" if present else "absent"))
        if not (apply_ or undo) or (apply_ and match) or (undo and not present):
            continue
        out = bytearray(d)
        if present:
            out = E.remove(out, rec)
        if apply_:
            out = E.insert(out, rec, DONOR, builder(rec))[0]
        E.fix_crc(out)
        problem = E.audit(d, out, rec, expect_present=apply_)
        if problem:
            sys.exit("ABORT: audit failed -- %s (nothing written)" % problem)
        kill_aow()
        open(E.SPELLS, "wb").write(out)
        print("    %s (%d -> %d B, CRC repaired)" % ("WRITTEN" if apply_ else "REMOVED", len(d), len(out)))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply to write, --undo to remove)")


if __name__ == "__main__":
    main()
