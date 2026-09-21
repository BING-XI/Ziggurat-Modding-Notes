#!/usr/bin/env python3
r"""
build_embrittle_pfs.py — insert Spells.pfs record 119, the data half of Embrittlement
(spell 109): spellbook description, icon, mana, research cost, sphere and tier.

    python build_scripts/build_embrittle_pfs.py            dry run + verify
    python build_scripts/build_embrittle_pfs.py --apply     write it
    python build_scripts/build_embrittle_pfs.py --undo      remove record 119 again
    python build_scripts/build_embrittle_pfs.py --dis       print the record's fields

TARGET: Release/Spells.pfs ONLY.

Companion to `build_embrittle.py` (the mechanics) and `build_embrittle_icon.py` (the artwork).
⚠ Run the icon script FIRST or the index below points at the vanilla Dragon art.

────────────────────────────────────────────────────────────────────────────────────────────
WHY A RECORD IS NEEDED AT ALL
────────────────────────────────────────────────────────────────────────────────────────────
`TSpellControl.ReadWrite @0x55779A6C` streams every registered spell under
**property tag = spell id + 10**, so spell 109's record id is **119**. Registration happens in
a cave at package init, i.e. BEFORE the .pfs pass, so the spell exists when the loader runs --
it simply has no record, and therefore:

  * an EMPTY TImageSequenceList at `+0x2C`. `ImageLib.Get` has no bounds check
    (see Copper_Medal_Design.md), so asking that list for the book icon is a real risk, not a
    cosmetic gap. This record is what removes it.
  * no spellbook description at all.
  * whatever costs the cave hard-codes -- and once a record exists **the data file wins**
    for tags 0x0A-0x11, which is the point: from now on Embrittlement is tuned like any
    vanilla spell, and `build_embrittle.py`'s constants are decorative.

────────────────────────────────────────────────────────────────────────────────────────────
CLONE SLOW'S RECORD -- do not author one
────────────────────────────────────────────────────────────────────────────────────────────
Record 120 (Slow, spell 110) is the ideal donor: same class (`TSlow`), same sphere (Earth),
same tactical class (`SpellTypes` 0x07), same single-enemy-unit targeting. Its tag 0x0C is a
1008-byte nested TImageSequenceList (cast animation from `EFFECTS\TWINKGR.ILB` plus the book
icon from `SPELLICN.ILB`) and its tag 0x0B a TSFXLibrary node. Hand-authoring either is a
project; cloning both is free and cannot be structurally wrong.

Patched on the clone:
    tag 0x0A  description  (u32-length-prefixed -- NOT the u8 Pascal form names use)
    tag 0x0C  the single `SPELLICN.ILB` icon index, 52 -> %(ICON)d
    tag 0x0D  mana cost         tag 0x0F  research cost
    tag 0x10  sphere (byte)     tag 0x11  research tier (byte)
Everything else -- sounds, cast animation, the whole ISL skeleton -- is Slow's, unchanged.

⚠ The spell id is NOT in the body. It is the index key (record id = spell id + 10), which is
why re-keying the clone to 119 is all that makes it spell 109's record.

────────────────────────────────────────────────────────────────────────────────────────────
THE CONTAINER -- what an INSERT costs, and why it is not a rebuild
────────────────────────────────────────────────────────────────────────────────────────────
Index shape (PFS_Format_CRC.md):  <u8 n> [<u32 wide>] small(u8 key,u8 off)* wide(u32,u32)*
then the payload, and **every offset is relative to the END of the directory.**

That relative-offset property is what makes this tractable. Growing the index by one wide
entry moves the payload base by 8 automatically, so:

    records BEFORE the insertion   offsets UNCHANGED
    records AFTER  the insertion   offsets += len(new body)
    the new entry                  offset = record 120's old offset
    wide count                     += 1
    trailing CRC-32                recomputed to the standard residue

Nothing else moves. This is a splice, not a directory rebuild -- which matters, because the
directory's widths and ordering are NOT rule-derivable and must never be regenerated from
scratch (the `.ail` lesson in build_item_hpmv_data.py).

⚠ **Records are sorted by id AND by offset, and both orders must agree.** `index_layout()`
literally probes for that invariant to find the index, so breaking it would make the file
unreadable to our own tooling as well as, presumably, the game. Record 119 is therefore
spliced BETWEEN 118 and 120 rather than appended at the end.

⚠ **CRC-32.** A `.pfs` carries a trailing CRC whose residue over `d[4:]` must be
`0x2144DF1C`. Get it wrong and the game/editor fail silently -- no message, no clue. Verified
before the edit (to prove the file was intact to begin with) and after.

⚠ **AoWDevEd rewrites Spells.pfs whole whenever the author saves the set.** Nothing here is
hard-coded to a file offset: the index, the donor record and the icon field are all
re-derived on every run. If the editor has since rewritten the file, this script still works
-- but a save AFTER applying will bake record 119 in permanently, and `--undo` will then be
removing the editor's record rather than ours. That is fine; it is still keyed on id 119.

Snapshots go to `<game dir>\backups\Spells.pfs.pre-embrittle` and
`<game dir>\backups\Ability.pfs.pre-embrittle`, never beside the target. They are a courtesy, not
the revert path -- `--undo` is, and it removes record 119 and repairs the CRC.
⚠ The snapshot is currently minted on the `--undo` path too, where the file is the PATCHED state by
definition. Do not treat a `.pre-embrittle` on disk as proof the file was ever unpatched.
"""
import os, sys, struct, shutil, zlib, importlib.util

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SPELLS = os.path.join(GAME, "Release", "Spells.pfs")
ABILS  = os.path.join(GAME, "Release", "Ability.pfs")
PFS_RESIDUE = 0x2144DF1C
SUFFIX = ".pre-embrittle"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)

