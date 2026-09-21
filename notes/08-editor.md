# The map editor — `AoWDevEd.exe`, `AoWEd.exe`, `HSEPack.dpl`

This file covers the **map editor**: its two executables (`AoWDevEd.exe`, the developer build; `AoWEd.exe`, its smaller sibling), and `HSEPack.dpl`, the map-data/map-view module both editors load and the game loads too. It covers editor performance, the dialog/toolbar/palette UX patches, the Map Validation jump-to-location feature, the Party-tool random-army generator, and the never-built area copy-paste design. It does **not** cover the game's own UI (dialogs, combat log, cursor, mouse wheel) — see `07-ui.md`, which also owns the editor's mouse-wheel scrollbar support (`build_wheel_editor.py`) as part of its cross-binary wheel story. It does not cover the Chasm/Sky terrain mechanics that motivated the terrain-palette feature (movement tables, cliff transitions, spell guards) — see `09-terrain-movement.md`; this file covers only the palette UI those terrains needed. General patching conventions (process locking, the AoWCompat lockstep rule, cave-placement discipline, keystone gotchas) live in `_new/CLAUDE.md` and `12-re-toolchain.md`; this file states only the editor-specific consequences of those rules.

## Status table

| feature | status | owning script | binary |
|---|---|---|---|
| Map-view frame rate 15 → 60 → 120 (DFM byte) | ✅ CONFIRMED WORKING (2026-07-07, at 60 fps; raised to 120 same day) — since superseded, see §1.4 | `build_editor_framerate.py` | `AoWDevEd.exe` + `AoWEd.exe` |
| Process timer resolution (`timeBeginPeriod`, kills the 15.6 ms `Sleep` floor) | 🔨 APPLIED, UNTESTED (2026-07-28) | `build_editor_timerres.py` | `AoWDevEd.exe` |
| Render gate (render 1 pass in N, pump every pass) | 🔨 APPLIED, UNTESTED (2026-07-28) — coupled to timerres, §1.3 | `build_editor_rendergate.py` | `HSEPack.dpl` |
| Per-dialog-type directory memory (Map/Set/Text) | 🔨 APPLIED, UNTESTED (v3, 2026-09-11) | `build_dlgdirs.py` | `AoWDevEd.exe` + `HSEPack.dpl` |
| Level Up / Level Down follow the 4-level display order (`Firmament` above Surface); Firmament shows the surface page | 🔨 APPLIED, UNTESTED (2026-09-06) | `build_deved_levelnav.py` | `AoWDevEd.exe` + `AoWEd.exe` |
| Menu options as toolbar rows + start maximized | 🔨 APPLIED, UNTESTED (automated-tested 2026-07-09) | `build_editor_toolbar.py` | `AoWDevEd.exe` |
| Toolbar trimmed to ONE captioned row (File / Developer / Help), `MBRowB` deleted | 🔨 APPLIED, UNTESTED (2026-09-06) | `build_deved_toolbar_trim.py` | `AoWDevEd.exe` |
| Terrain palette — Sky/Chasm brushes + cross-level | ✅ CONFIRMED WORKING (2026-07-24) | `build_deved_terrainpal.py` | `AoWDevEd.exe` |
| Map Validation dialog — clickable entries | ✅ CONFIRMED WORKING (2026-07-28) | `build_validation_goto.py` | `AoWDevEd.exe` |
| Party placer → random army generator + config dialog | ✅ CONFIRMED WORKING (2026-07-28) | `build_party_random.py` + `party_dialog.py` | `AoWDevEd.exe` |
| New map dialog → "New generated map" (Ziggurat Map Generator) | 🔨 APPLIED, UNTESTED (rebuilt 2026-09-06 for the twelfth dial, Hills) — the 2026-09-05 build's **automated click-through drove the whole chain to a loaded map**, §9.5 | `build_deved_newmapgen.py` | `AoWDevEd.exe` |
| Developer > **Delete Unused Heroes** — prunes the hero roster to (placed ∪ leaders) | 🔨 APPLIED, UNTESTED (2026-09-08), §10 | `build_deved_heroprune.py` | `AoWDevEd.exe` |
| Developer > Game Settings **folded into Map Settings as a "Game" tab**; the menu item is hidden | 🔨 APPLIED, UNTESTED (2026-09-12), §11 | `build_deved_gamesettings_tab.py` | `AoWDevEd.exe` |
| Item Properties gains **Hit Points / Movement** spinners (`item+0x4A` / `+0x4B`) | 🔨 APPLIED, UNTESTED (2026-09-13), §12 | `build_deved_itemhpmv.py` | `AoWDevEd.exe` |
| Settings > Abilities / Spells: **UP/DOWN arrows move the list selection** (the `Application.OnMessage` filter no longer confiscates them); `SpellListBoxClick`'s wrong-listbox guard fixed | 🔨 APPLIED, UNTESTED (2026-09-14), §13 | `build_deved_listarrows.py` | `AoWDevEd.exe` |
| Area copy-paste, radius-N discs, 6-way rotation | SPECULATIVE — designed, never built | none | would touch `HSEPack.dpl` |
| Timer autosave | 🛑 REVERTED (2026-07-07 — wrong hook, never fires) | `build_editor_autosave.py` | `AoWDevEd.exe` + `AoWEd.exe` |

