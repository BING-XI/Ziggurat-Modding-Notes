#!/usr/bin/env python3
r"""heroskill_races.py -- per-race offer probabilities for the hero level-up dialog.

⚠ EDITING THIS FILE CHANGES NOTHING ON ITS OWN. The 16x256 table is baked into `Ziggurat\AoWz.exe`
and `Ziggurat\AoWzCompat.exe` (zigexe.EXES) by `build_heroskill_race.py`. After any change here,
re-run

    python "Ziggurat/Modding Resources/build_scripts/build_heroskill_race.py" --apply

which rewrites both executables in lockstep, then regenerates the RUNNABLE pair at the game root.
Skipping either leaves the old table live with no error anywhere. (Exactly the `herodlg_cats.py`
DEFAULT_CAT trap that cost QA a finding on 2026-08-27.)

⚠⚠ `AoW.exe` / `AoWCompat.exe` at the game ROOT are VANILLA and are never a target.

⭐ THIS FILE IS THE AUTHORING SURFACE AND IT IS YOURS TO EDIT. The table below is a STARTING
POINT, not a design -- it was generated to be defensible, nothing more. Retune freely; `python
heroskill_races.py` prints the per-race expected counts, the deterministic floor and the standard
deviation, so the effect of an edit is visible before it is applied.

⚠ **There is no required range.** The report compares each row against 20-30 and marks it low or
high, but that is a DIRECTION the owner sketched once from a multiple-choice menu, not a bound they
set -- see SKETCH_LO below. It never gates anything and `--strict` does not touch it. After the
second 2026-09-10 ladder change ALL thirteen rows sit under 20 (13.5 to 18.4), which is inherent to
a top rung of 60 and is not a defect to fix.

================================================================================
⭐ heroskill_races.json WINS WHENEVER IT EXISTS
================================================================================
`heroskill_races.json`, beside this file, holds the FULL matrix -- every offered ability x each
of the 12 races, one value per cell. When it is present and parses, it is the table: `table()`,
`lookup_table()`, `stats()` and `report()` all resolve through it and `build_heroskill_race.py
--apply` bakes it. With no JSON, the `OFFERS` shorthand below is the table, exactly as before.

    absent   -> OFFERS shorthand         (report() prints "table source: ... shorthand")
    valid    -> the JSON                 (report() prints "table source: heroskill_races.json")
    corrupt  -> ValueError, loudly       (never a silent fall back to a different table)

The shorthand can express at most three values per ability (default / always 100 / never 0), so
a four-value ladder needs the full matrix. Seed one with `python heroskill_races.py --seed`,
which quantises the shorthand to the nearest of {0, 10, 25, 60}.

⭐ THE EDITOR LIVES IN THE ZIGGURAT MANUAL -- the "Hero Offers" tab (Project group). It reads
this JSON live on every build, offers the four-value dropdown per cell (hover + Q/W/E/R sets
0/10/25/60), and shows each race's expected offer count as you edit. Built by
`build_ziggurat_manual.py:r_heroskill()`.

⭐ **Save writes THIS FILE directly** (2026-09-10). In the Manual's own window the button reads
`Save` and goes through pywebview's js_api -- `build_ziggurat_manual.save_heroskill_offers()`,
which resolves the destination from `JSON_PATH` below, validates the payload, writes a temp file
in this directory, runs `validate()` over it and only then `os.replace`s it into place. Nothing
is written unless the whole table passes. In a plain browser there is no js_api, the button reads
`Export heroskill_races.json`, and it falls back to Save-As / a download for you to move here.

⚠ A cell OFF the ladder blocks the save. `validate()` warns about one and the api refuses on any
warning, so a hand-edited 100 has to be put back on a rung before the page can save again.

⚠ Saving still changes nothing in game. Re-run `build_heroskill_race.py --apply` (then
the build script) -- which is the assistant's job to run, not yours.

⚠ Row 15 (raceless: Mind Vessel, Dragon Golem) is NOT in the grid -- the 12 playable races are --
and it is NOT a 13th column in the JSON. In JSON mode it is DERIVED at table-build time by
`raceless_cells()`: per ability, the mean of the 12 grid columns, quantised onto the same
{0, 10, 25, 60} ladder the seed uses. Leaving it at TABLE_DEFAULT instead offered a Mind Vessel
or Dragon Golem hero all 102 abilities where the shorthand gave him ~25 -- a behaviour regression
nothing could see, because `report()` skipped the row (fixed 2026-09-09).

In shorthand mode row 15 is AUTHORED, by the `always=["Raceless"]` markers below. `report()`
prints which of the two is in force and lists every row either way, Raceless included.

================================================================================
WHAT THE NUMBERS MEAN
================================================================================
`OFFERS[<ability id>] = R(default_pct, always=[...], never=[...], only=[...])`

    default_pct   the chance (0..100) this ability is offered to a race with no explicit rule
    always=[..]   those races get 100
    never=[..]    those races get 0
    only=[..]     those races get 100, EVERY OTHER RACE gets 0 (default_pct is ignored)

Resolution order per (race, ability), first match wins:  never -> always -> only -> default.
`never` and `always` may not overlap; neither may `never` and `only`.

**Names, never raw race ids.** A misspelled name is an immediate assertion; a mistyped index is a
silently wrong column.

The decision at level-up is `hash(salt, hero unit id, hero level, ability id) % 100 < pct`, so:

    100  always offered      0  never offered      50  offered at roughly half the hero's levels

⚠ Since 2026-09-10 the ladder's TOP RUNG IS 60, not 100, so no authored cell is ever "always".
Only TABLE_DEFAULT (below) still holds 100, which means an ability the table has never heard of
is offered MORE often than any ability that was deliberately marked a race's signature.

The hash re-rolls on every level (the hero's level cache is one of its inputs), so a 50 is a
genuine coin flip per level-up -- but it is DERIVED, not drawn: closing and reopening the dialog,
adding and removing an ability, or saving and reloading all give the same answer. There is no
re-roll exploit and no shimmer.

================================================================================
⚠ TABLE_DEFAULT = 100 IS DELIBERATE -- FAIL OPEN
================================================================================
The table is indexed directly by ability id. An ability with no line below -- a newly minted one,
or one whose id this file has never heard of -- therefore reads whatever the cell holds. If that
were 0 it would be silently NEVER OFFERED, with nothing to see in any log. It is 100 instead, so
an unknown ability is always offered and the omission is visible in the dialog rather than absent
from it. Rows 12-14, which no race can reach (the enum is 0..11 plus 255), are filled with
TABLE_DEFAULT for the same reason.

================================================================================
THE RACE ENUM -- measured, not assumed
================================================================================
Read 2026-09-09 from `Release/HERORES.PFS` tag 0x0B (the race byte; tag 0x0A is the race NAME
string). Three records per race -- ids 0-11, 18-29 and 36-47 -- and all three agree:

    0 Human   1 Azrac   2 Lizardman  3 Frostling  4 Elf     5 Halfling
    6 Dwarf   7 HighMen 8 DarkElf    9 Orc       10 Goblin 11 Undead
    255 raceless (Mind Vessel, Dragon Golem)  -> clamped to row 15 by the cave

The cave reads the race with `mov eax,[hero+0x40] ; movzx eax, byte ptr [eax+0x20]`, which is
`THero.GetRace @0x55786F9C` inlined, and indexes `table[min(race,15)*256 + ability_id]`.

================================================================================
THE OFFERED SET -- 102 abilities, re-derived live
================================================================================
An ability reaches the level-up dialog iff its `Release/Ability.pfs` tag 9 has BOTH bit 8
(0x100, "Hero upgrade") and bit 9 (0x200, THero -- the editor labels it "Editor"). 102 qualify
today. `offered_ids()` below re-reads that live rather than hard-coding it, so this file cannot
drift from the data.

⚠⚠ **`Ability.pfs` record id = ability id + 10.** Joining record ids straight to ability ids
produces a completely wrong analysis that looks entirely reasonable. `offered_ids()` asserts the
join on two records checked against AoWDevEd on 2026-09-09:
    ability 97 (Webbed)       -> record 107, tag 9 = 0x03E, tag 6 = 0
    ability 88 (Black Breath) -> record 98,  tag 9 = 0x3FF, tag 6 = 20

================================================================================
HOW THE STARTING TABLE IS SHAPED
================================================================================
A flat rate over 102 abilities maximises the spread -- dialogs of 17 and of 34 both ordinary.
Shaping each race's column into rungs cuts that spread, because variance per cell is `p(1-p)`:
a cell at 0 contributes nothing, and one at the top rung contributes least when that rung is 100.

The seed table's shape, per race, is roughly:

    ~14 signature abilities on the top rung
    ~20 on the middle rung
    the rest on the bottom two

⚠ **Under the 2026-09-10 ladder (0, 10, 25, 60) that shape no longer buys certainty or tightness.**
The top rung is 60, so `p(1-p)` peaks there rather than vanishing: every race's deterministic floor
is **0** and sd rose to 3.0-3.3. Expected offers run 13.5 (Raceless) to 18.4 (Undead). Those are
properties of the rung values, not of the shape, and are the owner's choice -- do not "fix" them.

`python heroskill_races.py` prints expected, floor and sd per race. `--strict` errors on
validate()'s real defects; the 20-30 comparison is printed for calibration and is never an error.
"""
import hashlib
import json
import os
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

