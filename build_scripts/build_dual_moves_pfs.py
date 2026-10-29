#!/usr/bin/env python
r"""
build_dual_moves_pfs.py -- four vanilla spells leave their single-sphere tiers for dual tiers, as they
are (owner, 2026-10-29: "They're just being reassigned"):
    Healing Showers (spell 73, record 83)    Water tier 1 -> Life/Water tier 1
    Ooze            (spell 124, record 134)  Water tier 1 -> Earth/Water tier 1
    Disease Cloud   (spell 104, record 114)  Death tier 2 -> Death/Air tier 2
    Pestilence      (spell 9, record 19)     Death tier 3 -> Death/Air tier 3
Dual-sphere groundwork: build_dual_sphere.py (their TABLE rows and MOVED rows).  Icons 175-178:
build_dual_spell_icons.py.  Entangle's move (build_entangle_dual_pfs.py) is the template.

    python build_scripts/build_dual_moves_pfs.py            dry run + state
    python build_scripts/build_dual_moves_pfs.py --apply     the dual values
    python build_scripts/build_dual_moves_pfs.py --undo      back to the single-sphere tiers

Each record's sphere (tag 0x10), tier (0x11) and research (0x0F) override the class constructor's on
load: sphere -> 7 (dual), the tier kept, research -> the dual tier's figure (80 / 160 / 240, the
single tier N+1 price; dual spells are granted, never researched, so it only prices Wizard's Tower
offers); the book icon -> the vanilla glyph on the pair's glow.  Mana, behaviour and every other field
stay.  Splice machinery is build_embrittle_pfs.py's: each record is rewritten in place from its own
re-serialised fields (they round-trip byte-identically), the CRC is repaired and every other record
is proved byte-identical.
"""
import importlib.util, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, alias):
    spec = importlib.util.spec_from_file_location(alias, os.path.join(HERE, name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = _load("build_embrittle_pfs.py", "_emb")
DF = _load("build_deathfire_pfs.py", "_df")
from aowepack_patch import kill_aow                          # noqa: E402

DUAL = 7
# record: (name, description start, (sphere, tier, research, icon) vanilla, the same as dual)
MOVES = {
    83: ("Healing Showers", b"Restores the vigor in both units and lands", (6, 1, 40, 106), (DUAL, 1, 80, 175)),
    134: ("Ooze", b"Turns a battlefield area to sticky mud", (6, 1, 20, 108), (DUAL, 1, 80, 176)),
    114: ("Disease Cloud", b"Envelopes the target area in a deadly cloud", (2, 2, 80, 32), (DUAL, 2, 160, 177)),
    19: ("Pestilence", b"Spews forth a cloud of pestilence", (2, 3, 160, 22), (DUAL, 3, 240, 178)),
}


def icon_of(f):
    return DF.seq_parse(f[DF.TAG_IMG])[10]["f20"]


def values(f):
    return (f[E.TAG_SPHERE][0], f[E.TAG_TIER][0], struct.unpack("<I", f[E.TAG_RESEARCH])[0], icon_of(f))


def put(f, v):
    sph, tier, res, icon = v
    f[E.TAG_SPHERE], f[E.TAG_TIER], f[E.TAG_RESEARCH] = bytes([sph]), bytes([tier]), struct.pack("<I", res)
    slots = DF.seq_parse(f[DF.TAG_IMG])
    assert slots[10] is not None and slots[10]["name"] == E.ICON_PATH and slots[10]["kind"] == 0
    slots[10]["f20"] = icon
    f[DF.TAG_IMG] = DF.seq_build(slots)


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    d = E.read(E.SPELLS)
    if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
        sys.exit("ABORT: Spells.pfs CRC residue already wrong")
    base, _ent, _ws, span = E.records(d)
    todo = {}
    for rec, (name, start, van, dual) in MOVES.items():
        body = E.body_of(d, base, span, rec)
        f = DF.fields(body)
        if not f.get(E.TAG_DESC, b"")[4:].startswith(start):
            sys.exit("ABORT: record %d is not %s's" % (rec, name))
        if E.reserialise(f) != body:
            sys.exit("ABORT: record %d does not round-trip; refusing to rewrite it" % rec)
        v = values(f)
        st = "dual (installed)" if v == dual else "single sphere (original)" if v == van else None
        print("  Spells.pfs record %d (%s): %s" % (rec, name, st or "FOREIGN values %r" % (v,)))
        if st is None:
            sys.exit("ABORT: unexpected sphere / tier / research / icon")
        want = dual if apply_ else van
        if (apply_ or undo) and v != want:
            put(f, want)
            todo[rec] = E.reserialise(f)
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply for the dual values, --undo for the old tiers)")
        return
    if not todo:
        print("    nothing to do")
        return
    out = bytearray(d)
    for rec, new_body in todo.items():
        out = E.remove(out, rec)
        _b, _e, _w, sp = E.records(out)
        donor = min(i for i in sp)
        out = E.insert(out, rec, donor, lambda _donor_body, nb=new_body: nb)[0]
    E.fix_crc(out)
    for rec in todo:
        problem = E.audit(d, out, rec, expect_present=True) if len(todo) == 1 else None
        if problem:
            sys.exit("ABORT: audit failed -- %s (nothing written)" % problem)
    b2, _e2, _w2, sp2 = E.records(out)
    if sorted(sp2) != sorted(span):
        sys.exit("ABORT: the record set changed (nothing written)")
    for rec in span:
        want = todo.get(rec, E.body_of(d, base, span, rec))
        if E.body_of(out, b2, sp2, rec) != want:
            sys.exit("ABORT: record %d came out wrong (nothing written)" % rec)
    if len(out) != len(d):
        sys.exit("ABORT: the file length changed (nothing written)")
    if (E.zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
        sys.exit("ABORT: the CRC repair did not take (nothing written)")
    kill_aow()
    open(E.SPELLS, "wb").write(out)
    print("    WRITTEN (%d record%s, CRC repaired)" % (len(todo), "" if len(todo) == 1 else "s"))


if __name__ == "__main__":
    main()
