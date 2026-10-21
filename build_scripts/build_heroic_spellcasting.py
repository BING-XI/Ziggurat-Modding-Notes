#!/usr/bin/env python3
r"""
build_heroic_spellcasting.py -- every unit type with Spell Casting gets heroic option 1 = Spell
Casting one level above its own.  Data only: Ziggurat/Release/Unitres.pfs.  Owner's rule 2026-10-20.

    python build_scripts/build_heroic_spellcasting.py              dry run
    python build_scripts/build_heroic_spellcasting.py --apply
    python build_scripts/build_heroic_spellcasting.py --undo [--apply]

"Its own" level is the highest Spell Casting level across the type's base and medal owners (tags
0x19, 0x20, 0x1E, 0x1F); today every one sits on the base.  The option is the bundle AoWzEd writes
for a lone multi-level ability -- OPTION_L3 is the Charlatan's option 1 exactly as the owner
authored it -- with no stat deltas.  The grant is UpdateDefaultAbilities, which raises a level when
the option's is higher (build_heroicchoice.py), so base + 1 takes effect.

Left alone, and reported:
    a type already at the live cap (ability_names.levels(), 5 today) -- there is no level 6;
    a type whose option 1 already holds anything else -- the owner's own authoring;
    the Charlatan (record 5), the owner's own; --undo never touches it, and --apply fills it only
    when empty (its rule value, SC 3, is the owner's choice -- restored this way 2026-10-20 after
    an editor save wiped every option; cause in build_heroicchoice_data.py, LOAD_MASK).

Writing: a type without heroic options gets tags 0x21..0x23 appended, options 2 and 3 as the one
`00` byte the engine writes for an empty owner; an empty option 1 is replaced in place.  --undo
empties an option 1 that is a Spell-Casting-only bundle of this shape, and drops 0x21..0x23 when no
other heroic data remains, which restores the original bytes.  It cannot tell such a bundle from
an identical one the owner authored in the editor.

AoWzEd rewrites Unitres.pfs whole on save, so nothing here is positional: the index and every record
directory are re-derived each run, and the unmodified file must rebuild byte for byte before
anything is written.  CRC residue as in build_pfs_typos.py.
"""
import argparse, os, struct, sys, zlib
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(GAME, "Release", "Unitres.pfs")
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
import pfs, ability_names
from build_pfs_typos import index_layout, PFS_RESIDUE
import heroicchoice as G

SC = 0x34                                   # Spell Casting
RANK_OWNERS = (0x19, 0x20, 0x1E, 0x1F)      # base, copper, silver, gold
OPT1, OPT2, OPT3 = G.OWNER_TAGS
STAT_TAGS = {G.stat_tag(k, i) for k in range(3) for i in range(G.NSTATS)}
OWNER_AUTHORED = {5}                        # Human Charlatan
MULTILEVEL_DATA = 0x00022001                # TMultiLevelAbilityData class id
OPTION_L3 = bytes.fromhex("0402000304310b6617" "35000000" "00000000000010"
                          "000000000100000034000000" "01200200020a000b01033400")


# ------------------------------------------------------------------------------------------------
# directory <-> [(tag, bytes)] in directory order
# ------------------------------------------------------------------------------------------------
def decode_dir(body, top):
    p = 4 if top else 0
    n = body[p]; p += 1
    small, wide = n & 0x7F, 0
    if n & 0x80:
        wide = struct.unpack_from("<I", body, p)[0]; p += 4
    ent = []
    for _ in range(small):
        ent.append((body[p], body[p + 1])); p += 2
    for _ in range(wide):
        ent.append(struct.unpack_from("<II", body, p)); p += 8
    if [o for _, o in ent] != sorted(o for _, o in ent):
        raise ValueError("directory order is not payload order")
    ends = [o for _, o in ent[1:]] + [len(body) - p]
    return body[:4 if top else 0], [(t, body[p + o:p + e]) for (t, o), e in zip(ent, ends)]


def encode_dir(prefix, fields):
    small, wide, off = [], [], 0
    for t, b in fields:
        if not wide and t <= 0xFF and off <= 0xFF:
            small.append(bytes([t, off]))
        else:
            wide.append(struct.pack("<II", t, off))
        off += len(b)
    head = bytes([len(small) | (0x80 if wide else 0)])
    if wide:
        head += struct.pack("<I", len(wide))
    return prefix + head + b"".join(small) + b"".join(wide) + b"".join(b for _, b in fields)


