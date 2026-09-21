# The Ziggurat Map Generator

Generates AoW1 surface maps: terrain, water, rivers, islands, mountains. It lives outside
`Modding Resources/` — the code is in **`<game>/Zig Modding Tools/`** — because it is a standalone
Python toolchain, not a binary patch. The one binary patch it needs, the editor's
`File > New → New generated map` dialog, is `build_deved_newmapgen.py` and is documented in
**`08-editor.md` §9**. This file covers everything on the generator side of that boundary.

---

## The scope ruling — read this before proposing anything

> "There should be no concept of 'playability' or 'fairness' for map design. That can be edited in
> using, for example, teleporters which can arbitrarily connect any number of map locations. Income
> also doesn't depend on geography, at least not from mines, nodes and farms, since these can be
> sparse or clustered as the mapmaker sees fit. The purpose of a Ziggurat Map Generator will first
> and foremost be beautiful, varied, dramatic landscapes."
> — the user, and this has held through every revision since

So: **no** start-position balancing, no continent-size fairness, no resource distribution, no
connectivity guarantees, no "is this playable" heuristics. Every question is answered on how the map
*looks*. A landmass that is one hex of walkable ground is fine. An unreachable island is fine.

The design is three stages, of which **only stage 1 exists**:

| stage | what | status |
|---|---|---|
| 1 | terrain hexes, and the overlays that are part of the landscape (mountains) | built |
| 2 | forests and other decorative overlays | not started |
| 3 | structures and units | not started, and the user may never want it — "I am not sure I would even use 3) instead of doing it by hand" |

Also settled by ruling: **surface layer only** (caves are a separate task), and the user's numbers
are always in the current Ziggurat scale.

---

## The pieces

| file | role |
|---|---|
| `Zig Modding Tools/zig_hsm.py` | the FORMAT layer: read and write `.hsm`, and the hexagon/overlay registry read live from `Release/Release.hss` — hexagon palette, mountains, massifs and **hills**. Run it with no arguments and it round-trips 30 real maps and asserts they come back byte-identical. |
| `Zig Modding Tools/zig_mapgen.py` | the generator itself. Also a CLI. |
| `Zig Modding Tools/zig_mapgen_gui.py` | a tkinter settings window (PySide6 is not installed; tkinter is what is available). |
| `Zig Modding Tools/deved_bridge.py` | what the editor's cave shells out to. Turns 25 integer tokens into settings and calls `generate()`. |
| `Zig Modding Tools/zig_mapgen_settings.json` | persisted dials for the standalone front ends. |
| `Zig Modding Tools/lastgen/` | marker files the editor dialog probes to reopen where it left off — see `08-editor.md` §9.4b. |

⚠ **`zig_hsm.py`'s self-test is the safety net for the whole toolchain.** Any change to the format
layer must keep `round-trip: 30 identical, 0 not`.

⚠ **`Zig Modding Tools/` is NOT covered by the two profile-path scans in `CLAUDE.md`**, which look at
the game-root binaries and at `Modding Resources/`. This folder is distributable and two of its files
carry the absolute path as a matter of course: `deved_bridge.log` (every bridge run writes it) and
`last_map.txt` (every generation writes it). Delete both before sharing, along with `__pycache__/`,
and add the folder to the scan:

```bash
grep -rlaF "$USERNAME" "Zig Modding Tools/"      # -a, never -I
```

---

## The format, in one page

`.hsm` is `CFS\0\x02` + zlib. Inside is a tree of tagged directories ("TAoWDir"): `<u8 n>` then n
entries, either small `(u8 tag, u8 off)` or wide `(u32 tag, u32 off)`. **A field's length is the next
field's offset minus its own** — there is no explicit length.

* **The tile stream is field 6, running to field 1.** ⚠ Levels 1–2 carry an extra field 5 that
  shifts it by one byte. AoWx's generator hardcodes `lb+2` and gets away with it only for level 0.
* A **plain hexagon record** is 14 bytes: `01 32 00 | <u32 class-1> | 01 01 00 | <u32 guid>`.
* A **mountain record** is 33 bytes: the same, plus a decor child at tag `0x33` carrying
  `(guid, x, y)`. Synthesised by `mountain_record()` and proven byte-identical to a harvested one.
* Terrain ids: 0 Water, 1 Grass, 2 Desert, 3 Snow, 4 Steppe, 5 Wasteland, 6 Ice, 7 EarthWall,
  8 RockWall, 9 Lava, 10 CaveWater, **11 Chasm**, 12 Dirt, 13 CaveIce, **14 Sky**, 15 Border.
