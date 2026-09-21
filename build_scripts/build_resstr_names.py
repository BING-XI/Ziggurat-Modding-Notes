#!/usr/bin/env python3
r"""English display-name overrides in the localisation dictionary `Dict/ResStr.mld`.

    python build_scripts/build_resstr_names.py            # dry run + verify current state
    python build_scripts/build_resstr_names.py --apply
    python build_scripts/build_resstr_names.py --undo
    python build_scripts/build_resstr_names.py --dis      # also print the before/after strings

================================================================================
WHY THIS FILE AND NOT A .pfs
================================================================================
**`Spells.pfs` and `Ability.pfs` have no name field.** A spell's *description* is `Spells.pfs`
tag `0x0A` (edit those with `build_pfs_typos.py`), but its *name* is a Delphi **resourcestring**
compiled into `AoWEPACK.dpl`'s `.rsrc` as UTF-16 — e.g. "Summon Fire Sprite" at file offset
`0x298D9A`, inside a packed RT_STRING block (`<u16 len><wchar…>` back to back, **no slack**).
Editing it there would mean growing a resource block and shifting everything after it.

There is no need, because the engine already routes every resourcestring through a dictionary:

    AoWE.TranslateRStr @0x557249FC
      -> AoWE.TAoWEngine.TranslateRStr @0x55797B30
           if [[engine+0x78]+0x44] < 1 : return the source string unchanged
           else                        : IvDictio.TIvDictionary.Translate(dict, source, dest)

`Dict/ResStr.mld` is that dictionary, keyed on the **native** English string. An empty target slot
falls back to the source, which is why 1148 of the 1164 records are blank. **Ziggurat already uses
this as its rename mechanism** — the 16 non-empty `[US]` slots include "Fireball" → "Triple
Fireball", "Summon Mermaid" → "Craft Aether Barge", "Invoke Death" → "Reap Soul" and
"Version: %s" → "Version: Ziggurat %s". This script just adds rows to that set.

================================================================================
THE FORMAT (re-derived every run; nothing here is hard-coded)
================================================================================
`Dict/ResStr.mld` is a Multilizer v3 dictionary. Header (little-endian, offsets in bytes):

    0  tag "MLD" | 3 version | 4 byte_order | 5 char_set | 6 context | 7..11 reserved
    12 u2 language_count      14 u4 language_offset
    18 u2 translation_count   20 u4 translation_offset
    24 u2 locale_count        26 u4 locale_offset
    30 u2 info_size           32 u4 info_offset
    36..41 reserved

Translations start at `translation_offset` and are **packed sequentially with no index**: each
record is 8 `<u16 len><bytes>` strings — NATIVE, FORM, COMPONENT, then one per language in file
order, here `[US] [DE] [FR] [IT] [ES]` (language_count 6 = Native + 5). Verified by walking: 1164
records land exactly on `info_offset`, and `info_offset + info_size == filesize`.

⇒ A length change needs **one** fix-up: `info_offset` moves by the delta. Nothing else references
a position past the edit, and there is no checksum (contrast `.pfs`, which has one — see
`PFS_Format_CRC.md`). Both invariants are asserted after every write.

⚠ **`Dict/ResStr.txt` is edited in lockstep, and that is not cosmetic.** The `.txt` is the
human-editable source that `mld_conv.exe` (a GUI tool, PE subsystem 2) converts back into the
`.mld`. If the two drift, the next TXT→MLD round trip silently reverts whatever this script did.
The `.txt` `_HEADER_` block is deliberately left alone — `mld_conv` recomputes those values.

Revert is `--undo`: surgical, per-row, reverse order, both files, touching no backup. A
`.pre-resstrnames` snapshot of each file is taken on the first `--apply` only while every row is
still in its `old` state.
"""

import argparse
import os
import shutil
import struct

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

MLD = os.path.join(GAME, "Dict", "ResStr.mld")
TXT = os.path.join(GAME, "Dict", "ResStr.txt")
SUFFIX = ".pre-resstrnames"
# CLAUDE.md 2026-09-03: a snapshot goes in <game dir>\backups\, never beside the target.
# Migrated 2026-09-07; the two existing .pre-resstrnames files were MOVED here in the same
# change, which is what keeps the "a backup already exists" gate below meaningful -- repointing
# the path without moving them would have minted a fresh "snapshot" from the patched file.
BACKUP_DIR = os.path.join(GAME, "backups")


def backup_path(f):
    return os.path.join(BACKUP_DIR, os.path.basename(f) + SUFFIX)

LANG_TAG = "[US]"        # the slot we write; index 0 of the per-language strings
LANG_INDEX = 3           # NATIVE, FORM, COMPONENT, then [US]
FIELDS_PER_RECORD = 8

