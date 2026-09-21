# build_scripts/

One self-contained Python build script per mod feature (`build_*.py`). Moved here from
`Modding Resources/` on 2026-07-07 to declutter the top level.

**Locating the game directory.** Each script resolves it *relative to its own location* — two levels
up from the script file, since these live at `<game>/Modding Resources/build_scripts/`:

```python
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
```

So a script still runs correctly from any working directory, **and** the scripts contain no
machine-specific absolute paths — they work unchanged on anyone else's install. Set the
`AOW_GAME_DIR` environment variable to point at a different install (or if you move the scripts out
of the folder). `re_tools/*.py` use the same resolver, plus
`TOOLS = os.path.dirname(os.path.abspath(__file__))`.

## Shared modules (not `build_*`, patch nothing on their own)

| module | purpose |
|---|---|
| `rngstd.py` | ⭐ **the standard randomness emitter — pattern P4 DERIVED HASH.** Returns literal `bytes` (never an asm string, and it assembles nothing) for FNV-1a → `fmix32` → multiply-shift, plus `model()`, the identical arithmetic in Python for build-time calibration asserts. Import it rather than hand-rolling a hash: keystone encodes the same mnemonic two ways, and `rng_audit.py --hash` finds P4 sites by their exact bytes. `python rngstd.py` runs the self-test. Taxonomy + selection test: `../Zig notes/12-re-toolchain.md` §4.10 |
| `herodlg_cats.py`, `party_dialog.py`, `manual_exe_stub.py`, `gen_doubled_inventory.py` | feature-specific helpers; see the build script that imports each |

---

## ⚠⚠ `AOW_GAME_DIR` also scopes `kill_game()` — read this BEFORE a scratch round-trip

Many scripts call a `kill_game()` helper that terminates `AoW`/`AoWCompat`/`AoWDevEd`/`AoWEd` when
the target file is locked. That is the project's standing authorization — **but it matched on
process name only**, so a script writing to a **scratch copy** under `AOW_GAME_DIR` still killed the
user's *live* game.

**This caused a real incident on 2026-09-03.** A QA `--undo` round-trip on a scratch copy terminated
the running game mid-session, and the kill was initially misdiagnosed as a crash-on-expiry in the
feature under test. A "safe" read-only-looking verification destroyed live state and then sent the
investigation the wrong way.

**Fix, applied 2026-09-03:** every real `kill_game()` early-returns when `AOW_GAME_DIR` is set.

```python
def kill_game():
    # ⚠ SCRATCH GUARD: AOW_GAME_DIR set => we are NOT writing to the real install,
    # so we must NOT kill the user's running game. Standing kill authorization
    # applies to the real install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(["powershell", "-NoProfile", "-Command", ...])
```

Coverage measured 2026-09-03: **18** scripts matched `Stop-Process`; **14** actually kill and all 14
now carry the guard; the remaining **4** (`build_wheel_aowint.py`, `build_wheel_editor.py`,
`build_wheel_ext.py`, `build_wheel_vclpump.py`) were false positives — they only hold a `KILL_HINT`
string they *print*, and kill nothing. Derive the current numbers rather than trusting these:

```bash
comm -23 <(grep -rl "Stop-Process" build_scripts/*.py | sort) \
         <(grep -rl "SCRATCH GUARD"  build_scripts/*.py | sort)
```

**Any new script that kills processes must carry the guard.** A scratch round-trip is supposed to be
the *safe* way to test a script; it is not safe if it can reach outside the scratch copy.

Convention (see `../../CLAUDE.md`): keystone-assembled caves, capstone-disassembled for review,
**dry-run by default / `--apply` to write**, idempotent, verify-before-write (aborts on byte
mismatch), auto-backup to `<file>.pre-<feature>`. Re-running with no args re-verifies current state.
Needs `pip install capstone keystone-engine`.

    python build_scripts/build_firefeed.py            # dry-run (verify)
    python build_scripts/build_firefeed.py --apply    # write (close all AoW binaries first)

⚠ **Revert a feature with its own script's surgical `--undo`, NOT by copying a `.pre-*` backup.**
The line that used to stand here said the opposite; it is wrong and has been for a long time. A
`.pre-<feature>` restore wipes **every layer applied to that file afterwards**, and a snapshot's
*name* is no proof of what is inside it (`AoW.exe.pre-herodlgcolumns` is a snapshot of a *patched*
build). A surgical `--undo` restores only the hook sites / VMT slots that script owns and zeroes
only its own caves, so it survives both layering and pruning. See `../../CLAUDE.md`.

⚠ **Read the flag's implementation before trusting it.** `--undo` and `--revert` do not mean the
same thing everywhere: `build_mapcursor_fix.py --revert` merely restores `.pre-mapcursor`, and
`build_ai_itempickup.py --undo` is a **dry run** whose write switch is still `--apply`
(`--undo --apply`).

