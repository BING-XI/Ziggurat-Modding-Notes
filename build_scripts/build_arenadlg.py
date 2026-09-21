#!/usr/bin/env python3
r"""
AoW1 mod -- "arenadlg": re-lay the Arena dialog for the arena-battle rework.

Companion to build_arena.py (which is DPL-only). This one edits the TARENADLG **DFM resource** in
the canonical mod exes `Ziggurat\AoWz.exe` + `Ziggurat\AoWzCompat.exe` (names come from
`zigexe.py`). Binaries stay in lockstep; backups <exe>.pre-arenadlg.
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

FULL DESIGN: Modding Resources/Arena_Rework_Feasibility.md
TECHNIQUE:   Modding Resources/HeroUpgradeDlg_Tall.md  (the in-place exe-DFM recipe this reuses --
             locate_dfm/enc_int/apply_edits are imported from build_herodlg_tall.py, not copied)

================================================================================
WHAT CHANGES
================================================================================
Vanilla is a unit-training dialog: one row of EIGHT checkboxes, each a unit of your stack, over a
single centred one-line caption. The rework only ever has THREE meaningful boxes (weak / medium /
strong) and wants each on its own row with the offer spelled out beside it.

  Dlg            WinHeight  328 -> 420        (+92; awCenter/ahCenter, so it re-centres itself)
  UnitPnl        (26,195) 437x100 -> (26,190) 70x200      the checkbox COLUMN
    U1           WinLeft/Top   (0,0)   -> (10,  8)
    U2                         (55,0)  -> (10, 72)
    U3                         (110,0) -> (10,136)
    U4..U8       + Visible=False                          five boxes that are not categories
  SelectionInfoPnl (27,264) 437x20 -> (100,190) 363x200   the text block, beside the column
    SelectionInfoLbl  WinLeft 198 -> 10, AlignWidth awCenter -> awNone   (left-aligned, 3 lines)
  SelectionLbl   Text  'Select Unit(s) to Train' -> 'Fight in the Arena'
  SelectBtn      Text  'Train' -> 'Fight'
  DecoL/DecoR/AoWFrame1/SelectBtn/CancelBtn   WinTop 290 -> 382

The bottom band is `ahBottom` with BottomOffset 11, so it tracks the bottom edge on its own; its
WinTop is the design-time precomputed value and is updated too, so the layout is right whether the
runtime re-runs alignment at create or trusts the stored value (same reasoning as the hero dialog).

MapViewPnl / MapView / InfoSep / Title / TitleIcon / Close are untouched.

================================================================================
BYTE BUDGET -- a DFM cannot grow in place
================================================================================
The next resource starts immediately after this one, so the patched blob must be <= 0x37C6 bytes;
the tail is zero-padded and never read (the reader stops at the root terminator).

  SPEND  +45  five `Visible False` props on U4..U8   (9 B each: shortstring name + type byte)
         +1   UnitPnl.WinHeight        100 -> 200    Int8 is SIGNED, so >127 needs Int16
         +1   SelectionInfoPnl.WinHeight 20 -> 200   ditto
         +1   U3.WinTop                  0 -> 136    ditto
  SAVE    -2  SelectionInfoLbl.Alignment.AlignWidth 'awCenter' -> 'awNone'
          -5  SelectionLbl.Text 23 chars -> 18
          -1  SelectionInfoLbl.WinLeft 198 -> 10 re-encodes Int16 -> Int8
  FREE  +122  deleting DESIGNER-ONLY properties (see below)

⚠ `Visible` IS published on TAOWCheckBox -- verified by scanning every DFM in AoW.exe, where
TAOWButton/CheckBox/Image/Label/Panel/Window all carry it somewhere. An *unknown* property is what
raises EReadError; deleting a known one is always safe (the reader keeps the default).

The 122 free bytes come from properties the runtime never reads:
  * the root TArenaDlg's Left/Top/Height/Width (33 B) -- the trick from HeroUpgradeDlg_Tall.md;
    every exe-form root carries these.
  * TIvTranslator's Left/Top (14 B) -- a non-visual component; these are its designer icon position.
  * U4..U8's Left/Top (75 B) -- see below.

**Left/Top are DESIGNER-only on these controls; Win* is what the runtime uses.** Proof from the
vanilla data itself: U1..U8 have Left = 160,200,240,...,440 (pitch 40) but WinLeft = 0,55,110,...,386
(pitch 55), and the shipped dialog shows the boxes at pitch 55. So Left is stale designer state.

================================================================================
STATE MACHINE
================================================================================
Pristine slot recognised by SHA1. A patched slot is recognised by rebuilding the patch from the
pristine bytes and comparing -- so --apply is idempotent and --undo needs no backup. Re-tuning the
layout = edit LAYOUT below and re-run --apply from any state.

Dry-run by default; --apply to write both exes (they are killed first if they hold the file).
--undo restores the pristine slot in place.  The pristine payload comes from `pristine_slot()`,
which prefers a `.pre-arenadlg` snapshot and falls back to the vanilla exe -- `Ziggurat upload/
AoW.exe` or the stock one at the game root.  ⚠ Until 2026-09-09 it read `<exe>.pre-arenadlg`
only; with the backup stack deleted that left the state permanently 'applied?' and --undo dead.
"""

