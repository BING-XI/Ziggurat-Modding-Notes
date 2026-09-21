# Missile trajectories & interception by intervening units / obstacles

**Status: RE-only, no patch applied (2026-08-09).** Everything below is read off the binaries
(capstone on `AoWTCPCK.dpl`, Ghidra on the vanilla `AoWEPACK.dpl`). Nothing here has been changed;
nothing needs an in-game test to be *true*, but the tuning claims (how often a shot is actually
intercepted in practice) are derived from the formulas, not measured in play — flagged where it
matters.

> ⚠ **This supersedes the "size does NOT block missiles / no LOS code exists" verdict** in
> `Investigation_Combat.md` FEATURE 1 and `Investigation_INDEX_2026-07-08.md` #7. That verdict was
> derived entirely from `AoWEPACK.dpl` and is correct **only for auto-resolve**. Manual tactical
> combat has a complete, per-hex, probabilistic missile-interception system — it just lives in
> **`AoWTCPCK.dpl`**, which had not been searched.

---

## 0. The one thing to know first — there are TWO ranged systems

| | manual tactical combat | auto-resolve / "fast combat" |
|---|---|---|
| module | **`AoWTCPCK.dpl`** (`CombatTE`, `AoWTC` units) | **`AoWEPACK.dpl`** |
| driver | `CombatTE.TCAbRangedTE` (a `NetworkE.TTokenEvent`) | `TRangedAttackAbility.fcExecuteCombatCommand` @ `0x5576EB70` |
| flight path | **real** — pixel-space arc, `AoWTC.MakeRangedPath` @ `0x00427630` | none |
| intervening units | **yes**, probabilistic, retargets the shot | **no** |
| intervening terrain/obstacles | **yes** | **no** |
| walls | block the shot outright (probabilistic) | **−2 ATK cover penalty only** (§0a) |
| what the CA gets as cover arg | `0` (always) | `2` — condition in §0a |

Both ultimately call the *same* damage builder,
`AoWEPACK!TRangedAttackAbility.CreateRangedAttackCA` @ `0x5576EAE4`
(`AoWTCPCK` reaches it through the import thunk at `0x00402874`), so every ATK/DAM mod applied there
affects both. **Only the target selection differs.**

`AoWTCPCK.dpl` preferred base is `0x00400000`; all `0x004xxxxx` addresses below are that module.

### 0a. The auto-resolve wall penalty — what it actually is (re-derived 2026-08-09, live bytes)

The chain, all confirmed against the **live** `AoWEPACK.dpl`, not inherited from an earlier doc:

```
TRangedAttackAbility.fcExecuteCombatCommand  0x5576EB70
  5576EB86  call TFastCombat.GetWallSituation      (shooterObj, targetObj)
  5576EB8B  cmp al, 2
  5576EB8F  mov [esp+4], 2        <- the cover value; every other case leaves it 0
     ...passed as the 4th arg to...
TRangedAttackAbility.CreateRangedAttackCA    0x5576EAE4
  5576EB14  call [ecx + 0x114]    <- TRangedAttackAbility VMT+0x114 = GetAttackRA
  5576EB1A  sub  al, [ebp + 8]    <- ATK minus the cover value
  5576EB1D  push eax              <- pushed as a Setup() arg
```

So it is **−2 to the ranged ATK**, not to damage. Cross-check that fixes the VMT base: the same
function's shot-count loop calls `vmt[0x118]`, and on this base `+0x118` is `GetAttackRepeatRA` —
exactly what a repeat count should be. Neighbouring slots `+0x10C/+0x110/+0x11C` are
`GetRangeRA` / `GetDamageRA` / `GetDamageTypesRA`, and the classname string begins at `+0x120`,
so the table ends where it should.

