# City flagpole baubles lag the upgrade level — root cause

**Status: ✅ CONFIRMED WORKING (2026-08-29)** — validated in-game by the user. Diagnosed by static
analysis of the live `AoWEPACK.dpl` plus the pristine vanilla image
in Ghidra. The two are byte-identical everywhere this touches, so this is a **vanilla defect**, not
something Ziggurat introduced.

| | |
|---|---|
| build script | `Modding Resources/build_scripts/build_cityflag.py` |
| target binary | `AoWEPACK.dpl` (shared by `AoW.exe`, `AoWCompat.exe`, `AoWDevEd.exe`) |
| backup | `AoWEPACK.dpl.pre-cityflag` |
| revert | `python build_scripts/build_cityflag.py --undo` (surgical; touches no backup) |
| cave | `0x55819000`, 0x40 bytes reserved, 45 used |

## Symptom

The golden spheres ("baubles") on a city's flagpole show the *old* upgrade level after the city
finishes an upgrade. Sometimes they are right, sometimes they lag, with no obvious pattern.

## One-line cause

**The upgrade-completion path bumps the city's level but never recomputes the cached flag ID.**
Fortify does call the refresh; Upgrade does not.

## The data path

| offset (TCity) | meaning |
|---|---|
| `+0x08` | `TCityResource*` |
| `+0x0C` | structure state; bit 2 (`&4`) set means draw no flag |
| `+0x30` | owner player index (`<= 0` means independent) |
| `+0x44` | city flags: bit0 = domain contested, bit1 = under construction |
| `+0x45` | race |
| `+0x4C` | wall type |
| `+0x4D` | **upgrade level, 1..4** — saved (ReadWrite property id `0x10`) |
| `+0x50` | `TCityProductionControl*` |
| `+0x54` | **cached flag ID** — *not* saved |

`+0x54` bit layout: `bits 0-4` = race index (selects the banner art), `bit 5 (0x20)` = independent,
`bits 6-7` = **upgradeLevel - 1** (the bauble count). `0x3F` = draw nothing.

**Producer — `City.TCity.UpdateFlagID @0x557AC8B0`** (VMT slot `+0x1FC`, VMT base `0x557A73F0`):

```
[+0x54] = [player+0xA5] + (([+0x4D] - 1) << 6)   ; owned
[+0x54] = 0x20          + (([+0x4D] - 1) << 6)   ; independent
[+0x54] = 0x3F                                   ; hidden / contested / still building
```

**Consumer — `City.TCity.Show @0x557ACA88`**, which reads `[+0x54]` fresh on every map draw and
hands it to `AoWE.TFlagControl.ShowStructureFlag @0x5575A34C`. That function does
`ImageLib.Get(lib, flagID >> 6)` for the pole-with-baubles sprite, and uses `flagID & 0x1F` and
`& 0x20` for the banner. Cities whose resource byte `[cityres+0x46] < 2` go to
`TFlagControl.ShowFlag @0x5575A1E8` instead, which hard-codes pole image 4 and ignores the level —
that is the 1-hex cities, which can only ever be level 1, so the bug is invisible on them.

`TCity.Show` and `TPlayerStructure.Show @0x55760F94` are the **only** two callers of the flag
drawing routines. There is no second cache and no second reader — fixing `+0x54` fixes the display.

## The defect

`City.TCityProductionControl.NewTurn @0x557A82A8` dispatches on the finished production
(switch table at `0x557A8322`: case 0/default `0x557A8880`, 1 `0x557A833A`, **2 = Upgrade
`0x557A8346`**, 3 = Fortify `0x557A8475`, 4 = Migrate `0x557A870C`, 5 = Loot `0x557A85B9`).

Case 2, verified on the **live** DLL:

```
557A8346  mov  eax, edi
557A8348  call 0x5575CB6C           ; TProductionControl.BeginUpdate
557A834D  mov  eax, [edi+0x28]      ; the TCity
557A8350  mov  dl, [eax+0x4D]
557A8353  inc  edx
557A8354  call 0x557AC75C           ; TCity.SetUpgradeLevel  <-- level changes here
...                                 ; race-relation bump, ProductionDone, event log
557A846B  call 0x5575CB70           ; TProductionControl.EndUpdate
557A8470  jmp  0x557A8880
```

- `TCity.SetUpgradeLevel @0x557AC75C` writes `[+0x4D]` (at `0x557AC784`) and rebuilds the unit
  production list. Its only calls are `GetSize`, `GetRaceResource`, `TIntegerList.Get`,
  `TUnitProductionList.IndexOf/Add`, `UnitLevelToCityLevel`, `TList.Sort` — **no image or flag
  refresh**.
- Case 2 itself never calls `UpdateImages` or the `+0x1FC` slot.
- `EndUpdate` goes to `TCityProductionControl.Update @0x557A8D4C` to `TCity.Update @0x557A96D8` to
  `UpdateIncome` + `TStructure.Update`. No refresh in that chain either.

**Contrast case 3 (Fortify), same function:** `557A854E  call 0x557AC494 ; TCity.UpdateImages`.
That is exactly the missing call, and it is why new walls appear the instant they finish while new
baubles do not. `TCity.UpdateImages @0x557AC494` ends with `call [vmt+0x1FC]` (at `0x557AC616`), so
it always refreshes the flag ID.

## Why it looks intermittent

`+0x54` is **not persisted**: `TCity.ReadWrite @0x557ACBCC` writes `+0x48`, `+0x45`, `+0x4C`,
`+0x4D`, `+0x50`, `+0x44`, `+0x74`, `+0x58` — not `+0x54`. It is rebuilt from scratch by
`TCity.Activate @0x557AC9C0` -> `UpdateImages` -> `UpdateFlagID` on every map load. **Saving and
reloading therefore always corrects the flag.**

Within a session it also catches up whenever something *else* happens to call the producer. The
complete set of callers of slot `+0x1FC` in the DLL:

| caller | fires when |
|---|---|
| `TCity.UpdateImages @0x557AC494` | via SetRazed / SetWallType / NewDay / TerrainChanged / SetRace / Activate / MsgProc / Fortify-done |
| `TPlayerStructure.SetPlayer @0x55760DDF` | city changes owner (capture, join, migration to you) — early-outs if the owner is unchanged |
| `TPlayerStructure.Activate @0x557613A3` | map load |
| `TPlayerStructure.MsgProc @0x5576153A` | broadcast `0x20020005` (player list changed / player eliminated) |
| `TCity.UpdatePlayer @0x557AAAFA, 0x557AAB44` | only when the domain-contested bit `[+0x44]&1` **toggles**; reached from ArmyPlaced / ArmyRemoved / ArmyChanged / FinalizeCombat / BuildingDone |

None of those correlates with upgrading, which is why it reads as random from the player's seat.

**Prediction worth testing in-game (cheap):** upgrade a 2+-hex city — the baubles should *not*
change. Save and reload — they appear. A captured enemy city always looks right, because
`SetPlayer` refreshes it.

## Second, rarer instance of the same defect

`TCity.BuildingDone @0x557A97D8` (rebuilding a razed city) writes `[+0x4D] = 1` and `[+0x4C] = 0`
**directly**, then calls `SetRace([player+0xA5])`. `TCity.SetRace @0x557AC990` early-outs when the
race is unchanged, so rebuilding with a builder of the city's existing race skips `UpdateImages`
entirely; the inherited `TPlayerStructure.BuildingDone @0x557608F4` only reaches `UpdatePlayer`,
which refreshes conditionally. A rebuilt level-1 city can therefore keep the old *high* bauble count.

## Patch surface — clean

- All of this is in `AoWEPACK.dpl`, shared by `AoW.exe`, `AoWCompat.exe` and `AoWDevEd.exe`. One
  DLL patch covers everything; no per-exe work.
