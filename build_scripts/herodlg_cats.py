#!/usr/bin/env python3
"""Category table for the hero level-up dialog columns (shared by build + docs).

The game has NO category concept: `Release/Ability.pfs` has no category tag and the word
"Wayfaring" appears in no game file. This table is therefore a design decision, not a decode.

Ability ids are the `edx` of `TAbilityControl.GetAbility` and are stored at `[ability+0xC]`.
The 100 ids below are exactly the records in `Ability.pfs` that carry tag 6 (the hero level-up
point cost) -- i.e. exactly the abilities the Upgrades list offers. Verified against an in-game
screenshot (Archery 2, Bard's Skills 4, Black Bolts 6, Black Breath 20, Cold Strike 16,
Fire Breath 16, Fire Cannon 28, Charm 16, Doom Gaze 32 ... all name+cost pairs matched).

Any id NOT listed falls into DEFAULT_CAT, so mod-added abilities still show up somewhere rather
than vanishing from the dialog.

⚠ EDITING THIS FILE CHANGES NOTHING ON ITS OWN. The 256-byte table is baked into AoW.exe and
AoWCompat.exe by `build_herodlg_columns.py` (`exe.wr(D["cattbl"], CATS.lookup_table())`). After
any change here, re-run `python build_scripts/build_herodlg_columns.py --apply` -- it rewrites
both executables in lockstep. Skipping it leaves the old table live and the ability lands in
DEFAULT_CAT (Magic) with no error anywhere. (Cost QA a finding on 2026-08-27, for Shield.)

⚠ The 100 vanilla ids are exactly the Ability.pfs records carrying tag 6. Mod-added ids are
listed here as well and need NOT carry tag 6 yet -- but an ability with no tag 6 is
PERMANENTLY FREE at level-up unless its own registration cave stores one into [ability+0x14],
so give it one in AoWDevEd. Mod-added so far:
    176 Shield           -> 2 Melee        (build_shield.py, tag 6 = 8 since 2026-08-27)
    177 Reforming Flesh  -> 1 Resistances  (build_reformingflesh.py; no Ability.pfs record yet,
                                            cost 50 comes from its cave's [+0x14] store)
Still MISSING from this table (they fall into Magic today, which may or may not be wanted):
170 Magebane, 171 Drillmaster, 172-175 the caster-cost abilities. Left alone deliberately --
placing them is the owning feature's call, not this file's.
"""

# Column order = left-to-right in the dialog.
CATEGORIES = ["Wayfaring", "Resistances", "Melee", "Ranged", "Magic"]
DEFAULT_CAT = 4          # unknown / mod-added ability ids land in Magic

