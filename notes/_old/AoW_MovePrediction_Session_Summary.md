# Age of Wonders (1999) — Movement Prediction Bug Fix Session Summary

## Bug Description

Army stacks with mixed movement abilities display incorrect movement prediction range. The predictor combines worst-case per-hex cost (MAX across units) with the lowest remaining MP (MIN across units) — a pessimal pairing.

**Example:** Cavalry (Walking, 36 MP) + Elf Archer (Walking+Forestry, 26 MP) through forest predicts 4 hexes instead of the correct 6 hexes. The Cavalry should get 36/6 = 6 hops, and the Elf should get 26/4 = 6 hops (Forestry reduces forest cost to 4). MIN(6,6) = 6, but the game shows MIN(MP)/MAX(cost) = 26/6 = 4.

The actual per-hex movement execution is correct — individual units deduct their own costs. Only the UI prediction is wrong.

---

## Architecture Findings

### Movement Prediction Pipeline

1. **`TArmy.CreateMovePointTable`** (5578DC40) — Builds a 256-byte cost table for the army. Each unit's move type byte (from `GetMoveTypes`) selects one of 8 pre-defined cost tables (see Movement Cost Tables below). `MaximizeMovePointTable` takes element-wise MAX across all selected units' tables. The merged result is stored in `TMoveControlSettings+0xAC`.

### Movement Cost Tables

Movement abilities in AoW1 are not modifiers — they ARE cost tables. Each ability grants access to a different 256-byte table of terrain/road costs. A unit's `GetMoveTypes` returns a bitmask of which tables it uses. The 8 tables, indexed by bit position, are:

| Bit | Table | Granted by |
|-----|-------|------------|
| 0 | Walking | Default for land units |
| 1 | Swimming | Swimming, WaterWalking, LiquidForm |
| 2 | Flying | Flying, Floating, WindWalking |
| 3 | Forestry | Forestry ability |
| 4 | Cave Crawling | Cave Crawling ability |
| 5 | Mountaineering | Mountaineering ability |
| 6 | Fire Walking | Fire Immunity, Fire Halo |
| 7 | Tunneling | Tunneling ability |

A unit with Walking+Forestry (bits 0 and 3) has moveType byte = 0x09. `CreateMovePointTable` builds that unit's cost table by taking element-wise MIN across the Walking and Forestry tables — the unit uses whichever is cheaper per terrain type. For forest hexes, the Forestry table gives cost 4 while Walking gives cost 6, so the unit's effective forest cost is 4.

**The merged army table** then takes element-wise MAX across all units' individual tables. If a Cavalry (Walking only, forest cost 6) is stacked with an Elf (Walking+Forestry, forest cost 4), the merged cost for forest is MAX(6, 4) = 6. This merged cost is what the path stores per-hop.

Only Haste and Air Mastery modify costs beyond table selection — all other abilities simply grant access to their respective table.

2. **`TMoveControl.CalculatePathEx`** (55746080) — Dijkstra flood fill to find the optimal path. Uses the merged cost table. Stores per-hop merged costs as byte 3 of each path entry. The path itself is stored in **reverse order**: path[0] = destination end, path[last] = source.

3. **`TArmy.MovePoints`** (5578D8D0) — Returns MIN(MP) across selected units. The `jge` at `5578D92F` keeps the minimum. This value is stored in `TMoveSettings+14h` and used for the yellow/grey arrow color decision.

4. **`TMovepath.MovePointsToPos`** (557638D8) — Walks the path backward (from source to destination) subtracting stored merged costs from the MP budget. Returns a position index where the budget runs out. If MP goes negative, increments the index (overshoots back one step).

5. **`TMoveSelector.ShowMovePaths`** (55763F80) — ~730 lines of rendering code that draws the movement arrows and turn boundary markers.

### ShowMovePaths — The Rendering Function

**Arrow colors** are determined inside the drawing loop by comparing a running cost countdown (`[ebp-30h]`, starting at total path cost, decremented per hop) against `[esi+14h]` (the MIN(MP) budget from TMoveSettings). When remaining cost ≤ budget → yellow arrow; when > budget → grey arrow. This comparison happens at multiple points in the function (around addresses 55764140, 55764210, 55764332, 557642C8, 557643B0).

