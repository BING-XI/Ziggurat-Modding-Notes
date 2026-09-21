# Age of Wonders: Army Movement Prediction Bug — Analysis & Fix Proposals

## 1. Bug Summary

When an army stack contains units with differing movement abilities and/or remaining Movement Points, the movement path predictor underestimates how far the stack can travel. The player must repeatedly click to advance the army in small increments, or manually split the stack.

---

## 2. Root Cause

The prediction system combines the **worst per-hex cost** (MAX across all units' cost tables) with the **lowest remaining MP** (MIN across all units). This pairing is always pessimistic because the "slowest" unit varies per terrain type — the unit that's expensive on forest might be cheap on roads, and vice versa.

### How the existing code works

**Step 1 — Cost table construction** (`TArmy.CreateMovePointTable`, `5578DC40`):

For each unit in the army, the game calls `TAbstractUnit.CreateMovePointTable` which loads that unit's pre-computed 256-byte cost table (based on its `MoveTypes` bitmask — Walking, Forestry, Floating, etc.). It then calls `MaximizeMovePointTable` which takes the **element-wise maximum** across all units. This merged table represents the highest cost any unit would pay for each terrain cell. It also correctly propagates impassability (0xFF).

**Step 2 — Dijkstra flood fill** (`TMoveControl.SetupMove`, `55745AE8`):

Seeds the source hex at cost 0 and floods outward using the merged army cost table via `DefaultMoveOnMovePointProc` (`557454D8`). Each hex's accumulated cost is stored in the move point grid (`TMoveControlSettings`). The flood is bounded by a `max_cost_limit` field, typically 0xFFF or a heuristic estimate.

**Step 3 — Path tracing** (`TMoveControl.CalculatePathEx`, `557460B0`):

Traces back through the cost grid from destination to source, producing the optimal route as an `XYLList` of hex coordinates with per-hop costs.

**Step 4 — Turn boundary** (`TMovepath.MovePointsToPos`, `557638D8`):

Walks backward through the path's stored cost-per-hop values, subtracting from the army's MP budget (`MIN` of all units' MP). Returns the position index where MP is exhausted — this determines the "this turn / next turn" boundary shown to the player.

**Where the bug lives:** Steps 1 and 4. The per-hop costs come from the MAX-merged table, and the MP budget is the MIN across units. Both are wrong for per-unit evaluation.

### Worked example

Cavalry (Walking, 36 MP) + Elf Archer (Walking+Forestry, 26 MP) traversing forest:

| | Per-hex forest cost | Total for 6 forest hexes | Remaining MP |
|---|---|---|---|
| Cavalry | 6 (Walking) | 36 | 0 ✓ |
| Elf Archer | 4 (Forestry) | 24 | 2 ✓ |
| **Army merged** | **6 (MAX)** | **36** | — |
| **Army MP budget** | — | — | **26 (MIN)** |

Correct prediction: `MIN(36/6, 26/4) = MIN(6, 6.5) = 6 hexes`

Bugged prediction: `26 / 6 = 4 hexes` (worst cost + lowest MP)

---

## 3. Solution Approaches

### Approach A — Fix MoveOnMovePointProc only

Replace the merged table lookup with per-unit lookups, returning the MAX of individual unit costs for each hex.

**Verdict: Fundamentally broken.** This fixes the per-hex cost but still uses one accumulated cost pool paired with MIN(MP). When different units are "slowest" on different terrain types along a mixed path, their individual accumulated totals diverge. A single accumulated total cannot represent this.

### Approach B — Multiple Dijkstra passes

Run the existing flood fill once per unit (up to 8 times), each with that unit's own cost table and MP. Take the element-wise MAX of all resulting cost grids (intersection of reachable areas).

**Pros:** Fully correct; reuses existing code; fixes both the path prediction AND the hex highlight overlay.

**Cons:** Up to 8× cost for the flood fill; requires one temporary cost grid allocation (map_w × map_h × 4 bytes). The flood fill is the main bottleneck for AI turns — the `UseProcessTime` calls at lines 2060 and 2099 confirm the AI budgets processing time around the flood. Multiplying by 8 would meaningfully slow AI turns on large maps.

**Mitigation:** Only run multi-pass for armies with genuinely mixed move types. Single-type armies (common) use the existing fast path. This could reduce average overhead to ~2×.

### Approach C — Single Dijkstra with per-unit cost tracking

Modify the flood fill to maintain N accumulated costs per hex (one per unit). Only expand to a neighbor if ALL units can reach it.

**Verdict:** Theoretically elegant but requires the deepest code changes — modifying the core Dijkstra loop, the cost grid data structure, and the expansion logic. Very high complexity for assembly patching.

### Approach D — Fix the MP seed value

Use MAX(MP) instead of MIN(MP) as the Dijkstra's budget, combined with MAX costs in the table.

**Verdict: Fundamentally broken** for the same reason as Approach A — single-pool cost tracking can't represent multiple units with different per-terrain costs.

### Approach F — Post-path per-unit range recalculation (RECOMMENDED)

Leave the Dijkstra flood entirely unchanged. After the path is determined, replace the "how far along this path" calculation with a per-unit walk.

**Key insight:** The Dijkstra with the MAX-cost table finds the correct *route* — it just overestimates the cost. Since MAX ≥ any individual unit's cost, the flood never misses valid paths. Only the "turn boundary" calculation needs fixing.

**Implementation:**
1. The path (list of hexes) is already computed correctly by `CalculatePathEx`
2. Hook or replace `MovePointsToPos` for army stacks
3. For each unit: walk the path forward, looking up that unit's own cost from its pre-computed table, accumulating individually, stopping when that unit's own MP is exhausted
4. The army's turn boundary = MIN of all units' reachable positions

**Pros:**
- Zero impact on Dijkstra flood fill → zero impact on AI turn times
- Zero impact on path routing
- Small code footprint (~200–300 bytes in a code cave)
- Straightforward to verify: each unit is evaluated independently using existing per-unit cost tables

**Cons:**
- The hex highlight overlay (which hexes appear "reachable") remains slightly pessimistic — based on the unchanged flood fill. However, the actual path prediction and turn boundary will be correct, which is the player-facing bug.
- Does not fix the edge case where the overlay itself prevents the player from even clicking a reachable hex. In practice this is rare, because the path tracer works on the cost grid (which does include the hex — it's just marked as "costly"), and `MovePointsToPos` is what determines whether the army stops before or after it. The destination click target is separate from the overlay.

**Note on the Floater+Swordsman road example:** The flood fill using `MAX(road_cost) = 4` with the Dijkstra budget (which is `0xFFF`, not MIN(MP)) still includes the road hex in the cost grid. `MovePointsToPos` with our per-unit fix correctly determines both units can afford it. The original `MovePointsToPos` with `army_MP = 3` and `army_road_cost = 4` incorrectly says they can't.

---

## 4. Recommended Implementation — Approach F

### Hook point

`TMoveSettingsList.CalculateMovePositions` at `55763A5C`, specifically the call to `TMovepath.MovePointsToPos` at line `55763A86`.

Currently:
```
mov edx,[edi+14h]        ; edx = army's MP budget (the wrong single value)
mov eax,[edi+08h]        ; eax = TMovepath object (has path + per-hop costs)
call TMovepath.MovePointsToPos  ; returns position index
mov [edi+24h],eax        ; store result
```

We'd redirect this call to our new function `ArmyMovePointsToPos` which:
1. Checks if this is a multi-unit army (if single unit, call original)
2. Iterates units, computing per-unit range along the path
3. Returns MIN of per-unit results

### Data we need access to

- **The army object** — reachable via the `TMoveSettings` structure. `TMoveSettings` at `[edi]` has a reference to the move context, which links to `TMoveControlSettings`, which stores the army pointer at offset `+0x9C`.
- **Each unit in the army** — via `army[+0x08]` (unit list container), with `[+0x04]` pointing to the array and `[+0x08]` giving the count.
- **Each unit's MoveTypes** — virtual call `[edx+0xE8]` on the unit object.
- **Each unit's remaining MP** — virtual call `[edx+0xD8]` on the unit object.
- **The pre-computed cost tables** — `MovePointTables` at `AoWE.MovePointTables@65168A9A`, indexed by `MoveTypesToInt(movetypes) * 256`.
- **Map field terrain/road data** — each path hex's coordinates let us call `GetField(x, y, level)` and read field `[+0x14]` (terrain type) and `[+0x15]` (road/sub type).
- **The path itself** — the `TMovepath` object at `[edi+0x08]` has the path as an `XYLList`. Each entry is a packed XYL coordinate; per-hop costs are stored at `[path_entry*4+3]`.

### Pseudocode for the code cave

```
ArmyMovePointsToPos:
  ; Input: same as original context in CalculateMovePositions
  ;   edi = TMoveSettings for this army
  ; We need to find the army and iterate its units
  
  push ebx, esi, edi, ebp
  
  ; Get army from MoveControlSettings
  ; TMoveSettings.??? -> TMoveControlSettings -> army at +0x9C
  ; (Need to trace exact offset chain from TMoveSettings to army)
  
  ; Get unit count
  mov eax, [army+08h]      ; unit list  
  mov ecx, [eax+08h]       ; unit count
  cmp ecx, 1
  je .single_unit          ; fast path: use original function
  
  ; Get path object
  mov esi, [edi+08h]       ; TMovepath
  mov ebx, [esi+08h]       ; path length (number of path entries)
  test ebx, ebx
  jz .done
  
  ; Initialize min_reachable to path_length-1 (optimistic: everyone reaches end)
  lea ebp, [ebx-1]         ; ebp = min_reachable_position
  
  ; For each unit:
  xor ecx, ecx             ; ecx = unit_index
.unit_loop:
  push ecx
  
  ; Get unit pointer
  mov eax, [army+08h]
  mov eax, [eax+04h]
  mov eax, [eax+ecx*4]     ; eax = unit object
  
  ; Get unit's remaining MP  
  mov edx, [eax]
  call [edx+0D8h]          ; al = unit's MovePoints
  movzx edx, al            ; edx = unit_mp
  push edx
  
  ; Get unit's MoveTypes
  mov eax, unit_ptr
  mov edx, [eax]
  call [edx+0E8h]          ; al = unit's MoveTypes bitmask
  
  ; Convert to table index and get cost table pointer
  call MoveTypesToInt       ; eax = table index (0-255)
  shl eax, 5               ; * 32? No... 
  ; Actually: TAbstractUnit.CreateMovePointTable uses shl eax,5 then
  ;   lea esi,[MovePointTables + eax*8] which = MovePointTables + index*256
  ; So: table_ptr = MovePointTables + MoveTypesToInt(movetypes) * 256
  shl eax, 5
  lea esi, [MovePointTables + eax*8]  ; esi = unit's 256-byte cost table
  
  ; Walk path forward, accumulating this unit's cost
  pop edx                  ; edx = unit_mp
  xor ecx, ecx             ; ecx = accumulated_cost  
  xor ebx, ebx             ; ebx = hex_index (start at 1, skip source)
  inc ebx
  
.path_loop:
  cmp ebx, path_length
  jge .unit_done
  
  ; Get this hex's terrain info
  ; Need to call GetField(x, y, level) using path coordinates
  ; Then read field[0x14] = terrain, field[0x15] = road_sub
  ; Look up cost = unit_table[terrain * 16 + road_sub]
  
  ; ... (terrain lookup details) ...
  
  movzx eax, byte [cost_table + terrain*16 + road_sub]
  cmp al, 0FFh
  je .unit_blocked          ; impassable for this unit
  
  add ecx, eax             ; accumulated += hex_cost
  cmp ecx, edx             ; accumulated vs unit_mp
  jg .unit_stopped          ; can't afford this hex
  
  inc ebx
  jmp .path_loop
  
.unit_stopped:
  dec ebx                  ; last affordable hex = previous one
.unit_blocked:
  dec ebx
.unit_done:
  ; ebx = how far this unit can go
  cmp ebx, ebp
  jge .not_worse
  mov ebp, ebx             ; update min_reachable
.not_worse:
  
  pop ecx                  ; restore unit_index
  inc ecx
  cmp ecx, unit_count
  jl .unit_loop
  
.done:
  mov eax, ebp             ; return min_reachable_position
  pop ebp, edi, esi, ebx
  ret

.single_unit:
  ; Call original MovePointsToPos
  mov edx, [edi+14h]
  mov eax, [edi+08h]
  call TMovepath.MovePointsToPos
  pop ebp, edi, esi, ebx
  ret
```

### What still needs to be determined

1. **Exact offset chain from `TMoveSettings` to the army object.** We know `TMoveControlSettings` has the army at `+0x9C`, but we need to trace how `TMoveSettings` reaches `TMoveControlSettings`. This may go through `TMoveSelector` or be stored directly.

2. **How to read path hex coordinates from the `XYLList`.** Each path entry is a packed `XYL` value (X, Y, Level in one DWORD). We need the unpacking logic, which is visible in the `TXYLList.Get` calls throughout the code.

3. **The `MoveTypesToInt` function address** — used in `TAbstractUnit.CreateMovePointTable` at line 5031. We need its exact address to call it, or we can inline it (it likely just returns the byte value directly, since the table is indexed by the raw move type byte × 256).

4. **The `CanMoveOn` adjustment** — `DefaultMoveOnMovePointProc` checks field flag `0x40` and calls `TMapField.CanMoveOn` which can modify the cost. Our per-unit walk should ideally replicate this, though it's an edge case.

5. **The `Transporter` check** — `TArmy.Transporter` determines if the army is being carried by a transport unit (ship, etc.). When transported, the transport's stats override individual units. Our fix should check this and use the original code path when a transporter is present.

---

## 5. Performance & AI Impact

### Why AI turns are slow

The `UseProcessTime` calls at `55745C58` and `55745CD3` confirm that the Dijkstra flood fill is metered against a time budget. Large maps with many AI armies each running floods is the primary bottleneck. The floods themselves are efficient (simple priority-less Dijkstra on a hex grid), but the sheer number of them on large maps with many AI factions adds up.

### Impact of each approach

| Approach | Flood cost | Path calc cost | AI impact |
|---|---|---|---|
| **Current (bugged)** | 1× | 1× | baseline |
| **B (multi-pass)** | up to 8× | 1× | **severe** on large maps |
| **F (post-path fix)** | 1× | ~8× but trivial absolute cost | **none** |

Approach F's per-unit path walk is O(units × path_length). Even with 8 units and a 100-hex path, that's 800 table lookups — roughly microseconds on any hardware. The flood fill, by contrast, touches every hex on the map potentially multiple times. Approach F is the clear winner for performance.

---

## 6. Next Steps

1. **Trace the exact data structure links** from the hook point to the army's unit list — this requires examining a few more functions or doing runtime debugging.
2. **Locate `MoveTypesToInt`** and verify the cost table indexing formula.
3. **Write the code cave** in x86 assembly, using the hook at `CalculateMovePositions`.
4. **Test** with your Cavalry+Elf and Floater+Swordsman scenarios.
5. Optionally, later pursue Approach B for the hex overlay fix as a separate enhancement.
