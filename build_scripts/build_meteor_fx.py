#!/usr/bin/env python
r"""
build_meteor_fx.py -- Images\Effects\METEOR.ILB, the falling meteors of Meteor Storm's impact
(build_meteor_storm_pfs.py, slot 0).  A new file; no vanilla library is touched.

    python build_scripts/build_meteor_fx.py                 state (absent / current / STALE)
    python build_scripts/build_meteor_fx.py --apply         write it
    python build_scripts/build_meteor_fx.py --undo          delete it
    python build_scripts/build_meteor_fx.py --preview DIR   the whole impact as a GIF + a strip in DIR

FRAMES  ids 0-7: a meteor falling from the upper left onto IMPACT (100, 188) of a 112 x 200 canvas,
  a white core in an orange glow with a tail that cools to red; ids 10-17: the large one, 1.6 times
  the first drawing's size (the small one is 1.2), onto IMPACT_BIG.  Sprite16 (uncompressed RGB565 of the clip rectangle, key 0), draw mode 0x202
  at blend 100 -- additive, as EXPLBIG.ILB and DESTR.ILB draw -- so black adds nothing.
PREVIEW  draws build_meteor_storm_pfs.py's chain over a grass field with the 61 hexes of radius 4
  outlined at the game's spacing (HXtoHP: 32 px a column, 32 a row, odd columns 16 lower), one tick per
  50 ms, additively with each image's blend.
"""
import math, os, struct, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
FX = os.path.join(GAME, "Images", "Effects")
OUT = os.path.join(FX, "METEOR.ILB")
TOOLS = os.path.join(HERE, "..", "re_tools")