# id: (category index, label) -- label is documentation only, the build uses the index.
ABILITY_CATS = {
    # ---- 0 Wayfaring: movement, terrain, concealment, vision (27) ----------------------
    0:   (0, "Walking"),              1:   (0, "Flying"),
    2:   (0, "Swimming"),             3:   (0, "Forestry"),
    4:   (0, "Cave Crawling"),        5:   (0, "Mountaineering"),
    36:  (0, "Wall Climbing"),        39:  (0, "Night Vision"),
    41:  (0, "True Seeing"),           42:  (0, "Tunneling"),
    43:  (0, "Ignition"),           54:  (0, "Invisibility"),
    59:  (0, "Floating"),             64:  (0, "Vision"),
    66:  (0, "Wall Passage"),         68:  (0, "Path Of Decay"),
    69:  (0, "Path Of Life"),      109: (0, "Path Of Frost"),
    125: (0, "Construct/Builder"),
    138: (0, "Steppe Concealment"),   139: (0, "Cave Concealment"),
    140: (0, "Grass Concealment"),    141: (0, "Snow Concealment"),
    142: (0, "Desert Concealment"),   143: (0, "Wasteland Concealment"),
    144: (0, "Water Concealment"),    145: (0, "Concealment"),

    # ---- 1 Resistances: immunities, protections (18: 17 vanilla + Reforming Flesh) -----
    6:   (1, "Magic Immunity"),       7:   (1, "Fire Immunity"),
    8:   (1, "Cold Immunity"),        9:   (1, "Lightning Immunity"),
    10:  (1, "Poison Immunity"),      11:  (1, "Death Immunity"),
    12:  (1, "Holy Immunity"),        13:  (1, "Physical Immunity"),
    67:  (1, "Fearless"),
    70:  (1, "Death Protection"),     71:  (1, "Fire Protection"),
    72:  (1, "Holy Protection"),      73:  (1, "Poison Protection"),
    74:  (1, "Lightning Protection"), 75:  (1, "Magic Protection"),
    76:  (1, "Cold Protection"),      77:  (1, "Physical Protection"),
    # mod-added (build_reformingflesh.py, id 0xB1): +5 HP at the start of every combat round.
    # User-placed in Resistances 2026-08-31 -- it is a survivability passive, not a strike.
    177: (1, "Reforming Flesh"),

    # ---- 2 Melee (21: 20 vanilla + Shield) ----------------------------------------------
    14:  (2, "Fire Strike"),          15:  (2, "Cold Strike"),
    16:  (2, "Lightning Strike"),     17:  (2, "Poison Strike"),
    18:  (2, "Death Strike"),         19:  (2, "Holy Strike"),
    20:  (2, "Magic Strike"),         21:  (2, "Strike"),
    51:  (2, "Cause Fear"),           111: (2, "Charge"),
    112: (2, "Monster Slaying"),      113: (2, "Parry"),
    114: (2, "Round Attack"),         115: (2, "Extra Strike"),
    116: (2, "First Strike"),         117: (2, "Wall Crushing"),
    118: (2, "Lifestealing"),         119: (2, "Entangle Strike"),
    # 146/147 were "Evil Slaying"/"Good Slaying" — that describes the EFFECT, not the name the game
    # shows. Classes are THolyChampionAbility / TUnholyChampionAbility; author-confirmed 2026-08-09.
    146: (2, "Holy Champion"),        147: (2, "Unholy Champion"),
    # mod-added (build_shield.py, id 0xB0): +4 DEF against the front and front-left hexes.
    # Placed beside Parry (113), the vanilla ability it is modelled on.
    176: (2, "Shield"),

    # ---- 3 Ranged: shots, bolts, breaths (20) -------------------------------------------
    22:  (3, "Archery"),              24:  (3, "Hurl Boulder"),
    25:  (3, "Hurl Stones"),          32:  (3, "Marksmanship"),
    44:  (3, "Fire Cannon"),          45:  (3, "Fire Musket"),
    57:  (3, "Shoot Bolt"),        58:  (3, "Throw Javelin"),
    61:  (3, "Poison Darts"),         62:  (3, "Poison Spit"),
    86:  (3, "Fire Breath"),          87:  (3, "Cold Breath"),
    88:  (3, "Black Breath"),         89:  (3, "Divine Breath"),
    90:  (3, "Poison Breath"),
    120: (3, "Black Bolts"),          121: (3, "Magic Bolts"),
    122: (3, "Frost Bolts"),          123: (3, "Lightning Bolts"),
    124: (3, "Holy Bolts"),

    # ---- 4 Magic: spells, mind control, party buffs (16) --------------------------------
    27:  (4, "Web"),                  28:  (4, "Dominate"),
    29:  (4, "Seduce"),               30:  (4, "Flame Throwing"),
    31:  (4, "Call Flames"),          35:  (4, "Invoke Death"),
    37:  (4, "Bard's Skills"),        38:  (4, "Turn Undead"),
    40:  (4, "Entangle"),             46:  (4, "Leadership"),
    47:  (4, "Healing"),              49:  (4, "Regeneration"),
    52:  (4, "Spell Casting"),        55:  (4, "Doom Gaze"),
    106: (4, "Possess"),              148: (4, "Charm"),
}

TABLE_SIZE = 256          # lookup indexed directly by ability id; ids >= this use DEFAULT_CAT


def lookup_table():
    """-> 256 bytes, table[ability_id] = category index."""
    t = bytearray([DEFAULT_CAT]) * TABLE_SIZE
    for aid, (cat, _name) in ABILITY_CATS.items():
        assert 0 <= aid < TABLE_SIZE, "ability id %d out of table range" % aid
        assert 0 <= cat < len(CATEGORIES)
        t[aid] = cat
    return bytes(t)


def counts():
    """-> {category index: how many abilities}."""
    out = dict.fromkeys(range(len(CATEGORIES)), 0)
    for _aid, (cat, _n) in ABILITY_CATS.items():
        out[cat] += 1
    return out


if __name__ == "__main__":
    c = counts()
    print("%d abilities categorised (default for the rest: %s)\n"
          % (len(ABILITY_CATS), CATEGORIES[DEFAULT_CAT]))
    for i, name in enumerate(CATEGORIES):
        print("  %-12s %2d" % (name, c[i]))
    print("\n  %-12s %2d" % ("TOTAL", sum(c.values())))
    print("\nmax column = %d rows" % max(c.values()))