import argparse
import hashlib
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))

import dfm_edit                                    # noqa: E402
import zigexe                                      # noqa: E402  -- mod binary names
from build_herodlg_tall import (locate_dfm, enc_int, apply_edits,   # noqa: E402
                                write_slot, kill_game)

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
EXES = list(zigexe.EXES)                           # AoWz.exe + AoWzCompat.exe
BAK_SUFFIX = ".pre-arenadlg"
BACKUP_DIR = os.path.join(GAME, "backups")         # ⚠ never the game root -- rule 2026-09-03
RESNAME = "TARENADLG"

# SHA1 of the pristine TARENADLG resource payload (both exes carry the same bytes).
ORIG_SHA1 = None            # filled on first run; see check_pristine()

# ---------------------------------------------------------------- the layout
# ⚠ TAOWLabel is SINGLE-LINE (see build_arena.py's INFO_LINES comment), so the description is one
# sentence at a time and the dialog has to be wide enough for the longest of them -- ~88 chars at
# roughly 7 px/char in FontModule.AoW15WhiteGrey.
DLG_WIDTH = 700             # was 492
DLG_HEIGHT = 350            # was 328
GROW_W = DLG_WIDTH - 492
GROW_H = DLG_HEIGHT - 328

# The three category icons sit in ONE horizontal row, evenly spread, with the single description
# line centred underneath -- so the dialog only needs one icon's worth of vertical space.
ICON_W = 50                 # TAOWCheckBox WinWidth, unchanged from vanilla
PANEL_LEFT = 26
PANEL_WIDTH = DLG_WIDTH - 2 * PANEL_LEFT
ICON_ROW_TOP = 190          # UnitPnl top inside Dlg
ICON_ROW_HEIGHT = 64
ICON_TOP = 4                # checkbox top inside UnitPnl
# centre each icon in its third of the panel
ICON_XS = [(PANEL_WIDTH * (2 * i + 1)) // 6 - ICON_W // 2 for i in range(3)]
TEXT_TOP_PANEL = ICON_ROW_TOP + ICON_ROW_HEIGHT + 4   # SelectionInfoPnl top inside Dlg
TEXT_HEIGHT = 24
TEXT_TOP = 4                # the label inside that panel
BOTTOM_ROW = 290 + GROW_H   # derived, so retuning DLG_HEIGHT can never desync the bottom band

HEADER_TEXT = "Fight in the Arena"
BUTTON_TEXT = "Fight"

# (path suffix, property, new value) -- integers
INT_EDITS = [
    ("/Dlg",              "WinHeight", DLG_HEIGHT),
    ("/Dlg",              "WinWidth",  DLG_WIDTH),
    # the top half widens with the dialog
    ("/MapViewPnl",       "WinWidth",  452 + GROW_W),
    ("/MapView",          "WinWidth",  446 + GROW_W),
    ("/InfoSep",          "WinWidth",  453 + GROW_W),
    ("/AoWFrame1",        "WinWidth",  440 + GROW_W),
    # bottom band: right-hand decor follows the right edge, buttons stay centred
    ("/DecoR",            "WinLeft",   375 + GROW_W),
    ("/SelectBtn",        "WinLeft",   118 + GROW_W // 2),
    ("/CancelBtn",        "WinLeft",   246 + GROW_W // 2),
    ("/UnitPnl",          "WinLeft",   PANEL_LEFT),
    ("/UnitPnl",          "WinTop",    ICON_ROW_TOP),
    ("/UnitPnl",          "WinWidth",  PANEL_WIDTH),
    ("/UnitPnl",          "WinHeight", ICON_ROW_HEIGHT),
    ("/U1",               "WinLeft",   ICON_XS[0]),
    ("/U1",               "WinTop",    ICON_TOP),
    ("/U2",               "WinLeft",   ICON_XS[1]),
    ("/U2",               "WinTop",    ICON_TOP),
    ("/U3",               "WinLeft",   ICON_XS[2]),
    ("/U3",               "WinTop",    ICON_TOP),
    ("/SelectionInfoPnl", "WinLeft",   PANEL_LEFT),
    ("/SelectionInfoPnl", "WinTop",    TEXT_TOP_PANEL),
    ("/SelectionInfoPnl", "WinWidth",  PANEL_WIDTH),
    ("/SelectionInfoPnl", "WinHeight", TEXT_HEIGHT),
    ("/SelectionInfoLbl", "WinTop",    TEXT_TOP),
    ("/DecoL",            "WinTop",    BOTTOM_ROW),
    ("/DecoR",            "WinTop",    BOTTOM_ROW),
    ("/AoWFrame1",        "WinTop",    BOTTOM_ROW),
    ("/SelectBtn",        "WinTop",    BOTTOM_ROW),
    ("/CancelBtn",        "WinTop",    BOTTOM_ROW),
]
# (path suffix, property, new ident)
IDENT_EDITS = [
    # SelectionInfoLbl keeps its vanilla awCenter: with the icons in a row the single description
    # line reads best centred under them, so there is nothing to change here.
]
# (path suffix, property, new string)
STR_EDITS = [
    ("/SelectionLbl", "Text", HEADER_TEXT),
    ("/SelectBtn",    "Text", BUTTON_TEXT),
]
# properties to DELETE outright (designer-only; the runtime uses Win*)
DELETES = [("/ArenaDlg", n) for n in ("Left", "Top", "Height", "Width")] + \
          [("/Translator", n) for n in ("Left", "Top")] + \
          [("/U%d" % i, n) for i in (4, 5, 6, 7, 8) for n in ("Left", "Top")]
# checkboxes to hide: a `Visible False` property appended after their $class-adjacent props
HIDE = ["/U%d" % i for i in (4, 5, 6, 7, 8)]


def find(w, suffix, prop):
    hits = [p for p in w.props if p[0].endswith(suffix) and p[1] == prop]
    if len(hits) != 1:
        raise SystemExit("ABORT: %s.%s -> %d matches (expected 1)" % (suffix, prop, len(hits)))
    return hits[0]


def enc_str(name, s):
    return dfm_edit.shortstr(name) + bytes([dfm_edit.STR]) + dfm_edit.shortstr(s)


def enc_ident(name, s):
    return dfm_edit.shortstr(name) + bytes([dfm_edit.IDENT]) + dfm_edit.shortstr(s)


def transform(orig):
    """pristine slot -> patched slot, zero-padded back to the original length."""
    w = dfm_edit.walk(orig)
    if w.consumed != len(orig):
        raise SystemExit("ABORT: pristine DFM does not walk cleanly (%d/%d)" % (w.consumed, len(orig)))
    edits = []
    for suffix, prop, val in INT_EDITS:
        _, _, _, s, e, _ = find(w, suffix, prop)
        edits.append((s, e, enc_int(prop, val)))
    for suffix, prop, val in IDENT_EDITS:
        _, _, _, s, e, _ = find(w, suffix, prop)
        edits.append((s, e, enc_ident(prop, val)))
    for suffix, prop, val in STR_EDITS:
        _, _, _, s, e, _ = find(w, suffix, prop)
        edits.append((s, e, enc_str(prop, val)))
    for suffix, prop in DELETES:
        _, _, _, s, e, _ = find(w, suffix, prop)
        edits.append((s, e, b""))
    for suffix in HIDE:
        # insert `Visible False` at the start of the control's own property run, i.e. immediately
        # after its $class header -- property order inside an object is free.
        _, _, _, s, e, _ = find(w, suffix, "$class")
        edits.append((e, e, dfm_edit.shortstr("Visible") + bytes([dfm_edit.FALSE])))

    out = apply_edits(orig, edits)
    if len(out) > len(orig):
        raise SystemExit("ABORT: patched DFM is %d bytes, %d over budget"
                         % (len(out), len(out) - len(orig)))
    chk = dfm_edit.walk(out)
    if chk.consumed != len(out):
        raise SystemExit("ABORT: patched DFM does not walk cleanly (%d/%d)"
                         % (chk.consumed, len(out)))
    pad = len(orig) - len(out)
    return out + b"\0" * pad, pad


def slot_of(path):
    data = open(path, "rb").read()
    import build_herodlg_tall as H
    saved, H.RESNAME = H.RESNAME, RESNAME
    try:
        off, size = locate_dfm(data)
    finally:
        H.RESNAME = saved
    return data, off, size, data[off:off + size]


def pristine_slot(path, size):
    """-> (vanilla TARENADLG payload, donor label) or (None, None).

    ⚠ There is no `.pre-arenadlg` snapshot on this install -- the whole backup stack was deleted
    on 2026-09-03 -- and without one this script reported state 'applied?' and refused to act,
    while `--undo` printed "no backup, cannot undo".  Both were a missing *reference*, not a
    missing feature: the patch is in.

    Since 2026-09-09 the reference is always available.  The GAME ROOT is a stock GOG install
    (CHANGED(0) against the hashdb), so `<root>\\AoW.exe` carries the vanilla resource;
    `Ziggurat upload\\AoW.exe` (2025-03-21) carries the same payload and is kept as a second
    donor.  ⚠ Those two are VANILLA and are read-only here -- never a write target.

    A donor is trusted only when its slot is the same size AND `transform()`s cleanly, i.e. it
    still holds the properties in their pristine form.  Never trusted on filename alone: a
    `.pre-*` file is not proof of anything, and the old snapshots are named for the pre-rename
    `AoW.exe` / `AoWCompat.exe`.
    """
    base = os.path.basename(path)
    for label, cand in (
            ("backups/" + base + BAK_SUFFIX, os.path.join(BACKUP_DIR, base + BAK_SUFFIX)),
            (base + BAK_SUFFIX, path + BAK_SUFFIX),
            ("backups/" + zigexe.VANILLA_EXE + BAK_SUFFIX,
             os.path.join(BACKUP_DIR, zigexe.VANILLA_EXE + BAK_SUFFIX)),
            ("Ziggurat upload/" + zigexe.VANILLA_EXE,
             os.path.join(GAME, "Ziggurat upload", zigexe.VANILLA_EXE)),
            ("<root>/" + zigexe.VANILLA_EXE,
             os.path.join(GAME, "..", zigexe.VANILLA_EXE))):
        if not os.path.exists(cand):
            continue
        try:
            _, _, dsize, slot = slot_of(cand)
        except Exception:                                          # noqa: BLE001
            continue
        if dsize != size:
            continue
        try:
            transform(slot)                       # aborts unless the slot is pristine
        except SystemExit:
            continue
        return slot, label
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write both exes (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="restore the pristine DFM in place")
    ap.add_argument("--dump", action="store_true", help="list the resulting geometry and exit")
    args = ap.parse_args()

    print("=" * 78)
    print("arenadlg   TARENADLG layout")
    print("=" * 78)

    plans = []
    for exe in EXES:
        path = os.path.join(GAME, exe)
        data, off, size, cur = slot_of(path)
        pristine, donor = pristine_slot(path, size)
        # figure out which state we are in
        try:
            patched_from_cur, pad = transform(cur)
        except SystemExit:
            patched_from_cur = None
        if patched_from_cur is not None and cur != patched_from_cur:
            state, base = "stock", cur
        elif pristine is not None:
            want, pad = transform(pristine)
            state, base = ("applied" if cur == want else "unknown"), pristine
        elif patched_from_cur is None:
            state, base = "applied?", None
        else:
            state, base = "stock", cur
        print("  %-14s foff=0x%06X size=0x%04X   [%s]%s"
              % (exe, off, size, state, "  ref: " + donor if donor else ""))
        plans.append((path, off, size, cur, state, base, pristine))

    if args.dump:
        _, off, size, cur, _, _ = plans[0][0], *plans[0][1:]
        w = dfm_edit.walk(cur)
        for p in w.props:
            if p[1] in ("WinLeft", "WinTop", "WinWidth", "WinHeight", "Visible", "Text",
                        "Alignment.AlignWidth"):
                print("   %-32s %-20s %r" % (p[0], p[1], p[5]))
        return

    if args.undo:
        for path, off, size, cur, state, base, pristine in plans:
            if pristine is None:
                print("  %s: no pristine reference, cannot undo" % os.path.basename(path))
                continue
            if cur == pristine:
                print("  %s: already stock" % os.path.basename(path))
                continue
            if not args.apply:
                print("  %s: would restore the pristine DFM" % os.path.basename(path))
                continue
            write_slot(path, off, pristine)
            print("  %s: UNDONE" % os.path.basename(path))
        return

    for path, off, size, cur, state, base, pristine in plans:
        name = os.path.basename(path)
        if state == "applied":
            print("  %s: already applied" % name)
            continue
        if state != "stock":
            raise SystemExit("ABORT: %s is in state '%s' -- refusing to guess. Restore %s%s or "
                             "investigate." % (name, state, name, BAK_SUFFIX))
        new, pad = transform(cur)
        print("  %s: %d -> %d bytes (+%d zero pad)" % (name, size, size - pad, pad))
        if not args.apply:
            continue
        # ⚠ backups/ , never the game root (rule 2026-09-03). Reached only when state == "stock",
        # which is the positive proof-of-unpatched this snapshot needs.
        bak = os.path.join(BACKUP_DIR, os.path.basename(path) + BAK_SUFFIX)
        if not os.path.exists(bak):
            kill_game()
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, bak)
            print("     backup -> %s" % bak)
        write_slot(path, off, new)
        print("     APPLIED")

    if not args.apply:
        print("\nDRY RUN. Add --apply to write.")


if __name__ == "__main__":
    main()
