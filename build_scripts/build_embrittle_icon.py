# -*- coding: utf-8 -*-
r"""
build_embrittle_icon.py — a "cracked bone" spell icon for Embrittlement, written into
Images/SpellIcn.ILB and its half-resolution twin Images/_SpellIcn.ILB by REUSING the dead
entry 128 in each, with no format surgery.

    python build_scripts/build_embrittle_icon.py            dry run + verify
    python build_scripts/build_embrittle_icon.py --apply     write it
    python build_scripts/build_embrittle_icon.py --undo      restore the vanilla entry
    python build_scripts/build_embrittle_icon.py --png <dir> render before/after previews

TARGETS: Images/SpellIcn.ILB and Images/_SpellIcn.ILB. No binary is touched.

────────────────────────────────────────────────────────────────────────────────────────────
WHY ENTRY 128, AND WHY THIS IS NOT AN APPEND
────────────────────────────────────────────────────────────────────────────────────────────
In the shipped SpellIcn.ILB, 108 entries were referenced by a spell (Spells.pfs tag 0x0C ->
"SPELLICN.ILB" + a u32 index) and three were dead: 128, 129, 155. 128 is a Dragon silhouette
on a Cosmos-purple disc — cut content, referenced by nothing. Overwriting it in place keeps
every write exact-size: the directory and the file length are untouched, and it is reversible.

⚠ ENTRY 128'S PIXELS MOVE. build_dual_spell_icons.py inserts directory records, which pushes
the image data (and so every pixel offset) further into the file; build_regen_spell_icon.py
owns entry 129. The offsets are therefore found by walking the file (re_tools/spell_icons.py)
on every run, never stored. The 2026-09-01 version stored them and read FOREIGN by 2026-10-27.
The directory record itself (and its transparent dword) has not moved: inserted records go
after it.

────────────────────────────────────────────────────────────────────────────────────────────
THE THREE WRITES, PER TWIN
────────────────────────────────────────────────────────────────────────────────────────────
An icon is a COMPOSITE: a frame (the sphere-coloured disc; 40x35 in SpellIcn.ILB, 20x18 in
_SpellIcn.ILB) plus one sub-entry holding the artwork, a 34x29 clip at (2, 3) of a 40x35 box
in BOTH twins. Both are Sprite16 (type 22): UNCOMPRESSED RGB565 of the clip rectangle.

  1. frame pixels  <- copied from the SAME twin's icon 52 (Slow), the real SI-Earth.BMP disc,
                      read at apply time so it matches whatever Earth frame is installed.
  2. frame transparent dword (directory record, clip_off + 16) <- 0x00004148.
  3. sub pixels    <- the cracked bone from ART below.

⚠ WRITE 2 IS NOT COSMETIC. Icon 128's frame declares transparent = 0x0000 (pure black) while
the Earth frame contains pure-black pixels; a blitter that honours the key would punch holes
through the disc. Every Earth icon declares 0x4148, a value absent from its own pixels, so
matching it makes the entry behave like a known-good Earth icon.

The sub keeps its own transparent = 0xFFFF: the artwork's background is exactly that value,
so it drops out and the disc shows through.

Revert: the SpellIcn.ILB originals are embedded below (the vanilla root's SpellIcn.ILB has no
entry 128); the _SpellIcn.ILB originals are read from the vanilla root's _SpellIcn.ILB.

────────────────────────────────────────────────────────────────────────────────────────────
THE ART
────────────────────────────────────────────────────────────────────────────────────────────
ART below is the literal 34x29 stamp, one character per pixel, using the RAMP table: '.' is
white (keyed transparent), '#' is solid black, and ':' '-' '+' '*' are the intermediate greys
that produce the soft outline. It is stored as text so it is reviewable in the diff and immune
to a PIL version changing its resampling.

⚠ **THE ART IS ANTI-ALIASED, AND MUST BE.** Over all 110 vanilla overlays: black (<32) 17.3%,
mid (32-223) 14.1%, white 68.6%; per-icon mid runs 8-17%. A 1-bit stamp (v1) visibly did not
match its neighbours. v3 is 16.0% black / 10.9% mid.

⚠ White must stay EXACTLY 0xFFFF — the sub-entry's declared transparent value. RAMP['.'] = 255
does (r=31, g=63, b=31).

History (the owner's picks): v1 2026-09-01 hard-edged, knobs too broad. v2 anti-aliased, but
edge to edge and the break hard to see. v3 2026-10-27, draft C of four: a smaller whole bone
with a white branching crack along the shaft.
"""
import os, sys, struct, shutil, zlib, base64, hashlib, importlib.util

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ROOT = os.path.dirname(GAME)                 # the vanilla install, reference for the half twin
TOOLS = os.path.join(GAME, "Modding Resources", "re_tools")
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TWINS = [os.path.join(GAME, "Images", "SpellIcn.ILB"), os.path.join(GAME, "Images", "_SpellIcn.ILB")]
ILB = TWINS[0]
SUFFIX = ".pre-embrittleicon"

