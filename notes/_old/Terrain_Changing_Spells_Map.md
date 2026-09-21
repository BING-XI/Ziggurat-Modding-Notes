# Terrain-changing spells — verified map (AoWEPACK.dpl)

> Part of the terrain/map system — **start at `Terrain_System_INDEX.md`** for the map of these docs.

**Status: INVESTIGATION / VERIFIED VANILLA (2026-07-07).** One patch applied (Ice Storm lava→wasteland,
APPLIED-UNTESTED — see bottom). Decompiled *and*
disassembled from Ghidra (`AoWEPACK.dpl`, preferred base `0x55700000`, rebased at runtime →
any cave must be position-independent per `[[aow1-dpl-rebasing]]`). Goal of the work: broaden these
spells' terrain effects. User will supply explicit desired cases; Ice Storm lava→wasteland already
approved-in-principle (unbuilt).

## Terrain byte values (user-provided, cross-checked against the code)
```
0 Water        5 Wasteland    A Cave Water
1 Grass        6 Ice          B Cave Wasteland(?)
2 Desert       7 EarthWall    C Dirt
3 Snow         8 RockWall     D Cave Ice
4 Steppe       9 Lava
```
Cross-checks from code: Fire Storm makes Desert→`9`(Lava); Ice Storm makes Water→`6`(Ice), land→`3`(Snow);
Fire Storm melts Ice(`6`)→Water(`0`) and CaveIce(`D`)→CaveWater(`A`). All consistent with the table.

## The dispatch mechanism
Each storm overrides virtual `ChangeStormTerrain(Self=EAX, mapField=EDX, terrainByte*=ECX)` — called
per affected hex by the storm update loop, mutates the terrain byte in place through ECX (`RET 4`,
Delphi register call). Global-target spells (`THealingShowersTE`, `TFreezeWaterTE`, `TRejuvenateTE`)
have `ChangeTerrain` with the same in-place-byte pattern. The write sticks + redraws via the normal
storm/spell path (proven by vanilla in-game behavior). `TIceStorm.ChangeStormTerrain` xrefs are from
the VMT (`0x55913dc0`, `0x557cb558`) — pure virtual dispatch.

## Verified current mappings

### Ice Storm — `TIceStorm.ChangeStormTerrain` @ `0x557cced4`
- Water(0) → Ice(6)
- Ice(6) → keeps ice, spawns/updates a `TFrozenWaterHS` structure (random countdown at `+0xc`,
  caster tag at `+0xd`) — same sub-branch as Freeze Water.
- **everything else → Snow(3)**  ← lava(9) currently becomes snow here
Disasm: `else` = `MOV byte ptr [ECX],0x3` @ `0x557ccef0`.

### Fire Storm — `TFireStorm.ChangeStormTerrain` @ `0x557cd4f0` → helper `0x5580be74`
- Ice(6) → Water(0)          (`MOV [ECX],0` @ `0x5580be80`)
- CaveIce(D) → CaveWater(A)  (`MOV [ECX],0xa` @ `0x5580be89`)
- Desert(2) → Lava(9)        only if `GetArmyHS(hex)==0` AND the roll at `0x5580bea8` is non-zero
  (~75%); `MOV [ECX],0x9` @ `0x5580beb4`
- returns original terrain in AL. `RET` (0).

⚠ The whole helper at `0x5580be74` is a **modded cave with no owning build script** — it does not
exist in the pristine DLL, where `TFireStorm.ChangeStormTerrain` is just `if *p==6 then *p:=0`.
Treat it as orphaned pre-convention work; there is nothing to re-derive it from if it is lost.
Its 75% roll drew from the raw per-process generator until 2026-08-31, when
`build_rng_lockstep.py` retargeted it to the synchronised one (`Zig notes/RNG_Lockstep_Rule.md`);
the roll is otherwise unchanged, and the cave itself was not rebuilt.

