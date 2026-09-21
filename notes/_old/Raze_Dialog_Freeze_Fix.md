# Raze combat-type dialog offered to a non-participant → game freeze

**Status: APPLIED, UNTESTED (2026-07-21).** Four fixes in `build_scripts/build_razebattle_tower.py`.
**Revert: ⚠ no longer a safe single revert.** `AoWEPACK.dpl.pre-razedlgfix` was the newest layer when this
was written; it has since been **moved** to `Modding Resources/backups/` (2026-07-29/30, not deleted) and
is now layer **32 of 47** — restoring it would destroy 14 later features. The script has no `--undo` mode;
undo surgically (restore the four patch sites' original bytes, zero the caves) instead. Confirm the live
order with `ls -t AoWEPACK.dpl.pre-* "Modding Resources/backups/"AoWEPACK.dpl.pre-* | nl`.

Companion to `Raze_CombatPredictor_Analysis.md` (the feature) and `AI_Raze_v4_Leak_Analysis.md`
(the earlier `razeok` leak). Module `AoWEPACK.dpl`, Ghidra base `0x55700000`, Delphi 3 register
convention (EAX, EDX, ECX; callee-cleans `ret N`).

---

## 1. Symptom

In-game 2026-07-21: an AI razed one of its own cities. The **local human**, who was not a
participant, was shown the **quick-vs-tactical combat-type dialog** for that battle. Accepting it
froze the game — screen stopped, **sound still running** (i.e. an idle wait, not an access
violation). Had to kill `AoW.exe`.

Environment that mattered, and that no prior raze testing had covered:

- **Simultaneous turns** (not classic).
- `Combat Resolve Mode = 0` (**Ask**) in `HKCU\Software\Triumph Studios\Age of Wonders\General`.
- One human slot; all other players AI.
- Recent testing had let the AI capture many cities, so the **AI-razes-a-city** path finally ran at
  volume. `Raze_CombatPredictor_Analysis.md` had left exactly that as an unticked item
  ("worth a quick in-game check: AI razing a hostile city → fast battle").

## 2. What was NOT the cause (checked, so it is not re-checked)

- **The force-FAST gate is correct.** `cave_razemode @0x5580D100` tests
  `map[+0xA5] == razePlayer && GetPlayers(razePlayer)[+0xA7] == 0`, and both halves were verified
  against the installed bytes:
  - `map[+0xA5]` = **seated/local player**, sole writer `TAbstractAoWHSMap.SetSeatedPlayer
    @0x55772A78`; `map[+0xA4]` is the separate *current* player (`SetCurrentPlayer @0x55772A80`).
    `TSimultaniousPlayerControl.NewTurn @0x55758F74` only *reads* it — in single player the seat is
    pinned to the local human all game. **Not** the current-turn player.
  - `player[+0xA7]` = **player-type enum**, not "is remote": `0` = local interactive human,
    **`4` = independent**, `1/2/3/6/7` = AI levels. Independent proof:
    `TSetupControl.RemoveIndependentPlayers @0x557E0AB4` tests `[+0xA7]==4`; player 0 gets 4 at
    `0x557546F2` and again on every load at `0x557535ED`. Max players = 12 (`mov bl,0xC` @0x557546C3).
  - ⇒ **A player-0 / independent razer cannot pass the gate** (fails both halves), and neither can
    an AI. `cave_forcefail` has no player-0 blind spot either (type 4 takes its AI branch).
    *Do not re-try the "independents read as human" theory — it is disproved.*
- **No collision from the recent layers.** `aiitemtarget`, `aipickup`, `debuffcache`, `effectroll`,
  `replaylog` are disjoint from the raze caves/hooks/VMT slots (nearest approach ~8 KB).
- Rebellion and loot **cannot** reach the ask branch: `cave_rebellion` passes `owner|0x50` and
  `cave_lootbattle` `owner|0x90`, so `choice = ((x|0x10)>>4)&3 ∈ {1,3}` — never 0.

## 3. Root cause

Only four sites in the live DLL can raise a `TCombatTypeRequestEventLog` (classref `0x557172AC`):

| # | Create @ | Function | Guard |
|---|---|---|---|
| 1 | `0x55749367` | `TArmyCombatMoveTE.SetupCombat` | seat == chooser — safe |
| 2 | `0x55749604` | `TArmyCombatMoveTE.SetupCombat` | **no seated check**; only `PlayerTypeInvolved(combat, bit0)` |
| 3 | `0x557C1EBA` | `TExplorationSite.Search` | **none** — safe in vanilla only because `TStructure.ExecuteAI` is a stub |
| 4 | `0x5580CCBA` | **mod** `cave_towerraze` | `cave_razemode` |

Distribution is map VMT slot `0x12C` = `TAoWHSMap.TriggerExecuteEventLog @0x55776624`. With `CL=1`
it does an **immediate, re-entrant notify with no player filter at all** — vanilla's own final ask
block at `0x557495EE` shows it unfiltered and merely re-centres the camera when
`map[+0xA5] != log[+0x19]`. ⇒ **anything reaching site 4 pops a dialog on the local machine.**
`TCombatTypeRequestEventLog` is also absent from the `GetSimultaneousWindowPopupEvents` xrefs, so the
simultaneous popup mask (239) cannot suppress it.

Since the gate holds, the dialog came from **`cave_typechosen`**, the callback that re-issues the
raze TE after a choice. Three defects, each measured against vanilla's own handler for this exact
event log, `RequestCombatTypeCallBack @0x557489CC`:

1. **DWORD read of a BYTE field.** `mov ecx,[edx+0x18]` — but `+0x18` is a byte and the bytes above
   are live: `+0x19` acting player, `+0x1A` defender, `+0x1B/1C/1D` x/y/l. A **cancel** (type 0)
   with any nonzero player byte above it read back nonzero and was actioned as a pick. Worse,
   `shl edx,4` of a value ≥ 0x100 leaves the low byte clear, so the re-issued TE carried
   **choice 0 = ASK** → cancelling re-raised the dialog forever, minting a token event from inside
   an event-log callback each time. Vanilla: `mov al,[edi+0x18]` @0x557489D6.
2. **Missing request-live check.** Vanilla does `cmp byte [edi+0x24],0; je bail` @0x557489DC before
   anything. The cave never checked it → stale/replayed event logs were actioned.
3. **Player taken from a global that races.** `FLAG_RAZEPLAYER (0x558FA804)` is written by
   `cave_towerraze` on **every** entry, *before* the mode decision. The dialog is asynchronous, so
   any forced-FAST AI / rebellion / loot raze landing between raising it and answering it
   **retargeted the answer to a different player** — which is how a human ended up holding a dialog
   for someone else's raze. Simultaneous turns makes that race routine. The event log already
   carries the acting player at `+0x19` (vanilla reads it @0x55748A20).

**The freeze** is a separate, missing invariant. Vanilla refuses a manual resolve unless
`DefendersAvailable` **and** `TCombat.PlayerTypeInvolved(combat, bit0) @0x5572724C` — a type-0 local
human must actually be a party. `cave_towerraze` called neither, so it could open a modal combat with
nothing the human controls. And a **tactical `CreateCombat` disables the map turn timer**, which under
simultaneous turns is what keeps the world moving ⇒ frozen with sound. Compounding it,
`CreateCombat @0x55778714` raises *"Combat already created"* when `map[+0x120] != 0`, and the cave has
no SEH frame ("(D) DEFERRED"), so an unwind skips `DestroyCombat`/`UnlockGameOverEvent` and leaves
`map[+0x120]` non-null for the session — after which **every** later battle raises too.

## 4. The fix (as applied)

`cave_typechosen` 115 → **123 B** (budget 128 to `cave_lossgarrison`);
`cave_towerraze` 1101 → **1136 B** (budget 1152 to `cave_canraze`).

1. `cmp byte [edx+0x24],0 ; jz done` — honour the request-live flag first.
2. `movzx ecx, byte [edx+0x18]` — byte read; a cancel is now a cancel.
3. `movzx ebp, byte [edx+0x19]` at entry, `mov eax,ebp` at pack time — player from the event log,
   never from `FLAG_RAZEPLAYER`. (EBP is push/pop'd as scratch; vanilla's handler does the same
   @0x557489FC, and the cave has no EBP-relative locals.)
4. At `L3_modeset`, before `cave_razemode`: require the army that will actually be `AddArmy`'d as
   side 0 (`[[ebp-0xC]+0x1C]`, player byte `+0x12` — the same byte `Setup` passes as *atkPlayer*) to
   belong to the player named in the raze TE; otherwise force FAST. `cave_findrazer` returns the
   **first** army on the footprint, which for a multi-hex city need not be the razer. Includes a NIL
   screen because this dereferences the army earlier than the original code did.
5. At `L3_modeok`, before `CreateCombat`: `cmp dword [map+0x120],0 ; jne Lepi` — never build a second
   combat. The structure simply stands this time (AI RazeControl is one-shot; a human can re-click).

**Why the gate is placed before `CreateCombat`, not after.** The obvious transcription of vanilla is
`PlayerTypeInvolved(combat, 1)` *after* `AddArmy`/`AddArmyEx`. Rejected: a tactical `CreateCombat`
has by then already disabled the turn timer, so a combat we created and then declined to run modal
would leave the world stopped — the exact symptom being fixed. Checking the army's owner
pre-creation enforces the same invariant strictly earlier.

Also tightened (build-time only, no runtime effect): `cave_forcefail`'s budget assert now checks
`CAVE_VALFIX_RESV = 0x5580D200` (`build_razeeval_timing.py`'s `cave_valfix`) instead of only
`CAVE_SEED_RESV = 0x5580D600`. There were **8 bytes** of clearance; growing `cave_forcefail` would
have silently destroyed the razetiming fix.

## 5. Test plan

1. Load a save with AI cities and let the AI raze one (or reload `Save/autosave.asg` from
   2026-07-21 22:45 if still present). **Expect: no dialog at all** — the AI's raze resolves fast.
2. Raze one of your **own** structures with `Combat Resolve Mode = Ask`: the dialog should still
   appear, **Cancel must cancel** (previously it re-raised forever), and picking either option must
   fight the battle normally.
3. Repeat 2 during simultaneous turns while AI razes happen, to exercise the former race.
4. Confirm rebellion and loot battles still resolve fast and unchanged.

## 6. Open / not done

- **`TExplorationSite.Search @0x557C1EBA` (site 3) is an unguarded landmine**: mode 1, no type/seat/
  participant check, safe in vanilla only because the AI never searches. Any future mod that widens
  AI structure or site interaction re-opens it. Not touched.
- **No SEH frame** on `cave_towerraze` still. Fix 5 removes the main way to *reach* the raise, but a
  throw from anywhere inside `ExecuteRaze` still leaks `map[+0x120]`.
- ~~BSS double-claim~~ — **FIXED 2026-07-22, and it turned out to be a separate game-freezing bug.
  See §7.**
- `build_effectroll.py`'s `CAVE_LIMIT` encloses `build_debuffcache.py`'s caves with 63 B of headroom
  and no assert that would catch an overrun.

---

## 7. A SECOND, UNRELATED FREEZE — BSS flag collision (root cause MEASURED 2026-07-22)

After §4 was applied the user hit another freeze, with a different signature: **"Exception occured
during TArmyCombatMoveTE"**, both stacks deleted, frozen with sound running, reproducible on reload.
It is **not** a raze bug at all.

### How it was found — a file-logging probe, not more static analysis

`build_scripts/build_combatdiag.py` (additive, `--revert`-able) hooks `CreateCombat`,
`DestroyCombat`, `TStructure.Raze` and writes one line per event to `Save\razediag.log`, opened and
**closed per line** so the records survive killing the frozen process. Three static hypotheses died
against the first two logs:

| Hypothesis | Verdict from the log |
|---|---|
| The raze feature is involved | **Dead** — zero `RAZE` records; both combats came from `TArmyCombatMoveTE.ExecuteCombat @0x55749A8F`, none from `cave_towerraze` |
| `map[+0x120]` leaked → "Combat already created" | **Dead** — `map[+0x120]` read `00000000` at *every* `CreateCombat` |
| Freeze is a modal wait | **Dead** — flag `0x202B0` = quick resolve; the hang is inside an auto-resolved battle |

### The actual cause

v2 of the probe also dumped the mod's own BSS flags at each combat start. The dword at `0x558FA800`
read `00001408`, `00001D1D`, `00001D1B` across three battles — decoded as bytes:
`[0x800]=08,[0x801]=14` then `1D,1D` then `1B,1D`. **Those are map coordinates, not flags.**

`build_path_outerring.py` defines `SCRATCH=0x558FA800; SX=SCRATCH+0; SY=SCRATCH+1`, and its
`cave_stash` (hooked in `TAbstractUnit.MovedTo`) writes the move's centre x/y there on **every unit
move** — directly over **simfly's flag (`0x800`)** and **`FLAG_RAZEOK` (`0x801`)**.

Consequence: simfly's `cave_cv` (zeroes the defender damage value) and `cave_retal` (injects melee
retaliation) — scoped by design to the CanRaze / GetCivilStatus **predictor** — were silently active
in **every ordinary battle**. Zero combat values are exactly what makes `SetupRoundTargets` drop a
target, so a fast-combat round pump can reach a state where nothing can act and never terminates.
Two of the three logged battles survived it; the third hung.

This also retroactively falsifies the recorded "simfly cannot leak into the AI (verified
2026-07-11)" claim — that reasoning traced simfly's own code correctly but assumed nothing else
wrote the byte. The AI's direct `TCombatPredictor.Execute` calls were affected all along.

