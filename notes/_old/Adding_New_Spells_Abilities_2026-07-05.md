# Adding New Spells / Abilities to AoW1 — Feasibility Notes (2026-07-05)

> **UPDATE 2026-07-08 — PROVEN for abilities.** The first from-scratch ability, **Path of Sand**, is
> implemented and CONFIRMED WORKING in-game via exactly the Tier-1 clone recipe below (init cave hooked
> into `PassiveAb.RegisterPassiveAbilities`, `CreateEnhancementAbility(id,name,icon)` + `RegisterAbility`,
> literal AnsiString name, reused category word). See `Path_Of_Sand_NewAbility.md`. Practical gotchas found:
> (1) unit abilities live in a per-unit **width-checked bitset** (`GetAbilitySet`) but the setter auto-grows
> so ids aren't capped; (2) `ListAbilities` filters by the `+0x20` **category** word — reuse an existing
> one so the new ability lists where you expect; (3) **abilities have no icons** in AoW1 (text only);
> (4) behaviour that hangs off a hard-coded per-ability dispatch (like the Paths in `MovedTo`) needs a
> matching dispatch cave, and inherits that call site's gates (e.g. Paths are suppressed on Transport units).

Follow-up to `Unit_Spellcasting_Feasibility_2026-07-05.md` (same session, same evidence base:
Ghidra decompilation of AoWEPACK.dpl @ preferred base 0x55700000, full Delphi 3 symbols).

**Question:** How hard is it to outright add NEW spells or abilities to the game?

**Verdict:** Feasible. "More of the same" spells (re-parameterized clones of existing spell
classes) are *easier* than the unit-spellcasting mod. Genuinely novel mechanics are harder, and
adding a whole spell pack is the first AoW1 mod where a **companion DLL genuinely earns its keep**
(for the unit-spellcasting mod it was unnecessary; here it replaces writing gameplay logic in
position-independent assembly).

---

## 1. How spells are defined (verified mechanics)

Spells are **compiled Delphi classes, not data** — but the architecture is registry-based and
unusually mod-friendly:

- Every spell is a **singleton object** in a global registry (`TSpellControl`, at `AoWHSSet+0x84`).
  Registration happens at engine startup via per-unit functions like
  `CitySpells.RegisterCitySpells` (0x557B25EC), which:
  1. registers the spell's turn-event classes with the engine
     (`Engine.TEngine.RegisterEClasses` — the save/network class-identity registry), then
  2. constructs each spell singleton and calls `TSpellControl.RegisterSpell` (0x55779B40).
- `RegisterSpell` mechanics: spell ID is read from **spell+0x10 — a fixed constant the spell's own
  constructor sets** (not auto-assigned). The registry is a `TList` indexed by ID; it **grows on
  demand** (no fixed capacity), and raises "Spell already registered (n)" on collision. It also
  calls `TImageSequenceList.LinkToIL(spell+0x2C)` — linking the spell's graphics to the game's
  image libraries.
- `TSpell.Create` (0x55779178) builds per-spell infrastructure: +0x24 `TStringList`
  (description text), +0x28 `TSFXLibrary` node (sounds), +0x2C `TImageSequenceList` linked to
  `AoWHSSet+0x2C` (icons/animation), +0x18 = 1, +0xC default byte. Other known fields:
  +0x8 name (AnsiString), +0x10 ID, +0x14 mana cost, +0x20 sphere, +0x22 spell type
  (0/1 combat-capable, 2 global — from CanCastSpell/CanCastCombatSpell usage).
- A concrete spell is TINY. `CitySpells.TAnarchy.Create` (0x557B1EF8) in full:
  inherited `TCityTargetSpell.Create` → name := Translate(LoadResString(AnarchyRStr)) →
  **ID := 0x48** → one parameter byte at +0x38. That's the whole definition; all heavy machinery
  (targeting UI, TE creation/validation, network sync, animation playback, casting economics)
  lives in generic base classes: `TCityTargetSpell`, `TCityEnchantmentSpell`, `TSummonSpell`,
  `TUnitSpell`, `TCombatSpell`, `TGlobalEnchantmentSpell`, `TGlobalTargetSpell`, etc.
- **Everything downstream is registry-driven.** Research candidates
  (`TPlayerMagicControl.ListResearchSpells/ValidResearchSpell`), spellbooks
  (`TPlayerMagicControl.ListSpells`), hero/leader casting, saves, and MP all filter the registry
  by ID + metadata (sphere/level/type). A newly registered spell with valid metadata propagates
  into research, spellbook UI, and multiplayer **automatically — no UI patches needed** (unlike
  the unit-spellcasting mod, whose difficulty was all in gates/UI).

