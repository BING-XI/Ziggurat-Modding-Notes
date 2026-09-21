# AoW1 Terrain & Map System — Master Index

**Read this first** for anything touching terrain, hex rendering, movement costs, or the map
editor's tile palette. Details live in the linked docs; this page is the map + at-a-glance
reference + current state.

---

## The docs

| Doc | What it covers |
|---|---|
| `Hex_Transition_System.md` | How a hex decides its art and its edges: the 3-owned-edges scheme, the transition rule table, water shore masks, roads, both bridge types, mountains/terrain-adaptive map objects, **and where hexagon tile images actually live** |
| `Movement_Tables_Terrain_Types.md` | The **(terrain × overlay) movement-cost matrix**, all 8 ability tables, the terrain-id and overlay-id reference |
| `Terrain_Changing_Spells_Map.md` | Every terrain-changing spell's mapping + **the two write paths** (`ChangeTerrainEx` transaction vs raw write + `TerrainChanged`) |
| `Chasm_Sky_Terrain_Design.md` | The Chasm/Sky feature — design, all five build steps, and the traps hit on the way |
| `DevEd_Terrain_Palette_Design.md` | AoWDevEd's tile palette: brush buttons, cross-level terrains, how to add a DFM-callable handler |
| `GripOfWinter_Design.md` | **Freeze Water → Grip of Winter** — the cooling ladder, the widened target gates, and how `TFrozenWaterHS` is reused to make land changes revert. 🔨 **APPLIED, UNTESTED (2026-09-01)**. ⚠ **Two hard couplings with `RaiseTerrain_UG_Earth.md`** — see the row below and §4/§6 there. ⚠ Its "C_SHOW = no ice sprite" reading is corrected in `RaiseTerrain_UG_Earth.md` §5: that gate suppresses **the sparkle**, and there is no separate ice sprite |
| `RaiseTerrain_UG_Earth.md` | **Raise Terrain castable underground; underground Dirt → temporary Earth with the Freeze Water sparkle.** 🔨 **APPLIED, UNTESTED (2026-09-03)**. The surface-only spell flag (`[spell+0x39]`, one byte), the marker mint, and the in-place rewrite of two other features' live caves — plus the revert **order** that creates |
| `RNG_Lockstep_Rule.md` | **Which of the two generators a cave must draw from** — read before adding any roll to a terrain feature. Raise Terrain, Ice Storm and Fire Storm all rolled from the wrong one until 2026-08-31 |

---

## Feature: Chasm & Sky (flying/floating-only terrains) — ALL FIVE STEPS APPLIED

Two appropriated terrain ids — **Chasm = 0xB** (ex-uWasteland), **Sky = 0xE** (ex-Coast) —
passable only by Flying/Floating, with starfield art and cliff edges.

| Step | Script | Target | Backup |
|---|---|---|---|
| Movement rows + Coast water-filter | `build_chasm_sky_movement.py` | AoWEPACK.dpl | `.pre-chasmsky` |
| Editor palette (brushes + cross-level) | `build_deved_terrainpal.py` | AoWDevEd.exe | `.pre-terrainpal` |
| Tile art (23 tiles, in place) — **v2 grade 2026-07-30** | `build_chasm_sky_art.py` | **Release/Release.hss** | `.pre-chasmskyart` |
| Cliff edges | `build_chasm_sky_transitions.py` | AoWEPACK.dpl | `.pre-skytrans2` |
| Spell/ability guards (7 sites) | `build_chasm_sky_spellguard.py` | AoWEPACK.dpl | `.pre-spellguard` |