### Fix (applied 2026-07-22, awaiting in-game confirmation)

- `build_simfly.py`: `FLAG` `0x558FA800` → **`0x558FA860`**
- `build_razebattle_tower.py`: `FLAG_RAZEOK` `0x558FA801` → **`0x558FA861`**

`build_path_outerring.py` keeps `0x800/0x801` (it claimed them first, 2026-07-08, and its SX/SY are a
cross-script contract also read by `build_path_sand.py` — moving those would need both scripts
re-applied together). Both victim scripts rewrite their own caves **in place**; `build_simfly.py`
gained multi-prior support and `CAVE_SKIPAVENGER` gained `_own_prior` so the upgrade needs no revert.
Verified by scanning the live DLL: `0x558FA801` has **zero** cave references left, `0x558FA800` is
referenced only by the diagnostic, and the new bytes are referenced from 4 simfly and 7 razebattle
sites.

**Retest:** the diagnostic now watches `0x558FA860`, so field `v4` of every `CCRE` line must read
`00000000`. If it does and the freeze is gone, remove the probe with
`python build_scripts/build_combatdiag.py --revert --apply`.

**Free BSS is now: 0x558FA844–0x558FA85F and 0x558FA862 upward** (to `.idata` at `0x558FB000`).
Claimed: `0x800/0x801` path · `0x801–0x80C` razebattle (minus the moved razeok) · `0x810/0x820/0x82C`
combatlog · `0x840` tierresearch · `0x860/0x861` simfly + razeok · `0x900–0x958` diagnostic.

