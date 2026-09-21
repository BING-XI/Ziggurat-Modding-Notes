# AoW1 Movement Predictor Fix — Applied 2026-07-05

## Status

**v4 PATCHED** — the game's `AoWEPACK.dpl` (in the install dir) contains the v4 fix.
Pristine original preserved as `AoWEPACK.dpl.bak` in the install dir.
Reproducible via `build_patch.py` in the install dir (verifies bytes;
refuses to patch on mismatch; idempotent over patch versions).

### v3 → v4: the display budget was stale (2026-07-05)

v3 testing: execution fully correct (mixed stacks, water, boats, splits),
but the arrows/X marker still showed the old pessimistic range.

Root cause: **`TSelectedArmy.Update` is event-driven, not per-frame** (the
old session summary claimed "refreshes every frame" — wrong; its only
callers are FinishMove, SendMsg, SetArmyHS, SetSelection,
RectangleSelectEvent, MouseDownEvent). The Update hook fired at selection
time, when the path is still empty, so its guard stored vanilla MIN(MP);
`CalculateMovePath` then built the path but never touched `+14h`, so the
arrows kept comparing against the stale MIN(MP) budget.

v4 adds a fourth hook: the `PosToMovePoints(path, 0)` call at `55792A18`
inside `TSelectedArmy.CalculateMovePath` (computing `+0Ch` total cost) is
wrapped by `cave_calcpath` (5580D87F), which returns the total as usual and
also stores `B* = PosToMovePoints(path, TrueReachPos(...))` into `+14h` —
the budget is refreshed at the exact moment the path is (re)built. Register
context at the site: EDI = TMoveSettings, ESI = TArmyHS, EDX = 0.
Side benefit: the road-building branch right below (Not-enough-MP check and
road gold estimate) now uses the per-unit-correct budget too.

| Hook | VA | Cave routine |
|------|----|--------------|
| TMoveArmyTE.Setup | 55747B01 | cave_exec 5580D700 |
| MoveArmyEx | 5574A36E | cave_movearmy 5580D711 |
| TSelectedArmy.Update | 557936A3 | cave_display 5580D71F |
| TSelectedArmy.CalculateMovePath | 55792A18 | cave_calcpath 5580D87F |

(shared core: true_reach 5580D75A, unit_walk 5580D7DB; cave total 419 bytes)

### v2 → v3: signed terrain/road bytes (2026-07-05)

v2 testing: execution distance fixed for land stacks, but arrows still
pessimistic, and everything water-related broke (sailing flyers halted at
water, boats immobile, walker-swimmers stuck, even a pure walker couldn't
split from a swimmer stack).

