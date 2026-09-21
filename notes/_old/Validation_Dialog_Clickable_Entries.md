# Map Validation dialog: clickable entries (jump-to-location)

**Status: CONFIRMED WORKING (2026-07-28)** — user validated in the editor ("that's working well").
Applied 2026-07-28; automated live-drive test also passed — previously awaiting user in-game
confirmation.** Build script: `build_scripts/build_validation_goto.py` (dry-run default,
`--apply`, idempotent). Binary: `AoWDevEd.exe` only; backup `AoWDevEd.exe.pre-valgoto`;
new PE section `.vgo` (rva 0x190000 → VA 0x590000, read+exec, 365 bytes).

Double-clicking a line in the Map Validation dialog (the toolbar **Validate** speed-button,
`ValidateMapBtn`, third button on vanilla Panel2) centres the map view on the object the line
refers to, switching the displayed surface/underground level first if needed. Double-clicking an
indented `  Warning: ...` detail line walks upward to its header line; lines with no location
above them (player-level warnings, "Map validated successfully") do nothing.

## How the listing is produced (all in AoWEPACK.dpl, which is in Ghidra)

- `TMainForm.ValidateMapBtnClick` @ **0x42CEAC** (AoWDevEd.exe): creates a fresh
  `TMapValidationDlg` (classref `[0x4243F4]`), calls
  `AoWE.TAoWHSMap.ValidateMap(map=[[0x43289C]], receiver=Memo.Lines)`, `ShowModal`, `Free`.
  Dialog field **+0x1DC = Memo** (a read-only `TMemo`, `ScrollBars=ssBoth` → **no word-wrap**,
  so visual lines = logical lines); `TCustomMemo.FLines = +0x130`.
  (A second, *hidden* TMapValidationDlg singleton is auto-created at program startup into
  `[0x42F198]` — Delphi auto-create leftover, never shown; ignore it.)
- `TAoWHSMap.ValidateMap` @ 55776... broadcasts engine msg **0x20020103** to every map object;
  the message carries the receiver + a problem counter; afterwards it appends
  "Map validated successfully" / "Map validation failed!".
- `TStructure.MainValidateMap` @ **0x5575F4F8** is each structure's msg handler: it calls the
  virtual `ValidateMap(self, problemlist)` (**VMT+0x1B8**; base `TStructure.ValidateMap`
  @ 0x5575F4F4 is `return 1` — a do-nothing stub) collecting problem strings into a temp
  TStringList, and if non-empty emits:
  - header: resourcestring `%0:s at location %1:s` (file 0x294634) with %0 = name
    (VMT+0x104) and %1 = `"(" x ", " y ", " z ")"` built by `LStrCatN` from
    **GetX/GetY/GetLevel = VMT+0x74/+0x78/+0x7C** — so the `(x, y, z)` group is *always the
    last paren group* of a header line, and parens/digits survive dictionary translation;
  - then each problem line prefixed with two spaces (literal @ 0x5575F6BC).
- Known per-object validators: `City.TCity.ValidateMap` @ **0x557A96F4** (name empty or equal
  to the "Noname" resourcestring → "Warning: no name specified"),
  `Teleport.TTeleport.ValidateMap` @ **0x557A543C** (bytes +0x30/+0x31 — destination-set flags
  — either zero → "Warning: invalid location specified"), `AoWSetup.TSetupControl.ValidateMap`
  (player-level lines with **no** location header: leader skill points, missing player, etc.).
- The receiver's `+0x34` vtable slot = `TStrings.Add` — both the temp list and Memo.Lines are
  TStrings, same slot.

## The patch (AoWDevEd.exe is fixed-base 0x400000 → absolute refs are fine)

**Hook** — one call in `ValidateMapBtnClick`: `0x42CEE2: call 0x4012E8` (ShowModal thunk,
bytes `E8 01 44 FD FF`) → `call install_cave` (`E8 69 32 16 00`). At that point EAX = the
dialog.

**install cave** @ 0x590150 (29 B): `Memo := [dlg+0x1DC]`; writes `FOnDblClick`
(**TMethod: Code @ +0xAC, Data @ +0xB0** on TControl — offsets proven two ways: TMemo RTTI
GetProc `FF0000AC`, and `VCL30 TControl.DblClick @ 0x41342B48` which does
`cmp word [self+0xAE],0 ; mov edx,self ; mov eax,[self+0xB0] ; call [self+0xAC]` — note the
Assigned test only checks the **high word** of Code); restores EAX; `jmp 0x4012E8`.

