#!/usr/bin/env python3
r"""
build_zigail_razorplate.py -- Razor Plate (ability 0xBD) on four items of the Ziggurat item library.

Owner request 2026-10-10: put the new Razor Plate on 0-5 items of `User/Zig.ail`, where it fits.
Chosen (physical armour and shields only; Razor Plate cuts melee attackers):

    29  Blacksteel Shield   (no abilities)          a dark-steel shield with a bladed rim
    235 Scale Mail          (no abilities)          razor-edged scales
    232 Sandworm Scales     (Tunneling, Wall Crushing)  an abrasive burrowing hide
    311 Vine Shield         (Entangle Strike)       thorny vines -- the classic thorns cut

It works from an item: Razor Plate's caves ask the struck combat unit's GetAbilityEnabled (combat
VMT +0xA8 = TCombatUnit.GetAbilityEnabled 0x55725004), which forwards to the strategic unit's
item-aware +0x148 (aow1-two-ability-query-apis). No engine change.

FORMAT (measured on Zig.ail 2026-10-10)
    tag 2  u32  the ability set's size in bits = highest id + 1 (Chicken Shield, Parry 113 -> 114)
    tag 3       the bitset, ceil(size/8) bytes, LSB-first, bit index = ability id
    Razor Plate 189 needs size 190 and 24 bytes; the longest set in the file was 19 bytes.
    A plain passive needs no tag 0x31 entry and no per-ability sub-record.

HOW (the directory is copied verbatim, never re-derived -- build_item_hpmv_data.py's rule)
    * a record with no ability tags (29, 235): tags 2 and 3 are APPENDED (add_tags).
    * a record with them (232, 311): tag 2 is rewritten in place (u32, same length); tag 3 grows to
      24 bytes and every field whose offset lies after it shifts by the growth -- same entry widths,
      same entry order; aborts if a small (u8) offset would overflow.
    Record-index offsets of the later records move with the growth (reassemble keeps entry widths).

UNDO
    Byte-exact while the file is still this script's output: the four original records are
    embedded below and put back. If the game or editor has re-saved Zig.ail since (its writer
    re-lays records), --undo instead clears bit 189 in place -- semantically the same, not
    byte-exact.

Dry run by default; --apply / --undo; re-running verifies.
"""
import argparse, base64, hashlib, os, struct, sys, zlib
sys.dont_write_bytecode = True
from build_item_hpmv_data import (AIL, GAME, add_tags, emit, fields_of, parse_header, reassemble,
                                  split)
from aowepack_patch import kill_aow

ABIL = 0xBD
SIZE = ABIL + 1                         # 190 bits
NBYTES = (SIZE + 7) // 8                # 24
ITEMS = {29: "Blacksteel Shield", 235: "Scale Mail", 232: "Sandworm Scales", 311: "Vine Shield"}

ORIG_SHA = "a42ae1ec094b1e9d"   # the four records as they were before this script (sorted id order)
ORIG = {rid: zlib.decompress(base64.b64decode(b)) for rid, b in {
    29: ("eNrLYGJi4GBn4GDhEuMR55cQlhSVFVMsZGRgEHTKSUzOLi5JTc1RCM7ITM1JYWRi9mZgYHgJlGSOykwHAAOCCuU="),
    232: ("eNrLYGJi4GZiYGZhF+YQ51Ln0eDXFNYS1RM3EjMuY4ACFhhDYSkjAwN/cGJeSnl+Ua5CcHJiTmoxIyNjAFCuHyjF"
         "whyVmQ4AbrsLkg=="),
    235: ("eNrLYGJi4GRn4GDh4ucR4BcUFhIVE5cSk17AyMDAFZycmJOq4JuYmcPEyCjHwMDQBRRlYo7KTAcArFEHog=="),
    311: ("eNrLYGJi4GJiYGZhF+YQ51LmUeFXFVYT1RLTq2BABw1VjAwM3GGZeakKwRmZqTkpDIzMKUDxT0Bh5qjMdAAWrgoX"),
}.items()}


def offsets(body):
    _t4, small, wide, dsz = parse_header(body)
    return small, wide, dsz


def grow_tag3(body, new3):
    """Replace tag 3's payload with `new3` (longer), shifting every later field."""
    top4, small, wide, dsz = parse_header(body)
    ent = small + wide
    o3 = [o for t, o in ent if t == 3][0]
    if sum(1 for t, o in ent if o == o3) != 1:
        raise ValueError("another field shares tag 3's offset -- refusing")
    order = sorted(o for _t, o in ent)
    after = [o for o in order if o > o3]
    end3 = after[0] if after else len(body) - dsz
    payload = bytearray(body[dsz:])
    delta = len(new3) - (end3 - o3)
    if delta < 0:
        raise ValueError("tag 3 would shrink")
    payload[o3:end3] = new3

    def fix(lst, width):
        out = []
        for t, o in lst:
            if o > o3:
                o += delta
                if width == 1 and o > 0xFF:
                    raise ValueError("a small entry's offset would overflow")
            out.append((t, o))
        return out
    return emit(top4, fix(small, 1), fix(wide, 4), payload)


