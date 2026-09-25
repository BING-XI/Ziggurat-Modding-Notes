#!/usr/bin/env python3
r"""Typo / wording corrections to string fields in `Release/*.pfs`.

    python build_scripts/build_pfs_typos.py            # dry run + verify current state
    python build_scripts/build_pfs_typos.py --apply
    python build_scripts/build_pfs_typos.py --undo
    python build_scripts/build_pfs_typos.py --dis      # also print the before/after strings

One row per correction in `FIXES` below. Everything else here is the plumbing a `.pfs` string edit
needs, which is more than it looks:

  * the string almost never keeps its length, so the record's body directory, every later index
    offset and the trailing CRC all have to move with it;
  * the container has a CRC-32 whose residue must come out at `PFS_RESIDUE`, and the game/editor
    die silently with 'Invalid HSSET'-style failures if it does not;
  * `AoWDevEd` rewrites these files whole whenever the author saves, so NOTHING may be hard-coded:
    record offsets, the index layout and the directory widths are all re-derived every run.

⚠ **A `.pfs` string field comes in two forms and they are not interchangeable.** Descriptions are
`u32`-length-prefixed; names are `u8` Pascal. `pfs.pstr()` only knows the second, and misreads the
first (three leading NULs, drops the last character). `read_str()` below sniffs which it is and
refuses anything that is neither, so an integer field can never be mistaken for text.

Revert is `--undo`: surgical, per-fix, reverse order, and it touches no backup. A `<file>.pre-typos`
snapshot is taken on the first `--apply` **only while every fix in that file is still in its `old`
state** -- once the table grows, later runs correctly leave the original snapshot alone rather than
overwriting it with an already-patched file. Per CLAUDE.md that backup is a courtesy, not the revert
path.

Derivation notes for the container format live in `Modding Resources/PFS_Format_CRC.md`; the worked
example of a length-changing write is `build_vision9.py` (and its `Vision_Nine_Levels.md`).
"""

import argparse
import importlib.util
import os
import re
import shutil
import struct
import zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

PFS_RESIDUE = 0x2144DF1C      # crc32(d[4:]) of an intact .pfs -- holds for every file in Release/
SUFFIX = ".pre-typos"
# CLAUDE.md 2026-09-03: a snapshot goes in <game dir>\backups\, never beside the target.
# Migrated 2026-09-07. Safe to repoint without moving anything: the gate below also requires
# every fix to plan "ok", so it cannot mint one from an already-patched file at either path.
BACKUP_DIR = os.path.join(GAME, "backups")


