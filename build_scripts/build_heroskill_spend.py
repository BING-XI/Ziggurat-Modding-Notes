#!/usr/bin/env python3
r"""build_heroskill_spend.py -- spend the hero library's hoarded skill points.

DATA EDIT ONLY. No binary is patched; `AoWEPACK.dpl` is opened read-only, purely to re-assert the
constants the arithmetic depends on.

TARGET: `User/Ziggurat Heroes.ahl` -- the Ziggurat hero library, 50 heroes.
ALSO:   `Ziggurat release/User/Ziggurat Heroes.ahl`, but ONLY while it is byte-identical to the
        pre-edit target (it is, today). If it has drifted, it is skipped with a warning.
NOT TOUCHED: `User/Special Heroes.ahl`, `Release/HEROES.PFS`, `Ziggurat upload/`.

================================================================================
THE PROBLEM
================================================================================
Every hero in the library carries `GetSkillPoints() = level*10 + 10 - used - writeoff` unspent
points -- 589 across the 50, up to 26 on one hero. A hero recruited from this library therefore
arrives with a pile of free level-ups the player never earned, and the engine nags
("NotAllSkillPointsAssigned") until they are assigned.

THE FIX (user decision 2026-09-08). Per hero:
    left    = level*10 + 10 - used                (writeoff = tag 0x27, absent everywhere here)
    drop    = left // 10
    newLevel= max(1, level - drop)                -- floor at 1, then spend the whole residue
    rem     = left - 10*(level - newLevel)
    rem is spent on HP (2 pts each) and ATK (3 pts each).
Result: 47 heroes end on 0 unspent, 3 on 1 (rem == 1 buys nothing -- HP costs 2). Total 589 -> 3.

--------------------------------------------------------------------------------
SPLIT POLICY -- "alternate HP/ATK" (user decision 2026-09-08)
--------------------------------------------------------------------------------
Formally: over all (hp, atk) with 2*hp + 3*atk <= rem, minimise leftover first, then |hp - atk|,
tie-breaking toward more HP. Leftover is 0 for every rem >= 2 and 1 only at rem == 1.

That policy's FINGERPRINT -- asserted by `policy_selftest()` on every run:

    rem  1 -> -            rem  6 -> ATK+2
    rem  2 -> HP+1         rem  7 -> HP+2 ATK+1
    rem  3 -> ATK+1        rem  8 -> HP+1 ATK+2
    rem  4 -> HP+2         rem  9 -> HP+3 ATK+1
    rem  5 -> HP+1 ATK+1

The level floor never engages on today's data (the deepest drop is level 3 -> 1); the code
implements it anyway and prints a LOUD line for any hero that hits it, because such a hero would
be spending more than 9 points on stats and could plausibly run into a cap.

================================================================================
WHERE THE NUMBERS COME FROM -- all re-read from the live DLL on every run
================================================================================
`AoWE.THero.GetSkillPoints @0x557875C4`
    budget = level*10 + 10, at THREE `add reg, 0Ah` sites (vanilla was +15):
    0x557875EF (mapped path), 0x5578760C (no-map path), 0x55787620 (`GetSkillPointsMax`).
    It reads the level from the CACHE `[hero+0x4C]` (tag 0x16), not from XP -- which is exactly
    why both must be written.  `left` also subtracts `[hero+0x50]` = tag 0x27.

`AoWE.THero.UsedSkillPoints @0x55786CC8`
    used = 3*ATK(+0x6A) + 6*DEF(+0x6B) + 4*DAM(+0x6C) + 2*RES(+0x6F) + 2*HP(+0x6D) + 3*MOV(+0x6E)
    (MOV lives in cave 0x5580C800, called from 0x55786CFA -- `imul eax,eax,3`)
    then, per ability id the hero has:  + Ability.GetSkillPoints(hero)
    and, if the CHASSIS has it too:     - Ability.GetSkillPoints(chassisOwner)
    ⚠ the ability entry point is VMT +0x80 `GetSkillPoints`, NOT +0xC8 `ExpandCost`.

Level <-> XP.  `GetLevel = ExperienceToLevel([hero+0x48])`; `[hero+0x4C]` is only a cache that
`SetLevel @0x55787750` writes alongside `[hero+0x48]`.  So this script writes BOTH tag 0x16 and
tag 0x18 = LevelToExperience(newLevel).
    LevelToExperience(L) = sum over k=1..L-1 of table[k div 5], terms with (k div 5) > 5 skipped.
    ExperienceToLevel  has NO >5 guard -- it walks off the end of the table. The two are NOT
    inverses above level 30 and must not share an implementation.
    `HeroExperienceTable` XP column: `AoWEPACK.dpl @0x558E84B8`, stride 8, live = 20,30,40,50,60,70
    (vanilla was 15,15,20,20,25,25). Read live; never hard-coded.
    => level 1..7 <-> XP 0, 20, 40, 60, 80, 110, 140.

Caps, checked before any write: ATK `cmp edx,28h` @0x557877D6 (40), HP `cmp edx,64h` @0x557878BA
(100), both against `chassis + bought` where chassis ATK = `[[hero+0x40]+0x24]` (HERORES tag 0x0F)
and chassis HP = `[[hero+0x40]+0x27]` (HERORES tag 0x12). Worst case after this edit is ATK 10/40
and HP 29/100, so there is plenty of room -- but see DO-NOT #6 for why the check is not optional.

--------------------------------------------------------------------------------
MULTI-LEVEL ABILITY COSTS -- four in this library, none readable from Ability.pfs
--------------------------------------------------------------------------------
`TMultiLevelAbility.GetSkillPoints @0x55765348` looks like a sum but is not: the loop re-reads
`list[level]` `level` times, so it returns **cost * abilityLevel**, not sum(1..level). Every entry
of each ability's cost list holds the same constant, written by a cave:

    Vision       id 64  cost  4  levels 1..9   cave 0x55817000 (build_vision9.py)
    Marksmanship id 32  cost  6  levels 1..8   cave 0x55817400 (build_marksmanship8.py)
    Leadership   id 46  cost 10  levels 1..4   cave 0x5580EFC0 (build_leadership4.py)
    Spell Casting id 52 cost 20  levels 1..5   inline, `TSpellCastingAbility.Create` 0x5576DBE1

⚠ DO NOT read these from `Ability.pfs` tag 6 -- it is inert for multi-level abilities and WRONG:
   Leadership tag 6 = 20 (live 10), Spell Casting tag 6 = 15 (live 20).
⚠ DO NOT read Leadership's cost from the constructor immediate at 0x55766195 (`mov ecx,14h`). That
   instruction is DEAD -- the `call` after it, at 0x557661A2, was retargeted to cave 0x5580EFC0.
   ⚠ PRISTINE READS 10 THERE; only the LIVE file reads 20 -- the 20 is an earlier, unrecorded
   Ziggurat edit of that dead immediate (byte-checked 2026-09-10). Either way the answer is 10,
   from the cave -- but do not reach for the pristine DLL expecting to see 20.
Single-level abilities DO use `Ability.pfs` tag 6 (`TAbility.GetSkillPoints @0x5574E958` returns
`[ability+0x14]`), and every one in this library has it.

`TAbilityOwner.UpdateDefaultAbilities @0x5574F518`, run from `THero.Loaded` on every load, copies
each chassis ability (and its level record) onto the hero wherever the hero's level is lower. So
the effective hero level for a chassis ability is max(heroLevel, chassisLevel), and the chassis
credit always cancels exactly. This script models the max(); on today's data it is a no-op (chassis
set is a subset of the hero set on all 50, and heroLevel >= chassisLevel everywhere), and the
script asserts that the plain subtraction agrees.

================================================================================
FILE FORMAT -- `.ahl`, same container family as `.pfs` (see re_tools/pfs.py)
================================================================================
Directory shape everywhere: `<u8 n>[<u32 wide_count>](u8 key,u8 off)*(u32 key,u32 off)*<payload>`,
offsets relative to the END of that directory.

    0x0000  01 (00,00)                            outer: 1 small entry, key 0, payload @0x0003
    0x0003  03 (0x14,0x00)(0x15,0x10)(0x01,0x14)  THeroLibrary body, payload @0x000A
    0x000A  tag 0x14 = Pascal string "Ziggurat Heroes"
    0x001A  tag 0x15 = 0x36 = 54   <-- NEXT-UNIQUE-ID COUNTER, *not* a hero count
    0x001E  tag 0x01 = child list: 0x82 -> 2 small + u32 48 wide = 50 children, payload @0x01A7

Tag 0x01 is the LAST field of the library body, so growing the child list moves nothing above it.
Each child is `<u32 ClassID = 0x00020230 (THero)><directory><payload>`; ids 0..49; 423-byte header
+ 8197 bytes of records = 8620. No magic, no CRC -- NEVER stamp one.

Hero tags, from `THero.ReadWrite @0x55788880` (tag -> THero field offset):
    0x07->+0x3C  0x08->+0x44 hero-resource index  0x0A->+0x60 name  0x0B->+0x64 nickname
    0x0C->+0x68  0x0F->+0x69
    0x10->+0x6A ATK  0x11->+0x6B DEF  0x12->+0x6C DAM  0x13->+0x6D HP  0x14->+0x6E MOV
    0x15->+0x6F RES        <-- all six are PURCHASED DELTAS, 1 signed byte each
    0x16->+0x4C LEVEL CACHE (1B)   0x17->+0x54   0x18->+0x48 EXPERIENCE (4B)   0x19->+0x55
    0x1A->+0x58  0x1B->+0x5C  0x1D->+0x79  0x1E->+0x7A  0x1F->+0x88  0x21->+0x78  0x22->+0x8C
    0x23 library id  0x24 inventory  0x25 items  0x26 library name  0x27->+0x50 skill write-off
Abilities come from `TAbstractUnit.ReadWrite @0x557820E4` / `TAbilityOwner.ReadWrite @0x5574F318`:
tag 0x02 bit count, 0x03 bitset (LSB-first, bit index == ability id), 0x31 the TIntegerList of ids
that own a data sub-record, and per-ability sub-records at `tag = id + 0x32` with the level at
inner tag 0x0A.

The chassis is `HERORES.PFS` at the index in tag 0x08 (`GetHeroResource` indexes the list by
POSITION; ids 0..11 are contiguous and every hero here uses 0..11, so position == id). Six heroes
carry no tag 0x08 at all -- `THero.Create` leaves `[hero+0x44]` at 0, so their chassis is index 0,
"Human". Its ability owner is that record's tag 0x1D, a `top=False` directory.
Stats are deltas: `GetInherentAttack @0x55788354` = chassis[+0x24] + hero[+0x6A], and so on.

================================================================================
DO NOT -- recorded failures, each of which has cost real time
================================================================================
1. DO NOT re-derive a record directory; APPEND ONLY. `build_item_hpmv_data.py` proved the engine's
   writer picks entry widths and order by nothing recoverable from the data: a "small entry if the
   offset fits, in payload order" rebuild produced a valid-LOOKING record 10 bytes shorter with a
   reordered directory. Copy every existing (key, offset) verbatim, append new ones at the payload
   tail, and bump only the child-list offsets. Offsets are relative to the directory END, so
   appending an entry moves no existing field byte.
2. An ABSENT tag means zero, so raising a stat on a hero that has no such tag INSERTS one (tag 0x10
   present in 28 of 50, tag 0x13 in 33). Headroom is asserted, not assumed: max field offset today
   is 0x7E and max payload 0x8E, so u8 field offsets survive; the child list's two small entries
   sit at 0 and 171, and record 0 does not grow at all here (it is in both HAS_ sets).
3. DO NOT read a multi-level ability's cost from `Ability.pfs` tag 6, and DO NOT read Leadership's
   from 0x55766195. See the section above.
4. DO NOT derive the level from tag 0x16, and DO NOT write 0x16 or 0x18 alone -- `SetLevel` writes
   both, `GetLevel` reads XP, `GetSkillPoints` reads the cache. (On this file they happen to agree
   on all 50; the script asserts it rather than trusting it.)
5. DO NOT stamp a `.pfs`/`hss_crc.py` checksum. This container has none.
6. DO NOT rely on the engine to correct an over-spend. `THero.Loaded @0x5578799C` re-runs every
   setter with `value == current`; `cmp bl, [esi+0x6a] / jle` takes the free branch and skips the
   budget check entirely -- but the cap clamp above it still fires, so an over-cap stat is
   SILENTLY TRUNCATED with no error. Hence the pre-write cap assertions.
7. The game and the editor REWRITE this file (`THeroLibraryManager.WriteUserLibraries`). Anything
   running when you apply will overwrite the edit on exit -- `kill_aow()` handles that.

================================================================================
SELF-TESTS -- all run before anything is written; any failure aborts with nothing written
================================================================================
  * live-constant guard: 25 byte-runs in `AoWEPACK.dpl` (prices, budget, caps, cave costs and the
    three retargeted call/jmp links), plus the six-entry experience table;
  * the plan is RE-DERIVED from the clean bytes + HERORES.PFS + Ability.pfs + those live constants
    and asserted equal to the PLAN table below, which is therefore a fingerprint, not an input;
  * the split policy is asserted against its fingerprint table;
  * container assertions: 423 + sum(record lengths) == filesize, no `1C DF 44 21` magic, no
    trailing bytes, ClassID 0x00020230 on all 50, offsets fit their entry widths;
  * apply -> undo is computed IN MEMORY and asserted byte-identical to the clean input;
  * every hero's post-edit `left` is recomputed and asserted to be 0 or 1;
  * caps: chassisATK + boughtATK <= 40, chassisHP + boughtHP <= 100.

USAGE
    python build_scripts/build_heroskill_spend.py            verify / dry run  (writes nothing)
    python build_scripts/build_heroskill_spend.py --list     the full per-hero table
    python build_scripts/build_heroskill_spend.py --apply
    python build_scripts/build_heroskill_spend.py --undo     surgical: restores levels, XP and the
                                                             stat deltas, removes inserted tags

Backup (a convenience, NOT the revert path -- `--undo` is):
    <game dir>\backups\Ziggurat Heroes.ahl.pre-heroskill
It is minted only when the target is proved CLEAN, so `--undo` and a re-tune can never mint a
snapshot of an already-edited file.
"""

