# What actually dominates an AoWDevEd frame (measured 2026-07-28)

**Answer: two `Sleep(1)` calls that Windows rounds up to ~15.6 ms each.** Not rendering, not GDI,
not the map.

**Status 2026-07-28 — two patches, applied and measured, coupled (see the coupling warning below):**

| Patch | Binary / backup / section | Setting |
|---|---|---|
| `build_editor_timerres.py` | `AoWDevEd.exe` / `.pre-timerres` / `.tres` | `timeBeginPeriod(1)` + frame `--sleep 1` |
| `build_editor_rendergate.py` | `HSEPack.dpl` / `.pre-rendergate` / `.rgt` | `--every 16 --skip-sleep 4` |

Net effect, maximised 2180×1210, all samples foreground-validated:
**29.2% CPU / 14.0 ms p50 / 14.9 ms p95 → 5.2% / 6.4 ms / 7.6 ms** (5.6× less CPU, 2.2× better
p50, 2× better p95), map animation ~11 fps. Verified the map still animates and the editor UI
still works; **awaiting extended in-game use for final confirmation.**

## The measurement chain

Starting point: every editor dialog opens in ~24-31 ms steps, and
`SendMessageTimeout(WM_NULL)` to the main window took **31 ms round-trip while completely idle**.

1. **UI-thread-only profile** (`re_tools/sampler.py --window <hwnd>`, added this session — without
   it the histogram is swamped by eight idle worker threads all sitting in `NtWaitForSingleObject`):
   76% of the UI thread was in `ntdll!ZwDelayExecution`, 18% in `win32u!NtGdiStretchDIBitsInternal`,
   and only ~4% in any AoW module.
2. EIP alone can't say *who* called a kernel stub, so `re_tools/stack_prof.py` (new) samples the UI
   thread **and scans the stack at ESP** for return addresses inside known AoW modules. That gave
   the attribution:

   | Share of UI thread | Frame |
   |---|---|
   | 41.9% | `HSEPack!HSMEdit.THSMEdit.UpdateFrame+0xe` ← `DCPACK!TUpdateFrameThread.TriggerUpdateFrame` |
   | 34.2% | `AoWDevEd!TMainForm.HSMEditUpdateFrame+0x2e` |
   | 17.3% | `GFXEPACK!GFXE.TDIB16Surface.BltDC` (the `StretchDIBits` map blit) |
   | ~5% | everything else (sprite grabbing, visibility, sorting) |

3. Both of those first two return addresses are **the instruction after a `Sleep` call**:
   - `HSMEdit.THSMEdit.UpdateFrame` @ **0x55614904**: `push 1 / call Sleep` at +0x9
   - `TMainForm.HSMEditUpdateFrame` @ **0x428D18**: `push 1 / call Sleep` at +0x29
4. **No AoW module imports `timeBeginPeriod`** (checked AoWDevEd.exe, HSEPack, DCPACK, GFXEPACK,
   ILPACK, AoWEPACK, EngineP, AoW.exe), so the process runs at Windows' default **15.625 ms** timer
   granularity and each `Sleep(1)` really sleeps ~15.6 ms. 2 × 15.625 = **31.25 ms**, against a
   measured pump period of 31.0-31.5 ms.
5. Proven before writing any patch by injecting the fix into the running editor with
   `CreateRemoteThread(winmm!timeBeginPeriod, 1)`: the pump period dropped **31.5 → 8.0 ms**
   instantly with nothing else changed.

### Why the old FrameRate lever stopped working

`build_editor_framerate.py` (2026-07-07) fixed the *original* lag by raising the map view's DFM
`FrameRate` 15 → 60; it is now **120** on this install. FrameRate cannot pace below the `Sleep`
floor, so raising it further buys exactly nothing — the floor is the timer granularity.
⚠ That script also writes to a hard-coded `.rsrc` offset which the DFM relocations done by
`build_editor_toolbar.py` (`.mtb`) and `build_deved_terrainpal.py` (`.ctp`) have since made **dead
data** — the live `FrameRate` lives in the DFM the TMAINFORM resource entry actually points at.
Re-running it today would silently patch nothing.

