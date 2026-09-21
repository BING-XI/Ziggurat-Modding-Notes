# Shipyard water-area gold income

**Status: CONFIRMED WORKING (2026-08-26). Both halves tested in-game by the user. FINISHED.**

A shipyard produces **1 gold per 5 hexes** of contiguously adjacent water, divided between every
shipyard adjoining that body. Razed and under-construction shipyards are excluded entirely;
independent / unflagged ones **dilute the pot but collect nothing** (deliberate, §10 Q2).

⚠ **The rate is one named constant** — `HEXES_PER_GOLD = 5` in `build_shipyard_income.py`, next to
`CODE_VA_BASE`. The cave, every `--sim` expectation and `verify_cave` check 8 all derive from it, so a
re-tune is a one-line edit plus `--apply` (which rewrites the cave in place). It reaches the assembled
cave as the imm32 of `mov ecx, 5` at **`0x55822101`**; `verify_cave` reads that byte back and asserts it.
*(Shipped at 10, halved to 5 on 2026-08-26 at the user's request — a one-byte change, `0x55822102`
`0A`→`05`.)*

## The two halves — revert independently

| | script | binaries | footprint |
|---|---|---|---|
| **Income** | `build_shipyard_income.py` | `AoWEPACK.dpl` | 4-byte VMT-slot write at `0x557C7350` (`0x557BE500` → `0x55822080`) + cave `0x55822000..0x55822926` (2,343 B of a 0x1000 reservation) + BSS header `0x558FAB00` (0x6C B) |
| **Display** | `build_shipyard_income_display.py` | `AoW.exe` + `AoWCompat.exe` | gate disp32 at `0x004438A0` + `E9` at `0x004491CC` → section `.syd` `0x0062E000` (301 B used); 25 in-place bytes + one appended page per exe |

**Revert = each script's own surgical `--undo`.** Both are verified to return their targets
byte-identical to their backups (`AoWEPACK.dpl.pre-shipyardincome`,
`AoW.exe.pre-shipyarddisplay`, `AoWCompat.exe.pre-shipyarddisplay`) without touching a backup file.
The display half can be reverted alone, leaving the income half working.

Final applied hashes: `AoWEPACK.dpl` `d76726bc0896d45f…`, `AoW.exe` `9300d6421939e3e9…`,
`AoWCompat.exe` `a031a3f20a58b89a…`.

## Process record
**One `aow-pm` + three `aow-coder`/`aow-qa` rounds on the income half, one more of each on the display
half.** Two QA rounds returned FAIL with **zero defects in the patch bytes** — every finding was in the
regression guards or the docstring. The value of those rounds was almost entirely in §15: QA proved the
`--sim` suite was *blind* to the O(S × flood) regression by installing that regression and watching all
35 checks pass, and separately broke each build-time assertion to confirm it fired — finding two that
never could.

Every address below was read from the **live** `AoWEPACK.dpl` / `AoW.exe` / `AoWDevEd.exe` /
`HSEPack.dpl` with `re_tools/dasm.py` + `pescan.py` (Ghidra was not used; its image is vanilla and
HSEPack is not loaded in it anyway).

**The original idea as specified.** "Shipyards produce gold equal to 1 per 10 hexes of contiguously
adjacent water, divided between all un-razed shipyards adjoining that water body." Shipped at that rate,
then halved to **1 per 5 hexes** on the user's request after play-testing — see the header. The rest of
the sentence is implemented exactly as written.

**Verdict: GREEN.** One binary, one 4-byte VMT-slot repoint, one code cave. Effort is comparable to
`build_los_terrain.py`. The income pipeline for shipyards is *already fully built and registered* —
vanilla simply feeds it a zero.

---

## 1. Why this is cheap — the pipeline already exists

`Shipyard.TShipyard.GetBaseIncome` @ **`0x557C75D0`** is literally `33 C0 C3 90` = `xor eax,eax; ret`.
It is byte-identical in the live DLL and in `AoWEPACK_original_backup.dpl`, and the *only* reference to
it anywhere in the module is the VMT slot. A shipyard is a `TProductionPlace` whose base income was
deliberately zeroed; its sibling `TProductionPlace.GetBaseIncome` @`0x557BE4E0` returns a flat **10**.

Every shipyard **already owns a registered `TPlayerStructureIncomeSource`**:
`TProductionPlace.Create` @`0x557BE10C` builds one because `GetMagicSphere()` returns 8
(`TProductionPlace.GetMagicSphere` @`0x557BE228` = `mov al,8; ret`, not overridden by TShipyard), and
`Activate` @`0x557BEF2C` / `SetPlayer` register it. So a non-zero return reaches the purse with **no
other patch**.

Chain (Delphi register convention throughout — EAX=Self, EDX, ECX, then stack):

```
TShipyard.GetIncome            VMT+0x1F4  -> TProductionPlace.GetIncome     0x557BE500
  -> TShipyard.GetBaseIncome   VMT+0x22C  ->                                0x557C75D0  (returns 0)
TPlayerStructureIncomeSource.Income       0x55761AF8   ; mov eax,[eax+8]; call [vmt+0x1F4]
TPlayer.UpdateIncome                      0x55751F88   ; [pl+0xD0] = [pl+0xB0] + SUM(sources)
TPlayerControl.NewTurn+0x6A               0x5575542E   ; add edx,[eax+0xD0]; sub upkeep; SetGems
TPlayer.SetGems                           0x55751F38   ; mov [ebx+0xC4], edx
```

### `TShipyard` VMT — base `0x557C715C`, instsize `0x4C`, ClassID `0x000204BE`, no subclasses

| slot VA | off | method | resolves to | `.reloc`? |
|---|---|---|---|---|
| `0x557C7310` | `+0x1B4` | `GetCurrentActivityText` | `TProductionPlace` `0x557BE828` | yes |
| `0x557C7350` | `+0x1F4` | **`GetIncome`** | `TProductionPlace` `0x557BE500` | **yes** |
| `0x557C7388` | `+0x22C` | **`GetBaseIncome`** | `TShipyard` `0x557C75D0` (the zero stub) | **yes** |
| `0x557C7398` | `+0x23C` | `ListIncomeInfo` | `TProductionPlace` `0x557BE59C` | yes |

`SetRazed` / `GetRazed` / `GetRazeable` sit at VMT `+0x14C` / `+0x150` / `+0x154` (measured on
`TStructure`); TShipyard resolves the first two to `TProductionPlace.SetRazed` `0x557BE560` /
`TProductionPlace.GetRazed` `0x557BE558` (= `cmp byte [eax+0x48],1; sete al`).

---

## 2. ⚠ Hook `GetIncome` (+0x1F4), NOT `GetBaseIncome` (+0x22C)

**This is the single most important finding of the study, and it is counter-intuitive.** Making
`GetBaseIncome` non-zero is *not* display-inert. A byte-sweep for `FF 9x 2C 02 00 00`
(`call [reg+0x22C]`) across all five modules found consumers that change **gameplay**:

- `AoW.exe` `0x00440AD3` (`TProductionScreen.ActivityPreDraw`): on non-zero it does `TEObject.Create` +
  `mov dword [ebx+8], 0xA` — it **adds a Trade/Merchandise production-queue item to the shipyard**,
  icon index `0x2F` chosen at `0x0043F564`.
- `AoW.exe` `0x0043F33F`: `setne al` → enables a production-screen control.
- `TProductionPlace.GetCurrentActivityText` `0x557BE8AD`: Realm-window Places column flips
  `None` → **"Producing Merchandise"**.
- `TProductionPlace.ListIncomeInfo` `0x557BE59C`: gate at `0x557BE5E5` is `test eax,eax / jle` (strictly
  positive). Past it, `0x557BE643` dereferences `[eax+8]` on a `TProductionQueue.GetItem` result that
  `0x5575C80C` returns **nil** for out-of-range — a latent nil-deref shipyards have never executed.

Repointing **`0x557C7350` (GetIncome)** and leaving `0x557C7388` at `0x557C75D0` switches all of that
off at once, because every one of those sites reads `+0x22C` and keeps seeing 0. It also replaces the
`+25%` branch outright (see §3).

**The apparent price of this choice — and why it was not a price at all.** `AoW.exe` `0x004438A6`
*gates* the map structure-info panel on `GetBaseIncome` but `0x004438BE` *prints* `GetIncome`: the two
virtuals are split across gate and value, so the panel showed nothing. This was first written up here as
an accepted cost. It isn't — ⭐ **the correct fix is to move the GATE onto the value it already prints**
(§16.1, four bytes at `0x004438A0`), which is strictly more correct than vanilla. Do **not** instead make
`+0x22C` non-zero or return a "flat 1 sentinel": that re-opens every merchandise branch above.
⭐ **Generalise this:** before concluding a UI surface "can't show" a computed value, check whether it
gates on a *different* virtual than the one it prints.

---

## 3. Two engine multipliers sit between "the number" and the purse

1. **+25%, and it is the DEFAULT case.** `TProductionPlace.GetIncome` `0x557BE523` adds
   `ROUND(base * 0.25)` (float32 `0.25` at `0x557BE554`) when `[prodctrl+0x20] != 2`. The mode byte
   **defaults to 0** (`TProductionControl.Create` @`0x5575CB0C` = `mov byte [ebx+0x20],0`), so the bonus
   fires for every **idle** shipyard and is suppressed only while it is actively producing a ship.
   Income would visibly drop ~20% when a shipyard starts a ship. Hooking `GetIncome` removes this.
2. **Player-type scaling.** `TPlayer.UpdateIncome` `0x55751FC6` scales the player's whole total by
   `[player+0xA7]`: ×1.0 / ×2.0 / ×2.5+50 / ×3+100. Leave it alone — it applies to every income source.

---

## 4. The map layer (all in **HSEPack.dpl**, base `0x55600000`, 1,037 named exports, not in Ghidra)

- Map global `0x558FA040` (engine reaches it as `[0x558E9494]`). `map+0x10` = `TMapContainer`,
  `map+0x100` = `TStructureControl`, `map+0x174` = **day counter**.
- `TMapContainer`: `+0x14` level count, cap **3**, enforced at `TAoWHSMap.AddMapLevel` `0x5577768B`.
- `TAoWMapLevel`: `+0x0C` W, `+0x10` H, `+0x28` field instance size, `+0x2C` **contiguous field array**,
  `+0x74`/`+0x78` the X-offset / row-base tables.
- `TMapLevel.GetField(EAX=level, EDX=x, ECX=y)` @`0x556087B8` = `[+0x74][x*4] + [+0x78][y*4]`.
  **No bounds check.** Thunk from AoWEPACK: `0x557020DC`.
- `TMapField`: `+0x04` `TMapLevel*`, `+0x10/11/12` X/Y/L (**signed bytes**, read with `movsx`),
  `+0x14` cached terrain, `+0x15` overlay.