**Sprite indices:** Yellow arrows use base offset 0x22, grey arrows use 0x29/0x30.

**The divider X marker** is controlled by a `MovePointsToPos` call at address `5576463D`, AFTER the drawing loop. This is the call site we successfully hooked.

**Multi-day turn number** is displayed near the source hex when the path exceeds one turn, computed as `([esi+0Ch] - [esi+14h] - 1) / [esi+18h] + 1` where `+0Ch` = total path cost, `+14h` = MP budget, `+18h` = moves-per-day budget.

### TMoveSettings Layout (instance size 0x2C = 44 bytes)

| Offset | Type | Description | Set by |
|--------|------|-------------|--------|
| +00h | ptr | Vtable pointer | TObject |
| +04h | ? | TEObject base field | TEObject |
| +08h | TMovepath* | Path (TXYLList) | TMoveSettings.Create |
| +0Ch | int | Total path cost (from PosToMovePoints) | CalculateMovePath |
| +10h | ptr | TArmyHS* (the "move object") | TMoveSelector.AddMoveObject |
| +14h | int | MP budget = MIN(unit MovePoints) **← THE BUGGED VALUE** | SetSelection, TSelectedArmy.Update |
| +18h | int | Moves budget (from TArmy.Moves) | SetSelection, TSelectedArmy.Update |
| +1Ch | int | Priority multiplier (init 1) | TMoveSettings.Create |
| +20h | int | Unit selection bitmask | SetSelection |
| +24h | int | Position result | CalculateMovePositions |
| +28h | int | Valid flag | CalculateMovePositions |

### Path Entry Format (DWORD per entry)

| Byte | Content |
|------|---------|
| 0 | X coordinate |
| 1 | Y coordinate |
| 2 | Level (map layer) |
| 3 | Per-hop cost (signed, from merged cost table) |

**Path order:** path[0] is near the **destination**, path[count-1] is the **source** hex. The path is built by `CalculatePathEx` which traces backward from destination to source.

### Key Addresses

| Address | Symbol | Notes |
|---------|--------|-------|
| 5578D8D0 | TArmy.MovePoints | Returns MIN(MP); jge at 5578D92F keeps minimum |
| 5578DB8C | TArmy.MoveOnMovePoints | Builds temp cost table, returns cost for terrain/road |
| 5578DC40 | TArmy.CreateMovePointTable | Builds merged MAX cost table |
| 5578E00C | TArmy.Transporter | Checks if army has a transporter |
| 5577FDC4 | TAbstractUnit.CreateMovePointTable | Builds per-unit 256-byte cost table |
| 557638D8 | TMovepath.MovePointsToPos | Walks path backward, returns position index |
| 55763904 | TMovepath.PosToMovePoints | Converts position to accumulated cost |
| 557020FC | TMapContainer.GetField (jmp stub) | Returns TMapField* for X,Y,Level coords |
| 55763A5C | TMoveSettingsList.CalculateMovePositions | NOT used for arrow display |
| 55763F80 | TMoveSelector.ShowMovePaths | The rendering function |
| 55764007 | ShowMovePaths outer loop start | Iterates TMoveSettings entries |
| 5576463D | ShowMovePaths MovePointsToPos call | Controls the divider X marker **← HOOK POINT** |
| 55792900 | TSelectedArmy.CalculateMovePath | Builds path, stores in TMoveSettings |
| 55793078 | TSelectedArmy.ExecuteMove | Actual movement execution |
| 55793628 | TSelectedArmy.Update | Refreshes +14h and +18h every frame |
| 558FA040 | AoWHSMap global | Pointer to the global map object |

### GetField Access Pattern

**CRITICAL:** The correct map container for GetField is accessed as:
```
[TMoveSelector+10h] → [+10h] = TMapContainer
```
From within our code cave (called from ShowMovePaths), the TMoveSelector is accessible via the caller's saved ebp:
```
[[our_ebp] - 04h] = TMoveSelector (ShowMovePaths' local at [ebp-04h])
```

Using `[AoWHSMap+10h]` directly does NOT work and causes ShowScene errors.

