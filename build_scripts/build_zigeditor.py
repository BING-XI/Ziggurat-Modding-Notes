#!/usr/bin/env python3
r"""
ZIGGURAT-ORIENTED EDITOR  --  creates `Ziggurat\AoWzEd.exe`, purple dragon, mirrored.

LAYOUT -- BOTH FILES LIVE IN `GAME`, WHICH *IS* THE MOD DIRECTORY  (fixed 2026-09-10)
  `GAME` = `__file__/../..` = `<root>\Ziggurat\`.  Source and destination are siblings
  inside it:

      SRC = GAME\AoWDevEd.exe      the editor patch source; every editor build script
                                   (dlgdirs, modtoolbar, terrainpal, ...) patches THIS
      DST = GAME\AoWzEd.exe        the live editor the owner runs

  This script predates the 2026-09-09 move, when `GAME` was the game ROOT and the mod
  was a subdirectory of it.  Two constants survived the move and were both wrong:

    * `SUBDIR = GAME\Ziggurat` -> `<root>\Ziggurat\Ziggurat`, which does not exist.  The
      script hard-exited with "does not exist -- build the overlay first" before writing
      anything, so the editor could not be rebuilt at all.  There is no separate overlay
      directory to populate any more; `GAME` is it.
    * `STAGING = GAME\Ziggurat release`, and the source exe was read from there.
      ⚠⚠ That tree is RELEASE STAGING, refreshed by `re_tools/mod_manifest.py --stage`.
      CLAUDE.md: it is **never a patch source**.  Building the editor from it silently
      discards every editor patch applied since the last staging refresh -- the build
      succeeds, the icons are right, and the patches are simply gone.  It was latent only
      because the two copies happened to be byte-identical (md5 d32abcb1) on the day.
      The constant is deleted rather than corrected, so nothing here can reach staging.

  Binary names come from `zigexe.py`, not from literals here.

WHY IT NEEDS NO IMPORT PATCHING
  Everything Ziggurat runs lives INSIDE `Ziggurat\`, so the application directory *is*
  `Ziggurat\` and every package resolves there already -- no import surgery for the editor
  or for the game. (Until 2026-09-09 the game exes sat at the vanilla root with rewritten
  import names; `build_overlay.py` did that and is retired. See `12-re-toolchain.md` 13a.)

  For that to hold, `Ziggurat\` must be self-contained.  It carries all **33** packages --
  the 6 modified ones plus copies of the rest:

      cp -n *.dpl *.dll Ziggurat/        # then, and this is the easy half to forget:
      cp -n *.DPL      Ziggurat/

  ⚠⚠ **Git Bash globbing is CASE-SENSITIVE, and this install has nine UPPERCASE Delphi
  packages** -- `IBEVNT30.DPL`, `QRPT30.DPL`, `TEE30.DPL`, `TEEDB30.DPL`, `TEEUI30.DPL`,
  `VCLDB30.DPL`, `VCLDBX30.DPL`, `VCLSMP30.DPL`, `VCLX30.DPL`.  `*.dpl` matches none of
  them.  The editor imports `vclx30` and pulls in `vcldb30`, so the first build died at
  once with `STATUS_DLL_NOT_FOUND` and no indication of which module was missing.  NTFS
  itself is case-insensitive, so the game finds them fine; only the copy was short.
  `-n` (no-clobber) is load-bearing in both commands -- reversed, vanilla would overwrite
  the 6 modified packages.  Verified after copying: all 6 still match their modded hashes.

  ⚠ Do NOT "tidy" the unmodified packages out of `Ziggurat\`.  Measured live: the editor
  maps **18 packages, all from `Ziggurat\` and none from the top level**.

DATA AND REGISTRY -- automatic, nothing to set
  `Ziggurat\AoWzEd.exe` loads `Ziggurat\AoWEPACK.dpl`, which carries `build_regiso.py`'s
  patch, so it reads the `Age of Wonders Z` tree and picks up
  `Startup Directory = <game>\Ziggurat\`.  It therefore edits the MOD's data.  The
  top-level `AoWDevEd.exe` loads the vanilla packages, reads the plain
  `Age of Wonders` key, and edits VANILLA data -- left exactly as it is, per the owner's
  instruction 2026-09-09.

  ⚠ Both editors are the SAME modded binary (`AoWDevEd.exe`, an *added* file the vanilla
  installer never touched, so it survived the 2026-09-09 reinstall).  They differ only in
  which folder they run from, which is what decides the packages and therefore the data.
  That is deliberate: the top-level one keeps this project's editor improvements
  (render gate, terrain palette, validation goto, hero prune) while pointing at vanilla
  content.

⚠ THE EDITOR HAS **TWO** DRAGONS, IN TWO DIFFERENT FORMATS
  Recolouring one leaves the other untouched, which is what happened on the first pass
  (owner-caught 2026-09-09: the shell icon changed, the title bar stayed red).

  **1. The shell / taskbar icon** -- `RT_ICON` id 1, file 0x0446C4, 4264 bytes:
  40 B BITMAPINFOHEADER + 4096 B XOR (32x32, **32bpp BGRA**, bottom-up) + 128 B AND mask,
  no palette.  Art is a greyscale dragon over a green hex cluster.

  **2. The TITLE-BAR icon** -- the MainForm's DFM `Icon.Data` property, a whole embedded
  `.ico` file: 22 B ICO header then a 744 B payload that is 32x32 **4bpp with a 16-entry
  palette**, byte-identical in format to the GAME icon.  Art is the plain RED game dragon.
  It appears **8 times** in the DFM (one per form that shows it), all byte-identical:

      0x0471AA  0x047667  0x047DE7  0x06BD5B  0x074C0C  0x0D6303  0x0DC710  0x129C04

  0x074C0C is `sMDIForm`, the main window -- the one the owner saw.  All 8 are recoloured
  so child windows match.  Two nearby ICOs are deliberately LEFT ALONE: 0x0466F4 (red
  dragon over BLUE hexes, the stock AoWEd art) and 0x0C012F (a green icon, another form).
  They are found by payload MD5, not by offset, and the script asserts it found exactly 8.

  ⚠ Do not reuse one format's icon code for the other: #1 is per-pixel BGRA, #2 is a
  palette edit.

RECOLOURING, PER OWNER'S SPEC 2026-09-09 -- "dragon purple, not the hexes"
  #1: pixels with saturation <= 0.20 (the greyscale dragon) are mapped onto a purple ramp
  at hue **282 deg**: saturation `0.80*(1-v) + 0.35*v` so darks go rich and highlights go
  pastel, and value floored at **0.16** so the near-black silhouette becomes dark purple
  instead of staying black.  431 of the 664 opaque pixels are greyscale.
  ⚠ The green hexes (152 px), red outline (54 px) and yellow accents (27 px) are all
  ABOVE the saturation gate and are deliberately untouched -- an earlier version did the
  opposite (hexes purple, dragon grey) and was corrected.
  Alpha is preserved byte-for-byte; only R/G/B move.

  Both are ALSO MIRRORED left-to-right (owner 2026-09-09), matching AoWz.exe.
  #2: a palette edit, the same two entries as the game icon --
  `#800000 -> #3A006B` and `#FF0000 -> #A838E8`, olive/yellow spine kept as accent.
  ⚠ At 4bpp a row mirrors by NIBBLE, not by byte -- two pixels share a byte, so reversing
  bytes alone swaps every adjacent pair straight back. Row ORDER is untouched: a
  horizontal flip does not affect bottom-up storage.

REVERT
  `--undo` DELETES `GAME\AoWzEd.exe`.  There is nothing surgical to do: the file is a
  whole derived artefact, rebuilt from `AoWDevEd.exe` on every `--apply`, so removing it
  and re-running `--apply` is the complete round trip.  It touches no snapshot.

STATUS: applied 2026-09-09, UNTESTED in the editor itself (it launches; nobody has
opened a map).  Checklist in `Zig notes/11-engine-internals.md`.
⚠ The on-disk `AoWzEd.exe` (built 2026-09-09 20:50) was produced by the pre-fix script,
i.e. from the STAGING copy.  It is only trustworthy while staging and `GAME` agree; re-run
`--apply` after any editor patch to be sure it carries them.  The path fix above is
SOURCE-ONLY -- as of 2026-09-10 nothing has been rebuilt from it.

Needs Pillow only for `--png`; the recolour itself uses colorsys from the stdlib.
"""
import argparse
import colorsys
import os
import struct
import sys

