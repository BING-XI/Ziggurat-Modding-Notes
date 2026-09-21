# Caster cost abilities — Evoker / Conjurer / Enchanter / Ritualist

**Status: CONFIRMED WORKING (2026-08-27).** Validated in-game by the user.
Build script: `build_scripts/build_caster_cost.py`.
Spec (design rationale, membership tables, per-site derivations): `Caster_Cost_Abilities_SPEC.md`.

Each ability halves the **initial casting cost** of one spell family. Nothing else: no damage
change, no per-turn upkeep, no research cost, no icons (AoW1 abilities have none), no level tables,
no per-owner data record.

| ability | id | family | spells | cave cost | **live cost** (`Ability.pfs` tag 6) |
|---|---|---|---|---|---|
| Evoker | `0xAC` | `TCombatSpell` | 30 | 20 | **20** |
| Conjurer | `0xAD` | `TSummonSpell` | 13 | 40 | **40** |
| Enchanter | `0xAE` | `TUnitSpell` | 18 | 40 | **30** ⚠ |
| Ritualist | `0xAF` | `TGlobalEnchantmentSpell` | 12 | 40 | **30** ⚠ |

⚠ **The cave column is dead — the cave CANNOT set a level-up cost for these abilities.** They
shipped reading **0** and had to be given tag 6 in AoWDevEd. `Ability.pfs` records 182–185 (read
2026-08-27) carry tags 6/7/8/9, tag 6 = 20/40/30/30, tag 9 = `0x03FF` on all four.

**The rule, established 2026-08-27 — which source wins depends on the ability's KIND:**

| kind | cost lives in |
|---|---|
| **multi-level** (Leadership, Marksmanship, Dispel Magic, Spellcasting …) | **code** — the class overrides `ExpandCost`; `TDispelMagicAbility.ExpandCost @0x5576D130` is literally `return 5`, and tag 6 is ignored |
| **single-level / bit-only** (these four) | **`Ability.pfs` tag 6** — they inherit `TAbility.ExpandCost @0x5574E908` = `return [ability+0x14]` |

`TAbility.ReadWrite @0x5574F07C` passes the **address** of `[ability+0x14]` to the property reader
for tag 6, and that load runs *after* registration — so the data always overwrites the cave, and an
absent tag 6 leaves the field at **0**, i.e. **permanently free** (`THero.UsedSkillPoints` sums
`ExpandCost`). Change these costs in DevEd; re-running the build script cannot do it. The script
prints the live tag 6 on every run and flags any disagreement with its own constants.

⚠ **None of the four has a tag 5 description** — the records carry only 6/7/8/9. The abilities show
with no descriptive text until one is authored in DevEd.

Costs set 2026-08-26 (`LEVEL_COST` in the build script). ⚠ **The cave value is what AoWDevEd
serialises into `Ability.pfs` tag 6 on its first save — after that the DATA FILE WINS**, so changing
`LEVEL_COST` once the records exist has no in-game effect until tag 6 is edited in DevEd too. The
script warns about this when it detects existing records.

35 of 108 spells are deliberately uncovered (storms, terrain, city and target spells).

## Footprint — six sites, five caves, all in `AoWEPACK.dpl`

| | site | → | size |
|---|---|---|---|
| HOOK1 | `0x557894EC` `THero.CastingMana` **entry**, 7B | `cave_cost` `0x55820800` | 120B |
| HOOK2 | `0x55789510` the vanilla epilogue, 5B | `cave_floor` `0x55820878` | 20B |
| HOOK3 | `0x557BCF04` spare `call RegisterAbility`, 5B | `cave_reg` `0x558208B4` | 246B |
| SITE A | `0x557EFA7C` `TGlobalEnchantmentSpell.Activate`, 7B | `cave_gench` `0x5582088C` | 18B |
| SITE B | `0x557E44F8` `TSummonSpell.Activate`, 7B | `cave_summon` `0x558208A0` | 19B |
| SITE C | `0x557E4353` `TSummonSpellTE.Process`, 7B | **in place, no cave** | — |

### In-place re-tune (no revert, ever)