* Hexagon classes: `0x20153` static, `0x2073E` animated (water and ice in real maps), `0x20171`
  wall, `0x20558` border.
* `_splice()` fixes exactly two things: the level's field-1 offset, and every later level's offset in
  the parent table. Everything else is length-driven and needs no fixups.

### The registry (`Release/Release.hss`)

The only game-data dependency. It yields, per terrain, the hexagon variants to paint with
(`reg.palette`), the 1-hex mountains (`reg.mountains`) and the multi-hex ones (`reg.massifs`).

⚠⚠ **The mountain family is identified by CLASS `0x20169`, never by the overlay byte.** The 4-hex
land mountains carry overlay **2**, not 0; filtering on `ovl == OVL_MOUNTAIN` hid all ten of them for
weeks and left the generator using only two of the three sizes.

---

## The pipeline

`generate()` → `gen_surface()` builds the terrain, then `shore_buffer()` marks the ground no
overlay may stand on, then `place_mountains()`, `merge_mountains()` and `place_hills()` add
overlays, then `Map.write_terrain()` writes the level. Mountains and hills share one overlay
grid — a hex carries at most one decor child.

`gen_surface` runs in this order, and **the order carries most of the design**:

1. **The cold end** — pick the direction, build the warmth ramp.
2. **The geological plan** (`plan_structure` / `structure_field`) — 2–4 features chosen from
   orogen, sweep, rift, caldera, spiral, dome, fault. Each is a rasterised curve; a multi-source BFS
   turns them into a distance field. ⚠ **The plan comes first and the noise decorates it**, not the
   other way round. Without this the maps were "camouflage" — a stationary noise field cannot make
   overarching structure, only texture.
3. **Elevation** — the plan, plus continentalness through a spline, plus ridged multifractal relief,
   with domain warping so features have a grain instead of being isotropic blobs.
4. **Orographic rain shadow** — walk upwind, subtract the highest ground crossed.
5. **Hydrology, BEFORE the climate bands.** Priority-flood depression filling → flow direction →
   flow accumulation → rivers and lakes, then incision and a riparian corridor.
   ⚠ This ordering is load-bearing. When rivers were added *after* the bands they were pure paint:
   368 of 368 changed hexes were land→water and nothing else about the map moved. Routing water
   first lets it carve valleys and water the ground, which the terrain allocation then sees.
6. **Climate** — temperature and humidity fields; the band cutoffs are **quantiles of what those
   fields actually came out as**, over the hexes that stay dry land.
7. **Sea and islands** — the sea, then `add_islands()` as an ADDITIVE pass into open water, then
   `drown_islets()`.
8. **Terrain allocation** — the auction, below.
9. **Smooth, stamp rivers, despeckle, coalesce sky, adjacency repairs.**

### ⚠⚠ Warped sampling reads off the edge of the map

Domain warping deliberately samples outside the map, and a `Noise` lattice is only
`int(size/cell)+3` across. Unclamped, a sample past the right edge raises `IndexError` and one past
the left silently WRAPS to the far side through Python's negative indexing. `Noise._lattice` clamps
both. The unclamped version killed a 127×127 generation part-way through, and because the bridge
then never wrote its marker the editor sat frozen in the cave's poll loop.

Any new sampler that offsets its coordinates must go through `_lattice`, not index a grid directly.

### Rank normalisation — the trap that shaped the whole design

fbm is an average of uniform lattice values, so it clumps near 0.5 with sd ≈ 0.15. Thresholding it
with the obvious numbers selected ~5% of the map where 25% was intended. **Every field is wrapped in
`Field`, which rank-normalises it to a uniform 0..1 over the unmasked hexes**, and every cutoff is a
coverage share rather than a magnitude.

⚠⚠ The consequence that keeps biting: **a monotone transform of a SINGLE term is a no-op.** `alt**2`
ranks identically to `alt`. To move a terrain you must change the MIX, not steepen a curve.

---

## Terrain allocation — an auction, not a ladder

The user sets a prevalence per terrain (None … Very High). Those weights become target areas; the
fields decide only *where*.

Every `(terrain, hex)` pair is scored by `_suitability()`, rank-normalised per terrain, and pushed
into one heap. The best bid takes each hex until that terrain's quota is full.

Doing it terrain by terrain instead would let whichever went first strip the good ground and leave
the last one with whatever remained, suited or not. Thresholding a climate ladder would mean moving
one band silently squeezes its neighbours, so no control means what its label says.

