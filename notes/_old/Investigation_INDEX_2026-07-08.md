# Feature feasibility investigation — 2026-07-08 (overnight, Max effort)

Investigation-only RE study of a batch of modding ideas the user requested before bed. **No patches
applied.** Six parallel subagents each took a subsystem cluster and wrote a detailed findings doc;
this index ties them together with a one-line verdict per feature. See each cluster doc for addresses,
mechanisms, proposed patch approaches, and risks.

Status legend: ✅ Feasible · 🟡 Hard/partial · 🔴 Infeasible · 🔎 Needs more RE · ⏳ pending (agent running)

## Clusters & features

### [Abilities & Leadership](Investigation_Abilities_Leadership.md) ✔ done
**Shared model:** Leadership = multi-level ability id `0x2e`; per-owner data record has `+0xc` own/inherent level, `+0x10` external-aura level; `GetLevel` = `max(own,external)`. `GetInherent` proves inherent grants set own-level>0.
1. Semi-randomise hero level-up ability choices each level — ✅ **~82%.** Candidate set = 6 stat spinners + a learnable-ability list, gated by skill-pts + `CanExpand`; DLL AI mirror = `THero.ExecuteUpgradeHeroAI` @0x55787a24. Human dialog **`THeroUpgradeDlg` in AoW.exe** (VMT 0x4458C8, singleton [0x45a0f0]): `Setup` @**0x446268**, ability loop in `PopulateLists` @0x446954. **Injection:** roll a per-open offered-mask in `Setup` (store in a new global) + 5-byte hook at **0x4469F2** (ability loop skip→`jmp 0x446A49`) + optional stat-button disables. Use **`System.RandInt`** thunk @**0x401030** (local RNG) — NOT `TAoWHSMap.Random` @0x5577827c (MP-lockstep, asserts out of sync). New PE section needed (CODE slack ~20 B); patch AoW.exe + AoWCompat.exe. See doc §1.4.
14. Restore multi-level Leadership (cut content) — ✅ **DONE (4 levels), CONFIRMED WORKING 2026-07-20** — `build_leadership4.py`, `.pre-leadership4`, doc `Leadership_FourLevels_And_Fix.md`. Cap 1→4, cost 10/level (re-tuned from 20), curve **re-tuned 2026-08-20 to I +1/+1 · II +2/+2 · III +3/+3 · IV +4/+4** (raw values on the post-5%-conversion doubled scale = a flat +5/+10/+15/+20 pp ramp; was I +1/+0 · II +1/+1 · III +2/+1 · IV +2/+2), both bonus tables relocated to `0x5580F0C0`/`0x5580F0C8`, and `GetLevelName` now appends " I".." IV" by reusing Marksmanship's literals via a VMT+0x10c repoint. *Original estimate below, kept for the reasoning:* **~88% to 3 levels.** `TLeadershipAbility.Create` @0x5576616c stomps the cap `[+0x28]=1` (base `TMultiLevelAbility.Create` sets 4) at imm **`0x5576618a`**, and populates only cost[1]=20. Fix = change cap byte `01`→`03` + a small position-independent cave adding `TIntegerList.Put(list,2/3,cost)` (rel32 to `0x55702eb4`). Atk/def bonus data for levels 1-3 already present at `0x558e83e7`/`0x558e83eb` (+2 atk/+1 def flat); 4+ levels collide with adjacent data.
15. Bug: unit Leadership disabled by hero's baseline Leadership — ✅ **FIXED, CONFIRMED WORKING IN-GAME 2026-07-20** (`build_leadership_fix.py`, `.pre-leadershipfix`; root cause in `Leadership_Disable_Bug_RootCause.md`, as-built in `Leadership_FourLevels_And_Fix.md`). The loss was real and **permanent** (survived separating the unit). Two defects compounded: (A) `TAbilityOwner.UpdateDefaultAbilities` @0x5574F518 gates the grant on `GetAbLevel` (VMT+0x84 → **effective** level = own ∪ borrowed), so a unit ranking up **inside a leader's aura** looks like it already has Leadership and its inherent record is never copied — only the bit is set; (B) `ResetExternalSource` @0x557662E4 treats `own==0` as "borrowed, delete", so on leaving the aura it clears the bit **and** frees the record. No re-grant follows: `TUnit.NewDay`'s full rebuild is **day-1 gated** @0x55782CA9 and `SetExperience` needs a *rank change* — which never comes at gold medal. Heroes are vulnerable the same way (level-up inside another aura). The unused `GetInherentLevel` @0x55765200 is the correct term for (A). Unit/hero template data is clean; the only bare-bit Leadership in the game is the **Crown of Kings** item (separate defect: reads as level 0 → no bonus, no aura).

