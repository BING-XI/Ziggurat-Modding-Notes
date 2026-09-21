# Hit-chance increment audit — every site that would change for 10 pp → 5 pp

**Status: AUDIT COMPLETE 2026-08-18. The conversion it scoped was built, applied, and is
CONFIRMED WORKING in game (2026-08-24)** — this file stays the *site inventory*; the as-built
record, the scripts and the traps are in `FivePct_Conversion_Manifest.md` and
`FivePct_Doubled_Sources_Inventory.md`.
⚠⚠ **PREMISE CHANGED 2026-08-18:** the user chose to halve the slope **AND double every ATK/DEF/RES
source**, which is a verified perfect identity (hit chance and the full damage distribution are
bit-identical; the gain is that odd/half-steps become expressible). **§4c and §4g below were written
for a slope-only change and are VOID under the adopted plan** — see the notes inside them. §1, §2, §3
and §4a/b/e/f still stand. Conversion tracking lives in `FivePct_Conversion_Manifest.md`.

Inventory only, produced ahead
of a possible change from 10-percentage-point to 5-percentage-point granularity per point of stat
difference. Every byte below was read from the **live** `AoWEPACK.dpl` and diffed against
`Modding Resources/AoWEPACK_original_backup.dpl` (pristine). All VAs preferred-base (`0x55700000`).

**Headline:** the curve itself is **seven two-byte edits, all the same instruction** (was eight — `DispelChance` removed, see §1) — `add r32,r32` →
`nop; nop`. Four in the engine, three in existing Ziggurat caves. **5 pp is exactly representable at every
site** (no RNG change needed). The census is complete: an independent scan of **11 modules** found no other
implementation.

⚠ **But the eight edits are the small part.** The larger consequence is that **every ±1 stat modifier in the
game silently halves in value** — medals, morale, Leadership, blessings, curses, items, Parry, Charge — and
several systems change balance sharply without a single byte moving. See §3 and §4 before deciding.

Background on the two rolls: `Excess ATK minimum damage bonus.md` and
`Combat_Log_Implementation_Design.md` §0. ⚠ **Both of those docs state the 10 pp formula as fact and carry
numeric tables computed on `T = 10 − 2d`; both need re-deriving if this change ships.**

---

## 1. THE INVENTORY — the eight sites that encode the slope

Every one is `add r32,r32` immediately followed by a `×5` (`imul r32,r32,5` or `lea r,[r+r*4]`), i.e. the
×10 is built as ×2 then ×5. **NOPing the doubling leaves ×5.** No length change, no instruction-boundary
shift, and **no `.reloc` entry covers any of them** (checked against the parsed relocation table).

| # | VA | module / owner | function | rôle | bytes | → |
|---|---|---|---|---|---|---|
| 1 | `0x55725D9D` | AoWEPACK | `AoWE.HitRole` | **roll primitive** — `clamp(50+10d,10,90)` vs `RandInt(100)` | `03 C0` | `90 90` |
| 2 | `0x55725DCF` | AoWEPACK | `AoWE.HitRoleProbability` | float mirror of #1, ×0.01 — AI estimator | `03 C0` | `90 90` |
| 3 | `0x55725ED7` | AoWEPACK | `AoWE.ExecuteDamageRole` | ⭐ **the real to-hit for weapon strikes** — `T = 10−2d` over `RandInt(20)` | `03 C0` | `90 90` |
| 4 | `0x55725E3B` | AoWEPACK | `AoWE.DMDCtoDV` | the AI's closed-form model of #3 | `03 C0` | `90 90` |
| ~~5~~ | ~~`0x5577C1A4`~~ | AoWEPACK | ~~`TEnchantment.DispelChance`~~ | ⚠ **REMOVED 2026-08-18 — NOT a slope site.** See below | — | **leave** |
| 6 | `0x5580F6C3` | cave — `build_effectroll.py` | effect-roll log line | **displays** the odds in the combat log | `01 C0` | `90 90` |
| 7 | `0x558110C7` | cave — `build_combatlog_dll.py` (`_gotdef`) | damage log line | displays the odds | `01 C0` | `90 90` |
| 8 | `0x558118F0` | cave — `build_combatlog_dll.py` (`_tstats`) | touch log line | displays the odds | `01 C0` | `90 90` |

