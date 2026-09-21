# Movement point tables & terrain/overlay types (AoWEPACK.dpl)

> Part of the terrain/map system — **start at `Terrain_System_INDEX.md`** for the map of these docs.

Status: **verified against disassembly + data dumps 2026-07-24**, cross-checked against the
user's movement-table notes (which supplied the authoritative ability/overlay/terrain names).
Companion docs: `Hex_Transition_System.md` (rendering/updates), `Terrain_Changing_Spells_Map.md`
(spells), `Chasm_Sky_Terrain_Design.md` (the Chasm/Sky feature, built),
`older/vanilla_movement_system.txt` (pathfinder internals).

## The core mechanism

Movement cost is a **16×16 matrix per movement ability**: rows = terrain byte (`field+0x14`),
columns = overlay byte (`field+0x15`, −1 = none .. 0xE).

- Lookup: `TMoveControl.DefaultMoveOnMovePointProc` (`557454D8`):
  `cost = table[0x31 + terrain*16 + overlay]` (the +0x31 bias makes room for overlay −1;
  cost data starts at struct+0x31, or offset `terrain*16 + overlay + 1` when indexing a raw
  256-byte table). `0xFF` = impassable (sign-extended to −1 by all consumers).
- **8 static base tables, one per movement ability, in AoWEPACK.dpl DATA** — file-patchable:

| VA | Ability |
|---|---|
| `558E84FC` | Walking |
| `558E85FC` | Swimming / Water Walking / Liquid Form |
| `558E86FC` | **Flying / Floating / WW** (one shared table!) |
| `558E87FC` | Forestry |
| `558E88FC` | Cave Crawling |
| `558E89FC` | Mountaineering |
| `558E8AFC` | Fire Immunity / Fire Halo (lava crossing) |
| `558E8BFC` | Tunneling (can cross EarthWall at cost 8) |

- At startup `SUB_L55744B2C` (`55744B2C`) fills `MovePointTables` (`558EA040`, BSS, 64 KB =
  256 tables × 256 bytes) — one combined table per movement-type *byte* (bitmask of the 8
  abilities), best (lowest) cost per cell across the unit's abilities. A stack shares one
  worst-case (MAX) table across its units (`vanilla_movement_system.txt`).
- **Patching the 8 base tables in the file changes movement for every unit, the AI, and the
  path preview at once** — no code patch required; the generator propagates at startup.
- Sparse tables (Mountaineering, Fire Immunity…) define only the cells they improve; the
  best-of combine does the rest.

## Terrain types (rows)

| ID | Name | Notes |
|---|---|---|
| 0 | Water | |
| 1 | Grass | |
| 2 | Desert | |
| 3 | Snow | |
| 4 | Steppe | |
| 5 | Wasteland | |
| 6 | Ice | |
| 7 | Earth (EarthWall) | Tunneling crosses at 8; blocks Flying (cave ceiling) |
| 8 | Rock (RockWall) | blocks everything incl. Flying |
| 9 | Lava | FireImm/FH crosses at 3 |
| A | uWater (CaveWater) | |
| B | uWasteland | **NOW CHASM** — unused in practice (user ruling); row blanked to Fly/Float-only by `build_chasm_sky_movement.py` |
| C | uDirt (Dirt) | |
| D | uIce (CaveIce) | |
| E | Coast | **vanilla = a clone of the Water row** (Swim 4, Fly 4, bridge-crossable, land-impassable; differs from Water only in 2 trivial cells). Ziggurat's water-family sweep edited it in lockstep with Water/uWater (Swim 4→3 etc.) — table hygiene, not usage. Read-side special case with Water/Ice in `TAoWHexagon.TerrainChanged` `5579A94C`; **nothing ever writes 0xE** (verified spell map). **NOW SKY** — row blanked to Fly/Float-only by `build_chasm_sky_movement.py` |
| F | Border | **all-0xFF in every table — that IS its universal impassability.** Also excluded from transitions (`O==0xF`/`N==0xF` → none). |

