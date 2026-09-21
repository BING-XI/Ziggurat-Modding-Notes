# Path of Sand — adding a NEW ability (status: CONFIRMED WORKING in-game 2026-07-08)

First **from-scratch new ability** in this mod. A moving unit with *Path of Sand* dries the terrain it
leaves toward Desert, using the **same progression as the user's Desiccate** spell. Build script:
`build_scripts/build_path_sand.py`, backup `AoWEPACK.dpl.pre-pathsand`.

**Depends on `build_path_outerring.py` (`.pre-pathring`) being applied** — proc_sand reuses that mod's
`cave_stash` (writes the move's centre x/y to BSS scratch `0x558FA800`) and its ring framework. The
build aborts if the stash hook @`0x5578041E` isn't present. **Revert order: pathsand BEFORE pathring.**

## What it does
- **New ability**: id **`0x9F`**, name **"Path of Sand"**, category word `+0x20 = 0x37` (same as the
  vanilla Paths). A 4th Path alongside Life(0x45)/Decay(0x44)/Frost(0x6d). *(First tried id `0xB0`;
  registered + listed + assignable in DevEd, but did NOTHING in-game — see "ID constraint" below. `0x9F`
  is a free slot in the vanilla range and works.)*
- **Footprint**: radius 2, inner disk 100% + 25% proc on the outer ring — identical to the other three
  Paths after the outer-ring mod (reuses `proc_sand`, the same ring-gate).
- **Terrain progression** (cloned from Desiccate `FUN_5580c001`; read-once, no cascade → one stage per
  proc; Desert is terminal):
  `Grass(1)→Steppe(4)  Snow(3)→Grass(1)  Steppe(4)→Desert(2)  Wasteland(5)→Desert(2)  Dirt(C)→Steppe(4)`
  (Cloned into Sand's OWN cave `cave_sand_cb`, not calling `FUN_5580c001`, so a Desiccate revert can't
  silently turn Sand into a greening spell. If you retune Desiccate, mirror it here.)

## How it's built (two position-independent halves, no new DLL)

**A. Registration** — Path abilities are NOT a special class; the three are just
`CreateEnhancementAbility(id, name, icon) → RegisterAbility(ctrl, obj)` inside
`PassiveAb.RegisterPassiveAbilities` (`CreateEnhancementAbility` @`0x5576601c`: `TEnhancementAbility.Create`
then `obj+0xC=id`, `LStrAsg(obj+8,name)`, `obj+0x20=icon`). We **repoint the Path-of-Frost RegisterAbility
call @`0x557bc9e9`** to `cave_sandreg`, which re-issues Frost's registration (the displaced call) then
creates+registers Sand. `EBX` = the ability-control throughout the function, so `RegisterAbility(EBX,obj)`
is trivial. Name = a literal Delphi AnsiString (`refcount −1` → `LStrAsg` shares it, never frees it).
Icon = `*(0x557bcfc0)` = `0x37`, the exact word the Paths pass. New id `0xB0` is above vanilla (~0x91)
and the user's Dark Gift (0xA9); the registry is a grow-on-demand `TList` indexed by id, so a sparse
high id just adds nils. **A collision raises a LOUD "Ability already registered (n)" at startup** →
safe failure, bump `SAND_ID`.

**B. Behavior** — `TAbstractUnit.MovedTo` @`0x55780328` hard-codes each Path as
`if GetAbilityEnabled(unit,ID): map.Flood(VMT+0xd4)(…cb…,radius,…)`. We hook @`0x557804b7` (the
`MOV EDX,0x6d` starting the Frost check — reached for every NON-transported move, so Sand is an
independent 4th Path that never fires while transported). `cave_sanddispatch` does
`GetAbilityEnabled(unit,0xB0)` + a radius-2 Flood through `proc_sand`, then replays `MOV EDX,0x6d` and
falls into the Frost check. `proc_sand` = the outer-ring ring-gate (dHXtoHN vs stashed centre; inner
`jl 7`→100%, outer `Random(map,4)==0`→25%) → `cave_sand_cb`. `cave_sand_cb` clones
`PathOfDecayTerrainChange` @`0x557801c4`'s convention (`ECX=terrain*`, `EDX=field`, `RET 4`).

## Cave map (AoWEPACK.dpl)
`cave_sand_cb @5580DF00` · `proc_sand @5580DF40` · `cave_sanddispatch @5580DFA0` ·
`cave_sandreg @5580E000` · name literal `@5580E02C` ("Path of Sand", ptr `0x5580E034`).
Hooks: MovedTo `0x557804B7` (`BA 6D…`→`E9`), RegisterPassiveAbilities Frost-call `0x557BC9E9`
(`E8→RegisterAbility` → `E8→cave_sandreg`).

## Listings / "appear visually" — findings (2026-07-08)
The user asked to make new abilities show up in DevEd + the main-game unit card. Current state:
- **List membership: SOLVED by construction.** `TAbilityControl.ListAbilities` @`0x557505d4` enumerates
  the whole registry and filters by `ability+0x20 & requestedMask` (`+0x20` is a **category** word, not
  an icon). Sand's `+0x20 = 0x37` matches the vanilla Paths, so it is enumerated **wherever the Paths
  are** (the picker/card request that category). `ListAbilities` is referenced **only from the export
  table** → it exists for the EXEs (AoW.exe / AoWDevEd.exe) to call — strong sign the DevEd ability
  picker is registry-driven and will list Sand automatically. *(Confirm by opening DevEd once applied.)*
- **Name text: works.** Plain AnsiString, no library dependency.
- **Icons: none — and that's normal.** Abilities have **no icons anywhere in AoW1's UI** (text
  only); a new ability needing no art is expected behaviour, not a gap. Don't chase icon binding:
  `RegisterAbility` does call `LinkToIL(ability+0x1c)` (image-sequence list built empty in
  `TAbility.Create` @`0x5574e5f4`, linked to `AoWHSSet+0x2c`), but nothing ever draws it for
  abilities — the plumbing is a mirror of TSpell's `+0x2C`, which *is* drawn (spells do have icons).

## The "assignable but does nothing" bug — ACTUAL cause (Transport gate + terrain), and the ID red herring

The ability registered + listed + assigned in DevEd but did nothing in-game. **The real cause was TWO
things, neither of them the ability id:**
1. **The test unit had the Transport ability.** `MovedTo` gates ALL Path abilities behind a transporter
   check: @`0x55780416` `TEST AL,AL; JNZ 0x557804fe` — if the unit's army (`EBX+4`, a `TArmy`) has a
   transporter (`TArmy.Transporter(0xff) != 0` @`0x5578e00c`), it jumps **past every Path branch**
   (Life/Decay/Frost AND our Sand). This is **vanilla behaviour** — Path of Life/Decay/Frost are
   suppressed on transporter units too. A DIAGNOSTIC build (`--diag`, drops the GetAbilityEnabled gate so
   every unit terraforms) proved the cave/flood/mapping all work — every NON-transport unit dried terrain;
   only the Transport test unit didn't.
2. **Tested on desert/lava.** The Desiccate mapping only touches Grass/Snow/Steppe/Wasteland/Dirt →
   Desert(2, terminal)/Lava(9)/Water(0)/Ice(6) are no-ops by design. On a desert/lava-themed map that hid
   the effect.

**ID red herring (kept for the record so it isn't re-chased):** unit abilities ARE a width-checked bitset
(`TAbstractUnit.GetAbilitySet@0x5577f618` = `if id < unit+0xC: bit(id) else 0`), which first looked like a
hard cap at the vanilla count `0xAA`. **But it is NOT a cap** — the setter `TCustomAbilityList.SetAbSet`
@`0x5574e0bc` does `if width <= id: SetAbCount(id+1)` (auto-grows, no limit), and DevEd persists high ids
fine. So the first id `0xB0` would have worked too; the width was never the problem. **Path of Sand uses
`0x9F` anyway** — a clean free slot (keeps the registry count at `0xAA`, no compat change). Full free-id
map (from the four (Un)Register*Abilities lists) if a collision-free id is ever wanted:
`0x21, 0x38, 0x3B, 0x4E-0x55, 0x5B, 0x66-0x69, 0x6E, 0x85-0x89, 0x97, 0x9F`.

## Assignment — CONFIRMED
Assign in DevEd (check **Path of Sand**, save). In-game `GetAbilitySet(unit,0x9F)=1` →
`GetAbilityEnabled@0x5577f5e0` true → MovedTo dispatch fires. **Works on any NON-transport unit.**
A unit with the **Transport** ability did NOT terraform (vanilla Path gate). **FIXED** for all four Paths
by `build_scripts/build_path_transportgate.py` (backup `.pre-transportgate`, CONFIRMED WORKING in-game 2026-07-08):
the gate suppressed Paths whenever the *army* had a transporter (crude — the devs only had ship
transporters, which sit on water where Paths no-op). The fix hooks the `CALL TArmy.Transporter(0xff)`
@`0x55780407` → `cave_transgate` @`0x5580E060`, which zeroes the result when the transporter it found IS
the moving unit (`EAX==EBX`) — so the transporter itself leaves a trail while carried passengers stay
blocked. See that script's header for the truth table.

## Test checkpoints
1. **Game boots** → registration cave OK (first, before anything else).
2. Open DevEd → is "Path of Sand" in the ability list? (list-membership check)
3. Assign to a unit, move it → terrain dries toward Desert, radius 2 + fringe.
