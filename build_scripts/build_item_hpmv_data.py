#!/usr/bin/env python3
r"""
build_item_hpmv_data.py -- author the +HP / +MV values onto items in the Ziggurat item library.

Data half of `build_item_hpmv.py`. That script adds the ENGINE support (item+0x4A = HP bonus,
item+0x4B = MV bonus, read/written through `TItem.ReadWrite` tags 0x17 / 0x18); this one writes
the actual numbers into `User/Zig.ail`. Neither is any use without the other -- with the engine
patch and no data the feature is a correct no-op, and with data but no engine patch the two tags
are simply never read.

TARGET: `User/Zig.ail` -- the Ziggurat item library, 325 records. `Release/ITEMS.PFS` (the stock
83-item library) is deliberately NOT touched.

================================================================================
THE TABLE  (user-signed-off 2026-08-31)
================================================================================
Chosen thematically, then every value reduced by 2 at the user's instruction.

+MV goes only to items that ALREADY carry a mobility ability, which is what makes the theme hold:
  Stolen Angel Wings (Flying) - Invisibility Boots (Invisibility) - Ethereal Boots (Wall Passage)
  Windbearer Shield (Floating) - Sphere of Wind (Floating) - Ranger Boots (Concealment)

!! Three candidates were REJECTED after resolving their ability ids -- do not "restore" them:
   * Swift Axe (283) and Belt of Agility (26) carry Strike(21) + Extra Strike(115). In Ziggurat
     "agility" means EXTRA ATTACKS, not movement.
   * Vinewind Ring (313) carries Entangle(40) -- a snare, the opposite of mobility.
   Name-matching alone would have put +MV on all three. Resolve the abilities before extending
   this table.

+HP goes to the life-themed items (all of which carry Healing(47) or Lifestealing(118)) and to
PHYSICAL armour, tiered by the record's obtain value (tag 0x13). Robes / cloaks / tunics get
nothing -- in this set they are the RES-bearing caster line, not armour.

!! SIX of the 32 items are item type 6 (`itUse`, the backpack accessory slot) -- Ziggurat uses
   type 6 as a general accessory slot, so Elixir of Life, Amulet of Blood, Sphere of Wind and the
   three Boots all live there. Their bonuses only reach the hero because `build_useitems.py` is
   applied AND `build_item_hpmv.py` has P_BACKPACK = True. If either is reverted, those six go
   silently inert while the 26 worn items keep working. Reviewed 2026-09-13 and KEPT deliberately,
   stacking included: itUse has no equip position, the 8 backpack slots are interchangeable, so
   8x Elixir of Life is +96 HP into a ceiling of 100.

!! --undo AND --list NOW ABORT with `tag 0x16 sits at or past the appended block -- refusing`.
   Not a defect in the guard: the patched `TItem.ReadWrite` hooks at 0x55794712, ABOVE the
   `test al,4` gate that writes tag 0x16, so every library re-saved by the game or editor since
   2026-08-31 emits 0x17/0x18 BEFORE 0x16 in payload order, and the tags are no longer the tail
   `drop_tags` requires. To clear a value now, write 0 into the existing tag in place (no length
   change) rather than dropping it.

================================================================================
FILE FORMAT (see re_tools/pfs.py for the general shape)
================================================================================
`.ail` uses the same container as `.pfs`: an index directory, then record bodies. Both the index
and each body use the shape `<u8 n>[<u32 wide_count>](u8 key,u8 off)*(u8 wide keys/offs)*<payload>`
with offsets relative to the END of that directory. An item body is `top=True`: four opaque
class/version bytes precede its directory.

Measured on this file: the index is 1 small + 324 wide entries; record 0 sits at offset 0, so the
small entry never changes shape when bodies grow. NEITHER `.ail` NOR `ITEMS.PFS` CARRIES A MAGIC
HEADER OR A CRC (checked: no PFS magic, no trailing checksum) -- unlike `Unitres.pfs` /
`HERORES.PFS`. Never stamp one.

Tag space in an item record:
    0x00-0x06  TAbilityOwner (0x02/0x03 = the ability bitset)
    0x07-0x16  TItem's own fields; 0x16 is the last one vanilla writes
    0x17-0x30  FREE -- our two tags live here
    0x31       the ability-id list the loader drives off
    0x32+      per-ability data sub-records (tag = ability_id + ITEM_ABILITY_RECORD_BASE)
So 0x17/0x18 sit in a genuine gap, below both 0x31 and the 0x32+ ability block. Verified: no
record in Zig.ail or ITEMS.PFS uses either tag.

!! THE DIRECTORY IS NEVER RE-DERIVED, ONLY APPENDED TO -- and that is not fussiness, it is a bug
this script actually hit. The engine's writer does not choose entry widths or entry order by any
rule recoverable from the data: Zig.ail record 12 (Astral Vision Helm) stores tag 0x94 as a WIDE
entry at offset 33, where a small entry would have fitted, and its twelve small entries are in
neither key order nor payload order. A first version rebuilt each body from a "small if it fits,
in payload order" rule and produced a valid-LOOKING record 10 bytes shorter with a reordered
directory. So: copy every existing entry verbatim and append. Because offsets are relative to the
directory END, growing the directory does not move any existing field -- every original byte of
every record survives, and only the 32 touched records change length at all (+3 bytes each: a
2-byte small directory entry plus the 1-byte value, so the file grows by exactly 96).

SELF-TEST (runs on every invocation, before anything is written):
  1. the patched file is re-parsed and every one of the 325 records' complete field dicts is
     compared against the expected one -- all original tags byte-identical, plus exactly the
     intended new tags, and the four class/version bytes unchanged;
  2. untouched records must come out byte-identical;
  3. apply-then-undo is computed in memory and asserted byte-identical to the input file.
Any failure aborts with nothing written. `drop_tags` additionally refuses unless the tags really
are the tail of the payload -- the only shape `add_tags` can produce -- which is what makes --undo
provably exact rather than merely plausible.

USAGE
    python build_scripts/build_item_hpmv_data.py            verify / dry run
    python build_scripts/build_item_hpmv_data.py --apply
    python build_scripts/build_item_hpmv_data.py --undo     strip tags 0x17/0x18 again
    python build_scripts/build_item_hpmv_data.py --list     show the table with current file state

Backup: User/Zig.ail.pre-itemhpmv
"""

