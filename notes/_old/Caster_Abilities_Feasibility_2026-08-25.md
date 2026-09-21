# Evoker / Conjurer / Enchanter / Ritualist — feasibility study

**Status: SUPERSEDED — the feature shipped and is CONFIRMED WORKING 2026-08-27.**
Current state: `Caster_Cost_Abilities.md`. Design record: `Caster_Cost_Abilities_SPEC.md`.
This doc is retained only for the **combat-damage machinery** in §3, which would be the starting
point if a damage-scaling ability is ever revisited — the shipped abilities are all cost-only.
*Dated 2026-08-25. Produced by a 13-agent read-only sweep (6 dimension scouts, each adversarially
verified, then synthesised). Where a scout and its verifier disagreed, the verifier's fact was
taken. Addresses are AoWEPACK.dpl preferred-base VAs unless another binary is named.*

Proposed abilities:

| | effect |
|---|---|
| **Evoker** | ~~doubles spell damage, combat only~~ → **halves the cost of combat spells** (rescoped 2026-08-26) |
| **Conjurer** | halves the mana cost of summoning spells |
| **Enchanter** | halves the mana cost of enchantment spells |
| **Ritualist** | halves the mana cost of global spells / global enchantments |

The user's framing: *"The precise listings of spells covered by each one is relatively unimportant
as I imagine it can be tweaked later."* So the mechanism is what this study had to prove, not the
membership.

> ⚠ **This study turned up a live crash unrelated to the feature** — see §6 Step 0 and the
> separate section at the end. It was byte-verified in the main session, not just by an agent.

---

**Scope:** four new hero abilities. Read-only study. Every claim below carries a VA, a file+offset, a pfs tag or a doc path. Where the six scouts and their verifiers disagreed, the verifier's fact is used; the two places where both were uncertain are labelled **unknown**.

**Binaries referenced:** `AoWEPACK.dpl` (live, patched), `AoWTCPCK.dpl` (live), `AoW.exe` (live), `Modding Resources/AoWEPACK_original_backup.dpl` (pristine vanilla reference).

**Effort units used throughout:**
- **S** ≈ `build_mastery_cost.py` — one hook, one ~60-byte cave, surgical `--undo`.
- **M** ≈ `build_drillmaster.py` — registration cave + `Ability.pfs` record edit + CRC repair + a DevEd round-trip.
- **L** ≈ `build_magebane.py` / `build_turnundead_res.py` — several caves, a shared helper, chained exits, plus a second cave to repair the displayed number.

---

## 1. VERDICT TABLE — superseded

All four are feasible. The verdict table that stood here costed **Evoker as a damage ability**,
which the user cancelled on 2026-08-26. The current table lives in `Caster_Cost_Abilities_SPEC.md`.

One line worth keeping: with Evoker converted to a cost ability, **all four collapse into a single
hook and a single cave**, and the only real risk left is the wallet question (SPEC §6).

## 2. SHARED INFRASTRUCTURE

All four are plain **bit-only `TEnhancementAbility` passives**: no per-owner data record, no icon, no level table. That is the cheapest shape the engine has.

**Ability ids — measured live, three agreeing sources (`Release/Ability.pfs` record keys minus 10 = 151 records keys 10..181; `re_tools/ability_names.py` constructor scan = 150 named, max `0xAB`; `call RegisterAbility` site sweep = 151):**

- 151 ids in use, highest in use `0xAB` (Drillmaster). Live minus vanilla = exactly `{0x38 Assassin, 0x9F Path of Sand, 0xAA Magebane, 0xAB Drillmaster}`.
- **First free id ascending: `0x21`**, then `0x4E`–`0x55`, `0x5B`, `0x66`–`0x69`, `0x6E`, `0x85`–`0x89`, `0x97` (21 gaps below `0xAB`).
- **First free band above everything in use: `0xAC`–`0xCD` (34 contiguous).**
- **Recommendation: `0xAC`, `0xAD`, `0xAE`, `0xAF`.** Freeze before writing the cave — ids are serialised into saves (bitset tag 3, bit index == id) and every MP peer must run byte-identical binaries.
- The "`0xCD` ceiling" recorded in `Zig notes/Ability_ID_Budget.md` §1 and `Inioch/Inioch1/Inioch_Ability_Registration_And_IDs.md` §0 **is a false derivation** — `Engine.TPropertyTable.SaveToStream @0x5550FD0C` (`Enginep.dpl`) writes a wide (u32 tag, u32 offset) entry whenever `tag > 0x7F` or `offset > 0xFF`, and `Release/Unitres.pfs` already round-trips wide keys up to `0x11D`. Nothing above `0xCD` has been run in-game, so treat it as untested rather than proven-safe. `0xAC`–`0xAF` sits under it either way, so this is moot for this feature — but the source docs should be corrected.
- The related Inioch claim that ids above `~0xA9` crash `Localize.dpl` is **refuted by shipped fact**: Drillmaster is `0xAB`, CONFIRMED WORKING 2026-08-08, with level-up availability validated in play, and Magebane sits at `0xAA` in the same binary.

