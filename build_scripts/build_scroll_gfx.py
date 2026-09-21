#!/usr/bin/env python
"""
build_scroll_gfx.py -- give itScroll items an icon.

⚠⚠ DO NOT APPLY. CONFIRMED HARMFUL IN-GAME 2026-08-01. ⚠⚠
Retyping these four records breaks the image system: **blank hero portrait, no spell icons, and all
spell costs displayed as nonsense (1, 5, 0) though still castable** -- no error dialog. Isolated by a
clean single-variable A/B: reverting this file alone (cave untouched) made every symptom vanish.

So `ITEMGFX.PFS` tag 8 / `TItemGFX+0x20` is NOT a passive "which item type may use this graphic"
filter, even though `TItemGFXList.FindItemTypeGFX@0x55795C1C` compares exactly that byte. Something
in the image path also keys off it, and moving four records into the (previously empty) type-5 bucket
is enough to poison unrelated drawing. Root cause not pinned down -- do not retry as-is.

BETTER ROUTES TO A SCROLL ICON (untested):
  * The item stores its OWN graphic index (`item+0x40`, pfs tag 7); `FindItemTypeGFX` only supplies a
    DEFAULT when that is -1. So pick a graphic explicitly on the item in AoWDevEd instead.
  * Or APPEND new type-5 records pointing at `ITEMS\I_SCROLL.ILB` rather than retyping existing ones
    -- that leaves every current record's bucket untouched.
  * Note a scroll left at gfx index -1 is its own hazard: `ImageLib.Get` has no bounds check.

The original rationale follows.

PROBLEM
-------
`Images/ITEMS/I_Scroll.ILB` ships with the game and `Release/ITEMGFX.PFS` registers four scroll
icons as records 316-319 -- but their type tag (tag 8) says **6 (itUse)**, and there is not a single
type-**5** (itScroll) graphic in the whole file.  `TItemGFXList.FindItemTypeGFX@0x55795C1C` scans for
the first entry whose `+0x20` byte equals the requested type and returns **-1** when none matches, so
`TItem.SetItemType@0x5579457C` (and AoWDevEd's item form) give every newly created scroll a GFX index
of -1 -- i.e. no picture.  Part of the same cut-content story as `build_scroll_spellbook.py`; see
`Modding Resources/Investigation_Items.md` Feature 1.

FIX
---
Flip tag 8 from 6 -> 5 on ITEMGFX.PFS records 316, 317, 318 and 319 (four single bytes).  Those four
records are the only ones pointing at `ITEMS\\I_SCROLL.ILB`, so nothing else is affected: the ten
itUse items in the installed data (Wand of Flames, Frost Wand, ...) all use `I_USE.ILB` records
300-315 and keep their type.

Record offsets are DERIVED by parsing the file, never hard-coded, so this stays correct if the item
GFX table is re-authored.  `Release/Release.hss` contains no reference to any `.pfs`, so there is no
resource-set CRC to repair afterwards (unlike `.hss` edits -- see `re_tools/hss_crc.py`).

Idempotent, verify-before-write, backs up to `<game dir>/backups/ITEMGFX.PFS.pre-scrollgfx`.
Dry-run by default; `--apply` to write, `--undo` to put the 6s back -- but see the DO NOT APPLY
banner at the top: neither of those should ever be run.
"""
import os, sys, shutil, struct

TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import pfs  # noqa: E402  (parser + format notes live there)

PFS_REL = os.path.join("Release", "ITEMGFX.PFS")
SUFFIX = ".pre-scrollgfx"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
TYPE_TAG = 8
ITUSE, ITSCROLL = 6, 5
SCROLL_ILB = "I_SCROLL.ILB"