def put_tag2(body, size):
    top4, small, wide, dsz = parse_header(body)
    o2 = [o for t, o in small + wide if t == 2][0]
    b = bytearray(body)
    assert len(fields_of(body)[2]) == 4
    struct.pack_into("<I", b, dsz + o2, size)
    return bytes(b)


def with_razor(body):
    f = fields_of(body)
    if 3 not in f:
        bits = bytearray(NBYTES)
        bits[ABIL // 8] |= 1 << (ABIL % 8)
        assert 2 not in f
        return add_tags(body, [(2, struct.pack("<I", SIZE)), (3, bytes(bits))])
    bits = bytearray(f[3]) + bytearray(max(0, NBYTES - len(f[3])))
    bits[ABIL // 8] |= 1 << (ABIL % 8)
    old2 = struct.unpack("<I", f[2])[0]
    out = grow_tag3(body, bytes(bits)) if len(bits) > len(f[3]) else body
    return put_tag2(out, max(old2, SIZE))


def has_razor(body):
    f = fields_of(body)
    b = f.get(3, b"")
    return len(b) > ABIL // 8 and bool(b[ABIL // 8] & (1 << (ABIL % 8)))


def clear_razor(body):
    """Semantic undo for a re-saved file: clear the bit in place, no length change."""
    top4, small, wide, dsz = parse_header(body)
    o3 = [o for t, o in small + wide if t == 3][0]
    b = bytearray(body)
    b[dsz + o3 + ABIL // 8] &= ~(1 << (ABIL % 8)) & 0xFF
    return bytes(b)


def main():
    ap = argparse.ArgumentParser(description="Razor Plate on four Zig.ail items")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    a = ap.parse_args()
    d = open(AIL, "rb").read()
    base, ent, bodies = split(d)
    byid = dict(bodies)
    for rid, nm in ITEMS.items():
        f8 = fields_of(byid[rid]).get(8, bytes(1))
        got = f8[1:1 + f8[0]].decode("latin-1")
        if got != nm:
            sys.exit("ABORT: record %d is %r, not %r" % (rid, got, nm))
    state = {rid: has_razor(byid[rid]) for rid in ITEMS}
    print("build_zigail_razorplate -- %s" % os.path.relpath(AIL, GAME))
    for rid, nm in ITEMS.items():
        print("  %3d %-20s %s" % (rid, nm, "Razor Plate" if state[rid] else "-"))

    if ORIG:
        assert hashlib.sha256(b"".join(ORIG[r] for r in sorted(ORIG))).hexdigest().startswith(ORIG_SHA)
    if a.undo:
        new = []
        for rid, body in bodies:
            if rid in ITEMS and state[rid]:
                if rid in ORIG and with_razor(ORIG[rid]) == body:
                    body = ORIG[rid]
                else:
                    print("  record %d was re-saved since -- clearing the bit in place" % rid)
                    body = clear_razor(body)
            new.append((rid, body))
    else:
        new = [(rid, with_razor(body) if rid in ITEMS and not state[rid] else body)
               for rid, body in bodies]
    out = reassemble(d, base, ent, new)
    # self-test: every untouched record byte-identical, touched ones parse and carry exactly
    # the intended change
    _b2, _e2, after = split(out)
    for (rid, b0), (rid2, b1) in zip(bodies, after):
        assert rid == rid2
        if rid not in ITEMS:
            assert b0 == b1, "record %d changed" % rid
            continue
        f0, f1 = fields_of(b0), fields_of(b1)
        for t in set(f0) | set(f1):
            if t in (2, 3):
                continue
            assert f0.get(t) == f1.get(t), "record %d tag 0x%X changed" % (rid, t)
        assert has_razor(b1) == (not a.undo)
    if not a.undo:
        # the round trip this script promises: undo of our own output is the input, byte-exact
        rt = [(rid, ORIG.get(rid, b) if rid in ITEMS and not state[rid] else b) for rid, b in bodies]
        assert all(state.values()) or reassemble(d, base, ent, rt) == d
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written; self-test passed, file %d -> %d bytes)"
              % (len(d), len(out)))
        return
    if out == d:
        print("\nnothing to do")
        return
    kill_aow()
    open(AIL, "wb").write(out)
    print("\n%s -- Zig.ail %d -> %d bytes" % ("UNDONE" if a.undo else "APPLIED", len(d), len(out)))


if __name__ == "__main__":
    main()