import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# ⚠ `GAME` IS the mod directory -- do not join a "Ziggurat" or "Ziggurat release"
# component onto it.  See LAYOUT in the docstring.
SRC = zigexe.SRC_EDITOR             # AoWDevEd.exe -- patch source, in GAME
DST = zigexe.LIVE_EDITOR            # AoWzEd.exe   -- live editor, in GAME

ICON_OFF = 0x0446C4
ICON_LEN = 4264
W = H = 32
XOR_OFF = 40

SAT_GATE = 0.20                     # at or below this = the greyscale dragon
PURPLE_HUE = 282.0
VALUE_FLOOR = 0.16                  # so the near-black silhouette is not left black

# the title-bar icon: 32x32 4bpp, the plain RED game dragon, 8 copies in the DFM
DFM_ICON_MD5 = "a81ad2e4"           # first 8 hex of md5 over the 744 B payload
DFM_PAYLOAD = 744
DFM_HDR = 22                        # ICO header before the BITMAPINFOHEADER
RECOLOUR_PAL = {1: (0x3A, 0x00, 0x6B), 9: (0xA8, 0x38, 0xE8)}


def tint_dragon(d):
    """#1 -- BGRA per-pixel. Greyscale -> purple ramp; saturated art untouched."""
    n = 0
    for i in range(W * H):
        p = ICON_OFF + XOR_OFF + i * 4
        b, g, r, a = d[p], d[p + 1], d[p + 2], d[p + 3]
        if a < 32:
            continue
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        if s > SAT_GATE:
            continue                                    # hexes, outline, accents
        ns = 0.80 * (1 - v) + 0.35 * v
        nv = max(v, VALUE_FLOOR)
        r2, g2, b2 = colorsys.hsv_to_rgb(PURPLE_HUE / 360.0, ns, nv)
        d[p] = int(b2 * 255 + 0.5)
        d[p + 1] = int(g2 * 255 + 0.5)
        d[p + 2] = int(r2 * 255 + 0.5)
        n += 1
    return n


