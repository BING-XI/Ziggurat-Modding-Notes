# Exploration-site defender rosters — why every site of a type rolls the same units

**Status: APPLIED, UNTESTED (2026-07-29).** Root cause established by static analysis (Ghidra
symbols + capstone); the patch is applied to `AoWEPACK.dpl` but **not yet validated in-game**.
Promote to `CONFIRMED WORKING` only after a new-game test (see §6).

**Build script:** `build_scripts/build_sitedefender_vary.py` · **Backup:** `AoWEPACK.dpl.pre-sitedefvary`
**Related:** `build_scripts/build_razeroster_vary.py` — same family of defect, different function
(`Raze_CombatPredictor_Analysis.md` §13).
**Related, new:** `AI_Sites_And_Loot.md` — since 2026-09-03 **AI players actually fight these
rosters**. `build_ai_sitesearch.py` reads the same `[site+0x34]` `TDefendersArmy` through
`TUnitList.GetStrength @0x55783300` for its strength ladder, so anything that changes roster
strength also changes which sites the AI will approach.

`VA = file_offset + 0x55700C00`, ImageBase `0x55700000`.

---

## 1. The symptom

Every exploration site of the same structure type and the same **Defenders → Strength** setting
spawns an identical unit set, in every instance across the map, for a given match. Different
matches produce a different set, but it is again uniform within that match. Sites left on Strength
= **Random** additionally all resolve to the *same* strength.

## 2. The map's persistent RNG state

The map object carries a persistent RNG state field at **`map[+0x230]`**. The correct accessor is:

**`AoWE.TAoWHSMap.Random @0x5577827C`** — `EAX` = map object, `EDX` = range → `EAX` = value.

```
push ebx; push esi              ; callee-saves EBX and ESI
esi = edx (range) ; ebx = eax (map)
eax = [0x558FA040] ; test byte [eax+0x3C],8 ; jne alt   ; flag set -> plain RandInt, no state
eax = ebx ; call 0x55775608 ; test al,al ; je err       ; check fails -> returns 0
RandSeed  = [ebx+0x230]         ; install the saved seed
eax = esi ; call RandInt
[ebx+0x230] = RandSeed          ; *** WRITE THE ADVANCED SEED BACK ***
```

That write-back is the whole point: it is what makes the next caller get a different number.

The map object is reached as `[[0x558E9494]]` (two derefs). `&System.RandSeed` = `0x558FB720`.

## 3. The six roster generators — complete inventory

Taking the union of the callers of `TUnitIndexListCollection.GetRndCollection @0x557835B4`,
`FillWithRandomUnits @0x5575B160` and `PlaceRandomUnits @0x5575AEF8` gives **six** roster
generators (xref-verified in Ghidra 2026-07-29). Three are defective, in two different flavours,
and two correct implementations sit in the same codebase as reference:

| Function | VA | Seeding | Verdict |
|---|---|---|---|
| `AoWE.TStructure.GenerateRazeDefenders` | `0x5575FD1C` | `X + map[0x22C] + Y` | position-frozen — **fixed** by `razeroster_vary` |
| `City.TCity.GenerateRebelUnits` | `0x557ABCAC` | `X*10 + map[0x22C] + Y` **+ map[0x174]** | position-frozen in vanilla — **already fixed** by `build_razebattle_tower.py` |
| `City.TCity.GenerateDefenders` | `0x557AB6DC` | `TAoWHSMap.Random(map, 0xFFFFF)` | **correct** |
| `PrdPlace.TProductionPlace.GenerateDefenders` | `0x557BF1A8` | `TAoWHSMap.Random(map, 0xFFFFF)` | **correct** |
| `ExploreS.TExplorationSite.GenerateDefenders` | `0x557C1FC0` | `RandSeed = map[0x230]` | never-advanced — **fixed here** |
| `Dungeon.TDungeon.GeneratePrisoners` | `0x557C5C2C` | `RandSeed = map[0x230]` | never-advanced — **fixed here** |

> ⚠ An earlier revision of this doc said "four generators" and claimed no remaining instances. That
> was derived from the `GetRndCollection` callers alone and **undercounted** — the two `TCity`
> generators reach the fill/place helpers without going through `GetRndCollection`. Always union
> all three helpers' xrefs.

## 4. The bug

`TExplorationSite.GenerateDefenders` inlines a **raw read** of the persistent state and never
advances it:

