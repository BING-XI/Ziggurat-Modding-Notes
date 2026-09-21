# Strategic-map cursor "dead zone" on the right at large/4K window — investigation

**Status: CONFIRMED WORKING (2026-07-06).** User validated in-game: right/bottom real hexes on a
small map in a wide window are now live (cursor + clicks), off-map margins stay inert. Fix in
HSEPack.dpl via `build_mapcursor_fix.py` (backup `HSEPack.dpl.pre-mapcursor`).
The earlier DCPACK `GetMousePos` hack was WRONG (no in-game effect → not on the map-cursor path);
reverted. User confirmed: **bug only on SMALL maps** (~64-hex + 6-hex padding/side ≈ 74–76 wide),
never on large maps, and it hits **real operational hexes** on the right — the map renders CENTERED
with empty out-of-bounds space on each side.

## CONFIRMED ROOT CAUSE — centered small map + viewport-vs-mapwidth mismatch in Move
A map smaller than the viewport is **centered** via a **negative scroll origin**
(`[map+0x80]` = −leftMargin; `[map+0x84]` vertical). The real map then occupies viewport-x ∈
`[leftMargin, leftMargin+mapWidthPx]`. But `HSEngine.THSMapMouse.Move @ 0x5560B8F8` rejects on
**`viewport-x > GetMaxXhp`** (`0x5560C3EC` = the MAP's pixel width ≈ mapWidthHexes×32 ≈ 2360),
storing the invalid sentinel `0x80000000`. That **pre-empts** the correct, world-based accessors:
- `GetXhx @ 0x5560B6B0`, `GetYhx @ 0x5560B718`: `world = [map+0x80/84]scroll + mouse`; reject only
  if `column<0` or `column≥mapWidth` (`[[map+0x10]+0xc]`) → return `-1`. (Verified.)
- `GetXhp @ 0x5560B638`, `GetYhp @ 0x5560B674`: `world = scroll + mouse`; reject if `>GetMax*hp`
  or `<0`. (Verified.)
So the map's right portion (real hexes, world-x ∈ [0,mapWidth]) is wrongly killed by Move before the
accessors — cursor frozen + clicks dead. Dead-strip width = leftMargin = (viewport−map)/2, growing
with window width. Large maps (≥viewport) aren't centered → no bug. Explains everything incl. the
DCPACK no-op (wrong layer) and threshold = map width.

## APPLIED FIX (build_mapcursor_fix.py) — HSEPack.dpl
Neuter ONLY Move's two upper-bound rejections so it stores the real mouse whenever x,y≥0; the four
accessors then validate with correct world coords (identical to how the map's LEFT side already
works; off-map margins stay inert):
  `@ 0x5560B917  7F 14 (jg, x>GetMaxXhp) -> 90 90`   `@ 0x5560B923  7F 08 (jg, y>GetMaxYhp) -> 90 90`
In-place, 4 bytes, position-independent (HSEPack rebases; no abs refs). x≥0/y≥0 lower checks kept.
Backup `HSEPack.dpl.pre-mapcursor` (exists). **⚠ Revert: do NOT run `build_mapcursor_fix.py --revert`.**
That flag is *not* surgical — it does a whole-file `shutil.copyfile(BACKUP, TARGET)`, and
`.pre-mapcursor` is no longer the newest HSEPack layer (`.pre-rendergate` sits above it), so it would
silently destroy the render-gate performance fix. A script flag reading "revert" is not evidence that
the revert is safe.

Since this patch is only **4 bytes, in place**, undo it surgically instead — write the originals back:
`7F 14` @ `0x5560B917` and `7F 08` @ `0x5560B923`. (Making `--revert` do exactly that, instead of copying
the file, is a one-line fix worth doing.)

Test the strategic map (small map, wide window: right + bottom hexes now live) and spot-check the editor
(AoWDevEd loads HSEPack too) + that off-map margins still show the default cursor.

## NEW leading hypothesis (2026-07-06): the window is wider than the MAP (off east edge)
`~2360 ≈ 73–74 hexes × 32 px` = the map's own pixel width. The map-cursor coordinate flows through
`HSEngine.THSMapMouse` (HSEPack): `Move @ 0x5560B8F8` stores the mouse and rejects it when
`x > GetMaxXhp` (`0x5560C3EC` = pixel of last hex col +0x28 ≈ mapWidthHexes×32), and
`GetXhx @ 0x5560B6B0` / `GetXhp @ 0x5560B638` **independently** reject via world coords
(`worldX = [map+0x80]scroll + mouseX`; reject if `column≥mapWidth` or `worldX>GetMaxXhp`). So the
cursor correctly reads "no hex" once the viewport passes the map's east edge. This explains: threshold
≈ map width; "loads 960, fine until ~2360"; and why the DCPACK patch did nothing (wrong layer).
⇒ if true, this is largely "window wider than the map" (off-map margin), NOT a coordinate bug.

**MUST discriminate before any patch (decisive test):** does the threshold **track map size**?
- Load a clearly WIDER map, stretch past ~2360: if the dead zone moves right / disappears →
  confirmed off-map (window > map). Fix would be about the map-vs-window relationship (center /
  letterbox / cap viewport to map), not the cursor.
- If the dead zone stays at ~2360 regardless of map width → it IS a real coordinate cap; keep digging
  (find where the client mouse-x is capped at ~2360 before reaching the map — event delivery / a
  control width / a surface). 
Also: is there real terrain+objects UNDER the cursor in the dead strip, or blank map-edge/void?

## (SUPERSEDED) earlier display-layer theory — kept for the record, DO NOT re-try as-is
`GetMousePos @ 0x55103FC0` bounds-reject @ `0x551040B6` was the basis of `build_cursor_fix.py`
(3-byte neuter `83 3F 00→EB 1D 90`). **Confirmed NOT on the map-cursor path (patch had no in-game
effect).** Patch reverted; the dead script `build_cursor_fix.py` and redundant backup
`DCPACK.dpl.pre-cursorfix` were **removed after confirmation** (DCPACK.dpl verified byte-identical to
the backup first). Recorded here so it isn't retried. NB `0x55103FC0` may still govern *other*
windowed mouse input (menus/dialogs) — never tested, since this bug turned out to be elsewhere.

## (NOT APPLIED — the DCPACK theory) build_cursor_fix.py
⚠ **This patch is not installed and cannot be reverted or re-run: it had no in-game effect, the script
`build_cursor_fix.py` was deleted and `DCPACK.dpl.pre-cursorfix` was removed** (see the SUPERSEDED
section above for the confirmation). The real fix is the HSEPack `.pre-mapcursor` patch at the top of
this doc. Kept for the still-valid addresses below — `0x55103FC0` may govern *other* windowed mouse
input (menus/dialogs), which was never tested.

Windowed mouse reads go through `TDisplayCtrl.GetMousePos @ 0x55103FC0` (vtable+0x98 of the windowed
DC `TWindows16DC` — verified). It computes the client-relative mouse, then a **geometric bounds
test @ `0x551040B6`** rejects out-of-bound points with `(-1,-1)`, which propagates to the map and
freezes the cursor + kills clicks past ~2340 px. Because the render is 1:1 (sharp, "more map"), the
already-computed coordinate is correct across the whole window. The patch neuters **only** that
geometric test so the function falls through to its accept path (returns the computed coords):

  `@ 0x551040B6  83 3F 00 (cmp dword [edi],0)  ->  EB 1D 90 (jmp 0x551040D5 'mov al,1'; nop)`

Single-site, 3-byte, in-place (no cave/rebasing). The **separate** surface/focus gate @ `0x55103FD4`
(legit `(-1,-1)` when the mouse isn't over this display) is left intact. Was idempotent and
verify-before-write; the backup and its `--revert` are both gone (see the banner above).
**⚠ Shared DC: this routine serves the whole windowed UI — test menus/dialogs/combat, not just the map.**
If this both fixes the map AND leaves other screens fine → confirmed diagnosis + fix. If it misbehaves
elsewhere, fall back to a narrower fix (e.g. only widen the bound to the live client rect, or gate on
the map window) — the emergent ~2340 source is still not fully pinned (see below).

## Symptom (user report)
On a 4K monitor with the game window stretched large, the map cursor stops changing shape based on
the hovered hex over **a large fraction of the right side** of the screen; clicks there also don't
trigger hex/structure actions (e.g. opening a wizard tower dialog). Terrain in that region is drawn
**correctly**. Shrinking the window immediately removes the dead zone. Left side works and is
aligned (cursor acts on the hex it's over).

## Confirmed call chain (all static RE)
Modules & preferred bases: AoWEPACK.dpl `0x55700000`, **HSEPack.dpl `0x55600000`** (the "HSEngine"
hex-sprite package — Ghidra does NOT have it; use re_tools/capstone), **DCPACK.dpl `0x55100000`**
(DisplayC — DirectDraw/GDI display abstraction).

1. **Cursor only updates over a valid hex.** `AoWE.TAoWHSMap.MouseMoved` @ `0x55777A58`
   (AoWEPACK) calls `THSMapMouse.GetXhx`; if it returns invalid it early-returns, so
   `TAoWHSMap.UpdateCursor` @ `0x55777B20` never re-evaluates → cursor stays in its last/default
   state and click-mode logic (the `[map+0xc]+0xd` state word) is never set. This is the visible
   effect.
2. **The hex math is clean 32-bit — NOT the bug.** `THSMapMouse.GetXhx` @ `0x5560B6B0` /
   `GetXhp` @ `0x5560B638` compute `worldX = map[+0x80](scrollX) + mouseX` and call the pixel→hex
   converter @ `0x5560E3D8` = `col=(worldX-8)>>5`, `row=(worldY-parity*16)>>5` (hexes 32px wide,
   16px stagger). All 32-bit `sar`; **no 16-bit/word overflow anywhere.** `GetMaxXhp` @ `0x5560C3EC`
   (the east-edge bound) is derived purely from **map size**, independent of window.
   `THSMapMouse.Move` @ `0x5560B8F8` stores the mouse or the sentinel `0x80000000` (invalid).
3. **The mouse position comes from the display layer.** HSEPack **imports**
   `DisplayC.TCustomDisplay.GetMousePos` from DCPACK (verified via import table). So the map polls
   the display for the surface-relative mouse.
4. **The rejection happens here → root cause.** `DisplayC.TDisplayCtrl.GetMousePos` @ `0x55103FC0`
   (DCPACK): gets the raw mouse from the DC, subtracts the viewport origin (`DC[+0x30]/[+0x34]`),
   then **bounds-checks** the surface-relative point (@ `0x551040B6`): if `x<0 || x>widthBound ||
   y<0 || y>heightBound` it returns **`(-1,-1)` (`0xFFFFFFFF`)**. `widthBound`/`heightBound` come
   from intersecting the DC rect with a second surface rect (`DC[+0x24]`). That invalid value
   propagates up and freezes the cursor.
   - `TCustomDisplay.GetMousePos` @ `0x55104E6C` just forwards to the active DC's vtable `+0x98`.
   - Fullscreen DC `TDDrawFullScrDC.GetMousePos` @ `0x551073B4` returns the **raw** mouse (no
     scaling) — so fullscreen at native res is unaffected; the bug is a **windowed/stretched** path.
5. **Stretching is in play.** DCPACK imports `gdi32!StretchDIBits`, `SetStretchBltMode`, and
   `GFXE.TSurface.BltStretch` — the windowed blit stretches the back surface to the window, which is
   why terrain still fills/looks correct in the dead region. `ResizeBackSurfaces` @ `0x55104EF4`
   stores requested dims in `DC[+0x18c]/[+0x190]`.

**Net:** the window is stretched larger than the display **surface bounds** used by
`GetMousePos`; the right strip falls outside those bounds so the mouse reads `(-1,-1)` → the map
sees "no hex" → cursor frozen + clicks inert, even though the stretched image shows terrain there.

## RESOLVED (user-confirmed 2026-07-06): case (a) — render is 1:1, the bound rect is stale/capped
User facts: **windowed, freely resizable** (no fixed resolution); bug triggers past **~2340 px**
window width; past that, terrain is drawn as **"same size, more map shown"** (sharp, NOT stretched).
⇒ the back surface grows 1:1 with the window (`ResizeBackSurfaces` @ `0x55104EF4` reallocs to the
requested size with **no cap**), so the map is drawn & aligned across the full width. The dead zone
is purely a **mouse-acceptance bound** that was NOT grown with the surface.

**The bound = the "primary surface region" RECT stored inline at `[display+0x30..0x3C]`:**
- `TDisplayCtrl.GetPrimarySurfaceRgn` @ `0x55103E78` = `add eax,0x30; ret` (returns `&this[0x30]`).
- `SetPrimarySurfaceRgn` @ `0x55103E64` = `rep movsd` 4 dwords into `[this+0x30]` (L,T,R,B).
- `TCustomDisplay.GetMouseAboveSurface` @ `0x55105170` and `TDisplayCtrl.GetMousePos` @ `0x55103FC0`
  both containment-test the mouse against this rect and return **false / `(-1,-1)`** when outside.
This region stays ~2340 wide while the surface/window grow → right strip rejected → cursor frozen.
The actual (grown) surface size is available on the display object at **`[display+0x18C]` (width) /
`[display+0x190]` (height)** (set by `ResizeBackSurfaces`). Fix = keep the region rect in sync with
that, OR bound the mouse test to `[+0x18C]/[+0x190]` instead of the stale region.

## Corrected object layout (2026-07-06) — earlier notes had wrong-object errors
- **`TDisplayCtrl.GetMousePos` @ `0x55103FC0` runs on a *DC object*** (`TWindowsDC`→`TWindows16DC`
  for windowed; instsize ≤0x64), NOT on `TCustomDisplay`. Class hierarchy (DCPACK): `TAbstractDC`←
  `TDisplayCtrl`(0x4c)←`TWindowsDC`(0x58)←`TWindows16DC`(0x64); and `TDDrawDC`(0x5c)←
  `TDDrawFullScrDC`(0x70). `TCustomDisplay`(0x1ac) / `TDisplay` are the high-level VCL display.
- ⚠ **`[+0x18C]/[+0x190]` live on `TCustomDisplay` (0x1ac), NOT on the DC** — my earlier "bind the
  mouse to `[+0x18C]`" idea was on the wrong object. Discarded.
- In `GetMousePos`: `[DC+0x2c]` = the owning `TCustomDisplay` window (set by `55103F14`:
  `mov [DC+0x2c], edx`). Bounds come from that window's rect getters ∩ `[window+0x24]`, using
  `GetClientRect` (user32, imported).
- **Windowed = GDI `TWindowsDC`** (DirectDraw DC family is fullscreen-only — no `TDDrawWindowedDC`
  exists). Its surface-setup `0x55105D30` creates a `TDisplayGDISurface` (`[DC+0x54]`) sized from the
  window (`GetClientRect`) and sets the region rect `(0,0,surfaceW,surfaceH)`. **Both the render
  surface and the mouse region track the true client size — NO hardcoded cap in this path.**

## So ~2340 is EMERGENT, not a constant — needs runtime ground truth (do NOT guess)
Static code in the windowed path scales everything off `GetClientRect` with no 2340 constant, yet the
mouse dead-zone begins ~2340 while the render keeps drawing sharp "more map." Reconciling these
requires knowing, at runtime: which display mode/DC is actually active; the real values of the region
rect vs the render-surface vs `GetClientRect` when the window is >2340; and whether GDI DIB
(re)creation fails past a size (`55105D30` aborts via `call 55103F14` returning <0 → `jl 55105DF3`,
leaving the prior surface/region). Candidate emergent causes (UNPROVEN): a GDI/DIB or memory-DC max
size; the resize path not re-running the surface-setup past a threshold; a driver/hardware limit.

## Decisive next step (instead of guessing)
1. Confirm the **active display mode** (AoWSetup renderer setting) — pins the DC class/path.
2. Either (a) a reversible **candidate-fix build**: neuter the out-of-region rejection in the
   windowed `GetMousePos` so it returns the *computed* coords instead of `(-1,-1)` — since the render
   is 1:1, correct coords exist across the whole window, so this both **tests** the diagnosis and, if
   right, **is** the fix; or (b) a small **diagnostic build** logging the runtime rects. Prefer (a):
   one test that confirms+fixes. Risk: shared DC → verify menus/other screens, dry-run + backup.
   Must first confirm `TWindowsDC` vtable `+0x98` (GetMousePos slot) resolves to `0x55103FC0`.

## Fix options (once disambiguated) — all in DCPACK.dpl, position-independent cave rules apply
- **A. Widen/repair the bounds rect** in `TDisplayCtrl.GetMousePos` so it matches the actual
  window/render extent (if surface is full-size). Lowest risk to coords.
- **B. Scale the mouse** `surf = win * surfSize / winSize` in `GetMousePos` (if surface is
  fixed/stretched). Must match the blit's stretch exactly or the whole map misaligns.
- **C. Raise the back-surface size cap** in the resize/surface-alloc path.
- ⚠ DCPACK's display DC is used by the **whole game UI**, not just the map — any patch here is
  broad; test menus/other screens too. Per-binary: check AoW.exe vs AoWDevEd.exe separately.

## Key addresses (quick ref)
- AoWEPACK: `TAoWHSMap.MouseMoved 0x55777A58`, `UpdateCursor 0x55777B20`,
  `TAoWHSMapMouse.Move 0x557745F4`.
- HSEPack (`0x55600000`): `GetXhx 0x5560B6B0`, `GetXhp 0x5560B638`, pixel→hex `0x5560E3D8`,
  `GetMaxXhp 0x5560C3EC`, `GetMaxYhp 0x5560C414`, `Move 0x5560B8F8`, `SetViewPort 0x5560D01C`.
- DCPACK (`0x55100000`): `TDisplayCtrl.GetMousePos 0x55103FC0` (**bounds reject @ 0x551040B6**),
  `TCustomDisplay.GetMousePos 0x55104E6C`, `TDDrawFullScrDC.GetMousePos 0x551073B4`,
  `ResizeBackSurfaces 0x55104EF4`, `Resize 0x55105014`, `TWindowsDC.BltSurface 0x55105E64`.

## Tooling note
HSEPack.dpl / DCPACK.dpl are not in Ghidra. Disassemble with capstone via
`re_tools/pescan.py` (`PE(path).exports()` + `rva2off`); scratch scripts pattern in this session.
