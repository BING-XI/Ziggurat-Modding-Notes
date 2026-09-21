# `.pfs` container — the trailing CRC-32

**Status: FORMAT CONFIRMED 2026-08-07 — the editor itself writes it.** AoWDevEd re-saved
`Release/Unitres.pfs` (size 153927 → 153627, one duplicate record deleted) and the freshly
written file validates against the formula below. That is conclusive that the CRC is real and
that the *writer* maintains it, not merely a pattern in the shipped files. It also verifies on
9 of 9 magic-bearing files.

⚠ **Still untested: whether the READER rejects a bad one.** No deliberately-corrupted `.pfs` has
been fed to the game or the editor, so "a wrong CRC kills the load" remains inference from the
`.hss` precedent. It does not matter much in practice — anything writing a `.pfs` should repair
the checksum regardless, since the editor does.

## The finding

`Release/*.pfs` files that begin with the magic `1C DF 44 21` **end with a CRC-32 of
`data[4:-4]`** — everything between the magic and the checksum itself.

```python
import zlib, struct
d = open("Release/Unitres.pfs", "rb").read()
stored = struct.unpack_from("<I", d, len(d) - 4)[0]
calc   = zlib.crc32(d[4:-4]) & 0xFFFFFFFF        # stored == calc
```

Standard reflected CRC-32, identical to `zlib.crc32` — the same algorithm as
`Engine.GetCRC32` used by the `.hss` container (see `re_tools/hss_crc.py`).

**⚠ The covered region differs from `.hss`.** `.hss` checksums `d[:-4]`; `.pfs` checksums
`d[4:-4]`. Passing a `.pfs` to `hss_crc.py` will therefore report a false mismatch and "fix" it
by writing a wrong value. They are not interchangeable.

### Verified across the whole folder (2026-08-07)

| carries magic `1C DF 44 21` | CRC valid |
|---|---|
| `Ability.pfs`, `FACERES.PFS`, `HERORES.PFS`, `ITEMGFX.PFS`, `Spells.pfs`, `TEXT.pfs`, `Unitgfx.pfs`, `Unitres.pfs`, `comb_res.pfs` | all 9 ✅ |
| `General.pfs`, `HEROES.PFS`, `ITEMS.PFS`, `RulesV.pfs` | **no magic, no CRC** — do not append one |

The rule is the magic, not the extension: `HEROES.PFS` and `ITEMS.PFS` start `01 00 00 02 …`
and are raw property tables with no wrapper.

## Why `1C DF 44 21` is not really a magic number

`BUILD-YOUR-MOD-MANUAL.md` calls it an "optional magic", which works in practice but hides what
it is. `0x2144DF1C` is the **CRC-32 residue constant** — the value you get from running CRC-32
over any message with its own little-endian CRC appended. It is a self-check marker: computing
`zlib.crc32(d[4:])` over a *valid* file yields exactly `0x2144DF1C`, the same bytes as the
header. That is why all four files appeared to share a header "checksum" when first probed.

Practical upshot — one line validates a file without knowing its length:

```python
zlib.crc32(d[4:]) & 0xFFFFFFFF == 0x2144DF1C     # True iff the CRC is intact
```

## Editing a `.pfs`

**Scalar stats are safe.** On a unit record (`Unitres.pfs`, child classid `0x20212`) these are
fixed-size and can be written in place with no table rewrite and no offset shifts:

| tag | field | size |
|-----|-------|------|
| `0x0E` | ATK | byte (255 = no melee attack) |
| `0x0F` | DEF | byte |
| `0x10` | DAM | byte |
| `0x11` | HP  | byte |
| `0x12` | MV  | byte |
| `0x13` | RES | byte |
| `0x14` | level | byte |
| `0x1B` | gold cost | u32 |

Tag order verified 2026-08-07 against Man-at-Arms, Pikeman, Cavalier and Musketeer, all four
matching the design workbook on every stat. ⚠ **The order is not the workbook's** — the sheet
reads ATK DAM DEF RES HP MV, the record stores ATK DEF DAM HP MV RES.

