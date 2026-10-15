#!/usr/bin/env python3
r"""
build_sky_mosaic.py -- TRIAL: cloudy Sky (terrain 0xE) from the 8x8 mosaic.  AoWEPACK.dpl +
Release/Release.hss.  Owner request 2026-10-15: slot in Graphic_resources/mosaic_8x8 as a temporary
Sky, keeping the starry Sky.  --undo restores both files to the starry Sky byte for byte.

STATUS: REVERTED 2026-10-15 (owner did not like it as terrain; may reuse it later as an overlay).
Last build: graded, sharpened, drifting.  --undo restored both files to their earlier hashes.

SOURCE
    Modding Resources/Graphic_resources/mosaic_8x8/sky_c<C>_r<R>.png: 64 tiles, 48x32 RGBA, alpha
    0/255, silhouette identical to the shipped Sky tile (1056 opaque pixels).  The tiles form ONE
    seamless picture when hex (hx, hy) shows tile C = hx mod 8, R = hy mod 8 at the engine's own
    placement; the field repeats every 8 hexes both ways.  The PNGs are never modified.

GRADE (owner request 2026-10-15: match the original game's palette)
    The terrain art is 16-bit, so the game has no palette as such; the target is the colours of
    the vanilla hexagon tiles in the ROOT Release.hss.  Each pixel's luminance (contrast x1.3
    about the mosaic's mean) is looked up in a ramp built from vanilla Water, Ice, cave ice, Coast
    and Snow: per luminance bin the median vanilla colour.  Shadows come out Ice-blue, highlights
    Snow's lavender-white; mean brightness is kept.  Snapping each pixel to a colour that occurs
    in vanilla terrain was tried and rejected: vanilla has only ~25-40 colours in this range, so
    the soft clouds posterise into blotches.  Colours go to RGB565 by truncation.

SHARPENING (owner 2026-10-15, after seeing it live: too blurry)
    Measured fine detail (luminance sd after removing a sigma-1 blur): source clouds 0.5, vanilla
    Water/Coast 3.4, Ice 5.0, Snow 8.4, Grass 16.  Two steps, both before the ramp:
    - unsharp mask x2.5 (sigma 2.5) on the WHOLE picture as one periodic 256x256 canvas, so it
      sees across hex edges (per tile it drew faint hex outlines);
    - the game's own grain: the high-pass (sigma 2) of a vanilla Snow tile, chosen per mosaic tile
      ((C*3 + R*5) mod 8), at luminance sd 6.  Snow tiles share the Sky silhouette.
    Grain alone read as noise over blur; sharpening alone stayed smooth.  The sharpening also
    brings out faint seams already in the source picture.

WHY POSITION-KEYED, AND WHY AN OVERLAY
    The engine picks a hexagon's art with GetRndResource (equal weights, no position), so 64
    variants in Release.hss would scatter the pieces at random.  Land hexagons are painted once
    into the cached static scene, so the tile is chosen by map position in the dynamic pass,
    exactly as build_sky_anim.py's trial chose a frame by time (mechanism proved live there).

HOW
    The graded picture is stored once, as the periodic 256x256 canvas (8x8 hexes), not as 64 tiles.
    1. Release.hss: all 8 Sky variants (`H_co.BMP`, RLESprite16) are re-skinned in place with the
       canvas under hex (0,0) at drift 0 (the "base tile").  RLE size depends only on the
       silhouette, so every record keeps its length; CRC repaired.  If the overlay ever does not
       run, Sky shows the base tile on every hex, still.
    2. AoWEPACK.dpl: hook TAoWHSMap.DrawDynamicScene's entry 0x55778A60 (6 B, prologue replayed;
       no .reloc, nothing jumps inside) -> cave_sky.  Once per call it reads the drift
       s = (tick ms / 100) mod 256 from KUSER_SHARED_DATA (0x7FFE0320 x 0x7FFE0004 >> 24, a fixed
       system address, no .reloc -- build_sky_anim.py's clock).  It walks the visible hexes of the
       live map ([MAPVAR]) on the shown level; for every field whose terrain byte is 0xE, world
       origin (wx, wy) = (hx*32, hy*32 + (hx&1)*16), it blits at (wx - [map+0x80], wy - [map+0x84]):
       hex pixel (x, y) becomes canvas[(wy+y)&255][(wx+x-s)&255], so the picture drifts 1 px to
       the RIGHT every 100 ms and loops every 25.6 s (owner request 2026-10-15: drift left to
       right like the old trial).  A pixel is replaced ONLY where the back buffer still holds the
       base tile's pixel -- plain Sky; curtains, fades, bridges, pads and neighbours' transitions
       drawn over Sky are left alone.  Neighbouring hexes sample the same world pixel where they
       overlap, so there is no seam at any drift.  RGB565 and RGB555 surfaces each get their own
       canvas and base table (555 via ILPACK's remap, to555).  Surface descriptor, map fields and
       clipping are build_sky_anim.py's; see its docstring.
    Data at DATA_VA: spans (32 x L,R bytes, padded to 0x40), canvas 565 (256 rows x 512 B),
    canvas 555, base tile 565 (1056 px over the spans), base tile 555.  Ends 0x558940C0.

Rolls: none (display only).  PIC: rel32 + load-delta for module data.
Slot 0x55852200..0x55899FFF (AoWEPACK CODE), exclusive; taken over from build_sky_anim.py.
COUPLING: build_sky_anim.py uses the same hook, slot and Sky tiles -- the two are mutually
exclusive and each aborts on the other's bytes.  The edge art (build_skychasm_edges.py: water
dissolves, cliff curtains) was blended toward the starry tile and is not rebuilt here.
UNPROVEN RISK: AoWz.exe was not measured redrawing the dynamic layer each frame; if it does not,
the game shows the base tile on every Sky hex.  The drift build was not driven live (the still
build was, in AoWzEd); the per-pixel loop is longer than the trial's.
"""
import argparse
import glob
import os
import struct
import sys

sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm
import build_sky_anim as A

GAME = P.GAME
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import hexfield  # noqa: E402
import hss_crc  # noqa: E402
from ilb_rle16 import decode, reskin, rgb_to_rgb565  # noqa: E402

HSS = A.HSS
VANILLA_HSS = os.path.join(os.path.dirname(GAME), "Release", "Release.hss")
TILES = os.path.join(GAME, "Modding Resources", "Graphic_resources", "mosaic_8x8")
SKY = A.SKY
N = 8                                    # mosaic period, both axes
RAMP_TERRAINS = (0, 6, 0xD, 0xE, 3)      # vanilla Water, Ice, cave ice, Coast, Snow
CONTRAST = 1.3                           # picked from previews of 1.0 / 1.3 / 1.6
UNSHARP, UNSHARP_SIGMA = 2.5, 2.5        # picked from previews (owner: 1.0 was too blurry)
GRAIN, GRAIN_SIGMA = 6.0, 2.0            # Snow grain, in luminance sd (vanilla Snow 8.4, Ice 5.0)

HOOK, HOOK_ORIG, RESUME = A.HOOK, A.HOOK_ORIG, A.RESUME
SLOT, CAVE, DATA_VA, CANVAS_VA = A.SLOT, A.CAVE, A.DATA_VA, A.FRAMES_VA
P8 = N * 32                              # canvas side in px: the mosaic's period
DRIFT_MS = 100                           # 1 px to the right per 100 ms, as build_sky_anim.py
MAPVAR, GETLVL, FMT565, FMT555 = A.MAPVAR, A.GETLVL, A.FMT565, A.FMT555


# ----------------------------------------------------------------- art
def lum(a):
    return a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114


def game_ramp(T):
    """luminance -> RGB ramp of the vanilla cool terrains (RAMP_TERRAINS): per luminance bin the
    median colour, smoothed along the ramp.  Returns (bin luminances, colours)."""
    import numpy as np
    px = np.concatenate([(lambda a: a[a[..., 3] > 0][:, :3])(np.array(im))
                         for t in RAMP_TERRAINS for im in T[t]]).astype(float)
    L = lum(px)
    edges = np.linspace(np.percentile(L, 1), np.percentile(L, 99.5), 65)
    cols, ls = [], []
    for i in range(64):
        m = (L >= edges[i]) & (L < edges[i + 1])
        if m.sum() >= 8:
            cols.append(np.median(px[m], 0))
            ls.append(L[m].mean())
    k = np.array([1, 2, 3, 2, 1], float) / 9
    pad = np.pad(np.array(cols), ((2, 2), (0, 0)), mode="edge")
    return np.array(ls), np.stack([np.convolve(pad[:, c], k, "valid") for c in range(3)], 1)


