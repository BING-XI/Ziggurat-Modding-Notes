# City raze battles + rebellion battles — RE familiarization & design (2026-07-12)

**Status: DESIGN — nothing applied.** Prereq reading: `Raze_CombatPredictor_Analysis.md` §10/§10b/§12b
(civil status, labels, the exploration-site battle blueprint), `build_razebattle_tower.py` (the whole
tower/structure raze-battle machinery this transplants), `AI_Raze_Decision_CodeMap.md` (AI gates).
All addresses = AoWEPACK.dpl link-time VAs (Ghidra base 0x55700000).

## 1. Decoded vanilla machinery

### 1a. Rebellion (the revolt path)
- **`TCity.CheckRebellion` @0x557AB534** — called from **`TCity.NewDay` @0x557AB864** (once per city
  per day, after base NewDay/day-1 init) and **`TCity.ExecuteAnarchy` @0x557A9CA0** (second trigger;
  both funnel here, so one hook covers both).
- Logic: `owner != 0` && `GetCivilStatus() < 2` (0 Unruly / 1 Unrest) && `GetRazed()==0` →
  roll `Random(100) <= (status==0 ? 75 : 25)` → **REBELLION**:
  1. `MoveArmiesOutOfCity(DAT_557AB6D8=0x00)` @0x557AA808 — **evicts the garrison unharmed** to
     nearby free hexes (hex-spiral outward, `TArmyHS.PlaceEx`).
  2. `TCityRebellionEventLog` (classref @0x557A7760) created + `DistributeLocationEventLog` — the
     "Rebellion in X!" message (Execute @0x557AE020, GetText @0x557ADF94).
  3. `SetPlayer(0)` (vcall 0x1F0 = TCity @0x557AA2C8) — city flips independent.
  4. `GenerateRebelUnits` → `TAbstractUnit.Place` each rebel on the city hex (flag 0x00).
- **No battle anywhere.** The garrison steps aside; the mob walks in.

### 1b. The rebel mob == the raze militia (key convergence)
- **`TCity.GenerateRebelUnits` @0x557ABCAC**: saves RandSeed; seeds `x*10 + Map[+0x22C] + y`
  (deterministic per city+map — NO day term, unlike the patched structure roster); budget =
  **GetSize() × 25**; `FillWithRandomUnits(raceResource[+0x38] list, out, maxLevel=2,
  typeMask DAT_557ABD30=0x03, budget)`; restores RandSeed.
- **`TCity.GenerateRazeDefenders` @0x557AB408 = `GenerateRebelUnits(self,out); return 1`.**
  The populace you fight when razing your city IS the populace that rebels. One roster, two features.

### 1c. TCity raze-family VMT slots (vs the structure machinery we own)
```
0x150 GetRazed              557AB474  (city override: razed/building semantics)
0x154 GetRazeable           5575EDDC  shared
0x158 RazeEx                5576023C  shared (TE machinery)
0x15C SetupRazeDefenderAG   557AA378  city override (defender AG setup)
0x160/0x164 CreateTE/SetupTE shared
0x1A8 GenerateRazeDefenders 557AB408  city override (= rebel mob)
0x1AC PlaceRazeDefenders    5575FE84  shared
0x1B0 ExecuteRaze           557AB414  city override — THE REPOINT TARGET
0x1E8 Raze                  557602F8  shared (human confirm dialog / AI RazeEx)
0x1EC CanRaze               5575FB80  shared (cave_forcefail v6 already gates city razes)
0x1F0 SetPlayer             557AA2C8  city override (ownership transfer w/ income etc.)
```
- **`TCity.ExecuteRaze` @0x557AB414 is thin**: `if TStructure.ExecuteRaze(...)` (the base one at
  0x5575FFC8 — same function our tower cave calls) `then race.SetPlayerRelationValue(player,
  value−30)`. City raze = base raze + a **−30 race-relation penalty** on success.