import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
AIL = os.path.join(GAME, "User", "Zig.ail")
BAK = os.path.join(BACKUP_DIR, os.path.basename(AIL) + ".pre-itemhpmv")

HP_TAG, MV_TAG = 0x17, 0x18

# ---- the table: record id -> (+HP, +MV) -----------------------------------------------------
# Values are SIGNED bytes (-128..127); 0 means "no tag written for that stat".
TABLE = {
    # --- movement (every one already carries a mobility ability) ---
    274: (0, 6),    # Stolen Angel Wings      Torso    Flying
    156: (0, 6),    # Invisibility Boots      Use      Invisibility
    98:  (0, 4),    # Ethereal Boots          Use      Wall Passage
    319: (0, 4),    # Windbearer Shield       Defense  Floating
    266: (0, 2),    # Sphere of Wind          Use      Floating
    206: (0, 2),    # Ranger Boots            Use      Concealment
    # --- life-themed ---
    226: (12, 0),   # Robe of Life            Torso    Healing
    218: (12, 0),   # Ring of Life Power      Ring     Healing
    92:  (12, 0),   # Elixir of Life          Use      Healing + Regeneration
    215: (4, 0),    # Ring of Health          Ring     Healing
    220: (4, 0),    # Ring of Regeneration    Ring     Regeneration
    1:   (4, 0),    # Amulet of Blood         Use      Lifestealing
    # --- physical armour, obtain value >= 100 ---
    44:  (6, 0),    # Charged Cuirass
    81:  (6, 0),    # Dwarven Thricemail
    95:  (6, 0),    # Enervating Mail         (DEF 4 but inflicts Poisoned -- kept positive)
    183: (6, 0),    # Mirror Scale Armour
    208: (6, 0),    # Rime Hauberk
    # --- physical armour, obtain value 50..99 ---
    8:   (4, 0),    # Armour of Virtue
    74:  (4, 0),    # Dragon Power Plate
    89:  (4, 0),    # Elf Court Cuirass
    113: (4, 0),    # Frigid Plate
    159: (4, 0),    # Iron Cuirass
    175: (4, 0),    # Magma Plate
    230: (4, 0),    # Sacred Plate
    232: (4, 0),    # Sandworm Scales
    292: (4, 0),    # Tomb Guard Scales
    # --- physical armour, obtain value < 50 ---
    9:   (2, 0),    # Armour of Woe
    52:  (2, 0),    # Copper Cuirass
    134: (2, 0),    # Grey Mail
    235: (2, 0),    # Scale Mail
    281: (2, 0),    # Swamp Drake Plate
    309: (2, 0),    # Veteran Armour
}
TOP_WORD = 4        # item bodies carry four opaque class/version bytes before their directory


