#!/usr/bin/env python3
r"""
build_sky_parallax.py -- Firmament Sky shows the Surface far below, hazed, wrapping in both axes,
scrolling at a quarter of the sky's speed.  AoWEPACK.dpl only.  Owner request 2026-10-15, revised
the same day.  Dry run by default; --apply; --undo.

WHAT IT DOES
    While the Firmament (level 3) is shown, every pixel of a Sky hex (terrain 0xE) that still shows
    the starry tile is mixed with a 0.6-size image (SC_N / SC_D) of level 0: everything the game draws except
    armies and the map-edge border (owner: show everything, terrain + cities, no border), pushed
    HAZE = 0.55 toward HAZE_RGB (the vanilla Ice mean; owner: a dramatic distance haze), at
    SURFACE_SHARE 25 % against the sky.
    The image is the Surface's interior folded into a tile that repeats in x and y (owner: "make
    the image of the surface have wraparound, both X-axis and Y-axis"), and it scrolls at
    1 / 2**PAR_SHIFT = 1/4 of the sky's speed: image column = world x - (VX - VX/4), mod the tile.
    The tile is a whole number of hexes and of px: at 0.6 the hex pitch is 19.2 px, so a multiple
    of 10 hexes across (even, for the hex grid's column parity) and 5 down; the interior is rounded
    down to that and the rest overlaps.  Sprites that cross the seam are cut there.
    Curtains, fades, bridges, pads and neighbours' transitions drawn over Sky differ from the starry
    pixels and are left alone.  Display only: no rolls, nothing synced.
    Size 3/4 until the owner asked for 0.6 the same day.
    Withdrawn the same day: 1/2 size with 50/50 and 25 % mixes; corners pinned to the screen with a
    straight crop (cut the hexagonal edge); edges meeting the Firmament border at the view limits
    (the image must then cover the map at its own size, so it can never be slower than the window
    allows, and the edges part between the limits); a faint 1/8 cloud wash from the 8x8 mosaic
    (removed by the owner pending AoW2 cloud art).
    Layout: cave_main CAVE, blend +0x400, rebuild +0x700, data CAVE+0x1200.

HOW
    Hook TAoWHSMap.DrawDynamicScene's entry 0x55778A60 (6 B, prologue replayed; no .reloc, nothing
    jumps inside) -> cave_main, the hook build_sky_anim.py used.  eax = map, edx = the locked
    back-buffer record.  Live map only ([MAPVAR]); RGB565 or RGB555 only.
    1. Cache.  G_VALID is cleared on every frame shown on another level, so the cache is rebuilt
       on the first frame after switching to the Firmament (and on a map or pixel-format change).
       cave_rebuild renders level 0 through the game's own scene path, 15x15 hexes (480x480 px, 288
       image px -- a whole number at 0.6) at a time, into a 608x608 scratch buffer (a 64 px border on every side is rendered and thrown
       away: the sprite clipper drops a few rows of any sprite that starts above the clip top,
       which left notches along every chunk's top edge -- found live).  The buffer is described by
       a hand-built surface record (the 0x3C-byte record GFXE.TDIB16Surface.Lock fills: +0 w,
       +4 h, +8 bpp, +0C pitch, +10..+1C clip, +20 row 0, +28 format, +2C..+34 RGB masks -- copied
       from the back buffer, then w/h/pitch/clip/pixels replaced).  Per chunk: [map+0x88] = 0,
       view origin = chunk origin - 64, window [map+0x94..0xA0] = the chunk's hexes plus 4 columns
       each side, 4 rows above and 6 below (tall sprites hang upward from lower hexes);
       ResetVisibleStaticHS + ResetVisibleDynamicHS; for each field TMapLevel.GetField, then
       TMapField.CopyStaticVisibleHS into [map+0x1C] and CopyDynamicVisibleHS into [map+0x20];
       sort both ([list].vmt+0x90); then each list back to front through each object's Show
       (vmt+0xA8, as DrawStaticHS / DrawDynamicHS do), SKIPPING TArmyHS (VMT 0x557133A0) and
       TAoWBorderHexagon (VMT 0x5579A458), neither subclassed: mountains, forests, structures and
       the water's shore pass live in the dynamic list, flat terrain in the static one.  These are
       THSMap.Update*Scene's own loops minus the [map+0x24]/[map+0x28] extras and AoW's explored
       filter.  Each chunk is resampled to 0.6 into an unfolded image (about W*19.2+9.6 x
       H*19.2+9.6 px): pixel j takes the source 2x2 block at floor(5j/3) (steps COLSTEP = +1 +2 +2),
       averaged per channel
       over its NON-EMPTY pixels only (256/n from a table; 86 for n = 3), so the hex outline has no
       dark rim to show at the seam.  Then the seven fields are restored and the real
       UpdateStaticScene / UpdateDynamicScene (map vmt+0xD8 / +0xDC) rebuild both lists for the
       actual view -- DrawDynamicScene, which the hook sits in front of, draws from the dynamic
       list right after.
       Interior: per column and per row, the count of non-empty pixels; the first and last above a
       quarter of the other dimension bound the interior.  n hexes span n*p + p/2 px (p = 19.2),
       less the few px the threshold cuts off the slants: n = floor((last - first + 8) / p), rounded
       down to the tile quantum.  A short count overlaps columns, a long one leaves a gap.  ⚠ The border is not one hex: on the
       test map it is about five, and the engine draws each hex a few px left of hx*p, so deriving
       the period from rounded hex indices left a one-column gap (found live).
       Fold: unfolded pixel (x, y) goes to ((x - Xl) mod Px, (y - Yt) mod Py) if it is non-empty
       and the tile pixel is still empty (first in row order wins: a row-1 peak hanging above the
       interior stays over the bottom row's terrain).  The tile (System.@GetMem, kept for the
       process, reused while big enough) is Px x Py -- 2112 x 2208, 9.3 MB, for a 127x127 map;
       the unfolded image (12 MB) and the scratch are freed.
    2. Blend.  For every visible Firmament field with terrain 0xE, every hex pixel whose back-
       buffer value equals one of the 8 starry Sky tiles at that position becomes, per channel and
       in ONE step, (s W_S + c W_C + H W_H + half a step) >> 8 -- sky s, Surface c, haze colour H;
       weights /256: 192 / 29 / 35.  A tile pixel of 0 (the map's own empty hexes) leaves the sky.
       main wraps the hex origin into the tile (idiv, sign fixed); blend wraps each row once and
       each column step.
       ⚠ The first build chained the mixes as masked halvings ((v & M) >> 1 per step) on top of a
       haze already stored in 5 bits: on the RGB555 screen the Surface kept ~3-4 levels per channel
       and each truncation shaved a different share off each channel -- owner saw flat teal blotches
       ("as if reduced to 16-bit").  Reproduced offline (scratch sim.py) and replaced by the exact
       mix; never chain truncating blends at 5 bits per channel.
    Data: spans (32 x L,R bytes), the 8 Sky tiles' opaque pixels in 565, then 555 (to555, ILPACK's
    remap); mix_table() per format (565, 555): 3 channel masks, 3 x (H W_H + half a step); the
    5-dword 256/n table.
    BSS 0x558FAF00..0x558FAF1B: G_BUF, G_MW (Px), G_MH (Py), G_VALID, G_MAP, G_FMT, G_CAP.
    Proved live in AoWzEd 2026-10-15 (map "Cooperative Map Project Bing+The Groll 3", 127x127,
    2195x1256 view): the tile read back from the process is 110 x 115 hexes at 0.6 (114 x 115 at
    3/4), and tiled 2x2 its seams run on with no gap; the blend draws at quarter speed; a
    full-speed test build at 3/4 (PAR_SHIFT 0) put the seam on screen with no strip.  At 0.6 the
    tile is narrower than a 2195 px view, so a seam is always on screen across.

Rolls: none (display only).  PIC: rel32, load-delta (call/pop) for data, BSS and the two IAT
slots (VCL30 System.@GetMem 0x558FB718 / @FreeMem 0x558FB714).
Slot 0x55852200..0x55899FFF (AoWEPACK CODE), exclusive.
COUPLING: build_sky_anim.py and build_sky_mosaic.py use the same hook and slot -- mutually
exclusive; each aborts on the others' bytes (hook installed, slot not its own).
UNPROVEN RISK: AoWz.exe was not run.  Structures the player has not seen may not draw into the
image (their Show reads a fog-hidden flag); the cache refreshes only on entering the Firmament, so
Surface changes made while there (a city taken) show on the next visit.  A map whose interior has
holes along its middle could mis-measure the period (the quarter threshold tolerates scattered
empty hexes).
"""
import argparse
import os
import struct
import sys

sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm
import build_sky_anim as A

GAME = P.GAME
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
from ilb_rle16 import decode  # noqa: E402

HSS = A.HSS
SKY = A.SKY
FIRMAMENT, SURFACE = 3, 0
HOOK, HOOK_ORIG, RESUME = A.HOOK, A.HOOK_ORIG, A.RESUME
SLOT, CAVE = A.SLOT, A.CAVE
DATA_VA = CAVE + 0x1200
MAPVAR, GETLVL, FMT565, FMT555 = A.MAPVAR, A.GETLVL, A.FMT565, A.FMT555
A_BLEND = CAVE + 0x400
A_REBUILD = CAVE + 0x700
BASE_VA = DATA_VA + 0x40                 # 8 starry tiles, 565, then 555
TILE_B = 1056 * 2                        # 0x840
MIX_VA = BASE_VA + 2 * 8 * TILE_B        # 6 dwords 565, then 6 dwords 555 (mix_table)
RECIP_VA = MIX_VA + 48                   # 5 dwords: 256 / n for n = 0..4 source pixels

RESETVIS = 0x5570260C                    # thunk HSEPack!THSMap.ResetVisibleStaticHS
GETFIELD = 0x557020DC                    # thunk HSEPack!TMapLevel.GetField
COPYSTATIC = 0x5570203C                  # thunk HSEPack!TMapField.CopyStaticVisibleHS
RESETDYN = 0x55702614                    # thunk HSEPack!THSMap.ResetVisibleDynamicHS
COPYDYN = 0x55702034                     # thunk HSEPack!TMapField.CopyDynamicVisibleHS
ARMY_VMT = 0x557133A0                    # TArmyHS: armies are left out of the image
BORDER_VMT = 0x5579A458                  # TAoWBorderHexagon: the map edge is left out too
IAT_GETMEM = 0x558FB718                  # VCL30!System.@GetMem
IAT_FREEMEM = 0x558FB714                 # VCL30!System.@FreeMem

