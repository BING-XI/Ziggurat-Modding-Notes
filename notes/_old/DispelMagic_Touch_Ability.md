# Dispel Magic — the touch ability (`0x3C`)

**Status (2026-08-09): analysis verified; the level cap has been raised III → V and is APPLIED but
UNTESTED — see §9.** Read off the vanilla `AoWEPACK.dpl` in Ghidra plus the live file with capstone.
Formulas and addresses are verified; the per-spell resistance table is verified for `UnitSpells.*`
and flagged where it is not.

⚠ Sections 1–8 describe **vanilla** behaviour (cap III). The installed game is now at cap V.

Related prior art: `Investigation_Items.md` §3.6 (the item-granted version is infinitely usable —
a real bug), `Investigation_Abilities_Leadership.md` (multi-level ability model).

---

## 1. What it is

Ability id **`0x3C`**, vanilla levels **I–III** (now V here — §9). It descends from
**`TTouchAbility`**, so it is used by moving adjacent to a unit and touching it — not at range.

⚠ **The cap is NOT the base `TMultiLevelAbility` field `ability[+0x28]`.** Dispel Magic ignores that
field and hard-codes 3 in two `cmp`s (`CanExpand` @ `0x5576D163`, `Expand` @ `0x5576D1D0`), and keeps
its level at `TDispelMagicAbilityData` **+0x0D** — the base class uses +0x0C, which here is the
per-turn *enabled* toggle. Read the cap out of `CanExpand`/`Expand`, never off `[+0x28]`.

Class `AoWE.TDispelMagicAbility`, VMT `0x55721D78`. Two completely separate execution paths:

| | strategic map | tactical combat |
|---|---|---|
| driver | `TDispelMagicAbilityTE.Execute` @ `0x5576D744` | `TDispelMagicCA.Generate` @ `0x5576CC18` → `TDispelMagicAbilityCA.Execute` @ `0x5576CCE4` |
| when the dice are rolled | at execute time | at **Generate** time; `Execute` only applies the stored id list (`CA+0x10`, a `TIntegerList`) |
| extra behaviour | player message | **kills summoned units** (§4) |

## 2. What it actually does

It **strips enchantments off the touched unit**, rolling each one independently.

```
mana = GetDispelMana(ability, dispeller)          // 0x5576CEA8
     = GetLevel(dispeller) * 10 + 20              // VMT+0x70 = GetLevel -> 30 / 40 / 50

target.ListEnchantments(list)                     // 0x5577F45C
for each ench in list:
    chance = TEnchantment.DispelChance(ench, mana)         // 0x5577C1A0
    if Random(100) < chance:  ench.Dispel()                // VMT+0x68 = TEnchantment.Dispel
```

**`DispelChance` @ `0x5577C1A0`:**

```
chance = clamp( mana - 10 * (signed char)ench[+0x14] + 50 , 10 , 90 )
```

so with `mana = 10*level + 20`:

> **chance = clamp( 10·(dispelLevel) − 10·R + 70 , 10 , 90 )**, where `R = ench[+0x14]`

Then the ability is spent for the turn — `SetEnabled(ability, dispeller, 0)` — and the player is told
either `DispelMagicFailed` or `XSpellsSuccessfullyDispelled` with the count.

## 3. `R` — the enchantment's dispel resistance

`ench[+0x14]` is a byte, defaulting to **10** in `TEnchantment.Create` @ `0x5577BEAC` (which yields a
flat 10 % — effectively undispellable). Each unit-enchantment spell overwrites it in its
`ExecuteSpell`, at a uniform `+0x5D` in every one:

```
ench[+0x14] := spell[+0x3C]          // e.g. UnitSpells.THaste.ExecuteSpell @ 0x557E6BE1
```

and `spell[+0x3C]` is a hard-coded constant in each spell's `Create`.

⚠ **`spell[+0x3C]` is NOT serialised.** `TSpell.ReadWrite` @ `0x55779234` writes only `+0x14` mana
(tag `0xD`), `+0x1C` upkeep (`0xE`), `+0x18` research (`0xF`), `+0x20` sphere (`0x10`), `+0x21`
research tier (`0x11`). **So dispel resistance cannot be retuned from `Spells.pfs` — it is a DLL
patch.** (Note it is also *not* the research tier: Haste is tier 1 with `R = 3`.)

### Measured values (vanilla DLL, extracted from each `Create`)

| R | chance vs Dispel **I / II / III** | spells |
|---|---|---|
| 3 | **50 % / 60 % / 70 %** | Bless, Dark Gift, Enchant Weapon, Fury, Haste, Stone Skin |
| 4 | **40 % / 50 % / 60 %** | Concealment, Fire Aura, Free Movement, Healing Water, Holy Champion, Unholy Champion |
| 5 | **30 % / 40 % / 50 %** | Liquid Form, Wind Walking |
| 6 | **20 % / 30 % / 40 %** | Water Walking |
| 10 | **10 % / 10 % / 10 %** | Cosmetic Surgery (the floor — effectively permanent) |

