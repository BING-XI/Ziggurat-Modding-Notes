#!/usr/bin/env python3
r"""
build_livingflame_holders.py -- the Living Flame (0x52) holders.  Data only: Ziggurat/Release/Unitres.pfs.
Owner's list 2026-10-22.

    python build_scripts/build_livingflame_holders.py              dry run + state
    python build_scripts/build_livingflame_holders.py --apply
    python build_scripts/build_livingflame_holders.py --undo [--apply]

    record  unit             owner      change
    58      Salamander       0x19 base  + Living Flame 0x52
    226     Fire Elemental   0x19 base  + Living Flame 0x52
    228     Fire Sprite      0x19 base  + Living Flame 0x52

All three already carry Fire Immunity (0x07) and Fire Strike (0x0E), so the passive adds only the heal
(build_livingflame.py in battle, build_firefeed.py on the map).  Every owner's set is already wider
than 0x52, so only one bit changes per record; every other owner tag is carried over untouched.

Whole-file writer as build_stonegaze_holders.py: the index and every record directory are re-derived
each run, the unmodified file must rebuild byte for byte, and only the three records may change.

--undo: an owner that is still exactly this script's output gets its original bytes back (embedded
below); one re-saved since (AoWzEd rewrites the file whole) gets the 0x52 bit cleared in place.

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

LIVING_FLAME = 0x52
TAG_SIZE, TAG_BITS = 2, 3

# rid: (unit name, owner tag, original owner bytes as of 2026-10-22)
HOLDERS = {
    58: ("Salamander", 0x19, bytes.fromhex(
        "0402000304311b6627b500000081402080000810000010000000000b000000000000000000000000010000"
        "003400000001200200020a000b01023400")),
    226: ("Fire Elemental", 0x19, bytes.fromhex(
        "0402000304311b7227b2000000814620800008008801200000000020000000000000000200000000010000"
        "004000000001200200020a000b01014000")),
    228: ("Fire Sprite", 0x19, bytes.fromhex(
        "0202000304b20000008144200000080008022400000000000000000000000002")),
}


def ids_of(owner):
    return set(pfs.abilities_of(pfs.parse_dir(owner, top=False)))


def setbit(owner, on):
    """The owner with 0x52 set (on) or cleared; the size grown to fit when setting."""
    pre, fields = decode_dir(owner, top=False)
    if encode_dir(pre, fields) != owner:
        raise SystemExit("[ERR] an owner directory does not rebuild byte for byte")
    F = dict(fields)
    size = struct.unpack("<I", F[TAG_SIZE])[0]
    bits = bytearray(F[TAG_BITS])
    if len(bits) != (size + 7) // 8:
        raise SystemExit(f"[ERR] owner size {size} does not match its {len(bits)}-byte set")
    if on:
        size = max(size, LIVING_FLAME + 1)
        bits += bytes((size + 7) // 8 - len(bits))
        bits[LIVING_FLAME >> 3] |= 1 << (LIVING_FLAME & 7)
    else:
        bits[LIVING_FLAME >> 3] &= ~(1 << (LIVING_FLAME & 7)) & 0xFF
    new = {TAG_SIZE: struct.pack("<I", size), TAG_BITS: bytes(bits)}
    return encode_dir(pre, [(t, new.get(t, b)) for t, b in fields])


def plan(rid, body, undo):
    name, tag, orig = HOLDERS[rid]
    prefix, fields = decode_dir(body, top=True)
    if encode_dir(prefix, fields) != body:
        raise SystemExit(f"[ERR] record {rid} does not rebuild byte for byte")
    got = pfs.name_of(pfs.parse_dir(body, top=True), "unitres.pfs").strip()
    if got != name:
        raise SystemExit(f"[ERR] record {rid} is {got!r}, not {name!r}")
    cur = dict(fields)[tag]
    ours = setbit(orig, True)
    has = LIVING_FLAME in ids_of(cur)
    state = ("original" if cur == orig else "installed" if cur == ours else
             "installed, re-saved since" if has else "original, re-saved since")
    who = f"{rid:4d} {name:<16} owner {tag:#04x}"
    if undo:
        if not has:
            return "same", None, f"{who}  {state}"
        new = orig if cur == ours else setbit(cur, False)
    else:
        if has:
            return "same", None, f"{who}  {state}"
        new = ours if cur == orig else setbit(cur, True)
    want = (ids_of(cur) - {LIVING_FLAME}) if undo else (ids_of(cur) | {LIVING_FLAME})
    assert ids_of(new) == want, (rid, sorted(ids_of(new)), sorted(want))
    nb = encode_dir(prefix, [(t, new if t == tag else b) for t, b in fields])
    return "ok", nb, f"{who}  {state} -> " + ("without Living Flame" if undo else "Living Flame")


def run(d, undo, quiet=False):
    base, ent, bodies = split(d)
    if join(d, base, ent, bodies) != d:
        raise SystemExit("[ERR] the unmodified file does not rebuild byte for byte")
    out, changed = list(bodies), {}
    for k, ((rid, *_), body) in enumerate(zip(ent, bodies)):
        if rid not in HOLDERS:
            continue
        status, new, line = plan(rid, body, undo)
        if not quiet:
            print(f"[{status:<6}] {line}")
        if new is not None:
            out[k] = new
            changed[rid] = new
    if len({e[0] for e in ent} & HOLDERS.keys()) != len(HOLDERS):
        raise SystemExit("[ERR] a holder record is missing")
    return changed, join(d, base, ent, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write Unitres.pfs (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="remove Living Flame from the three")
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(GAME, "AoWzEd.exe")):
        raise SystemExit(f"[ERR] {GAME} is not the Ziggurat folder")
    d = open(TARGET, "rb").read()
    changed, out = run(d, a.undo)
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
    again, _ = run(out, a.undo, quiet=True)
    assert not again, "a second pass would change the file again"
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