# --------------------------------------------------------------------------------------------
# The table. `rec` is the .pfs record id, NOT the ability/unit id -- for Ability.pfs the record id
# is `ability id + 10` (Charm is ability 0x94 -> record 158). `tag` is the body directory tag:
# 5 = description, 10 = name, per PFS_Format_CRC.md.
#
# `old` must occur EXACTLY ONCE in the field, and must not be a substring of `new` or vice versa --
# both are checked at start-up, because either would make "is this already applied?" unanswerable.
# --------------------------------------------------------------------------------------------
FIXES = [
    ("Spells.pfs",   20,  10,
     'Freezes a small area of water, rendering it solid enough to walk over.\r\n',
     'Freezes a small area of water solid enough to walk over, and chills the land it touches: desert to steppe, steppe to grass, grass to snow. The ice and the chill both thaw after a few turns.\r\n',
     "Freeze Water -> Grip of Winter (build_gripofwinter.py): the spell gained a terrain-"
     "cooling ladder and became castable on land, and both effects revert"),
    ("Ability.pfs",  24,   5,
     'Infuses melee strikes with flame which can set enemies alight (5 Atk vs Res).\r\n',
     'Infuses melee strikes with flame which can set enemies alight (10 Atk vs Res).\r\n',
     "record 24 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  25,   5,
     'Infuses melee strikes with cold energy which can freeze enemies (5 Atk vs Res).\r\n',
     'Infuses melee strikes with cold energy which can freeze enemies (10 Atk vs Res).\r\n',
     "record 25 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  26,   5,
     'Infuses melee strikes with lightning energy which can stun (5 Atk vs Res).\r\n',
     'Infuses melee strikes with lightning energy which can stun (10 Atk vs Res).\r\n',
     "record 26 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  27,   5,
     'Infuses melee strikes with poison (5 Atk vs Res).\r\n',
     'Infuses melee strikes with poison (10 Atk vs Res).\r\n',
     "record 27 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  28,   5,
     'Infuses melee strikes with death energy which can curse enemies (5 Atk vs Res).\r\n',
     'Infuses melee strikes with death energy which can curse enemies (10 Atk vs Res).\r\n',
     "record 28 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  29,   5,
     'Infuses melee strikes with holy energy which can inflict vertigo (5 ATK vs RES).\r\n',
     'Infuses melee strikes with holy energy which can inflict vertigo (10 ATK vs RES).\r\n',
     "record 29 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  34,   5,
     'Launches a massive rock (4/6) at a long-ranged wall or unit.\r\n',
     'Launches a massive rock (8/13) at a long-ranged wall or unit.\r\n',
     "record 34 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  37,   5,
     'Allows the unit to ensnare their target (7 Atk vs Res) in a thick, gooey web that restricts all movement and also lowers its Defense (-2). \r\n',
     'Allows the unit to ensnare their target (14 Atk vs Res) in a thick, gooey web that restricts all movement and also lowers its Defense (-2). \r\n',
     "record 37 (doubling + 2026-08-24 re-grade, full-text row)"),
    # ⚠ 12 WAS WRONG and this row aborted every Ability.pfs write until 2026-08-29. The text was
    # stale BEFORE the doubling: vanilla code returned 6 (Ghidra) but Ziggurat had hand-edited it to
    # 5, and the doubling pass doubled the CODE 5 -> 10 (`FivePct_Doubled_Sources_Inventory.md`
    # row `0x55770665`) while this row doubled the TEXT 6 -> 12. Live bytes settle it:
    # `TDominateAbility.GetTouchAttack @0x55770664` = `b0 0a` = `mov al,10`. The field was later
    # corrected to 10 by hand, which left the table matching neither `old` nor `new` -- and
    # `process()` aborts the whole FILE on one row error, so no Ability.pfs fix could be applied.
    ("Ability.pfs",  38,   5,
     ('Allows the unit to force their will upon others, even beasts, elementals and undead. (6 Atk vs Res).\r\n',
      'Allows the unit to force their will upon others, even beasts, elementals and undead. (12 Atk vs Res).\r\n',
      'Allows the unit to force their will upon others, even beasts, elementals and undead. (10 Atk vs Res).\r\n'),
     'Allows the unit to force their will upon others, even beasts, elementals and undead. (Res vs Res).\r\n',
     "record 38 Dominate: the roll is the commander's RES since build_command_resroll.py (2026-09-25)"),
    ("Ability.pfs",  39,   5,
     ('Lets the unit attempt to warmly entice a target to follow them.\r\n(5 Atk vs Res)\r\n',
      'Lets the unit attempt to warmly entice a target to follow them.\r\n(10 Atk vs Res)\r\n'),
     'Lets the unit attempt to warmly entice a target to follow them.\r\n(Res vs Res)\r\n',
     "record 39 Seduce: the roll is the commander's RES since build_command_resroll.py (2026-09-25)"),
    ("Ability.pfs",  40,   5,
     'Afflicts enemies in a conical area with (7/2) lightning, bane curse and poison.\r\n',
     'Afflicts enemies in a conical area with (14/4) lightning, bane curse and poison.\r\n',
     "record 40 (doubling + 2026-08-24 re-grade, full-text row)"),
    # RE-TUNED 2026-08-29 (user ruling): the ATK bonus is rescaled 2 -> 1 per level, by
    # `build_marksmanship_atk2.py --undo` (which removes the inserted `add al,al` at the head of
    # cave 0x5580C240, so the bonus is `add bl,al` = ATK += level again). DAM is UNCHANGED at
    # +1/level -- `add ebx,eax` @0x5576E643 in GetDamageRA, with EAX = the ability level.
    # `old` is a tuple: [0] vanilla 4-level text (what --undo restores), [1] the 2-per-level text
    # this field held between 2026-08-24 and today.
    ("Ability.pfs",  42,   5,
     ('Gives the unit increased proficiency with ranged attacks.\r\nLevel 1 (At+1/Dm+0)\r\nLevel 2 (At+2/Dm+1)\r\nLevel 3 (At+3/Dm+1)\r\nLevel 4 (At+4/Dm+2)\r\n',
      'Gives the unit increased proficiency with ranged attacks.\r\nLevel 1 (At+2/Dm+1)\r\nLevel 2 (At+4/Dm+2)\r\nLevel 3 (At+6/Dm+3)\r\nLevel 4 (At+8/Dm+4)\r\nLevel 5 (At+10/Dm+5)\r\nLevel 6 (At+12/Dm+6)\r\nLevel 7 (At+14/Dm+7)\r\nLevel 8 (At+16/Dm+8)\r\n'),
     'Gives the unit increased proficiency with ranged attacks.\r\nLevel 1 (At+1/Dm+1)\r\nLevel 2 (At+2/Dm+2)\r\nLevel 3 (At+3/Dm+3)\r\nLevel 4 (At+4/Dm+4)\r\nLevel 5 (At+5/Dm+5)\r\nLevel 6 (At+6/Dm+6)\r\nLevel 7 (At+7/Dm+7)\r\nLevel 8 (At+8/Dm+8)\r\n',
     "Marksmanship levels (8 levels; ATK rescaled 2 -> 1 per level 2026-08-29)"),
    ("Ability.pfs",  45,   5,
     'After successful touch attack, target must resist or die. (9 Atk vs Res)\r\n',
     'After successful touch attack, target must resist or die. (18 Atk vs Res)\r\n',
     "record 45 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  50,   5,
     'Allows the unit to ensnare a target by summoning grasping tentacles (7 Atk vs Res), which restrict all movement and also lower Defense (-2). \r\n',
     'Allows the unit to ensnare a target by summoning grasping tentacles (14 Atk vs Res), which restrict all movement and also lower Defense (-2). \r\n',
     "record 50 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  54,   5,
     'Blasts walls or units across long ranges with powerful munitions. (4 Atk 12 Dam).\r\n',
     'Blasts walls or units across long ranges with powerful munitions. (8 Atk 25 Dam).\r\n',
     "record 54 (doubling + 2026-08-24 re-grade, full-text row)"),
    # RE-TUNED 2026-09-16 by build_leadership_others.py: Leadership no longer buffs its own
    # holder -- a unit's bonus is the best Leadership level among the OTHER units in its party.
    # `old` is a tuple: [0] vanilla text (what --undo restores), [1] the 4-level text this field
    # held between 2026-08-24 and today.
    ("Ability.pfs",  56,   5,
     ('Gives all units in party +2 Attack and +1 Defense.\r\n',
      'Gives all units in party +1 Attack and +1 Defense per level.\r\n'),
     'Gives every OTHER unit in the party +1 Attack and +1 Defense per level. A leader gains '
     'nothing from its own Leadership, only from other leaders beside it.\r\n',
     "record 56 (doubling + 2026-08-24 re-grade; others-only rework 2026-09-16)"),
    ("Ability.pfs",  57,   5,
     'Restores life to the injured (+5 HitPoints). Can be performed only once a day.\r\n',
     'Restores life to the injured (+10 HitPoints). Can be performed only once a day.\r\n',
     "record 57 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  75,   5,
     'Self-induced destruction of the unit, resulting in massive damage to all nearby. (8/6, fire and wall damage)\r\n',
     'Self-induced destruction of the unit, resulting in massive damage to all nearby. (16/12, fire and wall damage)\r\n',
     "record 75 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  96,   5,
     'Releases a short-ranged blast of (7/5) fire. \r\n',
     'Releases a short-ranged blast of (14/11) fire. \r\n',
     "record 96 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  97,   5,
     'Blasts a short-ranged area with extreme cold (7/5). \r\n',
     'Blasts a short-ranged area with extreme cold (14/11). \r\n',
     "record 97 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  99,   5,
     'Releases a short-ranged blast of (7/5) holy energy. \r\n',
     'Releases a short-ranged blast of (14/11) holy energy. \r\n',
     "record 99 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 100,   5,
     'Delivers a blast of (7/5) poisonous fumes over a short range.\r\n',
     'Delivers a blast of (14/11) poisonous fumes over a short range.\r\n',
     "record 100 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 102,   5,
     'The unit is dazed. It cannot perform actions, which also lowers its Defense (-2). \r\n',
     'The unit is dazed. It cannot perform actions, which also lowers its Defense (-4). \r\n',
     "Stunned (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 103,   5,
     'Inflicts -2 DEF/RES and prevents the unit from healing normally.\r\n',
     'Inflicts -4 DEF/RES and prevents the unit from healing normally.\r\n',
     "Cursed (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 104,   5,
     'The unit is trapped in grasping weeds. It cannot perform actions, which also lowers its Defense (-2). \r\n',
     'The unit is trapped in grasping weeds. It cannot perform actions, which also lowers its Defense (-4). \r\n',
     "Entangled (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 105,   5,
     'Unit is frozen in place for 3 turns, but the ice boosts Defense (+2). \r\n',
     'Unit is frozen in place for 3 turns, but the ice boosts Defense (+3). \r\n',
     "Frozen (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 106,   5,
     'Poisoned units struggle to wield melee weapons, losing 2 Atk and Dam.\r\n',
     'Poisoned units struggle to wield melee weapons, losing 3 Atk and Dam.\r\n',
     "Poisoned (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 107,   5,
     'The unit is trapped in a Web. It cannot perform actions, which also lowers its Defense (-2). \r\n',
     'The unit is trapped in a Web. It cannot perform actions, which also lowers its Defense (-4). \r\n',
     "Webbed (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 108,   5,
     'Renders the unit less able to Attack (-2) or Defend (-2) for an entire day.\r\n',
     'Renders the unit less able to Attack (-3) or Defend (-3) for an entire day.\r\n',
     "Vertigo (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 109,   5,
     "Increases the unit's Defense (+1) and Resistance (+1).\r\n",
     "Increases the unit's Defense (+1) and Resistance (+3).\r\n",
     "Nature's Blessing (doubling + 2026-08-24 re-grade, full-text row)"),
    # RE-TUNED 2026-09-13 (user): raised to +2/+4 alongside Blessed (record 168), whose display
    # name it shares. `old` [0] is the vanilla text --undo restores, [1] the 2026-08-24 re-grade.
    ("Ability.pfs", 110,   5,
     ('Gives the unit increased Defense (+1) and Resistance (+1).\r\n',
      'Gives the unit increased Defense (+1) and Resistance (+3).\r\n'),
     'Gives the unit increased Defense (+2) and Resistance (+4).\r\n',
     "High Prayer Blessing (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 116,   5,
     # Same stale-before-the-doubling shape as record 38: text said 8, code said 7, the pass
     # doubled the code to 14 (`FivePct_Doubled_Sources_Inventory.md` row `0x55769be9`) and this
     # row doubled the text to 16. Live: `TPossessAbility.GetTouchAttack @0x55769BE8` = `b0 0e`.
     ('Allows the unit to enter a target, and take over their body. (8 Atk vs Res)\r\n',
      'Allows the unit to enter a target, and take over their body. (16 Atk vs Res)\r\n'),
     'Allows the unit to enter a target, and take over their body. (14 Atk vs Res)\r\n',
     "record 116 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 121,   5,
     "When attacking, increases the Damage (+3) of the unit's first melee strike.\r\n",
     "When attacking, increases the Damage (+5) of the unit's first melee strike.\r\n",
     "Charge (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 122,   5,
     'Enhanced strikes (+3 Atk/Dam) against monstrous units.\r\n',
     'Enhanced strikes (+5 Atk/Dam) against monstrous units.\r\n',
     "Monster Slaying (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 123,   5,
     "Reduces the Attack (-4) power of an enemy's first strike against the unit.\r\n",
     "Reduces the Attack (-8) power of an enemy's first strike against the unit.\r\n",
     "Parry (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 126,   5,
     'When defending during melee, the unit takes the initial strike.\r\n',
     'The unit strikes first when defending, and negates enemy Charge.\r\n',
     "First Strike (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 128,   5,
     'Attacking strikes now absorb 2 Hitpoints.\r\n',
     'Attacking strikes now absorb 4 Hitpoints.\r\n',
     "record 128 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 129,   5,
     'Infuses melee strikes with the power (7 Atk vs Res) to ensnare the target in grasping vines.\r\n',
     'Infuses melee strikes with the power (14 Atk vs Res) to ensnare the target in grasping vines.\r\n',
     "record 129 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 137,   5,
     'For 2 rounds, the burning unit may be further injured by the flames (8 Atk 2 Dam).\r\n',
     'For 2 rounds, the burning unit may be further injured by the flames (16 Atk 4 Dam).\r\n',
     "record 137 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 141,   5,
     'Eats away at the unit from within, clouding their mind, and inflicting Damage (1) each turn until they perish.\r\n',
     'Eats away at the unit from within, clouding their mind, and inflicting Damage (2) each turn until they perish.\r\n',
     "record 141 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 156,   5,
     'Increases Attack (+2) and Damage (+2) of strikes against the forces of evil.\r\n',
     'Increases Attack (+5) and Damage (+5) of strikes against the forces of evil.\r\n',
     "record 156 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 157,   5,
     'Increases Attack (+2) and Damage (+2) of strikes against the forces of good.\r\n',
     'Increases Attack (+5) and Damage (+5) of strikes against the forces of good.\r\n',
     "record 157 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 158,   5,
     ('Persuades a humaoid enemy to switch sides (5 Atk vs Res).\r\n',
      'Persuades a humanoid enemy to switch sides (10 Atk vs Res).\r\n'),
     'Persuades a humanoid enemy to switch sides (Res vs Res).\r\n',
     "record 158 Charm: the roll is the commander's RES since build_command_resroll.py (2026-09-25)"),
    ("Ability.pfs", 163,   5,
     "Renders the unit's skin tougher, giving it stronger Defense (+2). \r\n",
     "Renders the unit's skin tougher, giving it stronger Defense (+3). \r\n",
     "Stone Skin (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 164,   5,
     "Imbues the unit's melee strike with magical energy, and adds +2/2 Attack and Damage.\r\n",
     "Imbues the unit's melee strike with magical energy, and adds +3/3 Attack and Damage.\r\n",
     "Enchanted Weapon (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 166,   5,
     'Increases Attack (+3) power, while reducing Defense (-1).\r\n',
     'Increases Attack (+5) power, while reducing Defense (-2).\r\n',
     "Fury (doubling + 2026-08-24 re-grade, full-text row)"),
    # RE-TUNED 2026-09-13 (user): Blessed raised to DEF +2 / RES +4, exempting it from the
    # 2026-08-24 one-notch-down re-grade. Engine side is build_buff_regrade.py @0x557BB5E4/E8.
    # ⚠ Record 110 (High Prayer Blessing) now carries the IDENTICAL `new` text -- correct, they
    # share the display name and the effect. Resolve these by RECORD ID, never by text.
    # ⚠ `old[0]` was 'Resistance (+2)', which exists in NO copy of Ability.pfs (all vanilla copies
    # read (+1)/(+1)) -- the pre-doubling CODE value written into a text row by mistake, so --undo
    # restored a string the game never shipped. Same defect as Spells.pfs 66 above. Corrected.
    ("Ability.pfs", 168,   5,
     ('Gives the unit increased Defense (+1) and Resistance (+1).\r\n',
      'Gives the unit increased Defense (+1) and Resistance (+3).\r\n'),
     'Gives the unit increased Defense (+2) and Resistance (+4).\r\n',
     "Blessed (doubling; raised to +2/+4 2026-09-13, full-text row)"),
    ("Ability.pfs", 170,   5,
     'Increases Attack (+2) and Damage (+2) of strikes against the forces of evil.\r\n',
     'Increases Attack (+5) and Damage (+5) of strikes against the forces of evil.\r\n',
     "record 170 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 171,   5,
     'Increases Attack (+2) and Damage (+2) of strikes against the forces of good.\r\n',
     'Increases Attack (+5) and Damage (+5) of strikes against the forces of good.\r\n',
     "record 171 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs", 178,   5,
     "Increases the unit's Attack and Damage by +2, but reduces Defence by 1.\r\n",
     "Increases the unit's Attack and Damage by +3, but reduces Defence by 2.\r\n",
     "Bloodlust (doubling + 2026-08-24 re-grade, full-text row)"),
    # Dark Gift, 2026-09-14 (user's wording): the card and the spellbook now carry the SAME
    # sentence, and it finally names the lifesteal the ability actually grants (DG_HEAL in
    # `build_lifesteal_roundattack.py`, re-tuned 4 -> 3 the same day). DAM is unchanged at +3
    # (`TDarkGiftEnchantment.GetDamage @0x557BB730` = `b0 03`).
    # ⚠ `old[0]` is the TRUE vanilla text, read out of `<root>/Release/Ability.pfs`. The value
    # this row declared before ('...and +2 to Damage.') is a later Ziggurat state, not vanilla --
    # `--undo` would have restored a string the game never shipped.
    ("Ability.pfs", 179,   5,
     ('Gives a single unit Death Strike and +1 to damage.\r\n',
      'Gives a single unit Death Strike and +2 to Damage.\r\n',
      'Gives a single unit Death Strike and +3 to Damage.\r\n'),
     'Gives a single unit Death Strike, +3 Dam, and +3 lifestealing.\r\n',
     "Dark Gift card (2026-09-14 wording; vanilla baseline corrected)"),
    ("Spells.pfs",  26,  10,
     'A powerful enchantment which grants a unit the ability to strike ethereal opponents, besides granting +2 Atk and +2 Dam.\r\n',
     'A powerful enchantment which grants a unit the ability to strike ethereal opponents, besides granting +3 Atk and +3 Dam.\r\n',
     "record 26 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Spells.pfs",  27,  10,
     "Hardens the target unit's body, increasing Defense (+2). \r\n",
     "Hardens the target unit's body, increasing Defense (+3). \r\n",
     "record 27 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Spells.pfs",  43,  10,
     'Instills destructive rage in a unit, bettering its ability to Attack (+3), but weakening Defense (-1).\r\n',
     'Instills destructive rage in a unit, bettering its ability to Attack (+5), but weakening Defense (-2).\r\n',
     "record 43 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Spells.pfs",  45,  10,
     'Removes all non-magical handicaps from the target unit and heals it (+5 HitPoints). \r\n',
     'Removes all non-magical handicaps from the target unit and heals it (+10 HitPoints). \r\n',
     "record 45 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Spells.pfs",  46,  10,
     'Bestows Holy might with which a unit may strike against any evil being with increased Attack (+2) and Damage (+2).\r\n',
     'Bestows Holy might with which a unit may strike against any evil being with increased Attack (+5) and Damage (+5).\r\n',
     "record 46 (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Spells.pfs",  47,  10,
     'Bestows upon the target unit unholy might  when fighting opponents of good alignment, increasing Attack (+2) and Damage (+2) power.\r\n',
     'Bestows upon the target unit unholy might  when fighting opponents of good alignment, increasing Attack (+5) and Damage (+5) power.\r\n',
     "record 47 (doubling + 2026-08-24 re-grade, full-text row)"),
    # RE-TUNED 2026-09-13 with Ability.pfs 168: the Bless SPELL's book entry describes the same
    # effect as the Blessed ability card, so it moves with it or the spellbook contradicts the card.
    # ⚠ `old[0]` was 'Resistance (+2)', a text that exists in NO copy of Spells.pfs -- every vanilla
    # copy reads (+1)/(+1). It was the pre-doubling CODE value written into the text row by mistake,
    # so --undo would have restored a string the game never shipped. Corrected to the real vanilla
    # text; [1] is the 2026-08-24 re-grade this field actually held.
    ("Spells.pfs",  66,  10,
     ('Shields a unit with holiness, giving additional Defense (+1), Resistance (+1), and Protection from Death-based Attacks.\r\n',
      'Shields a unit with holiness, giving additional Defense (+1), Resistance (+3), and Protection from Death-based Attacks.\r\n'),
     'Shields a unit with holiness, giving additional Defense (+2), Resistance (+4), and Protection from Death-based Attacks.\r\n',
     "Bless spell (doubling; raised to +2/+4 2026-09-13, full-text row)"),
    ("Spells.pfs",  83,  10,
     'Restores the vigor in both units and lands, by a gentle rain of refreshing pure water. Heal +3\r\n',
     'Restores the vigor in both units and lands, by a gentle rain of refreshing pure water. Heal +6\r\n',
     "record 83 (doubling + 2026-08-24 re-grade, full-text row)"),
    # Dark Gift spellbook entry -- the twin of Ability.pfs 179 above; identical `new` by design,
    # since the table resolves by record id and never by text. ⚠ `old[0]` is the TRUE vanilla
    # text from `<root>/Release/Spells.pfs`, which mentions no lifesteal at all (Dark Gift's
    # lifesteal is this mod's addition, ability 0xA9).
    ("Spells.pfs",  87,  10,
     ('Gives a single unit Death Strike and +1 to damage.\r\n',
      'Gives a single unit Death Strike, +2 to Damage, and +2 Lifestealing.\r\n',
      'Gives a single unit Death Strike, +3 to Damage, and +4 Lifestealing.\r\n'),
     'Gives a single unit Death Strike, +3 Dam, and +3 lifestealing.\r\n',
     "Dark Gift spellbook (2026-09-14 wording, lifesteal 4 -> 3; vanilla baseline corrected)"),
    # RE-TUNED 2026-09-13 with Ability.pfs 110, for the same reason as record 66 above.
    ("Spells.pfs", 112,  10,
     ('Blesses all friendly units during combat, increasing Defense (+1), and Resistance (+1) and partially healing wounds.\r\n',
      'Blesses all friendly units during combat, increasing Defense (+1), and Resistance (+3) and partially healing wounds.\r\n'),
     'Blesses all friendly units during combat, increasing Defense (+2), and Resistance (+4) and partially healing wounds.\r\n',
     "High Prayer spell (doubling; raised to +2/+4 2026-09-13, full-text row)"),
    ("Spells.pfs", 121,  10,
     'Attempts to ensnare a target by summoning grasping tentacles, which restrict all movement and lower Defense (-2). \r\n',
     'Attempts to ensnare a target by summoning grasping tentacles, which restrict all movement and lower Defense (-4). \r\n',
     "Charge (doubling + 2026-08-24 re-grade, full-text row)"),
    ("Ability.pfs",  62,   5,
     'Enables Spellcasting, with 10/20/40/60/90 spellcasting points and 5/15/30/50/75 mana generation for Spellcasting levels I / II / III / IV / V.\r\n',
     'Enables Spellcasting, with 10/20/40/60/90 spellcasting points for levels I / II / III / IV / V. On a hero, mana generation per turn equals Resistance x Spellcasting level.\r\n',
     "record 62 = Spell Casting (ability 0x34). The old text was wrong on BOTH counts: generation was the 10/20/40/60/90 table, not 5/15/30/50/75, and since build_spellcast_manares.py it is Resistance x level. Confirmed in-game 2026-08-27."),

    # ------------------------------------------------------------------------------------
    # 2026-08-27 sweep. Field semantics were DERIVED, not assumed, and hold for both ctors:
    #   TRangedAttackAbility ctor 0x5576ED48   ATTACK = CL   DAMAGE = 1st push imm8
    #   TBoltsAbility        ctor 0x5576EDE8   ATTACK = ECX  DAMAGE = 1st push imm8
    # proven by GetAttackRA @0x5576E65C (mov bl,[eax+0x2a]) and GetDamageRA @0x5576E614
    # (mov bl,[eax+0x29]). The description convention is ATK/DAM, corroborated by the two
    # rows already in this table: Hurl Boulder "(8/12)" and Fire Cannon "(8 Atk 24 Dam)".
    # ⚠ The OTHER pushes in a block are the damage-TYPE element and a sound id -- doubling
    # one of those would change a bolt's element or its sound, not its strength.
    # Every number below was byte-read from the LIVE DLL and byte-diffed against pristine.
    # ------------------------------------------------------------------------------------

    # -- ranged attacks whose ATK and DAM both doubled cleanly
    ("Ability.pfs",  35,   5, 'four 2/1 stones', 'four 4/3 stones',
     "Hurl Stones: live ATK 4 (cl @0x5576F5DA), DAM 2 (push @0x5576F5B0); pristine 3/1"),
    ("Ability.pfs",  41,   5, 'two 5/2 eruptions', 'two 10/5 eruptions',
     "Call Flames: live 10/4 (cl @0x5576F715, push @0x5576F6EB); pristine 5/4"),
    ("Ability.pfs",  55,   5, 'two 5/4 bullets', 'two 10/9 bullets',
     "Fire Musket: live 10/8 (cl @0x5576F619, push @0x5576F5EF); pristine 5/7"),
    ("Ability.pfs",  65,   5, 'three 3/4 beams', 'three 6/9 beams',
     "Doom Gaze: live 6/8 (cl @0x5576F7D2, push @0x5576F7A8). Note the ATK byte is "
     "byte-identical to pristine -- vanilla 6, Ziggurat 3, doubled back to 6"),
    ("Ability.pfs",  71,   5, 'three 3/1 poisoned', 'three 6/3 poisoned',
     "Poison Darts: live 6/2 (cl @0x5576F793, push @0x5576F769); pristine 4/1"),

    # -- rows where the text ALSO never matched the code. Writing the live value corrects an
    #    older authoring error as well as the doubling, so these are not pure x2 swaps.
    ("Ability.pfs",  67,   5, 'a 6/3 quarrel', 'a 14/7 quarrel',
     "Shoot Bolt: live 14/6 (cl @0x5576F55C, push @0x5576F532). Pure doubling would give "
     "12/6 -- the pre-doubling code held ATK 7 while the text said 6, so 14 is what the "
     "binary actually has"),
    ("Ability.pfs",  68,   5, 'a 4/3 javelin', 'a 8/9 javelin',
     "Throw Javelin: live 8/8 (cl @0x5576F59B, push @0x5576F571). Pure doubling would give "
     "8/6 -- the pre-doubling code held DAM 4 while the text said 3"),
    ("Ability.pfs",  72,   5, 'a 6/4 poisonous', 'a 12/7 poisonous',
     "Poison Spit: live 12/6 (cl @0x5576F6D6, push @0x5576F6AC). Pure doubling would give "
     "12/8 -- the text matched VANILLA (DAM 4) and went stale when Ziggurat cut it to 3"),
    ("Spells.pfs", 132,  10, '5 ATK and 3 DAM', '4 ATK and 4 DAM',
     "Stoning (spell id 0x7A): TStoning.Create @0x557F9420 sets +0x34=4 (ATK) and +0x35=4 "
     "(DAM); roles proven at GetCombatDamageValue @0x557F72A5. Pristine 5/2, so BOTH text "
     "numbers were already stale before the doubling"),

    # -- the five bolts, doubled in code on 2026-08-27 by build_bolts_double.py
    ("Ability.pfs", 130,   5, 'a 6/3 bolt of death', 'a 12/7 bolt of death',
     "Black Bolts: ecx @0x5576F326 6->12, push @0x5576F305 3->6"),
    ("Ability.pfs", 131,   5, 'a 7/3 bolt of magic', 'a 14/7 bolt of magic',
     "Magic Bolts: ecx @0x5576F35F 7->14, push @0x5576F33E 3->6"),
    ("Ability.pfs", 132,   5, 'a 6/3 bolt of ice', 'a 12/7 bolt of ice',
     "Frost Bolts: ecx @0x5576F398 6->12, push @0x5576F377 3->6"),
    ("Ability.pfs", 133,   5, 'bolt of 6/3 lightning', 'bolt of 12/7 lightning',
     "Lightning Bolts: ecx @0x5576F3D1 6->12, push @0x5576F3B0 3->6"),
    ("Ability.pfs", 134,   5, 'bolt of 6/3 holy', 'bolt of 12/7 holy',
     "Holy Bolts: ecx @0x5576F40A 6->12, push @0x5576F3E9 3->6"),

    # -- touch attacks whose text never matched the code. The 2026-08-24 pass doubled the
    #    STRING's number instead of reading the binary, so both are now off by the same
    #    factor. The convention is set by the five siblings that do agree exactly:
    #    Web 14, Entangle 14, Invoke Death 18. (Dominate's row went into its full-text row when
    #    the command roll became RES vs RES, build_command_resroll.py.)
    ("Ability.pfs", 116,   5, '(16 Atk vs Res)', '(14 Atk vs Res)',
     "Possess: TPossessAbility.GetTouchAttack @0x55769BE8 = 14 (vanilla 5, unhooked); "
     "shared with TPossessedAbility via both VMT+0x10c slots"),

    # -- fear / morale. ⚠ These change the STAT as well as the number: MoraleDefenseModifier
    #    @0x558E83E0 was zeroed on 2026-08-27, so every "Def-2" here is a promise the engine
    #    can no longer keep. Band-0 (terrible) modifiers are now ATK -4 / RES -6 / DEF 0.
    #    Spelled "Atk" to match the file's own convention (Att: appears only in rec 48).
    ("Ability.pfs",  61,   5, '(Def-2 Res-3)', '(Atk-4 Res-6)',
     "Cause Fear inflicts Panicked -> terrible morale band. Live band-0: ATK ladder "
     "(cave 0x5580C114) -4, MoraleResistanceModifier @0x558E83D8 -6, Defence table zeroed"),
    ("Ability.pfs",  63,   5, '(-2 Def -3 Res)', '(-4 Atk -6 Res)',
     "Holy Fear = -40 morale value; quoted pair is the terrible-band modifier, keeping the "
     "existing convention"),
    ("Ability.pfs", 118,   5, '(Def-2, Res-3)', '(Atk-4, Res-6)',
     "Panicked = -80 morale value, always lands on the terrible band"),

    # -- Protections. The +4 is NOT a stat bonus: it is a type-scoped addend inside one
    #    HitRole call in TAbstractUnit.ExecuteDamageEffectsRole @0x55781BA4 (six `add edi,4`
    #    sites, pristine `add edi,2`). Worded as a check bonus so it is not read as the
    #    "Resistance (+3)" stat notation used elsewhere in this file.
    #    ⚠ Magic (rec 85) and Physical (rec 87) are deliberately ABSENT: ExecuteDamageEffectsRole
    #    tests only bits {1,4,0x10,0x20,0x40,2}; there is no branch for magic (0x08) or
    #    physical (0x80), so neither protection has an effect roll to add to.
    ("Ability.pfs",  80,   5, 'death-based attacks by 50%.',
     'death-based attacks by 50%, and adds +4 to the Resistance check against their effects.',
     "Death Protection: +4 on the Cursed effect roll (0x55781D22)"),
    ("Ability.pfs",  81,   5, 'fire-based attacks by 50%.',
     'fire-based attacks by 50%, and adds +4 to the Resistance check against their effects.',
     "Fire Protection: +4 on the Burning effect roll (0x55781C1E)"),
    ("Ability.pfs",  82,   5, 'holy-based attacks by 50%.',
     'holy-based attacks by 50%, and adds +4 to the Resistance check against their effects.',
     "Holy Protection: +4 on the Vertigo effect roll (0x55781D74)"),
    ("Ability.pfs",  83,   5, 'poison-based attacks by 50%.',
     'poison-based attacks by 50%, and adds +4 to the Resistance check against their effects.',
     "Poison Protection: +4 on the Poisoned effect roll (0x55781CD0)"),
    ("Ability.pfs",  84,   5, 'lightning-based attacks by 50%.',
     'lightning-based attacks by 50%, and adds +4 to the Resistance check against their effects.',
     "Lightning Protection: +4 on the Stunned effect roll (0x55781C7E)"),
    ("Ability.pfs",  86,   5, 'cold-based attacks by 50%.',
     'cold-based attacks by 50%, and adds +4 to the Resistance check against their effects.',
     "Cold Protection: +4 on the Frozen effect roll (0x55781DD4)"),
    # -- three records with no row until now.
    #    Archery's damage was the one ranged value the 2026-08-24 pass got right, so it only
    #    needs the +1. Black Breath never had a row at all -- and its old text was the ONLY
    #    honest breath description in the file, since the other four had their damage doubled
    #    in text while the shared code byte stayed at 5.
    ("Ability.pfs",  32,   5, 'two 6/4 arrows', 'two 6/5 arrows',
     "Archery: +1 (build_ranged_damage.py). DAM 4->5 @0x5576F72B; ATK 6 unchanged"),
    ("Ability.pfs",  98,   5, 'a 7/5 cone', 'a 14/11 cone',
     "Black Breath: ATK was doubled 7->14 long ago; DAM came from the SHARED breath byte "
     "TBreathAbility.Create @0x5576EE6B, never doubled, now 5->11 (x2 then +1). The same "
     "byte serves Fire/Cold/Divine/Poison Breath, whose text already claimed 10"),
    # Turn Undead is a REWORD, not a number swap: build_turnundead_res.py made damage scale
    # off the caster's Resistance, so there is no per-level constant left to print. Attack is
    # a plain doubling (GetTouchAttack @0x5576B1F4 = 18/20/22/24) and
    # build_turnundead_double.py then took damage from level x RES/2 to level x RES.
    ("Ability.pfs",  48,   5,
     'targets.\r\nLevel 1  (Att:9/Dam:4)\r\nLevel 2  (Att:10/Dam:8)\r\n'
     'Level 3  (Att:11/Dam:12)\r\nLevel 4  (Att:12/Dam:16)\r\n',
     "targets. Damage equals the user's Resistance, multiplied by the level.\r\n"
     'Level 1  (Att:18)\r\nLevel 2  (Att:20)\r\nLevel 3  (Att:22)\r\nLevel 4  (Att:24)\r\n',
     "Turn Undead: ATK 9/10/11/12 -> 18/20/22/24; DAM is no longer a per-level constant, "
     "the cave @0x5580E2A0 computes level x Resistance (display cave @0x5580E300 matches)"),
    ("Ability.pfs", 177,   5, 'fire-based attacks by 50%.',
     'fire-based attacks by 50%, and adds +4 to the Resistance check against their effects.',
     "Fire Protection enchantment (ability 0xA7): GetAbProtectionTypesAll @0x5574F9CB ORs "
     "the same fire bit as 0x47, and TUnit's VMT +0xF0 is TAbstractUnit.GetProtectionTypes, "
     "so it reaches the roll on ordinary units too"),

    # Spell Ward rescoped 2026-09-06 (build_spellward_rescope.py). The ward no longer blocks
    # "any global spell" -- the master gate at 0x557792E8 now tests the SPELL ID and denies only
    # Warp Party (0x22) and Town Gate (0x26), and the two subordinate 0x40 mask tests are zeroed,
    # so global enchantments, summons, city spells and Disjunction are all unaffected. Note the
    # old text's trailing space before the CRLF -- it is part of the field and must match.
    ("Spells.pfs",  75,  10,
     ('Limits use of global enchantments. Players cannot cast or disjunct any global spells, '
      'unless the Spell Ward is first removed. \r\n',
      # 2026-09-06 text, before the spell was renamed Astral Ward (build_resstr_names.py)
      'Wards the paths of the arcane. While any Spell Ward is active, no player can cast Town '
      'Gate or Warp Party.\r\n'),
     'Wards the paths of the arcane. While any Astral Ward is active, no player can cast Town '
     'Gate or Warp Party.\r\n',
     "record 75 = spell id 65 (Spell Ward -> Astral Ward) + 10. Length-changing write: "
     "128 -> 109 chars"),

    # Power Leak -> Power Leech, 2026-09-07 (build_powerleech.py). The vanilla halving at
    # 0x5577CED8 is dead; the caster now steals 25% of the power income of every magic node owned
    # by another player, and that owner loses the same amount. "Only one at a time" is VANILLA
    # behaviour (TGlobalEnchantment.CanActivate @0x5577DAE8 refuses any second enchantment with
    # the same type code) and is stated here because nothing else in the UI says so. Note the old
    # text's trailing space before the CRLF -- it is part of the field and must match.
    #
    # ⚠ HARD CEILING 205 CHARACTERS on this field, and it is not the u32 length prefix that binds.
    # Record 58's body directory is MIXED: tags 10/11/12 are u8 (width-1) entries, tags 13..17 are
    # u32. Tag 12 sits at offset 158 and moves by the whole shift, so 158 + (new_len - 112) <= 255
    # => encoded field <= 209 B => 205 characters. Longer text makes plan() abort with "exceeds
    # the u8 directory ceiling" -- loudly, not silently. The text below is 195, leaving 10 spare.
    ("Spells.pfs",  58,  10,
     'Sends the mystic forces of the arcane back from whence they came, halving the magic power '
     'of all players. \r\n',
     'Draws the mystic forces of the arcane back to the caster, who takes 25% of the power of '
     'every magic node held by a rival. That rival loses as much. Only one Power Leech may be '
     'active at a time.\r\n',
     "record 58 = spell id 48 (Power Leak -> Power Leech) + 10. Length-changing write: "
     "108 -> 195 chars"),

    # Inioch's share8 spell changes, adopted 2026-09-25. Old texts carry a trailing space before
    # the CRLF where vanilla had one; it is part of the field.
    ("Spells.pfs",  23,  10,
     'Sprouts trees that radiate holy power. All evil units passing through the woods suffer '
     'holy damage. \r\n',
     'Sprouts trees that radiate holy power. All evil units passing through the woods suffer '
     'holy damage and may be struck with Vertigo.\r\n',
     "record 23 = Holy Woods (spell 13); build_ground_debuffs.py adds the Vertigo roll"),
    ("Spells.pfs",  24,  10,
     'Sprouts a barrier of evil trees that radiate death. Good units passing through the woods '
     'suffer damage. \r\n',
     'Sprouts a barrier of evil trees that radiate death. Good units passing through the woods '
     'suffer damage and may be Cursed.\r\n',
     "record 24 = Evil Woods (spell 14); build_ground_debuffs.py adds the Cursed roll"),
    ("Spells.pfs",  28,  10,
     'Levels the earth to plains, removing all earth-based obstacles, such as, mountains and '
     'hills. \r\n',
     'Levels the earth to plains, removing all earth-based obstacles such as mountains and '
     'hills, and leaves rocks where they stood.\r\n',
     "record 28 = Level Terrain (spell 18); build_levelterrain_rocks.py"),
    ("Spells.pfs",  80,  10,
     'Churns a whirling vortex in the water, damaging all water-based units caught therein.\r\n',
     'Churns a whirling vortex in the water, damaging every unit caught therein that cannot fly '
     'and draining its movement. Ships and swimmers suffer most.\r\n',
     "record 80 = Vortex (spell 70); build_vortex_rebalance.py"),
    ("Spells.pfs",  81,  10,
     'Triggers an earthquake underneath the target town, damaging the city and any garrisoned '
     'units.\r\n',
     'Triggers an earthquake underneath the target town, damaging the city and any garrisoned '
     'units. Wooden walls crumble more easily than stone, and quakes strike harder '
     'underground.\r\n',
     "record 81 = Town Quake (spell 71); build_townquake_retune.py"),
    ("Spells.pfs", 134,  10,
     'Changes a battlefield area into sticky mud. Movement speed on ooze-covered terrain is '
     'halved. \r\n',
     'Turns a battlefield area to sticky mud that halves movement and puts out fires and '
     'burning units.\r\n',
     "record 134 = Ooze (spell 124); build_ooze_extinguish.py. NB u8 directory: tag 12 sits at "
     "offset 247, so this field may grow by at most 8 B (96 -> 99 here)"),

    # Slow -> Lethargy, 2026-09-25 (build_lethargy.py; the name is build_resstr_names.py's).
    ("Spells.pfs", 120,  10,
     "Halves the target's mobility for the duration of combat.\r\n",
     "Saps the target's vigour for the rest of combat: its movement is halved, rounded up, and "
     "it loses one melee strike when attacking and one when defending, never below one.\r\n",
     "record 120 = Slow -> Lethargy (spell 110)"),
    ("Ability.pfs", 142,  5,
     "Halves the target's mobility for the duration of combat.\r\n",
     "Movement is halved, rounded up, and one melee strike is lost when attacking and when "
     "defending, never below one.\r\n",
     "record 142 = status 0x84 (Slow -> Lethargy). NB u8 directory: tag 9 must stay at offset "
     "<= 255, so this field may grow by at most 56 B -- this text uses all of it"),

    # Haste gains a melee strike each way, 2026-09-25 (build_lethargy.py's strike caves).
    # The owner reworded "and when defending" to "or defending" in the editor, 2026-09-25.
    ("Spells.pfs",  25,  10,
     ("Allows the target unit to move at great speed.\r\n",
      "Allows the target unit to move at great speed, and to strike once more in melee when "
      "attacking and when defending.\r\n"),
     "Allows the target unit to move at great speed, and to strike once more in melee when "
     "attacking or defending.\r\n",
     "record 25 = Haste (spell 15)"),
    ("Ability.pfs", 162,  5,
     "Reduces movement cost per hex by 1.\r\n",
     "Reduces movement cost per hex by 1. One extra melee strike when attacking and when "
     "defending.\r\n",
     "record 162 = status 0x98 (Haste)"),

    # Dispel Magic wrests a bound unit from an enemy master, 2026-09-25 (build_command_bond.py).
    ("Ability.pfs",  70,  5,
     "Dispels magical enchantments.\r\n",
     "Dispels magic; wrests bound units.\r\n",
     "record 70 = Dispel Magic (ability 0x3C). NB u8 directory: tag 9 sits at offset 249, so "
     "this field may grow by at most 6 B -- this text uses 5"),
    ("Spells.pfs",  18,  10,
     "Attempts to remove enchantments from a selected unit.\r\n",
     "Attempts to remove enchantments from a selected unit, and to wrest a unit bound to an "
     "enemy from its master (Res vs Res).\r\n",
     "record 18 = Dispel Magic (spell 8)"),
]








