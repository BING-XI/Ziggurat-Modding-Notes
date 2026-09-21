# Party placer → random army generator (AoWDevEd.exe)

Rework of the editor's **Party** tool: instead of placing an empty stack the mapmaker must fill by
hand, it places a randomly-generated stack of a chosen strength drawn from a chosen set of races.

**Status: CONFIRMED WORKING (2026-07-28)** — user validated in the editor ("all working"), then
requested the Medium/Large tier retune below, which was re-verified by automated live placement
(sampled across several land hexes per tier). Generator, placement hook and configuration dialog all
applied; also verified live: all three strengths, the race mask, the behaviour dropdown, the
no-races default, and the settings round-trip.

Clicking the **Party** button now opens a "Random Party Generator" dialog (strength, behaviour,
eligible races); every party placed afterwards uses those settings, so you configure once and place
many. Cancel leaves the previous settings untouched.

**No races are ticked by default**, and a zero race mask makes `fill_army` early-out — so out of
the box the Party tool behaves exactly as it always did (an empty stack to fill by hand) and only
starts generating once the mapmaker opts in by ticking races. Ticking nothing is therefore a
legitimate choice and is stored as such (there is deliberately no "empty selection is ignored"
guard). The behaviour byte is still applied to the empty stack.
Build script `build_scripts/build_party_random.py`; backup `AoWDevEd.exe.pre-partyrnd`; section
`.pty`.

Strength table (user spec):

| Strength | Composition |
|---|---|
| Weak | 3–4 × level 1 |
| Medium | 3–5 × level 1, 2 × level 2 |
| Large | 4 × level 1, 2–3 × level 2, 1 × level 3 |

Encoded in `g_spec` as three `(level, base count, random span)` byte triples per tier — the actual
count is `base + RandInt(span)`, so `span` 1 means a fixed count and any entry can be given a
spread without touching the cave. A zero count ends a tier's list. (Tuned 2026-07-28 on user
request: Medium's level-1 count and Large's level-2 count gained spreads; the earlier
hard-coded "Weak gets +RandInt(2)" special case was replaced by this general mechanism.)

## Reverse-engineering results (all verified against this build)

### Where a party is placed

`TMainForm.ArmyBtnClick` @ **0x42B69C** (the toolbar `ArmyBtn` / `uArmyBtn`, hint "Party") only
enters place mode: `THSLibrary.CreateHS(lib=[form+0x30C], …, type 0x28)` then
`THSMEdit.SelectPlaceHS(ctrl=[form+0x22C], …)`.

The actual placement is handled by the **editor-side** class `TArmyPlaceControl`
(VMT **0x419CD4**, reached from `VMT_TArmyHSEditor+0x6C`). It overrides exactly one method —
its `MsgProc` @ **0x41A35C** — which on message `0x10005`:

1. `HSEngine.HPtoHX` → hex coords; `TMapContainer.GetField(map=[[0x43289C]]+0x10, x, y, level)`
2. rejects terrain byte `[field+0x14] == 0xF`
3. queries the field for an existing army: `[field].VMT+0x80` with msg `0x20217`
4. if none: `TArmyHS.Create(classref [0x4328A8], 1, 0)` then
   `THSMap.PlaceHX(map, armyHS, level, x, y)` (fails → `Free`, esi := 0)
5. `esi` (the army HS) → `[esi].VMT+0x38` gives its HS-editor, then `[eax+0x50]` =
   `TArmyHSEditor.Edit` @ 0x419D3C → opens **TArmyEditForm** ("Army Properties") for manual filling.

**`TArmyHS + 0x1C` = the `TArmy`** (set in `TArmyHS.Create` @ 0x557908BC).

### The engine's own random-fill helpers (AoWEPACK)