---

## 8. THE OTHER FREEZE — combat log vs. walls (root cause FOUND 2026-07-22)

A second, unrelated freeze ran through this whole investigation and repeatedly stole the blame from
the raze work. **It is not a raze bug.** Recorded here because the hunt is intertwined with §7 and
because the technique matters more than the fix.

### Symptom
AI-initiated **automatic** battle against the player's **walled city**: accept, both stacks vanish,
game frozen with sound still running, reproducible on reload. Sometimes surfaced instead as
`Exception occured during TArmyCombatMoveTE`.

### Root cause (byte-verified)
`build_combatlog_dll.py`'s worker resolves names via `combatObj+0x4C`, the strategic-unit
back-pointer. That field only exists on **TCombatUnit**. Instance sizes:

| class | size | +0x4C is |
|---|---|---|
| `TCombatObject` | 0x4C | *past the end* |
| `TCombatUnit` | 0x5C | the strategic-unit pointer |
| `TCombatWall` | 0x50 | **its own packed bytes** (`TCombatWall.Setup` writes a setup byte at +0x4C, hitpoints at +0x4D) |

The code only **NIL-checked** it. On a wall that field is a small integer (e.g. `0x1403`), which
passes a nil check; the worker then did `mov ecx,[eax]` and called through it → access violation
inside the combat pump → the TE aborts, both armies (already consumed into the combat) are lost, the
combat never finalizes, and simultaneous turns waits forever.