`_suitability` scores are deliberately soft and overlapping, so a terrain turned up to High grows
outward from the ground that suits it best rather than spilling somewhere absurd.

---

## Climate: the cold direction

`COLD_DIRS = None / North / South / East / West / Random`, resolved per map. One temperature gradient
does both halves of the user's rule — "which end of the map holds snow/ice, with the opposite end
hosting desert" — because SNOW scores on `1 - temp` and DESERT on `temp`.

* `COLD_AMP = 0.85` tilts the temperature FIELD. This is what carries **sea ice** to the cold end.
* `COLD_TERR = 1.25` adds the gradient directly into SNOW's and DESERT's suitability.

⚠ **The field alone is far too weak, and this was measured.** DESERT scores humidity 0.6 against
temperature 0.4, so it follows dryness; across 12 runs the snow/desert split was often no better than
the bare noise gave on its own (one North run came out 234/228). With `COLD_TERR` added, all 12
directional runs polarise cleanly, and `None` runs stay byte-identical to before — the term is inert
when no direction is set.

It reuses the `latitude` archetype knob, which had been declared and never applied to anything.

---

## The flat shore

**User ruling 2026-09-06.** Water almost always has **1 to 3 hexes of flat land beside it** — no
hill and no mountain overlay. Sea, lake and river alike, and "flat" is about the overlay only: the
terrain type stays whatever the climate gave that hex.

`shore_buffer()` returns the forbidden set and `generate()` hands it to both placement passes.

* ⭐ **It runs BEFORE placement, as a forbidden set — never as an erase afterwards.** Rubbing
  mountains off a finished shore punches holes in the ranges and leaves one stopping dead at the
  coast; barring the ground first makes the range bend around the water.
* Rivers need no special handling. By the time this runs they have been stamped into the grid as
  WATER/ICE, so one multi-source BFS covers sea, lakes and rivers together.
* **Depth varies along the shore, not per hex.** A low-frequency field, rank-normalised over the
  WATER hexes (so the cutoffs mean what they say), is cut into fifths: `SHORE_DEPTHS = (1,2,2,3,3)`.
  Every hex in a stretch inherits the depth of the water it stands beside, carried inland by the
  walk itself.
  ⚠ Equal thirds put a third of the coast one hex deep. Since the two dials together cover 30% of
  the land at their defaults, the overlay share measured over a fixed two rings then sat at 6%
  against a 5% target — the rule holds either way, the flat measurement does not.
* **`SHORE_OPEN = 0.06` of the shoreline gets no buffer at all**, which is what leaves cliffs,
  fjords and mountain lakes. Selected by its own rank-normalised low-frequency field so the
  openings come in stretches; a per-hex roll would put a one-hex notch in every beach.
* The Sky wall respects it too — a rim hex inside the buffer is dropped from the wall.
* The buffer is exported in `<map>.plan.json` as `shore`, so stage 2 can see where the landscape
  is deliberately open, and so `--metrics` can measure the rule against its own set of hexes.

Measured over 5 seeds × 2 sizes at the defaults: **0.0%** of buffer hexes carry an overlay (it is
structural, not statistical), 98.1% of shoreline hexes are clear, and the overlay share within two
rings of water fell from 21.8% to 4.9%.

---

## Mountains

### The three object sizes

All are class `0x20169`, one anchor record each, on the five land terrains (Grass, Steppe, Desert,
Snow, Wasteland). Water's mountains are a different class and the generator never uses them.

| covered | overlay | footprint |
|---|---|---|
| 1 | 0 | the anchor |
| 4 | **2** | anchor + directions 0, 1, 5 (N, up-right, up-left) |
| 9 | 0 | anchor + all six neighbours + two of ring 2 |

The footprint array is field 7: `<u32 n>` then n pairs. Pair 0 is `(terrain, overlay)`; pairs 1..n-1
are slots, each `(terrain, subtile)` or one of **two** not-covered markers, `FEFE` and `FFFF`.

⚠ **Count the covered slots; never infer size from `n`.** The array length is 7, 17 or 19 more or
less independently of the shape — the Grass 4-hex has 7 slots and the other four terrains' 4-hex has
19, all encoding the same thing.

⚠ **Slot k maps to neighbour direction k−1** in `dirs6`'s fixed clockwise-from-N order.
`hexn` drops out-of-range neighbours, which shifts every later index, so it must never be used for
footprint work.

### What the footprint means, measured not assumed