### [Path abilities & Movement](Investigation_Path_Movement.md) ✔ done
**Cross-cutting:** all three route through `TAbstractUnit.MovedTo` @0x55780328, but Path abilities = terrain-changers while speed = the cost table. Single authoritative move-cost builder: `CreateMovePointTable` @0x5577fdc4 → `MovePointCost` @0x55780848 (feeds both real movement AND the predictor arrows).
2. Unit-ID into Path abilities → Sandworm faster in desert — ✅ **85% (tunneling-keyed) / 75% (ID-keyed).** Speed lever is the cost table, not the Path ability (wording conflated them). Hook tail of `CreateMovePointTable`, subtract from Desert row `buf[1+2*0x10+col]`. Discriminator: Tunneling move-type bit 0x80 (ability 0x2a — needs no lookup) or exact unit id (`[[unit+0x40]+0x18]`). ⚠ numeric Sandworm ID not in DLL — extract from game data.
12. Expand Path-ability radius + proc per step — ✅ **IMPLEMENTED & CONFIRMED WORKING IN-GAME (2026-07-08)** as **radius +1 with 25% proc on the OUTER ring only** (inner disk stays 100%). `build_scripts/build_path_outerring.py`, backup `.pre-pathring`. Radius = three 1-byte edits `6A 01`→`6A 02` @0x5578044e/0x55780495/0x557804da; per-hex ring gate via `dHXtoHN` + `AoWHSMap.Random(map,4)`; scratch in **BSS** `0x558FA800` (CODE is read-only — see technique doc). **Reusable "per-hex ring detection" write-up: [`HOWTO_PerHex_Ring_Detection.md`](HOWTO_PerHex_Ring_Detection.md).**
5. Frostling/Azrac racial faster movement on snow/desert — ✅ **80%.** Race = byte index @ `[[unit+0x40]+0x20]` (`TUnit.GetRace` @0x55782c90); same `CreateMovePointTable` hook reduces Snow row (terrain 3, Frostling) / Desert row (terrain 2, Azrac). ⚠ numeric race values assigned at data-load — extract Frostling/Azrac indices from game data once.