# ------------------------------------------------------------------------------------------
# The table: (native key, expected current [US], new [US], note)
# `native` must match the record's NATIVE string EXACTLY -- that is the dictionary's lookup key
# and the string the DLL resourcestring supplies. `old` is what the [US] slot must already hold,
# so "is this applied?" is always answerable; '' means the slot is empty (falls back to native).
# `old` may also be a TUPLE of accepted pre-states for a re-tuned row: element 0 is the vanilla
# slot (what --undo restores), the rest are texts the slot has held on the way here. Same rule as
# `olds_of()` in build_pfs_typos.py -- verify against the installed value OR the new one.
# ------------------------------------------------------------------------------------------
RENAMES = [
    ("Summon Fire Sprite", "", "Summon Fire Sprites",
     "the spell summons 3-7 sprites (RandInt(5)+3 for unit 0xE4, cave @0x5580C500), so the "
     "singular name misdescribed it; Spells.pfs record 31 already reads 'Summons 3-7 Fire Sprites.'"),
    ("Freeze Water", "", "Grip of Winter",
     "build_gripofwinter.py gives the spell a terrain-cooling ladder (Desert->Steppe->Grass->Snow) "
     "and makes it castable on land, so 'Freeze Water' no longer describes what it does. "
     "Spells.pfs record 20 tag 10 is rewritten to match by build_pfs_typos.py."),
    ("Spell Ward", "", "Astral Ward",
     "user rename 2026-09-07, after the rescope below was confirmed in-game. The refusal text and "
     "Spells.pfs record 75 (build_pfs_typos.py) name the spell too and were re-tuned in step."),
    ("Power Leak", "", "Power Leech",
     "build_powerleech.py drops the vanilla halving and makes the caster steal 25% of the power "
     "income of every magic node owned by another player. ONE row covers three surfaces: the "
     "spell name in the book, the enchantment name in the Magic window, and the "
     "'%s is already active' refusal -- TPowerLeakEnchantment.Create @0x557F0FD8 loads "
     "[ench+0x1C] from AoWE.PowerLeakRStr, the same resourcestring as the spell name. "
     "Spells.pfs record 58 (build_pfs_typos.py) carries the description."),
    ("Spell Ward locks all global enchantments",
     ("", "Spell Ward blocks Town Gate and Warp Party"),
     "Astral Ward blocks Town Gate and Warp Party",
     "build_spellward_rescope.py narrows the ward to spell ids 0x22 (Warp Party) and 0x26 "
     "(Town Gate); it no longer touches global enchantments, summons, city spells or "
     "Disjunction, so the vanilla refusal text names the wrong rule. This is the string the "
     "master gate loads at 0x55779302 (CannotCastGlobalEnchantmentWhenSpellWardIsActiveRStr, "
     "0x55707D4C) -- the only refusal the player can still see from the ward. The sibling row "
     "'Cannot dispel when Spell Ward is active' (ResStr.txt:2175) is deliberately left alone: "
     "site 3 of that patch makes it unreachable."),
]


# ---------------------------------------------------------------- mld structure

def hdr(d, off, fmt):
    return struct.unpack_from(fmt, d, off)[0]


def walk(d):
    """-> (records, end) where records = [(start, [(off, len)] * 8)] in file order."""
    n = hdr(d, 18, "<H")
    p = hdr(d, 20, "<I")
    out = []
    for _ in range(n):
        start = p
        fields = []
        for _k in range(FIELDS_PER_RECORD):
            ln = struct.unpack_from("<H", d, p)[0]
            fields.append((p + 2, ln))
            p += 2 + ln
        out.append((start, fields))
    return out, p


def check_invariants(d, where):
    recs, end = walk(d)
    info_off = hdr(d, 32, "<I")
    info_size = hdr(d, 30, "<H")
    if end != info_off:
        raise SystemExit("ABORT (%s): translations end at 0x%X but info_offset is 0x%X"
                         % (where, end, info_off))
    if info_off + info_size != len(d):
        raise SystemExit("ABORT (%s): info_offset+info_size = 0x%X but filesize is 0x%X"
                         % (where, info_off + info_size, len(d)))
    return recs


def find(recs, d, native):
    key = native.encode("latin1")
    hits = [(s, f) for s, f in recs if d[f[0][0]:f[0][0] + f[0][1]] == key]
    if len(hits) != 1:
        raise SystemExit("ABORT: NATIVE %r matches %d records, need exactly 1" % (native, len(hits)))
    return hits[0]


def get_slot(d, fields):
    o, ln = fields[LANG_INDEX]
    return d[o:o + ln].decode("latin1")


def set_slot(d, fields, new):
    """Return a NEW bytearray with the [US] slot replaced and info_offset fixed."""
    o, ln = fields[LANG_INDEX]
    nb = new.encode("latin1")
    out = bytearray(d)
    out[o - 2:o + ln] = struct.pack("<H", len(nb)) + nb
    delta = len(nb) - ln
    struct.pack_into("<I", out, 32, hdr(out, 32, "<I") + delta)
    return out


