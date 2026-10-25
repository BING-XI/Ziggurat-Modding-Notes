#!/usr/bin/env python3
r"""
build_stonegaze_holders.py -- the Stone Gaze (0xCB) holders.  Data only: Ziggurat/Release/Unitres.pfs.
Owner's ruling 2026-10-22 (the holders as proposed).

    python build_scripts/build_stonegaze_holders.py              dry run + state
    python build_scripts/build_stonegaze_holders.py --apply
    python build_scripts/build_stonegaze_holders.py --undo [--apply]

    record  unit                         owner        change
    65      Basilisk                     0x19 base    Doom Gaze 0x37 -> Stone Gaze 0xCB
    99      Halfling Cockatrice Hussar   0x1F gold    Doom Gaze 0x37 -> Stone Gaze 0xCB
    24      Beholder                     0x19 base    + Stone Gaze 0xCB (keeps Doom Gaze)

These three are every unit type that holds Doom Gaze.  Each owner's tag 2 (the set size in bits, u32)
grows to 0xCC and tag 3 (the LSB-first bitset) to 26 bytes; every other owner tag (the 0x31 list,
the per-ability data records) is carried over untouched.  Neither gaze has a data record.

Whole-file writer as build_heroic_spellcasting.py: the index and every record directory are re-derived
each run, the unmodified file must rebuild byte for byte, and only the three records may move.

--undo: an owner that is still exactly this script's output gets its original bytes back (embedded
below); one re-saved since (AoWzEd rewrites the file whole) gets the bits flipped back in place, which
restores the abilities but leaves the size at 0xCC.

Units already on a map keep the abilities they were created with: a Unitres edit reaches new games,
newly built units and units that rank up.
"""
import argparse, os, struct, sys
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
import pfs                                                              # noqa: E402
from build_heroic_spellcasting import TARGET, decode_dir, encode_dir, split, join  # noqa: E402
from aowepack_patch import kill_aow                                     # noqa: E402

DOOM, STONE = 0x37, 0xCB
TAG_SIZE, TAG_BITS = 2, 3

# rid: (unit name, owner tag, clear, original owner bytes as of 2026-10-22)
HOLDERS = {
    65: ("Basilisk", 0x19, DOOM, bytes.fromhex(
        "04020003043113521f7600000005042200810688800800000000002000000000010000002000000001200200"
        "020a000b01012000")),
    99: ("Halfling Cockatrice Hussar", 0x1F, DOOM, bytes.fromhex(
        "02020003048d000000000000000000800000000000000000000000")),
    24: ("Beholder", 0x19, None, bytes.fromhex(
        "0602000304311c5230723c6648ba000000400820040102988801000000000000000000000000000002000000"
        "000300000020000000400000003400000001200200020a000b0101200001200200020a000b0106400001200200"
        "020a000b01033400")),
}


def ids_of(owner):
    return set(pfs.abilities_of(pfs.parse_dir(owner, top=False)))