⚠⚠ **`TEnchantment.DispelChance` was wrongly listed here and has been REMOVED (2026-08-18).** It shares
the `clamp(50 + 10x, 10, 90)` *shape*, which is why a byte-pattern census finds it — but read directly it is
`clamp(dispelMana − 10×[ench+0x14] + 50, 10, 90)` with `GetDispelMana = 10×abilityLevel + 20`, i.e.
`clamp(10×(level − enchStrength) + 70, 10, 90)`. The difference is **ability level vs enchantment strength** —
neither is an ATK/DEF/RES stat, neither doubles. Halving its slope is a pure buff to dispelling, and **no
combination of edits makes it an identity** because the `+50` and `+20` constants do not scale. Leave it, and
leave `TDispelMagicAbility.GetDispelMana @0x5576CEB7` and `UnitSpells.TDispelMagic.GetDispelMana @0x557E89F8`
alone with it. **The slope patch is SEVEN sites: 4 engine + 3 caves.**

**Sites 1–4 are byte-identical to pristine at the doubling instruction** — this is a vanilla-relative edit,
not a re-tune of someone else's patch. (Sites 1 and 2 carry an unrelated live re-encoding three bytes later,
`lea eax,[eax+eax*4]` → `imul eax,eax,5`; see `Excess ATK minimum damage bonus.md` §7 for its unknown
provenance. It does not interfere.)

### ⚠ Three traps in that table

1. **`0x55725E3B`, NOT `0x55725E3D`.** The DMDCtoDV doubling is at `…E3B`; `…E3D` is the `B9` opcode of
   `mov ecx,0xa`. Verified: `03 C0 | B9 0A 00 00 00 | 2B C8`. Writing `90 90` at `…E3D` corrupts the `mov`
   and crashes on the first AI damage estimate. (An earlier working note had this address wrong.)
2. **The caves encode `add eax,eax` as `01 C0`, the engine as `03 C0`.** Both are valid encodings of the
   same instruction. **A byte-pattern search keyed on `03 C0` finds five sites and silently misses all
   three caves** — which is exactly how a combat log ends up printing the old odds next to a roll made on
   the new curve.
3. **Sites 3 and 4 do not go through `HitRole` at all.** Ordinary weapon strikes never call it (§ "There is
   no separate to-hit roll" in the Excess doc). Changing only `HitRole` would put weapon attacks and ability
   effects on **different curves**. All of 1–4 must ship in one pass.

### Resolution — 5 pp is exact everywhere

- `HitRole` / `HitRoleProbability`: `RandInt(100)` → 1 pp steps → exact.
- `ExecuteDamageRole` / `DMDCtoDV`: `RandInt(20)` → **one tick is exactly 5 pp** → exact.
- 2.5 pp would **not** be representable and would require widening the die plus rescaling the intercept
  (10), the interpolation base (18) and the two flat bands — a much larger job. 5 pp is the natural step.

### The resulting curve

`P = clamp(50 + 5d, 10, 90)`. Verified by enumeration on the post-edit bytes: `d=0` → 50%, `d=+1` → 55%,
`d=+8` → 90% (pinned), `d=−8` → 10% (floor). The clamp endpoints move from `d = ±4` to `d = ±8`.
**Leave `0x0A`/`0x5A` alone** — at the new slope they bind at exactly the same place as
`ExecuteDamageRole`'s structural cap (`T ≤ 2 ⇒ d ≥ 8`), so the two systems stay in lockstep for free.

⚠ The endpoints are **not symmetrically movable** if you ever want to: `HitRole`'s are literal constants, but
`ExecuteDamageRole`'s 90%/10% pins are the two flat 2-in-20 bands (`cmp ecx,1` `@0x55725EC3`,
`cmp ecx,0x12` `@0x55725ECC`) — and **those exact constants are read back by `build_combatlog_dll.py`'s
crit/fumble tests** (`@0x558111BF`, `@0x55811399`). Treat `[10,90]` as immovable.