## 2. How abilities are defined

Exact mirror of the spell system:

- Global registry `TAbilityControl` (`AoWHSSet+0x80`): `RegisterAbility` (0x55750238),
  `GetAbility(id)` (0x557501C0), `ListAbilities`, `UnregisterAbility(ID)` — same fixed-ID pattern
  (Spellcasting = 0x34, set in `TSpellCastingAbility.Create` at +0xC).
- Ability base classes: `TAbility` (0x5574E5F4 Create) and `TMultiLevelAbility` (leveled
  abilities with per-level expand costs via a TIntegerList — see TSpellCastingAbility.Create:
  5 levels, 20 skill points each).
- **The engine queries ability behavior through virtuals on the ability object** —
  `GetImmunityTypes`, `GetProtectionTypes`, `GetAttack/GetDefense/GetResistance/GetDamage`,
  `GetMoveTypes`, `GetWallCombatFeatures`, `NewDay/NewTurn/NewCombatTurn`, `CanActivate/Activate`
  (strategic button), `fc*/tc*` combat-command methods, `GetControlType` (how the UI renders it).
  New abilities therefore plug into combat math and UI **without touching any caller**.
- Ability assignment to units lives in the game library data (unit-type ability sets, edited via
  DevEd) or via enchantments (`TUnitEnchantmentAbility` pattern). Since the editors load the same
  AoWEPACK.dpl, newly registered abilities should appear in editor lists automatically —
  **verify this** (10-minute check) before committing to an ability project.

## 3. Difficulty tiers

### Tier 1 — Re-parameterized clones (EASY–MODERATE; easier than the unit-spellcasting mod)
New summon with a different creature, damage spell with different element/cost/sphere,
stat-tweaked enchantment, new passive ability reusing existing query virtuals:

- Init cave (hooked after an existing Register* call): instantiate an EXISTING spell/ability class
  (its class-ref/VMT is in the file), poke fields post-Create (ID, name, cost, sphere, level,
  payload params like summoned-unit index), call RegisterSpell/RegisterAbility.
- Name strings: `TranslateRStr` path can be bypassed by assigning a raw string — use the exported
  `System.@LStrAsg` family to respect Delphi string refcounting; never write the pointer directly.
- Icons/sounds: the spell's TImageSequenceList/TSFXLibrary nodes reference existing game art by
  library link; custom art possible via ILB tooling (IlbMaker present in game dir).

### Tier 2 — New behavior on an existing pattern (MODERATE–HARD in pure caves)
New effect logic (new city enchantment effect, new unit enchantment, new active combat ability):

- Requires a new class: clone a base VMT and repoint the behavior slots (ExecuteTE, ValidTarget*,
  fcExecuteCombatCommand, ...) at cave code.
- **Reloc-avoidance trick:** build the cloned VMT AT RUNTIME in the init cave (allocate, memcpy
  the original VMT, patch slots) instead of placing a VMT in the file — sidesteps .reloc-table
  surgery entirely and stays compatible with the DPL's guaranteed rebasing
  (see AoWEPACK rebasing notes).
- The real cost is authoring effect logic in position-independent assembly.

### Tier 3 — New spell archetypes (HARD in pure caves; DLL recommended)
New targeting modes or new turn-event types:

- Must register new TE classes via `RegisterEClasses` (mechanism exists and is exported) with
  unique ClassIDs (save + network identity).
- Each spell becomes a mini-project in asm; this is the tipping point for a companion DLL.

## 4. The companion-DLL option (now genuinely useful)

The unit-spellcasting mod didn't need a DLL (its problem was storage/gates). Adding content is an
*authoring* problem, and the Delphi package system helps: **every needed API is exported by
name** — `TSpell.Create`, base-class constructors, `RegisterSpell`, `RegisterEClasses`,
TSpellControl/TAbilityControl methods, even System string helpers.

- A small DLL (Free Pascal mimicking the mapped Delphi 3 object/VMT layout, or C with hand-built
  VMT structs) imports those and registers whole spell packs in readable high-level code.
- Loading vector: one added import-descriptor entry in AoWEPACK.dpl, or a `LoadLibrary` call in a
  tiny init cave.
- Rule of thumb: **1–3 cloned spells → pure caves; a spell pack or new archetypes → DLL.**

## 4b. How many ability IDs are available?

Moved to **`Ability_ID_Budget.md`** (consolidated 2026-07-24, self-contained). Summary: hard
ceiling id ≤ `0xCD` (one-byte save property tag `0x32+id`); **`0xAA`–`0xCD` = 36 safe contiguous
free ids** (highest vanilla id `0xA9`); apparent gaps below `0xA9` must be verified per-id (the
static sweep undercounts); bit-only passives are unbounded in principle but untested above `0xCD`.

