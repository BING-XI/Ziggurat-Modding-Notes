# AoWDevEd.exe — lag diagnosis, bug sweep, area copy-paste design

**Status: FrameRate fix CONFIRMED WORKING (2026-07-07) — user tested in-editor ("it's good") at
60 fps; now set to 120 (identical on the 60 Hz primary, hedged for the 119 Hz panel). Scanner/
palette "fixes" found UNNECESSARY after measurement. Remaining bugs triaged → none patched (shared
game DLLs / unproven / near-unreachable). Area copy-paste deferred by user.** Findings are from static disassembly + live sampling/latency measurement on the running
editor (Europe scenario + fresh 128×128 map), incl. a vanilla-vs-patched A/B.

## TL;DR — what actually happened

1. **THE fix: map view `FrameRate = 15` → 60 (DFM byte).** While the editor is active the render
   loop paces the *entire message pump*; probes measured a rock-steady **67.0 ms** (= 1000/15).
   Every click/tab event drained at ≤15/s. Patched to 60 → pump **~12–17 ms** (measured). This one
   byte fixes **both** reported complaints (placement lag AND tab lag). APPLIED to AoWDevEd.exe +
   AoWEd.exe via `build_editor_framerate.py --apply` (backups `.pre-edfps`).
   - Placement: was fully pump-gated; the click handler itself is 1–58 ms, redraw deferred to
     frames. 67 ms → ~12 ms pump = the "click 30×, watch them load in" drains ~5× faster.
   - Tabs (A/B, natural tab-switch settle, Europe map): **vanilla 15 fps ≈ 134 ms** (2× the 67 ms
     pump) → **patched 60 fps ≈ 62 ms** (2× the ~17 ms pump). The switch (~34 ms) and grid paint
     (~17 ms) were never heavy — the lag was pump serialization of the switch's message
     round-trips. No palette caching needed.
2. **Scanner perpetual-redraw claim (earlier draft): DISPROVEN by measurement.** Idle profile with
   the Scanner floater open vs closed shows **zero** `DrawMap`/`DrawObjects` samples either way and
   identical frame-loop cost (~1.5 % vs 1.1 %, all in `GetElapsedMilliSeconds`). Re-reading
   `TScanner.Draw` (0x5970395C): the `step := -1` full-redraw re-arm at 0x59703B8B is **gated
   behind surface (re)creation** (`if [self+0x174]==0` at 0x59703A11) — it only fires on first
   draw or a width change, NOT every paint. On a stable view `Draw` does 2 tiny minimap blits +
   a conditional `DrawObjects`. Scanner-on adds only ~3 ms to the pump. **No fix; and `TScanner`
   is shared with the game (AoW.exe/AoWCompat.exe import it) so a cave there was rightly rejected.**
3. **Palette tab paint: fast + GDI-bound, not disk-bound.** Grid full repaint = **17 ms**. Profiling
   a tab-cycle: **win32u.dll 60 %** (one hot GDI stub `win32u+0x11ec` = 50 %), ILPACK sprite
   decode only 0.4 %, **no ReadFile signature** → images are resident (LoadMode load-and-keep, not
   discard-per-draw). The subagent's "per-cell file reload" does not occur. Resolved by FrameRate;
   no ILPACK/EngineP cache cave.
4. **Area copy-paste (radius N): still very feasible, deferred by user.** Editor already has
   multi-object hex clipboard (`CutHS/CopyHS/PasteHS` on Ctrl+X/C/V + popup); copies the current
   `THexagonSpriteSelection` (TList, structurally multi-hex), pastes via `THSMap.Place`. Missing:
   radius-select on copy, per-object offsets on paste. ~2 HSEPack.dpl caves. Design in §4.

## Measurement method note
`FrameRate` is a DFM `vaInt8`; the editor bakes it into the THSMEdit instance at form create. To
A/B without disturbing the live patched exe, run the `.pre-edfps` backup under a temp name (loads
the same DPLs; DFM is embedded per-exe). Pump latency measured with `SendMessageTimeout(WM_NULL)`
while the app is foreground (frame loop stops when inactive → probes ~0.1 ms; must be active).
Tools: `re_tools/{sampler,scan_profile,palette_profile,paint_timer,settle_tab,measure_pump}.py`.

## Where things live (module map)