**handler cave** @ 0x590000 (330 B), a TNotifyEvent (EDX = the memo; preserves ebx/esi/edi/ebp):
1. `line := Perform(memo, EM_LINEFROMCHAR(0xC9), -1, 0)` — caret = clicked line. All Perform
   calls go through AoWDevEd's own IAT slot **[0x432354]** (`Controls.TControl.Perform`,
   EAX=self EDX=msg ECX=wparam push lparam, callee-cleaned) — no HWND handling, no new imports.
2. Walk `line` upward: `EM_GETLINE(0xC4)` into a 256-byte stack buffer (capacity word 0xFE),
   scan **right-to-left** for `'('`, then parse `int , int , int )` (spaces optional, ints
   capped at 999, digits required). First line that parses wins; parse failure → `line--`.
   Right-to-left is what makes names containing parens safe: the location group is rightmost.
3. On success (x, y, z): sanity `z <= 7`, then `TMainForm.SetMapLevel(mainform, z)` — the
   unnamed method @ **0x429C68** (EAX=form EDX=level): no-ops if already displayed, else
   `THSMEdit.SetSceneLevel` + `SelectEditResource(0)` + level UI update. Its `BOUND` guard
   (0x429D78) is only shortint −128..127, hence the cap. Then
   `THSMEdit.CenterView(ctrl, x, y, z)` — import thunk **0x402E28**, EAX=ctrl EDX=x ECX=y
   push level; x/y consumed as bytes; **clamps to map edges itself**
   (GetMaxXhp/GetMaxYhp), so out-of-range coords are safe.
   `mainform = [[0x42F0A8]]`; the THSMEdit control = **mainform+0x22C**; the control's
   current-level byte = **ctrl+0x21D**.

This mirrors the editor's own precedent `TPlayerInfoFloater.StructureGridDblClick` @ 0x425BEC
(grid row object → GetX/GetY/GetLevel → SetMapLevel → CenterView) — same call sequence, ours
just gets x/y/z from the line text instead of a stored object. (That handler also calls
`TAoWHSMap.Select` to highlight the object; ours doesn't — we'd have to look the structure up
by coordinates. Possible v2 nicety.)

## Verified live (automated, 2026-07-28)

Editor driven by winspy/menucmd/clicker + `live_ui.Mem` reading `[[0x42F0A8]]+0x22C` state,
map "1Scenario/AoW Europe Heaven Games.hsm":
- patched exe launches; Validate opens the dialog through the install cave (hook runs on the
  real path);
- dblclick on a **no-location** line: no crash, level and the THSMap viewport block
  (hsmap+0x80..0xA0: pixel origin + visible hex range) untouched (only a tick counter at
  hsmap+0x40 moved);
- dblclick on an injected `Probe at location (40, 30, 0)` line: viewport block recentres;
- dblclick on an indented line *below* a header: walks up and recentres (walk-up path).
Level-*switch* (z ≠ current) wasn't exercised live (test map opened on level 0 only); it is
the identical `SetMapLevel` call StructureGridDblClick makes, so risk is low. User should
confirm once on a two-level map with an underground warning.

## Traps hit / notes for future editor caves

- **keystone has no `;` comments in Intel mode** (LLVM parser) — `asm_src()` in the build
  script strips them; the terrainpal stubs never hit this because they were comment-free.
- The Map Validation **memo is a plain TMemo** — the entries carry no object refs at all, so
  any jump feature must either parse the visible text (chosen: translation-proof, zero
  cross-module state) or hook AoWEPACK's MainValidateMap to record a side-table (rejected:
  DLL-side storage + rebasing + lifetime headaches).
- `EM_LINEFROMCHAR(-1)` after a double-click is reliable: the first click of the pair sets the
  caret; even if the edit control then word-selects, the selection start stays on the clicked
  line.
- **Validate is not a menu item** — `ValidateMapBtn` is a windowless TSpeedButton on vanilla
  Panel2 (design coords 96..135 × 4..42; automate by posting WM_LBUTTON* to the *panel*).

## Revert

`copy AoWDevEd.exe.pre-valgoto AoWDevEd.exe` — **only while it is the newest AoWDevEd.exe
backup** — it is **NOT** any more (as of 2026-07-30: coppermedal > timerres > partyrnd > valgoto >
terrainpal > modtoolbar > dlgdirs > edfps — `.pre-valgoto` is 5th of 8), so restoring it would destroy
the copper medal, the party generator and the timer patch. Run `ls -t AoWDevEd.exe.pre-* | nl` first.
Undo surgically instead: restore the 5 bytes
`E8 01 44 FD FF` at file offset of VA 0x42CEE2 and zero the `.vgo` body — the dead section
header is harmless.