def retag(owner, clear, setid):
    """The owner with `clear` cleared and `setid` set; the size grown to fit `setid`."""
    pre, fields = decode_dir(owner, top=False)
    if encode_dir(pre, fields) != owner:
        raise SystemExit("[ERR] an owner directory does not rebuild byte for byte")
    F = dict(fields)
    size = struct.unpack("<I", F[TAG_SIZE])[0]
    bits = bytearray(F[TAG_BITS])
    if len(bits) != (size + 7) // 8:
        raise SystemExit(f"[ERR] owner size {size} does not match its {len(bits)}-byte set")
    size = max(size, setid + 1)
    bits += bytes((size + 7) // 8 - len(bits))
    if clear is not None:
        bits[clear >> 3] &= ~(1 << (clear & 7)) & 0xFF
    bits[setid >> 3] |= 1 << (setid & 7)
    new = {TAG_SIZE: struct.pack("<I", size), TAG_BITS: bytes(bits)}
    return encode_dir(pre, [(t, new.get(t, b)) for t, b in fields])


def plan(rid, body, undo):
    name, tag, clear, orig = HOLDERS[rid]
    prefix, fields = decode_dir(body, top=True)
    if encode_dir(prefix, fields) != body:
        raise SystemExit(f"[ERR] record {rid} does not rebuild byte for byte")
    got = pfs.name_of(pfs.parse_dir(body, top=True), "unitres.pfs").strip()
    if got != name:
        raise SystemExit(f"[ERR] record {rid} is {got!r}, not {name!r}")
    F = dict(fields)
    cur = F[tag]
    ours = retag(orig, clear, STONE)
    ids = ids_of(cur)
    swap = {clear} if clear is not None else set()
    want_ids = (ids | swap) - {STONE} if undo else (ids - swap) | {STONE}
    state =("original" if cur == orig else "installed" if cur == ours else
             "installed, re-saved since" if STONE in ids and (clear is None or clear not in ids) else
             "original, re-saved since" if STONE not in ids and (clear is None or clear in ids) else
             "OTHER")
    who = f"{rid:4d} {name:<28} owner {tag:#04x}"
    if state == "OTHER":
        return "error", None, f"{who}  holds {sorted(map(hex, ids))}: neither state"
    if undo:
        if state.startswith("original"):
            return "same", None, f"{who}  {state}"
        new = orig if cur == ours else retag(cur, STONE, clear) if clear is not None else None
        if new is None:                                      # Beholder re-saved: clear 0xCB only
            pre, of = decode_dir(cur, top=False)
            bits = bytearray(dict(of)[TAG_BITS])
            bits[STONE >> 3] &= ~(1 << (STONE & 7)) & 0xFF
            new = encode_dir(pre, [(t, bytes(bits) if t == TAG_BITS else b) for t, b in of])
    else:
        if state.startswith("installed"):
            return "same", None, f"{who}  {state}"
        new = ours if cur == orig else retag(cur, clear, STONE)
    assert ids_of(new) == want_ids, (rid, sorted(ids_of(new)), sorted(want_ids))
    nb = encode_dir(prefix, [(t, new if t == tag else b) for t, b in fields])
    return "ok", nb, f"{who}  {state} -> " + ("original" if undo else "Stone Gaze")


def run(d, undo, quiet=False):
    base, ent, bodies = split(d)
    if join(d, base, ent, bodies) != d:
        raise SystemExit("[ERR] the unmodified file does not rebuild byte for byte")
    out, changed, ok = list(bodies), {}, True
    for k, ((rid, *_), body) in enumerate(zip(ent, bodies)):
        if rid not in HOLDERS:
            continue
        status, new, line = plan(rid, body, undo)
        if not quiet:
            print(f"[{status:<6}] {line}")
        ok &= status != "error"
        if new is not None:
            out[k] = new
            changed[rid] = new
    if not quiet and len({e[0] for e in ent} & HOLDERS.keys()) != len(HOLDERS):
        raise SystemExit("[ERR] a holder record is missing")
    return ok, changed, join(d, base, ent, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write Unitres.pfs (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="restore Doom Gaze / remove Stone Gaze")
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(GAME, "AoWzEd.exe")):
        raise SystemExit(f"[ERR] {GAME} is not the Ziggurat folder")
    d = open(TARGET, "rb").read()
    ok, changed, out = run(d, a.undo)
    if not ok:
        raise SystemExit(1)
    if not changed:
        print("[i     ] nothing to do -- already in the target state")
        return

    _, ent0, before = split(d)
    _, ent1, after = split(out)
    assert [e[0] for e in ent0] == [e[0] for e in ent1]
    for (rid, *_), b0, b1 in zip(ent0, before, after):
        assert b1 == changed.get(rid, b0), f"record {rid} is not what was planned"
        f = pfs.parse_dir(b1, top=True)
        for tag, _l in pfs.UNIT_OWNERS:
            if tag in f:
                pfs.parse_dir(f[tag], top=False)
    ok2, again, _ = run(out, a.undo, quiet=True)
    assert ok2 and not again, "a second pass would change the file again"
    print(f"[i     ] {len(changed)} unit types, file {len(d)} -> {len(out)} B")
    if a.apply:
        kill_aow()
        tmp = TARGET + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(out)
        os.replace(tmp, TARGET)
        print(f"[i     ] wrote {TARGET}")
    else:
        print("[i     ] dry run -- re-run with --apply to write")


if __name__ == "__main__":
    main()
