#!/usr/bin/env python3
r"""
AoW1 mod -- Sky & Chasm EDGES (v3 of the Chasm/Sky transitions), 2026-10-03.

Three edge treatments for the two void terrains, Sky (0xE) and Chasm (0xB):

 1. SURFACE WATER / ICE beside a void -> an ethereal dissolve instead of a sandy coast.
    Water (0) and Ice (6) are TAoWWaterHexagon; every frame they paint up to six 86x84 shore
    pieces from a 32-image set, picked by which neighbours are land (ShowDynamic, AoWEPACK
    5579AFB4) at id = per-direction base + piece.  The base is chosen per neighbour in
    TAoWWaterHexagon.UpdateTransitions (0 grass / 0x28 snow / 0x50 wasteland).  HOOK W adds
    Sky -> 0xA0 and Chasm -> 0xC0, and the script adds two 32-image "fade" sets at those ids to
    Images/Waterhex.ILB and Images/IceHex.ILB.  Each fade piece covers the same run of edges as
    the sand piece it replaces (PIECE_EDGES, proved against the transcription for all 63 masks)
    and is a cross-fade drawn solid in MIXED colours (liquid and void textures blended by distance
    from the edge); only where the mix is within FADE_EPS of what lies underneath is it
    dithered.  v1 used pure liquid/void pixels thinned by dither alone -- the owner read it as
    spray paint.  Colour and dither are functions of position on a 16-px lattice period.
    ⚠ The override first calls the PARENT TLowerIsometricHexagon.ShowDynamic (HSEPack 5561A400),
    which draws the identical piece selection from the fixed grass-sand ids 0..31; vanilla's
    snow/wasteland pieces simply cover it.  A dithered fade cannot, so CAVE P skips that parent
    call on any water hex with a void neighbour (the override still draws every piece).  Without
    it the lakes showed speckled sand -- caught in the live editor, not by any static check.
    ⚠ Vanilla quirk kept: a water hex whose only land is SE and SW (and optionally N) draws no
    SW piece at all -- that one edge stays a plain line.

 2. CAVE WATER (0xA) beside a void -> the same dissolve, static.  The v2 remap turned both void
    terrains into CaveWater for edge selection, so CaveWater|void compared equal and drew
    nothing (a hard line).  The remap cave (CAVE R, rewritten in place) now emits HexTrans ids
    0xE0+d / 0xE3+d (Sky) and 0xB0+d / 0xB3+d (Chasm), drawn displaced (frame = upper
    neighbour's origin + (-6,-9)).  It also stops the void hex drawing the CaveWater cliff lip
    (0xA3+d) onto a surface water/ice neighbour, which the dissolve would otherwise reveal.
    Everything else keeps the v2 remap (cliffs 0xA0/0xA3, CaveIce 0xD0/0xD3, lava blend).

 3. LONG CLIFF below land.  Where cliff-land {1,2,3,4,5,0xC} sits above a void hex, the void
    hex drew the CaveWater cliff 0xA3+d (S edge 0xA4, SE 0xA3, SW 0xA5): a brown rock lip over a
    ~7 px blue-grey face, and the land hex drew 0xA0+d on its upper edges.  Both lips sat INSIDE
    the land hex as a flat dirt ring lying on the terrain -- which the owner wants -- but with the
    blue-grey face removed the ring stopped short of the hex edge and terrain showed outside it.
    So each lip column keeps its own pattern and is shifted so its outer pixel sits RIM_DELTA px
    past the outline (RIM_WIDEN extra columns close the corners).  Both rims are drawn by a hex painted
    after the land, as vanilla drew the lip: lower rims LOWRIM_ID0+d (0xE9..0xEB) by the void hex
    below, upper rims TOP_ID0+d (0xE6..0xE8) by the land hex itself -- CAVE R emits both,
    displaced.  The curtain slices repeat the lower rim outside the land hex, over the strands.
    The curtain (v3, 2026-10-03, owner's direction) is the game's own EARTH-WALL face art hanging
    behind the rim: the pieces TUpperIsometricHexagon.ShowDynamic (HSEPack 55619F18) draws for an Earth wall whose
    S, SE and SW sides are open -- EARTHHEX.ILB r+3 at (-51,-16), r at (13,-16), 0xD at (-19,0),
    r = 0..2 -- lowered RAISE px (walls are drawn raised) so the strand roots sit on the land
    hex's lower outline, and split by column into the three edges.  Recoloured per void set:
    cracks deepened (CRACK), darker with depth, faded into the Sky / Chasm tile's mean colour,
    tips and side roots dissolved by dither.  The variant r is (2X + Y) mod 3 of the land hex.
    Failed before it (same day, judged by the owner): v1 procedural face with a lighter ledge
    every 7.5 px (countable bands); v2 texture synthesis from the lip (no faults, but below the
    base game's art quality).
    Real underground CaveWater keeps its shipped cliffs.  Hexes paint top to bottom, so a tall sprite drawn by
    the land hex would be painted over by the void hexes below it; instead CAVE S replaces
    TAoWHexagon's VMT Show slot (+0xA8): after the normal draw, a void hex draws its own slice
    of every curtain that reaches it.  Slices are split by the exact set of hexes their pixel
    columns cross, and a slice is drawn only when the land hex is cliff-land and every crossed
    hex is void -- land in between occludes the curtain, as it should.  Slices: HexTrans ids
    CURTAIN_ID0 + set*0x80 + r*0x20 + slice (set 0 Sky, 1 Chasm, chosen by the drawing hex's own
    terrain); table at CAVE_S + 0x200.  A (set, r, slice) with no pixels has no image: an unset id
    inside the table returns nil from ImageLib.Get (its alias slot is -1) and CAVE S skips it.

SITES (AoWEPACK.dpl)
  HOOK W   0x5579AE30  `movsx eax,[edi+0x14]; cmp ax,3` (8 B) -> jmp CAVE_W; nop x3
  CAVE W   0x5581A000  Sky/Chasm neighbour -> per-dir shore base 0xA0/0xC0, resume 0x5579AE7B;
                       else re-issues the cmp and resumes 0x5579AE38
  CAVE R   0x55812000  the v2 remap cave (build_chasm_sky_transitions.py), rewritten in place;
                       its hook at 0x5579AA92 is unchanged.  Emits ids via 0x5579AC88.
  VMT      0x5579A278  TAoWHexagon +0xA8 Show: thunk 0x55799450 (THexagon.Show) -> CAVE_S.
                       The slot is .reloc-covered; CAVE_S is in-module, so the rebase stays right.
  CAVE S   0x5581A040  calls THexagon.Show, then (own terrain void) walks the slice table.
                       GetField 0x557020DC, HXtoHP 0x557026B4, ImageLib.Get 0x55702934 (thunks).
                       Guards: nil resource / nil transition ILB, and id < ILB count.
  CALL P   0x5579B19A  `call 0x5579A178` (parent ShowDynamic thunk) -> call CAVE_P (rel32 retarget)
  CAVE P   0x5581A300  any land-flagged direction with a base >= 0xA0 -> ret 4, else tail-jump
  Claim: 0x5581A000..0x5581A3FF (W, S, slice table at S+0x200, P).
  All caves are register/stack + rel32 + call/pop PC => position independent.

DATA FILES (Ziggurat/Images)
  HEXTRANS.ILB  + 12 dissolves (0xB0..0xB5, 0xE0..0xE5) + 6 rims (0xE6..0xE8 upper, 0xE9..0xEB
                lower) + the curtain slices (0x100..0x1FF)
  Waterhex.ILB  + 64 fades (0xA0..0xBF Sky, 0xC0..0xDF Chasm)
  IceHex.ILB    + 64 fades (same ids)
  Appended at the end of directory and pixel data; re-tuning strips and re-appends.
  The same ids go into each file's half-size twin (_HEXTRANS/_Waterhex/_IceHex.ILB, 07-ui.md
  §7.1).  The editor reads both twins at startup (access times, 2026-10-03) and only the full
  files were seen drawing; the twins exist so no lookup can ever index past a table's end.
  ⚠ Every id the shore code can request must exist (it dereferences ImageLib.Get's result
  without a nil check), so all 32 slots of each set are written, including the three slot ids
  vanilla never requests (20, 26, 27).

COUPLINGS (forward hazards)
  * CAVE R belongs to build_chasm_sky_transitions.py.  Undo THIS script before running that one
    (it would abort on the longer cave anyway).  --undo restores its v2 bytes exactly.
  * The shore code dereferences ImageLib.Get without a nil check: never restore Waterhex/IceHex
    (or their _ twins) from a copy while hook W is installed -- --undo first.
  * The curtain is built from 0xA3..0xA5's lip (HexTrans) and EARTHHEX.ILB 0..5 and 0xD; editing
    any of those images needs a re-run
    here so the slices match.
  * Texture sources: the first H_co (Sky), Hu_wl (Chasm), HU_WA (CaveWater) tile in
    Release/Release.hss, and image 0x8C of Waterhex/IceHex.  Re-skinning those needs a re-run.
  * Randomness: none.  Every pixel is a deterministic function of position; no RandInt is
    added (the per-hex shore variant r is vanilla's address hash).  Cosmetic only, no game state.

UNPROVEN RISK: whether the per-frame shore draw stays cheap with dithered pieces (many short
RLE runs) on a map with many water hexes beside Sky.

--undo: restores HOOK W, CALL P, CAVE R (v2 bytes), the VMT slot, zeroes the claim, strips our
images from all six ILBs.
Dry run by default; --apply writes; --preview OUT.png renders a test field (current vs new).
"""
import argparse, math, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import hexfield as hf  # noqa: E402