Reached whenever anything **damages a wall** — i.e. a wall-crushing attacker vs a walled city.
`TStrikeCA.Generate` calls base `TDamageCA.Generate` with the wall as target, whose hooked epilogue
runs the worker. Two false leads worth not repeating:
* **"stale ESI at the epilogue"** — WRONG. `Generate` sets `esi = ecx` (target) once in its prologue
  and is straight-line to one epilogue. The stub's register contract is byte-correct.
* **"wall has a short VMT so the stat call goes wild"** — WRONG. `TCombatWall` overrides
  `GetDefense`/`GetResistance` (+0x70/+0x74 → `0x55725C04`/`0x55725C08`). Those calls are fine.

### Why it only appeared now
The raze rework deliberately makes raze battles **wall-less** (its Stage-5 wall fix), so weeks of
testing never sent a wall through the log. AI fast-combat assaults on walled cities only began when
recent testing let the AI hold cities and field wall-crushers. The raze work *masked* this bug.

### Fix (**CONFIRMED WORKING in-game 2026-07-22**)
User retest: no freeze, and the wall logs as `?` exactly as designed.

Gate the `+0x4C` reads on `IsClass(obj, TCombatUnit)` (`IS_CLASS 0x557010C0`, classref value
`TCOMBATUNIT_VMT 0x55715A94`) before trusting them; non-units fall through to the existing `"?"`
fallback, so the line still logs. Applied at **all four** name lookups — two in the worker, two in
the v9 touch-role worker (each uses its own PIC anchor; `cu()` is computed per-anchor).

