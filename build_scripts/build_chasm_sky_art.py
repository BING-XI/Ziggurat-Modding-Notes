#!/usr/bin/env python3
r"""
AoW1 mod -- Chasm & Sky terrain, STEP 2: the tile graphics.  (v2 grade, 2026-07-30)

Re-skins the hexagon tiles of the two appropriated terrains, IN PLACE inside
Release/Release.hss:
    Chasm = terrain 0xB (ex-uWasteland)  -- 15 tiles named 'Hu_wl.BMP'
    Sky   = terrain 0xE (ex-Coast)       --  8 tiles named 'H_co.BMP'

TWO DIFFERENT SOURCES, ONE PER TERRAIN (v2 -- see "WHAT CHANGED IN v2" below):
    Sky   = the user's starfield art in <game>/Zigmod/Sky.bmp (a 256x256 PNG),
            decomposed into a smooth nebula + individually stamped stars.
    Chasm = the game's OWN surface-water tiles (`H_Wa2.BMP`, ids 140..155 of
            `Images/Waterhex.ILB`), re-graded into a near-black sea.
            <game>/Zigmod/Chasm.bmp is no longer used.

THE CRC (solved 2026-07-27; the lead was the user's own 2021 note pointing at
EngineP.dpl!Engine.GetCRC32)
  `HSEngine.THSEngine.LoadHSS` (HSEPack 5560F75C) reads the LAST dword of the file
  as a stored CRC and compares it with `GetCRC32(file, size-4)`; on mismatch it
  raises Exception('Invalid HSSET'), which is unhandled during startup, so both
  AoWDevEd.exe and AoW.exe just vanish.  `Engine.GetCRC32` (EngineP 5550E608) is
  textbook reflected CRC-32 == zlib.crc32; its lookup table is built at RUNTIME,
  which is why no static CRC32 table appears anywhere in the binaries.
  So an in-place splice is fine provided the trailing dword is recomputed --
  see re_tools/hss_crc.py.  (Not to be confused with TEngine.ReadFromFileCRC,
  EngineP 5551C084, a different container that stores its CRC FIRST.)

WHY THE SPLICE ITSELF IS SAFE
  Hexagon tiles are 48x32 RLESprite16 images embedded as self-contained mini-ILBs
  (see Hex_Transition_System.md).  `ilb_rle16.reskin()` rewrites ONLY the literal
  pixel words, leaving every record length and margin marker untouched, so the
  payload cannot change length (asserted anyway) and nothing in the stream moves.
  Each tile keeps its own exact silhouette.  Deterministic -- re-running produces
  identical bytes, so the script is idempotent.

WHAT CHANGED IN v2 (user feedback: "the stars are too high-frequency")
  v1 sampled a 48x32 window of the source art after a `shrink=2` MAX-POOL.  Max-
  pooling was meant to keep single-pixel stars crisp, but it also meant one tile
  covered 96x64 source pixels -- so a hex showed ~33 stars, and every 4-point
  sparkle in the art was pooled down into a shapeless dot.  A field of those read
  as confetti, not as sky.  Two fixes, and they are structural, not knob-turning:

  1. SKY: the two frequency bands are now generated SEPARATELY.
     * nebula -- the source box-downscaled 8x and blurred, then sampled MAGNIFIED
       (mag=2).  At down=8 even the brightest star (peak 214) spreads over 64
       pixels, i.e. +3 of value: the dust is gone by construction, and what is
       left is genuine low-frequency cloud.  Its luminance is then NORMALISED PER
       TILE (own mean removed, contrast scaled to `amp`) and painted in one fixed
       sky hue -- without that step the 8 variants have visibly different mean
       brightness and a field reads as a quilt of 8 stamps rather than one sky.
     * stars -- local maxima of the ORIGINAL art (37 of them, peaks 95..214) are
       extracted at native size WITH their painted 4-point diffraction spikes and
       halo, then stamped 1..5 per tile at hashed positions.  So the stars are
       still the user's art, pixel for pixel; only their density changed.
     Result: ~3 stars per hex instead of ~33, each one an actual sparkle.
  2. CHASM: the starfield is gone (per the user -- Chasm should read as a very
     deeply darkened sea, not a second sky).  The 16 shipped surface-water tiles
     are copied 1:1 -- no resampling at all, so the wave texture stays exactly as
     the artist drew it -- and re-graded.  Note the grade is NOT the v1 style
     `V' = floor + slope*V`: that buries the waves, because at V~0.15 the crests
     and troughs quantise into the same RGB565 step.  Instead the tile's own mean
     is removed and the detail is EXPANDED about a very low base, so the field
     mean sits far below open water (0.37) and the map's shadow overlays (0.28)
     while the wave structure keeps its contrast.

Usage:
  build_chasm_sky_art.py             -- dry run: report what would change
  build_chasm_sky_art.py --apply     -- splice the tiles and fix the CRC
  build_chasm_sky_art.py --preview   -- PNG of the new tiles + a hex-field mosaic
  build_chasm_sky_art.py --export    -- write import-ready BMPs to Zigmod/ instead
Auto-backup to Release/Release.hss.pre-chasmskyart (kept from the v1 run, so it is
still the pristine pre-art file).  Close AoW.exe / AoWCompat.exe / AoWDevEd.exe
first -- all three lock the file.  Needs: pip install pillow
"""
import argparse, colorsys, os, re, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
from ilb import parse                                                  # noqa: E402
from ilb_rle16 import (decode, encode, reskin,                          # noqa: E402
                       rgb_to_rgb565, rgb565_to_rgb)