| Piece | Module | Notes |
|---|---|---|
| Editor UI shell, forms, per-object editors | AoWDevEd.exe (CODE only 188 KB) | 136 classes; TMainForm VMT 0x425D00, method table dumped |
| Map view control `THSMEdit` + tools + hex clipboard | HSEPack.dpl (base 0x55600000), unit HSMEdit | also used by the game — caves never executed there but section must not break it |
| Map data (`THSMap`, `TMapField`, `THexagonSprite`, selection) | HSEPack.dpl, unit HSEngine | |
| Palette grids `TEResourceGrid` + engine/serialization (`TECopyComponent`, rwEObject) | EngineP.dpl (base 0x55500000) | |
| Minimap `TScanner` | AoWTools.dpl (base 0x59700000) | |
| Sprite libs (`TImageLibrary`, `TImage08.ShowDC`) | ILPACK.dpl (base 0x55200000) | |
| Display/frame loop (`TCustomDisplay`, `WaitForVerticalBlank`) | DCPACK.dpl | |

AoWEd.exe is a near-identical sibling build (same DFM layout, offsets differ slightly — both
sets listed below).

## 1. The lag, with evidence

### Measurements (live, instrumented)

- Sampling profiler (`re_tools/sampler.py`, suspends threads + reads Wow64 EIP @150–200 Hz):
  idle and during interaction the app is ~95 % in waits — the lag is **latency/pacing-bound, not
  CPU-bound** on the small test maps.
- WM_NULL round-trip probes against the THSMEdit window while the app is **active**:
  **67.0 ± 0.5 ms per pump**, always (= 1000/15). While the app is *inactive* the frame loop stops
  and probes return in 0.1 ms.
- Placement itself is cheap: the synchronous MouseDown→`DropSelectedPlaceHS` handler measured
  1.4–58 ms (mutation + `THSMap.SetModified`); redraw is deferred to the next frame(s).
- Tab switch (TCM_SETCURFOCUS, synchronous part): 36–70 ms; "Units" main tab 232 ms.
  The repaint itself is asynchronous on top of that.
- Placement verified end-to-end (objects appeared on the map; nothing was saved to disk).

### Mechanism

- DFM: `HSMEdit.FrameRate = 15`, `UpdateFrameMode = umAsynchrone`, `BufferingScheme = bsTripple`.
  The DCPACK display loop runs `THSMEdit.UpdateFrame` once per 66.7 ms while active and the message
  queue is only pumped between frames, so **every user event drains at ≤15/s**, plus frame work.
- `TMainForm.HSMEditUpdateFrame` (exe 0x428D18) additionally does per-frame: `Sleep(1)`,
  6× status-panel SetText (IntToStr each), ~9× ILF font SetText overlays, `GetField` queries.
- Placement redraw path: `DropSelectedPlaceHS` (5561437 8) → resource msg 0x10005 → map mutation →
  `SetModified`; `OnStaticSceneUpdated` merely sets a form flag (+0x6A4); the next frames do
  `BuildDynamicScene`/`BuildStaticScene` + blits. So a click-storm serializes as
  click → frame(s) → click → frame(s)…, exactly the reported "click 30 times, watch them load in".
- **Scanner floater** (`TScanner`, AoWTools.dpl): originally suspected of a perpetual full-map
  redraw — **DISPROVEN, see §2.** `Draw` (0x5970395C) only re-creates surfaces + re-arms `step`
  when the surface is null (first draw / width change); steady state = 2 tiny minimap blits +
  conditional `DrawObjects`. Idle profile shows no `DrawMap`/`DrawObjects` samples with the floater
  open. Per-placement the exe does call changed-rect `DrawMap` + `SetObDrawn(0)` via
  `TheMapMapChanged`/`TheMapScannerIconsChanged` (exe 0x42139C / 0x4215AC) — event-driven and
  correct, cheap. `TScanner` is **shared with the game** (AoW.exe/AoWCompat.exe import it).