G = 0x558FAF00                           # BSS state
G_BUF, G_MW, G_MH, G_VALID, G_MAP, G_FMT, G_CAP = (G + 4 * i for i in range(7))
SC_N, SC_D = 3, 5                        # image scale SC_N / SC_D (owner: 0.6)
HEXP = 32 * SC_N                         # hex pitch in the image, x SC_D (96 / 5 = 19.2 px)
CHUNK = 15                               # hexes per chunk side; 15*32 = 480 px -> 288, a whole px count
SCR = CHUNK * 32                         # chunk side, px
MARGIN = 64                              # scratch border, px, rendered and thrown away
SCRW = SCR + 2 * MARGIN                  # scratch side, px
CM = SCR * SC_N // SC_D                  # chunk side in the image, px
assert SCR * SC_N % SC_D == 0
# column steps over one period of SC_N image px: source floor(SC_D * j / SC_N); each 1 or 2 px
COLSTEP = [(SC_D * (j + 1)) // SC_N - (SC_D * j) // SC_N for j in range(SC_N)]
assert set(COLSTEP) <= {1, 2}
# the tile must hold a whole px count of hexes, even across (the hex grid's column parity)
_q = SC_D // __import__("math").gcd(HEXP, SC_D)
QX, QY = _q * 2 // __import__("math").gcd(_q, 2), _q
SAVED = (0x88, 0x80, 0x84, 0x94, 0x98, 0x9C, 0xA0)
HAZE_RGB = (102, 112, 138)               # vanilla Ice (terrain 6) mean colour
HAZE = 0.55                              # Surface pushed this far toward HAZE_RGB
SURFACE_SHARE = 0.25                     # hazed Surface against the starry sky
PAR_SHIFT = 2                            # the Surface scrolls at 1 / 2**PAR_SHIFT of the sky's speed
# one exact mix per channel, weights /256: sky, Surface, haze colour
W_S = round(256 * (1 - SURFACE_SHARE))
W_C = round((256 - W_S) * (1 - HAZE))
W_H = 256 - W_S - W_C


def draw_list(off, tag):
    """the scene list at [map+off], back to front, through Show (vmt+0xA8), skipping armies and
    border hexagons"""
    return f"""        mov  eax, [esp]
        mov  eax, [eax+{off:#x}]
        mov  edx, [eax]
        call dword ptr [edx+0x90]
        mov  eax, [esp]
        mov  eax, [eax+{off:#x}]
        mov  ecx, [eax+0xC]
        mov  [esp+0x9C], ecx
    {tag}l:
        dec  dword ptr [esp+0x9C]
        js   {tag}done
        mov  eax, [esp]
        mov  eax, [eax+{off:#x}]
        mov  eax, [eax+0x14]
        mov  ecx, [esp+0x9C]
        mov  esi, [eax+ecx*8+4]
        mov  eax, [esi]
        lea  edx, [ebp + {ARMY_VMT:#x}]
        cmp  eax, edx
        je   {tag}l
        lea  edx, [ebp + {BORDER_VMT:#x}]
        cmp  eax, edx
        je   {tag}l
        mov  ebx, [esp]
        lea  edx, [esp+0x50]
        push edx
        mov  ecx, [ebx+0x84]
        mov  edx, [ebx+0x80]
        mov  eax, esi
        mov  edi, [eax]
        call dword ptr [edi+0xA8]
        jmp  {tag}l
    {tag}done:
"""


def build_cave(base555):
    # main frame (0x60): +0 map, +4 desc, +8 level, +10 col, +14 row end, +18 col end, +1C row,
    #   +20 base tiles, +28 KX, +2C KY, +34 tile width Px, +38 tile height Py, +40 u0, +48 mix table
    pop_at = CAVE + 9                    # pushad(1) + sub esp,0x60(3) + call(5)
    main = asm(f"""
        pushad
        sub  esp, 0x60
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
        lea  esi, [ebp + {BASE_VA:#x}]
        lea  ebx, [ebp + {MIX_VA:#x}]
        cmp  ecx, {FMT565:#x}
        je   fmtok
        lea  esi, [ebp + {base555:#x}]
        lea  ebx, [ebp + {MIX_VA + 24:#x}]
        cmp  ecx, {FMT555:#x}
        jne  out
    fmtok:
        mov  [esp+0x20], esi
        mov  [esp+0x48], ebx
        cmp  dword ptr [eax+0x88], {FIRMAMENT}
        je   onfirm
        mov  dword ptr [ebp + {G_VALID:#x}], 0
        jmp  out
    onfirm:
        cmp  [ebp + {G_MAP:#x}], eax
        jne  rebuild
        cmp  [ebp + {G_FMT:#x}], ecx
        jne  rebuild
        cmp  dword ptr [ebp + {G_VALID:#x}], 0
        jne  cached
    rebuild:
        call {A_REBUILD:#x}
    cached:
        cmp  dword ptr [ebp + {G_BUF:#x}], 0
        je   out
        mov  eax, [ebp + {G_MW:#x}]
        test eax, eax
        jz   out
        mov  [esp+0x34], eax
        mov  eax, [ebp + {G_MH:#x}]
        test eax, eax
        jz   out
        mov  [esp+0x38], eax
        mov  eax, [esp]
        mov  ecx, [eax+0x80]
        mov  edx, ecx
        sar  edx, {PAR_SHIFT}
        sub  ecx, edx
        mov  [esp+0x28], ecx
        mov  ecx, [eax+0x84]
        mov  edx, ecx
        sar  edx, {PAR_SHIFT}
        sub  ecx, edx
        mov  [esp+0x2C], ecx
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
        mov  eax, esi
        sub  eax, [esp+0x28]
        cdq
        idiv dword ptr [esp+0x34]
        test edx, edx
        jge  ux
        add  edx, [esp+0x34]
    ux:
        mov  [esp+0x40], edx
        mov  eax, edi
        sub  eax, [esp+0x2C]
        cdq
        idiv dword ptr [esp+0x38]
        test edx, edx
        jge  vx
        add  edx, [esp+0x38]
    vx:
        mov  eax, [esp+0x40]
        mov  ebx, [esp]
        sub  esi, [ebx+0x80]
        sub  edi, [ebx+0x84]
        mov  ebx, [esp+4]
        mov  ecx, esp
        call {A_BLEND:#x}
    nextrow:
        inc  dword ptr [esp+0x1C]
        jmp  rowloop
    nextcol:
        inc  dword ptr [esp+0x10]
        jmp  colloop
    out:
        add  esp, 0x60
        popad
        push ebx
        push esi
        mov  esi, edx
        mov  ebx, eax
        jmp  {RESUME:#x}
    """, CAVE)
    assert CAVE + len(main) <= A_BLEND, "cave_main outgrew its slot"

    # blend: esi/edi = screen origin of the hex, ebx = desc, eax = tile column of hex x=0 and
    # edx = tile row of hex y=0 (both already wrapped), ecx = main's frame.  frame (0x70):
    # +0 spans, +4 base cursor, +C y, +10 sox, +14 soy, +18 u0, +1C v0, +20 span len,
    # +24 span left, +28 tile row ptr, +2C Px, +30 Py, +4C sky px, +50 Surface px, +58 mix table,
    # +5C column save, +60 result.  Inside the pixel loop ebx is pushed: every offset reads +4.
    hits = "".join(f"        cmp  bx, word ptr [esi + {k * TILE_B:#x}]\n        je   hit\n" for k in range(8))

    def chan(i):
        m = 4 * i
        return f"""
        mov  eax, [esp+0x50]
        and  eax, [ebx+{m}]
        imul edx, eax, {W_S}
        mov  eax, [esp+0x54]
        and  eax, [ebx+{m}]
        imul eax, eax, {W_C}
        add  edx, eax
        add  edx, [ebx+{12 + m}]
        shr  edx, 8
        and  edx, [ebx+{m}]
        or   [esp+0x64], edx"""

    blend = asm(f"""
        pushad
        sub  esp, 0x70
        mov  [esp+0x10], esi
        mov  [esp+0x14], edi
        mov  [esp+0x18], eax
        mov  [esp+0x1C], edx
        mov  eax, [ecx+0x20]
        mov  [esp+4], eax
        mov  eax, [ecx+0x34]
        mov  [esp+0x2C], eax
        mov  eax, [ecx+0x38]
        mov  [esp+0x30], eax
        mov  eax, [ecx+0x48]
        mov  [esp+0x58], eax
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
        mov  edx, [esp+0x1C]
        add  edx, ecx
    vwrap:
        cmp  edx, [esp+0x30]
        jb   vok
        sub  edx, [esp+0x30]
        jmp  vwrap
    vok:
        imul edx, [esp+0x2C]
        shl  edx, 1
        add  edx, [ebp + {G_BUF:#x}]
        mov  [esp+0x28], edx
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
        mov  eax, [esp+0x18]
        add  eax, [esp+0x24]
        add  eax, edx
    uwrap:
        cmp  eax, [esp+0x2C]
        jb   uok
        sub  eax, [esp+0x2C]
        jmp  uwrap
    uok:
        push ebx
    inner:
        movzx ebx, word ptr [edi]
{hits}        jmp  sk
    hit:
        mov  [esp+0x60], eax
        mov  [esp+0x50], ebx
        mov  edx, [esp+0x2C]
        movzx edx, word ptr [edx+eax*2]
        test edx, edx
        jz   nocache
        mov  [esp+0x54], edx
        mov  dword ptr [esp+0x64], 0
        mov  ebx, [esp+0x5C]
{chan(0)}{chan(1)}{chan(2)}
        mov  eax, [esp+0x64]
        mov  [edi], ax
    nocache:
        mov  eax, [esp+0x60]
    sk:
        add  edi, 2
        add  esi, 2
        inc  eax
        cmp  eax, [esp+0x30]
        jb   nw
        xor  eax, eax
    nw:
        dec  ecx
        jnz  inner
        pop  ebx
    bnext:
        mov  eax, [esp+0x20]
        shl  eax, 1
        add  [esp+4], eax
        inc  dword ptr [esp+0xC]
        jmp  brow
    bdone:
        add  esp, 0x70
        popad
        ret
    """, A_BLEND)
    assert A_BLEND + len(blend) <= A_REBUILD, "blend outgrew its slot"

    # rebuild: eax = map, edx = back-buffer desc.  frame (0x100):
    #   +0 map, +4 desc, +8 level 0, +C cols, +10 rows, +14 scratch, +18 cx0, +1C cy0,
    #   +20..+38 saved map fields, +40 c_lo, +44 c_hi, +48 r_lo, +4C r_hi, +50..+8B record,
    #   +8C c, +90 r, +94 pixel, +98 field, +9C list index, +A0 Px, +A4 Py, +A8 size, +AC my0,
    #   +B0 my1, +B4 mx0, +B8 mx1, +BC my / fold row, +C0 1/n multiplier, +C4 column phase,
    #   +C8 X0, +CC Y0, +D0 UW, +D4 UH, +D8 unfolded image, +DC Xl, +E0 Xr, +E4 Yt, +E8 Yb
    save = "\n".join(f"        mov  ecx, [ebx+{o:#x}]\n        mov  [esp+{0x20 + 4 * i:#x}], ecx"
                     for i, o in enumerate(SAVED))
    restore = "\n".join(f"        mov  ecx, [esp+{0x20 + 4 * i:#x}]\n        mov  [ebx+{o:#x}], ecx"
                        for i, o in enumerate(SAVED))
    # 2x2 average over the non-empty source pixels only (no dark rim on the hex outline)
    chan = lambda m: f"""
        movzx eax, word ptr [esi]
        and  eax, [ebx+{m:#x}]
        movzx edx, word ptr [esi+2]
        and  edx, [ebx+{m:#x}]
        add  eax, edx
        movzx edx, word ptr [esi+{SCRW * 2:#x}]
        and  edx, [ebx+{m:#x}]
        add  eax, edx
        movzx edx, word ptr [esi+{SCRW * 2 + 2:#x}]
        and  edx, [ebx+{m:#x}]
        add  eax, edx
        imul eax, [esp+0xC0]
        shr  eax, 8
        and  eax, [ebx+{m:#x}]
        or   [esp+0x94], eax"""
    cnt = "".join(f"""
        cmp  word ptr [esi+{o:#x}], 0
        setne al
        add  edx, eax""" for o in (0, 2, SCRW * 2, SCRW * 2 + 2))

    def edges(tag, counts, n, other, first, last):
        """first and last index whose count exceeds a quarter of the other dimension"""
        return f"""
        mov  ebx, {counts}
        mov  eax, [esp+{other:#x}]
        shr  eax, 2
        mov  ecx, -1
    {tag}1:
        inc  ecx
        cmp  ecx, [esp+{n:#x}]
        jge  sfree
        cmp  [ebx+ecx*4], eax
        jle  {tag}1
        mov  [esp+{first:#x}], ecx
        mov  ecx, [esp+{n:#x}]
    {tag}2:
        dec  ecx
        cmp  [ebx+ecx*4], eax
        jle  {tag}2
        mov  [esp+{last:#x}], ecx"""

    extra = "".join(f"        cmp  eax, {j}\n        je   ph2\n" for j, st in enumerate(COLSTEP) if st == 2)

    def period(first, last, origin, per, q):
        """hexes across the interior from its measured extent (n hexes span n*p + p/2 px, p the hex
        pitch, less a few px the quarter threshold cuts off the slants): floor((extent + 1 + 3p/8) / p),
        rounded down to a multiple of q so the tile is a whole px count (and even across); a short
        count only overlaps columns, a long one would leave a gap"""
        return f"""
        mov  eax, [esp+{last:#x}]
        sub  eax, [esp+{first:#x}]
        add  eax, {1 + round(3 * HEXP / SC_D / 8)}
        imul eax, eax, {SC_D}
        xor  edx, edx
        mov  ecx, {HEXP}
        div  ecx
        xor  edx, edx
        mov  ecx, {q}
        div  ecx
        test eax, eax
        jz   sfree
        imul eax, eax, {q * HEXP // SC_D}
        mov  [esp+{per:#x}], eax
        mov  eax, [esp+{first:#x}]
        mov  [esp+{origin:#x}], eax"""

    rebuild = asm(f"""
        pushad
        sub  esp, 0x100
        mov  [esp], eax
        mov  [esp+4], edx
        mov  dword ptr [ebp + {G_VALID:#x}], 1
        mov  [ebp + {G_MAP:#x}], eax
        mov  ecx, [edx+0x28]
        mov  [ebp + {G_FMT:#x}], ecx
        mov  dword ptr [ebp + {G_MW:#x}], 0
        mov  dword ptr [ebp + {G_MH:#x}], 0
        mov  eax, [eax+0x10]
        mov  edx, {SURFACE}
        call {GETLVL:#x}
        test eax, eax
        jz   rdone
        mov  [esp+8], eax
        mov  ecx, [eax+0xC]
        mov  [esp+0xC], ecx
        mov  ecx, [eax+0x10]
        mov  [esp+0x10], ecx
        mov  eax, [esp+0xC]
        imul eax, eax, {HEXP}
        add  eax, {HEXP // 2 + SC_D - 1}
        xor  edx, edx
        mov  ecx, {SC_D}
        div  ecx
        inc  eax
        and  eax, -2
        mov  [esp+0xD0], eax
        mov  eax, [esp+0x10]
        imul eax, eax, {HEXP}
        add  eax, {HEXP // 2 + SC_D - 1}
        xor  edx, edx
        div  ecx
        mov  [esp+0xD4], eax
        imul eax, [esp+0xD0]
        shl  eax, 1
        mov  [esp+0xA8], eax
        call dword ptr [ebp + {IAT_GETMEM:#x}]
        test eax, eax
        jz   rdone
        mov  [esp+0xD8], eax
        mov  edi, eax
        mov  ecx, [esp+0xA8]
        shr  ecx, 2
        xor  eax, eax
        rep  stosd
        mov  eax, {SCRW * SCRW * 2:#x}
        call dword ptr [ebp + {IAT_GETMEM:#x}]
        test eax, eax
        jz   ufree
        mov  [esp+0x14], eax
        mov  esi, [esp+4]
        lea  edi, [esp+0x50]
        mov  ecx, 15
        rep  movsd dword ptr es:[edi], dword ptr [esi]
        mov  dword ptr [esp+0x50], {SCRW}
        mov  dword ptr [esp+0x54], {SCRW}
        mov  dword ptr [esp+0x58], 16
        mov  dword ptr [esp+0x5C], {SCRW * 2}
        mov  dword ptr [esp+0x60], 0
        mov  dword ptr [esp+0x64], 0
        mov  dword ptr [esp+0x68], {SCRW}
        mov  dword ptr [esp+0x6C], {SCRW}
        mov  eax, [esp+0x14]
        mov  [esp+0x70], eax
        mov  ebx, [esp]
{save}
        mov  dword ptr [esp+0x1C], 0
    cyl:
        mov  eax, [esp+0x1C]
        cmp  eax, [esp+0x10]
        jge  chunks_done
        mov  dword ptr [esp+0x18], 0
    cxl:
        mov  eax, [esp+0x18]
        cmp  eax, [esp+0xC]
        jge  cynext
        mov  edi, [esp+0x14]
        xor  eax, eax
        mov  ecx, {SCRW * SCRW // 2:#x}
        rep  stosd
        mov  eax, [esp+0x18]
        sub  eax, 4
        jge  w1
        xor  eax, eax
    w1:
        mov  [esp+0x40], eax
        mov  eax, [esp+0x18]
        add  eax, {CHUNK + 4}
        cmp  eax, [esp+0xC]
        jle  w2
        mov  eax, [esp+0xC]
    w2:
        mov  [esp+0x44], eax
        mov  eax, [esp+0x1C]
        sub  eax, 4
        jge  w3
        xor  eax, eax
    w3:
        mov  [esp+0x48], eax
        mov  eax, [esp+0x1C]
        add  eax, {CHUNK + 6}
        cmp  eax, [esp+0x10]
        jle  w4
        mov  eax, [esp+0x10]
    w4:
        mov  [esp+0x4C], eax
        mov  ebx, [esp]
        mov  dword ptr [ebx+0x88], {SURFACE}
        mov  eax, [esp+0x18]
        shl  eax, 5
        sub  eax, {MARGIN}
        mov  [ebx+0x80], eax
        mov  eax, [esp+0x1C]
        shl  eax, 5
        sub  eax, {MARGIN}
        mov  [ebx+0x84], eax
        mov  eax, [esp+0x40]
        mov  [ebx+0x94], eax
        mov  ecx, [esp+0x44]
        sub  ecx, eax
        mov  [ebx+0x9C], ecx
        mov  eax, [esp+0x48]
        mov  [ebx+0x98], eax
        mov  ecx, [esp+0x4C]
        sub  ecx, eax
        mov  [ebx+0xA0], ecx
        mov  eax, ebx
        call {RESETVIS:#x}
        mov  eax, ebx
        call {RESETDYN:#x}
        mov  eax, [esp+0x40]
        mov  [esp+0x8C], eax
    ccl:
        mov  eax, [esp+0x8C]
        cmp  eax, [esp+0x44]
        jge  cdone
        mov  eax, [esp+0x48]
        mov  [esp+0x90], eax
    rrl:
        mov  ecx, [esp+0x90]
        cmp  ecx, [esp+0x4C]
        jge  rend
        mov  edx, [esp+0x8C]
        mov  eax, [esp+8]
        call {GETFIELD:#x}
        test eax, eax
        jz   rnext
        mov  [esp+0x98], eax
        mov  edx, [esp]
        mov  edx, [edx+0x1C]
        call {COPYSTATIC:#x}
        mov  eax, [esp+0x98]
        mov  edx, [esp]
        mov  edx, [edx+0x20]
        call {COPYDYN:#x}
    rnext:
        inc  dword ptr [esp+0x90]
        jmp  rrl
    rend:
        inc  dword ptr [esp+0x8C]
        jmp  ccl
    cdone:
{draw_list(0x1C, "st")}{draw_list(0x20, "dy")}
        mov  eax, [esp+0x1C]
        imul eax, eax, {HEXP}
        xor  edx, edx
        mov  ecx, {SC_D}
        div  ecx
        mov  [esp+0xAC], eax
        mov  [esp+0xBC], eax
        add  eax, {CM}
        cmp  eax, [esp+0xD4]
        jle  d1
        mov  eax, [esp+0xD4]
    d1:
        mov  [esp+0xB0], eax
        mov  eax, [esp+0x18]
        imul eax, eax, {HEXP}
        xor  edx, edx
        mov  ecx, {SC_D}
        div  ecx
        mov  [esp+0xB4], eax
        add  eax, {CM}
        cmp  eax, [esp+0xD0]
        jle  d2
        mov  eax, [esp+0xD0]
    d2:
        mov  [esp+0xB8], eax
        mov  ebx, [esp+4]
    dsl:
        mov  eax, [esp+0xBC]
        cmp  eax, [esp+0xB0]
        jge  dsdone
        sub  eax, [esp+0xAC]
        imul eax, eax, {SC_D}
        xor  edx, edx
        mov  ecx, {SC_N}
        div  ecx
        imul eax, eax, {SCRW * 2}
        add  eax, [esp+0x14]
        add  eax, {(MARGIN * SCRW + MARGIN) * 2:#x}
        mov  esi, eax
        mov  eax, [esp+0xBC]
        imul eax, [esp+0xD0]
        add  eax, [esp+0xB4]
        shl  eax, 1
        add  eax, [esp+0xD8]
        mov  edi, eax
        mov  dword ptr [esp+0xC4], 0
        mov  ecx, [esp+0xB8]
        sub  ecx, [esp+0xB4]
        jle  dynext
    dxl:
        mov  dword ptr [esp+0x94], 0
        xor  eax, eax
        xor  edx, edx{cnt}
        test edx, edx
        jz   dskip
        mov  edx, [ebp + edx*4 + {RECIP_VA:#x}]
        mov  [esp+0xC0], edx
{chan(0x2C)}
{chan(0x30)}
{chan(0x34)}
        mov  eax, [esp+0x94]
        mov  [edi], ax
    dskip:
        add  edi, 2
        add  esi, 2
        mov  eax, [esp+0xC4]
{extra}        jmp  ph1
    ph2:
        add  esi, 2
    ph1:
        inc  eax
        cmp  eax, {SC_N}
        jb   ph
        xor  eax, eax
    ph:
        mov  [esp+0xC4], eax
        dec  ecx
        jnz  dxl
    dynext:
        inc  dword ptr [esp+0xBC]
        jmp  dsl
    dsdone:
        add  dword ptr [esp+0x18], {CHUNK}
        jmp  cxl
    cynext:
        add  dword ptr [esp+0x1C], {CHUNK}
        jmp  cyl
    chunks_done:
        mov  ebx, [esp]
{restore}
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0xD8]
        mov  eax, [esp]
        mov  edx, [eax]
        call dword ptr [edx+0xDC]
        mov  edi, [esp+0x14]
        mov  ecx, [esp+0xD0]
        add  ecx, [esp+0xD4]
        xor  eax, eax
        rep  stosd
        mov  esi, [esp+0xD8]
        mov  ebx, [esp+0x14]
        mov  edx, [esp+0xD0]
        lea  edi, [ebx+edx*4]
        xor  edx, edx
    scy:
        cmp  edx, [esp+0xD4]
        jge  scdone
        xor  ecx, ecx
    scx:
        cmp  word ptr [esi], 0
        je   scz
        inc  dword ptr [ebx+ecx*4]
        inc  dword ptr [edi+edx*4]
    scz:
        add  esi, 2
        inc  ecx
        cmp  ecx, [esp+0xD0]
        jl   scx
        inc  edx
        jmp  scy
    scdone:
{edges("ex", "[esp+0x14]", 0xD0, 0xD4, 0xDC, 0xE0)}
        mov  eax, [esp+0xD0]
        shl  eax, 2
        add  eax, [esp+0x14]
{edges("ey", "eax", 0xD4, 0xD0, 0xE4, 0xE8)}
{period(0xDC, 0xE0, 0xC8, 0xA0, QX)}
{period(0xE4, 0xE8, 0xCC, 0xA4, QY)}
        mov  eax, [esp+0xA0]
        imul eax, [esp+0xA4]
        shl  eax, 1
        mov  [esp+0xA8], eax
        cmp  eax, [ebp + {G_CAP:#x}]
        jbe  havebuf
        mov  eax, [ebp + {G_BUF:#x}]
        test eax, eax
        jz   nofree
        call dword ptr [ebp + {IAT_FREEMEM:#x}]
    nofree:
        mov  dword ptr [ebp + {G_BUF:#x}], 0
        mov  dword ptr [ebp + {G_CAP:#x}], 0
        mov  eax, [esp+0xA8]
        call dword ptr [ebp + {IAT_GETMEM:#x}]
        test eax, eax
        jz   sfree
        mov  [ebp + {G_BUF:#x}], eax
        mov  ecx, [esp+0xA8]
        mov  [ebp + {G_CAP:#x}], ecx
    havebuf:
        mov  edi, [ebp + {G_BUF:#x}]
        mov  ecx, [esp+0xA8]
        shr  ecx, 2
        xor  eax, eax
        rep  stosd
        mov  dword ptr [esp+0xBC], 0
        mov  esi, [esp+0xD8]
    fy:
        mov  eax, [esp+0xBC]
        cmp  eax, [esp+0xD4]
        jge  fdone
        sub  eax, [esp+0xCC]
        cdq
        idiv dword ptr [esp+0xA4]
        test edx, edx
        jge  f3
        add  edx, [esp+0xA4]
    f3:
        mov  eax, edx
        imul eax, [esp+0xA0]
        shl  eax, 1
        add  eax, [ebp + {G_BUF:#x}]
        mov  edi, eax
        mov  eax, [esp+0xC8]
        neg  eax
        cdq
        idiv dword ptr [esp+0xA0]
        test edx, edx
        jge  f4
        add  edx, [esp+0xA0]
    f4:
        mov  ebx, [esp+0xA0]
        mov  ecx, [esp+0xD0]
    fx:
        movzx eax, word ptr [esi]
        test eax, eax
        jz   fn
        cmp  word ptr [edi+edx*2], 0
        jne  fn
        mov  [edi+edx*2], ax
    fn:
        add  esi, 2
        inc  edx
        cmp  edx, ebx
        jb   f5
        xor  edx, edx
    f5:
        dec  ecx
        jnz  fx
        inc  dword ptr [esp+0xBC]
        jmp  fy
    fdone:
        mov  eax, [esp+0xA0]
        mov  [ebp + {G_MW:#x}], eax
        mov  eax, [esp+0xA4]
        mov  [ebp + {G_MH:#x}], eax
    sfree:
        mov  eax, [esp+0x14]
        call dword ptr [ebp + {IAT_FREEMEM:#x}]
    ufree:
        mov  eax, [esp+0xD8]
        call dword ptr [ebp + {IAT_FREEMEM:#x}]
    rdone:
        add  esp, 0x100
        popad
        ret
    """, A_REBUILD)
    assert A_REBUILD + len(rebuild) <= DATA_VA, "rebuild outgrew its slot"
    return [("cave_main", CAVE, main), ("blend", A_BLEND, blend), ("rebuild", A_REBUILD, rebuild)]


def mix_table():
    """per format: 3 channel masks, 3 x (haze colour * W_H + half a channel step)"""
    r, g, b = HAZE_RGB
    out = b""
    for masks, hz in (((0xF800, 0x07E0, 0x001F), ((r >> 3) << 11, (g >> 2) << 5, b >> 3)),
                      ((0x7C00, 0x03E0, 0x001F), ((r >> 3) << 10, (g >> 3) << 5, b >> 3))):
        rnd = [(m & -m) << 7 for m in masks]          # half a channel step, before >> 8
        out += struct.pack("<6I", *masks, *(h * W_H + q for h, q in zip(hz, rnd)))
    return out


def build_data(hss):
    tiles = A.sky_tiles(hss)
    assert len(tiles) == 8, "expected 8 Sky tiles, found %d" % len(tiles)
    trs = {t[4] for t in tiles}
    assert len(trs) == 1, "Sky tiles disagree on the transparent colour"
    tr = trs.pop()
    rows8, mask = [], None
    for off, data, w, h, t in tiles:
        assert (w, h) == (48, 32)
        rows, _ = decode(data, w, h, t)
        m = [[p is not None for p in r] for r in rows]
        if mask is None:
            mask = m
        assert m == mask, "Sky tiles differ in silhouette"
        rows8.append(rows)
    spans = A.spans_of(mask)
    assert sum(r - l for l, r in spans) == 1056
    sp = b"".join(bytes([l, r]) for l, r in spans).ljust(0x40, b"\0")
    t565 = t555 = b""
    for rows in rows8:
        px = [v for y, (l, r) in enumerate(spans) for v in rows[y][l:r]]
        t565 += struct.pack("<1056H", *px)
        t555 += struct.pack("<1056H", *(A.to555(v, tr) for v in px))
    mix = mix_table()
    recip = struct.pack("<5I", 0, 256, 128, 86, 64)    # 86: 3 x 86 / 256 never drops a step
    blob = sp + t565 + t555 + mix + recip
    assert DATA_VA + len(sp + t565 + t555) == MIX_VA and DATA_VA + len(blob) - len(recip) == RECIP_VA
    return blob, BASE_VA + len(t565)


def main():
    ap = argparse.ArgumentParser(description="Firmament Sky over the Surface, hazed, wrapping")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    data_blob, base555 = build_data(open(HSS, "rb").read())
    blobs = build_cave(base555)
    blobs.append(("data", DATA_VA, data_blob))
    assert DATA_VA + len(data_blob) <= SLOT[1]
    print("build_sky_parallax: data %d B, code %s, slot %08X-%08X"
          % (len(data_blob), ", ".join("%s %d B" % (n, len(b)) for n, _v, b in blobs if n != "data"),
             SLOT[0], SLOT[1]))
    if a.dis:
        P.show([b for b in blobs if b[0] != "data"])

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
        sys.exit("ABORT: the hook is installed but the slot is not this script's "
                 "(build_sky_anim / build_sky_mosaic, or an earlier build of this one?)")
    if any(zone) and not blobs_in and hst == "vanilla":
        sys.exit("ABORT: slot is not zero and not ours")
    if P.relocs_in(d, HOOK, HOOK + 6) or P.relocs_in(d, SLOT[0], SLOT[1]):
        sys.exit("ABORT: .reloc entry under the hook or slot")
    if P.rel32_into(d, HOOK, HOOK + 6) or P.short_into(d, HOOK, HOOK + 6, HOOK, HOOK + 0xE0):
        sys.exit("ABORT: a jump lands inside the hook")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    P.kill_aow()
    d[zo:zh] = bytes(zh - zo)
    if a.apply:
        for _n, va, b in blobs:
            p = P.va2off(d, va)
            d[p:p + len(b)] = b
    d[o:o + 6] = hook_new if a.apply else HOOK_ORIG
    try:
        open(P.TARGET, "wb").write(d)
    except PermissionError:
        sys.exit("LOCKED -- close AoWz.exe / AoWzEd.exe and retry")
    print("\n%s" % ("APPLIED: Firmament Sky shows the Surface below" if a.apply
                    else "UNDONE: hook and slot restored"))


if __name__ == "__main__":
    main()
