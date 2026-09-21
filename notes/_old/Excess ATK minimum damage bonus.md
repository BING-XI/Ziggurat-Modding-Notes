# Excess ATK → minimum-damage bonus — RE investigation

**Status: RE COMPLETE 2026-08-18 — NO PATCH, NOTHING APPLIED.** Pure analysis of stock behaviour. Every
address below was read from the **live** `AoWEPACK.dpl` with `re_tools/dasm.py` and byte-diffed against
`Modding Resources/AoWEPACK_original_backup.dpl` (pristine); Ghidra's vanilla image was used only for
xrefs and for the vanilla-side clamps. All VAs are preferred-base (`0x55700000`).

**The question:** *is there a special bonus when the attacker has a huge amount of ATK in excess of the
target's DEF?*

**The answer:** **yes, but it is a damage bonus, not a hit-chance bonus, and nothing on screen shows it.**
Hit chance is hard-clamped at 90% and stops improving at ATK−DEF = +4. The same difference keeps feeding
the damage roll, where it raises the *minimum* damage a landed blow can deal — at large differences the
low rolls stop existing entirely. The AI models this correctly; the player is shown nothing.

Core to-hit / damage-roll decode lives in `Combat_Log_Implementation_Design.md` §0 — **this doc does not
restate it**, it covers only the excess-ATK regime and corrects two things §0 got slightly wrong.

> ⚠ **Every table below assumes the stock 10-percentage-point slope (`T = 10 − 2d`).** A change to 5 pp
> was under consideration 2026-08-18 — see **`HitChance_Increment_Audit.md`** for the full site inventory.
> If that ships, §2's damage tables, §5's reachability figures (13.4% of pairs at `d ≥ +4`) and the wall
> analysis all need re-deriving on `T = 10 − d`; the compression would start at `d > 10` instead of `d > 5`
> and progress half as fast.

---

## 1. There is no separate to-hit roll on the weapon-attack path

⚠ **This is the single most misleading thing about the system, and it is easy to re-derive wrongly.**

A normal melee or ranged strike **never calls `HitRole`**. `AoWE.ExecuteDamageRole @0x55725EAC` is
simultaneously the hit test *and* the magnitude — a "miss" is that function returning 0.

```
AoWE.ExecuteDamageRole(EAX = M (max damage), EDX = d (attack − defence)) → EAX
    if M <= 0                    return 0
    R = RandInt(20)                          ; 0..19 uniform            @0x55725EBC
    if R <= 1                    return 0    ; flat 10% fumble          @0x55725EC3
    if R >= 18                   return M    ; flat 10% auto-max        @0x55725ECC
    T = 10 - 2*d                             ; NO CLAMP                 @0x55725ED5
    if T > R                     return 0    ; the real miss test       @0x55725EE2
    if T >= 18                   return 0    ; DEAD CODE — see §3       @0x55725EE6
    D = 18 - T                               ; = 2d + 8
    return 1 + trunc( ((M-1)*(R-T) + (D>>1)) / D )      ; round-half-up @0x55725EEB..F02
```

`P(non-zero) = clamp(50 + 10*d, 10, 90)%` falls out of this by construction, which is why it matches
`AoWE.HitRole @0x55725D98` exactly — but they are **not two implementations of one thing**. `HitRole` is
used by 18 *secondary* sites only (status effects, touch abilities, resistance rolls). The two run in
sequence: `TDamageCA.Generate @0x55729C20` calls `vmt+0x110` for the hit, then — only on a hit —
`vmt+0x118 ExecuteDamageEffectsRole`, which rolls `HitRole` per effect. **A status effect therefore lands
at most 0.9 × 0.9 = 81%.**

`AoWE.HitRole` itself is unremarkable: `clamp(50 + 10*d, 10, 90)` vs `RandInt(100)`, `setg` (not `setge` —
checked; `setge` would give 91%).

### The difference arrives unclamped