---

## 2. The census is complete — what was scanned and found clean

Independent byte scan of **11 modules** (`AoWEPACK`, `AoWTCPCK`, `aowInt`, `AoW.exe`, `AoWDevEd.exe`,
`AoWInterface`, `HSEPack`, `Enginep`, `Gfxepack`, `AOWTools`, `AbilityP`), every CODE/`.text` section, for
`cmp r32,0x5A` in all three encodings:

- **AoWEPACK: exactly 7 hits** — `HitRole`, `HitRoleProbability`, `DispelChance`, the three caves, and one
  out-of-scope counter at `0x557B1709`.
- **Every other module: zero.** Also zero `imul r,r,5` and zero `lea r,[r+r*4]` in AoWTCPCK. The `+50`
  companion is absent from all of them too.
- `AoWTCPCK.dpl`: all **200** `RandInt`/`TAoWHSMap.Random` sites enumerated with their bounds (28×d10,
  18×d50, 14×d100, 13×d360, 13×d20, …). **None is a stat-derived hit test** — the d100s are variant
  selection. It imports `ExecuteDamageRole`/`Ex` and calls them from 38 sites (all walls/terrain/structures)
  but has no maths of its own.
- `aowInt.dpl`: imports nothing from AoWEPACK. `AoWDevEd.exe`: no combat maths, no hit-chance UI.
- `AoW.exe`: imports exactly **two** combat-math symbols — `GetDispelChanceMax` and `SetDispelChance`
  (Disjunction UI). Nothing else.
- **No probability lives in data.** `Spells.pfs` tag census (108 records): no power, no chance field.
  `Ability.pfs` (151 records): none. Zero hit-chance `%` strings in any binary or DFM — the only user-facing
  percentage literal in the whole install is Ziggurat's own `'% vs res '` (the `build_effectroll.py` cave).

*Stated blind spot:* a clamp using a register-held 90, a `cmov`, or `cmp al,0x5A` would evade the scan. The
`+50` companion being absent everywhere makes the negative solid.

⚠ **Any `AoW.exe` edit must be mirrored in `AoWCompat.exe`** (one byte apart). No `AoW.exe` edit is needed
for this change.

---

## 3. NOT a code edit — but every stat point halves in worth

**This is the part most likely to be missed, and it is bigger than §1.** After the change, ±1 stat is worth
5 pp instead of 10 pp. Every one of these is denominated in the unit whose price is being halved. None
requires a code edit; all change balance.

**Ability stat modifiers** — VMT-dispatched accessors with **zero rel32 xrefs**, so no call-graph scan sees
them (imm at VA+1):

| ability | VA | live | pristine |
|---|---|---|---|
| Nature's Blessing ATK/DEF/RES | `0x557B9CC0/C4/C8` | 0 / +1 / +2 | +1/+1/+1 |
| Bloodlust ATK/DEF/DAM | `0x557B9DB4/B8/BC` | +2 / −1 / +2 | +1/−1/+2 |
| Poisoned ATK/DEF/RES/DAM | `0x557B9E68/6C/70/74` | −2 / 0 / 0 / −2 | −1/−1/−1/−1 |
| Entangled DEF | `0x557B9FEC` | −2 | same |
| Frozen DEF | `0x557BA0B4` | **+2** | **−2** (Ziggurat flipped the sign) |
| Webbed / Stunned DEF | `0x557BA320` / `0x557BA550` | −2 | same |
| Vertigo ATK/DEF | `0x557BAC5C/60` | −2 / −2 | same |
| Cursed DEF/RES | `0x557BAD90/94` | −2 / −2 | same |
| Stone Skin DEF | `0x557BAF40` | +2 | same |
| Enchanted Weapon ATK/DAM | `0x557BB0EC/F0` | +2 / +2 | +1/+1 |
| Fury ATK/DEF | `0x557BB35C/60` | +3 / −1 | +2/−1 |
| Blessed DEF/RES | `0x557BB5E4/E8` | +1 / +2 | +1/+1 |
| Dark Gift DAM | `0x557BB730` | +2 | +1 |
| High Prayer DEF/RES | `0x557BB80C/10` | +1 / +1 | same |

