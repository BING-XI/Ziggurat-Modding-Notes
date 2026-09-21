# AoW1 Unit Spellcasting — Master Index

**Read this first.** Entry point for the unit-spellcasting mod. Details are in the linked docs;
this page is the map + at-a-glance reference + current state.

**Goal of the mod:** make the *Spellcasting* ability (ID `0x34`) work on ordinary (non-hero)
units, and show their casting points on the unit card — done by patching the game's own binaries
(no new DLL).

---

## Status — what works now (all applied & confirmed)

| Capability | Where | Script |
|---|---|---|
| Auto-resolve / fast combat casting | AoWEPACK.dpl | `build_spellcast.py` |
| Manual (tactical) combat casting | AoWTCPCK.dpl | `build_spellcast_tcpck.py` |
| Strategic **instant** casting (cost ≤ points) + ability button | AoWEPACK.dpl | `build_spellcast.py` |
| Per-turn point refill + point/mana accounting | AoWEPACK.dpl | `build_spellcast.py` |
| **Casting points shown on the unit card** | AoW.exe + AoWCompat.exe | `build_spellcast_card_v2.py` |
| **Multi-turn channelling progresses for units** | AoWEPACK.dpl | `build_spellcast_multiturn.py` |
| **"Spellcasting level ≥ spell tier" cast gate (M2)** — **units only** since 2026-09-03 | AoWEPACK.dpl | `build_spellcast_multiturn.py` + `build_spellcast_herotier.py` |
| **Item-granted Spell Casting is usable** — CONFIRMED 2026-08-28 | AoW.exe + AoWCompat.exe | `build_unitwin_ability.py` |
| ↳ ⚠ …and its DLL half: M2's level lookup made item-aware | AoWEPACK.dpl | `build_spellcast_multiturn.py` (v2 cave_tiergate) |
| **Item-granted Healing applies** — CONFIRMED 2026-08-28 | AoWEPACK.dpl | `build_abilityte_itemgrant.py` |
| **…and re-arms each turn** — CONFIRMED 2026-08-28 | AoWEPACK.dpl | `build_healing_rearm.py` |
| **Casting book hides too-high-tier spells (M3)** — **units only** since 2026-09-03 | AoW.exe + AoWCompat.exe | `build_scroll_spellbook.py` (owns the cave; see below) |
| **Cosmos spells (sphere 0) hidden from unit books (M4)** — heroes + leader keep them | AoW.exe + AoWCompat.exe | `build_spellcast_book_exe.py` |

### Tier gate is UNITS ONLY — 🔨 **APPLIED, UNTESTED (2026-09-03)**

