# Drillmaster — new passive ability (id 0xAB)

**Status: CONFIRMED WORKING 2026-08-08 (v4)** — XP grant, hero level-up availability and
multi-Drillmaster stacking all validated in play. Three bugs were found by playing it: an id
collision crashed startup (v1), the grant fired once per player (v2), and the ability never
appeared in the hero level-up dialog (v3).
Built by `build_scripts/build_drillmaster.py` — `AoWEPACK.dpl` (backup `.pre-drillmaster`) **and
`Release/Ability.pfs`** (backup `Ability.pfs.pre-drillmaster`), surgical `--undo` for both. Every
cave is disassembled back out of the written file before applying.

**Effect.** A stack containing a Drillmaster grants **+1 XP per turn to every other unit in it,
and the effect stacks** — N Drillmasters in one army give +N. Excluded: the Drillmasters
themselves (trainers do not train each other) and heroes, who already have their own XP trickle
and would otherwise double-dip.

## Why this was cheap: both halves already existed

Nothing here is new engine behaviour — it is two existing patterns joined.

| Need | Borrowed from | Address |
|---|---|---|
| A per-turn, per-stack hook | `TArmy.NewTurn` — one call per army per turn, and an army *is* the stack | `0x5578F79C` |
| Walking a stack's units | `TArmy.UpdateFormation`, the Leadership aura | `0x5578D034` |
| Asking a unit for an ability | `unit->vmt[0x148](id)` `GetAbilityEnabled` | — |
| Reading/writing XP | `unit->vmt[0x15C]` / `[0x160]` | — |
| Telling heroes apart | `System.@IsClass(obj, THero-vmt)` | `0x557010C0` / `0x55711FEC` |
| Registering an ability | the Path of Sand recipe | `Path_Of_Sand_NewAbility.md` |

**Stacking was nearly free** (v4). Pass 1 already walked the whole stack looking for a
Drillmaster — it just stopped at the first one and used `ebx` as a 0/1 flag. Counting instead is
`inc ebx` in place of `mov ebx,1; jmp p1done`, and pass 2's `inc edx` becomes `add edx, ebx`.
Three instructions, and the cave got 9 bytes *shorter*; the zero-the-zone-first step in `--apply`
is what stops the tail of the old build staying executable behind it.

The stack walk is `count = [[army+8]+8]`, `items = [[army+8]+4]`, `unit = [items + i*4]`.
⚠ **The count is on the LIST at +8, not on the army** — the standing trap for any cave that
iterates an engine list.

⚠ **The ability test uses the item-aware accessor pair** (`+0x144`/`+0x148`), not the
self-only `+0x84`/`+0x88` pair. Two-ability-query-APIs is a documented way to ship an ability
that registers fine and then does nothing; using the item-aware pair also means a Drillmaster
*item* would work with no further code.

Both XP accessors are virtual, so one path covers heroes (dword at `+0x48`) and units
(clamped byte) with no special casing — even though heroes are then skipped anyway.

## Layout

| Piece | VA | Size |
|---|---|---|
| `cave_reg` | `0x55816000` | 42 B |
| name literal `"Drillmaster"` | `0x5581602C` | 20 B |
| `cave_turn` | `0x55816040` | 173 B |

Cave space came from the 861 KB free run starting `0x5581546D`; `0x55814000` and
`0x55815000` were both already occupied, so **do not assume a round address is free** — scan.

### Hooks

- `0x557BCF39` `call RegisterAbility` → `call cave_reg`
- `0x5578F79C` (`TArmy.NewTurn` entry, 6 bytes `53 8B D8 3A 53 12`) → `jmp cave_turn` + `nop`,
  resuming at `0x5578F7A2`. The cave re-executes the displaced
  `push ebx; mov ebx,eax; cmp dl,[ebx+0x12]` **last**, immediately before jumping back, because
  the `jne` at the resume point consumes that comparison's flags.

⚠ **Path of Sand already owns the Path-of-Frost RegisterAbility call at `0x557BC9E9`.** This
feature deliberately takes the *last* call in `RegisterPassiveAbilities` instead. Anything
adding a third ability must pick yet another call site — there are ~90 to choose from, and
`build_drillmaster.py` prints which are already repointed.

## The selection mask — why a working ability can still be un-pickable

`CreateEnhancementAbility(id, name, X)`'s third argument is **not an icon index** (this script
called it `ICON` until v4, copying the constant out of the Path abilities without decoding it).
It is a `TAbilitySelectionType` set, stored as the word at `[ability+0x20]`. Names read straight
off the Delphi RTTI enum at **`0x55708E6C`** — the reliable way to name a bitfield here:

| bit | | bit | |
|---|---|---|---|
| `0x001` astUnit | `0x002` astHeadItem | `0x004` astTorsoItem | `0x008` astAttackItem |
| `0x010` astDefenseItem | `0x020` astRingItem | `0x040` astUseItem | `0x080` astCustomizeLeader |
| `0x100` astHeroUpgrade | `0x200` astEditor | | |

**The hero level-up dialog demands BOTH of the top two, from two different places** — which is why
half a mask looks like it should work:

