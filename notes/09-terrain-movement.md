# Terrain & Movement

Everything about the strategic-map hex/terrain system and strategic movement: terrain and overlay
ids, the movement-cost matrix, how a terrain change propagates into rendering (transitions, water
shores, roads, bridges, mountains), the two new flying/floating-only terrains (Chasm and Sky),
every terrain-changing spell, the Raise/Level Terrain pair, terrain-triggered unit effects
(elemental healing, fire healing fire units), the movement-predictor fix, and the Path-ability
terraform-on-move system. It does **not** cover: the general per-hex ring-detection RE technique
(used here by the Path outer-ring feature, but written up as a reusable technique in
`12-re-toolchain.md`); Grip of Winter's own cooling-ladder design (`05-spells-added.md` — this file
covers only the terrain-side coupling with Raise Terrain's underground-Earth feature); tactical
combat damage/terrain rendering; or unit-stacking/army mechanics.

## Status table

| Feature | Status | Owning script | Binary |
|---|---|---|---|
| Chasm & Sky — movement rows + Coast water-filter | 🔨 APPLIED, UNTESTED (v1 2026-07-24) · ✅ **v2 rows CONFIRMED WORKING (2026-09-21)** — Fly row fully open, Bridge column opened in the 5 walking-family tables | `build_chasm_sky_movement.py` | AoWEPACK.dpl |
| Roads on Dirt; bridges on Chasm and Sky (5 new resources) | ✅ CONFIRMED WORKING (2026-09-21) — 1131 children | `build_hss_addresource.py` | Release/Release.hss |
| Chasm & Sky — editor palette (brushes + cross-level) | ✅ CONFIRMED WORKING (2026-07-24) | `build_deved_terrainpal.py` | AoWDevEd.exe |
| Chasm & Sky — tile art, v2 grade | 🔨 APPLIED, UNTESTED (2026-07-30) | `build_chasm_sky_art.py` | Release/Release.hss |
| Chasm & Sky — cliff transitions, v2 remap | ✅ CONFIRMED WORKING (2026-07-27) | `build_chasm_sky_transitions.py` | AoWEPACK.dpl |
| Chasm & Sky — spell/ability guards (7 sites) | 🔨 APPLIED, UNTESTED (2026-07-27) | `build_chasm_sky_spellguard.py` | AoWEPACK.dpl |
| Chasm & Sky — per-hex animation | SPECULATIVE — fully designed 2026-07-30, declined by the user | none written | — |
| Chasm & Sky — structures: Sky reads as Chasm at the pad | ✅ CONFIRMED WORKING (2026-09-20) | `build_pad_skyalias.py` | AoWEPACK.dpl |
| Chasm & Sky — structures: no ground under a pad on Water/Lava/CaveWater/Chasm | ✅ CONFIRMED WORKING (2026-09-20) | `build_pad_transparent.py` | Release/Release.hss + 6 ILBs |
| **Firmament map level** — a 4th map level (index 3) filled with SKY terrain `0x0E`; surface-like vision, global-target spells, storm spells and Bird's View, `TCave.PlaceHX` guarded. Full record in `11-engine-internals.md` §"Firmament map level" | 🔨 APPLIED, UNTESTED (2026-09-06, v2) | `build_maplevel4.py` (+ in-place re-tunes of `build_shipyard_income.py`, `build_waterheal.py` v6; UI half `build_skylevel_ui.py`) | AoWEPACK.dpl + AoWz.exe + AoWzCompat.exe |
| Terrain rolls draw from the synced RNG (3 sites) | 🔨 APPLIED, UNTESTED (2026-08-31) | `build_rng_lockstep.py` (owned by the RNG/core-engine doc; two of the three sites are caves this file covers) | AoWEPACK.dpl |
| Ice Storm: Lava → Wasteland + per-proc skip gate | 🔨 APPLIED, UNTESTED — base redirect + 50% skip ✅ confirmed 2026-07-07; current 25% skip (same day) never retested | `build_icestorm_lava.py` — **⚠ never run `--apply` again**, see below | AoWEPACK.dpl |
| Raise Terrain: lava → 50% dirt, no mountain (surface) | ✅ CONFIRMED WORKING (2026-07-08) | `build_raiseterrain_lavadirt.py` | AoWEPACK.dpl |
| Raise Terrain: mountain art matches underlying terrain | 🔨 BUILT, NOT APPLIED (2026-07-07) — premise disproved in-game the same day; cave address now foreign, see below | `build_raiseterrain_mtn.py` — shelved, do not apply as written | AoWEPACK.dpl (would-be) |
| Raise Terrain underground → temporary Earth | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_raiseterrain_ug_earth.py` | AoWEPACK.dpl |
| Elemental terrain heal (Water/Air/Earth/Fire) | ✅ CONFIRMED WORKING (2026-08-30, v4) · 🔨 v6 Firmament (Earth excluded, Air included) APPLIED, UNTESTED (2026-09-06) | `build_waterheal.py` | AoWEPACK.dpl |
| Fire heals fire units (226/228) | ✅ CONFIRMED WORKING (v1 2026-07-07, v2 2026-08-29) | `build_firefeed.py` | AoWEPACK.dpl + AoWz.exe + AoWzCompat.exe |
| Movement predictor fix (v1→v4) | 🔨 APPLIED, UNTESTED (2026-07-05) | `build_patch.py` — **⚠ never run `--apply`**, see below | AoWEPACK.dpl |
| Path abilities: radius +1, 25% outer-ring proc | ✅ CONFIRMED WORKING (2026-07-08) | `build_path_outerring.py` | AoWEPACK.dpl |
| Move-cost: Sandworm/tunneler faster on desert | SPECULATIVE — feasible (85%/75%), not built | none written | — |
| Move-cost: Frostling/Azrac racial terrain bonus | SPECULATIVE — feasible (80%), not built | none written | — |

## Reference: terrain, overlay and hex geometry

### Terrain ids — the row of every movement/transition table (`field+0x14`)

| id | name | id | name |
|---|---|---|---|
| 0 | Water | 8 | RockWall (Rock) |
| 1 | Grass | 9 | Lava |
| 2 | Desert | A | CaveWater (uWater) |
| 3 | Snow | **B** | uWasteland → **CHASM** |
| 4 | Steppe | C | Dirt (uDirt) |
| 5 | Wasteland | D | CaveIce (uIce) |
| 6 | Ice | **E** | Coast → **SKY** |
| 7 | EarthWall (Earth) | F | Border (impassable to everyone; excluded from transitions) |

All 16 rows are allocated. A 17th terrain id would mean rewriting every 16-stride table, the
`terrain*16` transition-image-id scheme, resource registries and the editor palette — a rewrite,
not a patch. **B and E were free only because nothing shipped ever used them**: `B` (uWasteland) is
a byte-clone of the underground-wasteland pattern with no placed instances, and `E` (Coast) is a
byte-clone of the Water row (Swim 4, Fly 4, bridge-crossable, land-impassable, plus a
`TerrainChanged` special-case that renders it as plain Water — see Chasm & Sky below) that nothing
in the verified spell/terrain-write map ever writes to. Triumph's own editor terrain dropdown
labels `0xB` **"Reserved"**, confirming it was never given a real identity.

### Overlay ids — the column (`field+0x15`, signed, −1 = none)

None(−1), Mountain(0), Forest(1), Hill(2), Vegetation(3), Road(4), Bridge(5), Rubble(6),
Structure(7), Obstacle(8), L.Veg(9), Solid(A), Ooze(B), Res(C), Res(D), Res(E).

⭐ **Mountain is an overlay, not a terrain.** `TMountainMO.GetOverlay @0x557A2DC8` clamps any
declared value to 0, so "is this a mountain hex" is one compare — `[field+0x15]==0` — that works
identically on every terrain row and every map level (surface or underground). Plain hexes carry
`0xFF` (none), never `0`; adversarial proof: `TMoveControl.DefaultMoveOnMovePointProc
@0x557454D8` indexes `table[terrain*16 + overlay + 1]`, and if plain ground carried overlay `0` it
would resolve into the (mostly-impassable) Mountain column — the whole map would be unwalkable.

Columns entirely `0xFF` in every one of the 8 tables — free for new mechanics: **Solid (0xA)**,
**Res-D**, **Res-E**. **Res-C (0xC) is a vanilla flying-only column** (only the Fly/Float table has
costs there: 4 surface / 5 underground in the installed DLL) that nothing currently places.

### Movement cost — the (terrain × overlay) matrix

`TMoveControl.DefaultMoveOnMovePointProc @0x557454D8`: `cost = table[0x31 + terrain*16 + overlay]`
(row = terrain, column = overlay+1; `0xFF` = impassable, sign-extended). Eight 256-byte (16×16)
base tables, one per movement **ability**, static data in `AoWEPACK.dpl` — directly file-patchable:

| # | VA | Ability |
|---|---|---|
| 0 | `558E84FC` | Walking |
| 1 | `558E85FC` | Swimming / Water Walking / Liquid Form |
| 2 | `558E86FC` | **Flying / Floating / Wind Walking — one shared table** |
| 3 | `558E87FC` | Forestry |
| 4 | `558E88FC` | Cave Crawling |
| 5 | `558E89FC` | Mountaineering |
| 6 | `558E8AFC` | Fire Immunity / Fire Halo |
| 7 | `558E8BFC` | Tunneling |

At startup `SUB_L55744B2C @0x55744B2C` combines the 8 base tables (element-wise MIN) into all 256
move-type-bitmask combinations, `MovePointTables @0x558EA040` (BSS, 64 KB). **Patching the base
tables in the file changes movement for every unit, the AI, and the path preview at once** — no
code cave needed for a pure cost edit; the startup generator propagates it.

`TAbstractUnit.CreateMovePointTable @0x5577FDC4` is the single authoritative **per-unit** builder:
it copies `MovePointTables[moveTypes*0x100]` into a stack buffer, then applies enchantment/ability
modifiers (player road-upgrade flag; Enchanted/Cursed Roads abilities `0x17`/`0x01`/`0xA5`;
Haste-like ability `0x98`, cost−1 clamped ≥2; ability `0x84`, +2 to positive costs). Both real MP
deduction (`TAbstractUnit.MovedTo` → `MovePointCost @0x55780848`, `buf[1+terrain*0x10+road]`) and
the move-predictor cave (below) call exactly this function — **anything hooked here is consistent
between executed movement and the on-screen prediction for free**, which is why it is the injection
point for the two still-speculative move-cost features (Sandworm/desert, Frostling·Azrac/racial).

⚠ **Terrain, road/overlay and cost bytes in these tables are all `MOVSX`'d — signed chars, not
unsigned.** Road/overlay `−1` = no road; that is why every lookup adds `+1` (column 0 = the
no-road column) and `MaximizeMovePointTable`'s 13-column sweep covers `−1..11`. A cave that reads
these with `MOVZX` instead of `MOVSX` reads 256 bytes past a 256-byte buffer on the no-road column
and gets deterministic garbage that differs by call depth — see the Movement Predictor v2→v3 bug
below.

Consequences: Flying and Floating cannot be costed separately without splitting their shared table
(a 9th table + move-type-byte surgery). "Impassable to unit class X on terrain Y" mods are pure
data edits to the 8 base tables; combined tables live in BSS and can be poked live for
experimentation, but file-persistent changes belong in the 8 base tables.

⚠ **The installed tables are Ziggurat-rebalanced, not vanilla — 277 of 2048 cells differ from a
pristine reference copy of the DLL** (verified by byte-diff 2026-07-24). Broad strokes: Walking/
Forestry Ooze 8→12; Swimming water 4→3, gains land-Ooze swimming; Flying mountains 8→6, gains
Obstacle crossings; **Mountaineering gutted** from "walks normal land" to a pure mountains/hills
bonus table (6, incl. underground); Fire Immunity lava 4→3; **Tunneling massively expanded** from
EarthWall-only (10) to real overland movement (6–8) plus cheaper underground (EarthWall 10→8).
**Any script touching these tables must verify-before-write against the installed values, not
vanilla**, and any balance reasoning must state which baseline it uses.

### Hex geometry and where tile art lives

`px = hx*32 + 8`, `py = hy*32 + (hx&1)*16` (`HSEngine.HXtoHP`, HSEPack `0x5560E3B4`) — pitch 32,
odd columns pushed down 16. The hexagon's own drawn area (1056 px, rows widen 18→48 and back)
slightly overlaps the 32×32 lattice cell (1024 px) — that overlap is the engine's actual geometry,
not a bug; do not "correct" the pitch to 33 to make the areas match — it renders hairline gaps the
game never shows.

Static surface tiles (Grass, Desert, Snow, Steppe, wall, Border, uWasteland, Coast) are **embedded
in `Release/Release.hss`** as self-contained mini-ILBs (`\x04ILB\x00` header, ~3.4 KB each, one
8-bit hex bitmap per variant resource) — these tiles exist nowhere else. Animated or multi-image
sets are external `Images/*.ILB` by filename: `Waterhex.ILB`/`IceHex.ILB` (animation frames + shore
transitions, shared across every water/ice hex), `EARTHHEX.ILB`/`ROCKHEX.ILB` (underground solid
tiles), `HexTrans.ILB` (the shared transition-blend library, filename hard-coded in HSEPack),
`MOUNTAIN.ILB`. ⚠ `Images/BORDER.ILB` is a decoy — despite the name it holds *structure ownership
border* sprites, not the map-edge terrain; hexagon Border tiles are the embedded-in-.hss kind.

⚠ **`Release.hss` ends with a CRC-32 of everything before it.** `HSEngine.THSEngine.LoadHSS`
(HSEPack `5560F75C`) compares a stored trailing `u32` against `Engine.GetCRC32(file, size-4)`
(EngineP `5550E608`, table built at runtime — invisible to a static-table scan) and raises an
**unhandled** `Exception('Invalid HSSET')` on mismatch, so a patched-but-not-repaired `.hss` makes
**both AoWzEd.exe and AoWz.exe vanish at startup with no dialog**. Repair with
`re_tools/hss_crc.py <file> --fix` (the Chasm/Sky art script does this automatically). Not the same
container as `TEngine.ReadFromFileCRC` (EngineP `5551C084`, first-dword CRC over `file[4:]`, used by
other file types) — `.hsm`/`.csm` maps use neither (they start with the `"CFS\0"` magic).

⚠ **RLE row records inside a hex tile are 4-byte aligned**: the next record starts at
`align4(record_start + reclen)` (`ImageLib.TRLESprite16.RemapToPixelFormat`, ILPACK `55210AC7`).
Most tiles have a reclen already divisible by 4 so the padding never shows, but an odd-width tile
(e.g. 47px: `reclen=4+47*2=98`) does pad, and a decoder that misses this desyncs mid-tile and looks
exactly like corruption — **when a shipped asset looks corrupt, suspect the reader first.** Drive
the codec with `clipw`/`cliph`, not `w`/`h`. Tooling: `re_tools/ilb.py` (ILB parser),
`re_tools/ilb_rle16.py` (codec; `reskin()` rewrites only literal pixel words, payload length
can't change), `re_tools/hss_crc.py`. Facts: 48×32, RGB565, image type 17, transparent `0x594A`.

### Transition image-id space

`Images/HexTrans.ILB`, indexed by **image id = terrain*16 + k** (a 16-image block per terrain
type `T`):

| block | meaning |
|---|---|
| `T*16 + 0..2` | edge `d`, terrain `T` is the **neighbour** (drawn in place) |
| `T*16 + 3..5` | edge `d`, terrain `T` is **this hex** (drawn displaced onto the neighbour, flag bit `d+3`) |
| `T*16 + 6..14` | generic land-land edge: `+6+d+3·RandInt(3)` — 3 random variants per direction |

Cliff faces are special-cased ahead of the generic scheme: **`0xA0–0xA5` = the CaveWater edge = the
cliff** (`tu_xx-wa.BMP`; underground water sits below the floor, so its edge is a drop-off),
`0x90–0x95` = the lava edge (`tu_xx-la.BMP`, same idea). **`0xB6–0xBE` is only the underground-
wasteland *soft* blend (`tu_wl.BMP`), not a cliff** — conflating the two cost real time once, see
Chasm & Sky transitions v1 below. To give any terrain cliff edges, make the rule table treat it as
CaveWater (0xA).

## How terrain changes propagate

Every terrain edit — spell, storm, Raise/Level Terrain, this file's own features — goes through one
of two producer idioms into one shared consumer chain. Get the idiom right, or transitions, shores,
roads and bridges go stale.

### The two producer idioms

**A. `TAoWHSMap.ChangeTerrain` — map VMT `+0xD0`, `@0x55778D84`.** Single-hex direct set: `ret 0x10`
(`EAX=map, EDX=requester-or-0, ECX=x`; stack: `terrain, 0, level, y`). First reseeds
`System.RandSeed` from the synced game RNG (`AoWHSMap.Random(map, 0xFFFFFF)` at `0x55778D9A`), so
any cosmetic `RandInt()` the redraw does (resource-variant picks) stays deterministic across
multiplayer clients; then forwards into the shared HSEngine implementation, which does the actual
byte write and drives `TMapField.TerrainChanged` for that one hex — no validation/veto pass of its
own. Used by: the `MovedTo` EarthWall→Dirt collapse, Level Terrain's EarthWall→Dirt, Raise Terrain
underground's Dirt→Earth flip and its Grip-of-Winter-owned melt-back.

**B. `TAoWHSMap.ChangeTerrainEx` — map VMT `+0xD4`, `@0x55778DCC`.** Area+callback transactional
version: `ret 0x1C` (`EAX=map, EDX=requester-or-0, ECX=x`; stack: `changedCb, changedData, changeCb,
changeData, radius, level, y`). Also reseeds `RandSeed` first. Three passes over a hex spiral of the
given radius, under `LockTerrainChangedEvent`:
1. **Mutate** — save each hex's old `{terrain, overlay}`, run the caller's `changeCb(data, field,
   terrainBytePtr)` on a local copy, write the result raw into `field+0x14/+0x15`.
2. **Validate/rollback** — every HS on each field votes via virtual `+0x98 CanChangeTerrain`
   (overridden by `TStructure @0x5575EC1C` and `TArmyHS @0x55790DAC` — both veto; the
   terrain-adaptive MO family `TILTerrainMO`/`TFixedILTerrainMO` also votes — see Mountains below);
   any veto rolls that hex's bytes back. **`TMountainMO.CanChangeTerrain @0x557A2DDC` is
   `mov al,1; ret` — mountains explicitly allow terrain changes under them** (they re-skin or
   self-delete afterwards instead of vetoing). Validation runs with the whole disk already mutated,
   so a veto sees the new neighbourhood.
3. **Commit/notify** — surviving hexes get their new bytes re-written, `TMapField.TerrainChanged`
   fires (re-cache + 6-neighbour notify), and the caller's `changedCb(data, field, oldTerrain)`
   runs (post-work — e.g. Freeze Water spawning `TFrozenWaterHS` from the pre-change value).

`changeCb`/`changedCb` mutate the terrain byte **in place through a pointer** (`ECX`), exactly like
each storm's own `ChangeStormTerrain`. Used by: the storms (Ice/Death/Divine/Blast Storm, radius
growing 1→4 across four frames — see `TBlastStorm.UpdateStorm @0x557CCAC0`, which Ice/Death/Divine
Storm all inherit), the three Path abilities (radius hard-coded 1 at each call site, now 2 on the
outer-ring build below), and Freeze Water/Grip of Winter (radius 1).

**C. Raw write + `TMapField.TerrainChanged @0x55607CB4`.** No transaction, no veto pass — the caller
owns the consequences. What Flood/Restore (`TFloodControl.Flood/.Restore
@0x557F13D0`/`0x557F15CC`) and each storm's own per-hex loop do. Flood skips structures and
un-registers road HSes itself, but has **no army check** — unlike Freeze Water and the storms it
happily floods under a land army.

⚠ **Writing `field+0x14` without going through `TerrainChanged` is the stale-cache bug idiom.**
`TAoWHexagon.UpdateTransition` (the rule table below) reads the **neighbour field's cached** `+0x14`
byte, not the neighbour hexagon's live state — so a raw write that skips `TerrainChanged` leaves
stale edges until the next unrelated change kicks that neighbour.

### The consumer chain (why an edit redraws correctly)

`TMapField.TerrainChanged @0x55607CB4`: re-entrancy guard bit in `field+0x0F`; calls virtual `+0x9C`
on every HS on the field; re-derives the cached `field+0x14`/`+0x15` from the HSes' own
`GetTerrain`(+0x4C)/+0x58 (0xFF = ask the next HS); calls virtual `+0xA0` on every HS; then
`UpdateNeighbourTerrain @0x55607F9C` walks the 6 neighbours and calls
`TMapField.NeighbourTerrainChanged @0x55607F34` → virtual `+0xA4` on each HS there.

**Hex edge ownership — each hex owns only 3 of its 6 edges.** `THexagon.UpdateTransitions`
(HSEPack `55611DEC`) loops `UpdateTransition(d)` for `d=0,1,2` only; edge `d` looks at the neighbour
in HN direction `{6,1,2}[d]` (table `558E8DD8`) — the other three edges belong to the neighbouring
hexes, so no shared edge is computed twice. When a hex's terrain changes,
`THexagon.NeighbourTerrainChanged` (HSEPack `55611DAC`) reacts only for HN slot 0 and only for
incoming directions 1/2/6, remapping `1→edge0, 2→edge1, 6→edge2` and re-running that one edge.

**The rule table — `TAoWHexagon.UpdateTransition`, AoWEPACK `5579A9E0`.** Per edge `d`: clear the
slot, find the neighbour field, read `N`=neighbour terrain (`field+0x14` cache) and `O`=own terrain
(virtual `+0x4C`). No transition when: off-map, `N==O`, either negative, `N∈{7 EarthWall,
8 RockWall, F Border}`, `O==F`; also (generic tail) when `N∈{0 Water, 6 Ice}` — those edges are
handled by the water hex itself. Special-case order (first match wins): Lava↔CaveWater/CaveIce
(`0xB6+d`, shared soft block) or Lava↔Rock/Earth (none) else Lava edge (`0x90+d`/`0x93+d`);
CaveIce↔CaveWater pairing (`0xD0+d`/`0xD3+d`) else CaveIce generic (`0xD6+d`/`0xD9+d`);
CaveWater edge (`0xA0+d`/`0xA3+d` — **the cliff**); `N∈{Water,Ice}` → none; `O==Ice` vs Water
(`0x60+d`) or generic; `O==Water` (`0x03+d`); default → `O*16+6+d+3·RandInt(3)`. If the computed
index is out of range or `ImageLib.Get` returns null, **no transition is drawn at all** — adding a
new terrain means supplying its full 16-image block or its edges just don't blend.

Object layout (`TAoWHexagon`/`THexagon`): `+0x04`→owning `TMapField`; `+0x08`→hexagon resource
(`+0x20`=base-tile ILB, `+0x34`=transition ILB); `+0x10..+0x12`=per-edge transition image index
(byte, `0xFF`=none); `+0x13`=flags (bits 0–2 "edge has a transition", bits 3–5 "draw it displaced").
Drawing (`THexagonResource.Show`, HSEPack `55611FA4`) draws the base tile then, per set flag bit,
the transition image at a fixed pixel offset from the hex's own position — the displaced offsets
are exactly the delta to that edge's neighbour, which is how a flagged "terrain T is me" image
straddles onto the neighbour's tile.

**Water/shore (`TAoWWaterHexagon.UpdateTransitions`, AoWEPACK `5579AD98`)** ignores the 3-edge
scheme and walks all 6 neighbours itself: `hex+0x14` = 6-bit open-water mask (bit set when the
neighbour has no land hex and no border hex), `hex+0x15` low bits = coast mask, `hex+0x19+dir` =
per-direction shore tint (0x28 Snow-neighbour, 0x50 Wasteland-neighbour, else 0).

### Roads and bridges

Roads keep a 1-byte **connection mask** (`road+0x10`, bit `d−1` = HN direction `d` connected)
rather than blending terrain. `TAoWRoad.UpdateTransitions` (AoWEPACK `5579B84C`, **message
`0x1131`**) extends the base engine rule (`TRoad.UpdateTransitions`, HSEPack `55616F8C`, connects
to anything `FindOwnedHS`-matching `TAbstractRoad`, which also covers engine bridges): a neighbour
also connects if its field answers map-field message `0x1131` ("do you connect roads?") non-zero —
how city/structure hexes join the road net with **no road HS needed**. Composite codes: dirs 2+6
both set → `0x80`, dirs 3+5 both set → `0x40` (straight-through pieces). Drawing
(`TRoadResource.Show`, HSEPack `5561713C`): image = `1+code`; an **empty mask draws image 7** — an
isolated road hex still renders as a straight piece.

**Engine bridges** (`Bridge.TBridge`, HSEPack, road-carrying, multi-sprite): a 2-bit-per-direction
word (`0`=nothing, `1`=deck, `2`=bank ramp); `TBridge.UpdateTransitions @55617B60` classifies each
direction then keeps only the single farthest bank direction per shore group as the ramp.

**AoW hexagon bridges** (`HxBridge.THexagonBridge`, AoWEPACK — one-hex span over water):
orientation byte `+0x11` (axis 0/1/2 = opposite-pair 1↔4/2↔5/3↔6, `0xFF`=no valid span);
`DirectionValid @55799C04` requires **both** opposite neighbours to be land — the bridge sits on
water, its ends must be land. `NeighbourTerrainChanged @5579A054` recomputes and, if the
orientation ends `0xFF`, the bridge **frees itself** — terraforming away a bank is a legitimate
object-deletion path for a bridge, not a leak; don't be surprised by a bridge vanishing after a
nearby terrain-mod change.

### Mountains and terrain-adaptive map objects

Mountains are neither hexagons nor terrain bytes — they are map objects (`TMapObject`/`TMultiHexMO`
family) that publish a value into a footprint of fields' `+0x14`/`+0x15` caches and interact with
the terrain system through field caches, the `CanChangeTerrain` veto pass (above), and per-terrain
re-skinning.

| class | VA | role |
|---|---|---|
| `TMountainMO` / `TMountainMOR` | `557A27B0` / `557A28A0` | the vanilla mountain object/resource |
| `TMountainMO.CanChangeTerrain` = **always allow** | `557A2DDC` | mountains re-skin or die, never veto |
| `TMountainMO.GetOverlay` (clamps to 0) | `557A2DC8` | publishes overlay 0 |
| `TILTerrainMO` (generic terrain-adaptive base) | HSEPack `55618334` | `+0x18`=current terrain, `+0x14`=image index |
| `TILTerrainMO.TerrainChanged` (re-skin or self-free) | HSEPack `55618888` | image exists for new terrain → adopt it; else **frees itself** |
| `TFixedILTerrainMO.CanChangeTerrain` (the veto variant) | HSEPack `55618CA8` | non-mountain terrain-adaptive MOs *can* refuse a change they can't display |
| `TRaisedMountain : TILTerrainMO` (Raise Terrain's MO) | AoWEPACK `557A2A8C` | owner-turn countdown `+0x1E`; `RestoreTerrain @557A302C` frees it, re-places the field's *current* terrain |

**"One resource renders per-underlying-terrain"** — resolved 2026-07-24: the resource holds an
image per terrain type and the MO switches `+0x14`/`+0x18` on `TerrainChanged`, no per-terrain
lookup needed. **Terrain changes under a mountain re-skin or die, never veto** — vanilla leaks its
mountain object on a no-image failure (Raise Terrain underground's own marker does not, see below).
**Mountains do not split** on a partial-footprint clear, unlike the decoration/vegetation
`TTerrainMO` family (which has a single-cell-variant split mechanism) — the inherited
`TMapObject.MapFieldMsgProc` response to a footprint-clear message is "free the whole mountain."

## Chasm & Sky — flying/floating-only terrains

Two appropriated terrain ids, passable only by Flying/Floating, with their own art and cliff-edge
borders: **Chasm = `0xB`** (ex-uWasteland, an underground-flavoured row) and **Sky = `0xE`**
(ex-Coast, a surface row whose water-variant config gets overwritten). Chosen 2026-07-24 over an
"overlay terrain" alternative (mountain-pattern MO decoration, kept below as a fallback) because it
gets real hexagon art, native transition-system participation, normal editor placement, and lets
spells/storms exclude it by terrain id. Graphics source: the user's `Zigmod/Chasm.bmp`/`Sky.bmp`
(256×256 RGBA PNGs, despite the `.bmp` name).

All five build steps are applied; only the editor palette and v2 cliff transitions have an in-game
confirmation on record (see the status table). ⚠ `AoWEPACK.dpl` carries **four separate layers**
from this feature (movement, transitions, spellguard, plus whatever else has landed since) and none
of these five scripts has an automated `--undo`. ⚠ **There is no snapshot restore available** — every
`.exe`/`.dpl` `.pre-*` snapshot has been deleted, in three passes (2026-08-08, 2026-09-03, and
`<root>/backups/` on 2026-09-10), and `Ziggurat/backups/` is empty until a script mints into it.
(Only 10 *data-file* snapshots survive — `.ILB`, `.pfs`, `.ail`; no binary has one.) Use the
surgical byte-level reverts below; they are the only revert path.

### 1. Movement rows + Coast water-filter — `build_chasm_sky_movement.py`

Rewrote rows `0xB`/`0xE` in all 8 base tables (`558E84FC..558E8BFC`). **v2 (2026-09-20) is what is
live:**

| table | row `0xB` / `0xE` |
|---|---|
| Fly/Float (`558E86FC`) | **`04` × 16** — flyers cross whatever the hex carries |
| Walking, Forestry, CaveCrawl, Mountaineer, FireImm | `FF` × 16 except **column 6 (overlay 5, Bridge) = 3** |
| Swim (`558E85FC`), Tunnel (`558E8BFC`) | `FF` × 16 — ships do not sail a void, tunnellers do not burrow one |

⚠⚠ **v1's Fly row was `04 FF FF …` — 4 MP with NO overlay and every overlay column blocked**, which
this file used to describe as "every overlay combination is 4". It was not, and the difference was
load-bearing: `TStructure.GetOverlay @0x5575EBF0` returns **7**, so a structure standing on Chasm or
Sky could not be reached by anything, and razing one (overlay 6 Rubble) left a permanent hole. The
column, not the terrain, was the blocker. Bridges and roads were blocked the same way. Also carries an unrelated one-byte filter fix (`75→EB` at `0x5579A962`, see item 2 below).
Backup `AoWEPACK.dpl.pre-chasmsky`. Applied 2026-07-24; not itself in-game validated (placement and
rendering were tested, movement blocking was not — see status table).

**Neutralising the Coast water special-case.** `TAoWHexagon.TerrainChanged @0x5579A94C` fires only
for new terrain ∈ `{0, 6, 0xE}` and swaps the land hexagon for a `TAoWWaterHexagon`; the `0xE`
branch (`0x5579A9A6`) pushed terrain **0** instead of `0xE` — vanilla Coast was wired to render as
plain Water. Fix: (a) the `75→EB` filter patch above makes `0xE` fall through the family-filter
instead of taking the water-replacement branch, and (b) Sky hexagon resources are registered for
`0xE` in the land terrain control so the ordinary `TAoWHexagon.ChangeTerrain` relink path
(`GetRndResource(0xE)` → link → transitions → invalidate) handles Sky like any land terrain.

⚠ **Trap: `TAoWHexagon.TerrainChanged` treats terrain `{0, 6, 0xE}` as water-family** — anything
that ever reuses `0xE` for something else must re-neutralise this filter, and anything that reuses
`0x0` or `0x6` inherits the same trap.

### 2. Editor palette — `build_deved_terrainpal.py`, AoWDevEd.exe only

**✅ Confirmed in-game: terrain places from the palette.**

Adds Sky/Chasm brush buttons and makes the whole palette **cross-level** (every cave terrain also
gets a Surface-tab button and vice versa — a pure UI gap; `TMORTerrainControl.GetRndResource` keys
resources by terrain id only, the engine never had a level restriction). Cross-level buttons need
no new code (DFM `OnClick` handlers resolve by name against the form's published method table).
Sky/Chasm get two new handlers assembled from the shared 43-byte `TMainForm.<Terrain>BtnClick` stub
template (verified byte-identical to `uWaterBtnClick` at build time) and are named into the DFM by
**relocating** `TMainForm`'s published method table to a new PE section (`.ctp`) and repointing the
VMT's `vmtMethodTable` slot (`VMT-0x28`). Glyphs: the user's art masked to an existing terrain
glyph's hexagon silhouette; Chasm darkened (`CHASM_DARKEN`) so the two read as distinguishable. Full
DFM/VMT mechanism (reusable for any future editor button): `08-editor.md`.

⚠ **Layers on top of `build_dlgdirs.py` and `build_editor_toolbar.py`** — must run **after** them;
it reads whatever DFM the `TMAINFORM` resource entry currently points at. No automated `--undo`, and
⚠ **no `.pre-terrainpal` snapshot survives** — the `.pre-*` stack is gone (see §"four separate
layers" above). Revert surgically: the `.ctp` section + the `TMAINFORM` resource repoint.

### 3. Tile art — `build_chasm_sky_art.py`, target `Release/Release.hss`

**Applied, v2 grade (2026-07-30), untested at the current grade** — a v1 rendering pass was seen
in-game ("tiles render") but has since been entirely superseded by v2 in the same `.hss` layer
(v2 reused the v1-era backup, so the file carries exactly one art layer). All **23 tiles** re-skinned
in place (15 `Hu_wl`=Chasm, 8 `H_co`=Sky), file size unchanged, CRC repaired, re-run is a
byte-identical no-op. Backup `Release/Release.hss.pre-chasmskyart` — ⚠ does not currently exist.

⚠ **This script is BROKEN and cannot be run at all** (measured 2026-09-10). It dies before touching
anything: `FileNotFoundError: Ziggurat\Zigmod\Sky.bmp` — its source artwork directory is missing, and
`Ziggurat/Zigmod/` holds no `Sky.bmp`. This is **not** the 2026-09-09 exe rename; it is a missing
non-exe asset, and the failure is loud and reaches no binary. The **art is already installed** in
`Release/Release.hss`, so nothing is lost unless the `.hss` needs rebuilding. Open: locate or
re-create the source `.bmp` set before this script can ever be re-run.

**v1 was rejected by the user** ("the stars are too high-frequency") — a structural fault, not a
tuning knob: max-pooling the 256×256 source by 2 still packed ~33 stars per hex and flattened the
artwork's 4-point diffraction sparkles into shapeless 2×2 blocks.

**v2 — two different pipelines, one per terrain.** Sky (`0xE`) separates the two frequency bands
v1 conflated: a **nebula** layer (source downscaled 8×, blurred, sampled back magnified so even
the brightest source star spreads to +3 value — the dust disappears by construction; normalised
per tile to one fixed hue/contrast, or the field reads as a quilt of 8 differently-lit stamps)
plus **stars** stamped from the local maxima of the *original* art at native size with their
painted spikes, 1–5 per hex at hashed, jittered positions (a fixed count per hex draws a visible
grid). **Variant mix 85/15** (user's call): `GetRndResource` picks the 8 variants with equal
weight, so one slot (12.5%, closest to 15% obtainable) keeps the full v1 dense-starfield recipe,
plus 2 stamped crosses so the two designs read as related. Chasm (`0xB`) is **no longer a
starfield** (user: it should read as *a very deeply darkened sea*): the 16 shipped surface-water
tiles (`H_Wa2.BMP`, ids 140–155 of `Waterhex.ILB`) are copied 1:1 with no resampling, then
re-graded around a very low base that **expands** detail rather than the v1 `floor+slope·V` form,
which would have quantised the wave crests/troughs into the same RGB565 step at this darkness and
read as flat felt — a reusable lesson for any "make it very dark" re-skin in this game.

**Judging frequency needs a rendered hex field, not a tile strip** — the "too busy" complaint that
drove v2 was only visible once tiles were mosaiced at the engine's own `HXtoHP` placement (see hex
geometry above); `--preview` renders that mosaic in addition to a strip. Colour targets were
measured against the user's live map (deep water V≈0.37, land S 0.41–0.48, vanilla pixel-grain
contrast ~10–13; saturated colour is reserved for small magical accents, never field scale) —
the raw starfield failed on every one of those axes before the regrade.

### 4. Cliff transitions — `build_chasm_sky_transitions.py`, v2 applied 2026-07-27

**✅ Confirmed in-game: cliff edges render** (this reading refers to the current v2 remap — v1 was
tested and found wrong first, see below). Cave `0x55812000`, backup `AoWEPACK.dpl.pre-skytrans2`.

Inside `TAoWHexagon.UpdateTransition`, remap the working terrain values **O (EBP) and N (EDI) from
`0xB`/`0xE` to `0xA` (CaveWater)** — hook `0x5579AA92` (`movsx ebp,al` + `cmp ebp,edi`, 5 bytes) →
cave → back to `0x5579AA97` (a `jmp` leaves the flags the following `je` reads). The vanilla rule
table then does the rest for free on both sides: `O==CaveWater → 0xA3+d` (the void hex draws its own
displaced cliff lip), `N==CaveWater → 0xA0+d` (the land neighbour draws the cliff face in place).
Lava beside a Chasm still hits the shared `0xB6` lava↔cave-liquid block; CaveIce beside one hits
`0xD0+d`; Chasm next to Sky compares equal after the remap so no edge is drawn between them (both
are void — correct). The remap touches only edge *selection*; each hex's own base tile still comes
from its real terrain byte via `GetRndResource`.

**v1 was wrong** — it pointed Sky at the `0xB6` underground-wasteland *soft blend* instead of the
`0xA` CaveWater *cliff*, so edges rendered as a soft dark band instead of a drop-off (confirmed
wrong by the user's screenshot). v2's hook **reverted v1's hook at `0x5579AC74`** as part of landing
— v1 had jumped into the same cave address v2 reuses, so leaving it in place would have run v2's
code with v1's stale resume target.

### 5. Spell/ability guards — `build_chasm_sky_spellguard.py`, applied 2026-07-27

Seven effects made to leave terrain `0xB`/`0xE` alone. Caves at `0x55812100`+ (clear of the
transitions cave at `0x55812000`), backup `AoWEPACK.dpl.pre-spellguard`.

| # | effect | site | vanilla catch-all it was carved from |
|---|---|---|---|
| 1 | Death Storm | `TDeathStorm.ChangeStormTerrain @557CD304` | any land except 0/6 → Wasteland |
| 2 | Divine Storm | `TDivineStorm.ChangeStormTerrain @557CD6DC` | any land except 0/6 → Grass |
| 3 | Ice Storm | `TIceStorm.ChangeStormTerrain @557CCEF0` | catch-all `else` → Snow |
| 4 | Flood | `TFloodControl.Flood @557F1474` | floodable unless terrain∈{0,6,F} or overlay∈{0,2,7} |
| 5 | Raise Terrain | `TRaiseTerrainTE.ValidTargetMapF @557A35CB` | rejects only 0/6/A/D — a mountain could otherwise be raised on one |
| 6 | Path of Life (movement-triggered) | `PathOfLifeTerrainChange @557801A4` | any land except 0/6, surface only → Grass |
| 7 | Path of Decay (movement-triggered) | `PathOfDecayTerrainChange @557801C4` | any land except 0/6, surface only → Wasteland |

The two Path abilities are the likeliest to quietly eat a Chasm/Sky field during ordinary play (they
rewrite terrain as a carrying unit walks). Both are additionally gated to map level 0 in vanilla, but
the palette can place either terrain on any level, so both ids are excluded regardless. Death/Divine
Storm are tiny enough that their cave is the whole rewritten function (`jmp` in, `jmp` out); the
other five are 5-byte guards that re-do the displaced instructions, test for `0xB`/`0xE`, then either
take the "leave it alone" target or fall back into the original flow.

⚠⚠ **`build_icestorm_lava.py` — do not re-run `--apply`.** Ice Storm's `else`-site (`0x557CCEF0`)
was originally owned by `build_icestorm_lava.py` (lava→wasteland, below); this spellguard feature
**takes over that redirect and chains**: not Chasm/Sky → `jmp 0x5580DB20` (icestorm's own cave,
which still runs untouched); Chasm/Sky → the spellguard's own epilogue jump. Re-applying
`build_icestorm_lava.py` would rebuild the original redirect and **silently unlink the spellguard
chain** — the exact `build_magebane.py`-vs-`build_shield.py` failure mode already known from the
ability side of this project. `build_icestorm_lava.py`'s own docstring now carries this warning.

**Audited clean, deliberately not patched** (each tests specific ids and never matches `0xB`/`0xE`,
byte-diff-verified unchanged after applying): Fire Storm helper (6/D/2 only), Healing Showers
(2/4/5/9), Rejuvenate/Desiccate (1/3/4/5/C), Blast Storm (empty), Freeze Water (0→6, A→D, plus a
frozen-marker refresh), Level Terrain (EarthWall 7→Dirt only), Path of Frost (0→6/A→D plus the
same refresh) and Path of Sand (1/3/4/5/C). **The single distinction that predicted every hit and
miss in this audit: dangerous spells use a catch-all `else`; safe ones enumerate their source
terrains explicitly.**

### 6. Structures — the PAD is the gate and the mound, ✅ CONFIRMED WORKING (2026-09-20)

`build_pad_skyalias.py` (AoWEPACK.dpl) + `build_pad_transparent.py` (`Release/Release.hss` + 6 ILBs).

⭐⭐ **A structure's own per-terrain art does not decide where it can stand — its PAD does.**
`AoWE.TStructureResource.Create @0x5576046C` sets `res[0x44] = 1` unconditionally, so *every*
structure routes through the pad system: `TStructure.CanPlace @0x5575ECC8` → `TPadControl.CanPlacePad
@0x5574B958`, `TStructure.PlaceHX @0x5575ED10` → `TPadControl.PlacePad @0x5574B9B0`. A `TPad` is a
real map object placed underneath, with its own terrain-indexed art — **the raised lump of ground
under a tower is the pad, not part of the structure's sprite.** The Teleporter's own layer 1 is just
the stone circle; rendering `STR_TELE.ILB` 0/1/2 proved it.

Four pad resources live in `Release.hss` (class `0x20107` = `TPadResource`, ids 17/18/19/20), one per
footprint size, registered at index = hexes covered (`TStructureResource.CalculatePadIndex
@0x55760524` counts the resource's own `TTerrainList`). Vanilla fills slots **{1,2,3,4,5,11,12}**
with `Pad_Gr / Pad_De / Pad_sn / Pad_st / Pad_Wl / Padu_wl / padu_ca`, drawn lifted ~30 px — that
lift is the mound. ⚠ Terrain `0xB` was appropriated as **Chasm**, so `Padu_wl` (a wasteland mound)
was still being drawn under every structure standing over a void.

⭐ **Terrain validity is "does an image sequence exist at index == terrain id".**
`ILTer.TILTerrainMO.ValidTerrainType` (HSEPack `0x5561873C`) asks `GetImageSequence(VMT[0x12C]
GetTerrainTypeImage(t))`, and the base mapping (HSEPack `0x5561883C`) is literally `mov eax,edx /
ret`. When it fails, `GetValidTerrainType @0x55618780` tries `ForceTerrainType`, then **scans terrain
ids upward from 0 and takes the first that exists** — which is why a structure dropped on an invalid
hex silently converts the terrain. Vanilla stopped at 1 (Grass); once PAD1 gained a Water entry it
stopped at 0, so Sky hexes turned to Water.

**Sky (`0x0E`) cannot be authored in the editor at all**: a pad's slot list is 13 long (0..12) and
AoWzEd's index list is driven by that stored count, so there is no row 14. Hence the alias rather
than more data:

| what | where |
|---|---|
| cave `0x55819100`, 10 B | `cmp dl,0x0E / jne +2 / mov dl,0x0B / mov eax,edx / ret` — register-only, PIC |
| `Pad.TPad` VMT `0x557FE6C8` slot `+0x12C` | `0x5570353C` (HSEPack identity thunk) → `0x55819100` |

The slot already carried a `.reloc` entry and the new value is another in-module VA, so the
relocation stays correct (`build_relocfix.py --audit` clean). Because `ValidTerrainType` routes
*through* `GetTerrainTypeImage`, that one slot fixes validity and drawing together.

⚠ **`TStructure.GetTerrainTypeImage @0x5575E6A0` is deliberately NOT aliased.** The Teleporter has an
authored index-14 complex of its own; aliasing structure-side would discard it and hand Sky placement
to every structure carrying Chasm art. Structures without a slot 14 keep converting the hex — the
only difference is that they now land on Grass rather than Water.

`build_pad_transparent.py` then makes slots **0 Water, 9 Lava, 10 CaveWater, 11 Chasm** draw nothing,
across all four pads. It appends a fully transparent `RLESprite16` (named `ZIG_BLANK.BMP`) to
whichever ILB each slot already names — `PAD1..PAD4.ILB`, `TCOMBAT\BASE_HEX\H_ugWa.ILB`, `H_La.ILB` —
and repoints the slot's image index. ⭐ **The image index is a bare i32 inside the layer record, so
the `.hss` edit does not change length**: no directory offset moves, only the trailing CRC32 is
recomputed. `--undo` restored `Release.hss` byte-identical to its backup and every ILB to its vanilla
hash.

⚠ **A slot must keep an image; deleting it makes the terrain illegal again.** The slot existing is
the validity test, so "nothing drawn" has to be a transparent image, not an absent one.

⭐ **A fully transparent RLESprite16 is `cliph` rows of `08 00 00 00 <transparent u16> <clipw*2
u16>`.** No shipped tile uses that encoding, so the blitter was read rather than assumed: ILPACK
`0x55210B54` (from `TRLESprite16.ShowOpaque @0x55210310`) holds the transparent colour in **ESP** and
treats a `[transparent][skip-bytes]` pair as "advance the destination, write nothing" — including on
the `ecx < 8` tail path at `0x55210D0F`, which handles a marker as the only content of a row.

**The `.hss` image-sequence codec** (tag 10 of a `TMapObjectResource`): `u32 count`, then per slot a
marker byte — `1` empty, `0` present followed by layer records. A layer is `u32 namelen + name`,
`u8 layer`, `u8 flag`, `u8 mode`, then `mode 4`: `i32 image, i32 dx, i32 dy, i32 z, u32 nframes,
i32 frames[]`; **any other mode: `i32 image, i32 dx, i32 dy` and nothing else**, then `u8 more`
(1 = another layer, 0 = end of slot). ⚠ Missing the short mode-0 form desyncs the walk several slots
later and reports used slots as empty — it hid an authored Sky complex during this very
investigation. Cross-check: Teleport slot 12 layer 1 reads back the `Frame Table: 2` the editor's
Complex tab shows. Indices 20/21 are the destroy effect and smoke, 22–24 razed, 25–27 under
construction, 30–32 the `BORDER.ILB` ownership borders.

Confirmed in-game 2026-09-20: a teleporter on Sky keeps the hex as Sky, and Chasm/Water/Lava draw
stones with no ground underneath. Not separately observed, and cheap to glance at next time a map
calls for them: razed and under-construction teleporters on those four terrains, and an ordinary
structure dropped on Sky (expected to convert the hex to Grass rather than Water).

### 7. Roads and bridges on Dirt, Chasm and Sky — ✅ CONFIRMED WORKING (2026-09-21)

`build_chasm_sky_movement.py` v2 (the rows above) + `build_hss_addresource.py` (`Release/Release.hss`).

⭐⭐ **One road or bridge resource serves exactly ONE terrain.** `HSEngine.TAbstractRoad.CanPlace
@0x5560A820` compares `field[0x14]` against **entry 0 of the resource's own `TTerrainList`**
(`res[0x28]`, tag 7) and refuses on mismatch. `HxBridge.THexagonBridge.CanPlace @0x55799AE0` calls
that same function before its own axis test, so all three classes obey it:

| class | id | shipped terrains |
|---|---|---|
| `Road.TRoadResource` | `0x20165` | Grass, Desert, Snow, Steppe, Wasteland |
| `Bridge.TBridgeResource` (engine, road-carrying) | `0x20175` | Water, Lava, CaveWater, CaveIce, + Ice (Ziggurat) |
| `HxBridge.THexagonBridgeResource` (1-hex span) | `0x2087B` | Water, Ice, Lava, CaveWater, CaveIce |

So "roads on dirt" was never a movement problem — **Dirt already carried `Road=3` in vanilla** in
Walking, Forestry, CaveCrawl, Mountaineer and Tunnel. There was simply no road resource for terrain
`0xC`. Five records were cloned (donors chosen by the owner): Wasteland road → **Dirt road**;
CaveWater engine + hexagon bridges → **Chasm**; Water engine + hexagon bridges → **Sky**. Each new
record gets a fresh resource id (tag 1, the guid maps store), so no existing map is touched.

⚠ **Road and bridge art is embedded in the resource, not in `Images/`.** Tag 8 is a whole ILB
(`\x04ILB`, ~6.6 KB); the Desert road record is 6724 bytes and is almost entirely art. There is no
`ROAD*.ILB` on disk at all. That is why cloning a donor is the only cheap way to get art that fits —
and why each new record costs 6.7–11.4 KB.

⭐ `AoWE.Land @0x5575AEA4` (byte-identical to vanilla) returns *not land* only for
**{0 Water, 6 Ice, 9 Lava, 10 CaveWater, 13 CaveIce}** — so **Chasm and Sky already count as land**.
`THexagonBridge.DirectionValid @0x55799C04` requires both opposite neighbours to be land and
`NeighbourTerrainChanged @0x5579A054` frees the bridge when no axis qualifies, so a chasm bridge will
not delete itself. ⚠ The flip side: unlike a water bridge, it can be strung across open chasm rather
than only shore to shore, because the chasm hexes either side also read as land.

#### ⛔ The "1128-resource ceiling" was WRONG — it was a grid-slot collision (corrected 2026-09-21)

⚠⚠ **Do not trust any earlier note claiming `Release.hss` holds at most 1128 resources.** It does
not. The live file now carries **1131** children, loads in AoWzEd and runs in the game. What looked
like a count ceiling was an artefact of how the clones were built.

**The real fault.** `Engine.TEResource.ReadWrite @EngineP 0x5551B064` reads three fields:

| tag | field | meaning |
|---|---|---|
| 1 | `[res+0x0C]` | resource guid (what `zig_hsm.py` calls the guid) |
| 2 | `[res+0x10]` | **edit id** — which editor grid/tab the resource belongs to |
| 3 | `[res+0x14]` | **grid slot** — its position within that grid |

`EResGrid.TECustomResourceGrid.GenerateResourceEditList @0x5551FF14` walks the resource list,
filters on `[res+0x10] == [grid+0x240]`, and calls
`SetResource(grid, index = [res+0x14], resource)`. And `SetResource @0x5551FBB8` **destroys whatever
already occupies that slot**:

```
5551FBF7  call TList.Get          ; the current occupant
5551FBFC  mov dl,1
5551FBFE  mov ecx,[eax]
5551FC00  call dword ptr [ecx-4]  ; <-- its destructor
```

⭐⭐⭐ **So a cloned record that keeps its donor's tag 3 claims the donor's grid slot and FREES the
donor.** Every other reference to that object then dangles, and the first dereference is
`SetResource`'s own `call dword ptr [ecx+8]` on a heap-garbage VMT — the `EAccessViolation` with
fault address == read address.

The "any 2 pass, any 3 fail" pattern was counting **collisions**, not resources: every test clone was
taken from a donor and inherited its slot. Three freed objects was simply where one got dereferenced
before the run ended. The apparent count threshold, the file-size independence and the id
independence are all explained by that and needed no capacity limit at all.

⭐ **The fix is one i32 per clone**: allocate a fresh `[res+0x14]` within the donor's edit id.
`build_hss_addresource.py` now tracks the highest slot per edit id and hands each clone the next one.
Every road and bridge lives in **edit id 6**, whose slots ran 1..28 with a high-water mark of 36, so
the five new records took 37..41. Verified: no duplicate slot remains in edit id 6.

⚠ A donor with **no tag 3** cannot be cloned safely — its slot defaults to 0 and the clone would
collide there. The Desert road (`cid 121`) is such a record; the script aborts rather than clone one.

⚠⚠ **The debugging lesson is bigger than the bug.** Three independent, carefully-measured properties
(count threshold, not size, not content) all pointed at a capacity limit, and all three were
consistent with a completely different cause. Bisection localised *when* it broke and proved several
things it was not — but it could not say *what*, and the confident "1128 ceiling, editor-only"
conclusion drawn from it was wrong. Only the live stack trace settled it.

#### ⭐⭐ The faulting call, caught live (2026-09-21)

Caught with the standalone debugger server (see `12-re-toolchain.md`). Stack at the AV, on a
1129-child file:

```
0  0x0000180C                                             <- EIP, garbage
1  Enginep!EResGrid.TECustomResourceGrid.SetResource+0xa1
2  Enginep!EResGrid.TECustomResourceGrid.Activate+0x93
3  Enginep!EResGrid.TEResourceGridControl.MsgProc+0x57
4  Enginep!Engine.TENode.SendMsg+0x220
5  Enginep!Engine.TECustomNode.MsgProc+0x2c
6  HSEPack!HSSEdit.THSSEdit.Activate+0xa3
7  HSEPack!HSSEdit.THSSEdit.LoadHSSFile+0x6e
8  HSEPack!HSSEdit.THSSEdit.Load+0x93
```

Registers: `EAX 09780CE4  ECX 0977D8A8  ESI 00000003  EIP 0000180C`.

**The faulting instruction is `0x5551FC56  call dword ptr [ecx+8]`** in
`EResGrid.TECustomResourceGrid.SetResource @0x5551FBB8`, where `eax = [esp]` is the resource being
set and `ecx = [eax]` is its **VMT pointer**. `[0x0977D8A8+8]` held `0x180C`. So the grid is handed a
pointer that is not a valid object, and calls VMT slot `+8` on it.

Where the pointer comes from: `Activate+0x93` is the call to
`GenerateResourceEditList @0x5551FF14`, which walks the resource list at `[grid+0x264]` —
`VMT[0x54]` = count, `VMT[0x4C]` = get-by-index — filters on `[res+0x10] == [grid+0x240]` (the edit
id) and calls `SetResource` per hit.

⭐ **`ESI = 3` is the grid slot, and it is the whole story**: grid slot 3 belongs to the Wasteland
road (`cid 124`), which is exactly the donor the failing road clone was copied from. The clone stole
the slot and the grid destroyed the donor.

**Eliminated along the way, so nobody re-treads it:** `EngineP`'s `TPropertyTable` — `Add
@0x5550FEBC` grows through `SetCapacity @0x5550FB8C` (round up to a multiple of 32, `ReallocMem
capacity*8`) with no bound, and `LoadFromStream @0x5550FC3C`'s wide-entry loop counts in 16 bits,
topping out at 65535. `TENode.GetCount`/`GetChild` (`0x55519B40` / `0x55519ADC`) are
`[[self+8]+8]` and `[[[self+8]+4]+i*4]` over an ordinary Delphi `TList`, which has no such bound
either. Nothing in the container or the loader caps the resource count.


#### Raise Terrain: lava → 50% dirt, no mountain — `build_raiseterrain_lavadirt.py`

**✅ Confirmed working in-game (2026-07-08).** Lava is already a valid Raise Terrain target, but
mountain placement silently fails on it in vanilla, wasting the cast. Now each **lava** hex in the
area has a 50% chance to become **dirt (0xC)** with the normal green raise-glow but no mountain;
non-lava hexes keep normal mountain behaviour. Backup `AoWEPACK.dpl.pre-rtlavadirt`.

**Two patches, because of an animation-timing fix.** Vanilla places the mountain hidden immediately
and reveals it at glow **frame 9** (`NewFrameRaiseTerrainAnimation @557A31B0`); the first cut
changed terrain up front so dirt appeared before the glow peaked, so the flip was **deferred** into
that same frame-9 callback:
- **`cave_lavadirt`** (redirect at the per-hex loop `0x557A333E`, 5 B): if the hex is lava, roll —
  50% nothing, 50% set up the vanilla raise-glow block with no terrain change yet; non-lava replays
  the displaced instructions and takes the normal mountain path.
- **`cave_dirtdelay`** (redirect at `0x557A31E9`, augments the frame callback, currently
  `@0x5580DC20` — relocated once, see below): on frame 9, if the hex is still lava, flip it to dirt
  via the **lower-level** `HSEngine.THSMap.ChangeTerrainEx @0x557025D4` directly (not the
  `TAoWHSMap` VMT wrapper — see the RNG-guard note next), then replays the displaced instructions.
  Shared harmlessly with real mountains, whose hex is never lava.

⚠ **Failed approach, do not retry: calling the AoW-level `ChangeTerrain` wrapper (map VMT `+0xD0`)
from inside the frame-9 render callback.** That wrapper reseeds `RandSeed` via
`AoWHSMap.Random`, whose guard raises **"Invalid AoWHSMap.Random use"** when called from a
render/animation context rather than a synchronised one. A first attempt tried dodging this by
calling `HSEngine.THSMap.ChangeTerrainEx` at the wrong low-level address — **wrong**: that function
takes 7 stack params (`ret 0x1C`) versus the correct low-level call's 4, so the 4-arg call corrupted
the stack and produced **"Exception during AoWHSMap.NewFrame"** with no change at all. The fix that
shipped calls the correct lower-level function directly, which uses the raw (non-guarded)
`System.RandInt` and needs no flag juggling.

`cave_dirtdelay` was relocated from its original `0x5580DBD0` to `0x5580DC20` as part of that fix;
both the second lavadirt hook (`0x557A31E9`) and this cave are byte-identical and untouched by every
later feature that shares this cave neighbourhood.

⭐ **RNG note:** the 50% roll at `0x5580DB72` was also retargeted to the synced stub `0x55827000` by
`build_rng_lockstep.py` (2026-08-31) — live-verified 2026-09-03 (`call 0x55827000`, not the raw
thunk `0x55701080` this script's own docstring still describes; the docstring predates the retarget
and was never updated). Same undo-ordering coupling as Ice Storm above applies.

⚠⚠ **Coupling: `build_raiseterrain_ug_earth.py` has rewritten the head of this cave in place.**
Live-verified 2026-09-03 — `cave_lavadirt`'s first five bytes at `0x5580DB6C` now read
`cmp eax,9; jne 0x5580DB93; jmp 0x5583E180` (the underground-lava gate, `C_LAVAGATE`) where the
original was a plain `jne`+`mov eax,2`. **This script's own `--apply` can never succeed while Raise
Terrain UG Earth is installed** — its verify-before-write checks the range `0x5580DB60..0x5580DB93`
against its own recorded originals, which no longer match, and correctly aborts
("originals mismatch — not written") rather than overwriting the newer feature. See Raise Terrain
underground below for the full coupling and the required undo order. No automated `--undo`, and no
`.pre-rtlavadirt` snapshot survives — surgical revert only, and only *after*
Raise Terrain UG Earth has been undone first (same ordering rule).

## Raise Terrain underground: Dirt → temporary Earth

**🔨 APPLIED, UNTESTED (2026-09-03).** Written to the live `AoWEPACK.dpl`; every static and
round-trip check passes; nobody has played it. First applied 2026-09-02, then re-tuned in place
2026-09-03 with a sparkle fix (see §3 below). Script `build_raiseterrain_ug_earth.py`, backup
`AoWEPACK.dpl.pre-rtugearth` (taken 2026-09-02 from a file proved free of this feature).

```
underground (level != 0) + Dirt(0x0C)  ->  Earth(0x07) for 2-4 of the caster's turns,
                                            then back to Dirt, with the green raise glow
                                            AND the Freeze Water shimmer
```

Surface behaviour is completely untouched; no mountain placement changes anywhere. Revert:
`python build_scripts/build_raiseterrain_ug_earth.py --undo` — surgical, writes immediately, no
backup touched. **⚠ Revert order: undo this before `build_gripofwinter.py`** (§2 below).

### 1. Why underground casting was blocked, and the fix

`TGlobalTargetSpell`'s target-error routine (`@0x5579E73C`) tests a **surface-only flag byte** —
`TRaiseTerrain.Create` sets it at `0x557A3579` (`mov byte [esi+0x39],1`). **Fix: flip the immediate
at `0x557A357C` from `0x01` to `0x00`.** The script pins the three opcode bytes as context and
refuses to write if they don't match — a bare `01→00` at the wrong address would otherwise be
silent. Diagnosed originally by a third-party modder (Inioch) working from his own independently
patched copy, then re-verified here against both the live and pristine DLL. Neither
`ValidTargetMapF @557A35B8` nor `ValidTargetSelectionMapF @557A3610` has a level gate of its own —
see the open item on the overlay-non-zero requirement below.

### 2. The conversion cave, and where it hooks into the shared lava-dirt cave

`C_UGDIRT @0x5583E000` (267 B, part of a 512 B exclusive reservation `0x5583E000..0x5583E200`) is
reached by a `jmp` from inside `cave_lavadirt`'s non-lava branch (see the coupling note above) — for
hexes already past Raise Terrain's own per-hex validity check, stack layout unchanged from the
vanilla per-hex site. Gate: `field+0x14==Dirt(0xC)` and map level `!=0`; with the shipped
`EXCLUDE_ROAD_OVERLAY` knob (below) also `field+0x15 ∉ {4 Road, 5 Bridge}`. On a pass: find-or-create
a `TFrozenWaterHS` marker (same class Grip of Winter already extended), roll a duration via
**`AoWE.TAoWHSMap.Random @0x5577827C`** (`rng_audit.py` confirms `RaiseTerrain` is SYNC — 2..4 owner
turns, same formula shape as the vanilla mountain countdown), stamp `hs+0x0E=0x0C` (restore Dirt)
and `hs+0x0F=0x07` (set Earth), then flip via map VMT `+0xD0` = `TAoWHSMap.ChangeTerrain` (the
single-hex setter — **not** the 7-arg `ChangeTerrainEx`) with the vanilla raise-glow block still
running over it, no mountain placed. A failed marker create (`PlaceHX` fails — HS array full) frees
the orphan and leaves the hex untouched; **vanilla leaks its mountain object in the equivalent
case, this cave does not.**

⭐ **Marker/flip ordering is deliberate: stamp `+0x0E`/`+0x0F` before flipping the terrain.** The
flip's own `TerrainChanged` notification reaches Grip of Winter's `C_HSTC` cave, which keeps a
marker only if the hex's new terrain matches `+0x0F` — stamping afterwards would let `C_HSTC`
destroy the marker it needs to keep.

⚠ **QA-caught bug, fixed: the `ChangeTerrain` call's `EDX` (requester) argument is excluded from the
`CanChangeTerrain` veto poll.** Vanilla's `MeltIce` and Grip's own `C_MELT` both pass the marker
object there (not 0) — passing 0 only happened to work because `TArmyHS.CanChangeTerrain` nil-checks
it. Fixed to match vanilla, and done before the register holding it gets clobbered.

### 3. Grip of Winter dependency — hard, and mutual

`build_gripofwinter.py` already extended `TFrozenWaterHS` (instance size `[VMT−0x1C]=0x10`) with the
exact two padding bytes this feature needs, and its four caves are the *only* consumers:

| Grip cave | hook | does |
|---|---|---|
| `C_RW @0x5582A320` | `0x55764ACB` | persists `+0x0E` as property id `0x20`, `+0x0F` as `0x21` — save/load |
| `C_MELT @0x5582A3A0` | `0x55764AE0` | `+0x0E!=0` and terrain still `+0x0F` → `ChangeTerrain` back to `+0x0E`, else free — **the revert** |
| `C_HSTC @0x5582A460` | `0x55764B8B` | keep the marker only while the hex still holds `+0x0F` |
| `C_SHOW @0x5582A4E0` | `0x55764BD0` | `+0x0E!=0` → draw nothing — **the sparkle gate, see §4** |

This feature writes **none** of those — it only mints a marker saying "restore Dirt, I set Earth."
**⚠⚠ `build_gripofwinter.py` must stay applied — without its four hooks the raised earth is
permanent.** `build_raiseterrain_ug_earth.py --apply` refuses to run at all if any of the four hook
sites isn't a live `E9` redirect, or if `C_SHOW`'s body isn't one of the two images it recognises.
Property tables are id-indexed, so a save from before either feature simply lacks ids `0x20`/`0x21`
and loads both as 0 — a vanilla ice marker, harmlessly.

**The dependency runs both ways once both are installed**, because this feature also rewrites six
bytes inside Grip's `C_SHOW` cave (§4) and five bytes inside `cave_lavadirt` (above). Both of those
scripts now byte-compare against images that no longer exist, so **both abort cleanly before
writing anything**: `build_gripofwinter.py --apply`/`--undo` print `cave 0x5582A4E0 is foreign` /
`state: MIXED`; `build_raiseterrain_lavadirt.py --apply` prints an originals-mismatch abort.

```
*** UNDO build_raiseterrain_ug_earth.py BEFORE build_gripofwinter.py OR build_raiseterrain_lavadirt.py ***
```

Undoing this feature restores `C_SHOW` and `cave_lavadirt`'s original heads byte-exactly, handing
both other scripts their own `--apply`/`--undo` back. Nothing is corrupted by the wrong order —
every script aborts safely before writing — it just will not proceed until this one is undone first.

**Why rewrite someone else's cave at all:** `build_raiseterrain_lavadirt.py` owns the only usable
post-validity injection point in the per-hex loop (the instruction before it carries a `.reloc`
entry and must not move); that script has no `--undo` and no trustworthy backup, so it could not be
reverted first. Same in-place cave-rewrite pattern as `build_invis_penalty.py` over
`build_trueseeing.py`'s caves: built by copying the *installed* image and editing the copy, so the
unrelated lava-roll logic can never drift.

### 4. The sparkle — a correction to `05-spells-added.md`

First in-game-adjacent read of the design surfaced a misreading: `C_SHOW`'s gate (`+0x0E!=0` →
"draw nothing") was documented there as suppressing an "ice sprite." **It does not — there is no
separate ice sprite.** `TFrozenWaterHS.Show` makes exactly one call,
`ImageLib.TImageSequenceList.ShowLoopedEx` (a looped animation driven by a global tick and a
per-hex phase so neighbouring hexes don't pulse in sync) — that call **is** the shimmer, full stop;
the ice *look* comes from the terrain byte itself via the ordinary terrain renderer. So `C_SHOW`'s
gate is all-or-nothing on precisely the thing this feature's raised earth needed, and since this
feature's markers set `+0x0E=Dirt` (non-zero), they were being caught by it — raised earth converted
and reverted correctly but never shimmered.

**Fix — `C_SHOWGATE @0x5583E140`** (22 B, inside the same exclusive reservation): replace `C_SHOW`'s
first six bytes with a jump into a re-implemented predicate carrying one extra clause — `+0x0E==0`
(plain ice) **or** `+0x0F==7` (our raised-earth marker) → play the shimmer; anything else (Grip's own
cooled-land markers) → stay hidden. Both outcomes jump back into `build_gripofwinter.py`'s own
remaining bytes, which are otherwise completely untouched — proved by the fact that Grip's two other
marker states (vanilla ice `0/0`, cooled land `{2,4,1}/{4,1,3}`) both still resolve to exactly the
branch they took before this patch existed.

⚠ **`+0x0F==7` is a safe discriminator only while Earth stays off Grip's own cooling ladder**
(Desert→Steppe→Steppe→Grass→Grass→Snow, values `{1,3,4}`; its ice arm only ever writes `{0}`). If
Earth is ever added to that ladder, Grip's cooled land would start shimmering too — the fix at that
point is to also require `+0x0E==Dirt`. The shimmer has no tint parameter (fixed sequence index
`0x46`), so raised earth shimmers identically to Freeze Water ice.

### 5. Knobs (both shipped ON)

| knob | shipped | effect |
|---|---|---|
| `EXCLUDE_ROAD_OVERLAY` | `True` | Skips hexes with a road/bridge overlay. **This is data-loss avoidance, not a style choice** — converting terrain under a road/bridge deletes it permanently (the restore puts the terrain back but not the overlay), a real bug independently found by a third-party modder using the same underlying machinery. Do not turn this off. |
| `LAVA_SURFACE_ONLY` | `True` | The lava→50%-dirt arm stays surface-only underground lava was unreachable before this feature existed, so there was no defined vanilla answer for "what should underground lava do" — ruled 2026-09-02 that unlocking underground casting must not silently invent new lava behaviour. `False` would extend the 50% roll underground too. |

### 6. Design decision: converts up front, not at the lava arm's glow-frame-9

Unlike the lava-dirt arm (flips at frame 9 to match its glow reveal), this feature converts
**immediately**, in the synchronised terraforming call, letting the glow be purely cosmetic:
(1) touches nothing at the second lava-dirt hook, so the blast radius over that script is one jump
displacement, not two caves; (2) marker spawn, duration roll, owner and terrain change all happen
in one fixed synchronised order, so MP peers cannot diverge (the frame-9 route is already a known
MP residual for the lava arm — no reason for a second one); (3) no RNG-guard flag juggling, since
the variant roll from inside the synchronised TE draws SYNCED already; (4) robust to a
culled/skipped animation — an up-front flip has already committed, where a frame-9 flip would leave
a marker promising to restore terrain that was never set. Cost: the earth appears the instant the
spell resolves rather than at the glow's peak, and there is deliberately no knob for the other
timing (it would mean rewriting `cave_dirtdelay`, the whole thing this choice avoids).

### 7. Declined fix: countdown underflow

`TFrozenWaterHS.NewTurn @0x55764B98` decrements the countdown **before** checking it (unlike
`TRaisedMountain.NewTurn`, which checks first) — if something vetoes the terrain change, the marker
survives and the counter runs past zero. **Measured, not assumed:** the compare is signed, so
`0→0xFF` (−1) still calls `MeltIce` every subsequent turn — 129 turns of retrying, then one 127-turn
dormancy, then retrying resumes. Never permanently stuck. **Declined**: the fix means editing
vanilla `NewTurn`, shared with plain Freeze-Water ice and Grip's cooled land, for a case needing 129
consecutive vetoed turns first — and `ValidTargetMapF` already rejects any hex with a `TStructure`,
so this feature's own markers can never be created under one. If ever wanted, the fix (saturate
instead of wrap) belongs in `build_gripofwinter.py`, which owns the class.

### 8. Still needs the user's in-game test

1. Casting underground at all — cursor highlights underground hexes, cast goes through, no "must be
   cast on the surface" message. If it refuses, check the overlay-non-zero open item below first.
2. Underground Dirt → Earth, green raise glow, no mountain placed.
3. The Freeze Water shimmer plays on the raised earth (the whole point of the §4 re-tune).
4. Reverts to Dirt after 2–4 of the caster's turns.
5. Roads/bridges under the target hex are skipped, not destroyed.
6. Underground lava is unaffected (vanilla mountain path, no 50% dirt roll).
7. Surface behaviour is completely unchanged (lava still rolls 50% dirt at glow frame 9, Raise
   Terrain still raises mountains everywhere else).
8. Grip of Winter still looks right: plain ice still shimmers, cooled Desert/Steppe/Grass does not.
9. Save/load with a raised-earth hex standing — must reload and still revert on schedule; a
   pre-feature save must still load with its ice markers melting normally.
10. Re-casting on an already-raised hex keeps the marker's original restore terrain.
11. No "Invalid AoWHSMap.Random use" popup at any point.

## Elemental terrain heal

**✅ CONFIRMED WORKING (2026-08-30, v4)**, user in-game test · **🔨 v6 Firmament APPLIED,
UNTESTED (2026-09-06)**. Script `build_waterheal.py` (filename kept from v1 for continuity;
output/log label "elemheal"). Patches `AoWEPACK.dpl` only — no exe patch, no `.pfs` edit. Backup
`AoWEPACK.dpl.pre-waterheal` (taken only from a byte-proven vanilla state, never overwritten again
— it functions as a second vanilla reference for this one hook site). **Revert: `python
build_waterheal.py --undo`** — surgical, restores the 8 hook bytes at `0x557803BA` and zeroes the
full **v6** cave (`LEN6` = 360 B — **not** the v5 length of 354 B or the v4 length of 344 B),
touches no backup. No `.pre-*` snapshot is a revert path for it.

Once per hex **entered** during strategic movement, on the moving unit's **own** movement only
(HP amounts are the displayed, post-DAM/HP-doubling values):

| elemental | Unitres id | heals on | HP/hex | chime volume |
|---|---|---|---|---|
| Water | 227 (0xE3) | terrain Water(0) or cave water(0xA), any level — Ice(6) does **not** count | +2 | 50/100 |
| Air | 224 (0xE0) | any terrain, surface only (`level==0`) — **v6 (2026-09-06): the Firmament (level 3) too** | +1 | 25/100 |
| Earth | 225 (0xE1) | any underground level, **or** a Mountain-overlay hex on any level — **v5 (2026-09-06): excluded outright on the Firmament (level 3), including the Mountain-overlay case** | +1 | 25/100 |
| Fire | 226 (0xE2) | terrain Lava(9) | +4 | 50/100 |

**In-game check for v5/v6 (2026-09-06):** Earth elemental on the Firmament (level 3) — no heal, no chime.
Earth elemental on any underground level, and on a Mountain-overlay hex on any *other* level — still
+1 with the quarter-volume chime (only the Firmament case is now excluded). **Air** elemental on the
Firmament — +1 with the quarter-volume chime, exactly as on the surface; still +1 on the surface,
still nothing on Caverns or Depths.

**v6 (2026-09-06), the Air row.** The air arm at `0x5582407E` was `cmp byte [esi+0x12],0 / jne _out`
(surface index only); it becomes `cmp 0 / je _airok / cmp 3 / jne _out`, +6 B, cave 354 → **360 B**.
Rewritten in place over the installed v5, with the growth zone asserted zero — never revert-and-
reapply. So the two arms deliberately disagree about level 3: the Firmament is open sky, which is
air's element and is not earth's underground.

Shared rules: **own movement only** — an elemental riding in a transport doesn't heal, mirroring the
Path abilities' own gate; the check is army-level (a transported elemental counts as carried unless
it IS the transporter, even if it could self-propel). Heals only if `hp<max` (the setter clamps
anyway). The Healing ability's chime plays **iff a heal actually happened** and the hex is visible to
the local player — **the heal itself is never fog-gated** (multiplayer determinism: fog only gates
presentation). Nature Elemental (80) is excluded by ruling; tactical-combat movement is out of scope
(a separate exe-side system).

**Hook: `0x557803BA`**, inside `TAbstractUnit.MovedTo @0x55780328` (the per-hex-entered chokepoint —
EBX=unit, ESI=entered field). Replaces 8 bytes (`movsx eax,[esi+0x14]; cmp ax,7`, the vanilla
EarthWall/tunnel test) with a jump to `cave @0x55824000` (360 B at v6, verified all-zero
`0x55823E00..0x55825200` before install); the cave replays the displaced pair last so their flags
feed the following `jne`, then resumes at `0x557803C2`.

⚠ **Trap: predict the vanilla bytes to match from the file, never from disassembler mnemonic text.**
Two encodings of `cmp ax,7` exist (imm16 vs imm8 form); the planning pass guessed the wrong one,
caught only by byte-diffing the live file before patching. Do NOT hook the `MovedTo` epilogue at
`0x5578051B` — that belongs to `build_ai_itempickup.py` (the Magebane/Shield tail-chain lesson
applies to any epilogue hook in a function this many features share).

### Cave structure and dispatch

Fully PIC (no absolute memory operand; globals via `call $+5; pop` anchors, all calls rel32).
Sequence: fetch terrain/precondition, one shared 4-register-pop epilogue for every exit;
**transport gate** replicating the Path-ability transport wrapper's truth table *inline*, calling
vanilla `TArmy.Transporter` directly so the two features stay independently undoable either order
(verified both ways); **unit identity** via the same idiom Fire Heals Fire Units uses
(`unit+0x40`→resource→list→`UnitResourceIndex`; heroes cannot misfire, max hero-resource id 55);
**dispatch** on index `0xE0..0xE3` into four condition blocks reading terrain `[esi+0x14]`, level
`[esi+0x12]` (0=surface), overlay `[esi+0x15]` (0=mountain, 0xFF=none); each block packs
`EBP=(chime_volume<<16)|heal` into the one free callee-saved register, surviving every intervening
call; **HP gate** — `GetHitPoints`/`GetHits` are raw bytes that must be `movsx`'d before the 32-bit
compare (the DAM/HP dirty-upper-bits lesson); `hp>=max` skips both heal and sound; heal via vcall
`SetHitPoints` (clamps `[0,GetHits]`); **fog gate, sound only, deliberately after the heal** —
`TAoWHSMap.WatchingTerrain @0x55775ABC`, false skips only the chime; chime via `PlayEx` (below);
epilogue, tail-replay, resume.

### ⭐ Reusable machinery found here

**`PlayEx` — play any ability's sound effect at a per-call volume.** Thunk
`Sound.TSFXLibrary.PlayEx @0x55702CFC` (impl SoundP.dpl `0x5540605C`, `ret 0x14`): `EAX`=SFX library,
`EDX`=sound index within it, **`ECX`=volume on a 0–100 scale** (engine callers pass `0x64`/`−1` for
default; `0x32`=half, `0x19`=quarter — both ear-validated in-game). Five stack args, first-pushed =
loop flag (0=one-shot), then delay, `1, 0, 0`. To get an ability's library: `[GetAbility(id)+0x18]`.
**Do not use `Sound.SetSFXVolume` for a per-sound volume — it is process-global** and ducks
everything else playing.

**Mountain is an overlay, not a terrain** — restated here with the adversarial movement-table proof;
see the Reference section above for the full statement.

### Version history (all in-place rewrites — never revert-and-reapply)

v1 (2026-08-29): Water Elemental +2 on water, 50% chime. v2: + transport gate. v3 (2026-08-30):
per-elemental dispatch, Air/Earth/Fire added. v4: per-elemental chime volume via the EBP pack. The
script recognises vanilla/v1/v2/v3/v4 by regenerating each version's exact cave bytes and rewrites
in place from any older recognised state (the growth zone must verify zero); a corrupt/foreign state
refuses dry-run, apply and undo alike.

**Co-residents in `TAbstractUnit.MovedTo`, all verified untouched both ways:**
`build_path_transportgate.py` (retargets the `Transporter` call at `0x55780407` to a wrapper),
`build_ai_itempickup.py` (epilogue hook `0x5578051B`), `build_path_outerring.py`'s centre-stash hook
(`0x5578041E`, see Path abilities below). No undo ordering needed — this feature chains with none of
them.

**Failed/rejected approaches — do not retry:**
- Delivering the heal via `ExecuteDamageRole` (the fire-heal route below) — imports a to-hit roll
  and a Defence dependency; this heal is a plain `SetHitPoints` write and should stay one.
- `Sound.SetSFXVolume` for the half-volume chime — process-global, ducks everything.
- Fog-gating the heal itself — never; multiplayer determinism requires the heal to happen
  identically regardless of who can see the hex. Only the sound may consult visibility.

## Fire heals fire units (226 Fire Elemental / 228 Fire Sprite)

**✅ CONFIRMED WORKING** — v1 (heal + "+N" popup) validated in-game 2026-07-07 for both Firestorm and
map-hex fire/Fire Barrier; **v2 (no to-hit roll) validated 2026-08-29.** Script `build_firefeed.py`
patches **three** files: `AoWEPACK.dpl` (3 caves + 3 redirects),
`AoWz.exe` + `AoWzCompat.exe` (1 five-byte patch each, byte-identical site). No automated `--undo`;
surgical revert restores the 3 `AoWEPACK.dpl` redirects, the 1-byte patch at `0x436BFF` in each exe,
and zeroes the 3 caves (`cave_fireheal@0x5580DA20` 89 B, `cave_plusnum@0x5580DA80` 68 B,
`cave_mapfire_gate@0x5580DAD0` 71 B). ⚠ **No `.pre-firefeed` snapshot exists any more** — every
binary `.pre-*` was deleted (2026-08-08, 2026-09-03, and `<root>/backups/` on 2026-09-10). The
surgical path above is the only revert.

Fire damage **heals** unit resource-index 226/228 instead of doing nothing (they carry vanilla fire
immunity). Sources: Firestorm, map-hex fire, Fire Barrier. Tactical-combat fire (fireball/breath/
aura, a different code path — `TCombatObject.ExecuteDamage @0x55726C58`) is out of scope. Design
decisions (2026-07-06/07): heal amount = the would-be fire damage; popup shows the heal as `+N`.

### The one chokepoint: `TAbstractUnit.ExecuteDamageRole @0x55781AC4`

The shared resistance calculator for all environmental/"role" damage (fire, poison, holy, storms).
`EAX`=unit, `EDX`=strength, `ECX`=role/dice-type, `[EBP+8]`=16-bit damage-type set, returns damage in
`EAX`, `RET 4`. Body: if immune to every bit in the damage-type set → **return 0 without
computing** (this is why 226/228 needed a dedicated cave rather than a display fix — they never
reach the roll at all); otherwise roll `ExecuteDamageRole_500B4C01(damage, strength−GetDefense)` at
`0x55725EAC` (stat is **Defence**, `vtable+0xC4` on `TAbstractUnit @0x55710740` — a 2026-08-03 doc
edit briefly mis-recorded this as Resistance `+0xCC`; it never was), then halve if fully protected.

**Map-hex fire needed a second fix.** `TArmy.TriggerFireDamage @0x55790110` pre-gates its per-unit
loop on immunity and never calls `ExecuteDamageRole` for a fire-immune unit at all — so originally
only Firestorm (whose own `ExecuteStormDamage` has no such pre-gate) could heal 226/228.
`cave_mapfire_gate` redirects the 5-byte immunity test at `0x5579020C`: non-immune units are
unaffected; fire-immune units now check the unit index too — 226/228 still reach the damage path,
every other fire-immune unit still shows "immune."

**Unit identity, position-independent:** `unit+0x40`→`TUnitResource`, `+4`→owning list, vcall the
list's `UnitResourceIndex` slot (`+0x84`) → index; compare `0xE2`/`0xE4`. Heroes store their resource
at the same `+0x40` offset but from a different owning list, so the lookup returns a small hero
index and safely falls through — a null-resource guard is added as extra insurance regardless.
`TUnit.SetHitPoints` clamps to `[0, GetMaxHP]`, so the heal cannot overflow the HP byte
(`TAdjustableUnit.SetHitPoints` does *not* clamp, but that class is never the in-play map unit).

### Mechanism: return the negated roll

Every fire caller does `dmg = ExecuteDamageRole(...); if HP<dmg then dmg=HP; SetHP(HP-dmg)` and logs
`dmg` into the event-log the Party-Damage popup renders. For 226/228, `cave_fireheal` returns
**`-roll`**: the `HP<dmg` clamp is skipped (negative never exceeds HP), `SetHP(HP-(-x))` heals, and a
storm's `if 0<dmg` secondary-effect guard is false (no burn). The logged byte is negative, so the
display patch renders it as `+N`. (Two earlier iterations were rejected before this shipped:
return-positive-but-uncapped showed `254`/`255`; heal-internally-and-return-0 showed a bare `0` and
risked the paint routine skipping `damage==0` entries entirely.)

**Popup display — two edits, both needed.** `ShowDamageIcon(x,y,font,type,VALUE)`
(AoWEPACK-exported, `@0x5575A8CC`) does `IntToStr(VALUE)` + font draw. (1) **EXE `@0x436BFF`**:
`and eax,0xFF`→`movsx eax,al`, so the popup's owner-draw call passes the *signed* byte (e.g. −2) at
this one call site — both exes, byte-identical patch. (2) **`cave_plusnum`** redirects
`ShowDamageIcon`'s `IntToStr` setup: `VALUE<0` → render `"+"+IntToStr(-VALUE)` via `@LStrCat3
@0x55701190` and an embedded `"+"` literal addressed by call/pop delta; `VALUE>=0` unchanged. Only a
fire-heal ever produces a negative value here.

### v2 — keep the damage roll, remove the to-hit roll (✅ confirmed 2026-08-29)

v1 replicated `ExecuteDamageRole`'s non-immune branch verbatim before negating, so the *heal*
inherited the engine's full to-hit mechanic: `AoWE.ExecuteDamageRole @0x55725EAC` rolls
`RandInt(20)`, misses flat on ≤1 (~10%), auto-maxes on ≥18 (~10%), else scales against a threshold
`10-(attack-defence)`. Map fire passes attack 12 / damage 6 (already-doubled, constants at
`0x5580DB01`/`0x5580DB06` inside `cave_mapfire_gate`). v1 measured out to Fire Elemental healing 0
twenty percent of the time (mean 2.95 of 6), Fire Sprite 10% (mean 3.30) — **and the margin ran off
the target's own Defence, so a Defence buff on the fire unit made its own healing *worse*.**

**v2's `_heal` block** (27 B replacing v1's 30 B, live at `0x5580DA4D`) keeps the magnitude roll but
sets `strength=8` unconditionally (`NOMISS_MARGIN`, the lowest value that empties the miss band)
instead of `attack-defence`, discarding the to-hit term, and forces a flat-fumble roll of 1 instead
of 0 so the unlucky case still heals. Result at damage 6, identical for both units and never zero:
mean 3.40 (1–6, weighted 4/3/3/4/3/3 of 20). ✅ Confirmed in-game 2026-08-29: every tick heals, no
misses. Revert = flip `HEAL_TAKES_TOHIT_ROLL` back to `True` and re-run — both bodies are registered
pre-states, so this re-tunes in place with no backup touched (round-trip verified).

⭐⚠ **The reusable lesson.** v1 read as the conservative, faithful choice — "replicate the engine's
own non-immune branch, then negate" — which is exactly why the defect survived unnoticed: nothing in
the cave said the word "roll," so nobody thought to check for one. **Reusing an engine damage path
for a non-damage purpose silently imports everything that path decides, not just what it returns** —
a to-hit check, a stat dependency, whatever else lives inside it. When a cave borrows an engine
routine, enumerate what that routine *decides*, not only what it *returns*, before trusting the
borrow. (Restated from `aow1-item-hp-mv-bonuses`-adjacent lessons for terrain/movement context —
this exact trap is why the elemental heal above was built as a plain `SetHitPoints` write instead of
reusing this same path.)

Cosmetic, not fixed: `TriggerFireDamage` still logs the (now negative) damage byte into the same
event-log a structure's other messages use, so a map-fire heal can occasionally show a stray garbage
number elsewhere in that log. Harmless.

## Movement predictor fix (v1 → v4)

**🔨 APPLIED, UNTESTED (2026-07-05).** Script `build_patch.py`. No in-game confirmation is recorded
anywhere in the source material — only a test plan. **No automated `--undo` exists.**

### ⚠⚠ Never run `build_patch.py --apply` — it overwrites the pristine vanilla reference

Live-verified in the script itself: on `--apply`, line 284 unconditionally runs
`shutil.copyfile(DPL, BACKUP)` where `BACKUP = AoWEPACK_original_backup.dpl` — **the pristine
pre-modding reference this entire project uses for every "is this vanilla?" byte-diff.** This
happens even when every patch site is already applied and the run is a functional no-op — there is
no branch that skips it. Running `--apply` at this point in the project's life would overwrite that
reference with the current live DLL, which by now carries roughly 145 other features — silently and
irrecoverably destroying the one file every other feature's verification depends on.

The doc this feature was written up in independently recorded an equally dangerous "revert"
instruction — **"copy `AoWEPACK_original_backup.dpl` over `AoWEPACK.dpl`"** — which must never be
carried out either: it would wipe every one of the ~145 later features applied since 2026-07-05.
**Both directions of copying between these two files are now forbidden.** This is recorded as a
standing booby trap for the same reason `build_magebane.py --apply` is: the failure is silent,
total, and affects far more than the feature the script's name suggests.

**Running the script with no arguments (a plain dry run) is safe** — it only verifies bytes and
reports `ALREADY PATCHED` or a mismatch, and exits before the backup-copy line, which is gated
behind the `--apply` check. Use a plain run to check whether the v4 fix is still installed; never
pass `--apply`.

**No safe automated revert path exists.** If this feature is ever removed, it needs a hand-written
surgical undo: restore the three call-site originals below and zero the 419-byte cave
`0x5580D700..0x5580D89F`, verify-before-write. Original bytes (from the script's own `patches`
table, so a future session does not have to re-derive them): `TMoveArmyTE.Setup @0x55747B01` and
`MoveArmyEx @0x5574A36E` were both `E8 <rel32 to 0x557638D8>` (a call to
`TMovepath.MovePointsToPos`); `TSelectedArmy.Update @0x557936A3` (13 bytes) was
`8B D6 8B 43 08 E8 <rel32 to 0x557639DC> 89 68 14`.

### What it fixes, and the v1→v4 debugging history

The old (pre-2026-07-05) session summary claimed *"per-hex execution is correct — only the UI
prediction is wrong."* **This is false, and is not to be re-derived or repeated**: the *executed*
path is truncated by the identical pessimistic MIN(MP) math before movement even starts
(`TMoveArmyTE.Setup` copies only `MovePointsToPos(path, TArmy.MovePoints(army,mask))` hexes into the
move token), so a display-only fix (the previous approach, hooking the X-marker call inside
`ShowMovePaths`) could never have worked — the arrows would show more hexes than the army actually
moved. Both sides needed fixing together; the arrow colour logic itself needed no changes.

**The fix: `TrueReachPos(army, mask, path)`**, a cave at `0x5580D75A`. For the transporter (if any)
or each selected unit, build that unit's own cost table via the game's own
`TAbstractUnit.CreateMovePointTable` (the single authoritative builder, see Movement cost above),
then walk the path deducting that unit's own per-hex cost from that unit's own remaining MP; the
stack's true reach is the worst per-unit stop position. Three hooks replace the previous
`MovePointsToPos` calls/budget-store:

| site | VA | fixes |
|---|---|---|
| `TMoveArmyTE.Setup` | `55747B01` | execution truncation — armies actually move the full distance |
| `MoveArmyEx` | `5574A36E` | destination-reached check — attack/negotiate/combine trigger at true range |
| `TSelectedArmy.Update` | `557936A3` | UI: stores a synthetic budget into `TMoveSettings+0x14` so every vanilla consumer (arrows, X marker, turn numbers, gold estimate) lands on the true boundary hex with no changes to the ~730-line `ShowMovePaths` |

A fourth hook was needed later (v4): `TSelectedArmy.CalculateMovePath`'s
`PosToMovePoints(path,0)` call at `55792A18`, because `TSelectedArmy.Update` turned out to be
**event-driven, not per-frame** (its callers are `FinishMove`/`SendMsg`/`SetArmyHS`/`SetSelection`/
selection events) — it fires at selection time, before the path exists, so it kept storing the stale
vanilla budget forever; `CalculateMovePath` built the path but never refreshed it. `cave_calcpath
@0x5580D87F` now refreshes `+0x14` at the exact moment the path is (re)built, with the side benefit
that the not-enough-MP road-gold estimate right below it also uses the correct per-unit budget.

**v2→v3 (2026-07-05, same day): terrain/road/cost bytes are signed.** v2 used `MOVZX` where the
game uses `MOVSX`; on every no-road hex (road byte `−1`) the lookup indexed 256 bytes past the table
buffer into stack memory, and the resulting garbage was deterministic per terrain row and call
depth — land rows in the execution hook happened to read plausible small numbers (moves "worked"),
water rows read huge/negative garbage (blocked), and the *display* hook read different garbage at a
different stack depth (arrows pessimistic while execution ran full length) — the kind of
inconsistency that looks like two unrelated bugs but is one signedness mistake. Fixed by changing
exactly two opcodes; instruction lengths were unchanged so no cave labels moved. **Rule for any
future cave touching these tables: terrain, road and cost bytes are signed chars, and the road
column always needs the `+1` shift** (see Reference above).

**v1→v2 (same day): the rebase lesson.** v1 crashed in the real game ("Access violation ... read of
558FA040") because the DLL does not load at its preferred base in the live process — the loader
relocates the game's own absolute references via `.reloc`, but v1's cave had one bare
`mov eax,[558FA040]` with no reloc entry, so it read unmapped memory or garbage post-relocation.
Fixed with the standard `call $+5; pop eax; sub eax,preferred_VA; mov eax,[eax+558FA040]`
position-independent idiom. **Rule: never embed an absolute VA in a file-patched cave without either
a `.reloc` entry or the call/pop delta — runtime-only patches don't hit this because they apply
post-relocation, file patches always do.**

Deliberately left vanilla: AI move-planning keeps pessimistic planning (AI-issued moves still
benefit from the Setup fix once executed); multi-day tail prediction still uses merged/MIN costs.

### Test plan (never run, still the checklist)

Forestry case (a mixed-MP stack with Forestry through forest should predict and move 6 hexes, not
stop short); Floating case (a Floating + a Walking unit next to a road hex predict and execute
together correctly); regressions — single-unit moves, transporter/boarded stacks, attack at
exactly max range (combat must trigger), combining into a friendly stack at max range, multi-turn
arrows, hasted/slowed units, underground/cave paths.

## Path abilities and movement-cost — investigation + one built feature

Two systems share one trigger, `TAbstractUnit.MovedTo @0x55780328` (once per hex **entered**):
the **move-cost path** (`MovePointCost`/`CreateMovePointTable`, deducts MP — see Reference above) and
the **Path-ability terraform path** (Path of Life/Decay/Frost rewrite terrain as a carrying unit
walks). `param3` (the entered field) feeds the cost path; `param2` (the field the walk is centred
on, `[EBP-4]`) feeds every Path effect, using ability checks `GetAbilityEnabled` = unit VMT `+0x148`.
Path of Life (ability `0x45`, surface-only) and Path of Decay (`0x44`, surface-only) are mutually
exclusive by level; Path of Frost (`0x6D`) is independent, no level gate; Trail of Darkness
(`0x1A`) is a separate un-exploring mechanism, not a terrain change. None of these three fire while
the unit is being transported.

Each Path ability calls map VMT **+0xD4** (`TAoWHSMap.ChangeTerrainEx`, area+callback — see How
terrain changes propagate above) with **radius hard-coded to 1** at each call site and a leaf
`changeCb`: Path of Life/Decay `*tPtr = (terrain≠6,0 ∧ field.level==0) ? 1 : unchanged` /
`...5:unchanged`; Path of Frost turns water→ice and spawns/refreshes a `TFrozenWaterHS` from its
separate `changedCb`.

### Built: radius +1, 25% proc on the outer ring only — `build_path_outerring.py`

**✅ CONFIRMED WORKING IN-GAME (2026-07-08).** Not a uniform proc: the original radius-1 disk stays
100%, a new outer ring (hex-distance 2) rolls 25%. Backup `AoWEPACK.dpl.pre-pathring`.

1. **Radius**: three 1-byte edits, `6A 01`→`6A 02` at each Path call's pushed radius argument
   (`0x5578044E` Life, `0x55780495` Decay, `0x557804DA` Frost).
2. **Centre stash**: `cave_stash` hooks `MovedTo @0x5578041E` (just after the not-transported gate)
   and writes the centre hex's x/y into a 2-byte scratch, then replays the displaced instructions.
3. **Proc gate**: the three per-hex terrain callbacks are re-pointed (their pushed pointers carry
   `.reloc` entries, so writing the cave's preferred VA rebases correctly) to caves that compute
   `HN = dHXtoHN(centre, field)` and classify `HN<7` = inner (100%) vs `HN 7..18` = outer ring
   (roll `AoWHSMap.Random(map,4)==0`, 25%, **synced RNG — correct for MP determinism during move
   execution**). Frost's separate spawn-notify self-gates on the ice check already having happened,
   so it needs no gate of its own.

⚠ **Bug fixed during build: the centre-stash scratch must live in writable memory.** The first cut
put the 2-byte scratch inside the cave region itself (CODE), but **AoWEPACK's CODE section is
read-only at runtime** (section flags `0x60000020`) — the write faulted
("Exception occurred during TArmyDefaultMoveTE"; the move completed but the terraform aborted).
Fixed by moving the scratch into **BSS slack at `0x558FA800`** (flags `0xC0000000`=WRITE, reachable
from the caves via the same call/pop-delta anchor since BSS and CODE share one rebase delta).
**General rule, not specific to this feature: caves may EXECUTE from CODE but must never WRITE to
it — any static mutable scratch belongs in DATA/BSS.**

⭐ **`dHXtoHN` + a ring/distance threshold is a reusable primitive** for any ring, fading-edge, or
distance-keyed mechanic — write-up of the RE technique itself (not repeated here) is in
`12-re-toolchain.md`.

### Speculative, not built: two move-cost features

Both would hook the tail of `TAbstractUnit.CreateMovePointTable @0x5577FDC4` (the single
authoritative per-unit table builder — see Reference above), so either stays automatically
consistent between executed movement and the move predictor, exactly like the fixes above.

**Sandworm/tunneler faster through desert** (SPECULATIVE, feasible 85% tunneling-keyed / 75%
exact-id-keyed): after the table is built, subtract N from the copied Desert row
(`buf[1+2*0x10+col]`, cols 0..12, clamped to a floor). Two ways to identify "a Sandworm": (A) the
unit-type index via `[[unit+0x40]+0x18]` — but **the Sandworm's numeric id is not in the DLL** and
must be read once from live game data; (B) gate on the Tunneling move-type bit (`0x80`, ability
`0x2A`) instead, no lookup needed — in vanilla the Sandworm is the archetypal tunneler, so "all
tunnelers move faster on desert" is nearly equivalent.

**Frostling↔snow / Azrac↔desert racial move-cost** (SPECULATIVE, feasible 80%): a genuinely new
modifier axis (cost is currently move-type based only). After the table is built,
`race=[[unit+0x40]+0x20]` reduces the Snow row for Frostling, the Desert row for Azrac. **Neither
race's byte value is a DLL constant** (races are resourcestring names only; the index is assigned
at resource-load time) — read both from a known unit of each race once, or walk the race list via
`TRaceResource.GetRaceIndex @0x55759CD8` (`[raceRes+0x14]`).

## Open items

- **Sandworm's numeric unit-type id** — not derivable from the DLL. Read `[[unit+0x40]+0x18]`
  (GFX-resource index) off a placed Sandworm, or the editor's unit list, before building the
  exact-id variant.
- ~~Frostling/Azrac race byte values~~ **ANSWERED 2026-09-08** from `Release/HERORES.PFS` tag `0x0B`
  (38 hero resources, 3 per race). The full enum, read off the live file: **0** Human, **1** Azrac,
  **2** Lizardman, **3** Frostling, **4** Elf, **5** Halfling, **6** Dwarf, **7** High Men,
  **8** Dark Elf, **9** Orc, **10** Goblin, **11** Undead, **255** raceless (Mind Vessel, Dragon
  Golem). ⚠ The authoritative read is `[[unit+0x40]+0x20]` — the **chassis's** race, which is what
  `THero.GetRace @0x55786F9C` returns. `hero[+0x68]` (tag `0x0C`) is a parallel field with a `0xFF`
  "any" sentinel used by `THero.CanJoin @0x55786D86`; it can legitimately be `0xFF` where the chassis
  has a real race, so **never key a race table off `+0x68`**.
- **Raise Terrain underground: does the overlay-non-zero gate actually block casting on a Dirt
  floor hex?** `ValidTargetMapF`/`ValidTargetSelectionMapF` both require `field+0x15 != 0` on top of
  rejecting terrain 0/6/A/D. A third-party modder's unpatched install passed this, but that is his
  install's data, not a byte fact about this one — **first thing to check** if underground casting
  refuses with no visible reason.
- **Chasm/Sky: does any shipped scenario already use terrain `0xB`/`0xE`?** Verified only that
  nothing in the *code* path ever writes `0xE`; scenario **data** was never scanned.
- **Chasm/Sky: combat-map rendering and transport/boarding regressions near ex-Coast hexes** — both
  unverified, check in-game.
- **Ice Storm's current 25% skip rate** — only the mechanism and the earlier 50% value are
  in-game confirmed; the currently-installed `SKIP_DENOM=4` has never been retested.
- **Movement predictor v4** — the test plan above has never been run once, on any version.

## Failed approaches — do not retry

- **Chasm/Sky tile art v1** (max-pool the source by `shrink=2`, grade per pixel) — rejected as "too
  high-frequency": packs ~33 stars per hex and flattens the artwork's sparkles into 2×2 blocks.
  Superseded by v2's two-pipeline approach.
- **Chasm/Sky cliff transitions v1** (point Sky/Chasm at the `0xB6` underground-wasteland block) —
  that is the *soft blend*, not the CaveWater cliff (`0xA0`); confirmed wrong by the user's
  screenshot. Superseded by remapping the working terrain values to CaveWater in the rule table.
- **Raise Terrain lava-dirt: calling the AoW-level `ChangeTerrain` wrapper (map VMT `+0xD0`) from
  inside the frame-9 render callback** — trips "Invalid AoWHSMap.Random use". The follow-up attempt
  to dodge it by calling the *wrong* low-level HSEngine function corrupted the stack (mismatched arg
  count): "Exception during AoWHSMap.NewFrame", no change. Fixed by calling the *correct*
  lower-level `ChangeTerrainEx` (unguarded raw RNG) with the right argument count.
- **Elemental terrain heal via `ExecuteDamageRole`** — would import a to-hit roll and a Defence
  dependency into what should be an unconditional heal; built instead as a plain `SetHitPoints`
  write. Same trap as Fire Heals Fire Units v1, avoided instead of un-made.
- **Fire Heals Fire Units v1's heal magnitude** (replicate `ExecuteDamageRole`'s non-immune branch
  including its to-hit roll, then negate) — silently rolled the heal to hit against the healed
  unit's own Defence, so a Defence buff made its healing *worse*. Superseded by v2.
- **Movement predictor: a UI-only fix** (hooking the X-marker call inside `ShowMovePaths`, prior
  session) — built on the false belief that execution was correct and only the display was wrong.
  It is not: `TMoveArmyTE.Setup` truncates the *executed* path with the same pessimistic math before
  movement starts. Do not re-derive "only the UI needs fixing" for this feature.
- **`map.VMT[0xd4]` mis-identified as `UpdateStaticScene`/a thin wrapper** — sibling map-class
  vtables (`0x5570e8xx`, `0x5590d5xx`) share method addresses at a glance; the strategic map's
  vtable base is `0x5590d4b8`, confirmed by the EarthWall (`+0xD0`) vs Path (`+0xD4`) call sites.
- **Path outer-ring: mutable scratch inside the CODE-section cave** — AoWEPACK's CODE is read-only
  at runtime; the write faulted. Moved to BSS slack.
- **Raise Terrain "always places a grass mountain"** — an unverified inference from the
  terrain-blind resource-selection loop; a user in-game test of vanilla proved mountains already
  match their terrain. The speculative fix (`build_raiseterrain_mtn.py`) was never applied, and its
  target cave address has since been claimed by Ice Storm's skip gate anyway.
