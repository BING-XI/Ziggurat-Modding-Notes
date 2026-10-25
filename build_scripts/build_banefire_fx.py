# -*- coding: utf-8 -*-
r"""
build_banefire_fx.py -- Images/Effects/BANEFIRE.ILB, the green-purple banefire art for the Death/Fire
spells: the game's own flame, sparkle, spray and burst frames recoloured to palette B (owner,
2026-10-25: purple flame, green edge).  A NEW file; nothing else is touched.

    python build_scripts/build_banefire_fx.py                      dry run + state
    python build_scripts/build_banefire_fx.py --preview <dir>      also write a PNG strip per group
    python build_scripts/build_banefire_fx.py --apply              write BANEFIRE.ILB
    python build_scripts/build_banefire_fx.py --undo               delete it

ENTRIES (id: source)
   0-13  Effects\FireSm2.ILB 0-13   small flame (TransparentRLESprite16) -- Taint the Flame, drawn on
                                    each unit hit (High Prayer's aura slot)
  20-22  Effects\Particle.ILB 12-14 sparkle (Picture16)                  -- Taint's lead-in sparkles
  30-32  Effects\Particle.ILB 0-2   spray particle (Picture16)           -- Pillar of Banefire's spray
  40-44  Effects\Storm1.ILB 0-4     Geyser's burst (Sprite16, 320x480)   -- Pillar's burst at the target

HOW: every directory record is copied verbatim from its source (type, geometry, clip, transparent
key and the draw-mode/blend dwords stay as they were), only its id and data offset change, and its
pixel payload is recoloured IN PLACE at the same size (RLE rows keep their margins; the transparent
key is never produced).  The particles and the burst are opaque pictures the engine blends, so black
stays black: the palette is anchored at black, and only luminance decides the new colour.
The file layout is a v4.0 header (copied from FireSm2.ILB, imgdir/filelen rewritten), the records,
then the payloads; re_tools/ilb.py must walk it cleanly before it is written.

No half-resolution twin: Images\Effects has none (the engine loads effect libraries by name only).
"""
import os, struct, sys, importlib.util

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FX = os.path.join(GAME, "Images", "Effects")
OUT = os.path.join(FX, "BANEFIRE.ILB")
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools")

GROUPS = [   # (first new id, source library, source ids, label)
    (0, "FireSm2.ILB", range(0, 14), "taint flame"),
    (20, "Particle.ILB", range(12, 15), "taint sparkle"),
    (30, "Particle.ILB", range(0, 3), "pillar spray"),
    (40, "Storm1.ILB", range(0, 5), "pillar burst"),
]

# palette B, by luminance 0..1: black floor, green edge, purple core, pale violet heart
PALETTE = [(0.00, (0, 0, 0)), (0.08, (6, 30, 10)), (0.30, (30, 140, 50)), (0.55, (160, 60, 210)),
           (0.80, (225, 150, 255)), (1.00, (250, 235, 255))]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ILB, RLE = _load("ilb"), _load("ilb_rle16")


def grad(L):
    for (l0, c0), (l1, c1) in zip(PALETTE, PALETTE[1:]):
        if L <= l1:
            t = (L - l0) / (l1 - l0)
            return tuple(int(round(a + (b - a) * t)) for a, b in zip(c0, c1))
    return PALETTE[-1][1]


def recolour565(v, key=None):
    if v == key:
        return v
    r, g, b = RLE.rgb565_to_rgb(v)
    L = min(1.0, (0.30 * r + 0.59 * g + 0.11 * b) / 255.0 * 1.15)
    out = RLE.rgb_to_rgb565(*grad(L))
    if key is not None and out == key:
        out ^= 0x0020                  # never produce the transparent key
    return out


def payload_offset_pos(d, rec):
    """File position of the record's data-offset dword (re_tools/ilb.py field order)."""
    o = rec["dir_off"] + 4 + (4 if rec["composite"] else 0)
    typ = struct.unpack_from("<i", d, o)[0]
    o += 4
    if typ == 0:
        o += 8
    o += 1
    nlen = struct.unpack_from("<i", d, o)[0]
    o += 4 + nlen + 20 + 1 + 4
    return o


def rle_recolour(data, h, key):
    """re_tools/ilb_rle16.reskin's row walk, mapping each literal pixel's own value; record lengths,
    margin markers and the 4-byte row padding stay byte-for-byte."""
    out = bytearray(data)
    pos = 0
    for y in range(h):
        reclen = struct.unpack_from("<I", out, pos)[0]
        a, b = pos + 4, pos + reclen
        if b - a >= 4 and struct.unpack_from("<H", out, a)[0] == key:
            a += 4
        if b - a >= 4 and struct.unpack_from("<H", out, b - 4)[0] == key:
            b -= 4
        assert (b - a) % 2 == 0, "row %d: odd literal span" % y
        for i in range(a, b, 2):
            struct.pack_into("<H", out, i, recolour565(struct.unpack_from("<H", out, i)[0], key))
        pos = (pos + reclen + 3) & ~3
    assert len(out) - 3 <= pos <= len(out), "RLE walk did not consume the payload"
    return bytes(out)


