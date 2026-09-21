# Hero level-up dialog — doubled height, lists get the space

**Status: CONFIRMED WORKING 2026-07-31 (user tested in-game).** Script: `build_scripts/build_herodlg_tall.py`
(`--apply` / `--undo` / `--height N`). Binaries: **AoW.exe + AoWCompat.exe** (lockstep), backups
`<exe>.pre-herodlgtall`.

> ⚠ **SUPERSEDED as the dialog's owner (2026-07-31, same day).** `build_herodlg_columns.py` now
> grows and **relocates** this resource, and re-applies these same height edits itself. Consequences:
> - **Do not run this script any more.** It detects the relocated resource and prints a no-op
>   message pointing at the columns script. Change the height with
>   `build_herodlg_columns.py --apply --height N` instead.
> - **`<exe>.pre-herodlgtall` is no longer a safe revert** — it is layer 10 of 11 on AoW.exe, so
>   restoring it would destroy the columns feature. Use `build_herodlg_columns.py --undo`, which
>   lands back on exactly the state this doc describes.
>   *(`revert_audit.py` flags this very line as a "stale revert instruction". That is a false
>   positive — it matches the backup name inside a warning that says not to use it. Leave it.)*
>
> Everything below still documents how the height edit works and stays valid — the columns script
> imports `GEOM`, `enc_int`, `apply_edits`, `untransform` and `state_of` from it rather than
> duplicating them.

## What changed

`THeroUpgradeDlg` ("Upgrade Hero", the level-up dialog) grows from **407×432 to 407×864**; all
+432 px go to the ability lists, which grow 107→539 px = **6 → 31 visible rows** (ItemHeight 17).
Both lists grow: `AvailableAbilities` (right, "Upgrades") *and* `SelectedAbilities` (left, "Current
Abilities"), each with its cost column and scrollbar. Add/Remove, Done/Cancel and the bottom
knotwork band (`BCeltL/CeltM/CeltL/CeltR`) move down with the bottom edge. The dialog is
screen-centered by its own alignment (`awCenter/ahCenter`), so no positioning code is involved.

At 864 px the dialog needs a ≥~900-px-tall game resolution. Re-tune: `--apply --height N`
(433..2400) — works from any state, in place, touching no backup.

## Where the layout lives (the whole finding)

**The entire dialog layout is data**: RCDATA resource `THEROUPGRADEDLG` in the exe (foff 0xEE9B0,
size 0xCEFB in both exes as of writing — the script locates it by walking the PE resource tree, do
not hardcode; the RCDATA name table in these exes is already repointed outside `.rsrc` by the
combat-log clone). It is a standard Delphi-3 binary DFM streaming AOW-toolkit components
(`TAOWWindow/Panel/ListBox/VScrollBar/Button/Label/Image`, see `Combat_Log_GUI_Scout.md`).
`AoWHeroUpgradeDlg`'s *code* (0x4458B0..0x447528) has **zero geometry constants** — every imm-432
byte hit disassembles to a `[reg+0x1B0]` field displacement. DFM = sole layout authority.

Component facts (from the stream; parse with `re_tools/dfm_edit.py AoW.exe 0xEE9B0 0xCEFB`):

- Parent linkage is the **`AOWWindow` ident property** (not DFM nesting — all 96 controls are
  siblings of the root): lists/SBs/sort-buttons → `UpgradePnl` → `Dlg`; decor/buttons → `Dlg`.
- **Alignment model**: `ahTop`/`ahBottom` = that edge pinned via `TopOffset`/`BottomOffset`, size
  fixed; `ahBoth` = both edges pinned, size derived; `ahCenter` = centered. Same for `aw*`.
  Design-time `WinTop/WinHeight` are precomputed values consistent with the anchor formula — the
  patch updates **both** so the layout is right whether the runtime re-runs alignment at create or
  uses stored values.
- The four listboxes are `ahBoth` inside `UpgradePnl` (Top 15 / Bottom 28); `UpgradePnl` is
  `ahBottom` of `Dlg` (Bottom 38, its height is what the patch grows); Done/Cancel/knotwork are
  `ahBottom` (Bottom 10); everything above (`TopPnl`, `StatisicsPnl` [sic]) is `ahTop` — untouched.
- Scrollbars have **`VanishWhenFull=True`** — once a list fits entirely they disappear on their own.
  Their geometry has `Alignment=None`; list↔SB linkage is code-side (`*SBChange` handlers), not a
  `VScrollBar` DFM prop.
- The list/cost column headers ("Current Abilities/Cost/Upgrades") are **sort buttons**
  (`*Sort`, `*CostSort`), top-anchored in the panel — they stay put as the panel top doesn't move.

## The in-place edit technique (reusable for any exe DFM)

The next resource starts 1 byte after this one — **a DFM cannot grow in place**. Budget:

- 8 values needed Int8→Int16 re-encoding (+8 B): six `WinHeight 107→539`, two `WinTop 125→557`.
- Paid by **deleting the root data-module's designer-only `Left/Top/Height/Width`** (−33 B).
  Deleting props is always safe (readers keep defaults); *unknown* props are what raise EReadError.
  Every exe-form root carries these four ≈30 free bytes — remember this trick.
- Net −25 B, tail zero-padded; the DFM reader stops at the root terminator and never reads the pad
  (`dfm_edit.py` reports the state as "CLEAN + zero pad"). Declared resource size left unchanged.

16 value edits total (see `GEOM` in the script): `Dlg.WinHeight 432→864`, `UpgradePnl.WinHeight
150→582`, 6× list/SB `WinHeight 107→539`, 2× `WinTop 125→557` (Add/Remove, panel-relative),
6× `WinTop 395→827` (Done/Cancel/BCeltL/CeltM/CeltL/CeltR, window-relative).

**State machine** (why re-tuning needs no backup): pristine slot recognised by SHA1
(`66435ee7…a687`); any patched slot recognised by *inverse-transforming* (reinsert the four root
props verbatim, restore the 16 vanilla values) and SHA1-checking the result. `--apply --height N`
= untransform → transform(N); `--undo` = write the untransform output. Both directions verified.

## Not covered / follow-ups

- **AoWDevEd.exe has its own separate hero-upgrade dialog** (different build, own DFM) — untouched.
  The same technique applies if the editor's dialog should grow too.
- If a list somehow exceeds 31 rows the SB reappears and behaves as before (scroll range is
  code-side); nothing hardcodes "6 rows" anywhere that was found.
- Confirmed by the in-game test: frame/texture tiling at 864 px, scrollbar geometry and thumb
  sizing, list scrolling with >31 entries — all render and behave correctly.
