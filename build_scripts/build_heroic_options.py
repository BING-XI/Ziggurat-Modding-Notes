#!/usr/bin/env python3
r"""
build_heroic_options.py -- heroic options for unit types whose option slots are empty.  Data only:
Ziggurat/Release/Unitres.pfs.  Owner's request 2026-10-21 ("fill out the empty level up choices
for human units at the heroic level"); OPTIONS below is the design, one row per unit type.

NOT APPLIED -- the owner's order (2026-10-22): draft every race here first (done 2026-10-22: all
12 races, the shared war machines and the ships; owner-authored slots are skipped), then he
reviews and I redraft, then --apply, then he fine-tunes in the editor.  PENDING holds the rows
waiting for a proposed ability; the dry run lists them.

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
#
# Owner's design rules (2026-10-21): thick strokes -- each option a stark, skewed direction, not a
# spread of small bonuses.  A stat malus only beside a very strong ability (Physical Protection ->
# fewer Moves for the armour; Flying -> less Defense and Moves); otherwise no negatives.  No
# elemental protections: elemental immunities, Magic Protection and Physical Protection only;
# Magic Immunity rarely; Physical Immunity never.
OPTIONS = {
    (10, "Human Archer"): [
        (1, ["Forestry", "Concealment"], {"Moves": 4}),
        (2, [("Marksmanship", 6), "Night Vision"], {}),
        (3, ["Monster Slaying", "Fearless"], {}),
    ],
    (4, "Human Pikeman"): [
        (1, ["Monster Slaying"], {"Hits": 4}),
        (2, ["Parry"], {"Defense": 3}),
        (3, ["Drillmaster", "Fearless"], {}),
    ],
    (3, "Human Man-at-Arms"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Razor Plate"], {"Defense": 2}),
        (3, ["True Seeing", "Night Vision"], {"Resistance": 2}),
    ],
    (2, "Human Lancer"): [
        (1, [("Vision", 5)], {"Moves": 6}),
        (2, ["Throw Javelin"], {"Moves": 2}),
        (3, ["Physical Protection"], {"Moves": -6}),
    ],
    (9, "Human Zweihander"): [
        (1, [], {"Defense": 2, "Hits": 6}),
        (2, ["Magebane", "Magic Protection"], {}),
        (3, ["Charge"], {"Attack": 2}),
    ],
    (1, "Human Priest"): [
        (2, ["Holy Champion", "Death Immunity"], {}),
        (3, ["Bard's Skills"], {"Resistance": 4}),
    ],
    (6, "Human Cavalier"): [
        (2, ["Holy Champion", "Healing"], {}),
        (3, ["Monster Slaying", "Fire Immunity"], {}),
    ],
    (8, "Human Musketeer"): [
        (1, [("Marksmanship", 8), "Night Vision"], {}),
        (2, [], {"Hits": 2, "Moves": 6}),
        (3, ["Shield", "Parry"], {}),
    ],

    # ---- Frostlings (drafted 2026-10-22) -------------------------------------------------------
    (36, "Frostling Archer"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, [("Marksmanship", 6), "Night Vision"], {}),
    ],
    (45, "Frostling Frakkaman"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, ["Shield"], {"Defense": 2}),
    ],
    (39, "Frostling Swordsman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Strike"], {"Attack": 2}),
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (38, "Frostling Wolf Rider"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Cause Fear"], {"Attack": 2}),
        (3, [("Vision", 4), "True Seeing", "Night Vision"], {}),
    ],
    (47, "Frostling Sherpa"): [
        (1, ["Forestry"], {"Moves": 6}),
        (2, ["Charge"], {"Attack": 2}),
        (3, ["Cold Immunity"], {"Hits": 6}),
    ],
    (40, "Dire Penguin"): [
        (1, ["Charge"], {"Moves": 4}),
        (2, ["Round Attack"], {"Hits": 4}),
        (3, ["Cold Immunity", "Regeneration"], {}),
    ],
    (46, "Frostling Mammoth Rider"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Charge", "Round Attack"], {}),
        (3, ["Cause Fear"], {"Hits": 8}),
    ],
    (41, "Yeti"): [                                  # no ranged attack for a pure melee unit
        (1, ["Cause Fear", "Round Attack"], {}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Rime Aura"], {}),
    ],
    (37, "Frostling Shaman"): [                      # option 1 = Spell Casting 2
        (2, ["Rally"], {"Resistance": 2}),
        (3, ["Dispel Magic", "Magic Protection"], {}),
    ],
    (44, "Frostling Nordic Glow"): [                 # option 1 = Spell Casting 2
        (2, [("Mirror Image", 4)], {}),
        (3, ["Healing", "Rally"], {}),
    ],
    (42, "Frost Queen"): [                           # option 1 = Spell Casting 5; 3 is PENDING
        (2, [("Mirror Image", 6)], {}),
    ],
    (43, "Glacier Drake"): [                         # option 1 = Spell Casting 4
        (2, ["Rime Aura"], {}),
        (3, ["Magic Protection"], {"Hits": 8}),
    ],
    (252, "Frost Blower"): [                         # a shared war machine (ids 246-257)
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, [], {"Hits": 8, "Defense": 2}),
        (3, ["Rime Aura"], {}),
    ],

    # ---- Lizardmen (drafted 2026-10-22) --------------------------------------------------------
    (54, "Lizardman Archer"): [
        (1, ["Extra Shots"], {}),
        (2, [("Marksmanship", 6), "Night Vision"], {}),   # stand-in until Venomous Missiles
        (3, ["Skirmisher"], {"Moves": 4}),
    ],
    (66, "Lizardman Javelineer"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),          # stand-in until Venomous Missiles
        (3, ["Shield"], {"Defense": 2}),
    ],
    (57, "Lizardman Club-Sword"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Round Attack"], {}),
        (3, ["Lifestealing"], {"Attack": 2}),
    ],
    (56, "Lizardman Frog Rider"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Entangle Strike"], {}),
        (3, ["Regeneration"], {"Hits": 4}),
    ],
    (59, "Lurker"): [
        (1, ["Assassin", "First Strike"], {}),
        (2, ["Entangle Strike"], {"Hits": 4}),
        (3, ["Invisibility"], {}),
    ],
    (60, "Giant Slug"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Shots"], {}),
        (3, [], {"Hits": 10, "Defense": 2}),
    ],
    (61, "Swamp Wyvern"): [                          # no breath: a pure melee unit stays melee
        (1, ["Round Attack"], {}),
        (2, ["Lifestealing"], {"Hits": 6}),
        (3, ["Magic Protection"], {"Attack": 2}),
    ],
    (65, "Basilisk"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Mental Discipline", "Magic Protection"], {}),
        (3, ["Regeneration"], {"Hits": 6}),
    ],
    (55, "Lizardman Shaman"): [                      # option 1 = Spell Casting 2
        (2, ["Entangle"], {}),
        (3, ["Rally", "Mental Discipline"], {}),
    ],
    (58, "Salamander"): [                            # option 1 = Spell Casting 3
        (2, ["Searing Aura"], {}),
        (3, ["Fire Breath"], {}),
    ],
    (62, "Turtle Catapult"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -4}),
        (3, [], {"Hits": 8, "Defense": 2}),
    ],
    (63, "Turtle Ballista"): [
        (1, ["Extra Shots"], {}),
        (2, [("Marksmanship", 8)], {}),
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (64, "Turtle Ram"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, [], {"Hits": 8, "Defense": 2}),
    ],

    # ---- Elves (drafted 2026-10-22) ------------------------------------------------------------
    (72, "Elf Longbowman"): [
        (1, ["Extra Shots"], {}),
        (2, [("Marksmanship", 7), "Night Vision"], {}),   # stand-in until Piercing Shots
        (3, ["Skirmisher"], {"Moves": 4}),
    ],
    (74, "Elven Dragoon"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Extra Shots"], {}),
        (3, ["Physical Protection"], {"Moves": -6}),
    ],
    (75, "Elf Longswordsman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Strike"], {"Attack": 2}),
        (3, ["First Strike"], {"Defense": 2}),      # stand-in until Forest Cover
    ],
    (81, "Elf Sergeant"): [
        (1, ["Drillmaster", "Rally"], {}),
        (2, ["Round Attack"], {"Hits": 4}),
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (78, "Elf Ranger"): [
        (1, ["Extra Shots"], {}),
        (2, ["Night Vision", "True Seeing"], {}),   # stand-in until Forest Cover
        (3, ["Assassin", "First Strike"], {}),
    ],
    (76, "Fairy"): [
        (1, [("Mirror Image", 4)], {}),
        (2, ["Healing", "Rally"], {}),
        (3, ["Invisibility"], {}),
    ],
    (77, "Nymph"): [
        (1, ["Charm"], {}),
        (2, [("Mirror Image", 3)], {}),
        (3, ["Regeneration"], {"Hits": 6}),
    ],
    (83, "Ent"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Regeneration"], {"Hits": 8}),
        (3, ["Extra Shots"], {}),
    ],
    (73, "Elf Cleric"): [                            # option 1 = Spell Casting 2
        (2, ["Rally"], {"Resistance": 2}),           # stand-in until Hymn
        (3, ["Mental Discipline", "Death Immunity"], {}),
    ],
    (79, "Unicorn"): [                               # option 1 = Spell Casting 2
        (2, ["Holy Champion"], {"Attack": 2}),
        (3, ["Regeneration"], {"Hits": 6}),
    ],
    (80, "Nature Elemental"): [                      # option 1 = Spell Casting 4
        (2, ["Mental Discipline", "Magic Protection"], {}),
        (3, ["Round Attack"], {"Hits": 8}),
    ],
    (82, "Elf Druidess"): [                          # option 1 = Spell Casting 3
        (2, [("Mirror Image", 4)], {}),
        (3, ["Healing", "Rally"], {}),
    ],

    # ---- Halflings (drafted 2026-10-22) --------------------------------------------------------
    (90, "Halfling Slinger"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, ["Lucky"], {}),
    ],
    (92, "Halfling Pony Rider"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["First Strike"], {"Attack": 2}),
        (3, ["Forestry", "Mountaineering"], {"Moves": 4}),
    ],
    (93, "Halfling Swordsman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Lucky"], {}),
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (94, "Halfling Rogue"): [
        (1, ["Invisibility"], {}),
        (2, ["Extra Shots"], {}),
        (3, ["Lucky"], {}),
    ],
    (95, "Halfling Eagle Rider"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Round Attack"], {"Attack": 2}),
        (3, ["Physical Protection"], {"Moves": -6}),
    ],
    (96, "Satyr"): [
        (1, ["Cause Fear"], {"Attack": 2}),
        (2, ["Seduce"], {}),
        (3, ["Regeneration"], {"Hits": 4}),
    ],
    (98, "Centaur"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Extra Shots"], {}),
        (3, ["Charge"], {"Attack": 2}),             # stand-in until Forest Cover
    ],
    (99, "Halfling Cockatrice Hussar"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Round Attack"], {}),
        (3, ["Magic Protection"], {"Hits": 6}),
    ],
    (91, "Halfling Cleric"): [                       # option 1 = Spell Casting 2
        (2, ["Rally"], {"Resistance": 2}),           # stand-in until Hymn
        (3, ["Lucky"], {}),
    ],
    (97, "Leprechaun"): [                            # option 1 = Spell Casting 3
        (2, ["Lucky"], {}),
        (3, [("Mirror Image", 4)], {}),
    ],
    (101, "Leshy"): [                                # option 1 = Spell Casting 5; race unconfirmed
        (2, ["Round Attack"], {"Hits": 8}),
        (3, [("Mirror Image", 5)], {}),
    ],

    # ---- Dwarves (drafted 2026-10-22) ----------------------------------------------------------
    (108, "Dwarf Archer"): [
        (1, ["Extra Shots"], {}),
        (2, [("Marksmanship", 6), "Night Vision"], {}),   # stand-in until Piercing Shots
        (3, ["Magic Protection"], {"Resistance": 2}),     # stand-in until Spellward
    ],
    (117, "Dwarf Arbalest"): [
        (1, ["Extra Shots"], {}),
        (2, [("Marksmanship", 6), "Night Vision"], {}),   # stand-in until Piercing Shots
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (111, "Dwarf Axeman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Strike"], {"Attack": 2}),
        (3, ["Magic Protection"], {"Defense": 2}),  # stand-in until Spellward
    ],
    (112, "Dwarf Berserker"): [                      # no armour for a berserker
        (1, ["Lifestealing"], {"Attack": 2}),
        (2, ["Regeneration"], {"Hits": 6}),
        (3, ["Extra Strike"], {"Damage": 2}),
    ],
    (110, "Dwarf Boar Rider"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Round Attack"], {"Attack": 2}),
        (3, ["Cause Fear"], {"Hits": 4}),
    ],
    (116, "Dwarf Mole"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Round Attack"], {"Hits": 4}),
        (3, ["Assassin", "First Strike"], {}),
    ],
    (118, "Dwarf Miner"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Strike"], {"Attack": 2}),
        (3, ["Round Attack"], {"Hits": 4}),
    ],
    (113, "Giant"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Round Attack"], {"Hits": 8}),
    ],
    (114, "Dwarven Balloon"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, [], {"Hits": 10, "Defense": 2}),
    ],
    (109, "Dwarf Cleric"): [                         # option 1 = Spell Casting 2
        (2, ["Rally"], {"Resistance": 2}),           # stand-in until Hymn
        (3, ["Mental Discipline", "Magic Protection"], {}),   # stand-in until Spellward
    ],
    (115, "Dwarf First Born"): [                     # option 1 = Spell Casting 4
        (2, ["Magic Immunity"], {}),                # stand-in until Spellward
        (3, ["Round Attack"], {"Hits": 8}),
    ],

    # ---- Highmen (drafted 2026-10-22) ----------------------------------------------------------
    (126, "Highman Archer"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, [("Marksmanship", 6), "Night Vision"], {}),
    ],
    (136, "Highman Chariot"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, [], {"Hits": 8, "Defense": 2}),
    ],
    (128, "Highman Paladin"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Holy Champion"], {"Attack": 2}),
        (3, ["Mental Discipline"], {"Resistance": 4}),   # stand-in until Martyr
    ],
    (129, "Highman Legionary"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Round Attack"], {"Hits": 4}),         # stand-in until Martyr
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (135, "Highman Legionary"): [                    # a second record of the same name
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Round Attack"], {"Hits": 4}),         # stand-in until Martyr
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (130, "Spirit Puppet"): [
        (1, [("Mirror Image", 3)], {}),
        (2, ["Extra Shots"], {}),
        (3, [], {"Hits": 6, "Resistance": 4}),
    ],
    (131, "Titan"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Cause Fear"], {"Hits": 8}),
        (3, ["Mental Discipline", "Magic Protection"], {}),
    ],
    (132, "Valkyrie"): [
        (1, ["Healing", "Rally"], {}),              # stand-in until Martyr
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, ["Holy Champion"], {"Attack": 2}),
    ],
    (127, "Highman Chanter"): [                      # option 1 = Spell Casting 2
        (2, ["Rally"], {"Resistance": 2}),           # stand-in until Hymn
        (3, ["Mental Discipline", "Magic Protection"], {}),
    ],
    (133, "Astra"): [                                # option 1 = Spell Casting 4
        (2, ["Rally"], {"Resistance": 2}),           # stand-in until Hymn
        (3, ["Round Attack"], {"Hits": 8}),
    ],
    (134, "Highman Avenger"): [                      # option 1 = Spell Casting 3
        (2, ["Assassin", "First Strike"], {}),
        (3, ["Skirmisher"], {"Moves": 4}),
    ],

    # ---- Dark Elves (drafted 2026-10-22) -------------------------------------------------------
    (144, "Dark Elf Longbowman"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, ["Assassin", ("Marksmanship", 7)], {}),
    ],
    (146, "Dark Elf Mounted Sergeant"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Round Attack"], {"Attack": 2}),
    ],
    (147, "Dark Elf Longswordman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Strike"], {"Attack": 2}),
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (153, "Dark Elf Sergeant"): [
        (1, ["Drillmaster", "Rally"], {}),          # stand-in until Demoralise
        (2, ["Round Attack"], {"Hits": 4}),
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (154, "Dark Elf Spider Thane"): [
        (1, ["First Strike"], {"Attack": 2}),       # stand-in until Ambush
        (2, ["Entangle Strike"], {}),
        (3, ["Poison Strike"], {"Hits": 4}),
    ],
    (148, "Lady of Pain"): [
        (1, ["Charm"], {}),                          # stand-in until Demoralise
        (2, ["Lifestealing"], {"Hits": 4}),
        (3, [("Mirror Image", 3)], {}),
    ],
    (149, "Dark Elf Executioner"): [
        (1, ["Round Attack"], {}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Assassin", "First Strike"], {}),
    ],
    (151, "Shadow"): [
        (1, [("Mirror Image", 3)], {}),
        (2, ["Round Attack"], {}),
        (3, ["Lifestealing"], {"Attack": 2}),
    ],
    (145, "Dark Elf Storm Priest"): [                # option 1 = Spell Casting 2
        (2, ["Mental Discipline", "Magic Protection"], {}),   # stand-in until Demoralise
        (3, [("Mirror Image", 3)], {}),
    ],
    (150, "Spider Queen"): [                         # option 1 = Spell Casting 3
        (2, ["Entangle Strike"], {"Hits": 4}),
        (3, ["Smoky Haze"], {}),
    ],
    (152, "Incarnate"): [                            # option 1 = Spell Casting 4
        (2, [("Mirror Image", 6)], {}),
        (3, ["Round Attack"], {"Hits": 8}),
    ],

    # ---- Orcs (drafted 2026-10-22) -------------------------------------------------------------
    (162, "Orc Archer"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, [("Marksmanship", 6), "Night Vision"], {}),
    ],
    (172, "Orc Javelineer"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, ["Shield"], {"Defense": 2}),
    ],
    (165, "Orc Swordsman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Strike"], {"Attack": 2}),       # stand-in until Bloodrage
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (171, "Orc Axeman"): [
        (1, ["Extra Strike"], {"Damage": 2}),
        (2, ["Round Attack"], {"Hits": 4}),         # stand-in until Bloodrage
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (164, "Orc Heavy Cavalry"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Round Attack"], {"Attack": 2}),
        (3, ["Cause Fear"], {"Hits": 6}),
    ],
    (166, "Orc Warlord"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Rally"], {"Attack": 2}),              # stand-in until Bloodrage
        (3, ["Mental Discipline", "Magic Protection"], {}),
    ],
    (167, "Kobold"): [
        (1, ["First Strike"], {"Attack": 2}),       # stand-in until Ambush
        (2, ["Lucky"], {}),
        (3, ["Skirmisher"], {"Moves": 4}),
    ],
    (168, "Doom Bat"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Smoky Haze"], {}),
        (3, ["Magic Protection"], {"Hits": 4}),
    ],
    (169, "Orc Assassin"): [
        (1, ["Invisibility"], {}),
        (2, ["First Strike"], {"Attack": 2}),       # stand-in until Ambush
        (3, ["Extra Shots"], {}),
    ],
    (173, "Minotaur"): [
        (1, ["Charge"], {"Moves": 4}),
        (2, ["Cause Fear"], {"Hits": 6}),           # stand-in until Bloodrage
        (3, ["Physical Protection"], {"Moves": -6}),
    ],
    (163, "Orc Shaman"): [                           # option 1 = Spell Casting 2
        (2, ["Rally"], {"Resistance": 2}),           # stand-in until Demoralise
        (3, ["Regeneration"], {"Hits": 4}),         # stand-in until Bloodrage
    ],
    (170, "Red Dragon"): [                           # option 1 = Spell Casting 4
        (2, ["Searing Aura"], {}),
        (3, ["Magic Protection"], {"Hits": 8}),
    ],

    # ---- Goblins (drafted 2026-10-22) ----------------------------------------------------------
    (180, "Goblin Darter"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, [("Marksmanship", 6), "Concealment"], {}),
    ],
    (182, "Goblin Wolf Rider"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Cause Fear"], {"Attack": 2}),
        (3, ["First Strike"], {"Attack": 2}),       # stand-in until Ambush
    ],
    (183, "Goblin Spearman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Lucky"], {}),
        (3, ["Monster Slaying"], {"Hits": 4}),
    ],
    (186, "Goblin Bomber"): [
        (1, [], {"Hits": 4, "Moves": 6}),
        (2, [("Mirror Image", 3)], {}),
        (3, ["Concealment", "Forestry"], {}),
    ],
    (189, "Goblin Butcher"): [
        (1, ["Regeneration"], {"Hits": 4}),         # stand-in until Devour
        (2, ["Extra Strike"], {"Attack": 2}),
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (185, "Goblin Wyvern Rider"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, ["Smoky Haze"], {}),
        (3, ["Magic Protection"], {"Hits": 6}),
    ],
    (188, "Goblin Big Beetle"): [
        (1, ["Round Attack"], {"Attack": 2}),
        (2, ["Magic Protection"], {"Hits": 6}),
        (3, ["Charge"], {"Moves": 4}),
    ],
    (184, "Troll"): [
        (1, ["Round Attack"], {"Hits": 6}),         # stand-in until Devour
        (2, ["Extra Shots"], {}),
        (3, ["Physical Protection"], {"Moves": -6}),
    ],
    (187, "Karagh"): [
        (1, ["Round Attack"], {}),                  # stand-in until Devour
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Regeneration"], {"Hits": 8}),
    ],
    (190, "Werewolf"): [
        (1, ["Lifestealing"], {"Attack": 2}),       # stand-in until Devour
        (2, ["Round Attack"], {"Hits": 4}),
        (3, ["Charge"], {"Moves": 4}),              # stand-in until Ambush
    ],
    (181, "Goblin Shaman"): [                        # option 1 = Spell Casting 2
        (2, ["Smoky Haze"], {}),
        (3, ["Rally"], {"Resistance": 2}),
    ],

    # ---- Undead (drafted 2026-10-22) -----------------------------------------------------------
    (198, "Undead Archer"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, ["Mental Discipline"], {"Resistance": 2}),
    ],
    (201, "Undead Swordsman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Extra Strike"], {"Attack": 2}),       # stand-in until Undying
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (200, "Undead Knight"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Round Attack"], {"Attack": 2}),       # stand-in until Undying
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (202, "Hell Hound"): [
        (1, ["Searing Aura"], {}),
        (2, ["Lifestealing"], {"Hits": 4}),         # stand-in until Devour
        (3, ["Skirmisher"], {"Moves": 4}),
    ],
    (204, "Undead Bone Horror"): [
        (1, ["Round Attack"], {"Hits": 6}),         # stand-in until Devour
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Smoky Haze"], {}),
    ],
    (206, "Undead Wraith"): [
        (1, [("Mirror Image", 3)], {}),
        (2, ["Mental Discipline", "Magic Protection"], {}),
        (3, ["Assassin", "First Strike"], {}),
    ],
    (220, "Undead Mummy"): [
        (1, ["Smoky Haze"], {}),
        (2, ["Mental Discipline", "Magic Protection"], {}),
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (203, "Undead Reaper"): [                        # Spell Casting 5 is the cap: all three free
        (1, ["Mental Discipline", "Magic Protection"], {}),
        (2, ["Smoky Haze"], {}),
        (3, [], {"Hits": 10, "Defense": 2}),        # stand-in until Undying
    ],
    (248, "Undead Skull Thrower"): [
        (1, ["Extra Shots"], {}),
        (2, [], {"Hits": 8, "Defense": 2}),
    ],
    (249, "Undead Bone Ram"): [
        (1, [], {"Hits": 8, "Defense": 2}),
        (2, [], {"Moves": 6}),
    ],
    (199, "Undead Doom Priest"): [                   # option 1 = Spell Casting 2
        (2, [("Mirror Image", 3)], {}),              # stand-in until Demoralise
        (3, ["Mental Discipline", "Magic Protection"], {}),
    ],
    (205, "Demon"): [                                # option 1 = Spell Casting 3
        (2, ["Searing Aura"], {}),
        (3, ["Round Attack"], {"Hits": 8}),
    ],


    # ---- Azracs (drafted 2026-10-22; Yaka Avatar, Djinn and Scorpion are owner-authored) -------
    (18, "Azrac Bowman"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, [("Mirror Image", 3)], {}),
    ],
    (28, "Azrac Javelineer"): [
        (1, ["Extra Shots"], {}),
        (2, ["Skirmisher"], {"Moves": 4}),
        (3, ["Shield"], {"Defense": 2}),
    ],
    (21, "Azrac Swordsman"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, ["Searing Aura"], {}),
        (3, ["Mental Discipline"], {"Resistance": 4}),
    ],
    (20, "Azrac Rider"): [
        (1, ["Skirmisher"], {"Moves": 4}),
        (2, [("Mirror Image", 3)], {}),
        (3, ["Physical Protection"], {"Moves": -6}),
    ],
    (29, "Azrac Chariot"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Skirmisher"], {"Moves": 4}),
    ],
    (30, "Azrac Howdah"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Cause Fear"], {"Hits": 6}),
    ],
    (23, "Elephant"): [
        (1, ["Physical Protection"], {"Moves": -6}),
        (2, ["Cause Fear"], {"Hits": 8}),
        (3, ["Charge", "Round Attack"], {}),
    ],
    (26, "Sandworm"): [
        (1, ["Round Attack"], {"Hits": 8}),         # stand-in until Devour
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, ["Cause Fear"], {"Attack": 2}),
    ],
    (19, "Azrac Yakamajal"): [                       # option 1 = Spell Casting 2
        (2, ["Searing Aura"], {}),
        (3, ["Rally"], {"Resistance": 2}),
    ],
    (24, "Beholder"): [                              # option 1 = Spell Casting 4
        (2, ["Extra Shots"], {}),
        (3, ["Physical Protection"], {"Moves": -4}),
    ],

    # ---- Human gap: Air Galley (Crossbowman and Charlatan are owner-authored) ------------------
    (7, "Air Galley"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -6}),
        (3, [], {"Hits": 10, "Defense": 2}),
    ],

    # ---- Shared war machines (drafted 2026-10-22; Frost Blower 252 sits above) ----------------
    (246, "Bombard"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -4}),
        (3, [], {"Hits": 8, "Defense": 2}),
    ],
    (247, "Flame Thrower"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, [], {"Hits": 8, "Defense": 2}),
        (3, ["Searing Aura"], {}),
    ],
    (257, "Filth Spreader"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, [], {"Hits": 8, "Defense": 2}),
        (3, ["Smoky Haze"], {}),
    ],
    (251, "Catapult"): [
        (1, ["Extra Shots"], {}),
        (2, ["Physical Protection"], {"Moves": -4}),
        (3, [], {"Hits": 8, "Defense": 2}),
    ],
    (254, "Ballista"): [
        (1, ["Extra Shots"], {}),
        (2, [("Marksmanship", 8)], {}),
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (256, "Shredder Bolt"): [
        (1, ["Extra Shots"], {}),
        (2, [("Marksmanship", 8)], {}),
        (3, ["Physical Protection"], {"Moves": -4}),
    ],
    (250, "Battering Ram"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, [], {"Hits": 8, "Defense": 2}),
    ],
    (253, "Drill"): [
        (1, ["Physical Protection"], {"Moves": -4}),
        (2, [], {"Hits": 8, "Defense": 2}),
        (3, [], {"Moves": 6}),
    ],
    (255, "Builder"): [
        (1, [], {"Moves": 6}),
        (2, [], {"Hits": 10, "Defense": 2}),
    ],

    # ---- Ships (drafted 2026-10-22) ------------------------------------------------------------
    (258, "Dragon Ship"): [
        (1, ["Extra Shots"], {}),
        (2, [], {"Hits": 10, "Defense": 2}),
    ],
    (259, "Cog"): [
        (1, [], {"Hits": 10, "Defense": 2}),
        (2, [], {"Moves": 6}),
    ],
    (260, "Galley"): [
        (1, ["Round Attack"], {"Hits": 6}),
        (2, [], {"Hits": 10, "Defense": 2}),
    ],
}

# Rows the build does not write yet: an ability that is only proposed, or one this writer cannot
# encode (Leadership has its own data class, TLeadershipAbilityData).  Same shape as OPTIONS; a
# PENDING row replaces the OPTIONS row in its slot once its ability exists.  None of the proposed
# abilities here is endorsed (owner, 2026-10-22: "not fully formed ideas"); the OPTIONS rows are
# the drafts.
PENDING = {
    (42, "Frost Queen"): [(3, [("Leadership", 2), "Mental Discipline"], {})],
    (54, "Lizardman Archer"): [(2, ["Venomous Missiles"], {})],
    (66, "Lizardman Javelineer"): [(2, ["Venomous Missiles"], {})],
    (72, "Elf Longbowman"): [(2, ["Piercing Shots"], {})],
    (108, "Dwarf Archer"): [(2, ["Piercing Shots"], {}), (3, ["Spellward"], {})],
    (117, "Dwarf Arbalest"): [(2, ["Piercing Shots"], {})],
    (75, "Elf Longswordsman"): [(3, ["Forest Cover"], {})],
    (78, "Elf Ranger"): [(2, ["Forest Cover"], {})],
    (98, "Centaur"): [(3, ["Forest Cover"], {})],
    (73, "Elf Cleric"): [(2, ["Hymn"], {})],
    (91, "Halfling Cleric"): [(2, ["Hymn"], {})],
    (109, "Dwarf Cleric"): [(2, ["Hymn"], {}), (3, ["Spellward"], {})],
    (127, "Highman Chanter"): [(2, ["Hymn"], {})],
    (133, "Astra"): [(2, ["Hymn"], {})],
    (111, "Dwarf Axeman"): [(3, ["Spellward"], {})],
    (115, "Dwarf First Born"): [(2, ["Spellward"], {})],
    (128, "Highman Paladin"): [(3, ["Martyr"], {})],
    (129, "Highman Legionary"): [(2, ["Martyr"], {})],
    (135, "Highman Legionary"): [(2, ["Martyr"], {})],
    (132, "Valkyrie"): [(1, ["Martyr"], {})],
    (153, "Dark Elf Sergeant"): [(1, ["Demoralise"], {})],
    (148, "Lady of Pain"): [(1, ["Demoralise"], {})],
    (145, "Dark Elf Storm Priest"): [(2, ["Demoralise"], {})],
    (163, "Orc Shaman"): [(2, ["Demoralise"], {}), (3, ["Bloodrage"], {})],
    (199, "Undead Doom Priest"): [(2, ["Demoralise"], {})],
    (154, "Dark Elf Spider Thane"): [(1, ["Ambush"], {})],
    (167, "Kobold"): [(1, ["Ambush"], {})],
    (169, "Orc Assassin"): [(2, ["Ambush"], {})],
    (182, "Goblin Wolf Rider"): [(3, ["Ambush"], {})],
    (190, "Werewolf"): [(1, ["Devour"], {}), (3, ["Ambush"], {})],
    (204, "Undead Bone Horror"): [(1, ["Devour"], {})],
    (203, "Undead Reaper"): [(3, ["Undying"], {})],
    (165, "Orc Swordsman"): [(2, ["Bloodrage"], {})],
    (171, "Orc Axeman"): [(2, ["Bloodrage"], {})],
    (166, "Orc Warlord"): [(2, ["Bloodrage"], {})],
    (173, "Minotaur"): [(2, ["Bloodrage"], {})],
    (189, "Goblin Butcher"): [(1, ["Devour"], {})],
    (184, "Troll"): [(1, ["Devour"], {})],
    (187, "Karagh"): [(1, ["Devour"], {})],
    (202, "Hell Hound"): [(2, ["Devour"], {})],
    (201, "Undead Swordsman"): [(2, ["Undying"], {})],
    (200, "Undead Knight"): [(2, ["Undying"], {})],
    (26, "Sandworm"): [(1, ["Devour"], {})],
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
    for (rid, name), rows in PENDING.items():
        for slot, abil, stats in rows:
            print(f"[pend] {rid:4d} {name:<20} option {slot} -> "
                  + ", ".join(x if isinstance(x, str) else "%s %d" % x for x in abil)
                  + "".join(f"   {k} {v:+d}" for k, v in stats.items()))
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
