# Vision — nine levels, +1 sight each

**Status: CONFIRMED WORKING (2026-08-09)** — author-tested in game.

`sight = 3 + level`, levels **I..IX**. Was `3 + 2*level` capped at IV (sight 11); the new ceiling is
12. Ability id `0x40`, class `TVisionAbility : TMultiLevelAbility : TAbility`.

| | |
|---|---|
| script | `build_scripts/build_vision9.py` (`--apply` / `--undo` / `--dis`, dry-run default) |
| binaries | `AoWEPACK.dpl` only — **no exe patch, so no AoWCompat lockstep** |
| data | `Release/Ability.pfs` record 74 tag 5 (the description) |
| backups | `AoWEPACK.dpl.pre-vision9`, `Release/Ability.pfs.pre-vision9` |
| revert | `--undo` — surgical on both files, touches no backup |

**The full derivation lives in the script's docstring** — every address, why each site was chosen,
the PIC scheme, and the re-tune procedure. It is the source of truth; this doc holds the things a
docstring is the wrong place for.

## The five patch sites

| VA | change | note |
|---|---|---|
| `0x557B9889` | `mov [esi+0x28], 4` → `9` | the ceiling; `CanExpand` is the only gate and Vision inherits it |
| `0x55780F12` | `03 F6` → `90 90` | `TAbstractUnit.VisibilityRange` — strategic |
| `0x55724AEE` | `03 F6` → `90 90` | `TCombatUnit.GetVisibilityRange` — tactical |
| `0x557B9897` | 72 B of four inline `Put`s → `jmp cave_vcosts` | nine per-level costs instead of four |
| `0x557B5138` | VMT `+0x10C` → `cave_vlname` | level names V..IX; slot keeps its `.reloc` |

⚠ **`0x55817000..0x55817400` (1024 B) is RESERVED by this feature.** Content is ~280 B but the block
is written and zeroed as one unit, and its ownership test is the two hooks pointing into it — it
does not inspect contents. Anything a future feature parks in that range is silently overwritten on
`--apply` and zeroed on `--undo`.

## Why the two halves of the request could not ship separately

`TArmy.UpdateVisibilityRanges` @`0x5578E10C` packs the stack maximum into a **nibble pair** at
`[army+0x29]` with **no clamp** — `shl ebx,4` puts max TrueVisionRange in the high nibble, `add bl`
puts max VisibilityRange in the low one. So sight must stay ≤ 15.

| | max sight | fits? |
|---|---|---|
| before: cap 4, +2 | 11 | yes |
| **cap 9, +2 (raising the cap alone)** | **21** | **no — wraps and corrupts TrueVisionRange** |
| cap 9, +1 | 12 | yes |

The change is in fact *safer* than what it replaced: at `3 + 2*level` a data-assigned level of 7
would have overflowed; at `3 + level` it takes 13. And `GetLevel` is **not** clamped by
`[ability+0x28]` — the cap only gates `CanExpand` — so a data level above the cap does reach the
arithmetic. Nothing in the installed data does that (max assigned is 4).

Cannot stack: both sight sites query via VMT `+0x144`, the **item-searching** accessor, which routes
through `GetSuperlativeAbOwner` @`0x557881DC` — that takes a **max, not a sum**, so an item granting
Vision cannot add to an innate level.

## Balance — the nerf is deliberate

Unit data was **not** rescaled; author's decision, 2026-08-09. Every existing holder simply sees
less. **Do not add a rescale path.**

| Vision | sight before | after | carriers |
|---|---|---|---|
| I | 5 | 4 | 22 units, 49 heroes |
| II | 7 | 5 | 22 units, 1 hero, Helm of Eyes |
| III | 9 | 6 | 13 units |
| IV | 11 | **7** | 7 units (incl. Air Galley, Beholder) |

Matching the old level-IV sight now needs Vision VIII — 64 skill points against the previous 32.

## ⚠ Pre-existing undocumented Ziggurat edits at these sites

Byte-diff against `AoWEPACK_original_backup.dpl` found two edits that predate the note-taking
convention and are owned by **no build script**:

| VA | pristine | live | meaning |
|---|---|---|---|
| `0x55780F12` / `0x55724AEE` | `83 C6 04` | `83 C6 **03**` | base sight 4 → 3 |
| `0x557B9897` | `B9 **05**` | `B9 **08**` | per-level cost 5 → 8 |

A script written against Ghidra's vanilla image would assert the pristine bytes and abort.
`build_vision9.py` verifies the **live** values and aborts with an explanatory message if it ever
finds the pristine base of 4.

## Failed / rejected approaches — do not re-try as-is

1. **Extending the existing jump table.** `GetLevelName` does `jmp dword [edx*4 + 0x557B9920]`;
   bumping `cmp edx,4` and repointing the disp32 into a cave looks clean. It is not: **all five
   table entries carry `.reloc` entries**, and a cave-hosted table has none, so every entry goes
   stale the moment the package rebases. Repoint the **VMT slot** instead — it is itself relocated.
2. **Copying `mov eax,[0x558E90C0]` (LoadResString) into the cave** to fetch the "Vision" stem. That
   is an absolute memory reference; a cave copy cannot be relocated. Call the original
   `GetLevelName` with level 0 instead — it reaches the resourcestring through already-relocated
   code. (Same technique as `build_leadership4.py`'s `cave_lsname`.)
3. **Treating a 4-entry cost list read at index 9 as a crash.** It is not — `TIntegerList.Get`
   @`0x55513D5C` is bounds-checked and returns the list's default. The real consequence is milder
   and worse to find: levels V–IX would have cost **zero** skill points.

## The in-game description

Reads, in full — one line, no header sentence:

```
+1 vision range per level
```

⚠ **Deliberately NOT a per-level enumeration.** Two author instructions on 2026-08-09, in order:
drop the `Level 1  (+1)` … `Level 9  (+9)` listing (at a flat +1/level the running total is
redundantly obvious, and nine lines of it is noise), then drop the "Gives the unit increased visual
range in addition to the base 3 range." header too. Vanilla enumerates because its curve is
+2/level over four levels, where the total is worth spelling out. The info card does **not** clip —
it scrolls — so this was readability, not a fix.

⚠ **`desc_shape()` accepts all THREE forms and must keep doing so.** Each was the emitted format
for part of that day, so a real install can carry any of them, and dropping an arm strands exactly
those installs — `--apply` *and* `--undo` both refuse and the only recovery is editing the script:

1. bare curve, no header — current output
2. header + bare curve — briefly emitted between the two instructions
3. header + per-level listing — vanilla, and our first output

**Whenever the emitted format changes again, keep the previous arm.**

## Hero skill cost — the DLL is authoritative, not `Ability.pfs`

**4 skill points per level** (36 to reach IX). Halved from 8 on 2026-08-09.

⚠ For a multi-level ability the cost lives in the **DLL**: `TAbility.ExpandCost` @`0x5574E908`
returns `Ability.pfs` tag 6, but **`TMultiLevelAbility.ExpandCost` overrides it** and reads the
per-level `TIntegerList` at `[ability+0x2C]` — the list `cave_vcosts` fills. Tag 6 is inert for
cost here; `build_vision9.py` writes it anyway (`COST_EACH` → tag 6) purely so the Ziggurat Manual,
which reads tag 6 for its "Hero cost" column, does not print a number the game never charges.

**The manual's Hero cost column now reads the DLL** — `re_tools/ability_names.py costs()`, added
2026-08-09. Tag 6 was lying for two of the seven: Leadership printed 20 against a real 10, Spell
Casting printed 15 against a real 20. Three mechanisms had to be handled:

1. **`TMultiLevelAbility` descendants** fill the `[+0x2C]` list from their ctor — the cost is the
   `mov ecx, imm` feeding each `TIntegerList.Put` (Marksmanship 6, Spell Casting 20).
2. **...unless a mod replaced that run with a CAVE.** Leadership's live ctor still sets up
   `mov ecx, 0x14` (20) and then calls `build_leadership4.py`'s cave, which overwrites ecx with 10
   and loops. Reading the ctor alone gives the **stale pre-patch number**, so the scan follows one
   hop and the cave wins. Vision is the same shape. ⚠ It follows **unnamed** targets only — a cave
   has no export symbol, and a named callee's Puts must never outrank the ctor's.
3. **A class with its own `ExpandCost`** ignores the list entirely: `TTurnUndeadAbility` returns a
   flat `mov eax, 5` while below the cap, 0 at it.

⚠ **A cost is shown only when the hero level-up path actually offers the ability** — `Ability.pfs`
tag 9 mask & `0x100` (`astHeroUpgrade`). **Transport and Dispel Magic have real per-level cost
lists but no level-up screen ever shows them**, so quoting a price would be fiction; both render
blank. That rule is data-driven, not a special case, and it blanks 12 of the 109 rows.

Per-level costs, vanilla → Ziggurat: Marksmanship 5→6, Vision 5→4, and Turn Undead 5, Leadership
10, Spell Casting 20, Dispel Magic 5 unchanged. ⚠ Leadership's *cost* never moved — what Ziggurat
changed was the level count, 1 → 4.

⚠ `--undo` restores **8**, not vanilla's 5: Ziggurat had already retuned 5 → 8 in both the ctor and
tag 6 before this feature existed, so `.pre-vision9` carries 8. Restoring 5 would be a silent extra
edit dressed as an undo (`COST_PREV` in the script).

## First length-changing `.pfs` write in this project

Record 74 tag 5 went 136 B (vanilla) → 211 (enumerated 9 levels) → 103 (header + one line) →
**31 B** (bare line); the record 161 → 236 → 128 → **56 B**. 87 later index offsets shifted on each
pass: +75, −108, −72. **Both directions exercise the same path** — every pass ran a full collateral
re-parse (151/151 records, 150 byte-identical) before writing, so the shrink case is as proven as
the grow case.
Format notes and the general recipe are in `PFS_Format_CRC.md`; what this feature added:

- ⚠ **The description is a `u32`-length-prefixed string**, not the `u8` Pascal form used for names.
  `pfs.pstr()` misreads it (three leading NULs, drops the last character).
- **Two ceilings when re-tuning — but only one still applies.** Record 74's body directory uses
  **u8** offsets, and while the description enumerated every level, `MAX_LEVEL` 11 pushed tag 9 to
  257 and aborted two rungs before the nibble would. **The one-line description retired that**: the
  record no longer grows with `MAX_LEVEL`, so `[army+0x29]` (base + cap ≤ 15) is now the only wall.
  The u8 table in the script docstring is kept because it still describes what happens if anyone
  reinstates a per-level listing. Escape, if ever needed, is wide entries (records 32/67/68/71
  already use them).
- **The CRC gate catches incoherent damage, not a coherent-but-wrong layout.** A nudged index
  offset *with the CRC re-repaired* plans `ok`. Do not oversell it.
- ⚠ **A backwards tiling of body lengths is NOT an index integrity check** — `parse_index` derives
  those lengths from the very offsets being checked, so it can never fail. `build_drillmaster.py`
  carried the same idiom; both are fixed as of 2026-08-09.
- **The map editor round-trips this record.** The author re-saved the whole resource set from
  AoWEd after the edit was applied, and record 74 came back byte-identical.

## Re-tuning

`MAX_LEVEL` / `COST_EACH` / `SUFFIXES`, then re-run `--apply`. **Do not revert first** — both halves
rewrite in place and accept either the installed bytes or the new ones. Verified 6/6 in both
directions, including undoing a level-10 install with the level-9 script. Take the ceilings above
seriously: 10 is the last value that fits without switching record 74 to wide directory entries.

## Related

- `build_scripts/build_vision9.py` — the derivation
- `Investigation_Abilities_Leadership.md` — `TMultiLevelAbility`, `[+0x28]`, and
  `ability_names.levels()` which now reads every levelled ability's ceiling off the live DLL
- `Leadership_FourLevels_And_Fix.md` / `build_leadership4.py` — the donor for the cost cave and the
  `GetLevelName` VMT repoint
- `PFS_Format_CRC.md` — `.pfs` container, CRC, and the level-record format
