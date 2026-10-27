#!/usr/bin/env python
r"""
build_wotw_pfs.py -- the data of Weight of the World (spell 91): Spells.pfs record 101.  Code:
build_wotw.py, build_wotw_tc.py, build_wotw_field.py, build_wotw_field_tc.py, build_wotw_anim.py.

    python build_scripts/build_wotw_pfs.py            dry run + state
    python build_scripts/build_wotw_pfs.py --apply     write the record
    python build_scripts/build_wotw_pfs.py --undo      remove it

RECORD 101 = Geyser's record 128 (its battle class 0x1E draws the cast: a spray, a burst at the
  target hex, then a loop) with the description, mana 10, research 80, sphere 3 (Earth), tier 2,
  caster family 1 (Evoker), book icon 168 (spread wings over arrows pointing down to a ground line,
  build_dual_spell_icons.py; the owner's pick of four), and:
  - the three effect slots on Particle.ILB's amber glows (3, 4, 5), anchored on the target hex: a
    faint pulse, no debris (owner: an energy spell); build_wotw_tc.py draws no spray particles;
  - its own sound list in Geyser's two-cue layout: cue 0 High Prayer's MAGICC01.WAV, cue 1 (played
    at the landing by build_wotw_tc.py) Tremors' TREMORS.WAV.  The byte after the header is the first
    cue's size (path length + 18), as in Geyser's (21 + 18) and Triple Fireball's (26 + 18) lists.
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

REC, DONOR = 91 + 10, 118 + 10           # Geyser is spell 118
ICON = 168
MANA, RESEARCH, SPHERE, TIER, FAMILY = 10, 80, 3, 2, 1
TAG_SFX = 0x0B
DESC = ("Strikes every unit within 6 hexes, flyers harder. For the rest of the battle the area "
        "doubles movement cost and grounds flyers.")
GLOW = b"EFFECTS\\PARTICLE.ILB"
SLOTS = {0: [3, 4, 5, 4], 1: [3, 4, 5, 4, 3], 2: [4, 5, 4, 3, 4]}
ANCHOR = (7, 7)                          # a 19 x 19 glow centred on the hex (base point = the hex's HP)
CUE0, CUE1 = b"SFX\\ATTACK\\MAGICC01.WAV", b"SFX\\ZSP\\TREMORS.WAV"


def sound_list():
    return (b"\x01\x01\x00\x02\x00\x00\x01" + bytes([len(CUE0) + 18]) +
            b"\x02\x00!\x00\x01\x01\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00" + bytes([len(CUE0)]) + CUE0 +
            b"\x02\x00!\x00\x02\x05\x00\x01\x04\x01\x00\x00\x00\x01\x00\x00\x01\x00!\x00\x01\x05\x00" +
            bytes([len(CUE1)]) + CUE1)


def build(donor):
    f = DF.fields(donor)
    assert f.get(E.TAG_DESC, b"")[4:].startswith(b"Invokes a massive geyser"), "donor is not Geyser's record"
    old = f[TAG_SFX]
    # the layout check: Geyser's own list must rebuild byte for byte from the same template
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
    for k, frames in SLOTS.items():
        s = slots[k]
        assert s is not None and s["kind"] in (4, 5) and s["chain"] is None, "Geyser slot %d moved" % k
        s["name"], s["frames"] = GLOW, frames
        s["xs"], s["ys"] = ANCHOR
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