**Relocated `CAVE 0x5580E440 → 0x55811000`.** The old comment claimed "free to ~0x5580F400" but
`build_tierresearch_dll.py` had placed `cave_grant` at `0x5580ED80`, leaving only 2368 B — and the
image was already **2372 B**, overlapping its neighbour's first 4 bytes. That 4-byte overlap is why
verify said *"cave zone not free"* forever and the feature had become **un-reappliable (orphaned)**.
With the gate it needs 2446 B, so applying in place would have destroyed `cave_grant`. Legacy zone
vacated via `--vacate` (bounded strictly below `LEGACY_LIMIT`); `cave_grant` verified intact.

Also fixed: image now trims trailing alignment padding (it was *claiming* bytes it never used);
"cave zone not free" now reports how many bytes differ, where, and the differing regions; backup
suffix is `.pre-clogtypegate` so each change gets a real one-layer backup.

### Still open
* `Blt Error` — **root cause found and CONFIRMED FIXED 2026-07-22, but it was NOT this feature.**
  It was `build_replaylog.py` making the same ungated `+0x4C` read on a wall. See §9 below and
  `Blt_Error_Wall_Damage.md`. The theory once recorded here — "it is our cloned log window failing to
  blit, and FastCombatWin aborts the action it was animating, hence no damage" — was **wrong on every
  clause** and has been deleted; the blit loop does not even execute on that path. Damage was landing
  all along (the user established this directly: the wall broke while the error still fired).
  Two facts from that dead end are still worth keeping:
  - `AoWE..TFoo` exports **are** the VMT — reach them with `lea`, not `mov edx,[addr]`. Verified:
    `[0x5571D4BC]` is `0x55703074`, not a VMT.
  - ⚠ `TFastCombatUnit` **derives from** `TCombatUnit`, so a `+0x4C` type gate does *not* exclude it.
    Excluding fast-combat units needs its own explicit check.
