# AI Raze Decision — Complete Code Map (AoWEPACK.dpl)

**Status: investigation notes, 2026-07-12. Self-contained for review (e.g. by another model).**
Purpose: identify *every* piece of code the AI uses to decide whether to raze a structure, classify
each gate (force / relation / data), and surface the one **unresolved contradiction** between the code
and the user's in-game experience ("more force does NOT make the AI raze mines in vanilla; it razes
hostile cities, mostly under Scorcher AI, and little/nothing else").

All addresses are runtime VAs (Ghidra image base 0x55700000). "slot 0xNN" = VMT offset. Delphi register
convention (EAX,EDX,ECX; callee-clean).

---

## 0. TL;DR for the reviewer

1. The AI raze **execution** path is fully general and razes *any* razeable structure — not city-only.
   `TAIGroupRazeControl.Process` finds *any* `TStructure`, and has a dedicated non-city validator.
2. Every **decision gate** is a function of **force** and (for cities) **diplomatic relation**. None
   gates on structure *type*:
   - `ValidateRazeStructure` = pure force ratio.
   - `ValidateRazeCity` = hostile-relation + (force **or** the Scorcher "always-raze-hostile-city" bit).
   - `CanRaze` = a `TCombatPredictor` sim of *razer vs the structure's own template raze-militia*.
   - The target selector routes any **takeable** hostile target (mine included) to the raze mission.
3. The only force-independent per-structure lever is **`GetRazeable`** (a single template data byte
   `[template+0x58]`, identical code for all classes) and the **template-defined raze-militia**
   (`GenerateRazeDefenders`, from `[template+0x5c]`, NOT scaled to the attacker).
4. **RESOLUTION (after tracing (A) capture-timing and refuting (C) cross-module):** the raze mission is
   **post-capture**, and razeability gates it **first**. Selector status 5 (raze) is emitted in state
   0x15 **only when the target has left the enemy-target list** (`IndexOf==-1`) — i.e. after the group
   has moved to and *taken* the hex. The behavior AGC then attaches `TAIGroupRazeControl`, whose
   `Process` checks **`GetRazeable` (slot 0x154) BEFORE any validator** — if the just-taken structure
   isn't razeable, it does nothing and the structure simply stays captured. Every gate *after*
   `GetRazeable` is force/relation and would pass for a strong AI. Therefore the vanilla "AI never razes
   a mine regardless of force" is explained by exactly one force-independent fact: **vanilla mine/farm/
   node templates are flagged NON-razeable (`[template+0x58]==0`).** The AI *captures* them (income) and
   never reaches a raze because `GetRazeable` is false. Cities/towers are flagged razeable, so the AI
   *does* reach the raze decision for them — where `ValidateRazeCity`'s hostile-relation + Scorcher bit
   apply. This matches the user's memory precisely. (One caveat: the razeable byte is per-template DATA,
   not in the DLL; confirm via "can unmodded vanilla raze a mine at all?" — expected: no.)

Answer to the user's direct question — *"do the raze modes only refer to force superiority?"*: **Yes.**
The raze *modes* (RazeControl `+0x20` bits, the two validators, the CanRaze predictor) are all
force/relation. They do **not** encode a structure-type restriction. So the mine-exclusion, whatever it
is, does **not** live in the raze modes.

---

## 1. Target discovery — which fields become AI targets

- `TAoWMapField.GetAITarget` @**0x55771D84** — fills a 0x18-byte descriptor and sends **MapFieldMsg
  0x1200**; returns `descriptor[0] != 0` (non-zero ⇒ this field is a target). Message carries a
  **scan-type** byte (finder `[+0x132]`) that selects which action the finder seeks.
