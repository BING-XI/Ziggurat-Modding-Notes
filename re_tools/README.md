# AoW1 reverse-engineering toolkit

Small Python helpers used to reverse-engineer **AoWz.exe / AoWTCPCK.dpl / aowInt.dpl** — the
Delphi 3 modules that are *not* loaded in the Ghidra project (Ghidra has AoWEPACK.dpl only).
Requires `capstone` and `keystone-engine` (`pip install capstone keystone-engine`).

All addresses are preferred-base VAs. EXEs load at 0x400000; the .dpl
packages load at high bases (AoWEPACK preferred 0x55700000) but are relocated at runtime — for
file patches keep caves position-independent (rel32/register only) or reuse a slot that already
has a `.reloc` entry. See the parent-folder docs for the actual findings.

⚠⚠ **Never write an exe name as a literal here.** `AoW.exe` / `AoWCompat.exe` at the game root are
**vanilla**; the mod is `AoWz.exe` / `AoWzCompat.exe`, editor `AoWzEd.exe`. A tool that scans for a
process named `AoW.exe` reports "not running" against the mod — and, if vanilla happens to be
running, attaches to *it* and reports vanilla state with no error. Names come from
`build_scripts/zigexe.py`, reached here as `from zignames import zigexe` (`zigexe.GAME_EXE`,
`zigexe.EXES` = the mod game pair, `zigexe.ALL_EXES` = every mod binary, `zigexe.LIVE_EDITOR`).
Rationale and the one deliberate exception: `../Zig notes/12-re-toolchain.md` §11.3.

## Files

- **zignames.py** — `from zignames import zigexe`. Puts `build_scripts/` on `sys.path` and
  re-exports `zigexe`, the single source of truth for binary names. Every tool here that opens or
  scans for a game binary goes through it; nothing writes an exe name as a literal.
- **pescan.py** — foundational PE parser (`PE(path)`): section table + `rva2off`, import table
  (`imports()`), export table (`exports()`), string/short-string readers, dword reader.
  Everything else imports this. Also has CLI subcommands: `vmt`, `classes`, `imports`,
  `subclasses`, `iatrefs`, `dlls` (see the bottom of the file).
- **dfm_parse.py** — parses a compiled Delphi form (DFM) from the .rsrc. Forms are found by the
  `TPF0` signature; this walks the object tree and prints each control's class/name/geometry.
  Usage: `python dfm_parse.py <file-offset-of-TPF0-block-in-hex>`. Enumerate the blocks first with
  a `TPF0` byte search (see `Unit_Card_CastingPoints_Display_2026-07-06.md` §5).
- **ftall.py** — dumps a class's *published field table* (offset -> control-field name), i.e. maps
  a form field like `+0x70` to its control (`Mana`). Field table is at `[VMT-0x2C]` =
  `{Count:word}{ClassTable:dword}` then `{Offset:DWORD}{Idx:word}{Name:shortstr}`. Usage:
  `python ftall.py <VMT-VA-in-hex>`.
- **vmt_find.py** — given a *method address*, finds which class VMT contains it (scans for VMT
  self-pointers at `[VMT-0x40]`, class name at `[VMT-0x20]`) and prints the class + its field map.
  Handy for "which form does this paint function belong to?". Edit the target list at the bottom.
- **dump_exe.py** — annotated linear disassembler for `zigexe.GAME_EXE`: labels vtable calls
  (casting/stat getters, GetAbilityEnabled), IsClass calls, import thunks, and IAT/classref data
  refs. Edit the `dump(va, len)` calls at the bottom. A good template for reading any game-exe
  routine.

## Typical workflow used for the card work

1. `dfm_parse` to find the form + control positions.
2. `TPF0` search + the field table (`ftall`/`vmt_find`) to map field offset ⟷ control name.
3. `dump_exe` to read the paint function and find where a control is set (SetGText @0x403254).
4. Hook that call site with a cave (see the `build_spellcast_card_v2.py` pattern in the parent
   folder — new PE section + keystone-assembled cave, verify-before-write, backup).