ICON_ID = 128               # the dead entry being reused
DONOR_ID = 52               # icon 52 = Slow: the real SI-Earth.BMP disc
SUB_W, SUB_H = 34, 29
SUB_CLIP = [SUB_W, SUB_H, 2, 3]
SUB_PIX_LEN = SUB_W * SUB_H * 2

TRANSP_VANILLA = 0x00000000
TRANSP_EARTH = 0x00004148                           # what every real Earth frame declares

# Character -> 8-bit neutral grey. '#' solid ink ... '.' background (must be exactly 0xFFFF).
RAMP = {"#": 0, "*": 56, "+": 112, "-": 160, ":": 208, ".": 255}

# --- the stamp: 34 wide, 29 tall. See THE ART above -- greys are the soft outline. ----------
ART = [
    "..................................",
    "........--........................",
    "......:###*:......................",
    "......*####+......................",
    ".....:#####*......................",
    "......#####+......................",
    "....::-####-......................",
    "...+##*+####+.....................",
    "..-##########*:...................",
    "..*########*-##-..................",
    "..+########*.+##+.................",
    "..:####+*###::####-...............",
    "...:+*-..+##+.-+++::..............",
    "..........-##.....-#*:............",
    "...........:+:###::###-...........",
    ".............:###-.####+..........",
    "..............:*#*.:--*#*:.:+*+...",
    "................+#:::.+###+*###+..",
    ".................-:*############:.",
    "...................*############:.",
    "....................+###########..",
    ".....................:*####+###:..",
    ".......................*###*::....",
    "......................:#####-.....",
    "......................-#####+.....",
    "......................:#####-.....",
    ".......................-###+......",
    "........................:-:.......",
    "..................................",
]
# Earlier builds, so verify-before-write recognises an installed older one and REWRITES IT IN
# PLACE rather than refusing. Append here whenever the art changes; never replace.
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
PRIOR_ART.append(
[
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
])


