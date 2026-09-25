# Combat Maths

Everything that decides whether a blow lands and how hard it hits: the core to-hit/damage roll,
the two stat-scaling passes layered on it (the 5%-slope conversion and the DAM/HP doubling), hero
stat clamps, strategic-map damage, missile targeting, and the facing + Shield feature that reads
hex geometry into the roll. It replaces 14 source documents (listed in `_old/REDIRECTS.md`), plus §0 of
`07-ui.md`.

**Not covered here** — go to the sibling files instead: unit spellcasting (`06-unit-spellcasting.md`),
the combat-log capture/UI machinery (the rest of `07-ui.md`), ability-specific
mechanics not load-bearing for the maths itself (Slayer, Turn Undead's dedicated doc, invisibility,
item stat bonuses, unit enchantments), and the general two-RNG rule (`12-re-toolchain.md` — this file
states only what combat specifically draws from, in §1 and §9).

## ⚠⚠ Read this first — every number below is LIVE unless marked vanilla

**Ghidra's decompile is the pristine vanilla `AoWEPACK.dpl`. This install is not vanilla — it runs a
5% to-hit slope and doubled ATK/DEF/RES/DAM/HP.** A function with no `[LIVE-PATCH]` comment in Ghidra
is *not* evidence it is unpatched. Never quote a slope, increment or clamp from a decompile — byte-diff
the live file first (`re_tools/dasm.py AoWEPACK.dpl <VA> <len>` against
`Modding Resources/AoWEPACK_original_backup.dpl`).

The single worked example that makes the trap concrete: **`AoWE.ExecuteDamageRole @0x55725EAC`**
decompiles as `T = 10 − 2·diff`. The **live bytes** at `0x55725ED7` are `90 90` where pristine has
`03 C0` (`add eax,eax`) — the doubling is NOP'd out. **Live: `T = 10 − diff`.** A point of stat
difference is worth **5 percentage points, not 10**, and the accuracy pin sits at **`diff = ±8`, not
±4**. Every excess-ATK table in §6 below is given on this corrected, live basis.

| | vanilla | this install (live) |
|---|---|---|
| to-hit slope | 10 pp / stat point, `T = 10 − 2d` | **5 pp** / stat point, `T = 10 − d` |
| accuracy pin band | `d = ±4` | **`d = ±8`** |
| `TUnit` ATK / DEF / RES ceiling | 10 / 10 / 10 | **40 / 60 / 60** |
| `THero` ATK / DEF / RES / DAM ceiling | 10 / 10 / 10 / 10 | **40 / 40 / 40 / 40** |
| `TUnit` / `THero` DAM ceiling | 10 / 10 | **60 / 40** |
| hero HP ceiling (Set == Get) | 30 / 30 | **100 / 100** (was 120/120 until 2026-08-31) |
| item / medal-rank / morale / Leadership bonuses | ×1 | **×1, deliberately NOT doubled** (D2) — half as influential now |

**Two RNGs, briefly** (full rule: `12-re-toolchain.md`). Everything in this file — `HitRole`,
`ExecuteDamageRole`, the effect-roll family, Shield's auto-resolve draw — uses the **RAW** generator,
`System.@RandInt` via thunk `0x55701080`, because `TCombat.Execute @0x557282C8` re-anchors
`System.RandSeed` from one **SYNCED** draw (`TAoWHSMap.Random`) at the start of every combat and the
whole battle then runs deterministically off the raw stream. A synced draw *inside* combat trips the
`GetSynchronised` guard and perturbs the sync value — never use it here.

## Status table

| feature | status | owning script(s) | binary / file |
|---|---|---|---|
| 5% to-hit slope (7 sites) | ✅ CONFIRMED WORKING (2026-08-24) | `build_hitslope5.py` | `AoWEPACK.dpl` |
| ATK/DEF/RES doubling, 12 stages | ✅ CONFIRMED WORKING (2026-08-24) | `build_statdouble.py` | `AoWEPACK.dpl`, `AoWTCPCK.dpl`, `Unitres.pfs`, `HERORES.PFS` |
| Hero ATK/DEF/RES ceilings → 40 | ✅ CONFIRMED WORKING (2026-08-24) | `build_hero_clamps.py` | `AoWEPACK.dpl` |
| Hero chassis ATK ×1 / DAM ×2 | ✅ CONFIRMED WORKING (2026-08-24) | `build_hero_chassis_atkdam.py` | `HERORES.PFS` |
| DAM/HP doubling — core (147 code imms + 527 `.pfs` bytes) | ✅ CONFIRMED WORKING (2026-08-24) | `build_damhpdouble.py` | `AoWEPACK.dpl`, `.pfs` |
| — HP-120 defect (units w/ XP showed HP 120) | fixed 🔨 APPLIED, UNTESTED (2026-08-26) | `build_medal_hpmv.py` v3 | `AoWEPACK.dpl` |
| — hero ATK Set/Get split (points silently wasted above 40) | fixed 🔨 APPLIED, UNTESTED (2026-08-26) — see caveat in §5 | `build_hero_clamps.py` + fivepct/damhp manifests | `AoWEPACK.dpl` |
| — HP ceiling 120 → 100 (4 places) | 🔨 APPLIED, UNTESTED (2026-08-31) | `build_hero_clamps.py`, `build_medal_hpmv.py` v4, `build_editor_spinners.py` | `AoWEPACK.dpl`, both editor exes |
| — regen/heal 8-bit wrap fixes | 🔨 APPLIED, UNTESTED (2026-08-24/26) | `build_newturn_healcap.py`, `build_healwrap_fixes.py` | `AoWEPACK.dpl` |
| — map-fire dead-code fix (was ~4× too weak) | 🔨 APPLIED, UNTESTED (2026-08-26) | `build_firefeed.py` (`MAPFIRE_ATK/DAM=12/6`) | `AoWEPACK.dpl` |
| — Burning/Decay/Turn-Undead-AI damage gap-fix | 🔨 APPLIED, UNTESTED (2026-08-26) | `build_damhp_gapfix.py` | `AoWEPACK.dpl` |
| — morale re-scale (ATK ±4, RES ±6) | 🔨 APPLIED, UNTESTED (2026-08-26) | `build_morale_scale.py` | `AoWEPACK.dpl` |
| — tactical wall/structure HP unified 40 stone / 10 wood | 🔨 APPLIED, UNTESTED (2026-08-26) | `build_tcpck_damhp.py` | `AoWTCPCK.dpl` |
| Hero library skill points spent down (589 unspent → 3) | 🔨 APPLIED, UNTESTED (2026-09-08) | `build_heroskill_spend.py` | `User/Ziggurat Heroes.ahl`, `Ziggurat release/User/` — **no binary** |
| A hero holding unspent skill points is offered them | 🔨 APPLIED, UNTESTED (2026-09-22, v2; v3 guard 2026-09-24) | `build_hero_turn1_upgrade.py` (`0x55786CB3`→nops, `0x55787FE7` call-retarget, cave `C_TURN1 0x5584B000`) | `AoWEPACK.dpl` |
| Excess-ATK → minimum-damage bonus | vanilla mechanism, RE only, no patch | — | `AoWEPACK.dpl` |
| Strategic map damage (storms/grounds/fire/vortex/quake/poison) | vanilla mechanism; ATK/DAM sides doubled by the two passes above | — | `AoWEPACK.dpl` |
| Missile trajectory & interception (manual tactical) | vanilla mechanism, RE only, no patch | — | `AoWTCPCK.dpl` |
| Melee round order (Charge/Parry/First Strike) | vanilla mechanism; magnitudes doubled | — | `AoWEPACK.dpl` |
| Facing — deferred-retaliation timing (S1) | 🛑 REVERTED (2026-08-27, by choice, not a defect — CONFIRMED WORKING before reverting; kept re-appliable) | `build_facing_retal.py` | `AoWTCPCK.dpl` |
| Shield — manual-tactical geometric arc (front + front-left) | ✅ CONFIRMED WORKING (2026-08-27) — arc/handedness only, see caveat in §9 | `build_shield.py` | `AoWEPACK.dpl`, `Release/Ability.pfs` |
| Shield — ranged-only scope + magnitude −5 | 🔨 APPLIED, UNTESTED (2026-08-27) | `build_shield.py` | `AoWEPACK.dpl` |
| Shield — auto-resolve 75% probabilistic rule | 🔨 APPLIED, UNTESTED (2026-08-27) | `build_shield.py` | `AoWEPACK.dpl` |
| Shield — melee links | 🛑 REVERTED (2026-08-27, scope decision — Parry already covers melee; never validated in game before reverting) | `build_shield.py` (`RETIRED_SITES`) | `AoWEPACK.dpl` |
| Lifesteal on round-attack / defensive hits | SPECULATIVE (feasibility only, 90%/85% confidence, nothing built) | — | `AoWEPACK.dpl` |
| Enchanted Weapon for mundane ranged attacks | SPECULATIVE (feasibility only, 85% confidence, nothing built) | — | `AoWEPACK.dpl` |
| Unit-size blocking missiles (auto-resolve) | SPECULATIVE, superseded finding — see §10 | — | `AoWEPACK.dpl` |

---

## 1. The core roll — decoded, corrected to the live slope

Two rolls exist and they are **not interchangeable implementations of one thing**:

- **`AoWE.HitRole @0x55725D98`** (EAX = attack − defence → AL bool) drives 18 *secondary* sites only:
  status effects, touch abilities, resistance rolls, the effect-roll family. `clamp(50 + 5d, 10, 90)`
  vs `RandInt(100)`, `setg` (checked — not `setge`, which would give 91%).
- **`AoWE.ExecuteDamageRole @0x55725EAC`** is the hit test *and* the damage magnitude for every
  ordinary weapon strike, melee or ranged. **Weapon strikes never call `HitRole` at all** — this is
  the single most misleading thing about the system, and it is easy to re-derive wrongly.

```
AoWE.ExecuteDamageRole(EAX = M damage rating, EDX = d = attack − defence) -> EAX

    if M <= 0                    return 0
    R = RandInt(20)                                  ; 0..19 uniform          @0x55725EBC
    if R <= 1                    return 0             ; flat 10% AUTO-MISS ("fumble")
    if R >= 18                   return M             ; flat 10% AUTO-MAX ("critical")
    T = 10 - d                                        ; LIVE. Decompile shows 10-2d — WRONG, see above
    if T > R                     return 0             ; the real miss test
    D = 18 - T = 8 + d
    return 1 + trunc( ((M-1)*(R-T) + (D>>1)) / D )    ; round-half-up
```

`P(non-zero) = clamp(50 + 5d, 10, 90)%` falls out of this by construction — that is why it agrees with
`HitRole` exactly — but the two are independent implementations that happen to match, not one function
calling the other. Only **4 callers** reach `ExecuteDamageRole`, and no descendant overrides VMT
`+0x110`/`+0x114` (`TCombatObject`/`TCombatUnit`/`TFastCombatUnit` all inherit), so this is universal:
`0x55726A33`, the `Ex` form `0x55726AC8` (uses Resistance instead of Defence when its flag byte is 1),
`0x55781B0D` (strategic-map damage, §7), and the fire-heals-fire cave `0x5580DA61`.

**No critical-hit mechanic in the ID'd sense.** The `R≥18` branch is the whole "critical" — flat 10%,
no multiplier, never exceeds the normal maximum. `P(rolled == max)` is ≥10% and *rises* with `d` purely
from rounding (≈15% at `d`=+1..+5, 20% at +6..+10 on the live scale) — `rolled==max` therefore **cannot**
be used to detect the auto-max branch; only `R` itself distinguishes them (relevant to the combat-log
capture design, which stores `R` in DLL BSS at `0x558FA810` for exactly this reason — see
`07-ui.md` for the capture mechanics, out of scope here).

### The band: `d = ±8`, not ±4

`T ≥ 18` makes the middle band (`R` in 2..17) unreachable — `T > R` is always true — so past `d ≤ −8`
the *only* surviving outcomes are the two auto-branches: a flat **10% chance of connecting, and every
connection is maximum damage.** Symmetrically, `T ≤ 1` at `d ≥ +8` makes the middle band always pass,
pinning hit% at the 90% ceiling (still floored by the flat 10% auto-miss). Both pins are **structural**
(the `R≤1`/`R≥18` tests fire before `T` is even computed), not the `cmp esi,0x12/jge` guard at
`0x55725EE6` — that guard is provably **dead code** (enumerated exhaustively over `d ∈ [−200,200] ×
R ∈ [2,17]`: fires 0 times). What actually zeroes the middle band at `d ≤ −8` is the preceding
`cmp esi,ecx/jg` at `0x55725EE2`.

### Which defensive stat the roll uses — a live bug this doc corrects

`TCombatObject.ExecuteDamageRole @0x557269F0` (ret 4) uses **`[vmt+0x70] GetDefense`**.
`ExecuteDamageRoleEx @0x55726A6C` (ret 8, extra byte at `[ebp+8]`) uses **`[vmt+0x74] GetResistance`
iff that extra byte == 1**, else Defence. **The `Ex`/GenerateEx path (Turn Undead, combat spells) rolls
vs RESISTANCE, not Defence.** Both return a signed byte in AL (`movsx`). Both also (a) return 0 early
if `types & ~GetImmunityTypes(vmt+0x7c) == 0` (full immunity — free at the caller: `word[CA+0x11]==0`
means fully immune, no virtual call needed), and (b) **halve** the result (round-half-toward-zero) if
every remaining type is Protected.

⚠ **Never carry an offset across the combat-object and strategic-unit hierarchies.** The strategic-map
version of this same wrapper (§7) uses **`vmt+0xC4` GetDefense** / **`vmt+0xCC` GetResistance** —
completely different slots on a completely different class. An offset means nothing without its class.

---

## 2. The melee round — strike order, and the Parry correction

`TMeleeRound` builds the whole round up-front as an interleaved strike array (stride `0x14`, base
`round+0x0C`, side byte at `+0x0C`: 0 = attacker delivers, 1 = defender retaliates), then executes it.
**Two parallel copies of the same logic** — real combat (`TCombatObject`, vmt `+0xA8`) and prediction
(`TAbstractUnit`, vmt `+0x148`) — and a mod that touches one must touch the other:

| | real combat | prediction |
|---|---|---|
| set-up | `Calculate @0x55767D24` | `CalculateUnit @0x55767A3C` |
| build | `CalculateStrikes @0x55767B24` | `CalculateUnitStrikes @0x557677CC` |