**Registration.** One cave registers all four. Splice a still-vanilla `call TAbilityControl.RegisterAbility (0x55750238)` inside `PassiveAb.RegisterPassiveAbilities @0x557BC1CC` — **86** remain free in the window `0x557BC000`–`0x557BD200`, the last being `0x557BCF04` (registers ability `0x8F`). Four sites are already consumed: `0x557675C4` (Assassin, outside the window), `0x557BC9E9` (Path of Sand), `0x557BCF39` (Drillmaster), `0x557BCF6E` (Magebane). EBX holds the ability control throughout, so the cave body per ability is:

```
mov eax, <id>            ; 0xAC..0xAF
lea edx, [anchor + name_blob + 8]   ; Delphi AnsiString: <i32 -1><u32 len><bytes><NUL>
mov cx, 0x03FF                      ; TAbilitySelectionTypes
call 0x5576601C          ; AoWE.CreateEnhancementAbility -> EAX = ability
mov edx, eax
mov eax, ebx
call 0x55750238          ; TAbilityControl.RegisterAbility
```

Registering a taken id raises `'Ability already registered ('` (string `@0x55750390`) at startup, which Delphi surfaces as a bare `Runtime error 217` before the main window.

**Selection mask.** `CreateEnhancementAbility`'s third argument is a `TAbilitySelectionType` **set**, not an icon (RTTI at file offset `0x826E`, VA `0x55708E6E`): `astUnit 0x001 … astCustomizeLeader 0x080, astHeroUpgrade 0x100, astEditor 0x200`. The hero level-up dialog applies **two** gates and needs both bits:
- `TAbility.CanExpand @0x5574E8B8` ANDs `[ability+0x20]` against `owner->vmt[0x8C]`; `THero.GetAbilitySelectionTypes @0x55786B10` returns the constant word `0x0200`.
- The dialog's fill loop tests `test byte ptr [ability+0x21], 1` (= `0x100`). In the **live** `AoW.exe` that loop is not at `0x004469EC` — `build_herodlg_columns.py` replaced `0x00446972`–`0x00446A53` with `jmp 0x623DE4`; the live gates are `call dword ptr [ecx+0xc4]` `@0x00623E72` and `test byte ptr [eax+0x21],1` `@0x00623E83`.

`CanExpand` also has a **first** test the earlier reports omitted: `owner->vmt[0x4C] GetAbSet(id)` — the **self-only** query. So a hero wearing an item that grants Evoker would still be offered Evoker at level-up.

**Use mask `0x03FF`** (what Drillmaster ships, and what 80 of the 101 level-up abilities carry) unless the abilities are meant to be hero-only, in which case `0x0300`.

**`Release/Ability.pfs`.** `TAbility.ReadWrite @0x5574F07C` serialises exactly five tags into an ability: 5 → `[+0x10]` description, 6 → `[+0x14]` level-up cost, 7 → `[+0x18]` SFX, 8 → `[+0x1C]` images, 9 → `[+0x20]` selection mask. **There is no numeric modifier field on an ability record anywhere** — no data-side route exists for any of the four; each needs a cave. Two consequences:
- **Tag 9 overwrites the cave's mask** once a record exists (0 of 21 vanilla sites agree with their own data file; all 4 mod ids agree only because DevEd wrote them from memory). For a *brand-new* id with no record, the cave's mask stands — `TPropertyTable.FindOffset @0x5550FE70` returns −1 and the reader skips.
- **No constructor sets `[ability+0x14]`.** `TAbility.Create @0x5574E5F4` sets only `+0x10/+0x18/+0x1C`; `TEnhancementAbility.Create @0x55765FDC` sets only `+0x24` and `+0x20`. So an ability with no tag 6 has a hero level-up cost of **zero** — and because `THero.UsedSkillPoints @0x55786CC8` sums `ability->vmt[0x80] GetSkillPoints` (which returns the same `[+0x14]`), it is *permanently* free, not merely displayed as free. Either author tag 6 in DevEd or write `mov dword ptr [obj+0x14], N` in the registration cave.

