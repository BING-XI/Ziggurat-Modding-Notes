# Strategic map damage — storms, grounds, fire, vortex, quake, poison

**Status: RE COMPLETE 2026-08-18 — NOTHING APPLIED.** Map of every source of damage dealt to units on the
**strategic** map (as opposed to inside combat). All addresses read from the **live** `AoWEPACK.dpl` with
`re_tools/dasm.py`; VMT slots resolved from the class VMT against the DLL's own export table, not inferred.
Preferred-base VAs (`0x55700000`).

**One-line answer:** every strategic damage source funnels through
**`AoWE.TAbstractUnit.ExecuteDamageRole @0x55781AC4`**, which wraps the *same* core roll
(`AoWE.ExecuteDamageRole @0x55725EAC`) that resolves weapon strikes in combat. There are **seven** engine
callers and one Ziggurat cave.

Storm *internals* (per-storm debuffs, protection masking) are in `Investigation_Storm_Protections.md`; this
doc is the cross-source map. The two agree where they overlap — see §4.

---

## 1. The chokepoint

```
AoWE.TAbstractUnit.ExecuteDamageRole @0x55781AC4
    (EAX = unit, EDX = attack, ECX = damage, [ebp+8] = damage-type set (word))

    si = types & ~GetImmunityTypes(vmt+0xEC)
    if si == 0                                 -> return 0     ; immune to ALL of it, NO ROLL
    diff = attack - GetDefense(vmt+0xC4)                       ; <- DEFENCE, not Resistance
    result = AoWE.ExecuteDamageRole(damage, diff)              ; the shared combat roll
    if (types & ~GetProtectionTypes(vmt+0xF0) & si) == 0       ; protected against everything left
        result = (result+1) >> 1                               ; halve, round-half-toward-zero
    return result
```

⚠ **It rolls against Defence (`vmt+0xC4`), not Resistance (`vmt+0xCC`).** Verified by resolving
`TAbstractUnit`'s VMT (`0x55710740`) slot-by-slot against `.edata`:

| slot | symbol | slot | symbol |
|---|---|---|---|
| `+0xC0` | `GetAttack` | `+0xE0` | `GetHitPoints` |
| `+0xC4` | **`GetDefense`** | `+0xE4` | `SetHitPoints` |
| `+0xC8` | `GetDamage` | `+0xEC` | `GetImmunityTypes` |
| `+0xCC` | `GetResistance` | `+0xF0` | `GetProtectionTypes` |
| `+0xD0` | `GetHits` | `+0xFC` | `GetAlignment` |
| `+0xD4` | `GetMoves` | `+0x148` | `GetAbilityEnabled` |

This is the aliasing trap CLAUDE.md warns about: in **combat** the equivalent wrapper
(`TCombatObject.ExecuteDamageRole @0x557269F0`) uses `vmt+0x70 GetDefense` and `vmt+0x74 GetResistance` —
totally different numbers on a different class. Never carry an offset across the two hierarchies.

⚠ **The live file hooks this function's first instruction**: `0x55781AC4` is `jmp 0x5580DA20`, the
fire-heals-fire cave (`build_firefeed.py`), which re-enters at `0x5580DA61` and `neg`s the result for
fire-affinity units. Anything hooking here must preserve that.

---

## 2. The complete caller census

`E8`/`E9` rel32 scan of the whole CODE section (`0x55701000`, `0x1E6918` bytes) — exhaustive, and it sees
the Ziggurat caves that a Ghidra xref on the vanilla image would not:

| source | function | call site | attack | damage | damage type |
|---|---|---|---|---|---|
| **Storms** | `TAbstractUnit.ExecuteStormDamage @0x55780668` | `0x557807C2` | per-storm | per-storm | per-storm (§4) |
| **Map fire** | `TArmy.TriggerFireDamage @0x55790110` | `0x55790223` | 6 | 3 | `dtFire` (`[0x55790310]` = 1) |
| **Vortex** | `TVortexTE.Process @0x557A13CC` | `0x557A164B` | **8** | variable (EBX) | pushed |
| **Town quake** | `TTownQuake.TriggerArmyDamage` | `0x557B1CEE` | 7 | 5 | `dtPhysical` (`[0x557B1DDC]` = 0x80) |
| **Poison plant** | `TPoisonPlant.TriggerArmyDamage` | `0x557C4178` | 6 | 2 | `dtPoison` (`[0x557C4288]` = 0x10) |
| **Holy ground** | `THolyGround.TriggerArmyDamage @0x557C7E18` | `0x557C7F61` | 6 | 4 | `dtHoly` (`[0x557C8050]` = 0x40) |
| **Unholy ground** | `TUnHolyGround.TriggerArmyDamage @0x557C8FA4` | `0x557C90CE` | 6 | 4 | `dtDeath` (`[0x557C91DC]` = 0x20) |
| *(Ziggurat)* | fire-heals-fire cave | `0x5580DB0D` | — | — | — |