### ⚠⚠ The tag map is PER FILE. `HERORES.PFS` is `Unitres.pfs`'s sequence shifted one tag up

Same six stats in the same order — but every tag is one higher, so reusing the unit map mislabels
**all six columns** while still producing numbers that look plausible:

| tag | `Unitres.pfs` | `HERORES.PFS` |
|-----|---------------|---------------|
| `0x0D` | — | alignment / race group (0–6; `ReadWrite` clamps >6 to 3) |
| `0x0E` | ATK | (unused) |
| `0x0F` | DEF | **ATK** |
| `0x10` | DAM | **DEF** |
| `0x11` | HP | **DAM** |
| `0x12` | MV | **HP** |
| `0x13` | RES | **MV** |
| `0x14` | level | **RES** — there is **no starting-level field** on a hero chassis |
| `0x1B` | gold | absent — heroes are not bought |

**Read off the code, not guessed:** `THeroResource.ReadWrite` @`0x55789FD4` serialises tags
`0x0F`–`0x14` into instance `+0x24`–`+0x29`, and `THero`'s level-up bonus bytes at `+0x6A`–`+0x6F`
fix the sequence as **ATK DEF DAM HP MV RES**. Confirmed against the vanilla workbook: **Azracs and
Highmen match on all six stats**, HP is 10 for every race in both, and Ziggurat's change is a clean
−4 MV. 43 of 72 cells match exactly, and every mismatch is a coherent mod change.

⚠ **Do not pin this from a single hero's info card — that is how the wrong map shipped.** A level-2
Lizard reading ATK 4 · DEF 4 · DAM 3 · RES 3 · Hits 10 · Moves 28 fits a *rotated* map just as
convincingly, because that chassis has ATK, DEF and DAM all equal to 3 and the card adds +1 to
several stats from level-ups, morale and items. Four "exact matches" out of five felt like proof
and was coincidence. The published table's `Lvl` column was really RES until 2026-08-08.

**Derive a new file's map from its `ReadWrite`; never inherit one and never confirm it from one
sample.** Both files are property tables in the same container, which is what makes it tempting.

### `HERORES.PFS` layout — 38 records

Three blocks of twelve races in `RACES12` order, plus two specials:

| ids | block | tag `0x0C` | notes |
|---|---|---|---|
| 0–11 | mounted **Hero** | 0 | |
| 18–29 | **Infantry hero** | 0 | lower HP and MV than the mounted block |
| 36–47 | **Leader** | **2** | ability blob `0x1D` is 82–110 B vs the others' 46–74 |
| 54, 55 | Mind Vessel, Dragon Golem | 0 | |

Ids run in 18-slot groups (12 races + 6 spare) and tag `0x08` is the graphics slot, +18 per race.
⚠ **Key records by position, not by name** — the blocks disagree with themselves (`Lizard` vs
`Lizardman`, `High men` vs `Highman`). `HEROES.PFS` (the 50 named heroes) points at a chassis with
its **tag 8**; the design workbook's `Race` sheet rows 15–26 hold the vanilla statline for the
mounted block only. Read by `read_hero_chassis()` in `build_ziggurat_manual.py`.

**Anything that changes a length is a different job.** Renaming a unit or editing a description
resizes the record, which means rebuilding its property table, every offset after it in the
table, and the root index. Use DevEd for that; it is not worth reimplementing.

### Editing ability sets — done, and in the browser (2026-08-08)

`build_ziggurat_manual.py` embeds `Unitres.pfs` in the manual and ships an **in-browser editor**
(in the Units tab) that adds/removes abilities per medal owner, **assigns levels** (Roman-numeral
buttons capped per ability, both on a chip and in the add-picker so "Marksmanship II" is one
click), and downloads a rebuilt `Unitres.pfs` with the CRC repaired — a full property-table
re-serialiser in JS. It is proven by a **load-time self-test that re-emits the untouched file and
asserts byte-identical** (disabling edit mode if not).

**Verified against Python, twice, 2026-08-09** — ⚠ still *never loaded into the game*:

- *Length-preserving* (Crossbowman copper Marksmanship I→IV): the download differed from the
  original in **exactly one content byte plus the CRC**, and the CRC matched Python `zlib`
  byte-for-byte.
- *Length-changing* (Pikeman + Turn Undead III silver, + Dispel Magic II gold, +39 B): 178 of 179
  records byte-identical, only the edited one differs. A **from-scratch Python reconstruction**
  (swap the body, shift every later u32 index offset, recompute the CRC) produced the same size
  and the same trailing CRC — two independent implementations agreeing on the whole file.
  `re_tools/pfs.py` then re-parsed it and read back both levels correctly.

What made length-changing edits tractable here:

- **The root index is friendly.** Record 0 is the only `u8`-offset (small) entry and is always at
  offset 0; the other 178 are `u32` (wide) and grow freely. So growing any record only shifts
  `u32` offsets — no overflow, no small/wide reshuffle. Keep the exact ctrl/small/wide structure
  and rewrite offset values only.
- **A directory re-emits byte-exact** if you preserve entry order (small entries first, then
  wide), each entry's small/wide flag, and lay the data out in the original offset order. New
  entries: small iff `tag<256 and offset<256`.

### The four ability owners and the level records (measured 2026-08-08)

Every unit record carries **four** ability-set owners, each a `top=False` sub-directory:
`tag 0x19` base · **`0x20` copper** · `0x1E` silver · `0x1F` gold. Inside an owner: `tag 2` =
capacity (u32 bit count), `tag 3` = the ability bitset (bit index == ability id),
**`tag 0x31` = the record-id list (below)**, and `tag 0x32+id` = a per-ability **data record**,
carrying the level for the ids that have one.

#### ⚠⚠ Tag `0x31` — the loader reads ONLY the records this list names

`TAbilityOwner.ReadWrite` @`0x5574F318` does **not** scan an owner for `0x32+id` tags. It reads
the `Engine.TIntegerList` at **tag `0x31`** — format `[u32 0][u32 count][u32 ids…]`, first dword
always 0, insertion order arbitrary (verified across 670 AoWEd-authored owners; trailing slack
after `8+4·count` is ignored — vanilla Carrack gold carries 4 such bytes) — and deserialises
`0x32+id` for exactly those ids. Consequences:

- **A record not listed is dead bytes.** The bit still grants the ability, so the unit gets it at
  **level 0**: a bare name on the card (the level-name caves fall back below level 1) and no
  effect. This is what bare "Leadership" on a silver unit was — not a display bug, not a stale
  grant.
- **The write path emits only listed records too**, so an AoWEd re-save of the resource set
  *permanently deletes* unlisted records. Repair before ever opening the editor on such a file.
- A **listed id with no record** makes the loader read a missing object (removals that forgot the
  list); the engine never writes that shape either.

The manual's in-browser ability editor shipped without this knowledge and broke **71 owners
across 40 units** (every ability it *added*, 2026-08-08 → 2026-08-14 — the Leadership II/III
mints and a large batch of Vision assignments — plus four stale-entry removals). Both ends fixed
and **CONFIRMED WORKING (2026-08-14)** — author-tested in game after the repair:

- `build_scripts/build_unitres_reclist.py` — reconciles every owner's list to its records
  (dry-run default, `--apply`; ⚠ `--undo` just restores `.pre-reclist`, wiping later Unitres
  edits). Idempotent; leaves slack-but-correct owners untouched.
- the editor now syncs the list on every commit (`syncRecList`), mirroring the engine's writer:
  list ≡ records present, dropped when none. Verified by driving the built page headlessly under
  Node: add+remove round-trips the file byte-identically, and a minted add produces a file the
  Python fixer independently declares consistent.

⚠ **An already-granted unit in a SAVE keeps its broken level-0 copy** — grants are snapshots (see
below), so the file repair reaches existing units only on their next rank-up re-grant; base-rank
assignments on existing units never refresh. New games and newly built units are correct.
⚠ **Medals are CUMULATIVE deltas**: the grant loop @`0x557828EC` unions owner
`[type + rank*4 + 0x38]` for every rank up to the unit's, so a gold unit accumulates
base→copper→silver→gold and a later rank's level wins (Bone Horror Marksmanship silver L1 →
gold L2). An empty owner is a single `00` byte.

