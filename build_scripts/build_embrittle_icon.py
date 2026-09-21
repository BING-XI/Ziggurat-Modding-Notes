# -*- coding: utf-8 -*-
r"""
build_embrittle_icon.py — a "broken bone" spell icon for Embrittlement, written into
Images/SpellIcn.ILB by REUSING a dead entry, with no format surgery.

    python build_scripts/build_embrittle_icon.py            dry run + verify
    python build_scripts/build_embrittle_icon.py --apply     write it
    python build_scripts/build_embrittle_icon.py --undo      restore the vanilla entry
    python build_scripts/build_embrittle_icon.py --png <dir> render before/after previews

TARGET: Images/SpellIcn.ILB ONLY. No binary is touched.

────────────────────────────────────────────────────────────────────────────────────────────
WHY ENTRY 128, AND WHY THIS IS NOT AN APPEND
────────────────────────────────────────────────────────────────────────────────────────────
SpellIcn.ILB holds 111 top-level entries with ids 0..155. Exactly 108 are referenced by a
spell (Spells.pfs tag 0x0C -> "SPELLICN.ILB" + a u32 index). **Three are dead: 128, 129, 155.**
128 is a Dragon silhouette on a Cosmos-purple disc — cut content, referenced by nothing.

Appending a 112th entry would mean rewriting the directory, every `off` field after the
insertion point and the `imgdir` header — a format-surgery project. Overwriting a dead entry
in place needs **none of that**: the three writes below are all exact-size, so the directory,
every offset and the file length are untouched. It is also trivially reversible.

⚠ `Images/SpellIcn.ILB` has no other owner — `grep -rlni spellicn build_scripts/` was empty
on 2026-09-01. That is what makes a whole-entry rewrite safe here; do not assume it for any
other data file.

────────────────────────────────────────────────────────────────────────────────────────────
THE THREE WRITES
────────────────────────────────────────────────────────────────────────────────────────────
An icon is a COMPOSITE: a 40x35 frame (the sphere-coloured disc) plus one sub-entry holding
the artwork, inset at the sub's clip origin. Both are Sprite16 (type 22): pixel data is
UNCOMPRESSED RGB565 of the clip rectangle, exactly clipw*cliph*2 bytes. See
re_tools/spell_icons.py for the full format derivation.

  1. frame pixels   @0x8B4C5, 2800 B  <- copied verbatim from icon 52 (Slow), i.e. the real
                                         SI-Earth.BMP disc. Read from the live file at apply
                                         time rather than embedded, so it always matches
                                         whatever Earth frame is actually installed.
  2. frame transparent field @0x4FFD, 4 B   0x00000000 -> 0x00004148
  3. sub pixels     @0x8BFB5, 1972 B (34x29) <- the broken bone from ART below.

⚠ WRITE 2 IS NOT COSMETIC. Icon 128's frame declares transparent = 0x0000 (pure black) while
the Earth frame contains **113 pure-black pixels**. Any blitter that honours the colour key
would punch 113 holes through the disc. Every Earth icon declares 0x4148 — a value absent
from its own pixels, i.e. "key nothing, this is an opaque background" — so matching it makes
the new entry behave byte-for-byte like a known-good Earth icon instead of relying on an
assumption about whether the game honours the field. (re_tools/spell_icons.py concluded the
field is unusable for RENDERING and ignores it; that is a statement about the tool, not a
guarantee about the engine. Don't rely on it.)

The sub keeps its own transparent = 0xFFFF: the artwork's background is exactly that value,
so it drops out and the disc shows through. The ink itself is anti-aliased greyscale --
see THE ART below, and do not "clean it up" to 1-bit.

────────────────────────────────────────────────────────────────────────────────────────────
THE ART
────────────────────────────────────────────────────────────────────────────────────────────
ART below is the literal 34x29 stamp, one character per pixel, using the RAMP table: '.' is
white (keyed transparent), '#' is solid black, and ':' '-' '+' '*' are the intermediate greys
that produce the soft outline. It is deliberately stored as text rather than regenerated from
drawing code: it is reviewable in the diff, editable by hand with any text editor, and immune
to a PIL version changing its resampling and silently altering the shipped artwork.

⚠ **THE ART IS ANTI-ALIASED, AND MUST BE.** v1 of this script shipped a 1-bit stamp on the
strength of spell_icons.py's note that "25 pixels in the entire file are off-grey" — that says
off-NEUTRAL (not on the r=g=b axis), NOT "not black or white", and reading it the second way is
what produced a hard-edged icon that visibly did not match its neighbours. Measured over all
110 vanilla overlays (133,984 px):

    black (<32)   23,200   17.3%
    MID (32-223)  18,835   14.1%      <- the soft, semi-black outline
    white (>223)  91,949   68.6%

Per-icon the mid-tone share runs 8-17% (Slow 8.1, Entangle 7.9, Tremors 10.1, Stone Skin 11.9).
This stamp is 16% black / 8.0% mid, inside that band. The engine evidently composites these by
luminance rather than by a pure colour key, which is also why spell_icons.py's ink_alpha()
renders them correctly.

⚠ White must stay EXACTLY 0xFFFF — that is the sub-entry's declared transparent value, so any
pixel meant to disappear has to hit it exactly. RAMP['.'] = 255 does (r=31,g=63,b=31).
"""
import os, sys, struct, shutil, zlib, base64, hashlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ILB = os.path.join(GAME, "Images", "SpellIcn.ILB")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ILB) + ".pre-embrittleicon")

