#!/usr/bin/env python3
r"""
build_mirrorimage_pfs.py -- the Release/Ability.pfs record for Mirror Image, which
build_mirrorimage.py registers at package init (ability 0xC6, record key 0xC6 + 10 = 208).

Built from Forestry's record (0x03, key 13, the donor), as build_razorplate_pfs.py:
    tag 5  description   new text (u32-prefixed, CRLF-terminated like every vanilla one)
    tag 7  SFX node      the donor's
    tag 8  images        the donor's (the empty list: no overhead icon)
    tag 6  cost          4 skill points, the price of every level (the cave's Put list is what
                         the level-up charges for a multi-level ability; this keeps the two equal)
    tag 9  mask          ff 03 = 0x03FF, every TAbilitySelectionType bit: units, every item slot,
                         leader customisation, hero level-up, editor.  build_mirrorimage.py passes the
                         same mask (the data file wins over the cave once a record exists).

Being offered at hero level-up (tag 9 has 0x100|0x200) puts Mirror Image in the Ziggurat Manual's Hero
Offers grid; its 0 % row in heroskill_races.json and its Resistances column in herodlg_cats.py belong
with this record (03-abilities-added.md, "Adding a new ability").

Key 208 is the highest key, so the record is appended after 207 (Searing Aura).  Splice
machinery is build_commandedundead_pfs.py's, imported.  Every record that is not ours is proved
byte-identical before the write; the CRC residue is checked before and after.

    python build_scripts/build_mirrorimage_pfs.py        dry run + state
    python build_scripts/build_mirrorimage_pfs.py --apply write the record
    python build_scripts/build_mirrorimage_pfs.py --undo  remove it (surgical)
"""
import os, struct, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_cu", os.path.join(HERE, "build_commandedundead_pfs.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
from aowepack_patch import kill_aow                              # noqa: E402

ABILS = C.ABILS
ABIL_ID, DONOR = 0xC6, 0x03
KEY = ABIL_ID + 10
MASK = struct.pack("<H", 0x03FF)
COST = struct.pack("<I", 4)
DESC = ("The unit enters every battle with one mirror image per level. Every strike or shot aimed "
        "at it misses and destroys an image instead, until none are left.")


def build(d):
    base, _e, _w, span = C.records(d)
    f = dict(C.fields_of(C.body_of(d, base, span, DONOR + 10)))
    assert C.TAG_DESC in f and C.TAG_MASK in f and C.TAG_IMG in f and C.TAG_SFX in f, \
        "donor %d is not Forestry's record" % (DONOR + 10)
    assert f[C.TAG_IMG] == C.EMPTY_IMAGES, "donor %d draws an overhead icon" % (DONOR + 10)
    return C.reserialise({C.TAG_DESC: C.pstr32(DESC), C.TAG_COST: COST, C.TAG_SFX: f[C.TAG_SFX],
                          C.TAG_IMG: f[C.TAG_IMG], C.TAG_MASK: MASK})


def audit(old, new, present):
    ob, _oe, _w, osp = C.records(old)
    nb, _ne, _w2, nsp = C.records(new)
    for rid in sorted((set(osp) | set(nsp)) - {KEY}):
        if rid not in nsp or rid not in osp or C.body_of(old, ob, osp, rid) != C.body_of(new, nb, nsp, rid):
            return "record %d changed" % rid
    if (KEY in nsp) != present:
        return "record %d %s" % (KEY, "missing" if present else "still present")
    return None if C.crc_ok(new) else "CRC residue wrong"


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    d = C.read(ABILS)
    if not C.crc_ok(d):
        sys.exit("ABORT: Ability.pfs CRC residue is wrong -- the file is already damaged")
    base, _e, _w, span = C.records(d)
    body = build(d)
    st = ("present, matches" if KEY in span and C.body_of(d, base, span, KEY) == body
          else "PRESENT, differs" if KEY in span else "absent")
    print("build_mirrorimage_pfs -- %s\n  key %d  Mirror Image  %s" % (ABILS, KEY, st))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    out = bytearray(d)
    if KEY in C.records(out)[3]:
        out = C.remove(out, KEY)
    if apply_:
        out = C.insert(out, KEY, body)
    out = C.fix_crc(out)
    err = audit(d, out, apply_)
    if err:
        sys.exit("ABORT: audit failed -- %s" % err)
    C.independent_parse(out)
    if bytes(out) == bytes(d):
        print("\nnothing to do")
        return
    kill_aow()
    open(ABILS, "wb").write(out)
    print("\n%s -- %d records, CRC OK" % ("APPLIED" if apply_ else "UNDONE", len(C.records(out)[1])))


if __name__ == "__main__":
    main()