**Confirmed in-game by the user:** terrain places from the palette, tiles render, cliff edges
render.
**Applied but NOT yet user-validated in-game:** the **v2 tile art** (Sky = nebula + stamped
sparkles at ~1/10 the old star density, 1 variant in 8 keeping the old dense starfield; Chasm =
the shipped surface-water tiles re-graded to a near-black sea), the movement rows
(walkers/ships blocked, flyers at 4 MP) and the seven spell/ability guards. Test a Death Storm
or a Flood over a Chasm field, and a Path-of-Decay unit walking across one.
**Declined but fully mapped:** per-hex animation (twinkles / gusts). A land hexagon
(`THexagon` family) has **no `ShowDynamic` VMT slot** — only `TLowerIsometricHexagon`
descendants such as `TAoWWaterHexagon` can animate, and they self-register a
`TDynamicIsometricHexagon` companion in `UpdateTransitions`. Full design + addresses in
`Chasm_Sky_Terrain_Design.md` → "Animation".

⚠ `AoWEPACK.dpl` carries **four** layers from this feature. Only the newest `.pre-*` is a safe
single-step revert — run `ls -t AoWEPACK.dpl.pre-* | nl` (or `re_tools/revert_audit.py`) first.

---

## Feature: terrain rolls draw from the synchronised RNG — APPLIED 2026-08-31, UNTESTED

Three modded caves rolled through the raw per-process generator while deciding replicated
terrain state; vanilla draws synced in all three of those functions. Fixed by retargeting each
`call` rel32 (4 bytes each) at a shared 24-byte PIC stub — no cave rebuilt, no branch moved.

| Site | Cave (owner) | Injected into |
|---|---|---|
| `0x5580DB72` | `cave_lavadirt` (`build_raiseterrain_lavadirt.py`) | `TRaiseTerrainTE.RaiseTerrain` |
| `0x5580DB46` | `cave_iceroll` (`build_icestorm_lava.py`) | `TIceStorm.ChangeStormTerrain` |
| `0x5580BEA8` | Fire Storm helper `0x5580BE74` (**orphan**) | `TFireStorm.ChangeStormTerrain` |

Script `build_rng_lockstep.py`, stub `0x55827000`, backup `.pre-rnglockstep`, surgical `--undo`.
Rule + full audit of every modded RNG site: `RNG_Lockstep_Rule.md`.
Check any time with `python "Modding Resources/re_tools/rng_audit.py" --owners`.

---

## ⚠ The temporary-terrain cluster — Grip of Winter + Raise Terrain UG Earth are COUPLED

Two features share one marker class (`TFrozenWaterHS`) and one cave (`C_SHOW`). Read this before
running either script.

| Feature | Status | Script | Backup | Doc |
|---|---|---|---|---|
| Grip of Winter (ex-Freeze Water) | 🔨 **APPLIED, UNTESTED (2026-09-01)** | `build_gripofwinter.py` | `.pre-gripofwinter` | `GripOfWinter_Design.md` |
| Raise Terrain underground: Dirt → temporary Earth | 🔨 **APPLIED, UNTESTED (2026-09-03)** | `build_raiseterrain_ug_earth.py` | `.pre-rtugearth` | `RaiseTerrain_UG_Earth.md` |

**1. Raise Terrain DEPENDS on Grip of Winter.** Grip owns the whole temporary-terrain machinery —
the `[hs+0x0E]` (restore) / `[hs+0x0F]` (set) padding-byte scheme on `TFrozenWaterHS`, the save
serialisation (`C_RW`, property ids `0x20`/`0x21`), the melt/revert (`C_MELT`) and the
keep-while-terrain-matches rule (`C_HSTC`). Raise Terrain writes **none** of those; it only mints a
marker saying "restore Dirt, I set Earth". **Without Grip's four hooks the raised earth would be
PERMANENT**, so `build_raiseterrain_ug_earth.py` refuses to apply if any of `0x55764ACB`,
`0x55764AE0`, `0x55764B8B`, `0x55764BD0` is not hooked.

**2. Raise Terrain rewrites six bytes inside Grip's `C_SHOW` cave** (`0x5582A4E0`) to restore the
sparkle on raised earth. Grip byte-compares that whole 20-byte blob, so **while Raise Terrain is
installed `build_gripofwinter.py` can neither `--apply` nor `--undo`** — both abort with
`cave 0x5582A4E0 is foreign`, *before* writing anything. It also rewrites five bytes inside
`build_raiseterrain_lavadirt.py`'s `cave_lavadirt`, which likewise **cannot re-apply** (it aborts
with "originals mismatch — not written").