def option(level):
    count = SC + 1
    bitset = bytearray((count + 7) // 8)
    bitset[SC // 8] |= 1 << (SC % 8)
    data = encode_dir(struct.pack("<I", MULTILEVEL_DATA),
                      [(0x0A, bytes([level])), (0x0B, struct.pack("<H", SC))])
    return encode_dir(b"", [(2, struct.pack("<I", count)), (3, bytes(bitset)),
                            (0x31, struct.pack("<III", 0, 1, SC)), (SC + 0x32, data)])


assert option(3) == OPTION_L3, "option() no longer matches the editor's bundle"


def sc_level(owner):
    """Spell Casting level an owner grants, or None."""
    f = pfs.parse_dir(owner, top=False)
    if SC not in pfs.abilities_of(f) or SC + 0x32 not in f:
        return None
    return pfs.parse_dir(f[SC + 0x32], top=True)[0x0A][0]


# ------------------------------------------------------------------------------------------------
# file <-> record bodies
# ------------------------------------------------------------------------------------------------
def split(d):
    if zlib.crc32(d[4:]) & 0xFFFFFFFF != PFS_RESIDUE:
        raise SystemExit("[ERR] CRC residue is wrong before any edit -- refusing to rewrite")
    base, ent = index_layout(d)
    if [e[0] for e in ent] != [r for r, _ in pfs.parse_index(d)]:
        raise SystemExit("[ERR] index entry ids disagree with parse_index")
    offs = [e[1] for e in ent] + [len(d) - 4 - base]
    return base, ent, [d[base + a:base + b] for a, b in zip(offs, offs[1:])]


def join(d, base, ent, bodies):
    out = bytearray(d[:base + ent[0][1]])
    off = ent[0][1]
    for (_rid, _o, pos, w), body in zip(ent, bodies):
        if w == 1:
            if off > 0xFF:
                raise SystemExit("[ERR] an index small-entry offset would overflow u8")
            out[pos] = off
        else:
            struct.pack_into("<I", out, pos, off)
        out += body
        off += len(body)
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE
    return bytes(out)


# ------------------------------------------------------------------------------------------------
def plan(rid, body, undo, cap):
    """(status, new_body or None, line) or None for a type without Spell Casting."""
    prefix, fields = decode_dir(body, top=True)
    if encode_dir(prefix, fields) != body:
        raise SystemExit(f"[ERR] record {rid} does not rebuild byte for byte")
    F = dict(fields)
    levels = [sc_level(F[t]) for t in RANK_OWNERS if t in F]
    levels = [lv for lv in levels if lv is not None]
    if not levels:
        return None
    level = max(levels)
    name = pfs.name_of(pfs.parse_dir(body, top=True), "unitres.pfs").strip()
    who = f"{rid:4d} {name:<24} SC {level}"
    cur = F.get(OPT1)
    if (OPT1 in F) != (OPT2 in F) or (OPT1 in F) != (OPT3 in F):
        return "error", None, f"{who}  heroic owner tags are not all present or all absent"

    def rebuilt(new):
        return encode_dir(prefix, new)

    if rid in OWNER_AUTHORED and (undo or cur not in (None, b"\0")):
        lv = sc_level(cur) if cur not in (None, b"\0") else None
        return "kept", None, f"{who}  owner-authored option 1 (SC {lv}), not touched"

    if undo:
        if cur not in {option(lv) for lv in range(1, cap + 1)}:
            return "same", None, f"{who}  no Spell Casting option 1 of this script's shape"
        bare = F[OPT2] == F[OPT3] == b"\0" and not STAT_TAGS & F.keys()
        new = ([(t, b) for t, b in fields if t not in (OPT1, OPT2, OPT3)] if bare else
               [(t, b"\0" if t == OPT1 else b) for t, b in fields])
        return "ok", rebuilt(new), f"{who}  option 1 SC {sc_level(cur)} -> " + (
            "removed with the empty heroic tags" if bare else "empty")

    if level >= cap:
        return "capped", None, f"{who}  already at the cap {cap}: option 1 left empty"
    want = option(level + 1)
    if cur == want:
        return "same", None, f"{who}  option 1 already SC {level + 1}"
    if cur is None:
        if STAT_TAGS & F.keys():
            return "error", None, f"{who}  stat deltas without option owners"
        new = fields + [(OPT1, want), (OPT2, b"\0"), (OPT3, b"\0")]
    elif cur == b"\0":
        new = [(t, want if t == OPT1 else b) for t, b in fields]
    else:
        held = [hex(a) for a in pfs.abilities_of(pfs.parse_dir(cur, top=False))]
        return "kept", None, f"{who}  option 1 already authored ({', '.join(held)}), not touched"
    return "ok", rebuilt(new), f"{who}  option 1 -> SC {level + 1}"


def run(d, undo, cap, quiet=False):
    base, ent, bodies = split(d)
    if join(d, base, ent, bodies) != d:
        raise SystemExit("[ERR] the unmodified file does not rebuild byte for byte")
    out, changed, ok = list(bodies), {}, True
    for k, ((rid, *_), body) in enumerate(zip(ent, bodies)):
        p = plan(rid, body, undo, cap)
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
    ap.add_argument("--undo", action="store_true", help="remove the Spell Casting options")
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(GAME, "AoWzEd.exe")):
        raise SystemExit(f"[ERR] {GAME} is not the Ziggurat folder")
    cap = ability_names.levels()[SC]
    d = open(TARGET, "rb").read()
    ok, changed, out = run(d, a.undo, cap)
    if not ok:
        raise SystemExit(1)
    if not changed:
        print("[i     ] nothing to do -- already in the target state")
        return

    # verify: only the planned records moved, each reads back through pfs.py, a second pass is a no-op
    _, ent0, before = split(d)
    _, ent1, after = split(out)
    assert [e[0] for e in ent0] == [e[0] for e in ent1]
    for (rid, *_), b0, b1 in zip(ent0, before, after):
        assert b1 == changed.get(rid, b0), f"record {rid} is not what was planned"
        if rid in changed:
            opt = pfs.parse_dir(b1, top=True).get(OPT1)
            assert (opt in (None, b"\0")) if a.undo else sc_level(opt) is not None
    ok2, again, _ = run(out, a.undo, cap, quiet=True)
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
