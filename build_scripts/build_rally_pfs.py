#!/usr/bin/env python3
r"""
build_rally_pfs.py -- the Release/Ability.pfs records for Rally (0xC2, key 204) and its status
Rallied (0xC3, key 205), which build_rally.py registers at package init.

    Rally     built from Forestry's record (0x03, key 13): tag 5 new text, tag 6 cost 12 (Healing's
              price), tag 7 SFX and tag 8 (the empty image list) the donor's, tag 9 mask 0x03FF --
              every TAbilitySelectionType bit, as the registration cave passes.  Offered at hero
              level-up, so it sits in the Hero Offers grid (0 % per race, heroskill_races.json) and
              the Magic column (herodlg_cats.py).
    Rallied   built from Panicked's record (0x6C, key 118): tag 5 new text, tags 7/8 the donor's,
              tag 9 mask 0 -- a status, never offered or assignable, as Embrittled (key 188).

Keys 204 and 205 are the highest, so both are appended after 203 (Extra Shots).  Splice machinery is
build_commandedundead_pfs.py's, imported.  Every record that is not ours is proved byte-identical
before the write; the CRC residue is checked before and after.

    python build_scripts/build_rally_pfs.py            dry run + state
    python build_scripts/build_rally_pfs.py --apply    write both records
    python build_scripts/build_rally_pfs.py --undo     remove them (surgical)
"""
import os, struct, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_cu", os.path.join(HERE, "build_commandedundead_pfs.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
from aowepack_patch import kill_aow                              # noqa: E402

ABILS = C.ABILS
RECORDS = {   # key: (donor key, description, cost or None, mask)
    0xC2 + 10: (0x03 + 10,
                "Activates when clicked, using the unit's action. Every ally within 6 hexes, the unit "
                "included: a panicked one has a 50% chance to recover, and each gains +30 morale for "
                "the rest of the battle.", 12, 0x03FF),
    0xC3 + 10: (0x6C + 10,
                "Rallied: +30 morale for the rest of the battle.", None, 0x0000),
}


def build(d):
    base, _e, _w, span = C.records(d)
    out = {}
    for key, (donor, desc, cost, mask) in RECORDS.items():
        f = dict(C.fields_of(C.body_of(d, base, span, donor)))
        assert C.TAG_DESC in f and C.TAG_MASK in f and C.TAG_IMG in f and C.TAG_SFX in f, \
            "donor %d lacks a standard field" % donor
        rec = {C.TAG_DESC: C.pstr32(desc), C.TAG_SFX: f[C.TAG_SFX], C.TAG_IMG: f[C.TAG_IMG],
               C.TAG_MASK: struct.pack("<H", mask)}
        if cost is not None:
            rec[C.TAG_COST] = struct.pack("<I", cost)
        out[key] = C.reserialise(rec)
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
    print("build_rally_pfs -- %s" % ABILS)
    for key, body in bodies.items():
        st = ("present, matches" if key in span and C.body_of(d, base, span, key) == body
              else "PRESENT, differs" if key in span else "absent")
        print("  key %d  %s" % (key, st))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    out = bytearray(d)
    for key in sorted(RECORDS):
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
    if bytes(out) == bytes(d):
        print("\nnothing to do")
        return
    kill_aow()
    open(ABILS, "wb").write(out)
    print("\n%s -- %d records, CRC OK" % ("APPLIED" if apply_ else "UNDONE", len(C.records(out)[1])))


if __name__ == "__main__":
    main()