Changing a level-up cost changes four `mov [eax+0x14],imm32` immediates inside `cave_reg` and
nothing else — the block size is fixed at 43 bytes, so no address moves. The script classifies that
as **`RETUNE`**: `retuned_costs()` masks the four cost dwords and compares the rest, so the cave is
recognised as its own at a different cost and **rewritten in place**. Any other differing byte falls
through to `OTHER` and a hard abort.

This is the CLAUDE.md rule made concrete — *never write "revert and re-apply" as a re-tune
procedure*. A `.pre-*` restore would wipe every feature layered on since, and with several sessions
patching this DLL that is now days of other people's work.

**Cave reservation `0x55820800..0x55820FFF` EXCLUSIVE** (423 bytes emitted, 428 with alignment).
Neighbours: `build_los_terrain.py` below (`0x55820000..0x55820800`), `build_dispelmagic5.py` above
(`0x55821000..0x558213FF`), `build_shipyard_income.py` above that (`0x55822000..0x55822FFF`).

Backup `AoWEPACK.dpl.pre-castercost`. **Revert with `--undo`** (surgical, restores 11 sites and
zeroes only the 423 emitted bytes — never the rounded reservation).

## The three design decisions that shaped it

1. **Hook the entry, not the existing mastery hook.** `build_mastery_cost.py` owns `0x557894F8`
   *and* the function's tail (`jmp 0x55789510`), and by `0x557894F3` the caster in EAX is
   overwritten and never spilled. A caster-dependent discount can only be a prologue insert.
2. **The floor needs its own hook.** A floor set in the prologue does not survive: the mastery cave
   rescales EBX afterwards and `(1×3)>>2 = 0`. `cave_floor` sits at the exit, which makes the two
   halves **orthogonal to mastery_cost** — either feature can be undone without breaking the other.
3. **Classification is a VMT slot *difference*, so it needs no PIC anchor.**
   `[VMT+0x6C] − [VMT+0x18]` cancels the load delta; `[VMT+0x18]` is `TSpell.ReadWrite` for all 117
   subtree classes. Combat needs a second test (`[VMT+0x80] − [VMT+0x18] == 0x7E034`) because its
   `+0x6C` constant is shared with the abstract `TSpell`.

## The wallet fix — and the vanilla bug it repairs

`THero.CastSpell` takes an instant branch when `CastingMana ≤ [hero+0x80]`. On that branch the cost
was re-read **raw** from `[spell+0x14]`, skipping `CastingMana`. All three raw-read sites are
byte-identical to the pristine backup, and vanilla's sphere-Mastery ×2 lives *inside*
`CastingMana` — `GetSphereManaDoubled @0x5577E230` has **exactly one code caller**. So any path
skipping `CastingMana` skips the multiplier too.

**Why nobody noticed in 27 years:** a ×2 *penalty* makes the gate stricter than `TSpellTE.Validate`'s
re-check, so the re-check can never trip and the only symptom is an uncharged penalty. A ×0.5
*discount* pushes the gate the other way and opens a hard silent-failure band `D ≤ P < R` where the
spell is accepted and then dropped. **General rule: when a gate and a later re-check read different
versions of the same number, the sign of the modifier decides whether the bug is invisible or fatal.**

Consequence, signed off by the user: `mastery_cost`'s ×1.50/×0.75 now reaches instantly-cast summons
and global enchantments for the first time.

## QA — adversarial pass, 2026-08-26 (PASS-WITH-NOTES)

Five independent verifiers plus an adjudicator that re-checked every major finding against live
bytes. **No defect in the installed bytes.** Fixed in the script afterwards: a false id-clash from
scanning its own cave, an `--undo` that could unregister ids whose bits were already set, inverted
ordering comments, three wrong docstring figures, a non-atomic write, and an inflated byte count.

**Two findings worth keeping:**
- ⚠ **Water Mastery tripwire.** `TWaterMastery.ExecuteTE @0x557F0A88` reads the raw cost, so SITE A
  does not cover it. Harmless *only* because 250 → 125 → 93 exceeds the 90-point casting ceiling.
  Lower its cost, raise the casting-points ladder, or add a second discount and it flips into a
  250-mana charge against a 93-mana preview.
