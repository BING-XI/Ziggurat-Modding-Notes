# Grip of Winter (ex-Freeze Water) — design

> **Status: 🔨 APPLIED, UNTESTED (2026-09-01) — needs the user's in-game test.** All four pieces are
> installed and byte-verified; nothing here is confirmed until it is played. Every address was read
> out of the **live** `AoWEPACK.dpl`; the design decisions are the user's (2026-08-31).
> Part of the terrain system — see `Terrain_System_INDEX.md` and `Terrain_Changing_Spells_Map.md`.

> ⚠⚠ **COUPLED WITH `RaiseTerrain_UG_Earth.md` (applied 2026-09-03), IN BOTH DIRECTIONS.**
> **(a)** That feature depends on this one: it reuses the `+0x0E`/`+0x0F` scheme, `C_RW`, `C_MELT`
> and `C_HSTC` wholesale, and refuses to apply if this script's four `TFrozenWaterHS` hooks are
> absent — without them its raised earth would be permanent. **(b)** It rewrites the first six bytes
> of this script's `C_SHOW` cave (`0x5582A4E0`), which this script byte-compares — so **while it is
> installed, `build_gripofwinter.py` can neither `--apply` nor `--undo`**; both abort with
> `cave 0x5582A4E0 is foreign`, before writing. **Undo `build_raiseterrain_ug_earth.py` first**, and
> this script's undo comes straight back.

| | |
|---|---|
| binary | `build_scripts/build_gripofwinter.py` → `AoWEPACK.dpl`, backup `.pre-gripofwinter` |
| name | `build_scripts/build_resstr_names.py` → `Dict/ResStr.mld` + `.txt` |
| description | `build_scripts/build_pfs_typos.py` → `Release/Spells.pfs` rec 20 tag 10 |
| manual | `build_ziggurat_manual.py` prose (shipyard-income section) |
| revert | `build_gripofwinter.py --undo` — surgical, verified byte-exact, touches no backup |

## What is being built

Freeze Water becomes **Grip of Winter**: it keeps its ice, gains a **terrain-cooling ladder**, and
becomes **castable on any hex** rather than water only. The cooling is **temporary and reverts**,
the way the ice already melts back.

| | |
|---|---|
| Ladder (one step per cast) | Desert(2) → Steppe(4) → Grass(1) → Snow(3) |
| Water arm (unchanged) | Water(0) → Ice(6); CaveWater(A) → CaveIce(D) |
| Footprint | unchanged — radius 1, the target hex and its six neighbours |
| Duration | temporary, same timer and melt path as the ice |
| Target gate | widened from water-only to any explored hex with no structure and no army |
| Binaries touched | `AoWEPACK.dpl` only — plus two data files (`Dict/ResStr.*`, `Release/Spells.pfs`) |