def _pfs_mod():
    """Load re_tools/pfs.py relative to THIS SCRIPT, not to GAME.

    ⚠ `AOW_GAME_DIR` points at an install to patch; the toolkit travels with the script. Resolving
    the parser under GAME breaks the moment you point this at a throwaway copy -- which is exactly
    how it gets tested. Same rule as `TOOLS` in re_tools/*.py.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(here, "..", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --------------------------------------------------------------------------------------------
# container
# --------------------------------------------------------------------------------------------
def index_layout(d):
    """(payload_base, [(record_id, offset, offset_field_pos, width)]) for the file index.

    Probed from the bytes, never hard-coded. Mirrors re_tools/pfs.py:parse_index but also reports
    WHERE each offset lives, so the offsets after an edited record can be rewritten in place.
    """
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


def body_dir(body):
    """([(tag, offset, width)], directory_size) for a record body.

    ⚠ Bodies mix the two entry forms: `body[0]` is `small | 0x80` and, when the high bit is set, a
    `u32` wide count follows. Charm's record is exactly that shape (4 small + 1 wide), so a writer
    that only handles the pure-small form -- as build_vision9.py's deliberately does -- cannot touch
    it. Offsets are relative to the END of the directory.
    """
    n = body[0]
    p = 1
    small, wide = n & 0x7F, 0
    if n & 0x80:
        wide = struct.unpack_from("<I", body, p)[0]
        p += 4
    ent = []
    for _ in range(small):
        ent.append((body[p], body[p + 1], 1)); p += 2
    for _ in range(wide):
        t, o = struct.unpack_from("<II", body, p)
        ent.append((t, o, 4)); p += 8
    return ent, p


def slice_fields(body, ent, dsz):
    """{tag: bytes}. A field runs to the start of the next one by offset, last one to end of body."""
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    out = {}
    for j, k in enumerate(order):
        t, o, _ = ent[k]
        a = dsz + o
        b = dsz + ent[order[j + 1]][1] if j + 1 < len(order) else len(body)
        if not (dsz <= a <= b <= len(body)):
            raise ValueError("bad offset for tag %d" % t)
        out[t] = body[a:b]
    return out


def read_str(field):
    """(text, encoder) for a .pfs string field, or (None, None) when it is not one.

    The u32 arm is tried first and is self-checking -- `4 + n == len(field)` fails for a 4-byte
    integer field unless that integer is 0, and an empty string can never contain the `old`
    substring a fix looks for, so the one ambiguous case is harmless.
    """
    if len(field) >= 4:
        n = struct.unpack_from("<I", field, 0)[0]
        if 4 + n == len(field):
            return (field[4:].decode("latin-1"),
                    lambda s: struct.pack("<I", len(s)) + s.encode("latin-1"))
    if len(field) >= 1 and 1 + field[0] == len(field) and field[0] < 0x80:
        return field[1:].decode("latin-1"), lambda s: bytes([len(s)]) + s.encode("latin-1")
    return None, None


def plan(d, rec, tag, old, new):
    """Pure: (status, new_bytes, note). status in {'same', 'ok', 'error'}. Never writes."""
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return "error", None, ("CRC residue is wrong before any edit -- the file is already "
                               "damaged; refusing to rewrite it")
    # ⚠ Both parsers PROBE for the layout, so an unfamiliar file makes them RAISE rather than
    # return. That is a realistic input, not a hypothetical: AoWDevEd rewrites these files whole
    # when the author saves a map. A traceback here would be a bug report; return a readable error.
    try:
        pfs = _pfs_mod()
        recs = pfs.parse_index(bytes(d))
        base, ent = index_layout(bytes(d))
    except (ValueError, IndexError, KeyError, struct.error) as exc:
        return "error", None, (f"cannot parse the index ({exc}) -- the file's layout is not one "
                               "this script recognises, so it will not be rewritten")
    # Two independent probes for the wide-array start must agree on the record list. This checks
    # layout DISCOVERY, not data -- data integrity is the CRC above.
    if [a for a, _, _, _ in ent] != [r for r, _ in recs]:
        return "error", None, "index entry ids disagree with parse_index"

    bodies = dict(recs)
    if rec not in bodies:
        return "error", None, f"no record {rec} in this file"
    body = bodies[rec]
    rec_off = dict((a, b) for a, b, _, _ in ent)[rec]
    a0 = base + rec_off

    try:
        dents, dsz = body_dir(body)
        fields = slice_fields(body, dents, dsz)
    except (ValueError, IndexError, struct.error) as exc:
        return "error", None, f"record {rec} body does not parse ({exc})"
    if tag not in fields:
        return "error", None, f"record {rec} has no tag {tag} (has {sorted(fields)})"

    text, encode = read_str(fields[tag])
    if text is None:
        return "error", None, (f"record {rec} tag {tag} is {len(fields[tag])} B and is neither a "
                               "u32-prefixed nor a u8 Pascal string -- refusing to treat it as text")
    n_old, n_new = text.count(old), text.count(new)
    if n_new == 1 and n_old == 0:
        return "same", None, f"already reads {new!r}"
    if n_old == 0:
        return "error", None, (f"record {rec} tag {tag} contains neither {old!r} nor {new!r} -- "
                               f"the text has been edited elsewhere:\n     {text!r}")
    if n_old != 1:
        return "error", None, f"record {rec} tag {tag} contains {old!r} {n_old} times, expected 1"
    if n_new:
        return "error", None, (f"record {rec} tag {tag} contains BOTH {old!r} and {new!r} -- "
                               "ambiguous, refusing to guess")

    want = text.replace(old, new)
    field = encode(want)
    shift = len(field) - len(fields[tag])
    off_t = dict((t, o) for t, o, _ in dents)[tag]

    # --- rebuild the directory in place: only offsets AFTER the edited field move ---------------
    new_dir = bytearray(body[:dsz])
    p = 1 + (4 if body[0] & 0x80 else 0)
    for t, o, w in dents:
        v = o + shift if o > off_t else o
        if w == 1:
            if v > 0xFF:
                return "error", None, (
                    f"record {rec} tag {t} offset {v} exceeds the u8 directory ceiling (255). The "
                    "string is too long for the small-entry form; this body would have to be "
                    "converted to WIDE (u32) entries -- other records in these files already are.")
            new_dir[p + 1] = v
        else:
            struct.pack_into("<I", new_dir, p + 4, v)
        p += 2 if w == 1 else 8
    if p != dsz:
        return "error", None, "directory walk did not land on the directory end"

    # --- rebuild the payload, and assert the fields TILE it exactly -----------------------------
    # Not circular: the field lengths come from the OLD offsets, the placement from the NEW ones,
    # so an off-by-one in `shift` shows up as a gap or an overlap rather than passing quietly.
    size = len(body) - dsz + shift
    payload = bytearray(size)
    seen = bytearray(size)
    for t, o, _ in dents:
        blob = field if t == tag else fields[t]
        v = o + shift if o > off_t else o
        if v + len(blob) > size:
            return "error", None, f"record {rec} tag {t} would run past the end of the body"
        if any(seen[v:v + len(blob)]):
            return "error", None, f"record {rec} fields overlap at tag {t}"
        payload[v:v + len(blob)] = blob
        seen[v:v + len(blob)] = b"\x01" * len(blob)
    if not all(seen):
        return "error", None, f"record {rec} rebuilt payload has a {size - sum(seen)} B hole"
    new_body = bytes(new_dir) + bytes(payload)

    # --- splice, shift every later index offset, repair the CRC ---------------------------------
    out = bytearray(d)
    out[a0:a0 + len(body)] = new_body           # every index field lives below `base` <= a0
    moved = 0
    for _rid, o, pos, w in ent:
        if o <= rec_off:
            continue
        v = o + shift
        if w == 1:
            if v > 0xFF:
                return "error", None, f"index small-entry offset {v} overflows u8"
            out[pos] = v
        else:
            struct.pack_into("<I", out, pos, v)
        moved += 1
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    if zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return "error", None, "CRC repair failed (residue mismatch)"

    try:
        bad = collateral(bytes(d), bytes(out), rec, tag, want)
    except (ValueError, IndexError, KeyError, struct.error) as exc:
        return "error", None, f"the rewritten file no longer parses ({exc})"
    if bad:
        return "error", None, "collateral damage: " + bad
    return "ok", bytes(out), (f"tag {tag} {len(fields[tag])} -> {len(field)} B, record {len(body)} "
                              f"-> {len(new_body)} B, file {len(d)} -> {len(out)} B, "
                              f"{moved} later offsets {shift:+d}")


def collateral(old_d, new_d, rec, tag, want):
    """'' if the rewrite touched nothing but `tag` of record `rec`, else what else moved."""
    pfs = _pfs_mod()
    o, n = pfs.parse_index(old_d), pfs.parse_index(new_d)
    if [r for r, _ in o] != [r for r, _ in n]:
        return "record id list changed"
    last = n[-1][0]
    ob, nb = dict(o), dict(n)
    for rid in ob:
        a, b = ob[rid], nb[rid]
        if rid == last:                 # the final body swallows the 4-byte trailing CRC
            a, b = a[:-4], b[:-4]
        if rid != rec and a != b:
            return f"record {rid} changed ({len(a)} -> {len(b)} B)"
    for rid, b in n:                    # everything must still parse
        try:
            e, s = body_dir(b)
            slice_fields(b, e, s)
        except (ValueError, IndexError, struct.error) as exc:
            return f"record {rid} no longer parses ({exc})"
    eo, so = body_dir(ob[rec]); f_old = slice_fields(ob[rec], eo, so)
    en, sn = body_dir(nb[rec]); f_new = slice_fields(nb[rec], en, sn)
    if sorted(f_new) != sorted(f_old):
        return f"record {rec} tags became {sorted(f_new)}, were {sorted(f_old)}"
    for t in f_old:
        if t != tag and f_old[t] != f_new[t]:
            return f"record {rec} tag {t} changed ({f_old[t].hex()} -> {f_new[t].hex()})"
    got, _ = read_str(f_new[tag])
    if got != want:
        return f"record {rec} tag {tag} did not round-trip"
    return ""


# --------------------------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------------------------
def olds_of(old):
    """`old` may be a single string OR a tuple of accepted pre-states.

    A tuple is what a RE-TUNED row needs: element 0 is always the vanilla text (what `--undo`
    restores, so provenance is never lost), and the rest are texts this field has held on the way
    here. Without it, changing a full-text row's `new` bricks the table -- an already-patched file
    then matches neither the row's `old` nor its `new`, and `plan()` correctly refuses to guess,
    which aborts every fix for that file. That is the .pfs twin of the cave rule in CLAUDE.md:
    verify against the currently-installed value OR the new one.
    """
    return old if isinstance(old, tuple) else (old,)


DIGITS = re.compile(r"\d+")


def _nums(s):
    return DIGITS.findall(s)


def _shape(s):
    """The string with every number blanked -- two strings share a shape iff only digits differ."""
    return DIGITS.sub("#", s)


def _retarget(text, nums):
    """Replace the Nth number in `text` with nums[N]; every other character survives untouched."""
    it = iter(nums)
    return DIGITS.sub(lambda m: next(it), text)


def field_text(d, rec, tag):
    """The record's current text, or None if anything is unfamiliar. Never raises."""
    try:
        recs = dict(_pfs_mod().parse_index(bytes(d)))
        dents, dsz = body_dir(recs[rec])
        text, _ = read_str(slice_fields(recs[rec], dents, dsz)[tag])
        return text
    except Exception:
        return None