DLL = os.path.join(GAME, "AoWEPACK.dpl")
HSS = os.path.join(GAME, "Release", "Release.hss")
IMG = os.path.join(GAME, "Images")
HEXTRANS = os.path.join(IMG, "HEXTRANS.ILB")
WATERHEX = os.path.join(IMG, "Waterhex.ILB")
ICEHEX = os.path.join(IMG, "IceHex.ILB")
DLL_BASE = 0x55700000

SKY, CHASM, CAVEWATER = 0x0E, 0x0B, 0x0A
CLIFFLAND = (1, 2, 3, 4, 5, 0xC)       # terrains that get the 0xA3+d cliff over a void
VOIDS = (SKY, CHASM)

# ---------------------------------------------------------------- tunables (re-run to re-tune)
WATER_FADE = dict(R_IN=9, R_OUT=14, CAP=10)       # px into the liquid / into the void / end taper
WATER_FADE_SINGLE = dict(R_IN=9, R_OUT=7, CAP=10) # the six isolated-edge pieces (Sky holes)
SINGLE_PIECES = (13, 17, 15, 23, 14, 16)          # ShowDynamic's lone-edge pieces for dirs 1..6
CW_FADE = dict(R=10, CAP=8)
FADE_EPS = (0.04, 0.16)                           # foreign share below which fade pixels dither out
STRAND = dict(START=2, LEN=30,           # px below the edge where the fade to the void starts / spans
              DARK0=0.95, DARK1=0.6,     # brightness at the roots / at the end of the fade
              CRACK=1.8,                 # shadows: distance below the local mean is multiplied by this
              STRUCT=0.6,                # how much light/dark structure survives inside the fade
              WING=(-8, 55),             # columns kept (land frame); the side roots beyond 0..47
              SIDE=(1, 8),               # side roots dither out over these px past the corner
              TIP=(-10, 2))              # tips dither out over END+TIP[0]..END+TIP[1]
STRAND_DROP = 1                                   # strands start this far below the outline (behind the rim)
MIN_SLICE = 4                                     # drop curtain slices smaller than this (px)

WBASE = {SKY: 0xA0, CHASM: 0xC0}
CW_IDS = {(SKY, 'own'): 0xE0, (SKY, 'void'): 0xE3, (CHASM, 'own'): 0xB0, (CHASM, 'void'): 0xB3}
CURTAIN_ID0 = 0x100                               # + set*SET_STRIDE + r*SLICE_STRIDE + slice
SLICE_STRIDE, SET_STRIDE = 0x20, 0x80             # set 0 Sky, 1 Chasm; r = variant 0..2
TOP_ID0 = 0xE6                                    # upper rims (cliff-land below a void), +d
LOWRIM_ID0 = 0xE9                                 # lower rims (void below cliff-land), +d
UNUSED_SLOTS = {20: {4}, 26: {5, 6}, 27: {2, 3}}   # never requested; any valid image will do

# ---------------------------------------------------------------- code sites
HOOK_W, HOOK_W_ORIG = 0x5579AE30, bytes.fromhex("0fbe47146683f803")
W_RESUME_CMP, W_RESUME_NEXT = 0x5579AE38, 0x5579AE7B
CAVE_W = 0x5581A000
CAVE_R = 0x55812000
CAVE_R_V2 = bytes.fromhex("0fbee883fd0e740583fd0b7505bd0a00000083ff0e740583ff0b7505bf0a00000039fde96f8af8ff")
CAVE_R_LIMIT = 0x55812100                          # build_chasm_sky_spellguard.py starts here
R_RESUME, R_TAIL = 0x5579AA97, 0x5579AC88
VMT_SHOW = 0x5579A1D0 + 0xA8
THUNK_SHOW, THUNK_GETFIELD, THUNK_HXTOHP, THUNK_GET = 0x55799450, 0x557020DC, 0x557026B4, 0x55702934
CAVE_S = 0x5581A040
CAVE_S_TBL = CAVE_S + 0x200
SITE_P = 0x5579B19A                                # call TLowerIsometricHexagon.ShowDynamic (thunk)
THUNK_PARENT_DYN = 0x5579A178
CAVE_P = 0x5581A300
CAVE_END = 0x5581A400                              # claim: 0x5581A000..0x5581A3FF