- Because the base ExecuteRaze runs inside, city razes already pass through: its internal CanRaze#2
  (covered by the v5 structural re-entry range ✓) and the avenger `PlaceRazeDefenders` vcall
  @0x557601F0 (cave_skipavenger is razeok-gated; the vanilla city path doesn't set razeok → vanilla
  avenger behavior, which the rework will supersede).
- The AI raze gate (cave_forcefail v6) already routes cities to the ORIGINAL predictor veto — no AI
  change needed for this feature.

### 1d. Civil status (the rebellion TRIGGER — stays untouched)
`GetCivilStatus` @0x557AC14C / `ListCivilStatusInfo` @0x557ABD34: loyalty = relationBase(−35/−25/0/
+15/+25) + WallType×5 + UpgradeLevel×5 ± 10 terrain + garrison bonus (simfly'd predictor sim of
loyal-garrison vs rebels+disloyal; morale byte unit+0x26, loyal ≥ 41). Labels: 0 Unruly, 1 Unrest,
2 Stable, 3 Content, 4 Cheerful, 5 Oppressed, 6 Enslaved. (NOTE: the user's old city mod zeroed the
walls/upgrade/terrain terms on the live build — see Raze doc §0b/§10b.)

## 2. Design

### 2a. City raze as a real battle (transplant of the tower pattern)
Repoint **TCity slot 0x1B0 → cave_cityraze** (new cave; TCity was deliberately excluded from the
Stage-8 repoint because its ExecuteRaze/GenerateRazeDefenders/SetupRazeDefenderAG differ):
- Reuse the cave_towerraze flow wholesale: razing army = visitor on the city field; militia = fresh
  hidden TDefendersArmy filled via vcall slot 0x1A8 (dispatches to the CITY version = the rebel mob,
  size-scaled 25×size, level ≤ 2) — **no new roster code needed**.
- Wall-less "inside" fight (clear razer party[+0x18] after AddArmy, as Stage 5) — razing your own
  city happens inside the walls.
- Result gate {3,6} → raze: call **TCity.ExecuteRaze 0x557AB414** (NOT the base!) under razeok so
  the −30 race-relation penalty is preserved. 4 → loss-garrison: cave_lossgarrison already does
  IsClass(TPlayerStructure)-gated VIRTUAL SetPlayer(0) → dispatches to TCity.SetPlayer @0x557AA2C8
  correctly; survivors (Design A) become the independent garrison. 2/5 → nothing.
- Fast/tactical/ask + AI-fast (cave_razemode) + no-flee + survivor rehome: all shared machinery
  applies as-is; razeasync/razeplayer flags shared.
- Seed note: the city roster has no day term (RandSeed save/restore inside GenerateRebelUnits);
  per-day variation would need a separate hook in 0x557ABCAC — OPTIONAL, defer.
- OPEN: multi-hex footprints. CanRaze's razer side + the visitor-army pickup use the structure's
  field ([city+4]); razers standing on an outlying footprint hex may need handling (vanilla CanRaze
  has the same view — parity is acceptable for v1).

### 2b. Rebellion as a real battle
Hook **CheckRebellion @0x557AB534 at the post-roll site** (the `MoveArmiesOutOfCity` call at the
rebellion branch): replace evict+flip+spawn with:
1. Build hidden TDefendersArmy(player 0), fill via GenerateRebelUnits — the same mob vanilla would
   have spawned.