### Healing Showers — `THealingShowersTE.ChangeTerrain` @ `0x557a1b8c` → helper `0x5580bf2f`
- Desert(2) → Steppe(4)
- Steppe(4) → Grass(1)
- Wasteland(5) → Steppe(4)
- **Lava(9) → Wasteland(5)**  ← already cools lava (final `SUB AL,4; JZ; MOV [ECX],5` @ `0x5580bf50`)
- everything else unchanged. `RET` (0).

### Death Storm — `TDeathStorm.ChangeStormTerrain` @ `0x557cd304`
- Any land except Water(0)/Ice(6) → Wasteland(5). `RET 4`.

### Divine Storm — `TDivineStorm.ChangeStormTerrain` @ `0x557cd6dc`
- Any land except Water(0)/Ice(6) → Grass(1). `RET 4`.

### Blast Storm — `TBlastStorm.ChangeStormTerrain` @ `0x557ccab0`
- **empty** — changes no terrain (damage/knockback only). `RET`.

### Grip of Winter (ex-Freeze Water) — `TFreezeWaterTE.ChangeTerrain` @ `0x5579e884`
> ⚠ **Modded since 2026-09-01** (`build_gripofwinter.py`, applied-untested): the spell is now
> castable on **any** hex, also cools **Desert(2)→Steppe(4)→Grass(1)→Snow(3)** one step per
> cast, and the land change **reverts** on the same timer as the ice. What follows is the
> vanilla lifecycle, which the water arm still follows exactly.
> Full design, the eight edit sites and the in-game checklist: **`GripOfWinter_Design.md`**.

Vanilla lifecycle (2026-07-24):
`TFreezeWaterTE.Process` (`0x5579e994`) plays the twinkle animation/sound if observed, then calls
map VMT **+0xD4** (→ `THSMap.ChangeTerrainEx`, see "The two write paths" below) with radius 1 and
two callbacks:
- **ChangeTerrain cb** (`0x5579e884`), called per hex during the mutate pass; only if
  `GetArmyHS(hex)==0`:
  - Water(0) → Ice(6); CaveWater(A) → CaveIce(D)
  - already Ice(6)/CaveIce(D) → find the hex's `TFrozenWaterHS` and *refresh* it:
    countdown `+0xC = (Random(0xB)−5)/5 + 3` (1–4 turns), owner `+0xD` = caster.
- **TerrainChanged cb** (`0x5579e900`), called per hex in the commit pass with the OLD terrain:
  if the hex is now 6/D and wasn't before → create `TFrozenWaterHS`, `PlaceHX`, countdown
  `+0xC = (Random(0x20)−5)/5 + 3` (2–8 turns), owner `+0xD` = caster.

**`TFrozenWaterHS`** (AoWE, class ptr `0x55714774`) — the "temporary ice" marker:
- `NewTurn` (`0x55764b98`): only on the owner's turn, `dec +0xC`; at 0 → `MeltIce`.
- `MeltIce` (`0x55764ae0`): hex Ice(6) → map VMT **+0xD0** ChangeTerrainEx-single back to
  Water(0); CaveIce(D) → CaveWater(A); any other terrain → just frees itself. So melting is
  itself a normal terrain change (transitions, roads, bridges all update).
- `TerrainChanged` (`0x55764b6c`, virtual +0xA0 pass): if the hex's terrain is no longer 6/D
  (someone else melted it, e.g. Fire Storm) → frees itself. No leak.

### Rejuvenate / **"Desiccate" (user's mod)** — `TRejuvenateTE.RejuvenateTerrain` @ `0x5579f3e4` → helper `0x5580c001`
- Grass(1) → Steppe(4); Snow(3) → Grass(1); Steppe(4) → Desert(2); Wasteland(5) → Desert(2);
  Dirt(C) → Steppe(4). (Reads original byte for each independent `if`, no cascade.)
