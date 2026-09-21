"""RLESprite16 (ILB image type 17/18) codec -- decode and encode AoW hex tiles.

FORMAT (derived from the data 2026-07-24 and round-trip verified against every
48x32 hexagon tile embedded in Release.hss).  The pixel data is a sequence of
per-row records, one per image row, top to bottom:

    u32 reclen            ; byte length of this record, including itself
    [u16 colour, u16 left_bytes]    ; leading transparent margin -- OMITTED if 0
    u16 pixels[...]                 ; literal RGB565 pixels
    [u16 colour, u16 right_bytes]   ; trailing transparent margin -- OMITTED if 0

so  left_bytes + literal_bytes + right_bytes == width*2  for every row.  A margin
marker is present only when that margin is non-zero, so the full-width rows of a
hexagon (its middle two) are stored as bare pixels.  A marker is recognised by its
first u16 being the image's transparent colour.
⚠ **RECORDS ARE 4-BYTE ALIGNED.**  The next record starts at `align4(start + reclen)`, so a
row whose reclen is not a multiple of 4 is followed by padding.  The engine does exactly this
in `ImageLib.TRLESprite16.RemapToPixelFormat`'s walker (ILPACK `55210AC7`:
`lea esi,[esi+7]; and esi,0xFFFFFFFC; mov ecx,[esi-4]`).  Most hex tiles have every reclen
divisible by 4 so the padding never appears -- but a 47px-wide tile gives reclen 98 and DOES
pad.  Missing this makes the decoder desync mid-tile and look like corruption.

All counts are BYTES, not pixels (2 bytes per pixel).  There is exactly one
literal span per row -- fine for convex shapes such as a hexagon, and it means
**the encoded size depends only on the silhouette, not on the pixel content**:
re-skinning a tile while keeping its transparent margins produces a byte-for-byte
same-SIZE payload, which is what makes in-place splicing into Release.hss safe.

Pixels are RGB565 (pixelFormat 0x56509310) little-endian.

⚠ WIDTH/HEIGHT COME FROM `clipwide`/`cliphigh`, NOT `wide`/`high`.  Per the ILB spec
"the only part of the image that is defined in its data is the square inside clipwide
and cliphigh" -- the surrounding border is implied transparent.  Most hex tiles have
clipw==w, but at least one shipped `Hu_wl` variant is 48x32 with **clipw=47**, and
feeding it w=48 makes every row look one pixel short and eventually desync.  Pass the
clip dimensions to decode()/reskin().
"""
import struct


def rgb565_to_rgb(v):
    r = (v >> 11) & 0x1F; g = (v >> 5) & 0x3F; b = v & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def rgb_to_rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def decode(data, w, h, transparent):
    """-> (pixels, margins) ; pixels[y] = list of w ints (None = transparent),
    margins[y] = (left_bytes, right_bytes)."""
    rows, margins, pos = [], [], 0
    for y in range(h):
        if pos + 4 > len(data):
            raise ValueError(f"row {y}: data exhausted")
        reclen = struct.unpack_from("<I", data, pos)[0]
        if reclen < 12 or pos + reclen > len(data):
            raise ValueError(f"row {y}: bad reclen {reclen}")
        a, b = pos + 4, pos + reclen          # payload span
        left = right = 0
        if b - a >= 4 and struct.unpack_from("<H", data, a)[0] == transparent:
            left = struct.unpack_from("<H", data, a + 2)[0]; a += 4
        if b - a >= 4 and struct.unpack_from("<H", data, b - 4)[0] == transparent:
            right = struct.unpack_from("<H", data, b - 2)[0]; b -= 4
        body = b - a
        if left + body + right != w * 2:
            raise ValueError(f"row {y}: {left}+{body}+{right} != {w*2}")
        px = [None] * (left // 2)
        px += list(struct.unpack_from(f"<{body//2}H", data, a))
        px += [None] * (right // 2)
        rows.append(px); margins.append((left, right))
        pos = (pos + reclen + 3) & ~3          # records are 4-byte aligned
    if not (len(data) - 3 <= pos <= len(data)):
        raise ValueError(f"trailing data: consumed {pos} of {len(data)}")
    return rows, margins


def reskin(data, h, transparent, pixel_fn):
    """Rewrite ONLY the literal pixels of an RLESprite16 payload, preserving every
    record length and margin marker byte-for-byte.  `pixel_fn(x, y) -> rgb565` is
    called for each literal pixel at its image coordinates.  Returns bytes of
    exactly the same length as `data`.

    This is the safe way to re-skin a shipped tile: it makes no assumption about
    the silhouette, so it also handles the odd tiles whose rows do not span the
    full declared width (Release.hss ships one such Hu_wl variant)."""
    out = bytearray(data)
    pos = 0
    for y in range(h):
        if pos + 4 > len(out):
            raise ValueError(f"row {y}: data exhausted")
        reclen = struct.unpack_from("<I", out, pos)[0]
        if reclen < 4 or pos + reclen > len(out):
            raise ValueError(f"row {y}: bad reclen {reclen}")
        a, b = pos + 4, pos + reclen
        left = 0
        if b - a >= 4 and struct.unpack_from("<H", out, a)[0] == transparent:
            left = struct.unpack_from("<H", out, a + 2)[0]; a += 4
        if b - a >= 4 and struct.unpack_from("<H", out, b - 4)[0] == transparent:
            b -= 4
        if (b - a) % 2:
            raise ValueError(f"row {y}: odd literal byte count {b-a}")
        for i in range((b - a) // 2):
            struct.pack_into("<H", out, a + i*2, pixel_fn(left // 2 + i, y) & 0xFFFF)
        pos = (pos + reclen + 3) & ~3          # skip inter-record padding
    if not (len(out) - 3 <= pos <= len(out)):
        raise ValueError(f"trailing data: consumed {pos} of {len(out)}")
    return bytes(out)


def encode(rows, transparent):
    """Inverse of decode().  Each row must be a list of ints/None with exactly
    one contiguous non-None span (or be entirely transparent)."""
    out = bytearray()
    for y, px in enumerate(rows):
        idx = [i for i, v in enumerate(px) if v is not None]
        if idx:
            a, b = idx[0], idx[-1] + 1
            if any(px[i] is None for i in range(a, b)):
                raise ValueError(f"row {y}: transparent hole inside the span")
        else:
            a = b = 0
        left, right = a * 2, (len(px) - b) * 2
        body = (b - a) * 2
        rec = b""
        if left:
            rec += struct.pack("<HH", transparent, left)
        rec += struct.pack(f"<{b-a}H", *px[a:b])
        if right:
            rec += struct.pack("<HH", transparent, right)
        out += struct.pack("<I", len(rec) + 4) + rec
        while len(out) & 3:                    # pad to the 4-byte record boundary
            out += bytes([transparent & 0xFF if len(out) & 1 == 0 else transparent >> 8])
    return bytes(out)
