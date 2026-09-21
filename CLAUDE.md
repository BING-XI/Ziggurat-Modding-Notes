# Age of Wonders (1) — binary modding project

This directory is a **pristine vanilla AoW1 install** with Ziggurat riding on top as an overlay.
Mods are applied as **binary patches** to the game's Delphi 3 modules (`AoWEPACK.dpl`,
`AoWTCPCK.dpl`, `aowInt.dpl`) and executables — no source, no new DLLs. All reverse-engineering
notes, patch scripts and the RE toolkit live in **`Ziggurat/Modding Resources/`**.

**Start at `Ziggurat/Modding Resources/Zig notes/00-INDEX.md`.**

## ⭐⭐ ALL ZIGGURAT WORK HAPPENS INSIDE `Ziggurat/` — owner's rule, 2026-09-09 — IMPORTANT

```
<game root>\                 a stock GOG install, byte-clean, CHANGED(0) vs the hashdb
   AoW.exe  AoWEPACK.dpl …   VANILLA. 33 packages + data. NEVER PATCH THESE.
   goggame-*.hashdb          the vanilla manifest; mod_manifest.py reads it from HERE
   backups\                  ⚠ pre-move snapshots, orphaned — see below
   Ziggurat\
      AoWz.exe  AoWzCompat.exe   the LIVE mod exes — run from here, patch THESE
      AoWzEd.exe                 the Ziggurat-oriented editor (live; runs from here)
      AoWEPACK.dpl …             33 packages: 6 modified + 27 copies  <-- PATCH TARGETS
      Release\ Dict\ …           the mod's data root (1883 files)
      build_ziggurat_manual.py   the Manual builder + `Ziggurat Manual.exe`
      Modding Resources\         scripts, notes, RE toolkit, bundled reference assets
      Ziggurat release\          release payload / staging — NOT a patch source
```

`Ziggurat/` carries **all 33** packages, not just the 6 modified ones, because every Ziggurat exe runs
from that folder and resolves its imports there. ⚠ Do not "tidy" the 27 copies away — that invariant
is what lets the binaries be patched directly, with no rebuild step.

**A bare filename in a build script means the file in `Ziggurat/`, never the root.** The root copies
are vanilla and shared with the vanilla game; patching one corrupts vanilla and does nothing to the
mod.

⭐ **The existing path idiom already does the right thing — do not "fix" it.** Scripts live at
`Ziggurat/Modding Resources/build_scripts/`, so `__file__/../..` resolves to `<game>/Ziggurat`:

```python
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
```

Every pre-existing script therefore targets the mod correctly with **no edit**, purely because the
workshop moved inside the overlay. ⚠ **`AOW_GAME_DIR`, if it is ever set, overrides this and will
silently send every patch to the wrong tree.** Leave it unset.

⚠⚠ **The number of `..` depends on the script's depth, and getting it wrong now lands on VANILLA.**
Two `..` is right for `Ziggurat/Modding Resources/build_scripts/`. Scripts one level shallower, in
`Ziggurat/Modding Resources/` — `build_mod_manual.py`, `ai_combat_spell_antispam_patch.py` — need
**one**:

```python
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, ".."))
```

Copying the two-`..` form into a shallow script resolves to the **game root**, which used to be the
mod and is now the vanilla install. It reads or patches vanilla and reports success.

⭐ **Better: anchor on contents, not on depth.** `build_ziggurat_manual.py` has now lived at two
depths and counting `..` broke it both times, so it walks up looking for a folder that *contains*
`Release/` instead. Prefer that for anything that might move.

### ⚠ Two things the move broke quietly — both fixed 2026-09-09, both worth recognising again

- **`mod_manifest.py` could not find the hashdb.** `goggame-1207658883.hashdb` describes the
  *vanilla* install and stayed at the root, while `GAME` became `Ziggurat/`. It failed **silently**:
  empty report, exit code 0. It now looks in `GAME` then the parent. Comparing `Ziggurat/` against
  that manifest is still exactly right — CHANGED means "differs from stock", ADDED means "new".
  ⚠ Its filter lists (`IGNORE_DIRS` / `NEVER_SHIP` …) have **not** been re-reviewed for the new
  layout: the 29 MB `Ziggurat Manual.exe` and the renamed exes now land in the payload, which is why
  it reports 126.7 MB against the pre-move 93 MB, and `MISSING (4)` is the hashdb expecting
  `AoW.exe`/`AoWCompat.exe` in a tree where they are now `AoWz.exe`/`AoWzCompat.exe`. Decide what
  should ship before cutting a release from it.
- **`build_ziggurat_manual.py` lost every one of its ~20 workshop paths.** They were anchored to the
  folder it used to live in. The workbook miss failed loudly; the `re_tools` miss failed **silently**
  — `pfs.py` not found, unit stats fell back to the workbook, and the manual built with 0 units
  instead of 189 while reporting success. Anchors are now `GAME` / `_WORKSHOP` / `RE_TOOLS`.

### `backups/` — the old snapshots are orphaned at the root

`BACKUP_DIR = os.path.join(GAME, "backups")` now means `Ziggurat/backups`, which does not exist yet;
the 29 pre-move `.pre-*` snapshots sit in `<root>/backups`, i.e. inside the **vanilla** install, and
are snapshots of *modded* binaries. They are still valid inputs to a script's `--undo`, but nothing
will add to them. Leave them or move them deliberately — do not assume a script's `--undo` will find
one there.