These are working session scripts (some have hard-coded target addresses at the bottom) — treat
them as templates, not polished tools.

## Added 2026-07-07 (editor lag / copy-paste investigation)

General-purpose (work on ANY module, not just the game exe):

- **aowsyms.py** — `get_symbols(modname)` -> (pe, base, {va: name}, iat). Names come from
  exports (dpl) plus a VMT scan + *published method tables* (exe). Empirical VMT layout:
  self-ptr −0x40, method table −0x28, field table −0x2C, name −0x20, instsize −0x1C, parent −0x18.
- **dasm.py** `<module> <va-hex> [len]` or `<module> sym <substring>` — annotated capstone
  disassembly; resolves cross-DLL import thunks (`call ... ; VCL30.dpl!...`), IAT slots,
  short-strings. Length defaults to next-export distance.
- **rng_audit.py** `[module ...] [--owners|--functions|--all-sites|--hash]` — every RNG draw in every
  binary, classified `ok` (synced `TAoWHSMap.Random`) / `RAW` (`System.@RandInt`, per-process
  seed) / `seed`, diffed against the stock copies at the game root (each md5-checked against the GOG
  hashdb) so modded sites stand out. A missing target or reference exits 2. `--owners`
  attributes a site to its build script; `--functions` prints which vanilla functions use which
  generator — that is the answer to "which one should my cave use". Catches call/jmp rel32,
  indirect calls **and bare address constants**, across every EXECUTE section (not just
  `CODE`/`.text`), because a cave can reach the RNG by the rebase-delta idiom and can live in a
  custom section. Register any new project-installed RNG wrapper in its `WRAPPERS` dict or caves
  routed through it become invisible. ⚠⚠ `--hash` is a **separate** scan for **P4 DERIVED HASH**
  sites (`build_scripts/rngstd.py`): those derive an answer instead of drawing one, so they
  reference neither generator and every other mode of this tool is blind to them by construction.
  Rule: `../Zig notes/12-re-toolchain.md` §4, taxonomy and selection test in §4.10.
- **xref.py** `<module> <va> [...]` — rel32 call/jmp + absolute-dword refs, labeled by enclosing
  symbol.
- **mtab.py** `<module> <vmt-va>` — published method table (DFM event handler name -> code VA).
- **sampler.py** `[--exe AoWzEd.exe --seconds 20 --hz 200 --out prof.txt]` — sampling profiler
  for the running 32-bit game/editor from 64-bit Python (SuspendThread + Wow64GetThreadContext),
  histogram symbolized via aowsyms. Read-only; safe on a live process. ⚠ `--exe` names a RUNNING
  process, so it defaults to the LIVE editor `AoWzEd.exe`, not the patch source `AoWDevEd.exe`.
  Same for **stack_prof.py**, which adds a poor-man's stack walk on top.

UI automation used to drive the editor for live measurements (winspy.py window/child tree,
clicker.py PostMessage clicks/tab-cycling/keys, menucmd.py menu-tree + WM_COMMAND, grabwin.py
PrintWindow capture of occluded windows, topmost.py z-order without focus steal).
See `../Editor_Lag_CopyPaste_Investigation_2026-07-07.md` for the findings these produced.

## Added 2026-07-21 (game *data*, not code)

- **pfs.py** — parser for `<game>/Release/*.pfs`, the unit / item / spell / hero / ability tables
  (the DPLs hold the code; the content lives here). Decodes the shared directory format and the
  **ability bitsets** — bit index *is* the ability id — so you can ask "which units have ability X".
  Units carry three ability owners: base chassis `0x19`, silver `0x1E`, gold `0x1F` (medals are
  deltas). Full format notes + the `AoWEPACK.dpl` ReadWrite addresses it was derived from are in the
  module docstring.
  `python pfs.py has Unitres.pfs 0x36` · `names <file>` · `tags <file> <id>` · `counts <id> ...`
  ⚠ The installed `.pfs` data is the **Ziggurat** mod, not vanilla — no vanilla copy is on disk.