> ⚠ **VMT-base gotcha that cost a wrong reading here.** In `AoWEPACK.dpl`'s export table,
> **`Unit..TClass` (two dots) is the VMT; `Unit.TClass` (one dot) is not** — for
> `TRangedAttackAbility` those are `0x5571E8D4` and `0x5571EA10`, `0x13C` apart. Taking the one-dot
> symbol as the VMT makes every slot resolve to a plausible-but-wrong method
> (`+0x114` reads as `TAbility.NewTurn`), which is exactly the failure mode of
> `aow1-investigation-traps` #13 — the instruction was read right, the operand's identity was assumed.
> **Verify a VMT base by walking `[VMT-0x2C]` to the classname ShortString** (Delphi 3
> `vmtClassName = -44`), which also tells you where the table ends.

**The condition** is narrower than "the target is behind a wall". `GetWallSituation` @ `0x5574468C`:

```
if not GetWallInBetween(...)          -> 0     (no penalty)
else if GetSide(SHOOTER) == 1         -> 1     (no penalty — fcExecuteCombatCommand only tests ==2)
else                                  -> 2     (-2 ATK)
```

and `GetWallInBetween` @ `0x55744600` is **not geometric** — it XORs the two *parties'* "inside the
walls" booleans (`party+0x18`, party index = the grid byte's high nibble), gated on the combat
carrying a wall object with flag `[wall+0x47] & 1` clear. So:

- the penalty needs the two **parties** to be on opposite sides of the siege wall, nothing to do with
  the line between the individual units;
- it is applied to the shooter whose `GetSide != 1` only. `TCombatObject.GetSide` @ `0x55726660`
  returns `player[+0x0A]`, or **2** when `bPlayer_side == 0xFF` (playerless objects), so side-2
  objects are penalised too.

*Not chased:* `sub al` is a byte op with no clamp, so an ATK of 1 would wrap to 255. Whether
`Setup`/the to-hit code reads that slot as signed or unsigned was not checked — the same "unclamped"
caveat already recorded for the invisibility ATK penalty.

---

## 1. `AoWTC.MakeRangedPath` @ `0x00427630` — the trajectory generator

Delphi register convention, `ret 0x28` (10 stack params):

```
MakeRangedPath(AL = shooterSide,          // TCombatObject.GetSide of the firer
               DX = stepDivisor,          // "speed"; bigger = fewer, longer steps
               CX = arcHeight,            // 0 = dead flat
               [ebp+0x08] = ^TList,       // OUT: obstruction records
               [ebp+0x0C] = ^TXYZList,    // OUT: the flight path
               [ebp+0x10] = checkUnits:byte,
               [ebp+0x14] = extraPixelY,  [ebp+0x18] = extraPixelX,   // target fudge, normally 0
               [ebp+0x1C] = targetHX,     [ebp+0x20] = targetHY,
               [ebp+0x24] = sourceHY,     [ebp+0x28] = sourceHX)
```

### 1a. Step count

```
N = max(2,  (|targetHX-sourceHX| + |targetHY-sourceHY|) * 100 / stepDivisor)
```

`N+1` `TXYZ` points are emitted (`i = 0..N`). Hex→pixel is `HSEPack!HSEngine.HXtoHP`
(`px = x*32+8`, `py = y*32+(x&1)*16`); both endpoints get `+13` on each axis to land on the hex
centre.

### 1b. X/Y — plain linear interpolation

```
pt[i].x = (Bx - Ax) * i / N + Ax          // TXYZ +0x04
pt[i].y = (By - Ay) * i / N + Ay          // TXYZ +0x08
```

**The ground track is a straight line in screen space**, not a hex-walk. Which hexes the shot crosses
is discovered afterwards by converting each sample point back with `HPtoHX`.

### 1c. Z — the arc (`TXYZ +0x0C`)

`k` is a symmetric triangle peaking mid-flight:

```
half = N div 2
k = (i >  half) ? N - i + 1
  : (i == half) ? i
  :               i + 1
```

then

```
arcHeight == 0  ->  z = 0
otherwise       ->  z = round( sqrt( (k * N * arcHeight) div 10 ) )  -  (10 * N) div arcHeight
```