- `AoWE.FillWithRandomUnits` @ **0x5575B160** —
  `(EAX=candidate TIntegerList, EDX=TArmy, ECX=maxLevel, [ebp+8]=unit-TYPE set, [ebp+0xC]=value
  budget) : int`, `ret 8`. Nested filter @ 0x5575B104. Adds random units until the accumulated
  `GetObtainValue` reaches the budget (50 retries, plus a 20-try "best fit to the remaining
  budget" refinement).
- `AoWE.FillWithRandomUnitIndexes` @ 0x5575B358 — same but appends indices to a list.
- Caller example: `TExplorationSite.GenerateDefenders` @ 0x557C1FC0 passes budget = strength × 0x32.

⚠ **The set parameter is a unit-TYPE set, not a race set** — the filter calls `VMT+0x114` =
`TUnit.GetUnitType`, not GetRace. (Tempting misread: the decompiler's `race` naming. Don't
re-derive it as a race filter.) And the helper is **budget-driven, so it cannot produce an exact
per-level count** — which is why this feature does its own selection loop rather than calling it.
The one thing it *is* good for: called with budget = 1 it adds exactly one unit.

### Primitives the generator uses

Everything below is reached from the exe. `AoWDevEd.exe` imports the AoWEPACK global
`AoWE.AoWHSSet` at **IAT 0x432898**, whose slot holds the *runtime address of the variable*; the
preferred VA of that variable is **0x558FA044**, so

```
dll_delta = [0x432898] - 0x558FA044
```

turns **any** AoWEPACK preferred VA into its runtime address — the exe can call any AoWEPACK
function and read any AoWEPACK global without new imports. (Same trick as the VCL30 delta in
`Editor_Modernization_DialogDirs_Toolbar.md`.) Used addresses (preferred VAs, add `dll_delta`):

| Address | Symbol | Convention |
|---|---|---|
| 0x55710C6C | `TUnit` class-reference **global** | `classref = [0x55710C6C + delta]` |
| 0x5577EB28 | `TAbstractUnit.Create` | EAX=classref, DL=1, ECX=0 → EAX=unit |
| 0x55782BE4 | `TUnit.SetUnitResource` | EAX=unit, EDX=resource |
| 0x55785050 | `TUnitResourceList.GetUnitResource` | EAX=list, EDX=index → EAX=res (0 if out of range) |
| 0x55701080 | `System._RandInt` | EAX=range → EAX=0..range-1 |
| 0x55701030 | `System.Randomize` | — |

Objects and fields:

- HSSet object = `[[0x432898]]`; **unit resource list = `[HSSet + 0x5C]`**; race resource list =
  `[HSSet + 0x54]`.
- List element count is `[[list+8]+8]` (the engine-list rule from
  [[aow1-engine-lists-tokens]] — *not* `[list+8]`).
- **TUnit VMT** (class VMT at `[0x55710C6C]` = 0x55710CAC, instance size 0x94):
  `+0x2C` `TAbstractUnit.Release`, `+0xA0` `TUnit.GetUnitLevel`, **`+0xA4` `TUnit.GetRace`**,
  `+0x114` `TUnit.GetUnitType`, `+0x174` `TUnit.GetObtainValue`.
- **TArmy VMT** (0x557130EC, instance size 0x2C): `+0x54` GetCount, `+0xA4` `TArmy.CanAddUnit`,
  `+0xAC` `TArmy.AddUnit`.
  ⚠ TUnit`+0xA4` (GetRace) and TArmy`+0xA4` (CanAddUnit) are *different classes* — an easy
  conflation, and the reason the first pass of this analysis mislabelled the type filter.
- `TAbstractUnit.GetRace` @ 0x5577EDDC and `.GetUnitLevel` @ 0x5577FCC8 are **base stubs**
  (`-1` and `0`); only the TUnit overrides return real values, so these must be called through the
  VMT, never directly.
- Race enumeration (from `RaceBox.TRaceBox.GenerateItems` @ 0x55800868): count from the
  `TRaceList` (`VMT+0x54`), name = `[TRaceResourceList.GetRaceResource(raceResList, i) + 0x24]`
  (AnsiString), and `[TRaceList.GetRace(list,i) + 0x14]` is the per-race *enabled* flag.

### The patch

New section **`.pty`** (R/W/X, so the settings globals live in it) holding the generator plus its
state. Hook: the 8 bytes at **0x41A414** (`85 F6 74 21 6A 00 6A 00` =
`test esi,esi / je 0x41A439 / push 0 / push 0`) become `jmp cave` + 3 × `nop`; the cave
re-implements those four instructions exactly, and between them — when `esi` is non-nil and
`[esi+0x1C]`'s unit count is **0** (i.e. a freshly created, empty party, never an existing stack
the user clicked) — calls the generator on `[esi+0x1C]`, then rejoins at 0x41A41C.

Generator, per (level, count) pair of the selected strength:

1. build a candidate array of unit-resource indices whose `GetUnitLevel` equals the level and
   whose `GetRace` is in the allowed mask, using **one scratch TUnit** re-pointed at each resource
   via `SetUnitResource` (this is how the engine's own filter reads these, so any per-resource
   logic is honoured);