**Exported data tables** (DATA section — a code scan never finds these):
`DefenseRankProgression` `0x558E83C4`, `AttackRankProgression` `0x558E83C8`, `DamageRankProgression`
`0x558E83CC`, `ResistanceRankProgression` `0x558E83D0`, `HitsRankProgression` `0x558E83D4`,
`MoraleResistanceModifier` `0x558E83D8`, `MoraleDefenseModifier` `0x558E83E0`.
⚠ **`LeadershipAttackProgression`/`…Defense` `0x558E83E8`/`0x558E83EC` are DEAD** — `TLeadershipAbility.
GetAttack/GetDefense` (`0x557661FC`/`0x55766210`) were repointed to a cave (`0x5580F0C0`/`0x5580F0C8`,
`build_leadership4.py`). Re-tune Leadership through that script, not the exported table.

**Conditional attack penalties:** Parry `sub dword [ebx],N` `@0x55767BE1` (imm8 at `0x55767BE3`, live `04`,
pristine `02`); the −2 ranged wall penalty (`@0x5576EB1A`); Ziggurat's invisibility −1 melee / −3 ranged
(`build_invis_penalty.py`); Charge; the slayer +2/+3 bonuses.

**Item bonuses:** `ITEMS.PFS` tag `0x0B` ATK (23 items, +1..+3), `0x0C` DEF (28), `0x0D` DAM (22),
`0x0E` RES (23).

**Fixed-power immediates** — these are the "attack side" of every secondary-effect roll, and there are
**seven** groups, not six:

| site | imm addr | live | opposed by |
|---|---|---|---|
| `ExecuteDamageEffectsRole` ×6 | `0x55781C31/C91/CE3/D35/D87/DE7` | 5,5,5,5,5,5 (pristine 4,6,3,4,3,2) | `vmt+0xCC` RES |
| `TStrikeCA.Generate` roll 1 | `0x55766914` | 5 | RES |
| `TStrikeCA.Generate` roll 2 | `0x5576694E` | 7 | RES |
| `ExecuteLifeMasteryFearRole` | `0x55780BEB` | 4 | RES |
| `ExecuteDeathMasteryCurseRole` | `0x55780CB3` | 6 | RES |
| `TBurningAbility.NewCombatTurn` | `0x557BA464` | 10 | RES |
| `ExecuteResistanceRole` | `sub edi,2` imm8 `0x55781B81` | −2 | RES |

**⭐ Touch abilities — `GetTouchAttack` (added 2026-08-18; missed by the original sweep).**
`TTouchAbility.CombatTouchRole @0x557681B0` is **two ANDed `HitRole`s**: roll 1 = attacker
`GetAttack(vmt+0x6c)` − target `GetDefense(vmt+0x70)` `@0x557681D6`; roll 2 = `GetTouchAttack(vmt+0x10c)`
− target `GetResistance(vmt+0x74)` `@0x55768216`. Both must pass, so the family caps at 0.9 × 0.9 = **81%**.
Roll 2's attack side is a per-ability virtual — nine overrides, and **Ziggurat retuned five of them plus
the whole Turn Undead ladder**:

| ability | VA | live | vanilla |
|---|---|---|---|
| `TTouchAbility` (base) | `0x557680CC` | **−10** | −10 |
| `TPossessAbility` | `0x55769BE8` | **7** | 5 |
| `TWebAbility` | `0x5576A20C` | **7** | 4 |
| `TEntangleAbility` | `0x5576A810` | 7 | 7 |
| `TInvokeDeathAbility` | `0x5576B84C` | **9** | 6 |
| `TDominateAbility` | `0x55770664` | **5** | 6 |
| `TCharmAbility` | `0x55770798` | 5 | 5 |
| `TSeduceAbility` | `0x55770978` | **5** | 4 |
| `TTurnUndeadAbility` I–IV | `0x5576B1F4` (ladder) | **9, 10, 11, 12** (default 4) | 4, 5, 6, 7 |

⚠ The base **−10 is a fail sentinel**, not a value: `cmp esi,-0xA / je` `@0x557681FC` returns false
outright. Any touch ability that does not override `GetTouchAttack` can never succeed through
`CombatTouchRole`.

⚠⚠ **Touch compounds the slope change twice.** Because success is a *product* of two clamped rolls, both
move toward 50% and the product moves toward 25% — a larger swing than any single-roll ability. Worked
against a developed attacker (ATK 12) versus a DEF-3 target, combined success today → at 5 pp:

| ability | vs RES 3 | vs RES 5 | vs RES 8 |
|---|---|---|---|
| Seduce / Charm / Dominate (5) | 63% → 54% | 45% → 45% | 18% → **31.5%** |
| Web / Entangle / Possess (7) | 81% → **63%** | 63% → 54% | 36% → 40.5% |
| Invoke Death (9) | 81% → 72% | 81% → **63%** | 54% → 49.5% |
| Turn Undead IV (12) | 81% → 81% | 81% → 76.5% | 81% → **63%** |

**Up to −18 pp** wherever roll 2 was pinned at 90% and un-pins, and up to **+13.5 pp** against
high-resistance targets. The strong touch abilities — precisely the ones Ziggurat buffed — lose the most.
This family needs its own balance pass if the slope changes.

**Combat-spell powers** are code immediates in each `Create` — never enumerated anywhere before:
`TMindDecay` `0x557F8581` = 6 · `TSlow` `0x557F88F1` = 9 · `TEntangle` `0x557F8AC9` = 7 ·
`TTerror` `0x557F9A81` = 8 · `TOoze` `0x557F95F1` = 0.
⚠ **Terror is encoded FIVE times, not twice** (corrected 2026-08-18) — `+0x34 = 8`, plus hard-coded
`mov eax,8` at `0x557F9887` (`TFastCombatTerrorCA`) and `0x557F9A0B` (`TTacticalCombatTerrorCA`), plus
imm32 at `0x557F9CA6` (`TTerror.fcGetDamageValueEx`) and `0x557F9D8F` (`tcGetDamageValueEx`). Re-tune any
subset and auto-resolve, tactical and the AI estimator desynchronise from each other.
⚠ Also: only **five** of the thirty combat-spell powers were listed here. The full set of 30 `+0x34`
values is in `FivePct_Conversion_Manifest.md`; leaving any un-doubled while RES doubles **inverts** the
spell (`TColdBreath` power 12 vs RES 5 goes 85% → 10%).

---

## 4. Second-order balance — quantified against the installed data (179 units)

**4a. ⭐ City walls.** ⚠ **CORRECTED 2026-08-18 — there are TWO wall defence values, not one.**
**Auto-resolve** (AoWEPACK): `TCombatWall.GetDefense @0x55725C04` and `TWallUnit.GetDefense @0x55783658`
are both `xor eax,eax` = **DEF 0**. **Manual tactical combat** (AoWTCPCK): `CityWall.TCityWall.GetDefense`
@`0x00405AD5` returns **−2** (`mov dword [ebp-8],0xFFFFFFFE`, imm32 @`0x00405AD8`) — i.e. it *gives the
attacker +2*. The figures below are computed on DEF 0 and are therefore correct for **auto-resolve only**;
the tactical path runs two points more favourable to the attacker. Versus a wall `d` = the attacker's
entire ATK (+2 in tactical).