**Only two of them also apply status effects.** Callers of
`TAbstractUnit.ExecuteDamageEffects @0x55781E28` are exactly **`ExecuteStormDamage` (`0x55780811`)** and
**`TPoisonPlant.TriggerArmyDamage` (`0x557C41D2`)**. The grounds, map fire, vortex and quake deal typed
damage only — no debuff. (This corrects a natural but wrong assumption that holy/unholy ground curses you.)

Every caller clamps the result to the target's remaining HP via `GetHitPoints (vmt+0xE0)` before applying.

---

## 3. `TDamageType` — the enum, from RTTI

Recovered from the Delphi RTTI member names in the DLL. A `TDamageTypes` set is a 16-bit word with
bit *n* = ordinal *n*:

| bit | value | name | bit | value | name |
|---|---|---|---|---|---|
| 0 | `0x001` | `dtFire` | 5 | `0x020` | `dtDeath` |
| 1 | `0x002` | `dtCold` | 6 | `0x040` | `dtHoly` |
| 2 | `0x004` | `dtLightning` | 7 | `0x080` | `dtPhysical` |
| 3 | `0x008` | `dtMagic` | 8 | `0x100` | `dtWall` |
| 4 | `0x010` | `dtPoison` | 9 | `0x200` | `dtNone` |

⭐ **Reusable:** this is the authoritative decode for every `word` damage-type mask in the engine. Per
`[[aow1-scrolls-cut-content]]`, RTTI enum names beat string search — the members sit as consecutive
Delphi ShortStrings and can be recovered from any build.

---

## 4. Storms — index, type and strength

`TArmy.IncommingStorm @0x557904B4` → `TAbstractUnit.ExecuteStormDamage @0x55780668` per unit.

- **Type**: `StormDamageType` `@0x558E8330` is an **8-byte array of enum ORDINALS** (not a bitmask table),
  indexed by storm number: `mov dl, byte [eax + 0x558E8330]` `@0x557807A5`, then
  `System.@SetElem @0x55701088` builds the one-element set. Live bytes: `09 00 05 06 01 02 04 90`
  (index 7 = `0x90` is padding — storms are 0..6).
  ⚠ A previous read of this as a *word* table produced nonsense; it is bytes-of-ordinals.
- **Strength**: a 7-entry jump table at `0x5578072E` (`cmp eax,6 / ja / jmp [eax*4 + 0x5578072E]`), each
  case setting `EBP` = attack and `ESI` = damage.

| idx | storm | case | attack / damage | type |
|---|---|---|---|---|
| 0 | **Blast Storm** | `0x55780792` | **0 / 0** | `dtNone` (`0x200`) |
| 1 | Fire Storm | `0x5578077A` | 8 / 5 | `dtFire` |
| 2 | Death Storm | `0x55780762` | 8 / 4 | `dtDeath` |
| 3 | Divine Storm | `0x5578076E` | 8 / 5 | `dtHoly` |
| 4 | Ice Storm | `0x5578074A` | 8 / 5 | `dtCold` |
| 5 | Lightning Storm | `0x55780756` | 8 / 6 | `dtLightning` |
| 6 | Pestilence | `0x55780786` | 7 / 1 | `dtPoison` |

**This is an independent re-derivation, and it confirms `Investigation_Storm_Protections.md` §1 in full**
— that doc already carries all seven rows with the same attack/damage pairs and types, derived a
different way (via the `StormType` virtuals). Two independent routes agreeing is the useful result here;
this table adds nothing new to the storm picture. Consult that doc for the per-storm **debuffs**, which
this one does not cover.

⭐ **Blast Storm deals NO damage through this path** — its case is the same `xor ebp,ebp; xor esi,esi`
target as the out-of-range default, so `damage = 0` and `ExecuteDamageRole` returns 0 immediately. Its
`dtNone` type is consistent with that. Whatever Blast Storm does, it is not unit damage here.