### The Ziggurat Manual

`build_ziggurat_manual.py` and `Ziggurat Manual.exe` both live in **`Ziggurat/`** (moved out of
`Modding Resources/` on 2026-09-09). `build_manual_exe.py` builds the exe there.

#### ⭐⭐ "Update the mod" INCLUDES publishing the manual — owner ruling 2026-09-16

**When the owner says "update the mod", "push an update", "push a release" or similar, the Pages
manual is part of that job, not a separate errand.** Do it without being asked again.

The reason it cannot look after itself: **the published manual is a STATIC SNAPSHOT.** The builder
reads the live binaries and `.pfs`/`.ail` files *on this machine* and bakes the numbers into HTML.
The page then reads nothing, ever — not the installer, not the player's install. Shipping more of
the mod would not change that, because all the reading happens at build time, here. The only thing
that moves the published page is re-running the builder and pushing the output.

So every mod update ends with:

```bash
python build_ziggurat_manual.py --public --out "Modding Resources/site/index.html"
cp "Modding Resources/site/index.html" "Modding Resources/gh-repo/index.html"   # then commit + push
```

⭐ **Run it every time — it is never wrong and almost never costs anything.** The build is
content-hash cached over ~107 declared inputs *plus whatever the last build actually opened*, so it
prints "up to date" and writes nothing in ~0.4 s when the mod has not moved. ⚠ Never `--force` to
"make sure"; that defeats the cache's whole purpose, which is to tell you whether anything changed.

⚠⚠ **`--public` is mandatory, and `Ziggurat Manual.html` must never be published.** The authoring
build carries three in-browser editors, one of which embeds the whole of `Unitres.pfs` as ~211 KB of
base64. It was published by accident on 2026-09-11. Full account: `12-re-toolchain.md` §14.6.

⚠ **The trigger is the owner's request, not a file change.** Nothing watches `Ability.pfs`. A
scheduled watcher was built and rejected 2026-09-16 — on a timer it would publish mid-edit states
unattended, and it needed a long prompt to stay safe about `--public` and content collapse.

The exe is a thin runner: it executes the **on-disk** builder when one sits beside it, so editing the
builder needs no rebuild. Since 2026-09-09 it also **bundles** a fallback copy plus everything a
player lacks — the workbook, `re_tools/`, `Release - Vanilla/`, `spell_names.json` — so a shipped
Manual works standalone (verified with the on-disk builder removed: identical 189 units / 116
passives). On-disk always wins. ⚠ Re-run `build_manual_exe.py` when the **workbook or `re_tools`**
change, not just when imports change — the bundled copies are snapshots.

### The Ziggurat binaries — no indirection, patch them directly

`Ziggurat/AoWz.exe` (and `AoWzCompat.exe`, `AoWzEd.exe`) run **from `Ziggurat/`** and resolve every
package from that folder, so they are the live files. Patch them and the change is live — there is no
derived copy and no rebuild step. Same for `Ziggurat/AoWEPACK.dpl` and the rest.

⭐ **This works because `Ziggurat/` carries a COMPLETE package set — all 33, not just the 6 modified
ones.** That is the load-bearing invariant of the whole layout. ⚠ Remove the 27 unmodified copies to
"save space" and every exe in the folder dies with `STATUS_DLL_NOT_FOUND`, naming nothing.

⚠ `Ziggurat/AoWDevEd.exe` is not live — `Ziggurat/AoWzEd.exe` is, built by `build_zigeditor.py`.
The copies under `Ziggurat/Ziggurat release/` are release staging, refreshed by
`re_tools/mod_manifest.py --stage`, and are **not** a patch source — patching those would be
discarded by the next staging refresh.

**Retired 2026-09-09: `build_overlay.py` and the root `AoWz.exe`/`AoWzCompat.exe`.** Until then the
exes lived at the vanilla root with their import names rewritten to `Ziggurat\<pkg>.dpl`, which made
every exe patch a two-step that failed silently if you forgot the second. Copying the full package set
into `Ziggurat/` for the editor removed the need, so the exes moved in beside their packages and the
indirection went away. The RE is kept — it is a genuinely reusable technique — in
`Zig notes/12-re-toolchain.md` §13a, along with the reason it is no longer needed here.

### What the overlay rests on