> **Units pinned at the 90% cap versus a wall: 111/179 (62%) today → 6/179 (3%) after.**
> Median-ATK-4 unit versus a wall: 90% → 70%.

And because the same `T` drives the damage ramp, wall attacks simultaneously lose their minimum-damage
floor. All 38 of `AoWTCPCK.dpl`'s `ExecuteDamageRole` call sites are walls/terrain/structures — **sieges are
where this change lands hardest.**

**4b. Base-stat saturation nearly vanishes.** Over all 32,041 ordered unit pairs: `d ≥ +4` 13.4% → `d ≥ +8`
**0.5%**; `d ≤ −4` 2.2% → `d ≤ −8` **0.1%**. The unpinned band goes **84.4% → 99.5%**. The `[10,90]` clamp
becomes near-dead code for base stats and only bites once modifiers stack. That is a real design shift —
*stat gap matters less, modifier stack matters more* — and it is arguably the point of the change.

**4c. ~~Secondary effects move the WRONG WAY~~ — ⚠ VOID UNDER THE ADOPTED PLAN.** This section assumed
RESISTANCE would NOT be doubled. Under the adopted plan RES doubles alongside the fixed powers, so these
rolls are an exact identity and none of the numbers below apply. Retained only because the reasoning is
correct for a slope-only change and would otherwise be re-derived. **Original text:**

**4c. Secondary effects move the WRONG WAY.** Every `HitRole` caller except one passes
`FIXED_POWER − RES`, so halving the slope compresses those chances **toward 50%**, making them *more*
uniform and *less* stat-differentiated — the opposite of the change's purpose:

- Burning (power 10): mean landing chance **87.0% → 78.3%**; units at the 90% cap **151/179 → 20/179**.
- Effect rolls (power 5): mean **56.8% → 53.3%**; units at the 10% floor **4/179 → 0/179**.

**There is no data-side compensation that restores the old curve** — doubling a power immediate fixes only
`RES = 0` and overshoots everywhere else, because the resistance side is not doubled. If you want secondary
effects to keep their spread you must either leave `HitRole` at 10 pp (accepting two different curves) or
re-tune all seven power groups by hand against the RES distribution.

**4d. The excess-ATK damage premium halves in rate.** Conditional mean damage given a hit stays ≈
`1 + (M−1)/2` for every `T`, but the *minimum-damage* compression now starts at `d > 10` instead of `d > 5`
and progresses half as fast. High-ATK/high-damage units lose roughly the top half of their premium; the
effect remains **exactly zero at damage 1**. Net: a relative nerf to heavy hitters and to sieges, neutral
for chaff. (The tables in `Excess ATK minimum damage bonus.md` §2 are all computed on the old slope.)

**4e. The AI diverges in TWO places if `DMDCtoDV` is missed.** It also feeds the **tactical** AI in
AoWTCPCK via imported `TMeleeRound.GetAttackerDV`/`GetDefenderDV` (IAT `0x0046E660`/`0x0046E65C`), not just
the strategic one.

**4f. Disjunction silently doubles in relative strength.** `TDisjunctionSpellCaster` is a flat
player-chosen percentage (cap raised `0x4B→0x64` live) and never touches `DispelChance`. Halve the Dispel
Magic curve and Disjunction becomes twice as good by comparison. Its UI lives in `AoW.exe`
(`GetDispelChanceMax` called `@0x00432F26`, `SetDispelChance` `@0x0043318D`).

**4g. ~~New parity artefact~~ — ⚠ VOID UNDER THE ADOPTED PLAN.** With stats doubled, `d' = 2d` so
`T = 10 − d'` is bit-identical to today's `T = 10 − 2d` and stays even; the asymmetric-rounding artefact
never arises. Applies only to a slope-only change. **Original text:**

**4g. New parity artefact.** After the edit `T` is odd for odd `d`, so `18−T` is odd and the `shr edx,1`
rounding term floors asymmetrically — damage rounding differs by ≤1 between even and odd `d`. Percentages
still agree between paths. Today `T` is always even, so this artefact does not exist. Harmless, but it will
look like a bug to anyone reading damage logs closely.