- Structure `MapFieldMsgProc` (slot 0xCC) dispatches 0x1200 to the class's **`UpdateAITarget`
  (slot 0x1C4)**. Per-class handlers:
  - `TPlayerStructure.UpdateAITarget` @**0x557615B4** (base for mine/farm/node/altar): responds to
    **scan-type 0 only**; marks the structure a target if not razed, requester≠owner, and
    (unowned **or** `ValidAttackRelation` to owner). Target value = slot 0x21C. *No raze/capture
    distinction emitted.*
  - `TCity.UpdateAITarget` @**0x557AA5C0**: scan-type 0/1 = capture/JoinAmount eval (relation, size);
    scan-type 3/5/6 = the requester's **own** city (production/defense). City-specific richness, but
    the enemy-city path is the **capture** (0/1) branch.
  - Per-leaf handlers: `TMine` @0x557B4498, `TFarm` @0x557B2D40, `TPowerNode` @0x557D04F0,
    `TProductionPlace` @0x557BF0F4, `TTower` @0x557C3648.
- Finder scan-type default: `TAIGroupTargetFinder.Setup` writes **0** (@0x5573A2DC). Under scan-type 0
  **both mines and cities are found.** Other scan-type writers: type1 @0x557D9A0B (TRaidAGC), type5
  @0x557DB197 (inside `TFortifyAGC.ProcessStates` @0x557DB0F4), type6 @0x557D7672 (RazeControl).
- `TAIGroupTargetFinder.TargetFoundEvent` @**0x5573A18C** — builds a `TAIGroupControlTarget` from the
  descriptor (copies desc fields into target+0x18..0x38). Target flags `[+0x3c]` are NOT set here.

## 2. Target selection — the state machine that assigns the mission

`TAIGroupTargetSelector.Process` @**0x5573D2C0**. State var `[+0x18]`; **output status byte `[+0x1c]`**
which the behavior AGC reads. Target flags live at `target[+0x3c]`. Flag DAT constants:
`0x02`=can-take-alone, `0x04`=recruit, `0x08`=production, `0x10`=cooperation, `0x20`=**raze route**,
mask `0x1C`=recruit|prod|coop.

- **Round 1 (state 0):** per target, compute required strength/superiority, run `TCombatPredictor`.
  If group can take it alone (result 3 + enough superiority) → set bit `0x02`. Else route through
  recruit/prod/coop sub-controls (states 1–5) which set bits `0x04/0x08/0x10`. Then sort by score → state 10.
- **Round 2 (state 10):** pick best can-take-alone (bit `0x02`) target.
  `if ((flags & 0x1C)==0) { flags |= 0x20; → state 0x14 }` else route to capture/production sub-states.
- **State 0x14:** `if ((flags & 0x20)==0)` → production-location move → **state 0x16**; else (raze route)
  → `SetupTarget(group,target,2,0)` → **state 0x15**.
- **State 0x15:** `IndexOf(target) == -1` → **`status[+0x1c] = 5`** (else 3). ← the raze signal.
- **State 0x16:** `SetupTarget(group,target,1,0)` → `status = 2` (capture).
- `TAIGroup.SetupTarget` @**0x55737648**: records mission **type** (1 or 2) at `group+0x3c` (literal
  from the state machine — *no city check*); type 2 pulls the destination back by `GetMovePointsMin`.

**Net:** status **5** = "type-2 mission" = a validated, can-take-alone hostile target that no
recruit/production/cooperation sub-control claimed. Reachable for a mine.

## 3. Mission attachment — behavior AGCs

`ProcessStates` state 5 (identical shape across behaviors) reads `selector[+0x1c]`:
`==5` → attach **`TAIGroupRazeControl`**; `==4` → wander/other; else → done.
- `TNormalAGC` @0x557DD3C8, `TScorcherAGC` @0x557DE07C, `TAggressorAGC` @0x557DDA28,
  `TDefenderAGC` @0x557DD700, `TExpanderAGC` @0x557DDD44, `TSkirmishAGC` @0x557DE3A8.
- RazeControl **mode byte `[+0x20]`**: Reset default = **0x01** (bit0 strength; `DAT_557D7414`).
  **Scorcher** additionally `mode |= 0x02` (`DAT_557DE358`) and sets factor `+0x28 = 1.5f`; also its
  selector weight `+0x6c = 200.0f`. All others keep mode 0x01.

## 4. Raze validation + execution