- **In the user's mod this spell is repurposed as "Desiccate" — it dries terrain toward Desert.**
  The drying direction seen above is intentional (that's the mod). Do NOT "fix" it back to a
  greening spell.

### Flood — global enchantment, `TFloodControl` @ AoWEPACK (analyzed 2026-07-24)
Not a storm: `TFloodEnchantment` (Activate `0x557f1bec`, Deactivate `0x557f1ca8`, delayed by
`DaysBeforeActive` `0x557f19a8`) drives `TFloodControl.Flood` (`0x557f13d0`) / `.Restore`
(`0x557f15cc`). **It bypasses ChangeTerrainEx entirely** — raw byte writes + per-field
`TMapField.TerrainChanged`, bracketed by `LockMapChangedEvent`/`Unlock` + `InvalidateMap`.

`Flood` (surface level only, interior hexes):
1. **Scan pass**: for every Water(0) hex, walk its 6 neighbours. A neighbour is *floodable* if
   its terrain ∉ {0, 6 Ice, F} and its overlay byte (`field+0x15`) ∉ {0, 2, 7} (those overlay
   types shield the hex — recorded raw, semantic names unverified), or if terrain==0 with
   overlay==5. For floodable hexes: if not already recorded and **no `TStructure`** on the field
   (`FindNoneTransparentHS`) → save `{terrain, overlay}` into the control's 2-byte-per-cell
   array (`ctl+0x10`, width `ctl+8`). If the hex's overlay ∈ {4,5} → **find the road-family HS
   and free it** (roads drown; overlay 4/5 is how the road family registers on the field).
2. **Apply pass**: every recorded cell → `field+0x14 = 0` (Water) + `TMapField.TerrainChanged`.

⚠ **No army check** — unlike Freeze Water and the storms, Flood happily puts water under a land
army (only structures block it). Also note the coast advances only 1 ring per activation-scan
from *pre-existing* water (the scan reads terrain live but records before applying).

`Restore` (on Deactivate):
1. Every recorded cell whose terrain is still Water(0) **or Ice(6)** → write the saved terrain
   byte back + `TerrainChanged`. (Ice counts so a frozen flood still un-floods.)
2. For cells with a saved overlay: overlay ∈ {4,5} → re-place the road via the road control
   (`AoWHSSet+0x1C`, virtual +0x50); any other overlay → scan the resource registry for
   ClassID `0x20167` resources whose `TTerrainList` is single-terrain matching
   {restored terrain, saved overlay}, collect into a TList, pick one with the guarded
   `TAoWHSMap.Random`, place via virtual +0x68 (rebuilds forests/decorations).

### The two write paths (how any terrain change actually lands) — 2026-07-24
Full consumer-side chain (hexagon re-blend, water masks, roads, bridges) is in
`Hex_Transition_System.md`. Producer side, there are exactly two idioms:

**A. The transactional driver — `THSMap.ChangeTerrainEx` (HSEPack `0x5560c888`; single-hex
wrapper `0x5560c688`; map VMT +0xD0 single / +0xD4 area-with-callbacks).** Three passes over a
hex-spiral of the given radius, under `LockTerrainChangedEvent`:
1. *Mutate*: save old `{terrain, overlay}` per hex, run the caller's ChangeTerrain callback on
   local copies, write results raw into `field+0x14/+0x15`, save new pair.
2. *Validate/rollback*: `TMapField.CanChangeTerrainEx` (`0x55607bb0`) asks every HS on the field
   via virtual **+0x98 `CanChangeTerrain`** (overridden by `TStructure` `0x5575ec1c`, `TArmyHS`
   `0x55790dac`, and the terrain-adaptive MO family `TILTerrainMO`/`TFixedILTerrainMO`, HSEPack
   `0x55618840`/`0x55618ca8`) — ALL must agree; a veto restores the old bytes. **`TMountainMO`
   (`0x557a2ddc`) is `mov al,1; ret` — mountains explicitly ALLOW terrain changes under them**
   (they re-skin or self-delete instead; see Hex_Transition_System.md § Mountains).
   Validation runs with the whole area already mutated, so vetoes see the new neighbourhood.
3. *Commit/notify*: for surviving hexes re-write the new bytes, call
   `TMapField.TerrainChanged` (re-cache + 6-neighbour notify → transitions/roads/bridges), and
   invoke the caller's TerrainChanged callback with the old value (spell post-work, e.g.
   spawning `TFrozenWaterHS`). Then unlock + `TerrainChangedRad` rect invalidate.

