#!/usr/bin/env python3
r"""
build_stonegaze_pfs.py -- the Release/Ability.pfs records for Stone Gaze (0xCB, key 213) and
Petrified (0xCC, key 214), which build_stonegaze.py registers at package init.

Stone Gaze, from Forestry's record (0x03, key 13), as build_smokyhaze_pfs.py:
    tag 5  description   new text (u32-prefixed, CRLF-terminated like every vanilla one)
    tag 6  cost          32 skill points at hero level-up, Doom Gaze's price (record 65)
    tag 7  SFX node      the donor's
    tag 8  images        the donor's (the empty list)
    tag 9  mask          ff 03 = 0x03FF, every TAbilitySelectionType bit, as the cave passes
Petrified, from Stunned's record (0x5C, key 102), the class it copies:
    tag 5  description   new text
    tag 7  SFX node      the donor's
    tag 8  images        the empty list, not Stunned's dazed-stars sequence: neither overhead-icon
                         consumer (TAbstractUnit.ShowEx's chain, AoWTCPCK's battlefield id list)
                         names 0xCC, and the statue tint is its battlefield mark
    tag 9  mask          00 00: a status, offered nowhere (Stunned's 0x7E reaches the item slots)
    no tag 6, as Stunned

Stone Gaze is offered at hero level-up (0x100|0x200), so it is in the Ziggurat Manual's Hero Offers
grid: its 0 % row in heroskill_races.json and its Magic column in herodlg_cats.py (Doom Gaze's)
belong with this record.

Keys 213 and 214 are the highest, so both records are appended after 212 (Smoky Haze).  Splice
machinery is build_commandedundead_pfs.py's, imported.  Every record that is not ours is proved
byte-identical before the write; the CRC residue is checked before and after.

    python build_scripts/build_stonegaze_pfs.py        dry run + state
    python build_scripts/build_stonegaze_pfs.py --apply write both records
    python build_scripts/build_stonegaze_pfs.py --undo  remove them (surgical)
"""
import os, struct, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_cu", os.path.join(HERE, "build_commandedundead_pfs.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
from aowepack_patch import kill_aow                              # noqa: E402

ABILS = C.ABILS
STONE, PETRIFIED = 0xCB, 0xCC
DOOM_KEY = 0x37 + 10
COST = struct.pack("<I", 32)
STONE_DESC = ("At the start of an enemy's turn in battle, if it is within 6 hexes and each stands in "
              "the other's front arc, it may be turned to stone: a 50% chance, then a resistance roll "
              "against attack 8. In auto-resolve, every enemy in melee reach. Magic Immunity, war "
              "machines and other Stone Gaze units are immune.")
PETRIFIED_DESC = ("Turned to stone for the rest of the battle: the unit cannot act and its Defense is 8 "
                  "higher. It counts as fallen when the battle is decided; after a won battle it turns "
                  "back to flesh, after a lost one it dies. Dispel Magic or Remedy restores it.")

# key: (name, donor key, tags to keep from the donor, new tags)
RECORDS = {
    STONE + 10: ("Stone Gaze", 0x03 + 10, (C.TAG_SFX, C.TAG_IMG),
                 {C.TAG_DESC: C.pstr32(STONE_DESC), C.TAG_COST: COST,
                  C.TAG_MASK: struct.pack("<H", 0x03FF)}),
    PETRIFIED + 10: ("Petrified", 0x5C + 10, (C.TAG_SFX,),
                     {C.TAG_DESC: C.pstr32(PETRIFIED_DESC), C.TAG_IMG: C.EMPTY_IMAGES,
                      C.TAG_MASK: struct.pack("<H", 0x0000)}),
}


def build(d):
    base, _e, _w, span = C.records(d)
    doom = dict(C.fields_of(C.body_of(d, base, span, DOOM_KEY)))
    assert doom[C.TAG_COST] == COST, "Doom Gaze's cost is no longer 32"
    out = {}
    for key, (_name, donor, keep, new) in RECORDS.items():
        f = dict(C.fields_of(C.body_of(d, base, span, donor)))
        assert f[C.TAG_DESC].startswith(b"/\x00\x00\x00Reduces movement" if donor == 13 else
                                        b"T\x00\x00\x00The unit is dazed"), "donor %d moved" % donor
        assert all(t in f for t in keep), "donor %d lacks a kept tag" % donor
        if C.TAG_IMG in keep:
            assert f[C.TAG_IMG] == C.EMPTY_IMAGES, "donor %d draws an overhead icon" % donor
        tags = dict(new)
        tags.update({t: f[t] for t in keep})
        out[key] = C.reserialise(dict(sorted(tags.items())))
    return out


def audit(old, new, present):
    ob, _oe, _w, osp = C.records(old)
    nb, _ne, _w2, nsp = C.records(new)
    for rid in sorted((set(osp) | set(nsp)) - set(RECORDS)):
        if rid not in nsp or rid not in osp or C.body_of(old, ob, osp, rid) != C.body_of(new, nb, nsp, rid):
            return "record %d changed" % rid
    for key in RECORDS:
        if (key in nsp) != present:
            return "record %d %s" % (key, "missing" if present else "still present")
    return None if C.crc_ok(new) else "CRC residue wrong"


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    d = C.read(ABILS)
    if not C.crc_ok(d):
        sys.exit("ABORT: Ability.pfs CRC residue is wrong -- the file is already damaged")
    base, _e, _w, span = C.records(d)
    bodies = build(d)
    print("build_stonegaze_pfs -- %s" % ABILS)
    for key, body in bodies.items():
        st = ("present, matches" if key in span and C.body_of(d, base, span, key) == body
              else "PRESENT, differs" if key in span else "absent")
        print("  key %d  %-10s  %s" % (key, RECORDS[key][0], st))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    out = bytearray(d)
    for key in sorted(RECORDS, reverse=True):
        if key in C.records(out)[3]:
            out = C.remove(out, key)
    if apply_:
        for key in sorted(RECORDS):
            out = C.insert(out, key, bodies[key])
    out = C.fix_crc(out)
    err = audit(d, out, apply_)
    if err:
        sys.exit("ABORT: audit failed -- %s" % err)
    C.independent_parse(out)
    if apply_:
        nb, _ne, _w, nsp = C.records(out)
        assert all(C.body_of(out, nb, nsp, k) == b for k, b in bodies.items())
    if bytes(out) == bytes(d):
        print("\nnothing to do")
        return
    kill_aow()
    open(ABILS, "wb").write(out)
    print("\n%s -- %d records, CRC OK" % ("APPLIED" if apply_ else "UNDONE", len(C.records(out)[1])))


if __name__ == "__main__":
    main()
