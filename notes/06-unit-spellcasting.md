# Unit Spellcasting

Makes the *Spellcasting* ability (id `0x34`) functional on ordinary (non-hero) units — mana-throttled
casting in auto-resolve, tactical combat and on the strategic map, plus a casting-points display on
the unit card — by patching `AoWEPACK.dpl`, `AoWTCPCK.dpl`, `AoWz.exe` and `AoWzCompat.exe`. No new
DLL. It also covers the two features layered directly on top of that mechanism: the "Spellcasting
level ≥ spell tier" cast gate (and its 2026-09-03 reversal to units-only) and hero mana income scaling
with Resistance.

**Not covered here** (each has its own file that owns it — this file does not restate them):
Vision, Leadership, Fire-heals-fire, Turn Undead and the unit-enchantment re-grade → existing-ability
changes, see `02-abilities-modded.md`; the Caster-cost abilities (Evoker/Conjurer/Enchanter/
Ritualist) and the Shield ability → new abilities, see `03-abilities-added.md`; the spell Tier
Research system → `04-spells-modded.md`; the hero level-up dialog rework (tall + category columns)
→ `07-ui.md`; the project-wide 5 %-slope and DAM/HP-doubling passes, and the melee facing re-timing
→ `01-combat-maths.md`; elemental terrain healing → `09-terrain-movement.md`. The old unit-spellcasting master index had accreted full write-ups of all of these as a de facto project
changelog — none of it is unit spellcasting, and it is dropped here without restatement.

Two things not fully owned by this file but touched because they share a cave or a coupling with it:
**Scrolls as a permanent per-hero spellbook grant** (`build_scroll_spellbook.py`) rewrote the exe
book-filter cave that M3/M4 live in, and its 2026-09-03 edit to that cave *is* the units-only ruling's
book half — the coupling is documented in full below, the scroll feature's own design is not.
**Item-granted Spell Casting** (`build_unitwin_ability.py`, exe-side, CONFIRMED 2026-08-28) is the
reason the M2 tier gate had to become item-aware; it is cross-referenced, not documented.

---

## Status table

| feature | status | owning script | binary |
|---|---|---|---|
| Phase 1a — auto/fast-combat casting | ✅ CONFIRMED WORKING (2026-07-06) | `build_spellcast.py` | AoWEPACK.dpl |
| Phase 1b — manual/tactical combat casting | ✅ CONFIRMED WORKING (2026-07-06) | `build_spellcast_tcpck.py` | AoWTCPCK.dpl |
| Phase 2 — strategic instant casting + ability button | ✅ CONFIRMED WORKING (2026-07-06) | `build_spellcast.py` | AoWEPACK.dpl |
| Casting points on the unit card | ✅ CONFIRMED WORKING (2026-07-06) | `build_spellcast_card_v2.py` | AoWz.exe + AoWzCompat.exe |
| M1 — multi-turn channel accrual (progress no longer freezes) | ✅ CONFIRMED WORKING (2026-07-06) | `build_spellcast_multiturn.py` | AoWEPACK.dpl |
| M2 — "Spellcasting level ≥ spell tier" cast gate, all casters | ✅ CONFIRMED WORKING (2026-07-06); item-aware v2 fix ✅ CONFIRMED WORKING (2026-08-28) | `build_spellcast_multiturn.py` | AoWEPACK.dpl |
| M2 — hero/leader **exemption** from the tier gate (units only) | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_spellcast_herotier.py` | AoWEPACK.dpl |
| M3 — hide too-high-tier spells from the casting book | ✅ CONFIRMED WORKING (2026-07-06) as "prune everyone"; units-only behaviour 🔨 APPLIED, UNTESTED (2026-09-03) | `build_scroll_spellbook.py` (rewrote `build_spellcast_book_exe.py`'s cave in place) | AoWz.exe + AoWzCompat.exe |
| M4 — hide Cosmos spells from *unit* books (heroes/leader keep them) | ✅ CONFIRMED WORKING (2026-07-06), unaffected by the 2026-09-03 reorder | `build_scroll_spellbook.py` (rewrote `build_spellcast_book_exe.py`'s cave in place) | AoWz.exe + AoWzCompat.exe |
| C2 — save/load persistence of casting state | ✅ CONFIRMED WORKING (2026-07-06) | `build_spellcast_persist.py` | AoWEPACK.dpl |
| Hero mana generation = Resistance × Spellcasting level | ✅ CONFIRMED WORKING (2026-08-27) | `build_spellcast_manares.py` | AoWEPACK.dpl |
| Mana generation *for unit casters* | SPECULATIVE — deliberately LOCKED, never to be built | *(cancelled Phase 3; every relevant script re-asserts the stub)* | AoWEPACK.dpl |
| Scrolls — permanent per-hero spellbook grant *(adjacent feature — shares `cave_bookfilter` with M3/M4; not itself unit spellcasting)* | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_scroll_spellbook.py` | AoWz.exe + AoWzCompat.exe + AoWEPACK.dpl |
| Fast-combat freeze hypothesis (unit casters vs. walled cities) | Investigated and **ruled out** — real cause found elsewhere | `build_fastcast_gate.py` (diagnostic toggle, kept) | AoWEPACK.dpl |
| Per-unit intrinsic spellbook / HP-MV casting cost / enchant cost-by-level | SPECULATIVE — investigated, nothing built | *(none)* | AoWEPACK.dpl / AoWz.exe |