ICON_ID = 128               # the dead entry being reused
DONOR_ID = 52               # icon 52 = Slow: the real SI-Earth.BMP disc

# --- patch points, measured with re_tools/spell_icons.py (walk() reports clip_off) ---------
FRAME_PIX_OFF, FRAME_PIX_LEN = 0x8B4C5, 2800        # 40x35 RGB565
FRAME_TRANSP_OFF = 0x4FFD                           # the frame's transparent dword
SUB_PIX_OFF, SUB_PIX_LEN = 0x8BFB5, 1972            # 34x29 RGB565
SUB_W, SUB_H = 34, 29
DONOR_FRAME_PIX_OFF = 0x3E8F5                       # icon 52's frame pixels

TRANSP_VANILLA = 0x00000000
TRANSP_EARTH = 0x00004148                           # what every real Earth frame declares

# Character -> 8-bit neutral grey. '#' solid ink ... '.' background (must be exactly 0xFFFF).
RAMP = {"#": 0, "*": 56, "+": 112, "-": 160, ":": 208, ".": 255}

# --- the stamp: 34 wide, 29 tall. See THE ART above -- greys are the soft outline. ----------
ART = [
    "..................................",
    "..................................",
    "..................................",
    ".....+#*-.........................",
    "....+####:........................",
    "....#####-........................",
    "....#####-........................",
    "...:+####.........................",
    "..*######*:.......................",
    ".+#########+......................",
    ".###########*-....................",
    ".*####*#######*:..................",
    ".:###*.:*#######+.................",
    "..:--....-#######*:...............",
    "..........:+####+::*+:............",
    "............-*+:.-####*-....-**-..",
    "...............:########*-.:####+.",
    "...............:+##########*#####.",
    "..................-*#############.",
    "....................-*##########-.",
    "......................:+######*-..",
    ".........................+####:...",
    ".........................+####*...",
    ".........................*####*...",
    ".........................-####-...",
    "..........................-**-....",
    "..................................",
    "..................................",
    "..................................",
]