def snow_grain(T):
    """high-pass luminance of each vanilla Snow tile (hex-masked Gaussian, GRAIN_SIGMA), scaled so
    the mean standard deviation over the tiles is 1."""
    import numpy as np
    from scipy import ndimage as nd
    out = []
    for im in T[3]:
        a = np.array(im).astype(float)
        m = (a[..., 3] > 0).astype(float)
        L = lum(a[..., :3])
        b = nd.gaussian_filter(L * m, GRAIN_SIGMA) / np.maximum(nd.gaussian_filter(m, GRAIN_SIGMA), 1e-6)
        out.append((L - b) * m)
    sd = np.mean([h[h != 0].std() for h in out])
    return [h / sd for h in out]


def load_tiles():
    import numpy as np
    from PIL import Image
    from scipy import ndimage as nd
    src = {}
    for r in range(N):
        for c in range(N):
            f = os.path.join(TILES, "sky_c%d_r%d.png" % (c, r))
            im = Image.open(f).convert("RGBA")
            assert im.size == (48, 32), f
            src[c, r] = np.array(im).astype(float)
    # 1. the whole picture as one periodic canvas (256x256 px = 8x8 hexes), so the sharpening sees
    #    across hex edges and adds no seams
    L = np.zeros((P8, P8))
    seen = np.zeros((P8, P8), bool)
    org = lambda c, r: (c * 32, r * 32 + (c & 1) * 16)
    for (c, r), a in src.items():
        ox, oy = org(c, r)
        ys, xs = np.nonzero(a[..., 3] > 0)
        L[(oy + ys) % P8, (ox + xs) % P8] = lum(a[..., :3])[ys, xs]
        seen[(oy + ys) % P8, (ox + xs) % P8] = True
    assert seen.all(), "the mosaic does not cover its period"
    m0 = L.mean()
    # 2. unsharp mask (wrapping), then contrast about the mean
    L = L + UNSHARP * (L - nd.gaussian_filter(L, UNSHARP_SIGMA, mode="wrap"))
    L = (L - m0) * CONTRAST + m0
    # 3. the game's grain, pasted per hex into the canvas (each hex its own vanilla Snow tile),
    #    then every pixel through the game ramp
    T = hexfield.hss_tiles(VANILLA_HSS)
    RL, RC = game_ramp(T)
    grain = snow_grain(T)
    G = np.zeros((P8, P8))
    for r in range(N):
        for c in range(N):
            ox, oy = org(c, r)
            g = grain[(c * 3 + r * 5) % len(grain)]
            ys, xs = np.nonzero(src[c, r][..., 3] > 0)
            G[(oy + ys) % P8, (ox + xs) % P8] = g[ys, xs]
    l = L + GRAIN * G
    rgb = np.clip(np.stack([np.interp(l, RL, RC[:, k]) for k in range(3)], -1), 0, 255).astype(int)
    canvas = [[rgb_to_rgb565(*rgb[y, x]) for x in range(P8)] for y in range(P8)]
    # the static tile: the canvas under hex (0, 0) at drift 0
    a = src[0, 0]
    mask = [[bool(a[y, x, 3]) for x in range(48)] for y in range(32)]
    for (c, r), t in src.items():
        assert [[bool(t[y, x, 3]) for x in range(48)] for y in range(32)] == mask, \
            "sky_c%d_r%d: silhouette differs" % (c, r)
    base = [[canvas[y][x] if mask[y][x] else None for x in range(48)] for y in range(32)]
    assert len(glob.glob(os.path.join(TILES, "sky_c*_r*.png"))) == N * N
    return canvas, base, mask


