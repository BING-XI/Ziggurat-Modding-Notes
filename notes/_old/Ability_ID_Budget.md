# AoW1 — How many new abilities can be added? (Ability-ID budget)

*Consolidated 2026-07-24 from the 2026-07-05 feasibility study, the 2026-07-20 measurement
session, and follow-up notes. Self-contained: written to be usable without any other doc, though
`Adding_New_Spells_Abilities_2026-07-05.md` holds the wider spell/ability-adding context.
All addresses are AoWEPACK.dpl preferred-base VAs (0x55800000-region); the DPL rebases at
runtime, so patches must stay position-independent.*

## TL;DR

- **⚠ NEVER QUOTE THE FREE-ID NUMBER FROM THIS DOC — MEASURE IT.** This section has now gone
  stale *twice* the same way (`0xAA` in 2026-08-07, then `0xAB`–`0xB0` by 2026-08-31), because
  each new ability silently invalidates it. Registering a taken id raises an unhandled exception
  during init that Delphi reports as a bare **`Runtime error 217`** — nothing in the message
  mentions abilities, so the cost of trusting a stale figure is an opaque startup crash.
  **The measurement**: `mov eax,<id>; call CreateEnhancementAbility` sites in the DLL, plus
  `Release/Ability.pfs` record keys (key = id + 10). `build_scripts/build_drillmaster.py:
  check_id_free()` does exactly that and aborts before writing — clone it into every new script.
  ⚠ That scan misses **class-based** registrations; `re_tools/ability_names.py`'s constructor
  scan is the authoritative cross-check (66 ctor-derived ids, highest `0xA9`).
- **Measured 2026-09-02** against the live registry (Count 179): **highest in use `0xB2`**
  (Embrittled). Taken since 2026-08-31: `0xB1` Reforming Flesh, `0xB2` Embrittled, and — from
  vanilla **holes below 170** — `0x88` Can Command Undead, `0x89` Commanded Undead.
- **The budget, structurally (see §0):**

  | kind | constraint | room as of 2026-09-02 |
  |---|---|---|
  | stateful (per-unit data record) | save-tag byte: id ≤ `0xCD` | **27** above the max (`0xB3`–`0xCD`) + up to **19** verified gaps below 170 |
  | bit-only passive | not bound by the tag | `0xCE`–`0xFF`, **50** more — *untested*; one save/load round-trip settles it |

  ⚠ Those counts go stale with every new ability. Measure; do not quote.
- **Hard ceiling: id ≤ `0xCD` (205)** for any ability with a per-owner data record. This is a
  save-format limit, not a registry limit.
- A figure of "~116 free slots" circulated from an early static sweep. **It is wrong** — the
  sweep provably undercounts vanilla usage (see §3). Gaps below `0xA9` are usable but **must be
  verified per-id** (a nil registry slot ≠ unreferenced): the procedure is in §0.
- ⭐ **The limits were never mainly numeric.** Every ceiling met so far was a *fixed-size table or
  hard-coded id chain* — `AbilTypes` (170 B, tactical), the per-module loop terminators, the
  `ShowEx` icon chain — each found because something crashed or silently did nothing. §0 is the
  first time they are all on one page; assume the list is complete only for `AoWTCPCK.dpl`, whose
  range checks make its tables *visible*. `AoW.exe` has no range checks, so an unchecked table
  there would read garbage silently.
- **Bit-only abilities** (plain passives, no per-owner record) are not bound by the `0xCD`
  ceiling *in principle* — every relevant structure auto-grows, and since 2026-09-02 the tactical
  tables reach 255 too — but this is **untested above `0xCD`**; one save/load round-trip settles it.

## 0. What changed on 2026-09-02 — read this before the sections below

Two findings from the Turn Undead work revise the budget's *shape* (not its counts — measure those):

- **The `[0..169]` hardware `BOUND` in `AoWTCPCK.dpl` is GONE as a ceiling.** It guarded
  `AoWTC.AbilTypes`, a 170-byte per-id category table, and it was a *live crash* for any enabled
  id 170–178 once the AI scan loops were raised (`Error during TCAI Create Unit List`, observed in
  game 2026-09-01). `build_abiltypes_relocate.py` (CONFIRMED WORKING 2026-09-02) moved the table to
  **`0x00469440`, 256 entries**, and raised all nine limit pairs to `{0,255}`. A full census of all
  371 `bound` sites in the module shows **no other ability-indexed fixed table** — the `hi=130`
  tables are `SpellTypes` (spell ids, a separate ceiling). ⇒ On the tactical side, ids up to **255**
  now pass every check. The old "above 169, passives only" rule in `ID_Ceilings.md` is obsolete.