**Workflow gap:** no build script can mint an `Ability.pfs` record. `build_drillmaster.py` aborts (`"ABORT: Ability.pfs has no record %d for ability"`). Four **AoWDevEd assign-and-save round trips** are on the critical path before descriptions and costs exist. `build_pfs_typos.py` is the length-changing text writer (re-derives offsets, repairs CRC-32 to residue `0x2144DF1C`); `build_drillmaster.py`'s `pfs_tag9_offset`/`pfs_write` is the length-preserving u16 mask writer.

**Names live in code, not data** — there is no name tag. Embed a literal Delphi `AnsiString` in the cave (`<i32 -1><u32 len><bytes><NUL>`, pass blob+8 in EDX; refcount −1 makes `LStrAsg` share and never free). Precedents at `0x5580E02C` (Path of Sand) and `0x5581602C` (Drillmaster).

**Ability-query API — use the item-aware family.** `THero` has two parallel accessors:
- self-only: VMT `+0x4C` GetAbSet, `+0x54` GetAbCount, `+0x84` GetAbLevel, `+0x88` GetAbEnabled;
- item-aware: `+0x144` GetAbilityLevel `@0x5578831C`, **`+0x148` GetAbilityEnabled `@0x5578827C`**, `+0x14C` GetAbilitySet, `+0x158` GetAbilityCount.

`+0x148` on `THero` chains self (`TAbstractUnit.GetAbilityEnabled @0x5577F5E0`) → equipped (`THeroItems @0x55786674`) → itUse bag (`THeroInventory @0x55786154`). Use `+0x148` and an "Evoker's Staff" works for free. `TAbstractUnit` and `TUnit` both hold `0x5577F5E0` in that slot, so it is safe for unit casters too. **Never hand a `TCombatUnit` to `+0x148`** — its VMT ends before `+0x140` and the read lands in the class-name blob; use the forwarder `TCombatUnit.GetAbilityEnabled @0x55725004` at combat VMT `+0xA8`, which nil-guards `[cu+0x4C]` internally.

For a bit-only passive there is no separate enabled flag to initialise: `TAbility.GetEnabled @0x5574EEF4` is literally `owner->GetAbSet(id)`.

**Icons: none.** AoW1 abilities have no icons anywhere in the UI. Zero art cost.

**Level-up category:** free. `build_herodlg_columns.py`'s cave_fill indexes a 256-byte table by `[ability+0x0C]`, and `herodlg_cats.py` fills every unlisted id with `DEFAULT_CAT = 4 = Magic`. Magic currently holds 17 of a 27-row budget; +4 = 21. Note `layout()`'s assert only counts curated ids, so it will not warn about the four — the runtime headroom is what protects against the scrollbar returning.

**Manual:** `re_tools/ability_names.py MODDED` lists only `{0x9F, 0x38, 0xAB}` — Magebane (`0xAA`) is already missing and prints as `?`. The four new ids need entries there, plus tag 5 + tag 6, or `build_ziggurat_manual.py:read_passive_abilities()` skips them (`if not (zc or vc or z.get("cost")): continue`).

**Cave space is not a constraint.** Live `AoWEPACK.dpl` CODE (VA `0x55701000`, raw `0x1E6A00`, virtual end `0x558E7918`): last non-zero byte `0x5582040E`; a single contiguous zero run of 816,393 bytes follows. **Allocate from `0x55820800`** — `build_los_terrain.py` reserves `0x55820000`–`0x55820800` exclusively. Avoid `0x55817000`–`0x55817400` (vision9, explicit "DO NOT ALLOCATE INSIDE IT") and `0x55817400`–`0x55820000` (marksmanship8 reserve). Do **not** use the 67-byte pocket after the mastery cave.

