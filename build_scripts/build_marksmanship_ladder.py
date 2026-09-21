#!/usr/bin/env python3
r"""
AoW1 mod -- fill the COPPER gap in every unit's Marksmanship medal ladder (`Release/Unitres.pfs`).

    python build_scripts/build_marksmanship_ladder.py            # dry run + verify current state
    python build_scripts/build_marksmanship_ladder.py --apply
    python build_scripts/build_marksmanship_ladder.py --undo      # surgical, no backup needed
    python build_scripts/build_marksmanship_ladder.py --list      # per-unit before/after table

WHY. AoW1 shipped three ability-set owners per unit (base / silver / gold). `build_copper_medal.py`
added a fourth rank, COPPER, with its own owner (tag 0x20 in the file, `[unitres+0x3C]` in memory),
but the shipped unit data was never re-laddered -- so a ranged unit that gains +1 Marksmanship per
medal skipped a rung at copper. 77 of the 82 carriers were in that state.

THE RULE (author decision 2026-08-15). The ladder gains a rank, so it gains a level: base keeps the
level it always had, the old silver and gold rungs each slide one rank later, and gold ends up ONE
LEVEL HIGHER than it was.

    before   (base B,   --,        silver S,  gold G)
    after    (base B,   copper S,  silver G,  gold G+1)

Carriers are IDENTIFIED by Marksmanship at gold. Nothing is ever weakened and no base rung is
created or destroyed -- the only edits are a new copper rung and +1 at gold (silver takes the old
gold level, which is also +1).

  ⚠ An earlier version of this script anchored on GOLD and worked backwards (silver=G-1, copper=G-2,
  base=G-3). That was mis-specified and is NOT what shipped: it left the 50-unit (--,--,1,2) group
  untouched, removed base Marksmanship from 14 units and lowered it on 12 more. Do not reinstate it.

EXEMPTIONS -- exactly one rule, plus units that are already correct:
  * NO SILVER MARKSMANSHIP -> exempt (author instruction). Only `Earth Elemental`, which carries
    Marksmanship II at gold and nothing below, because it only gains its ranged attack at gold.
    Sliding its gold rung down to silver would grant Marksmanship to a unit that cannot shoot.
  * ALREADY HAS A COPPER RUNG -> untouched, because it is already in the target shape. Four units,
    hand-authored after the copper patch: Human Crossbowman and Catapult (--,1,2,3), Human Priest
    and Human Charlatan (1,2,3,4).

  ⚠ Those four are why TOUCHED is an explicit id set rather than a shape test. `(--,1,2,3)` is
  simultaneously the AFTER state of a (--,--,1,2) unit and the untouched state of Human Crossbowman;
  a shape test cannot tell them apart, and `--undo` would un-shift the four that were never shifted.

DEPENDS ON `build_marksmanship8.py`. The rule pushes twelve units to gold Marksmanship **V**, which
vanilla's 4-level cap would silently clamp: `TIntegerList.Get` is bounds-checked, so an over-cap
level costs nothing and `GetLevelName` returns an EMPTY string -- a blank ability name on the info
card, not a crash. The live DLL cap is therefore read (via `re_tools/ability_names.levels()`) and
asserted >= the highest level this writes, before anything is planned.

SCOPE -- data only. No binary is touched.

WHAT AN OWNER EDIT ACTUALLY INVOLVES (three fields, not one -- a KNOWN, SHIPPED BUG CLASS)
  `TAbilityOwner.ReadWrite` @0x5574F318 does NOT scan an owner for `0x32+id` record tags. It reads
  the `Engine.TIntegerList` at tag **0x31** and loads records for exactly the ids listed there. So
  granting a levelled ability needs all three of:

      tag 3      the ability bitset -- bit index IS the ability id (0x20 = bit 32), LSB-first,
                 with tag 2 holding the bit capacity (grown to >= 33 if the owner is short)
      tag 0x52   the per-ability level record (0x32 + 0x20)
      tag 0x31   the record-id list -- WITHOUT which the record is dead bytes

  Omit tag 0x31 and the unit gets the ability bit with the record never deserialised: a BARE NAME on
  the info card and no effect, and the engine's own write path then emits only listed records, so
  one AoWEd re-save DELETES the orphan. That is exactly what the Ziggurat Manual's in-browser editor
  did before 2026-08-14 -- 71 owners had to be repaired by `build_unitres_reclist.py`. This script
  maintains all three and asserts the invariant on EVERY owner in the file afterwards.

⚠ WHY A SCRIPT AND NOT THE MANUAL'S ABILITY EDITOR. The Manual embeds Unitres.pfs and can edit these
  chips, but it has no bulk operation (its toolbar is Edit / count / Download / Reset) -- this change
  is 231 owner edits across 77 units, each a fold-out row. More to the point, a scripted edit gets
  dry-run, verify-before-write, idempotency and a surgical `--undo`; the browser flow hands back a
  downloaded file with none of that. Use the Manual for one-off tweaks, this for systematic ones.

THE LEVEL RECORD FORMAT (tag 0x32+id), decoded 2026-08-15 and uniform across all 82 carriers:

      01 20 02 00 | 02 | 0a 00 | 0b 01 | LL 20 00
      \_classid_/   \n   \tag 0x0A  \tag 0x0B   \_ payload: level byte, then u16 ability id

  classid 0x00022001, a 2-entry small directory, tag 0x0A = the LEVEL (1 byte), tag 0x0B = the
  ability id (u16). 12 bytes, and only `LL` ever varies. ⚠ It carries the 4-byte classid prefix
  (`top=True`), unlike an ability-OWNER directory which does not -- parsing it with top=False
  silently yields a plausible-but-wrong directory.

  An owner that already has the record has its level byte poked IN PLACE, preserving its exact
  bytes; only an owner that lacks one gets the template emitted. Since this rule never removes a
  rung, silver and gold are always in-place pokes and only copper is ever built from scratch.

REVERSIBILITY. The rule is exactly invertible -- `(B, C, S, G) -> (B, --, C, S)` -- so no
before/after table is needed, only the ID SET it was applied to. Every unit is verified to be in a
valid before OR after shape before anything is written, so `--apply` and `--undo` are both
idempotent and neither needs a backup. When the file is wholly in the before state the derived
carrier set is asserted to equal TOUCHED, so the table cannot silently drift from the data.

  Measured 2026-08-15 over two full apply/undo round trips: `--undo` restores the file
  BYTE-IDENTICALLY (SHA1 match against `.pre-mkladder`). That holds because the rule performs no
  removals -- silver/gold are level-byte pokes, and copper is added then deleted wholesale.
  ⚠ It only holds because COPPER_HAS_BITSET below distinguishes the two kinds of empty copper owner.

⚠ A `<game dir>\backups\Unitres.pfs.pre-mkladder` snapshot is still taken on the first `--apply`,
but per CLAUDE.md it is a courtesy, NOT the revert path -- `--undo` is, and it touches no backup.

VERIFIED AGAINST THE ENGINE, not assumed: the medal grant loop @0x557828EC calls
`build_copper_medal.py`'s cave @0x55813000, which is
    mov edx, [edx + eax*4 + 0x38] ; mov eax, esi ; jmp TAbilityOwner.UpdateDefaultAbilities
-- a FOUR-entry owner array at `TUnitResource+0x38` indexed by rank, so the copper owner really is
unioned in at copper rank. ⚠ Still worth an in-game check: the copper ability-owner feature as a
whole is recorded as applied-but-untested.
"""
import argparse
import importlib.util
import os
import shutil
import struct
import zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PFS = os.path.join(GAME, "Release", "Unitres.pfs")
SUFFIX = ".pre-mkladder"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(PFS) + SUFFIX)