import hss_crc                                                         # noqa: E402

HSS = os.path.join(GAME, "Release", "Release.hss")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(HSS) + ".pre-chasmskyart")
ART = os.path.join(GAME, "Zigmod")
WATERHEX = os.path.join(GAME, "Images", "Waterhex.ILB")

# ---------------------------------------------------------------------------
# CONFIG.  Sky's field targets (V 0.30 / S 0.49 / hue 242deg) are the ones the
# 2026-07-27 pass measured against the user's live map: map deep water V 0.37
# S 0.53 hue 220deg, land S 0.41-0.48, shadow overlays 0.28, and saturated colour
# reserved for small magical accents.  Sky therefore parks between the shadows and
# open water; Chasm sits well BELOW both, which is what makes it read as a hole.
CREAM = (238, 234, 216)          # the map's accent register: bright, never white
TARGETS = {
    0x0B: dict(tile="Hu_wl.BMP", label="CHASM", out="Chasm_tile.bmp", mode="water",
               # "abyss" depth, chosen by the user 2026-07-30 over the shallower
               # V 0.155 / contrast 1.40 candidate
               base_v=0.115, contrast=1.20, sat=0.55, hue_shift=8.0, grain=0.012),
    0x0E: dict(tile="H_co.BMP", label="SKY", out="Sky_tile.bmp", mode="stars",
               art="Sky.bmp", down=8, blur=1.2, mag=2.0,
               hue=242.0, sat=0.49, base_v=0.30, amp=0.045, grain=0.030,
               count=4, vary=True, big_pct=65, gain=0.70, gain_big=1.00,
               star_min=95, seed=23,
               # THE 85/15 SPLIT (user, 2026-07-30): most hexes are the calm new
               # sky, but a minority keep the v1 dense starfield so the field
               # occasionally shows a star-cluster hex.  `GetRndResource` picks
               # among the 8 variants with equal weight, so one dense tile = 12.5%,
               # the closest 8 slots can get to 15%.  The dense tiles also get
               # `dense_stars` stamped crosses, so the two designs read as related.
               dense={7}, dense_stars=2,
               v1=dict(shrink=2, boost=2.10, floor=0.168, slope=0.55, sat=0.669,
                       hue_shift=14.3, grain=0.055, star_t=0.55, halo=0.45)),
}