### Why the three cost abilities are far cheaper together

They share one hook, one cave, one classification pass and — critically — **one** `GetAbilityEnabled` call. Classify the spell first, then query only the one ability that family maps to:

```
classify(spell) -> {summon | unit-enchantment | global-enchantment | none}
                 -> abilityId = {0xAD | 0xAE | 0xAF | -}
one call to caster->vmt[0x148](abilityId)
```

That matters because `TAbstractUnit.GetAbilityEnabled` is **not** a cheap bit test: it calls `vmt+0x14C`, reads the global AoWHSSet at `[0x558FA044]+0x80`, calls `TAbilityControl.GetAbility`, then dispatches the ability object's `vmt+0x74` — two nested virtual calls plus a registry search, inside a function the AI hammers in affordability loops. Three queries per cost evaluation would be three times that. Built separately, each ability also needs its own hook on an already-crowded function; built together, it is one 7-byte displacement.

---

## 3–6. SUPERSEDED — the design changed on 2026-08-26

**The user narrowed the scope: all four abilities now halve only the INITIAL CASTING COST.**
Evoker is a cost ability (combat spells), not a damage ability. There are no upkeep patches.

**The build spec is `Caster_Cost_Abilities_SPEC.md`** — membership table, classification tests,
both caves, the wallet fix, the cave map and the acceptance criteria. Use that, not this doc.

What was deleted here and why: §3a (shared cost hook) is fully restated and corrected in the SPEC;
§3c/§3d (Ritualist and Enchanter upkeep) are out of scope; §3e and §4 (Evoker as a damage ability)
are cancelled. Two of this doc's §3a claims were **wrong** and are corrected in the SPEC —
do not re-derive them from here:

- the `[spell+0x3c] == 0` exclusion of Dispel Magic / Remedy / Healing Water was a damage/duration
  filter, irrelevant to cost, and `+0x3c == 0` is the common case file-wide (`TCombatSpell.Create`
  writes 0 at `0x557F723A`). All 18 `TUnitSpell` classes are in the Enchanter bucket;
- a floor applied in the prologue **does not survive the function** — the mastery cave rescales EBX
  afterwards and `(1×3)>>2 = 0`. The floor belongs at the exit, `0x55789510`.

### Machinery retained — only useful if a damage ability is ever revisited

The Evoker-as-damage investigation is cancelled, but its map is valid and cost real time to build:

- Spell damage in combat is produced at `CombatSpells.TCombatSpell.CreateCA @0x557F72C0`
  (damage read + arg push at `0x557F72E4`–`0x557F72F4` → `TDamageCA.GenerateEx @0x55729C98`).
- **Three subclasses override `CreateCA` and still deal damage**, each with its own arithmetic and
  a different CA VMT slot: `TGeyser @0x557F9148`, `TWindsOfFury @0x557F9EB8`,
  `TTurnUndead @0x557F7C50`. Seven further overrides deal no damage.
- **The caster IS reachable**: `CreateCA` holds the caster's `TCombatUnit` at `[ebp-4]`. Use the
  combat-VMT forwarder `+0xA8 → TCombatUnit.GetAbilityEnabled @0x55725004`, which does the
  `[cu+0x4C]` bridge and the nil guard for you and lands on the item-aware query.
- **Combat-only needs no runtime test** — no strategic path reaches `CreateCA` (byte scan for
  `call [reg+0x78]` across all four modules + import-table check; all 21 xrefs are VMT data slots).
- ⚠ **The tactical fan-in is 14 sites, not 3.** Eleven are lingering map-effect handlers in
  `TTacticalCombatUnitHS.MapFieldMsgProc @0x00420E5C` and `TCCorpseHS.MapFieldMsgProc`
  (burning/icy/quaked hexes, corpses). A `CreateCA` hook doubles those too.
- ⚠ **Do not hook `TDamageCA.GenerateEx @0x55729C98`** — the caster is not among its parameters, and
  it already carries epilogue hooks from `build_combatlog_dll.py` / `build_touchlog_gate.py`.