## The patch

`timeBeginPeriod(1)` once, on the first `Sleep` call. Implementation:

- The exe's kernel32 `Sleep` **import thunk** at **0x4013C8** (`jmp dword ptr [0x4322A0]`,
  `ff25a0224300`) becomes `jmp cave` + `nop`. The cave does a one-time init (guarded by a flag in
  `.tres`, which is R/W/X) and tail-jumps to the real `Sleep` with the caller's stack untouched, so
  no startup hook is needed and every later call costs one compare. `pushad`/`popad` around the
  init keeps it invisible to the caller.
- AoWDevEd.exe imports neither `LoadLibraryA` nor `GetProcAddress`, so the cave reaches them
  through **VCL30.dpl's IAT** — the same trick `build_dlgdirs.py` uses for the profile APIs:
  `vcl_delta = [0x432210] - 0x41336300` (the exe's slot for `Forms.TCustomForm.Create`, preferred
  VA VCL30 base + 0x36300), then `LoadLibraryA = [0x413E4360 + vcl_delta]`,
  `GetProcAddress = [0x413E43B4 + vcl_delta]`.
  ⚠ **Deliberately not** derived from winmm's own export RVAs. GFXEPACK imports `timeGetTime`, so
  winmm's runtime base *is* reachable that way — but baking winmm export RVAs into the patch would
  turn any Windows servicing update into a crash.

### The catch, and the knob

An accurate timer makes `Sleep(1)` really 1 ms, so the loop **free-runs** — it blits the whole map
~125×/second for nothing. Idle CPU is essentially `per-frame work / period`, and per-frame work is
~4 ms (mostly that `StretchDIBits`). Measured by toggling the timer inside one live process:

| Configuration | Pump period | Idle CPU |
|---|---|---|
| stock (15.6 ms timer, `Sleep(1)`) | 31.0 ms | 13.6% of a core |
| 1 ms timer, `Sleep(1)` — free-running | 8.1 ms | ~55% |
| **1 ms timer, `Sleep(8)` (the default)** | **15.1 ms** | **27.2%** |

So the frame budget has to be put back by hand: `--sleep N` patches the `push 1` imm8 at
**0x428D3F** (`TMainForm.HSMEditUpdateFrame+0x29`). Default 8 → roughly twice the responsiveness
for roughly twice the idle CPU. HSEPack's own `Sleep(1)` still adds ~1 ms and is left alone (that
DLL is shared with `AoWEd.exe`). Lower N for a snappier editor on a desktop, raise it on a laptop.

Verified after applying: pump 15.1 ms, map renders correctly, the Party generator dialog opens
(click → visible **99 ms → 47 ms**).

## Is the whole view redrawn needlessly every frame? NO — tested 2026-07-28

The obvious reading of the numbers above is "it repaints the entire field of view constantly for no
reason". **That is wrong, and the dirty-rectangle pipeline works.** Idle CPU at a *fixed* 1100×800
window:

| Content in view | Idle CPU |
|---|---|
| **blank new map (48×48, surface only, no objects)** | **0.6%** |
| loaded map, open ocean | 9.7% |
| loaded map, dense land (cities/forest) | 12.8% |

A blank map fills the same viewport with terrain and costs essentially nothing. So the per-frame
cost tracks **animated content**, not the mere existence of a viewport: with nothing dynamic on
screen, no blt rects get registered (`GFXE.RegisterBltRect`) and the presentation step blits
nothing. `THSMEdit.UpdateFrame`'s `BuildDynamicScene` and `THSMap.ResetVisibleDynamicHS` /
`TMapField.CopyDynamicVisibleHS` walk the **visible** fields, which is why the cost looks
area-proportional (the earlier area sweep: 2.64 Mpx → 35%, 0.11 Mpx → 3.1%, minimised → 1.9%).