TABLE_DEFAULT = 100        # a (race, id) cell with no line below -> ALWAYS offered (fail open)
TABLE_ROWS = 16            # row = min(race, 15)
TABLE_COLS = 256           # indexed directly by ability id
RACELESS_ROW = 15          # race 255 clamps here

# measured 2026-09-09 from Release/HERORES.PFS tag 0x0B
RACE_IDS = {
    "Human": 0, "Azrac": 1, "Lizardman": 2, "Frostling": 3,
    "Elf": 4, "Halfling": 5, "Dwarf": 6, "HighMen": 7,
    "DarkElf": 8, "Orc": 9, "Goblin": 10, "Undead": 11,
    "Raceless": RACELESS_ROW,
}
# rows no race byte can select (the enum is 0..11 and 255): filled with TABLE_DEFAULT.
UNREACHABLE_ROWS = [r for r in range(TABLE_ROWS)
                    if r not in RACE_IDS.values()]

# ⚠ NOT A RULE, AND NOT THE OWNER'S NUMBER. On 2026-09-09 the owner picked "About 20-30" from a
# three-option menu (the alternatives were 40-50 and 60-70) when asked roughly how many abilities a
# hero should see. On 2026-09-10 they corrected the record: *"I don't think I ever actively proposed
# a '20 floor' - that would've been a very vague guideline, or nothing at all really."*
# So this is a DIRECTION -- materially fewer than 102, near vanilla's 23 -- printed for calibration
# only. It is never an error, it does not gate anything, and nothing may call it a floor, a band or
# a target. Real invariants live in validate(); those are what --strict enforces.
SKETCH_LO, SKETCH_HI = 20, 30