def number_sync(d, rec, tag, olds, new):
    """NUMBER MODE -- match on the NUMERALS, not the prose.

    75 of the 95 rows below differ from their `old` only in digits. What such a row actually
    asserts is "this description must state the value the binary holds"; the sentence around the
    number is the author's business, not this table's. Matching full text made every wording edit
    in AoWDevEd a hard failure -- on 2026-09-14 a pure case change (`DEF/RES` -> `Def/Res`, no
    digit touched) blocked all 80 `Ability.pfs` rows, because `process()` abandons the whole file
    on one unmatched row. The author using the game's own editor must not be a breaking event.

    Tried only AFTER full-text matching has failed, so a clean tree behaves exactly as before.
    Returns (status, old_sub, new_sub) or None when the row is not eligible. Deliberately narrow:

      * the row must be digits-only (same `_shape`), so a row that rewrites prose -- Grip of
        Winter, Power Leech, the Spellcasting correction -- can never land here;
      * the live text must carry the SAME COUNT of numbers, so a rewording that adds or removes
        one stays a hard failure rather than a positional guess;
      * the live numbers must equal the target (already applied) or one of the accepted
        pre-states. Anything else means the author changed a VALUE, which is precisely the
        text-vs-binary disagreement this table exists to catch: report it, never overwrite it.
    """
    text = field_text(d, rec, tag)
    if text is None:
        return None
    if not [o for o in olds if _shape(o) == _shape(new)]:
        return None
    cur, tgt = _nums(text), _nums(new)
    if cur == tgt:
        return "same", None, None
    if len(cur) != len(tgt) or not any(cur == _nums(o) for o in olds):
        return None
    return "ok", text, _retarget(text, tgt)