- The displayed number would need its own patch: `TCombatSpell.GetCombatInfo @0x557F7258` copies
  `[spell+0x34]`/`[spell+0x38]` raw, and receives the **strategic** unit in EDX, so the test there
  is `vmt+0x148` directly, not the `+0xA8` forwarder.
- Spell objects are shared singletons — double in flight, never write `[spell+0x35]`.

Upkeep machinery, if that is ever revisited: global-enchantment upkeep is written once and
persisted at `TGlobalEnchantmentSpell.SetupEnchantment @0x557EF914` (7 bytes, no relocs, hero in
EDX, inherited by all 12 classes). Unit-enchantment upkeep is `[ench+0x10]`, summed **per player**
by `TPlayerMagicControl.GetManaUpkeep @0x5577C964` — there is no caster dimension, so a
caster-scoped discount has nowhere to live.

## 7. TRAPS

- **`0x557894F8` is owned by `build_mastery_cost.py`** — hook the entry at `0x557894EC` instead; never re-hook, and never write "revert and re-apply" (there is no `.pre-masterycost`; only `--undo`).
- **`build_mastery_cost.py --apply` mints a fake `.pre-masterycost`** — because the file no longer exists, the next apply snapshots the fully-patched 2026-08-24 DLL under a pristine-sounding name. Same trap as `.pre-herodlgcolumns`.
- **`.reloc` at `0x557894F4`** is `CastingMana`'s only relocation — displacing it is the classic "works one launch, crashes the next".
- **EAX (the caster) dies at `0x557894F3`** and is never spilled; the only pushes in the function are `53 56`.
- **The `CastingMana` entry cave cannot wrap the call** — the mastery cave already owns the tail via `jmp 0x55789510`. Prologue insert only.
- **`GetAbilityEnabled` clobbers EAX/ECX/EDX** and is two nested virtual calls plus a registry search — save the spell across it, and classify first so you make one query, not three.
- **`[TCombatUnit+0x4C]` aliases** — on `TCombatWall` it is packed bytes (nonzero garbage that sails through a nil test: the Blt Error bug), on `TCombatPredictorUnit` it is signed HP. Class-test, do not nil-test. Use the `vmt+0xA8` forwarder `@0x55725004`, which does both.
- **`TCombatUnit`'s VMT ends before `+0x140`** — a `vmt[0x148]` call on one lands in the class-name/RTTI blob.
- **VMT `+0x148` aliases too** — on `TStructure`/`TArena`/`TExplorationSite` it is `GetName`, returning a pointer that reads as a non-zero boolean.
- **Spell objects are shared singletons** — `TSpellControl.RegisterSpell @0x55779B40` indexes a TList by `[spell+0x10]`. Never mutate `[spell+0x35]`; double in flight.
- **`[spell+0x22] == 2` is not "global enchantment"** — it is `stGlobal`, carried by 60 of 108 spells. `TGlobalEnchantmentSpell.Create @0x557EF8D8` does not even set it.
- **`[spell+0x22]` on the `*TE` companion classes is a hex coordinate** (`TGlobalTargetSpellTE.SetLocation @0x5579E2A8`, `TCityTargetSpellTE.SetLocation @0x557B02F0` both write it; ~60 read sites use `movsx`). The test is only valid on a real `TSpell`.
- **A zero cost is not harmless** — `THero.CastingDone` then consumes neither mana nor casting points. Floor of 1, always.
- **A new ability with no `Ability.pfs` tag 6 is permanently free**, not just displayed as free (`UsedSkillPoints` sums `ExpandCost`).
- **`Ability.pfs` tag 9 overwrites the cave's mask** once a record exists — verify after every DevEd save.
- **Saves silently strip unregistered ability bits** — `TCustomAbilityList.ReadWrite @0x5574E2BC` calls `SetAbSet(id, false)` for any set bit whose `GetAbility(id)` is nil. So an old build loading a new save degrades gracefully rather than crashing — but the ability is gone and re-saving makes it stick. Freeze the four ids before anything ships.
- **`TAbstractUnit.GetAbilityEnabled @0x5577F5E0` dereferences `GetAbility(id)` with no null check** (`0x5577F603`). Any cave that sets an ability bit for an id it did not register turns that into a null-deref.
- **MP has no content hash** — `AoWSetup.TSetupControl.ValidateCompatibleVersion @0x557DFCAC` compares only the high word of the version. Mismatched peers connect and then desync.
- **Per-object `NewTurn` runs once per PLAYER** — `TArmy.NewTurn @0x5578F79C` opens with `cmp dl,[ebx+0x12]`. Any "+N per turn" cave must repeat that guard (Drillmaster v2 granted +3 XP in a 3-player game).
- **Keystone:** `push 0xFFFF` assembles as `6A FF` = −1, silently; `call $+5` as a PIC anchor emits nothing and the anchor search then zeroes the rel32 of whatever `E8` precedes it; inline `;` comments are rejected. Disassemble every cave you assemble.
- **DLL caves must be position-independent.** The best classification idiom here needs no anchor at all: `[VMT+0x6C] − [VMT+0x18]` is rebase-invariant because `TSpell.ReadWrite` is un-overridden across all 117 subtree classes.
- **Cave allocation:** start at `0x55820800`. `0x55817000`–`0x55817400` is reserved by `build_vision9.py`; `0x55817400`–`0x55820000` by marksmanship8; `0x55820000`–`0x55820800` by `build_los_terrain.py`. Round addresses like `0x55814000`, `0x55815000` and `0x55820000` are **not** free.
- **Mutable state goes in BSS**, from `0x558FA800` upward — CODE caves are read+execute only, and BSS raw size is 0, so a file-byte assertion there chases a phantom. None of the four needs mutable state.
- **Ghidra's image is pristine vanilla** and its `[LIVE-PATCH]` annotations can be stale (one still records Burning at 4→10 when the live immediate at `0x557BA463` is 20). Byte-check the live file for every "is this patched" claim.
- **The Ghidra MCP tool wrappers do not register in a subagent's tool index** even when `connect_instance` reports 221 tools. The bridge itself is healthy — query it directly: `curl -s http://127.0.0.1:8089/decompile_function?address=0x...`, `/get_function_xrefs`, `/get_xrefs_to`, `/read_memory`. Four of the six scouts degraded to hand-disassembly unnecessarily.