- **Max map = 127×127 × 3 levels = 48,387 fields.** `AoWDevEd.exe` `TNewMapDlg.OKBtnClick` writes the
  four presets at `0x40342A`/`0x403449`/`0x403468`/`0x403478` = `0x30`/`0x40`/`0x60`/**`0x7F`**.
  ⚠ The DFM caption says "Extra large (128x128)" and the code contradicts it — it is **127**.
  These are presets, not a clamp; the signed-byte coordinates are the real ceiling.
- **Maps do not wrap and regions cannot span levels.** `HSEngine.WalkToNextHN` @`0x5560E610` is pure
  delta arithmetic off tables at `0x5562E250` (even X) / `0x5562E290` (odd X) with no modulo — it
  happily emits out-of-range coords, so **the caller must clamp**. The walk record built by
  `InitHNWalk` @`0x5560E5C8` has **no L field** (`+0` dir, `+4` step, `+8` HN, `+0xC` radius,
  `+0x10/14` cur X/Y, `+0x18/1C` orig X/Y), so every traversal is 2-D within one level.
- Grid is **odd-q column-staggered** (`py = y*32 + (x&1)*16`).

### What counts as water — use the shipyard's own rule

`TShipyardConstructionControl.ValidateLocation` @`0x557C7788` tests `field[+0x14]` ∈ `{0x00 Water,
0x0A CaveWater}` at `0x557C7825`-`0x557C782B`, over an `InitHNWalk(radius 0)` covering **HN 0..6**
(centre + ring 1 = 7 hexes; `InitHNWalk` seeds the HN counter to 0 for radius 0), with a four-test
clamp at `0x557C77FC`-`0x557C7814`.

⚠ **Never use the historical water family `{0, 6, 0x0A, 0x0E}`.** On this install
`build_chasm_sky_movement.py` repurposed terrain `0x0E` as **SKY** and `0x0B` as **CHASM** — a naive
fill would count flying-only Sky hexes as ocean. Ice (`6`) is *not* water by the shipyard's rule.

---

## 5. A connected-component fill DOES ship — but do not use it

`HSEngine.LocationsConnected` @`0x5560E754` (HSEPack) is a real flood-fill, already imported by
AoWEPACK via thunk `0x557026EC`. **Use it as an algorithmic template only.** It operates over a
supplied `TXYLList` (so you must enumerate every water hex first), its inner loop rescans that list via
the linear `TXYLList.IndexOf` @`0x556056D4`, and the marker at `0x5560E6B0` is **directly recursive**
with depth equal to component size. At map scale that is quadratic *and* a stack overflow.

The right template is `GlobalEnchantmentSpells.TFloodControl.Setup` @`0x557F1384` — the shipping worked
example of a heap side-array (`ReallocMem` a `W*H*2` array, `FillChar` it to 0, free in Destroy).
⚠ Read it from `AoWEPACK_original_backup.dpl`; the live `TFloodControl.Flood` carries two 5-byte
project hooks at `0x557F1474` and `0x557F15BF`. ⚠ Do not copy its bounds strategy — it has a latent
out-of-bounds read on the last row. Copy `ValidateLocation`'s four-test clamp instead.

---

## 6. Memory — the heap, not BSS

BSS slack is **far too small**: BSS `0x558EA000` vsize `0x10231` → declared end `0x558FA231`, `.idata`
at `0x558FB000`, so slack is 3,535 bytes with ~150 already claimed. A byte-per-hex label array for one
127×127 level is 16,129 B on its own.

Use the Delphi heap. Module-local thunks, verified byte-for-byte in the live file:

| thunk | function | args |
|---|---|---|
| `0x55701008` | `System.@GetMem` | |
| `0x55701010` | `System.@FreeMem` | |
| `0x55701018` | `System.@ReallocMem` | EAX = &ptr cell, EDX = bytes |
| `0x55701078` | `System.@FillChar` | EAX = ptr, EDX = count, CL = value |

Per-level scratch, allocated and freed inside one pass: `labels uint16[W*H]`, `queue uint32[W*H]`,
`area`/`count uint32[W*H+1]` ≈ **225 KB peak**, one GetMem / one FreeMem per pass.
Keep only a 24-byte header in BSS (tbl_ptr, cap, n, cached_map, cached_day, busy).

⚠ **BFS with an explicit queue, never recursion** — a 16k-deep recursive fill blows the Delphi stack.

⚠ **Budget BSS/cave addresses against BOTH patch trees**: `build_scripts/` *and*
`Inioch/AoWx_to_Zig - Monthly_Social_Assistance_Cheque/patch scripts/`, which claims BSS
`0x558FAF23/24/40/60/A0` and overlapping caves, and whose own README says never to run it here.

**Cave space:** ⚠ **`0x55822000..0x55822FFF` is now OWNED by this feature — do not allocate into it.**
`0x55823000..0x55823FFF` is still all-zero, and the free run continues to `0x558E7A10`
(816,640 zero bytes measured from `0x55820410` on 2026-08-26). Nearest owner below is
`build_los_terrain.py` (up to `0x5582040F`).
**BSS:** this feature owns **`0x558FAB00..0x558FAB7F`**. Known claims elsewhere — `build_los_terrain.py`
`0x558FAA00/01`; the Inioch tree `0x558FA800`, `0x558FA8F0`, `0x558FA980`, `0x558FAA00`,
`0x558FAF20..0x558FAFA0`.

---

## 7. Caching — recompute once per game day

Naive recompute-per-call is catastrophic: `TProductionPlace.Activate+0x90` → `RegisterIncomeSource` →
`UpdateIncome`, so **map load performs Σ S(S+1)/2 `Income()` calls per player** — order 10⁹
instructions and 1-4 s of added load time. One full labelling pass is ~6.5M instructions (single-digit ms).

Key the cache on **(map pointer, `[map+0x174]` day counter)**. `TPlayerControl.NewDay` @`0x55754DA4`
does `inc dword ptr [eax+0x174]` at `0x55754DCB` — **immediately before** `TPlayerList.BeginUpdate` at
`0x55754DDC`, which is what drives `UpdateIncome`. So the day key is already fresh when the income sweep
runs. Lazy rebuild on first miss covers save-load and map change for free.

Cross-player consistency is free by construction: the pass is global, so every player's share of a
shared body comes from the same snapshot.

Optional hook to move the pass off the UI path: `0x55754DCB`, displacing
`FF 80 74 01 00 00` (`inc dword ptr [eax+0x174]`, 6 bytes, **confirmed carries no relocation** — the
relocs nearby at `0x55754DC7`/`0x55754DD2` are inside the two `mov eax,[0x558FA040]` operands, never
displace those). EAX already holds the map. The site is inside an SEH frame installed at `0x55754DC3`.

### ⚠ Rejected: any terrain-changed funnel — this is a recorded FAILED APPROACH
`build_los_terrain` v1 repointed `TAoWHSMap` VMT+0x94 (`TriggerTerrainChangedEvent` `0x557724EC`) as a
"terrain changed" hook and produced **unbounded recursion** (`MapChanged` `0x55772538` calls the slot;
`InvalidateMap` `0x557725C0` calls MapChanged per level; UpdateVisibility ends in InvalidateMap). It
froze the editor on map open. **AoWEPACK has no terrain-change-only notification.** Do not re-derive.

---

## 8. Structures, razed state, placement

- Registry: `TStructureControl` at `map+0x100`. `GetCount` @`0x55762390`, `GetStructure(i)` @`0x55762364`
  (bounds-checked, nil out of range). Dense — removal goes through VCL `TList.Remove`, which compacts.
  Includes **unowned** structures (`TStructure.Activate` @`0x5575F6D7` registers unconditionally).
  Copyable walk: `TStructureAIPA.Activate` @`0x55762594` — ⚠ but it uses absolute `mov eax,[0x558FA040]`
  loads, so it is **not** byte-copyable into a PIC cave.
- Identity: `TShipyard.ClassID = 0x000204BE`, unique across all ~930 VMTs, **no subclasses**. Engine's
  own register-only idiom: `mov edx,[obj]; call [edx+0x24]; cmp eax,0x204BE` (verbatim at `0x5576249E`).
  Surface and underground shipyard resources (ids 60 / 107, selected at `0x557C76AD`/`0x557C76C3`)
  instantiate the same class — one test catches both.
- Structure fields: `+0x04` `TMapField*`, `+0x08` resource, `+0x10/11` X/Y, `+0x1C` structure id,
  `+0x24` builder byte (`0xFF` = not building), `+0x30` owner byte (`0xFF` = unowned), `+0x40` income
  source, `+0x44` production control, `+0x48` **razed flag**.
- Razing does **not** destroy the object: `TStructure.ExecuteRaze` @`0x5575FFC8` → `SetRazed(true)` sets
  `[+0x48]=1` and forces `SetPlayer(-1)`, unregistering the income source; the object stays in the
  registry and on the map. Rebuild ends at `TStructure.BuildingDone` @`0x5575F010`, which calls
  `SetRazed(false)` at `0x5575F139` — income resumes automatically.
- **Shipyard raze runs the vanilla path.** `build_razebattle_tower.py` repointed VMT+0x1B0 on
  TCity/TProductionPlace/TPowerNode, but Delphi copies parent VMTs at compile time, so TShipyard's own
  `+0x1B0` (`0x557C730C`) still holds `0x5575FFC8`. Do not rely on that script's cave state.
- **Footprint hex count is NOT in the binary.** `TShipyardResource.Create` @`0x557C75DC` sets only
  `[res+0x44]=0`, `[res+0x60]=0x96`, `[res+0x5A]=0x0A`, `[res+0x5B]=1` and never builds a `TTerrainList`.
  The count is `[[shipyard+8]+0x28]+4`, loaded from `Release/Release.hss`.
  **Sidestep it** with `TTerrainList.CreateSurroundingHNTable` (thunk `0x55701CAC`) — the engine's own
  "hexes surrounding this whole structure" primitive, with two precedents:
  `Crops.TPlayerCropStructure.GetCropCount` @`0x557A6480` and `TStructure.UpdateRoads` @`0x5575E71E`.

---

## 9. Blast radius

**One binary.** No exe change is required for the core feature.

- `AoWTCPCK.dpl` / `AoWDevEd.exe`: their three "Shipyard" strings each are import-descriptor names for
  the Delphi unit's init/finalization, not code. `aowInt.dpl` and `HSEPack.dpl` do not import AoWEPACK.
  `AoW.exe`'s only real Shipyard reference is the classref used twice for `@IsClass` icon selection
  (`0x43F761`, `0x43F7C4`).
- **⚠ The cave RUNS IN THE EDITOR — but via ONE door, not two.** `HSEngine.TMapObject.MainPlace`
  @`0x55609DD2` invokes the Activate slot, so `Activate → RegisterIncomeSource → UpdateIncome →
  GetIncome` is reachable in `AoWDevEd.exe` during map load and structure placement, when a structure
  may have no map field. **Null guards are mandatory, not optional.** Returning 0 is always safe — it is
  exactly vanilla.
  ⚠ `AoWDevEd.exe 0x004174F4` / `0x0041750C` are **NOT** virtual calls and are not a second door — an
  earlier draft of this doc said they were. There is no `mov edx,[eax]` before them; they are a Delphi
  **method-pointer field pair** (`TMethod.Code` at `+0x1F4`, `.Data` at `+0x1F8`) on an editor form.
  A byte sweep for `FF 9x F4 01 00 00` gives AoWEPACK 7, AoW.exe 4, AoWDevEd 2 (both bogus),
  AoWTCPCK/aowInt/HSEPack 0. Classic offset-aliasing — don't hunt for editor call sites to guard.
- **AI: no crash or hang surface.** The AI cannot build shipyards at all (construction runs only through
  `TConstructStructureTE` / `TConstructionControlList.GetConstructionControl`, imported by `AoW.exe`
  alone), `TStructure.ExecuteAI` really is `xor eax,eax; ret`, and income feeds the AI only as two
  bounded linear terms: `TAIBudgetManager.UpdateBudgets` @`0x55736987` and
  `TProductionPlace.UpdateAITarget` @`0x557BF15D` = `clamp(own_income/2 + 50, 25, 75)`, which already
  saturates at vanilla incomes.
- **Saves: nothing needs to enter them.** The value is fully derivable from replicated map state. The
  property table is id-indexed (`TPropertyTable.FindOffset` returns −1 for absent ids); the shipyard
  chain uses ids 0,1,3,4,5,6,7,8,9,0xA,0x62,0x63. Do **not** grow `TShipyard` or `TAoWMapField`.
- **Multiplayer: NOT A RISK FOR THIS PROJECT.** Every peer runs the mod — *mixed modded/unmodded
  matches are explicitly not a design target* (user ruling, 2026-08-25; see
  [[aow1-no-mixed-mod-multiplayer]]). So the only MP requirement is that the computation be
  **deterministic across peers**, and it is: no RNG, fixed (level, y, x) iteration order, fixed-direction
  neighbour walk, reads only replicated map state, and **never per-player fog** (never touch
  `FogArea` `0x55771EF4` / `ExploreArea` `0x5577212C` — that is the one way this design could desync).
  Income is derived, not serialised — `TPlayer.ReadWrite` @`0x5575314C` streams `[player+0xB0]` but
  never the total `[player+0xD0]` — so every peer recomputes identically.
  *Recorded for completeness, not as a task:* the engine could not catch a mismatch anyway.
  `TPlayerControl.GetSyncValue` @`0x55754D04` ships one dword, `map+0x230`, which `TAoWHSMap.Random`
  reads at `0x5577829D` and writes back at `0x557782B4` — the RNG seed, not a state hash, and gold
  cannot enter it; `ValidateCompatibleVersion` @`0x557DFCAC` compares only the top 16 bits of the
  version dword.

### Balance reach the user should sign off on
- **Freeze Water / Ice Storm become economic attacks** — they convert water to Ice(6), removing it from
  a body and potentially **splitting** it. Flood converts land to water, merging bodies.
- Raising income **reduces unit desertion**: `TArmy.Desert` @`0x5578F2DC` compares upkeep against
  `[player+0xD0]`.
- A gold-total victory scenario can **end early**: `TPlayer.SetGems` `0x55751F51`-`0x55751F7F` tests
  `map[+0x14D]==2` and compares `map[+0x154]`, calling `TAoWHSMap.GameOver` @`0x55776838`.

---

## 10. Spec questions the engine does not answer — DECIDED

The engine gives no answer to any of these — `ValidateLocation` stops at the **first** water hex and
never tests connectivity between water neighbours, so "the water body a shipyard touches" is not even a
function. **Q1, Q2 and Q6 were decided by the user on 2026-08-25**; Q3-Q5 keep the recommended defaults
(not explicitly ruled on, no objection raised).

| # | question | ruling |
|---|---|---|
| 1 | Shipyard touching **disjoint bodies** | ✅ **DECIDED — gather from ALL of them**, a divided share from each. Fall back to one body per shipyard only if the multi-region path proves genuinely hard. |
| 2 | Who is in the **divisor** | ✅ **DECIDED — every shipyard on the body, including independent / unflagged (owner `0xFF`) ones.** Only the razed are excluded (`[s+0x48]==1`), per the spec sentence. |
| 3 | **Rounding** | default stands: `pot = area div HEXES_PER_GOLD` once per body, then `share = pot div N`, remainder discarded at both steps |
| 4 | Body **smaller than `HEXES_PER_GOLD`** / share rounds to 0 | default stands: accept the blackout — all four display gates hide at zero, and forcing a visible zero means defeating four separate vanilla gates |
| 5 | **Ice / bridges** | default stands: water = exactly `{0x00, 0x0A}`, overlay ignored (so bridged water counts, Ice does not) — the engine's own placement rule. ⚠ carries the Freeze-Water-as-economic-attack consequence in §9 |
| 6 | **Underground** sea vs surface sea above it | ✅ **DECIDED — separate bodies.** Also structurally forced: the HN walk record has no L field |

### Consequences of Q1 and Q2 that the implementation must carry

- **Q2 destroys gold on purpose, and that is accepted.** An unowned shipyard is never registered as an
  income source — `TProductionPlace.Activate` gates registration at `0x557BEEB1` on
  `cmp byte [ebx+0x30],0xFF` — so an independent shipyard **dilutes the pot without collecting its
  share**. A derelict shipyard on your sea is therefore a standing tax until someone razes or takes it.
  That is the ruled behaviour, not a defect; do not "fix" it in the cave.
- **Two different membership tests are needed**, and conflating them is the likely bug:
  *divisor membership* = `[s+0x48] != 1` (not razed) — nothing else.
  *payee eligibility* = also owned (`[s+0x30] != 0xFF`), because there is no player to pay otherwise.
- ✅ **DECIDED (2026-08-26) — an under-construction shipyard (`[s+0x24] != 0xFF`) does not count at
  all**: not in the divisor, not earning. "Shipyards should only count once complete." Cheap to
  implement — the same one-byte test the razed check uses, applied in *both* the divisor sweep and the
  payee path — so the offered "skip it if hard" fallback is not needed.
  Net effect: the divisor test is `[s+0x48] != 1 && [s+0x24] == 0xFF`; the payee test adds
  `[s+0x30] != 0xFF`.
- **The "up to 3" ceiling holds only for a single-hex footprint.** Six neighbours alternating
  water/land/water/land/water/land gives at most 3 disjoint water groups. If the shipyard occupies more
  than one hex, its surrounding ring is longer and the ceiling rises — and the footprint hex count is
  **not in the binary** (§8, it lives in `Release/Release.hss`). Size the per-shipyard region-id dedupe
  array from the actual surrounding-hex count at runtime, not from a hard-coded 3.

---

## 11. Phased plan

**P0-P2 — DONE 2026-08-26 (applied, untested).** Built as **one complete round**, not P1-then-P2: the
divisor and the multi-region straddle fall out of the *same* labelling pass, so splitting them removed
~40 bytes of arithmetic rather than a risk class, and the user can only test in-game once per round.
P1's diagnostic value was bought instead with a **`--sim` mode** — a pure-Python reference of the whole
rule over synthetic maps, so a wrong in-game number can be attributed to the rule or to the assembly
without burning a game round.

As built:
- **Two-tier cache.** Tier 1 (the flood fill) keyed on `(map ptr, [map+0x174] day, [container+0x14]
  level count, [level0+0x14], [level0+0x2C])`. Tier 2 (the per-region divisor counts) is refreshed far
  more eagerly. ⚠ **`TStructureControl.GetCount` must never enter the tier-1 key** — at map load
  `RegisterIncomeSource` calls `UpdateIncome` per structure, so a structure-keyed label cache would run
  S full flood passes.
- **No `GetField` calls at all.** The field array is contiguous:
  `field(x,y) = [level+0x2C] + (y*W + x) * [level+0x28]`, outer y / inner x, proven by
  `HSEngine.TMapLevel.CreateMapFieldList` @`0x556087CC`. The water sweep is a linear stride walk.
- **Adjacency = the shipyard's own hex + its six neighbours**, using the *same* delta table the BFS
  uses, so "adjacent" and "connected" can never disagree. This is exactly the 7-hex set
  `ValidateLocation` itself validates, and it needs no `Release.hss` footprint data (§14.1 sidestepped).
- **Tier 2 runs unconditionally**, over a **cached shipyard sub-list** (`harvest`). The harvest — the
  only `GetStructure` + ClassID walk in the cave — is re-run iff `H_YVALID == 0` or `GetCount` moved;
  the **membership bytes `[s+0x48]`, `[s+0x24]`, `[s+0x30]` are re-read on every evaluation**, which is
  what keeps completion and razing live in the same evaluation rather than a day later.
  ⚠ `build_t1` must clear `H_YVALID`/`H_YN` **before** its `ReallocMem` — the pointer array lives in
  the block `ReallocMem` can move. That ordering is the use-after-free invariant; `verify_cave` asserts it.
- Cave blocks: table `0x55822000` (128 B), entry `0x55822080` (186), ensure `0x55822140` (233),
  regions_of `0x55822230` (270), build_t1 `0x55822340` (1072), build_t2 `0x55822770` (266),
  **harvest `0x55822880` (167)**. `yards[]` is `MAX_YARDS = 1024` dwords at the end of the heap block
  (the 4 KB is inside the allocation; the `cmp ecx,0x400` cap is enforced *before* the store).

### ⚠ Who calls `TPlayer.UpdateIncome` — the corrected inventory
A brute E8 scan of CODE finds **six** direct callers of `0x55751F88`, three of them ungated. This
matters because the ungated ones are what the sub-list protects:

| site | enclosing function | gated on `[player+8]`? |
|---|---|---|
| `0x5574B6FD` | `TDisbandUnitTE.Execute +0x269` | **no** |
| `0x55751EEA` | `TPlayer.EndUpdate +0x22` | the lock-release path |
| `0x55752093` | `TPlayer.RegisterIncomeSource +0x2B` | yes |
| `0x557520BA` | `TPlayer.UnregisterIncomeSource +0x1E` | yes |
| `0x557A61AB` | `Crops.TPlayerCropStructure.SetIncome +0x2F` | **no** |
| `0x557BED10` | `TProductionPlace.Update +0x2C` | **no** |

⚠ `TProductionPlace.SetPlayer 0x557BF0BC` is **not** in this list — it calls
`TPlayer.RegisterIncomeSource 0x55752068`, which *is* gated. An earlier draft named it as an ungated
direct caller; it is neither.

**There is no map-load income storm.** `TAoWHSMap.MsgProc` @`0x55778498` (msg `0x20000008`) calls
`TPlayerList.BeginUpdate` @`0x557784C1`, dispatches activation @`0x55778500`
(→ `TProductionPlace.Activate 0x557BEE9C` → `RegisterIncomeSource`), then `TPlayerList.EndUpdate`
@`0x55778522`. `TPlayer.BeginUpdate` @`0x55751EA8` does `inc [ebx+8]`, so every per-structure
registration is suppressed and `EndUpdate+0x22` issues exactly **one** sweep per player.
`TAoWHSMap.Activate`'s own Begin/End pair (`+0x109`/`+0x114`) is **empty** — a refresh trigger, not a
second wrapper — and runs inside the outer window anyway.
*Residual inference:* that map load actually sends msg `0x20000008` was not proved statically.

**P3 — only if playtesting asks.** Dirty flag from `TStructure.PlaceOnMap` `0x5575E7C0` /
`RemoveFromMap` `0x5575E7EC` / `TProductionPlace.SetRazed` `0x557BE560` for same-turn freshness
(**never** a map-level terrain funnel — see §7). Realm-window breakdown row: a `ShipyardIncome` cave
cloned from `Mine.MineIncome` @`0x557B47C4`, called from `AoW.exe` `0x004491CC` via the rebase-delta
trick, mirrored into `AoWCompat.exe`. Until then the Realm breakdown's five hard-coded categories
(external / `City.CityIncome` / `Farm.FarmIncome` / `Mine.MineIncome` / `BldGuild.BuildersGuildIncome`,
`0x00448FBB`-`0x004491CC`) will **not sum to its own Income headline**, which reads `player+0xD0`.

**Effort:** `build_shipyard_income.py` ≈ 500-700 lines, Cave A ≈ 400-600 bytes. One solid coder day for
P1+P2, one QA round, one in-game round. Time sinks, ranked: (1) the BFS in hand-written x86 with the
parity delta table inlined — `build_los_terrain.py` lines 11-45 / 188-190 is the donor; (2) the guard set
and the editor path; (3) heap alloc/free discipline in a cave.

**Undo footprint:** restore `0x557C7350` → `0x557BE500`; zero the cave zone; verify-before-write against
*either* `0x557BE500` or the current cave VA so `--apply` rewrites in place rather than reverting.
Touch no backup. One 4-byte data write + one cave zone — the cheapest possible footprint for a feature
this size, and the reason the GetIncome-slot design is worth the lost map-panel icon.

---

## 12. Acceptance criteria

**Checkable without launching the game**
- `0x557C7350` holds the cave VA; **`0x557C7388` UNCHANGED at `0x557C75D0`** — the load-bearing
  assertion of the whole design. `0x557C7310` and `0x557C7398` unchanged.
- Cave disassembles cleanly; no absolute memory operand except through the PIC delta; every `call` is
  rel32 into the module. Grep the listing for `[0x55` → expect zero hits outside the delta arithmetic.
- Preserves EBX/ESI/EDI/EBP on every return path; ends in a bare `ret`, never `ret n`.
- All four guards present: `[self+0x48]==1`, `[self+0x24]!=0xFF`, `[self+0x30]==0xFF`, `[self+0x04]==0`.
- Map-null guard in the `Mine.MineIncome` @`0x557B47CE` shape, plus container-null and level-count sanity.
- Every neighbour access bounds-clamped against `[level+0x0C]`/`[level+0x10]` before any dereference.
- Water predicate exactly `{0x00, 0x0A}`; grep the cave for `0x0E` and `0x06` as terrain comparands → zero.
- BFS is iterative; no `call` to the fill from inside itself.
- `--undo` round-trips to a byte-identical file (SHA-256). Re-run with no args reports installed+verified.
- ⚠ **verify-before-write against LIVE bytes, never vanilla** — see §13.
- No exe / `AoWTCPCK.dpl` / `aowInt.dpl` byte changes in P1-P2.

**In-game only (needs the user)**
- Big-sea shipyard shows a plausible "Income / N gold"; a pond shipyard shows nothing.
- Treasury actually rises by that amount next turn. (Expect the Realm breakdown's five categories **not**
  to sum to the headline — known, accepted until P3.)
- **No shipyard reports "Producing Merchandise"** and no merchandise entry appears in the production
  activity strip. If either does, `+0x22C` was touched.
- Shipyard info panel in three states — idle, mid-ship-production, queue just emptied — no crash.
- Two shipyards of **different players** on the same sea each show half the pot, and the figures agree.
- Build a third → all three shares drop to a third by the next day. Raze one → survivors rise.
- **An independent / unflagged shipyard on the same sea dilutes the pot and collects nothing** (Q2
  ruling): with one owned + one independent shipyard on a 200-hex sea, the owned one shows **10**, not 20.
- **A shipyard on an isthmus between two seas collects from both** (Q1 ruling) — put one where a
  ~100-hex and a ~200-hex body meet and confirm it shows the sum of the two shares, not either alone.
- A shipyard on an **underground** sea collects only from that sea, never from the surface sea above it.
- Cast Freeze Water across a strait → income changes next day (also the terrain-invalidation test).
- `AoWDevEd.exe`: open a shipyard map, place a shipyard, save, reload — no exception, no hang.
- Load a **pre-patch save** → income appears without a day passing (the lazy-recompute path).
- No perceptible turn-start pause on the largest available map.

---

## 13. ⚠ FOUR undocumented live-vs-vanilla edits near this feature

**No build script and no doc owns any of them.** Almost certainly deliberate Ziggurat balance from
before the note-taking convention. **Any build script near these must verify against LIVE bytes or it
will abort.**

| VA | live | vanilla | meaning |
|---|---|---|---|
| `0x557C7605` | `0x0A` (10) | `0x19` (25) | rebuild cost, gold (`TShipyardResource.Create`, `[esi+0x5A]`) |
| `0x557C7609` | `1` | `2` | rebuild time, turns (`[esi+0x5B]`) |
| `0x557C774A` | `0x14` (20) | `0x32` (50) | shipyard build cost (`TShipyardConstructionControl.GetInfo`) |
| `0x557BE4CC..D3` | `90 90 6B C0 06 83 C0 06` | `74 08 8D 04 80 83 C0 0A` | **`TProductionPlace.GetPower`** @`0x557BE468`: vanilla `if picks=0 then 0 else picks*5+10`; live `picks*6+6` **unconditionally** (the `je` NOP'd out) |

The fourth one matters beyond bookkeeping:

- **Shipyards already produce magic power.** `GetMagicSphere` returns 8 (`0x557BE228`), so power scales
  off `TLeader.GetSpherePicks`. This doc's "vanilla simply feeds it a zero" is true of **gold only**.
  A regression check after any change here: a shipyard's *power* contribution must be unchanged.
- ⚠ **Do not copy `GetPower`'s ownership idiom.** Its gate is `cmp byte [ebx+0x30], 0; jle` — a
  **signed** test that also excludes **player 0**. The correct ownership test is
  `cmp byte [eax+0x30], 0xFF; je`, the idiom `TProductionPlace.Activate` uses at `0x557BEEB1`.

---

## 14. Open items

**Closed during the build:**
- ~~Shipyard footprint hex count~~ — **sidestepped**, not measured. The cave uses the shipyard's own hex
  plus its six neighbours, which is exactly the 7-hex set `ValidateLocation` itself validates
  (`InitHNWalk` radius 0, `cmp dword [ebp-0x20], 7`). If the footprint is ever found to exceed 1 hex,
  the divisor and payee paths still agree with each other, so the failure mode is **under-collection,
  never mis-payment**. `CreateSurroundingHNTable` (thunk `0x55701CAC`) remains the primitive if true
  footprint adjacency is ever wanted; ⚠ how `UpdateRoads` frees that list is still unread.
- ~~`TAoWMapField` instance size~~ — never assumed; the stride is read from `[level+0x28]` at runtime.
  `CreateMapFieldList` @`0x556087F7`-`0x55608862` confirms `[level+0x0C]=W`, `[+0x10]=H`, `[+0x14]=W*H`,
  `[+0x28]=InstanceSize`, `[+0x2C]=`block, so the `W*H == [level+0x14]` guard is a real consistency
  test rather than a guess that could silently drop every level.

**Still open:**
1. Whether `[prodctrl+0x20]` can be 2 with an empty queue (the `ListIncomeInfo` nil-deref). Irrelevant
   in this design; relevant the moment `+0x22C` moves.
2. `AoW.exe` call frequency of `ListIncomeInfo` (`0x0043F842`) and `GetCurrentActivityText` — per
   selection or per repaint. Unmeasured; needs a live probe, not static analysis.
3. Whether any installed map places shipyards on levels 1-2 (content question for the user).
4. **Two `AoW.exe` panels will now show a shipyard gold figure** where they showed none:
   `0x0043F679`/`0x0043F68F` (production screen) and `0x0044286B` (`IntToStr` → `TAOWLabel.SetGText`).
   Expected and harmless — but this doc's blast-radius section did not budget them, so a *new but
   correct* label should not be reported as a bug. The accepted price is confirmed real: `0x004438A6`
   gates on `+0x22C`, so the map info-panel gold row does stay hidden.
   A sweep for `FF /2 disp32=0x1F4` across all eight binaries finds **13** sites, not one; the other
   eleven were characterised and cleared (class-own methods a shipyard never reaches; `MineIncome` /
   `BuildersGuildIncome` filter on ClassID first at `0x557B4819`; and
   `ExploreS.TExplorationSite.ExecuteSearch` passes EDX/ECX so it is a *different slot entirely* — the
   offset-aliasing trap again).

---

## 15. ⚠ Traps this build paid for — reusable

1. **`TStructure`'s x/y are NOT at `[s+0x10]`/`[s+0x11]`.** They live on the **map field**.
   `HSEngine.TMapObject.GetXhx` @`0x556094CC` is `mov eax,[ebx+4]; mov al,[eax+0x10]`; `GetYhx`
   @`0x55609538` reads `[field+0x11]`; `GetLhx` @`0x556095A4` reads `[field+0x12]` — all three assert
   `[obj+4] <> nil` ("Owner not set") first. `TMapObject.ReadWrite` streams `lea edx,[ebx+8]` as the
   resource id, so structure `+0x10` belongs to some descendant and is not x. Read x/y/L from
   `[s+0x04]`, never from the structure. (An early draft of this doc had it wrong; the coder caught it.)
2. **The sign-extended-imm8 trap wears a second mask.** keystone encodes
   `cmp word ptr [ecx+edi*2], 0xFFFF` as `66 83 3C 79 FF` — a sign-extended imm8 `−1`. *Correct* here
   (it widens to `0xFFFF` for a 16-bit compare), but an assertion looking for the literal bytes `FF FF`
   silently misses it, and capstone renders it as `, -1`. Rewrite as `movzx eax, word ptr[…]` /
   `cmp eax, 0xFFFF`, and assert that **no operand equal to `-1` appears anywhere in the cave**.
   ⚠ **Test for the operand VALUE, not the substring `", -1"`.** The canonical case this guard exists
   for — `push 0xFFFF` → `6A FF` — renders as `push -1` with **no comma at all**, so a `", -1"` string
   match misses precisely the trap it was written to catch. (Found 2026-08-26 when a spec of mine said
   `", -1"` and the coder's self-test caught it.)
3. **`--sim` is a spec test, not an implementation test.** A pure-Python reference written by the same
   author in the same file proves the *model* of the rule is right; it never executes the cave's x86.
   Keep it (it separates "wrong rule" from "wrong assembly" without burning a game round) but do not
   mistake a green `--sim` for cave-side evidence — that comes only from reading the disassembly.
4. **`TStructure.BuildingDone` does not touch `TStructureControl`.** It calls `SetRazed(false)`
   @`0x5575F13F` then clears the builder byte in place @`0x5575F145` (`mov byte [ebx+0x24], 0xFF`).
   So **registry count is not a valid cache key for "has anything become eligible?"** — completion is
   invisible to it. This cost a real over-payment bug (fixed).
5. ⚠ **Cave blocks are 16-byte aligned, so a naive concatenation does not equal the live zone.**
   `b"".join(block_bytes)` is 2,322 B while `end - CAVE_VA` is 2,343 B — the difference is inter-block
   zero padding. A verifier comparing the join against the file sees a mismatch that looks like a real
   defect. **Compare per block at its own VA**, or splat the blocks into a `0x1000` zero image first.
6. **A test suite nobody has watched fail is not a guard.** `--sim`'s 35 assertions passed *with the
   O(S × flood) catastrophe installed*, because every scenario varied razed/building flags on a
   **fixed** yard list and the key term that triggers the disaster never moved. The fix was a
   map-load-storm scenario (grow the list one yard at a time, assert the flood pass ran once) plus
   byte-level `verify_cave` assertions on call targets — and then *deliberately breaking each one* to
   watch it abort. Prose in a docstring stops nobody; a build-time abort does.
   ⚠ Known limit of the call-target assertions: they decode **direct** calls, so
   `mov edi, TARGET / call edi` slips past. Documented, not fixed.
7. ⚠ **A guard that compares the cave against the constant that built it can never fail.** Two of the
   display patch's nine self-tests were exactly this shape; QA broke the source constants and both
   builds came out clean — including the `HOOK_RESUME` mutation that lands the resume **inside the
   patch's own `E9`**, the trap already recorded against `build_arena.py`. **Anchor every constant to a
   binary**, not to itself: the resume address to the host function, a ClassID to the `mov eax,imm32;
   ret` stub the DLL actually exports.
   ⚠⚠ **And an instruction-boundary walk is NOT sufficient on its own** — on the vanilla file the bad
   resume `0x004491CE` *is* a real boundary (`8b 07` is two bytes). What kills it is the **relational**
   assertion `resume == hook_va + len(displaced)`. Do both.

---

## 16. Display gaps — diagnosed 2026-08-26 (fix not yet applied)

Both surfaces live in **`AoW.exe`** (and therefore `AoWCompat.exe` in lockstep). Neither is a fault in
the income cave.

### 16.1 Map structure-info panel — blocked by a gate on the wrong virtual

Two sites in `AoW.exe` gate the row on `GetBaseIncome` (VMT+0x22C) while *printing* `GetIncome`
(VMT+0x1F4). Since the design deliberately leaves `+0x22C` at the zero stub, the gate always closes:

```
004438A0  call dword ptr [edx + 0x22c]   ; GetBaseIncome -> 0 for a shipyard
004438A6  test eax, eax
004438A8  je   0x4438dc                  ; ...so the row is hidden
004438AA  mov  edx, 0x1f                 ; gold icon index
004438B5  call TAOWImage.SetCurrent
004438BE  call dword ptr [edx + 0x1f4]   ; but the VALUE printed is GetIncome
004438D5  call TAOWLabel.SetGText
```

**Fix: change the gate's disp32 from `0x22C` to `0x1F4` at `0x004438A0` ONLY** — `FF 92 2C 02 00 00` →
`FF 92 F4 01 00 00`. Four bytes, one site, mirrored into `AoWCompat.exe`.

### ⚠ Three other `call [reg+0x22C]` sites that look like the same gate and MUST NOT be touched

1. **`0x00443B41`** — not a number, an **activity caption**. Its two RStr slots resolve to
   `[0x0045E214]` = `AoWE.ProducingMerchandiseRStr` and `[0x0045E3DC]` = `AoWE.NoneRStr`; it is an
   if/else picking the caption. Repointing it to `+0x1F4` would make every earning shipyard read
   **"Producing Merchandise"** — precisely the outcome §2 bought by leaving `+0x22C` at zero.
   A shipyard correctly reads "None". *(An earlier draft of this section proposed patching it. Don't.)*
2. **`0x00440AD3`** (`TProductionScreen.ActivityPreDraw`) — **creates a Merchandise production-queue
   item** on non-zero. Never touch. (Full sweep of all 8 binaries for `FF 9x 2C 02 00 00 / 85 C0 / je`:
   AoW.exe `0x440AD3`, `0x4438A0`, `0x443B41`; AoWEPACK `0x557BE8AD`; zero elsewhere.)
3. **`0x00443119` / `0x00443140` / `0x0044318D`** — the **Altar** panel (`0x00443078`, dispatched under
   `IsClass [0x45E738] = Altar..TAltar`). On `TAltar`, `+0x22C` is `GetRechargeDays` and `+0x230` is
   `CanTarget` — offset aliasing again. Patching them corrupts the altar gauge.
   ⚠ An earlier draft added "they also carry `.reloc` entries". **That is false**, and the correction is
   worth keeping because it generalises: all 11,909 relocation entries in `AoW.exe` were parsed, and the
   **maximum reloc RVA is `0x5A630`** — nothing above `DATA` is relocated at all. A `FF 92 <disp32>`
   VMT call encodes a *displacement*, never an absolute address, so no call site of this shape can ever
   carry a relocation. Don't cite `.reloc` as a reason to avoid an exe VMT-call site; cite the aliasing.

### Blast radius of the `0x004438A0` edit — narrower than it looks, and provably safe
The dispatcher at `0x00444032` reaches this function only for `TProductionPlace` descendants **with
`GetMagicSphere() == 8`**, so the six magic nodes (spheres 0-7) never arrive. That leaves exactly four
classes — `TProductionPlace`, `TShipyard`, `TBuildersGuild`, `TRandomNode` — and **no descendant
overrides `+0x1F4` or `+0x22C` except TShipyard**. Mines, farms, cities, towers and altars enter through
separate `IsClass` arms; on several of them `+0x22C` is past the end of their VMT, which is why the type
gate is load-bearing. For the other three, `GetIncome == 0` exactly when `GetBaseIncome == 0`
(`base + ROUND(base*0.25)`, and the `[prodctrl+0x20]==2` branch returns `esi` unchanged), so the edit is
inert for them. **Gating on the value you print is strictly more correct than gating on a different
virtual.**

⚠ This gate is shared by **every** `TProductionPlace` descendant, not just shipyards. It is safe
because for all of them `GetIncome == 0` exactly when `GetBaseIncome == 0`:
`TProductionPlace.GetIncome` computes `base + ROUND(base * 0.25)`, so `base = 0 → 0`. Only the shipyard,
whose `+0x1F4` is our cave, changes behaviour. Gating on the value you print is also strictly more
correct than gating on a different virtual.

### 16.2 Realm window — genuinely has no shipyard category

`0x00449030..0x004491CC` emits **five hard-coded rows**, each an identical five-call sequence:

```
mov eax,[edi] / mov al,[eax+0xA5]     ; seated player index
call <XxxIncome>                       ; AoWEPACK import thunk
mov esi,eax / test esi,esi / je skip   ; zero rows are skipped
LoadResString(<RStr ptr>) -> AoWE.TranslateRStr -> [ebx+0x140].[+0x118].[vmt+0x34]   ; label column
IntToStr(esi)                         -> [ebx+0x184].[+0x118].[vmt+0x34]             ; value column
```

Thunks: `City.CityIncome 0x402ADC`, `Farm.FarmIncome 0x402B14`, `Mine.MineIncome 0x402B4C`,
`BldGuild.BuildersGuildIncome 0x402D14`, plus an "external" row. There is no `ShipyardIncome`.

⭐ **The two columns are LISTS that get `.Add`ed to (`[vmt+0x34]`), not a fixed layout** — so a sixth
row needs no geometry work at all, just one more copy of the sequence.

**Fix shape — entirely in the exe, no DLL change and no new import:**
1. ⭐ **The summation belongs in the exe, not the AoWEPACK cave.** `TPlayerStructureList.GetStructure`
   (thunk `0x004023DC`), `TPlayerList.GetPlayers` (`0x00402464`), `TranslateRStr` (`0x004021E4`),
   `LoadResString` (`0x00401180`), `IntToStr` (`0x004013AC`) and the `AoWE.AoWHSMap` slot
   (`[0x0045DF7C]`) are **already imported by AoW.exe**; everything else is a VMT call. So there is no
   second DLL cave, no rebase-delta trick, and no second `--undo` surface.
   `cave_sum(EDX = seated player index)` is shape-cloned from `Mine.MineIncome` @`0x557B47C4`
   (⚠ *shape*, not bytes — `0x557B47CE`/`0x557B47DC` are absolute DLL globals).
   ⚠ **Return 0, not −1, on a nil map** — MineIncome's `−1` would print as a literal "-1" row, because
   the row's skip test is `test esi,esi`.
2. Hook `E9 rel32` at **`0x004491CC`** + 4× `0x90`, displacing 9 `.reloc`-clean bytes
   (`8B 07 0F BE 90 A5 00 00 00`); the only inbound branch (`je` at `0x00449180`) lands exactly on it.
   New PE section `.syd` @ `0x0062E000` (template: `build_tierresearch_exe.py`).
3. ⚠ **`AoWE.ShipyardRStr` is NOT usable here.** AoW.exe imports 1,625 AoWEPACK symbols and
   `ShipyardRStr` is not among them — the five row labels are *data imports* (`[0x45E11C]` =
   `CitiesRStr`, `[0x45E114]` = `FarmsRStr`, `[0x45E118]` = `MinesRStr`, `[0x45E0BC]` =
   `BuildersGuildsRStr`, `[0x45E108]` = `ExternalIncomeRStr`). Its text is also "Shipyard" (singular)
   against peers reading "Cities"/"Farms"/"Mines". **Do not add an import** — recorded refusal in
   `Editor_Modernization_DialogDirs_Toolbar.md:124` ("fragile table surgery").
   Instead put a **Delphi AnsiString literal `"Shipyards"`** in the section (`dd -1, dd 9, bytes, NUL`)
   and feed it to `TranslateRStr`, which takes an AnsiString rather than a resource record — so it stays
   dictionary-translatable via `Dict/ResStr.txt` exactly like the vanilla labels, and the `-1` refcount
   makes `@LStrAsg`/`@LStrClr` no-ops on it.
4. Reuse the frame's own `[ebp-4]` LStr temp as the five vanilla rows do — the epilogue's
   `@LStrArrayClr` at `0x00449219` already frees it. No BSS, no leak.

### ⚠ Column capacity is the one thing that could change the job
The `.Add` mechanism is confirmed (`[control+0x118]` = `Classes.TStringList`, `vmt+0x34` = `Add`;
independently recorded in `Combat_Log_Implementation_Design.md:442-447`). **The capacity is not.**
Fitting the form field base to `0x138` = `TotalPnl` identifies `[ebx+0x140]` = **`IncomeMem`** (labels,
`BorderHeight` 1) and `[ebx+0x184]` = **`IncomeValue`** (values, `BorderHeight` **4**, and ⚠ **no
scrollbar at all**). At designer size that is **6 label rows but only 5 value rows**. Today the function
writes at most 5, so **our row is the first thing that can ever overflow.** Both memos are `ahBoth`
inside `IncomePnl`, so runtime heights differ from the DFM and must be **measured live**, not inferred.
**The lever if it is 5 vs 6:** `IncomeValue.BorderHeight` `4 → 1`, a single `vaInt8` in the TRealmWin
RCDATA DFM (region `0x15F0B4`+), same length, no CRC — via `re_tools/dfm_edit.py`.

**`AoWDevEd.exe` needs nothing** — zero `call [reg+0x22C]` sites anywhere in it; its two
`call [reg+0x1F4]` sites are event-handler object fields, not VMT calls; and none of its 28 DFM forms
is a realm or production-place panel.
