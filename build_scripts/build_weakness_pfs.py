#!/usr/bin/env python3
r"""
build_weakness_pfs.py -- Release/Ability.pfs records for the seven Weakness abilities that
build_weakness.py registers at package init (ids 0xB3..0xB9, record keys id + 10 = 189..195).

Each record is built from the matching Protection's record (the donor, resolved by RECORD ID):
    tag 5  description   new text (u32-prefixed, CRLF-terminated like every vanilla one)
    tag 7  SFX node      the donor's (01 01 00 00)
    tag 8  images        the donor's (the empty list: no overhead icon)
    tag 9  mask          7F 02 = 0x027F, the mask build_weakness.py passes (the data file wins
                         over the cave once a record exists, so it must be written here too)
    no tag 6             no hero level-up cost: a weakness is never offered at level-up

Splice machinery (index entries, payload offsets, CRC) is build_commandedundead_pfs.py's,
imported, so the two stay one implementation.  Records are spliced in id order.  Every record
that is not ours is proved byte-identical before the write; the CRC residue 0x2144DF1C is
checked before and after.

    python build_scripts/build_weakness_pfs.py            dry run + state
    python build_scripts/build_weakness_pfs.py --apply    write the seven records
    python build_scripts/build_weakness_pfs.py --undo     remove them (surgical)

An AoWDevEd set save rewrites Ability.pfs whole and keeps these keys; --undo still finds them.
"""
import os, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_cu", os.path.join(HERE, "build_commandedundead_pfs.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
from aowepack_patch import kill_aow                              # noqa: E402

ABILS = C.ABILS
FIRST_ID = 0xB3
# (damage bit, protection id, name word, adjective, has status effect)
TYPES = [(0, 0x47, "Fire", "fire", True), (1, 0x4C, "Cold", "cold", True),
         (2, 0x4A, "Lightning", "lightning", True), (3, 0x4B, "Magic", "magically", False),
         (4, 0x49, "Poison", "poison", True), (5, 0x46, "Death", "death", True),
         (6, 0x48, "Holy", "holy", True)]
MASK = b"\x7f\x02"


def desc(word, adj, effects):
    s = "Increases the damage inflicted upon the unit by %s-based attacks by 50%%" % adj
    s += ", and subtracts 4 from the Resistance check against their effects." if effects else "."
    return s + " %s Protection cancels it; %s Immunity overrides it." % (word, word)


def build(d, base, span, bit, prot, word, adj, eff):
    f = dict(C.fields_of(C.body_of(d, base, span, prot + 10)))
    assert C.TAG_DESC in f and C.TAG_MASK in f and C.TAG_IMG in f and C.TAG_SFX in f, \
        "donor %d is not a Protection record" % (prot + 10)
    assert f[C.TAG_IMG] == C.EMPTY_IMAGES, "donor %d draws an overhead icon" % (prot + 10)
    return C.reserialise({C.TAG_DESC: C.pstr32(desc(word, adj, eff)), C.TAG_SFX: f[C.TAG_SFX],
                          C.TAG_IMG: f[C.TAG_IMG], C.TAG_MASK: MASK})


def plan(d):
    base, _e, _w, span = C.records(d)
    return [(FIRST_ID + bit + 10, word, build(d, base, span, bit, prot, word, adj, eff))
            for bit, prot, word, adj, eff in TYPES]


def audit(old, new, ours, present):
    ob, _oe, _w, osp = C.records(old)
    nb, _ne, _w2, nsp = C.records(new)
    for rid in sorted((set(osp) | set(nsp)) - ours):
        if rid not in nsp or rid not in osp or C.body_of(old, ob, osp, rid) != C.body_of(new, nb, nsp, rid):
            return "record %d changed" % rid
    for rid in ours:
        if (rid in nsp) != present:
            return "record %d %s" % (rid, "missing" if present else "still present")
    return None if C.crc_ok(new) else "CRC residue wrong"


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    d = C.read(ABILS)
    if not C.crc_ok(d):
        sys.exit("ABORT: Ability.pfs CRC residue is wrong -- the file is already damaged")
    base, _e, _w, span = C.records(d)
    want = plan(d)
    ours = {rid for rid, _n, _b in want}
    print("build_weakness_pfs -- %s" % ABILS)
    for rid, word, body in want:
        st = ("present, matches" if rid in span and C.body_of(d, base, span, rid) == body
              else "PRESENT, differs" if rid in span else "absent")
        print("  key %d  %-10s Weakness  %s" % (rid, word, st))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    out = bytearray(d)
    for rid, _w2, body in want:
        if rid in C.records(out)[3]:
            out = C.remove(out, rid)
        if apply_:
            out = C.insert(out, rid, body)
    out = C.fix_crc(out)
    err = audit(d, out, ours, apply_)
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