import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
from build_statdouble import kill_aow                                          # noqa: E402
import pfs                                                                     # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
AHL = os.path.join(GAME, "User", "Ziggurat Heroes.ahl")
REL = os.path.join(GAME, "Ziggurat release", "User", "Ziggurat Heroes.ahl")
DLL = os.path.join(GAME, "AoWEPACK.dpl")

BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(AHL) + ".pre-heroskill")

THERO_CLASSID = 0x00020230
TOP_WORD = 4                       # ClassID before each hero body

T_ATK, T_DEF, T_DAM, T_HP, T_MOV, T_RES = 0x10, 0x11, 0x12, 0x13, 0x14, 0x15
T_LEVEL, T_XP, T_WRITEOFF = 0x16, 0x18, 0x27
T_CHASSIS, T_BITCOUNT, T_BITSET, T_DATAIDS = 0x08, 0x02, 0x03, 0x31
ABILITY_SUBRECORD_BASE = 0x32      # sub-record tag = ability id + 0x32
T_SUB_LEVEL = 0x0A                 # TMultiLevelAbilityData level

PRICE_ATK, PRICE_HP = 3, 2         # what a point of each costs in UsedSkillPoints

# ---------------------------------------------------------------------------------------------
# THE PLAN -- rid: (oldLevel, newLevel, oldATK, newATK, oldHP, newHP)
# A FINGERPRINT, not an input: `derive_plan()` rebuilds this from the clean bytes and the live
# constants on every run and aborts if it does not match.
# ---------------------------------------------------------------------------------------------
PLAN = {
     0: (5, 4,  3,  3,  1,  1),   # Acara the Spider          (1 point left over: rem was 1)
     1: (3, 2,  2,  2,  2,  2),   # Alexandra Lifestealer
     2: (3, 2,  0,  2,  3,  4),   # Arnus Ironshod
     3: (2, 1,  1,  1,  2,  2),   # Atam the Righteous        (1 point left over)
     4: (3, 2,  0,  0,  2,  4),   # Azktor the Unholy
     5: (4, 4,  1,  2,  0,  3),   # Bandir the Fiery
     6: (3, 3,  1,  2,  0,  3),   # Bjern Wolfsong
     7: (3, 1,  0,  0,  1,  1),   # Borak the Brute
     8: (5, 5,  0,  2,  0,  0),   # Caspar the Pious
     9: (3, 2,  2,  4,  0,  1),   # Conan McHarr
    10: (3, 3,  0,  0,  2,  4),   # Dactor Deathbringer
    11: (5, 3,  2,  4,  4,  4),   # Danto Dragonslayer
    12: (3, 3,  1,  2,  2,  5),   # One-Eye the Old
    13: (3, 3,  0,  2,  1,  1),   # Eclo Frostbite
    14: (5, 3,  2,  2,  2,  4),   # Esmeralda the Healer
    15: (3, 3,  2,  4,  1,  2),   # Fakana Poisoner
    16: (3, 1,  0,  0,  5,  5),   # Forok the Bloated
    17: (7, 7,  0,  0,  0,  2),   # Freya the Seer
    18: (3, 2,  1,  1,  1,  1),   # Gorthak the Black         (1 point left over)
    19: (6, 4,  0,  0,  8,  9),   # Ham Binger
    20: (6, 6,  1,  2,  0,  0),   # Igor the Lich
    21: (5, 4,  2,  2,  1,  3),   # Isabelle the Serene
    22: (3, 2,  0,  0,  5,  7),   # Jacob the Noble
    23: (5, 4,  1,  2,  2,  2),   # Jattah the Leper
    24: (4, 4,  1,  2,  0,  0),   # Jiswyn Treesong
    25: (4, 3,  0,  0,  2,  4),   # Karum the Mighty
    26: (2, 1,  0,  0,  2,  4),   # Katar the Gladiator
    27: (5, 3,  2,  2,  0,  0),   # Khabar Eagle Eye
    28: (4, 4,  1,  2,  3,  6),   # Lily Whiteleaf
    29: (4, 3,  1,  2,  2,  5),   # Lingolas the Hermit
    30: (7, 6,  0,  0,  6,  7),   # Makai the Preacher
    31: (3, 2,  1,  2,  3,  4),   # Menfir Oakleaf
    32: (7, 7,  0,  2,  4,  5),   # Meridon the Wise
    33: (4, 4,  1,  2,  0,  1),   # Namru the Forsaken
    34: (7, 6,  0,  0,  0,  2),   # Norshin War Priest
    35: (3, 2,  0,  0,  0,  1),   # Resh Redhead
    36: (5, 5,  0,  0,  1,  2),   # Roderick Nightrunner
    37: (4, 3,  2,  2,  0,  0),   # Sha-rah Sundance
    38: (2, 2,  1,  2,  0,  3),   # Shai Eggbuster
    39: (4, 4,  1,  2,  0,  0),   # Sister Tersia
    40: (6, 6,  1,  2,  1,  2),   # Sondra the Priestess
    41: (5, 4,  0,  0,  1,  1),   # Tanaris the Knowing
    42: (3, 2,  0,  0,  1,  1),   # Tarash the Shaman
    43: (5, 4,  2,  2,  2,  2),   # Thomac Stonecrusher
    44: (3, 2,  0,  2,  0,  0),   # Tirlas Nightguard
    45: (4, 3,  0,  0,  2,  4),   # Tondor Grimstone
    46: (4, 4,  3,  4,  0,  3),   # Vandir Soulslayer
    47: (5, 5,  0,  0,  0,  0),   # Vn'nih the Odd            (already exactly on budget)
    48: (6, 5,  1,  2,  2,  5),   # Winger Lightfinger
    49: (4, 2,  1,  2,  4,  4),   # Zodar Banesword
}

