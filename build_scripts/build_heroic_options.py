#!/usr/bin/env python3
r"""
build_heroic_options.py -- heroic options for unit types whose option slots are empty.  Data only:
Ziggurat/Release/Unitres.pfs.  Owner's request 2026-10-21 ("fill out the empty level up choices
for human units at the heroic level"); OPTIONS below is the design, one row per unit type.

    python build_scripts/build_heroic_options.py              dry run (prints every option)
    python build_scripts/build_heroic_options.py --apply
    python build_scripts/build_heroic_options.py --undo [--apply]

An option is one ability owner (at most heroicchoice.MAX_ABILITIES distinct abilities; a levelled
one carries its level) plus six signed stat deltas in heroicchoice.STAT_FIELDS order.  The owner is
built the way the engine writes one: tag 2 = highest id + 1, tag 3 the bitset, tag 0x31 the id
list (ascending) and per levelled ability a TMultiLevelAbilityData record (Marksmanship, Vision;
the families this table uses).  A delta is a one-byte tag 0x24 + 6*k + i, written only when non-zero.

A slot is filled only when it is EMPTY -- owner absent or `00`, and none of its six deltas set -- so
the owner's own options and build_heroic_spellcasting.py's Spell Casting option 1 stay as they are,
and a row whose slot is already taken is reported and skipped.  A levelled ability must exceed the
highest level the type reaches on its ranks and in its Always set, and a single-level one must not
be held on those owners already: both are checked, so an option never grants nothing.

The heroic tail of a changed record is written in the editor's order: 0x21, 0x22, 0x23, the non-zero
delta tags ascending, 0x36.  --undo empties every slot that still equals this script's row and drops
0x21..0x23 when no other heroic data remains (no deltas, no Always set), which restores the
original bytes.  It cannot tell such a slot from an identical one authored in the editor.

Shares build_heroic_spellcasting.py's whole-file rebuild (the editor rewrites Unitres.pfs whole on
save): the index and every directory are re-derived each run, and the unmodified file must rebuild
byte for byte before anything is written.
"""
import argparse, os, struct, sys
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
import pfs, ability_names
import heroicchoice as G
from build_heroic_spellcasting import TARGET, GAME, decode_dir, encode_dir, split, join

MULTILEVEL_DATA = 0x00022001
RANKS = (0x19, 0x20, 0x1E, 0x1F)                 # base, Copper, Silver, Gold
HEROIC_TAGS = set(G.OWNER_TAGS) | {G.stat_tag(k, i) for k in range(3) for i in range(G.NSTATS)} \
    | {G.ALWAYS_TAG}
STAT = {n: i for i, n in enumerate(G.STAT_FIELDS)}

# (record id, name) -> [(option slot 1..3, [ability or (ability, level)], {stat: delta})]
OPTIONS = {
    (10, "Human Archer"): [
        (1, ["Forestry", "Concealment"], {"Moves": 2}),
        (2, [("Marksmanship", 5), "Night Vision"], {}),
        (3, ["Monster Slaying", "Fearless"], {}),
    ],
    (4, "Human Pikeman"): [
        (1, ["Monster Slaying"], {"Hits": 2}),
        (2, ["Parry"], {"Defense": 2}),
        (3, ["Drillmaster", "Fearless"], {}),
    ],
    (3, "Human Man-at-Arms"): [
        (1, ["Razor Plate"], {"Defense": 1}),
        (2, ["Fearless"], {"Hits": 4}),
        (3, ["True Seeing", "Night Vision"], {"Resistance": 1}),
    ],
    (2, "Human Lancer"): [
        (1, [("Vision", 4)], {"Moves": 4}),
        (2, ["Throw Javelin"], {"Moves": 2}),
        (3, ["Parry"], {"Defense": 2, "Moves": -2}),
    ],
    (9, "Human Zweihander"): [
        (1, [], {"Defense": 2, "Hits": 4}),
        (2, ["Magebane", "True Seeing"], {"Resistance": 1}),
        (3, ["Charge"], {"Attack": 2, "Defense": -2}),
    ],
    (1, "Human Priest"): [
        (2, ["Holy Champion", "Death Protection"], {}),
        (3, ["Bard's Skills"], {"Hits": 2, "Resistance": 2}),
    ],
    (6, "Human Cavalier"): [
        (2, ["Holy Champion", "Healing"], {}),
        (3, ["Monster Slaying", "Lightning Protection"], {}),
    ],
    (8, "Human Musketeer"): [
        (1, [("Marksmanship", 7), "Night Vision"], {}),
        (2, [], {"Hits": 2, "Moves": 6}),
        (3, ["Shield", "Parry"], {}),
    ],
}