### [Items](Investigation_Items.md) ✔ done
3. Scroll items work as scrolls (cut content) — ✅ **re-investigated 2026-07-30: scrolls are a COMPLETE shipped feature with NO DATA.** Item type 5 is the RTTI enum member **`itScroll`** (`TItemTypes` = itHead/itTorso/itAttack/itDefense/itRing/**itScroll**/itUse, names @VA 0x55708C50) — the engine (`CanUse`@0x557940ac, `ExecuteUse`@0x55793f68, MP-safe `TItemTE` path), the in-game Use button (`TUnitWindow` shows `ItemUseBtn` iff type==5 @[exe]0x40A657 → `UseItemClick`@0x00409FFC), the AoWDevEd item editor (type combo entry "Scroll" → reveals a **"Scroll spell:"** dropdown writing `item+0x38`), the artwork (`Images/ITEMS/I_Scroll.ILB`, gfx 316–319) and the localized strings all ship. **`Release/ITEMS.PFS` simply has 0 of 83 items at type 5**, and the generator constant **`AoWE.itAll` = 0x5F has bit 5 cleared** (VA 0x558E803C = file 0x1E6E3C) so treasure/exploration-site rolls can never yield one. Shipped behaviour = one-shot **tome** (permanently researches the spell, then consumes the item), not a cast. Restoring = mostly data (author type-5 items; retype ITEMGFX 316–319 tag 8 from 6→5) + one byte for random generation; ⚠ open defect: `ItemUsePnl` (+0x160) is `Visible=False` in the DFM and never shown, which likely hides the Use button — verify in-game. Making scrolls *cast* instead of teach is a separate ~2-cave change in ExecuteUse/CanUse (cast primitive `GetSpell`→vtable[0x68] validate→[0x6c] activate, bypasses mana/research); **no scroll-vs-tome discriminator needed** since no type-5 item exists to convert. — **BUILT as Feature 1b (permanent per-hero spellbook grant, not a one-shot cast): ⚠ APPLIED 2026-07-30, BROKE THE SPELL BOOK, REVERTED 2026-07-31 — root cause not yet found** (spells + icons missing, error dialog, freeze; clean A/B, files restored byte-identically to backup). Every static check passes — stage 1 of the cave is instruction-identical, the gate bytes and ITEMGFX retype are provably inert with 0 type-5 items, no absolute refs point into the grown zone, and the VMT slots are right — so the defect is in an assumption, not the arithmetic. Bisect with `--stage1only`. Full elimination list in `Investigation_Items.md` Feature 1b.** `build_scroll_spellbook.py` + `build_scroll_gfx.py`, backups `*.pre-scrollbook` / `ITEMGFX.PFS.pre-scrollgfx`, revert via each script's `--undo`. Rewrote `cave_bookfilter@0x0060C0A8` in place (130→332 B) — ⚠ do not re-run `build_spellcast_book_exe.py --apply`. Still needs a type-5 item to be authored in AoWDevEd before anything is observable.
6. Item-granted HP and MV (beyond ATK/DAM/DEF/RES) — ✅ **BUILT AND APPLIED 2026-08-31, UNTESTED IN GAME** (`build_item_hpmv.py` engine + `build_item_hpmv_data.py` data; 32 items in **`User/Zig.ail`**, the live library). Original scoping:** ATK/DEF/DAM/RES sum item bytes +0x46..+0x49 via `THeroItems.Get*`; `THero.GetHits` @0x5578859c (VMT +0xD0, clamp **[2,120]**) / `GetMoves` @0x557885c0 (VMT +0xD4, clamp [1,80]) have the identical additive shape but omit the item term. Both still vanilla-shaped and unhooked; `THero` and `TLeader` share them; 0 relocs in the hook footprints; item bytes **+0x4a/+0x4b still free** (instsize 0x4C); `TItem.ReadWrite` tags **0x17/0x18 free** in code *and* data. Auto-resolve comes free (AoWTCPCK does 74 × `call [reg+0x84]` → `TCombatUnit.GetHits` → vtable[0xD0]). Cheaper than the 2026-07-30 estimate because **`build_useitems.py` (applied) already ships the aggregator-cave template at `0x55815080`** — clone it with offset 0x4a/0x4b. ⚠⚠ **THE TRAP: `add dl,[eax+0x6d]` is an 8-BIT add and `base + hero+0x6d` already reaches the 120 ceiling, so any item bonus ≥ 8 wraps past 127 and the floor clamp returns 2 HP — sum in 32-bit.** Full plan, authoring and display routes in `Investigation_Items.md` FEATURE 2.