- ⚠ **Cosmagic Scrying residual band.** Spell 59 routes through
  `TCosmeticSurgerySpellCaster.Cast @0x557E8524`, which still pushes raw, so at Spellcasting 1
  (`7 ≤ 10 < 15`) the cast does nothing. Empty from level 2. Fixable as a fourth wallet site.

**Refuted — do not re-investigate:** the six auto-resolve combat spells that store the raw cost do
**not** over-charge. Their gate is raw too (`fcPrefetchCombatCommands @0x557F76FF`), and the manual
tactical path pushes charge=0 at all three `CreateCA` call sites, so the raw store never runs there.
Also refuted: the `vmtSelfPtr` guard is *not* what makes the `+0x148` call safe — every combat class
has a valid self-pointer. What makes it safe is the caller set: all seven combat-side callers bridge
through `[combatObject+0x4C]` first.

## Verified without the game

- All 6 windows byte-matched expectations and were identical to vanilla pre-patch; **zero `.reloc`
  entries** in any displaced window or anywhere in the reservation.
- Diff vs `.pre-castercost`: 7 runs, 355 changed bytes — the six sites plus one contiguous cave
  block. Nothing else in the 2.7 MB file changed.
- Idempotent; **`--undo` → `--apply` byte-exact** (sha256), re-verified after the script fixes.
- Co-tenants `build_mastery_cost.py` and `build_dispelmagic5.py` both still verify their own state.
- `check_ids_free` on the patched file now reports clash `[]` (was `[0xAC..0xAF]`).

## Post-confirmation state (2026-08-27)

The out-of-band work is **done**: `Ability.pfs` records 182–185 exist, tag 9 survived the DevEd
saves as `0x03FF`, and `re_tools/ability_names.py` MODDED now carries `0xAC`–`0xAF` (plus Magebane
`0xAA`, which had been missing since 2026-08-07 and printed as `?` in the Manual).

Two follow-ups remain, neither blocking:

1. **Tag 5 descriptions are empty** on all four. Author them in AoWDevEd.
2. **Enchanter and Ritualist read 30, not the 40 that was asked for** (see the table above). Fix in
   DevEd, not in the script.

⚠ **`--undo` now refuses without `--force`.** Records 182–185 exist, so unregistering the ids would
leave set ability bits pointing at nil and the next ability query would access-violate
(`TAbstractUnit.GetAbilityEnabled` derefs `GetAbility` unchecked at `0x5577F60A`). Strip the
abilities from everything in DevEd first. This gate is in the script and was verified.

### ⚠ A fifth ability appeared during this work — not ours

`0xB0` is now registered by the DLL (30 `CreateEnhancementAbility` sites, highest `0xB0`), with
`Ability.pfs` record 186 carrying tags 7/8/9 only. **It has no tag 6, so it is permanently free** —
`THero.UsedSkillPoints` sums `ExpandCost` = `[ability+0x14]`, and nothing initialises that field.
Another session added it while this feature was being built. Not a conflict with `0xAC`–`0xAF`, but
whoever owns it needs to author tag 6. It also has no MODDED name entry, so it prints as `?`.

## OUT-OF-BAND recipe (historical — completed 2026-08-27)

1. **Launch once.** A bare `Runtime error 217` before the main window = duplicate ability id.
2. **Four AoWDevEd assign-and-save round trips** to mint `Ability.pfs` records 182–185. No build
   script can create one. Author tag 5 (description) and **tag 6 (level-up cost)** there —
   **without tag 6 the ability is permanently free, not merely displayed as free.**
3. Re-check tag 9 stayed `0x03FF` after every save; the data file overwrites the cave's mask.
4. Add `0xAC`–`0xAF` (and Magebane `0xAA`, missing today) to `re_tools/ability_names.py` MODDED.

⚠ **Once step 2 is done, `--undo` refuses without `--force`** — unregistering an id whose bit is set
access-violates at the next ability query (`TAbstractUnit.GetAbilityEnabled` derefs
`GetAbility` unchecked at `0x5577F60A`). Strip the abilities in DevEd first.