- `TAIGroupRazeControl.Process` @**0x557D74E4**: `FindNoneTransparentHS(field, TStructure)` — ANY
  structure. `if GetRazeable(slot 0x154)`: `SetupBattleFieldInfo`/`RetrieveBattleFieldInfo`; then
  `IsClass(TCity) ? ValidateRazeCity : ValidateRazeStructure`; if pass → `ExecuteRaze`. **If not
  razeable, it does nothing (not even capture).**
- `ValidateRazeStructure` @**0x557D74B4**: `bl=0; if mode&4: bl=1; if mode&1 &&
  ROUND(bfi[+0x10] × factor[+0x24]) < bfi[+0x14]: bl=1`. **Pure force.** No relation, no
  city/non-city discriminator; mode bit `0x02` unused.
  **Bucket semantics BYTE-VERIFIED (2026-07-12)** — full decode chain:
  - `DiplomaticRelation` @0x5575B844: same player → **2**; player-vs-player → stored diplomacy byte
    (`TPlayerDiplomaticRelations.GetDiplomaticRelation` @0x55750A10; out-of-range default 3);
    race path → `StatusToDiplomaticRelation` @0x5575B698: race-status 0-1 (hostile) → **1**,
    2 (neutral) → **3**, 3-4 (friendly) → **0**. Enum: **0=friendly/allied, 1=hostile, 2=self,
    3=neutral**.
  - `ReturnBattleFieldInfo` bitsets (+0xC=`0x04`, +0xD=`0x0A`, set by `SetupBattleFieldInfo`
    @0x5575C098): bucket **+0x10 = bit 2 = SELF-player strength only**; bucket **+0x14 =
    bits 1,3 = HOSTILE + NEUTRAL strength**; **allied strength (relation 0) counts in neither**.
  - `TAIGroupRazeControl.Reset` @0x557D73E0 writes **2.0f** (0x40000000) to both `+0x24` (structure
    factor — no AGC changes it) and `+0x28` (city factor — Scorcher lowers to 1.5f).
  - `RetrieveBattleFieldInfo` @0x55778AD4: `InitHNWalk` hex-spiral out to distance **0xF = 15**
    (radius confirmed), MapFieldMsg 0x1108 per field, monotonic max-clamp on both buckets.
  - **Independents are excluded entirely** (byte-verified): `RazeControl.Process` passes bfi flags
    `DAT_557D75C0 = 0x10`; the gate @0x5578C38E (`test [bfi+2],0x10; cmp byte [unit+0x24],0 → skip`)
    throws out every unit owned by **player 0 = independents** from BOTH buckets before any relation
    math (`[unit+0x24]` = owner-player byte). The finer flag `0x04` (count only *roaming* independents
    — excludes AG-kind 2 = Guard and AG-less units via `AG=[unit+0x20]`, AG vcall slot 0xD0 = kind) is
    NOT set for the raze test; other `SetupBattleFieldInfo` callers use it.
  ⇒ **Complete verified rule: the AI razes a non-city iff
  `round(ownPlayerStrength₁₅ × 2.0) < hostile+neutral REAL-PLAYER strength₁₅`** — scorched-earth
  denial ("about to lose this area *to another player*"). Own forces make the test maximally false, so
  a dominant vanilla AI never razes mines; allies count in neither bucket; neutral *players* count as
  threat; **independents — however heavily they guard nearby structures — contribute zero**, which is
  why indie-dense maps never trigger AI razing either.
- `ValidateRazeCity` @**0x557D7440**: `relation = CityRace.GetPlayerRelation(razer)`; if `relation<2`
  (hostile): raze if `(mode&2)||(mode&4)` **or** `(mode&1 && round(relation-2) < bfInfo[+0x14])`;
  if `relation>=2`: only `mode&4` (never). ⇒ **hostile city razed unconditionally iff mode bit 0x02**
  (only Scorcher sets it). **This is the sole city-privileged, relation-gated lever.**
- `TAIGroupRazeControl.ExecuteRaze` @0x557D742C → vcall **slot 0x1E8** = `TStructure.Raze`
  @**0x557602F8** → `CanRaze` (slot 0x1EC) → if pass, `ExecuteRaze` (slot 0x1B0) @0x5575FFC8 (vanilla).