AID = 0x20                      # Marksmanship
REC_TAG = 0x32 + AID            # 0x52 -- the per-ability level record
LIST_TAG = 0x31
BITS_TAG, CAP_TAG = 3, 2
# rank order, and the file tag each owner lives under. ⚠ copper is 0x20 -- the same NUMBER as the
# Marksmanship ability id, which is a coincidence and not a relationship. Named constants so no
# site has to work out which 0x20 it is looking at.
RANKS = [("base", 0x19), ("copper", 0x20), ("silver", 0x1E), ("gold", 0x1F)]
LEVEL_TEMPLATE = bytes.fromhex("01200200020a000b01") + bytes([1]) + struct.pack("<H", AID)
EMPTY_OWNER = b"\x00"           # n=0: no entries, no payload


def require(cond, msg):
    """A guard `python -O` cannot strip -- every one turns a silently-wrong write into a loud
    abort, and `assert` would be removed outright by -O."""
    if not cond:
        raise SystemExit("ABORT: " + msg)


def _mod(relpath, name):
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(name, os.path.join(here, relpath))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# The directory codec, the tag-0x31 list codec and the file-index walker are REUSED from
# build_unitres_reclist.py rather than re-implemented. That script is the one that had to repair
# this very field across 71 owners, so its codec is the version proven against real AoWEd-authored
# data (670 owners), and a second copy here would be a second thing to keep right. Its main() is
# __main__-guarded, so importing it runs nothing.
_RL = _mod(os.path.join(".", "build_unitres_reclist.py"), "unitres_reclist")
dir_parse, dir_emit = _RL.dir_parse, _RL.dir_emit
list_parse, list_emit = _RL.list_parse, _RL.list_emit
index_layout, PFS_RESIDUE = _RL.index_layout, _RL.PFS_RESIDUE
_pfs = _mod(os.path.join("..", "re_tools", "pfs.py"), "pfs")