def hashf(*a):
    """Deterministic 32-bit mix -- no RNG anywhere, so output is reproducible."""
    x = 0x9E3779B9
    for v in a:
        x = (x ^ ((v & 0xFFFFFFFF) * 0x85EBCA6B)) & 0xFFFFFFFF
        x = ((x << 13) | (x >> 19)) & 0xFFFFFFFF
        x = (x * 0xC2B2AE35) & 0xFFFFFFFF
    return x


def walk_rows(raw, clipw, cliph, transparent):
    """General item walk -> list of rows (clipw entries, None = transparent).
    Stops at the first row that does not total exactly clipw pixels, so a
    partially-corrupt tile yields the prefix that IS well formed."""
    rows, pos = [], 0
    while pos + 4 <= len(raw) and len(rows) < cliph:
        reclen = struct.unpack_from("<I", raw, pos)[0]
        if reclen < 4 or pos + reclen > len(raw):
            break
        a, b = pos + 4, pos + reclen
        p, px = a, []
        while p < b:
            if b - p >= 4 and struct.unpack_from("<H", raw, p)[0] == transparent:
                px += [None] * (struct.unpack_from("<H", raw, p + 2)[0] // 2); p += 4
            else:
                px.append(struct.unpack_from("<H", raw, p)[0]); p += 2
        if len(px) != clipw:
            break
        rows.append(px); pos += reclen
    return rows


def rebuild_malformed(raw, clipw, cliph, transparent, sample, target_size):
    """Rebuild a tile whose RLE chain is only partly well formed.

    Retained as a fallback only -- since the 4-byte record alignment was
    understood (2026-07-27) every shipped hexagon tile parses, so this path is not
    exercised.  A hexagon is vertically symmetric, so the valid top half is
    mirrored to make the bottom half, the result is painted, and the encoding is
    nudged to the ORIGINAL byte size (mandatory -- the payload must not change
    length):
      * one full-width row inset by 1px on each side  -> +4 bytes (gains 2 markers)
      * one margined row narrowed by 1px on each side -> -4 bytes
    Widths always stay exactly clipw, which is what the engine blits."""
    rows = walk_rows(raw, clipw, cliph, transparent)
    if len(rows) < 2:
        raise ValueError(f"only {len(rows)} usable rows")
    full = rows + [list(r) for r in reversed(rows)][:cliph - len(rows)]
    if len(full) != cliph:
        raise ValueError(f"mirrored to {len(full)} rows, need {cliph}")
    painted = [[None if v is None else sample(x, y) for x, v in enumerate(r)]
               for y, r in enumerate(full)]
    def size():
        return len(encode(painted, transparent))
    guard = 0
    while size() != target_size and guard < 200:
        guard += 1
        if size() < target_size:                      # need +4: inset a full row
            i = next((k for k, r in enumerate(painted)
                      if r[0] is not None and r[-1] is not None), None)
            if i is None:
                raise ValueError("no full-width row left to inset")
            painted[i][0] = painted[i][-1] = None
        else:                                          # need -4: narrow a row
            i = max(range(len(painted)),
                    key=lambda k: sum(1 for v in painted[k] if v is not None))
            span = [k for k, v in enumerate(painted[i]) if v is not None]
            if len(span) < 4:
                raise ValueError("cannot narrow further")
            painted[i][span[0]] = painted[i][span[-1]] = None
    if size() != target_size:
        raise ValueError(f"got {size()}, want {target_size}")
    return encode(painted, transparent)


def find_blobs(data):
    """Yield (blob_start, filelen, terrain) for each embedded hexagon-resource ILB.
    Signature: a 1-entry TTerrainList `01 00 00 00 <terrain> <overlay>` right before
    the `\\x04ILB\\0` magic; hexagon tiles carry overlay 0xFE (roads use 4,
    bridges 5)."""
    for m in re.finditer(rb"\x04ILB\x00", data):
        s = m.start()
        if data[s-6:s-2] != b"\x01\x00\x00\x00":
            continue
        yield s, struct.unpack_from("<I", data, s+20)[0], data[s-2]


# ---------------------------------------------------------------------------
# SKY: nebula + stamped stars
class SkyArt:
    """Loads the source once and caches the nebula map and the star catalogue.

    Two sub-modes: the v2 nebula+stamped-stars tile, and the v1 dense starfield
    for the indices in cfg["dense"] (see the 85/15 note on TARGETS)."""

    def __init__(self, cfg):
        from PIL import Image, ImageFilter
        self.cfg = cfg
        self.src = Image.open(os.path.join(ART, cfg["art"])).convert("RGB")
        self._maxpool = {}
        w, h = self.src.size[0] // cfg["down"], self.src.size[1] // cfg["down"]
        neb = self.src.resize((w, h), Image.BOX)
        if cfg["blur"]:                    # wrap-pad so the blur stays tileable
            pad = 4
            big = Image.new("RGB", (w + 2*pad, h + 2*pad))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    big.paste(neb, (pad + dx*w, pad + dy*h))
            neb = big.filter(ImageFilter.GaussianBlur(cfg["blur"])).crop(
                (pad, pad, pad + w, pad + h))
        self.neb = neb.load()
        self.nw, self.nh = neb.size
        self.px = self.src.load()
        self.sw, self.sh = self.src.size
        self.stars = self._find_stars(cfg["star_min"])
        self._patches = {}

    def _find_stars(self, min_v, radius=3):
        """Local maxima brighter than min_v -> [(x, y, peak)], brightest first."""
        px, W, H = self.px, self.sw, self.sh
        out = []
        for y in range(H):
            for x in range(W):
                v = max(px[x, y])
                if v < min_v:
                    continue
                top = True
                for dy in range(-radius, radius + 1):
                    for dx in range(-radius, radius + 1):
                        if (dx or dy) and max(px[(x+dx) % W, (y+dy) % H]) > v:
                            top = False; break
                    if not top:
                        break
                if top:
                    out.append((x, y, v))
        out.sort(key=lambda t: -t[2])
        return out

    def patch(self, sx, sy, half=4):
        """The star's own painted shape (spikes + halo) as an additive patch,
        with its local background subtracted so only the star is carried over."""
        key = (sx, sy, half)
        if key in self._patches:
            return self._patches[key]
        px, W, H = self.px, self.sw, self.sh
        ring = [max(px[(sx+dx) % W, (sy+dy) % H])
                for dy in (-half, half) for dx in range(-half, half + 1)]
        bg = sorted(ring)[len(ring) // 2]
        out = {}
        for dy in range(-half, half + 1):
            for dx in range(-half, half + 1):
                r, g, b = px[(sx+dx) % W, (sy+dy) % H]
                m = max(r, g, b) - bg
                if m <= 2:
                    continue
                k = m / max(1, 255 - bg)
                out[(dx, dy)] = (r*k, g*k, b*k)
        self._patches[key] = out
        return out

    def _cloud(self, ox, oy, x, y):
        mag, nw, nh = self.cfg["mag"], self.nw, self.nh
        fx, fy = ox + x/mag, oy + y/mag
        x0, y0 = int(fx) % nw, int(fy) % nh
        x1, y1 = (x0+1) % nw, (y0+1) % nh
        tx, ty = fx - int(fx), fy - int(fy)
        t = 0.0
        for xx, yy, wgt in ((x0, y0, (1-tx)*(1-ty)), (x1, y0, tx*(1-ty)),
                            (x0, y1, (1-tx)*ty), (x1, y1, tx*ty)):
            t += max(self.neb[xx, yy]) * wgt
        return t / 255.0

    # ---- v1 dense starfield (the minority variant) -------------------------
    def _pooled(self, shrink):
        """Max-pool the source: keeps single-pixel stars crisp where plain
        averaging would smear them away, and multiplies how many land in one
        48x32 window -- which is exactly what makes this variant DENSE."""
        from PIL import Image
        if shrink in self._maxpool:
            return self._maxpool[shrink]
        if shrink <= 1:
            out = self.src
        else:
            w, h = self.src.size[0]//shrink, self.src.size[1]//shrink
            sp = self.src.load(); out = Image.new("RGB", (w, h))
            for y in range(h):
                for x in range(w):
                    best = (0, 0, 0)
                    for dy in range(shrink):
                        for dx in range(shrink):
                            p = sp[x*shrink+dx, y*shrink+dy]
                            if sum(p) > sum(best):
                                best = p
                    out.putpixel((x, y), best)
        self._maxpool[shrink] = out
        return out

    def dense_tile(self, mask, idx):
        """The v1 look, byte-for-byte the same recipe that shipped 2026-07-27:
        window-sample the max-pooled art, lift the black floor, mute the
        saturation, step away from the water hue, hash-dither, cap stars to CREAM
        and give them a 45% halo on 4-neighbours."""
        c = self.cfg["v1"]
        src = self._pooled(c["shrink"])
        sw, sh = src.size; sp = src.load()
        ox, oy = (idx*977) % sw, (idx*613) % sh
        boost, hshift = c["boost"], c["hue_shift"]/360.0
        star_t, halo = c["star_t"], c["halo"]

        def raw(x, y):
            r, g, b = sp[(ox+x) % sw, (oy+y) % sh]
            return (min(255, int(r*boost)), min(255, int(g*boost)),
                    min(255, int(b*boost)))

        def is_star(p):
            return max(p) / 255.0 > star_t

        H, W = len(mask), len(mask[0])
        buf = [[None]*W for _ in range(H)]
        for y in range(H):
            for x in range(W):
                if mask[y][x] is None:
                    continue
                r, g, b = raw(x, y)
                if is_star((r, g, b)):
                    r = r*0.25 + CREAM[0]*0.75
                    g = g*0.25 + CREAM[1]*0.75
                    b = b*0.25 + CREAM[2]*0.75
                    buf[y][x] = [r, g, b]
                    continue
                h, sv, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
                v = c["floor"] + c["slope"]*v
                n = ((x*73856093 ^ y*19349663 ^ idx*83492791) & 0xFFFF) / 0xFFFF
                v = min(1.0, max(0.0, v + (n-0.5)*2.0*c["grain"]))
                r, g, b = colorsys.hsv_to_rgb((h + hshift) % 1.0,
                                              min(1.0, sv*c["sat"]), v)
                r, g, b = r*255, g*255, b*255
                if any(is_star(raw(x+dx, y+dy))
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    r = r*(1-halo) + CREAM[0]*0.62*halo
                    g = g*(1-halo) + CREAM[1]*0.62*halo
                    b = b*(1-halo) + CREAM[2]*0.62*halo
                buf[y][x] = [r, g, b]
        self._stamp(buf, mask, idx, self.cfg.get("dense_stars", 0))
        return finish(buf, mask)

    # ---- shared -----------------------------------------------------------
    def _stamp(self, buf, mask, idx, k):
        """Stamp k of the artwork's own stars, at native size, spikes and all."""
        cfg = self.cfg
        H, W = len(mask), len(mask[0])
        for j in range(k):
            h = hashf(idx, j, cfg["seed"])
            sx, sy, _peak = self.stars[h % len(self.stars)]
            cx = 6 + (h >> 8) % (W - 12)
            cy = 5 + (h >> 16) % (H - 10)
            big = (j == 0 and (h >> 24) % 100 < cfg["big_pct"])
            gain = cfg["gain_big"] if big else cfg["gain"]
            for (dx, dy), add in self.patch(sx, sy).items():
                x, y = cx + dx, cy + dy
                if not (0 <= x < W and 0 <= y < H) or buf[y][x] is None:
                    continue
                p = buf[y][x]
                for i in range(3):
                    p[i] = min(255.0, p[i] + add[i]*gain*(CREAM[i]/255.0))

    def tile(self, mask, idx):
        """mask: decoded tile rows (None = transparent) -> rows of rgb565/None."""
        cfg = self.cfg
        if idx in cfg.get("dense", ()):
            return self.dense_tile(mask, idx)
        H, W = len(mask), len(mask[0])
        ox, oy = (idx*37) % self.nw, (idx*61) % self.nh
        cl = {(x, y): self._cloud(ox, oy, x, y)
              for y in range(H) for x in range(W) if mask[y][x] is not None}
        mean = sum(cl.values()) / len(cl)
        spread = (max(cl.values()) - min(cl.values())) or 1.0
        hue, sat = cfg["hue"]/360.0, cfg["sat"]
        buf = [[None]*W for _ in range(H)]
        for (x, y), v0 in cl.items():
            n = (hashf(x, y, idx) & 0xFFFF) / 0xFFFF
            v = cfg["base_v"] + (v0-mean)/spread*cfg["amp"] + (n-0.5)*2*cfg["grain"]
            buf[y][x] = [c*255 for c in
                         colorsys.hsv_to_rgb(hue, sat, max(0.0, min(1.0, v)))]
        k = cfg["count"]
        if cfg.get("vary"):     # a fixed count per hex draws a visible grid
            k = max(0, k - 1 + (hashf(idx, 99, cfg["seed"]) % 3))
        self._stamp(buf, mask, idx, k)
        return finish(buf, mask)


# ---------------------------------------------------------------------------
# CHASM: the shipped surface-water tiles, re-graded to an abyss
def water_tiles():
    """The 16 `H_Wa2.BMP` 48x32 water tiles (ids 140..155 of Waterhex.ILB) as RGB
    rows, None = transparent.  Read-only: Waterhex.ILB is never written here."""
    d = open(WATERHEX, "rb").read()
    r = parse(d)
    out = []
    for im_ in r["images"]:
        if not (140 <= im_["id"] <= 155) or im_["type"] != 17:
            continue
        raw = d[r["hdr"]["imgdir"] + im_["offset"]:][:im_["size"]]
        rows, _ = decode(raw, im_.get("clipw", im_["w"]),
                         im_.get("cliph", im_["h"]), im_["transparent"])
        out.append([[None if v is None else rgb565_to_rgb(v) for v in row]
                    for row in rows])
    if not out:
        raise RuntimeError(f"no H_Wa2 tiles found in {WATERHEX}")
    return out


class ChasmArt:
    def __init__(self, cfg):
        self.cfg = cfg
        self.water = water_tiles()

    def tile(self, mask, idx):
        cfg = self.cfg
        src = self.water[idx % len(self.water)]
        H, W = len(mask), len(mask[0])
        sh, sw = len(src), len(src[0])

        def at(x, y):
            p = src[y % sh][x % sw]
            if p is None:            # water tile's own margin -> mirror inward
                p = src[y % sh][max(0, min(sw-1, sw-1-x))] or (40, 52, 78)
            return p

        hsv = {(x, y): colorsys.rgb_to_hsv(*[c/255 for c in at(x, y)])
               for y in range(H) for x in range(W) if mask[y][x] is not None}
        vmean = sum(t[2] for t in hsv.values()) / len(hsv)
        buf = [[None]*W for _ in range(H)]
        for (x, y), (h, s, v) in hsv.items():
            n = (hashf(x, y, idx) & 0xFFFF) / 0xFFFF
            v = cfg["base_v"] + (v-vmean)*cfg["contrast"] + (n-0.5)*2*cfg["grain"]
            r, g, b = colorsys.hsv_to_rgb((h + cfg["hue_shift"]/360.0) % 1.0,
                                          min(1.0, s*cfg["sat"]),
                                          max(0.0, min(1.0, v)))
            buf[y][x] = [r*255, g*255, b*255]
        return finish(buf, mask)


def finish(buf, mask):
    """Clamp to the map's accent register (never pure white) and pack to rgb565."""
    H, W = len(mask), len(mask[0])
    rows = []
    for y in range(H):
        row = []
        for x in range(W):
            if mask[y][x] is None or buf[y][x] is None:
                row.append(None); continue
            r, g, b = (int(v) for v in buf[y][x])
            m = max(r, g, b)
            if m > 238:
                r, g, b = (v*238//m for v in (r, g, b))
            row.append(rgb_to_rgb565(r, g, b))
        rows.append(row)
    return rows


def make_art(cfg):
    return SkyArt(cfg) if cfg["mode"] == "stars" else ChasmArt(cfg)


# ---------------------------------------------------------------------------
def tile_to_image(rows, key_rgb):
    from PIL import Image
    w, h = len(rows[0]), len(rows)
    im = Image.new("RGB", (w, h), key_rgb)
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if v is not None:
                im.putpixel((x, y), rgb565_to_rgb(v))
    return im


def tile_to_rgba(rows):
    from PIL import Image
    w, h = len(rows[0]), len(rows)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if v is not None:
                im.putpixel((x, y), rgb565_to_rgb(v) + (255,))
    return im


def field_mosaic(tiles, nx=14, ny=8, bg=(46, 34, 26)):
    """A real hex field -- the only way star/wave frequency can be judged.

    Placement is the engine's own `HSEngine.HXtoHP` (HSEPack 5560E3B4):
        px = hx*32 + 8 ;  py = hy*32 + (hx & 1)*16
    i.e. pitch 32 with odd columns pushed down 16.  Note the tile is a hexagon of
    area 1056 px (rows widen 18->48 and back) while the lattice cell is only
    32*32 = 1024, so **neighbouring hexes overlap slightly** -- do not "fix" the
    pitch to 33 to make the areas match: that is geometrically seamless but not
    what the engine does, and it leaves hairline gaps where the engine has none."""
    from PIL import Image
    W = nx*32 + 8 + 48
    H = ny*32 + 16 + 32
    out = Image.new("RGB", (W, H), bg)
    for hx in range(nx):
        for hy in range(ny):
            t = tiles[hashf(hx, hy, 7) % len(tiles)]
            out.paste(t, (hx*32 + 8, hy*32 + (hx & 1)*16), t)
    return out


def collect(data):
    """-> {terrain: [(abs_data_offset, raw, clipw, cliph, transparent)]} in the
    order the blobs appear, which is the index that drives variant selection."""
    found = {t: [] for t in TARGETS}
    skipped = []
    for s, flen, terrain in find_blobs(data):
        cfg = TARGETS.get(terrain)
        if not cfg:
            continue
        blob = bytes(data[s:s+flen])
        try:
            r = parse(blob)
        except Exception as e:
            skipped.append((terrain, s, f"ILB parse: {e}")); continue
        for im_ in r["images"]:
            if im_["type"] != 17 or im_["name"].upper() != cfg["tile"].upper():
                continue
            doff = r["hdr"]["imgdir"] + im_["offset"]
            found[terrain].append((s + doff, blob[doff:doff+im_["size"]],
                                   im_.get("clipw", im_["w"]),
                                   im_.get("cliph", im_["h"]), im_["transparent"]))
    return found, skipped


def do_export(data):
    """Write import-ready 48x32 BMPs for manual AoWDevEd import."""
    found, _ = collect(data)
    for terrain, cfg in TARGETS.items():
        if not found[terrain]:
            print(f"  {cfg['label']}: no tile found"); continue
        art = make_art(cfg)
        off, raw, cw, ch, tr = found[terrain][0]
        mask, _ = decode(raw, cw, ch, tr)
        rows = art.tile(mask, 0)
        p = os.path.join(ART, cfg["out"])
        key = rgb565_to_rgb(tr)
        tile_to_image(rows, key).save(p)
        print(f"  {cfg['label']:5} -> {p}  (48x32, key colour "
              f"#{key[0]:02X}{key[1]:02X}{key[2]:02X} = transparent {tr:#06x})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--rebuild-malformed", action="store_true",
                    help="EXPERIMENTAL fallback for tiles whose RLE chain will not "
                         "parse; not needed since the 4-byte record alignment was "
                         "understood (every shipped tile parses).")
    args = ap.parse_args()

    data = bytearray(open(HSS, "rb").read())
    if not hss_crc.verify(bytes(data)):
        print(f"ABORT: {os.path.basename(HSS)} already has a BAD CRC "
              f"(stored {hss_crc.stored_crc(bytes(data)):#010x}, "
              f"computed {hss_crc.crc_of(bytes(data)):#010x}) -- restore it first")
        return 1
    if args.export:
        do_export(bytes(data)); return 0

    found, skipped = collect(bytes(data))
    edits, previews = [], {}
    for terrain, cfg in TARGETS.items():
        art = make_art(cfg)
        tiles = []
        for idx, (off, raw, cw, ch, tr) in enumerate(found[terrain]):
            try:
                mask, _ = decode(raw, cw, ch, tr)
                rows = art.tile(mask, idx)
                new_raw = reskin(raw, ch, tr, lambda x, y: rows[y][x])
            except Exception as e:
                if not args.rebuild_malformed:
                    skipped.append((terrain, off, f"{cfg['tile']}[{idx}]: {e}"))
                    continue
                try:
                    mask = [[0]*cw for _ in range(ch)]
                    rows = art.tile(mask, idx)
                    new_raw = rebuild_malformed(raw, cw, ch, tr,
                                                lambda x, y: rows[y][x], len(raw))
                except Exception as e2:
                    skipped.append((terrain, off, f"{cfg['tile']}[{idx}]: {e} / "
                                                  f"rebuild: {e2}"))
                    continue
            assert len(new_raw) == len(raw), "payload length changed"
            tiles.append(rows)
            if new_raw != raw:
                edits.append((off, len(raw), new_raw))
        previews[terrain] = tiles
        print(f"  {cfg['label']:5} (terrain {terrain:#04x}, {cfg['tile']}, "
              f"mode={cfg['mode']}): {len(found[terrain])} tiles, "
              f"{len(tiles)} re-skinned")
    if skipped:
        print(f"  {len(skipped)} tile(s) left with their original art:")
        for terrain, s, why in skipped[:6]:
            print(f"    terrain {terrain:#04x} @{s}: {why}")

    if args.preview:
        from PIL import Image
        outdir = os.environ.get("SCRATCH", ART)
        for terrain, cfg in TARGETS.items():
            rgba = [tile_to_rgba(r) for r in previews[terrain]]
            if not rgba:
                continue
            strip = Image.new("RGB", (len(rgba)*50, 32), (30, 30, 30))
            for i, t in enumerate(rgba):
                strip.paste(t, (i*50, 0), t)
            strip = strip.resize((strip.width*3, strip.height*3), Image.NEAREST)
            mos = field_mosaic(rgba)
            sheet = Image.new("RGB", (max(strip.width, mos.width),
                                      strip.height + mos.height + 6), (30, 30, 30))
            sheet.paste(strip, (0, 0)); sheet.paste(mos, (0, strip.height + 6))
            p = os.path.join(outdir, f"chasm_sky_{cfg['label'].lower()}.png")
            sheet.save(p)
            print(f"  preview -> {p}")
        return 0

    if not edits:
        print("  tiles already carry this art (idempotent no-op)"); return 0
    print(f"  {len(edits)} tile payload(s) to rewrite, all same-size "
          f"({sum(e[1] for e in edits)} bytes), then CRC repair")
    if not args.apply:
        print("dry run - re-run with --apply to write"); return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(HSS, BACKUP); print(f"  backup -> {os.path.basename(BACKUP)}")
    for off, ln, new in edits:
        data[off:off+ln] = new
    before = hss_crc.stored_crc(bytes(data))
    data = bytearray(hss_crc.fix(bytes(data)))
    after = hss_crc.stored_crc(bytes(data))
    assert hss_crc.verify(bytes(data)), "CRC repair failed"
    try:
        open(HSS, "wb").write(bytes(data))
    except PermissionError:
        print("LOCKED - close AoW.exe / AoWCompat.exe / AoWDevEd.exe and retry")
        return 1
    print(f"applied: {len(edits)} tiles re-skinned; CRC {before:#010x} -> "
          f"{after:#010x}; file size unchanged ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