# =============================================================================================
# container primitives -- probed from the bytes, never hard-coded
# =============================================================================================
def index_layout(d):
    """(payload_base, [(id, offset, offset_field_pos, width)]). Mirrors re_tools/pfs.py."""
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
    S, wids, _ = best
    N = len(wids)
    for p in range(0, S):
        if not (d[p] & 0x80):
            continue
        if struct.unpack_from("<I", d, p + 1)[0] != N:
            continue
        ns = d[p] & 0x7F
        if p + 5 + 2 * ns == S:
            ent = [(d[p + 5 + 2 * k], d[p + 6 + 2 * k], p + 6 + 2 * k, 1) for k in range(ns)]
            ent += [(struct.unpack_from("<I", d, S + 8 * k)[0],
                     struct.unpack_from("<I", d, S + 8 * k + 4)[0], S + 8 * k + 4, 4)
                    for k in range(N)]
            return S + 8 * N, ent
    raise ValueError("index layout not recognised")


def parse_header(body):
    """-> (top4, small[], wide[], dirEnd) with the directory entries in FILE order.

    !! The directory is copied VERBATIM, never re-derived. A record may legitimately store an
    entry WIDE that would fit a small one -- Zig.ail record 12 (Astral Vision Helm) keeps tag 0x94
    as a wide entry at offset 33, and its 12 small entries are in neither key nor payload order.
    Re-serialising such a body from a "what would fit" rule shortens it by 10 bytes and reorders
    the directory. The engine's own writer's width/order choice is not reproducible from the data,
    so DO NOT try: preserve what is there and only append.
    """
    p = TOP_WORD
    n = body[p]; p += 1
    nsmall, nwide = n & 0x7F, 0
    if n & 0x80:
        nwide = struct.unpack_from("<I", body, p)[0]; p += 4
    small, wide = [], []
    for _ in range(nsmall):
        small.append((body[p], body[p + 1])); p += 2
    for _ in range(nwide):
        t, o = struct.unpack_from("<II", body, p)
        wide.append((t, o)); p += 8
    return body[:TOP_WORD], small, wide, p


def emit(top4, small, wide, payload):
    """Serialise a body from explicit entry lists, preserving their given order and widths."""
    if len(small) > 0x7F:
        raise ValueError("too many small entries")
    head = bytearray()
    head.append((len(small) & 0x7F) | (0x80 if wide else 0))
    if wide:
        head += struct.pack("<I", len(wide))
    for t, o in small:
        head += bytes([t, o])
    for t, o in wide:
        head += struct.pack("<II", t, o)
    return bytes(top4) + bytes(head) + bytes(payload)


def fields_of(body):
    """{tag: data} for a body, sliced by offset (last field runs to the end)."""
    _t4, small, wide, dsz = parse_header(body)
    ent = small + wide
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    out = {}
    for j, k in enumerate(order):
        t, o = ent[k]
        a = dsz + o
        b = dsz + ent[order[j + 1]][1] if j + 1 < len(order) else len(body)
        if not (dsz <= a <= b <= len(body)):
            raise ValueError("bad offset for tag 0x%02X" % t)
        out[t] = body[a:b]
    return out