### MovePointTables Global (558EA040)

This 65536-byte array (256 move-type entries × 256 bytes each) is populated by `TArmy.CreateMovePointTable` for the **merged** move type combination of the currently selected units. Each of the 256 possible moveType bitmask values maps to a 256-byte cost sub-table. Only the entries actually used by selected units are populated. **Individual unit moveTypes DO have valid entries here** — the problem was our earlier code used the wrong base address or index computation, causing out-of-bounds reads.

**`TAbstractUnit.CreateMovePointTable`** (5577FDC4) builds per-unit cost tables. Takes `eax = unit*`, `edx = pointer to 256-byte buffer`. However, testing showed it returned the same costs as the merged table, suggesting it may build the table for the unit's moveType bitmask using element-wise MIN across that unit's component tables — which for a single-ability unit like Walking would give the same cost as the Walking table alone. **This needs further investigation** (see Unsolved Problem).

---

## Hook Implementation

### Confirmed Working Hook Point

**Address:** `5576463E` (the 4-byte relative offset inside the CALL at `5576463D`)

**Original bytes:** `96 F2 FF FF` (targets `557638D8` = MovePointsToPos)

**Patched bytes:** `BE 90 0A 00` (redirects to code cave at `5580D700`)

**Context:** Called from `ShowMovePaths` with:
- `eax` = TMovepath* (from `[esi+08h]`)
- `edx` = MP budget (from `[esi+14h]`)
- `esi` = TMoveSettings* (preserved throughout ShowMovePaths)

### Code Cave Location