- **Gaps BELOW 170 are real, usable ids.** Turn Undead took `0x88`/`0x89` from vanilla holes. The
  live registry (Count 179) has **19 remaining nil slots**: `0x21, 0x4E–0x55, 0x5B, 0x66–0x69, 0x6E,
  0x85, 0x86, 0x87, 0x97`. ⚠ A nil slot proves nothing *registers* the id; it does not prove nothing
  *references* it by constant (cut content may still be checked somewhere). Per-id verification =
  scan both binaries for `mov edx,<id>` / `push <id>` feeding an ability call — the global scan QA ran
  for `0x88`/`0x89` is the template.

**The budget now, structurally.** Stateful (data-record) abilities remain bound by the save-tag byte:
id ≤ `0xCD`. Free above the current max (`0xB2`): `0xB3`–`0xCD` = **27**, plus up to **19** verified
gaps below 170. Bit-only passives are additionally *not* bound by the tag and can in principle use
`0xCE`–`0xFF` (**50** more) — still untested; one save/load round-trip settles it. ⚠ `AoW.exe` was
compiled *without* range checks, so an unchecked fixed table there would read garbage silently rather
than crash; none has been found, but "none found" is weaker than the TCPCK census.

**Every new ability now needs, beyond a free id and registration:** an `Ability.pfs` record (key =
id+10); a **category byte at `[0x00469440 + id]`** if it is an action (0 is inert everywhere — the AI
skips it and clicking it deselects); the two loop ceilings bumped; and, if it should draw a
persistent overhead icon, **its own block in `TAbstractUnit.ShowEx`'s hard-coded chain** — see
`TurnUndead_EvilCommand_Design.md`.

**The `ShowEx` icon chain, for reference** (`TAbstractUnit.ShowEx @0x557812EC`, 2026-09-02). Persistent
status icons are drawn ONLY for these ids, each by an explicit
`if GetAbilityEnabled(unit,id) then ShowLooped(GetAbility(id)->[+0x1C]) at (x+0x20, y+0x28)` block,
in this order: `0x60, 0x62, 0x5D, 0x91, 0x04, 0x30 Seduced, 0x96 Dominated, 0x95 Charmed, 0x61, 0x5C,
0x5F, 0x5E, 0x7F, 0x6B Possessed, 0x22 Turned Undead, 0x46` — plus, since 2026-09-02, `0x89` via
`cave_ankh`. The `.pfs` tag-8 image sequence is the *supply*; this chain is the only *consumer*. A
status ability absent from it draws nothing, however good its record. Worked example of adding one:
`build_turnundead_evilcommand.py` (`cave_ankh`, a `call rel32` retarget at the epilogue `0x55781A2E`).

## 1. The hard ceiling: id ≤ 0xCD (205)

Applies to any ability that carries a **per-owner data record** — multi-level / stateful
abilities such as Leadership, Marksmanship, Spellcasting.

Why: `TAbilityOwner.ReadWrite` @ `0x5574F318` serialises each ability-data record under a
property tag of **`0x32 + abilityID`** (`add eax, 0x32` @ `0x5574F484`), and the property tag is
**one byte** on disk. So `0x32 + id ≤ 0xFF` ⇒ **`id ≤ 0xCD`**. Exceeding it wraps/collides with
other tags and corrupts the record on save/load.

Verified empirically against `<game dir>\Release\Unitres.pfs`: a real owner's property table at
file offset `0x87C` reads `05 | 02 00 | 03 04 | 31 0a | 52 1a | 60 26` — i.e.
`count, (tag,offset)×5` — where tag `0x52` decodes to id `0x20` (Marksmanship) and tag `0x60` to
id `0x2E` (Leadership).

## 2. What is NOT the limit (all auto-grow)