# ---------------------------------------------------------------- the JSON matrix
JSON_NAME = "heroskill_races.json"
JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), JSON_NAME)

# The only four values the Manual's editor offers, ascending. ⚠ Moving a rung is a DATA
# migration, not just a constant edit: every cell in heroskill_races.json sits on one of these,
# and the correct migration is by TIER IDENTITY (rung i -> new rung i), never by re-quantising
# the old numbers onto the new rungs. Re-quantising 40 onto (0,10,25,60) lands on 25 by luck, but
# it does so by accident -- 15 would land on 10 either way while 40 could have gone to 100 under
# a different ladder, and the author meant "the third rung", not "40 percent".
# 2026-09-10: (0, 15, 40, 100) -> (0, 10, 30, 100), owner's retune. Every race lost ~3.6-4.3
# expected offers by construction; report() lists it with every other row.
# 2026-09-10, second retune: (0, 10, 30, 100) -> (0, 10, 25, 60), owner's call.
# ⚠⚠ THE TOP RUNG NO LONGER MEANS "ALWAYS". At 60 nothing is guaranteed to anyone: every race's
# deterministic floor went 8..17 -> 0, so a High Man is offered Turn Undead 60% of the time
# rather than every level. Mean expected offers 22.4 -> 16.3, sd 2.6-2.9 -> 3.0-3.3 (a cell at
# 100 adds no variance; one at 60 adds the most of any rung). All three effects are inherent to
# the rung values and are not a defect to tune out.
LADDER = (0, 10, 25, 60)
# the grid's columns, in table-row order. Raceless (row 15) is deliberately absent -- see the
# docstring; in JSON mode it is DERIVED from these twelve, never stored.
GRID_RACES = [n for n, r in sorted(RACE_IDS.items(), key=lambda kv: kv[1])
              if r != RACELESS_ROW]
RACELESS_NAME = "Raceless"


class R:
    """One ability's per-race rule. See the module docstring for the resolution order."""

    __slots__ = ("default", "always", "never", "only")

    def __init__(self, default, always=(), never=(), only=()):
        self.default = int(default)
        self.always = tuple(always)
        self.never = tuple(never)
        self.only = tuple(only)

    def pct(self, race):
        if race in self.never:
            return 0
        if race in self.always:
            return 100
        if self.only:
            return 100 if race in self.only else 0
        return self.default

    def names(self):
        return set(self.always) | set(self.never) | set(self.only)


