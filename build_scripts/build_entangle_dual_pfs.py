#!/usr/bin/env python
r"""
build_entangle_dual_pfs.py -- Entangle (spell 111, Spells.pfs record 121) leaves Earth tier 2 for the
Life/Earth dual tier 1 (owner, 2026-10-26: "as present" -- its behaviour and numbers stay).
Dual-sphere groundwork: build_dual_sphere.py (its TABLE row (111, LIFE, EARTH)).

    python build_scripts/build_entangle_dual_pfs.py            dry run + state
    python build_scripts/build_entangle_dual_pfs.py --apply     the dual values
    python build_scripts/build_entangle_dual_pfs.py --undo      back to Earth tier 2

The record's sphere (tag 0x10), tier (0x11) and research (0x0F) override TEntangle.Create's on load,
as every Ziggurat tier move does: sphere 3 -> 7 (dual), tier 2 -> 1, research 40 -> 80 (the dual
tier-1 figure; dual spells are granted, never researched, so it only prices Wizard's Tower offers),
and its book icon 53 -> 167 (its own glyph on the Life/Earth glow).  Everything else is untouched.  Curse of Lethe is a separate TEntangle instance with
its own record (96); it is unaffected.

Splice machinery is build_embrittle_pfs.py's: the record is rewritten in place (removed, then
re-inserted from its own re-serialised fields; the record round-trips byte-identically), the CRC is
repaired and every other record is proved byte-identical.
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

REC = 111 + 10
DESC_START = b"Attempts to ensnare a target"
EARTH_T2 = {E.TAG_SPHERE: b"\x03", E.TAG_TIER: b"\x02", E.TAG_RESEARCH: struct.pack("<I", 40)}
DUAL_T1 = {E.TAG_SPHERE: b"\x07", E.TAG_TIER: b"\x01", E.TAG_RESEARCH: struct.pack("<I", 80)}
ICON_EARTH, ICON_DUAL = 53, 167          # vanilla's icon; its glyph on the Life/Earth glow (build_dual_spell_icons.py)


def icon_of(f):
    return DF.seq_parse(f[DF.TAG_IMG])[10]["f20"]


def set_icon(f, iid):
    slots = DF.seq_parse(f[DF.TAG_IMG])
    assert slots[10] is not None and slots[10]["name"] == E.ICON_PATH and slots[10]["kind"] == 0
    slots[10]["f20"] = iid
    f[DF.TAG_IMG] = DF.seq_build(slots)


def state_of(f):
    for name, vals, icon in (("dual (installed)", DUAL_T1, ICON_DUAL), ("Earth tier 2 (original)", EARTH_T2, ICON_EARTH),
                             ("dual, Earth icon (re-tune)", DUAL_T1, ICON_EARTH)):
        if all(f.get(t) == v for t, v in vals.items()) and icon_of(f) == icon:
            return name
    return None


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    d = E.read(E.SPELLS)
    if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
        sys.exit("ABORT: Spells.pfs CRC residue already wrong")
    base, _ent, _ws, span = E.records(d)
    body = E.body_of(d, base, span, REC)
    f = DF.fields(body)
    if not f.get(E.TAG_DESC, b"")[4:].startswith(DESC_START):
        sys.exit("ABORT: record %d is not Entangle's" % REC)
    if E.reserialise(f) != body:
        sys.exit("ABORT: record %d does not round-trip; refusing to rewrite it" % REC)
    st = state_of(f)
    print("  Spells.pfs record %d (Entangle): %s" % (REC, st or "FOREIGN values %r" % {
        t: f.get(t).hex() for t in DUAL_T1}))
    if st is None:
        sys.exit("ABORT: unexpected sphere / tier / research")
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply for the dual values, --undo for Earth tier 2)")
        return
    want = DUAL_T1 if apply_ else EARTH_T2
    if (apply_ and st == "dual (installed)") or (undo and st.startswith("Earth")):
        print("    nothing to do")
        return
    f.update(want)
    set_icon(f, ICON_DUAL if apply_ else ICON_EARTH)
    new_body = E.reserialise(f)
    out = E.remove(bytearray(d), REC)
    donor = min(i for i in span if i != REC)
    out = E.insert(out, REC, donor, lambda _donor_body: new_body)[0]
    E.fix_crc(out)
    problem = E.audit(d, out, REC, expect_present=True)
    if problem:
        sys.exit("ABORT: audit failed -- %s (nothing written)" % problem)
    b2, _e2, _w2, sp2 = E.records(out)
    assert E.body_of(out, b2, sp2, REC) == new_body
    kill_aow()
    open(E.SPELLS, "wb").write(out)
    print("    WRITTEN (%s, CRC repaired)" % ("Life/Earth dual tier 1" if apply_ else "Earth tier 2"))


if __name__ == "__main__":
    main()