* The script header still says **"HOOKS (3)"**; there are **seven**.
* The script can now REVISE ITS OWN CAVE in place: a non-stock `TDamageCA.Generate` epilogue proves
  the cave is ours, so both the image and the hook sites accept our previous build as a prior.
  Without that, every revision moved the internal stub addresses and the verify refused — the
  mechanism by which this feature originally became an orphan.

### Regression introduced and fixed the same day: the `+0x24` contract
§4's `cave_typechosen` hardening added vanilla's request-live check `cmp byte [eventlog+0x24],0`.
The analysis it came from said vanilla *"checks +0x24, which the mod never sets **or** checks"* --
acting on the "never checks" half while missing "never sets" meant the check read 0 every time
and **every raze choice silently bailed**: dialog appears, you pick, nothing happens.
FIXED by making our event log honour the contract -- `mov byte [esi+0x24],1` in `cave_towerraze`'s
`L3_askdialog`, right after the existing `+0x19`/`+0x1A` writes (`+0x19` *was* already set, which
is why the player-from-eventlog half worked). cave_towerraze 1136 -> 1140 B.
**LESSON: before adopting a caller-side check from vanilla, verify the PRODUCER side sets the
field.** Copying half of a contract is worse than copying none of it.

### Tools built for this (reusable)
* `re_tools/bisect_dll.py` — binary-searches the `.pre-*` backup stack. 33 layers → 6 tests. Parks the
  current DLL first and refuses to touch anything until it has.
* `re_tools/hang_stack.py` — reads a frozen game's EIP + call frames out-of-band (Wow64 contexts), no
  debugger needed. **Detect stalls PER-THREAD**: the first version required every thread to freeze at
  once, which never happens when the symptom is "sound still running".
* `build_scripts/build_touchlog_gate.py` — toggles any subset of the seven combat-log hooks without
  rebuilding the cave. Addresses are post-relocation; re-read them if the cave moves again.

---

## 9. THE `Blt Error` — `build_replaylog.py` read `+0x4C` off a wall (**CONFIRMED FIXED 2026-07-22**)

Full write-up: **`Blt_Error_Wall_Damage.md`**. Summary:

`build_replaylog.py`'s cave (`0x5580F180`, hooked at `0x55729D97` in `TDamageCA.GenerateEx`) fetched
combatant names via `[obj+0x4C]` → strategic unit → `GetName`. It guarded that pointer for **NIL but
not for TYPE**. `+0x4C` is a `TCombatUnit`-only field; `TCombatWall` reuses the offset for packed
bytes, so on a wall the read returns nonzero garbage, passes `test eax,eax`, and `mov ecx,[eax]`
access-violates. **Every hit on a wall.**

Fixed with the same `System.@IsClass` type gate already used in `build_combatlog_dll.py` — applied
BEFORE the `+0x4C` read, `"?"` fallback otherwise. Cave rewritten in place (825 B); no revert.

**This is the same defect as §8, in a second, independent cave.** §8 fixed `build_combatlog_dll.py`;
nobody checked whether any other cave used the same idiom. Two copies existed.