# v1's 1-bit stamp, kept so verify-before-write recognises an already-installed older build and
# REWRITES IT IN PLACE rather than refusing. Append here whenever the art changes; never replace.
#   v1 (2026-09-01): hard-edged, and the knobs were too broad. Both noted by the author on sight.
PRIOR_ART = [[
    "..................................", "........####......................",
    ".......######.....................", ".......######.....................",
    ".......######.....................", ".......######.....................",
    "...##########.....................", "..##########......................",
    "..##########......................", "..###########.....................",
    "..############....................", "...#####..#####...................",
    "...........#####..................", "............#####.................",
    ".............#####................", "..................##..............",
    "...............#######....#####...", "................########..######..",
    ".................###############..", "...................#############..",
    ".....................###########..", "......................#########...",
    ".......................#####......", "......................######......",
    "......................#######.....", "......................######......",
    ".......................#####......", "........................###.......",
    "..................................",
]]


def stamp(art):
    """A character grid -> RGB565 little-endian bytes for the sub-entry."""
    assert len(art) == SUB_H, "art must be %d rows, got %d" % (SUB_H, len(art))
    out = bytearray()
    for y, row in enumerate(art):
        assert len(row) == SUB_W, "art row %d is %d chars, expected %d" % (y, len(row), SUB_W)
        for ch in row:
            assert ch in RAMP, "art may only use %r, found %r" % ("".join(RAMP), ch)
            g = RAMP[ch]
            out += struct.pack("<H", ((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3))
    assert len(out) == SUB_PIX_LEN, "art is %d B, slot is %d B" % (len(out), SUB_PIX_LEN)
    return bytes(out)


def art_pixels():
    px = stamp(ART)
    assert struct.unpack_from("<H", px, 0)[0] == 0xFFFF, \
        "the top-left pixel must be exactly 0xFFFF -- it is the declared transparent value"
    return px


def read(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def wanted(d):
    """-> [(offset, new bytes, description)] for the three writes, given the live file."""
    return [
        (FRAME_PIX_OFF, bytes(d[DONOR_FRAME_PIX_OFF:DONOR_FRAME_PIX_OFF + FRAME_PIX_LEN]),
         "frame pixels <- icon %d (SI-Earth.BMP disc)" % DONOR_ID),
        (FRAME_TRANSP_OFF, struct.pack("<I", TRANSP_EARTH),
         "frame transparent %#010x -> %#010x (match the Earth icons)"
         % (TRANSP_VANILLA, TRANSP_EARTH)),
        (SUB_PIX_OFF, art_pixels(), "sub pixels <- the broken-bone stamp (%dx%d)"
         % (SUB_W, SUB_H)),
    ]


# --- the vanilla entry, so --undo needs no backup file -------------------------------------
# zlib+base64 of icon 128's original frame pixels (2800 B) followed by its original sub
# pixels (1972 B) -- the Cosmos disc and the Dragon silhouette. Embedded rather than restored
# from .pre-embrittleicon so the revert path survives the backup being pruned, which is this
# project's standing rule for every feature.
ORIG_B64 = (
"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"
)


def originals():
    raw = zlib.decompress(base64.b64decode(ORIG_B64))
    assert len(raw) == FRAME_PIX_LEN + SUB_PIX_LEN
    assert hashlib.sha256(raw).hexdigest().startswith("742620b2329b1434"), \
        "embedded vanilla blob failed its own hash check"
    return [(FRAME_PIX_OFF, raw[:FRAME_PIX_LEN], "frame pixels <- vanilla Cosmos disc"),
            (FRAME_TRANSP_OFF, struct.pack("<I", TRANSP_VANILLA), "frame transparent restored"),
            (SUB_PIX_OFF, raw[FRAME_PIX_LEN:], "sub pixels <- vanilla Dragon silhouette")]


def state(d):
    """'applied' | 'vanilla' | 'stale' (an older build of ours) | 'FOREIGN'.

    'stale' exists so re-cutting the artwork is a REWRITE IN PLACE. Only FOREIGN aborts --
    that means something outside this feature edited the entry.
    """
    if all(bytes(d[o:o + len(b)]) == b for o, b, _ in wanted(d)):
        return "applied"
    if all(bytes(d[o:o + len(b)]) == b for o, b, _ in originals()):
        return "vanilla"
    frame_ok = (bytes(d[FRAME_PIX_OFF:FRAME_PIX_OFF + FRAME_PIX_LEN])
                == bytes(d[DONOR_FRAME_PIX_OFF:DONOR_FRAME_PIX_OFF + FRAME_PIX_LEN]))
    transp_ok = bytes(d[FRAME_TRANSP_OFF:FRAME_TRANSP_OFF + 4]) == struct.pack("<I", TRANSP_EARTH)
    cur = bytes(d[SUB_PIX_OFF:SUB_PIX_OFF + SUB_PIX_LEN])
    if frame_ok and transp_ok and any(cur == stamp(a) for a in PRIOR_ART):
        return "stale"
    return "FOREIGN"


def show():
    d = read(ILB)
    st = state(d)
    print("build_embrittle_icon -- broken-bone icon in SpellIcn.ILB entry %d" % ICON_ID)
    print("target: %s" % GAME)
    print()
    for o, b, desc in wanted(d):
        cur = "applied" if bytes(d[o:o + len(b)]) == b else "not applied"
        print("  %08X  %-11s  %s" % (o, cur, desc))
    print()
    print("  entry %d state: %s   (file %d B, unchanged by this patch)" % (ICON_ID, st.upper(), len(d)))
    n = SUB_W * SUB_H
    lv = [RAMP[c] for r in ART for c in r]
    blk = sum(1 for v in lv if v < 32)
    mid = sum(1 for v in lv if 32 <= v <= 223)
    print("  art: %dx%d, black %d (%.0f%%), anti-aliased mid-tone %d (%.1f%%)"
          % (SUB_W, SUB_H, blk, 100.0 * blk / n, mid, 100.0 * mid / n))
    print("       vanilla overlays pooled: 17.3% black / 14.1% mid; per-icon mid runs 8-17%")
    return st


def preview(outdir):
    """Render the entry as the game composites it, before and after, at 8x."""
    sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
    import spell_icons as si
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    d = read(ILB)
    for label, patches in (("before", originals()), ("after", wanted(d))):
        t = bytearray(d)
        for o, b, _ in patches:
            t[o:o + len(b)] = b
        t = bytes(t)
        entries, base = si.walk(t)
        top, subs = next((a, b) for a, b in entries if a["id"] == ICON_ID)
        img = si.render(t, top, subs, base)
        p = os.path.join(outdir, "icon128_%s.png" % label)
        img.resize((img.width * 8, img.height * 8), Image.NEAREST).save(p)
        print("  wrote %s" % p)


def apply(undo=False):
    d = read(ILB)
    st = state(d)
    if st == "FOREIGN":
        sys.exit("ABORT: entry %d holds neither the vanilla art nor ours -- someone else "
                 "edited SpellIcn.ILB (verify-before-write)" % ICON_ID)
    want = "vanilla" if undo else "applied"
    if st == want:
        print("  already %s -- nothing to do" % want)
        return
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(ILB, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    before = len(d)
    for o, b, desc in (originals() if undo else wanted(d)):
        d[o:o + len(b)] = b
    assert len(d) == before, "file length changed -- this patch must be size-neutral"
    with open(ILB, "wb") as f:
        f.write(d)
    print("  SpellIcn.ILB entry %d %s (%d B, length unchanged)"
          % (ICON_ID, "REVERTED" if undo else "PATCHED", before))
    print()
    if not undo:
        print("  The icon is in the file. It is NOT yet attached to the spell: that needs")
        print("  Spells.pfs record 119 (= spell 109 + 10) with tag 0x0C -> SPELLICN.ILB, %d."
              % ICON_ID)
        print("  Rebuild the contact sheet to see it in place:")
        print("      python \"Modding Resources/re_tools/spell_icons.py\"")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--png" in sys.argv:
        show(); preview(sys.argv[sys.argv.index("--png") + 1])
    elif "--undo" in args:
        show(); apply(undo=True)
    elif "--apply" in args:
        show(); apply()
    else:
        show()
        print()
        print("(dry run -- nothing written.  --apply to patch, --undo to revert,")
        print(" --png <dir> to render before/after previews)")