- **Palette grids** (`TEResourceGrid`, EngineP.dpl): tab click = WM_PAINT of the shown grid;
  `DrawCell` (0x5551F9FC) → `TEResource.Draw` → ILPACK `BltLibraryImage` → `TImage08.ShowDC`
  (0x55215CA8): temporary 16-bpp DIB per cell, palette remap, StretchDIBits, region ops. Measured
  full-grid repaint = **17 ms**, tab-cycle profile is **GDI-bound** (win32u 60 %), **not**
  disk-bound (ILPACK 0.4 %, no ReadFile) — so images are resident (LoadMode load-and-keep); the
  feared per-cell `LoadDiscardableImageData` reload does **not** occur here. Fast enough; the tab
  lag was pump serialization, not paint.

### Why the user saw ~0.5 s (synthesis, post-measurement)

**Everything traced back to the 67 ms (15 Hz) pump.** Placement: the click handler is ≤58 ms but
each queued click waits a frame, so a click-storm drains at 15/s. Tabs: the switch (~34 ms) + grid
paint (~17 ms) each wait a frame, and the switch involves several message round-trips → stacks to
a fraction of a second at 15 Hz. **FrameRate 60 collapses all of it** (pump ~17 ms; tab settle
134 → 62 ms; placement drain ~5×). The scanner and palette were red herrings once measured.

## 2. Fixes — outcome

1. **FrameRate 15 → 60 (map view). APPLIED + mechanically verified.** DFM `vaInt8`, one byte/exe:
   - AoWDevEd.exe value byte **0x751A0**, AoWEd.exe **0x743E0** (0x0F→0x3C). Anchor
     `\x09FrameRate\x02` verified before write. Backups `.pre-edfps`.
   - Other FrameRate sites left alone: scanner display = 1 (0xD353A dev / 0xD2762 ed), three other
     displays = 20. **Do NOT raise the scanner display's FrameRate** (would make it redraw more).
   - Verified: pump 67.0 → ~12–17 ms; tab settle 134 → 62 ms (vanilla-vs-patched A/B). Awaiting the
     user's subjective in-editor confirmation before marking CONFIRMED WORKING.
   - **Why 60 and not higher — measured, do NOT re-litigate.** FrameRate sweep 60/120/240 gives an
     identical pump median (~17 ms = 1000/60): the DirectDraw loop is **vblank-locked to the 60 Hz
     primary display** (this rig: RTX 4090 output @60 Hz where the editor runs; a 119 Hz AMD panel
     exists but the editor did not sync to it). Values >60 write a number the vblank wait ignores →
     zero benefit; nothing in the system exceeds 119 Hz so 240 is pointless regardless. On a
     >60 Hz display the editor *might* benefit up to that panel's Hz (≤120 here) if its DDraw path
     syncs there — untested/unachieved. Also: idle CPU while active ≈25 % of one core at any
     FrameRate (frame-loop vblank spin + per-frame `UpdateFrame`), inherent to the design.
   - Script: `build_editor_framerate.py` (dry-run default, `--apply`, `--fps N`, idempotent,
     verify-before-write, auto-backup). **Revert (checked 2026-07-30):** `AoWEd.exe.pre-edfps` is that
     file's only layer → safe single revert. `AoWDevEd.exe.pre-edfps` is the **oldest of 8** layers →
     restoring it destroys all 7 features applied since; re-tune the FrameRate with `--fps N` (it
     rewrites in place) or undo surgically instead.
2. **Scanner perpetual-redraw fix — NOT NEEDED (hypothesis disproven, see §1/§3).** Would have been
   a cave in shared AoWTools.dpl for a non-problem. `MapDrawSteps` DFM byte (0xD3C3D dev / 0xD2E65
   ed) left at 1 deliberately — raising it only bands a redraw that isn't happening and would show
   a perpetual sweeping band if it did.
3. **Palette cache — NOT NEEDED.** Paint is 17 ms and GDI-bound, not the bottleneck; resolved by
   FrameRate. No ILPACK/EngineP cave (both shared with the game).
4. (Optional, unimplemented) Trim per-frame status-bar/ILF `SetText` in `HSMEditUpdateFrame`
   (exe-local) to only-on-change — low value now that FrameRate is fixed.

## 3. Bug sweep — triage (NONE patched; rationale each)

- **TheMapMapChanged region math** (exe 0x4213B2–C7, W=x2−x1): **REFUTED.** Standard Delphi
  *exclusive* `TRect` (Right/Bottom one-past) → `x2−x1` is the correct width; matches the −6 border
  offset and every other `DrawMap` call site. Not a bug.