The AoW wrappers `TAoWHSMap.ChangeTerrain`/`Ex` (`0x55778d84`/`0x55778dcc`) do one extra thing
first: **reseed the VCL `RandSeed` from the synchronized game RNG** (`Random(0xFFFFFF)`), so the
cosmetic `RandInt(3)` transition-variant picks during the redraw are identical on all networked
clients despite using the non-lockstep UI RNG.

**B. Raw write + `TMapField.TerrainChanged` (`0x55607cb4`)** — what Flood/Restore and the storm
loops do per hex. No CanChangeTerrain veto pass, no callbacks; caller takes responsibility.
Writing `field+0x14` *without* calling `TerrainChanged` is the bug idiom: caches, transitions,
roads, and bridges all go stale (see Hex_Transition_System.md).

- Map-field terrain byte lives at **field + 0x14**, overlay at **+0x15** (0xFF = none).
- `PlaceTerrain` @ `0x55778eec` — editor-side setter, same family.

## Raise Terrain / Level Terrain (investigated 2026-07-07)
There is **no "Lower Terrain" spell** in AoW1 (searched — only `TLowerIsometricHexagon`, a renderer,
and `SysUtils.LowerCase`). The elevation pair is **Raise Terrain** (spell index `0x13`) and **Level
Terrain** (spell index `0x12`). Mountains are *map objects*, not a terrain byte — that's why there's
no "mountain" terrain value. (`GetMapLevel(field+0x22)` = the surface-vs-underground map layer, NOT
continuous elevation.)

### Raise Terrain — `TRaiseTerrainTE.RaiseTerrain` @ `0x557a3280` (Process @ `0x557a34b8`)
Does **not** change the terrain byte. Over a ~1-radius hex area (`InitHNWalk`, `local_24 <= 1`), for
each field that passes spell `0x13` `ValidTargetMapF` (vtable+0xb4): finds the `TRaisedMountainResource`
(resource type `0x2016b`, terrain-list `UsedTerrain==1`), calls `RestoreTerrain(field)`, then creates
a **`TRaisedMountain`** multi-hex map object and `PlaceHX`es it with an `TImageSequenceAnimation`
(rise animation). The mountain gets a random countdown at `MO+0x1e = (Random(0xb)-5)/5 + 3`, owner at
`+0x1d` — i.e. **temporary** (times out, then `TRaisedMountain.RestoreTerrain` puts the old terrain
back). Broadening handles: radius (`local_24 <= 1`), the countdown formula (permanent = force high),
the resource lookup gate.

> **NOT bugged — verified in-game (user test 2026-07-07). Do not "fix".** The selection loop
> (`0x557a3340`) is terrain-blind (picks one fixed `TRaisedMountainResource`), which led me to
> *infer* it places grass mountains / forces grass onto the hex. **That inference was wrong** — the
> forcing/rendering logic lives in `HSEPack.dpl` (not analyzed), and the single resource evidently
> renders per-underlying-terrain by itself. User tested unmodified vanilla (live `RaiseTerrain` is
> byte-identical to `AoWEPACK_original_backup.dpl`) and mountains already match the terrain. A
> speculative `build_scripts/build_raiseterrain_mtn.py` (`ChangeTerrainEx` fix-up cave) was written
> but **only dry-run, never applied** (no `.pre-raisemtn` backup). Keep it shelved unless a real
> per-terrain mismatch is ever demonstrated in-game.

