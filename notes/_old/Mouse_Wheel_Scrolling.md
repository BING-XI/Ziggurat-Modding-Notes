# Mouse-wheel scrolling — SPEC (aow-pm, 2026-09-02) — NOT BUILT

**Status: SPEC, handed to `aow-coder` 2026-09-02. Decisions taken by the user 2026-09-02:** D1 = foreground + under-cursor gating; D2 = scrollbar-less memos INERT; D3 = his defaults (3 lines/notch, slider step 5, wheel-up = previous); D4 = build BOTH extensions now; D5 = separate WH_MOUSE editor hook, PIC rewrite. Nothing is confirmed in-game yet. When built and confirmed
in-game, this file is rewritten as the feature doc (cave/global tables, contract header, gates,
do-not-try list, apply/undo order) per the recording convention.

Investigation + address-transfer verification: `Modding Resources/Inioch/share1/Inioch_MouseWheel_VCL30.md`.

TRACK: **BINARY** — `aowInt.dpl` + `vcl30.dpl` (the on-disk name is lowercase `vcl30.dpl`).
**No exe is patched**, so there is no AoWCompat lockstep step: the exe addresses the caves carry
(`0x416D0C/0x416D54`, and for (C) `0x42BF40/0x40ABF0/0x40AC9C`) are runtime comparison constants
against method pointers that are byte-identical in `AoW.exe` and `AoWCompat.exe`.

Ghidra holds `AoWEPACK.dpl` only and no wheel site lives there. Everything below was verified from the
live files with `re_tools/pescan.py`, `dasm.py` and aowInt's own export table.

## PRIOR ART

| file | gives us |
|---|---|
| `Modding Resources/Inioch/share1/Inioch_MouseWheel_VCL30.md` | architecture, measurements, full address-transfer verification (2026-09-02) |
| `Modding Resources/Inioch/share5/memory/mouse-wheel-scrolling.md` | design record rounds 1–4, all field offsets, the level-up parallel-list wiring |
| `Modding Resources/Inioch/share5/patch scripts/build_wheel_aowint.py` | foundation half 1 (hover latches + `WheelScroll`), reference implementation, PIC |
| `Modding Resources/Inioch/share5/patch scripts/build_wheel_vcl_pump.py` | foundation half 2 (pump hook + `WH_MOUSE_LL` owner thread), reference, PIC |
| `Modding Resources/Inioch/share5/patch scripts/wheel_probe.py` | live counter reader for `--diag` builds — port to `re_tools/` |
| `Modding Resources/Inioch/share3/mouse_wheel_scrolling_patch.py` + `Mouse Wheel Scrolling.md` | editor Win32-scrollbar half (WH_MOUSE at `TApplication.Run`). **Not PIC** — see (B) |
| `Modding Resources/Inioch/share4/patch scripts/build_wheel_power_slider.py`, `build_memo_wheel_inert.py` | extensions (C) |
| `build_scripts/build_memo_clamp.py` | **already applied** (2026-08-28, untested), in place inside `TAOWMemo.SetListOff @0x59819298` at `+0x13..+0x22` — verified live (`7c 03 89 c6 4e 85 f6 79 02 31 f6 90…`). `WheelScroll` calls the function ENTRY, so it passes through the clamp: this is what makes case 3 (memo with no scrollbar) safe on an empty memo (Count−1 = −1) and on scroll-up (−3). |
| `build_scripts/build_invis_penalty.py`, `build_sitedefender_vary.py` | the in-place-rewrite and surgical `--undo` models to copy |

Never run any Inioch script: same target filenames, `GAME` resolved one level up.

## DO NOT TRY (recorded failures)

1. **WH_MOUSE (thread hook) for in-game delivery** — installed at `TApplication.Run` it never fires in
   the game process (his MessageBox diagnostic; §5 of share1). Reason: the game receives **zero
   `WM_MOUSEWHEEL`** — the render window is never the focused window, so no queue/WndProc/thread-hook
   design can see the wheel. Only `WH_MOUSE_LL` sees it.
2. **Owning the `WH_MOUSE_LL` hook on the game thread** (his rounds 1–3) — ~1000 callbacks/s from a
   gaming mouse serviced by the render thread = frame-rate loss + cursor ghosting;
   install-only-while-hovering only mitigated it. The dedicated owner thread (round 4) is the fix,
   not a nicety.
