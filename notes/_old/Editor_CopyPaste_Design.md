# Editor Area Copy-Paste (radius N, 6-way rotatable) — Design

**Status: DESIGN ONLY — not built, not applied. 2026-07-07.**
Target: `AoWDevEd.exe` / `AoWEd.exe` editor via caves in **HSEPack.dpl** (position-independent —
that DLL rebases at runtime; game loads it too but never reaches the `HSMEdit` code paths).
Authoritative design doc for this feature. Supersedes §4 of
`Editor_Lag_CopyPaste_Investigation_2026-07-07.md`.

## Finalized requirements (user, 2026-07-07)
- **Radius-N area copy/paste** (e.g. discs of radius 3 / 5 / 7 hexes).
- **Paste rotatable in 6 directions** (k×60°), control = **Ctrl + mouse-wheel**.
- **Include**: all non-settlement/city structures (mines, nodes, altars, sites…), terrain,
  overlay objects, roads, ground items, clouds, crops.
- **Exclude**: unit armies; cities/settlements; **event markers** (flag events, move-on events).
- No preview, no undo in v1 (the editor has no undo anywhere — save before stamping).

## What already exists (HSEPack.dpl, disassembly-verified)
- `THSMEdit.CutHS/CopyHS/PasteHS/DeleteHS` (55612F8C/556130B4/55613188/55613320), wired to
  Ctrl+X/C/V/Del in `THSMEdit.KeyDown` (556133C4, via VMT slots +0xB8/+0xBC/+0xC0/+0xC4) and to
  the right-click popup + main-menu Edit (exe WM_COMMAND ids 69/70/71/72).
- `CopyHS`: iterates **the whole `THexagonSpriteSelection`** (engine+0x18; TList-backed,
  `GetCount` vmt+0x54, `GetHS` 5560BB30) → `TECopyComponent` (EngineP) → `CopyToClipboard` under a
  per-level format name from `GetCopyPasteHSIDstring` ('Surface Hexagonsprites' /
  'Underground Hexagonsprites' — so cross-level paste is blocked by design; we keep that).
- `PasteHS`: anchor = first selected hex (getters vmt+0x74/+0x78/+0x7C, byte coords →
  `HXtoHP`+0x10 border margin); `PasteFromClipboard` → for each object **`THSMap.Place` (5560CFB4)
  at the anchor** (vanilla flattens the whole clipboard onto ONE hex); failures → free +
  MessageBeep; then `SetModified`.
- Serialization = the engine's `rwEObject` framework (same as `.hsm` save) → **object positions
  survive the clipboard round-trip** (verify `GetXhx` pre-Place at impl).
- Field/selection API for area-select: `TMapContainer.GetField(x,y)` (55608D84),
  `TMapField.GetCount` (55606FC4) / `GetHN` (55606F28) enumerate a hex's sprites;
  `THexagonSpriteSelection.SelectLocationHS` (5560BBF0) / `UnselectAll` (5560BAC8) build selection.

## Grounded facts (this session)
- **Grid layout** (`HXtoHP` 5560E3B4 / `HPtoHX` 5560E3D8): `x_px = x*32 + 8`,
  `y_px = y*32 + (x&1)*16` → **odd-q offset** (odd columns shifted down half a hex). `THSMap.Place`
  takes *pixel* coords; PasteHS does `HXtoHP(x,y)` then `+0x10,+0x10` (hex centre) — we reuse that.