def validate_table():
    for fname, rec, tag, old, new, what in FIXES:
        for cand in olds_of(old):
            if cand == new:
                raise SystemExit(f"[x] {what}: old and new are identical")
            if cand in new or new in cand:
                raise SystemExit(f"[x] {what}: {cand!r} and {new!r} are substrings of each other, "
                                 "so 'already applied?' cannot be answered -- widen both to a phrase")


def process(fname, commit, undo, dis):
    """Plan (and optionally write) every fix for one file. Returns (ok, pending, wrote)."""
    path = os.path.join(GAME, "Release", fname)
    if not os.path.exists(path):
        print(f"[x] missing {path}")
        return False, False, False
    rows = [f for f in FIXES if f[0] == fname]
    orig = open(path, "rb").read()

    d = orig
    plans = []
    skipped = []
    for _f, rec, tag, old, new, what in (reversed(rows) if undo else rows):
        if undo:
            # element 0 is the vanilla text -- undo always lands back there, never on an
            # intermediate state the field passed through.
            a, b = new, olds_of(old)[0]
            status, out, note = plan(d, rec, tag, a, b)
        else:
            # try each accepted pre-state; the first that plans (or is already the target) wins.
            for cand in olds_of(old):
                a, b = cand, new
                status, out, note = plan(d, rec, tag, a, b)
                if status != "error":
                    break
            if status == "error":
                ns = number_sync(d, rec, tag, olds_of(old), new)
                if ns and ns[0] == "same":
                    status, out = "same", None
                    note = ("numerals already %s -- the prose differs from the table and that is "
                            "the author's to keep" % "/".join(_nums(new)))
                elif ns:
                    a, b = ns[1], ns[2]
                    status, out, note = plan(d, rec, tag, a, b)
                    if status == "ok":
                        note = ("NUMBER MODE: prose differs from the table, syncing only the "
                                "numerals -> %s" % "/".join(_nums(new)))
        if status == "error":
            # ⚠ Do NOT abandon the file. One row the table no longer recognises used to return
            # here, blocking the other 79 -- see number_sync(). A row that cannot be matched is
            # reported loudly and skipped; the rest still apply.
            skipped.append((rec, tag, what, note))
            continue
        plans.append((what, rec, tag, a, b, status, note))
        if status == "ok":
            d = out

    for what, rec, tag, a, b, status, note in plans:
        mark = "[= ]" if status == "same" else "[pfs]"
        print(f"{mark} {fname} rec {rec} tag {tag}  {what}: {note}")
        if dis and status == "ok":
            print(f"        - {a!r}\n        + {b!r}")

    if skipped:
        # Every row unmatched means the FILE is the problem (bad CRC, an index layout the parsers
        # do not recognise) rather than a few drifted strings -- that is still a hard failure.
        if len(skipped) == len(rows):
            print(f"[x] {fname}: not one of its {len(rows)} rows matches -- treating this as a "
                  f"file-level failure, nothing written")
            for rec, tag, what, note in skipped:
                print(f"       rec {rec} tag {tag}: {note}")
            return False, False, False
        print(f"[!] {fname}: {len(skipped)} of {len(rows)} rows SKIPPED -- the text on disk matches "
              f"neither the table's `old` nor its `new`, and the numerals could not be synced "
              f"either. The other {len(rows) - len(skipped)} rows were still processed.")
        for rec, tag, what, note in skipped:
            print(f"       rec {rec} tag {tag}  {what}")
            print(f"         {note.splitlines()[0]}")
        print("       Reconcile by adding the on-disk text to that row's `old` tuple, or by "
              "updating its `new` if the wording is now authoritative.")

    if d == orig:
        return True, False, False
    print(f"[pfs] collateral check: {len(_pfs_mod().parse_index(d))} records parse, all but the "
          f"edited ones byte-identical, CRC residue {PFS_RESIDUE:#010X} OK")
    if not commit:
        return True, True, False

    # Snapshot only from a file where NO fix has been applied yet, and never overwrite an existing
    # one. ⚠ Both halves matter: once the table grows, a later --apply runs against an already
    # patched file, and re-taking the backup then would produce the "a .pre-* file is not proof of
    # anything" artefact CLAUDE.md warns about -- one that sits on disk looking authoritative.
    bp = os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)
    # ⚠ `not skipped` is load-bearing: a skipped row means the file holds text this table cannot
    # account for, so it is NOT the clean pre-patch state a `.pre-typos` name claims.
    if (not undo and not skipped and not os.path.exists(bp)
            and all(s == "ok" for *_x, s, _n in plans)):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, bp)
        print(f"[bak] {os.path.basename(bp)}")
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(d)
    os.replace(tmp, path)
    print(f"[ok ] wrote {path} ({len(orig)} -> {len(d)} B)")
    return True, True, True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the files (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="put the original wording back")
    ap.add_argument("--dis", action="store_true", help="print the before/after strings")
    a = ap.parse_args()
    validate_table()

    ok_all, pending_any, wrote_any = True, False, False
    for fname in dict.fromkeys(f[0] for f in FIXES):
        ok, pending, wrote = process(fname, a.apply, a.undo, a.dis)
        ok_all &= ok
        pending_any |= pending
        wrote_any |= wrote
    if not ok_all:
        raise SystemExit(1)
    if not wrote_any:
        flag = "--undo --apply" if a.undo else "--apply"
        print(f"[i  ] re-run with {flag} to write" if pending_any else
              "[i  ] nothing to do -- already in the target state")


if __name__ == "__main__":
    main()