_BY_NAME = {}
for _a, _n in ability_names.names().items():
    _BY_NAME.setdefault(_n, []).append(_a)


def ability_id(name):
    ids = _BY_NAME.get(name, [])
    assert len(ids) == 1, "ability name %r resolves to %r" % (name, ids)
    return ids[0]


def normalise(abilities):
    """[(id, level or None)] ascending by id."""
    out = [(ability_id(a), None) if isinstance(a, str) else (ability_id(a[0]), a[1]) for a in abilities]
    return sorted(out)


def owner_bytes(abilities):
    if not abilities:
        return b"\0"
    ids = [a for a, _ in abilities]
    count = max(ids) + 1
    bitset = bytearray((count + 7) // 8)
    for a in ids:
        bitset[a // 8] |= 1 << (a % 8)
    fields = [(2, struct.pack("<I", count)), (3, bytes(bitset))]
    levelled = [(a, lv) for a, lv in abilities if lv is not None]
    if levelled:
        fields.append((0x31, struct.pack("<II", 0, len(levelled)) +
                       b"".join(struct.pack("<I", a) for a, _ in levelled)))
        for a, lv in levelled:
            fields.append((a + 0x32, encode_dir(struct.pack("<I", MULTILEVEL_DATA),
                                                [(0x0A, bytes([lv])), (0x0B, struct.pack("<H", a))])))
    return encode_dir(b"", fields)


def held(F):
    """{ability id: highest level (0 for single-level)} over the ranks and the Always set."""
    out = {}
    for tag in RANKS + (G.ALWAYS_TAG,):
        if F.get(tag) in (None, b"\0"):
            continue
        f = pfs.parse_dir(F[tag], top=False)
        for a in pfs.abilities_of(f):
            lv = 0
            if a + 0x32 in f:
                rec = pfs.parse_dir(f[a + 0x32], top=True)
                if struct.unpack_from("<I", f[a + 0x32])[0] == MULTILEVEL_DATA and 0x0A in rec:
                    lv = rec[0x0A][0]
            out[a] = max(out.get(a, 0), lv)
    return out


def slot_empty(F, k):
    return F.get(G.OWNER_TAGS[k]) in (None, b"\0") and not any(
        F.get(G.stat_tag(k, i), b"\0") != b"\0" for i in range(G.NSTATS))


def slot_is(F, k, owner, deltas):
    return F.get(G.OWNER_TAGS[k]) == owner and all(
        F.get(G.stat_tag(k, i), b"\0") == struct.pack("<b", deltas.get(i, 0)) for i in range(G.NSTATS))


def describe(abilities, deltas, names):
    a = ", ".join(names[x] + ("" if lv is None else " %d" % lv) for x, lv in abilities) or "-"
    d = " ".join("%s %+d" % (G.STAT_FIELDS[i], v) for i, v in sorted(deltas.items()))
    return a + ("   " + d if d else "")


def plan(rid, body, undo, caps, names):
    prefix, fields = decode_dir(body, top=True)
    if encode_dir(prefix, fields) != body:
        raise SystemExit(f"[ERR] record {rid} does not rebuild byte for byte")
    F = dict(fields)
    name = pfs.name_of(pfs.parse_dir(body, top=True), "unitres.pfs").strip()
    rows = OPTIONS.get((rid, name))
    if rows is None:
        if any(r == rid for r, _ in OPTIONS):
            raise SystemExit(f"[ERR] record {rid} is {name!r}, not the type OPTIONS names")
        return None, []
    have = held(F)
    lines, newF = [], dict(F)
    for slot, abil, stats in rows:
        k = slot - 1
        abilities = normalise(abil)
        deltas = {STAT[s]: v for s, v in stats.items() if v}
        assert len(abilities) <= G.MAX_ABILITIES and all(
            G.DELTA_MIN <= v <= G.DELTA_MAX for v in deltas.values()), (name, slot)
        for a, lv in abilities:
            if lv is None:
                assert a not in have, f"{name} option {slot}: already holds {names[a]}"
            else:
                assert lv > have.get(a, 0) and lv <= caps.get(a, lv), \
                    f"{name} option {slot}: {names[a]} {lv} vs held {have.get(a, 0)}, cap {caps.get(a)}"
        owner = owner_bytes(abilities)
        text = describe(abilities, deltas, names)
        if undo:
            if slot_is(F, k, owner, deltas):
                newF[G.OWNER_TAGS[k]] = b"\0"
                for i in range(G.NSTATS):
                    newF.pop(G.stat_tag(k, i), None)
                lines.append(("ok", f"option {slot} emptied ({text})"))
            else:
                lines.append(("same", f"option {slot} is not this script's ({text})"))
        elif slot_is(F, k, owner, deltas):
            lines.append(("same", f"option {slot} already {text}"))
        elif slot_empty(F, k):
            newF[G.OWNER_TAGS[k]] = owner
            for i in range(G.NSTATS):
                newF.pop(G.stat_tag(k, i), None)
                if deltas.get(i):
                    newF[G.stat_tag(k, i)] = struct.pack("<b", deltas[i])
            lines.append(("ok", f"option {slot} -> {text}"))
        else:
            lines.append(("kept", f"option {slot} already authored, not touched"))
    if newF == F:
        return None, [(st, f"{rid:4d} {name:<20} {ln}") for st, ln in lines]
    # rebuild the heroic tail in the editor's order
    for t in G.OWNER_TAGS:
        newF.setdefault(t, b"\0")
    bare = (all(newF[t] == b"\0" for t in G.OWNER_TAGS) and G.ALWAYS_TAG not in newF
            and not any(G.stat_tag(k, i) in newF for k in range(3) for i in range(G.NSTATS)))
    head = [(t, b) for t, b in fields if t not in HEROIC_TAGS]
    tail = [] if bare else [(t, newF[t]) for t in G.OWNER_TAGS]
    tail += sorted((t, b) for t, b in newF.items() if t in HEROIC_TAGS and t not in G.OWNER_TAGS
                   and t != G.ALWAYS_TAG)
    if G.ALWAYS_TAG in newF:
        tail.append((G.ALWAYS_TAG, newF[G.ALWAYS_TAG]))
    assert max(t for t, _ in head) < min(G.OWNER_TAGS), f"record {rid}: a tag sorts after 0x21"
    return encode_dir(prefix, head + tail), [(st, f"{rid:4d} {name:<20} {ln}") for st, ln in lines]


def run(d, undo, caps, names, quiet=False):
    base, ent, bodies = split(d)
    if join(d, base, ent, bodies) != d:
        raise SystemExit("[ERR] the unmodified file does not rebuild byte for byte")
    out, changed, seen = list(bodies), {}, set()
    for k, ((rid, *_), body) in enumerate(zip(ent, bodies)):
        new, lines = plan(rid, body, undo, caps, names)
        if lines:
            seen.add(rid)
        for st, ln in lines:
            if not quiet:
                print(f"[{st:<4}] {ln}")
        if new is not None:
            out[k] = new
            changed[rid] = new
    missing = {r for r, _ in OPTIONS} - seen
    if missing:
        raise SystemExit(f"[ERR] OPTIONS names records that are not in the file: {sorted(missing)}")
    return changed, join(d, base, ent, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write Unitres.pfs (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="empty the options this script wrote")
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(GAME, "AoWzEd.exe")):
        raise SystemExit(f"[ERR] {GAME} is not the Ziggurat folder")
    caps, names = ability_names.levels(), ability_names.names()
    d = open(TARGET, "rb").read()
    changed, out = run(d, a.undo, caps, names)
    if not changed:
        print("[i   ] nothing to do -- already in the target state")
        return
    _, ent0, before = split(d)
    _, ent1, after = split(out)
    assert [e[0] for e in ent0] == [e[0] for e in ent1]
    for (rid, *_), b0, b1 in zip(ent0, before, after):
        assert b1 == changed.get(rid, b0), f"record {rid} is not what was planned"
        if rid in changed:
            f = pfs.parse_dir(b1, top=True)
            for t in G.OWNER_TAGS:
                if f.get(t) not in (None, b"\0"):
                    pfs.abilities_of(pfs.parse_dir(f[t], top=False))
    again, _ = run(out, a.undo, caps, names, quiet=True)
    assert not again, "a second pass would change the file again"
    print(f"[i   ] {len(changed)} unit types, file {len(d)} -> {len(out)} B")
    if a.apply:
        with open(TARGET, "wb") as fh:
            fh.write(out)
        print(f"[i   ] wrote {TARGET}")
    else:
        print("[i   ] dry run -- re-run with --apply to write")


if __name__ == "__main__":
    main()