def flip_bgra(d):
    """#1 -- mirror the 32bpp XOR bitmap and its 1bpp AND mask, left to right."""
    for y in range(H):
        row = ICON_OFF + XOR_OFF + y * W * 4
        px = [bytes(d[row + x * 4:row + x * 4 + 4]) for x in range(W)]
        px.reverse()
        d[row:row + W * 4] = b"".join(px)
    ao = ICON_OFF + XOR_OFF + W * H * 4
    for y in range(H):
        row = ao + y * 4
        bits = [(d[row + x // 8] >> (7 - x % 8)) & 1 for x in range(W)]
        bits.reverse()
        for x in range(0, W, 8):
            v = 0
            for k in range(8):
                v = (v << 1) | bits[x + k]
            d[row + x // 8] = v


def flip_4bpp(d, body):
    """#2 -- mirror one embedded .ico: 4bpp XOR by NIBBLE, AND mask by bit.

    ⚠ At 4bpp a row does not reverse by byte -- two pixels share a byte, so reversing
    bytes alone leaves every adjacent pair swapped back. Unpack to nibbles first."""
    xo = body + 40 + 64
    for y in range(H):
        row = xo + y * 16
        px = []
        for x in range(W):
            byte = d[row + x // 2]
            px.append((byte >> 4) if x % 2 == 0 else (byte & 0xF))
        px.reverse()
        for x in range(0, W, 2):
            d[row + x // 2] = (px[x] << 4) | px[x + 1]
    ao = xo + 512
    for y in range(H):
        row = ao + y * 4
        bits = [(d[row + x // 8] >> (7 - x % 8)) & 1 for x in range(W)]
        bits.reverse()
        for x in range(0, W, 8):
            v = 0
            for k in range(8):
                v = (v << 1) | bits[x + k]
            d[row + x // 8] = v


def recolour_titlebar(d):
    """#2 -- find every embedded red-dragon .ico by payload MD5 and repalette it."""
    import hashlib
    hits = []
    start = 0
    sig = b"\x00\x00\x01\x00\x01\x00\x20\x20\x10"       # ICONDIR + 32x32, 16 colours
    while True:
        o = d.find(sig, start)
        if o < 0:
            break
        start = o + 1
        size = struct.unpack_from("<I", d, o + 14)[0]
        if size != DFM_PAYLOAD:
            continue
        body = o + DFM_HDR
        if hashlib.md5(bytes(d[body:body + DFM_PAYLOAD])).hexdigest()[:8] != DFM_ICON_MD5:
            continue                                    # a different icon -- leave it
        for idx, (r, g, b) in RECOLOUR_PAL.items():
            struct.pack_into("<BBBB", d, body + 40 + idx * 4, b, g, r, 0)
        flip_4bpp(d, body)
        hits.append(o)
    return hits


def preview(d, path):
    try:
        from PIL import Image
    except ImportError:
        sys.exit("--png needs Pillow")
    im = Image.new("RGBA", (W, H))
    for y in range(H):
        for x in range(W):
            p = ICON_OFF + XOR_OFF + ((H - 1 - y) * W + x) * 4
            im.putpixel((x, y), (d[p + 2], d[p + 1], d[p], d[p + 3]))
    im.resize((256, 256), Image.NEAREST).save(path)
    print("  preview -> %s" % path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true", help="delete Ziggurat\\AoWzEd.exe")
    ap.add_argument("--png", metavar="PATH")
    args = ap.parse_args()

    out = os.path.join(GAME, DST)
    if args.undo:
        if os.path.isfile(out):
            os.remove(out)
            print("removed %s" % out)
        else:
            print("nothing to remove")
        return

    # `GAME` must be the MOD tree, not the vanilla root.  Anchor on contents, not on
    # depth: `Modding Resources\` exists only inside `Ziggurat\`.  The one way this goes
    # wrong is AOW_GAME_DIR being set -- CLAUDE.md says leave it unset.
    if not os.path.isdir(os.path.join(GAME, "Modding Resources")):
        sys.exit("!! %s is not the mod directory (no 'Modding Resources' in it) -- "
                 "GAME must be <root>\\Ziggurat; is AOW_GAME_DIR set?" % GAME)

    src = os.path.join(GAME, SRC)
    if not os.path.isfile(src):
        sys.exit("!! missing %s -- the source editor must sit beside the packages in %s"
                 % (src, GAME))
    print("src: %s" % src)
    print("dst: %s" % out)

    d = bytearray(open(src, "rb").read())
    hdr = struct.unpack_from("<IiiHH", d, ICON_OFF)
    if hdr[1] != W or hdr[2] != H * 2 or hdr[4] != 32:
        sys.exit("!! icon at 0x%X is %dx%d %dbpp, expected %dx%d 32bpp"
                 % (ICON_OFF, hdr[1], hdr[2] // 2, hdr[4], W, H))
    print("icon ok: %dx%d %dbpp at 0x%X" % (hdr[1], hdr[2] // 2, hdr[4], ICON_OFF))

    n = tint_dragon(d)
    flip_bgra(d)
    print("  shell icon : %d greyscale pixels -> purple ramp (hue %g, floor %g), mirrored"
          % (n, PURPLE_HUE, VALUE_FLOOR))
    hits = recolour_titlebar(d)
    print("  title bar  : %d embedded .ico copies repaletted + mirrored %s"
          % (len(hits), " ".join("0x%06X" % h for h in hits)))
    if len(hits) != 8:
        print("  !! expected 8 red-dragon icons, found %d -- the DFM layout has changed;"
              % len(hits))
        print("     re-derive them before trusting this build")
        if args.apply:
            sys.exit(2)
    if args.png:
        preview(d, args.png)

    missing = [m for m in ("AoWEPACK.dpl", "vcl30.dpl", "Localize.dpl", "EngineP.dpl",
                           "ILToolsP.dpl", "VCLADDON.dpl", "AOWTools.dpl")
               if not os.path.isfile(os.path.join(GAME, m))]
    if missing:
        print("  !! %s is missing these packages: %s" % (GAME, ", ".join(missing)))
        print("     from the GAME ROOT run:  cp -n *.dpl *.dll Ziggurat/ ;"
              "  cp -n *.DPL Ziggurat/")
        if args.apply:
            sys.exit(2)
    else:
        print("  packages   : all 7 required packages present in %s" % GAME)

    if not args.apply:
        print("\ndry run.  Would write %s" % out)
        return
    open(out, "wb").write(d)
    print("  wrote %s (%d bytes)" % (out, len(d)))


if __name__ == "__main__":
    main()