The reason it *looks* like a blind full-screen repaint on a real map is that on a populated AoW map
essentially every visible hex has something animating — water shimmers, city flags wave, units
idle — so the dirty region genuinely is the whole view, every frame. There is no waste to reclaim.

⚠ Do not "fix" this by hunting for a missing dirty check. `TCustomDisplay.UpdateFrame`
(DCPACK 0x5510597C) does run unconditionally and its only guard is a null test on the display
object at `[self+0x1A8]` — that looks like the smoking gun and is not: the actual gating lives
deeper, in the virtual present at `[displayctx+0x70]`, driven by the registered rect list. The
blank-map measurement is the proof. (This is a different question from the 2026-07-07 "scanner
perpetual redraw" claim, which was about `TScanner` in AoWTools.dpl and was separately disproven —
don't conflate the two.)

## The CPU/latency trade-off, measured (2026-07-28, maximised 2180×1210 = 2.64 Mpx)

Sweeping the frame-loop `Sleep` imm8 at **0x428D40** live (VirtualProtectEx + write) with the
timer-resolution patch in place:

| frame `Sleep` | idle CPU | pump latency |
|---|---|---|
| 8 ms (current default) | 27.2% | 14.5 ms |
| 12 ms | 22.2% | 18.7 ms |
| 16 ms | 21.2% | 23.0 ms |
| 20 ms | 16.9% | 26.5 ms |
| 25 ms | 15.3% | 32.8 ms |
| 33 ms | 11.6% | 39.9 ms |
| 50 ms | 6.9% | 56.8 ms |

The model is exactly `latency ≈ Sleep + 6.5 ms` and `CPU ≈ 6.5 / (Sleep + 6.5)`: the render costs
**~6.5 ms** and runs on **every** loop iteration. At the default the editor is animating the map at
~70 fps, which no map editor needs — that is what the 27% buys.

### ⚠ FrameRate is NOT a render throttle — lowering it makes BOTH worse

`SetFrameRate` (DCPACK **0x55104B08**) writes the published property at `+0x174` **and** the derived
frame interval `round(1000/fps)` at **`+0x178`**; the loop paces off `+0x178`. (Writing only `+0x174`
does nothing — that produced a flat, meaningless first sweep. Mimic the setter: write both.)
Sweeping it live, maximised:

| FrameRate | idle CPU | pump latency |
|---|---|---|
| 120 (current) | 27–30% | 14 ms |
| 60 | 42% | 17 ms |
| 30 | 70% | 33 ms |
| 20 | 83% | 50 ms |
| 12 | 88% | 83 ms |
| 150 – 1000 | 28–33% (flat) | 14 ms (flat) |

So **lower FrameRate costs more CPU and more latency**, and above ~120 the knob is inert because
`Sleep(8)` governs. This retires the idea (stated in earlier drafts of this doc) that FrameRate could
be used to decouple render rate from pump rate — it cannot, and turning it *down* to save CPU is
exactly backwards. `build_editor_framerate.py --fps` should only ever be used to raise it, and it is
already at its useful maximum.

⚠ That script also patches the **dead** `.rsrc` copy of the DFM at a hard-coded offset; the live
TMAINFORM DFM has been relocated to `.ctp` by `build_deved_terrainpal.py`. Re-running it silently
edits nothing that matters. The live value happens to already be 120.

## ⚠ MEASUREMENT HAZARD: the editor self-throttles when it is not the foreground window

`THSMEdit.UpdateFrame` gates on `[esi+0x1bc]`, so an inactive editor idles at **~1-3% CPU with
~31 ms pump latency no matter how anything is tuned**. A whole tuning sweep silently drifted into
the background and produced beautiful, meaningless numbers (every config "1-3% CPU"). **Verify
foreground per sample** — `GetWindowThreadProcessId(GetForegroundWindow())` — and discard samples
that fail.

Worse, you cannot fix it from the harness: Windows' foreground lock defeats `SetForegroundWindow`
(even with `AttachThreadInput`) *and* `SwitchToThisWindow` from a background script. The reliable
route is to **relaunch the editor**, since a freshly launched process gets foreground rights; then
run the whole sweep in that one session with per-sample validation.

## Breaking the trade-off — BUILT 2026-07-28 (`build_editor_rendergate.py`)

`HSEPack.dpl` gains a `.rgt` section that renders only every Nth loop pass while the loop keeps
pumping every pass. Backup `HSEPack.dpl.pre-rendergate`; defaults `--every 10 --skip-sleep 4`.
Measured maximised (2180×1210), sweeping the live-tunable state dwords:

| every | skip sleep | idle CPU | latency p50 | p95 | ~map fps |
|---|---|---|---|---|---|
| 1 (vanilla) | 8 | 28.7% | 15.0 ms | 16.3 ms | ~70 |
| 2 | 8 | 21.2% | 14.2 ms | 15.6 ms | ~55 |
| 6 | 8 | 11.6% | 10.4 ms | 15.7 ms | ~18 |
| 6 | 4 | 13.1% | 0.1 ms | 16.0 ms | ~33 |
| 10 | 4 | 9.7% | 6.4 ms | 16.2 ms | ~22 |
| 16 | 4 | 3.4% | 10.4 ms | 15.2 ms | ~14 |

### Round 2: the exe's `Sleep(8)` was the p95

Note the p95 pinned at ~15-16 ms in every row above. Once the gate paces the loop, the exe's
`Sleep(8)` inside `TMainForm.HSMEditUpdateFrame` no longer paces anything — it only pads the
**render** pass, and that pass sets the worst case. Dropping it to 1
(`build_editor_timerres.py --sleep 1`) roughly halves p95. Full sweep, all samples
foreground-validated, maximised 2180×1210:

| exe Sleep | every | skip | CPU | p50 | p95 |
|---|---|---|---|---|---|
| 8 | 1 (gate off) | 8 | 29.2% | 14.0 ms | 14.9 ms |
| 8 | 10 | 4 | 7.6% | 6.2 ms | 14.8 ms |
| 1 | 10 | 4 | 9.9% | 6.5 ms | 8.2 ms |
| **1** | **16** | **4** | **5.2%** | **6.4 ms** | **7.6 ms** ← shipped |
| 1 | 24 | 4 | 5.5% | 5.5 ms | 7.3 ms |
| 1 | 24 | 6 | 3.4% | 8.5 ms | 9.1 ms |
| 1 | 30 | 8 | 3.4% | 10.4 ms | 11.0 ms |

Shipped default is **exe Sleep 1 + every 16 + skip 4**: **5.2% CPU, 6.4 ms p50, 7.6 ms p95**,
~11 fps map animation. Against untouched vanilla that is **5.6× less CPU, 2.2× better p50 and
2× better p95**. Push to `--every 24 --skip-sleep 6` for 3.4% if choppier water is acceptable.

⚠ **The two patches are now coupled.** `exe Sleep = 1` is only safe *with* the render gate — the
gate's `skip_sleep` is what paces the loop. Reverting `HSEPack.dpl.pre-rendergate` without also
restoring the exe to `--sleep 8` leaves a hot loop rendering at ~117 fps. Revert both, or neither.

With exe Sleep = 1 the render passes come round sooner, so an equivalent render rate needs a
larger `every` than it did at Sleep(8) — that is why the default moved 10 → 16.

### Round 1 sweep (exe Sleep still 8)

**3× less CPU and ~2× lower latency simultaneously** — it beats every point on the Sleep-only
curve above on both axes. Verified still correct: the map keeps animating at every tested setting
(8/8 distinct frames over 2 s at every=1, 10 and 24), and the toolbar → modal-dialog path still
works under the gate.

⚠ Don't push `skip_sleep` to 2 expecting more: passes then run ~500×/s and the per-pass overhead
(prologue + `Sleep` syscall) costs ~25% on its own — measured 27–30% CPU at skip=2 regardless of
`every`. 4 ms is the knee.

### Two traps this build hit

1. **Skipping to the function's own early-exit (0x55614C27) is not enough.** That label still runs
   `call TCustomDisplay.UpdateFrame` (0x55614C29), which performs the present. First attempt got
   only 35% → 22.5% and a profile still showing 27% in `NtGdiStretchDIBitsInternal`. The skip path
   must jump to the **epilogue at 0x55614C2E**. The blank-map "present with nothing dirty is free"
   result does *not* generalise to this path.
2. **keystone parses `add eax, <const> - Label` as a MEMORY operand** (`add eax, dword ptr [...]`),
   silently producing a pointer read instead of an adjustment. Compute call/pop deltas in Python
   and emit a literal; the script asserts the cave prologue is `push/push/call` so the delta stays
   valid.

## Original design notes (superseded by the build above)

The only way to get low CPU *and* low latency is to stop rendering on every loop iteration: pump at
~8 ms but render every Nth pass. Projected from the model, N=5 gives ~14% CPU at ~8–14 ms latency,
versus ~40 ms latency for the same 14% on the table above.

The gate has to go in **HSEPack.dpl**, not the exe: `THSMEdit.UpdateFrame` (0x55614904) is reached
only through its VMT slot (`THSMEdit+0xAC`), and `TMainForm.HSMEditUpdateFrame` is just the exe's
`OnUpdateFrame` event — gating the exe side skips the status-bar work, not the rendering. The
natural gate is right after the `Sleep(1)` at 0x55614912, branching to the function's **existing**
early-exit at 0x55614C27; the skip path must still sleep, or the loop free-runs (the exe handler's
`Sleep(8)` lives inside the region being skipped). Costs: a position-independent cave plus writable
counter state in HSEPack (it rebases), and HSEPack is shared with AoW.exe — though `THSMEdit` is
editor-only, so the game never executes it.

## If more is ever wanted

The floor is therefore the ~4 ms software `GFXE.TDIB16Surface.BltDC` → `StretchDIBits` of whatever
is dirty, which on a real map is the full 2195×1225 view. Since the work is legitimate, the only
levers are making the blit itself cheaper or shrinking the view. Note DCPACK ships both a
`TDDrawDC` (DirectDraw) and a `TWindows16DC`/DIB path, and the editor is on the **software DIB
path** — moving its windowed map view onto DirectDraw is the plausible big win, and a much larger
change than anything here.

## Measurement traps banked here

- `sampler.py` without `--tid`/`--window` is useless for this: idle worker threads dominate.
- EIP-only sampling can't attribute kernel waits; use `stack_prof.py`.
- `PrintWindow` (what `grabwin.py` uses) repaints synchronously into your DC, so it can neither show
  what is on screen nor when it got there. An early "paint progress" measurement built on it
  reported a bogus ~800 ms that was entirely instrument overhead.
- Timer resolution is **per-process** on Win10 2004+. `NtQueryTimerResolution` reported 1.000 ms
  (another app had raised it system-wide) while the editor was still getting 15.6 ms — so the
  system-wide number tells you nothing about the target, and calling `timeBeginPeriod` in *your*
  process does not speed up *theirs*. Test by injecting into the target.

## Revert

~~`copy AoWDevEd.exe.pre-timerres AoWDevEd.exe`~~ — that condition ("**only while it is the newest
AoWDevEd backup**") **no longer holds as of 2026-07-30**: `.pre-coppermedal` has since been layered on
top, so `.pre-timerres` is 7th of 8 and restoring it would destroy the copper-medal work.
Verify with `ls -t AoWDevEd.exe.pre-* | nl`.

**Undo surgically instead** (the documented path, still correct): restore `ff25a0224300` at 0x4013C8,
put `01` back at 0x428D40, and zero `.tres`.