# Which records carry the stat tag in the PRISTINE file. Anything outside these sets and given a
# non-zero new value gets the tag INSERTED, and `--undo` removes exactly those again.
HAS_ATK_TAG = frozenset([0, 1, 3, 5, 6, 9, 11, 12, 14, 15, 18, 20, 21, 23, 24, 27, 28, 29, 31,
                         33, 37, 38, 39, 40, 43, 46, 48, 49])
HAS_HP_TAG = frozenset([0, 1, 2, 3, 4, 7, 10, 11, 12, 13, 14, 15, 16, 18, 19, 21, 22, 23, 25, 26,
                        28, 29, 30, 31, 32, 36, 40, 41, 42, 43, 45, 48, 49])

# The split policy's fingerprint: rem -> (+HP, +ATK). Asserted, not consulted.
POLICY_FINGERPRINT = {0: (0, 0), 1: (0, 0), 2: (1, 0), 3: (0, 1), 4: (2, 0), 5: (1, 1),
                      6: (0, 2), 7: (2, 1), 8: (1, 2), 9: (3, 1)}

# Multi-level abilities: id -> (name, cost VA, expected cost, max level). The cost is READ from the
# DLL at these VAs; the numbers here are only what the guard asserts.
MULTI_LEVEL = {
    64: ("Vision",        0x5581700C,  4, 9),
    32: ("Marksmanship",  0x5581740C,  6, 8),
    46: ("Leadership",    0x5580EFCE, 10, 4),
    52: ("Spell Casting", 0x5576DBE2, 20, 5),
}