### [Spellcasting extras](Investigation_Spellcasting_Extra.md) ✔ done
4. Per-unit intrinsic spellbook listings (e.g. Yaka Avatar → Fireball) — 🟡 **72%.** Casting never checks research (`THero.CanCastSpell` @0x55789710 gates only mana+CanActivate+tier); a spell just needs to *appear* in the book. Hook = extend exe `cave_bookfilter` (@0x60C0A8, caster at [EDX+8]) with a unit-id→spellID table. Snag: exe imports `GetSpell` but not `TSpellList.Add` → needs manual TList append / import surgery.
9. HP-cost or MV-cost for casting spells — ✅ **"in addition" 85% / "instead" 60%.** Deduct sites: `THero.CastingDone` @0x557893e8 (instant) & `ExecuteStartCasting` @0x55789130 (channel). HP @ unit+0x3e (SetHitPoints VMT +0xE4, clamps), MV @ unit+0x3d. "Instead of points" harder — points also gate instant-vs-channel affordability.
8. Unit enchantments scaled cost/upkeep by size/level/transport — 🟡 **upkeep 85% / cast-cost 55%.** ⚠ SIZE is dead (`GetUnitSize` @0x5577f184 always returns 1 — all AoW1 units 1-hex); use LEVEL (resource+0x2f) or transport cap. Upkeep @ ench+0x10; hook tail of `TUnitEnchantmentAbility.Expand` @0x55765894. Cast-cost only partly reachable (combat caster path untraced).

### [Combat mechanics](Investigation_Combat.md) ✔ done
**⚠ DISCOVERY — undocumented combat caves already live in your DLL** (diff vs the vanilla backup): `cave_5580C150` (Life Stealing +1→+2 HP), `cave_5580C240` (marksmanship-ranged rework + height penalty), `cave_5580C390` (XP-on-hit rescale). Not from this session — pre-existing, **undocumented** combat work. New caves must avoid `0x5580C000–0x5580C3FF` (and the session caves at `0x5580D900+`). See "Cross-cutting" below.
7. Make unit size relevant (large units obstruct missiles?) — ✅ **REASSESSED 2026-08-09 → Feasible (small cave), see [`Missile_Trajectory_And_Interception.md`](Missile_Trajectory_And_Interception.md).** The original "no LOS code exists, blocking is net-new" verdict was wrong: it searched only `AoWEPACK.dpl`. **Manual tactical combat already intercepts missiles per-hex** — `AoWTC.MakeRangedPath` @ `0x00427630` (**AoWTCPCK.dpl**) traces the flight arc, scores every intervening hex holding a unit / wall / Obstacle overlay / EarthWall-Border terrain into a 0–100 chance, and `CombatTE.TCAbRangedTE.NextStrike` @ `0x0040D290` rolls it and **retargets the shot onto the blocker**. Arc height (per-ability, `MakeAbilPath` @ `0x004271EC`) is the anti-blocking term. Adding a size term = extend the unit handler at `0x00427C0B`. Still true: auto-resolve has no blocking at all (walls give only a −2 ATK cover penalty), and **all AoW1 units are 1-hex** (`TAbstractUnit.GetUnitSize` @0x5577F184 ≡ 1), so size remains an invented stat — prefer level / transport capacity, or drive it off the flight arc instead.
11. Lifestealing on round-attack hits (+ optionally defensive) — ✅ **round 90% / defensive 85%.** Life Stealing = ability 0x76; sets heal-flag bit 0x02 @ `CA+0x18` — but ONLY in `TMeleeRound.CreateStrikeCA`@0x55767E68's offensive branch (@0x55767EDA). Round attack uses a *different* builder (global `CreateStrikeCA`@0x557665E4) that never checks 0x76; defensive/retaliation branch omits it too. Fix = add the same `HasAbility(0x76)→OR CA+0x18,0x02` to the global builder (round) and the retaliation branch (defensive) — existing heal cave then fires. (User wants round only; defensive is separable.)
13. Enchanted Weapon for mundane ranged attacks (atk/dam + magic type) — ✅ **85%.** Enchanted Weapon = ability 0x9A (+2 atk/+2 dam + Magic bit 0x08 into **melee** via GetDamageTypes@0x55766DE4). Ranged bypasses it (independent stats: `GetAttackRA`@0x5576E65C, type `GetDamageTypesRA`@0x5576E6B0). Fix = one cave on `CreateRangedAttackCA`@0x5576EAE4 (shooter = param_2): if `GetAbilityEnabled(0x9A)` add +2 atk/dam and OR 0x08 into the damage-type word. Marksmanship (ability 0x20) is the exact working template.