# ---------------------------------------------------------------- the affected units
# Record ids carrying Marksmanship at BOTH gold and silver but NOT at copper, measured on the
# unmodified file 2026-08-15. Excludes `Earth Elemental` (267, no silver -- author exemption) and
# the four units already in the target shape (0 Human Crossbowman, 1 Human Priest, 2 Human
# Charlatan, 253 Catapult). See the header for why this is an id set and not a shape test.
TOUCHED = frozenset({
    7, 8, 10, 18, 19, 22, 24, 25, 28, 29, 30, 36, 42, 43, 45, 46, 54, 56, 58, 60, 62, 63,
    65, 66, 72, 73, 74, 78, 82, 83, 90, 91, 94, 95, 97, 98, 101, 108, 109, 113, 115, 117,
    126, 130, 134, 136, 144, 145, 150, 162, 169, 170, 172, 180, 184, 185, 198, 199, 204,
    216, 217, 226, 230, 231, 236, 238, 239, 246, 247, 248, 252, 254, 256, 257, 258, 261, 263,
})

# Of those, the ones whose COPPER owner already carries tags 2/3 (a real, if empty, ability set)
# rather than the bare 1-byte `00` directory. Everything else in TOUCHED is bare.
#
# ⚠ WITHOUT THIS, `--undo` IS NOT BYTE-EXACT. Granting to a bare owner must create tags 2 and 3;
# removing again clears the bit and drops tags 0x31/0x52, but 2/3 legitimately remain -- an empty
# bitset with capacity 33 rather than the `00` the file had, 13 B larger per owner. The two states
# are indistinguishable AFTER the fact (Air Galley's copper owner genuinely is an empty bitset and
# must keep it), so the pre-state is recorded here rather than guessed. Asserted in collateral().
COPPER_HAS_BITSET = frozenset({7, 24, 42, 73, 82, 91, 109, 134, 238, 239})


def forward(cur):
    """(B, --, S, G) -> (B, S, G, G+1). None if `cur` is not a valid before-state."""
    b, c, s, g = cur
    if c is not None or s is None or g is None:
        return None
    return (b, s, g, g + 1)


def inverse(cur):
    """(B, C, S, G) -> (B, --, C, S). None if `cur` is not a valid after-state."""
    b, c, s, g = cur
    if c is None or s is None or g is None or g != s + 1:
        return None
    return (b, None, c, s)


for _t in ((None, None, 1, 2), (1, None, 2, 3), (2, None, 3, 4), (None, None, 3, 4)):
    require(inverse(forward(_t)) == _t, "forward/inverse disagree on %s" % (_t,))


# ---------------------------------------------------------------- bitset + owner editing
def bit_get(blob, i):
    return bool(blob[i >> 3] & (1 << (i & 7))) if (i >> 3) < len(blob) else False


def owner_level(ow):
    """(present, level) for AID in one owner blob. level is None when the record is missing --
    the dead-bytes state, NOT level 0, and the caller must be able to tell them apart."""
    if ow is None or len(ow) <= 1:
        return False, None
    d = dir_parse(ow, top=False)
    if not bit_get(d["data"].get(BITS_TAG, b""), AID):
        return False, None
    rec = d["data"].get(REC_TAG)
    if rec is None:
        return True, None
    return True, dir_parse(rec, top=True)["data"][0x0A][0]


def ladder(top):
    """The unit's current (base, copper, silver, gold) Marksmanship levels."""
    out = []
    for _lab, tag in RANKS:
        present, lv = owner_level(top["data"].get(tag))
        out.append(lv if present else None)
    return tuple(out)