# ================================================================== the knobs
ICON = 128                   # SpellIcn.ILB entry rewritten by build_embrittle_icon.py
MANA = 14                    # tag 0x0D  -- matches Tremors, the other Earth tier-3 combat spell
RESEARCH = 80                # tag 0x0F  -- likewise
SPHERE = 3                   # tag 0x10  -- msEarth (0 Cosmos 1 Life 2 Death 3 Earth 4 Air
                             #                       5 Fire 6 Water)
TIER = 3                     # tag 0x11  -- research tier

SPELL_DESC = ("Makes a target's body brittle, causing it to suffer double damage "
              "from physical attacks for the duration of combat.")

# The status the spell applies, shown on the afflicted unit. Deliberately the exact mirror of
# vanilla Physical Protection's own wording -- "Reduces the damage inflicted upon the unit by
# physically-based attacks by 50%." -- because the two abilities are exact mirrors and a player
# comparing them should see that at a glance.
ABIL_DESC = ("Doubles the damage inflicted upon the unit by physically-based attacks, "
             "for the duration of combat.")
# ===========================================================================

TAG_DESC, TAG_IMG, TAG_MANA, TAG_RESEARCH, TAG_SPHERE, TAG_TIER = 0x0A, 0x0C, 0x0D, 0x0F, 0x10, 0x11
ABIL_TAG_DESC = 5            # Ability.pfs: tag 5 = description (u32-length-prefixed)
ICON_PATH = b"SPELLICN.ILB"