```
557C1FCB  A1 94 94 8E 55        mov eax,[0x558E9494]     ; -> ptr to map control   [.reloc]
557C1FD0  8B 00                 mov eax,[eax]            ; -> the map object
557C1FD2  8B 80 30 02 00 00     mov eax,[eax+0x230]      ; read persistent RNG state
557C1FD8  8B 15 20 B7 8F 55     mov edx,[0x558FB720]     ; &System.RandSeed         [.reloc]
557C1FDE  89 02                 mov [edx],eax            ; install -- never written back
```

then:

```c
if (site[0x30] == 4) site[0x30] = RandInt(3) + 1;       // Strength "Random" -> 1..4
coll = GetRndCollection(site[8]->[0x64]);                // roster template for this site type
FillWithRandomUnits(list, site[0x34], 4, ..., site[0x30] * 0x32);   // strength = tier * 50
```

Every site installs the identical seed and replays the identical draw sequence ⇒ identical tier,
identical template pick, identical units. It varies between matches only because `map[+0x230]`
starts from a per-game value.

`TDungeon.GeneratePrisoners` is the same code with the strength byte at `+0x3C` and the collection
at `[site+8]+0x68`.

**Field map:** `site[+0x30]` = defender strength byte (**0 = none**, 1–3 = fixed, **4 = the
editor's "Random"**), `site[+0x34]` = target list, `site[+0x64]` (on the resource) = defender
collection. Dungeon prisoners: `+0x3C` / `+0x38` / `+0x68`. Combat strength = `tier * 0x32` (50).

## 5. When it runs

`ExploreS.TExplorationSite.NewDay @0x557C20A4` is the **only** caller:

```c
TStructure.NewDay(self);
if (map[0x174] == 1 && site[0x30] != 0)
    GenerateDefenders(self);
```

`map[+0x174]` is the game-day counter (the same field `razeroster_vary` folds into the raze seed),
so rosters are rolled **once, on game day 1**, for every site in turn — each re-installing the same
constant seed.

> **Corrects an earlier note.** `Investigation_AI_Item_Pickup.md` says "site defenders are spawned
> *by* `ExecuteSearch` from stored data". The *stored data* is produced here, on day 1;
> `ExecuteSearch` only spawns what already exists. Items are separate — stocked by
> `TExplorationSite.Generate @0x557C2944`, which seeds correctly via `TAoWHSMap.Random`, so
> treasure already varies per site.

## 6. The patch

Do what the correct sibling does: take the seed from `TAoWHSMap.Random`, which advances the shared
state.

**Mode `vary` (applied).** Hook the 6-byte `mov eax,[eax+0x230]` — at that point **`EAX` already
holds the map object**, loaded by the two preceding instructions which are left in place:

| Hook VA | orig | new | cave |
|---|---|---|---|
| `0x557C1FD2` | `8b 80 30 02 00 00` | `e9 29 04 05 00 90` | `0x55812400` (15 B) |
| `0x557C5C3A` | `8b 80 30 02 00 00` | `e9 01 c8 04 00 90` | `0x55812440` (15 B) |

```
mov edx, 0xFFFFFF
call 0x5577827C          ; TAoWHSMap.Random -> fresh value, advances map[0x230]
jmp  <resume>            ; into the existing "mov edx,[&RandSeed]; mov [edx],eax"
```

**Mode `keep`** (implemented, not applied): hooks *after* the tier roll instead
(`0x557C1FF4` / `0x557C5C5C`, `mov eax,[esi+8]; mov eax,[eax+0x64|0x68]`), preserving today's
strength outcome and varying only the unit set. Needs the PIC delta trick — the map pointer is not
live there. Switch with `--undo` then `--apply --mode keep`.

### Verified before writing
- **`.reloc` clean at both hook sites.** Nearest entries are `0x557C1FDA` / `0x557C5C42` — the
  disp32 of the *following* `mov edx,[0x558FB720]`, deliberately left in place. (Displacing a
  reloc-bearing operand is the classic "works one launch, crashes the next" trap.)
- **Cave space measured on the LIVE DLL:** one contiguous zero run `0x55812219..0x558E7918`
  (874,239 B). Base `0x55812400` sits well inside it.
- **PIC:** mode `vary` introduces **no absolute data references at all** — rel32 call + rel32 jmp
  only. Rebase-safe with no delta anchor.
- **Registers:** `TAoWHSMap.Random` preserves `EBX`/`ESI`, returns in `EAX`, clobbers `EAX/EDX/ECX`.
  `ESI` = Self is live across the cave and survives.

### Test procedure (to promote this doc to CONFIRMED)
Start a **new game** — rosters are rolled on day 1, so an existing save keeps what it already
generated. Find two or more sites of the same type (e.g. two Crypts) and compare their garrisons.
Also check a dungeon's prisoner reward across two dungeons.

## 7. Landmines & consequences

- **⚠ Strength now varies too** in mode `vary`, because the tier roll happens *after* the seed
  install. That is what the editor's "Random" strength dropdown implies, and it is currently broken
  the same way — but it changes the strength distribution of existing maps. Use `--mode keep` to
  preserve the old strength behaviour.
- **⚠ Downstream RNG drift.** Advancing `map[+0x230]` once more per site shifts every later
  consumer of the map RNG, so a game started under this patch will not reproduce a vanilla draw
  sequence. Harmless for a new game, and it is what the correct sibling already does.
- **MP-safe.** `NewDay` is a synchronised turn event and every peer makes the same calls in the same
  order, exactly as the existing correct callers (`TProductionPlace.GenerateDefenders`,
  `TExplorationSite.Generate`) already do. No new desync surface. All peers need the patched DLL.
- **`TAoWHSMap.Random` has two non-default paths** — a map flag (`byte[[0x558FA040]+0x3C] & 8`)
  that skips the saved-seed machinery, and an internal check that returns 0. Both are pre-existing
  behaviour shared with the item roller, so the patch takes on no new risk there.
- **Revert:** `--undo` removes the feature surgically (restores the vanilla bytes, zeroes the caves)
  **without touching any `.pre-*` backup**, so features applied later survive. Prefer it over
  restoring `AoWEPACK.dpl.pre-sitedefvary`, which is only safe while this is the newest layer —
  check with `ls -t AoWEPACK.dpl.pre-* | nl` before ever doing a backup restore.

## 8. Still open

- ~~`City.TCity.GenerateRebelUnits` is unfixed~~ — **wrong, and corrected 2026-07-29.** In vanilla
  it does seed from `GetX()*10 + map[0x22C] + GetY()` (position-frozen), but our live DLL **already
  patches it**: `build_razebattle_tower.py` hooks the seed add at `0x557ABCD5` into
  `cave_cityseed @0x5580D2E0`, which replays the displaced `add ebp,[eax+0x22c]` and appends
  `add ebp,[eax+0x174]` — the day counter. Its own comment: *"+= day → city mob (raze militia +
  rebels) re-rolls daily"*. Because `TCity.GenerateRazeDefenders` is just `GenerateRebelUnits`
  plus `ret 1`, that single hook covers **both** the city raze militia and the rebellion mob.
  **⚠ How the wrong claim happened — the trap to remember:** it came from reading the *Ghidra
  decompile*, which still shows the unhooked body. **The Ghidra project holds the PRISTINE VANILLA
  `AoWEPACK.dpl`, not the live one.** Re-measured 2026-08-03 against both files: Ghidra shows
  `SUB EAX,0xa` at `0x557710F3` (road build cost — pristine `83 e8 0a`; live is `83 e8 05`),
  `MOV AL,0xa`/`MOV AL,0x5` at `0x55725C36` (live: `0x18`/`0x8`), `MOV EDX,0x6D` at `0x557804B7`
  (no Path of Sand), and **no code at any cave address** (`0x5580C880`, `0x5580D2E0`, `0x5580F700`,
  `0x55810000` are all zero in pristine and all populated in live). Live differs from pristine in
  **518 byte-runs** (493 CODE / 24 DATA / 1 `.rsrc`), and Ghidra has none of them.
  **So Ghidra is a valid vanilla reference — and is zero evidence about what is installed.** Never
  conclude "unpatched" from Ghidra; byte-check the live file and run
  `grep -rl "<VA>" build_scripts/`. Corollary: data tables read out of Ghidra (movement costs at
  `0x558E84FC`, rank stat tables) are **vanilla numbers, not the installed Ziggurat-rebalanced
  ones** — read those from the live file.
  *(A 2026-07-29 note here claimed the image carried the Ziggurat road-cost change. It did not;
  that calibration was simply wrong. The lesson it was attached to — Ghidra ≠ live — stands.)*
- Whether `[map+0x230]` is also consumed by map generation itself (which would make the drift in
  §7 visible at worldgen) has not been traced. Irrelevant for in-game day-1 rolling, but worth
  knowing before touching the editor side.
- **Crusade is unrelated** — see `Investigation_Crusade_Spell.md`. It uses `TAoWHSMap.Random`
  correctly everywhere; its repetitiveness is hardcoded table size, not a seeding defect.
