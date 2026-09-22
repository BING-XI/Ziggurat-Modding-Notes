# Ziggurat — the map

Start here. This is the index to the Ziggurat modding record for Age of Wonders 1: what has been
built, what is waiting to be tested, what will hurt you, and where the detail lives.

**Consolidated 2026-09-03** from 110 separate documents.

---

## Where knowledge lives

| | holds |
|---|---|
| `build_scripts/build_*.py` | the patch, and in its module docstring the addresses, cave assembly, and reasoning. **For an atomic single-cave feature the script IS the record.** |
| these `NN-*.md` files | cross-feature knowledge, engine mechanics, multi-stage design history, and every outstanding in-game checklist |
| the live binaries | the truth. Everything else can be stale — byte-diff before quoting a number. |

## The files

| file | covers |
|---|---|
| `01-combat-maths.md` | to-hit, damage, the 5 % conversion, the DAM/HP doubling, stat clamps, facing, missiles |
| `02-abilities-modded.md` | changes to vanilla abilities — Invisibility, Turn Undead, Vision, Panic, Leadership, Dispel, lifesteal, enchantment re-grade |
| `03-abilities-added.md` | abilities minted from scratch, plus id budget, registration, ceilings and costs |
| `04-spells-modded.md` | changes to vanilla spells, tier research, mastery cost, spell-id budget |
| `05-spells-added.md` | Embrittle and Grip of Winter, and the recipe for a new spell |
| `06-unit-spellcasting.md` | the Spellcasting ability on ordinary units — the largest multi-binary feature |
| `07-ui.md` | the game's UI: combat log, hero level-up dialog, unit window, cursor |
| `08-editor.md` | the map editor: performance, autosave, palette, toolbar, validation, party generator |
| `09-terrain-movement.md` | hexes, terrain change, transitions, movement tables, the move predictor |
| `10-ai-and-structures.md` | AI behaviour, raze, the raze combat predictor, Arena, shipyards, sites |
| `11-engine-internals.md` | items, file formats, serialization, and shelved analyses worth keeping |
| `12-re-toolchain.md` | **how to work on this project** — Ghidra, capstone, the RNG rule, cave ownership, keystone traps, **§13 how a release is cut**, **§14 the Ziggurat Manual's failure modes** |
| `Map_Generator.md` | **the Ziggurat Map Generator** — the pipeline, terrain allocation, mountains, hills, Sky, and the scope ruling that governs it |
| `Inioch.md` | material from the fellow modder, and what we adopted from it |
| `CLAUDE.md` (repo root) | the conventions. Read it before patching anything. |

**If you are new, read `12-re-toolchain.md` first.** It carries the rules that make everything else
safe, and the traps that have cost this project the most time.

## Conventions — not features, so not on the status ladder

| convention | where | adopted |
|---|---|---|
| **Randomness: five patterns, one selection test.** P1 SYNCED DRAW / P2 COMBAT RAW / P3 COSMETIC RAW / **P5 RESEED-FROM-STATE** (vanilla's own reproducibility idiom — prefer it) / P4 DERIVED HASH (**this project's invention**, only when the decided set can shrink so draw order is unstable) — the set is **closed**; name the pattern in the build script's docstring rather than designing a roll from scratch. P4 makes no draw: `build_scripts/rngstd.py` emits FNV-1a → `fmix32` → multiply-shift as literal bytes, salted from the per-game constant `map[+0x22C]`. ⚠ P4 sites are invisible to `rng_audit.py --owners` by construction — check them with `--hash`. | `12-re-toolchain.md` §4.10 (test, salt evidence, 9 anti-patterns); repo-root `CLAUDE.md` | 2026-09-09 |
| ⚠⚠ **A moved install keeps loading from the OLD folder.** The engine takes its data root from `HKCU\…\Age of Wonders Z\General\Startup Directory`, not from the exe's location, so copying an installed `Ziggurat\` elsewhere gives hundreds of `Error loading:` dialogs for files that are all present. ⭐ **The tell is that the path in the dialog is not the folder the exe was launched from** — same-folder means missing files, different-folder means stale registry. Caused by `createvalueifdoesntexist` on the installer's two `[Registry]` lines, which meant re-running it could never update the path; **removed 2026-09-15**, so re-running now fixes it. Installers before that need the key deleted by hand. ⭐ Open: an exe-relative data root would remove the class entirely — `TAoWRegistry` in `AoWEPACK.dpl` is the single choke point (`Get/SetStartupDirectory` `0x55705298`/`0x55705248`, rw helper `0x55703D08`). | `12-re-toolchain.md` §13.3 | 2026-09-15 |
| **The public repo carries a HANDLE.** `BING-XI/Ziggurat-Engine-Mod` commits as **`Ziggurat Mason <156740625+BING-XI@users.noreply.github.com>`** (set globally), never the owner's real name. **Commit messages are player-facing: interesting gameplay changes only, or nothing — no bugfixes, no RE detail, no attribution trailers.** ⚠ GitHub's "Keep my email address private" does **not** stop `git push` exposing an address — the separate "Block command line pushes that expose my email" does, and it is off. ⚠⚠ Force-pushing does not remove a commit from GitHub; get it right before the first push. ⚠⚠ The `$USERNAME` leak scans **miss the git identity** (`<user>` ≠ `<git-name>` ≠ the lowercase gmail) — it hid in `gh-repo/.git/logs/`; clear with `git reflog expire --expire=now --all && git gc --prune=now`. | repo-root `CLAUDE.md`; `12-re-toolchain.md` §13.1a step 6 | 2026-09-14 |

---

## ⚠⚠ Booby traps — read before running any build script

| script | what happens |
|---|---|
| **`build_patch.py --apply`** | line 284 `shutil.copyfile(DPL, BACKUP)` **overwrites `Modding Resources/AoWEPACK_original_backup.dpl`** — the pristine vanilla reference — with the live patched DLL. It is the movement-predictor script; the feature is real, the backup line is not. |
| **`build_scroll_gfx.py`** | retyping `ITEMGFX.PFS` 316–319 breaks the image system wholesale — blank hero portrait, no spell icons. Applied, tested, **confirmed harmful in-game 2026-08-01**. |
| **`build_herodlg_tall.py`** | superseded same-day by `build_herodlg_columns.py`, which now owns the dialog. Use `build_herodlg_columns.py --undo`. |
| **Wall HP** | never "restore" it to a ×2 — there are THREE independent tables, unified to 40 stone / 10 wood by owner ruling. |
| **`build_razediag.py --want-open`** | **test-map use only** — it sets `TAIGroupRazeControl`'s mode bit `0x04`, which makes the AI raze **everything** it stands on, cities of its own race included. It shipped live for two months undetected (`10-ai-and-structures.md` §3.6). ⚠ **A diagnostic that changes game behaviour needs a status row** — this one had none anywhere, which is exactly why nobody looked. Run `python build_razediag.py` (no args) before any playtest; all three levers must read `STOCK`. |
| **`build_spellcast_book_exe.py`** | **retired — it no longer owns its own cave**, so a dry run reports `MISMATCH cave @ 0060C0A8` **permanently, and that is the correct output**, not a broken state: `build_scroll_spellbook.py` rewrote `cave_bookfilter@0x0060C0A8` in place (130 → 344 B) and owns the live bytes. ⚠ Do not "repair" the mismatch by relaxing the check or re-deriving the cave — that destroys the scroll feature and the hero-tier exemption. `--apply` is safe by accident only: the verify gate aborts before writing (`:174`). Re-tune the filter in `build_scroll_spellbook.py`'s `_loop`. Full record: `06-unit-spellcasting.md` §"The cave's second owner". |

**Retired 2026-09-03:** the standing "never run `build_magebane.py --apply`" warning. That hazard was
real between 2026-08-26 and 2026-08-29 and was fixed by `ranged_tail()` (`build_magebane.py:207`),
which detects whether Shield's cave is present and chains into it. Re-applying is now safe in both
states. ⚠ Still true: re-running `build_assassin.py`, `build_ranged_slayers.py` or
`build_invis_penalty.py` rebuilds their caves and **silently drops the Magebane chain** — re-run
Magebane afterwards; `--verify` reports it.

## ⚠ A third of the scripts cannot be reverted

**48 of 148 `build_*.py` have no `--undo` and no `--revert`**, and for several no `.pre-*` snapshot
survives either. Those features are **permanent in practice**. Several older docs promised a revert
path that does not exist.

Check before promising one:

```bash
grep -l -- '--undo\|--revert' "Modding Resources/build_scripts/build_X.py"
```

⚠ Not every `--revert` is surgical — `build_mapcursor_fix.py --revert` merely restores a snapshot,
which is as destructive as a manual copy. Read the implementation.

Notable scripts with **no** revert path: all six foundational unit-spellcasting scripts,
`build_razebattle_tower.py` (the largest feature), `build_combatlog_dll.py`, `build_copper_medal.py`,
`build_tierresearch_dll/exe.py`, and both `build_trueseeing.py` and `build_invis_penalty.py` — which
is the convention's own worked example for in-place cave rewriting, one-way at both ends.

---

## 🔨 Awaiting your in-game test

Everything below is written to a live binary and statically verified. **Nobody has played it.** Each
file carries the specific checklist for its own rows.

### Combat maths — `01-combat-maths.md`
- **Map-placed heroes keep their unspent skill points and get a turn-1 level-up prompt**
  (`build_hero_turn1_upgrade.py`) — 🔨 APPLIED, UNTESTED (2026-09-22). Vanilla confiscates them on
  day 1: `THero.NewDay @0x55786CBA` banks the whole pool into the write-off `[hero+0x50]` (tag
  `0x27`), so a level-5 editor leader offers 10 points at level 6, not 70. ⚠ Both vanilla exemptions
  miss a PBEM game — the campaign+human one needs a campaign, and the "Customize leaders" one is
  **hard-disabled by the setup form in PBEM** (`AoWz.exe @0x00410D44`, session mode 2). The patch
  rewrites the 10-byte block in place to call `C_TURN1 0x5584B000` (40 B, PIC), which leaves the
  write-off alone and decrements the level cache `[hero+0x4C]` so `ValidateHeroUpgrade
  @0x55787D54` — whose trigger is a **lag, not an event** — raises the dialog on the owner's first
  turn. ⚠⚠ The cache is **persisted**; the `GetLevel() >= cache` guard is what stops an unrestored
  decrement writing a permanent 10-point budget loss into the save. §5 of `01-combat-maths.md` holds
  the mechanism, the three guards and the in-game checklist.