Strike counts: attacker `[self+0x28]` = 2 (**+1 for ExtraStrike `0x73`**), defender `[self+0x2C]` = 2
(no ExtraStrike check — matches the card's "when on the offense"). One boolean decides strike order:

```
flip = defender.HasAbility(0x74 FirstStrike)
    && !attacker.HasAbility(0x74)        // both sides having it cancels out
    && [self+0x2C] != 0                  // a defender who cannot strike back cannot strike first
```

`CalculateStrikes(self, flip)` seeds `side = flip` and alternates; total strikes are unchanged — **a
pure reordering, not an extra swing.** Inside, gated on `i == 0 || (i == 1 && side != flip)`:

- **Charge `0x6F`** — vanilla `+2` damage, **live `+5`** (byte-checked 2026-08-27 at `0x55767BCA` and
  `0x55767872`: `83 43 04 05` vs pristine `83 43 04 02`) — only on the round's opening strike, and only
  when that strike belongs to the attacker (`side==0 && i==0`).
- **Parry `0x71`** — vanilla `−2` attack, **live `−8`**. **Correction: the immediate byte at
  `0x55767BE3` (instruction `sub dword [ebx],8` at `0x55767BE1`) is `08`, not `04`.** Twin site
  `0x55767889`. Byte-checked 2026-08-27 against both the pristine DLL (`83 2B 02`) and `Ability.pfs`
  record 123 (cost 8, card text already says `-8`, so this is deliberate, not a doubling artefact).
  On the live 5 pp slope that is **−40 percentage points**. Applies on the target of the **first**
  strike of each side, so ordering does not affect it. Parry's only two call sites in the whole DLL are
  `TMeleeRound.CalculateStrikes+0xB3` and `CalculateUnitStrikes+0xB3` — **it never applies to ranged.**

**First Strike negating Charge is emergent, not coded.** With `flip=1` the defender takes index 0; the
attacker's opening strike lands at index 1, where `i==0` fails, so Charge's branch is never reached.
Grepping for a link between the two abilities finds nothing and would conclude wrongly.

`Calculate`/`CalculateUnit` are byte-identical to pristine; `CalculateStrikes`/`CalculateUnitStrikes`
differ from pristine only in the Charge/Parry immediates (both copies retuned together) plus a
`build_assassin.py` cave jump at `0x55767C5C` — the ordering and gating logic itself is stock.

⚠ **Known, unrelated defect on exactly these sites — do not "fix" it as part of anything else.** The
alignment bonus (Holy/Unholy Champion, `0x92`/`0x93`/`0xA0`/`0xA1`) is applied at two melee sites and
should agree; it does not. Pristine both **2**; live: `0x5576665D`/`0x55766660` (in `CreateStrikeCA`,
the free-swing/touch path) and `0x55766699`/`0x5576669C` (second arm, same function) are **4**; but
`0x55767C55`/`0x55767C58` (in `TMeleeRound.CalculateStrikes`, the ordinary-melee path) are **5**.
Verified 2026-08-25 by byte-diff at file offsets `0x065A55`, `0x065A91`, `0x06704D`. Under the DAM/HP
doubling 2→4 is the correct value, so the `CalculateStrikes` copy is one too high. (Monster Slaying
went 3→5 at *both* sites — consistently — so this is not a systematic re-grade rule; it is a specific
miss on this one bonus.)

---

## 3. The 5% to-hit conversion

**Status: ✅ CONFIRMED WORKING (2026-08-24)**, applied 2026-08-20. **Doubling every ATK/DEF/RES source
and halving the slope is a verified perfect identity** — enumerated: hit chance *and* the complete
damage distribution are bit-identical across all damage ratings and all differences −12..+12.
`T = 10 − 2d` becomes `T = 10 − d′` with `d′ = 2d`, so `T` is unchanged and stays even;
`50 + 10d ≡ 50 + 5d′`. The change therefore buys exactly two things: half-steps become expressible
(a net +1 stat point is now 55%, previously unreachable), and whatever is deliberately **not** doubled
(D2, below) becomes half as influential.

### The slope: seven sites, not eight

Every slope site is `add r32,r32` immediately followed by a ×5 (the ×10 is built as ×2 then ×5).
NOPping the doubling leaves ×5. No length change, no `.reloc` entry covers any of them.

| # | VA | owner | function | rôle | live |
|---|---|---|---|---|---|
| 1 | `0x55725D9D` | engine | `AoWE.HitRole` | roll primitive, `clamp(50+10d,10,90)` vs `RandInt(100)` | `90 90` |
| 2 | `0x55725DCF` | engine | `AoWE.HitRoleProbability` | float mirror, AI estimator | `90 90` |
| 3 | `0x55725ED7` | engine | `AoWE.ExecuteDamageRole` | **the real weapon-strike hit test** | `90 90` |
| 4 | `0x55725E3B` | engine | `AoWE.DMDCtoDV` | AI's closed-form model of #3 | `90 90` |
| 5 | `0x5580F6C3` | `build_effectroll.py` | effect-roll log line | displays the odds | `90 90` |
| 6 | `0x558110C7` | `build_combatlog_dll.py` | damage log line (`_gotdef`) | displays the odds | `90 90` |
| 7 | `0x558118F0` | `build_combatlog_dll.py` | touch log line (`_tstats`) | displays the odds | `90 90` |

`TEnchantment.DispelChance @0x5577C1A4` shares the same clamp *shape* (a byte-pattern census finds it)
but is **not** a slope site and was removed from the set. Read directly it is
`clamp(dispelMana − 10×[ench+0x14] + 50, 10, 90)` with `GetDispelMana = 10×abilityLevel + 20`, i.e.
`clamp(10×(level − enchStrength) + 70, 10, 90)`. The difference term is ability level vs enchantment
strength — neither is an ATK/DEF/RES stat, neither doubles, and the `+50`/`+20` constants do not scale,
so halving this slope would be a pure, non-identity buff to dispelling. Left alone deliberately, along
with both `GetDispelMana` copies (`0x5576CEB7` ability-side, `0x557E89F8` spell-side — the spell side
is the one place a clean 5% halving is **not** exactly representable: live `15L+25`; the exact half is
`7.5L+12.5`, a genuine design decision, never built).

⚠ **`0x55725D9F` (`imul eax,eax,5`, replacing pristine `lea eax,[eax+eax*4]`) is owned by
`build_hitslope5.py`**, written as part of the same edit that NOPs the doubling at the immediately
preceding byte `0x55725D9D` — it is **not** an undocumented hand edit, whatever an older note says.
Same pattern at `0x55725DD1` for `HitRoleProbability`'s own ×5 companion. Sites 3/4 (`T = 10−d` shape)
have no such companion — do not go looking for one there.

**Decoys — never locate these sites by byte pattern.** A census of `add r,r` immediately followed by
×5 returns 18 hits across `AoWEPACK.dpl`; 11 are unrelated (skill-point prices, dispel mana, other
arithmetic): `0x5572D3FC 0x5572D484 0x55730676 0x55730780 0x5576CEB7 0x557875E8 0x55787605 0x55789F69
0x557A1AFB 0x557AC405 0x557CEB34 0x557DB2A9`. `build_hitslope5.py` writes by absolute address only and
refuses if any site's bytes are unexpected.

**Idempotence.** `90 90` at all seven addresses is unambiguous (both live and pristine hold `03 C0`/
`01 C0` beforehand), so no version marker is needed — a partial state aborts rather than repairs.

### The doubling: 12 stages, ~825 writes

`build_statdouble.py` is manifest-driven (`fivepct_manifest.json`), applying only explicitly-verified
stages; nothing is applied until every stage is green. Counts: **117 ATK + 18 DEF + 30 RES code
immediates**, **217+217+217 = 651 `.pfs` data bytes**, **6 skill-point prices halved**.

| stage | scope | entries |
|---|---|---|
| 1 | stat clamps + hero skill economy | 16 |
| 2 | `.pfs` base stats (`Unitres.pfs` 179 records/537 bytes, `HERORES.PFS` 38/114) + CRC | 651 |
| 3 | ability/enchantment stat modifiers (`PassiveAb.*`) | 18 |
| 4 | effect-roll powers vs Resistance | 17 |
| 5 | touch attacks (`GetTouchAttack`) | 12 |
| 6 | strategic-map hazard ATK (storms/fire/vortex/quake/poison/grounds) | 12 |
| 7 | combat-spell powers (`+0x34`, `CombatSpells.*` namespace) | 32 |
| 8 | champion/slaying bonuses + innate ranged ATK constants | 21 |
| 9 | `AoWTCPCK.dpl` tactical wall/terrain constants (2nd binary) | 4 |
| 10 | walls, Parry, Wall Crushing, Self-Destruct, `MakeDefaultLevelUnit` | 27 |
| 11 | Ziggurat cave constants owned by 5 other feature scripts (chained caves) | 13 |
| 12 | Underground/Cave ranged malus (its own stage, unowned cave) | 1 |

`Unitres.pfs` tag map: `0x0E`=ATK, `0x0F`=DEF, `0x13`=RES. **`HERORES.PFS` differs**: `0x0F`=ATK,
`0x10`=DEF, `0x14`=RES — `0x13` there is **MOVES**. Applying the wrong map doubles hero movement
(24–36→48–72) and silently leaves resistance untouched; both maps are verified from
`THeroResource.ReadWrite @0x55789FD4` and cross-checked against the `UsedSkillPoints` cost multipliers
(5/5/10/5/5/2). Verification without the game: **every one of the 651 bytes is even** — the
pre-conversion tables were full of odd values, so a single odd value proves incompleteness.

Idempotence: a marker dword `Z5PC` + u32 stage mask lives in free CODE space at `0x55818000`
(file `0x117400`) — BSS is not usable (zero raw size). `--undo` restores the recorded **live** values,
never pristine (e.g. `TDeathRay` damage is live 4 / pristine 8 — an idempotence collision the marker
resolves correctly).

### Stage 11 — caves chained across five other scripts

Not "14 pokes in 5 scripts" — the caves form a **chain**, and several scripts repoint each other's
exit jumps:

```
hook 0x5576EB34 -> cave_ts_rng (invis, 0x5580E400) -> cave_rng (ranged_slayers, 0x5580E190)
                -> [magebane repoints the exit at 0x5580E298 into its own cave 0x55812A20]
assassin cave_melee3 (0x5580E120) exit -> cave_ts_melee3 (invis, 0x5580E3B0)
                -> [magebane repoints the exit at 0x5580E3D9]
```

Re-running an owner in isolation silently deletes whatever chained onto it afterwards. Any stage-11
re-tune order: `build_magebane.py --undo` → re-run the owning script → `build_magebane.py --apply`
then `--verify` (it reports the chain). Ownership by `CAVE*` constant, not guesswork:
`build_assassin.py` (4, `0x5580E070`–`0x5580E190`), `build_ranged_slayers.py` (4, `0x5580E190`–
`0x5580E2A0`), `build_invis_penalty.py` (3, `0x5580E370`–`0x5580E440`), `build_turnundead_res.py` (2 +
the `shr eax,1→2` structural edit), `build_marksmanship8.py` (1, hooks `0x5580C240`).

The redesign that made this re-tunable: **accept-variants** (regenerate the body across the plausible
constant range and accept any match), **prefix comparison + growth assertion** (a re-tune can change
body length — `shr eax,1` is 2 bytes, `shr eax,2` is 3 — compare by prefix, assert the growth zone is
still zero), and **terminator preservation** — a cave's exit `jmp` is a chain link, not a private
detail; regenerating with the stock destination silently deletes everything downstream. Owners now
keep whatever exit target is installed and log `[chain] <cave> exit kept at <target>`.

**Marksmanship, current state:** ranged ATK **+level** (1–8). `GetAttackRA` passes the raw level
from `GetAbilityLevel(0x20)` to the cave `0x5580C240`, whose `add bl,al` adds it. Ranged DAM is
**+level** too: `GetDamageRA`'s `add ebx,eax`, with the pre-existing `shr eax,1` dropped (H9, a
Leadership-style flat ramp). `build_marksmanship_atk2.py` would double the ATK by inserting
`add al,al` and shifting the 72-byte body +2. It is **not applied, and must not be**: owner ruling
2026-09-24, Marksmanship stays +1 ATK per level. The Cave/Depths ranged malus rides the same cave (gated on Night Vision
`0x27`), already at `sub bl,4` (doubled, stage 12) and untouched by the relocation.

**The malus skips the Firmament** — `build_firmament_rangedmalus.py`, 🔨 APPLIED, UNTESTED
(2026-09-24).
- **The defect:** the cave's level test was `cmp al,0 / je` (malus whenever level ≠ 0). It was
  written before the Firmament existed, so level 3 counted as underground. Owner ruling 2026-09-24:
  exclude the Firmament.
- **The fix:** `0x5580C27F` is now `test al,al / jp 0x5580C286` (`84 C0 7A 03`, same length and
  target). PF is set for levels 0 and 3, so the malus applies on Caverns and Depths only — the
  surface-or-Firmament split `build_maplevel4.py` uses for vision.
- **Coupling:** the site moves to `0x5580C281` if `build_marksmanship_atk2.py` is ever applied, and
  the script finds it in either layout. Surgical `--undo`.

In-game checklist:
1. A ranged unit **without** Night Vision on the Firmament attacks at its surface ranged ATK (combat
   log).
2. The same unit on Caverns and on Depths still attacks at −4.
3. A unit **with** Night Vision takes no malus on any level.

### A later balance change layers on stage 2 — hero chassis

`build_hero_chassis_atkdam.py` doubles `HERORES.PFS` **ATTACK** and **DAMAGE** again, on top of stage
2 (above). **Undo order matters**: undo the chassis script first, re-apply it last, or `HERORES.PFS`
lands mixed (ATK at pre-state, DAM still scaled) — the chassis script detects that and aborts with a
diagnosis but cannot repair it. (Currently ATK's factor is ×1, so the two scripts write identical ATK
bytes and the order is harmless — it stops being harmless the moment ATK is raised again.)

### D2 — deliberately NOT doubled

> *"Do NOT double: items, medal ranks, morale, Leadership."* (user, 2026-08-18) — these become **half
> as influential**. That was the point, not a side effect.

| source | live values | table |
|---|---|---|
| Item bonuses | `ITEMS.PFS` tags `0x0B` ATK/`0x0C` DEF/`0x0E` RES, 1..3 | 23/28/23 bytes |
| Medal ranks | `AttackRankProgression 0x558E83C8=[0,1,2,3]`, `DefenseRankProgression 0x558E83C4=[0,0,0,1]`, `ResistanceRankProgression 0x558E83D0=[0,1,2,3]` | — |
| Morale (pre-2026-08-26 rescale) | `MoraleResistanceModifier 0x558E83D8`, `MoraleDefenseModifier 0x558E83E0`, morale→ATK bands in cave `0x5580C0F7` | superseded — see §4's morale re-scale |
| Leadership | vanilla exported tables are **dead** — `build_leadership4.py` repointed `GetAttack`/`GetDefense` to its own tables at `0x5580F0C0`/`0x5580F0C8`, ATK/DEF `1,2,3,4` each, re-tuned 2026-08-20 to a flat +5/+10/+15/+20 pp ramp | freely re-tunable data, `build_leadership4.py` |

⚠ Rank tables and (pre-rescale) morale tables are owned by `build_copper_medal.py`'s `STAT_TABLES` —
reversing D2 means doubling them there and appending to `PRIOR_TUNINGS`, or its verify refuses.

**`HEROES.PFS` (the 50 predefined-hero library) remains undecided and un-doubled** — tags `0x10`
ATK/`0x11` DEF/`0x15` RES, 1..3, 39/37/32 bytes — **until 2026-08-24's H6 decision, which doubled it**
(all five bonus tags, including DAM `0x12` and HP `0x13` — see §4). Carries **no PFS magic and no
CRC**; never run the CRC repair over it.

### Traps paid for during staging (compressed — the full staging log lived only in the manifest)

- ⚠⚠ **The conversion's "before" column is the INSTALLED DLL, not vanilla — so a recorded `X → 2X`
  may be doubling a Ziggurat value.** The install already carried undocumented pre-convention
  hand-edits, and the audit that fed the manifest sampled the live file. Worked instance (found
  2026-09-09): Terror's ATK is recorded as **8 → 16**, but pristine
  `AoWEPACK_original_backup.dpl` holds **6** at all five of its sites — the 6 → 8 step was a
  pre-convention Ziggurat change nobody recorded, so the pass doubled 8 rather than vanilla's 6.
  Consequence for anyone reasoning backwards from a live constant: **`live / 2` is not the vanilla
  value.** Byte-diff the pristine DLL instead — never infer the baseline from the manifest.