**Two live-state facts worth recording regardless of whether this feature proceeds:**
- `SummonSpells.TSummonSpell.SetupSummonSpellTE @0x557E4484` is entirely replaced in the live DLL by `jmp 0x5580C500`, and **no** script under `build_scripts/` references either address. The cave makes summon unit id `0xE4` spawn `RandInt(5)+3` copies. That is directly material to Conjurer — one summon spell already produces 3–7 units for one mana payment.
- Two more unowned, undocumented caves sit on the spellcasting economy: the Spellcasting mana-income ladder at `0x557885EC` (reached from `TLeader.GetPowerGeneration @0x5578B461`) and the casting-points ladder at `0x5580BF00` (from `THero.GetCastingPointsMax @0x55788639`), both 10/20/40/60/90, both with no script, no backup and no `--undo`. `Unit_Spellcasting_Feasibility_2026-07-05.md:99` describes those values as if they were vanilla — they are not (vanilla is level×5+5 and level×10 respectively), and that line should be corrected at source.
---

## 9. Three unowned, undocumented caves on the spellcasting economy

Found by the same audit; no script under `build_scripts/` references any of them, none has a
backup or an `--undo`, and their effects are currently invisible to the docs:

| site | live behaviour |
|---|---|
| `SummonSpells.TSummonSpell.SetupSummonSpellTE @0x557E4484` | entirely replaced by `jmp 0x5580C500`; the cave makes summon unit id `0xE4` spawn `RandInt(5)+3` copies |
| `0x557885EC` (from `TLeader.GetPowerGeneration @0x5578B461`) | Spellcasting mana-income ladder, 10/20/40/60/90 (vanilla: level×5+5) |
| `0x5580BF00` (from `THero.GetCastingPointsMax @0x55788639`) | casting-points ladder, 10/20/40/60/90 (vanilla: level×10) |

`Unit_Spellcasting_Feasibility_2026-07-05.md:99` describes those ladder values as if they were
vanilla. They are not — that line should be corrected at source.

The summon multiplier is directly material to **Conjurer**: one summon spell already yields 3–7
units for a single mana payment, so halving its cost compounds with an existing multiplier.