70 hand-made maps from `1Scenario/` contain 5727 multi-hex mountains and **not one multi-record
cluster** — every occurrence is a single 33-byte record and the engine draws the rest. What the
footprint buys is a bigger graphic; what it costs is a clean neighbourhood:

| | 9-hex | 1-hex |
|---|---|---|
| all six neighbours on the terrain the footprint names | **93%** | 48% |
| another mountain among those six | **4%** | 36% |

The 4-hex object's three covered directions were derived the same way, over 12451 placements:
directions 0/1/5 show 86% terrain match and 3–4% mountain occupancy, directions 2/3/4 show 75% and
11–13%, which is the background rate.

This matches the user's own account of placing them by hand: *"the 3-radius mountains can be a bit
fiddly to stack atop each other (left and right corners cannot overlap)"*.

### ⭐ How much: a share of the LAND, and the dial is the target

**Rewritten 2026-09-06.** `mountains` used to be *the share of the crest band that gets a mountain*,
and `High` and `Very High` were the same number, 1.00. So the dial's ceiling was the band's own
size, and the band is two or three rasterised curves a few hexes wide. Measured across five
127×127 maps at `Very High`, one seed offered **56 candidate hexes on the whole map — 0.6% of the
land** — with the dial hard against its stop. The generator's median was 13.7% of land under
mountain graphic against the hand-made corpus's **24% median and 36% at p90**.

`GRADE_SCALES['mountains']` is now a share of the land, and the placement has to reach it:

| | None | Very Low | Low | Medium | High | Very High |
|---|---|---|---|---|---|---|
| target share of land | 0.00 | 0.06 | 0.13 | 0.22 | 0.32 | 0.45 |
| measured, one 127×127 seed | 0.000 | — | 0.130 | 0.220 | 0.320 | 0.450 |

It lands on the target to the hex now that a massif's footprint may only cover ground the pass
already chose (see Placement). `Medium` sits on the hand-made median by construction; `Very High`
is past its p90 and short of its 0.595 maximum.

⚠ **The sky wall comes OUT of that budget, not on top of it.** Sky is walled in mountains
(below), and on a Sky-heavy map that wall is most of the mountains there are. Charged separately it
doubled the dial: a `skylands` map at `High` measured 0.598 of land where 0.32 was asked for. The
wall is still built first and is never absorbed, so a wall larger than the whole budget simply is
the answer.

### ⭐⭐ Where: thin sweeping ranges, made longer rather than wider

**User ruling 2026-09-06.** A range is a long curved LINE, one or two hexes wide and three only at
a knot, with hills on its flanks. Large blobs of mountain are wrong. Four things enforce that, and
the fourth is the one that makes the other three affordable.

**1. The crest is the generating curve itself, one hex wide.** `structure_field` used to mark
everything within 16% of a feature's width as spine, which on a major feature is two or three
rings — the "crest line" a range was built around was already five hexes across before the range
machinery added anything, and nothing downstream could recover a line from it. It is now
`dist == 0`.

**2. A narrow CORRIDOR, and a hard cap.** Every hex's BFS distance from the crest against a local
half-width from a low-frequency field along the range (`MTN_HALFWIDTH = (0.10, 1.45)`, scaled by
`mtn_spread`), plus a knot term where the ridged relief is above `MTN_KNOT_AT`, plus a
high-frequency wobble so the flank is ragged. Nothing beyond **`MTN_MAX_DIST = 2`** can carry a
mountain whatever it bids: a blob cannot form because there is nowhere for its middle to be. Where
the width field drops below `MTN_GAP` the range breaks and a hex within `MTN_PASS_BAR` of the crest
is barred outright — otherwise turning Mountains up fills every pass back in.

**3. The bid, distance first.** `MTN_MIX` = band 2.60, slope 0.65, struct 0.30, relief 0.30, alt
0.20, over fields that are all rank-normalised and therefore directly comparable. `band` is 1.0 on
the crest line and falls to 0 one hex past the cap, so a range reads as a line; the other four
decide **which stretches** of the network get the mountains.
* **Steepness outranks altitude**, by the same ruling: a mountain belongs where the ground
  *breaks*, not merely where it is high.
  ⚠ Steepness is the elevation RANGE over two rings (`ruggedness()`), max minus min — not a single
  neighbour delta, which a one-hex step cut by a river maximises. At one ring the field is spiky at
  hex scale and its top quarter is a scatter rather than a region. Taken from the **finished**
  elevation, after incision, so valley walls bid.