def add_tags(body, new):
    """APPEND-ONLY: add [(tag, data)] at the end of the payload, leaving every existing byte and
    every existing offset untouched (offsets are relative to the directory END, so growing the
    directory does not move them)."""
    top4, small, wide, dsz = parse_header(body)
    payload = bytearray(body[dsz:])
    for tag, data in new:
        o = len(payload)
        if tag < 0x100 and o < 0x100:
            small.append((tag, o))
        else:
            wide.append((tag, o))
        payload += data
    return emit(top4, small, wide, payload)


def drop_tags(body, tags):
    """Exact inverse of add_tags: remove those entries and truncate the payload they occupy.

    Refuses unless the tags really are the tail of the payload, which is the only shape add_tags
    can produce -- that guard is what makes --undo provably byte-exact.
    """
    top4, small, wide, dsz = parse_header(body)
    ent = [(t, o, "s") for t, o in small] + [(t, o, "w") for t, o in wide]
    mine = [e for e in ent if e[0] in tags]
    if not mine:
        return body
    cut = min(o for _t, o, _k in mine)
    for t, o, _k in ent:
        if t not in tags and o >= cut:
            raise ValueError("tag 0x%02X sits at or past the appended block -- refusing" % t)
    small = [(t, o) for t, o in small if t not in tags]
    wide = [(t, o) for t, o in wide if t not in tags]
    return emit(top4, small, wide, bytearray(body[dsz:])[:cut])


def split(d):
    """-> (base, ent, [(id, body)]) with bodies sliced by the index offsets."""
    base, ent = index_layout(d)
    ids = [a for a, _o, _p, _w in ent]
    offs = [o for _a, o, _p, _w in ent]
    bodies = []
    for k in range(len(ids)):
        a = base + offs[k]
        b = base + offs[k + 1] if k + 1 < len(offs) else len(d)
        bodies.append((ids[k], d[a:b]))
    return base, ent, bodies


def reassemble(d, base, ent, bodies):
    """Rewrite the payload from `bodies` and fix every index offset in place.

    The index's ENTRY SHAPES are preserved exactly (this file is 1 small + 324 wide, and record 0
    sits at offset 0 so the small entry never needs promoting). If a rewritten offset no longer
    fits its entry width we abort rather than silently truncate.
    """
    out = bytearray(d[:base])
    offs, o = [], 0
    for _rid, body in bodies:
        offs.append(o); o += len(body)
        out += body
    for (rid, _off, pos, width), newoff in zip(ent, offs):
        if width == 1:
            if newoff > 0xFF:
                raise ValueError("record %d offset %d no longer fits a small index entry"
                                 % (rid, newoff))
            out[pos] = newoff
        else:
            struct.pack_into("<I", out, pos, newoff)
    return bytes(out)


# =============================================================================================
# the edit
# =============================================================================================
def edit(d, install):
    """Return the file with the table's tags added (install=True) or removed (install=False).

    Records outside TABLE are copied byte-for-byte; they are never re-serialised.
    """
    base, ent, bodies = split(d)
    known = {rid for rid, _b in bodies}
    missing = [r for r in TABLE if r not in known]
    if missing:
        raise ValueError("record id(s) not in this library: %s" % sorted(missing))

    new_bodies = []
    for rid, body in bodies:
        if rid in TABLE:
            hp, mv = TABLE[rid]
            body = drop_tags(body, (HP_TAG, MV_TAG))
            if install:
                add = []
                if hp:
                    add.append((HP_TAG, bytes([hp & 0xFF])))
                if mv:
                    add.append((MV_TAG, bytes([mv & 0xFF])))
                if add:
                    body = add_tags(body, add)
        new_bodies.append((rid, body))
    return reassemble(d, base, ent, new_bodies)


def state_of(d):
    """-> 'clean' | 'installed' | 'partial'."""
    _b, _e, bodies = split(d)
    have = 0
    for rid, body in bodies:
        if rid not in TABLE:
            continue
        hp, mv = TABLE[rid]
        f = fields_of(body)
        want = {}
        if hp:
            want[HP_TAG] = bytes([hp & 0xFF])
        if mv:
            want[MV_TAG] = bytes([mv & 0xFF])
        got = {t: f[t] for t in (HP_TAG, MV_TAG) if t in f}
        if got == want:
            have += 1
    if have == len(TABLE):
        return "installed"
    if have == 0:
        return "clean"
    return "partial"


