#!/usr/bin/env python3
r"""Give the Magebane ability (id 0xAA) a description in `Release/Ability.pfs`.

    python build_scripts/build_magebane_desc.py            # dry run + verify current state
    python build_scripts/build_magebane_desc.py --apply
    python build_scripts/build_magebane_desc.py --undo

================================================================================
WHY THIS IS NOT A build_pfs_typos.py ROW
================================================================================
`build_pfs_typos.py` rewrites a string field that already exists -- its `plan()` bails with
"record N has no tag T" otherwise, and its whole rebuild assumes the body directory keeps its size.
Magebane's record has **no tag 5 at all**:

    record 180 (= ability 0xAA + 10), as shipped by the editor:
        tag 6 = 8          hero level-up point cost
        tag 7 = 0x00000101 SFX
        tag 8 = 0          image list  (blank icon -- expected for a new id)
        tag 9 = 0x0037     selection mask, matching the registration cave's CATWORD

So this has to CREATE a field: the directory grows by one 2-byte small entry and the payload grows
by the u32-prefixed string. Doing that inside `plan()` would mean unpicking its `dsz`-is-constant
assumption on a function ~30 working rows depend on, so it lives here instead. The helpers it does
reuse -- `index_layout`, `body_dir`, `slice_fields` -- are imported from that script rather than
re-derived, so there is one implementation of the container format.

================================================================================
THE WRITE
================================================================================
* The new field is APPENDED at the end of the record's payload, so **every existing field keeps its
  offset** and only the new entry is added to the directory. Nothing inside the record moves.
* The record grows by `2 + 4 + len(text)`; every FILE-index offset after it shifts by that much.
* Small directory entries are u8 -- the new field's offset (the old payload size, 14) and every
  later index offset are range-checked, and the script refuses rather than truncating.
* The trailing CRC-32 is repaired and the residue re-asserted.
* Entries are written in ascending tag order (5,6,7,8,9). Readers key by tag, so order is cosmetic;
  it keeps a hand-dumped record legible.

Backup `Release/Ability.pfs.pre-magebanedesc`; `--undo` removes tag 5 again and is byte-exact.
"""

import argparse
import importlib.util
import os
import shutil
import struct
import sys
import zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
HERE = os.path.dirname(os.path.abspath(__file__))

ABIL_PFS = os.path.join(GAME, "Release", "Ability.pfs")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ABIL_PFS) + ".pre-magebanedesc")
PFS_RESIDUE = 0x2144DF1C

MAGEBANE_ID = 0xAA
REC = MAGEBANE_ID + 10          # 180
TAG = 5                         # description

TEXT = ("+2/2 ATK/DAM against units per enchantment they have, and +5/5 ATK/DAM "
        "against summoned units\r\n")