Note it is a **square root of a triangle**, not a parabola — flatter over the apex than a real
ballistic arc, and both integer divisions truncate, so short shots can sit at `z=0` throughout.

**`z` is the whole anti-blocking mechanic** (see §2b): a higher arc literally flies over the
obstruction check. That is why Archery lobs and Doom Gaze does not.

### 1d. Per-ability arc & speed — `AoWTC.MakeAbilPath` @ `0x004271EC`

`MakeAbilPath(AL = side, DX = abilityId, CX = spellId, ...)` picks the style, then tail-calls
`MakeRangedPath`. `abilityId` is `TCAbRangedTE+0x14`; `spellId` is `+0x18`.

| style | arc `CX` | step div `DX` | checkUnits | abilities (id → `re_tools/ability_names.py`) |
|---|---|---|---|---|
| **flat, dense** | `0` | `0x19` = 25 | 1 | 55 Doom Gaze |
| **high lob** | `0x64` = 100 | `0x32` = 50 | 1 | 22 **Archery**, 24 Hurl Boulder, 25 Hurl Stones |
| **low arc** | `0x14` = 20 | `0x32` = 50 | 1 | 44 Fire Cannon, 45 Fire Musket, 57 Shoot Bolt, 58 Throw Javelin, 123 Lightning Bolts |
| **no path at all** | — | — | — | 30 Flame Throwing, 31 Call Flames, 86–90 the five Breaths |
| **per-spell** | jump table | | | 52 Spell Casting → sub-dispatch on spell id |

- **"no path at all"** (`0x0042730A`) emits a single point at the shooter's own hex and does
  `TList.Clear` — so those abilities are **structurally unblockable**. Breath weapons and
  Flame Throwing can never be intercepted; that is by construction, not by a high roll.
- **Spell Casting (52)**: byte index table at `0x0042739A` over `spellId-100` (range 100..119),
  dword jump table at `0x004273AE`. Only spell ids **100, 103, 107, 117, 119** get a bespoke path;
  everything else falls to the default at `0x004274E9`. (117 = Chain Lightning.)

### 1e. Missile art

`TRangedPathHS.Activate` @ `0x00427DE0` links two image libraries: **`TCombat\Misc.ILB`**
(`+0x0C`) and **`TargHex.ILB`** (`+0x10`). The direction sprite index comes from
`AoWTC.GetRangedDirIndex` @ `0x00430D48` and is stored at `TRangedPathHS+0x20`.

---

## 2. The obstruction scan (second half of `MakeRangedPath`, from `0x00427887`)

For each sample point, convert back to a hex (`HPtoHX`) and **skip the shooter's hex and the
target's hex**. For everything in between, fetch `TMapLevel.GetField(HX,HY)` and query it with
`field->vmt[0x80](classId)`:

| class id | class | fetched into | when |
|---|---|---|---|
| `0x220104` | `AoWTC.TTacticalCombatUnitHS` | `unit` | only if `checkUnits` |
| `0x220504` | `CityWall.TCityWall` | `wall` | always |
| `0x220506` | `CityWall.TCityWallDoor` / `CombatStructure.TCombatStructure` | `wall` (fallback) | only if `shooterSide == 0` |

plus two raw field bytes — same enums as the strategic map (see
`Movement_Tables_Terrain_Types.md`):

- **`field+0x14` = terrain id**: `7` (EarthWall) or `0xF` (Border / off-battlefield) ⇒ hard block.
  ⚠ `8` RockWall is **not** checked, and **overlay 0 (Mountain) is not checked either** — mountains
  do not block missiles.
- **`field+0x15` = overlay id**: `8` = **Obstacle** ⇒ blocks (only in the range ≥ 2 branch).

`r = dHXtoRad(currentHex, shooterHex)` is the hex distance from the shooter. The rules split on it:

**`r == 1` (hex directly beside the shooter)**
- `unit` present **and** `GetSide(unit->[0x1c]) != shooterSide` ⇒ code **1**.
  → **your own units adjacent to your archer never block it; an adjacent enemy does.**
- `wall` present with `wall[+0x20] > 0` and `shooterSide == 0` ⇒ code **4**.

**`r > 1`**
- `unit` present (friend **or** foe) ⇒ code **1**. → **friendly fire is live from 2 hexes out.**
- no `wall`, and `field+0x15 == 8` (Obstacle overlay) ⇒ code **1**.
- `wall` present with `wall[+0x20] > 0`:
  - `r > 2` ⇒ code **2**;
  - `r == 2` ⇒ code **2** *only if* none of the six neighbours of the **shooter's** hex holds a wall
    or door (i.e. you get a free shot over your own wall when you are standing on the battlement).
- `wall[+0x20] <= 0` (breached) ⇒ no block. Destroying a wall really does open the firing lane.

Terrain `0xF` / `7` ⇒ code **3**, tested before everything else.

### 2b. Turning a code into a percentage

Each blocking hex gets one record in the out-`TList`
(`+0x04` = index of the path point, `+0x08` = interception chance 0..100):

| code | meaning | weight `w` contributed by this sample |
|---|---|---|
| 1 | unit / obstacle | `w = 2 * (dx + dy - z)` where `dx = clamp-fold((pt.x+11)-hexPx, 47)`, `dy = clamp-fold((pt.y+3)-hexPy, 31)` — i.e. **how centrally the shot crosses the hex, minus its height** |
| 2 | wall | `w = 200 - 3*z`, and the record takes **`max`**, not a sum |
| 3 | terrain | `w = 100` (absolute) |
| 4 | adjacent wall, own side | `w = 50`, contributed **once** |

Codes 1 and 3 **accumulate** across every sample point that lands in the same hex, then the record is
clamped to 100. So the slower the missile crosses a hex (more samples) and the flatter it flies
(lower `z`), the more likely it is stopped there.

Worked shape (derivation, not measured): a 4-hex Archery shot gives `N=8`, `z` running 9 → 18 → 9,
so roughly 2 samples × ~10 per intervening hex ≈ **20 %**. The same shot as Lightning Bolts
(`arc 20`) has `z` running 0 → 4 → 0 and lands far higher. Doom Gaze (`arc 0`, `stepDiv 25`) has
`z = 0` and ~4× the samples, so it hits essentially the first thing in the way — correct for a beam.

---

## 3. The roll, and the retarget — `CombatTE.TCAbRangedTE.NextStrike` @ `0x0040D290`

After `MakeAbilPath` returns (call site `0x0040ED9B`), the loop at **`0x0040EE41`–`0x0040F0A2`**:

```
for j = 0 .. TList.Count-1:
    entry = TList[j]
    if TAoWHSMap.Random(100) >= entry[+8]:  continue        // not intercepted
    pt   = path[ entry[+4] ]
    hex  = HPtoHX(pt.x, pt.y)
    blocker = field(hex).Get(0x220104)                       // unit
           ?: field(hex).Get(0x220166)                       // CombatTerrain.TCombatTerrain
           ?: field(hex).Get(0x220504)                       // TCityWall
           ?: field(hex).Get(0x220506)                       // door / structure
    if blocker = nil and terrain not in {7,0xF} and overlay <> 8:  continue
    truncate the TXYZList after entry[+4]                    // the missile visibly stops there
    if blocker is TTacticalCombatUnit*:  missile[+0x2C] := blocker[+0x1C]   // NEW VICTIM
    else:                                missile[+0x2C] := nil             // shot absorbed
    break
```

`missile` is the `TRangedPathHS` (`ClassID 0x220105`). Its `+0x2C` is consumed in
**`TCAbRangedTE.Execute` @ `0x0040C43D`**:

```
EAX = TAbilityControl.GetAbility(TE[+0x14])     // the ranged ability
EDX = TE[+0x10]                                 // attacker combat object
ECX = missile[+0x2C]                            // <-- TARGET
push 0                                          // cover penalty = 0
call AoWEPACK!TRangedAttackAbility.CreateRangedAttackCA
```

So an intervening unit is **not** "the shot fizzles" — it becomes the genuine target of a normal
ranged-attack CA: full to-hit, full damage, full ability processing, XP to the shooter. Note the
`0x220166` (`TCombatTerrain`) entry in the blocker chain: it is *findable* as a blocker but is not a
`TTacticalCombatUnit`, so it absorbs the shot with `nil` target — battlefield trees/rocks eat arrows
without taking damage from them.

### The three `MakeRangedPath` call sites and their `checkUnits`

| site | purpose | `checkUnits` |
|---|---|---|
| `0x0040ED9B` (via `MakeAbilPath`) | the real shot | **1** |
| `0x0040D65F` | stray/fan trajectory (SIN/COS spread off `TE+0x34`) | **0** — cosmetic only |
| `0x0040ED26` | `arc 0, stepDiv 10` special | 1 |
| `0x00414E6B` (`TCAI.EvalPath`) | AI pre-check, kind 5 | **0** |

---

## 4. What the player and the AI see

- **Preview**: `AoWTC.TCombatUnitSelectionControl.CalculateRangedPath` @ `0x0041DC58` builds the same
  path for the hover overlay. It bails immediately if the target hex terrain is `0xF`. Its arc
  parameter comes from the ability's own `vmt[0x84]` category (`5 → 0x0C`, `4 → 8`, else `4`), i.e.
  the preview uses a *different* arc scale than the shot — worth knowing before trusting it as a
  ground truth for the roll.
- **AI**: `AoWTC.TCAI.EvalPath` @ `0x00414DA8` runs `MakeAbilPath`, then for each obstruction record
  calls `TCAI.EvalHex` on the blocked hex and folds the result in proportionally
  (`score = EvalHex * entry[+8] / 100`, `0x00414F85`+). **The AI does price in the chance of hitting
  whatever is in the way**, including its own units. It only bothers for ability "kinds"
  {1,2,3,5,6,11,28} (kind = byte table `[0x004672F4]` for spells, `[0x00467248]` for abilities).

---

## 5. Levers, if this is ever to be modded

Cheapest to most invasive:

1. **Re-tune an ability's arc / speed** — three `mov cx, imm16` / `mov dx, imm16` pairs in
   `MakeAbilPath` at `0x004272BC`/`0x004272C0` (lob), `0x004272F5`/`0x004272F9` (low arc),
   `0x00427287` (flat). Two bytes each, no cave. Raising `CX` on Archery makes archers safer to
   shoot past friends; lowering it makes them dangerous.
2. **Move an ability between styles** — the comparison chain at `0x004271FD`–`0x0042725C` is a plain
   `cmp/sub` ladder on the ability id. Moving e.g. Lightning Bolts from "low arc" to "no path" makes
   it unblockable.
3. **Change the interception weights** — the four handlers at `0x00427C0B` (unit),
   `0x00427CB0` (wall), `0x00427CD1` (terrain), `0x00427CDA` (adjacent wall). The `imul eax,eax,2`
   at `0x00427CA1` is the single multiplier controlling how blocking units are overall.
4. **Add unit size as a term** — this is where the original "make size matter" idea belongs. See
   §6 for exactly what is and isn't available; the short version is that `[ebp-0x50]` already holds
   the intervening `TTacticalCombatUnitHS` and the weight is computed 11 instructions later, so the
   hook site is trivial — the work is *fetching* the size, not applying it.
5. **Give manual combat the wall cover penalty** — the `push 0` at `0x0040C41D` (and the two
   preview sites `0x00421137`, `0x0042125B`) is the `param_4` that fast combat sets to `2`.

