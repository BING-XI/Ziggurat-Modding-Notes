# DevEd terrain-palette upgrade — Sky/Chasm buttons + cross-level terrain brushes

> Part of the terrain/map system — **start at `Terrain_System_INDEX.md`** for the map of these docs.

Status: **BUILT AND APPLIED 2026-07-24** — `build_scripts/build_deved_terrainpal.py`, backup
`AoWDevEd.exe.pre-terrainpal`, new PE section `.ctp`. Automated live test passed (details at the
bottom); **the one thing still needing a human check is painting a hex** (see "Not yet verified").
Goal (user request): add Sky (0xE) and Chasm (0xB) brush buttons to AoWDevEd's top-level tile
palette, and make surface terrain buttons available on the Underground tab and cave terrain
buttons on the Surface tab.

## As built

| Tab | Row | Buttons |
|---|---|---|
| Surface (`ToolbarPnl`) | 0–1 | *(vanilla)* Party, Item, Road, Water, Grass / Steppe, Desert, Wasteland, Snow, Ice |
| | 2 | **Sky**, CaveWater, Dirt, Lava, CaveIce |
| | 3 | Earth, Rock, **Chasm** |
| Underground (`Panel10`) | 0–1 | *(vanilla)* Party, Item, Bridge, CaveWater, Dirt / Lava, CaveIce, Earth, Rock, **+ Chasm** (fills the vanilla empty slot) |
| | 2 | **Sky**, Water, Grass, Steppe, Desert |
| | 3 | Wasteland, Snow, Ice |

Both panels 76 → **152 px** high (4 rows × 38); the resource grid below is `alClient` and reflows.
New component names: `SkyBtn`/`ChasmBtn` (surface), `uSkyBtn`/`uChasmBtn` (underground),
`X<Terrain>Btn` for the cross-level clones.

### The three moving parts
1. **Cross-level buttons — zero new code.** DFM `OnClick` resolves by name at load, so the clones
   point at the existing handlers (`WaterBtnClick`, `LavaBtnClick`, …) and copy the original
   buttons' `Glyph.Data` blobs verbatim. Vanilla already does this (`uArmyBtn` → `ArmyBtnClick`).
2. **Two new handlers.** Every `TMainForm.<Terrain>BtnClick` is the same 43-byte stub differing
   only in one `mov dl,<id>`; the script assembles `SkyBtnClick` (dl=0xE) and `ChasmBtnClick`
   (dl=0xB) and **asserts the template re-assembles byte-identical to
   `TMainForm.uWaterBtnClick`** (dl=0xA) before writing. Landed at `0x52E000` / `0x52E02C`.
3. **Published method table relocated.** It cannot grow in place (the `TMainForm` class-name
   shortstring sits immediately after it), so the whole 132-entry / 3181-byte table is copied
   into `.ctp` with 2 entries appended (134 / 3219B at `0x52E060`) and the VMT slot
   `VMT-0x28` = `0x425CD8` repointed `0x4272EE` → `0x52E060`. Delphi 3 VMT layout: selfptr
   −0x40, methodtable −0x28, classname −0x20, parent −0x18. Table entry format:
   `{word size (incl. itself), dword code addr, shortstring name}` after a leading word count.

### Glyphs
48×32 24-bit BMPs with a 4-byte Delphi TBitmap stream-size prefix; the **bottom-left pixel is the
transparent key** (`#BFBFBF` here). Sky/Chasm are generated from `<game>/Zigmod/Sky.bmp` and
`Chasm.bmp` (which are actually 256×256 RGBA **PNGs**) masked to `GrassBtn`'s exact hexagon
silhouette. Two art notes learned by looking at the result:
- plain LANCZOS downscaling averages the stars out of a 256px starfield — the script blends a
  **max-pool** with the average so stars survive at 48×32, then applies a brightness `boost`;
- the two source images are identical, so the icons are differentiated deliberately: Sky =
  bright open starfield (`SKY_BOOST`), Chasm = dimmer starfield inside a 3px **rocky rim**
  (`CHASM_BOOST`/`CHASM_RIM`/`CHASM_RIM_W`) so it reads as a pit. Knobs at the top of the script.

### Layering
Reads whatever DFM the `TMAINFORM` resource entry currently points at, so it **must run after**
`build_dlgdirs.py` and `build_editor_toolbar.py` (it consumed the `.mtb` DFM and repointed the
entry at `.ctp`; the `.mtb` copy is now dead data, exactly as that patch left the `.rsrc` copy).
Section order in the patched exe: CODE, DATA, BSS, .idata, .reloc, .rsrc, .dlgd, .mtb, .ctp.

### Live test (automated, 2026-07-24)
Editor launches maximized, no crash — which alone proves **every** new `OnClick` name resolved
(an unresolved one raises `EReadError` while streaming the form, so the form would not show).
Then: File>New (surface+underground) → both palettes render with all 18 buttons and correct
glyphs at H=152 (`TPanel` measured live at 349×152); Level-Down switches to the Underground
palette; clicking `uSkyBtn`, `uChasmBtn` and cross-level `XGrassBtn` **latches each one in the
GroupIndex=1 radio group with no exception dialog**, confirming the handlers execute — and for
Sky/Chasm that is only possible via the relocated method table. `dasm.py` also now resolves the
two stub names *from the new table*, an independent read-back of the repoint.