- **ilb.py** — ILB image-library directory parser (`parse(bytes) -> {hdr, images}`); handles the
  v3.0/v4.0 headers and every image type's directory record. CLI: `ilb.py <file.ilb> [--all]` or
  `--idx N`. Works on external `Images/*.ILB` **and** on the mini-ILBs embedded in `Release.hss`.
  Format reference: `ILB desc.pdf` inside `IlbMaker_Release_1.0.2.7.7z` in the game folder.
- **ilb_rle16.py** — codec for image type 17/18 (`RLESprite16`), the format of the hexagon tiles:
  `decode` / `encode` / `reskin` (rewrites only literal pixels, so the payload length cannot
  change — the safe way to re-skin a shipped tile in place). Two traps, both of which cost engine
  crashes before they were understood: **row records are 4-byte aligned** (next record starts at
  `align4(start+reclen)`, so odd-width rows carry padding — proof in ILPACK `55210AC7`), and the
  row width/height come from **`clipwide`/`cliphigh`, not `wide`/`high`**. With both handled every
  hexagon tile in the shipped set round-trips byte-identically.
- **hss_crc.py** — `.hss` resource sets end with a **CRC-32 over everything before them**
  (`THSEngine.LoadHSS`, HSEPack `5560F75C`; the CRC is the LAST dword, `zlib.crc32`-compatible).
  On mismatch the engine raises an *unhandled* `Invalid HSSET`, so the game and the editor just
  vanish at startup with no dialog. Patch the file, then `hss_crc.py <file> --fix` (or
  `hss_crc.fix(bytes)`). **Any script that writes a `.hss` must call this.**
- **revert_audit.py** `[--all]` — safety check before ANY revert. Prints the true layer order for every
  patched binary (derived from `.pre-*` backup mtimes, which `copy2` preserves), then scans the docs and
  build scripts for revert instructions and flags the stale ones. A `.pre-<feature>` backup restores the
  WHOLE file, so it is only safe for the **newest** layer; "revert X then re-apply" procedures rot
  silently as soon as anyone patches that file again. `AoWEPACK.dpl` is **40 layers** deep as of 2026-07-27 (newest `.pre-spellguard`) — derive it with `ls -t AoWEPACK.dpl.pre-* | nl`, never trust a written count.

  ⚠ **xref.py caveat (cost a session 2026-07-21):** it finds only DIRECTLY-embedded operands. This exe
  reaches many BSS gvars through DATA pointer-table slots (e.g. `[0x45A4F0] = 0x45B1B0` → the
  TFastCombatWindow instance gvar), so "no xrefs" does NOT mean a gvar is dead — dump the DATA tables
  around `0x45A4D0..` before declaring an address unused.

## Added 2026-07-28 (editor frame-cost analysis)

- **sampler.py** gained `--tid N` / `--window <hwnd-hex>`: sample ONE thread. Without it the
  histogram is swamped by idle worker threads sitting in `NtWaitForSingleObject` and the UI
  thread's own time is invisible. (It also grew a `__main__` guard so it can be imported.)
- **stack_prof.py** `--window <hwnd-hex> [--seconds] [--hz] [--depth] [--slots]` — sampling
  profiler **with a poor-man's stack walk**. `sampler.py` records EIP only, which is useless when
  the hot address is a kernel stub: you learn the thread sits in `ZwDelayExecution` but not who
  called it. This one also reads a window of the stack at ESP and reports the first return
  addresses that land inside a known AoW module, so waits get attributed to the responsible AoW
  function. It is what identified the editor's two `Sleep(1)` calls as 76% of the UI thread —
  see `../Editor_Frame_Cost_Analysis.md`.

  ⚠ Timer resolution is **per-process** on Win10 2004+: `NtQueryTimerResolution` reports the
  system value and tells you nothing about the target, and calling `timeBeginPeriod` in your own
  process does not affect theirs. Test by injecting (`CreateRemoteThread` on
  `winmm!timeBeginPeriod`).
  ⚠ `grabwin.py`'s `PrintWindow` repaints the window synchronously into your DC — it cannot show
  what is actually on screen, nor when it got there. Do not use it to time painting.