Root cause: the map field's terrain (+0x14) and road (+0x15) bytes are
**signed** — the game reads them with MOVSX everywhere, and road = −1 means
"no road" (that is why every cost lookup adds +1: column 0 is the no-road
column, and `MaximizeMovePointTable`'s 13-column sweep covers roads −1..11).
v2's cave used MOVZX, so on every no-road hex the lookup indexed 256 bytes
past the 256-byte table buffer into stack memory. The garbage is
deterministic per terrain row and call depth: land rows in the execution
hook happened to read plausible small costs (moves "worked"), water rows and
some others read negative/huge bytes (blocked), and the display hook at a
different stack depth read different garbage (arrows pessimistic while
execution was full-length).

v3 changes exactly two opcodes (MOVZX→MOVSX for terrain and road in
`unit_walk`); instruction lengths unchanged, so all cave labels and site
patches are identical.

**Rule: when replicating this game's table lookups, treat terrain, road,
and cost bytes as SIGNED chars, and keep the +1 road-column shift.**

### Confirmed table semantics (user's table images, in this folder)

The 256-byte cost tables are 16x16: **row = underlay terrain** (`field+0x14`:
Water, Grass, Desert, Snow, Steppe, Wasteland, Ice, Earth, Rock, Lava,
uWater, uWasteland, uDirt, uIce, Cost, Border) and **column = overlay**
(`field+0x15` + 1: None, Mount., Forest, Hill, Veget., Road, Bridge, Rubble,
Struc., Obstacle, L.Veg., Solid, Ooze, Res, Res, Res). The overlay byte is
signed with **-1 = no overlay** ("None" column); overlay 4 = Road (the
column the Enchanted-Roads modifier touches), 5 = Bridge.
`MaximizeMovePointTable`'s 13-column sweep = None..Ooze (skips Reserved).
A "forest hex" is Grass underlay + Forest overlay (walking cost 6).

The 8 base tables at 558E84FC..558E8BFC are, in order: Walking, Swimming/
WaterWalking/LiquidForm, Flying/Floating/WindWalking, Forestry, Cave
Crawling, Mountaineering, FireImm/FireHalo, Tunneling. NOTE the move-type
bitmask mapping from the precompute routine (FUN_55744b2c):
bit 0x01 = Walking, **bit 0x02 = Flying, bit 0x04 = Swimming** (the old
session summary had Swimming/Flying swapped), 0x08 = Forestry, 0x10 = Cave
Crawling, 0x20 = Mountaineering, 0x40 = Fire Walking, 0x80 = Tunneling
(0x80 is masked off when AoWHSMap+120h is nonzero).

### v1 → v2: the rebase lesson (2026-07-05, same day)

v1 crashed in the full game: *"Access violation at 00ECD829 in module
AoWEPACK.dpl, read of 558FA040"*. The DLL does **not** load at its preferred
base 0x55700000 in the real game process — it was rebased to ~0x00DC0000.
The loader relocates the game's own absolute references via the .reloc
section, but the v1 cave's `mov eax,[558FA040]` had no reloc entry, so it
read unmapped memory (AV) or garbage (one session showed sailing flyers
unable to enter water — junk map-container pointer producing junk costs).

v2 replaces that single absolute read with a call/pop position-independent
sequence: `call $+5; pop eax; sub eax, preferred_VA; mov eax,[eax+558FA040]`.
Everything else in the cave was already rel32/register-based and rebase-safe.

**Rule for future caves in this DLL: never embed an absolute VA without
either a reloc entry or the call/pop delta trick. Runtime patches (Cheat
Engine style) don't hit this because they're applied post-relocation —
file patches do.**

## The fallacious assumption in the previous attempt

The old session summary claimed: *"The actual per-hex movement execution is
correct — only the UI prediction is wrong."* **This is false.** Per-hex MP
*deduction* is correct, but the executed path is **truncated with the exact
same buggy math** before movement starts:

- `TMoveArmyTE.Setup` (55747AD4) computes
  `MovePointsToPos(path, TArmy.MovePoints(army, mask))` — MIN(MP) across units
  walked against merged MAX-cost hops — and copies only that prefix of the
  path into the move token. The units physically stop at the predicted 4
  hexes because the token never contained more than 4 hexes.

So a UI-only fix (the previous approach: hooking the X-marker call inside
`ShowMovePaths`) could never have worked — arrows would show 6 hexes while the
army still moved 4. Both sides had to be fixed, and the arrow-color logic
didn't need patching at all (see below).

## Corrected architecture findings

1. **`MovePointTables` (558EA040) is fully pre-computed.** `FUN_55744b2c`
   fills all 256 move-type-bitmask combinations at init, taking element-wise
   MIN across the 8 base tables (558E84FC..558E8BFC). The previous session's
   "unsolved problem" (per-unit table == merged table) was a diagnostic bug —
   unit[0] was almost certainly the Walking-only unit, whose individual table
   legitimately equals the merged table.
2. **`TAbstractUnit.CreateMovePointTable` (5577FDC4) is the authoritative
   per-unit cost function.** It copies `MovePointTables[moveTypes*0x100]` and
   applies enchantment/ability modifiers (road upgrade flag, abilities 0x17/
   0x01/0xA5, Haste 0x98, 0x84). Real MP deduction (`TAbstractUnit.MovedTo` →
   `MovePointCost`) uses exactly this: `cost = buf[1 + terrain*0x10 + road]`
   with terrain = `field+0x14`, road = `field+0x15`.
3. **Every UI element keys off `TMoveSettings+14h`**: arrow yellow/grey
   (running cost countdown vs +14h), X marker (`MovePointsToPos(path,+14h)`),
   multi-day turn number, `CalculateMovePositions`, and the ExecuteMove gold
   estimate. `TSelectedArmy.Update` (55793628) rewrites +14h every frame.
   Fixing the value stored there fixes the whole UI in one place.
4. **Correct GetField pattern**: container = `[[558FA040]+0x10]`, call stub
   `557020FC` with eax=container, edx=x, ecx=y, push level. (The old doc's
   "[AoWHSMap+10h] doesn't work" was a missing pointer dereference — the game
   itself uses this pattern inside `TSelectedArmy.Update`.)

## The fix

**Core routine `TrueReachPos(army, mask, path)`** (code cave at 5580D75A):
for the transporter (if any) or each selected unit — build the unit's own
cost table via the game's `TAbstractUnit.CreateMovePointTable`, then walk the
path from source toward destination deducting that unit's own per-hex cost
from that unit's own remaining MP (vtable+0xD8). The stack's reach = the
worst per-unit stop position. Position semantics identical to
`TMovepath.MovePointsToPos` (0 = destination, count-1 = source).

Special hexes (`field+0x19` flag 0x40, the `CanMoveOn` override case) use the
stored merged hop cost for all units — conservative, vanilla-equivalent.

**Three hooks** (all previously `call TMovepath.MovePointsToPos` or the
+14h store):

| Site | VA | What it fixes |
|------|----|---------------|
| `TMoveArmyTE.Setup` | 55747B01 | Execution-path truncation — armies now actually move the full distance |
| `MoveArmyEx` | 5574A36E | Destination-reached check — attack/negotiate/combine actions trigger correctly at true range |
| `TSelectedArmy.Update` | 557936A3 (13 bytes) | Stores synthetic budget `B* = PosToMovePoints(path, TrueReachPos(...))` into `TMoveSettings+14h`; arrows, X marker, turn numbers and gold estimate all follow |

The synthetic-budget trick: `B*` is the merged-cost prefix sum of the truly
reachable path prefix, so every vanilla consumer that walks merged costs
against +14h lands exactly on the true boundary hex — no changes needed in
`ShowMovePaths`' ~730 lines.

### Cave layout (5580D700, 371 bytes, zero-padding region of CODE section)

```
5580D700 cave_exec       shim for Setup    (army/mask from caller frame)
5580D711 cave_movearmy   shim for MoveArmyEx (army from esi, mask [ebp-1])
5580D71F cave_display    shim for Update   (writes +14h; falls back to
                                            vanilla MIN(MP) when no path,
                                            path < 2 entries, or no armyHS)
5580D75A true_reach      core (transporter case, per-unit MAX of stop pos,
                               empty-selection fallback to source pos)
5580D7DB unit_walk       per-unit path walk
```

## Deliberately left vanilla

- **AI call sites** (`TAIMoveExecuterControl.CreateMove`,
  `TAdjacentMEC.CalculateMeetingPoint`, `TTransportMEC.CreateTransporterMove`)
  — AI keeps vanilla pessimistic planning; AI-issued moves still benefit from
  the Setup fix when executed. Lower destabilization risk.
- **Multi-day tail prediction** (turn-boundary markers beyond the current
  turn) still uses merged costs / MIN moves-per-day — same as vanilla.
- `TSelectedArmy.ExecuteMove`'s post-move "continue next turn" flag check.

## Assumptions / limitations

- The DLL loads at its preferred base 0x55700000 (no ASLR on this binary; the
  previous session's runtime patches at absolute addresses confirmed this).
  The cave contains one absolute reference (`mov eax,[558FA040]`) with no
  reloc entry.
- Multiplayer: both clients should run the patched DLL (the move token
  carries the path, but reach checks run on each side).

## Test plan

1. **Forestry case**: Human Cavalry (36 MP) + Elf Archer w/ Forestry (26 MP)
   through forest — predictor should show 6 hexes yellow and one click should
   move them 6 hexes (was 4 + 1 + 1).
2. **Floating case**: Fire Elemental (4 MP, Floating) + Swordsman (3 MP,
   Walking) next to a road hex — should predict and execute the 1-hex move.
3. **Regressions**: single-unit moves, transporter (ship with boarded units),
   attack order onto an enemy at exactly max range (combat should trigger),
   move into friendly stack to combine at max range, multi-turn path arrows,
   hasted/slowed units, underground/cave paths.

## Revert

Copy `AoWEPACK_original_backup.dpl` over `AoWEPACK.dpl`.