3. **Driving a parallel-list listbox directly** — the level-up columns have `[lb+0x118] == 0`;
   scrolling the hovered list moves one column and leaves the cost column + thumb behind. Drive the
   governing sibling `TAOWVScrollBar` so the form's `OnChange` syncs everything.
4. **Signature-byte coupling** — gating the pump on `WheelScroll`'s first byte silently killed
   scrolling when the prologue changed. Replaced by an explicit contract header (below).
5. **Absolute IAT references in a DPL cave** — his share3 blob is `ff 15 <abs>` / `push 0x413A8400`;
   a rebased `vcl30.dpl` would crash at `Run`. Every DPL cave here must use the `call $+5; pop; sub`
   delta.

## Re-verified by the PM (beyond share1 §4)

- `vcl30.dpl` sections: `CODE 0x41301000 (R+X)`, `DATA 0x413E1000 (RW, raw 0xDFE00)`,
  `.idata 0x413E4000 (RW — C0000040, so `.idata`-slack globals are legal)`. CODE zero tail
  `0x413A8307..0x413E0A00` (231,161 B); caves `0x413A8400..0x413A9000` all zero; DATA slack
  `0x413E27D4..0x413E2800` and `.idata` slack `0x413E713C..0x413E7200` all zero; no `.reloc` entry in
  any hook site, cave or slack range.
- `ProcessMessage` frame (dasm): `add esp,-0x20; push 1/0/0/0; lea eax,[esp+0x14]; push eax;
  call PeekMessageA; test eax,eax; je …; mov bl,1; cmp dword [esp+8],0x12 @0x4133BA6D; je 0x4133BAEC`.
  TMsg at `[esp+4]`: hwnd `+4`, message `+8`, wParam `+0xC`. The hook site is reached **only when a
  message was retrieved** — hence the WM_NULL wake-up is load-bearing. `Run` prologue
  `55 8B EC 51 89 45 FC` with an instruction boundary at `Run+7 = 0x4133BCA3`.
- Every IAT slot both halves use resolves by name; `CreateThread` has two slots (`0x413E41E8`,
  `0x413E4434`), both valid. Additionally imported, needed by the new gates:
  `GetCurrentProcessId 0x413E43EC`, `GetForegroundWindow 0x413E47C0`,
  `GetWindowThreadProcessId 0x413E4744`, `GetCursorPos 0x413E47DC`, `WindowFromPoint 0x413E45FC`.
  **No import-table surgery anywhere.** (`PostThreadMessageA` is not imported — stay with `PostMessageA`.)
- `aowInt.dpl`: CODE content ends `0x598227C7`, zero to `0x5983D200`; DATA slack
  `0x5983E024..0x5983E200` all zero; all six hook sites carry the expected vanilla bytes and are
  exported-symbol-resolvable (`TAOWHScrollBar.CheckMouseMove @0x5981FA5C`,
  `TAOWButton.CheckMouseMove @0x59811808` are true entries with `55 8B EC 51 53`); the proposed ranges
  `0x59824000..0x59826000` and `0x5983E040..0x5983E100` are zero and reloc-free. Verify-before-write
  must compare **our** sites only.
- `AoW.exe` published method tables (VMT scan): `TLeaderSetupWin.FacePrevBtnClick 0x416D0C /
  FaceNextBtnClick 0x416D54`, `TPowerDlg.PowerSliderChange 0x42BF40`,
  `TUnitWindow.PPrevClick 0x40ABF0 / PNextClick 0x40AC9C`,
  `THeroUpgradeDlg.AvailableAbilitiesSBChange 0x447030` (entry now `E9` into
  `build_herodlg_columns.py`'s `cave_sbchange` — entry address preserved, which is all the
  sibling-search needs). So the share4 extension addresses transfer too.