# ----------------------------------------------------------------- code
def build_cave(canvas555, base565, base555):
    a_blit = CAVE + 0x200
    pop_at = CAVE + 9                    # pushad(1) + sub esp,0x30(3) + call(5)
    # frame: +0 map, +4 surface, +8 level, +10 col, +14 row end, +18 col end, +1C row,
    #        +20 canvas, +24 base tile, +28 drift (px)
    main = asm(f"""
        pushad
        sub  esp, 0x30
        call {pop_at:#x}
        pop  ebp
        sub  ebp, {pop_at:#x}
        mov  [esp], eax
        mov  [esp+4], edx
        test edx, edx
        jz   out
        cmp  [ebp + {MAPVAR:#x}], eax
        jne  out
        mov  ecx, [edx+0x28]
        lea  eax, [ebp + {CANVAS_VA:#x}]
        lea  esi, [ebp + {base565:#x}]
        cmp  ecx, {FMT565:#x}
        je   fmtok
        lea  eax, [ebp + {canvas555:#x}]
        lea  esi, [ebp + {base555:#x}]
        cmp  ecx, {FMT555:#x}
        jne  out
    fmtok:
        mov  [esp+0x20], eax
        mov  [esp+0x24], esi
        mov  eax, dword ptr [0x7FFE0320]
        mul  dword ptr [0x7FFE0004]
        shrd eax, edx, 24
        xor  edx, edx
        mov  ecx, {DRIFT_MS}
        div  ecx
        and  eax, {P8 - 1}
        mov  [esp+0x28], eax
        mov  eax, [esp]
        mov  edx, [eax+0x88]
        mov  eax, [eax+0x10]
        call {GETLVL:#x}
        test eax, eax
        jz   out
        mov  [esp+8], eax
        mov  eax, [esp]
        mov  ecx, [eax+0x94]
        mov  [esp+0x10], ecx
        add  ecx, [eax+0x9C]
        mov  [esp+0x18], ecx
    colloop:
        mov  ecx, [esp+0x10]
        cmp  ecx, [esp+0x18]
        jge  out
        mov  eax, [esp]
        mov  edx, [eax+0x98]
        mov  [esp+0x1C], edx
        add  edx, [eax+0xA0]
        mov  [esp+0x14], edx
    rowloop:
        mov  edx, [esp+0x1C]
        cmp  edx, [esp+0x14]
        jge  nextcol
        mov  ecx, [esp+0x10]
        mov  ebx, [esp+8]
        test ecx, ecx
        js   nextrow
        test edx, edx
        js   nextrow
        cmp  ecx, [ebx+0xC]
        jge  nextrow
        cmp  edx, [ebx+0x10]
        jge  nextrow
        mov  eax, [ebx+0x74]
        mov  eax, [eax+ecx*4]
        mov  esi, [ebx+0x78]
        add  eax, [esi+edx*4]
        cmp  byte ptr [eax+0x14], {SKY:#x}
        jne  nextrow
        mov  esi, ecx
        shl  esi, 5
        mov  edi, edx
        shl  edi, 5
        mov  ebx, ecx
        and  ebx, 1
        shl  ebx, 4
        add  edi, ebx
        mov  edx, edi
        mov  eax, esi
        sub  eax, [esp+0x28]
        mov  ebx, [esp]
        sub  esi, [ebx+0x80]
        sub  edi, [ebx+0x84]
        mov  ebx, [esp+4]
        mov  ecx, esp
        call {a_blit:#x}
    nextrow:
        inc  dword ptr [esp+0x1C]
        jmp  rowloop
    nextcol:
        inc  dword ptr [esp+0x10]
        jmp  colloop
    out:
        add  esp, 0x30
        popad
        push ebx
        push esi
        mov  esi, edx
        mov  ebx, eax
        jmp  {RESUME:#x}
    """, CAVE)
    assert CAVE + len(main) <= a_blit, "cave_sky outgrew its slot"
    # blit: esi/edi = screen origin of the hex, ebx = surface desc, eax = canvas column of the
    # hex's x=0 (world x - drift, unmasked), edx = canvas row of its y=0, ecx = caller's frame.
    # frame: +0 spans, +4 base cursor, +8 canvas, +C y, +10 sox, +14 soy, +18 cx0, +1C wy0,
    #        +20 span length, +24 span left, +28 canvas row, +2C saved ebx
    blit = asm(f"""
        pushad
        sub  esp, 0x30
        mov  [esp+0x10], esi
        mov  [esp+0x14], edi
        mov  [esp+0x18], eax
        mov  [esp+0x1C], edx
        mov  eax, [ecx+0x24]
        mov  [esp+4], eax
        mov  eax, [ecx+0x20]
        mov  [esp+8], eax
        lea  eax, [ebp + {DATA_VA:#x}]
        mov  [esp], eax
        mov  dword ptr [esp+0xC], 0
    brow:
        mov  ecx, [esp+0xC]
        cmp  ecx, 32
        jge  bdone
        mov  eax, [esp]
        movzx esi, byte ptr [eax+ecx*2]
        movzx edi, byte ptr [eax+ecx*2+1]
        mov  eax, edi
        sub  eax, esi
        mov  [esp+0x20], eax
        mov  [esp+0x24], esi
        mov  eax, [esp+0x14]
        add  eax, ecx
        cmp  eax, [ebx+0x14]
        jl   bnext
        cmp  eax, [ebx+0x1C]
        jge  bnext
        imul eax, [ebx+0xC]
        add  eax, [ebx+0x20]
        add  esi, [esp+0x10]
        add  edi, [esp+0x10]
        xor  edx, edx
        cmp  esi, [ebx+0x10]
        jge  c1
        mov  edx, [ebx+0x10]
        sub  edx, esi
        mov  esi, [ebx+0x10]
    c1:
        cmp  edi, [ebx+0x18]
        jle  c2
        mov  edi, [ebx+0x18]
    c2:
        mov  ecx, edi
        sub  ecx, esi
        jle  bnext
        lea  edi, [eax+esi*2]
        mov  esi, [esp+4]
        lea  esi, [esi+edx*2]
        mov  eax, [esp+0x1C]
        add  eax, [esp+0xC]
        and  eax, {P8 - 1}
        shl  eax, 9
        add  eax, [esp+8]
        mov  [esp+0x28], eax
        mov  eax, [esp+0x18]
        add  eax, [esp+0x24]
        add  eax, edx
        mov  edx, [esp+0x28]
        mov  [esp+0x2C], ebx
    inner:
        mov  bx, [edi]
        cmp  bx, [esi]
        jne  sk
        mov  ebx, eax
        and  ebx, {P8 - 1}
        mov  bx, [edx+ebx*2]
        mov  [edi], bx
    sk:
        add  edi, 2
        add  esi, 2
        inc  eax
        dec  ecx
        jnz  inner
        mov  ebx, [esp+0x2C]
    bnext:
        mov  eax, [esp+0x20]
        shl  eax, 1
        add  [esp+4], eax
        inc  dword ptr [esp+0xC]
        jmp  brow
    bdone:
        add  esp, 0x30
        popad
        ret
    """, a_blit)
    return [("cave_sky", CAVE, main), ("blit", a_blit, blit)]