---

## 5. ⚠ The one site where 5% is NOT exactly representable

`UnitSpells.TDispelMagic.GetDispelMana @0x557E89F8` — the **spell** producer feeding `DispelChance`
(distinct from the **ability** producer). Live bytes `@0x557E8A0C`: `C1 E0 04 2B C2 83 C0 19` =
**`15·L + 25`**. The exact half is `7.5L + 12.5`. Two sub-agents proposed different roundings (`7L+13` vs
`8L+13`) without noticing they disagreed.

**This is a design decision, not a mechanical edit.** The ability-side producer
`TDispelMagicAbility.GetDispelMana @0x5576CEA8` = `10L + 20` halves exactly to `5L + 10`
(`0x5576CEB7`: `03 C0 8D 04 80` → `8D 04 80 90 90`, and `83 C0 14` → `83 C0 0A`).

---

## 6. Scripts and docs that go stale

Per the recording convention these must be fixed **at source**, not contradicted:

- **`build_effectroll.py`** — hard-codes `clamp(50 + 10*(5-res), 10, 90)` with worked RES 5/7/9 examples.
- **`build_stormeffectroll.py`** — same formula plus the vanilla per-type strengths.
- **`build_dispelmagic5.py`** — its whole rationale quotes `GetLevel*10 + 20` and
  `clamp(mana − 10*ench + 50, 10, 90)`; levels IV/V become worth half.
- **`build_combatlog_dll.py`** (~line 31) — states the hit% formula outright.
- **`Excess ATK minimum damage bonus.md`** and **`Combat_Log_Implementation_Design.md` §0** — both state the
  10 pp formula as fact with full numeric tables on `T = 10 − 2d`.
- **`Ziggurat Engine Notes.xlsx`** — `misc!C41` "To-hit increment per ATK/DEF/RES" (feeds the Ziggurat
  Manual), plus `C42` (Parry DEF +4), `C44` (Charge DAM +3) and `C36/C37/C38` (stat ranges).

⚠ **`build_touchlog_gate.py` restores *stock* bytes at `0x55725EBC` / `0x5576B55C` / `0x557681B0` /
`0x557681D6` / `0x55768216`.** Harmless for a 2-byte slope NOP; **fatal** for any larger rewrite of
`ExecuteDamageRole`. Other scripts referencing these functions: `build_combatlog_dll.py`,
`build_effectroll.py`, `build_stormeffectroll.py`, `build_firefeed.py`, `build_dispelmagic5.py`.

---

## 7. If this is built

Shape suggested by the audit — **not written, not applied**:

- **One script, one pass, all eight bytes-pairs.** Sites 1–5 and 6–8 must not be separable; a partial apply
  leaves weapon strikes and ability effects on different curves, or the log lying.
- Verify-before-write against **either** `03 C0`/`01 C0` (unpatched) **or** `90 90` (already applied) so it
  is idempotent, per the project convention.
- Surgical `--undo` restoring `03 C0` / `01 C0`. No backup needed — it is 16 bytes total.
- ⚠ Locate the cave sites by **cave-relative offset from the owning script's cave base**, not by scanning
  for `03 C0` — see §1 trap 2. Better: have `build_effectroll.py` and `build_combatlog_dll.py` emit ×5
  directly, so the display copies can never drift from the engine again.
- Decide §5 (`15L+25`) and §4c (secondary-effect powers) **before** building; both are balance calls.

---

## Cross-references

- `Excess ATK minimum damage bonus.md` — the two rolls, why weapon strikes never call `HitRole`, the
  damage-compression coupling, walls at DEF 0. ⚠ its tables assume the 10 pp slope.
- `Combat_Log_Implementation_Design.md` §0 — base decode of both rolls.
- `Investigation_Storm_Protections.md` — the six `ExecuteDamageEffectsRole` power immediates.
- Memory: `[[aow1-combat-math-decoded]]`.