- Which processes load `vcl30.dpl`: `AoW.exe`, `AoWCompat.exe`, `AoWDevEd.exe`, `AoWEd.exe` only.
  `AoWSetup.exe`, `Launcher.exe`, `mld_conv.exe`, `unins000.exe` import nothing from it and contain no
  `vcl30` string, so they cannot be affected. ⚠ **CORRECTED 2026-09-02 (QA):** the two editors import
  **23** symbols from `aowInt.dpl`, **including the `AOWWinManager..TAOWWinManager` VMT** — so H1/CLR
  DOES run in both editors. The earlier "2 non-toolkit symbols, latches can never arm" claim was
  false. The five latch-setting classes (`TAOWListBox`, `TAOWMemo`, `TAOWImage`, `TAOWButton`,
  `TAOWHScrollBar`) are absent from the editors' import list, but `AoWDialogForm` / `AoWWinGeneric`
  could instantiate them *intra-module*, which an import table cannot see. **So G1 ("no editor spins
  up the LL thread") and "no double-scroll in the editor" are UNPROVEN, not established.**
  Falsifying measurement: run `AoWDevEd.exe`, hover its lists, then
  `python "Modding Resources/re_tools/wheel_probe.py"` — `G_THREADED` must read 0.

## APPROACH

Port his round-4 stack with four changes: fresh aowInt cave/global addresses (collision rule), a
self-describing cross-file contract (replaces the signature byte), explicit gating so the LL hook
exists only where it is needed and never swallows another application's wheel, and a PIC rewrite of
the editor half.

**Contract header** — aowInt `VA 0x59824000` (RVA `0x24000`), 32 bytes of constants in CODE:

```
+00 dd 0x48575A41   magic "AZWH"
+04 dd 0x00010000   version: hi word = major (pump requires == 1)
+08 dd 0x0003E040   RVA of the latch block
+0C dd 8            latch count (dwords)
+10 dd 0x00024200   helper slot 0 = WheelScroll
+14 dd 0            helper slot 1 (extension: WheelPower)
+18 dd 0            helper slot 2 (extension: WheelUnit)
+1C dd 0            helper slot 3 (spare)
```

Helper ABI: `stdcall(delta)`, `ret 4`, `eax = 1` handled / `0` not; preserves ebx/esi/edi/ebp; may
call any UI code (it runs on the game thread inside `ProcessMessage`). The vcl30 half hard-codes
**one** aowInt RVA (`0x24000`) plus magic/major; changing any helper's prologue can no longer break
anything. Runtime rule: magic missing or major ≠ 1 → the pump never creates the thread and never calls
anything (fail-safe); build-time rule: both scripts' no-arg run opens **both** files and prints the
chain state (fail-loud).

**Gates** (the two behaviour differences in our install):

- **G1 lazy thread creation**: the pump creates the `WH_MOUSE_LL` owner thread the first time it sees
  (header valid AND any latch ≠ 0). The editors never arm a latch (2 aowInt imports, no toolkit), so
  no editor ever spins up the system-wide hook; the game does so the first time the cursor enters a
  list.
- **G2 LL proc arming** — queue + wake + swallow only if ALL hold, in this order: `nCode == 0`,
  `wParam == WM_MOUSEWHEEL`, `G_AOWBASE` valid and header magic present, any latch ≠ 0,
  `GetWindowThreadProcessId(GetForegroundWindow()) → pid == G_PID`, and
  `GetWindowThreadProcessId(WindowFromPoint(GetCursorPos())) → pid == G_PID`. Otherwise
  `CallNextHookEx` — never swallowed. Use `GetCursorPos`, **not** `MSLLHOOKSTRUCT.pt`: the hook point
  is physical pixels while a DPI-unaware Delphi 3 process sees logical ones, so mixing them with
  `WindowFromPoint` fails at any scaling ≠ 100 %. These calls run only on wheel events, not on the
  ~1000/s move events, so the perf fix is untouched. `WindowFromPoint` sends `WM_NCHITTEST` only to
  windows of the calling thread; the owner thread owns none, so no cross-thread wait.
- G3 (his, kept): the CLR hook zeroes the whole 8-dword latch block at the start of every move sweep.
- G4 (**not in v1**, fallback only): zero latches + `G_PENDING` on `WM_ACTIVATEAPP(wParam=0)` in the
  pump if in-game tests show stale-latch scrolling.

**Pump drain** (small improvement, same contract): `G_PENDING` accumulates raw deltas; the pump takes
`n = G_PENDING / 120` (toward zero), `lock sub`s `n*120` back, and calls the helper slots in order
once per notch (|n| capped at 8). His sign-only single step over-scrolls on touchpads/free-spin wheels
that post many sub-120 deltas. Also refresh `G_HWND` from every non-zero `msg.hwnd` (his captures the
first one forever; if that window dies the wake-up post fails silently and "wheel while still" stops
working mid-session).

No dice anywhere: no RNG generator question arises; `rng_audit.py --owners` must show no new site.

### Address plan

**aowInt.dpl** (ImageBase `0x59800000`; CODE file = VA − `0x59800C00`; DATA file = VA − `0x59801A00`;
scripts should use a section-aware `va2off` like `build_memo_clamp.py`).

Hooks (all reloc-free, bytes verified live):

| id | site | steal | patch | resume |
|---|---|---|---|---|
| H1 CLR | `TAOWWinManager.CheckMouseMove` entry `0x59807094` | 6 B `55 8B EC 83 C4 F4` | `E9 rel32 90` | `0x5980709A` |
| H2 SET | `TAOWListBox.CheckMouseMove+0x7D` = `0x598175C5` (ebx = listbox, inside-branch) | 7 B `C7 43 78 FF FF FF FF` | `E9 rel32 90 90` | `0x598175CC` |
| H3 SET2 | `TAOWMemo.CheckMouseMove+0x9A` = `0x5981A29A` (ebx = memo) | 7 B same | `E9 rel32 90 90` | `0x5981A2A1` |
| H4 SET3 | `TAOWImage.CheckMouseMove+0x6A` = `0x59815882` (ebx = image) | 6 B `8A 83 C0 00 00 00` | `E9 rel32 90` | `0x59815888` |

Caves (all inside the verified-zero, reloc-free run; budgets asserted at build time; positions are
free to move since only the header and rel32 reference them):

| VA | budget | contents |
|---|---|---|
| `0x59824000` | 0x40 | contract header |
| `0x59824040` | 0x80 | CLR: `pushad; delta→edi; lea edi,[edi+0x5983E040]; xor eax,eax; mov ecx,8; rep stosd; popad;` stolen 6 B; `jmp 0x5980709A` |
| `0x598240C0` | 0x40 | SET: `push eax; delta→eax; mov [eax+0x5983E040],ebx; pop eax;` stolen 7 B; jmp |
| `0x59824100` | 0x40 | SET2: same, memo |
| `0x59824140` | 0xC0 | SET3: his ≤3-level parent climb over `[+0x10C]`→`[+0xD0]` children, `TAOWButton` VMT `0x59810DC0` match, `[btn+0x138]` == `0x416D54`/`0x416D0C` → latch `[1]`/`[2]` |
| `0x59824200` | 0x200 | `WheelScroll` — his three cases verbatim (VMT classify listbox `0x59815F9C` / memo `0x5981848C`; case 1 `[lb+0x118]`/`[memo+0x120]`; case 2 sibling `TAOWVScrollBar` `0x5980C594` search with vertical overlap, nearest at/right of the list's left; case 3 `SetListOff`); `SetFPos 0x5980CA28`, `TAOWListBox.Update 0x59817138` / `SetListOff 0x598168F4`, `TAOWMemo.Update 0x59819B18` / `SetListOff 0x59819298`; OnChange via `[sb+0x6C]/[+0x6E]/[+0x70]`, portrait fallback via `[btn+0x138]/[+0x13A]/[+0x13C]`. `LINES = 3`. Build flag `MEMO_NEEDS_SCROLLBAR` (decision D2) selects whether a scrollbar-less memo takes case 3 or returns 0 |
| `0x59824400..0x598247FF` | 1 KB | reserved for (C) |

Do not touch: `0x59822800..` (`build_glowboost.py` CAVE1/CAVE2, unapplied), `0x59823000..0x59823200`
(`build_bltprobe.py`, unapplied); leave `0x59823200..0x59823FFF` empty so his reference addresses
never alias ours.

DATA slack allocation (record this table in the doc):

| range | owner |
|---|---|
| `0x5983E024..0x5983E03F` | unallocated |
| `0x5983E040..0x5983E05F` | wheel latch block: `[0]` g_hover `[1]` g_facenext `[2]` g_faceprev `[3]` g_pslider (C) `[4]` g_unext (C) `[5]` g_uprev (C) `[6]` g_uarmed (C) `[7]` spare |
| `0x5983E060..0x5983E0BF` | wheel `--diag` counters (24 dwords) |
| `0x5983E0C0..0x5983E0FF` | spare |
| `0x5983E100..0x5983E1FF` | `build_bltprobe.py` scratch — never touch |

**vcl30.dpl** (ImageBase `0x41300000`; CODE file = VA − `0x41300C00`; DATA file = VA − `0x41301200`;
`.idata` file = VA − `0x41302A00`).

| id | site | steal | patch |
|---|---|---|---|
| H5 PUMP (A) | `Forms.TApplication.ProcessMessage+0x25` = `0x4133BA6D` | 5 B `83 7C 24 08 12` | `E8 rel32` (call); cave ends `cmp dword [esp+0xC],0x12; ret` so the `je @0x4133BA72` still sees the flags |
| H6 RUN (B) | `Forms.TApplication.Run` entry `0x4133BC9C` | 7 B `55 8B EC 51 89 45 FC` | `E9 rel32 90 90`; cave replays the 7 B and `jmp 0x4133BCA3` |

Caves: (B) `0x413A8400` MouseProc (1 KB budget), `0x413A8800` installer (0x200); (A) `0x413A8A00`
pump (0x100), `0x413A8B00` LL proc (0x100), `0x413A8C00` owner thread (0x100). Free from `0x413A8D00`.

Globals (`.idata` slack, RW, zero): `G_PENDING 0x413E7140`, `G_HWND 0x413E7144`,
`G_THREADED 0x413E7148`, `G_PID 0x413E714C` (set **before** `CreateThread`), `G_AOWBASE 0x413E7150`
(0 unresolved / −1 absent so `GetModuleHandleA` is not called per message forever in an aowInt-less
process), `G_HHOOK 0x413E7154`; `0x413E7158..0x413E717F` spare; `--diag` counters
`0x413E7180..0x413E71FF`. DATA slack `0x413E27D4..0x413E27FF` stays unused ((B) needs no global).

IAT slots, all reached as `call [reg+slot]` with `reg` = load delta: (A) `GetModuleHandleA 0x413E43BC`,
`CreateThread 0x413E41E8`, `GetCurrentProcessId 0x413E43EC`, `SetWindowsHookExA 0x413E463C`,
`CallNextHookEx 0x413E4894`, `PostMessageA 0x413E46C8`, `PeekMessageA 0x413E46CC`,
`WaitMessage 0x413E4604`, `GetForegroundWindow 0x413E47C0`, `GetWindowThreadProcessId 0x413E4744`,
`GetCursorPos 0x413E47DC`, `WindowFromPoint 0x413E45FC`. (B) `GetCurrentThreadId 0x413E43E8`,
`SetWindowsHookExA`, `WindowFromPoint`, `GetWindowLongA 0x413E4758`, `GetParent 0x413E4784`,
`SendMessageA 0x413E468C`, `CallNextHookEx`, `GetKeyState 0x413E47B4`. Owner thread:
`SetWindowsHookExA(WH_MOUSE_LL=14, LL cave, hMod = delta+0x41300000, 0)` then `WaitMessage` /
`PeekMessageA(PM_REMOVE)` drain forever; it no longer needs `GetModuleHandleA` (the pump resolves the
base before the thread exists). The only string in any cave is the leaf `"aowInt.dpl"` (pump cave),
NUL-preceded.

## AS BUILT — QA 2026-09-02 (applied, UNTESTED in game)

The address plan below is the *spec*; these are the **built** addresses where they differ, all
verified sound (no overlap, budgets respected, zero-fill past each cave):

- **vcl30 caves grew and moved** — `PUMP 0x413A8A00` (316 B / 0x180), `LL 0x413A8B80` (274 B / 0x180),
  `TH 0x413A8D00` (79 B / 0x80). The spec's 0x100 budgets were too small once the G2 gates went in.
  Editor caves `MouseProc 0x413A8400` (337 B / 0x400) and `installer 0x413A8800` (50 B / 0x200) run
  contiguously up to 0x413A8A00; free from 0x413A8D4F.
- **aowInt**: `WheelScroll` is 442 B in its 0x200 budget, ending 0x598243BA — 70 B clear of the
  extension zone. Header slots 1–2 hold 0x24540 / 0x245C0 (the built extensions), not zero.
- `--undo` round-trip proven byte-identical both ways (full-file diff against `aowInt.dpl.pre-wheel`
  and `vcl30.dpl.pre-wheelpump`, then re-applied to the same hashes). `build_wheel_aowint.py --undo`
  correctly refuses while the extension half is installed.

**Open findings that need an in-game answer or a decision:**

1. ⚠ **G1 unproven** — see the corrected editor-import note above.
2. ⚠ **Stale-pointer window** — `WheelScroll` (`call [edi+0x138]`), `WheelPower` (`call [edi+0x6c]`)
   and `WheelUnit` (`call [esi+0x138]`) call through a latched object pointer whose only invalidation
   is the next mouse-move sweep (G3, in `TAOWWinManager.CheckMouseMove`). If a window is destroyed and
   the user wheels **before any further sweep**, these call through freed memory. G4 covers alt-tab,
   not destruction. Probe: close a dialog by keyboard without moving the mouse, then wheel.
3. **H7/SLD latches the power slider with no hover test** — at function *entry*, before any bounds
   test, so latch[3] means "the Power dialog is open", not "the cursor is on the bar". A notch
   anywhere over the game moves the slider by 5, and the LL hook arms for the whole window while that
   dialog is open. Deliberate per the ext docstring; **make it an explicit decision or add a hover
   test.** (H8/BTN by contrast does require the cursor inside its zone.)
4. **`rng_audit.py` does not audit `vcl30.dpl`**, so the standing check does not cover the five vcl30
   caves. QA read every branch by hand: only IAT calls, intra-cave rel32, one `call eax` to the aowInt
   helper, and the delta `call $+5` — **no RNG draw of either kind**. That half is a hand-check, not
   the tool's.

**Environment traps found on the way** (worth keeping):

- ⚠ `grep -i -F` **aborts on this machine** (rc 134) and silently returns nothing — a collision sweep
  reported "no owner" for all 25 addresses because of it. `grep -rl` and `grep -rlaF` both work.
- `pescan.py iatrefs` reports the *sibling* `CreateThread` slot (0x413E4434) rather than the
  FirstThunk entry the caves use (0x413E41E8). Both are valid imports; resolve IAT slots by name from
  the import table, not by `iatrefs`, before trusting one.
- `re_tools/__pycache__/*.pyc` carries the profile path again (regenerates on every script run) —
  the mandatory pre-share `find … -name '*.pyc' -delete` still applies. Everything else scanned clean,
  including all four `.pre-wheel*` backups.

## DELIVERABLES (ordered)

**(A) Foundation — build first.**

1. `build_scripts/build_wheel_aowint.py` — H1–H4, header, CLR/SET/SET2/SET3/WheelScroll, latch block,
   `--diag`. Inert alone. Backup `aowInt.dpl.pre-wheel`. `--undo`: restore the four sites' exact
   bytes, zero `0x59824000..0x59824400` and `0x5983E040..0x5983E0BF`; **refuses** while header slots
   1–3 or `0x59824400..0x59824800` are non-zero ("undo build_wheel_ext.py first").
2. `build_scripts/build_wheel_vclpump.py` — H5, pump/LL/thread caves, globals. Backup
   `vcl30.dpl.pre-wheelpump`. `--undo`: restore 5 B, zero `0x413A8A00..0x413A8D00` and
   `0x413E7140..0x413E7200`.
3. `re_tools/wheel_probe.py` — port of his: module base + RVA via the process module list (pattern in
   `read_bltprobe.py`), prints the counter block with his "reading the numbers" table extended for the
   new gates (`gated: unarmed / foreground / under-cursor`).
   Apply order: 1 then 2 (callee first — a convention, both halves are inert alone by construction).
   Undo order: 2 then 1. Both files are locked while any of the four importers runs; the standing
   kill list covers exactly them.

**(B) Editor Win32 scrollbars — second, independent of (A).**

4. `build_scripts/build_wheel_editor.py` — H6 + PIC rewrite (keystone) of the share3 algorithm:
   `MouseProc(nCode,wParam,lParam)`; passthrough unless `nCode==0 && wParam==0x20A`;
   `delta = (short)[MOUSEHOOKSTRUCTEX+0x16]`; `WindowFromPoint(pt)`; primary axis = horizontal iff
   `GetKeyState(VK_SHIFT)&0x8000` else vertical; `FIND(mask)` walks the `GetParent` chain testing
   `GetWindowLongA(GWL_STYLE)` against `WS_VSCROLL 0x200000` / `WS_HSCROLL 0x100000`, primary then
   secondary; found → 3× `SendMessageA(hwnd, WM_VSCROLL 0x115 / WM_HSCROLL 0x114,
   delta>0 ? SB_LINEUP 0 : SB_LINEDOWN 1, 0)` + `SB_ENDSCROLL 8`, return 1 (swallow); else
   `CallNextHookEx`. Installer: `SetWindowsHookExA(WH_MOUSE=7, MouseProc, 0, GetCurrentThreadId())`.
   Backup `vcl30.dpl.pre-wheeleditor`; `--undo` restores 7 B and zeroes `0x413A8400..0x413A8A00`.
   Inert in the game (proven never fires); in the editor, if it swallows a wheel first the pump never
   sees it, and (A) never arms there — no double-scroll either way.

**(C) Extensions — after the user confirms (A), and only per decisions D3/D4.**

5. `build_scripts/build_wheel_ext.py` (aowInt only — vcl30 untouched, because the LL proc ORs the
   whole latch block and the pump iterates the header slots): H7 `TAOWHScrollBar.CheckMouseMove` entry
   `0x5981FA5C` steal `55 8B EC 51 53` → SLD cave `0x59824400` (latch `[3]` when
   `[sb+0x6C] == 0x42BF40`); H8 `TAOWButton.CheckMouseMove` entry `0x59811808` same steal → BTN cave
   `0x59824440` (latch `[4]/[5]` on `PNextClick 0x40AC9C`/`PPrevClick 0x40ABF0`, preview-zone test
   from the buttons' own rects → `[6]`); `WheelPower 0x59824540` (`SetFPos ±5`, fire OnChange) into
   header slot 1; `WheelUnit 0x598245C0` into slot 2. Backup `aowInt.dpl.pre-wheelext`; `--undo`
   restores H7/H8, zeroes its caves, slots 1–2 and latches 3–6. Requires (A) present (asserts the
   header).
6. Memo-inert is **not** a separate script: it is the `MEMO_NEEDS_SCROLLBAR` flag in script 1 (his
   1-byte `je` retarget becomes a build-time branch), re-applied in place.

**Docs — last, after in-game confirmation:** rewrite this file as the feature doc (cave/global
allocation tables above, contract header, gates, the five DO-NOT-TRY items, apply/undo order), index
rows, and the share1 §6 deferral note.

## USER DECISIONS

- **D1 gating** — G1+G2 as above; confirm, or drop the under-cursor half of G2 (keeping only
  foreground-process) for fewer moving parts.
- **D2 scrollbar-less memos** (city-view text boxes): inert (his ruling) or scroll-with-clamp (safe
  since `build_memo_clamp.py`)? Default: inert.
- **D3 tunables**: 3 lines per notch, power-slider step 5, wheel-up = previous face/unit. Defaults
  from his build.
- **D4 scope of (C)**: power slider, unit-window cycling, both, or neither now. Recommend: neither
  until (A)+(B) are confirmed.
- **D5 (B)**: port faithfully (recommended) vs fold editor handling into the pump cave (possible — the
  editor's queue does carry `WM_MOUSEWHEEL` — but a redesign of a user-confirmed mechanism, and it
  would couple (B)'s undo to (A)'s).

## UNKNOWNS (measure, with which tool)

- U1 Our level-up dialog is the 5-column rebuild (`HeroUpgradeDlg_Categories_Design.md`): name list
  126 px, cost list at +123, bar 17 px overlaying the cost list's right edge, all in `UpgradePnl`; the
  nearest-at/right heuristic picks each list's own bar (dx 152 / 29) and rejects bars of earlier
  columns (negative dx). But his walk uses `[ctrl+0x10C]`→`[+0xD0]` while our docs record the parent
  at `+0xCC` (`live_ui.py`, herodlg memory) — likely two different fields (owning `AOWWindow` vs
  Parent). Confirm with `re_tools/live_ui.py` on the open dialog that the five `TAOWVScrollBar`s sit
  in the `[+0xD0]` list of the object at `[list+0x10C]`; if not, case 2 never fires and the columns
  desync (his pre-fix symptom).
- U2 Display scaling on the test machine: G2's under-cursor check is the only DPI-sensitive piece;
  the `--diag` counter `gated: under-cursor` distinguishes "never arms" from "arms but nothing
  scrolls".
- U3 `build_unitwin_ability.py` rebuilt `TUnitWindow`: for (C) confirm `T2Memo` is still a `TAOWMemo`
  child and PNext/PPrev still exist (handlers verified; geometry is read at runtime so the zone
  self-adjusts).
- U4 Whether the game thread receives `WM_ACTIVATEAPP` — only if G4 is ever needed.

## ACCEPTANCE (checkable without launching the game)

- Each script with no args prints hook-site state (`vanilla` / `applied` / `foreign`), cave state,
  and — for scripts 1 and 2 — the cross-file chain verdict (`complete` / `aowInt half only, inert` /
  `vcl30 half only, inert`) after reading both files; `foreign` at any site aborts.
- Dry-run by default; `--apply` idempotent (second run reports "already applied", no write);
  verify-before-write compares exact bytes at the hook sites and asserts every cave/global zone is
  all-zero or already our exact blob.
- Byte checks after apply: `0x4133BA6D` = `E8` + rel32 to `0x413A8A00`; `0x59807094` = `E9` + rel32
  to `0x59824040` + `90`; `0x598175C5`/`0x5981A29A` = `E9` rel32 `90 90`; `0x59815882` = `E9` rel32
  `90`; header dwords at `0x59824000` =
  `41 5A 57 48 | 00 00 01 00 | 40 E0 03 00 | 08 00 00 00 | 00 42 02 00 | 0 | 0 | 0`;
  (B) `0x4133BC9C` = `E9` rel32 `90 90`.
- `--dis` (capstone) of every cave reviewed: no `push imm8` where an imm32 was intended (keystone
  trap); every cave ends with the displaced bytes + a `jmp`/`ret` to the recorded resume address; the
  pump cave's tail is exactly `83 7C 24 0C 12 C3`.
- PIC scan of every DPL cave: no `[imm32]` memory operand, no `call/jmp` to an absolute address, no
  `push imm32` of a `0x413…`/`0x598…` VA. Allowed imm32 module VAs: the `sub reg,imm32` immediately
  after the delta `pop`, `lea reg,[reg+VMT]` displacements, and the exe handler constants
  (`0x416D0C/0x416D54`, (C) `0x42BF40/0x40ABF0/0x40AC9C`).
- `.reloc` scan reports zero entries inside every displaced range and every cave/global range, in
  both files.
- No drive-letter absolute path (`[A-Za-z]:\`) anywhere in any cave extent; `aowInt.dpl` occurs
  exactly once in vcl30's caves, preceded by NUL; `grep -rlaF "$USERNAME"` over `build_scripts/` and
  both binaries is clean; `GAME` resolved two levels up / `AOW_GAME_DIR`.
- `--undo` round-trip (each script, and the pair in order 2→1): hook bytes byte-identical to the
  pre-apply bytes, own cave and global zones all-zero, no other byte of either file changed
  (full-file diff against the feature backup for the first apply, since `vcl30.dpl` is pristine
  today); script 1's `--undo` refuses while extension slots/caves are non-zero.
- Feature backups written once: `aowInt.dpl.pre-wheel`, `vcl30.dpl.pre-wheelpump`,
  `vcl30.dpl.pre-wheeleditor`, (C) `aowInt.dpl.pre-wheelext`; `vcl30.dpl.pre-wheelpump`
  byte-identical to today's untouched `vcl30.dpl`.
- `rng_audit.py --owners` output unchanged (no cave calls either generator).
- Both binaries still parse (`pescan.py`), sections/sizes unchanged, and `build_memo_clamp.py` with
  no args still reports `applied`.

## IN-GAME (only the user can confirm)

- Map-select / load-game list, hero level-up columns, leader-setup lists, unit-window description
  tab, magic-window lists and the events log all scroll under the wheel; on the level-up dialog the
  cost column and the scrollbar thumb move with the name column.
- Leader-setup: wheel over the portrait cycles faces (up = previous).
- A wheel notch with the mouse perfectly still scrolls (wake-up post works), including late in a
  session after dialogs have opened and closed.
- No frame-rate dip or cursor lag with a high-report-rate mouse, in menus and on the map.
- Alt-tab to another application and wheel there: not swallowed. With the game in the foreground,
  wheel over another window floating on top of it: not swallowed.
- Scrolling up past the top of a memo pins at line 0 with no "Exception during Draw" (memo clamp).
- Editor (`AoWDevEd.exe`): lists, treeviews, scroll boxes scroll; Shift+wheel scrolls horizontally
  where a horizontal bar exists; no double-scroll.
- `AoWEd.exe` and `AoWDevEd.exe` start normally (AoWSetup.exe does not load `vcl30.dpl`, so it is
  unaffected by construction).
- (C) if built: power-distribution slider moves 5 per notch with labels updating; unit-window
  preview zone cycles units.