def _ins(d, tag, blob):
    """Set d.data[tag], inserting the directory entry in ascending tag order if it is new."""
    d["data"][tag] = blob
    if tag not in [t for t, _s in d["ent"]]:
        at = next((k for k, (t, _s) in enumerate(d["ent"]) if t > tag), len(d["ent"]))
        d["ent"].insert(at, (tag, True))


def _del(d, tag):
    d["ent"] = [(t, s) for t, s in d["ent"] if t != tag]
    d["layout"] = [t for t in d["layout"] if t != tag]
    d["data"].pop(tag, None)


def set_owner(ow, level, bare_when_empty=False):
    """One owner blob -> the blob with AID at `level` (None = absent). All three fields maintained.

    `bare_when_empty` restores the 1-byte empty-directory form when removal leaves the owner with
    nothing at all -- see COPPER_HAS_BITSET for why that cannot be inferred from the blob itself.
    """
    d = dir_parse(ow, top=False) if ow and len(ow) > 1 else {
        "classid": None, "ent": [], "layout": [], "data": {}}

    if level is None:
        bits = bytearray(d["data"].get(BITS_TAG, b""))
        if (AID >> 3) < len(bits):
            bits[AID >> 3] &= ~(1 << (AID & 7)) & 0xFF
            _ins(d, BITS_TAG, bytes(bits))
        _del(d, REC_TAG)
        ids, ok = list_parse(d["data"].get(LIST_TAG))
        if ok:
            rest = [i for i in ids if i != AID]
            # Mirror the engine: an owner with no level records carries no list at all. Leaving an
            # empty list behind is the state build_unitres_reclist.py exists to clean up.
            if rest:
                _ins(d, LIST_TAG, list_emit(rest))
            else:
                _del(d, LIST_TAG)
        if (bare_when_empty and not any(d["data"].get(BITS_TAG, b""))
                and not [t for t in d["data"] if t >= 0x32]):
            return EMPTY_OWNER
        return dir_emit(d)

    cap = struct.unpack_from("<I", d["data"][CAP_TAG], 0)[0] if CAP_TAG in d["data"] else 0
    cap = max(cap, AID + 1)
    _ins(d, CAP_TAG, struct.pack("<I", cap))
    bits = bytearray(d["data"].get(BITS_TAG, b""))
    need = (cap + 7) // 8
    if len(bits) < need:
        bits += b"\x00" * (need - len(bits))
    bits[AID >> 3] |= 1 << (AID & 7)
    _ins(d, BITS_TAG, bytes(bits))

    # Poke the level byte of the EXISTING record where there is one, so an owner whose level merely
    # changes re-emits byte-identically apart from that byte; only mint the template when absent.
    rec = d["data"].get(REC_TAG, LEVEL_TEMPLATE)
    r = dir_parse(rec, top=True)
    require(struct.unpack_from("<H", r["data"][0x0B], 0)[0] == AID,
            "level record does not carry ability id %#x" % AID)
    r["data"][0x0A] = bytes([level])
    _ins(d, REC_TAG, dir_emit(r))

    ids, ok = list_parse(d["data"].get(LIST_TAG))
    ids = ids if ok else []
    if AID not in ids:
        _ins(d, LIST_TAG, list_emit(ids + [AID]))
    return dir_emit(d)


def unit_name(top):
    return " ".join(x for x in (_pfs.pstr(top["data"].get(10, b"")),
                                _pfs.pstr(top["data"].get(11, b""))) if x).strip()


def dll_cap():
    """The live DLL's Marksmanship ceiling, or None if it cannot be read."""
    try:
        an = _mod(os.path.join("..", "re_tools", "ability_names.py"), "ability_names")
        return an.levels().get(AID)
    except Exception:                                              # noqa: BLE001
        return None