2. `count` times: pick a random candidate, create a TUnit, `SetUnitResource`, and if
   `TArmy.CanAddUnit` then `TArmy.AddUnit`, then `Release` the local reference — the exact
   create/add/release sequence `FillWithRandomUnits` uses;
3. `Release` the scratch unit.

The Army Properties dialog still opens after placement (unchanged), so the owner/player can be set
and the roll tweaked or re-rolled.

Settings live in `.pty` globals: `g_strength` @ VA 0x591000 (default 1 = Medium), `g_racemask`
@ 0x591004 (default **0** = none ticked), `g_behavior` @ 0x591010 (default 2 = Guard), plus
`g_seeded`/`g_ncand`/`g_ctrls`/`g_spec`/`g_cand`.

### Behaviour

The placement hook also writes the chosen behaviour to **`TArmy + 0x24`** — the same byte
`TArmyEditForm.BehaviourComboBoxChange` @ 0x41A288 writes (it does
`[form+0x250].byte[0x24] := Objects[ItemIndex]`, and `[form+0x250]` is the TArmy because it is
what gets passed to `TUnitGrid.SetUnits`). ⚠ **The dropdown order is NOT the id order** — the
combo stores the real id in each item's `Objects[]`. Ids come from each AI-group class's
`Behavior` method (a one-instruction `mov al,imm`):

| Row | Auto | Patrol | Guard | Guard Area | Scout | Refuge | Raid | Suicidal |
|---|---|---|---|---|---|---|---|---|
| id | 0 | 1 | 2 | 3 | 4 | 5 | 6 | **10** |

(Others exist but are not offered by the editor: Fortify 9, Passive 11, Transport 18.)
`TArmy.SetBehavior` @ 0x5578C590 is a *different* thing — it builds a runtime AI group — and is
**not** what the editor uses; don't reach for it.

## The configuration dialog (Stage 2)

`build_scripts/party_dialog.py` holds the control table and the cave; `build_party_random.py`
splices it into `.pty`. Hook: the first 5 bytes of `TMainForm.ArmyBtnClick` @ **0x42B69C**
(`53 8B D8 8B C2` = `push ebx / mov ebx,eax / mov eax,edx`) become `jmp armybtn_hook`; the cave
re-runs those three instructions, calls `show_dialog` with EAX/EDX/ECX preserved, and rejoins at
0x42B6A1.

**The dialog is built at runtime from real VCL controls** — `TCustomForm.CreateNew` plus a
data-driven loop over a 21-entry control table — rather than from a DFM resource. That avoids
inventing a new Delphi form class *and* rebuilding the PE resource tree, and it lets the race
check-boxes take their captions from the loaded mapset (important here: the installed data is the
Ziggurat mod). Everything is reached through a second rebase delta:

```
vcl_delta = [0x432210] - 0x41336300     ; exe IAT slot for Forms.TCustomForm.Create,
                                        ; whose VCL30 rva is 0x36300 (VCL30 base 0x41300000)
```

Recipe (all preferred VAs = 0x41300000 + rva, add `vcl_delta`):

| What | Where |
|---|---|
| `TCustomForm.CreateNew` | rva 0x36490 — EAX=class, DL=1, ECX=owner |
| virtual constructor | **VMT slot 0x24** (`TComponent.Create`) — dispatch per class, so each control gets its own ctor |
| `TControl.SetBounds` | **VMT slot 0x4C**; EDX=Left, ECX=Top, **push Width then Height** (left-to-right), `ret 8` |
| `TControl.SetParent` / `SetTextBuf` / `SetVisible` | rva 0x41F88 / 0x4208C / 0x4200C |
| `TStrings.Add` | **VMT slot 0x34**; the combo's TStrings is at **combo+0x118** |
| checkbox get/set Checked | rva 0x51800 / 0x51820 |
| radio SetChecked | rva 0x51B6C |
| combo SetItemIndex / SetStyle | rva 0x50568 / 0x50760 (csDropDownList = 2) |
| class VMTs (rva) | TForm 0x340EC, TGroupBox 0x49990, TRadioButton 0x4CBD0, TCheckBox 0x4C64C, TComboBox 0x4B878, TButton 0x4BFD0 |

Field shortcuts used instead of calls: `TRadioButton.Checked` is field-backed at **+0x11D**,
`TButton.ModalResult` at **+0x120** (so OK/Cancel need no event handlers at all — set the field and
the modal form closes itself), `TComponent.Tag` at +0x0C, `TControl` FLeft/FTop/FWidth/FHeight at
+0x30/+0x34/+0x38/+0x3C. Captions use **`SetTextBuf` (PChar)**, which sidesteps building Delphi
AnsiStrings; only the combo's `Items.Add` needs real AnsiStrings, and those are emitted as Delphi 3
literals — **`[allocSiz][refCnt=-1][length]` immediately before the characters, pointer at the
characters, NUL-terminated** (verified against shipped literals in AoWEPACK).