### [Storm-debuff protections](Investigation_Storm_Protections.md) ✔ done
10. Poison/holy/death protections vs Pestilence & Divine/Death storm debuffs — ✅ **~90%, ONE cave.** All three debuffs funnel through `ExecuteStormDamage` @0x55780668 → `ExecuteDamageEffects` @0x55781e28 at hook site **0x5578080f** (`8B C7 E8 12 16 00 00`). Pestilence→Poisoned (bit 0x10), Death Storm→Cursed (0x20), Divine Storm→**Vertigo** (0x40). **Premise correction:** `ExecuteDamageEffects` already masks with `~GetImmunityTypes` (+0xEC) AND immune units take 0 base damage → immunity already blocks the debuff entirely. The real gap: it never reads `GetProtectionTypes` (+0xF0), so *protected* (half-damage) units still get the full debuff. **Fix:** redirect 0x5578080f → cave that does `DX &= ~GetProtectionTypes` before the call (mirrors the `~immunity` masking); free space @0x5580DC80. Poison-Prot(0x49) resists Pestilence, Death-Prot(0x46) Death Storm, Holy-Prot(0x48) Divine vertigo. Leaves TPoisonPlant untouched, base damage unchanged. ✅ Vertigo confirmed present + patched into this DLL (diff vs May-2025 copy: added `CMP AL,3;JZ→DX=0x40`; also ×8→×4 terrain-dmg). ⚠ DECISION: vertigo is gated by the holy bit only, so *holy protection* would block it — confirm that's intended.

---

