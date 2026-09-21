#!/usr/bin/env python3
r"""Reconcile every ability owner's tag-0x31 record-id list in `Release/Unitres.pfs`.

    python build_scripts/build_unitres_reclist.py            # dry run: list every owner to fix
    python build_scripts/build_unitres_reclist.py --apply
    python build_scripts/build_unitres_reclist.py --undo     # restore the .pre-reclist backup

THE BUG THIS REPAIRS. `TAbilityOwner.ReadWrite` @0x5574F318 does not scan an owner for
`0x32+id` record tags: it reads the `Engine.TIntegerList` stored at **tag 0x31** and loads
records for exactly the ids listed there. The Ziggurat Manual's in-browser ability editor
(before 2026-08-14) minted and added level records without maintaining that list, so every
ability it ADDED sat in the file as dead bytes: the bit set, the record never deserialised,
the unit granted the ability at level 0 -- a bare name on the card and no effect. 71 owners
were in that state when this script was written (silver Leadership II showing as bare
"Leadership" was the symptom that exposed it). Worse, the engine's WRITE path also emits only
listed records, so one AoWEd re-save of the resource set would have deleted them all.

The transform, per owner that has any `0x32+id` records:
  * tag 0x31 absent            -> insert `[u32 0][u32 count][u32 ids...]`, ids ascending
  * list != records            -> keep the old order for ids that still have records, drop
                                  stale ids (records since removed), append missing ascending
  * records gone, list remains -> drop tag 0x31 (mirrors the engine: no records, no list)
  * sets already equal         -> UNTOUCHED, even with trailing slack after the list
                                  (vanilla Carrack gold carries 4 slack bytes; the loader
                                  reads count items and ignores the rest)

Format verified empirically across 670 AoWEd-authored owners (vanilla + April upload): first
dword always 0, insertion order arbitrary, `8 + 4*count` bytes plus tolerated slack.

⚠ `--undo` is NOT surgical: it restores `<game dir>\backups\Unitres.pfs.pre-reclist` wholesale,
wiping any Unitres edit made after `--apply`. There is nothing to surgically undo *to* -- the broken
lists carry no information the records don't. The backup is taken on first `--apply` only and
never overwritten, so if it is absent `--undo` refuses rather than guessing.
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
PFS_RESIDUE = 0x2144DF1C
SUFFIX = ".pre-reclist"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
# ⚠ --undo READS this path (CRC-gates it, then copies it back) and --apply WRITES it. One constant,
# so the two can never drift apart.
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(PFS) + SUFFIX)
OWNER_TAGS = {0x19: "base", 0x20: "copper", 0x1E: "silver", 0x1F: "gold"}
LIST_TAG = 0x31


def _pfs_mod():
    """re_tools/pfs.py, resolved relative to THIS SCRIPT (the toolkit travels with it)."""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(here, "..", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --------------------------------------------------------------------------------------------
# directory codec -- full fidelity: entry order, small/wide form and payload layout preserved,
# so an untouched field re-emits byte-identically (asserted per record below).
# --------------------------------------------------------------------------------------------
def dir_parse(blob, top):
    p = 4 if top else 0
    classid = struct.unpack_from("<I", blob, 0)[0] if top else None
    n = blob[p]; p += 1
    small, wide = n & 0x7F, 0
    if n & 0x80:
        wide = struct.unpack_from("<I", blob, p)[0]; p += 4
    ent = []
    for _ in range(small):
        ent.append([blob[p], blob[p + 1], True]); p += 2
    for _ in range(wide):
        t, o = struct.unpack_from("<II", blob, p); ent.append([t, o, False]); p += 8
    ds = p
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    data, layout = {}, []
    for j, k in enumerate(order):
        t, o, _s = ent[k]
        a = ds + o
        b = ds + ent[order[j + 1]][1] if j + 1 < len(order) else len(blob)
        if not (ds <= a <= b <= len(blob)):
            raise ValueError("bad offset for tag %d" % t)
        data[t] = blob[a:b]; layout.append(t)
    return {"classid": classid, "ent": [(t, s) for t, _o, s in ent],
            "layout": layout, "data": data}


def dir_emit(d):
    """Re-emit a parsed directory. Payload in layout order (new tags appended), entry order
    preserved; a small entry whose tag/offset no longer fits u8 is demoted to wide -- the
    engine reads mixed directories (unit records are mixed already)."""
    tags = [t for t, _s in d["ent"]]
    dataorder = [t for t in d["layout"] if t in d["data"] and t in tags]
    for t in tags:
        if t not in dataorder:
            dataorder.append(t)
    offsets, payload = {}, bytearray()
    for t in dataorder:
        offsets[t] = len(payload); payload += d["data"][t]
    smalls, wides = [], []
    for t, was_small in d["ent"]:
        if was_small and t < 256 and offsets[t] < 256:
            smalls.append(t)
        else:
            wides.append(t)
    out = bytearray()
    if d["classid"] is not None:
        out += struct.pack("<I", d["classid"])
    out.append(len(smalls) | (0x80 if wides else 0))
    if wides:
        out += struct.pack("<I", len(wides))
    for t in smalls:
        out += bytes([t, offsets[t]])
    for t in wides:
        out += struct.pack("<II", t, offsets[t])
    return bytes(out) + bytes(payload)


def list_parse(blob):
    """(ids, well_formed) from a tag-0x31 field; count-driven, slack ignored (the loader does
    the same)."""
    if blob is None or len(blob) < 8:
        return None, False
    n = struct.unpack_from("<I", blob, 4)[0]
    if 8 + 4 * n > len(blob):
        return None, False
    return list(struct.unpack_from("<%dI" % n, blob, 8)), True


def list_emit(ids):
    return struct.pack("<II", 0, len(ids)) + b"".join(struct.pack("<I", i) for i in ids)


def fix_owner(ow):
    """(new_blob_or_None, note). None = no change needed."""
    d = dir_parse(ow, top=False)
    recs = sorted(t - 0x32 for t in d["data"] if t >= 0x32)
    ids, ok = list_parse(d["data"].get(LIST_TAG))
    if not recs:
        if LIST_TAG not in d["data"]:
            return None, ""
        d["ent"] = [(t, s) for t, s in d["ent"] if t != LIST_TAG]
        d["layout"] = [t for t in d["layout"] if t != LIST_TAG]
        del d["data"][LIST_TAG]
        return dir_emit(d), "records gone -> list dropped (was %s)" % [hex(i) for i in ids or []]
    if ok and set(ids) == set(recs):
        return None, ""
    keep = [i for i in (ids or []) if i in set(recs)]
    new = keep + sorted(set(recs) - set(keep))
    d["data"][LIST_TAG] = list_emit(new)
    if LIST_TAG not in [t for t, _s in d["ent"]]:
        at = next((k + 1 for k, (t, _s) in enumerate(d["ent"]) if t == 3), len(d["ent"]))
        d["ent"].insert(at, (LIST_TAG, True))
    reason = ("NO list" if ids is None else "list %s" % [hex(i) for i in ids])
    return dir_emit(d), "%s -> %s" % (reason, [hex(i) for i in new])


# --------------------------------------------------------------------------------------------
# file plumbing (same index machinery as build_pfs_typos.py)
# --------------------------------------------------------------------------------------------
def index_layout(d):
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


def plan(d, pfs):
    """(changes, new_bytes, errors). Pure. changes = [(unit, ownerlabel, note)]."""
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return [], None, ["CRC residue wrong before any edit -- refusing to touch the file"]
    base, ent = index_layout(d)
    recs = pfs.parse_index(bytes(d))
    if [a for a, _, _, _ in ent] != [r for r, _ in recs]:
        return [], None, ["index entry ids disagree with parse_index"]

    changes, errors = [], []
    newbodies = {}
    for rid, body in recs:
        top = dir_parse(body, top=True)
        nm = " ".join(x for x in (pfs.pstr(top["data"].get(10, b"")),
                                  pfs.pstr(top["data"].get(11, b""))) if x) or ("record %d" % rid)
        touched = False
        for otag, olabel in OWNER_TAGS.items():
            ow = top["data"].get(otag)
            if ow is None or len(ow) <= 1:
                continue
            try:
                nb, note = fix_owner(ow)
            except (ValueError, IndexError, struct.error) as exc:
                errors.append("%s %s owner does not parse (%s)" % (nm, olabel, exc))
                continue
            if nb is None:
                continue
            top["data"][otag] = nb
            changes.append((nm, olabel, note))
            touched = True
        if touched:
            nb = dir_emit(top)
            # fidelity check: every field except the rewritten owners must round-trip
            chk = dir_parse(nb, top=True)
            for t, blob in top["data"].items():
                if chk["data"].get(t) != blob:
                    errors.append("%s: tag %d did not survive the record rebuild" % (nm, t))
            newbodies[rid] = nb

    if errors or not changes:
        return changes, None, errors

    # splice + shift the index + repair the CRC
    out = bytearray(d[:base])
    offs = {}
    pos = 0
    last = recs[-1][0]
    for rid, body in recs:
        if rid == last:                      # final body swallows the trailing CRC dword
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
                return changes, None, ["index small-entry offset %d overflows u8" % v]
            out[fieldpos] = v
        else:
            struct.pack_into("<I", out, fieldpos, v)
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    if zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return changes, None, ["CRC repair failed"]
    return changes, bytes(out), []


def collateral(old_d, new_d, pfs, changed_units):
    o, n = pfs.parse_index(old_d), pfs.parse_index(new_d)
    if [r for r, _ in o] != [r for r, _ in n]:
        return "record id list changed"
    last = n[-1][0]
    ob, nb = dict(o), dict(n)
    for rid in ob:
        a, b = ob[rid], nb[rid]
        if rid == last:
            a, b = a[:-4], b[:-4]
        if rid not in changed_units and a != b:
            return "record %d changed but was not planned to" % rid
    # invariant: every owner's list now names exactly its records
    for rid, body in n:
        top = dir_parse(body, top=True)
        for otag in OWNER_TAGS:
            ow = top["data"].get(otag)
            if ow is None or len(ow) <= 1:
                continue
            d = dir_parse(ow, top=False)
            recs = sorted(t - 0x32 for t in d["data"] if t >= 0x32)
            ids, ok = list_parse(d["data"].get(LIST_TAG))
            if recs and (not ok or set(ids) != set(recs)):
                return "record %d owner %#x still inconsistent" % (rid, otag)
            if not recs and LIST_TAG in d["data"]:
                return "record %d owner %#x kept a list with no records" % (rid, otag)
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the file (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="restore the .pre-reclist backup (NOT surgical: wipes any Unitres "
                         "edit made after --apply)")
    a = ap.parse_args()
    pfs = _pfs_mod()

    if a.undo:
        bp = BACKUP
        if not os.path.exists(bp):
            raise SystemExit("[x] no %s to restore" % bp)
        b = open(bp, "rb").read()
        if zlib.crc32(b[4:]) & 0xFFFFFFFF != PFS_RESIDUE:
            raise SystemExit("[x] backup fails the CRC gate -- refusing to restore it")
        if not a.apply:
            print("[i  ] would restore %s (%d B) over %s -- re-run with --undo --apply"
                  % (os.path.basename(bp), len(b), os.path.basename(PFS)))
            return
        shutil.copy2(bp, PFS)
        print("[ok ] restored %s" % os.path.basename(bp))
        return

    d = open(PFS, "rb").read()
    changes, out, errors = plan(d, pfs)
    for e in errors:
        print("[x] %s" % e)
    if errors:
        raise SystemExit(1)
    if not changes:
        print("[= ] every owner's tag-0x31 list already matches its records -- nothing to do")
        return
    byunit = {}
    for nm, olabel, note in changes:
        byunit.setdefault(nm, []).append((olabel, note))
    print("[plan] %d owners across %d units:" % (len(changes), len(byunit)))
    for nm, rows in byunit.items():
        for olabel, note in rows:
            print("   %-24s %-6s %s" % (nm, olabel, note))
    changed_units = set()
    recs = pfs.parse_index(d)
    for rid, body in recs:
        top = dir_parse(body, top=True)
        nm = " ".join(x for x in (pfs.pstr(top["data"].get(10, b"")),
                                  pfs.pstr(top["data"].get(11, b""))) if x) or ("record %d" % rid)
        if nm in byunit:
            changed_units.add(rid)
    bad = collateral(d, out, pfs, changed_units)
    if bad:
        raise SystemExit("[x] collateral: %s" % bad)
    print("[chk ] %d records parse, untouched ones byte-identical, every owner list==records, "
          "CRC residue %#010X OK" % (len(recs), PFS_RESIDUE))
    if not a.apply:
        print("[i  ] dry run -- re-run with --apply to write")
        return
    bp = BACKUP
    if not os.path.exists(bp):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(PFS, bp)
        print("[bak ] %s" % bp)
    tmp = PFS + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(out)
    os.replace(tmp, PFS)
    print("[ok  ] wrote %s (%d -> %d B)" % (PFS, len(d), len(out)))


if __name__ == "__main__":
    main()
