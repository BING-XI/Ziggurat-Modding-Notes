#!/usr/bin/env python3
r"""
build_heroic_progressions.py -- every unit type's ALWAYS heroic set = one more level of each
multi-level ability that rises on the unit's own ranks, Spell Casting excepted.  Data only:
Ziggurat/Release/Unitres.pfs, tag ALWAYS_TAG.  Owner's rule 2026-10-20.

    python build_scripts/build_heroic_progressions.py              dry run (lists every grant)
    python build_scripts/build_heroic_progressions.py --apply
    python build_scripts/build_heroic_progressions.py --undo [--apply]

"Rises on the unit": its level, accumulated over base -> Copper -> Silver -> Gold (tags 0x19,
0x20, 0x1E, 0x1F; a medal set is a delta, so the running maximum), is higher at Gold than at base.
An ability that never rises -- a Shaman's flat Marksmanship -- is not progressed.  The grant is
that Gold level + 1, unless that passes the ability's live cap (ability_names.levels()); a capped
ability is reported and left out.  Spell Casting is excluded: the heroic options carry it
(build_heroic_spellcasting.py).

The Always owner is built the way the engine writes one: tag 2 = highest id + 1, tag 3 the
bitset, tag 0x31 the id list (ascending), and per ability its level record copied from the unit's
own highest-ranked record of that ability with the level replaced -- so the data class is right
for every family (TMultiLevelAbilityData / Leadership: tag 0x0A; Dispel Magic: tag 0x0B, 0x0A
being its enabled flag).  A record without heroic tags also gets the empty option owners 0x21..0x23
(one `00` byte each), as the engine's own writer emits them whenever anything heroic is present.

Left alone and reported: a type whose Always set already holds something else (the owner's own
authoring).  --undo removes an Always set equal to this script's, and the empty option owners
with it when nothing else heroic remains, which restores the original bytes.

Shares build_heroic_spellcasting.py's whole-file rebuild: the index and every directory are
re-derived each run and the unmodified file must rebuild byte for byte before anything is written.
"""
import argparse, os, struct, sys
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
import pfs, ability_names
import heroicchoice as G
from build_heroic_spellcasting import (TARGET, GAME, decode_dir, encode_dir, split, join,
                                       STAT_TAGS, OPT1, OPT2, OPT3)

SC = 0x34
RANKS = (0x19, 0x20, 0x1E, 0x1F)                 # base, Copper, Silver, Gold
DISPEL_DATA = 0x000202CD                         # level at tag 0x0B; 0x0A = enabled


def level_field(rec):
    return 0x0B if struct.unpack_from("<I", rec)[0] == DISPEL_DATA else 0x0A


def rank_levels(F, aid):
    """[(level, record bytes or None)] per rank; level 0 where the rank set lacks the ability."""
    out = []
    for tag in RANKS:
        lv, rec = 0, None
        if tag in F and len(F[tag]) > 1:
            f = pfs.parse_dir(F[tag], top=False)
            if aid in pfs.abilities_of(f) and aid + 0x32 in f:
                rec = f[aid + 0x32]
                sub = pfs.parse_dir(rec, top=True)
                lv = sub.get(level_field(rec), b"\0")[0]
        out.append((lv, rec))
    return out


def with_level(rec, level):
    prefix, fields = decode_dir(rec, top=True)
    lf = level_field(rec)
    assert any(t == lf and len(b) == 1 for t, b in fields), "level field is not one byte"
    return encode_dir(prefix, [(t, bytes([level]) if t == lf else b) for t, b in fields])


def plan_grants(F, caps):
    """[(ability id, Gold level, grant level, template record)] and [(ability id, cap)] capped."""
    grants, capped = [], []
    for aid in sorted(caps):
        if aid == SC:
            continue
        per = rank_levels(F, aid)
        run, top, tmpl = 0, 0, None
        for lv, rec in per:
            if lv > run:
                run = lv
            if rec is not None and lv >= top:
                top, tmpl = lv, rec
        if run <= per[0][0] or tmpl is None:
            continue
        if run + 1 > caps[aid]:
            capped.append((aid, caps[aid]))
            continue
        grants.append((aid, run, run + 1, tmpl))
    return grants, capped