def si():
    spec = importlib.util.spec_from_file_location("spell_icons", os.path.join(TOOLS, "spell_icons.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


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


def locate(d):
    """Walk the file -> (frame off, frame len, transparent off, sub off, donor frame off)."""
    entries, base = si().walk(bytes(d))
    by = {t["id"]: (t, s) for t, s in entries}
    top, subs = by[ICON_ID]
    donor = by[DONOR_ID][0]
    assert len(subs) == 1 and subs[0]["clip"] == SUB_CLIP and subs[0]["size"] == SUB_PIX_LEN, \
        "entry %d's sub is not the %dx%d clip at (2, 3)" % (ICON_ID, SUB_W, SUB_H)
    assert top["size"] == donor["size"] and (top["w"], top["h"]) == (donor["w"], donor["h"]), \
        "entry %d's frame and icon %d's differ in size" % (ICON_ID, DONOR_ID)
    return base + top["off"], top["size"], top["clip_off"] + 16, base + subs[0]["off"], base + donor["off"]


def wanted(d):
    """-> [(offset, new bytes, description)] for the three writes, given the live file."""
    fo, fl, to, so, do = locate(d)
    return [
        (fo, bytes(d[do:do + fl]), "frame pixels <- icon %d (SI-Earth.BMP disc)" % DONOR_ID),
        (to, struct.pack("<I", TRANSP_EARTH),
         "frame transparent %#010x -> %#010x (match the Earth icons)" % (TRANSP_VANILLA, TRANSP_EARTH)),
        (so, art_pixels(), "sub pixels <- the cracked-bone stamp (%dx%d)" % (SUB_W, SUB_H)),
    ]


# --- SpellIcn.ILB's vanilla entry, so --undo needs no backup file ---------------------------
# zlib+base64 of icon 128's original frame pixels (2800 B) followed by its original sub
# pixels (1972 B) -- the Cosmos disc and the Dragon silhouette.
ORIG_B64 = (
"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"
)

def originals(path, d):
    fo, fl, to, so, _do = locate(d)
    if os.path.basename(path).startswith("_"):
        r = read(os.path.join(ROOT, "Images", os.path.basename(path)))
        rfo, rfl, rto, rso, _r = locate(r)
        assert rfl == fl, "the vanilla root's half-res frame is another size"
        assert bytes(r[rto:rto + 4]) == struct.pack("<I", TRANSP_VANILLA)
        frame, sub = bytes(r[rfo:rfo + rfl]), bytes(r[rso:rso + SUB_PIX_LEN])
    else:
        raw = zlib.decompress(base64.b64decode(ORIG_B64))
        assert hashlib.sha256(raw).hexdigest().startswith("742620b2329b1434"), \
            "embedded vanilla blob failed its own hash check"
        assert len(raw) == fl + SUB_PIX_LEN
        frame, sub = raw[:fl], raw[fl:]
    return [(fo, frame, "frame pixels <- vanilla Cosmos disc"),
            (to, struct.pack("<I", TRANSP_VANILLA), "frame transparent restored"),
            (so, sub, "sub pixels <- vanilla Dragon silhouette")]


def state(path, d):
    """'applied' | 'vanilla' | 'stale' (an older build of ours) | 'FOREIGN'.

    'stale' exists so re-cutting the artwork is a REWRITE IN PLACE. Only FOREIGN aborts --
    that means something outside this feature edited the entry.
    """
    match = lambda ws: all(bytes(d[o:o + len(b)]) == b for o, b, _ in ws)
    w = wanted(d)
    if match(w):
        return "applied"
    if match(originals(path, d)):
        return "vanilla"
    so = w[2][0]
    if match(w[:2]) and any(bytes(d[so:so + SUB_PIX_LEN]) == stamp(a) for a in PRIOR_ART):
        return "stale"
    return "FOREIGN"


def show():
    print("build_embrittle_icon -- cracked-bone icon in entry %d of both SpellIcn twins" % ICON_ID)
    print("target: %s" % GAME)
    states = {}
    for path in TWINS:
        d = read(path)
        print()
        print("  %s" % os.path.basename(path))
        for o, b, desc in wanted(d):
            cur = "applied" if bytes(d[o:o + len(b)]) == b else "not applied"
            print("    %08X  %-11s  %s" % (o, cur, desc))
        states[path] = state(path, d)
        print("    entry %d state: %s" % (ICON_ID, states[path].upper()))
    n = SUB_W * SUB_H
    lv = [RAMP[c] for r in ART for c in r]
    blk = sum(1 for v in lv if v < 32)
    mid = sum(1 for v in lv if 32 <= v <= 223)
    print()
    print("  art: %dx%d, black %d (%.0f%%), anti-aliased mid-tone %d (%.1f%%)"
          % (SUB_W, SUB_H, blk, 100.0 * blk / n, mid, 100.0 * mid / n))
    print("       vanilla overlays pooled: 17.3% black / 14.1% mid; per-icon mid runs 8-17%")
    return states


def preview(outdir):
    """Render the full-size entry as the game composites it, before and after, at 8x."""
    S = si()
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    d = read(ILB)
    for label, patches in (("before", originals(ILB, d)), ("after", wanted(d))):
        t = bytearray(d)
        for o, b, _ in patches:
            t[o:o + len(b)] = b
        t = bytes(t)
        entries, base = S.walk(t)
        top, subs = next((a, b) for a, b in entries if a["id"] == ICON_ID)
        img = S.render(t, top, subs, base)
        p = os.path.join(outdir, "icon128_%s.png" % label)
        img.resize((img.width * 8, img.height * 8), Image.NEAREST).save(p)
        print("  wrote %s" % p)


def apply(undo=False):
    files = {p: read(p) for p in TWINS}
    for p, d in files.items():
        if state(p, d) == "FOREIGN":
            sys.exit("ABORT: %s entry %d holds neither the vanilla art nor ours -- someone else "
                     "edited it (verify-before-write)" % (os.path.basename(p), ICON_ID))
    want = "vanilla" if undo else "applied"
    for p, d in files.items():
        name = os.path.basename(p)
        if state(p, d) == want:
            print("  %s already %s -- nothing to do" % (name, want))
            continue
        backup = os.path.join(BACKUP_DIR, name + SUFFIX)
        if not undo and not os.path.exists(backup):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(p, backup)
            print("  backup -> %s" % os.path.basename(backup))
        before = len(d)
        for o, b, _desc in (originals(p, d) if undo else wanted(d)):
            d[o:o + len(b)] = b
        assert len(d) == before, "file length changed -- this patch must be size-neutral"
        with open(p, "wb") as f:
            f.write(d)
        assert state(p, read(p)) == want, "%s did not read back %s" % (name, want)
        print("  %s entry %d %s (%d B, length unchanged)"
              % (name, ICON_ID, "REVERTED" if undo else "PATCHED", before))


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