XP_TABLE_VA = 0x558E84B8           # HeroExperienceTable XP column, stride 8, six entries
XP_TABLE_STRIDE = 8
XP_TABLE_N = 6
EXPECTED_XP_TABLE = (20, 30, 40, 50, 60, 70)

CAP_ATK, CAP_HP = 40, 100

# (VA, expected bytes, what it proves).  Byte RUNS, not bare immediates: each price is bound to the
# field offset it multiplies, so a field move cannot slip past the guard.
GUARD = [
    (0x557875ED, "83 C0 0A",                   "GetSkillPoints: add eax,0Ah   (budget = L*10+10)"),
    (0x5578760A, "83 C0 0A",                   "GetSkillPoints no-map path: add eax,0Ah"),
    (0x5578761E, "83 C2 0A",                   "GetSkillPointsMax: add edx,0Ah"),
    (0x55786CCD, "0F BE 46 6A 6B F8 03",       "UsedSkillPoints: ATK [+6A] * 3"),
    (0x55786CD4, "0F BE 46 6B 6B C0 06",       "UsedSkillPoints: DEF [+6B] * 6"),
    (0x55786CDD, "0F BE 46 6C 90 90 6B C0 04", "UsedSkillPoints: DAM [+6C] * 4"),
    (0x55786CE8, "0F BE 46 6F 6B C0 02",       "UsedSkillPoints: RES [+6F] * 2"),
    (0x55786CF1, "0F BE 46 6D 6B C0 02",       "UsedSkillPoints: HP  [+6D] * 2"),
    (0x5580C800, "0F BE 46 6E 6B C0 03 C3",    "MOV cave: MOV [+6E] * 3"),
    (0x5581700B, "B9 04 00 00 00",             "Vision cave: mov ecx,4"),
    (0x55817016, "83 FF 09",                   "Vision cave: levels 1..9"),
    (0x557B9890, "C7 46 0C 40 00 00 00",       "Vision ctor: ability id 64"),
    (0x557B9889, "C7 46 28 09 00 00 00",       "Vision ctor: max level 9"),
    (0x5581740B, "B9 06 00 00 00",             "Marksmanship cave: mov ecx,6"),
    (0x55817416, "83 FF 08",                   "Marksmanship cave: levels 1..8"),
    (0x557BBD4F, "C7 46 0C 20 00 00 00",       "Marksmanship ctor: ability id 32"),
    (0x557BBD60, "C7 46 28 08 00 00 00",       "Marksmanship ctor: max level 8"),
    (0x5580EFCD, "B9 0A 00 00 00",             "Leadership cave: mov ecx,0Ah"),
    (0x5580EFD8, "83 FE 04",                   "Leadership cave: levels 1..4"),
    (0x55766187, "C7 46 28 04 00 00 00",       "Leadership ctor: max level 4"),
    (0x5576618E, "C7 46 0C 2E 00 00 00",       "Leadership ctor: ability id 46"),
    (0x5576DBAC, "C7 46 0C 34 00 00 00",       "Spell Casting ctor: ability id 52"),
    (0x5576DBDA, "C7 46 28 05 00 00 00",       "Spell Casting ctor: max level 5"),
    (0x557877CB, "8B 46 40 8A 40 24",          "SetUnitAttack: chassis ATK at chassis+0x24"),
    (0x557877D6, "83 FA 28",                   "SetUnitAttack: cap 40"),
    (0x557877F0, "83 E8 03",                   "SetUnitAttack: a point of ATK costs 3"),
    (0x557878AF, "8B 46 40 8A 40 27",          "SetUnitHits: chassis HP at chassis+0x27"),
    (0x557878BA, "83 FA 64",                   "SetUnitHits: cap 100"),
    (0x557878D4, "83 E8 02",                   "SetUnitHits: a point of HP costs 2"),
]

# rel32 links that must still point at the cost caves (call/jmp VA -> target).
GUARD_LINKS = [
    (0x557B9897, 0xE9, 0x55817000, "Vision ctor tail-jmp -> cave"),
    (0x557BBD67, 0xE9, 0x55817400, "Marksmanship ctor tail-jmp -> cave"),
    (0x557661A2, 0xE8, 0x5580EFC0, "Leadership ctor call -> cave (0x55766195 is DEAD code)"),
    (0x55786CFA, 0xE8, 0x5580C800, "UsedSkillPoints -> MOV cost cave"),
]

# The five per-level Spell Casting writes, `mov ecx,14h` every 0x12 bytes from here.
SPELLCAST_FIRST, SPELLCAST_STRIDE, SPELLCAST_LEVELS = 0x5576DBE1, 0x12, 5


# =============================================================================================
# PE helpers -- VA -> file offset is PER SECTION in AoWEPACK.dpl, never a flat delta
# =============================================================================================
def pe_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    base = struct.unpack_from("<I", d, e + 24 + 28)[0]
    tab = e + 24 + opt
    out = []
    for i in range(nsec):
        o = tab + 40 * i
        vsz, va, rsz, ptr = struct.unpack_from("<IIII", d, o + 8)
        out.append((base + va, max(vsz, rsz), ptr))
    return out


def va2off(secs, va):
    for sva, size, ptr in secs:
        if sva <= va < sva + size:
            return ptr + (va - sva)
    raise ValueError("VA %08X is in no section" % va)