- HP ceiling 120 → 100 (four places that must move together) — 2026-08-31
- Morale re-scale (ATK ±4, RES ±6) — 2026-08-26
- Map-fire dead-code fix (was ~4× too weak) — 2026-08-26
- Burning / Decay / Turn-Undead-AI damage gap-fix — 2026-08-26
- Shield — ranged-only scope, magnitude −5 — 2026-08-27
- Shield — auto-resolve 75 % probabilistic rule — 2026-08-27
- **Hero library skill points spent down** (`build_heroskill_spend.py`, DATA edit — no binary
  patched) — 2026-09-08. All 50 heroes in `User/Ziggurat Heroes.ahl` carried unspent points (589
  total, up to 26 each); each hero's level was dropped by `left // 10` (both tag `0x16` and tag
  `0x18` written) and the residue spent on HP/ATK by the "alternate HP/ATK" rule. **589 → 3
  unspent**, file 8620 → 8662 bytes, `Ziggurat release/User/` written in lockstep. Surgical
  `--undo`; snapshot `backups\Ziggurat Heroes.ahl.pre-heroskill`. §5 of `01-combat-maths.md` now
  holds the price list, the `level*10+10` budget and its three sites, the live
  `HeroExperienceTable`, and the `.ahl` format. **In-game checklist:**
  0. **Launch `AoWz.exe`, quit, then `md5sum "Ziggurat/User/Ziggurat Heroes.ahl"`.** If it is no longer
     `ba6600c5c56eaf616c8c140f98cb36ff`, `WriteUserLibraries` re-serialised it in the engine's own
     layout — expected, not corruption. Re-run the script with no args: `state: installed` means the
     values survived and only the layout moved; `partial` means something changed the values.
  1. **Open a hero-recruitment screen** (or the editor's hero library) — no "not all skill points
     assigned" nag on any of the 50, and no error on load.
  2. Recruit **Borak the Brute** or **Forok the Bloated** (3 → 1; seven heroes drop two levels, but
     these two end lowest and are the only ones whose XP field is now 0, which is the one path
     `THero.ReadWrite`'s legacy fixup at `0x55788A48` takes) and confirm the level, XP-to-next-level
     and stat card all agree.
  3. Recruit **Acara the Spider**, **Atam the Righteous** or **Gorthak the Black** — these three are
     *meant* to show exactly **1** unspent point.
  4. Check a **Spell Casting** hero (Vn'nih the Odd, Meridon the Wise, Jiswyn Treesong) — the
     20-per-level price is the single biggest term in the sum; if their level looks wrong, the cost
     model is wrong.
  5. Level one up in-game and confirm the new point is spendable and the budget advances by 10.
  6. Save and reload a game containing a recruited library hero — stats and level must survive.
  ⚠ Nothing may be running when it is applied: the game and the editor rewrite this file on exit.

### Abilities — `02-abilities-modded.md`, `03-abilities-added.md`
- **Dark Gift — lifesteal heal 4 → 3, both texts rewritten to the owner's sentence** 🔨 APPLIED,
  UNTESTED (2026-09-14): `build_lifesteal_roundattack.py` (`DG_HEAL=3`, cave `0x5580DC80` imm byte
  `0x5580DCB1`, in-place rewrite — `LS_HEAL` stays **4**, `0x76` is a different ability) and
  `build_pfs_typos.py` (`Spells.pfs` rec 87 tag 10, `Ability.pfs` rec 179 tag 5, both now
  "Gives a single unit Death Strike, +3 Dam, and +3 lifestealing."). DAM was already +3 at
  `0x557BB731` and was **not** touched. ⚠ Both rows' declared vanilla baseline was fiction — true
  vanilla is "…Death Strike and +1 to damage." for both, now `old[0]`. ⚠ `Ability.pfs` writes are
  **still blocked** by two unrelated hand-edited rows (rec 103, rec 61); the Dark Gift card text was
  already correct on disk, so nothing is outstanding here. ⚠ The lifesteal script's backup gate was
  `if not exists` and minted a `.pre-lsround` from an already-patched DLL; deleted, gate replaced
  with a positive pre-patch test. `02-abilities-modded.md`
- ⚠⚠ **Attacking a WALL with an Assassin or Magebane carrier crashed the game — fixed** 🔨 APPLIED,
  UNTESTED (2026-09-11): `combatunitguard.py` (new shared cave `0x55849000`, 98 B, entries
  `guard_unit` `0x55849000` / `guard_hero` `0x55849040`) + `build_assassin.py` +
  `build_magebane.py`, all in `AoWEPACK.dpl`. **`[combatobject+0x4C]` exists only on `TCombatUnit`;
  `TCombatWall` is a SIBLING and reuses those bytes as wall type + wall HP**, so a Ziggurat stone
  wall reads back as `0x00002802` — non-zero, so a `test eax,eax` nil guard passes it and the next
  dereference AVs (`EAccessViolation in VCL30.dpl at 00003A18`). ⚠⚠ **`System.@IsClass` is nil-safe
  but NOT garbage-safe** — entry `0x41303A14` (export RVA 14868) is `test eax,eax / je`, so nil
  returns False; there is simply no validity test on a *non-nil* pointer before `mov eax,[eax]`.
  ⚠ `0x41303A18` is the **loop body**, not the entry — it is the back-edge target of the `jne` at
  `0x41303A23`, hence both the reported fault address and the reason hooking this function's entry
  once died with runtime 216. The gate must be `IsClass(obj, TCombatUnit)` **before** the `+0x4C`
  read; the shared guard nil-checks as well so callers test one result, matching the house pattern.
  Five sites carried it (assassin `0x5580E0B7`/`0x5580E160`, magebane `0x558129F3`/`0x55812A23`/
  `0x55812A5D`); a full sweep of mod cave space cleared the other 20 `[reg+0x4C]` hits. Assassin
  gained `--undo-wallguard` (surgical, SHA-1-identical round trip) and a chain-guarded `--undo`;
  both scripts' snapshot gates were minting `.pre-*` files from already-patched DLLs and now
  require virgin hooks. Full record: `03-abilities-added.md`, Assassin section
- **Per-race hero level-up offer gate** — each ability now has a race-dependent chance of appearing
  in the Upgrades columns (Turn Undead: High Men / Dark Elf / Undead at 60 %, the other eleven races
  0 %, raceless 10 %; Elves see Archery and Forestry at 60 % each; **13.5–18.4** of 102 offered per
  level-up on average since the second retune of 2026-09-10). 🔨 APPLIED, UNTESTED (2026-09-09):
  `build_heroskill_race.py` on `Ziggurat/AoWz.exe` + `Ziggurat/AoWzCompat.exe` (6 B displaced at `cf_gate`, today
  `0x00623E53` — **it moves on every `build_herodlg_columns.py --apply`**, so never hard-code it;
  cave `0x00628000..0x0062A000`, 201 B code + a 16×256 table at `0x00629000`;
  snapshots in `backups\`; surgical `--undo`). Percentages live in **`heroskill_races.py`, which is
  the user's file to edit** — editing it changes nothing until `--apply` is re-run. ⭐ The project's
  first **P4 derived-hash** site (`rngstd.py`): no draw at all, so the offer set survives a dialog
  reopen, an Add/Remove and a save/reload, and every peer computes the same one. ⚠⚠ **COUPLED to
  `build_herodlg_columns.py`**, whose `--apply` regenerates the cave the hook lives inside — it is
  now taught to re-chain and prints `re-chained` / `not installed` every run, **and aborts before
  `save()` if the re-chain fails** rather than shipping an exe with the gate unlinked (2026-09-09).
  ⚠⚠ **`Ability.pfs`
  record id = ability id + 10**; joining them directly produced a wrong analysis that survived two
  reviews. ⚠ Fail open: an ability with no table line is ALWAYS offered, deliberately —
  ⚠ and since the top rung dropped to 60 that makes an **unknown** ability more likely to appear
  than any deliberately-marked racial signature. Still the right fail-open (the alternative is a new
  ability silently never appearing), but it is a new asymmetry
- **The offer table's editor — Ziggurat Manual, "Hero Offers" tab** — 🔨 BUILT (2026-09-09), **no
  binary patched**. 102 abilities × 12 races, one dropdown per cell at **0/10/25/60** (0/15/40/100
  until the first retune of 2026-09-10, then 0/10/30/100 until the second; the tiers are
  colour-ramped), hover + `Q W E
  R`, live per-race expected-offer count. `build_scripts/heroskill_races.json` is now the table
  **whenever it exists** (the `OFFERS` shorthand can hold only three values per ability, so it
  cannot express the grid); absent → shorthand as before, corrupt → raises rather than falling back.
  Seed with `heroskill_races.py --seed` (quantises 5→0, 15→10, 25/30/40→25, 100→60). ⚠⚠ **Moving a
  rung migrates the JSON by TIER IDENTITY, never by re-quantising** — `07-ui.md` §2.8a. ⚠⚠ **The top
  rung is 60, so nothing is guaranteed to anyone**: every race's deterministic floor is **0** and a
  High Man sees Turn Undead 60 % of level-ups, not every one. Expected offers now run **13.5–18.4**
  (mean 16.3, sd 3.0–3.3), all thirteen rows under 20 — inherent to a top rung of 60, **not** a
  defect; `report()` prints `low` in a `vs 20-30` column and gates nothing. ⚠ Editing it changes
  nothing until `build_heroskill_race.py --apply` is re-run — baked 2026-09-09, **`stale` since the
  first rung change and still `stale` after the second**. ⚠ Raceless (row 15) is not in the grid and is **derived** —
  the per-ability mean of the 12, quantised onto the ladder (13.5 expected). It was
  left at `TABLE_DEFAULT` = all 102 offered until 2026-09-09, invisibly, because `report()` skipped
  the row. ⭐ Its three staleness mitigations (DOM-as-model, a `built`/`now` fingerprint pair,
  defeating Chromium's `<select>` restore) answer the 2026-08-14 export-reopen trap —
  `12-re-toolchain.md` §14.4, detail in `07-ui.md` §2.8. The second toolbar figure is the ladder
  distribution `380/454/238/152`, not an "authored cells" count (100 was both the default and a
  ladder value, so setting a cell to 100 % counted down)
- **Ziggurat Manual build cache** — 🔨 BUILT (2026-09-10), **no binary patched**. Opening the
  Manual when nothing has changed no longer rebuilds it: **8.3 s cold, 0.43 s warm**. Keyed on the
  **content** of 107 declared inputs plus whatever the last build actually opened; `--force`
  rebuilds anyway. ⚠⚠ This re-opens the **2026-08-14 staleness hazard** the always-rebuild design
  existed to close, so **any doubt rebuilds** — no/corrupt/wrong-version sidecar, an unresolvable
  input tag, an unreadable input, a missing / truncated / altered HTML. The sidecar
  `Ziggurat Manual.html.build.json` stores **root-relative tags, never absolute paths** (profile
  leak + the exe's `_MEIPASS` moves every launch), carries the build's warnings so a skipped run
  can reprint them, and the page stamps its key in `<meta name="zm-build">`. `07-ui.md` §2.9.
- **Ziggurat Manual `--public` — the Pages site no longer ships the authoring UI** — ✅ **LIVE
  (2026-09-13)**, **no binary patched**. Published and verified on the served page: 0 `<input>`,
  0 `<textarea>`, 0 real `<select>` (the one hit is inside a CSS comment), 0 `<form>`, 1 `<button>`,
  no `contenteditable`, no embedded `.pfs`. The 2026-09-11 upload was a byte copy of
  `Ziggurat Manual.html`, so **three** editors went public: the "Edit text" bar over 210
  `contentEditable` blocks, the ability editor with **the whole of `Unitres.pfs` embedded as 211 KB
  of base64**, and the Hero Offers grid as **1237 `<select>` dropdowns** with an Export button.
  None of it could persist (Pages is static; both save paths need pywebview or a local file) but the
  changelog read as anyone's to rewrite. `--public` omits all three and renders the offer cells as
  static spans — no `<input>`/`<textarea>`/`<select>`/`<form>` left, one `<button>` (the
  Ziggurat/vanilla toggle), 2,574,676 → 2,021,878 bytes. ⚠ Publish with
  `--public --out "Modding Resources/site/index.html"`, **never** by copying the authoring page.
  ⚠ `PUBLIC` is in the cache key (`CACHE_VERSION` 2). The runtime net is `window.zmCanAuthor()`,
  which must test `location.protocol === 'file:'` **first** — pywebview injects its api
  asynchronously. `12-re-toolchain.md` §14.6.
- **Reforming Flesh's level-up cost — 0 → 20** — 🔨 APPLIED, UNTESTED (2026-09-10):
  `build_reformingflesh.py` v3 on `AoWEPACK.dpl` alone. **A registration-time store of
  `[ability+0x14]` can never work**, which is why v2's `mov dword [eax+0x14], 50` left the ability
  free in game: `TAbilityControl.ReadWrite` walks the ability list by index and `rwEObject
  @0x555116B0` calls `TAbility.ReadWrite` for **every** registered ability, record or no record, so
  `rwInteger @0x55510EF4` reaches its `xor eax,eax / mov [edi],eax` tail and **zeroes the field when
  tag 6 is absent**. The two neighbouring tags disagree — `rwData` (tag 9, the selection mask)
  *skips* on a missing tag — so a record-less ability keeps its cave's mask and loses its cave's
  cost: **offered at level-up, and free.** Fix: `cave_cost @0x558260B0` (32 B, appended to the same
  zone, now `0x55826000..0x558260D0`) hooked into `TAbility.ReadWrite` at `0x5574F0AA` — `mov ecx,7`
  is exactly 5 bytes, no `.reloc` entry, `TAbility.ReadWrite` byte-identical to the pristine root
  DLL. It fills in a **zero only**, so a future tag 6 still wins. Cost lives in `EXPAND_COST`; a
  re-tune is an in-place rewrite (`retune` state) and never a revert-and-re-apply.
  ⚠ **The owner's DevEd edit went to `<root>\Release\Ability.pfs`** — no editor binary carries the
  regiso patch, so all of them read/write the **vanilla** data root while the game reads
  `Ziggurat\Release\`. That session minted all 13 mod-ability records there, including 187 with
  tag 6 = 20. The root's `Release/Ability.pfs` is consequently **no longer stock** (147 → 160
  records); `Modding Resources/Release - Vanilla/Ability.pfs` is the pristine copy if it should be
  put back. **In-game checklist:** (1) level a hero and confirm Reforming Flesh is offered and
  **costs 20**, not 0; (2) confirm the points are actually deducted and a hero with 19 left cannot
  take it; (3) confirm no other ability's cost moved — Leadership 10, Spell Casting 20, Vision 4,
  Marksmanship 6, Regeneration 8; (4) launch once and confirm no `Runtime error 217`/`216`, since
  the hook runs during the `Ability.pfs` load at startup. ⚠ Still offered to **every race at 100 %**:
  `offered_ids()` only sees abilities that *have* a record, so 177 falls through `TABLE_DEFAULT`.
  It is the **only** such ability — the live DLL registers 160, the Ziggurat tree has records for
  159, and 177 is the single gap.
- **Ziggurat Manual — Hero Offers cost column read the wrong number for two abilities** — 🔨 BUILT
  (2026-09-10), **no binary patched**. The grid took its Cost column straight from
  `heroskill_races.offered_costs()` = `Ability.pfs` tag 6, and **tag 6 is inert for a levelled
  ability**: every `TMultiLevelAbility` descendant overrides `ExpandCost` and charges out of its own
  per-level list. `read_heroskill_offers()` now applies the same precedence the Abilities page
  already used — levelled → `ability_names.costs()` (which follows the call hop out of the ctor into
  a mod cave), single-level → tag 6. Over the 102 offered ids exactly two moved:
  **Leadership 20 → 10** and **Spell Casting 15 → 20**; Vision 4, Marksmanship 6 and Turn Undead 5
  were already right. ⚠ The owner has been authoring offer probabilities against the two wrong
  figures. The grid's fingerprint is over the offer percentages only, so `d3892d5f` is unchanged.
- **Panic cleared by any damage that lands** — 🔨 APPLIED, UNTESTED (2026-09-09):
  `build_panic_cleardamage.py` on `AoWEPACK.dpl` alone (hook `TCombatObject.ExecuteDamage
  @0x55726C58`, 6 B displaced; cave `0x55829000`, 58 B; snapshot
  `backups\AoWEPACK.dpl.pre-paniccleardamage`; surgical `--undo`). One body serves all four combat
  classes and AoWTCPCK.dpl reaches it through an import thunk, so the single hook covers melee,
  ranged, breath, touch, spells, ticks **and auto-resolve** with no second binary. ⭐ The finding
  that makes this the fix: **Panicked has no timer** — `TPanickedAbility.Create` writes duration
  mode 3 ("entire combat"), which `NewTurn` (mode 1) and `NewCombatTurn` (mode 2) never tick, so
  before this the only mid-battle exits were Healing and Remedy. Coupled to `build_panic_nomelee.py`
  in play but not in code — separate hooks, separate caves, separate `--undo`s
- **Panic — the click-to-attack hard gate (6th hook)** — ✅ **CONFIRMED WORKING (2026-09-13)**:
  `build_panic_nomelee.py` gains site `meleemove` on `AoWTCPCK.dpl` (hook `0x00422CE8` in
  `TTacticalCombatUnitHS.MeleeMoveTC`, **6 B displaced** → `E9 rel32` + one `NOP`; cave `0x004383C0`,
  35 B; forbid `0x00422D60` = `Result := False`). Closes a user-reported hole: the panicked unit
  showed the "blocked" cursor but a left-click still attacked. ⭐ The reusable finding —
  **`UpdateMoveCursor` only picks a GLYPH; `MoveUnits`/`MoveSelectedRoute` never read its decision**,
  so any modded "may not initiate melee" rule must gate `MeleeMoveTC`, vanilla's single creation point
  for deliberate tactical melee, not just the cursor. Vanilla's cursor-only enforcement works for
  Flying purely because it never offers a legal-looking route to an illegal target. ⚠ Side effect,
  accepted: a panicked unit can no longer smash walls/gates (wall-smashing runs through `MeleeMoveTC`
  too). ⚠ `SITES` is now **append-only** — `cave_va()` indexes slots by position within the file.
  ⚠ The script's backup gate was fixed in the same edit: it snapshots only when **every** site in that
  file reads vanilla, otherwise `--apply` over a partly-installed feature mints a `.pre-` file holding
  patched bytes
- **Turn Undead / Dispel Magic levels above I apply again** — 🔨 APPLIED, UNTESTED (2026-09-10):
  `build_inherent_level_fix.py` on `AoWEPACK.dpl`, two VMT dwords (6 bytes), no cave, surgical
  `--undo`. Repairs a regression `build_leadership_fix.py` introduced: those two classes override
  `GetLevel` but inherit the base `GetInherentLevel` (`return 0`), so the grant compared 0 vs 0 and
  skipped the record copy — points deducted, no level. ⚠ Also changes the hero level-up dialog's
  Cost column and **Remove** button for these two, through four `GetInherentAbilityLevel` sites in
  `AoWz.exe`/`AoWzCompat.exe` that a DLL-only scan missed — checklist item 3 in `02-abilities-modded.md`
  §B′ exists to close that. ⭐ `--audit` is the reusable sweep for the whole defect class
- Terror — one cast per combat, per side (v2) — 2026-08-31
- Leadership — aura instant-refresh on level-up — 2026-07-20
- Leadership IV grants Fearless — 2026-09-01
- Leadership buffs only the OTHER units in the party; card shows "own (+received)" — 2026-09-16
- Dispel Magic — level cap III → V — 2026-08-09
- Magebane — enchantment-scaling ATK/DMG (`0xAA`) re-tune, and its description text — 2026-08-29
- Item-granted HP / MV bonuses — 2026-08-31

### Spells — `04-spells-modded.md`, `05-spells-added.md`
- **Power Leech (ex Power Leak)** — the halving is gone; the caster steals 25% of the power of every magic node owned by another player, and that owner loses the same. 🔨 APPLIED, UNTESTED (2026-09-07): `build_powerleech.py` on `AoWEPACK.dpl` (4 B at `0x5577CEC5`, 1 B at `0x5577CED8`, `cave_powerleech @0x55848000`), plus the rename, the `Spells.pfs` record 58 description and `NEWMECH_POWERLEECH` in the manual. One-at-a-time is **already vanilla** and was verified, not built. The **income row** is a separate patch: `build_powerleech_ui.py` on `Ziggurat/AoWz.exe` + `Ziggurat/AoWzCompat.exe` (7 B at `0x0042CFD9`, `cave_powerleech_ui @0x0062D100`) adds a "Power Leech (gained)" / "Power Leech (lost)" row to the Magic window's power breakdown — 🔨 APPLIED, UNTESTED (2026-09-09)
- **Terror — spell ATK 16 → 12** — 🔨 APPLIED, UNTESTED (2026-09-09): `build_terror_atk12.py` on `AoWEPACK.dpl`, pure immediate rewrite, no cave/hook (`0x557F9A81` w1, `0x557F9887`/`0x557F9A0B`/`0x557F9CA6`/`0x557F9D8F` w4; snapshot `backups\AoWEPACK.dpl.pre-terroratk12`; surgical `--undo` restores **16**, not vanilla 6). ⚠ **Terror's power is encoded FIVE times — a partial edit is silent** (different powers in tactical vs auto-resolve vs the AI estimate). ⚠ Vanilla was **6**: the recorded "8 → 16" doubled an undocumented pre-convention Ziggurat value, so **`live / 2` is not the vanilla number** — see the trap in `01-combat-maths.md` §3
- Embrittle — the whole spell — 2026-09-01 ⚠ **v1 broke startup; a cave that runs at package init must be proved by launching the exe**
- Grip of Winter — the spell, its description, and its manual prose — 2026-09-01
- Storm / Poison Plant debuff — roll vs Resistance — 2026-07-30
- Research Book slot **buttons** now move with their panels (`build_tierresearch_btnfix.py`, hook `0x42F2DC`, cave `0x611F00` in the `.tres` slack, both exes) — 🔨 APPLIED, UNTESTED 2026-09-06 — fixes "some sphere-tiers selectable, others not": `cave_layout` re-pitched the panels for research mode but never moved the sibling `SxBtn` click targets. ⚠ Do **not** retarget the `call` at `0x42F2D7` instead — that is one of `build_tierresearch_exe.py`'s verified hooks and breaks its self-check
- ⭐⭐ **The Death Altar crash — a STALE `.reloc` ENTRY, not the combat log** (`build_relocfix.py`) — ✅ **CONFIRMED WORKING 2026-09-13** (applied 2026-09-11). The Death/Divine dispatch rewrite in `ExecuteStormDamage` overwrote `mov dx,[0x55780840]` but left its base-relocation at RVA `0x807FB`, so **the loader added the rebase delta to live code on every launch**, smashing `0x557807FD/FE` — the `mov dx,0x20` that is the **Death** arm, and only that arm. Reported as `EExternalException … at 000807FE / External exception 80000003`; `000807FE` is the second corrupted byte and the code varies with the load address. Fixed by flipping the entry type `3 → 0`, plus **ten more** found by the same sweep. ⚠⚠ **Invisible to every static check** — the file, `dasm.py`, the byte-diff and the owning script are all correct. ⚠ The `--audit` needs **all three** of its rules: "dword is not an in-image VA" alone has a systematic false-negative class (an operand at the *end* of the displaced range leaves a residual that still reads as a valid VA — it missed 4 of the 11), and the twin-diff rule that catches those is blind on the editor, which has no vanilla twin. Full decode + the rules in `12-re-toolchain.md` §5.2c; the register of all eleven, the reverse-coupling table and the release-staging caveat in §6.5a
- Combat-log effect-roll emitter gated to tactical combat only (`build_effectroll_tacticalgate.py`, cave `0x55810500`) — 🔨 APPLIED, UNTESTED 2026-09-06 — the emitter's `CLG1` guard is not a combat gate, so the tactical-only string/ring machinery also ran on the strategic map and in auto-resolve; this confines it. ⚠ It was applied believing it was the Death-altar fix. **It was not** — see the row above. Keep it (running that machinery off the tactical path is still wrong), but it is not known to have fixed anything observable
- Animate Dead — permanent undead, and the free-upkeep balance question — recorded 2026-09-04 ⚠ **pre-convention hand-edit; no script, no `--undo`; never attach a persistent enchantment to these units**

### Unit spellcasting — `06-unit-spellcasting.md`
- Tier gate is **units only** (reverses the 2026-07-06 "units and heroes" decision) — 2026-09-03
- Scroll as a permanent per-hero spellbook grant — cave extended 2026-09-03

### UI — `07-ui.md`
- **Taskbar button icon** — 🔨 APPLIED, UNTESTED (2026-09-13). Win11 drew the grey placeholder on the
  button, which belongs to Delphi 3's hidden `TApplication` owner window. ⭐ **The defect is narrower
  than "no icon": a live probe found `ICON_BIG` already set and byte-identical to `MAINICON`, while
  `ICON_SMALL` and `GCL_HICONSM` were 0.** `Forms.TApplication.CreateHandle @0x4133ACB0` sends
  `WM_SETICON(ICON_BIG)` to the owner window itself at `0x4133ADC0..0x4133ADD3`, gated on
  `Controls.NewStyleControls` (`[0x413E2504]` → BSS `0x413E3738`), which is true at runtime. All three
  `TApplication` senders push wParam 1 — **D3 never sends `ICON_SMALL` at all** — and nothing imports
  `SetClassLongA`. The taskbar resolves `ICON_SMALL2 → ICON_SMALL → GCL_HICONSM`; the `ICON_SMALL`
  send is the change, `ICON_BIG` is belt-and-braces. Delivered by **retargeting the existing
  `call Forms.TApplication.Initialize`** (`0x004599DE` game, `0x0042EE52` editor — 4 bytes of operand,
  nothing displaced) to a 96 B cave that tail-jumps to the real thunk. ⭐ `user32!LoadIconA` and the
  `'MAINICON'` literal come from **vcl30.dpl** via the rebase delta `[<GetExeName IAT slot>] −
  0x4133C0F8` — `LoadIconA` is in no exe's IAT. (`SendMessageA` *is* in the editor's, 1 of 19 user32
  imports; it goes through vcl30 anyway to keep one cave body across all four files.) `07-ui.md` §8.
  `build_taskbar_icon.py` on `Ziggurat/AoWz.exe` + `AoWzCompat.exe` + `AoWDevEd.exe`, then
  **`build_zigeditor.py --apply`**.
- **Hero level-up dialog: Add now acts on the column that actually holds the selection** — 2026-09-10.
  ⚠⚠ `cave_fill` (= `PopulateLists`, which Add **and** Remove call) reset the cached `activecol` to 0
  on every repopulate while leaving each list's published `Selected` alone, so after any Add the
  cache pointed at column 0 and `AddAbilityBtnClick` read a `Selected` of −1 and did nothing. It was
  unrepairable by re-clicking because `TAOWListBox.CheckMouseDown` fires `OnChange` **only when the
  clicked row differs from `Selected`**. Two symptoms, one bug: no second level of a multi-level
  ability (the only path to Vision III is a second Add on a row the hero already partly owns), and a
  dead Add after an Add+Remove. **Rule: derive the active column by scanning for `Selected ≠ −1`;
  never cache which column a button acts on.** ⚠ Not caused by the same day's `cave_setfmax` scroll
  sync, which was kept — byte-proved by diffing `.hcol` against the 2026-09-09 staged exe. `07-ui.md`
  §2.4a. `build_herodlg_columns.py` on `Ziggurat/AoWz.exe` + `AoWzCompat.exe`.
- **Hero level-up dialog: 960×525 (8 rows/column), and each column now owns its own scrollbar**
  — 2026-09-10. ⚠⚠ One DFM ident fixed three bugs at once: the four cloned Cost lists carried the
  donor's `VScrollBar = AvailableAbilitiesSB`, so the wheel over any Cost column drove column 0,
  `TAOWListBox.Update` dragged those costs back on every repaint, and `AvailSB2..5` were never
  positioned or made visible (only the list that *references* a bar runs `TAOWListBox.SetSize`'s
  show/place/feed path). **When cloning a DFM component, audit its ident properties for references
  to the donor's siblings** — handler names are meant to be shared, control references are not.
  `07-ui.md` §2.2a. `build_herodlg_columns.py` on `Ziggurat/AoWz.exe` + `AoWzCompat.exe`.
- Unit-window party arrows, every entry path — 2026-09-03
- Combat log — spell labelling (live tactical), touch attacks, effect-landing roll
- Mouse wheel — editor Win32 scrollbars — 2026-09-02
- 12 added hero faces moved into the right resolution set (`H_Faces` 79 @103×128, `_H_Faces` 79 @52×64) — 2026-09-04

### Editor — `08-editor.md`, `Map_Generator.md`
- Editor **Open/Save Mapset defaults to the engine's own data root** instead of the Windows folder
  MRU when `AoWEd_LastDirs.ini` has no `Set=` line. 🔨 APPLIED, UNTESTED (2026-09-11):
  `build_dlgdirs.py` v3 on `Ziggurat/HSEPack.dpl`, §2.2. ⚠⚠ **This closes a real data-loss route**:
  the mapset the Set dialog opens decides where all eleven `.pfs` files are written
  (`THSEngine.LoadHSS @0x5560F75C+0x2F` → `engine[+0x44]` → `ExtractFilePath`), and on 2026-09-10 the
  MRU fallback put an ability edit into the **vanilla** `<root>\Release\`. Data root =
  `[[THSSEdit+0x24]+0x2C]` = `Engine.TEngine.FStartupDirectory`, reached off the instance the hook
  already has because **HSEPack.dpl imports nothing from AoWEPACK.dpl**, so the usual IAT-delta trick
  has no anchor. Cave `engdir 0x5564E07D` + `DIRBUF 0x5564E520` in `.dlgd` page slack (VirtualSize
  `0x520 → 0x630`); 34 raw bytes left there. ⚠ `Map` must never reuse `[edi+0x24]` — `THSMEdit` is a
  different class. ⚠ `AoWDevEd.exe`'s half is byte-identical to v2 and was deliberately not rewritten,
  so **no `build_zigeditor.py` propagation is needed for v3** — but the script never mentions that
  two-step and any future exe-touching version does need it (§2). ⚠ Every `engdir` failure falls back
  to the **MRU**, i.e. into the trap; a missing `Ziggurat\Release\` is one such case and is
  undetectable from the cave, so the static pass is not a behaviour pass.
- Editor **Developer > Delete Unused Heroes** — prunes the open map's hero roster to
  (placed on the map) ∪ (leaders), with a counted Yes/No/Cancel confirmation. 🔨 APPLIED, UNTESTED
  (2026-09-08): `build_deved_heroprune.py` on `AoWDevEd.exe`, §10. The predicate is the engine's own
  — `hero[+0x04] == 0` (`TEObject.Owner`) and not `IsClass(TLeader)`; `Owner` covers tile armies,
  city garrisons and site defenders in one test. Cave `0x0058E3A0` in `.ctp`'s zero tail, no new
  section, file length unchanged; `TMainForm`'s method table relocated a second time (134 → 135).
  ⚠ `build_deved_terrainpal.py --apply` over this is a **safe no-op** (it guards on `.ctp` already
  existing). The hazard is *deleting* `.ctp` to re-run terrainpal — that destroys this **and**
  toolbar_trim. ⚠ `build_deved_toolbar_trim.py --undo` is refused while this is applied; undo
  heroprune first.
- Editor **Developer > Game Settings folded into Map Settings as a "Game" tab**, menu item hidden.
  🔨 APPLIED, UNTESTED (2026-09-12): `build_deved_gamesettings_tab.py` on `AoWDevEd.exe`, §11.
  ⭐ **The form is REPARENTED, not rebuilt** — `TGameSettingsDlg` is constructed as a never-shown
  form owned by Map Settings, a fresh `TTabSheet` goes into `MainPageControl`, and the embedded
  form's `ClientPnl` gets `Parent := sheet / Align := alClient`. No DFM grows, no RCDATA moves, no
  field table is touched; the whole patch is **four rewritten `call rel32` operands** (`0x004230E8`,
  `0x00423730`, `0x0042315F`, `0x004284B2`) into one 216-byte cave at `0x0058F280` in `.ctp` page
  slack, plus one dword `G_GSDLG 0x004E0520` in `.dlgd` page slack. ⚠ `sheet.Parent :=` is **not** a
  substitute for `SetPageControl` — `TTabSheet` does not override `SetParent`, and `FPages` is only
  touched by `InsertPage`, so Parent alone gives a panel with no tab; `SetPageControl` is not
  imported and is reached by the IAT-delta idiom (`[0x00432210] + 0x309C0`, **recomputed from
  `vcl30.dpl` and asserted on every run**). ⚠ A Delphi virtual constructor takes `AOwner` in **ECX**,
  not EDX — `DL` holds the alloc flag. ⚠⚠ `build_deved_heroprune.py` zeroes `.ctp`'s whole tail on
  **both `--apply` and `--undo`** (`--apply` strips in place first) and will destroy this cave
  silently — the editor then AVs at **startup**; `.ctp` apply order is now terrainpal →
  toolbar_trim → heroprune → gamesettings_tab. ⚠ Inherited vanilla defect made newly reachable (not fixed):
  `0x0042E052` uses `@LStrPos` (first `'.'`), and `[THSMEdit+0x1E4]` is a **full path**, so a map
  under a dotted directory is truncated on every Map Settings OK.
- Editor **Item Properties gains Hit Points / Movement spinners + their stat icons**, authoring
  `item+0x4A` / `+0x4B` (the bytes `build_item_hpmv.py` added). 🔨 APPLIED, UNTESTED (2026-09-13):
  `build_deved_itemhpmv.py` on `AoWDevEd.exe`, §12. **Controls are created at RUNTIME, not cloned
  in the DFM** — the RCDATA cannot grow (one pad byte to the next form), a DFM-named `OnChange`
  needs a published method or `TReader` rejects the whole form, and the load path is four unrolled
  sequences with no loop to extend. Three rewritten `call rel32` operands (`0x004137DC` and
  `0x0041389F` → `cave_enter`, `0x004133AE` → `cave_load`) into a 644-byte cave at `0x00599000` in
  `.nmg` page slack, plus a **length-neutral** DFM re-pitch of 16 Int8 values (32 px → 24 px row
  pitch, spin Height 26 → 22) that opens rows at y 112 and 136 inside the unchanged 161 px panel.
  ⚠ `TSpin.EditorEnabled` is **`+0x140`**, not `+0x120` (that is `AutoSelect`), and a fresh TSpin is
  **not** blank — `Create` sets `MaxValue := 0x0FFFFFFF`. ⚠ `SetValue` clamps via `CheckValue` and
  its `SetText` raises `EN_CHANGE`, so with `MinValue 0` a negative bonus can be clamped to 0 by the
  UI — identical to the four existing spinners, owner's call. ⚠ It does **not** fire merely on
  opening: `cave_enter` and the first `cave_load` run before `ShowModal`, so `FHandle = 0` routes
  WM_SETTEXT to `DefaultHandler` (no `EN_CHANGE`) and `TCustomEdit.CNCommand @0x4134FA54` also gates
  on `FCreating`. It needs a post-show `UpdateControls` or a spin click, and `Edit` Assigns back only
  on `mrOk`. ⚠ No "already built?" test on
  purpose: the form is `Create → (Edit XOR Execute) once → Free` at all eight construction sites, and
  a `G_FORM == form` skip would pass on a *new* form at a *recycled* address holding *freed* spin
  pointers. `ItemTypeBoxChange` is deliberately not a
  hook, so changing item type keeps HP/MV while resetting ATK/DEF/DAM/RES (`TItem.SetItemType`'s own
  asymmetry).
  The **icons** are `TImage`s cloned verbatim from `THEROEDITFORM`'s `Image11`/`Image12` — the art
  was already in the binary, so nothing was authored. Because the RCDATA cannot grow, the **whole
  `TITEMEDITFORM` resource was relocated** to `0x00599400` (9958 B) and its directory entry
  repointed; `.nmg` `0x6E00 → 0x8C00` (both sizes), SizeOfImage `0x19A000 → 0x19C000` (**RVA space —
  not `0x59C000`, which folds in ImageBase**), file `0x192200 → 0x194000`. No field-table or
  instsize change (40 entries / `0x284`): `Panel1` is already a DFM component with no published
  field, so `FieldAddress` returning nil is harmless. All six rows' geometry is now **derived** from
  `ROW_PITCH`/`SPIN_H`, icon Tops included (`spin + (22−height)//2` → 114 and 139; ⚠ `Image11` is the
  H17 control and `Image12` the H16 one, despite its 32×15 bitmap).
  ⚠⚠ `build_deved_newmapgen.py --apply` **rebuilds `.nmg` in place**, which now erases the cave *and*
  a **live resource** — Item Properties then fails to open with a `TReader` error. The script
  recognises that as a **damaged** state and `--apply` repairs it (`--undo` is reachable from it too);
  an earlier build asserted instead and was unrecoverable in both directions. The hazard is **latent**:
  newmapgen's `--apply` refuses while applied and its `--undo` is surgical and leaves `.nmg` alone.
  ⚠⚠ The old bytes stay in `.rsrc` at `0x0697A8` as the **master this script rebuilds from**, so an
  edit made only to the live `.nmg` copy is silently reverted on the next `--apply` — and the verify
  path prints `DRY RUN`, not a diagnosis. Dead-master register + scanner inventory in
  `12-re-toolchain.md`; `build_editor_spinners.py` now reports **18** sites because it scans the
  whole file and finds both copies.
- Editor **Settings > Abilities / Spells: UP/DOWN arrows move the list selection.** 🔨 APPLIED,
  UNTESTED (2026-09-14): `build_deved_listarrows.py` on `AoWDevEd.exe`, §13. ⭐ The root cause is a
  **reusable finding for any "keyboard does nothing in the editor" report**: `TMainForm.FormCreate`
  installs an `Application.OnMessage` filter (`[App+0x9c]` = Code `0x004280DC`, `[App+0xa0]` = Data,
  assigned at `0x00428630`) that accepts WM_KEYDOWN for VK `0x25` LEFT / `0x27` RIGHT / `0x26` UP /
  `0x28` DOWN, forwards them to `[TMainForm+0x22C]` (HSMEdit) as map scrolling and sets
  `Handled := True`. `TApplication.ProcessMessage` calls `OnMessage` **before** `IsKeyMsg` /
  `TranslateMessage` / `DispatchMessage`, so the focused control never receives the key — which is
  why clicking works and arrows are inert. Hook `0x0042812F` (5 B `3b 70 5c 75 23`,
  `cmp esi,[eax+0x5c]` = the `Screen.ActiveForm` test) → a 57 B cave at **`0x0052D640`** in `.mtb`
  page slack (453 B free at `0x0052D63B`; VirtualSize `0x4C63B → 0x4C800`, Characteristics
  `0x40000040 → 0x60000040` for MEM_EXECUTE). The cave passes the key through when `TMsg.hwnd`
  (`[ebx+0]`) equals `AbilityListBox`'s or `SpellListBox`'s `FHandle`, else runs vanilla.
  ⚠ **Do not hook `0x00428128`** — that 5-byte `mov eax,[0x432220]` is the obvious site and strands
  the type-3 `.reloc` fixup at `0x00428129` mid-rel32. ⭐ **No refresh code is needed**: the native
  LISTBOX sends LBN_SELCHANGE for keyboard moves as for clicks, and
  `StdCtrls.TCustomListBox.CNCommand @0x41352984` turns NotifyCode 1 into `TControl.Changed` +
  `@CallDynaInst bx=0xFFF0` = `Click` → `OnClick`, so one hook serves both lists. Offsets from
  `TMainForm`'s field table `0x00425D92` (305 entries): `+0x4A0` AbilityListBox, `+0x4DC`
  SpellListBox, `+0x22C` HSMEdit; `+0xCC` = `TWinControl.FHandle` — **a wrong one is silent.**
  Second, separate fix behind `--part guard`: `SpellListBoxClick @0x0042BF60` guarded on the wrong
  listbox (`0x0042BF92` read `[ebx+0x4a0]` then worked off `[ebx+0x4dc]`), so the Spells panel stayed
  blank until an ability had been selected — one byte at `0x0042BF94`, `A0 → DC`.
  ⚠⚠ Two-step: `build_deved_listarrows.py --apply` then **`build_zigeditor.py --apply`**.
- In-game **item banner shows Hits / Moves bonuses** beside the four combat ones. 🔨 APPLIED,
  UNTESTED (2026-09-13): `build_itembanner_hpmv.py` on `AoWz.exe` + `AoWzCompat.exe`, `07-ui.md` §9.
  `TItemBanner` lives **only in the exe pair** — not in any `.dpl`, not in the editor.
  `IBannerPopupShow @0x00406AE8` renders the four bonuses as four **unrolled** ~0x7A-byte blocks on a
  2-column grid (`esi` from `0x1E`, `+0x32`, wrap at `0x82`; `y` from `0x64`, `+0x14` per row), so
  this is a cave, not a table edit. New RWX section `.ibnr`; `TITEMBANNER` grown 7411 → 9469 B by four
  components cloned from `TUnitBanner` and relocated into it; field table 13 → 17, instsize
  `0x78 → 0x88`. `cave_hpmv` 328 B @ `0x00632700` (hook `E9` at `0x00406D7D`), `cave_clamp` 40 B @
  `0x00632848` (hook at `0x00406E21`). **The icons already existed** — `Int\Icons.ILB` id 4 (Hits) and
  `Int\IconMove.ILB` id **16** (Moves, 32 px wide, so its icon sits at `esi+0x03`, not `esi+0x0A`).
  ⚠ `Int\Icons.ILB` id 5 is **Mana**, not Movement.
  ⚠⚠ **A new control is constructed VISIBLE** (`TAoWComponent.Create @0x59802318` writes
  `[esi+0x75]=1`) and `SetVisible` walks no child list — which is why vanilla opens with an
  eight-call `SetVisible(False)` sweep at `0x00406B39`. The first build omitted the four new controls
  from that reset and **every static check passed**; stale icons would have persisted between items.
  The four hides now sit at the head of `cave_hpmv`, proven equivalent to a third hook by a
  branch-target sweep (every edge into `[0x406B89, 0x406D82]` originates at ≥ `0x00406B9C`).
  ⚠ The popup height clamp was raised from a flat `0xC8` to `max(200, y+60)` — **bit-identical for
  every `y ≤ 140`**, but without it a 5-stat item left the ability list 6 px tall, i.e. zero rows.
  ⚠⚠ `.ibnr` consumed the **last free section-header slot** (table at `0x1F8`, 13 × 40 ends at
  `0x400` = SizeOfHeaders exactly). No 14th section is possible; a future exe feature must squat in a
  measured zero tail or `--undo` this first. `add_section()` asserts rather than corrupting CODE.
- Editor toolbar **trimmed to one captioned row** — `File |` New Open Save "Save As" · `Developer |`
  "Open Mapset" "Fog of War" · `Help |` About; 3 labels + 24 buttons deleted and the `MBRowB` panel
  removed, so the map view starts 31 px higher. 🔨 APPLIED, UNTESTED (2026-09-06):
  `build_deved_toolbar_trim.py` on `AoWDevEd.exe`. In-place shrink of the live `.ctp` `TMAINFORM`
  DFM (`0x6065C → 0x5F644`), resource-entry `Size` only, no section header touched; surgical
  `--undo` from `backups\AoWDevEd.TMAINFORM.pre-toolbartrim.dfm` — ⚠⚠ **that snapshot no longer
  exists** (it was in `<root>/backups/`, deleted 2026-09-10), so this `--undo` currently has nothing
  to restore from. ⚠ Its `--undo` is **refused while
  heroprune is applied** (the live DFM is `0x5F6A0`, not the trimmed `0x5F644`) — undo heroprune
  first. ⚠ Deleting `.ctp` to re-run `build_deved_terrainpal.py` resurrects the deleted buttons.
- Editor `File > New` → **New generated map** — the Ziggurat Map Generator behind a twelve-dial
  panel. 🔨 APPLIED, UNTESTED (rebuilt 2026-09-06 for the twelfth dial, Hills):
  `build_deved_newmapgen.py` on `AoWDevEd.exe`, cave section `.nmg` @ `0x00593000`. The 2026-09-05
  eleven-dial build was driven end-to-end by an automated click-through; this one has not been.
  ⚠ Its info box lost its last third whenever a map had been generated that session — fixed
  2026-09-06, and that specific regression is item 1 of §9.5's checklist.
- Map generator: **mountains bid on steepness rather than altitude, the Mountains dial is a share
  of the land (its old High and Very High were the same number), and hills are placed** — no binary
  patch, `Zig Modding Tools/zig_mapgen.py` + `zig_hsm.py`. 2026-09-06. Verified across 69 generated
  maps read back from the written `.hsm`; never opened in the editor.
- Map generator: **water gets a 1–3 hex flat shore, and mountains form thin sweeping ranges rather
  than clumps** — `zig_mapgen.py`, no binary patch. 2026-09-06. `shore_buffer()` bars every overlay
  from a varying-depth band beside sea, lake and river; the ranges follow a narrow corridor around
  the planned crest and are made LONGER (`extend_crest`) rather than wider when the dial asks for
  more. Measured with the new `--metrics` report over 5 seeds × 2 sizes: mean range width
  5.36 → 1.94 hexes, overlay within two hexes of water 21.8 % → 4.9 %, the dial's own share hit to
  0.01 pp. ⚠ At Very High (45 % of land) the corridor saturates and the ranges necessarily merge.
  Never opened in the editor.

### Terrain & movement — `09-terrain-movement.md`
- Chasm & Sky — movement rows, spell/ability guards, tile art v2
- ⭐ **Structures on Chasm & Sky — the PAD is the gate and the mound** (`09-terrain-movement.md`
  §"Chasm & Sky" step 6). Every structure resource carries `res[0x44]=1`, so `TStructure.CanPlace`
  is `CanPlacePad` and a `TPad` map object — with its own terrain-indexed art — decides the terrain,
  not the structure's own sprite. Pad slot lists are 13 long, so Sky (`0x0E`) is unreachable in the
  editor: `build_pad_skyalias.py` maps it to Chasm in `TPad`'s VMT slot `+0x12C`;
  `build_pad_transparent.py` blanks Water/Lava/CaveWater/Chasm so nothing is drawn under the
  structure. ✅ CONFIRMED WORKING 2026-09-20
- ⚠⚠ **A Chasm/Sky hex carrying ANY overlay was impassable to everything, flyers included**
  (`09-terrain-movement.md` §1) — the Fly row was `04 FF FF …`, 4 MP only with no overlay, so a
  teleporter (`GetOverlay` = 7) on those terrains could not be reached at all. v2 opens the whole Fly
  row and the Bridge column of the five walking-family tables. ✅ CONFIRMED WORKING 2026-09-21
- ⛔⛔ **A cloned `.hss` resource MUST get a fresh tag 3** (`09-terrain-movement.md` §7). Tag 2 =
  edit id (which editor grid), **tag 3 = the slot within that grid** — and
  `TECustomResourceGrid.SetResource @0x5551FBB8` **destroys whatever already occupies the slot**. A
  clone that keeps its donor's tag 3 frees the donor, and the next dereference is an
  `EAccessViolation` on a heap-garbage VMT. ⚠⚠ **There is NO 1128-resource ceiling** — an earlier
  note claimed one; the live file carries 1131 and both exes are happy. The "any 2 pass, any 3 fail"
  bisection was counting collisions, not resources.
- ⭐⭐ **Roads on Dirt, bridges on Chasm and Sky** (`09-terrain-movement.md` §7) — one road/bridge
  resource serves exactly **one** terrain (`TAbstractRoad.CanPlace @0x5560A820` matches its own
  terrain list) and the art is embedded per resource, so it takes five cloned records.
  `build_hss_addresource.py`, the project's first length-changing `Release.hss` splice.
  ✅ CONFIRMED WORKING 2026-09-21
- ⭐⭐ [`re_tools/hss_loadtest.py`] — **the only honest way to test a `.hss` change.** ⚠⚠ AoWzEd
  stays alive, windowed, at 40 MB when a mapset fails to load; a "is the process up" check passed a
  broken file. Drives `Developer > Open Mapset` and watches for the modal `TMessageForm`.
- ⚠ **`build_hss_exception_detail.py` is APPLIED and is a DIAGNOSTIC** — `--undo` before any
  release. It makes "Error loading …hss" follow up with the real exception. On a 1129-child file:
  It turned "Error loading" into `EAccessViolation`, and the live debugger then named the call:
  `SetResource+0xa1`, `call [ecx+8]` on a freed resource. ⭐ Without it this was three wrong
  hypotheses deep.
- Raise Terrain underground → temporary Earth — 2026-09-03
- Ice Storm Lava → Wasteland — the 25 % skip rate was never retested after the confirmed 50 %
- Movement predictor fix (v1→v4) — 2026-07-05
- Terrain rolls draw from the synced RNG (3 sites) — 2026-08-31

### AI & structures — `10-ai-and-structures.md`
- ⭐ **The tactical-combat AI's pause between moves — half the AI turn, and it is not thinking time**
  (`10-ai-and-structures.md` §9). Measured live: 32 × **692 ms** stalls with the token queue empty and
  nothing animating = 50 % of a 42.6 s AI turn. `TCAI.EvalBattle`'s state-1 scan evaluates **one unit
  per rendered frame** (`cmp dword [cai+0x24], 1` at `0x419289`, and again at `0x419B2C`), and the
  whole scan restarts for every action — **quadratic in army size**. The engine's own third site
  already uses **50** (`0x419E78`), which is both the precedent and the script's sentinel.
  ✅ CONFIRMED WORKING (2026-09-12) — **0.5 s+ of the ~0.7 s stall gone**, no stutter, AI unchanged:
  `build_combat_ai_budget.py` on `Ziggurat\AoWTCPCK.dpl`, budget 1 → 16, two imm8 bytes inside
  existing instructions (nothing displaced, so no cave and no `.reloc` hazard), snapshot
  `backups\AoWTCPCK.dpl.pre-aibudget`, surgical `--undo`, `--budget N` re-tunes in place.
  ⭐ The ~0.2 s residue is the budget's floor: states 3/4/5/0 each cost one frame **per action**
  regardless. ⚠ Tactical combat imports **no clock** — every combat delay is frames, paced by
  `AoWz.exe`'s DFM `FrameRate` = 30 (value byte `0x12F8D4`); that is the second, global lever.
- ⚠⚠ **AI razed friendly and own-race cities — a diagnostic lever left live for two months**
  (`build_razediag.py --want-open`, byte `0x557D7414` = `05` instead of vanilla `01`). Bit `0x04` is
  `TAIGroupRazeControl`'s **unconditional** mode bit: `ValidateRazeCity` returns it verbatim on the
  `relation ≥ 2` path and `ValidateRazeStructure` seeds `true` from it, so **race relation stopped
  protecting any city** and the non-city scorched-earth want-gate vanished, for every behaviour AGC.
  Found by playtest (elves razing elven settlements, first Cult of Storms mission).
  🛑 REVERTED / 🔨 fix APPLIED, UNTESTED (2026-09-11) — one byte, staged copy refreshed in lockstep.
  ⚠⚠ **The revert does not rescue a save already in progress**: each city raze costs the razed city's
  race **−30** relation with the razer off a 50 baseline, and `< 41` is status `< 2` = hostile, so one
  razed elven city makes every later elven raze legitimate under vanilla's own rule. Restart the
  mission. ⭐ The 2026-07-21 sighting "an AI razed one of its own cities" (`10-ai-and-structures.md`
  §4.5.1) was this bug, mis-attributed to the dialog downstream of it. §3.6.
- **Raze/rebellion battles Stage 12 — victorious city rebels are buyable, and the combat report
  reaches every witness.** 🔨 APPLIED, UNTESTED (2026-09-12) — `build_razebattle_tower.py` on
  `Ziggurat/AoWEPACK.dpl`, two caves rewritten in place (no `--undo` exists; §4.4.11).
  **12a** `cave_cityguard@0x5580D2B0` razeguard branch `jmp 0x5575FE0C` → `ret`
  (`0x5580D2CC`: `E9 3B 2B F5 FF` → `C3`+pad): **city** loss-garrisons now get **no AI group at all**,
  exact vanilla parity. A Guard AG (behaviour 2) made `TAbstractUnit.CanJoin@0x557821AC` refuse
  before any race logic, so `TCity.JoinAmount@0x557ACF98` → `GetCanJoinSelection@0x5578FA04` returned
  empty and no gold offer ever appeared. Structures keep Guard kind 2. ⚠ Not kind 5 `TRefugeAG` —
  `JoinAmount@0x55782324` special-cases behaviour 5 to cost **0**. ⚠ Do not patch `CanJoin`.
  **12b** the Stage-2 single-player event-log block (~109 B) → four instructions calling
  `AoWE.DistributeCombatEvent@0x5572928C` (EAX=`combat[+0x18]`, DL=`EVENTLOG_SHOW`=1), vanilla's own
  fast-combat form at `TArmyCombatMoveTE.ExecuteCombat+0x2b5@0x55749BD9`: reports now file for every
  player who **saw** or **fought in** the battle. Fixes rebellion, raze and loot alike — on the
  **fast** path; the tactical one is **12d** below.
  **12c** fixed cave reservations `TOWERRAZE_RESV=1152` / `CITYGUARD_RESV=33` — the writer emits only
  `len(new)` bytes, so a shrinking cave orphans its tail. ⚠ **That had already happened before Stage
  12**: an earlier stage shrank `cave_towerraze` 1152→1140 and left 12 bytes of live code at
  `0x5580CD84` falling straight into `cave_canraze`. Proved unreferenced (module-wide absolute-dword
  and `E8`/`E9` rel32 scan) and zeroed by the 1152 reservation; `cave_canraze` byte-unchanged after.
  **12d** the same report on the **TACTICAL (modal)** path, in `cave_razedone` — the `combat[+0x2C]`
  completion callback, which filed nothing for anybody. Traced, not assumed: `TCombat.Initialize`
  calls `LockExecuted` from its own `+0x8` (`0x55727C9C`, `inc combat[+0x28]`) and `TCombat.Finalize`
  unlocks at its tail, so on the tactical path that count goes
  `0→1→0` and the callback fires **inside `Finalize`** — after the `SetFinalData` call at
  `Finalize+0xa0` = `0x55727ED8` (the function is `TCombatLogbook.SetFinalData@0x55728E44`), before any
  `DestroyCombat`. ⚠⚠ **Two things differ from 12b and both are required.** `DL=0`
  (`EVENTLOG_SHOW_MODAL`), because the tactical raze is only ever reached by the local human, who
  just *watched* the fight — and because vanilla's own modal `combat[+0x2C]` callback
  (`TArmyCombatMoveTE.CombatExecuted@0x557496D4`, tail `0x557498F5`) uses `xor edx,edx`. And the call
  must be wrapped in `SynchroniseBegin`/`End` (`0x557755F8`/`0x55775600`, `inc`/`dec map[+0x234]`):
  `TEventLogbook.AddEvent@0x557FDB90` **asserts** `GetSynchronised@0x55775608`, which 12b satisfies
  only because its site runs inside the raze TE — this callback fires outside it. Omit the wrapper
  and the modal path raises an `EventLog.pas` assertion. No double-filing: a module-wide scan finds
  exactly three callers of `0x5572928C` before this stage (four after), no other module imports it,
  and vanilla's modal filer can
  never run for our combat because `cave_towerraze` owns `combat[+0x2C]`. ⚠ **`cave_razedone`
  RELOCATED `0x5580D3D0`→`0x5580D500`** (138→174 B, past the old slot's 144; `RAZEDONE_RESV=0x100`
  ends exactly on the seed reserve) and the vacated slot is **zero-filled**; `LOOTBATTLE_RESV=0x60`
  added. The two reservations absorb orphans 12c never reached — 23 B of pre-v2 `cave_lootbattle` at
  `0x5580D4E3` (starts mid-instruction) and a 55 B pre-Stage-10 copy of `cave_rebelchance` at
  `0x5580D550`; both proved unreferenced in every section, zero `.reloc` entries. §4.4.3a.
  Zero new RNG draws (`rng_audit --owners`: no new site); reloc audit 0. ⚠ The first apply minted a
  **fake** `backups\AoWEPACK.dpl.pre-razedlgfix` from the already-patched file; it was deleted and the
  backup line now gates positively on `VMT_ORIG` — so **no snapshot exists for this feature**, which
  is correct, because there was no unpatched file to take one from.
  **12e** (2026-09-12) the region is now **closed**: `CANRAZE_RESV=0x20` / `SKIPAVENGER_RESV=0x60` /
  `REHOME_RESV=0x100` absorb the last three orphans, which 12c and 12d both missed because each
  reserved only the caves it happened to be editing — an 11 B **complete, enterable** duplicate of
  `cave_canraze` at `0x5580CDA0`, the 27 B pre-relocation `cave_forcefail` at `0x5580CDE0`, and a 5 B
  `cave_rehome` tail at `0x5580D040`. Deadness re-proved at 12e rather than inherited (every `E8`/`E9`
  rel32, every literal dword in every section, all 63,880 `.reloc` entries: zero references).
  ⚠ **Both rel8 candidates a linear scan throws are false positives** — `0x5580CDEB` is the orphan's
  own internal `je`, and `0x5580CFEC` is byte 3 of a displacement, not an instruction boundary.
  12d's positive on-disk guard is generalised to all three (zeros, our own bytes, or *only* the named
  orphan — else abort), and ⭐ **the orphan exemption lapses after the apply**, so a re-run re-proves
  they are gone instead of whitelisting the addresses forever. Verified: "already applied"; all three
  spans and all three growth zones zero; all eleven caves **and** both foreign neighbours
  (`cave_valfix`, the seed cave) byte-unchanged; reloc audit 0; file size unchanged; ⭐ a sweep of
  `0x5580C910..0x5580D640` now finds **zero non-zero bytes outside a known cave span**. Byte hygiene
  only — no cave's code moved or changed, so **nothing new to test in-game**. §4.4.11.
  **In-game checklist:** (1) lose a city to a rebellion, then click the rebel garrison — a **gold
  join offer** must appear, at a **non-zero** price; (2) same for a garrison that beat a city raze and
  one that beat a city loot; (3) ⭐ over several turns, that city garrison must **stay on the city
  hex and still fight when attacked** — 12a removed its AI group, and Stage 11 had added the Guard AG
  precisely to stop `THuntAG` wandering, so drifting off would mean group-less is worse than what it
  replaced (vanilla parity is byte-verified for *placement* only); (4) confirm a **structure**
  loss-garrison (tower/mine/farm) still holds position — it keeps Guard kind 2 and must be unaffected;
  (5) fight a fast rebellion **against a defended city** as a third party who can see the hex, and
  confirm a combat report lands in **your** log and replays; (6) confirm the city's owner gets one
  too; (7) confirm a normal (non-raze) fast battle's report is unchanged; (8) confirm the avenger
  spawns after an ordinary raze still vary (the 1/8 raider flavour still rolls);
  **12d:** (9) Combat Resolve Mode = **Tactical**, raze a **defended** structure of your own, fight
  it out — the report must be **in your log** and must **not** auto-open (`DL=0` working, not a
  failure), and a third party who can see the hex must get one too; (10) ⚠⚠ **watch for a
  `D:\AoWDev\AoWE\EventLog.pas` assertion dialog as the combat screen closes** — that is
  `GetSynchronised` failing and is this stage's single most likely failure mode; (11) repeat for a
  tactical **loss** (result 4: the Guard loss-garrison with the literal survivors must still spawn —
  the report files *before* the garrison, so a regression shows as a missing garrison), a tactical
  **stalemate** (result 2), and a tactical **city** raze; (12) Ask mode → *quick* must behave exactly
  as 12b did. ⚠ **Rebellion and loot need no tactical test** — both pack choice = fast into the
  `ExecuteRaze` arg (`owner|0x50` / `owner|0x90`) and can never reach `L3_tactical`; 12b covers them.
  ⚠ **(5)/(6) must use a DEFENDED target.** A walkover sets result `6`, and
  `DistributeCombatEvent`'s replay gate is `cmp byte ptr [eax+0x30],6 / je` at `0x55729367` where
  `finaldata[+0x30]` is a verbatim copy of the result byte (`0x55727F77`) — so an undefended target
  files the report for every witness and deliberately never pops it up. Vanilla behaves identically
  for ordinary fast combats; testing on an undefended city produces a false failure.
  **12f** (2026-09-12) `L3_tactical` passed the **COMBAT** to `DestroyCombat`, which takes the **MAP**.
  Pre-existing (byte-identical in `backups\AoWEPACK.dpl.pre-panicnomelee`), found by QA on the 12d pass
  and given its own pass. `0x5580CC6A` `mov eax,[ebp-0x18]` → `mov eax,[ebp-0x14]`; one operand,
  `8b 45 e8`→`8b 45 ec`, size-neutral, both call sites keep their addresses. ⭐ **Vanilla settles it**:
  `TArmyCombatMoveTE.ExecuteCombat` has the byte-identical `cmp al,1 / je` at `0x55749BAB` and its
  `AL != 1` fall-through does `mov eax,[0x558fa040] / call 0x557787f8` at `0x55749D09` — the map.
  ⭐ **Reachability was proved, not assumed.** The tactical path does **not** run `TCombat.Execute`:
  `CreateCombat(0x220110)` builds a **`TTacticalCombat`** (`AoWTCPCK.dpl` VMT `0x00413314`, inst `0x50`
  — the only `TCombat` descendant outside `AoWEPACK.dpl`), whose slot `0x64` `@0x004295E8` returns 1 at
  **exactly one instruction**, `0x00429992`, and only after `TAoWCombatMap.NewTurn`, i.e. once the modal
  screen is actually up. Three earlier exits all return non-1: `8` (`ValidateWallCombat` — *not*
  reachable for a raze, the Stage-5 wall fix zeroes the `party0[+0x18]` it tests), `2`
  (`side1.GetCount() == side1[+0x18]` @`0x00429667` — **the only live exit**), and `6`
  (`side1.GetCount() == 0` @`0x004296B9` — **dead code**). ⭐ `side[+0x18]` is written only by
  `TCombatSide.UpdateSettings@0x55727038`, reached from `TCombat.Activate+0x8d`, which the cave calls
  before `Execute`; it counts objects with `[[obj+0x14]+8] > 0 && [obj+0x30] == 0`. Since it is zeroed
  and incremented at most once per entry of the list `GetCount()` counts, `GetCount()==0` forces
  `side[+0x18]==0` — so an empty militia side short-circuits with result **2**, never 6. ⚠ `Lempty`
  screens a militia **army** with no units, not a militia **side** that lands zero combat objects.
  ⚠⚠ **A flyer-vs-walkers standoff is NOT this branch** — that is a *fought* stalemate (`Execute`
  returned 1, screen opened, `UpdateStatus` wrote 2 later), finishing via `cave_razedone` at modal
  close. All three exits fire before `TRndTacHsm.RandomMap@0x004296DC` generates the tactical map.
  ⚠ No in-game recipe for exit 2 on a non-empty side is known — `[obj+0x14]`/`[obj+0x30]` are undecoded. Old behaviour: `TTacticalCombat` is
  `0x50` B, so `[combat+0x120]` read `0xD0` B **past the object** — zero ⇒ silent bail, `map[+0x120]`
  stuck, every later battle raises "Combat already created"; non-zero ⇒ a virtual call through a wild
  pointer. ⚠ **The Open-items claim that this also stranded `FLAG_RAZEASYNC` was wrong** and is deleted:
  `TTacticalCombat.Finalize` chains to `TCombat.Finalize` (`0x0042952D`), whose tail unlocks `1→0`, so
  `cave_razedone` **does** fire here and clears it — an extra clear would be dead code. Reloc audit 0;
  zero new RNG draws. **In-game:** (13) the modal path (`AL=1`) must be unregressed — a tactical
  raze fought to a result must still raze/garrison and file its report; (14) repeat for a tactical
  **city** raze. ⚠ **The fixed branch itself has no known repro** and (13)/(14) do not exercise it;
  its only observable is the *absence* of a later "Combat already created". Latent-defect fix, verified
  against vanilla's own `0x55749D09`. §4.4.3b.
  §4.4.3 / §4.4.7 / §4.4.9 / §4.4.11.
- AI paths to and searches exploration sites — 2026-09-03
- City raze as a real battle (Stage 9), and AI non-city scorched-earth allowance (v6)
- City loot gold multiplier (9× → 10×) — 2026-07-12
- Arena — dialog re-layout, empty-state sprite
- Exploration-site and non-city raze defender roster variation

### Engine — `11-engine-internals.md`
- Registry isolation — `HKCU\Software\Triumph Studios\Age of Wonders` → `…\Age of Wonders Z`. ⭐ **The point is side-by-side installs, not settings**: `Startup Directory` is the data root, so before this, two copies of the folder both loaded `Release/`, `Dict/`, `Images/` from whichever one wrote the key last. 🔨 APPLIED, UNTESTED 2026-09-09: `build_regiso.py`, 9 in-place Delphi-const edits (6 in `AoWEPACK.dpl`, **3 in `AoWSetup.exe`** — Inioch's write-up misses those), no cave, no hook, surgical `--undo`. Registry seeded the same day. ⚠ 43-character ceiling on the path. ⚠ Which key a folder uses is a property of the FILES in it — a copied folder is a second `Z` install, not a vanilla one
- AoWSetup install check collapsed to Install/Exit after the above. Cured by `build_aowsetup_installcheck.py` — ✅ CONFIRMED WORKING 2026-09-09 — Inioch's `'.'` fallback: call-rel32 retarget at `0x004675A0`, cave `0x00469820` (31 B, **next free `0x00469840`**, R-X). ⚠ `0x0046719C` is `ret 8` — the cave re-pushes its own args. ⚠⚠ **The cause is still unknown, and the fix proves it is worse than it looked**: the fallback only fires on a nil read, so `TRegistry` really was failing in-process on a key that reads fine out-of-process. AoWEPACK reads the same tree — the isolation is unproven until the game's own settings are shown to persist there
- Mind Decay — MP determinism + nil-check — 2026-09-03
- **TE exception detail — ⚠⚠ DIAGNOSTIC, `--undo` it before cutting a release.** The
  "Exception occured during `<TE>`" dialog is followed by a second one naming the real fault:
  `Exception <class> in module <module> at <offset>.` 🛑 **REVERTED 2026-09-13** — undone for the
  2026.09.13 release and **not currently installed**; `--apply` again to diagnose, and expect the
  manifest to move `CHANGED 52 → 53` / `SAME 844 → 843` when you do. Was 🔨 APPLIED, UNTESTED (2026-09-11):
  `build_te_exception_detail.py` on **`Ziggurat/Network.dpl`** (5 B at `0x55803DD2`, the
  `call Dialogs.ShowMessage` inside `NetworkE.TTokenExecuter.ExecuteTokenEvent @0x55803D24`;
  cave `0x55806210`, 150 of `0x1F0` B; snapshot `backups\Network.dpl.pre-texcdetail`; surgical
  `--undo`). ⭐ **DECODE: static VA = `<offset>` + the named module's preferred base** —
  `AoWEPACK.dpl 0x55700000`, `Network.dpl 0x55800000`, `HSEPack.dpl 0x55600000`,
  `aowInt.dpl 0x59800000`, `Dcpack.dpl 0x55100000`, `vcl30.dpl 0x41300000`,
  `AoWz.exe`/**`AoWTCPCK.dpl` both `0x00400000`**. Built for the walled-structure
  `TArmyCombatMoveTE` bug, but it locates **any** TE fault — the engine discards the exception
  object at `0x55803DD2`, so without this every turn-event crash in the game is unlocatable by
  design. Ported from Inioch's v2; full record + cave + RTL deltas in `12-re-toolchain.md` §3a.
  **In-game checklist:** reproduce the bug, dismiss the stock dialog, read the second one, decode,
  then `--undo`
- Firmament map level — a 4th map level at index 3, filled with Sky terrain `0x0E`, surface-like vision, global-target spells, storm spells and Bird's View. 🔨 APPLIED, UNTESTED 2026-09-06 (v2): `build_maplevel4.py` (cap byte `0x5577768E` `03→04`, cave `0x55844000`, 250 B, 8 hooks) + in-place cave re-tunes of `build_shipyard_income.py` and `build_waterheal.py` (v6: earth elementals excluded from the Firmament, air elementals included); UI half `build_skylevel_ui.py` (v3, caption "Firmament") + editor Level Up/Down display order `build_deved_levelnav.py` (`AoWDevEd.exe`, `AoWEd.exe`). Target binaries: `Ziggurat/AoWEPACK.dpl` + `Ziggurat/AoWz.exe` + `Ziggurat/AoWzCompat.exe`, not the DLL alone. Editor New-Map dialog and the map-gen tools still to do

---

## Open items — unresolved, with the check that would settle each

0b. ~~Turn Undead and Dispel Magic levels above I are never applied~~ **FIXED 2026-09-10, 🔨 APPLIED,
   UNTESTED** — `build_inherent_level_fix.py` on `AoWEPACK.dpl` (two VMT dwords, 6 bytes, no cave:
   `0x5571FE90` and `0x55721E0C` `+0x94` -> each class's own `GetLevel`; snapshot
   `backups\AoWEPACK.dpl.pre-inherentlevelfix`; surgical `--undo`, sha256 round-trip verified).
   `build_leadership_fix.py`'s `cave_abinherent` had made the grant compare `GetInherentLevel`, which
   `TTurnUndeadAbility` and `TDispelMagicAbility` inherit from the base as `return 0` — so buying
   either past level I deducted the points and applied nothing. ⚠ **The user's in-game checklist is
   outstanding** — see `02-abilities-modded.md` §B′, especially item 3: the fix also changes the hero
   level-up dialog's Cost column and Remove button for these two abilities, via four
   `GetInherentAbilityLevel` sites **in `AoWz.exe`** that a DLL-only scan missed.

1. **Storm effect roll's RNG generator.** It reaches `HitRole` (RAW) from a non-combat,
   non-re-anchored context with no sanctioned reseed bridge. `rng_audit.py` classifies it "already
   SYNC" with no per-site reasoning, and structurally cannot see this class of bug. **Settle with an
   in-game MP test across several turns**, watching for a late unrelated out-of-sync dialog.
2. **`build_turnundead_res.py`'s verifier is broken.** Running it reports `[x] cave zone 5580E2A0
   not free` against its own installed patch — a keystone encoding difference (`shr eax,1` assembles
   as 2 bytes where the installed form is 3). The feature works; the script cannot recognise its own
   state and hands a future session a false alarm.
3. **`build_magebane.py --undo`** zeroes its whole `0x200`-byte cave unconditionally
   (`build_magebane.py:499`). Its effect on Shield's chained cave has never been verified.
4. **Cave `0x5580DB40` is double-claimed.** `build_icestorm_lava.py`'s `CAVE2` occupies it live;
   `build_raiseterrain_mtn.py` declares the same address and expects zeros. That script is correctly
   shelved and its verify-before-write aborts cleanly, but it **can never be applied as written**,
   and neither script mentions the other.
5. Several strategic-map hazard DAM immediates (Town Quake, Poison Plant, both Grounds) are confirmed
   doubled only by a stage-count, not by an individual address. Byte-diff to confirm.

## Settled this session — do not re-litigate

| question | answer |
|---|---|
| Parry's attack penalty at `0x55767BE3` | **`0x08`** (live byte read). The `04` figure was wrong. |
| Is ability id `0xCD` a save-format ceiling? | **No.** `Engine.TPropertyTable.SaveToStream @0x5550FD0C` widens to (u32,u32) whenever `tag > 0x7F`. ⚠ Nothing above `0xCD` has been run in-game — untested, not proven-safe. |
| Ability `0x77` | **Entangle Strike**, applying Entangled `0x5E` — not "Death Strike". |
| Was Turn Undead's `GetTouchAttack` left un-doubled? | **No, it was doubled** — live bytes return 18/20/22/24/8. The long-standing claim that it kept vanilla's 9/10/11/12 was wrong. |
| Who owns `imul eax,eax,5` at `0x55725D9F`? | **`build_hitslope5.py`** — not an "undocumented hand edit". |
| Site-defender rosters | produced on **day 1**; `ExecuteSearch` only spawns what already exists. |
| Were the `Images/_*.ILB` faces "halved by a modding accident"? | **No — `_NAME.ILB` is AoW1's half-resolution twin of `NAME.ILB`, by design.** 86 pairs in `Images/`, 85 parse, **all 85 exact half-size**. Restoring a `_` set to full size destroys the low-res artwork. The real defect was 12 added hero faces sitting in `_H_Faces.ILB` at full size and missing from `H_Faces.ILB` — fixed by `build_faces_hires.py`, see `07-ui.md` §7. |
| `Modding Resources/backups/` | **deleted 2026-08-08.** It does not exist. 36 files referenced it. |
| `<root>/backups/` | **deleted 2026-09-10** (29 `.pre-*` snapshots, 52 MB, sitting inside the pristine vanilla install). `Ziggurat/backups/` is where scripts mint now, and it does not exist yet — it is created on demand. |
| Does any `.pre-*` binary snapshot survive? | **No.** Zero `*.exe.pre-*` and zero `*.dpl.pre-*` anywhere in the tree (measured 2026-09-10). Only 10 **data-file** snapshots remain — `.ILB`, `.pfs`, `.ail` — and each exists twice, once at the root and once in `Ziggurat/`. Revert is always the script's surgical `--undo`. |
| Zip or installer? | **Installer** — owner ruling 2026-09-11 supersedes the 2026-09-07 "plain zip" decision, which is now deleted from `12-re-toolchain.md` §13.3. Inno Setup 7, `installer/Ziggurat.iss`. A zip cannot copy the player's own vanilla data into `Ziggurat\` (that is what keeps the download 18 MB instead of 370) and cannot write the `Age of Wonders Z` registry key. |
| Does the installer ship the manual? | **No** — the Pages site is the manual and the changelog. Nor its **builder**: `build_ziggurat_manual.py` + `Ziggurat Manual.html.build.json` joined `NEVER_SHIP` on 2026-09-13, payload 347 → 345. |