* ⚠ **Only the terrain half of the bid is blurred** (`blur`, `MTN_BLUR = 2`). Blurring the distance
  term as well smears the range's own definition over its neighbourhood, which is the fat band this
  design exists to remove. Blurring the terrain half is still needed for the original reason: a bid
  of rank-normalised fields is uniform on 0..1, and its top N is a scatter of single hexes.
* **Anti-clump**: a candidate off the crest line whose own ring already holds `MTN_CLUMP_MAX = 4`
  mountains is refused however well it bids, so a knot cannot fill solid. Crest hexes are exempt —
  the line is the skeleton every width measurement is taken against.

**4. ⭐⭐ `extend_crest`: more mountains means MORE RANGE, never a wider one.** The dial is a share
of the land, so a range 1–2 hexes wide has to be several times longer than one 5 hexes wide to
spend the same budget. If the corridor cannot carry `MTN_BAND_FILL × take`, secondary sweeps are
branched off the network and the corridor rebuilt, up to `MTN_EXTEND = 12` rounds.

* Each branch is a **circular arc**, the same geometry `_feature_curve` gives the planned features
  and for the same reason: an arc sweeps, a greedy uphill walk zigzags. `MTN_BRANCH_TRIES = 5` arcs
  are drawn and the best is kept.
* ⚠ **A branch is scored on `MTN_BRANCH_MIX` (struct 0.55, slope 0.25, relief 0.20), not on the
  bid.** Scored on the bid the branches found every steep patch on the map and left no country
  between the ranges; weighted towards the geological plan they stay inside the belt it raised.
* ⚠ **`MTN_BRANCH_CROWD` penalises an arc for running within `MTN_SPACING = 4` of range the
  network already has.** Measured against the corridor alone (2 hexes) the branches wove a thicket
  of ridges. It is a score, not a bar, so a map whose budget needs every hex still fills — it runs
  out of uncrowded ground last rather than first.
* A branch starts at an END of the network three times as often as anywhere along it: extending a
  range keeps it one range, a spur from the middle makes two.
* `MTN_BAND_FILL = 1.35` — over one deliberately. The corridor is built with slack because the
  anti-clump rule refuses some of it, the passes bar more, and `gather` cannot hand a speck's hexes
  back with nowhere to put them. Built to exactly the budget the finished share measured 17%
  against a dial asking for 22%.

**`gather()` absorbs the small bodies and grows the survivors** by exactly as many hexes,
best-bidding hex first — the same absorb-and-regrow `coalesce()` does for Sky. Area in, area out,
and the regrowth is confined to the corridor so it lengthens a range instead of thickening it.
⚠ Its floor is `max(MTN_MIN_HEXES, MTN_MIN_BLOB × total)`: thin ranges make many more bodies than
fat ones, so a share-only test either spares every speck or eats a legitimate short range.

⚠ **`crestline`, not `spine`.** `gen_surface` clears the spine wherever it crosses water, because a
crest is only a *range* on dry land — but the corridor measures distance *from* the crest, and a
seed set missing the drowned stretches loses the band on the land beside them too. The plan carries
both: `spine` (land only, for the preview) and `crestline` (the whole curve, for the distance
field). The distance field **crosses water**; only the selection is restricted to placeable ground.

### Before and after — 5 seeds × 2 sizes (96×96 and 127×127), default dials

Read back from the written `.hsm` by `zig_mapgen.py --metrics`. "Width" is a body's area divided by
its thinned skeleton's length, so a one-hex ribbon measures 1.0 and a blob measures its own radius.

| | before | after | target |
|---|---|---|---|
| shoreline hexes carrying no overlay | 80.3% | **98.1%** | ≥ 90% |
| overlay share within 2 rings of water | 21.8% | **4.9%** | ≤ 5% |
| overlay share inside the buffer itself | — | **0.0%** | 0 |
| mountain bodies per map | 2.0 | 5.7 | — |
| mean body area, hexes | 1373 | 401 | — |
| **mean width** | **5.36** | **1.94** | ≤ 2.0 |
| mountain in bodies wider than 2.5 | 98.5% | **0.7%** | ≤ 10% |
| total skeleton length per map | 383 | **950** | up |
| mean body length | 243 | 204 | — |
| mountain share of land (dial asks 22%) | 23.3% | **21.99%** | ±15% |
| hill share of land (dial asks 9%) | 9.00% | 9.00% | ±15% |
| 127×127 generation | 1.0 s | 1.1 s | ≤ 2× |

