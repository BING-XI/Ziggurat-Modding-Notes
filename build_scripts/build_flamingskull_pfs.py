#!/usr/bin/env python3
r"""
build_flamingskull_pfs.py -- the Release/Ability.pfs record for Hurl Flaming Skull, which
build_flamingskull.py registers at package init (ability 0xBF, record key 0xBF + 10 = 201).

    tag 5  description   new text, with build_flamingskull.py's ATK/DAM
    tag 6  cost          20 skill points at hero level-up, Hurl Boulder's
    tag 7  SFX           record 34 (Hurl Boulder): SFX\ATTACK\CATAPULT.WAV + A_PUNCH2.WAV
    tag 8  images        a 41-slot ImageLib.TImageSequenceList, as every hurl's: slot 0 = the flight
                         sprite in manual combat, slot 40 = the picture TRangedAttackCA.ShowObject
                         (0x5576E550) draws in the auto-combat replay.  Both are Images/Combat.ILB
                         entry 116, the cut ability's flaming skull (Fire Cannon flies its own
                         Combat.ILB entry, 112, the same way).  Slot 0 centres the skull's clip rect
                         (25x28 at 18,0) on the flight path, as Hurl Boulder's 64x64 frames are
                         centred (-32); slot 40 places it where Hurl Boulder's entry 110 sits.
    tag 9  mask          ff 03 = 0x03FF, Hurl Boulder's

TImageSequenceList, from ILPACK's LoadFromStream (0x552190D8 / 0x55218A60 / 0x55219F1C):
    u32 count; per slot u8 0 = a sequence follows, non-zero = empty slot.  A sequence: u32-length
    library name, u8 layer, u8 speed, u8 mode, u32 image, i32 dx, i32 dy, [mode 4/5: u32 flags,
    u32 n, n x u32 frames], u8 child-follows.

Ranked like the other records: offered at hero level-up (tag 9 has 0x100|0x200), so its row in
heroskill_races.json (0 for every race) and its Ranged column in herodlg_cats.py belong with it.
Key 201 is the highest key and is appended.  Splice machinery: build_commandedundead_pfs.py's.

    python build_scripts/build_flamingskull_pfs.py            dry run + state
    python build_scripts/build_flamingskull_pfs.py --apply    write the record
    python build_scripts/build_flamingskull_pfs.py --undo     remove it (surgical)
"""
import os, struct, sys, importlib.util

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
S = _load("_fs", "build_flamingskull.py")
from aowepack_patch import kill_aow                              # noqa: E402

ABILS = C.ABILS
ABIL_ID = S.ABIL_ID
KEY = ABIL_ID + 10
SFX_DONOR = 0x18 + 10                                # Hurl Boulder
MASK = struct.pack("<H", 0x03FF)
COST = struct.pack("<I", 20)
DESC = "Launches a flaming skull (%d/%d) at a long-ranged wall or unit." % (S.ATK, S.DAM)
LIBRARY, IMAGE = b"COMBAT.ILB", 116
SLOTS = 41
FLIGHT = dict(layer=0, speed=0, mode=0, img=IMAGE, dx=-30, dy=-14)     # slot 0
REPLAY = dict(layer=0, speed=0, mode=0, img=IMAGE, dx=-20, dy=-22)     # slot 40


def sequence(s):
    return (struct.pack("<I", len(LIBRARY)) + LIBRARY
            + bytes([s["layer"], s["speed"], s["mode"]])
            + struct.pack("<Iii", s["img"], s["dx"], s["dy"]) + b"\x00")


def image_list():
    out = bytearray(struct.pack("<I", SLOTS))
    for k in range(SLOTS):
        s = FLIGHT if k == 0 else REPLAY if k == SLOTS - 1 else None
        out += b"\x00" + sequence(s) if s else b"\x01"
    return bytes(out)


def parse_image_list(b):
    """The reader's own walk, for the self-check: [(slot, library, img, dx, dy)]."""
    n, p, got = struct.unpack_from("<I", b, 0)[0], 4, []
    for k in range(n):
        flag = b[p]; p += 1
        if flag:
            continue
        ln = struct.unpack_from("<I", b, p)[0]; p += 4
        lib = b[p:p + ln]; p += ln
        mode = b[p + 2]; p += 3
        img, dx, dy = struct.unpack_from("<Iii", b, p); p += 12
        assert (mode - 4) & 0xFF >= 2, "no frame table expected"
        assert b[p] == 0, "no child expected"; p += 1
        got.append((k, lib, img, dx, dy))
    assert p == len(b), "image list has %d trailing bytes" % (len(b) - p)
    return got


def build(d):
    base, _e, _w, span = C.records(d)
    sfx = dict(C.fields_of(C.body_of(d, base, span, SFX_DONOR)))
    assert b"SFX\\ATTACK\\CATAPULT.WAV" in sfx[C.TAG_SFX], \
        "record %d's sounds are no longer Hurl Boulder's catapult" % SFX_DONOR
    img = image_list()
    assert parse_image_list(img) == [(0, LIBRARY, IMAGE, FLIGHT["dx"], FLIGHT["dy"]),
                                     (40, LIBRARY, IMAGE, REPLAY["dx"], REPLAY["dy"])]
    return C.reserialise({C.TAG_DESC: C.pstr32(DESC), C.TAG_COST: COST, C.TAG_SFX: sfx[C.TAG_SFX],
                          C.TAG_IMG: img, C.TAG_MASK: MASK})


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
    hb = dict(C.fields_of(C.body_of(d, base, span, SFX_DONOR)))
    print("build_flamingskull_pfs -- %s\n  key %d  Hurl Flaming Skull  %s\n  %r, cost %d "
          "(Hurl Boulder's: %d)" % (ABILS, KEY, st, DESC, struct.unpack("<I", COST)[0],
                                    struct.unpack("<I", hb[C.TAG_COST])[0] if C.TAG_COST in hb else 0))
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