N_FRAMES = 8
SCALE, CANVAS, IMPACT = 1.2, (112, 200), (100, 188)
SCALE_BIG, CANVAS_BIG, IMPACT_BIG = 1.6, (160, 276), (140, 260)
TRAVEL, TAIL = (56.0, 112.0), 40.0
DRAWMODE, BLEND, PIXFMT = 0x202, 100, 0x56509310


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def meteor(k, scale, canvas, impact):
    """Frame k of a fall: float RGB (h, w, 3)."""
    import numpy as np
    w, h = canvas
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.float32)
    tx, ty = TRAVEL[0] * scale, TRAVEL[1] * scale
    ln = math.hypot(tx, ty)
    ux, uy = tx / ln, ty / ln
    t = (k + 1) / N_FRAMES
    hx, hy = impact[0] - tx * (1 - t), impact[1] - ty * (1 - t)

    def blob(cx, cy, sigma, amp, col):
        g = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma * sigma)) * amp
        img[:] += g[..., None] * np.array(col, np.float32)

    tail = TAIL * scale
    steps = int(tail * 2)
    for i in range(steps):
        s = i / steps
        a = math.exp(-2.6 * s) * (1 - s) ** 0.6
        col = (255 - 85 * s, 190 - 150 * s, 80 - 70 * s)
        flick = 1.0 + 0.18 * math.sin(i * 1.7 + k * 2.3)
        blob(hx - ux * tail * s, hy - uy * tail * s, (1.5 - 1.0 * s) * scale, 0.22 * a * flick, col)
    rnd = (k * 7919 + 13) % 997
    for j in range(5):
        rnd = (rnd * 31 + 17) % 997
        s = 0.25 + 0.6 * (rnd % 100) / 100
        off = ((rnd // 100) % 9 - 4) * 0.9 * scale
        blob(hx - ux * tail * s - uy * off, hy - uy * tail * s + ux * off, 0.6 * scale, 0.55, (255, 150, 50))
    blob(hx, hy, 4.5 * scale, 0.75, (255, 140, 40))
    blob(hx, hy, 1.7 * scale, 1.0, (255, 250, 225))
    return np.clip(img, 0, 255)


def frames():
    out = []
    for k in range(N_FRAMES):
        out.append((k, meteor(k, SCALE, CANVAS, IMPACT)))
    for k in range(N_FRAMES):
        out.append((10 + k, meteor(k, SCALE_BIG, CANVAS_BIG, IMPACT_BIG)))
    return out


def to565(img):
    import numpy as np
    a = np.rint(img).astype(np.uint16)
    v = ((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)
    return v


def build():
    ilb = _load(os.path.join(TOOLS, "ilb.py"), "ilb")
    tmpl = open(os.path.join(FX, "ExplBig.ILB"), "rb").read()
    p = ilb.parse(tmpl)
    r = p["images"][1]
    o = r["dir_off"] + 4 + 4 + 1 + 4 + len(r["name"]) + 20
    unknown_a = tmpl[o]
    header = bytearray(tmpl[:28])
    dir_bytes, data = bytearray(), bytearray()
    for iid, img in frames():
        v = to565(img)
        ys, xs = (v != 0).nonzero()
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
        clip = v[y0:y1, x0:x1].astype("<u2").tobytes()
        h, w = v.shape
        name = b"Meteor%02d.bmp" % iid
        dir_bytes += struct.pack("<ii", iid, 22) + b"\x03" + struct.pack("<i", len(name)) + name
        dir_bytes += struct.pack("<5i", w, h, 0, 0, 0) + bytes([unknown_a])
        dir_bytes += struct.pack("<ii", len(clip), len(data)) + struct.pack("<ii", w, h)
        dir_bytes += struct.pack("<iiI", DRAWMODE, BLEND, PIXFMT)
        dir_bytes += struct.pack("<5i", x1 - x0, y1 - y0, x0, y0, 0) + struct.pack("<i", -1)
        data += clip
    dir_bytes += struct.pack("<i", -1)
    imgdir = 28 + len(dir_bytes)
    struct.pack_into("<III", header, 16, imgdir, imgdir + len(data), 0)
    out = bytes(header + dir_bytes + data)
    q = ilb.parse(out)
    assert q["dir_consumed"] == q["dir_end"] == imgdir and all(x["trailer_ok"] for x in q["images"])
    assert [x["id"] for x in q["images"]] == [i for i, _ in frames()]
    return out


def preview(outdir, built):
    import numpy as np
    from PIL import Image, ImageDraw
    sys.path.insert(0, GAME)
    cwd = os.getcwd()
    os.chdir(GAME)
    import build_ziggurat_manual as M
    PF = _load(os.path.join(HERE, "build_meteor_storm_pfs.py"), "_mspfs")
    tmp = os.path.join(outdir, "METEOR.preview.ILB")
    open(tmp, "wb").write(built)
    ilb = _load(os.path.join(TOOLS, "ilb.py"), "ilb")
    libs = {}

    def image(lib, iid):
        key = (lib, iid)
        if key not in libs:
            path = tmp if lib == PF.METEOR else os.path.join(GAME, "Images", lib.decode().replace("EFFECTS\\", "Effects\\"))
            recs = {x["id"]: x for x in ilb.parse(open(path, "rb").read())["images"]}
            if iid not in recs:
                libs[key] = None
            else:
                im = np.asarray(M._ilb_render(path, iid, crop=False).convert("RGB"), np.float32)
                libs[key] = (im, recs[iid].get("blend", 100) / 100.0)
        return libs[key]

    W = H = 440
    cx, cy = W // 2, H // 2 + 20
    rng = np.random.default_rng(7)
    base = np.zeros((H, W, 3), np.float32)
    base[:] = (62, 104, 46)
    base += rng.normal(0, 7, (H, W, 1))
    bg = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(bg)
    for q in range(-4, 5):
        for r in range(-4, 5):
            if max(abs(q), abs(r), abs(-q - r)) > 4:
                continue
            col = q
            row = r + (q - (q & 1)) // 2
            px = cx + 32 * col
            py = cy + 32 * row + 16 * (col & 1)
            pts = [(px + 21 * math.cos(math.radians(a)), py + 16 * math.sin(math.radians(a))) for a in range(0, 360, 60)]
            d.polygon(pts, outline=(84, 130, 66))
    base = np.asarray(bg, np.float32)
    seqs = PF.chain_specs()
    T = max(len(f) for *_x, f in seqs)
    gif, strip = [], []
    for t in range(T + 2):
        fr = base.copy()
        for lib, xs, ys, flist in seqs:
            if t >= len(flist):
                continue
            got = image(lib, flist[t])
            if got is None:
                continue
            im, blend = got
            x0, y0 = cx + xs, cy + ys
            h, w = im.shape[:2]
            a0, b0 = max(0, -x0), max(0, -y0)
            a1, b1 = min(w, W - x0), min(h, H - y0)
            if a1 > a0 and b1 > b0:
                fr[y0 + b0:y0 + b1, x0 + a0:x0 + a1] += im[b0:b1, a0:a1] * blend
        img = Image.fromarray(np.clip(fr, 0, 255).astype(np.uint8))
        gif.append(img)
        if t % 4 == 0:
            strip.append(img)
    gif[0].save(os.path.join(outdir, "meteor_storm_impact.gif"), save_all=True, append_images=gif[1:],
                duration=50, loop=0)
    cols = 6
    rows = (len(strip) + cols - 1) // cols
    S = Image.new("RGB", (cols * W // 2, rows * H // 2))
    for i, im in enumerate(strip):
        S.paste(im.resize((W // 2, H // 2)), ((i % cols) * W // 2, (i // cols) * H // 2))
    S.save(os.path.join(outdir, "meteor_storm_strip.png"))
    big = Image.new("RGB", (W * 3, H))
    for i, t in enumerate((12, 24, 44)):
        big.paste(gif[min(t, len(gif) - 1)], (i * W, 0))
    big.save(os.path.join(outdir, "meteor_storm_stills.png"))
    os.remove(tmp)
    os.chdir(cwd)
    print("  preview: %d ticks -> %s" % (T, outdir))


def main():
    built = build()
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1], built)
        return
    cur = open(OUT, "rb").read() if os.path.exists(OUT) else None
    state = "absent" if cur is None else "current" if cur == built else "STALE"
    print("build_meteor_fx -- %s: %s (%d images, %d bytes)" % (OUT, state, len(frames()), len(built)))
    if "--apply" in sys.argv:
        if state != "current":
            open(OUT, "wb").write(built)
            print("    WRITTEN")
    elif "--undo" in sys.argv:
        if cur is not None:
            os.remove(OUT)
            print("    DELETED")
    else:
        print("\n(dry run -- nothing written.  --apply / --undo / --preview DIR)")


if __name__ == "__main__":
    main()