## 5. CanRaze + the predictor (the force sim)

- `TStructure.CanRaze` @**0x5575FB80**: gate `GetRazed==0 && GetRazeable!=0`. Build `TCombatPredictor`:
  `AddOpponent(units on hex belonging to razer)` (side 1) and `AddUnit(GenerateRazeDefenders militia)`
  (side 0). Execute. **Veto (cannot raze) iff `result∈{3,4,6} && GetSuperiority>99`.**
  *(Note: this predictor was **side-swapped** by an earlier session mod — razer=AddOpponent side1,
  militia=AddUnit side0 — which muddies the vanilla veto direction. Treat the exact veto polarity as
  uncertain until re-derived against a clean vanilla dump.)*
- `GetRazeable` @**0x5575EDDC**: returns `*(byte*)([self+8] + 0x58)` — a **per-template data byte**,
  **identical code for every class** (verified: slot 0x154 = 0x5575EDDC for TCity/TMine/TFarm/
  TPowerNode/TProductionPlace/TPlayerStructure). Razeability is therefore pure **data**.
- `GenerateRazeDefenders` @**0x5575FD1C** (structure; slot 0x1A8): random units from the template
  collection `[template+0x5c]`, amount `[template+0x60]`, **capped at ≤8**, seeded by structure XY.
  **Not scaled to the attacker.** (TCity overrides with its own @0x557AB408.)
- `TCombatPredictor.FinishCombat` @**0x5572AF4C** — result byte `[+0x14]` (side0=militia, side1=razer):
  `3`=side1(razer) wiped / both-wiped-militia-stronger; `4`=side0(militia) wiped / both-wiped-razer-
  stronger; `2`=both survive; `8`=wall blocks. `GetSuperiority` @**0x5572B798** = winning side's margin.
  ⇒ **undefended mine → militia empty → result 4, superiority ≈ 0 → NO veto → CanRaze ALLOWS.**

## 6. GetMoveAction (referenced, not the raze driver)