Verified end-to-end, no clamp anywhere between the stats and the roll:

| step | VA | what it does |
|---|---|---|
| `TMeleeRound.CreateStrikeCA` | `0x55767E68` | `attack = GetAttack(vmt+0x6c) + strikeMod` as a **byte** |
| `TStrikeCA.Generate` | `0x557668B4` | forwards its three stack params verbatim |
| `TDamageCA.Generate` | `0x55729C42/46` | `movsx ecx, byte [ebp+0xc]` (damage), `movsx edx, byte [ebp+0x10]` (attack) |
| `TCombatObject.ExecuteDamageRole` | `0x557269F0` | `GetDefense(vmt+0x70)`, `movsx eax,al`, `sub eax,edx`, straight into EDX |
| `AoWE.ExecuteDamageRole` | `0x55725EAC` | consumes it |

Only 4 call sites reach `0x55725EAC`: `0x55726A33`, `0x55726AC8` (the `Ex` form, which uses
`GetResistance vmt+0x74` when its flag byte is 1), `0x55781B0D`, and the fire-heal cave `0x5580DA61`.
All four do the same unclamped `sub`. **No descendant overrides `vmt+0x110`/`+0x114`** — slot `0x110` is
`0x557269F0` in all four TCombatObject-family VMTs (`0x557158EC`, `0x55715A94`, `0x55715C40`, `0x5571D4BC`).

**Tactical combat shares the roll.** `AoWTCPCK.dpl` imports `AoWE.ExecuteDamageRole` (IAT `0x0046E7F4`,
thunk `0x004024F4`) and calls it from 38 sites — all walls/terrain/structures — and its
TCombatObject-descendant VMTs inherit the wrappers. It has **no combat maths of its own**. `aowInt.dpl`
imports nothing from AoWEPACK; `AoW.exe` imports only HP-bar/display helpers.

---

## 2. The bonus itself — excess ATK buys minimum damage

`T = 10 − 2d` goes negative once `d > 5`, so `D = 18 − T = 2d + 8` grows and the scaling ratio
`(R−T)/D → 1` for **every** surviving roll. The distribution compresses upward against the max.

**Max damage 5** (the median unit in this install is damage 3, mean 3.18):

| d | T | hit% | E[dmg] | min dmg on a hit | P(rolled == max) |
|---:|---:|---:|---:|---:|---:|
| −5 | 20 | 10% | 0.50 | **5** | 10% |
| −4 | 18 | 10% | 0.50 | **5** | 10% |
| −3 | 16 | 20% | 0.70 | 1 | 10% |
| 0 | 10 | 50% | 1.70 | 1 | 15% |
| +3 | 4 | 80% | 2.50 | 1 | 15% |
| **+4** | 2 | **90%** | 2.90 | 1 | 20% |
| +5 | 0 | 90% | 3.00 | 1 | 20% |
| +6 | −2 | 90% | 3.15 | 2 | 20% |
| +9 | −8 | 90% | 3.50 | 3 | 25% |
| +10 | −10 | 90% | 3.55 | 3 | 25% |
| +15 | −20 | 90% | 3.80 | 3 | 30% |
| +20 | −30 | 90% | 4.00 | 4 | 40% |
| +30 | −50 | 90% | 4.10 | 4 | 50% |
| +60 | −110 | 90% | 4.50 | **5** | 90% |

Hit chance is frozen from +4 onward; expected damage still climbs **55%** further (2.90 → 4.50).
At `d = +20` a 5-damage strike deals only **0 (10%), 4 (50%), or 5 (40%)** — rolls of 1, 2 and 3 have
been squeezed out of existence.

**Max damage 10:**