# ============================================================================
# THE TABLE.  Grouped by the dialog's own columns (herodlg_cats.py), ability id
# ascending inside each group, cost from Release/Ability.pfs tag 6 in the comment.
# ⭐ STARTING POINT -- see the docstring.  Edit freely, then re-run --apply.
# ============================================================================
OFFERS = {
    # ---------------- Wayfaring -------------------------------------------------------
    0:   R(10, always=["Halfling"]),                                    # Walking       4
    1:   R(10, always=["Frostling"], never=["Dwarf", "Lizardman"]),     # Flying       60
    2:   R(30, always=["Lizardman"], never=["Dwarf", "Undead"]),        # Swimming     20
    3:   R(30, always=["Elf", "Halfling"]),                             # Forestry      4
    4:   R(30, always=["Dwarf", "Orc", "Goblin", "DarkElf"]),           # Cave Crawl    4
    5:   R(25, always=["Dwarf", "Frostling"]),                          # Mountaineer  12
    36:  R(25, always=["Dwarf", "Goblin"]),                             # Wall Climb   16
    39:  R(30, always=["DarkElf", "Goblin", "Undead", "Orc"]),          # Night Vision 12
    41:  R(25, always=["Elf", "HighMen"]),                              # True Seeing  12
    42:  R(10, always=["Dwarf"]),                                       # Tunneling    12
    54:  R(10, always=["DarkElf", "Goblin"]),                           # Invisibility 20
    59:  R(10, always=["Raceless"]),                                    # Floating     20
    64:  R(40, always=["Elf", "HighMen", "Human", "Raceless"]),         # Vision        4
    66:  R(5,  always=["Undead", "Raceless"]),                          # Wall Passage 16
    68:  R(5,  always=["Undead"]),                                      # Path Of Decay 6
    69:  R(5,  always=["Elf", "HighMen"], never=["Undead"]),            # Path Of Life 12
    109: R(5,  always=["Frostling"]),                                   # Path Of Frost 18
    138: R(5,  always=["Azrac", "Orc"]),                                # Steppe Conc   4
    139: R(5,  always=["Dwarf", "Goblin", "DarkElf"]),                  # Cave Conc     6
    140: R(5,  always=["Elf", "Halfling"]),                             # Grass Conc   12
    141: R(5,  always=["Frostling"]),                                   # Snow Conc     4
    142: R(5,  always=["Azrac"]),                                       # Desert Conc   4
    143: R(5,  always=["Orc", "Undead"]),                               # Wasteland     4
    144: R(5,  always=["Lizardman"]),                                   # Water Conc    8
    145: R(5,  always=["Halfling", "Goblin"]),                          # Concealment   6

    # ---------------- Resistances -----------------------------------------------------
    6:   R(5,  always=["Raceless"]),                                    # Magic Immun  28
    7:   R(5,  always=["Azrac"]),                                       # Fire Immun   16
    8:   R(5,  always=["Frostling"]),                                   # Cold Immun   12
    9:   R(5),                                                          # Lightning Im 12
    10:  R(5,  always=["Lizardman", "Goblin"]),                         # Poison Immun 12
    11:  R(5,  always=["Undead"]),                                      # Death Immun  12
    12:  R(5,  never=["Undead", "DarkElf"]),                            # Holy Immun   12
    67:  R(40, always=["Orc", "Undead", "Raceless"], never=["Halfling"]),  # Fearless   2
    70:  R(30, always=["Undead", "DarkElf"]),                           # Death Prot    4
    71:  R(30, always=["Azrac", "Dwarf"]),                              # Fire Prot     4
    72:  R(30, always=["HighMen"], never=["Undead"]),                   # Holy Prot     4
    73:  R(30, always=["Lizardman", "Goblin"]),                         # Poison Prot   4
    74:  R(30),                                                         # Lightning Pr  4
    75:  R(25, always=["Elf"]),                                         # Magic Prot   12
    76:  R(30, always=["Frostling"]),                                   # Cold Prot     4
    77:  R(15, always=["Dwarf", "Raceless"]),                           # Physical Pr  24

    # ---------------- Melee -----------------------------------------------------------
    14:  R(10, always=["Azrac"]),                                       # Fire Strike   2
    15:  R(10, always=["Frostling"]),                                   # Cold Strike  16
    16:  R(10),                                                         # Lightning St 16
    17:  R(10, always=["Goblin", "Lizardman"]),                         # Poison Strike12
    18:  R(10, always=["Undead"], never=["HighMen", "Halfling"]),       # Death Strike  4
    19:  R(10, always=["HighMen"], never=["Undead", "DarkElf"]),        # Holy Strike   8
    20:  R(10),                                                         # Magic Strike  2
    21:  R(40, always=["Orc", "Human", "Raceless"]),                    # Strike        4
    51:  R(10, always=["Undead", "Orc"]),                               # Cause Fear    2
    111: R(30, always=["Orc", "Human", "Azrac"]),                       # Charge        4
    112: R(30, always=["Dwarf", "Orc", "Raceless"]),                    # Monster Slay  4
    113: R(40, always=["Human", "Dwarf", "Halfling", "Raceless"]),      # Parry         8
    114: R(30, always=["Orc", "Human"]),                                # Round Attack  2
    115: R(30, always=["Orc"]),                                         # Extra Strike  8
    116: R(25, always=["Elf"]),                                         # First Strike 20
    117: R(25, always=["Dwarf", "Orc", "Raceless"]),                    # Wall Crush    8
    118: R(10, always=["Undead"]),                                      # Lifestealing 20
    119: R(10, always=["Elf"]),                                         # Entangle St  28
    146: R(5,  always=["HighMen"], never=["Undead", "DarkElf"]),        # Holy Champ   12
    147: R(5,  always=["Undead", "DarkElf"], never=["HighMen"]),        # Unholy Champ 12
    176: R(40, always=["Human", "Dwarf", "HighMen"]),                   # Shield        8

    # ---------------- Ranged ----------------------------------------------------------
    22:  R(30, always=["Elf", "Halfling", "Azrac", "DarkElf"]),         # Archery       2
    24:  R(10, always=["Orc"]),                                         # Hurl Boulder 20
    25:  R(10, always=["Halfling", "Goblin"]),                          # Hurl Stones   8
    32:  R(30, always=["Elf", "Azrac", "Human"]),                       # Marksmanship  6
    44:  R(5,  always=["Dwarf"]),                                       # Fire Cannon  28
    45:  R(5,  always=["Dwarf"]),                                       # Fire Musket  16
    57:  R(10, always=["Dwarf", "Halfling"]),                           # Shoot Bolt    4
    58:  R(10, always=["Lizardman", "Azrac", "Goblin"]),                # Throw Javelin 2
    61:  R(10, always=["Goblin", "DarkElf"]),                           # Poison Darts  4
    62:  R(5,  always=["Lizardman"]),                                   # Poison Spit   4
    86:  R(5),                                                          # Fire Breath  16
    87:  R(5,  always=["Frostling"]),                                   # Cold Breath  20
    88:  R(5,  always=["Undead"], never=["HighMen"]),                   # Black Breath 20
    89:  R(5,  always=["HighMen"], never=["Undead", "DarkElf"]),        # Divine Breath24
    90:  R(5,  always=["Goblin"]),                                      # Poison Breath20
    120: R(10, always=["Undead", "DarkElf"]),                           # Black Bolts   6
    121: R(10, always=["Raceless"]),                                    # Magic Bolts   4
    122: R(10, always=["Frostling"]),                                   # Frost Bolts   6
    123: R(10),                                                         # Lightning Bo  8
    124: R(10, always=["HighMen"], never=["Undead", "DarkElf"]),        # Holy Bolts    8

    # ---------------- Magic -----------------------------------------------------------
    27:  R(10, always=["Elf"]),                                         # Web           4
    28:  R(5,  always=["DarkElf"]),                                     # Dominate     32
    29:  R(5,  always=["DarkElf"]),                                     # Seduce        8
    30:  R(10, always=["Azrac"]),                                       # Flame Throw  20
    31:  R(10, always=["Azrac"]),                                       # Call Flames   8
    35:  R(5,  always=["Undead"], never=["HighMen", "Halfling"]),       # Invoke Death 32
    37:  R(25, always=["Halfling", "Human", "Elf"]),                    # Bard's Skills 4
    38:  R(0,  always=["HighMen", "DarkElf", "Undead"]),                # Turn Undead   5
    40:  R(10, always=["Elf"]),                                         # Entangle      2
    46:  R(40, always=["Human", "HighMen", "Orc"]),                     # Leadership   20
    47:  R(30, always=["HighMen", "Halfling"], never=["Undead"]),       # Healing      12
    49:  R(25, always=["Lizardman"], never=["Undead"]),                 # Regeneration  8
    52:  R(40, always=["Human", "HighMen", "DarkElf"]),                 # Spell Casting15
    55:  R(5,  always=["Undead", "DarkElf", "Raceless"]),               # Doom Gaze    32
    148: R(10, always=["DarkElf"]),                                     # Charm        16
    171: R(30, always=["Human", "Dwarf"]),                              # Drillmaster  10
    172: R(25, always=["Azrac"]),                                       # Evoker       20
    173: R(25, always=["Goblin"]),                                      # Conjurer     40
    174: R(25, always=["Elf"]),                                         # Enchanter    30
    175: R(25, always=["Undead"]),                                      # Ritualist    30
}