#### ⚠⚠ A `Unitres.pfs` medal edit does NOT reach units in an existing save

**The grant is a one-off snapshot, then it is serialised.** `TAbilityOwner.UpdateDefaultAbilities`
@`0x5574F518` copies the owner's per-ability data record (level and all) onto the unit with
`TEObject.Copy`, and the unit keeps that copy. It has exactly three callers that matter:

| caller | when | scope |
|---|---|---|
| `TUnit.SetUnitResource` @`0x55782C27` | the unit is created | full |
| `TUnit.SetExperience` @`0x557828B4` | its rank actually **changes** | only the newly-reached ranks |
| `TUnit.NewDay` @`0x55782C98` | **day 1 only** — `cmp [AoWHSMap+0x174], 1` (`+0x174` is the day counter) | wipes with `SetAbCount(0)`, re-grants base→rank |

So an ongoing game **never** re-reads `Unitres.pfs` for a unit that already holds its medal.
`THero.Loaded` calls `UpdateDefaultAbilities`, `TUnit` has no equivalent — heroes refresh on load,
units do not. **Symptom when you forget this: the unit shows the ability at its OLD level** — a
numeral, just the previous one. ⚠ A **bare** name (no numeral at all) is a *different* fault:
level 0, i.e. bit-set-but-no-record — the tag `0x31` trap above. The 2026-08-14 bare-"Leadership"
hunt initially blamed stale grants; that was wrong (the old data would have rendered
"Leadership I", not bare), and the numeral distinguishes the two on sight.

**What does pick the edit up:** a new game (day-1 rebuild), a newly built unit, or a unit that ranks
up *after* the edit. ⚠ A unit already at gold can never rank again, so in that save it is stuck.

⚠ The loop also **never downgrades and never removes** — `if srcLevel <= dstLevel: skip`, and
nothing deletes an ability the data no longer grants. Lowering a level in the data leaves existing
units on the higher one.

The display chain, for reference: `TAbilityOwner.GetAbName` @`0x5574FC14` → `ability.GetName(owner)`
→ `TMultiLevelAbility.GetName` @`0x55765298` = `GetLevelName(GetLevel(owner))`, and
`GetLevel` @`0x557651D8` is just `GetAbilityData(owner, id)[+0xC]`. Tag `0x0A` deserialises to
`[+0xC]` (`TMultiLevelAbilityData.ReadWrite` @`0x55765124`), so **tag `0x0A` is the right byte to
write** — a wrong numeral in game is a stale grant, not a wrong tag. ⚠ Leadership adds a second
level at tag `0x19` → `[+0x10]` and `TLeadershipAbility.GetLevel` @`0x557661C4` returns the **max**
of the two, so tag `0x0A` alone is still sufficient.

#### The level is a FIELD in the record's own directory — never index from either end

A level record is `classid:u32` + an ordinary property directory (`parse_dir(rec, top=True)`),
and the level is a tagged field inside it:

| classid | carries | level at | id at | seen on |
|---|---|---|---|---|
| `0x00022001` | generic multi-level data | **tag `0x0A`** (u8) | tag `0x0B` (u16) | Marksmanship, Turn Undead, Transport, Spell Casting, Vision |
| `0x000202CE` | `TLeadershipAbilityData` | **tag `0x0A`** (u8) | tag `0x0B` (u16) | Leadership |
| `0x000202CD` | `TDispelMagicAbilityData` | **tag `0x0B`** (u8) | — implied by the class | Dispel Magic |

So: read tag `0x0A` if it is ≥1 byte, else tag `0x0B`. Writing that byte is **length-preserving**,
so a level edit never re-lays-out the directory. `_record_level` / `_record_level_pos` in
`build_ziggurat_manual.py` (and `levelPos` in its embedded JS) do exactly this.