- **Registry**: `TAbilityControl.GetAbility` @ `0x557501C0` is a plain `TList` indexed by id
  (`items[id]`, bounds-checked vs Count). `RegisterAbility` @ `0x55750238` grows the list and
  asserts `"Ability already registered (n)"` on a duplicate id.
- **Per-owner bitset**: `SetAbSet` @ `0x5574E0BC` auto-grows (`if id >= count:
  SetAbCount(id+1)`); `SetAbCount` @ `0x5574E0F8` only asserts against `0x7FFFFFF`.
- **Bitset serialisation**: count under tag 2, bits under tag 3 as `(count+7)/8` raw bytes —
  width scales with the highest id, no fixed cap.

Consequence: a **bit-only** ability (most plain passives) has no per-owner record and is
therefore not bound by §1 in principle. **Untested above `0xCD`** — if you try it, do a full
save/load round-trip test (and an MP sync test if relevant) before shipping.

## 2b. ⚠ ABILITY **LEVELS** COST NOTHING FROM THIS BUDGET (verified 2026-08-09)

A recurring scoping question: *does raising a multi-level ability's cap (Leadership → IV, Dispel
Magic → V) eat into the `0xAA`–`0xCD` id budget?* **No. It is a completely different resource.**

A `TMultiLevelAbility` is **one id**. `Expand` @ `0x55765378` shows the whole model:

```
data = owner.GetAbilityData(ability[+0x0C])        // +0x0C = the ability id
if data = nil:
    data = AbilityDataClass.Create
    data[+0x0E] := abilityId  (word)
    data[+0x0C] := 1                                // <-- THE LEVEL, a per-owner byte
    TAbility.SetAb(owner, id, 1)                    // one bit in the owner's ability set
    owner.AddAbilityData(data)
else if data[+0x0C] <> ability[+0x28]:
    data[+0x0C] := data[+0x0C] + 1                  // level up, in place
```