⚠ The scan also reported `R` for `CitySpells.TAntiMagicShell/TGoldRush/TWarmonger`, `Dungeon.TDungeon`
and several `CombatSpells.*`, but **only the `UnitSpells.*` rows are verified** — those are the ones
where the `ExecuteSpell` write of `ench[+0x14] := spell[+0x3C]` was actually read. For the others,
`+0x3C` may be a different field (the standard disp8-aliasing caveat).

## 4. Summoned units die

`TDispelMagicCA.Execute` @ `0x5576CCE4`, combat only:

```
had = targetUnit->vmt[0x148](0x9B)      // ability 0x9B = "Summoned"; +0x148 is the ITEM-AWARE query
... apply the dispels ...
if (had && !targetUnit->vmt[0x148](0x9B))
    attacker->vmt[0x108]( target, target->vmt[0x88]() )
    //  TCombatObject.DoDamage( target, target.GetHitPoints() )
```

Dispelling whatever grants **Summoned** deals damage equal to the target's **current hit points** —
an instant kill, credited to the dispeller (so the XP goes to them). The `vmt[0x148]` call is on the
`TUnit` at `[combatUnit+0x4C]`, not on the combat object — the item-aware accessor from
[[aow1-two-ability-query-apis]].

⚠ This is **combat-only**. The strategic `TDispelMagicAbilityTE.Execute` has no equivalent branch.

## 5. Targeting rules — and the asymmetry that matters

`CanTouch` @ `0x5576D264` / `CanTouchUnit` @ `0x5576D244` / `TDispelMagicAbilityUnitSelector.CanSelectUnit`
@ `0x5576DA48` all funnel into **`TAbstractUnit.CanDispelEnchantment` @ `0x5577F40C`**:

```
for each ability type A:
    ench = unit.AbilityToEnchantment(A)
    if ench <> nil and ench[+0xC] <> myPlayerIndex:  return TRUE
return FALSE
```

`ench[+0xC]` is the **source player** (set by `TEnchantment.SetSource` @ `0x5577C140`). So the target
must carry at least one enchantment **belonging to someone else**. Combat additionally requires both
parties to be `TCombatUnit`.

> ### ⚠ Legality is filtered by owner; the EFFECT is not.
> `CanDispelEnchantment` needs one *foreign* enchantment to make the target legal — but
> `ListEnchantments` (both paths) enumerates **every** enchantment on the unit with no owner filter,
> and every one of them is rolled. **Cleansing an enemy curse off your own unit will also roll to
> strip your own buffs from it.** Verified in both `TDispelMagicAbilityTE.Execute` and
> `TDispelMagicCA.Generate`.

## 6. Once per turn — and the known item bug

`SetEnabled(ability, unit, 0)` fires at the end of both paths; `NewTurn` @ `0x5576CEC4` re-enables.
`Investigation_Items.md` §3.6 records that `TDispelMagicAbility` is one of only two abilities
(with `THealing`) whose `SetEnabled` writes to the unit's own ability record, so an **item-granted**
Dispel Magic never gets disabled — **infinitely usable**. That analysis stands; nothing here changes it.

## 7. Not to be confused with

- **`UnitSpells.TDispelMagic`** (`0x557E8940`) — the *spell* a caster unit/hero casts. Separate
  class, its own `GetDispelMana` @ `0x557E89F8`, targets a party/unit rather than requiring touch.
- **`GlobalSpells.TDisjunctionSpellCaster`** — the global Disjunction spell, with its own
  `GetDispelChanceMax` / `SetDispelChance`.
- `TDispelMagicCA` (`0x5576C9C4`) is the shared effect CA; `TDispelMagicAbilityCA` is the touch
  ability's subclass of it, adding only the per-turn consume.

## 8. Levers

| want | where |
|---|---|
| stronger/weaker dispel per level | `GetDispelMana` @ `0x5576CEA8` — `level*10 + 20`, two immediates |
| shift the whole curve | the `+ 0x32` and `* -10` in `DispelChance` @ `0x5577C1A0` |
| raise/lower the 10 %/90 % clamps | same function |
| make a specific spell harder to dispel | that spell's `Create`, the `mov byte [reg+0x3c], imm` — **not** `Spells.pfs` |
| stop friendly enchantments being stripped | filter by `ench[+0xC]` inside the loops in `TDispelMagicAbilityTE.Execute` / `TDispelMagicCA.Generate` |
| more levels | **DONE — see §9** (`build_dispelmagic5.py`) |

## 9. AS BUILT — cap raised to V (`build_dispelmagic5.py`) — **APPLIED 2026-08-09, UNTESTED**

