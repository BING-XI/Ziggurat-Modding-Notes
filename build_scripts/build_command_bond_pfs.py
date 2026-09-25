#!/usr/bin/env python3
r"""
build_command_bond_pfs.py -- the Release/Ability.pfs records for the two abilities
build_command_bond.py registers at package init: Bound (0xBB, record key 197) and Commanding
(0xBC, key 198).

Both are built from Physical Protection's record (0x4D, key 87):
    tag 5  description   new text (u32-prefixed, CRLF-terminated like every vanilla one)
    tag 7  SFX node      the donor's
    tag 8  images        the donor's (the empty list: no overhead icon)
    tag 9  mask          00 00: never offered in the editor, on items or at hero level-up
                         (the data file wins over the cave once a record exists)
    no tag 6             no level-up cost

Splice machinery is build_commandedundead_pfs.py's, imported.  Every record that is not ours is
proved byte-identical before the write; the CRC residue is checked before and after.

    python build_scripts/build_command_bond_pfs.py            dry run + state
    python build_scripts/build_command_bond_pfs.py --apply    write both records
    python build_scripts/build_command_bond_pfs.py --undo     remove them (surgical)
"""
import os, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_cu", os.path.join(HERE, "build_commandedundead_pfs.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
from aowepack_patch import kill_aow                              # noqa: E402

ABILS = C.ABILS
DONOR = 0x4D
MASK = b"\x00\x00"
RECORDS = {
    0xBB + 10: ("Bound",
                "This unit serves the one that seized it. It breaks free and turns independent if "
                "that master dies or changes sides. An enemy's Dispel Magic can take it over "
                "(Res vs Res)."),
    0xBC + 10: ("Commanding",
                "Holds other units under compulsion, and loses 1 Resistance for each one it holds."),
}


def build(d, text):
    base, _e, _w, span = C.records(d)
    f = dict(C.fields_of(C.body_of(d, base, span, DONOR + 10)))
    assert C.TAG_DESC in f and C.TAG_MASK in f and C.TAG_IMG in f and C.TAG_SFX in f, \
        "donor %d is not a Protection record" % (DONOR + 10)
    assert f[C.TAG_IMG] == C.EMPTY_IMAGES, "donor %d draws an overhead icon" % (DONOR + 10)
    return C.reserialise({C.TAG_DESC: C.pstr32(text), C.TAG_SFX: f[C.TAG_SFX],
                          C.TAG_IMG: f[C.TAG_IMG], C.TAG_MASK: MASK})


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
    print("build_command_bond_pfs -- %s" % ABILS)
    for key, (name, text) in RECORDS.items():
        body = build(d, text)
        st = ("present, matches" if key in span and C.body_of(d, base, span, key) == body
              else "PRESENT, differs" if key in span else "absent")
        print("  key %d  %-11s %s" % (key, name, st))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    out = bytearray(d)
    for key, (_name, text) in RECORDS.items():
        if key in C.records(out)[3]:
            out = C.remove(out, key)
        if apply_:
            out = C.insert(out, key, build(d, text))
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