- **TScanner.Draw surface-recreate compares width only** (0x597039DF: `cmp eax,[ebp-0x1C]`):
  **real but near-unreachable + shared.** Height-only resize of the display surface keeps a stale
  surface; self-corrects on any width change. Scanner is a fixed-size floater in the editor, and a
  fix means a cave in shared AoWTools.dpl (affects the game). Not worth the risk. Documented.
- **`ValidateResourceID`** (EngineP 0x5551B134): O(M·N) linear FindResource per resource during
  grid activation; `xor [res+0xC],0xFFFF` ID flip; random re-roll ≤10 tries, no unique fallback.
  Shared EngineP.dpl; grid activation runs on map-open (not per-tab), so low felt impact. Not
  patched — would need game-side testing for a non-felt issue.
- **`TECustomResourceGrid.SetResource`** (0x5551FBB8): possible use-after-free when overwriting an
  occupied slot (in-place virtual-destruct while the MOR list may hold the pointer). **UNPROVEN** +
  shared. Not blind-patched — would need to prove reachability/aliasing first.
- `BltLibraryImage` over-wide clip restore (0x552135A5), `DrawCell` double image fetch
  (0x5551FA5F/74 vs 0x5551FB23): cosmetic/waste, harmless. First-click-after-activation eaten
  (`[THSMEdit+0x1D4]`): by design (drag guard).

**Net:** the one clear win (FrameRate) is applied; the remaining items are either non-bugs, or
sit in game-shared DLLs (AoWTools/EngineP/ILPACK) with low/no felt impact and don't justify a risky
binary patch. Deliberately leaving them documented rather than patched.

## 4. Area copy-paste (radius 3/5/7) — design

> **SUPERSEDED — see `Editor_CopyPaste_Design.md` for the authoritative, up-to-date design**
> (finalized controls: Ctrl+mouse-wheel rotation; exclude armies+cities+event-markers; include
> items+clouds+crops). The text below is the earlier draft (Ctrl+Shift+R rotation, event-marker
> filter "pending") kept only for history; do not implement from it.

### What already exists (all in HSEPack.dpl, disassembled)

- `THSMEdit.CutHS/CopyHS/PasteHS/DeleteHS` (55612F8C/556130B4/55613188/55613320), wired to
  Ctrl+X/C/V/Del in `KeyDown` (556133C4, via VMT slots +0xB8/+0xBC/+0xC0/+0xC4) and to the
  right-click popup + main-menu Edit (exe WM_COMMAND ids 69/70/71/72).
- `CopyHS`: iterates **the whole `THexagonSpriteSelection`** (engine+0x18; TList-backed,
  `GetCount` vmt+0x54, `GetHS` 5560BB30) → `TECopyComponent` (EngineP) →
  **`CopyToClipboard`** under format name from `GetCopyPasteHSIDstring`
  ('Surface Hexagonsprites' / 'Underground Hexagonsprites' — per level, so cross-level paste is
  blocked by design).
- `PasteHS`: anchor = first selected hex (getters vmt+0x74/+0x78/+0x7C, byte coords →
  `HXtoHP`+0x10 border margin); `PasteFromClipboard` → for each object
  **`THSMap.Place`(5560CFB4) at the anchor** (all objects flattened onto one hex — current
  semantics = single-hex stack copy), failures → free + MessageBeep; then `SetModified`.
- Serialization is the engine's rwEObject framework (same as .hsm save) → **object positions
  survive the clipboard round-trip** (high confidence; verify GetXhx pre-Place when implementing).