⚠ Any patch to `AoWTCPCK.dpl` must be **position-independent** (it is a Delphi package and rebases),
same rule as `AoWEPACK.dpl`. Existing AoWTCPCK patch scripts to copy the pattern from:
`build_replaylog.py`, `build_simfly.py`, `build_spellcast_tcpck.py`.

---

## 6. Does unit size affect occlusion? **No — every unit occludes identically** (verified 2026-08-09)

`MakeRangedPath` touches the intervening unit in exactly **five** instructions, and none of them
reads a unit stat:

| addr | what |
|---|---|
| `0x004279EC` | store `nil` (when `checkUnits == 0`) |
| `0x00427A18` | store `field->Get(0x220104)` — the unit HS |
| `0x00427A81` | nil-test (range-1 branch) |
| `0x00427A87` | `[unit+0x1C]` → `TCombatObject.GetSide` — friend/foe, **range 1 only** |
| `0x00427AD5` | nil-test (range >1 branch) |

The weight handler at `0x00427C0B` reads only: the current hex's pixel origin (`HXtoHP`), the path
point's `+0x04`/`+0x08`/`+0x0C` (x/y/z) and the constants `0xB, 0x2F, 3, 0x1F, 2`. **No unit field
appears in it.** `AoWTCPCK.dpl` also imports nothing matching `*Size*`, and makes no VMT call on the
intervening unit at all.

**So the occlusion chance is a property of the *missile*, not of the *occluder*.** A Fairy and a Red
Dragon standing in the same hex are equally likely to eat the arrow. What varies it is the ability's
arc height and step count (§1d) and how centrally the arc crosses that particular hex.

### The data is there if you want to change that

`unit_size` is a real, varied stat — `TUnitResource+0x50`, serialised as **`Unitres.pfs` tag `0x1C`**
(`TUnitResource.ReadWrite` @ `0x55784DE4`). Measured across all **179** installed unit records:

| size | count | examples |
|---|---|---|
| 0 | 21 | Frostling Archer, Halfling Swordsman, Fairy, Leprechaun |
| 1 | 81 | Human Man-at-Arms, Human Archer, Azrac Swordsman, Djinn |
| 2 | 52 | Human Lancer, Beholder, Sandworm, Turtle Catapult |
| 3 | 25 | Elephant, Titan, Giant, Red Dragon, Air Galley |

⚠ **Range is 0–3, never 4–5** — and this is the *installed Ziggurat* data, so re-measure if the
vanilla files are ever compared.

⚠ **The hard part is the fetch, not the term.** Size is *not* reachable from a combat object:
no `TCombatUnit` VMT slot holds `GetUnitSize`, and `vmt[+0x90]` is **`GetAlignment`** (verified off
`AoWE..TCombatUnit` = `0x55715A94`). From `[ebp-0x50]` you have `TTacticalCombatUnitHS → +0x1C =
TCombatObject`, and getting from there to `TUnit`/its resource is the unsolved step —
`TCombatUnit+0x4C` is the likely bridge (it is what `TCombatUnit.GetAlignment` forwards through)
but that has **not** been verified for this purpose. Budget the work there, not in `0x00427C0B`.

## 7. Loose ends deliberately not chased

- The five bespoke spell paths (ids 100/103/107/117/119) at `0x004273C6`, `0x004273FD`,
  `0x0042743E`, `0x00427477`, `0x004274B0` — not decoded individually.
- `aowFX.MakeArcPathXY` (`aowFXpck.dpl`, thunk `0x00402E24`), used by one `NextStrike` branch at
  `0x0040EC83` instead of `MakeRangedPath` — a separate arc generator, unexamined.
- Where the `TRangedPathHS` animation actually *lands* (which frame triggers `Execute`) — only the
  target selection was traced, not the frame pump.
- Whether `TCombatObstacle` (`ClassID 0x22052A`) is ever placed with overlay 8; the scan checks the
  overlay byte, not that class.
