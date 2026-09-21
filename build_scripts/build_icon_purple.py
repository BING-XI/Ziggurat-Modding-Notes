#!/usr/bin/env python3
r"""
ZIGGURAT EXE ICON  --  purple dragon, mirrored.  `Ziggurat\AoWz.exe` + `AoWzCompat.exe`
(names from `zigexe.py`).  ⚠ The exe is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from
`Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step;
that script is retired.)

WHAT IT DOES
  Recolours the application icon's two reds to purple and mirrors the image
  horizontally, so the Ziggurat executable is distinguishable at a glance from the
  vanilla `AoW.exe` at the game root.  The 2026-09-09 rename to `AoWz.exe` happened after
  this was written and cost the resource nothing -- it travels with the file.

THE RESOURCE
  The exe carries exactly ONE icon: RT_ICON id 1, file 0x00073AEC, 744 bytes,
  reached from RT_GROUP_ICON id 6360.  Layout is a plain icon image:

      BITMAPINFOHEADER   40 B   biWidth 32, biHeight 64 (= 32 image + 32 mask), 4bpp
      palette            64 B   16 x BGRA
      XOR bitmap        512 B   32 rows x 16 B, 4bpp, BOTTOM-UP
      AND mask          128 B   32 rows x 4 B, 1bpp, BOTTOM-UP, 1 = transparent
                        ------
                        744 B

  Nothing changes size, so this is an in-place .rsrc write: no directory rebuild, no
  section growth, no SizeOfImage edit.

THE PALETTE
  The icon ships the stock Windows 16-colour palette, but only six entries are ever
  visible (measured over the 536 opaque pixels):

      idx  0  #000000  227 px   outline
      idx  1  #800000  141 px   body shading      -> #3A006B
      idx  9  #FF0000  113 px   body              -> #A838E8
      idx  3  #808000   31 px   spine, dark       kept
      idx 11  #FFFF00   20 px   spine, highlight  kept
      idx  8  #808080    4 px                     kept

  Only the two reds move.  The spine stays gold deliberately: a uniform hue rotation
  sends yellow to pink, which loses the highlight against the new purple and reads as
  a wash.  Black, grey and the transparent field are hue-free and unaffected.

  ⚠ There is no white in this icon -- index 15 is unused.  The pale S-curve inside the
  dragon's coil is the TRANSPARENT field showing through (488 px), not a drawn glyph,
  so mirroring costs nothing there.  (It looks like a letter in a preview rendered on a
  light background; it is not one.)

THE FLIP
  Both bitmaps are mirrored left-to-right.  The XOR bitmap is 4bpp, so a row reverses
  by nibble, not by byte; the AND mask is 1bpp and reverses by bit.  Row ORDER is left
  alone -- these are bottom-up bitmaps and a horizontal flip does not touch that.

LOCKSTEP
  `AoWzCompat.exe` is `AoWz.exe` with one byte changed (file 0x3BB7C, 0x0F -> 0x05), so
  it gets the identical edit -- see CLAUDE.md.  The script asserts the two files differ
  in exactly that one byte before writing and again afterwards; if that ever fails,
  stop, because the lockstep assumption has broken somewhere else.

--undo restores the original palette entries and un-mirrors both bitmaps.  The flip is
its own inverse, so --undo is exact and the round trip is byte-identical.

Needs no third-party packages.  `--png <path>` writes a preview and wants Pillow.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)
BACKUP_DIR = os.path.join(GAME, "backups")

TARGETS = list(zigexe.EXES)
COMPAT_BYTE = zigexe.COMPAT_BYTE   # the one byte AoWzCompat.exe differs by

ICON_OFF = 0x00073AEC
ICON_LEN = 744
W = H = 32
PAL_OFF = 40
XOR_OFF = 40 + 64
AND_OFF = XOR_OFF + 512

# palette index -> (vanilla RGB, ziggurat RGB)
RECOLOUR = {
    1: ((0x80, 0x00, 0x00), (0x3A, 0x00, 0x6B)),
    9: ((0xFF, 0x00, 0x00), (0xA8, 0x38, 0xE8)),
}


def get_pal(d, i):
    b, g, r, a = struct.unpack_from("<BBBB", d, ICON_OFF + PAL_OFF + i * 4)
    return (r, g, b)


def set_pal(d, i, rgb):
    r, g, b = rgb
    struct.pack_into("<BBBB", d, ICON_OFF + PAL_OFF + i * 4, b, g, r, 0)


def flip_xor(d):
    for y in range(H):
        row = ICON_OFF + XOR_OFF + y * 16
        px = []
        for x in range(W):
            byte = d[row + x // 2]
            px.append((byte >> 4) if x % 2 == 0 else (byte & 0xF))
        px.reverse()
        for x in range(0, W, 2):
            d[row + x // 2] = (px[x] << 4) | px[x + 1]


def flip_and(d):
    for y in range(H):
        row = ICON_OFF + AND_OFF + y * 4
        bits = []
        for x in range(W):
            bits.append((d[row + x // 8] >> (7 - x % 8)) & 1)
        bits.reverse()
        for x in range(0, W, 8):
            v = 0
            for k in range(8):
                v = (v << 1) | bits[x + k]
            d[row + x // 8] = v


def is_patched(d):
    """Palette is the state marker; the flip has no fingerprint of its own."""
    van = all(get_pal(d, i) == a for i, (a, b) in RECOLOUR.items())
    zig = all(get_pal(d, i) == b for i, (a, b) in RECOLOUR.items())
    if van:
        return False
    if zig:
        return True
    return None


def preview(d, path):
    try:
        from PIL import Image
    except ImportError:
        sys.exit("--png needs Pillow")
    im = Image.new("RGBA", (W, H))
    for y in range(H):
        for x in range(W):
            src = ICON_OFF + XOR_OFF + (H - 1 - y) * 16 + x // 2
            idx = (d[src] >> 4) if x % 2 == 0 else (d[src] & 0xF)
            m = (d[ICON_OFF + AND_OFF + (H - 1 - y) * 4 + x // 8] >> (7 - x % 8)) & 1
            im.putpixel((x, y), (0, 0, 0, 0) if m else get_pal(d, idx) + (255,))
    im.resize((256, 256), Image.NEAREST).save(path)
    print("  preview -> %s" % path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--png", metavar="PATH", help="write a 256x256 preview of current state")
    args = ap.parse_args()
    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")

    paths = [os.path.join(GAME, t) for t in TARGETS]
    blobs = []
    for p in paths:
        if not os.path.isfile(p):
            sys.exit("missing: %s" % p)
        blobs.append(bytearray(open(p, "rb").read()))

    # lockstep precondition
    a, b = blobs
    diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    if len(a) != len(b) or diff != [COMPAT_BYTE]:
        sys.exit("!! %s / %s differ at %d bytes (%s), expected only 0x%X -- stop"
                 % (TARGETS[0], TARGETS[1], len(diff),
                    [hex(x) for x in diff[:6]], COMPAT_BYTE))
    print("lockstep ok: the two exes differ only at 0x%X" % COMPAT_BYTE)

    states = [is_patched(x) for x in blobs]
    if None in states:
        sys.exit("!! icon palette is neither vanilla nor ziggurat -- someone else edited it")
    if states[0] != states[1]:
        sys.exit("!! the two exes are in different icon states -- fix by hand")
    patched = states[0]
    print("icon state: %s" % ("ZIGGURAT (purple, mirrored)" if patched else "vanilla"))

    if args.png:
        preview(blobs[0], args.png)

    want = not args.undo
    if patched == want:
        print("nothing to do -- already in the requested state.")
        return
    if not (args.apply or args.undo):
        print("dry run.  Re-run with --apply (or --undo) to write.")
        return

    # ⚠ the mod exes were renamed AoWz*/AoWzEd on 2026-09-09; a list that stops at AoW/AoWCompat/
    # AoWDevEd/AoWEd cannot release a lock held by AoWz.exe or AoWzEd.exe. Single source:
    # zigexe.LOCKING_PROCESSES.
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } "
                    "| Stop-Process -Force" % "|".join(zigexe.LOCKING_PROCESSES)],
                   capture_output=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    for p, d in zip(paths, blobs):
        bk = os.path.join(BACKUP_DIR, os.path.basename(p) + ".pre-purpleicon")
        # `want and ...` is already a POSITIVE unpatched test, not a "no backup file yet" gate:
        # control only reaches here with patched != want, so want=True implies is_patched() said
        # the palette is still vanilla. Keep it that way -- never snapshot on --undo.
        if want and not os.path.exists(bk):
            shutil.copyfile(p, bk)
            print("  backup -> backups\\%s" % os.path.basename(bk))
        for i, (van, zig) in RECOLOUR.items():
            set_pal(d, i, zig if want else van)
        flip_xor(d)
        flip_and(d)
        open(p, "wb").write(d)
        print("  %s: palette %s, bitmaps mirrored"
              % (os.path.basename(p), "-> purple" if want else "-> vanilla red"))

    a2 = bytearray(open(paths[0], "rb").read())
    b2 = bytearray(open(paths[1], "rb").read())
    d2 = [i for i in range(len(a2)) if a2[i] != b2[i]]
    print("  verify: state=%s, lockstep diff=%s"
          % ("ZIGGURAT" if is_patched(a2) else "vanilla", [hex(x) for x in d2]))


if __name__ == "__main__":
    main()