#### APPLIED PATCH — Raise Terrain on lava → 50% dirt + raise-glow, no mountain (build_raiseterrain_lavadirt.py)
**Status: CONFIRMED WORKING IN-GAME (2026-07-08)** — 50% lava→dirt, no mountain, green raise-glow, dirt
flips in sync with the glow (frame 9), no popup/exception. All validated by the user.
Backup `AoWEPACK.dpl.pre-rtlavadirt`. Lava is already a valid Raise Terrain target (ValidTargetMapF
rejects only 0/6/A/D), but mountain placement fails on lava so vanilla just wastes the cast. Now each
**lava(9)** hex in the area has a **50% chance → dirt(0xC)** with the **green "raise" glow** but **no
mountain**; non-lava hexes keep normal mountain behaviour (per-hex rule, user choice).
- Redirect @ `0x557A333E` (`XOR EAX,EAX; MOV ESI,[EBP+8]`, 5 B, injected right after `ValidTargetMapF`
  passes / before the mountain-resource lookup) → `cave_lavadirt` @ `0x5580DB60` (88 B).
**TWO patches (timing fix 2026-07-08):** vanilla places the mountain hidden immediately and reveals it
at glow **frame 9** (`NewFrameRaiseTerrainAnimation` @`0x557A31B0`). First cut changed terrain up front
→ dirt appeared before the glow peaked. Fixed by **deferring** the terrain flip into that same frame-9
callback, so dirt and glow land together.
- **cave_lavadirt** @ `0x5580DB60` (redirect @ `0x557A333E`, 5 B): `field=[ESP+8]`; terrain(`+0x14`)≠9 →
  replay `XOR/MOV`, `jmp 0x557A3343` (mountain). Lava → `RandInt(2)` (`0x55701080`); nonzero → `jmp
  0x557A3498` (nothing); 0 → `mov ebx,[esp+8]` (field), `jmp 0x557A3414` (vanilla raise-glow block:
  builds the glow anim, wires `NewFrameRaiseTerrainAnimation` with data=EBX=field, `PlaceHX`es it).
  **No terrain change here.** EBX=field (valid non-mountain ptr) keeps the block's mountain callbacks
  safe no-ops.
- **cave_dirtdelay** @ `0x5580DBD0` (redirect @ `0x557A31E9` = `MOV EBX,EAX; MOV EDX,0x2016A`, 7 B):
  augments the frame callback. On entry `EAX=field` (anim's hex), `EDI=frame`. If `frame==9` AND
  `field+0x14==Lava(9)` → change the hex to dirt using the field's own coords (`+0x10`=x,`+0x11`=y,
  `+0x12`=level, confirmed via `TIceStorm.StormTerrainChanged`), then replay the 2 displaced instrs,
  `jmp 0x557A31F0`. Map via call/pop-delta on `0x558E9494` (rebase-safe). Shared with real mountains,
  but their hex is never lava → no-op for them, and `EDI`(frame) stays intact so their frame-9 reveal
  is unaffected.
- **Random-guard fix (2026-07-08), cave_dirtdelay @ `0x5580DC20` (moved off `0x5580DBD0`):**
  `ChangeTerrainEx` from the animation callback trips two engine limits in turn:
  1. **"Invalid AoWHSMap.Random use"** — the `vtable+0xD0` terrain change calls `AoWHSMap.Random`
     (`0x5577827C`) to pick a variant; its guard errors when `(*0x558FA040)+0x3c & 8 == 0 &&
     !GetSynchronised` (i.e. from render context). *(A first attempt called the "lower"
     `HSEngine.THSMap.ChangeTerrainEx` `0x557025D4` to dodge it — WRONG: that fn takes **7** stack
     params (`RET 0x1c`) vs the `vtable+0xD0` fn's **4**, so 4-arg calls corrupt the stack →
     **"Exception during AoWHSMap.NewFrame"** and no change.)*
  2. **FIX:** keep the working `vtable+0xD0` call, but temporarily **set the guard's own flag**
     `(*0x558FA040)+0x3c |= 8` (→ `Random` takes the unguarded raw-`RandInt` path, no popup) and
     restore the original byte after. Both globals (`*0x558FA040` for the flag, `*0x558E9494` for the
     map) read via one call/pop-delta anchor. `EBX` holds the flag object across the call (callee-saved)
     for the restore; `ESI`=vtable (non-zero) keeps the vanilla `CMP ESI,resource` a safe skip.
