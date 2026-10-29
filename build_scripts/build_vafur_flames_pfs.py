#!/usr/bin/env python
r"""
build_vafur_flames_pfs.py -- the data of Vafur Flames (spell 97): Spells.pfs record 107.  Code:
build_vafur_flames.py, build_vafur_flames_tc.py.

    python build_scripts/build_vafur_flames_pfs.py            dry run + state
    python build_scripts/build_vafur_flames_pfs.py --apply     write the record
    python build_scripts/build_vafur_flames_pfs.py --undo      remove it

RECORD 107 = Geyser's record 128 (its battle class 0x1E draws the cast: a spray, a burst at the
  target hex, then a loop) with the description, mana 7, research 80, sphere 5 (Fire), tier 2, caster
  family 1 (Evoker), book icon 174 (Call Flames' flame three times on a slope, the owner's pick N3,
  build_dual_spell_icons.py), and:
  - the three effect slots on Fire Barrier's flames: slot 0 (the spray, which build_vafur_flames_tc.py
    never draws) on EFFECTS\FIRESM.ILB, the burst (1) and its loop (2) on EFFECTS\FIRELG.ILB's 26
    frames, anchored as TCombatFire draws them (combat sequence 24's offset plus the fire's mean
    jitter of 15 px), so the cast flares where the wall's first flame then stands;
  - its own sound list in Geyser's two-cue layout: both cues Fire Barrier's SFX\ATTACK\FIRESTRT.WAV
    (cue 0 at the cast, cue 1 played at the landing by build_vafur_flames_tc.py).
Splice machinery is build_embrittle_pfs.py's; the tag-0x0C parser is build_deathfire_pfs.py's.
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

REC, DONOR = 97 + 10, 118 + 10           # Geyser is spell 118
ICON = 174
MANA, RESEARCH, SPHERE, TIER, FAMILY = 7, 80, 5, 2, 1
TAG_SFX = 0x0B
DESC = ("Raises a wall of fire up to 6 hexes long that strikes the units in it. A unit entering the "
        "flames, or standing in them when your turn starts, is struck again.")
SMALL, LARGE = b"EFFECTS\\FIRESM.ILB", b"EFFECTS\\FIRELG.ILB"
SLOTS = {0: (SMALL, [0, 3, 6, 9], (-39, -49)),
         1: (LARGE, list(range(26)), (-95, -80)),
         2: (LARGE, list(range(26)), (-95, -80))}
CUE0 = CUE1 = b"SFX\\ATTACK\\FIRESTRT.WAV"


def sound_list():
    return (b"\x01\x01\x00\x02\x00\x00\x01" + bytes([len(CUE0) + 18]) +
            b"\x02\x00!\x00\x01\x01\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00" + bytes([len(CUE0)]) + CUE0 +
            b"\x02\x00!\x00\x02\x05\x00\x01\x04\x01\x00\x00\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00" +
            bytes([len(CUE1)]) + CUE1)


def build(donor):
    f = DF.fields(donor)
    assert f.get(E.TAG_DESC, b"")[4:].startswith(b"Invokes a massive geyser"), "donor is not Geyser's record"
    old = f[TAG_SFX]
    geyser = (b"\x01\x01\x00\x02\x00\x00\x01" + bytes([21 + 18]) +
              b"\x02\x00!\x00\x01\x01\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00\x15SFX\\MOVES\\WATERLG.WAV" +
              b"\x02\x00!\x00\x02\x05\x00\x01\x04\x01\x00\x00\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00\x1aSFX\\HIT_DEATH\\D_UNDEAD.WAV")
    assert old == geyser, "Geyser's sound list is not the layout this script rebuilds"
    f[E.TAG_DESC] = E.pstr32(DESC)
    f[E.TAG_MANA] = struct.pack("<I", MANA)
    f[E.TAG_RESEARCH] = struct.pack("<I", RESEARCH)
    f[E.TAG_SPHERE] = bytes([SPHERE])
    f[E.TAG_TIER] = bytes([TIER])
    f[DF.TAG_FAMILY] = bytes([FAMILY])
    f[TAG_SFX] = sound_list()
    slots = DF.seq_parse(f[DF.TAG_IMG])
    for k, (name, frames, anchor) in SLOTS.items():
        s = slots[k]
        assert s is not None and s["kind"] in (4, 5) and s["chain"] is None, "Geyser slot %d moved" % k
        s["name"], s["frames"] = name, frames
        s["xs"], s["ys"] = anchor
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