- **Rotation math** (cube coords; deltas are translation-invariant, offsets are NOT):
  `q = x; r = y − (x − (x&1))/2; s = −q−r`. Rotate 60° CW: `(q,r,s) → (−r,−s,−q)`, applied k times.
  Back: `x = q; y = r + (q − (q&1))/2`. Rotate the *delta* (object − copy-anchor), add to the
  paste-anchor cube, convert back. `(x&1)` = bit0 (correct for negative odds in two's complement);
  `(q−(q&1))` is even so `sar 1` is exact. A radius-R disc maps onto itself under rotation → no
  shape distortion.
- **Roads rotate for free**: `Road.TRoad.UpdateNeighbourTransitions` (55617064) +
  `TAbstractRoad.NeighbourTerrainChanged` — road appearance derives from neighbours after
  placement (like terrain edges); no direction bits to remap. Verify visually at impl.
- **The vanilla select tool is single-HS** (`SelectLocation` 5560BC0C: pixel hit-test via HS
  virtual +0xF8). So area copy must enumerate fields directly: a field's HS array is at `[field+8]`
  (dword items), count via field vtable +0x54 (= `TMapField.GetCount`) — the exact access pattern
  `SelectLocation` itself uses.
- **Class taxonomy for the filter** (AoWEPACK VMT parent-chain scan):
  - `TCity → TPlayerCropStructure → TPlayerStructure → TStructure` — **cities ARE structures**;
    filter must match `TCity` exactly, NOT `TPlayerStructure` (that would also drop mines/nodes:
    `TAirNode → TProductionPlace → TPlayerStructure → TStructure`).
  - `TArmyHS → TUnitHS → …` (armies); `TExplorationSite → TStructure`;
    `TCrop / TItemHS / TFlagEvent / TMoveOnEvent / TSmokeCloud / TPoisonCloud / TPad` are direct
    HSEPack-base children.
- **The cave cannot use Delphi `is` against AoWEPACK classes** (HSEPack must not import AoWEPACK —
  the dependency runs the other way). Filter = **walk the VMT parent chain comparing class names**
  (name ptr at VMT−0x20 shortstring, parent classref at VMT−0x18) — import-free, subclass-safe,
  ~25 asm lines.

## Filter rules (FINAL)
Exclude a hexsprite iff its class ancestry contains any of:
- `TUnitHS`  ⇒ armies (incl. `TArmyHS`)            — excluded (user)
- `TCity`   ⇒ cities / settlements                 — excluded (user)
- `TFlagEvent`, `TMoveOnEvent` ⇒ scenario event markers — **excluded (user)**

Include everything else: terrain hexagons, overlay objects, roads, all non-city structures
(mines / nodes / altars / exploration sites — they keep their owner, same as vanilla paste),
ground items (`TItemHS`), clouds (`TSmokeCloud` / `TPoisonCloud`), crops (`TCrop`).
The exclusion set is a **data-driven name table** in the cave — trivial to adjust later.

## Controls (FINAL)
- **Ctrl+Shift+C** — copy a disc of the current radius around the hovered hex.
- **Ctrl+Shift+V** — paste at the hovered hex with the current rotation.
- **Ctrl + mouse-wheel** — rotate the pending paste ±60° per wheel notch (wheel-up = CW,
  wheel-down = CCW); wrap mod 360; `ShowMsg` "Paste rotation: N°".
- **Ctrl+Shift+1..9** — set copy radius (covers 3/5/7 and more); `ShowMsg` "Copy radius: N".
- Same map level only (per-level clipboard format names) — vanilla behaviour preserved.

**Control-hook note:** copy/paste/radius are keystrokes → hook `THSMEdit.KeyDown` (556133C4),
extending its Ctrl branch (556133DB) to also test Shift. **Rotation is a mouse-wheel event, a
different message path** (`WM_MOUSEWHEEL` → VCL `TControl.MouseWheel` / `CMMouseWheel`). At impl,
verify whether `THSMEdit` already has a MouseWheel handler to hook, or whether we must add
`WM_MOUSEWHEEL` handling (window-proc/MsgProc hook). Confirm plain-wheel is still free to scroll
and that Ctrl+wheel isn't already bound (zoom, etc.).

## The three caves (HSEPack.dpl, position-independent)
1. **Rotation state (mouse-wheel hook)** — on Ctrl+mouse-wheel over the map view: `rot = (rot ± 1)
   mod 6`; store in a cave global; `ShowMsg`. Small.
2. **Area-copy (KeyDown hook)** — `UnselectAll`; for each offset in the radius-R disc
   (cube-distance loop): bounds-check vs map dims, `TMapContainer.GetField(x,y)`; for
   i in 0..count−1: hs = `[field+8][i]`; **dedupe** (skip if already selected — `TList.IndexOf`;
   multi-hex objects appear in several fields, membership rule = base hex in disc via `GetBaseHX`);
   apply the name-chain filter; `SelectLocationHS(sel, hs)`. Insert in field z-order (bottom-up) so
   terrain-hexagons place before overlays on paste (CopyHS reverses, PasteHS reverses again ⇒ net
   selection order = place order). Then fall into existing `CopyHS` (556130B4); stash copy-anchor
   hex + R + a fresh copy-stamp in cave globals; `UnselectAll` after.
3. **Rotated offset-paste (cave over the Place loop 5561327F–556132A3)** — guard: if the cave
   copy-stamp is unset (clipboard predates this session) → vanilla single-hex behaviour. Else per
   object: read stored hx/hy (getters vmt+0x74/+0x78, byte coords), delta = objCube −
   copyAnchorCube, rotate k×60° (k = stored rot), target = pasteAnchorCube + delta → offset coords
   → `HXtoHP`+0x10 → `THSMap.Place`. Per-object failures beep (vanilla); `SetModified` at end
   (vanilla). Multi-hex structures: base lands rotated, footprint sprite is NOT rotated (no rotated
   artwork exists) — Place's own validity check rejects overlaps.

Backup `<file>.pre-areacopy`. Effort: ~1–2 sessions + in-editor verification.

## Implementation-time verifications (ordered)
1. **Hook fires** (LESSON from autosave v1): before building, confirm the KeyDown/mouse-wheel hooks
   actually execute on the intended input — patch a minimal counter, read it from the cave's fixed…
   no, HSEPack rebases → read via module-base + offset (see `re_tools/get_base.py`). Don't invest in
   the full cave until the trigger is proven live.
2. `[field+8]` / vtable+0x54 array access on a live field (or `GetHN(i)` arg order as fallback).
3. Positions survive the clipboard round-trip (read a pasted object's hx/hy pre-Place).
4. Place order: terrain-hexagon-first assumption (selection→copy→paste double reversal).
5. Selection visual side-effects with ~100 HSes selected (`TriggerSelectEvent` storm) — if noisy,
   bypass selection entirely and build the `TECopyComponent` list directly in the cave (CopyHS's
   loop is trivial to replicate).
6. Roads / terrain transitions look right after a rotated paste (auto-derive assumption).
7. Map-border clipping: `GetField` bounds guard (map dims from `TMapLevel` fields — level+0xC /
   level+0x10, per `Scanner.SetMap`).
8. Mouse-wheel: Ctrl+wheel is free (no existing zoom/scroll binding); plain wheel still scrolls.
9. Filter correctness: place one of each excluded type (army, city, flag event, move-on event) plus
   included types in a test disc, copy-paste, confirm only the right ones transfer.