- the dialog's own fill loop tests `astHeroUpgrade` directly (`test byte ptr [ability+0x21],1`);
- `TAbility.CanExpand` @`0x5574E8B8` ANDs the whole mask with the owner's
  `GetAbilitySelectionTypes`, and **`THero`'s** @`0x55786B10` returns `0x200 astEditor`
  (`TAbstractUnit`'s returns `astUnit`; `TItem`'s returns its slot bit).

Drillmaster carried `0x0137` — astHeroUpgrade set, astEditor clear — so it registered, was
assignable in DevEd, showed on unit cards and granted XP correctly, and was still never offered
at level-up. `build_drillmaster.py` now uses **`0x03FF`** (every context), which is what 80 of the
101 level-up abilities carry.

⚠ **The `.pfs` wins over the cave.** `TAbilityControl.ReadWrite` @`0x55750164` serialises each
ability under tag `list index + 10`, and `RegisterAbility` parks the object at `list[id]`, so the
record key is `id + 10`. `TAbility.ReadWrite` @`0x5574F07C` then reads **tag 9** straight into
`[ability+0x20]` — *after* registration. Measured: **all 21** vanilla `CreateEnhancementAbility`
sites register a mask the data file promptly overwrites, and **0 of 21 agree**. Patching the cave
alone would have changed nothing on screen. The script therefore edits `Release/Ability.pfs`
record 181 tag 9 as well, deriving the offset from the index (never hard-coded — DevEd rewrites
the file and every offset moves) and repairing the trailing CRC-32 (`PFS_Format_CRC.md`).

Other tag semantics on an ability record, from `TAbility.ReadWrite`: tag 5 description,
**tag 6 hero level-up cost** (`ExpandCost` = `[ability+0x14]`), tag 7 SFX, tag 8 image list,
tag 9 selection mask.

⚠ Inioch's `build_mod_manual.py` reads hero availability as `(mask & 0x80) and (mask & 0x100)`.
That happens to select the same 96 vanilla abilities, because every stock ability with
`astHeroUpgrade` also has `astCustomizeLeader` and `astEditor` — but the bit the engine actually
tests is `0x200`, so the heuristic mislabels any *new* ability. Use `0x100 | 0x200`.

## Failed approaches / traps

- **⚠ `TArmy.NewTurn` is NOT called once per turn — it is called once per PLAYER.** It filters
  with `cmp dl,[army+0x12]` (dl = player index) as its very first act, and v1 of the cave did
  its work *above* that guard. Result: every unit in a Drillmaster stack gained +1 XP per
  player per turn — **+3 a turn in a three-player game**. The cave now repeats the same
  comparison before scanning, and re-executes it at the end for the host function. Any cave
  hooking a per-object `NewTurn`/`NewDay` entry point should assume the same shape and check.

- **⚠ Ability id 0xAA collided — `Runtime error 217` before the main window.** The first build
  used 0xAA on the strength of `Ability_ID_Budget.md` calling **0xAA–0xCD** "guaranteed safe".
  That band has gone stale: 0xAA is now the *highest id in use*, not the first free one, and
  re-registering it raises an unhandled exception during unit initialisation, which Delphi
  reports as runtime error 217. Nothing in the crash names the ability system.
  **Never take the documented band on trust.** `build_drillmaster.py` now measures it on every
  run (`check_id_free`) from two independent sources — `mov eax,<id>; call
  CreateEnhancementAbility` sites in the DLL, and the record keys of `Release/Ability.pfs`
  (key = id + 10) — and aborts before writing if the id is taken. As of 2026-08-07: 150 ids in
  use, highest 0xAA, so **0xAB** is the first free one.

- **`call $+5` as the PIC delta anchor — DOES NOT ASSEMBLE.** Keystone silently emits *nothing*
  for it. The anchor search then finds whatever earlier `E8` happens to sit five bytes before a
  matching `pop` and zeroes **its** rel32. In `cave_reg` that was the `call RegisterAbility`,
  which would have become a call into the middle of this cave — a crash at startup, from an
  instruction that looks right in the source. Always write a real `call <addr>`; the target is
  irrelevant because the rel32 gets zeroed anyway. Caught only by disassembling the assembled
  bytes, which is why that rule exists.
- **Testing hero-ness by instance size** (`[VMT-0x1C]`: `0x48` TUnit vs `0x9C` THero) was
  considered and rejected. It is rebase-free and tempting, but the copper-medal work already
  grew `TUnitResource` once; a size check would break silently the next time a class grows.
  `IsClass` costs a delta-trick and handles `TLeader` for free.

## Open choices (not defects)

1. Drillmasters do not train each other — N of them give +N to everyone *else*. Cross-training
   would be a one-line change to pass 2's skip test.
2. The tally is uncapped. A stack holds at most 8 units, so the ceiling is +7/turn for a lone
   trainee among seven Drillmasters; self-limiting, but clampable if it ever matters.
3. `0x03FF` also makes Drillmaster item-assignable. The cave uses the item-aware accessor pair,
   so a Drillmaster ring already works — narrow the mask in DevEd if that is unwanted.
4. Whether Drillmaster should also be grantable as a medal-rank bonus.

The category default was never in question: `herodlg_cats.py` sends every unlisted id to
`DEFAULT_CAT` = Magic, and the live `AoW.exe` table byte for 0xAB reads 4.