- ⚠⚠ A relocated cave body (Marksmanship's +2-byte insert) invalidated another script's manifest
  address inside the shifted range; nothing warned. Before relocating anything, grep every build
  script and manifest for addresses inside the range about to move.
- ⚠ `build_invis_penalty.py`/`build_ranged_slayers.py` can report `[x]` even with correct bytes,
  because they verify their cave *including* a terminator that `build_magebane.py` has since
  repointed — a false `[x]` here is a script defect, not a byte defect.
- ⚠⚠ Backward instruction decoding is unreliable in **both** directions: shortest decode picks up
  spurious mid-instruction `jmp`s; longest decode can pick the wrong instruction when a displacement
  byte doubles as another opcode. Decode **forward** from a known instruction boundary.
- A "self-validated" anchor is worthless when the claimed value is `0` — 22 entries resolved to value
  0 during re-anchoring and only one was real; the rest are assert-only with soft "verified" status.
- Every stage needs a **direction** check, not just a value check — a stat's skill-point price
  (halves) and its stat ceiling (doubles) can be conflated by a naive classifier.
- `.pfs` tag maps are per-file, not reusable (see above). Family-name regexes over-match
  substrings (`Fury`→`TWindsOfFury`, `ground`→`Underground`) — scope by class namespace or address
  range instead.
- Verifiers must accept signed *or* unsigned readings of the same recorded byte, or an
  already-correct assert-only site reads as "moved".

---

## 4. DAM/HP doubling — the second identity

**Status: ✅ CONFIRMED WORKING (2026-08-24)**, with one defect found in later play and fixed
2026-08-26 (that fix is 🔨 APPLIED, UNTESTED). Extends the conversion's identity to damage and hit
points: **every damage source ×2, every HP pool ×2** → time-to-kill unchanged, half-step damage/HP
become expressible. Manifest: `damhp_manifest.json`, 147 code immediates + 527 `.pfs` data bytes,
byte-verified before and after write.

### Decisions (user, 2026-08-24, H1–H9 + adopted defaults)

| # | decision | consequence |
|---|---|---|
| H1 | item DAM stays unchanged (`ITEMS.PFS` tag `0x0D`, 1..3) | consistent with the D2 item exception |
| H2 | medal DAM → `[0,0,1,2]` (was `[0,0,1,1]`) | a chosen curve, not a straight ×2 — owned by `build_copper_medal.py` |
| H3 | level-up prices halve **from the live Ziggurat values** | DAM 8→4, HP 4→2. Never derive prices from the vanilla decompile |
| H4 | damage caps → 60 | `TUnit.GetDamage` 30→60, `THero.GetDamage` 40→60 (later reduced, §5) |
| H5 | HP cap: "whatever is safe" pending an 8-bit-width audit | resolved to 120 (below), later 100 (below) |
| H6 | `HEROES.PFS`: double all five bonus tags (ATK `0x10`, DEF `0x11`, DAM `0x12`, HP `0x13`, RES `0x15`) | closes the conversion's open library-hero item |
| H7 | hero chassis DAM stays ×2 (parity) | dissolves into the global doubling — `build_hero_chassis_atkdam.py` FACTOR unchanged |
| H8 | medal HP doubles (`build_medal_hpmv.py` K 1→2) | keeps medal HP's worth vs doubled pools |
| H9 | Marksmanship DAM → smooth ramp 1/2/3/4 | see §3 |

Standing repairs adopted without a separate question: HP caps 80→120 (later 100), mandatory NewTurn
overheal fix, assert `cmp ebx,0x32→0x7F` before any doubled damage lands, floors 1→2 (GetDamage,
GetHits, NewTurn regen, Resurrect/Animate), Turn Undead exact ×2, five clamp `mov` twins + `SetUnit*`
twin repaired, Self-Destruct `push 8→16`, breath/FlameThrowing attack 7→14, Magebane `BONUS_PER 1→2`.

### The 147-immediate build, in apply order

| stage | scope | note |
|---|---|---|
| 1 (`S4`) | clamps/prices/AI thresholds, the ≥50-damage assert, conversion repairs | assert `0x32→0x7F`; SetUnit DAM cap 20→40, HP cap 80→120; UsedSkillPoints DAM via NOP of `add eax,eax` (`03 C0→90 90`); AI DAM/HITS thresholds 10→20/30→60; repairs 3 unit clamp `mov` twins, 3 `SetUnit*` twins, SD `push 8→16`, breath+FlameThrowing 7→14, Marksmanship rider drop |
| 2 (`S3`) | HP + healing immediates | Healing 5→10, DispelMagic AI 5→10, High Prayer 5→10 ×6, Remedy, Showers 3→6, walls, `MakeDefaultLevelUnit` HITS ×4, Resurrect/Animate 1→2, regen floor 1→2 |
| 3 (`S2`) | engine damage immediates, both DPLs | 85 sites: 22 spell `+0x35` bytes, 11 ranged registrations, breaths, slayer/champ/charge adds, Wall Crushing ×10 + Self-Destruct ×8 (6→12), storm and hazard damage sides (see §7 for the current numbers), 4 PassiveAb GetDamage, `MakeDefaultLevelUnit` DAM |
| 4 (`S1`) | `.pfs` data — 527 bytes | Unitres DAM(`0x10`)+HITS(`0x11`), HERORES HP(`0x12`), HEROES.PFS all five bonus tags (H6) — gated on the `HPC2` marker |

⚠ **Stage 3's original docstring over-claimed "Burning/Decay ticks" and "AoWTCPCK TCDamage" coverage —
corrected 2026-08-26.** Neither address (`TBurningAbility.NewCombatTurn @0x557BA475`,
`TDecayAbility.NewCombatTurn @0x557BA772`) was ever doubled by this stage, and `build_damhpdouble.py`
**never wrote a single byte to `AoWTCPCK.dpl`** — that module differs from its own `.pre-damhp` by
zero bytes from this pass (the 5% pass did write 4 bytes there). Both gaps have since been closed —
see "Gaps both passes missed" and "AoWTCPCK — the module the pass never wrote to" below.

Companion pieces, each its own script: `build_newturn_healcap.py` (overheal wrap fix, 24-byte hook →
cave `0x55818040`), `build_medal_hpmv.py` (unit computed-HP cap, tail `jmp` → cave `0x55818080`),
`build_hero_clamps.py` (hero bounds ladder — §5), cave retunes (assassin 3→6, ranged_slayers 1→2,
LifeStealing 2→4 and Dark Gift 2→4→**3** (the two heals are independent `add eax,N` immediates in
the same cave; Dark Gift came back down to 3 on 2026-09-14 by owner ruling, LifeStealing stayed at
4), Turn Undead `DMG_SCALE=2`, Magebane `BONUS_PER 1→2`, copper-medal Damage
`[0,0,1,2]`), `build_editor_spinners.py` (14 sites/exe, both editors — also fixes a pre-existing
re-save clamp corruption; ⚠ **now broken and unrunnable**, see below), `build_hpbar_clamp.py` (re-homed to `0x558180C0`, its old cave having been
silently reclaimed while unapplied). New cave/marker map: `Z5PC @0x117400`, `Z5DH @0x117408`,
`HPC2 @0x117410`, healcap cave `0x55818040` (49 B), medal cap cave `0x55818080` (17 B), hpbar cave
`0x558180C0`.

⚠ **`build_editor_spinners.py` is BROKEN and cannot be run** (measured 2026-09-10). `EXES =
["AoWDevEd.exe", "AoWEd.exe"]` (`:39`), and **`AoWEd.exe` does not exist in the overlay** — only at
the vanilla root — so it dies at `:80` with `FileNotFoundError: Ziggurat\AoWEd.exe`. That editor was
superseded by `Ziggurat\AoWzEd.exe`. This is **not** the 2026-09-09 exe rename (which touched only
`AoW.exe`/`AoWCompat.exe`); it is a separate stale target, and it cannot reach the vanilla tree.

⭐ **It fails safe, including under `--apply`**: the loop reads *both* exes into `plans` before the
write loop at `:102`, so the crash on the second file happens before a single byte is written —
no partial apply is possible. Consequence is only that its half of the HP-ceiling work, the 14
spinner sites, **cannot be re-applied or undone** until `EXES` names the editors that exist.

**Undo order** (all surgical, no `.pre-*` restores): `build_damhpdouble.py --undo` → `build_pfs_typos.py
--undo` → owner retunes individually (Magebane dance for assassin/ranged/turnundead: `--undo` at
`BONUS_PER=1` → owners → `--apply` at 2) → `build_medal_hpmv.py --undo` (returns to **v0**, not v1) →
`build_hero_clamps.py --undo` → `build_newturn_healcap.py --undo` → `build_editor_spinners.py --undo`
→ `build_hpbar_clamp.py --revert`.

### The Turn Undead damage formula, current state

`(level × casterRES + 1) >> 1` (vanilla) → 2026-08-20: re-rounded to `(level × RES + 2) >> 2`
(`DMG_ROUND=2, DMG_SHIFT=2`, closing the RES-doubling identity) → 2026-08-24: an **exact ×2** appended
(`add eax,eax` after the shift, `build_turnundead_res.py` `DMG_SCALE=2`) so there is no rounding
drift. Current live formula: `2 × ((level × RES + 2) >> 2)`, caves `0x5580E2A0` (combat damage) /
`0x5580E300` (info-card display) — both scaled together.

### Charge and Self-Destruct: re-proven complete by enumeration

Two user challenges (2026-08-24) drove an exhaustive re-check rather than trusting the stage counts.

**Self-Destruct** — all 19 `TSelfDestruct*` exports enumerated and every immediate tallied: ATK sites
(6, all =16 live): `GetDamageValue`/`GetDamageValueEx`/`fcGetDamageValueEx` `mov eax,0x10`,
`GetCombatInfo [ebx+1]`, `GetOffensiveStrength`, the execute `push 0x10` (this last was the stage-10
gap, repaired). DAM sites (8, all =12). Verdict: **complete.** `TSelfDestructCA.Execute` reads only
CA fields populated from the patched pushes — auto-scales. No `tcGetDamageValueEx` exists for this
ability (unlike Wall Crushing), so the 10-vs-8 immediate asymmetry is real, not a miss.

**Charge (`0x6F`)** has no class of its own — only `ChargeRStr` exists, a generic enhancement ability,
so there is no per-class family to miss. Every encoding of the id swept across both DPLs (9
candidates): the real thing is `0x5576785F` + `0x55767BB7` (`GetAbilityEnabled(0x6F) → add dword
[ebx+4],6` in both melee strike tables, live-verified at 6, damage-only). Remaining candidates are
unregister lists, a different namespace (spell id `0x6F`), text/string data, or a serialisation field
tag — none is a real Charge site. `AoWTCPCK.dpl` has zero references (tactical executes engine-built
strikes); no cave tests `0x6F`.

### 2026-08-26 — the HP-120 defect: an 8-bit divide feeding a 32-bit compare

**Symptom** (user, in-game): *"when my units gained any XP, their HP maxxed out to 120."*

**Root cause.** `TUnit.GetHits` (pre-existing cave `0x5580BE15`, computing `rank×K + base +
XP/(level+1)`) does `div cl` — an **8-bit** divide that writes only AL (quotient) and AH (remainder);
it never touches EAX bits 16–31. The v2 HP-cap cave then did `mov ebx,eax; add eax,ebx; cmp eax,120`
at full **32-bit** width, so the comparison saw `remainder<<8 | quotient`: any non-zero remainder
contributed ≥256, tripping the clamp and forcing HP to exactly 120. `mov edx,0` immediately before the
`div` is dead code (`DIV r/m8` never touches EDX) — nine bytes of no-op sitting directly in front of
the bug. `div cl` is mandatory, not incidental: `TUnit.GetUnitLevel` returns a pointer-dirty EAX with
only CL clean, so "tidying" to `div ecx` would divide by a pointer.

**Exact trigger:** `XP mod (level+1) != 0` — most XP values, re-rolling on every XP change. **Not a
vanilla defect** (byte-diffed: `0x5580BE00..0x5580BE73` is all-zero in the pristine DLL — the whole
cave pair is mod-authored; vanilla `TUnit.GetHits @0x55782B68` was a medal-table lookup with no XP
term at all). What *is* vanilla is the byte-return convention that hid the dirt for years
(`GetMovementPoints`/`GetUnitLevel` both return EAX with a resource pointer in bits 8-31, byte-identical
pristine and live).

**⭐ The general lesson.** Widening an 8-bit computation to a 32-bit compare does not merely add a
clamp — it promotes every previously-truncated dirty bit into the comparison. Zero-extend the 8-bit
source explicitly (`movzx`) before any 32-bit compare; the compare is the new consumer and it is
stricter than the old one.

**Fix — `build_medal_hpmv.py` v3, applied 2026-08-26, untested in game.** First instruction becomes
`movzx ebx,al` (`0F B6 D8`); body 17→18 bytes; growth zone re-verified all-zero.

**A sibling latent bug, not yet triggered.** `0x5580BE6D` (the movement tail) still has the identical
`mov ebx,eax` / 32-bit `add` shape, fed by its own `div cl` at `0x5580BE6A`. `TUnit.GetMoves` returns
`(remainder<<8)|value` **today** and is harmless only because every consumer truncates to a byte.
**Adding any movement cap or 32-bit consumer here reproduces the HP bug verbatim** — it must use
`movzx ebx,al` from the outset.

**A second sibling, latent but benign by construction.** The regen-heal cave (`0x55818040`) does a
32-bit `add edx,ebx` over an EBX it inherits from the host un-sanitised (`mov ebx,eax` off a
byte-returning `GetHits`), but never misbehaves: `LARGE_ADDRESS_AWARE` is clear so the dirt is always
large-and-positive, and the clamp maps every large-positive sum to exactly max HP — the intended
Regeneration result anyway. Optional hardening exists (insert `movsx ebx,bl` after `pop ebx`) but is
not required.

**Do NOT "harmonise" the widening instruction across caves.** The medal-cap cave narrows an
**unsigned** `div` quotient (`movzx`); the healwrap caves (below) narrow a **signed** HP byte
(`movsx`, matching `SetHitPoints`'s own `test bl,bl/jge` floor). They are correctly different.

### The regeneration/heal wrap fixes

**Correction to an earlier framing:** the 8-bit overheal add is a vanilla CODE defect that vanilla
DATA could never reach (pristine hero HP ceiling 30, no XP-hits cave, cur+max ≤ ~60 — no wrap
possible). It became reachable when Ziggurat raised the hero HP ceiling to 80 and added uncapped
XP-hits growth; doubling would have made it routine. `SetHitPoints` clamps to max and floors negatives
at 0, so a wrapped (negative) sum becomes **0 HP from resting/healing** — the worst possible outcome
from a "heal".

A systematic sweep of all 92 `SetHitPoints` call sites found three remaining wrap-idiom sites plus two
heal doublings the DAM/HP pass itself had missed (a converter trap: the source manifest used a `imms`
dict for most families but singular `imm`/`edits` keys for structural rows, which the converter never
walked):

| site | was | now (`build_healwrap_fixes.py`) |
|---|---|---|
| High Prayer fast `0x557F7DE3` | `add dl,10` uncapped | 32-bit + 127 pre-clamp cave `0x55818100` |
| High Prayer tactical `0x557F7EC6` | same | cave `0x55818130` |
| Healing Showers `0x557A1DDD` | `add dl,3` uncapped **and undoubled** | cave `0x55818160`, heal **6** |
| Remedy `0x557E739F` | 5 (missed by the converter) | **10** (wrap-safe: 32-bit, max-clamped) |

Safe by construction, verified, not "fixed": `HealUnit` caps at missing HP first; HealingWater/
CallHero/HealUnits/NaturesBlessing set cur=max; lifesteal adds 32-bit + setter clamp; damage
subtraction floors at 0; the uncapped add in `cave_5580C150` is dead code (bypassed by the
lifesteal/round-attack cave).

**With these fixes, every path that raises current HP is 32-bit and clamped** — the cap was safe at
120, and 127 would have been safe too. It was lowered to **100 on 2026-08-31** by user ruling
regardless, reclaiming margin under the wall (see below).

### The HP ceiling: 120 → 100, in four places (2026-08-31, applied, untested)

**User ruling: reclaim margin under the 127 signed-byte wall.** All four families moved together:

1. `THero.GetHits` ceiling and `THero.SetUnitHits` purchase cap — both `build_hero_clamps.py`, ladder
   **80/120/100**. The `SetUnitHits` pair moved **out of** `damhp_manifest.json` and into the ladder
   script, because a two-state manifest entry cannot express a re-target (a byte holding the *previous*
   target reads FOREIGN and aborts the stage — `--repair` can never reach it). The manifest's two
   entries were re-pointed to 100 so stage 1 still verifies clean and `--undo` still writes 80.
2. Unit computed-HP cap cave, `build_medal_hpmv.py` **v4**, `0x55818086`/`0x5581808B`.
3. Editor `HitsEdit` spinners, `build_editor_spinners.py`, ladder 50/120/100, 4 sites across both
   editor exes.
4. (implicit) `Set == Get` preserved at **100/100** — margin under the wall is now **27**, not 7.

⚠ **Existing saves: a hero already above 100 HP loses the excess, and spent skill points stay spent.**
`hero+0x6D` stores the *purchased* bonus, not the total; `GetHits` clamps `base+0x6D` to 100, so a hero
at base 30 + 90 purchased reads 100 and the top 20 points (40 skill points at 2/point) are dead.
Nothing corrupts or wraps — the next `SetHitPoints` simply clamps current HP down to the new max. New
purchases are refused past 100. No unit or hero base exceeds 100 (`Unitres.pfs` HITS max 60,
`HERORES.PFS` max 30 — see the headroom note below), so the cap only ever truncates *totals*, and this
is the first thing to check when testing in an existing game.

**⚠ The cap must stay ≤127 for a structural reason, and it is now enforced rather than remembered.**
Every `build_hero_clamps.py` bound uses `66 83 F8 ib` (opcode `83 /7`), whose imm8 is **sign-extended**,
and the stored byte is read back with `movsx`. A ceiling of 150 (`0x96`) becomes **−106**: `jle` is
then false for every non-negative value, the clamp fires on *every* call, and the getter returns a
constant 150 — the clamp inverts from a cap into a force. The write loop now carries
`assert 0 <= w <= 0x7F` inline. Separately, `build_newturn_healcap.py`'s cave narrows both HP values
with `movsx ecx/edx,al` (sign-extension) — a cap above 127 would make those bytes negative and invert
the heal clamp.

**Headroom check.** `Release/Unitres.pfs` HITS after doubling: 179 records, min 6, max **60**, mean 20.
Worst realistic total: `60 + rank3×2 + 200/5 = 106` — under the cap. The cap legitimately binds only
for a maximum-XP low-level unit, which is itself evidence that every "120" seen in play before the fix
was the defect above, not a legitimate cap hit.

⚠ **Open congruence question, deliberately left unresolved.** Base HP doubled but the XP-to-HP term
(`XP/(level+1)`) did **not** — a veteran now gains proportionally *less* HP from experience than
before the conversion. Doubling that term too would push the worst case to ~206 and break the ≤127
wall; a real design choice, not an oversight.

### Hero ATK Set/Get split — the trap that also produced the HP bug's cousin

An independent audit (not the user, not the HP bug) found live hero **ATK** points bought above 40
were silently discarded: `THero.SetUnitAttack` purchase cap was **60** (`cmp edx,0x3c @0x557877D6`)
while `THero.GetAttack`'s effective ceiling was **40** (`cmp ax,0x28 @0x557883C8`) — a half-finished
migration (the conversion's D4 raised the purchase cap 30→60; the getter ceiling was hand-set to 40
separately on 2026-08-20; nobody reconciled them). Full Set/Get table at the time:

| stat | purchase cap | effective ceiling | |
|---|---|---|---|
| Attack | 60 | 40 | ⚠ wasted points |
| Defence | 40 | 40 | ok |
| Damage | 40 | 60 | benign — extra 20 is item/ability-only headroom |
| Resistance | 40 | 40 | ok |
| Hits | 120 | 120 | ok (then 100/100, §above) |
| Moves | 80 | 80 | ok |

**Resolved 2026-08-26: `Set == Get` for all five pairs.** ATK/DEF/DAM/RES **40/40**; HITS **100/100**
(120/120 until 2026-08-31). Byte-checked against pristine: vanilla is *also* Set==Get for all six
stats (10/10 ATK/DEF/DAM/RES, 30/30 HITS) — confirming this is the correct invariant, not a new
convention. ⚠ Consequence recorded deliberately: `TUnit.GetDamage` ceiling is **60**, so heroes now
cap *below* units on damage (vanilla had both at 10) — reversible in `build_hero_clamps.py` if
unwanted in play.

### Gaps both passes missed — the (POWER, DAMAGE) defect class

> A paired **(POWER, DAMAGE)** site where POWER fell in the 5% conversion's scope and was caught,
> while DAMAGE ten-to-twenty bytes later fell in the DAM/HP pass's scope and was never enumerated —
> so **neither manifest contains it, and both scripts report a clean all-clear.** A coverage claim
> must be derived from the manifest, never written by hand.

**⭐ The worst instance: both passes patched dead code.** `build_firefeed.py` overwrites
`TriggerFireDamage`'s immunity gate at `0x5579020C` with `jmp 0x5580DAD0`, so the original body at
`0x55790211..0x55790227` **never executes**. Both the 5% pass and the DAM/HP pass wrote their doubled
values into that dead body (`0x5579021D`=12 attack, `0x55790218`=6 damage) while the *live* cave held
stale values (`0x5580DB07`=6, `0x5580DB02`=3). Because Defence doubled **and** the slope halved, an
undoubled attack is a net **loss**, not a halving — burn chance against a DEF-5 unit fell from ~65% to
~35%, and with the stale damage on top, strategic map fire ran about **4× too weak**. The
fire-heals-fire "+N" heal was halved too (it reuses this caller's ECX/EDX verbatim).

**Fixed 2026-08-26** in `build_firefeed.py`: `MAPFIRE_ATK`/`MAPFIRE_DAM` = **12/6**, written to the
live cave (not the dead body). The script's verify-before-write now accepts a *list* of prior cave
bodies, so the cave is re-tuned in place rather than reverted. ⚠ Never "fix" this by restoring
`TRIG_ORIG` to make the doubled *dead* body live — that reverts fire-heals-fire. ⚠ A foreign
byte-poke into the cave is silently reverted by the next `--apply`.

**Standing check this earned:** scanning all 383 manifest addresses for an `E9` cave hook within 40
bytes *before* the site returns exactly the two map-fire hits plus two already-known/already-flagged
cases — cheap, and it is the one check that would have caught the miss. Worth adding to `aow-qa`.

**`build_damhp_gapfix.py` — three more sites in neither manifest**, ladder model, surgical `--undo`,
backup `.pre-damhpgapfix`:

| site | address | was | now |
|---|---|---|---|
| Burning tick damage | `0x557BA475` | 2 | **4** |
| Decay tick damage | `0x557BA772` | 1 | **2** |
| Turn Undead AI heuristic damage L1–L4 | `0x5576B223/226/229/22C` | 4/8/12/16 | **8/16/24/32** |

Burning's POWER twin at `0x557BA464` *is* in the 5% manifest (10→20, applied) while its damage 17
bytes later was in nothing. Decay has no `HitRole` on its path at all, so no POWER half ever existed
to drag it into a manifest — Mind Decay's spell ATTACK (`0x557F8581`) was doubled 6→12 while this,
its entire damage output, was untouched. Turn Undead here is **AI-only** (real combat damage flows
through `build_turnundead_res.py`'s caves, which do carry ×2) — the one live caller is the AI
heuristic `GetOffensiveStrength @0x5576AEDA`, whose **ceiling** the DAM/HP pass doubled (5→10,
`0x5576AEE6`/`EA`) while never doubling the value being clamped. Smoking gun for the whole defect
class: fix the input, not the ceiling.

**Verified correct — do NOT "fix" these:** the six elemental-Resistance effect-roll powers
(`0x55781C31` etc., now **10**) and their six Protection bonuses (now **+4**); every fear/entangle/
touch check (Entangle 14, Entangle Strike 14, Web 14, Possess 14, **Terror 12**, Cause Fear 10, Holy Fear
8, Charm/Dominate/Seduce 10, Invoke Death 18 — Cause Fear has no class of its own, it is a flag set in
`TStrikeCA.Generate`, roll `10 − defender stat`, gated by Fearless `0x43`); durations never double
(Burning 2, Entangled 2, Frozen 3, Webbed 3, Stunned 1, Holy Fear 3, Vertigo 3, Cursed 3, default 4);
the touch-fail sentinel `−10 @0x557680CD` and its three guards must stay mutually consistent; the
buff/debuff regrade is one notch **below** the doubled value on purpose (Bloodlust +3, Poisoned −3,
Enchanted Weapon +3/+3, Dark Gift +3, Stone Skin +3, Fury +5/−2, Vertigo −3/−3 — a naive
sweep reads these as un-doubled; they are not); the two dead map-fire copies are already doubled and
unreachable — leave them.

⚠ **Blessed and High Prayer Blessing are NOT in that list** — they were exempted on 2026-09-13 (E8)
and sit **at** the doubled value, DEF +2 / RES +4, except High Prayer RES which is one *above* it.
So for these two the naive reading is the right one. See `02-abilities-modded.md`.

⚠ **Terror's 12 is a deliberate design value (2026-09-09), not a conversion artefact — do not
"restore" it to 16.** The conversion left it at 16 and `_old/FivePct_Doubled_Sources_Inventory.md`
records that as "8 → 16"; both are accurate history and stay as they are. The user then set the
value to 12, which is `build_terror_atk12.py`'s target and the number the live DLL now holds at all
**five** sites. A future audit that diffs live-vs-manifest will flag Terror as "un-converted": it is
not, it is re-tuned. See `04-spells-modded.md`.

### Morale re-scaled (`build_morale_scale.py`, reverses the D2 exception)

The 5% conversion deliberately left morale unscaled ("becomes half as influential" — D2). On the
doubled scale a morale swing bit half as hard while the Manual still printed the old numbers. Reversed
by user ruling. **Ziggurat's arrangement is not vanilla's, and the difference decides what to edit:**

- **ATTACK is a Ziggurat addition** — vanilla has no morale→ATK link. `TUnit.GetAttack` hooks a cave
  at `0x5580C0FC` reading morale from `[ebx+0x26]`, five bands, clamped [0,40]. Ladder
  `−2/−1/0/+1/+2` → **`−4/−2/0/+2/+4`**. ⚠ Has bonuses at high morale, not only penalties at low. Two
  rungs had no immediate to double (`dec al`/`inc al`) and were re-encoded in place as
  `sub al,2`/`add al,2` — same length, no jump displacements move.
- **RESISTANCE** — `MoraleResistanceModifier 0x558E83D8`, vanilla `[−2,−1,0,0,0]`, pre-rescale
  Ziggurat `[−3,−2,−1,0,+1]`, now **`[−6,−4,−2,0,+2]`**. Read by `TUnit.GetResistance @0x55782AF7` /
  `THero.GetResistance @0x5578856D`.
- **DEFENCE deliberately NOT changed.** `MoraleDefenseModifier 0x558E83E0` stays vanilla
  `[−2,−1,0,0,0]` and is still live (readers: `TUnit.GetDefense @0x55782A6B`, `THero.GetDefense
  @0x55788449`, cave `0x5580BFCE`). The ruling named Attack and Resistance only — morale's Defence
  component remains half as influential. Trivial to add if that is ever unwanted.

### `AoWTCPCK.dpl` — the module the DAM/HP pass never wrote to, now fixed

`build_damhpdouble.py`'s 145 manifest entries are all `AoWEPACK.dpl`; the 5% conversion *did* write
here (4 bytes), so manual tactical combat was left half-converted — every ATK/DEF value on the new
scale, every DAMAGE and HP value on the old one. Whole-file diff live vs `.pre-statdouble` was exactly
those 4 bytes and nothing else (`0x004ED8`, `0x00FD3F`, `0x0661A4`, `0x0661A8`).

**Symptom: the game held three independent wall-HP representations.**

| representation | where | vanilla | before this fix | **now (unified)** |
|---|---|---|---|---|
| `TWallUnit.SetWallType` | combat predictor, AoWEPACK | 10 / 5 | 20 / 10 | **40 / 10** |
| `TCombatWall.GetHits` | auto-resolve, AoWEPACK | 10 / 5 | 48 / 16 | **40 / 10** |
| `AoWTC.WallMaxHP` | manual tactical, AoWTCPCK | — | 13 / 7 | **40 / 10** |

A stone wall had 13 HP in a hand-fought battle, 20 in the predictor that forecast it, and 48 if
auto-resolved — against damage that had doubled everywhere. Manual sieges razed walls roughly **2×
faster than the predictor promised and 3.7× faster than auto-resolve.**

**⭐ User ruling 2026-08-26: all three unified at 40 stone / 10 wood** — a *balance* decision, not a
pure doubling (a straight ×2 rescale would have landed at 26/14). Do not "restore" it to ×2 of vanilla
or of Ziggurat. Script: `build_tcpck_damhp.py`, ladder model, verify-before-write, surgical `--undo`,
backup `.pre-tcpckdamhp`. **Applied 2026-08-26, untested in game.**

| site | address | was | now |
|---|---|---|---|
| `TCDamage[0]` melee Wall Crushing | `0x004671AC` | 6 | **12** |
| `TCDamage[1]` burning fire hex / turn | `0x004671B0` | 1 | **2** |
| `WallMaxHP[0]` wooden wall + every city door | `0x004675F8` | 7 | **10** |
| `WallMaxHP[1]` stone wall | `0x004675FC` | 13 | **40** |
| `TCombatTerrain` HP | `0x0041092B` | 3 | **6** |
| `TCombatStructure` HP ×3 | `0x00432849`/`0x0043290E`/`0x0043291D` | 5 | **10** |
| `MakeHitBlood` blood-spray band widths 1–2 | `0x0040996C`/`0x00409971` | 3/4 | **6/8** (band 3 left at `0x5D`) |

⚠ **Single-apply congruence group** — damages and the HP pools they eat must land together, or walls
crumble twice as fast (damage-only) or manual siege/fire becomes half as effective (HP-only, e.g. a
1-damage fire hex needing 26 turns to burn a stone wall). ⚠ `fivepct_manifest.json` recorded
`WallMaxHP[0..1]` as **one** width-1 entry — wrong: they are two separate int32 words, reached through
Delphi `IMPORTEDDATA` indirection (`mov edx,[<slot>]; mov edx,[edx+idx*4]`); the slots are `.reloc`'d,
the array values are not — patch the values, never the pointer slots. ⚠ Adjacency traps on every side:
`WallISIndex` sits 8 bytes before `WallMaxHP` and `ImageLib.Get` has no bounds check; `clusterChk` sits
immediately after; a literal `mov byte [eax+0x4d],1` inside the HP setter is a "wall breached" boolean,
not HP, at the exact byte-offset AoWEPACK's *different* `TCombatWall` uses for its HP byte. ⚠ Blood
band 3 (`0x5D`) is **deliberately left alone**: raising it to `0x7F` was tried on the theory that
raised damage ceilings made 108-126 reachable — they don't (single-hit damage is bounded by the DAM
stat, ceiling 60; 15..107 already covers everything attainable) — and doubling it properly would need
a 5-byte `2D imm32` where there is a 3-byte `83 E8 ib`, displacing two short jumps. **Recorded failed
approach — do not retry the naive `0x5D→0x7F` bump.**

Safe by construction, verified: no signed-byte-127 hazard in this module (every HP path is 32-bit end
to end); wall damage art rescales for free (a pure ratio, no hard-coded threshold); no AI edit needed
(the five AI readers index the live array, not a copy); `TCombatTerrain.SetHitPoints` discards its
argument (inert — doubled anyway for consistency with its Defence sibling); `TCombatObstacle` has no
HP field (indestructible by design); ranged Wall Crushing takes every number from already-doubled
AoWEPACK ability data. **Expected, not a bug: fire gets ~25–33% slower** at `TCDamage[1]`=2 against
doubled pools (the rounding formula degenerates to exactly 1 at damage 1, ~1.5 at damage 2) — generic
to tiny-magnitude damage under this programme, not a defect.

**In-game checklist (untested):** manual siege hit-count on stone and wooden walls / city doors should
be unchanged from before the whole DAM/HP+5% programme (a rescale, so any change in hit count is a
bug); predictor forecast should now match manual; auto-resolve should no longer raze walls dramatically
faster than manual; all four wall-damage art stages still appear at the same relative points; Wall
Crushing's info-card damage should now agree with what actually lands (previously 12 vs 6); fire in
tactical combat should still destroy walls/terrain/structures, just ~25–33% slower than intuition
suggests; combat structures shouldn't die to half the previous hits; map editor structure-placement
preview HP should match in-game; tactical AI during a siege should neither over- nor under-commit;
save/load a partially-damaged wall; one full ordinary (non-siege) tactical battle as a smoke test.

---

## 5. Hero stat clamps and chassis

**Status: the ATK/DEF/RES ceiling raise (30→40) is ✅ CONFIRMED WORKING (2026-08-24)**, applied
2026-08-20, and has not moved since. Everything the ladder has done *after* that confirmation —
DAM ceiling 40→60→40 (H4, then the 2026-08-26 Set/Get reconciliation), the ATK purchase-cap fix that
same day, and HITS 120→100 (2026-08-31) — is **🔨 APPLIED, UNTESTED**; none of it has been separately
re-confirmed in-game. `build_hero_clamps.py` now owns every bound (ceiling *and* floor) on
`THero.GetAttack`/`GetDefense`/`GetResistance`/`GetDamage`/`GetHits`, plus the HITS purchase cap in
`SetUnitHits` (moved here 2026-08-31 — see §4). Current ladder-model state: ATK/DEF/RES ceilings
**40**, DAM ceiling **40** (was 60 under H4, returned to 40 on 2026-08-26 to restore Set==Get), HITS
ceiling **100** (was 120), DAM and HITS floors **2**.

⚠ **Every bound is a PAIR of immediates**, not one — the test and the value written when it trips are
separate instructions:

```
557883C8  66 83 F8 28   cmp ax, 0x28         <- imm at +3
557883CC  7E 04         jle  short
557883CE  C6 04 24 28   mov byte [esp], 0x28  <- imm at +3 (SEPARATE instruction)
```

Patching only the `cmp` produces a silent discontinuity: 31–40 pass through, anything above 40 snaps
back to **30**. That half-patched state was actually reached during this work and caught only by
disassembling the result. `fivepct_manifest.json` lists only the `cmp` immediates for these sites —
treat every `UNCHANGED` clamp entry in any manifest as under-specified until its `mov` twin is found.

⚠ **Two different encoding shapes.** ATK/DEF/RES/DAM use `cmp ax,imm8` (`66 83 F8`) +
`mov byte [esp],imm8` (`C6 04 24`). `GetHits` uses `cmp dx,imm8` (`66 83 FA`) + `mov al,imm8` (`B0`).
`TUnit.GetDamage @0x55782AD4` (imms `0x55782AD7`/`0x55782ADB`) is deliberately **not** touched by this
script (unit damage was never doubled by anything separate from the general DAM/HP pass, only hero
chassis damage needed room) and uses **yet another** encoding: `cmp dx,imm8` test but `mov al,imm8`
(`B0 nn`, two bytes) rather than `mov byte [esp],imm8`.

| getter | ceiling | set by |
|---|---|---|
| `THero.GetAttack`/`GetDefense`/`GetResistance` | **40** | `build_hero_clamps.py` |
| `THero.GetDamage` | **40** | `build_hero_clamps.py` (60 under H4, returned to 40 2026-08-26) |
| `THero.GetHits` | **100** | `build_hero_clamps.py` (was 120; floors 2) |
| `THero.SetUnitHits` purchase cap | **100** | `build_hero_clamps.py` since 2026-08-31 (ladder 80/120/100) — must equal `GetHits` |
| `TUnit.GetAttack` | 40 | 5% conversion stage 1 (two copies; `mov` twins repaired) |
| `TUnit.GetDefense`/`GetResistance` | 60 | 5% conversion stage 1 (twins repaired) |
| `TUnit.GetDamage` | **60** | `build_damhpdouble.py` (H4) |
| unit computed-HP total | **100** | `build_medal_hpmv.py` cap cave (v2→120, v3 fixed the quotient bug, v4→100) |

**Ladder model.** Each row lists every value it has legitimately held, oldest first; the target is
the last. Any ladder value verifies (half-applied states are repaired by writing the target); any byte
off the ladder aborts. `--undo` writes `ladder[0]` everywhere, byte-identical to
`AoWEPACK.dpl.pre-heroclamps`.

### Hero chassis — ATK ×1, DAM ×2

`THeroResource` — the 38 records in `Release/HERORES.PFS`, the stat template a hero is built from
(`THero.LinkToResource @0x55787984`; live stat = chassis + bought bonus + item + ability). Field map,
proved by the getter that actually reads each field, **not** by the ambiguous cost multipliers alone
(5/5/**10**/5/2 for ATK/DEF/DAM/HITS/MOVES/RES in `UsedSkillPoints` — DAM and HITS are both plausible
at cost-adjacent values):

| tag | field | stat | proved by |
|---|---|---|---|
| `0x0F` | `+0x24` | **ATTACK** | `THero.GetInherentAttack @0x55788354` |
| `0x10` | `+0x25` | Defence | `GetInherentDefense @0x557883DC` |
| `0x11` | `+0x26` | **DAMAGE** | `GetInherentDamage @0x55788478`, `GetDamage @0x55788484` |
| `0x12` | `+0x27` | Hit points | `GetHits @0x5578859C` |
| `0x13` | `+0x28` | **Movement** | `GetMoves @0x557885C0` — the `build_statdouble.py`-documented trap: applying `Unitres.pfs`'s tag map here doubles movement and misses resistance |
| `0x14` | `+0x29` | Resistance | `GetInherentResistance @0x55788500` |

Two user instructions in order produced the current tuning: *"double all the ATK/DAM values"* (both
doubled) then *"don't quadruple ATK"* (**ATK returned to ×1**, DAM kept at ×2). 38 damage bytes scaled
(1..4 → 2..8); the 38 attack bytes are written back to exactly the stage-2 (5%-conversion) value, so
this script and `build_statdouble.py` agree on them. ⚠ **Chassis DEF/RES are already doubled by
stage 2** (DEF 1..4→2..8, RES 2..6→4..12) — doubling them again here would quadruple them, exactly what
the second instruction ruled out; this script deliberately owns only ATK and DAM.

**Damage doubling is a balance change, not part of the conversion identity** — under the identity only
ATK/DEF/RES double, damage never does, so chassis damage ×2 roughly doubles hero base damage output
and must never be "corrected" back by a future session reading only the conversion rules. Attack, by
contrast, sits exactly where the conversion identity put it.

⚠ **Undo order — both this script and `build_statdouble.py` stage 2 write the same 38 ATTACK bytes.**
`build_statdouble.py --undo` halves ATK/DEF/RES and does not touch DAMAGE:

```
undo:     build_hero_chassis_atkdam.py --undo   THEN   build_statdouble.py --undo
re-apply: build_statdouble.py --apply           THEN   build_hero_chassis_atkdam.py --apply
```

While ATK's factor is ×1 the two scripts write identical bytes and the order is harmless; it stops
being harmless the moment ATK is raised again — a wrong order leaves `HERORES.PFS` in a mixed state
(ATK at pre-state, DAM still scaled) that the chassis script's all-or-nothing vector check detects and
aborts on, but cannot repair.

### Hero skill points — the budget, the price list, and the hero library

**Status: `build_heroskill_spend.py` — 🔨 APPLIED, UNTESTED (2026-09-08).** Data edit only; no
binary is patched. Everything below was read from the live binaries, not from a decompile.

**Budget.** `THero.GetSkillPoints @0x557875C4` returns `level*10 + 10 - UsedSkillPoints`, and on the
map-present arm only, also `- [hero+0x50]` (`0x557875F3 sub eax,[ebx+0x50]`; the no-map arm at
`0x557875F8` omits it). The `+10` is **three** separate immediates and they must move together —
vanilla is `+15`:

| instruction VA | immediate VA | instruction | path |
|---|---|---|---|
| `0x557875ED` | `0x557875EF` | `83 C0 0A` `add eax,0Ah` | map present |
| `0x5578760A` | `0x5578760C` | `83 C0 0A` `add eax,0Ah` | no map / bit 1 of `[*0x558FA040+0x3C]` |
| `0x5578761E` | `0x55787620` | `83 C2 0A` `add edx,0Ah` | `GetSkillPointsMax @0x55787614` |

⚠ Disassemble from the **instruction** VA; the immediate VA is what a byte-patch manifest records
(and what `build_heroskill_spend.py`'s guard reads), and `dasm.py` at that address returns garbage.

⚠ It reads the level from the **cache** `[hero+0x4C]` (tag 0x16), while `GetLevel @0x55787740`
derives it from XP `[hero+0x48]`. `SetLevel @0x55787750` writes both; anything editing one must
write the other.

⚠ **`[hero+0x50]` is a per-hero write-off (tag 0x27) and it is NOT free storage.** It is absent from
every record in the hero *library file*, which makes it look dead — but `THero.NewDay` writes it at
runtime:

```
55786CB5  call THero.GetSkillPoints
55786CBA  mov  dword ptr [ebx+0x50], eax
```

gated on `map[+0x174]==1 && (engine[+0x70]==0 || player==null || player[+0xA7]!=0) &&
(map[+0x149]==0 || !IsClass(hero,TLeader))`.

⭐ **This is the day-1 confiscation of unspent skill points, and it is vanilla** (NewDay,
GetSkillPoints and UsedSkillPoints are all byte-identical to the root reference). `map[+0x174]` is
the **day counter**, so `== 1` means it fires **once, on the first day only** — the write is
self-referential but never iterates. Since `writeoff' := (budget − used) − writeoff`, the points
still spendable afterwards are **exactly the value the map stored in tag `0x27`**, independent of
level: absent tag ⇒ 0 ⇒ every unspent point a map-placed hero started with is gone. `0x55786CBA` is
the **only** writer of `[hero+0x50]` in the module.

The two exemptions:

| gate | meaning | effect |
|---|---|---|
| `engine[+0x70] != 0` **and** `player[+0xA7] == 0` | a **campaign** is loaded (`TAoWEngine.LoadCampaign` writes `+0x70`, `CloseCampaign` clears it) and the hero's owner is a **human** player (`+0xA7` is the player-type enum, 0 = human, 1..7 = AI kinds — `TAIPlayerControl.Activate` switches on it) | skipped entirely |
| `map[+0x149] != 0` **and** `IsClass(hero,TLeader)` | `+0x149` is the **"Customize leaders"** setup checkbox — `TSetupControl.SetupMap+0x529 @0x557E108D` copies it from `TSetupSettings[+0x2A]` (stream id `0x10`, **default 0**, `TSetupSettings.Reset @0x557DF5A4`) | leaders only |

⚠ So in a non-campaign game (skirmish, hotseat, PBEM, network MP) with "Customize leaders" off —
the default — **every hero on the map, leaders included, loses its unspent points at the start of
day 1**. Setting a leader to level 5 in the editor and expecting the 60 points to be spendable at
the next level-up does not work; the hero gets only the 10 the new level adds. Nothing else reads
`[hero+0x50]` but `GetSkillPoints` and `GetSkillPointsMax`, and the field is streamed (tag `0x27`,
dword) so a pre-set value survives in maps and saves.

⚠⚠ **In PBEM the vanilla lever is unreachable.** `AoWz.exe @0x00410D44` `cmp byte ptr
[TSetupSettings+0x3C], 2` disables the "Customize leaders" checkbox (`0x00410D60`
`mov byte ptr [ctrl+0xC0], 0`, label greyed to `0x808080`) and restricts the Turns combo to
"Classic". `+0x3C` is the session mode, written only by `TSetupControl.SetupHost+0x3A @0x557E24EA`
and copied to `map[+0x13A]`; **2 = play-by-email**, proven by `TAoWHSMap.SetupPlayerControl
@0x55777F1C`, which builds `TPBEMPlayerControl` for exactly that value. The enabled branch is
`0x00410DC2`. ⭐ Customising does **not** replace the scenario's leader: `hPickMap @0x557E20C8`
copies each map player's leader into `TPlayerSetupSettings[+0x1C]` (a real `TLeader` from
`TPlayerSetupSettings.Create`), the dialog edits that copy, and `SetupMap` copies it back — a round
trip, skipped when `TSetupSettings[+0x20] != 0`, which `hPickMap` reads from the map header `+0x174`.

**Price list** — `THero.UsedSkillPoints @0x55786CC8`, each price bound to its field:

| stat | field | live price | site |
|---|---|---|---|
| ATK | `+0x6A` | **3** | `0x55786CD1 6B F8 03` |
| DEF | `+0x6B` | **6** | `0x55786CD8 6B C0 06` |
| DAM | `+0x6C` | **4** | `0x55786CE3 6B C0 04` (two `90` nops precede it) |
| RES | `+0x6F` | **2** | `0x55786CEC 6B C0 02` |
| HP | `+0x6D` | **2** | `0x55786CF5 6B C0 02` |
| MOV | `+0x6E` | **3** | cave `0x5580C800`, called from `0x55786CFA` |

⚠ The AI level-up chooser's five gates must equal these prices; `build_ai_levelup_gates.py` checks
and re-syncs them, so re-run it after any re-price.

Then, per ability id the hero has: `+ Ability.GetSkillPoints(hero)`, and if the **chassis** has it
too, `- Ability.GetSkillPoints(chassisOwner)`. ⚠ The entry point is VMT **`+0x80` `GetSkillPoints`**,
not `+0xC8 ExpandCost`. The chassis's own ability owner is `[[hero+0x40]+0x2C]` = `HERORES.PFS`
tag `0x1D`, a `top=False` directory.

⭐ **The chassis credit is large and you cannot price a hero without it.** Measured 2026-09-22 on a
live map: four leaders priced from their save records alone came out at −12 to −70 points, i.e.
apparently over budget, while the editor's own Leader Properties reported one of them at
**44/90 unspent**. Leadership 10 + Spell Casting 20 + Vision 4 is 34 of credit on its own. Never
conclude "this hero has no points" from the hero record in isolation.

`THeroResource.UsedSkillPoints @0x55789F50` prices the **chassis** on a different scale entirely:
ATK `+0x24` ×5, DEF `+0x25` ×5, DAM `+0x26` ×10, **HP `+0x27` ×5, MOV `+0x28` ×2, RES `+0x29` ×5.**
⚠ It does not price the fields in tag order — the `×5` at `0x55789F70` reads `+0x29` (RES) and the
one at `0x55789F79` reads `+0x27` (HP), so reading the multipliers off in source order gives HP/MOV/RES
as 5/5/2 when they are 5/2/5. Never mix this list up with the hero one above. ⭐ This is the scale the
**editor's Leader Properties dialog shows** (`Attack (sp:5)`, `Damage (sp:10)`, `Moves (sp:2)` …), so
a price quoted from that dialog is the chassis price, not the hero one.

**Ability prices.** Single-level: `TAbility.GetSkillPoints @0x5574E958` returns `[ability+0x14]` =
`Ability.pfs` tag 6. Multi-level: `TMultiLevelAbility.GetSkillPoints @0x55765348` looks like a sum
but is not — the loop re-reads `list[level]` `level` times, so it is **`cost * abilityLevel`**, and
the contribution over a chassis is `cost * (heroLevel - chassisLevel)`.

| ability | id | live cost | levels | where the constant lives |
|---|---|---|---|---|
| Vision | 64 | **4** | 1..9 | cave `0x55817000` (`build_vision9.py`), ctor tail-jmp at `0x557B9897` |
| Marksmanship | 32 | **6** | 1..8 | cave `0x55817400` (`build_marksmanship8.py`), tail-jmp `0x557BBD67` |
| Leadership | 46 | **10** | 1..4 | cave `0x5580EFC0` (`build_leadership4.py`), `call` at `0x557661A2` |
| Spell Casting | 52 | **20** | 1..5 | inline, `0x5576DBE1` + `0x12`·k, five `mov ecx,14h` |

⚠ **`Ability.pfs` tag 6 is inert for multi-level abilities and gives the wrong number** — Leadership
tag 6 = 20 against a live 10, Spell Casting tag 6 = 15 against a live 20.
⚠ **Leadership's constructor immediate at `0x55766195` (`mov ecx,14h`) is DEAD code.** The `call`
after it was retargeted to the cave. ⚠ **Pristine reads 10 there; only the LIVE file reads 20** —
the 20 is an earlier, unrecorded Ziggurat edit of that dead immediate, byte-checked 2026-09-10 and
claimed by no build script. The answer is 10 either way, from the cave.

`TAbilityOwner.UpdateDefaultAbilities @0x5574F518`, run from `THero.Loaded` on every load, copies a
chassis ability and its level record onto the hero wherever the hero's level is lower — so the
effective level is `max(hero, chassis)` and the chassis credit always cancels exactly.

**Level ↔ XP.** `HeroExperienceTable @0x558E84B4`, stride 8. The **XP column is at `+4`**, i.e.
`0x558E84B8`: live `20,30,40,50,60,70` against vanilla `15,15,20,20,25,25`. So levels 1–9 sit at XP
**0, 20, 40, 60, 80, 110, 140, 170, 200** (re-derived from the live table 2026-09-22).

```
LevelToExperience(L) @0x557876A0 = sum over k=1..L-1 of table[k div 5], skipping (k div 5) > 5
ExperienceToLevel(xp) @0x557876D4 = walk L upward until the running sum exceeds xp
```
⚠ `ExperienceToLevel` has **no `> 5` guard** — it reads past the table end above level 30. The two
are not inverses up there and must not share one implementation. ⭐ Below that they ARE exact
inverses, and the `jg` is strictly-greater, so `ExperienceToLevel(LevelToExperience(L)) == L` with no
off-by-one — verified for L = 3, 5 and 8 against the live table.

**The five `ExecuteUpgradeHeroAI` constants are skill-point gates, set equal to the prices** —
`build_ai_levelup_gates.py`, 🔨 APPLIED, UNTESTED (2026-09-24).
- **How the routine works:** `THero.ExecuteUpgradeHeroAI @0x55787A24` sets
  `esi = GetSkillPoints` (`0x55787A49`). It offers a stat only when `cmp esi,N / jl` passes and
  `bought + chassis` is under the cap (`cmp eax,M / jge`; live caps 20/20/20/20/60). So N means
  "unspent points on hand", not a level.
- **History:** vanilla's N values, 5/5/5/10/5, are exactly vanilla's prices. Ziggurat carried a
  hand-edit 4/16/8/8/3, which a 2026-09-08 ruling read as target levels. Under it, DEF was offered
  only while the AI held 16+ unspent points.
- **Owner ruling 2026-09-24:** match the prices.

| gate imm | field | stat | was | now = price |
|---|---|---|---|---|
| `0x55787A52` | `+0x6A` | ATK | 4 | 3 |
| `0x55787A77` | `+0x6B` | DEF | 16 | 6 |
| `0x55787A9F` | `+0x6F` | RES | 8 | 2 |
| `0x55787AC7` | `+0x6C` | DAM | 8 | 4 |
| `0x55787AEF` | `+0x6D` | HP | 3 | 2 |

⚠ The gates must move with the prices. The script reads the prices from `UsedSkillPoints` rather
than hard-coding them, so after any re-price its dry run says DRIFT and `--apply` re-syncs. Surgical
`--undo` restores 4/16/8/8/3.

In-game checklist:
1. Follow an AI hero over several level-ups: DEF and RES now rise too, not only ATK and HP.
2. AI heroes still stop at the caps (20; HP 60).
3. No AI hero ends a level-up with negative unspent points.

The same routine's three ability offers at `0x55787B72`, `0x55787B93` and `0x55787CE6` are **Frost
Bolts `0x7A`** where vanilla offers **Archery `0x16`**. That is a deliberate owner hand-edit, confirmed
2026-09-24, with no owning script.

**Caps** (`SetUnitAttack @0x557877BC`, `SetUnitHits @0x557878A0`): ATK `cmp edx,28h` at `0x557877D6`
= **40**, HP `cmp edx,64h` at `0x557878BA` = **100**, both against `chassis + bought`.
⚠ **`THero.Loaded @0x5578799C` will not correct an over-spend.** It re-runs every setter with
`value == current`; `cmp bl,[esi+0x6a] / jle` takes the free branch and skips the budget check — but
the cap clamp above it still fires, so an over-cap stat is **silently truncated** with no error.
Assert the caps before writing; do not rely on the engine.


### Unspent skill points are offered — `build_hero_turn1_upgrade.py`

**Status: 🔨 APPLIED, UNTESTED (2026-09-22, v2).** `AoWEPACK.dpl` only; `THero.NewTurn` and
`THero.NewDay` exist in no other module, so there is no `AoWz.exe`/`AoWzCompat.exe` lockstep half.

⭐⭐ **The real defect is not the confiscation — it is that a level SET in the editor can never open
the spend UI.** Measured live 2026-09-22 (out-of-band `ReadProcessMemory` poller across a real PBEM
game start, plus the editor's own Leader Properties): a leader authored at level 8 arrives with
**44 of 90 points unspent**, `[hero+0x50] == 0`, and no dialog, ever. `ValidateHeroUpgrade
@0x55787D54` — called from `THero.NewTurn @0x55787FE7` on the owner's turn — fires only on a **lag**:

```
if (hero.levelCache[+0x4C] < GetLevel())          ; GetLevel derives from XP [+0x48]
    hero.levelCache = GetLevel()
    raise THeroUpgradeEventLog(old -> new)        ; this IS the level-up dialog
    if (player[+0xA7] != 0) ExecuteUpgradeHeroAI  ; AI spends its own
```

⚠⚠ `THero.SetLevel @0x55787750` writes **both** `[+0x48] = LevelToExperience(level)` and
`[+0x4C] = level`, so cache `==` GetLevel() from the moment the map loads. Measured: Grozt cache 8 /
XP 170, and `LevelToExperience(8)` is exactly 170. The points stay stranded until the hero naturally
earns past the **next** threshold (level 9 at XP 200); everything banked below it is never offered.

**The patch — two sites, one cave.** `SITE 1 0x55786CB3` (10 B) → 10 × `nop`, disarming vanilla's
day-1 confiscation; both inbound jumps land on the run's boundaries so the whole run is safe to blank.
`SITE 2 0x55787FE7` (5 B) retargets `call ValidateHeroUpgrade` to the cave — the call-retarget idiom,
4 displacement bytes, nothing displaced. `C_TURN1 = 0x5584B000`, **129 bytes since v3** (46 in v2),
PIC (rel32 transfers; v3 reaches the map through a `call $+5` anchor):

```
push ebx / mov ebx,eax
call THero.GetSkillPoints @0x557875C4 / test eax,eax / jle done      ; guard 1
mov eax,ebx / call THero.GetLevel @0x55787740
movsx eax,al / movzx edx,byte [ebx+0x4C] / cmp eax,edx / jl done     ; guard 2
cmp dl,1 / jbe done                                                  ; guard 3
map = [anchor + (0x558FA040 - anchor)] ; player = GetPlayers([map+0x140], movsx [ebx+0x24])
pbemday1 predicate && [player+0xD4] == ebx -> done                   ; guard 4 (v3, 2026-09-24)
dec byte [ebx+0x4C]
done: mov eax,ebx / pop ebx / jmp THero.ValidateHeroUpgrade @0x55787D54
```

EDX/ECX are clobbered, which is safe: the call site sets only EAX (`mov eax,esi @0x55787FE5`) and
`ValidateHeroUpgrade` overwrites its third argument before reading it.

⚠⚠ **Guard 2 is the load-bearing one and its absence is silent.** `[hero+0x4C]` is tag `0x16` and is
**persisted**. If the cache were ever above the XP-derived level, the decrement would not be undone —
a permanent 10-point budget loss written into the save. Guard 1 makes the behaviour self-limiting
(once spent, it stops firing) and means a hero who **declines** is offered again next turn, by design.
Guard 3 floors the cache at 1, because this write bypasses `SetLevel`'s clamp.

**Scope**: every hero, every turn, on its owner's turn — map-placed, recruited, or levelled in play.
AI-owned included; `ExecuteUpgradeHeroAI` spends for them.

#### ⚠⚠ v1 hooked `THero.NewDay`'s day-1 block and NEVER FIRED — and every static check passed

The obvious home for this is the confiscation block itself, gated on `map[+0x174] == 1`. It verified
clean, disassembled correctly, round-tripped `--undo`, and did nothing. The poller showed the map
loading with `map[+0x174] == 1`, every leader at `[+0x50] == 0`, and — at the sample immediately
before `ValidateHeroUpgrade` ran (XP still exactly 170, i.e. pre-award) — the cache already reading
**8, not 7**. All three guards passed on those values. `TPlayerControl.NewDay+0x27 @0x55754DCB` is
the only incrementer of the counter and `TAoWHSMap.Create+0x32E` the only other writer, so the gate
value was right; whatever dispatches per-unit `NewDay` simply does not reach heroes on the first day.
Not chased further — `NewTurn` is provably on the path (the same poller watched its XP award move
Grozt 170 → 172 and the other three leaders 45 → 47).

⭐⭐ **Three static guards all passing is not evidence the code ran. Only an execution trace is.**
This is the same lesson as the dead-VMT-slot gate in `02-abilities-modded.md`, reached a different
way, and it cost a full build-and-test cycle. ⭐ The instrument that settled it needs no debugger:
`re_tools/live_ui.py`'s `Mem` class plus a `Module32First` walk gives the runtime base of
`AoWEPACK.dpl`, after which any global or object field is readable from a running game — including
verifying that the **loaded** image carries the patched bytes.

**In-game checklist:**
1. **Launch `AoWz.exe` and reach the main menu** — proves the DLL still loads.
2. Start a game on a map whose leader was authored above level 1 with points unspent (the editor's
   Leader Properties shows the count, e.g. "Skill Points 44/90").
3. On that leader's **first turn** the level-up dialog must appear, offering the full unspent count.
4. Assign them; confirm the stats stick and the hero card reads the authored level, **not** one lower.
   One low means `ValidateHeroUpgrade` did not restore the cache and guard 2's premise is wrong.
5. **Decline** the dialog on another hero: it must be offered again next turn, and the points must
   still be there.
6. Spend everything on a third hero: the prompt must **stop** appearing.
7. A hero with 0 unspent points must never be prompted; a level-1 hero must never be prompted.
8. Save and reload; the level and the remaining points must survive.
9. Watch an **AI** leader — it should arrive already upgraded rather than sitting on unspent points.

#### `User/Ziggurat Heroes.ahl` — the hero library format

Same container family as `.pfs` (`re_tools/pfs.py`): `<u8 n>[<u32 wide_count>](u8 key,u8 off)*
(u32 key,u32 off)* <payload>`, offsets relative to the **end of that directory**. No magic, no CRC —
never stamp one.

```
0x0000  01 (00,00)                            outer: 1 small entry, key 0, payload @0x0003
0x0003  03 (0x14,0x00)(0x15,0x10)(0x01,0x14)  THeroLibrary body, payload @0x000A
0x000A  tag 0x14 = Pascal string "Ziggurat Heroes"
0x001A  tag 0x15 = 0x36 = 54   <-- NEXT-UNIQUE-ID COUNTER, *not* a hero count
0x001E  tag 0x01 = child list: 0x82 -> 2 small + u32 48 wide = 50 children, payload @0x01A7
```

Tag `0x01` is the **last** field of the library body, so growing the child list moves nothing above
it: 423-byte header + 8197 bytes of records = 8620 (pristine). Each child is
`<u32 ClassID = 0x00020230 (THero)><directory><payload>`, ids 0..49.

Hero tag → `THero` field offset, from `THero.ReadWrite @0x55788880`:

| tag | field | | tag | field |
|---|---|---|---|---|
| `0x08` | `+0x44` hero-resource index | | `0x16` | `+0x4C` **level cache**, 1 B |
| `0x0A`/`0x0B` | `+0x60`/`+0x64` name / nickname | | `0x18` | `+0x48` **experience**, 4 B |
| `0x10`..`0x15` | `+0x6A`..`+0x6F` ATK DEF DAM HP MOV RES | | `0x27` | `+0x50` skill-point write-off |
| `0x23`/`0x26` | library id / library name | | `0x24`/`0x25` | inventory / items |

Tags `0x10`..`0x15` are **purchased deltas**, one signed byte each — the live stat is
`chassis + delta + item + ability` (`GetInherentAttack @0x55788354`). An **absent tag means zero**,
so raising a stat on a hero that has none inserts one (`0x10` present in 28 of 50, `0x13` in 33).
Abilities come from `TAbilityOwner.ReadWrite @0x5574F318`: tag `0x02` bit count, `0x03` bitset
(LSB-first, bit index **is** the ability id), `0x31` the `TIntegerList` of ids owning a data
sub-record, and per-ability sub-records at `tag = id + 0x32` with the level at inner tag `0x0A`.

The chassis is `HERORES.PFS` at the index in tag `0x08` — `THeroResourceList.GetHeroResource
@0x5578A0FC` indexes the list by **position**, and HERORES ids are *not* contiguous (0..11, 18..29,
36..47, 54, 55), so position ≠ id above 11. Every hero in this library uses 0..11, where they
coincide. Six heroes carry no tag `0x08` at all; `THero.Create` leaves `[hero+0x44]` at 0, so their
chassis is index 0, "Human".

⚠ **Never re-derive a record directory — append only.** The engine's writer picks entry widths and
order by nothing recoverable from the data (`build_item_hpmv_data.py` proved this on `Zig.ail`).
Copy every existing `(key, offset)` verbatim, append new entries at the payload tail, bump only the
child-list offsets. Because offsets are relative to the directory end, appending moves no existing
field byte.

⚠⚠ **The game and the editor rewrite this file, and there is no dirty-flag gate.**
`THeroLibraryManager.WriteUserLibraries @0x5578ACAC` loops `GetLibrary(1..n-1)` →
`THeroLibrary.SaveToFile @0x5578A91C` unconditionally (`0x5578ACE0`–`0x5578AD24`). Two consequences:

- Anything running when a data edit is applied overwrites it on exit — kill the binaries first.
- **A recorded md5 for this file goes stale the first time the game is played**, because the engine
  re-serialises in its own directory layout. That is not corruption: `build_heroskill_spend.py`
  still reports `state: installed` if the *values* survived. But `--undo` would then produce a file
  that is not byte-identical to `backups\Ziggurat Heroes.ahl.pre-heroskill`, and if a rewrite moves
  an appended tag off the payload tail, `--undo` refuses outright rather than writing (verified —
  `"tag 0xNN sits at or past tag 0x10 -- refusing to remove"`). Compare by *values*, not by md5,
  once the file has seen a play session.

⚠ **Unmeasured:** *when* `WriteUserLibraries` fires (exit only? every save? only after the library
editor?), and whether `SaveToFile`'s output happens to match what the script writes byte for byte.
Either measurement would settle the paragraph above; neither has been taken.

#### What was applied

All 50 heroes shipped with unspent skill points — 589 in total, up to 26 on one hero, so a recruit
arrived with free level-ups nobody earned and the engine nagged
(`AoWE.NotAllSkillPointsAssignedRStr`). Per hero: `drop = left // 10`, `newLevel = max(1, level - drop)`
written to **both** tag `0x16` and tag `0x18`, and the residue `rem = left - 10*drop` spent on HP
(2/pt) and ATK (3/pt) by "alternate HP/ATK" — maximise spend, then minimise `|hp - atk|`, ties toward
HP:

```
rem 1 -> -        rem 4 -> HP+2        rem 7 -> HP+2 ATK+1
rem 2 -> HP+1     rem 5 -> HP+1 ATK+1  rem 8 -> HP+1 ATK+2
rem 3 -> ATK+1    rem 6 -> ATK+2       rem 9 -> HP+3 ATK+1
```

Result: **589 unspent → 3.** 47 heroes end on 0, and Acara the Spider / Atam the Righteous / Gorthak
the Black end on 1 because their `rem` was 1 and the cheapest stat costs 2. Levels drop by 0–2, 39
levels in total; **seven** heroes drop two (Borak 3→1, Forok 3→1, Danto 5→3, Esmeralda 5→3, Khabar
5→3, Ham Binger 6→4, Zodar 4→2) and four land on level 1 (Borak, Forok, plus Atam and Katar from 2).
The floor of 1 is reached but never has to truncate — nothing would have gone below it.
14 records gained a stat tag (5 × `0x10`, 9 × `0x13`), so the file is 8620 → 8662
bytes. Worst case after the edit is ATK 10/40 and HP 29/100 — nowhere near a cap.
`Ziggurat release/User/` got the same bytes; `User/Special Heroes.ahl`, `Release/HEROES.PFS` and
`Ziggurat upload/` were deliberately not touched.

---

## 6. Excess ATK → minimum-damage bonus (vanilla mechanism, RE only)

**Status: pure analysis, nothing applied.** The question: is there a special bonus for a huge ATK
excess over the target's DEF? **Yes — but it is a damage bonus, not a hit-chance bonus, and nothing
on screen shows it.** Hit chance is hard-clamped at 90% and stops improving at `d = +8` (live scale).
The same `d` keeps feeding the damage roll, raising the *minimum* damage a landed blow can deal — at
large `d` the low rolls stop existing entirely. The AI models this correctly; the player is shown
nothing. (Mechanism decoded in §1; this section covers the excess-ATK regime specifically.)

### The tables, corrected to the live 5 pp / ±8 scale

The identity in §3 (`T_live(d_live=2·d_old) ≡ T_old(d_old)`, since the live formula is `T=10−d_live`
with `d_live` on the doubled stat scale, exactly equal to the pre-conversion `T=10−2·d_old`) means the
original per-`d` tables are byte-for-byte reusable — only the `d`-axis label doubles. Presented here
already relabelled to the live scale.

**Max damage 5** (median unit in this install is damage 3, mean 3.18):

| d (live scale) | T | hit% | E[dmg] | min dmg on a hit | P(rolled == max) |
|---:|---:|---:|---:|---:|---:|
| −10 | 20 | 10% | 0.50 | **5** | 10% |
| −8 | 18 | 10% | 0.50 | **5** | 10% |
| −6 | 16 | 20% | 0.70 | 1 | 10% |
| 0 | 10 | 50% | 1.70 | 1 | 15% |
| +6 | 4 | 80% | 2.50 | 1 | 15% |
| **+8** | 2 | **90%** | 2.90 | 1 | 20% |
| +10 | 0 | 90% | 3.00 | 1 | 20% |
| +12 | −2 | 90% | 3.15 | 2 | 20% |
| +18 | −8 | 90% | 3.50 | 3 | 25% |
| +20 | −10 | 90% | 3.55 | 3 | 25% |
| +30 | −20 | 90% | 3.80 | 3 | 30% |
| +40 | −30 | 90% | 4.00 | 4 | 40% |
| +60 | −50 | 90% | 4.10 | 4 | 50% |
| +120 | −110 | 90% | 4.50 | **5** | 90% |

Hit chance is frozen from `d=+8` onward; expected damage still climbs **55%** further (2.90→4.50). At
`d=+40` a 5-damage strike lands only 0 (10%), 4 (50%) or 5 (40%) — rolls of 1, 2 and 3 have been
squeezed out of existence entirely.

**Max damage 10:**

| d (live) | hit% | E[dmg] | min dmg on a hit |
|---:|---:|---:|---:|
| 0 | 50% | 3.00 | 1 |
| +8 | 90% | 5.20 | 1 |
| +10 | 90% | 5.80 | 2 |
| +12 | 90% | 6.00 | 3 |
| +16 | 90% | 6.50 | 4 |
| +20 | 90% | 6.80 | 5 |
| +30 | 90% | 7.40 | 6 |
| +40 | 90% | 7.75 | 7 |
| +60 | 90% | 8.10 | 8 |

**The effect scales with the damage rating, and is exactly ZERO at damage 1** — E[dmg] going
`d=+8→+40`:

| max damage | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 |
|---|---|---|---|---|---|---|---|---|---|
| at d=+8 | 0.90 | 1.40 | 1.90 | 2.35 | 2.90 | 3.30 | 4.25 | 5.20 | 6.15 |
| at d=+40 | 0.90 | 1.80 | 2.50 | 3.20 | 4.00 | 4.70 | 6.25 | 7.75 | 9.25 |
| gain | **+0%** | +29% | +32% | +36% | +38% | +42% | +47% | +49% | +50% |

A 1-damage unit gets **nothing** from excess attack past `d=+8` — the formula's `(M−1)` factor is
zero, so every landed blow is 1 regardless. Excess ATK is worth roughly nothing on chaff and a great
deal on high-damage units.

### The mirror case: `d ≤ −8` — every landed blow is maximum damage

Because `R≥18` is tested before `T` is even computed, the auto-max branch is independent of the stat
gap. At `d≤−8` no middle roll survives, so a hopelessly outmatched attacker connects exactly **10%**
of the time, and **every connection deals full damage.** Further negative difference has zero further
effect. ⚠ Qualification: what the target actually *takes* is filtered downstream by
`TCombatObject.ExecuteDamageRole` (0 without rolling if fully immune; halved if fully Protected; and
on this install, `neg`'d for fire-affinity units by the fire-heals-fire cave `0x5580DA20`) — the
unqualified "10% of blows for full damage" holds exactly only at the bare call sites, in practice
`AoWTCPCK.dpl`'s city-wall damage.

### Which differences are actually reachable

The operative caps are engine clamps, not the data, and Ziggurat widened all of them — **now doubled
again by the 5% conversion.** Current live ceilings (byte-verified, §3/§5): `TUnit.GetAttack` **40**
(vanilla 10), `TUnit.GetDefense`/`GetResistance` **60** (vanilla 10), `THero.GetAttack`/`GetDefense`/
`GetResistance` **40** (vanilla 10). Floors stay at Ziggurat's **0** (vanilla floored DEF at 1) — this
is what makes a city wall's hard-coded **DEF 0** (`TCombatWall.GetDefense`/`TWallUnit.GetDefense` are
both `xor eax,eax`) meaningful: any attacker versus a wall sits at `d` = its entire attack value, the
single most common high-`d` matchup in normal play.

⚠ **Open item, not re-derived for this merge.** The pre-conversion doc quoted a "max possible
ATK−DEF" of **+30 (+38 with post-clamp melee bonuses)** using the *pre-5%-conversion* Ziggurat clamps
(ATK ceiling 20, hero ATK ceiling 30). With the ceilings now at 40 (both unit and hero, tied by the
Set==Get reconciliation) and the post-clamp bonuses (Charge, alignment/Champion, Monster Slaying) also
roughly doubled by the conversion, the current maximum is higher than 40+16≈56 but has not been
recomputed exactly in this corpus — treat any precise figure as unverified until re-derived.
**Ranged attacks use a completely different table** (`TRangedAttackAbility.GetAttackRA @0x5576E65C`,
a per-ability constant, not the unit card's ATK) and never share a melee `d` figure.

### Who sees the effect: the AI does, the player does not

**The AI models it accurately.** `AoWE.DMDCtoDV @0x55725E30` is a closed-form analytic expectation of
the real roll — same `T = 10−d`, same span, same `(M−1)` slope, with a dedicated `T<0` arm
(`0x55725E6C`) that explicitly models the compression regime, tracking real expected damage to within
~0.4% mean error for `d≥+8` (its one blind spot is the *hopeless* end: for `d≤−9` it returns `5×M`
where the truth is `10×M`, a flat 2× under-valuation, because it drops the auto-max branch). It feeds
every AI scoring path: `StrikeDV`, `StatisticsToLimitedDV`/`StatisticsToDV`, both halves of the
two-copy melee round, `GetTargetCVDV`, auto-resolve command scoring (`DVtoDEV`), and the **tactical**
AI in `AoWTCPCK.dpl` (`AoWTC.TCAI.tcDVtoDEV`).

**The player sees nothing.** `AoW.exe` imports exactly one symbol from the whole DV/predictor family
(a morale label); the info card writes only raw Attack/Damage and the tooltips actively mislead
("Attack is the ability of a unit to hit a target with a melee strike" — framed as pure accuracy). No
hit-percentage or expected-damage readout exists anywhere in the UI. **One genuinely linear model does
over-value raw attack**: `TStrikeAbility.GetOffensiveStrength` = `attack × min(damage,10 [live: 30]) ×
swings / 2`, no hit cap, no roll — feeds AI production/recruitment priority, not per-strike scoring.

### Live-vs-vanilla byte state of the roll itself

The maths is stock; only two live differences exist, neither behavioural: the RNG call at
`0x55725EBD..C0` is redirected through the combat-log's transparent logging cave (`0x558114E0`, calls
the real `System.@RandInt`, stores EAX unchanged); and `HitRole`/`HitRoleProbability`'s ×5 companion is
`imul eax,eax,5` live vs `lea eax,[eax+eax*4]` pristine (same value, same length — owned by
`build_hitslope5.py`, see §3). `DMDCtoDV`, `DMmaxDCtoDV`, `StatisticsToDV`, `StatisticsToLimitedDV`,
`DVtoDEV`, `TCombatObject.ExecuteDamageRole`/`...Ex` are all byte-identical to pristine.

### Other traps found while establishing the negatives (still true)

No lookup table is indexed by a stat difference anywhere in any of the four binaries; no strike count
scales with attack (melee is a flat 2/side, +1 for Extra Strike `0x73`; Round Attack adds
`Random(2)+1` extra targets); no damage multiplier and no overkill (`ExecuteDamage` asserts
`0 ≤ damage ≤ 0x31` [live: raised with the assert bump in §4] and clamps to remaining HP); an
instant-kill mechanic exists (`TInvokeDeathCA.Execute` sets damage = target's current HP) but is gated
by an ordinary 90%-capped `HitRole` pair, not gap-based; a second independent
`clamp(50+10Δ,10,90)` lives at `TEnchantment.DispelChance` and never touches `HitRole` (§3); every
named ability modifies ATK/DEF/damage *inputs*, never the roll distribution. ⚠ **Possible vanilla bug,
not investigated**: `TMeleeRound.CreateStrikeCA` computes strike attack as an unfloored 8-bit add
(`(byte)(GetAttack()+strikeMod)`), and the live invisibility cave does an unguarded `sub bl,1` — a
sufficiently negative modifier on a 0-attack unit could wrap to a huge positive attack. Worth a look if
a weak unit is ever seen hitting like a dragon.

---

## 7. Strategic map damage — storms, grounds, fire, vortex, quake, poison

**Status: vanilla mechanism; ATK and DAM sides doubled by the two passes in §3/§4.** Every strategic
damage source funnels through **`AoWE.TAbstractUnit.ExecuteDamageRole @0x55781AC4`**, wrapping the
same core roll (§1) that resolves weapon strikes. Seven engine callers plus one Ziggurat cave.

```
AoWE.TAbstractUnit.ExecuteDamageRole @0x55781AC4
    (EAX = unit, EDX = attack, ECX = damage, [ebp+8] = damage-type set)

    si = types & ~GetImmunityTypes(vmt+0xEC)
    if si == 0                                 -> return 0     ; fully immune, NO ROLL
    diff = attack - GetDefense(vmt+0xC4)                       ; <- DEFENCE, not Resistance
    result = AoWE.ExecuteDamageRole(damage, diff)              ; the shared combat roll, §1
    if (types & ~GetProtectionTypes(vmt+0xF0) & si) == 0       ; protected vs everything left
        result = (result+1) >> 1                                ; halve, round-half-toward-zero
    return result
```

⚠ **This rolls against Defence (`vmt+0xC4`), not Resistance (`vmt+0xCC`)** — resolved slot-by-slot
against `TAbstractUnit`'s VMT `0x55710740`. This is the aliasing trap CLAUDE.md warns about: the
**combat** wrapper (`TCombatObject.ExecuteDamageRole`, §1) uses `vmt+0x70`/`+0x74` on a completely
different class hierarchy — never carry an offset across the two.

⚠ **The live file hooks this function's first instruction**: `0x55781AC4` is `jmp 0x5580DA20`, the
fire-heals-fire cave, re-entering at `0x5580DA61` to `neg` the result for fire-affinity units. Anything
hooking here must preserve that.

### The complete caller census

| source | function | attack | damage | type |
|---|---|---|---|---|
| Storms | `TAbstractUnit.ExecuteStormDamage @0x55780668` | per-storm | per-storm | per-storm |
| Map fire | `TArmy.TriggerFireDamage @0x55790110` | **12** (fixed 2026-08-26, §4) | **6** | `dtFire` |
| Vortex | `TVortexTE.Process @0x557A13CC` | 8 (pre-doubling; not independently re-verified post-doubling — see note below) | variable (EBX) | pushed |
| Town quake | `TTownQuake.TriggerArmyDamage` | 7 (pre-doubling figure) | 5 (pre-doubling figure) | `dtPhysical` |
| Poison plant | `TPoisonPlant.TriggerArmyDamage` | 6 (pre-doubling figure) | 2 (pre-doubling figure) | `dtPoison` |
| Holy ground | `THolyGround.TriggerArmyDamage @0x557C7E18` | 6 (pre-doubling figure) | 4 (pre-doubling figure) | `dtHoly` |
| Unholy ground | `TUnHolyGround.TriggerArmyDamage @0x557C8FA4` | 6 (pre-doubling figure) | 4 (pre-doubling figure) | `dtDeath` |
| *(Ziggurat)* | fire-heals-fire cave | — | — | — |

⚠ **Open item.** The ATK sides above (except map fire) are 5%-conversion stage-6 addresses and are
confirmed doubled (Ice/Lightning/Death/Divine/Fire Storm and Pestilence, Map fire, Vortex, Town quake,
Poison plant, Holy/Unholy ground — 12 sites, addresses in §3's stage-6 table). The DAM sides are
covered by the DAM/HP pass's stage-3 count ("hazards ×7, storms ×6" among its 85 sites) but **no
per-address table for the non-storm hazard DAM immediates exists in this corpus** — only Map Fire's
was individually re-derived (via the dead-code defect investigation, §4). The values shown as
"pre-doubling figure" above are this doc's 2026-08-18 measurement, doubled arithmetically for display
but **not independently byte-verified post-doubling** the way Map Fire was. Byte-diff Town Quake,
Poison Plant and the two Grounds' damage immediates before quoting them as fact.

**Only two sources also apply status effects** — callers of `TAbstractUnit.ExecuteDamageEffects
@0x55781E28` are exactly `ExecuteStormDamage` and `TPoisonPlant.TriggerArmyDamage`. Grounds, map fire,
vortex and quake deal typed damage only, no debuff (holy/unholy ground does not curse you, despite the
tempting assumption). Every caller clamps to the target's remaining HP first.

### `TDamageType` — the enum (RTTI-derived, authoritative for every 16-bit type mask in the engine)

| bit | value | name | bit | value | name |
|---|---|---|---|---|---|
| 0 | `0x001` | `dtFire` | 5 | `0x020` | `dtDeath` |
| 1 | `0x002` | `dtCold` | 6 | `0x040` | `dtHoly` |
| 2 | `0x004` | `dtLightning` | 7 | `0x080` | `dtPhysical` |
| 3 | `0x008` | `dtMagic` | 8 | `0x100` | `dtWall` |
| 4 | `0x010` | `dtPoison` | 9 | `0x200` | `dtNone` |

Recovered from Delphi RTTI member names (consecutive ShortStrings, recoverable from any build) — RTTI
enum names beat string search. Consistent with the melee strike-source table (Fire `0xE`, Cold `0xF`,
Lightning `0x10`, Magic `0x14`/EnchantedWeapon `0x9A`, Poison `0x11`, Death `0x12`, Holy `0x13`,
Physical default).

### Storms — index, type, strength

`TArmy.IncommingStorm @0x557904B4` → `ExecuteStormDamage` per unit. **Type** is a **byte** array of
enum ordinals (not a bitmask), `StormDamageType 0x558E8330`: live bytes `09 00 05 06 01 02 04` (index
7 padding; storms are 0..6). **Strength** is a 7-entry jump table at `0x5578072E`:

| idx | storm | attack/damage (pre-doubling) | type |
|---|---|---|---|
| 0 | Blast Storm | **0 / 0** | `dtNone` — deals **no unit damage** through this path |
| 1 | Fire Storm | 8 / 5 | `dtFire` |
| 2 | Death Storm | 8 / 4 | `dtDeath` |
| 3 | Divine Storm | 8 / 5 | `dtHoly` |
| 4 | Ice Storm | 8 / 5 | `dtCold` |
| 5 | Lightning Storm | 8 / 6 | `dtLightning` |
| 6 | Pestilence | 7 / 1 | `dtPoison` |

Attack sides confirmed doubled (stage 6, §3: Ice/Lightning/Death/Divine/Fire 8→16, Pestilence 7→14).
Damage sides doubled per the DAM/HP pass's "storms ×6" count but not individually byte-re-verified
here (same caveat as above). Two tests before the switch (`GetAbilityEnabled(0x17)`,
`GetMoveTypes&2`) gate only the **terrain bonus** (×4 base-strength for standing on the storm's own
terrain type, itself reduced from an earlier ×8 by a prior Ziggurat patch), not the damage itself —
both paths still reach the switch.

### The grounds — arrival hit AND per-turn tick are separate triggers

`THolyGround`/`TUnHolyGround` carry two independent entry points into the same `TriggerArmyDamage`:
**`ArmyPlaced`** fires the instant an army is placed on the field (suppressed during load/map-edit via
`[AoWHSMap+0x3C]&2`); **`NewTurn`** fires again every turn the army remains, and ticks the ground's
duration. **Standing on holy ground costs you once on arrival and once per turn thereafter.**
`CanDoDamage` walks the army roster and skips units immune to the type, or whose alignment is `alsPureGood`
(holy ground does not burn good units; unholy is the mirror).

### Bearing on the slope conversion

All seven sources inherited the slope edit automatically — no extra code sites needed. They share a
shape that made the pre-conversion slope-only proposal awkward: a **fixed** attack rolled against a
**variable** Defence, so halving the slope alone (without doubling stats) would have compressed them
toward 50% rather than spreading them out. Under the **adopted** (both-doubled) plan the identity in
§3 holds here too — see the flagged contradiction in §11 about whether any pre/post comparison table
for hazards is safe to trust without re-deriving.

---

## 8. Missile trajectories & interception (manual tactical combat)

**Status: RE only, vanilla mechanism, nothing modded.** Formulas below are read off the binaries and
are correct as *maths*; the tuning claims (how often a shot is intercepted in practice) are derived,
not measured in play.

### Two ranged systems — know which one you are reading about

| | manual tactical combat | auto-resolve / "fast combat" |
|---|---|---|
| module | `AoWTCPCK.dpl` (`CombatTE`, `AoWTC`) | `AoWEPACK.dpl` |
| driver | `CombatTE.TCAbRangedTE` | `TRangedAttackAbility.fcExecuteCombatCommand @0x5576EB70` |
| flight path | real pixel-space arc, `AoWTC.MakeRangedPath @0x00427630` | none |
| intervening units | yes, probabilistic, retargets the shot | no |
| intervening terrain/obstacles | yes | no |
| walls | block the shot outright (probabilistic) | −2 ATK cover penalty only |
| cover arg passed to the CA | `0` always | `2` under a specific condition (below) |

Both ultimately call the same damage builder, `AoWEPACK!TRangedAttackAbility.CreateRangedAttackCA
@0x5576EAE4` (AoWTCPCK reaches it via import thunk `0x00402874`), so every ATK/DAM mod there affects
both — only target selection differs. `AoWTCPCK.dpl` preferred base `0x00400000`.

**The auto-resolve wall penalty, precisely.** `fcExecuteCombatCommand` calls `TFastCombat.
GetWallSituation(shooter,target)`; if it returns exactly 2 the cover arg becomes 2 (every other case
leaves it 0), and `CreateRangedAttackCA` does `ATK − cover`. `GetWallSituation` (`0x5574468C`) returns
0 if `GetWallInBetween` is false; 1 if the shooter's own `GetSide==1` (no penalty either way — the
caller only tests `==2`); else 2. **`GetWallInBetween` is not geometric** — it XORs the two *parties'*
"inside the walls" booleans (party index = the grid byte's high nibble), gated on the combat carrying
a wall object with `[wall+0x47]&1` clear. So the penalty needs the two *parties* on opposite sides of
the siege wall, nothing to do with the line between the individual units, and only bites the shooter
whose side isn't 1. Not clamped (`sub al` with no floor) — whether the consumer reads that byte signed
or unsigned was not checked.

### `AoWTC.MakeRangedPath @0x00427630` — the trajectory generator

```
MakeRangedPath(AL=shooterSide, DX=stepDivisor, CX=arcHeight,
               [ebp+8]=^TList obstructions OUT, [ebp+0xC]=^TXYZList path OUT,
               [ebp+0x10]=checkUnits:byte, [ebp+0x14/0x18]=target fudge,
               [ebp+0x1C/0x20]=targetHX/HY, [ebp+0x24/0x28]=sourceHY/HX)
```

**Step count**: `N = max(2, (|Δx|+|Δy|) × 100 / stepDivisor)`. `N+1` points emitted, `i=0..N`; hex→pixel
via `HXtoHP` (`px=x*32+8, py=y*32+(x&1)*16`), both endpoints get `+13` per axis to land on hex centre.
**X/Y** are plain linear interpolation — **the ground track is a straight line in screen space, not a
hex-walk**; which hexes it crosses is discovered afterwards by converting sample points back with
`HPtoHX`. **Z (the arc)** is a symmetric triangle `k` peaking mid-flight, fed through
`z = round(sqrt((k·N·arcHeight)/10)) − (10·N)/arcHeight` when `arcHeight≠0` — a **square root of a
triangle**, flatter over the apex than a real ballistic arc, and both integer divisions truncate so
short shots can sit at `z=0` throughout. **`z` is the whole anti-blocking mechanic** — a higher arc
literally flies over the obstruction check, which is why Archery lobs and Doom Gaze does not.

**Per-ability arc & speed** (`AoWTC.MakeAbilPath @0x004271EC`, tail-calls `MakeRangedPath`):

| style | arc | step div | abilities |
|---|---|---|---|
| flat, dense | 0 | 25 | Doom Gaze |
| high lob | 100 | 50 | Archery, Hurl Boulder, Hurl Stones |
| low arc | 20 | 50 | Fire Cannon, Fire Musket, Shoot Bolt, Throw Javelin, Lightning Bolts |
| no path at all | — | — | Flame Throwing, Call Flames, the five Breaths |
| per-spell | jump table | | Spell Casting (only ids 100/103/107/117/119 get a bespoke path) |

"No path at all" emits one point at the shooter's own hex and clears the obstruction list. ⚠ That
does **not** make those abilities unblockable in manual combat. Category 5 (Flame Throwing `0x1E`,
the five Breaths `0x56`–`0x5A`) has its own `NextStrike` case, which builds each strike's line with
`MakeRangedPath` (`0x40D65F`) and zeroes a blocked strike (`0x40F06F`).

**Breath and Flame Throwing aim each strike at its own hex** — `build_breath_line.py`, 🔨 APPLIED,
UNTESTED (2026-09-24), ported from Inioch's `patch_breath_line_v1.py` with his range-check defect
fixed.
- **The defect:** vanilla tests each of the 12 damaging strikes (of 20; strikes 12–19 are a cosmetic
  return sweep) along the fan's spray angle, not toward the hex it damages. Side walls ate strikes
  in corridors, and obstacles beyond the target cancelled hits.
- **The fix:** hook `0x40D5F1` (`6A 32 8B 45 FC`) → PIC cave `0x439400` (164 B, reservation to
  `0x4397FF`). For strikes 0–11 the cave centres the line on the damage hex, taken from the same
  tables vanilla uses at `0x40D671`–`0x40D72A` (`dHXtoHN` result bounded 1–60, table index 0–71),
  and zeroes the fan offsets. On any failed check it runs vanilla untouched.
- **Animation:** the damaging flames are now drawn to the hexes they hit; keeping the old fan would
  need a second path call.
- **Multiplayer:** no draw of its own. It changes how many synced `Random(100)` block rolls happen
  at `0x40EE5B`, identically on every peer. Auto-resolve has no obstruction step.
- Surgical `--undo`.

In-game checklist:
1. A dragon breathing down a one-hex corridor hits enemies in range along it.
2. An obstacle beyond the target no longer cancels hits.
3. An obstacle between breather and target still blocks.
4. Flame Throwing behaves the same way.
5. The flame animation looks acceptable.

### The obstruction scan

For each sample point (skipping the shooter's and target's own hex), fetch the field and query its
class and two raw bytes: `field+0x14` terrain id (`7` EarthWall or `0xF` Border/off-battlefield ⇒ hard
block; `8` RockWall is **not** checked, and mountain overlay is **not** checked — mountains do not
block missiles) and `field+0x15` overlay id (`8` Obstacle ⇒ blocks, range≥2 only).

At `r==1` (adjacent to the shooter): a unit blocks only if it is on the **opposite side** — **your own
adjacent units never block your archer; an adjacent enemy does.** At `r>1`: any unit, friend or foe,
blocks — **friendly fire is live from 2 hexes out.** A wall blocks unless breached (`wall[+0x20]≤0`);
at exactly `r==2` you get a free shot over your own wall if none of the shooter's six neighbours holds
a wall or door.

Each blocking hex becomes one interception-chance record (0..100): unit/obstacle weight
`w = 2×(dx+dy−z)` (how centrally the shot crosses, minus its height); wall `w = 200−3z` (record takes
`max`, not a sum); terrain `w = 100` absolute; adjacent-own-wall `w = 50` once. Codes 1/3 accumulate
across every sample in the same hex, then clamp to 100 — slower crossings and flatter arcs raise the
odds.

### The roll and retarget — `NextStrike @0x0040D290`

```
for each obstruction record: if RandInt(100) >= record.chance: continue   ; not intercepted
    truncate the visible flight path at the blocked point
    if blocker is a unit:  missile target := blocker      ; a REAL new victim
    else:                  missile target := nil          ; shot absorbed
    break
```

An intervening unit is **not** "the shot fizzles" — it becomes the genuine target of a normal
ranged-attack CA: full to-hit, full damage, full ability processing, XP to the shooter. `TCombatTerrain`
scenery is findable as a blocker but absorbs the shot with a nil target — trees/rocks eat arrows
without taking damage. **The AI prices this in**: `TCAI.EvalPath` folds each obstruction's
`EvalHex × chance/100` into its scoring, including for its own units, for a limited set of ability
"kinds".

### Does unit size matter? No — every unit occludes identically (verified)

`MakeRangedPath` touches the intervening unit in exactly five instructions and reads no unit stat —
the friend/foe check at `r==1` reads only side. **The occlusion chance is a property of the *missile*
(its arc height and step count), not the *occluder*.** A Fairy and a Red Dragon in the same hex are
equally likely to eat the arrow. Unit size (`TUnitResource+0x50`, `Unitres.pfs` tag `0x1C`, range 0–3
across 179 records: 21/81/52/25 units) is real data but is not wired into occlusion at all — the hard
part of ever adding it is the *fetch* (size is not reachable from a `TCombatUnit` VMT slot; `+0x90` is
`GetAlignment`, not size), not the weight-handler hook site.

### Levers, if this is ever modded

Cheapest to most invasive: re-tune an ability's arc/speed (two-byte `mov cx/dx,imm16` pairs in
`MakeAbilPath`, no cave); move an ability between styles (a plain cmp/sub ladder on ability id, e.g.
moving Lightning Bolts to "no path" makes it unblockable); change the interception weights (four
handlers at `0x00427C0B` unit / `0x00427CB0` wall / `0x00427CD1` terrain / `0x00427CDA` adjacent wall
— `imul eax,eax,2` at `0x00427CA1` is the single unit-blocking multiplier); add unit size as a term
(§ above — `[ebp-0x50]` already holds the `TTacticalCombatUnitHS`, the weight is computed 11
instructions later, so the hook is trivial, the fetch is the work); give manual combat the wall cover
penalty (the `push 0` at `0x0040C41D` and two preview sites are the `param_4` fast combat sets to `2`).

---

## 9. Facing, deferred retaliation, and Shield

**Current installed state** (from `build_shield.py`'s docstring, the authoritative record of what is
actually live — the design spec below describes an earlier iteration that has since been retuned):

- **Manual tactical combat**: a unit with Shield (ability `0xB0`) takes **−5** on the ATTACK number of
  every **ranged** blow arriving from its front hex or front-**left** hex — `(D−F) mod 6 ∈ {0,5}`
  where `D` = hex direction defender→attacker, `F` = the defender's facing byte (`HS+0x14`). Melee is
  **not** covered.
- **Auto-resolve**: no hexes, no facing — Shield instead applies the same −5 with a flat **75% per
  ranged shot**, unconditionally (no arc).
- **Deferred-retaliation facing (S1)** was built, confirmed working, then reverted the same day by
  choice — it existed to protect the melee arc Shield no longer has.

### F1–F4 — what the engine already gives you (feasibility, 2026-08-25)

The engine is already a **six-facing game**. `AoWE.TUnitHS+0x14` is one byte, legal range 0..6 (0=none,
1..6 the hex neighbours), default 3, serialised as property id 9, maintained by 40+ write sites,
rendered from six idle + six walking sprite sets per unit, and already has a hexagon radio-button group
in both editor forms. **Scope was narrowed by the user to tactical combat only (2026-08-26)** —
strategic per-stack facing (on `TArmyHS`) is fine as-is and is explicitly not a target.

| | verdict | the deciding fact |
|---|---|---|
| F1 — units have a facing | Feasible — already exists | Per-unit tactical facing is real (`TTacticalCombatUnitHS`, one object per unit); nothing to build |
| F2 — turning costs MP | Feasible with caveats | One VMT slot (`AoWTC.TCombatMoveControl+0x04 @0x00412AC8`) surcharges a finished path; the pathfinder still cannot *route* with facing in mind — costs become exact, the chosen route occasionally isn't cheapest. **Not built.** |
| F3 — rear attacks do extra damage | Feasible with caveats | Vanilla forcibly re-faces the melee defender to its attacker before the strike resolves — deleting/gating that is the mandatory precondition. Ranged is unaffected (never re-faces the victim). |
| F4 — Shield | Feasible, built | Id `0xB0` free, registration is the Drillmaster recipe verbatim, the damage-time query is one `GetAbilityEnabled` call, gated on F3's arc test |

Two corrections that matter if per-unit persistent (not just per-battle) facing is ever pursued:
**direction 0 does not survive a save** (`rwByte` skips zero bytes; a legacy fix-up rewrites it to 3 —
never use 0 as a sentinel), and **the spare values of `+0x14` are not spare** — vanilla melee
transiently writes 7/8/9 mid-turn and wraps on the next instruction; a bit-packing hook would corrupt
that.

**Hex geometry** lives in `HSEPack.dpl` (`HSEngine`, base `0x55600000`, not in Ghidra), a true 6-neighbour
odd-q hex grid. HN 1..6 clockwise from North; opposite = `d+3` wrapped, pairs (1,4)(2,5)(3,6).
`dHXtoHNfast` (thunk `0x557026AC`) is exact **only for adjacent hexes** — beyond adjacency it is a
sign-of-dx/dy quadrant classifier, **measured 29.5% wrong** over all deltas with `r≤12` at both
parities (worked example: defender (10,20), shooter (11,10) → returns 2/NE, true bearing is 1/N). The
exact route is `dHXtoRad` (thunk `0x5570266C`) + `dHXtoHN` (thunk `0x557026A4`, a spiral index) +
inline ring decomposition:

```
k      = hn - (3*r*(r-1) + 1)
sector = ((k + (r-1) div 2) div r) mod 6
dir    = sector + 1
```

Verified against all 60 entries of the engine's own `AoWTC.BreathDir @0x004673A8` table — reproduces
it exactly, so a Shield arc and a breath cone can never visually disagree. Both primitives are
`jmp [IAT]` into `HSEPack.dpl`, `ret 4`, preserve `EBX/ESI/EDI/EBP`.

**Handedness (proven, three independent legs, closed by in-game confirmation 2026-08-27).**
`HNtoXYTable @0x5562E024` decodes 1=(0,−1) 2=(+1,−1) 3=(+1,0) 4=(0,+1) 5=(−1,0) 6=(−1,−1): direction 1
is North, numbering runs **clockwise** in map coordinates, for both column parities. Corroborated by
AoWEPACK's own rotation tables (CW/CCW/opposite) and by `AoWTC.GetMeleeDirIndex`, whose result is
written straight into `HS+0x14`. **The user confirmed in-game that Shield protects front and
front-left only** — the only link static analysis could never settle (the sprite-set-index ↔ hex-
direction ↔ screen transform) is now proven end to end.

### S1 — deferred-retaliation facing: 🛑 REVERTED (2026-08-27, by choice, not a defect)

**The user tested `build_facing_retal.py` in-game on 2026-08-27 and confirmed it works.** All three
parts behaved as designed: a melee victim no longer spins when struck, it turns to face its attacker
just before its own retaliation swing, and touch victims no longer spin. **Reverted the same day —
not because of any defect.** Shield moved to ranged-only (below), which removed the reason the
defender's melee-time facing needed preserving; vanilla's on-being-hit turn was judged the more
familiar behaviour to leave in place. The script is kept on disk as a working, re-appliable technical
option and every site reads its original bytes again:

```
python "Modding Resources/build_scripts/build_facing_retal.py" --apply     # bring it back
```

**What it changed** (target `AoWTCPCK.dpl`, cave `0x00438200`, 51 bytes, inside a 191 KB free CODE run
starting `0x0043810D`):

| site | edit |
|---|---|
| `0x004092B9` | on-being-hit turn removed: `EB 65 90` (`jmp 0x00409320`) — the defender no longer re-faces on being struck |
| `0x00409BB3` | just-before-retaliation turn added: hook into the cave, computes attackerFacing+3 (mod 6) and re-faces the DEFENDER, then re-issues the displaced bytes |
| `0x00409F2A` | touch-target re-face removed: `E9 3D 01 00 00 90` (`jmp 0x0040A06C`) — a webbed/entangled/turn-undead victim no longer spins to face its toucher; the toucher itself (`0x00409E60`) still turns, deliberately kept as the mirror of melee's attacker turn |

⚠ **Do not NOP the skipped spans instead of jumping over them** — live `.reloc` entries sit inside both
(`0x004092D3`/`0x0040930E` in the melee span; four more in the touch span, two genuinely dead, two
still reachable through the Wall-Crushing guard block that remains live). A `.dpl` rebases, so the
loader rewrites those disp32s at load time; NOPping turns them into base-dependent junk instructions on
a different machine — silent and non-reproducible.

⚠ **Part c must jump to `0x0040A06C`, never `0x00409F9A`** — the latter is a Wall-Crushing branch head,
not a join point.

⚠ **`pushad`/`popad` in the retaliation cave is mandatory, not defensive style** — `ExecuteStrike`'s
prologue does not save `EBX/ESI/EDI`, but its caller `LastMove` does; a clobber would corrupt
`LastMove`'s saved registers. It is free (nothing is live at the hook).

**The dependency**: the retaliation cave reads the ATTACKER's facing byte and adds 3 — that is only
the defender→attacker direction because vanilla's *kept* attacker-facing write (`0x004092B4`) already
faced the attacker at its target one step earlier, and the two units are adjacent. If that write is
ever removed, the cave must recompute with `GetMeleeDirIndex` from the two hexes instead.

**⭐ The interaction re-applying S1 would remove.** With S1 reverted and Shield ranged-only, vanilla's
restored on-being-hit turn means **engaging a shielded unit in melee rotates its shield arc** — a
melee unit can be used to spin a target's front/front-left arc toward or away from friendly archers.
This is emergent from restoring vanilla, not designed, and is a real tactical lever worth judging on
purpose. Re-applying S1 removes it.

### S2 — Shield: current state, ✅ arc CONFIRMED / retune 🔨 UNTESTED

**The arc/handedness claim is ✅ CONFIRMED WORKING (2026-08-27)** — front and front-left, exactly.
**The current magnitude (−5), scope (ranged-only) and the auto-resolve 75% rule are 🔨 APPLIED,
UNTESTED** — they were built and byte-verified *after* the confirmed −4/melee+ranged configuration was
tested, so the tested configuration no longer exists. Ability id **`0xB0`** (not the `0xAC` either
feasibility doc originally proposed — that range was claimed by the four caster abilities;
`0xB0` is free in both the DLL scan and `Ability.pfs`), selection mask `0x03FF`.

**Why ranged-only.** User ruling 2026-08-27: vanilla **Parry (`0x71`)** already grants a melee defence
buff (`sub dword [ebx],8 @0x55767BE1`, −8 ATK, every bearing, §2) — a melee Shield would be
conceptually redundant with an ability the game already ships. Shield is the *ranged* counterpart to
Parry, meant to be bought separately. Ranged is discriminated **structurally, by which constructor
builds the blow, not by a flag**: melee goes through `CreateStrikeCA`, ranged (and breath, and Bolts)
goes through the single shared `TRangedAttackAbility.CreateRangedAttackCA @0x5576EAE4` — the one link
site serves *both* engines, told apart inside the cave by the victim's instance size (`0x68` tactical
vs `0x64` fast — **test exact equality for fast, not `>=`**, or the 75% roll would leak into manual
combat, which is reached from a UI message handler).

```
mode         gate            rule
manual       geometric       (D-F) mod 6 in {0,5}  -- front and front-left
auto-resolve probabilistic   RandInt(4) < 3  --  exactly 75.000% per shot (RandInt(4) is the top two seed bits)
```

−5 attack ≡ +5 defence bit-for-bit (the roll only ever sees `d = attack−defence`, formed by one
unclamped `sub` — the exact structural precedent is Parry). On the live 5 pp slope that is **−25
percentage points** of hit chance. The attack byte is read back **sign-extended**
(`movsx edx, byte [ebp+0x10]`), so underflow is not a hazard — `0xFB` reads as −5, never 251; the byte
is a private per-action stack slot, not a shared accumulator, and the whole chain on this install
subtracts at most ~12 from a non-negative base (slayers −5, invisibility −2/−5, Shield −5), so −128 is
unreachable.

**The 75% roll is per shot, not per attack action** — a 3-shot archer gets the shield on ~2.25 of 3
shots; manual combat calls the identical constructor per shot, so the two modes stay structurally
consistent. **The AI does not know about Shield in either mode** — target scoring runs through
`fcGetDamageValueEx`/`GetDamageValueEx` (VMT `+0xE4`/`+0xDC`), left vanilla on purpose (see
determinism, below): those slots ARE speculative (prefetch, scoring, the raze gate), and a draw there
would be the unsafe placement. Consequence: the auto-resolve AI keeps shooting shielded units as
though unshielded — an accepted, deliberate gap, not an oversight.

**Registration and cave siting, current addresses** (superseding the original design spec, which
named different sites since claimed by other features): registration hook `0x557BCECF` (**not**
`0x557BCF04` — that call is already `build_caster_cost.py`'s cave); cave page
`0x55823000`–`0x55823FFF`, this script's exclusive reservation (**not** `0x55822A00`, the original
spec's address — that collides with `build_shipyard_income.py`'s declared reservation); ranged link
`0x55812A7B`, the tail of `build_magebane.py`'s ranged cave (**zero byte slack** — the replacement
must be exactly 5 bytes, and `EAX`/`EDX` are live at the tail so the cave must restore them before its
final `jmp`). **Revert order: undo Shield before undoing Magebane** — Magebane's `--undo` zeroes its
whole cave, stranding Shield's cave with nothing calling it (silent, not a crash). Re-applying Magebane
is safe as of 2026-08-29 (its ranged tail is chain-aware and re-emits `jmp` to Shield's cave).

**`Release/Ability.pfs` record 186 now exists** (minted by an AoWDevEd round-trip, confirmed
2026-08-27). Tag 6 (level-up cost) = **8**, same as Parry — the cave's own `EXPAND_COST=6` is
decorative from here on, since the data file wins on every load. Tag 9 initially arrived as `0x0111`
(missing the `0x200` bit hero level-up needs alongside `0x100`) — `--apply` now writes `0x03FF` and
repairs the CRC, a real functional fix, not bookkeeping. No tag 5 — Shield has no info-card
description; adding one is a record-length change and needs the editor, never a byte-patching script.
`AoWz.exe`/`AoWzCompat.exe` each carry one byte (file offset `0x21DE40`) placing Shield in the **Melee**
level-up column — chosen while Shield was still melee-capable, now arguably the wrong column
("Resistances" holds the 17 mitigation abilities); no `--undo`, fix is to edit `ABILITY_CATS` in
`herodlg_cats.py` and re-run `build_herodlg_columns.py --apply`. ⚠ Editing `herodlg_cats.py` alone is
**not enough** — the 256-byte lookup table is *baked into both exes*; editing only the source dict
leaves the binaries holding the old table and Shield silently defaults to the Magic column, with every
verifier reporting green. (Found by QA 2026-08-27, after exactly that happened.)

### Determinism — why the auto-resolve draw is safe here, and only here

`call 0x55701080` → `VCL30.dpl!System.@RandInt` — the **identical primitive** the existing to-hit and
damage rolls already use, not an analogue (§1). `RandInt(4)` returns the top two bits of the advanced
seed, so `<3` is exactly 75.000%, no modulo bias — do not "fix" this by reaching for a `%` operator.

A conditionally-executed draw is the failure mode for MP lockstep; an unconditional-per-peer one is
not. Here the gate reads only replicated game state (victim non-nil, has ability `0xB0`, is a
fast-combat unit) — nothing local, nothing timer- or fog-dependent. Three facts close it:

- `System.RandSeed` is re-anchored once per combat by `TCombat.Execute @0x557282C8`
  (`RandSeed := AoWHSMap.Random($FFFFFF)`, one synchronised draw), then the whole battle runs off the
  raw stream deterministically — the canonical SYNC→RAW bridge this project already relies on
  elsewhere (`12-re-toolchain.md`).
- **The combat predictor draws no random numbers at all** — checked, not assumed: it never builds a
  `TCombatAction`, and no predictor address appears among the ~110–115 references to `@RandInt`
  or `TAoWHSMap.Random`. Three independent proofs: `CreateRangedAttackCA` has exactly two in-DLL
  callers, both auto-resolve execution bodies; the ability VMT slot that reaches them has exactly one
  call site in the whole DLL; `TStructure.CanRaze` instantiates a `TCombatPredictor`, never a
  `TFastCombat`, and its unit class fails the size guard anyway.
- **`@RandInt` does not advance `[map+0x230]`**, the value the out-of-sync comparator reads — this
  patch cannot trip a false desync alarm. (The flip side, stated plainly: because it doesn't touch
  that value, a hypothetical draw-count divergence here would go *undetected* rather than caught —
  not a new exposure, already true of every existing combat roll including vanilla's to-hit.)

### Retired — the melee links (recorded failed approach, machinery kept)

Applied 2026-08-26, byte-verified, **never validated in game**; reverted by `--undo` on 2026-08-27 as a
scope decision (Parry already covers melee), not a defect. Kept because the sites were expensive to
find, the register contracts are reusable by any future per-strike melee mod, and one note below is a
genuine failed approach worth not re-deriving.

- `0x55767EBA` / `0x55767F2A` — the two per-strike arms of `AoWE.TMeleeRound.CreateStrikeCA`
  (side-0 attacker-delivering / side-1 defender-retaliating). The displaced window in each is part of
  the ATTACK ARGUMENT push to `TStrikeCA.Generate`, not a save — a modifier is `sub byte [esp],N` on
  the already-pushed value, and **`pushad` must NOT be used here** because `[esp]` has to stay on the
  argument. Covered manual melee + retaliation and (silently, no-op, because the class guard rejects
  `TFastCombatUnit`) auto-resolve.
  ⚠ **Recorded failed approach — do not "rediscover" this as a cheap melee re-add.** The melee3 chain
  tail (`0x55812A2E`/`0x55812A09` depending on when read, inside `CalculateStrikes`) was the original
  design spec's proposed melee link, but `CalculateStrikes` runs **once per round**, before any facing
  change, so it structurally **cannot** express a per-strike arc. Never move a melee link back there.
- `0x55812A09` (moved from `0x558129EC` when `build_magebane.py` was re-tuned 2026-08-29 — **never
  hand-edit this address, it lives inside Magebane's cave and moves when Magebane does**) — the melee1
  chain tail, free-swing + touch abilities.
- ⚠ **Do not carry the melee links' "silent no-op in auto-resolve" over to the ranged link** — that
  stopped being true 2026-08-27. The ranged cave now tests the identical instance size *explicitly*
  and gives `0x64` a 75% roll instead of nothing. If the melee links are ever revived, decide
  deliberately whether they inherit the same treatment.

### The shared arc primitive and the class guard (reusable technique)

Both melee (adjacency-only) and the exact ranged formula (any distance) read hexes via
**`obj → [obj+0x60] = HS → [HS+0x04] = TMapField → X=byte[field+0x10], Y=byte[field+0x11]`** — never
via VMT `+0x74`/`+0x78` on the combat unit itself. ⚠ **On `TTacticalCombatUnit`, those VMT slots are
`GetResistance`/`GetDamage`** (`GetXhx`/`GetYhx` live at those offsets only on the HS classes) —
feeding Resistance and Damage into the direction maths shields the wrong arc **with no crash**, the
same offset-aliasing hazard CLAUDE.md warns about generally. Mandatory class guard first:
`mov ecx,[obj]; cmp dword [ecx-0x1C],0x68; jb bad` — `[obj+0x60]` is an HS only at instance size `0x68`
(`TTacticalCombatUnit`); `TFastCombatUnit` is `0x64` and its `+0x60` is **not** an HS. A wall or bare
combat object never reaches this far: `TCombatObject.GetAbilityEnabled` is `return 0`, filtering them
at the ability query, before geometry is ever touched.

### In-game checklist (untested items)

Shield from all six bearings in manual combat (front + front-left only, combat-log attack number 5
lower); ranged at long range due north (arc classification must track the true bearing, not a 90°
quadrant — this is exactly what the exact-primitive fix guards against); intercepted/absorbed shots
(no crash, nil victim handled); melee must now be **completely** unaffected by Shield (no reduction
from any melee bearing — the retired-links assertion should make this true by construction, but it
needs an in-game look); breath and flame-throwing now get Shield in both modes (confirm that's
wanted); auto-resolve the same matchup repeatedly with/without Shield on the defender and compare
losses statistically (75% is not visible in one battle); confirm the hero level-up column now reads
correctly (Melee, pending the "arguably wrong now" question above); one manual siege and one
auto-resolved battle to completion with no exception dialog; multiplayer — auto-resolve the identical
battle on two peers and confirm no desync (the only test that can falsify the determinism argument
above).

---

## 10. Lifesteal on round/defensive hits, and Enchanted Weapon for ranged (SPECULATIVE)

Two feasibility investigations from the same combat-cluster session (2026-07-08); **nothing built**.
Both build on pre-existing, undocumented Ziggurat caves found by diffing live vs pristine in the
`0x5580C1xx`–`0x5580C3xx` region: lifesteal heal (`cave_5580C150`, hooked from `TStrikeCA.Execute`,
heals the attacker **+2** on an on-hit melee, was vanilla +1 — since doubled to **+4** by the DAM/HP
pass, see §4) and Marksmanship-ranged (`cave_5580C240`, §3).

### Lifesteal misses round-attack and defensive (retaliation) hits

**Mechanism (vanilla).** Life Stealing = ability `0x76`. On a landed melee hit it heals the attacker,
driven by a flag bit `0x02` in the strike CA at `CA+0x18`, set **only** in
`TMeleeRound.CreateStrikeCA`'s **offensive** branch (`strike[0xC]==0`) and consumed in
`TStrikeCA.Execute`.

**Why it misses.** Round attack (`TRoundAttackAbility.fcExecuteCombatCommand`, byte-identical to
vanilla) builds every hit through the **global** `CreateStrikeCA @0x557665E4`, which never checks
ability `0x76` at all. Defensive/retaliation goes through `TMeleeRound.CreateStrikeCA`, but its
**defensive** branch (`strike[0xC]==1`) also omits the `0x76` check — only the offensive branch has
it. Both gaps are the *same* omission: the ability-0x76→flag line exists in exactly one of the three
strike-CA builders.

**Proposed patch (never built), Feasible ~90%/85% confidence:** hook the tail of the global
`CreateStrikeCA` (before it returns) with a 5-line cave testing `GetAbilityEnabled(0x76)` on the
attacker (`param_1`) and OR-ing `0x02` into `[CA+0x18]` — this reuses the existing heal cave
automatically, no consumer change needed. Mirror in `TMeleeRound.CreateStrikeCA`'s defensive branch,
testing the retaliator (`*(param_1+0x14)`). Both caves register-only + rel32, position-independent.
Open item: ability `0xA9` (the heal cave's second tier) was never fully identified in this
investigation — not required for the primary goal.

### Enchanted Weapon does nothing for mundane ranged attacks

**Mechanism (vanilla).** Enchanted Weapon = ability `0x9A`, `GetAttack`/`GetDamage` overrides both
**+2**/**+2** (live; doubled from vanilla's own values by stage 3, §3). Melee picks these up two ways
— `GetAbAttackAll`/`GetAbDamageAll` summing every enabled ability's stat contribution, and
`GetDamageTypes` OR-ing in the Magic bit `0x08` when the unit carries `0x14` or `0x9A`. **Ranged
computes attack, damage and damage-type completely independently** (`GetAttackRA` = a per-ability
constant + Marksmanship only; a separate ranged-ability VMT `+0x114` damage getter; `GetDamageTypesRA`
= a raw 2-byte ability field) — none of the three ever consults ability `0x9A`.

**The template is Marksmanship**, already doing exactly this pattern for its own id. The single
cleanest hook is `CreateRangedAttackCA @0x5576EAE4` — it has the shooter in hand and assembles all
three of attack, damage and damage-type in one place.

**Proposed patch (never built), Feasible ~85% confidence:** after the attack/damage reads, if
`shooter.GetAbilityEnabled(0x9A)`, add +2 to each (mirroring the melee constants) and OR `0x08` into
the damage-type word before it is stored into the CA. Alternative: extend the existing Marksmanship
cave (`0x5580C240`) plus the two ranged getters separately — rejected because those getters don't all
receive the unit object, making the single `CreateRangedAttackCA` hook preferable. Binary: AoWEPACK
(auto-resolve/fast); manual tactical ranged would need the equivalent AoWTCPCK build verified
separately (the type/stat model is shared, the driver is not). Open item: confirm whether the vanilla
ranged damage getter already folds in Marksmanship (relevant to whether "like Marksmanship" means
matching its ramp or adding on top).

### Superseded — unit size blocking missiles in auto-resolve

The 2026-07-08 verdict ("no line-of-sight code exists anywhere, blocking would be net-new") was derived
only from `AoWEPACK.dpl` and is true only of **auto-resolve**. Manual tactical combat already has the
complete probabilistic interception system described in §8, in `AoWTCPCK.dpl`, which the original
search simply never looked at (searching `AoWEPACK.dpl` alone for `Missile`/`LOS`/`Cover`/`Intercept`
finds nothing and is *not* strong negative evidence for the whole game — search every combat module).
"Make size matter to auto-resolve ranged" is downgraded from "build LOS from scratch" to "mirror the
existing wall/height cover term in `CreateRangedAttackCA`, keyed to the target" — a small cave, if ever
wanted — but the ID'd blocker is that unit size is **not reachable from a `TCombatObject`** at all (no
`GetUnitSize` VMT slot anywhere on that hierarchy; `+0x90` is `GetAlignment`), so the unsolved step is
the fetch, matching §8's finding for the tactical case exactly. The **"slaying" abilities** (Holy/
Unholy Champion, Monster Slaying) are keyed on **alignment** (`vmt+0x90`), not size — an earlier version
of this investigation had this backwards; corrected and reconfirmed against both VMT bases.

---

## 11. Where formulas saturate on the doubled scale

Ranges that were comfortable in vanilla or pre-conversion Ziggurat are now crossed by a single strong
stat, pinning results at their clamps and flattening whatever else was meant to matter.

- **The accuracy/damage-roll pin itself** moved from `d=±4` to `d=±8` (§1) — exactly proportional to
  the doubling, by the proven identity, so this alone is not a saturation *problem*, just the new
  reference point every other saturation claim in this file is measured against.
- **Touch abilities compound the slope change twice**, because success is the *product* of two
  clamped rolls (attacker ATK vs target DEF, then the ability's own `GetTouchAttack` vs target
  Resistance — §1's `Ex`-path note). Both rolls move toward their own 50% under a fixed differential,
  so the *product* moves toward 25% — a materially larger swing than any single-roll ability, and it
  hits hardest exactly on the touch abilities Ziggurat had already buffed (Web/Entangle/Possess,
  Invoke Death, Turn Undead). Quantifying this precisely on the *current* doubled-RES scale has not
  been redone in this corpus — the only numbers available (`01-combat-maths.md §3`) are
  computed on the pre-doubling-RES premise and are not safely relabelled the way §6's tables are
  (that relabelling worked because both sides of the roll double together; here only one side of the
  *first* roll and both sides of the *second* roll are in play, and the two rolls interact
  multiplicatively). **Open item**: re-derive the touch double-roll compression table against live
  doubled RES before relying on any specific percentage.
- **Excess-ATK minimum-damage saturation** (§6): past `d=+8` (current scale) accuracy is fully pinned
  and *only* the damage floor keeps climbing — at `d=+40` a max-5 strike can no longer roll below 4.
  This is the mechanism working as designed, not a defect, but it means high-ATK/high-DAM units gain
  disproportionately from every further point invested past the pin, while 1-damage chaff gains
  nothing at all past `d=+8` — a real design shift worth remembering when tuning any new ATK source.
- **The wall-pin identity, and a flagged internal contradiction.** Because doubling ATK/DEF/RES and
  halving the slope is a *proven perfect identity* (§3 — verified by enumeration, bit-identical hit
  chance and damage distribution across the whole −12..+12 range, and restated independently for the
  DAM/HP pass in §4), the **fraction** of matchups that pin at the 90%/10% caps should be *unchanged*
  by the conversion for any pair whose stats doubled together with the slope — including attacker vs a
  hard-coded-DEF-0 wall, where `d_new = 2·ATK_old = 2·d_old` exactly. **This file
  §4a/§4b report a large real drop** (wall-pin frequency 111/179→6/179; base-stat saturation
  13.4%→0.5%) and that doc's own header claims those sections "still stand" under the adopted
  (both-doubled) plan — but the specific before/after figures are only reachable if the *stat* side
  was held fixed while only the *slope* moved (a scenario the same document explicitly voided
  elsewhere, in §4c/§4g, for an identical reason). This reads as leftover analysis from the doc's own
  premise change mid-session, not a description of what shipped. **Flagged, not resolved** — the merge
  brief's correction table does not cover it, and inventing a fix risks being wrong in either
  direction. Treat §4a/§4b's specific numbers as describing a hypothetical slope-only build, not this
  install, until someone re-derives the wall-pin frequency directly against the live doubled data.
- **Reachable-range headroom is stale.** The pre-conversion "max ATK−DEF ≈ +30 (+38 with post-clamp
  bonuses)" figure (§6) used clamps that have since moved (unit ATK ceiling 20→40, hero ATK ceiling
  30→40) and bonuses that have since roughly doubled again. Nobody has re-run the full 32,041-ordered-
  pair sweep against the current data. The clamps themselves are solid (byte-verified, §3/§5); the
  *population* statistics built on top of them are not.

---

## 12. Known gaps in the doubling passes

- **Map fire, Burning, Decay, Turn-Undead-AI-heuristic damage** — all found and fixed 2026-08-26 (§4).
  The general lesson they share: a **(POWER, DAMAGE) pair** where POWER was in the 5% conversion's
  scope and DAMAGE, ten-to-twenty bytes later, was in nobody's manifest — so both scripts report a
  clean all-clear while the site sits half-converted. A coverage claim is only as good as the manifest
  it is derived from.
- **`TTurnUndeadAbility.GetTouchAttack` (ladder `0x5576B1F4`) — SETTLED 2026-09-03: it IS doubled.**
  The live bytes were read directly:

  ```
  5576B202  mov al, 0x12   ; 18   (level I)
  5576B205  mov al, 0x14   ; 20   (level II)
  5576B208  mov al, 0x16   ; 22   (level III)
  5576B20B  mov al, 0x18   ; 24   (level IV)
  5576B20E  mov al, 0x08   ;  8   (default)
  ```

  This matches the doubled-sources stage-5 table (§3) (9/10/11/12/4 → 18/20/22/24/8,
  applied 2026-08-20). The older claim that this ladder "still returns the vanilla 9/10/11/12" —
  which had propagated as far as the project's `CLAUDE.md` as its worked example of an unconverted
  gap — is **wrong**, and Turn Undead is therefore **not** floored against undead with RES ≥ 20.
  ⚠ The *rule* the stale example was illustrating still holds: wherever a stat is compared against a
  constant, byte-diff the site rather than assuming either state.
- **The melee1/melee3 alignment-bonus asymmetry (4 vs 5)** — §2. Real, byte-confirmed, unrelated to
  facing/Shield despite living on the same sites; not fixed here by design (recorded so it isn't
  mistaken for something either pass "should" have caught).
- **Touch double-roll compression** — not re-quantified on the live doubled scale (§11).
- **Storm/hazard DAM immediates** (Town Quake, Poison Plant, both Grounds) — doubled per the DAM/HP
  pass's own stage-3 count, but no individual address was re-derived for this merge the way Map Fire's
  was (§4). Byte-diff before quoting exact current values.
- **`HEROES.PFS`'s doubling (H6)** closed what the conversion manifest called "the one place
  where a stated decision and the installed state disagree" — recorded here so a future session does
  not re-open it as still-undecided; H6 (2026-08-24) settled it.

---

## Open items

- ~~Turn Undead `GetTouchAttack`~~ — **settled 2026-09-03, it is doubled (18/20/22/24/8). See §12.**
- Re-derive `01-combat-maths.md §4a/§4b`'s wall-pin and base-stat-saturation percentages
  directly against the current doubled data, or retire the old figures outright — see §11.
- Re-quantify the touch-ability double-roll compression table on the live doubled-RES scale — see §11.
- Byte-diff the non-map-fire strategic hazard DAM immediates (Town Quake, Poison Plant, Holy/Unholy
  Ground) individually — see §7, §12.
- Re-derive the current maximum reachable base ATK−DEF difference (both unit and hero) against the
  current 40/60/40 ceilings and the doubled post-clamp bonuses — see §6.
- Shield: in-game checklist in §9 (arc-from-all-bearings, ranged-at-long-range sector accuracy, melee
  now fully inert, auto-resolve 75% statistically, MP determinism on two peers).
- Facing: whether restoring vanilla's on-being-hit melee turn (by leaving S1 reverted) reads as
  intended once players can use it to spin a Shield unit's protected arc — see §9's "interaction"
  note. A design call, not a defect to chase.
- Shield's hero level-up column (currently Melee) probably wants moving now that the ability is
  ranged-only — an editor-category edit, not a script fix (§9).
- Lifesteal-on-round/defensive-hits and Enchanted-Weapon-for-ranged (§10) remain SPECULATIVE — nothing
  built, no acceptance criteria drafted.

## Failed approaches — do not retry

- **Doubling `MakeHitBlood` blood-spray band 3 (`0x5D→0x7F`)** on the theory that the raised
  `Invalid Damage Value` assert ceiling made 108–126 reachable. It doesn't — single-hit damage is
  bounded by the DAM stat (ceiling 60), so 15..107 already covers everything attainable. A true
  doubling would need a 5-byte `2D imm32` encoding where a 3-byte `83 E8 ib` fits today, displacing
  two short jumps. Left at `0x5D` by the author's ruling (§4).
- **Attributing `0x55725D9F`'s `imul eax,eax,5` re-encoding to an undocumented hand edit.** It is
  owned by `build_hitslope5.py`, written alongside the doubling-NOP at `0x55725D9D` (§3). Repeated in
  more than one older doc; corrected here.
- **Reading Parry's live penalty as −4 (imm8 `0x04` at `0x55767BE3`).** The current live byte is
  `0x08` (§2) — a stale pre-5%-conversion reading, not a live fact.
- **Treating the melee3 chain tail (`CalculateStrikes`, `0x55812A2E`/`0x55812A09`) as a viable
  per-strike hook for any facing-dependent melee rule.** It runs once per round, before any facing
  change (§9). This is exactly why the retired Shield melee links used the per-strike `CreateStrikeCA`
  arms instead.
- **Applying `Unitres.pfs`'s ATK/DEF/RES tag map (`0x0E/0x0F/0x13`) to `HERORES.PFS`.** That file's
  map is `0x0F/0x10/0x14`; `0x13` there is Movement. Doubles hero movement and silently leaves
  Resistance untouched (§3).
- **"Fixing" the two dead map-fire byte copies (`0x55790218`=6, `0x5579021D`=12) by restoring the
  `TriggerFireDamage` immunity-gate hook (`TRIG_ORIG`) to make that dead body live.** That reverts
  fire-heals-fire entirely. The correct fix (already applied) rewrites the *live* cave instead (§4).
- **Locating the 5% slope's seven sites by byte-pattern search for `add r,r` immediately followed by
  a ×5.** Returns 18 hits; 11 are decoys (skill-point prices, dispel mana, unrelated arithmetic) — see
  the address list in §3. Locate by absolute address only.