- Field access for radius-select: `TMapContainer.GetField(x,y)`, `TMapField.GetCount` (55606FC4)
  + `TMapField.GetHN` (55606F28) enumerate a hex's sprites; `THexagonSpriteSelection.
  SelectLocationHS` (5560BBF0) / `UnselectAll` (5560BAC8) build the selection.

### Refined design v2 (2026-07-07, post user requirements: rotation + content filter)

**User requirements**: radius-N area copy/paste; paste rotatable in 6 directions (k×60°);
include non-settlement/city structures; exclude unit armies.

#### Grounded facts (disassembly-verified this session)

- **Grid layout** (`HXtoHP` 5560E3B4 / `HPtoHX` 5560E3D8): `x_px = x*32+8`,
  `y_px = y*32 + (x&1)*16` → **odd-q offset layout** (odd *columns* shifted down half a hex).
  `THSMap.Place` takes *pixel* coords; PasteHS's own pattern is `HXtoHP(x,y)` then `+0x10,+0x10`
  (hex center). Our paste computes target hex coords and reuses exactly that.
- **Rotation math** (cube coords; deltas are translation-invariant, offsets are NOT):
  `q = x; r = y − (x − (x&1))/2; s = −q−r`. Rotate 60° CW: `(q,r,s) → (−r,−s,−q)`, k times.
  Back: `x = q; y = r + (q − (q&1))/2`. Compute **absolute anchor cube** and **absolute object
  cube**, rotate the *delta*, add to paste-anchor cube, convert back. `(x&1)` is bit0 — correct
  for negative odd values in two's complement; `(q−(q&1))` is even so `sar 1` is exact.
  A radius-R disc maps onto itself under rotation about its center → no shape distortion.
- **Roads rotate for free**: `Road.TRoad.UpdateNeighbourTransitions` (55617064) +
  `TAbstractRoad.NeighbourTerrainChanged` — road appearance derives from neighbors after
  placement, like terrain edges. No direction bits to remap. (Verify visually at impl.)
- **The select tool is single-HS** (`SelectLocation` 5560BC0C: pixel hit-test via HS virtual
  +0xF8, cycles through the stack, `UnselectLocation` first) — so vanilla Ctrl+C copies ONE
  sprite. Area copy therefore enumerates fields directly: the field's HS array is at
  `[field+8]` (dword items), count via field vtable `+0x54` (= `TMapField.GetCount`) — the exact
  access pattern SelectLocation itself uses.
- **Class taxonomy for the filter** (AoWEPACK VMT scan, parent chains):
  `TCity → TPlayerCropStructure → TPlayerStructure → TStructure` (cities ARE structures — filter
  must match `TCity`, NOT `TPlayerStructure`, or mines/nodes get excluded:
  `TAirNode → TProductionPlace → TPlayerStructure → TStructure`);
  `TArmyHS → TUnitHS → …` (armies); `TExplorationSite → TStructure`;
  `TCrop/TItemHS/TFlagEvent/TMoveOnEvent/TSmokeCloud/TPad` are direct HSEPack-base children.
- **Cave cannot use Delphi `is` against AoWEPACK classes**: HSEPack must not import from
  AoWEPACK (dependency is the other way). Filter = **walk the VMT parent chain comparing class
  names** (name ptr at VMT−0x20 shortstring, parent classref at VMT−0x18) — import-free,
  subclass-safe, ~25 asm lines.

#### Filter rules

Exclude an HS iff its class ancestry contains:
- `TUnitHS` (⇒ armies incl. `TArmyHS`) — **user requirement**
- `TCity` (⇒ settlements) — **user requirement**
- proposed additionally: `TFlagEvent`, `TMoveOnEvent` (invisible scenario-event markers —
  copying event logic with scenery is surprising) — **PENDING user decision**
Include everything else: terrain hexagons, overlay objects, roads, all non-city structures
(mines/nodes/altars/sites keep their owner — same as vanilla paste), items, clouds, crops.
Exclusion list = data-driven name table in the cave (easy to adjust).

#### UX (all in THSMEdit.KeyDown, Ctrl branch 556133DB extended to check Shift)

- **Ctrl+Shift+1..9** — set copy radius R (covers 3/5/7); `ShowMsg` "Copy radius: N".
- **Ctrl+Shift+C** — copy disc of radius R around the hovered hex (hover coords via
  `THSMapMouse` getters as MouseDown does). Stores anchor hex + R in cave globals.
- **Ctrl+Shift+R** — rotation += 60° (mod 360); `ShowMsg` "Paste rotation: 120°".
- **Ctrl+Shift+V** — paste at hovered hex with current rotation.
- Same-level only (existing per-level clipboard format names) — vanilla behavior preserved.
- v1 has **no preview and no undo** (the editor has no undo anywhere; save before stamping).
  Future: preview via the place-HS ghost machinery; undo via pre-paste region snapshot.

#### The two caves (revised)

1. **Area-copy** (KeyDown hook): `UnselectAll`; for each offset in radius-R disc (cube-distance
   loop): bounds-check against map dims, `TMapContainer.GetField(x,y)`; for i in 0..count−1:
   hs = `[field+8][i]`; **dedupe** (skip if already in selection — `TList.IndexOf`, multi-hex
   objects appear in several fields; membership rule = base hex in disc via `GetBaseHX`);
   apply name-chain filter; `SelectLocationHS(sel, hs)`. Insert in field z-order (bottom-up) so
   terrain hexagons place before overlays on paste (CopyHS reverses, PasteHS reverses again ⇒
   net selection order = place order). Then fall into existing `CopyHS` (55 6130B4); stash
   anchor+R+a fresh copy-stamp in cave globals; `UnselectAll` after.
2. **Rotated offset-paste** (cave over the Place loop at 5561327F–556132A3): guard: if cave
   copy-stamp unset (clipboard from before this session) → vanilla behavior. Else per object:
   read stored hx/hy (getters vmt+0x74/+0x78 — byte coords, positions survive rwEObject
   serialization), delta = objCube − copyAnchorCube, rotate k×60°, target = pasteAnchorCube +
   delta → offset coords → `HXtoHP`+0x10 → `THSMap.Place`. Failures beep per object (vanilla);
   `SetModified` at end (vanilla). Multi-hex structures: base lands rotated, footprint itself is
   NOT rotated (no rotated sprites exist) — Place's own validity check rejects collisions.

Both caves in a new PE section of **HSEPack.dpl** (position-independent, call/pop deltas for
globals; game loads this DLL but never reaches HSMEdit paths). Backup `.pre-areacopy`.
Effort: ~1–2 sessions + in-editor verification.

#### Implementation-time verifications (ordered)

1. `[field+8]`/vtable+0x54 array access on a live field (or `GetHN(i)` arg order as fallback).
2. Positions really survive the clipboard round-trip (read a pasted object's hx/hy pre-Place).
3. Place order: terrain-hexagon-first assumption (selection→copy→paste double reversal).
4. Selection visual side-effects with ~100 HSes selected (TriggerSelectEvent storm) — if noisy,
   bypass selection entirely and build the TECopyComponent list directly (CopyHS's loop is
   trivial to replicate in the cave).
5. Roads/terrain transitions visually correct after rotated paste (auto-derive assumption).
6. Map-border clipping: GetField bounds guard (map dims from TMapLevel fields seen in
   Scanner.SetMap: level+0xC / level+0x10).

## 5. Tooling added this session (`re_tools/`)

- `aowsyms.py` — symbol resolution for any AoW module (dpl exports; exe VMT scan + published
  method tables).
- `dasm.py` — annotated capstone disassembler for **any** module (resolves cross-DLL import
  thunks, IAT slots, shortstrings; `dasm.py <mod> sym <substring>` works too). Supersedes the
  AoW.exe-only dump_exe.py for package work.
- `xref.py` — rel32 call/jmp + absolute-dword xref scanner, hits labeled by enclosing symbol.
- `mtab.py` — published-method-table dumper (event handler name → code VA) for exe classes.
- `sampler.py` — Wow64 sampling profiler (suspend/GetThreadContext/EIP histogram, symbolized).
- UI automation (used for the live experiments; may be handy again): `winspy.py` (window tree),
  `clicker.py` (PostMessage clicks/tabs/keys), `menucmd.py` (menu tree + WM_COMMAND),
  `grabwin.py` (PrintWindow capture of occluded windows), `topmost.py`.
- Empirical VMT layout note (Delphi 3, this codebase): self-ptr −0x40, **method table −0x28**,
  field table −0x2C, class name −0x20, instance size −0x1C, parent −0x18.
- DFM value types: 14 = vaCollection (`{[idx] vaList props… 0}* 0`) — dfm parser in scratchpad
  handles it; worth folding into `dfm_parse.py` if needed again.

## 6. Measurement protocol for the user's real map (2 minutes)

1. Open the editor with the big map, start clicking placements / tabs.
2. `python "Modding Resources/re_tools/sampler.py" --seconds 20 --hz 200 --out prof.txt`
3. The symbol histogram names the dominant cost (scanner DrawMap/DrawObjects vs ILPACK ShowDC vs
   waits). If waits dominate with ~15 Hz pump probes → FrameRate patch first.