| d | hit% | E[dmg] | min dmg on a hit |
|---:|---:|---:|---:|
| 0 | 50% | 3.00 | 1 |
| +4 | 90% | 5.20 | 1 |
| +5 | 90% | 5.80 | 2 |
| +6 | 90% | 6.00 | 3 |
| +8 | 90% | 6.50 | 4 |
| +10 | 90% | 6.80 | 5 |
| +15 | 90% | 7.40 | 6 |
| +20 | 90% | 7.75 | 7 |
| +30 | 90% | 8.10 | 8 |

### ⚠ The effect scales with the damage rating — and is exactly ZERO at damage 1

E[dmg] going `d = +4 → +20`:

| max damage | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 |
|---|---|---|---|---|---|---|---|---|---|
| at +4 | 0.90 | 1.40 | 1.90 | 2.35 | 2.90 | 3.30 | 4.25 | 5.20 | 6.15 |
| at +20 | 0.90 | 1.80 | 2.50 | 3.20 | 4.00 | 4.70 | 6.25 | 7.75 | 9.25 |
| gain | **+0%** | +29% | +32% | +36% | +38% | +42% | +47% | +49% | +50% |

A 1-damage unit gets **nothing** from excess attack past +4 — the formula's `(M−1)` factor is zero, so
every landed blow is 1 regardless. **Excess ATK is worth roughly nothing on chaff and a great deal on
high-damage units.** This is the design-relevant consequence.

---

## 3. ⚠ TRAP — the `T >= 18` guard at `0x55725EE6` is DEAD CODE

**Do not re-derive this wrongly.** It is extremely tempting to attribute the `d <= −4` behaviour to
`cmp esi,0x12 / jge` at `0x55725EE6`, because `d = −4` makes `T = 18` exactly. That is wrong.

To *reach* `0x55725EE6` you must have passed `cmp ecx,0x12 / jl` (so `R <= 17`) **and** failed
`cmp esi,ecx / jg` (so `T <= R`). Therefore `T <= 17 < 18` always, and the `jge` **can never be taken**.
Enumerated exhaustively over `d ∈ [−200,200] × R ∈ [2,17]`: fires 0 times.

It is a divide-by-zero safety net for the later `idiv edi` where `edi = 18 − T` (zero iff `T == 18`).
What actually zeroes every middle roll at `d <= −4` is the **preceding** `cmp esi,ecx / jg` at
`0x55725EE2` — `T >= 18 > 17 >= R`. Removing the `0x12` guard would change no outcome.