def _typos():
    """Reuse build_pfs_typos.py's container readers rather than re-deriving them."""
    p = os.path.join(GAME, "Modding Resources", "build_scripts", "build_pfs_typos.py")
    spec = importlib.util.spec_from_file_location("_pfs_typos", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T = _typos()


def index_header(d, S, N):
    """(pos, small_count) of the index header -- the same probe index_layout() uses."""
    for p in range(0, S):
        if d[p] & 0x80 and struct.unpack_from("<I", d, p + 1)[0] == N:
            ns = d[p] & 0x7F
            if p + 5 + 2 * ns == S:
                return p, ns
    raise ValueError("index header not found")


def read(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def records(d):
    """-> (payload_base, entries, wide_start, {id: (offset, end_offset)})."""
    base, ent = T.index_layout(d)
    N = sum(1 for e in ent if e[3] == 4)
    wide_start = base - 8 * N
    order = sorted(ent, key=lambda e: e[1])
    span = {}
    for j, e in enumerate(order):
        end = order[j + 1][1] if j + 1 < len(order) else len(d) - 4 - base
        span[e[0]] = (e[1], end)
    return base, ent, wide_start, span


def body_of(d, base, span, rid):
    a, b = span[rid]
    return bytes(d[base + a: base + b])


def reserialise(fields):
    """{tag: bytes} -> a record body, offsets recomputed, entry widths chosen per entry.

    Payload goes in tag order (the donors' own convention). Offsets are relative to the END of
    the directory, so they do not depend on the directory's own size -- which is what lets the
    width choice be made after the offsets are known.
    """
    tags = sorted(fields)
    offs, run = {}, 0
    for t in tags:
        offs[t] = run
        run += len(fields[t])
    small = [t for t in tags if offs[t] <= 0xFF]
    wide = [t for t in tags if offs[t] > 0xFF]
    hdr = bytearray([(len(small) & 0x7F) | (0x80 if wide else 0)])
    if wide:
        hdr += struct.pack("<I", len(wide))
    for t in small:
        hdr += bytes([t, offs[t]])
    for t in wide:
        hdr += struct.pack("<II", t, offs[t])
    body = bytes(hdr) + b"".join(fields[t] for t in tags)
    rent, rdsz = T.body_dir(body)
    assert T.slice_fields(body, rent, rdsz) == fields, \
        "re-serialised body does not parse back to the same fields"
    return body


def pstr32(text):
    """The u32-length-prefixed string form both description fields use.

    NOT the u8 Pascal form that NAMES use -- pfs.pstr() only knows the second and misreads this
    one. Every vanilla description also ends CRLF; matching that keeps the memo control's line
    handling identical to a stock entry.
    """
    b = (text + "\r\n").encode("latin1")
    return struct.pack("<I", len(b)) + b


def build_spell_body(donor):
    """Slow's SPELL record (120) with our fields substituted."""
    ent, dsz = T.body_dir(donor)
    f = dict(T.slice_fields(donor, ent, dsz))
    f[TAG_DESC] = pstr32(SPELL_DESC)
    f[TAG_MANA] = struct.pack("<I", MANA)
    f[TAG_RESEARCH] = struct.pack("<I", RESEARCH)
    f[TAG_SPHERE] = bytes([SPHERE])
    f[TAG_TIER] = bytes([TIER])
    img = bytearray(f[TAG_IMG])
    needle = struct.pack("<I", len(ICON_PATH)) + ICON_PATH
    hits = [i for i in range(len(img) - len(needle)) if img[i:i + len(needle)] == needle]
    assert len(hits) == 1, "expected exactly one %s in tag 0x0C, found %d" % (ICON_PATH, len(hits))
    struct.pack_into("<I", img, hits[0] + len(needle) + 3, ICON)   # path, 3 filler, u32 index
    f[TAG_IMG] = bytes(img)
    return reserialise(f)


def build_abil_body(donor):
    """Slow's ABILITY record (142) with only the description replaced.

    Slow is the donor specifically because its **tag 9 is `00 00`** -- the selection-type mask,
    which Ability.pfs OVERWRITES the registration cave's value with (see the ability-selection
    note in CLAUDE.md's memory index). Cloning Physical Protection instead would have shipped
    tag 9 = 0x03FF and made Embrittled selectable in the editor, on items and at hero level-up.
    Slow's 0 keeps it status-only, matching what TSlowEnchantmentAbility.Create sets.

    Tags 7 and 8 are cloned unexamined: Slow is the same kind of object -- a combat-only
    enchantment status -- so inheriting its presentation is right by construction.
    """
    ent, dsz = T.body_dir(donor)
    f = dict(T.slice_fields(donor, ent, dsz))
    assert f.get(9) == b"\x00\x00", \
        "donor's tag 9 (selection mask) is %r, expected 00 00 -- wrong donor" % f.get(9)
    f[ABIL_TAG_DESC] = pstr32(ABIL_DESC)
    return reserialise(f)


# (label, path, record id, donor record id, body builder)
TARGETS = [
    ("Spells.pfs  record 119", SPELLS, 119, 120, build_spell_body),
    ("Ability.pfs record 188", ABILS, 188, 142, build_abil_body),
]


def splice_at(span, rec):
    """Where a new record's body goes: in front of the first record with a LARGER id, or at the
    end of the payload if there is none.

    Records are sorted by id AND by offset and both orders must agree -- index_layout() probes
    for exactly that invariant. Spell 119 lands mid-file (before 120); ability 188 is past the
    current maximum (186) and lands at the end. Deriving the point from the ID ORDER rather than
    from the donor is what lets one code path serve both.
    """
    later = [i for i in span if i > rec]
    return min(span[i][0] for i in later) if later else max(e for _a, e in span.values())


def insert(d, rec, donor_id, builder):
    base, ent, wide_start, span = records(d)
    assert rec not in span, "record %d already present" % rec
    body = builder(body_of(d, base, span, donor_id))
    at = splice_at(span, rec)
    N = sum(1 for e in ent if e[3] == 4)
    p, _ns = index_header(d, wide_start, N)
    assert all(i < rec for i, _o, _pos, w in ent if w == 1), \
        "a SMALL index entry has an id past ours; its u8 offset could need to move"
    out = bytearray(d)
    for i, o, pos, w in ent:
        if w == 4 and o >= at:
            struct.pack_into("<I", out, pos, o + len(body))
    k = sum(1 for i, _o, _p, w in ent if w == 4 and i < rec)
    out[wide_start + 8 * k: wide_start + 8 * k] = struct.pack("<II", rec, at)
    struct.pack_into("<I", out, p + 1, N + 1)
    out[base + 8 + at: base + 8 + at] = body                # payload base moved +8
    return out, body


def remove(d, rec):
    base, ent, wide_start, span = records(d)
    assert rec in span, "record %d is not present" % rec
    at, end = span[rec]
    n = end - at
    N = sum(1 for e in ent if e[3] == 4)
    p, _ns = index_header(d, wide_start, N)
    out = bytearray(d)
    del out[base + at: base + at + n]
    k = sum(1 for i, _o, _p, w in ent if w == 4 and i < rec)
    del out[wide_start + 8 * k: wide_start + 8 * k + 8]
    struct.pack_into("<I", out, p + 1, N - 1)
    for i, o, pos, w in ent:
        if w == 4 and i != rec and o > at:
            struct.pack_into("<I", out, pos - 8, o - n)
    return out


def fix_crc(out):
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE, "CRC repair failed"
    return out


def audit(old, new, rec, expect_present):
    """Every OTHER record must survive byte-identical.

    `rec` itself is excluded: on the rewrite path (a stale build already in the file) it is
    SUPPOSED to differ, and an earlier version of this check flagged that intended change and
    aborted. Excluding it keeps the guard meaningful -- it still proves the splice touched
    nothing else -- without making a re-tune impossible.
    """
    ob, _oe, _w, osp = records(old)
    nb, _ne, _w2, nsp = records(new)
    for rid in sorted((set(osp) & set(nsp)) - {rec}):
        if body_of(old, ob, osp, rid) != body_of(new, nb, nsp, rid):
            return "record %d changed" % rid
    if expect_present and rec not in nsp:
        return "record %d missing after insert" % rec
    if not expect_present and rec in nsp:
        return "record %d still present after removal" % rec
    missing = set(osp) - set(nsp) - ({rec} if not expect_present else set())
    if missing:
        return "records disappeared: %s" % sorted(missing)
    return None


def fields_of(body):
    ent, dsz = T.body_dir(body)
    return T.slice_fields(body, ent, dsz)


def status(label, path, rec, donor_id, builder):
    d = read(path)
    ok = zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF == PFS_RESIDUE
    base, ent, _w, span = records(d)
    present = rec in span
    match = present and body_of(d, base, span, rec) == builder(body_of(d, base, span, donor_id))
    return dict(label=label, path=path, rec=rec, donor=donor_id, builder=builder, d=d, ok=ok,
                n=len(ent), present=present, match=match)


def show():
    print("build_embrittle_pfs -- the data records for Embrittlement (spell 109 / ability 0xB2)")
    print("target: %s" % GAME)
    print()
    out = []
    for tgt in TARGETS:
        st = status(*tgt)
        out.append(st)
        print("  %-24s %3d records, CRC %s"
              % (st["label"], st["n"], "OK" if st["ok"] else "WRONG -- file damaged"))
        print("       record %-4d %s" % (st["rec"],
              ("PRESENT, matches this build" if st["match"] else "PRESENT but DIFFERS -- will be rewritten")
              if st["present"] else "absent"))
    return out


def dis():
    for label, path, rec, donor_id, builder in TARGETS:
        d = read(path)
        base, _e, _w, span = records(d)
        body = body_of(d, base, span, rec) if rec in span else builder(
            body_of(d, base, span, donor_id))
        print()
        print("; ---- %s (%s) ----" % (label, "installed" if rec in span else "THIS BUILD"))
        for t, v in sorted(fields_of(body).items()):
            is_desc = (path == SPELLS and t == TAG_DESC) or (path == ABILS and t == ABIL_TAG_DESC)
            if is_desc:
                print("  tag %#04x  description : %r" % (t, v[4:].decode("latin1")))
            elif path == SPELLS and t in (TAG_MANA, TAG_RESEARCH):
                print("  tag %#04x  %-11s: %d" % (t, "mana" if t == TAG_MANA else "research",
                                                  struct.unpack("<I", v)[0]))
            elif path == SPELLS and t in (TAG_SPHERE, TAG_TIER):
                print("  tag %#04x  %-11s: %d" % (t, "sphere" if t == TAG_SPHERE else "tier", v[0]))
            elif path == SPELLS and t == TAG_IMG:
                needle = struct.pack("<I", len(ICON_PATH)) + ICON_PATH
                i = v.find(needle)
                print("  tag %#04x  images      : %d B, SPELLICN.ILB icon index = %d"
                      % (t, len(v), struct.unpack_from("<I", v, i + len(needle) + 3)[0]))
            else:
                tail = "  (selection mask -- 0 keeps it status-only)" if path == ABILS and t == 9 else ""
                print("  tag %#04x  %-11s: %3d B  %s%s"
                      % (t, "field", len(v), v.hex(" ") if len(v) <= 8 else "", tail))


def apply(undo=False):
    for st in show():
        label, path, rec = st["label"], st["path"], st["rec"]
        donor_id, builder = st["donor"], st["builder"]
        if not st["ok"]:
            sys.exit("ABORT: %s CRC residue already wrong -- refusing to write a damaged file"
                     % label)
        if undo and not st["present"]:
            print("\n  %s: not present -- nothing to do" % label)
            continue
        if not undo and st["match"]:
            print("\n  %s: already applied -- nothing to do" % label)
            continue
        d = st["d"]
        before = len(d)
        # ⚠ Snapshot on apply ONLY. A snapshot means "the state before this feature was applied",
        # so minting one during --undo copies the PATCHED file to a name that reads as pre-patch.
        # That was masked until 2026-09-10 by a stale snapshot already sitting at the old path;
        # once snapshots moved to backups\ and the loose ones were pruned, this guard became
        # load-bearing.
        backup = os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)
        if not undo and not os.path.exists(backup):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, backup)
            print("\n  backup -> %s" % backup)
        if st["present"]:
            d = remove(d, rec)              # a stale build, or --undo
        out = d if undo else insert(d, rec, donor_id, builder)[0]
        fix_crc(out)
        problem = audit(read(path), out, rec, expect_present=not undo)
        if problem:
            sys.exit("ABORT: %s post-edit audit failed -- %s (nothing written)" % (label, problem))
        with open(path, "wb") as f:
            f.write(out)
        print("  %s: record %d %s  (%d -> %d bytes, CRC repaired)"
              % (label, rec, "REMOVED" if undo else "WRITTEN", before, len(out)))
    if not undo:
        print()
        print("  NEEDS THE USER'S IN-GAME TEST:")
        print("   1. The spellbook page shows the broken-bone icon, the description, Earth")
        print("      tier %d, %d mana." % (TIER, MANA))
        print("   2. A unit hit by the spell lists the status, whose description reads as the")
        print("      mirror of Physical Protection's.")
        print("   3. Every OTHER spell and ability still shows its own icon and text -- the")
        print("      audit proves the bytes, not that the game agrees.")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--undo" in args:
        apply(undo=True)
    elif "--apply" in args:
        apply()
    else:
        show()
        dis()
        print()
        print("(dry run -- nothing written.  --apply to write, --undo to remove)")