# ============================================================================
# derivation + validation
# ============================================================================
def _abilitypfs_offered():
    """-> {ability id: (mask, cost)} for every ability the level-up dialog can offer.

    Live from `Release/Ability.pfs`, never hard-coded, and the record-id join is asserted.
    """
    sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
    import pfs                                                          # noqa: E402

    recs, _fname = pfs.load("Ability.pfs")
    byrec = {}
    for rid, body in recs:
        try:
            byrec[rid] = pfs.parse_dir(body, top=False)
        except (ValueError, IndexError):
            continue

    def tag9(rid):
        f = byrec.get(rid, {})
        return struct.unpack_from("<H", f[9])[0] if 9 in f and len(f[9]) >= 2 else 0

    def tag6(rid):
        f = byrec.get(rid, {})
        return pfs.u32(f[6]) if 6 in f else 0

    # ⚠ THE JOIN: record id = ability id + 10.  Checked against AoWDevEd 2026-09-09.
    assert tag9(97 + 10) == 0x03E and tag6(97 + 10) == 0, (
        "Ability.pfs join broken: ability 97 (Webbed) -> record 107 should be tag9=0x03E "
        "tag6=0, got 0x%03X / %d" % (tag9(107), tag6(107)))
    assert tag9(88 + 10) == 0x3FF and tag6(88 + 10) == 20, (
        "Ability.pfs join broken: ability 88 (Black Breath) -> record 98 should be tag9=0x3FF "
        "tag6=20, got 0x%03X / %d" % (tag9(98), tag6(98)))

    out = {}
    for rid in byrec:
        m = tag9(rid)
        if (m & 0x100) and (m & 0x200):          # b8 Hero upgrade AND b9 THero
            out[rid - 10] = (m, tag6(rid))
    return out


def offered_ids():
    """-> sorted list of the ability ids offered at hero level-up, live from Ability.pfs."""
    return sorted(_abilitypfs_offered())


def offered_costs():
    """-> {ability id: level-up point cost} for the offered set (Ability.pfs tag 6)."""
    return {aid: cost for aid, (_mask, cost) in _abilitypfs_offered().items()}


# ============================================================================
# heroskill_races.json -- the full matrix, and the authority whenever it exists
# ============================================================================
# The file is written by a hand-rolled emitter rather than json.dumps because the Manual's
# in-browser editor has to produce BYTE-IDENTICAL output from JavaScript: an export that
# round-trips to a different-looking file cannot be diffed against the seed, and "did my edit
# land?" then has no cheap answer. Both emitters follow the same three rules: meta keys in the
# fixed order below, offers ascending by ability id one row per line, races in GRID_RACES order.
META = [
    ("table", "hero level-up offer probability, per race, per ability, in percent"),
    ("authority", "this file wins over the OFFERS shorthand in heroskill_races.py "
                  "whenever it is present and parses"),
    ("apply", "python build_scripts/build_heroskill_race.py --apply"),
    ("editor", "Ziggurat Manual, Hero Offers tab"),
    ("races", GRID_RACES),
    ("ladder", list(LADDER)),
    ("table_default", TABLE_DEFAULT),
    ("raceless_row", RACELESS_ROW),
    ("raceless", "not in the grid and not stored here - row 15 is derived at table-build time, "
                 "the per-ability mean of the 12 races quantised onto the ladder"),
]


def _jval(v):
    """One meta value as JSON text. ASCII strings with no escapes, ints, and flat lists only."""
    if isinstance(v, str):
        assert v.isascii() and '"' not in v and "\\" not in v, \
            "meta strings stay plain ASCII so the browser emitter matches byte for byte: %r" % v
        return '"%s"' % v
    if isinstance(v, bool):
        raise TypeError("no booleans in meta")
    if isinstance(v, int):
        return "%d" % v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_jval(x) for x in v) + "]"
    raise TypeError("meta value %r has no canonical form" % (v,))