# ================================================================= art
def _bn16():
    """16x16 blue-noise threshold matrix (void-and-cluster, deterministic)."""
    import random
    n, sigma, N = 16, 1.5, 256
    K = [[math.exp(-(min(dx, n - dx) ** 2 + min(dy, n - dy) ** 2) / (2 * sigma * sigma))
          for dy in range(n)] for dx in range(n)]
    def energy(p):
        E = [0.0] * N
        for i in range(N):
            if p[i]:
                x0, y0 = i % n, i // n
                for j in range(N):
                    E[j] += K[(j % n - x0) % n][(j // n - y0) % n]
        return E
    rnd = random.Random(7)
    pat = [False] * N
    for i in rnd.sample(range(N), N // 10):
        pat[i] = True
    while True:
        E = energy(pat); t = max((E[i], i) for i in range(N) if pat[i])[1]; pat[t] = False
        E = energy(pat); v = min((E[i], i) for i in range(N) if not pat[i])[1]
        if v == t:
            pat[t] = True; break
        pat[v] = True
    rank, ones = [0] * N, sum(pat)
    p = pat[:]
    for r in range(ones - 1, -1, -1):
        E = energy(p); t = max((E[i], i) for i in range(N) if p[i])[1]; p[t] = False; rank[t] = r
    p = pat[:]
    for r in range(ones, N):
        E = energy(p); v = min((E[i], i) for i in range(N) if not p[i])[1]; p[v] = True; rank[v] = r
    return [[(rank[y * n + x] + 0.5) / N for x in range(n)] for y in range(n)]


BN = _bn16()


def theta(x, y):
    return BN[y % 16][x % 16]


def smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def hnoise(*a):
    v = 2166136261
    for x in a:
        v = ((v ^ (x & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    v ^= v >> 13; v = (v * 0x5bd1e995) & 0xFFFFFFFF; v ^= v >> 15
    return v / 4294967296.0


def vnoise1(x, period, seed):
    i = math.floor(x / period); f = x / period - i
    a, b = hnoise(seed, i) * 2 - 1, hnoise(seed, i + 1) * 2 - 1
    f = f * f * (3 - 2 * f)
    return a + (b - a) * f


class Tex:
    """a 48x32 tile repeated on the hex lattice (periodic under (32,16) and (0,32))"""
    def __init__(self, tile):
        self.px = tile.load()

    def at(self, x, y):
        for hx in (x // 32 - 1, x // 32):
            ox, oy = hx * 32, ((y - (hx & 1) * 16) // 32) * 32 + (hx & 1) * 16
            if hf.in_tile(x - ox, y - oy):
                c = self.px[x - ox, y - oy]
                if c[3]:
                    return c[:3]
        raise ValueError("lattice texture hole at %d,%d" % (x, y))


def chain(E, ox=0, oy=0):
    out = []
    for d in sorted(E):
        a, b = hf.edge_seg(d, ox, oy)
        out.append((a, b, ((d - 2) % 6 + 1) not in E, (d % 6 + 1) not in E))
    return out


def dissolve(W, H, fx, fy, edges, inside, outside, tex_in, tex_out, R_in, R_out, CAP):
    """Cross-fade along `edges`: frame pixel (X,Y) = reference (X+fx, Y+fy).  Each pixel is the
    MIX of the two textures (the fraction of the foreign one rises toward the edge and past it),
    drawn solid; only where the mix is within FADE_EPS of what lies underneath is it dithered, so
    no high-contrast speckle remains (owner: the all-or-nothing dither read as spray paint).
    Terminal edge ends taper over CAP px by thinning, not by colour, so overlapping shore pieces
    agree on every pixel's colour."""
    from PIL import Image
    lo, hi = FADE_EPS
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); px = im.load()
    for Y in range(H):
        for X in range(W):
            x, y = X + fx, Y + fy
            ins = any(hf.in_tile(x - ox, y - oy) for ox, oy in inside)
            outs = not ins and any(hf.in_tile(x - ox, y - oy) for ox, oy in outside)
            if not (ins or outs):
                continue
            amt = k = 0.0
            for a, b, st, et in edges:
                dist, t = hf.seg_dist(x + .5, y + .5, a, b)
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                beyond = -t * L if (t < 0 and st) else (t - 1) * L if (t > 1 and et) else 0.0
                pin = 1 - smooth(-R_in, R_out, -dist if ins else dist)
                f = (1 - pin) if ins else pin                      # share of the foreign texture
                ke = 1 - smooth(0, CAP, beyond)
                if ke * f > k * amt or (ke * f == k * amt and f > amt):
                    amt, k = f, ke
            q = k * smooth(lo, hi, amt)
            if q > 0 and theta(x, y) < q:
                bg = (tex_in if ins else tex_out).at(x, y)
                fg = (tex_out if ins else tex_in).at(x, y)
                px[X, Y] = tuple(int(round(bg[i] + (fg[i] - bg[i]) * amt)) for i in range(3)) + (255,)
    return im


def water_fades(tex_liquid, tex_void):
    """The pieces drawn for ONE isolated land edge (its neighbours are liquid) use WATER_FADE_SINGLE:
    a one-hex Sky hole in a lake gets one such piece from each of its six liquid neighbours, and
    at the full radius those fades met in the middle and squeezed the sky into a dark star."""
    out = {}
    for k in range(32):
        E = hf.PIECE_EDGES.get(k) or UNUSED_SLOTS[k]
        dy = hf.PIECE_DY.get(k, 0)
        F = WATER_FADE_SINGLE if k in SINGLE_PIECES else WATER_FADE
        out[k] = dissolve(86, 84, -19, -32 + dy, chain(E), [(0, 0)], [hf.DIRV[d] for d in E],
                          tex_liquid, tex_void, F['R_IN'], F['R_OUT'], F['CAP'])
    return out


def cw_dissolves(tex_cw, tex_void):
    """-> {('own'|'void', d): image}.  Frame = upper neighbour origin + (-6,-9) (displaced)."""
    out = {}
    for d, dirn in enumerate((6, 1, 2)):
        ox, oy = hf.DIRV[dirn]
        for owner, tin, tout in (('own', tex_cw, tex_void), ('void', tex_void, tex_cw)):
            out[(owner, d)] = dissolve(76, 84, ox - 6, oy - 9, chain({dirn}), [(0, 0)], [(ox, oy)],
                                       tin, tout, CW_FADE['R'], CW_FADE['R'], CW_FADE['CAP'])
    return out


CDIR = {'S': (4, 0xA4), 'SE': (3, 0xA3), 'SW': (5, 0xA5)}   # HN dir land->void, cliff image


def edge_y(dirn, x):
    xc = x + .5
    if dirn == 'S':
        return 32.0 if 15 <= x < 33 else None
    if dirn == 'SE':
        return 32 - (xc - 33) * 16 / 15 if 33 <= x < 48 else None
    return 16 + xc * 16 / 15 if 0 <= x < 15 else None


EARTHHEX = os.path.join(IMG, "EARTHHEX.ILB")
# TUpperIsometricHexagon.ShowDynamic (HSEPack 55619F18), Earth wall with S+SE+SW open and NE/NW
# walled: SW face r+3 at (-51,-16), SE face r at (13,-16), centre strands 0xD at (-19,0), r = 0..2.
# Walls are drawn raised; RAISE puts the strand roots on the land hex's real lower outline.
EARTH_PIECES = lambda r: ((r + 3, -51, -16), (r, 13, -16), (0xD, -19, 0))
RAISE = 16
VARIANTS = 3


def lower_y(x):
    ys = [y for y in range(32) if hf.in_tile(x, y)]
    return max(ys) if ys else None


def ref_y(x):
    """the land outline the strands hang from (flat beyond the side vertices)"""
    return lower_y(x) if 0 <= x < 48 else 16


def edge_of(x):
    return 'SW' if x < 15 else 'S' if x < 33 else 'SE'


def earth_strands(eh, r):
    """the Earth-wall faces for variant r, lowered by RAISE, clipped to below the land outline and
    to the WING columns -> {(x, y): rgb} in the LAND hex frame"""
    pix = {}
    for pid, dx, dy in EARTH_PIECES(r):
        im = eh.get(pid); px = im.load()
        for Y in range(im.size[1]):
            for X in range(im.size[0]):
                if px[X, Y][3]:
                    pix[(X + dx, Y + dy + RAISE)] = px[X, Y][:3]
    return {(x, y): c for (x, y), c in pix.items()
            if STRAND['WING'][0] <= x <= STRAND['WING'][1]
            and not (0 <= x < 48 and hf.in_tile(x, y)) and y > ref_y(x)}


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def recolour(pix, void_rgb):
    """Deepen the cracks (pixels darker than their 5x5 mean get CRACK x further below it), darken
    with depth, and fade into the void colour; the tips and the side roots dissolve by dither so a
    faded root never paints over a neighbouring hex's strands."""
    C = STRAND
    end = C['START'] + C['LEN']
    out = {}
    for (x, y), c in pix.items():
        t = y - ref_y(x)
        side = -x if x < 0 else (x - 47 if x > 47 else 0)
        keep = (1 - smooth(C['SIDE'][0], C['SIDE'][1], side)) * \
               (1 - smooth(end + C['TIP'][0], end + C['TIP'][1], t))
        if theta(x, y) >= keep:
            continue
        u = max(smooth(C['START'], end, t), 0.6 * smooth(0, C['SIDE'][1], side))
        nb = [pix[q] for q in ((x + a, y + b) for a in range(-2, 3) for b in range(-2, 3)) if q in pix]
        m = sum(lum(q) for q in nb) / len(nb)
        L = lum(c)
        k = max(0.0, m - (m - L) * C['CRACK']) / L if 1 < L < m else 1.0
        c2 = [v * k * (C['DARK0'] + (C['DARK1'] - C['DARK0']) * u) for v in c]
        s = 1 + C['STRUCT'] * (lum(c2) / 255 - 0.25) * 4 * (1 - u)
        out[(x, y)] = tuple(int(max(0, min(255, round(c2[i] * (1 - u) + void_rgb[i] * s * u))))
                            for i in range(3))
    return out


FACE_V = 0.26          # a shipped cliff column's bottom run darker than this is its blue-grey face
RIM_DELTA = 1          # each rim column's outer pixel sits this far past the hex outline
RIM_WIDEN = 3          # extra columns either side of an edge's span (closes the hex corners)
RIM_PCT = 0.8          # per-edge shift reaches the outline in this share of columns; the rest fill
RIM_SPAN_LOW = {'S': (15, 33), 'SE': (33, 48), 'SW': (0, 15)}
RIM_SPAN_UP = {6: (0, 15), 1: (15, 33), 2: (33, 48)}


def cliff_pixels(ht, iid):
    """a shipped HexTrans image as {(x, y): rgb} in the frame of the hex that draws it in place"""
    im = ht.get(iid); px = im.load()
    return {(X - 6, Y - 9): px[X, Y][:3] for Y in range(im.size[1]) for X in range(im.size[0])
            if px[X, Y][3]}


def split_face(pix):
    """the shipped cliff minus its bottom run of dark pixels (the blue-grey face)"""
    cols = {}
    for (x, y) in pix:
        cols.setdefault(x, []).append(y)
    lip = dict(pix)
    for x, ys in cols.items():
        top = None
        for y in sorted(ys, reverse=True):
            if max(pix[(x, y)]) / 255 < FACE_V and (top is None or y == top - 1):
                top = y
            else:
                break
        if top is not None:
            for y in ys:
                if y >= top:
                    lip.pop((x, y))
    return lip


def warm(c, hue=35 / 360):
    """put a cold (bluish/grey) pixel on the lip's brown hue; brown pixels pass unchanged"""
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(k / 255 for k in c))
    if 0.03 <= h <= 0.16 and s >= 0.15:
        return c
    return tuple(int(round(255 * k)) for k in colorsys.hsv_to_rgb(hue, max(s, 0.28), v * 0.95))


def upper_out(x):
    return min(y for y in range(32) if hf.in_tile(x, y))


def _edge_shift(need):
    """one shift for a whole edge (a per-column shift shears the lip art into vertical streaks):
    the RIM_PCT percentile of what each column needs to reach the outline"""
    need = sorted(need)
    return need[min(len(need) - 1, int(len(need) * RIM_PCT))]


def lower_rim(ht, dirn):
    """The CaveWater lip of 0xA3+d, a flat dirt ring lying on the terrain, expanded out to the hex
    edge.  With its blue-grey face removed the lip stopped ~3 px short of the outline and terrain
    showed outside it (owner: "some parts of the surface terrain were outside it").  The whole
    lip moves down by one per-edge shift (_edge_shift); a column still short of RIM_DELTA px past
    the outline repeats its bottom pixel down to it.  RIM_WIDEN extra columns either side are
    shifted with the edge (no fill) and close the corners together with the neighbouring edge."""
    lip = split_face(cliff_pixels(ht, CDIR[dirn][1]))
    a, b = RIM_SPAN_LOW[dirn]
    cols = {}
    for (x, y) in lip:
        cols.setdefault(x, []).append(y)
    s = _edge_shift([lower_y(x) + RIM_DELTA - max(cols[x]) for x in range(a, b) if x in cols])
    out = {}
    for x in range(max(0, a - RIM_WIDEN), min(48, b + RIM_WIDEN)):
        if x not in cols:
            continue
        for y in cols[x]:
            out[(x, y + s)] = warm(lip[(x, y)])
        if a <= x < b:
            bot = max(cols[x])
            for y in range(bot + s + 1, lower_y(x) + RIM_DELTA + 1):
                out[(x, y)] = warm(lip[(x, bot)])
    return out


def upper_rim(ht, dirn):
    """0xA0+d (the lip the land hex draws on an upper edge facing CaveWater), expanded out to the
    edge the same way -> {(x, y): rgb} in the LAND frame, clipped to the land hex and the void
    neighbour."""
    d = {6: 0, 1: 1, 2: 2}[dirn]
    P = cliff_pixels(ht, 0xA0 + d)
    a, b = RIM_SPAN_UP[dirn]
    nx, ny = hf.DIRV[dirn]
    cols = {}
    for (x, y) in P:
        cols.setdefault(x, []).append(y)
    s = _edge_shift([min(cols[x]) - (upper_out(x) - RIM_DELTA) for x in range(a, b) if x in cols])
    raw = {}
    for x in range(max(0, a - RIM_WIDEN), min(48, b + RIM_WIDEN)):
        if x not in cols:
            continue
        for y in cols[x]:
            raw[(x, y - s)] = warm(P[(x, y)])
        if a <= x < b:
            top = min(cols[x])
            for y in range(upper_out(x) - RIM_DELTA, top - s):
                raw[(x, y)] = warm(P[(x, top)])
    return {(x, y): c for (x, y), c in raw.items()
            if hf.in_tile(x, y) or hf.in_tile(x - nx, y - ny)}


def rim_images(ht):
    """-> {id: image}.  TOP_ID0+d: upper rims, drawn by the LAND hex, displaced (frame = void
    neighbour origin + (-6,-9)).  LOWRIM_ID0+d: lower rims, drawn by the VOID hex below, displaced
    (frame = land origin + (-6,-9)) -- the hex painted after the land, so the overlap lies on top
    of the terrain, exactly as vanilla drew 0xA3+d.  Clipped to the land hex and that void hex;
    the curtain slices repeat the rim outside the land hex for the hexes painted later."""
    from PIL import Image
    out = {}
    for d, dirn in enumerate((6, 1, 2)):
        nx, ny = hf.DIRV[dirn]
        im = Image.new("RGBA", (60, 50), (0, 0, 0, 0)); p = im.load()
        for (x, y), c in upper_rim(ht, dirn).items():
            X, Y = x - nx + 6, y - ny + 9
            if 0 <= X < 60 and 0 <= Y < 50:
                p[X, Y] = c + (255,)
        out[TOP_ID0 + d] = im
    for d, dirn in enumerate(('SE', 'S', 'SW')):          # edge d of the void hex A below L
        ax, ay = hf.DIRV[CDIR[dirn][0]]
        im = Image.new("RGBA", (60, 50), (0, 0, 0, 0)); p = im.load()
        for (x, y), c in lower_rim(ht, dirn).items():
            if (hf.in_tile(x, y) or hf.in_tile(x - ax, y - ay)) and 0 <= x + 6 < 60 and 0 <= y + 9 < 50:
                p[x + 6, y + 9] = c + (255,)
        out[LOWRIM_ID0 + d] = im
    return out


def curtain_art(ht, void_rgb):
    """-> slices [dict(dirn, land, void, imgs {(set, r): image}, n)].  Curtain = the Earth-wall
    strands of the edge's columns, recoloured per void set (0 Sky, 1 Chasm) and variant r; they hang
    straight from the land outline (no rim -- the owner ruled the CaveWater lip's flat brown band
    out, it shrank the terrain).  Slices: per drawing hex Q != L, every curtain pixel inside Q,
    split by the exact set of hexes its column crosses between the edge and the pixel; one key set
    shared by all (set, r)."""
    from PIL import Image
    eh = hf.Lib(EARTHHEX)
    strands = {(s, r): {(x, y + STRAND_DROP): c
                        for (x, y), c in recolour(earth_strands(eh, r), void_rgb[s]).items()}
               for s in range(len(void_rgb)) for r in range(VARIANTS)}
    rims = {dirn: lower_rim(ht, dirn) for dirn in CDIR}
    keys = {}
    for dirn in ('SE', 'S', 'SW'):
        A = hf.DIRV[CDIR[dirn][0]]
        for sr, spix in strands.items():
            C = {q: c for q, c in spix.items() if edge_of(q[0]) == dirn}
            C.update(rims[dirn])                          # the rim over the strand roots
            for (x, y), c in C.items():
                hs = [h for h in hf.hex_at(x, y) if h != (0, 0)]
                if not hs:
                    continue                              # inside L only; overlap pixels stay
                ye = edge_y(dirn, x)
                ye = int(math.floor(ye)) if ye is not None else y
                for q in hs:
                    qx, qy = hf.origin(*q)
                    path = {hf.primary(x, yy) for yy in range(ye, y)} - {(0, 0), q}
                    void = {(A[0] - qx, A[1] - qy)} | {(hf.origin(*h)[0] - qx, hf.origin(*h)[1] - qy)
                                                       for h in path}
                    key = (dirn, q, tuple(sorted(void - {(0, 0)})))
                    keys.setdefault(key, {}).setdefault(sr, {})[(x, y)] = c
    out = []
    for (dirn, q, void), per in sorted(keys.items()):
        if max(len(v) for v in per.values()) < MIN_SLICE:
            continue
        qx, qy = hf.origin(*q)
        imgs = {}
        for sr, pix in per.items():
            im2 = Image.new("RGBA", (48, 32), (0, 0, 0, 0)); p2 = im2.load()
            for (x, y), c in pix.items():
                p2[x - qx, y - qy] = c + (255,)
            imgs[sr] = im2
        out.append(dict(dirn=dirn, land=(-qx, -qy), void=list(void), imgs=imgs,
                        n=max(len(v) for v in per.values())))
    assert len(out) <= SLICE_STRIDE, "more slices than one variant's id block holds"
    return out


def slice_id(i, s, r):
    return CURTAIN_ID0 + s * SET_STRIDE + r * SLICE_STRIDE + i


def build_art():
    """-> dict(hextrans={id: img}, water={id: img}, ice={id: img}, slices=[...])"""
    ht, wl, il = hf.Lib(HEXTRANS), hf.Lib(WATERHEX), hf.Lib(ICEHEX)
    for lib, ids in ((ht, list(range(0xA3, 0xA6))), (wl, [0x8C]), (il, [0x8C])):
        for i in ids:
            assert lib.recs.get(i), "source image %#x missing" % i
    # the sources must be the SHIPPED images, never ours from an earlier run
    tiles = hf.hss_tiles(HSS)
    tex = {SKY: Tex(tiles[SKY][0]), CHASM: Tex(tiles[CHASM][0]), CAVEWATER: Tex(tiles[CAVEWATER][0]),
           'water': Tex(wl.get(0x8C)), 'ice': Tex(il.get(0x8C))}
    art = dict(hextrans={}, water={}, ice={})
    for vt in VOIDS:
        for liquid in ('water', 'ice'):
            for k, im in water_fades(tex[liquid], tex[vt]).items():
                art[liquid][WBASE[vt] + k] = im
        for (owner, d), im in cw_dissolves(tex[CAVEWATER], tex[vt]).items():
            art['hextrans'][CW_IDS[(vt, owner)] + d] = im
    void_rgb = []
    for vt in (SKY, CHASM):                               # set 0 = Sky, set 1 = Chasm (CAVE S)
        px = [im.getpixel((x, y))[:3] for im in tiles[vt] for x in range(48) for y in range(32)
              if im.getpixel((x, y))[3]]
        void_rgb.append(tuple(sum(c[i] for c in px) // len(px) for i in range(3)))
    art['slices'] = curtain_art(ht, void_rgb)
    art['hextrans'].update(rim_images(ht))
    for i, s in enumerate(art['slices']):
        for (vs, r), im in s['imgs'].items():
            art['hextrans'][slice_id(i, vs, r)] = im
    return art, tiles


# ================================================================= code
def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def cave_w():
    return asm(f"""
        movsx eax, byte ptr [edi+0x14]
        cmp eax, {SKY}
        je _sky
        cmp eax, {CHASM}
        je _chasm
        cmp ax, 3
        jmp 0x{W_RESUME_CMP:X}
    _sky:
        mov cl, {WBASE[SKY]}
        jmp _set
    _chasm:
        mov cl, {WBASE[CHASM]}
    _set:
        mov eax, dword ptr [esp+8]
        mov byte ptr [ebx+eax+0x19], cl
        jmp 0x{W_RESUME_NEXT:X}
    """, CAVE_W)


def cave_r():
    return asm(f"""
        movsx ebp, al
        test edi, edi
        je _wn
        cmp edi, 6
        jne _cw
    _wn:
        cmp ebp, {SKY}
        je _none
        cmp ebp, {CHASM}
        je _none
        jmp _remap
    _cw:
        cmp ebp, {CAVEWATER}
        jne _cw2
        cmp edi, {SKY}
        je _a_sky
        cmp edi, {CHASM}
        je _a_ch
        jmp _remap
    _cw2:
        cmp edi, {CAVEWATER}
        jne _top
        cmp ebp, {SKY}
        je _sky_a
        cmp ebp, {CHASM}
        je _ch_a
        jmp _remap
    _top:
        cmp ebp, {SKY}
        je _t_ov
        cmp ebp, {CHASM}
        jne _t_nv
    _t_ov:
        cmp edi, 15
        ja _remap
        mov edx, {CLIFFMASK}
        bt edx, edi
        jae _remap
        mov al, {LOWRIM_ID0}
        jmp _emit
    _t_nv:
        cmp edi, {SKY}
        je _t_nv2
        cmp edi, {CHASM}
        jne _remap
    _t_nv2:
        cmp ebp, 15
        ja _remap
        mov edx, {CLIFFMASK}
        bt edx, ebp
        jae _remap
        mov al, {TOP_ID0}
        jmp _emit
    _a_sky:
        mov al, {CW_IDS[(SKY, 'own')]}
        jmp _emit
    _a_ch:
        mov al, {CW_IDS[(CHASM, 'own')]}
        jmp _emit
    _sky_a:
        mov al, {CW_IDS[(SKY, 'void')]}
        jmp _emit
    _ch_a:
        mov al, {CW_IDS[(CHASM, 'void')]}
    _emit:
        add al, bl
        movzx edx, bl
        mov byte ptr [esi+edx+0x10], al
        mov byte ptr [esp], 1
    _none:
        jmp 0x{R_TAIL:X}
    _remap:
        cmp ebp, {SKY}
        je _mo
        cmp ebp, {CHASM}
        jne _cn
    _mo:
        mov ebp, {CAVEWATER}
    _cn:
        cmp edi, {SKY}
        je _mn
        cmp edi, {CHASM}
        jne _done
    _mn:
        mov edi, {CAVEWATER}
    _done:
        cmp ebp, edi
        jmp 0x{R_RESUME:X}
    """, CAVE_R)


def cave_p():
    """Skip the PARENT's shore pass on a water hex with a void neighbour.  TAoWWaterHexagon.
    ShowDynamic first calls TLowerIsometricHexagon.ShowDynamic (HSEPack 5561A400), which draws the
    same piece selection from the fixed grass-sand ids 0..31, then draws its own per-direction
    set over it.  Vanilla's snow/wasteland pieces cover the sand; a dithered fade cannot, so on
    those hexes the parent pass is skipped -- the override still draws every piece itself
    (identical selection logic, verified instruction for instruction)."""
    return asm(f"""
        push ebx
        push esi
        movzx esi, byte ptr [eax+0x14]
        xor ebx, ebx
    _l:
        bt esi, ebx
        jae _n
        cmp byte ptr [eax+ebx+0x1A], {min(WBASE.values())}
        jae _skip
    _n:
        inc ebx
        cmp ebx, 6
        jb _l
        pop esi
        pop ebx
        jmp 0x{THUNK_PARENT_DYN:X}
    _skip:
        pop esi
        pop ebx
        ret 4
    """, CAVE_P)


CLIFFMASK = sum(1 << t for t in CLIFFLAND)
VOIDMASK = sum(1 << t for t in VOIDS)


def cave_s():
    # frame: [ebp-4] vx  [-8] vy  [-0xC] py  [-0x10] px  [-0x14] draw x  [-0x18] draw y
    #        [-0x1C] ILB [-0x20] level [-0x24] hx [-0x28] pieces left [-0x30] voids left
    #        [-0x2C] last X  [-0x34] last Y (from _ter)  [-0x38] next slice
    #        [-0x3C] set offset (Chasm: SET_STRIDE)  [-0x40] set + variant offset of this group
    pc_at = CAVE_S + 14
    src = f"""
        push ebp
        mov ebp, esp
        sub esp, 0x40
        push ebx
        push esi
        push edi
        call _pc
    _pc:
        pop edi
        add edi, {CAVE_S_TBL - pc_at}
        mov ebx, eax
        mov dword ptr [ebp-4], edx
        mov dword ptr [ebp-8], ecx
        push dword ptr [ebp+8]
        mov eax, ebx
        mov edx, dword ptr [ebp-4]
        mov ecx, dword ptr [ebp-8]
        call 0x{THUNK_SHOW:X}
        mov esi, dword ptr [ebx+4]
        movsx eax, byte ptr [esi+0x14]
        cmp eax, 15
        ja _out
        mov edx, {VOIDMASK}
        bt edx, eax
        jnc _out
        xor edx, edx
        cmp eax, {CHASM}
        jne _set0
        mov edx, {SET_STRIDE}
    _set0:
        mov dword ptr [ebp-0x3C], edx
        lea eax, [ebp-0xC]
        push eax
        lea ecx, [ebp-0x10]
        movsx edx, byte ptr [esi+0x11]
        movsx eax, byte ptr [esi+0x10]
        call 0x{THUNK_HXTOHP:X}
        mov eax, dword ptr [ebp-0x10]
        sub eax, dword ptr [ebp-4]
        sub eax, 8
        mov dword ptr [ebp-0x14], eax
        mov eax, dword ptr [ebp-0xC]
        sub eax, dword ptr [ebp-8]
        mov dword ptr [ebp-0x18], eax
        mov eax, dword ptr [ebx+8]
        test eax, eax
        je _out
        mov eax, dword ptr [eax+0x34]
        test eax, eax
        je _out
        mov dword ptr [ebp-0x1C], eax
        mov eax, dword ptr [esi+4]
        mov dword ptr [ebp-0x20], eax
        movsx eax, byte ptr [esi+0x10]
        mov dword ptr [ebp-0x24], eax
    _group:
        mov cx, word ptr [edi]
        cmp cl, 0x7F
        je _out
        movzx eax, byte ptr [edi+2]
        mov dword ptr [ebp-0x28], eax
        add edi, 3
        call _ter
        cmp eax, 15
        ja _skipgrp
        mov edx, {CLIFFMASK}
        bt edx, eax
        jnc _skipgrp
        mov eax, dword ptr [ebp-0x2C]
        add eax, eax
        add eax, dword ptr [ebp-0x34]
        xor edx, edx
        mov ecx, {VARIANTS}
        div ecx
        imul edx, edx, {SLICE_STRIDE}
        add edx, dword ptr [ebp-0x3C]
        mov dword ptr [ebp-0x40], edx
    _slice:
        cmp dword ptr [ebp-0x28], 0
        je _group
        movzx eax, byte ptr [edi+2]
        mov dword ptr [ebp-0x30], eax
        lea eax, [edi+eax*2+3]
        mov dword ptr [ebp-0x38], eax
        lea esi, [edi+3]
    _vloop:
        cmp dword ptr [ebp-0x30], 0
        je _draw
        mov cx, word ptr [esi]
        call _ter
        cmp eax, 15
        ja _next
        mov edx, {VOIDMASK}
        bt edx, eax
        jnc _next
        add esi, 2
        dec dword ptr [ebp-0x30]
        jmp _vloop
    _draw:
        movzx edx, word ptr [edi]
        add edx, dword ptr [ebp-0x40]
        mov eax, dword ptr [ebp-0x1C]
        cmp edx, dword ptr [eax+0x44]
        jge _next
        call 0x{THUNK_GET:X}
        test eax, eax
        je _next
        push dword ptr [ebp+8]
        mov edx, dword ptr [ebp-0x14]
        mov ecx, dword ptr [ebp-0x18]
        mov esi, dword ptr [eax]
        call dword ptr [esi+0x84]
    _next:
        mov edi, dword ptr [ebp-0x38]
        dec dword ptr [ebp-0x28]
        jmp _slice
    _skipgrp:
        mov ecx, dword ptr [ebp-0x28]
    _sk:
        test ecx, ecx
        je _group
        movzx eax, byte ptr [edi+2]
        lea edi, [edi+eax*2+3]
        dec ecx
        jmp _sk
    _out:
        lea esp, [ebp-0x4C]
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 4

    _ter:
        movsx eax, cl
        add eax, dword ptr [ebp-0x24]
        js _oob
        mov edx, dword ptr [ebp-0x20]
        cmp eax, dword ptr [edx+0xC]
        jge _oob
        movsx edx, ch
        shl edx, 4
        add edx, dword ptr [ebp-0xC]
        mov ecx, eax
        and ecx, 1
        shl ecx, 4
        sub edx, ecx
        sar edx, 5
        js _oob
        mov ecx, dword ptr [ebp-0x20]
        cmp edx, dword ptr [ecx+0x10]
        jge _oob
        mov dword ptr [ebp-0x2C], eax
        mov dword ptr [ebp-0x34], edx
        mov ecx, edx
        mov edx, eax
        mov eax, dword ptr [ebp-0x20]
        call 0x{THUNK_GETFIELD:X}
        movsx eax, byte ptr [eax+0x14]
        ret
    _oob:
        or eax, -1
        ret
    """
    code = asm(src, CAVE_S)
    assert code[14] == 0x5F, "PC fetch is not at CAVE_S+14"
    assert CAVE_S + len(code) <= CAVE_S_TBL, "cave S overruns its table"
    return code


def slice_table(slices):
    """groups by land offset: [dx, oy16, n] then n x [u16 id, nvoid, (dx, oy16)*]; 0x7F ends."""
    def enc(o):
        dx, dy = o
        assert dx % 32 == 0 and dy % 16 == 0
        return struct.pack("<bb", dx // 32, dy // 16)
    groups = {}
    for i, s in enumerate(slices):
        groups.setdefault(s['land'], []).append((CURTAIN_ID0 + i, s['void']))
    t = bytearray()
    for land, items in groups.items():
        t += enc(land) + bytes([len(items)])
        for iid, void in items:
            t += struct.pack("<HB", iid, len(void)) + b"".join(enc(v) for v in void)
    t += b"\x7F\x00\x00"
    return bytes(t)


# ================================================================= files
def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    opt = struct.unpack_from("<H", data, e + 20)[0]
    s, out = e + 24 + opt, []
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, s + 8)
        out.append((vaddr, vsize, raw, rsize)); s += 40
    return out


def va2off(secs, va):
    rva = va - DLL_BASE
    for vaddr, vsize, raw, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    raise ValueError("VA %08X not mapped" % va)


def dll_plan(data, art, undo):
    """-> list of (va, old, new, label) after verifying every site is in a known state."""
    secs = load_sections(data)
    rd = lambda va, n: bytes(data[va2off(secs, va):va2off(secs, va) + n])
    plan = []
    w = cave_w(); r = cave_r(); s = cave_s(); p = cave_p()
    tbl = slice_table(art['slices']) if art else b""
    assert CAVE_W + len(w) <= CAVE_S and CAVE_R + len(r) <= CAVE_R_LIMIT
    assert CAVE_S_TBL + len(tbl) <= CAVE_P, "slice table overruns cave P"
    assert CAVE_P + len(p) <= CAVE_END

    call_orig = b"\xE8" + struct.pack("<i", THUNK_PARENT_DYN - (SITE_P + 5))
    call_new = b"\xE8" + struct.pack("<i", CAVE_P - (SITE_P + 5))
    cur = rd(SITE_P, 5)
    if cur not in (call_orig, call_new):
        raise SystemExit(f"ABORT: call at {SITE_P:#x} unexpected: {cur.hex()}")
    plan.append((SITE_P, cur, call_orig if undo else call_new, "call P (parent shore pass)"))
    hook_w = b"\xE9" + struct.pack("<i", CAVE_W - (HOOK_W + 5)) + b"\x90" * 3

    cur = rd(HOOK_W, 8)
    if cur not in (HOOK_W_ORIG, hook_w):
        raise SystemExit(f"ABORT: hook W bytes unexpected: {cur.hex()}")
    plan.append((HOOK_W, cur, HOOK_W_ORIG if undo else hook_w, "hook W (water shore base)"))

    cur = rd(CAVE_R, CAVE_R_LIMIT - CAVE_R)
    v2 = CAVE_R_V2 + b"\x00" * (CAVE_R_LIMIT - CAVE_R - len(CAVE_R_V2))
    v3 = r + b"\x00" * (CAVE_R_LIMIT - CAVE_R - len(r))
    ours_any = cur[:5] == r[:5] and not cur[len(cur) - 0x10:].strip(b"\x00")   # any version of ours
    if cur not in (v2, v3) and not ours_any:
        raise SystemExit("ABORT: cave R is neither the v2 remap nor ours -- run "
                         "build_chasm_sky_transitions.py's dry run and look")
    plan.append((CAVE_R, cur, v2 if undo else v3, "cave R (remap: water / cave-water cases)"))

    cur = rd(VMT_SHOW, 4)
    want_old, want_new = struct.pack("<I", THUNK_SHOW), struct.pack("<I", CAVE_S)
    if cur not in (want_old, want_new):
        raise SystemExit(f"ABORT: TAoWHexagon VMT +0xA8 unexpected: {cur.hex()}")
    plan.append((VMT_SHOW, cur, want_old if undo else want_new, "VMT TAoWHexagon.Show +0xA8"))

    cur = rd(CAVE_W, CAVE_END - CAVE_W)
    body = bytearray(CAVE_END - CAVE_W)
    if not undo:
        body[0:len(w)] = w
        body[CAVE_S - CAVE_W:CAVE_S - CAVE_W + len(s)] = s
        body[CAVE_S_TBL - CAVE_W:CAVE_S_TBL - CAVE_W + len(tbl)] = tbl
        body[CAVE_P - CAVE_W:CAVE_P - CAVE_W + len(p)] = p
    ours = rd(HOOK_W, 8) == hook_w or rd(VMT_SHOW, 4) == want_new or rd(SITE_P, 5) == call_new
    if any(cur) and not ours:
        raise SystemExit("ABORT: 0x5581A000..0x5581A3FF holds bytes this script did not write")
    plan.append((CAVE_W, cur, bytes(body), "caves W + S + P + slice table"))
    return plan, secs, (w, r, s, tbl, p)


def reloc_covered(data, secs, va):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    rva, size = struct.unpack_from("<II", data, e + 24 + 96 + 5 * 8)
    o, end = va2off(secs, DLL_BASE + rva), va2off(secs, DLL_BASE + rva) + size
    hits = []
    while o < end:
        page, blk = struct.unpack_from("<II", data, o)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", data, o + 8 + 2 * i)[0]
            if ent >> 12 == 3:
                hits.append(DLL_BASE + page + (ent & 0xFFF))
        o += blk
    return hits


def our_ids():
    return dict(hextrans=set(CW_IDS[k] + d for k in CW_IDS for d in range(3)) |
                set(range(TOP_ID0, TOP_ID0 + 3)) | set(range(LOWRIM_ID0, LOWRIM_ID0 + 3)) |
                set(range(CURTAIN_ID0, CURTAIN_ID0 + 2 * SET_STRIDE)),
                water=set(range(0xA0, 0xE0)), ice=set(range(0xA0, 0xE0)))


def halve(im):
    """the `_<NAME>.ILB` twin of an image: half size, ceil per axis (07-ui.md §7.1).  A pixel is
    opaque when at least two of its 2x2 source pixels are; colour = their mean."""
    from PIL import Image
    W, H = im.size
    out = Image.new("RGBA", ((W + 1) // 2, (H + 1) // 2), (0, 0, 0, 0))
    sp, dp = im.load(), out.load()
    for y in range(out.size[1]):
        for x in range(out.size[0]):
            cs = [sp[a, b] for a in (2 * x, 2 * x + 1) for b in (2 * y, 2 * y + 1)
                  if a < W and b < H and sp[a, b][3]]
            if len(cs) >= 2:
                dp[x, y] = tuple(sum(c[i] for c in cs) // len(cs) for i in range(3)) + (255,)
    return out


def ilb_plan(art, undo):
    ids = our_ids()
    out = []
    files = []
    for key, path in (('hextrans', HEXTRANS), ('water', WATERHEX), ('ice', ICEHEX)):
        files += [(key, path, False), (key, os.path.join(IMG, "_" + os.path.basename(path)), True)]
    for key, path, half in files:
        d = open(path, "rb").read()
        base = hf.ilb_strip(d, ids[key])
        R = hf.read_records(base)
        clash = [r['id'] for r in R['recs'] if r['id'] in ids[key]]
        if clash:
            raise SystemExit(f"ABORT: {os.path.basename(path)} already uses ids {clash[:6]}")
        if undo:
            new = base
        else:
            tpl = R['recs'][-1]
            items = []
            imgs = {i: (halve(im) if half else im) for i, im in art[key].items()}
            for iid in sorted(imgs):
                name = {"hextrans": "zskychasm_edge.BMP", "water": "zskychasm_fade.BMP",
                        "ice": "zskychasm_fade.BMP"}[key]
                items.append(hf.image_record(tpl, iid, name, imgs[iid], tpl['tr']))
            new = hf.ilb_append(base, items)
            # every shipped image must survive field-for-field and pixel-for-pixel
            R0, R1 = hf.read_records(base), hf.read_records(new)
            f = lambda r: {k: v for k, v in r.items() if k not in ('start', 'raw')}
            m1 = {r['id']: r for r in R1['recs']}
            for r in R0['recs']:
                assert f(m1[r['id']]) == f(r), "shipped record %#x changed" % r['id']
                a = base[R0['imgdir'] + r['offset']:][:r['size']]
                b = new[R1['imgdir'] + r['offset']:][:r['size']]
                assert a == b, "shipped pixels %#x changed" % r['id']
            for iid in imgs:
                im = hf.decode_image(new, m1[iid], R1['imgdir'])
                a = imgs[iid]
                mask = lambda i: bytes(v > 0 for v in i.getchannel("A").tobytes())
                assert mask(im) == mask(a), "image %#x did not round-trip" % iid
        out.append((path, d, new))
    return out


# ================================================================= preview
def preview_scene():
    M = {(hx, hy): SKY for hx in range(16) for hy in range(11)}
    for k in [(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2), (4, 2), (2, 3), (3, 3), (2, 0), (3, 0), (4, 1)]:
        M[k] = 1
    M[(3, 2)], M[(4, 2)] = 2, 4
    for k in [(7, 2), (8, 2), (7, 3), (8, 5)]:
        M[k] = 0
    for k in [(9, 4), (10, 4)]:
        M[k] = 6
    for hy in range(4):
        M[(13, hy)], M[(14, hy)] = CAVEWATER, 0xD
    M[(12, 1)] = CAVEWATER
    for hx in range(16):
        for hy in range(7, 11):
            M[(hx, hy)] = CHASM
    for k in [(2, 7), (3, 7), (2, 8), (4, 8), (3, 8), (11, 8), (12, 8), (12, 9)]:
        M[k] = 0xC
    for k in [(6, 8), (7, 8)]:
        M[k] = CAVEWATER
    M[(14, 9)] = M[(15, 9)] = 0
    return M


def new_rule(O, N, d, r):
    if N in (0, 6) and O in VOIDS:
        return None
    if O == CAVEWATER and N in VOIDS:
        return (CW_IDS[(N, 'own')] + d, True)
    if N == CAVEWATER and O in VOIDS:
        return (CW_IDS[(O, 'void')] + d, True)
    if O in VOIDS and N in CLIFFLAND:
        return (LOWRIM_ID0 + d, True)
    if O in CLIFFLAND and N in VOIDS:
        return (TOP_ID0 + d, True)
    return hf.vanilla_rule(CAVEWATER if O in VOIDS else O, CAVEWATER if N in VOIDS else N, d, r)


def cur_rule(O, N, d, r):
    return hf.vanilla_rule(CAVEWATER if O in VOIDS else O, CAVEWATER if N in VOIDS else N, d, r)


def preview(out_path, art, tiles):
    from PIL import Image
    libs = [hf.Lib(HEXTRANS), hf.Lib(WATERHEX), hf.Lib(ICEHEX)]
    for lib, key in zip(libs, ('hextrans', 'water', 'ice')):   # hide images from an earlier run
        for i in our_ids()[key] & set(lib.recs):
            del lib.recs[i]
    M = preview_scene()
    a = hf.render(M, *libs, tiles, rule=cur_rule)
    for lib, key in zip(libs, ('hextrans', 'water', 'ice')):
        lib.cache.update(art[key]); lib.recs.update({i: True for i in art[key]})

    def after(T, hx, hy):
        if T(hx, hy) not in VOIDS:
            return []
        qx, qy = hf.origin(hx, hy)
        ter = lambda o: T(*hf.px2hex(qx + o[0], qy + o[1]))
        vs = 1 if T(hx, hy) == CHASM else 0                      # CAVE S: set by the drawing hex
        out = []
        for s in art['slices']:
            if ter(s['land']) in CLIFFLAND and all(ter(v) in VOIDS for v in s['void']):
                lx, ly = hf.px2hex(qx + s['land'][0], qy + s['land'][1])
                im = s['imgs'].get((vs, (2 * lx + ly) % VARIANTS))  # CAVE S: variant by the land hex
                if im is not None:
                    out.append((im, 0, 0))
        return out
    b = hf.render(M, *libs, tiles, rule=new_rule, shore_base=lambda N: WBASE.get(N), after_hex=after)
    sheet = Image.new("RGBA", (a.size[0], a.size[1] * 2 + 8), (255, 255, 255, 255))
    sheet.paste(a, (0, 0)); sheet.paste(b, (0, a.size[1] + 8))
    sheet = sheet.resize((sheet.size[0] * 2, sheet.size[1] * 2), Image.NEAREST)
    sheet.save(out_path)
    print(f"preview -> {out_path}  (top: current, bottom: with this script)")


# ================================================================= main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--preview", metavar="OUT.png")
    args = ap.parse_args()
    for p in (DLL, HSS, HEXTRANS, WATERHEX, ICEHEX, os.path.join(GAME, "AoWz.exe")):
        assert os.path.exists(p), f"missing {p} -- GAME must be the Ziggurat folder"

    art, tiles = (None, None) if args.undo else build_art()
    if art:
        print(f"art: {len(art['hextrans'])} HexTrans, {len(art['water'])} Waterhex, "
              f"{len(art['ice'])} IceHex images; {len(art['slices'])} curtain slices")
        for i, s in enumerate(art['slices']):
            print(f"    slice {CURTAIN_ID0 + i:#x} {s['dirn']:2} land {s['land']} void {s['void']} ({s['n']} px)")
    if args.preview:
        preview(args.preview, art, tiles)

    data = bytearray(open(DLL, "rb").read())
    plan, secs, (w, r, s, tbl, p) = dll_plan(data, art, args.undo)
    assert VMT_SHOW in reloc_covered(data, secs, VMT_SHOW), "VMT slot lost its .reloc entry"
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    if not args.undo:
        for name, code, at in (("CAVE W", w, CAVE_W), ("CAVE R", r, CAVE_R), ("CAVE S", s, CAVE_S),
                               ("CAVE P", p, CAVE_P)):
            print(f"  {name} {at:#x} ({len(code)} B)")
            n = sum(i.size for i in cs.disasm(code, at))
            assert n == len(code), f"{name}: disassembly stops at +{n:#x}"
        print(f"  slice table {CAVE_S_TBL:#x} ({len(tbl)} B)")
    changed = [(va, old, new, lab) for va, old, new, lab in plan if old != new]
    ilbs = ilb_plan(art, args.undo)
    ilb_changed = [(p, old, new) for p, old, new in ilbs if old != new]
    for va, old, new, lab in plan:
        print(f"  {'CHANGE' if old != new else 'same  '} {va:#x} {lab}")
    for p, old, new in ilbs:
        print(f"  {'CHANGE' if old != new else 'same  '} {os.path.basename(p)} {len(old)} -> {len(new)} bytes")
    if not changed and not ilb_changed:
        print("nothing to do -- already in the requested state"); return 0
    if not args.apply:
        print("dry run -- re-run with --apply (or --undo --apply) to write"); return 0

    for va, old, new, lab in plan:
        o = va2off(secs, va)
        data[o:o + len(new)] = new
    try:
        open(DLL, "wb").write(data)
        for p, old, new in ilb_changed:
            open(p, "wb").write(new)
    except PermissionError:
        print("LOCKED -- close AoWz.exe / AoWzEd.exe / AoWDevEd.exe and retry"); return 1
    print("undone" if args.undo else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
