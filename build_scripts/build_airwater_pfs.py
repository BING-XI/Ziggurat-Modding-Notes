#!/usr/bin/env python
r"""
build_airwater_pfs.py -- the data of the Air/Water dual spells: Spells.pfs records 98 (Mistform,
spell 88), 99 (Mist, 89) and 100 (Static Shield, 90); Ability.pfs records 94 (Mistform, 0x54) and
95 (Static Shield, 0x55).  Code: build_airwater_ench.py, build_staticshield.py, build_mist.py,
build_mist_tc.py.

    python build_scripts/build_airwater_pfs.py            dry run + state
    python build_scripts/build_airwater_pfs.py --apply     write the five records
    python build_scripts/build_airwater_pfs.py --undo      remove them

Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index, CRC repaired, every other
record proved byte-identical); the tag-0x0C parser is build_deathfire_pfs.py's.

SPELLS 98 / 100 = Wind Walking's record 53 (same class, TWindWalking: its cast effect and sound) and
  SPELL 99 = High Prayer's record 112 (its class drives Mist's look), each with the owner's
  description, mana, upkeep, research (the single tier N+1 figure: it prices Wizard's Tower
  offers), sphere 7 (dual), tier, caster family (3 Enchanter for the enchantments, 1 Evoker for
  Mist) and book icon 164 / 165 / 166 (build_dual_spell_icons.py; the owner's picks).  Mist's
  sparkles on the misted units are PARTICLE.ILB's pale glows 15, 16, 17, 16 (were High Prayer's
  yellow 12, 13, 14, 13); its aura slot is never drawn (build_mist_tc.py skips every aura).
ABILITIES 94 / 95 = Wind Walking's enchantment record 175 (tag 9 = 00 00 keeps them out of the
  editor and the level-up offers) with new descriptions.
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

TAG_UPKEEP = 0x0E
WW_SPELL, HP_SPELL, WW_ENCH = 43 + 10, 102 + 10, 0xA5 + 10
SPELLS = [
    dict(rec=98, donor=WW_SPELL, donor_desc=b"Bestows flight", icon=164, mana=12, upkeep=1,
         research=80, tier=1, family=3,
         desc="Grants the unit Floating. The next damage it suffers will cancel the enchantment "
              "instead of wounding it."),
    dict(rec=99, donor=HP_SPELL, donor_desc=b"Blesses all friendly units", icon=165, mana=15,
         upkeep=None, research=160, tier=2, family=1,
         desc="Reduces line of sight in combat by 3 hexes for all enemies lacking True Seeing.",
         sparkles=[15, 16, 17, 16]),
    dict(rec=100, donor=WW_SPELL, donor_desc=b"Bestows flight", icon=166, mana=45, upkeep=5,
         research=240, tier=3, family=3,
         desc="Grants Lightning Immunity. Striking this unit in melee has a chance to inflict "
              "Stunned."),
]
ABILS = [
    dict(rec=0x54 + 10, desc="Mistform: the unit floats. The next damage it suffers ends Mistform "
                             "instead of wounding it."),
    dict(rec=0x55 + 10, desc="Static Shield: Lightning Immunity. A unit that strikes it in melee may "
                             "be stunned."),
]


def spell_builder(sp):
    def build(donor):
        f = DF.fields(donor)
        assert f.get(E.TAG_DESC, b"")[4:].startswith(sp["donor_desc"]), "donor %d moved" % sp["donor"]
        f[E.TAG_DESC] = E.pstr32(sp["desc"])
        f[E.TAG_MANA] = struct.pack("<I", sp["mana"])
        if sp["upkeep"] is not None:
            f[TAG_UPKEEP] = struct.pack("<I", sp["upkeep"])
        f[E.TAG_RESEARCH] = struct.pack("<I", sp["research"])
        f[E.TAG_SPHERE] = bytes([7])
        f[E.TAG_TIER] = bytes([sp["tier"]])
        f[DF.TAG_FAMILY] = bytes([sp["family"]])
        slots = DF.seq_parse(f[DF.TAG_IMG])
        if "sparkles" in sp:
            s = slots[0]
            assert s is not None and s["name"] == b"EFFECTS\\PARTICLE.ILB" and s["kind"] in (4, 5) \
                and s["chain"] is None, "High Prayer's sparkle slot moved"
            s["frames"] = sp["sparkles"]
        icon = slots[10]
        assert icon is not None and icon["name"] == E.ICON_PATH and icon["kind"] == 0, "slot 10 is not the icon"
        icon["f20"] = sp["icon"]
        f[DF.TAG_IMG] = DF.seq_build(slots)
        assert DF.seq_parse(f[DF.TAG_IMG]) == slots
        return E.reserialise(f)
    return build


def abil_builder(ab):
    def build(donor):
        f = DF.fields(donor)
        assert f.get(E.ABIL_TAG_DESC, b"")[4:].startswith(b"Allows the unit to walk upon the wind"), \
            "donor %d is not Wind Walking's enchantment" % WW_ENCH
        assert f.get(9) == b"\x00\x00"
        f[E.ABIL_TAG_DESC] = E.pstr32(ab["desc"])
        return E.reserialise(f)
    return build


TARGETS = ([("Spells.pfs  record %d" % sp["rec"], E.SPELLS, sp["rec"], sp["donor"], spell_builder(sp))
            for sp in SPELLS] +
           [("Ability.pfs record %d" % ab["rec"], E.ABILS, ab["rec"], WW_ENCH, abil_builder(ab))
            for ab in ABILS])


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    for path in (E.SPELLS, E.ABILS):
        d = E.read(path)
        if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
            sys.exit("ABORT: %s CRC residue already wrong" % os.path.basename(path))
        out, changed = bytearray(d), False
        for label, p, rec, donor, builder in TARGETS:
            if p != path:
                continue
            base, _ent, _ws, span = E.records(out)
            want = builder(E.body_of(out, base, span, donor))
            present = rec in span
            match = present and E.body_of(out, base, span, rec) == want
            print("  %s: %s" % (label, "present, matches" if match else "PRESENT, differs" if present else "absent"))
            if not (apply_ or undo) or (apply_ and match) or (undo and not present):
                continue
            before = bytes(out)
            if present:
                out = E.remove(out, rec)
            if apply_:
                out = E.insert(out, rec, donor, builder)[0]
            E.fix_crc(out)
            problem = E.audit(bytearray(before), out, rec, expect_present=apply_)
            if problem:
                sys.exit("ABORT: %s audit failed -- %s (nothing written)" % (label, problem))
            changed = True
        if changed:
            kill_aow()
            open(path, "wb").write(out)
            print("    %s %s (%d -> %d B, CRC repaired)" % ("WRITTEN" if apply_ else "REMOVED",
                                                         os.path.basename(path), len(d), len(out)))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply to write, --undo to remove)")


if __name__ == "__main__":
    main()