**The two editor binaries are separate compiles of the same source**, not a one-byte relationship like `AoWz.exe`/`AoWzCompat.exe`: `AoWDevEd.exe` and `AoWEd.exe` share DFM layout and function shapes but every address shifts by a small, per-function constant (`TMainForm.HSMEditUpdateFrame` sits at `0x428D18` in one and `0x428CA0` in the other; `AoWDevEd.exe`'s `CODE` section is ~332 bytes larger). **Verify every address independently per exe** — never assume one function's delta carries to another. `HSEPack.dpl` (map data + the `THSMEdit`/`THSSEdit` map-view controls) rebases at runtime like every `.dpl`, and is loaded by **both** editors and by the game (`AoWz.exe`/`AoWzCompat.exe`) — patches there are safe only because the touched entry points (`THSMEdit.Load/Save/SaveAs`, `THSMEdit.UpdateFrame`, `TArmyPlaceControl`) are editor-only call paths the game never reaches. **`AoWDevEd.exe` imports the AoWEPACK global `AoWE.AoWHSSet`, so it loads `AoWEPACK.dpl` and locks it too** — closing "the game" is not enough before patching that DLL; kill the editor as well (`_new/CLAUDE.md`'s standing kill-authorisation already covers `AoWDevEd`/`AoWEd` by name).

### Current on-disk layout (verified 2026-09-03) and why "restore a backup" is off the table

```
AoWDevEd.exe: CODE DATA BSS .idata .reloc .rsrc  .dlgd .mtb .ctp .vgo .pty .tres
HSEPack.dpl:  CODE DATA BSS .idata .edata .rdata .reloc .rsrc  .dlgd .rgt
```

Read live from both PE section tables: the six appended `AoWDevEd.exe` sections are in exactly the documented **apply order — dlgdirs → modtoolbar → terrainpal → valgoto → partyrnd → timerres** — each later patch reads whatever the previous one left behind (terrainpal in particular consumes whatever DFM the `TMAINFORM` resource entry currently points at, so it must run after both dlgdirs and modtoolbar). `HSEPack.dpl` carries only `.dlgd` (shared with the exe feature) and `.rgt` (render gate); it has no `.pty`/`.vgo`/`.ctp` — those are exe-only.

**Exactly one `.pre-*` snapshot exists for this family: `Ziggurat\backups\HSEPack.dpl.pre-dlgdirs3`**, minted 2026-09-11 when v3 overwrote v2 (sha256 `736630d9…`, verified to be exactly the v2 install — `.dlgd` VirtualSize `0x520`, no `Release\` string, 607 differing bytes in 32 runs against live, every one inside the cave or the 8 call sites plus that one header field). There is **none** for `AoWDevEd.exe` and none for v1. ⚠ The right check after the 2026-09-09 move is `find Ziggurat -name '*.pre-*'` (currently 7 hits) — **not** `ls -la *.pre-*` in the game root, which these snapshots left when `BACKUP_DIR` moved and which now lists the vanilla install's leftovers instead. Every source doc behind this merge that talks about "layer 5 of 8" or "restore only while it's the newest backup" describes a backup stack that **no longer exists in any form** — not thinner, gone. So the distinction the project always insisted on (surgical `--undo` vs. copying a snapshot) stands for every feature in this file except that one file: each revert below is either the script's own `--undo` (only `build_dlgdirs.py` has one) or a manual byte-level restore; where neither exists, that is stated plainly rather than pointing at a command or a file that isn't there.

| section | VA (`AoWDevEd.exe`, fixed base) / preferred VA (`HSEPack.dpl`) | size (virtual/raw) | feature |
|---|---|---|---|
| `.dlgd` | `0x4E0000` | `0x520`/`0x400` | dlgdirs — 16 hook wrappers, `ensure_ini`, `PATHBUF`. ⚠ v3 left this half **byte-identical to v2** (no `Set` dialog in the exe), so `0x520` here is correct and is *not* evidence of a stale install — check `HSEPack.dpl` for the v3 marker instead |
| `.mtb` | `0x4E1000` | `0x4C63B`/`0x4C800` | modtoolbar — DFM blob (now dead data, §1.4) |
| `.ctp` | `0x52E000` | `0x61400`/`0x61400` | terrainpal — **live** `TMAINFORM` DFM + 2 stub handlers + relocated method table. **Its 4296-byte zero tail is now `build_deved_heroprune.py`'s cave** (§10): VirtualSize was raised `0x61350 → 0x61400`, SizeOfRawData is unchanged and must stay so — `.ctp`'s raw data ends at file `0x18A200`, exactly `.vgo`'s `PointerToRawData` |
| `.vgo` | `0x590000` | `0x16D`/`0x200` | valgoto — install cave + handler |
| `.pty` | `0x591000` | `0xDC6`/`0xE00` | party random — generator, dialog, globals |
| `.tres` | `0x592000` | `0x200`/`0x200` | timerres — `timeBeginPeriod` init cave at `0x592000..0x592075`; **`0x592080..0x5921FF` is `build_deved_levelnav.py`'s cave** (page slack claimed 2026-09-06; VirtualSize raised `0x76 → 0x200`). ⚠ The AoWDevEd section table is FULL — 13 headers end at file `0x400` where CODE begins; every future AoWDevEd cave must take page slack in an existing section |
| `.lvn` | `0x4DF000` (`AoWEd.exe` only) | `0x180`/`0x200` | levelnav — ORDER/RORDER + 4 hook caves; `+0x100` parks the 40 displaced section-header bytes |
| `.dlgd` (HSEPack) | `0x5564E000` | `0x630`/`0x400` | dlgdirs, HSEPack half. v3 (2026-09-11) added `engdir` + `DIRBUF` (StrRec `0x5564E520`, chars `0x5564E528`, `0x108` B), raising VirtualSize `0x520 → 0x630`. **34 of the 0x400 raw bytes are left** — see §2.2 for the 264 bytes that can be freed if another feature needs room here |
| `.rgt` | `0x5564F000` | `0x44`/`0x200` | rendergate — counter/every/skip-sleep tunables |

Live-read confirmations worth recording because they settle several "which value is actually live" questions the source docs leave open: the `.ctp` `TMAINFORM` copy's `FrameRate` byte is `120` (file offset `0x12A1B1`); `g_strength`/`g_racemask`/`g_behavior` in `.pty` read `1`/`0`/`2` — exactly the documented defaults (Medium, no races, Guard), so the config dialog has never been used to change them on this install; the render-gate's `.rgt` state dword reads `every=16`, `skip_sleep=4` — the shipped final tuning, not some earlier sweep value; the exe-side per-frame `Sleep` operand byte at `0x428D40` (inside `TMainForm.HSMEditUpdateFrame`) reads `1` — also the shipped value. All four features are therefore not just "applied" but applied at their documented final settings, right now.

---

## 1. Editor performance — FrameRate, the `Sleep` floor, and the render gate

Three build scripts, applied three weeks apart, that turn out to be one story: a reported "click 30 times and watch them load in" placement lag and a sluggish tab-switch, chased down through two successively deeper floors.

### 1.1 First pass (2026-07-07) — the FrameRate pacing floor

`HSMEdit.FrameRate = 15` is a DFM `vaInt8` baked into the map view at form-create; while the editor is **active**, the DCPACK render loop calls `THSMEdit.UpdateFrame` once per `1000/FrameRate` ms and the message queue is only drained *between* frames — so every click and tab-switch event, regardless of how cheap its own handler is, drains at ≤15/s. Measured with `SendMessageTimeout(WM_NULL)` probes while foreground: a rock-steady **67.0 ± 0.5 ms** per pump. Placement's own mutation handler is cheap (1.4–58 ms; the redraw is what's deferred to later frames) and a tab switch's own work is ~34 ms plus a 17 ms grid repaint — neither is the bottleneck, the *serialization* against a 15 Hz pump is.

**Fix: raise `FrameRate` to 60.** One DFM byte per exe (`0x0F→0x3C` at file offset `0x751A0` in `AoWDevEd.exe`, `0x743E0` in `AoWEd.exe`, both inside `.rsrc` at the time). Verified: pump 67 → ~12–17 ms, tab-switch settle 134 → 62 ms. **✅ User-confirmed** ("it's good") at 60 fps; raised to 120 the same day as a hedge for a second, higher-refresh monitor on the same rig.

**Why not higher, and why the hedge bought nothing.** `FrameRate` 60/120/240 measure an *identical* ~17 ms pump — the DirectDraw loop is vblank-locked to the rig's 60 Hz primary display, so anything above 60 writes a number the vblank wait ignores. The rig's 119 Hz secondary panel was never actually synced to by this DDraw path either, so 120 is inert there too. Left at 120 anyway (harmless) rather than reverted to 60.

**Two other DFM `FrameRate` sites exist and must be left alone**: the Scanner floater's own display (`= 1`) and three other, unrelated displays (`= 20`). Raising the scanner's would make it redraw *more* for no benefit (§1.5).

### 1.2 Second pass (2026-07-28) — the real floor was two `Sleep(1)` calls

Three weeks later the editor was still measurably sluggish: `SendMessageTimeout(WM_NULL)` to a completely idle main window took **31 ms round-trip**. A UI-thread-only sampling profile (`sampler.py --window <hwnd>` — without narrowing to one thread, eight idle worker threads swamp the histogram) found 76% of the thread parked in `ntdll!ZwDelayExecution`. Stack-walking those samples (`stack_prof.py`, new: samples the thread *and* scans the stack at ESP for return addresses inside known AoW modules, because EIP alone can't attribute a kernel wait to its caller) attributed it to **two separate `Sleep(1)` calls per frame**:

| return address (stack_prof) | share of UI thread |
|---|---|
| `HSEPack!HSMEdit.THSMEdit.UpdateFrame+0xe` | 41.9% |
| `AoWDevEd!TMainForm.HSMEditUpdateFrame+0x2e` | 34.2% |
| `GFXEPACK!GFXE.TDIB16Surface.BltDC` (the actual map blit) | 17.3% |

The first two return addresses both sit immediately after a `push 1 / call Sleep` pair (`BltDC` is real, on-CPU blit work, not a sleep) — `HSMEdit.THSMEdit.UpdateFrame @0x55614904` (HSEPack) at `+0x9`; `TMainForm.HSMEditUpdateFrame @0x428D18` (the exe) with its `push`/`call` at `+0x27`/`+0x29` (byte-verified live today: `6A 01` at `0x428D3F`, `E8` at `0x428D41`).

**No AoW module imports `timeBeginPeriod`**, so the process runs at Windows' default 15.625 ms timer granularity and each `Sleep(1)` really sleeps ~15.6 ms — 2 × 15.625 ≈ 31.25 ms, matching the measured 31.0–31.5 ms pump almost exactly. This is *why the FrameRate lever stopped mattering*: `FrameRate` cannot pace the loop below the `Sleep` floor it sits on top of. Proven before writing any patch by injecting `timeBeginPeriod(1)` into the running editor with a remote thread: pump period dropped 31.5 → 8.0 ms instantly, nothing else changed.

**The fix (`build_editor_timerres.py`).** Hook the exe's own kernel32 `Sleep` import thunk at `0x4013C8` (`jmp dword ptr [0x4322A0]`, `ff25a0224300` → `jmp cave` + nop — verified live today: current bytes are `e9 53 0c 19 00 90`) so the cave does a one-time `timeBeginPeriod(1)` init on the first call (a guard flag in its own R/W/X section, `.tres`) and tail-jumps to the real `Sleep` with the caller's stack untouched — no startup hook, and every later call costs one compare. `AoWDevEd.exe` imports neither `LoadLibraryA` nor `GetProcAddress`, so the cave recovers them through **VCL30.dpl's IAT** (the general technique — reusing a *different* import's known delta to reach a whole other module's IAT with no new import — is derived fully in §6.1; here: `vcl_delta = [0x432210] − 0x41336300`, the exe's slot for `Forms.TCustomForm.Create` against its preferred VA in VCL30, then `LoadLibraryA=[0x413E4360+vcl_delta]`, `GetProcAddress=[0x413E43B4+vcl_delta]`). Deliberately **not** derived from winmm's own export RVAs — GFXEPACK imports `timeGetTime`, so winmm's runtime base *is* reachable that way, but baking winmm's export offsets into the patch would turn a Windows servicing update into a crash.

**The catch: an accurate timer makes `Sleep(1)` free-run the loop.** Once real, `Sleep(1)` really is ~1 ms, and the loop blits the whole map ~125×/second for nothing — idle CPU jumped 13.6% → ~55%. The frame budget has to be put back by hand: `--sleep N` patches the tunable operand byte at **`0x428D40`** (the `push` opcode itself sits one byte earlier at `0x428D3F`; the call into `Sleep` follows immediately at `0x428D41`). Shipped default **1**, on the strength of the render gate below absorbing the pacing job instead.

**A tempting-but-wrong optimisation idea, ruled out by measurement: lowering `FrameRate` to save CPU.** `SetFrameRate` (DCPACK `0x55104B08`) writes the published property at `+0x174` **and** the derived frame interval `round(1000/fps)` at `+0x178`, and the loop paces off `+0x178` — an early sweep that wrote only `+0x174` produced a flat, meaningless result for exactly that reason. Swept live, maximised, with the timer-resolution patch already in place:

| `FrameRate` | idle CPU | pump latency |
|---|---|---|
| 120 (then-current) | 27–30% | 14 ms |
| 60 | 42% | 17 ms |
| 30 | 70% | 33 ms |
| 20 | 83% | 50 ms |
| 12 | 88% | 83 ms |
| 150–1000 | 28–33% (flat) | 14 ms (flat) |

**Lower `FrameRate` costs *more* CPU and *more* latency, not less** — turning it down to save CPU is exactly backwards, and above ~120 the knob is inert (`Sleep(8)`, at the time of this sweep, governed instead). This retires the idea that `FrameRate` could ever be used to decouple render rate from pump rate on its own; `build_editor_framerate.py --fps` should only ever raise the value, and §1.1's 120 was already at its useful maximum before this measurement even existed.

### 1.3 Third pass — decoupling render rate from pump rate (`build_editor_rendergate.py`)

With an accurate timer, CPU and latency both trade off a single knob (`latency ≈ Sleep + 6.5 ms`, `CPU ≈ 6.5/(Sleep+6.5)` — the render itself costs a fixed ~6.5 ms and runs on *every* pass) — you can have a fast pump or a cheap CPU, never both, because the loop renders on every iteration. Swept directly (maximised 2180×1210, timer-resolution patch already in place):

| frame `Sleep` | idle CPU | pump latency |
|---|---|---|
| 8 ms (the pre-gate default) | 27.2% | 14.5 ms |
| 12 ms | 22.2% | 18.7 ms |
| 16 ms | 21.2% | 23.0 ms |
| 20 ms | 16.9% | 26.5 ms |
| 25 ms | 15.3% | 32.8 ms |
| 33 ms | 11.6% | 39.9 ms |
| 50 ms | 6.9% | 56.8 ms |

Every point on this curve trades one axis for the other at a fixed ratio; none of them reach anywhere near the eventual shipped state (5.2% CPU / 6.4 ms, below) on either axis alone. **Fix: render only every Nth pass while still pumping every pass**, so CPU depends on the render period and latency depends only on the per-pass sleep — both improve at once.

`HSMEdit.UpdateFrame @0x55614904` (reached only through its VMT slot `THSMEdit+0xAC`; the exe's own `OnUpdateFrame` handler is just an *event*, gating it skips the status bar, not the render) has 7 bytes at `0x55614912` (`cmp byte ptr [esi+0x1bc],0` — the same "map loaded" field `THSMEdit.Save` itself checks, §8's guard table) turned into `jmp cave` + 2 nops (verified live today: current bytes are `e9 f5 a6 03 00 90 90`). The cave counts passes and either re-runs the displaced compare and rejoins the normal render branch at `0x55614919`, or sleeps `skip_sleep` ms and jumps to the function's **epilogue**, `0x55614C2E`.

⚠ **The skip path must target the epilogue, not the function's own early-exit at `0x55614C27`** — that label still runs `call TCustomDisplay.UpdateFrame` (`0x55614C29`), which does the actual present (`GFXE.TDIB16Surface.BltDC → StretchDIBits`). The first attempt jumped to the early-exit and only got CPU from 35% to 22.5%, with `NtGdiStretchDIBitsInternal` still showing 27% in the profile. The tempting-but-wrong reasoning (see §1.5) was "a present with nothing dirty is free" — true on a blank map, not on this path, because the present still runs regardless of dirty state here.

Because that same call also fires `OnUpdateFrame` (and hence the exe's `Sleep`), **the cave itself must sleep on skipped passes or the loop free-runs** at the DLL's `Sleep(1)`. State (a pass counter, `every`, `skip_sleep`) lives in the new R/W/X `.rgt` section — HSEPack rebases, so every reference is `[reg+disp32]` off a call/pop delta and every branch is rel32; `every` is a live-tunable dword the section exposes for `WriteProcessMemory` sweeps with no rebuild.

⚠ **`skip_sleep` below 4 backfires** — at ~500 passes/second the per-pass overhead (prologue + the `Sleep` syscall itself) costs ~25% CPU on its own, independent of rendering. 4 ms is the knee of the curve.

⚠ **The displaced 7 bytes stop one byte short of a `.reloc` entry** at `0x55614920` (the absolute operand of a `mov eax,[0x5562E2F4]` immediately after) — do not widen the hooked range.

**Coupling — revert both or neither.** `exe Sleep=1` is only safe *with* the render gate installed; the gate's `skip_sleep` is what re-paces the loop once the timer is accurate. Reverting `HSEPack.dpl`'s render-gate patch without also restoring the exe's `Sleep` to 8 leaves a hot loop rendering at ~117 fps. Also: with `exe Sleep=1`, render passes come round sooner, so an equivalent render rate needs a *larger* `every` than it did at `Sleep=8` — that's why the shipped default moved from an initial sweep value of 10 up to 16.

**Round 1, maximised 2180×1210, exe `Sleep` still 8** — already better than the Sleep-only curve above on both axes at once:

| `every` | `skip_sleep` | idle CPU | p50 | p95 | ~map fps |
|---|---|---|---|---|---|
| 1 (vanilla) | 8 | 28.7% | 15.0 ms | 16.3 ms | ~70 |
| 2 | 8 | 21.2% | 14.2 ms | 15.6 ms | ~55 |
| 6 | 8 | 11.6% | 10.4 ms | 15.7 ms | ~18 |
| 10 | 4 | 9.7% | 6.4 ms | 16.2 ms | ~22 |
| 16 | 4 | 3.4% | 10.4 ms | 15.2 ms | ~14 |

**p95 is pinned at ~15–16 ms in every row above** — once the gate is doing the pacing, the exe's own `Sleep(8)` no longer paces anything, it only pads the render pass itself, and that pass sets the worst case.

**Round 2 — dropping the exe's `Sleep` to 1 once the gate is installed roughly halves p95**, all samples foreground-validated:

| exe `Sleep` | `every` | `skip` | CPU | p50 | p95 |
|---|---|---|---|---|---|
| 8 | 1 (gate off) | 8 | 29.2% | 14.0 ms | 14.9 ms |
| 8 | 10 | 4 | 7.6% | 6.2 ms | 14.8 ms |
| 1 | 10 | 4 | 9.9% | 6.5 ms | 8.2 ms |
| **1** | **16** | **4** | **5.2%** | **6.4 ms** | **7.6 ms** ← shipped |
| 1 | 24 | 4 | 5.5% | 5.5 ms | 7.3 ms |
| 1 | 24 | 6 | 3.4% | 8.5 ms | 9.1 ms |
| 1 | 30 | 8 | 3.4% | 10.4 ms | 11.0 ms |

Shipped default (exe `Sleep=1`, `every=16`, `skip_sleep=4`) is **5.6× less CPU, 2.2× better median latency, 2× better p95** than untouched vanilla, verified still animating (8/8 distinct frames sampled over 2 s at every tested `every`) and the toolbar → modal-dialog path still works under the gate. Push to `--every 24 --skip-sleep 6` for 3.4% CPU if choppier water is acceptable.

⚠ **Keystone gotcha found here** (distinct from the `push` imm8 trap in `12-re-toolchain.md` §5.2): `add eax, <const> − Label` parses as a **memory operand** (`add eax, dword ptr [...]`) in keystone's Intel-mode LLVM parser, silently producing a pointer read instead of an arithmetic adjustment. Compute call/pop deltas in Python and emit a literal; assert the cave's `push/push/call` prologue shape so the delta stays valid.

Both patches await extended real-editing use — no crash, no visual break, and the map keeps animating in every automated check, but neither has the user's own sign-off (§ Open items).

### 1.4 Why `FrameRate` is now dead weight for `AoWDevEd.exe`

`build_editor_framerate.py` patches a hard-coded `.rsrc` file offset for the `TMAINFORM` DFM. `build_editor_toolbar.py` (2026-07-09) and `build_deved_terrainpal.py` (2026-07-24) each **repoint the `TMAINFORM` resource entry** to a rebuilt copy of the DFM in a new section (`.rsrc → .mtb → .ctp`, in that order — see the layout table above), leaving every earlier copy as dead data *for that one resource entry only*. **Re-running `build_editor_framerate.py` against `AoWDevEd.exe` today edits bytes nothing reads.** Live-verified: the `.rsrc` copy (`0x751A0`) and the `.mtb` copy (`0xDCCBD`) both still read `120`, but so does the one place that matters, `.ctp` (`0x12A1B1`) — a coincidence of when each relocation happened to occur, not something a future retune should rely on. **`AoWEd.exe` never received modtoolbar or terrainpal, so its own `.rsrc` copy (`0x743E0`) is still the live one** — the two exes are no longer symmetric with respect to this script, despite the script itself treating them identically.

This is also now moot regardless of which copy is live: §1.2 established that `FrameRate` cannot pace the loop below the `Sleep` floor, so raising it further — even into the copy that matters — buys nothing on `AoWDevEd.exe` any more. It remains the whole story for `AoWEd.exe`, which never got the timer-resolution or render-gate patches.

### 1.5 Bug sweep — considered, not patched

Four candidate bugs were investigated alongside the two profiling passes and deliberately left alone:

- **`TheMapMapChanged` region width `x2−x1`** (exe `0x4213B2`) — looked like an off-by-one, is not: standard Delphi *exclusive* `TRect` (`Right`/`Bottom` one-past-the-end) makes `x2−x1` the correct width, matching every other `DrawMap` call site.
- **`TScanner.Draw` surface-recreate compares width only** (`0x597039DF`) — real (a height-only viewport resize keeps a stale minimap surface until the next width change) but low-value and in a shared DLL (`AoWTools.dpl`, imported by the game too) for a floater that self-corrects on the next width change.
- **`EngineP.ValidateResourceID`** (`0x5551B134`) — an O(M·N) linear `FindResource` scan per resource during palette-grid activation; runs once per map-open, not per tab, so felt impact is low. Shared `EngineP.dpl`.
- **`TECustomResourceGrid.SetResource`** (`0x5551FBB8`) — a *possible* use-after-free overwriting an occupied grid slot (in-place virtual-destruct while another list may still hold the pointer). **Genuinely unproven and unpatched** — reachability/aliasing was never demonstrated, and it's shared `EngineP.dpl` (see Open items).

None of the four justified a risky patch to a DLL the game also loads for a cost nobody had actually measured as significant.

### 1.6 Measurement traps banked here

- **Foreground self-throttle.** The render loop idles at ~1–3% CPU / ~31 ms latency whenever `AoWDevEd.exe` is **not** the foreground window, regardless of any tuning — an entire sweep once silently drifted into the background and reported beautiful, meaningless flat numbers. Validate `GetWindowThreadProcessId(GetForegroundWindow())` per sample and discard non-foreground ones. **This cannot be fixed from the harness**: Windows' foreground lock defeats `SetForegroundWindow` (even with `AttachThreadInput`) *and* `SwitchToThisWindow` from a background script — relaunching the editor (a fresh process gets foreground rights) and running the whole sweep in that one session is the only reliable route.
- **The dirty-rect pipeline is not the problem — tested, don't re-derive.** A blank 48×48 map fills the same viewport as a populated one for **0.6%** CPU vs. 9.7% (ocean) / 12.8% (dense land); with nothing animating, no blit rects get registered and the present blits nothing. It only *looks* like a blind full-screen repaint because on a populated map nearly every visible hex has something animating (water shimmer, city flags, unit idles), so the dirty region genuinely is the whole view, every frame. `TCustomDisplay.UpdateFrame`'s only visible guard is a null test — tempting to blame, and wrong; the real gating is deeper, in the virtual present the registered-rect list drives.
- **Timer resolution is per-process on Win10 2004+.** `NtQueryTimerResolution` reported 1.000 ms system-wide (another app had already raised it) while the editor itself was still measured at 15.6 ms — the system-wide number tells you nothing about one target process, and calling `timeBeginPeriod` from *your own* diagnostic process does nothing to speed up the editor. Test by injecting into the target.
- **`PrintWindow` repaints synchronously** into the caller's DC — it cannot show what's actually on screen or when it got there. An early "paint progress" measurement built on it reported a bogus ~800 ms that was pure instrument overhead.
- Tight cross-process polling (`GetWindowTextW`/`EnumChildWindows` in a loop) perturbs the very message pump being measured; use fixed-delay snapshots and diff afterwards.

**If more is ever wanted.** The remaining floor is the ~4 ms software blit itself (`GFXE.TDIB16Surface.BltDC → StretchDIBits`) of whatever is dirty — on a real map, essentially the whole viewport, every frame that renders at all (§1.6). That work is legitimate, not waste, so the only levers left are making the blit cheaper or shrinking the view. `DCPACK.dpl` ships both a `TDDrawDC` (DirectDraw) path and the `TWindows16DC`/software-DIB path this editor actually uses — moving the windowed map view onto DirectDraw is the plausible next big win, and a considerably larger change than anything else in this section.

### 1.7 Tooling added during this investigation, reusable beyond it

- `aowsyms.py` — symbol resolution for any AoW module (`.dpl` exports, or an exe's VMT scan + published method tables).
- `dasm.py` — annotated capstone disassembler for **any** module (resolves cross-DLL import thunks, IAT slots, shortstrings; `dasm.py <mod> sym <substring>` too) — supersedes an earlier AoW.exe-only dumper for package work.
- `xref.py` — rel32 call/jmp + absolute-dword cross-reference scanner, hits labelled by enclosing symbol.
- `mtab.py` — published-method-table dumper (event-handler name → code VA) for exe classes.
- `sampler.py` — Wow64 sampling profiler (suspend / `GetThreadContext` / EIP histogram, symbolised); `--window <hwnd>` narrows to one thread, essential once other threads are present.
- `stack_prof.py` — the same sampling, but also scans the stack at ESP for return addresses inside known AoW modules, so a kernel wait (`Sleep`, a wait object) can be attributed to its *caller* rather than showing up as an opaque `ntdll`/`win32u` frame.
- UI automation, useful again for any future editor-hook feature: `winspy.py` (window tree), `clicker.py` (posts clicks/tabs/keys), `menucmd.py` (menu tree + `WM_COMMAND`), `grabwin.py` (`PrintWindow` capture of occluded windows — see the caveat above), `topmost.py`.
- Empirical Delphi 3 VMT layout note (used throughout this file): self-ptr `−0x40`, method table `−0x28`, field table `−0x2C`, class name `−0x20`, instance size `−0x1C`, parent `−0x18`.

---

## 2. Per-dialog-type directory memory (`build_dlgdirs.py`)

Every file dialog in the editor (map Open/SaveAs, mapset Open/SaveAs, text import/export) shared one Windows per-application MRU folder, because none of them seeded `FileName`/`InitialDir`. Scenario maps and mapsets live in different directory trees, so this meant constant re-navigation. **Fix: each dialog *type* remembers its own path**, persisted in `<game dir>\AoWEd_LastDirs.ini`, section `[LastDirs]`, keys `Map` / `Set` / `Text`. For `Map`/`Text` a missing key is exactly vanilla behaviour; since v3 a missing `Set` key seeds the engine's own data root instead of the MRU (§2.2). The INI builds up only as dialogs are accepted.

16 hook sites, all `call <import-thunk>` → `call <cave-wrapper>` (5 bytes, 1:1, the wrapper calls the original thunk itself):

| module | role | site → dialog type |
|---|---|---|
| `AoWDevEd.exe` (seed, `Create` thunk `0x4019C8`) | before `Execute`: set `FFileName`(+0x6C)/`FInitialDir`(+0x60) | `0x429840` OpenBtnClick=Map, `0x42B9AC` ImportText=Text, `0x42B8AC` ExportText=Text, `0x42D436` ExportAbilityInfo=Text |
| `AoWDevEd.exe` (persist, `GetFileName` thunk `0x4019D0`) | after a successful pick, write back | `0x429899`, `0x42B9DF`, `0x42B8EC`, `0x42D488` (same order) |
| `HSEPack.dpl` (seed, `Create` thunk `0x55601A54`) | same, editor-only entry points | `0x55615267` `THSMEdit.Load`=Map, `0x55615E96` `THSSEdit.Load`=Set |
| `HSEPack.dpl` (dirseed, `SetInitialDir` thunk `0x55601A64`) | reroute `SetInitialDir(GetCurrentDir)` to the remembered folder | `0x55614D7E` `THSMEdit.SaveAs`=Map, `0x55615C5A` `THSSEdit.SaveAs`=Set |
| `HSEPack.dpl` (persist, `GetFileName` thunk `0x55601A5C`) | write back | `0x556152BD`, `0x55614E65`, `0x55615EE5`, `0x55615C8E` |

**`Ziggurat\HSEPack.dpl` is also loaded by `AoWz.exe`/`AoWzCompat.exe`/`AoWzEd.exe`, but the patched functions (`THS?Edit.Load/SaveAs`) are editor-only entry points the game never calls** — an import-table scan settles it: only `AoWDevEd.exe` and `AoWzEd.exe` import `HSSEdit.THSSEdit.Load`/`.SaveAs` at all, while `AoWz.exe`, `AoWzCompat.exe` and every `.dpl` import zero `THS?Edit` symbols. The cave carries no absolute exe addresses, so riding along in the game is inert.

⚠ **`AoWEd.exe` does *not* get its map/mapset dialogs fixed for free.** It exists only at the game **root**, has 6 sections and no `.dlgd`, and it loads the **root's vanilla** `HSEPack.dpl` — it gets nothing. (The earlier claim here dates from when the exes lived at the root and shared one DLL; the 2026-09-09 move invalidated it.)

⚠⚠ **`build_dlgdirs.py` maintains `AoWDevEd.exe`, which is the patch *source*; the editor the owner runs is `Ziggurat\AoWzEd.exe`, copied from it and re-skinned by `build_zigeditor.py`.** So the exe half of this feature exists in three copies — `<root>\AoWDevEd.exe` (byte-identical to the Ziggurat one), `Ziggurat\AoWDevEd.exe`, `Ziggurat\AoWzEd.exe` — and the script maintains one. ⚠ `AoWzEd.exe` is **not** a byte copy: measured 2026-09-11, 4396 bytes differ in 1224 runs, every one inside `.rsrc` (the purple-dragon icon), while `.dlgd` raw `0xDC200..0xDC600` and all 8 hook sites are equal. Verify the live editor by comparing the cave region and the sites, never by hashing the file. Run `build_zigeditor.py --apply` after any `build_dlgdirs.py --apply`/`--undo` that changes an exe byte — four sibling editor scripts (`build_editor_autosave.py`, `build_editor_spinners.py`, `build_deved_levelnav.py`, `build_editor_framerate.py`) open their docstrings with exactly that two-step; `build_dlgdirs.py` never did, which is why it is called out here. Specifically `--undo` restores the 8 sites in `AoWDevEd.exe` and leaves the 8 in `AoWzEd.exe` pointing into a cave that is still present but inert. **v3 is unaffected — it changed no exe byte at all.**

When a map/set already has a full path (loaded from disk), the VCL's own `lpstrFile` wins over `InitialDir` regardless — so Save-As on an already-open file still opens at that file's own folder; the dirseed reroute matters only for a brand-new, never-saved document.

### 2.1 The profile-path leak — v1 baked it, v2 derives it at runtime

**v1 stored the *build machine's* absolute INI path as a literal baked into the cave** (`INI_PATH = GAME + r"\AoWEd_LastDirs.ini"`, computed once at build time and written verbatim into the blob). That put a real username into two shipped binaries, `HSEPack.dpl` and `AoWDevEd.exe` — undetected for a stretch, because both are binaries living **outside** `Modding Resources/`, exactly where the project's own folder-grep privacy check never looks. A third-party modder independently hit and diagnosed the identical defect in his own copy before this project caught it in its own.

**v2 derives the path at runtime instead**: `GetModuleFileNameA(NULL, PATHBUF, 0x104)` → back-scan to the last `\` → append the literal leaf `AoWEd_LastDirs.ini`. `hModule=NULL` is deliberate — it returns the *host process's own* image path, and all four hosts (`AoW`/`AoWCompat`/`AoWDevEd`/`AoWEd`) live in the game directory; `HSEPack.dpl` doesn't import `GetModuleHandleA` at all, so `NULL` is also the only option available to it. **Both modules already import `GetModuleFileNameA` natively from kernel32, with a ready-made Delphi thunk** (`HSEPack.dpl` `0x556011D8`, `AoWDevEd.exe` `0x00401158`) — deriving the path costs one `call rel32` to an existing thunk, no VCL30-delta hop, no import-table surgery. The result caches in `PATHBUF`; the loader zero-fills virtual bytes past `SizeOfRawData`, so the buffer's own first byte doubles as a "not yet built" flag with no separate init hook needed.

This is a **correctness** fix as much as a privacy one: a baked absolute path works on exactly one install and then fails *silently* on every other one, because the profile APIs resolve a directory-less filename against `%WINDIR%` — reads come back empty, writes land in `C:\Windows` or vanish into UAC virtualisation. (Two tempting alternatives that share that same silent-failure shape are in Failed approaches, below.)

**Cave placement and page slack.** `.dlgd` is **not** the last section in either module any more (`.rgt`/`.mtb` etc. follow it) — so `SizeOfRawData` stays fixed at `0x400` and the file layout of every later section is preserved; `PATHBUF` (0x108 bytes, doubling as a Delphi 3 static AnsiString: `[buf−8]`=refcount −1, `[buf−4]`=length) lives in the section's **page slack** at `cave+0x400`, and the only PE header field the script edits on a rewrite is `.dlgd`'s `VirtualSize` (`0x400 → 0x520` for v2, and `→ 0x630` in HSEPack.dpl once v3 claims `DIRBUF` as well, §2.2). v1's baked-literal design needed no slack region at all, so **a `VirtualSize` above `0x400` is itself proof the install is not v1** — but read the two modules separately: live today `HSEPack.dpl` is `0x630`/`0x400` (v3) and `AoWDevEd.exe` is `0x520`/`0x400`, and the exe's `0x520` is **correct, not stale** — v3 changed no exe byte.

**Reaching kernel32's profile APIs from a module that doesn't import them.** Neither module imports `Get/WritePrivateProfileStringA`; both import `VCL30.dpl!Dialogs.TOpenDialog.Create` (needed for the dialogs themselves), and VCL30's own IniFiles unit pulls in the profile APIs — so the same general technique as `build_editor_timerres.py` (§1.2) and `build_party_random.py` (§6.1) recovers them: `vcl_delta = [own IAT slot for TOpenDialog.Create] − 0x4137AFB0` (Create's preferred VA in VCL30), then `GetPrivateProfileStringA=[0x413E43B8+vcl_delta]`, `WritePrivateProfileStringA=[0x413E42F8+vcl_delta]`. Own IAT slots: `AoWDevEd.exe 0x432598`, `HSEPack.dpl 0x556308DC`.

`HSEPack.dpl` rebases, so every data reference in its half of the cave is `[reg+disp32]` corrected by a call/pop module-delta helper, and every call is rel32 — no `.reloc` entries needed (and `.dlgd` has none, which matters, since `.reloc` cannot be extended in place). In the exe the identical code runs with delta = 0.

⚠ **`ensure_ini` is not thread-safe** (a second thread reading the "not built" flag mid-`rep movsb` would see a half-built path) — left unguarded deliberately: every call site is main-UI-thread modal-dialog code, and the failure mode is benign (the profile API rejects a malformed path → vanilla behaviour).

**String handoff and register discipline.** `System.@LStrAsg` copies rather than aliases whenever the source string's refcount is negative (verified directly in the VCL30 disassembly), so handing the INI buffer's doubled-up AnsiString into `FFileName`/`FInitialDir` is safe, and `SetInitialDir` copies too — nothing has to track the buffer's lifetime afterwards. Delphi's register convention makes `eax`/`ecx`/`edx` caller-saved and `ebx`/`esi`/`edi` callee-saved; the caves push/pop `ebx`/`esi`/`edi` and rely only on `eax` surviving across the original thunk calls. ⚠ `ecx` holds `&key` and is **live** across all three `ensure_ini` call sites, and `edx` holds the picked AnsiString at the save-common site — so `ensure_ini` itself saves and restores `ecx`/`edx`/`esi`/`edi` and returns a result only in `eax`, rather than assuming the more usual "only `eax`/`ecx`/`edx` are volatile" convention holds for its own callers.

**The hook shape**, identical at all 16 sites (`AoWDevEd.exe`'s `0x429840`, taken as the example): a 5-byte `call` to an import thunk is repointed to the cave wrapper, which performs the seed/persist/dirseed work and then makes the *original* call itself, so the dialog's own construction is untouched either side of the patch:

```
orig:  E8 xx xx xx xx        ; call [TOpenDialog.Create thunk 0x4019C8]
new:   E8 yy yy yy yy        ; call cave_seed_map   (cave: seed FFileName/FInitialDir,
                             ;   then `call [0x4019C8]` itself, then ret)
```

**Live-tested (v1's automated pass, 2026-07-09), driven via clicker/menucmd with screenshots captured:**

1. Open Mapset → picked `Release\Release.hss` → INI got `Set=…Release.hss`.
2. File>Open (map) → picked `1Scenario\…\111MPv1.hsm` → INI got `Map=…111MPv1.hsm`, `Set` untouched — the two memories are genuinely independent.
3. Reopen Open Mapset → dialog preselected `Release.hss` in `Release\` (the seed cave), not the map folder.
4. Save As with a mapset loaded → dialog opened cleanly (no crash), `Release.hss` preselected.

**⚠ This pass covers v1's baked-path cave only.** v2 replaced the INI-path derivation on the critical path of all 16 hooks and has never itself been executed — see Open items.

### 2.2 v3 — the `Set` dialogs fall back to the engine's data root, not the Windows MRU

🔨 APPLIED, UNTESTED (2026-09-11). `HSEPack.dpl` only; `AoWDevEd.exe`'s half of the cave is byte-identical to v2 and was not rewritten (verified: its SHA-256 is unchanged across `--apply`).

**Why the `Set` key is not just another remembered folder.** The editor writes every `.PFS` to `ExtractFilePath(engine[+0x44])`, and `engine[+0x44]` is set by `HSEngine.THSEngine.LoadHSS @0x5560F75C+0x2F` (and `SaveHSS @0x5560F970+0x71`) to `SysUtils.ExpandFileName(<the .hss the user picked>)`. So **whichever mapset the Set dialog opens decides where `Ability.pfs` and its ten siblings are saved** — `AoWE.TAoWHSSet.ReadWrite @0x5574C528+0x86` is the consumer, the write itself is `Engine.TEngine.WriteToFileCRC @0x5574C88F`. On 2026-09-10 `<root>\Release\Release.hss` — the **vanilla** tree's mapset — was opened in `Ziggurat\AoWzEd.exe` and an ability edit landed in `<root>\Release\`, not `Ziggurat\Release\`. The route in was the *no-INI* fallback: with no remembered `Set` path the dialog fell through to the Windows per-application folder MRU, which had the vanilla tree in it. Hand-fixing the INI repairs one install; the trap re-arms on a fresh install or any time `AoWEd_LastDirs.ini` is deleted.

**The fix.** With no `Set` value in the INI, both Set dialogs seed `FInitialDir := <engine data root> + "Release\"` — `<game>\Ziggurat\Release\` under the registry isolation. An INI value still wins; v3 replaces only the fallback.

**Reaching the data root from a rebasing HSEPack cave.** Not through AoWEPACK's `AoWE.AoWEngine @0x558FA048`: **`HSEPack.dpl` imports nothing at all from `AoWEPACK.dpl`** (checked — zero descriptors), so the VCL30-IAT-delta idiom of §2.1/§6.1 has no anchor there, and AoWEPACK rebases too. The engine comes off the instance the hook already holds:

| step | fact |
|---|---|
| `edi` = `THSSEdit` `Self` at **both** Set hook sites | `THSSEdit.Load @0x55615E64+0x11` and `THSSEdit.SaveAs @0x55615BF8+0x08` both do `mov edi,eax`, and neither the seed nor the dirseed wrapper overwrites `edi` before `engdir` runs |
| `[edi+0x24]` = the engine | written only by `THSSEdit.SetHSEngine @0x55615AC8`, which hands it straight to `EngineP.dpl!Engine.TEUser.Connect` — so it is always a `TEngine` descendant. Both hosts null-check it before the hook fires (`Load 0x55615E87`, `SaveAs 0x55615C12`) |
| `[engine+0x2C]` = the data root | `Engine.TEngine.FStartupDirectory`, an AnsiString. Declared **three classes above `TAoWEngine`**: `TEObject → TECustomNode → TENode → TEngine` (EngineP.dpl; `SetStartupDirectory @0x5551B658` does `lea eax,[ebx+0x2c]; @LStrAsg`) `→ THSEngine` (instsize `0x58`, HSEPack) `→ TAoWEngine` (instsize `0x80`, AoWEPACK, parent slot `0x558FC144` → `HSEPack!HSEngine..THSEngine`). **+0x2C is therefore valid on any engine in any host**, not a TAoWEngine-only field |
| trailing `\` | guaranteed twice over — `TAoWEngine.UpdateStartupDirectory @0x557982D0` appends one when the registry value lacks it, and the base `TEngine.UpdateStartupDirectory @0x5551B5F4` assigns `ExtractFilePath(Application.ExeName)`, which keeps the delimiter. `engdir` verifies it anyway and returns 0 (→ vanilla) if absent |

⚠ **`Map` must not reuse any of this.** `THSMEdit` is an unrelated class (parent `DisplayC.TDisplay`, instsize `0x270`, its own `SetHSEngine @0x55613CD0`), so `[edi+0x24]` there is **not** an engine. The fallback is gated on the module's `engfb` entry *and* on the key name.

**`engdir` @`0x5564E07D`** (82 B): engine → `FStartupDirectory` → length from `[str-4]` → reject nil/empty/no-trailing-`\`/over-255 → `rep movsb` the root then `"Release\"+NUL` into `DIRBUF`, writing `StrRec.refcount = -1` and `StrRec.length` itself first. Returns `&DIRBUF` in `eax`, or 0. Clobbers `eax`/`ecx`/`edx` only. Every operand is `[ebx+disp32]` or register-relative — 0 `.reloc` fixups anywhere in `.dlgd`'s page, confirmed live.

**How it hangs off the existing wrappers — no `*_common` body changed.**
- `seed_Set` (hook `0x55615E96`): after `mov ebx,<delta>`, `call engdir`; on success assign straight into `FInitialDir` (+0x60). `seed_common` then runs untouched, so an INI hit overwrites both `FFileName` and `FInitialDir` and the INI still wins.
- `dirseed_Set` (hook `0x55615C5A`): the wrapper already pushes the original `GetCurrentDir` string for `dirseed_orig` to pop into `edx`. On success `engdir`'s result is stored over that stack slot (`mov [esp],eax`), so the CWD fallback becomes the data root; the INI-hit path discards the slot as before. Nothing is refcounted either way — the caller still owns and clears its `GetCurrentDir` string, and `@LStrAsg`/`SetInitialDir` copy out of `DIRBUF` because its refcount is negative. (SaveAs also copies `engine[+0x44]` into `FFileName` at `0x55615C6C`, which wins whenever a mapset is already open; this fallback is what you get when one is not.)

⚠⚠ **`engdir` may NOT build into the shared profile `buf`.** `dirseed_common` overwrites `buf` with the `GetPrivateProfileStringA` read *before* `dirseed_orig` consumes the pushed pointer. On a miss the default is `""`, so `buf` would hold a NUL at [0] while the AnsiString length field still carried the old directory length — `SetInitialDir` would receive a run of NULs and silently do nothing. Hence `DIRBUF` with its own StrRec. (The seed path alone *could* have shared `buf`, since `@LStrAsg` copies immediately; one buffer for both is simpler and costs only page slack.)

**Storage.** `DIRBUF` is in `.dlgd`'s page slack at `cave+0x520` (StrRec `0x5564E520`, chars `0x5564E528`, `0x108` B), VirtualSize `0x520 → 0x630`; `.rgt` starts at RVA `0x4F000`, so the full `0x1000` of virtual space is ours and `process()` asserts the new size cannot reach the next section. `SizeOfRawData` stays `0x400` and the file length is unchanged (`0x48800`). Unlike `PATHBUF`, `DIRBUF` does **not** lean on the loader's zero-fill as an init flag.

**State machine.** `classify()` now recognises `v3` (what `--apply` writes), `v2` and `v1`, and `--apply` accepts and overwrites any of them in place; all 8 HSEPack sites are repointed because inserting `engdir` shifted every wrapper entry (`seed_Set 0x5564E095 → 0x5564E0E7`, `dirseed_Set 0x5564E1AD → 0x5564E212`, etc.). A module whose cave is unchanged reports `v3` and `--apply` is a no-op, which is why `AoWDevEd.exe` needs no rewrite. Snapshot over a proven-v2 install: `Ziggurat\backups\HSEPack.dpl.pre-dlgdirs3`.

⚠⚠ **Every `engdir` failure path falls back into the trap this closes.** The cave's own `-> exact vanilla` comments are accurate and misleading at once: vanilla here *is* the Windows per-application folder MRU, the thing that steered the 2026-09-10 edit into `<root>\Release\`. Failing open is still right — failing closed would mean refusing to open the dialog — but it means a silent partial failure is indistinguishable from no patch at all. The paths:

- engine or `FStartupDirectory` nil/empty, or no trailing `\`.
- **data root ≥ 256 characters.** `maxroot = DIRBUF_CHARS − len("Release\")−1 = 255`, so `cmp ecx,0xFF / ja` rejects 256+. Unreachable in practice rather than by construction — a 256-char root makes `<root>Release\Ability.pfs` exceed `MAX_PATH`, so the editor could not write there anyway. To close it by construction, raise `DIRBUF_CHARS` `0x108 → 0x110` (page slack is free) — ⚠ but that changes the cave, so `classify()` must first keep the current v3 bytes as a recognised generation or `--apply` will report `unknown` against the live install and abort.
- **`<data root>\Release\` does not exist** — Win32 ignores a non-existent `lpstrInitialDir` outright and the dialog falls back to the MRU. Nothing in the cave can detect this. It is the clearest reason a clean static pass here is not a behaviour pass.

**Verified without the game:** fresh-install (`absent`) apply on a pristine vanilla `HSEPack.dpl`; apply over the live v2; `--undo`; re-apply from `undone` reproducing the first v3 write byte-for-byte; re-apply over v3 a no-op; file length and `SizeOfImage` unchanged; all 8 site bytes and their rel32 targets; zero `.reloc` fixups in `.dlgd`; the cave's only strings are `LastDirs`, `AoWEd_LastDirs.ini`, `Release\` — no absolute path, no username, in either tree's binaries. Adversarial QA pass 2026-09-11 additionally confirmed, against the live bytes: `@LStrAsg @0x41304780` takes its `@NewAnsiString`+`System.Move` **deep-copy** branch for a negative refcount (`mov ecx,[edx-8] / inc ecx / jg skip`) and `SetInitialDir @0x4137B6D8` ends in `@LStrCopy`, so neither touches `DIRBUF`'s refcount — no leak, no double free, and the discarded `GetCurrentDir` string stays owned by `SaveAs`'s `[ebp-4]` and is freed by `@LStrClr` at `0x55615CC9`; `TOpenDialog.Create @0x4137AFB0` and `GetFileName @0x4137B660` take no stack arguments and never write `edi`; and a resync-on-failure sweep of the whole `HSSEdit` unit (`0x556157C4..0x55616380`, 1315 instructions) finds **exactly one** writer of `[reg+0x24]` — `SetHSEngine @0x55615ACA`. ⭐ The strongest evidence for the `edi` assumption is vanilla's own codegen: `SaveAs` does `call TOpenDialog.Create` at `0x55615C39` and then `mov edx,[edi+0x24]` at `0x55615C6F`, so the Delphi compiler itself relies on `Self` surviving in `edi` across that call.

**Room left:** 34 of the 0x400 raw bytes. `SizeOfRawData` cannot grow (`.rgt`'s raw data starts at file `0x048600`), so the next feature wanting code here must free some. The obvious 264 bytes: the profile read buffer `buf` is runtime-only scratch and could move to page slack exactly as `DIRBUF` did, leaving just its 8-byte StrRec. ⚠ That changes the data layout, so `classify()`'s v1 probe — which reads `pathstr` at a fixed offset out of the installed bytes — must be re-checked in the same pass.

---

## 3. Menu options as toolbar rows + start maximized (`build_editor_toolbar.py`, trimmed by `build_deved_toolbar_trim.py`)

Requested for a 4K screen where the editor's tiny 916×696 centred window and menu-buried dialogs are painful. Injects an always-visible, captioned toolbar row under the existing icon toolbar, exposing menu sub-options as flat `TSpeedButton`s, grouped and **underlined-label**-headed by its parent menu. Current live layout — one row, `MBRowA` (`Top=50`, `H=31`), content width ~560 px:

- `File |` New Open Save "Save As" · `Developer |` "Open Mapset" "Fog of War" · `Help |` About

Also sets `WindowState=wsMaximized` (`--no-maximize` to skip) and adds a `ShortCut=16467` (Ctrl+S) to the `SaveItem` menu item, which had none — `KeyPreview=True` on the form routes it to `SaveBtnClick` from anywhere. Deliberately skipped: `File>Close`/`Exit` (misclick risk — Close was in fact *removed* from the toolbar for the same reason), the runtime-built per-map Players menu, and the toggle buttons' check-mark *state* (a button fires the real handler; the check mark still shows correctly in the menu, which stays fully functional alongside the toolbar).

**User-requested revision (2026-07-09-b), already folded into the description above, worth keeping for the DFM-splicing lesson it left behind.** Three edits landed in one pass: the `Close` button was dropped from the File group; every category label got an explicit underlined copy of the form font (`Font.Style=[fsUnderline]`, `ParentFont=False`) so they read as section headers rather than more buttons; and the Ctrl+S shortcut was added to `SaveItem`. **The build script locates `SaveItem` via a recursive DFM node search and splices the new property in — but because the menu resource streams *after* the toolbar panels in the same DFM, the three insert points must be spliced highest-offset-first** (`SaveItem` → the panel's own tail → the DFM root), or each earlier splice invalidates the byte offsets the later ones were computed against. Generalises to any DFM edit touching more than one insertion point in the same resource.

**Mechanism: a pure DFM resource edit, zero new code.** DFM event handlers resolve **by name** against the form's published method table at load time, so a brand-new `TSpeedButton`/`TLabel`/`TPanel` — all already in `TMainForm`'s streaming class table — can be wired to an *existing* handler (`OnClick=OpenBtnClick`, etc.) with nothing recompiled. All 32 referenced handler names were verified present in the published method table before building; each either self-guards (checked in disassembly) or is exactly as reachable as its always-enabled menu item already is.

The enlarged DFM (`0x4AFD5 → 0x4C393` bytes) can't fit back in `.rsrc`, so it's appended as a new section `.mtb` and the `TMAINFORM` resource's `IMAGE_RESOURCE_DATA_ENTRY` (found by walking `.rsrc`) is repointed at it; the original blob stays in `.rsrc`, now dead for this one resource entry (§1.4). The panel is `alTop` at `Top=50` so the VCL stacks it under the vanilla icon toolbar (`Panel2`, `Top=0`); the main content panel is `alClient` and reflows itself.

**Live-tested (automated, 2026-07-09):** launches maximized, the rows render with correct captions; About/Open-Mapset buttons open their real dialogs; a synthesized Ctrl+S ran the Save path without fault. `TSpeedButton` has no HWND (`TGraphicControl`) — it receives mouse input via its parent panel's `WM_MOUSE*`, dispatched by coordinate, so automation posts to the *panel*, not the button.

### Trim (2026-09-06, `build_deved_toolbar_trim.py`) — 🔨 APPLIED, UNTESTED

User ruling: nearly all of the injected buttons went unused. Three labels (Edit, Options, Preview) and 24 buttons (`MBCut MBCopy MBPaste MBDelete`, `MBMapSettings MBPlayerInfo MBScanner MBRemLevel MBAddLevel`, `MBPrev640 MBPrev800 MBPrev1024 MBPrev1280`, `MBNewCombat MBNewMapset MBGameSettings MBMapsetSettings MBEditMapText MBExportText MBImportText MBMultilizer MBDebugMode MBExportAbil MBRemLeaders`) were deleted; the five row-B survivors (`MBLabMBRowBDeveloper`, `MBOpenMapset`, `MBFogOfWar`, `MBLabMBRowBHelp`, `MBAbout`) were **moved into `MBRowA`** and the `MBRowB` panel deleted outright, so the map view starts 31 px higher. Every survivor's `Left` is recomputed with `build_editor_toolbar.py`'s own constants (`CHAR_W=6`, `GROUP_GAP=22`, `BTN_GAP=2`, `LAB_TOP=9`, `BTN_TOP=4`), giving 6/40/76/116/156 · 236/300/382 · 480/514. Component names are unchanged, so `MBRowA` still serves as `build_editor_toolbar.py`'s marker.

**Mechanism: an in-place shrink of the live `.ctp` DFM.** `0x6065C → 0x5F644` bytes (−4120), written back at the same file offset `0x129AF4`, the freed tail zero-filled, and only the resource data entry's **`Size`** field updated (`OffsetToData` and every section header left alone — the AoWDevEd section table is full, §"Current on-disk layout"). The DFM ends exactly at `.ctp`'s virtual end, so the zeroed tail overlaps nothing. `build_trimmed()` is state-agnostic — fed the two-row blob it deletes, fed its own output it is byte-identical — so **re-tuning the spacing is an `--apply` in place, never a revert-and-reapply.**

`--undo` is real *in design*: the untrimmed blob is snapshotted to `<game dir>\backups\AoWDevEd.TMAINFORM.pre-toolbartrim.dfm` (0x6065C bytes), and only from a blob positively proved untrimmed (`MBRowB` present *and* all 27 deleted names present) — never from the script's own output. Round-trip verified bit-exact: `--undo` returns the exe to sha256 `082e28e7…`, `--apply` back to `9715097a…`, file length unchanged at 1 647 104 bytes both ways.

⚠⚠ **But that snapshot does not currently exist**, so `--undo` has nothing to restore from today. It lived in `<root>/backups/`, deleted 2026-09-10; `BACKUP_DIR` now resolves to `Ziggurat/backups/`, which is created on demand and is empty. The design above is sound and the round trip was really measured — it simply cannot be exercised until a fresh `--apply` mints the blob again. This feature is one of the ones whose revert is genuinely snapshot-based rather than surgical, so the loss is real here in a way it is not for a script with a byte-level `--undo`.

⚠ **Forward hazard: re-running `build_deved_terrainpal.py --apply`, or anything else that rebuilds `TMAINFORM` from the `.mtb` copy, resurrects all 27 deleted components.** `.mtb` still holds the full two-row blob and those scripts read whatever the resource entry points at. They currently no-op on their own section marker, so this only bites after a manual section removal.

⚠ **`build_editor_toolbar.py`'s docstring claim that "all 32 handler names were verified against the published method table" is not enforced in its code, and one name is wrong**: `MBOpenMapset` carries `OnClick=OpenMapsetClick` while the table entry is `OpenMapSetClick`. It has always worked because **Delphi's `TObject.MethodAddress` folds case** — worth knowing before anyone "fixes" a handler-name mismatch that is not a defect. The trim script's own check is therefore case-insensitive and prints the table spelling when it differs.

`build_editor_toolbar.py` itself still has no scripted `--undo`. `.mtb` is not the newest section any more (`.ctp`/`.vgo`/`.pty`/`.tres` all follow it) — a surgical revert means restoring the original `.rsrc` bytes for the `TMAINFORM` data-entry pointer and dropping `.mtb`, and re-tuning the toolbar is meant to be done by rewriting the DFM in place (clearing the marker check) rather than by any revert-then-reapply cycle.

---

## 4. Terrain palette — Sky/Chasm brushes + cross-level (`build_deved_terrainpal.py`)

✅ CONFIRMED WORKING (2026-07-24; carried forward from `09-terrain-movement.md`, which covers *why* Chasm (`0xB`) and Sky (`0xE`) exist as flying/floating-only terrains, their movement tables, cliff transitions, and the Coast-water-family filter trap — none of that is repeated here). This section is the **general reference for adding any new terrain brush, or any new DFM-callable handler, to this editor** — the mechanism generalises well beyond these two terrains.

**What it adds.** Sky and Chasm brush buttons, plus makes the whole palette **cross-level**: every cave terrain gets a button on the Surface tab and vice versa (`TMORTerrainControl.GetRndResource` keys resources by terrain id alone — the engine never had a level restriction, so this was a pure UI gap). Both palette panels grow 76→152 px (4 rows); the resource grid below is `alClient` and reflows.

**Three moving parts:**

1. **Cross-level buttons need zero new code.** Same DFM name-resolution trick as §3: a clone button's `OnClick` points at an *existing* handler (`WaterBtnClick`, `LavaBtnClick`, …) — vanilla itself already does this (`uArmyBtn→ArmyBtnClick`). Glyph bitmaps are copied verbatim from the originals.
2. **Two genuinely new handlers.** Every `TMainForm.<Terrain>BtnClick` is the *same* 43-byte stub differing in exactly one `mov dl,<terrain id>` byte; the script assembles `SkyBtnClick` (`dl=0xE`, landed `0x52E000`) and `ChasmBtnClick` (`dl=0xB`, `0x52E02C`) and **asserts the template re-assembles byte-identical to the real `TMainForm.uWaterBtnClick`** (`dl=0xA`) before writing — a self-checking template rather than a hand-derived stub. Two handler-body shapes exist in the wild: the *surface* buttons' handler calls `TSpeedButton.SetAllowAllUp` first and reads `Sender`; the *underground* buttons' handler (43 bytes, no `SetAllowAllUp`) ignores `Sender` entirely. **The new stubs copy the underground shape** specifically because it ignores `Sender` — one handler then works correctly from either palette panel. Both shapes end by testing a byte at `[Self+0x60C]+0xC0`, which selects change-terrain vs. clear-terrain behaviour; the new stubs replicate that test blindly, without needing to know what the flag actually means, exactly like they copy the rest of the template.
3. **Making a new handler name resolvable at all needs the published method table relocated.** It can't grow in place (the `TMainForm` class-name shortstring sits immediately after it in memory), so the whole table (132→134 entries, 3181→3219 bytes) is copied into `.ctp` at `0x52E060` and the VMT's `vmtMethodTable` slot (`VMT−0x28` = `0x00425CD8`) is repointed there from `0x4272EE`. (`build_deved_heroprune.py` later relocated it a second time, to `0x0058E5CC` with 135 entries — §10; the table at `0x52E060` survives untouched as that script's `--undo` target.) Delphi 3 VMT layout, empirically confirmed across this project: self-ptr `−0x40`, method table `−0x28`, class name `−0x20`, instance size `−0x1C`, parent `−0x18`. Table entry format: `{word size-including-itself}{dword code address}{shortstring name}`, after a leading word count.

**Glyphs.** 48×32 24-bit BMPs with a 4-byte Delphi `TBitmap` length prefix; the bottom-left pixel is the transparent key colour. Sky/Chasm art comes from `<game>\Zigmod\Sky.bmp`/`Chasm.bmp` (actually 256×256 RGBA PNGs despite the extension), masked to an existing glyph's exact hexagon silhouette. Two things learned rendering it down: plain Lanczos downscaling averages a starfield's stars away entirely by 48×32, so the script blends a **max-pool** with the average (stars survive) before a brightness boost; and because the two source images are visually identical, Sky and Chasm are differentiated deliberately in the glyph pipeline alone (brighter/open vs. darkened, per-terrain boost knobs) so the palette reads the two apart.

**Layering.** Reads whatever DFM the `TMAINFORM` resource entry currently points at, so it **must run after** `build_dlgdirs.py` and `build_editor_toolbar.py` — it consumed the `.mtb` copy and repointed the entry at `.ctp`, leaving `.mtb` dead for `TMAINFORM` in turn (§1.4's chain).

**Live-tested (automated, 2026-07-24):** the editor launching maximized with no crash already proves every new `OnClick` name resolved (an unresolved handler name raises `EReadError` while streaming the form, so the form simply wouldn't show); both palettes then render all 18 buttons at the correct height, Level-switching swaps to the Underground set correctly, and clicking `uSkyBtn`/`uChasmBtn`/a cross-level clone all latch in the `GroupIndex=1` radio group with no exception — for Sky/Chasm specifically that's only reachable via the relocated method table, so it's a real proof of the repoint, not just of the DFM. `dasm.py` independently resolves both stub names from the new table, confirming the repoint a second way.

**UI structure recon.** At the time this feature was built, the `TMAINFORM` DFM's active copy lived at file offset `0xDC600` inside `.mtb` (modtoolbar's relocation — the original `0x74AFC` copy in `.rsrc` was already dead, §1.4's chain). Surface palette (`ToolbarPnl`) buttons: `ArmyBtn`, `ItemBtn`, `RoadBtn`, `GrassBtn`, `WaterBtn`, `IceBtn`, `SnowBtn`, `WastelandBtn`, `DesertBtn`, `SteppeBtn` (all `GroupIndex=1`). Underground palette (`Panel10`) buttons: `uArmyBtn`/`uItemBtn` (reusing the *surface* handlers directly — vanilla's own cross-level precedent), `uWaterBtn`, `DirtBtn`, `LavaBtn`, `uIceBtn`, `EarthBtn`, `RockBtn`. The two handler-body shapes noted above sit at fixed address ranges: surface handlers from `0x42B19C`, underground ones from `0x42B594`.

**Terrain ids used by the vanilla handlers** (the gap this feature filled): Water 0, Grass 1, Desert 2, Snow 3, Steppe 4, Wasteland 5, Ice 6, Earth 7, Rock 8, Lava 9, uWater `0xA`, Dirt `0xC`, uIce `0xD` — every id except `0xB` and `0xE` (this feature's Chasm/Sky) and `0xF` Border, which remains unexposed in any palette.

**Traps hit while testing, kept for the next session that drives this editor by automation:** `SetForegroundWindow` plus a synthetic `PgDn` **killed the process outright** — a DirectDraw activation issue, not the patch (the same patched editor survived an identical flow afterwards using message-only input), and `PgDn` isn't even a level key here regardless (level switching is `LevelUpBtn`/`LevelDownBtn`, two `TSpeedButton`s on `Panel2` at Left 288/328, Top 4, 39×38). Separately, `SB_GETTEXT` to the status bar blocks and never marshals cross-process — read the status text out of a `grabwin.py` bitmap capture instead.

**The alternative route not taken — ruleset "hex objects."** AoW1 modders can also surface a terrain as a *paintable resource-grid tile* by inserting a hand-made hexagon resource into the ruleset (`Release.hss` already carries three: `Lava-1.bmp`, `Dirt-1.bmp`, `Boder-1.bmp` [sic]) — each is an ordinary single-image tile resource (a 1-entry `TTerrainList` header + an embedded ILB) at 50×42 instead of vanilla's 48×32. Adding `Sky-1.bmp`/`Chasm-1.bmp` this way would double as a directly clickable palette entry *and* feed the art into `GetRndResource`'s pool, so the brush buttons above would start painting it too — but that edit has to be made in `AoWDevEd` itself (`Release.hss` cannot be byte-patched directly, per `09-terrain-movement.md`), so it isn't a shortcut around this feature, just a second, complementary way to reach the same pool. Not built; recorded because it's the general pattern for exposing *any* new terrain without a brush button at all. (Also recon'd: `TMainForm.LinkToMORList` hands every `TEResourceGrid` the *same* resource list — which tab a resource lands in is driven purely by its own edit-ID, not by any exe-side per-grid filter, so a new palette tab specifically can never be populated from the exe side alone.)

No scripted `--undo`; `09-terrain-movement.md` already recommends the surgical path (restore the `.ctp` section + the `TMAINFORM` resource repoint) rather than any snapshot, consistent with this file's finding that no snapshot exists to restore in the first place.

---

## 5. Map Validation dialog — clickable entries (`build_validation_goto.py`)

✅ CONFIRMED WORKING (2026-07-28) — user validated in the editor ("that's working well").

Double-clicking a line in the Map Validation dialog (`Developer > Validate Map`, a read-only `TMemo`) centres the map view on the object that line describes, switching level first if needed; double-clicking an indented `  Warning: …` detail line walks upward to find its `<Name> at location (x, y, z)` header; lines with no location above them (player-level warnings, "Map validated successfully") do nothing.

**Why parsing the visible text beats a side-channel.** The listing is filled by `AoWEPACK.dpl`'s own `TStructure.MainValidateMap`, which formats each header as a resourcestring `%0:s at location %1:s` with `%1` built by `LStrCatN` from `GetX`/`GetY`/`GetLevel` — so the `(x, y, z)` group is **always the last parenthesised group** on a header line, and survives dictionary translation intact (parens and digits don't translate). The memo carries no object references at all, so the two options were parse-the-text (translation-proof, zero cross-module state) or hook `MainValidateMap` DLL-side to record a side-table (rejected: rebasing DLL storage + object lifetime headaches for no real benefit) — text-parsing won cleanly.

**The patch.** One call in `TMainForm.ValidateMapBtnClick` (`0x42CEE2`, the `ShowModal` thunk call, `E8 01 44 FD FF`) becomes `call install_cave` (`E8 69 32 16 00`, verified live today — matches the documented bytes exactly). At that point `EAX` is the just-created dialog; the **install cave** (`0x590150`, 29 B) writes the memo's `FOnDblClick` (`TMethod`: Code `+0xAC`, Data `+0xB0` on `TControl` — proven both from TMemo RTTI and from `VCL30!TControl.DblClick`'s own dispatch code) before restoring `EAX` and tail-jumping into the real `ShowModal` thunk.

**The handler cave** (`0x590000`, 330 B, a `TNotifyEvent` — `EDX`=the memo):

1. `EM_LINEFROMCHAR(-1)` via `Perform` (through the exe's own IAT slot for `Controls.TControl.Perform`, `0x432354` — no new imports) gets the clicked line; the first click of a double-click sets the caret even if the second word-selects, so this is reliable.
2. Walk upward with `EM_GETLINE` into a 256-byte stack buffer, scanning **right-to-left** for `'('` then parsing `int, int, int)` (ints capped at 999) — right-to-left is what makes object names containing parentheses safe, since the location group is always the rightmost one. First line that parses wins; a parse failure decrements the line index and retries.
3. On success: `TMainForm.SetMapLevel(mainform, z)` (`0x429C68` — no-ops if already displayed; its `BOUND` guard is only shortint range, hence a `z<=7` sanity cap before calling it) then `THSMEdit.CenterView(ctrl, x, y, z)` (import thunk `0x402E28`; clamps to map edges itself, so out-of-range coordinates from a mis-parse are harmless).

This mirrors the editor's own precedent, `TPlayerInfoFloater.StructureGridDblClick` (`0x425BEC`: grid row → `GetX`/`GetY`/`GetLevel` → `SetMapLevel` → `CenterView`) — same call sequence, just sourcing `x`/`y`/`z` from parsed line text instead of a stored object reference. (That handler also calls `TAoWHSMap.Select` to highlight the object; this one doesn't, since it would need a coordinate→object lookup it doesn't otherwise need — a possible v2 nicety.)

**Live-tested (automated, 2026-07-28):** double-clicking a no-location line does nothing (viewport untouched, only a tick counter moves); double-clicking an injected `Probe at location (40, 30, 0)` line recentres correctly; double-clicking an indented line below a header walks up and recentres. The level-*switching* branch (`z≠`current) was never exercised — the test map only had one level open — see Open items.

**Two small traps for the next editor cave.** Keystone's Intel-mode (LLVM) parser has no `;`-comment support at all — the build script's `asm_src()` helper strips them before assembling, a step every other script in this file that assembles from a commented source template also needs (the terrainpal stubs happened to be comment-free, so they never hit it). And `ValidateMapBtn` **is not a menu item** — it's a windowless `TSpeedButton` on vanilla `Panel2` (design coordinates 96..135 × 4..42), so automating it means posting `WM_LBUTTON*` to the *panel*, exactly like §3's toolbar buttons.

No scripted `--undo`. Surgical revert: restore `E8 01 44 FD FF` at `0x42CEE2` and zero the `.vgo` body (the dead section header is harmless left in place).

---

## 6. Party placer → random army generator (`build_party_random.py`, `party_dialog.py`)

✅ CONFIRMED WORKING (2026-07-28) — user validated in the editor ("all working"), then requested the Medium/Large tier retune covered below, which was re-verified by automated live placement across several land hexes per tier rather than by a further user session — worth knowing precisely because it means the *retuned spreads* specifically carry slightly weaker evidence than the *mechanism* (dialog, hook, race mask, behaviour byte) they sit inside.

Reworks the editor's Party tool: instead of dropping an empty stack the mapmaker fills by hand, it opens a "Random Party Generator" dialog (strength / behaviour / eligible races) the first time, then places a randomly-generated stack of that configuration on every subsequent placement — configure once, place many. **No races are ticked by default**, and a zero race mask makes the generator early-out, so out of the box the tool is byte-for-byte the vanilla empty-stack behaviour; it only starts generating once the mapmaker opts in. Only **empty** parties are ever filled — clicking an existing, non-empty stack with the Party tool still just opens it for editing, unchanged.

| Strength | Composition | encoding |
|---|---|---|
| Weak | 3–4 × level 1 | `(1,3,2)` |
| Medium | 3–5 × level 1, 2 × level 2 | `(1,3,3),(2,2,1)` |
| Large | 4 × level 1, 2–3 × level 2, 1 × level 3 | `(1,4,1),(2,2,2),(3,1,1)` |

Each tuple is `(level, base count, random span)` and the actual count is `base + RandInt(span)` — `span≤1` gives a fixed count, so any tier can be given a spread without touching the cave logic, only the `g_spec` data (verified directly against the shipped `STRENGTH_TABLE` in `build_party_random.py`). Tuned 2026-07-28 from an initial fixed-count table: Medium's level-1 count and Large's level-2 count gained spreads on user request, replacing an earlier one-off "Weak gets +RandInt(2)" special case with this general mechanism. Live-read today: `.pty`'s `g_strength=1`/`g_racemask=0`/`g_behavior=2` — the dialog has never been used to change the installed defaults from Medium/none/Guard.

### 6.1 The rebase-delta trick — calling another module's functions and globals with no new imports

**The general idiom, used three times in this file alone** (here; `build_editor_timerres.py` §1.2; `build_dlgdirs.py` §2.1) and worth a single clean statement: an **imported variable** slot in a module's own IAT gives you that target module's *runtime rebase delta* for free, because the loader has already resolved the variable's live address into that slot.

```
delta = [own IAT slot holding the address of some known imported variable/function]
        − (that thing's preferred VA in the target module)
```

Add `delta` to **any** preferred VA in the target module — a function, a global, a class-reference cell — to get its runtime address, with no new import descriptor and no dependence on the target module's own export table (which may not even have one, for an `.exe`). Two concrete instances:

- **`dll_delta` (AoWEPACK.dpl), used by this feature**: `AoWDevEd.exe` imports the AoWEPACK global `AoWE.AoWHSSet` at IAT slot `0x432898`; that slot holds the variable's *runtime* address, and the variable's own preferred VA is `0x558FA044`, so `dll_delta = [0x432898] − 0x558FA044`.
- **`vcl_delta` (VCL30.dpl), used by §6.4's dialog and by §1.2/§2.1**: `[0x432210] − 0x41336300` (the exe's IAT slot for `Forms.TCustomForm.Create` against its own preferred VA).

Preferred VAs and conventions used here (add `dll_delta`):

| address | symbol | convention |
|---|---|---|
| `0x55710C6C` | `TUnit` class-reference global | `classref = [addr+delta]` |
| `0x5577EB28` | `TAbstractUnit.Create` | EAX=classref, DL=1, ECX=0 → EAX=unit |
| `0x55782BE4` | `TUnit.SetUnitResource` | EAX=unit, EDX=resource |
| `0x55785050` | `TUnitResourceList.GetUnitResource` | EAX=list, EDX=index → EAX=res (0 if OOB) |
| `0x55701080` | `System._RandInt` | EAX=range → EAX=0..range−1 |
| `0x55701030` | `System.Randomize` | — |

Object layout used alongside the table above: the `HSSet` object is `[[0x432898]]`; the **unit resource list is `[HSSet+0x5C]`** (the generator's candidate pool, §6.2) and the **race resource list is `[HSSet+0x54]`** (§6.4's dialog); both are engine lists, so element count is `[[list+8]+8]`, never `[list+8]`. `TUnit`'s own class VMT (at `[0x55710C6C]`) sits at `0x55710CAC`, instance size `0x94`; `TArmy`'s VMT sits at `0x557130EC`, instance size `0x2C` (`GetCount` is its `+0x54`).

`AoWDevEd.exe`'s own three RNG draws (`Randomize` + raw `RandInt`) are already in `12-re-toolchain.md`'s standing RNG audit as **correct as they stand** — "map editor only, no peers, nothing replicated" — so this file doesn't re-derive the SYNC/RAW question the rest of the project has to ask of every roll; there is no lockstep to protect inside a single-process editor.

### 6.2 Where a party is placed, and the hook

`TMainForm.ArmyBtnClick` (`0x42B69C`) only *enters place mode*; the actual placement is the editor-side `TArmyPlaceControl.MsgProc` (`0x41A35C`, VMT `0x419CD4`), which on the placement message creates a `TArmyHS` and calls `THSMap.PlaceHX`, then opens **TArmyEditForm** ("Army Properties") for manual filling — `TArmyHS+0x1C` is the `TArmy`.

The hook re-implements 4 bytes at `0x41A414` (`test esi,esi / je 0x41A439 / push 0 / push 0`, 8 B total) as `jmp cave` + 3 nops: the cave re-runs those exact instructions and, only when `esi` (the just-created army HS) is non-nil **and** its `TArmy`'s unit count is 0 (a freshly created, empty party — never a stack the user actually clicked), calls the generator before falling through to the vanilla "open Army Properties" tail.

**The generator**, per `(level, count)` pair of the active strength: build a candidate array of unit-resource indices whose `GetUnitLevel` (`TUnit` VMT `+0xA0`) equals the level and whose `GetRace` (`+0xA4`) is in the allowed mask — using **one scratch `TUnit`** re-pointed at each resource in turn via `SetUnitResource`, because that's how the engine's own filters read these fields, so any per-resource logic is honoured automatically; then `count` times, pick a random candidate, create a real `TUnit`, and if `TArmy.CanAddUnit` (`+0xA4` — a *different* class's `+0xA4`, see the trap below) then `TArmy.AddUnit` (`+0xAC`), releasing the local reference either way (`Release` = `TAbstractUnit` VMT `+0x2C`) — the identical create/add/release sequence the engine's own `AoWE.FillWithRandomUnits` uses (Failed approaches: why that helper wasn't reused directly).

The engine's own helpers, for reference: `AoWE.FillWithRandomUnits @0x5575B160` (`EAX`=candidate `TIntegerList`, `EDX`=`TArmy`, `ECX`=max level, `[ebp+8]`=unit-type set, `[ebp+0xC]`=value budget, `ret 8`; retries randomly up to 50 times, plus a 20-try "best fit to the remaining budget" refinement) and `AoWE.FillWithRandomUnitIndexes @0x5575B358` (the same thing, appending indices to a list instead). `TExplorationSite.GenerateDefenders @0x557C1FC0` is a live caller, passing budget = strength × `0x32` — useful as a worked example of the convention if a future feature ever does want the engine's own budget-driven filler rather than an exact per-level count.

⚠ **`TUnit+0xA4` is `GetRace`; `TArmy+0xA4` is `CanAddUnit`.** Same VMT offset, two unrelated classes — an easy silent conflation, and the reason the first pass at this analysis mislabelled the unit-type filter as a race filter. `TAbstractUnit.GetRace`/`.GetUnitLevel` are **base stubs** returning `−1`/`0` — only the `TUnit` overrides are real, so both must always be called virtually, never as a direct call.

⚠ **`TArmy.CanAddUnit` enforces terrain, not just stack size** — when the army is already on the map it calls `ValidTerrain` against the hex it stands on, so a party dropped on **water** with land-only races ticked comes out silently empty or short: the generator worked, the engine refused the units. (This cost a real debugging detour: a Dwarves-only test party came out empty on three ocean hexes and full on grass.) The behaviour is correct and kept; if the dialog ever wants to warn the user, this is where the rejection actually happens.

### 6.3 The behaviour byte

The hook also writes the chosen behaviour straight to `TArmy+0x24` — the same field `TArmyEditForm.BehaviourComboBoxChange` (`0x41A288`) writes. ⚠ **The dropdown's row order is not its id order** — the combo keeps the real id in each item's `Objects[]`:

| row | Auto | Patrol | Guard | Guard Area | Scout | Refuge | Raid | Suicidal |
|---|---|---|---|---|---|---|---|---|
| id | 0 | 1 | 2 | 3 | 4 | 5 | 6 | **10** |

(`TArmy.SetBehavior` builds a *runtime* AI group and is a different thing entirely — not what the editor writes, don't reach for it.)

### 6.4 The configuration dialog — a VCL dialog built entirely from a cave, no DFM

Hook: the first 5 bytes of `TMainForm.ArmyBtnClick` (`0x42B69C`, `push ebx / mov ebx,eax / mov eax,edx`) become `jmp armybtn_hook`; the cave re-runs those three instructions, calls `show_dialog` with `EAX`/`EDX`/`ECX` preserved, and rejoins at `0x42B6A1`.

**Built at runtime from real VCL controls** (`TCustomForm.CreateNew` + a data-driven loop over a 21-entry control table) rather than from a DFM resource — this avoids inventing a whole new Delphi form class and rebuilding the PE resource tree, and crucially lets the race checkboxes take their captions from whatever mapset is actually loaded (the installed set is Ziggurat's, not vanilla's). Reached through the same `vcl_delta` idiom as §6.1/§1.2/§2.1 (`[0x432210] − 0x41336300`):

| what | where (VCL30 preferred rva, add `vcl_delta`) |
|---|---|
| `TCustomForm.CreateNew` | `0x36490` — EAX=class, DL=1, ECX=owner |
| virtual constructor | **VMT slot `0x24`** (`TComponent.Create`) — dispatches per class |
| `TControl.SetBounds` | **VMT slot `0x4C`**; EDX=Left, ECX=Top, push Width then Height, `ret 8` |
| `TStrings.Add` | **VMT slot `0x34`**; combo's `TStrings` is at `combo+0x118` |
| checkbox get/set `Checked`, radio `SetChecked`, combo `SetItemIndex`/`SetStyle` | rvas `0x51800`/`0x51820`/`0x51B6C`/`0x50568`/`0x50760` (`csDropDownList=2`) |
| class VMTs | `TForm 0x340EC`, `TGroupBox 0x49990`, `TRadioButton 0x4CBD0`, `TCheckBox 0x4C64C`, `TComboBox 0x4B878`, `TButton 0x4BFD0` |

Field shortcuts sidestep several of the calls above: `TRadioButton.Checked` is field-backed at `+0x11D`, `TButton.ModalResult` at `+0x120` (so OK/Cancel need **no event handlers at all** — set the field and the modal form closes itself), `TComponent.Tag` at `+0xC`. Captions use `SetTextBuf` (a raw `PChar`), sidestepping AnsiString construction entirely; only the combo's `Items.Add` needs a real Delphi 3 string literal (`[allocSize][refcount=−1][length]` immediately before the NUL-terminated characters — verified against shipped literals).

The race list itself comes from `[HSSet+0x54]` (`TRaceResourceList`; count via the engine-list rule `[[list+8]+8]`, name via `GetRaceResource(i)+0x24`, already NUL-terminated so it hands straight to `SetTextBuf`); checkboxes beyond the live race count are hidden. Installed (Ziggurat) set has 286 unit resources; races `0..11` are the twelve playable races and `255` is the raceless pool used by the palette's Humanoids/Creatures/Machines tabs (those tabs are `GetUnitType`, not race, at all) — **the authoritative race byte is `res+0x20`**, not `res+0x1C` (a display-name half that is *not* always the race: race 9 yields both "Orc" and "Minotaur" unit names).

⚠ **`TCustomCheckBox.GetChecked` reads the cached field `[self+0x11E]`, not the live window state.** Driving an automated test with `BM_SETCHECK` changes the box on screen but not what the cave actually reads back — cost one confusing "the mask came back as every race" result before switching to `BM_CLICK` (which the VCL processes properly) or setting the field directly.

**Re-tuning never needs a revert.** `build_party_random.py --apply` rewrites `.pty` **in place** every time (it's the last section, so truncate-and-re-append is safe) rather than adding a new backup layer — Stage 2 (the dialog) was applied this way on top of Stage 1 with no new `.pre-*` file. ⚠ Its "already patched" check compares the **whole** intended section body, not just the hook-target bytes — a data-only change (dialog geometry, the strength table, defaults) leaves every label address identical, so a hook-only check would silently no-op; this bit once on 2026-07-28 when a dialog layout change appeared to apply but hadn't.

### 6.5 Why the dialog "feels slow" to open — it isn't the dialog

Measured with posted clicks: the dialog window itself is created ~78 ms after the click, all 21 controls exist by ~96 ms (so ~18 ms for the *entire* control tree), and content is pixel-stable by ~120 ms — squarely in line with comparable stock dialogs (About: 2 controls/27 ms; Game Settings: 19/55 ms; Map Settings: 52/165 ms). **The real driver is the same 15 Hz-era pump cost from §1**: `SendMessageTimeout(WM_NULL)` to a completely idle main window still took ~24 ms round-trip on this build, and a three-message click (move/down/up) costs ~72 ms before `ArmyBtnClick` even runs — most of the observed 99 ms. Sampling during the open shows the process essentially idle in message waits, confirming it's waiting on the pump, not computing anything. (`FrameRate` was already 120 at the time of this measurement — raising it further cannot help, since §1.2/1.4 established the floor is elsewhere.)

**Live-tested (automated, 2026-07-28)**, race/level counts read directly from placed units (`unit[0x40]→resource`, `res[0x2F]`=level, `res[0x20]`=race):

| setting | result |
|---|---|
| Medium, all races | `{lvl1:4, lvl2:2}` = 6 units, 5 different races |
| Large, all races | `{lvl1:4, lvl2:3, lvl3:1}` = 8 units |
| Weak, all races | `{lvl1:4}` (3 + `rand(2)` rolled 4) |
| Weak, mask `0x40` (Dwarf only) | `{lvl1:3}`, all race 6 — mask honoured |
| clicking an existing, non-empty party | untouched (unit count ≠ 0 → hook skips) |
| dialog round-trip: Large + Orc/Goblin + Raid, OK | globals became `g_strength=2 g_racemask=0x600 g_behavior=6` |
| party placed with those settings | 8 units `{lvl1:4, lvl2:3, lvl3:1}`, races {9,10} only, `TArmy+0x24=6` |
| default state (no races ticked), OK, place | 0 units — vanilla empty stack — `TArmy+0x24=2` (Guard) |
| retuned Weak × 2 land hexes | `{lvl1:3}`, `{lvl1:4}` — 3–4 spread |
| retuned Medium × 4 land hexes | `{lvl1:5,lvl2:2}` ×2, `{lvl1:4,lvl2:2}`, `{lvl1:3,lvl2:2}` — 3–5 spread, level 2 fixed |
| retuned Large × 4 land hexes | `{lvl1:4,lvl2:2,lvl3:1}` ×2, `{lvl1:4,lvl2:3,lvl3:1}` ×2 — 2–3 spread at level 2 |

Confirming the "vanilla until opted in" design goal (the default-state row) and that every retuned spread matches §6's table exactly.

**Debugging technique worth re-deriving if needed again:** a VMT-scan probe can find the live `TArmyEditForm` (VMT `0x419908`) and walk `form+0x214→TUnitGrid`, `grid+0x1E0→TArmy`, `army+8→` the inner `TList` (`+8` count, `+4` items) to read a party's contents without touching the save file. ⚠ Freed forms keep their VMT pointer, so a scan turns up several candidates — pin the live one by finding whichever object holds the visible window's HWND. ⚠ Ghidra renders these engine classes as `int *`, so `param_1[0x78]` in a decompile is a **dword index**, i.e. byte offset `0x1E0` — reading it as a byte offset silently lands on the wrong field.

No scripted `--undo` for Stage 1's hook (Stage 2 never needs one, §6.4). Manual: restore `85 F6 74 21 6A 00 6A 00` at `0x41A414` and zero the `.pty` body.

---

## 7. Area copy-paste — radius-N discs, 6-way rotation

**SPECULATIVE — fully designed, never built.** Would touch `HSEPack.dpl` with position-independent caves; the game loads that DLL but never reaches the `THSMEdit` code paths involved, so it would be as safe there as every other editor-only HSEPack patch in this file.

**What exists already, that this reuses rather than replaces.** The editor already has a multi-object hex clipboard: `THSMEdit.CutHS/CopyHS/PasteHS/DeleteHS` (`0x55612F8C`/`0x556130B4`/`0x55613188`/`0x55613320`), wired to Ctrl+X/C/V/Del in `KeyDown` (`0x556133C4`) and to the right-click popup and the Edit menu. `CopyHS` iterates the **whole current selection** (a `THexagonSpriteSelection`, TList-backed) through EngineP's `TECopyComponent` onto the Windows clipboard under a per-map-level format name (so cross-level paste is already blocked by design, and this feature keeps that); `PasteHS` places every clipboard object at one anchor hex (today's vanilla semantics: a single-hex stack copy). Serialization is the same `rwEObject` framework the `.hsm` save format itself uses, so object positions are expected to survive the round-trip (flagged for verification at implementation time regardless).

**Finalised requirements** (superseding an earlier, structurally similar draft in the original lag-investigation doc that used Ctrl+Shift+R for rotation and left the event-marker filter as a pending question — both settled below): radius-N disc copy (3/5/7+); 6-way rotation via **Ctrl+mouse-wheel**; exclude unit armies (`TUnitHS`), cities/settlements (`TCity`), and scenario event markers (`TFlagEvent`/`TMoveOnEvent`); include everything else — non-city structures (mines/nodes/altars/sites, keeping their owner), terrain, roads, overlays, ground items, clouds, crops.

**Grounded facts, disassembly-verified.** Grid layout is **odd-q offset** (`HXtoHP`: `x_px=x*32+8`, `y_px=y*32+(x&1)*16`). Rotation works in cube coordinates (`q=x; r=y−(x−(x&1))/2; s=−q−r`; 60° CW is `(q,r,s)→(−r,−s,−q)`, applied *k* times to the **delta** between an object and the copy anchor, not to raw coordinates, since only deltas are translation-invariant) — a disc of radius R maps onto itself under rotation, so there's no shape distortion to correct for. Roads rotate for free (`TRoad.UpdateNeighbourTransitions` derives appearance from neighbours after placement, exactly like ordinary terrain edges — no direction bits to remap). The vanilla select tool is single-hex only, so area-copy must enumerate a field's HS array directly (`[field+8]`, count via the field's own vtable `+0x54`) rather than driving the selection tool in a loop.

**The class-taxonomy trap for the filter.** `TCity → TPlayerCropStructure → TPlayerStructure → TStructure` — cities *are* structures, so the exclusion filter must match `TCity` exactly, never the broader `TPlayerStructure` (which would also silently drop mines and nodes: `TAirNode → TProductionPlace → TPlayerStructure → TStructure`). Because `HSEPack.dpl` must not import from `AoWEPACK.dpl` (the dependency runs the other way), the filter can't use a Delphi `is` test — it has to **walk the VMT parent chain comparing class-name shortstrings** (name at `VMT−0x20`, parent classref at `VMT−0x18`), which is import-free and automatically subclass-safe.

**The three caves.** (1) *Rotation state*: a Ctrl+mouse-wheel hook (a different message path from KeyDown — `WM_MOUSEWHEEL`/`CMMouseWheel`, not yet confirmed to exist on `THSMEdit` at all) increments a stored rotation `mod 6` and shows a message. (2) *Area-copy* (`KeyDown` hook, Ctrl+Shift+C, radius via Ctrl+Shift+1..9): walk a radius-R cube-distance disc, bounds-check, enumerate each field's HS array, dedupe multi-hex objects by base-hex membership, apply the name-chain filter, then fall into the existing `CopyHS` with a fresh anchor+radius+copy-stamp recorded in cave globals. (3) *Rotated offset-paste* (a cave over `PasteHS`'s existing `Place` loop, Ctrl+Shift+V): if the clipboard predates this session (no copy-stamp) fall back to vanilla single-hex behaviour; otherwise read each object's stored hex position, rotate the delta from the copy anchor by the stored rotation, and place at the equivalent offset from the paste anchor. Multi-hex structures rotate their *base* position only — no rotated artwork exists, so the footprint itself doesn't turn, and `Place`'s own overlap check rejects any resulting collision.

**No preview, no undo in v1** — the editor has no undo anywhere in it, so the standing advice is simply "save before stamping."

**Implementation-time verifications, in order** (nothing below has been checked, because nothing has been built):

1. **Apply the autosave lesson (§8) before anything else.** Confirm every hook — the `KeyDown` extension, and especially the mouse-wheel path, a message route nothing else in this file has proven exists on `THSMEdit` at all — actually **fires** on the intended input via a minimal counter read (`HSEPack` rebases, so read it through a module-base offset, not a fixed VA), before investing in the full cave.
2. The `[field+8]`/vtable-`+0x54` array-access pattern on a live field (or `GetHN(i)` as a fallback argument order).
3. That object positions genuinely survive the clipboard round-trip — read a pasted object's `hx`/`hy` back pre-`Place`.
4. Place order: that the double-reversal between selection order, `CopyHS`, and `PasteHS` really does yield terrain-hexagon-before-overlay placement.
5. Selection-event storm behaviour with ~100 HSes selected at once (`TriggerSelectEvent` firing per selection) — if noisy, bypass the selection UI entirely and build the `TECopyComponent` list directly in the cave; `CopyHS`'s own loop is trivial to replicate.
6. That roads and terrain transitions look visually correct after a rotated paste (the auto-derive-from-neighbours assumption).
7. Map-edge clipping via the field bounds guard (map dimensions from the `TMapLevel` fields `TScanner.SetMap` already reads: `level+0xC`/`level+0x10`).
8. That Ctrl+mouse-wheel is actually free over the map view (no existing zoom/scroll binding) and that plain wheel still scrolls.
9. Filter correctness: place one of each excluded type (army, city, flag event, move-on event) plus one of each included type in the same test disc, copy-paste, and confirm only the right ones transfer.

---

## 8. Timer autosave — 🛑 REVERTED (2026-07-07)

**What it tried to do.** Every N minutes (default 5), silently write the current map to a fixed backup file (`<game dir>\Save\editor_autosave.hsm`) without touching the user's own filename or clearing the modified/dirty flag, so a crash costs at most N minutes.

**The obvious hook, and the two review fixes it needed before it could even be tested.** `TMainForm.HSMEditUpdateFrame` (`0x428D18` `AoWDevEd.exe` / `0x428CA0` `AoWEd.exe`, structurally identical bodies) looks exactly right: it's the render-loop callback, so a per-frame counter inside it is a self-contained clock needing no imports (`AUTOSAVE_FRAMES = minutes*60*fps`, no rollover, no first-call edge case). The 6-byte entry prologue (`55 8B EC 83 C4 9C`) becomes `jmp cave`. Two bugs were caught in review before this was ever applied: **the hook had to be a `JMP`, not a `CALL`** — a `CALL` would leave a return address under the re-executed prologue's own frame, so the function's own `ret` would land back inside its own body and crash on the very first frame; and **`EAX` (`Self`) had to be explicitly preserved across the save branch** — the resumed body reads `Self` from `EAX` several instructions in, but the save path (a `SaveHSM` call) clobbers it first.

**It assembled clean, ran without crashing, and did precisely nothing — the hook point was simply wrong.** Live-tested with a short 120-frame interval: after 4 seconds of active use, a real placement click, 300 posted `WM_MOUSEMOVE` messages, and 24 genuine cursor moves across hexes with the editor foreground, the cave's own frame counter (read directly from process memory) stayed at exactly **0**. Root cause: `THSMEdit.UpdateFrame` (the HSEPack-side per-frame method, distinct from this exe-side handler) **early-exits on a global `HSEdData.UpdateMap==0` gate**, and only fires the `OnUpdateFrame` **event** at all when the app is active *and* the real mouse is currently over a valid hex — it is a scene-activity notification, not a per-frame tick. The editor's live status-bar hex coordinates, which look like proof this fires constantly, are actually driven by the *separate* `OnMouseMove` handler.

This is a clean pass of the sharpened failed-approach test the rest of this project's docs are held to: it is exactly the hook a competent reverse-engineer would reach for first (it's *named* like a per-frame tick, and the render-loop framing in §1 makes it look doubly reasonable), and nothing about the eventual redesign path explains *why* it was dead — that took an empirical, process-memory counter read to discover, not inference from the correct answer.

**Everything else about the cave design remains valid, reusable machinery** if a v2 ever hooks a real per-frame or per-edit tick: the save call itself matches `THSMEdit.Save`'s own convention exactly (`EAX`=HSSet, `EDX`=filename AnsiString, two stack dwords for a progress callback, `ret 8`); a **NIL callback is provably safe** — `TEStorageStream.ShowProgress`'s "Assigned" guard tests only the *high word* of the callback code pointer, so pushing `0,0` skips the progress call entirely rather than faulting; the guard chain that decides whether to bother saving at all is `TMainForm+0x22C→HSMEdit`, `[HSMEdit+0x1BC]`≠0 ("map loaded" — the same field §1.3's render gate hooks), `[HSMEdit+0x1C0]→HSSet`, `[HSSet+0x3C]→THSMap`, `[THSMap+0x3C]&1` (the modified/dirty bit); and the embedded AnsiString literal follows the standard Delphi 3 immutable-constant layout (`refcount=−1`, then length, then NUL-terminated characters) so it can never be freed or reallocated by the callee. Neither `GetElapsedMilliSeconds` nor `GetTickCount`/`timeGetTime` is actually imported by either exe (checked directly in the IAT) — which is *why* frame-counting was chosen over a wall clock in the first place, and remains the right call for any redesign that doesn't specifically need real time.

**A risk worth carrying into any redesign, never actually tested because v1 never got far enough to matter: the save runs with no exception handling at all.** Vanilla `THSMEdit.Save` is invoked from a button handler wrapped in the VCL's own structured exception handling; this hook calls `SaveHSM` straight from the render-loop cave, outside any `try/except`. If `SaveHSM` ever raises — target directory missing, the backup file made read-only, a full disk — the exception would propagate unguarded, and an autosave that can crash the editor mid-session is worse than no autosave at all. `Save\` exists on a normal install so the happy path was never at risk, but a v2 attempt should deliberately test a failure case (make the backup path read-only, force a save, confirm the editor survives) before trusting the design — and if it doesn't survive, either wrap the call in a minimal SEH frame (`fs:[0]` chain built by hand in the cave) or pre-check the target path is writable before ever calling `SaveHSM`.

**v2 candidate hooks, not yet tried:** `TMainForm.HSMEditMouseMove` (`0x42AADC`, exe-local, fires on every genuine mouse move over the map — this is what actually drives the live coordinate readout, so it provably fires during real editing) is the preferred candidate; `THSMEdit.UpdateFrame`'s own *entry* (`0x55614904`, HSEPack, before the `UpdateMap` gate) is the alternative, at the cost of needing a position-independent cave in a module shared with the game; or abandon time-based saving entirely for "save every N edits" on the placement path. **Whichever is chosen, verify it fires with the same empirical counter-read technique before writing the full cave** — this is the one lesson worth carrying into any future editor-hook feature in this file, autosave included.

No backup exists to restore (deleted after the 2026-07-07 revert, along with every other redundant post-confirmation backup) and the feature is confirmed absent from the live binary today — `AoWDevEd.exe` has no `.asv` section, and its `HSMEditUpdateFrame` entry reads the untouched vanilla prologue (`55 8B EC 83 C4 9C`, verified live). If v2 is ever built and applied, it shares no cave or hook with anything else in this file, so its own eventual undo would be fully independent.

---

## 9. New map dialog → "New generated map" (`build_deved_newmapgen.py`)

🔨 **APPLIED, UNTESTED (rebuilt 2026-09-06)**, `AoWDevEd.exe` only. `File > New` gains a
`New blank map` / `New generated map` pair, eight terrain-prevalence dropdowns, a sea-percentage
slider, **twelve** world dials, an island-size range, a cold-direction picker and an info button.
**Every setting is remembered from the last generation** (§9.4b). It defaults to
**Extra large (128×128)** and **three levels** — moved in the DFM by relocating `Checked`+`TabStop`
from `MediumRB` to `ExtraLargeRB` and from `OneLevel` to `ThreeLevels`; the cave reads both radio
groups by *elimination*, so nothing else changes. Blank re-enters the vanilla body untouched.
Generated shells out to `Zig Modding Tools\devedgen.bat`, waits, and opens the result. The
generator itself is `Zig Modding Tools\zig_mapgen.py`; see [[aow1-ziggurat-map-generator]].

**The hook is a call retarget**, not an `E9`: `OKBtnClick @0x004034E4` is a five-byte thunk
(`call 0x4033F0; ret`), so only the rel32 at `0x004034E5` moves. Nothing is displaced and the
`--undo` is four bytes.

### 9.1 Three VMT tables had to be relocated, for three different reasons

`TNewMapDlg` is a compiled Delphi 3 class and none of its tables can grow in place — field table,
method table and the class-name shortstring sit packed back to back ending at file `0x2782`.

| table | VMT slot | was | now | why |
|---|---|---|---|---|
| field table | `-0x2C` @ `0x00403250` | 19 entries | 47 @ `0x596808` | a DFM component is only stored into the form if the class publishes a FIELD of that name |
| class table | (pointer inside the field table) | 8 slots @ `0x004033A0` | 11 @ `0x5967D8` | the new fields' class indices; the three added slots are the **existing** IAT slots for `TComboBox` `0x00432640`, `TEdit` `0x00432648`, `TScrollBar` `0x0043262C` — no new import |
| method table | `-0x28` @ `0x00403382` | 1 (`OKBtnClick`) | 4 @ `0x596798` | a DFM can only bind a handler the class **publishes**, and the controls needed three |
| InstanceSize | `-0x1C` | `0x228` | `0x298` | 28 new 4-byte field slots, `0x228`–`0x294` |

⚠ **Every address in this section moves whenever the cave is rebuilt** — the tables are `place()`d
after the code, so one more dial shifts all four. The values above are the twelve-dial build of
2026-09-06 (`.nmg` rva `0x193000`, 24022 of 28160 B; cave 1639 B @ `0x593000`; `GenInfo` @
`0x593E90`; DFM 9078 B @ rva `0x196A60`). Read them out of the binary rather than from here.

Method-table format (same shape as the field table, different record):
`<u16 count>` then `{<u16 entrysize><u32 addr><shortstring name>}`, `entrysize = 7 + len(name)`.
`TObject.MethodAddress` walks it by name up the class chain, so the DFM's `OnChange = GenChanged`
resolves with no address in the DFM at all.

### 9.2 `GenChanged` — one handler on every generation control

210 bytes at `0x00593670`, a `TNotifyEvent` (`eax` = form, `edx` = sender), bound 45 times in the
DFM. It does two things: ticks `GenMapRB` via `StdCtrls.TRadioButton.SetChecked` (thunk
`0x00401AB8`, `eax` = control, `dl` = bool), and writes the slider's position into the `SeaVal`
label via `Controls.TControl.SetText` (thunk `0x00401568`, `edx` = AnsiString) as a hand-built
literal with refcount −1.

⚠ **Controls fire `OnChange` while the form is STREAMING**, before the user has touched anything —
a `TScrollBar` when `Position` loads, a `TEdit` when `Text` loads. Letting that through leaves the
dialog on "New generated map" the moment it opens, inverting the default. The guard is the **last
component in the DFM**: a component is bound to its field when its `Name` is read, which precedes
its own properties, so the sentinel is nil for every event raised during loading and non-nil for
every one after. Cheaper and more certain than testing `csLoading` in `ComponentState`, whose
offset would have to be assumed.

⚠⚠ **The sentinel must also be a control that can raise nothing itself.** `IslMax` (a `TEdit`) was
tried first and fails *observably*: `TCustomEdit.CMTextChanged` calls `Change`, and its own `Text`
is streamed after its own field is bound — so it opens the guard for itself and the dialog comes up
on "New generated map". Measured live, not reasoned about. The working sentinel is `IslNote`, the
final `TLabel`; a `TLabel` has no such path.

⚠ Combos carry **both** `OnChange` and `OnClick`, because a `csDropDownList` selection change is
reported as one or the other depending on the Delphi 3 build. `GenChanged` is idempotent.

### 9.2a `GenInit` — the form's `OnShow`, because a D3 DFM cannot select a combo item

1851 bytes at `0x00593750`, restoring 21 combos. Setting `Text` on a `csDropDownList` does nothing
(Windows ignores `WM_SETTEXT` on `CBS_DROPDOWNLIST`) and `ItemIndex` is not published, so **every
dropdown opened blank with `ItemIndex` −1** — measured live on the nineteen-combo build, 0 of 19 had
a selection — and the user could not see
the defaults the cave would actually use. Reordering `Items.Strings` before `Text` in the DFM does
not help; it was tried and measured. `CB_SETCURSEL` (`0x014E`) at show time is the only route.

A combo that already has a selection is skipped, so re-opening keeps the last choice. `CB_SETCURSEL`
raises no `CBN_SELCHANGE`, so `GenInit` cannot trip `GenChanged` and move the radio.

### 9.3 Verify a property is published BEFORE putting it in a generated DFM

`TReader` rejects the **entire form** over one unknown property, so this cost two round trips:
`ItemIndex` (public, not published, on D3 `TComboBox`) and `PageSize` (arrived in D4). The check is
the VCL's own RTTI — `re_tools/rtti_props.py <TClass> [Prop ...]`, which exits 1 on a missing one
and reproduces both of those failures:

    find <u8 7=tkClass><shortstring classname>, then ClassType+ParentInfo (8 B),
    PropCount:u16, UnitName:shortstring, then TPropData: <u16 count> and per property
    26 bytes of TPropInfo followed by <shortstring name>

⚠ **26 bytes**, not 24: `PropType/GetProc/SetProc/StoredProc` (4×4) + `Index` + `Default` (2×4) +
`NameIndex` (2). D3 `TScrollBar` publishes `Kind Min Max Position LargeChange SmallChange OnChange
OnScroll` — and no `PageSize`, which is the check that would have caught it.

### 9.4 The rest of the machinery

* ⚠⚠ **Adding a dial is parametric, and two fixed-size things do not follow it on their own**
  (found 2026-09-06 adding `Hills`, the twelfth). `DIALS`, the DFM, the cave's token stream, the
  field table and `deved_bridge.DIAL_ORDER` all size themselves off `len(DIALS)`. These do not:
  - **`FORM_HEIGHT`.** The panel clips its children and the form clips the panel; eleven dials had
    already overflowed a 412-high panel, and the twelfth would have overflowed the 680-high form
    the same way. A clipped combo is simply not on screen — it raises nothing. Both are now derived
    from `len(DIALS)` (`GENPNL_TOP + GENPNL_HEIGHT + 40`).
  - **`GenInit`'s data slots.** `t_combo` holds `4 * len(combos)` bytes at a hardcoded offset. At
    eleven dials that was 80 B in an 80-B slot; the twelfth ran four bytes into `t_size`. The
    overlap assert caught it, and there is now an explicit assert with room for 40 combos.
  - **`STATE_KEYS`**, in both this script and the bridge, needs one more character. ⚠ A key's
    CHARACTER carries its meaning across a rebuild, so the NEW dial takes the unused character at
    its own slot and every existing key stays where it is: Hills went in at D10 as `'7'`, leaving
    `'S'` meaning Islands (`'IJKLMNOPQR7S'`). Re-lettering instead would silently swap two dials in
    every marker left in `Zig Modding Tools\lastgen\`.
  - ⚠⚠ **`b_fhdr` / `b_ftxt`, and the info text, are the pair that actually broke** (2026-09-06).
    `INFO_TEXT` sat at data+3100 and the OK cave's failure-marker buffers at data+4500; the twelfth
    dial's two extra lines pushed the text to 1611 bytes and it swallowed them. The corruption is
    copy-on-write in `.nmg`, so it appears only *after* a map has been generated in that session and
    is gone again on the next launch: the "Explain settings" box loses its last third. Nothing failed
    at build and nothing failed at load.
    The fix is structural — the info text goes LAST in the data area (data+4000) and everything else
    stays below it — and **`main()`'s overlap assert now walks the runtime scratch buffers as well as
    the initialised blobs**, which is what it was missing. Each `assemble_*` returns a `reserve`
    dict for that. It was proved to fire by putting `s_text` back at 3200.

⚠ **`--undo` restores the thunk's rel32 from the BACKUP, not from the `OK_BODY` constant.** So if a
later feature ever retargets `0x004034E5` as well, undoing this one silently unlinks it — the
`build_magebane.py` chain defect in a different binary. Related: `backups\AoWDevEd.exe.pre-newmapgen`
was minted 2026-08-31 and predates `build_deved_levelnav.py`'s `.tres` cave, which IS applied in the
live exe — a wholesale restore of that backup would have lost level navigation. ⚠ Moot as of
2026-09-10: **that snapshot no longer exists** (`<root>/backups/` deleted). The surgical `--undo` is
unaffected either way (16 bytes, verified) and is now the only path.

⚠ **The form is now 710 client-high, `poScreenCenter` and `bsDialog`** — about 740 outer, and not
resizable. On a work area shorter than that the bottom-aligned OK/Cancel strip goes off screen with
no way to recover it.

⚠ **The script does not verify itself while applied.** `main()` returns as soon as it sees the
retargeted thunk, so a no-argument run prints four values and never rebuilds, and `--dis` prints
nothing at all. That is a departure from the project convention ("re-running with no args verifies
current state") and it means every check of an applied build has to be made from outside the script.
The vanilla tables and DFM are all still in the file — only the three VMT slots and the resource
entry move — so a verify path is possible; it has not been written.

* **The game directory is derived at runtime** with `GetModuleFileNameA` and never baked in —
  `build_dlgdirs.py` is the patch that got this wrong (§2.1).
* **`WinExec` is not in AoWDevEd's IAT.** It is reached through `vclx30.dpl` by the rebase-delta
  idiom (§6.1): `vclx30_base = [0x004332E4] - 0x19604`, then `[vclx30_base + 0x243F8]`.
* **The editor builds the blank map first and saves it** to `Scenario\Custom\zNewMap.hsm`; the
  generator fills that file in. So the map inherits the editor's own player table and hero
  library rather than some other mapmaker's — an earlier version reused an existing map as a
  container and carried its metadata across.
* **The handoff is a fixed path**, because AoWDevEd imports no file API beyond `FileExists` — no
  read, no delete. The cave waits for `zNewMap.done` to go ABSENT then PRESENT; the bridge deletes
  it before starting, so a failed run cannot re-open the previous map and look as if it worked.
* `TApplication.ProcessMessages` was removed from the poll loop: called with a junk `Self` it
  produces "Oh dear, it's the end....". The loop is `Sleep` only.

### 9.4a ⚠⚠ Writing the blank container — the bug that made everything else look fine

**The container save was wrong from the first build and nothing said so** (found and fixed
2026-09-05, by driving the dialog rather than reading the code).

The vanilla OK body `0x004033F0` **does** build the map: `THSEngine.NewHSM(engine, 0x20011)` into
the global at `0x0043289C`, then a `TAoWNewHSMapSettings` carrying width/height (`0x30/0x40/0x60/
0x7F`) and level count, then `call [[map]+0xCC]` = `TAoWHSMap.CreateNewMap`. So a correctly sized
map exists by the time the cave regains control.

The cave then tried to save it with `call [[map]+0xAC]`. **On `TAoWHSMap` that slot is
`AddMapLevel`.** The mistake came from reading `THSMEdit.Save`'s tail —
`mov edx,[self+0x1E4]; mov eax,esi; mov ecx,[eax]; call [ecx+0xAC]` — and assuming `esi` was the
map. It is `[THSMEdit+0x1C0]`, the HSSet document object (§8's guard chain names it), which does not
exist yet inside `OKBtnClick`. `TAoWHSMap`'s VMT has **no** save method at all; `SaveGame`
`0x55775884` is the save-*game* path, with a `TSaveGameTE` token event and a seated-player check.

So no file was ever written, and the generator **silently fell back to whatever stale
`zNewMap.hsm` was on disk** — which is why an Extra Large, three-level request came back as a
64×64 single-level map, and why every earlier run looked correct only because the leftover
container happened to match.

The fix is `HSEngine.THSEngine.SaveHSM`, which writes the engine's **current** map, `engine[+0x3C]`
— verified live to be the same object as the `0x0043289C` global at that moment:

    eax = [[0x00432894]]            ; THSEngine
    bail if [eax + 0x3C] = 0        ; no current map
    push 0 / push 0                 ; progress callback + Self; ret 8, callee clears
    edx = filename AnsiString
    ecx = [0x004329C0] - 0x25C      ; IAT slot for NewHSM, which this exe imports,
    call ecx                        ; minus the fixed RVA gap to SaveHSM (same module)

A nil progress callback is safe here for the reason §8 already established: `TEStorageStream.
ShowProgress`'s Assigned guard tests only the high word of the code pointer.

⚠ **The bridge now refuses a stale container** — it compares the handoff's dimensions and level
count against what the dialog asked for and stops with `STALE CONTAINER: …` rather than generating
into the wrong file. A silent fallback is what hid this for the whole life of the feature.

### 9.4b Settings memory, and the info button

**The dialog is destroyed and rebuilt on every `File > New`** — measured, not assumed: two
consecutive opens return different `HWND`s, so the DFM is re-streamed and every default comes back.
Nothing is retained on its own.

**AoWDevEd imports exactly one file API: `SysUtils.FileExists`.** Everything else was checked and
ruled out — `TEngine.ReadTextFromFile` deserialises a `TEObject` through
`TEReadTextStorageStream` rather than reading bytes; `IniFiles`, `Registry` and `FileIntf` are
linked but only their unit initialisers are imported; there is no `CreateFile`. So the dialog cannot
*read* a settings file, only ask whether a name exists.

Hence **one empty marker file per setting**, `<game>\Zig Modding Tools\lastgen\<key><digit>`, written
by the bridge and probed by `GenInit`: 34 slots, ten probes each, all stats on one small directory.
Twenty-one combos, both radio groups, the sea percentage as three digits and the two island edits as
four right-aligned digits each — a leading zero simply has no marker, which strips it for free.
Missing markers fall through to the DFM defaults, so a fresh install needs no special case.

⚠⚠ **Every key must be distinct WITHOUT REGARD TO CASE.** The first attempt used an `abcd`/`efgh`
tail after `ABCDEFGH`, and Windows' case-insensitive filenames made the island markers answer the
terrain probes: Desert came back as the island minimum's digit and Sky as the maximum's. The keys are
now letters then digits (`A`–`Z`, `0`–`7`).

⚠ **`GenInit`'s own restore fires `GenChanged`.** `WM_SETTEXT` on a `TEdit` reaches
`CM_TEXTCHANGED → Change`, so putting the island sizes back ticked "New generated map" every time the
dialog opened. A `b_busy` byte, raised for the whole of `GenInit`, makes `GenChanged` **skip the
radio but still refresh the readout** — and since the island edits are the last thing restored, that
same event is what puts the restored sea percentage on the label. Skipping the whole handler instead
left the label reading the DFM default while the slider sat somewhere else.

⚠ The slider is restored with `SBM_SETPOS` straight at the window, which is also how the cave reads
it back, so the two always agree. Reflecting a `WM_HSCROLL(SB_THUMBPOSITION)` off the parent — the
"proper" VCL route, which would also update the control's own `FPosition` — was tried and **measured
to do nothing on Delphi 3**. Don't re-attempt it.

**The info button** (`GenInfo`, the third added method) calls `Forms.TApplication.MessageBox`
(thunk `0x00401348`; `eax`=Self, `edx`=Text, `ecx`=Caption, flags on the stack, `ret 4`).
`Forms.Application` is an imported **variable**, so its IAT slot `0x00432224` holds the address *of*
the variable and the instance is one dereference further in.

⚠ This is a deliberate exception to the house rule that generated GUIs carry controls and data only
— the user asked for it (2026-09-05). The dialog itself stays prose-free; the explanations live
behind the button.

⚠ Blob overlap in the cave's data area is **silent**: the explainer text grew into the caption
string and the message box ended "…holds the snoMap generation settings". `main()` now asserts that
no blob runs into the next.

### 9.4c The generator itself

Everything on the far side of the bridge -- the pipeline, terrain allocation, the cold direction,
mountains and their three object sizes, Sky, and the adjacency rules -- is in **`Map_Generator.md`**.
It was written here first and moved out once it outgrew a subsection of the editor file; the editor
only launches it.


---

### 9.4d ⚠⚠ A generator crash used to freeze the editor for ten minutes

Two defects, found together when an Extra Large generation died part-way:

* **`Noise._lattice` read outside its own lattice.** Domain warping deliberately samples off the
  edge of the map, and the grid is only `int(size/cell)+3` across. A sample past the right edge
  raised `IndexError`; one past the left silently wrapped to the far side through Python's negative
  indexing. Now clamped, which fixes both. 12/12 127×127 generations pass where this used to fail.
* **The cave then polled for `.done` for the full `12000 × 50 ms`** with the editor frozen and
  nothing on screen. The bridge now writes `Scenario\Custom\zNewMap.fail` on **any** failure — the
  exception arm *and* every early return, via a `main()`/`_run()` split — and the cave checks for it
  each time round the wait, so a failure comes back in one poll.

⚠ Only the exception arm wrote the marker at first; the "stale container" and "no blank map" returns
did not, which are exactly the paths most likely to fire.

### 9.5 What the automated pass proved, and what still needs a human

⚠ **This section's evidence is from the ELEVEN-dial build of 2026-09-05**, including its "46 fields
bound" count (now 47). The click-through was not re-run against the twelve-dial build; its
checklist below is still outstanding, and item 1 of it now has the info-box regression above to
check as well.

**Driven live on 2026-09-05** — the editor launched, `File > New` posted via
`re_tools/menucmd.py`, the dialog read back with `EnumChildWindows` and captured with
`re_tools/grabwin.py`, controls driven by posted messages only (`re_tools/clicker.py`'s technique:
no cursor movement, no focus steal):

* the form **loads** — no "Error reading …", 46 fields bound, 4 published methods
* opens on **"New generated map"** (the default since 2026-09-06; it was blank before), with
  every setting restored from the previous generation
* `WM_HSCROLL` ×7 on the sea slider → position 30 → 37, the **readout followed**, and the radio
  **moved to "New generated map"** by itself
* `CB_SETCURSEL` + `WM_COMMAND`/`CBN_SELCHANGE` on the Grass combo → index 2 → 4, radio moved again
* `BM_CLICK` on OK → the bridge ran with the argument vector matching the dialog exactly, and
  **the editor opened the result** — Map Settings came up showing the generator's own map name,
  `zTerra`. After the §9.4a save fix, with the handoff deleted first: the container came back
  `127x127, levels [0,1,2]` (it had been silently 64×64), 13225 land hexes, 1550 mountains,
  26 sky hexes moved off the water, 204 steppe buffering snow, and snow visibly banding the north
  edge through steppe into grass

⚠ **`BM_SETCHECK` does not select a VCL radio button.** It sets the window's state; the cave reads
the VCL's own `FChecked` at `[control+0x11D]`, which stays False, so the blank path runs and the
test looks like a broken feature. Drive a real control change and let `GenChanged` do it, or call
`TRadioButton.SetChecked`. This cost one wrong diagnosis.

⚠ This is an automated click-through, **not** the user's test — status stays `APPLIED, UNTESTED`
per the ladder. What it cannot cover, and what a real session should watch for:

1. OK on **"New blank map"** → the vanilla blank map, unchanged. (The automated pass only exercised
   the generated arm.)
2. A **real mouse** drag of the slider and real dropdown clicks, rather than posted messages.
3. Re-opening the dialog: the dropdowns should keep the previous selections, not reset.
4. Sizes other than XL, and 1- and 2-level maps — the size/level plumbing was wrong until 9.4a, so
   only XL/3 and (accidentally) M/1 have ever actually been through it.
5. Whether an XL three-level generation takes an acceptable time — the automated run took roughly a
   minute with the editor's UI frozen in the cave's poll loop, and nothing indicates progress.
6. Each cold direction, and `Random`, on a map with Snow and Desert both enabled.
7. Settings memory across an editor restart, and after a generation that fails.
8. The info button's text against what the dials actually do — it is hand-written, not derived.
7. ⚠ The title bar still reads `AoWEd [noname.hsm]` after a generated map loads, though the map and
   its name are correct. Cosmetic, unexplained, worth a look if it bothers anyone.

---

## 10. Developer > Delete Unused Heroes (`build_deved_heroprune.py`)

🔨 APPLIED, UNTESTED (2026-09-08). `AoWDevEd.exe` only — `AoWEd.exe` is out of scope by the
2026-09-07 owner ruling (patched but not shipped). `AoWz.exe`, `AoWzCompat.exe`, `AoWEPACK.dpl` and
`HSEPack.dpl` were byte-identical before and after (MD5-checked). ⚠ The live editor is
`Ziggurat\AoWzEd.exe`, built from `Ziggurat\AoWDevEd.exe` by `build_zigeditor.py` — patch the
source, then rebuild, or the change does not reach the editor you run.

**What it does.** A Developer-menu item that prunes the open map's hero roster down to
(heroes placed on the map) ∪ (leaders) and deletes the rest.
`TAoWHSMap.InitializeNewMap @0x55777590` bulk-copies the whole mapset hero library into every new
map's roster; this removes that bloat. The prune persists into the `.hsm`, because
`THeroControl.ReadWrite @0x5578A304` streams the roster under property id `0x14`.

### 10.1 The predicate is the engine's own test

```
delete iff  hero[+0x04] == 0  AND  NOT IsClass(hero, TLeader)
```

`+0x04` is `Engine.TEObject.Owner` — the container holding the hero. **One test covers on-a-tile
armies, city garrisons and exploration-site defender armies**, because all three are `TArmy`s.
Confirmed three ways: `THeroControl.ValidateLibraryHeroes @0x5578A480` frees an orphaned library
hero only under `cmp dword ptr [ebx+4],0 / jne` at `0x5578A4CB`; `TPlayer.MakeHeroEmerge
@0x55752520` and `GlobalSpells.TCallHero.FindCallHero @0x557ECBDC` select candidates the same way;
`TAbstractUnit.SetOwner @0x5577F524` is the only writer.

Dead heroes (`hero[+0x55] & 1`) and hidden ones (`hero[+0x78] != 0`) are **not** spared, and there
is no library-vs-bespoke distinction — user ruling 2026-09-08, the predicate above is the whole rule.

⚠ **`hero[+0x24]` (owner player index) is NOT a usable "in use" test.** `THero.Activate
@0x557873E8` repairs it to −1 when the owning player does not exist and `Owner == 0`, so a
predicate built on it spares genuinely unplaced heroes.

⚠ **Do not test hero-ness or leader-ness by VMT instance size** (`THero` = `0x9C`, `TLeader` =
`0xA4`) — the recorded failure in `12-re-toolchain.md`. Use `System.@IsClass`, thunk `0x00401048`,
class ref `[0x004328AC]` = `AoWE..TLeader`, exactly as the template does.

### 10.2 Template: `TMainForm.RemoveLeadersMIClick @0x0042D598`

138 bytes, a shipping bulk operation over the same list with the same `IsClass` test inverted. The
loop shape is copied verbatim: **iterate downward `count−1 → 0` and re-fetch `GetHero(hc, i)` after
the class test**, because `@IsClass` clobbers `eax` and the deletion mutates the list underneath.
Per victim:

```
call [h_vmt + 0x188]     ; THero.Deactivate -- unregisters the power source,
                         ;   removes the hero from player[+0x80]
call [h_vmt + 0x2C]      ; TAbstractUnit.Release -- refcount 1->0 -> THero.Destroy
                         ;   -> THeroControl.UnRegisterHero (guarded by hero[+0x98])
                         ;   -> heroList.RemoveChild -> Changed() -> grid refresh
```

That pair covers every back-reference. `player[+0xD4]` is never reached because leaders are
excluded; army membership cannot apply because the predicate demands `Owner == nil`. No quest or
event class resolves a hero — `THeroControl.FindID @0x5578A3D8` has exactly three callers
(`THero.Activate`, `THero.CanActivate`, `TItemTE.Execute`).

**The template's `SetOwner(nil)` (`VMT+0x08`, `edx=0`) is deliberately omitted**: the predicate
guarantees `Owner == nil` and `TAbstractUnit.SetOwner` early-outs on `cmp esi,[ebx+4] / je` at
`0x5577F52B`, so it is a provable no-op.

**Two things the cave adds to the template.** A nil check on each `GetHero` result — the roster can
hold nils, which is why `ValidateLibraryHeroes` tests `test ebx,ebx / je` before using an entry, and
`RemoveLeadersMIClick` not doing so is a latent vanilla defect. And **one** `SetModified(map)` after
the loop (thunk `0x00401FF0`, `eax = map`); `RemoveLeadersMIClick` omits it entirely — arguably a
vanilla bug, since `THeroControlGrid.DeleteHero` does it per hero.

Addresses reached, all import thunks the exe already has: `0x00401E60` `THeroControl.GetCount`,
`0x00401E58` `THeroControl.GetHero`, `0x00401048` `System.@IsClass`, `0x00401FF0`
`HSEngine.THSMap.SetModified`, `0x00401348` `Forms.TApplication.MessageBox`. The map is
`[[0x0043289C]]` (`AoWE.AoWHSMap` is an imported *variable*, so the slot holds its address — hence
the double indirection the template uses); `map[+0xF8]` is the `THeroControl`, whose list is
`[hc+0x14]`.

⚠ **`THeroControl.BeginUpdate`/`EndUpdate` are not in `AoWDevEd.exe`'s IAT** — it imports only
`GetCount`, `GetHero`, `IndexOfLibraryEx` and `UpdateLibraryHeroes`. Adding an import is far more
invasive than the grid refreshes it would save. The cave brackets the work with the map-render
pause/resume `TMainForm.DeleteHeroBtnClick @0x0042AD10` uses instead: `[Self+0x22C]` = `THSMEdit`,
guard byte `[edit+0x1BC]`, `THSMEdit` VMT `+0x90`/`+0x94`, which resolve through HSEPack's `THSMEdit`
VMT `0x55612564` to `DisplayC.TCustomDisplay.PauseFrameUpdateLoop` / `ResumeFrameUpdateLoop`.

### 10.3 The confirmation, and why the message lives on the stack

Two passes — count, prompt, delete. The prompt is `TMainForm.MsgDlg @0x0042BBE4`
(`eax=Self, edx=AnsiString, cl=3` mtConfirmation, `push buttons_word`, `push 0`, `ret 8`; returns
`ax`, `6` = mrYes) with buttons word **11** = `mbYes|mbNo|mbCancel`, the value at `[0x0042ADB0]`
that `DeleteHeroBtnClick` passes.

⭐ **With dlgtype 3 and buttons 11, `MsgDlg` matches its own constant at `[0x0042BCAC]` and takes a
Win32 path, not a VCL one**: `@LStrToPChar` → `TApplication.MessageBox` → `MessageBoxA`, with the
localised `ConfirmRStr` caption and `MB_YESNOCANCEL|MB_ICONQUESTION`. **That path never does
`LStrAsg` on the message**, so nothing can retain the pointer past the call — which is what lets the
cave build the AnsiString on its own **stack frame** (header at `[ebp-0x50]`, refcount `-1`, length
at `[ebp-0x4C]`, text at `[ebp-0x48]`) rather than claim writable memory. That matters here because
**`.ctp` is `CODE|EXECUTE|READ`, not writable**: a static buffer would have cost either a
section-characteristics change or a fresh BSS-slack allocation, for a transient 33-byte message.
Any future cave that needs a *retained* string in this section still faces that choice.

The digits are formatted with `div ebx` / push-pop, and the plural is a second literal, so the box
reads "Delete 1 unused hero?" or "Delete 12 unused heroes?". At a count of zero it shows
"No unused heroes to delete." through `TApplication.MessageBox` directly
(`eax=Application` = `[[0x00432224]]`, `edx=Text`, `ecx=Caption`, `push MB_OK|MB_ICONINFORMATION`,
`ret 4`) — a menu item that silently does nothing reads as broken. Both PChars are read-only
literals in the cave. There is no after-the-fact "deleted N" box: the count was already in the
prompt and the grid visibly shrinks.

The epilogue reloads `esp` from `ebp` **before** the `pop edi/esi/ebx`, so a stack-cleanup mismatch
at either dialog call could not restore garbage into the preserved registers.

No in-editor undo and no save-first gate — the confirmation dialog is the guard (user ruling).

### 10.4 Where it lives — `.ctp`'s tail, no new section

```
.ctp   VA 0x0052E000  file 0x00128E00  VirtualSize 0x61350 -> 0x61400  SizeOfRawData 0x61400
  0x0052E000..0x0052E05F   terrainpal's two terrain stubs
  0x0052E060..0x0052ECF3   terrainpal's 134-entry method table (3219 B) -- NOW DEAD, but --undo
                           points back at it, so it must stay byte-intact
  0x0052ECF4..0x0058E393   live TMAINFORM DFM, grown in place 0x5F644 -> 0x5F6A0 (+92)
  0x0058E3A0..0x0058E56A   PruneFreeHeroesClick, 459 B (ret at 0x58E56A)
  0x0058E56B..0x0058E56F   5 NOP alignment bytes
  0x0058E570..0x0058E5CB   5 string literals, 92 B
  0x0058E5CC..0x0058F279   relocated method table, 135 entries, 3246 B  (VMT-0x28 = 0x00425CD8)
  0x0058F27A..0x0058F3FF   390 B still free
```

`TMainForm` VMT `0x00425D00`, InstanceSize `0x6AC` (unchanged — no new fields, so no field table or
InstanceSize edit; this is a method-only relocation, unlike `build_deved_newmapgen.py`'s three-table
job). The DFM node is spliced in at blob `0x5DA7C`, immediately after `RemoveLeadersItem`, the last
child of `DeveloperItems` (Caption `&Developer`) under `MainMenu1`:

```
TMenuItem PruneFreeHeroesItem / Caption 'Delete Unused Heroes' / OnClick 'PruneFreeHeroesClick'
```

92 bytes, shaped exactly like the `RemoveLeadersItem` node beside it. No `TSpeedButton` was added to
`HeroPnl`: it is hand-packed (height 57, lowest child ends at 53) and the 640×432 dialog-resize
clamp makes geometry changes the expensive kind. A menu item is free.

**Constraints asserted on every run, before and after the write:** `SizeOfRawData` stays `0x61400`;
no later section's `PointerToRawData` moves (`.vgo`/`.pty`/`.tres`/`.nmg`); the file length is
identical; the region past the relocated table is still zero. `.ctp`'s raw data ends at file
`0x18A200`, which is *exactly* `.vgo`'s `PointerToRawData` — there is no room to grow it, which is
why the tail is the only option and why the file length is a hard invariant.

Backups are gated on a **positive** test that the file is unpatched by this feature (VMT−0x28 still
`0x0052E060`, DFM still `0x5F644`, no `PruneFreeHeroesItem`, tail all zero, VirtualSize still
`0x61350`) — not on the absence of a backup file. `--apply` over an existing install strips in
memory and rebuilds, so a re-tune never needs revert-and-reapply and never mints a second backup.
Verified: apply → re-apply is byte-identical; `--undo` restores the file to its exact pre-apply MD5.

**RNG: this feature rolls no dice.** `rng_audit.py --functions` reports
`AoWDevEd.exe: SYNC 0 site(s) / RAW 3 site(s) in 1 function` (`build_party_random.py`'s `Randomize`
+ `RandInt`) both before and after. Nobody should reach for a generator here.

Apply order: dlgdirs → modtoolbar → terrainpal → valgoto → partyrnd → timerres → levelnav →
newmapgen → toolbar_trim → heroprune. The script aborts with a chain diagnosis if `.ctp` is absent.

`build_deved_terrainpal.py --apply` after this is **safe** — its line 389 guard prints
`already patched (.ctp section present) - idempotent no-op` and returns before touching the DFM, the
method table or the section. `build_editor_toolbar.py` line 333 has the same guard on `.mtb`.

⚠ **The hazard is the inverse: terrainpal is now inert.** A future terrain-palette change means
deleting `.ctp` and re-running it, and *that deletion* destroys this feature **and**
`build_deved_toolbar_trim.py` — both live in the section terrainpal owns. Re-apply both behind it,
toolbar_trim then heroprune.

⚠ **`build_deved_toolbar_trim.py --undo` is blocked while this feature is applied.** Its line 483
computes `already = (new_blob == blob)`; this feature's 92-byte menu node makes the live DFM
`0x5F6A0` rather than the trimmed `0x5F644`, so line 494 refuses with `live blob is not the trimmed
output - refusing to undo`. That is fail-safe, not a defect — its snapshot is `0x6065C` bytes and
restoring it would write straight through the cave and the relocated method table at
`0x58E3A0..0x58F27A`. **Undo order: heroprune first, then toolbar_trim.**

### 10.5 In-editor checklist — needs the user

1. **Launch `AoWDevEd.exe` at all.** A wrong method table or a malformed DFM fails at *form load*
   (`EReadError` while streaming), and every static check above still passes. The editor opening
   is itself the proof that `PruneFreeHeroesClick` resolved.
2. Open the **Developer** menu: "Delete Unused Heroes" sits at the bottom, under "Remove Leaders".
3. With **no map open**, click it — expect nothing at all (silent, no dialog, no crash).
4. Open a map with a full hero library. Click it: expect "Delete N unused heroes?" with Yes/No/
   Cancel and the localised Confirm caption. Check N against the roster by eye.
5. Click **Cancel**, then **No** — the roster must be unchanged both times, and the map view must
   still animate (that is the pause/resume bracket having resumed).
6. Click **Yes**. The hero grid should shrink to placed heroes + leaders, redraw without artefacts,
   and the title bar should show the map as modified.
7. Click it a second time — expect "No unused heroes to delete." (MB_OK information box).
8. **Save, close, reopen the map**: the pruned roster must persist, and heroes placed on the map,
   in city garrisons and defending exploration sites must all still be there. Site defenders are
   the one worth checking deliberately — they are the least obvious `TArmy`.
9. A map with **dead or hidden** heroes in the roster: those are deleted too, by design.
10. Run a **Map Validation** pass afterwards, and start a game on the pruned map, to confirm nothing
    references a freed hero.

---

## 11. Developer > Game Settings becomes a Map Settings tab (`build_deved_gamesettings_tab.py`)

🔨 APPLIED, UNTESTED (2026-09-12). `AoWDevEd.exe` only, then `build_zigeditor.py --apply` to derive
`AoWzEd.exe`. No other binary touched; file length unchanged (1,647,104 B), no section header
changed, 212 import descriptors before and after.

The editor shipped two dialogs over the same map record: `Map Settings` (`TMapSettingsDlg`, **four**
tabs — General / Settings / Players / Diplomacy) and `Developer > Game Settings` (`TGameSettingsDlg`,
one tab). The second is now a **fifth** tab, `Game`, inside the first, and its menu item is hidden.

⚠ Count the tabs in the DFM, not from memory. `TMAPSETTINGSDLG` at file `0xC2C84` holds exactly four
`TTabSheet` nodes and `FormCreate` adds none; an earlier draft of this section said six/seven and
would have made a correct patch read as a failure against its own checklist.

⭐ **The form is REPARENTED, not rebuilt.** Nothing moves control-by-control, no DFM grows, no
RCDATA is relocated, no published field table is touched. `TGameSettingsDlg` is constructed as a
normal never-shown form owned by the Map Settings dialog; a fresh `TTabSheet` is inserted into
`MainPageControl`; the game-settings form's `ClientPnl` gets `Parent := sheet`, `Align := alClient`.
That is the whole trick, and it is the cheap way to fold any Delphi dialog into any page control.

### 11.1 Four call-retargets into one cave

Every insertion point is already a 5-byte `call rel32` whose callee has to run anyway, so the patch
is **four rewritten rel32 operands** — 4 bytes each, nothing displaced, no `E9` hook, no instruction
truncated, and (audited) no `.reloc` type-3 fixup inside any of the four operand windows, the cave,
or the global. Each cave body calls the displaced original first, so `--undo` is four dwords.

| # | site VA | file | vanilla | original callee | cave entry |
|---|---|---|---|---|---|
| 1 | `0x004230E8` | `0x224E8` | `E8 43 FE FF FF` | `0x00422F30` | `cave_build` `0x0058F280` |
| 2 | `0x00423730` | `0x22B30` | `E8 33 F5 FF FF` | `0x00422C68` | `cave_commit` `0x0058F302` |
| 3 | `0x0042315F` | `0x2255F` | `E8 DC DE FD FF` | `0x00401040` `TObject.Free` | `cave_free` `0x0058F318` |
| 4 | `0x004284B2` | `0x278B2` | `E8 91 93 FD FF` | `0x00401848` `TMenuItem.SetVisible` | `cave_menu` `0x0058F333` |

1 is the last call in `TMapSettingsDlg.FormCreate @0x00422FDC` before its SEH teardown — the DFM has
streamed, so `MainPageControl` is live, and `EAX` = Self from `0x004230E6 mov eax,edi`.
2 sits in `TMapSettingsDlg.OKBtnClick @0x004236CC` inside the VerifyRaces-succeeded branch
(`test bl,bl / je 0x423777`), `EAX` = Self, ahead of the site's own `THSMap.SetModified` at
`0x00423735`. 3 is the **third** `TObject.Free` in `TMapSettingsDlg.FormDestroy @0x00423140`
(`[ebx+0x2F8]`), `EBX` = Self. 4 is `DeveloperItems.Visible := True` in `TMainForm.FormCreate` and is
unconditional: the `ParamStr(1)` compare at `0x00428471` branches `jne 0x00428490`, and `0x00428490`
is also where the matching path falls through, so both reach `0x004284AA`.

Registers on entry are already what each cave wants, so no site needs a shim, and `EAX` is dead at
all four return points. **PIC is not required and must not be built** — `AoWDevEd.exe` is fixed-base
(`ImageBase 0x400000`, DYNAMIC_BASE clear), so absolute operands are correct; the `call $+5 / pop /
sub` anchor belongs to the rebasing `.dpl`s.

**RNG: this feature draws nothing and inherits nothing.** `rng_audit.py AoWDevEd.exe --functions`
prints `SYNC: 0` / `RAW: 3 site(s) in 1 function` (all `build_party_random.py`'s) before and after;
`TAoWHSMap.Random` is not imported by this binary at all. No pattern applies.

### 11.2 The three call mechanics worth keeping

- **A Delphi constructor's declared parameter is in ECX, not EDX** — the alloc flag occupies `DL`,
  which pushes `AOwner` one register along. Copied verbatim from the site this feature replaces,
  `TMainForm.GameSettingsClick @0x0042D3B4`:
  `mov ecx,<AOwner> / mov dl,1 / mov eax,[0x0042D9D8] / call 0x00401228`.
- **A Delphi package exports a class symbol AT the VMT address**, so an IAT slot naming a class holds
  the class reference itself — one indirection, not two. `0x00432C94` = `ComCtrls..TTabSheet` →
  `0x4135DDE8` in vcl30, which reads back as `name='TTabSheet', instsize=0x120`. `TTabSheet`
  **overrides** `Create` (its VMT+0x24 is `ComCtrls.TTabSheet.Create @0x41366B80`, not
  `Forms.TCustomForm.Create @0x41336300`), so the cave dispatches through the slot:
  `mov eax,[0x00432C94] / mov dl,1 / mov ecx,<AOwner> / call dword ptr [eax+0x24]`.
  Create is VMT+`0x24` on every Delphi 3 form class in this exe; `Destroy` is VMT−`0x04`, but the
  `TObject.Free` thunk `0x00401040` is the thing to call.
- **`ComCtrls.TTabSheet.SetPageControl` is not imported by this exe**, and import-table surgery on a
  124-byte `.idata` tail is recorded as fragile (§2, failed approaches). The **IAT-delta idiom**
  (§6.1) reaches it with no new import:
  `mov ecx,[0x00432210] / add ecx,0x000309C0` — `0x309C0 = 0x41366CC0 − 0x41336300`, both from the
  live `Ziggurat\vcl30.dpl` export table. ⚠ The script **recomputes that constant from vcl30.dpl on
  every run and asserts it equals the baked value**; it is never trusted blind. It is stable against
  `build_wheel_vclpump.py`, which retargets one 5-byte call at `0x4133BA6D` and appends caves in
  vcl30's CODE zero tail from `0x413A8A00` — neither export moves.

⚠ **`sheet.Parent := MainPageControl` is NOT a substitute for `SetPageControl`.** vcl30's `TTabSheet`
overrides `CMTextChanged, Create, CreateParams, Destroy, GetPageIndex, GetTabIndex, ReadState,
SetPageControl, SetPageIndex, SetTabVisible` — and **not** `SetParent`. `TPageControl.FPages` is only
touched by `InsertPage`/`RemovePage`, reached from `SetPageControl`. Parent alone gives a panel with
no tab. The `Game` caption is set **after** `SetPageControl` so the `CMTextChanged` override has a
page control to repaint.

### 11.3 Field offsets and why the pointer is a global

From the published field tables, not guessed:

```
TMapSettingsDlg   VMT 0x004220E8  instsize 0x300  fieldtable 0x00422168  methodtable 0x004226A1
  +0x1DC ClientPnl  +0x1E0 MainPageControl  +0x1E4 GeneralSheet  +0x1F8 SettingsSheet
  +0x204 PlayersSheet  +0x2B8 DiplomacySheet
  FormCreate 0x00422FDC  OKBtnClick 0x004236CC  FormDestroy 0x00423140
  private +0x2F4 TPlayerList  +0x2F8 TRaceList  +0x2FC TSonglist
TGameSettingsDlg  VMT 0x0042DA18  instsize 0x238  classref cell 0x0042D9D8
  +0x1DC BottomPnl  +0x1E0 ClientPnl  +0x1EC MainPageControl  +0x1F0 GeneralSheet
  published methods, all three: FormCreate 0x0042DE6C, OKBtnClick 0x0042DF2C,
  GameTypeCBChange 0x0042E158
TMainForm         VMT 0x00425D00  +0x358 DeveloperItems  +0x544 GameSettingsMI
```

⚠ `TMapSettingsDlg`'s fields run to `0x300` = its instance size, so the class has **no instance
slack**: the embedded-form pointer has to be a global, `G_GSDLG = 0x004E0520`. That is sound because
the dialog is modal and there is only ever one — its sole construction site is `0x0042A99C`, inside
the guarded opener `0x0042A960`.

⭐ `TGameSettingsDlg` has **no FormShow and no FormDestroy**, so everything it displays is seeded in
`FormCreate` — which is exactly why constructing it and never showing it works.

**Constructing it here is safe.** `TGameSettingsDlg.FormCreate @0x0042DE6C` dereferences the map at
`[[0x0043289C]]` unguarded. The opener this patch replaces guards that itself; Map Settings carries
the **same** guard and is the only way in — `0x0042A976 cmp byte ptr [esi+0x1BC],0` (a document is
open) and `0x0042A983 mov eax,[0x0043289C] / cmp dword ptr [eax],0 / je`.

### 11.4 Lifetime — correct in both directions

`Forms.TCustomForm.Destroy @0x4133659C` fires `OnDestroy` at `0x4133661C` (gated on the Assigned test
at `0x413365FE`) and only reaches `inherited Destroy` at `0x413366A7`. So `TMapSettingsDlg.FormDestroy`
— and therefore `cave_free` — runs long before any child control is torn down. **That ordering is
load-bearing**: `Controls.TWinControl.Destroy @0x4134316C` destroys every child control regardless of
ownership (loop `0x413431A5..0x413431CC`), and freeing the embedded form first means that loop never
sees `ClientPnl`. Freeing the form also runs `TComponent.DestroyComponents`, which takes `ClientPnl`
(still an owned component of the embedded form, merely re-parented) out of the tab sheet's control
list. The sheet itself is owned by Map Settings and dies with it.

Constructor failure is covered by the same path: if anything in `cave_build` raises after `G_GSDLG`
is stored, `TCustomForm.Create` destroys the half-built Map Settings form, `OnDestroy` fires, and
`cave_free` frees the embedded form and zeroes the global.

### 11.5 `TGameSettingsDlg.OKBtnClick` is called WHOLE (`0x0042DF2C`), never replicated

⚠ "call it but stop before the field-write block ends" is impossible: it installs an SEH frame at
`0x0042DF3E..0x0042DF47` torn down only at `0x0042E108`. Read end to end it is also safe from a
non-modal context — it never touches `ModalResult`, never calls `Close`/`Hide`, never reads its own
window handle or `Application`:

```
0x0042DF4A..0x0042DFDD  the eight settings -> [[0x0043289C]]+0x18C etc.
0x0042DFDE              ExtractFileExt([[0x0042F0A8]]+0x22C -> +0x1E4)
0x0042DFF9..0x0042E034  CompareText vs '.csm' (0x0042E134) then '.hsm' (0x0042E144);
                        neither matches -> jne 0x0042E101, straight to SetModified
0x0042E03A..0x0042E0FC  on a match: LStrPos('.'), copy the head into map[+0x7C],
                        GameTypeCB.ItemIndex -> map[+0x11A], re-append the extension,
                        THSMEdit.SetHSMapFilename
0x0042E101              THSMap.SetModified
```

Idempotent when Game Type is unchanged, because `FormCreate` seeds `GameTypeCB.ItemIndex :=
map[+0x11A]` first thing (`0x0042DE7A..0x0042DE86`). Note `map[+0x11A]` is written **inside** the
extension guard, so for a never-saved map whose extension is neither `.csm` nor `.hsm` the Game Type
is silently not committed — vanilla behaviour, deliberately unchanged.

### 11.6 ⚠ Inherited vanilla defect, newly reachable — NOT fixed here

`0x0042E052` uses `System.@LStrPos` (the **first** `'.'`), not a last-delimiter scan, so a map whose
**path** contains a dot is truncated: `…\maps\v1.2\foo.hsm` → `…\maps\v1.hsm`, and the truncated name
is then handed to `THSMEdit.SetHSMapFilename`, so the next Save writes there.

Measured, because it decides whether the defect can bite: **`[THSMEdit+0x1E4]` holds a full path**,
not a bare filename. `THSMEdit.LoadHSM @0x556150E4` assigns `[ebx+0x1E4] := edx` straight from its
argument and the exe hands it `TOpenDialog.FileName` verbatim (`TMainForm.OpenBtnClick @0x00429820`
→ `0x004296D4` → `LoadHSM @0x004296F8`); `THSMEdit.SaveAs @0x55614E6D` likewise stores the save
dialog's returned FileName. Only a never-saved document holds a bare name — the `'noname.hsm'`
literal `THSMEdit.Save @0x55614EE3` compares against. So any dotted directory anywhere in the map's
path triggers it. (The stock `…\Age of Wonders\Ziggurat\Save\` has none.)

It fires today on Developer > Game Settings OK; after this patch it also fires on every Map Settings
OK. Pre-existing, out of scope here.

### 11.7 Allocation, and what it costs the neighbours

```
.ctp  VA 0x0052E000  file 0x00128E00  VirtualSize = SizeOfRawData = 0x61400  chars 0x60000020
  ...0x0058F279   build_deved_heroprune.py's last byte
  0x0058F27A..0x0058F27F   6 B left alone (heroprune's alignment tail)
  0x0058F280..0x0058F3FF   384 B reserved, 216 used (199 B code + 1 pad + 16 B literal), 168 spare
.dlgd VA 0x004E0000  SizeOfRawData 0x400  VirtualSize 0x520  chars 0xE0000060 (R/W/X)
  G_GSDLG 0x004E0520, one dword
```

`.ctp` is `CODE|EXECUTE|READ` — **read-only at runtime**, which is why the one mutable dword cannot
live there. ⚠⚠ `G_GSDLG` is past `.dlgd`'s `SizeOfRawData` *and* one byte past its `VirtualSize`, so
it has **no file offset**: naive `raw + (rva − va)` arithmetic yields `0xDC720`, inside `.mtb`'s raw
data. The script's `va2off()` is bounded by `rsz`, never `max(vsz, rsz)`, and refuses the address.
The loader still commits the whole page (`.dlgd` owns `0x004E0000..0x004E0FFF`, `.mtb` starts at
`0x004E1000`) and zero-fills past the raw data, so the dword starts at 0 and `--undo` has nothing to
clear there.

The `Game` caption is a Delphi 3 immutable AnsiString in the cave — `FF FF FF FF 04 00 00 00 'Game'
00` — with `EDX` given the address of the **chars**, not the header. Same shape as the shipped
`'.csm'` at `0x0042E134`.

⚠ **`.ctp` tenancy is now four scripts.** Apply order: **terrainpal → toolbar_trim → heroprune →
gamesettings_tab.** ⚠⚠ `build_deved_heroprune.py` zeroes `.ctp`'s whole tail out to file `0x18A200`
(`zero_to = ctp_raw + ctp_rsz`) on **both `--undo` and `--apply`** — `--apply` over an
already-applied file prints `rebuilding IN PLACE (strip, then lay down again)` and calls the same
`strip()` first, so this is not an `--undo`-only hazard. Either **destroys this cave without saying
so**, and heroprune's own "the `.ctp` tail is not all zero" guard then *passes*, because `strip()`
just erased the evidence. Symptom: four `call rel32` sites pointing at zeroed memory, one of them
inside `TMainForm.FormCreate`, so `AoWzEd.exe` AVs at **startup**, not on first use. Re-run this
script and then `build_zigeditor.py --apply` behind either operation. Deleting `.ctp` to re-run
`build_deved_terrainpal.py` destroys all three later scripts the same way. heroprune had 390 spare
tail bytes; this claims 384, leaving it no growth room.

⚠ **`build_dlgdirs.py` and this script are adjacent in `.dlgd` page slack** — dlgdirs owns PATHBUF
`0x004E0400..0x004E051F`, this owns `0x004E0520..0x004E0523`. No overlap **today** only because
AoWDevEd.exe's entry in that script has `engfb=None`. Its v3 `DIRBUF_OFF = PATHBUF_OFF +
PATHBUF_SIZE = 0x520`, so giving AoWDevEd.exe an `engfb` entry would put DIRBUF's StrRec exactly on
top of `G_GSDLG`. If that ever happens, move `G_GSDLG` to `0x004E0630` or later — slack runs to
`0x004E0FFF`.

`build_deved_toolbar_trim.py` already removed `MBGameSettings` from the live toolbar (the string
survives only at file `0x1262D8`, inside the dead `.mtb` DFM), so hiding the menu item is the whole
of the entry-point removal — there is no second way in.

**Backups** are gated on a positive test that all four sites read vanilla **and** the cave is blank,
not on the absence of a backup file, and are minted on `--apply` only. Snapshot:
`<game dir>\backups\AoWDevEd.exe.pre-gstab`. Verified: apply → `--undo` restores the exact pre-apply
MD5 (0 differing bytes); apply → `--undo` → apply reproduces the post-apply MD5 byte for byte; a
second `--apply` reports `already patched and up to date - no-op`; a corrupted byte at any of the
four sites is rejected before any write.

### 11.8 In-editor checklist — needs the user

1. **Launch `AoWzEd.exe` at all.** `cave_menu` runs inside `TMainForm.FormCreate`, i.e. at form load
   — the editor opening is itself the proof that hook 4 and the menu offset are right.
2. Open the **Developer** menu: "Game Settings" must be **gone**, everything else present.
3. With no map open, **Map Settings** must still do nothing (the opener's own guard).
4. Open a map, then **Map Settings**: **five** tabs, the last named **Game**, General still selected on
   open. The Game tab's contents must fill the tab body with no OK/Cancel strip of their own
   (`BottomPnl` hidden) and no clipping at the bottom or right.
5. Every control on the Game tab must show the **current map's** values, not defaults — Game Type,
   the four spin values, the two check boxes.
6. Change something on the Game tab, click **OK** on Map Settings, reopen: the change must have
   stuck, and the other four tabs' settings must be unaffected.
7. Click **Cancel** instead: the Game tab's change must **not** be applied (`cave_commit` only runs
   in the OK path).
8. Change **Game Type** on a saved `.hsm` map and OK: the title bar / map filename must switch
   extension as it did from the old dialog, and the map must still load afterwards.
9. Open and close Map Settings **repeatedly** (ten times) — no leak, no "tab already exists", no
   duplicate Game tabs, and the editor must still close cleanly (`cave_free` zeroing `G_GSDLG`).
10. Open Map Settings, close the **map** without closing the editor, open another map, Map Settings
    again — the Game tab must show the new map's values.

---

## 12. Item Properties gains Hit Points / Movement spinners (`build_deved_itemhpmv.py`)

**🔨 APPLIED, UNTESTED (2026-09-13).** `build_item_hpmv.py` gave `TItem` two signed bonus bytes —
`item+0x4A` HP, `item+0x4B` MV, streamed as `TItem.ReadWrite` tags `0x17`/`0x18` — and nothing in
the editor could author them. This adds two rows to **Item Properties**' Statistics panel next to
ATK / DEF / DAM / RES, with the same left-hand stat icons the other four carry (§12.10).

```
target   Ziggurat\AoWDevEd.exe      -> build_zigeditor.py --apply -> AoWzEd.exe
cave     0x00599000..0x005993FF     1024 B reserved, 644 used, `.nmg` page slack
globals  0x00599000 G_FORM / +4 G_HPSPIN / +8 G_MVSPIN
dfm      TITEMEDITFORM relocated to 0x00599400 (rva 0x199400), 7487 -> 9958 B
roll     NONE — draws no random number and inherits none; the icon half injects no code
```

### 12.1 Why the controls are created at runtime

Three separate walls, each of which alone rules out the obvious DFM-clone route:

- **The DFM cannot grow.** `TITEMEDITFORM` is RCDATA at file `0x000697A8`, `0x1D3F` bytes;
  `TITEMEXPLORATIONSITEEDITFORM` starts at `0x0006B4E8`, one pad byte behind it.
- **A DFM-named `OnChange` needs a matching published method.** `TReader` rejects the *entire* form
  over one unresolvable ident, so two new handlers would mean relocating `TItemEditForm`'s published
  method table. A runtime-assigned `TMethod` needs no published slot at all — which is also why the
  dead published stub `DescriptionEditChange @0x00413B80` is not reused.
- **The load path is unrolled, not a loop.** `UpdateControls` reads the four bytes at
  `0x00413371..0x004133B2` as four hand-written sequences; there is nothing generic to name a fifth
  and sixth control into.

So: three `call rel32` **operand retargets** (4 bytes each, nothing displaced, no instruction
truncated) into one cave, plus a length-neutral DFM re-pitch that opens two rows inside the panel
that already exists.

### 12.2 The three retargets

| # | site | vanilla | goes to | context |
|---|---|---|---|---|
| A | `0x004137DC` | `E8 3B FA FF FF` | `cave_enter` | the `call UpdateControls` in `TItemEditForm.Execute @0x00413750` (view mode); EAX = Self |
| B | `0x0041389F` | `E8 78 F9 FF FF` | `cave_enter` | the `call UpdateControls` in `TItemEditForm.Edit @0x00413810` (edit mode); EAX = Self |
| C | `0x004133AE` | `E8 35 FD FE FF` | `cave_load` | the RES `call TSpin.SetValue`, last of the four unrolled loads, inside `UpdateControls` |

⚠ The other two `UpdateControls` callers — `ItemTypeBoxChange @0x00413A1D` and
`AbilityBtnClick @0x00413B6E` — are deliberately **not** retargeted. They refresh a form that
already exists; routing them through `cave_enter` would build a second set of controls on every
item-type change. They still reach `cave_load`, which is inside `UpdateControls`, so both spinners
refresh with everything else.

Audited: the base-relocation directory (10780 fixups) puts nothing in any of the three operand
windows, nothing in the cave, and nothing anywhere in `.nmg`. `AoWDevEd.exe` has ImageBase
`0x400000` and `DllCharacteristics 0`, so absolute operands are correct — PIC belongs to the
rebasing `.dpl` packages, not here.

### 12.3 The cave

- **`cave_change` `0x00599040`** — the shared `OnChange`. EAX = `TMethod.Data` = the form,
  EDX = Sender. Guards `EAX == G_FORM`, dispatches EDX against `G_HPSPIN`/`G_MVSPIN` and returns if
  it matches **neither** (never "else it must be MV"), nil-checks `[form+0x27C]`, calls
  `TSpin.GetValue`, saturates to [−128, 127] in 32 bits, stores the byte.
- **`cave_load` `0x00599093`** — runs the displaced `TSpin.SetValue(ResistanceEdit, item[0x49])`
  with EAX/EDX already loaded by vanilla, then loads `item+0x4A`/`+0x4B` into the two cached spins.
  ESI (the item) and EBX (the form) survive because `TSpin.SetValue` pushes/pops EBX and ESI and
  never touches EDI. Guards `EBX == G_FORM` before dereferencing either cached pointer.
- **`cave_enter` `0x005990C5`** — invalidates the three globals *first*, builds TLabel + TSpin
  twice against `[form+0x224]` StatisticsPnl, applies the read-only colour when `[form+0x280] != 0`,
  publishes `G_FORM`, wires both `OnChange`s **last**, and tail-jumps to `0x0041321C` with
  EAX = Self. Every failure path leaves `G_FORM = 0`, which switches the other two caves off.

⭐ **There is deliberately no "already built?" test.** `TItemEditForm` is constructed and freed per
use at all **eight** of its construction sites (`0x004203D9`, `0x00413DC0`, two in `TItemLibrary…`
around `0x00416540`, `0x00417DF0`, `0x00420A60`, `0x0042B0A0`, `0x0042B100`), each
`Create → (Edit XOR Execute) exactly once → Free`, so `cave_enter` runs exactly once per instance.
A `G_FORM == form` skip would be strictly **worse**: Delphi's heap hands back the same form address,
so it would pass on a *new* instance whose cached spins are the *freed* ones of the old. Building
unconditionally has no such failure mode — a pathological double call would stack two harmless
orphan controls that the panel frees with everything else.

### 12.4 The VCL toolkit, and the three things that are not what they look like

Everything needed is already imported by `AoWDevEd.exe`; nothing is added to `.idata`.

| what | where |
|---|---|
| `SpinEdit..TSpin` class ref | IAT `0x0043357C` (instsize `0x150`) |
| `StdCtrls..TLabel` class ref | IAT `0x00432654` (instsize `0x0C4`) |
| virtual constructor | VMT **+0x24** — **both** classes override it |
| `SetParent` | VMT **+0x3C** |
| `SetBounds` | VMT **+0x4C**; EDX = Left, ECX = Top, **push Width then Height**, callee `ret 8` |
| `TSpin.SetValue` / `GetValue` | exe thunks `0x004030E8` / `0x004030E0` |
| `TControl.SetText` / `SetColor` | exe thunks `0x00401568` / `0x004015A0` |

`TSpin` fields, read out of the class's own published RTTI: MinValue `+0x130`, MaxValue `+0x134`,
Increment `+0x138`, **EditorEnabled `+0x140`**, `OnChange` TMethod Code `+0x128` / Data `+0x12C`.

- ⚠ **EditorEnabled is `+0x140`, not `+0x120` — `+0x120` is `AutoSelect`.** Confirmed twice: the
  RTTI property table, and `TSpin.IsValidChar @0x00403279` reading `[esi+0x140]`. Both new spinners
  set it to False, matching all four DFM ones.
- ⚠ **A fresh TSpin is not the blank slate it looks like.** `TSpin.Create @0x00403034` sets
  `MaxValue := 0x0FFFFFFF` at `0x004030E0`, `Increment := 1` and `EditorEnabled := True`; only
  MinValue stays 0. Both ceilings are therefore written explicitly.
- ⚠ **`TSpin.SetValue` calls `CheckValue @0x004036EC` before setting the text**, and `SetText`
  raises `EN_CHANGE`, which fires `OnChange`, which writes the clamped number straight back. With
  `MinValue 0` a **negative** `item+0x4A`/`+0x4B` can therefore be clamped to 0 by the UI. That is
  not new: the four existing spinners have `MinValue 0` over the equally signed `+0x46..+0x49`, so
  the new pair behaves identically. Owner's call, 2026-09-13: mirror the existing four
  (`MinValue 0`, `MaxValue` 60 HP / 50 MV), no negative/cursed authoring.
- ⚠ **It does not fire merely on opening the dialog.** `cave_enter` and the first `cave_load` both
  run *before* `ShowModal`, so the spins have no window handle: `TControl.SetText` with `FHandle = 0`
  routes WM_SETTEXT to `TControl.DefaultHandler`, which raises no `EN_CHANGE`, and
  `TCustomEdit.CNCommand @0x4134FA54` additionally gates on `[eax+0x124]` (`FCreating`). The
  write-back needs a **post-show** `UpdateControls` (item-type change, ability edit) or a spin-button
  click. And `TItemEditForm.Edit @0x00413810` Assigns the working copy back only on `mrOk`
  (`dec eax / sete [ebp-1] / cmp byte [ebp-1],0 / je 0x4138F8`), so Cancel discards any clamping.

`AOwner` is **nil** for all four controls, deliberately: they are not in `form.Components`, so
`FindComponent` cannot see them and the form's `TIvTranslator` (+0x278) never touches their
captions. They are still freed — `Controls.TWinControl.Destroy @0x4134316C` destroys every child
control of StatisticsPnl regardless of ownership. ECX survives the constructor because
`System.@ClassCreate @0x41303BFC` explicitly `push edx / push ecx` … `pop ecx / pop edx` around
`NewInstance`.

### 12.5 The layout — a length-neutral DFM re-pitch

StatisticsPnl is 397×161 at (20,156) inside GeneralSheet, with its four rows on a 32 px pitch
(spins Top 24/56/88/120, Height 26). Re-pitched to a **24 px pitch with 22 px spins** — the geometry
`TUnitResourceEditForm`'s GroupBox2 already uses — rows become 16/40/64/88 and the cave places HP at
112 and MV at 136, both inside the unchanged 161 px panel. Labels sit at spin+3; icons sit at
`spin + (22 − icon height)//2`, which reproduces all six rows — H17 → spin+2, H16 → spin+3.

⭐ **All six rows go through one rule, and each icon's height is read out of the DFM rather than
listed.** Until 2026-09-13 the four existing icons' Tops were baked literals (`18/42/66/91`) while
the two new ones were derived, so a change to `ROW_PITCH` or `SPIN_H` would have moved the new pair
and silently left the old four behind. `row_y` / `label_y` / `icon_y` are now the only place any of
it is written, `HP_Y`/`MV_Y` are `row_y(4)`/`row_y(5)` rather than constants, and the script asserts
the last row still fits the 161 px panel. Deriving matters here because which icon is 16 px high is
not guessable from its bitmap (§12.10).

Sixteen `Int8` values move — Top on 4 spins / 4 labels / 4 images, Height on the 4 spins — and every
one is Int8 before **and** after, so the re-pitch itself is byte-neutral; it is written into the
**master** `.rsrc` copy at file `0x000697A8`, which never moves even after §12.10 relocates the
resource. The right-hand column (AbilityListBox 24..113, ChangeAbilities 120..147) is untouched. The
script locates the resource through the **resource directory** on every run rather than trusting a
baked offset, and re-parses the DFM asserting `consumed == len`.

### 12.6 `TItem.SetItemType`'s asymmetry is preserved on purpose

`TItem.SetItemType @0x5579457C` zeroes `+0x46..+0x49` on a type change and deliberately does **not**
zero `+0x4A/+0x4B`. So changing an item's type resets the four combat bonuses and keeps HP/MV. That
is the second reason `ItemTypeBoxChange` must not be a creation hook: it re-runs `UpdateControls`,
which reloads all six spinners, and the two new ones must show the values that survived.

### 12.7 Persistence needed nothing, and `Zig.ail` is not touched

`AoWDevEd.exe` imports AoWEPACK / EngineP / VCLADDON by bare name and runs from `Ziggurat\`, so it
loads the **patched** packages. `TItem` does not override Assign/Copy and
`Engine.TEObject.Assign @0x555191F4` is a stream round-trip, so both the dialog's Copy-edit-Assign
and the library save run through the patched `TItem.ReadWrite`; tags `0x17`/`0x18` round-trip for
free. The script writes to exactly one file. The live library remains `Ziggurat\User\Zig.ail` via
`TItemLibraryManager.ReadUserLibraries @0x55795520` (engine data root, **not** the open mapset — the
`.pfs`-location hazard does not apply here).

### 12.8 Allocation and forward hazards

`.nmg` (rva `0x193000`, chars `0xE0000060` RWX) is `build_deved_newmapgen.py`'s own section and its
raw data runs to end-of-file, which is what makes it growable. The cave sits at
`0x00599000..0x005993FF` — section offset `0x6000`, 1024 B, clear of newmapgen's body (which ends at
rva `0x198DD6`) — and the relocated DFM of §12.10 begins at `0x00599400`, immediately above it.
`--apply` sets VirtualSize *and* SizeOfRawData to `0x8C00` so both live inside the declared section
rather than relying on loader slack behaviour, exactly as `build_taskbar_icon.py` does for `.vgo`.
Because `.nmg` is RWX, the 12 mutable bytes live inside the cave span and `--undo` clears the cave in
one contiguous zero-fill.

- ⚠⚠ **`build_deved_newmapgen.py --apply` rebuilds `.nmg` in place** — `del d[exist_raw:]`, then the
  fresh body plus zero padding out to SizeOfRawData, then `VirtualSize := len(body)`. Since §12.10
  landed that no longer erases a cave and a header field; it erases **a live resource**. The
  directory entry would still point at rva `0x199400`, so **Item Properties would fail to open with
  a `TReader` error rather than merely losing its icons** — a hard failure, not a cosmetic one. Its
  `rawsz = max(exist_rawsz, …)` keeps SizeOfRawData at `0x8C00`, so the file length **and
  SizeOfImage** survive and only VirtualSize drops back to `0x5DD6`. That asymmetry is precisely the
  **damaged state** of §12.10, which `build_deved_itemhpmv.py --apply` repairs in place; follow it
  with `build_zigeditor.py --apply`.
  - ⚠ Its **`--undo` is not a hazard.** Lines 1486–1508 are surgical — the `rel32`, three VMT slots
    and its own resource entry — and explicitly leave `.nmg` alone as dead data. The earlier "behind
    any newmapgen apply *or* undo" was over-broad.
  - ⚠ And the hazard is **latent, not live**. `--apply` refuses while applied
    (`already applied (OKBtnClick -> 0x593000)`) and `--undo` requires
    `<game dir>\backups\AoWDevEd.exe.pre-newmapgen`, which does not exist. Neither half can run
    today. Recorded so a future session that recreates that snapshot knows the order — and so that
    nobody panics about a live breakage that is not one.
- ⚠⚠ **`build_editor_autosave.py` APPENDS a new PE section (`.asv`)**, and applying it to an editor
  binary would move `.nmg` off the end of the file. `.nmg` raw data ending at EOF is the invariant
  behind both newmapgen's `'.nmg is not the last section … cannot grow'` assert and this cave's
  regrow story. It is **not** applied to either editor binary today (no `.asv` in either section
  table). If it ever is, re-check both `.nmg` scripts first.
  ⚠ `grep -rl '\.nmg' build_scripts/` returns **four** files, not two: this one, newmapgen, autosave,
  and `build_deved_levelnav.py` — the last names it in prose only (its cave is `.tres @0x00592080`).
- ⚠ **`build_useitems.py` already patches `UpdateControls`**, at `0x0041349C`
  (`cmp byte [eax+0x34],6` → `0x7F`, the itUse grey-out). No byte overlap with the three operand
  windows, and it is located by signature rather than address, so the two compose — noted because
  that one function now has two owners.
- ⚠ **`build_editor_spinners.py` owns the DFM `MaxValue` ceilings on this form** (all four = 60) and
  matches owners by **substring across the whole exe**. The two new spinners are runtime-created and
  have no DFM `MaxValue`, so they are invisible to it — and must stay that way: never give a future
  DFM control on this form a name containing `HitsEdit` or `MovesEdit`.
- ⚠ **TITEMEDITFORM's DFM now exists twice in the exe** (§12.10): the dead master in `.rsrc` and the
  live copy in `.nmg`. Any whole-file DFM scanner sees both. Measured for `build_editor_spinners.py`
  after the relocation: it reports **18** sites rather than 14, the 4 extra at
  `0x19382B`/`0x1938AC`/`0x193931`/`0x1939B5`, all already at target, and patches both copies to the
  same value — so the two compose *by luck*. A future scanner that asserts a site *count* will trip.
  The full per-script inventory (who hits both copies, who hits only the live one, who hits neither)
  is in `12-re-toolchain.md`'s dead-master register.

Verified: apply → `--undo` restores the exact pre-apply MD5 (0 differing bytes, **including file
length**); `--undo` → `--apply` reproduces the post-apply MD5 byte for byte; both directions were
run twice. The snapshot (`<game dir>\backups\AoWDevEd.exe.pre-itemhpmv`) is minted on `--apply` only
and only over a file proved unpatched at all three sites, with a blank cave, an un-pitched DFM, the
resource entry still in `.rsrc` and an ungrown `.nmg`.

### 12.9 In-editor checklist — needs the user

1. **Launch `AoWzEd.exe`.** The cave runs at dialog-open, not package init, so startup is not the
   proof here — but it must still start.
2. Open an item's **Properties** (Developer > Item Library, or double-click an item on a map).
   The Statistics panel must show **six** rows: Attack / Damage / Defense / Resistance / Hit Points
   / Movement, evenly spaced, nothing clipped at the bottom of the panel and nothing overlapping the
   Abilities list on the right.
   ⚠⚠ **This is also the first proof that the relocated resource loads at all.** The form's DFM now
   comes out of `.nmg`, not `.rsrc` (§12.10) — if the relocation is wrong the dialog does not open
   and raises a `TReader` error instead. A dialog that opens *at all* clears that.
2a. **The two new rows must carry icons** in the same left column as the other four: the Hits icon
   beside Hit Points, the Moves icon beside Movement, vertically centred on their spinners like the
   existing four. They are the same two Hero Properties shows — open **Hero Properties** side by
   side and compare. ⚠ The Moves icon is a 32 px bitmap in a 17 px control, so it is **clipped on
   the right** exactly as it is on Hero Properties. That is correct, not a bug.
3. Set **Hit Points** to a non-zero value, OK, reopen — the value must come back.
4. Same for **Movement**.
5. **Save the item library** and restart the editor: both values must survive the `Zig.ail`
   round-trip (this is the `TItem.ReadWrite` tag `0x17`/`0x18` path).
6. **Change the item's Type** with HP/MV set: Attack/Defense/Damage/Resistance must reset to 0 and
   **Hit Points / Movement must keep their values** (§12.6). No duplicate spinners must appear.
7. Open an item in **view-only** mode (a library item reached from a map object — the path that
   calls `Execute` rather than `Edit`): all six spinners greyed, none editable.
8. Set an item type to the one that **hides** the Statistics panel (`item+0x34 == 5`) — the two new
   controls must disappear with the panel, not float on top of the form.
9. Open and close Item Properties **ten times in a row**: no leak, no stacking duplicate spinners,
   editor still closes cleanly.
10. Equip an item with a Hit Points bonus on a hero **in the game** (`AoWz.exe`) and confirm the
    hero's HP actually rises — the editor half and `build_item_hpmv.py`'s engine half meeting.
11. **Open the New map dialog** (File > New) once. It is the other `.nmg` tenant, and the section it
    lives in has just been regrown underneath it; its generated-map controls must still be there.

### 12.10 The two icons — art copied out of THEROEDITFORM, and a relocated resource

**🔨 APPLIED, UNTESTED (2026-09-13).** The four existing stat rows carry icons; the two new ones
did not. The art did not have to be authored — it was already in the binary.

**"Hero Properties" already holds both bitmaps**, as `TImage` children of its own stat panel:

| src `TImage` | row | file span (whole object) | `Picture.Data` payload | bitmap | control |
|---|---|---|---|---|---|
| `Image11` | Hits (`HitsLabel`) | `0x0005BC0F..0x0005BF93` | 834 B | 16×16×24, 822 B | 17×17 |
| `Image12` | Moves (`MovesLabel`) | `0x0005CDD1..0x0005D3F6` | 1506 B | **32**×15×24, 1494 B | 17×16 |

Proof they are the right siblings rather than a lookalike set: the four icons already on Item
Properties (`Image6/7/10/8`) are **byte-identical** to THEROEDITFORM's `Image9/7/10/8` — same md5
over each 834 B payload. One icon set; `Image11`/`Image12` are its HP and MV members. Both source
spans are identical in `AoWzEd.exe` at the same offsets. The script asserts the four-way twin match
before it copies anything.

Only the `Picture.Data` **property bytes** are copied (name shortstring + `0x0A` + `u32 len` +
`'TBitmap'` + `u32 gsize` + a plain `BM` DIB). Left/Top/Width/Height are re-emitted so the smallest
integer encoding is used, and the nodes are named `Image13`/`Image14` — 7 characters, exactly as
long as the sources'.

- ⚠ **`Image12` has no `Stretch` and no `Center`**, so its 32 px bitmap is **clipped** to the 17×16
  control. Copied verbatim on purpose: Item Properties then shows exactly what Hero Properties
  shows.
- ⚠ **`Image11` is the 17 px high control and `Image12` the 16 px one** — the opposite of what the
  bitmap dimensions suggest, and the easy thing to get backwards. Top is therefore derived from the
  copied Height (§12.5), giving `Image13` Top 114 and `Image14` Top 139. `Image14`'s Top does not
  fit a **signed** `vaInt8`, so it is a `vaInt16` while `Image13`'s is a `vaInt8`.

**No field-table change is needed, and this is proved by existence inside this same exe.** `Panel1`
is a TITEMEDITFORM DFM component with **no** published field on `TItemEditForm` (the field table has
`OKBtn`/`CancelBtn` but not their parent), and the form loads today: `TComponent.SetReference` →
`TObject.FieldAddress` returns nil and does nothing. So the field table stays at **40** entries and
InstanceSize at **`0x284`**; both are asserted every run and verified after apply.

**Relocating the resource.** TITEMEDITFORM cannot grow in place — RCDATA at file `0x000697A8`,
`0x1D3F` bytes, `TITEMEXPLORATIONSITEEDITFORM` starting at `0x0006B4E8`, one pad byte behind. So the
grown form is written elsewhere and the directory entry at file `0x000434E0` is repointed. Prior art
in this very binary: `TMAINFORM` already loads out of `.ctp` (rva `0x12ECF4`) and `TNEWMAPDLG` out of
`.nmg` (rva `0x196A60`). The Win32 loader returns `module base + OffsetToData`; nothing requires the
data to sit inside `.rsrc`. The `.rsrc` original is **left in place**, dead but intact — it stays the
master the grown copy is derived from, and it makes `--undo` a directory-entry rewrite rather than a
7487-byte restore.

```
                          before        after
RCDATA/TITEMEDITFORM      rva 0x6D1A8   rva 0x199400        7487 -> 9958 B  (+2471)
  Image13  (from Image11)               899 B node,  834 B Picture.Data
  Image14  (from Image12)              1572 B node, 1506 B Picture.Data
.nmg VirtualSize          0x6E00        0x8C00
.nmg SizeOfRawData        0x6E00        0x8C00
SizeOfImage               0x0019A000    0x0019C000
file length               0x00192200    0x00194000          (+0x1E00 zero bytes at EOF)
```

- ⚠ **`SizeOfImage` is an RVA-space quantity**: `align(0x193000 + 0x8C00, 0x1000) = 0x19C000`. The
  spec drafted `0x59C000`, which is that number with ImageBase folded in — writing it would declare
  a 5.8 MB image. The script re-derives both values from the section table and asserts them.
- Free zeroed space in `.nmg` before this change was `554 + 124 + 2816 = 3494 B` against the 9958 B
  needed, which is why the section had to be extended rather than just tucked into.
- Nothing is displaced. The file only gains bytes at EOF; the only in-place writes outside the cave
  are 16 DFM `Int8`s, 3 call operands, 3 PE header dwords and the 8-byte resource data entry.
  Audited: **zero** base relocations anywhere in `.rsrc` and zero anywhere in `.nmg`, so nothing can
  be stranded. `build_relocfix.py --audit` reports 0 for both editor binaries afterwards.
- The PE `CheckSum` field was already stale before any of this (`0xDE30B` stored, `0x194E35`
  computed) and Windows does not verify it for a user-mode exe, so it is left alone.
- `build_zigeditor.py --apply` still finds **exactly 8** embedded red-dragon `.ico`s: TITEMEDITFORM
  contains none (the nearest is `0x06BD5B`, past its end), so duplicating the form adds no 9th.

⚠ **`--undo` zeroes before it truncates.** The relocated DFM starts at file `0x191800`, which is
**below** the old EOF — 2560 of its bytes live inside the section's original raw data. Cutting the
file back to `0x192200` alone would leave them behind, and the "restores the exact pre-apply MD5"
claim would be false by 2560 bytes while every other check still passed.

**The `.rsrc` original is left in place, dead but intact**, and that is deliberate: it is the master
`build_new_dfm()` re-derives the live copy from on every `--apply`. Zeroing it would break
idempotency and force `--undo` to carry 7487 literal bytes instead of an 8-byte directory rewrite.
⚠⚠ The cost is that **an edit made only to the live `.nmg` copy is silently reverted by the next
`--apply`** — and the verify path would print `DRY RUN`, not name the problem. A future edit to
TITEMEDITFORM goes into the master at file `0x000697A8`, or into this script. The exe now carries
four dead DFM masters against three live relocated copies; the register and the per-script scanner
inventory are in `12-re-toolchain.md`, beside the cave-ownership table.

#### Four states, and the damaged one

| state | means |
|---|---|
| pristine | 3 calls vanilla, cave blank, DFM un-pitched, entry in `.rsrc`, `.nmg` ungrown |
| fully ours | everything installed and current — the only state that prints "chain intact" |
| **damaged** | the entry **already** points into `.nmg`, so the editor reads whatever is there, but the section is not grown / VirtualSize does not declare it / the DFM or the cave is not ours / a call site does not point at the cave. **Item Properties is broken.** `--apply` repairs it in place; `--undo` stays reachable |
| foreign | a call operand, a DFM byte or the entry holds a third value → abort |

⚠⚠ **`grown` asks only "does the *file* carry the bytes?"** — SizeOfRawData and the file length —
and `vsz_declared` asks separately whether VirtualSize covers the region. The first version required
both in one predicate (`assert grown or ungrown` over the whole quadruple), which made the
newmapgen-rebuild state unreachable by **both** `--apply` and `--undo`: the assert sat above the
`if args.undo:` block, so the binary would have been left broken with its own script refusing to act
in either direction, recoverable only from the snapshot or by hand-editing `.nmg`'s VirtualSize.
Caught by QA, 2026-09-13, and verified fixed by simulating the rebuild on the live exe: damaged →
`--undo` lands on the pre-apply MD5 and length, damaged → `--apply` lands on the post-apply MD5 and
length, and neither mints a snapshot.

---

## 13. Arrow keys move the Abilities / Spells list selection (`build_deved_listarrows.py`)

🔨 **APPLIED, UNTESTED (2026-09-14)** — `AoWDevEd.exe`, rebuilt to `AoWzEd.exe`.

In **Settings > Abilities** and **Settings > Spells**, clicking a list entry refreshed the detail
panels but UP/DOWN did nothing. Two independent defects, fixed behind separate flags
(`--part arrows` / `--part guard` / `--part both`).

### 13.1 ⭐ `TMainForm` installs an `Application.OnMessage` filter that confiscates every arrow key

**This is the reusable finding, and it reaches well past this feature.** Any future "keyboard does
nothing in the editor" report should start here rather than at the control.

`TMainForm.FormCreate` assigns `Application.OnMessage` at `0x00428630` — a Delphi method pointer, so
**two** slots: `[App+0x9c]` = Code = `0x004280DC`, `[App+0xa0]` = Data = the form. The handler:

```
004280E8  mov  eax,[ebx+4]        ; TMsg.message   (ebx = @TMsg, esi = TMainForm)
004280EB  cmp  eax,0x100 / jl  OUT
004280F2  cmp  eax,0x108 / jg  OUT        ; WM_KEYFIRST..WM_KEYLAST
004280F9  cmp  eax,0x100 / jne OUT        ; WM_KEYDOWN only
00428100  mov  eax,[ebx+8]                ; wParam = the virtual key
00428108..00428126                        ; accept VK 0x25 LEFT 0x27 RIGHT 0x26 UP 0x28 DOWN
00428128  mov  eax,[0x432220]             ; Forms.Screen     <-- .reloc HIGHLOW at 0x00428129
0042812D  mov  eax,[eax]
0042812F  cmp  esi,[eax+0x5c]             ; Screen.ActiveForm = MainForm ?   <-- HOOK HERE
00428132  jne  0x00428157
00428134  ...                             ; forward to [esi+0x22c] (HSMEdit) KeyDown,
00428154  mov  byte ptr [eax],1           ;   @CallDynaInst bx=0xFFDF, then Handled := True
00428157  pop ecx/edx/esi/ebx; ret        ; "not ours" exit -- Handled stays False
```

`TApplication.ProcessMessage` calls `OnMessage` **before** `IsKeyMsg` / `TranslateMessage` /
`DispatchMessage`, so with `Handled := True` the focused control never sees WM_KEYDOWN at all. The
four arrows are scroll commands for the map view and the form takes them globally. Nothing is wrong
with the listboxes — that is why the mouse path works perfectly and the keyboard path is inert.

⚠ **Do not hook `0x00428128`.** That 5-byte `mov eax,[0x432220]` is the obvious site and it is the
standing stale-`.reloc` trap: a type-3 HIGHLOW fixup sits at `0x00428129`, so the loader would apply
a rebase delta on top of the hook's own rel32. The only two type-3 entries in `0x428100..0x428180`
are `0x00428129` and `0x0042817C`; the window `0x0042812F..0x00428133` carries none.

**Fix:** hook `0x0042812F` (5 B, `3b 70 5c 75 23`) to a cave that lets the message through untouched
when `TMsg.hwnd` is one of the two listbox handles, and otherwise runs vanilla. `TMsg.hwnd` is
`[ebx+0]`; for a key message that is the focus window.

Scope, deliberate: the cave whitelists only the two listboxes. Comparing against `HSMEdit.Handle`
instead would be one comparison shorter and would hand the arrows back to every control on the form.

### 13.2 ⭐ No refresh code is needed — LBN_SELCHANGE → `Click` → `OnClick` is vanilla VCL

The native LISTBOX sends LBN_SELCHANGE for a keyboard move exactly as it does for a click, and
`StdCtrls.TCustomListBox.CNCommand @0x41352984` (vcl30.dpl) turns that into the OnClick handler:

```
41352987  mov  ax,[edx+6]              ; NotifyCode
4135298B  dec  ax / je 0x41352997      ; 1 = LBN_SELCHANGE
41352997  call Controls.TControl.Changed
413529A0  mov  bx,0xfff0 / call @CallDynaInst    ; = Click -> OnClick
413529AB  ..                           ; 2 = LBN_DBLCLK -> bx 0xffef = DblClick
```

So `AbilityListBoxClick @0x0042C33C` and `SpellListBoxClick @0x0042BF60` fire unchanged — the DFM
wires both as `OnClick` and the published method table carries both addresses. **One hook serves both
lists and the cave contains no refresh code.**

### 13.3 Field offsets — read from the published field table, never inferred

`TMainForm`'s field table (VMT−0x2C) is at `0x00425D92`, 305 entries:

| offset | field | notes |
|---|---|---|
| `+0x22C` | `HSMEdit` | the editor document the filter forwards to |
| `+0x240` / `+0x244` | `MORPageControl` / `SurfaceSheet` | orientation only |
| `+0x4A0` | `AbilityListBox` | class idx 19 |
| `+0x4DC` | `SpellListBox` | class idx 19 — same class |
| `+0xCC` | `TWinControl.FHandle` | from `Controls.TWinControl.GetHandle @0x41346158`: `call HandleNeeded / mov eax,[ebx+0xcc] / ret` |

⚠ A wrong offset here is **silent** — the cave simply never matches and the arrows stay dead exactly
as before. There is no crash to catch it.

### 13.4 The cave — `0x0052D640`, 57 of 96 B, in `.mtb` page slack

`AoWDevEd.exe` cannot take a 14th section (`e_lfanew` `0x100`, 13 section headers ending at exactly
`0x400`, which is where CODE's raw data begins). `.mtb` — `build_editor_toolbar.py`'s toolbar-bitmap
section — has VirtualSize `0x4C63B` against SizeOfRawData `0x4C800`, i.e. **453 bytes of slack at VA
`0x0052D63B`, verified all-zero**. The cave takes `0x0052D640..0x0052D69F`.

Entry: ESI = TMainForm, EBX = @TMsg, EAX = Screen^. EAX/ECX/EDX are dead at both resume points
(`0x00428134` reloads eax from `[ebx+0xc]`; `0x00428157` pops ecx/edx as stack discards), so the cave
clobbers them freely; ESI and EBX are preserved.

```
0052D640  3b 70 5c            cmp esi,[eax+0x5c]      ; displaced original
0052D643  75 2f               jne 0x52d674            ; another form active -> vanilla "not ours"
0052D645  8b 03               mov eax,[ebx]           ; TMsg.hwnd
0052D647  85 c0               test eax,eax
0052D649  74 24               je  0x52d66f
0052D64B  8b 96 a0 04 00 00   mov edx,[esi+0x4a0]     ; AbilityListBox
0052D651  85 d2               test edx,edx
0052D653  74 08               je  0x52d65d
0052D655  3b 82 cc 00 00 00   cmp eax,[edx+0xcc]      ; TWinControl.FHandle
0052D65B  74 17               je  0x52d674            ; ability list focused -> let the key through
0052D65D  8b 96 dc 04 00 00   mov edx,[esi+0x4dc]     ; SpellListBox
0052D663  85 d2               test edx,edx
0052D665  74 08               je  0x52d66f
0052D667  3b 82 cc 00 00 00   cmp eax,[edx+0xcc]
0052D66D  74 05               je  0x52d674            ; spell list focused -> let the key through
0052D66F  e9 c0 aa ef ff      jmp 0x428134            ; vanilla: swallow for HSMEdit
0052D674  e9 de aa ef ff      jmp 0x428157            ; vanilla: leave Handled False
```

`.mtb` VirtualSize `0x4C63B` → `0x4C800` so the cave is formally inside the section rather than
relying on the loader mapping past VirtualSize, and Characteristics `0x40000040` → `0x60000040`
(`| IMAGE_SCN_MEM_EXECUTE`) because the section is data-only as it stands. `--undo` restores both.
Raising VirtualSize cannot collide — `.mtb` RVA `0xE1000 + 0x4C800 = 0x12D800`, and `.ctp` starts at
RVA `0x12E000`; SizeOfImage is unchanged (`0x19C000`, still set by the last section). `.mtb` carries
no base relocations of its own, and the exe's fixed base `0x400000` makes the two `jmp rel32` the
cave's only absolute-ish references.

⚠ **FORWARD HAZARD:** `0x0052D640..0x0052D69F` in `.mtb` is now owned by `build_deved_listarrows.py`.
`build_editor_toolbar.py` owns the section and is a no-op once `.mtb` exists, but nothing else may
claim that window. Registered in the cave-ownership table in `12-re-toolchain.md`.

### 13.5 The second fix — `SpellListBoxClick` guards on the WRONG listbox (inherited vanilla bug)

```
0042BF84  mov  eax,[0x432898] / cmp dword ptr [eax],0 / je bail   ; map loaded?
0042BF92  8b 83 a0 04 00 00   mov  eax,[ebx+0x4a0]    ; <-- AbilityListBox. WRONG.
0042BF98  call StdCtrls.TCustomListBox.GetItemIndex
0042BF9D  inc  eax / je bail                          ; index -1 -> do nothing
0042BFA4  mov  esi,[ebx+0x4dc]                        ; ..then does its real work off SpellListBox
```

A copy-paste slip: the guard tests the ability list's selection and the body uses the spell list's,
so **the Spells panel stays blank until an ability has been selected at least once in that session**.
One byte at `0x0042BF94`: `A0` → `DC`.

⚠ `AbilityListBoxClick @0x0042C33C` has the identical idiom and it is **correct** — `0x0042C362` =
`0f 84 86 01 00 00` (map-loaded guard), `0x0042C368` = `mov eax,[esi+0x4a0]`, which is the ability
list and is what it should read. Not touched; the script asserts both bytes are unchanged.

### 13.6 In-editor checklist — needs the user

Run `Ziggurat\AoWzEd.exe` (not `AoWDevEd.exe`) with a map loaded.

1. **The editor still launches.** The cave runs on every arrow keypress, not at package init, so a
   failure here would be a section-characteristics problem (`.mtb` is now `MEM_EXECUTE`), not the
   cave logic.
2. **Settings > Abilities:** click an entry, then press UP / DOWN. The selection must move **and the
   detail panels must follow it**, exactly as clicking does.
3. **Settings > Spells:** the same. ⭐ Do this in a **fresh session without touching the Abilities tab
   first** — that is the §13.5 bug's whole signature. The panel must populate on the first click.
4. **The map view must still scroll with the arrows** when focus is anywhere else — click the map,
   press all four arrows. This is vanilla behaviour the hook must not have eaten.
5. **LEFT / RIGHT inside the two listboxes** now reach the listbox instead of scrolling the map. A
   listbox ignores them, so the expected outcome is "nothing happens" — confirm it is not something
   worse (no beep, no lost focus).
6. **Other tabs are unaffected** — Settings > anything else, and the Developer menu dialogs: arrows
   must behave exactly as before.
7. Type in any edit field on the form and confirm the arrows still move the caret as they always did
   (they were never routed through this filter — the VK test is WM_KEYDOWN-only and the ActiveForm
   gate already excluded modal dialogs).

---

## Open items

Technical opens — investigation gaps, not "please test this in-game" (each feature above that isn't yet `✅ CONFIRMED` already carries its own checklist inline).

- **`build_dlgdirs.py` v2's runtime INI-path derivation (`ensure_ini`) has never actually executed.** The 2026-07-09 automated pass validated only v1's baked-path cave, which v2 replaced outright; `ensure_ini` sits on the critical path of all 16 hooks. Check: open any of the four dialog types fresh, confirm `AoWEd_LastDirs.ini` appears at `<game dir>\AoWEd_LastDirs.ini` (not `%WINDIR%`), and that Map/Set/Text remember independently as v1 did.
- **`build_dlgdirs.py` v3's `engdir` (§2.2) has never executed either** — it is on the critical path of the two `Set` hooks in `HSEPack.dpl`. Needs `Ziggurat\AoWzEd.exe`:
  1. ⚠ **First move `Ziggurat\AoWEd_LastDirs.ini` aside, or delete its `Set=` line** — it currently reads `Set=…\Ziggurat\Release\Release.hss`, so `engdir` would run and then `seed_common` would overwrite its result with the INI value, giving a **false pass**. With no `Set=` line, **Developer > Open Mapset** must open in `<game>\Ziggurat\Release\` with `Release.hss` listed and no file preselected — *not* `<root>\Release\`, not wherever Explorer was last. This is the whole point of v3. An access violation on the first open would mean `[edi+0x24]` or `[engine+0x2C]` is wrong; the AV address to report lies in `0x5564E07D..0x5564E0CE`.
  2. Put the `Set=` line back pointing somewhere else and reopen the dialog: the INI value must still win.
  3. With no mapset open, **Save Mapset As** with no `Set=` line: the dialog must start in `<game>\Ziggurat\Release\` rather than the process CWD. With a mapset open it should still preselect that mapset's own file (`engine[+0x44]` → `FFileName` wins over `FInitialDir` — unchanged vanilla behaviour).
  4. `Map` and `Text` must be unaffected in every case — they have no engine fallback.
  5. The editor must still **launch** (the cave runs at dialog-open, not package init, so this is a low-risk check, but `engdir` dereferences `[edi+0x24]` and `[engine+0x2C]` and a wrong offset would AV on the first Open Mapset rather than at startup).
- **`build_validation_goto.py`'s level-switching branch was never exercised live** — the 2026-07-28 test map only had one level open, so `TMainForm.SetMapLevel` actually changing the displayed level (as opposed to no-op'ing because it's already correct) rode entirely on it being "the identical call `StructureGridDblClick` already makes." Check: double-click a location header referencing the *other* level on a two-level map with an underground warning, confirm the view actually switches level and recentres.
- **`build_editor_toolbar.py` has no direct user confirmation on record**, only the 2026-07-09 automated click-through. Check: a short real session exercising a handful of the new buttons, and Ctrl+S specifically from inside a text field that has keyboard focus (the automated pass drove it via a synthesized keystroke with no control focused).
- **The timerres/rendergate pair (§1.2–1.3) is explicitly "awaiting extended in-game use."** Static and automated checks all pass (no crash, map keeps animating, correct fps at every tested tuning), but nobody has actually edited a real map for an extended session at the shipped `every=16`/`skip_sleep=4`/exe-`Sleep=1` settings. Check: an ordinary editing session, watching for stutter, and Task-Manager-level CPU sanity.
- **`EngineP.dpl`'s `TECustomResourceGrid.SetResource`** (`0x5551FBB8`) has a *possible* use-after-free overwriting an occupied grid slot — flagged during the 2026-07-07 lag sweep, never patched because reachability was never demonstrated, and it's shared with the game. Check: construct a repro (assign two different resources to the same palette-grid slot in quick succession) under a debugger and watch for corruption or a crash before ever considering a patch here.

## Failed approaches — do not retry

- **Reaching un-imported kernel32 profile APIs via import-table surgery, or a hard-coded rebasing cross-DLL call target** (`build_dlgdirs.py`). Both are the obvious first move for "the module doesn't import this API"; both are fragile in ways the actual fix doesn't itself make obvious (bound-import descriptors and loader-patched OFT=0 tables for the former, the fact that every `.dpl` rebases at runtime for the latter). The VCL30-IAT-delta idiom (§6.1) needs neither.
- **A bare relative INI filename, or `GetCurrentDirectoryA`, for the per-dialog INI path** (`build_dlgdirs.py`). Both look like the obvious choice for "where's the INI"; both fail silently for non-obvious reasons — `Get/WritePrivateProfileString` resolve a directory-less name against `%WINDIR%` (empty reads, writes into `C:\Windows` or UAC virtualisation), and the SaveAs common dialog itself repoints the process's current directory on every single file pick, so a CWD-derived path would wander session to session. `ensure_ini`'s `GetModuleFileNameA`-based derivation (§2.1) sidesteps both.
- **Reusing `AoWE.FillWithRandomUnits`/`FillWithRandomUnitIndexes` for the party generator** (`build_party_random.py`). It's the engine's own, already-written random-army filler, and looks like exactly the right tool — it's budget-driven (can't produce an exact per-level count, only "spend until a value budget is reached") and its filter set is a unit-*type* set, not a race set (the nested filter calls `GetUnitType`, not `GetRace` — an easy misread the decompiler's own naming invites). `build_party_random.py` builds its own selection loop instead; the helper's only actual reuse is that a budget of exactly 1 adds exactly one unit.
- **Treating the Scanner floater and the palette resource grid as the lag's cause** (2026-07-07 lag investigation). Both are plausible first suspects for "the editor feels slow" — a floater with its own redraw loop, a grid that might reload art per cell — and both were cleanly disproven by live profiling rather than patched: the scanner's full redraw only re-arms on surface (re)creation, not every paint (idle profiling showed zero `DrawMap`/`DrawObjects` samples with it open either way), and the palette grid's tab-cycle cost is GDI-bound (`win32u` 60%) with no `ReadFile` calls at all, not disk-bound. The real cost, both times, was the 15 Hz message pump (§1.1) — patching either shared DLL would have been a real risk taken for a problem that didn't exist there.