def recolour_payload(rec, data):
    t = rec["type"]
    if t in (17, 18):
        return rle_recolour(data, rec["cliph"], rec["transparent"] & 0xFFFF)
    if t == 22:
        key = rec["s16"][4] & 0xFFFF
        vals = struct.unpack("<%dH" % (len(data) // 2), data)
        return struct.pack("<%dH" % len(vals), *[recolour565(v, key) for v in vals])
    if t == 16:
        vals = struct.unpack("<%dH" % (len(data) // 2), data)
        return struct.pack("<%dH" % len(vals), *[recolour565(v) for v in vals])
    raise ValueError("unsupported image type %d" % t)


def build():
    first_src = open(os.path.join(FX, "FireSm2.ILB"), "rb").read()
    header = bytearray(first_src[:28])
    assert header[:4] == b"\x04ILB" and struct.unpack_from("<f", header, 8)[0] == 4.0
    recs, datas = [], []
    for first, lib, ids, _label in GROUPS:
        src = open(os.path.join(FX, lib), "rb").read()
        p = ILB.parse(src)
        assert p["dir_consumed"] == p["dir_end"] == p["hdr"]["imgdir"], "%s does not walk cleanly" % lib
        assert p["hdr"]["npal"] == 0
        byid = {r["id"]: (k, r) for k, r in enumerate(p["images"])}
        for n, sid in enumerate(ids):
            k, r = byid[sid]
            end = p["images"][k + 1]["dir_off"] if k + 1 < len(p["images"]) else p["dir_consumed"]
            if k + 1 == len(p["images"]) and src[end - 8:end] == b"\xff" * 8:
                end -= 4                      # the directory's closing -1 is not this record's
            raw = bytearray(src[r["dir_off"]:end])
            assert raw[-4:] == b"\xff\xff\xff\xff", "%s %d: record does not end in its trailer" % (lib, sid)
            assert r["offset"] is not None and not r["composite"], "%s %d: inline/composite" % (lib, sid)
            data = src[p["hdr"]["imgdir"] + r["offset"]:p["hdr"]["imgdir"] + r["offset"] + r["size"]]
            new = recolour_payload(r, data)
            assert len(new) == len(data), "%s %d: payload size changed" % (lib, sid)
            struct.pack_into("<i", raw, 0, first + n)
            recs.append((raw, payload_offset_pos(src, r) - r["dir_off"]))
            datas.append(new)
    dir_bytes, data_bytes = bytearray(), bytearray()
    for (raw, opos), data in zip(recs, datas):
        struct.pack_into("<i", raw, opos, len(data_bytes))
        dir_bytes += raw
        data_bytes += data
    dir_bytes += b"\xff\xff\xff\xff"            # closing -1, as every source directory has
    imgdir = 28 + len(dir_bytes)
    struct.pack_into("<II", header, 16, imgdir, imgdir + len(data_bytes))
    struct.pack_into("<I", header, 24, 0)
    out = bytes(header + dir_bytes + data_bytes)
    p = ILB.parse(out)
    assert p["dir_consumed"] == p["dir_end"] == imgdir and all(r["trailer_ok"] for r in p["images"])
    want = [first + n for first, _l, ids, _x in GROUPS for n in range(len(ids))]
    assert [r["id"] for r in p["images"]] == want, "ids came back wrong"
    return out


def preview(outdir, built):
    sys.path.insert(0, GAME)
    os.chdir(GAME)
    import build_ziggurat_manual as M
    from PIL import Image
    tmp = os.path.join(outdir, "BANEFIRE.preview.ILB")
    open(tmp, "wb").write(built)
    for first, _lib, ids, label in GROUPS:
        fr = [M._ilb_render(tmp, first + n, crop=False).convert("RGBA") for n in range(len(ids))]
        box = None
        for im in fr:
            bb = im.getbbox()
            if bb:
                box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]),
                                              max(box[2], bb[2]), max(box[3], bb[3]))
        fr = [im.crop(box) for im in fr] if box else fr
        W = sum(im.width + 4 for im in fr)
        H = max(im.height for im in fr)
        S = Image.new("RGBA", (W, H), (40, 40, 40, 255))
        x = 0
        for im in fr:
            S.alpha_composite(im, (x, H - im.height))
            x += im.width + 4
        S.save(os.path.join(outdir, "banefire_%s.png" % label.replace(" ", "_")))
    os.remove(tmp)


def main():
    built = build()
    cur = open(OUT, "rb").read() if os.path.exists(OUT) else None
    state = "absent" if cur is None else "current" if cur == built else "STALE"
    print("build_banefire_fx -- %s: %s (%d entries, %d bytes)"
          % (os.path.relpath(OUT, GAME), state, sum(len(g[2]) for g in GROUPS), len(built)))
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1], built)
        print("  preview written")
    if "--undo" in sys.argv:
        if cur is not None:
            os.remove(OUT)
            print("  REMOVED")
        return
    if "--apply" in sys.argv:
        if state == "current":
            print("  nothing to write")
            return
        open(OUT, "wb").write(built)
        print("  APPLIED")
    else:
        print("  (dry run: nothing written)")


if __name__ == "__main__":
    main()