### Why the dialog never said anything useful — two nested catch-alls
1. `TFastCombatForm.FCWinDrawSurface` (AoW.exe `0x435E7C`) wraps its body in `try..except`; the arm at
   `0x435F26` does `Exception.Create('Exception during FastCombatWin.DrawSurface')` + `@RaiseExcept`,
   **discarding the original exception**.
2. That generic replacement propagates into aowInt's draw routine, whose try (`0x59807BC6..0x59807D48`)
   has an except arm at `0x59807D55` that MessageBoxes a **fixed literal**, `"Blt Error"`, with caption
   `"Error - " + component.Name`. Siblings in the same routine: `"Verify Surface Error"`, `"Draw Error"`,
   `"SB Draw Events Error"`, `"Exception during DrawSurface"`.

So the visible text named neither the fault nor the failing component. **In this codebase, an error
string next to a MessageBox is usually a label in an `except` arm, not a description — never reason
about what it means; probe the handler.**

### Why the A/B testing pointed the wrong way — READ THIS BEFORE TRUSTING A GATE TOOL
The user said from the start that this began with the combat-log work. An A/B run reported
"**ALL SEVEN DLL hooks off → error persists**", which was written up as "the DLL half is EXONERATED",
and three mechanism theories were then built on that.

The A/B was measuring the wrong thing. `build_touchlog_gate.py` knows only the seven hooks owned by
`build_combatlog_dll.py`. `build_replaylog.py` is a **separate feature with its own hook**, and it
stayed live through every isolation run. The exoneration was an artefact of the gate tool's inventory.

**LESSON: a gate tool's negative result is only as good as its inventory.** Derive "what is patched in
this binary" from the binary (or from the full `build_scripts/` set), not from one script's notion of
its own hooks. And **when an A/B contradicts the user's direct observation of when a symptom appeared,
suspect the test's scope before discarding the observation.**

### Disproven theories — do not re-derive
* **`HitPointsToHitPcnt` negative-clamp / inverted clip rect.** `@0x5575A804` really does clamp only
  the top (`cmp eax,0x64/jle/mov eax,0x64`; negatives pass through), and `ShowHitPcnt @0x5575A830`
  really does build the rect's right edge from it. Tempting, and it is why `build_hpbar_clamp.py`
  exists — but it was **never the cause**: the repro is a d6 vs a 25 HP wall, which cannot reach
  negative HP, and the error fires on *any* hit, not only overkill. `TCombatWall.Show`/`ShowHitPcnt`
  are not even called in these battles (zero `HITP` records across 77 combats on the razediag probe).
  `build_hpbar_clamp.py` is **reverted / at stock** — leave it that way unless negative-HP display is
  independently demonstrated.
* **Log-window geometry / drain starvation / fast-combat visibility.** All three were built on the bad
  attribution above. `live_ui.py` (run while the modal dialog held the game still) showed both windows
  in bounds and not overlapping, killing the geometry theory.
* **"It is our cloned log window failing to blit."** No — the blit loop never even runs on this path
  (`[self+0xE4]` BltRect count is 0). The failing statement is the virtual call at `0x59807D3D`.

### Still open
* The combat-log DLL **fast-combat gate** was justified by one of the failed theories, fixed nothing,
  and is incomplete anyway: `build_effectroll.py` writes to the ring directly, bypassing the worker
  (measured live: `wrIdx=20 rdIdx=4` with effect-roll lines pending during a fast combat). Recommend
  reverting unless quieter auto-battles are wanted for their own sake.
* **Drain starvation is real and confirmed** (`wrIdx=20 rdIdx=4` live): `MapWindowUpdate` does not
  tick while FCWin animates, so ring lines pile up and are delivered in a burst afterwards. Not
  currently harmful, but it is why the ring must never be assumed drained.
* Audit of the remaining ungated `+0x4C` sites (`build_ranged_slayers.py`, `build_debuffcache.py`,
  `build_simfly.py`) — see `Blt_Error_Wall_Damage.md` §"Sibling risk".