⚠ **Do not use the record LENGTH to find the level.** The obvious reading — "12-byte form keeps
it at `[-3]`, 10-byte Dispel-Magic form at `[-1]`" — matches the two common shapes and then fails
silently: a record's span runs to the *next* field's offset, so one at the end of its owner picks
up trailing slack. Vanilla's Galleon carries a **16-byte** Marksmanship record, where `[-3]` is
`0x31` and the manual printed "Marksmanship 49". Harvesting a template must likewise prefer the
**shortest** record seen for an id, or the clone pastes 4 junk bytes.

These are typed ability-data payloads, not plain directories — **do not fabricate one; clone a
template harvested from the file and set the level byte.**

#### Which abilities have a level, and how high — `ability_names.levels()`

**7 levelled abilities, read from the live DLL** (not a hard-coded table — a cap is a mod-tunable
immediate, and this project already raised Leadership's from 1 to 4):

| id | ability | cap | where the cap lives |
|---|---|---|---|
| `0x20` | Marksmanship | 4 | ctor `[self+0x28]` |
| `0x26` | Turn Undead | 4 | own `CanExpand` `cmp eax,4` |
| `0x2E` | Leadership | 4 | ctor `[self+0x28]` (vanilla ctor sets 1) |
| `0x32` | Transport | 7 | ctor `[self+0x28]` — this "level" is carrying capacity |
| `0x34` | Spell Casting | 5 | ctor `[self+0x28]` |
| `0x3C` | Dispel Magic | 3 | own `CanExpand` `cmp eax,3` |
| `0x40` | Vision | 4 | ctor `[self+0x28]` |

`CanExpand` is the authority — whatever it compares the current level against IS the ceiling —
and there are **two families that must both be handled**:

1. `TMultiLevelAbility` descendants: `CanExpand` is `SETL` on `level < [self+0x28]`, and
   `[+0x28]` is an immediate in the ctor. `TMultiLevelAbility.Create` @`0x55765168` seeds **4**;
   a subclass overrides it (`0x55765192` is the base's write).
2. Levelled classes that are **not** `TMultiLevelAbility`: `TTurnUndeadAbility` and
   `TDispelMagicAbility` descend from `TTouchAbility : TAbility` and hard-code the ceiling as
   `call [reg+0x70]` (GetLevel) → `cmp eax, imm; jl`. Chasing only family 1 silently drops both.

Two traps that cost real time here, both now guarded in `levels()`:

- **A byte window around the id write is not a function.** ±256 B both *missed*
  `TTurnUndeadAbility.Create` (it reaches the base only via `TTouchAbility.Create`) and *invented*
  a levelled "Cosmetic Surgery" from a neighbouring function's bytes. The DLL exports 10,036
  symbols — take exact bounds from them.
- **Reachability must follow ctor→ctor edges only.** Transitive closure over *any* call marked
  `TConstructAbility` (a plain `TAbility`, no levels) as multi-level through some helper several
  hops down. Require both caller and callee to end in `.Create`.

⚠ **A `0x32+id` record does not prove the ability is levelled.** `Walking` (`0x00`) has no
multi-level ctor at all, yet one owner in `Unitres.pfs` carries tag `0x32` holding `0xDD` — some
other per-owner datum. 145 units have Walking with no record at all. Trust the scan, not the tag.

Ability id → name is resolved by `re_tools/ability_names.py` (curated map + DLL constructor scan
+ the game's own RT_STRING table; 150 ids, all 109 unit abilities named).

**Always repair the CRC last**, after every byte edit, or the file is dead — and **check it first,
on the file as read, before touching a byte.** A writer that only repairs will happily stamp a valid
checksum over pre-existing damage, which destroys the one piece of evidence that anything was ever
wrong: after that the file looks intact to every tool, including this one. Gate on the residue and
refuse to proceed:

```python
if zlib.crc32(d[4:]) & 0xFFFFFFFF != 0x2144DF1C:
    sys.exit("ABORT: already damaged before any edit — refusing to rewrite")
```

Put the gate where *every* path reaches the file, not just the write path, so a dry run reports the
damage too. `build_vision9.py` gates inside its pure `pfs_plan`; `build_drillmaster.py` gates inside
`pfs_tag9_offset`, which its read, its dry-run report and its write all funnel through. Use
`sys.exit`, never `assert` — `python -O` strips asserts, and a stripped guard here writes a dead file
without a word.

Be honest about the reach: the residue **catches incoherent damage** (a flipped byte, a nudged
offset, a truncation — anything the stored CRC no longer matches) and **misses a coherent-but-wrong
layout** that was re-CRC'd. Nothing cheap catches that second class.

### Editing a string field — `build_scripts/build_pfs_typos.py`

The generic, table-driven writer for text corrections. One row per fix — file, record id, tag, the
old substring, the new one — and it does the whole length-changing dance: body directory, every
later index offset, the CRC. Dry-run default, `--apply`, surgical `--undo`, `--dis` to print the
strings. First use was Charm's `humaoid` → `humanoid` (2026-08-09).

Three things it knows that a one-off script tends not to:

- ⚠ **A record body directory can MIX small and wide entries.** `body[0]` is `small | 0x80`, and
  when the high bit is set a **`u32` wide count follows** before the entries. Charm's record 158 is
  4 small + 1 wide (tag 9 sits at offset 305, past the u8 ceiling). `build_vision9.py`'s writer
  deliberately **refuses** wide bodies — it was verified only against the pure-small form — so it
  cannot edit this record at all. Handle both, or say which you handle and abort on the other.
- ⚠ **Two string forms, and `pfs.pstr()` only knows one.** Descriptions (tag 5) are
  **`u32`-length-prefixed**; names (tag 10) are **`u8` Pascal**. Sniff by whether `4 + n` or
  `1 + n` equals the field length, and refuse anything that is neither — that is what stops an
  integer field being rewritten as text. The one ambiguous case, a 4-byte zero, decodes as the
  empty string and can never contain the substring a fix looks for.
- **The fields must TILE the rebuilt payload exactly** — no gap, no overlap. Unlike the backwards
  tiling in *Failed/rejected* below this is **not** circular: the field *lengths* come from the old
  offsets and the *placement* from the new ones, so an off-by-one in the shift shows up as a hole.

Its refusals, all exercised: damaged file before any edit; the substring absent (someone else
edited the text); both spellings present; the field not a string; no such record; a shifted u8
offset over 255.

Two guards on the state, because "is this applied?" must be answerable: `old` must occur **exactly
once**, and `old` and `new` must not be substrings of each other (checked at start-up for the whole
table). The `.pre-typos` snapshot is taken **only on the first apply, while nothing in that file is
patched yet, and never overwritten** — otherwise a later run against an already-patched file would
mint exactly the lying backup CLAUDE.md warns about.

## Failed/rejected approaches

- **Treating the first dword as a plain magic constant and ignoring the tail.** Works for
  reading, and is what the shared AoWx notes describe, but silently loses the checksum on any
  write. Anything that writes a `.pfs` must recompute the trailing dword.
- **Reusing `hss_crc.py` directly.** Wrong region (`d[:-4]` vs `d[4:-4]`); its `--fix` would
  write a checksum the engine will not accept.
- **⚠ Verifying the layout by tiling record bodies backwards from EOF and comparing the result to
  the index offsets.** Looks like a sound integrity check and is **circular — it can never fail**:
  `parse_index` derives each body as a slice *at* the very offset being re-derived, so tiling
  backwards reproduces the same start by construction. It proves slicing is deterministic, nothing
  more. It was in `build_vision9.py` (where it passed a deliberate +3 offset nudge) and in
  `build_drillmaster.py`; both were replaced with the CRC gate above on 2026-08-09, and both carry a
  comment saying not to bring it back. Do not re-derive it — the temptation is that it *reads* like
  the check you want.

## Related

- `re_tools/pfs.py` — reader (index + property tables + ability owners)
- `build_scripts/build_pfs_typos.py` — table-driven string/typo writer (see above)
- `re_tools/reconcile_units.py` — workbook vs `Unitres.pfs` stat diff
- `build_ziggurat_manual.py` — reads `Unitres.pfs` for the manual's live unit stats
- `re_tools/hss_crc.py` — the `.hss` sibling, and where the CRC-32 algorithm was decoded