def always_owner(grants):
    ids = [a for a, _r, _g, _t in grants]
    count = max(ids) + 1
    bits = bytearray((count + 7) // 8)
    for a in ids:
        bits[a // 8] |= 1 << (a % 8)
    fields = [(2, struct.pack("<I", count)), (3, bytes(bits)),
              (0x31, struct.pack("<II", 0, len(ids)) + b"".join(struct.pack("<I", a) for a in ids))]
    fields += [(a + 0x32, with_level(t, g)) for a, _r, g, t in grants]
    return encode_dir(b"", fields)


def plan(rid, body, undo, caps, names):
    prefix, fields = decode_dir(body, top=True)
    if encode_dir(prefix, fields) != body:
        raise SystemExit(f"[ERR] record {rid} does not rebuild byte for byte")
    F = dict(fields)
    grants, capped = plan_grants(F, caps)
    name = pfs.name_of(pfs.parse_dir(body, top=True), "unitres.pfs").strip()
    who = f"{rid:4d} {name:<24}"
    note = "  (capped: %s)" % ", ".join("%s %d" % (names[a], c) for a, c in capped) if capped else ""
    cur = F.get(G.ALWAYS_TAG)
    if (OPT1 in F) != (OPT2 in F) or (OPT1 in F) != (OPT3 in F):
        return "error", None, f"{who}  heroic option tags are not all present or all absent"
    if not grants:
        return None if not capped else ("capped", None, who + "  nothing to grant" + note)
    want = always_owner(grants)
    what = ", ".join("%s %d->%d" % (names[a], r, g) for a, r, g, _t in grants)

    if undo:
        if cur != want:
            return "same", None, f"{who}  no Always set of this script's shape"
        bare = (F.get(OPT1) == F.get(OPT2) == F.get(OPT3) == b"\0") and not STAT_TAGS & F.keys()
        drop = {G.ALWAYS_TAG} | ({OPT1, OPT2, OPT3} if bare else set())
        return "ok", encode_dir(prefix, [(t, b) for t, b in fields if t not in drop]), \
            f"{who}  Always removed" + (" with the empty options" if bare else "")

    if cur == want:
        return "same", None, f"{who}  Always already {what}"
    if cur not in (None, b"\0"):
        held = [names.get(a, hex(a)) for a in pfs.abilities_of(pfs.parse_dir(cur, top=False))]
        return "kept", None, f"{who}  Always already authored ({', '.join(held)}), not touched"
    new = list(fields)
    if OPT1 not in F:
        new += [(OPT1, b"\0"), (OPT2, b"\0"), (OPT3, b"\0")]
    new = [(t, b) for t, b in new if t != G.ALWAYS_TAG] + [(G.ALWAYS_TAG, want)]
    return "ok", encode_dir(prefix, new), f"{who}  Always: {what}{note}"


def run(d, undo, caps, names, quiet=False):
    base, ent, bodies = split(d)
    if join(d, base, ent, bodies) != d:
        raise SystemExit("[ERR] the unmodified file does not rebuild byte for byte")
    out, changed, ok = list(bodies), {}, True
    for k, ((rid, *_), body) in enumerate(zip(ent, bodies)):
        p = plan(rid, body, undo, caps, names)
        if p is None:
            continue
        status, new, line = p
        if not quiet:
            print(f"[{status:<6}] {line}")
        ok &= status != "error"
        if new is not None:
            out[k] = new
            changed[rid] = new
    return ok, changed, join(d, base, ent, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write Unitres.pfs (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="remove the Always sets this script wrote")
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(GAME, "AoWzEd.exe")):
        raise SystemExit(f"[ERR] {GAME} is not the Ziggurat folder")
    caps, names = ability_names.levels(), ability_names.names()
    d = open(TARGET, "rb").read()
    ok, changed, out = run(d, a.undo, caps, names)
    if not ok:
        raise SystemExit(1)
    if not changed:
        print("[i     ] nothing to do -- already in the target state")
        return
    _, ent0, before = split(d)
    _, ent1, after = split(out)
    assert [e[0] for e in ent0] == [e[0] for e in ent1]
    for (rid, *_), b0, b1 in zip(ent0, before, after):
        assert b1 == changed.get(rid, b0), f"record {rid} is not what was planned"
        if rid in changed and not a.undo:
            f = pfs.parse_dir(pfs.parse_dir(b1, top=True)[G.ALWAYS_TAG], top=False)
            assert pfs.abilities_of(f), f"record {rid}: the Always set reads back empty"
    ok2, again, _ = run(out, a.undo, caps, names, quiet=True)
    assert ok2 and not again, "a second pass would change the file again"
    print(f"[i     ] {len(changed)} unit types, file {len(d)} -> {len(out)} B")
    if a.apply:
        with open(TARGET, "wb") as f:
            f.write(out)
        print(f"[i     ] wrote {TARGET}")
    else:
        print("[i     ] dry run -- re-run with --apply to write")


if __name__ == "__main__":
    main()