### Not yet verified (needs a human)
**Painting a hex.** The map canvas is DirectDraw-backed and ignores posted mouse input (the
status bar's hex coords never moved), so the automation could not paint. What is unproven is only
the last hop — that the latched brush writes terrain 0xE/0xB into the field — and the stub code is
byte-identical to a shipping handler apart from the immediate. **To check: pick Sky or Chasm,
click a hex, hover it and read the status bar terrain name** (expect Coast / the 0xB name), or
just watch the tile change.

Traps hit while testing, for the next session: driving the editor with
`SetForegroundWindow` + a synthetic `PgDn` **killed the process** (DirectDraw activation, not the
patch — the patched editor survived the same flow afterwards with message-only input, and PgDn
isn't a level key at all: level switching is `LevelUpBtn`/`LevelDownBtn`, TSpeedButtons on
`Panel2` at Left 288/328, Top 4, 39×38). Also `SB_GETTEXT` to the status bar blocks/never
marshals cross-process — read the status text out of a `grabwin.py` bitmap instead.

## Recon (all verified)

**Engine side needs nothing.** `TMORTerrainControl.GetRndResource` (HSEPack `5560E94C`) keys
resources by (terrain id, resource class) — there is **no level dimension**; surface/underground
is convention only (disjoint id ranges). This is why the ruleset hex-object workaround already
places lava/dirt/border anywhere. Cross-level brushes work the moment the UI offers them.

**UI structure** (TMAINFORM DFM; ACTIVE copy at file offset `0xDC600` in the `.mtb` section —
the modtoolbar patch relocated it there; the `0x74AFC` copy in `.rsrc` is dead):
- Surface palette: `ToolbarPnl` with `TSpeedButton`s: ArmyBtn, ItemBtn, RoadBtn, GrassBtn,
  WaterBtn, IceBtn, SnowBtn, WastelandBtn, DesertBtn, SteppeBtn (GroupIndex=1).
- Underground palette: `Panel10` with uArmyBtn/uItemBtn (reuse Army/Item handlers!), uWaterBtn,
  DirtBtn, LavaBtn, uIceBtn, EarthBtn, RockBtn.
- Each terrain button has its **own named OnClick handler**; DFM resolves handler names against
  TMainForm's published method table at load.

## The other painting route: ruleset "hex objects" (investigated 2026-07-27)

Besides the terrain brush buttons this patch adds, AoW modders expose a terrain by inserting a
**hexagon resource** into the ruleset, which then appears as a clickable tile in the editor's
resource grid. The existing hand-made ones in `Release.hss` are easy to spot by their names:

| Resource | Terrain | Image |
|---|---|---|
| `Lava-1.bmp` | 0x09 Lava | 50x42 RLESprite16, 1-image ILB |
| `Dirt-1.bmp` | 0x0C uDirt | 50x42 |
| `Boder-1.bmp` *(sic)* | 0x0F Border | 50x42, ×2 |

Each is exactly the same shape as a vanilla tile resource — a single-image embedded ILB preceded
by a 1-entry `TTerrainList` (`01 00 00 00 <terrain> FE`) — just at 50x42 instead of the vanilla
48x32, and with a hand-made name. **The equivalent for this feature is `Sky-1.bmp`
(Terrain Type `Coast` = 0x0E) and `Chasm-1.bmp` (Terrain Type `Reserved` = 0x0B).**

Adding those two does double duty: it gives a directly-clickable palette entry *and* puts the new
art into `GetRndResource`'s pool for that terrain, so the brush buttons start painting it too.
It must be done in AoWDevEd — `Release.hss` cannot be byte-patched (see
`Chasm_Sky_Terrain_Design.md` step 3).

Grid mechanics found while checking whether the tiles could be surfaced without touching the
.hss: `TMainForm.LinkToMORList` (`0x42A834`) hands **every** `TEResourceGrid` the *same* resource
list, and all terrain grids share `DefaultResourceCID` — `0x20167` (`TTerrainMOR`, decorations)
for Grass/Steppe/Desert/Snow/Wasteland/Dirt, `0x20153` (`THexagonResource`, tiles) for the
Places/Objects/Hexagons grids. So the exe does **not** filter grids by terrain; which tab a
resource lands in is driven by its own edit-ID (the `[:0\5\1\129:]` keys in `Release/release.txt`).
That means a new palette tab cannot be populated from the exe side alone — the resource has to
exist and carry the right edit-ID, which is again editor work.

## Notes kept from the recon

- **Handler template variants.** The *surface* handlers (`0x42B19C`+) begin
  `push ebx / mov ebx,eax / mov eax,edx / xor edx,edx / call TSpeedButton.SetAllowAllUp(0x402320)`
  before the terrain code; the *underground* ones (`0x42B594`+) are 43 bytes and skip that,
  ignoring `Sender` entirely. The new stubs copy the **underground** shape precisely because it
  ignores Sender, so one handler works from either panel.
- The `[Self+0x60C]` object and its `+0xC0` byte select change-terrain vs clear-terrain; the stubs
  replicate that test blindly — no need to know what the flag means.
- `TabSheet1`/`TabSheet2`/`TabSheet3` are ghost 'Hexagons' sheets in the DFM — left alone.
- Terrain ids used by the vanilla handlers: Water 0, Grass 1, Desert 2, Snow 3, Steppe 4,
  Wasteland 5, Ice 6, Earth 7, Rock 8, Lava 9, uWater A, Dirt C, uIce D — i.e. **every id except
  0xB and 0xE**, the two this feature adds (and 0xF Border, still unexposed).