So a level is **a byte inside the owner's single data record for that id** — no extra id, no extra
registry slot, no extra bitset bit, no extra save property tag (§1's `0x32+id` is per *id*).
The level byte serialises as tag 10 of `TMultiLevelAbilityData.ReadWrite` @ `0x55765124`, inside
the record that already exists, so raising a cap is save-compatible
(see the id-indexed property-table model — growing a record is backward-compatible).

**What a level actually costs, all per-ability and all local:**

| thing | where | note |
|---|---|---|
| the cap | `ability[+0x28]`, a **dword** set in that ability's `Create` | base `TMultiLevelAbility.Create` @ `0x55765168` defaults it to **4**; Leadership's `Create` stomps it to 1. ⚠ **Not every levelled ability uses this field** — see the row below |
| ⚠ …or a hard-coded immediate | **Dispel Magic ignores `[+0x28]` entirely** | it overrides the machinery with its own `cmp` against **3** in *two* places — `CanExpand` @ `0x5576D163` and `Expand` @ `0x5576D1D0` — and keeps its level at `TDispelMagicAbilityData` **+0x0D** (not the base class's +0x0C; +0x0C is its per-turn enabled toggle). Patching `[+0x28]` on it does nothing. **Always find the cap by reading `CanExpand`/`Expand`, never by assuming the base field.** (`build_dispelmagic5.py`) |
| per-level skill-point cost | `ability[+0x2C]`, a `TIntegerList` | `ExpandCost` @ `0x557652E4` reads `costList[currentLevel + 1]` — **must be populated up to the cap** or levelling reads past the end |
| per-level effect data | that ability's own bonus table | ⚠ **this is the real constraint.** Leadership's atk/def tables were fixed-size in DATA and 4+ levels collided with adjacent data, so `build_leadership4.py` relocated them to `0x5580F0C0`/`0x5580F0C8` |
| level names | `GetLevelName` | Leadership reused Marksmanship's " I".." IV" literals via a VMT `+0x10C` repoint rather than minting strings |
| ceiling on the level itself | the level is a **byte** | ≤ 255 in principle; nobody has gone past 5 |

`CanExpand` @ `0x55765308` gates on `selectionMask & ability[+0x20]` **and** `GetLevel(owner) <
ability[+0x28]` — so the selection-mask trap (§5 / `Ability.pfs` tag 9) applies to *offering* the
upgrade, independently of the cap.

**Prior art, both confirmed working in-game:** `build_leadership4.py` (cap 1 → 4) and Inioch's
`patch_dispelmagic5_v1.py` (cap 3 → 5). The Leadership feature working with the cap changed only in
`Create` is the empirical evidence that the **code-side cap is authoritative** — `Ability.pfs` does
not appear to override it the way it overrides the selection mask.

## 3. Why "~116 free" is fiction — the static-sweep undercount

A static sweep (constructor immediates `mov [reg+0x0C], imm32`, plus ids passed to the 23
`CreateEnhancementAbility` @ `0x5576601C` call sites) recovers **90 ids spanning `0x01`–`0xA9`**,
which naively suggests ~116 free slots under the `0xCD` ceiling.

**The sweep is a lower bound on usage.** It cannot see ids that never appear as an immediate,
and it provably missed real vanilla ids: `0x2A` Tunneling, `0x70` Monster Slaying, `0x76` Life
Stealing — and a mod-added id (`0x9F`, Path of Sand) as well. It also produces false positives:
`0xFA` matches the ctor byte pattern but is city-AI code in
`TCityAIPA.Process`/`ValidateUpgradeBudget`, not an ability.

**So: never treat an apparent gap below `0xA9` as free.** The only safe test is dynamic —
register the id and watch for the `"Ability already registered"` assert. Ids `0x38` (Assassin)
and `0x9F` (Path of Sand) were claimed exactly this way and confirmed working in-game.

## 4. The recommended range

Highest vanilla id = **`0xA9`** (Dark Gift).

⇒ **Use `0xB2`–`0xCD`: 28 contiguous free ids** (as measured 2026-08-31), above everything in
use and under the ceiling. This also satisfies the ID-stability rule: saves and MP reference
ability ids, so pick your ids once and freeze them.

⚠ **This number shrinks every time an ability is added, and this line will be wrong again.**
It has already been corrected twice (`0xAA`–`0xCD` → `0xAB`–`0xCD` → `0xB2`–`0xCD`). Re-measure
with `check_id_free()`; do not quote it.

If more than 36 stateful abilities are ever needed, the options are:
1. Reclaim verified-free gaps below `0xA9` (per-id dynamic verification, §3).
2. Go bit-only above `0xCD` for passives (untested, §2).
3. Widen the record tag — a **save-format change that breaks compatibility**; last resort.

Treat 36 as the practical budget.

## 5. Registration mechanics (context for actually adding one)

- Abilities are compiled Delphi flyweight singletons in a global registry (`TAbilityControl` @
  `AoWHSSet+0x80`; spells parallel it via `TSpellControl` @ `AoWHSSet+0x84`). The ability id is
  set in each constructor at object offset `+0xC` (spell id at `+0x10`).
- Research/spellbook/MP/save all *filter the registry*, so new registrations propagate
  automatically — no UI patches needed.
- Clones of existing ability classes are easy via an init cave; new behaviour = clone the VMT at
  runtime in the cave (avoids `.reloc` surgery and survives DPL rebasing). Whole packs of new
  archetypes are the tipping point for a companion DLL (all needed APIs are exported by name).
- AI: clones inherit their base class's AI virtuals and get used sensibly; novel archetypes are
  ignored by the AI unless handlers are written.
- All peers in MP must run identical modded binaries.
- ⚠ **`CreateEnhancementAbility`'s third argument is a selection-type bitmask, not an icon.** Get
  it wrong and the ability registers, assigns, displays and *works* — and is simply never offered
  at hero level-up. The dialog needs `0x100 astHeroUpgrade` **and** `0x200 astEditor`, tested in
  two different places, and **`Release/Ability.pfs` tag 9 overwrites whatever the cave passed**
  (0 of 21 vanilla sites agree with their own data file). Full decode, RTTI enum and addresses:
  `Drillmaster_Ability.md` §"The selection mask".

## Provenance

Measured 2026-07-20 against the installed game (note: installed data is the **Ziggurat** mod,
but the id ceiling and registry mechanics are engine-side and mod-independent). Empirical
anchors: `Unitres.pfs` property table decode (§1), duplicate-register asserts on `0x38`/`0x9F`
(§3), both mod abilities confirmed working in-game.