def json_text(mat):
    """-> the exact text of heroskill_races.json for matrix `mat`. Deterministic: no dates, no
    stored fingerprint. Re-emitting an unedited table reproduces the file byte for byte."""
    lines = ["{", '  "meta": {']
    for i, (k, v) in enumerate(META):
        lines.append('    "%s": %s%s' % (k, _jval(v), "" if i == len(META) - 1 else ","))
    lines.append("  },")
    lines.append('  "offers": {')
    ids = sorted(mat)
    for i, aid in enumerate(ids):
        cells = ", ".join('"%s": %d' % (n, int(mat[aid][n]))
                          for n in GRID_RACES if n in mat[aid])
        lines.append('    "%d": {%s}%s' % (aid, cells, "" if i == len(ids) - 1 else ","))
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def canonical(mat):
    """-> the whitespace-free text that IS the table's identity, for the fingerprint.

    Separate from json_text so the fingerprint depends on the values alone: reformatting the
    file, or editing its meta, must not move it. Reproduced character for character by the
    Manual's editor.
    """
    parts = []
    for aid in sorted(mat):
        cells = ",".join('"%s":%d' % (n, int(mat[aid][n]))
                         for n in GRID_RACES if n in mat[aid])
        parts.append('"%d":{%s}' % (aid, cells))
    return "{" + ",".join(parts) + "}"


def fingerprint(mat=None):
    """-> 8 hex chars identifying the table. Printed by report() and shown by the editor, so a
    stale page after an export+reload is visible rather than inferred (the 2026-08-14 trap)."""
    if mat is None:
        mat = matrix()
    return hashlib.sha256(canonical(mat).encode("ascii")).hexdigest()[:8]


def ladder_counts(mat=None, race=None):
    """-> [n at each LADDER rung, n off-ladder] over the 12 grid races.

    The editor's second staleness figure, and the drivers of the expected-offer count:
    E = 0.60*#60 + 0.25*#25 + 0.10*#10 on today's ladder, but it is DERIVED from LADDER and
    never spelled out. It replaced "cells differing from TABLE_DEFAULT", which
    counted DOWN when a cell was deliberately set to 100% -- 100 being both the fail-open
    default and the top of the ladder, that reading made an edit look like it went backwards.

    `race` limits the count to one grid column; omitted, it counts the whole grid.
    """
    if mat is None:
        mat = matrix()
    names = [race] if race else GRID_RACES
    out = [0] * (len(LADDER) + 1)
    for cells in mat.values():
        for n in names:
            if n not in cells:
                continue
            v = cells[n]
            out[LADDER.index(v) if v in LADDER else len(LADDER)] += 1
    return out


def quantise(pct, ladder=LADDER):
    """-> the nearest ladder value; a tie goes to the lower one."""
    return min(ladder, key=lambda v: (abs(v - pct), v))


def e_formula(ladder=LADDER):
    """-> e.g. 'E = 0.60*#60 + 0.25*#25 + 0.10*#10'. DERIVED from the ladder, never spelled out, so
    moving a rung cannot leave a stale formula printed under the counts it explains."""
    return "E = " + " + ".join("#100" if v == 100 else "%.2f*#%d" % (v / 100.0, v)
                               for v in sorted(ladder, reverse=True) if v)


def raceless_cells(mat):
    """-> {ability id: pct} for row 15, DERIVED -- never stored, never authored.

    Per ability, the mean of the 12 grid columns quantised onto LADDER. A grid race with no
    cell for that ability counts as TABLE_DEFAULT, matching what `table()` would write for it.

    Only ability ids the matrix already carries get a row-15 value; an id the table has never
    heard of keeps TABLE_DEFAULT on row 15 exactly as it does on every other row (fail open).
    """
    out = {}
    for aid, cells in mat.items():
        vals = [cells.get(n, TABLE_DEFAULT) for n in GRID_RACES]
        out[aid] = quantise(sum(vals) / float(len(vals)))
    return out


def seed_matrix():
    """-> the full matrix, the OFFERS shorthand quantised onto LADDER, over the live offered set.

    Under LADDER = (0, 10, 25, 60) the shorthand's values move 5 -> 0, 10 -> 10, 25 -> 25,
    30 -> 25. That shifts every race's expected offer count, which is expected and is what
    report() prints afterwards.

    ⚠ This is the SEED path only, for a table that does not exist yet. It is NOT how an existing
    heroskill_races.json migrates when the ladder moves -- that migration is by tier identity
    (rung i -> new rung i); see LADDER's comment.
    """
    out = {}
    for aid in offered_ids():
        r = OFFERS.get(aid)
        out[aid] = {n: quantise(r.pct(n) if r else TABLE_DEFAULT) for n in GRID_RACES}
    return out


def load_json(path=None):
    """-> {ability id: {race name: pct}} from the JSON, or None if there is no file.

    ⚠ A file that exists and cannot be read raises. Falling back to the shorthand would silently
    swap the table for a different one -- the exact failure this module's docstring warns about.
    """
    path = path or JSON_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError("%s exists but will not parse (%s). Fix or delete it -- it is the "
                         "table whenever it is present." % (path, exc))
    if not isinstance(doc, dict) or not isinstance(doc.get("offers"), dict):
        raise ValueError("%s has no 'offers' object" % path)
    mat = {}
    for k, cells in doc["offers"].items():
        try:
            aid = int(k)
        except (TypeError, ValueError):
            raise ValueError("%s: ability key %r is not an integer" % (path, k))
        if not 0 <= aid < TABLE_COLS:
            raise ValueError("%s: ability id %d outside 0..%d" % (path, aid, TABLE_COLS - 1))
        if not isinstance(cells, dict):
            raise ValueError("%s: ability %d does not map races to values" % (path, aid))
        row = {}
        for name, v in cells.items():
            if name not in RACE_IDS:
                raise ValueError("%s: ability %d names unknown race %r" % (path, aid, name))
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100:
                raise ValueError("%s: ability %d, %s = %r is not an integer 0..100"
                                 % (path, aid, name, v))
            row[name] = v
        mat[aid] = row
    return mat