# ---------------------------------------------------------------- plan / verify
def plan(d, undo):
    """(rows, new_bytes, errors). Pure -- never writes. rows = [(rid, name, from, to, notes)]."""
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return [], None, ["CRC residue wrong before any edit -- refusing to touch the file"]
    base, ent = index_layout(d)
    recs = _pfs.parse_index(bytes(d))
    if [a for a, _, _, _ in ent] != [r for r, _ in recs]:
        return [], None, ["index entry ids disagree with parse_index"]

    rows, errors, newbodies = [], [], {}
    seen, all_before, extra = set(), True, []
    for rid, body in recs:
        top = dir_parse(body, top=True)
        cur = ladder(top)
        if rid not in TOUCHED:
            # completeness: any OTHER carrier that qualifies would mean TOUCHED has drifted
            if cur[3] is not None and cur[2] is not None and cur[1] is None:
                extra.append((rid, unit_name(top), cur))
            continue
        seen.add(rid)
        nm = unit_name(top)
        src, dst = (inverse(cur), None) if undo else (forward(cur), None)
        if undo:
            dst, src = inverse(cur), cur
            if dst is None:                      # not in the after state -- already undone?
                if forward(cur) is not None:
                    continue                     # it is in the before state: nothing to do
                errors.append("%s (rec %d) is %s -- neither an applied nor a reverted ladder"
                              % (nm, rid, cur))
                continue
        else:
            all_before = all_before and forward(cur) is not None
            dst = forward(cur)
            if dst is None:                      # not in the before state -- already applied?
                if inverse(cur) is not None:
                    continue
                errors.append("%s (rec %d) is %s -- neither a pristine nor an applied ladder"
                              % (nm, rid, cur))
                continue
        notes = []
        for (lab, tag), c, t in zip(RANKS, cur, dst):
            if c == t:
                continue
            ow = top["data"].get(tag)
            if ow is None:
                errors.append("%s: no %s owner tag %#x to write into" % (nm, lab, tag))
                continue
            top["data"][tag] = set_owner(
                ow, t, bare_when_empty=(lab == "copper" and rid not in COPPER_HAS_BITSET))
            notes.append("%s %s->%s" % (lab, "-" if c is None else c, "-" if t is None else t))
        nb = dir_emit(top)
        chk = dir_parse(nb, top=True)
        for t, blob in top["data"].items():             # every field must survive the rebuild
            if chk["data"].get(t) != blob:
                errors.append("%s: tag %d did not survive the record rebuild" % (nm, t))
        newbodies[rid] = nb
        rows.append((rid, nm, cur, dst, ", ".join(notes)))

    for rid in sorted(TOUCHED - seen):
        errors.append("record %d is not in this Unitres.pfs" % rid)
    # Only meaningful when nothing has been applied yet; once shifted, the qualifying shape changes.
    if not undo and all_before and extra:
        errors.append("TOUCHED is incomplete -- these carriers also qualify: %s"
                      % ", ".join("%d %s %s" % e for e in extra))
    if not errors and not undo and rows:
        top_level = max(r[3][3] for r in rows)
        cap = dll_cap()
        if cap is None:
            errors.append("could not read the live DLL's Marksmanship cap -- refusing to write "
                          "levels that may exceed it")
        elif cap < top_level:
            errors.append("this ladder writes Marksmanship %d but the live DLL caps it at %d "
                          "(run build_marksmanship8.py --apply first; over-cap levels cost no "
                          "skill points and render with an EMPTY name)" % (top_level, cap))
    if errors or not newbodies:
        return rows, None, errors

    out = bytearray(d[:base])
    offs, pos, last = {}, 0, recs[-1][0]
    for rid, body in recs:
        if rid == last:                                 # final body swallows the trailing CRC dword
            body = body[:-4]
        nb = newbodies.get(rid, body)
        offs[rid] = pos
        out += nb
        pos += len(nb)
    out += d[-4:]
    for rid, _o, fieldpos, w in ent:
        v = offs[rid]
        if w == 1:
            if v > 0xFF:
                return rows, None, ["index small-entry offset %d overflows u8" % v]
            out[fieldpos] = v
        else:
            struct.pack_into("<I", out, fieldpos, v)
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    if zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return rows, None, ["CRC repair failed"]
    return rows, bytes(out), []