**Address:** `5580D700` (unused space in the DLL's code section)

**Available space:** At least 400 bytes before any conflict

---

## What Works (Proven via Diagnostics)

1. **The hook point is correct** — returning `original + 1` moved the divider X by one hex
2. **Doubling the MP budget** and writing to `[esi+14h]` extended the yellow arrow section (confirmed the arrow color mechanism)
3. **GetField works** from the code cave when using the correct map container (via caller's ebp)
4. **GetField works in register-based loops** (edi/esi/ebx as counters) — tested with full path length
5. **Unit vtable calls work in loops** — MovePoints (`[vtable+D8h]`) and GetMoveTypes (`[vtable+E8h]`) both work correctly
6. **Combined unit + GetField nested loops work** — push/pop edi for outer loop, register inner loop
7. **`TAbstractUnit.CreateMovePointTable`** can be called per unit to build individual cost tables on the stack
8. **Transporter guard** (`TArmy.Transporter` at `5578E00C`) correctly identifies transporter armies
9. **Path count guard** (skip if count < 3) prevents crashes on very short paths

---

## What Doesn't Work / Known Pitfalls

1. **Memory-based loop counters** (`dec [ebp-xx]` / `cmp [ebp-xx]`) in loops containing GetField calls cause ShowScene error spam. **Must use register-based loop control.**

2. **`MovePointTables` at `558EA040`** — Earlier attempts to use this for per-unit lookups caused ShowScene errors, originally attributed to uninitialized data. Now understood to likely have been caused by the wrong GetField map container (`[AoWHSMap+10h]` instead of `[[TMoveSelector+10h]+10h]`). **May actually work with correct GetField** — needs retesting.

3. **`[AoWHSMap+10h]`** is NOT the correct TMapContainer for GetField in the ShowMovePaths context. Causes ShowScene errors.

4. **Writing to `[esi+14h]`** persists across frames and can corrupt the arrow display if the value is wrong. When we computed the per-unit budget as "sum of merged costs for K hops," it naturally exceeded MIN(MP) because the merged costs use MAX across units while individual units can traverse cheaper via their ability tables. The fundamental problem: the arrow drawing loop compares accumulated merged (MAX) costs against a single budget number, but per-unit movement can't be correctly expressed as a single budget in that framework. A different approach to arrow colors may be needed (e.g., patching the comparison points in the drawing loop, or rewriting the loop to do per-unit checks).

5. **`TArmy.MovePoints`** (5578D8D0) is deeply wired into the game's state management. Changing `jge` to `jle` at `5578D92F` to make it return MAX instead of MIN caused: stuck MP display (50 on unit cards), units moving when they shouldn't, and MapViewer.ShowScene errors on long paths.

6. **The two other `MovePointsToPos` call sites** — in `CalculateMovePositions` (55763A86) and `ExecuteMove` (5579328C) — do NOT control the arrow display. Hooking them has no visible effect on the prediction UI.

---

## Unsolved Problem

**`TAbstractUnit.CreateMovePointTable`** returned the same per-terrain costs as the merged army table in our diagnostic. The raw hop count for unit[0] matched the pessimistic vanilla prediction. This is unexpected given our understanding of the cost table system.

### What we now know about cost tables

Movement abilities ARE cost tables — Forestry doesn't modify the Walking table, it provides a completely separate Forestry table with different costs. A unit with Walking+Forestry (moveType 0x09) should have its individual cost table built by taking element-wise MIN across the Walking table (forest cost 6) and the Forestry table (forest cost 4), yielding an effective forest cost of 4.

The merged army table then takes element-wise MAX across units. With Cavalry (Walking, forest=6) + Elf (Walking+Forestry, forest=4), the merged forest cost is MAX(6,4) = 6.

### Why the diagnostic may have failed

Several possibilities:

1. **`CreateMovePointTable` may not be the right function.** Perhaps it builds a table for just one of the unit's movement types (e.g., Walking only), not the combined MIN across all the unit's types. The MIN combination might happen at a higher level (in `TArmy.CreateMovePointTable` before the MAX merge step).

2. **The MovePointTables global might work after all.** Since movement abilities are indexed by moveType bitmask, `MovePointTables[0x09 * 256 + terrain*16 + road]` should give the pre-computed MIN(Walking, Forestry) cost for that terrain. The earlier crash with MovePointTables was caused by using an incorrect base address (`[AoWHSMap+10h]` for GetField) — not by the table contents being wrong. Now that we have the correct GetField pattern, re-testing with MovePointTables and proper `GetMoveTypes` indexing might work.

3. **The diagnostic itself may have had a bug.** It only processed unit[0] and returned raw hops. If unit[0] was the Cavalry (Walking only, no Forestry), its cost table would correctly show forest cost = 6, giving 36/6 = 6 hops. The Elf would also get 26/6 ≈ 4 hops with Walking-only costs if CreateMovePointTable didn't apply the Forestry table. We never confirmed which unit was at index 0, or tested with a solo Elf with Forestry to verify its individual cost.

### Possible Next Steps

1. **Re-test MovePointTables with correct GetField.** Use `GetMoveTypes` (vtable+E8h) on each unit to get its moveType byte, then look up `MovePointTables[moveType * 256 + terrain*16 + road]`. The earlier crash was from the wrong map container, not wrong table data. With the proven `[[caller_ebp] - 04h]+10h+10h` GetField pattern, this approach might now work.

2. **Test with a solo Forestry unit.** Select only the Elf Archer (with Forestry) and check if `CreateMovePointTable` returns cost 4 for forest. If it returns 6, the function doesn't combine the unit's multiple tables.

3. **Examine `TArmy.CreateMovePointTable` more carefully.** This function calls `TAbstractUnit.CreateMovePointTable` per unit, then `MaximizeMovePointTable` to merge. Look at what happens BEFORE the MAX merge — the per-unit table at that point should have the correct MIN-combined costs. The issue may be that `TAbstractUnit.CreateMovePointTable` builds a single-type table, and the MIN combination happens inside `TArmy.CreateMovePointTable`'s loop.

4. **Look at how actual movement deduction works.** The execution path (when you click Move) correctly deducts per-unit costs. Tracing `TArmy.MovedTo` or similar functions would reveal where individual costs including abilities are computed.

---

## Files Produced

- `/mnt/user-data/outputs/AoW_MovePrediction_CodeCave.asm` — annotated assembly (from earlier session, may be outdated)
- `/mnt/user-data/outputs/AoW_Movement_Prediction_Bug_Analysis.md` — full analysis document (from earlier session)
- Source disassembly: `/mnt/user-data/uploads/AoWEPack_dpl_excerpts_trimmed.text`