- **Registry isolation** (`build_regiso.py`) — the mod reads
  `HKCU\Software\Triumph Studios\Age of Wonders Z`, vanilla reads `…\Age of Wonders`. That key's
  `Startup Directory` = `<game>\Ziggurat\` is what moves the data root. Break it and the mod loads
  vanilla's data.
- **A complete package set in `Ziggurat/`**, so its exes need no import surgery.
- The vanilla data at the root is shared, so the overlay costs ~373 MB rather than a second install.

---

## Where knowledge lives

| | holds |
|---|---|
| `build_scripts/build_*.py` | the patch itself, and — in its module docstring — the addresses, the cave assembly, the failed approaches, the `--undo`. **For an atomic single-cave feature the script IS the record.** |
| `Zig notes/NN-*.md` | twelve thematic files. Cross-feature knowledge, engine mechanics, multi-stage design history, and every in-game checklist still outstanding. |
| the live binaries | the truth. Everything else can be stale. |

Twelve files, by topic: `00-INDEX`, `01-combat-maths`, `02-abilities-modded`, `03-abilities-added`,
`04-spells-modded`, `05-spells-added`, `06-unit-spellcasting`, `07-ui`, `08-editor`,
`09-terrain-movement`, `10-ai-and-structures`, `11-engine-internals`, `12-re-toolchain`.
Plus `Inioch.md` for the fellow-modder material.

## Recording convention

**Record at APPLY time, not at confirmation time.** The moment a patch is written to a live binary,
add its section and its `00-INDEX.md` row with status `🔨 APPLIED, UNTESTED (date)`.

### The status ladder — every feature carries exactly one

| status | means | who sets it |
|---|---|---|
| `SPECULATIVE` | analysed / designed, **not** applied | anyone |
| `🔨 BUILT, NOT APPLIED (date)` | script exists and dry-runs clean; nothing written | anyone |
| `🔨 APPLIED, UNTESTED (date)` | written to a live binary; static checks pass; **nobody has played it** | anyone |
| `✅ CONFIRMED WORKING (date)` | the user tested it in-game and it works | **only the user's test** |
| `🛑 REVERTED (date, why)` | applied then backed out — keep the RE, say why | anyone |

**Never label something confirmed on your own say-so.** Static verification, byte-checks, QA passes
and clean `--undo` round-trips justify `APPLIED, UNTESTED` and nothing more. This project has proved
it repeatedly: a cave that ran at package init passed every static check and broke startup (Embrittle
v1, runtime error 216); a PIC anchor `0x4C` short assembled, verified, and read the wrong memory
forever.

⭐⭐ **A cave that runs at package init must be proved by LAUNCHING THE EXE.**

### An `APPLIED, UNTESTED` record must carry

Addresses, cave VAs + byte counts, struct/field offsets, the *why*, the script's `--undo`, and **the
in-game checklist the user still needs to run**. Drop the checklist when the status goes green — that
is usually the whole edit.

**Cross-feature couplings are the expensive thing.** Record them as a *forward* hazard — "X and Y
share cave `0xNNNN`; applying X after Y clobbers it" — not as revert ceremony. The canonical
cave-ownership table is in `12-re-toolchain.md`; add to it whenever you allocate.

### Superseded analysis — delete it unless it earns its place

Default: **delete the wrong text** and put the correct finding in its place. No `SUPERSEDED` banners,
no strikethrough, no "the verdict below is wrong" preambles — a wrong analysis left in the record
costs every future session the time to read it *and* re-adjudicate it.

**A failed approach is not automatically worth keeping** (ruling 2026-09-03). Once the working method
is recorded, most failures are distracting bloat. Keep one only if it passes **both** tests:

1. **Would a competent person plausibly try it first?** — it is the obvious or tempting move.
2. **Does the working method fail to explain why it doesn't work?** — if reading the correct method
   already makes the failure obvious, the failure adds nothing.

Keeps, by that test: *widening a bounded table in place rather than relocating it*; *testing
hero-ness by VMT instance size instead of `IsClass`*; *reusing `hss_crc.py` on a `.pfs`* (wrong
covered region). Cuts: process notes ("don't test three changes in one pass"), restatements of a
rule already given, and any failure whose reason is simply the working method's own rationale.

Also keep **reusable machinery** found along the way (addresses, call paths, struct offsets) even
when the conclusion built on it was wrong. When anything stays, compress it to a single bullet — the
approach, and the one-line reason it fails. **Never list the same failure twice in one file.** Fix
invalidated claims **at the source**, never by appending a contradiction.

## How patches are built

- **One Python build script per feature** in `Ziggurat/Modding Resources/build_scripts/` (`build_*.py`,
  runnable from anywhere). Keystone-assembled caves, capstone-disassembled for review, **dry-run by
  default / `--apply` to write, idempotent, verify-before-write (aborts on byte mismatch)**.
  Re-running with no args verifies current state.
- **Revert = the script's surgical `--undo`.** ⚠ Not every `--revert` flag is surgical —
  `build_mapcursor_fix.py --revert` merely restores a snapshot. Read the implementation first.
- **Re-tuning is an in-place cave rewrite**, never revert-and-reapply: verify against *either* the
  installed bytes or the new ones, overwrite, assert the growth zone is still zero.
  `build_invis_penalty.py` is the worked example (it rewrites caves owned by `build_trueseeing.py`).
- **`.pre-*` snapshots are not a revert path.** They accumulate (every `--apply` mints one), only the
  newest per file is ever a safe single layer, and a restore wipes every layer applied afterwards.
  Prune them; do not rely on them. The binary stack was deleted on 2026-09-03 and the last loose
  data-file snapshots on 2026-09-10 — **three remain**, all in `Ziggurat\`:
  `Images\Combat.ILB.pre-coppermedal`, `Images\_Combat.ILB.pre-coppermedal`,
  `Int\Scenes\BookWin.ILB.pre-glowilb`. They were kept because `build_copper_medal.py` and
  `build_glowilb.py` are the only two of their cohort with **no `--undo` at all**, so for those two
  features the snapshot is the only route back. Everything else reverts through the script.
  ⚠ A recursive `find . -name '*.pre-*'` is the only honest check — these live beside their targets
  in `Images\`, `Release\`, `User\`, `Int\Scenes\`, so a top-level glob reports a clean tree.

### ⚠ A `.pre-*` snapshot goes in `<game dir>\backups\`, never the game root

**Rule, 2026-09-03.** Any script that mints a snapshot writes it to a dedicated subfolder, created on
demand. The game root holds the game, not 200 MB of drifting copies — at last count the root carried
88 snapshots totalling 199 MB, which is what forced the clean-out.

```python
BACKUP_DIR = os.path.join(GAME, "backups")           # GAME = <game>/Ziggurat, per the rule above
os.makedirs(BACKUP_DIR, exist_ok=True)
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-<feature>")
```

Keep the existing `<binary>.pre-<feature>` naming — only the directory changes, so
`Ziggurat\backups\AoWEPACK.dpl.pre-vision9`. ⚠ This is **not** the old `Modding Resources/backups/`, which was
deleted 2026-08-08 and is gone for good; this one sits beside the binaries.

⭐ **The migration is DONE (2026-09-10): 158 of 176 `build_scripts/*.py` now use `BACKUP_DIR`, and
none writes a snapshot beside its target.** The remaining files mint no snapshot at all. The bulk
edit that this note used to warn against was run in three passes and verified — 176 files parse,
every one dry-runs without a traceback, and neither `backups\` directory exists afterwards, which
proves no `makedirs` fires outside `--apply`.

⚠ **The snapshot path hides in five shapes, and a grep for one finds a third of them.** In order of
discovery, each found only after the previous predicate came up clean:

| shape | example |
|---|---|
| module constant | `BACKUP = TARGET + ".pre-x"` |
| write-path local | `bp = path + suffix`, inside the `--apply` branch |
| helper default | `def process(path, base, suffix=".pre-assassin")` |
| bare suffix constant | `SUFFIX = ".pre-coppermedal"`, joined elsewhere |
| **filename and suffix fused** | `BACKUP = os.path.join(GAME, "AoWEPACK.dpl.pre-spellcast")` |

The last one has no `+` and no separate suffix, so both of the first two predicates missed all five
files carrying it. `grep -L BACKUP_DIR` over everything containing a `.pre-` literal is the check
that actually terminates.

⚠⚠ **A snapshot must be minted on `--apply` ONLY.** `--undo` and `--revert` usually run through the
same write path, so an ungated snapshot copies the **patched** file to a name that reads as
pre-patch. Fixed 2026-09-10 in `build_embrittle_pfs.py`, `build_effectroll.py` and `build_patch.py`;
`build_panic_cleardamage.py` is the model, gating on a proven-unpatched hook site. This stayed
invisible for months because a stale snapshot already sat at the old path and the `if not exists`
guard short-circuited. Moving the directory and pruning the strays made the gate load-bearing.
- **Caves must be position-independent** (rel32 / register-only, no absolute mem refs) — the `.dpl`
  packages rebase at runtime. Exe caves (fixed base `0x400000`) may use absolute addresses.
- **Per-executable patches only affect that binary.** `AoW.exe` and `AoWDevEd.exe` are different
  builds and often call *different* functions for the same feature. Verify the call path per binary.
- **`AoWCompat.exe` is NOT a separate binary to analyse.** It is `AoW.exe` with exactly one byte
  changed — file offset `0x3BB7C` (VA `0x43C77C`), `0x0F` → `0x05`. Every AoW.exe finding applies
  verbatim; patch both in lockstep; recreate by byte-flip if lost.

### Pristine references — the GAME ROOT is now the reference (2026-09-09)

**The vanilla install at the root is itself the byte-diff baseline.** `mod_manifest.py` reports
`CHANGED(0)` against the GOG hashdb, and the root's `AoWEPACK.dpl` is byte-identical to
`AoWEPACK_original_backup.dpl` (both `08149246b0`, verified). So "is this vanilla?" is now answered by
comparing against `<root>/<name>` directly — no special copy required, for **any** module, including
the ones we never had a pristine copy of (`aowInt.dpl`, `AoWTCPCK.dpl`, `HSEPack.dpl`, `Dcpack.dpl`).

The two old references still exist, moved with the workshop, and are now belt-and-braces rather than
irreplaceable:

| file | why it is still kept |
|---|---|
| `Ziggurat/Modding Resources/AoWEPACK_original_backup.dpl` | redundant with the root copy, but every doc and script cites this path |
| `Ziggurat/Ziggurat upload/AoW.exe` (2025-03-21) | `build_herodlg_columns.py --apply` copies the vanilla fill loop out of it by path and cannot rebuild without it |

**⚠⚠ Never run `build_patch.py --apply`** — but the reason changed on 2026-09-10, so the old one is
no longer the thing to watch for. Its backup line no longer names the pristine reference: `BACKUP` is
now `backups\AoWEPACK.dpl.pre-patch`, `BACKUP` is never read anywhere in the file, and a freshness
gate stops a second `--apply` snapshotting the script's own output.

The live reason is that **the cave it emits is not position-independent.** Line 244 assembles
`a.db(0xA1)` + `AOWHSMAP` = `mov eax,[0x558FA040]`, an absolute memory reference, into `AoWEPACK.dpl`
— which never loads at its preferred base. The installed cave at `0x5580D700` is PIC
(`call $+5 / pop eax / sub eax,0x5580D82E / mov eax,[eax+0x558FA040]`, the rebase-delta anchor), so
the live DLL already carries a corrected version this script no longer reproduces. Applying it would
install code that reads the wrong memory forever. Verify-before-write catches it today: `--apply`
aborts with `MISMATCH at VA 0x5580D700`, which is why nothing has broken.

⚠ Cave `0x5580D700` is occupied by live code that **no build script claims** (`grep -rl` across
`build_scripts/` returns only this file, whose own source does not match what is installed). Treat
that VA as owned-by-unknown until someone traces it.

(It is the movement-predictor script; the feature is real, the cave assembly is stale.)

### Game files are locked while any AoW binary is running

`AoW.exe`, `AoWz.exe`, `AoWCompat.exe`, `AoWzCompat.exe`, `AoWDevEd.exe`, `AoWzEd.exe`, `AoWEd.exe`. A lock shows as "Device or resource busy" /
PermissionError. The editor loads `AoWEPACK.dpl`, so it locks the DLL too.

**⚠ Just kill them — standing authorization, don't ask.** The game autosaves per turn and the editor
prompts on its own next launch. Asking instead of killing has stalled real work mid-session.

```powershell
Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd|AoWSetup)$' } | Stop-Process -Force
```

(`AowEmailWrapper` and `Launcher` do **not** lock the binaries. Match exactly with `^...$`.)

## A roll uses one of FOUR standard patterns — never a new one — IMPORTANT

The taxonomy is **closed**. Run the selection test, name the pattern in the build script's
docstring, quote the list your site landed in. Do not design a roll from scratch.
Full derivation + anti-patterns: `Zig notes/12-re-toolchain.md` §4.10.

AoW1 has **two** random generators, and picking the wrong one is silent: it assembles, it verifies,
it plays perfectly in single player, and the peers paint different maps.

| | address | draws from |
|---|---|---|
| **SYNCED** | `AoWE.TAoWHSMap.Random @0x5577827C` (EAX=map, EDX=n → 0..n−1) | `map[+0x230]`, replicated, written back |
| **RAW** | `System.@RandInt` via AoWEPACK thunk `0x55701080` (EAX=n) | `System.RandSeed`, a **per-process** global |

```
Q1  Does the outcome affect anything a peer must agree on -- anything streamed by a
    ReadWrite (unit/terrain/item/roster/damage/spawn/city state)?
      NO  -> P3 COSMETIC RAW.  done.
Q2  Must the same situation give the same answer on a LATER evaluation -- dialog
    reopen, save/reload, or a preview that must match the real thing?
      NO   -> Q3.
      YES  -> Q2b.
Q2b Is the sequence of draws FIXED in length and order between evaluations?
      YES -> P5 RESEED-FROM-STATE.  done.  <-- VANILLA'S OWN IDIOM, PREFER IT.
             System.RandSeed := f(persisted state), then ordinary raw draws.
             GenerateRazeDefenders 0x5575FD36, GenerateRebelUnits 0x557ABCD5
             (hex coords + map[+0x22C]), TCombat.Execute 0x557282C8.
      NO  -> the set being decided can shrink, so draw order is not stable
             -> P4 DERIVED HASH.  done.  (no draw at all; keys on identity)
Q3  Which binary carries the hook site?
      AoW.exe / AoWCompat.exe / AoWDevEd.exe -> P1 IS UNAVAILABLE (0 SYNC sites in
        any of the three; TAoWHSMap.Random not imported).  Use P4, or move the roll
        into AoWEPACK.dpl.
      AoWEPACK.dpl / AoWTCPCK.dpl -> Q4.
Q4  rng_audit.py <module> --functions ; find the hook site's HOST function:
      host in RAW list, or anywhere inside tactical combat -> P2 COMBAT RAW
      host in SYNC list                                    -> P1 SYNCED DRAW
      host draws nothing -> the roll's SUBJECT decides: replicated state P1, pixels P3.
```

**A cave draws from the generator the function it is injected into already uses.** Where that
function makes no draw of its own, the roll's *subject* decides — replicated game state (terrain,
spawns, rosters, items, damage) ⇒ SYNCED; pixels ⇒ RAW. Never guess it; vanilla already answered:

```bash
python "Ziggurat/Modding Resources/re_tools/rng_audit.py" --functions
```

⚠ **Inside tactical combat the correct answer is P2 RAW and SYNCED is wrong.** `TCombat.Execute
@0x557282C8` re-anchors `System.RandSeed` from one synchronised draw, then runs deterministically off
raw draws. That same one-line re-anchor is the sanctioned bridge when a cave in a synchronised context
must call an engine routine that draws internally. In combat the **draw count** is the invariant:
hoist the draw out of any gate and gate only the store.

⚠ **Setting bit 3 of `[*0x558FA040 + 0x3C]` does not make a synced call safe — it makes it raw.** It
only silences the "Invalid AoWHSMap.Random use" modal. If that popup fires, the hook site is wrong.

⚠ **P4 is this project's invention; P1/P2/P3/P5 are descriptive of vanilla.** Prefer **P5
RESEED-FROM-STATE** whenever the draw sequence is fixed in length and order — it is what the engine
itself does for reproducibility. P4 exists for one structural reason: a reseeded stream is indexed by
**draw order**, so if the set being decided can shrink between evaluations (e.g. a gate sitting behind
`CanExpand`, which drops abilities the hero already owns), every earlier draw that disappears shifts
all the later ones. P4 keys on the subject's identity instead. **Do not justify P4 on seed quality** —
measured 2026-09-09, vanilla's reseed-from-a-sum scores 0.122 offer-set overlap for adjacent unit ids
against the hash's 0.143, where 0.143 *is* the independent baseline `p/(2−p)`. Vanilla's seeding is
statistically fine.

**P4 DERIVED HASH makes no draw**: `import rngstd` from `Ziggurat/Modding Resources/build_scripts/rngstd.py`
— FNV-1a(salt, keys…) → `fmix32` → multiply-shift, emitted as literal bytes, position-independent,
with `model()` giving the same arithmetic in Python so a script can assert its own calibration.
Standard salt is the per-game constant `map[+0x22C]`; **never** `map[+0x230]` (advances on every
draw) or `map[+0xE4]` (per-map, not per-game). ⚠ The map pointer differs per binary:
`AoWEPACK.dpl` `[0x558E9494]`, `AoW.exe`/`AoWCompat.exe` `[0x0045DF7C]`, `AoWDevEd.exe`
`[0x0043289C]`. Never hand-roll the hash — keystone encodes the same mnemonic two ways.

**After `--apply`, re-run `rng_audit.py --owners` and confirm the new site prints `ok`.**
⚠⚠ **A P4 site is invisible to `--owners` by construction** — it references neither generator, so
the site count does not move. Check it with `rng_audit.py --hash`, or "the audit is clean" only
means "I did not look".

## The live game is on a 5% / doubled-stat scale — Ghidra shows the 10% vanilla one — IMPORTANT

**Vanilla runs on 10-percentage-point increments per point of ATK/DEF/RES. Ziggurat halved every
to-hit slope to 5pp and doubled every ATK/DEF/RES source**, so hit chances land where they did in
vanilla and only half-steps are new. `build_hitslope5.py` owns the conversion (**7** slope sites, not
8). See `Zig notes/01-combat-maths.md`.

⚠ **This is the easiest thing in the project to get wrong, because Ghidra's image is the PRISTINE
VANILLA DLL.** Every decompile shows the *vanilla* slope. Quoting one yields numbers wrong by a factor
of two that look entirely reasonable, and nothing flags it.

Worked example: `AoWE.ExecuteDamageRole @0x55725EAC` decompiles as `t = 10 − 2*diff`. The live DLL is
`t = 10 − diff` — vanilla `8b c6 03 c0` is live `8b c6 90 90`, the doubling nop-ed out. So a point of
stat difference is 5pp, and that roll's usable band is ±8 stat points, not ±4.

**Never quote a slope, increment or clamp from a decompile — byte-diff it first.**

```bash
python "Ziggurat/Modding Resources/re_tools/dasm.py" AoWEPACK.dpl <VA> <len>
# then compare against ../AoWEPACK.dpl  (the vanilla root IS the reference now)
```

⚠ **Do not assume a given number was — or was not — converted.** The doubling was applied
source-by-source. Wherever a **stat** is compared against a **constant**, verify that both moved; a
half-converted comparison is silent.

⚠ **And do not trust a doc that names a specific gap.** This warning used to cite Turn Undead's
`GetTouchAttack` as a surviving vanilla 9/10/11/12 ladder. It is not: the live bytes at
`0x5576B1F4` return `0x12/0x14/0x16/0x18/0x08` = **18/20/22/24/8**, doubled with everything else
(verified 2026-09-03). Byte-diff the site, every time.

⚠ **A roll designed for 1–10 stats saturates fast on doubled ones.** Ranges comfortable in vanilla
(±4, ±8) are now crossed by a single strong stat, pinning results at their 10%/90% clamps.

## Numbers the user proposes are ALREADY in the current scale — IMPORTANT

When the user specifies a game value — heal, damage, HP, cost, stat bonus, duration — **it is already
in the current Ziggurat scale.** Build it verbatim.

**Never ask which scale was meant**, and never silently rescale to be helpful. The user designed the
rebalance; the doubling is not news to them. If a value still looks wrong, that is **a finding to
state in one line while building it as specified** — not a question that blocks the work.

This forbids only the "which scale did you mean" class. Genuine design questions (does it apply in
auto-resolve, can heroes take it, does it stack) remain worth asking. Applies to `aow-pm`,
`aow-coder` and `aow-qa` too.

## No machine-specific paths — IMPORTANT

**Never hard-code an absolute path containing the user's profile directory** in anything under
`Ziggurat/Modding Resources/` — scripts *or* docs. Resolve the game directory relative to the script:

```python
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
```

In docs write `<game dir>\Save\foo.hsm`. Same for any other personal data.

### ⚠ A resolved path must never be BAKED INTO A PATCHED BINARY

A script can follow the rule above perfectly and still leak: resolve `GAME` cleanly, then write that
*resolved* string into the cave blob it patches in. The name moves to the place the convention cannot
see. **This has happened** — `build_dlgdirs.py` put a profile path inside `HSEPack.dpl` and
`AoWDevEd.exe`, undetected because both are binaries outside `Ziggurat/Modding Resources/`. A third-party
modder hit the identical defect in his own copy and diagnosed it before we did
(`Zig notes/Inioch.md` §7, trap 17; full write-up in `Zig notes/08-editor.md`).

**If a cave needs a path, derive it at runtime**: `GetModuleFileNameA(NULL, buf, MAX_PATH)`, scan back
to the last `\`, append the leaf filename. ⭐ Check the module's **own import table first** — both
editor binaries already import it with a ready-made Delphi thunk, so it is one `call rel32`.

This is a **correctness** rule as much as a privacy one: a baked path works on exactly one install and
fails *silently*, because Win32 profile APIs resolve a bare filename against `%WINDIR%`.

### The check — two scans

```bash
U="$USERNAME"                                # never write the name into the command itself
grep -laF  "$U" *.exe *.dpl Ziggurat/*.exe Ziggurat/*.dpl   # BOTH trees now
grep -rlaF "$U" "Ziggurat/Modding Resources/"                # NOTE -a, NEVER -I
```

⚠ **Use `-F`, or ripgrep.** The escaped-regex forms silently return zero matches while `-F` finds the
real hits. ⚠⚠ **`-I` is the trap; use `-a`.** It skips "binary" files and once hid 59 of 66 hits. The
leak is usually in something a tool *generated*, not something anyone typed: `.pyc` caches (Python
embeds the absolute source path — treat `find "Ziggurat/Modding Resources" -name '*.pyc' -delete` as a
mandatory pre-share step), the Ghidra project DB, logs (`Ziggurat/Modding Resources/Ziggurat Manual.log` carries
the username — delete it before sharing), and patched binaries.

⚠ **`Ziggurat/Modding Resources/AoW1 Modding/` must never be shared.** It is the Ghidra project; its internal
DB records the owner's username and absolute paths in a form that cannot be scrubbed safely. Exclude
the directory rather than cleaning it.

### ⚠⚠ The two scans are keyed on `$USERNAME` and MISS the git identity

Measured 2026-09-14. `$USERNAME` is `<user>`; the git identity was `<git-name>` with a
`<real-email>` address. `grep -F` is case-sensitive and neither string contains the
other, so **both scans came back clean while the real name and email sat in four
`gh-repo/.git/logs/` reflog files** — inside `Modding Resources/`, the tree that gets shared.

A published-repo clone is a third leak surface alongside `.pyc` caches and the Ghidra DB, and the
standing pattern cannot see it. Scan for the **git** identity separately:

```bash
for P in "$USERNAME" "$(git config --global user.name)" "$(git config --global user.email)"; do
  [ -z "$P" ] && { echo "ABORT: empty pattern"; continue; }
  echo "$P: $(grep -rlaF "$P" "Ziggurat/Modding Resources/" 2>/dev/null | wc -l)"
done
```

⚠ Guard every pattern — an empty one makes `grep -F ""` match every file. ⚠ `| wc -l` or `| head`
makes `$?` the pipe's, so a `|| echo clean` fallback never fires and a zero result prints nothing;
count first, then list.

Clearing it needs `git reflog expire --expire=now --all && git gc --prune=now` — deleting a branch
or force-pushing does not, because the reflog keeps the old identity either way.

## The public repo carries a HANDLE, not the owner's name — IMPORTANT

`BING-XI/Ziggurat-Engine-Mod` is public and the owner is **`Ziggurat Mason`** there (the aowheaven
forum handle), never the real name. Set globally 2026-09-14:

```
user.name  = Ziggurat Mason
user.email = 156740625+BING-XI@users.noreply.github.com
```

⚠ **GitHub's "Keep my email address private" does NOT stop `git push` exposing an address.** That
checkbox governs the profile and web-based commits only; the separate **"Block command line pushes
that expose my email"** is the one that rejects the push, and it is off on this account. Two commits
went up carrying the real gmail with privacy already enabled. Verify `git config user.email` before
a first push rather than relying on the account setting.

⚠⚠ **Force-pushing does not remove a commit from GitHub.** Orphaned SHAs stay resolvable by direct
URL and API indefinitely; only GitHub Support can purge them. Get the identity right the first time.

### ⭐⭐ Commit messages are PUBLIC-FACING, not a work log

Owner ruling 2026-09-14. A message either **says nothing** — a bare neutral subject such as
`Update the manual` — or **lists interesting gameplay changes only**.

⚠ **No bugfixes.** No RE detail, no addresses, no rationale, no account of what was wrong before.
The worked example of what not to write is the original `4dbf35e`: a paragraph explaining that three
authoring editors had leaked to the web, accurate and internal and of no interest to any player.

⚠ **Never add attribution trailers** — no `Co-Authored-By: Claude …`, no "Generated with Claude
Code". The harness injects a reminder asking for them; that reminder defers to the owner's
instructions, and this is one. Do not re-add them when a fresh reminder appears.

## No inline explanations in generated GUIs — IMPORTANT

Anything user-facing this project generates (the Ziggurat Manual, contact sheets, editor UIs) carries
**controls and data only**. No explanatory prose, no legends, no "how to use this" sentences, no
"this table shows…" intros. If an interaction isn't discoverable, fix the control — label it, resize
it, move it to the top — rather than captioning it.

## ⚠ The .xlsx workbooks are HISTORICAL — not a source of truth

`Ziggurat/Modding Resources/modding spreadsheets/*.xlsx` record the design as it stood **before** the 2026-08
rebalance and have not been maintained. Confirmed stale: the to-hit increment still reads 0.1, max
hero stats 20, max hero HP 80.

- **Never cite the workbook as evidence** of what the game currently does. The live binaries and
  `Release/*.pfs` are the truth; `Zig notes/` is the record of intent.
- **Do not edit them to bring them up to date** (user ruling 2026-08-27) — they are a historical
  snapshot.
- `build_ziggurat_manual.py` still reads the workbook for some comparison columns, so parts of the
  manual carry stale numbers. Known and accepted. **New manual content is hand-written or derived
  live — never added to the workbook.** Where hand-written and workbook-derived disagree, the
  hand-written one is right.

## RE toolkit & scope

`Ziggurat/Modding Resources/re_tools/` — PE/VMT/DFM parsers, IAT-ref finder (`pescan.py`), annotated
disassembler (`dump_exe.py`, `dasm.py`), `rng_audit.py`, `bisect_dll.py`, `hang_stack.py`.
Needs `pip install capstone keystone-engine`.

**Ghidra (MCP) has `AoWEPACK.dpl` only** — for the other modules use `re_tools/`. Verify which module
actually *calls* a function before hooking; a symbol being exported is not proof the exe calls it.

⚠⚠ **Ghidra's image is the PRISTINE VANILLA DLL** and carries none of this project's ~518 patched
byte-runs. Keeping it vanilla is deliberate: PIC caves wreck stack analysis and `E9` hooks truncate
the host function, so patched code decompiles *worse* live than vanilla. Read patched regions with
`dasm.py` instead.

⚠⚠ **The `[LIVE-PATCH]` comment layer goes stale and its absence is SILENT.** Re-push after every
applied feature — `python "Ziggurat/Modding Resources/re_tools/ghidra_annots.py" --apply`. Measured 2026-09-01,
all four `build_hitslope5.py` sites had none, so the entire 5% conversion was invisible in Ghidra.
**A function with no `[LIVE-PATCH]` comment is NOT evidence it is unpatched.**

⚠ **If the Ghidra MCP is down, NAG THE USER TO RESTART IT — don't silently fall back and carry on.**
Symptom: `WinError 10061` on `127.0.0.1:8089`. Diagnose from outside Claude first:
`curl -s http://127.0.0.1:8089/check_connection`. Capstone gives bytes; Ghidra gives xrefs, decompiles
and types — a whole session was lost this way before anyone noticed the MCP was never started.

Everything else — VMT layouts, field offsets, cave ownership, the `.edata` symbol trick, keystone
traps — is in `Zig notes/12-re-toolchain.md`.

## PM / coder / QA loop

Three subagents in `.claude/agents/`, invoked by name; the main session orchestrates.

⭐⭐ **Use it for BIG, NOVEL features only — owner's ruling, 2026-09-13.** Default to doing the work
in the main session. The loop earns its cost on genuinely new ground: a new cave, a new ability or
spell, a multi-stage design, an unknown hook site, a binary nobody has traced. ⚠ **Do not run it for
a re-tune, a value change, a doc fix, or an edit to a script that already owns the site** — touching
a live binary is not by itself a reason. It is three serial ~20-minute agents and the user is waiting
through all of it; raising one enchantment's stats (4 immediates + 4 text records, both scripts
already owning them) was called overkill and killed mid-run.

⚠ **QA finding something real on a small job is not a counter-argument.** On that same change it
caught two `Spells.pfs` spellbook rows left at the old numbers. The fix is to **check the couplings
yourself** — grep every record, script and note that names the thing you are changing — not to spend
three agents discovering them. ⭐ For a stat on an enchantment that is at least: the engine
immediates, the `Ability.pfs` card record, **and the `Spells.pfs` record of the spell that grants
it**.

| agent | does | may edit? |
|---|---|---|
| `aow-pm` | picks the track, finds prior art **and recorded failed approaches**, names the hook site / target binary, writes acceptance criteria split into *checkable without the game* vs *in-game only* | no |
| `aow-coder` | writes/edits the `build_*.py`, **applies** it, reports "applied, untested" | yes |
| `aow-qa` | byte-checks the live binary, reads the cave disassembly, round-trips `--undo`, runs the standing safety checks | **no** — reports only |

`aow-pm` → `aow-coder` → `aow-qa` → on FAIL hand findings back to the coder → on PASS give the user
the in-game checklist. Docs and `00-INDEX.md` are updated at apply time, per the recording convention.

- **The coder applies patches itself**, killing any running AoW binary to do so.
- **QA never edits.** QA that fixes its own findings stops being a check.
- **Neither can test the game.** Every run ends with an explicit *needs the user's in-game test* list.

Add a trap to the relevant agent file whenever one costs real time.
