#!/usr/bin/env python
r"""
build_meteor_storm_pfs.py -- the data half of Meteor Storm (build_meteor_storm.py): Spells.pfs record 102
(spell 92).

    python build_scripts/build_meteor_storm_pfs.py            dry run + state
    python build_scripts/build_meteor_storm_pfs.py --apply     write the record
    python build_scripts/build_meteor_storm_pfs.py --undo      remove it

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other record
proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's; the two-cue sound list is
build_wotw_pfs.py's layout.

RECORD 102 = Fire Storm's record 13 (same class) with the description, mana 60, research 160 (the single
  tier-3 figure: it prices Wizard's Tower offers), sphere 7 (dual), tier 2, the book icon ICON (the meteor
  on the Earth/Air glow, build_dual_spell_icons.py), and:
  SOUNDS  cue 0 SFX\ATTACK\MAGICC01.WAV (the cast, the caster's seat only), cue 1 SFX\ATTACK\BLAST.WAV
          (the impact) -- build_meteor_storm.py plays both.
  IMAGES  slot 0 = the impact: one chain of sequences that the marker's Show draws from the hex's anchor
          (its pixel position + 16) at the frame counted from the impact.  Per meteor in IMPACTS: a fall
          (METEOR.ILB, build_meteor_fx.py: frames 0-7, or 10-17 for the large one) that ends on its
          point, then a burst there (EFFECTS\DESTR.ILB 0-17, or EFFECTS\EXPLBIG.ILB 0-29).  A
          sequence waits on image 99, which exists in none of the three libraries, as Level Terrain's
          own cast effect waits.  Fire Storm's slots 10 and 20-22 are kept.
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

REC, DONOR = 92 + 10, 3 + 10             # Fire Storm is spell 3
ICON = 169
MANA, RESEARCH, SPHERE, TIER, FAMILY = 60, 160, 7, 2, 1
TAG_SFX = 0x0B
DESC = "Meteors land two turns after casting, striking every unit within 4 hexes."
CUE0, CUE1 = b"SFX\\ATTACK\\MAGICC01.WAV", b"SFX\\ATTACK\\BLAST.WAV"
BLANK = 99

# libraries: (name, burst or fall frames, the point in the image that lands on the impact point)
METEOR = b"EFFECTS\\METEOR.ILB"
FALL, FALL_BIG = list(range(0, 8)), list(range(10, 18))
FALL_POINT, FALL_POINT_BIG = (100, 188), (140, 260)       # build_meteor_fx.py's IMPACT / IMPACT_BIG
BURST = (b"EFFECTS\\DESTR.ILB", list(range(18)), (88, 124))
BURST_BIG = (b"EFFECTS\\EXPLBIG.ILB", list(range(30)), (128, 140))

# the meteors: (tick the fall starts, x, y from the anchor in pixels, large)
IMPACTS = [
    (0, -38, -30, False), (3, 52, 18, False), (5, -88, 40, False), (8, 20, -84, False),
    (10, 96, -46, False), (13, -60, -92, False), (15, -14, 70, False), (18, 74, 82, False),
    (20, -104, -20, False), (23, 34, -12, False), (25, 110, 30, False), (28, -46, 104, False),
    (31, 2, -6, True),
]


def chain_specs():
    """[(library, xs, ys, frames)]: the falls, then the bursts (all additive, so the order is free)."""
    falls, bursts = [], []
    for t0, x, y, big in IMPACTS:
        fr, (px, py) = (FALL_BIG, FALL_POINT_BIG) if big else (FALL, FALL_POINT)
        falls.append((METEOR, x - px, y - py, [BLANK] * t0 + fr))
        lib, bf, (bx, by) = BURST_BIG if big else BURST
        bursts.append((lib, x - bx, y - by, [BLANK] * (t0 + len(fr)) + bf))
    return falls + bursts


def impact_chain():
    seqs = chain_specs()
    head = None
    for k, (lib, xs, ys, frames) in reversed(list(enumerate(seqs))):
        head = {"name": lib, "f8": k, "f18": 0, "kind": 4, "f20": 0, "xs": xs, "ys": ys, "ft10": 0,
                "frames": frames, "chain": head}
    return head


def sound_list():
    return (b"\x01\x01\x00\x02\x00\x00\x01" + bytes([len(CUE0) + 18]) +
            b"\x02\x00!\x00\x01\x01\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00" + bytes([len(CUE0)]) + CUE0 +
            b"\x02\x00!\x00\x02\x05\x00\x01\x04\x01\x00\x00\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00" +
            bytes([len(CUE1)]) + CUE1)


def build(donor):
    f = DF.fields(donor)
    assert f.get(E.TAG_DESC, b"")[4:].startswith(b"Invokes a massive firestorm"), "donor is not Fire Storm's record"
    assert f[TAG_SFX] == b"\x01\x01\x00\x00", "Fire Storm's sound list is not the empty one"
    f[E.TAG_DESC] = E.pstr32(DESC)
    f[E.TAG_MANA] = struct.pack("<I", MANA)
    f[E.TAG_RESEARCH] = struct.pack("<I", RESEARCH)
    f[E.TAG_SPHERE] = bytes([SPHERE])
    f[E.TAG_TIER] = bytes([TIER])
    f[DF.TAG_FAMILY] = bytes([FAMILY])
    f[TAG_SFX] = sound_list()
    slots = DF.seq_parse(f[DF.TAG_IMG])
    assert slots[0] is None, "Fire Storm's slot 0 is not empty"
    slots[0] = impact_chain()
    icon = slots[10]
    assert icon is not None and icon["name"] == E.ICON_PATH and icon["kind"] == 0, "slot 10 is not the icon"
    icon["f20"] = ICON
    f[DF.TAG_IMG] = DF.seq_build(slots)
    assert DF.seq_parse(f[DF.TAG_IMG]) == slots
    return E.reserialise(f)


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    d = E.read(E.SPELLS)
    if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
        sys.exit("ABORT: Spells.pfs CRC residue already wrong")
    base, _ent, _ws, span = E.records(d)
    want = build(E.body_of(d, base, span, DONOR))
    present = REC in span
    match = present and E.body_of(d, base, span, REC) == want
    print("  Spells.pfs record %d: %s" % (REC, "present, matches" if match else "PRESENT, differs" if present else "absent"))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply to write, --undo to remove)")
        return
    if (apply_ and match) or (undo and not present):
        print("    nothing to do")
        return
    out = bytearray(d)
    if present:
        out = E.remove(out, REC)
    if apply_:
        out = E.insert(out, REC, DONOR, build)[0]
    E.fix_crc(out)
    problem = E.audit(d, out, REC, expect_present=apply_)
    if problem:
        sys.exit("ABORT: audit failed -- %s (nothing written)" % problem)
    kill_aow()
    open(E.SPELLS, "wb").write(out)
    print("    %s (%d -> %d B, CRC repaired)" % ("WRITTEN" if apply_ else "REMOVED", len(d), len(out)))


if __name__ == "__main__":
    main()
