# AoW1 native GUI toolkit — reference (from the combat-log scout, 2026-07-16)

**The combat log was built and confirmed working; the implementation record is
`Combat_Log_Implementation_Design.md`.** This file keeps only the scout findings that stay reusable
for ANY future GUI mod — the route deliberation, effort estimates and staged plan are gone (route A,
clone-the-chat-window, is what got built).

## 1. The UI toolkit — `aowInt.dpl` (base 0x59800000)
Full retained-mode custom UI: `TAOWWindow/TAOWGenericWindow/TAOWBaseWindow`, `TAOWWinManager`
(Draw/Update/CheckKey*/CheckMouse*), `TAOWPanel/Button/CheckBox/ComboBox/Edit/Image/Label/Menu/TabPanel/
ToolTip/Gauge`, scrollbars, and three scrollable text controls:
- **`TAOWListBox`** — `Create/Draw/SetFStrings/SetIndex/SetListOff/SetVScroll/SetSize/SetVisible/Update/Validate`
- **`TAOWMemo`** — same pattern (`SetFStrings`, `SetVScroll`, …) + cursor/keyboard editing
- **`TaowHTMLMemo`** — rich text; `LoadFont/SetFileName/SetAOWWindow/SetVScroll`

**`SetFStrings` is the content API**: the control renders an external strings object; append + `Update` →
scrolled redraw. Text rendering via `Ilpack.dpl` **`TImageLibraryFont`** (`ImageLib.ParseFontText`) — bitmap
fonts from the image library, no GDI. (`AoWInterface.dpl` is a near-duplicate toolkit at base 0x400000 —
likely the setup/menu shell's copy; the in-game one is `aowInt.dpl`.)

No text/font code exists in `Gfxepack` (raw DirectDraw blitters) or `HSEPack` (hex-sprite engine); a raw
paint-overlay would have to drive `TImageLibraryFont` by hand — strictly worse than the toolkit windows.
Frame pump = `Dcpack` `TCustomDisplay.UpdateFrame` / `StartUpdateFrameLoop`.

## 2. Exe game windows are DFM-streamed Delphi forms
`AoW.exe` VMT scan: 84 classes, including `TChatWindow, TResultsWin, TFastCombatWindow, TUnitWindow,
TMWindow (map), TSWindow (scanner), TIWindow (info), TNewTurnDlg, THeroUpgradeDlg, …`. Their published
methods are event handlers ⇒ DFM resources instantiate them — the same resource tech as the editor-toolbar
precedent (`dfm_parse.py`). Cloning a window class + DFM without a compiler is proven; the full recipe
(VMT block copy, method-table extension, RCDATA dir rebuild) is in `Combat_Log_Implementation_Design.md` §2.
NB: **tactical combat plays on the map screen** — floating game windows are available during combat.

`TChatWindow` (the clone donor): VMT `0x412D5C`; handlers `MinClick 0x412F10`, `ChatEditReturn 0x412F30`
(the append-a-line path), `ChatWinResize 0x413008`, `ChatWinShow 0x413040`, `ChatWinHide 0x41305C`,
`ChatMemoUpdate 0x41306C`, `PlayerListPreDrawItem 0x413090`. Floating, minimizable, idle in single-player.

## 3. Post-battle report machinery — `TResultsWin` + `TCombatLogbook` (decoded, unused)
Never built (the live log made it unnecessary), but the decoding is valid if battle reports in saves/PBEM
are ever wanted:
- `TCombatLogbook` (AoWEPACK) = **two `TCombatData` roster snapshots** — `+0xc` initial (`SetInitialData
  @0x55728E30`), `+0x10` final (`SetFinalData @0x55728E44`) — plus a TENode `+0x14` and flag `+0x19`;
  `ReadWrite @0x55728EA0` = it is **saved** (streams 5/6/7/8).
- Logbook-entry text (`TCombatEventLog.GetText @0x5572905C`) = the battle-header string at
  `finalData+0x48`, colored per player via `RaceColors @0x558E8294`.
- Adding per-strike lines would mean a strings container + `ReadWrite` extension (save-format touch) +
  `TResultsWin` DFM/code extension (`ResultsWinCreate @0x427D1C`, `ResultsPnlUpdate @0x428130`).
- **Precedent for strings in the CA pipeline: `TUpdateHeaderCA`** (created in `TCombat.SetLogbookHeader
  @0x5572759C`, carries an LStr at CA+0xc through ExecuteCombatAction) — the model if log lines should
  ever be MP-replicated rather than locally captured.

## 4. File logging (never needed, nearly free)
`kernel32!CreateFileA/WriteFile/CloseHandle` are already in AoWEPACK's IAT, plus `EngineP` exports
`TEngine.OutputDebugMessage/OutputDebugStr`.