Mean *body* length falls because the map now carries five or six ranges where it carried two; the
figure that answers "are the ranges longer" is the total skeleton length, which is 2.5× what it
was. The mountain share landing on the dial to 0.01 pp is the massif rule below, not luck.

⚠ **At Very High the width target cannot be met, and it is arithmetic rather than a defect.** 45%
of the land at width 2 needs a crest network of ~2500 hexes on a map with 11000 land hexes; the
ranges have to touch. Measured on one 127×127 map: Low 12.99% at width 1.79, Medium 21.99% at 1.96,
High 31.99% at 1.85, **Very High 45.00% at width 2.65 with 98% of the mountain in bodies wider than
2.5**. The dial still means exactly what it says at every position.

### Placement

`place_mountains()` places objects **in a full pass per size, largest first**, then fills with
1-hex mountains.

⚠ Largest-first must be per PASS, not per anchor. Letting a 4-hex object take the best ground the
moment it fits blocks 9-hex ones that would have anchored a hex or two away, and measurably cost
both object count and total graphic area.

⚠ Massifs are ordered by the **bid**, not by raw elevation — after `MTN_MIX` those are not the same
ground.

⚠⚠ **Every hex a massif's footprint covers must be one the pass CHOSE for mountain**, not merely
one a mountain could stand on. A 4-hex graphic hanging off a 1-hex ribbon is exactly the bulge the
range rules exist to prevent, and it is also how the finished area used to overshoot the dial — the
graphic spilled onto ground outside the budget, which is why `Medium` measured 0.228 against a
0.220 target. With the test the two are equal by construction and massifs appear only where the
corridor is locally wide, which is what "3 hexes at a knot" means in practice.

⚠ `reg.mountains` used to include Water — the registry really does carry a mountain overlay for it —
so a bare `in reg.mountains` test grew ranges out into the sea. Candidates go through `placeable()`.

`merge_mountains()` is the finishing pass: a leftover clump of 1-hex mountains matching a 4- or 9-hex
footprint is fused into one object, **repainting the terrain underneath** to the anchor's, which the
user allowed explicitly. Without that almost nothing merges on mixed ground.

⚠ Repainting can undo the snow adjacency rule, so a merge that would put snow against grass or desert
is REFUSED rather than repaired afterwards. The repairs live in `gen_surface`, and re-running them
here could change the terrain out from under a massif just placed on it.

⚠⚠ **A fused cell loses its RECORD but keeps its GRAPHIC**, so it must join `covered`. It did not,
while nothing downstream read that set. The moment hills were placed after the merge, **448 of them
landed on hexes a merge had just covered** and nothing in the log said so. Anything that runs after
`merge_mountains` must be handed `covered`.

⚠ **The knot term has to be a threshold.** As a plain multiple the relief fattened the whole range
uniformly, because a rank-normalised field sits above its own midpoint half the time. As a
threshold (`MTN_KNOT_AT` / `MTN_KNOT`) it makes discrete massifs where the ground really is broken
and leaves a ridge elsewhere.

---

## Hills

Added 2026-09-06. Same kind of object as a mountain — one anchor record carrying a decor child — in
a **1-hex** and a **2-hex** form, on the same five land terrains, controlled by its own `hills` dial.

### ⚠⚠ The class does not identify them; the NAME does

Hills are class **`0x20167`**, the generic decor class that also holds every forest, stone, bone and
crop in the game. Overlay 2 narrows it to two families, and the other one is **`Large Skeleton`**,
which has the same 1-hex and 2-hex footprints. `Registry` therefore reads **field 6, the object's
own name (a Pascal short string)**, and gates on `Hills`. Filtering by class, or by class+overlay,
places skeletons.

Three variants per terrain, all one anchor record:

| footprint `n` | covered | the second hex |
|---|---|---|
| 1 | 1 | — |
| 3 | 2 | direction **1** (up-right) |
| 7 | 2 | direction **5** (up-left) |

Both 2-hex forms cover an *upper* neighbour, the same bias the 4-hex mountain shows.

### What hand-made maps do — 24631 hills across 76 maps

| | |
|---|---|
| hills per mountain record | **0.80** |
| hill graphic as a share of land | median **7.8%**, p75 10.3%, max 21.7% |
| 1-hex : 2-hex | 55 : 45 |
| touching a mountain | 32% |
| within two hexes of one | 67% |
| more than five hexes from any | 7% |
| on the terrain their footprint names | 97% |
| **2-hex covered hex already occupied** | **0 of 11047** |