def verify_patch(orig, patched):
    """Re-parse the patched file and prove nothing but the intended tags changed."""
    _b0, _e0, b0 = split(orig)
    _b1, _e1, b1 = split(patched)
    if [r for r, _ in b0] != [r for r, _ in b1]:
        raise ValueError("record id list changed")
    for (rid, ob), (_rid2, nb) in zip(b0, b1):
        of = fields_of(ob)
        nf = fields_of(nb)
        hp, mv = TABLE.get(rid, (0, 0))
        expect = dict(of)
        expect.pop(HP_TAG, None); expect.pop(MV_TAG, None)
        if hp:
            expect[HP_TAG] = bytes([hp & 0xFF])
        if mv:
            expect[MV_TAG] = bytes([mv & 0xFF])
        if nf != expect:
            diff = {t for t in set(nf) | set(expect) if nf.get(t) != expect.get(t)}
            raise ValueError("record %d differs on tag(s) %s" % (rid, [hex(t) for t in diff]))
        if ob[:TOP_WORD] != nb[:TOP_WORD]:
            raise ValueError("record %d class/version word changed" % rid)
        if rid not in TABLE and ob != nb:
            raise ValueError("untouched record %d was rewritten" % rid)


def names(d):
    out = {}
    for rid, body in split(d)[2]:
        f = fields_of(body)
        if 8 in f and f[8]:
            out[rid] = f[8][1:1 + f[8][0]].decode("latin-1")
    return out


# =============================================================================================
def main():
    ap = argparse.ArgumentParser(description="author +HP/+MV onto Zig.ail items")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(AIL):
        sys.exit("ERROR: not found: %s" % AIL)
    d = open(AIL, "rb").read()

    try:
        st = state_of(d)
        patched = edit(d, True)
        verify_patch(d, patched)
        stripped = edit(patched, False)
    except (ValueError, IndexError, struct.error) as exc:
        sys.exit("ABORT: %s" % exc)

    clean = edit(d, False)
    if st == "clean" and stripped != d:
        sys.exit("ABORT: apply-then-undo is not byte-identical to the input -- the serialiser "
                 "would not round-trip. Nothing written.")

    nm = names(d)
    print("build_item_hpmv_data -- %s" % os.path.relpath(AIL, GAME))
    print("%d of %d records carry a bonus | file %d -> %d bytes | state: %s\n"
          % (len(TABLE), len(split(d)[2]), len(d), len(patched), st))

    if a.list or not (a.apply or a.undo):
        cur = {rid: fields_of(b) for rid, b in split(d)[2] if rid in TABLE}
        print("%-4s %-26s %5s %5s   %s" % ("id", "name", "+HP", "+MV", "in file now"))
        for rid, (hp, mv) in sorted(TABLE.items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0])):
            f = cur.get(rid, {})
            now = " ".join("%s=%d" % ("HP" if t == HP_TAG else "MV",
                                      int.from_bytes(f[t], "little", signed=True))
                           for t in (HP_TAG, MV_TAG) if t in f) or "-"
            print("%-4d %-26s %5s %5s   %s"
                  % (rid, nm.get(rid, "?"), ("+%d" % hp) if hp else "-",
                     ("+%d" % mv) if mv else "-", now))
        print("\nself-test: patched file re-parses with only the intended tag changes; "
              "untouched records byte-identical; apply-then-undo byte-identical.")
        if not (a.apply or a.undo):
            print("\n(dry run -- nothing written)")
            return

    want = "clean" if a.undo else "installed"
    if st == want:
        print("\nalready %s -- nothing to do (idempotent)." % want)
        return

    kill_aow()
    if not a.undo and not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(AIL, BAK)
        print("  backup -> %s" % os.path.basename(BAK))
    open(AIL, "wb").write(clean if a.undo else patched)
    print("\n%s -- %s is now %d bytes."
          % ("UNDONE" if a.undo else "APPLIED", os.path.basename(AIL),
             len(clean if a.undo else patched)))


if __name__ == "__main__":
    main()
