#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""build_faces_hires.py -- put the 12 added hero faces in the RIGHT resolution set.

    python build_faces_hires.py            dry run (default) -- report, write nothing
    python build_faces_hires.py --apply    write both ILBs
    python build_faces_hires.py --undo     surgical revert (needs no snapshot -- see below)

THE DEFECT (found 2026-09-04)
-----------------------------
AoW1 ships every image library as a PAIR: `Images/<NAME>.ILB` at full size and
`Images/_<NAME>.ILB` at EXACTLY half.  The engine picks one by screen resolution.
Measured over the whole Images tree: 86 pairs, 85 parse, and all 85 are exact
half-size -- `_Combat` 13x1 vs `Combat` 25x2, `_City1` 28x32 vs 56x63, faces
52x64 vs 103x128.  **The `_` set being half-size is the design, not damage.**

Twelve added hero faces (ids 396..407) were appended to `Images/Faces/_H_Faces.ILB`
-- the LOW-RES file -- at full 103x128, and never added to `H_Faces.ILB` at all:

    H_Faces.ILB    67 entries, ids 0..395, all 103x128     <- missing all 12
    _H_Faces.ILB   79 entries: 67 at 52x64 + ids 396..407 at 103x128

Because the engine blits an entry at whatever size its directory record declares,
those 12 draw at DOUBLE size in low-res mode, and are absent entirely in high-res.

This script makes the pair consistent:

    H_Faces.ILB    79 entries, all 103x128   (12 appended, pixels copied verbatim)
    _H_Faces.ILB   79 entries, all 52x64     (the 12 downscaled in place)

Nothing else changes; ids 0..395 are byte-identical in both files afterwards.
`Images/Faces/Faces - Copy/` is NOT used and NOT touched -- its five files are
already byte-identical to the live full-size ones, and it predates the 12 adds.

FORMAT NOTES (verified against both files, this install)
--------------------------------------------------------
v4.0 header, no palettes: 28-byte header, then the directory, then contiguous
pixel data with NO slack and NO gaps.  Header dwords at 16/20 are `imgdir`
(data start, absolute) and `filelen`.  Image `offset` is RELATIVE to `imgdir`,
so inserting directory entries and bumping `imgdir` keeps every existing image
valid -- the same splice `build_copper_medal.py` uses.  The directory ends with a
lone -1 dword after the last entry.

Every face entry here is type 16 (Picture16), info 3, not composite, and its
pixel data is raw RGB565, `size == w*h*2`.  Entry field offsets, from `dir_off`,
with `N = len(name)`:

    0 id | 4 type | 8 info(u8) | 9 nlen | 13 name[N]
    13+N   w, h, xsh, ysh, subid        (5 dwords)
    13+N+20 unknownA (u8)
    13+N+21 size | +25 offset | +29 totw | +33 toth
    13+N+37 drawmode | +41 blend | +45 pixfmt | +49 trailer(-1)
    entry length = 13+N+53

The writer VERIFIES that formula against ilb.parse() on every entry it touches
before it writes anything, so a format surprise aborts rather than corrupts.

UNDO needs no snapshot: after --apply the full-size pixels for ids 396..407 live
in H_Faces.ILB, so --undo copies them back into _H_Faces.ILB and strips the 12
entries from H_Faces.ILB, restoring both files byte-for-byte.  A `.pre-faces_hires`
snapshot is still minted in <game dir>/backups/ on the first --apply.

IN-GAME CHECKLIST (nobody has played this -- see the module status)
    [ ] high-res mode: the 12 new portraits appear and are not stretched
    [ ] low-res mode: the 12 new portraits appear at the same size as every other face
    [ ] existing hero/unit portraits (ids 0..395) are unchanged in BOTH modes
    [ ] the hero-creation portrait picker reaches ids 396..407 (it may be range-bound;
        nothing in Unitgfx.pfs references above 331 today, so this is untested ground)