(Ghidra renders it honestly as the redundant `|| (0x11 < iVar2)` disjunct. `Combat_Log_Implementation_
Design.md` §0's pseudocode omits the guard entirely, which is — by luck — behaviourally correct.)

---

## 4. The mirror case: at ATK−DEF ≤ −4, every landed blow is MAXIMUM damage

Because `R >= 18` is tested **before** `T` is even computed, the auto-max branch is completely
independent of the stat gap. At `d <= −4` no middle roll can survive, so the *only* non-zero outcomes are
the two auto-max rolls.

**A hopelessly outmatched attacker connects exactly 10% of the time, and every single connection deals
the full damage rating.** Further negative difference has zero observable effect — `d = −4` and `d = −40`
are identical.

⚠ **Qualification:** that is the *raw roll's* return. What the target actually takes is filtered by
`TCombatObject.ExecuteDamageRole @0x557269F0`, which:
- returns **0 without rolling** if `damageTypes & ~GetImmunityTypes(vmt+0x7c) == 0` (fully immune)
  → immunity gives **0%**, not 10%;
- **halves** the rolled result (round-half-up, `inc/sar/jns/adc`) if the target is Protected against all
  remaining types;
- and on **this install** is further hooked at `TAbstractUnit.ExecuteDamageRole @0x55781AC4 → cave
  `0x5580DA20`` (fire-heals-fire), which `neg`s the result for fire-affinity units.

`TCombatObject.ExecuteDamage @0x55726C58` then clamps to remaining HP. The unqualified "10% of blows for
full damage" holds exactly only at the **bare** call sites — in practice `AoWTCPCK.dpl`'s city-wall damage.

---

## 5. Which differences are actually reachable

**The operative caps are engine clamps, not the data — and Ziggurat raised all four.**

| | vanilla | live (Ziggurat) |
|---|---|---|
| `TUnit.GetAttack @0x557829EC` | clamp **[1,10]** | **[0,20]** (via cave `0x5580C0F7`) |
| `TUnit.GetDefense @0x55782A40` | clamp **[1,10]** | **[0,30]** |
| `THero.GetAttack @0x55788360` | clamp **[1,10]** | **[0,30]** |
| `THero.GetDefense @0x55788454` | clamp **[1,10]** | **[0,30]** |
| **max possible ATK−DEF** | **+9** | **+30** (+38 with post-clamp melee bonuses) |

So **in vanilla the whole high-end regime barely exists** — `d` cannot exceed +9, where a 5-damage strike
averages 3.50 against 2.90 at +4. The dramatic `d = +20` numbers are a **Ziggurat-only** phenomenon,
created by widening the clamps and by allowing DEF **0** (vanilla floored it at 1).

**Base data** (`Release/Unitres.pfs`, 179 records, Ziggurat): ATK 1–12 (median 4), DEF 1–10 (median 3),
damage 1–10 (median 3). Largest base unit-vs-unit difference **+11** (Syron 12 vs the eleven DEF-1 units).
Vanilla data: ATK 1–8, largest base difference **+7**.
Over all 32,041 ordered pairs, **13.4% already sit at `d >= +4`** — i.e. one attack in seven is already in
the pinned-accuracy regime before any modifier.

**⭐ City walls are the big one.** `TCombatWall.GetDefense @0x55725C04` and
`TWallUnit.GetDefense @0x55783658` are both literally `xor eax,eax; ret` — **defence 0**. So *any*
attacker versus a wall sits at `d` = its entire attack value. This is by far the most common high-`d`
case in normal play, and it is why siege damage feels so much more consistent than field damage.

**Realistic high end:** a developed hero reaches ATK ≈ 23–27 (base 4 + 15 bought at 6 skill points each +
Sword of Power +3 + Ring of Power +1 + Leadership IV +2 + Bloodlust +2), giving `d = +25` versus the
60-strong DEF-2 tier and `+27` versus a wall or a debuffed target.

**⚠ Ranged attacks use a completely different table.** `TRangedAttackAbility.GetAttackRA @0x5576E65C`
returns a per-ability constant from `[ability+0x2A]` (2–7 in this install), **not** the unit card's ATK.
Marksmanship adds up to +8, then −2 underground without Night Vision, −2 behind a wall, −3 versus an
Invisible target without True Vision. Ranged tops out near `d = +19`. Never quote a melee `d` figure for
a ranged attack.

---

## 6. Who sees the effect: the AI does, the player does not

This is the interesting asymmetry, and it is **not** what you would guess.

**The AI models it accurately.** `AoWE.DMDCtoDV @0x55725E30` is a *closed-form analytic expectation* of
the real roll — same `T = 10 − 2d`, same 18-wide span, same `(M−1)` slope, `×5` at the end to convert a
sum over `RandInt(20)` into 100× expected damage. It has a dedicated `T < 0` arm (`@0x55725E6C`) with a
quadratic correction, i.e. **it explicitly models the compression regime**. It tracks `100 × E[real]` to
within ~0.4% mean error for `d >= +4`.

It feeds everything that scores an actual attack: `StrikeDV @0x557664B0` → `StatisticsToLimitedDV
@0x55726094`; `StatisticsToDV @0x55726038`; both halves of the two-copy melee round (real
`CalculateStrikes @0x55767B24` and prediction `CalculateUnitStrikes @0x557677CC` — **line-for-line
identical apart from which class's VMT they dispatch through**); `GetTargetCVDV` →
`GetTargetStrength/GetTargetPriority`; auto-resolve command scoring via `DVtoDEV @0x55725F10`; and the
tactical AI in `AoWTCPCK.dpl` (`AoWTC.TCAI.tcDVtoDEV @0x413664`).

Its one real blind spot is the **hopeless** end, not the high end: for `d <= −5` it returns `5*M` where
the truth is `10*M` — a flat 2× **under**valuation, because it drops the auto-max branch (§4).

**The player sees nothing.** `AoW.exe` imports exactly **one** symbol from the whole DV/predictor family
(`TArmy.GetPartyStatus`, one call site at `0x00406674`, rendering a five-word morale label);
`aowInt.dpl` imports none. The info card writes only raw Attack/Damage
(`TStrikeAbility.GetCombatInfo @0x55766F60`), and the in-game tooltips actively mislead:

> "Attack is the ability of a unit to hit a target with a melee strike."
> "Damage is the maximum strength of a unit's melee attack."

Attack is framed as **pure accuracy**. No hit-percentage or expected-damage readout exists anywhere. The
only predictor-derived text on screen is the three-bucket "Occupation Forces: Weak/Average/Strong" city
line.

⚠ **One genuinely linear model does exist** and it *does* over-value raw attack:
`TStrikeAbility.GetOffensiveStrength @0x55766BAC` → `FUN_55726100 @0x55726100` =
`attack × min(damage,10) × swings / 2`, no hit cap, no roll. It feeds AI **production and recruitment**
priority and `TCombatPredictorSide` strength totals — not per-strike scoring. (Live Ziggurat raises the
damage cap `10 → 30` here.)

---

## 7. Live-vs-vanilla byte state of the roll itself

The maths is **stock**. Only two live differences exist in this code, neither behavioural:

| VA | live | vanilla | note |
|---|---|---|---|
| `0x55725EBD..C0` | `call 0x558114E0` | `call 0x55701080` | RNG redirected to a **transparent** logging cave (`build_combatlog_dll.py`): calls the real `System.@RandInt`, stores `EAX` to `0x558FA810`, returns `EAX` unchanged |
| `0x55725D9F`, `0x55725DD1` | `imul eax,eax,5` | `lea eax,[eax+eax*4]` | same value, same length, in `HitRole` and `HitRoleProbability` |

⚠ **Provenance note on the `imul` re-encoding:** `Investigation_Storm_Protections.md` attributes it to
"our build". **No build script writes `0x55725D9F`** — `grep`ped all of `build_scripts/`; the four hits on
`0x55725D98` are `HITROLE` *call-target* constants, not patch sites. Treat it as an undocumented hand
edit. It is a plausible deliberate setup for a one-byte to-hit-slope tunable (`6B C0 nn`), currently left
at the vanilla `5` (= 10 percentage points per point of difference), but that is speculation.

`DMDCtoDV`, `DMmaxDCtoDV`, `StatisticsToDV`, `StatisticsToLimitedDV`, `DVtoDEV`,
`TCombatObject.ExecuteDamageRole` and `...Ex` are **byte-identical to pristine**.

Modded *constants* around the path (label any measurement from this install "Ziggurat"): `TStrikeCA.
Generate` effect base `3→5` @`0x55766913`; all six `ExecuteDamageEffectsRole` powers forced to 5
(`build_effectroll.py`); Charge `2→3` @`0x55767BCA`; Parry `2→4` @`0x55767BE1`/`0x55767889`; AI damage
cap `10→30` @`0x55726100`; medal ranks 3→4 with `AttackRankProgression` `[0,1,1] → [0,1,2,3]`; morale now
modifies unit **attack** (−2..+2) instead of unit defence.

---

## 8. Other traps found while establishing the negatives

The claim "there is no other diff-dependent bonus" survives an exhaustive sweep, with these caveats:

- **No lookup table is indexed by a stat difference** anywhere in any of the four binaries. The only
  combat tables in `.data` are medal-rank and morale indexed (`0x558E83C4`–`0x558E83EC`), and they feed
  the ATK/DEF **inputs**, not the roll.
- **No strike count scales with attack.** Melee is a flat 2 per side (`+1` for Extra Strike `0x73`);
  Round Attack adds `Random(2)+1` extra targets; ranged shots/round is a raw data field
  (`GetAttackRepeatRA @0x5576E6AC` = `mov al,[eax+0x2D]`).
- **No damage multiplier and no overkill.** `ExecuteDamage @0x55726C58` asserts `0 <= damage <= 0x31` and
  clamps to remaining HP.
- **An instant-kill mechanic does exist** but is not gap-gated: `TInvokeDeathCA.Execute @0x5576B714` sets
  damage = target's current HP, gated by an ordinary 90%-capped `HitRole` pair.
- **A second independent `clamp(50+10Δ,10,90)`** lives at `TEnchantment.DispelChance @0x5577C1A0`
  (Dispel Magic / Disjunction) and never touches `HitRole`.
- **Every named ability modifies ATK/DEF/damage inputs, never the roll distribution** — Charge, Parry,
  slayers, Marksmanship, Life Steal, First Strike (ordering only) all verified.
- ⚠ **Possible vanilla bug, not investigated:** `TMeleeRound.CreateStrikeCA` computes the strike attack as
  `(byte)(GetAttack() + strikeMod)` — an **8-bit** add with no floor check, and the live invisibility cave
  `0x5580E370` does `sub bl,1` unguarded. A sufficiently negative modifier on a 0-attack unit would wrap
  to a huge positive attack, i.e. guaranteed near-maximum damage. Worth a look if anyone ever sees a
  weak unit hit like a dragon.

---

## 9. If anyone ever wants to change this

Not applied, not proposed — recorded so the options are not re-derived:

- **Change the slope** (10 pp per point): `HitRole @0x55725D9F` is already `imul eax,eax,5` — one byte
  (`6B C0 nn`) tunes it. ⚠ Would desynchronise `HitRole` from `ExecuteDamageRole`, whose 90% cap is
  structural (`R <= 1`), not a constant. Change both or accept the mismatch.
- **Change the caps**: the `0x0A`/`0x5A` immediates at `0x55725DA7`/`0x55725DB1`. Affects only the
  secondary-effect path, **not** weapon attacks (§1).
- **Change the weapon-attack cap**: the `cmp ecx,1` / `cmp ecx,0x12` immediates at `0x55725EC3` /
  `0x55725ECC`. These are the real 10%/90% bounds.
- **Change the compression**: the `10` and the `2*` in `T = 10 − 2d` (`0x55725ED5..E0`), and the `18` in
  `D = 18 − T` (`0x55725EF2`). ⚠ `D` must stay `>= 1` or `shr edx,1` on a negative `D` yields a huge
  unsigned value and `idiv` produces garbage — the guard at `0x55725EE6` only covers `T == 18` exactly.
- ⚠ **Any change must be mirrored in `DMDCtoDV @0x55725E30`** or the AI's valuation silently diverges from
  the actual roll — including its `T < 0` arm at `0x55725E6C`. This is the trap that makes a "simple"
  combat-maths tweak a two-function job.

---

## Cross-references

- `Combat_Log_Implementation_Design.md` §0 — the base to-hit/damage decode (⚠ its "no separate to-hit
  roll" nuance is only implicit; see §1 above).
- `Investigation_Combat.md` — the melee round, strike ordering, Charge/Parry/First Strike.
- `Investigation_Storm_Protections.md` — the `ExecuteDamageEffectsRole` six-roll effect path
  (⚠ its `HitRole`-patch provenance claim is corrected in §7 above).
- `Raze_CombatPredictor_Analysis.md` — `TCombatPredictor`, `GetOffensiveStrength`, the `10→30` cap.
- Memory: `[[aow1-combat-math-decoded]]`, `[[aow1-verify-against-pristine-dll]]`.