# ---------------------------------------------------------------- txt mirror

def txt_slot(lines, native):
    """-> index of the '[US] = [...]' line belonging to `native`."""
    want = "NATIVE    = [%s]" % native
    starts = [i for i, l in enumerate(lines) if l.rstrip("\r") == want]
    if len(starts) != 1:
        raise SystemExit("ABORT: %s matches %d lines in ResStr.txt, need exactly 1"
                         % (want, len(starts)))
    i = starts[0]
    for j in range(i + 1, min(i + FIELDS_PER_RECORD + 2, len(lines))):
        if lines[j].startswith("NATIVE"):
            break
        if lines[j].startswith(LANG_TAG):
            return j
    raise SystemExit("ABORT: no %s line found under %s in ResStr.txt" % (LANG_TAG, want))


def _txt_span(s):
    """Bracket span of the VALUE. The tag itself is bracketed too ('[US]      = [x]'),
    so anchor on the '= [' separator rather than the first '['."""
    a = s.index("= [") + 2
    return a, s.rindex("]")


def txt_get(lines, j):
    s = lines[j].rstrip("\r")
    a, b = _txt_span(s)
    return s[a + 1:b]


def txt_set(lines, j, new):
    """⚠ The file is CRLF. Lines are held verbatim (read with newline='') so the terminator
    survives the round trip -- strip the CR to edit, then put it back, or the write silently
    converts all 10612 line endings to LF."""
    raw = lines[j]
    cr = "\r" if raw.endswith("\r") else ""
    s = raw[:-1] if cr else raw
    a, b = _txt_span(s)
    lines[j] = s[:a + 1] + new + s[b:] + cr


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="English display-name overrides in Dict/ResStr.mld")
    ap.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="surgically restore each row's previous [US] text in both files")
    ap.add_argument("--dis", action="store_true", help="print the before/after strings")
    args = ap.parse_args()

    for f in (MLD, TXT):
        if not os.path.isfile(f):
            raise SystemExit("ERROR: not found: %s\n(set AOW_GAME_DIR)" % f)

    d = bytearray(open(MLD, "rb").read())
    # newline="" keeps the CRLF terminators verbatim; universal-newline mode would eat them
    # and the write-back would rewrite the whole file as LF.
    lines = open(TXT, encoding="latin1", newline="").read().split("\n")
    check_invariants(d, "before")

    rows = list(reversed(RENAMES)) if args.undo else RENAMES
    todo, state = [], []
    for native, old, new, note in rows:
        olds = old if isinstance(old, tuple) else (old,)
        # undo always lands on the vanilla slot (olds[0]), never on an intermediate state
        srcs, dst = ((new,), olds[0]) if args.undo else (olds, new)
        recs = walk(d)[0]
        _s, fields = find(recs, d, native)
        cur = get_slot(d, fields)
        j = txt_slot(lines, native)
        tcur = txt_get(lines, j)
        if tcur != cur:
            raise SystemExit("ABORT: %r out of sync -- .mld has %r but .txt has %r.\n"
                             "Reconcile them (mld_conv.exe) before running this script."
                             % (native, cur, tcur))
        state.append((native, cur, dst, note))
        if cur == dst:
            continue
        if cur not in srcs:
            raise SystemExit("ABORT: %r [US] is %r, expected one of %r or %r"
                             % (native, cur, srcs, dst))
        todo.append((native, dst))
        d = set_slot(d, fields, dst)
        txt_set(lines, j, dst)

    print("build_resstr_names  (%s)" % ("undo" if args.undo else "apply"))
    for native, cur, dst, note in state:
        mark = "already there" if cur == dst else "%r -> %r" % (cur, dst)
        print("  %-24s %s" % (native, mark))
        if args.dis:
            print("      native shown when [US] is empty; note: %s" % note)
    if not todo:
        print("Nothing to do -- every row is already in the target state.")
        return

    check_invariants(d, "after")

    if not args.apply and not args.undo:
        print("DRY RUN -- re-run with --apply to commit.")
        return

    if not args.undo:
        for f in (MLD, TXT):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            bp = backup_path(f)
            if not os.path.exists(bp):
                shutil.copy2(f, bp)
                print("backup -> backups/%s" % os.path.basename(bp))
    try:
        open(MLD, "wb").write(bytes(d))
        open(TXT, "w", encoding="latin1", newline="").write("\n".join(lines))
    except PermissionError:
        raise SystemExit("ERROR: Dict/ResStr.* is locked. Close the AoW binaries and retry.")

    print("%s %d row(s). ResStr.mld and ResStr.txt written in lockstep."
          % ("UNDID" if args.undo else "APPLIED", len(todo)))
    if not args.undo:
        print("TEST: open the spell book -- the Fire tier-2 spell should read "
              "'Summon Fire Sprites'.")


if __name__ == "__main__":
    main()