_RESOLVED = None


def _resolve():
    """-> ("json"|"shorthand", {ability id: {race: pct}}). Cached: report() asks 15 times.

    In JSON mode the Raceless column is stripped if the file carries one (validate() warns) and
    re-derived from the 12 grid columns, so row 15 is a function of the grid and cannot be
    edited into disagreement with it.
    """
    global _RESOLVED
    if _RESOLVED is None:
        mat = load_json()
        if mat is None:
            # every race INCLUDING Raceless, so shorthand mode is bit-for-bit what it always was
            _RESOLVED = ("shorthand",
                         {aid: {n: r.pct(n) for n in RACE_IDS} for aid, r in OFFERS.items()})
        else:
            mat = {aid: {n: v for n, v in cells.items() if n != RACELESS_NAME}
                   for aid, cells in mat.items()}
            for aid, p in raceless_cells(mat).items():
                mat[aid][RACELESS_NAME] = p
            _RESOLVED = ("json", mat)
    return _RESOLVED


def raceless_source():
    """-> "derived" (JSON mode: computed from the 12 grid columns) or "authored" (shorthand)."""
    return "derived" if mode() == "json" else "authored"


def mode():
    """-> "json" or "shorthand"."""
    return _resolve()[0]


def matrix():
    """-> {ability id: {race name: pct}} from whichever table is in force."""
    return _resolve()[1]


def source():
    """-> a one-line description of where the live table comes from."""
    return (JSON_PATH if mode() == "json"
            else "the OFFERS shorthand in %s (no %s)" % (os.path.basename(__file__), JSON_NAME))


def validate():
    """-> list of warning strings.  Raises AssertionError on anything structurally wrong."""
    warn = []
    for aid, r in OFFERS.items():
        assert isinstance(aid, int) and 0 <= aid < TABLE_COLS, \
            "ability id %r out of table range 0..%d" % (aid, TABLE_COLS - 1)
        assert isinstance(r, R), "OFFERS[%d] is not an R()" % aid
        assert 0 <= r.default <= 100, "OFFERS[%d] default %d not in 0..100" % (aid, r.default)
        bad = r.names() - set(RACE_IDS)
        assert not bad, "OFFERS[%d] names unknown race(s) %s" % (aid, sorted(bad))
        assert not (set(r.always) & set(r.never)), \
            "OFFERS[%d]: %s is in both always and never" % (aid, sorted(set(r.always) & set(r.never)))
        assert not (set(r.only) & set(r.never)), \
            "OFFERS[%d]: %s is in both only and never" % (aid, sorted(set(r.only) & set(r.never)))
    # duplicate ids are impossible in a dict literal, but a duplicate KEY silently drops the
    # first line, so count what the source file actually contains.
    _assert_no_duplicate_keys()

    # the cross-check runs against whichever table is IN FORCE, so a JSON gap is caught too.
    md, mat = _resolve()
    noun = "OFFERS line" if md == "shorthand" else "row in " + JSON_NAME
    subj = "OFFERS lists" if md == "shorthand" else JSON_NAME + " lists"
    live = set(offered_ids())
    for aid in sorted(live - set(mat)):
        warn.append("ability %d is offered at level-up but has no %s "
                    "-> every race gets TABLE_DEFAULT (%d)" % (aid, noun, TABLE_DEFAULT))
    for aid in sorted(set(mat) - live):
        warn.append("%s ability %d, which Ability.pfs does not offer at level-up "
                    "(tag 9 lacks 0x100|0x200) -- the row is inert" % (subj, aid))
    if md == "json":
        raw = load_json() or {}
        stored = sorted(aid for aid in raw if RACELESS_NAME in raw[aid])
        if stored:
            warn.append("%s: %d row(s) store a %s column (first: %s) -- it is IGNORED. Row 15 is "
                        "derived from the 12 grid races; the grid is 12 races wide."
                        % (JSON_NAME, len(stored), RACELESS_NAME,
                           ", ".join(str(a) for a in stored[:4])))
        for aid in sorted(mat):
            miss = [n for n in GRID_RACES if n not in mat[aid]]
            if miss:
                warn.append("%s: ability %d has no value for %s -> %s get TABLE_DEFAULT (%d)"
                            % (JSON_NAME, aid, ", ".join(miss),
                               "they" if len(miss) > 1 else "it", TABLE_DEFAULT))
        off = sorted((aid, n, mat[aid][n]) for aid in mat for n in mat[aid]
                     if mat[aid][n] not in LADDER)
        if off:
            warn.append("%s: %d cell(s) off the %s ladder the editor offers, first: %s"
                        % (JSON_NAME, len(off), "/".join(str(x) for x in LADDER),
                           ", ".join("%d %s=%d" % t for t in off[:4])))
    return warn


def _assert_no_duplicate_keys():
    """A duplicate id in the OFFERS literal is legal Python and silently drops the first entry."""
    src = open(os.path.abspath(__file__), "r", encoding="utf-8").read()
    body = src.split("OFFERS = {", 1)[1].split("\n}\n", 1)[0]
    seen, dup = set(), []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split(":", 1)[0].strip()
        if not key.isdigit():
            continue
        k = int(key)
        (dup.append(k) if k in seen else seen.add(k))
    assert not dup, "duplicate ability id(s) in OFFERS: %s" % sorted(set(dup))