- Script re-applies over the earlier up-front-conversion cave. Same `.pre-rtlavadirt` backup — ⚠ **since
  moved to `Modding Resources/backups/` and now 40 layers deep**, see revert note below.
- **Verify in-game:** cast Raise Terrain on a lava field → ~half the lava hexes become dirt, none get
  mountains; casting on grass still raises mountains (and converts any lava hexes in the ring).
- Revert: ⚠ **the backup exists but is 40 features deep — not usable.**
  `AoWEPACK.dpl.pre-rtlavadirt` was **moved** (not deleted) to
  `Modding Resources/backups/AoWEPACK.dpl.pre-rtlavadirt` on 2026-07-29/30; it is layer **6 of 47**, so
  restoring it would destroy 40 later features. `build_raiseterrain_lavadirt.py` has no `--undo` mode, so
  removing this feature means undoing it surgically: restore the redirect at the documented hook site to
  its original bytes and zero this script's cave range, verify-before-write.

### Level Terrain — `TLevelTerrainTE.LevelTerrain` @ `0x5579f068` (Process @ `0x5579f16c`)
Over a ~1-radius area (`local_20 < 2`), for each field passing spell `0x12` `ValidTargetMapF`, **only
if no army on the hex** (`GetArmyHS==0`):
1. `ClearTerrain(x,y,...)` — removes overlay/terrain map-objects on the hex (raised mountains, walls,
   etc.).
2. If `field+0x14 == 7` (**EarthWall**) → `ChangeTerrainEx(..., 0xC=Dirt, ...)` (vtable+0xd0). So it
   converts EarthWall(7) → Dirt(C).
It does **not** touch RockWall(8), Lava, or other terrain bytes. Broadening handles: the `==7` test /
`0xC` target (e.g. also flatten RockWall(8)→Dirt, or lava→wasteland), the no-army gate, the radius.