- `TPlayerStructure.GetMoveAction` @0x55761620 → 0/1 (capture). `TCity.GetMoveAction` @0x557AD0D4 →
  0/1/**2** (the JoinAmount/settle path — city-only, but "join", not "raze"). Not the raze router.

---

## 7. Resolution — raze is post-capture; razeability is the gate

The apparent contradiction (a strong AI *should* raze a takeable mine) dissolves once the **timing** of
status 5 is read correctly:

- Selector **state 0x14** (raze route) calls `SetupTarget(...,2,0)` and sets the group's **destination**
  to the target hex, then yields (`state=0x15`, returns "still active"). The group then **moves to and
  takes the hex over subsequent ticks** (capturing an undefended structure / defeating its garrison).
- Selector **state 0x15** runs after that move: `IndexOf(target in enemy-target-list)`. The target is
  now **gone from the list** (it's been taken) → `IndexOf==-1` → **`status[+0x1c]=5`**. (If the target
  were still an enemy — not taken — status would be 3, no raze.)
- So **status 5 = "the group has TAKEN this target"**, and only *then* does the behavior AGC attach
  `TAIGroupRazeControl`. Raze is a **follow-on decision on what was just captured**, not the reason the
  group went there.
- `TAIGroupRazeControl.Process` checks **`GetRazeable` (slot 0x154) FIRST** — before `ValidateRaze*`,
  before `CanRaze`. A non-razeable just-captured structure ⇒ **Process does nothing**; the structure
  stays captured. Everything after `GetRazeable` (both validators, `CanRaze`) is force/relation and
  would pass for a strong AI.

**⇒ The force-independent gate is `GetRazeable` = the per-template `[+0x58]` data byte.** Vanilla flags
cities/towers razeable and (hypothesis, matching the user's memory) mines/farms/nodes **non-razeable**,
so the AI captures income structures and never reaches their raze branch — *regardless of force*. This is
exactly "more force doesn't make it raze mines," and it is DATA, not a mode.

- **(C) refuted:** `aowInt.dpl` = the UI/image package (`AOWInterfaceImgLib`, `TInterfaceIL`,
  `doBltOnWMPAINT`; **zero** raze/AI/AGC strings). `AoW.exe` has only the **human** raze button
  (`RazeBtn`/`RazeBtnClick`) and does not even reference `CanRaze`/`ExecuteRaze`/`TAIGroup`/`Scorcher`.
  There is **no separate AI module**; the AI raze decision is 100% in AoWEPACK.dpl (mapped above).
- **Remaining confirmable fact (data, not code):** is a vanilla mine's `[+0x58]` razeable byte 0?
  Fastest check: in *unmodded* vanilla, is "Raze" offered/possible on an enemy mine? Expected: no. The
  user's raze project (enabling structure razing) is what makes the modded AI reach the mine-raze branch;
  **v4** (AI CanRaze veto = city-only) re-suppresses it for non-cities.

## 7b. The two-gate synthesis (why the mod deranged AI razing WITHOUT touching the AI code)

Vanilla non-city AI razing is governed by TWO complementary gates:

1. **Want-gate** (`ValidateRazeStructure`, §4): fires when the group is locally OUTNUMBERED
   (`own×2 < enemy players` in r15). By construction it selects **weak/desperate groups** — a strong
   group almost never trips it, a weak group near any front trips it easily.
2. **Feasibility-gate** (vanilla `CanRaze`, §5): predictor-sims the razer against the structure's
   template raze-militia and REFUSES when the militia would win — i.e. it rejects **weak groups**.

The gates select nearly disjoint sets: the want-gate passes mostly weak groups, the feasibility-gate
then vetoes exactly those. Vanilla intersection (desperate AND still able to beat ~8 militia) ≈ never
→ players essentially never saw an AI mine raze. Neither gate alone explains vanilla; the SYSTEM does.

Why the intersection is empty in PRACTICE (user's synthesis, 2026-07-12, code-corroborated):
- **The selector budgets force to the target**: `GetRequiredStrength`/`GetRequiredCombatPredictorSuperiority`
  (selector state 0) size the group against the target's *actual defenders*. Mines are cheap targets →
  captured by small groups; cities need conquest stacks. So the units standing on a just-taken mine are
  systematically the ones least able to beat its raze-militia.
- **Raze is evaluated post-capture only**, so the question only arises for a group that just took the
  structure — and a militia-beating stack is, by the same 15-hex tally, usually the dominant local force
  (it sits in the "own" bucket), so the want-gate can't fire for it. The selector's own force-budgeting
  parks groups in the dead zone between the two gates.
- **Scorcher cities are not a lower bar — they are NO bar**: mode bit 0x02 short-circuits
  `ValidateRazeCity` for hostile-race cities entirely (regional dominance never consulted). The 1.5×
  city factor Scorcher also writes (+0x28) is effectively dead code behind that flag. Non-Scorcher AIs
  face the same ×2.0 desperation test for cities as for structures → "other AIs razed very little".
- Residual vanilla looseness: the vanilla hex-gate allowed sim STALLS (result 2 ∉ veto set {3,4,6}) —
  in principle a desperate lone flyer could raze a mine via the melee-vs-flyer zeroing bug; rare only
  because scout/raid-type groups never attach the raze plugin. v6's `result==4 && sup<50` closes this,
  making v6 strictly rarer than vanilla's letter.

The mod (raze-as-real-battle) deliberately replaced gate 2 with "forces present → attempt; the real
battle decides" — correct philosophy for humans, and necessary because (a) that same predictor sim was
the source of the original Great-Eagle over-permissive bug, and (b) the post-battle re-entry must not
be re-vetoed. Unknown at the time: gate 2 was doing double duty as the ABSORBER of the AI's constant
stream of desperate want-gate hits. With it gone, every desperate weak group actually marched into a
manifested-militia battle → the observed suicide loops. The mod's own features then amplified
visibility: a lost raze leaves a Guard garrison + flips ownership → recapture → the SAME want re-fires
on the same mine (vanilla resolved each want once, silently). v2/v3 failed to rebuild gate 2 from the
simfly-rescoped predictor (it measures different economics; v2 routed stalls as passes, v3's strength
gate passed strong groups which then SUCCEEDED at razing). v4/v5 (AI razes cities only) is stricter
than vanilla's letter — it also blocks the vanishingly-rare "strong but locally doomed" scorched-earth
mine raze vanilla theoretically allowed — but identical to vanilla as ever actually observed, per the
user's explicit preference (no AI non-city razes at all).

**v6 (2026-07-12, APPLIED, awaiting in-game confirmation)** — after the full decode above, the user
chose to restore the *designed* scorched-earth behavior with a corrected feasibility gate. The
non-city AI branch of `cave_forcefail` now allows the raze IFF **all three** hold:
1. `ValidateRazeStructure` fired upstream (unchanged vanilla want-gate: locally doomed to a PLAYER,
   independents invisible) — reaching CanRaze at all implies this;
2. the simfly'd CanRaze predictor says the razer **decisively wins**: result byte **== 4** (militia
   wiped; result-2 stalls are what sank v2);
3. the win is **cheap**: `GetSuperiority` @0x5572B798 **< 50** (for result 4 it equals the razer's
   predicted loss-strength %; strength proxies are what sank v3).
City path (vanilla veto, Scorcher intact) and human path (forces-present) unchanged; the v5
structural re-entry test and razeok heal unchanged. Since razeroster, the sim fights the same
seed-stable roster the real battle manifests that day, so predicted wins convert. Rare by design —
test via an engineered editor scenario (small but militia-beating AI stack on an enemy mine, large
hostile-player army within 15 hexes → its turn should end with the mine razed).

**First engineered test (2026-07-12): NO raze — analysis.** Setup: 48 hostile dragons/astras (≫2×
the AI's total force) near the AI; the AI captured a guarded mine with 2 basilisks + avatar (+5
warriors), **all at red HP after the capture battle** (screenshot). Candidate causes, in likelihood
order:
- **(A) One-shot-at-weakest-moment timing (probably the design working):** the raze question is asked
  exactly ONCE, in `RazeControl.Process` immediately after the capture — the plugin then calls `Done`
  and the now-owned mine can never become a target again. So the sim (which fights with CURRENT HP)
  pits a battle-worn stack against a FRESH ≤8-unit militia roster → predicted result 3 (razer loses)
  or a pyrrhic result 4 with ≥50% losses → blocked by the v6 margin (a red-HP stack likely fails even
  the plain result==4 bar, and vanilla would equally have vetoed a predicted loss). NOTE: this same
  timing is yet another reason vanilla mine-razes ~never manifested — the evaluation moment is
  systematically the moment of maximum damage.
- **(B) Assignment gap:** raze is only evaluated when the captured structure was the group's ASSIGNED
  selector target (status-5 path). An incidental capture en route to another target never attaches
  `RazeControl` — the question is never asked.
- **(C) Want-gate miss:** dragons farther than 15 hexes from the MINE itself, or not hostile/neutral
  relation to the AI (allied strength counts as nothing).
**Isolating test:** same scenario but an UNDEFENDED mine (strip its guards) so the stack arrives at
full HP. Razes → (A) confirmed (then decide: keep strict margin, or relax sup<50 → sup<100
(vanilla's own result-4 bar) / drop to plain result==4). Still no raze → suspect (B)/(C).

## 8. Relation to the mod (why it razed mines — superseded by §7b's fuller picture)

The mod changed, on the AI raze path: `simfly` (rescoped the CanRaze predictor to fast-combat
economics), `cave_forcefail` (CanRaze verdict), and Stage-8 (repointed `ExecuteRaze` slot 0x1B0 for the
six structure classes to the real-combat cave). It did **not** touch `GetRazeable`, the selector, or
`ValidateRazeStructure`. The user reports the modded AI *attempts* mine razes and *loses* them ("only
attempt a raze when they would lose"), consistent with `simfly` mis-evaluating the CanRaze predictor so
it no longer vetoes hopeless mine razes. **v4** (AI CanRaze veto = city-only, `cave_forcefail` gated by
`IsClass(TCity)`) deterministically restores "AI razes cities only" regardless of which of A/B/C is the
true vanilla mechanism — so it is the correct fix even with the contradiction open.