User ruling 2026-09-03: *"Spellcasting level should only restrict tier of spell that's castable for
units, not heroes."* Heroes and the leader cast anything researched; units keep the level ≥ tier
limit. **Two halves, both required — either alone is a silent no-op** (book half missing ⇒ the hero
never sees the spell; cast half missing ⇒ the hero sees it, clicks it, and nothing happens, because
`cave_tiergate`'s fail arm returns with no message).

| half | file | what | revert |
|---|---|---|---|
| cast gate | `AoWEPACK.dpl` | `build_spellcast_herotier.py`: retargets the 4 rel32 bytes at `0x5578974E` (the M2 hook inside `THero.CanCastSpell`) to `cave_herotier @0x55846000` (47 B). `IsClass(caster, THero)` → hero/leader jump to vanilla `0x55789753`; units fall into the **unmodified** `cave_tiergate @0x5580D95E`. | `--undo --apply`, round-tripped byte-identical |
| book filter | `AoW.exe` + `AoWCompat.exe` | 15 bytes each inside `cave_bookfilter`'s `_loop` at `0x0060C10E`: the hero-family test moved ahead of the tier test. **Size-neutral reorder** (36 B both ways) — `.sc` has 0 spare. Lives in `build_scroll_spellbook.py`; see the ⚠⚠ note below. | `build_scroll_spellbook.py --undo --apply` — ⚠ also removes scrolls |

`cave_tiergate` is *not* modified, so `build_spellcast_multiturn.py` still verifies it byte-for-byte;
its M2 hook entry gained `0x55846000` as a second accepted applied state so it neither reports a
false mismatch nor clobbers the retarget on a later `--apply`.
⚠ **`build_scroll_spellbook.py`'s stage-2 scroll append keeps its own `tier > level` filter**
(user ruling 2026-07-30), so a hero casts any *researched* spell regardless of tier but still not a
too-high-tier *scroll* spell. **Sanctioned asymmetry — do not "harmonise" it.**

**Applied to (backup state as of 2026-07-30 — the DLL backups MOVED, and are now very deep):**
- `AoWEPACK.dpl` (18 Phase-1 patches, `AoWEPACK.dpl.pre-spellcast`; **+5 multi-turn / tier-gate
  patches (M1/M2), `AoWEPACK.dpl.pre-multiturn`**). Both were **moved** to
  `Modding Resources/backups/` on 2026-07-29/30 — not deleted — but they are the **1st and 2nd of 47**
  layers. The old "restore `.pre-multiturn` to drop only the polish; restore `.pre-spellcast` to drop all
  spellcasting" would now wipe 45 and 46 later features respectively. Undo surgically from
  `build_spellcast.py` / `build_spellcast_multiturn.py` instead.
  (Note `AoWTCPCK.dpl.pre-spellcast` also exists, in the game root — a bare `.pre-spellcast` in these
  docs is ambiguous between the two targets, and only the TCPCK one is a safe single revert.)
- `AoWTCPCK.dpl` (5 patches) — backup `AoWTCPCK.dpl.pre-spellcast` ✅ **exists and is the only layer**,
  so this is a genuinely safe single revert.
- `AoW.exe` + `AoWCompat.exe` — card display (`*.pre-cardv2`) **+ book filter M3 (`*.pre-bookfilter`)**.
  Both exist but are the **1st and 2nd of 9** exe layers: restoring `.pre-cardv2` destroys 8 later
  features, `.pre-bookfilter` destroys 7. Not usable as a revert. The M3 cave shares the card patch's
  `.sc` section.

  ⚠⚠ **`cave_bookfilter` @`0x0060C0A8` is SHARED, and `build_scroll_spellbook.py` owns it.**
  Measured 2026-09-03: that script's **344-byte in-place rewrite is installed and live** on both
  exes (`build_scroll_spellbook.py` reports `2 already apply-state` for `AoW.exe`,
  `AoWCompat.exe` and `AoWEPACK.dpl`). Stage 1 is the unit-spellcasting book filter (M3/M4);
  stage 2 appends spells granted by carried scrolls. The five `ListSpells` call sites are
  unchanged. Consequences:
  - **A plain `build_spellcast_book_exe.py` dry run reports MISMATCH on the cave. That is
    EXPECTED** — it is that script observing this rewrite, not a broken state. **Do not
    `--apply` it and never force it**: it would silently delete both the scroll behaviour and
    the hero-tier exemption below.
  - **Since 2026-09-03 stage 1 also carries the hero-tier exemption** (user ruling: the
    Spellcasting tier limit is for units only). The `_loop` prune tests hero-family first and
    keeps everything for a hero/leader; tier and Cosmos prunes are unit-only. Pairs with
    `build_spellcast_herotier.py` on the DLL side — **both halves are needed; either alone is a
    silent no-op.**
  - ⚠ **`build_scroll_spellbook.py --undo` silently re-breaks the hero exemption.** It restores
    `build_spellcast_book_exe.py`'s original 130-byte filter, which prunes by tier for *every*
    caster. Verified 2026-09-03: after that undo, `build_spellcast_book_exe.py` reports a clean
    `6 already, 0 to patch` while heroes are tier-limited again — nothing anywhere says so.
    Revert order for the whole ruling: `build_spellcast_herotier.py --undo --apply` (DLL) then
    `build_scroll_spellbook.py --undo --apply` (exes). To drop **only** the scroll feature and
    keep the exemption, re-apply with `--append-upto=0` instead of undoing.
  - To re-tune the tier/Cosmos filter, edit the `_loop` stage in `build_scroll_spellbook.py`.
  - `.sc` is **full**: the cave is padded to the section's raw limit `0x0060C200` — **0 spare**.
    Any growth needs a new PE section (pattern: `build_tierresearch_exe.py`'s `.tres`). This is
    why the 2026-09-03 change had to be a size-neutral reorder.
  - **Failed approach, still worth knowing:** the first full version of that rewrite **broke the
    spell book** (spells and icons missing, error dialog, freeze — clean A/B, 2026-07-31). Root
    cause found by the `--append-upto` bisect: the hero inventory array can hold entries that are
    not live `TItem`s, so a type-byte test alone let `GetSpell` run on a garbage id. Fixed by
    requiring the entry's VMT to be `TItem`'s. See `Investigation_Items.md` Feature 1b.

Each build script: run with no args to **verify** current state, `--apply` to write. Idempotent,
verify-before-write, auto-backup. **Revert ≠ "copy the matching backup"** — run
`python "Modding Resources/re_tools/revert_audit.py"` first: `AoWEPACK.dpl` carries 47 layers (42 of them
now in `Modding Resources/backups/`), so almost every named DLL backup is mid-stack and restoring it
destroys later features. In MP, both peers need the patched binaries. Units cast from the **player's**
researched spellbook (so the player must have researched castable spells to test).

### ⚠ AbilTypes relocation — ✅ CONFIRMED WORKING 2026-09-02 (crash fix, prerequisite)

`build_scripts/build_abiltypes_relocate.py` · `AoWTCPCK.dpl` · backup `.pre-abiltypes` · surgical `--undo`.

**Fixed a live crash**: `Error during TCAI Create Unit List` in any tactical battle where a unit
carried an enabled ability id **170–178** (Magebane … Embrittled). `build_abilityid_ceilings.py` had
raised four `TCAI.EvalBattle` scan loops to `0xB3` while `AoWTC.AbilTypes` was a 170-byte table
guarded by fifteen `bound eax,(0,169)`. The justification for leaving those bounds alone — that only
*selectable* abilities reach them — is true in `CreateTCAbList` and **false in those four scans**.

Table now at **`0x00469440`, 256 entries** (0–169 verbatim, 170–255 = 0); 13 references repointed
(12 displacements + pointer cell `0x4693DC`); all **9** limit pairs `{0,169}` → `{0,255}`. Data-only,
71 bytes, nothing displaced. ⚠ `--undo` **refuses** unless the ceiling loops are lowered first —
reverting alone re-arms the crash.
⭐ **After minting any new ability, set `[0x00469440 + id]` to its category** or it is inert
everywhere — see the rewritten forward hazard in `ID_Ceilings.md`.

### ⭐ Turn Undead — Evil casters command the undead — ✅ CONFIRMED WORKING 2026-09-02

`build_scripts/build_turnundead_evilcommand.py` + `build_turnundead_resroll.py` · `AoWEPACK.dpl` ·
backups `.pre-turnundeadevilcmd` / `.pre-turnundeadresroll` · surgical `--undo` (both).
Full write-up: **`TurnUndead_EvilCommand_Design.md`**.

An **Evil / Pure Evil** caster's Turn Undead seizes the undead instead of damaging and stunning it,
reusing the vanilla `TCommandAbility` machinery so the within-battle revert comes free. Roll chance
is the existing stun roll, with the attacker term swapped to `casterRES × (4+level)/5`.

✅ Fully confirmed in game 2026-09-02, including revert-on-caster-death, strip list, and the
auto-resolve retaliation guard. Ankh overlay also confirmed — needs a `.pfs` record **and** a block in
`TAbstractUnit.ShowEx`'s hard-coded icon chain (`cave_ankh`); the record alone draws nothing.

## Scope decisions

- **Multi-turn channelling for units — ENABLED (2026-07-06).** Originally shelved; re-opened and
  the user chose enable + a "Spellcasting level ≥ spell tier" gate (units **and** heroes) + hiding
  too-high-tier spells from the casting book. Root cause of the freeze: accrual lived only in
  `THero.NewTurn` (fix jumps the unit NewTurn into that body past the hero-only
  `ValidateHeroUpgrade`). **Book filter (M3) CONFIRMED working in-game 2026-07-06**; multi-turn
  completion still worth a spot-check. Full writeup + test/revert in
  `Unit_Spellcasting_Polish_2026-07-06.md`.
- **No mana generation for unit casters — LOCKED** — would break the economy. Phase 3
  (GetPowerGeneration redirect + power-source lifecycle) is **cancelled**. Units draw from the
  *player's* mana pool, throttled by their own points; they must never be mana *sources*.
  ⚠ Still true, and re-asserted on every run of `build_spellcast_manares.py` (which aborts if
  `TUnit`/`TAdjustableUnit` VMT `+0x134` ever leaves the zero stub). But **hero** mana
  generation *did* change on 2026-08-27 — it now scales with Resistance. Do not read this
  bullet as "mana generation is untouched": see `Spellcasting_Mana_Resistance.md`.

## Still open (optional, not done)

- **C2 save-persistence — ✅ CONFIRMED WORKING 2026-07-06.** A unit's casting cluster now serializes
  across save/load via `build_spellcast_persist.py` (backup `AoWEPACK.dpl.pre-persist`): TUnit &
  TAdjustableUnit ReadWrite VMT slots (`+0x18`) redirected to wrappers that call the original then
  append THero's 5 tagged casting fields (property-table format → old-save-safe). See polish doc §7.
- *(nothing else outstanding — mana-gen is LOCKED-off by design; AI-casts-Cosmos is accepted.)*

### Hero mana generation = RES × Spellcasting level — ✅ CONFIRMED WORKING 2026-08-27

A hero's per-turn mana income was a flat table (10/20/40/60/90 for I–V); it is now
**`Spellcasting level × the hero's card Resistance`** (1× multiplier, user ruling). Heroes and the
leader only — `TUnit`/`TAdjustableUnit` VMT `+0x134` still hold the `xor eax,eax; ret` stub, so the
LOCKED unit-side decision above is intact and is asserted on every run.
Doc: `Spellcasting_Mana_Resistance.md`. Script: `build_scripts/build_spellcast_manares.py`
(backup `.pre-spellcastmanares`; **revert with `--undo`**, which restores the *table*, not vanilla).

**No cave and no hook** — a 22-byte in-place rewrite of the 40-byte level→power body at
`0x557885EC`, bounded by `THero.GetCastingPointsMax @0x55788614`, with **exactly one** inbound
reference in the whole file (the `call` at `0x5578B461`) and no `.reloc` entries. It therefore
cannot collide with any cave allocator. Resistance comes from `vtable[+0xCC]`
(`THero.GetResistance @0x5578850C`, shared by `THero` and `TLeader`, clamped [0,40], returned in AL),
so income moves with **morale and RES items**. `AoWEPACK.dpl` only — no exe lockstep edit exists,
because the exe reads the magic window through `GetPower`/`GetManaIncome` and calls `Power()`
dynamically.

⭐ **The 10/20/40/60/90 table was an orphan**: vanilla computed `level*5 + 5` inline, and a
pre-convention Ziggurat patch replaced it — no script under `build_scripts/` owned either address
until now. Found by a live-vs-pristine byte-diff *before* patching; without it, `--undo` would have
restored the wrong bytes. Data side: `Release/Ability.pfs` record 62 and two
`build_ziggurat_manual.py` `MISC_OVERRIDES` rows were corrected the same day (the shipped ability
text had claimed "5/15/30/50/75 mana generation", wrong even before this change).

### Caster cost abilities — ✅ CONFIRMED WORKING 2026-08-27

**Evoker `0xAC` / Conjurer `0xAD` / Enchanter `0xAE` / Ritualist `0xAF`** — each halves the initial
casting cost of one spell family (combat / summons / unit enchantments / global enchantments).
Doc: `Caster_Cost_Abilities.md`. Spec: `Caster_Cost_Abilities_SPEC.md`.
Script: `build_scripts/build_caster_cost.py` (backup `.pre-castercost`; **revert with `--undo`**,
which now refuses without `--force` because the `Ability.pfs` records exist).

Six sites, five caves, **reservation `0x55820800..0x55820FFF`** (423 B of 2048): `CastingMana` entry
`0x557894EC` (classify + halve), its epilogue `0x55789510` (floor of 1 — a floor set in the prologue
does not survive, mastery rescales EBX after it), the registration splice `0x557BCF04`, plus the
three wallet-fix sites `0x557EFA7C` / `0x557E44F8` / `0x557E4353`.

**Membership is by CLASS, not by spell** — the cave compares `[VMT+0x6C] − [VMT+0x18]` against four
per-family constants (the difference is rebase-invariant, so no PIC anchor is needed). Combat needs
a second test because its constant is shared with the abstract `TSpell`. 73 of 108 spells are
covered; the other 35 (storms, terrain, city, hero, target spells) get no discount. **Deliberately
not tunable per-spell** — the user declined an id-lookup table on 2026-08-27.

⚠ **The wallet fix repairs a VANILLA bug** — instantly-cast summons and global enchantments re-read
the raw `[spell+0x14]`, so sphere-Mastery's ×2 never reached them either (`GetSphereManaDoubled` has
exactly one caller). See [[aow1-vanilla-instantcast-rawcost-bug]] for the general lesson.

⚠ **Live level-up costs are 20 / 40 / 30 / 30**, not the 20/40/40/40 in the cave — `Ability.pfs`
tag 6 overrides the cave immediate once a record exists. Change it in AoWDevEd, not in the script.
Tag 5 descriptions are still empty on all four.

QA (adversarial, 5 verifiers + adjudicator): PASS-WITH-NOTES, no defect in the installed bytes.
Two live rough edges recorded in the doc: the **Water Mastery** 3-point tripwire and the
**Cosmagic Scrying** level-1 silent band.
⚠ **Those four ids are contended** — `Facing_Mechanics_Feasibility_2026-08-25.md` also proposes
`0xAC` (for *Shield*). Five proposed abilities, four free ids: re-measure with `check_id_free`
before building either, and re-number the loser. Neither doc's id is reserved.

### ⭐ Facing re-timing + Shield — **BOTH CONFIRMED WORKING 2026-08-27**

`Shield_And_Retaliation_Facing_Spec_2026-08-26.md` (design) +
`Facing_Shield_Handover_2026-08-27.md` (what was written, undo commands, in-game checklist).
⭐ **`build_facing_retal.py` was CONFIRMED WORKING IN-GAME by the user (2026-08-27)** — melee
victims no longer spin when hit, they turn just before retaliating, touch victims no longer spin.
**It was then reverted the same day by choice, not because of a defect**, when Shield moved to
ranged-only. The script is kept as a working, re-appliable technical option (`--apply` brings it
back; `--parts a|b|c` for one part at a time). `AoWTCPCK.dpl` is back to its pre-facingretal bytes.

⭐ **Shield — CONFIRMED WORKING IN-GAME 2026-08-27**, including that **front and front-left are
the only protected directions**. Applied to `AoWEPACK.dpl`; **RANGED ATTACKS ONLY** (vanilla
**Parry `0x71`** already covers melee DEF — live magnitude **−8** — so a melee Shield is redundant).
Id `0xB0`, mask `0x3FF`, **−5** attack (≡ +5 DEF = −25 pp). **Manual** fires on the geometric arc
`(D−F) mod 6 ∈ {0,5}`; **auto-resolve** has no facing so it fires at a flat **75% per shot**
(`RandInt(4) < 3`) — that arm is **still statistically untested**. Revert: `build_shield.py --undo`.

⭐ The confirmation settles **HN handedness end to end** (map maths + pixel bearings + what the
player sees). Ranged-only is **structural**: melee builds its action through `CreateStrikeCA` and
never reaches the code.

⚠ One byte in each exe at `0x21DE40` puts Shield in the **Melee** level-up column — chosen while
it was a melee ability, so it may now be the wrong column. No `--undo`: edit `herodlg_cats.py` and
re-run `build_herodlg_columns.py --apply`.

⭐ **Emergent interaction to judge on purpose:** with S1 reverted, vanilla re-faces a melee victim
towards its attacker, so **engaging a unit in melee rotates its shield arc** relative to your
archers. Re-applying S1 would remove that lever. The facing
work above, cut by the user 2026-08-26 to exactly two items. **S1**: a unit no longer turns when
hit — it turns to face its attacker only just before a *retaliation* strike. **S2**: new ability
**Shield**, +4 DEF against attacks from the defender's front and front-**left** hexes (2 of 6).

⭐ **AoW1 melee has an explicit retaliation step** — `TMeleeRound` builds one interleaved strike
array (stride `0x14`, base `round+0x0C`) with a side byte at `+0x0C` (0 = attacker, 1 = defender),
written at `0x55767B8F`. So S1 maps onto something real: remove `0x004092B9` (3 bytes) and hook
`0x00409BB3`, the head of `ExecuteStrike`'s `side != 0` arm.

⭐ **`+4 DEF` ≡ `−4 ATK` bit-for-bit** — the roll only sees `d = attack − defence`, formed by one
unclamped `sub eax,edx` at `0x55726A2C`. Vanilla's Parry (`0x71`) already works this way. On the
live 5 pp slope, +4 DEF = **−20 percentage points** of hit chance.

⭐ **HN handedness PROVEN** (three legs: `HNtoXYTable @0x5562E024`, `HXtoHP @0x5560E3B4` pixel
bearings 0/63/117/180/243/297°, and `GetMeleeDirIndex @0x00430C58`): **HN 1..6 is clockwise from
North**. Arc = `(D−F) mod 6 ∈ {0,5}`.

⚠ **`dHXtoHNfast` is a sign-of-dx/dy quadrant classifier — 29.5 % wrong beyond adjacency.** For
ranged, use `dHXtoRad` + `dHXtoHN` + inline ring decomposition; validated 60/60 against the
engine's own `BreathDir` table.

⚠ **Three stale cave-space facts corrected**: `0x55822000` is OCCUPIED; `0x5580E440` is claimed by
`build_combatlog_dll.py` (`LEGACY_CAVE`, whose `--vacate` zeroes `0x5580E440`–`0x5580ED80`) and by
`build_invis_penalty.py` (`RNG_LIMIT`). Use `0x55822A00` (AoWEPACK) and `0x00438200` (AoWTCPCK).

⚠ **The "only four free ability ids" claim above is a misreading** of the Caster doc's four-ability
*recommendation*. There are **34 contiguous free ids `0xAC`–`0xCD`** plus 21 gaps. Shield takes
`0xB0`, so it does **not** contend with the caster abilities after all.

⭐ **Decisions taken 2026-08-26**: arc = front + front-**left** `{0,5}`; **+4**; hero-buyable
(mask `0x03FF`, so add `0xB0` to `herodlg_cats.py`); **ranged included** with the exact primitive;
and the arc is evaluated **once per strike**. ⚠ That last one **supersedes the spec's melee hook**
— the melee3 tail `0x55812A2E` runs once per round and cannot express it; the melee link must move
inside `TMeleeRound.CreateStrikeCA @0x55767E68`, **a site not yet characterised**. The cave must
also read the strike's side byte (`+0x0C`) because attacker and defender swap on a retaliation.

⚠ Shield does nothing in **auto-resolve** — `TFastCombatUnit` (instsize `0x64`) has no hex and no
facing, and its `+0x60` is NOT an HS. The mandatory instance-size class guard excludes it.

### Facing mechanics — feasibility done, nothing built

**Unit facing / turn costs / rear-attack bonus / Shield** — see
`Facing_Mechanics_Feasibility_2026-08-25.md` (**SPECULATIVE, nothing applied**). Headline: AoW1 is
**already a six-facing game** — `TUnitHS+0x14` holds a direction 1..6, is serialised as property
id 9 by `TUnitHS.ReadWrite @0x55783ED4`, is written from 40+ sites, is rendered from six real
sprite sets (`TArmyHS.Show @0x557914D8` indexes `Items[dir-1]` idle / `Items[dir+5]` walking), and
`AoWDevEd.exe` already ships a hexagon of `Dir1..Dir6` radio buttons. ⚠ **SCOPED TACTICAL-COMBAT-ONLY by the user 2026-08-26** — the strategic map is
explicitly out of scope, which deletes the largest cost in that doc (no new `TUnit` field, no
strategic MP three-surface coupling, no predictor-cave work, no strategic hotkey). Per-unit facing
in battle **already exists**: `TTacticalCombatUnitHS` is one object per unit, each with its own
`TUnitHS+0x14`. Verdicts under the narrowed scope: facing **already there**; rear-attack bonus and
Shield **feasible**; tactical turn costs **feasible with caveats** — the surcharge goes on the
finished path via one VMT slot (`0x00412AC8`), but `CalculatePathEx @0x557460B0` still cannot
*route* with facing, so costs are exact and the chosen route is occasionally not the cheapest.

⚠ **Blocking precondition for any melee rear bonus:** vanilla spins the defender to face its
attacker *before* the strike resolves — `SetDirection` at `0x004092E0` and `0x0040931B` in
`CombatTE.TCMeleeMoveTE.LastMove`. Under vanilla rules every melee blow is frontal by
construction. Ranged is unaffected.

⚠ That doc also carries a **byte-confirmed pre-existing defect** on the strike sites this feature
would extend: the alignment bonus is `2` at **both** melee sites in pristine
`AoWEPACK_original_backup.dpl`, but the live install has **4** at melee1 (`0x5576665D`,
`0x55766699`) and **5** at melee3 (`0x55767C55`). Under the DAM/HP doubling 2→4 is correct, so
melee3 is one too high — the same alignment bonus is worth 4 down one melee path and 5 down the
other. Verified 2026-08-25 by byte-diff at file offsets `0x065A55`/`0x065A91`/`0x06704D`.
Independent of the facing work; see §7 item 11 of that doc.

---

## The detailed docs

| Doc | Covers |
|---|---|
| `Unit_Spellcasting_Feasibility_2026-07-05.md` | Why it's feasible via file patches (no DLL); the architecture map, the ~8 `is THero` gates, storage-via-instance-growth insight. |
| `Unit_Spellcasting_Implementation_2026-07-05.md` | The **functional** patches in full: instance growth (D1/D2), VMT casting-point redirects (D3–D5), the NewTurn refill cave (C1), and every combat/strategic/TCPCK gate. Phasing + test plan. |
| `Unit_Card_CastingPoints_Display_2026-07-06.md` | The **UI** card display: the working cave, the *failed* approaches with reasons (incl. the gate that **crashes**), and the visibility gotcha. |
| `Unit_Spellcasting_Polish_2026-07-06.md` | **Polish RE:** detecting ability level (`GetAbilityLevel`, VMT +0x144) & spell tier (`TSpell+0x21`); the "level ≥ tier" rule + injection point; multi-turn channelling root-cause (NewTurn accrual missing) + fix + the `ValidateHeroUpgrade` landmine. |
| `Adding_New_Spells_Abilities_2026-07-05.md` | Separate but related: how hard it is to add brand-new spells/abilities (registry flyweights, fixed IDs, DLL vs caves). |
| `RNG_Lockstep_Rule.md` | **Read before adding any roll to any cave.** AoW1 has two generators and picking the wrong one is silent — perfect in single player, divergent between peers. SYNCED is `TAoWHSMap.Random @0x5577827C` (draws from the replicated `map[+0x230]` and writes it back; also the value the out-of-sync comparator reads); RAW is `System.@RandInt` via thunk `0x55701080` (per-process `System.RandSeed`). **Rule: match the generator the function you inject into already uses** — `re_tools/rng_audit.py --functions` prints that for every function in the pristine DLL, so never reason it out. ⚠ Inside tactical combat RAW is *correct* and SYNCED is *wrong* (`TCombat.Execute @0x557282C8` re-anchors `System.RandSeed` from one synced draw, then the whole fight runs off raw draws). ⚠ Setting bit 3 of `[*0x558FA040+0x3C]` to silence the "Invalid AoWHSMap.Random use" modal **converts the draw to a raw one** — it silences the diagnostic, not the bug. Holds the audit of all 25 modded RNG sites: 3 were wrong (Raise Terrain lava, Ice Storm, Fire Storm — fixed by `build_rng_lockstep.py`, **applied 2026-08-31, untested**), 4 raw ones are correct and must not be "fixed". |
| `Facing_Mechanics_Feasibility_2026-08-25.md` | **SPECULATIVE.** Unit facing, MP cost for turning, rear-attack damage bonus, frontal-block *Shield* ability. Holds the facing byte + its 40 writers, the HSEPack hex-direction library (`dHXtoHNfast @0x5560E338` and friends, thunked into both packages), the strategic vs tactical MP charge rules (`min(unitOwnCost, pathByte)` vs unclamped), the three strike-site chains and their **current tail order**, and why the pathfinder cannot represent a turn cost. ⚠ Contends with the caster abilities for ability id `0xAC`. |
| `Shield_And_Retaliation_Facing_Spec_2026-08-26.md` | **APPLIED 2026-08-27, UNTESTED.** S1 deferred-retaliation facing + S2 the Shield ability. Holds the melee exchange in execution order with VAs, the retaliation side-byte, the proven HN handedness, the exact ranged sector formula, the three chain tails and their register contracts, the instance-size class guard, and corrected cave-space addresses. |
| `Facing_Shield_Handover_2026-08-27.md` | What was actually written to each binary, the surgical `--undo` commands, the 17-step in-game test checklist with failure diagnoses, the outstanding AoWDevEd round-trip, and the gaps QA could not check. |
| `Investigation_Items.md` §3.11 + `build_scripts/build_useitems.py` | **Use items, fully functional — APPLIED 2026-08-02, UNTESTED.** `itUse` backpack items now grant the four stat bytes, immunities/protections/move types, and working passive abilities; Healing `0x2F` and Dispel Magic `0x3C` no longer infinitely usable from an item. 13 sites in `AoWEPACK.dpl` + cave `0x55815000` (backup `.pre-useitems`, now **layer 50**), 1 byte in each editor. **Revert with `--undo`, never the backup.** ⚠ P2 edits sit inside `GetAttackRA`, which already carries `cave_5580C240` — they compose, don't revert to "restore" it. |
| `Investigation_Items.md` FEATURE 2 + `build_scripts/build_item_hpmv.py` + `build_item_hpmv_data.py` | **Items grant +HP / +MV — APPLIED 2026-08-31, UNTESTED.** 3 hooks + 5 caves in `AoWEPACK.dpl` (cave span `0x5582B000..0x5582B200`, backup `.pre-itemhpmv`, surgical `--undo`); storage `item+0x4A`/`+0x4B` signed; persistence tags `0x17`/`0x18`; 32 items authored in **`User/Zig.ail`** (the live library — NOT `ITEMS.PFS`). Reaches strategic, tactical and auto-resolve from the one DLL pair. ⚠ `TItem.ReadWrite`'s tail is unhookable (`mov ebx,[eax]` @`0x55794726` clobbers the item pointer on one of two paths) — hook `0x55794712`. ⭐ A record directory cannot be re-derived, only appended to. Original scoping notes: **~95%.** Targets `THero.GetHits@0x5578859c` (VMT +0xD0) and `GetMoves@0x557885c0` (VMT +0xD4) — both still vanilla-shaped, shared by `THero` and `TLeader`, 0 relocs in the hook footprints; storage `item+0x4a`/`+0x4b` (free, no instance growth); persistence tags `0x17`/`0x18`. Reaches strategic, tactical **and** auto-resolve for free. Clone `build_useitems.py`'s aggregator cave at `0x55815080`. ⚠⚠ **`add dl,[eax+0x6d]` is an 8-bit add and `base + hero+0x6d` hits the ceiling exactly — at the 2026-08-31 ceiling of 100 an item bonus ≥ 28 wraps and the hero drops to 2 HP (at the old 120 it took only ≥ 8). Do the sum in 32-bit and re-enter vanilla at `0x557885A7` so `build_hero_clamps.py` keeps the clamp immediates.** |
| `Investigation_Items.md` | **Read §0.6 before hooking ANY ability consumer.** `THero` has **two parallel ability-query APIs** and only the high-slot one sees items: `+0x4c/+0x84/+0x88` (`GetAbSet`/`GetAbLevel`/`GetAbEnabled`) are **self-only**; `+0x14c/+0x144/+0x148/+0x158` (`GetAbilitySet`/`GetAbilityLevel`/`GetAbilityEnabled`/`GetAbilityCount`) resolve self→equipped→`itUse` inventory. Relevant here because the spellcasting mod's own tier gate reads Spellcasting `0x34` through **VMT +0x144** (item-aware) while `UnitSpells.TDispelMagic.GetDispelMana` reads it via **+0x84** (self-only) — so an item-granted Spellcasting level strengthens casting points but **not** Dispel. ⚠ That first clause was ASPIRATIONAL until 2026-08-28: `cave_tiergate` v1 reached the +0x144 *implementation* by a **static call to the base** `TAbstractUnit.GetAbilityLevel @0x5577F658`, which bypasses `THero`'s override `@0x5578831C` and so saw no items at all. Every item-granted caster failed the tier compare and, because the fail arm returns with no message, the spellbook opened and clicking a spell did nothing. Fixed by dispatching through the slot; see §3.3c of `Investigation_Items.md`. Also holds the item stat/ability routes, the equipped-vs-use-slot capability matrix, and the Marksmanship / Healing item defects. |
| `City_Flag_Bauble_Lag.md` | **✅ CONFIRMED WORKING 2026-08-29** — `build_cityflag.py`, `AoWEPACK.dpl`, cave `0x55819000`, backup `.pre-cityflag`, surgical `--undo`. Vanilla bug: the flagpole bauble count is a **cached** byte `TCity+0x54` (`bits 6-7 = upgradeLevel-1`) whose only producer is `TCity.UpdateFlagID @0x557AC8B0`, and the two paths that change the level — upgrade-completes (`TCityProductionControl.NewTurn` case 2 @`0x557A8346`) and rebuild-after-raze (`TCity.BuildingDone @0x557A97D8`) — never call it. Intermittent because `+0x54` is not saved, so map load rebuilds it. ⭐ Holds the **wrapper-thunk-on-an-existing-`call rel32`** idiom: retarget a call's rel32 instead of writing an `E9` hook — 4 bytes in the host function, nothing displaced, no resume hazard, PIC for free, trivial `--undo`. |
| `ResStr_Dictionary_Names.md` | **✅ CONFIRMED WORKING 2026-08-29** — `build_resstr_names.py`, `Dict/ResStr.mld` + `.txt`, backups `.pre-resstrnames`, surgical `--undo`. ⚠ **A spell's/ability's NAME is not in the `.pfs`** — only the description is (`Spells.pfs` tag `0x0A`, `Ability.pfs` tag 5, via `build_pfs_typos.py`). Names are DLL resourcestrings, but you never patch those: `TranslateRStr` routes every one through `Dict/ResStr.mld`, keyed on the native English string, and Ziggurat's 16 existing `[US]` overrides (Fireball→Triple Fireball, Summon Mermaid→Craft Aether Barge, …) are that mechanism. Holds the Multilizer v3 layout (no index, no checksum, one `info_offset` fix-up), the CRLF trap, and the fact that `mld_conv.exe` is a GUI that hangs a shell. First row: Summon Fire Sprite → **Summon Fire Sprites**. |
| `Fire_Heals_FireUnits_Design.md` | **✅ CONFIRMED WORKING** — v1 2026-07-07 (fire heals Fire Elemental 226 / Fire Sprite 228, `+N` popup); **v2 2026-08-29: the heal no longer takes a to-hit roll.** `build_firefeed.py`, `AoWEPACK.dpl` caves `0x5580DA20/DA80/DAD0`. ⭐ The trap it earned: **reusing an engine damage path for a non-damage purpose silently imports its to-hit roll and its stat dependency** — v1 "faithfully replicated the non-immune branch" and so healed *nothing* 20 % of the time, scaling off the recipient's **Defence** (`vmt+0xC4`, not Resistance — an earlier doc revision had that wrong). v2 discards the strength term, passes a fixed no-miss margin and clamps the flat fumble to 1; heal is now 1..6, mean 3.40, identical for both units. ⚠ The cave run is **padded to its old length** because `CAVE_B`/`CAVE_C` are derived from `len(caveA)` — shrinking it would silently relocate the two later caves. Revert = flip `HEAL_TAKES_TOHIT_ROLL` and re-run (both bodies are accepted pre-states; no backup involved). |
| `Panic_No_Offensive_Melee.md` | **APPLIED 2026-08-31, UNTESTED.** Panicked units (`0x6C`) cannot *initiate* melee but still retaliate. `build_panic_nomelee.py`, 5 hooks + 5 caves (`AoWTCPCK.dpl` `0x00438300`, `AoWEPACK.dpl` `0x55828000`), backups `.pre-panicnomelee`, surgical `--undo`. ⭐ Built by copying vanilla's **flying rule**: `TMeleeRound.Calculate @0x55767D24` has **no** flying test, so the rule lives entirely in the four "may I initiate?" gates and retaliation survives for free — the same is now true of panic. Holds all six vanilla flying sites (⚠ **two different rules**: one-way "target flies, attacker doesn't" vs two-way "same altitude" for free swings/ZOC), the single tactical-melee chokepoint `MeleeMoveTC @0x00422CD8` and its two callers, and the register maps of `CanExecuteMelee` / `TTouchAbility.CanTouch` (mirror images — `ESI`/`EDI` swap roles). ⚠ **Trap: do NOT add `0x6C` to `TCombatUnit.GetLocked`** — it is consulted for both sides, so it kills retaliation too. |
| `Terror_OncePerCombat.md` | **APPLIED 2026-08-31 (v2, per-side), UNTESTED.** Each *side* casts Terror at most once per battle. `build_terror_oncepercombat.py`, `AoWEPACK.dpl`, caves `0x5582A000`+, flag array `0x558FAC00..03`, backup `.pre-terroronce`, surgical `--undo`. Holds the **two combat contexts** map — tactical value = VMT `+0x88` `TTerror.tcGetDamageValueEx`, driver picks the single highest-priority action (so ÷64 caps it); fast value = `TTerror.fcPrefetchCombatCommands` inline, driver drops a command **only at value exactly 0** (so ÷64 caps nothing). ⭐⚠ **`TTerror.fcGetDamageValueEx` (VMT `+0x98`) is DEAD** — 0 direct refs, 1 dword ref (its own slot); a gate there assembles, verifies and does nothing. *An override is not evidence the method is on the path.* ⭐ **Combat sides: there is no `GetSide`** — `TCombatObject.GetOpponentSide @0x55726688` reads `[player+0x0A]` and XORs 1, so sides are exactly {0,1} with `2` for an object whose `[obj+0x45]` player slot is `0xFF`; ⚠ it returns in **AL only** (upper EAX is the incoming pointer on the escape path) and preserves EBX/ESI/EDI/EBP. ⚠ Terror's VMT base is `0x557F61D4` (export table `..TTerror`) — slot arithmetic from an assumed base renames every slot. ⚠ A displaced run containing a `call rel32` must be **re-assembled** in the cave, never copied verbatim. ⚠ Prior-art flag/cave addresses (`0x558FAF20-22`, `0x5580DCE8/DD14/DD34`) all collide with live features — re-pick, never copy. |
| `Embrittlement_Spell.md` | **APPLIED 2026-09-01 — mechanics + icon + `Spells.pfs` record 119; UNTESTED IN PLAY (the game launches). v1 BROKE STARTUP, fixed same day.** Three scripts: `build_embrittle.py` (7 hooks + cave zone `0x5582D000`), `build_embrittle_icon.py` (a broken-bone stamp written over DEAD SpellIcn.ILB entry 128 — three exact-size writes, no directory surgery; ⚠ the frame's `transparent` must move `0x0000`→`0x4148` or the Earth disc gets 113 holes), `build_embrittle_pfs.py` (record 119 CLONED from Slow's 120 — a splice, not a directory rebuild, because index offsets are relative to the end of the directory; ids and offsets must stay co-sorted; CRC residue `0x2144DF1C`). Free spell ids now **79–99**. ⭐ **Naming: vanilla INFLECTS the status** — `TBlessedEnchantment` loads `BlessedRStr` (spell *Bless*), and `0x28`/`0x5E` ship as *Entangle*/*Entangled*; so the spell is the imperative verb and the status the past participle. ⚠ `ability_names.py`'s "… Enchantment" names are class-derived artefacts of its ctor scan, NOT in-game names — never cite them as convention. ⚠⚠ v1 handed `System.@LStrAsg` the name literal's **header** address instead of header**+8**; a Delphi AnsiString points at the first character (refcount at `ptr-8`), so LStrAsg refcounted the zero padding before the cave and wrote into the **read-only CODE section during DLL init** ⇒ **`Runtime error 216 at 00003924`** on launch. `build_reformingflesh.py:435` carries the `+8` with a comment; it was not carried across. ⚠ **216 = GPF, 217 = duplicate ability id** — don't confuse them. ⭐⭐ **Byte-verify, `.reloc` scan, PIC audit, byte-identical `--undo` round-trip, `rng_audit` and the leak scan were ALL GREEN on a build that could not start the game — a cave that runs at package init must be proved by LAUNCHING THE EXE, as a build-time check, not an in-game test handed to the user.** New tactical combat spell **Embrittle** (id 109, Earth, tier 3, 14 mana, Resistance-opposed) applying new passive **Embrittled** (`0xB2`): the unit takes **DOUBLE** physical damage for the rest of the battle — the mirror of Physical Protection, and it **cancels exactly** against it. `build_embrittle.py`, `AoWEPACK.dpl` 7 hooks + cave zone `0x5582D000..0x5582D300`, `AoWTCPCK.dpl` one byte (`SpellTypes[109] = 0x07`), backups `.pre-embrittle`, surgical `--undo` (round-tripped byte-identical). ⭐ **The whole trick: when a vanilla class already carries everything and only a constant differs, clone the INSTANCE and make the constant a function of state the code already holds.** Embrittlement *is* a `TSlow` and emits genuine `TSlowCA`s — so a "Tier-3 new archetype" needing `RegisterEClasses` collapsed into four small caves with **no new class and no new save/network ClassID**. Holds the single damage chokepoint `TCombatObject.ExecuteDamageRole @0x557269F0` / `...Ex @0x55726A6C` (VMT `+0x110`/`+0x114`, unoverridden, so one patch reaches manual + auto-resolve + strategic), the damage-type bit order and its two defining functions, and the free wall type-gate. ⚠ **Double BEFORE the vanilla halve** or the cancellation is off by one. ⚠ **The `ExecuteDamage` assert bound is 126, not vanilla's 49** — Ziggurat raised it in the DAM/HP pass. ⚠ **Not `CreateEnhancementAbility`** — the CA calls `+0x54`/`+0x58` on `[abilityData+0x10]`, which only a `TUnitEnchantmentAbility` data class has; instantiate `TSlowEnchantmentAbility` and poke `[+0x0C]`. ⚠ **Manual tactical combat has NO damage-based target gate** (`TSlow` returns an all-zero damage struct and is still castable) — the vanilla idiom for a restricted target is TurnUndead's **CreateCA fizzle**, which is what the Physical Immunity refusal uses; the cast is still spent. ⚠ Registering `0xB2` forced **both** ability-id ladders to `0xB3` (`build_abilityid_ceilings.py`, `build_tcablist_ceiling.py`) and an entry in `re_tools/ability_names.py` `MODDED` — omit either and the ability works but is invisible to the tactical AI and the hover popups. ⚠ No `Spells.pfs` record 119 yet, so no description/icon: **whether the spellbook renders an empty image list safely is the first in-game check.** |
| `Leadership_FourLevels_And_Fix.md` | **Leadership I–IV — ✅ CONFIRMED WORKING 2026-07-20; curve re-tuned 2026-08-20 and the re-tune CONFIRMED 2026-08-24.** `build_leadership4.py`, `AoWEPACK.dpl`, caves `0x5580EFC0` (costs) + `0x5580F000` (`GetLevelName`) + data `0x5580F0C0`. ⚠ **No `--undo` yet** — reverting means restoring five hook sites and zeroing three cave zones by hand; re-tuning is done **in place** instead (below), which is why this has never bitten. Copy the shape from `build_leadership_fix.py` if a rollback is ever needed. Live curve **ATK/DEF +1/+2/+3/+4, 10 skill points per level, flat** — raw table values, because Leadership is a **D2 exception deliberately NOT doubled** by `build_statdouble.py`, so this table is the only place its strength is set; one point buys 5 pp, putting level IV back at vanilla's effective +20 pp. Three vanilla pins lifted: the ctor sets cap 4 then **stomps it to 1** @`0x55766187`; only `cost[1]=20` was ever defined; `GetLevelName @0x557663D0` **ignores its level argument**. ⭐ **The reusable trick: an existing absolute operand that already carries a `.reloc` entry can be repointed anywhere in the image and stays rebase-correct** — both bonus tables were relocated into the cave by changing only the *value* of the disp32 (`0x55766207` / `0x5576621B`), never removing the relocation. ⚠ **Vanilla packs the two tables 4 bytes apart** (`0x558E83E7` / `0x558E83EB`), so `attack[4]` reads `defense[0]` — and the bytes just past each vanilla table are `02` and `01`, so a naive cap-raise with no table change would have read `+2/+1` at level IV **purely by adjacency**: correct-looking and entirely accidental. ⭐ `cave_lsname` calls the *original* `GetLevelName` into a stack temp (so resource loading + SEH stay in vanilla code) then `LStrCat3`s Marksmanship/Vision's own constant literals `" I"` / `" II"` / `" III"` / `" IV"` (`0x557BBF18/24/30/40`, refcount −1) rather than fabricating Delphi strings; since `TMultiLevelAbility.GetName` and `ExpandName` both funnel through `GetLevelName`, that one fix feeds the unit card **and** the hero level-up dialog for free. ⚠ **Re-tune in place** — set `COST_EACH` / `ATK_BONUS` / `DEF_BONUS` and re-run with `--apply`; the free-space guard identifies the 16-byte suffix-VA block at `DATA_TAB+0x10` as this script's own signature and rewrites the curve bytes in front of it (`[~ ] re-tuning in place`). **Never revert-and-re-apply.** ⚠ The curve deliberately re-balances level 1 *downward* — vanilla's +2/+1 is now level **III**, so pre-existing level-1 leaders (hero chassis, medal units) got weaker. |
| `Leadership_Disable_Bug_RootCause.md` | **Leadership “permanently disabled” bug — ✅ FIXED, CONFIRMED WORKING 2026-07-20.** `build_leadership_fix.py`, `AoWEPACK.dpl`, cave `0x5580F100`, hooks `0x5574F54D` + `0x5574F55B` (8-byte `mov ecx,[eax]; call [ecx+0x84]` → `call cave` + 3 nop). **Surgical `--undo` added 2026-09-02** — restores both 8-byte call sites, zeroes `cave_abinherent`, verifies before writing, aborts on foreign bytes, no-ops when already vanilla, touches no backup; round-tripped byte-identical (sha256). ⚠ The `.pre-leadershipfix` snapshot is **gone** (the whole `backups/` directory was deleted 2026-08-08) and was never a safe revert path. The vanilla bug: a unit that earns Leadership **while standing in another leader's aura** never receives its own inherent record, and when the aura later goes away the aura GC deletes the borrowed record *and clears the ability bit* — the legitimately earned Leadership is gone permanently, and separating the unit does not bring it back. **Two defects combine, neither harmful alone:** (A) `UpdateDefaultAbilities` compares **effective** levels (own ∪ borrowed), so an active aura makes the recipient look like it already has Leadership and the real grant is skipped; (B) `TLeadershipAbility.ResetExternalSource` uses **`own level == 0`** as its “this record is aura-borrowed, delete it” test, and a masked unit's record is own-level 0. The fix routes (A) through `GetInherentLevel` (**ability VMT `+0x94`**, vs `+0x70 GetLevel`) via `TAbilityControl.GetAbility @0x557501C0` off the `AoWHSSet` registry (`0x558FA044`, registry at `+0x80`). ⭐ **Holds the two-store ability model** — the enabled **bitset** (`GetAbilitySet @0x5577F618` VMT `+0x14c`, `GetAbSet` VMT `+0x4c`) and the ability-**data record** list (`GetAbilityData @0x5574F1C4`, head `owner+0x10`, next `data+0x8`) are independent and can disagree; the level accessors read **only the record** (`GetAbilityLevel @0x5577F658` VMT `+0x144` — no record ⇒ level 0), while `GetAbilityEnabled @0x5577F5E0` VMT `+0x148` reads the bitset **and** the record. `TLeadershipAbilityData`: `+0x0c` own level, `+0x0e` id (word), `+0x10` borrowed level, `+0x14` source name. ⚠ That missing own-vs-borrowed discriminator is exactly why `Leadership4_Grants_Fearless.md` refuses to grant the Fearless *bit*. |
| `Leadership_FourLevels_And_Fix.md` §8 | **Aura instant-refresh — APPLIED 2026-07-20, UNTESTED.** `build_leadership_aura.py`, `AoWEPACK.dpl`, cave `0x5580F140`. **Surgical `--undo` added 2026-09-02** — repoints the hooked call back at `TAbilityOwner.UpdateDefaultAbilities`, zeroes `cave_auraup`, same guarantees as the fix script's; round-tripped byte-identical. ⚠ `.pre-leadershipaura` is **gone** with the rest of the backup stack. Distinct from the disable bug: after buying a Leadership level in the hero level-up UI, party units don't get the new aura bonus until the army next updates — a move, or next turn. The level applies immediately; only the *aura* is stale. Fix: the `call TAbilityOwner.UpdateDefaultAbilities` @`0x557854E0` at the tail of `THeroUpgradeTE.Execute @0x55785450` is repointed to a cave that runs the original and then `army = [hero+0x4]; if army && IsClass(army, TArmy): TArmy.UpdateFormation(army)` — `UpdateFormation @0x5578D034` being the engine's **sole** aura recomputer, so behaviour is identical to a move, just immediate. The `IsClass(TArmy)` guard is *vanilla's own* idiom (`TAbstractUnit.MovedTo+0xce`, `UpdateMoraleValue+0x5f`); the classref global is `0x557130AC` → VMT `0x557130EC` “TArmy”; the following `mov byte [edi+0x54],0` @`0x557854E5` is asserted at build time to pin the function version. **MP-safe** — `THeroUpgradeTE` is a network-distributed token event executing on every peer and `UpdateFormation` is deterministic (no RNG). ⚠⚠ **Never trust a cave address from another modder's build.** The idea and first implementation are a fellow modder's (`patch_leadership_aura_refresh_v1.py`), and it used `0x5580E120` — which in our DLL holds live `build_assassin.py` code, so applying it unmodified would have **silently destroyed the slayer feature**. Re-scan for free space in your own binary first. |
| `Leadership4_Grants_Fearless.md` | **Leadership IV makes the whole stack count as Fearless — APPLIED 2026-09-01, UNTESTED.** `build_leadership_fearless.py`, **`AoWEPACK.dpl` only** (Fearless is not queried by `AoW.exe`, `AoWTCPCK.dpl` or `aowInt.dpl`, so there is **no AoW.exe/AoWCompat lockstep half**), cave `C_FEAR` `0x5582C000` (58 B, span asserted zero-or-ours to `0x5582C080`), five 15-byte site patches, threshold `LEAD_LEVEL = 4` tunable at the top of the script, backup `.pre-leadfearless`, surgical `--undo` (round-tripped byte-identical). Ids: Leadership `0x2E`, Fearless `0x43`, Panicked `0x6C`. **Fearless means exactly one thing: “cannot be given the Panicked status”** — a plain bit-only passive registered by `PassiveAb`, no ability class, no data record. Five sites, each the same vanilla 15-byte run (`mov edx,<id>; mov eax,<reg>; mov ecx,[eax]; call [ecx+0xA8]`), all retargeted to the one cave: `TStrikeCA.Generate+0x41 @0x557668F5` (melee Cause Fear), `TFastCombatTerrorCA.Generate+0x5D @0x557F983D` and `TTacticalCombatTerrorCA.Generate+0x29 @0x557F99C1` (Terror, auto-resolve + tactical), plus the two AI target-value tests `TTerror.fcPrefetchCombatCommands @0x557F9B64` and `TTerror.tcGetDamageValueEx @0x557F9D4E` — vanilla checks only Panicked there and never Fearless, so the AI already overvalues Terror against immune targets; routing them through the cave incidentally fixes that pre-existing vanilla case for natively-Fearless units too. ⭐ **Propagation is free — do not build an aura:** `TArmy.UpdateFormation` pass 2 pushes the army's max Leadership onto **every** member with no gate, and `TCombatUnit.SetParty @0x557250D6` re-runs it at combat start, so the borrowed level is live in tactical **and** auto-resolve — scope identical to Leadership's existing ATK/DEF bonus. ⭐⚠ **The cave must call `+0xB8 GetAbilityOwner`, NOT `+0xB0 GetAbilityLevel`** — the single most important byte in the patch. `+0xA8` returns false for **both** “nil `[obj+0x4C]`” and “ability not enabled”, and this cave makes its second query precisely when the first returned **false**, so the `+0xA8` gate that licenses the unguarded `+0xB0` was never discharged; a nil `[combatobj+0x4C]` is normal engine state, so `+0xB0` would be a real intermittent crash. **Generalisable: a nil-guarded accessor returning FALSE does not discharge the guard for its ungated sibling** — reach for the accessor that returns the pointer and test it. ⚠ **The Fearless bit is deliberately never granted** — bit-only means there is no own-level byte, so borrowed cannot be told from inherent and a buggy un-grant would **permanently strip native Fearless from undead and elementals**; the cost is that a stack member's card shows Leadership IV but not Fearless (`ListAbilitiesEx @0x5574E52C` builds the card from the real bitset via `GetAbSet`, so there is no cheap display-only hook). **User ruling 2026-08-31: effect only, no card entry.** ⚠ The strategic-map site `ExecuteLifeMasteryFearRole @0x55780B90` **already** exempts any Leadership holder at every level in vanilla — left alone, patching it would be redundant. ⚠ Expect the immunity to persist for the whole battle even if the Leadership-IV hero dies mid-combat (`UpdateFormation` runs at `SetParty` only) — exactly how vanilla already treats the ATK/DEF bonus. ⚠ `0x5582B200` was the first cave choice and is **wrong**: it is `build_item_hpmv.py`'s `CAVE_END`. A script's declared span extends past its last emitted byte, so grep `build_scripts/` for the address band rather than trusting a zero run. |

---

## Quick reference — key addresses & facts

Preferred-base VAs. **AoWEPACK.dpl** base `0x55700000` (rebased at runtime — file caves must be
position-independent, or reuse a slot that already has a `.reloc` entry). **AoW.exe / AoWCompat.exe**
base `0x400000` (fixed; absolute addresses OK). Ghidra MCP has **AoWEPACK.dpl only**; for
AoW.exe / AoWTCPCK.dpl / aowInt.dpl use `re_tools/` (capstone-based).

**Ability / unit model (AoWEPACK.dpl)**
- Spellcasting ability ID = `0x34`. Level→points table: 1→10, 2→20, 3→40, 4→60, 5→90.
- `TUnit` VMT `0x55710CAC`; instance-size word `0x55710C90` (grown `0x48`→`0x94`).
  `TAdjustableUnit` VMT `0x55712A54`; size word `0x55712A38`. (both grown, both VMT-redirected)
- Casting cluster on a (grown) unit: `+0x7C` power-source ptr, `+0x80` current points (byte),
  `+0x84` spell-in-progress ID, `+0x88` progress, `+0x8C` mana required, `+0x90` eventlog id.
- Unit vtable slots: `+0x128` GetCastingPointsMax, `+0x12C` GetCastingPoints, `+0x130`
  SetCastingPoints, `+0x13C` NewTurn, `+0x144` GetAbilityLevel, `+0x148` GetAbilityEnabled.
- THero impls used as redirect targets: GetCastingPointsMax `0x55788614`, GetCastingPoints
  `0x55788644`, SetCastingPoints `0x5578864C`. TAbstractUnit.NewTurn `0x55780D4C`.
- `cave_iscaster` = `mov ecx,[eax]; mov edx,0x34; jmp [ecx+0x148]` (returns GetAbilityEnabled(0x34)).
  Only safe where the object is known to be a TAbstractUnit.
- AoWEPACK cave region `0x5580D900` (after the move-fix cave). AoWEPACK `@IsClass` thunk `0x557010C0`.
- Gates retargeted → cave_iscaster: G1 CanActivate `0x5576DEB7`, G2 fcPrefetch `0x5576E418`,
  G3 breach-wall `0x5576DF17`, G4 CastingDone `0x557794CD`, G5 CombatCastingDone `0x5577950C`,
  G6 recast `0x5577A25C`, G7 CombatSpell.fcPrefetch `0x557F76EB`. (G6 = the is-THero in
  `TSpellCastEventLog.Execute` @ `0x5577A1C8` — the multi-turn *completion* trigger, so completion
  is already unblocked for units.)

**Polish primitives (see `Unit_Spellcasting_Polish_2026-07-06.md`)**
- Ability level: `TAbstractUnit.GetAbilityLevel(unit, 0x34)` @ `0x5577F658` → 1–5, 0 if absent
  (via `TMultiLevelAbility.GetLevel` @ `0x557651D8`, reads `abilityData+0xc`).
- Spell fields (resolve id via `TSpellControl.GetSpell(*(AoWHSSet+0x84), id)` @ `0x55779AC8`):
  `+0x14` base mana, **`+0x20` sphere (0 = Cosmos)**, **`+0x21` research tier (1–4)**, `+0x22` category (2=global ench).
- Sphere enum via `TLeader.GetSpherePicks` @ `0x5578B17C`: **0=Cosmos** (hard-returns 4 picks =
  "researchable regardless of picks"), 1–6 = elemental pairs. `TLeader : THero` (VMT `0x55712238`,
  the player's wizard; overrides `ClassID` @ `0x5578B0C8`).
- Hero-family test = **`IsClass(caster, THero)`** (true for THero + TLeader, false for units).
  Exe: `mov edx,[0x45DFC4]` (THero classref) + `call 0x401070` (@IsClass). DLL classref `[0x55711FAC]`,
  @IsClass `0x557010C0` (needs call/pop delta in a cave — DLL rebases). `ClassID` vtable slot `+0x24`
  (THero→0x20230, TUnit→0x20213, TLeader overrides — so use IsClass, not exact ClassID).
- "Level ≥ tier" rule → gate at `THero.CanCastSpell` @ `0x55789710` (scope to non-heroes).
- Multi-turn: start `ExecuteStartCasting` @ `0x55789130` (works; mana paid up front). **Accrual
  missing** — lives only in `THero.NewTurn` @ `0x55787FCC` (fix = replicate its casting block into
  `cave_unit_newturn`, MINUS `ValidateHeroUpgrade` @ `0x55787D54`, which is hero-only and crashes
  units). Predicates: `Casting` `0x89598`, `CastingReady` `0x895A4`, `CastingDone` `0x893E8`.

**Tactical combat (AoWTCPCK.dpl)**
- `@IsClass` thunk `0x401058`. Cave `0x438100`. 4 gates `0x418739 / 0x418B86 / 0x418F71 / 0x4195D4`
  (each `cmp ability,0x34` → `is THero` on `combatUnit+0x4C`).

**Unit card (AoW.exe)** — see the card doc for the full story
- Paint fn `0x407DB8` (TUnitWindow). Upkeep `SetGText` hooks `0x40916A` / `0x4091A6` (EBX=unit,
  ESI=&form — the safe hook). Card cave `0x60C000` (new `.sc` PE section).
- Form fields: UpkeepIcon `+0x1D4`, ManaIcon `+0x6C`, UpKeep `+0x1D8`, **Mana `+0x70`** (the CP cell).
- Helpers/thunks: SetGText `0x403254`, IntToStr `0x4013AC`, @LStrCatN `0x401128`, @LStrArrayClr
  `0x4010E0`, `"/"` literal `0x404234`, `@IsClass` `0x401070`. `control.vtable+0x6c` = SetVisible(dl).
- **⚠ Never patch the `is THero` gate at `0x407E43`** — it crashes (object not always a TAbstractUnit;
  its `edi` is entangled with the paint's hero logic).

---

## Tooling

- **Build/patch scripts** (self-contained, in the `build_scripts/` subfolder): `build_spellcast.py`,
  `build_spellcast_tcpck.py`, `build_spellcast_card_v2.py`. Model for new caves: keystone-assembled,
  verify-before-write, backup, idempotent; PE-section-adding logic is in `card_v2`.
- **RE toolkit** (`re_tools/`): `pescan.py` (PE parser), `dfm_parse.py` (Delphi form parser),
  `ftall.py`/`vmt_find.py` (VMT field-table readers), `dump_exe.py` (annotated AoW.exe disassembler),
  + README. Needs `pip install capstone keystone-engine`.
- Related fixes in this folder (different features): `build_patch.py` +
  `MovePredictor_Fix_2026-07-05.md` (movement predictor), `TransportBoarding_VanishBug_Analysis.md`.
- **Vision — nine levels, +1 sight each** (CONFIRMED WORKING 2026-08-09): `sight = 3 + level`,
  levels I..IX, was `3 + 2*level` capped at IV. `build_vision9.py` → **AoWEPACK.dpl** (5 sites +
  1 KB cave block **`0x55817000..0x55817400`, RESERVED — do not allocate inside it**) **+
  `Release/Ability.pfs`** record 74 tag 5. Backups `.pre-vision9` on both; **revert with `--undo`**,
  which is surgical on both files. No exe patch, so no AoWCompat lockstep.
  Doc: `Vision_Nine_Levels.md`. Four things in it are reusable beyond Vision:
  **(1)** `TArmy.UpdateVisibilityRanges` @0x5578E10C packs stack sight into a **nibble pair** at
  `[army+0x29]` with no clamp — **base + cap must stay ≤ 15**, which is why raising the cap and
  cutting the per-level bonus could not ship separately;
  **(2)** the sight radius is computed at **TWO** sites (`0x55780F12` strategic, `0x55724AEE`
  tactical) — patch one and the map disagrees with the battle;
  **(3)** to add level names past a `GetLevelName` jump table, **repoint the VMT slot, never the
  table** — its entries carry `.reloc` and a cave-hosted copy would not;
  **(4)** the **first length-changing `.pfs` write** in this project (record grew 161→236 B, 87
  later index offsets shifted) — ⚠ descriptions are `u32`-length-prefixed, not `u8` Pascal, and a
  backwards tiling of body lengths is **not** an index integrity check (it is circular; the CRC is
  the real gate). `build_drillmaster.py` carried the same idiom and was fixed the same day.
  `re_tools/ability_names.py levels()` now reads every levelled ability's ceiling off the live DLL
  (7 abilities; Vision reports 9) and the Ziggurat Manual follows it.
- **Fire heals Fire units** (CONFIRMED WORKING 2026-07-07 — Firestorm + map fire/Fire Barrier):
  `build_firefeed.py` + `Fire_Heals_FireUnits_Design.md`. Fire (Firestorm + map-hex fire + Fire
  Barrier) HEALS Fire Elemental (226) / Fire Sprite (228); Party-Damage popup shows "+N". Patches
  `AoWEPACK.dpl` (**3 caves**: `cave_fireheal` @0x5580DA20 redirecting `ExecuteDamageRole` @0x55781AC4
  → negated roll; `cave_plusnum` @0x5580DA80 redirecting `ShowDamageIcon`'s IntToStr → "+N";
  `cave_mapfire_gate` @0x5580DAD0 rerouting 226/228 past `TriggerFireDamage`'s fire-immunity gate
  @0x5579020C) **+ `AoW.exe` + `AoWCompat.exe`** (`0x436BFF` and→movsx). Backups `*.pre-firefeed`.
  Other fire-immune units still show "immune"; tactical-combat fire is a separate path (out).
- **Elemental terrain heal** (CONFIRMED WORKING 2026-08-30): elementals heal per hex **entered** on
  their element during strategic movement, own movement only (army-level transport gate, as Path
  abilities) — Water 227 +2 on water/cave water, Air 224 +1 on any surface hex, Earth 225 +1
  underground or on mountain overlay, Fire 226 +4 on lava; Healing chime iff healed + hex visible
  (50% volume Water/Fire, 25% Air/Earth; heal itself never fog-gated — MP determinism).
  `build_waterheal.py` (label "elemheal") → **AoWEPACK.dpl only**: 8-byte hook @0x557803BA in
  `TAbstractUnit.MovedTo` + 344 B PIC cave @0x55824000. Backup `.pre-waterheal`; revert = surgical
  `--undo`; script recognises v1–v4 states and rewrites in place. Doc: `Elemental_Terrain_Heal.md`
  — holds the ⭐ reusable **PlayEx per-call-volume sound ABI** (thunk @0x55702CFC, ECX=0–100),
  ⭐ **mountain = overlay 0 in `[field+0x15]` (0xFF = none), not a terrain**, and the per-hex
  `MovedTo` hook + `WatchingTerrain` presentation-gate idioms.
- **Tier Research** (CONFIRMED WORKING 2026-07-18): research is per **(sphere, tier)** group —
  one entry researches a whole tier; flat cost **100/200/400/800**; day 1 grants **one full
  tier-1 sphere** instead of 3 random spells; the Research Book shows grouped entries
  ("Death I", 3/page balanced across the spread) with every member spell's icon + name, and the
  Currently-Researching / Researched views + event log say the tier, not a spell.
  Docs: `Spell_Research_System_2026-07-18.md` (vanilla decode §1–6, as-built §7, iteration log
  v2→v7.9). Scripts + binaries:
  - `build_tierresearch_dll.py` → **AoWEPACK.dpl** (backup `.pre-tierresearch`) — 4 caves
    @0x5580ED80+: whole-tier grant, flat cost, day-1 sphere grant, tier event text.
  - `build_tierresearch_exe.py` → **AoW.exe + AoWCompat.exe** (backups `.pre-tierresearch`) —
    new **`.tres` section @0x611000**, 14 caves + 24 hooks: list grouping/slot arrangement,
    per-mode runtime layout, titles/turns+cost, icon+name rows, self-healing layout.
  - `build_glowilb.py` → **Int\Scenes\BookWin.ILB** (backup `.pre-glowilb`) — hover glow
    (image 26) intensity 20%→70% and sprite rebuilt 254×82→**254×100**.
  - `build_glowboost.py` → **aowInt.dpl**: **WITHDRAWN, do not apply** (double-compositing the
    lit strip ghosts because the book never repaints under buttons; `.pre-glowboost` is
    byte-identical to the live file and can be deleted).
  Apply order: DLL and exes are independent; the exe layer needs the DLL for correct mechanics.
  Re-tuning any layout/glow constant = **revert the matching backup, edit, re-apply** (the caves
  resize). `HILITE_H` (exe) must stay equal to `NEW_H` (ILB).
- **Hero level-up dialog doubled** (CONFIRMED WORKING 2026-07-31): `THeroUpgradeDlg` 432→864 px
  tall, ability lists 6→31 visible rows. Pure in-place **DFM data edit** (RCDATA `THEROUPGRADEDLG`
  in **AoW.exe + AoWCompat.exe**, no code) — `build_herodlg_tall.py` (`--undo` surgical,
  `--height N` re-tunes in place), backups `.pre-herodlgtall`. Doc: `HeroUpgradeDlg_Tall.md` —
  includes the reusable exe-DFM in-place edit technique (root designer-prop deletion = byte
  budget) and the AOW-toolkit Alignment/AOWWindow semantics.
- **Hero level-up category columns** (CONFIRMED WORKING 2026-07-31, all four rounds user-tested):
  the Upgrades list split into **5 category columns each with its own Cost column** (10 lists),
  presented as **two framed boxes** — hero state above, pickable listings below with
  Remove/Add/Done/Cancel as their header on a knotwork band. Per-column click-sorting. Dialog 960×860.
  `build_herodlg_columns.py` (+ `herodlg_cats.py` = the taxonomy) → **AoW.exe + AoWCompat.exe**,
  new RWX section **`.hcol` @0x612000** holding the relocated DFM, the rebuilt field table and 6 caves;
  backups `.pre-herodlgcolumns`, **revert with `--undo`**. Doc: `HeroUpgradeDlg_Categories_Design.md`.
  **This script now owns the dialog geometry — do not run `build_herodlg_tall.py` any more**
  (it detects the relocated resource and no-ops); use `--height`/`--width` here.
  Reusable technique in the doc: **cloning DFM components and reusing the donors' event-handler names,
  then making those handlers Sender-aware (EDX) — so N controls need zero new methods**; **reparenting
  by the `AOWWindow` ident + the GenericF 8-image frame-set catalogue** (index 88 = a 3px grouping
  frame; a panel needs BOTH `ILFrame` and `ILIndexFrame`); growing a
  Delphi class (field table + `[VMT-0x1C]` instance size); the full RE of `THeroUpgradeDlg`
  (FillLists @0x446954, the listbox strings/GetObject contract, `Engine.SortStrings*` paired sort);
  the proof that **an unbound DFM component is silently tolerated** (`TComponent.SetReference` nil
  guard, vcl30 @0x41326F50); **all 100 learnable abilities** extracted from `Ability.pfs` tag 6
  (corrects a wrong Fire Breath id in the third-party ability map); and the exe `.reloc` rule.

- **5% to-hit increments — the whole-game stat doubling** (CONFIRMED WORKING 2026-08-24, applied
  2026-08-18/20): the to-hit slope was halved at **7** sites and **every** ATK/DEF/RES source doubled,
  so hit chance and the damage distribution are mathematically unchanged — what is new is that
  **half-steps are now expressible** (a 5 pp grade instead of 10 pp). 176 code immediates across
  **AoWEPACK.dpl + AoWTCPCK.dpl** and 651 `.pfs` data bytes in **Release/Unitres.pfs +
  Release/HERORES.PFS**. `build_hitslope5.py` (backup `.pre-hitslope5`), `build_statdouble.py`
  (`.pre-statdouble` on all four files; idempotence marker **`Z5PC` @VA 0x55818000**, manifest
  `build_scripts/fivepct_manifest.json`), and `build_marksmanship_atk2.py` (`.pre-marksatk2`) — the
  last structural item, which **relocates an unowned 72-byte cave at 0x5580C240 by 2 bytes** to make
  room for `add al,al`. Docs: `FivePct_Conversion_Manifest.md` (decisions + traps) and
  `FivePct_Doubled_Sources_Inventory.md` (**generated** by `gen_doubled_inventory.py --write` — do not
  hand-edit). ⚠ 13 of the doubled immediates are owned by **other feature scripts**; re-tune them
  there, not here, or the next `--apply` of the owner will silently undo the conversion.

- **DAM/HP doubling — the second identity** (CONFIRMED WORKING 2026-08-24): every damage source and
  every HP pool ×2, so time-to-kill is unchanged and half-step damage/HP become expressible — the
  congruence pass that finishes the 5% conversion. `build_damhpdouble.py` (147-entry manifest
  `damhp_manifest.json`, marker **`Z5DH` @file 0x117408**) → **AoWEPACK.dpl + AoWTCPCK.dpl +
  Release/Unitres.pfs + Release/HERORES.PFS + Release/HEROES.PFS**, all backed up `.pre-damhp`.
  Companions, each with its own backup:
  - `build_newturn_healcap.py` (`.pre-newturnheal`) — cave **0x55818040**: rewrites the per-turn heal
    sum in **32 bits** and clamps to max, fixing a **vanilla** `add dl,bl` 8-bit overheal wrap that
    vanilla data could never reach (its hero HP ceiling was 30) but doubled pools can.
  - `build_healwrap_fixes.py` (`.pre-healwrap`) — the same wrap at three more sites, caves
    **0x55818100 / 0x55818130 / 0x55818160** (High Prayer fast + tactical, Healing Showers).
  - `build_medal_hpmv.py` **v4** (`.pre-medalhpmv2`) — unit computed-HP cap **100** via a tail `jmp` (v2 introduced it at 120, v3 fixed the quotient bug, v4 lowered it 2026-08-31)
    to a cave at **0x55818080**, and stamps the **`HPC2` gate marker @file 0x117410** that unblocks
    `build_damhpdouble.py` stage 4. **Apply this before the doubling**, not after.
    ⚠ **v2 of this cave was BROKEN** (found in play 2026-08-26): it compared all of EAX at 32-bit
    width, but `div cl` at 0x5580BE43 is an **8-bit** divide leaving the REMAINDER in AH, so every
    unit with `XP mod (level+1) != 0` clamped to **120** — and the heal cave, which reads the same
    `GetHits` for its maximum, then topped units up to that false value so it stuck. v3 fixes it
    with `movzx ebx, al`. ⭐ **The reusable lesson: widening an 8-bit computation to a 32-bit
    compare promotes every previously-truncated dirty bit into the comparison** — vanilla's own
    tail at 0x5580BE6D has the identical shape and is harmless only because its result is
    consumed as a byte. ⚠ The cap must stay **<= 127**: the heal cave narrows HP with `movsx`.
  - `build_editor_spinners.py` (`.pre-spinners`) — 14 DFM `MaxValue` sites in **AoWDevEd.exe +
    AoWEd.exe**, found by owner name, ATK/DEF/RES/DAM → 60, Hits → 120. Without it the editor
    silently clamps a doubled unit on save.
  - `build_pfs_typos.py` (`.pre-typos`) — 62 description strings re-stated to the new numbers.
  ⭐ **2026-08-26 gap pass — three more scripts, all APPLIED/UNTESTED.** A sweep prompted by the
  author asking about Burning found that a paired **(POWER, DAMAGE)** site splits across the two
  passes' scopes, so **neither manifest holds the damage half and both scripts report a clean
  all-clear**. `build_damhp_gapfix.py` (`.pre-damhpgapfix`) fixes Burning 2→4, Decay 1→2 and the
  four TurnUndead AI values; `build_tcpck_damhp.py` (`.pre-tcpckdamhp`) gives **AoWTCPCK.dpl** its
  DAM/HP pass at last — all 145 damhp entries were AoWEPACK, so manual tactical combat kept
  old-scale damage and HP (**wall HP 13/7 → 26/14**, and the game holds THREE disagreeing wall-HP
  tables); `build_morale_scale.py` (`.pre-moralescale`) reverses the D2 morale exception.
  ⚠ **Worst instance: both passes patched DEAD CODE.** `build_firefeed.py` hooks
  `TriggerFireDamage @0x5579020C`, so both wrote their doubled values into the skipped original
  body while the live cave kept 6/3 — map fire ran ~4× too weak. Fixed in that script's
  `caveC_src` (`MAPFIRE_ATK`/`MAPFIRE_DAM`), whose verify now accepts prior cave bodies so it
  re-tunes in place. ⭐ **Standing check this earned: before trusting a manifest entry, verify the
  site is still REACHABLE** — scan for an `E9` hook within 40 bytes before it (exactly 4 hits
  across 383 addresses). Full detail + traps: `DamHP_Double_Decisions.md`.
  ⭐ **`--repair` (added 2026-08-26) is the re-tune path for a manifest-owned immediate.** Both
  `build_statdouble.py` and `build_damhpdouble.py` gate `--apply` on a stage marker, so once a stage
  is marked applied an edited `newValue` can never be written — the scripts detected the condition
  and advised "--undo then re-apply", which is precisely the procedure CLAUDE.md forbids (it wipes
  every layer applied since). `--repair` writes target over live **per entry**, verify-before-write,
  marker untouched. To re-target: set the entry's `live` to the currently-installed value and
  `newValue` to the new one (keep the original in `priorLive`), then `--repair`.
  ⚠ A single clamp's two immediates can be owned by **different manifests** — hero ATK's `cmp`
  half is fivepct's, its `mov` half damhp's. Re-tune both or the clamp half-applies.
  ⚠ The safety margin is **not** the cap: it is that every adder now sums in 32 bits and clamps.
  The ≥50-damage `Invalid Damage Value` assert was raised in the same pass. Doc:
  `DamHP_Double_Decisions.md` (decisions H1–H9, the byte model, and **six pre-existing conversion
  defects repaired here** — three unit-clamp `mov` twins, three `SetUnit*` twins, Self-Destruct's
  attack, the breath/FlameThrowing attack and Magebane's ATK half).

- **Hero chassis DAMAGE doubled + the THero stat-bound ladder** (CONFIRMED WORKING 2026-08-24):
  `build_hero_chassis_atkdam.py` (`Release/HERORES.PFS`, backup `.pre-herochassis`) scales the chassis
  by a per-stat `FACTOR`; the shipped tuning is **ATK ×1, DAM ×2** (attack was briefly doubled and
  deliberately reverted — the 5% conversion had already doubled it). `build_hero_clamps.py`
  (**AoWEPACK.dpl**, `.pre-heroclamps`) owns **seven** bounds on a ladder model: ATK/DEF/RES ceilings
  **40**, DAM ceiling **60**, HITS ceiling **120**, DAM and HITS floors **2**.
  ⚠ **Every bound is a PAIRED immediate** — a `cmp` *and* a `mov` that writes the value. Patching only
  the `cmp` produced the exact bug this doc exists to record: values 31–40 passed the test but
  anything above snapped back to **30**. The script now detects and repairs half-applied states.
  ⚠ HERORES tag `0x13` is **movement**, not a stat — the field-map trap that made the chassis edit
  look like it had a plausible off-by-one. Docs: `Hero_Chassis_ATK_DAM_Double.md`,
  `Hero_Stat_Clamps_40.md`.

- **Unit enchantment re-grade + the Manual section that reads it live** (CONFIRMED WORKING 2026-08-24):
  the doubling left every buff on an **even** value, spending none of the headroom the finer slope
  was bought for; this drops the affected buffs one notch onto odd grades. **36 engine immediates**
  via `build_buff_regrade.py` (**AoWEPACK.dpl**, backup `.pre-buffregrade`, surgical `--undo`) — Fury
  +5, Enchanted Weapon +3/+3, Stone Skin/Frozen/Bloodlust/Dark Gift +3, Blessed and **High Prayer
  Blessing** both +1 DEF/+3 RES, Vertigo and Poisoned −3. Cave-side copies stay with their owners:
  `build_assassin.py` (Holy/Unholy Champion + Assassin **+5/+5 melee, +2/+2 ranged**),
  `build_ranged_slayers.py`, `build_invis_penalty.py` (invisible target: **−2 melee / −5 ranged** ATK
  for an attacker without True Vision). The re-grade **syncs `fivepct_manifest.json` and
  `damhp_manifest.json`** and flips rows to `UNCHANGED` where the new value equals the recorded
  pre-doubling one — without that, `build_statdouble.py` reports a spurious DESYNC.
  `re_tools/enchant_mods.py` is the **live** extractor the Ziggurat Manual's **Unit Enchantments** tab
  reads (21 enchantments / 13 statuses / 7 combat boosts, bucketed by walking **VMT ancestry**, not by
  name); `decode_getter` **raises** on an unrecognised encoding rather than guessing. Zeros render as
  an en-dash, and the tab sits in the **Units & Heroes** group. Doc: `Unit_Enchantments.md`.
  ⚠ Three owner scripts (`build_assassin`, `build_invis_penalty`, `build_ranged_slayers`) emit bodies
  ending `jmp <stock exit>` while `build_magebane.py` splices into those exits — all three now accept
  a stock **or** a known chain exit (`preserve_terminator`) and re-terminate what they write. Before
  that fix all three verified **FALSE**.