def index_with_offsets(d):
    """pfs.parse_index, but yielding absolute (record_id, start, end) instead of copied bytes."""
    best = None
    for s in range(0, 0x40):
        ids, offs, p = [], [], s
        while p + 8 <= len(d):
            i, o = struct.unpack_from("<II", d, p)
            if ids and (i <= ids[-1] or o <= offs[-1]):
                break
            if i > 0x10000 or o > len(d):
                break
            ids.append(i); offs.append(o); p += 8
        if len(ids) > 5 and (best is None or len(ids) > len(best[1])):
            best = (s, ids, offs)
    if best is None:
        raise ValueError("no wide index found")
    S, wids, woffs = best
    N = len(wids)
    small = []
    for p in range(0, S):
        if not (d[p] & 0x80) or p + 5 > len(d):
            continue
        if struct.unpack_from("<I", d, p + 1)[0] != N:
            continue
        ns = d[p] & 0x7f
        if p + 5 + 2 * ns == S:
            small = [(d[p + 5 + 2 * k], d[p + 6 + 2 * k]) for k in range(ns)]
            break
    ids = [i for i, _ in small] + wids
    offs = [o for _, o in small] + woffs
    base = S + 8 * N
    out = []
    for k in range(len(ids)):
        a = base + offs[k]
        b = base + offs[k + 1] if k + 1 < len(offs) else len(d)
        out.append((ids[k], a, b))
    return out


def tag_abs_offset(body, tag):
    """Absolute-within-body offset of `tag`'s payload (mirrors pfs.parse_dir's arithmetic)."""
    p = 4                                   # 4-byte class/version prefix
    n = body[p]; p += 1
    small = n & 0x7f
    wide = 0
    if n & 0x80:
        wide = struct.unpack_from("<I", body, p)[0]; p += 4
    ent = []
    for _ in range(small):
        ent.append((body[p], body[p + 1])); p += 2
    for _ in range(wide):
        t, o = struct.unpack_from("<II", body, p); ent.append((t, o)); p += 8
    ds = p
    for t, o in ent:
        if t == tag:
            return ds + o
    return None


def collect(d):
    """[(file_offset, old, new, desc)] for every I_SCROLL.ILB record's type byte."""
    out = []
    for rid, a, b in index_with_offsets(d):
        body = d[a:b]
        try:
            fields = pfs.parse_dir(body)
        except (ValueError, IndexError):
            continue
        ilb = pfs.pstr(fields.get(6, b"")).upper()
        if SCROLL_ILB not in ilb:
            continue
        rel = tag_abs_offset(body, TYPE_TAG)
        if rel is None:
            print(f"  record {rid}: no tag {TYPE_TAG} -- skipped"); continue
        out.append((a + rel, bytes([ITUSE]), bytes([ITSCROLL]),
                    f"record {rid} ({ilb}) type"))
    return out


def main():
    undo = '--undo' in sys.argv
    path = os.path.join(GAME, PFS_REL)
    if not os.path.exists(path):
        print(f"ABORT -- {PFS_REL} not found"); return 1
    d = bytearray(open(path, 'rb').read())
    patches = collect(d)
    if not patches:
        print(f"ABORT -- no records reference {SCROLL_ILB}; nothing to retype."); return 1
    print(f"{PFS_REL}: {len(patches)} scroll GFX record(s)")
    already = todo = 0
    ok = True
    for off, old, new, desc in patches:
        cur = bytes(d[off:off + 1])
        target, other = (old, new) if undo else (new, old)
        mark = ''
        if cur == target:
            already += 1; mark = 'already'
        elif cur == other:
            todo += 1; mark = f"{other[0]} -> {target[0]}"
        else:
            mark = f"MISMATCH (have {cur[0]}, expected {ITUSE} or {ITSCROLL})"; ok = False
        print(f"  {desc} @ {off:#08x}: {mark}")
    if not ok:
        print("ABORT -- refusing to write over unexpected bytes."); return 1
    if '--apply' not in sys.argv:
        print("\nDRY RUN -- nothing written. Re-run with --apply "
              "(close AoW.exe / AoWDevEd.exe first; they lock the data files).")
        return 0
    if todo == 0:
        print("Nothing to do."); return 0
    backup = os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)
    if not undo and not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup); print(f"  backup -> {backup}")
    for off, old, new, desc in patches:
        d[off:off + 1] = old if undo else new
    open(path, 'wb').write(bytes(d))
    print("  undone: scroll GFX records are typed itUse again (itScroll has no icon)." if undo
          else "  applied: scroll icons are now selectable for itScroll items.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