⚠ **Two tests sit before the switch but they gate the TERRAIN BONUS, not the damage** — a natural
misreading. `GetAbilityEnabled(0x17)` `@0x5578068B` and `GetMoveTypes (vmt+0xE8) & 2` `@0x5578069B`
both jump straight to the strength switch at `0x5578071D` when they fail; the damage is dealt either
way. What they actually skip is the location/terrain lookup that sets `BL`, which at `0x55780796`
drives `imul esi,2; imul esi,2` — the **×4 base-strength bonus for standing on the storm's own
terrain type** (documented as ×8 before a prior Ziggurat patch; see
`Investigation_Storm_Protections.md` §1 and §6).

---

## 5. The grounds — "walking on" is a SEPARATE trigger from the per-turn tick

`THolyGround` (and its `TUnHolyGround` mirror) carry two independent entry points into the same
`TriggerArmyDamage`:

| trigger | VA | when |
|---|---|---|
| **`ArmyPlaced`** | `0x557C8054` | the instant an army is **placed on the field** — the walk-on hit |
| **`NewTurn`** | `0x557C80A0` | again **every turn** the army remains, and ticks the ground's lifetime |

```
THolyGround.ArmyPlaced @0x557C8054
    if ([[AoWHSMap]+0x3C] & 2) == 0        ; suppressed during load / map-edit
        TriggerArmyDamage()
    ret
```

`NewTurn` additionally decrements the duration byte at `[obj+0x1E]` and calls
`THolyGround.RestoreTerrain @0x557C8068` when it reaches zero. Unholy mirrors at `0x557C91E0` /
`0x557C922C` / `0x557C91F4`.

So **standing on holy ground costs you once on arrival and once per turn thereafter.**

### `CanDoDamage @0x557C80EC` — the "does this hurt anyone here" gate

Walks the army's `TUnitList` (`TUnitList.GetUnit @0x5578309C`) and, per unit:

1. `GetImmunityTypes (vmt+0xEC)`, `test al,0x40` → skip if immune to holy;
2. `GetAlignment (vmt+0xFC)`, `cmp al,6` → skip;
3. `GetAlignment` again, tested against the `alsPureGood` bitset (`[0x558E9418]`) → **skip if the unit's
   alignment is pure good**.

Holy ground does not burn good units. `TUnHolyGround.CanDoDamage @0x557C9278` is the mirror.
`TriggerArmyDamage` itself has a further `GetAbilityEnabled(1)` skip at `0x557C7F44`.

---

## 6. Bearing on a hit-chance slope change

All seven sources inherit `HitChance_Increment_Audit.md`'s slope edit automatically — **no extra code
sites**. But they share the shape that makes §4c of that audit awkward: a **fixed** attack value rolled
against a variable Defence. Halving the slope compresses them toward 50% rather than spreading them out.

Holy/unholy ground (attack 6) against the installed unit population (DEF 1–10, median 3):

| target DEF | diff | today | at 5 pp |
|---|---|---|---|
| 1 | +5 | 90% (pinned) | 75% |
| 3 (median) | +3 | 80% | 65% |
| 6 | 0 | 50% | 50% |
| 10 | −4 | 10% (floor) | 30% |

Storms and the vortex at attack 8 shift further still. **Net: map hazards become markedly less lethal
against weak units and more lethal against tough ones** — the opposite of finer discrimination. Raising
the fixed attack values only corrects one point on each curve, because the Defence side is not scaled.
If the slope change ships, these seven immediates (6, 6, 6, 7, 8, and the storm cases 7–8) are a balance
decision in their own right.

---

## 7. Correction to an existing doc

`Investigation_Storm_Protections.md` — its damage-type table lists `0x200` as "(blast)". `0x200` is the
**`dtNone`** ordinal; Blast Storm is storm **index 0** and its type is `dtNone`. Both statements are
compatible, but the *type name* is `dtNone`, and the full enum is in §3 above. Its `StormDamageType[]`
reference should be read as a **byte** array of ordinals (§4).

## Cross-references

- `Investigation_Storm_Protections.md` — per-storm debuffs, immunity/protection masking, the effect caves.
- `Fire_Heals_FireUnits_Design.md` — the `0x5580DA20` cave that negates this roll for fire units.
- `Excess ATK minimum damage bonus.md` — the shared core roll and its damage curve.
- `HitChance_Increment_Audit.md` — the slope-change inventory (§6 above).
- Memory: `[[aow1-combat-math-decoded]]`, `[[aow1-fire-heals-fire-units]]`.