- `UpdateFlagID`, `SetUpgradeLevel`, `UpdateImages` and case 2's body are **byte-identical to
  pristine** in the live DLL. A grep over `build_scripts/` finds no script referencing
  `0x557AC8B0`, `0x557AC75C`, `0x557AC494`, `0x557A8346` or `0x557A8354`.
- The only live patches inside `NewTurn` are Ziggurat's hand edit at `0x557A8380`
  (race relation `+5` -> `+0xF`, inside case 2 but well clear of the call being retargeted),
  `build_razebattle_tower.py` at `0x557A85B9` (case 5) and `build_loot_multiplier.py` at
  `0x557A8600` / `0x557A86BD` (case 5).

## The fix as applied — retarget one call per site, no displacement

Each site is an existing 5-byte `call rel32`; only the 4-byte rel32 changes, repointed at a thunk
that does the original call and then refreshes the images. Live bytes after `--apply`:

| site | was | now | thunk |
|---|---|---|---|
| `0x557A8354` (upgrade completes) | `E8 03 44 00 00` → `SetUpgradeLevel` | `E8 A7 0C 07 00` → `0x55819000` | `push eax / call 0x557AC75C / pop eax / call 0x557AC494 / ret` |
| `0x557A980B` (razed city rebuilt) | `E8 E4 70 FB FF` → `TPlayerStructure.BuildingDone` | `E8 10 F8 06 00` → `0x55819020` | `push eax / call 0x557608F4 / pop eax / call 0x557AC494 / ret` |

Why this shape:

- **No displaced instructions**, so no hook-resume hazard and nothing to replay.
- **rel32 + register ops only** ⇒ position-independent, which the `.dpl` requires (it rebases).
  Verified: no `.reloc` entry falls inside `0x557A8355+4`, `0x557A980C+4`, or the cave, so the
  loader cannot corrupt either rel32.
- **Register contract.** Both wrapped callees are Delphi `register` procedures taking Self in EAX
  with no stack arguments and a plain `ret` (`SetUpgradeLevel` @`0x557AC898`, `UpdateImages`
  @`0x557AC622`), so `push eax` / `pop eax` around them is balanced. `UpdateImages` needs only EAX.
  At site 1 the caller reloads EAX at `0x557A8359` (`mov eax, edi`) and EBX/ESI/EDI are
  callee-saved; at site 2 the next instruction is `pop ebx; ret`.
- **Ordering at site 2:** `UpdateImages` runs *after* the inherited `BuildingDone`, so
  `UpdatePlayer` has already settled `[+0x44]` before the flag ID is recomputed from it.
- Calling `UpdateImages` inside `BeginUpdate`/`EndUpdate` at site 1 is demonstrated safe by vanilla
  itself — Fortify does exactly that, ten instructions later in the same function.

Verified after apply: both thunks disassemble with correct symbol resolution on the live DLL, file
size unchanged, zeros intact past the cave, and a `--undo` round-trip leaves the file **0 bytes
different** from the pre-apply state, with both call sites byte-equal to
`AoWEPACK_original_backup.dpl`.

## In-game result

Confirmed working 2026-08-29: the baubles now step up the moment an upgrade completes, with no
save/reload.

## The reusable part — wrapper-thunk on an existing `call rel32`

Worth stealing whenever the fix is "this call site should also do X". Instead of the usual
`E9 jmp` hook, **retarget the rel32 of a `call` that is already there** at a thunk that performs
the original call and then X:

```
cave:  push eax / call <original target> / pop eax / call <the addition> / ret
```

Compared with a displacement hook this gives you: no displaced instructions to replay, no
resume-address hazard, a 4-byte footprint in the host function, no `.reloc` exposure (a `call`
rel32 is never relocated — but scan anyway), and an `--undo` that is literally "write the old rel32
back and zero the cave". It is position-independent for free. Preconditions: the callee must take
its arguments in registers with a plain `ret` (no `ret imm16`), and you must own the *call site*,
not the callee — every other caller of that function is untouched, which is usually exactly what
you want.