def table():
    """-> 4096 bytes, table[row*256 + ability_id] = percentage, from the table in force."""
    t = bytearray([TABLE_DEFAULT]) * (TABLE_ROWS * TABLE_COLS)
    for aid, cells in matrix().items():
        for name, p in cells.items():
            assert 0 <= p <= 100
            t[RACE_IDS[name] * TABLE_COLS + aid] = p
    # UNREACHABLE_ROWS keep TABLE_DEFAULT: fail open. Row 15 does not -- it is authored in
    # shorthand mode and derived in JSON mode, and matrix() carries it either way.
    assert len(t) == TABLE_ROWS * TABLE_COLS
    return bytes(t)


def lookup_table():
    """-> table(). The name the rest of the toolchain uses for a baked lookup (herodlg_cats)."""
    return table()


def stats():
    """-> {race name: (expected count, deterministic floor, sd, n_offered)} over the live set."""
    mat = matrix()
    live = offered_ids()
    out = {}
    for name in RACE_IDS:
        exp = floor = var = 0.0
        for aid in live:
            cells = mat.get(aid)
            p = (cells.get(name, TABLE_DEFAULT) if cells else TABLE_DEFAULT) / 100.0
            exp += p
            if p >= 1.0:
                floor += 1
            var += p * (1.0 - p)
        out[name] = (exp, int(floor), var ** 0.5, len(live))
    return out


def report(strict=False):
    warn = validate()
    md, mat = _resolve()
    live = offered_ids()
    noun = "an OFFERS line" if md == "shorthand" else "a row in " + JSON_NAME
    print("heroskill_races -- per-race hero level-up offer table")
    print("  table source: %s" % source())
    print("  %d abilities offered at level-up (live from Release/Ability.pfs, record id = "
          "ability id + 10)" % len(live))
    print("  %d have %s; %d fall back to TABLE_DEFAULT = %d (fail open)"
          % (len(set(live) & set(mat)), noun, len(set(live) - set(mat)), TABLE_DEFAULT))
    print("  table %d rows x %d cols = %d B; unreachable rows %s hold TABLE_DEFAULT"
          % (TABLE_ROWS, TABLE_COLS, TABLE_ROWS * TABLE_COLS, UNREACHABLE_ROWS))
    lc = ladder_counts(mat)
    print("  fingerprint %s over %d ability rows x %d races" % (fingerprint(mat), len(mat),
                                                                len(GRID_RACES)))
    print("  ladder %s%s   (%s)"
          % ("  ".join("%d%%=%d" % (v, lc[i]) for i, v in enumerate(LADDER)),
             "  off-ladder=%d" % lc[-1] if lc[-1] else "", e_formula()))
    print()
    print("  %-10s %3s  %8s  %5s  %5s  %-8s %s"
          % ("race", "row", "expected", "det", "sd", "source", "vs %d-%d" % (SKETCH_LO, SKETCH_HI)))
    # ⚠ EVERY row is listed, Raceless included. It was skipped in JSON mode until 2026-09-09 --
    # which made the one row carrying a real regression the one row nothing looked at.
    outside = []
    st = stats()
    for name, row in sorted(RACE_IDS.items(), key=lambda kv: kv[1]):
        exp, floor, sd, _n = st[name]
        mark = "low" if exp < SKETCH_LO else ("high" if exp > SKETCH_HI else "")
        if mark:
            outside.append((name, exp))
        src = raceless_source() if name == RACELESS_NAME else "authored"
        print("  %-10s %3d  %8.1f  %5d  %5.1f  %-8s %s"
              % (name, row, exp, floor, sd, src, mark))
    for row in UNREACHABLE_ROWS:
        print("  %-10s %3d  %8s  %5s  %5s  %-8s (unreachable, all %d)"
              % ("-", row, "-", "-", "-", "-", TABLE_DEFAULT))
    print()
    for w in warn:
        print("  WARNING: " + w)
    if outside:
        # Informational only. NEVER an error, --strict included: see SKETCH_LO's note --
        # 20-30 is a direction the owner sketched, not a bound they set.
        print("  note: %d race(s) outside %d-%d: %s"
              % (len(outside), SKETCH_LO, SKETCH_HI,
                 ", ".join("%s %.1f" % (n, e) for n, e in outside)))
    if not warn:
        print("  no warnings")
    elif strict:
        # --strict enforces the REAL invariants validate() checks -- values off the ladder,
        # an unknown race name, a duplicate or out-of-range id, a missing row. Those are
        # defects. An expected-offer count is a design choice and is not.
        print("\n  ERROR: %d validation warning(s); --strict treats these as errors." % len(warn))
        return 1
    return 0


def seed(path=None, force=False):
    """Write heroskill_races.json from the quantised shorthand. Refuses to clobber."""
    path = path or JSON_PATH
    if os.path.exists(path) and not force:
        print("%s already exists -- refusing to overwrite an authored table.\n"
              "  Delete it, or pass --force, if the quantised shorthand really is what you want."
              % path)
        return 1
    mat = seed_matrix()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json_text(mat))
    lc = ladder_counts(mat)
    print("wrote %s\n  %d ability rows x %d races, quantised to %s\n  fingerprint %s, ladder %s"
          % (path, len(mat), len(GRID_RACES), "/".join(str(x) for x in LADDER),
             fingerprint(mat), "  ".join("%d%%=%d" % (v, lc[i])
                                         for i, v in enumerate(LADDER))))
    return 0


if __name__ == "__main__":
    _argv = sys.argv[1:]
    if "--seed" in _argv:
        sys.exit(seed(force="--force" in _argv))
    sys.exit(report(strict="--strict" in _argv))