That last row is a hard rule, not a preference: no hand-made map ever puts the second hex of a
2-hex hill on another hill or mountain. `place_hills` enforces it, along with same-terrain.

### Where they go

`HILL_MIX`: an **apron** term (1.00) that falls away with distance from the nearest mountain
*graphic* through `HILL_APRON = (0.74, 0.68, 0.52, 0.38, 0.26, 0.16)`, plus the same **steepness**
(0.85) the mountains bid on, plus altitude (0.25) and relief (0.25). Blurred like the mountain bid,
then the best bids take hexes until `hills` × land is covered. Rings 1–3 carry most of the weight,
which is what puts the hills on the flanks of the thin ranges.

`place_hills` is handed the same `forbid` set as the mountains, so no hill lands in the flat shore
buffer. ⚠ `_hill_slot_free` goes through `free()`, so the 2-hex form's covered neighbour cannot
land in the buffer either.

The apron is deliberately soft. Generated against hand-made, by ring:

| ring | 1 | 2 | 3 | 4 | 5 | 6 | >6 |
|---|---|---|---|---|---|---|---|
| generated | 34% | 44% | 14% | 3% | 2% | 1% | 2% |
| hand-made | 32% | 35% | 12% | 7% | 4% | 3% | 7% |

⚠ An earlier `HILL_APRON` peaking at 1.00 on ring 1 put 47% of hills against a mountain and read as
a drawn outline around each range. Same failure mode as the sky wall's, same fix: flatten the
profile and let steepness carry the tail.

**With `mountains` at None the apron is zero everywhere and hills fall back on steepness alone**,
which is a hill-country map and works — 0.240 of land, no violations.

### Order

`place_hills()` runs **after `merge_mountains()`**, because the merge repaints the terrain under a
fused massif and a hill placed first would be standing on ground that then changed. It writes into
the mountains' own overlay grid and shares their `covered` set.

`HILL_TWO = 0.68` is the chance of *trying* the 2-hex form; after the free-slot test fails some of
the time it lands at 46% of placements, against the corpus's 45%.

## Sky

Sky (terrain 14) is flying-only void — the "sky cliff devoids".

* **The top of the elevation ladder.** Suitability is `alt*0.55 + relf*0.25 + max(0, struct)*0.20`,
  which puts it on the highest and most broken ground inside the raised half of the plan. It sits at
  roughly the **87th percentile** of land elevation.
  ⚠ Three mixes were compared: weighting altitude harder gave the same percentile but progressively
  less coherent voids (68 → 60 → 52 hex mean blob), so the relief and structure terms earn their
  place.
* **Half the area its prevalence would buy.** `SKY_SHARE = 0.5`, applied to the finished SHARE inside
  `allocate_terrain`.
  ⚠ NOT to the weight. Halving a weight also shrinks the total it is divided by, which measured
  **0.56** of the original area rather than 0.50; scaling the share and handing the remainder to the
  other terrains in proportion measures **0.51**. Remember this for any future "half as much X".
* **Few large voids.** `coalesce()` absorbs bodies below `SKY_MIN_BLOB` (6% of total sky) into the
  ground around them and grows the survivors back by exactly as many hexes, largest first, so
  clumping costs no area. Five 96×96 maps went from ~9 scattered patches averaging 68 hexes to
  **2–7 bodies averaging 62–236, largest up to 287**.
* **Inside a thick mountain clump, not behind a fence.** Rings of placeable land are walked outward
  from every void and each joins the clump at its own density (`SKY_BAND`), giving mountain ground
  **4–6 hexes deep**. The wall is deliberately incomplete: the share is rolled per map from
  `SKY_WALL_RANGE = (0.60, 1.00)`, the user's own tolerance, and lands at 72–100% (mean 82%) once
  massif coverage is counted.
  ⚠ An earlier version walled every ring-1 hex with a 1-hex mountain. It satisfied the letter of
  "ensconced" and looked like a drawn outline. Do not re-tighten it.
* ⚠ A hex touching Sky can never anchor a massif — Sky is not the massif's terrain — so massifs sit
  at ring 2 and outward and their footprints reach back over the rim.

---

## The two adjacency rules

Run after the majority smooth, the river stamp and the despeckle, next to the existing
"lava may never touch water" rule, and **in this order**:

1. **Sky may never touch water or ice.** The sky hex gives way, not the water — the coastline and
   the rivers came out of the hydrology and moving them would unpick it. The rim takes the most
   common solid terrain it already borders, else Wasteland.