## Scorecard (all 6 clusters done)
✅ Feasible (9): scrolls, item HP/MV, HP/MV spell-cost, Sandworm-desert, Path radius+proc, Frostling/Azrac
race, multi-level Leadership, Lifesteal round/defensive, Enchanted-Weapon ranged, storm-debuff protections.
🟡 Hard/partial (3): per-unit spellbook, enchant cost/upkeep scaling, unit-size cover-penalty.
🔎 Needs-more-RE (0). 🔴 Infeasible (0).
*(#7 missile blocking reclassified ✅ on 2026-08-09 — the mechanic already exists in AoWTCPCK.dpl.)*
*(#15 Leadership-bug reclassified 2026-07-19: root cause found, own doc, independent of #14.)*
**Nothing is a hard no** — every idea is at least partially reachable.

## Cross-cutting themes & shared prerequisites
1. **⚠ You already have undocumented combat caves live** at `0x5580C150 / 0x5580C240 / 0x5580C390`
   (Life-Steal +2, marksmanship+height, XP-on-hit) — found by diffing the DLL vs the vanilla backup.
   They're **not recorded** anywhere in Modding Resources. Recommend: document them (or tell me they're
   someone else's) before layering more combat work. Occupied pockets to avoid:
   `0x5580C000–0x5580C3FF` (combat) and `0x5580D900+` (this session: firefeed/spellcast-persist/icestorm/
   raise-lavadirt). Interstitial gaps: `0x5580C400–0x5580D8FF` and `0x5580DC80+`.

   **⚠ CORRECTION (2026-07-21): DLL cave space is NOT scarce — this section originally read
   "cave-space map is filling up", which was only ever true of the crowded `0x5580C000–0x5580D900`
   pocket, not of the binary.** Measured directly: `AoWEPACK.dpl` CODE is VA `0x55701000`,
   vsize `0x1E6918` (virtual end `0x558E7918`), rawsize `0x1E6A00` — rawsize ≥ vsize, so the **whole
   section is file-backed**. In the **pristine shipped DLL** the last non-zero byte is `0x5580BDEE`,
   leaving ~900 KB of zeros; in the live DLL it is `0x5580F959`, leaving **884,670 verified-zero
   bytes** up to `0x558E7918`. Every cave this project has written lives in that tail (~16.7 KB used
   so far), so the region is proven usable in-game. Allocate new DLL caves upward from `0x55810000`;
   hard ceiling `0x558E7918` (DATA starts `0x558E8000`), stay under `0x558E7000` to be safe.
   Still read+execute only — mutable cave state belongs in BSS slack from `0x558FA800` up.
   **The "~20 bytes of alignment slack → need a new PE section" note in
   `Investigation_Abilities_Leadership.md` §1.4 is about AoW.exe, NOT the DLL, and remains correct
   for exe caves** (hence the `.sc` / `.clog` / `.mtb` section pattern). Don't carry it over.
2. **Data-extraction prerequisite (blocks 3 features):** several need numeric IDs that live in the game
   *data packs*, not the DLL — **Sandworm unit id** (#2), **Frostling & Azrac race indices** (#5). One-time
   task: read them from the resource data / editor. Tunneling can instead be keyed on move-type bit `0x80`
   (ability `0x2a`), sidestepping the Sandworm id.
3. **MP-safe RNG discipline (recurring):** the DLL's `TAoWHSMap.Random` @`0x5577827c` is MP-lockstep and
   *asserts if used outside a synchronised context* (the exact popup we hit on the lava→dirt work). Rule of
   thumb confirmed across features: use it **only** in synchronised game-logic (unit moves → #12 proc is
   fine); for UI/AI/animation contexts use the **exe-local `System.RandInt`** (@`0x401030`, #1 level-up) or
   the DLL raw RandInt / the flag-suppress trick. Getting this wrong = desync or the assert popup.
4. **Ability-ID reference harvested** (reusable): Leadership `0x2e`, Life Stealing `0x76`, Enchanted Weapon
   `0x9A`, Marksmanship `0x20`, Tunneling `0x2a`, Poison-Prot `0x49`, Death-Prot `0x46`, Holy-Prot `0x48`,
   Spellcasting `0x7a`. Effect bits: poison `0x10`, death `0x20`, holy/vertigo `0x40`, magic `0x08`.
5. **"Unit size" is largely a dead axis** — all AoW1 units are 1-hex (`GetUnitSize`≡1); size only drives
   melee slaying bonuses. So #7 (missile blocking) and any size-scaled-cost idea (#8) should pivot to
   *level* / *transport capacity*, or accept size-as-a-cover-stat as a new invented mechanic.
   ⚠ Corrected 2026-08-09: this stays true of *size*, but #7's premise was wrong — missile blocking
   itself already exists in manual combat (`Missile_Trajectory_And_Interception.md`), and the natural
   knob is the per-ability **flight arc**, not size.
6. **Multi-level Leadership (#14) and the Leadership-disabled bug (#15) are independent** — raising the
   cap does not fix the bug (a lvl-2 medal grant is still masked whenever the borrowed level is ≥ the
   template's), and the fix adds no levels. **BOTH CONFIRMED WORKING IN-GAME 2026-07-20** as two
   separate scripts — see `Leadership_FourLevels_And_Fix.md`.

## Suggested sequencing (when you're back)
- **Quick, high-confidence wins:** Path radius (three 1-byte edits, #12), storm-debuff protection (one cave,
  #10), item HP/MV (#6), multi-level Leadership (#14), Lifesteal-on-round (#11).
- **Medium:** scrolls (#3), Enchanted-Weapon ranged (#13), HP/MV spell cost (#9), Sandworm/racial movement
  (#2/#5, after the data-ID extraction), enchant upkeep scaling by level (#8).
- **Bigger / research-first:** per-unit spellbook (#4, needs exe TList-append surgery), hero level-up
  randomization (#1, needs a new AoW.exe PE-section). *(#7 moved out of this tier 2026-08-09 — it is a
  small AoWTCPCK cave, not net-new LOS code.)*

## Decision points parked for you (not blockers — just choices)
- #10: Divine-Storm **Vertigo** is gated on the *holy* bit, so Holy Protection would resist it — OK, or do
  you want a vertigo-specific resist? · #11: round-attack lifesteal only, or also defensive? · #8/#7: accept
  size as an invented cover/cost stat, or pivot to level/transport? · #1: how many of the eligible abilities
  should each level-up offer (subset size)?

*Note: your list ended with a trailing empty bullet — no feature was specified there; add it anytime.*
*All findings are investigation-only. No game binary was modified.*