"""
import os
import struct
import sys

TOOLS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "re_tools"))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import ilb  # noqa: E402  (sys.path fix must precede)

FACES = os.path.join(GAME, "Images", "Faces")
HI = os.path.join(FACES, "H_Faces.ILB")
LO = os.path.join(FACES, "_H_Faces.ILB")
BACKUP_DIR = os.path.join(GAME, "backups")

NEW_IDS = list(range(396, 408))          # the 12 added faces
FULL_W, FULL_H = 103, 128
HALF_W, HALF_H = 52, 64                  # (103+1)//2, 128//2 -- the engine's ceil convention


# ---------------------------------------------------------------- ILB plumbing

def read(path):
    with open(path, "rb") as f:
        return f.read()


def parse(d):
    r = ilb.parse(d)
    return r["hdr"], r["images"]


def fields(rec):
    """Byte offsets of the mutable dwords inside one directory entry."""
    b = rec["dir_off"]
    w = b + 13 + len(rec["name"])
    return dict(id=b, w=w, h=w + 4, size=w + 21, offset=w + 25,
                totw=w + 29, toth=w + 33, end=w + 53)


def check_entry(d, rec):
    """Prove the field formula against what ilb.parse() reported. Aborts on surprise."""
    if rec["type"] != 16 or rec["info"] != 3 or rec["composite"]:
        sys.exit("ABORT: id %d is type=%d info=%d composite=%s -- writer handles only "
                 "type 16 / info 3 / non-composite" % (rec["id"], rec["type"],
                                                       rec["info"], rec["composite"]))
    f = fields(rec)
    for key, off in (("id", f["id"]), ("w", f["w"]), ("h", f["h"]),
                     ("size", f["size"]), ("offset", f["offset"]),
                     ("totw", f["totw"]), ("toth", f["toth"])):
        got = struct.unpack_from("<i", d, off)[0]
        if got != rec[key]:
            sys.exit("ABORT: field formula wrong for id %d: %s at 0x%X reads %d, "
                     "parser says %d" % (rec["id"], key, off, got, rec[key]))
    if struct.unpack_from("<i", d, f["end"] - 4)[0] != -1:
        sys.exit("ABORT: entry id %d has no -1 trailer where expected" % rec["id"])
    if rec["size"] != rec["w"] * rec["h"] * 2:
        sys.exit("ABORT: id %d size %d != w*h*2 (%d) -- not raw RGB565"
                 % (rec["id"], rec["size"], rec["w"] * rec["h"] * 2))
    return f


def entry_bytes(d, rec):
    return d[rec["dir_off"]:fields(rec)["end"]]


def set_dword(buf, off, val):
    struct.pack_into("<i", buf, off, val)


def sanity(path, d, hdr, imgs):
    """Directory contiguous, data contiguous, no slack -- the invariants this writer keeps."""
    if hdr["filelen"] != len(d):
        sys.exit("ABORT: %s header filelen %d != actual %d"
                 % (os.path.basename(path), hdr["filelen"], len(d)))
    cur = 0
    for rec in sorted(imgs, key=lambda r: r["offset"]):
        if rec["offset"] != cur:
            sys.exit("ABORT: %s data not contiguous at id %d (expected %d, got %d)"
                     % (os.path.basename(path), rec["id"], cur, rec["offset"]))
        cur += rec["size"]
    if hdr["imgdir"] + cur != len(d):
        sys.exit("ABORT: %s has %d bytes of slack after the pixel data"
                 % (os.path.basename(path), len(d) - hdr["imgdir"] - cur))


def rebuild(hdr, dir_body, data):
    """28-byte header + directory body + -1 terminator + pixel data."""
    imgdir = 28 + len(dir_body) + 4
    out = bytearray()
    out += struct.pack("<4sIfI", b"\x04ILB", hdr["someid"], hdr["version"], hdr["hdrlen"])
    out += struct.pack("<III", imgdir, imgdir + len(data), 0)
    out += dir_body
    out += struct.pack("<i", -1)
    out += data
    assert len(out) == imgdir + len(data)
    return bytes(out)


# ---------------------------------------------------------------- pixel work

def downscale(raw, sw, sh, dw, dh):
    """RGB565 raw -> RGB565 raw, high-quality box/Lanczos resample."""
    try:
        from PIL import Image
    except ImportError:
        sys.exit("ABORT: Pillow is required for the downscale (pip install pillow)")
    im = Image.new("RGB", (sw, sh))
    px = im.load()
    for k in range(sw * sh):
        v = raw[2 * k] | (raw[2 * k + 1] << 8)
        px[k % sw, k // sw] = ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63,
                               (v & 31) * 255 // 31)
    im = im.resize((dw, dh), Image.LANCZOS)
    px = im.load()
    out = bytearray(dw * dh * 2)
    for k in range(dw * dh):
        r, g, b = px[k % dw, k // dw]
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        out[2 * k] = v & 0xFF
        out[2 * k + 1] = v >> 8
    return bytes(out)


def pixels(d, hdr, rec):
    st = hdr["imgdir"] + rec["offset"]
    return d[st:st + rec["size"]]


# ---------------------------------------------------------------- state

def state():
    """('vanilla'|'applied'|other) plus the parsed pair."""
    dh, dl = read(HI), read(LO)
    hh, ih = parse(dh)
    hl, il = parse(dl)
    sanity(HI, dh, hh, ih)
    sanity(LO, dl, hl, il)
    hi_ids = {r["id"] for r in ih}
    lo_big = [r["id"] for r in il if (r["w"], r["h"]) == (FULL_W, FULL_H)]
    lo_ids = {r["id"] for r in il}

    if not set(NEW_IDS) <= lo_ids:
        return "unexpected", ("_H_Faces.ILB does not carry ids %s"
                              % sorted(set(NEW_IDS) - lo_ids)), (dh, hh, ih, dl, hl, il)
    if set(NEW_IDS) <= hi_ids and not lo_big:
        return "applied", "both files carry ids 396..407 at their own resolution", \
               (dh, hh, ih, dl, hl, il)
    if not (set(NEW_IDS) & hi_ids) and sorted(lo_big) == NEW_IDS:
        return "vanilla", "12 adds live only in _H_Faces.ILB, at full size", \
               (dh, hh, ih, dl, hl, il)
    return "unexpected", ("H_Faces has %d of the 12; _H_Faces has %d full-size entries"
                          % (len(set(NEW_IDS) & hi_ids), len(lo_big))), \
           (dh, hh, ih, dl, hl, il)


# ---------------------------------------------------------------- build

def build_applied(dh, hh, ih, dl, hl, il):
    """-> (new H_Faces bytes, new _H_Faces bytes)."""
    for r in ih:
        check_entry(dh, r)
    for r in il:
        check_entry(dl, r)
    by_lo = {r["id"]: r for r in il}
    new = [by_lo[i] for i in NEW_IDS]
    for r in new:
        if (r["w"], r["h"]) != (FULL_W, FULL_H):
            sys.exit("ABORT: id %d in _H_Faces is %dx%d, expected %dx%d"
                     % (r["id"], r["w"], r["h"], FULL_W, FULL_H))

    # ---- H_Faces.ILB: append the 12 verbatim, only `offset` rewritten
    keep = [r for r in ih]
    hi_dir = bytearray(dh[28:hh["imgdir"] - 4])
    hi_data = bytearray(dh[hh["imgdir"]:])
    for r in new:
        blob = bytearray(entry_bytes(dl, r))
        f = fields(r)
        set_dword(blob, f["offset"] - r["dir_off"], len(hi_data))
        hi_dir += blob
        hi_data += pixels(dl, hl, r)
    new_hi = rebuild(hh, bytes(hi_dir), bytes(hi_data))

    # ---- _H_Faces.ILB: downscale the 12 in place (directory length unchanged)
    lo_dir = bytearray(dl[28:hl["imgdir"] - 4])
    first = min(r["offset"] for r in new)
    lo_data = bytearray(dl[hl["imgdir"]:hl["imgdir"] + first])   # ids 0..395, untouched
    for r in new:
        small = downscale(pixels(dl, hl, r), FULL_W, FULL_H, HALF_W, HALF_H)
        f = fields(r)
        base = r["dir_off"] - 28
        set_dword(lo_dir, f["w"] - 28, HALF_W)
        set_dword(lo_dir, f["h"] - 28, HALF_H)
        set_dword(lo_dir, f["totw"] - 28, HALF_W)
        set_dword(lo_dir, f["toth"] - 28, HALF_H)
        set_dword(lo_dir, f["size"] - 28, len(small))
        set_dword(lo_dir, f["offset"] - 28, len(lo_data))
        assert base >= 0
        lo_data += small
    new_lo = rebuild(hl, bytes(lo_dir), bytes(lo_data))
    return new_hi, new_lo, len(keep)


def build_vanilla(dh, hh, ih, dl, hl, il):
    """Reverse: pull the full-size pixels back out of H_Faces, strip them from it."""
    for r in ih:
        check_entry(dh, r)
    for r in il:
        check_entry(dl, r)
    by_hi = {r["id"]: r for r in ih}
    by_lo = {r["id"]: r for r in il}
    missing = [i for i in NEW_IDS if i not in by_hi]
    if missing:
        sys.exit("ABORT: cannot undo -- H_Faces.ILB lacks ids %s, so the full-size "
                 "pixels are gone. Restore from backups/ instead." % missing)

    # ---- H_Faces.ILB: drop the 12 entries and their pixels
    keep = [r for r in ih if r["id"] not in set(NEW_IDS)]
    hi_dir = bytearray()
    hi_data = bytearray()
    for r in keep:
        blob = bytearray(entry_bytes(dh, r))
        f = fields(r)
        set_dword(blob, f["offset"] - r["dir_off"], len(hi_data))
        hi_dir += blob
        hi_data += pixels(dh, hh, r)
    new_hi = rebuild(hh, bytes(hi_dir), bytes(hi_data))

    # ---- _H_Faces.ILB: restore the 12 at full size from H_Faces' copy
    lo_dir = bytearray(dl[28:hl["imgdir"] - 4])
    first = min(by_lo[i]["offset"] for i in NEW_IDS)
    lo_data = bytearray(dl[hl["imgdir"]:hl["imgdir"] + first])
    for i in NEW_IDS:
        r, src = by_lo[i], by_hi[i]
        f = fields(r)
        set_dword(lo_dir, f["w"] - 28, FULL_W)
        set_dword(lo_dir, f["h"] - 28, FULL_H)
        set_dword(lo_dir, f["totw"] - 28, FULL_W)
        set_dword(lo_dir, f["toth"] - 28, FULL_H)
        set_dword(lo_dir, f["size"] - 28, src["size"])
        set_dword(lo_dir, f["offset"] - 28, len(lo_data))
        lo_data += pixels(dh, hh, src)
    new_lo = rebuild(hl, bytes(lo_dir), bytes(lo_data))
    return new_hi, new_lo, len(keep)


# ---------------------------------------------------------------- verify + write

def verify(label, path, blob, want_n, want_dims):
    hdr, imgs = parse(blob)
    sanity(path, blob, hdr, imgs)
    if len(imgs) != want_n:
        sys.exit("ABORT: %s would have %d entries, expected %d"
                 % (label, len(imgs), want_n))
    bad = [(r["id"], r["w"], r["h"]) for r in imgs if (r["w"], r["h"]) != want_dims]
    if bad:
        sys.exit("ABORT: %s would carry %d entries not %dx%d: %s"
                 % (label, len(bad), want_dims[0], want_dims[1], bad[:6]))
    ids = [r["id"] for r in imgs]
    if len(set(ids)) != len(ids):
        sys.exit("ABORT: %s would carry duplicate entry ids" % label)
    for r in imgs:
        check_entry(blob, r)
    return hdr, imgs


def snapshot(path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, os.path.basename(path) + ".pre-faces_hires")
    if not os.path.exists(dst):
        with open(dst, "wb") as f:
            f.write(read(path))
        print("   snapshot -> backups/%s" % os.path.basename(dst))


def write(path, blob):
    with open(path, "wb") as f:
        f.write(blob)


def main():
    argv = sys.argv[1:]
    apply_ = "--apply" in argv
    undo = "--undo" in argv
    if apply_ and undo:
        sys.exit("--apply and --undo are mutually exclusive")

    st, why, (dh, hh, ih, dl, hl, il) = state()
    print("H_Faces.ILB   %7d bytes  %3d entries" % (len(dh), len(ih)))
    print("_H_Faces.ILB  %7d bytes  %3d entries" % (len(dl), len(il)))
    print("state: %s -- %s" % (st.upper(), why))

    if st == "unexpected":
        sys.exit("ABORT: refusing to touch an unrecognised state.")

    if undo:
        if st == "vanilla":
            print("\nAlready reverted; nothing to do.")
            return
        new_hi, new_lo, n = build_vanilla(dh, hh, ih, dl, hl, il)
        verify("H_Faces.ILB", HI, new_hi, len(ih) - 12, (FULL_W, FULL_H))
        hdr, imgs = parse(new_lo)
        big = [r["id"] for r in imgs if (r["w"], r["h"]) == (FULL_W, FULL_H)]
        if sorted(big) != NEW_IDS:
            sys.exit("ABORT: undo would leave %d full-size entries in _H_Faces" % len(big))
        action = "UNDO"
    else:
        if st == "applied":
            print("\nAlready applied; nothing to do.")
            return
        new_hi, new_lo, n = build_applied(dh, hh, ih, dl, hl, il)
        verify("H_Faces.ILB", HI, new_hi, len(ih) + 12, (FULL_W, FULL_H))
        verify("_H_Faces.ILB", LO, new_lo, len(il), (HALF_W, HALF_H))
        action = "APPLY"

    print("\n%s would write:" % action)
    print("   H_Faces.ILB   %7d -> %7d bytes" % (len(dh), len(new_hi)))
    print("   _H_Faces.ILB  %7d -> %7d bytes" % (len(dl), len(new_lo)))

    # ids 0..395 must survive byte-identical in both files
    for label, old, new in (("H_Faces", dh, new_hi), ("_H_Faces", dl, new_lo)):
        oh, oi = parse(old)
        nh, ni = parse(new)
        nmap = {r["id"]: r for r in ni}
        for r in oi:
            if r["id"] in NEW_IDS or r["id"] not in nmap:
                continue
            if pixels(old, oh, r) != pixels(new, nh, nmap[r["id"]]):
                sys.exit("ABORT: %s id %d pixels would change" % (label, r["id"]))
    print("   ids 0..395 verified byte-identical in both files")

    if not (apply_ or undo):
        print("\n(dry run -- pass --apply to write)")
        return

    snapshot(HI)
    snapshot(LO)
    write(HI, new_hi)
    write(LO, new_lo)
    print("\n%s: written." % action)
    st2, why2, _ = state()
    print("re-read state: %s -- %s" % (st2.upper(), why2))


if __name__ == "__main__":
    main()