2. **Snow may never abut grass or desert.** The WARM hex becomes the buffer, so a snowfield gains a
   tundra fringe rather than losing ground. Steppe if the user enabled it, else Wasteland, else
   Steppe anyway. Collected first and applied after, so a hex converted early cannot be read as a
   neighbour later; one pass suffices because the conversion creates no new violations.

Sky runs first because its fill can pick Snow, which the snow pass then has to fringe.

---

## The editor path

Full detail in **`08-editor.md` §9**. In summary: the dialog's OK cave builds a blank map at the
chosen size, saves it to `Scenario\Custom\zNewMap.hsm` with `THSEngine.SaveHSM`, shells out to
`devedgen.bat` → `deved_bridge.py` with 25 tokens, waits for `zNewMap.done` (or `zNewMap.fail`), and
opens the result.

⚠ **The bridge REFUSES a stale container** — it compares the handoff's size and level count against
what the dialog asked for. A silent fallback here hid a broken save for the whole life of the
feature: an Extra Large request came back 64×64 and nothing said so.

---

## Verifying a change

**`python zig_mapgen.py --metrics "<dir>/*.hsm"`** is the standing report. It reads the written
`.hsm` back through `zig_hsm`, shares no code with the placement, and prints one line per map plus
a mean: shoreline clear share, overlay share at rings 1/≤2/≤3 from water, overlay share inside the
map's own shore buffer (from the `.plan.json` sidecar — `-` when the map predates the rule), the
mountain bodies' count, mean area, **width = area / thinned skeleton length**, the share of
mountain in bodies wider than 2.5, body length mean/max/total, and both dials' achieved share of
land against what was asked for.

⚠ Overlay coverage is the **graphic** — anchor plus every hex its footprint draws over. An
anchors-only checker read 95% where the truth was 100% on the sky wall. The 9-hex object's two
ring-2 slots are counted as 7 rather than 9, exactly as the placement treats them.

Everything else still wants a scratch tool; recreate them rather than trusting a screenshot.

| check | how |
|---|---|
| format still sound | `python "Zig Modding Tools/zig_hsm.py"` → `30 identical, 0 not` |
| the rules hold | generate across several seeds and assert 0 sky-on-water and 0 snow-on-warm |
| multi-hex legality | read the WRITTEN `.hsm` back: every anchor's footprint on its own terrain, nothing else occupying a covered hex, nothing off the map |
| sky walling | ⚠ count a massif's covered neighbours, not just records |
| range shape, the shore | `--metrics`: width ≤ 2.0, bodies wider than 2.5 under 10%, ring ≤2 overlay under 5% |
| **what it looks like** | ⚠ the PNG preview draws one triangle per overlay hex, which at a 22% share reads as texture whatever the arrangement. Draw the mountain/hill/water MASK as filled hexes instead — the line structure is invisible in the preview and obvious in the mask |
| hill legality | the 2-hex hill's covered neighbour: same terrain, and NOTHING else on it |
| the dial means what it says | mountain graphic / land against `GRADE_SCALES['mountains']`, across several seeds |

⚠⚠ **Read the generated file back, not the log.** Two real bugs were invisible in the log and obvious
in the file: mountains silently dropped, and a map generated into a stale container. And when
comparing a log against a file, make sure they are from the SAME run — re-running the bridge
in between cost an hour chasing a phantom 885-vs-1262 discrepancy.

---

## Open

* Stages 2 and 3 (forests/decoration, structures/units). Hills are placed by stage 1 because they
  are landscape rather than decoration; forests are not.
* The plan's crest length is still the generator's most variable input (37 to 1398 hexes over five
  seeds of one setting). `extend_crest` now branches whatever is missing, which is a better
  compensation than widening was, but `plan_structure` producing a reliable crest of its own would
  still be the real fix. The branches are also invisible to the `.plan.json` `spine` export, so
  stage 2 sees only the planned curves, not the network the mountains actually used.
* At `Very High` (45% of land) the ranges necessarily merge — see the width figures above. If that
  position should stay thin, the dial's top has to come down; it cannot be had both ways.
* The cave layers are blanked to solid rock; cave generation is a separate task by ruling.
* The 4-hex WATER mountains (class `0x2009d`) are unused — they would be reefs, and mountains on
  water was a bug once already.
* Ring-2 footprint slots are not checked when placing a 9-hex object. Real maps only show a 4%
  ring-1 violation rate so ring 1 is what matters in practice, and the editor renders the result
  correctly, but the two ring-2 slots have never been mapped to directions.