Snow is the floor: nothing cools past it, and Wasteland/Lava/Dirt/Ice are not on the ladder
(user's choice — the wider "lava and wasteland too" variant was offered and declined).

## Baseline state — verified, not assumed

Every Freeze Water function is **byte-identical to `AoWEPACK_original_backup.dpl`** except one byte:

- `0x5579E96B`: `mov edx,0xB` → `mov edx,0x20` in the live file. That is the **initial freeze
  countdown range** — pristine `Random(0xB)` → 1–4 turns, live `Random(0x20)` → 2–8 turns. It is a
  **pre-convention orphan edit with no owning build script**; nothing re-derives it if lost.

So this feature starts from clean ground, and `--undo` must restore *that* byte, not the pristine one.

## The five functions involved

```
GlobalTargetSpells.TFreezeWater.Create                   0x5579EAE8   name + id 0xA + cost 5
GlobalTargetSpells.TFreezeWater.ValidTargetMapF          0x5579EB8C   water-only gate #1
GlobalTargetSpells.TFreezeWater.ValidTargetSelectionMapF 0x5579EBDC   water-only gate #2
GlobalTargetSpells.TFreezeWaterTE.ChangeTerrain          0x5579E884   per-hex mutate callback
GlobalTargetSpells.TFreezeWaterTE.TerrainChanged         0x5579E900   per-hex commit callback
AoWE.TFrozenWaterHS.*                                    0x55764AA0+  the temporary-terrain marker
```

`TFreezeWaterTE.Process @0x5579E994` drives it: map VMT **+0xD4** (`ChangeTerrainEx` area form),
`push 1` = radius 1 at `0x5579EA99`, with the two callbacks above.

---

## 1. The rename — one data row, no binary surgery

Spell names are Delphi resourcestrings, but every one passes through the translation dictionary.
`TFreezeWater.Create` proves the route:

```
5579EB1B  mov eax,[0x558E9454]     ; FreezeWaterRStr
5579EB20  call System.LoadResString
5579EB2B  call AoWE.TranslateRStr  ; -> Dict/ResStr.mld
5579EB36  call System.@LStrAsg     ; -> [spell+8], the displayed name
```

- `Dict/ResStr.txt:4480` — `NATIVE = [Freeze Water]`, `[US]` slot currently empty → `Grip of Winter`.
- Use **`build_resstr_names.py`** (already CONFIRMED WORKING, surgical `--undo`, writes `.mld` and
  `.txt` in lockstep). Full format notes in `ResStr_Dictionary_Names.md`.

⚠ **Do not touch the `.rsrc` resourcestring** — the UTF-16 block has no slack and growing one entry
shifts every entry after it.

### Two text follow-ons

- **`Release/Spells.pfs` record 20, tag 10** (record id = spell id 0xA + 10) currently reads
  `'Freezes a small area of water, rendering it solid enough to walk over.\r\n'`. It must describe
  the cooling and the reversion. One row in **`build_pfs_typos.py`** (handles the CRC and the
  offset shifts).
- **`build_ziggurat_manual.py:2720`** names "Freeze Water" in the shipyard-income prose.

---

## 2. The cooling ladder — one cave, one 6-byte hook

`TFreezeWaterTE.ChangeTerrain @0x5579E884` (EAX=TE, EDX=mapField, ECX=→terrain byte, `RET 4`):

```
5579E890  call GetArmyHS(field)     ; army on the hex -> nothing happens at all
5579E899  jne  0x5579E8F7           ; (epilogue)
5579E89B  movsx eax,[ebx]           ; <-- HOOK SITE, 6 bytes (0F BE 03 66 85 C0)
5579E89E  test ax,ax                ;     0 Water     -> 6 Ice
5579E8A8  cmp  ax,0xA               ;     A CaveWater -> D CaveIce
5579E8B3  sub al,6 / sub al,7       ;     already 6/D -> refresh the melt timer
5579E8BB  jne  0x5579E8F7           ;     EVERYTHING ELSE -> nothing      <-- the gap
```

Hook `0x5579E89B` with `E9 rel32` + `NOP` — the identical 6-byte `movsx`/`test` idiom
`build_icestorm_lava.py` already uses on `TIceStorm.ChangeStormTerrain`. The cave:

- terrain 2 → 4, 4 → 1, 1 → 3; write through ECX, `jmp 0x5579E8F7`
- anything else → replay `movsx eax,[ebx]; test ax,ax`, `jmp 0x5579E8A1`

Register-only + rel32, so **position-independent** as the rebasing DPL requires. No RNG, so the
lockstep rule is moot — though note this function already draws from the **synced** generator
(`0x5577827C` at `0x5579E8DC`), so a roll could be added safely later.

Placing the hook *after* the `GetArmyHS` gate makes cooling inherit the spell's existing
"not under an army" rule for free.

**One step per cast, no cascade.** `ChangeTerrainEx` makes a single pass per cast (unlike storms,
which pass over the centre four times via `TBlastStorm.UpdateStorm`), and the callback reads the
original byte once. Desert → Snow therefore takes three casts. This matches Healing Showers and
Desiccate.

### Cave space

Highest occupied CODE byte is **`0x5582A16D`** (`build_terror_oncepercombat.py` reserves
`0x5582A000..0x5582A200`). Allocate from **`0x5582A200`** — a verified all-zero run of `0xBD7AA`
(~775 KB) follows.

---

## 3. Castable anywhere — two tests, and they are the only terrain gates

The base `TGlobalTargetSpell.ValidTargetMapF @0x5579E4A8` is `mov al,1; ret`, so the water
restriction lives entirely in these two identical fragments:

```
ValidTargetMapF           0x5579EBA0   movsx edi,[ebx+0x14]; test di,di; je ok; cmp di,0xA; jne reject
ValidTargetSelectionMapF  0x5579EBF0   same test on [esi+0x14]
```

Widen both so any terrain passes. The surviving gates are worth keeping and need no change:

- `FindNoneTransparentHS(TStructure)` must be null — no structure on the hex
- `GetArmyHS` must be null — no army on the hex
- `ValidTargetSelectionMapF`'s base call additionally requires the hex be **explored**

⚠ **Both must move together.** `ValidTargetMapF` decides validity; `ValidTargetSelectionMapF`
decides what the cursor will highlight. Patching one leaves the spell either uncastable or
untargetable.

---

## 4. Temporary cooling — `TFrozenWaterHS` already has the room

`TFrozenWaterHS` (ClassID `0x2016C`, VMT `0x557147B4`, class-ref slot `0x55714774`) is the
existing "this terrain reverts" marker. Measured layout:

| | |
|---|---|
| instance size `[VMT-0x1C]` | **0x10** |
| `+0x04` | the map field |
| `+0x0C` | countdown, decremented on the owner's turn |
| `+0x0D` | owner (caster tag) |
| **`+0x0E`, `+0x0F`** | **free** — Delphi alignment padding |

⭐ **No class resize is needed.** Every method was disassembled (`ClassID`, `GetLevel`, `ReadWrite`,
`MeltIce`, `TerrainChanged`, `NewTurn`, `MsgProc`, `Show`) and **none references `+0x0E` or
`+0x0F`**. The only `+8` in the family is `[ebx+8]` inside `TerrainChanged`, which is the
notification struct in EDX, not `Self`.

### The two new fields

- **`+0x0E` = terrain to restore.** `0` means "vanilla ice marker" — which is also the vanilla
  restore value for Ice(6), so the sentinel is semantically free. Delphi's `InitInstance`
  zero-fills, and old saves carry no value for it, so **every pre-existing marker reads 0 and
  behaves exactly as before**.
- **`+0x0F` = the terrain this marker set.** Needed so `TerrainChanged` can tell "is my change
  still standing?" from "someone else overwrote this hex".

### The four edits

**a. `TFreezeWaterTE.TerrainChanged @0x5579E900`** — the commit-pass callback that creates markers.
⭐ It is already handed the **old terrain in CL** (`mov [ebp-1],cl` at `0x5579E907`) and the field
carries the new terrain at `[esi+0x14]`, so both new fields are available with no extra plumbing.
Vanilla creates a marker only when the new terrain is 6/D and the old was not; widen it to also
create one when the cooling fired, setting `+0x0E` = old and `+0x0F` = new. The existing countdown
(`Random(0x20)` → 2–8 turns, synced RNG, correct for this context) and owner assignment are reused
as-is.

**b. `TFrozenWaterHS.MeltIce @0x55764AE0`** — vanilla restores Water(0) from Ice(6) and CaveWater(A)
from CaveIce(D), and otherwise frees itself (`call [ecx-4]` = Destroy, at `0x55764B60`). Add a land
arm that pushes `[self+0x0E]` instead of the hard-coded `0`/`0xA` into the same
`ChangeTerrainEx` call (map VMT **+0xD0**, single-hex form).

⭐ Note vanilla does **not** destroy the marker after restoring — the terrain change fires
`TerrainChanged`, which sees the hex is no longer its terrain and destroys it there. The land arm
inherits that for free.

**c. `TFrozenWaterHS.TerrainChanged @0x55764B6C`** — currently destroys the marker whenever the hex
is no longer 6/D. **Left alone, this fires on our own cooling and kills the marker instantly, making
the change permanent.** Widen to also survive when `+0x0E != 0` and the new terrain equals `+0x0F`.

**d. `TFrozenWaterHS.Show @0x55764BD0`** — draws looped image sequence `0x46` from `AoWHSSet+0x94`,
phase-offset per hex, and it would look wrong on cooled steppe or snow. Hook the entry:
`[eax+0x0E] != 0` → `ret 4` immediately.

⚠ **What that call actually is, corrected 2026-09-03.** It is not an "ice sprite" — `Show`'s single
outbound call is `ImageLib.TImageSequenceList.ShowLoopedEx` (via `0x5570291C`), a **looped animation
driven by the global anim tick with a per-hex phase of `hexX + 3*hexY`**. It is the Freeze Water
**shimmer**, and it is the *only* thing `Show` draws — the ice *look* comes from the terrain byte
(6 / 0xD) painted by the terrain renderer. There is no separable sprite, so `C_SHOW` is an
all-or-nothing gate on the sparkle. That is still the right call for cooled land, but it also
suppressed the sparkle on Raise Terrain's raised earth, which is why
`build_raiseterrain_ug_earth.py` now rewrites `C_SHOW`'s head — full derivation and the
three-marker-state proof that **this feature's own appearance is unchanged** in
`RaiseTerrain_UG_Earth.md` §5.

⚠ That fix discriminates on `+0x0F == 7` (Earth). **If Earth is ever added to the cooling ladder
above, cooled land starts to shimmer** — the discriminator would then need `+0x0E == Dirt` as well.

### Save/load

`ReadWrite @0x55764AAC` persists `+0x0C` as property id `0x1E` and `+0x0D` as `0x1F`
(EDX = field address, ECX = property id, EAX = archive, via `[archive_vmt+0x3C]`). Add `+0x0E` as
`0x20` and `+0x0F` as `0x21`.

⭐ **Property ids are a per-class running counter, not a global namespace.** Surveying all 223
`ReadWrite` methods in the module shows every class numbering its own fields upward from `0x0A`;
`TFrozenWaterHS`'s ancestors consume `0x0A..0x1D` and its own two are the next in sequence. So
`0x20`/`0x21` are this class's next free ids regardless of what other classes use, and because the
table is **id-indexed rather than positional**, old saves that lack them load fine
(`[[aow1-property-table-serialization]]`).

---

## Known wrinkle: re-casting on an already-cooled hex

Cast twice on the same hex (desert → steppe → grass) and there is only ever **one** marker.
The commit order in `ChangeTerrainEx` pass 3 is: write bytes → `TMapField.TerrainChanged`
(which notifies the marker) → the spell's own callback. So on the second cast the marker sees
grass ≠ its `+0x0F` (steppe) and destroys itself *before* the spell callback runs, and a fresh
marker is created with `+0x0E` = steppe. Left unhandled, the hex would then revert only to steppe, and one step
of cooling would become permanent.

**Decided (user, 2026-08-31): the marker remembers the ORIGINAL terrain.** Edit (c) must therefore
do more than survive — when `+0x0E != 0` and the new terrain is the next step down the same ladder,
**keep `+0x0E` unchanged**, update `+0x0F` to the new terrain, and do not destroy the marker. A hex
cooled desert → steppe → grass then reverts straight back to **desert** in one hop, and no amount of
re-casting ever terraforms permanently.

⚠ This makes edit (c) the load-bearing one. Because `TMapField.TerrainChanged` notifies the marker
*before* the spell's own commit callback runs, edit (c) is the only place that sees the second cast
while `+0x0E` still holds the original — get it wrong and the marker is already gone by the time
edit (a) could have preserved anything.

## Risks to check in game

- **The AI now has a much wider target set.** Both gates are what the AI's spell targeting consults,
  so widening them may make the AI cast Grip of Winter on arbitrary land. Watch an AI wizard with
  the spell before calling this done.
- **`CanChangeTerrain` vetoes.** `ChangeTerrainEx` pass 2 polls every HS on the field via virtual
  **+0x98**; `TStructure` and the terrain-adaptive `TILTerrainMO`/`TFixedILTerrainMO` family
  (forests, decorations) override it. A forested grass hex may refuse to cool. Mountains explicitly
  allow (`TMountainMO @0x557A2DDC` is `mov al,1; ret`).
- **A vetoed melt retries forever.** If the restore is vetoed, `NewTurn` keeps decrementing past
  zero and calling `MeltIce` every turn. Vanilla has the same property; worth confirming it is not
  visible.
- **Shipyard income.** Cooling does not create or destroy water, so it cannot move a water body —
  but `Shipyard_Water_Income.md` recounts daily and the ice arm still can.

## Build order

1. `build_resstr_names.py` — add the `Freeze Water` → `Grip of Winter` row.
2. `build_pfs_typos.py` — add the `Spells.pfs` record 20 tag 10 description row.
3. **`build_gripofwinter.py`** (new) — all six binary edits in one script with a surgical `--undo`:
   the ladder cave + hook, both target gates, and the four `TFrozenWaterHS` edits.
4. `build_ziggurat_manual.py:2720` — update the prose.

All four are applied. `build_gripofwinter.py` is dry-run by default, verifies before writing,
is idempotent, and its `--undo` restores each hook site and zeroes its own caves rather than
restoring a `.pre-*`.

---

## As built (2026-09-01)

7 caves (394 bytes in the reserved span `0x5582A200..0x5582A600`), 7 `E9` hooks, 2 in-place gate
widenings. Cave sizes: C_COOL 47, C_TCCLS 73, C_TCFIN 47, C_RW 50, C_MELT 110, C_HSTC 71, C_SHOW 20.

⚠ Since 2026-09-03 the **first six bytes of `C_SHOW`** (`0x5582A4E0`, its `cmp byte [eax+0x0E],0` +
`jne`) are owned by `build_raiseterrain_ug_earth.py` and read `jmp 0x5583E140` + `nop`. Its
remaining 14 bytes are untouched and are still the code that executes; both non-raised-earth marker
states still end on this script's own bytes at `0x5582A4E6` and `0x5582A4F1`. This is why
`--apply`/`--undo` report `cave 0x5582A4E0 is foreign` until that feature is undone.

### Checks that passed

- **`--undo` is byte-exact** against the pre-apply snapshot (sha256 match), and **`--apply` is
  idempotent** (re-apply reproduces the applied hash exactly).
- The orphan freeze-duration byte at `0x5579E96B` still reads **`0x20`**, not the pristine `0x0B`.
- No `.reloc` entry falls inside any displaced run; no branch anywhere in CODE targets the middle
  of one; the only absolute dword pointing at a run start is `0x55764BD0` = `Show`'s own VMT slot
  (`+0xA8`), and calls through it land on the `E9`.
- `rng_audit.py --owners`: still 23 modded sites, none in the new cave span — the caves add no draw.
- No profile-path leak: nothing in the game-root binaries or in any file this feature touched, and
  the cave span holds **no** drive-letter path and **no** printable string at all.
- `build_pfs_typos.py` collateral check: 108 records parse, all but the edited one byte-identical,
  CRC residue `0x2144DF1C` intact.

### What still needs the user's in-game test

1. **The ladder.** Cast on desert → steppe; on steppe → grass; on grass → snow. Snow must not cool.
2. **Castable on land** — the cursor should highlight land hexes, and the cast must go through.
   Structures and occupied hexes must still refuse.
3. **The water arm is unchanged** — water still freezes, the ice still looks like ice, and it still
   melts back on its own timer.
4. **The cooling reverts** after a few turns, and **no shimmer** plays over cooled land (that is
   `C_SHOW`; see the correction under edit (d) — there is no separate ice sprite). Water/ice hexes
   must still shimmer as they always did.
5. **Re-cast on an already cooled hex**: desert → steppe → grass, then wait. It must revert straight
   back to **desert**, not stop at steppe.
6. **Load an existing save** made before this patch. Old `TFrozenWaterHS` markers must melt normally
   (their `+0x0E` reads 0), and a save made *after* the patch must reload with its land markers
   intact — this is the only exercise of the new property ids `0x20`/`0x21`.
7. **The AI.** Both target gates are what AI spell targeting consults, so watch an AI wizard that
   has the spell; the widened gate may make it cast on arbitrary land.
8. **Forested / decorated hexes.** `ChangeTerrainEx`'s validate pass polls `CanChangeTerrain`
   (virtual `+0x98`), which `TILTerrainMO`/`TFixedILTerrainMO` override — a forested grass hex may
   simply refuse to cool. Confirm whether it does, and whether that reads as a bug or as scenery.
9. **The name and description** — spell book should read **Grip of Winter** with the new text.
