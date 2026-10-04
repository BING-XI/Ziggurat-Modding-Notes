#!/usr/bin/env python3
r"""
AoW1 mod -- retire the dense-starfield Sky tile (2026-10-03).

Sky (terrain 0xE) has 8 hexagon variants embedded in Release/Release.hss; GetRndResource picks
them with equal weight.  Variant 7 (the 8th H_co.BMP blob in file order, the only one outside
the contiguous run of the other seven) kept the v1 "dense starfield" recipe for the 85/15 mix
chosen 2026-07-30.  Its pixels carry horizontal bars, and the owner judged it too busy anyway
(2026-10-03), so it is retired: its literal pixels are re-skinned IN PLACE with variant SRC
rotated 180 degrees.  The tile silhouette is symmetric under that rotation, so ilb_rle16.reskin
keeps every record length and the file size; the trailing CRC-32 is repaired (hss_crc).

Result: all 8 Sky variants are calm v2 tiles; two of them are the same art at 180 degrees.

--undo writes the original barred payload back (embedded below, sha256 prefix ORIG_SHA) and
repairs the CRC.  Dry run by default; --apply writes.  Coupling: build_chasm_sky_art.py would
regenerate variant 7 as dense (its `dense={7}`) -- that script cannot run anyway (its source art
Zigmod/Sky.bmp is missing), but drop the 7 from `dense` before it is ever revived.
"""
import argparse, base64, hashlib, os, re, struct, sys, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import ilb  # noqa: E402
import hss_crc  # noqa: E402
from ilb_rle16 import decode, reskin  # noqa: E402

HSS = os.path.join(GAME, "Release", "Release.hss")
SKY, VARIANT, SRC = 0x0E, 7, 5
ORIG_SHA = "ed2dd28cf8148d8c"
ORIG = zlib.decompress(base64.b64decode(
    "eNp9Vj1vG0cQXRiGlzRiyTCMQAoMI9vdsIkXsAFv4CIHuBCPhmEIKWw6RUClMO9cuPZPIP1PTvkFgVo3IlO6dKtGVGp1"
    "mTezex+UbA6u4szbmfdmZveRMaZ489CMaexhhS+ppLO9gYNZtxlbR47kB7/H4v/AVAS/jMaOo2hMQ3iJX+Y02rqhKwi+"
    "TyXmJ5Mw1TNzsBEQOL7gb0JArTy84P9M4vZMQh5RQrCMPGErxUYSDbP8b+YQ85vE/mhG8q/aJJ6Q6mMc6meTOWSDuOcS"
    "f98M3STGVb7yLZbGaczZnt3XrJDDXE5A7IFg3DO7R1qTWssUKtIT1TSy9Gc/w6zWyfEvBOeuuTxZTwsit80HMGOWUM+L"
    "KtDFWxqwZQSeweld80qwdpjT42nmqMNOw5DXbO2+ZtBgMMoBR0Bv9QXO74L3g0m62G/wRT2+pDqytJrOU9UpE8Z6LZi3"
    "jXSW9GOfv6FbhMRAOkEYRPf69fSfr8tDZK++yhbw/hDcgSk9OOJKXJtZ4nPue3w2XV5I3ZuZVtDnHph/CvYto4xZyhqF"
    "t/sv8dt0INh1ym/svy1f4P4l+DdNpkoQGGwzVc8+38OYgfpqP4Glss939AX2OznjBp9xELcB2J/Qh8P3V/vXaW3d6go/"
    "1/7dw3zZdtaj79/TyxPgo5Zb3J9lNOW3SlrEX7+3pULSCmVi/ICZo8jzad713ak+fsEZmKS2h7Nrcl5PVznsmvl0URPS"
    "7VRIDpqH+u1WiS9L16lSxJzXXPVmVoeaz2lV0fps3BqF9Dj8iy0FE1/QJ2kClruZwDazj19+qRZhEerQVwVZg2W7n7b6"
    "UFlu2WDs1L+iSJyMT77bR8uwU809bBHa6lLGYEn0vkY94KbZs/H0zJ2HVos6L0iVWOXnuc5gySd1M82uVCWnM2baFyQZ"
    "DOg0ZE3PAA/cK//gZxGW/H2vv3QP3W52G2bmTvHk06vDMjIODsgpWp0sr7WXrmiTqgBW2r/Q8eVh2dk+mtGc+V+EVb5m"
    "2/CH7Ps7tPUFTrobBlQHnlvX50j51CnbTJd+KRlT3PudOQjASPdVxpOFbVd2OFH+GMFfcKddzI5DGdAL2/whPt2dOn98"
    "O/LrYOBI9nbN5x+Hi9n+57f//frvzhEylDuH2u2O2HR/4+ZJt496LALveGZm9+jyZPdoA2XDqMcP4pq3AyZYpkY3+jmf"
    "x+qBjxmqUQ3ldaOMcEx6r6QNpUytWF/tnlqqSLNQCjL809voPMe7IhPd66ZDTvNV7BBossqh3wPzKL6/UJ9t6kte8NNo"
    "xMLvf1vrHtI="
))


def sky_tiles(data):
    """-> [(abs payload offset, payload, clipw, cliph, transparent)] for the Sky tiles, file order"""
    out = []
    for m in re.finditer(rb"\x04ILB\x00", data):
        s = m.start()
        if data[s - 6:s - 2] != b"\x01\x00\x00\x00" or data[s - 1] != 0xFE or data[s - 2] != SKY:
            continue
        P = ilb.parse(data[s:s + struct.unpack_from("<I", data, s + 20)[0]])
        r = P["images"][0]
        off = s + P["hdr"]["imgdir"] + r["offset"]
        out.append((off, bytes(data[off:off + r["size"]]), r["clipw"], r["cliph"], r["transparent"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    args = ap.parse_args()
    assert hashlib.sha256(ORIG).hexdigest().startswith(ORIG_SHA)
    data = bytearray(open(HSS, "rb").read())
    if not hss_crc.verify(bytes(data)):
        print("ABORT: Release.hss already has a bad CRC -- find out why first"); return 1
    tiles = sky_tiles(data)
    assert len(tiles) == 8, "expected 8 Sky tiles, found %d" % len(tiles)
    off, cur, w, h, tr = tiles[VARIANT]
    _, src, sw, sh, str_ = tiles[SRC]
    assert (w, h, sw, sh, tr, str_) == (48, 32, 48, 32, tr, tr) and len(cur) == len(ORIG)
    rows, _ = decode(src, sw, sh, str_)
    new = reskin(ORIG, h, tr, lambda x, y: rows[h - 1 - y][w - 1 - x])
    want = ORIG if args.undo else new
    state = "barred original" if cur == ORIG else "retired" if cur == new else None
    if state is None:
        print("ABORT: Sky variant 7 is neither the original nor this script's tile"); return 1
    print(f"Sky variant {VARIANT} @ {off:#x}: currently {state}")
    if cur == want:
        print("nothing to do"); return 0
    if not args.apply:
        print("dry run -- re-run with --apply" + (" --undo" if args.undo else "")); return 0
    data[off:off + len(want)] = want
    out = hss_crc.fix(bytes(data))
    assert hss_crc.verify(out) and len(out) == len(data)
    try:
        open(HSS, "wb").write(out)
    except PermissionError:
        print("LOCKED -- close AoWz.exe / AoWzEd.exe and retry"); return 1
    print("restored the dense tile" if args.undo else f"retired: variant {VARIANT} = variant {SRC} rotated 180")
    return 0


if __name__ == "__main__":
    sys.exit(main())