Each script's matching design doc lives in `../Zig notes/` and lists its backup name(s), addresses,
revert command and status.

| Script | Feature | Doc |
|---|---|---|
| `build_spellcast.py`, `build_spellcast_tcpck.py`, `build_spellcast_card_v2.py`, `build_spellcast_multiturn.py`, `build_spellcast_book_exe.py`, `build_spellcast_persist.py` | Unit/hero spellcasting (multi-part) | `../Unit_Spellcasting_INDEX.md` |
| `build_firefeed.py` | Fire heals Fire units | `../Fire_Heals_FireUnits_Design.md` |
| `build_mapcursor_fix.py` | Small-map cursor dead-zone | `../Cursor_RightSide_LargeWindow_Bug.md` |
| `build_editor_framerate.py` | Editor lag (map-view FrameRate) | `../Editor_Lag_CopyPaste_Investigation_2026-07-07.md` |
| `build_editor_timerres.py` | Editor responsiveness: `timeBeginPeriod(1)` + frame-budget knob (`--sleep N`) | `../Editor_Frame_Cost_Analysis.md` |
| `build_editor_rendergate.py` | Editor CPU: render 1 map frame in N while the pump keeps running (HSEPack.dpl) | `../Editor_Frame_Cost_Analysis.md` |
| `build_editor_autosave.py` | Editor autosave | `../Editor_Autosave_Design.md` |
| `build_validation_goto.py` | Map Validation dialog: double-click an entry to centre the view on it | `../Validation_Dialog_Clickable_Entries.md` |
| `build_party_random.py` | Party tool places a random army stack (strength + allowed races) | `../Party_Random_Generator.md` |
| `build_patch.py` | Movement-predictor fix | `../MovePredictor_Fix_2026-07-05.md` |
| `build_icestorm_lava.py` | Ice Storm: Lava→Wasteland ⚠ **do not `--apply`** — its else-hook is chained by `build_chasm_sky_spellguard.py` | `../Terrain_Changing_Spells_Map.md` |
| `build_rng_lockstep.py` | Terrain rolls draw from the **synchronised** RNG, not the per-process one (Raise Terrain / Ice Storm / Fire Storm) | `../Zig notes/12-re-toolchain.md` §4 |
| `build_chasm_sky_movement.py`, `build_chasm_sky_art.py`, `build_chasm_sky_transitions.py`, `build_chasm_sky_spellguard.py`, `build_deved_terrainpal.py` | Chasm & Sky flying-only terrains (multi-part) | `../Terrain_System_INDEX.md` |
| `build_ai_sitesearch.py` | AI players path to and search exploration sites (7 site classes, 14 VMT slots) | `../Zig notes/AI_Sites_And_Loot.md` |
| `build_ai_itemloot.py` | AI heroes equip / upgrade-swap ground items; ground items become group-aware AI targets. ⚠ **Supersedes `build_ai_itempickup.py` and `build_ai_itemtarget.py`** — refuses to apply while the old pickup script owns its two hook sites | `../Zig notes/AI_Sites_And_Loot.md` |
| `build_ai_itempickup.py` | ⚠ **`--undo`'d 2026-09-02, must stay inert** — superseded by `build_ai_itemloot.py`. Its `--undo` is a dry run; write it with `--undo --apply` | `../Zig notes/AI_Sites_And_Loot.md` |
| `build_raiseterrain_ug_earth.py` | Raise Terrain castable underground; underground Dirt → temporary Earth + sparkle. ⚠ **Depends on `build_gripofwinter.py`; while installed, `build_gripofwinter.py` and `build_raiseterrain_lavadirt.py` cannot run. Undo this one FIRST** | `../Zig notes/RaiseTerrain_UG_Earth.md` |
| `build_minddecay_oos.py` | Mind Decay: unconditional combat RNG draw (MP draw-count determinism) + the nil check vanilla lacks | `../Zig notes/MindDecay_OOS_Fix.md` |

⚠ `build_editor_timerres.py` and `build_editor_rendergate.py` are **coupled**: `--sleep 1` is only
safe with the render gate installed (the gate's `skip_sleep` paces the loop). Reverting
`HSEPack.dpl.pre-rendergate` without also running `build_editor_timerres.py --sleep 8 --apply`
leaves the editor's frame loop free-running at ~117 fps. Revert both or neither.

⚠ `build_chasm_sky_art.py` patches **`Release/Release.hss`**, not a binary. That file carries a
trailing CRC-32 — the script repairs it automatically via `re_tools/hss_crc.py`; a hand-edit that
skips the repair makes the game AND editor die silently at startup. See `../Terrain_System_INDEX.md`.

