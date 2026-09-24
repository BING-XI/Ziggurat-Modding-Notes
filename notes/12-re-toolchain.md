# RE toolchain & method

How to find things in the AoW1 binaries and how to patch them without breaking something you can't
see. This file covers: the Ghidra setup and the discipline of reading a **pristine vanilla** image
safely; naming VMT slots and instance fields straight from the DLL's own export table (the full
derived VMT layout and field catalogue live here, in full, as the reference); the two-RNG rule; a
reusable per-hex ring-distance technique; the cave-space allocation convention and the canonical
table of who owns what; the pristine-reference / backup / revert convention; the process-lock and
AoWCompat-lockstep rules; and a small ability-id / effect-bit quick reference salvaged from an
otherwise-superseded investigation log.

It does **not** cover any specific game feature's design, balance numbers, or in-game checklist —
those live in the sibling feature files. Where a technique here was proven on a specific feature
(the per-hex ring gate on Path abilities, the RNG fix on terrain spells), this file names the
feature and its status for context, but the feature's own record is the sibling file.

## Status table

Almost everything in this file is method, not a shipped feature, so most sections carry no ladder
status. The few applied patches this file documents in technical depth:

| feature | status | owning script | binary |
|---|---|---|---|
| RNG lockstep fix (3 terrain caves moved from RAW to SYNCED) | 🔨 APPLIED, UNTESTED (2026-08-31) | `build_rng_lockstep.py` | AoWEPACK.dpl |
| Per-hex ring detection, worked example (Path radius +1, 25% outer-ring proc) | ✅ CONFIRMED WORKING (2026-07-08) — technique only; feature record lives in the movement/Path file | `build_path_outerring.py` | AoWEPACK.dpl |
| Mind Decay draw-count-invariance fix (worked example for RNG discipline inside combat) | 🔨 APPLIED, UNTESTED (2026-09-03) — full record in `11-engine-internals.md` (combat-math file) | `build_minddecay_oos.py` | AoWEPACK.dpl |
| **TE exception detail** — ⚠ **DIAGNOSTIC, revert before shipping**. Makes "Exception occured during `<TE>`" print the module + offset of the real fault. §3a | 🔨 APPLIED, UNTESTED (2026-09-11) | `build_te_exception_detail.py` | Network.dpl |

Ghidra's own annotation layers (patched-site comments, structs, enums) are tooling state, not a
game patch, and don't fit the ladder above — see "The `[LIVE-PATCH]` layer" below for their own
freshness tracking.

⚠ **Before putting a property into any DFM a build script emits, check it is PUBLISHED.** `TReader`
rejects the *entire form* over one unknown property and the form then fails to load; every static
check still passes. `re_tools/rtti_props.py <TClass> [Prop ...]` reads the VCL's own RTTI out of
`vcl30.dpl` and exits 1 on a missing one. It reproduces both failures that cost this project a
round trip each: Delphi 3's `TComboBox` leaves `ItemIndex` public rather than published, and
`TScrollBar.PageSize` did not exist until Delphi 4. The parse and the D3 method-table format sit in
`08-editor.md` §9.3.

⭐ **A DIALOG patch does not have to wait for the user's in-game test — drive it.** `08-editor.md`
§9.5 is the worked example: launch the exe, `re_tools/menucmd.py <mainhwnd> list|exec <id>` to reach
the menu command, `EnumChildWindows` to read every control's real state (⚠ Delphi registers its own
window classes, so the class name is `TComboBox`, not `ComboBox`), `re_tools/grabwin.py` to capture
the window even when occluded, and posted messages to drive it with no cursor movement and no focus
steal (`re_tools/clicker.py`). That pass found two defects a full static check had passed —
a streaming guard that opened itself, and 19 dropdowns silently blank — before the user saw either.
`re_tools/dfm_verify.py <module> <TFormClass>` is the static half: it walks the patched DFM as
`TReader` will and cross-checks it against the field and method tables.

---

## 1. Ghidra: setup, starting it, rollback

**Status: working, verified end-to-end 2026-08-03.** Current stack: **bethington/ghidra-mcp 6.0.0**
(267 tools, HTTP on **127.0.0.1:8089**) on **Ghidra 12.1.2**, replacing LaurieWired/GhidraMCP 1.4
(27 tools, port 8080), which is left installed as a rollback path — do not delete it.

| piece | where | notes |
|---|---|---|
| Ghidra 12.1.2 | `%USERPROFILE%\Downloads\PROGRAMS\ghidra_12.1.2_PUBLIC\` | launcher `ghidraRun.bat`. Needs JDK 21+; runs on the installed Temurin 25. |
| Ghidra 11.3.2 (old) | `%USERPROFILE%\Downloads\PROGRAMS\ghidra_11.3.2_PUBLIC_20250415\` | rollback path, untouched |
| GhidraMCP 6.0.0 extension | `%APPDATA%\ghidra\ghidra_12.1.2_PUBLIC\Extensions\GhidraMCP\` | serves HTTP on 127.0.0.1:8089 |
| Python bridge | `ghidra-mcp-bridge 6.0.0`, installed into **both** Python 3.13 and 3.14 | see the interpreter trap below |
| release downloads | `%USERPROFILE%\Downloads\PROGRAMS\GhidraMCP-6.0.0\` | zip + wheel + INSTALLATION.md, kept for reinstall |
| Claude Desktop config | `%APPDATA%\Claude\claude_desktop_config.json` | `"ghidra": {"command": "<absolute path to python.exe>", "args": ["-m", "bridge_mcp_ghidra"]}` |

The console script `bridge-mcp-ghidra.exe` lands in a directory that is **not on PATH** — always use
the `python -m bridge_mcp_ghidra` form. There is no `--ghidra-server` flag in v6 (1.4 had one); the
bridge defaults to `http://127.0.0.1:8089` and auto-discovers.

### ⚠ Trap: `"command": "python"` launches a DIFFERENT interpreter than your shell

This machine has **two** Pythons: the one a shell resolves bare `python` to (what `re_tools/` uses),
and a separate `Python313` install that **Claude Desktop** resolves bare `python` to, because its
own PATH puts Python313 first. Installing the MCP wheel from a shell puts it in the shell's Python
only, and the MCP server then dies instantly on every start with a useless toast ("Server
disconnected"); the real cause is visible only in `%APPDATA%\Claude\logs\mcp-server-ghidra.log`:

```
...\Python313\python.exe: No module named bridge_mcp_ghidra
```

**Fix, and the standing rule:** install the wheel with *both* interpreters and pin `"command"` to an
**absolute** `python.exe` path in the config, never bare `python`. Diagnose any "Server disconnected"
from that log file first — the bridge will run perfectly by hand while failing under Claude.

⚠ Installing on 3.13 upgraded its `mcp` package 1.26.0 → 1.29.0 as a side effect. If some *other*
Python MCP server misbehaves after touching this, that shared dependency is the first thing to check.

### The project

`Modding Resources\AoW1 Modding\AoW1-vanilla.gpr` — program `AoWEPACK_vanilla.dpl`, image base
`0x55700000`, `x86:LE:32` / `borlanddelphi`, ~800 functions, headless-analysed in 122s.

It is a byte-for-byte import of `AoWEPACK_original_backup.dpl` (the pristine pre-modding DLL), just
renamed so the program name states what it is. Verified through the running server:
`disassemble_function?address=55771068` → `557710f3: SUB EAX,0xa` (vanilla road build cost 10; the
live DLL charges 5 — see the vanilla-image discipline below).

- Ghidra's `get_metadata` reports an `Executable Path` under a scratchpad temp folder — that is just
  where the renamed copy was staged for import. The bytes live in the project; the path is dead
  metadata, **not** evidence of where the vanilla DLL lives.
- `Modding Resources\AoW1 Modding\` also holds older 11.3.2-era projects (`Files`,
  `Projects\Misc Files`, `BloodTypes`, `MovePrediction`, `Transport Disappearance`, ~219 MB total).
  Opening one of those in 12.1.2 upgrades it one-way — copy before opening.
- **⚠ `Modding Resources/AoW1 Modding/` must never be shared** — it is the Ghidra project, and its
  internal DB (`.rep/`, `.lock/`, `.gbf`, `.prp`) records the owner's username and absolute paths in
  a form that cannot be scrubbed without risking the project. Exclude the whole directory when
  sharing this folder; do not try to clean it in place.

### Starting it

1. Run `ghidraRun.bat` from the 12.1.2 folder.
2. **File → Open Project** → `AoW1-vanilla.gpr` (the recent-projects list may still point at an old
   location it was moved from).
3. Open `AoWEPACK_vanilla.dpl` in the CodeBrowser.
4. The GhidraMCP plugin is saved in the tool config and should already be on. If not:
   **File → Configure → Configure All Plugins → Miscellaneous → Configure → GhidraMCPPlugin** (it is
   a standalone plugin, filed under *Miscellaneous*, not under a package).

Verify without touching Claude:

```bash
curl -s http://127.0.0.1:8089/check_connection
```

Expected: `Connected: GhidraMCP plugin running with program 'AoWEPACK_vanilla.dpl'`. Other useful raw
endpoints: `/list_open_programs`, `/get_metadata`, `/list_functions`,
`/disassemble_function?address=<VA>`, `/decompile_function_by_address?address=<VA>`.

### ⚠⚠ If the MCP is down, say so and ask the user to restart it — do not silently fall back

Symptom: any `mcp__ghidra__*` call fails with `Max retries exceeded` / `WinError 10061 target
machine actively refused it` on `127.0.0.1:8089`. **Say so immediately and explicitly**, and ask the
user to restart Ghidra + the MCP bridge — then keep working with `re_tools/` (capstone) in the
meantime and ask again at the next natural pause if it is still down. Diagnose from outside Claude
first: `curl -s http://127.0.0.1:8089/check_connection` tells you whether it's Ghidra or the bridge
that's down.

This is a rule, not a nicety, because degrading silently is expensive in a specific way: capstone
gives you *bytes*; Ghidra gives you *xrefs, decompiles and types*. A whole session was lost on
2026-07-30/31 re-deriving by hand what Ghidra would have answered in one call, because nobody
noticed the MCP had simply never been started.

### Rollback

One file. Restore the backup and restart Claude Desktop:

```bash
cp "$APPDATA/Claude/claude_desktop_config.json.pre-ghidramcp6" "$APPDATA/Claude/claude_desktop_config.json"
```

Then run the 11.3.2 `ghidraRun.bat` instead. Nothing about the 11.3.2 install, its extension, or its
projects was modified by the upgrade.

---

## 2. ⚠⚠ Ghidra's image is the PRISTINE VANILLA DLL — never claim "unpatched" from a decompile

This is the single most expensive mistake this project makes, repeatedly, and the discipline below
exists entirely to stop it happening again.

**The Ghidra project is `AoWEPACK_original_backup.dpl` under a renamed program.** It carries **none**
of this project's roughly 518 patched byte-runs. A decompile that looks unpatched, clean, or
vanilla-shaped is not evidence of anything about the *live* file — it is simply what vanilla looked
like before any of this project's ~150 build scripts ran.

**Keeping the Ghidra image vanilla is deliberate, not an oversight — don't propose importing the live
DLL:**

- Caves in this project are position-independent via the `call $+5; pop; sub` idiom (see
  `aow1-dpl-rebasing`). Ghidra models that `call` as a real subroutine call, so its stack analysis —
  and the decompile — of **every cave** comes out as garbage.
- A 5-byte `E9` hook makes Ghidra end the host function at the tail jump, orphaning the original tail
  as undefined bytes, and the cave's jump back into mid-function adds an edge Ghidra attributes
  poorly.

**Patched functions therefore decompile *worse* in a live import than in the vanilla one.** The
correct split is: **Ghidra (vanilla) for engine logic, xrefs and types; capstone for anything
patched.** Read patched regions with:

```bash
python "Modding Resources/re_tools/dasm.py" AoWEPACK.dpl <VA> <len>
```

and compare against `Modding Resources/AoWEPACK_original_backup.dpl` for the vanilla bytes before
concluding anything about what's live.

**Worked example of getting this wrong (found 2026-09-01):** `AoWE.ExecuteDamageRole @0x55725EAC`
decompiles in Ghidra as `t = 10 - 2*diff` (vanilla). The **live** DLL is `t = 10 - diff` — vanilla
`8b c6 03 c0` (`mov eax,esi; add eax,eax`) is live `8b c6 90 90`, the doubling NOP-ed out by
`build_hitslope5.py`. Quoting the decompiled form gives a slope wrong by a factor of two, and
nothing about reading it flags the error. See "The live game is on a doubled scale" below for the
general form of this trap.

**Corollary:** every data table read out of Ghidra (movement costs, rank stat tables, to-hit slopes)
is a **vanilla** number, not the installed Ziggurat-rebalanced one. Read those from the live file.

### The `[LIVE-PATCH]` comment layer — what makes the vanilla image safe to read

Reading a vanilla decompile and concluding "X is unpatched" produced two confirmed, expensive wrong
verdicts before this layer existed: a `TCity.GenerateRebelUnits` verdict that survived a week, and a
wrong road-build-cost claim that propagated into three files. Every site where the live DLL differs
from the pristine image Ghidra shows now carries a comment, in both the decompiler and the listing:

```
[LIVE-PATCH] live DLL differs here (1B): 0a -> 05 | named in: road_build_cost_by_decoration_patch.py
| VANILLA SHOWN - verify with re_tools/dasm.py AoWEPACK.dpl 557710F3 0x1
```

Nothing here is hand-maintained: `re_tools/ghidra_annots.py` derives the site list from a live-vs-
pristine byte diff and the attribution by grepping `build_scripts/`, so re-running it after any new
feature keeps it correct.

```bash
python "Modding Resources/re_tools/ghidra_annots.py"          # dry run: inventory only
python "Modding Resources/re_tools/ghidra_annots.py" --apply  # write the comments
python "Modding Resources/re_tools/ghidra_annots.py" --undo   # clear only its own comments
python "Modding Resources/re_tools/ghidra_annots.py" --json FILE   # dump the inventory
```

Ghidra must be running with the vanilla program open; the script refuses to write into any other
program. **Save the program in Ghidra afterwards** — the plugin does not auto-save.

As last inventoried (2026-08-03): 443 patched sites had a vanilla counterpart to compare against (a
further 75 cave runs were skipped — no vanilla code sits there to diff against). Of the 443: 183 were
named by a `build_scripts/` script, 31 named only by a doc, and **229 named by neither**. Those 229
are not corruption or lost documentation — they are five years (2020–2025) of the Ziggurat mod's own
hand-edits, made long before this project's build-script-and-doc convention existed. Don't
reverse-engineer their intent; the author is available and one question replaces an hour of analysis.

Two implementation traps worth carrying forward if this tool is ever touched:

- **A diff run starts at the first byte that DIFFERS, which is usually mid-instruction.** A patched
  road cost is `sub eax,0xa` but the differing byte is the immediate a few bytes in. Ghidra only
  renders a comment at a code-unit boundary, so an unsnapped address produces a comment that
  silently never appears — 268 of 443 sites needed snapping (60% would have been invisible without
  it). Fix: decode forward from several lead-ins and take the most common containing instruction,
  since x86 cannot be decoded backwards.
- **Grep proves a file *mentions* an address, not that it *wrote* it.** Hence "named in:", never
  "patched by". A script can cite an address purely as a reference or a boundary check without ever
  writing there.

### ⚠⚠ The layer GOES STALE, and its absence is SILENT — re-push it after every applied feature

Measured 2026-09-01: sites owned by `build_combatlog_dll.py`, `build_invis_penalty.py`,
`build_turnundead_res.py` and `build_touchlog_gate.py` all carried comments, while **all four**
`build_hitslope5.py` sites had **none** — `0x55725D9D` (inside `HitRole` itself), plus `0x55725DCF`,
`0x55725E3B`, `0x55725ED7`. The comment layer predates that feature, so the **entire 5% to-hit
conversion was invisible in Ghidra** — which is exactly how a session came to quote vanilla's 10%
slope as live (the worked example two sections up). **A function with no `[LIVE-PATCH]` comment is
NOT evidence it is unpatched.** Check with `ghidra_annots.py` (dry run) or
`grep -rl "<VA>" build_scripts/` before believing a function is clean.

### ⚠ "No script writes this address" is not the same claim as "no script owns this address"

A second, related trap: a patch can own an address by writing the *byte next to it*, and a grep for
the address itself then comes up empty. Worked example, found while auditing `build_hitslope5.py`'s
seven to-hit slope sites: an earlier investigation doc labelled `0x55725D9F` (`imul eax,eax,5`) "an
undocumented hand edit, no script writes it." Wrong — `build_hitslope5.py` owns that instruction as
part of the same edit, by NOP-ing the two bytes immediately *before* it (`0x55725D9D`, `add eax,eax`
→ `90 90`), which changes the effective slope of the multiply at `0x55725D9F` without touching a
single byte of it. A grep for `55725D9F` in `build_scripts/` finds nothing; a grep for `55725D9D`
finds the owner immediately. **Attribution needs a byte-range read, not a single-address grep** —
the same lesson as the "named in: vs patched by" trap above, from the opposite direction.

---

## 3. Naming things without hand-analysis — the DLL exports its own symbol table

`AoWEPACK.dpl` is a Delphi 3 runtime **package**, and its `.edata` exports **10,036 named symbols**
covering essentially every method. The export directory *is* a complete symbol table, parseable
straight out of the file — **Ghidra is not required to name a VMT slot or a method.** Map slot →
target VA → export name, and Ghidra (when available) just corroborates it via
`get_function_by_address`.

Corollaries worth knowing before walking a VMT by hand:

- **Slots that look nameless in Ghidra are import thunks.** e.g. several of `TAbstractUnit`'s slots
  point at `FF 25 <iat>` jumps into a thunk table; Ghidra defines no function there, so a Ghidra-only
  walk reports them blank. Resolving the IAT names them — they are `Engine.TEObject` methods
  imported from **EngineP.dpl**, a module Ghidra does not have loaded.
- **The class hierarchy leaves this module.** e.g. `TAbstractUnit → TAbilityOwner →
  TCustomAbilityList → Engine.TEObject`, and that last one is imported, so a naive parent-walk stops
  at `TCustomAbilityList`. The ancestor's own virtual methods are still fully named (from the import
  table), even though the ancestor's binary is absent.
- **A VMT's end is detectable exactly**, two independent ways: the first slot that does not point
  into CODE, and — more reliably — the class-name ShortString and the RTTI init-table record sit
  immediately after the last slot, so `[VMT-0x34]` (vmtInitTable) equalling `VMT+<n>` proves the VMT
  is exactly `n` slots long. Reading past the end is not a bad method pointer; it is a jump into a
  string.
- **`vmtSelfPtr` at `[VMT-0x40]` holds the VMT's own address** — a self-checking fingerprint.
  Scanning CODE for "a dword at address A whose value equals A+0x40" enumerates every VMT in the
  module (893 classes found this way) with zero false positives — a better VMT finder than a string
  search, and it needs no class name to start from.

### ⚠ Delphi 3 negative VMT header — `Destroy` is at a NEGATIVE offset, not a positive slot

```
-0x40 vmtSelfPtr    -0x20 vmtClassName   -0x1C vmtInstanceSize   -0x18 vmtParent
-0x14 SafeCallException   -0x10 DefaultHandler   -0x0C NewInstance
-0x08 FreeInstance        -0x04 Destroy
```

**If you are hooking a destructor, it is at `VMT-0x04`.** A VMT-slot hook table that only walks
`+0x00` upward will miss it entirely. Delphi 3 has no AfterConstruction/BeforeDestruction/Dispatch
entries (unlike Delphi 4+), so the header is 0x40 bytes, not stock Delphi 3's 0x4C.

⚠ This binary's layout is empirically **not** the textbook Delphi 3 one either (which puts
ClassName at -12 and the standard virtuals at positive 0..28) — it uses an older Delphi-2-style
layout with the five standard `TObject` virtuals at **negative** `-0x14..-0x04` and user-declared
virtuals starting at `+0x00`. Verified across `TPlayer`, `TItem`, `TAbilityOwner`,
`TCustomAbilityList` and EngineP's `TEObject`. The recipe this project has always used —
`[VMT-0x20]` = class name, `[VMT-0x1C]` = instance size, `[VMT-0x18]` = parent — is correct for this
binary and safe to keep. If the textbook Delphi 3 constants had been used instead, every offset in
this project's docs would be shifted by 0x14. They are not.

⭐ **This holds for `AoW.exe` too, not just AoWEPACK** (verified 2026-09-08 on `TSpellBook`:
class-name ptr `0x0042DD88`, instance size `0x248` at `0x0042DD8C` ⇒ **VMT `0x0042DDA8`**). It
matters the moment you scan live memory for an instance, because an object's first dword is its
VMT: derive the VMT with the textbook `vmtClassName = -44` and you get `0x0042DDC0`, which matches
**nothing** and makes a correct scanner report "no instances found". Cost a wasted round trip.
⚠ A VMT-value scan also hits **static references inside the image** (`vmtSelfPtr`, class-ref
constants) — real instances are heap addresses, so discard any hit below `0x01000000`.

`re_tools/spellbook_geom.py` is the worked example: it attaches to the running game, finds the
`TSpellBook` instance, and prints every slot's live parent / alignment / rect.

⚠ **It is currently broken by the 2026-09-09 rename** (measured 2026-09-10, NOT fixed — it is an
`re_tools` script, outside the twenty-one migrated `build_*.py`). Line 136 is
`pids = pids_by_name("AoW.exe") or pids_by_name("AoWCompat.exe")`, and those are now the **vanilla**
process names, so against a running `AoWz.exe` it prints "AoW.exe is not running" and exits.
**12 other `re_tools` scripts share the defect** — full list, failure modes and the one-line fix in
§Open items. ⚠ Do not trust any live-attach tool until that is done: the process-name scanners can
attach to a running *vanilla* `AoW.exe` and report its geometry as the mod's, with no error.

It exists because
the **DFM lied about the control hierarchy** (flat siblings on disk, re-parented into child
controls at runtime) and two successive fixes were built on that wrong reading — see
`04-spells-modded.md`. For any question of the form "where is this control actually", measure with
this or `live_ui.py`; do not reason from the DFM.

### ⚠ `vmtParent` is DOUBLE-INDIRECT

`[VMT-0x18]` does not point directly at the parent's VMT — it points at a **cell that holds** the
parent classref: `parent = [[VMT-0x18]]`. Reading it singly gives a bogus mid-string address that
decodes as ASCII garbage. This is the same idiom as Delphi's own `TObject.ClassParent`
(`MOV EAX,[EAX+vmtParent]; MOV EAX,[EAX]`). When the parent lives in another package the cell is an
IAT entry, so in the on-disk image it holds a hint/name RVA, not an address — dereference it against
the import table instead of treating it as a VA.

### ⚠ Abstract stubs return 0 — that is the design, not a bug to "fix"

On `TAbstractUnit`, the `GetInherent*` slots and `GetAttack`/`GetDefense`/`GetDamage`/
`GetResistance`/`GetHits`/`GetMoves` are 4-byte `33 C0 C3 90` (`xor eax,eax; ret`) stubs, and
`SetCastingPoints` is a bare `ret`. They exist purely to be overridden by `TUnit`/`THero` — a
decompile that shows one of these returning a constant 0 is showing you the abstract base, not a
patched-out feature.

### ⚠ The combat ability accessors are NOT uniformly nil-safe — `GetAbilityLevel` needs its own gate

On `TCombatObject`/`TCombatUnit`, the ability accessors all reach the strategic unit through
`[combatobj+0x4C]`, but only some of them check it first (verified byte-identical to pristine —
this is vanilla design, not a defect):

```
+0xA8 GetAbilityEnabled:  mov ecx,[eax+0x4C] / test ecx,ecx / je -> return 0    GUARDED
+0xB0 GetAbilityLevel:    mov eax,[eax+0x4C] / mov ecx,[eax] / call [ecx+0x144]  NOT GUARDED
+0xB4 GetAbilityCount:    mov edx,[eax+0x4C] / test edx,edx / je -> return 0    GUARDED
```

**A nil `[combatobj+0x4C]` is therefore normal engine state, not corruption** — the engine only ever
reaches `+0xB0` directly behind a `+0xA8` test. The rule for a new cave: **call `GetAbilityLevel`
(`+0xB0`) only immediately behind a `GetAbilityEnabled` (`+0xA8`) gate on the *same object in the
same function*.** A gate set in an earlier function (a flag stashed during `Generate` and read
during `Execute`) does not count — by the time `Execute` runs, the attacker may have died or
detached. Walls are safe automatically: `TCombatObject.GetAbilityOwner`/`GetAbilityEnabled`/
`GetAbilityLevel` are all `xor eax,eax; ret`.

⚠⚠ **"Walls are safe automatically" applies to those three VIRTUALS ONLY — never to a direct
`[combatobj+0x4C]` read.** `TCombatWall` (VMT `0x55715C40`, instsize `0x50`) is a **sibling** of
`TCombatUnit` (`0x55715A94`, `0x5C`) under `TCombatObject` (`0x557158EC`, `0x4C`), so it has no
strategic-unit field at all and reuses those bytes as packed data: `+0x4C` wall type, `+0x4D` wall
HP. A Ziggurat stone wall reads back as `0x00002802` — **non-zero**, so the nil test above passes
it. A cave that needs the strategic unit must gate on `IsClass(obj, TCombatUnit)` *before* the read,
or go through `+0xB8 GetAbilityOwner`, which is the engine's own type-safe accessor for the same
field. Full write-up and the shared guard cave: `03-abilities-added.md`, Assassin section.

### `System.@IsClass` — entry `0x41303A14`, nil-safe, NOT garbage-safe

Export `System.@IsClass` resolves to VCL30.dpl **RVA 14868 = `0x3A14`** (the `ret` at `0x41303A13`
ends the previous function). AoWEPACK reaches it through the thunk `0x557010C0`
(`jmp [0x558FB6BC]`).

```
41303A14  85 c0      test eax,eax        <- ENTRY: nil test, so IsClass(nil,C) = False
41303A16  74 10      je  0x41303A28
41303A18  8b 00      mov eax,[eax]       ;  @@loop
41303A1A  39 d0      cmp eax,edx
41303A1C  74 08      je  0x41303A26
41303A1E  8b 40 e8   mov eax,[eax-0x18]  ;  vmtParent -- a POINTER TO a classref cell, which is
41303A21  85 c0      test eax,eax        ;  why the loop re-enters at the `mov eax,[eax]`
41303A23  75 f3      jne 0x41303A18
41303A25  c3         ret                 ;  EAX==0, so AL==0
41303A26  b0 01      mov al,1
41303A28  c3         ret
```

- **Nil is handled; garbage is not.** There is no validity test on a non-nil pointer — it goes
  straight to `mov eax,[eax]`. Every AoW1 "IsClass AVed" report is a garbage object pointer.
- ⚠ **`0x41303A18` is the LOOP BODY, not the entry.** It is the back-edge target of the `jne` at
  `0x41303A23`. Two consequences: a fault is reported at `00003A18` whatever the caller did, and
  **hooking this function's entry with a 5-byte `E9` dies with runtime 216** because the back-edge
  lands inside the displaced bytes. Do not hook `@IsClass`; gate at the call site.
- Delphi 2/3 VMT negative offsets used above: selfptr `-0x40`, field table `-0x2C`, class name
  `-0x20`, instance size `-0x1C`, **vmtParent `-0x18`** (a `PPClass`, not a VMT pointer).

Audited 2026-08-28: the only ungated `+0xB0` call in the live DLL is a vanilla dispatch that
`build_turnundead_res.py` reads — safe today (a Turn Undead attacker is never a wall) but it is
exactly the `Generate`/`Execute` shape, so re-timing that ability re-opens the hazard.
`build_arena.py` also calls `[ecx+0xB0]`, but on the army/unit-list class, where the slot means
something else entirely — another instance of "an offset means nothing without its class" below.

### ⚠⚠ An offset means nothing without its class — five aliasing traps found in one session

This is the single biggest source of wrong offset claims in the whole project's history, and it
recurs because two sibling classes (or a base and a mod-grown descendant) can use the *same* byte
offset for two *completely unrelated* fields. The cross-class alias table and the full field
catalogue below are keyed **by class first**, specifically to make this mistake harder to make.
Quick-reference table (full detail with each field's evidence sits in the catalogue):

| offset | means | |
|---|---|---|
| `+0x4C` | `TCombatUnit` strategic-unit ptr / `TCombatWall` packed byte / `TCombatPredictorUnit` signed HP / `TCity` WallType / `TUnitResource` gold / `THero` level cache | caused the "Blt Error" bug — twice |
| `+0x30` | `TStructure`: past the end (instsize 0x30) / `TExplorationSite` defender strength / `TArena` mod flags (installed-only) / `TCity` owner | three siblings, one byte |
| `+0x10` | `TAoWHexagon`: 3 transition-image bytes / `TAoWWaterHexagon`: a pointer | sibling classes, different parents |
| `+0x40` stat block | `TUnit` resource stats at `+0x29..+0x2E` / `THero` resource stats at `+0x24..+0x29` | 5 bytes apart; both reached via `+0x40` |
| `+0x18` on a CA | `TStrikeCA` effect flags / `TCombatSpellCA` spell id / a ranged CA's ability id | |

The worked derivations behind each of these — plus four more classification traps found while
resolving 16 cross-doc conflicts (`TStructure+0x30`'s three siblings, the hexagon `+0x10` alias, the
`TUnit`/`THero` stat-block offset, and the `map+0x120`/`+0x30` C7 water-mask polarity correction) —
are kept with the field catalogue below, since they only make sense next to the fields they're
warning about.

---
## 3a. Locating a swallowed turn-event exception — the TE exception-detail instrument

**Status: 🔨 APPLIED, UNTESTED (2026-09-11). ⚠⚠ DIAGNOSTIC ONLY — `--undo` it before cutting a
release.** Script: `build_scripts/build_te_exception_detail.py`. Ported from Inioch's proven v2
(`Modding Resources/Inioch/share5/patch scripts/`), re-verified address by address against this
install.

### The defect it instruments

`NetworkE.TTokenExecuter.ExecuteTokenEvent @0x55803D24` (Network.dpl) wraps every turn event in

```
  55803D7C  call [ecx+0x4C]                ; TE.Execute -- TArmyCombatMoveTE, TStructureTE, ...
except:
  55803D90  mov edx,0x55803E14             ; ShortString 'Exception occured during ' (len 0x19)
  55803DAB  call TObject.ClassName
  55803DBC  call @PStrCat
  55803DCA  call @LStrFromString
  55803DD2  call Dialogs.ShowMessage       <-- the hook site
  55803DD9  call @DoneExcept
  55803DE1  inc dword ptr [eax+0x20]       ; and the turn event is ABANDONED
```

The exception object is discarded, so **every TE fault in the game is unlocatable by design** — the
player sees a class name, the turn event silently does not happen (armies moved onto a walled enemy
structure are lost), and the follow-on errors ("Combat already created") arrive with no relation to
the cause. `@DoneExcept` sits *after* the hook, which is what makes the instrument possible: the
exception is still live when `ShowMessage` runs.

### What the patch does

Retargets the 5-byte `call ShowMessage` to a cave that shows the stock dialog unchanged, then calls
`SysUtils.ExceptionErrorMessage` on the still-live exception and shows a second dialog.

**`ExceptionErrorMessage`, not `E.Message`** — that is the whole point of the v2 design. `E.Message`
is perfect for an access violation, which carries its own address, and useless for a *raised* Delphi
exception: HSEngine's `EListError 'Index out of bounds'` names no address at all.
`ExceptionErrorMessage` always formats a module + module-relative offset, whatever the class.
VCL30's `SException` is `'Exception %s in module %s at %p.'#10'%s%s'`, and the `%p` argument is
computed at `0x4130F1F7` as `sub ebx,[ebp-0x32C]` = `ExceptAddr − Info.AllocationBase` from the
`VirtualQuery` — i.e. **genuinely module-relative, not a runtime address**, which is why the decode
below needs no live module base.

```
Exception EAccessViolation in module AoWEPACK.dpl at 00025EAC.
Access violation at address 55725EAC in module 'AoWEPACK.dpl'. Read of address 00000000.
```

⭐ **DECODE: static VA = `<offset>` + the preferred base of the module the dialog names.**

| module | preferred base | | module | preferred base |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x55700000` | | `aowInt.dpl` | `0x59800000` |
| `Network.dpl` | `0x55800000` | | `Dcpack.dpl` | `0x55100000` |
| `HSEPack.dpl` | `0x55600000` | | `vcl30.dpl` | `0x41300000` |
| `AoWz.exe` | `0x00400000` | | `AoWTCPCK.dpl` | `0x00400000` |

⚠ **`AoWTCPCK.dpl` prefers `0x00400000`, the same base as the exe** — it is a DLL that always
rebases, and it is not `0x55A00000`. All eight were read from the PE OptionalHeader of the shipped
files; `build_te_exception_detail.py --bases` reprints them live and that printout is the authority.

### Addresses

Target `Ziggurat\Network.dpl`, ImageBase `0x55800000`, **CODE `va=0x1000 raw=0x400 rs=0x5400
vs=0x5210`, so VA = file offset + `0x55800C00`.**

| | |
|---|---|
| hook | `0x55803DD2` (file `0x31D2`), `e8 ed d8 ff ff` → `e8 39 24 00 00` |
| cave | `0x55806210` (file `0x5610`), **150 of `0x1F0` bytes**, verified all-zero before writing |
| .reloc | 858 entries, max file offset `0x581C`, **none inside either range** |

The cave sits past CODE's `VirtualSize` (`0x1000+0x5210 = 0x6210`) but inside `SizeOfRawData`
(`0x1000+0x5400 = 0x6400`), so it is file-backed, mapped and executable, and it ends exactly at
CODE's raw end (`0x5610 + 0x1F0 = 0x5800`). ⭐ Reusable: **the tail between a CODE section's
VirtualSize and its SizeOfRawData is real executable cave space** — this one is the only cave
Network.dpl has.

### The three RTL routines Network.dpl does not import

`ExceptObject`, `ExceptAddr` and `ExceptionErrorMessage` are not in Network.dpl's import table, and
adding an import to a Delphi package is not worth it. They are **fixed deltas from the one neighbour
it does import**, `SysUtils.Exception.Create` at IAT slot `0x55809564` (confirmed by walking the
import descriptors — it is the only VCL30 entry in that region):

| VCL30 export | VA | ord | delta from the anchor |
|---|---|---|---|
| `SysUtils.Exception.Create` | `0x4130F444` | 460 | — (the anchor) |
| `SysUtils.ExceptObject` | `0x4130F13C` | 466 | `−0x308` |
| `SysUtils.ExceptAddr` | `0x4130F15C` | 465 | `−0x2E8` |
| `SysUtils.ExceptionErrorMessage` | `0x4130F188` | 464 | `−0x2BC` |

`--verify-rtl` re-derives all four from this install's `vcl30.dpl` export table and refuses to write
if a delta moved; `--apply` runs it unconditionally. ABI, disassembled rather than assumed:
`ExceptObject`/`ExceptAddr` take no argument and return in EAX (both are
`call @GetExceptionPointer / test / mov eax,[eax+8 or +4] / ret`, and `ExceptObject` returns **nil**
when no exception is live — the cave tests for that and degrades to the stock dialog alone).
`ExceptionErrorMessage(EAX=ExceptObject, EDX=ExceptAddr, ECX=Buffer, Size pushed)` returns the length
in EAX and is **`ret 4` at `0x4130F308` — callee cleans**, so the cave must not adjust esp after it.

### The cave

```
55806210  push ebp / mov ebp,esp / add esp,-0x140 / push ebx / push esi
5580621B  mov esi,eax                    ; the finished AnsiString
5580621F  mov [ebp-4],0                  ; local AnsiString := nil
55806222  call $+5 / pop ebx / sub ebx,0x55806227      <-- PIC anchor: ebx = rebase delta
5580622E  mov eax,esi / call 0x558016C4                ; 1) the stock dialog, unchanged
55806235  mov eax,[ebx+0x55809564] / sub eax,0x308 / call eax    ; E := ExceptObject
55806242  test eax,eax / je done / push eax
55806247  mov eax,[ebx+0x55809564] / sub eax,0x2E8 / call eax    ; addr := ExceptAddr
55806256  mov esi,[ebx+0x55809564] / sub esi,0x2BC / pop eax
55806263  lea ecx,[ebp-0x110] / push 0xFA / call esi   ; ExceptionErrorMessage, ret 4
55806270  cmp eax,0xFA / jbe / mov eax,0xFA            ; clamp to a ShortString
5580627C  mov [ebp-0x111],al                           ; length byte, immediately before the chars
55806282  lea edx,[ebp-0x111] / lea eax,[ebp-4] / call 0x558010B8   ; @LStrFromString
55806290  mov eax,[ebp-4] / call 0x558016C4            ; 2) the detail dialog
55806298  lea eax,[ebp-4] / call 0x558010A8            ; @LStrClr -- no leak
558062A0  done: pop esi / pop ebx / mov esp,ebp / pop ebp / ret
```

**PIC.** Network.dpl rebases (its preferred base overlaps AoWEPACK), so the cave carries no absolute
memory reference: the `call $+5 / pop ebx / sub ebx,<static VA of the pop>` anchor turns every IAT
read into `[ebx + <static VA>]`, and everything else is `E8 rel32` inside the module or
`[ebp]`-relative. The script's `check_pic()` walks the assembled bytes with capstone and rejects any
mem operand with no base and no index register.

**Frame.** `0x140` of locals: `[ebp-0x111]` length byte, `[ebp-0x110..ebp-0x16]` 250 chars,
`[ebp-4]` the AnsiString. The deepest push reaches `ebp-0x150`, below the buffer, so the pushes and
the buffer never overlap. 250 keeps the result inside a ShortString.

**Hand-assembled, not keystone** — deliberate, and the one place the standing `push imm8` trap would
bite is exactly `push 250`. It is emitted as `68 FA 00 00 00` and `check_imm32_push()` asserts
capstone reads a 5-byte push of `0xFA`, not `6A FA` = −6. Read `--dis`; do not trust the table above.

**RNG:** the cave makes no draw and inherits none — `ShowMessage`, `ExceptionErrorMessage`,
`@LStrFromString`, `@LStrClr` are in neither the SYNC nor the RAW list. Nothing to pick.

### Revert, backup, verification done

`--undo` is **surgical**: restores the 5 bytes at `0x55803DD2` and zeroes the `0x1F0` cave,
verify-before-write, touching no backup. Round-trip measured — applied `5ae623280f0c…`, `--undo`
returns the file byte-identical to the vanilla root copy (`02af854a0ed3…`), `--apply` reproduces
`5ae623280f0c…` exactly. Snapshot `Ziggurat\backups\Network.dpl.pre-texcdetail`, minted on `--apply`
only and only after proving the live file matches the **vanilla root `<root>\Network.dpl`** at both
ranges; confirmed byte-identical to that reference. Applied diff vs vanilla: 135 differing bytes in 9
runs, every one inside the hook or cave window. `Ziggurat\AoWz.exe` launches and reaches its main
window with the patch in (`Network.dpl` is a static import of the exe, so the load is proved).

**In-game checklist (needs the user):**
1. Reproduce the bug — move an army onto a walled enemy structure.
2. Dismiss the stock "Exception occured during TArmyCombatMoveTE" dialog; a **second** dialog follows.
3. Write down the class, the module and the offset, and decode with the table above.
4. `--undo` when the hunt is over.

---
## 4. The two RNGs — a cave draws from the generator its host function already uses

**Status: confirmed from the binaries (2026-08-31, re-measured 2026-09-03).** Every claim below is
derived from `AoWEPACK_original_backup.dpl` (pristine) and the live modules, not from reasoning
about what a lockstep engine "should" do. Audit tool: `re_tools/rng_audit.py`.

AoW1 has **two random generators** and they are not interchangeable. Picking the wrong one is
silent — it assembles, it verifies, it plays perfectly in single player, and it diverges the map on
the first cast of a networked game.

⭐ **Start at §4.10** if you are adding a roll. It is the closed five-pattern taxonomy and its
selection test; §4.1–4.9 below are the derivation it stands on.

### 4.1 SYNCED — `AoWE.TAoWHSMap.Random @0x5577827C`

```
EAX = map instance, EDX = n   ->   EAX in 0..n-1
```

It **is** `System.@RandInt` with the replicated seed swapped in and out (vanilla body):

```asm
5577827C  push ebx / push esi / mov esi,edx / mov ebx,eax
55778282  mov  eax,[0x558FA040]           ; AoWE.AoWHSMap (the flag map)
55778287  test byte ptr [eax+0x3c], 8
5577828B  jne  0x557782CB                 ; flag set -> plain RandInt, NO bookkeeping
5577828D  call 0x55775608                 ; TAoWHSMap.GetSynchronised
55778294  test al,al
55778296  je   0x557782BC                 ; not synchronised -> ShowMessage + return 0
55778298  mov  eax,[0x558FB720]           ; &System.RandSeed
5577829D  mov  edx,[ebx+0x230]            ; the REPLICATED seed
557782A3  mov  [eax],edx                  ;   -> RandSeed
557782A5  mov  eax,esi
557782A7  call 0x55701080                 ; System.@RandInt
557782AC  mov  edx,[0x558FB720]
557782B2  mov  edx,[edx]
557782B4  mov  [ebx+0x230],edx            ; advanced seed written BACK
```

- `map[+0x230]` is replicated state, so every peer walks the same sequence.
- It is also **the value the out-of-sync comparator reads** —
  `TPlayerControl.GetSyncValue @0x55754CE8` returns `[AoWHSMap+0x230]`.
- Outside a synchronised context it pops the modal **"Invalid AoWHSMap.Random use"** and returns 0.

Canonical call site (copied verbatim from vanilla `TIceStorm.ChangeStormTerrain @0x557CCF12`):

```asm
mov  eax, [0x558E9494]     ; ptr -> AoWE.AoWHSMap
mov  eax, [eax]            ; the map
mov  edx, N
call 0x5577827C
```

Registers: pushes/pops EBX and ESI (so those survive), returns in EAX, **clobbers EAX, EDX, ECX and
flags**. ECX is the one that catches people out — in a terrain hook ECX is usually the pointer to
the terrain byte. Push it.

### 4.2 RAW — `System.@RandInt`, AoWEPACK thunk `0x55701080`

`jmp [0x558FB6DC]` → `VCL30.dpl!System.@RandInt`, body at `0x41303384`. `EAX = n` → `0..n-1`. Draws
from `System.RandSeed`, a **per-process global**. Two machines running the same code get different
numbers, and nothing detects it.

`System.@RandInt` is a multiply-shift, not a `%` — `RandInt(4)` is literally the top two seed bits,
so `RandInt(4) < 3` is exactly 75.000%. Do not "fix the bias".

### 4.3 The rule

> **A cave draws from the generator the function it is injected into already uses.**
> Where that function makes no draw of its own, the generator is decided by what the roll decides —
> replicated game state ⇒ SYNCED; pixels ⇒ RAW.

Check it with one command before writing the cave:

```bash
python "Modding Resources/re_tools/rng_audit.py" AoWEPACK.dpl --functions
```

That prints, for the pristine DLL, every function that draws and which generator it uses. If the
hook target is in the SYNC list, the cave uses `0x5577827C`. If it is in the RAW list, the cave uses
`0x55701080` and inherits whatever property vanilla already had there.

Vanilla is not sloppy about this split — it draws **111 synced** and **110 raw** times, principled
throughout:

| vanilla uses SYNCED in | vanilla uses RAW in |
|---|---|
| `*.ExecuteTE`, `*.Execute`, `*.Process`, `NewTurn`, `NewDay` | `*.Show`, `*.ShowAnimation`, `*.NewFrame`, `UpdateTransition` |
| `TAoWHSMap.ChangeTerrain` / `ChangeTerrainEx` / `PlaceTerrain` | `TCity.Show`, `TStructure.ShowRazeAnimation`, `TWorldFXHS.NewFrame` |
| `TRaiseTerrainTE.RaiseTerrain`, `TIceStorm.ChangeStormTerrain` | `TFireStorm.UpdateStorm` (frame counter, not state) |
| `TCity.CheckRebellion`, `GenerateDefenders` (PrdPlace), `TItemHS.GenerateItems` | `ExecuteDamageRole`, `HitRole` — **combat rolls** |
| `TCombat.Execute` (the per-combat re-anchor, below) | `TSetupControl.hPickMap`, `TEmailGameControl.*`, `FillWithRandomUnits` — pre-game / map generation |
| every AI `Process` / `ExecuteAI` | `TAoWWaterHexagon.Create/ShowDynamic` — tile art phase |

### 4.4 ⭐⚠ Inside tactical combat, RAW is the correct answer and SYNCED is wrong

`TCombat.Execute @0x557282C8` is nothing but one line:

```asm
557282C8  mov  edx, 0xFFFFFF
557282CD  mov  eax, [0x558FA040]
557282D2  call 0x5577827C            ; TAoWHSMap.Random(map, $FFFFFF)
557282D7  mov  edx, [0x558FB720]
557282DD  mov  [edx], eax            ; System.RandSeed := that
```

A battle re-anchors `System.RandSeed` from **one** synchronised draw and then runs the whole fight
off raw draws, deterministically, on every peer. Calling the synced generator mid-combat is wrong
twice over: `GetSynchronised` is false there (modal popup, returns 0), and it would advance
`[map+0x230]` — the very value the desync comparator watches.

That single-draw re-anchor is also the sanctioned **bridge** when a cave must use raw draws in a
synchronised context because it calls an engine routine that draws internally:
`System.RandSeed := TAoWHSMap.Random(map, $FFFFFF)` **first**, then call the routine. `build_arena.py`
does exactly this before `GenerateItem`, and vanilla `TItemExplorationSite.Generate` does the same.

### 4.5 ⭐⚠ The second rule: inside combat, the DRAW COUNT is the invariant

Because of that re-anchor, "RAW = every machine gets a different number" is **false inside a
battle**. Both peers start the fight from the same seed, so the raw stream is replicated — **but
only while both consume the same NUMBER of `@RandInt` draws.**

> **A conditional raw draw in combat is a silent desync.** It assembles, it verifies, it plays
> perfectly in single player, and it is invisible to the out-of-sync comparator (which watches
> `[map+0x230]`, untouched by raw draws). The symptom surfaces later and elsewhere: one peer's
> to-hit rolls shift by one draw, units die differently, and the OOS dialog finally fires on some
> unrelated synced draw.

So picking the right *generator* is necessary but not sufficient — a cave in a combat context must
also draw the **same number of times on every path**. Where a roll is gated, hoist the draw out of
the gate and gate only the *store*: discarding an unwanted result costs one draw uniformly on every
machine and preserves determinism exactly.

⚠ **Hoisting is only safe if the draw's INPUTS are safe to evaluate on the rejected path too** — this
looks like a pure refactor and is not. Worked example: `TMindDecay.CreateCA`
(`build_minddecay_oos.py` — 🔨 APPLIED, UNTESTED (2026-09-03), full write-up in
`11-engine-internals.md`) has its `HitRole` call sitting behind five gates, four of which dereference
the target's strategic unit via `[combatunit+0x4C]`. The obvious move is to hoist the whole
expression `[spell+0x34] − target.GetResistance()`. **That AVs.** `GetResistance` is VMT `+0x74`, a
`TCombatObject` base slot (`xor eax,eax; ret`, harmless) — but `TCombatUnit` **overrides** it with
`mov eax,[eax+0x4C]` → `call [edx+0xCC]`, i.e. the very dereference the gates were protecting.
Hoist the **call** only, and substitute a constant for the input on the rejected path — draw-count
invariance depends on the number of `HitRole` calls, not on what they're passed.

⚠ Verify the callee actually draws unconditionally before relying on it. `HitRole @0x55725D98` makes
exactly **one** `@RandInt` call, with only forward clamp branches around it — check this by
disassembly rather than assumption, and have the build script assert it at write time.

**Vanilla is not clean here** — `TMindDecay`'s gate chain is byte-identical to
`AoWEPACK_original_backup.dpl`, so this defect is stock AoW1, not something the mod introduced.
Assume other conditional combat draws exist; `HitRole`'s other callers are the place to look:
`TStrikeCA.Generate` (×2), `TTouchAbility.CombatTouchRole` (×2), `TTurnUndeadAbility.CreateTurnUndeadCA`,
`ExecuteLifeMasteryFearRole`, `ExecuteDeathMasteryCurseRole`, `ExecuteResistanceRole`,
`TBurningAbility.NewCombatTurn`, `TMindDecay`/`TSlow`/`TEntangle.CreateCA`,
`TFastCombatTerrorCA`/`TTacticalCombatTerrorCA.Generate`.

⚠ `rng_audit.py` **cannot see this class of bug.** It matches references to the RNG *entry points*; a
cave that reaches the generator through a caller like `HitRole` adds no new site and the audit's
count does not move. The audit proves you picked the right generator, not that your draw count is
symmetric — that has to be reasoned by hand from the gate structure.

### 4.6 The trap that makes a "synced" call silently raw

`TAoWHSMap.Random` skips **all** its seed bookkeeping when **bit 3 of `[*0x558FA040 + 0x3C]`** is
set (the branch to `0x557782CB` in the listing above). Setting that flag is the known way to
suppress the "Invalid AoWHSMap.Random use" popup when engine code you're calling draws internally
from a non-synchronised context — but understand what it buys: **it converts the draw to a raw one,
with no warning.** It silences the diagnostic; it does not make the call safe.
`build_raiseterrain_lavadirt.py`'s `cave_dirtdelay` uses it deliberately, because the call it wraps
runs from `NewFrameRaiseTerrainAnimation`, a per-frame render callback where `GetSynchronised` is
genuinely false and the unsuppressed call would pop the modal every frame. Consequence, accepted:
peers may pick different *tile art variants* for a converted hex (a raw draw inside `ChangeTerrainEx`'s
variant selection); it never touches `[map+0x230]`, so it cannot trip the desync alarm — believed
cosmetic, unverified. ⚠ Note the two contexts differ even within this one feature: the TE body
(`TRaiseTerrainTE.RaiseTerrain`) **is** synchronised (that's where the 50% lava roll lives, using
SYNC correctly) while the frame-9 callback is not — don't generalise one to the other.

### 4.7 The audit tool

```bash
python "Modding Resources/re_tools/rng_audit.py"                 # every module vs its pristine ref
python "Modding Resources/re_tools/rng_audit.py" --owners        # attribute each site to a build script
python "Modding Resources/re_tools/rng_audit.py" --functions     # which functions draw, from which generator
python "Modding Resources/re_tools/rng_audit.py" AoWEPACK.dpl --all-sites
```

It finds `call`/`jmp` rel32, `call`/`jmp [iat]`, **and bare address constants** in every EXECUTE
section — the last two matter because a cave can reach the RNG with no call target the scan could
otherwise match: the cross-module rebase-delta idiom (`add esi, 0x55701080 ; call esi`) leaves only
a constant (`build_party_random.py` uses it in `AoWDevEd.exe`), and a cave living in a custom PE
section (a `.pty`, `.sc`, `.clog` section) has no `CODE`/`.text` name a naive whitelist would catch —
the tool walks section **characteristics** instead. `--owners` maps a site to the nearest preceding
VA literal in `build_scripts/`, because an exact grep for the call's own VA usually finds nothing —
scripts only ever name the cave's *base* address. Exe-range literals (`0x00400000`–`0x006FFFFF`) are
shared by every module based at `0x400000` — the exe pair, `AoWDevEd.exe`, `AoWTCPCK.dpl` — so below
`0x55000000` a script is a candidate only if its code names the module (filename or `zigexe`
constant). `--hash` also requires the script to import `rngstd`: `build_herodlg_columns.py` lists
`0x628010` in its `.hcol` squatter comment and would otherwise win `0x006280A9` from its real owner.

Targets are the live modules in `Ziggurat/`, exe names from `zigexe`. **References are the stock
copies at the game root**, located by the GOG manifest (`goggame-*.hashdb` lives only there) and
md5-checked against it on every run: `AoWEPACK.dpl`, `AoW.exe` for `AoWz.exe`, `AoWCompat.exe` for
`AoWzCompat.exe`, `AoWTCPCK.dpl`, `aowInt.dpl`, `HSEPack.dpl`. `AoWDevEd.exe` has none — the root
copy is modded and the hashdb has no entry — so its sites print unseparated. A missing target, a
missing reference or a reference that fails the hashdb check exits **2** before anything is printed.

⚠ **From the 2026-09-09 move until 2026-09-23 no default run audited the mod exes.** The module
table still named `AoW.exe`/`AoWCompat.exe`, which do not exist in `Ziggurat/`; the tool printed
`(missing)`, counted zero sites and exited 0, and the reference it listed, `Ziggurat upload/AoW.exe`,
had gone too. Explicit `rng_audit.py AoWz.exe …` runs did scan the exe, but with no reference, so
they could not separate a modded site from a stock one. Re-measured 2026-09-23: the gap hid no
modded draw (§4.8).

### 4.8 Audit of every modded RNG site (2026-08-31, re-measured 2026-09-03 and 2026-09-23)

24 modded sites in `AoWEPACK.dpl`, plus 3 in `AoWDevEd.exe` (no reference; attributed by
inspection). Re-measured 2026-09-23 with every other module diffed against its root copy: none in
`AoWz.exe`/`AoWzCompat.exe` (1 stock RAW site each), `AoWTCPCK.dpl` (273 stock), `HSEPack.dpl`
(9 stock) or `aowInt.dpl` (no entry point). The P4 site `0x006280A9` in both exes
(`build_heroskill_race.py`) makes no draw and shows only under `--hash`. Changes since the
2026-08-31 audit:

| feature (script) | new sites | note |
|---|---|---|
| `build_raiseterrain_ug_earth.py` | **+1** — `0x5583E095`, prints `ok` | `Random(0xB)` for the marker duration inside `TRaiseTerrainTE.RaiseTerrain`, which vanilla itself draws SYNC in twice. Reuses the shared `0x55827000` stub, so `0x55827011` now lists a fourth owner. |
| `build_ai_sitesearch.py` | none | neither cave draws; the search's own rolls stay inside `ExecuteSearch` on the existing synced stream |
| `build_ai_itemloot.py` | none | no cave draws; the script's own `selfcheck()` asserts it for call/jmp rel32 **and** bare address constants |
| `build_minddecay_oos.py` | **none, by construction** | reaches the RNG through `HitRole`, a caller — invisible to this audit, see §4.5 |

**Wrong generator — fixed by `build_scripts/build_rng_lockstep.py`, 🔨 APPLIED 2026-08-31, NOT YET
TESTED IN GAME.** A 24-byte `rng_sync` stub at `0x55827000`, three `call` rel32s retargeted,
`--undo` round-tripped. The three owning caves are otherwise untouched — no cave grew, no branch
target moved.

| site | cave | injected into | vanilla draws | was | now |
|---|---|---|---|---|---|
| `0x5580DB72` | `0x5580DB60` `cave_lavadirt` (`build_raiseterrain_lavadirt.py`) | `Mountain.TRaiseTerrainTE.RaiseTerrain` | SYNC ×2 (`0x557A3397`, `0x557A346E`) | RAW | SYNC |
| `0x5580DB46` | `0x5580DB40` `cave_iceroll` (`build_icestorm_lava.py`) | `Storms.TIceStorm.ChangeStormTerrain` | SYNC (`0x557CCF1E`) | RAW | SYNC |
| `0x5580BEA8` | `0x5580BE74` Fire Storm terrain helper — orphaned, no build script | `Storms.TFireStorm.ChangeStormTerrain` | none, but its sibling `TIceStorm.ChangeStormTerrain` uses SYNC through the same VMT slot | RAW | SYNC |

All three write **replicated terrain state** off what had been a per-process seed, so peers would
have painted different maps from the first cast. **Needs the user's in-game test:** cast Raise
Terrain on lava, Ice Storm, and Fire Storm and confirm each still behaves as before — the exact
numbers that come out will differ, but the proportions and the visuals should be unchanged, and no
"Invalid AoWHSMap.Random use" modal should appear.

Correct as they stand — do **not** "fix" these:

| site | owner | why it is right |
|---|---|---|
| `0x5582310E` | `build_shield.py` — auto-resolve arc, `RandInt(4)<3` | inside combat; rides the seed `TCombat.Execute` re-anchored. A synced draw here would trip the guard *and* perturb the sync value. |
| `0x558114E0` | `build_combatlog_dll.py` transparent logging cave | **replays** vanilla's own `ExecuteDamageRole` draw; adds no draw of its own |
| `0x5580C50E`, `0x5580C52B` | orphan cave `0x5580C500` replacing `SummonSpells.TSummonSpell.SetupSummonSpellTE` | vanilla draws **raw** at the identical spot; the added multi-spawn roll inherits exactly vanilla's property — the TE is populated before submission, so it runs once on the initiating peer only |
| `0x55814200`, `0x55814495` | `build_arena.py` | the sanctioned bridge — synced re-anchor before `GenerateItem` |
| 13 sites | arena, crusade spawns, path-of-sand/outer-ring, tier research, site-defender vary, magebane, mastery cost, storm effect roll | already SYNC |
| 3 sites in `AoWDevEd.exe` | `build_party_random.py` (`System.Randomize` + raw `RandInt`) | map **editor** only — no peers, nothing replicated |

### 4.9 Checklist for a new cave that rolls

1. `rng_audit.py --functions` → is the hook target in the pristine SYNC list or the RAW list?
2. Match it. If the function makes no draw of its own, ask what the roll decides: replicated state
   ⇒ SYNC.
3. SYNC preamble is the 3-instruction one in §4.1. In a cave, the `[0x558E9494]` map-pointer load
   needs the call/pop-delta anchor (`aow1-dpl-rebasing`) — it is an absolute data ref and the DPL
   rebases.
4. Save ECX across the call if you're holding a pointer in it.
5. Never mint a raw draw just to dodge the "Invalid AoWHSMap.Random use" popup. The popup means the
   context is not synchronised — either the hook site is wrong, or the roll belongs further up in
   the TE body.
6. Re-run `rng_audit.py --owners` after `--apply` and confirm your site prints `ok`.

### 4.10 ⭐ The five patterns — the closed taxonomy and its selection test

**Convention, adopted 2026-09-09; corrected the same day.** §4.1–4.9 derive *which generator*. This
section closes the set: **five** patterns, no sixth. Run the test, name the pattern in the build
script's docstring, move on.

Four of the five are **descriptive of vanilla**. The fifth, **P4 DERIVED HASH**, is **an invention
of this project** — say so when you use it, and use it only for the reason below.

⚠ **The first draft of this section got the engine wrong and it is worth knowing how.** It presented
P4 as the way to get "the same answer every time", and mentioned vanilla's actual mechanism only as
a footnote inside P2. Vanilla in fact has a first-class pattern for exactly that job —
**P5 RESEED-FROM-STATE** — and uses it in at least three places:

```
5575FD31  mov  eax, [AoWHSMap]           ; AoWE.GenerateRazeDefenders
5575FD36  add  esi, [eax + 0x22c]        ; hex coords + the per-game salt
5575FD48  mov  eax, [System.RandSeed]
5575FD4D  mov  [eax], esi                ; RandSeed := f(place, game)
5575FD55  call GetRndCollection          ; ...then ordinary RAW draws
```

`City.GenerateRebelUnits @0x557ABCD5` is the identical shape (city coords + salt + size), and
`TCombat.Execute @0x557282C8` is the same idea with a *synced* draw as the anchor instead of map
state. That is how the engine makes raze defenders and rebel garrisons reproducible per place per
game without ever taking a synchronised draw.

**So P5, not P4, is the idiomatic answer to "must be reproducible".** Reach for P4 only when P5's
one structural limitation bites.

#### When P4 is justified over P5 — and it is a structural reason, not a statistical one

A reseeded stream is indexed by **draw order**. That is fine when the sequence of draws is fixed in
length and order, which is why it works for raze/rebel/combat. It fails when the *set of things being
decided* can shrink between evaluations: every earlier draw that disappears shifts all the later
ones, so a given subject's verdict changes for reasons that have nothing to do with it.

`build_heroskill_race.py` is the worked example — its gate sits after `CanExpand`, which rejects
abilities the hero already owns, so the candidate list shrinks as the hero levels. Under P5 an
ability's verdict would move every time the hero bought an unrelated skill. **P4 keys on the
subject's identity rather than its position, so it is order-independent.**

⚠ **Do not justify P4 on seed quality — that argument was tested and is false.** Measured over 3000
trials on two heroes whose unit ids differ by 1, offer-set Jaccard overlap was **0.122 for vanilla's
reseed-from-a-sum** against **0.143 for the `rngstd` hash**, where 0.143 is exactly the independent
baseline `p/(2−p)` at p=0.25. Vanilla's sum-of-small-integers seeding is statistically adequate;
adjacent seeds do not produce correlated streams through Delphi's LCG. Order-independence is the
whole case for P4.

#### The selection test — run top to bottom, stop at the first answer

```
Q1  Does the outcome affect anything a peer must agree on -- anything streamed by a
    ReadWrite (unit/terrain/item/roster/damage/spawn/city state)?
      NO  -> P3 COSMETIC RAW.  done.
Q2  Must the same situation give the same answer on a LATER evaluation -- dialog
    reopen, save/reload, or a preview that must match the real thing?
      NO   -> Q3.
      YES  -> Q2b.
Q2b Is the sequence of draws FIXED in length and order between evaluations?
      YES -> P5 RESEED-FROM-STATE.  done.  (vanilla's own idiom -- prefer it)
      NO  -> the set being decided can shrink, so draw order is not stable
             -> P4 DERIVED HASH.  done.  (no draw at all; keys on identity)
Q3  Which binary carries the hook site?
      AoWz.exe / AoWzCompat.exe / AoWDevEd.exe -> P1 IS UNAVAILABLE (0 SYNC sites in
        any of the three; TAoWHSMap.Random not imported).  Use P4, or move the roll
        into AoWEPACK.dpl.
      AoWEPACK.dpl / AoWTCPCK.dpl -> Q4.
Q4  rng_audit.py <module> --functions ; find the hook site's HOST function:
      host in RAW list, or anywhere inside tactical combat -> P2 COMBAT RAW
      host in SYNC list                                    -> P1 SYNCED DRAW
      host draws nothing -> the roll's SUBJECT decides: replicated state P1, pixels P3.
```

| pattern | mechanism |
|---|---|
| **P1 SYNCED DRAW** | `AoWE.TAoWHSMap.Random @0x5577827C`, EAX=map EDX=n → 0..n−1. Clobbers EAX/EDX/**ECX**/flags; preserves EBX/ESI. In a DPL cave the `[0x558E9494]` map load needs the `call $+5; pop; sub` anchor. Full ABI: §4.1. |
| **P2 COMBAT RAW** | `System.@RandInt` via AoWEPACK thunk `0x55701080` (EAX=n). `TCombat.Execute @0x557282C8` re-anchors `System.RandSeed` from one synced draw, then the fight is deterministic. **Draw count is the invariant** — hoist the draw out of any gate, gate only the store (§4.5). |
| **P3 COSMETIC RAW** | same thunk, no ceremony. |
| **P5 RESEED-FROM-STATE** | **vanilla's own reproducibility idiom — prefer it over P4.** `System.RandSeed := f(persisted state)` then ordinary raw draws. Worked sites: `GenerateRazeDefenders @0x5575FD36`, `GenerateRebelUnits @0x557ABCD5` (both hex coords + `map[+0x22C]`), `TCombat.Execute @0x557282C8` (synced draw as the anchor). ⚠ It clobbers the process-global seed — acceptable for a one-shot event, think twice on a UI repaint path. ⚠ Only valid where the draw sequence is fixed in length and order. |
| **P4 DERIVED HASH** | **this project's invention, not engine practice.** No draw. `build_scripts/rngstd.py` — FNV-1a(salt, keys…) → `fmix32` → multiply-shift. Salt `map[+0x22C]`. Use **only** when P5's order-dependence bites, i.e. the set being decided can shrink between evaluations. Invisible to `--owners`; `rng_audit.py --hash` is what finds it. |

> **Rule: name the pattern, and quote the list your site landed in, in the build script's
> docstring.** One line — `"P2 COMBAT RAW: host TStrikeCA.Generate is in the RAW list"`. That line
> is the whole justification, and it is what makes the choice auditable a year later without
> re-deriving it.

Q3's answer is measured, not assumed: `rng_audit.py AoWz.exe --functions` /
`AoWzCompat.exe` / `AoWDevEd.exe` all print `SYNC: 0`, and none of the three imports
`TAoWHSMap.Random` (verified 2026-09-09). An exe cave *could* reach it through the rebase-delta
idiom (`build_party_random.py` does that for `@RandInt`) — but there is no vanilla SYNC site in
any of the three to inherit a synchronised context from, so the guard at `GetSynchronised @0x55775608`
is the thing you would be fighting. Use P4.

#### The salt — `map[+0x22C]`, and the evidence for it

Established from the pristine DLL, then byte-checked live: **both writers and the serialiser are
byte-identical to `AoWEPACK_original_backup.dpl`**, i.e. unpatched (re-verified 2026-09-09).

```
writers, exactly two:
  0x557E0FDA  AoWSetup.TSetupControl.SetupMap+0x476   map[+0x22C] := setupSettings[+0x2C]
              inside the `if (settings[+0x20]==0)` new-game block; distributed to peers
              via ListPCCInfo / NetworkE.TPlayerCommunicationControl.  REPLICATED.
  0x55754F51  AoWE.TPlayerControl.NewDay+0x1AD
              0x55754F18  cmp [map+0x174], 1      ; day 1 only
              0x55754F36  cmp byte [map+0x13A],0  ; 0 = local, 1 = network
              0x55754F3D  jne 0x55754F57          ; NETWORK MP -> SKIP Randomize AND the write
              0x55754F3F  call System.Randomize
              0x55754F51  mov [map+0x22C], RandSeed
              0x55754F68  mov [map+0x230], [map+0x22C]   ; anchors the synced stream, day 1
serialised:   0x5577702C  AoWE.TAoWHSMap.ReadWrite+0x2CC   lea edx,[ebx+0x22C]; mov ecx,0x24
readers:      0x55754F5C, 0x5575FD36 (TStructure.GenerateRazeDefenders+0x1A),
              0x557ABCD5 (City.TCity.GenerateRebelUnits+0x29)
```

Set once before day 2, never written again, streamed, identical on every peer. In network MP the
local `Randomize` path is skipped **precisely so the replicated setup value stands**. Vanilla
already trusts it as a per-game salt in two roster generators, and this repo already relies on it
unnamed at both of those sites: `build_razeroster_vary.py` hooks `0x5575FD36` and replays
`add esi,[eax+0x22c]`; `build_razebattle_tower.py` hooks `0x557ABCD5` and replays
`add ebp,[eax+0x22c]`. Cite those two as the precedent.

Read as `[[<map ptr>]] + 0x22C`. ⚠ **The map pointer is per-binary — it is not one address:**

| binary | map pointer | note |
|---|---|---|
| `AoWEPACK.dpl` | `[0x558E9494]` → map | in a cave this needs the `call $+5; pop; sub` anchor |
| `AoWz.exe`, `AoWzCompat.exe` | `[0x0045DF7C]` → map | IAT slot for `AoWEPACK.dpl!AoWE.AoWHSMap`; 678 vanilla sites use `mov eax,[0x0045DF7C]; mov eax,[eax]` |
| `AoWDevEd.exe` | `[0x0043289C]` → map | **different slot** — the editor is a different build; 119 sites |

(verified 2026-09-09; `AoWEPACK.dpl` also has `[0x558FA040]` = `AoWE.AoWHSMap` reachable *directly*,
one indirection fewer, which is what §4.1's listing uses.)

Two caveats, both to be stated in any script that uses it:

- It is **0 or stale until `NewDay` runs on day 1.** A P4 site that could evaluate during setup must
  tolerate 0 — FNV mixes 0 perfectly well, so the only real requirement is to guard the nil map
  pointer before dereferencing it.
- A hotseat/PBEM game gets the value from `Randomize`; a network game gets it from the setup
  exchange. Both are per-game and both are replicated — different provenance, same guarantee.

**Minting a new field was considered and rejected.** It would work: property tables are id-indexed
(`aow1-property-table-serialization`), so a new `ReadWrite` id is backward-compatible and degrades
to zero in an old save. But it costs an instance-size grow, a `ReadWrite` cave, a free property id,
an init hook and a **permanent save-format commitment** — to duplicate a field vanilla already
maintains correctly.

#### Anti-patterns — each with the reason it fails

1. **P1 outside a synchronised context.** `GetSynchronised @0x55775608` is false, so
   `TAoWHSMap.Random` shows "Invalid AoWHSMap.Random use" and returns 0. The modal means the hook
   site is wrong, not that the call needs suppressing.
2. **Silencing that modal with bit 3 of `[*0x558FA040 + 0x3C]`.** It takes the `jne 0x557782CB`
   branch, skipping all seed bookkeeping: **it makes the call raw** (§4.6). Legitimate only where
   the context is genuinely unsynchronised *and* the consequence is cosmetic —
   `build_raiseterrain_lavadirt.py`'s `cave_dirtdelay` is the one sanctioned use. Never a fix for a
   misplaced hook.
3. **P1 inside tactical combat.** The guard trips *and* it perturbs `[map+0x230]`, the value
   `TPlayerControl.GetSyncValue @0x55754CE8` reports to the desync comparator.
4. **A conditional raw draw inside combat.** Draw-count asymmetry — invisible to `rng_audit.py`
   *and* to the comparator. §4.5; worked example `build_minddecay_oos.py`.
5. **P3 for anything that must survive a reload.** `System.RandSeed` is per-process, so reloading
   re-rolls it. Wherever the result is an offer or a reward that is a player-facing exploit, not a
   cosmetic difference.
6. **`map[+0xE4]` (game name) as a P4 salt.** Per-**map**, not per-game: two playthroughs of the
   same map hash identically. It is also an AnsiString, so reading it is a length-driven loop rather
   than a dword read.
7. **`map[+0x230]` as a P4 salt.** That is the live synced seed and it advances on every draw
   (`0x557782B4`), so it holds a different value at every evaluation — which destroys the one
   property P4 exists to give.
8. **Hand-rolling the hash.** `import rngstd`. keystone encodes `xor eax,edx` as either `31 D0` or
   `33 C2` depending on spelling, so two hand-written sites drift apart and `--hash` stops finding
   them. **A P4 site whose bytes do not contain `rngstd.SIGNATURE` is off-convention by
   definition.**
9. **Minting a fifth pattern without adding it to this section first.** The taxonomy being closed is
   the entire point; a pattern that exists only in one script's docstring is not a convention.

#### Emitting P4 — `build_scripts/rngstd.py`

Returns literal `bytes`, never an asm string, and assembles nothing.

| call | bytes | emits |
|---|---|---|
| `basis()` | 5 | `mov eax, 0x811C9DC5` |
| `mix()` | 8 | `xor eax,edx ; imul eax,eax,0x01000193` — one per input, unrolled, **never a loop** |
| `fmix32()` | 33 | the MurmurHash3 finaliser |
| `range_n(n)` | 7 | `mov ecx,n ; mul ecx` → **EDX = 0..n−1** |
| `hash_pct(inner)` | 45 + len(inner) | `basis() + inner + fmix32() + range_n(100)` |
| `model(salt, *keys, n=100)` | — | the identical arithmetic in pure Python |
| `SIGNATURE` | 6 | `69 c0 6b ca eb 85` — locates P4 sites |

**First shipped P4 site, 2026-09-09** — `build_heroskill_race.py`, the per-race hero level-up offer
gate, `0x006280A9` in `AoWz.exe` and `AoWzCompat.exe`. Reference implementation for the whole pattern:
salt + 3 keys, `mul` clobbers EDX:EAX so the two values it must keep are pushed across the hash, and
the script asserts its emitted bytes are `basis() + 4×mix() + fmix32() + range_n(100)` in that order
before writing. `02-abilities-modded.md` Feature 1.

⚠ **`--hash` cannot attribute an EXE cave.** Its `_HEX_RE` indexes only `0x55xxxxxx`–`0x58xxxxxx`
literals, so an `AoWz.exe` P4 site prints `UNOWNED (no build script)` however carefully the script
declares its address. The site is still *found*, which is what `--hash` is for; only the owner column
is blind. Widen the regex when the first person is bothered by it.

**EAX accumulates; the caller puts each input in EDX and emits one `mix()`. Clobbers EAX, EDX, ECX
and flags; preserves everything else. After `range_n` the answer is in EDX; EAX is destroyed.**
Percentage gate: `mov ecx,100 ; mul ecx ; cmp edx,<pct> ; jb pass`. Every instruction is
register-only, so the blob is position-independent and safe verbatim in a DPL cave — only the
caller's own input loads can break that.

`model()` is not decoration. Use it to assert the site's calibration at build time and to let QA
check an entire outcome table without launching the game.

⚠ **The multiply-shift bias is a standing accepted ruling — do not "fix" it.** `2^32/100 =
42949672.96`, so 4 buckets in 100 are short by one value in ~4.29e7: a relative deviation of
2.3e-8. Same bias `System.@RandInt` has always had (§4.2). A rejection loop would cost a branch, a
second evaluation path and — in a combat context — draw-count asymmetry.

⚠⚠ **A P4 site is invisible to `rng_audit.py --owners`, by construction** — it references neither
generator, so the count of modded RNG sites does not move when you add one. Verify it with

```bash
python "Modding Resources/re_tools/rng_audit.py" --hash
```

which scans every EXECUTE section of every module for `SIGNATURE` and attributes each hit to its
build script. Without it, "the audit is clean" silently means "I did not look".

---
## 5. Cave space: the rules, then the map

### 5.1 Position-independence

The `.dpl` packages (`AoWEPACK.dpl`, `AoWTCPCK.dpl`, `aowInt.dpl`) never load at their preferred
image base — they rebase at runtime (`aow1-dpl-rebasing`). **Every cave written into a `.dpl` must
be position-independent**: rel32 `call`/`jmp`, register-only addressing, or the `call $+5; pop; sub`
delta idiom to reach an absolute data address. Reuse a VMT slot that already has a `.reloc` entry, or
jump *into* existing code to borrow its already-relocated globals.

**Exe caves are the exception.** `AoWz.exe`, `AoWzCompat.exe`, `AoWDevEd.exe` and `AoWzEd.exe` load at a
fixed base (`0x00400000`), so caves there may use absolute addresses directly.

### 5.2 ⚠ keystone `push` imm8 trap

`push 0xFFFF` assembles as `6A FF` = **push -1**, silently — keystone picks the imm8 encoding without
warning that the value doesn't fit. **Disassemble every cave you assemble** before trusting it:

```bash
python "Modding Resources/re_tools/dasm.py" AoWEPACK.dpl <cave VA> <len>   # or a script's own --dis flag
```

### 5.2b ⚠ Scan `.reloc` across the HOOK WINDOW, not just the cave

A byte-run that carries a `.reloc` entry cannot be displaced. The loader adds the rebase delta to
the dword at that address, so an `E9 rel32` written over one comes out with the delta folded into
its displacement and jumps somewhere arbitrary — at load, silently, and only on the real (rebased)
image, never in a static byte-check.

Worked example (2026-09-09, `build_panic_cleardamage.py`). `TCombatObject.ExecuteDamage
@0x55726C58` carries four `.reloc` entries in its body: `0x55726C34`, `0x55726C6F`, `0x55726C74`,
`0x55726CA9`. The entry site `0x55726C58`–`0x55726C5D` is clear, so the hook goes there. ⚠ **The
tempting alternative `0x55726CA8`** — `mov al, byte ptr [0x55726D3C]`, a 5-byte instruction that
looks like a perfect hook window — **sits directly on the `0x55726CA9` entry** and would be
corrupted at load.

Make the scan part of the script, not part of the scoping pass: parse the base-relocation directory
(data directory index 5), skip type-0 padding entries, and abort if any target falls inside either
the hook window or the cave reservation. `build_panic_cleardamage.py`'s `PEFile.relocs_in(lo, hi)`
is ~20 lines and runs on every invocation including the dry run — copy it.

### 5.2c ⚠⚠ The other half — an entry that SURVIVES the displacement corrupts code at every load

§5.2b says "don't put a hook on a `.reloc` entry". The complementary defect is what happens when you
do it anyway, or when the displaced instruction *was* the absolute operand the entry described: **the
entry stays in the table.** The loader then adds the rebase delta to whatever bytes now occupy those
four addresses — live code — **on every launch, in memory only.**

⚠⚠ **Nothing in this project's static toolchain can see it.** The file on disk is correct, `dasm.py`
is correct, a byte-diff against the pristine DLL is correct, and the owning build script verifies
clean. The corruption is applied by the Windows loader *after* every one of those checks.

**Module bases are 64 KB aligned, so the delta's low 16 bits are always zero: only bytes RVA+2 and
RVA+3 of the relocated dword move.** A stale entry therefore smashes exactly two bytes, two bytes
into the new instruction stream — which is why the damage is so localised and so easy to mistake for
something else.

**Worked example — the Death Altar (found 2026-09-11, `build_relocfix.py`).**
✅ **CONFIRMED WORKING 2026-09-13** — the crash is gone in game, and the repair shipped in the
2026.09.13 release (`AoWEPACK.dpl` md5 `841ed66aca7e`). ⭐ That confirmation is worth more than a
normal green: this defect was **invisible to every static check** — the file, `dasm.py`, the
byte-diff and the owning build script were all correct — so playing it was the only instrument that
could ever have settled it. Vanilla `ExecuteStormDamage` selects the Death-storm debuff mask with

```
557807F8  66 8b 15 40 08 78 55      mov dx, [0x55780840]        reloc @RVA 0x807FB
```

The live build replaced that arm with `eb 1a` (jmp, for the no-debuff storms) at `0x557807FA` and
`66 ba 20 00` (`mov dx,0x20` — Death) at `0x557807FC`, and left the entry. Every launch the loader
rewrote `0x557807FD`/`0x557807FE`, so the **Death** arm — and only the Death arm — executed garbage.
Divine (`0x55780802`) sits past the relocated dword; Pestilence (`0x55780808`) keeps its own, still
valid, entry. That is exactly the observed symptom: Death Altar faults, the other two storms are fine.

```
Exception EExternalException in module AoWEPACK.dpl at 000807FE.
External exception 80000003.
```

⭐ **Decoding that dialog: `000807FE` is the SECOND corrupted byte** (`base + RVA+3`), and
`80000003` = `STATUS_BREAKPOINT` — the garbage decoded to an `int 3`. Simulated across all 65536
64 KB-aligned deltas, 95 of them put an `int3` at exactly `0x557807FE`, all in the band
base `0x00BC0000`–`0x01B30000` — which is where a **non-ASLR** package lands (AoWEPACK.dpl carries
`DllCharacteristics = 0x0001`, no `DYNAMIC_BASE`, so the loader takes the first free region, low).
Exactly **one** delta of 65536 leaves the instruction intact, and it is delta 0, which never happens.
⚠ The exception code is therefore a function of the load address: the same defect presents as a
breakpoint on one boot, an access violation on another, and a silently wrong answer on a third.

**The fix: flip the entry's 4-bit type from 3 (`HIGHLOW`) to 0 (`IMAGE_REL_BASED_ABSOLUTE`).**
Type 0 is defined as "skip; used to pad a block" — ntdll's `LdrProcessRelocationBlockLongLong`, and
ReactOS's and Wine's equivalents, do `case 0: break;` without ever reading the offset field, so the
12-bit offset survives as an exact `--undo` key and no block size, entry count or file length
changes. **One byte changes on disk per entry** (the high half of the 16-bit entry word, `3c`→`0c`);
`pack_into("<H", …)` writes two and one of them differs. It is the correct repair, not merely the
cheap one: the absolute operand the entry described no longer exists, so there is nothing left to
relocate. ⚠ Do **not** "tidy up" by zeroing the offset as well — that costs the `--undo` key, and
under the only failure hypothesis that matters (a loader that ignores the type field) it would
redirect the bogus fixup from dead bytes onto a live dword at page+0, where several pages already
carry a real type-3 entry.

**The standing check — run it after any feature that displaces bytes:**

```bash
python "Modding Resources/build_scripts/build_relocfix.py" --audit
```

It runs three rules, and **the first alone is not sufficient**:

- **A — "target dword is not inside `[ImageBase, ImageBase + SizeOfImage)`".** Needs nothing but the
  module. Vanilla scores **0 across 35 root modules, ~225 000 entries**, four linker vintages, and
  the margins are comfortable rather than marginal (the nearest legitimate relocated dword in any
  module sits ≥`0x1000` above its ImageBase and ≥`0x37F8` below the image end), so there are no
  false positives to adjudicate.
  ⚠⚠ **But it has a systematic false-negative class.** When the displaced instruction's operand sat
  at the **end** of the displaced range, the tail of the old address survives and the residual dword
  still reads as a valid in-image VA. Four entries in `AoWz.exe` leave `0x0045A420`/`0x0045A400`
  behind exactly this way and rule A calls every one of them clean.
- **B — "the byte immediately *before* the operand differs from the vanilla twin".** The opcode or
  modrm moved, so the operand is orphaned. A deliberate absolute **retarget** changes only the dword
  and is correctly ignored. Measured over all 33 packages and both exes: B is a strict superset of A
  and produced **zero** false positives. ⚠ It needs a vanilla twin at the root — `AoWDevEd.exe` and
  `AoWzEd.exe` have none (the root copy is the same modded build), so **the editor is covered by
  rule A only**.
- **C — the reverse:** a **type-0** entry whose dword *is* in-image and whose preceding byte matches
  vanilla means a feature was reverted and put its absolute operand back **under a relocation this
  script disabled**. In `AoWEPACK.dpl`, which always rebases, that is live, not latent. The coupling
  table is in §6.5a.

The 2026-09-11 sweep neutralised **eleven** entries across four binaries — see §6.5a.
⚠ `--audit` globs `Ziggurat\*.dpl|*.exe` only; **`Ziggurat\Ziggurat release\` is staging and is not
covered.** Run `re_tools/mod_manifest.py --stage` before cutting a release or the payload ships the
pre-fix binaries.

### 5.3 CODE is read+execute only — mutable state goes in BSS

AoWEPACK's CODE section is **read-only at runtime past the initial load** in the sense that matters
here: section flags carry no WRITE bit, so a cave may **execute** from CODE but must never **write**
to it. Putting mutable scratch inside a CODE cave produces a page-fault crash the instant the first
write happens — confirmed the hard way (a *"Exception occurred during TArmyDefaultMoveTE"* crash
when Path's ring-detection scratch was first placed inside the CODE region).

**Rule: caves may execute from CODE; mutable scratch belongs in a writable section.**

| section | starts at | flags | note |
|---|---|---|---|
| DATA | `0x558E8000` | `0xC0000040` | initialised data, writable |
| **BSS** | `0x558EA000` | `0xC0000000` | zero-init, writable. vsize `0x10231` ends ~`0x558FA231`; the page rounds up to `0x558FB000`, so **`0x558FA800` onward is committed, zeroed, and past everything the game itself uses** — free scratch |

A code cave reaches BSS with the usual call/pop-delta trick and a constant offset (CODE and BSS share
the same runtime rebase delta). Known BSS allocations in the current tree: the per-hex ring-detection
centre stash at `0x558FA800` (2 bytes, §7 below), and the combat-log roll-tracking scratch at
`0x558FA820`/`0x558FA82C` (12 bytes each: `+0` ok flag, `+4` diff, `+8` stat). Nothing else is
currently known to claim BSS space — it is far from full.

### 5.4 CODE cave space is NOT scarce — allocate upward from `0x55810000`

An early investigation log wrongly concluded the cave-space pocket was filling up; that was only
ever true of one crowded corner. Measured directly: `AoWEPACK.dpl` CODE starts at VA `0x55701000`,
vsize `0x1E6918` (virtual end `0x558E7918`), rawsize ≥ vsize, so the **whole section is file-backed**
— nothing here depends on the loader zero-filling anything. In the **pristine shipped DLL** the last
non-zero byte is `0x5580BDEE`; historically (2026-07-08) the live DLL's last non-zero byte was
`0x5580F959`, leaving 884,670 verified-zero bytes up to the section end. That figure is long stale by
now — see the cave-ownership table below for the current high-water mark — but the conclusion it
established still holds: **allocate new DLL caves upward from `0x55810000`**, hard ceiling
`0x558E7918` (DATA starts `0x558E8000`; stay under `0x558E7000` to be safe). As of this merge the
highest-addressed cave found in `build_scripts/` is `build_powerleech.py`'s
`0x55848000..0x55848400` — comfortably inside the free run, with hundreds of KB still untouched above
it.

The **crowded pocket** below `0x55810000` (roughly `0x5580C000`–`0x5580FFFF`) is where the earliest
features landed and where most of the deliberate cave-sharing lives (see the ownership table). New
work does not need to go there; the table exists mainly so an old cave in that pocket isn't mistaken
for free space.

### 5.5 Exclusive reservations vs tight footprints — read this before treating any two addresses as colliding

Two different conventions coexist in `build_scripts/`, and conflating them produces false alarms:

- **A tight footprint**: `CAVE = 0x...`, and the emitted body is however many bytes the assembler
  produces. `--undo` zeroes exactly that many bytes, no more. A neighbour placed a few bytes past the
  *declared* constant, but past the *actual* emitted body, is not a collision — the author placed it
  there deliberately, having checked the real footprint, not just the constant. (`CAVE_MAX`/
  `CAVE_LIMIT`-as-a-length in these scripts is usually a generous **reservation ceiling**, e.g.
  "`CAVE_MAX = 0x40` — reserved; the emitted length is what `--undo` zeroes.")
- **An exclusive reservation**: a whole span (often a round number — a page, `0x100`, `0x200`,
  `0x400`) is asserted zero-or-ours on every run, specifically so nothing else ever lands inside it,
  even in slack the current body doesn't use. These are called out explicitly in the scripts
  ("EXCLUSIVE RESERVATION `0x...`..`0x...`", or "asserted zero-or-ours across the whole span") and
  are the addresses worth respecting most carefully. Current exclusive reservations:
  `0x55820800..0x55820FFF` (`build_caster_cost.py`), `0x55821000..0x558213FF`
  (`build_dispelmagic5.py`), `0x55822000..0x55822FFF` (`build_shipyard_income.py`, a full page),
  `0x55823000..0x55823FFF` (`build_shield.py`, a full page), `0x5582E000..0x5582E07F`
  (`build_burning_sailing.py`), `0x5582F000..0x5582F0FF` (`build_lightning_ignites.py`),
  `0x55834000..0x55835FFF` (`build_ai_sitesearch.py`, 8 KB), `0x55846000..0x5584607F`
  (`build_spellcast_herotier.py`), `0x55847000..0x558470FF` (`build_spellward_rescope.py`),
  `0x55848000..0x558483FF` (`build_powerleech.py`).

**Do not report a "collision" from raw constant arithmetic alone** unless it falls into one of these
two buckets: (a) two scripts declare the literal *same starting address*, or (b) one script's own
comment explicitly says it is reusing, rewriting or bounded by another's cave. The canonical table
below is built on that basis; it does not attempt to re-derive new collisions from spacing alone.

### 5.6 The lesson worth more than any single fix

From the `build_dispelmagic5.py` cave-relocation postmortem (§6 has the full story):

> "No script references this zero run" is a statement about a MOMENT IN TIME, not a reservation.
> Record a cave address in the allocation map the day it is claimed, declare its extent, and make
> `--undo` zero ONLY the emitted length — never a rounded reservation, which is what would let one
> feature's undo silently destroy another's cave.

### 5.7 Scripts that must NEVER be (re-)applied, and why

A short, high-value list — check it before running any script's `--apply` for the first time in a
session, and re-check after adding a new feature near any of these addresses:

| script | do not | why |
|---|---|---|
| `build_scroll_gfx.py` | **apply at all** | CONFIRMED HARMFUL in-game (2026-08-01): retyping four `ITEMGFX` records to item type 5 for a scroll icon breaks the image system — blank hero portrait, no spell icons, spell costs render as nonsense (1, 5, 0), no error dialog. Isolated by a clean single-variable A/B (reverting this file alone made every symptom vanish). Root cause not pinned down; do not retry as written. Better routes, untested: point the item's own graphic index (`item+0x40`, pfs tag 7) directly instead of relying on `FindItemTypeGFX`'s type-keyed default, or *append* new type-5 records rather than retyping existing ones. |
| `build_icestorm_lava.py` | **apply at all, currently** | Its `ELSE_SITE` hook at `0x557CCEF0` was taken over by `build_chasm_sky_spellguard.py`, which chains through it (`jmp 0x5580DB20` on the "not Chasm/Sky" path — this feature's cave still runs). Re-applying `build_icestorm_lava.py` rebuilds that 5-byte redirect from its own original bytes and **silently unlinks the spellguard chain** — the self-verify mismatch this produces at `0x557CCEF0` is that broken chain, not damage to Ice Storm itself. Same failure mode, and same fix shape, as the magebane/Shield case directly below — a script written before its chain successor existed will rebuild the link out of existence if re-run naively. (Ice Storm's separate synced-RNG fix, §4.8, is already installed via a call retarget and needs no re-run.) |
| `build_raiseterrain_mtn.py` | **apply, ever** | ⚠ SHELVED (2026-07-07) for an independent reason first: the premise ("Raise Terrain forces grass under mountains") was an unverified inference the user disproved in-game. Its cave address (`0x5580DB40`) is *also* now occupied — see the ownership table. Kept only because the doc holds two diagnosed vanilla bugs (a `TGeneral` slot-overflow crash, a Seduce double-stack) that may be useful later. |
| `build_patch.py` | **apply without reading it first** | `--apply` runs `shutil.copyfile(DPL, BACKUP)` at line 284, where `BACKUP = AoWEPACK_original_backup.dpl` — **the pristine byte-diff reference**. Running this script's `--apply` overwrites the pristine reference with a copy of the current, already heavily-patched live DLL, permanently destroying the vanilla baseline every other script's verify-before-write and this whole toolchain's "byte-diff against pristine" discipline depends on. (Verified 2026-09-03: the reference file is still intact — this script has not been run since the convention was established.) This is the original movement-predictor-fix script, superseded in spirit by the current `.pre-<feature>` + surgical-`--undo` convention; if the predictor needs work, treat this script as a read-only reference for the mechanism, not something to run. |

Two scripts that carry a *similar-sounding* trap and are **not** on this list, because the trap was
fixed — recorded here so an old warning doesn't get carried forward past its fix:

- **`build_magebane.py`** — an earlier state of this script would, if `--apply`'d before undoing
  `build_shield.py`, silently unlink Shield's ranged penalty (the two share a chained exit jump —
  see the ownership table). **Fixed 2026-08-29**: the script now detects at build time whether
  Shield's ranged cave (`0x558230D0`) is present and chains into it, or returns straight to the
  engine if Shield has been undone. Re-applying `build_magebane.py` is safe in either state and in
  either order; no revert ordering is required any more. If a standing note anywhere still says
  otherwise, it predates 2026-08-29 and should be corrected at the source.
- **`build_invis_penalty.py`** — rewrites `build_trueseeing.py`'s three cave bodies in place, at the
  same addresses, and is designed to do so; this is a declared, working coupling (ownership table),
  not a hazard.

---
## 6. The canonical cave-ownership table

Built by reading the `CAVE`/`CAVE_VA`/`CAVE_BASE`/`CAVE_LIMIT`-style constants declared across every
`build_*.py` in `Modding Resources/build_scripts/` (over 300 such constants across more than 110
scripts once every named cave, sub-cave and reservation boundary is counted), cross-checked against
each script's own docstring for placement rationale and known couplings. This is a **method
document**, not a live occupancy scanner — it will drift as new features land; re-derive rather than
trust it blindly once it's more than a few weeks old (`grep -rn "CAVE.*= 0x" build_scripts/` is the
starting point for a refresh).

Read §5.5 before treating any two entries below as colliding: a script's declared `CAVE_MAX`/
`CAVE_LIMIT` is usually a generous reservation ceiling, not its tight footprint, and a neighbour
placed inside that ceiling but outside the real body is normal, deliberate allocation — not a bug.
The entries flagged **⚠ COLLISION** or **⚠ COUPLED** below are the ones with actual textual evidence
of a problem or a deliberate shared claim; everything else is a plain "who's here" reference.

### 6.1 AoWEPACK.dpl — CODE `0x55701000`–`0x558E7918`, DATA from `0x558E8000`, BSS scratch from `0x558EA000`

The historical "884,670 free bytes" measurement (2026-07-08) is long stale; treat the table below as
the current high-water reference instead. Allocate new work above the highest entry here, inside the
`0x55810000`+ open run (§5.4).

⚠⚠ **Hunting orphaned cave tails: the alignment heuristic DOES NOT WORK. Five candidates, five false
positives (2026-09-12).** The failure mode being hunted is real — a script writes `len(new)` bytes, so
a cave that *shrinks* between edits leaves the old tail live on disk; `build_razebattle_tower.py`
Stages 12c/12d/12e absorbed six of them (`10-ai-and-structures.md` §4.4.11). The tempting shortcut is
that **a cave starts at an aligned address, so an unaligned start means a tail**. It is wrong, and all
five unaligned islands in `0x5580B000..0x55820000` turned out to be live, for three distinct reasons:

- **The prologue is split across the call site.** `0x5580C001`'s caller does `push ebp` at
  `0x5579F3E4` and the cave opens on `mov ebp,esp`. The cave is *supposed* to start on an odd byte.
- **A cave's first byte is legitimately `0x00`.** `0x55818200` opens `00 d0` = `add al,dl`;
  `0x5580F0C0` is a data ladder whose first element is 0. A non-zero-run scan clips the leading byte
  and reports the address **+1**, manufacturing an unaligned start out of a perfectly aligned cave.
- **Caves are simply packed unaligned**, particularly in the `0x5580C000` hand-edit pocket
  (`0x5580C0A1`, `0x5580C211`).

⭐ **Only the reference proof settles it**, and it is cheap: every `E8`/`E9` rel32 in `CODE`, every
rel8 (`EB`/`70`–`7F`) **excluding jumps internal to the span**, every literal dword in **every**
section of the whole file, every `.reloc` entry, and the fall-through question — does the preceding
cave end in `ret`/`jmp`, or run on into the span? A span is dead only when all five come back empty.
⚠ **Two rel8 false-positive classes recur** and both cost time: a jump *inside* the dead blob to
itself, and a byte that is not an instruction boundary at all (a displacement or immediate byte that
happens to be `0x7x`). Disassemble the host cave from its real entry before believing any rel8 hit.

⭐ **Run the vanilla byte-diff first — it is one comparison and eliminates most candidates.** The
pristine root install is the baseline, and **vanilla's own CODE ends at `0x5580BDEE`**: anything above
that which is non-zero is mod content, anything below that matching the root is engine code nobody
should touch. Two of the largest islands found by a naive scan (`0x5580B3B8`, `0x5580B66C`) are
vanilla data, not caves.

⭐ **A "no build script mentions this address" test is weak on its own**: 40 of the 142 non-zero
islands in cave space have a start address no script names, because addresses are often computed
(`CAVE_BASE + 0x60`), because zero-padding inside one cave splits it into several islands, and because
the `0x5580C000`–`0x5580C600` pocket is pre-build-script hand edits that no script will ever name.
Attribute a cave by its **hook site** instead — grep the scripts for the caller VA, not the cave VA.

**The crowded early pocket, `0x5580B000`–`0x5580FFFF`** — the oldest features, plus two undocumented
hand-authored Ziggurat caves that predate the build-script convention entirely:

| VA | script | size | feature |
|---|---|---|---|
| `0x5580C001` | *(none — pre-existing Ziggurat hand-edit)* | 40 B | **LIVE**, `call`ed from `0x5579F3E5`. Remaps a byte through `[ecx]`: `1→4`, `3→1`, `4→2`, `5→2`, `0xC→4`. ⚠ **Its prologue is SPLIT across the call site** — the caller does `push ebp` at `0x5579F3E4` and the cave opens on `mov ebp,esp`, so it legitimately starts at an **odd** address and `0x5580C000` is zero. Another of the 2026-07-08 hand edits; purpose not recorded — ask the author (§2). Audited 2026-09-12. |
| `0x5580C029` | `build_copper_medal.py` | 21 B | **LIVE**, `call`ed from `0x557A8DBE`. `mov edx,15; mov eax,esi; call TUnit.AddXP@0x557828B4` — the **Warmonger** city-enchantment flat-15-XP grant the script's docstring describes. Packed immediately after the cave above, behind a 4-byte `nop` entry pad. Audited 2026-09-12. |
| `0x5580C0A1` | *(none — pre-existing Ziggurat hand-edit)* | 33 B | **LIVE**, `call`ed from `0x5579F617`. Predicate: returns 1 iff `[esi+0x14]` ∈ {1,3,4,5,0xC} — the same constant set the `0x5580C001` remap keys on. ⚠ **Not a duplicate of the similar blob at `0x5580C0D8`**, which is separately live; they were mistaken for a shrink-tail pair on the 2026-09-12 sweep. Purpose not recorded — ask the author (§2). |
| `0x5580C0D8` | *(shared)* — `build_morale_hero_atk.py` owns `0x5580C0FC` inside it | 101 B | **LIVE, two entries**: `0x5580C0D8` `call`ed from `0x5579F63F` (an unattributed hand-edit predicate, near-identical to `0x5580C0A1` above), and `0x5580C0F7` reached by `jmp` from `0x55782A05` in `TUnit.GetAttack` — the **unit-side** morale→Attack ladder, twin of the hero-side cave at `0x55818200`. ⭐ Both morale-ATK caves are now in this table; per `aow1-morale-three-stats`, the ATK term is a bespoke cave on the raw byte and is **invisible to a `GetMorale` xref hunt**. Audited 2026-09-12. |
| `0x5580C211` | *(none — pre-existing Ziggurat hand-edit)* | 12 B | **LIVE**, `call`ed from `0x557D5EE2` (which then does `imul eax,eax,3`). `call 0x55779AC8; mov eax,[eax+0x18]; sar eax,3; ret`. Purpose not recorded — ask the author (§2). Audited 2026-09-12. |
| `0x5580C240` | *(none — pre-existing Ziggurat hand-edit)*, formalised/extended by `build_marksmanship_atk2.py` | — | Marksmanship ranged rework + Cave/Depths height malus. One of the caves found by the 2026-07-08 diff sweep with **no owning script or doc** — five years of hand edits, not corruption; ask the author rather than reverse-engineering intent (§2). |
| `0x5580C290` | *(none — pre-existing author hand-edit)* | 31 B | Animate Dead unit-type selector (198 Archer Undead vs 201 Swordsman Undead), called from `TAnimateDeadCA.Execute @0x557FA346`. Paired with the 15-byte nop at `0x557FA369` that removes the `0x82` "Combat Resurrected" grant and makes the raise permanent. ⚠ Its selector reads the **pointer** `esi`, not a field — per-process heap layout, so it is neither SYNCED nor RAW; MP peers can raise different undead. ⚠ Do not attach a persistent enchantment to these units — see `04-spells-modded.md`. `build_marksmanship_atk2.py` already treats this address as its `SLACK_END` ("real code resumes here"), so its slack assert is consistent with this cave. |
| `0x5580C500` | *(orphan — no build script)* | — | replaces `SummonSpells.TSummonSpell.SetupSummonSpellTE`; multi-spawn roll, correctly inherits vanilla's RAW draw at this site (§4.8) |
| `0x5580C810`–`0x5580C880` | `build_simfly.py` | — | fast-combat-equivalent flying economics in `TCombatPredictor` (`CAVE_EXEC`/`CAVE_CV`/`CAVE_RETAL`) |
| `0x5580C910`–`0x5580D640` | `build_razebattle_tower.py` | ~15 named sub-caves | Raze-as-real-battle, Stages 2–10 (tower raze gated on outcome, avengers suppressed, city raze dispatch/guard/seed, rebellion, loot battle). Internal layout is self-managed by this one script; ceiling `CAVE_END_LIMIT = 0x5580D640` is enforced against the next two entries. |
| `0x5580D200` | `build_razeeval_timing.py` | 18 B (`cave_valfix`) | AI post-capture raze evaluation made deterministic. **⚠ COUPLED**: `build_razebattle_tower.py` explicitly reserves down to this address (`CAVE_VALFIX_RESV`) and never writes at or past it — a correctly-coordinated adjacency, not a collision. |
| `0x5580D600`–`0x5580D640` | `build_razeroster_vary.py` | to `CAVE_LIMIT = 0x5580D640` | hidden raze-defender roster re-rolls per game-day (the "seed cave"). **⚠ COUPLED**: same relationship as above, from the other side (`build_razebattle_tower.py`'s `CAVE_SEED_RESV`). |
| `0x5580D700` | `build_patch.py` | — | `CAVE_BASE` for the original movement-predictor cave. **Do not `--apply` this script** — see §5.7. |
| `0x5580D900` | `build_spellcast.py` | — | Unit Spellcasting Phase 1a (auto/fast-combat casting). **⚠ COUPLED**: `build_fastcast_gate.py` (a diagnostic A/B toggle) directly flips bytes inside this cave (`CAVE_ISCASTER`) rather than owning its own — it has no cave of its own. `build_spellcast_multiturn.py`'s `CAVE_BASE` is the same address (M2 multi-turn channelling extends this cave in place, `PERSIST_BASE = 0x5580D990` is its own follow-on boundary, shared with `build_spellcast_persist.py` below). |
| `0x5580D990` | `build_spellcast_persist.py` / `build_spellcast_multiturn.py` | — | C2: persist casting state across save/load. **⚠ COUPLED**: both scripts declare the identical `PERSIST_BASE`, by design — `spellcast_multiturn`'s M2 tiergate cave must end below it. |
| `0x5580DA20` | `build_firefeed.py` | — | `cave_fireheal` — Fire heals Fire units |
| `0x5580DB20` | `build_icestorm_lava.py` | — | `cave_icelava` — Ice Storm cools Lava to Wasteland (the `ELSE_SITE` terrain branch) |
| `0x5580DB40` | `build_icestorm_lava.py` (**current, live**) — `cave_iceroll`, exactly 32 B, ends exactly at `0x5580DB60` | 0x20 | per-proc skip gate (25% chance of no terrain change per storm tick). **⚠ COLLISION, not live**: `build_raiseterrain_mtn.py` also declares `CAVE = 0x5580DB40` ("zero space, above cave_icelava"), written when `cave_iceroll` did not yet exist. That script is doubly dead — SHELVED since 2026-07-07 because its own premise was disproved in-game, *and* its target address is now occupied. Its own verify-before-write would abort cleanly if ever run, but **never apply it**. See §5.7. |
| `0x5580DB60` | `build_raiseterrain_lavadirt.py` — `cave_lavadirt` (51 B) | — | Raise Terrain: lava → 50% dirt. **⚠ COUPLED**: `build_raiseterrain_ug_earth.py` rewrites bytes inside this same cave in place (`LD_CAVE = 0x5580DB60`, byte-diffed and patched, not a fresh claim) as part of making Raise Terrain work underground — a second declared in-place-rewrite coupling, structurally identical to the invis_penalty/trueseeing case below. |
| `0x5580DC20` | `build_raiseterrain_lavadirt.py` | — | `cave_dirtdelay` (current; moved off `0x5580DBD0`, now dead, to skip stale bytes) |
| `0x5580DC80` | `build_lifesteal_roundattack.py` | — | `cave_lsround` — Lifestealing (0x76) / Dark Gift (0xA9) heals also fire on Round Attack hits |
| `0x5580DD30`+ | `build_path_outerring.py` | — | Path radius +1, 25% proc on the outer ring — `cave_stash` + three proc-gate caves; full mechanism in §7 below |
| `0x5580DF00` | `build_path_sand.py` | — | Path of Sand (new ability), `cave_cb` |
| `0x5580E060` | `build_path_transportgate.py` | — | Path abilities fire on the transporter, not just carried passengers |
| `0x5580E070` | `build_assassin.py` | — | Assassin / Hero Slaying, Phase 1 (melee). **⚠ COUPLED**: this cave's exit jump is repointed by `build_magebane.py` (chained-cave pattern, §6.4). |
| `0x5580E190` | `build_ranged_slayers.py` | — | `CAVE_RNG` — Phase 2 of the slayer work (ranged branch for Monster/Holy/Unholy/Assassin slaying). **⚠ COUPLED**: exit jump also repointed by `build_magebane.py`. |
| `0x5580E2A0`, `0x5580E300` | `build_turnundead_res.py` | — | Turn Undead damage = level × caster RES (`CAVE`, `CAVE2`) |
| `0x5580E370`, `0x5580E3B0`, `0x5580E400` | `build_trueseeing.py` (original owner) — **rewritten in place** by `build_invis_penalty.py` (v2) | — | `CAVE_TS_MELEE` / `CAVE_TS_MELEE3` / `CAVE_TS_RNG`. **⚠ COUPLED, deliberately**: both scripts declare the *identical three addresses*. v1 (`build_trueseeing.py`) gave True Seeing a +3/+1 attack bonus vs Invisible; v2 (`build_invis_penalty.py`) flips the framing — Invisible is a defensive advantage, and lacking True Seeing costs **−2 melee / −5 ranged** attack (not the −1/−3 an older design doc states — verified live: `build_invis_penalty.py:110-112`, `MELEE_PENALTY=2`, `RANGED_PENALTY=5`). v2 rewrites the three cave *bodies* at these same addresses; the chain plumbing v1 installed (the exit jumps into these caves) is unchanged and reused. Do not revert `.pre-trueseeing` to "undo" this — it predates combatlog/tierresearch/leadership4 and would silently undo them too; re-tune by editing v2's constants and re-applying, since it rewrites in place. |
| `0x5580E440`–`0x5580ED80` | `build_combatlog_dll.py` (**legacy, relocated 2026-07-22**) | — | old home of the combat-log capture cave; overlapped `build_tierresearch_dll.py`'s `cave_grant` at `0x5580ED80` by a few bytes (harmless padding, but broke `verify` forever — this is *why* it moved). Current home is `0x55811000`. Relocation is optional to vacate (`--vacate` flag zeroes the old bytes); **whether that flag was ever run is not established from the source alone — byte-check before assuming `0x5580E440` is free.** `build_invis_penalty.py`'s own `RNG_LIMIT = 0x5580E440` boundary still treats it as occupied ("combat-log worker"). Treat this address range as claimed. |
| `0x5580ED80` | `build_tierresearch_dll.py` | — | `CAVE_GRANT` — tier research mechanics (day-1 free spells, group completion). **⚠ COUPLED**: its `cave_day1` at `0x5580EE30` is **v2 since 2026-09-24** — a callable routine (`call` at `0x5577CC72`, `add esp,8 ; ret`, return path `jmp 0x5577CD4A` at `0x5577CC79`), because `build_pbem_leadersetup.py`'s `C_APPLY` calls it and pins its sha256. Undo `build_pbem_leadersetup.py` before any change to that routine |
| `0x5580EFC0`, `0x5580F000` | `build_leadership4.py` | — | `CAVE_COSTS` / `CAVE_NAME` — Leadership I–IV |
| `0x5580F0C0` | `build_leadership4.py` | 32 B | **LIVE DATA**, not code — two 4-byte ladders `{1,2,3,4}` at `0x5580F0C0`/`0x5580F0C8`, read absolutely by `mov al,[eax+…]` at `0x55766205` and `0x55766219` (**both `.reloc`-covered**, correct for vanilla-space code), plus a four-pointer block at `0x5580F0D0` holding link-time VAs `0x557BBF18/24/30/40`. ⭐ That block is read from inside the cave at `0x5580F030` by `mov ecx,[ebp+edx*4+0x5580F0D0]; add ecx,ebp` — **the delta-in-EBP rebase idiom**, so it is position-independent and correctly carries **no** `.reloc` entry. ⚠ Its first byte is legitimately `0x00` (ladder element), so a non-zero-run scan reports it as `0x5580F0C1`. Audited 2026-09-12. |
| `0x5580F100` | `build_leadership_fix.py` | — | fixes Leadership going permanently dead after stacking with another leader |
| `0x5580F140` | `build_leadership_aura.py` | — | Leadership aura refresh is instant after buying a level |
| `0x5580F180`–`0x5580F600` | `build_replaylog.py` | — | re-display a combat log when its replay reopens from Event History |
| `0x5580F600`–`0x5580FA00` | `build_effectroll.py` | — | combat log: report the resistance roll behind a debuff landing. **⚠ COUPLED**: `build_hitslope5.py` patches one byte inside this cave (`0x5580F6C3`) to keep the printed odds in sync with the halved to-hit slope — see §2's "attribution needs a byte range" trap. |
| `0x5580F900` | `build_debuffcache.py` | stride `0x20`/site | fixes Webbed/Entangled stat modifiers not applying to units |

**`0x55810000`–`0x5581FFFF`** — the "not actually scarce" open run, allocated upward since 2026-07:

| VA | script | size | feature |
|---|---|---|---|
| `0x55810000` | `build_ai_itempickup.py` (✅ confirmed working 2026-07-21) | — | AI heroes equip a matching item from an empty slot. Functionally **superseded** by `build_ai_itemloot.py` per that script's own docstring — check live state before reusing this address. |
| `0x55810200` | `build_ai_itemtarget.py` | 0x100 | applied then **REVERTED** 2026-07-22 (companion to the entry above) |
| `0x55810400` | `build_combatdiag.py` | — | diagnostic combat-create/destroy/raze logger |
| `0x55810500` | `build_effectroll_tacticalgate.py` (🔨 APPLIED, UNTESTED 2026-09-06) | 0x40 | gates the combat-log effect-roll emitter (`0x5580F605`, owned by `build_effectroll.py`) on `RING_TACTICAL` (`0x60D00C`) so it runs only in live tactical combat — off it (strategic storms via `build_stormeffectroll.py`, and auto-resolve) `HitRole` still runs but the emitter is skipped. **⚠ FORWARD HAZARD**: hooks 0x5580F605 inside `build_effectroll.py`'s cave; re-applying that script drops this gate silently — re-run this one afterwards. |
| `0x55811000` | `build_combatlog_dll.py` (current home) | — | combat log capture + line formatting |
| `0x55812000` | `build_chasm_sky_transitions.py` | — | Chasm/Sky terrain step 3 — cliff edges |
| `0x55812100` | `build_chasm_sky_spellguard.py` | — | Chasm/Sky terrain step 4 — keeps terraforming spells from overwriting the two appropriated terrain ids. **⚠ COUPLED**: this script took over the `ELSE_SITE` hook at `0x557CCEF0` that `build_icestorm_lava.py` also owns — see the `0x5580DB40` entry and §5.7. |
| `0x55812400` | `build_sitedefender_vary.py` | stride `0x40`/site | exploration-site / dungeon-prisoner rosters vary per site instead of being identical |
| `0x55812500` | `build_crusade_spawns.py` | 0x300 | Crusade spell spawn table rework |
| `0x55812800` | `build_stormeffectroll.py` | 0x40 | strategic-map storm/poison-plant debuffs roll vs Resistance instead of landing automatically |
| `0x55812880` | `build_mastery_cost.py` | 0x60 | Sphere Mastery mana economics rework |
| `0x55812900` | `build_magebane.py` | 0x200 (`0x55812900`–`0x55812AFF`) | new ability Magebane (+ATK/+DMG per enchantment on the target). Chains into three other scripts' caves — full mechanism in §6.4. |
| `0x55816000` | `build_drillmaster.py` | — | new passive ability Drillmaster (id `0xAB`; a stale line in this script's own docstring header says `0xAA` — the code constant `ABILITY_ID = 0xAB` is what's live) |
| `0x55817000` | `build_vision9.py` | — | `CAVE_COSTS`/`CAVE_NAME`/`CAVE_DATA`, `CAVE_BLOCK=0x400` — Vision becomes a 9-level ability |
| `0x55817400` | `build_marksmanship8.py` | — | `CAVE_COSTS`/`CAVE_NAME`/`CAVE_DATA`, `CAVE_BLOCK=0x400` — Marksmanship becomes an 8-level ability |
| `0x55818040` | `build_newturn_healcap.py` | 0x40 | fixes `TAbstractUnit.NewTurn`'s 8-bit overheal wrap |
| `0x55818080` | `build_medal_hpmv.py` | 0x40 | `CAP_CAVE` — medals grant HP/Movement; unit HP total cap |
| `0x55818100`, `0x55818130`, `0x55818160` | `build_healwrap_fixes.py` | 0x30 each | closes the last 8-bit heal-wrap sites (High Prayer fast-combat, High Prayer tactical, Healing Showers) |
| `0x55818200` | `build_morale_hero_atk.py` | 0x40 | gives heroes the same morale→Attack ladder units already have. Reached by `jmp` from the hook at `0x557883B1` in `AoWE.THero.GetAttack`; the ladder tests `[ebp+0x26]` against 21/41/61/81 for ±4/±2. ⚠ Its first byte is legitimately `0x00` — `00 d0` = `add al,dl`, completing the `add dl,[ecx+0x24]` the hook displaced — so a non-zero-run scan reports the cave as starting at `0x55818201`. Audited 2026-09-12. |
| `0x55818240` | `build_abilityte_itemgrant.py` | 0x30 | item-granted Healing/Dispel Magic order actually applies when it executes |
| `0x55818260` | `build_healing_rearm.py` | 0x40 | re-arms an item-granted Healing on new turn (chain partner of the entry above — both needed together) |
| `0x558180C0` | `build_hpbar_clamp.py` | — | fixes the vanilla "Blt Error" from a negative HP bar value ("re-homed 2026-08-24") |
| `0x55819000` | `build_cityflag.py` | 0x40 (two 0x20 sub-caves) | refreshes the city flag id when a city's upgrade level changes |
| `0x55819100` | `build_pad_skyalias.py` | 0x40 (10 B used) | structure pads read Sky (`0x0E`) as Chasm (`0x0B`). Reached **only** through `Pad.TPad`'s VMT `0x557FE6C8` slot `+0x12C`, not by any jump or call — so a hook-site scan will not find it. Register-only, PIC. |

⭐ **Growing `Release.hss` works** — `build_hss_addresource.py` (2026-09-20). Child offsets are stored
relative to the payload base that follows the child table, so appending a table entry shifts the base
and every child together and **no child offset changes**; only root tags pointing past the child table
need bumping, then `re_tools/hss_crc.py --fix`. Applied 2026-09-21: 1126 → **1131** children, opens in
AoWzEd and runs in the game. ⛔⛔ **A clone MUST be given a fresh tag 3 (its editor grid slot), or it
frees its donor** — full account in `09-terrain-movement.md` §7. There is **no** resource-count
ceiling; an earlier note here claimed 1128 and was wrong.

### ⭐⭐ The live debugger — how to actually get one running (2026-09-21)

`debugger_*` MCP tools need a **standalone server** the pip bridge does not ship. `ghidra-mcp-bridge`
(installed into `…\Programs\Python\Python313`) contains only the client half,
`bridge_mcp_ghidra/debugger.py`, which POSTs to `GHIDRA_DEBUGGER_URL` (default
`http://127.0.0.1:8099`). The server lives in the **source repo** only:

```bash
git clone https://github.com/bethington/ghidra-mcp    # checked out at tag v6.0.0 to match the bridge
cd ghidra-mcp && uv sync --group debugger
WINDBG_DIR="C:\Windows\System32" uv run python -m debugger --port 8099
```

⚠ **`pybag` wants `dbgeng.dll` from the SDK Debugging Tools, which are NOT installed** — this box has
only `dbgcore/dbghelp/srcsrv/symsrv` in `Windows Kits\10\Debuggers\x64`. ⭐ No SDK install is needed:
`pybag.find_dbgdir()` honours **`WINDBG_DIR`**, and `C:\Windows\System32` has a full
`dbgeng/dbghelp/dbgmodel/dbgcore` set (10.0.26100.1). That one env var is the whole fix.

⚠⚠ **Do NOT use the bridge's `debugger_continue`** — it calls `go_nowait`, which only sets
`DEBUG_STATUS_GO` and never pumps `WaitForEvent`, so the target does not execute (its window stops
answering posted messages) and the session then dies with `SetExecutionStatus` → `E_ACCESSDENIED`.
⭐ Drive the server's HTTP API directly instead; it exposes far more than the MCP surfaces:
`POST /debugger/go_wait {"timeout_ms":N}` (the one that actually runs the target),
`POST /debugger/pass_exceptions {"enabled":false}` (**required** — with it true, first-chance AVs are
passed to the app's SEH and you never stop), `/debugger/interrupt`, `/debugger/sync_modules`,
`GET /debugger/stack?depth=N`, `/debugger/registers`, `/debugger/memory`.

⚠ Breakpoints via the MCP need a Ghidra↔runtime module map, and this project's Ghidra holds only
`AoWEPACK_original_backup.dpl` — a name that matches no runtime module, so the map is empty and
`debugger_set_breakpoint` fails for every address. Catching a fault needs no breakpoint; use
`pass_exceptions:false` + a `go_wait` loop while another thread drives the UI.

⭐ Every AoW module loads at its **preferred base** in AoWzEd (HSEPack `0x55600000`, AoWEPACK
`0x55700000`, EngineP `0x55500000`, vcl30 `0x41300000`, exe `0x00400000`), so static VAs are runtime
VAs and no delta arithmetic is needed. Stack frames come back symbolised.

⚠⚠ **Test a `.hss` change with `re_tools/hss_loadtest.py`, never by launching the exe.** AoWzEd stays
alive, windowed, at 40 MB when a mapset fails to load — a "is the process still up" check passed a
file the engine rejected outright. Only the CRC failure (`Exception('Invalid HSSET')`) makes the exe
vanish; everything else is a modal dialog. The load test drives `Developer > Open Mapset`
(WM_COMMAND 52) on a running editor and watches for the `TMessageForm`.

**`0x55820000`–`0x5583FFFF`** — later, more spread-out allocations, several exclusive reservations:

| VA | script | size | feature |
|---|---|---|---|
| `0x55820000` | `build_los_terrain.py` | 0x800 | strategic-map terrain LOS blocking (Earth/Rock) + fog-refcount rebuild |
| `0x55820800` | `build_caster_cost.py` | **exclusive** `0x55820800`–`0x55820FFF` | four bit-only hero abilities halving the initial casting cost of a spell family each |
| `0x55821000` | `build_dispelmagic5.py` | **exclusive** `0x55821000`–`0x558213FF` | Dispel Magic IV+V. **Relocated 2026-08-26** — see §6.3 for the full swallow/repair story, the single best worked example of the allocation discipline in this codebase. |
| `0x55822000` | `build_shipyard_income.py` | **exclusive**, a full page `0x55822000`–`0x55822FFF` | Shipyard gold income from contiguous adjacent water. Currently claimed — treat any older note calling this address free as stale. |
| `0x55823000` | `build_shield.py` | **exclusive**, a full page `0x55823000`–`0x55823FFF` | new passive ability Shield (ranged attacks only). `SHIELD_RANGED_CAVE = 0x558230D0` is chained into from `build_magebane.py` — §6.4. |
| `0x55824000` | `build_waterheal.py` | growth zone `0x55824000`–`0x55825200` (verified zero pre-install) | elemental terrain healing (grew out of an earlier "waterheal" feature; keeps that name/cave/hook) |
| `0x55826000` | `build_reformingflesh.py` | one blob `0x55826000`–`0x558260D0` (208 B) + `0x20` growth slack to `0x558260F0`, proved zero on every path | new passive ability Reforming Flesh (id `0xB1`): `cave_reg` + name literal + `cave_round` + **`cave_cost @0x558260B0`** (v3, 2026-09-10 — the level-up cost, hooked into `TAbility.ReadWrite @0x5574F0AA`, because a registration-time store of `[ability+0x14]` is zeroed by the `Ability.pfs` load). **Deliberately placed here, not at the `0x55824200` its own design spec originally named** — that address sits *inside* `build_waterheal.py`'s declared growth zone above; see §6.3 for why that would have been silently overwritten. |
| `0x55828000` | `build_panic_nomelee.py` | `0x55828000` + `0x55828040`, 40 B each (`CAVE_STRIDE = 0x40`) | panicked units cannot initiate melee — the AoWEPACK half (auto-resolve melee + touch); the other **four** caves are in AoWTCPCK.dpl from `0x00438300` through `0x004383C0` — see that module's table below for the slot-by-slot list and the next free address |
| `0x55829000` | `build_panic_cleardamage.py` | **exclusive** `0x55829000`–`0x558290FF` (58 B used), asserted zero-or-ours | Panicked `0x6C` removed by any damage that lands. Single hook on `TCombatObject.ExecuteDamage @0x55726C58`; the whole `0x100` is zeroed by `--undo` |
| `0x5582A000` | `build_terror_oncepercombat.py` | `0x5582A000`–`0x5582A200`, asserted zero-or-ours | each side casts Terror at most once per combat |
| `0x5582A200` | `build_gripofwinter.py` | `0x5582A200`–`0x5582A600`, asserted zero-or-ours | Freeze Water becomes Grip of Winter. **⚠ COUPLED**: `build_raiseterrain_ug_earth.py` owns the first 6 bytes of the `C_SHOW` cave at `0x5582A4E0` **in place** (`jmp 0x5583E140`, replacing a `cmp`/`jne` pair), a declared in-place rewrite like the `0x5580DB60` row above. `build_gripofwinter.py` byte-compares the whole 20-byte blob, so **while ug-earth is installed it can neither `--apply` nor `--undo`** — both abort before writing, nothing corrupts, and a dry run correctly reports `state: MIXED` with `C_SHOW *** FOREIGN ***`. ⭐ **`MIXED` here is the expected reading, not a defect.** Fixed order: **undo `build_raiseterrain_ug_earth.py` first.** Full write-up in `05-spells-added.md` ("Coupling with `build_raiseterrain_ug_earth.py`") and `09-terrain-movement.md` §3. |
| `0x5582B000` | `build_item_hpmv.py` | `0x5582B000`–`0x5582B200`, asserted zero-or-ours | items grant bonus HP and Movement, matching the existing ATK/DEF/DAM/RES grant |
| `0x5582C000` | `build_leadership_fearless.py` | `0x5582C000`–`0x5582C080`, asserted zero-or-ours | Leadership IV makes the whole stack count as Fearless |
| `0x5582D000` | `build_embrittle.py` | reservation incl. growth slack, `0x300` | new spell Embrittle + new passive Embrittled (id `0xB2`, double physical damage) |
| `0x5582E000` | `build_burning_sailing.py` | **exclusive** `0x5582E000`–`0x5582E07F` | sailing units and machines take multiplied Burning damage. Also owns the immediate operand at `0x557BA475` (an existing engine address, not a cave — the tick-rate constant for the DAM/HP gap-fix pass). |
| `0x5582F000` | `build_lightning_ignites.py` | **exclusive** `0x5582F000`–`0x5582F0FF` | lightning damage can set machines on fire |
| `0x55831000` | `build_turnundead_resroll.py` | reservation incl. growth slack, `0x100` | Turn Undead's stun/seize roll becomes an opposed Resistance check |
| `0x55832000` | `build_turnundead_evilcommand.py` | reservation incl. growth slack, `0x400` | an evil caster's Turn Undead seizes the target instead of damaging/stunning it |
| `0x55834000` | `build_ai_sitesearch.py` | **exclusive**, 8 KB (`0x55834000`–`0x55835FFF`; `cave_execai` then `cave_msgproc`, each 1 KB) | AI players path to, and search, exploration sites |
| `0x55838000` | `build_ai_itemloot.py` | `0x55838000`–`0x55838600` (6 sub-caves) | AI heroes pick up / equip / upgrade-swap / stash ground items; supersedes `build_ai_itempickup.py` and `build_ai_itemtarget.py` above |
| `0x5583E000` | `build_raiseterrain_ug_earth.py` | `C_UGDIRT` `0x5583E000` (320 B), `C_SHOWGATE` `0x5583E140` (64 B slot, 22 B used) | Raise Terrain works underground, producing temporary earth. `C_SHOWGATE` is what `0x5582A4E0` jumps to: it tests the restore-terrain byte `[eax+0x0E]` and the Earth marker `[eax+0x0F] == 7`, then either `jmp 0x5582A4E6` (Grip of Winter's own untouched 14-byte tail → vanilla `Show`) or `jmp 0x5582A4F1` (`ret 4`, draw nothing). See the `0x5582A200` row for the undo ordering this creates. |
| `0x55842000` | `build_minddecay_oos.py` | 256 B written; full page `0x55842000`–`0x55842FFF` verified zero and reserved | Mind Decay's to-hit roll made draw-count-invariant (§4.5's worked example) |
| `0x55844000` | `build_maplevel4.py` | **exclusive**, `0x400` (v2: 250 B used — `fillterr` `0x55844000`, `vis1` `..20`, `vis2` `..40`, `spellgate` `..60`, `placeguard` `..80`, `stormcast` `..A0`, `stormai` `..C0`, `birdsview` `..E0`) | Firmament map level (index 3): Sky terrain fill, surface-like vision, the global-target / storm / Bird's View spell gates, and the `TCave.PlaceHX` guard. Needs no globals — no PIC anchor, no absolute operand |
| `0x55846000` | `build_spellcast_herotier.py` | **exclusive**, `0x80` | the Spellcasting-level tier gate applies to units only, not heroes |
| `0x55847000` | `build_spellward_rescope.py` | **exclusive**, `0x100` (22 B used) | Astral Ward (ex Spell Ward) blocks only Town Gate (`0x26`) and Warp Party (`0x22`) — `cave_spellward`, hooked from `TSpell.CanActivate @0x557792E8` |
| `0x55848000` | `build_powerleech.py` | **exclusive**, `0x400` (379 B used — `cave_powerleech` `0x55848000`, `nodepower` `0x5584810F`) | Power Leech: the caster steals 25% of the power of every magic node owned by another player. Entered by retargeting the opening `call` of `GetNetPower @0x5577CEC4`. **PIC anchored on a function**, not on a data global — `sub ecx, 0x77C50` leaves EDI = runtime `TPowerNode.GetPower @0x557D03C8`, so the node test is `cmp [edx+0x1F8], edi` and the map (`edi + 0x129C78`) and `TPlayerStructurePowerSource.Power` (`edi − 0x6E874`) are small offsets. **No `0x55xxxxxx` operand in the cave.** |
| `0x55849000` | `combatunitguard.py` (**a module, not a build script**) | **exclusive**, `0x100` (98 B used — `guard_unit` `0x55849000`, `guard_hero` `0x55849040`) | The shared "is this combat object really a `TCombatUnit`?" guard, added 2026-09-11 after a wall-target AV. `guard_unit(EAX=combat obj) -> EAX = [obj+0x4C]` or 0; `guard_hero(EAX=combat obj) -> AL = target is a THero`. **⚠ COUPLED, by design**: `build_assassin.py` and `build_magebane.py` both install the identical blob (verify-before-write accepts zero-or-ours from either) and both call `combatunitguard.undo_if_unused()`, which zeroes it **only when no caller outside the undoing script's own caves remains**. Clobbers EAX + flags only; PIC via a `call $+5`/`pop` anchor to the classref cells `0x55715A54` (TCombatUnit) and `0x55711FAC` (THero) |
| `0x5584A000` | `build_leadership_others.py` (🔨 APPLIED, UNTESTED 2026-09-16) | **exclusive**, `0x400` (518 B used — `cave_blevel` `0x5584A000` 28 B, `cave_pass2` `0x5584A040` 226 B, `cave_lname` `0x5584A180` 264 B incl. the four `" (+<roman> received)"` AnsiStrings and their pointer table at `0x5584A214`) | Leadership buffs only the OTHER units in the party, and the card splits own level from received level. Hooks `0x557661FC` / `0x55766210` (the two bonus getters, 5 B `call`), `0x5578D128` (`TArmy.UpdateFormation` pass 2, 6 B `jmp`, resuming at the shared exit `0x5578D186` — only the first 6 bytes may be displaced, `0x5578D162` carries the region's sole `.reloc` entry) and the VMT slot `0x55722060` (`GetName`, itself `.reloc`-covered — the value is repointed, the entry kept). **⚠ COUPLED**: `cave_lname` reaches `build_leadership4.py`'s `cave_lsname` through `VMT+0x10c` rather than by address, so the two compose; and `build_leadership_fearless.py` depends on `TLeadershipAbility.GetLevel` still returning `max(own, borrowed)`, which is why the original author's own-only `GetLevel` change was deliberately not ported. PIC: one `call $+5`/`pop edi` anchor for `0x558FA044` in `cave_pass2`, one `pop ebp` anchor for the literal table in `cave_lname`. |
| `0x5584B000` | `build_hero_turn1_upgrade.py` (🔨 APPLIED, UNTESTED 2026-09-22 v2; **v3** 2026-09-24) | **exclusive**, `0x100` (was `0x80`; 129 B used — `C_TURN1` `0x5584B000`) | A hero holding unspent skill points is offered them. Entered by **retargeting the `call rel32`** at `THero.NewTurn+0x1B @0x55787FE7` (was `ValidateHeroUpgrade @0x55787D54`); the cave creates the level-cache lag when `GetSkillPoints() > 0` and **tail-jumps** to the original. Second site `0x55786CB3` is 10× `nop` (vanilla's day-1 confiscation, disarmed). v3 adds guard 4: no lag for a PBEM human's leader on day 1 (`pbemday1.py` predicate; map via a `call $+5` anchor), re-tuned in place over v2. **⚠ COUPLED** to `build_pbem_leadersetup.py`, which accepts this cave only fully v3 or fully absent. ⚠ **v1 hooked `0x55786CB3` instead and never executed** — see `01-combat-maths.md` §5 |
| `0x5584C000` | `build_pbem_leadersetup.py` (stage 1 ✅ 2026-09-24; stage 2 🔨 APPLIED, UNTESTED 2026-09-24) | **exclusive**, `0x400` (was `0x100`; 649 B used), asserted zero-or-ours | PBEM turn-1 leader window. Fixed entries: `C_RAISE 0x5584C000` (124 B; 5-byte E9 over `0x55756B94`, raises `TPlayerMagicEventLog` mode 3; VMT derived PIC), `C_GATE 0x5584C100` (71 B; E9 + 17 nop over `0x5577CC5C`, defers the day-1 grant), `C_APPLY 0x5584C180` (265 B; called from the exe through the rebase delta `[0x45DF7C] − 0x558FA040` — the exe holds this constant, so it must not move). Second site `0x5577C3FF` (one rel8 byte, `4B→47`). **⚠ COUPLED**: `C_APPLY` calls `build_tierresearch_dll.py`'s `cave_day1` v2 at `0x5580EE30`. Exe half is the `0x0062C000` row in §6.2. Full record `07-ui.md` §10.5–10.6. **Current high-water mark** |

⚠ **`build_spellcast_herotier.py --apply` would abort today.** Its `ZONE_END` is `0x55848000`
(line 125) and it asserts `cave_end..ZONE_END` is zero, but `build_spellward_rescope.py`'s cave
now sits at `0x55847000` inside that window. Lower its `ZONE_END` to `0x55847000` when you next
touch that script. Found 2026-09-07 during the Power Leech scoping; the abort is safe, not
corrupting, and `build_powerleech.py` does not make it worse — its cave starts at exactly
`0x55848000`, which is where both neighbours' zero-asserts stop.

Free above `0x5584C400`, all the way to the `0x558E7918` CODE ceiling. (`0x55844000`, `0x55848000`,
`0x55849000`, `0x5584A000`, `0x5584B000` and `0x5584C000` are now claimed — see the rows above. `0x55848400..0x55849000` is the gap between
Power Leech's reservation ceiling and the guard, and is free but small.)

### 6.2 Other binaries

**AoWz.exe / AoWzCompat.exe** (base `0x00400000`, lockstep — see §9; identical addresses are valid
for both, since AoWzCompat is a 1-byte build-number edit of the game exe.  ⚠ The only pair to patch is
`Ziggurat\AoWz.exe` / `Ziggurat\AoWzCompat.exe`; they run from `Ziggurat\` and resolve their imports
there, so they are the live files and there is no derived copy and no propagation step. The root holds
only the vanilla `AoW.exe` / `AoWCompat.exe`, which are never targets. **`build_overlay.py` and the
root `AoWz.exe`/`AoWzCompat.exe` it used to derive were retired and deleted 2026-09-10** — anything
telling you to run it after an exe patch is stale.):

| VA | script | feature |
|---|---|---|
| `0x0060C0A8` | `build_spellcast_book_exe.py` (original), **rewritten in place and extended** by `build_scroll_spellbook.py` | `cave_bookfilter` — hides too-high-tier spells from the casting book. **⚠ COUPLED, non-trivially** — full revert-order story in §6.5. |
| `0x00610720` | `build_bltprobe_exe.py` | diagnostic: captures the original exception behind "Blt Error" |
| `0x00628000`–`0x00629FFF` | `build_heroskill_race.py` | **exclusive**, `0x2000` — the per-race hero level-up offer gate. `RGT1` magic at `0x00628000`, code `0x00628010` (201 B), the two **fixed** tail-jump slots at `0x00628200`/`0x00628205`, and a 16×256 table at `0x00629000` ending exactly at the squatter floor below. ⚠⚠ **COUPLED to `build_herodlg_columns.py`, which would otherwise unlink it**: its hook sits *inside* `cave_fill`, which that script regenerates on every `--apply`. Both scripts locate the site by pattern (never by constant) and the columns script re-chains via `relink_bytes()`; full story in `02-abilities-modded.md` Feature 1. Also the project's first **P4 derived-hash** site (`rngstd.fmix32` at `0x006280A9`) |
| `0x0062A000`–`0x0062A3FF` | `build_skylevel_ui.py` | **v3** (caption "Firmament", code base `0x0062A040`, 512 B used) — the AoWz.exe/AoWzCompat.exe half of the Firmament map level: the World Map level strip (`TSWindow.ScannerTab`) and the level-navigation UI. DLL half is `build_maplevel4.py`, cave `0x55844000`. ✅ **Guard is already in place**: `build_herodlg_columns.py` sets `SQUATTER_FLOOR` and asserts it in `apply_to`. That floor moved `0x0062A000` → **`0x00628000`** on 2026-09-09 when the entry above took the top 8 KB; the columns blob tops out at **`0x00624200`** (2026-09-10: 8 rows/column, the per-column scrollbar sync in `cave_setfmax`, and the derive-don't-cache `cave_activelist` of `07-ui.md` §2.4a), leaving **15,872 verified-zero bytes at `0x00624200..0x00628000`** for future exe caves (`0x3E00`) |
| `0x0062D000` | `build_unitwin_ability.py` | lets a hero use an item-granted activatable ability from the unit window |
| `0x0062D020` | `build_savedate_format.py` | ISO date in the Load/Save dialog (".hcol" section, after the entry above) |
| `0x0062B000`–`0x0062B0FF` | `build_taskbar_icon.py` | **exclusive**, `0x100` (96 B used) — sets `WM_SETICON` ICON_BIG + ICON_SMALL on the `TApplication` owner window so the taskbar button stops showing the grey placeholder. Reached by **retargeting the existing `call Forms.TApplication.Initialize` at `0x004599DE`** (4 bytes of operand, nothing displaced); the cave tail-jumps to the real thunk `0x00401754`. Borrows `user32!LoadIconA`/`SendMessageA` and the `'MAINICON'` literal out of **vcl30.dpl** via the rebase delta `[0x0045D56C] − 0x4133C0F8` (that IAT slot is `Forms.TApplication.GetExeName`, preferred VA `0x4133C0F8`) — AoWz.exe imports exactly one user32 function (UnionRect) and neither of those two. Editor half is the `.vgo` row below |
| `0x00630000`–`0x00632FFF` | `build_itembanner_hpmv.py` | **exclusive**, its own new RWX section **`.ibnr`** (`0x3000`, appended after `.pyar`; SizeOfImage `0x230000` → `0x233000`). Layout: the grown `TITEMBANNER` DFM at `0x00630000` (9469 B), the relocated 17-entry field table at `0x00632500`, `cave_hpmv` at `0x00632700` (328 B) and `cave_clamp` at `0x00632848` (40 B) — top of blob `0x00632870`, leaving `0x00632870..0x00633000` = **1936 B** spare (measured all-zero, file-backed at file `0x22CA70..0x22D200`). ⚠ **`--apply` zeroes the whole `0x3000` before writing**, so a squatter in that tail is wiped by the next re-apply exactly as `.hcol`'s below-floor squatters would be — take one of the three `.hcol` runs listed below the table instead unless you also add a floor here. ⚠⚠ **This section consumed the LAST free section-header slot in the exe**: the table starts at file `0x1F8` and SizeOfHeaders is `0x400`, so 13 headers end at exactly `0x400`. No 14th section can be added — squat in a zero tail, or `--undo` this first (its `--undo` removes the section and gives the slot back). ⚠ Its relocated field table carries **one absolute with no `.reloc` entry** — the class-table VA `0x00406AA0` at `0x00632502`, whose original at `0x0040697A` did have a HIGHLOW entry. That is precedent, not a defect: `build_herodlg_columns.py` relocates `THeroUpgradeDlg`'s table with the byte-identical shape and is CONFIRMED WORKING, and AoWz.exe is `RELOCS_STRIPPED=0 / DYNAMIC_BASE=0` (DllCharacteristics `0x0000`), so the image always loads at `0x00400000`. **`build_relocfix.py` detects only STALE relocations, never a MISSING one**, so a clean audit says nothing either way. Full record in `07-ui.md` §9 |
| `0x0062D100`–`0x0062D2FF` | `build_powerleech_ui.py` | **exclusive**, `0x200` (0xA8 B of data + 107 B of code at `0x0062D1A8`) — the Power Leech income row in `TMagicWin` tab 4, hooked from `0x0042CFD9` (7 B). Also `.hcol`, the next clear `0x100`-aligned slot above `build_savedate_format.py`'s cave (last non-zero `0x0062D07A`); the script asserts `0x0062D0A0..0x0062DFFF` is zero outside its own span. The data half is two Delphi literal AnsiStrings plus a **fake object + 24-slot fake VMT of `xor eax,eax ; ret`** — the name list's `AddObject` object may not be nil, because `PowerSourceListDoubleClick @0x0042D944` and `PowerValueListMouseDown @0x0042D988` deref it unchecked. DLL half is `build_powerleech.py`, cave `0x55848000` |
| `0x0062C000`–`0x0062C3FF` | `build_pbem_leadersetup.py` (stage 1 ✅ 2026-09-24; stage 2 🔨 APPLIED, UNTESTED 2026-09-24) | **exclusive**, `0x400` (944 B used), asserted zero-or-ours, inside the `.hcol` run `0x0062B100..0x0062D000`. Globals `G_EVENT 0x0062C000`, `G_CODE ..04`, `G_DATA ..08`, `G_MODAL ..0C` (byte); `.hcol` is RWX (`0xE0000060`, asserted), so `--undo` is one contiguous zero-fill. `C_SHOW 0x0062C010` (315 B, fixed: the dispatch hook targets it), `C_DONE 0x0062C150` (210 B, calls the DLL's `C_APPLY`), `C_PANEL 0x0062C230` (29 B), `C_OFFER 0x0062C250` (234 B, the P4 offer roll — `rng_audit.py --hash` lists it at `0x0062C301`), panel table `0x0062C340`, `G_VIS 0x0062C390`, `G_PLAYER 0x0062C3A0`. Sites: the rel32 of the `jmp 0x44F51E` at `0x0044F183` (nothing displaced) and a 6-byte E9 over `0x004161C9` in `TLeaderSetupWin`'s available-ability loop. Reads `build_heroskill_race.py`'s table at `0x00629000`. DLL half is the `0x5584C000` row. Full record `07-ui.md` §10.5–10.6 |

⚠⚠ **`.hcol` below `0x00628000` is NOT allocatable — `build_herodlg_columns.py` zeroes it on every
`--apply`.** Its line 1547 is `exe.wr(SEC_VA, b"\0" * (SQUATTER_FLOOR - SEC_VA))`, i.e. it wipes
`0x00612000..0x00628000` wholesale before laying its blob back down. The **15,872 free bytes at
`0x00624200..0x00628000`** the row above advertises are inside that wipe: anything parked there
verifies clean, survives until the next columns re-apply, and then vanishes with no diagnostic. The
genuinely free, unpoliced space is **four disjoint runs**, re-measured byte-by-byte on the live exe
2026-09-13 (the earlier "`0x0062A400..0x0062D000`, all-zero" was wrong — `build_taskbar_icon.py`'s
cave is inside it, 85 non-zero bytes in 8 runs spanning `0x0062B000..0x0062B05F`, and that script
declares the whole `0x100` exclusive):

| run | size | note |
|---|---|---|
| `0x0062A400..0x0062B000` | 3072 B | above `build_skylevel_ui.py`, below the taskbar cave |
| `0x0062B100..0x0062C000` | 3840 B | above `build_taskbar_icon.py`'s exclusive `0x0062B000..0x0062B0FF` |
| `0x0062C400..0x0062D000` | 3072 B | above `build_pbem_leadersetup.py`'s exclusive `0x0062C000..0x0062C3FF` (claimed 2026-09-23 out of the former 7936 B run) |
| `0x0062D213..0x0062E000` | 3565 B | `.hcol`'s real tail, above `build_powerleech_ui.py`'s last byte `0x0062D212` — **not** everything from `0x0062D000`, which is that script's own cave |

`.syd` / `.pyar` are both whole-section blobs their owners rewrite and byte-compare — neither is
slack. `.ibnr`'s tail **`0x00632870..0x00633000` (1936 B, measured all-zero)** is the fourth run, but
it is inside another script's section: see the `.ibnr` row above before taking it.

⚠⚠ **AoWz.exe HAS NO SPARE SECTION-HEADER SLOT since 2026-09-13.** `build_itembanner_hpmv.py`'s
`.ibnr` is the 13th section and the header table now ends at exactly `0x400` = SizeOfHeaders. A 14th
header would overwrite CODE's raw data at file `0x400`, so **a new exe feature cannot add a section**:
take space from the free `.hcol` runs listed above, from `.ibnr`'s own tail (`0x00632844..0x00633000`), or run
`build_itembanner_hpmv.py --undo` first — its undo removes the section and returns the slot. Both
`add_section()` implementations (here and in `build_herodlg_columns.py`) assert the bound rather than
corrupting the image, so the failure is loud.

**AoWDevEd.exe / AoWzEd.exe** (base `0x00400000` — a *different* binary from AoWz.exe despite the
identical preferred base; these two numeric spaces are never comparable to each other).
⚠⚠ **Unlike the game exes, the editor DOES have a propagation step**: every editor script patches
`Ziggurat\AoWDevEd.exe` and `build_zigeditor.py --apply` copies it wholesale to the live
`Ziggurat\AoWzEd.exe`. Skip that second step and the patch verifies clean against a binary nobody
runs. It bites `--undo` just as hard as `--apply`. ⚠ `AoWzEd.exe` is **not** a byte copy — measured
2026-09-11 it differs from `AoWDevEd.exe` by 4396 bytes in 1224 runs, all of them inside `.rsrc` (the
purple-dragon icon `build_zigeditor.py` swaps in); same file size, every code and cave byte equal. So
"is the feature in the live editor?" is answered by comparing the cave region and the hook sites, not
by hashing the file. ⚠ A third copy sits at the game **root** — `<root>\AoWDevEd.exe`, sha256
`7288edc1…`, carrying all seven appended sections. It is **not** byte-identical to
`Ziggurat\AoWDevEd.exe` and has not been since 2026-09-11: it diverges at `0x3D0E1` and keeps a stale
relocation the Ziggurat copy no longer has. Every editor feature applied since then is missing from
it, and **nothing is going to fix that** — no script maintains the copy. Treat a root-vs-Ziggurat hash
difference as expected, never as evidence that an editor patch failed. It is not in the GOG hashdb, so
`mod_manifest.py` reports `CHANGED(0)` honestly while the root's editor is in fact fully modded.
⚠ **No hash is quoted for `Ziggurat\AoWDevEd.exe` on purpose** — it changes on every editor `--apply`,
so any value written here is stale within one feature and reads as a discrepancy. The root's hash is
quotable only because nothing maintains that file. Answer "is this feature in the editor?" by checking
the cave region and the hook sites:

Editor-only exe caves are placed via computed `base_va = 0x400000 + newva` in
`build_party_random.py`, `build_editor_timerres.py`, `build_validation_goto.py` and
`build_deved_terrainpal.py` — each computes its own landing spot rather than declaring a fixed
constant, so there is no fixed-address table to give here; consult each script directly before
adding new editor-only exe caves.

Fixed editor-exe allocations that DO exist (2026-09-06):

| VA range | binary | owner script | contents |
|---|---|---|---|
| `0x00592080..0x005921FF` | `AoWDevEd.exe` (`.tres` page slack) | `build_deved_levelnav.py` | ORDER/RORDER + 4 code blocks (236 B used) — ⚠ shares `.tres` with `build_editor_timerres.py`, which owns `0x00592000..0x00592075`; `build_editor_timerres.py --apply` over an installed state would truncate the file at `.tres`'s raw offset — only its own "`.tres` is not the last section" assert protects `.nmg` and this cave |
| `0x00593000..0x00598DD6` | `AoWDevEd.exe` (own section `.nmg`, rva `0x193000`, 24022 of **35840** B) | `build_deved_newmapgen.py` | the **largest editor-exe allocation there is**: OK cave, `GenChanged`, `GenInit`, `GenInfo`, then a 0x2000-based data area, then the relocated method/class/field tables and the rebuilt 9078-byte DFM. ⚠ It is the LAST section and its raw data runs to end-of-file, which is what lets a rebuilt cave regrow it in place; `--undo` leaves it behind as dead data so a re-apply reuses it. Everything in it moves on every rebuild — read addresses from the binary, never from a note. ⚠⚠ It **no longer owns the whole section**: `build_deved_itemhpmv.py` holds the cave at `0x00599000..0x005993FF` **and a live 9958-byte resource at `0x00599400`** in the page slack above. A rebuild here zeroes **both** — the cave silently, the resource not silently at all, because the directory entry still points at rva `0x199400` and **Item Properties then fails to open with a `TReader` error**. Its `rawsz = max(exist_rawsz, …)` keeps SizeOfRawData at `0x8C00`, so the file length and SizeOfImage survive and only VirtualSize drops back to `0x5DD6`. `build_deved_itemhpmv.py` recognises that exact asymmetry as its DAMAGED state and repairs it in place. ⚠ Latent, not live: this script's `--apply` refuses while applied, and its `--undo` needs `Ziggurat\backups\AoWDevEd.exe.pre-newmapgen`, which does not exist. Its `--undo` is in any case surgical and leaves `.nmg` alone |
| `0x004E0000..0x004E051F` | `AoWDevEd.exe` (own section `.dlgd`, rva `0xE0000`) | `build_dlgdirs.py` | the exe half of the dialog-directory feature: 8 hook wrappers + `ensure_ini` + `getdelta` in the raw `0x400` (718 B used, 306 spare), then `PATHBUF` at `0x004E0400` in page slack (VirtualSize `0x520`). ⚠ **v3 (2026-09-11) left this half byte-identical to v2** — the engine-data-root fallback is `Set`-key-only and there is no Set dialog in the exe — so `0x520` here is correct and is *not* evidence of a stale install. ⚠ Free page slack is now `0x004E0524..0x004E0FFF` (2780 B) — `build_deved_gamesettings_tab.py` took the first dword. ⚠⚠ **Giving `AoWDevEd.exe` an `engfb` entry would collide with it**: v3's `DIRBUF_OFF = PATHBUF_OFF + PATHBUF_SIZE = 0x520` is exactly that dword |
| `0x004DF000..0x004DF17F` | `AoWEd.exe` (new section `.lvn`) | `build_deved_levelnav.py` | same layout; `+0x100` holds the 40 displaced section-header bytes |
| `0x00590180..0x005901FF` | `AoWDevEd.exe` (`.vgo` tail) | `build_taskbar_icon.py` | **exclusive**, `0x80` (96 B used) — the editor half of the taskbar icon; same cave body as AoWz.exe `0x0062B000`, only four immediates differ (`app 0x00432224`, `GetExeName 0x00432178`, `GetModuleHandleA 0x00432160`, thunk `0x00401328`). Hook is the `call Forms.TApplication.Initialize` at `0x0042EE52`, operand-only. `build_validation_goto.py` owns `0x00590000..0x0059016C` below it and is a no-op once `.vgo` exists, so it will not wipe this. ⚠ `.vgo` had `SizeOfRawData 0x200` but `VirtualSize 0x16D`; `--apply` raises VirtualSize to `0x200` (and `--undo` puts it back) so the cave is inside the declared section rather than relying on loader slack behaviour. SizeOfImage and file length are unchanged |
| `0x0058E3A0..0x0058F279` | `AoWDevEd.exe` (`.ctp` tail, after the DFM) | `build_deved_heroprune.py` | Developer > Delete Unused Heroes: `PruneFreeHeroesClick` (459 B, `ret` at `0x0058E56A`, then 5 NOP pad) + 92 B of literals + `TMainForm`'s method table relocated a **second** time (134 → 135 entries, 3246 B, VMT−0x28 repointed `0x0052E060 → 0x0058E5CC`). 3906 of the 4296 free tail bytes used, 390 left — **of which the entry below now takes 384**. Grew the live DFM in place `0x5F644 → 0x5F6A0`; `.ctp` VirtualSize `0x61350 → 0x61400`, **SizeOfRawData untouched** — `.ctp`'s raw data ends at file `0x18A200`, which is exactly `.vgo`'s `PointerToRawData`, so the file length cannot change. ⚠ **COUPLED to `build_deved_terrainpal.py`** — see the hazard below |
| `0x0058F280..0x0058F3FF` | `AoWDevEd.exe` (`.ctp` tail, above heroprune) | `build_deved_gamesettings_tab.py` | **exclusive**, 384 B reserved / 216 used (199 B code + 1 pad + a 16 B `'Game'` AnsiString literal at `0x0058F348`, chars at `0x0058F350`), 168 spare. Four cave entries — `cave_build 0x0058F280`, `cave_commit 0x0058F302`, `cave_free 0x0058F318`, `cave_menu 0x0058F333` — reached by **retargeting four existing `call rel32` operands** (`0x004230E8`, `0x00423730`, `0x0042315F`, `0x004284B2`), 4 bytes each, nothing displaced. Its one mutable dword cannot live here (`.ctp` is `0x60000020`, no WRITE) and sits at `G_GSDLG 0x004E0520` in `.dlgd` page slack instead. ⚠⚠ **`build_deved_heroprune.py` zeroes `.ctp`'s tail out to file `0x18A200` on BOTH `--apply` and `--undo`, and will destroy this cave silently** — re-apply behind either |
| `0x00599000..0x005993FF` | `AoWDevEd.exe` (`.nmg` page slack, above newmapgen's body) | `build_deved_itemhpmv.py` | **exclusive**, 1024 B reserved / 644 used / 380 spare — Item Properties' Hit Points + Movement spinners. 12 B of globals (`G_FORM`/`G_HPSPIN`/`G_MVSPIN`) at `0x00599000`, two AnsiString literals at `0x00599010`, 580 B of code at `0x00599040` (`cave_change` `0x00599040`, `cave_load` `0x00599093`, `cave_enter` `0x005990C5`), reached by **retargeting three existing `call rel32` operands** (`0x004137DC`, `0x0041389F`, `0x004133AE`), 4 bytes each, nothing displaced. `.nmg` is `0xE0000060` (RWX), so the mutable globals live inside the cave span and `--undo` is one contiguous zero-fill. Reservation was 768 B until 2026-09-13; it was raised to 1024 so the cave can never meet the relocated resource in the row below |
| `0x0052D640..0x0052D69F` | `AoWDevEd.exe` (`.mtb` page slack) | `build_deved_listarrows.py` | **exclusive**, 96 B reserved / 57 used — the arrow-key gate on `TMainForm`'s `Application.OnMessage` filter, so UP/DOWN reach the Abilities and Spells listboxes. Hook `0x0042812F` (5 B `3b 70 5c 75 23`); the cave compares `TMsg.hwnd` against `[TMainForm+0x4A0]`/`[+0x4DC]` `+0xCC` (`TWinControl.FHandle`) and tail-jumps to vanilla's own `0x00428134` (swallow) or `0x00428157` (pass). ⚠ **Do not hook `0x00428128`** — the type-3 `.reloc` at `0x00428129` would be stranded mid-rel32. `.mtb` is `build_editor_toolbar.py`'s toolbar-bitmap section (VirtualSize `0x4C63B`, SizeOfRawData `0x4C800` → **453 B of slack at `0x0052D63B`**); `--apply` raises VirtualSize to `0x4C800` and Characteristics `0x40000040 → 0x60000040` (adds MEM_EXECUTE — the section is data-only otherwise), `--undo` restores both. No collision: `.mtb` rva `0xE1000 + 0x4C800 = 0x12D800` and `.ctp` starts at `0x12E000`; SizeOfImage and file length unchanged. Remaining free `.mtb` slack: `0x0052D6A0..0x0052D800` = 352 B, plus the 5 B below the cave. ⚠ `build_editor_toolbar.py` owns the section but is a no-op once `.mtb` exists, so it will not wipe this |
| `0x00599400..0x0059BAE6` | `AoWDevEd.exe` (`.nmg`, above the cave) | `build_deved_itemhpmv.py` | **the relocated `TITEMEDITFORM` DFM**, 9958 B — data, not code. Item Properties grew two `TImage` nodes (`Image13`/`Image14`, the HP and MV stat icons, copied verbatim out of `THEROEDITFORM`) and could not grow in place, so the resource **directory entry** at file `0x000434E0` was repointed here from rva `0x6D1A8`. ⚠ **This is the entry that grew `.nmg`**: VirtualSize **and** SizeOfRawData `0x6E00 -> 0x8C00`, SizeOfImage `0x0019A000 -> 0x0019C000` (RVA space — *not* `0x59C000`), file length `0x00192200 -> 0x00194000`. **Real free `.nmg` slack is now `0x0059BAE6..0x0059BC00` = 282 B**, not the 2816 B this table used to claim. The `.rsrc` original at file `0x000697A8` is left in place as a dead master — see the dead-master register below |

⚠ **`AoWDevEd.exe` cannot take another PE section**: `e_lfanew` is `0x100` and its 13 headers end at exactly file `0x400`, where CODE's raw data begins. Future AoWDevEd caves go into page slack of an existing section.

### Dead DFM masters in `AoWDevEd.exe` — four of them, and the trap they set

Relocating a form's RCDATA leaves the original bytes in place, live-looking and unreferenced: only the resource directory's `(OffsetToData, Size)` moved. `AoWDevEd.exe` now carries **four dead masters against three live relocated copies** (inventory measured 2026-09-13):

| form | dead master | live copy | relocated by |
|---|---|---|---|
| `TMAINFORM` | file `0x074AFC` (`.rsrc`) **and** `0x0DC600` (`.mtb`) | `.ctp` | `build_editor_toolbar.py` then `build_deved_terrainpal.py` — two relocations, so two masters |
| `TNEWMAPDLG` | file `0x0CE7D4` | `.nmg` rva `0x196A60` | `build_deved_newmapgen.py` |
| `TITEMEDITFORM` | file `0x0697A8` | `.nmg` rva `0x199400` | `build_deved_itemhpmv.py` |

**Keeping them is correct.** `build_deved_itemhpmv.py`'s `build_new_dfm()` re-derives the live copy from its master on every `--apply`; zeroing the master would break idempotency and force `--undo` to carry 7487 literal bytes instead of an 8-byte directory rewrite.

⚠⚠ **The sharp edge: a script that correctly walks the resource directory edits the LIVE copy, and the owning script's next `--apply` silently reverts it.** The verify path prints `DRY RUN`, not a diagnosis — nothing compares master against copy. **A future edit to a relocated form must go into the master, or into the owning script.**

⚠ **And a whole-file scanner sees both copies.** Which is which, measured on `AoWDevEd.exe`:

- **Both copies** — `build_editor_spinners.py`. Whole-file `re.finditer(rb"\x08MaxValue\x02")` with no notion of the resource directory. It composes *by luck*, patching both to the same value; since the TITEMEDITFORM relocation it reports **18** sites rather than 14, the four extra at `0x19382B`/`0x1938AC`/`0x193931`/`0x1939B5`, all `AT TARGET`. A future scanner that asserts a site **count** will trip.
- **Live copy only** — `build_editor_toolbar.py`, `build_deved_terrainpal.py`, `build_deved_toolbar_trim.py`, `build_deved_heroprune.py`, `build_deved_newmapgen.py`. All walk the directory.
- **Neither** — `build_deved_gamesettings_tab.py`, `build_useitems.py`.

⚠ **Forward hazard, `.ctp`: terrainpal is now INERT, and un-inerting it is what costs you.** `build_deved_terrainpal.py --apply` over an installed state is a **safe no-op** — line 389 tests for the `.ctp` section and prints `already patched (.ctp section present) - idempotent no-op` before touching the DFM, the method table or the section (`build_editor_toolbar.py` line 333 has the identical guard on `.mtb`). The consequence is that a future terrain-palette change requires **deleting `.ctp` first**, and that deletion destroys `build_deved_heroprune.py`, `build_deved_toolbar_trim.py` *and* `build_deved_gamesettings_tab.py`, all three of which live in the section terrainpal owns. Apply order is **terrainpal → toolbar_trim → heroprune → gamesettings_tab**, and all four must be re-applied in that order behind any `.ctp` rebuild.

⚠⚠ **`build_deved_heroprune.py` silently destroys `build_deved_gamesettings_tab.py`'s cave — on `--apply` as well as `--undo`.** Its `strip()` zeroes `.ctp`'s tail from `dfm_off + ORIG_DFM_SIZE` = file `0x189138` out to `ctp_raw + ctp_rsz` = file `0x18A200`; the gamesettings cave at `0x0058F280..0x0058F3FF` (file `0x18A080..0x18A1FF`) is inside that range. `--undo` runs `strip()` and drops VirtualSize back to `0x61350`; **`--apply` over an already-applied file runs the same `strip()` first** (`already applied -- rebuilding IN PLACE (strip, then lay down again)`), so both wipe it. Two guards that look like they would catch this do not: `build()`'s "the `.ctp` tail is not all zero" test passes *because `strip()` just erased the evidence*, and the `bytes(d) == before` short-circuit does not fire because the file genuinely changed. The result is four `call rel32`s pointing at zeroed memory, one of them (`cave_menu 0x0058F333`) inside `TMainForm.FormCreate` — so `AoWzEd.exe` AVs at **startup**, not on first use. Undoing or re-applying heroprune therefore means re-running `build_deved_gamesettings_tab.py --apply` and `build_zigeditor.py --apply` straight afterwards.

⭐ **The general lesson: a script that zeroes a whole section tail is a landlord, not a tenant.** `strip()`-then-rebuild is the right shape for a single owner and silently hostile to anything allocated above it, because the "is my slack still clean?" guard runs *after* the wipe. When allocating above such a script, put the warning in **that script's** output, not only in your own — the person who trips it is running the other one. Done here: `build_deved_heroprune.py` now names the cave and the recovery in its docstring and in both its `--apply` and `--undo` output.

⚠ **`build_deved_toolbar_trim.py --undo` is refused while heroprune is applied.** Its line 483 computes `already = (new_blob == blob)` and line 494 declines when that is false; heroprune's 92-byte menu node makes the live DFM `0x5F6A0` rather than the trimmed `0x5F644`. Fail-safe rather than a defect — toolbar_trim's snapshot is `0x6065C` bytes and restoring it would write straight through heroprune's cave and the relocated method table at `0x58E3A0..0x58F27A`. **Undo order: heroprune first, then toolbar_trim.**

⚠ **`.ctp` now holds TWO dead `TMainForm` method tables.** `0x0052E060..0x0052ECF3` (134 entries, 3219 B) is terrainpal's, live until heroprune repointed VMT−0x28 past it; `heroprune --undo` points back at it and relies on it still being byte-intact, so **do not reclaim it as cave space.** The genuinely reclaimable dead run is the pre-terrainpal table inside `.mtb`.

**AoWTCPCK.dpl** (preferred base `0x00400000`, rebases like the other `.dpl`s — same PIC discipline
as AoWEPACK applies):

| VA | script | feature |
|---|---|---|
| `0x00438100` | `build_spellcast_tcpck.py` | manual/tactical combat cast gate (Unit Spellcasting Phase 1b) — inside a 191 KB zero run at `0x438080` |
| `0x00438200` | `build_facing_retal.py` | deferred-retaliation facing (✅ confirmed working in-game 2026-08-27, then **reverted by choice**, re-appliable) |
| `0x00438300` | `build_panic_nomelee.py` (AoWTCPCK.dpl half) | Panicked units cannot initiate melee, still retaliate — `CAVE_BASE["AoWTCPCK.dpl"]`, inside the same 191 KB free run as the entry above. **Four** slots at `CAVE_STRIDE = 0x40`: `0x00438300` `cursor`, `0x00438340` `ai`, `0x00438380` `freeswing`, `0x004383C0` `meleemove` (added 2026-09-12). Next free slot `0x00438400`. ⚠ Slot index is the site's position **within its file** in `SITES`, so that list is append-only — inserting renumbers the installed caves and every site reports `state=foreign` |

**aowInt.dpl** (preferred base `0x59800000`):

| VA | script | feature |
|---|---|---|
| `0x59822800` | `build_glowboost.py` | doubles the spellbook hover-glow intensity |
| `0x59823000` | `build_bltprobe.py` | diagnostic: captures what fails when aowInt raises "Blt Error" |

**Network.dpl** (preferred base `0x55800000`, rebases — same PIC discipline as AoWEPACK). It has
**exactly one cave, and no more**: CODE is `va=0x1000 raw=0x400 rs=0x5400 vs=0x5210`, so the only
free space is the `0x1F0`-byte tail between VirtualSize and SizeOfRawData. It is file-backed and
executable, and it ends exactly at CODE's raw end.

| VA | script | feature |
|---|---|---|
| `0x55806210`–`0x558063FF` | `build_te_exception_detail.py` | **exclusive**, `0x1F0` (150 B used). ⚠⚠ **DIAGNOSTIC — `--undo` before cutting a release.** Makes the swallowed turn-event exception print its module + offset; hook is the `call ShowMessage` at `0x55803DD2`. §3a |

⚠ **That `0x1F0` is the whole CODE budget — there is no second code cave in Network.dpl.** The full
section map, for anyone who needs to allocate here next (SectionAlignment `0x1000`, FileAlignment
`0x200`):

| section | RVA | VirtualSize | raw | SizeOfRawData | flags | what is left |
|---|---|---|---|---|---|---|
| CODE | `0x1000` | `0x5210` | `0x400` | `0x5400` | **R-X** | the `0x1F0` above, now taken |
| DATA | `0x7000` | `0x20` | `0x5800` | `0x200` | RW | **`0x55807020`–`0x558071FF` = `0x1E0` of file-backed WRITABLE space, free** |
| BSS | `0x8000` | `0x45` | — | **`0`** | RW | `0x55808045`–`0x55808FFF`, loader-zeroed, writable, no file bytes — mutable state only |

`0x55806400`–`0x55806FFF` is CODE page slack: **R-X and unbacked**, so it is neither patchable in the
file nor writable at runtime. It is not cave space in either sense. A feature needing more than
`0x1F0` of code here must chain off this cave or append a section.

**vcl30.dpl** (preferred base `0x41300000`, rebases — PIC discipline applies to anything placed here):
touched by the mouse-wheel-scrolling feature family (`build_wheel_editor.py`,
`build_wheel_vclpump.py`) and `build_editor_timerres.py`. `build_wheel_vclpump.py` and
`build_editor_timerres.py` compute their landing addresses per-run; `build_wheel_editor.py` does not,
and its allocation was missing from this table until 2026-09-13:

| VA range | script | feature |
|---|---|---|
| `0x413A8400`–`0x413A87FF` | `build_wheel_editor.py` | `MouseProc`, 1 KB budget |
| `0x413A8800`–`0x413A89FF` | `build_wheel_editor.py` | the installer cave, `0x200`. **Hooked from `Forms.TApplication.Run @0x4133BC9C` with an `E9`, 7-byte prologue stolen** (`55 8b ec 51 89 45 fc`), resuming at `0x4133BCA3`. Verified live 2026-09-13: `0x4133BC9C` reads `jmp 0x413A8800`, two `nop` pad, then the resume |

Reserved zone is `0x413A8400..0x413A8A00`. ⚠ `TApplication.Run` is therefore **already taken** — the
obvious "one PIC cave in vcl30 fixes every exe at once" idea has to chain off this cave rather than
hook the same prologue. That is one of the two reasons `build_taskbar_icon.py` went per-exe instead
(the other: a vcl30 cave cannot reach the editor *source* `AoWDevEd.exe`, so future editor builds
would ship without it).

**HSEPack.dpl** (preferred base `0x55600000`, per `build_editor_rendergate.py`'s `PREF_BASE`). Two
**appended sections**, both at the end of the module, both read out of the live section table rather
than declared as a `CAVE_VA` constant — which is why a `grep -rn "CAVE.*= 0x"` refresh of this table
misses them entirely. `build_los_terrain.py` and `build_wheel_aowint.py` do patch existing hook sites
or reach another module's cave by cross-module call, as the rest of this entry used to claim for all
of them; these two do not:

| range | owner | notes |
|---|---|---|
| `.dlgd` `0x5564E000`–`0x5564E3FF` (raw) | `build_dlgdirs.py` | 16-wrapper dialog-directory cave. **34 bytes spare as of v3 (2026-09-11)**; `SizeOfRawData` is frozen at `0x400` because `.rgt`'s raw data starts at file `0x048600` |
| `.dlgd` `0x5564E400`–`0x5564E51F` | `build_dlgdirs.py` | `PATHBUF`, page slack past `SizeOfRawData`; its loader-zeroed first byte is the "INI path not yet built" flag |
| `.dlgd` `0x5564E520`–`0x5564E62F` | `build_dlgdirs.py` | `DIRBUF` (v3): StrRec at `0x5564E520`, chars at `0x5564E528`. VirtualSize raised `0x520 → 0x630` |
| `.dlgd` `0x5564E630`–`0x5564EFFF` | **free** | 2512 B of page slack. `.dlgd` owns its whole page — `.rgt` is at RVA `0x4F000` — so a VirtualSize up to `0x1000` is safe |
| `.rgt` `0x5564F000`–`0x5564F043` | `build_editor_rendergate.py` | counter / `every` / `skip_sleep` tunables |

⚠ `.dlgd`'s page slack is writable *data* only. Anything past `SizeOfRawData` has no file bytes
behind it, so **code cannot live there** — it exists solely because the loader zero-fills a section's
virtual tail. Code has to come out of the 34 remaining raw bytes (or out of the 264 that freeing the
profile read buffer would recover; see `08-editor.md` §2.2).

### 6.3 Two worked examples of the allocation discipline

**The `build_dispelmagic5.py` relocation (2026-08-26) is the canonical cautionary tale — read this
before ever trusting "no script references this address" as a reservation.**

The original cave was `0x55812AA0`, chosen because that zero run was, at the time, "referenced by no
script in `build_scripts/`." True when written; **false four months later**, when `build_magebane.py`
was given `CAVE_VA = 0x55812900` with `CAVE_LIMIT = 0x200` — i.e. `0x55812900..0x55812AFF` — which
swallows `0x55812AA0`. Magebane's own registration cave ended up occupying `0x55812A90..0x55812AB4`.

The result was a **live crash**. Dispel Magic's three site-patches stayed correct, but its cave was
gone: `GetLevelName`'s default arm jumped to `0x55812AA0`, which by then was the immediate-operand
tail of Magebane's `mov eax,0xAA` at `0x55812A9D`. Execution began on `00 00`
(`add byte ptr [eax], al`) with `EAX == 0`, i.e. a **null-pointer write**. Both level caps still read
5, so Dispel Magic IV/V were reachable in the UI and the game faulted the moment either was cast.
Magebane itself was undamaged — it was the victim address, not the intruder, that broke.

The fix (current state, `0x55821000..0x558213FF`, an explicit **exclusive reservation** this time):
verified 1024 zero bytes, no `.reloc` entries in the range, inside CODE vsize, sitting cleanly
between `build_caster_cost.py`'s reservation (`0x55820800..0x55820FFF`) and
`build_shipyard_income.py`'s floor (`0x55822000`), touching neither. The script also carries an
`OLD_CAVES` list naming the stolen address, so a future re-run **recognises** the damage (a jump
still pointing at `0x55812AA0` is reported as *stale, recoverable*, not *corrupt*) and repairs it —
repointing the jump and rebuilding the cave elsewhere — rather than aborting.

> "No script references this zero run" is a statement about a MOMENT IN TIME, not a reservation.
> Record a cave address in the allocation map the day it is claimed, declare its extent, and make
> `--undo` zero ONLY the emitted length — never a rounded reservation, which is what would let one
> feature's undo silently destroy another's cave.

**`build_reformingflesh.py`'s design spec named `0x55824200`, and the script itself caught why that
was wrong before ever writing a byte:** the spec reasoned from "an 800,936-byte zero run begins at
`0x55824158`" — true, but that run is the *tail of `build_waterheal.py`'s own declared growth zone*
(`0x55824000..0x55825200`, occupied to `0x55824168` as of v6 on 2026-09-06 and reserved to declare room to grow).
Dropping a cave at `0x55824200` would have sat inside another feature's reservation and been silently
overwritten the day `waterheal` grew — the same mistake `build_shield.py` separately caught and
documented when *its* spec named an address inside `build_shipyard_income.py`'s reservation.
`build_reformingflesh.py` allocated from `0x55826000` instead — page-aligned, above every address any
build script claimed at the time, confirmed with a plain grep for the digits before trusting it.

**The general lesson both examples teach: a "free" measurement is only as good as the moment it was
taken, and the only durable check is grepping the *current* tree for the digits of the address you're
about to claim** — not trusting a stale doc, and not trusting a zero-byte scan alone (zero bytes are
necessary but not sufficient; another script's *reservation* can be zero and still not be yours).

### 6.4 Chained caves — repointing another cave's exit jump instead of rewriting its body

`build_magebane.py` is the clearest example of a second, distinct coupling pattern (distinct from
"rewrite the body in place," which `build_invis_penalty.py`/`build_trueseeing.py` and
`build_raiseterrain_ug_earth.py`/`build_raiseterrain_lavadirt.py` both use — §6.1). Rather than
rewrite the three strike-creation caves it needs to add its bonus to, Magebane **repoints each cave's
final exit jump** into a small Magebane block that does its work and then jumps on to the original
return address:

| site | exit jump lives in (owned by) | was → | now → |
|---|---|---|---|
| melee 1 | `build_assassin.py`'s cave, exit at `0x5580E399` | `0x557666CF` (engine) | Magebane block → same |
| melee 3 | `build_ranged_slayers.py`'s cave family, exit at `0x5580E3D9` | `0x55767C89` (engine) | Magebane block → same |
| ranged | `build_invis_penalty.py`'s cave, exit at `0x5580E298` | `0x5576EB39` (engine) | Magebane block → chains onward (below) |

Minimal (4 bytes of rel32 per site) and reversible, but it makes the three donor scripts' caves a
**silent dependency**: re-running any of `build_assassin.py`, `build_ranged_slayers.py` or
`build_invis_penalty.py` rewrites its own cave from scratch and **drops the Magebane chain** with no
error — `build_magebane.py --verify` is what catches it, and re-running `build_magebane.py` afterward
restores the link.

The ranged site chains a second time, into `build_shield.py`'s own ranged cave
(`SHIELD_RANGED_CAVE = 0x558230D0`), which then resumes at the engine itself — so the full ranged
chain is `ranged slayers → invisibility → Magebane → Shield → engine`. Emitting the plain engine
address as Magebane's tail would have **silently unlinked Shield's ranged penalty**, a confirmed-
working feature, with no error anywhere — this was a real, un-runnable state of the script between
2026-08-26 and 2026-08-29. **Fixed 2026-08-29**: the build now detects at write time whether Shield's
cave is present (checks whether the bytes at `0x558230D0` are non-zero) and chains into it if so, or
emits the plain engine tail if Shield has been `--undo`ne. Re-applying `build_magebane.py` is
therefore safe in either state and in either order — no revert ordering is required. (An older
standing note warning never to `--apply` Magebane before undoing Shield predates this fix and should
be treated as superseded.)

**The general pattern, worth reusing:** when a new feature needs to run at a site an earlier cave
already owns the exit of, repointing that exit's rel32 is cheaper and safer than rewriting the body —
provided the chain is detected (not hard-coded) at build time, so the script degrades gracefully
if an earlier link in the chain has since been undone.

#### The wire-format contract — two scripts, one set of bytes

`build_heroskill_race.py` + `build_herodlg_columns.py` (2026-09-09) is the same coupling seen from
the *donor's* side: the guest hooks a site **inside** the host's cave, and the host regenerates that
cave wholesale. Magebane detects and repairs its own chain when re-run; here the **host** repairs the
guest, because the host is the one that breaks it. Four rules made that safe, and they generalise to
any pair of scripts that must write the same bytes:

1. **One code path, not two copies.** The host does not re-derive anything: it imports the guest and
   calls `relink_bytes(data)`, which runs the guest's own pattern search and its own byte emitters
   over the host's in-memory image. Two implementations of "the same" hook drift; one cannot.
2. **Fixed slots for everything the host must rewrite.** The guest's two tail jumps sit at constant
   offsets (`cave+0x200`, `cave+0x205`) so the host can repoint them without assembling anything or
   knowing how long the guest's code is.
3. **A magic dword as the installed-probe.** `RGT1` at the cave base answers "is the guest here?"
   in four bytes, with no address arithmetic and no dependence on the guest's current code size.
4. **Never silent, in either direction.** The host prints `re-chained` or `not installed` on every
   apply, and shouts if the guest module will not even import. The guest's no-arg run re-verifies
   the whole chain. Byte-identical output from either order is then testable, and was tested.

⚠ The trap this pair sprang: **the guest's cave replays the host bytes it displaced**, so the cave's
own first instructions *are* the locator pattern. Any pattern search must exclude the searcher's own
reservation, or the first apply succeeds and every later run finds two matches.

### 6.5 `cave_bookfilter@0x0060C0A8` — one cave, two features, a non-obvious revert order

`build_spellcast_book_exe.py` originally owned this cave (a ~0xA1-byte filter that hides too-high-
tier spells from the casting book, in AoWz.exe + AoWzCompat.exe). `build_scroll_spellbook.py` absorbed
it verbatim when it rewrote the cave in place on 2026-07-30, to add scroll-granted spells to the
filtered list. On 2026-09-03 the filter's own logic changed again, in place, to make the tier test
**unit-only** per a user ruling ("Spellcasting level should only restrict tier of spell that's
castable for units, not heroes") — so `build_scroll_spellbook.py` is now the *only* place the
hero-tier exemption exists on the exe side, and the cave now serves three purposes at once (tier
filtering, the hero exemption, and scroll spells).

This has a real dependency the DLL side must match: **`build_spellcast_herotier.py`** (§6.1,
`0x55846000`) is the AoWEPACK.dpl half of the same ruling — the cast-gate that actually enforces the
unit-only tier restriction. Either half missing is a silent no-op, in different ways:

- book half missing → a hero never *sees* the too-high-tier spell in their book, so nothing visibly
  changes;
- cast half missing → the hero sees the spell, clicks it, and nothing happens, with no message
  (`cave_tiergate`'s fail arm on the DLL side returns silently).

**⚠ `build_scroll_spellbook.py --undo` silently RE-BREAKS the hero exemption.** `--undo` restores
`old_cave`, which is `build_spellcast_book_exe.py`'s *original* 130-byte filter — the one that prunes
by tier for every caster, hero included. Undoing this script therefore reverts heroes to being
tier-limited again, with no error anywhere, *and* removes the scroll behaviour at the same time
(which is probably the only part you were trying to undo).

```text
REVERT ORDER — drop the whole hero-tier ruling, both halves:
    python build_scripts/build_spellcast_herotier.py --undo --apply     # DLL first
    python build_scripts/build_scroll_spellbook.py  --undo --apply      # exes second

REVERT ORDER — drop only the SCROLL feature, keep the hero exemption:
    not possible with --undo as written — it would take the exemption with it.
    Re-apply this script with the scroll stage disabled instead:
        python build_scripts/build_scroll_spellbook.py --append-upto=0 --apply
    which keeps the current (hero-exempt) stage-1 prune and emits no scroll append.
```

The DLL half (`build_spellcast_herotier.py`) is independent of the scroll feature and can be undone
on its own at any time without touching this cave.

Also worth carrying forward as a deliberate, sanctioned asymmetry rather than a bug: a **scroll**
spell is still gated by the M2 tier test (`spell.tier <= hero's Spellcasting level`) even though a
**researched** spell of the same tier is not, for that same hero, since 2026-09-03. Scrolls are
therefore stricter than research on purpose — do not "harmonise" the two without asking first.

### 6.5a The stale-`.reloc` register — every neutralised entry, and what displaced it

`build_relocfix.py` owns all of these. Mechanism, decode and the three detection rules are in §5.2c.
State: ✅ **CONFIRMED WORKING (2026-09-13)** — the Death Altar entry is proven by play; the other ten
are proven only by the same reasoning that found them, since each sits on dead or latent bytes and
has no observable symptom to test. `--undo --apply` restores type 3 on exactly these eleven.
The table keys each entry on the **file offset of its 16-bit entry word**, not on the RVA: 23
page-aligned RVAs in `AoWEPACK.dpl` (6 in `AoWDevEd.exe`, 1 in `AoWz.exe`) carry both a type-3 entry
and a type-0 pad at offset 0, so an `(rva, type)` lookup can alias the pad.

| module | RVA | sits in | displaced by | what the loader would smash |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x07CC75` | `TPlayerMagicControl.NewTurn+0x49` | `build_tierresearch_dll.py` hook @`0x5577CC72` over `mov eax,[0x558FC958]` — `e9` in v1, **`e8` (call) since v2, 2026-09-24** | the two `nop`s at `0x5577CC77/78` — a rebase delta is a multiple of 64 KB, so a `HIGHLOW` entry at `CC75` moves only the dword's top two bytes; the hook's rel32 (`CC73..CC76`) is never touched. ⚠ **Live since v2**: the grant now returns through those `nop`s to the `jmp 0x5577CD4A` at `0x5577CC79`, so this neutralisation is load-bearing (in v1 they were dead) |
| `AoWEPACK.dpl` | **`0x0807FB`** | **`ExecuteStormDamage+0x193`** | the Death/Divine dispatch rewrite over `mov dx,[0x55780840]` — ⚠ **no owning build script**, an unowned legacy patch | ⚠⚠ **`mov dx,0x20` — THE DEATH-ALTAR CRASH** |
| `AoWEPACK.dpl` | `0x082B77` | `TUnit.GetHits+0xF` | `build_medal_hpmv.py` shrank the body to `call 0x5580BE15 / ret` | inter-function padding before `TUnit.GetMoves@0x55782B84` — **dead** |
| `AoWz.exe` / `AoWzCompat.exe` | `0x02EDAE`, `0x02EE14` | `TSpellBook.SpellBookDestroy+0x686/+0x6EC` | `build_tierresearch_exe.py` nop'd the `push` at `0x42EDAD`/`0x42EE13` | latent |
| ″ | `0x05121C` | `TMWindow.MapWindowUpdate+0x4` | `build_clogwin_gate.py` / `build_combatlog_exe.py` hook @`0x451218` | latent |
| ″ | `0x00ABF5`, `0x00ACA1` | `0x0040ABF0`, `0x0040AC9C` | `e9` hooks over `mov eax,[0x45A420]` | **orphan tail** — rule A misses these (residual dword `0x0045A420` is a valid VA); caves never resume there |
| ″ | `0x04723C`, `0x047274` | `TSortClick` sites | `build_herodlg_columns.py` `e9` @`0x447238`/`0x447270` | **orphan tail**, same shape; caves re-implement the displaced code and `ret` |
| `AoWDevEd.exe` → `AoWzEd.exe` | `0x0013CA` | the `Sleep` import thunk `0x4013C8` | `build_editor_timerres.py` `e9` → cave `0x592020` | ⚠ **RVA+2 is the MSB of that `rel32`** — the one latent entry that would not hit padding but jump wild |

⚠ **Only the three in `AoWEPACK.dpl` were ever firing.** The exes carry `DllCharacteristics = 0` —
no `DYNAMIC_BASE` — so they load at `0x400000` and the delta is 0. (`IMAGE_FILE_RELOCS_STRIPPED` is
**not** set, so the table is live and Windows' *Force randomization for images* would apply it.)
⚠ **Fixing them does not make the exes ASLR-safe** and §6.5a must not be read that way: the added
cave sections (`.sc`, `.clog`, `.tres`, `.hcol`, RVA `0x20C000`–`0x22E000`) carry **zero**
relocations while containing absolute operands — cave `0x624050` alone has `mov eax,[0x45A420]` and
two `[esi*4 + 0x623cxx]` refs — so under mandatory ASLR the mod's exes break comprehensively
regardless. These eleven were fixed because it is free and correct, not because it buys ASLR safety.

⚠ **Reverse coupling — undo one of these features and its entry must be re-enabled.** Rule C in
`--audit` catches it after the fact; `build_relocfix.py` with no args aborts outright.

| undoing | restores | re-enable |
|---|---|---|
| `build_medal_hpmv.py --undo` | `TUnit.GetHits`' `0x558E83D4` medal-table lookup | `AoWEPACK.dpl` `0x82B77` |
| `build_clogwin_gate.py --off` | the stock prologue @`0x451218` | `AoWz.exe` `0x5121C` |
| `build_editor_timerres.py` undo | the `ff 25 <IAT_Sleep>` thunk @`0x4013C8` | `AoWDevEd.exe` `0x13CA` |
| `build_tierresearch_exe.py` verify-restore | `68 b0 ee 42 00` @`0x42EDAD`/`0x42EE13` | `AoWz.exe` `0x2EDAE`/`0x2EE14` |

⚠ `AoWzEd.exe` is **derived**. `build_relocfix.py` patches `AoWDevEd.exe` and prints the reminder;
`build_zigeditor.py --apply` was run afterwards. `AoWzEd.exe` vs `AoWDevEd.exe` differ in 4396 bytes,
all in `.rsrc`/`.mtb`/`.ctp` and **none in `.reloc`**, so the type-0 at `0x13CA` is the proof the
rebuild landed — never a file hash.
⚠ Root `AoWDevEd.exe` is **no longer byte-identical** to the Ziggurat one: it still carries the stale
entry, and now differs at exactly file `0x3D0E1`. Correct per "never patch the root", but the root
editor is the one non-vanilla binary there and someone may run it.

---
## 7. Reusable technique — per-hex ring detection for area effects

**Status: technique CONFIRMED WORKING in-game (2026-07-08)**, via the Path radius+1 / 25%-outer-ring
mod. This is a general RE technique, not a terrain feature — it belongs here rather than in a
feature file, because it applies to any future mechanic that needs to tell, per affected hex,
*which ring* it sits on relative to an effect's centre, then scale, gate or randomise behaviour by
ring. The feature it was proven on (Path abilities) has its own record in the movement/Path file;
this section is the reusable half.

Use it for: fading edges (an outer ring converts less often), ring-only/hollow effects (only the rim
burns), distance-scaled damage or healing, or any radius-graded area spell or ability.

### 7.1 The primitive: hex-number (HN) as a distance index

AoW hexes around a centre are numbered in an outward spiral. `HN` (the game's own "hex number") *is*
the distance-ordered index, so a single call converts two hex coordinates into "how far apart, as a
ring":

```
dHXtoHN   @0x557026A4   EAX=x1, EDX=y1, ECX=x2, [esp+4]=y2  ->  EAX = HN   (RET 4 / stdcall, 1 stack arg)
HNtoRad   @0x5570267C   EAX=HN  -> EAX = ring radius r
RadToHN   @0x55702684   EAX=r   -> EAX = first HN of ring r
```

Standard hex geometry — ring `r` has `6r` hexes; cumulative through ring `r` is `1+3r(r+1)`:

| ring r | hexes on it | HN range | first HN = `RadToHN(r)` |
|---:|---:|---|---:|
| 0 | 1 (centre) | 0 | 0 |
| 1 | 6 | 1..6 | 1 |
| 2 | 12 | 7..18 | 7 |
| 3 | 18 | 19..36 | 19 |
| 4 | 24 | 37..60 | 37 |

So **"which ring is this hex on?"** = `HNtoRad(dHXtoHN(cx,cy, hx,hy))`, or — cheaper — just compare
the raw HN against a threshold. For "is it strictly outside radius R?", the threshold is
`RadToHN(R+1)`: a radius-1 disk vs its ring-2 rim uses threshold **7** (`HN < 7` = inner disk,
`HN >= 7` = outer ring); a radius-2 disk vs its ring-3 rim uses threshold **19**; etc.

`dHXtoHN` is order-independent for distance (symmetric in its two points) and is already used by the
storm/area code, so it's the canonical, MP-safe way to measure hex distance. Don't hand-roll cube
coordinates.

⚠ Note the general caution elsewhere in this project about `dHXtoHN`'s companion function
`dHXtoHNfast`: that faster variant is **29.5% wrong beyond adjacency** — use the plain `dHXtoHN`
above for anything that isn't a pure "are these two hexes neighbours" check.

### 7.2 The pattern (three steps)

An area effect that walks a disk of hexes and fires a per-hex callback has no idea where the
*centre* is by the time the callback runs — it only gets the current hex. So:

**Step A — widen the radius.** The radius is usually a `push imm8` right before the area call. Bump
the immediate (`6A 01` → `6A 02` = `push 1` → `push 2`). One byte per call site.

**Step B — stash the centre.** Hook a point where the centre hex is in hand and copy its `x,y` into a
**2-byte scratch global**. Area walks are single-threaded, so one shared scratch is fine. The scratch
**must** live in a writable section — see §7.3.

**Step C — gate the per-hex callback.** Re-point the callback pointer to a small cave that:

1. reads the current hex's `x,y`,
2. computes `HN = dHXtoHN(cx, cy, hx, hy)`,
3. `cmp HN, <threshold>` — below ⇒ inner ⇒ run the real callback unconditionally; at/above ⇒ outer
   rim ⇒ roll the RNG and run it only on a hit, else `ret` (leave the hex untouched).

Re-pointing works only if the callback pointer has a `.reloc` entry (so writing the cave's preferred
VA gets rebased at load) — verify with the reloc parser before trusting it.

### 7.3 Gotcha 1 — scratch must live in a WRITABLE section (this cost a crash)

AoWEPACK's CODE section is read-only at runtime; the free cave region a script assembles into is
*inside* that section — fine to **execute**, faults if you **write**. Putting the centre-scratch
inside a CODE cave produced *"Exception occurred during TArmyDefaultMoveTE"* — the move ran, but the
terraform aborted the instant the stash tried to store.

**Rule (same as §5.3): caves may execute from CODE but must never write to it — put mutable scratch
in BSS.** This feature's centre stash lives at `SCRATCH = 0x558FA800` (2 bytes). Because BSS and CODE
share the same runtime rebase delta, a code cave reaches BSS with the usual call/pop-delta trick and
a constant offset — here the anchor plus a fixed offset lands exactly on `0x558FA800`,
position-independent, verified at the byte level after apply.

### 7.4 Gotcha 2 — use the synced RNG, and know the escape hatches

The proc roll uses the DLL's synchronised generator (§4.1): `Random(map,4); test eax,eax; jnz skip`
(proc only on `0`, i.e. 25%). Move execution *is* synchronised, so this passes cleanly here. If you
ever reuse this pattern from an unsynchronised context (render/anim/AI), see §4 in full — do not
improvise a raw draw or the bit-3 suppress flag without reading the trap in §4.6 first.

### 7.5 Worked example — Path radius +1, 25% on the outer ring

Path of Life (`0x45`) / Decay (`0x44`) / Frost (`0x6d`) terraform a radius-1 disk behind a moving
unit (`TAbstractUnit.MovedTo @0x55780328` → per-hex terrain callbacks). Goal: radius 2, but the
*new* rim (ring 2) converts only 25% of the time, so the trail frays at its edge instead of forming a
hard circle.

- **Radius:** `6A 01`→`6A 02` at `0x5578044E` (Life), `0x55780495` (Decay), `0x557804DA` (Frost).
- **Centre stash:** hook `0x5578041E` → `cave_stash @0x5580DD30`: reads `[EBP-4]`, writes `cx,cy` to
  `SCRATCH=0x558FA800`, replays the displaced `mov eax,[ebp-4]; cmp byte[eax+0x12],0`, jumps back to
  `0x55780425`.
- **Proc-gates:** the three callback pushes at `0x55780452 / 0x55780499 / 0x557804DE` (targets
  `0x557801A4 / C4 / E4`, each `.reloc`-backed) are re-pointed to `proc_life`/`proc_decay`/`proc_frost`
  @ `0x5580DD60` / `0x5580DDC0` / `0x5580DE20`. Each: `HN=dHXtoHN(cx,cy,hx,hy)`; `cmp eax,7; jl _proc`
  (inner disk, 100%); else `Random(map,4); test eax,eax; jnz _skip` (outer ring, 25%); `_proc:` jmp
  real callback; `_skip:` ret. Registers saved/restored so the area loop's EBX/ESI/EDI/EBP survive.
- Frost's separate FrozenWater spawn-notify (`PathOfFrostTerrainChanged @0x5578024C`) self-gates
  (only fires where a hex actually became ice), so it needs no ring gate of its own.

Caves at `0x5580DD30`+ — see §6.1 for the neighbouring allocations. Revert is surgical: the owning
script's `--undo` restores the three gated callbacks' original bytes and zeroes the caves from
`0x5580DD30` up; there is no `.pre-*` snapshot to restore instead (§10).

### 7.6 Adapting it — quick recipes

- **Different outer radius:** bump the `push` immediate to R, set the cave threshold to `RadToHN(R+1)`
  from the table in §7.1 (radius 2 → threshold 19, radius 3 → 37, …).
- **Different proc rate on the rim:** change `Random`'s `EDX` (the denominator) — `3` ≈ 33%, `4` =
  25%, `5` = 20%, `10` = 10% (proc on result `0`). For 75%, proc on `!= 0` instead (`jz _skip`).
- **Graded by ring (not just in/out):** call `HNtoRad` (or compare against several `RadToHN`
  thresholds) and pick a per-ring denominator — e.g. ring 1 100%, ring 2 50%, ring 3 25% for a smooth
  falloff.
- **Ring-only / hollow effect:** invert the inner test — `jl _skip` instead of `jl _proc`, so the
  centre disk is spared and only the rim fires.
- **Any centre-relative area:** the same stash-centre → `dHXtoHN`-per-hex approach works for *any*
  effect that exposes a per-hex hook and a reachable centre; it isn't Path-specific.

---
## 8. The full derived VMT layout

Produced 2026-08-03 by walking each class's VMT and resolving every slot to its real RTTI symbol via
the method in §3 — **no slot below is a guess.** `re_tools/ghidra_structs.py --md` regenerates this
from the binary at any time; do not hand-edit the table, edit the script.

As currently derived: **18 classes, 1,394 VMT slots** (an earlier summary elsewhere in this project's
history quoted "36 classes, 2,581 slots" — that count is stale and should not be repeated; the table
below, and the Extents summary at its head, are the current ground truth). The great majority of
slots resolve to a real export name; the remainder are methods inherited from base classes in *other*
modules this DLL does not export (`EngineP.dpl`, `VCL30.dpl`) — those are marked as such, not guessed.

**Where a VMT ends is found exactly**, because the class-name ShortString immediately follows the
last slot (e.g. `TStructure`'s VMT ends `…7453540A` = `\x0A"TStructure"`). Reading past it is not a
bad method pointer — it is a jump into a string. §3 above has the general header layout, the
double-indirect parent-pointer trap, and the abstract-stub / nil-safety gotchas that apply across
every class below; they are not repeated per class.

**⚠ `Inioch_Structure_Raze_Framework.md`'s "TStructure VMT" table is a union of three incompatible
classes** — worth flagging prominently since raze/structure work is a large and active area of this
project. It lists `+0x1F0 SetPlayer`, `+0x1FC ExecuteSearch`, `+0x200 Search`,
`+0x204/+0x208/+0x220 Update*` as `TStructure` slots. **`TStructure`'s own VMT ends at `+0x1EC`**
(`CanRaze` is its last slot) — none of those exist on it. Measured extents:

| class | VMT ends | `+0x1F0` | `+0x1FC` | `+0x200` |
|---|---|---|---|---|
| `TStructure`, `TArena` | `+0x1EC` | — | — | — |
| `TExplorationSite`, `TDungeon` | `+0x200` | `GetExplored` | `ExecuteSearch` | `Search` |
| `TTower`, `TReflectingPool` | `+0x220` | **`SetPlayer`** | `Update…` | `Visibility…` |

So `+0x1F0` is `GetExplored` on one branch, `SetPlayer` on another, and **does not exist at all** on
`TStructure` or `TArena`. A cave calling `structure->vmt[0x1F0]` on the wrong concrete class either
calls the wrong method or jumps into the RTTI string. Always take a slot list from the table below
for the **concrete** class you actually hold, never from a base-class assumption.

**The live DLL's VMT hooks, derived for free** by comparing pristine against live slot-by-slot: 15
VMT slots are currently repointed by this project. Notably `TUnit`/`TAdjustableUnit` `+0x128/+0x12C/
+0x130` are repointed to `THero`'s casting-point getters (the unit-spellcasting feature), and
`+0x13C` (`NewTurn`) and `+0x018` (`ReadWrite`) go to caves; `TArena` repoints three slots; `TTower`
repoints `ExecuteRaze`. Bulk verification of 103 older doc claims against this derivation: 89 passed,
3 were plain errors, 5 were not exported, 6 were past the VMT's actual end — three corrected claims
worth recording since they were cited elsewhere in this project:

| doc claim | derived (correct) slot |
|---|---|
| `TAbstractUnit+0x50` "SetAbilityEnabled" | **`TAbilityOwner.SetAbSet`** |
| `TAbstractUnit+0x11C` "CreateEnchantment" | **`TAbstractUnit.CanAddToList`** |
| `TAbstractUnit+0x1AC` "KillUnit" | **`TAbstractUnit.Killed`** |

The full class-by-class table follows, including each class's own derivation notes (how its extent
was proven, its ancestor chain, and where each slot range was introduced).

---
### Extents

| class | VMT | instance size | VMT ends | slots |
|---|---|---|---|---|
| `AoWE.TPlayer` | `0x5570C508` | `0xDC` | `0x4C` | 19 |
| `AoWE.TSpell` | `0x55722D7C` | `0x34` | `0x9C` | 44 |
| `AoWHex.TAoWWaterHexagon` | `0x5579A5F8` | `0x20` | `0x128` | 74 |
| `TAbility` | `0x5570F254` | `0x24` | `0x10C` | 67 |
| `TAbstractUnit` | `0x55710740` | `0x3C` | `0x1B8` | 110 |
| `TAoWHSMap` | `0x5570E874` | `0x41C` | `0x130` | 76 |
| `TAoWHexagon` | `0x5579A1D0` | `0x14` | `0x124` | 73 |
| `TArena` | `557D6240` | `0x30` | `0x1F0` | 124 |
| `TCombatObject` | `0x557158EC` | `0x4C` | `0x134` | 77 |
| `TCombatUnit` | `0x55715A94` | `0x5C` | `0x13C` | 79 |
| `TExplorationSite` | `0x557C1440` | `0x38` | `0x204` | 129 |
| `THero` | `0x55711FEC` | `0x9C` | `0x1C8` | 114 |
| `TItem` | `0x5570FAFC` | `0x4C` | `0xB4` | 45 |
| `TRangedAttackAbility` | `0x5571E8D4` | `0x30` | `0x120` | 72 |
| `TStrikeCA` | `0x5571E344` | `0x1C` | `0x70` | 28 |
| `TStructure` | `0x55713C18` | `0x30` | `0x1F0` | 124 |
| `TUnit` | `0x55710CAC` | `0x48` | `0x1B8` | 110 |
| `TUnitResource` | `0x55710A64` | `0x54` | `0x74` | 29 |

### AoWE.TPlayer  —  VMT `0x5570C508`, instance `0xDC`, 19 slots, ends `0x4C`

<details><summary>derivation notes</summary>

```
VMT = 0x5570C508 .. 0x5570C553 inclusive. 19 virtual slots (+0x00..+0x48); first offset past the end is +0x4C.

WHY +0x4C IS THE END (three independent proofs, not just "pointer looks wrong"):
1. [VMT+0x4C] = 0x0000000E, not a CODE pointer (CODE = 0x55701000-0x558E7918).
2. vmtInitTable at [VMT-0x34] = 0x5570C554 = VMT+0x4C exactly, i.e. the compiler placed the field-init table immediately after the last VMT slot. That 0x0E is tkRecord, the InitTable's kind byte.
3. TPlayer's parent Engine.TEObject also has a 19-slot VMT: of 86 direct TEObject descendants in AoWEPACK, 60 end at exactly +0x4C. TPlayer declares NO new virtual methods at all — it only overrides existing TEObject slots.

TPlayer OVERRIDES exactly 5 methods (4 in the positive VMT + Destroy at -0x04): ReadWrite, Create, ClassID, MsgProc, Destroy. Everything else is an inherited Engine.TEObject jmp-thunk. All 14 inherited slots resolve to `jmp dword ptr [IAT]` stubs importing from EngineP.dpl; names taken from the PE import-name table (ground truth, not inference), and independently corroborated by counting how many sibling classes leave each slot un-overridden: +0x18 ReadWrite x163, +0x1C MainReadWrite x706, +0x20 Create x65, +0x24 ClassID x357, +0x44 MsgProc x546, +0x48 SetArrayOwner x722.

NEGATIVE (metadata + the 5 standard Delphi virtuals). NOTE these are real callable slots and one of them is a TPlayer override:
  -0x40 vmtSelfPtr        = 0x5570C508  (equals the VMT address itself - this is what pins the base)
  -0x3C vmtIntfTable      = 0
  -0x38 vmtAutoTable      = 0
  -0x34 vmtInitTable      = 0x5570C554
  -0x30 vmtTypeInfo       = 0
  -0x2C vmtFieldTable     = 0
  -0x28 vmtMethodTable    = 0
  -0x24 vmtDynamicTable   = 0
  -0x20 vmtClassName      = 0x5570C57E -> ShortString 07 "TPlayer"
  -0x1C vmtInstanceSize   = 0xDC (220)
  -0x18 vmtParent         = 0x558FC92C -> IAT slot, EngineP.dpl :: "Engine..TEObject@BD8FE92F"
  -0x14 SafeCallException = 0x557010C8 -> VCL30.dpl :: System.TObject.SafeCallException@23EDC2EF
  -0x10 DefaultHandler    = 0x557010D0 -> VCL30.dpl :: System.TObject.DefaultHandler@23EDC2EF
  -0x0C NewInstance       = 0x55701098 -> VCL30.dpl :: System.TObject.NewInstance@23EDC2EF
  -0x08 FreeInstance      = 0x557010A0 -> VCL30.dpl :: System.TObject.FreeInstance@23EDC2EF
  -0x04 Destroy           = 0x55751154 -> AoWE.TPlayer.Destroy@23EDC2EF  *** TPlayer OVERRIDE ***

⚠ CORRECTION TO THE VMT RECIPE IN THE BRIEF (worth propagating to the docs). The recipe given ([VMT-0x20]=name, [VMT-0x1C]=instsize, [VMT-0x18]=parent) is CORRECT for this binary, but it is NOT the textbook Delphi 3 layout (which puts ClassName at -12 and the standard virtuals at POSITIVE 0..28). AoWEPACK uses the older Delphi 2-style layout: the 5 standard TObject virtuals sit at NEGATIVE -0x14..-0x04 and user-declared virtuals start at +0x00. Verified empirically, so the project's convention is safe to keep:
  - vmtSelfPtr is at -0x40 and holds the VMT address itself. This is a self-checking fingerprint: scanning CODE for "dword at A whose value == A+0x40" enumerates every VMT in the module (found 893 classes) with zero false positives. That is a better VMT finder than the string search, and it needs no class name.
  - Destroy landing at exactly -0x04 (canonical vmtDestroy for this layout) confirms the base independently.
If the textbook Delphi 3 constants had been used, every offset in this project's docs would be shifted by 0x14. They are not.

PARENT CHAIN STOPS HERE: TPlayer's immediate parent Engine.TEObject lives in EngineP.dpl, which is NOT loaded in Ghidra, so the chain above TEObject cannot be walked from this module. TEObject's own 19 virtual methods are fully named above regardless (from the import table), so the whole inherited surface is known even though the ancestor's binary is absent.

BONUS - managed fields, derived from the InitTable at 0x5570C554 (kind=0x0E tkRecord, count=4). TPlayer has exactly 4 compiler-managed AnsiString fields (typeinfo = VCL30.dpl :: 
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | Engine.TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | Engine.TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | Engine.TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | Engine.TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x18` | `0x5575314C` | `AoWE.TPlayer.ReadWrite@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.ReadWrite) |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | Engine.TEObject |
| `0x20` | `0x55750EA8` | `AoWE.TPlayer.Create@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.Create) |
| `0x24` | `0x557516C8` | `AoWE.TPlayer.ClassID@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.ClassID) |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | Engine.TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | Engine.TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | Engine.TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | Engine.TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | Engine.TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | Engine.TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | Engine.TEObject |
| `0x44` | `0x55752F08` | `AoWE.TPlayer.MsgProc@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.MsgProc) |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | Engine.TEObject |

### AoWE.TSpell  —  VMT `0x55722D7C`, instance `0x34`, 44 slots, ends `0x9C`

<details><summary>derivation notes</summary>

```
DERIVATION (all VAs at the DPL's preferred base 0x55700000; the module rebases at runtime).

VMT LOCATION. Class-name ShortString "\x06TSpell" at 0x55722E2A; the only dword pointing at it is
at 0x55722D5C, so VMT = 0x55722D5C + 0x20 = 0x55722D7C. Cross-checked against the self-pointer:
[VMT-0x40] == 0x55722D7C == VMT itself. Ghidra's read_memory at 0x55722D7C byte-for-byte matches
Modding Resources/AoWEPACK_original_backup.dpl, so file and Ghidra image agree.

VMT HEADER (Delphi 3, 64-byte header — CONFIRMED empirically by the imported symbol names, not
assumed). Layout verified as:
  -0x40 SelfPtr        = 0x55722D7C  (points at the VMT)
  -0x3C IntfTable      = 0
  -0x38 AutoTable      = 0
  -0x34 InitTable      = 0x55722E18
  -0x30 TypeInfo       = 0
  -0x2C FieldTable     = 0
  -0x28 MethodTable    = 0
  -0x24 DynamicTable   = 0   <- no dynamic methods; every virtual is in the table above
  -0x20 ClassName      = 0x55722E2A
  -0x1C InstanceSize   = 0x34 (52 bytes)
  -0x18 Parent         = 0x558FC92C
  -0x14 SafeCallException / -0x10 DefaultHandler / -0x0C NewInstance / -0x08 FreeInstance
  -0x04 Destroy        = 0x557791F4 = AoWE.TSpell.Destroy  (TSpell overrides the destructor)
Note the ordering: vmtDestroy is at -0x04, NOT at +0x08. The four System.TObject slots at
-0x14..-0x08 name themselves via the import table, which pins the whole header layout.

ANCESTRY. [VMT-0x18] = 0x558FC92C is an .idata (IAT) slot, i.e. the parent classref is IMPORTED:
EngineP.dpl!Engine..TEObject@BD8FE92F. So the chain is
  System.TObject -> Engine.TEObject (EngineP.dpl) -> AoWE.TSpell
with NO intermediate class. TSpell is a DIRECT descendant of TEObject.

INHERITED SLOTS ARE IMPORT THUNKS. Because TEObject lives in another package, every inherited slot
points at an 8-byte thunk in this module's CODE section of the form
  FF 25 <abs IAT>   jmp dword ptr [imp]      (+ 8B C0 padding)
e.g. +0x00 -> 0x55703074 = "jmp [0x558FC724]" -> EngineP.dpl!Engine.TEObject.ClassVersion.
Ghidra has no function objects at these thunk addresses (get_function_by_address returns "No
function found"), so the names above were resolved by walking this DLL's import descriptors and
reading the IMAGE_IMPORT_BY_NAME entry each IAT slot references. That is ground truth, not a guess.
IMPORTANT FOR HOOKING: patching a 557030xx thunk changes that call for EVERY AoWEPACK class that
inherits the slot, not just TSpell. Redirect the VMT slot itself, not the thunk.

TEObject's own VMT is exactly 0x4C bytes (19 slots, +0x00..+0x48). TSpell's newly-introduced
virtuals therefore start at +0x4C. The base names for slots +0x00..+0x48 were confirmed by scanning
all 893 VMTs in the module, taking the 86 that are direct TEObject descendants, and reading the
un-overridden thunk in each slot — every one of the 19 slots is left un-overridden by at least one
sibling, so all 19 names are directly observed. In particular this pins the two slots TSpell
overrides: +0x18 = TEObject.ReadWrite (51 of 86 siblings override it) and +0x20 = TEObject.Create
(64 of 86 override it, it is a virtual constructor).

END OF VMT. [VMT+0x9C] = 0x0000000E, which is not in the executable range (CODE = 0x55701000..
0x558E7A00) — so the VMT is 39 slots, +0x00..+0x98, ending at +0x9C. This is not a heuristic stop:
0x55722D7C + 0x9C = 0x55722E18, which is exactly the value of the InitTable pointer at [VMT-0x34].
The InitTable record begins there (its first dword 0x0000000E is a type-kind tag), so the VMT ends
where the init table begins. Nothing follows the VMT that could be mistaken for a 40th slot.

MEMBERS THAT ARE NOT VIRTUAL. Ghidra's symbol table lists 28 AoWE.TSpell.* methods; 22 of them
(plus Destroy) appear above. The six that are NOT in the VMT are non-virtual/static methods and
cannot be hooked by slot replacement:
  0x557797A0 AICastSpellExpenseMade     0x557796E4 AIRequestCastSpellExpense
  0x557794BC CastingDone                0x557794E8 CombatCastingDone
  0x5577954C CombatSpellCast
(DynamicTable is nu
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `-0x14` | `0x557010C8` | `System.TObject.SafeCallException@23EDC2EF` | System.TObject |
| `-0x10` | `0x557010D0` | `System.TObject.DefaultHandler@23EDC2EF` | System.TObject |
| `-0x0C` | `0x55701098` | `System.TObject.NewInstance@23EDC2EF` | System.TObject |
| `-0x08` | `0x557010A0` | `System.TObject.FreeInstance@23EDC2EF` | System.TObject |
| `-0x04` | `0x557791F4` | `AoWE.TSpell.Destroy@23EDC2EF` | AoWE.TSpell |
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | Engine.TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | Engine.TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | Engine.TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | Engine.TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x18` | `0x55779234` | `AoWE.TSpell.ReadWrite@23EDC2EF` | AoWE.TSpell |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | Engine.TEObject |
| `0x20` | `0x55779178` | `AoWE.TSpell.Create@23EDC2EF` | AoWE.TSpell |
| `0x24` | `0x55703094` | `Engine.TEObject.ClassID@23EDC2EF` | Engine.TEObject |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | Engine.TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | Engine.TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | Engine.TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | Engine.TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | Engine.TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | Engine.TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | Engine.TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | Engine.TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | Engine.TEObject |
| `0x4C` | `0x5577956C` | `AoWE.TSpell.PlayDefaultCastEffects@23EDC2EF` | AoWE.TSpell |
| `0x50` | `0x55779670` | `AoWE.TSpell.ExecuteTE@23EDC2EF` | AoWE.TSpell |
| `0x54` | `0x557796C4` | `AoWE.TSpell.CreateCastSpellAction@23EDC2EF` | AoWE.TSpell |
| `0x58` | `0x557796D4` | `AoWE.TSpell.SetupCastSpellAction@23EDC2EF` | AoWE.TSpell |
| `0x5C` | `0x55779824` | `AoWE.TSpell.AIPrefetchCastSpellActions@23EDC2EF` | AoWE.TSpell |
| `0x60` | `0x55779828` | `AoWE.TSpell.AIExecuteCastSpellAction@23EDC2EF` | AoWE.TSpell |
| `0x64` | `0x55779230` | `AoWE.TSpell.GetEnabled@23EDC2EF` | AoWE.TSpell |
| `0x68` | `0x557792D0` | `AoWE.TSpell.CanActivate@23EDC2EF` | AoWE.TSpell |
| `0x6C` | `0x55779354` | `AoWE.TSpell.Activate@23EDC2EF` | AoWE.TSpell |
| `0x70` | `0x557793A4` | `AoWE.TSpell.CanActivateCombat@23EDC2EF` | AoWE.TSpell |
| `0x74` | `0x557793B4` | `AoWE.TSpell.ActivateCombat@23EDC2EF` | AoWE.TSpell |
| `0x78` | `0x55779450` | `AoWE.TSpell.CreateCA@23EDC2EF` | AoWE.TSpell |
| `0x7C` | `0x5577945C` | `AoWE.TSpell.GetCombatInfo@23EDC2EF` | AoWE.TSpell |
| `0x80` | `0x5577948C` | `AoWE.TSpell.GetCombatDamageValue@23EDC2EF` | AoWE.TSpell |
| `0x84` | `0x55779490` | `AoWE.TSpell.GetCombatDamageValueEx@23EDC2EF` | AoWE.TSpell |
| `0x88` | `0x5577969C` | `AoWE.TSpell.tcGetDamageValueEx@23EDC2EF` | AoWE.TSpell |
| `0x8C` | `0x557796B8` | `AoWE.TSpell.tcGetDamageValue@23EDC2EF` | AoWE.TSpell |
| `0x90` | `0x55779694` | `AoWE.TSpell.fcPrefetchCombatCommands@23EDC2EF` | AoWE.TSpell |
| `0x94` | `0x55779698` | `AoWE.TSpell.fcExecuteCombatCommand@23EDC2EF` | AoWE.TSpell |
| `0x98` | `0x5577967C` | `AoWE.TSpell.fcGetDamageValueEx@23EDC2EF` | AoWE.TSpell |

### AoWHex.TAoWWaterHexagon  —  VMT `0x5579A5F8`, instance `0x20`, 74 slots, ends `0x128`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
VMT located by the RTTI recipe on Modding Resources\AoWEPACK_original_backup.dpl: exactly ONE dword in the image points at the ShortString "TAoWWaterHexagon" (@0x5579A720), so VMT = that dword's VA + 0x20 = 0x5579A5F8. No ambiguity. Cross-checked with Ghidra read_memory at 0x5579A5F8 len 304 — Ghidra's bytes are byte-identical to the file-derived table, so both views agree.
VMT file offset (preferred base 0x55700000, CODE VA 0x55701000 / raw 0x400): 0x999F8. VMT slot N is at file offset 0x999F8 + N.

END OF VMT
74 slots, +0x000..+0x124 inclusive; first non-CODE dword is at +0x128 = 0x6F415410, which is the class's OWN name ShortString (10 "TAoWWaterHexagon" — 0x5579A5F8+0x128 = 0x5579A720, exactly the vmtClassName target). So vmt_end = 0x128 and it is self-evidently the end, not a guess.

*** ALMOST EVERY SLOT IS AN IMPORT THUNK, NOT LOCAL CODE ***
Only 5 slots point at real AoWEPACK code. The other 69 point at 6-byte `jmp dword ptr [IAT]` stubs inside AoWEPACK whose IAT entry names the implementing package. I resolved every one through AoWEPACK's import directory (name table), which is why the symbols are exact rather than inferred. Ghidra has no function defined at some of these stubs (e.g. 0x5579A148, 0x5579A140) — get_function_by_address returns "No function found" there; the import-table walk is the reliable resolver.
Module map for the symbols above (derivable from the unit prefix):
  Engine.*    -> EngineP.dpl
  HSEngine.*  -> HSEPack.dpl
  IsoHex.*    -> HSEPack.dpl
  AoWHex.*    -> local, inside AoWEPACK.dpl (the 5 own overrides)
The three IsoHex thunks sit next to the VMT rather than in the module-wide thunk block: 0x5579A148 = jmp [0x558FCD58] (DynamicIsometricHexagonClass), 0x5579A150 = jmp [0x558FCD54] (Disconnect), 0x5579A158 = jmp [0x558FCD50] (NeighbourTerrainChanged).
PATCHING IMPLICATION: to change inherited behaviour for water hexagons only, overwrite the VMT slot (file offset 0x999F8+N) — do NOT patch the thunk, it is shared by other classes, and do not expect the implementation to be in AoWEPACK at all.

THE 5 SLOTS TAoWWaterHexagon ACTUALLY IMPLEMENTS (all local AoWEPACK code, Ghidra-symbolled)
  +0x020 Create            0x5579AD40  body 5579AD40-5579AD8F  (TAoWWaterHexagon*, char)
  +0x024 ClassID           0x5579AD90  body 5579AD90-5579AD95  (6 bytes: mov eax,0002073D; ret -> ClassID = 0x2073D)
  +0x0A8 Show              0x5579AEAC  body 5579AEAC-5579AFB1
  +0x11C UpdateTransitions 0x5579AD98  body 5579AD98-5579AEAB
  +0x124 ShowDynamic       0x5579AFB4  body 5579AFB4-5579B54E  (by far the largest — the water animation path)

ANCESTOR CHAIN (derived, not assumed — walked through HSEPack.dpl's own VMTs; the vmtParent field at VMT-0x18 is an .idata slot = import 'IsoHex..TLowerIsometricHexagon@D76F96D2' from HSEPack.dpl)
  TEObject (EngineP.dpl)
    -> HSEngine.THexagonSprite        VMT 0x55603694  instsize 0x08  vmt_end +0x108
    -> HSEngine.TMapObject            VMT 0x55604190  instsize 0x10  vmt_end +0x11C
    -> HSEngine.TAbstractHexagon      VMT 0x556047CC  instsize 0x10  vmt_end +0x120
    -> IsoHex.TIsometricHexagon       VMT 0x556190D8  instsize 0x18  vmt_end +0x128
    -> IsoHex.TLowerIsometricHexagon  VMT 0x55619640  instsize 0x18  vmt_end +0x128
    -> AoWHex.TAoWWaterHexagon        VMT 0x5579A5F8  instsize 0x20  vmt_end +0x128
(HSEPack VAs are at HSEPack.dpl's own preferred base, a different module.)
Consequences worth recording:
- TAoWWaterHexagon introduces NO new virtual methods — its vmt_end equals its parent's (0x128). All 5 local slots are overrides.
- Slot ownership boundaries: TAbstractHexagon's VMT ends at +0x120, so +0x11C (UpdateTransitions) is the last slot it declares; TIsometricHexagon adds +0x120 (DynamicIsometricHexagonClass) and +0x124 (ShowDynamic).
- TLowerIsometricHexagon contributes ZERO slots to this VMT even though it is the direct parent: it exports overrides of ClassID, UpdateTransitions and ShowDynamic, and TAoWWaterHexagon re-overrides all th
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557021F4` | `HSEngine.TMapObject.ReadWrite@23EDC2EF` | TMapObject |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5579AD40` | `AoWHex.TAoWWaterHexagon.Create@23EDC2EF` | TAoWWaterHexagon |
| `0x24` | `0x5579AD90` | `AoWHex.TAoWWaterHexagon.ClassID@23EDC2EF` | TAoWWaterHexagon |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x557021B4` | `HSEngine.TMapObject.GetTerrain@23EDC2EF` | TMapObject |
| `0x50` | `0x557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `0x557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `0x557021CC` | `HSEngine.TMapObject.GetOverlay@23EDC2EF` | TMapObject |
| `0x5C` | `0x557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `0x557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `0x557022FC` | `HSEngine.TAbstractHexagon.GetLevel@23EDC2EF` | TAbstractHexagon |
| `0x68` | `0x55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `0x5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `0x557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `0x55702164` | `HSEngine.TMapObject.GetXhx@23EDC2EF` | TMapObject |
| `0x78` | `0x5570216C` | `HSEngine.TMapObject.GetYhx@23EDC2EF` | TMapObject |
| `0x7C` | `0x55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `0x55701DC4` | `HSEngine.THexagonSprite.GetXYL@23EDC2EF` | THexagonSprite |
| `0x84` | `0x5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `0x55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `0x557022F4` | `HSEngine.TAbstractHexagon.GetShowPriority@23EDC2EF` | TAbstractHexagon |
| `0x90` | `0x55702214` | `HSEngine.TMapObject.Connect@23EDC2EF` | TMapObject |
| `0x94` | `0x5579A150` | `IsoHex.TIsometricHexagon.Disconnect@23EDC2EF` | TIsometricHexagon |
| `0x98` | `0x55701E24` | `HSEngine.THexagonSprite.CanChangeTerrain@23EDC2EF` | THexagonSprite |
| `0x9C` | `0x5570231C` | `HSEngine.TAbstractHexagon.ChangeTerrain@23EDC2EF` | TAbstractHexagon |
| `0xA0` | `0x55702324` | `HSEngine.TAbstractHexagon.TerrainChanged@23EDC2EF` | TAbstractHexagon |
| `0xA4` | `0x5579A158` | `IsoHex.TIsometricHexagon.NeighbourTerrainChanged@23EDC2EF` | TIsometricHexagon |
| `0xA8` | `0x5579AEAC` | `AoWHex.TAoWWaterHexagon.Show@23EDC2EF` | TAoWWaterHexagon |
| `0xAC` | `0x5570222C` | `HSEngine.TMapObject.PlaceOnMap@23EDC2EF` | TMapObject |
| `0xB0` | `0x55702234` | `HSEngine.TMapObject.RemoveFromMap@23EDC2EF` | TMapObject |
| `0xB4` | `0x5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `0x55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `0x55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `0x557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `0x5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `0x55702224` | `HSEngine.TMapObject.Loaded@23EDC2EF` | TMapObject |
| `0xCC` | `0x5570233C` | `HSEngine.TAbstractHexagon.MapFieldMsgProc@23EDC2EF` | TAbstractHexagon |
| `0xD0` | `0x55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `0x55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `0x55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `0x55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `0x55702314` | `HSEngine.TAbstractHexagon.Activate@23EDC2EF` | TAbstractHexagon |
| `0xE4` | `0x55702254` | `HSEngine.TMapObject.Deactivate@23EDC2EF` | TMapObject |
| `0xE8` | `0x55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `0x55701D44` | `HSEngine.THexagonSprite.UpdateMapField@23EDC2EF` | THexagonSprite |
| `0xF0` | `0x5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `0x55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `0x557021A4` | `HSEngine.TMapObject.CanSelect@23EDC2EF` | TMapObject |
| `0xFC` | `0x557021E4` | `HSEngine.TMapObject.Select@23EDC2EF` | TMapObject |
| `0x100` | `0x557021EC` | `HSEngine.TMapObject.Unselect@23EDC2EF` | TMapObject |
| `0x104` | `0x55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x5570230C` | `HSEngine.TAbstractHexagon.SetResource@23EDC2EF` | TAbstractHexagon |
| `0x114` | `0x5570232C` | `HSEngine.TAbstractHexagon.CanPlace@23EDC2EF` | TAbstractHexagon |
| `0x118` | `0x55702334` | `HSEngine.TAbstractHexagon.PlaceHX@23EDC2EF` | TAbstractHexagon |
| `0x11C` | `0x5579AD98` | `AoWHex.TAoWWaterHexagon.UpdateTransitions@23EDC2EF` | TAoWWaterHexagon |
| `0x120` | `0x5579A148` | `IsoHex.TIsometricHexagon.DynamicIsometricHexagonClass@23EDC2EF` | TIsometricHexagon |
| `0x124` | `0x5579AFB4` | `AoWHex.TAoWWaterHexagon.ShowDynamic@23EDC2EF` | TAoWWaterHexagon |

### TAbility  —  VMT `0x5570F254`, instance `0x24`, 67 slots, ends `0x10C`

<details><summary>derivation notes</summary>

```
DERIVATION / GROUND TRUTH
Source bytes: "Modding Resources/AoWEPACK_original_backup.dpl" (same image Ghidra holds as AoWEPACK_vanilla.dpl). Preferred base 0x55700000; the DPL rebases at runtime, so treat VAs as base+RVA.

RTTI header (Delphi 3 layout, all verified empirically, not assumed):
  [VMT-0x40] 0x5570F254 = self-pointer (equals the VMT VA -> confirms VMT location)
  [VMT-0x34] 0x5570F360 = init table  == VMT+0x10C  (see END-OF-VMT proof)
  [VMT-0x20] 0x5570F372 -> ShortString 08 "TAbility"
  [VMT-0x1C] 0x00000024 = instance size (36 bytes)
  [VMT-0x18] 0x558FC92C = .idata cell "EngineP.dpl!Engine..TEObject@BD8FE92F"
  [VMT-0x14] 0x557010C8 -> thunk VCL30.dpl!System.TObject.SafeCallException
  [VMT-0x10] 0x557010D0 -> thunk VCL30.dpl!System.TObject.DefaultHandler
  [VMT-0x0C] 0x55701098 -> thunk VCL30.dpl!System.TObject.NewInstance
  [VMT-0x08] 0x557010A0 -> thunk VCL30.dpl!System.TObject.FreeInstance
  [VMT-0x04] 0x5574E65C = AoWE.TAbility.Destroy@23EDC2EF  <-- REAL OVERRIDE, lives outside the 0x00+ walk. Anyone hooking TAbility destruction must patch -0x04, not a positive slot.

ANCESTRY: TAbility's immediate parent is Engine.TEObject in EngineP.dpl. There is NO intermediate class inside AoWEPACK. TEObject itself is not in this module, so its own VMT cannot be walked here.

END-OF-VMT PROOF (three independent lines):
 1. VMT+0x10C reads 0x0000000E, not a CODE pointer.
 2. vmtInitTable ([VMT-0x34]) == 0x5570F360 == VMT+0x10C exactly -> the class's data tables begin where the VMT ends; 0x0E is the tkRecord type-kind byte of that init table.
 3. Descendant cross-check: TDurationAbility (VMT 0x5571DD68, instsize 0x2C, parent TAdjustableAbility) reproduces slots 0x00..0x108 with identical semantics (overriding some) and then adds TDurationAbility.GetDuration at +0x10C and TDurationAbility.GetTotalDuration at +0x110, ending at 0x114. So 0x108 is genuinely TAbility's last slot.

HOW SYMBOLS WERE RESOLVED
- Delphi packages export every method; I parsed AoWEPACK.dpl's export directory (10036 names / 10033 distinct VAs) into a VA->symbol map. That is the same source Ghidra derives its names from. Spot-checked against Ghidra get_function_by_address for 0x5574E65C, 0x5574F07C, 0x5574E978 -> exact match.
- The 17 inherited slots do NOT point at AoWEPACK code: they hold 6-byte `jmp dword ptr [IAT]` thunks in the cluster 0x55703074..0x55703104 (8-byte stride). Ghidra has no function objects there (get_function_by_address returns "No function found"), so these resolve only through the import table. The `target_va` I report is the thunk address inside AoWEPACK; the `symbol` is the imported EngineP.dpl method it forwards to.

TRAP FOR FUTURE WORK: the thunk cluster contains 19 TEObject thunks but only 17 appear in TAbility's VMT. Engine.TEObject.ReadWrite (thunk 0x557030FC) and Engine.TEObject.Copy (thunk 0x557030CC) are absent — ReadWrite because TAbility overrides that slot (its thunk is the `inherited` call; confirmed in the decompile of TAbility.ReadWrite, which calls Engine_TEObject_ReadWrite first), Copy because it is called non-virtually elsewhere in the module. Do NOT infer VMT membership from membership of the thunk cluster.

TWO OVERRIDES IN THE INHERITED REGION: +0x018 (ReadWrite) and +0x020 (Create, a virtual constructor). Every other slot in 0x00..0x048 is a straight TEObject passthrough.

TAbility INTRODUCES 48 NEW VIRTUALS: +0x04C through +0x108 inclusive. All 67 slots resolved to a real symbol; none unnamed.

STUB WARNING: several targets are 3-4 byte default stubs, e.g. AbilityDataClass at 0x5574E978 has body 0x5574E978-0x5574E97A (3 bytes, Ghidra-confirmed), and 0x5574E990/994/998/99C/9A0 (GetAttack/GetDefense/GetResistance/GetDamage/GetMoveTypes) sit 4 bytes apart — base implementations that return a constant and exist purely to be overridden. Hooking these by displacing bytes will run into the neighbouring function.

FIELD EVIDENCE for instance size 0x24: TAbility.Create writes +0x10 (TStringList), +0x18 (TSFXLibra
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `EngineP.dpl!Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `EngineP.dpl!Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `EngineP.dpl!Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `EngineP.dpl!Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `EngineP.dpl!Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x5574F07C` | `AoWE.TAbility.ReadWrite@23EDC2EF` | TAbility (override of TEObject.ReadWrite) |
| `0x1C` | `0x55703104` | `EngineP.dpl!Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5574E5F4` | `AoWE.TAbility.Create@23EDC2EF` | TAbility (override of TEObject.Create, virtual constructor) |
| `0x24` | `0x55703094` | `EngineP.dpl!Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x28` | `0x5570307C` | `EngineP.dpl!Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `EngineP.dpl!Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `EngineP.dpl!Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `EngineP.dpl!Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `EngineP.dpl!Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `EngineP.dpl!Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `EngineP.dpl!Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `EngineP.dpl!Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `EngineP.dpl!Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5574EF2C` | `AoWE.TAbility.Execute@23EDC2EF` | TAbility |
| `0x50` | `0x5574E9AC` | `AoWE.TAbility.GetHidden@23EDC2EF` | TAbility |
| `0x54` | `0x5574EF1C` | `AoWE.TAbility.GetAbilityType@23EDC2EF` | TAbility |
| `0x58` | `0x5574E97C` | `AoWE.TAbility.GetName@23EDC2EF` | TAbility |
| `0x5C` | `0x5574E990` | `AoWE.TAbility.GetAttack@23EDC2EF` | TAbility |
| `0x60` | `0x5574E994` | `AoWE.TAbility.GetDefense@23EDC2EF` | TAbility |
| `0x64` | `0x5574E998` | `AoWE.TAbility.GetResistance@23EDC2EF` | TAbility |
| `0x68` | `0x5574E99C` | `AoWE.TAbility.GetDamage@23EDC2EF` | TAbility |
| `0x6C` | `0x5574E9A0` | `AoWE.TAbility.GetMoveTypes@23EDC2EF` | TAbility |
| `0x70` | `0x5574E9B0` | `AoWE.TAbility.GetLevel@23EDC2EF` | TAbility |
| `0x74` | `0x5574EEF4` | `AoWE.TAbility.GetEnabled@23EDC2EF` | TAbility |
| `0x78` | `0x5574EF00` | `AoWE.TAbility.GetImmunityTypes@23EDC2EF` | TAbility |
| `0x7C` | `0x5574EF0C` | `AoWE.TAbility.GetProtectionTypes@23EDC2EF` | TAbility |
| `0x80` | `0x5574E958` | `AoWE.TAbility.GetSkillPoints@23EDC2EF` | TAbility |
| `0x84` | `0x5574E73C` | `AoWE.TAbility.GetCombatMode@23EDC2EF` | TAbility |
| `0x88` | `0x5574E8AC` | `AoWE.TAbility.GetWallCombatFeatures@23EDC2EF` | TAbility |
| `0x8C` | `0x5574E704` | `AoWE.TAbility.GetSourceName@23EDC2EF` | TAbility |
| `0x90` | `0x5574E948` | `AoWE.TAbility.GetInherent@23EDC2EF` | TAbility |
| `0x94` | `0x5574E954` | `AoWE.TAbility.GetInherentLevel@23EDC2EF` | TAbility |
| `0x98` | `0x5574E730` | `AoWE.TAbility.GetControlType@23EDC2EF` | TAbility |
| `0x9C` | `0x5574E784` | `AoWE.TAbility.fcValidRoundDistance@23EDC2EF` | TAbility |
| `0xA0` | `0x5574EF24` | `AoWE.TAbility.fcPrefetchCombatCommands@23EDC2EF` | TAbility |
| `0xA4` | `0x5574EF28` | `AoWE.TAbility.fcExecuteCombatCommand@23EDC2EF` | TAbility |
| `0xA8` | `0x5574EF30` | `AoWE.TAbility.NewDay@23EDC2EF` | TAbility |
| `0xAC` | `0x5574EF34` | `AoWE.TAbility.NewTurn@23EDC2EF` | TAbility |
| `0xB0` | `0x5574EF40` | `AoWE.TAbility.CanActivate@23EDC2EF` | TAbility |
| `0xB4` | `0x5574EF68` | `AoWE.TAbility.Activate@23EDC2EF` | TAbility |
| `0xB8` | `0x5574EFDC` | `AoWE.TAbility.CanActivateCombat@23EDC2EF` | TAbility |
| `0xBC` | `0x5574F004` | `AoWE.TAbility.ActivateCombat@23EDC2EF` | TAbility |
| `0xC0` | `0x5574EF18` | `AoWE.TAbility.ListSpells@23EDC2EF` | TAbility |
| `0xC4` | `0x5574E8B8` | `AoWE.TAbility.CanExpand@23EDC2EF` | TAbility |
| `0xC8` | `0x5574E908` | `AoWE.TAbility.ExpandCost@23EDC2EF` | TAbility |
| `0xCC` | `0x5574E8F4` | `AoWE.TAbility.ExpandName@23EDC2EF` | TAbility |
| `0xD0` | `0x5574E90C` | `AoWE.TAbility.Expand@23EDC2EF` | TAbility |
| `0xD4` | `0x5574E91C` | `AoWE.TAbility.Remove@23EDC2EF` | TAbility |
| `0xD8` | `0x5574E740` | `AoWE.TAbility.GetDamageValue@23EDC2EF` | TAbility |
| `0xDC` | `0x5574E744` | `AoWE.TAbility.GetDamageValueEx@23EDC2EF` | TAbility |
| `0xE0` | `0x5574E9B4` | `AoWE.TAbility.GetOffensiveStrength@23EDC2EF` | TAbility |
| `0xE4` | `0x5574E764` | `AoWE.TAbility.fcGetDamageValueEx@23EDC2EF` | TAbility |
| `0xE8` | `0x5574E814` | `AoWE.TAbility.fcGetDamageValue@23EDC2EF` | TAbility |
| `0xEC` | `0x5574E844` | `AoWE.TAbility.tcGetDamageValueEx@23EDC2EF` | TAbility |
| `0xF0` | `0x5574E868` | `AoWE.TAbility.tcGetDamageValue@23EDC2EF` | TAbility |
| `0xF4` | `0x5574EF20` | `AoWE.TAbility.CombatObjectDestroyed@23EDC2EF` | TAbility |
| `0xF8` | `0x5574EF38` | `AoWE.TAbility.NewCombatTurn@23EDC2EF` | TAbility |
| `0xFC` | `0x5574EF3C` | `AoWE.TAbility.CombatDone@23EDC2EF` | TAbility |
| `0x100` | `0x5574E9D0` | `AoWE.TAbility.ListInfo@23EDC2EF` | TAbility |
| `0x104` | `0x5574E88C` | `AoWE.TAbility.GetCombatInfo@23EDC2EF` | TAbility |
| `0x108` | `0x5574E978` | `AoWE.TAbility.AbilityDataClass@23EDC2EF` | TAbility |

### TAbstractUnit  —  VMT `0x55710740`, instance `0x3C`, 110 slots, ends `0x1B8`

<details><summary>derivation notes</summary>

```
METHOD / GROUND TRUTH
AoWEPACK.dpl is a Delphi 3 runtime *package*: its .edata exports 10036 named symbols covering every method, so the export directory IS a complete symbol table. I parsed it directly out of "Modding Resources/AoWEPACK_original_backup.dpl" (the same pristine bytes Ghidra holds) and mapped VMT slot -> export name. Cross-checked 4 slots against Ghidra get_function_by_address (0x5577F524 SetOwner, 0x5577FD90 GetAttack, 0x5578091C Animate, 0x5574FC3C TAbilityOwner.GetAbAttack) - all 4 exact matches. No slot is a guess; every one of the 110 has a real RTTI symbol.

VMT EXTENT
VMT = 0x55710740, 110 slots, +0x000..+0x1B4 inclusive. Ends at +0x1B8: the dword there is 0x6241540D, which is not a pointer but the class-name ShortString itself (0x0D = len 13, then "TAb..") at 0x557108F8 - i.e. the name string sits immediately after the VMT. This is the same end-of-VMT signature as the TAoWHexagon case in the brief.

ANCESTOR CHAIN (via [VMT-0x18] -> classref ptr)
TAbstractUnit (VMT 0x55710740, inst 0x3C)
  -> TAbilityOwner (VMT 0x5570F588, inst 0x14, VMT 39 slots, ends +0x09C)
  -> TCustomAbilityList (VMT 0x5570F3DC, inst 0x10, VMT 23 slots, ends +0x05C)
  -> Engine.TEObject -- IMPORTED, lives in EngineP.dpl, NOT in this DLL.
TCustomAbilityList's vmtParent points at IAT slot 0x558FC92C = "EngineP.dpl!Engine..TEObject@BD8FE92F". A naive parent-walk therefore stops at TCustomAbilityList; the root is in another module.

THE 12 "UNNAMED" SLOTS ARE IMPORT THUNKS, NOT UNKNOWNS
Slots 0x00,0x04,0x0C,0x10,0x14,0x1C,0x24,0x34,0x38,0x3C,0x40,0x48 point into a thunk table at 0x557030xx. Each is `FF 25 <iat>` = jmp dword ptr [IAT], + an 8BC0 (mov eax,eax) pad. Ghidra has NO function defined at those addresses (get_function_by_address returns "No function found") - so a Ghidra-only walk would report them as nameless. Resolving the IAT gives the true owner: all 12 are Engine.TEObject methods in EngineP.dpl. Symbols below are given in "EngineP.dpl!Engine.TEObject.X@hash" form; the "dll!" prefix marks the imported/thunked ones.

DELPHI 3 NEGATIVE HEADER (empirically confirmed, differs from Delphi 4+)
 -0x40 vmtSelfPtr      = 0x55710740 (the VMT itself; also exported as classref "AoWE..TAbstractUnit@B010B7CB")
 -0x3C..-0x24          = 0 (IntfTable/AutoTable/InitTable/TypeInfo/FieldTable/MethodTable/DynamicTable all null)
 -0x20 vmtClassName    = 0x557108F8
 -0x1C vmtInstanceSize = 0x3C
 -0x18 vmtParent       = 0x5570F548
 -0x14 SafeCallException = 0x557010C8  VCL30.dpl!System.TObject.SafeCallException
 -0x10 DefaultHandler    = 0x557010D0  VCL30.dpl!System.TObject.DefaultHandler
 -0x0C NewInstance       = 0x55701098  VCL30.dpl!System.TObject.NewInstance
 -0x08 FreeInstance      = 0x557010A0  VCL30.dpl!System.TObject.FreeInstance
 -0x04 Destroy           = 0x5577EB6C  AoWE.TAbstractUnit.Destroy@23EDC2EF
IMPORTANT FOR HOOKING: Destroy is at VMT-0x04, a NEGATIVE offset - it is not in the positive slot table. Delphi 3 has no AfterConstruction/BeforeDestruction/Dispatch entries.

WHO INTRODUCED EACH SLOT (derived from the ancestors' own VMT lengths, which are exactly the boundaries)
  +0x000..+0x048 (19 slots) introduced by TEObject
  +0x04C..+0x058 ( 4 slots) introduced by TCustomAbilityList
  +0x05C..+0x098 (16 slots) introduced by TAbilityOwner
  +0x09C..+0x1B4 (71 slots) NEW virtuals introduced by TAbstractUnit
  = 110 total.

WHO IMPLEMENTS EACH SLOT (the "owner" field below)
  TAbstractUnit 81, TAbilityOwner 15, TEObject 12, TCustomAbilityList 2.
TAbstractUnit's 81 = 71 new + 10 OVERRIDES of inherited slots:
  overriding TEObject:      +0x08 SetOwner, +0x18 ReadWrite, +0x20 Create, +0x28 AddRef, +0x2C Release, +0x44 MsgProc
  overriding TAbilityOwner: +0x60 GetOwnerName, +0x8C GetAbilitySelectionTypes, +0x90 Changed, +0x98 RemoveAbility
Note TAbstractUnit does NOT override Clear (+0x30 stays TAbilityOwner.Clear), nor GetAbSet/GetAbCount (+0x4C/+0x54 stay TCustomAbilityList) - those two are the only slots still implemented by TCustomAbili
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `EngineP.dpl!Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x5577F524` | `AoWE.TAbstractUnit.SetOwner@23EDC2EF` | TAbstractUnit |
| `0x0C` | `0x557030D4` | `EngineP.dpl!Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `EngineP.dpl!Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `EngineP.dpl!Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557820E4` | `AoWE.TAbstractUnit.ReadWrite@23EDC2EF` | TAbstractUnit |
| `0x1C` | `0x55703104` | `EngineP.dpl!Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5577EB28` | `AoWE.TAbstractUnit.Create@23EDC2EF` | TAbstractUnit |
| `0x24` | `0x55703094` | `EngineP.dpl!Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x28` | `0x5577EBC4` | `AoWE.TAbstractUnit.AddRef@23EDC2EF` | TAbstractUnit |
| `0x2C` | `0x5577EBCC` | `AoWE.TAbstractUnit.Release@23EDC2EF` | TAbstractUnit |
| `0x30` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x34` | `0x557030BC` | `EngineP.dpl!Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `EngineP.dpl!Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `EngineP.dpl!Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `EngineP.dpl!Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x55781238` | `AoWE.TAbstractUnit.MsgProc@23EDC2EF` | TAbstractUnit |
| `0x48` | `0x557030EC` | `EngineP.dpl!Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5574E0E0` | `AoWE.TCustomAbilityList.GetAbSet@23EDC2EF` | TCustomAbilityList |
| `0x50` | `0x5574F308` | `AoWE.TAbilityOwner.SetAbSet@23EDC2EF` | TAbilityOwner |
| `0x54` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x58` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x5C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x60` | `0x5577F69C` | `AoWE.TAbstractUnit.GetOwnerName@23EDC2EF` | TAbstractUnit |
| `0x64` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x68` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x6C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x70` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x74` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x78` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x7C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x80` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x84` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x88` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x8C` | `0x5577ECC0` | `AoWE.TAbstractUnit.GetAbilitySelectionTypes@23EDC2EF` | TAbstractUnit |
| `0x90` | `0x55780FA8` | `AoWE.TAbstractUnit.Changed@23EDC2EF` | TAbstractUnit |
| `0x94` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x98` | `0x5577F6EC` | `AoWE.TAbstractUnit.RemoveAbility@23EDC2EF` | TAbstractUnit |
| `0x9C` | `0x5577FC64` | `AoWE.TAbstractUnit.GetUpkeep@23EDC2EF` | TAbstractUnit |
| `0xA0` | `0x5577FCC8` | `AoWE.TAbstractUnit.GetUnitLevel@23EDC2EF` | TAbstractUnit |
| `0xA4` | `0x5577EDDC` | `AoWE.TAbstractUnit.GetRace@23EDC2EF` | TAbstractUnit |
| `0xA8` | `0x5577FD8C` | `AoWE.TAbstractUnit.GetInherentAttack@23EDC2EF` | TAbstractUnit |
| `0xAC` | `0x5577FD94` | `AoWE.TAbstractUnit.GetInherentDefense@23EDC2EF` | TAbstractUnit |
| `0xB0` | `0x5577FD9C` | `AoWE.TAbstractUnit.GetInherentDamage@23EDC2EF` | TAbstractUnit |
| `0xB4` | `0x5577FDA4` | `AoWE.TAbstractUnit.GetInherentResistance@23EDC2EF` | TAbstractUnit |
| `0xB8` | `0x5577F570` | `AoWE.TAbstractUnit.GetInherentAbility@23EDC2EF` | TAbstractUnit |
| `0xBC` | `0x5577F5A8` | `AoWE.TAbstractUnit.GetInherentAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0xC0` | `0x5577FD90` | `AoWE.TAbstractUnit.GetAttack@23EDC2EF` | TAbstractUnit |
| `0xC4` | `0x5577FD98` | `AoWE.TAbstractUnit.GetDefense@23EDC2EF` | TAbstractUnit |
| `0xC8` | `0x5577FDA0` | `AoWE.TAbstractUnit.GetDamage@23EDC2EF` | TAbstractUnit |
| `0xCC` | `0x5577FDA8` | `AoWE.TAbstractUnit.GetResistance@23EDC2EF` | TAbstractUnit |
| `0xD0` | `0x5577FDAC` | `AoWE.TAbstractUnit.GetHits@23EDC2EF` | TAbstractUnit |
| `0xD4` | `0x5577FDB0` | `AoWE.TAbstractUnit.GetMoves@23EDC2EF` | TAbstractUnit |
| `0xD8` | `0x5577FCD0` | `AoWE.TAbstractUnit.GetMovePoints@23EDC2EF` | TAbstractUnit |
| `0xDC` | `0x5577FCD4` | `AoWE.TAbstractUnit.SetMovePoints@23EDC2EF` | TAbstractUnit |
| `0xE0` | `0x5577FCD8` | `AoWE.TAbstractUnit.GetHitPoints@23EDC2EF` | TAbstractUnit |
| `0xE4` | `0x5577FCDC` | `AoWE.TAbstractUnit.SetHitPoints@23EDC2EF` | TAbstractUnit |
| `0xE8` | `0x5577FFD0` | `AoWE.TAbstractUnit.GetMoveTypes@23EDC2EF` | TAbstractUnit |
| `0xEC` | `0x5577FD54` | `AoWE.TAbstractUnit.GetImmunityTypes@23EDC2EF` | TAbstractUnit |
| `0xF0` | `0x5577FD74` | `AoWE.TAbstractUnit.GetProtectionTypes@23EDC2EF` | TAbstractUnit |
| `0xF4` | `0x5577FFE4` | `AoWE.TAbstractUnit.GetFace@23EDC2EF` | TAbstractUnit |
| `0xF8` | `0x5577FFE8` | `AoWE.TAbstractUnit.GetName@23EDC2EF` | TAbstractUnit |
| `0xFC` | `0x5577FC60` | `AoWE.TAbstractUnit.GetAlignment@23EDC2EF` | TAbstractUnit |
| `0x100` | `0x5577FFF4` | `AoWE.TAbstractUnit.GetPreviewImage@23EDC2EF` | TAbstractUnit |
| `0x104` | `0x5577FCCC` | `AoWE.TAbstractUnit.GetTransportCapacity@23EDC2EF` | TAbstractUnit |
| `0x108` | `0x5577FD40` | `AoWE.TAbstractUnit.GetTransporter@23EDC2EF` | TAbstractUnit |
| `0x10C` | `0x55780878` | `AoWE.TAbstractUnit.GetGender@23EDC2EF` | TAbstractUnit |
| `0x110` | `0x5577EBB4` | `AoWE.TAbstractUnit.GetBloodType@23EDC2EF` | TAbstractUnit |
| `0x114` | `0x5577FD88` | `AoWE.TAbstractUnit.GetUnitType@23EDC2EF` | TAbstractUnit |
| `0x118` | `0x5577FFF8` | `AoWE.TAbstractUnit.GetUnitGFXResourceIndex@23EDC2EF` | TAbstractUnit |
| `0x11C` | `0x55781208` | `AoWE.TAbstractUnit.CanAddToList@23EDC2EF` | TAbstractUnit |
| `0x120` | `0x5577ECCC` | `AoWE.TAbstractUnit.GetWallCombatFeatures@23EDC2EF` | TAbstractUnit |
| `0x124` | `0x5577EBB8` | `AoWE.TAbstractUnit.GetCampaignTransferPoints@23EDC2EF` | TAbstractUnit |
| `0x128` | `0x5577FDB8` | `AoWE.TAbstractUnit.GetCastingPointsMax@23EDC2EF` | TAbstractUnit |
| `0x12C` | `0x5577FDBC` | `AoWE.TAbstractUnit.GetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x130` | `0x5577FDC0` | `AoWE.TAbstractUnit.SetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x134` | `0x5577FDB4` | `AoWE.TAbstractUnit.GetPowerGeneration@23EDC2EF` | TAbstractUnit |
| `0x138` | `0x5578120C` | `AoWE.TAbstractUnit.NewDay@23EDC2EF` | TAbstractUnit |
| `0x13C` | `0x55780D4C` | `AoWE.TAbstractUnit.NewTurn@23EDC2EF` | TAbstractUnit |
| `0x140` | `0x55780E28` | `AoWE.TAbstractUnit.NewTurnDone@23EDC2EF` | TAbstractUnit |
| `0x144` | `0x5577F658` | `AoWE.TAbstractUnit.GetAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x148` | `0x5577F5E0` | `AoWE.TAbstractUnit.GetAbilityEnabled@23EDC2EF` | TAbstractUnit |
| `0x14C` | `0x5577F618` | `AoWE.TAbstractUnit.GetAbilitySet@23EDC2EF` | TAbstractUnit |
| `0x150` | `0x5577F630` | `AoWE.TAbstractUnit.GetAbilityName@23EDC2EF` | TAbstractUnit |
| `0x154` | `0x5577F67C` | `AoWE.TAbstractUnit.GetAbilityOwner@23EDC2EF` | TAbstractUnit |
| `0x158` | `0x5577F56C` | `AoWE.TAbstractUnit.GetAbilityCount@23EDC2EF` | TAbstractUnit |
| `0x15C` | `0x5577FBA0` | `AoWE.TAbstractUnit.GetExperience@23EDC2EF` | TAbstractUnit |
| `0x160` | `0x5577FBA4` | `AoWE.TAbstractUnit.SetExperience@23EDC2EF` | TAbstractUnit |
| `0x164` | `0x5577FBA8` | `AoWE.TAbstractUnit.GetNextLevelExperience@23EDC2EF` | TAbstractUnit |
| `0x168` | `0x5577FB98` | `AoWE.TAbstractUnit.GetDescription@23EDC2EF` | TAbstractUnit |
| `0x16C` | `0x5577F4A8` | `AoWE.TAbstractUnit.SetPlayer@23EDC2EF` | TAbstractUnit |
| `0x170` | `0x5577F4F4` | `AoWE.TAbstractUnit.GetIndependentRelation@23EDC2EF` | TAbstractUnit |
| `0x174` | `0x5577F188` | `AoWE.TAbstractUnit.GetObtainValue@23EDC2EF` | TAbstractUnit |
| `0x178` | `0x5577F184` | `AoWE.TAbstractUnit.GetUnitSize@23EDC2EF` | TAbstractUnit |
| `0x17C` | `0x5577EED8` | `AoWE.TAbstractUnit.GetUnitMoraleValue@23EDC2EF` | TAbstractUnit |
| `0x180` | `0x5577FB9C` | `AoWE.TAbstractUnit.CanActivate@23EDC2EF` | TAbstractUnit |
| `0x184` | `0x5577FBAC` | `AoWE.TAbstractUnit.Activate@23EDC2EF` | TAbstractUnit |
| `0x188` | `0x5577FC20` | `AoWE.TAbstractUnit.Deactivate@23EDC2EF` | TAbstractUnit |
| `0x18C` | `0x55780328` | `AoWE.TAbstractUnit.MovedTo@23EDC2EF` | TAbstractUnit |
| `0x190` | `0x557825B0` | `AoWE.TAbstractUnit.CanDisband@23EDC2EF` | TAbstractUnit |
| `0x194` | `0x557821AC` | `AoWE.TAbstractUnit.CanJoin@23EDC2EF` | TAbstractUnit |
| `0x198` | `0x55782324` | `AoWE.TAbstractUnit.JoinAmount@23EDC2EF` | TAbstractUnit |
| `0x19C` | `0x55782364` | `AoWE.TAbstractUnit.OfferToJoin@23EDC2EF` | TAbstractUnit |
| `0x1A0` | `0x55782440` | `AoWE.TAbstractUnit.GetJoinMessage@23EDC2EF` | TAbstractUnit |
| `0x1A4` | `0x557812EC` | `AoWE.TAbstractUnit.ShowEx@23EDC2EF` | TAbstractUnit |
| `0x1A8` | `0x5577FD3C` | `AoWE.TAbstractUnit.UnitKilled@23EDC2EF` | TAbstractUnit |
| `0x1AC` | `0x5578087C` | `AoWE.TAbstractUnit.Killed@23EDC2EF` | TAbstractUnit |
| `0x1B0` | `0x557808DC` | `AoWE.TAbstractUnit.Resurrect@23EDC2EF` | TAbstractUnit |
| `0x1B4` | `0x5578091C` | `AoWE.TAbstractUnit.Animate@23EDC2EF` | TAbstractUnit |

### TAoWHSMap  —  VMT `0x5570E874`, instance `0x41C`, 76 slots, ends `0x130`

<details><summary>derivation notes</summary>

```
DERIVED, NOT GUESSED. Source of truth = the DPL's own PE export + import tables, cross-checked against Ghidra (AoWEPACK_vanilla.dpl). All 76 slots resolved; ZERO slots have an unknown symbol.

== VMT LOCATION / IDENTITY ==
VMT = 0x5570E874 (CODE section; module preferred base 0x55700000, so file-relative RVA 0xE874 -> file offset 0xE274). Independently confirmed three ways:
 1. [VMT-0x20] = 0x5570E9C6 -> ShortString "\x09TAoWHSMap".
 2. [VMT-0x40] (vmtSelfPtr) = 0x5570E874, i.e. points at itself.
 3. The DPL EXPORTS the classref at that exact address as "AoWE..TAoWHSMap@2F9CE523" (Delphi's Unit..Class@hash form). Only one candidate VMT exists for this name.
Instance size [VMT-0x1C] = 0x41C (1052 bytes).

== WHERE THE VMT ENDS (hard boundary, not a guess) ==
Last valid slot is +0x12C. VMT+0x130 = 0x5570E9A4, which is exactly the pointer stored in [VMT-0x34] (vmtInitTable) — the class's RTTI managed-field table. Its first dword reads 0x0000000E (tkRecord in the Delphi-3 TTypeKind numbering), which is why the walk stops: it is data, not a code pointer. So the VMT occupies 0x5570E874..0x5570E9A4 = 0x130 bytes = 76 slots, then the init table (0x22 bytes), then the class-name ShortString at 0x5570E9C6.

== ANCESTRY (from [VMT-0x18], which is a PClass i.e. pointer-to-classref) ==
TAoWHSMap (AoWE, VMT 0x5570E874, instsize 0x41C)
  -> TAbstractAoWHSMap (AoWE, VMT 0x5570E37C, instsize 0xD8, Destroy 0x55772338)
     -> HSEngine.THSMap  [external: TAbstractAoWHSMap's vmtParent slot is IAT 0x558FC15C = HSEPack.dpl!"HSEngine..THSMap@EA8E2427", so the chain leaves this module here]
        -> ... Engine.TENode / Engine.TECustomNode / Engine.TEObject (EngineP.dpl) -> System.TObject (VCL30.dpl)
TAbstractAoWHSMap's own VMT ends at +0x118, so TAoWHSMap's slots +0x118..+0x12C (6 entries) are NEWLY INTRODUCED virtuals; every other TAoWHSMap-owned slot is an override.

== HOW INHERITED SLOTS WERE RESOLVED (important for readers) ==
Slots whose target lands in 0x55702400-0x55703300 are NOT functions in this module — they are 6-byte Delphi package import thunks "JMP dword ptr [IAT]". Verified in Ghidra: 0x55703074 = ff2524c78f55 -> JMP [0x558FC724]; 0x5570262C = ff2508bc8f55 -> JMP [0x558FBC08]. Ghidra reports "No function found" at these addresses (it never made functions in the thunk region), so the names above come from the PE import table, which is equally authoritative. Unit prefix tells you the module: Engine.* = EngineP.dpl, HSEngine.* = HSEPack.dpl, System.* = VCL30.dpl. Every one of the 40 non-export slots was confirmed to start with FF 25 and to hit a named IAT entry — none are unnamed ordinals.

== SLOT OWNERSHIP TALLY (76 total) ==
TAoWHSMap 23 | TAbstractAoWHSMap 13 | HSEngine.THSMap 14 (HSEPack.dpl) | Engine.TEObject 11 | Engine.TENode 8 | Engine.TECustomNode 7 (all EngineP.dpl).

== NEGATIVE HEADER (Delphi 3 layout, confirmed byte-for-byte against Ghidra at 0x5570E834) ==
 -0x40 vmtSelfPtr        = 0x5570E874  (export "AoWE..TAoWHSMap@2F9CE523")
 -0x3C vmtIntfTable      = 0
 -0x38 vmtAutoTable      = 0
 -0x34 vmtInitTable      = 0x5570E9A4  (tkRecord; 3 managed fields, all System.String — typeinfo via IAT 0x558FB72C = VCL30.dpl!"System.String@44481A84" — at instance offsets +0xE4, +0xE8, +0x178. Since the parent's instsize is 0xD8, all three are TAoWHSMap's own fields.)
 -0x30 vmtTypeInfo       = 0
 -0x2C vmtFieldTable     = 0
 -0x28 vmtMethodTable    = 0  (no published methods)
 -0x24 vmtDynamicTable   = 0  (NO dynamic/message methods on this class — relevant if you were hoping to hook a message handler here; message dispatch goes through MsgProc at +0x044 instead)
 -0x20 vmtClassName      = 0x5570E9C6 -> "TAoWHSMap"
 -0x1C vmtInstanceSize   = 0x41C
 -0x18 vmtParent         = 0x5570E33C -> [.] = 0x5570E37C (TAbstractAoWHSMap)
 -0x14 SafeCallException = 0x557010C8  thunk -> VCL30.dpl!System.TObject.SafeCallException@23EDC2EF
 -0x10 DefaultHandler    = 0x557010D0  thunk -> VCL30.dpl!System.TObject.DefaultHandler@23EDC2EF
 -0x0C NewInsta
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x55702534` | `HSEngine.THSMap.GetControlStyle@23EDC2EF` | THSMap |
| `0x008` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x55776D60` | `AoWE.TAoWHSMap.ReadWrite@23EDC2EF` | TAoWHSMap |
| `0x01C` | `0x557772A0` | `AoWE.TAoWHSMap.MainReadWrite@23EDC2EF` | TAoWHSMap |
| `0x020` | `0x557748A4` | `AoWE.TAoWHSMap.Create@23EDC2EF` | TAoWHSMap |
| `0x024` | `0x557773C4` | `AoWE.TAoWHSMap.ClassID@23EDC2EF` | TAoWHSMap |
| `0x028` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x02C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x030` | `0x5570253C` | `HSEngine.THSMap.Clear@23EDC2EF` | THSMap |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x55703144` | `Engine.TECustomNode.Assign@23EDC2EF` | TECustomNode |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x55778498` | `AoWE.TAoWHSMap.MsgProc@23EDC2EF` | TAoWHSMap |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x557031CC` | `Engine.TENode.GetChild@23EDC2EF` | TENode |
| `0x050` | `0x557031D4` | `Engine.TENode.SetChild@23EDC2EF` | TENode |
| `0x054` | `0x557031DC` | `Engine.TENode.GetCount@23EDC2EF` | TENode |
| `0x058` | `0x55703154` | `Engine.TECustomNode.ReadWriteChildren@23EDC2EF` | TECustomNode |
| `0x05C` | `0x5570316C` | `Engine.TECustomNode.SendToChild@23EDC2EF` | TECustomNode |
| `0x060` | `0x557031B4` | `Engine.TENode.DestroyAllChildren@23EDC2EF` | TENode |
| `0x064` | `0x5570314C` | `Engine.TECustomNode.QuickClear@23EDC2EF` | TECustomNode |
| `0x068` | `0x5577855C` | `AoWE.TAoWHSMap.SendMsg@23EDC2EF` | TAoWHSMap |
| `0x06C` | `0x557031EC` | `Engine.TENode.RemoveChild@23EDC2EF` | TENode |
| `0x070` | `0x557031F4` | `Engine.TENode.AddChild@23EDC2EF` | TENode |
| `0x074` | `0x5570319C` | `Engine.TECustomNode.DestroyChildren@23EDC2EF` | TECustomNode |
| `0x078` | `0x55703194` | `Engine.TECustomNode.FindChildInTree@23EDC2EF` | TECustomNode |
| `0x07C` | `0x557031FC` | `Engine.TENode.FindChild@23EDC2EF` | TENode |
| `0x080` | `0x55703184` | `Engine.TECustomNode.FindOwnedChild@23EDC2EF` | TECustomNode |
| `0x084` | `0x55703204` | `Engine.TENode.FindChildIndex@23EDC2EF` | TENode |
| `0x088` | `0x55775938` | `AoWE.TAoWHSMap.CreateMouse@23EDC2EF` | TAoWHSMap |
| `0x08C` | `0x557769DC` | `AoWE.TAoWHSMap.NotifyProgress@23EDC2EF` | TAoWHSMap |
| `0x090` | `0x55777590` | `AoWE.TAoWHSMap.InitializeNewMap@23EDC2EF` | TAoWHSMap |
| `0x094` | `0x557724EC` | `AoWE.TAbstractAoWHSMap.TriggerTerrainChangedEvent@23EDC2EF` | TAbstractAoWHSMap |
| `0x098` | `0x5570262C` | `HSEngine.THSMap.DrawStaticHS@23EDC2EF` | THSMap |
| `0x09C` | `0x55702644` | `HSEngine.THSMap.DrawDynamicHS@23EDC2EF` | THSMap |
| `0x0A0` | `0x55702634` | `HSEngine.THSMap.DrawStaticHSEx@23EDC2EF` | THSMap |
| `0x0A4` | `0x5570264C` | `HSEngine.THSMap.DrawDynamicHSEx@23EDC2EF` | THSMap |
| `0x0A8` | `0x557025C4` | `HSEngine.THSMap.FillLevelWithResource@23EDC2EF` | THSMap |
| `0x0AC` | `0x55777684` | `AoWE.TAoWHSMap.AddMapLevel@23EDC2EF` | TAoWHSMap |
| `0x0B0` | `0x55778000` | `AoWE.TAoWHSMap.Activate@23EDC2EF` | TAoWHSMap |
| `0x0B4` | `0x55702554` | `HSEngine.THSMap.Deactivate@23EDC2EF` | THSMap |
| `0x0B8` | `0x5570256C` | `HSEngine.THSMap.ViewLevel@23EDC2EF` | THSMap |
| `0x0BC` | `0x5570255C` | `HSEngine.THSMap.CenterViewTo@23EDC2EF` | THSMap |
| `0x0C0` | `0x55702564` | `HSEngine.THSMap.ChangeViewTo@23EDC2EF` | THSMap |
| `0x0C4` | `0x557025FC` | `HSEngine.THSMap.GetViewCenter@23EDC2EF` | THSMap |
| `0x0C8` | `0x55702574` | `HSEngine.THSMap.MakeVisible@23EDC2EF` | THSMap |
| `0x0CC` | `0x557776BC` | `AoWE.TAoWHSMap.CreateNewMap@23EDC2EF` | TAoWHSMap |
| `0x0D0` | `0x55778D84` | `AoWE.TAoWHSMap.ChangeTerrain@23EDC2EF` | TAoWHSMap |
| `0x0D4` | `0x55778DCC` | `AoWE.TAoWHSMap.ChangeTerrainEx@23EDC2EF` | TAoWHSMap |
| `0x0D8` | `0x55773544` | `AoWE.TAbstractAoWHSMap.UpdateStaticScene@23EDC2EF` | TAbstractAoWHSMap |
| `0x0DC` | `0x55773624` | `AoWE.TAbstractAoWHSMap.UpdateDynamicScene@23EDC2EF` | TAbstractAoWHSMap |
| `0x0E0` | `0x5570263C` | `HSEngine.THSMap.DrawStaticScene@23EDC2EF` | THSMap |
| `0x0E4` | `0x55778A60` | `AoWE.TAoWHSMap.DrawDynamicScene@23EDC2EF` | TAoWHSMap |
| `0x0E8` | `0x55777CE8` | `AoWE.TAoWHSMap.NewFrame@23EDC2EF` | TAoWHSMap |
| `0x0EC` | `0x557732F4` | `AoWE.TAbstractAoWHSMap.ShowBackHexagonSelector@23EDC2EF` | TAbstractAoWHSMap |
| `0x0F0` | `0x5577338C` | `AoWE.TAbstractAoWHSMap.ShowFrontHexagonSelector@23EDC2EF` | TAbstractAoWHSMap |
| `0x0F4` | `0x55773424` | `AoWE.TAbstractAoWHSMap.UpdateHexagonSelector@23EDC2EF` | TAbstractAoWHSMap |
| `0x0F8` | `0x55775948` | `AoWE.TAoWHSMap.SetSeatedPlayer@23EDC2EF` | TAoWHSMap |
| `0x0FC` | `0x55772A80` | `AoWE.TAbstractAoWHSMap.SetCurrentPlayer@23EDC2EF` | TAbstractAoWHSMap |
| `0x100` | `0x557723C0` | `AoWE.TAbstractAoWHSMap.SetFogEnabled@23EDC2EF` | TAbstractAoWHSMap |
| `0x104` | `0x557723D4` | `AoWE.TAbstractAoWHSMap.SetExplorationEnabled@23EDC2EF` | TAbstractAoWHSMap |
| `0x108` | `0x55773770` | `AoWE.TAbstractAoWHSMap.DropHeroItem@23EDC2EF` | TAbstractAoWHSMap |
| `0x10C` | `0x557737A8` | `AoWE.TAbstractAoWHSMap.GetHeroItemsOnGround@23EDC2EF` | TAbstractAoWHSMap |
| `0x110` | `0x557729B4` | `AoWE.TAbstractAoWHSMap.ShowMessage@23EDC2EF` | TAbstractAoWHSMap |
| `0x114` | `0x557728F0` | `AoWE.TAbstractAoWHSMap.ShowWarning@23EDC2EF` | TAbstractAoWHSMap |
| `0x118` | `0x557763D4` | `AoWE.TAoWHSMap.TriggerCombatEvent@23EDC2EF` | TAoWHSMap |
| `0x11C` | `0x557763E0` | `AoWE.TAoWHSMap.TriggerGameTerminatedEvent@23EDC2EF` | TAoWHSMap |
| `0x120` | `0x55776684` | `AoWE.TAoWHSMap.TriggerPlayerTerminatedEvent@23EDC2EF` | TAoWHSMap |
| `0x124` | `0x55777D68` | `AoWE.TAoWHSMap.StartNewMap@23EDC2EF` | TAoWHSMap |
| `0x128` | `0x55777F10` | `AoWE.TAoWHSMap.StartLoadedMap@23EDC2EF` | TAoWHSMap |
| `0x12C` | `0x55776624` | `AoWE.TAoWHSMap.TriggerExecuteEventLog@23EDC2EF` | TAoWHSMap |

### TAoWHexagon  —  VMT `0x5579A1D0`, instance `0x14`, 73 slots, ends `0x124`

<details><summary>derivation notes</summary>

```
DERIVATION. Class-name ShortString 0x0B "TAoWHexagon" at VA 5579A2F4; the dword pointing at it is at 5579A1B0, so VMT = 5579A1B0+0x20 = 5579A1D0. [VMT-0x20]=5579A2F4 (name), [VMT-0x1C]=0x14 (instance size), [VMT-0x18]=558FCD30 which is an IAT slot importing HSEPack.dpl!"Hexagon..THexagon@3C8222E0" -> parent class is THexagon. Exactly one VMT candidate exists for this name.

VMT END. Last valid slot is +0x120. VMT_VA+0x124 = 5579A2F4, which is byte-identical to the class-name ShortString itself (0x0B 'T''A''o' = dword 6F41540B, then 78654857 'WHex', 6E6F6761 'agon'). So the VMT occupies 5579A1D0..5579A2F3 = 0x124 bytes = 73 slots, and the class-name string sits immediately after it. This is the exact case the task warned about.

MOST SLOTS ARE IMPORT THUNKS, NOT REAL FUNCTIONS. 69 of 73 targets are 6-byte `JMP dword ptr [IAT]` stubs in AoWEPACK's own thunk block (55701D44-55703104 and 55799448-55799458), padded with `MOV EAX,EAX`. Ghidra has no function at those addresses (get_function_by_address returns "No function found") — the symbols below were derived by decoding the FF 25 operand and looking the IAT VA up in AoWEPACK.dpl's import directory, which names the exporting package and the full Delphi RTTI symbol. target_va is what the VMT slot literally contains (the thunk), which is the address you would overwrite to hook a slot; the real code lives in HSEPack.dpl / EngineP.dpl. Only the 4 TAoWHexagon overrides are real local functions with Ghidra symbols.

ANCESTOR CHAIN (walked through HSEPack.dpl's own VMTs, since Ghidra only holds AoWEPACK):
  TEObject         (EngineP.dpl, unit Engine)   - imported, VMT not local
  -> THexagonSprite   (HSEPack.dpl, unit HSEngine)  VMT=55603694 instsize=0x08 vmtlen=0x108 (66 slots)
  -> TMapObject       (HSEPack.dpl, unit HSEngine)  VMT=55604190 instsize=0x10 vmtlen=0x11C (71 slots)
  -> TAbstractHexagon (HSEPack.dpl, unit HSEngine)  VMT=556047CC instsize=0x10 vmtlen=0x120 (72 slots)
  -> THexagon         (HSEPack.dpl, unit Hexagon)   VMT=55611B10 instsize=0x14 vmtlen=0x124 (73 slots)
  -> TAoWHexagon      (AoWEPACK.dpl, unit AoWHex)   VMT=5579A1D0 instsize=0x14 vmtlen=0x124 (73 slots)
NOTE the chain order is the OPPOSITE of what the slot layout suggests: THexagonSprite is the BASE and TMapObject derives from it, not vice versa. Do not infer chain order from which owner appears at low offsets.

Slot introduction: TEObject introduces 0x00-0x48; THexagonSprite extends to 0x104; TMapObject introduces 0x108-0x118; TAbstractHexagon introduces 0x11C; THexagon introduces 0x120. TAoWHexagon introduces NOTHING - same vmtlen 0x124 and same instance size 0x14 as THexagon, so it adds no virtual methods and no fields. It is a pure behaviour-override subclass.

TAoWHexagon's 4 overrides, with the base implementation each one replaces (read out of THexagon's VMT in HSEPack.dpl):
  +0x09C ChangeTerrain            overrides HSEngine.TAbstractHexagon.ChangeTerrain (5560A548)
  +0x0A0 TerrainChanged           overrides HSEngine.TAbstractHexagon.TerrainChanged (5560A618)
  +0x0A4 NeighbourTerrainChanged  overrides Hexagon.THexagon.NeighbourTerrainChanged (55611DAC)
  +0x120 UpdateTransition         overrides Hexagon.THexagon.UpdateTransition (55611DE8)
Corroboration: Ghidra's search for "TAoWHexagon" returns exactly these four functions and no others, so no virtual method was missed. Slot-by-slot, TAoWHexagon's VMT is identical to THexagon's except at these four offsets.

Owner tally: TMapObject 32, TEObject 17, THexagonSprite 10, TAbstractHexagon 7, TAoWHexagon 4, THexagon 3 = 73.

Beware +0x11C UpdateTransitions (plural, THexagon, the driver) vs +0x120 UpdateTransition (singular, TAoWHexagon, the per-edge worker) - adjacent slots, one letter apart.

Scripts used (scratchpad, throwaway; nothing in the project was written or modified, and no mutating Ghidra tool was called):
  ...\scratchpad\hexvmt.py, hexvmt2.py, aowhex_chain_probe.py, aowhex_hsepack_slots.py, aowhex_emit.py
Source bytes: Modding Resources\A
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557021F4` | `HSEngine.TMapObject.ReadWrite@23EDC2EF` | TMapObject |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55703064` | `Engine.TEObject.Create@23EDC2EF` | TEObject |
| `0x24` | `0x55799448` | `Hexagon.THexagon.ClassID@23EDC2EF` | THexagon |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x557021B4` | `HSEngine.TMapObject.GetTerrain@23EDC2EF` | TMapObject |
| `0x50` | `0x557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `0x557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `0x557021CC` | `HSEngine.TMapObject.GetOverlay@23EDC2EF` | TMapObject |
| `0x5C` | `0x557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `0x557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `0x557022FC` | `HSEngine.TAbstractHexagon.GetLevel@23EDC2EF` | TAbstractHexagon |
| `0x68` | `0x55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `0x5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `0x557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `0x55702164` | `HSEngine.TMapObject.GetXhx@23EDC2EF` | TMapObject |
| `0x78` | `0x5570216C` | `HSEngine.TMapObject.GetYhx@23EDC2EF` | TMapObject |
| `0x7C` | `0x55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `0x55701DC4` | `HSEngine.THexagonSprite.GetXYL@23EDC2EF` | THexagonSprite |
| `0x84` | `0x5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `0x55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `0x557022F4` | `HSEngine.TAbstractHexagon.GetShowPriority@23EDC2EF` | TAbstractHexagon |
| `0x90` | `0x55702214` | `HSEngine.TMapObject.Connect@23EDC2EF` | TMapObject |
| `0x94` | `0x5570221C` | `HSEngine.TMapObject.Disconnect@23EDC2EF` | TMapObject |
| `0x98` | `0x55701E24` | `HSEngine.THexagonSprite.CanChangeTerrain@23EDC2EF` | THexagonSprite |
| `0x9C` | `0x5579A89C` | `AoWHex.TAoWHexagon.ChangeTerrain@23EDC2EF` | TAoWHexagon |
| `0xA0` | `0x5579A94C` | `AoWHex.TAoWHexagon.TerrainChanged@23EDC2EF` | TAoWHexagon |
| `0xA4` | `0x5579A864` | `AoWHex.TAoWHexagon.NeighbourTerrainChanged@23EDC2EF` | TAoWHexagon |
| `0xA8` | `0x55799450` | `Hexagon.THexagon.Show@23EDC2EF` | THexagon |
| `0xAC` | `0x5570222C` | `HSEngine.TMapObject.PlaceOnMap@23EDC2EF` | TMapObject |
| `0xB0` | `0x55702234` | `HSEngine.TMapObject.RemoveFromMap@23EDC2EF` | TMapObject |
| `0xB4` | `0x5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `0x55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `0x55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `0x557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `0x5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `0x55702224` | `HSEngine.TMapObject.Loaded@23EDC2EF` | TMapObject |
| `0xCC` | `0x5570233C` | `HSEngine.TAbstractHexagon.MapFieldMsgProc@23EDC2EF` | TAbstractHexagon |
| `0xD0` | `0x55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `0x55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `0x55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `0x55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `0x55702314` | `HSEngine.TAbstractHexagon.Activate@23EDC2EF` | TAbstractHexagon |
| `0xE4` | `0x55702254` | `HSEngine.TMapObject.Deactivate@23EDC2EF` | TMapObject |
| `0xE8` | `0x55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `0x55701D44` | `HSEngine.THexagonSprite.UpdateMapField@23EDC2EF` | THexagonSprite |
| `0xF0` | `0x5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `0x55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `0x557021A4` | `HSEngine.TMapObject.CanSelect@23EDC2EF` | TMapObject |
| `0xFC` | `0x557021E4` | `HSEngine.TMapObject.Select@23EDC2EF` | TMapObject |
| `0x100` | `0x557021EC` | `HSEngine.TMapObject.Unselect@23EDC2EF` | TMapObject |
| `0x104` | `0x55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x5570230C` | `HSEngine.TAbstractHexagon.SetResource@23EDC2EF` | TAbstractHexagon |
| `0x114` | `0x5570232C` | `HSEngine.TAbstractHexagon.CanPlace@23EDC2EF` | TAbstractHexagon |
| `0x118` | `0x55702334` | `HSEngine.TAbstractHexagon.PlaceHX@23EDC2EF` | TAbstractHexagon |
| `0x11C` | `0x55799458` | `Hexagon.THexagon.UpdateTransitions@23EDC2EF` | THexagon |
| `0x120` | `0x5579A9E0` | `AoWHex.TAoWHexagon.UpdateTransition@23EDC2EF` | TAoWHexagon |

### TArena  —  VMT `557D6240`, instance `0x30`, 124 slots, ends `0x1F0`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
Source = "Modding Resources/AoWEPACK_original_backup.dpl" (pristine vanilla, byte-identical to the Ghidra image). Every slot symbol comes from the file's own tables, not from guessing: local targets resolved through AoWEPACK's export directory (10036 exported names / 10033 unique VAs), cross-module targets resolved through the import directory. 15 slots spread across the table (including the tightly packed 1-4 byte stubs at 5575F360/64/68/74, 5575EDE4, 5575E69C, 5575F4F4) were independently spot-checked with mcp__ghidra__get_function_by_address — all 15 matched the export-derived name exactly. No slot came back without a symbol; there are zero "" entries.
All VAs are at the preferred base 0x55700000. The DPL rebases at runtime (see the project's PIC rule). CODE section: VA 55701000..558E7A00, raw 0x400 -> file offset = VA - 0x55700C00. VMT file offset = 0xD5640.

WHERE THE VMT ENDS (unambiguous)
+0x1EC (AoWE.TStructure.CanRaze) is the last slot. The dword at +0x1F0 is 0x72415406, i.e. the bytes 06 'T' 'A' 'r' — the start of the ShortString "TArena" at 557D6430, which is exactly what vmtClassName (VMT-0x20) points at. The class-name string immediately follows the VMT, so the terminator is self-proving. 124 slots, 0x1F0 bytes.

VMT HEADER (negative offsets) — Delphi 3 layout, all values verified
  -0x40 vmtSelfPtr        557D6240  (points back at the VMT; this is how I enumerated all 893 VMTs in the DLL)
  -0x3C vmtIntfTable      0
  -0x38 vmtAutoTable      0
  -0x34 vmtInitTable      0
  -0x30 vmtTypeInfo       0
  -0x2C vmtFieldTable     0
  -0x28 vmtMethodTable    0
  -0x24 vmtDynamicTable   0        <-- TArena has NO dynamic methods
  -0x20 vmtClassName      557D6430 -> ShortString "TArena"
  -0x1C vmtInstanceSize   0x30
  -0x18 vmtParent         55713BD8 -> deref -> 55713C18 = TStructure VMT
  -0x14 vmtSafeCallException 557010C8 -> VCL30.dpl!System.TObject.SafeCallException
  -0x10 vmtDefaultHandler    557010D0 -> VCL30.dpl!System.TObject.DefaultHandler
  -0x0C vmtNewInstance       55701098 -> VCL30.dpl!System.TObject.NewInstance
  -0x08 vmtFreeInstance      557010A0 -> VCL30.dpl!System.TObject.FreeInstance
  -0x04 vmtDestroy           5575E5C8 -> AoWE.TStructure.Destroy  (TArena does NOT override Destroy)
Note vmtDestroy sits at -0x04, NOT at a positive slot — user-declared virtuals start at +0x00.

⚠ 50 OF THE 124 SLOTS ARE IMPORT THUNKS, NOT REAL FUNCTIONS
Every target in 0x55701000-0x557035FF is a 6-byte `FF 25 <IAT>` jump stub inside AoWEPACK, forwarding to another package. The target_va I report is the address actually stored in the VMT (the thunk), which is what a patcher reads/writes; the symbol is the ultimate function in the foreign DLL. Module per owner class:
  TEObject           -> EngineP.dpl   (15 slots)
  TMapObject         -> HSEPack.dpl   (20 slots)
  TMultiHexMO        -> HSEPack.dpl   (9 slots)
  THexagonSprite     -> HSEPack.dpl   (8 slots)
  TILTerrainMO       -> HSEPack.dpl   (2 slots)
  TFixedILTerrainMO  -> HSEPack.dpl   (1 slot)
  TStructure/TArena  -> AoWEPACK.dpl  (65 + 4 slots, real local code)
Consequence: those 50 methods cannot be hooked by patching the function body in AoWEPACK — only the VMT slot (or the thunk's 6 bytes, or HSEPack/EngineP itself). Ghidra has none of those modules, which is why get_function_by_address returns "No function found" for them.

⚠ `owner` = IMPLEMENTER, NOT DECLARER
The owner field is the class whose implementation currently occupies the slot. It is not necessarily the class that first declared the virtual. Clear example: +0x74/+0x78 hold TMultiHexMO.GetXhx/GetYhx interleaved among TMapObject slots — TMultiHexMO overrode a slot declared further up the chain. Do not infer declaration order from it.

ANCESTRY
TArena -> TStructure (AoWEPACK, unit AoWE, VMT 55713C18) -> [TFixedILTerrainMO / TILTerrainMO / TMultiHexMO / TMapObject / THexagonSprite, all HSEPack.dpl] -> TEObject (EngineP.dpl) -> TObject (VCL30.dpl).
The chain walk stops at TStruc
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `5575E658` | `AoWE.TStructure.ReadWrite@23EDC2EF` | TStructure |
| `0x1C` | `55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `5575E590` | `AoWE.TStructure.Create@23EDC2EF` | TStructure |
| `0x24` | `557D66E8` | `Arena.TArena.ClassID@23EDC2EF` | TArena |
| `0x28` | `5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `5575F898` | `AoWE.TStructure.MsgProc@23EDC2EF` | TStructure |
| `0x48` | `557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `5575EC04` | `AoWE.TStructure.GetTerrain@23EDC2EF` | TStructure |
| `0x50` | `557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `5575EBF0` | `AoWE.TStructure.GetOverlay@23EDC2EF` | TStructure |
| `0x5C` | `557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `5570213C` | `HSEngine.TMapObject.GetLevel@23EDC2EF` | TMapObject |
| `0x68` | `55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `55702394` | `HSEngine.TMultiHexMO.GetXhx@23EDC2EF` | TMultiHexMO |
| `0x78` | `5570239C` | `HSEngine.TMultiHexMO.GetYhx@23EDC2EF` | TMultiHexMO |
| `0x7C` | `55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `557023A4` | `HSEngine.TMultiHexMO.GetXYL@23EDC2EF` | TMultiHexMO |
| `0x84` | `5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `557023AC` | `HSEngine.TMultiHexMO.GetShowPriority@23EDC2EF` | TMultiHexMO |
| `0x90` | `557023C4` | `HSEngine.TMultiHexMO.Connect@23EDC2EF` | TMultiHexMO |
| `0x94` | `557023CC` | `HSEngine.TMultiHexMO.Disconnect@23EDC2EF` | TMultiHexMO |
| `0x98` | `5575EC1C` | `AoWE.TStructure.CanChangeTerrain@23EDC2EF` | TStructure |
| `0x9C` | `557035AC` | `ILTer.TFixedILTerrainMO.ChangeTerrain@23EDC2EF` | TFixedILTerrainMO |
| `0xA0` | `5575EC80` | `AoWE.TStructure.TerrainChanged@23EDC2EF` | TStructure |
| `0xA4` | `55701E3C` | `HSEngine.THexagonSprite.NeighbourTerrainChanged@23EDC2EF` | THexagonSprite |
| `0xA8` | `5575F958` | `AoWE.TStructure.Show@23EDC2EF` | TStructure |
| `0xAC` | `5575E7C0` | `AoWE.TStructure.PlaceOnMap@23EDC2EF` | TStructure |
| `0xB0` | `5575E7EC` | `AoWE.TStructure.RemoveFromMap@23EDC2EF` | TStructure |
| `0xB4` | `5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `55703574` | `ILTer.TILTerrainMO.Loaded@23EDC2EF` | TILTerrainMO |
| `0xCC` | `5575F730` | `AoWE.TStructure.MapFieldMsgProc@23EDC2EF` | TStructure |
| `0xD0` | `55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `5575F6C0` | `AoWE.TStructure.Activate@23EDC2EF` | TStructure |
| `0xE4` | `5575F710` | `AoWE.TStructure.Deactivate@23EDC2EF` | TStructure |
| `0xE8` | `55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `55760444` | `AoWE.TStructure.UpdateMapField@23EDC2EF` | TStructure |
| `0xF0` | `5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `5575E994` | `AoWE.TStructure.CanSelect@23EDC2EF` | TStructure |
| `0xFC` | `5575EA40` | `AoWE.TStructure.Select@23EDC2EF` | TStructure |
| `0x100` | `5575EA64` | `AoWE.TStructure.Unselect@23EDC2EF` | TStructure |
| `0x104` | `55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `55702184` | `HSEngine.TMapObject.SetResource@23EDC2EF` | TMapObject |
| `0x114` | `5575ECC8` | `AoWE.TStructure.CanPlace@23EDC2EF` | TStructure |
| `0x118` | `5575ED10` | `AoWE.TStructure.PlaceHX@23EDC2EF` | TStructure |
| `0x11C` | `55702424` | `HSEngine.TMultiHexMO.SortMapFields@23EDC2EF` | TMultiHexMO |
| `0x120` | `557023F4` | `HSEngine.TMultiHexMO.CanPlaceOnHS@23EDC2EF` | TMultiHexMO |
| `0x124` | `55702414` | `HSEngine.TMultiHexMO.GetMostFrequentMapFieldTerrainType@23EDC2EF` | TMultiHexMO |
| `0x128` | `5575EC44` | `AoWE.TStructure.ValidTerrainType@23EDC2EF` | TStructure |
| `0x12C` | `5575E6A0` | `AoWE.TStructure.GetTerrainTypeImage@23EDC2EF` | TStructure |
| `0x130` | `5575E93C` | `AoWE.TStructure.ForceTerrainType@23EDC2EF` | TStructure |
| `0x134` | `55703534` | `ILTer.TILTerrainMO.GetValidTerrainType@23EDC2EF` | TILTerrainMO |
| `0x138` | `5575EB0C` | `AoWE.TStructure.GetTopBorderImage@23EDC2EF` | TStructure |
| `0x13C` | `5575EB58` | `AoWE.TStructure.GetMiddleBorderImage@23EDC2EF` | TStructure |
| `0x140` | `5575EBA4` | `AoWE.TStructure.GetBottomBorderImage@23EDC2EF` | TStructure |
| `0x144` | `5575E988` | `AoWE.TStructure.GetDescription@23EDC2EF` | TStructure |
| `0x148` | `5575E950` | `AoWE.TStructure.GetName@23EDC2EF` | TStructure |
| `0x14C` | `5575EDE8` | `AoWE.TStructure.SetRazed@23EDC2EF` | TStructure |
| `0x150` | `5575EDE4` | `AoWE.TStructure.GetRazed@23EDC2EF` | TStructure |
| `0x154` | `5575EDDC` | `AoWE.TStructure.GetRazeable@23EDC2EF` | TStructure |
| `0x158` | `5576023C` | `AoWE.TStructure.RazeEx@23EDC2EF` | TStructure |
| `0x15C` | `5575FE0C` | `AoWE.TStructure.SetupRazeDefenderAG@23EDC2EF` | TStructure |
| `0x160` | `557D6B68` | `Arena.TArena.CreateTE@23EDC2EF` | TArena |
| `0x164` | `5575E89C` | `AoWE.TStructure.SetupTE@23EDC2EF` | TStructure |
| `0x168` | `557D67D8` | `Arena.TArena.ExecuteTE@23EDC2EF` | TArena |
| `0x16C` | `5575F378` | `AoWE.TStructure.GetDefenseRequirements@23EDC2EF` | TStructure |
| `0x170` | `5575F374` | `AoWE.TStructure.GetDefensePriority@23EDC2EF` | TStructure |
| `0x174` | `5575F338` | `AoWE.TStructure.NewDay@23EDC2EF` | TStructure |
| `0x178` | `5575F33C` | `AoWE.TStructure.NewTurn@23EDC2EF` | TStructure |
| `0x17C` | `5575F36C` | `AoWE.TStructure.SeatedPlayerChanged@23EDC2EF` | TStructure |
| `0x180` | `5575F360` | `AoWE.TStructure.ArmyPlaced@23EDC2EF` | TStructure |
| `0x184` | `5575F364` | `AoWE.TStructure.ArmyRemoved@23EDC2EF` | TStructure |
| `0x188` | `5575F368` | `AoWE.TStructure.ArmyChanged@23EDC2EF` | TStructure |
| `0x18C` | `5575EA18` | `AoWE.TStructure.PlaySelectSample@23EDC2EF` | TStructure |
| `0x190` | `5575E818` | `AoWE.TStructure.CreateShadow@23EDC2EF` | TStructure |
| `0x194` | `5575E850` | `AoWE.TStructure.DestroyShadow@23EDC2EF` | TStructure |
| `0x198` | `5575F908` | `AoWE.TStructure.ShowShadow@23EDC2EF` | TStructure |
| `0x19C` | `5575F010` | `AoWE.TStructure.BuildingDone@23EDC2EF` | TStructure |
| `0x1A0` | `5575EF08` | `AoWE.TStructure.ExecuteRebuild@23EDC2EF` | TStructure |
| `0x1A4` | `5575EFD8` | `AoWE.TStructure.ExecuteBuild@23EDC2EF` | TStructure |
| `0x1A8` | `5575FD1C` | `AoWE.TStructure.GenerateRazeDefenders@23EDC2EF` | TStructure |
| `0x1AC` | `5575FE84` | `AoWE.TStructure.PlaceRazeDefenders@23EDC2EF` | TStructure |
| `0x1B0` | `5575FFC8` | `AoWE.TStructure.ExecuteRaze@23EDC2EF` | TStructure |
| `0x1B4` | `5575E968` | `AoWE.TStructure.GetCurrentActivityText@23EDC2EF` | TStructure |
| `0x1B8` | `5575F4F4` | `AoWE.TStructure.ValidateMap@23EDC2EF` | TStructure |
| `0x1BC` | `5575F4F8` | `AoWE.TStructure.MainValidateMap@23EDC2EF` | TStructure |
| `0x1C0` | `5575E698` | `AoWE.TStructure.ExecuteAI@23EDC2EF` | TStructure |
| `0x1C4` | `5575E69C` | `AoWE.TStructure.UpdateAITarget@23EDC2EF` | TStructure |
| `0x1C8` | `5575E878` | `AoWE.TStructure.Update@23EDC2EF` | TStructure |
| `0x1CC` | `5575EDEC` | `AoWE.TStructure.VisibleForPlayer@23EDC2EF` | TStructure |
| `0x1D0` | `557D66F0` | `Arena.TArena.CanDblClick@23EDC2EF` | TArena |
| `0x1D4` | `5575F37C` | `AoWE.TStructure.ListUnits@23EDC2EF` | TStructure |
| `0x1D8` | `5575F434` | `AoWE.TStructure.ListArmies@23EDC2EF` | TStructure |
| `0x1DC` | `5575F18C` | `AoWE.TStructure.GetRebuildInfo@23EDC2EF` | TStructure |
| `0x1E0` | `5575F1A4` | `AoWE.TStructure.CanRebuild@23EDC2EF` | TStructure |
| `0x1E4` | `5575F26C` | `AoWE.TStructure.Rebuild@23EDC2EF` | TStructure |
| `0x1E8` | `557602F8` | `AoWE.TStructure.Raze@23EDC2EF` | TStructure |
| `0x1EC` | `5575FB80` | `AoWE.TStructure.CanRaze@23EDC2EF` | TStructure |

### TCombatObject  —  VMT `0x557158EC`, instance `0x4C`, 77 slots, ends `0x134`

<details><summary>derivation notes</summary>

```
DERIVED, NOT GUESSED. Source: pristine vanilla AoWEPACK.dpl (Ghidra program AoWEPACK_vanilla.dpl, image base 0x55700000; cross-checked byte-for-byte against Modding Resources/AoWEPACK_original_backup.dpl). 77 slots, ALL resolved to real symbols - zero unknowns, zero "" entries.

VMT HEADER (negative offsets, Delphi 2/3 layout - confirmed empirically, NOT the Delphi 4+ layout):
  VMT-0x20 = 0x55715A20 -> ClassName ShortString
  VMT-0x1C = 0x0000004C -> InstanceSize (76 bytes)
  VMT-0x18 = 0x558FC92C -> Parent (PClass cell) = EngineP.dpl!Engine..TEObject@BD8FE92F
  VMT-0x14 = 0x557010C8 -> VCL30.dpl!System.TObject.SafeCallException
  VMT-0x10 = 0x557010D0 -> VCL30.dpl!System.TObject.DefaultHandler
  VMT-0x0C = 0x55701098 -> VCL30.dpl!System.TObject.NewInstance
  VMT-0x08 = 0x557010A0 -> VCL30.dpl!System.TObject.FreeInstance
  VMT-0x04 = 0x55726168 -> AoWE.TCombatObject.Destroy (destructor lives in the header, NOT in a positive slot)

WHY THE END IS CERTAIN (not a heuristic stop): the last slot is +0x130, and the dword at +0x134 is 0x6F43540D = the bytes 0D 54 43 6F, i.e. the ShortString <len 13>"TCombatObject" - the very string VMT-0x20 points at (0x557158EC + 0x134 = 0x55715A20, exactly the ClassName pointer value). The VMT is immediately followed by its own class-name string, then 8B C0 padding, then the next VMT at 0x55715A34. So vmt_end = 0x134 is closed by arithmetic, not by "the pointer stopped looking like code".

DIRECT PARENT IS Engine.TEObject, AND IT LIVES IN ANOTHER PACKAGE (EngineP.dpl). This is the single most important structural fact here: TCombatObject derives directly from TEObject (no intermediate class), and TEObject's VMT is exactly 0x4C bytes = 19 slots. Therefore slots +0x00..+0x48 are the TEObject slice and slots +0x4C..+0x130 (58 slots) are TCombatObject's own additions.

*** PATCHING TRAP - READ BEFORE HOOKING ANY INHERITED SLOT ***
Because TEObject is in EngineP.dpl, every INHERITED (non-overridden) slot does NOT point at real code in AoWEPACK.dpl. It points at an 8-byte IMPORT THUNK in AoWEPACK's thunk band at 0x55703064..0x5570310C, each of the form:
    FF 25 <abs IAT cell>    jmp dword ptr [cell]      (+ 2 bytes 8B C0 padding)
The target_va I report for those slots is the THUNK address inside AoWEPACK (what the VMT slot literally contains - that is what you compare/patch), not the final TEObject code, which is in EngineP.dpl and is not in this image at all. Thunk -> IAT cell mapping for the inherited slots:
  +0x000 0x55703074 -> [0x558FC724] ClassVersion      +0x004 0x557030DC -> [0x558FC6F0] GetControlStyle
  +0x008 0x557030E4 -> [0x558FC6EC] SetOwner          +0x00C 0x557030D4 -> [0x558FC6F4] GetEngine
  +0x010 0x557030AC -> [0x558FC708] GetLastMsg        +0x014 0x557030B4 -> [0x558FC704] SetLastMsg
  +0x01C 0x55703104 -> [0x558FC6DC] MainReadWrite     +0x024 0x55703094 -> [0x558FC714] ClassID
  +0x028 0x5570307C -> [0x558FC720] AddRef            +0x02C 0x55703084 -> [0x558FC71C] Release
  +0x030 0x5570308C -> [0x558FC718] Clear             +0x034 0x557030BC -> [0x558FC700] Compare
  +0x038 0x5570309C -> [0x558FC710] Editor            +0x03C 0x557030C4 -> [0x558FC6FC] Assign
  +0x040 0x557030A4 -> [0x558FC70C] TimerEvent        +0x044 0x557030F4 -> [0x558FC6E4] MsgProc
  +0x048 0x557030EC -> [0x558FC6E8] SetArrayOwner
Two further TEObject thunks exist but are NOT reachable through this VMT because TCombatObject overrides both: Create thunk 0x55703064 -> [0x558FC72C] (overridden at +0x20) and ReadWrite thunk 0x557030FC -> [0x558FC6E0] (overridden at +0x18). TEObject.Destroy thunk 0x5570306C -> [0x558FC728] is likewise overridden, in the header at VMT-0x04.

Ghidra had NO function defined at 11 of those 17 thunk addresses (0x55703074, 0x5570307C, 0x55703084, 0x55703094, 0x557030A4, 0x557030AC, 0x557030B4, 0x557030BC, 0x557030C4, 0x557030D4, 0x55703104) - get_function_by_address returns "No function found". Those names were recovered by parsing the PE import table directly (75 descriptors, 1444 IAT
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x557265C0` | `AoWE.TCombatObject.ReadWrite@23EDC2EF` | TCombatObject |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x55726118` | `AoWE.TCombatObject.Create@23EDC2EF` | TCombatObject |
| `0x024` | `0x55703094` | `Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x028` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x02C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x030` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x5572637C` | `AoWE.TCombatObject.GetTargetCVDV@23EDC2EF` | TCombatObject |
| `0x050` | `0x55726390` | `AoWE.TCombatObject.GetTargetWallCV@23EDC2EF` | TCombatObject |
| `0x054` | `0x557261AC` | `AoWE.TCombatObject.TargetsChanged@23EDC2EF` | TCombatObject |
| `0x058` | `0x55726394` | `AoWE.TCombatObject.GetTargetPriority@23EDC2EF` | TCombatObject |
| `0x05C` | `0x55726454` | `AoWE.TCombatObject.GetTargetStrength@23EDC2EF` | TCombatObject |
| `0x060` | `0x5572663C` | `AoWE.TCombatObject.GetEnabled@23EDC2EF` | TCombatObject |
| `0x064` | `0x557267A0` | `AoWE.TCombatObject.GetLocked@23EDC2EF` | TCombatObject |
| `0x068` | `0x557267A4` | `AoWE.TCombatObject.SetCombatPlayer@23EDC2EF` | TCombatObject |
| `0x06C` | `0x5572685C` | `AoWE.TCombatObject.GetAttack@23EDC2EF` | TCombatObject |
| `0x070` | `0x55726860` | `AoWE.TCombatObject.GetDefense@23EDC2EF` | TCombatObject |
| `0x074` | `0x55726864` | `AoWE.TCombatObject.GetResistance@23EDC2EF` | TCombatObject |
| `0x078` | `0x55726868` | `AoWE.TCombatObject.GetDamage@23EDC2EF` | TCombatObject |
| `0x07C` | `0x5572686C` | `AoWE.TCombatObject.GetImmunityTypes@23EDC2EF` | TCombatObject |
| `0x080` | `0x55726878` | `AoWE.TCombatObject.GetProtectionTypes@23EDC2EF` | TCombatObject |
| `0x084` | `0x55726888` | `AoWE.TCombatObject.GetHits@23EDC2EF` | TCombatObject |
| `0x088` | `0x55726890` | `AoWE.TCombatObject.GetHitPoints@23EDC2EF` | TCombatObject |
| `0x08C` | `0x5572688C` | `AoWE.TCombatObject.SetHitPoints@23EDC2EF` | TCombatObject |
| `0x090` | `0x557268CC` | `AoWE.TCombatObject.GetAlignment@23EDC2EF` | TCombatObject |
| `0x094` | `0x55726884` | `AoWE.TCombatObject.GetMoves@23EDC2EF` | TCombatObject |
| `0x098` | `0x55726894` | `AoWE.TCombatObject.GetExperience@23EDC2EF` | TCombatObject |
| `0x09C` | `0x55726898` | `AoWE.TCombatObject.SetExperience@23EDC2EF` | TCombatObject |
| `0x0A0` | `0x5572689C` | `AoWE.TCombatObject.GetLevel@23EDC2EF` | TCombatObject |
| `0x0A4` | `0x557265BC` | `AoWE.TCombatObject.GetVisibilityRange@23EDC2EF` | TCombatObject |
| `0x0A8` | `0x557268D4` | `AoWE.TCombatObject.GetAbilityEnabled@23EDC2EF` | TCombatObject |
| `0x0AC` | `0x557268D8` | `AoWE.TCombatObject.SetAbilityEnabled@23EDC2EF` | TCombatObject |
| `0x0B0` | `0x557268DC` | `AoWE.TCombatObject.GetAbilityLevel@23EDC2EF` | TCombatObject |
| `0x0B4` | `0x557268E0` | `AoWE.TCombatObject.GetAbilityCount@23EDC2EF` | TCombatObject |
| `0x0B8` | `0x557268D0` | `AoWE.TCombatObject.GetAbilityOwner@23EDC2EF` | TCombatObject |
| `0x0BC` | `0x55726708` | `AoWE.TCombatObject.Activate@23EDC2EF` | TCombatObject |
| `0x0C0` | `0x5572674C` | `AoWE.TCombatObject.Deactivate@23EDC2EF` | TCombatObject |
| `0x0C4` | `0x55726934` | `AoWE.TCombatObject.ObjectDestroyed@23EDC2EF` | TCombatObject |
| `0x0C8` | `0x5572653C` | `AoWE.TCombatObject.ObjectSideChanged@23EDC2EF` | TCombatObject |
| `0x0CC` | `0x55726790` | `AoWE.TCombatObject.Initialize@23EDC2EF` | TCombatObject |
| `0x0D0` | `0x55726794` | `AoWE.TCombatObject.Finalize@23EDC2EF` | TCombatObject |
| `0x0D4` | `0x557265B8` | `AoWE.TCombatObject.fcRoundDistance@23EDC2EF` | TCombatObject |
| `0x0D8` | `0x557265AC` | `AoWE.TCombatObject.fcExecute@23EDC2EF` | TCombatObject |
| `0x0DC` | `0x557265B0` | `AoWE.TCombatObject.fcBehindWall@23EDC2EF` | TCombatObject |
| `0x0E0` | `0x557265B4` | `AoWE.TCombatObject.fcWallInBetween@23EDC2EF` | TCombatObject |
| `0x0E4` | `0x5572695C` | `AoWE.TCombatObject.SupportCombatMode@23EDC2EF` | TCombatObject |
| `0x0E8` | `0x55726630` | `AoWE.TCombatObject.WallCombatFeatures@23EDC2EF` | TCombatObject |
| `0x0EC` | `0x5572679C` | `AoWE.TCombatObject.PlaySFX@23EDC2EF` | TCombatObject |
| `0x0F0` | `0x557266B4` | `AoWE.TCombatObject.NewTurn@23EDC2EF` | TCombatObject |
| `0x0F4` | `0x557266D0` | `AoWE.TCombatObject.NewRound@23EDC2EF` | TCombatObject |
| `0x0F8` | `0x557266D4` | `AoWE.TCombatObject.CombatDone@23EDC2EF` | TCombatObject |
| `0x0FC` | `0x55726D40` | `AoWE.TCombatObject.Show@23EDC2EF` | TCombatObject |
| `0x100` | `0x55726D48` | `AoWE.TCombatObject.ShowAttackAnimation@23EDC2EF` | TCombatObject |
| `0x104` | `0x55726D54` | `AoWE.TCombatObject.ShowHitAnimation@23EDC2EF` | TCombatObject |
| `0x108` | `0x55726B1C` | `AoWE.TCombatObject.DoDamage@23EDC2EF` | TCombatObject |
| `0x10C` | `0x55726960` | `AoWE.TCombatObject.GetOptimalDamageType@23EDC2EF` | TCombatObject |
| `0x110` | `0x557269F0` | `AoWE.TCombatObject.ExecuteDamageRole@23EDC2EF` | TCombatObject |
| `0x114` | `0x55726A6C` | `AoWE.TCombatObject.ExecuteDamageRoleEx@23EDC2EF` | TCombatObject |
| `0x118` | `0x55726B10` | `AoWE.TCombatObject.ExecuteDamageEffectsRole@23EDC2EF` | TCombatObject |
| `0x11C` | `0x55726C24` | `AoWE.TCombatObject.Surrender@23EDC2EF` | TCombatObject |
| `0x120` | `0x55726BA4` | `AoWE.TCombatObject.DestroyObject@23EDC2EF` | TCombatObject |
| `0x124` | `0x55726C58` | `AoWE.TCombatObject.ExecuteDamage@23EDC2EF` | TCombatObject |
| `0x128` | `0x55726B04` | `AoWE.TCombatObject.ExecuteDamageEffects@23EDC2EF` | TCombatObject |
| `0x12C` | `0x557266D8` | `AoWE.TCombatObject.TurnDone@23EDC2EF` | TCombatObject |
| `0x130` | `0x557268A0` | `AoWE.TCombatObject.IDStr@23EDC2EF` | TCombatObject |

### TCombatUnit  —  VMT `0x55715A94`, instance `0x5C`, 79 slots, ends `0x13C`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
Every symbol is ground truth from two independent sources that agreed on all of them:
(a) the DPL's own PE export directory (10036 exported names, parsed from
    "Modding Resources/AoWEPACK_original_backup.dpl"), and
(b) Ghidra's RTTI-derived function symbols, spot-checked on 8 addresses (557261AC, 557265B8,
    55725204, 5572653C, 557267A4, 55726960, 55726B1C, 55726C58, 557266D8) — all matched exactly.
Ghidra's in-memory VMT bytes at 55715A94 are byte-identical to the backup file.

Throwaway scripts (in the scratchpad, NOT in the project):
  vmt_walk_combatunit.py — locate VMT + naive slot walk
  vmt_resolve.py         — export+import symbol resolution; reusable for ANY class:
                           `python vmt_resolve.py TWhatever`
  vmt_extra.py           — negative header, parent chain, TCombatObject-vs-TCombatUnit diff

WHERE THE VMT ENDS — 0x13C, unambiguous
The dword at VMT+0x13C is 0x6F43540B, not a code pointer: the bytes are
`0B 54 43 6F 6D 62 61 74 55 6E 69 74` = the ShortString "TCombatUnit". That is exactly the string
[VMT-0x20] points at (0x55715BD0 == 0x55715A94 + 0x13C) — Delphi placed the class-name string
immediately after the last slot. Last real slot is +0x138. 79 slots total.

INSTANCE SIZE 0x5C (92). Parent TCombatObject is 0x4C, so TCombatUnit adds 0x10 bytes of fields.
Descendant TFastCombatUnit is 0x64.

VMT HEADER (negative offsets) — Delphi 3 layout, vmtSelfPtr at -0x40:
  -0x40 55715A94 vmtSelfPtr (exported as `AoWE..TCombatUnit@B2B5938D`)
  -0x3C 00000000 vmtIntfTable      -0x38 00000000 vmtAutoTable
  -0x34 00000000 vmtInitTable      -0x30 00000000 vmtTypeInfo
  -0x2C 00000000 vmtFieldTable     -0x28 00000000 vmtMethodTable
  -0x24 00000000 vmtDynamicTable  <-- NULL: TCombatUnit has NO dynamic/message-method table, so
                                     every dispatchable method is in the positive VMT.
  -0x20 55715BD0 vmtClassName -> "TCombatUnit"
  -0x1C 0000005C vmtInstanceSize
  -0x18 557158AC vmtParent (pointer TO the classref; deref -> 557158EC = TCombatObject VMT)
  -0x14 557010C8 vmtSafeCallException (thunk -> VCL30.dpl!System.TObject.SafeCallException)
  -0x10 557010D0 vmtDefaultHandler    (thunk -> VCL30.dpl!System.TObject.DefaultHandler)
  -0x0C 55701098 vmtNewInstance       (thunk -> VCL30.dpl!System.TObject.NewInstance)
  -0x08 557010A0 vmtFreeInstance      (thunk -> VCL30.dpl!System.TObject.FreeInstance)
  -0x04 55724A6C vmtDestroy = AoWE.TCombatUnit.Destroy@23EDC2EF  <-- destructor lives HERE, not in
                                     the positive table. Easy to miss.

ANCESTRY
  TCombatUnit      VMT=55715A94 instsize=0x5C vmtlen=0x13C (79 slots)
   -> TCombatObject VMT=557158EC instsize=0x4C vmtlen=0x134 (77 slots)
   -> Engine.TEObject — the chain LEAVES AoWEPACK here. TCombatObject's [VMT-0x18] is 558FC92C, an
      .idata slot importing `EngineP.dpl!Engine..TEObject@BD8FE92F`. TEObject's VMT is not in this
      module, so TEObject-owned slots cannot be walked further from this file.

THE 16 "TEObject" SLOTS ARE IMPORT THUNKS, NOT FUNCTION BODIES
Slots +0x00,04,08,0C,10,14,1C,28,2C,30,34,38,3C,40,44,48 point at 6-byte stubs in the 0x55703xxx
block: `FF 25 <abs>` = `jmp dword ptr [IAT]`, padded to 8 bytes with `8B C0`. Verified:
55703074 = FF 25 24 C7 8F 55 -> [558FC724] -> EngineP.dpl!Engine.TEObject.ClassVersion.
The symbol reported for these is the *imported* RTTI symbol from the import directory — real, not a
guess — but Ghidra has no function at those addresses ("No function found for 0x55703074"), so
get_function_by_address returns nothing there. target_va is the thunk inside AoWEPACK; the code
lives in EngineP.dpl. To hook one, patch the VMT slot, never the shared thunk.

OWNERSHIP SUMMARY (79 slots)
  50 owned/overridden by TCombatUnit
  13 inherited unchanged from TCombatObject: +0x054 TargetsChanged, +0x068 SetCombatPlayer,
     +0x0C8 ObjectSideChanged, +0x0D4 fcRoundDistance, +0x0D8 fcExecute, +0x0DC fcBehindWall,
     +0x0E0 fcWallInBe
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x55725204` | `AoWE.TCombatUnit.ReadWrite@23EDC2EF` | TCombatUnit |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55724A28` | `AoWE.TCombatUnit.Create@23EDC2EF` | TCombatUnit |
| `0x24` | `0x55724A9C` | `AoWE.TCombatUnit.ClassID@23EDC2EF` | TCombatUnit |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x557252E8` | `AoWE.TCombatUnit.GetTargetCVDV@23EDC2EF` | TCombatUnit |
| `0x50` | `0x55725438` | `AoWE.TCombatUnit.GetTargetWallCV@23EDC2EF` | TCombatUnit |
| `0x54` | `0x557261AC` | `AoWE.TCombatObject.TargetsChanged@23EDC2EF` | TCombatObject |
| `0x58` | `0x5572582C` | `AoWE.TCombatUnit.GetTargetPriority@23EDC2EF` | TCombatUnit |
| `0x5C` | `0x55725850` | `AoWE.TCombatUnit.GetTargetStrength@23EDC2EF` | TCombatUnit |
| `0x60` | `0x55724B70` | `AoWE.TCombatUnit.GetEnabled@23EDC2EF` | TCombatUnit |
| `0x64` | `0x55724BA4` | `AoWE.TCombatUnit.GetLocked@23EDC2EF` | TCombatUnit |
| `0x68` | `0x557267A4` | `AoWE.TCombatObject.SetCombatPlayer@23EDC2EF` | TCombatObject |
| `0x6C` | `0x55725490` | `AoWE.TCombatUnit.GetAttack@23EDC2EF` | TCombatUnit |
| `0x70` | `0x5572549C` | `AoWE.TCombatUnit.GetDefense@23EDC2EF` | TCombatUnit |
| `0x74` | `0x557254A8` | `AoWE.TCombatUnit.GetResistance@23EDC2EF` | TCombatUnit |
| `0x78` | `0x557254B4` | `AoWE.TCombatUnit.GetDamage@23EDC2EF` | TCombatUnit |
| `0x7C` | `0x557254C0` | `AoWE.TCombatUnit.GetImmunityTypes@23EDC2EF` | TCombatUnit |
| `0x80` | `0x557254E0` | `AoWE.TCombatUnit.GetProtectionTypes@23EDC2EF` | TCombatUnit |
| `0x84` | `0x5572504C` | `AoWE.TCombatUnit.GetHits@23EDC2EF` | TCombatUnit |
| `0x88` | `0x55725064` | `AoWE.TCombatUnit.GetHitPoints@23EDC2EF` | TCombatUnit |
| `0x8C` | `0x5572507C` | `AoWE.TCombatUnit.SetHitPoints@23EDC2EF` | TCombatUnit |
| `0x90` | `0x55724FF4` | `AoWE.TCombatUnit.GetAlignment@23EDC2EF` | TCombatUnit |
| `0x94` | `0x55724FE0` | `AoWE.TCombatUnit.GetMoves@23EDC2EF` | TCombatUnit |
| `0x98` | `0x557254F8` | `AoWE.TCombatUnit.GetExperience@23EDC2EF` | TCombatUnit |
| `0x9C` | `0x55725504` | `AoWE.TCombatUnit.SetExperience@23EDC2EF` | TCombatUnit |
| `0xA0` | `0x55725510` | `AoWE.TCombatUnit.GetLevel@23EDC2EF` | TCombatUnit |
| `0xA4` | `0x55724AD0` | `AoWE.TCombatUnit.GetVisibilityRange@23EDC2EF` | TCombatUnit |
| `0xA8` | `0x55725004` | `AoWE.TCombatUnit.GetAbilityEnabled@23EDC2EF` | TCombatUnit | ⚠ nil-GUARDED |
| `0xAC` | `0x5572501C` | `AoWE.TCombatUnit.SetAbilityEnabled@23EDC2EF` | TCombatUnit |
| `0xB0` | `0x55725028` | `AoWE.TCombatUnit.GetAbilityLevel@23EDC2EF` | TCombatUnit | ⚠ **NOT** nil-guarded |
| `0xB4` | `0x55725034` | `AoWE.TCombatUnit.GetAbilityCount@23EDC2EF` | TCombatUnit | ⚠ nil-guarded |
| `0xB8` | `0x55725000` | `AoWE.TCombatUnit.GetAbilityOwner@23EDC2EF` | TCombatUnit |
| `0xBC` | `0x55724CD0` | `AoWE.TCombatUnit.Activate@23EDC2EF` | TCombatUnit |
| `0xC0` | `0x55724CF4` | `AoWE.TCombatUnit.Deactivate@23EDC2EF` | TCombatUnit |
| `0xC4` | `0x55725284` | `AoWE.TCombatUnit.ObjectDestroyed@23EDC2EF` | TCombatUnit |
| `0xC8` | `0x5572653C` | `AoWE.TCombatObject.ObjectSideChanged@23EDC2EF` | TCombatObject |
| `0xCC` | `0x55724D10` | `AoWE.TCombatUnit.Initialize@23EDC2EF` | TCombatUnit |
| `0xD0` | `0x55724D44` | `AoWE.TCombatUnit.Finalize@23EDC2EF` | TCombatUnit |
| `0xD4` | `0x557265B8` | `AoWE.TCombatObject.fcRoundDistance@23EDC2EF` | TCombatObject |
| `0xD8` | `0x557265AC` | `AoWE.TCombatObject.fcExecute@23EDC2EF` | TCombatObject |
| `0xDC` | `0x557265B0` | `AoWE.TCombatObject.fcBehindWall@23EDC2EF` | TCombatObject |
| `0xE0` | `0x557265B4` | `AoWE.TCombatObject.fcWallInBetween@23EDC2EF` | TCombatObject |
| `0xE4` | `0x55725638` | `AoWE.TCombatUnit.SupportCombatMode@23EDC2EF` | TCombatUnit |
| `0xE8` | `0x55724C14` | `AoWE.TCombatUnit.WallCombatFeatures@23EDC2EF` | TCombatUnit |
| `0xEC` | `0x55724F2C` | `AoWE.TCombatUnit.PlaySFX@23EDC2EF` | TCombatUnit |
| `0xF0` | `0x55724B28` | `AoWE.TCombatUnit.NewTurn@23EDC2EF` | TCombatUnit |
| `0xF4` | `0x55724B4C` | `AoWE.TCombatUnit.NewRound@23EDC2EF` | TCombatUnit |
| `0xF8` | `0x55724B54` | `AoWE.TCombatUnit.CombatDone@23EDC2EF` | TCombatUnit |
| `0xFC` | `0x5572591C` | `AoWE.TCombatUnit.Show@23EDC2EF` | TCombatUnit |
| `0x100` | `0x557259C4` | `AoWE.TCombatUnit.ShowAttackAnimation@23EDC2EF` | TCombatUnit |
| `0x104` | `0x55725A18` | `AoWE.TCombatUnit.ShowHitAnimation@23EDC2EF` | TCombatUnit |
| `0x108` | `0x55726B1C` | `AoWE.TCombatObject.DoDamage@23EDC2EF` | TCombatObject |
| `0x10C` | `0x55726960` | `AoWE.TCombatObject.GetOptimalDamageType@23EDC2EF` | TCombatObject |
| `0x110` | `0x557269F0` | `AoWE.TCombatObject.ExecuteDamageRole@23EDC2EF` | TCombatObject |
| `0x114` | `0x55726A6C` | `AoWE.TCombatObject.ExecuteDamageRoleEx@23EDC2EF` | TCombatObject |
| `0x118` | `0x55724C3C` | `AoWE.TCombatUnit.ExecuteDamageEffectsRole@23EDC2EF` | TCombatUnit |
| `0x11C` | `0x557257B8` | `AoWE.TCombatUnit.Surrender@23EDC2EF` | TCombatUnit |
| `0x120` | `0x557256F0` | `AoWE.TCombatUnit.DestroyObject@23EDC2EF` | TCombatUnit |
| `0x124` | `0x55726C58` | `AoWE.TCombatObject.ExecuteDamage@23EDC2EF` | TCombatObject |
| `0x128` | `0x55724C1C` | `AoWE.TCombatUnit.ExecuteDamageEffects@23EDC2EF` | TCombatUnit |
| `0x12C` | `0x557266D8` | `AoWE.TCombatObject.TurnDone@23EDC2EF` | TCombatObject |
| `0x130` | `0x5572551C` | `AoWE.TCombatUnit.IDStr@23EDC2EF` | TCombatUnit |
| `0x134` | `0x55725194` | `AoWE.TCombatUnit.SetUnit@23EDC2EF` | TCombatUnit |
| `0x138` | `0x557256E4` | `AoWE.TCombatUnit.KillUnit@23EDC2EF` | TCombatUnit |

### TExplorationSite  —  VMT `0x557C1440`, instance `0x38`, 129 slots, ends `0x204`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
- Class lives in Delphi unit "ExploreS" (NOT "AoWE"). Full symbols are ExploreS.TExplorationSite.<Method>@23EDC2EF.
- VMT found via the RTTI recipe on Modding Resources/AoWEPACK_original_backup.dpl (same bytes Ghidra holds):
  [VMT-0x20]=0x557C1644 -> ShortString(0x10)"TExplorationSite"; [VMT-0x1C]=0x38 instance size;
  [VMT-0x18]=0x55713BD8 -> deref 0x55713C18 = TStructure's VMT.
- RTTI TTypeInfo record at 0x557C165C (kind byte 0x07 = tkClass, name "TExplorationSite", ClassType=0x557C1440, UnitName "ExploreS"). Only 2 occurrences of the class-name ShortString in the file: the VMT name string and this TypeInfo — so there is exactly ONE TExplorationSite VMT.

WHERE THE VMT ENDS (important: "points into CODE" does NOT bound it here — Delphi puts VMTs, class-name strings and TypeInfo all inside the CODE section)
- Last valid slot is +0x200. The class-name ShortString begins immediately at VMT+0x204 (= 0x557C1644), verified byte-exact against Ghidra read_memory at 0x557C1638:
  90 18 7C 55 | 20 1A 7C 55 | 5C 1E 7C 55 | 10 'TExplorationSite' | 8D 40 00
  i.e. slots +0x1F8/+0x1FC/+0x200 then the string. So first offset past the VMT = 0x204, 129 slots.

INHERITANCE (ancestor chain, from slot owners + parent classrefs)
  Engine.TEObject (EngineP.dpl)
    -> HSEngine.THexagonSprite (HSEPack.dpl)
      -> HSEngine.TMapObject
        -> HSEngine.TMultiHexMO
          -> ILTer.TILTerrainMO
            -> ILTer.TFixedILTerrainMO   <-- TStructure's parent, resolved from IAT cell 0x558FCA08 = "HSEPack.dpl!ILTer..TFixedILTerrainMO@DE482B1C"
              -> AoWE.TStructure (VMT 0x55713C18, instsize 0x30, 124 slots, ends at +0x1EC / first past end 0x1F0)
                -> ExploreS.TExplorationSite (VMT 0x557C1440, instsize 0x38, 129 slots)
- TExplorationSite adds 8 bytes of own fields (0x30..0x37) over TStructure's 0x30.
- Owner histogram over the 129 slots: TStructure 58, TMapObject 20, TExplorationSite 16, TEObject 15, TMultiHexMO 9, THexagonSprite 8, TILTerrainMO 2, TFixedILTerrainMO 1.

OVERRIDE vs NEW (diffed slot-by-slot against TStructure's VMT — this is derived, not guessed)
- 11 INHERITED slots that TExplorationSite OVERRIDES (TStructure's value -> TExplorationSite's):
  +0x018 ReadWrite   0x5575E658 -> 0x557C1F8C
  +0x020 Create      0x5575E590 -> 0x557C17CC
  +0x024 ClassID     0x5575E588 -> 0x557C183C
  +0x044 MsgProc     0x5575F898 -> 0x557C2118
  +0x0E0 Activate    0x5575F6C0 -> 0x557C20F0
  +0x0E4 Deactivate  0x5575F710 -> 0x557C2104
  +0x0F8 CanSelect   0x5575E994 -> 0x557C1D58
  +0x12C GetTerrainTypeImage 0x5575E6A0 -> 0x557C1848
  +0x168 ExecuteTE   0x5575E8CC -> 0x557C1D28
  +0x174 NewDay      0x5575F338 -> 0x557C20A4
  +0x1C8 Update      0x5575E878 -> 0x557C20D0
- 5 slots NEWLY DECLARED by TExplorationSite (past TStructure's VMT end of 0x1F0): +0x1F0 GetExplored, +0x1F4 SetupCombat, +0x1F8 ExecuteSearchDone, +0x1FC ExecuteSearch, +0x200 Search. These are the exploration-site search/combat entry points and exist on no ancestor.
- All other 113 slots are inherited unchanged; "owner" is the class that PROVIDES the implementation (the most-derived override in the chain), which is what the symbol records. It is not necessarily the class that *declared* the slot — e.g. +0x04C is TStructure.GetTerrain while +0x050/+0x054 are TMapObject.SetTerrain/GetTerrainCount, one declared trio with only the getter overridden.

SYMBOL SOURCES (every slot resolved; none unknown)
- 61 slots point at functions inside AoWEPACK.dpl and were resolved from its export table (10036 named exports). Cross-checked 9 of them against Ghidra get_function_by_address — 9/9 exact string match (e.g. 0x557C1F8C -> ExploreS.TExplorationSite.ReadWrite@23EDC2EF, 0x5575EC04 -> AoWE.TStructure.GetTerrain@23EDC2EF).
- 68 slots point at 8-byte-spaced cross-package import thunks in the 0x55701D00-0x557035B0 range, of the form "FF 25 <IAT>" + "8B C0" padding. Ghidra has NO function defined at these addresses (get_function_by_address returns "No fun
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `0x55703074` | `EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `0x557030DC` | `EngineP.dpl!Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `0x557030E4` | `EngineP.dpl!Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `0x557030D4` | `EngineP.dpl!Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `EngineP.dpl!Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `EngineP.dpl!Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557C1F8C` | `ExploreS.TExplorationSite.ReadWrite@23EDC2EF` | TExplorationSite |
| `0x1C` | `0x55703104` | `EngineP.dpl!Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x557C17CC` | `ExploreS.TExplorationSite.Create@23EDC2EF` | TExplorationSite |
| `0x24` | `0x557C183C` | `ExploreS.TExplorationSite.ClassID@23EDC2EF` | TExplorationSite |
| `0x28` | `0x5570307C` | `EngineP.dpl!Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `EngineP.dpl!Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `EngineP.dpl!Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `EngineP.dpl!Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `EngineP.dpl!Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `EngineP.dpl!Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `EngineP.dpl!Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557C2118` | `ExploreS.TExplorationSite.MsgProc@23EDC2EF` | TExplorationSite |
| `0x48` | `0x557030EC` | `EngineP.dpl!Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5575EC04` | `AoWE.TStructure.GetTerrain@23EDC2EF` | TStructure |
| `0x50` | `0x557021BC` | `HSEPack.dpl!HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `0x557021C4` | `HSEPack.dpl!HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `0x5575EBF0` | `AoWE.TStructure.GetOverlay@23EDC2EF` | TStructure |
| `0x5C` | `0x557021D4` | `HSEPack.dpl!HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `0x557021DC` | `HSEPack.dpl!HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `0x5570213C` | `HSEPack.dpl!HSEngine.TMapObject.GetLevel@23EDC2EF` | TMapObject |
| `0x68` | `0x55702134` | `HSEPack.dpl!HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `0x5570214C` | `HSEPack.dpl!HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `0x557021AC` | `HSEPack.dpl!HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `0x55702394` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetXhx@23EDC2EF` | TMultiHexMO |
| `0x78` | `0x5570239C` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetYhx@23EDC2EF` | TMultiHexMO |
| `0x7C` | `0x55702174` | `HSEPack.dpl!HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `0x557023A4` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetXYL@23EDC2EF` | TMultiHexMO |
| `0x84` | `0x5570215C` | `HSEPack.dpl!HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `0x55702154` | `HSEPack.dpl!HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `0x557023AC` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetShowPriority@23EDC2EF` | TMultiHexMO |
| `0x90` | `0x557023C4` | `HSEPack.dpl!HSEngine.TMultiHexMO.Connect@23EDC2EF` | TMultiHexMO |
| `0x94` | `0x557023CC` | `HSEPack.dpl!HSEngine.TMultiHexMO.Disconnect@23EDC2EF` | TMultiHexMO |
| `0x98` | `0x5575EC1C` | `AoWE.TStructure.CanChangeTerrain@23EDC2EF` | TStructure |
| `0x9C` | `0x557035AC` | `HSEPack.dpl!ILTer.TFixedILTerrainMO.ChangeTerrain@23EDC2EF` | TFixedILTerrainMO |
| `0xA0` | `0x5575EC80` | `AoWE.TStructure.TerrainChanged@23EDC2EF` | TStructure |
| `0xA4` | `0x55701E3C` | `HSEPack.dpl!HSEngine.THexagonSprite.NeighbourTerrainChanged@23EDC2EF` | THexagonSprite |
| `0xA8` | `0x5575F958` | `AoWE.TStructure.Show@23EDC2EF` | TStructure |
| `0xAC` | `0x5575E7C0` | `AoWE.TStructure.PlaceOnMap@23EDC2EF` | TStructure |
| `0xB0` | `0x5575E7EC` | `AoWE.TStructure.RemoveFromMap@23EDC2EF` | TStructure |
| `0xB4` | `0x5570225C` | `HSEPack.dpl!HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `0x55702264` | `HSEPack.dpl!HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `0x55701EC4` | `HSEPack.dpl!HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `0x557021FC` | `HSEPack.dpl!HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `0x5570223C` | `HSEPack.dpl!HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `0x55703574` | `HSEPack.dpl!ILTer.TILTerrainMO.Loaded@23EDC2EF` | TILTerrainMO |
| `0xCC` | `0x5575F730` | `AoWE.TStructure.MapFieldMsgProc@23EDC2EF` | TStructure |
| `0xD0` | `0x55701D54` | `HSEPack.dpl!HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `0x55701D5C` | `HSEPack.dpl!HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `0x55701D64` | `HSEPack.dpl!HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `0x55701D8C` | `HSEPack.dpl!HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `0x557C20F0` | `ExploreS.TExplorationSite.Activate@23EDC2EF` | TExplorationSite |
| `0xE4` | `0x557C2104` | `ExploreS.TExplorationSite.Deactivate@23EDC2EF` | TExplorationSite |
| `0xE8` | `0x55701D9C` | `HSEPack.dpl!HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `0x55760444` | `AoWE.TStructure.UpdateMapField@23EDC2EF` | TStructure |
| `0xF0` | `0x5570219C` | `HSEPack.dpl!HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `0x55701DA4` | `HSEPack.dpl!HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `0x557C1D58` | `ExploreS.TExplorationSite.CanSelect@23EDC2EF` | TExplorationSite |
| `0xFC` | `0x5575EA40` | `AoWE.TStructure.Select@23EDC2EF` | TStructure |
| `0x100` | `0x5575EA64` | `AoWE.TStructure.Unselect@23EDC2EF` | TStructure |
| `0x104` | `0x55702144` | `HSEPack.dpl!HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEPack.dpl!HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEPack.dpl!HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x55702184` | `HSEPack.dpl!HSEngine.TMapObject.SetResource@23EDC2EF` | TMapObject |
| `0x114` | `0x5575ECC8` | `AoWE.TStructure.CanPlace@23EDC2EF` | TStructure |
| `0x118` | `0x5575ED10` | `AoWE.TStructure.PlaceHX@23EDC2EF` | TStructure |
| `0x11C` | `0x55702424` | `HSEPack.dpl!HSEngine.TMultiHexMO.SortMapFields@23EDC2EF` | TMultiHexMO |
| `0x120` | `0x557023F4` | `HSEPack.dpl!HSEngine.TMultiHexMO.CanPlaceOnHS@23EDC2EF` | TMultiHexMO |
| `0x124` | `0x55702414` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetMostFrequentMapFieldTerrainType@23EDC2EF` | TMultiHexMO |
| `0x128` | `0x5575EC44` | `AoWE.TStructure.ValidTerrainType@23EDC2EF` | TStructure |
| `0x12C` | `0x557C1848` | `ExploreS.TExplorationSite.GetTerrainTypeImage@23EDC2EF` | TExplorationSite |
| `0x130` | `0x5575E93C` | `AoWE.TStructure.ForceTerrainType@23EDC2EF` | TStructure |
| `0x134` | `0x55703534` | `HSEPack.dpl!ILTer.TILTerrainMO.GetValidTerrainType@23EDC2EF` | TILTerrainMO |
| `0x138` | `0x5575EB0C` | `AoWE.TStructure.GetTopBorderImage@23EDC2EF` | TStructure |
| `0x13C` | `0x5575EB58` | `AoWE.TStructure.GetMiddleBorderImage@23EDC2EF` | TStructure |
| `0x140` | `0x5575EBA4` | `AoWE.TStructure.GetBottomBorderImage@23EDC2EF` | TStructure |
| `0x144` | `0x5575E988` | `AoWE.TStructure.GetDescription@23EDC2EF` | TStructure |
| `0x148` | `0x5575E950` | `AoWE.TStructure.GetName@23EDC2EF` | TStructure |
| `0x14C` | `0x5575EDE8` | `AoWE.TStructure.SetRazed@23EDC2EF` | TStructure |
| `0x150` | `0x5575EDE4` | `AoWE.TStructure.GetRazed@23EDC2EF` | TStructure |
| `0x154` | `0x5575EDDC` | `AoWE.TStructure.GetRazeable@23EDC2EF` | TStructure |
| `0x158` | `0x5576023C` | `AoWE.TStructure.RazeEx@23EDC2EF` | TStructure |
| `0x15C` | `0x5575FE0C` | `AoWE.TStructure.SetupRazeDefenderAG@23EDC2EF` | TStructure |
| `0x160` | `0x5575E88C` | `AoWE.TStructure.CreateTE@23EDC2EF` | TStructure |
| `0x164` | `0x5575E89C` | `AoWE.TStructure.SetupTE@23EDC2EF` | TStructure |
| `0x168` | `0x557C1D28` | `ExploreS.TExplorationSite.ExecuteTE@23EDC2EF` | TExplorationSite |
| `0x16C` | `0x5575F378` | `AoWE.TStructure.GetDefenseRequirements@23EDC2EF` | TStructure |
| `0x170` | `0x5575F374` | `AoWE.TStructure.GetDefensePriority@23EDC2EF` | TStructure |
| `0x174` | `0x557C20A4` | `ExploreS.TExplorationSite.NewDay@23EDC2EF` | TExplorationSite |
| `0x178` | `0x5575F33C` | `AoWE.TStructure.NewTurn@23EDC2EF` | TStructure |
| `0x17C` | `0x5575F36C` | `AoWE.TStructure.SeatedPlayerChanged@23EDC2EF` | TStructure |
| `0x180` | `0x5575F360` | `AoWE.TStructure.ArmyPlaced@23EDC2EF` | TStructure |
| `0x184` | `0x5575F364` | `AoWE.TStructure.ArmyRemoved@23EDC2EF` | TStructure |
| `0x188` | `0x5575F368` | `AoWE.TStructure.ArmyChanged@23EDC2EF` | TStructure |
| `0x18C` | `0x5575EA18` | `AoWE.TStructure.PlaySelectSample@23EDC2EF` | TStructure |
| `0x190` | `0x5575E818` | `AoWE.TStructure.CreateShadow@23EDC2EF` | TStructure |
| `0x194` | `0x5575E850` | `AoWE.TStructure.DestroyShadow@23EDC2EF` | TStructure |
| `0x198` | `0x5575F908` | `AoWE.TStructure.ShowShadow@23EDC2EF` | TStructure |
| `0x19C` | `0x5575F010` | `AoWE.TStructure.BuildingDone@23EDC2EF` | TStructure |
| `0x1A0` | `0x5575EF08` | `AoWE.TStructure.ExecuteRebuild@23EDC2EF` | TStructure |
| `0x1A4` | `0x5575EFD8` | `AoWE.TStructure.ExecuteBuild@23EDC2EF` | TStructure |
| `0x1A8` | `0x5575FD1C` | `AoWE.TStructure.GenerateRazeDefenders@23EDC2EF` | TStructure |
| `0x1AC` | `0x5575FE84` | `AoWE.TStructure.PlaceRazeDefenders@23EDC2EF` | TStructure |
| `0x1B0` | `0x5575FFC8` | `AoWE.TStructure.ExecuteRaze@23EDC2EF` | TStructure |
| `0x1B4` | `0x5575E968` | `AoWE.TStructure.GetCurrentActivityText@23EDC2EF` | TStructure |
| `0x1B8` | `0x5575F4F4` | `AoWE.TStructure.ValidateMap@23EDC2EF` | TStructure |
| `0x1BC` | `0x5575F4F8` | `AoWE.TStructure.MainValidateMap@23EDC2EF` | TStructure |
| `0x1C0` | `0x5575E698` | `AoWE.TStructure.ExecuteAI@23EDC2EF` | TStructure |
| `0x1C4` | `0x5575E69C` | `AoWE.TStructure.UpdateAITarget@23EDC2EF` | TStructure |
| `0x1C8` | `0x557C20D0` | `ExploreS.TExplorationSite.Update@23EDC2EF` | TExplorationSite |
| `0x1CC` | `0x5575EDEC` | `AoWE.TStructure.VisibleForPlayer@23EDC2EF` | TStructure |
| `0x1D0` | `0x5575E990` | `AoWE.TStructure.CanDblClick@23EDC2EF` | TStructure |
| `0x1D4` | `0x5575F37C` | `AoWE.TStructure.ListUnits@23EDC2EF` | TStructure |
| `0x1D8` | `0x5575F434` | `AoWE.TStructure.ListArmies@23EDC2EF` | TStructure |
| `0x1DC` | `0x5575F18C` | `AoWE.TStructure.GetRebuildInfo@23EDC2EF` | TStructure |
| `0x1E0` | `0x5575F1A4` | `AoWE.TStructure.CanRebuild@23EDC2EF` | TStructure |
| `0x1E4` | `0x5575F26C` | `AoWE.TStructure.Rebuild@23EDC2EF` | TStructure |
| `0x1E8` | `0x557602F8` | `AoWE.TStructure.Raze@23EDC2EF` | TStructure |
| `0x1EC` | `0x5575FB80` | `AoWE.TStructure.CanRaze@23EDC2EF` | TStructure |
| `0x1F0` | `0x557C1844` | `ExploreS.TExplorationSite.GetExplored@23EDC2EF` | TExplorationSite |
| `0x1F4` | `0x557C1960` | `ExploreS.TExplorationSite.SetupCombat@23EDC2EF` | TExplorationSite |
| `0x1F8` | `0x557C1890` | `ExploreS.TExplorationSite.ExecuteSearchDone@23EDC2EF` | TExplorationSite |
| `0x1FC` | `0x557C1A20` | `ExploreS.TExplorationSite.ExecuteSearch@23EDC2EF` | TExplorationSite |
| `0x200` | `0x557C1E5C` | `ExploreS.TExplorationSite.Search@23EDC2EF` | TExplorationSite |

### THero  —  VMT `0x55711FEC`, instance `0x9C`, 114 slots, ends `0x1C8`

<details><summary>derivation notes</summary>

```
MODULE: AoWEPACK.dpl (pristine vanilla, image base 0x55700000 — Ghidra program AoWEPACK_vanilla.dpl). All VAs are at the preferred base; the DPL rebases at runtime.

=== VMT BOUNDARY — CONFIRMED TWO INDEPENDENT WAYS ===
The VMT slot array is 0x000..0x1C4 inclusive = 114 slots; first offset past the end is +0x1C8 (VA 0x557121B4).
1. Heuristic: [VMT+0x1C8] = 0x0000000E, not a CODE pointer.
2. Structural proof: Delphi 3's vmtInitTable field at [VMT-0x34] holds 0x557121B4 — i.e. the compiler's own record of where the init table starts, which is exactly VMT+0x1C8. The 0x0E byte is tkRecord, the head of that init table (3 managed AnsiString fields at instance offsets 0x60, 0x64, 0x94; typeinfo 0x558FB72C). The init table runs 0x22 bytes and is followed at 0x557121D6 by the class-name ShortString "THero" (which is what [VMT-0x20] points at).

=== DELPHI 3 VMT HEADER (verified on THero, offsets relative to VMT) ===
 -0x40 vmtSelfPtr        = 0x55711FEC (== VMT, verified for all four classes in the chain)
 -0x3C vmtIntfTable      = 0
 -0x38 vmtAutoTable      = 0
 -0x34 vmtInitTable      = 0x557121B4   <-- the reliable end-of-VMT marker when non-zero
 -0x30 vmtTypeInfo       = 0
 -0x2C vmtFieldTable     = 0
 -0x28 vmtMethodTable    = 0
 -0x24 vmtDynamicTable   = 0
 -0x20 vmtClassName      = 0x557121D6 -> \x05"THero"
 -0x1C vmtInstanceSize   = 0x9C
 -0x18 vmtParent         = 0x55710700 (pointer TO the parent classref; [0x55710700] = 0x55710740 = TAbstractUnit VMT)
 -0x14 vmtSafeCallException = 0x557010C8
 -0x10 vmtDefaultHandler    = 0x557010D0
 -0x0C vmtNewInstance       = 0x55701098
 -0x08 vmtFreeInstance      = 0x557010A0
 -0x04 vmtDestroy           = 0x557868F4 = AoWE.THero.Destroy@23EDC2EF
NOTE: THero.Destroy is at VMT-0x04, i.e. in the header, NOT in the slot array below. Do not look for it among the 114 slots.

=== ANCESTOR CHAIN (derived, with per-class VMT length) ===
  Engine.TEObject (EngineP.dpl, EXTERNAL — parentref 0x558FC92C is an IAT slot importing "EngineP.dpl!Engine..TEObject@BD8FE92F")
    -> TCustomAbilityList  VMT=0x5570F3DC  instsize=0x10  vmt_len=0x5C  (23 slots)
    -> TAbilityOwner       VMT=0x5570F588  instsize=0x14  vmt_len=0x9C  (39 slots)
    -> TAbstractUnit       VMT=0x55710740  instsize=0x3C  vmt_len=0x1B8 (110 slots)
    -> THero               VMT=0x55711FEC  instsize=0x9C  vmt_len=0x1C8 (114 slots)
THero's parent is TAbstractUnit, NOT TUnit — TUnit is a sibling branch.
Ancestor VMT lengths were confirmed by a second marker: for all three ancestors vmtInitTable is 0 (no managed fields), but their class-name ShortString ([VMT-0x20]) sits at exactly VMT+vmt_len (delta 0), so the slot arrays end precisely there.

=== NEW VIRTUALS INTRODUCED BY THero ===
TAbstractUnit's VMT is 0x1B8 long, so slots +0x1B8..+0x1C4 (4 slots) are THero-introduced: GetNickname, SetNickname, SetHeroResourceIndex, EditDropMsg. Everything at +0x000..+0x1B4 is a slot inherited from the ancestor layout, either overridden by THero or left pointing at the ancestor's implementation.

=== OWNERSHIP TALLY (implementing class per slot) ===
  THero 69, TAbstractUnit 20, TAbilityOwner 14, TEObject 10, TCustomAbilityList 1.
The 45 non-THero slots are inherited implementations — hooking those addresses affects every descendant sharing them, not just heroes.

=== TEObject SLOTS ARE IMPORT THUNKS, NOT LOCAL CODE ===
The 10 slots whose targets lie in 0x55703064..0x55703104 are NOT functions in AoWEPACK.dpl. That range is a table of 8-byte stubs, each `mov eax,eax; jmp dword ptr [IAT]`, forwarding to EngineP.dpl. Ghidra has function symbols on only 3 of the 10 used here (Editor, GetControlStyle, SetArrayOwner) and reports "No function found" for the rest — the names below were recovered by parsing the PE import table and mapping each stub's IAT slot to its import name. Full stub table for reference:
  0x55703064 -> [0x558FC72C] Engine.TEObject.Create
  0x5570306C -> [0x558FC728] Engine.TEObject.Destroy
  0x55703074 -> [0x558FC724] Engine.TEObject.Cl
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x55786A80` | `AoWE.THero.SetOwner@23EDC2EF` | THero |
| `0x00C` | `0x55786B1C` | `AoWE.THero.GetEngine@23EDC2EF` | THero |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x55788880` | `AoWE.THero.ReadWrite@23EDC2EF` | THero |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x55786848` | `AoWE.THero.Create@23EDC2EF` | THero |
| `0x024` | `0x55786C10` | `AoWE.THero.ClassID@23EDC2EF` | THero |
| `0x028` | `0x5577EBC4` | `AoWE.TAbstractUnit.AddRef@23EDC2EF` | TAbstractUnit |
| `0x02C` | `0x5577EBCC` | `AoWE.TAbstractUnit.Release@23EDC2EF` | TAbstractUnit |
| `0x030` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x55788C04` | `AoWE.THero.MsgProc@23EDC2EF` | THero |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x55788104` | `AoWE.THero.GetAbSet@23EDC2EF` | THero |
| `0x050` | `0x557880FC` | `AoWE.THero.SetAbSet@23EDC2EF` | THero |
| `0x054` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x058` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x05C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x060` | `0x5577F69C` | `AoWE.TAbstractUnit.GetOwnerName@23EDC2EF` | TAbstractUnit |
| `0x064` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x068` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x06C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x070` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x074` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x078` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x07C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x080` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x084` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x088` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x08C` | `0x55786B10` | `AoWE.THero.GetAbilitySelectionTypes@23EDC2EF` | THero |
| `0x090` | `0x55786BDC` | `AoWE.THero.Changed@23EDC2EF` | THero |
| `0x094` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x098` | `0x5577F6EC` | `AoWE.TAbstractUnit.RemoveAbility@23EDC2EF` | TAbstractUnit |
| `0x09C` | `0x557872C0` | `AoWE.THero.GetUpkeep@23EDC2EF` | THero |
| `0x0A0` | `0x55786A7C` | `AoWE.THero.GetUnitLevel@23EDC2EF` | THero |
| `0x0A4` | `0x55786F9C` | `AoWE.THero.GetRace@23EDC2EF` | THero |
| `0x0A8` | `0x55788354` | `AoWE.THero.GetInherentAttack@23EDC2EF` | THero |
| `0x0AC` | `0x557883DC` | `AoWE.THero.GetInherentDefense@23EDC2EF` | THero |
| `0x0B0` | `0x55788478` | `AoWE.THero.GetInherentDamage@23EDC2EF` | THero |
| `0x0B4` | `0x55788500` | `AoWE.THero.GetInherentResistance@23EDC2EF` | THero |
| `0x0B8` | `0x5577F570` | `AoWE.TAbstractUnit.GetInherentAbility@23EDC2EF` | TAbstractUnit |
| `0x0BC` | `0x5577F5A8` | `AoWE.TAbstractUnit.GetInherentAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x0C0` | `0x55788360` | `AoWE.THero.GetAttack@23EDC2EF` | THero |
| `0x0C4` | `0x557883E8` | `AoWE.THero.GetDefense@23EDC2EF` | THero |
| `0x0C8` | `0x55788484` | `AoWE.THero.GetDamage@23EDC2EF` | THero |
| `0x0CC` | `0x5578850C` | `AoWE.THero.GetResistance@23EDC2EF` | THero |
| `0x0D0` | `0x5578859C` | `AoWE.THero.GetHits@23EDC2EF` | THero |
| `0x0D4` | `0x557885C0` | `AoWE.THero.GetMoves@23EDC2EF` | THero |
| `0x0D8` | `0x55787018` | `AoWE.THero.GetMovePoints@23EDC2EF` | THero |
| `0x0DC` | `0x5578701C` | `AoWE.THero.SetMovePoints@23EDC2EF` | THero |
| `0x0E0` | `0x55787044` | `AoWE.THero.GetHitPoints@23EDC2EF` | THero |
| `0x0E4` | `0x55787048` | `AoWE.THero.SetHitPoints@23EDC2EF` | THero |
| `0x0E8` | `0x55786FB8` | `AoWE.THero.GetMoveTypes@23EDC2EF` | THero |
| `0x0EC` | `0x55786FD8` | `AoWE.THero.GetImmunityTypes@23EDC2EF` | THero |
| `0x0F0` | `0x55786FF8` | `AoWE.THero.GetProtectionTypes@23EDC2EF` | THero |
| `0x0F4` | `0x557887DC` | `AoWE.THero.GetFace@23EDC2EF` | THero |
| `0x0F8` | `0x55786FA4` | `AoWE.THero.GetName@23EDC2EF` | THero |
| `0x0FC` | `0x5578707C` | `AoWE.THero.GetAlignment@23EDC2EF` | THero |
| `0x100` | `0x55788680` | `AoWE.THero.GetPreviewImage@23EDC2EF` | THero |
| `0x104` | `0x5577FCCC` | `AoWE.TAbstractUnit.GetTransportCapacity@23EDC2EF` | TAbstractUnit |
| `0x108` | `0x5577FD40` | `AoWE.TAbstractUnit.GetTransporter@23EDC2EF` | TAbstractUnit |
| `0x10C` | `0x55786C34` | `AoWE.THero.GetGender@23EDC2EF` | THero |
| `0x110` | `0x5577EBB4` | `AoWE.TAbstractUnit.GetBloodType@23EDC2EF` | TAbstractUnit |
| `0x114` | `0x55786C38` | `AoWE.THero.GetUnitType@23EDC2EF` | THero |
| `0x118` | `0x557875BC` | `AoWE.THero.GetUnitGFXResourceIndex@23EDC2EF` | THero |
| `0x11C` | `0x55781208` | `AoWE.TAbstractUnit.CanAddToList@23EDC2EF` | TAbstractUnit |
| `0x120` | `0x5577ECCC` | `AoWE.TAbstractUnit.GetWallCombatFeatures@23EDC2EF` | TAbstractUnit |
| `0x124` | `0x55786970` | `AoWE.THero.GetCampaignTransferPoints@23EDC2EF` | THero |
| `0x128` | `0x55788614` | `AoWE.THero.GetCastingPointsMax@23EDC2EF` | THero |
| `0x12C` | `0x55788644` | `AoWE.THero.GetCastingPoints@23EDC2EF` | THero |
| `0x130` | `0x5578864C` | `AoWE.THero.SetCastingPoints@23EDC2EF` | THero |
| `0x134` | `0x557885E4` | `AoWE.THero.GetPowerGeneration@23EDC2EF` | THero |
| `0x138` | `0x55786C3C` | `AoWE.THero.NewDay@23EDC2EF` | THero |
| `0x13C` | `0x55787FCC` | `AoWE.THero.NewTurn@23EDC2EF` | THero |
| `0x140` | `0x55780E28` | `AoWE.TAbstractUnit.NewTurnDone@23EDC2EF` | TAbstractUnit |
| `0x144` | `0x5578831C` | `AoWE.THero.GetAbilityLevel@23EDC2EF` | THero |
| `0x148` | `0x5578827C` | `AoWE.THero.GetAbilityEnabled@23EDC2EF` | THero |
| `0x14C` | `0x557882AC` | `AoWE.THero.GetAbilitySet@23EDC2EF` | THero |
| `0x150` | `0x557882DC` | `AoWE.THero.GetAbilityName@23EDC2EF` | THero |
| `0x154` | `0x55788274` | `AoWE.THero.GetAbilityOwner@23EDC2EF` | THero |
| `0x158` | `0x55788114` | `AoWE.THero.GetAbilityCount@23EDC2EF` | THero |
| `0x15C` | `0x55787670` | `AoWE.THero.GetExperience@23EDC2EF` | THero |
| `0x160` | `0x55787674` | `AoWE.THero.SetExperience@23EDC2EF` | THero |
| `0x164` | `0x5578770C` | `AoWE.THero.GetNextLevelExperience@23EDC2EF` | THero |
| `0x168` | `0x55786C30` | `AoWE.THero.GetDescription@23EDC2EF` | THero |
| `0x16C` | `0x557872D0` | `AoWE.THero.SetPlayer@23EDC2EF` | THero |
| `0x170` | `0x5577F4F4` | `AoWE.TAbstractUnit.GetIndependentRelation@23EDC2EF` | TAbstractUnit |
| `0x174` | `0x55786C18` | `AoWE.THero.GetObtainValue@23EDC2EF` | THero |
| `0x178` | `0x5577F184` | `AoWE.TAbstractUnit.GetUnitSize@23EDC2EF` | TAbstractUnit |
| `0x17C` | `0x5577EED8` | `AoWE.TAbstractUnit.GetUnitMoraleValue@23EDC2EF` | TAbstractUnit |
| `0x180` | `0x55787264` | `AoWE.THero.CanActivate@23EDC2EF` | THero |
| `0x184` | `0x557873E8` | `AoWE.THero.Activate@23EDC2EF` | THero |
| `0x188` | `0x5578754C` | `AoWE.THero.Deactivate@23EDC2EF` | THero |
| `0x18C` | `0x55780328` | `AoWE.TAbstractUnit.MovedTo@23EDC2EF` | TAbstractUnit |
| `0x190` | `0x557825B0` | `AoWE.TAbstractUnit.CanDisband@23EDC2EF` | TAbstractUnit |
| `0x194` | `0x55786D7C` | `AoWE.THero.CanJoin@23EDC2EF` | THero |
| `0x198` | `0x55782324` | `AoWE.TAbstractUnit.JoinAmount@23EDC2EF` | TAbstractUnit |
| `0x19C` | `0x55786EB4` | `AoWE.THero.OfferToJoin@23EDC2EF` | THero |
| `0x1A0` | `0x55782440` | `AoWE.TAbstractUnit.GetJoinMessage@23EDC2EF` | TAbstractUnit |
| `0x1A4` | `0x55786B30` | `AoWE.THero.ShowEx@23EDC2EF` | THero |
| `0x1A8` | `0x5577FD3C` | `AoWE.TAbstractUnit.UnitKilled@23EDC2EF` | TAbstractUnit |
| `0x1AC` | `0x55787164` | `AoWE.THero.Killed@23EDC2EF` | THero |
| `0x1B0` | `0x55787224` | `AoWE.THero.Resurrect@23EDC2EF` | THero |
| `0x1B4` | `0x55787244` | `AoWE.THero.Animate@23EDC2EF` | THero |
| `0x1B8` | `0x55786AB0` | `AoWE.THero.GetNickname@23EDC2EF` | THero |
| `0x1BC` | `0x55786AC4` | `AoWE.THero.SetNickname@23EDC2EF` | THero |
| `0x1C0` | `0x55788840` | `AoWE.THero.SetHeroResourceIndex@23EDC2EF` | THero |
| `0x1C4` | `0x55788B40` | `AoWE.THero.EditDropMsg@23EDC2EF` | THero |

### TItem  —  VMT `0x5570FAFC`, instance `0x4C`, 45 slots, ends `0xB4`

<details><summary>derivation notes</summary>

```
COMPLETE — 45 slots, +0x00..+0x0B0, every one has a real RTTI symbol (zero unknowns). Class name ShortString "TItem" @0x5570FBD2; class-ref export AoWE..TItem@228E47F6 = the VMT address itself.

== HOW DERIVED / CONFIDENCE ==
Parsed Modding Resources/AoWEPACK_original_backup.dpl (same bytes Ghidra holds) and resolved every slot through the DPL's own export table (10036 named exports) plus its import table. Cross-checked against Ghidra (AoWEPACK_vanilla.dpl) with get_function_by_address on 5 sampled slots (0x20 Create, 0xA0 Use, 0x30 Clear, 0x8C GetAbilitySelectionTypes, 0xB0 Deactivate) and read_memory on the header + tail — all identical. Scripts: <scratchpad>/ad_titem_full.py, ad_titem_thunks.py, ad_titem_chain.py, ad_teobject.py; row dump in ad_titem_rows.json.

== ⚠ TRAP: vmtParent IS DOUBLE-INDIRECT ==
The recipe in the task brief says [VMT-0x18] -> parent classref. It is actually a POINTER TO a classref cell: parent = [[VMT-0x18]]. Reading it singly gives 0x5570F548, which is not a VMT and decodes as string bytes ("bili"), producing a bogus "chain". Correct read gives 0x5570F588 = TAbilityOwner. Same idiom as Delphi's TObject.ClassParent (MOV EAX,[EAX+vmtParent]; MOV EAX,[EAX]). Additionally, when the parent lives in another package the cell is an IAT entry, so in the on-disk image it holds a hint/name RVA (e.g. 0x002086EA), not an address — dereference it against the import table instead.

== FULL VMT HEADER LAYOUT (this Delphi build; differs from stock Delphi 3) ==
Empirically verified on TItem, TAbilityOwner, TCustomAbilityList and EngineP's TEObject:
  [VMT-0x40] vmtSelfPtr        = 0x5570FAFC (== VMT; a reliable "is this really a VMT?" test)
  [VMT-0x3C] vmtIntfTable      = 0
  [VMT-0x38] vmtAutoTable      = 0
  [VMT-0x34] vmtInitTable      = 0x5570FBB0
  [VMT-0x30] vmtTypeInfo       = 0
  [VMT-0x2C] vmtFieldTable     = 0
  [VMT-0x28] vmtMethodTable    = 0
  [VMT-0x24] vmtDynamicTable   = 0
  [VMT-0x20] vmtClassName      -> ShortString "TItem" @0x5570FBD2
  [VMT-0x1C] vmtInstanceSize   = 0x4C
  [VMT-0x18] vmtParent         -> cell holding 0x5570F588 (TAbilityOwner)   <-- double indirect
  [VMT-0x14] vmtSafeCallException = 0x557010C8 -> VCL30.dpl!System.TObject.SafeCallException
  [VMT-0x10] vmtDefaultHandler   = 0x557010D0 -> VCL30.dpl!System.TObject.DefaultHandler
  [VMT-0x0C] vmtNewInstance      = 0x55701098 -> VCL30.dpl!System.TObject.NewInstance
  [VMT-0x08] vmtFreeInstance     = 0x557010A0 -> VCL30.dpl!System.TObject.FreeInstance
  [VMT-0x04] vmtDestroy          = 0x55793E9C -> AoWE.TItem.Destroy@23EDC2EF
Note the header is 0x40 bytes, not stock D3's 0x4C: vmtAfterConstruction/vmtBeforeDestruction/vmtDispatch are absent (3 dwords fewer between vmtClassName and vmtDestroy).
⚠ TItem.Destroy is at VMT-0x04, NOT a positive slot — a VMT-slot hook table that only walks +0x00 upward will miss the destructor entirely.

== VMT END = +0xB4, PROVEN STRUCTURALLY ==
[VMT+0xB4] = 0x0000000E, not a code pointer. Better proof than the "not in CODE" heuristic: vmtInitTable ([VMT-0x34]) = 0x5570FBB0 = VMT+0xB4 exactly, i.e. the RTTI init-table record is laid out immediately after the last VMT slot, so the last slot is +0xB0. Bytes past the end: +0xB4=0000000E, +0xB8=00030000, +0xBC=B72C0000, +0xC0=0018558F.

== ANCESTOR CHAIN (derived) AND WHERE EACH SLOT IS INTRODUCED ==
  TItem              VMT 0x5570FAFC  instsize 0x4C  vmt_end 0xB4 (45 slots)
  TAbilityOwner      VMT 0x5570F588  instsize 0x14  vmt_end 0x9C (39 slots)
  TCustomAbilityList VMT 0x5570F3DC  instsize 0x10  vmt_end 0x5C (23 slots)
  TEObject           VMT 0x5550C188 in EngineP.dpl (base 0x55500000), instsize 0x8, vmt_end 0x4C (19 slots)
  System.TObject     (VCL30.dpl, external)
Introduction ranges follow the vmt_end boundaries exactly (19+4+16+6 = 45):
  +0x00..+0x48 (19 slots) introduced by TEObject
  +0x4C..+0x58 (4 slots)  introduced by TCustomAbilityList
  +0x5C..+0x98 (16 slots) introduced by TAbilityOwner
  +0x9C..+0xB0 (6 slots)  introduced by TItem   (Can
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x55793F18` | `AoWE.TItem.SetOwner@23EDC2EF` | TItem |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557945C8` | `AoWE.TItem.ReadWrite@23EDC2EF` | TItem |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55793E48` | `AoWE.TItem.Create@23EDC2EF` | TItem |
| `0x24` | `0x5579437C` | `AoWE.TItem.ClassID@23EDC2EF` | TItem |
| `0x28` | `0x55793EF8` | `AoWE.TItem.AddRef@23EDC2EF` | TItem |
| `0x2C` | `0x55793F00` | `AoWE.TItem.Release@23EDC2EF` | TItem |
| `0x30` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x55794878` | `AoWE.TItem.MsgProc@23EDC2EF` | TItem |
| `0x48` | `0x55794274` | `AoWE.TItem.SetArrayOwner@23EDC2EF` | TItem |
| `0x4C` | `0x5574E0E0` | `AoWE.TCustomAbilityList.GetAbSet@23EDC2EF` | TCustomAbilityList |
| `0x50` | `0x5574F308` | `AoWE.TAbilityOwner.SetAbSet@23EDC2EF` | TAbilityOwner |
| `0x54` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x58` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x5C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x60` | `0x55794498` | `AoWE.TItem.GetOwnerName@23EDC2EF` | TItem |
| `0x64` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x68` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x6C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x70` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x74` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x78` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x7C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x80` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x84` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x88` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x8C` | `0x557944AC` | `AoWE.TItem.GetAbilitySelectionTypes@23EDC2EF` | TItem |
| `0x90` | `0x55794360` | `AoWE.TItem.Changed@23EDC2EF` | TItem |
| `0x94` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x98` | `0x5574F5EC` | `AoWE.TAbilityOwner.RemoveAbility@23EDC2EF` | TAbilityOwner |
| `0x9C` | `0x557940AC` | `AoWE.TItem.CanUse@23EDC2EF` | TItem |
| `0xA0` | `0x557941B4` | `AoWE.TItem.Use@23EDC2EF` | TItem |
| `0xA4` | `0x55793F68` | `AoWE.TItem.ExecuteUse@23EDC2EF` | TItem |
| `0xA8` | `0x5579452C` | `AoWE.TItem.Show@23EDC2EF` | TItem |
| `0xAC` | `0x55794308` | `AoWE.TItem.Activate@23EDC2EF` | TItem |
| `0xB0` | `0x55794344` | `AoWE.TItem.Deactivate@23EDC2EF` | TItem |

### TRangedAttackAbility  —  VMT `0x5571E8D4`, instance `0x30`, 72 slots, ends `0x120`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
Two independent sources agree byte-for-byte. (1) File parse of "Modding Resources/AoWEPACK_original_backup.dpl" (same bytes Ghidra holds) using the Delphi RTTI recipe. (2) Ghidra read_memory at 0x5571E8D4 length 304 returned an identical byte run. Symbols come from the DPL's own export table (.edata: 10036 exports, 10033 distinct VAs) — i.e. Delphi's published RTTI names, not inference. Four slots were cross-checked against mcp__ghidra__get_function_by_address (0x5576E5C4, 0x5576ECF0, 0x55764C70, 0x5574E814) and matched exactly.

VMT LOCATION
Class-name ShortString "\x14TRangedAttackAbility" at 0x5571E9F4; the dword pointing at it is at 0x5571E8B4, so VMT = 0x5571E8B4 + 0x20 = 0x5571E8D4. [VMT-0x1C] = 0x30 instance size, [VMT-0x18] = 0x5571D8F0 -> parent VMT 0x5571D930 (TAdjustableAbility).

WHERE THE VMT ENDS — 0x120, and it is unambiguous
Slot +0x11C (0x5576E6B0) is the last CODE pointer. The dword at +0x120 reads 0x61525414, which is not a code address: those bytes are 14 54 52 61 6E 67 65 64 41 74 74 61 63 6B 41 62 ... = the length-prefixed ShortString "\x14TRangedAttackAbility" itself, which sits immediately after the VMT at 0x5571E9F4 (= VMT + 0x120). Exactly the failure mode the brief warned about. So: 72 slots, 0x00..0x11C inclusive.

ANCESTRY (each link derived from [VMT-0x18], not assumed)
  TRangedAttackAbility  VMT=0x5571E8D4  instsize=0x30  72 slots (ends 0x120)
  TAdjustableAbility    VMT=0x5571D930  instsize=0x28  67 slots (ends 0x10C)
  TAbility              VMT=0x5570F254  instsize=0x24  67 slots (ends 0x10C)
  Engine.TEObject       (external — TAbility's parent classref 0x558FC92C lies in .idata, i.e. imported from EngineP.dpl, so the chain leaves this module here)

SLOT OWNERSHIP TALLY (72 total)
  Engine.TEObject ....... 17 slots (inherited, imported)
  TAbility .............. 37 slots (inherited)
  TAdjustableAbility ..... 1 slot  (inherited)
  TRangedAttackAbility .. 17 slots (12 overrides + 5 brand-new virtuals)

TEObject SLOTS ARE IMPORT THUNKS — IMPORTANT FOR PATCHING
The 17 TEObject slots do not hold EngineP.dpl addresses. Each holds a local AoWEPACK stub in the 0x55703074..0x55703104 block of the form "JMP dword ptr [<IAT slot>]" followed by "MOV EAX,EAX" padding (verified: 0x55703074 = FF 25 24 C7 8F 55 -> IAT 0x558FC724). Ghidra has no function defined at these addresses (get_function_by_address returns "No function found"), which is why they look nameless in a decompile — the name comes from the import table. target_va below is the thunk VA (what is actually stored in the VMT slot), which is the address that matters for a VMT-slot patch. IAT slots for reference: +0x000->0x558FC724, +0x004->0x558FC6F0, +0x008->0x558FC6EC, +0x00C->0x558FC6F4, +0x010->0x558FC708, +0x014->0x558FC704, +0x01C->0x558FC6DC, +0x024->0x558FC714, +0x028->0x558FC720, +0x02C->0x558FC71C, +0x030->0x558FC718, +0x034->0x558FC700, +0x038->0x558FC710, +0x03C->0x558FC6FC, +0x040->0x558FC70C, +0x044->0x558FC6E4, +0x048->0x558FC6E8.

WHAT TRangedAttackAbility ACTUALLY ADDS
Five new virtuals at the tail, past every ancestor's VMT end (0x10C) — the "RA" (ranged-attack) accessor block:
  +0x10C GetRangeRA, +0x110 GetDamageRA, +0x114 GetAttackRA, +0x118 GetAttackRepeatRA, +0x11C GetDamageTypesRA
These are tiny (GetRangeRA is 4 bytes, GetDamageTypesRA is 7) — plain field getters over the 8 bytes of instance data TRangedAttackAbility adds on top of TAdjustableAbility's 0x28.
Twelve overrides of inherited slots: +0x020 Create, +0x084 GetCombatMode, +0x088 GetWallCombatFeatures, +0x098 GetControlType, +0x09C fcValidRoundDistance, +0x0A0 fcPrefetchCombatCommands, +0x0A4 fcExecuteCombatCommand, +0x0D8 GetDamageValue, +0x0DC GetDamageValueEx, +0x0E0 GetOffensiveStrength, +0x0E4 fcGetDamageValueEx, +0x104 GetCombatInfo.

TAdjustableAbility IS NEARLY A NO-OP LAYER
It overrides exactly ONE slot versus TAbility — +0x054 GetAbilityType (0x5574EF1C -> 0x55764C70, a 4-byte stub) — and adds 4 bytes of instance data. Worth knowing
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x5574F07C` | `AoWE.TAbility.ReadWrite@23EDC2EF` | TAbility |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5576E5C4` | `AoWE.TRangedAttackAbility.Create@23EDC2EF` | TRangedAttackAbility |
| `0x24` | `0x55703094` | `Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5574EF2C` | `AoWE.TAbility.Execute@23EDC2EF` | TAbility |
| `0x50` | `0x5574E9AC` | `AoWE.TAbility.GetHidden@23EDC2EF` | TAbility |
| `0x54` | `0x55764C70` | `AoWE.TAdjustableAbility.GetAbilityType@23EDC2EF` | TAdjustableAbility |
| `0x58` | `0x5574E97C` | `AoWE.TAbility.GetName@23EDC2EF` | TAbility |
| `0x5C` | `0x5574E990` | `AoWE.TAbility.GetAttack@23EDC2EF` | TAbility |
| `0x60` | `0x5574E994` | `AoWE.TAbility.GetDefense@23EDC2EF` | TAbility |
| `0x64` | `0x5574E998` | `AoWE.TAbility.GetResistance@23EDC2EF` | TAbility |
| `0x68` | `0x5574E99C` | `AoWE.TAbility.GetDamage@23EDC2EF` | TAbility |
| `0x6C` | `0x5574E9A0` | `AoWE.TAbility.GetMoveTypes@23EDC2EF` | TAbility |
| `0x70` | `0x5574E9B0` | `AoWE.TAbility.GetLevel@23EDC2EF` | TAbility |
| `0x74` | `0x5574EEF4` | `AoWE.TAbility.GetEnabled@23EDC2EF` | TAbility |
| `0x78` | `0x5574EF00` | `AoWE.TAbility.GetImmunityTypes@23EDC2EF` | TAbility |
| `0x7C` | `0x5574EF0C` | `AoWE.TAbility.GetProtectionTypes@23EDC2EF` | TAbility |
| `0x80` | `0x5574E958` | `AoWE.TAbility.GetSkillPoints@23EDC2EF` | TAbility |
| `0x84` | `0x5576E6B8` | `AoWE.TRangedAttackAbility.GetCombatMode@23EDC2EF` | TRangedAttackAbility |
| `0x88` | `0x5576E6D4` | `AoWE.TRangedAttackAbility.GetWallCombatFeatures@23EDC2EF` | TRangedAttackAbility |
| `0x8C` | `0x5574E704` | `AoWE.TAbility.GetSourceName@23EDC2EF` | TAbility |
| `0x90` | `0x5574E948` | `AoWE.TAbility.GetInherent@23EDC2EF` | TAbility |
| `0x94` | `0x5574E954` | `AoWE.TAbility.GetInherentLevel@23EDC2EF` | TAbility |
| `0x98` | `0x5576E604` | `AoWE.TRangedAttackAbility.GetControlType@23EDC2EF` | TRangedAttackAbility |
| `0x9C` | `0x5576ECF0` | `AoWE.TRangedAttackAbility.fcValidRoundDistance@23EDC2EF` | TRangedAttackAbility |
| `0xA0` | `0x5576EC10` | `AoWE.TRangedAttackAbility.fcPrefetchCombatCommands@23EDC2EF` | TRangedAttackAbility |
| `0xA4` | `0x5576EB70` | `AoWE.TRangedAttackAbility.fcExecuteCombatCommand@23EDC2EF` | TRangedAttackAbility |
| `0xA8` | `0x5574EF30` | `AoWE.TAbility.NewDay@23EDC2EF` | TAbility |
| `0xAC` | `0x5574EF34` | `AoWE.TAbility.NewTurn@23EDC2EF` | TAbility |
| `0xB0` | `0x5574EF40` | `AoWE.TAbility.CanActivate@23EDC2EF` | TAbility |
| `0xB4` | `0x5574EF68` | `AoWE.TAbility.Activate@23EDC2EF` | TAbility |
| `0xB8` | `0x5574EFDC` | `AoWE.TAbility.CanActivateCombat@23EDC2EF` | TAbility |
| `0xBC` | `0x5574F004` | `AoWE.TAbility.ActivateCombat@23EDC2EF` | TAbility |
| `0xC0` | `0x5574EF18` | `AoWE.TAbility.ListSpells@23EDC2EF` | TAbility |
| `0xC4` | `0x5574E8B8` | `AoWE.TAbility.CanExpand@23EDC2EF` | TAbility |
| `0xC8` | `0x5574E908` | `AoWE.TAbility.ExpandCost@23EDC2EF` | TAbility |
| `0xCC` | `0x5574E8F4` | `AoWE.TAbility.ExpandName@23EDC2EF` | TAbility |
| `0xD0` | `0x5574E90C` | `AoWE.TAbility.Expand@23EDC2EF` | TAbility |
| `0xD4` | `0x5574E91C` | `AoWE.TAbility.Remove@23EDC2EF` | TAbility |
| `0xD8` | `0x5576E764` | `AoWE.TRangedAttackAbility.GetDamageValue@23EDC2EF` | TRangedAttackAbility |
| `0xDC` | `0x5576E7FC` | `AoWE.TRangedAttackAbility.GetDamageValueEx@23EDC2EF` | TRangedAttackAbility |
| `0xE0` | `0x5576E704` | `AoWE.TRangedAttackAbility.GetOffensiveStrength@23EDC2EF` | TRangedAttackAbility |
| `0xE4` | `0x5576E8D4` | `AoWE.TRangedAttackAbility.fcGetDamageValueEx@23EDC2EF` | TRangedAttackAbility |
| `0xE8` | `0x5574E814` | `AoWE.TAbility.fcGetDamageValue@23EDC2EF` | TAbility |
| `0xEC` | `0x5574E844` | `AoWE.TAbility.tcGetDamageValueEx@23EDC2EF` | TAbility |
| `0xF0` | `0x5574E868` | `AoWE.TAbility.tcGetDamageValue@23EDC2EF` | TAbility |
| `0xF4` | `0x5574EF20` | `AoWE.TAbility.CombatObjectDestroyed@23EDC2EF` | TAbility |
| `0xF8` | `0x5574EF38` | `AoWE.TAbility.NewCombatTurn@23EDC2EF` | TAbility |
| `0xFC` | `0x5574EF3C` | `AoWE.TAbility.CombatDone@23EDC2EF` | TAbility |
| `0x100` | `0x5574E9D0` | `AoWE.TAbility.ListInfo@23EDC2EF` | TAbility |
| `0x104` | `0x5576EA8C` | `AoWE.TRangedAttackAbility.GetCombatInfo@23EDC2EF` | TRangedAttackAbility |
| `0x108` | `0x5574E978` | `AoWE.TAbility.AbilityDataClass@23EDC2EF` | TAbility |
| `0x10C` | `0x5576E610` | `AoWE.TRangedAttackAbility.GetRangeRA@23EDC2EF` | TRangedAttackAbility |
| `0x110` | `0x5576E614` | `AoWE.TRangedAttackAbility.GetDamageRA@23EDC2EF` | TRangedAttackAbility |
| `0x114` | `0x5576E65C` | `AoWE.TRangedAttackAbility.GetAttackRA@23EDC2EF` | TRangedAttackAbility |
| `0x118` | `0x5576E6AC` | `AoWE.TRangedAttackAbility.GetAttackRepeatRA@23EDC2EF` | TRangedAttackAbility |
| `0x11C` | `0x5576E6B0` | `AoWE.TRangedAttackAbility.GetDamageTypesRA@23EDC2EF` | TRangedAttackAbility |

### TStrikeCA  —  VMT `0x5571E344`, instance `0x1C`, 28 slots, ends `0x70`

<details><summary>derivation notes</summary>

```
ALL ADDRESSES ARE PREFERRED-BASE VAs (image base 0x55700000); the DPL rebases at runtime.

WHY vmt_end = 0x70 (hard proof, not a guess): the dword at VMT+0x70 is 0x5571E3B4, which is exactly the value of vmtClassName ([VMT-0x20]). Its bytes are 09 'TStrikeCA' — the class-name ShortString, which Delphi lays down immediately after the VMT. So the VMT is exactly 0x70 bytes = 28 virtual slots (+0x00..+0x6C). Nothing at or beyond +0x70 is a method pointer.

INHERITANCE CHAIN (derived by walking vmtParent = [VMT-0x18]):
  TStrikeCA       VMT=0x5571E344  instsize=0x1C  vmt_end=0x70  (28 slots)
  TDamageCA       VMT=0x557162F4  instsize=0x18  vmt_end=0x70  (28 slots)
  TSingleTargetCA VMT=0x557161CC  instsize=0x10  vmt_end=0x64  (25 slots)
  TCombatAction   VMT=0x557160B4  instsize=0x0C  vmt_end=0x64  (25 slots)
  Engine.TEObject -- NOT in this module; vmtParent is IAT slot 0x558FC92C = "Engine..TEObject@BD8FE92F" imported from EngineP.dpl. Its VMT is 0x4C long (19 slots) - measured from two direct TEObject descendants in AoWEPACK that add no virtuals of their own (TUnitProduction VMT=0x5570A0D0 and TProductionSettings VMT=0x5570A4B4, both vmt_end=0x4C).
  TObject         (VCL30.dpl)

DELPHI 2/3 VMT HEADER (confirmed: vmtSelfPtr at -0x40 equals the VMT address):
  -0x40 SelfPtr           = 0x5571E344
  -0x3C..-0x24            = 0 (IntfTable, AutoTable, InitTable, TypeInfo, FieldTable, MethodTable, DynamicTable all NULL -> TStrikeCA has NO published fields, NO RTTI type info, and NO dynamic/message methods)
  -0x20 ClassName         = 0x5571E3B4 -> "TStrikeCA"
  -0x1C InstanceSize      = 0x1C
  -0x18 Parent            = 0x557162B4 (classref cell holding TDamageCA's VMT 0x557162F4)
  -0x14 SafeCallException = 0x557010C8 thunk -> VCL30.dpl  System.TObject.SafeCallException@23EDC2EF
  -0x10 DefaultHandler    = 0x557010D0 thunk -> VCL30.dpl  System.TObject.DefaultHandler@23EDC2EF
  -0x0C NewInstance       = 0x55701098 thunk -> VCL30.dpl  System.TObject.NewInstance@23EDC2EF
  -0x08 FreeInstance      = 0x557010A0 thunk -> VCL30.dpl  System.TObject.FreeInstance@23EDC2EF
  -0x04 Destroy           = 0x5570306C thunk -> EngineP.dpl Engine.TEObject.Destroy@23EDC2EF  (NOT overridden anywhere in the chain)

IMPORT-THUNK MECHANISM (this is why Ghidra reports "No function found" for the 0x5570xxxx slot targets, and why get_function_by_address/decompile fail there): every slot whose owner is TEObject points at an 8-byte import stub in the thunk table at the start of CODE. Layout per entry: FF 25 <imm32 IAT ptr> followed by 8B C0 padding. E.g. 0x55703074 = "jmp dword ptr [0x558FC724]" and IAT 0x558FC724 = EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF. The real code lives in EngineP.dpl, which is NOT present in this game directory (glob found no EngineP.dpl) and is NOT loaded in Ghidra. The symbols above come from the PE import table, which is ground truth. Do not try to decompile those addresses in Ghidra - read the thunk's imm32 and look up the IAT instead.

WHERE EACH SLOT IS INTRODUCED (vs merely overridden):
- +0x00..+0x48 (19 slots) are ALL introduced by Engine.TEObject; its VMT is 0x4C long. TEObject slot order, verified against direct descendants: ClassVersion, GetControlStyle, SetOwner, GetEngine, GetLastMsg, SetLastMsg, ReadWrite, MainReadWrite, Create, ClassID, AddRef, Release, Clear, Compare, Editor, Assign, TimerEvent, MsgProc, SetArrayOwner.
  Of these, 5 are overridden somewhere in TStrikeCA's chain: +0x18 ReadWrite (by TStrikeCA), +0x20 Create (by TCombatAction), +0x24 ClassID (by TStrikeCA), +0x28 AddRef and +0x2C Release (by TCombatAction). The other 14 still run TEObject's code.
  Note Engine.TEObject.Copy@23EDC2EF (IAT 0x558FC6F8) is imported but occupies no VMT slot - it is a non-virtual method.
- +0x4C..+0x60 (6 slots) are introduced by TCombatAction (its VMT grows from TEObject's 0x4C to 0x64): GetName, Execute, Play, ShowObject, ShowFieldObject, ShowFightingObjects.
- +0x64..+0x6C (3 slots) are introduced by TDamageCA (VMT gr
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x55766714` | `AoWE.TStrikeCA.ReadWrite@23EDC2EF` | TStrikeCA |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x557298B4` | `AoWE.TCombatAction.Create@23EDC2EF` | TCombatAction |
| `0x24` | `0x5576670C` | `AoWE.TStrikeCA.ClassID@23EDC2EF` | TStrikeCA |
| `0x28` | `0x557298EC` | `AoWE.TCombatAction.AddRef@23EDC2EF` | TCombatAction |
| `0x2C` | `0x557298F4` | `AoWE.TCombatAction.Release@23EDC2EF` | TCombatAction |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5572990C` | `AoWE.TCombatAction.GetName@23EDC2EF` | TCombatAction |
| `0x50` | `0x55766738` | `AoWE.TStrikeCA.Execute@23EDC2EF` | TStrikeCA |
| `0x54` | `0x55766860` | `AoWE.TStrikeCA.Play@23EDC2EF` | TStrikeCA |
| `0x58` | `0x55729E1C` | `AoWE.TDamageCA.ShowObject@23EDC2EF` | TDamageCA |
| `0x5C` | `0x55729A0C` | `AoWE.TSingleTargetCA.ShowFieldObject@23EDC2EF` | TSingleTargetCA |
| `0x60` | `0x55729B1C` | `AoWE.TSingleTargetCA.ShowFightingObjects@23EDC2EF` | TSingleTargetCA |
| `0x64` | `0x55729BE4` | `AoWE.TDamageCA.Setup@23EDC2EF` | TDamageCA |
| `0x68` | `0x557668B4` | `AoWE.TStrikeCA.Generate@23EDC2EF` | TStrikeCA |
| `0x6C` | `0x55729C98` | `AoWE.TDamageCA.GenerateEx@23EDC2EF` | TDamageCA |

### TStructure  —  VMT `0x55713C18`, instance `0x30`, 124 slots, ends `0x1F0`

<details><summary>derivation notes</summary>

```
UNIT/MODULE: AoWE unit, AoWEPACK.dpl (preferred base 0x55700000, which is also Ghidra's image base, so VAs below are directly usable in Ghidra). 124 slots (0x1F0/4), ALL resolved to real RTTI symbols — zero unknowns.

METHOD: symbols came from the DPL's own export table (10036 named exports) plus the import table, parsed from Modding Resources/AoWEPACK_original_backup.dpl (the same pristine bytes Ghidra holds). This is ground truth, not inference. Scripts left in the scratchpad: tstructure_vmt.py, exports.py, vmt_full.py, check.py, tstruct_chain.py.

*** THE INHERITED SLOTS ARE IMPORT THUNKS, NOT LOCAL FUNCTIONS ***
55 of the 124 slots point into 0x55701000-0x557035FF, the thunk block at the very start of CODE. Each is `FF 25 <abs32>` = `jmp dword ptr [IAT]` followed by `8B C0` padding (verified: 0x55703074 = ff2524c78f55 8bc0 -> IAT 0x558FC724). Ghidra returns "No function found" for these because it never made them functions — that is expected, not a gap. The IAT entry's import name IS the ancestor's full RTTI symbol, which is where every inherited symbol below comes from. Consequence for modding: to hook an inherited slot you are pointing at a 6-byte jump stub shared by every AoWEPACK class that inherits it — patching the stub hits ALL of them; patching the VMT slot hits only TStructure.

VMT HEADER (measured, all negative offsets read directly):
  -0x24  0x00000000   (empty table ptr)
  -0x20  0x55713E08   -> ShortString "TStructure" (len byte 0x0A)
  -0x1C  0x00000030   instance size = 48 bytes
  -0x18  0x558FCA08   vmtParent -> IAT slot, HSEPack.dpl ! ILTer..TFixedILTerrainMO@DE482B1C
  -0x14  0x557010C8   thunk -> VCL30.dpl ! System.TObject.SafeCallException
  -0x10  0x557010D0   thunk -> VCL30.dpl ! System.TObject.DefaultHandler
  -0x0C  0x55701098   thunk -> VCL30.dpl ! System.TObject.NewInstance
  -0x08  0x557010A0   thunk -> VCL30.dpl ! System.TObject.FreeInstance
  -0x04  0x5575E5C8   AoWE.TStructure.Destroy@23EDC2EF   <-- TStructure OVERRIDES Destroy; it is at -0x04, NOT in the positive slot range
No AfterConstruction/BeforeDestruction/Dispatch slots exist (Delphi 2-era layout), so do not assume the modern Delphi vmt* constants.

PROOF OF VMT END (0x1F0): [VMT-0x20] (the class-name pointer) equals VMT+0x1F0 exactly — the class-name ShortString is laid down immediately after the last slot. Bytes at VMT+0x1EC are `80 FB 75 55 | 0A 54 53 74 72 75 63 74 75 72 65` = last slot (CanRaze) then 0x0A "TStructure". So VMT+0x1F0 reads 0x7453540A, which is string data, not a code pointer. Last valid slot = +0x1EC.

ANCESTRY (derived by following vmtParent across packages, not guessed):
  System.TObject            vcl30.dpl      VMT 0x41301244  instsize 0x04
   -> Engine.TEObject       Enginep.dpl    VMT 0x5550C188  instsize 0x08
   -> HSEngine.THexagonSprite  HSEPack.dpl VMT 0x55603694  instsize 0x08   VMT ends +0x108
   -> HSEngine.TMapObject      HSEPack.dpl VMT 0x55604190  instsize 0x10   VMT ends +0x11C
   -> HSEngine.TMultiHexMO     HSEPack.dpl VMT 0x55604540  instsize 0x14   VMT ends +0x128
   -> ILTer.TILTerrainMO       HSEPack.dpl VMT 0x556181E8  instsize 0x1C   VMT ends +0x138
   -> ILTer.TFixedILTerrainMO  HSEPack.dpl VMT 0x55618484  instsize 0x1C   VMT ends +0x138  (adds no new virtuals, only overrides)
   -> AoWE.TStructure          AoWEPACK.dpl VMT 0x55713C18 instsize 0x30   VMT ends +0x1F0

*** KEY BOUNDARY: 0x138 ***
The direct parent TFixedILTerrainMO's VMT ends at +0x138. Therefore slots +0x000..+0x134 (78 slots) are the INHERITED slot range, and slots +0x138..+0x1EC (46 slots) are methods TStructure INTRODUCES. This is independently confirmed: every single slot from +0x138 upward carries an AoWE.TStructure symbol, and the last non-TStructure slot is exactly +0x134. Breakdown: 55 slots inherited-as-is + 23 TStructure overrides within +0x000..+0x134, + 46 new = 124. Owner histogram: TStructure 69, TMapObject 20, TEObject 15, TMultiHexMO 9, THexagonSprite 8, TILTerrainMO 2, TFixedILTerrainMO 1.

THE 23 OVERRIDDE
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x5575E658` | `AoWE.TStructure.ReadWrite@23EDC2EF` | TStructure |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x5575E590` | `AoWE.TStructure.Create@23EDC2EF` | TStructure |
| `0x024` | `0x5575E588` | `AoWE.TStructure.ClassID@23EDC2EF` | TStructure |
| `0x028` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x02C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x030` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x5575F898` | `AoWE.TStructure.MsgProc@23EDC2EF` | TStructure |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x5575EC04` | `AoWE.TStructure.GetTerrain@23EDC2EF` | TStructure |
| `0x050` | `0x557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x054` | `0x557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x058` | `0x5575EBF0` | `AoWE.TStructure.GetOverlay@23EDC2EF` | TStructure |
| `0x05C` | `0x557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x060` | `0x557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x064` | `0x5570213C` | `HSEngine.TMapObject.GetLevel@23EDC2EF` | TMapObject |
| `0x068` | `0x55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x06C` | `0x5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x070` | `0x557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x074` | `0x55702394` | `HSEngine.TMultiHexMO.GetXhx@23EDC2EF` | TMultiHexMO |
| `0x078` | `0x5570239C` | `HSEngine.TMultiHexMO.GetYhx@23EDC2EF` | TMultiHexMO |
| `0x07C` | `0x55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x080` | `0x557023A4` | `HSEngine.TMultiHexMO.GetXYL@23EDC2EF` | TMultiHexMO |
| `0x084` | `0x5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x088` | `0x55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x08C` | `0x557023AC` | `HSEngine.TMultiHexMO.GetShowPriority@23EDC2EF` | TMultiHexMO |
| `0x090` | `0x557023C4` | `HSEngine.TMultiHexMO.Connect@23EDC2EF` | TMultiHexMO |
| `0x094` | `0x557023CC` | `HSEngine.TMultiHexMO.Disconnect@23EDC2EF` | TMultiHexMO |
| `0x098` | `0x5575EC1C` | `AoWE.TStructure.CanChangeTerrain@23EDC2EF` | TStructure |
| `0x09C` | `0x557035AC` | `ILTer.TFixedILTerrainMO.ChangeTerrain@23EDC2EF` | TFixedILTerrainMO |
| `0x0A0` | `0x5575EC80` | `AoWE.TStructure.TerrainChanged@23EDC2EF` | TStructure |
| `0x0A4` | `0x55701E3C` | `HSEngine.THexagonSprite.NeighbourTerrainChanged@23EDC2EF` | THexagonSprite |
| `0x0A8` | `0x5575F958` | `AoWE.TStructure.Show@23EDC2EF` | TStructure |
| `0x0AC` | `0x5575E7C0` | `AoWE.TStructure.PlaceOnMap@23EDC2EF` | TStructure |
| `0x0B0` | `0x5575E7EC` | `AoWE.TStructure.RemoveFromMap@23EDC2EF` | TStructure |
| `0x0B4` | `0x5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0x0B8` | `0x55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0x0BC` | `0x55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0x0C0` | `0x557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0x0C4` | `0x5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0x0C8` | `0x55703574` | `ILTer.TILTerrainMO.Loaded@23EDC2EF` | TILTerrainMO |
| `0x0CC` | `0x5575F730` | `AoWE.TStructure.MapFieldMsgProc@23EDC2EF` | TStructure |
| `0x0D0` | `0x55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0x0D4` | `0x55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0x0D8` | `0x55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0x0DC` | `0x55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0x0E0` | `0x5575F6C0` | `AoWE.TStructure.Activate@23EDC2EF` | TStructure |
| `0x0E4` | `0x5575F710` | `AoWE.TStructure.Deactivate@23EDC2EF` | TStructure |
| `0x0E8` | `0x55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0x0EC` | `0x55760444` | `AoWE.TStructure.UpdateMapField@23EDC2EF` | TStructure |
| `0x0F0` | `0x5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0x0F4` | `0x55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0x0F8` | `0x5575E994` | `AoWE.TStructure.CanSelect@23EDC2EF` | TStructure |
| `0x0FC` | `0x5575EA40` | `AoWE.TStructure.Select@23EDC2EF` | TStructure |
| `0x100` | `0x5575EA64` | `AoWE.TStructure.Unselect@23EDC2EF` | TStructure |
| `0x104` | `0x55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x55702184` | `HSEngine.TMapObject.SetResource@23EDC2EF` | TMapObject |
| `0x114` | `0x5575ECC8` | `AoWE.TStructure.CanPlace@23EDC2EF` | TStructure |
| `0x118` | `0x5575ED10` | `AoWE.TStructure.PlaceHX@23EDC2EF` | TStructure |
| `0x11C` | `0x55702424` | `HSEngine.TMultiHexMO.SortMapFields@23EDC2EF` | TMultiHexMO |
| `0x120` | `0x557023F4` | `HSEngine.TMultiHexMO.CanPlaceOnHS@23EDC2EF` | TMultiHexMO |
| `0x124` | `0x55702414` | `HSEngine.TMultiHexMO.GetMostFrequentMapFieldTerrainType@23EDC2EF` | TMultiHexMO |
| `0x128` | `0x5575EC44` | `AoWE.TStructure.ValidTerrainType@23EDC2EF` | TStructure |
| `0x12C` | `0x5575E6A0` | `AoWE.TStructure.GetTerrainTypeImage@23EDC2EF` | TStructure |
| `0x130` | `0x5575E93C` | `AoWE.TStructure.ForceTerrainType@23EDC2EF` | TStructure |
| `0x134` | `0x55703534` | `ILTer.TILTerrainMO.GetValidTerrainType@23EDC2EF` | TILTerrainMO |
| `0x138` | `0x5575EB0C` | `AoWE.TStructure.GetTopBorderImage@23EDC2EF` | TStructure |
| `0x13C` | `0x5575EB58` | `AoWE.TStructure.GetMiddleBorderImage@23EDC2EF` | TStructure |
| `0x140` | `0x5575EBA4` | `AoWE.TStructure.GetBottomBorderImage@23EDC2EF` | TStructure |
| `0x144` | `0x5575E988` | `AoWE.TStructure.GetDescription@23EDC2EF` | TStructure |
| `0x148` | `0x5575E950` | `AoWE.TStructure.GetName@23EDC2EF` | TStructure |
| `0x14C` | `0x5575EDE8` | `AoWE.TStructure.SetRazed@23EDC2EF` | TStructure |
| `0x150` | `0x5575EDE4` | `AoWE.TStructure.GetRazed@23EDC2EF` | TStructure |
| `0x154` | `0x5575EDDC` | `AoWE.TStructure.GetRazeable@23EDC2EF` | TStructure |
| `0x158` | `0x5576023C` | `AoWE.TStructure.RazeEx@23EDC2EF` | TStructure |
| `0x15C` | `0x5575FE0C` | `AoWE.TStructure.SetupRazeDefenderAG@23EDC2EF` | TStructure |
| `0x160` | `0x5575E88C` | `AoWE.TStructure.CreateTE@23EDC2EF` | TStructure |
| `0x164` | `0x5575E89C` | `AoWE.TStructure.SetupTE@23EDC2EF` | TStructure |
| `0x168` | `0x5575E8CC` | `AoWE.TStructure.ExecuteTE@23EDC2EF` | TStructure |
| `0x16C` | `0x5575F378` | `AoWE.TStructure.GetDefenseRequirements@23EDC2EF` | TStructure |
| `0x170` | `0x5575F374` | `AoWE.TStructure.GetDefensePriority@23EDC2EF` | TStructure |
| `0x174` | `0x5575F338` | `AoWE.TStructure.NewDay@23EDC2EF` | TStructure |
| `0x178` | `0x5575F33C` | `AoWE.TStructure.NewTurn@23EDC2EF` | TStructure |
| `0x17C` | `0x5575F36C` | `AoWE.TStructure.SeatedPlayerChanged@23EDC2EF` | TStructure |
| `0x180` | `0x5575F360` | `AoWE.TStructure.ArmyPlaced@23EDC2EF` | TStructure |
| `0x184` | `0x5575F364` | `AoWE.TStructure.ArmyRemoved@23EDC2EF` | TStructure |
| `0x188` | `0x5575F368` | `AoWE.TStructure.ArmyChanged@23EDC2EF` | TStructure |
| `0x18C` | `0x5575EA18` | `AoWE.TStructure.PlaySelectSample@23EDC2EF` | TStructure |
| `0x190` | `0x5575E818` | `AoWE.TStructure.CreateShadow@23EDC2EF` | TStructure |
| `0x194` | `0x5575E850` | `AoWE.TStructure.DestroyShadow@23EDC2EF` | TStructure |
| `0x198` | `0x5575F908` | `AoWE.TStructure.ShowShadow@23EDC2EF` | TStructure |
| `0x19C` | `0x5575F010` | `AoWE.TStructure.BuildingDone@23EDC2EF` | TStructure |
| `0x1A0` | `0x5575EF08` | `AoWE.TStructure.ExecuteRebuild@23EDC2EF` | TStructure |
| `0x1A4` | `0x5575EFD8` | `AoWE.TStructure.ExecuteBuild@23EDC2EF` | TStructure |
| `0x1A8` | `0x5575FD1C` | `AoWE.TStructure.GenerateRazeDefenders@23EDC2EF` | TStructure |
| `0x1AC` | `0x5575FE84` | `AoWE.TStructure.PlaceRazeDefenders@23EDC2EF` | TStructure |
| `0x1B0` | `0x5575FFC8` | `AoWE.TStructure.ExecuteRaze@23EDC2EF` | TStructure |
| `0x1B4` | `0x5575E968` | `AoWE.TStructure.GetCurrentActivityText@23EDC2EF` | TStructure |
| `0x1B8` | `0x5575F4F4` | `AoWE.TStructure.ValidateMap@23EDC2EF` | TStructure |
| `0x1BC` | `0x5575F4F8` | `AoWE.TStructure.MainValidateMap@23EDC2EF` | TStructure |
| `0x1C0` | `0x5575E698` | `AoWE.TStructure.ExecuteAI@23EDC2EF` | TStructure |
| `0x1C4` | `0x5575E69C` | `AoWE.TStructure.UpdateAITarget@23EDC2EF` | TStructure |
| `0x1C8` | `0x5575E878` | `AoWE.TStructure.Update@23EDC2EF` | TStructure |
| `0x1CC` | `0x5575EDEC` | `AoWE.TStructure.VisibleForPlayer@23EDC2EF` | TStructure |
| `0x1D0` | `0x5575E990` | `AoWE.TStructure.CanDblClick@23EDC2EF` | TStructure |
| `0x1D4` | `0x5575F37C` | `AoWE.TStructure.ListUnits@23EDC2EF` | TStructure |
| `0x1D8` | `0x5575F434` | `AoWE.TStructure.ListArmies@23EDC2EF` | TStructure |
| `0x1DC` | `0x5575F18C` | `AoWE.TStructure.GetRebuildInfo@23EDC2EF` | TStructure |
| `0x1E0` | `0x5575F1A4` | `AoWE.TStructure.CanRebuild@23EDC2EF` | TStructure |
| `0x1E4` | `0x5575F26C` | `AoWE.TStructure.Rebuild@23EDC2EF` | TStructure |
| `0x1E8` | `0x557602F8` | `AoWE.TStructure.Raze@23EDC2EF` | TStructure |
| `0x1EC` | `0x5575FB80` | `AoWE.TStructure.CanRaze@23EDC2EF` | TStructure |

### TUnit  —  VMT `0x55710CAC`, instance `0x48`, 110 slots, ends `0x1B8`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
- Preferred image base 0x55700000; CODE = 0x55701000..0x558E7A00. All VAs below are at the preferred base (the DPL rebases at runtime).
- VMT located by the RTTI recipe on Modding Resources/AoWEPACK_original_backup.dpl: ShortString `05 "TUnit"` at 0x55710E64; the only dword pointing at it is at 0x55710C8C, so VMT = 0x55710C8C + 0x20 = 0x55710CAC. Unique — no other candidate.
- Ghidra's bytes at 0x55710C8C match the file byte-for-byte (read_memory cross-check), so the file-derived table is the same data Ghidra holds.

VMT END (hard stop)
- The VMT ends at +0x1B8. The dword at 0x55710E64 (= VMT+0x1B8) is 0x6E555405, which is not a code pointer — it is literally the class-name ShortString `05 'T' 'U' 'n'...` that [VMT-0x20] points at. Confirmed by read_memory at 0x55710E60: `1c097855 0554556e 6974 8bc0 700e7155`. So the name string immediately follows the last slot, exactly the TAoWHexagon pattern. 110 slots, 0x1B8 bytes, every one resolved to a real symbol — zero unnamed slots.

VMT HEADER (this is NOT the Delphi 4+ layout — 16 dwords, 0x40 total)
  VMT-0x40 = 0x55710CAC  SelfPtr (equals the VMT — this pins the header size)
  VMT-0x3C .. -0x24      all zero (IntfTable/AutoTable/InitTable/TypeInfo/FieldTable/MethodTable/DynamicTable)
  VMT-0x20 = 0x55710E64  class-name ShortString
  VMT-0x1C = 0x00000048  instance size (72 bytes)
  VMT-0x18 = 0x55710700  parent classref -> 0x55710740 = TAbstractUnit VMT
  VMT-0x14 = 0x557010C8 | VMT-0x10 = 0x557010D0 | VMT-0x0C = 0x55701098 | VMT-0x08 = 0x557010A0
  VMT-0x04 = 0x5577EB6C  AoWE.TAbstractUnit.Destroy@23EDC2EF   (destructor, inherited)
  Only FIVE TObject virtuals sit below +0 (-0x14..-0x04), not eight — there is no SafeCallException / AfterConstruction / BeforeDestruction. Anyone hand-porting a Delphi 7 VMT constant table here will be off by 0xC.

ANCESTRY (derived by walking [VMT-0x18] parent classrefs)
  TEObject (external) -> TCustomAbilityList -> TAbilityOwner -> TAbstractUnit -> TUnit
  TCustomAbilityList  VMT 0x5570F3DC  instsize 0x10  vmtlen 0x05C (23 slots)
  TAbilityOwner       VMT 0x5570F588  instsize 0x14  vmtlen 0x09C (39 slots)
  TAbstractUnit       VMT 0x55710740  instsize 0x3C  vmtlen 0x1B8 (110 slots)
  TUnit               VMT 0x55710CAC  instsize 0x48  vmtlen 0x1B8 (110 slots)
- IMPORTANT: TAbstractUnit's VMT is ALSO 0x1B8 long. TUnit introduces NO new virtual methods at all — it only overrides 40 of the 110 inherited slots. Any new virtual added to TUnit must be added to TAbstractUnit's VMT too (both grow together), or the slot index will not match across the hierarchy.
- The chain terminates inside this module at TCustomAbilityList: its [VMT-0x18] parent classref is 0x558FC92C, an .idata IAT slot, i.e. its parent TEObject lives in another package.

THE 11 "TEObject" SLOTS ARE IMPORT THUNKS — READ THIS BEFORE HOOKING THEM
- Slots +0x000, +0x004, +0x00C, +0x010, +0x014, +0x01C, +0x034, +0x038, +0x03C, +0x040, +0x048 point into 0x557030xx, which is NOT local code: each is a 6-byte `JMP dword ptr [0x558FC6xx]` import thunk into **EngineP.dpl** (unit `Engine`, class `TEObject`). Patching one of these thunks would change behaviour for every class in AoWEPACK that inherits the method, not just TUnit — override the VMT slot instead.
- Ghidra returns "No function found" for 6 of these thunk addresses (0x55703074, 0x557030AC, 0x557030B4, 0x557030BC, 0x557030C4, 0x557030D4, 0x55703104) because they are undefined there. Their names in the table come from the PE import table, not from Ghidra. Method validated: for the 3 thunks Ghidra *does* name (0x5570309C Editor, 0x557030DC GetControlStyle, 0x557030EC SetArrayOwner) the import-table walk produced exactly the same symbols, and get_xrefs_to 0x558FC724 confirms the 0x55703074 -> IAT indirection.

WHY THE EXPORT TABLE ALONE IS NOT ENOUGH (trap for future VMT dumps)
- AoWEPACK.dpl's export directory has 10036 names but its lowest function RVA is 0x374C — nothing below 0x5570374C is exported. A VMT dump th
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x5577F524` | `AoWE.TAbstractUnit.SetOwner@23EDC2EF` | TAbstractUnit |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x55782CEC` | `AoWE.TUnit.ReadWrite@23EDC2EF` | TUnit |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x5577EB28` | `AoWE.TAbstractUnit.Create@23EDC2EF` | TAbstractUnit |
| `0x024` | `0x557826AC` | `AoWE.TUnit.ClassID@23EDC2EF` | TUnit |
| `0x028` | `0x5577EBC4` | `AoWE.TAbstractUnit.AddRef@23EDC2EF` | TAbstractUnit |
| `0x02C` | `0x5577EBCC` | `AoWE.TAbstractUnit.Release@23EDC2EF` | TAbstractUnit |
| `0x030` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x55781238` | `AoWE.TAbstractUnit.MsgProc@23EDC2EF` | TAbstractUnit |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x5574E0E0` | `AoWE.TCustomAbilityList.GetAbSet@23EDC2EF` | TCustomAbilityList |
| `0x050` | `0x5574F308` | `AoWE.TAbilityOwner.SetAbSet@23EDC2EF` | TAbilityOwner |
| `0x054` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x058` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x05C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x060` | `0x5577F69C` | `AoWE.TAbstractUnit.GetOwnerName@23EDC2EF` | TAbstractUnit |
| `0x064` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x068` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x06C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x070` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x074` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x078` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x07C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x080` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x084` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x088` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x08C` | `0x5577ECC0` | `AoWE.TAbstractUnit.GetAbilitySelectionTypes@23EDC2EF` | TAbstractUnit |
| `0x090` | `0x55782B34` | `AoWE.TUnit.Changed@23EDC2EF` | TUnit |
| `0x094` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x098` | `0x5577F6EC` | `AoWE.TAbstractUnit.RemoveAbility@23EDC2EF` | TAbstractUnit |
| `0x09C` | `0x5577FC64` | `AoWE.TAbstractUnit.GetUpkeep@23EDC2EF` | TAbstractUnit |
| `0x0A0` | `0x55782B8C` | `AoWE.TUnit.GetUnitLevel@23EDC2EF` | TUnit |
| `0x0A4` | `0x55782C90` | `AoWE.TUnit.GetRace@23EDC2EF` | TUnit |
| `0x0A8` | `0x557829D0` | `AoWE.TUnit.GetInherentAttack@23EDC2EF` | TUnit |
| `0x0AC` | `0x55782A24` | `AoWE.TUnit.GetInherentDefense@23EDC2EF` | TUnit |
| `0x0B0` | `0x55782A8C` | `AoWE.TUnit.GetInherentDamage@23EDC2EF` | TUnit |
| `0x0B4` | `0x55782AE0` | `AoWE.TUnit.GetInherentResistance@23EDC2EF` | TUnit |
| `0x0B8` | `0x5577F570` | `AoWE.TAbstractUnit.GetInherentAbility@23EDC2EF` | TAbstractUnit |
| `0x0BC` | `0x5577F5A8` | `AoWE.TAbstractUnit.GetInherentAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x0C0` | `0x557829EC` | `AoWE.TUnit.GetAttack@23EDC2EF` | TUnit |
| `0x0C4` | `0x55782A40` | `AoWE.TUnit.GetDefense@23EDC2EF` | TUnit |
| `0x0C8` | `0x55782AA8` | `AoWE.TUnit.GetDamage@23EDC2EF` | TUnit |
| `0x0CC` | `0x55782AE8` | `AoWE.TUnit.GetResistance@23EDC2EF` | TUnit |
| `0x0D0` | `0x55782B68` | `AoWE.TUnit.GetHits@23EDC2EF` | TUnit |
| `0x0D4` | `0x55782B84` | `AoWE.TUnit.GetMoves@23EDC2EF` | TUnit |
| `0x0D8` | `0x5578276C` | `AoWE.TUnit.GetMovePoints@23EDC2EF` | TUnit |
| `0x0DC` | `0x55782794` | `AoWE.TUnit.SetMovePoints@23EDC2EF` | TUnit |
| `0x0E0` | `0x557827C0` | `AoWE.TUnit.GetHitPoints@23EDC2EF` | TUnit |
| `0x0E4` | `0x557827C4` | `AoWE.TUnit.SetHitPoints@23EDC2EF` | TUnit |
| `0x0E8` | `0x5577FFD0` | `AoWE.TAbstractUnit.GetMoveTypes@23EDC2EF` | TAbstractUnit |
| `0x0EC` | `0x5577FD54` | `AoWE.TAbstractUnit.GetImmunityTypes@23EDC2EF` | TAbstractUnit |
| `0x0F0` | `0x5577FD74` | `AoWE.TAbstractUnit.GetProtectionTypes@23EDC2EF` | TAbstractUnit |
| `0x0F4` | `0x5578283C` | `AoWE.TUnit.GetFace@23EDC2EF` | TUnit |
| `0x0F8` | `0x557826B4` | `AoWE.TUnit.GetName@23EDC2EF` | TUnit |
| `0x0FC` | `0x55782770` | `AoWE.TUnit.GetAlignment@23EDC2EF` | TUnit |
| `0x100` | `0x55782B94` | `AoWE.TUnit.GetPreviewImage@23EDC2EF` | TUnit |
| `0x104` | `0x55782BA0` | `AoWE.TUnit.GetTransportCapacity@23EDC2EF` | TUnit |
| `0x108` | `0x55782BD0` | `AoWE.TUnit.GetTransporter@23EDC2EF` | TUnit |
| `0x10C` | `0x55782810` | `AoWE.TUnit.GetGender@23EDC2EF` | TUnit |
| `0x110` | `0x55782800` | `AoWE.TUnit.GetBloodType@23EDC2EF` | TUnit |
| `0x114` | `0x55782808` | `AoWE.TUnit.GetUnitType@23EDC2EF` | TUnit |
| `0x118` | `0x55782C54` | `AoWE.TUnit.GetUnitGFXResourceIndex@23EDC2EF` | TUnit |
| `0x11C` | `0x55781208` | `AoWE.TAbstractUnit.CanAddToList@23EDC2EF` | TAbstractUnit |
| `0x120` | `0x5577ECCC` | `AoWE.TAbstractUnit.GetWallCombatFeatures@23EDC2EF` | TAbstractUnit |
| `0x124` | `0x5577EBB8` | `AoWE.TAbstractUnit.GetCampaignTransferPoints@23EDC2EF` | TAbstractUnit |
| `0x128` | `0x5577FDB8` | `AoWE.TAbstractUnit.GetCastingPointsMax@23EDC2EF` | TAbstractUnit |
| `0x12C` | `0x5577FDBC` | `AoWE.TAbstractUnit.GetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x130` | `0x5577FDC0` | `AoWE.TAbstractUnit.SetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x134` | `0x5577FDB4` | `AoWE.TAbstractUnit.GetPowerGeneration@23EDC2EF` | TAbstractUnit |
| `0x138` | `0x55782C98` | `AoWE.TUnit.NewDay@23EDC2EF` | TUnit |
| `0x13C` | `0x55780D4C` | `AoWE.TAbstractUnit.NewTurn@23EDC2EF` | TAbstractUnit |
| `0x140` | `0x55780E28` | `AoWE.TAbstractUnit.NewTurnDone@23EDC2EF` | TAbstractUnit |
| `0x144` | `0x5577F658` | `AoWE.TAbstractUnit.GetAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x148` | `0x5577F5E0` | `AoWE.TAbstractUnit.GetAbilityEnabled@23EDC2EF` | TAbstractUnit |
| `0x14C` | `0x5577F618` | `AoWE.TAbstractUnit.GetAbilitySet@23EDC2EF` | TAbstractUnit |
| `0x150` | `0x5577F630` | `AoWE.TAbstractUnit.GetAbilityName@23EDC2EF` | TAbstractUnit |
| `0x154` | `0x5577F67C` | `AoWE.TAbstractUnit.GetAbilityOwner@23EDC2EF` | TAbstractUnit |
| `0x158` | `0x5577F56C` | `AoWE.TAbstractUnit.GetAbilityCount@23EDC2EF` | TAbstractUnit |
| `0x15C` | `0x557828AC` | `AoWE.TUnit.GetExperience@23EDC2EF` | TUnit |
| `0x160` | `0x557828B4` | `AoWE.TUnit.SetExperience@23EDC2EF` | TUnit |
| `0x164` | `0x55782920` | `AoWE.TUnit.GetNextLevelExperience@23EDC2EF` | TUnit |
| `0x168` | `0x55782918` | `AoWE.TUnit.GetDescription@23EDC2EF` | TUnit |
| `0x16C` | `0x5577F4A8` | `AoWE.TAbstractUnit.SetPlayer@23EDC2EF` | TAbstractUnit |
| `0x170` | `0x5577F4F4` | `AoWE.TAbstractUnit.GetIndependentRelation@23EDC2EF` | TAbstractUnit |
| `0x174` | `0x55782764` | `AoWE.TUnit.GetObtainValue@23EDC2EF` | TUnit |
| `0x178` | `0x557827F8` | `AoWE.TUnit.GetUnitSize@23EDC2EF` | TUnit |
| `0x17C` | `0x5577EED8` | `AoWE.TAbstractUnit.GetUnitMoraleValue@23EDC2EF` | TAbstractUnit |
| `0x180` | `0x5577FB9C` | `AoWE.TAbstractUnit.CanActivate@23EDC2EF` | TAbstractUnit |
| `0x184` | `0x55782C5C` | `AoWE.TUnit.Activate@23EDC2EF` | TUnit |
| `0x188` | `0x5577FC20` | `AoWE.TAbstractUnit.Deactivate@23EDC2EF` | TAbstractUnit |
| `0x18C` | `0x55780328` | `AoWE.TAbstractUnit.MovedTo@23EDC2EF` | TAbstractUnit |
| `0x190` | `0x557825B0` | `AoWE.TAbstractUnit.CanDisband@23EDC2EF` | TAbstractUnit |
| `0x194` | `0x557821AC` | `AoWE.TAbstractUnit.CanJoin@23EDC2EF` | TAbstractUnit |
| `0x198` | `0x55782324` | `AoWE.TAbstractUnit.JoinAmount@23EDC2EF` | TAbstractUnit |
| `0x19C` | `0x55782364` | `AoWE.TAbstractUnit.OfferToJoin@23EDC2EF` | TAbstractUnit |
| `0x1A0` | `0x55782440` | `AoWE.TAbstractUnit.GetJoinMessage@23EDC2EF` | TAbstractUnit |
| `0x1A4` | `0x557826C8` | `AoWE.TUnit.ShowEx@23EDC2EF` | TUnit |
| `0x1A8` | `0x55782838` | `AoWE.TUnit.UnitKilled@23EDC2EF` | TUnit |
| `0x1AC` | `0x55782818` | `AoWE.TUnit.Killed@23EDC2EF` | TUnit |
| `0x1B0` | `0x557808DC` | `AoWE.TAbstractUnit.Resurrect@23EDC2EF` | TAbstractUnit |
| `0x1B4` | `0x5578091C` | `AoWE.TAbstractUnit.Animate@23EDC2EF` | TAbstractUnit |

### TUnitResource  —  VMT `0x55710A64`, instance `0x54`, 29 slots, ends `0x74`

<details><summary>derivation notes</summary>

```
ALL 29 slots resolved, zero unknowns. Every VA is at the DPL's preferred base 0x55700000 (the .dpl rebases at runtime).

== HOW THIS WAS DERIVED ==
VMT located by the RTTI recipe against Modding Resources/AoWEPACK_original_backup.dpl (the pristine vanilla bytes Ghidra holds). Exactly ONE candidate matched "TUnitResource"; self-check passed: [VMT-0x40] (SelfPtr) = 0x55710A64 = the VMT itself.

*** IMPORTANT METHOD NOTE — Ghidra ALONE CANNOT DO THIS. *** 12 of the 29 slots point at 6-byte import thunks (FF 25 <IAT>) into EngineP.dpl, and Ghidra has NO function defined at several of them (get_function_by_address on 0x55703074, 0x55703384, 0x557030AC, 0x557030B4 all return "No function found"). Their true symbols come from the PE IMPORT table, not from Ghidra and not from the DPL export table. Resolution used here: local slots -> AoWEPACK.dpl export table (10036 named exports); thunk slots -> read the IAT VA out of the FF 25 operand, look it up in the import descriptors. Spot-checked 6 local symbols against Ghidra get_function_by_address; all matched exactly.

== END OF VMT ==
[VMT+0x74] = 0x0000000E, not a CODE pointer -> VMT body is 0x00..0x70 inclusive, 29 slots, ends at +0x74. Corroborated three ways: (a) [VMT-0x34] InitTable = 0x55710AD8 = exactly VMT+0x74, i.e. the next structure begins there; (b) the sibling TAbstractUnitResource VMT also ends at +0x74, where its bytes read 0x62415415 = 0x15 'TAb...' — the length byte of its own 21-char class-name ShortString; (c) TUnitResource introduces no new virtuals over its parent (see below), so 29 is the inherited count.

== ANCESTRY (fully derived, not assumed) ==
System.TObject (VCL30.dpl)
  -> Engine.TEObject      (EngineP.dpl, VMT 0x5550C188, instsize 0x08, 19 slots, ends +0x4C)
    -> Engine.TEResource  (EngineP.dpl, VMT 0x5550D6C0, instsize 0x18, 25 slots, ends +0x64)
      -> AoWE.TAbstractUnitResource (AoWEPACK.dpl, VMT 0x5571096C, instsize 0x1C, 29 slots, ends +0x74)
        -> AoWE.TUnitResource       (AoWEPACK.dpl, VMT 0x55710A64, instsize 0x54, 29 slots, ends +0x74)
TAbstractUnitResource's [VMT-0x18] parent ref is an IAT entry (0x558FC8EC -> EngineP.dpl!"Engine..TEResource@9052749E"), i.e. the parent class lives in another package. The two EngineP VMTs were dumped from <game dir>\Enginep.dpl by the same method to confirm the chain and the slot boundaries.

== WHICH CLASS INTRODUCES WHICH SLOT (from the ancestors' own VMT lengths) ==
  0x00..0x48 (19 slots) declared by Engine.TEObject
  0x4C..0x60 (6 slots)  declared by Engine.TEResource
  0x64..0x70 (4 slots)  declared by AoWE.TAbstractUnitResource
  TUnitResource declares NO new virtual methods — it only overrides.
Note slot 0x48 SetArrayOwner and slot 0x08 SetOwner are TEObject-declared slots that TEResource overrides; slot 0x4C GetCellImage / 0x54 ResourceEditName / 0x58 ResourceUserClassID / 0x5C CreateResourceUser are TEResource-declared slots that TAbstractUnitResource or TUnitResource override.

== THE 7 SLOTS TUnitResource OVERRIDES vs TAbstractUnitResource (these are the interesting hook points) ==
  +0x18 ReadWrite            0x55784DE4  (was 0x55784A48 TAbstractUnitResource.ReadWrite)
  +0x20 Create               0x55784C44  (was 0x55703064 thunk -> Engine.TEObject.Create)
  +0x24 ClassID              0x55784DA0  (was 0x55703374 thunk -> Engine.TEResource.ClassID)
  +0x58 ResourceUserClassID  0x55784D68  (was 0x557033AC thunk -> Engine.TEResource.ResourceUserClassID)
  +0x5C CreateResourceUser   0x55784D70  (was 0x557033B4 thunk -> Engine.TEResource.CreateResourceUser)
  +0x64 DropUnit             0x55784F70  (was 0x55784A6C TAbstractUnitResource.DropUnit)
  +0x70 GetObtainValue       0x55784D58  (was 0x557849F8 TAbstractUnitResource.GetObtainValue)

== NEGATIVE (TObject) VMT SLOTS — part of virtual dispatch, NOT in the 0x00.. body ==
This build uses the Delphi 3 header layout (SafeCallException/DefaultHandler/NewInstance/FreeInstance/Destroy only; the Delphi-4 AfterConstruction/BeforeDestruction/Dispatch entr
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x55703384` | `Engine.TEResource.SetOwner@23EDC2EF` | TEResource |
| `0x0C` | `0x557849F0` | `AoWE.TAbstractUnitResource.GetEngine@23EDC2EF` | TAbstractUnitResource |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x55784DE4` | `AoWE.TUnitResource.ReadWrite@23EDC2EF` | TUnitResource |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55784C44` | `AoWE.TUnitResource.Create@23EDC2EF` | TUnitResource |
| `0x24` | `0x55784DA0` | `AoWE.TUnitResource.ClassID@23EDC2EF` | TUnitResource |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x55784B0C` | `AoWE.TAbstractUnitResource.MsgProc@23EDC2EF` | TAbstractUnitResource |
| `0x48` | `0x5570338C` | `Engine.TEResource.SetArrayOwner@23EDC2EF` | TEResource |
| `0x4C` | `0x55784A3C` | `AoWE.TAbstractUnitResource.GetCellImage@23EDC2EF` | TAbstractUnitResource |
| `0x50` | `0x5570339C` | `Engine.TEResource.SetCellImage@23EDC2EF` | TEResource |
| `0x54` | `0x55784AE8` | `AoWE.TAbstractUnitResource.ResourceEditName@23EDC2EF` | TAbstractUnitResource |
| `0x58` | `0x55784D68` | `AoWE.TUnitResource.ResourceUserClassID@23EDC2EF` | TUnitResource |
| `0x5C` | `0x55784D70` | `AoWE.TUnitResource.CreateResourceUser@23EDC2EF` | TUnitResource |
| `0x60` | `0x55703394` | `Engine.TEResource.Draw@23EDC2EF` | TEResource |
| `0x64` | `0x55784F70` | `AoWE.TUnitResource.DropUnit@23EDC2EF` | TUnitResource |
| `0x68` | `0x55784A1C` | `AoWE.TAbstractUnitResource.GetPreviewImage@23EDC2EF` | TAbstractUnitResource |
| `0x6C` | `0x557849FC` | `AoWE.TAbstractUnitResource.GetFace@23EDC2EF` | TAbstractUnitResource |
| `0x70` | `0x55784D58` | `AoWE.TUnitResource.GetObtainValue@23EDC2EF` | TUnitResource |

## 9. The full instance-field catalogue

**Generated from `re_tools/ghidra_fields.py --md`; do not hand-edit — edit the script and re-run.**
As currently derived: **18 classes, 269 instance fields**, each tagged with its evidence: **M**
measured by decompile (158 fields), **D** doc-stated (106), **S** speculative (5). VMT slots are
deliberately absent from this catalogue — they are fully covered in §8. The catalogue is **keyed by
class first, never by a bare offset** — §3's aliasing warning is not decoration; five separate
aliasing traps were found in one session by exactly the mistake a flat offset-sorted table invites.

### 9.1 The bounds check makes the catalogue self-policing

Field *meanings* cannot be derived from the binary, but **instance sizes can** (RTTI at
`[VMT-0x1C]`), and a field claimed at or past its class's instance size is provably wrong, or
actually belongs to a subclass. Every entry is checked on every regeneration. Three claims outside
the catalogue were condemned by this check and correctly excluded, since a measured instance size
beats any doc:

| claim | instance size | verdict |
|---|---|---|
| `TAbility+0x24` cosmetic category byte | `TAbility` = **0x24** | past the end — belongs to a subclass |
| `TCombatPredictor+0x34` loop object | `TCombatPredictor` = **0x34** | past the end (was already flagged speculative) |
| `TAbility+0x28` max level / `+0x2C` cost list | `TAbility` = **0x24** | these are `TMultiLevelAbility` (instance size 0x30) fields, not `TAbility`'s |

Three fields **inside** the catalogue are legitimately past their class's *vanilla* instance size,
because this project's own mods grew the class — the bounds check flags these too, and the flag is
correct in a different sense: it records the vanilla/installed distinction rather than an error.
`TUnit+0x7C` (the unit-spellcasting casting cluster, past vanilla's `0x48`) and `TArena+0x30`/`+0x34`
(mod flags + roster seed, past vanilla's `0x30`) are both marked `⚠ INSTALLED ONLY` in the table
below for exactly this reason.

### 9.2 Method — same as §3: the DLL names its own methods and fields' owning class

1. Find the class VMT from the class-name ShortString — `[VMT-0x20]` points at it, so the dword that
   points to the string is `VMT-0x20`. `[VMT-0x1C]` (instance size) cross-checks the hit.
2. Read a slot, decompile the target; Ghidra prints the real symbol, e.g.
   `AoWE.TUnit.GetDefense@23EDC2EF`.
3. Field offsets inside the instance are then read off the decompiled accessor bodies themselves
   (`param_1->field_0x45`-style expressions once the struct is typed), cross-checked against the
   instance size from step 1.

No inference, no voting — which matters, because a sweep of ~400 offset facts recorded across this
project's docs turned up **16 direct conflicts** (same class, same offset claimed to mean two
different things). All 16 were resolved **by measurement, not by majority vote**: a vote is exactly
how a wrong claim becomes permanent, which is how the road-build-cost error and the `+0x4C` alias
each ended up duplicated across multiple docs in the first place. Final tally: **14 resolved by
direct measurement**, 1 reconciled by inference and labelled as such, 1 left unmeasurable with this
toolchain. Of the 14 measured: **8 were plain documentation errors**, and **4 were latent
class-aliasing traps** where both sides of the "conflict" were actually right, about two different
classes. **No shipped cave was ever found to be wrong in this pass** — every defect found was in a
doc describing the code, never in the code itself. The traps worth carrying forward, beyond the
quick-reference table in §3:

**`TUnit` and `THero` read their stats from DIFFERENT resource layouts, 5 bytes apart.** Both classes
hold a resource pointer at `+0x40`, but the stat blocks that pointer leads to are not aligned:

| stat | via `TUnit.Get*` | via `THero.Get*` |
|---|---|---|
| Attack | `[[unit+0x40]+0x29]` | — |
| Defense | `[[unit+0x40]+0x2A]` | `[[hero+0x40]+0x25]` |
| Resistance | `[[unit+0x40]+0x2E]` | — |

So `re_tools/pfs.py`'s stat map (`+0x29` ATK, `+0x2A` DEF, `+0x2B` DMG, `+0x2C` HP, `+0x2D` Move,
`+0x2E` RES) is the **`TUnit`** layout; a `+0x24`/`+0x25`… map seen elsewhere is the **`THero`**
layout. Both are correct, for different classes, and a source that doesn't say which one it means is
incomplete. **A cave written against one and run on the other reads the wrong byte** — the same
family of bug as `+0x4C`.

**`+0x30` is past the end of `TStructure` — every subclass means something different by it.**
`TStructure`'s instance size is exactly `0x30`, so its own fields stop at `+0x2F`; `+0x30` is one
past the end. Measured per concrete class:

| class | instance size | what sits at `+0x30` |
|---|---|---|
| `TStructure` | **0x30** | nothing — past the end |
| `TArena` | **0x30** vanilla, **grown to 0x38** by this project | nothing in vanilla; the mod claims `+0x30` (mod flags) / `+0x34` (roster seed) |
| `TExplorationSite` | 0x38 | defender-strength byte (`+0x34` = the hidden defenders army pointer) |
| `TDungeon` | 0x40 | inherits the site layout, adds prisoners at `+0x38`/`+0x3C` |
| `TReflectingPool`, `TTower` | 0x40 | their own, unrelated fields |

Three sibling classes independently own that byte — a cave reading `structure[+0x30]` behaves
completely differently depending on which concrete subclass it's handed. Any use of `+0x30` must name
the concrete subclass; treat it exactly like the `+0x4C` family.

**The hexagon `+0x10` alias, and the `+0x14`/`+0x15` polarity it took two passes to get right.**
`TAoWHexagon` (instance size `0x14`) has three transition-image bytes at `+0x10..+0x12` and flags at
`+0x13`; its sibling `TAoWWaterHexagon` (instance size `0x20`, a *different* parent classref, not a
child of `TAoWHexagon`) uses `+0x10` as a lazily-created dynamic-companion **pointer** instead. Full
verified `TAoWWaterHexagon` layout (totals `0x20`, matching its instance size): `+0x10` dynamic
companion pointer, `+0x14` land-neighbour mask, `+0x15` differing-terrain mask (low 6 bits; `&0xC0`
preserves the top two as the tile phase), `+0x18` signed frame counter, `+0x19` rolled animation id,
`+0x1A..0x1F` per-direction shore-tint bytes (`0x28` for a Snow neighbour, `0x50` for Wasteland, else
0).

⚠ **`+0x14`'s polarity was itself got wrong once and corrected** — worth recording as the general
lesson, not just the fact. `UpdateTransitions` sets bit *d* only when the neighbour owns no
`TLowerIsometricHexagon` and no `TBorderHexagon`. The first pass concluded this meant "open-water
mask", reasoning that `TLowerIsometricHexagon` sounded like the *land* family — it is in fact the
**water** family (`TAoWWaterHexagon`'s own parent classref is the exact classref value being tested
against). So the correct read is **`+0x14` bit d = "the neighbour in direction d+1 IS land"** — the
opposite of the first conclusion. The refuting evidence (`TAoWWaterHexagon parentref=558FCD70`) was
sitting in the same session's own probe output at the moment the wrong call was made: a decompile was
read correctly, and the *class identity* of a constant inside it was assumed rather than checked.
**When a `FindOwnedHS`/class-compare decides a polarity, resolve the classref before trusting the
sense of the test** — caught only because an independent agent re-derived the same field later and
the two disagreed.

**`map+0x174` is the day counter, confirmed by one decompile that also settled nine other map
fields.** `AoWE.TPlayerControl.NewDay` contains the increment directly, and the value is formatted
into the "Day %d" event-log line and compared against the turn limit — "init state" was a
mis-generalisation from an earlier test that only checked "is it nonzero". The same decompile
independently confirmed: `+0x140` `TPlayerList`, `+0x144` `TRaceList` (previously recorded only as
"second list"), `+0x158` turn limit, `+0x16C` turn-order mode (`==2` ⇒ regenerate turn order),
`+0x19C` notify event list, `+0x22C`/`+0x230` seed constant / seed state (the SYNCED RNG's replicated
state — §4), `+0x13A` session mode (gates the day-1 `Randomize`, not a generic "scenario flag"), and
`+0xA5` seated player. Message `0x20020001` is confirmed as NewDay.

**Transport capacity: vanilla and the installed layout are BOTH right, for different eras of the same
field.** `AoWE.TUnit.GetTransportCapacity` takes the max of the item-aware ability level for
Transport (ability id `0x32`) and `TUnitResource.GetTransportCapacity`. Vanilla reads the latter from
`+0x44` (confirmed 1-byte field, padded to a dword — which is exactly what made the byte reusable);
the copper-medal mod relocated it to `+0x32`, and `+0x44` now holds the gold-rank ability-owner
pointer instead. Not a contradiction — a **vanilla vs. installed** distinction the catalogue records
per-class rather than resolving to one answer.

---
### TAbility (AoWE unit, AoWEPACK.dpl; VMT @ 0x5570F254, class name ptr [VMT-0x20]=0x5570F372 "TAbility", instance size [VMT-0x1C] = 0x24, parent cell [VMT-0x18]=0x558FC92C -> imported Engine.TEObject)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `unknown_this_offset_is_not_introdu` | S | UNKNOWN. This offset is NOT introduced by TAbility and is never read or written by any TAbility method (all 54 TAbility.* functions were checked; ever |
| `+0x08` | - | `fname_the_ability_s_display_name_a` | M | FName - the ability's display name, as a reference-counted Delphi AnsiString. Returned verbatim by GetName and ExpandName; set in each concrete abilit |
| `+0x0C` | - | `fabilityid_the_ability_s_global_ab` | M | FAbilityID - the ability's global ability id (0..N). It is the index under which the singleton is stored in TAbilityControl's TList, the key every TAb |
| `+0x10` | - | `fdescription_a_tstringlist_holding` | M | FDescription - a TStringList holding the ability's description text lines. Created empty in the constructor, freed in the destructor, filled from the  |
| `+0x14` | - | `fexpandcost_the_point_cost_of_acqu` | M | FExpandCost - the point cost of acquiring this ability, returned unchanged by ExpandCost, and also returned by GetSkillPoints as the ability's skill-p |
| `+0x18` | - | `fsfx_the_ability_s_sound_effect_li` | M | FSFX - the ability's sound-effect library: the set of sounds played when the ability fires. Constructed empty, freed in the destructor, populated from |
| `+0x1C` | - | `fanimation_the_ability_s_image_seq` | M | FAnimation - the ability's image-sequence list (its on-screen effect animation, and the frames the ability draws over its target). Created against the |
| `+0x20` | - | `fselectiontypes_the_set_of_owner_c` | M | FSelectionTypes - the set of owner categories this ability may legitimately belong to / be selected for. Members (from the enum's own RTTI, ordinal =  |

### TAbstractUnit  (instance size `0x3C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `owner_pointer_to_the_engine_contai` | M | [introduced by Engine.TEObject(imported)] Owner - pointer to the Engine container/list object that currently holds this unit (a TUnitList / TArmy while on the map, nil when unowned). Set only  |
| `+0x08` | 4 | `pointer_to_a_heap_allocated_bit_ar` | M | [introduced by TCustomAbilityList] Pointer to a heap-allocated bit array holding the unit's ability set - one bit per ability id, bit i at byte i>>3, mask 1<<(i&7). Its companion length |
| `+0x0C` | 4 | `ability_bitset_width_bits` | M | DWORD, not a byte: the ability count in BITS. GetAbilitySet: `if id < unit+0xC` |
| `+0x10` | 4 | `ability_data_head` | D | linked list; next at data+0x08 (TAbilityOwner) |
| `+0x14` | 4 | `reference_count_initialised_to_1_i` | M | Reference count. Initialised to 1 in the constructor; AddRef increments, Release decrements and calls the destructor (VMT-0x04) when it reaches zero.  |
| `+0x18` | 4 | `unit_id` | D | network / FindUnit key; Create inits to -1 |
| `+0x1C` | 4 | `id_of_the_ai_group_taigroup_this_u` | M | ID of the AI group (TAIGroup) this unit belongs to; 0 = not in a group. This is the *persistent* handle - the live TAIGroup pointer is the separate fi |
| `+0x20` | 4 | `ai_group_link` | D |  |
| `+0x24` | 1 | `owner_player_index` | D |  |
| `+0x25` | 1 | `flags` | D | bit1 gates the morale/notify block in Changed() |
| `+0x26` | 1 | `morale_cache` | M | cached morale VALUE, SIGNED byte clamped to [-25, +125]. loyal >= 41 |
| `+0x38` | 1 | `legacy_ai_group_behaviour_code_the` | M | Legacy AI-group *behaviour* code (the small enum returned by TGroupControl.Behavior: 0 = none/base, 2 = Guard, 0x0A = Suicidal, 0x0B = Passive, 0x0D = |

### TAoWHSMap  (instance size `0x41C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0xA4` | 1 | `current_turn_player` | D |  |
| `+0xA5` | 1 | `seated_local_player` | M | passed to GameOver in TPlayerControl.NewDay |
| `+0xE4` | 4 | `ansistring_the_map_s_game_s_name_n` | M | AnsiString: the map's/game's NAME (not its filename). Initialised to 'noname' in the constructor, streamed under property id 0x19, and used as the bas |
| `+0xF4` | 4 | `owned_aowe_titemcontrol_instance_t` | M | Owned AoWE.TItemControl instance - the map-wide registry of all TItem objects (RegisterItem/UnRegisterItem, FindItem, GenerateItem(s), CreateUniqueID, |
| `+0xF8` | 4 | `owned_aowe_therocontrol_instance_t` | M | Owned AoWE.THeroControl instance - the map-wide hero registry (RegisterHero/UnRegisterHero, GetHero, FindID, ListDeadHeroes, ValidateLibraryHeroes, Ge |
| `+0xFC` | 4 | `owned_aowe_tunitcontrol_instance_t` | M | Owned AoWE.TUnitControl instance - the map-wide unit registry and units-changed notification hub. Streamed under property id 0x26. |
| `+0x100` | 4 | `owned_aowe_tstructurecontrol_insta` | M | Owned AoWE.TStructureControl instance - the map-wide structure registry (Register/Unregister, GetStructure, FindID, IndexOfID, CreateUniqueID). Stream |
| `+0x124` | 4 | `owned_aowe_ttutorialcontrol_instan` | M | Owned AoWE.TTutorialControl instance - shows tutorial hint messages and remembers which have already been shown. Streamed under property id 0x38, so t |
| `+0x128` | 4 | `owned_aowe_taiexecuter_instance_th` | M | Owned AoWE.TAIExecuter instance - the per-frame driver that runs AI players' turns. Runtime only, not streamed. |
| `+0x12C` | 4 | `owned_aowe_taiplayeractionmanager_` | M | Owned AoWE.TAIPlayerActionManager instance - the registry of AI player-action (AIPA) CLASSES, not of instances. The constructor registers 12: TEndTurn |
| `+0x130` | 4 | `owned_aowe_taigroupmanager_instanc` | M | Owned AoWE.TAIGroupManager instance - creates and owns the AI's army groups (CreateGroup, CreateUniqueID) and holds the registry of AI-group classes ( |
| `+0x134` | 4 | `owned_aowe_taowhsmapkeyboard_insta` | M | Owned AoWE.TAoWHSMapKeyboard instance - the strategic-map keyboard-input handler. Not streamed. Caveat: the class identity is certain (taken from the  |
| `+0x13A` | 1 | `session_mode` | M | connection/session enum: 0 = local (single/hotseat), 1 = network MP. Gates the day-1 Randomize -- 'scenario flag' was the wrong label |
| `+0x140` | 4 | `player_list` | M | TPlayerList |
| `+0x144` | 4 | `race_list` | M | TRaceList -- was recorded only as '(second list)' |
| `+0x158` | 4 | `turn_limit` | M | compared to the day counter; triggers GameOver |
| `+0x16C` | 1 | `turn_order_mode` | M | == 2 -> GenerateNewTurnOrder |
| `+0x170` | 4 | `owned_engine_tbytelist_holding_the` | M | Owned Engine.TByteList holding the TURN ORDER - the sequence of player indices for the current day. Element 0 is always player 0 (the independents); t |
| `+0x174` | 4 | `day_counter` | M | incremented by TPlayerControl.NewDay. NOT 'init state' |
| `+0x188` | 4 | `global_magic_control` | D |  |
| `+0x18C` | 4 | `owned_aowe_taowmapcampaignsettings` | M | Owned AoWE.TAoWMapCampaignSettings instance - the per-scenario campaign carry-over limits. A pure data record (only Create + ReadWrite exist): +0x08 b |
| `+0x19C` | 4 | `notify_event_list` | M |  |
| `+0x1AC` | 4 | `owned_engine_teventlist_the_seated` | M | Owned Engine.TEventList - the 'seated player changed' notify-event list. Registered handlers are fired (with the global AoWHSMap as argument) whenever |
| `+0x1CC` | 4 | `owned_eventlog_teventloglist_used_` | M | Owned EventLog.TEventLogList used as a DEFERRAL BUFFER for per-player event-log entries. While the lock counter at +0x1C8 is non-zero each copy of an  |
| `+0x1D4` | 4 | `owned_eventlog_texecuteeventlogcal` | M | Owned EventLog.TExecuteEventLogCallBackList - the FIFO queue of pending event-log PLAYBACK requests (each entry a 16-byte record: log object + callbac |
| `+0x22C` | 4 | `per_game_seed_constant` | M | **The standard P4 salt (§4.10).** Two writers, both vanilla-unpatched: `SetupMap+0x476 @0x557E0FDA` (from the replicated setup settings, `settings[+0x2C]`) and `NewDay+0x1AD @0x55754F51` (from `Randomize`, day 1 only, **skipped when `map[+0x13A]==1`, i.e. network MP**). Serialised by `ReadWrite+0x2CC @0x5577702C` (`lea edx,[ebx+0x22C]; mov ecx,0x24`). Read at `0x55754F5C`, `0x5575FD36` (`GenerateRazeDefenders`), `0x557ABCD5` (`GenerateRebelUnits`). Set once before day 2, never written again, identical on every peer. ⚠ 0 or stale until `NewDay` runs on day 1 |
| `+0x230` | 4 | `seed_state` | M | MP-lockstep RNG state — the SYNCED stream (§4.1). Anchored from `+0x22C` on day 1 at `NewDay+0x1C4 @0x55754F68`; advanced and written back by `TAoWHSMap.Random @0x557782B4` on **every** synced draw; reported to the desync comparator by `GetSyncValue @0x55754CE8`; serialised in the same `ReadWrite` block as `+0x22C`. ⚠ Never a P4 salt — it is a different value at every evaluation |
| `+0x239` | 1 | `the_turn_mode_player_control_style` | M | The TURN MODE (player-control style) of this game: 1 = sequential/turn-based (TTurnPlayerControl, or TPBEMPlayerControl when the session is play-by-em |
| `+0x23C` | 4 | `token_manager` | D |  |
| `+0x240` | 4 | `owned_networke_tplayercommunicator` | M | Owned NetworkE.TPlayerCommunicator instance - the network/session transport for player messages. Its +0x1C is the TPlayerCommunicationControl (nil in  |
| `+0x244` | 4 | `owned_aowe_tplayercontrol_instance` | M | Owned AoWE.TPlayerControl instance - the polymorphic turn-flow controller. Its concrete class is chosen from the turn mode at +0x239: TTurnPlayerContr |

### TAoWHexagon  (instance size `0x14`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `map_field` | D |  |
| `+0x08` | 4 | `resource` | D |  |
| `+0x0C` | - | `fstatus_tmapobjectstatus_a_1_byte_` | M | FStatus : TMapObjectStatus - a 1-byte Delphi SET of runtime state flags (RTTI-confirmed type name and member names). Bits: 0x01 moVisible; 0x02 moReso |
| `+0x10` | 3 | `transition_image_per_edge` | M | ⚠ 3 BYTES here. On TAoWWaterHexagon (a SIBLING class) +0x10 is a pointer |
| `+0x13` | 1 | `transition_flags` | D | bits 0-2 = edge n has an image |

### TAoWWaterHexagon  (instance size `0x20`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `pointer_to_the_tmapfield_this_hexa` | M | [introduced by Engine.TEObject(imported)] Pointer to the TMapField this hexagon sprite occupies (the owning map field). That record carries: +0x04 = TMapLevel*, +0x10 = X (byte), +0x11 = Y (by |
| `+0x08` | 4 | `pointer_to_the_hexagon_s_resource_` | M | Pointer to the hexagon's resource / art-definition object (the TAoWWaterHexagonResource, of the TIsometricHexagonResource / TMapObjectResource family) |
| `+0x10` | 4 | `dynamic_companion` | M | lazily created in UpdateTransitions |
| `+0x14` | 1 | `land_neighbour_mask` | M | bit d set when the neighbour in dir d+1 IS land -- UpdateTransitions sets it when the neighbour owns no TLowerIsometricHexagon (the WATER family: it is TAoWWaterHexagon's own parent classref 0x558FCD70) and no TBorderHexagon |
| `+0x15` | 1 | `differing_terrain_mask` | M | low 6 bits; top 2 preserved (&0xC0) = tile phase |
| `+0x18` | 1 | `frame_counter` | M | signed; negative = idle delay |
| `+0x19` | 1 | `animation_id` | M | rolled 20-39 / 50-58 |
| `+0x1A` | 6 | `shore_tint_per_dir` | M | 0x28 Snow neighbour, 0x50 Wasteland, else 0 |

### TArena  (instance size `0x30`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `pointer_to_the_taowmapfield_this_s` | M | [introduced by Engine.TEObject(imported)] Pointer to the TAoWMapField this structure occupies - the map-object's back-link to its own tile on the strategic map. Not a TArena concept at all: it |
| `+0x30` | 1 | `mod_flags` | D | ⚠ INSTALLED ONLY -- bit0 EMPTY, bit1 SEEDED. Legal only because build_arena.py grows instsize 0x30 -> 0x38 |
| `+0x34` | 4 | `mod_roster_seed` | D | ⚠ INSTALLED ONLY |

### TCombatObject  (instance size `0x4C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `combat` | D | owning TCombat |
| `+0x0C` | 4 | `find_id` | D |  |
| `+0x10` | 4 | `engine_tquaditemlist_the_outgoing_` | M | Engine.TQuadItemList* - the OUTGOING target list: one 16-byte quad per enemy object this object can attack. Quad = (A=target TCombatObject*, B=CV, C=W |
| `+0x14` | 4 | `engine_tquaditemlist_the_incoming_` | M | Engine.TQuadItemList* - the INCOMING/reverse list: one quad per enemy object that has registered THIS object as its target. Same quad shape, A=attacke |
| `+0x18` | 4 | `integer_running_sum_of_quad_field_` | M | Integer - running SUM of quad field B (CV, the normalised combat value this object can deal) over ALL entries of the outgoing list 0x10. I.e. this obj |
| `+0x1C` | 4 | `integer_running_sum_of_quad_field_` | D | Integer - running SUM of quad field C (WallCV, the value returned by the virtual GetTargetWallCV, only non-zero when the combat has walls) over all en |
| `+0x20` | 4 | `integer_running_sum_of_quad_field_` | M | Integer - running SUM of quad field B (CV) over all entries of the INCOMING list 0x14, accumulated by the attacker when it registers this object. I.e. |
| `+0x24` | 4 | `integer_running_sum_of_quad_field_` | D | Integer - running SUM of quad field C (WallCV) over the INCOMING list 0x14; the wall counterpart of 0x20. !! It is incremented in AddTarget but NEVER  |
| `+0x28` | 4 | `integer_count_of_entries_in_the_ou` | D | Integer - COUNT of entries in the outgoing list 0x10 whose CV (quad B) is > 0, i.e. how many enemy objects this object can actually damage. Incremente |
| `+0x2C` | 4 | `integer_count_of_entries_in_the_ou` | D | Integer - COUNT of entries in the outgoing list 0x10 whose WallCV (quad C) is > 0. Wall counterpart of 0x28. Maintained correctly in both directions b |
| `+0x30` | 4 | `integer_count_of_entries_in_the_in` | M | Integer - COUNT of entries in the INCOMING list 0x14 whose CV (quad B) is > 0, i.e. how many enemies can actually damage this object. Zero means nothi |
| `+0x34` | 4 | `integer_count_of_entries_in_the_in` | D | Integer - COUNT of entries in the INCOMING list 0x14 whose WallCV (quad C) is > 0. Wall counterpart of 0x30. Maintained correctly in both directions b |
| `+0x38` | 4 | `integer_memoised_result_of_the_vir` | M | Integer - memoised result of the virtual GetTargetPriority: the AI score for 'how attractive is it for this object to act'. Computed as (N+2) * SUM ov |
| `+0x3C` | 1 | `boolean_delphi_byte_boolean_dirty_` | M | Boolean (Delphi Byte/Boolean) - DIRTY flag for the 0x38 priority cache. Set to 1 by TargetsChanged (called whenever any target edge is added or remove |
| `+0x40` | 4 | `integer_memoised_result_of_the_vir` | M | Integer - memoised result of the virtual GetTargetStrength: the AVERAGE of quad field D (DV, the raw maximum damage value against that target) over th |
| `+0x44` | 1 | `boolean_delphi_byte_boolean_dirty_` | M | Boolean (Delphi Byte/Boolean) - DIRTY flag for the 0x40 strength cache. Set to 1 by TargetsChanged; cleared to 0 at the end of GetTargetStrength. No p |
| `+0x45` | 1 | `player_side` | D | GetPlayer |
| `+0x46` | 1 | `grid_position` | M | packed party<<4 | slot_in_party, each nibble 0..7; 0x80 = wall sentinel. NOT a printable id -- that name came from TCombatUnit.IDStr merely IntToStr-ing it |
| `+0x47` | 1 | `state_flags` | D | alive iff (x & 0x09) == 0 |
| `+0x48` | 1 | `conquer_flags` | D | bit0 = conquer object |

### TCombatUnit  (instance size `0x5C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x4C` | 4 | `strategic_unit` | M | PTR:TAbstractUnit -- ⚠ a TAbstractUnit*, NOT a TUnit*: THero and TLeader live here too. TCombatUnit ONLY; GetAlignment forwards through it. TCombatWall+0x4C is a packed byte, TCombatPredictorUnit+0x4C is signed HP -- the alias behind the 'Blt Error' bug |
| `+0x50` | 4 | `pointer_to_the_tcombatparty_this_c` | M | Pointer to the TCombatParty this combat unit currently belongs to (the on-battlefield stack, index = field_0x46 >> 4). Non-owning cache, no AddRef/Rel |
| `+0x54` | 1 | `boolean_this_unit_is_aboard_the_ar` | M | Boolean: "this unit is aboard the army's transport" (embarked cargo, e.g. a land unit inside a boat in a water battle). Set to True exactly when the u |
| `+0x55` | 1 | `cached_wall_combat_features_bitmas` | M | Cached wall-combat-features bitmask -- what this unit can do to/against a besieged city wall this battle. Recomputed, not serialized. Value = TAbstrac |
| `+0x58` | 4 | `int32_index_of_the_tunitgfxresourc` | M | Int32 index of the TUnitGFXResource this combat unit currently holds a reference on; -1 (0xFFFFFFFF) means "none held". Pure refcount bookkeeping, not |

### TExplorationSite  (instance size `0x38`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x30` | 1 | `defender_strength` | D | 0 none, 1-3 fixed, 4 = editor 'Random' |
| `+0x34` | 4 | `defenders_army` | D |  |

### THero  (instance size `0x9C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x3C` | 4 | `face_resource_index_index_into_tfa` | M | Face resource index - index into TFaceResourceList selecting the hero's portrait. Seeded from heroResource[+0x30] when the map is in editor mode; over |
| `+0x40` | 4 | `resource` | M | ⚠ stat block is 5 bytes EARLIER than TUnit's |
| `+0x44` | 4 | `hero_resource_index_the_index_into` | M | Hero resource index - the index into THeroResourceList identifying which hero template/definition this hero instance is. 0xFFFFFFFF = unassigned. Reso |
| `+0x48` | 4 | `experience_points_the_hero_s_raw_x` | M | Experience points (the hero's raw XP total; level is derived from it, not stored - +0x4C only caches the last computed level). |
| `+0x4C` | 1 | `level_cache` | M | 1 BYTE, not 4. Pure cache of ExperienceToLevel(+0x48); the experience dword at +0x48 is authoritative |
| `+0x50` | 4 | `a_subtractive_offset_applied_to_th` | M | A subtractive offset applied to the hero's skill-point allowance - skill points that have been written off and can no longer be spent. Pool = level*10 |
| `+0x54` | 1 | `upgrade_pending` | D |  |
| `+0x55` | 1 | `flag_byte_bit_0_the_hero_is_dead_k` | M | Flag byte. Bit 0 = the hero is dead (killed but retained in THeroControl so it can be resurrected/recalled). No other bit of this byte is read or writ |
| `+0x58` | 4 | `death_timestamp_a_copy_of_the_owni` | M | Death timestamp: a copy of the owning player's turn counter (TPlayer+0x5C) taken at the moment the hero was killed. Used as a cooldown so the hero wil |
| `+0x5C` | 1 | `the_player_index_that_owned_the_he` | M | The player index that owned the hero at the moment it was killed (the player it "died under"). Paired with +0x58 to gate re-joining that same player,  |
| `+0x5D` | 1 | `transient_runtime_flag_byte_not_se` | M | Transient runtime flag byte - NOT serialized (absent from THero.ReadWrite's field list). Bit 0 = "currently copying this hero from a hero-library temp |
| `+0x60` | 4 | `custom_name` | D | AnsiString |
| `+0x64` | 4 | `nickname_epithet_a_delphi_long_str` | M | Nickname / epithet - a Delphi long string (AnsiString pointer), separate from the hero's name at +0x60. |
| `+0x68` | 1 | `race_id_signed_byte_1_no_race_mirr` | M | Race id (signed byte; -1 = no race). Mirrors the hero resource's race field but is stored per-instance so it survives independently of the resource. |
| `+0x69` | 1 | `gender_thero_stores_it_per_instanc` | M | Gender. THero stores it per-instance; the base class returns the constant 2 and TUnit reads it from the unit resource, so this is the hero-specific ov |
| `+0x6A` | 1 | `atk_bonus` | D |  |
| `+0x6B` | 1 | `def_bonus` | M | read by THero.GetDefense |
| `+0x6C` | 1 | `damage_bonus_purchased_with_skill_` | M | Damage bonus purchased with skill points (signed). Costs 10 skill points per point - the most expensive of the six upgradable stats - and is clamped s |
| `+0x6D` | 1 | `maxhp_bonus` | D |  |
| `+0x6E` | 1 | `maxmv_bonus` | D |  |
| `+0x6F` | 1 | `res_bonus` | D |  |
| `+0x70` | 4 | `items` | M | PTR:THeroItems; THero.GetDefense reads it |
| `+0x74` | 4 | `inventory` | D | THeroInventory, 8 backpack slots |
| `+0x78` | 1 | `persistent_boolean_that_hides_the_` | D | Persistent Boolean that hides the hero from the hero-browse grids. Both hero grids include a hero only if `(TAoWEngine[+0x30] & 2) != 0 || hero[+0x78] |
| `+0x79` | 1 | `move_points_cur` | D |  |
| `+0x7A` | 1 | `hit_points_cur` | D |  |
| `+0x7C` | 4 | `power_source` | D | not serialized |
| `+0x80` | 1 | `casting_points` | D | RW tag 0x0D |
| `+0x84` | 4 | `spell_in_progress` | D | tag 0x0E |
| `+0x88` | 4 | `casting_progress` | D | tag 0x1F |
| `+0x8C` | 4 | `mana_required` | D | tag 0x22 |
| `+0x90` | 4 | `library_hero_id` | M | tag 0x23, -1 = not a library hero; paired with the library set name at +0x94. THero.GetLibraryHero is `cmp [eax+0x90],-1; setnz al`. NOT a casting-ready event-log id -- no such field exists on THero |
| `+0x94` | 4 | `ansistring_the_name_of_the_hero_li` | M | AnsiString: the name of the hero library (the .hero library file/collection) this hero was defined in. Together with dwLibrary_hero_id at +0x90 it is  |
| `+0x98` | 1 | `boolean_this_hero_is_currently_reg` | M | Boolean: "this hero is currently registered in the map's THeroControl list". Guards the register/unregister pair against double entry. |

### TItem  (instance size `0x4C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `container` | D | set by TItem.SetOwner |
| `+0x08` | 4 | `pointer_to_the_heap_allocated_abil` | M | [introduced by TCustomAbilityList] Pointer to the heap-allocated ability BITSET buffer - one bit per ability id, byte-indexed [id>>3], bit (id&7). Allocated/resized by ReallocMem to (Ab |
| `+0x0C` | 4 | `abcount_the_capacity_of_the_abilit` | M | [introduced by TCustomAbilityList] AbCount - the CAPACITY of the ability bitset in bits, i.e. the number of ability-id slots covered (highest usable ability id + 1). It is NOT a populat |
| `+0x10` | 4 | `head_pointer_of_a_singly_linked_li` | M | [introduced by TAbilityOwner] Head pointer of a singly-linked list of TAbilityData objects (per-ability extra payload, e.g. TUnitEnchantmentAbilityData). Nodes are chained through  |
| `+0x14` | 4 | `item_id` | D | RW tag 0x11 |
| `+0x18` | 4 | `name` | D | tag 8 |
| `+0x1C` | 1 | `flags` | D | bit0 = activated |
| `+0x20` | 4 | `reference_count_initialised_to_1_o` | M | Reference count. Initialised to 1 on construction; AddRef/Release are the VMT+0x28/+0x2C slots and the object self-destructs when it reaches 0. Delibe |
| `+0x24` | 4 | `library_item_id_this_item_s_unique` | M | Library item ID - this item's unique id inside its item library (paired with the library name at 0x28). The sentinel -1 (0xFFFFFFFF) means 'not a libr |
| `+0x28` | 4 | `ansistring_delphi_long_string_hold` | M | AnsiString (Delphi long string) holding the NAME OF THE ITEM LIBRARY this item was instantiated from; combined with the library id at 0x24 to re-resol |
| `+0x2C` | 4 | `obtain_value` | D | tag 0x13; GetObtainValue = max(x,10) |
| `+0x30` | 4 | `unknown_provably_a_delphi_long_str` | S | UNKNOWN - provably a Delphi long string (AnsiString) belonging to the item's own definition data (stream property id 9, immediately after Name at id 8 |
| `+0x34` | 1 | `item_type` | D | TItemTypes enum, tag 0x0F |
| `+0x38` | 4 | `spell_id` | D | tag 0x14 |
| `+0x3C` | 4 | `ability_list` | D | TStringList, tag 0x12 |
| `+0x40` | 4 | `gfx_index` | D | tag 7 |
| `+0x44` | 1 | `unknown_enum` | M | 1 BYTE, not 2 (+0x45 is a proven distinct field). tag 0x10, meaning still unresolved |
| `+0x45` | 1 | `rarity` | D | tag 0x0A |
| `+0x46` | 1 | `atk_bonus` | D | tag 0x0B |
| `+0x47` | 1 | `def_bonus` | D | tag 0x0C |
| `+0x48` | 1 | `dam_bonus` | D | tag 0x0D  ⚠ note order: TItem is ATK,DEF,DAM,RES |
| `+0x49` | 1 | `res_bonus` | D | tag 0x0E   whereas TUnit caches are ATK,DEF,RES,DAM |
| `+0x4A` | 1 | `unused_padding` | M | free zero-init padding in the vanilla 0x4C allocation; NOT claimed in either binary. The 'mod claims it' note came from a design proposal that was never built |
| `+0x4B` | 1 | `unused_padding2` | M | as +0x4A -- unbuilt proposal, not a live field |

### TPlayer  (instance size `0xDC`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `update_lock_nesting_counter_beginu` | M | Update-lock nesting counter (BeginUpdate/EndUpdate depth). While non-zero every change-notification is suppressed; EndUpdate decrements and, at 0, fir |
| `+0x0C` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's GOLD changes. |
| `+0x10` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's per-turn INCOME changes. |
| `+0x14` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's UPKEEP changes. |
| `+0x18` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's event LOGBOOK changes. |
| `+0x1C` | 4 | `aowe_tplayerstructurelist_a_techan` | M | AoWE.TPlayerStructureList (a TEChangeNotifyEventList, with [list+0x14] = back-pointer to this player) holding EVERY structure this player owns (cities |
| `+0x20` | 4 | `aowe_tplayerstructurelist_of_this_` | M | AoWE.TPlayerStructureList of this player's VICTORY / capture locations (the win-condition sites). Emptiness of the not-yet-captured subset ends the ga |
| `+0x24` | 4 | `aowe_tproductioncontrollist_the_pl` | M | AoWE.TProductionControlList - the player's list of active production controls (one per producing site/city queue). |
| `+0x28` | 4 | `aowe_tarmylist_techangenotifyevent` | M | AoWE.TArmyList (TEChangeNotifyEventList, [list+0x14] = this player) - every army the player owns. Its change event is TPlayer.ArmiesChanged; emptying  |
| `+0x2C` | 1 | `boolean_turn_ended_flag_for_this_p` | M | Boolean "turn ended" flag for this player. |
| `+0x34` | 4 | `unknown_a_classes_tstringlist_owne` | S | UNKNOWN. A Classes.TStringList owned by the player: constructed in Create, streamed as property id 0x28, freed in Destroy - and never read, written or |
| `+0x38` | 4 | `aowe_tdiplomaticrelationlist_a_tby` | D | AoWE.TDiplomaticRelationList (a TByteList indexed by player id, value = relation enum) holding an initial relation table that is consumed at map start |
| `+0x3C` | 4 | `aowe_tdiplomaticrelationlist_tbyte` | M | AoWE.TDiplomaticRelationList (TByteList, index = player id, value = relation enum) holding the map/setup-authored STARTING diplomatic relations. At ma |
| `+0x40` | 4 | `aowe_tplayerdiplomaticrelations_th` | M | AoWE.TPlayerDiplomaticRelations - the player's LIVE diplomacy object ([+8] = back-pointer to this player, [+0x0C] = TByteList of current relations per |
| `+0x44` | 1 | `player_status` | M | 1-BYTE tri-state: 0 = still playing, 1 = victory, 2 = defeated. Not a 4-byte bool |
| `+0x45` | 1 | `player_participation_state_0_not_i` | M | Player participation state: 0 = not in play yet (initial), 1 = active/in the game, 2 = removed/eliminated from the game. This is the "is this player a |
| `+0x48` | 4 | `busy_lock` | D |  |
| `+0x4C` | 4 | `ansistring_the_player_s_own_name_u` | M | AnsiString: the player's own name, used only when the player has NO leader hero (0xD4 == nil). When a leader exists the name lives on the hero (hero+0 |
| `+0x54` | 4 | `magic_control` | D | TPlayerMagicControl |
| `+0x58` | 4 | `an_owned_aowe_tleader_instance_tha` | D | An owned AoWE.TLeader instance that acts as the stand-in for the player's leader at stream slot 0x1E: TPlayer.ReadWrite writes/reads either this objec |
| `+0x60` | 4 | `aowe_tplayerstatistics_the_per_tur` | M | AoWE.TPlayerStatistics - the per-turn statistics object; [obj+8] is the TTurnInfo list of TTurnInfoItem records (gold, mana, structure count, total ar |
| `+0x64` | 4 | `aowe_tincomesourcelist_the_list_of` | M | AoWE.TIncomeSourceList - the list of objects that contribute gold income; [list+8] is the underlying TList. Summed each turn into the income total at  |
| `+0x68` | 4 | `unknown_a_third_aowe_tplayerstruct` | S | UNKNOWN. A third AoWE.TPlayerStructureList (TEChangeNotifyEventList) that is constructed in TPlayer.Create and freed in TPlayer.Destroy but is never a |
| `+0x70` | 4 | `base_day_for_hero_join_hero_emerge` | M | Base day for hero-join/hero-emerge timing: the game day from which the next hero offer is measured. GetIdealHeroJoinDay returns this + 5/10/15 dependi |
| `+0x80` | 4 | `aowe_therolist_the_heroes_currentl` | M | AoWE.THeroList - the heroes currently belonging to this player. |
| `+0x84` | 4 | `aowe_taigrouplist_the_ai_groups_ar` | M | AoWE.TAIGroupList - the AI groups (army task forces) owned by this player. |
| `+0x88` | 4 | `aowe_taiplayercontrol_this_player_` | M | AoWE.TAIPlayerControl - this player's AI controller object; [obj+8] is a back-pointer to the player. Streamed as an object at id 0x1C and forwarded ev |
| `+0x8C` | 4 | `aowe_taibudgetmanager_this_player_` | M | AoWE.TAIBudgetManager - this player's AI gold/mana budget manager; [obj+8] is a back-pointer to the player. Streamed as an object at id 0x33 and forwa |
| `+0x90` | 4 | `aowe_tdiplomaticactionlist_the_log` | M | AoWE.TDiplomaticActionList - the log of diplomatic actions involving this player, kept so the AI can find the last action of a given type and not repe |
| `+0x94` | 4 | `engine_tbitlist_indexed_by_player_` | M | Engine.TBitList indexed by player id - the AI's "valid attack targets" mask (bit set when the diplomatic relation to that player is 1, i.e. war). |
| `+0xA0` | 4 | `aowe_tpbemplayersettings_the_playe` | M | AoWE.TPBEMPlayerSettings - the player's play-by-email settings object ([+8] byte flag, [+0x0C] an AoWE.TEmailGame). |
| `+0xA5` | 1 | `race_id_of_the_player_index_into_t` | M | Race id of the player (index into the race tables; 0xFF = none/unset, the Create default). |
| `+0xA6` | 1 | `player_index` | D |  |
| `+0xA7` | 1 | `player_type` | D | PlayerType enum; 4 = independent. NOT a bare human/AI bool |
| `+0xAC` | 4 | `starting_gold_for_the_player_map_s` | M | Starting gold for the player (map/setup authored). Default 250 (0xFA); copied into dwGold (0xC4) when a new map starts. |
| `+0xB0` | 4 | `flat_base_gold_income_per_turn_the` | M | Flat base gold income per turn: the starting value of the income accumulator before the registered income sources are summed (result stored in 0xD0).  |
| `+0xC4` | 4 | `gold` | D |  |
| `+0xC8` | 4 | `cached_army_gold_upkeep_total_for_` | M | Cached ARMY (gold) upkeep total for the player - the summed per-unit upkeep of all its armies. |
| `+0xCC` | 4 | `cached_magic_mana_upkeep_total_for` | M | Cached MAGIC (mana) upkeep total for the player. |
| `+0xD0` | 4 | `cached_total_gold_income_per_turn_` | M | Cached total gold income per turn = base (0xB0) + sum of all registered income sources, then scaled/bonused by AI difficulty (bPlayer_type 2,3 multipl |
| `+0xD4` | 4 | `pointer_to_the_player_s_leader_uni` | M | Pointer to the player's LEADER unit (AoWE.TLeader / THero). Nil means no leader; the object supplies the player's name (hero+0x60), face, map location |
| `+0xD8` | 4 | `event_logbook` | D |  |

### TRangedAttackAbility  (instance size `0x30`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x28` | 1 | `range_tier` | D | 0..3, NOT a hex count |
| `+0x29` | 1 | `base_ranged_damage` | M | GetDamageRA reads it |
| `+0x2A` | 1 | `base_ranged_attack` | D |  |
| `+0x2B` | 2 | `innate_damage_types` | D | DamageTypeBits |
| `+0x2D` | 1 | `attack_repeat_count_how_many_separ` | M | Attack-repeat count: how many separate ranged shots/strikes this ability fires per attack. Backing field for the virtual getter TRangedAttackAbility.G |

### TSpell  (instance size `0x34`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `name` | D | plain LStr value, no VMT call |
| `+0x0C` | 1 | `castcontexts_a_delphi_set_bit_flag` | M | CastContexts: a Delphi SET (bit flags) of the contexts in which this spell may be cast. Bit 1 (mask 0x02) = CASTABLE IN COMBAT -- this is directly pro |
| `+0x10` | 4 | `spell_id` | D |  |
| `+0x14` | 4 | `mana_cost` | D | RW id 0x0D |
| `+0x18` | 4 | `research_cost` | D | RW id 0x0F; Create defaults it to 1 |
| `+0x1C` | 4 | `mana_upkeep_per_turn` | M | RW id 0x0E -- MANA UPKEEP PER TURN, not a casting-point cost. Nothing spends casting points from this field |
| `+0x20` | 1 | `sphere` | D | MagicSphere enum, RW id 0x10 |
| `+0x21` | 1 | `research_tier` | D | ResearchTier enum, RW id 0x11 |
| `+0x22` | 1 | `category` | D | 2 = global enchantment |
| `+0x24` | 4 | `description` | D | TStringList, RW id 0x0A |
| `+0x28` | 4 | `sfx` | D | RW id 0x0B |
| `+0x2C` | 4 | `images` | D | TImageSequenceList, RW id 0x0C; seq 10 = book icon |
| `+0x30` | 4 | `ai_value` | D |  |

### TStrikeCA  (instance size `0x1C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `reference_count_lifetime_refcount_` | M | [introduced by TCombatAction] Reference count (lifetime refcount). Initialised to 1 by the constructor; AddRef increments and returns the new count; Release decrements and, on reac |
| `+0x0C` | 1 | `flags` | D | bit0 = defensive/retaliation |
| `+0x0D` | 1 | `attacker_id` | D |  |
| `+0x0E` | 1 | `target_id` | D |  |
| `+0x10` | 1 | `rolled_damage` | D | 0 = MISS |
| `+0x11` | 2 | `effective_damage_types` | D | 0 => fully immune |
| `+0x13` | 2 | `effect_landings` | D |  |
| `+0x15` | 1 | `applied_damage` | D | written in Execute |
| `+0x18` | 4 | `effect_flags` | D | ⚠ TStrikeCA ONLY. TCombatSpellCA+0x18 is the SPELL ID; a ranged CA carries the ability id there |

### TStructure  (instance size `0x30`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `map_field` | D |  |
| `+0x08` | 4 | `resource` | D |  |
| `+0x0C` | 1 | `object_state_flag_set_delphi_set_b` | M | Object state flag set (Delphi set, byte-wide). Named bits, from sibling accessors that read the same offset: bit0 (0x01) = Visible, bit1 (0x02) = Edit |
| `+0x10` | - | `hex_x_coordinate_hx_x_of_the_objec` | M | Hex X coordinate (HX x) of the object on the map - signed byte. Feeds every hex-geometry call the class makes. |
| `+0x11` | - | `hex_y_coordinate_hx_y_of_the_objec` | M | Hex Y coordinate (HX y) of the object on the map - signed byte. Always used as the second argument alongside +0x10. |
| `+0x14` | 4 | `cached_image_index_for_the_object_` | M | Cached image INDEX for the object's current terrain type - i.e. the memoised result of the virtual GetTerrainTypeImage (VMT+0x12C) applied to the terr |
| `+0x18` | - | `terrain_type_the_object_currently_` | M | Terrain type the object currently sits on / renders for - signed byte (negative = none/invalid). Set from the terrain-changed notification and from th |
| `+0x1C` | 4 | `structure_id` | D |  |
| `+0x20` | 4 | `beginupdate_endupdate_nesting_coun` | M | BeginUpdate/EndUpdate nesting counter (signed int, 0 = not inside an update block). Suppresses the TAoWHSMap.StructureChanged repaint/notify while non |
| `+0x24` | 1 | `player_index_of_the_player_current` | M | Player index of the player currently building or rebuilding this structure; 0xFF = nobody (the 'not under construction' sentinel). GetBuilding is lite |
| `+0x25` | 1 | `turns_remaining_until_the_current_` | M | Turns remaining until the current build/rebuild finishes - a countdown byte. Decremented once per turn of the player held in +0x24; when it reaches 0  |
| `+0x28` | 4 | `pointer_to_this_structure_s_aowe_t` | M | Pointer to this structure's AoWE.TStructureShadow companion object (nil when it has none). The shadow is a separate hex sprite that back-references th |
| `+0x2C` | 1 | `cached_this_structure_is_currently` | M | Cached 'this structure is currently hidden by fog of war' boolean (1 = hidden). Recomputed by FogChanged: seeded from the map's global fog flag (map+0 |

### TUnit  (instance size `0x48`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x3C` | 1 | `experience` | D | GetRank recomputes from it |
| `+0x3D` | 1 | `move_points_cur` | D |  |
| `+0x3E` | 1 | `hit_points_cur` | D | signed |
| `+0x3F` | 1 | `unknown_no_semantic_a_dead_byte_it` | D | UNKNOWN / no semantic - a dead byte. It is never read, written, compared, LEA'd, or streamed anywhere in AoWEPACK.dpl. Structurally it is the 1-byte a |
| `+0x40` | 4 | `resource` | M | PTR:TUnitResource -- ⚠ THero+0x40 is a DIFFERENT layout |
| `+0x44` | 1 | `atk_modifier_cache` | M | GetAttack adds it |
| `+0x45` | 1 | `def_modifier_cache` | M | GetDefense adds it |
| `+0x46` | 1 | `res_modifier_cache` | M | GetResistance adds it |
| `+0x47` | 1 | `dam_modifier_cache` | D | by position; the other three are measured |
| `+0x7C` | - | `casting_cluster` | D | ⚠ MOD ONLY -- vanilla instsize is 0x48. build_spellcast.py grows the class; +0x7C..+0x93 mirror THero's cluster |

### TUnitResource  (instance size `0x54`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x18` | 4 | `gfx_index` | D |  |
| `+0x1C` | - | `the_unit_type_s_name_a_delphi_ansi` | M | The unit type's name - a Delphi AnsiString (long-string pointer). It is the base component of the displayed unit name: TUnitResource.GetUnitName assig |
| `+0x20` | 1 | `race` | D |  |
| `+0x21` | 1 | `unknown_it_is_a_1_byte_non_pointer` | S | UNKNOWN. It is a 1-byte, non-pointer, persisted field (stream property id 0x16) that no code anywhere in AoWEPACK.dpl ever reads or writes - it is onl |
| `+0x24` | 4 | `own_name` | M | AnsiString, pfs tag 0x0B -- the unit's OWN name ("Rider", "Priest"), NOT a display name |
| `+0x28` | 1 | `alignment_a_talignment_enum_byte_0` | M | Alignment - a TAlignment enum byte: 0=alPureGood, 1=alGood, 2=alPureNeutral, 3=alNeutral, 4=alEvil, 5=alPureEvil, 6=alNone. This is the unit's inheren |
| `+0x29` | 1 | `base_attack` | M | TUnit.GetAttack reads it |
| `+0x2A` | 1 | `base_defense` | M | TUnit.GetDefense reads it |
| `+0x2B` | 1 | `base_damage` | D |  |
| `+0x2C` | 1 | `base_hits` | D |  |
| `+0x2D` | 1 | `base_moves` | D |  |
| `+0x2E` | 1 | `base_resistance` | M | TUnit.GetResistance reads it |
| `+0x2F` | 1 | `level_tier` | D | GetUpkeep = +0x2F + 1 |
| `+0x30` | 1 | `unit_type` | D | pfs tag 0x15; see UnitType_PARTIAL enum |
| `+0x31` | 1 | `gender_a_tunitgender_enum_byte_0_u` | M | Gender - a TUnitGender enum byte: 0=ugMale, 1=ugFemale, 2=ugNeutral. |
| `+0x32` | 1 | `transport_capacity_MOD` | D | ⚠ INSTALLED ONLY -- moved here from +0x44 by build_copper_medal.py |
| `+0x38` | 4 | `ability_owner_rank0` | D | pfs tag 0x19 |
| `+0x3C` | 4 | `ability_owner_rank1` | D | vanilla: silver. INSTALLED: copper (tag 0x20) |
| `+0x40` | 4 | `ability_owner_rank2` | D | vanilla: gold. INSTALLED: silver (tag 0x1E) |
| `+0x44` | 1 | `transport_capacity_VANILLA` | M | 1 BYTE in vanilla (pfs tag 0x18); +0x45..+0x47 are padding -- which is exactly what let build_copper_medal.py reuse the dword. INSTALLED: gold ability owner (tag 0x1F) |
| `+0x48` | 4 | `description_list` | M | TStringList OBJECT POINTER, not an AnsiString -- reading it as a string is wrong. pfs tag 0x1A |
| `+0x4C` | 4 | `gold_cost` | D | pfs tag 0x1B |
| `+0x50` | 1 | `unit_size` | M | TUnit.GetUnitSize reads [[unit+0x40]+0x50] |
| `+0x51` | 1 | `blood_type_a_tbloodtype_enum_byte_` | M | Blood type - a TBloodType enum byte selecting the colour of the blood/gore effect the unit produces: 0=btNone, 1=btRed, 2=btBlue, 3=btGreen. Defaults  |
| `+0x52` | - | `not_a_field_trailing_alignment_pad` | D | Not a field - trailing alignment padding in the instance. The last real field is the 1-byte 0x51, so the declared layout ends at 0x52, and Delphi roun |

## 10. Pristine references, backups, and the revert convention

### 10.1 Two files are load-bearing — do not delete either in any cleanup

| file | why it must survive |
|---|---|
| `Modding Resources/AoWEPACK_original_backup.dpl` | the pristine pre-modding DLL — the "is this vanilla behaviour?" byte-diff reference every script's verify-before-write and this whole toolchain's discipline depends on. It is also what the Ghidra vanilla project (§1–§2) was imported from. |
| `Ziggurat upload/AoW.exe` (dated 2025-03-21) | the **only** unpatched exe left anywhere in the tree; `build_herodlg_columns.py --apply` copies the vanilla fill loop out of it and cannot rebuild without it |

Both confirmed present as of this merge.

### 10.2 ⚠⚠ Never restore either pristine reference over a live file

Copying `AoWEPACK_original_backup.dpl` over the live `AoWEPACK.dpl` would wipe roughly 150 features'
worth of patches in one move — this has been proposed before (an old predictor-fix doc's revert
instructions said exactly this) and must never be followed. If a topic ever touches restoring a
pristine DLL, say so plainly and refuse the shortcut; the only correct revert path is a feature's own
surgical `--undo` (§10.4).

**The reverse direction is just as dangerous and less obvious: never let anything overwrite the
pristine reference with a copy of the live file.** `build_patch.py --apply` does exactly this — see
§5.7. Verified 2026-09-03: the pristine reference is still intact, because that script has not been
run since this convention was established. Treat any script whose `--apply` path writes to
`AoWEPACK_original_backup.dpl` as a standing hazard, not just that one.

### 10.3 The `Modding Resources/backups/` directory does not exist — stop looking for it

On 2026-08-08 roughly 100 `.pre-*` snapshots were deleted deliberately (each a full ~2.7 MB copy;
~270 MB of accumulated bloat), and the `backups/` directory itself no longer exists. **Do not go
looking for it, and disregard any doc — including some of the very docs this file was merged from —
that describes features as living in "two backup directories" or quotes a layer count like "27 of
47".** Those counts were true the day they were written and are meaningless now; several of the
specific `.pre-*` files they referred to (`.pre-trueseeing`, several others) have themselves since
been deleted.

**And `<root>/backups/` is gone too — deleted 2026-09-10** (29 `.pre-*` snapshots, 52 MB, which had
been sitting inside the pristine vanilla install). That was the third such clear-out, after
`Modding Resources/backups/` in 2026-08-08 and the 88-file root stack on 2026-09-03.

**Current state, measured 2026-09-10 — there is NO binary snapshot layer at all:**

| | |
|---|---|
| `*.exe.pre-*`, `*.dpl.pre-*` | **zero, anywhere in the tree** |
| surviving `.pre-*` | 10 **data-file** snapshots only — `.ILB`, `.pfs`, `.ail` — and each exists twice, once at `<root>` and once in `Ziggurat/` |
| where a new one is minted | `Ziggurat/backups/`, per `BACKUP_DIR`. ⚠ It does not exist yet; it is created on demand by the first script that mints into it. |

This is fine, and is the intended state: **every feature's real revert path is its own script's
surgical `--undo`, not a file.** A `.pre-<feature>` restore still wipes every layer applied to that
file *after* the snapshot was taken. ⚠⚠ Two corollaries that have already misled this project:
**the absence of a `.pre-X` is no longer evidence that feature X was never applied** (several docs
used it that way), and any doc naming a specific `.pre-*` as its revert path is quoting a file that
does not exist. Derive the inventory rather than quoting a count from any doc, this one included:

```bash
find . -name '*.pre-*'                            # the real inventory, whole tree
```

⚠ **A `.pre-<feature>` file is not proof of anything until byte-checked against known-vanilla bytes.**
A snapshot can be taken by a rebuild that ran *after* a feature was already installed, in which case
it is a snapshot of the previous **patched** state, not a pristine one — never trust a filename alone.
`shutil.copy2` preserves mtimes, so sorting by mtime gives the true layer order for a given target
file; only the *newest* backup for that file is a safe one-layer revert, and "newest" expires the
moment anyone patches that file again.

`re_tools/bisect_dll.py` binary-searches this stack to find which feature broke something — it still
has material to work with, but only for files whose snapshots were taken from a *proven* baseline
(byte-check first).

### 10.4 The re-tune procedure is REWRITE THE CAVE IN PLACE, never "revert and re-apply"

Never write "revert to `.pre-X` and re-apply with new constants" as a re-tune procedure for any
feature that shares its cave, its VMT slot, or its hook site with anything applied afterward — that
revert would take every later feature down with it, and there may be no snapshot left that predates
all of them anyway.

Instead, the build script should **rewrite its own cave in place**: verify-before-write against
*either* the currently-installed bytes or the newly-computed ones, overwrite, and assert that any
zone the cave grows into is still zero. Take a fresh feature-named backup so the revert path stays
exactly one layer deep. `build_invis_penalty.py` rewriting `build_trueseeing.py`'s three cave bodies
in place (§6.1) is the clean worked example; `build_dispelmagic5.py`'s relocation-with-repair logic
(§6.3) is the same discipline applied to a *moved* cave, not just a re-tuned one.

**Better still: give the script a genuine surgical `--undo`** that restores the original hook/VMT
slot bytes and zeroes its own cave, verify-before-write, touching no backup file at all. That path
survives both layering and pruning. Worked examples with a real surgical `--undo`:
`build_sitedefender_vary.py`, `build_magebane.py`, `build_mastery_cost.py`,
`build_stormeffectroll.py`, `build_crusade_spawns.py`; also `build_ai_itemtarget.py`,
`build_debuffcache.py`, `build_effectroll.py`, `build_hpbar_clamp.py` under a `--revert` flag.

⚠ **Not every `--revert` flag is surgical — read the implementation before trusting it.**
`build_mapcursor_fix.py --revert` just restores its `.pre-mapcursor` snapshot, which is exactly as
destructive as a manual copy would be (§10.3's warning applies to it in full). A flag name is not a
guarantee; check what the code actually does.

---

## 11. Process locks and the AoWCompat lockstep rule

### 11.1 Game files are locked while any AoW binary is running

`AoWz.exe`, `AoWzCompat.exe`, `AoWzEd.exe`, `AoWDevEd.exe` (and vanilla `AoW.exe` / `AoWCompat.exe`,
`AoWEd.exe`) all lock their own files while running. A
lock surfaces as "Device or resource busy" or a `PermissionError` on write. `AoWDevEd.exe` loads
`AoWEPACK.dpl`, so it locks the DLL too, not just its own exe.

**⚠ Standing authorisation: just kill them, don't ask.** If a lock is blocking an `--apply`, `--undo`,
or any other write, terminate the process and retry — do not stop to ask the user to close the game
first. There is nothing to lose: the game autosaves per turn, and the editor prompts on its own next
launch regardless.

```powershell
Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd|AoWSetup)$' } | Stop-Process -Force
```

`AowEmailWrapper` and `Launcher` do **not** lock the binaries — leave them running. Match process
names exactly with `^...$`, or the `-match` operator will also catch `AowEmailWrapper` by accident
(it contains "AoW" as a substring).

### 11.2 `AoWzCompat.exe` is `AoWz.exe` with exactly ONE byte changed

`AoWzCompat.exe` is not a separate binary to analyse. The only difference is file offset `0x3BB7C`
(VA `0x43C77C`), the reported build number in the multiplayer version check — `0x0F` (v1.36.0015) in
`AoWz.exe` versus `0x05` (v1.36.0005) in `AoWzCompat.exe`. It exists purely to let this build talk
multiplayer to peers still on 1.36.0005.

⚠⚠ **The split is a ZIGGURAT property, not a vanilla one** (measured 2026-09-09). GOG ships the
root `AoW.exe` and `AoWCompat.exe` **byte-identical** — both `f2c3630ead01aaae7c3fcd27a88c992d`, both
carrying `0x05` at `0x3BB7C`. The 2026-07-24 byte-diff that first recorded this was run on the
already-modified install, so it described Ziggurat's pair, not stock. Live values: `Ziggurat\AoWz.exe`
`0x0F` / `Ziggurat\AoWzCompat.exe` `0x05`.

**Every `AoWz.exe` address, finding, and patch applies to `AoWzCompat.exe` verbatim.** Always patch
both in lockstep; never reverse-engineer `AoWzCompat.exe` separately — that would just be re-deriving
`AoWz.exe`'s own analysis under a different filename. If it is ever lost or corrupted: copy
`AoWz.exe` and flip that one byte back.

**Per-executable patches only affect their own binary otherwise.** `AoWz.exe`/`AoWzCompat.exe` (the
game) and `AoWDevEd.exe`/`AoWEd.exe` (the editor) are different builds and frequently call *different*
functions for what looks like the same feature — verify the actual call path in the binary you're
about to patch; don't assume the editor and the game share code just because the game and its MP
compatibility twin do.

### 11.3 ⭐ Never write an exe name as a literal — `zigexe.py` is the only place a binary is named

`build_scripts/zigexe.py` exports `GAME_EXE` `COMPAT_EXE` `SRC_EDITOR` `LIVE_EDITOR` `EXES`
`ALL_EXES` `LOCKING_PROCESSES` `COMPAT_BYTE` `VANILLA_EXE` `VANILLA_COMPAT`. It supplies **names,
not paths** — joining is the caller's job. Build scripts get it from a sibling `import zigexe`;
`re_tools` reaches it through `re_tools/zignames.py`, a shim that puts `build_scripts/` on
`sys.path` and re-exports the module:

```python
from zignames import zigexe
pe = PE(os.path.join(GAME, zigexe.GAME_EXE))
for name in zigexe.EXES: ...
```

It exists because the 2026-09-09 rename broke twenty-one build scripts at once and the repair was
twenty-one near-identical edits. That pass then **missed `re_tools/` entirely** — twelve tools there
still named the pre-rename pair, found and fixed 2026-09-10 (plus `sampler.py` / `stack_prof.py`,
which defaulted `--exe` to the source editor rather than the live one).

⚠⚠ **A process scan that names `AoW.exe` does not merely fail — it can answer from the WRONG
GAME.** Against a running `AoWz.exe` it reports "not running"; if vanilla `AoW.exe` happens to be
running it attaches to *that* and prints vanilla geometry, vanilla module bases, "probe has not
fired" for a probe that is installed — every one of those a wrong answer with **no error**. The
loudly-failing variant (`open(GAME/"AoW.exe")` → `FileNotFoundError`) is the harmless one. Scan
`zigexe.EXES` for "the mod game", `zigexe.ALL_EXES` for "any mod binary".

⚠ **One `re_tools` script names an old exe CORRECTLY — do not sweep it into this.**
`mod_manifest.py:85` lists `AoWEd.exe` in `NEVER_SHIP`, a filename to exclude from the payload.
(`AoWEd.exe` no longer exists in the overlay at all — only the root's stock copy, md5
`f45bebf5627d5900cd39da45d21eb792`, MATCH against the GOG hashdb.)

⚠ `rng_audit.py` was exempted here as a second exception until 2026-09-23, and the exemption hid a
defect: `AoW.exe`/`AoWCompat.exe` were the **keys** of its module table — audit targets, joined to
`Ziggurat/` — not only the reference path they mapped to, so both mod exes dropped out of every
default run for two weeks with exit code 0 (§4.7). Before exempting a name from a sweep, check
whether it is used as a target or as a reference. `rng_audit.py` now takes both from `zigexe`:
`GAME_EXE`/`COMPAT_EXE` as targets, `VANILLA_EXE`/`VANILLA_COMPAT` as references.

⚠ **A name alone does not locate a binary that is to be LAUNCHED.** `AoWz.exe` and `AoWzCompat.exe`
exist in **both** trees: the pair in `Ziggurat\` is the canonical patch source that nothing runs,
and `build_overlay.py` derives the runnable pair at the **root**. The editors are the other way
round — they run from `Ziggurat\`. `veh_capture.py`'s `resolve_target()` is the worked example, and
it launches with `cwd` = the resolved exe's own directory, not `GAME`.

### 11.4 ⭐⭐ The root exes are a LOADER CONFIGURATION, not a copy — measured 2026-09-10

`<root>\AoWz.exe` has **6 of its 22 import names rewritten** to `Ziggurat\<pkg>.dpl`, and those six
are exactly the packages that differ from vanilla:

```
Ziggurat\VCL30.dpl   Ziggurat\ILPACK.dpl    Ziggurat\HSEPack.dpl
Ziggurat\AoWEPACK.dpl  Ziggurat\aowInt.dpl  Ziggurat\AoWTCPCK.dpl
```

`Ziggurat\AoWz.exe` has **zero** backslashed imports — all 22 bare. Windows resolves implicit imports
against the **executable's own directory**, so a bare-import exe at the root would load the root's
vanilla packages. The prefix is the entire mechanism that redirects those six. That is why the
runnable pair must sit at the root, and why patching `Ziggurat\AoWz.exe` alone changes nothing until
`build_overlay.py --apply` regenerates them.

⚠ **The "share the unmodified packages" rationale does not survive measurement.** `Ziggurat\` carries
a complete 22-package set, **16 byte-identical to the root's, 2.0 MB total** — that duplication is
already paid, because `AoWzEd.exe` runs from `Ziggurat\` and resolves everything there. The ~373 MB
the overlay actually saves is the **data** tree, held by the registry `Startup Directory`, which is
independent of which exe runs. The root pair's real job is narrower: it is the only place an exe can
sit, be launched by a shortcut or the GOG entry, and still reach the modded six.

### 11.5 ⚠ `build_zigeditor.py` was silently unrunnable from 2026-09-09 to 2026-09-10

The script that builds the live editor resolved `SUBDIR = GAME\Ziggurat` → `<root>\Ziggurat\Ziggurat`,
which does not exist, and hard-exited with `!! ... does not exist -- build the overlay first`. Both
constants predated the move, when `GAME` was the game root and the mod was a subdirectory; `GAME`
**is** the mod directory now. `SUBDIR` and `STAGING` are both deleted rather than reassigned — the
names are what invite the next re-nesting.

⚠⚠ The worse half was `STAGING = GAME\Ziggurat release`: the editor source was read from the
**release staging tree**, which `mod_manifest.py --stage` refreshes. Building from it silently
discards every patch applied since the last refresh. It was latent only because the two copies
happened to agree (`d32abcb174`). Source is now `GAME\AoWDevEd.exe`.

⚠ The on-disk `AoWzEd.exe` (2026-09-09 20:50, `b4ccd52c20`) was built by the pre-fix script, i.e.
**from the staging copy**. It is trustworthy only while staging and `Ziggurat\` agree. Rebuild it
deliberately.

---

## 12. Ability-id and effect-bit quick reference

Salvaged from an otherwise-superseded 2026-07-08 investigation sweep — the numbered features that log
covered each now have their own dedicated file with the full mechanism; only the raw id/bit values
are reusable outside that context, so they're kept here rather than in a "features" file:

| ability | id |
|---|---|
| Leadership | `0x2E` |
| Life Stealing | `0x76` |
| Enchanted Weapon | `0x9A` |
| Marksmanship | `0x20` |
| Tunneling | `0x2A` |
| Poison Protection | `0x49` |
| Death Protection | `0x46` |
| Holy Protection | `0x48` |
| Spellcasting | `0x7A` |
| Transport | `0x32` |
| Drillmaster (this project's) | `0xAB` |
| Magebane (this project's) | `0xAA` |

| effect / damage-type bit | value |
|---|---|
| Poison | `0x10` |
| Death | `0x20` |
| Holy / Vertigo | `0x40` |
| Magic | `0x08` |

"Unit size" is a largely dead axis in AoW1 — `TAbstractUnit.GetUnitSize @0x5577F184` always returns 1,
i.e. **every unit in the game is 1-hex.** Any mechanic that wants to scale off "how big is this unit"
has no real stat to read; pivot to level, transport capacity, or accept a new invented cover/cost
stat. (Missile blocking, once thought to need this, does not — `AoWTCPCK.dpl`'s manual tactical
combat already intercepts shots per-hex against units/walls/Obstacle overlay/EarthWall-Border terrain
independent of any size concept; see the missile-trajectory file for the mechanism.)

---

## 13. Publishing a release — what the mod consists of, and how to prove it

⚠⚠ **First, revert every applied DIAGNOSTIC.** They are normal patches in every other respect —
`mod_manifest.py` reports their binary as CHANGED and stages it without comment, so nothing else in
this pipeline will catch one. Run each with no args and read the `state:` line:

| script | binary | what a player would see if it shipped |
|---|---|---|
| `build_te_exception_detail.py` (§3a) | `Network.dpl` | a second modal dialog with a hex offset after every swallowed turn-event exception |
| `build_razediag.py` (`10-ai-and-structures.md` §3.6) | `AoWEPACK.dpl` | with `--want-open`, an AI that razes everything it stands on, its own race's cities included |

```bash
python "Ziggurat/Modding Resources/build_scripts/build_te_exception_detail.py" --undo
python "Ziggurat/Modding Resources/build_scripts/build_razediag.py"    # all three levers must read STOCK
```

⭐ **The revert is visible in the report, and that is the confirmation to wait for.** Undoing the TE
patch returns `Network.dpl` to its GOG hash, so it leaves CHANGED and joins SAME: the counts move
`CHANGED 53 → 52`, `SAME 843 → 844`. A diagnostic whose revert does **not** move those counts either
was not applied or did not fully revert.

⭐ **`goggame-1207658883.hashdb` in the game root is a complete vanilla reference for the whole
install** — the one thing this project otherwise lacks. It is a zip containing a single file of the
same name: a 12-byte header `<III` = (headerSize=12, version=1, count=975), then `count` records of
1056 bytes = 1024-byte NUL-padded relative path (backslash separators, cp1252) + 32 ASCII hex chars
of MD5. Hashing the live tree against it partitions every file into CHANGED / ADDED / MISSING / SAME
with no guessing and no per-file baselines. This is strictly better than the mtime heuristic: the
March-2026 art carries 2025-03-21 timestamps *older* than the 2025-08-26 install date, so mtime
ordering says nothing.

```bash
python "Ziggurat/Modding Resources/re_tools/mod_manifest.py"                             # report
python "Ziggurat/Modding Resources/re_tools/mod_manifest.py" --json out.json             # manifest
python "Ziggurat/Modding Resources/re_tools/mod_manifest.py" --stage "Ziggurat/Ziggurat release"
```

⚠ **`--stage DIR` is relative to the CWD, not to `GAME`.** `GAME` moved to `Ziggurat/` in the
2026-09-09 overlay split but the argument did not follow it, so the pre-move incantation
`--stage "Ziggurat release"` run from the game root now stages into `<root>/Ziggurat release` — a
new directory inside the **vanilla** install, which `IGNORE_DIRS` does not match either (it matches
the leaf name `Ziggurat release`, so it would be ignored — but the payload is in the wrong tree and
the real staging folder silently keeps the previous release's bytes). Pass the path you mean.

⚠⚠ **`--stage` only ever copies; it never prunes.** A file that drops out of the payload — because
it went into `NEVER_SHIP`, or stopped differing from stock — **stays in the staging tree and ships**.
Nothing in the report mentions it, because the report describes the live install, not the folder.
The check that catches it is a set difference of staged-on-disk against the `--json` manifest;
run it every time, and re-run the staged-vs-live MD5 pass afterwards (§13.1).

`mod_manifest.py` owns four lists that separate mod content from workshop clutter, GOG install
furniture (`unins000.*`, `goggame-*`, `*.ico`, `EULA.txt`) and player data. **Extend the lists rather
than filtering by hand** — they are the record of what counts as mod content.

| list | applies to | for |
|---|---|---|
| `IGNORE_DIRS` | ADDED | whole trees that are never mod content; also prunes the walk |
| `IGNORE_GLOBS` | ADDED | leaf patterns — `*.pre-*`, `*.hsm`, `*.zip`, `*.ini` … |
| `ALWAYS_SHIP_DIRS` | ADDED | trees shipped **whole**, exempt from `IGNORE_GLOBS` |
| `NEVER_SHIP` | **CHANGED and ADDED** | a patched file deliberately held back |

⚠ **`IGNORE_GLOBS` never touches CHANGED**, deliberately — otherwise `TCMaps/eCrpt000.HSM` would
vanish from a release under `*.hsm` and nothing would say so. Withholding a *patched* file is what
`NEVER_SHIP` is for, and the report prints a WITHHELD section so the omission is visible.
`ALWAYS_SHIP_DIRS` exists for the mirror problem: `1Scenario/` holds nothing but `.hsm` and `.zip`,
so a glob-filtered walk ships none of it.

`compare_prev_upload.py` cross-checks a manifest against `Ziggurat upload/` (the March 2026 release)
and is the regression test for the filter.

### 13.1 The 2026-09-08 release

**962 files, 92.0 MB** — 52 replacing a stock 1.36 file, 910 new (620 of those are the `1Scenario/`
map collection). Packaged as `Ziggurat-2026-09-08.zip` (91.2 MB, 965 entries) from the staging tree
`Ziggurat release/`, plus `Ziggurat Manual.exe` + `.html` and a `README.txt`. Staging was verified
file-by-file against the live install: 962/962 MD5 match.

⚠ **A staged tree goes stale the moment any script applies.** `AoW.exe`/`AoWCompat.exe` were rebuilt
after the first packaging run and the zip silently carried the old pair. Re-run `--stage` (it
overwrites) and re-hash staged-vs-live before every upload; the exe pair's own check is that they
differ at **exactly one** offset, `0x3BB7C` (`0x0F` in `AoWz.exe`, `0x05` in `AoWzCompat.exe`) — a
bugfix applied to only one of them shows up here and nowhere else. ⚠ That check is meaningless
against the *vanilla* pair, which is byte-identical; see §11.2.

The eight patched binaries shipped: `AoW.exe`, `AoWCompat.exe`, `AoWEPACK.dpl`, `AoWTCPCK.dpl`,
`aowInt.dpl`, `vcl30.dpl` (mouse wheel, `build_wheel_vclpump.py`), `HSEPack.dpl`, `Ilpack.dpl`.
Plus `AoWDevEd.exe`, which is **not in any GOG install** — shipping it hands players a binary they
never owned. Owner ruling 2026-09-07: include it.

⚠⚠ **`AoWEd.exe` NO LONGER EXISTS AS A PATCH TARGET, and its patches are gone** (measured
2026-09-10). It was never shipped (owner ruling 2026-09-07 — `AoWDevEd.exe` supersedes it), and the
2026-09-09 move left **no `Ziggurat/AoWEd.exe` at all**; the only copy is `<root>/AoWEd.exe`, which is
**stock** — md5 `f45bebf5…`, MATCH against the GOG hashdb. So its four editor-side patches —
`build_editor_autosave.py`, `build_editor_framerate.py`, `build_editor_spinners.py`,
`build_deved_levelnav.py` — are no longer installed anywhere, and any script still naming
`AoWEd.exe` now aborts with `FileNotFoundError` (`build_editor_spinners.py` does exactly this; see
`01-combat-maths.md`). ⭐ It fails loudly and **cannot reach the vanilla file**, because `GAME` is
`Ziggurat/`. Open decision: either drop `AoWEd.exe` from those scripts' target lists, or retarget
them at `AoWzEd.exe`. A player's vanilla `AoWEd.exe` still loads the **patched** `AoWEPACK.dpl` and
`HSEPack.dpl` (both editors import both); the exe-side caves simply go uncalled.

`1Scenario/` ships whole, as-is: 620 files, 48 MB, more than half the package. Two known oddities
inside it, accepted rather than cleaned — `1Scenario/Campaign/` duplicates the vanilla
`Scenario/Campaign/` 43 `.csm` files, and `1Scenario/Laboratory/` carries working notes
(`Test 2.txt`, a file literally named `.txt`).

⚠ **`Ilpack.dpl` is patched by someone else, not by this project.** No `build_*.py` writes it and its
mtime is the install timestamp. It carries a third-party ShowScene patch (owner, 2026-09-07). Ship
it; do not "restore" it to the GOG hash, and do not expect a build script to explain it.

**`Images/Scenes/Intro.avi` is absent** from the working install — a local deletion, not a mod
change. A zip cannot propagate it; anything installer-shaped must not delete it either.

### 13.1a The installer releases — 2026-09-11 and 2026-09-13, and the order to cut one in

Published as GitHub releases on `BING-XI/Ziggurat-Engine-Mod`, tagged `v<AppVer>`, one asset each.
The manual is **not** in the payload — it is the Pages site (§14.6), which doubles as the changelog.

| | files | payload | installer |
|---|---|---|---|
| 2026-09-11 | 347 | 48.8 MB | 18,229,233 B |
| 2026-09-13 | **345** | 48.4 MB | 18,133,962 B, sha256 `cfd22a18…` |

The 345 is 52 files replacing a stock 1.36 file and 293 new. It dropped from 969 when `1Scenario/`
(620 maps, shipped separately) and `Ziggurat Manual.exe`/`.html` left on 2026-09-11, and from 347
when **the manual's builder followed the manual out** on 2026-09-13: `build_ziggurat_manual.py`
(313 KB of authoring code) and `Ziggurat Manual.html.build.json` were still ADDED content, so every
player got a builder with nothing to build and a cache sidecar keyed to a page not in the payload.
Both are now in `NEVER_SHIP`.

⭐ **The trap that hid it:** `NEVER_SHIP` was doing its job on the manual, and a companion file that
merely *relates* to a withheld file is not caught by anything — it is ordinary ADDED content sitting
at the root of `Ziggurat/`. The `WITHHELD` section does not list it either, because that section
reports withheld **CHANGED** files only. Read the staged top-level listing with your own eyes once
per release; a wrong entry is obvious among the dozen root-level files and invisible everywhere else.

⚠⚠ **It has now happened three times**, and the third one appeared on its own with no source change:
`manual_text.json` is written the first time anyone uses the manual's "Edit text", so on 2026-09-18
the payload silently went 345 → **346** and would have shipped the author's prose overrides to every
player. Caught only by the file **count** moving. The lesson is not "add another name to the list" —
it is that **a payload whose count changed for a reason you cannot immediately name is a stop**, and
that anything the authoring tools *write* becomes payload the moment it exists.

| withheld | why | added |
|---|---|---|
| `Ziggurat Manual.exe` / `.html` | the manual is hosted on Pages | 2026-09-11 |
| `build_ziggurat_manual.py`, `Ziggurat Manual.html.build.json` | its builder and cache, with no manual to act on | 2026-09-13 |
| `manual_text.json` | the author's prose overrides, for a manual not in the payload | 2026-09-18 |

**The order, all of it:**

1. Kill every AoW binary (they lock the targets). Standing authorisation — §11.1.
2. Revert every diagnostic; confirm via the CHANGED/SAME counts moving (§13 preamble).
3. `build_relocfix.py --audit` — any feature that displaced bytes can have left a stale entry, and
   that is invisible to every other check (§5.2c).
4. Verify the exe pair differs at **exactly one** offset, `0x3BB7C` (`0x0F`/`0x05`) — §11.2. A fix
   applied to only one of them shows up here and nowhere else.
5. `mod_manifest.py --stage <path> --json <path>`, then **orphan check** (staged-on-disk minus the
   manifest) and **staged-vs-live MD5**, both to 0 / N-of-N. Re-stage after *any* later patch.
6. Rebuild the Pages manual: `--public --out "Modding Resources/site/index.html"`, copy to
   `gh-repo/`, push. ⚠ never a copy of the authoring page — §14.6. ⚠⚠ Before the **first** push from
   a new clone, check `git config user.name` / `user.email` resolve to
   `Ziggurat Mason <156740625+BING-XI@users.noreply.github.com>` — the repo is public, the owner is a
   handle there, and a force-push afterwards does **not** remove the exposed commit from GitHub.
   Commit messages are player-facing: gameplay changes only, or nothing. No bugfixes, no attribution
   trailers. Both rules and the reflog trap are in the repo-root `CLAUDE.md`.
7. Compile the installer (§13.3).
8. Pre-share hygiene **last**: delete `.pyc` and `Ziggurat Manual.log`, then the guarded `grep -laF`
   scans over the staged payload, the installer exe and `gh-repo/` — §13.4.
9. `gh release create v<AppVer> "<exe>" --title … --notes-file …`, then confirm the asset's byte
   count matches the local file.

⭐ **Two post-publish checks that are not optional.** The asset upload is reported as a URL whether
or not the bytes arrived — read back `state=uploaded` and the size. And **Pages deploys
asynchronously**: for ~90 s after the push the old page is still served, so a `curl` immediately
after `git push` reports the *previous* release's content and looks like a failed build. Wait for
`gh api repos/<owner>/<repo>/pages/builds --jq '.[0].status'` to read `built`, then compare
`git show HEAD:index.html | sha256sum` against the served bytes. On 2026-09-13 that intermediate
read showed 1239 `<select>` elements — the pre-`--public` page — which reads exactly like the
`--public` build having failed, and did not.

⚠ **`wc -c` on `gh-repo/index.html` (2,021,878) will not equal the bytes Pages serves (2,021,150).**
Git normalises the 728 CRLF line endings on commit. The blob hash is the only honest comparison.

### 13.2 The March 2026 release over-shipped by 56 %

434 of its 770 files were byte-identical to a stock GOG install — whole `Images/TCombat/` and
`Images/UNITS/` trees copied wholesale. Zero files in it differ from vanilla in a way the manifest
misses, so the hashdb method is a proven superset of hand-picking. Also stale in it:
`Release/Release - Copy.hss`, which no longer exists here.

### 13.3 An Inno Setup installer, not a zip — and the two things only it can do

Owner ruling 2026-09-11, superseding the 2026-09-07 "plain zip" decision. The source is
`Modding Resources/installer/Ziggurat.iss`, compiled with **Inno Setup 7**:

```bash
cd "Ziggurat/Modding Resources/installer"
"/c/Program Files/Inno Setup 7/ISCC.exe" "//DAppVer=2026.09.13" Ziggurat.iss
```

⚠ **ISCC is under `C:\Program Files\`, NOT `Program Files (x86)`** — Inno 7's compiler is 64-bit even
though `ArchitecturesAllowed=x86compatible` targets a 32-bit game. ⚠ In bash the define needs a
**doubled** slash, `//DAppVer=…`: MSYS path-mangles a single leading `/` into `C:/...` and ISCC then
reads it as a filename. Output lands in `installer/out/Ziggurat Setup <AppVer>.exe`.

**Two steps cannot be done by extracting files, and they are the whole argument:**

1. The mod's data root is the player's **own** vanilla data. `PrepareToInstall` copies all 33
   packages plus eleven data directories out of the game folder into `Ziggurat\` first, and `[Files]`
   then overlays the 345-file payload on top. That is why the download is 18 MB and not 370 MB —
   Triumph's files are never redistributed, only copied locally from files the player already owns.
   ⚠ **Order is load-bearing**: Inno runs `PrepareToInstall` before `[Files]`. Reverse them and
   vanilla overwrites the mod.
2. `HKCU\Software\Triumph Studios\Age of Wonders Z\General\Startup Directory` must point at
   `{app}\Ziggurat\`. No archive can write that, and without it the mod loads vanilla's data.

### ⚠⚠ `createvalueifdoesntexist` made the install location unfixable — removed 2026-09-15

The two `[Registry]` lines carried `createvalueifdoesntexist`, so the installer wrote
`Startup Directory` / `Root Directory` **once and never again**. Re-running it against a different
folder left the first install's path in the registry and silently did nothing useful.

⭐⭐ **Reproduced 2026-09-16, and it is worse than "a moved install".** Once that key exists — i.e.
for **anyone who has ever installed Ziggurat before** — an old installer's registry write is a
**complete no-op, wherever you install**. Measured with two fake vanilla trees:

| step | installer | target | resulting `Startup Directory` |
|---|---|---|---|
| 1 | 2026.09.13 | `vanillaA` | **unchanged** — still the pre-existing path |
| 2 | 2026.09.13 | `vanillaB` | **unchanged** — still the pre-existing path |
| 3 | 2026.09.16 | `vanillaB` | `…\vanillaB\Ziggurat\` ✅ |

So a returning player's data root is frozen at wherever they *first* installed, and every
reinstall — same folder or not — silently fails to move it. That is exactly the report: installing
into a renamed copy of vanilla failed, installing over the **original** folder worked, because only
the original matched the frozen value. It presents as hundreds of `Error loading:` dialogs naming
files that are all present, just not *there*.

⚠ **It is not a dependency on the VANILLA key**, which is the natural reading of the symptom. The
only place `…\Age of Wonders\General\Root Directory` is read is `GuessGameDir`, and that merely
pre-fills the browse box. The frozen value is Ziggurat's own `…\Age of Wonders Z` key.

⭐ **The diagnostic tell is in the dialog itself: the path it names is not the folder the exe was
launched from.** Same-folder ⇒ missing files; different-folder ⇒ stale registry. I initially read
those dialogs as proof the registry was *correct* — the paths resolved, so I concluded the data root
was fine and he must have hand-copied without running the installer. Wrong: a resolving path proves
only that *some* root was found. **Compare it against the launch directory before concluding
anything.**

⚠ Do not reinstate the flag to "protect a user's setting". These two values *are* the install
location; there is one data root, so last-install-wins is correct.

⭐ **The answer for an affected player is "install 2026.09.16", full stop.** It writes the value
unconditionally, so it repairs any frozen prior state by itself, at whatever folder they point it
at. ⚠ **Never tell a player to delete the registry key by hand** — it was the first thing that came
to mind here and it is the wrong shape of answer: a registry edit is beyond most players, it is a
support burden, and the installer is already the thing whose job this is.

### ⚠⚠ The installer could not tell you it had failed — fixed 2026-09-15, with an A/B

`CopyTree` and `CopyPackages` discarded the Boolean from every `CopyFile`, and `CopyTree` discarded
`CreateDir`'s too. So a failure anywhere in the ~1,300 copied files was swallowed: the loop carried
on, `PrepareToInstall` returned `''`, Inno overlaid the payload and **reported a successful
install**. The player got a `Ziggurat\` missing an arbitrary subset of their own game data and
hundreds of `Error loading:` dialogs at launch, naming files the installer believed it had written.

⭐ **Reproduced on demand**, which is what turned this from a code-reading into a fact. Build a fake
vanilla tree (`AoW.exe` + `AoWEPACK.dpl` + `Release\Unitres.pfs` is all `LooksLikeAoW` wants), then
force exactly one copy to fail by pre-creating the destination **as a directory** — `FileExists` is
false for a directory, so the guard lets `CopyFile` through and it fails:

```bash
mkdir -p "$T/Ziggurat/Int/GenericT.ilb"     # a DIRECTORY where a file must land
"./Ziggurat Setup <ver>.exe" //VERYSILENT //SUPPRESSMSGBOXES "/DIR=$T" "/LOG=$L"
```

| | old (2026.09.15) | fixed |
|---|---|---|
| exit code | **0 — success** | **7 — aborted** |
| payload installed | yes | no |
| failure named in the log | **0 mentions** | the exact path |

The fix counts failures (`NoteFail`), keeps going so the total is real rather than fail-fast, and has
`PrepareToInstall` return a non-empty string — which aborts **before** `[Files]` and `[Registry]`,
verified: the payload was absent and the registry untouched after the abort.

⚠⚠ **`//VERYSILENT`, not `/VERYSILENT`.** MSYS rewrites a single leading slash into a path: the log
showed Inno receiving `"C:/Program Files/Git/VERYSILENT"`, so it got neither flag and sat on the
interactive wizard until killed. `/DIR=` and `/LOG=` survive because they contain `=`. Same trap as
the ISCC `//DAppVer=` define — it has now cost time twice.

⚠ Testing an installer **writes `HKCU\…\Age of Wonders Z\General`** now that
`createvalueifdoesntexist` is gone, repointing the live data root at the test folder. Read both
values first, restore them after, and launch `AoWz.exe` to confirm. The abort path is safe to test
(it returns before `[Registry]`); the success path is not.

### The data root is registry-bound, and it need not be — open

`TAoWRegistry` in `AoWEPACK.dpl` is the **single** choke point: `AoW.exe`, `AoWCompat.exe`,
`AoWEd.exe` and `AoWDevEd.exe` carry no copy of the key path at all (`build_regiso.py`, scanned, zero
hits), so every binary routes through it.

Traced 2026-09-15, vanilla image:

| | |
|---|---|
| `0x55705248` | `SetStartupDirectory` — `rw(Self, 'General', 'Startup Directory', 0, value)` |
| `0x55705298` | `GetStartupDirectory` — `rw(Self, 'General', 'Startup Directory', 1, @Result)` |
| `0x55703D08` | the shared rw helper; arg1 `0`=write / `1`=read, arg2 value/buffer |
| `0x557052F8` / `0x55705314` | the `"Startup Directory"` and `"General"` constants it loads into ECX/EDX |

⚠ `GetStartupDirectory` has **zero `call rel32` sites** — it is reached through the VMT, which is why
finding its callers needs Ghidra's xrefs rather than a byte scan.

**The proposal, not built:** an exe-relative data root removes the whole failure class.
`GetModuleFileNameA(NULL, …)` → strip to the last `\` gives `Ziggurat\` for `AoWz.exe`/`AoWzEd.exe`
and the game root for a vanilla `AoW.exe` — correct in every case, with no registry read. Precedent
exists in this tree: `build_aowsetup_installcheck.py` already installs Inioch's `'.'`-fallback-on-nil
in `AoWSetup.exe` (call-rel32 retarget `0x004675A0`, cave `0x00469820`, 31 B). ⚠ `Root Directory`
would need the same treatment, and settings other than the data root should stay in the registry.

`Uninstallable=no` is honest rather than lazy: deleting `Ziggurat\` **is** a complete uninstall —
vanilla's files are never modified and vanilla reads a different registry key — so the only thing an
uninstaller could do is delete a folder the user can delete. ⚠ For the same reason there are **no
Start Menu shortcuts**: they would dangle after the supported removal.

The cost that was weighed and accepted: the exe is unsigned, so SmartScreen warns on first run.
That is stated in the release body and in the repo README.

### 13.4 ⚠ The `.pyc` delete must be the **LAST** pre-share step, not an early one

`CLAUDE.md` calls `find "Modding Resources" -name '*.pyc' -delete` a mandatory pre-share step but
does not say when to run it. **Order matters: running any RE tool re-creates the leak.** Python
embeds the absolute source path in every `__pycache__` entry it writes, so a single
`dasm.py`/`pescan.py` invocation regenerates `re_tools/__pycache__/{aowsyms,pescan}.cpython-*.pyc`
carrying the profile path. Observed 2026-09-09: a QA pass that deleted the caches, then ran `dasm.py`
to check a cave, ended with both files back on disk.

So the sequence is: finish every verification run first, **then** delete the caches, **then** run the
two `grep -laF` / `grep -rlaF` scans (with `-a`, never `-I`), **then** zip. Anything that re-runs a
tool after the delete invalidates the scan. The same applies to `Modding Resources/Ziggurat
Manual.log` (rebuilding the manual re-creates it) and to `Zig Modding Tools/`, which the two scans in
`CLAUDE.md` do not cover at all — see `Map_Generator.md`.

⚠⚠ **Guard the pattern, or an empty `$USERNAME` reports the entire tree as leaking.**
`U="$USERNAME"; grep -rlaF "$U" .` with `U` unset becomes `grep -F ""`, which matches **every
file** — a 300-line "leak" list that is pure artefact. It bites when the assignment is skipped,
e.g. an earlier command in an `&&` chain fails and only the `grep` runs after a `;`. Cost real
time on 2026-09-09. Always guard:

```bash
U="$USERNAME"; [ -z "$U" ] && echo "ABORT: USERNAME empty" || grep -rlaF "$U" "Modding Resources/"
```

A true positive is a handful of named files. A hit list in the hundreds means the pattern is
empty, not that the tree is compromised — check `$U` before believing it.

---

## 13a. ⭐ A PE import name may carry a relative path — PROVEN ON THIS MACHINE 2026-09-09

**The Windows loader honours a path component in an `IMAGE_IMPORT_DESCRIPTOR`'s `Name` string**, and
resolves it against the **application** directory (the directory of the running `.exe`, *not* the
directory of the importing DLL). So an import named `Ziggurat\AoWEPACK.dpl` loads
`<exe dir>\Ziggurat\AoWEPACK.dpl`. This is what makes a modded overlay possible: a vanilla install at
top level, every modified package in a subfolder, and one patched exe that reaches into it.

**How it was proven** — a copy of `AoW.exe` with its seven `AOWTools.dpl` descriptors repointed at a
new string `Ziggurat\AOWTools.dpl`:

| step | `Ziggurat\AOWTools.dpl` | top-level `AOWTools.dpl` | result |
|---|---|---|---|
| A | absent | **present** | exits `0xC0000135` STATUS_DLL_NOT_FOUND |
| B | present | present | starts normally |

Step A is the load-bearing half: the bare name was available in the app directory and the loader
**did not fall back to it**, so the path component is genuinely honoured rather than stripped.

**Mechanics for anyone building on this:**

- ⚠ **Delphi emits one import descriptor per UNIT, not per package.** `AoW.exe` has **239**
  descriptors for ~20 distinct modules — `AoWEPACK.dpl` alone appears ~90 times, `aowInt.dpl` ~30,
  `VCL30.dpl` ~25, each with its own copy of the name string. Redirecting a module means rewriting the
  `Name` RVA of *every* descriptor whose string matches. They can all point at **one** new string.
- The new string can live anywhere readable. `AoW.exe`'s `.idata` tail slack is
  file `0x6BF7C`–`0x6C000` / RVA `0x6E37C`, **132 bytes, verified zero** — enough for ~6 names. Bump
  the section's `VirtualSize` to cover what you write.
- Because resolution is relative to the **application** directory, a redirected DLL's own imports use
  the same prefix: `Ziggurat\vcl30.dpl` inside `Ziggurat\AoWEPACK.dpl` still resolves to
  `<exe dir>\Ziggurat\vcl30.dpl`. The prefix does **not** compound.
- Unredirected modules keep resolving from the app directory, so a vanilla install's copies are shared
  and nothing is duplicated.

**⭐ The loader also dedupes by BASE NAME, which is what made a partial redirect survivable.** With
only the 6 modified packages redirected, the 15 shared ones still imported `vcl30.dpl` by *bare* name
— two VCL runtimes in one process, which Delphi's package system does not survive. It never happened:
enumerating the live process showed exactly **one** `VCL30.dpl` mapped, Ziggurat's. A later bare-name
request matches the already-loaded module by base name. ⚠ That relies on ordering — it holds because
the exe's own descriptors resolve first, so the redirected copy is always loaded before any shared
package asks for it.

### ⚠ Not in use here any more — and why, because the reason generalises

`build_overlay.py` used all of the above to run `AoWz.exe` from the **vanilla root** while its six
modified packages sat in `Ziggurat\`. It was **retired 2026-09-09** and deleted; nothing in the tree
uses relative import names today.

The mechanism became unnecessary the moment `Ziggurat\` acquired a **complete** package set. That
happened for an unrelated reason — `AoWzEd.exe` runs from `Ziggurat\` and needed all 33 packages
resolvable there — and once every package was present, the exe could simply live in `Ziggurat\` too
and resolve everything from its own directory with no patching at all. Verified: 20 packages, all
from `Ziggurat\`, none from the root.

**The lesson worth carrying:** an exe placed *inside* the folder holding its packages needs no import
surgery whatsoever. Reach for the relative-path trick only when the exe genuinely cannot live beside
its own dependencies — the whole 175-descriptor rewrite existed to work around a layout choice, not a
technical constraint.

## 14. The Ziggurat Manual — its two standing failure modes

`build_ziggurat_manual.py` renders `Ziggurat Manual.html`. Every tab it fills from **live** sources
(Units, Abilities, Unit Enchantments, Movement, Heroes, portraits) is current by construction. The
two ways it goes wrong are both silent, and a review on **2026-09-09** found instances of each.

### 14.1 ⚠ A missing input file drops content with no warning

`spell_names.json` moved into `Zig notes/` on 2026-09-09. `merge_spell_icons()` still looked for it
beside the script, found nothing, and `return 0`-ed — so **every one of the 108 spell icons vanished
from the page**, and the only trace was the `spell icons 0 of 108 spells` line in `--check`, which
reads like a count rather than a failure. Both the working build and the shipped
`Ziggurat release/Ziggurat Manual.html` had zero `class="sico"` images. Fixed: both paths are tried
and absence now calls `warn()`.

**The general rule: an optional input that silently degrades output is worse than one that aborts.**
Any `if not os.path.exists(p): return` in that script wants a `warn()` beside it.

### 14.2 ⭐⚠ The hand-written blocks drift; the live-read tabs do not

The module-level constants (`MAJOR`, `NEWMECH_*`, `HIGHLIGHTS`, `LATEST`, `SPELL_BEHAVIOUR`,
`DEBUFF_NOTES`, `EDITOR_ITEMS`, `BUGFIX_GAME`, `NEW_ABILITIES`) are the manual's only coverage of
anything the workbook cannot supply — and **the workbook is a frozen historical snapshot, so that
is nearly everything built since 2026-08.** On 2026-09-09 they were three weeks behind: no
Firmament, no Embrittle, no Panic rules, no Terror cap, `LATEST` still naming two pre-rescale items,
and `NEWMECH_SCALE` still printing the 120 HP ceiling that moved to 100 on 2026-08-31.

**So: a feature's own record is not complete until its manual block exists.** Several feature
sections already carry a `| manual | build_ziggurat_manual.py | <constant name> |` row
(`04-spells-modded.md` §Astral Ward and §Power Leech are the pattern) — copy it.

### 14.3 ⚠⚠ The workbook contradicts the live binary, and `MISC_OVERRIDES` is the only defence

`MISC_OVERRIDES` in that script corrects individual workbook rows against live byte reads. It is not
optional polish: without an entry, the sheet's pre-rescale number renders as fact. Corrected
2026-09-09 (all byte-read via `re_tools/enchant_mods.py`, vanilla column from
`AoWEPACK_original_backup.dpl`):

| row | sheet said | live |
|---|---|---|
| Leadership Boost | Zig `ATK +2, DEF +1` / van `ATK +1` | van **+1/+1** one level; Zig **+1/+1 → +4/+4** over four |
| Max unit HP / Max hero HP | 120 | **100** (since 2026-08-31) |
| Stunned / Entangled / Webbed | *no Ziggurat value at all* — rendered `?` | DEF **-4** (van -2) |
| Frozen | `DEF +2` | DEF **+3** — and vanilla is **-2**, so the sign flipped |
| Poisoned | `-2 ATK -2 DAM` | **-3 ATK -3 DAM** (van -1 on all four stats) |
| Vertigo | rendered *unchanged* | **-3/-3** (van -2/-2) |
| Cursed | rendered *unchanged* | **-4 DEF -4 RES** (van -2/-2) |
| Bloodlust | `DAM +2` | **+3 ATK +3 DAM -2 DEF** |
| Nature's Blessing | `DEF +1, RES +2` | **+1 DEF +3 RES** — the Attack is gone |

⚠ **Two tabs printing different numbers for one effect is the symptom to look for.** The Debuffs tab
is workbook-driven and the Unit Enchantments tab is live-read; before this they disagreed on six
effects. When they disagree, the live one is right and the sheet needs a `MISC_OVERRIDES` entry.

⚠ **Durations are not readable by `enchant_mods.py`** and are kept verbatim from the sheet. Do not
put a duration into `MISC_OVERRIDES` without a live source for it.

### 14.4 ⭐ The Hero Offers tab — an editor that answers "did my edit land?" on its face

Added 2026-09-09. The Hero Offers tab (Project group) edits the race × ability offer table behind
the hero level-up dialog: 102 offered abilities × 12 races, one `<select>` per cell on a four-rung
ladder (**0 / 10 / 25 / 60 %** since the second retune of 2026-09-10, colour-ramped), hover plus `Q W E R` to set them,
a live expected-offer count per race, and a **Save** that writes `build_scripts/heroskill_races.json`
straight to disk through pywebview's `js_api` — no dialog, server-side validation, temp file plus
`os.replace`. Detail in `07-ui.md` §2.8.

⭐ **A page that can write to disk needs its validation server-side, and its confirmation must be
a fact about the file.** The api returns the saved file's own fingerprint and the page's `built`
readout moves onto that, so `built == now` says something about disk rather than about the DOM.
Handing back "saved OK" would have been the same class of claim as a cache that trusts an mtime.

It is the answer to the failure that cost a session on **2026-08-14** — export, copy the file in,
reopen, and the page showed the PREVIOUS data, which reads exactly like the edit having failed.
Three things fix it, and each is worth copying into any future editor here:

- **The DOM is the model.** No parallel JS copy of the table exists, so nothing can drift from what
  is on screen. Export serialises the same cells the page renders.
- **Two figures, shown as data**: an 8-hex SHA-256 over the table's canonical form, and the count
  of cells at each ladder rung. `built` is what the build read off disk; `now` is what the grid
  holds. Equal means current; different is coloured and needs no interpretation. The Python and
  JavaScript emitters produce **byte-identical** text (verified on an edited table), so a re-export
  of an unedited file diffs clean against it.
- ⚠⚠ **Chromium restores `<select>` values across a reload** — which recreates the 2026-08-14 bug
  exactly. Every cell carries the build's own value in `data-v` and a startup pass forces the
  selects back to it; `autocomplete="off"` alone is not enough to rely on.

⚠ A JSON value off the four-step ladder keeps its own extra `<option>` rather than being rounded to
whichever value happens to be first in the list, and the build `warn()`s the count.

⭐ **Data-driven presentation: key the CSS on the RUNG, not the value.** Each cell also carries
`data-t`, its index in `LADDER`, and the tier colour ramp selects on that. The owner moved the
ladder twice on 2026-09-10 — `0/15/40/100` → `0/10/30/100` → `0/10/25/60` — and both times the
`<option>` list, the `Q W E R` bindings, the calibration rows, the ladder counts and the colours all
followed with **no code change**, because every one of them was already indexed rather than
hard-coded. The only literals that had to move were the constant itself and prose. Copy the habit.

⚠ **Prose is what actually costs on a rung move.** Both moves needed a documentation sweep across
four notes files while the code needed a one-line constant edit and a data migration. Budget for
that, and grep the fingerprint (`2a098b10` at the time; the owner's table is **`818757b6`** today,
`430/357/248/201`) as well as the rung values — the ladder appears
written as `0/10/25/60` and as `0 / 10 / 25 / 60`, and a single-spacing grep misses half of it.

⚠⚠ **A number the grid does not have a column for is a number nothing checks.** The calibration
table's out-of-band flag covers the 12 grid races; the derived Raceless figure rides the toolbar and
had no flag until 2026-09-10, when the rung change pushed it to 17.8 and it sat there unmarked.
Same shape as the 2026-09-09 bug where `report()` skipped row 15. Whenever a readout lives outside
the table that validates the others, band-check it separately — at build time *and* in the live
recompute.

### 14.4a The Manual's build cache (2026-09-10)

`build_ziggurat_manual.py` no longer rebuilds when nothing it reads has changed: **8.3 s cold,
0.43 s warm**. ⚠⚠ That deliberately re-opens the 2026-08-14 hazard this whole section is about, so
the cache is written to be airtight, not fast — content hashes (never mtimes), **any doubt
rebuilds**, digests taken before *and* after the build to close the mid-build race, warnings
carried in the sidecar so a skipped run still prints them, and the page stamping its own input key
in `<meta name="zm-build">`. Rules, inputs and the tested failure paths: `07-ui.md` §2.9.

⚠ The sidecar `Ziggurat Manual.html.build.json` stores **root-relative tags** (`game/…`, `shop/…`),
never absolute paths. Two reasons, either one sufficient: an absolute path carries the author's
profile directory into a file that sits in the shipped tree, and the frozen exe's `_MEIPASS`
extraction directory is different on every single launch, so an absolute key would miss every time.

### 14.5 Scrolls are still dataless — do not document them

`build_scroll_spellbook.py` is applied, but `User/Zig.ail` (the live item library, **not**
`Release/ITEMS.PFS`) holds **0** items of type 5 across its 325 records — types present are
0/1/2/3/4/6 only (counted 2026-09-09 off tag `0x0F`). No player can obtain a scroll, so the feature
has no manual coverage and should get none until scroll items exist.

### 14.6 ⚠⚠ Publishing the Manual — `--public`, never a copy of the authoring page

The GitHub Pages site is `https://bing-xi.github.io/Ziggurat-Engine-Mod/`, served from `main` of
`BING-XI/Ziggurat-Engine-Mod`. The working clone is `Modding Resources/gh-repo/` (`index.html` +
`README.md`); `Modding Resources/site/` is the build target that feeds it.

```bash
python build_ziggurat_manual.py --public --out "Modding Resources/site/index.html"
cp "Modding Resources/site/index.html" "Modding Resources/gh-repo/index.html"
```

⚠ **`Ziggurat Manual.html` is an AUTHORING build and must never be uploaded as-is.** It was, on
2026-09-11 — a byte copy, hash `9832a694`, to both `site/` and `gh-repo/` — which put **three**
editors on a public page:

| surface | what shipped |
|---|---|
| `.mtxbar` + 210 `[data-mtx]` spans + `#mtxdef` | "Edit text" made every prose block `contentEditable`; 33 KB of shipped-text defaults rode along |
| `#abdata` + `EDITOR_JS` | the in-browser ability editor — **the whole of `Unitres.pfs`, 211 KB of base64** — and an "Edit abilities" toolbar |
| `.hsbar` + `#hsdata` + `HEROSKILL_JS` | the Hero Offers grid as **1237 `<select>` dropdowns**, plus an Export/Save button and the source filename |

Nothing could persist — Pages is static, and both save paths need pywebview or a local file — but
the changelog read as a wiki anyone could rewrite, and a doctored screenshot was one click away.

**`--public` (2026-09-13)** sets the module global `PUBLIC`, which: has `mtx()` return its prose
bare; empties `mtx_chrome`, `ab_embed` and the Hero Offers `bar`; drops `MTX_JS`, `EDITOR_JS` and
`HEROSKILL_JS` from the template; and renders each offer cell as `<span class="hss" data-t=N>`.
Result: no `<input>`, `<textarea>`, `<select>` or `<form>`, one `<button>` (the Ziggurat/vanilla
comparison toggle), 2,574,676 → 2,021,878 bytes.

⭐ **The tier ramp was re-keyed from `select.hss[data-t]` to `.hss[data-t]`** so a span and a select
look identical. `cursor:pointer`, the hover border and `.hit` stay qualified to `select.hss`, so a
static cell never advertises a click it cannot take. Anything new that styles an editable cell
belongs on `select.hss`, not `.hss`.

⚠ **`PUBLIC` is in the build-cache key** (`CACHE_VERSION` 2). The sidecar sits beside `--out`, so
the normal case never collides, but `--public` and a plain build aimed at the *same* `--out` would
otherwise agree on the key and the second would report "up to date" over a page built in the other
mode.

**The net under it: `window.zmCanAuthor()`** (`AUTHOR_GATE_JS`, emitted first in an authoring build
only). All three editors call it and remove themselves when it is false; the heroskill one also
swaps its 1237 selects for spans, the same page reached at runtime instead of at build time.
Verified over http: a full authoring build serves with zero form controls and no console errors.

⚠ **Test `location.protocol === 'file:'` first and never `window.pywebview` alone** — pywebview
injects its api **asynchronously** and may not have done so when the gate runs. `open_native_window()`
passes a `file:///` url, so the protocol is the reliable half and the api check is the spare.

⚠ This is not a security boundary and cannot be: devtools can edit any page. It governs what the
manual *offers*.

---

## Open items

- **The Ghidra pointer-chain typing is incomplete.** `TUnit.resource` is still typed `undefined4`
  in the project, so decompiles show `param_1->dwResource + 0x2a` instead of
  `param_1->resource->base_defense`. The struct was created before the pointer types were added, and
  `create_struct` refuses to overwrite an existing type; the `recreate_struct` fallback did not take.
  **The check that would settle it:** delete the affected structs and re-run
  `re_tools/ghidra_fields.py --apply`, or apply `modify_struct_field_type` per field instead of
  recreating the struct wholesale.
- **The enum layer (layer 3 of the annotation stack) is still pending.** Ability ids, spell ids,
  terrain/overlay ids, the player-type enum (independent = 4), raze result codes (`{3,4,6}`), item
  types, medal ranks and message ids are all known individually across various docs and scripts but
  have never been consolidated into actual Ghidra enums the way structs were in layer 2. **The check:**
  none yet exists to run — this is authoring work, not verification work.
- **C12 (a field on `TMapField`'s VMT, `+0x84`) is not measurable with the current toolchain.**
  `TMapField` is not present in `AoWEPACK.dpl` — it lives in `HSEngine`, which Ghidra does not have
  loaded (AoWEPACK only *imports* it, e.g. `HSEngine.TMapField.FindOwnedHS`). Only `TAoWMapField` is
  local. Three candidate meanings (move-entry handler / `FindChildIndex` / `UnitResourceIndex`) are
  unresolved, and are probably three different classes' fields conflated by a doc, not one field.
  **The check:** import or capstone-analyse the owning module (`HSEngine.dpl`) directly; Ghidra alone
  cannot answer this.
- **C16 (`map+0x120`, a tunneling-during-combat gate) is reconciled by inference only, not measured.**
  `TAbstractUnit.GetMoveTypes` turns out to be a bare forward to `GetAbMoveTypesAll` with no map check
  at all, so wherever the "no tunneling during combat" behaviour actually lives, it isn't there. The
  likely reading — a field meaning "a combat is in progress", with the tunneling restriction as one
  consequence of it — is consistent with the sources that disagree about it, but nobody has located
  the actual gating code. **The check:** trace forward from a known tunneling unit's move-cost
  computation during an active combat and find where (if anywhere) it diverges from the same unit's
  move cost outside combat.
- **Whether `build_ai_itempickup.py`'s cave (`0x55810000`) and the reverted
  `build_ai_itemtarget.py`'s old span (`0x55810200`) are still live is not established from source
  alone.** `build_ai_itemloot.py`'s own docstring says it supersedes both, but "supersedes" doesn't by
  itself confirm the older script's `--undo` was ever run. **The check:** byte-read
  `0x55810000..0x558102AD` against each script's known cave contents before reusing or reasoning about
  that range.
- **Whether `build_combatlog_dll.py`'s legacy cave (`0x5580E440..0x5580ED80`) has actually been
  vacated is likewise unconfirmed.** The relocation script supports an optional `--vacate` flag to
  zero the abandoned bytes; nothing in the source establishes whether it was ever run.
  **The check:** byte-read the range and compare against the "old home" bytes the script's own
  `--vacate` logic expects to find (or zero).
- **The free-CODE-space high-water mark needs periodic re-derivation, not permanent trust in this
  doc.** §6.1's table reflects the constants declared in `build_scripts/` as read for this merge;
  every new feature moves the true high-water mark. **The check:**
  `grep -rn "CAVE.*= 0x" build_scripts/ | sort -t= -k2` (or the Python approach in this file's own
  construction) re-derives it in a few minutes.

## Failed approaches — do not retry

- **Retyping `ITEMGFX` records from type 6 to type 5 to give scroll items an icon**
  (`build_scroll_gfx.py`) — CONFIRMED HARMFUL in-game, 2026-08-01: blank hero portrait, missing spell
  icons, spell costs rendered as nonsense (1, 5, 0), no error dialog anywhere. Isolated by a clean
  single-variable A/B (reverting this one file, cave untouched, made every symptom vanish), but root
  cause was never pinned down — something in the image-loading path keys off that byte beyond the
  documented "which item type may use this graphic" filter. Do not retry as written. Two untested
  better routes are recorded in the script itself: set the item's own graphic index directly
  (`item+0x40`, pfs tag 7) instead of relying on the type-keyed default, or *append* new type-5
  records rather than retyping existing shared ones.
- **Importing the live, patched `AoWEPACK.dpl` into Ghidra instead of keeping the project vanilla** —
  considered and deliberately rejected 2026-08-03, not simply never tried. Caves are
  position-independent via a `call $+5; pop; sub` idiom that Ghidra's stack analysis cannot follow,
  and `E9` hooks truncate the host function at the tail jump; both effects make patched code decompile
  *worse* live than vanilla. Read patched regions with `re_tools/dasm.py` instead — see §2.
- **Treating a cave's declared `CAVE_MAX`/`CAVE_LIMIT` reservation as its true footprint when
  looking for free space nearby** — not a single dated incident so much as a recurring near-miss
  pattern worth naming: §5.5 and §6.3 both cover why this specific reasoning step keeps almost causing
  collisions (`build_reformingflesh.py`'s original design spec is the cleanest example, caught before
  it shipped). Always check the *declared reservation*, not just how many bytes are currently
  non-zero.