> **Status: applied, awaiting the user's in-game test.** Do NOT mark confirmed without it.
> Revert with `python build_scripts/build_dispelmagic5.py --undo` (surgical: restores the three
> sites and zeroes its own cave; touches no backup). Backup `AoWEPACK.dpl.pre-dispelmagic5` also
> exists but undo is the preferred path.

**Why this was cheap:** Dispel Magic has **no per-level value ladder**. Everything a level does
flows through `GetDispelMana = level*10 + 20`, so IV/V get strength 60/70 for free in all three
consumers. `GetSkillPoints` is `level*5` (`lea eax,[eax+eax*4]`) and `ExpandCost` is a flat **5**,
both cap-independent. Contrast Leadership, whose fixed-size bonus tables had to be relocated.

⚠ **Dispel Magic does not use the base `TMultiLevelAbility` cap `ability[+0x28]`.** It hard-codes 3
in two `cmp`s. Patching `[+0x28]` would have done nothing.

| # | site | change |
|---|---|---|
| 1 | `CanExpand` @ `0x5576D163` | `cmp eax, 3` → `5` (offer the upgrade) |
| 2 | `Expand` @ `0x5576D1D0` | `cmp byte [ebp+0xD], 3` → `5` (allow the increment) |
| 3 | `GetLevelName` @ `0x5576CF61` | the default arm was already a 5-byte `jmp 0x5576CFF8`; retargeted to the cave |
| 4 | cave `0x55821000` (88 B) | level 4 → `" IV"`, level 5 → `" V"`, else falls through to `0x5576CFF8` |

Resulting ladder — strength 30/40/50/**60**/**70**, skill cost 5 per buy:

| enchantment R | I | II | III | **IV** | **V** |
|---|---|---|---|---|---|
| 3 (Bless, Haste, Fury, Stone Skin, Enchant Weapon, Dark Gift) | 50 | 60 | 70 | **80** | **90** |
| 4 (Concealment, Fire Aura, Free Movement, Champion, Healing Water) | 40 | 50 | 60 | **70** | **80** |
| 5 (Liquid Form, Wind Walking) | 30 | 40 | 50 | **60** | **70** |
| 6 (Water Walking) | 20 | 30 | 40 | **50** | **60** |

V against an R=3 enchantment reaches the **90 % clamp** — level V is the ceiling; a VI would add
nothing against the common buffs.

**Cave choice:** `0x55821000`, an exclusive reservation of `0x55821000..0x558213FF`. The crowded
`0x5580Exxx` pocket was avoided on purpose — it is claimed by the combat-log and
true-seeing/invis features **even where it currently reads as zeros**. PIC via `call/pop/sub` for
the three data pointers; rel32 for the three calls.

**Verified without the game:** all four sites byte-checked in the live DLL after apply; `--undo`
round-tripped back to vanilla and re-applied; a whole-file diff against the backup shows exactly the
intended runs (the two cap bytes, 3 bytes of the retargeted `jmp` displacement, and the 88-byte
cave) and nothing else.

### Inioch's claimed dependency — checked and NOT applicable here

`patch_dispelmagic5_v1.py` declares a hard requirement on `patch_inherent_level_fix_v1.py`
("DM VMT+0x94 → own GetLevel, or level purchases would be silently discarded by
`UpdateDefaultAbilities`"). **Traced on this install and deliberately not included:**

- `TDispelMagicAbility` VMT `+0x94` is the base `TAbility.GetInherentLevel` @ `0x5574E954`, which
  **returns a constant 0**.
- `UpdateDefaultAbilities` @ `0x5574F518` is already hooked here at `0x5574F54D` by
  `build_leadership_fix.py`; the live cave @ `0x5580F100` resolves the ability and calls
  `ability->vmt[0x94]` — i.e. `GetInherentLevel`, for both the template and the destination.
- The discard branch needs `inherent(template) > inherent(dest)`. With a constant 0 on both sides
  that is unreachable, so the record — and the purchased level — is left alone.

Two other Inioch claims did not hold and were re-measured: it says `ExpandCost` is "a flat 1 skill
point" (here it is **5**), and it uses cave `0x5580E680`, which sits in the contested pocket above.

⚠ **If in-game testing shows purchased levels reverting, the `+0x94` repoint is the first suspect** —
the static argument above is sound but has not been exercised in play.

## 10. Not chased

- Which classes outside `UnitSpells.*` genuinely use `+0x3C` as dispel resistance (§3 caveat).
- `AbilityToEnchantment` @ `0x5577F3B4` — the ability-type → enchantment mapping was not read; it is
  what defines the universe of "enchantments" for both listing and legality.
- Whether the AI ever uses the ability (no `ExecuteAI` was looked for).
- The `Select` path at `0x5576DA54` (strategic target picking UI).