class Constants(object):
    """Everything the arithmetic needs, read out of the live DLL."""

    def __init__(self, dll_bytes):
        d = dll_bytes
        secs = pe_sections(d)
        problems = []

        for va, hexs, why in GUARD:
            want = bytes.fromhex(hexs.replace(" ", ""))
            got = d[va2off(secs, va):va2off(secs, va) + len(want)]
            if got != want:
                problems.append("  %08X  %s\n      expected %s\n      found    %s"
                                % (va, why, hexs, got.hex(" ").upper()))

        for va, opc, target, why in GUARD_LINKS:
            o = va2off(secs, va)
            rel = struct.unpack_from("<i", d, o + 1)[0]
            if d[o] != opc or va + 5 + rel != target:
                problems.append("  %08X  %s\n      expected %02X -> %08X, found %02X -> %08X"
                                % (va, why, opc, target, d[o], va + 5 + rel))

        for k in range(SPELLCAST_LEVELS):
            va = SPELLCAST_FIRST + SPELLCAST_STRIDE * k
            o = va2off(secs, va)
            if d[o] != 0xB9 or struct.unpack_from("<I", d, o + 1)[0] != 20:
                problems.append("  %08X  Spell Casting level %d cost is not 20" % (va, k + 1))

        self.xp_table = tuple(
            struct.unpack_from("<I", d, va2off(secs, XP_TABLE_VA + XP_TABLE_STRIDE * i))[0]
            for i in range(XP_TABLE_N))
        if self.xp_table != EXPECTED_XP_TABLE:
            problems.append("  %08X  HeroExperienceTable XP column\n      expected %s\n"
                            "      found    %s" % (XP_TABLE_VA, EXPECTED_XP_TABLE, self.xp_table))

        self.multi_cost = {}
        for aid, (name, va, want, maxlvl) in MULTI_LEVEL.items():
            got = struct.unpack_from("<I", d, va2off(secs, va))[0]
            self.multi_cost[aid] = got
            if got != want:
                problems.append("  %08X  %s cost: expected %d, found %d" % (va, name, want, got))

        if problems:
            raise ValueError("live-constant guard failed -- the DLL moved under this script:\n"
                             + "\n".join(problems))

    # -- level <-> XP.  Two directions, two implementations: ExperienceToLevel has no >5 guard.
    def level_to_experience(self, level):
        """`THero.LevelToExperience @0x557876A0`."""
        total = 0
        for k in range(1, level):
            if k // 5 <= 5:
                total += self.xp_table[k // 5]
        return total

    def experience_to_level(self, xp, level_max=50):
        """`THero.ExperienceToLevel @0x557876D4`. No >5 guard -- it walks off the table end."""
        level, run = 1, 0
        while True:
            idx = level // 5
            run += self.xp_table[idx] if idx < len(self.xp_table) else 1 << 30
            if run > xp:
                return level
            level += 1
            if level_max <= level:
                return level


# =============================================================================================
# the split policy
# =============================================================================================
def split_points(rem):
    """(+HP, +ATK) for `rem` points: max spend, then min |hp - atk|, then more HP."""
    best = None
    for hp in range(rem // PRICE_HP + 1):
        for atk in range((rem - PRICE_HP * hp) // PRICE_ATK + 1):
            key = (rem - PRICE_HP * hp - PRICE_ATK * atk, abs(hp - atk), -hp)
            if best is None or key < best[0]:
                best = (key, hp, atk)
    return best[1], best[2]


def policy_selftest():
    got = {r: split_points(r) for r in POLICY_FINGERPRINT}
    if got != POLICY_FINGERPRINT:
        diff = [r for r in got if got[r] != POLICY_FINGERPRINT[r]]
        raise ValueError("split policy no longer matches its fingerprint at rem=%s: %s vs %s"
                         % (diff, [got[r] for r in diff], [POLICY_FINGERPRINT[r] for r in diff]))


# =============================================================================================
# container primitives -- copied verbatim, appended to, NEVER re-derived (DO-NOT #1)
# =============================================================================================
def read_dir(b, p):
    """-> (small[], wide[], dirEnd) in FILE order."""
    n = b[p]
    p += 1
    nsmall, nwide = n & 0x7F, 0
    if n & 0x80:
        nwide = struct.unpack_from("<I", b, p)[0]
        p += 4
    small, wide = [], []
    for _ in range(nsmall):
        small.append((b[p], b[p + 1]))
        p += 2
    for _ in range(nwide):
        t, o = struct.unpack_from("<II", b, p)
        wide.append((t, o))
        p += 8
    return small, wide, p


def emit_dir(small, wide):
    if len(small) > 0x7F:
        raise ValueError("too many small entries")
    head = bytearray([(len(small) & 0x7F) | (0x80 if wide else 0)])
    if wide:
        head += struct.pack("<I", len(wide))
    for t, o in small:
        if t > 0xFF or o > 0xFF:
            raise ValueError("entry (0x%X, %d) no longer fits a small directory slot" % (t, o))
        head += bytes([t, o])
    for t, o in wide:
        head += struct.pack("<II", t, o)
    return bytes(head)


def fields_of(body, start=TOP_WORD):
    """{tag: bytes} for a body, sliced by offset order; the last field runs to the end."""
    small, wide, dend = read_dir(body, start)
    ent = small + wide
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    out = {}
    for j, k in enumerate(order):
        t, o = ent[k]
        a = dend + o
        b = dend + ent[order[j + 1]][1] if j + 1 < len(order) else len(body)
        if not (dend <= a <= b <= len(body)):
            raise ValueError("bad offset for tag 0x%02X" % t)
        out[t] = body[a:b]
    return out


def field_span(body, tag, start=TOP_WORD):
    """(absolute start, absolute end) of `tag` inside `body`, or None."""
    small, wide, dend = read_dir(body, start)
    ent = small + wide
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    for j, k in enumerate(order):
        if ent[k][0] != tag:
            continue
        a = dend + ent[k][1]
        b = dend + ent[order[j + 1]][1] if j + 1 < len(order) else len(body)
        return a, b
    return None


def set_field(body, tag, data):
    """In-place overwrite of an EXISTING field of exactly this size. No directory change."""
    span = field_span(body, tag)
    if span is None:
        raise ValueError("tag 0x%02X is not present" % tag)
    a, b = span
    if b - a != len(data):
        raise ValueError("tag 0x%02X is %d bytes, refusing to write %d" % (tag, b - a, len(data)))
    return body[:a] + bytes(data) + body[b:]


def append_field(body, tag, data):
    """APPEND-ONLY: new entry at the payload tail. Offsets are relative to the directory END, so
    no existing field byte moves."""
    small, wide, dend = read_dir(body, TOP_WORD)
    if any(t == tag for t, _o in small + wide):
        raise ValueError("tag 0x%02X already present" % tag)
    payload = bytearray(body[dend:])
    off = len(payload)
    if tag <= 0xFF and off <= 0xFF:
        small = small + [(tag, off)]
    else:
        wide = wide + [(tag, off)]
    payload += data
    return body[:TOP_WORD] + emit_dir(small, wide) + bytes(payload)


def remove_field(body, tag):
    """Exact inverse of append_field. Refuses unless the tag really is the payload tail -- the only
    shape append_field can produce, which is what makes --undo provably exact."""
    small, wide, dend = read_dir(body, TOP_WORD)
    ent = small + wide
    mine = [(t, o) for t, o in ent if t == tag]
    if not mine:
        return body
    cut = mine[0][1]
    for t, o in ent:
        if t != tag and o >= cut:
            raise ValueError("tag 0x%02X sits at or past tag 0x%02X -- refusing to remove"
                             % (t, tag))
    small = [(t, o) for t, o in small if t != tag]
    wide = [(t, o) for t, o in wide if t != tag]
    return body[:TOP_WORD] + emit_dir(small, wide) + bytes(bytearray(body[dend:])[:cut])


class Library(object):
    """The `.ahl` split into an untouched head, the child directory, and the 50 hero bodies."""

    MAGIC_PFS = bytes.fromhex("1CDF4421")

    def __init__(self, d):
        if d[:4] == self.MAGIC_PFS:
            raise ValueError("this file carries the .pfs magic -- wrong container")
        osmall, owide, oend = read_dir(d, 0)
        if owide or osmall != [(0, 0)]:
            raise ValueError("outer directory is not the expected single entry (0, 0)")
        lsmall, lwide, lend = read_dir(d, oend)
        lib = dict(lsmall + lwide)
        if 0x01 not in lib:
            raise ValueError("library body has no child list (tag 0x01)")
        if lib[0x01] != max(lib.values()):
            raise ValueError("tag 0x01 is not the last field of the library body -- growing it "
                             "would move other fields")
        self.name = pfs.pstr(d[lend + lib[0x14]:lend + lib[0x14] + 32]) if 0x14 in lib else ""
        self.counter = struct.unpack_from("<I", d, lend + lib[0x15])[0] if 0x15 in lib else None
        self.list_start = lend + lib[0x01]
        csmall, cwide, cend = read_dir(d, self.list_start)
        self.csmall, self.cwide = csmall, cwide
        self.head = d[:self.list_start]
        self.header_len = cend
        ent = csmall + cwide
        offs = [o for _t, o in ent]
        if offs != sorted(offs):
            raise ValueError("child offsets are not monotonic")
        self.bodies = []
        for k, (rid, off) in enumerate(ent):
            a = cend + off
            b = cend + ent[k + 1][1] if k + 1 < len(ent) else len(d)
            body = d[a:b]
            if struct.unpack_from("<I", body, 0)[0] != THERO_CLASSID:
                raise ValueError("record %d ClassID is not THero (0x%08X)" % (rid, THERO_CLASSID))
            self.bodies.append((rid, body))
        if self.header_len + sum(len(b) for _r, b in self.bodies) != len(d):
            raise ValueError("header + record lengths != file size -- trailing bytes?")

    def build(self, bodies):
        """Rewrite from `bodies`, fixing the child offsets. Entry widths are preserved exactly."""
        if [r for r, _b in bodies] != [r for r, _b in self.bodies]:
            raise ValueError("record id list changed")
        offs, run = [], 0
        for _rid, body in bodies:
            offs.append(run)
            run += len(body)
        small = [(t, offs[i]) for i, (t, _o) in enumerate(self.csmall)]
        wide = [(t, offs[len(self.csmall) + i]) for i, (t, _o) in enumerate(self.cwide)]
        head = emit_dir(small, wide)
        if len(head) != self.header_len - self.list_start:
            raise ValueError("child directory changed size")
        return self.head + head + b"".join(b for _r, b in bodies)


# =============================================================================================
# reading a hero
# =============================================================================================
def u8(f, tag):
    return f[tag][0] if tag in f and f[tag] else 0


def integer_list(raw):
    """Delphi TIntegerList as serialised: <u32 prefix><u32 count><u32 ids...>."""
    if not raw or len(raw) < 8:
        return []
    n = struct.unpack_from("<I", raw, 4)[0]
    if 8 + 4 * n > len(raw):
        return []
    return [struct.unpack_from("<I", raw, 8 + 4 * i)[0] for i in range(n)]


def ability_ids(f):
    return set(pfs.bits(f[T_BITSET])) if T_BITSET in f else set()


def ability_level(f, aid):
    """`TMultiLevelAbility.GetLevel @0x557651D8`: GetAbilityData(owner) ? [rec+0xC] : 0.
    The loader drives off tag 0x31, so a sub-record that list does not name is never read."""
    tag = aid + ABILITY_SUBRECORD_BASE
    if aid not in integer_list(f.get(T_DATAIDS, b"")) or tag not in f:
        return 0
    return u8(fields_of(f[tag], TOP_WORD), T_SUB_LEVEL)


class GameData(object):
    """HERORES.PFS chassis records and Ability.pfs tag-6 costs."""

    def __init__(self):
        recs, _key = pfs.load("HERORES.PFS")
        self.chassis = []
        for _rid, body in recs:
            f = pfs.parse_dir(body, top=True)
            owner = pfs.parse_dir(f[0x1D], top=False) if 0x1D in f else {}
            self.chassis.append({"atk": u8(f, 0x0F), "hp": u8(f, 0x12),
                                 "name": pfs.pstr(f.get(0x0A, b"")), "owner": owner})
        self.ability_cost = {}
        for rid, f, _key in pfs._iter("Ability.pfs"):
            if 6 in f:
                raw = f[6]
                self.ability_cost[rid - 10] = (struct.unpack_from("<I", raw, 0)[0]
                                               if len(raw) >= 4 else raw[0])


def hero_costs(f, chassis, gd, consts):
    """-> (stat_points, single_level_points, multi_level_points).

    Mirrors `THero.UsedSkillPoints @0x55786CC8`, including the max() that
    `TAbilityOwner.UpdateDefaultAbilities` imposes at load time.
    """
    owner = chassis["owner"]
    stat = (3 * u8(f, T_ATK) + 6 * u8(f, T_DEF) + 4 * u8(f, T_DAM)
            + 2 * u8(f, T_HP) + 3 * u8(f, T_MOV) + 2 * u8(f, T_RES))
    hset, cset = ability_ids(f), ability_ids(owner)
    single = multi = 0
    for aid in sorted(hset | cset):
        if aid in MULTI_LEVEL:
            hl, cl = ability_level(f, aid), ability_level(owner, aid)
            multi += consts.multi_cost[aid] * (max(hl, cl) - cl)
        elif aid in hset and aid not in cset:
            if aid not in gd.ability_cost:
                raise ValueError("ability %d is neither multi-level nor has Ability.pfs tag 6"
                                 % aid)
            single += gd.ability_cost[aid]
    return stat, single, multi


def read_hero(rid, body, gd, consts):
    f = fields_of(body)
    idx = struct.unpack_from("<I", f[T_CHASSIS], 0)[0] if T_CHASSIS in f else 0
    if not (0 <= idx < len(gd.chassis)):
        raise ValueError("record %d: hero-resource index %d out of range" % (rid, idx))
    ch = gd.chassis[idx]
    stat, single, multi = hero_costs(f, ch, gd, consts)
    writeoff = struct.unpack_from("<I", f[T_WRITEOFF], 0)[0] if T_WRITEOFF in f else 0
    xp = struct.unpack_from("<I", f[T_XP], 0)[0]
    level = consts.experience_to_level(xp)
    used = stat + single + multi
    return {
        "rid": rid, "fields": f, "chassis": ch, "chassis_index": idx,
        "name": (pfs.pstr(f.get(0x0A, b"")) + " " + pfs.pstr(f.get(0x0B, b""))).strip(),
        "atk": u8(f, T_ATK), "hp": u8(f, T_HP),
        "stat": stat, "single": single, "multi": multi, "used": used,
        "xp": xp, "level_cache": u8(f, T_LEVEL), "level": level, "writeoff": writeoff,
        "budget": level * 10 + 10,
        "left": level * 10 + 10 - used - writeoff,
    }


def derive_plan(clean, gd, consts):
    """Rebuild PLAN, HAS_ATK_TAG and HAS_HP_TAG from the clean bytes. -> (plan, has_atk, has_hp,
    rows, floor_hits)."""
    lib = Library(clean)
    plan, has_atk, has_hp, rows, floored = {}, set(), set(), [], []
    for rid, body in lib.bodies:
        h = read_hero(rid, body, gd, consts)
        f = h["fields"]
        if T_ATK in f:
            has_atk.add(rid)
        if T_HP in f:
            has_hp.add(rid)
        if h["level_cache"] != h["level"]:
            raise ValueError("record %d (%s): tag 0x16 says level %d but XP %d says level %d -- "
                             "undo could not restore the original XP exactly"
                             % (rid, h["name"], h["level_cache"], h["xp"], h["level"]))
        if h["xp"] != consts.level_to_experience(h["level"]):
            raise ValueError("record %d (%s): XP %d is not the level-%d boundary %d"
                             % (rid, h["name"], h["xp"], h["level"],
                                consts.level_to_experience(h["level"])))
        left = h["left"]
        if left < 0:
            raise ValueError("record %d (%s) is already OVER budget by %d" % (rid, h["name"], -left))
        drop = left // 10
        new_level = max(1, h["level"] - drop)
        rem = left - 10 * (h["level"] - new_level)
        if new_level != h["level"] - drop:
            floored.append((rid, h["name"], h["level"], rem))
        dhp, datk = split_points(rem)
        plan[rid] = (h["level"], new_level, h["atk"], h["atk"] + datk, h["hp"], h["hp"] + dhp)
        h.update({"new_level": new_level, "rem": rem, "dhp": dhp, "datk": datk,
                  "leftover": rem - PRICE_HP * dhp - PRICE_ATK * datk})
        rows.append(h)
    return plan, has_atk, has_hp, rows, floored


# =============================================================================================
# the edit
# =============================================================================================
def _write_stats(body, rid, level, atk, hp, consts):
    body = set_field(body, T_LEVEL, bytes([level]))
    body = set_field(body, T_XP, struct.pack("<I", consts.level_to_experience(level)))
    for tag, val, had in ((T_ATK, atk, rid in HAS_ATK_TAG), (T_HP, hp, rid in HAS_HP_TAG)):
        if had:
            body = set_field(body, tag, bytes([val]))
        elif val:
            body = append_field(body, tag, bytes([val]))
    return body


def to_clean(body, rid, consts):
    old_level, _nl, old_atk, _na, old_hp, _nh = PLAN[rid]
    if rid not in HAS_ATK_TAG:
        body = remove_field(body, T_ATK)
    if rid not in HAS_HP_TAG:
        body = remove_field(body, T_HP)
    return _write_stats(body, rid, old_level, old_atk, old_hp, consts)


def to_installed(body, rid, consts):
    _ol, new_level, _oa, new_atk, _oh, new_hp = PLAN[rid]
    return _write_stats(body, rid, new_level, new_atk, new_hp, consts)


def edit(d, install, consts):
    lib = Library(d)
    out = []
    for rid, body in lib.bodies:
        if rid not in PLAN:
            raise ValueError("record %d is not in PLAN" % rid)
        body = to_clean(body, rid, consts)
        if install:
            body = to_installed(body, rid, consts)
        out.append((rid, body))
    return lib.build(out)


def state_of(d, consts):
    """-> 'clean' | 'installed' | 'partial'."""
    lib = Library(d)
    n_clean = n_inst = 0
    for rid, body in lib.bodies:
        f = fields_of(body)
        ol, nl, oa, na, oh, nh = PLAN[rid]
        got = (u8(f, T_LEVEL), struct.unpack_from("<I", f[T_XP], 0)[0], u8(f, T_ATK), u8(f, T_HP),
               T_ATK in f, T_HP in f)
        want_clean = (ol, consts.level_to_experience(ol), oa, oh,
                      rid in HAS_ATK_TAG, rid in HAS_HP_TAG)
        want_inst = (nl, consts.level_to_experience(nl), na, nh,
                     rid in HAS_ATK_TAG or bool(na), rid in HAS_HP_TAG or bool(nh))
        if got == want_clean:
            n_clean += 1
        if got == want_inst:
            n_inst += 1
    if n_inst == len(lib.bodies):
        return "installed"
    if n_clean == len(lib.bodies):
        return "clean"
    return "partial"


def verify_patch(clean, patched, consts):
    """Re-parse and prove nothing but tags 0x10/0x13/0x16/0x18 moved."""
    a, b = Library(clean), Library(patched)
    for (rid, ob), (_rid, nb) in zip(a.bodies, b.bodies):
        of, nf = fields_of(ob), fields_of(nb)
        _ol, nl, _oa, na, _oh, nh = PLAN[rid]
        want = dict(of)
        want[T_LEVEL] = bytes([nl])
        want[T_XP] = struct.pack("<I", consts.level_to_experience(nl))
        for tag, val in ((T_ATK, na), (T_HP, nh)):
            if tag in want or val:
                want[tag] = bytes([val])
        if nf != want:
            bad = sorted(t for t in set(nf) | set(want) if nf.get(t) != want.get(t))
            raise ValueError("record %d differs on tag(s) %s" % (rid, [hex(t) for t in bad]))
        if ob[:TOP_WORD] != nb[:TOP_WORD]:
            raise ValueError("record %d ClassID changed" % rid)


def check_caps(rows):
    """`THero.Loaded` bypasses the budget check but NOT the cap clamp, which truncates silently."""
    bad = []
    for h in rows:
        _ol, _nl, _oa, na, _oh, nh = PLAN[h["rid"]]
        if h["chassis"]["atk"] + na > CAP_ATK:
            bad.append("record %d (%s): ATK %d + %d > %d"
                       % (h["rid"], h["name"], h["chassis"]["atk"], na, CAP_ATK))
        if h["chassis"]["hp"] + nh > CAP_HP:
            bad.append("record %d (%s): HP %d + %d > %d"
                       % (h["rid"], h["name"], h["chassis"]["hp"], nh, CAP_HP))
    if bad:
        raise ValueError("cap violation -- the engine would truncate these silently:\n  "
                         + "\n  ".join(bad))


def check_after(rows, consts):
    """Recompute `left` for the patched state; must be 0 or 1 for every hero."""
    bad = []
    for h in rows:
        _ol, nl, _oa, na, _oh, nh = PLAN[h["rid"]]
        used = h["used"] + PRICE_ATK * (na - h["atk"]) + PRICE_HP * (nh - h["hp"])
        left = nl * 10 + 10 - used - h["writeoff"]
        h["after_left"] = left
        if left not in (0, 1):
            bad.append("record %d (%s): %d left" % (h["rid"], h["name"], left))
    if bad:
        raise ValueError("post-edit budget is not 0/1:\n  " + "\n  ".join(bad))


# =============================================================================================
def main():
    ap = argparse.ArgumentParser(description="spend the hero library's unspent skill points")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    for p in (AHL, DLL):
        if not os.path.exists(p):
            sys.exit("ERROR: not found: %s" % p)

    d = open(AHL, "rb").read()
    try:
        policy_selftest()
        consts = Constants(open(DLL, "rb").read())
        gd = GameData()

        clean = edit(d, False, consts)
        if state_of(clean, consts) != "clean":
            raise ValueError("could not reconstruct a clean file from the current one")
        plan, has_atk, has_hp, rows, floored = derive_plan(clean, gd, consts)
        if plan != PLAN:
            bad = sorted(set(plan) | set(PLAN))
            bad = [r for r in bad if plan.get(r) != PLAN.get(r)]
            raise ValueError("re-derived plan disagrees with the PLAN table at record(s) %s:\n"
                             "  derived %s\n  table   %s"
                             % (bad, [plan.get(r) for r in bad], [PLAN.get(r) for r in bad]))
        if has_atk != set(HAS_ATK_TAG) or has_hp != set(HAS_HP_TAG):
            raise ValueError("stat-tag presence sets disagree with the file:\n"
                             "  ATK derived %s\n  HP  derived %s"
                             % (sorted(has_atk), sorted(has_hp)))

        state = state_of(d, consts)
        patched = edit(clean, True, consts)
        verify_patch(clean, patched, consts)
        check_caps(rows)
        check_after(rows, consts)
        if edit(patched, False, consts) != clean:
            raise ValueError("apply-then-undo is not byte-identical to the clean input")
    except (ValueError, IndexError, KeyError, struct.error) as exc:
        sys.exit("ABORT: %s" % exc)

    print("build_heroskill_spend -- %s (%s, %d heroes, next-id counter %s)"
          % (os.path.relpath(AHL, GAME), Library(d).name, len(rows), Library(d).counter))
    print("file %d -> %d bytes | state: %s | live XP table %s | costs %s"
          % (len(clean), len(patched), state, list(consts.xp_table),
             {MULTI_LEVEL[k][0]: v for k, v in sorted(consts.multi_cost.items())}))
    if floored:
        print("\n!! LEVEL FLOOR ENGAGED -- these heroes could not drop far enough and spend the "
              "whole residue on stats:")
        for rid, name, lvl, rem in floored:
            print("   record %d %s: level %d -> 1, %d points to spend" % (rid, name, lvl, rem))
    print()

    if a.list or not (a.apply or a.undo):
        print("%-3s %-24s %-11s %2s %4s %5s %5s %5s %5s %5s | %3s %4s %4s %5s"
              % ("id", "name", "chassis", "L", "bud", "stat", "abil", "mlvl", "used", "left",
                 "->L", "+HP", "+ATK", "over"))
        for h in rows:
            _ol, nl, _oa, na, _oh, nh = PLAN[h["rid"]]
            print("%-3d %-24s %-11s %2d %4d %5d %5d %5d %5d %5d | %3d %4d %4d %5d"
                  % (h["rid"], h["name"][:24], h["chassis"]["name"][:11], h["level"], h["budget"],
                     h["stat"], h["single"], h["multi"], h["used"], h["left"],
                     nl, h["dhp"], h["datk"], h["after_left"]))
        print("\n%d heroes, %d unspent points before -> %d after; %d end on 1 (rem was 1, and HP "
              "costs 2)" % (len(rows), sum(h["left"] for h in rows),
                            sum(h["after_left"] for h in rows),
                            sum(1 for h in rows if h["after_left"])))
        print("tags inserted: 0x10 on %d record(s), 0x13 on %d"
              % (sum(1 for h in rows if h["rid"] not in HAS_ATK_TAG and PLAN[h["rid"]][3]),
                 sum(1 for h in rows if h["rid"] not in HAS_HP_TAG and PLAN[h["rid"]][5])))
        if not (a.apply or a.undo):
            print("\n(dry run -- nothing written)")
            return

    want = "clean" if a.undo else "installed"
    if state == want:
        print("already %s -- nothing to do (idempotent)." % want)
        return
    if state == "partial":
        sys.exit("ABORT: the file is in a PARTIAL state -- neither clean nor installed. "
                 "Something else edited it; inspect before running with --apply or --undo.")

    out = clean if a.undo else patched
    rel_ok = os.path.exists(REL) and open(REL, "rb").read() == d
    if os.path.exists(REL) and not rel_ok:
        print("WARNING: %s has drifted from the target -- SKIPPING it."
              % os.path.relpath(REL, GAME))

    kill_aow()
    if not a.undo:
        # The snapshot is minted ONLY from a proved-clean file, so --undo and a re-tune can never
        # overwrite it with an already-edited state.
        if state != "clean":
            sys.exit("ABORT: refusing to back up a file that is not proved clean")
        if not os.path.exists(BACKUP):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(AHL, BACKUP)
            print("  backup -> backups/%s" % os.path.basename(BACKUP))
        else:
            print("  backup already exists, left alone: backups/%s" % os.path.basename(BACKUP))

    open(AHL, "wb").write(out)
    print("  wrote %s (%d bytes)" % (os.path.relpath(AHL, GAME), len(out)))
    if rel_ok:
        open(REL, "wb").write(out)
        print("  wrote %s (%d bytes)" % (os.path.relpath(REL, GAME), len(out)))

    check = open(AHL, "rb").read()
    if check != out:
        sys.exit("ABORT: read-back mismatch")
    print("\n%s -- verified: state is now %s."
          % ("UNDONE" if a.undo else "APPLIED", state_of(check, consts)))


if __name__ == "__main__":
    main()