## Added 2026-07-30 (item / ability investigation)

- **abquery.py** `<module> [--slot 0x88] [--id 0x20]` — finds every **hardcoded ability-ID query**
  and groups it by *which VMT slot* it calls. AoW1 has **two parallel ability-query APIs** on
  `THero` and only one searches items: `+0x4c/+0x84/+0x88` (`GetAbSet`/`GetAbLevel`/`GetAbEnabled`)
  are **self-only** (inherited from `TAbilityOwner`, never overridden), while
  `+0x14c/+0x144/+0x148/+0x158` resolve self → equipped items → `itUse` inventory. A consumer on the
  self-only side cannot see an item-granted ability *at all* — which is why Marksmanship on an item
  does nothing (its only 4 query sites, in `GetAttackRA`/`GetDamageRA`, are all self-only). Run this
  **before hooking any ability consumer**. See `../Investigation_Items.md` §0.6.

  ⚠ Slot numbers are **per-hierarchy**: `+0x148` is `GetAbilityEnabled` on a unit but
  `TCombatObject.DoDamage` on a `TCombatUnit`. Read the owning-function column and judge.
  ⚠ A Ghidra `PTR_<Class>_<addr>` is the **vmtSelfPtr** slot — the real VMT base is `+0x40` from it.
  Getting that wrong shifts every slot number by 0x40 and makes the whole map look wrong.
  ⚠ Like `fieldrefs.py`, it resyncs the linear sweep: bare `capstone.disasm()` over a CODE section
  stops at the first undecodable byte and silently reports near-zero hits.

## Added 2026-09-03 (crash capture)

- **veh_capture.py** — registers, stack and fault site of a **crashed** game. Complements
  `hang_stack.py`: that one reads a game that has *frozen*, this one reads a game that has *died*.
  Launches the target suspended (or `--attach PID`), `VirtualAllocEx`s an RWX region, writes x86
  shellcode for a **vectored exception handler** + install stub, `CreateRemoteThread`s the stub
  (`RtlAddVectoredExceptionHandler`), resumes. On a matching fault the handler copies `CONTEXT` +
  `EXCEPTION_RECORD` and **spins so the thread never unwinds**, and the Python side then reads
  registers, stack and memory out of the frozen process at leisure. Ported from Inioch's
  `Inioch/share6/patch scripts/diag_inject_veh.py`.
  `--self-test` (7 scenarios, no game involved) · `--dis` (read the shellcode back) ·
  `--census` · `--skip N` · `--at MOD+0xRVA` · `--fault-range LO-HI` · `--code`. Patches nothing.
  ⭐ **`--census` entries are full records since 2026-09-25** (from Inioch's share8
  `diag_veh_logger.py`): registers, up to 0x400 B of stack (clamped at the thread's `fs:[4]`
  StackBase), and for a Delphi raise (`0x0EEDFADE`) the raise site plus the exception's class name
  and message. Class and message are copied **inside the handler**, because the except block has
  usually freed the object before this side polls. 32 entries; an entry counts once its sequence
  word (written last) matches. Names the raise site of a swallowed TE/Draw exception without
  `build_te_exception_detail.py`'s Network.dpl patch.

  ⭐ **Why a VEH and not a debugger:** AoW1 is Delphi with its own memory manager, so attaching a
  debugger changes the heap layout enough that an out-of-bounds read lands on benign memory and the
  crash stops reproducing. `_NO_DEBUG_HEAP` does not help — that is the *Windows* heap. The handler
  runs in-process, so no debug port is ever set and the real crash happens.
  ⚠ **The first access violation is often not the fatal one** — Delphi raises and handles AVs
  inside `try..except` (and uses code `0x0EEDFADE` as ordinary control flow). Run `--census` to see
  what actually flies past, then `--skip N`.
  ⚠ **WOW64:** `RtlAddVectoredExceptionHandler` must be resolved from the *target's* 32-bit ntdll —
  64-bit Python's own copy is the wrong bitness. At `CREATE_SUSPENDED` the loader list is empty, so
  the tool finds ntdll by scanning the target for `MEM_IMAGE` regions with machine `0x14C` rather
  than by enumerating modules (Inioch used a throwaway normal launch for this; the scan avoids
  launching the game twice). Registers come from `Wow64GetThreadContext`.
  ⚠ A `--at MODULE+0xRVA` filter **cannot** be baked in at injection time (no module but ntdll is
  mapped yet); it is data in the injected control block and is armed once the module appears.
  ⚠ The RWX region is placed clear of every game module's preferred `ImageBase`, so it cannot bump
  `AoWEPACK.dpl` off `0x55700000` — Inioch's version could, which made the captured addresses
  unfamiliar. The report prints each module's real base and flags anything relocated anyway.

