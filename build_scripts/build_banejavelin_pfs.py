#!/usr/bin/env python3
r"""
build_banejavelin_pfs.py -- the Release/Ability.pfs record for Shoot Bane Javelin, which
build_banejavelin.py registers at package init (ability 0xBE, record key 0xBE + 10 = 200).

Assembled from two live records:
    tag 5  description   new text (u32-prefixed, CRLF-terminated like every vanilla one), with
                         build_banejavelin.py's ATK/DAM
    tag 6  cost          4 skill points at hero level-up, Shoot Bolt's
    tag 7  SFX           record 67 (Shoot Bolt): SFX\ATTACK\BALLISTA.WAV + ARRHIT.WAV, the sounds
                         vanilla's Shoot Black Javelin also used
    tag 8  images        record 68 (Throw Javelin, ex Shoot Black Javelin): the 24 black-javelin
                         frames TCOMBAT\OBJECTS\ARROW.ILB 300-323 (one per direction) and the
                         auto-resolve hit icon COMBAT.ILB 123
    tag 9  mask          ff 03 = 0x03FF: units, every item slot, leader customisation, hero
                         level-up, editor -- Shoot Bolt's

Being offered at hero level-up (tag 9 has 0x100|0x200) puts the ability in the Ziggurat Manual's
Hero Offers grid; its row in heroskill_races.json (0 for every race) and its Ranged column in
herodlg_cats.py belong with this record.

Key 200 is the highest key, so the record is appended after 199 (Razor Plate).  Splice machinery is
build_commandedundead_pfs.py's, imported.  Every record that is not ours is proved byte-identical
before the write; the CRC residue is checked before and after.  Both donors' bodies are checked for
what is copied out of them, so a later edit to Shoot Bolt's sounds or Throw Javelin's sprite stops
this script instead of being cloned silently.

    python build_scripts/build_banejavelin_pfs.py            dry run + state
    python build_scripts/build_banejavelin_pfs.py --apply    write the record
    python build_scripts/build_banejavelin_pfs.py --undo     remove it (surgical)
"""
import os, re, struct, sys, importlib.util

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = _load("_cu", "build_commandedundead_pfs.py")
B = _load("_bj", "build_banejavelin.py")
from aowepack_patch import kill_aow                              # noqa: E402

ABILS = C.ABILS
ABIL_ID = B.ABIL_ID
KEY = ABIL_ID + 10
SFX_DONOR, IMG_DONOR = 0x39 + 10, 0x3A + 10          # Shoot Bolt, Throw Javelin
MASK = struct.pack("<H", 0x03FF)
COST = struct.pack("<I", 4)
DESC = "Fires a %d/%d javelin tainted with death magic at long range." % (B.ATK, B.DAM)


def ilb_refs(v, name):
    """Image indices a tag-8 list takes from ILB `name`: the path, three flag bytes, u32 index."""
    return [struct.unpack_from("<I", v, m.end() + 3)[0]
            for m in re.finditer(re.escape(name), v)]


def build(d):
    base, _e, _w, span = C.records(d)
    sfx = dict(C.fields_of(C.body_of(d, base, span, SFX_DONOR)))
    img = dict(C.fields_of(C.body_of(d, base, span, IMG_DONOR)))
    assert b"SFX\\ATTACK\\BALLISTA.WAV" in sfx[C.TAG_SFX], \
        "record %d's sounds are no longer Shoot Bolt's ballista" % SFX_DONOR
    frames = ilb_refs(img[C.TAG_IMG], b"TCOMBAT\\OBJECTS\\ARROW.ILB")
    icons = ilb_refs(img[C.TAG_IMG], b"\x0a\x00\x00\x00COMBAT.ILB")     # u32-length path
    assert frames == list(range(300, 324)), \
        "record %d no longer draws the black javelin (ARROW.ILB 300-323): %r" % (IMG_DONOR, frames)
    assert icons == [123], "record %d's auto-resolve icon is %r, not COMBAT.ILB 123" % (IMG_DONOR, icons)
    return C.reserialise({C.TAG_DESC: C.pstr32(DESC), C.TAG_COST: COST, C.TAG_SFX: sfx[C.TAG_SFX],
                          C.TAG_IMG: img[C.TAG_IMG], C.TAG_MASK: MASK})


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
    sb = dict(C.fields_of(C.body_of(d, base, span, SFX_DONOR)))
    print("build_banejavelin_pfs -- %s\n  key %d  Shoot Bane Javelin  %s\n  %r, cost %d "
          "(Shoot Bolt's: %d)" % (ABILS, KEY, st, DESC, struct.unpack("<I", COST)[0],
                                  struct.unpack("<I", sb[C.TAG_COST])[0] if C.TAG_COST in sb else 0))
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
