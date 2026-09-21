#!/usr/bin/env python3
r"""
AoW1 -- spellbook hover-glow: stronger AND taller (BookWin.ILB image 26 "SBBtn.BMP").

Two data edits, both idempotent, no other image disturbed:

1. INTENSITY. The glow draws via TLibraryImage.Show's dispatch: img+0x38 = 2 -> jumptable on
   img+0x39 (0=explicit table, 1=Alpha, 3=Intensity, 4=Shadow, 5=LinearAlpha) with the percent
   at img+0x3C. Image 26 is mode 2/3 = INTENSITY (a brightening blend) at 20% -- which on bright
   parchment is nearly invisible. Raised to 70%.

2. HEIGHT. The button draws the strip UNSCALED (TInterfaceIL.DrawILI -> ShowClipped), so the
   highlight can only be as tall as the stored image: 254x82. Our research entries are 104px
   tall, so a wrapped second name line ("Poison / Plants", "Disease / Cloud") fell outside it.
   The pixel data is RAW 16-bit (stored size 41656 == 254*82*2), so we rebuild it 254xNEW_H by
   duplicating a middle row (keeps the soft top/bottom edges), APPEND the new data at EOF
   and repoint the record's data offset -- every other image keeps its offset untouched.

Record layout (verified against this file; offsets are for image 26's record @0xA50):
  +0x16 idx | +0x1A classid | +0x1E ver(3) | namelen+name | w1 @0xA66 | h1 @0xA6A | ...
  | size @0xA7B | dataoff @0xA7F | w2 @0xA83 | h2 @0xA87 | showinfo @0xA8B (mode bytes) +
  pct @0xA8F | pixfmt @0xA93 (0x56509310) | w3 @0xA97 | h3 @0xA9B | ... | FFFFFFFF
NB: the taller sprite only shows if the slot panel/button rects allow it -- build_tierresearch_exe
sets both to HILITE_H in research mode (cast mode keeps vanilla).

Backup: BookWin.ILB.pre-glowilb. Dry-run by default; --apply to write.
"""
import shutil, sys, struct, os

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ILB  = os.path.join(GAME, "Int", "Scenes", "BookWin.ILB")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ILB) + ".pre-glowilb")

O_W1, O_H1 = 0xA66, 0xA6A
O_SIZE, O_DATAOFF = 0xA7B, 0xA7F
O_W2, O_H2 = 0xA83, 0xA87
O_MODE, O_PCT, O_PIXFMT = 0xA8B, 0xA8F, 0xA93
O_W3, O_H3 = 0xA97, 0xA9B

WIDTH   = 254
OLD_H   = 82
NEW_H   = 100     # must match HILITE_H in build_tierresearch_exe.py
PCT     = 0x46    # 70% intensity
BPP     = 2

def u32(d, o): return struct.unpack_from("<I", d, o)[0]
def p32(d, o, v): struct.pack_into("<I", d, o, v)

def main():
    d = bytearray(open(ILB, 'rb').read())
    # sanity: this must be the image we think it is
    if u32(d, O_PIXFMT) != 0x56509310 or u32(d, O_W1) != WIDTH or u32(d, O_MODE) != 0x0302:
        print("ABORT: image-26 record does not match the expected layout."); return 1

    h, pct, size, off = u32(d, O_H1), u32(d, O_PCT), u32(d, O_SIZE), u32(d, O_DATAOFF)
    print(f"image 26: {WIDTH}x{h}, intensity {pct}%, data {size}B @ {off:#x}")
    if h == NEW_H and pct == PCT:
        print("already applied."); return 0
    if h != OLD_H and h != NEW_H:
        print(f"ABORT: unexpected height {h}"); return 1
    if h == OLD_H and size != WIDTH * OLD_H * BPP:
        print(f"ABORT: data size {size} != raw {WIDTH*OLD_H*BPP} (not raw pixels?)"); return 1

    print(f"  intensity {pct}% -> {PCT}%" + ("" if pct != PCT else " (unchanged)"))
    if h == OLD_H:
        print(f"  height {OLD_H} -> {NEW_H} (+{NEW_H-OLD_H} duplicated middle rows), "
              f"data moved to EOF {len(d):#x}")
    if '--apply' not in sys.argv:
        print("Dry run OK. Re-run with --apply to write."); return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copyfile(ILB, BACKUP); print(f"backup -> {BACKUP}")

    p32(d, O_PCT, PCT)
    if h == OLD_H:
        stride = WIDTH * BPP
        rows = [bytes(d[off + i*stride: off + (i+1)*stride]) for i in range(OLD_H)]
        mid = OLD_H // 2
        newrows = rows[:mid] + [rows[mid]] * (NEW_H - OLD_H) + rows[mid:]
        assert len(newrows) == NEW_H
        newoff = len(d)
        d.extend(b"".join(newrows))
        p32(d, O_DATAOFF, newoff)
        p32(d, O_SIZE, WIDTH * NEW_H * BPP)
        for o in (O_H1, O_H2, O_H3):
            p32(d, o, NEW_H)
    open(ILB, 'wb').write(d)
    print("applied.")
    return 0

sys.exit(main())