def collateral(old_d, new_d, touched, undo):
    """'' if the rewrite touched only the planned records and left every owner self-consistent."""
    o, n = _pfs.parse_index(old_d), _pfs.parse_index(new_d)
    if [r for r, _ in o] != [r for r, _ in n]:
        return "record id list changed"
    last = n[-1][0]
    ob, nb = dict(o), dict(n)
    for rid in ob:
        a, b = ob[rid], nb[rid]
        if rid == last:
            a, b = a[:-4], b[:-4]
        if rid not in touched and a != b:
            return "record %d changed but was not planned to" % rid
    for rid, body in n:
        top = dir_parse(body, top=True)
        if rid in touched:
            cur = ladder(top)
            want_shape = inverse if undo else forward
            if want_shape(cur) is None and (inverse(cur) is None and forward(cur) is None):
                return "record %d came out in no recognisable shape: %s" % (rid, cur)
            # byte-fidelity of the undo: a bare copper owner must come back BARE, not as an empty
            # bitset. Without this the undo is correct-but-not-identical and nothing would say so.
            if undo and rid not in COPPER_HAS_BITSET and top["data"].get(0x20) != EMPTY_OWNER:
                return ("record %d copper owner did not return to the bare form (%d B, expected 1)"
                        % (rid, len(top["data"].get(0x20, b""))))
        # the invariant build_unitres_reclist.py exists to enforce, re-checked on EVERY owner in
        # the file -- not just the ones we touched, so a pre-existing break is caught too
        for _lab, otag in RANKS:
            ow = top["data"].get(otag)
            if ow is None or len(ow) <= 1:
                continue
            d = dir_parse(ow, top=False)
            got = sorted(t - 0x32 for t in d["data"] if t >= 0x32)
            ids, ok = list_parse(d["data"].get(LIST_TAG))
            if got and (not ok or set(ids) != set(got)):
                return "record %d owner %#x: list %s != records %s" % (rid, otag, ids, got)
            if not got and LIST_TAG in d["data"]:
                return "record %d owner %#x kept a list with no records" % (rid, otag)
            if bit_get(d["data"].get(BITS_TAG, b""), AID) != (REC_TAG in d["data"]):
                return ("record %d owner %#x: Marksmanship bit and level record disagree "
                        "(bare-name state)" % (rid, otag))
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--apply", action="store_true", help="write the file (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="restore the prior ladders (surgical)")
    ap.add_argument("--list", action="store_true", help="print the full per-unit table")
    a = ap.parse_args()

    d = open(PFS, "rb").read()
    rows, out, errors = plan(d, a.undo)
    for e in errors:
        print("[x] %s" % e)
    if errors:
        raise SystemExit(1)
    print("[rule ] (B,-,S,G) -> (B,S,G,G+1): copper takes the old silver level, gold gains one")
    print("[exempt] no silver Marksmanship: Earth Elemental | already correct: Human Crossbowman, "
          "Human Priest, Human Charlatan, Catapult")
    if not rows:
        print("[= ] all %d ladders already in the %s state -- nothing to do"
              % (len(TOUCHED), "original" if a.undo else "target"))
        return
    print("[cap  ] live DLL Marksmanship ceiling %s; highest level written %d"
          % (dll_cap(), max(r[3][3] for r in rows)))
    if a.list or not a.apply:
        shapes = {}
        for _rid, _nm, cur, dst, _n in rows:
            shapes.setdefault((cur, dst), []).append(_nm)
        for (cur, dst), names in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
            print("   %-20s -> %-20s x%-3d  %s%s"
                  % (str(cur), str(dst), len(names), ", ".join(names[:3]),
                     ", ..." if len(names) > 3 else ""))
    touched = {r[0] for r in rows}
    bad = collateral(d, out, touched, a.undo)
    if bad:
        raise SystemExit("[x] collateral: %s" % bad)
    print("[chk  ] %d units, %d owner edits; untouched records byte-identical; every owner's "
          "tag-0x31 list == its records and bit == record; CRC residue %#010X OK"
          % (len(rows), sum(len(r[4].split(", ")) for r in rows), PFS_RESIDUE))
    if not a.apply:
        print("[dry  ] re-run with --apply to write (close AoW.exe / AoWDevEd.exe first)")
        return
    bp = BACKUP
    # Only ever from an un-edited file: on --undo the current file is the PATCHED state, and a
    # snapshot taken there is the "a .pre-* is not proof of anything" artefact CLAUDE.md warns of.
    if not a.undo and not os.path.exists(bp):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(PFS, bp)
        print("[bak  ] %s" % bp)
    tmp = PFS + ".tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(out)
        os.replace(tmp, PFS)
    except PermissionError:
        print("[x] LOCKED -- close AoW.exe / AoWCompat.exe / AoWDevEd.exe (nothing written)")
        raise SystemExit(1)
    print("[ok   ] %s %s (%d -> %d B); revert: --undo"
          % ("reverted" if a.undo else "wrote", os.path.basename(PFS), len(d), len(out)))


if __name__ == "__main__":
    main()