- **abmask.py** `[module] [--use]` — dumps every ability's **owner-type legality mask**
  (`TAbility+0x20`) and the owner-side `GetAbilitySelectionTypes` (VMT +0x8c) constants. This is the
  fastest way to learn what a subsystem was *designed* to do: the mask bits are b0=unit,
  b1..b6 = itHead/itTorso/itAttack/itDefense/itRing/**itUse**, b9=hero, and **itScroll's mask is
  0x0000** (no ability may ever live on a scroll). Answered "why do Use items work differently" in one
  table — `itUse` is the lane for *activatable* abilities (only 10 classes declare bit 6, all
  touch/bolt/ranged/targeted), while passives like Marksmanship are routed to the wearable slots.

  ⚠ The mask is **not enforced on items**: its only enforcer,
  `TAbilityOwner.ValidateOwnerTypeAbilities`, is called solely from `TUnitResource.ReadWrite`. So an
  illegal ability on an item is kept-but-ignored, and a legal one is not guaranteed to work. Declared
  legality and observed behaviour are independent — check both.
  ⚠ `Ability.pfs` record ids are **not** ability ids (record 0x2F holds Leadership's description) —
  it is a description table with its own numbering. The masks live in code, in each `.Create`.
  ⚠ `aowsyms.get_symbols` strips the `@<unit-hash>` Ghidra shows — filter on `.endswith(".Create")`,
  not `".Create@23EDC2EF"`, or you silently match zero symbols.

## Added 2026-09-25 (ported from Inioch's share8)

- **hwbp.py** — hardware **watchpoint**: who writes (or reads, `--access rw`) this address.
  `DebugActiveProcess`, Dr0/Dr7 on every thread, one report per hit (the instruction after the
  access, the bytes before it, registers, call chain), then clears Dr7 and detaches; the game keeps
  running. Address as `0xABS`, `MODULE+0xOFF` or `@0xLINKVA` (rebase-safe). `--len 1|2|4`,
  `--seconds`, `--max-hits`, `--log PATH` (nothing is written without it). Proven on the live game
  2026-09-25.
  ⚠ On x64 the `DEBUG_EVENT` union starts at +16, not +12; his original read every exception code
  four bytes off. ⚠ A WOW64 debuggee's single-step arrives as `0x4000001E`, not `0x80000004`.
  ⚠ Attaching to a running process does not switch on the debug heap, so `veh_capture.py`'s
  Heisenbug does not apply.
- **ref_probe.py** — who points at this object: scans committed writable memory for the address and
  names each holder as `Class obj@X +0xOFF` (nearest preceding live VMT, recognised by the Delphi
  self-pointer `[vmt−0x40] == vmt`, so every module's classes resolve) or `MODULE+0xOFF (global)`.
  Proven on the live game 2026-09-25 (15 holders of `TAoWHSMap`, incl. the `0x558FA040` global).
  ⚠ A classref field also looks like a VMT; a TList item array and a stack local have no VMT before
  them.

Not ported: `diag_veh_attach.py` (= `veh_capture.py --attach`).