⚠ **`TCustomCheckBox.GetChecked` reads the cached field `[self+0x11E]`, not the window.** Driving a
test with `BM_SETCHECK` therefore changes the box on screen but *not* what the cave reads — it cost
one confusing "the race mask came back as all races" result. Automate with `BM_CLICK` (which VCL
processes) or set the field directly.

The race list comes from `[HSSet+0x54]` (`TRaceResourceList`): count via the engine-list rule
`[[list+8]+8]`, name via `TRaceResourceList.GetRaceResource` @ 0x5575A0C4 then `+0x24` (an
AnsiString, and since Delphi AnsiStrings are NUL-terminated it can be handed straight to
`SetTextBuf` as a PChar). Check-boxes beyond the race count are hidden.

### Rewriting the caves without adding a backup layer

`build_party_random.py` **rewrites `.pty` in place** (per the project rule against
"revert and re-apply"): it accepts either pristine hook bytes *or* its own, asserts `.pty` is still
the last section, truncates the file at the section's raw offset and re-appends the new body. Stage
2 was applied this way — `AoWDevEd.exe.pre-partyrnd` is still the single Stage-1 backup and the
layer count did not grow.

### ⚠ `TArmy.CanAddUnit` enforces terrain — an empty result is usually a water hex

`TArmy.CanAddUnit` @ 0x5578E2F8 does more than a stack-size check: when the army is already on the
map it calls `TAbstractUnit.ValidTerrain(unit, field[0x14], field[0x15])` for the field the army
stands on. So a party dropped on **water** silently gets few or no units when the allowed races are
land-only — the generator is working, the engine is refusing the units. This cost a debugging
detour: a Dwarves-only party came out empty on three ocean hexes and full on grass. Keep the
behaviour (it prevents nonsense stacks), but if Stage 2 ever wants to warn the user, that is where
the rejection happens.

## Verified live (automated, 2026-07-28)

Editor driven by winspy/clicker + direct process reads, map `1Scenario/AoW Europe Heaven Games.hsm`
(the map was **not** saved afterwards). Levels/races read straight from each placed unit via
`unit[0x40]` → resource, `res[0x2F]` = level, `res[0x20]` = race:

| Setting | Result |
|---|---|
| Medium, all races | `{lvl1: 4, lvl2: 2}` = 6 units, 5 different races |
| Large, all races | `{lvl1: 4, lvl2: 3, lvl3: 1}` = 8 units |
| Weak, all races | `{lvl1: 4}` (3 + rand(2) rolled 4) |
| Weak, mask 0x40 (Dwarf only) | `{lvl1: 3}`, all race 6 — mask honoured |
| clicking an existing party | untouched (count != 0 → hook skips) |
| dialog round-trip: Large + Orc/Goblin + Raid, OK | globals became `g_strength=2 g_racemask=0x600 g_behavior=6` |
| party placed with those settings | 8 units `{lvl1:4, lvl2:3, lvl3:1}`, races {9,10} only, `TArmy+0x24 = 6` |
| default state (no races ticked), OK, place | 0 units — vanilla empty stack — with `TArmy+0x24 = 2` (Guard) |
| tick Elf only, OK, place | mask became 0x10; 6 units `{lvl1:4, lvl2:2}`, all race 4 |
| retuned Weak × 2 land hexes | `{lvl1:3}`, `{lvl1:4}` — 3–4 spread |
| retuned Medium × 4 land hexes | `{lvl1:5,lvl2:2}`, `{lvl1:4,lvl2:2}`, `{lvl1:5,lvl2:2}`, `{lvl1:3,lvl2:2}` — 3–5 spread, level 2 fixed |
| retuned Large × 4 land hexes | `{lvl1:4,lvl2:2,lvl3:1}` ×2 and `{lvl1:4,lvl2:3,lvl3:1}` ×2 — 2–3 spread at level 2 |

Side effect worth knowing: because the hook fills any party whose unit count is **0**, clicking the
Party tool on an *empty* stack (one placed with no races ticked, or one emptied by hand) re-rolls
it. Only non-empty stacks are left alone.