```
*** UNDO build_raiseterrain_ug_earth.py BEFORE build_gripofwinter.py ***
```

Undoing Raise Terrain restores `C_SHOW` byte-exactly and hands Grip its undo back. Everything aborts
safely in the wrong order — nothing is corrupted, it just will not run.

## At-a-glance reference

**Terrain ids:** 0 Water, 1 Grass, 2 Desert, 3 Snow, 4 Steppe, 5 Wasteland, 6 Ice, 7 EarthWall,
8 RockWall, 9 Lava, A CaveWater, **B uWasteland → CHASM**, C uDirt, D CaveIce,
**E Coast → SKY**, F Border. All 16 rows are allocated — a 17th id would be a rewrite.

**Movement cost** = `table[0x31 + terrain*16 + overlay]`, 8 ability tables at
`558E84FC`..`558E8BFC` (Walking; Swim/WaterWalk/LiquidForm; **Fly/Float/WW share one**;
Forestry; CaveCrawling; Mountaineering; FireImm/FH; Tunneling). 0xFF = impassable.
⚠ The installed tables are **Ziggurat-rebalanced** (277 cells differ from vanilla) — always
verify-before-write against the installed bytes.

**Hex geometry:** `px = x*32 + 8`, `py = y*32 + (x&1)*16` (`HXtoHP`, HSEPack `5560E3B4`).

**Transition images** (`Images/HexTrans.ILB`) are keyed by **image ID**, and the id space is
exactly `terrain*16 + k`: k 0–2 neighbour-side, 3–5 own-side (drawn displaced), 6–14 generic
land-land blend (3 dirs × 3 variants). Cliff blocks: **`0xA0–0xA5` = CaveWater = the cliff**,
`0x90–0x95` = lava; `0xB6–0xBE` is only the underground-wasteland *soft* blend.

**Where tile art lives:** static surface tiles (grass, desert, snow, steppe, wall, Border,
uWasteland, Coast) are **embedded in `Release/Release.hss`** as mini-ILBs — 48×32, RGB565,
image type 17, transparent colour `0x594A`. Animated/shared sets are external
`Images/*.ILB` (`Waterhex`, `IceHex`, `EARTHHEX`, `ROCKHEX`, `HexTrans`, `MOUNTAIN`).

---

## Traps that cost real time in this area

1. **`.hss` files carry a trailing CRC-32.** Patch the file, then repair with
   `re_tools/hss_crc.py --fix`, or the game *and* editor die silently at startup (unhandled
   `Invalid HSSET`). I wrongly concluded ".hss is unpatchable" from black-box tests before
   finding `EngineP.dpl!Engine.GetCRC32`. See `aow1-hss-crc` memory.
2. **RLE row records are 4-byte aligned**, and width/height come from `clipwide`/`cliphigh`,
   not `wide`/`high`. Missing either makes a perfectly good shipped tile look corrupt — and
   "fixing" it crashes the engine. **When a shipped asset looks corrupt, suspect the reader.**
3. **`TAoWHexagon.TerrainChanged` treats terrain {0, 6, 0xE} as water-family** and replaces the
   land hexagon with a `TAoWWaterHexagon` (the 0xE branch even substitutes terrain 0). Anything
   reusing 0xE must neutralise that filter.
4. **Transitions read the neighbour field's cached terrain byte** (`field+0x14`), so a raw
   terrain write without `TMapField.TerrainChanged` leaves stale edges.
5. **Dangerous spells use a catch-all `else`; safe ones enumerate source terrains.** That single
   distinction predicted every hit and miss in the spell audit.
6. **A stale `AoWDevEd.exe` from a previous launch** makes a naive "is it still running?" check
   match the OLD process — `taskkill /F /IM AoWDevEd.exe` and wait before judging any launch.