## Patch-space notes (for when explicit cases arrive)
- In-place value swaps (e.g. Ice Storm's `else` 3→5 for lava only) need carving the lava case out of
  the catch-all → a small **code cave** (register-relative on ECX only → position-independent, easy).
- The three shared helpers (`0x5580be74` FireStorm, `0x5580bf2f` HealingShowers, `0x5580c001`
  Rejuvenate) sit in a `0x5580b***` code region — confirm surrounding free space before extending
  them in place; otherwise redirect to a fresh cave.
- Frozen-water sub-branches use absolute globals (`[0x55714774]`, `[0x558e9494]`) — those specific
  branches are NOT position-independent; avoid relocating them, borrow them in place.

## APPLIED PATCH — Ice Storm: Lava(9) → Wasteland(5)  (build_icestorm_lava.py)
**Status: CONFIRMED WORKING (2026-07-07).** Backup `AoWEPACK.dpl.pre-icelava` — ⚠ **moved to
`Modding Resources/backups/` on 2026-07-29/30 and now 41 layers deep**, see the revert bullet below.
In-game: lava turns to wasteland; see the expected concentric-ring note below.
- Redirect @ `0x557CCEF0`: the catch-all `else` (`C6 01 03 EB 44` = `mov [ecx],3; jmp 0x557CCF39`)
  → `E9 2B0C0400` (`jmp cave_icelava`).
- `cave_icelava` @ `0x5580DB20` (20 B): `cmp al,9; jne _snow; mov [ecx],5; jmp 0x557CCF39;
  _snow: mov [ecx],3; jmp 0x557CCF39`. AL = terrain (from `MOVSX EAX,[ECX]` @ `0x557CCEDD`, intact);
  ECX = live map-field terrain byte. Position-independent (AL/ECX + rel32). Cave sits above the
  fire-heal caves (end `0x5580DB16`) → coexists with `build_firefeed.py` either order.
- Net: Ice Storm turns lava→Wasteland instead of Snow; all other terrains unchanged. Water→Ice and
  the Ice→FrozenWater branch untouched.
- **Verify in-game:** cast Ice Storm over a lava hex → it should become Wasteland (not Snow).
  Confirm non-lava land still becomes Snow and water still becomes Ice. Then mark CONFIRMED WORKING.
- Revert: ⚠ **the backup exists but is 41 features deep — not usable.** `AoWEPACK.dpl.pre-icelava` was
  **moved** to `Modding Resources/backups/AoWEPACK.dpl.pre-icelava` on 2026-07-29/30; it is layer
  **5 of 47**. `build_icestorm_lava.py` has no `--undo` mode; to remove the feature, restore the
  `0x557CCEF0` redirect to its original `C6 01 03 EB 44` and zero the `cave_icelava` / `cave_iceroll`
  ranges (`0x5580DB20`, `0x5580DB40`), verify-before-write.
- **Also (vanilla, no patch):** Healing Showers already turns lava→Wasteland.

### Expected behavior: concentric ring (outer wasteland, inner snow) — CONFIRMED, accepted by user
In-game a lava area becomes a **wasteland ring around a snow core**, because Ice Storm applies its
terrain change **more than once** to central hexes:
- **Ice Storm inherits `TBlastStorm.UpdateStorm`** (`0x557ccac0`; confirmed via vtable — Ice Storm's
  UpdateStorm slot `0x557cb54c` → BlastStorm's, ChangeStormTerrain slot `0x557cb558` → its own).
- `TBlastStorm.UpdateStorm` runs the area effect at **4 frames with growing radius**: frame 8→r1,
  12→r2, 18→r3, 22→r4. Each pass covers the whole disk and runs `ChangeStormTerrain` per hex. So a
  center hex is hit ~4×, an edge hex 1×.
- Patch chain `lava(9)→wasteland(5)→snow(3)` is **non-idempotent**: edge (1 pass) stops at wasteland;
  center (repeated) goes wasteland→snow. Vanilla never showed a ring because it was idempotent
  (everything→snow, snow→snow). **Not a patch bug** — same update is shared by Blast/Death/Divine.
- User verdict on the ring: "looks cool, acceptable."

### PATCH 2 — per-proc skip gate (cave_iceroll) — 25% skip, APPLIED (2026-07-07)
To widen the surviving wasteland, added a **"do nothing" roll on each proc of each hex**. Skip chance
= `1/SKIP_DENOM` (script knob; **currently 25%**, `SKIP_DENOM=4`; started at 50% then user reduced to
25% 2026-07-07 — 50% part confirmed working in-game, 25% awaiting retest). Same
`build_icestorm_lava.py` (now 4 patches); both patches shared the `.pre-icelava` backup, which is now
relocated and 41 layers deep (see above — not a usable revert). Re-tune by editing `SKIP_DENOM` (add new
value to `KNOWN_DENOMS` so it re-applies in place) + `--apply` — this rewrites the cave in place and needs
no backup.
- Entry redirect @ `0x557CCEDD` (`MOVSX EAX,[ECX]; TEST AX,AX`, 6 B → `E9 rel32`+NOP) → `cave_iceroll`
  @ `0x5580DB40` (32 B): `RandInt(SKIP_DENOM)` via thunk `0x55701080` (EAX=N→0..N-1); on 0 → `jmp`
  epilogue `0x557CCF39` (no change); else → replay MOVSX/TEST, `jmp 0x557CCEE3` (normal flow). ECX
  preserved across RandInt; rebase-safe (reg + rel32).
- Wraps the whole function, so it thins **every** Ice Storm terrain effect by ~50%/proc (water→ice,
  land→snow, lava→wasteland→snow, frozen-water spawns). Because center hexes get ~4 procs and edges 1,
  the net is: fewer follow-through steps → more surviving wasteland on lava (some center hexes stay
  wasteland or even lava) — patchier/organic.
- **Verify in-game:** Ice Storm on lava should now leave a wider, more broken-up wasteland area.