All 16 rows are *allocated* (a 17th ID would mean rewriting every 16-stride table, the
transition `T*16` byte-index scheme, resource registries, editor palette) — but per the user,
rows 0xB and 0xE carried no real map content, and both have now been repurposed as Chasm/Sky.

## Overlay types (columns)

Column order (index = overlay+1): **None(−1), Mountain(0), Forest(1), Hill(2), Vegetation(3),
Road(4), Bridge(5), Rubble(6), Structure(7), Obstacle(8), L.Veg(9), Solid(A), Ooze(B),
Res(C), Res(D), Res(E)**.

Cross-checks against engine behaviour found this conversation:
- Mountain = overlay 0 — `TMountainMO.GetOverlay` (`557A2DC8`) clamps to 0; Walking column is
  0xFF (mountains impassable on foot), Flying 6, Mountaineering 6 (Hill 4).
- Road = 4, Structure = 7 (both Walking cost 3 — the "second road" I saw is the structure hex);
  Bridge = 5 (Water+Bridge walkable at 3 — the engine `TBridge` deck).
- Flood's overlay shield set {0, 2, 7} = Mountain, Hill, Structure. Flood destroys road HSes on
  overlay ∈ {4,5} = Road, Bridge.
- Ooze (B): a real swamp-like overlay — Walking 8 (vanilla; Ziggurat retuned to 12), Swimming 8,
  Flying 4, Tunneling 6.
- **Res-C (overlay 0xC) is a VANILLA flying-only overlay**: only the Fly/Float table has costs
  there (4 on surface rows, 5 underground in the installed DLL) — everything else 0xFF. What
  vanilla uses it for (if anything places it) is unknown — but it's a ready-made
  "flying-only" column. Verified present in the pristine vanilla DLL.
- **Columns entirely 0xFF in every table: Solid (A), Res-D, Res-E** — free for new mechanics.
  Solid has a defined *name* (likely intended as an all-blocking overlay), so prefer D/E — or
  claim C and inherit its vanilla flying costs (see `Chasm_Sky_Terrain_Design.md`).

## ⚠ The installed tables are NOT vanilla — Ziggurat rebalanced them (byte-diff 2026-07-24)

**277 cells differ** between the pristine vanilla DLL (`C:\GAMES\Age of Wonders Vanilla\`) and
the installed AoWEPACK.dpl. Broad strokes of the Ziggurat edits:
- Walking/Forestry: Ooze 8→12; walking gains uIce bridges.
- Swimming: water cost 4→3; gains land-Ooze at 8 (swamp swimming); loses uWater-Ooze.
- Fly: mountains 8→6; underground rows uWl/uDi 4→5; gains Obstacle crossings; loses uWater roads.
- Cave Crawling: broadly retuned (surface 4→5, underground cheaper 3–4).
- **Mountaineering: gutted** — vanilla let mountaineers walk normal land in this table;
  Ziggurat reduced it to mountains-only (6, incl. underground mountains) + hills, making it a
  pure sparse bonus table.
- Fire Immunity: lava 4→3, can stand on lava structures.
- **Tunneling: massively expanded** — vanilla was EarthWall-only (10); Ziggurat gives overland
  movement at 6–8 and cheap underground travel (EarthWall 10→8).

Any build script touching these tables must verify-before-write against the **installed**
values (or both), not vanilla; and any balance reasoning should state which baseline it uses.

## Consequences / reusable facts

- "Impassable to unit class X on terrain Y" mods are **pure data edits** to the 8 base tables.
- Flying and Floating cannot be given different costs without splitting their shared table —
  i.e. adding a 9th ability table + touching the movement-type byte handling. Anything that
  treats them together is table-cell-only.
- The overlay byte is published to `field+0x15` by HSes (hexagon resources' terrain lists, or
  map objects like mountains/roads/decorations — see `Hex_Transition_System.md` § Mountains).
  Placing an overlay-publishing object on a hex changes its movement without touching terrain.
- Combined tables live in BSS (`558EA040`) — runtime experiments can poke them live, but
  file-persistent changes belong in the 8 base tables.
