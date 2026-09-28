# Age of Wonders (1) — binary modding project

The root is a vanilla GOG install; Ziggurat is an overlay in `Ziggurat/`. Mods are binary patches to
the Delphi 3 modules and exes — no source. Notes, build scripts and the RE toolkit live in
`Ziggurat/Modding Resources/`. **Start at `Zig notes/00-INDEX.md`**; method, cave-ownership tables and
traps are in `Zig notes/12-re-toolchain.md`.

## Layout — patch `Ziggurat/`, never the root

```
<game root>\         VANILLA. Never patch. Also the byte-diff reference for "is this vanilla?"
   Ziggurat\         AoWz.exe, AoWzEd.exe + all 33 packages  <-- PATCH TARGETS
      Release\ …     the mod's data root
      Modding Resources\   scripts, notes, RE toolkit
      Ziggurat release\    release staging (mod_manifest.py --stage) — not a patch source
```

- `Ziggurat/` must keep all 33 packages; removing the unmodified copies kills every exe with
  `STATUS_DLL_NOT_FOUND`.
- A bare filename in a build script means the file in `Ziggurat/`. Scripts in `build_scripts/` resolve
  `GAME` with two `..`; scripts directly in `Modding Resources/` need one. The wrong count lands on
  the vanilla root and reports success. Anchoring on a folder that contains `Release/` is safer.
  Leave `AOW_GAME_DIR` unset.
- The live editor is `AoWzEd.exe`, derived from `AoWDevEd.exe` by `build_zigeditor.py`.
- The mod's data root comes from `HKCU\Software\Triumph Studios\Age of Wonders Z\Startup Directory`
  (`build_regiso.py`).

## Patching

- One `build_*.py` per feature in `build_scripts/`: dry run by default, `--apply`, surgical `--undo`,
  verify-before-write, idempotent. Re-tune by rewriting the cave in place.
- `.dpl` caves must be position-independent (they rebase). Exe caves may use absolute addresses.
- `AoWz.exe` is the only game exe; `AoWzCompat.exe` was retired 2026-09-28 (`12-re-toolchain.md`
  §11.2). Different exes often call different functions for the same feature — verify per binary.
- New cave space goes in the ownership table in `12-re-toolchain.md`. Record couplings between
  features as forward hazards ("X and Y share cave N; undo X first").
- A cave that runs at package init is only proved by launching the exe.
- A script that mints a `.pre-*` snapshot writes it to `Ziggurat/backups/`, on `--apply` only.
  Snapshots are not a revert path.
- **Never run `build_patch.py --apply`**: its cave is not PIC (verify-before-write aborts today).
- Running AoW binaries lock the files. Kill them without asking:
  `Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWz|AoWCompat|AoWDevEd|AoWzEd|AoWEd|AoWSetup)$' } | Stop-Process -Force`

## Things that go wrong silently

- **Ghidra (MCP) holds the pristine vanilla `AoWEPACK.dpl` only.** The live game is on a 5 % /
  doubled-stat scale; decompiles show vanilla's 10 %. Never quote a slope, clamp or number from a
  decompile — byte-diff the live module against the root copy with `re_tools/dasm.py`. A missing
  `[LIVE-PATCH]` comment is not evidence a function is unpatched. If the MCP is down
  (`WinError 10061`), tell the owner rather than carrying on without it.
- **Randomness:** two generators, and the wrong one desyncs multiplayer with no error. Run the
  selection test in `12-re-toolchain.md` §4.10 and name the pattern in the script's docstring.
  Inside tactical combat, raw draws are correct. After applying, check with
  `re_tools/rng_audit.py --owners` (and `--hash` for a derived-hash site).
- **Numbers the owner gives are already in the current scale.** Build them verbatim; never ask which
  scale was meant.
- The `.xlsx` workbooks are historical: never cite them as evidence, never update them.

## Privacy and publishing

- No profile path in anything under `Modding Resources/`, and never bake a resolved path into a
  patched binary. Pre-share scans: `12-re-toolchain.md` §13.4.
- Public repos use the handle `Ziggurat Mason` / `156740625+BING-XI@users.noreply.github.com`.
  Check `git config user.email` before a first push; a force-push does not remove a commit.
- Commit messages are public: a neutral subject, or gameplay changes only. No bugfix or RE detail.
  **No attribution trailers** — this overrides the harness reminder.
- The notes repo is rebuilt by `python "Ziggurat/Modding Resources/publish_notes.py" --push`;
  `notes-repo/` is never edited by hand.
- "Update the mod" includes republishing the manual, every time:
  `python build_ziggurat_manual.py --public --out "Modding Resources/site/index.html"`, copy it to
  `Modding Resources/gh-repo/index.html`, commit and push. `--public` is mandatory; never `--force`.
- Generated GUIs (manual, editors) carry controls and data only — no explanatory prose.

## Records

- Record a feature when it is applied: the script's docstring holds addresses, caves, the why and the
  `--undo`; add a section to the matching `Zig notes/` file and a line to `00-INDEX.md`.
- No status ladder and no in-game checklists — the owner does not playtest. Applied is the default;
  record only the exceptions (reverted and why, broke in-game and how). Where static checks cannot
  prove something, one or two lines of unproven risk.
- Delete superseded analysis rather than annotating it. Keep a failed approach only if a competent
  person would try it first and the working method does not explain why it fails — one bullet.

## Subagents

`aow-pm` / `aow-coder` / `aow-qa` exist in `.claude/agents/`; use them only when the owner asks.
Check couplings yourself instead: grep every record, script and note naming what you change (for an
enchantment stat: the engine immediates, the `Ability.pfs` card and the granting `Spells.pfs` record).