2. Real combat on the city: **garrison defends, rebels attack**, wall-less (rebels rise inside).
   Fast for AI/remote owners (cave_razemode-style local-human gate); the local human OWNER gets the
   fast/manual choice (rebellion fires during their own turn's NewDay).
3. Result gate:
   - **Rebels win (garrison wiped)** → vanilla consequence, minus eviction (garrison is dead):
     TCityRebellionEventLog + SetPlayer(0) + place the SURVIVING (damaged, XP'd) rebels via the
     Design-A survivor machinery. City independent.
   - **Garrison wins** → rebels dead, city stays; distribute a (reworded?) rebellion log so the
     owner knows it happened. No loyalty change (vanilla has none).
   - **Stalemate/mutual** → fizzle: nothing changes (city stays, no flip, no spawn).
4. Both triggers (NewDay + ExecuteAnarchy) route through CheckRebellion → one hook covers both.

### 2c. Shared-flag interactions to respect
razeok (re-entry bypass — city raze win path must set it around 0x557AB414 since the base ExecuteRaze
re-calls CanRaze), razeguard (Guard AG + survivor substitution — city SetupRazeDefenderAG @0x557AA378
is the CITY override; the razeguard kind-hook lives on the STRUCTURE version @0x5575FE0C → needs a
city-side equivalent or the Guard AG wired directly), razenoflee, razeasync/razeplayer,
FLAG_RAZESURVIVORS. BSS free from 0x558FA809+ (0x558FA808 = survivors dword). Cave space free:
0x5580D212..0x5580D5FF (after cave_valfix) — likely too small for cave_cityraze (towerraze is ~1005B);
new cave space must be surveyed (the 0x5580C000 region map is in the build script / investigation docs).

## 2d. LOOTING (Part C — decoded 2026-07-12; multiplier APPLIED-UNTESTED, battle NOT yet implemented)
User request: "Looting should be modded to trigger a battle." Mechanism decoded:
- **`TCity.Loot` @0x557AB038**: `CanLoot` check, then (if not busy) queues a **production item** —
  `TProductionItem` with id `CityActionToProductionID(5)` (action 5 → production id **0xe**) via
  `TProductionControl.Produce(city[+0x50], item, 0)`. Loot itself only QUEUES; it computes no gold.
- **`TCity.LootTime` @0x557AB024** = `return 1` — loot takes 1 production turn.
- **Completion + gold award: `TCityProductionControl.NewTurn` @0x557A82A8, `case 5`** (dispatched via
  `ProductionIDToCityAction(0xe)=5`). This is where the gold arrives, computed **twice** as
  `citySize × 9` (citySize = **byte at TCity+0x3c**): once for the event-log text
  (`IntToStr(size×9)` → "City looted for N gold"), once for the payout (`player.gold += size×9` →
  `TPlayer.SetGems`). Both encoded `LEA reg,[reg+reg*8]` (=×9). `CanLoot` @0x557AB02C is a pure bool
  (`(city[+0x44]&2)==0`) — **no loot-value preview exists anywhere else** (verified: only these two).

### Loot multiplier 9× → 15× — APPLIED-UNTESTED 2026-07-12 (`build_loot_multiplier.py`, `.pre-lootmult`)
Per user ("increase the loot multiplier from 9x to 15x"). Both ×9 sites patched in place — `×15`
can't be a single LEA (scale ≤ 8) but `imul reg,reg,15` is *also* 3 bytes (`6B /r ib`), register-only
(no `.reloc` hazard, no cave):
- SITE 1 @0x557A8600 (msg text):  `8D 04 C0` `lea eax,[eax+eax*8]` → `6B C0 0A` `imul eax,eax,10`
- SITE 2 @0x557A86BE (gold award):`8D 14 D2` `lea edx,[edx+edx*8]` → `6B D2 0A` `imul edx,edx,10`
`NEW_MULT` constant at top of the script (currently **10**; must stay imm8 <128 to keep imul 3 bytes).
Idempotent, dry-run/`--apply`, verify-before-write; **re-appliable** (accepts either the vanilla ×9 LEA
OR any prior imul-at-this-site, so retuning needs no revert). Independent of every other patch (own
site, own backup `.pre-lootmult` = vanilla ×9). History: first ×15, user retuned to ×10 2026-07-12.

### Loot as a battle — Part C IMPLEMENTED, APPLIED-UNTESTED 2026-07-12 (`build_razebattle_tower.py`)
The delay IS the penalty (user: "you can't fight-then-immediately-move-away"), so the battle fires **at
production COMPLETION** — hooked at `TCityProductionControl.NewTurn` case-5 TOP (**0x557A85B9**, before
the `mov eax,edi; call BeginUpdate`), just before the gold. Mechanically a city loot == a city raze
whose "looter WON" branch **awards gold instead of razing**; loss and stalemate are identical to a city
raze. Reuses cave_towerraze via a **LOOT BIT** (ExecuteRaze arg DL **bit 7 = 0x80**; with fast bit 0x10
→ arg = `owner|0x90`), exactly like the rebellion bit (0x40). New machinery:
- **`cave_lootbattle` @0x5580D4A0** (74 B, hook = E9+2NOP over the 7-byte displaced mov+call): reads
  the **owner byte `city[+0x30]`** (as cave_rebellion/CheckRebellion/SetPlayer), invokes
  `city.ExecuteRaze` (VMT 0x1B0 = cave_towerraze) with `owner|0x90`, resolved FAST/synchronous.
  cave_towerraze preserves EDI (=the TCityProductionControl, live), which `TCity.SetPlayer` does
  **not** free (verified) → no UAF on a flip.
  **v1 BUG — FIXED v2 2026-07-12 (failed approach, do not retry):** v1 read the owner via **city slot
  0x7C** — but on structures slots 0x74/0x78/0x7C are the **X/Y/LEVEL coordinate accessors** (slot 0x7C
  is GetPlayer only on the *production control*, which is what case 5 calls on EDI — same slot index,
  different class). So v1's "owner" = the city's map **level**: every SURFACE city returned 0, tripped
  the `owner==0` safety guard → battle skipped, gold paid straight (user: "even weak units can loot,
  no injury/xp trace"; an underground city would have fired with player=1). v2 = the +0x30 byte read;
  cave shrank, zero-padded to v1's 74 B so the rewrite covers v1's stale tail.
- Outcomes (VANILLA loot semantics, user-confirmed 2026-07-13 "Win razes it"): **WIN (looter side-0 wins
  3/6)** → case 5 runs in full = ×10 gold + "City looted" message + **`SetRazed(1)` → the city is razed to
  ownerless ruins** (this is what vanilla loot always did; the battle just gates whether you pull it off).
  **LOSS (looter wiped, result 4)** → `cave_lossgarrison` flips the city independent + surviving populace
  garrisons it, looting garrison dead, no gold (the penalty). **STALEMATE (2/5)** → no gold, city + garrison
  held, production stays → re-fights next turn. Defensive: undefended populace (`Lempty`) → win;
  no-garrison (`Lnoarmy`) → no gold.
- The **payout is always the REAL case 5** (`cave_lootbattle` jmps to 0x557A85C0 → BeginUpdate…SetRazed),
  never a transcribed cave — so the gold/message/raze are byte-identical to vanilla. cave_lootbattle hooks
  case-5 TOP (before BeginUpdate) so a no-pay path (`jmp 0x557A8880` epilogue) leaves the update-lock
  balanced; the epilogue only nils NewTurn's zero-init string locals (safe).

### Fast/manual CHOICE — APPLIED-UNTESTED 2026-07-13 (approach A: next-turn payout)
Loot now honours the player's combat-resolve setting (Quick vs Tactical/Ask) instead of forcing fast.
cave_lootbattle passes `owner|0x80` (loot, **no** fast bit); cave_towerraze/cave_razemode still force AI &
remote owners to fast. The hard part is that a MANUAL (modal) fight unwinds the turn-processing stack
before it finishes, so its payout can't ride case 5 synchronously — it pays via the real case 5 on the
**owner's NEXT turn** (chosen over a risky hand-transcribed payout cave). Machinery (three BSS bytes):
- **FLAG_LOOTWIN @0x558FA80C** (healed each towerraze entry) = a DIRECT fast win (registry Quick / AI):
  `Lraze` sets it → cave_lootbattle reads it right after the synchronous battle → pays via case 5 **this**
  turn.
- **FLAG_LOOTASYNC @0x558FA80D** (not healed) = "a detached loot is in flight". Set by `cave_typechosen`
  when the picked combat is a loot (it also ORs bit 7 into the re-issued `TE+0x20`). Read by the
  mode-divert (skip the dialog on the re-issue, else infinite loop), by `Lraze` (fast pick), and by
  `cave_razedone` (tactical pick); each consumer clears it.
- **FLAG_LOOTWIN2 @0x558FA80E** (not healed, survives unrelated towerraze entries) = "a manual loot was
  WON; pay next turn". Set by `Lraze` (detached fast pick) or `cave_razedone` (tactical win). Read at
  cave_lootbattle ENTRY → pay via case 5, cleared.
- **Routing**: registry Quick (or AI) → direct synchronous fast → FLAG_LOOTWIN → pay now. Registry
  Tactical/Ask → cave_towerraze **mode-divert** sends the DIRECT loot through the proven raze fast/manual
  **dialog → TE re-issue** (defers the fight to the safe interactive event-processing point, not modal-
  during-NewTurn); the re-issue carries the loot bit (`cave_typechosen`), skips the divert
  (FLAG_LOOTASYNC set), and resolves fast (`Lraze`→FLAG_LOOTWIN2) or tactical (`cave_razedone`→
  FLAG_LOOTWIN2) → pay next turn.
- **Cave shuffles** for the ~90 B of new plumbing: cave_towerraze grew (1159 B) → `cave_canraze` nudged
  0x5580CD90→**0x5580CDA0** (into its zero tail; budget→1168 B); `cave_typechosen` (+loot carry, 141 B)
  RELOCATED 0x5580CE10→**0x5580C560** (pre-towerraze verified-zero block); `cave_razedone` (+loot branch,
  171 B) grew → `cave_rebelchance` moved 0x5580D460→**0x5580D550**; `cave_lootbattle` reworked to 90 B.
  CanRaze hook prior widened (`_own_prior`) to accept the pre-move target.
- **KNOWN benign edges** (documented, degrade to a harmless re-fight next turn): two manual loots won the
  SAME turn share the single FLAG_LOOTWIN2 → the 2nd re-fights; a DETACHED loot on an empty-roster city
  hits `Lempty` (sets FLAG_LOOTWIN, orphaned) → re-fights. FLAG_RAZEPLAYER is shared across the dialog
  async gap (same assumption razes rely on; serial in single-player).
- **Test points**: registry=Quick → instant loot as before. registry=Tactical/Ask → a fast/manual dialog
  at loot completion; pick Tactical → you FIGHT the loot battle; on a win the **gold + raze land at the
  start of your next turn** (the ~1-turn manual payout delay — expected). Loss → lose the city that turn.
- KNOWN EDGE (unchanged): on a loss the completed loot production isn't dequeued (city independent → no
  more processing; harmless unless the exact city is recaptured). ⚠ **Revert Part C: not by snapshot.**
  `AoWEPACK.dpl.pre-razebattle` was **moved** to `Modding Resources/backups/` on 2026-07-29/30 (not
  deleted), but it is layer **14 of 47** — restoring it destroys 33 later features. Undo surgically from
  `build_razebattle_tower.py` instead.

## 3. Open design questions (for the user)
1. Rebellion battle participants: main-hex garrison army only, or all city-footprint armies?
2. Local human owner: offer fast/manual choice, or always fast (vanilla-style event)?
3. Crushed rebellion: any consequence (loyalty boost / cooldown), or rebels-dead-only (vanilla-ish)?
4. City raze roster day-variation: add the day term to GenerateRebelUnits' seed (rebellions and raze
   militia would vary per day like structures), or keep vanilla determinism?