def _typos():
    spec = importlib.util.spec_from_file_location(
        "pfs_typos", os.path.join(HERE, "build_pfs_typos.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _pfs():
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def crc_gate(d, where):
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT (%s): Ability.pfs CRC residue is %#010x, expected %#010x -- the file is\n"
                 "       damaged. Refusing to touch it; repairing the CRC over the damage would\n"
                 "       stamp it valid. Restore Release/Ability.pfs or re-save it from AoWDevEd."
                 % (where, zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))


def record_span(d, T):
    """(start, body) for record REC. Bodies tile the file from the first to EOF."""
    recs = _pfs().parse_index(bytes(d))
    starts, at = {}, len(d)
    for rid, body in reversed(recs):
        at -= len(body)
        starts[rid] = at
    if REC not in starts:
        sys.exit("ABORT: Ability.pfs has no record %d for Magebane (%#04x). Assign the ability to "
                 "something in AoWDevEd and save, so the editor creates one." % (REC, MAGEBANE_ID))
    return starts[REC], dict(recs)[REC]


def rebuild(body, T, add):
    """Return the new body: `add` True inserts tag 5, False removes it."""
    dents, dsz = T.body_dir(body)
    fields = T.slice_fields(body, dents, dsz)
    have = TAG in fields
    if add and have:
        return None, "already has tag %d" % TAG
    if not add and not have:
        return None, "has no tag %d" % TAG
    if any(w != 1 for _t, _o, w in dents):
        sys.exit("ABORT: record %d mixes wide directory entries -- this writer only handles the "
                 "pure-small form." % REC)

    if add:
        blob = struct.pack("<I", len(TEXT)) + TEXT.encode("latin-1")
        keep = [(t, o) for t, o, _w in dents]
        new_off = len(body) - dsz                      # append: every existing offset unchanged
        if new_off > 0xFF:
            sys.exit("ABORT: record %d payload is %d B; a u8 directory offset caps at 255."
                     % (REC, new_off))
        entries = sorted(keep + [(TAG, new_off)])
        payload = bytes(body[dsz:]) + blob
    else:
        entries = sorted((t, o) for t, o, _w in dents if t != TAG)
        payload = bytes(body[dsz:])[:fields[TAG] and len(body) - dsz - len(fields[TAG])]
        if payload + fields[TAG] != bytes(body[dsz:]):
            sys.exit("ABORT: tag %d is not the LAST field in record %d, so removing it would move "
                     "the others. Undo is only safe for the field this script appended." % (TAG, REC))

    new_dir = bytearray([len(entries)])
    for t, o in entries:
        new_dir += bytes([t, o])
    return bytes(new_dir) + payload, None


def splice(d, T, start, old_body, new_body):
    """Replace the record and shift every later index offset; repair the CRC."""
    delta = len(new_body) - len(old_body)
    base, ent = T.index_layout(bytes(d))
    rec_off = start - base
    out = bytearray(d)
    out[start:start + len(old_body)] = new_body
    for _rid, o, pos, w in ent:
        if o <= rec_off:
            continue
        v = o + delta
        if w == 1:
            if v > 0xFF:
                sys.exit("ABORT: index small-entry offset %d overflows u8 -- refusing to truncate."
                         % v)
            out[pos] = v
        else:
            struct.pack_into("<I", out, pos, v)
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    if zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: CRC repair produced the wrong residue -- nothing written.")
    return out, delta


def verify(before, after, T, expect_text):
    """Every OTHER record byte-identical, every record still parses, ours reads as intended,
    and none of ITS other tags moved."""
    p = _pfs()
    o, n = p.parse_index(bytes(before)), p.parse_index(bytes(after))
    if [r for r, _ in o] != [r for r, _ in n]:
        sys.exit("ABORT: the record id list changed.")
    last = n[-1][0]           # ⚠ the final body swallows the 4-byte trailing CRC, which we repair
    ob, nb = dict(o), dict(n)
    for rid in ob:
        a, b = ob[rid], nb[rid]
        if rid == last:
            a, b = a[:-4], b[:-4]
        if rid != REC and a != b:
            sys.exit("ABORT: record %d changed as collateral damage (%d -> %d B)."
                     % (rid, len(a), len(b)))
    for rid, b in n:
        try:
            e, s = T.body_dir(b)
            T.slice_fields(b, e, s)
        except (ValueError, IndexError, struct.error) as exc:
            sys.exit("ABORT: record %d no longer parses (%s)." % (rid, exc))

    eo, so = T.body_dir(ob[REC]); f_old = T.slice_fields(ob[REC], eo, so)
    en, sn = T.body_dir(nb[REC]); f_new = T.slice_fields(nb[REC], en, sn)
    for t in f_old:
        if t != TAG and f_old[t] != f_new[t]:
            sys.exit("ABORT: record %d tag %d changed (%s -> %s)."
                     % (REC, t, f_old[t].hex(), f_new[t].hex()))
    got = T.read_str(f_new[TAG])[0] if TAG in f_new else None
    if got != expect_text:
        sys.exit("ABORT: record %d tag %d reads %r, expected %r." % (REC, TAG, got, expect_text))


def main():
    ap = argparse.ArgumentParser(description="Add Magebane's description to Ability.pfs")
    ap.add_argument("--apply", action="store_true", help="write it (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="remove the description field again")
    args = ap.parse_args()

    if not os.path.isfile(ABIL_PFS):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR)" % ABIL_PFS)
    T = _typos()
    d = bytearray(open(ABIL_PFS, "rb").read())
    crc_gate(d, "before")

    start, body = record_span(d, T)
    dents, dsz = T.body_dir(body)
    fields = T.slice_fields(body, dents, dsz)
    cur = T.read_str(fields[TAG])[0] if TAG in fields else None

    print("build_magebane_desc  record %d (ability %#04x)  tags %s"
          % (REC, MAGEBANE_ID, sorted(fields)))
    print("  current description: %r" % cur)
    print("  target  description: %r" % (None if args.undo else TEXT))

    want_present = not args.undo
    if (cur is not None) == want_present and (cur is None or cur == TEXT):
        print("Nothing to do -- already in the target state.")
        return

    new_body, why = rebuild(body, T, add=want_present)
    if new_body is None:
        print("Nothing to do -- record %s." % why)
        return
    out, delta = splice(d, T, start, body, new_body)
    verify(d, out, T, TEXT if want_present else None)
    print("  record %d B -> %d B (%+d), later index offsets shifted, CRC repaired"
          % (len(body), len(new_body), delta))

    if not args.apply and not args.undo:
        print("DRY RUN -- re-run with --apply to commit.")
        print("(Close AoW.exe / AoWDevEd.exe first -- they lock Release/.)")
        return

    if want_present and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(ABIL_PFS, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))
    try:
        open(ABIL_PFS, "wb").write(bytes(out))
    except PermissionError:
        sys.exit("ERROR: Release/Ability.pfs is locked. Close the AoW binaries and retry.")
    print("%s. %d records still parse." % ("UNDONE" if args.undo else "APPLIED",
                                           len(_pfs().parse_index(bytes(out)))))
    if want_present:
        print("TEST: hover Magebane on a unit card -- the description should read the new text.")


if __name__ == "__main__":
    main()