Confirmation dates for Phase 1a/1b/2/card: no source doc states these in isolation with their own
"user confirmed on date X" line. The date above is carried forward from the master index's own
"Status — what works now (all applied & confirmed)" heading and from the Polish investigation, whose
2026-07-06 work was explicitly gated on this test plan already having passed ("Report which steps
work; that gates applying the staged C1-progress / C2-persistence caves" — Implementation doc).

---

## How it works (vanilla architecture — read this before touching any gate)

### Module topology

| Module | Role | Casting-relevant content |
|---|---|---|
| `AoWEPACK.dpl` | all game logic | `THero`/`TUnit`/`TSpell`/`TSpellCastingAbility`/`TPlayerMagicControl`, TEs, AI |
| `AoW.exe` | host + all strategic/shared UI | imports THero class-ref (7 code refs) + `CastSpell`/`CastCombatSpell`/`CancelCasting`/`Casting*`/`CanCastSpellInstantly` thunks + `Casting*RStr` strings |
| `AoWTCPCK.dpl` | tactical combat engine/screen | imports THero class-ref (22 refs), `CanCastSpellInstantly`, `TSpell.CombatSpellCast`, `TSpellControl.GetSpell` |
| aowInt.dpl / HSEPack.dpl / Enginep.dpl / AbilityP.dpl | UI widgets / map engine / core engine | **zero** casting-related imports — not involved |

Delphi packages import/export by name and `is`/`as` checks go through import slots, which is what
makes this kind of cross-module patch enumerable at all.

### Class hierarchy and the casting cluster

```
TCustomAbilityList (0x10) ← TAbilityOwner (0x14) ← TAbstractUnit (0x3C)
                                                      ├─ TUnit           0x48  ← ordinary map units
                                                      ├─ TAdjustableUnit 0x48  ← editor-customised units
                                                      ├─ TWallUnit       0x40  ← combat walls (excluded, see below)
                                                      └─ THero           0x9C
                                                           └─ TLeader    0xA4  (the player's wizard)
```

VMT header layout (Delphi 3, empirical): `[VMT−0x20]` = class-name ptr, `[VMT−0x1C]` = **instance
size**, `[VMT−0x18]` = parent class-ref ptr, `[VMT−0x2C]` = published field table.

| Class | class-ref slot | VMT | instance-size word |
|---|---|---|---|
| TAbstractUnit | `0x55710700` | `0x55710740` | `0x55710724` (= 0x3C) |
| TUnit | — | `0x55710CAC` | `0x55710C90` (0x48 → **0x94**) |
| TAdjustableUnit | — | `0x55712A54` | `0x55712A38` (0x48 → **0x94**) |
| THero | `0x55711FAC` | `0x55711FEC` | `0x55711FD0` (= 0x9C) |
| TLeader | (`0x557121F8` = parent-ref) | `0x55712238` | `0x5571221C` (= 0xA4) |
| TCombatUnit | `0x55715A54` | — | combat wrapper; `+0x4C` → strategic unit ptr |

The whole casting state lives in **five THero fields**, and nowhere else:

| Offset | Type | Meaning | THero.ReadWrite tag |
|---|---|---|---|
| `+0x7C` | ptr | `THeroPowerSource` (mana-gen registration object) | not serialized (rebuilt) |
| `+0x80` | byte | current casting points ("channelling points" in combat) | `0x0D` |
| `+0x84` | int32 | spell id being cast strategically (0 = none) | `0x0E` |
| `+0x88` | int32 | accumulated casting progress | `0x1F` |
| `+0x8C` | int32 | total mana required for the in-progress spell | `0x22` |
| `+0x90` | int32 | casting-ready event-log id (default −1) | `0x23` |

`TUnit`'s own fields sit at `+0x3C/+0x3D/+0x3E` (byte; experience/medal data) and `+0x40`
(`TUnitResource*`), serialized as tags 7/8/9/0xA. Tags ≥ `0x0B` were free in `TUnit`'s stream —
exactly why the casting tags (`0x0D..0x23`) could be appended for C2 with zero collision risk against
`TUnit`'s own tags, the base chain (`TAbstractUnit` 4/5/6/0x2F, `TAbilityOwner` 0x31/0x32+), or each
other (they already coexist inside `THero`).

### Relevant vtable slots (TAbstractUnit VMT, offsets from VMT base)

| Slot | Method | TAbstractUnit impl (vanilla stub) | THero override |
|---|---|---|---|
| `+0x128` | GetCastingPointsMax | returns 0 (`0x5577FDB8`) | ability-driven (`0x55788614`) |
| `+0x12C` | GetCastingPoints | returns 0 (`0x5577FDBC`) | reads `+0x80` (`0x55788644`) |
| `+0x130` | SetCastingPoints | no-op (`0x5577FDC0`) | writes `+0x80` (`0x5578864C`) |
| `+0x134` | GetPowerGeneration | returns 0 (`0x5577FDB4`) | → `TLeader` impl (`0x5578B43C`) |
| `+0x138` | NewDay | `0x5578120C` | — |
| `+0x13C` | NewTurn | `0x55780D4C` | casting refill/progress (`0x55787FCC`) |
| `+0x144` | GetAbilityLevel | `0x5577F658` (self-only base) | `0x5578831C` (item-aware: self → equipped → inventory) |
| `+0x148` | GetAbilityEnabled | `0x5577F5E0` | item-aware, same pattern |

**Critical fact that makes this whole mod tractable:** `THero.GetCastingPointsMax` and
`TLeader.GetPowerGeneration` touch **no hero-only field at all** — they call
`GetAbilityEnabled(0x34)` / `GetAbilityLevel(0x34)` through the VMT and map the level through a
table. They are class-agnostic and install directly into `TUnit`'s VMT unmodified.

Spellcasting = ability id **`0x34`**; singleton `TSpellCastingAbility` in the global ability control
(`AoWHSSet+0x80`). **Level → points table (both level and casting-points tables): I=10, II=20,
III=40, IV=60, V=90.** Ability level range is 1–5, confirmed by `TSpellCastingAbility.GetLevelName`
@`0x5576DC74` (switch on cases 0–5, level 0 = ability absent).

### The five vanilla usage paths, and which gate unlocks each for units

| Path | Vanilla chokepoint | Unlocked by |
|---|---|---|
| **(A) Mana generation** | `THeroPowerSource.Power` (`0x557867D0`) → owner vtable `+0x134` | **Never unlocked — deliberately.** See Scope below. |
| **(B) Strategic ability activation ("open spellbook")** | `TSpellCastingAbility.CanActivate` (`0x5576DEAC`): `return unit is THero` | Gate **G1** → `cave_iscaster` |
| **(C) Strategic casting** (instant + multi-turn) | `THero.CastSpell` (`0x55789854`) → `CanCastSpell`/`ExecuteStartCasting`/`TSpellCastEventLog.Execute` | Gates **G1, G4, G6**; multi-turn needs **M1** (accrual) |
| **(D) Manual/tactical combat casting** | `THero.CastCombatSpell` (`0x55789BC8`) → `CanCastCombatSpell` → `TSpell.ActivateCombat`/`CombatCastingDone` | Gate **G5** (DLL) + 4 TCPCK gates (Phase 1b) |
| **(E) Fast (auto-resolve) combat** | `TSpellCastingAbility.fcPrefetchCombatCommands` (`0x5576E2BC`) reads `unit+0x84`, checks `combatUnit+0x4C is THero` | Gates **G2, G3, G7** |

Everything else on the cast path is already generic and needed **no patch at all**:
`THeroUpdateTE.Execute` (MP casting command — `FindUnit` + dispatch, no class check),
`TSpellTE.Validate/Execute/GetSource` (unit-ID based), `TAbility.Activate`'s event plumbing
(`TActivateAbilityInfo` carries a unit id, handles any `TAbstractUnit`), `TSpell.CanActivate/
Activate/ActivateCombat/CanActivateCombat`, `TSpellCastingAbility.AICanCastCombatSpell`,
`THero.CastingMana` (touches only spell data), `TSpellCastingAbility.Expand/Remove` (already notify
`TPlayerMagicControl.Update` for *any* `TAbstractUnit` — the engine had half-plumbed generic support
and never finished the non-hero side). **Multiplayer determinism** needs no extra care: all casting
is TE/token-based on unit ids, and refill runs inside deterministic turn processing — identical
guarantees to heroes (both peers must run the patched binaries, as with every feature in this line).

**Spell list:** `THero.ListSpells` (`0x557879F0`) forwards to `TPlayerMagicControl.ListSpells` —
heroes (and, once unlocked, units) cast from the **player's researched spellbook**. Units need no
spell storage of their own; casting spends the *player's* mana, throttled by the unit's own casting
points. This is the single fact that makes the whole feature small.

### Why it was dead for units — exactly two mechanisms

1. **`is THero` class checks** at every entry point in the table above — the ability button reads
   disabled, completion accounting is skipped, AI prefetch skips units.
2. **Missing state/overrides on `TUnit`** — the instance is too small for the `+0x7C..+0x93`
   cluster, and `TUnit` inherits the `return 0` stubs for `GetCastingPoints[Max]`/
   `GetPowerGeneration` and the plain `TAbstractUnit.NewTurn` (no refill). Max points = 0 fails every
   check even where the class gate passes.

### The storage problem and why no companion DLL was needed

A prior investigation had concluded a new DLL was required, to hold per-unit casting state
externally. That conclusion was wrong. Delphi allocates every object via a **data word in the file**
(`[VMT−0x1C]`, the instance size), used by `NewInstance`/`GetMem`, with the whole instance
**zero-filled** on construction. `TUnit` is a **leaf class** — no descendants exist (verified by a
full-file VMT parent scan) — so its field layout is safe to extend unilaterally.

**The fix: grow `TUnit`'s instance size 0x48 → 0x94** (and `TAdjustableUnit` identically), placing
the casting cluster at **the same offsets THero uses**. Consequences, all verified per-function:

- Every THero casting method that touches only the cluster + virtuals (`CanCastSpell`,
  `CanCastSpellInstantly`, `CanCastCombatSpell`, `CastSpell`, `CastCombatSpell`, `CastingMana`,
  `Casting`, `CastingReady`, `CastingTurns/Left`, `ExecuteStartCasting`, `ExecuteCancelCasting`,
  `CastingDone`, `RemoveCastingReadyEventLog`, `CreateHeroUpdateTE`) is directly reusable on a grown
  `TUnit` — none of them touch hero-only fields (`+0x3C..+0x7B`: items/inventory/skills).
- No save-format impact from the size itself — saves serialize tagged fields, not raw instance memory.
- Memory cost: +76 bytes/unit, negligible. No relocation issue — the instance-size word is a plain
  constant, no `.reloc` entry.
- **Bonus:** vanilla's fast-combat prefetch already read `unit+0x84` on *every* combat unit
  (an out-of-bounds read past `TUnit`'s original 0x48-byte instance on non-hero units) — instance
  growth incidentally makes that pre-existing vanilla OOB read well-defined instead of garbage.

**Rejected alternative — vmtParent swap** (make `TUnit` "inherit" `THero` for RTTI purposes): would
make *every* `is THero` check in the entire game true for units — items, levelling, joins, death
handling — unbounded behavioural fallout. Not attempted.

**`TWallUnit` is deliberately excluded** — never grown. The G-gates test the Spellcasting ability, and
walls have none, so they fail cleanly; the pre-existing vanilla OOB read on `unit+0x84` for walls in
fast combat is left exactly as it was (harmless, unchanged). This is also why the one "triage-only"
gate from the original plan — wall-siege caster (de)registration in `TFastCombatUnit.Initialize`/
`KillUnit`, `0x5574413D`/`0x55743A81` — was never built: there is nothing for it to do.

---

## Phase 1 — enabling combat casting

### Phase 1a — auto/fast combat (AoWEPACK.dpl)

`build_spellcast.py` — 18 patches, ✅ CONFIRMED WORKING (2026-07-06). No `--undo` exists (see
**Open items** — no revert path for this layer).

- **D1/D2** grow `TUnit` (VMT `0x55710CAC`, size word `0x55710C90`) and `TAdjustableUnit`
  (`0x55712A54` / `0x55712A38`) instance size 0x48 → **0x94**.
- **D3/D4/D5** redirect VMT slots **+0x128/+0x12C/+0x130** (both classes) from the `TAbstractUnit`
  `return 0` stubs to THero's class-agnostic impls (`0x55788614`/`0x55788644`/`0x5578864C`).
- **C1 (refill)** installs `cave_unit_newturn` at VMT **+0x13C**: calls `TAbstractUnit.NewTurn` then,
  on the owner's turn, `points(+0x80) := GetCastingPointsMax()` — THero's own refill line, nothing
  hero-only. (Superseded in place by M1's cave on 2026-07-06 — see below.)
- **Gates → `cave_iscaster`** (`mov ecx,[eax]; mov edx,0x34; jmp [ecx+0x148]` — returns
  `GetAbilityEnabled(0x34)`; walls & non-casters fail cleanly, no OOB): **G2**
  `fcPrefetchCombatCommands` `0x5576E418`, **G3** `CanCastBreachWallSpell` `0x5576DF17`, **G5**
  `CombatCastingDone` `0x5577950C`, **G7** `CombatSpell.fcPrefetch` `0x557F76EB`, **G4** strategic
  `CastingDone` `0x557794CD` (inert until Phase 2, patched now to avoid re-touching the site later).
- Cave region **`0x5580D900`** (after the pre-existing move-fix cave): `cave_iscaster` (13 B,
  `0x5580D900`) + Phase-1's `cave_unit_newturn` (46 B, `0x5580D90D`, ends ≈`0x5580D93A`).

Result: a unit with Spellcasting casts the player's researched combat spells in auto-resolve and fast
combat, with per-turn point refill and correct point/mana accounting.

### Phase 1b — manual/tactical combat (AoWTCPCK.dpl)

`build_spellcast_tcpck.py` — 5 patches, ✅ CONFIRMED WORKING (2026-07-06). No `--undo`. Requires
Phase 1a applied first.

Retargets the 4 tactical "can this unit cast" gates (each already scoped to Spellcasting: `cmp
ability,0x34; jne skip; mov eax,[combatUnit+0x4C]; call @IsClass(THero)`) — sites **`0x418739`,
`0x418B86`, `0x418F71`, `0x4195D4`** — from `@IsClass` (`0x401058`) to a TCPCK-local `cave_iscaster`
at **`0x438100`** (same 3-instruction `GetAbilityEnabled` thunk; the gated object is
`combatUnit+0x4C`, a `TAbstractUnit` descendant, so `vtable+0x148` is valid there). No behaviour
change for heroes.

**Phase 0 finding (still true, worth keeping):** `AoW.exe`'s strategic casting UI is
**caster-generic already** — all casting calls (`CastSpell` ×3, `CastCombatSpell`,
`CanCastSpellInstantly`, `ListSpells` ×5) operate on a UI-held object pointer with **no `is THero`
gate**; the exe's 7 `is THero` sites are hero-panel/combat-map-highlight/wizard-tower/face display,
not casting gates. So strategic casting needed **no exe patch** — enabling the ability button
(AoWEPACK G1) was sufficient, which is the single most feasibility-friendly fact this project found
in its own engine. `AoWTCPCK.dpl`'s 22 `is THero` refs, by contrast, gate the tactical "can cast"
check directly — those are the 4 sites above.

### The fast-combat freeze red herring — `build_fastcast_gate.py`

While chasing a real, reproducible freeze — an AI-initiated **automatic** battle against the player's
**walled city** hung the game (sound still running, no input, reproducible on reload) — the working
hypothesis was that unit spellcasting's fast-combat gates were implicated: both sides fielding a unit
caster, three of the seven Phase-1 gates (**G2** `fcPrefetchCombatCommands`, **G3**
`CanCastBreachWallSpell`, **G7** `CombatSpell.fcPrefetch`) sit exactly inside the freezing code path,
and a wall assault is the one case that exercises `CanCastBreachWallSpell`.

`build_fastcast_gate.py` is a **diagnostic toggle**, not a fix: `--disable` points only those three
call sites back at the stock `System.@IsClass` thunk (heroes-only, vanilla behaviour) for A/B
testing; `--restore` puts them back on `cave_iscaster`. Three 5-byte call-target rewrites, no cave
touched, fully reversible either way, idempotent.

**The hypothesis was ruled out.** The actual root cause (found and ✅ CONFIRMED FIXED 2026-07-22, in
`10-ai-and-structures.md` §8) was unrelated to spellcasting entirely: `build_combatlog_dll.py`'s
combat-log worker read `combatObj+0x4C` (the strategic-unit back-pointer, valid only on
`TCombatUnit`) with a **nil check but no type check**; on a `TCombatWall`, `+0x4C` aliases packed
setup/hitpoint bytes, so a small nonzero integer there passed the nil check and the worker jumped
through it as a vtable pointer, access-violating inside the combat pump. Reached whenever anything
damages a wall — i.e. any wall-crushing attacker vs. a walled city, with or without a caster on
either side. Fixed by gating all four `+0x4C` name-lookup sites on `IsClass(obj, TCombatUnit)`.

The diagnostic script is kept — the hypothesis it tests remains a reasonable first move if this exact
symptom class (AI + walled city + freeze) ever recurs with the real cause not yet re-identified — but
treat a return to it as reopening a closed lead, not as the first place to look.

---

## Phase 2 — strategic casting and the unit card

### Strategic instant casting (AoWEPACK.dpl)

`build_spellcast.py`, continued — ✅ CONFIRMED WORKING (2026-07-06):

- **G1** `SpellCastingAbility.CanActivate` (`0x5576DEB7`) → `cave_iscaster`: enables the strategic
  Spellcasting ability button for units. Because the exe casting UI is already generic (Phase 0
  finding above), the spellbook then opens and casts on the unit via the existing `THero.CastSpell`
  path unmodified.
- **G6** `SpellCastEventLog.Execute` (`0x5577A25C`) → `cave_iscaster`: the recast-ready handler
  accepts units (inert until M1 landed multi-turn progress).

Result: a unit can cast **instant** strategic spells — any spell whose cost ≤ the unit's current
casting points. Multi-turn (unaffordable) casts needed M1 (below) to actually progress; before M1
landed, starting one left the unit "casting" with no progress (cancellable, not a crash).

### Casting points on the unit card (AoWz.exe + AoWzCompat.exe)

`build_spellcast_card_v2.py` — ✅ CONFIRMED WORKING (2026-07-06). No `--undo`. Depends on Phase 1a's
**D3** patch (VMT `+0x128` redirected to `THero.GetCastingPointsMax`) — the display reads casting
points through that slot.

**The realisation that made this a small patch:** the unit card is drawn by one paint function,
`0x407DB8` (`TUnitWindow` method), which **already contains a complete casting-points display**: at
`0x4087C0` it reads `GetCastingPointsMax(unit)` and, if > 0, writes `"current/max"` to the card's
**Mana label** — control field `+0x70`, the exact cell a hero uses. The display was simply switched
off for units by two things: it is driven by `edi`, set to the unit for heroes and `nil` for units by
an `is THero` gate at `0x407E43`; and the Mana label + icon are hidden by default for non-wizard
units (the game explicitly calls `SetVisible(true)` before writing them for heroes).

**The safe hook:** the upkeep caption-set, `SetGText(eax=UpKeep label, edx=upkeep string)` at
**`0x40916A`** (upkeep > 0) and **`0x4091A6`** (upkeep ≤ 0) — both sites have `EBX = the unit`
(a valid `TAbstractUnit`) and `ESI = &form`. Retargeting both `SetGText` calls to a cave that (1)
performs the original upkeep `SetGText`, then (2) if `ebx.GetAbilityEnabled(0x34)`: shows the Mana
label (`control.vtable+0x6C` = `SetVisible(dl)`), builds `"cur/max"` from `GetCastingPoints`
(`+0x12C`) and `GetCastingPointsMax` (`+0x128`), writes it via `SetGText`, and shows the Mana icon.
This changes **no** existing hero/unit logic — it only adds a display — so the crash path below is
never touched. Cave lives in a **new `.sc` PE section**, runtime VA **`0x60C000`** (raw base
`0x0060C000`, raw limit `0x0060C200` — later grown into by the book-filter and scroll-book caves, see
below). Both exes patched (either can be the launcher).

**Field/thunk reference** (AoWz.exe, image base `0x400000`): unit-card paint `0x407DB8`; upkeep hooks
`0x40916A`/`0x4091A6`; `TAOWLabel.SetGText` `0x403254`; `IntToStr` `0x4013AC`; `@LStrCatN`
`0x401128`; `@LStrArrayClr` `0x4010E0`; `"/"` literal `0x404234`; `@IsClass` `0x401070`; form fields
UpkeepIcon `+0x1D4`, ManaIcon `+0x6C`, UpKeep `+0x1D8`, **Mana `+0x70`**; unit vtable `+0x128`
GetCastingPointsMax, `+0x12C` GetCastingPoints, `+0x148` GetAbilityEnabled.

⚠ **Never patch the `is THero` gate at `0x407E43`** — see **Failed approaches** below; it crashes.

---

## Multi-turn channelling and the tier gate (M1 / M2)

Investigated and applied `Modding Resources/Zig notes/06-unit-spellcasting.md`
(2026-07-06), whose analysis ran against **vanilla** Ghidra bytes (the live file is separately
patched — e.g. gate G6 still reads `CALL @IsClass` there). Two detection primitives underlie both M1
and M2:

- **Ability level**: `TAbstractUnit.GetAbilityLevel(unit, abilityID)` @`0x5577F658` → byte, 0 if
  absent. Virtual, unit VMT slot `+0x144`. Mechanism: `GetAbilityLevel` →
  `TAbilityControl.GetAbility(*(AoWHSSet+0x80), 0x34)` returns the `TSpellCastingAbility` flyweight
  (a `TMultiLevelAbility`), whose `GetLevel(unit)` @`0x557651D8` does
  `data = GetAbilityData(unit, ability[+0xc]); return data ? *(byte*)(data+0xc) : 0`.
- **Spell research tier**: resolve id → `TSpell*` via `TSpellControl.GetSpell(*(AoWHSSet+0x84),id)`
  @`0x55779AC8`. `TSpell+0x14` = base mana; `+0x20` = sphere byte (**0 = Cosmos**); **`+0x21` =
  research tier, range 1–4**; `+0x22` = category (2 = global enchantment).

### M1 — multi-turn accrual fix

**Root cause of the freeze:** casting progress accrues **only** inside `THero.NewTurn` @`0x55787FCC`
— Phase-1's `cave_unit_newturn` called just the *base* `TAbstractUnit.NewTurn` + a bare point refill,
so a unit's in-progress spell (`+0x84`) never advanced `+0x88`, and `CastingReady` was never true.
Completion itself was already unblocked (Phase-1 gate **G6**, the is-THero inside
`TSpellCastEventLog.Execute`) — only accrual was missing.

**Landmine ruled out:** simply repointing `NewTurn` at `THero.NewTurn` outright is unsafe — its first
call is `THero.ValidateHeroUpgrade` @`0x55787D54`, deeply hero-specific (experience via vtable
`+0x15C`/`+0x160`, `HeroExperienceTable`, level cache `+0x4C`, fires `THeroUpgradeEventLog`); on a
unit those vtable slots are not experience accessors → garbage dispatch. It does not early-out for
owned units (its `owner==0` guard fails for real players), so the whole-function redirect is unsafe.

**The fix, `build_spellcast_multiturn.py`:** a **new** `cave_unit_newturn` @ **`0x5580D940`**
(fresh zero space right after Phase-1's old cave, which ends ≈`0x5580D93A`) replicates the `NewTurn`
prologue (`push ebx/esi/edi`; call base `TAbstractUnit.NewTurn` `0x55780D4C`; owner check), then
**`jmp 0x55787FEC`** — straight into `THero.NewTurn` just **past** `ValidateHeroUpgrade`. The hero's
own refill+accrual+ready-event code then runs in place (with its already-`.reloc`'d globals intact);
its own epilogue (`POP EDI/ESI/EBX/RET`) balances the cave's matching prologue pushes. C1 (VMT
`+0x13C`, both `TUnit` `0x55710CAC` and `TAdjustableUnit` `0x55712A54`) is repointed from the old
Phase-1 cave (`0x5580D90D`) to `0x5580D940`; the old cave is left as harmless dead bytes. Completion
still rides Phase-1 gate G6, already unblocked.

Predicates (for reference): `Casting` @`0x89598` = `+0x84 != 0`; `CastingReady` @`0x895A4` =
`+0x84 != 0 && +0x88 == +0x8C`; `CastingDone` @`0x893E8` clears the cluster (mana already paid up
front by `ExecuteStartCasting`).

### M2 — "level ≥ tier" cast gate, v1 → v2 (item-aware fix)

Directly computable once both primitives above exist: `castable ⟺ GetAbilityLevel(unit,0x34) ≥
TSpell[+0x21]`. **Injection point:** `THero.CanCastSpell` @`0x55789710` — the shared strategic
chokepoint the exe already calls generically on the caster object (hero or unit); it already resolves
the `TSpell` into a register. A 6-byte inject at **`0x5578974D`** (right after `GetSpell` resolves the
spell — overwrites `mov esi,eax; movsx edx,[ebx+0x24]` with `E9 rel32 + NOP`) diverts into
`cave_tiergate` @ **`0x5580D95E`** (immediately after the new `cave_unit_newturn`, bounded above by
`build_spellcast_persist.py`'s cave at `0x5580D990` — 50-byte slot). The cave replicates the two
displaced instructions, compares `GetAbilityLevel(caster,0x34)` to `TSpell+0x21`; below tier, it
blocks via the function's own fail exit (`xor ebx,ebx; jmp 0x55789826`); otherwise it continues at
`0x55789753`. **Applied to units AND heroes** as a 2026-07-06 decision — `CanCastSpell` is the shared
chokepoint and the player's *global* spellbook casting goes through `TPlayerMagicControl` instead, so
the wizard/leader's own non-hero-object casting was unaffected either way. Also gates the AI
(`TUnitSpell.AI*` routes through `CanCastSpell` too). ✅ CONFIRMED WORKING (2026-07-06).

**v1 bug, fixed 2026-08-28 (✅ CONFIRMED WORKING):** `cave_tiergate` v1 read the caster's level by
**calling the base implementation directly** — `mov edx,0x34; call 0x5577F658`
(`TAbstractUnit.GetAbilityLevel`). But `THero` **overrides** that slot: VMT `+0x144` →
`THero.GetAbilityLevel` @`0x5578831C`, which searches self → `THeroItems` → inventory. A static call
to the base **bypasses the override**, so a hero (or by extension any caster) with **item-granted**
Spellcasting read level 0 and every spell silently failed the tier compare — silently, because the
fail arm returns with no message: the spellbook opened, a spell was clicked, and nothing happened.
**Fix:** dispatch through the vtable instead — `mov ecx,[eax]; push 0x34; pop edx; call
[ecx+0x144]` — the item-aware slot. (The `push 0x34; pop edx` instead of `mov edx,0x34` is
deliberate: it sets the full 32-bit EDX in 3 bytes instead of 5, which is what keeps the cave inside
its slot — see the keystone push-imm8 trap noted in the project's standing traps; always disassemble
what you assembled rather than trusting the byte-count arithmetic.) v1's exact byte signature is kept
in the script as an accepted prior state, so a re-run **re-tunes in place** rather than demanding a
revert-then-reapply (which the project's own convention forbids). Paired with the exe-side fix,
`build_unitwin_ability.py` (item-granted Spell Casting usable — CONFIRMED 2026-08-28, out of scope
here).

**No surgical `--undo` exists for M1/M2 in `build_spellcast_multiturn.py`** — only `--apply`, with a
re-tune-in-place ladder for known prior states. See **Open items**.

### M2 reversed to units-only — 🔨 APPLIED, UNTESTED (2026-09-03)

**User ruling 2026-09-03:** *"Spellcasting level should only restrict tier of spell that's castable
for units, not heroes."* This **reverses** the 2026-07-06 "units AND heroes" decision above, which
had never been updated to reflect the change until now. Heroes and the leader now cast anything the
player has researched, regardless of Spellcasting level; units keep the level ≥ tier limit.

**Two halves, both required — either alone is a silent no-op:**

| half | file | mechanism | revert |
|---|---|---|---|
| **cast gate** | `AoWEPACK.dpl` | `build_spellcast_herotier.py` retargets the 4 rel32 bytes at `0x5578974E` (M2's hook inside `CanCastSpell`, i.e. `CANCAST_INJECT+1`) from `cave_tiergate` to a new `cave_herotier` @ **`0x55846000`** (own reservation, span 0x80 owned/zeroed on undo, zone end `0x55848000` — deliberately a *separate* reservation, because `cave_tiergate`'s own 50-byte slot was already ~48 B full and an `IsClass` test costs ~25 B more, too big to extend in place). The cave: `IsClass(caster, THero)?` — **yes** (hero *or* `TLeader`, its subclass): replicate the two displaced instructions and `jmp 0x55789753` == vanilla, no tier test at all; **no**: `jmp 0x5580D95E`, straight into the **unmodified** `cave_tiergate`, which still does the level≥tier compare for units. | `python build_scripts/build_spellcast_herotier.py --undo --apply` |
| **book filter** | `AoWz.exe` + `AoWzCompat.exe` | 15 bytes each inside `cave_bookfilter`'s `_loop`, **size-neutral reorder** (36 B both ways — `.sc` has 0 spare) — hero-family test moved ahead of the tier test. Lives in `build_scroll_spellbook.py` (it owns the cave — see next section). | `python build_scripts/build_scroll_spellbook.py --undo --apply` — ⚠ **also removes the scroll feature and re-breaks this exemption**, see below |

`cave_tiergate` itself is **not** modified by the herotier patch — `build_spellcast_multiturn.py`
verifies it byte-for-byte on every run, and its hook-entry check now accepts `cave_herotier`'s address
as a **second valid "already applied" state**, so a dry run stays clean and a later `--apply` of
*that* script cannot clobber the exemption.

**Why `IsClass`, not a field test:** `IsClass(obj, THero)` is the engine's own test, true for `THero`
**and** its descendant `TLeader` (the player's wizard) — exactly the "heroes and leaders" set the
ruling names. Verified directly in the script, not assumed: `[0x55711FAC]` → VMT `0x55711FEC` whose
`[VMT-0x20]` reads `"THero"`; `[0x557121F8]` → VMT `0x55712238` reads `"TLeader"`.

**⚠ Sanctioned asymmetry — do not "harmonise":** `build_scroll_spellbook.py`'s scroll-append stage
keeps its **own**, separate `tier > level → skip` filter (a 2026-07-30 decision, left standing
2026-09-03) — a hero now casts any *researched* spell regardless of tier but still cannot cast a
too-high-tier *scroll* spell. Scrolls are deliberately stricter than research.

**Revert order for the whole 2026-09-03 ruling** (both halves):
```
python build_scripts/build_spellcast_herotier.py --undo --apply     # DLL first
python build_scripts/build_scroll_spellbook.py  --undo --apply      # exes second
```
Undoing `build_spellcast_herotier.py` **alone** is safe and independent — it just puts every caster
back under the DLL-side gate, and the exe-side book filter (still hero-exempt) briefly disagrees with
it (a hero would see a spell it can no longer click — silently, per M2's fail arm). Undo both, in this
order, to avoid that window. Undoing **`build_scroll_spellbook.py`'s `--undo` alone** is the more
dangerous direction — see the callout in the next section.

**In-game checklist (nothing here is confirmed yet):**
1. Give a hero Spellcasting II and research a tier-4 spell → the spell should now appear in that
   hero's casting book **and cast successfully** (previously hidden and, if forced, blocked).
2. Give a **unit** Spellcasting II with the same research → the tier-4 spell should still be **hidden**
   from the unit's book and still **blocked** at cast time if reached another way.
3. A hero **without** Spellcasting still cannot open a casting book at all (regression check,
   unrelated to this change).
4. A scroll for a tier-4 spell is still **inert** in the hands of a low-Spellcasting hero (the
   sanctioned scroll/research asymmetry) — confirm it, do not "fix" it.
5. AI sanity pass — the AI lists via `TPlayerMagicControl.ListSpells` directly in the DLL, so it
   should be unaffected by the exe-side book-filter reorder either way; the DLL-side cast gate change
   does apply to it (AI heroes may now attempt higher-tier spells).

---

## Casting-book filters (M3 / M4) and the shared `cave_bookfilter`

### Why this is an exe patch, not a DLL patch

The "Cast Global Spell" book is filled by **`AoW.exe` calling `TPlayerMagicControl.ListSpells`
directly** (import thunk `0x402654`, 5 call sites) — the exe **never calls `THero.ListSpells`**,
confirmed via `re_tools/pescan.py iatrefs`: the exe's only `ListSpells` import is
`TPlayerMagicControl.ListSpells`. **The first M3 attempt was a DLL-side hook on
`THero.ListSpells`'s internal call — it was completely inert**, because that function is never
reached from the exe. It was reverted the same day (2026-07-06) by restoring
`AoWEPACK.dpl.pre-multiturn` and reapplying `build_spellcast_multiturn.py` (M1+M2 only) — a command
that is **no longer usable**, since that backup is long gone (see Open items); this is recorded only
as the historical shape of the cleanup, not a live procedure.

### M3 / M4 as originally built — `build_spellcast_book_exe.py`

The book-population sites carry no caster level directly, but the current caster is in the window
object at `[window+0x22C]` (proven: the `CastSpell`/`CanCastSpellInstantly` sites in the same
functions call `THero.CastSpell([window+0x22C], …)`). At every `ListSpells` call site,
`EDX = &collector = window+0x224`, so **`caster = [EDX+8]`**. All 5 `call 0x402654` sites
(**`0042F0F9`, `0042F20C`, `00430D58`, `00430DDE`, `00430EDD`**) were redirected to a new
`cave_bookfilter` @ **`0x0060C0A8`** (inside the card patch's `.sc` section — this feature **depends
on** `build_spellcast_card_v2.py` having run first). The cave runs the real `ListSpells` to fill the
collector, reads `caster=[EDX+8]`, gets `level = caster.vtable[+0x144](0x34)`, then **compacts the
collector's `TSpellList` in place** (`list=[EDX]; TList=[list+4]; count=[TList+8]; items=[TList+4]`),
dropping any entry whose `TSpell+0x21 > level` (**M3**) — grown to 84→130 B to add: drop a Cosmos
spell (`TSpell+0x20 == 0`) unless the caster is hero-family (**M4**, `IsClass(caster,THero)`, exe
classref `[0x45DFC4]`, `@IsClass 0x401070`). No DLL calls, null-caster guarded, `ebx/esi/edi`
preserved. All **three** book tabs (`TSpellBook+0x222`: 0=Combat, 1=Unit, 2=Global) share these five
sites, so one cave covers strategic **and** tactical casting.

Both ✅ CONFIRMED WORKING **in-game** (user, 2026-07-06): a low-level caster's book stopped listing
too-high-tier spells; a **unit**'s book showed **no Cosmos** spells at any level while a **hero**'s
and the **player's own (leader)**'s book kept them. **Accepted gap (WON'T FIX, user 2026-07-06):** the
AI still lists candidates via `TPlayerMagicControl.ListSpells` directly inside the DLL, bypassing this
exe cave entirely, so **AI units can still cast Cosmos spells** — judged not worth a riskier DLL-side
classref-in-a-rebasing-cave fix for no human-visible benefit. **Editor not covered**: `AoWDevEd.exe`
uses `TSpellControl.ListSpells`, a different caster-less enumerator, for its own book.

### The cave's second owner — `build_scroll_spellbook.py`

⚠⚠ **`cave_bookfilter` is now SHARED, and `build_scroll_spellbook.py` owns the live bytes.** On
2026-07-30 that script — building an unrelated feature, scrolls as a permanent per-hero spellbook
grant (item type 5, `itScroll`) — **rewrote `cave_bookfilter` in place** (84→130 B *pre-existing* M3/M4
prune, grown to up to 344 B) rather than chaining a second cave, because `.sc` had only 0xD6 free
bytes after the old cave (0x158 = 344 B counting the cave itself) and the category mask (`CL`) is
consumed inside the same prologue that an append stage would need. It **absorbed the M3/M4 prune
logic verbatim** as stage 1, then appends spells granted by carried scrolls as stage 2. Per
CLAUDE.md's own convention for a shared/crowded cave: verify-before-write against either the
currently-installed bytes or the new ones, assert the grown-into zone is still zero, fresh
feature-named backup (`.pre-scrollbook`) — the same pattern as `build_invis_penalty.py` rewriting
`build_trueseeing.py`'s caves.

**Consequence — `build_spellcast_book_exe.py` is now effectively retired in practice.** A plain dry
run of it reports **MISMATCH** on the cave — this is **expected**, it is that script observing the
scroll rewrite, not a broken state. **Do not `--apply` it and never force it**: doing so would
silently overwrite the cave with book_exe.py's own shorter version and destroy **both** the scroll
behaviour **and** the 2026-09-03 hero-tier exemption (its own verify step no longer recognises the
current bytes as "original", so it would simply abort rather than force — but that abort is the
correct outcome, don't work around it). **To re-tune the tier/Cosmos filter, edit
`build_scroll_spellbook.py`'s `_loop` stage, not `build_spellcast_book_exe.py`.**

**⚠ `build_scroll_spellbook.py --undo` silently re-breaks the hero-tier exemption.** `--undo` restores
`build_spellcast_book_exe.py`'s **original** 130-byte filter, which prunes by tier for **every**
caster — heroes go back to being tier-limited, with no error and nothing in any log, and it also
removes the scroll behaviour (probably the actual target of the undo). Verified 2026-09-03: after
that undo, `build_spellcast_book_exe.py` itself reports a clean `6 already, 0 to patch` while heroes
are tier-limited again — nothing anywhere flags the regression. **To drop only the scroll feature and
keep the hero exemption**, re-apply with `--append-upto=0` instead of undoing — this keeps the
current (hero-exempt) stage-1 prune and emits no scroll-append stage.

**Engine primitives reached with no new imports** (reusable idiom): `TSpellControl.GetSpell` and
`System.@IsClass` are already imported (thunks `0x4025A4`/`0x401070`); `TSpellList.Add` is **not**
imported, so it is reached via the runtime rebase delta —
`dll_delta = [0x0045DF78] − 0x558FA044` (IAT slot for `AoWE.AoWHSSet` minus its preferred VA), then
`call 0x5577A03C + dll_delta` — the same trick documented in `08-editor.md`. Using the
real `TSpellList.Add` avoids the `TList` capacity edge case a manual array append would hit.

**Failed approach, worth keeping (bisect story):** the first full version of the scroll-append stage
**broke the spell book in-game** (spells and icons missing, error dialog, freeze — clean A/B,
2026-07-31). A `--append-upto N` bisect control (0=prune only … 5=full) narrowed it: levels 0–3
(caster pointer, `+0x74` inventory, virtual `GetCount`, the raw array walk) all worked; level 4/5
broke. Root cause: **the hero inventory array can hold entries that are not live `TItem`s** — these
engine lists are sparse (removal can be sparse-or-compacting by a style bit), so a slot can
legitimately read a small non-pointer value at what looks like the item-type byte, and a type-byte
test alone cannot tell a dead slot from a live one. A garbage id reached `GetSpell`, and a bogus
`TSpell*` got appended, choking the icon draw. **Fix:** before touching the type byte, require the
entry's **VMT** to *be* `TItem`'s (`cmp [entry], TITEM_VMT+dll_delta`) — reached via the same rebase
delta as `TSpellList.Add`. Paid for by dropping a planned dedupe pass (`.sc` was exhausted at
344/344 bytes); the only cost is that a scroll whose spell the player has *also* researched now
appears twice in the book.

### M3/M4 status after the shared-cave history

Both prune rules are still the **live, installed** behaviour (M4 unchanged since 2026-07-06; M3
unit-only since 2026-09-03) — the cave's *owner* changed, its *behaviour* for M4 did not, and its
behaviour for M3 changed exactly as intended by the 2026-09-03 ruling above. See the status table for
exact per-behaviour dates.

---

## C2 — save/load persistence of casting state

`build_spellcast_persist.py` → `AoWEPACK.dpl`, backup `AoWEPACK.dpl.pre-persist` (gone — see Open
items), no `--undo`. Independent of M1/M2 (reverts alone, if it had a revert). ✅ CONFIRMED WORKING
(2026-07-06): a unit's casting state (points / in-progress spell / progress) survives a save→load
round-trip.

**Problem:** `TUnit`/`TAdjustableUnit` `ReadWrite` (the object serializer) never wrote the casting
cluster, so on load a unit's points reset to 0 (refills next turn) and any in-progress channel was
lost. `THero.ReadWrite` @`0x55788880` *does* serialize those fields; this mirrors it for units.

**Save format = property table** (`TPropertyTable.PropertyExist`): every field has a numeric tag; a
missing tag on read falls back to a default. Appending new tagged fields is therefore compatible
**both directions** — an old/pre-mod save lacks the tags (unit loads with cleared casting state), and
a mod-made save loaded by an *unpatched* game simply ignores the extra properties (no corruption).

**Fields persisted** (exact transcription of THero's own tagged stream calls): `+0x80` points (byte,
tag `0xD`, stream vtable `+0x30`); `+0x84` in-progress spell id (int, `0xE`, `+0x2C`); `+0x88`
progress (int, `0x1F`, `+0x2C`); `+0x8C` mana required (int, `0x22`, `+0x2C`); `+0x90` ready-event id
(int, default −1, tag `0x23`, `+0x40`). **Not** persisted: `+0x7C` power-source ptr — `THero` doesn't
persist it either (runtime-only; units use the player's mana pool, no per-unit power source object).

**Mechanism:** redirect the `ReadWrite` VMT slot **`+0x18`** of each unit class to a thin wrapper that
calls the **original** `ReadWrite` (different per class!) then a shared `cave_cast_fields` @
**`0x5580D990`** (register/rel32 only — this is the same address `build_spellcast_multiturn.py` uses
as `cave_tiergate`'s upper slot bound) that appends the 5 tagged fields. `TUnit` VMT `+0x18` =
`TUnit.ReadWrite` (`0x55782CEC`); `TAdjustableUnit` VMT `+0x18` = `TAbstractUnit.ReadWrite`
(`0x557820E4`) — two different originals, hence two wrappers. One bidirectional cave handles both
save and load, because the stream methods read or write per the stream's own mode byte (mirroring
`THero.ReadWrite`).

---

## Hero mana generation = Resistance × Spellcasting level

`build_spellcast_manares.py` → `AoWEPACK.dpl` **only**. ✅ CONFIRMED WORKING (2026-08-27), user-tested.
Backup `AoWEPACK.dpl.pre-spellcastmanares` (not currently present anywhere in the tree — see Open items;
irrelevant here because a surgical **`--undo`** exists and is the real revert path).

A hero's per-turn mana income was a flat five-entry table keyed on Spellcasting level. It now scales
with the hero's Resistance as well:

| | I | II | III | IV | V |
|---|---:|---:|---:|---:|---:|
| vanilla (`level*5 + 5`) | 10 | 15 | 20 | 25 | 30 |
| Ziggurat, until 2026-08-27 | 10 | 20 | 40 | 60 | 90 |
| **now** | level × Resistance (worked examples below) | | | | |

Worked values: RES 4 → 4/8/12/16/20 · RES 6 → 6/12/18/24/30 · RES 8 → 8/16/24/32/40 · RES 12 →
12/24/36/48/60 · RES 20 → 20/40/60/80/100 · RES 40 (the clamp) → 40/80/120/160/200. At the chassis
Resistances the game actually ships (4–12 across the 38 `HERORES.PFS` chassis records: RES 4 ×7, RES
6 ×15, RES 8 ×13, RES 10 ×1, RES 12 ×2), this is a **net nerf** against the old table and lands near
*vanilla* levels; it only overtakes 10/20/40/60/90 from about RES 18. The 1× multiplier was chosen
deliberately by the user after seeing a 3× table.

### The chain and the patch

```
THero.SetPlayer  @0x55787388  \  register a THeroPowerSource with
THero.Activate   @0x55787512  /  TPlayerMagicControl.RegisterPowerSource @0x5577D3C0
TPlayerMagicControl.GetPower  @0x5577CA00   sum Power() over TPowerSourceList
  THeroPowerSource.Power      @0x557867D0   -> hero.vtable[+0x134]
    TLeader.GetPowerGeneration @0x5578B43C  (THero's slot @0x557885E4 tail-calls this)
        GetAbilityEnabled(0x34) via vtable[+0x148]     item-aware
        GetAbilityLevel(0x34)   via vtable[+0x144]     item-aware
        call 0x557885EC                               <-- the only patched bytes
GetManaIncome @0x5577C95C -> GetNetPowerToMana @0x5577CEE4 (research share, player-type factor)
```

`GetNetPower @0x5577CEC4` halves the total when bit 3 of `[globalmagic+0x10]` is set, and
`GetNetPowerToMana` multiplies by a per-player-type factor off `[player+0xA7]` — both sit above this
change and are untouched.

22 bytes, replacing the lookup table **in place** — no cave, no hook, no displaced host bytes:

```
557885EC  0f b6 c0           movzx eax, al             ; Spellcasting level
557885EF  50                 push  eax
557885F0  89 d8              mov   eax, ebx            ; self (THero / TLeader)
557885F2  8b 10              mov   edx, [eax]
557885F4  ff 92 cc 00 00 00  call  [edx + 0xCC]        ; THero.GetResistance -> al
557885FA  0f b6 c0           movzx eax, al
557885FD  5a                 pop   edx
557885FE  0f af c2           imul  eax, edx            ; RES * level
55788601  c3                 ret
```

Trailing 18 bytes of the 40-byte zone are zeroed. A `MULTIPLIER` constant in the script emits an
extra `add`/`lea`/`imul` tail if it is ever raised above 1 — the only edit needed to re-tune.

### Why no cave was needed, and why that is provably safe

`0x557885EC..0x55788613` is 40 bytes of in-function slack, hard-bounded by
`THero.GetCastingPointsMax @0x55788614`. Re-proved on every run, not just assumed:

- a full-file sweep for rel32 `E8`/`E9` targets and absolute dwords finds **exactly one** reference
  into the range — the `call` at `0x5578B461`;
- the range carries **no `.reloc` entries**;
- `THero`/`TLeader` VMT `+0x134` still point at `0x557885E4`/`0x5578B43C`; `TUnit`/`TAdjustableUnit`
  VMT `+0x134` still hold the zero stub;
- the caller's 44-byte body is byte-compared, not just the call site — the patch depends on
  `ebx = self` (set by `mov ebx,eax` @`0x5578B43D`, callee-saved under the Delphi convention, which
  the caller's own `pop ebx` @`0x5578B466` also relies on); if a future patch ever displaces that
  prologue, EBX could stop being self, so the script refuses rather than reading a stale register.

Because no cave is allocated, this feature **cannot** collide with a cave allocator (contrast the
Magebane/dispelmagic5 collision elsewhere in the project).

### ⭐ The 10/20/40/60/90 table was an orphan — byte-diff before you patch, always

The most reusable finding here: **byte-diffing the live DLL against `AoWEPACK_original_backup.dpl`
before patching** (not only when something looks wrong) turned up that the table this script replaced
was **not vanilla and not owned by any script**. Vanilla computed `level*5 + 5` inline
(`lea eax,[eax+eax*4]; add eax,5`), and `THero.GetPowerGeneration` was a full duplicate copy of the
same body. A **pre-convention Ziggurat patch** — predating `build_scripts/`'s own conventions —
collapsed `THero`'s copy into `call TLeader...; ret` (6 bytes) and spent the freed 40 bytes on the
10/20/40/60/90 table, retargeting `TLeader`'s tail to `call 0x557885EC`. `grep -rlin
'5578B43C|557885EC' build_scripts/` found only a disclaiming comment in `build_spellcast.py`. Without
the diff, this would have been recorded as "changed vanilla's `level*5+5`", and **`--undo` would have
restored the wrong bytes**. ⚠ As shipped, **`--undo` restores the TABLE, not vanilla** — that is
deliberate (it returns the install to its pre-*this*-feature Ziggurat state) — there is no script
that restores vanilla's inline formula.

### Scope, and what stays unaffected

`vtable[+0xCC]` is `THero.GetResistance @0x5578850C`, identical for `THero` and `TLeader`, so one
`call` serves heroes and the leader. It is the **card** value: chassis + bought points + ability
modifiers + item bonuses + morale, clamped **[0, 40]** (the project's doubled-stat-scale ceiling) and
returned in AL — so `movzx eax,al` is provably safe (max output 5×40=200). Consequences that are
*behaviour*, not bugs: income moves with morale (an unhappy hero earns less), and RES items raise
income. Item-granted Spellcasting also counts (the item-aware `+0x148`/`+0x144` pair is used, not the
self-only `+0x84`/`+0x88` pair). `GetInherentResistance @0x55788500` (`+0xB4`: chassis + bought points
only, no items, no morale, unclamped, 3 bytes cheaper) was considered and **not** taken — the user
asked for "the hero's RES stat", i.e. the card value.

**Units are unaffected, for free.** `TUnit`/`TAdjustableUnit` VMT `+0x134` still point at
`TAbstractUnit.GetPowerGeneration @0x5577FDB4` = `xor eax,eax; ret` — `build_spellcast.py` never
redirected that slot ("Phase 3 — cancelled", the LOCKED scope decision below). This script asserts the
stub is untouched on every run and aborts rather than silently turning units into mana sources.
**One binary only** — no other module (`AoW.exe`, `AoWCompat.exe`, `AoWTCPCK.dpl`, `aowInt.dpl`,
`AoWDevEd.exe`) carries a copy of the formula or any `call [reg+0x134]`; the exe drives the magic
window through imported `GetPower`/`GetNetPower`/`GetManaIncome` and calls `Power()` dynamically
through the source's own VMT, so every display and the AI mana budget follow the change for free.

**Data + Manual, updated the same day:** `Release/Ability.pfs` record 62 tag 5 (Spell Casting; record
id = ability id + 10) now reads *"...On a hero, mana generation per turn equals Resistance x
Spellcasting level"* (the old text — "5/15/30/50/75 mana generation" — was already wrong even before
this change, against a 10/20/40/60/90 code table). `build_ziggurat_manual.py` gained two
`MISC_OVERRIDES` rows for the same reason the workbook can't be edited directly (it's a frozen
historical snapshot) — the workbook had split `level*5+5` across two separate rows, which is why its
`5/10/15/20/25` had looked like a plausible vanilla value and was not.

---

## Scope decisions still standing

- **Mana generation for unit casters — LOCKED, never to be built.** Would break the economy. Phase 3
  (`GetPowerGeneration` redirect on `TUnit`/`TAdjustableUnit` VMT `+0x134` + `THeroPowerSource`
  lifecycle on units) is **cancelled**, not deferred. Units draw from the *player's* mana pool,
  throttled by their own casting points; they must never become mana *sources*. Every relevant script
  (`build_spellcast.py`, `build_spellcast_manares.py`) re-asserts the stub on every run and aborts if
  it ever moves.
- **Multi-turn channelling and the tier gate apply to units AND heroes — SUPERSEDED 2026-09-03.** See
  the dedicated section above; heroes/leader are now exempt from the tier gate specifically (not from
  multi-turn channelling itself, which heroes always had).
- **AI casting Cosmos spells with units — accepted, WON'T FIX** (2026-07-06). The AI lists via
  `TPlayerMagicControl.ListSpells` directly inside the DLL, bypassing the exe's book filter; judged
  not worth a DLL-side classref-in-a-rebasing-cave fix for no human-visible benefit.
- **`AoWDevEd.exe`'s own casting book is not covered** by M3/M4 — it uses a different, caster-less
  enumerator (`TSpellControl.ListSpells`). Not in scope; would need a separate, harder patch.

---

## Open items

### No revert path exists for the Phase-1/Phase-2/M1-M2-v1/C2/card/book-filter layer

Checked directly against the live tree (no file named `*.pre-spellcast*`, `*.pre-multiturn*`,
`*.pre-persist*`, `*.pre-cardv2*`, `*.pre-bookfilter*`, or `*.pre-scrollbook*` exists anywhere in it):
**`build_spellcast.py`, `build_spellcast_tcpck.py`, `build_spellcast_multiturn.py`,
`build_spellcast_persist.py`, `build_spellcast_card_v2.py` and `build_spellcast_book_exe.py` have
neither a surgical `--undo` nor a usable `.pre-*` backup.** The backups these scripts once wrote either
never existed under a name still current, or — like the rest of the project's root-level snapshot
stack — were pruned in routine cleanup, since none of them was a safe single-layer revert to begin
with (each sat many features deep even before `Modding Resources/backups/` itself was deleted
2026-08-08). This is foundational: dozens of later features assume `TUnit`'s grown 0x94-byte instance
and the redirected VMT slots. Treat this layer as **permanent** for practical purposes. If a genuine
removal is ever required, it needs a **hand-written surgical `--undo`** modelled on
`build_spellcast_herotier.py` / `build_scroll_spellbook.py` / `build_spellcast_manares.py` — restore
the displaced hook bytes and zero only the caves this feature itself owns, verify-before-write,
touching no backup — not a `.pre-*` restore (which would also destroy everything layered on
`AoWEPACK.dpl`/`AoWTCPCK.dpl`/the exes since). ⚠ `AoWEPACK.dpl.pre-herotier` was minted 2026-09-03
for the one script that does have surgical undo, as a one-layer safety margin rather than the actual
revert path — **it no longer exists**, having gone with `<root>/backups/` on 2026-09-10. No binary
`.pre-*` snapshot survives anywhere in the tree.

### Speculative, unbuilt extensions

Three feature ideas were investigated on top of the (already-working) mod and **nothing was applied**
— no build script exists for any of them. Kept here because the primitives are reusable and the
investigation is otherwise nowhere else on record.

- **Per-unit intrinsic spellbook** (cast a species-specific spell regardless of research) — FEASIBLE
  but HARD (confidence 72%). Casting itself needs **no research check** at all —
  `THero.CanCastSpell @0x55789710` checks only not-already-casting, mana ≥ cost, and the spell's own
  `CanActivate`; research gating lives *entirely* in the book. So an intrinsic spell only needs to be
  made to *appear*. The crux is that the exe imports `TSpellList.GetCount/GetSpell/Clear/Delete/
  Create/SortOnLevel` but **not** `.Add` — reachable either as a manual `TList` append inside
  `cave_bookfilter` (6-instruction extension, degrades gracefully when the list is exactly at
  capacity) or via the same `TSpellList.Add` rebase-delta trick `build_scroll_spellbook.py` uses.
  Species key: `unit+0x40 → TUnitResource`, `resource+0x4 → list`, `list.vtable[0x84]() →
  UnitResourceIndex` (the stable per-species id `build_firefeed.py` also keys off). Would need its own
  M2 interaction (an intrinsic spell above the caster's level is still blocked at cast time).
- **HP or MV cost for casting**, in addition to points — FEASIBLE (85%), one cave after
  `THero.CastingDone @0x557893E8` (the shared instant-cast deduction sink; mirror in
  `ExecuteStartCasting @0x55789130` for multi-turn channel-start). HP via the clamping virtual
  `SetHitPoints` (vtable `+0xE4`, clamps to `[0,GetMaxHP]`); MV as a raw `unit+0x3D` byte
  (no clamping accessor — needs its own underflow guard). "**Instead of** points" is harder (60%):
  points aren't just deducted, they gate the instant-vs-multi-turn choice, so redirecting the
  *affordability* reads too is a multi-site, easy-to-desync change.
- **Unit-enchantment cost/upkeep scaled by target level** — upkeep scaling FEASIBLE (85%), one hook at
  the tail of `TUnitEnchantmentAbility.Expand @0x55765894` (target unit and fresh enchantment both
  live there); `SetUpkeep(ench, base × f(GetUnitLevel()))` then flows into
  `TPlayerMagicControl.GetManaUpkeep`'s sum for free. Cast-cost scaling is harder (55%) — reachable for
  the strategic unit-spell path (`TUnitSpellTE.Process @0x5577AB24`) but not traced for the
  combat-cast path (`TCombatSpellCaster`). **SIZE is a dead scaling axis** —
  `TAbstractUnit.GetUnitSize @0x5577F184` returns a hardcoded constant 1 for every unit in the game.

### Other loose ends

- The EXE casting-window "might need a shim for units" risk flagged in the original feasibility
  analysis never materialised — Phase 0 found the strategic UI already caster-generic. Resolved, not
  open.
- `TAdjustableUnit`'s override surface was checked once (no `NewTurn` override; `ReadWrite` override
  at `0x557820E4`) before Phase 1/C2 shipped; nothing has re-checked it since further features layered
  on top of `AoWEPACK.dpl`. Low risk, not re-verified.

---

## Failed approaches — do not retry

- **DLL-side hook on `THero.ListSpells` for the casting-book filter (original M3 attempt).** Inert —
  the exe never calls `THero.ListSpells`, only `TPlayerMagicControl.ListSpells` directly (5 sites,
  confirmed via `pescan.py iatrefs`). The book must be filtered where it's actually built: the exe.
- **`cave_tiergate` v1 — static call to `TAbstractUnit.GetAbilityLevel` (the base, not the vtable
  slot).** Bypasses `THero`'s item-aware override, so item-granted Spellcasting silently read level 0
  and every spell failed the tier compare with no message. Always dispatch ability queries through
  the vtable slot the caster's actual class overrides (`+0x144`/`+0x148`), never call a known base
  implementation directly when the object could be a `THero`.
- **Card display: patch the hero window (`0x433A40`/`0x433A64`).** Wrong window entirely — that's
  `THeroInfoDlg`'s side, not `TUnitWindow`'s unit card. No effect on units.
- **Card display: force `edi = unit` at the hero window.** Same wrong window; no effect.
- **Card display: flip the `is THero` gate at `0x407E43` in the unit-card paint function.** **CRASHES**
  (access violation, garbage vtable dispatch). The object tested there is not guaranteed to be a
  `TAbstractUnit`, so calling `GetAbilityEnabled` through `[vtable+0x148]` on it jumps to garbage;
  separately, `edi` is entangled with the paint's hero logic, so a hero *without* Spellcasting gets
  `edi=nil` where downstream code assumes a valid object. **Never patch this gate.** Replacing an
  `is THero` check with a `GetAbilityEnabled` virtual call is only safe where the object is *known* to
  be a `TAbstractUnit` (e.g. the combat gates, where it's always `combatUnit+0x4C`) — not at a general
  gate whose object could be any class.
- **Card display: append casting points to the Upkeep label (`+0x1D8`) via a code cave.** Worked
  mechanically but the label's render viewport clips at the cell boundary (the number was
  guillotined) and its centred alignment (`AlignWidth=awCenter`) caused symmetric overflow. Cosmetic
  dead end — use the Mana label (`+0x70`) instead, which has its own uncramped viewport.
- **Scroll-append stage 4/5 without a VMT-type guard on inventory entries.** Broke the live spell book
  (missing spells/icons, error dialog, freeze). The hero inventory array can hold non-`TItem` entries;
  a type-byte test alone can't tell a dead slot from a live one. Require `[entry]` (the VMT pointer)
  to equal `TItem`'s VMT before touching `+0x34`.
- **Blaming unit-spellcasting's fast-combat gates (G2/G3/G7) for the AI-vs-walled-city freeze.**
  Investigated in depth (`build_fastcast_gate.py`), plausible given three gates sit in the freezing
  code path — but ruled out. The actual cause was unrelated: the combat log's `combatObj+0x4C`
  strategic-unit lookup, nil-checked but not type-checked, read garbage off a `TCombatWall` (which
  reuses that offset for packed setup bytes) and jumped through it as a vtable pointer. Fixed
  elsewhere (`10-ai-and-structures.md` §8, CONFIRMED 2026-07-22); nothing about unit spellcasting
  needed to change.
- **vmtParent swap** (make `TUnit` "inherit" `THero` for RTTI, considered during feasibility). Rejected
  outright — would make every `is THero` check in the entire game true for units (items, levelling,
  joins, death handling), unbounded fallout, never attempted.
- **A companion DLL for per-unit casting state.** An earlier investigation had concluded this was
  necessary; wrong — solved by growing `TUnit`'s own instance size and reusing the engine's
  zero-filling allocator. Never built.