Also confirmed from the live data: the installed (Ziggurat) set has **286 unit resources**, races
**0..11** are the twelve playable races (Human, Azrac, Lizardman, Frostling, Elf, Halfling, Dwarf,
Highman, Dark Elf, Orc, Goblin, Undead — order taken from the dialog, which reads the mapset) and
race **255** is the raceless pool (the palette's Humanoids / Creatures / Machines tabs — those are
`GetUnitType`, not races). `res+0x1C` and `res+0x24` are the two halves of the display name
(idx 111 = "Dwarf" + "Axeman"); **the authoritative race is the byte at `res+0x20`** — do not infer
it from `+0x1C`, which is not always the race (race 9 yields both "Orc" and "Minotaur").

Useful scratch tooling written for this (in the session scratchpad, worth re-deriving if needed):
a VMT-scan probe that finds the live `TArmyEditForm` (VMT 0x419908) and walks
`form+0x214` → `TUnitGrid`, `grid+0x1E0` → `TArmy`, `army+8` → inner TList (`+8` count, `+4`
items). ⚠ Freed forms keep their VMT pointer, so several candidates match — pin the live one by
finding the object holding the visible window's HWND. ⚠ Ghidra renders these classes as `int *`,
so its `param_1[0x78]` is a **DWORD index** = byte offset 0x1E0; taking it as a byte offset wastes
a debug cycle.

### Why the dialog feels slow to open (measured 2026-07-28 — it is NOT the dialog)

The dialog is not the cost. Measured with posted clicks on the live editor:

| Milestone (from the click) | Time |
|---|---|
| dialog window object created | ~78 ms |
| all 21 child controls created | ~96 ms (so **~18 ms for the whole control tree**) |
| window visible (`ShowModal`) | ~99 ms |
| content fully rendered, pixel-stable thereafter | ~120 ms |

Comparable stock editor dialogs: About (2 controls) 27 ms, Game Settings (19) 55 ms, Map Settings
(52) 165 ms — so this dialog sits in the normal range for this editor.

The real driver: **`SendMessageTimeout(WM_NULL)` to the editor's main window takes ~24 ms round-trip
even when the editor is completely idle.** The map render loop paces the message pump (see
`Editor_Lag_CopyPaste_Investigation_2026-07-07.md`), so the queue drains roughly one message per
rendered frame. A three-message mouse click (move/down/up) therefore costs ~72 ms before
`ArmyBtnClick` even runs — which is most of the ~99 ms above. That per-step ~24 ms is what reads as
"each field takes 20 ms".

⚠ The map view's DFM `FrameRate` is already **120** on this install, so 24 ms is *not* a configured
cap — it is how long one map frame actually takes to render. Raising FrameRate further cannot help;
only making a frame cheaper (or draining more than one message per frame) would. Sampling the
process during the open shows it essentially idle (all time in `NtWaitFor…`/message waits, no
hotspot), confirming it is waiting, not computing.

**Two measurement traps this cost time on:**
- `PrintWindow` (what `grabwin.py` uses) sends `WM_PRINT`, which repaints the window *synchronously*
  into your DC. It therefore cannot tell you what is actually on screen or when it got there — an
  early "paint progress" measurement built on it reported a bogus ~800 ms that was pure instrument
  overhead (the polling loop's own EnumWindows + PrintWindow cost).
- Polling with cross-process `GetWindowTextW`/`EnumChildWindows` in a tight loop perturbs the very
  pump you are measuring. Use fixed-delay snapshots and compare frames afterwards.

### Re-applying after a tweak

`build_party_random.py --apply` **rewrites `.pty` in place** (it is the last section) and never adds
a backup layer, so re-tuning never needs a revert. ⚠ Its "already patched" check compares the whole
intended section body, not just the hook targets — a change that touches only cave *data* (dialog
geometry, the strength table, the defaults) leaves every label address identical, so a
hook-target-only check silently no-ops. That bit once on 2026-07-28: a dialog layout change appeared
to apply but didn't.

## Revert

`copy AoWDevEd.exe.pre-partyrnd AoWDevEd.exe` — ⚠ **no longer the newest AoWDevEd backup**
(`.pre-timerres` is, as of 2026-07-28), so restoring it would also destroy the timer-resolution
patch. Check with `ls -t AoWDevEd.exe.pre-* | nl`. Original guidance, still the rule:
**only while it is the newest AoWDevEd backup**
(`ls -t AoWDevEd.exe.pre-* | nl`). Otherwise undo surgically: restore the 8 bytes
`85 F6 74 21 6A 00 6A 00` at VA 0x41A414 and zero the `.pty` body.
