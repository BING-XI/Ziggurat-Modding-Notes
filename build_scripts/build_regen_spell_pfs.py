#!/usr/bin/env python3
r"""
build_regen_spell_pfs.py -- the data half of the Regeneration spell (build_regen_spell.py):
Spells.pfs record 89 (spell 79) and Ability.pfs record 93 (its enchantment, ability 0x53).

    python build_scripts/build_regen_spell_pfs.py            dry run + state
    python build_scripts/build_regen_spell_pfs.py --apply     write both records
    python build_scripts/build_regen_spell_pfs.py --undo      remove both again

Splice machinery is build_embrittle_pfs.py's (records sorted by id, wide index entry inserted,
later offsets shifted, CRC repaired, every other record proved byte-identical), imported.

SPELL RECORD 89 = Stone Skin's record 27 (same class, TStoneSkin, so its cast animation, sounds
and the whole image-sequence skeleton are structurally right) with:
    tag 0x0A  description        tag 0x0C  the SPELLICN.ILB book icon index -> ICON
    tag 0x0D  mana 20            tag 0x0E  upkeep 2
    tag 0x0F  research 40        tag 0x10  sphere 6 (Water)       tag 0x11  tier 1
    tag 0x12  caster family 3 (Enchanter), Stone Skin's own -- kept
Owner's numbers, 2026-10-22.  Once the record exists the data file wins over the cave's pokes.
The cast animation is Stone Skin's (cosmetic; a Water one would be a donor from another class).

ABILITY RECORD 93 = Stone Skin's enchantment record 163 (tag 9 = 00 00: never offered in the
editor, on items or at level-up -- right for a spell enchantment) with only the description.

ICON 129: a dead SpellIcn.ILB entry (cut content, referenced by nothing), repainted as a Water
icon by build_regen_spell_icon.py -- run that first, or the book shows the old purple helmet.
"""
import importlib.util, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_emb", os.path.join(HERE, "build_embrittle_pfs.py"))
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)
from aowepack_patch import kill_aow                          # noqa: E402

SPELL_REC, SPELL_DONOR = 79 + 10, 17 + 10
ABIL_REC, ABIL_DONOR = 0x53 + 10, 0x99 + 10
ICON = 129
MANA, UPKEEP, RESEARCH, SPHERE, TIER = 20, 2, 40, 6, 1
TAG_UPKEEP = 0x0E
SPELL_DESC = "Enchants a unit with regeneration: it fully heals overnight."
ABIL_DESC = "Enchantment lets the unit fully heal overnight."


def build_spell_body(donor):
    ent, dsz = E.T.body_dir(donor)
    f = dict(E.T.slice_fields(donor, ent, dsz))
    assert f.get(E.TAG_SPHERE) == b"\x03" and f.get(E.TAG_TIER) == b"\x02", "donor is not Stone Skin's record"
    f[E.TAG_DESC] = E.pstr32(SPELL_DESC)
    f[E.TAG_MANA] = struct.pack("<I", MANA)
    f[TAG_UPKEEP] = struct.pack("<I", UPKEEP)
    f[E.TAG_RESEARCH] = struct.pack("<I", RESEARCH)
    f[E.TAG_SPHERE] = bytes([SPHERE])
    f[E.TAG_TIER] = bytes([TIER])
    img = bytearray(f[E.TAG_IMG])
    needle = struct.pack("<I", len(E.ICON_PATH)) + E.ICON_PATH
    hits = [i for i in range(len(img) - len(needle)) if img[i:i + len(needle)] == needle]
    assert len(hits) == 1, "expected exactly one %s in tag 0x0C, found %d" % (E.ICON_PATH, len(hits))
    struct.pack_into("<I", img, hits[0] + len(needle) + 3, ICON)
    f[E.TAG_IMG] = bytes(img)
    return E.reserialise(f)


def build_abil_body(donor):
    ent, dsz = E.T.body_dir(donor)
    f = dict(E.T.slice_fields(donor, ent, dsz))
    assert f.get(9) == b"\x00\x00", "donor's tag 9 is %r, expected 00 00 -- wrong donor" % f.get(9)
    f[E.ABIL_TAG_DESC] = E.pstr32(ABIL_DESC)
    return E.reserialise(f)


TARGETS = [
    ("Spells.pfs  record %d" % SPELL_REC, E.SPELLS, SPELL_REC, SPELL_DONOR, build_spell_body),
    ("Ability.pfs record %d" % ABIL_REC, E.ABILS, ABIL_REC, ABIL_DONOR, build_abil_body),
]


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    for label, path, rec, donor, builder in TARGETS:
        d = E.read(path)
        if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
            sys.exit("ABORT: %s CRC residue already wrong" % label)
        base, _ent, _ws, span = E.records(d)
        want = builder(E.body_of(d, base, span, donor))
        present = rec in span
        match = present and E.body_of(d, base, span, rec) == want
        print("  %s: %s" % (label, "present, matches" if match else "PRESENT, differs" if present else "absent"))
        if not (apply_ or undo) or (apply_ and match) or (undo and not present):
            continue
        out = bytearray(d)
        if present:
            out = E.remove(out, rec)
        if apply_:
            out = E.insert(out, rec, donor, builder)[0]
        E.fix_crc(out)
        problem = E.audit(d, out, rec, expect_present=apply_)
        if problem:
            sys.exit("ABORT: %s audit failed -- %s (nothing written)" % (label, problem))
        kill_aow()
        open(path, "wb").write(out)
        print("    %s (%d -> %d B, CRC repaired)" % ("WRITTEN" if apply_ else "REMOVED", len(d), len(out)))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply to write, --undo to remove)")


if __name__ == "__main__":
    main()