## 5. Caveats

1. **ID stability**: saves and MP reference spell/ability IDs; pick free ids and freeze them.
   **Abilities**: above vanilla max — `0xAA`–`0xCD` (§4b). **Spells: the OPPOSITE — stay BELOW
   the vanilla combat band**: use **79–99 or 109**; ids ≥ 131 break the `SpellTypes[0..130]`
   table (range-check errors in tactical combat, out-of-bounds reads in the exe) — see §7.
2. **AI**: cloned spells inherit their base class's AI virtuals
   (`AIPrefetchCastSpellActions`, `AIRequestCastSpellExpense`, ...) so the AI uses them sensibly.
   Novel archetypes are simply ignored by AI unless handlers are written.
3. **Editor round-trip**: verify DevEd lists new registered abilities/spells (expected, since it
   loads the same packages) and that library files store the new IDs cleanly.
4. **Localization**: raw-string names bypass the translation tables cleanly; localized names would
   need Localize.dpl resource additions (not investigated).
5. **MP**: as always, all peers must run identical modded binaries (+ DLL if used).

## 6. Suggested first project (when implementing)

A Tier-1 clone — e.g. a new summon spell with a different creature and sphere — exercises the
entire pipeline (registration, research, spellbook, casting, TE, save, AI) with near-zero new
logic. Verify: appears in research list, researchable, castable by wizard AND heroes, AI casts it,
save/load round-trips, MP sync. Then escalate tiers as desired.

---

## 7. Spell-ID budget, Spells.pfs anatomy, and the SpellTypes table (measured 2026-07-30)

Static analysis, not yet exercised in-game. Evidence: Ghidra (AoWEPACK.dpl), capstone
(`re_tools/dasm.py` on AoWTCPCK.dpl / EngineP.dpl / AoW.exe), `re_tools/pfs.py` on the installed
(Ziggurat) `Release/Spells.pfs`, plus a whole-DLL sweep for the ctor idiom `mov [reg+0x10], imm32`.

### 7a. The vanilla spell-ID map

**Ids 1–78 = strategic spells** (11 registration units: GlobalTargetSpells, Mountain, CitySpells,
PoisonP, HolyG, UnHolyG, Storms, SummonSpells, UnitSpells, GlobalSpells, GlobalEnchantmentSpells);
**ids 100–130 = the CombatSpells unit** (combat spells); **109 is the only hole**. Total = 108,
reconciling three independent sources exactly: 108 `RegisterSpell` call sites, 108 ctor-sweep ids,
108 `Spells.pfs` records. All registration is reached from **`AoWEReg.AoWEReg`** (call to
RegisterCitySpells @`0x557fac1b`) during **package init at DLL load** — i.e. *before* any set/.pfs
load, so a cave-registered spell exists when the .pfs pass runs.

### 7b. No serialization ceiling (unlike abilities)

Spell ids are 32-bit in every serialized reference found — there is **no analog of the ability
one-byte `0x32+id` tag ceiling**:

| Where | Field | Width |
|---|---|---|
| researched-spell list | `TPlayerMagicControl+0x30`, tag 0x16 | `TIntegerList.SaveToStream` (EngineP.dpl @0x5551424C) writes 4-byte count + 4-byte elements |
| current research | `+0x34`, tag 0x17 | int |
| research/mana TE (MP wire) | `TChangePlayerMagicTE+0x14`, tag 0x16 | int (ReadWrite @0x5577D840) |
| Tome items | `TItem+0x38`, tag 0x14 (use-type byte `+0x34` = 5) | int (ExecuteUse @0x55793F68 passes it to ExecuteSpellResearched) |
| hero cast state | `THero +0x84/+0x88/+0x8C/+0x90` | ints (+0x90 = int-with-default −1) |
| .pfs record key | record id = spell id + 10 | directory supports u32 wide keys (Unitres.pfs already uses keys > 255) |

### 7c. THE constraint: `AoWTC.SpellTypes` — byte[0..130] in AoWTCPCK.dpl

`AoWTC.SpellTypes` @ **0x4672F4** (AoWTCPCK.dpl DATA, exported; **AoW.exe imports it at IAT slot
`0x45EBEC`**) is a **132-byte** table, declared range **[0,130]** (Delphi `bound` pairs @0x4180E8
and @0x41B034; byte 131 = padding). `SpellTypes[id]` = the spell's **tactical-combat class**
(0 = not castable in combat). Vanilla: sparse nonzero entries below 100 (the unit-target spells
usable in combat, mostly 0x07), rich values for 100–130, `SpellTypes[109] = 0` (matches the
registry hole). Consumers:

- **Exe research-book filter** @0x42F304 (inside the population fn; the id `cmp` @0x42F2F1 now
  hosts the tier-research nilguard cave, original bytes `83 78 10 64 7C 29`): ids < 100 skip the
  check; ids ≥ 100 with `SpellTypes[id] == 0` are deleted from the research list. **This read has
  NO bound check** — an id ≥ 131 reads whatever data follows the table.
- **Combat AI**: `TCAI.CheckUnit` @0x4159EC — `movzx` of `SpellTypes[id]` into a **0x30-case
  jumptable** @0x415A02 (per-class tactical evaluation); `TCAI.EvalBattle` (4 sites) iterates ids
  0..130 testing `SpellTypes[id] != 0`; `TCAI.EvalPath`.
- **Combat targeting UI**: `TTacticalCombatUnitHS.SelectSpell`, `TCombatUnitSelectionControl.
  CalculateRangedPath` / `ExecuteMoveSelection`, `MakeAbilPath`, `TRangedPathHS.Show` — the
  targeting/path behavior of a selected combat spell is keyed by its class byte.
- **AoWDevEd.exe does NOT import it** — editor listing is unaffected.

**Consequences:**

- **22 immediately safe new ids: 79–99 and 109.** All are in-range for SpellTypes.
  **Strategic-only spells: use 79–99** (byte stays 0; ids < 100 never hit the research filter).
  **Combat-castable spells: any of the 22**, with the SpellTypes byte set to the donor spell's
  class value — a **one-byte file patch in AoWTCPCK.dpl DATA** (fixed offset, own-module data, no
  reloc concerns). Reserve **109 for a combat-capable spell**: as an id ≥ 100 it is dropped from
  research while its byte is 0, and a nonzero byte implies a tactical class.
- **Ids ≥ 131 are broken without table surgery**: tactical-combat paths raise `ERangeError`
  (bound checks) and the exe research filter reads out of bounds. Growing the table = relocate to
  a bigger buffer + patch the **12 CODE disp32 refs** in AoWTCPCK + the **2 bound pairs** + the
  **export RVA** (the exe import re-binds by name automatically). Scoped Tier-2 sub-project;
  unnecessary until more than 22 new spells exist.

### 7d. Spells.pfs record anatomy (why clones are even easier than §3 assumed)

`TSpellControl.ReadWrite` @0x55779A6C iterates the registry and streams each **non-nil** spell
under **property tag = spell id + 10** (= the .pfs record id; nil slots skipped; spells without a
record keep their in-code defaults). `TSpell.ReadWrite` @0x55779234 gives the record's tag map:

| Tag | Field | Meaning |
|---|---|---|
| 0xA | +0x24 | description TStrings (the spellbook memo text) |
| 0xB | +0x28 | SFX library node (sounds) |
| 0xC | +0x2C | **icon/animation TImageSequenceList** (sequence 10 = book icon) |
| 0xD | +0x14 | mana cost |
| 0xE | +0x1C | casting-point cost |
| 0xF | +0x18 | research cost |
| 0x10 | +0x20 | sphere (1-byte blob) |
| 0x11 | +0x21 | research tier (byte, 0 = not researchable) |

So **costs, sphere, tier, description, sounds AND icons are all data-side**. (Icons are a
spell-only concern: spells have icons, abilities never do — an ability rendering text-only is
normal AoW1 behaviour.) NOT in the record (must be set by the ctor / init cave): name `+0x8`
(resourcestring), id `+0x10`, category `+0x22` (base-class-determined), AI research weight
`+0x30`.

**Workflow implication (expected, untested):** the ReadWrite is symmetric, so saving the set from
the editor **writes a record for every registered spell** — i.e. register the clone in the init
cave, save the development set once, and the new record materializes; thereafter the spell is
tuned data-side like any vanilla spell. Alternative: craft the record bytes directly (pfs.py knows
the directory format).

### 7e. Practical recipe delta vs §3 Tier 1

Init cave (hooked by displacing one `RegisterSpell` call, Path-of-Sand style — e.g. the last
CombatSpells call @0x557FA83F; **verify live bytes first**: Ghidra's image is stale and
`grep -rl 0x557FA8 build_scripts/` must come up empty): instantiate donor class → poke id (+0x10),
name (+0x8 via `System.@LStrAsg`, literal AnsiString), category if diverging, AI value (+0x30),
payload params → `RegisterSpell`. Then: SpellTypes byte (if combat-castable / id 109), .pfs record
(editor save or hand-crafted), done. Everything else (research, books, casting, save, MP, AI)
follows from §1 registry propagation + §7b widths.