def build_data(canvas, base, spans, transparent):
    """spans, canvas 565, canvas 555, base tile 565, base tile 555; returns (blob, VAs)."""
    sp = b"".join(bytes([l, r]) for l, r in spans).ljust(0x40, b"\0")
    flat = [v for row in canvas for v in row]
    c565 = struct.pack("<%dH" % len(flat), *flat)
    c555 = struct.pack("<%dH" % len(flat), *(A.to555(v, transparent) for v in flat))
    bpx = [v for y, (l, r) in enumerate(spans) for v in base[y][l:r]]
    b565 = struct.pack("<%dH" % len(bpx), *bpx)
    b555 = struct.pack("<%dH" % len(bpx), *(A.to555(v, transparent) for v in bpx))
    va555 = CANVAS_VA + len(c565)
    vab565 = va555 + len(c555)
    vab555 = vab565 + len(b565)
    return sp + c565 + c555 + b565 + b555, (va555, vab565, vab555)


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="TEMPORARY: cloudy Sky from the 8x8 mosaic")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    orig = [A.ORIG[i * len(A.ORIG) // 8:(i + 1) * len(A.ORIG) // 8] for i in range(8)]

    # --- art and blobs
    canvas, base, mask = load_tiles()
    spans = A.spans_of(mask)
    npx = sum(r - l for l, r in spans)
    transparent = {t[4] for t in A.sky_tiles(open(HSS, "rb").read())}
    assert len(transparent) == 1, "Sky tiles disagree on the transparent colour"
    transparent = transparent.pop()
    assert all(p != transparent for row in canvas for p in row), \
        "a mosaic pixel equals the transparent colour"
    data_blob, vas = build_data(canvas, base, spans, transparent)
    blobs = build_cave(*vas)
    blobs.append(("data", DATA_VA, data_blob))
    assert DATA_VA + len(data_blob) <= SLOT[1], "data overflows the slot"
    assert max(va + len(b) for n, va, b in blobs if n != "data") <= DATA_VA
    print("build_sky_mosaic: %dx%d canvas, %d px/hex, data %d B, slot %08X-%08X"
          % (P8, P8, npx, len(data_blob), SLOT[0], SLOT[1]))
    if a.dis:
        P.show([b for b in blobs if b[0] != "data"])

    # --- Release.hss state
    hss = bytearray(open(HSS, "rb").read())
    if not hss_crc.verify(bytes(hss)):
        sys.exit("ABORT: Release.hss already has a bad CRC -- find out why first")
    hss_tiles = A.sky_tiles(hss)
    assert len(hss_tiles) == 8, "expected 8 Sky tiles, found %d" % len(hss_tiles)
    ours = []
    for i, (off, cur, w, h, tr) in enumerate(hss_tiles):
        assert (w, h) == (48, 32) and len(cur) == len(orig[i])
        rows, _ = decode(orig[i], w, h, tr)
        assert [[p is not None for p in r] for r in rows] == mask, "tile %d silhouette" % i
        ours.append(reskin(orig[i], h, tr, lambda x, y: base[y][x]))
        assert len(ours[i]) == len(orig[i])
    st = ["starry" if cur == orig[i] else "mosaic" if cur == ours[i] else "FOREIGN"
          for i, (off, cur, *_r) in enumerate(hss_tiles)]
    print("  Release.hss Sky tiles: %s" % ", ".join(st))
    if "FOREIGN" in st:
        sys.exit("ABORT: a Sky tile is neither the starry art nor this script's c0_r0")

    # --- AoWEPACK.dpl state
    d = bytearray(open(P.TARGET, "rb").read())
    o = P.va2off(d, HOOK)
    hook_new = P.jmp_to(HOOK, CAVE, 6)
    cur = bytes(d[o:o + 6])
    hst = "vanilla" if cur == HOOK_ORIG else "installed" if cur == hook_new else "FOREIGN"
    zo, zh = P.va2off(d, SLOT[0]), P.va2off(d, SLOT[1])
    zone = bytes(d[zo:zh])
    blobs_in = all(bytes(d[P.va2off(d, va):P.va2off(d, va) + len(b)]) == b for _n, va, b in blobs)
    print("  hook %08X: %s; slot: %s" % (HOOK, hst, "zero" if not any(zone)
                                            else "ours" if blobs_in else "NOT ZERO (stale or foreign)"))
    if hst == "FOREIGN":
        sys.exit("ABORT: the hook site holds foreign bytes")
    if hst == "installed" and not blobs_in:
        sys.exit("ABORT: the hook is installed but the slot is not this script's (build_sky_anim?)")
    if P.relocs_in(d, HOOK, HOOK + 6) or P.relocs_in(d, SLOT[0], SLOT[1]):
        sys.exit("ABORT: .reloc entry under the hook or slot")
    if P.rel32_into(d, HOOK, HOOK + 6) or P.short_into(d, HOOK, HOOK + 6, HOOK, HOOK + 0xE0):
        sys.exit("ABORT: a jump lands inside the hook")
    if any(zone) and not blobs_in and hst == "vanilla":
        sys.exit("ABORT: slot is not zero and not ours")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    P.kill_aow()
    for i, (off, cur, *_r) in enumerate(hss_tiles):
        want = ours[i] if a.apply else orig[i]
        hss[off:off + len(want)] = want
    out = hss_crc.fix(bytes(hss))
    assert hss_crc.verify(out) and len(out) == len(hss)
    d[zo:zh] = bytes(zh - zo)
    if a.apply:
        for _n, va, b in blobs:
            p = P.va2off(d, va)
            d[p:p + len(b)] = b
    d[o:o + 6] = hook_new if a.apply else HOOK_ORIG
    try:
        open(P.TARGET, "wb").write(d)
        open(HSS, "wb").write(out)
    except PermissionError:
        sys.exit("LOCKED -- close AoWz.exe / AoWzEd.exe and retry")
    print("\n%s" % ("APPLIED: Sky = cloud mosaic (temporary)" if a.apply
                    else "UNDONE: starry Sky restored"))


if __name__ == "__main__":
    main()
