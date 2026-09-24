# Abilities — modified

Changes to abilities that **already existed** in vanilla AoW1: Invisibility/True Seeing, Turn Undead,
Vision, the unit-enchantment/status/combat-boost value re-grade, the Webbed/Entangled stat-cache bug,
Panic, the Command family (Seduce/Charm/Dominate/Turn-Undead-as-Command), Dispel Magic, Lifesteal on
Round Attack, and Leadership. Brand-new abilities built from scratch (Path of Sand, etc.) belong in
**`03-abilities-added.md`**. The 5%/doubled-stat combat scale and the two-RNG rule are covered once,
in full, in `01-combat-maths.md`; this file states only the numbers each feature actually uses. Cave
ownership and the VMT/field catalogues live in `12-re-toolchain.md`.

## Status table

| feature | status | owning script | binary |
|---|---|---|---|
| Invisibility → attacker ATK penalty (True Vision negates) | 🔨 APPLIED, UNTESTED (2026-07-21; numbers retuned 2026-08-24) | `build_invis_penalty.py` (rewrites `build_trueseeing.py`'s caves in place) | AoWEPACK.dpl |
| Turn Undead damage = 0.5×level×casterRES | ✅ CONFIRMED WORKING (2026-07-16) | `build_turnundead_res.py` | AoWEPACK.dpl |
| Turn Undead roll 2 (stun/seize gate): attacker term swapped to casterRES×(4+level)/5 | ✅ CONFIRMED WORKING (2026-09-02, as part of the evil-command test) | `build_turnundead_resroll.py` | AoWEPACK.dpl |
| Turn Undead — Evil/Pure Evil casters seize the undead instead of damaging it | ✅ CONFIRMED WORKING (2026-09-02) | `build_turnundead_evilcommand.py` | AoWEPACK.dpl |
| Turn Undead — commanded-undead ankh overlay icon | ✅ CONFIRMED WORKING (2026-09-02) | `build_commandedundead_pfs.py` + a `ShowEx` cave in `build_turnundead_evilcommand.py` | Release/Ability.pfs + AoWEPACK.dpl |
| Vision — nine levels, +1 sight/level | ✅ CONFIRMED WORKING (2026-08-09) | `build_vision9.py` | AoWEPACK.dpl + Release/Ability.pfs |
| Unit enchantment / status / combat-boost re-grade (odd-value grades) | ✅ CONFIRMED WORKING (2026-08-24) | `build_buff_regrade.py` (+ `build_assassin.py` cave copies) | AoWEPACK.dpl |
| Webbed / Entangled DEF penalty silently not applying to units | ✅ CONFIRMED WORKING (2026-07-21) | `build_debuffcache.py` | AoWEPACK.dpl |
| Panic — blocks offensive melee, retaliation preserved | ✅ CONFIRMED WORKING (2026-09-13; 6th hook `meleemove` applied 2026-09-12) | `build_panic_nomelee.py` | AoWTCPCK.dpl + AoWEPACK.dpl |
| Panic — cleared by any damage that lands | 🔨 APPLIED, UNTESTED (2026-09-09) | `build_panic_cleardamage.py` | AoWEPACK.dpl |
| Command abilities (Seduce/Charm/Dominate) — cross-battle revert-on-controller-death nerf | SPECULATIVE | none built | AoWEPACK.dpl (proposed) |
| Dispel Magic — level cap III → V | 🔨 APPLIED, UNTESTED (2026-08-09) | `build_dispelmagic5.py` | AoWEPACK.dpl |
| Lifesteal on Round Attack (offensive: normal + round) | ✅ CONFIRMED WORKING (2026-07-08) | `build_lifesteal_roundattack.py` | AoWEPACK.dpl |
| Lifesteal — defensive/retaliation variant | SPECULATIVE (documented, `DEFENSIVE=False`, never applied) | `build_lifesteal_roundattack.py` (`DEFENSIVE` switch) | AoWEPACK.dpl |
| Leadership — 4 levels (I–IV) | ✅ CONFIRMED WORKING (2026-07-20; cost re-tuned 20→10/level same day) | `build_leadership4.py` | AoWEPACK.dpl |
| Leadership — aura-disable bug fix | ✅ CONFIRMED WORKING (2026-07-20) | `build_leadership_fix.py` | AoWEPACK.dpl |
| Leadership — aura instant-refresh on level-up | 🔨 APPLIED, UNTESTED (2026-07-20) | `build_leadership_aura.py` | AoWEPACK.dpl |
| Leadership IV grants the stack Fearless (Terror/Cause Fear immunity) | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_leadership_fearless.py` | AoWEPACK.dpl |
| Leadership buffs only the OTHER units in the party (+ split "own (+received)" card text) | 🔨 APPLIED, UNTESTED (2026-09-16) | `build_leadership_others.py` | AoWEPACK.dpl |
| Per-race probability gate on hero level-up ability offers | 🔨 APPLIED, UNTESTED (2026-09-09) — see Feature 1 below | `build_heroskill_race.py` + `heroskill_races.py` | `Ziggurat/AoWz.exe` + `Ziggurat/AoWzCompat.exe` |

---

## Invisibility → attacker ATK penalty, negated by True Seeing

**Status: 🔨 APPLIED, UNTESTED.** v2 written 2026-07-21; penalty values retuned 2026-08-24. Script
`build_invis_penalty.py` (no `--undo` — see Revert below). Binary `AoWEPACK.dpl`, backup
`AoWEPACK.dpl.pre-invispenalty` (a re-tune, not a revert path — see Revert).

**Current rule: target has Invisibility `0x36` AND attacker lacks True Vision `0x29` → −2 melee ATK /
−5 ranged ATK.** Attack only, no damage change, no floor clamp. At the live 5pp-per-point slope
(`01-combat-maths.md`) that is **−10pp hit chance melee, −25pp ranged**.

⚠ **The −1/−3 figures recorded in this project's earlier notes are stale.** Confirmed from the live
constants (`build_invis_penalty.py:110-112`): `MELEE_PENALTY = 2` (history: 2 → 1 → 2 again, restored
2026-08-24) and `RANGED_PENALTY = 5` (was 6 — vanilla 3, doubled to 6, then re-graded down to 5 the
same day, alongside the rest of the `Unit enchantment` re-grade below). Nobody has re-run the original
in-game test (attack a Shadow/Djinn/Air Elemental with an ordinary unit and read the combat-log ATK
and hit-chance line, then repeat with a True-Seeing unit) since the numbers moved, so the mechanism
itself is still **untested**, not just its constants.

### Ability IDs and scope

| ability | id | role | proof |
|---|---|---|---|
| True Vision ("True Seeing") | `0x29` | negates the penalty | `TAbstractUnit.TrueVisionRange @0x55780F80`; resourcestring `AoWE.TrueVisionRStr` |
| Invisibility | `0x36` | triggers the penalty | `TAbstractUnit.ConcealedOnMapF @0x55780524`; resourcestring `AoWE.InvisibilityRStr` |

**Scope is `0x36` only** (user decision, twice) — not the full `ConcealedOnMapF` semantics, which would
widen the trigger from 9 unit types to 68 (the Concealment *enchantment* `0xA2`, what the Concealment
spell actually grants, and terrain concealments `0x8A`–`0x91` are deliberately excluded).

### Vanilla context — invisibility has no combat effect at all

Exhaustive: every constant-id `call [reg+0xA8]` (combat `GetAbilityEnabled`) site in the vanilla DPL
was enumerated — 68 of them. The complete set of ability ids tactical combat ever tests is
`01 15 33 35 3B 3F 43 5E 60 61 6A 6B 6C 6F 70 71 73 74 76 77 80 81 84 92 93 A0 A1`. `0x36`, `0x29`,
`0x8A`–`0x91`, `0xA2` are all absent — inert markers in vanilla, structurally identical to the Dragon
marker `0x3F`. **This mod is the first combat consequence invisibility has ever had.**

Vanilla's actual payoff is strategic and narrow: `TArmy.UpdateConcealment @0x5578C98C` hides an army's
hotspot only if *every* unit in the stack is concealed (one escort breaks it); `TrueVisionRange
@0x55780F80` returns 1 for units *without* the ability (everyone detects invisibles at range 1, so True
Vision buys range, not detection); `TPlayerStructure.TrueVisionRange @0x55761060` returns 0 (cities and
towers never detect invisibles). That adjacency rule is *why* melee gets the smaller penalty and ranged
the larger one: in vanilla the adjacent attacker already sees you fine, so the distant shooter is the
one who should struggle.

### Injection sites

Melee has **two** tables (opportunity strikes only worked through one of them the first time this was
built); ranged has one. v2 only rewrote the three cave *bodies* — the v1 chain plumbing is untouched.

| path | function → cave | attacker | target | ATK slot | penalty |
|---|---|---|---|---|---|
| melee (round/opportunity/ability) | `CreateStrikeCA` → `cave_melee` @`0x5580E070` → exit @`0x5580E0D5` → **`cave_ts_melee` @`0x5580E370`** (46 B) | `EBP` | `ESI` | `BL` — absolute | −2 |
| melee (deliberate + retaliation) | `TMeleeRound.CalculateStrikes` → `cave_melee3` @`0x5580E120` → exit @`0x5580E183` → **`cave_ts_melee3` @`0x5580E3B0`** (46 B) | `ESI` | `EDI` | `dword [EBX]` — **DELTA** | −2 |
| ranged + breath (per shot) | hook @`0x5576EB34` → **`cave_ts_rng` @`0x5580E400`** (51 B) → `cave_rng` @`0x5580E190` | `ESI` | `[EBP-4]` | `[ESP+4]` after its own push — absolute | −5 |

⚠ **The trap — site 2's slot is a delta, not a value.** `dword [EBX]` is a modifier accumulator: the
base is fetched separately and the delta added (`call [edx+0x6C]; movsx eax,al; add eax,[ebx]`
@`0x55767CC7`, folded 8-bit in `TMeleeRound.CreateStrikeCA` @`0x55767EBA`). A floor clamp here would
wipe out Monster Slaying/Assassin instead of flooring the attack — **never clamp site 2.**

⚠ Ranged slot offsets differ by frame depth: at the hook `0x5576EB34` the attack sits at `[ESP]`
(pushed @`0x5576EB1D`); `cave_rng` reaches it as `[esp+8]` because of its own `push edi; push eax`;
`cave_ts_rng` reaches it as `[esp+4]` after one `push eax`. `cave_rng`'s own `add byte [esp],1` targets
*damage*, not attack — do not confuse the two slots.

### Why no clamp — the engine is signed end to end

Attack is a transient stack argument, never stored in the CA (only the rolled damage is, at `CA+0x10`,
so attack is never serialised or re-read). `TDamageCA.Generate @0x55729C46` does `movsx edx, byte
[ebp+0x10]` → `TCombatObject.ExecuteDamageRole @0x557269F0` does `movsx eax,al` on defence then a
32-bit signed `sub` → every downstream compare is signed. An underflowed `0xFE` reads back as −2, not
254 — there is no "wraps to always-hits" bug on this path, because that would need a `MOVZX` and there
is none. `hit% = clamp(50 + slope×(atk−def), 10, 90)` floors a hopeless margin at 10%; the only
`jle → return 0` guard is on *damage*, never attack.

Three vanilla precedents, all unclamped signed subtractions — this mod copies the idiom rather than
inventing one:

- **Parry (`0x71`) @`0x55767BE1`: `sub dword ptr [ebx], 8`** — at site 2, every strike. This is
  literally the mechanic being copied here: a defender's ability subtracts from the attacker's attack.
  `cave_ts_melee3` is that same block with `0x71`→`0x36`, and the True Vision clause added. (Vanilla
  Parry hooks site 2 *only* — it never applies to opportunity strikes or ranged; this feature covers
  all three deliberately.)
- Wall penalty @`0x5576EB1A`: `sub al, [ebp+8]`, = 2 iff `GetWallSituation()==2` (−2 ranged behind
  walls).
- Vertigo @`0x557BAC5C` / Poisoned @`0x557B9E68` return −2 from `GetAttack` (ability attack is a
  `ShortInt`).

⚠ **Do not port this to the damage slot** (`[esp+3]` / `dword[ebx+4]` / `[esp]`) — damage ≤ 0 hits the
hard `test/jle → 0` guard, so it means guaranteed zero, not a reduced hit.

### Prevalence in the installed data

⚠ The installed `.pfs` data is the Ziggurat mod, not vanilla (no vanilla copy exists on disk); binaries
are stock.

| | Invisibility `0x36` | True Vision `0x29` |
|---|---|---|
| unit types | 9 / 179 (5%) | 33 / 179 (18%) |
| items | Ring of Invisibility | Helm of Eyes, Ring of True Sight |
| named heroes | 0 / 50 | 6 / 50 |
| hero level-up cost | 20 pts | 12 pts |

Invisible units: Djinn (25), Leprechaun (97), Leshy (101), Shadow (151), Incarnate (152), Air Elemental
(224), Aether Barge (231), Fairy Dragon (271), + Human Charlatan (5) at gold medal. The counter is ~3×
more common and the cheaper hero pick — but heroes can also buy Invisibility (20 pts), so the trigger
isn't limited to those nine chassis.

### Where the penalty is visible

| surface | shows it? | why |
|---|---|---|
| combat log | yes | its tail hook already does `movsx byte [ebp+0x10]` → prints `A-2`, not 253 |
| melee-round DV preview | site 2 only | that delta also feeds per-strike CV via `0x55726038` → `TMeleeRound.CalculateDV @0x55767F58`; vanilla Parry behaves identically |
| unit info card | no | `TStrikeAbility.GetCombatInfo @0x55766F60` reads base stats (`vmt+0xC0/0xC8`) |
| AI targeting | no | `GetOffensiveStrength @0x55766BAC` reads the same base stats — the AI keeps attacking invisible units at full confidence and never values True Seeing |

### Revert / re-tune

No `--undo` exists. Manual surgical revert: restore the three injection sites — `cave_melee`'s exit
@`0x5580E0D5`, `cave_melee3`'s exit @`0x5580E183`, and the ranged hook @`0x5576EB34` — to whichever
prior state is wanted (pristine, or `build_trueseeing.py`'s v1 bonus bodies), and zero the three cave
bodies at `0x5580E370`/`0x5580E3B0`/`0x5580E400`. **Re-tuning the numbers does not need this**: edit
`MELEE_PENALTY`/`RANGED_PENALTY` and re-`--apply` — the script rewrites its own cave bodies in place
(verify-before-write accepts either the installed bytes or the new ones), which is how the 2026-08-24
retune was done with no backup involved. Caves resize when the constants change; the free-space assert
covers that.

### In-game checklist

1. Attack a Shadow/Djinn/Air Elemental with an ordinary unit; combat log reads 2 less melee ATK / 10pp
   less hit chance, or 5 less / 25pp less at range.
2. Repeat with a True-Seeing unit (Priest, Elf Cleric, Beholder…) — numbers unmodified.
3. Monster Slaying / Champions / Assassin bonuses still fire alongside the penalty (site 2 interaction).
4. Opportunity strikes and retaliations show the penalty too (both melee tables), not just deliberate
   attacks.

---

## Turn Undead

Three layered features, all in `AoWEPACK.dpl` only (ability logic is DLL-side; exe involvement is
unverified — see Open items). Read in build order: damage scaling (2026-07-16, confirmed) → the roll-2
opposed-RES swap (2026-09-01, confirmed 2026-09-02) → Evil/Pure-Evil casters seize control instead of
damaging (2026-09-02, confirmed). A prerequisite crash fix, `build_abiltypes_relocate.py` (unrelated —
see `03-abilities-added.md`), is **✅ CONFIRMED WORKING 2026-09-02** and must stay applied; it is not otherwise
covered here.

### A. Damage = 0.5 × level × casterRES

**Status: ✅ CONFIRMED WORKING (2026-07-16)**, user-validated in-game. Script `build_turnundead_res.py`
(no `--undo`). Binary `AoWEPACK.dpl`.

> **DAM = clamp( round(0.5 × level × casterRES), 127 )** — integer maths `(level·RES + 1) >> 1`
> (round half-up; RES 0 ⇒ 0). ATK is deliberately left on the vanilla level table (9/10/11/12). Two
> parts patched: the damage actually dealt, and the info card's displayed DAM, so the shown number
> matches what is rolled.

| RES | L1 | L2 | L3 | L4 |
|---|---|---|---|---|
| 2 | 1 | 2 | 3 | 4 |
| 8 | 4 | 8 | 12 | 16 |
| 15 | 8 | 15 | 23 | 30 |

Turn Undead is a touch attack, class `TTurnUndeadAbility` (VMT ptr `0x5571FDFC`, **ends at `+0x124`** —
no room for the Command-family slots, a fact that shapes feature C below). `GetTurnUndeadDamage
@0x5576B214` is the vanilla level×4 lookup; it receives only `edx=level`, never the caster, so the fix
has to hook the *call site* where the caster is in scope, not the function itself.

**Combat path** — inside `CreateTurnUndeadCA @0x5576B528` (verified: `ESI`=attacker combat object,
`EBP`=target, via the to-hit calc `ESI.GetAttack − EBP.GetDefense`):

```
5576B56C  call [ESI.vmt+0xB0]     ; GetAbilityLevel(TurnUndead) -> level
5576B57C  call [this.vmt+0x10C]   ; GetTouchAttack(level) -> CA attack        (UNCHANGED here)
5576B589  call 0x5576B214         ; GetTurnUndeadDamage(level) -> CA damage    <== REPOINTED
```

At `0x5576B589`: `EDX`=level, `ESI`=attacker combat object, `EAX`=this. Repoint the 5-byte `call` →
cave **`0x5580E2A0`** (36 B originally; grows a little as re-tuned — see the verifier note below).
RES source is combat-object `VMT+0x74` (`TCombatUnit.GetResistance`, forwards to the strategic unit's
`VMT+0xCC`) — the caster's *effective* RES, buffs and debuffs included. The 127 clamp guards
`TDamageCA.GenerateEx @0x55729C98`'s `movsx ecx, byte [ebp+0x10]` signed-byte read; at realistic values
(level ≤4, RES ≤~30) it is invisible in practice.

**Display path** — `GetCombatInfo @0x5576B234`'s owner isn't in a register at the point it needs it, so
the whole function is replaced: a 5-byte entry `jmp` → cave **`0x5580E300`** (101 B), which keeps the
owner in `EBP`, replays `GetTouchAttack` for ATK, then computes the same `round(0.5×level×RES)` for
DAM via the owner's strategic `VMT+0xCC`. Both caves are register/immediate + rel32-only ⇒
position-independent.

**Deliberately not changed:** `GetOffensiveStrength @0x5576AEDA` (AI unit-strength heuristic — its
damage is already capped at 5, so `level×RES` would just always clamp, not worth touching) and the
separate DV/predictor preview (`GetDamageValueEx`/`fcGetDamageValueEx`, a different float×stat formula
entirely — affects only the AI's pre-battle odds estimate, never the damage actually applied).

**Revert:** no `--undo`. Manually restore `0x5576B589` to `E8 86 FC FF FF` (5-byte call to
`GetTurnUndeadDamage`) and `0x5576B234` to `53 56 57 8B D9` (5 bytes), then zero both caves — sizes vary
with the installed formula, so re-disassemble (`--dis`) before zeroing rather than trusting a byte
count from this doc.

⚠ **The formula has been revised twice** (`level×RES` → `level×max(RES−3,1)` → `0.5×level×RES`), and
each revision shifted cave layout. **Never revert-and-reapply to re-tune** — that procedure has already
gone stale once in this project's history (an earlier version of this doc pointed at
`.pre-turnundead`, which by now sits under dozens of later layers). Re-tune by making the script accept
*either* the installed cave bytes or the new ones, overwrite in place, and take a fresh
`.pre-<feature>` backup — the pattern `build_invis_penalty.py` established.

### A′. Roll 2 swapped to an opposed casterRES check

**Status: ✅ CONFIRMED WORKING (2026-09-02)** — bundled into the evil-command feature's in-game test,
whose confirmed checklist explicitly includes "damage/info-card". Script `build_turnundead_resroll.py`
(has surgical `--undo`), applied 2026-09-01. Binary `AoWEPACK.dpl`.

Two rolls stand between using the ability and the stun/seize landing:

1. **To-hit**, in `CreateTurnUndeadCA`: `HitRole(attackerATK − targetDEF)`. `HitRole @0x55725D98` =
   `clamp(diff × 5 + 50, 10, 90)` % at the live 5pp/point slope (`imul eax,eax,5` — vanilla was ×10,
   see `01-combat-maths.md`), then `RandInt(100) < chance`. A miss means `GenerateEx` is never called,
   so `ca[+0x10]` stays 0 — no damage, no stun.
2. **Damage roll**, inside `GenerateEx` → `ExecuteDamageRoleEx @0x55726A6C`. Turn Undead passes
   `param_4=1`, which selects the defender's **`GetResistance`**, not Defence — so
   `ExecuteDamageRole @0x55725EAC` runs with `diff = attackerTerm − targetRES`. That routine:
   `r=RandInt(20)`; `r<2` ⇒ 0 (flat 10% auto-fail); `r≥18` ⇒ full damage (10% auto-max); otherwise a
   ramp against `t = 10 − diff` in the **live** DLL (not vanilla's `10 − 2×diff` — `build_hitslope5.py`
   nop'd out the doubling as one of its seven sites, byte-diff-verified 2026-09-01). Consequences: each
   point of stat difference is worth 5pp, not 10; the roll's usable band is diff ∈ [−8,+8], pinned at
   10%/90% outside it. Result is halved (round up) against partial holy protection.

**The change:** the *attacker* term of roll 2 was `GetTouchAttack(level)` — the flat 9/10/11/12 level
table, not a stat. Ziggurat already scales the *damage rating* off caster RES (feature A above), but
the *chance* term was still the flat table — which floors against undead with RES ≥ 20, since 9–12
against a doubled RES stat pins at the 10% auto-fail band regardless of level. Swapped for
**casterRES × (4+level)/5** (mult 1/1.2/1.4/1.6 for levels I–IV), making roll 2 a true opposed
`casterRES − targetRES` check with no new gate and no new RNG draw (only the *attacker's* side of the
already-existing roll changes).

Patch site — replace 6 bytes at **`0x5576B57C`** (`ff 91 0c 01 00 00`, the `call [ecx+0x10C]` that was
`GetTouchAttack(level)`) with `E8 <rel32> 90` into a small cave:

```
push  edx               ; save level (EDX = level on entry, from mov edx,[esp] @0x5576B575)
mov   eax, esi          ; attacker combat object
mov   edx, [eax]
call  [edx+0x74]        ; TCombatUnit.GetResistance -> AL
movzx eax, al            ; MANDATORY -- returns in AL only
pop   edx
movzx edx, dl            ; level 1..4
add   edx, 4              ; 5..8
imul  eax, edx            ; casterRES * (4+level)
add   eax, 2               ; round to nearest
mov   ecx, 5
xor   edx, edx
div   ecx                  ; eax = round(casterRES * mult)
ret
```

Max intermediate `255×8+2=2042` — no overflow; `xor edx,edx` before `div` is mandatory. Register-only ⇒
position-independent; clobbers only EAX/ECX/EDX (caller reloads both immediately after), so
EBX/ESI/EDI/EBP survive — the same ABI the existing `0x5580E2A0` cave already proved from this call
site. Roll 1 (`HitRole(attackerATK−targetDEF)`) is untouched; Turn Undead's ATK is otherwise unchanged.

Resulting odds (chance the stun/seize roll lands, after a successful to-hit):

| casterRES | vs tRES | L1 | L2 | L3 | L4 |
|---|---|---|---|---|---|
| 8 | 8 | 50% | 60% | 65% | 75% |
| 8 | 20 | 10% | 10% | 10% | 15% |
| 12 | 20 | 10% | 20% | 35% | 45% |
| 20 | 20 | 50% | 70% | 90% | 90% |
| 30 | any ≤20 | 90% | 90% | 90% | 90% |

Two things fixed, one caveat: level matters again; and it repairs the pre-existing gap (old L4 odds
were 90/70/50/30/10/10/10% at target RES 4/8/…/28 — floored against any doubled-RES undead ≥20). ⚠ It
also **saturates for strong casters** — the roll's whole usable band is ±8, and `casterRES×1.6` at
RES 20 already adds +12, so from roughly casterRES ≥ 20 the result pins at 90% against most targets and
ability level stops mattering, exactly where high-RES heroes live. Flagged, not fixed — halving the
difference (`(casterRES×mult − targetRES)/2`) would spread the same design across the full RES 0–40
range if the flat top is ever unwanted; one extra `shr` in the cave.

**Consequences built alongside:** the info card had to move with it — edited *inside* the existing
`0x5580E300` cave from feature A (at `0x5580E31B`), not a new cave, so the displayed ATK still equals
what roll 2 actually uses. This also shifts the damage *amount* for non-evil casters, since
`ExecuteDamageRole` reuses the same difference for its zero-threshold and its ramp — a genuine balance
change, not just a display fix. ⚠ `GenerateEx` takes the attack argument as a signed `char`; RES above
127 would read negative — unreachable at current clamps (hero RES caps at 40) and vanilla `touchAttack`
had the identical property, noted only so it isn't rediscovered as a bug.

**Revert:** `python build_scripts/build_turnundead_resroll.py --undo`.

### B. Evil/Pure Evil casters seize control instead of damaging

**Status: ✅ CONFIRMED WORKING (2026-09-02)** — user validated in-game: launch, seize, revert on caster
death, permanence on survival, strip list, retaliation guard (auto-resolve), damage/info-card. Script
`build_turnundead_evilcommand.py` (surgical `--undo`), 15 patch sites in `AoWEPACK.dpl`. Request: when
Turn Undead is used by an Evil or Pure Evil unit/hero, it should seize control of the undead target
like Charm/Seduce/Dominate instead of dealing holy damage + stun; if the caster dies in the same
battle, the seized undead should revert.

**The second requirement is free.** Revert-on-controller-death-within-battle is already vanilla
behaviour of the `TCommandAbility` family (below) — piggybacking on it, as the user proposed, costs
nothing. All the cost is in making the engine *dispatch* that machinery for a caster that doesn't own a
command ability.

#### B1. The two mind-control families — Possess is a red herring

`TPossessAbility`/`TPossessCA` look relevant and are not: `TPossessCA.Execute @0x557696E0` is a
**body-snatch** (swaps the possessor's combat object onto the victim's strategic unit); do not model on
it. The real family is **`TCommandAbility`** (VMT base `0x55720544`); Seduce/Dominate/Charm are thin
subclasses overriding only `Create`/`GetTouchAttack`/`CanTouch`:

| ability | own id `[+0x0C]` | paired "…ed" id `[+0x28]` |
|---|---|---|
| Seduce | `0x1D` (29) | `0x30` (48) |
| Dominate | `0x1C` (28) | `0x96` (150) |
| Charm | `0x94` (148) | — |
| Turn Undead | `0x26` (38) | *none — not a command ability* |

`CommandAbilityIDs @0x558E84E4` = `{0x1D, 0x1C, 0x94}` (3 dwords), iterated by `TCommandCA.Execute` and
`TPossessCA.Execute` to strip any pre-existing control off a victim before taking it.

#### B2. How a seize works, and where the revert-on-death already lives

`TCommandAbility.fcExecuteCombatCommand @0x557703C0` → `CreateCommandCA` (rolls via
`CombatTouchRole`, stores the ability's own id in `[CA+0x10]`, forces failure if the target
`IsClass(TLeader)`) → `TCommand CA.Execute @0x5576FC68` → on success, opposing sides only, calls
**`TCommandAbility.Command @0x5576FE50`**, which: flips the victim's combat-object side
(`SetCombatPlayer`), creates a `TCommandedAbilityData` on the victim (`[+0x0C]`=commanded id,
`[+0x14]`=controller ability id, `[+0x10]`=commander's CO id, `[+0x18]`=**victim's original side** —
what a revert restores), sets the victim's ability bit, and appends the victim's CO id to the
commander's `TCommandAbilityData.TByteList` at `[+0x10]`.

Revert-on-death is already there: `TCommandAbility.CombatObjectDestroyed @0x5576FE44` →
`ResetCommandedUnits @0x5576FF94` walks the commander's `TByteList`, resolves each victim via
`TCombatData.FindID` in the **active combat**, and calls `Uncommand @0x5576FF08` (restores the stashed
side, strips the ability) on each. `TCommandAbility.CombatDone @0x5576FE28` drops the commander's data
record at combat end, which is exactly why surviving control becomes permanent. (Contrast
the cross-battle variant below, which wants the *cross-battle* version — a separate, still-unbuilt
feature.)

#### B3. The one real obstacle — dispatch requires ownership

Both the notification and the revert are gated on ability **ownership**:
`TAbilityOwner.TriggerCombatDone @0x5574FEC4` iterates ability ids and calls `owner.vmt[0x4C](id)`
("does this owner have ability id") before invoking the hook — an ability the owner doesn't have is
never notified. `ResetCommandedUnits` re-checks it itself via `GetAbilityEnabled`.

⇒ **Reusing Dominate's id (`0x1C`) fails silently** — an Evil cleric doesn't own Dominate, so its death
never triggers the revert. Granting real Dominate is also out (it would become a usable ability whose
`CanTouchUnit` permits living targets). ⇒ **`TTurnUndeadAbility` cannot be promoted into a command
ability either** — its VMT ends at `+0x124` (the class-name string sits where Command's slots would
be); extending it means relocating the whole VMT into a cave (~78 new `.reloc` entries, against the
project's PIC rule).

**The workable shape:** mint a new, hidden command-ability *instance* **`N = 0x88`** (a cloned
`TDominateAbility`/`TCommandAbility` instance, sharing its VMT — "clone the instance, not the class")
plus its paired commanded-status ability **`M = 0x89`**. Hook **`TTurnUndeadCA.Execute @0x5576AC00`** —
not `fcExecuteCombatCommand` (see the rejected alternative below).

**Design decision (user, 2026-09-01): the seize chance is whatever already governs Turn Undead's
stun** — no separate roll. `TTurnUndeadCA.Execute` grants the flee/panic status `0x22` when
`ca[+0x10] != 0` (the field `TDamageCA.GenerateEx` writes the rolled damage into — it doubles as the
success flag) and the victim survived. Hanging the seize on the same test makes the two chances
identical by construction, with no duplicated roll.

#### B4. The hook

Resolve the attacker via `TCombatData.FindID(combat, ca[+0x0D])`, read combat-object `VMT+0x90`
(`GetAlignment`, forwards to strategic `+0xFC`): not `alEvil(4)`/`alPureEvil(5)` ⇒ fall through to
vanilla unchanged; Evil ⇒ **skip `TDamageCA.Execute` entirely** (suppresses HP loss *and* the
damage-type statuses — this is what "controls instead of stun/damage" means), then if `ca[+0x10]!=0`,
call **`Command(N, attackerCO, victimCO)`** directly in place of granting `0x22`.

Calling `Command` directly (not via `CreateCommandCA`) is what keeps this small — `CombatTouchRole`,
`GetTouchAttack` and `GetLevel` are never consulted, so `N` needs no private VMT. Because `Command` is
called directly, three things `TCommandCA.Execute` normally does must be replicated or consciously
dropped:

1. `GetSide(attacker) != GetSide(victim)` guard — **replicated** (else an already-friendly undead could
   be "seized").
2. The two loops over `CommandAbilityIDs` stripping an existing controller off the victim —
   **replicated** (else a unit already Dominated by a third party ends up with two controllers).
3. Commander gains the victim's level as XP, as `TCommandCA.Execute` does — **omitted**, a balance
   choice, not a correctness one.

**Setting the caster's bit `N` is mandatory** — `Command` creates the commander's data record but never
calls `SetAb` on the commander (real Dominate users already own the bit), so the cave must set it at
first seize or both ownership gates in §B3 fail and the revert never fires. The bit persists (harmless
— later battles `GetAbilityData` returns 0 and `ResetCommandedUnits` no-ops) but `N` must stay
**invisible** on the card and in level-up selection (`[+0x20]` selection mask = 0; ⚠ `Ability.pfs`
tag 9 overwrites the cave's mask, per the ability-selection-mask rule).

**Rejected alternative — redirect `fcExecuteCombatCommand`.** Repointing `TTurnUndeadAbility` VMT slot
`+0xA4` (VA `0x5571FEA0`, holds `0x5576B5C0`, verified unpatched) at
`TCommandAbility.fcExecuteCombatCommand` with `this` swapped to `N` is a tidy one-slot swap (`+0xA4` is
the same slot in both classes) and inherits Command's retaliation rule for free — **but it routes the
roll through `CreateCommandCA`→`CombatTouchRole`, which uses `N`'s own `GetTouchAttack`/`GetLevel`, and
`TDominateAbility.GetTouchAttack` ignores its level argument and returns a constant 6.** So it does not
reproduce Turn Undead's stun chance without a private VMT for `N` — the reason this route was rejected.
Kept recorded as the right hook if the chance requirement is ever relaxed.

#### B5. Targeting needs no work

`TTurnUndeadAbility.CanTouchUnit @0x5576ADC4` already gates undead-only (`GetUnitType()<2` and
(`GetRace()==0x0B` or `GetAbilityEnabled(0x81)`)); `TCommandAbility.CanTouchUnit` only requires
`GetUnitType()!=2` (`utMachine`), which the Turn Undead gate already implies. Only the *execute* slot is
redirected, so the UI, AI targeting and range checks keep using Turn Undead's own gates untouched.

#### B6. The strip list — six loops, not four

`CommandAbilityIDs` needed a fourth entry (`N`), and the census of *every* pristine reference found
**six** loops, not the four a naive scan finds:

| site | how it reaches the array | patched? |
|---|---|---|
| `TCommandCA.Execute` loops 1/2 | `mov esi,imm32` @`0x5576FCD9`/`0x5576FD05` | yes |
| `TPossessCA.Execute` loops 1/2 | `mov esi,imm32` @`0x55769717`/`0x55769743` | yes |
| `TMindDecayCA.Execute` loops 1/2 | via a **data-pointer cell** `0x558E91FC` — missed by a byte scan for `mov reg, 0x558E84E4` | yes (the **cell** is retargeted) |
| `TCombatUnit.CommandingTargetPriority`/`Strength` | `imm32` @`0x55725886`/`0x557258DA` | **no — deliberately** (AI target *scoring*, a balance decision) |

Fix: a 4-entry copy at `0x5583225C`, six sites' `mov ebx,3` raised to `4`; the vanilla 3-entry array is
left byte-identical for the two AI scorers. ⚠ **The array patch and the ability registration must
apply/revert atomically** — the patched loops call `GetAbility(0x88)` then vcall the result;
`GetAbility` returns nil for an unregistered id, and undoing the registration alone would crash every
vanilla Dominate/Seduce/Charm/Possess/Mind-Decay in ordinary play (`mov ecx,[eax]` faults on nil). Both
live in `build_turnundead_evilcommand.py` behind one state verdict. ⚠ The feature's own strip loops
need the 4-entry array too, or a *second* evil Turn Undead caster seizing what a first one holds
reproduces the identical two-controller defect. ⚠ **Mind Decay's interaction is one-directional** —
Mind Decay holds its victim via ability `0x83` ("Decay", granted directly, no `TCommandAbilityData`
pair) so it structurally cannot be strip-listed: Mind Decay taking our victim strips us, but our seize
never clears `0x83` off a Mind-Decayed victim. Vanilla Dominate has the identical gap — not a
regression.

#### B7. Why the AI never fires this ability, and the constraint that keeps it that way

`TFastCombatUnit.fcExecute` enumerates every enabled ability id and calls `vmt[0xA0]` on each, so it
genuinely reaches `0x88` once a caster owns the bit. It produces nothing because
`TCommandAbility.fcGetDamageValueEx` → `CombatTouchRoleProbability` reads `GetTouchAttack` and checks it
against a sentinel: `cmp ebx,-0xA; je → probability 0.0` @`0x5576827B`. `0x88` is a **plain**
`TCommandAbility` (no override), so `VMT+0x10C` = `mov al,0F6h; ret` = **−10**, exactly the sentinel —
`fcPrefetchCombatCommands` skips every target, and `CombatTouchRole` carries the identical sentinel, so
even a hand-queued command would always miss.

⭐⭐ **This is load-bearing, not incidental.** Never give `0x88` a private VMT with a real
`GetTouchAttack` — it would instantly become a generic Dominate the auto-resolve AI fires at any
non-machine living enemy, since `TCommandAbility.CanTouch`/`CanTouchUnit` impose no undead gate and no
alignment gate. The undead restriction lives *only* in `TTurnUndeadAbility.CanTouchUnit`, which this
path never reaches — the "clone the instance, share the VMT" decision is a correctness choice, not
merely a size one.

#### B8. The retaliation guard — auto-resolve only

Vanilla Turn Undead retaliates whenever the target still stands; `TCommandAbility` retaliates only when
its CA *failed*. A successfully seized undead was getting a free swing at its new owner. The guard
replaces 7 bytes at **`0x5576B5EC`** (`8b c3 8b 10 ff 52 60`) with `call cave_retal` + 2 nops; the
existing `test al,al / je 0x5576B619` consumes the returned AL.

| caster | roll | target enabled | retaliate? |
|---|---|---|---|
| any | — | no | no (vanilla) |
| any | failed | yes | yes (vanilla, and Command's rule too) |
| non-evil | succeeded | yes | yes (vanilla, deliberately unchanged) |
| **evil** | **succeeded** | yes | **no** ← the guard |

Both fallback paths (nil `FindID`, disabled target) fail *toward* retaliation, i.e. toward vanilla.

⚠⚠ **Scope: fast combat only — manual tactical already had the guard.**
`TTurnUndeadAbility.fcExecuteCombatCommand @0x5576B5C0` has exactly **one** caller in the whole
package (`TFastCombatUnit.fcExecute`); manual tactical combat re-implements the whole sequence in
`AoWTCPCK.dpl` (`CombatTE.TCAbTouchMoveTE.LastMove @0x0040A7ED`), whose own `cmp byte [eax+0x61],0 /
jne 0x40AC13` already skips retaliation on any successful Turn Undead, for *any* alignment. So manual
tactical never granted retaliation after a successful Turn Undead in the first place — the guard closes
a gap that existed only in auto-resolve. **Test the guard by auto-resolving**; a manual-combat test
proves nothing (the seized unit won't retaliate whether the guard works or not, and the matrix's third
row will look "broken" there because manual combat never granted it to begin with).

#### B9. The ankh overlay icon

**Status: ✅ CONFIRMED WORKING (2026-09-02)**, both combat modes. Two halves, neither sufficient alone:
(1) an `Ability.pfs` record for `M = 0x89` (key 147, `build_commandedundead_pfs.py`, cloned from
`0x22`'s SEFFECT.ILB sequence); (2) a block in **`TAbstractUnit.ShowEx @0x557812EC`**, which draws
persistent status icons from a **hard-coded chain of 16 ability ids** (`0x30` Seduced, `0x96`
Dominated, `0x95` Charmed, `0x22` Turned Undead/panicked, `0x6B` Possessed…) — there is no generic
"draw every ability's icon" loop. `cave_ankh @0x558322B0` adds `0x89` to the chain via a `call rel32`
retarget at the epilogue (`0x55781A2E`), nil-checking `GetAbility` and asserting record 147 carries a
real image sequence. ⭐ **Any future status ability that should show an overhead icon needs its own
`ShowEx` block — the `.pfs` record alone draws nothing.**

#### Traps found building this feature

- Possess ≠ mind control — don't model a command-family feature on `TPossessAbility` (§B1).
- `CanTouchUnit`'s `param_3` is a **strategic** unit; `CanTouch`'s is a **combat** object (it derefs
  `param_3[0x13]` = `+0x4C`) — resolving `+0x114` against the combat VMT gives `ExecuteDamageRoleEx`
  and reads as nonsense. An offset means nothing without its class.
- `TUnit.GetAlignment @0x55782770` returns `alPureEvil(5)` for *any* unit with ability `0x6B`
  (Possessed) — a possessed unit therefore counts as an Evil caster here. Engine quirk, cosmetic in this
  feature.
- `ca[+0x10]` is the damage amount *and* the success flag — **you cannot zero the damage to suppress
  the effect** (a zero rating makes the roll fail and the seize never fires). Suppress by **skipping
  `TDamageCA.Execute`**, never by reducing the damage input.
- ⚠⚠ `fc`-prefixed methods are **auto-resolve only** — manual tactical re-implements them in
  `AoWTCPCK.dpl`. Before hooking any `fc*` method, find its manual counterpart first. `cave_exec` is on
  *both* paths only because it hooks the CA (`TTurnUndeadCA.Execute`), reached via
  `TCombat.ExecuteCombatAction` from both combat modes.
- `CombatTouchRole` reads `ability.vmt[0x70] GetLevel(owner)` and feeds it to `GetTouchAttack`, but
  `TDominateAbility.GetTouchAttack` ignores it and returns a constant 6 — why the rejected
  `CreateCommandCA` route (§B3) can't reproduce Turn Undead's stun chance.
- Two ability ids are needed (`N` controller + `M` commanded) — **measure them at build time** with
  `check_id_free()`; never quote a free id from a doc (`03-abilities-added.md` has gone stale twice — a
  taken id gives a bare `Runtime error 217` at init).

#### Key addresses

| what | VA |
|---|---|
| hook: `TTurnUndeadCA.Execute` (chosen) | `0x5576AC00` |
| `TTurnUndeadCA.GetSuccessfull` (reads `ca[+0x10]`) | `0x5576ABF8` |
| `TDamageCA.Execute` (skipped by the evil branch) | `0x55729D14` |
| `TDamageCA.GenerateEx` (writes `ca[+0x10]`) | `0x55729C98` |
| `TTurnUndeadAbility.CreateTurnUndeadCA` | `0x5576B528` |
| flee/panic status granted on stun | id `0x22` (34) |
| `TTurnUndeadAbility` VMT `+0xA4` (rejected hook, unpatched) | `0x5571FEA0` (holds `0x5576B5C0`) |
| `TCommandAbility.fcExecuteCombatCommand` / `CreateCommandCA` / `Command` / `Uncommand` / `ResetCommandedUnits` | `0x557703C0` / `0x55770358` / `0x5576FE50` / `0x5576FF08` / `0x5576FF94` |
| `TCommandCA.Execute` | `0x5576FC68` |
| `TCombatUnit.GetAlignment` (combat VMT `+0x90`) | `0x55724FF4` |
| `TCombatData.FindID` / `TCombatObject.GetSide` | `0x55728C68` / `0x55726660` |
| `CommandAbilityIDs` (3 dwords, vanilla) | `0x558E84E4` |
| `TCommandAbility` VMT base | `0x55720544` |
| `TTurnUndeadAbility` VMT base (ends `+0x124`) | `0x5571FDFC` |

### Open items carried from Turn Undead

- The evil branch skips `TDamageCA.Execute`, so roll 2 still decides the seize but deals no damage —
  confirm this reads correctly in play: an evil caster's seize odds are `HitRole(ATK−DEF) ×
  ExecuteDamageRole(casterRES−targetRES)`, with the damage magnitude computed and then discarded.
- Whether the commander should gain the victim's level as XP (§B4 item 3) — a balance call, not a
  correctness one. Currently omitted.
- Whether any humanoid undead has gender 0, which would let vanilla **Seduce** target it (Charm
  excludes undead explicitly; Seduce has no undead test at all). Check: the gender byte at
  unit-resource `+0x31` for undead records in `Unitres.pfs`.
- Verify no `AoWz.exe`/`AoWTCPCK.dpl` involvement in the Turn Undead ability path (per-binary rule) —
  the doc records this as unverified, not as clean.
- Whether the Turn Undead **combat spell** (`CombatSpells.TTurnUndead @0x557F7B94`, a separate class
  from the ability) should follow the same evil-command rule — out of scope as requested; flagged so it
  isn't a surprise later.
- Confirm ability `N` (`0x88`) stays off the unit info card once its selection mask reads 0.

---

## Vision — nine levels, +1 sight each

**Status: ✅ CONFIRMED WORKING (2026-08-09)**, author-tested in-game. `sight = 3 + level`, levels
**I–IX** (was `3 + 2×level` capped at IV, sight 11 → new ceiling 12). Ability id `0x40`, class
`TVisionAbility : TMultiLevelAbility : TAbility`. Script `build_vision9.py` (`--apply`/`--undo`/`--dis`,
dry-run default — **has** a surgical `--undo`, touches no backup). Binaries: `AoWEPACK.dpl` +
`Release/Ability.pfs` (record 74 tag 5, the description) — no exe patch, so no AoWCompat lockstep.
Backups `AoWEPACK.dpl.pre-vision9`, `Release/Ability.pfs.pre-vision9`.

### The five patch sites

| VA | change | note |
|---|---|---|
| `0x557B9889` | `mov [esi+0x28], 4` → `9` | the level ceiling; `CanExpand` is the only gate and Vision inherits it |
| `0x55780F12` | `03 F6` → `90 90` | `TAbstractUnit.VisibilityRange` — strategic map |
| `0x55724AEE` | `03 F6` → `90 90` | `TCombatUnit.GetVisibilityRange` — tactical |
| `0x557B9897` | 72 B of four inline `Put`s → `jmp cave_vcosts` | nine per-level skill costs instead of four |
| `0x557B5138` | VMT `+0x10C` → `cave_vlname` | level names V–IX; the slot keeps its `.reloc` |

⚠ **`0x55817000..0x55817400` (1024 B) is exclusively reserved by this feature** — content is ~280 B but
the block is written/zeroed as one unit; anything a future feature parks there is silently overwritten
on `--apply` and zeroed on `--undo`.

### Why both halves had to ship together

`TArmy.UpdateVisibilityRanges @0x5578E10C` packs the stack maximum into a **nibble pair** at
`[army+0x29]` with **no clamp** (`shl ebx,4` → max TrueVisionRange in the high nibble, `add bl` → max
VisibilityRange in the low one). Sight must stay ≤15. Raising the cap to 9 while keeping the old +2/level
would reach 21 (wraps, corrupts TrueVisionRange); cap 9 at +1/level reaches 12 — fits, and is in fact
*safer* than what it replaced (`GetLevel` is not clamped by `[+0x28]`, only `CanExpand` is gated by it,
so a data-assigned level above the cap still reaches the arithmetic — at `3+2×level` a level of 7 would
already have overflowed). Cannot stack with an item: both sight sites query via the item-searching
`VMT+0x144` accessor, which routes through `GetSuperlativeAbOwner` — a **max**, not a sum.

### Balance — the nerf is deliberate

Unit data was **not** rescaled (author's decision) — every existing holder simply sees less; do not add
a rescale path.

| Vision | sight before → after | carriers |
|---|---|---|
| I | 5 → 4 | 22 units, 49 heroes |
| II | 7 → 5 | 22 units, 1 hero, Helm of Eyes |
| III | 9 → 6 | 13 units |
| IV | 11 → **7** | 7 units (incl. Air Galley, Beholder) |

Matching the old level-IV sight now needs Vision VIII (64 skill points against the previous 32).

⚠ **Two pre-existing undocumented Ziggurat edits were found at these sites**, byte-diffed against
`AoWEPACK_original_backup.dpl`, owned by no build script: base sight `83 C6 04`→`83 C6 03` (4→3) at
both range sites, and per-level cost `B9 05`→`B9 08` (5→8) at `0x557B9897`. A script written against
Ghidra's pristine image would assert the pristine bytes and abort; `build_vision9.py` instead verifies
the **live** values and aborts with an explanatory message if it ever finds the pristine base of 4.

### Hero skill cost — the DLL is authoritative, not `Ability.pfs`

**4 skill points per level** (36 to reach IX; halved from 8 the same day). For a multi-level ability the
cost lives in the DLL: `TAbility.ExpandCost @0x5574E908` returns `Ability.pfs` tag 6, but
**`TMultiLevelAbility.ExpandCost` overrides it** and reads the per-level `TIntegerList` at
`[ability+0x2C]` — the list `cave_vcosts` fills. Tag 6 is inert for cost here; the script writes it
anyway purely so the Ziggurat Manual's "Hero cost" column (which reads tag 6) doesn't print a number the
game never charges. ⚠ A cost is shown only when `Ability.pfs` tag 9's mask includes `0x100`
(`astHeroUpgrade`) — Transport and Dispel Magic have real per-level cost lists but no level-up screen
ever offers them, so both render blank; that is data-driven, not a special case.

### First length-changing `.pfs` write in this project

Record 74 tag 5 went 136 B (vanilla) → 211 (enumerated 9 levels) → 103 (header + one line) → **31 B**
(bare line, the final in-game text: `+1 vision range per level`, one line, no header sentence — two
author instructions in sequence dropped first the per-level enumeration then the header). Record 161
went 236 → 128 → 56 B in step. 87 later index offsets shifted on each pass (+75, −108, −72); every pass
ran a full collateral re-parse before writing, so both the grow and the shrink direction are proven.
⚠ **The description is a `u32`-length-prefixed string**, not the `u8` Pascal form used for names —
`pfs.pstr()` misreads it. ⚠ `desc_shape()` accepts all **three** emitted forms (bare curve; header+bare
curve; header+per-level listing) and must keep doing so — each was the output for part of one day, so a
real install can carry any of them; dropping an arm strands those installs (both `--apply` and `--undo`
refuse).

**Two ceilings on `MAX_LEVEL`, only one still bites.** Record 74's body directory uses u8 offsets: 10
levels fits (offset 240), 11 aborts (257 — two rungs before the nibble wall) — but the one-line
description retired the growth, so record 74 no longer scales with `MAX_LEVEL` and this ceiling is
inert unless a per-level listing is reinstated (escape: wide/u32 directory entries, already used by 25
other records). The real ceiling is the `[army+0x29]` nibble: `BASE_SIGHT + MAX_LEVEL ≤ 15`, so
**MAX_LEVEL 12 is the last value that fits**, 13 raises `SystemExit` at import — no cheap escape, it's
the engine's storage format.

### Failed / rejected approaches — do not re-try as-is

- **Extending the existing `GetLevelName` jump table** (`jmp dword[edx*4+0x557B9920]`) — all five
  entries carry `.reloc` entries; a cave-hosted table has none and goes stale on rebase. Repoint the
  **VMT slot** instead (itself relocated) — verified the *only* reference to `GetLevelName` in the
  module.
- **Copying `mov eax,[0x558E90C0]` (LoadResString) into the cave** to fetch the "Vision" stem — an
  absolute memory reference, un-relocatable from a cave. Call the original `GetLevelName` with level 0
  instead; it reaches the resourcestring through already-relocated code (same technique as
  `build_leadership4.py`'s `cave_lsname`).
- **Treating a 4-entry cost list read at index 9 as a crash.** `TIntegerList.Get` is bounds-checked and
  returns the list's default — the real, milder, harder-to-spot consequence would have been levels V–IX
  costing **zero** skill points.

### Re-tuning

Edit `MAX_LEVEL`/`COST_EACH`/`SUFFIXES` and re-`--apply` — do **not** revert first; both halves rewrite
in place and accept either the installed bytes or the new ones (verified 6/6 round-trip both ways,
including undoing a level-10 install with the level-9 script).

---

## Unit enchantment / status / combat-boost re-grade

**Status: ✅ CONFIRMED WORKING (2026-08-24)**, validated in-game the same day — **except the Blessed
pair, re-tuned 2026-09-13 and 🔨 APPLIED, UNTESTED (2026-09-13)** (see "Blessed raised to +2/+4"
below). Scripts `build_buff_regrade.py` (36 engine immediates, surgical `--undo`, backup
`AoWEPACK.dpl.pre-buffregrade`) and `build_assassin.py` (cave copies). Extractor
`re_tools/enchant_mods.py`; Ziggurat Manual section "Unit Enchantments". Binary `AoWEPACK.dpl`.

**Why:** the 5% conversion doubled every stat, so every buff landed on an even number (vanilla +2 became
+4, vanilla +3 became +6). The finer slope existed precisely to make in-between grades usable, and
nothing was spending that headroom — this re-grade drops the affected buffs one notch onto odd values.

### Decisions (user, 2026-08-24)

| # | decision |
|---|---|
| E1 | Enchanted Weapon → **+3/+3** ATK/DAM (not the mechanical +4/+4) |
| E2 | One notch down: Stone Skin +3, Frozen +3, Blessed DEF+1/RES+3, Nature's Blessing DEF+1/RES+3, Bloodlust +3/+3, Dark Gift +3, Fury ATK+5 |
| E3 | Combat boosts (Monster Slaying, Assassin, Charge) → **+5**, grouped with Parry as a *Combat Boosts* manual subsection |
| E4 | Debuffs: **only** Vertigo and Poisoned move to −3; Cursed/Entangled/Stunned/Webbed stay at the doubled −4; Bloodlust DEF and Fury DEF stay −2 |
| E5 | High Prayer Blessing matched to Blessed's *effect* (only the stat effect is equalised; the two remain different families — see below). ⚠ **Superseded in value by E8**, which moved the pair again — the *matching* is what survives |
| E6 | Invisibility to-hit penalties re-graded: ranged −6→**−5**; melee bounced −2→−1→**−2** (restored same day). Owned by `build_invis_penalty.py`, not this script — see the Invisibility section above |
| E7 | Holy/Unholy Champion melee → **+5/+5**, matching Monster Slaying/Assassin — 12 immediates (each in three strike builders × ATK/DAM); their ranged branch (already +2/+2) is untouched |
| E8 | **(2026-09-13) Blessed raised to DEF +2 / RES +4**, and High Prayer Blessing follows it there, keeping E5's match. Nature's Blessing stays at +1/+3 — distinct display name, so nothing forces it to track the pair |

### Two families — the class names lie about which is which

The engine's own test, `TAbstractUnit.AbilityToEnchantment @0x5577F3B4`, is an `IsClass` against
**`TUnitEnchantmentAbility`** (VMT `0x55722364`) — nothing else defines "is this a unit enchantment".

| family | root VMT | count | dispellable |
|---|---|---|---|
| Unit enchantments | `TUnitEnchantmentAbility` `0x55722364` | 21 | yes |
| Temporary statuses | `TDurationAbility` `0x5571DD68` | 13 | no |

**Eight `...Ability`-suffixed classes that read like enchantments are statuses:** Bloodlust, Cursed,
High Prayer Blessing, Nature's Blessing, Poisoned, Stunned, Vertigo, Webbed. Look-alike pairs straddle
the split — **Webbed (status) vs Entangled (enchantment)**, **Stunned (status) vs Frozen
(enchantment)** — never bucket by name. 14 of the 21 enchantments carry no stat modifier at all (Haste,
Concealment, Free Movement, Water/Wind Walking, Liquid Form, Fire Halo, Fire Protection, Summoned,
Cosmetic Surgery, Slow, Turned Undead, Holy/Unholy Champion); their effect is an ability-id test at a
consumer site, and they still belong in the enchantments list.

⚠ **`TBlessedEnchantment` and `THighPrayerBlessingAbility` both resolve to the display name
"Blessed"** — different families, same name, and since E5 the **same stat effect** (DEF+2/RES+4 since
E8) too. ⭐ **Move them together or not at all**: they are indistinguishable on the unit card, so a
change to one silently makes the same-named effect read two different numbers.
They still differ in how they arrive and end: Blessed is cast, permanent, dispellable; High Prayer's
version is combat-duration and cannot be dispelled. Three description strings now read near-identically
(`Ability.pfs` records 109/110/168) — the `FIXES` table for description edits must key on **record id**,
not text.

### Current live values (read any time with `re_tools/enchant_mods.py` — walks the class hierarchy and
disassembles the getters, so it cannot go stale)

| enchantment | live | vanilla |
|---|---|---|
| Blessed / High Prayer Blessing | DEF +2, RES +4 | +1/+1 |
| Bloodlust | ATK +3, DEF −2, DAM +3 | +1/−1/+2 |
| Cursed | DEF −4, RES −4 | −2/−2 |
| Dark Gift | DAM +3 (plus Death Strike and lifesteal +3 — neither is an enchantment stat, see below) | +1 |
| Enchanted Weapon | ATK +3, DAM +3 | +1/+1 |
| Entangled | DEF −4 | −2 |
| **Frozen** | DEF **+3** | −2 (Ziggurat flipped the sign — a deliberate ice-block design, then doubled and re-graded down one notch like the other E2 buffs) |
| Fury | ATK +5, DEF −2 | +2/−1 |
| Nature's Blessing | ATK 0, DEF +1, RES +3 | +1/+1/+1 |
| Poisoned | ATK −3, DEF 0, RES 0, DAM −3 | −1/−1/−1/−1 |
| Stone Skin | DEF +3 | +2 |
| Stunned / Webbed | DEF −4 | −2 |
| Vertigo | ATK −3, DEF −3 | −2/−2 |

Combat boosts, split melee/ranged in the manual because they differ:

| bonus | melee | ranged |
|---|---|---|
| Monster Slaying / Assassin / Holy Champion / Unholy Champion | +5/+5 | +2/+2 |
| Charge | DAM +5 | — |
| **Parry** | **−8 to the attacker** | — |
| Invisible target, attacker lacks True Vision | −2 ATK | −5 ATK |

Leadership: +1/+2/+3/+4 both stats by level — see the Leadership section below.

⚠ The four slayer-style bonuses' **ranged** branch is one shared cave (`build_ranged_slayers.py`
@`0x5580E190`, covering Monster Slaying `0x70`, Holy/Unholy Champion `0x92`/`0xA0`/`0x93`/`0xA1`,
Assassin `0x38`); their melee branches are separate engine sites per builder. In that cave `[esp]` is
DAMAGE and `[esp+8]` is ATTACK — an operand-swap trap the script documents. `0x55767C82` in
`CalculateStrikes` still reads `add dword [ebx], 3` — that is the *dead* Monster Slaying block,
superseded by the cave at `0x5580E148`; do not "fix" it to 5.

### Dark Gift lifesteal 4 → 3, and both texts rewritten — 🔨 APPLIED, UNTESTED (2026-09-14)

Owner's wording, verbatim: *"Gives a single unit Death Strike, +3 Dam, and +3 lifestealing."*

| what | where | before | after |
|---|---|---|---|
| DAM | `AoWEPACK.dpl` imm `0x557BB731`, `TDarkGiftEnchantment.GetDamage @0x557BB730` (`b0 03`) | +3 | **+3 — deliberately NOT touched** |
| lifesteal heal | `AoWEPACK.dpl` cave `cave_lsround @0x5580DC80`, DG imm byte `0x5580DCB1` (`83 c0 04` → `83 c0 03`) | 4 | 3 |
| spellbook text | `Release/Spells.pfs` rec 87 tag 10 | `'…, +3 to Damage, and +4 Lifestealing.'` | the sentence above |
| card text | `Release/Ability.pfs` rec 179 tag 5 | already read the target sentence (see below) | unchanged |

Scripts: `build_lifesteal_roundattack.py` (`DG_HEAL=3`; `LS_HEAL` stays **4** — `0x76` LifeStealing
is a different ability) and `build_pfs_typos.py` (both rows now carry the identical `new`; the table
resolves by record id, never by text).

⚠ **Both rows' declared vanilla baseline was fiction and has been corrected.** True vanilla, read out
of `<root>/Release/`, is `'Gives a single unit Death Strike and +1 to damage.'` for **both** records —
the spellbook row previously claimed `'…, +2 to Damage, and +2 Lifestealing.'`, which mentions a
lifesteal vanilla does not have. `--undo` would have written a string the game never shipped. Same
defect class as Ability 168 / Spells 66 (found 2026-09-13). `old[0]` is now the real vanilla text and
the intermediate Ziggurat states follow it in the tuple.

⚠ **`Ability.pfs` cannot currently be written at all** — `process()` aborts the whole file on the
first unrecognised row, and three rows are hand-edited past what the table knows: rec 103
(`'Inflicts -4 Def/Res…'`, the table expects `DEF/RES` — value already right, capitalisation differs),
rec 61 (`'(Atk-4 Res-6 and cannot launch offensive melee)'` — the Panic wording swallowed the closing
paren the row matches on), and rec 179 before this edit. 179 is fixed; **103 and 61 are still
blocking** and were left alone as out of scope. The Dark Gift card text is nevertheless already
correct in the live file, so nothing is outstanding for this feature.

### Blessed raised to +2/+4 — 🔨 APPLIED, UNTESTED (2026-09-13)

E8. Four immediates in `AoWEPACK.dpl`, written by `build_buff_regrade.py --apply`:

| site | imm VA | was | now |
|---|---|---|---|
| `PassiveAb.TBlessedEnchantment.GetDefense` | `0x557BB5E5` | +1 | **+2** |
| `PassiveAb.TBlessedEnchantment.GetResistance` | `0x557BB5E9` | +3 | **+4** |
| `PassiveAb.THighPrayerBlessingAbility.GetDefense` | `0x557BB80D` | +1 | **+2** |
| `PassiveAb.THighPrayerBlessingAbility.GetResistance` | `0x557BB811` | +3 | **+4** |

Three of the four land back on the plain doubled value — Blessed and High Prayer are simply **exempt
from E2** now, so those ROWS entries have `live == new` and `--undo` is a no-op there. Only High
Prayer RES ends above its doubling (vanilla +1, doubled +2, now +4).

⚠⚠ **Four text records describe this one effect, and the first pass moved only two.** All four are
`build_pfs_typos.py` rows:

| file | rec | tag | what the player reads it on |
|---|---|---|---|
| `Ability.pfs` | 168 | 5 | the **Blessed** ability card |
| `Ability.pfs` | 110 | 5 | the **High Prayer Blessing** card (same display name) |
| `Spells.pfs` | 66 | 10 | the **Bless** spellbook entry, read *before* casting |
| `Spells.pfs` | 112 | 10 | the **High Prayer** spellbook entry |

The two `Spells.pfs` rows were missed and caught in QA: the spellbook would have said +1/+3 while
the card said +2/+4. ⭐ **A stat change on an enchantment has an ability record AND a spell record**
— the spell that grants it describes the same numbers. Ability records alone are half the job.

⚠ **Two of those rows had a vanilla baseline that exists in no copy of the file.** `Ability.pfs` 168
and `Spells.pfs` 66 both declared `old` = "Resistance (+2)", the *pre-doubling code* value written
into a text row by mistake; every vanilla copy of both files reads (+1)/(+1). Since `old[0]` is what
`--undo` restores, the revert would have written a string the game never shipped. Both corrected
2026-09-13. **Check a text row's baseline against `<root>/Release/` before trusting it** — a wrong
`old` is invisible while the row is applied.

⭐ **A re-tune of an immediate migrates in place via an optional 7th ROWS element** listing superseded
grades, which `resolve()` accepts alongside `live` and `new`. Without it a changed `new` makes the
installed byte match neither, and the script aborts — the same failure the `.pfs` table solved with a
tuple `old`, and the same rule as the cave retune in CLAUDE.md.

⚠⚠ **Two defects in `build_buff_regrade.py` found while re-tuning, both fixed 2026-09-13, both of
which had made the byte and its manifest row drift apart silently:**

- **`sync_parents`' UNCHANGED flip was ONE-WAY.** It pins a row to `UNCHANGED` when the re-grade lands
  on the pre-doubling value, but its own filter then skipped every non-`DOUBLE`/`HALVE` row — so the
  pinned row became invisible to the script that pinned it, and neither `--undo` nor a re-tune could
  restore it. Both Blessed/High Prayer DEF rows sat at `newValue 1 / UNCHANGED` while the live byte
  was heading for +2, exactly the FOREIGN state the sync exists to prevent. The flip now leaves a
  ` | REGRADE:` marker in `ruling` and the filter readmits **only** marked rows — **1** of the 128
  `UNCHANGED` fivepct rows once E8 is applied (Nature's Blessing DEF, the one buff still re-graded
  onto its pre-doubling value); the other 127 stay excluded. It was 3 before E8 freed the two DEF
  rows, so read the count as a live measurement, not a constant.
- **The snapshot gate was a bare `not os.path.exists(BACKUP)`**, on the shared write path — so
  `--undo`, or the first `--apply` after a re-tune, would copy an already-patched dpl to a name
  reading `.pre-buffregrade`. Now gated on `want_new and at_live == len(rows)`, i.e. proof every
  immediate still sits on its doubled value. No snapshot was minted for E8, correctly: the revert
  path is the surgical `--undo`.

**In-game checklist (nobody has played this):**

1. Cast **Bless** on a non-hero unit — card reads DEF +2 / RES +4, and the description text matches.
2. Same unit's actual to-hit: +2 DEF is **10pp** on the 5% slope, not 5pp.
3. **Dispel Magic** removes Blessed; the stats fall back by exactly 2/4.
4. A **High Prayer** structure's blessing shows the same +2/+4 and expires with the combat.
5. Blessed **stacks** with Nature's Blessing (still +1/+3) rather than overwriting it.
6. Save, reload, re-open the unit card — the values survive (heroes recompute, units cache).

### What was and wasn't zeroed

Byte-diffed live vs `AoWEPACK_original_backup.dpl`, and checked for a VMT repoint: **Bloodlust was
never zeroed** — vanilla ATK+1, Ziggurat *raised* it. What Ziggurat did zero: **Nature's Blessing
ATK** (vanilla +1 → 0) and **Poisoned DEF and RES** (vanilla −1 each → 0). The manual prints a dash
(the glyph itself, not an empty string — an empty Ziggurat-side value means "not stated in the design
workbook" and renders a `?` tooltip, which is wrong for a number read out of the binary) for a zeroed
slot, same as a stat the class never modifies — the vanilla/Ziggurat comparison column still shows the
zeroing by contrast.

### The manual section

Three tables — Unit Enchantments (21), Temporary Statuses (13), Combat Boosts — matching the engine's
own taxonomy. `read_enchantments()` calls `enchant_mods.py` against **both** the live DLL (Ziggurat
column) and `AoWEPACK_original_backup.dpl` (vanilla column), so the existing compare switch works for
free; no number is hand-written. The extractor is hierarchy-driven with no hardcoded class list: it
enumerates every VMT via the Delphi `vmtClassName` shortstring, walks ancestry via `vmtParent` at
**VMT−0x18** (a pointer *to* the parent's VMT pointer — deref twice), and reads the fixed stat slots
`+0x5C ATK, +0x60 DEF, +0x64 RES, +0x68 DAM` (a slot still holding `TAbility`'s own `33 C0 C3` means "no
modifier"). Traps it has to handle: two getter encodings (`B0 nn` `mov al` vs `83 C8 nn` `or eax`,
sign-extended — Poisoned ATK/DAM, Fury DEF) — `decode_getter` **raises** rather than guessing on
anything unrecognised; non-uniform immediate offsets in the combat-boost adds (`80 44 24 dd nn` puts the
displacement *before* the immediate — reading a fixed `+3` there once shipped a bug); duplicate copies
(most conditional bonuses exist in two strike tables — `combat_boosts()` reads every copy and **raises
if they disagree**, since a divergence means a partial re-tune); Leadership's two storage schemes
(vanilla flat tables vs Ziggurat's per-level cave — reading a pristine DLL yields zeros, so the
extractor follows one unnamed-callee hop to the cave and slices to the ability's real level cap).

⭐ **Three verifiers were crying wolf.** `build_assassin.py`, `build_invis_penalty.py` and
`build_ranged_slayers.py` each generate cave bodies ending `jmp <stock exit>` and compare against
installed bytes — but `build_magebane.py` splices itself into those very exits, so no generated variant
could ever match, and two of the three reported a false `[x]` for months. Fixed: both now accept the
stock exit **or** a known chain exit, and re-terminate the body they write so the chain survives a
re-tune. **A verifier that cries wolf is a defect** — it trains you to ignore the one time it's right.

⚠ **Parent-manifest coupling.** Every byte this re-grade moves is also a row in `fivepct_manifest.json`
and/or `damhp_manifest.json` (see `01-combat-maths.md`), whose own verifiers accept only "recorded live"
or "recorded target". `build_buff_regrade.py` rewrites those rows' `newValue` on apply and restores them
on undo. Two rows needed more: re-grading +2→+1 lands the byte back on the pre-doubling value, which
`build_statdouble.py` would otherwise flag as a DESYNC — those rows are pinned `UNCHANGED` while the
re-grade is installed.

⚠ **Two lessons paid for in the description-text pass** (all 62 affected strings, applied via
`build_pfs_typos.py`): resolve by **record id**, not text uniqueness (three near-identical blessing
descriptions were once mismatched by text-matching — record id = ability id + 10 settles it); and
`FIXES` rows must be **one full-text row per field** — chained edits (doubling then re-grade touching
the same field) broke the old "find `old`, replace with `new`" scheme, and naive consecutive-row
collapsing is also wrong (some records hold independent edits, e.g. Marksmanship's eight level strings).
Rebuilt as one row per record/tag, `old` = the field at the `.pre-typos` baseline; round-trips
byte-identically both ways.

### ⭐⭐ NUMBER MODE — editing a description in AoWDevEd is no longer a breaking event (2026-09-14)

**Owner's objection, and it was right:** *"why not design it to not break just because a basic game
utility was used?"* A DevEd save had changed `Ability.pfs` rec 103 from `-4 DEF/RES` to `-4 Def/Res`
— a pure case change, not one digit touched — and `process()` abandoned the **whole file**, blocking
all 80 `Ability.pfs` rows. Two changes, both in `build_pfs_typos.py`:

**1. Match numerals, not prose.** Measured: **75 of the 95 rows differ from their `old` only in
digits.** What such a row asserts is "this description must state the value the binary holds"; the
sentence around the number belongs to the author. `number_sync()` is tried **only after** full-text
matching fails, so a clean tree behaves exactly as before, and is deliberately narrow — it refuses
unless the row is digits-only (`_shape()` equality, so Grip of Winter / Power Leech / Spellcasting
can never reach it), the live text carries the **same count** of numbers, and those numbers equal
either the target or an accepted pre-state. Verified against five hand-built cases:

| author did | result |
|---|---|
| reworded, numbers untouched | **syncs the digits, keeps the prose** |
| reworded, already at target | no write |
| **changed a value** (5 → 7) | **SKIP, flagged** — never overwritten |
| added a number | SKIP, flagged |
| removed the number | SKIP, flagged |

⭐ The third row is the load-bearing one: a changed *value* is exactly the text-vs-binary
disagreement this table exists to catch, so number mode reports it rather than silently restoring
the table's number over the author's.

**2. Skip-and-warn instead of abandoning the file.** One unmatched row used to `return` out of
`process()`, taking the other 79 with it — and it returned *before* printing the plan list, so you
could not even see what else was fine. Unmatched rows are now collected, reported with the row's
`what`, and skipped. ⚠ Two guards keep this honest: if **every** row is unmatched the file-level
failure is preserved (bad CRC, unrecognised index layout), and `not skipped` was added to the
`.pre-typos` gate, since a file holding text the table cannot account for is not the clean
pre-patch state that name claims.

Result on the live tree: rec 103 auto-heals; rec 61 (Panic — the author *added* `(14 vs Res)`, so
the count moved) is correctly still flagged; the other 79 process. **`--undo` went from dead to
reverting 76 of 80 rows** — the duplicate-row pairs at recs 38/116 that QA found on 2026-09-13 now
skip instead of killing the revert. ⚠ That underlying duplicate-pair ordering defect is **not
fixed**, only made non-fatal: a revert is still incomplete for those four rows.

---

## Webbed / Entangled DEF penalty — the units-cache-vs-heroes-recompute bug

**Status: ✅ CONFIRMED WORKING (2026-07-21)**, user-validated in-game. Script `build_debuffcache.py`
(no `--undo`). Backup `AoWEPACK.dpl.pre-debuffcache`. Binary `AoWEPACK.dpl`. Triggered by: "some debuffs
(webbed/frozen) don't consistently apply their stat modifiers to both units and heroes."

### ⭐ The precondition: units cache ability stat modifiers, heroes recompute live

`TUnit.Changed @0x55782B34` rebuilds a 4-byte cached block on the unit: `unit+0x44..0x47` =
ATK/DEF/RES/DAM from `GetAbAttackAll`/`GetAbDefenseAll`/`GetAbResistanceAll`/`GetAbDamageAll`.
`TUnit.GetDefense @0x55782A40` then only **reads** `[+0x45]` — it never walks the ability list.
`THero.GetDefense @0x557883E8` has **no cache** — it sums abilities live on every call via
`GetSuperlativeEnabledAbOwner` + `GetAbDefense`. `TCombatUnit.GetDefense @0x5572549C` bare-forwards to
the underlying unit, so **the asymmetry is live in tactical combat, not just the strategic map.**
`GetAbDefenseAll` has exactly one caller in the module — `TUnit.Changed` — and nothing else refreshes
the cache (verified: `SetAbSet`, `AddAbilityData`, `RemoveAbilityData` call no `Changed`).

**This is the general project rule now — applying a stat-modifying ability via `Expand` instead of
`ExpandAbility` silently does nothing on units, and heroes mask the difference. Always test a stat-cache
change on a non-hero.**

### Defect A — three apply sites skip `Changed()`

`TAbilityOwner.ExpandAbility @0x5574F5B4` is the wrapper that keeps the cache coherent: it calls
ability `Expand` (`vmt[0xD0]`) then, on success, `owner.vmt[0x90]` = `Changed()`. **Three combat-action
sites call `Expand` directly and skip the wrapper:**

| site | VA | applies |
|---|---|---|
| `TWebCA.Execute` | `0x5576A06C` | Webbed `0x61` |
| `TEntangleCA.Execute` | `0x5576A648` | Entangled `0x5E` |
| `TEntangleSpellCA.Execute` | `0x557F89F4` | Entangled `0x5E` (spell version) |

Contrast the correct path — every *other* status is applied through
`TAbstractUnit.ExecuteCombatDamageEffects @0x55781ED8` via owner `vmt[0x94]` = `ExpandAbility`
(Frozen `0x5F`, Stunned `0x5C`, Poisoned `0x60`, Cursed `0x5D`, Vertigo `0x62` all go through it, and
all correctly refresh the cache). **Webbed and Entangled are the only two statuses applied outside that
function, and both use the broken path.**

**Observable signature:** on a unit, the bit is set and the icon shows, but `[+0x45]` is stale — the
penalty has zero effect until some *unrelated* event (`SetHitPoints`/`SetExperience`/`SetRank`/another
properly-applied enchantment) happens to call `Changed`. On a hero, always works immediately. **Removal
always works** (routes through `RemoveAbility`→`Changed`), so debuffs wear off reliably but turn on
unreliably — the diagnostic tell for this class of bug.

### Defect B — the values themselves (not a bug)

Census of `GetDefense` (a single `MOV AL,imm; RET` per class): Stunned/Cursed/Webbed/Vertigo = −2
(pre-doubling figures — the current live values, doubled and partly re-graded, are in the Unit
Enchantments table above); **Frozen returns +2** (pre-doubling; now +3 live, see above) — **intentional,
user-confirmed 2026-07-21: Frozen depicts the unit encased in ice, so the bonus is the design. Do not
"fix" this byte.** Webbed/Entangled/Frozen/Stunned override `GetDefense` only — ATK/RES/DAM were never
implemented for them, a design gap rather than a defect. Field semantics: ability `+0x20` is the
selection/display mask; `+0x24` is a cosmetic type/category byte; `+0x28` is duration mode for the
`TDurationAbility` family only (1=days, 2=combat turns, 3=entire combat) — the enchantment family has no
such field and uses the `GetDurationMode` virtual instead (base = 0, never).

**Ruled out during root-causing** (compressed — do not re-derive): sign/`MOVZX` extension bug — dead,
every aggregator uses plain 8-bit `ADD BL,AL` and every clamp uses `MOVSX`; a Leadership-style "bare
bit, no data record" defect — doesn't apply, both `Expand` variants set the bit and add the record in
the same branch; a base-class split between `TDurationAbility`/`TUnitEnchantmentAbility` — governs
duration semantics and dispellability only, `GetDefense` is the same VMT slot `0x60` in both; `THero`
item-omission — doesn't recur, all four hero getters already include the item term.

### Unit morale→defence — this project's own pre-convention change, not vanilla

Found while chasing a suspected vanilla bug: `TUnit.GetDefense @0x55782A40` at `0x55782A69` carries a
**2-byte no-op** (`40 48` = `INC EAX; DEC EAX`) in place of the vanilla `ADD AL, [EDX]` (morale-based
defence modifier). **Confirmed by the user (2026-07-21) as their own change**, made before this
project's note-taking convention existed. **Intentional — do not "fix" it.** Byte-diffed across 18
archived DLL copies: vanilla `02 02` in 11 files up to `AoWEPACK - Weakness1.dpl`, the `40 48` patch in
7 files from `AoWEPACK - Copy (12).dpl` onward — introduced between 2026-01-04 and 2026-03-18.
`TUnit.GetResistance` keeps the vanilla idiom in all 18 copies, and `THero.GetDefense` still applies its
morale term — so the change is narrow: **units lose morale-based defence; unit morale-resistance, unit
morale-attack, and hero morale-defence all remain.** The design intent for that asymmetry was never
written down; treat current behaviour as desired, ask before altering. Same era/category as the
undocumented combat caves flagged in `12-re-toolchain.md` (old Life-Steal heal amount,
marksmanship+height, XP-on-hit) — very likely the same pre-convention period, equally intentional, not
chased further. **Anything in `AoWEPACK.dpl` that looks like a vanilla bug should be byte-diffed against
an archived pre-convention copy before being "fixed."**

### The fix (Defect A) — `build_debuffcache.py`

Chosen approach: fix the three call sites, not make units recompute live (that would put a full
ability-list walk inside `TAbstractUnit.UpdateDefensiveStrength`, which the AI calls in evaluation
loops — minimal blast radius wins). Each site's 6-byte `CALL [ECX+0xD0]` (`FF 91 D0 00 00 00`) →
`E9 <rel32> 90` into a 26-byte cave:

```asm
call dword ptr [ecx + 0xd0]      ; original Expand(ability=EAX, unit=EDX)
mov  eax, dword ptr [ebx + 0x4c] ; EAX = target unit (EBX = target combat unit, callee-saved)
test eax, eax
jz   .done                       ; nil guard -- vanilla would already have faulted, but free
mov  edx, dword ptr [eax]
call dword ptr [edx + 0x90]      ; Changed() -> rebuilds unit+0x44..0x47
.done:
jmp  <call_va + 6>
```

| site | CALL VA | cave VA | returns to |
|---|---|---|---|
| `TWebCA.Execute` | `0x5576A0A1` | `0x5580F900` | `0x5576A0A7` |
| `TEntangleCA.Execute` | `0x5576A68D` | `0x5580F920` | `0x5576A693` |
| `TEntangleSpellCA.Execute` | `0x557F8A44` | `0x5580F940` | `0x557F8A4A` |

`EBX` is callee-saved and demonstrably survives the call — vanilla itself reloads `MOV EAX,[EBX+0x4C]`
immediately after it at both Entangle sites, which is also why the `data+0x0F` source-side stamp still
works untouched. None of the three sites consumes `Expand`'s return in `EAX`, so the cave is free to
clobber EAX/ECX/EDX. **`Changed` is called unconditionally** (unlike `ExpandAbility`, which gates it on
`Expand`'s result) — deliberate: idempotent, and it also heals a cache left stale by a pre-patch save
when the debuff is re-applied (the gated version would skip the refresh forever on an already-webbed
unit, since `Expand` returns 0 on a refresh). Position-independent (register-indirect calls + one rel32
jmp). New caves should be allocated from `0x55810000` onward — the ~880 KB zero run starting
`0x5580F8C0` is plentiful, no need to keep crowding the low `0x5580C000` pocket.

Deliberately **not** touched: `TUnit.GetDefense` (carries the intentional morale no-op above) and
`TFrozenAbility.GetDefense` (the intentional +2/+3 bonus above).

### Revert

No `--undo`. Manually restore the three 6-byte `CALL [ECX+0xD0]` sites to `FF 91 D0 00 00 00` and zero
the three 26-byte caves at `0x5580F900`/`0x5580F920`/`0x5580F940`.

### Open items carried from this feature

- What else calls `TUnit.Changed` — governs how often a stale cache silently self-corrects, i.e. how
  often the pre-fix bug *appeared* to work by accident. Known callers: `SetExperience`,
  `SetHitPoints`, `SetRank` — list not exhaustively verified.
- `TUnitEnchantmentAbility.Expand @0x55765894` asserts `owner is TAbstractUnit` and `owner+0x18 >= 1` —
  if any caller can violate this and an outer handler swallows the assertion, that is a silent Frozen
  failure. Inferred risk only; no violating caller has been traced.
- `TCursedAbility.Create` never sets ability `+0x24`, leaving type 0 while its duration-family peers use
  1 — a cosmetic mislabel in the info panel, confirmed code, inferred (harmless) impact.
- Whether `AoWDevEd.exe` shares these call paths — per the per-binary rule, not assumed, not checked.

---

## Panic — cannot initiate melee, still retaliates

**Status: ✅ CONFIRMED WORKING (2026-09-13).** Script `build_panic_nomelee.py` (surgical `--undo`,
touches no backup). Binaries `AoWTCPCK.dpl` + `AoWEPACK.dpl`. Backups
`<game dir>\backups\AoWTCPCK.dpl.pre-panicnomelee`, `<game dir>\backups\AoWEPACK.dpl.pre-panicnomelee`.

**2026-09-12 — sixth hook `meleemove` added** to close a user-reported hole: the cursor said "no" but
a left-click still attacked. Applied and byte-verified; the previous five hooks are unchanged
(`--undo`/`--apply` round-trip is byte-identical). Nobody has played it.

**Goal (user's words):** "rather like how melee walkers cannot attack flyers offensively, but can
retaliate." **Verdict: the analogy is exact** — the flying rule is implemented the way the user
guessed, and copying its shape gives the retaliation behaviour for free with no change to any combat
arithmetic.

### The load-bearing fact

`AoWE.TMeleeRound.Calculate @0x55767D24` contains **no flying test at all**. The whole flying rule lives
in the "may I *initiate*?" gates upstream; once a round is built, both sides' strike counts
(`round+0x28` attacker, `round+0x2C` defender) come from their own properties only. So a ground unit
gets its two retaliation strikes against a flyer that attacked it regardless — nothing in the round
knows the reverse attack would have been illegal. **Gating Panic the same way inherits the same
property.** This is also why the round is the *wrong* place to patch (see Failed approaches).

⚠ **The trap: do not add `0x6C` (Panicked) to `TCombatUnit.GetLocked @0x55724BA4`.** `GetLocked` is
vanilla's total-incapacity predicate (`0x5F`/`0x61`/`0x5C`/`0x5E`/`0x22`); `Calculate` consults it for
**both** sides, so adding Panic there would stop the panicked unit retaliating too — the exact thing
this feature must preserve.

### How the flying rule actually works — all six sites

Ability id `1` = Flying, queried via `TCombatObject VMT+0xA8` (`GetAbilityEnabled`, item-aware). Two
different rules, easy to confuse:

**3a. One-way "can't hit what's above you" — the rule this feature copies**
(`if target.Flying and not attacker.Flying → forbidden`):

| # | module | site | gates |
|---|---|---|---|
| 1 | AoWTCPCK | `TCombatUnitSelectionControl.UpdateMoveCursor @0x0041FA7F` | the human attack cursor |
| 2 | AoWTCPCK | `TCAI.CheckUnit @0x00415478` | the tactical AI's melee evaluation |
| 3 | AoWEPACK | `TStrikeAbility.CanExecuteMelee @0x55766B75` | auto-resolve melee command prefetch |
| 4 | AoWEPACK | `TStrikeAbility.fcGetDamageValueEx @0x55766CA7` | auto-resolve target scoring (DV:=0) |
| 5 | AoWEPACK | `TTouchAbility.CanTouch @0x55768346` | touch abilities, tactical **and** fast |

⚠ All five test `id 1` only — Floating (`0x3B`) and WindWalking are not covered by any of them.

**3b. Two-way "same altitude" — a different rule, not copied** (incidental melee, not deliberate
attacks): `CombatTE.TCombatMoveTE.ExecuteDefaultMove @0x00408749` (the free/opportunity swing when a
unit moves past an enemy) and `TTacticalCombatUnitHS.CanMoveOn @0x00420BE9` (zone-of-control move-cost
surcharge).

**3c. The hard gate — `MeleeMoveTC`, and why the cursor alone is not enough.**
`TTacticalCombatUnitHS.MeleeMoveTC @0x00422CD8` is the single creation point for every deliberate
tactical melee (exactly two callers: the AI's `EvalBattle @0x0041AB74`, the player's
`MoveSelectedRoute @0x0041E1E6`; and it is the sole caller of `CreateTCMeleeMoveTE @0x00409BFC`). It
contains no flying test of its own.

⚠ **The player's click path never consults the cursor decision.** `UpdateMoveCursor` only chooses a
glyph — its forbidden arm at `0x0041FABE` writes `Self+0x2C := 0x59` and `[[0x46c064]+0xC]+0x34 :=
0x100` and returns, and nothing on the click path reads either field:

```
TCombatUnitSelectionControl.MoveUnits @0x0041E280      no cursor/validity test anywhere
  -> MoveSelectedRoute @0x0041E01C                     call @0x0041E323
    -> MeleeMoveTC @0x00422CD8                         call @0x0041E1E6, attackerHS+0x34 == -1
      -> CreateTCMeleeMoveTE @0x00409BFC
```

So for **Flying**, vanilla gets away with cursor-only enforcement because nothing ever hands the
player a legal-looking route to an illegal target — but a *modded* gate that refuses only at the
cursor leaves the left-click working. That is exactly the hole Panic fell through (user-reported
2026-09-12, fixed by the `meleemove` hook below). **Any future "attacker may not initiate melee" rule
must gate `MeleeMoveTC`, not just the cursor.**

### Panicked `0x6C`

A `TDurationAbility` (no owner — so Dispel Magic cannot strip it), applied on a Cause Fear
(`0x33`) hit. Its only mechanical effect is a **−80 morale value**, which lands the unit in the terrible
morale band (see `01-combat-maths.md` for the morale table). **Works on heroes too** (checked
2026-08-31): the apply path tests `IsClass(target, TCombatUnit)` — "is this a unit at all," not
"unit-vs-hero" — and all six gates read via the item-aware `VMT+0xA8`/`+0x148`, which for a hero
checks the hero's own set first (independently confirmed: the −80 morale penalty already reads `0x6C`
the identical way). ⚠ `Fearless 0x43` blocks Cause Fear outright — a hero that never panics probably
has Fearless, not a defect (see the Leadership-IV-grants-Fearless feature below, which relies on this
same fact). ⚠ The project's general "units cache, heroes recompute live" caution does not apply here —
these gates read ability **presence**, not a cached stat.

⚠ **Panicked has no timer.** `PassiveAb.TPanickedAbility.Create` writes duration **mode 3** at
`0x557BA7EE` (`mov byte ptr [esi+0x28], 3`) = "entire combat", byte-identical to vanilla (checked
2026-09-09). `TDurationAbility.NewTurn @0x55764D30` gates on `[+0x28] == 1` and `NewCombatTurn
@0x55764D8C` on `== 2`, so neither ever ticks it down; only `CombatDone @0x55764E00` — gate
`(mode−2) < 2` unsigned, i.e. modes 2 and 3 — removes it, at battle end. So in vanilla the *only*
mid-battle exits are Healing (`THealingAbility.HealUnit @0x5576C41C`) and Remedy. **Damage now
clears it too** — see the next section, which also makes scope decision 5 below ("ranged
deliberately not gated") near-moot: a panicked unit that gets shot stops being panicked.

### The patch — six hooks

The first five gated sites begin with **`BA 01 00 00 00` (`mov edx,1`)** — five bytes, so an
`E9 rel32` hook displaces exactly one instruction. All verified `.reloc`-free before patching.

| site | module | hook VA | cave VA (size) | forbidden target |
|---|---|---|---|---|
| `cursor` | AoWTCPCK | `0x0041FA7F` | `0x00438300` (44 B) | `0x0041FABE` (the same "no" cursor as pointing at your own unit) |
| `ai` | AoWTCPCK | `0x00415478` | `0x00438340` (41 B) | `0x004158AF` (AI skips this candidate) |
| `freeswing` | AoWTCPCK | `0x00408749` | `0x00438380` (44 B) | `0x0040880E` (no free swing) |
| `meleemove` | AoWTCPCK | `0x00422CE8` | `0x004383C0` (35 B) | `0x00422D60` (`Result := False`, order never created) |
| `autoresolve` | AoWEPACK | `0x55766B75` | `0x55828000` (40 B) | `0x55766B9B` (`xor eax,eax` → 0) |
| `touch` | AoWEPACK | `0x5576833D` | `0x55828040` (40 B) | `0x55768363` (`xor eax,eax` → 0) |

⚠ **Site order in `SITES` is load-bearing.** `cave_va()` numbers slots by a site's index *within its
file*, so `meleemove` had to be appended after `freeswing`; inserting it earlier renumbers
`cursor`/`ai`/`freeswing` and every installed site reports `state=foreign`.

⚠ **Attacker/target register mapping is easy to get backwards and differs per site** — `cursor`:
attacker `[ebp-0x10]→+0x1C`, target `[ebp-0x14]→+0x1C`; `ai`: attacker `[ebp+0x14]`, target
`[ebp+0x10]`; `freeswing`: attacker `[ebp-0x10]→+0x1C` (the stationary unit), target `[ebp+8]→[-4]→+0x1C`
(the mover); `autoresolve`: attacker `ESI`, target `EDI` (confirmed from the prologue and the sole
caller `fcPrefetchCombatCommands`); `touch`: attacker `EDI`, target `ESI` — the **mirror image** of
`autoresolve` (`CanExecuteMelee` does `MOV EDI,ECX; MOV ESI,EDX`; `TTouchAbility.CanTouch` does
`MOV ESI,ECX; MOV EDI,EDX`). Read each prologue; never pattern-match the flying test's own load.

Cave shape (`cursor` shown):

```asm
push eax / push ecx / push edx
mov  eax, [ebp-0x10]        ; attacker HS -> its TCombatUnit
mov  eax, [eax+0x1c]
mov  edx, 0x6C               ; Panicked
mov  ecx, [eax]
call dword ptr [ecx+0xa8]    ; GetAbilityEnabled
test al, al
pop  edx / pop ecx / pop eax  ; pops do not touch flags
jnz  forbidden
mov  edx, 1                  ; the displaced instruction
jmp  <resume>
forbidden:
jmp  <forbidden-target>
```

⭐ **Each cave repeats the vanilla flying test's own object-load verbatim, only the ability id
changes** — if the vanilla test could safely reach `+0xA8` on that object, so can this one. PIC:
`jmp`/`call rel32` + register-indirect only; EAX/ECX/EDX are caller-saved under Delphi convention,
EBX/ESI/EDI/EBP preserved (matters at the two AoWEPACK sites where they're live across the hook). No
cave draws RNG. Cave space: AoWTCPCK `CODE` has a 190 912-byte zero run from `0x00438240` to
`0x00466C00` (`0x00438100`–`23F` already claimed by the facing/shield work); allocated from `0x00438300`.

`meleemove` is the one site with a different shape, for two reasons — it displaces **six** bytes, and
its resume target reads EAX:

```
00422CE4  mov byte ptr [ebp-9], 0   ; Result := False   -- runs BEFORE the hook
00422CE8  mov eax,[ebp-4]           ; \ the displaced pair (6 B, not 5)
00422CEB  mov eax,[eax+0x1c]        ; / EAX := attacker's TCombatUnit
00422CEE  call 0x402544             ; GetPlayer -- READS EAX
...
00422D60  mov al,[ebp-9] / mov esp,ebp / pop ebp / ret
```

```asm
mov  eax, [ebp-4]            ; the displaced pair, re-run at the top of the cave
mov  eax, [eax+0x1c]
push eax                     ; resume target 0x00422CEE needs EAX intact
mov  edx, 0x6C
mov  ecx, [eax]
call dword ptr [ecx+0xa8]
test al, al
pop  eax                     ; pop does not touch flags
jnz  forbid
jmp  0x00422CEE
forbid:
jmp  0x00422D60
```

The hook is therefore `E9 rel32` + **one `0x90`**. Jumping to `0x00422D60` returns False with no
cleanup: `[ebp-9]` is already 0 and nothing has been allocated. `MoveSelectedRoute` already handles a
False return (`test al,al / je 0x41e279` → plain exit) — the same path vanilla takes when the token
control refuses — so **no new code path is created**. EDX was spilled to `[ebp-8]` at `0x00422CDE`, so
ECX/EDX hold nothing live at the hook. The `.reloc` in this window sits at `0x00422CF7` (the imm32 of
`mov eax,[0x46e8d4]` at `0x00422CF6`), clear of the displaced `0x00422CE8..0x00422CEE`.

⚠ **The script's backup gate had to be fixed to add this site** (2026-09-12). `--apply` over a file
already carrying the other five would have minted a `.pre-panicnomelee` snapshot of the *patched*
bytes — the exact `CLAUDE.md` trap. It now snapshots only when **every** site in that file reads
vanilla, and says so otherwise.

### Scope decisions (settled 2026-08-31)

1. **Free/opportunity swings — blocked** (`freeswing`).
2. **Touch abilities — blocked**, placed inside the `side(attacker)!=side(target)` arm, so **friendly
   touch abilities are unaffected — a panicked healer still heals.** Charm/Seduce covered transitively
   (their `CanTouch` calls the base). ⚠ `TSelfDestructAbility.CanTouch` does not call the base and
   carries no flying gate in vanilla either — a panicked unit can still self-destruct.
3. **Enforcement goes one step beyond vanilla** — cursor + AI + auto-resolve + a hard gate. Vanilla's
   cursor-only shape was not enough; see 4.
4. **`MeleeMoveTC` hard gate — ADDED 2026-09-12** (declined 2026-08-31 "still available if a hole
   turns up"; the hole turned up). User-reported: the panicked unit showed the "blocked" cursor but a
   left-click still launched the attack, because `MoveUnits`/`MoveSelectedRoute` never read the cursor
   decision. ⚠ **The `cursor` and `ai` hooks stay** — `cursor` is what tells the player why the click
   does nothing, and `ai` stops the tactical AI scoring a move the gate will refuse (an activation
   loop risk).
   **Accepted side effect: a panicked unit can no longer smash walls or gates**, since wall-smashing
   also runs through `MeleeMoveTC` (`attackerHS+0x34 == -1` with a wall on the destination hex). This
   matches what the `cursor` hook already displayed — it tests the attacker only and never looks at
   the target's type, so it already showed "blocked" when a panicked unit pointed at a wall. No wall
   exemption wanted.
5. **Ranged — not gated**, out of scope by the wording; a panicked archer keeps shooting. ⚠ Largely
   moot since 2026-09-09: damage clears Panic, so a panicked archer that is being shot at loses the
   status anyway (`build_panic_cleardamage.py`, next section). Re-affirmed as out of scope then.
6. **`Ability.pfs` text still to do** — record 118 ("Panicked") wants the restriction appended (Cause
   Fear is record 61).

### What this does not do

No change to any damage, to-hit or morale number. No effect on the raze combat predictor (it has no
concept of panic). Panic is invisible to Floating/WindWalking edge cases, same as the flying rule it
copies.

### Revert

```bash
python "Modding Resources/build_scripts/build_panic_nomelee.py" --undo
```

Restores all six hook sites (five `mov edx,1`, one six-byte `mov eax,[ebp-4] / mov eax,[eax+0x1c]`),
zeroes the six caves, touches no backup. Round-tripped byte-identical 2026-09-12.

### ✅ Confirmed in game, 2026-09-13

The click-to-attack hard gate holds: a panicked attacker gets the "no" cursor **and** the left-click
does nothing, which is the hole the 2026-09-12 `meleemove` hook was built to close. Retaliation is
intact. Shipped in the 2026.09.13 release (`AoWTCPCK.dpl` md5 `d1afa960a834`).

**Accepted side effect, recorded so it is not re-reported as a bug: a panicked unit can no longer
smash walls or gates.** Wall-smashing runs through `MeleeMoveTC` too, so the same gate refuses it.
A *non*-panicked unit smashes walls normally. `UpdateMoveCursor` keys on the target's type rather
than the attacker's status, so the cursor already showed "blocked" there in vanilla — the click now
agrees with it.

---

## Panic — cleared by any damage that lands

**Status: 🔨 APPLIED, UNTESTED (2026-09-09).** Script `build_panic_cleardamage.py` (surgical
`--undo`). Binary `AoWEPACK.dpl` only. Snapshot `backups\AoWEPACK.dpl.pre-paniccleardamage`.

**Goal:** being hit snaps a unit out of Panic. Any damage that actually lands clears `0x6C` — no
threshold, no source filter. This is the fix for "a panicked unit stays panicked for the whole
battle no matter what you do to it", which the duration-mode finding above explains: Panicked is
mode 3, so nothing ticks it down.

A miss never reaches the patched code (the strike only calls `DoDamage` on a hit) and a
fully-absorbed hit arrives with EDX = 0, so "only a landed blow clears it" falls out of the hook
site itself and needs no test of its own beyond `test ebx,ebx / jle`.

### One hook covers everything

`AoWE.TCombatObject.ExecuteDamage @0x55726C58`, VMT slot `+0x124`. A scan of `AoWEPACK.dpl` finds
the dword `0x55726C58` at exactly four addresses, all of them a `+0x124` slot:

| class | VMT | `+0x124` |
|---|---|---|
| `TCombatObject` | `0x557158EC` | `0x55715A10` |
| `TCombatUnit` | `0x55715A94` | `0x55715BB8` |
| `TCombatWall` | `0x55715C40` | `0x55715D64` |
| `TFastCombatUnit` | `0x5571D4BC` | `0x5571D5E0` |

One body inside this DLL — so the single hook covers melee (normal / round / retaliation /
free swing), ranged, breath, touch, every `TDamageCA` and spell damage path, self-destruct, Command
CA damage, the Burning and Decay combat ticks, **and auto-resolve** (`TFastCombatUnit` overrides
neither `ExecuteDamage` nor `GetAbilityOwner`). `AoW.exe` and `aowInt.dpl` hold no reference at all.

### ⚠ `AoWTCPCK.dpl` **does** override `+0x124` — and a same-module scan cannot see it

`AoWTC.TTacticalCombatUnit` (VMT `0x00412B4C`, instsize `0x68`) carries `+0x124 = 0x00420250`, its
own `ExecuteDamage`:

```
00420250  push ebp / mov ebp,esp / add esp,-0x4c
00420256  jmp  0x437FE0        <- build_facing_retal.py cave; stores [ebp-4]=eax, [ebp-8]=edx
0042025D  push ebp / call 0x420048 / pop ecx
00420264  mov  edx, [ebp-8]    ; the ORIGINAL damage, unmodified
00420267  mov  eax, [ebp-4]    ; the object
0042026A  call 0x40256C        ; -> AoWEPACK.dpl!AoWE.TCombatObject.ExecuteDamage  (the hook)
```

**Coverage is intact.** The override is a wrapper that delegates with the damage still in EDX, so
the patched body runs on the tactical path too, and there is still no second binary to keep in
lockstep — `0x0040256C` is the plain import thunk `FF 25 B8 E7 46 00` into `AoWEPACK.dpl`.

⭐ **The reusable lesson: a cross-module override is invisible to a same-module dword scan.** The
original survey searched `AoWEPACK.dpl` for the dword `0x55726C58` and could not have found this —
AoWTCPCK's slot holds a *local* address. To find one, enumerate the other module's VMTs by their
self-pointer at `VMT−0x40` and read the slot directly. Done here for all 78 AoWTCPCK VMTs:
`TTacticalCombatUnit` is the only class occupying `+0x124`, and its `+0xB8` resolves to
`AoWEPACK.dpl!AoWE.TCombatUnit.GetAbilityOwner` (not overridden either). ⚠ The `+0x124` hits at
`0x00402124` in that scan are `HSEPack.dpl!HSEngine.TMultiHexMO.GetMostFrequentMapFieldTerrainType`
— a different class family, correctly discarded.

Vanilla bytes `53 56 57 55 8B DA` (`push ebx; push esi; push edi; push ebp; mov ebx,edx`) — six
bytes to a clean boundary at `0x55726C5E` (`mov esi,eax`), replaced by `E9 rel32` + one `90`.
**At entry EAX = the victim combat object, EDX = the requested damage.**

### The cave — `0x55829000`, 58 bytes

```asm
push ebx / push esi / push edi / push ebp
mov  ebx, edx                 ; the displaced prologue, verbatim
test ebx, ebx
jle  .out                     ; 0 damage (fully absorbed) leaves Panic alone
push eax
mov  ecx, [eax]
call dword ptr [ecx+0xB8]     ; GetAbilityOwner -> EAX, nil for walls
test eax, eax
jz   .pop
push eax
mov  edx, 0x6C
mov  ecx, [eax]
call dword ptr [ecx+0x4C]     ; GetAbSet(0x6C) -> AL, presence pre-check
test al, al
pop  eax
jz   .pop
mov  edx, 0x6C
mov  ecx, [eax]
call dword ptr [ecx+0x98]     ; RemoveAbility
.pop:
pop  eax
.out:
jmp  0x55726C5E
```

Stack balanced on all four exits; `pop` does not touch flags; EBX carries the damage across the
calls and all three callees preserve EBX/ESI/EDI/EBP under the Delphi convention. PIC: rel32 +
register-indirect only, no absolute memory operand.

⭐ **`TDurationAbility.CombatDone @0x55764E00` is the vanilla model, instruction for instruction** —
`mov eax,<combat object>; mov edx,[eax]; call [edx+0xB8]` to reach the ability owner, then
`mov edx,<id>; mov ecx,[eax]; call [ecx+0x98]` to remove. This cave is that plus two guards vanilla
does not need in its own context. The precedent is not a distant one: `CombatDone` is **the routine
that removes Panicked at battle end**, so the cave does the engine's own thing to the same ability
id, only earlier.

- **`GetAbilityOwner` (`+0xB8`), not `GetAbilityEnabled` (`+0xA8`).** `+0xA8` returns false both for
  "disabled" and for "no owner", and the `+0xB0` follow-up is not nil-guarded. Testing `+0xB8`'s
  result is also what makes walls safe with **no `IsClass`**: `TCombatObject.GetAbilityOwner
  @0x557268D0` is `xor eax,eax / ret` and `TCombatWall` inherits it (live
  `TCombatWall+0xB8 = 0x557268D0`). `TCombatUnit.GetAbilityOwner @0x55725000` is
  `mov eax,[eax+0x4C] / ret`, which can itself be nil — hence the `test eax,eax`. The two `0x4C`s
  in this feature cannot collide: `TCombatObject` has instsize `0x4C` (`[VMT−0x1C]`), so it has no
  `+0x4C` *field* to misread, and the cave's `+0x4C` is a VMT slot on the **owner**.
- **The `GetAbSet` (`+0x4C`) pre-check** exists for cost, not correctness. `ExecuteDamage` is the
  hottest path in combat and also runs inside auto-resolve batch simulation.
  ⚠ **The cost it avoids is an allocation, not a `Changed()` recompute** — `Changed()` would not
  fire. `TAbilityOwner.RemoveAbility @0x5574F5EC` gates it on `Remove`'s result
  (`5574F60E mov ebx,eax / test bl,bl / je 0x5574F61E`, skipping the `call [edx+0x90]`), and
  `TDurationAbility.Remove @0x557650D8` returns 0 on the nil-data path (`0x55765119 xor ebx,ebx`).
  What that path *does* still do is call `TAbility.SetAb(owner, 0x6C, 0)` @`0x5574E718` →
  `TCustomAbilityList.SetAbSet @0x5574E0BC`, whose `id >= AbCount` arm (`cmp edx,[eax+0xC] / jae`)
  falls through to `SetAbCount(0x6D)` @`0x5574E0F8` and grows the bitset — `System.@ReallocMem`
  @`0x5574E138` plus a `@FillChar` zero-fill whenever the byte count moves. Without the pre-check
  every unit in the game takes a bitset realloc on its first damaging hit.
  `TCustomAbilityList.GetAbSet @0x5574E0E0` is `cmp edx,[eax+0xC]` / `bt [eax+8],edx` —
  one virtual call, an id-indexed bitset, no allocation. Same predicate `TAbilityOwner
  .TriggerCombatDone @0x5574FEC4` uses. `THero.GetAbSet @0x55788104` overrides it with a tail call
  to the same body, so it stays **self-only** — correct, because `0x6C` can never come from an item.
- **Removal primitive:** `owner->vmt[0x98](owner, 0x6C)` → `TAbstractUnit.RemoveAbility @0x5577F6EC`
  → `TAbilityOwner.RemoveAbility @0x5574F5EC` → `TDurationAbility.Remove @0x557650D8` →
  `RemoveAbilityData` → `Changed()`. Exactly what `THealingAbility.HealUnit @0x5576C41C` and
  `TRemedy.ExecuteSpell` already do to `0x6C`. **That chain calls `Changed()` itself, so there is no
  `build_debuffcache.py`-style stat-cache follow-up to add.** Safe when the unit is not panicked:
  `Remove` handles `data == nil`, returns false, `Changed()` is skipped. `THero` does not override
  `+0x98` (live `THero+0x98 = 0x5577F6EC`, same as `TUnit`).
  ⚠ **`+0x98` on a `TCombatObject` is `GetExperience @0x55726894`** — you must go through
  `GetAbilityOwner` first, and getting it backwards is silent.

### Ordering — already correct, and a discriminator would be wrong

Live-verified in `TStrikeCA.Execute`: `call [ebp+0x108]` (DoDamage → ExecuteDamage) at `0x55766769`
runs before the Panicked grant in the same function — **136 bytes** to the `mov edx,0x6C`
@`0x557667F1`, **151 bytes** to the `call [ecx+0xD0]` @`0x55766800` that applies it.
The hook therefore fires strictly before the grant, and Cause
Fear works unchanged. Multi-strike rounds are self-consistent: strike 2's damage clears strike 1's
grant, then re-grants. Both Terror CAs (`0x557F990C`, `0x557F977C`) apply `0x6C` and deal no damage
in the same CA. **Do not add an exemption for the applying strike** — unnecessary, and it would
break the "damage clears it" rule for the second strike of a Cause Fear round.

### Site choice: entry, not the tail

The alternative site is `0x55726CCF` (`8B C5 5D 5F 5E`, exactly 5 bytes, reloc-free, ESI = object,
EBP = post-clamp effective damage). Both sites sit in the same function body, so **coverage does not
discriminate between them** — the AoWTCPCK wrapper above delegates into the whole of it either way.
The choice turns on object lifetime alone. The tail is **not used**, because it runs after the
lethal-blow `DestroyObject` call at `0x55726CC9`, where `GetAbilityOwner` can hand back a detached
pointer. At the entry site the object is alive by construction, and the `Changed()` lands before
`SetHitPoints` rather than after `DestroyObject`.

Re-entrancy checked before finalising: `TUnit.Changed @0x55782B34` is `TAbstractUnit.Changed` plus
four `GetAbXxxAll` aggregations into `[unit+0x44..0x47]`; `TAbstractUnit.Changed @0x55780FA8` is
morale/offensive/defensive/enchanted recompute plus a `TAoWHSMap.UnitChanged` notify-event;
`THero.Changed @0x55786BDC` adds only `THeroControl.HeroChanged`. Nothing in either re-enters
`TCombatObject`.

### ⚠ Forward hazards

- **Coupled feature: `build_panic_nomelee.py`** (previous section). Independent hooks, independent
  caves (`0x55828000`/`0x55828040` here, `0x00438300`..`0x004383C0` in AoWTCPCK.dpl), independent
  `--undo`s. Deliberately **not** merged, on feature grounds rather than code grounds: that script
  *gates* permission predicates (each cave picks one of two branch targets in a "may I initiate?"
  test), this one *removes* the status as a side effect of a damage path. They are separately tunable
  — no-melee makes Panic matter, clear-on-damage makes it short, and either is wanted without the
  other — so each needs its own `--undo` and its own in-game checklist. Reverting either leaves the
  other working.
- **`build_burning_sailing.py` owns `0x55726C66`** inside this same function (`cmp ebx,0x32` →
  `0x7F`, the damage-assert ceiling), twelve bytes past the hook window. Untouched here, but any
  future widening of this hook past six bytes would eat it.
- ⚠ **`build_facing_retal.py` owns `0x00420256 → 0x00437FE0`** — inside
  `AoWTC.TTacticalCombatUnit.ExecuteDamage`, the AoWTCPCK wrapper documented above. Anything that
  rewrites that wrapper interacts with that script. This feature writes nothing in AoWTCPCK.dpl and
  only depends on the wrapper continuing to delegate with the damage in EDX.
- ⚠ **Do not relocate this hook to `0x55726CA8`.** It sits directly on the `.reloc` entry at
  `0x55726CA9`; the loader would add the rebase delta into the `E9` displacement. `.reloc` entries
  in this function: `0x55726C34`, `0x55726C6F`, `0x55726C74`, `0x55726CA9` — the six-byte window at
  `0x55726C58` is clear, and the script re-scans on every run.

RNG: no draw added, none inherited. `ExecuteDamage`, `GetAbilityOwner`, `GetAbSet`, `RemoveAbility`,
`Remove`, `RemoveAbilityData` and `Changed` are in neither the SYNC nor the RAW list;
`rng_audit.py --owners` after apply lists no site in `0x55829xxx`.

### Revert

```bash
python "Modding Resources/build_scripts/build_panic_cleardamage.py" --undo
```

Restores the six vanilla bytes at `0x55726C58` and zeroes the whole `0x55829000`–`0x558290FF`
reservation; touches no backup. Round-tripped on a scratch copy 2026-09-09 — both regions come back
byte-identical to `AoWEPACK_original_backup.dpl`.

### In-game checklist

1. **⭐ Panic a melee unit with Cause Fear, then shoot it once with an archer** — the Panicked icon
   disappears and it attacks normally next turn. This is the reported bug.
2. Cause Fear still panics — the target is Panicked *after* the hit resolves, not cancelled by its
   own damage. Test on **a unit and a hero**.
3. A two-strike Cause Fear unit: the target is still Panicked after the full round.
4. Terror (the spell) still panics an undamaged stack; panic ends on the first hit any of them takes.
5. **⭐ A lethal blow that also clears Panic** — bring a panicked unit to 1–2 HP and finish it with
   one big hit. *Right looks like:* normal death animation, no access violation, no unit vanishing
   from the wrong side, combat continues. **Why it is on the list:** `TAbstractUnit.RemoveAbility
   @0x5577F6EC` calls `AddRef` (`[vmt+0x28]`) then `Release` (`[vmt+0x2C]`), and
   `TAbstractUnit.Release @0x5577EBCC` destroys the object at zero refcount. Theory — inert, because
   an in-combat unit always holds a positive refcount, and vanilla makes the identical call from
   `TDurationAbility.CombatDone` and `THealingAbility.HealUnit`. Could not be closed statically.
6. **`Changed()` notify subscribers** — hit a panicked unit repeatedly and watch the tactical unit
   panel. *Right looks like:* no flicker, no stall, no stale value. `TAoWHSMap.UnitChanged` fires
   `TriggerNotifyEvents` on the list at `[map+0x208]`, whose handlers register at runtime and cannot
   be enumerated from the file.
7. A panicked unit that is also Burning loses Panic **when its Burning tick lands, and not when it
   misses** — statically confirmed as a design consequence (see below); confirm it is wanted.
8. Retaliation unaffected — attacking a panicked unit still draws its normal retaliation strikes.
9. Auto-resolve completes, no crash, no assert dialog, with Cause Fear and Terror on both sides.
10. Siege a city and hit walls — no crash, no "Invalid Damage Value" assert.
11. After the battle, no unit carries a stuck Panicked icon on the strategic map.
12. No regression when nobody is panicked; turn and auto-resolve speed unchanged.
13. Healing and Remedy still clear Panic.

### Closed statically — the Burning tick routes through the hook

`TBurningAbility` overrides `+0xF8` (`NewCombatTurn`) to `0x557BA3D4`, which after a `HitRole` at
`0x557BA46B` jumps into `build_burning_sailing.py`'s cave (`0x557BA479 jmp 0x5582E000`), ending
`0x5582E02F call dword ptr [ecx+0x124]` — this feature's slot. **So a landed Burning tick clears
Panic and a missed one does not**, which is the same rule as every other damage source. It stays in
the checklist only as "confirm this is wanted", not as an open question about the code path.

### Not done, deliberately

- **No ranged gate added to `build_panic_nomelee.py`** — out of scope for this run, and largely moot
  now (see that section's scope item 5).
- **`Release/Ability.pfs` record 118 ("Panicked") text not touched** — out of scope for this run. It
  still lacks both the no-melee restriction and the cleared-by-damage note.

---

## Command abilities (Seduce/Charm/Dominate) — cross-battle revert nerf

**Status: SPECULATIVE** — design/feasibility note only (2026-07-12), nothing built. Addresses Seduce,
Charm, Dominate and any future `TCommandAbility`-based mind control.

**The concern (user):** vanilla keeps a mind-controlled unit permanently once the controller survives
the battle in which control was taken — no further downside ever. Desired nerf: control should revert
**whenever the controller dies, even many turns/battles later**, not just within the same fight.

**Vanilla mechanism, as it actually is** (superseding an earlier draft of this analysis that assumed
the controller-side list persists — it doesn't): the controller's `TCommandAbility` data holds a
`TByteList` of **combat-object** ids at `data[+0x10]` — per-battle values, meaningless once combat ends.
Only the **victim** side persists across saves (`TCommandedAbilityData.ReadWrite`, holding a
back-reference to the controller at `[+0x14]`). The within-battle revert
(`ResetCommandedUnits`/`Uncommand`, detailed in the Turn Undead evil-command section above, which reuses
this exact machinery) only knows how to reach commanded units that are **objects in the active
combat** — it has no path to a unit on the strategic map. The original controlling **player** is not
stored anywhere either; `data[+0x18]` stashes only the victim's combat **side** byte, which is
battle-scoped.

**Feasibility verdict: FEASIBLE, moderate effort**, in three parts:
1. A global unit-death hook (strategic scope) that checks, for the dying unit, whether its
   `TCommandAbility` data's commanded list is non-empty.
2. A strategic-scope revert adapting `ResetCommandedUnits` — resolve each commanded unit id via the
   strategic registry (`TUnitControl.FindUnit @0x5577E948`) instead of `TCombatData.FindID`, restore
   its original owner, strip the commanded ability.
3. **Stash the original owning player at control time** — nothing in the engine stores it; the nerf
   must add a spare byte to the ability data (already serialised via `ReadWrite`, so persistence is
   close to free).

**Interaction with the rebellion/raze "converted units join the stack" feature**: same machinery.
Build the "join the stack" harvest first (winning-side conquest, respecting existing within-battle
permanence); layer this cross-battle revert on top.

⚠ **Cross-feature coupling with the Turn Undead evil-command feature above**: that feature already
extends `CommandAbilityIDs` to a fourth entry (`0x88`) and fixes the strip-list to six loops. Any future
build of this nerf must account for that fourth id and its own commanded-status pair (`0x89`) — a
generic "walk every `TCommandAbility` controller" implementation should already be safe if it uses the
same 4-entry array `build_turnundead_evilcommand.py` installed at `0x5583225C`, rather than the vanilla
3-entry `CommandAbilityIDs @0x558E84E4`.

---

## Dispel Magic — the touch ability (`0x3C`)

**Status: 🔨 APPLIED, UNTESTED (2026-08-09)** — level cap raised III→V. Script `build_dispelmagic5.py`
(surgical `--undo`). Binary `AoWEPACK.dpl`, backup `AoWEPACK.dpl.pre-dispelmagic5` (undo is the
preferred revert path). Class `AoWE.TDispelMagicAbility`, VMT `0x55721D78`, descends from
`TTouchAbility` (used by touch, not at range).

⚠ **The cap is not the base `TMultiLevelAbility` field `[+0x28]`** — Dispel Magic hard-codes 3 in two
`cmp`s (`CanExpand @0x5576D163`, `Expand @0x5576D1D0`) and keeps its level at
`TDispelMagicAbilityData+0x0D` (the base class's `+0x0C` is repurposed here as the per-turn *enabled*
toggle). Patching `[+0x28]` would have done nothing.

### What it does

Strips enchantments off the touched unit, rolling each independently. Two execution paths — strategic
(`TDispelMagicAbilityTE.Execute @0x5576D744`, rolls at execute time) and tactical
(`TDispelMagicCA.Generate @0x5576CC18` rolls at Generate time; `Execute` only applies the stored id
list; **combat only, also kills summoned units** — see below).

```
mana = GetDispelMana(dispeller) = GetLevel(dispeller)*10 + 20      ; 30/40/50 vanilla I-III
for each enchantment on target:
    chance = clamp( 10*level - 10*R + 70, 10, 90 )   ; R = ench[+0x14], dispel resistance
    if Random(100) < chance: dispel it
```

`R` defaults to 10 (a flat, effectively-undispellable 10%) and is overwritten per-spell at a uniform
`+0x5D` inside each `ExecuteSpell` from a hard-coded constant in that spell's `Create`. ⚠ **`R` is not
serialised** (`TSpell.ReadWrite` writes only mana/upkeep/research/sphere/tier) — **dispel resistance
cannot be retuned from `Spells.pfs`, it is a DLL patch.**

| R | chance vs Dispel I/II/III (vanilla) | spells |
|---|---|---|
| 3 | 50/60/70% | Bless, Dark Gift, Enchant Weapon, Fury, Haste, Stone Skin |
| 4 | 40/50/60% | Concealment, Fire Aura, Free Movement, Healing Water, Holy/Unholy Champion |
| 5 | 30/40/50% | Liquid Form, Wind Walking |
| 6 | 20/30/40% | Water Walking |
| 10 | 10/10/10% | Cosmetic Surgery (the floor) |

⚠ Only the `UnitSpells.*` rows above are verified; `R` was also read off several `CitySpells`/`Dungeon`/
`CombatSpells` classes but not confirmed to mean the same thing there (standard disp8-aliasing caveat).

**Summoned units die on dispel** (combat only): if the target had ability `0x9B` "Summoned" and loses
it, the dispeller deals damage equal to the target's **current hit points** — an instant kill credited
to the dispeller (the XP goes to them). No equivalent branch exists in the strategic execute path.

**Targeting vs effect asymmetry**: legality (`CanDispelEnchantment`) requires the target carry at least
one enchantment belonging to *someone else*. But `ListEnchantments` enumerates **every** enchantment
with no owner filter, and every one is rolled — **cleansing an enemy curse off your own unit also rolls
to strip your own buffs from it.** Verified in both execution paths.

**Once per turn** via `SetEnabled`; `NewTurn` re-enables. The separate known bug that an item-granted
Dispel Magic is infinitely usable (one of only two abilities whose `SetEnabled` writes to the unit's own
record) stands unchanged, recorded elsewhere.

### AS BUILT — cap III → V

Cheap because Dispel Magic has no per-level value ladder — everything flows through
`GetDispelMana = level*10+20`, so IV/V give strength 60/70 for free in all three consumers; skill cost
is a flat 5/level, cap-independent (contrast Leadership, whose fixed-size bonus tables had to be
relocated).

| # | site | change |
|---|---|---|
| 1 | `CanExpand @0x5576D163` | `cmp eax,3` → `5` |
| 2 | `Expand @0x5576D1D0` | `cmp byte [ebp+0xD],3` → `5` |
| 3 | `GetLevelName @0x5576CF61` | default arm's existing 5-byte `jmp 0x5576CFF8` retargeted to the cave |
| 4 | cave `0x55821000` (88 B, exclusive reservation `0x55821000`–`13FF`) | level 4→`" IV"`, 5→`" V"`, else falls through to `0x5576CFF8` |

| enchantment R | I | II | III | **IV** | **V** |
|---|---|---|---|---|---|
| 3 | 50 | 60 | 70 | **80** | **90** |
| 4 | 40 | 50 | 60 | **70** | **80** |
| 5 | 30 | 40 | 50 | **60** | **70** |
| 6 | 20 | 30 | 40 | **50** | **60** |

V against an R=3 enchantment hits the 90% clamp — V is the effective ceiling; a VI would add nothing
against the common buffs. Cave placed at `0x55821000` deliberately, away from the crowded `0x5580Exxx`
pocket (claimed by combat-log/true-seeing/invis features even where it currently reads zeros).

**Verified without the game:** all four sites byte-checked post-apply; `--undo` round-trips to vanilla
and re-applies; a whole-file diff against the backup shows exactly the intended byte runs and nothing
else.

⚠ **A third-party dependency claim was traced and does NOT apply here.** A fellow modder's equivalent
patch declares a hard requirement on a separate "inherent level" fix, reasoning that Dispel Magic's VMT
`+0x94` needs repointing or purchased levels get silently discarded by `UpdateDefaultAbilities`. Traced
on this install: `TDispelMagicAbility+0x94` is the base `TAbility.GetInherentLevel`, a constant-0
return; `UpdateDefaultAbilities` is already hooked here by the Leadership disable-bug fix (see below),
whose cave dispatches `vmt[0x94]` for both the template and the destination — with a constant 0 on both
sides the discard branch (`inherent(template) > inherent(dest)`) is unreachable, so the purchased level
is left alone. (Two other claims from the same source were also re-measured and found wrong for this
install: `ExpandCost` here is a flat **5**, not "1"; and the claimed cave address `0x5580E680` sits in
this project's contested pocket.) ⚠ If in-game testing ever shows purchased Dispel Magic levels
reverting, the `+0x94` repoint is the first thing to re-examine — the static argument is sound but
unexercised in play.

### Revert

```bash
python "Modding Resources/build_scripts/build_dispelmagic5.py" --undo
```

Surgical: restores the three sites, zeroes the cave, touches no backup.

### In-game checklist

Cast Dispel Magic IV and V against enchanted targets and confirm the strength/chance matches the table
above; confirm the level-up dialog and unit card offer/read "Dispel Magic IV/V"; confirm no regression
to I–III.

---

## Lifesteal on Round Attack

**Status: ✅ CONFIRMED WORKING (2026-07-08)** — offensive strikes (normal melee + round attack), both
LifeStealing (`0x76`) and Dark Gift (`0xA9`) lifesteal, user-validated in-game. Script
`build_lifesteal_roundattack.py` (no `--undo`). Binary `AoWEPACK.dpl`, backup
`AoWEPACK.dpl.pre-lsround` (a re-tune snapshot, not the revert path — see Revert below).

### Ability ids — corrected

⚠ **`0x77` is Entangle Strike, not "Death Strike."** It applies **Entangled `0x5E`**, not "Cursed."
Death Strike is a different ability (`0x12`); Cursed (`0x5D`) is inflicted by the Death damage type
(`0x20`) via the **effects word `CA+0x13`** — an entirely different mechanism from the `CA+0x18` strike
flags this feature uses. (Both this project's own build script header and an earlier pass of this doc
repeated the wrong name in a reference table at the bottom while correctly identifying it earlier in
the same text — the corrected mapping above is the only one to use.)

### The combat-strike model

A melee hit is a `TStrikeCA`. **`TStrikeCA.Generate @0x557668B4`** is the planning pass — resolves
to-hit/damage and sets on-hit **effect flags** in `CA+0x18`, based on the *attacker's* abilities; it
runs for every strike (normal, round, retaliation). **`TStrikeCA.Execute @0x55766738`** is the apply
pass — re-reads those flags. Registers at the effect section: `EBX`=CA, `EDI`=attacker, `ESI`=target.

| field | meaning |
|---|---|
| `CA+0x0C` bit `0x01` | defensive/retaliation flag (0 = offensive) |
| `CA+0x10` (byte) | strike damage; 0 = the hit did nothing — effects are inherently hit-gated |
| `CA+0x15` (byte) | strike result, written in `Execute` — **the trap**, see below |
| `CA+0x18` (byte) | effect flag bits |

How the engine's own working effects are wired (the template this feature copies):

| attacker ability | flag set in | `CA+0x18` bit | applied |
|---|---|---|---|
| Cause Fear `0x33` → Panicked `0x6C` | Generate | `0x01` | flag-block @`0x557667CF`, gate = flag only |
| Entangle Strike `0x77` → Entangled `0x5E` | Generate | `0x04` | flag-block @`0x55766806`, gate = flag only |

Live bit map of `CA+0x18` after this mod: `0x01` Cause Fear→Panicked (vanilla) · `0x02` vanilla
LifeStealing flag — **still set by `TMeleeRound.CreateStrikeCA` but never read any more** (this mod's
`jmp 0x5580DC80` @`0x5576678C` bypasses the vanilla consumer block — vestigial, not a signal to reuse)
· `0x04` Entangle Strike→Entangled · **`0x08` = this mod's LifeStealing** (set @`0x5580DCE9`, healed
@`0x5580DC80`) · **`0x10` = this mod's Dark Gift** (set @`0x5580DD00`, healed @`0x5580DC9F`). Both mod
bits gate on `¬CA+0x0C bit0` — offensive strikes only.

### Root cause — why plain lifesteal misses round attack

Vanilla LifeStealing's flag (`CA+0x18` bit `0x02`) is set **only** by the normal-melee builder
`TMeleeRound.CreateStrikeCA @0x55767E68` — round attack goes through the *global* `CreateStrikeCA
@0x557665E4` (called from `TRoundAttackAbility.fcExecuteCombatCommand`), which never sets it. Worse, the
heal itself sits in `Execute`'s **first block**, gated on the strike-result byte `CA+0x15`, which reads
0 in `Execute` for a round-attack strike (it resolves before that block runs) — so the block is skipped
entirely regardless of the flag. **Fix: stop fighting it, wire lifesteal exactly like Cursed** — a fresh
flag set in Generate, applied in a plain flag-block with no `CA+0x15` gate.

### Implementation

Two position-independent caves, two redirects, free bits `0x08`/`0x10`.

**Cave A — set the flags in Generate** (hook `0x557668E2`, inside Generate's `if CA+0x10!=0` block,
already hit-gated; original `BA 33 00 00 00` → `E9 <rel32>`):

```asm
test byte [ebx+0x0c], 1     ; offensive-only gate
jnz  _replay                ;   defensive strike -> set no flag
mov  edx, 0x76 / mov eax,edi / mov ecx,[eax] / call [ecx+0xa8]   ; GetAbilityEnabled(LifeStealing)
test al,al / jz _dg
or   byte [ebx+0x18], 0x08
_dg:
mov  edx, 0xA9 / mov eax,edi / mov ecx,[eax] / call [ecx+0xa8]   ; GetAbilityEnabled(Dark Gift)
test al,al / jz _replay
or   byte [ebx+0x18], 0x10
_replay:
mov  edx, 0x33               ; replay the displaced instruction
jmp  0x557668E7
```

**Cave B — heal in Execute** (hook `0x5576678C`, Execute's effect-section start; original
`80 7B 15 00 74 3D` (6 B) → `E9 <rel32> 90`):

```asm
test byte [ebx+0x18], 0x08
jz   _dg
mov  eax,edi / mov edx,[eax] / call [edx+0x88]   ; GetHitPoints
add  eax, 4                  ; LS_HEAL -- LifeStealing (0x76); imm byte @0x5580DC92
mov  edx,eax / mov eax,edi / mov ecx,[eax] / call [ecx+0x8c]   ; SetHitPoints (clamps)
_dg:
test byte [ebx+0x18], 0x10
jz   _done
... identical heal, +3 ...   ; DG_HEAL -- Dark Gift (0xA9); imm byte @0x5580DCB1
_done:
jmp  0x557667CF               ; SKIPS the old CA+0x15-gated first block entirely -- no double-heal
```

⚠ **The two heals are INDEPENDENT and are no longer equal.** Current constants:
`LS_HEAL=4; DG_HEAL=3` (`build_lifesteal_roundattack.py`). `0x76` LifeStealing and `0xA9` Dark Gift
are different abilities that merely share this cave — do not "make them consistent". Both were 2
before the 2026-08-24 general DAM/HP ×2 pass, which doubled the flat drain heal with the rest of the
HP scale; Dark Gift then came back to **3** on 2026-09-14 (owner ruling, so the card reads
"+3 Dam, and +3 lifestealing"). Any doc still saying "heal amount is 4" means LifeStealing only.

Re-tuning either one is a single `add eax,N` immediate byte — `0x5580DC92` (LS) and `0x5580DCB1`
(DG) — and `add eax, imm8` keeps its length for 1..127, so `cave_lsgen` at `0x5580DCD0` never moves.
`--apply` rewrites the cave in place: `CAVE1_VARIANTS` regenerates the body across ls/dg ∈
{1,2,3,4,6,8} so a body carrying the OLD constants verifies as ours rather than aborting.

⚠ **`--apply` mints no `.pre-lsround` on a re-tune** (gate added 2026-09-14). The old
`if not os.path.exists(backup)` test minted one from an already-patched DLL — it sat in
`Ziggurat\backups\` one byte from the live file, named as though it predated the feature, and was
deleted. The gate is now a positive test that every site still reads its pre-patch bytes.

Safe because the heal calls and `GetAbilityEnabled` are Delphi register methods preserving
EBX/ESI/EDI/EBP, so CA/target/attacker survive into the following flag-blocks; `SetHitPoints` clamps,
so no overflow. **Result: LifeStealing and Dark Gift heal on all offensive strikes (normal + round
attack), not on defensive/retaliation, not on ranged** (a different CA class whose `Execute` this cave
never runs in). Caves at `0x5580DC80`/`0x5580DCD0`.

### Revert

⚠ **No `--undo` exists, and copying back `.pre-lsround` is not the revert path** (this project's
standing rule — later layers would be destroyed). Manual surgical revert: restore the 6-byte Execute
hook @`0x5576678C` to `80 7B 15 00 74 3D` and the 5-byte Generate hook @`0x557668E2` to
`BA 33 00 00 00`, then zero the two caves at `0x5580DC80`/`0x5580DCD0`. Re-tuning the heal amount
(`LS_HEAL`/`DG_HEAL`) does not need any of this — it is two `add eax,N` immediate bytes, editable and
re-appliable directly.

### The undeveloped defensive/retaliation variant

**Status: SPECULATIVE — documented, never applied.** `DEFENSIVE=False` is the current, shipped setting.
Making retaliation strikes lifesteal too is a one-line change: Cave A's `test byte[ebx+0x0c],1 / jnz
_replay` pair is the *only* thing excluding defensive strikes (Cave B already heals whoever the current
strike's attacker is, which for a retaliation strike is the retaliating unit — exactly right). Three
equivalent routes: flip the script's `DEFENSIVE` switch and re-`--apply` (a real re-apply, cave bytes
change); hand-edit the asm and reassemble; or, if only the offensive version is already installed,
NOP the 6 gate bytes in the live cave (`F6 43 0C 01 75 2E` → six `90`s — confirm the displacement byte
at the target install before poking, it is build-specific). Effect would be: LifeStealing/Dark Gift
units heal both on hits they land and hits they land while retaliating (stacks — a unit that both
attacks and retaliates in a round heals on each), still hit-gated, still not ranged. Caveat for whoever
builds it: strong on tanky, high-retaliation units; consider a smaller defensive heal value; a **pure
defensive-only** variant (heal on retaliation, not on attack) needs the gate polarity flipped
(`jnz`→`jz`), which would also remove round-attack lifesteal — the opposite of this feature's point.
Splitting LifeStealing and Dark Gift onto independent offensive/defensive gates needs the shared gate
split into two.

---

## Leadership

Five source records, kept as five distinct sections because they are five distinct events, not
duplicates of each other: **A** is the original investigation (three features, one of which stayed
speculative); **B** is the root-cause analysis and fix for a data-loss bug found along the way; **C** is
the as-built 4-level ability plus an aura-refresh fix; **D** is a later feature (Leadership IV grants
Fearless) built on top of C's aura machinery; **E** makes the aura skip its own holder. All addresses are `AoWEPACK.dpl` preferred-base VAs
(base `0x55700000`); every cave below is position-independent. Leadership ability id `0x2E`.

### A. Origin investigation — three features

**Status: mixed** — Feature 1 shipped on 2026-09-09 (`🔨 APPLIED, UNTESTED`) and is now a feature in
its own right rather than an investigation note; Feature 2 was superseded by the shipped 4-level
version (C, below); Feature 3 became its own confirmed fix (B, below).

**Shared ability model:** abilities are flyweights (one `TAbility` per id, held by the global
`TAbilityControl`). Per-owner state splits into an **enabled bitset** (owner `VMT+0x4C`/`+0x50`/`+0x14C`)
and an **ability-data linked list** (head `owner+0x10`, one `TxxxAbilityData` record per id).
`TLeadershipAbilityData`: `+0x0C` own/inherent level, `+0x0E` ability id, `+0x10` external-source
(borrowed) level, `+0x14` external-source name. `TLeadershipAbility.GetLevel @0x557661C4` =
`max(own, borrowed)`; `GetInherent @0x55766384` = `data && data[+0x0C]!=0` — the engine's own test for
"genuinely mine," central to Feature 3/B below.

#### Feature 1 — per-race probability gate on hero level-up ability offers

**Status: 🔨 APPLIED, UNTESTED (2026-09-09).** Scripts `build_heroskill_race.py` (the patch) and
`heroskill_races.py` (the percentages — **the user's file to edit**). `Ziggurat/AoWz.exe` +
`Ziggurat/AoWzCompat.exe` only; nothing in `AoWEPACK.dpl`. ⚠⚠ **Its two snapshots no longer exist.**
`<root>\backups\AoW.exe.pre-heroskillrace` and `<root>\backups\AoWCompat.exe.pre-heroskillrace` were
minted 2026-09-09 14:58 from a positively-proved-unpatched file, kept their **pre-rename** filenames,
and went with `<root>/backups/` when that directory was deleted on 2026-09-10. `BACKUP_DIR` resolves
to `Ziggurat\backups\`, so a fresh mint would land there as `AoWz.exe.pre-heroskillrace` regardless.
This costs nothing: the surgical `--undo` restores the 6 displaced bytes and zeroes the cave,
touching no backup, and that was always the revert path.

Every ability now has a per-race chance of appearing in the Upgrades columns. Turn Undead is offered
to High Men, Dark Elves and the Undead at 60 %, to Humans, Azracs, Elves, Halflings and Dwarves at
25 %, to Lizardmen, Frostlings, Orcs and Goblins never, and to a raceless hero at 25 %; an Elf sees
Archery and Forestry at 60 % each, a Dwarf sees Mountaineering, Cave Crawling and Tunneling at 60 %
each; the rest is a per-level weighted coin flip.
Single-dialog range is **6–35** across the twelve races (raceless 6–30), computed exactly as a
Poisson binomial over the live table and cut where either tail falls below 1 in 5,400.

⚠⚠ **The top rung is 60, so nothing is guaranteed to anyone.** Since the second retune of
2026-09-10 no authored cell reads 100: every race's deterministic floor is **0**, and a High Man is
offered Turn Undead 60 % of the time rather than at every level-up. `always=[...]` in the `OFFERS`
shorthand still means 100, but the shorthand is not the live table — the JSON is.

**The live table (`heroskill_races.json`, fingerprint `818757b6`, ladder `0/10/25/60`), baked into
both exes** — `build_heroskill_race.py` reports `applied -- hook, cave, tails and table all current`
against `AoWz.exe` and `AoWzCompat.exe` (verified 2026-09-23). Expected offers of 103, the
deterministic floor (`det`: cells at 100 — **zero for every row** since the second retune, and kept
as a column only because `report()` prints it), and the ladder distribution per race:

| race | row | expected | det | sd | 0% | 10% | 25% | 60% |
|---|---|---|---|---|---|---|---|---|
| Human | 0 | 15.9 | 0 | 3.1 | 37 | 34 | 19 | 13 |
| Azrac | 1 | 19.0 | 0 | 3.2 | 43 | 20 | 20 | 20 |
| Lizardman | 2 | 15.6 | 0 | 3.1 | 38 | 32 | 21 | 12 |
| Frostling | 3 | 16.3 | 0 | 3.2 | 39 | 28 | 23 | 13 |
| Elf | 4 | 17.1 | 0 | 3.3 | 34 | 31 | 25 | 13 |
| Halfling | 5 | 18.9 | 0 | 3.3 | 33 | 35 | 16 | 19 |
| Dwarf | 6 | 17.4 | 0 | 3.3 | 33 | 33 | 23 | 14 |
| High Men | 7 | 22.1 | 0 | 3.5 | 30 | 28 | 22 | 23 |
| Dark Elf | 8 | 20.4 | 0 | 3.4 | 32 | 29 | 22 | 20 |
| Orc | 9 | 16.5 | 0 | 3.1 | 39 | 29 | 21 | 14 |
| Goblin | 10 | 17.4 | 0 | 3.2 | 36 | 31 | 21 | 15 |
| Undead | 11 | 21.5 | 0 | 3.4 | 36 | 27 | 15 | 25 |
| **Raceless** (derived) | 15 | 17.0 | 0 | 3.4 | 23 | 43 | 27 | 10 |

Grid totals 430 / 357 / 248 / 201 over 103 × 12 = 1236 cells, and
`E = 0.60·#60 + 0.25·#25 + 0.10·#10` reproduces each row's expected count exactly.

**⚠ The twelve races' mean is 18.2 expected offers** (15.6–22.1, sd 3.1–3.5; raceless 17.0, sd 3.4).
The second rung change took it from 22.4 to 16.3 and the cell edits since have raised it again. A
cell at 60 contributes more variance than any other rung and a cell at 100 contributes none, which
is why the spread rose when the top rung dropped. ⚠ Ten of the thirteen rows sit under 20 and
`report()` prints `low` against them in its `vs 20-30` calibration column; High Men (22.1), Undead
(21.5) and Dark Elves (20.4) do not. That is **not a defect** — 20–30 gates nothing and is not a
band (§2.8a). Migration rule, the per-race arithmetic of both rung changes, and why a tier remap
moves row 15's distribution but not the twelve's: `07-ui.md` §2.8a.

**⚠ Row 15 (raceless — Mind Vessel, Dragon Golem) is DERIVED, not authored.** The grid is 12 races by
user ruling and the JSON stores 12 columns; `raceless_cells()` computes row 15 at table-build time as
the per-ability **mean of the 12, quantised onto the ladder**. Leaving it at `TABLE_DEFAULT`
instead — which is what JSON mode did until 2026-09-09 — offered a raceless hero **all 102** where the
shorthand gave him 25.4. Nothing could catch it: `report()` printed row 15 as "not in the grid" and
skipped it, so `--strict` skipped it too. Both now cover it, tagged `derived` or `authored`.

**Row 15 carries 10 cells at the top rung** (Forestry, Strike, Marksmanship, Spell Casting, Vision,
Shield and the Death, Fire, Poison and Cold Protections): a mean of the twelve quantises to 60 once
it passes 42.5, which seven races at 60 and five at 25 already clear. Neither floor nor spread
distinguishes row 15 — every row's floor is 0, and its sd 3.4 sits inside the twelve's 3.1–3.5.
Its shape does: 70 cells on the two middle rungs against 40–56 for the twelve, and only 10 at 60
against their 12–25.
In shorthand mode row 15 stays authored by the `always=["Raceless"]` markers (26.4 expected — the
shorthand's `always` is 100 and does not follow `LADDER`).

**The gate is `cave_fill`'s third test**, after `CanExpand` (mask `0x200`, `call [ability_vmt+0xC4]`)
and `test byte [ability+0x21],1` (mask `0x100`) — so it only ever sees abilities the dialog was
already going to list. 6 bytes displaced; the cave replays both `mov`s, so **EAX = the ability id** on
entry and on every accept path, which is what the resume instruction consumes.

⚠⚠ **Every address in the host is located BY PATTERN on every run, never by constant.** `cave_fill`
is `build_herodlg_columns.py`'s cave (that script replaced `0x446972..0x446A53` with `jmp 0x623DE4`),
and it regenerates that cave from source on every `--apply`, so every VA inside it moves. Each pattern
must match **exactly once inside `.hcol`** or the script aborts:

| site | pattern | today | is |
|---|---|---|---|
| `cf_gate` | `8b 45 f4 8b 40 0c 3d 00 01 00 00` | `0x00623E53` (moves on every `build_herodlg_columns.py --apply` — the script re-locates it by this pattern, never by the address) | `mov eax,[ebp-0xC]` ; `mov eax,[eax+0xC]` |
| resume | `cf_gate + 6` | `0x00623E59` | `cmp eax, 0x100` |
| `cf_next` | `46 ff 4d f0` | `0x00623EF8` | `inc esi` ; `dec dword [ebp-0x10]` |

⚠ Scope the `cf_next` search to `.hcol`: `46 ff 4d f0` matches **twice** in the whole file (the other
hit is at file `0x45FA8`, in CODE).

⭐⚠ **The cave's own first 11 bytes ARE the `cf_gate` pattern** — it replays the two displaced `mov`s
and then falls into its own `cmp eax,0x100` fail-open check, which is the same instruction the pattern
ends on. The locator therefore excludes the cave's own reservation. Without that exclusion the first
`--apply` succeeds and every run afterwards aborts with "matched 2"; worse, a locator that can find the
copy it just wrote could hook the cave to itself. Hit on 2026-09-09, during the very first apply.

**Cave — `0x00628000..0x0062A000` in `.hcol`, 8 KB:**

```
0x00628000    4 B   magic 'RGT1' (dword 0x31544752) -- the "is it installed" probe
0x00628010          entry, 201 of 496 B used   (the E9 target)
0x00628200    5 B   jmp <resume>    ACCEPT tail   -- fixed offsets, so the columns script can
0x00628205    5 B   jmp <cf_next>   REJECT tail   -- rewrite them without re-assembling
0x00629000  4096 B  the table, 16 rows x 256 columns
0x0062A000          build_skylevel_ui.py -- the ceiling
```

⚠ A 16×256 table needs a **full page**: an earlier layout put the magic at `0x00629000` and the table
at `0x00629100`, which ends at `0x0062A100` — 256 bytes inside `build_skylevel_ui.py`'s cave. The
reservation starts at `0x00628000` and the table is page-aligned so it ends exactly at the squatter
floor. `.hcol`'s free run was 24,196 zero bytes at `0x0062417C..0x0062A000`; 16,004 remain below this (`0x628000 - 0x62417C = 0x3E84`; measured, all zero).

**Decision:** `pct = table[min(race,15)*256 + ability_id]`, accept iff `hash < pct`.

**Race key** — `mov ecx,[hero+0x40]` ; `movzx ecx, byte ptr [ecx+0x20]`, which is
`THero.GetRace @0x55786F9C` inlined (a two-instruction leaf). ⚠ **Never call it through VMT `+0xA4`:**
its body ends `mov al,[eax+0x20] ; ret`, so only AL is valid and the top 24 bits of EAX are the
resource *pointer* — using EAX as a row index after that call reads megabytes past the table.
`[hero+0x40]` is nil-guarded and fails open. ⚠ Never `hero[+0x68]`. Race enum read from
`Release/HERORES.PFS` tag `0x0B` (tag `0x0A` is the race NAME string), three records per race all
agreeing: `0 Human, 1 Azrac, 2 Lizardman, 3 Frostling, 4 Elf, 5 Halfling, 6 Dwarf, 7 High Men,
8 Dark Elf, 9 Orc, 10 Goblin, 11 Undead, 255 raceless` (Mind Vessel, Dragon Golem → row 15). Rows
12–14 are unreachable and hold 100.

**Which hero object — the ORIGINAL at `[ebx+0x1D8]`, not the working copy at `[ebx+0x1DC]`.**
`Setup @0x446268` does `mov eax,[ebx+0x1D8]` → `TEObject.Copy @0x4462C7` → `mov [ebx+0x1DC],eax`;
`cave_fill` passes the *copy* to `CanExpand`, which is right for "does he already have it". The gate
must not: `PopulateLists @0x446954` re-runs on **every Add and every Remove**, and the copy is what
those mutate. Reading the original makes the offer set invariant for the life of the dialog.

**RNG — pattern P4 DERIVED HASH** (`12-re-toolchain.md` §4.10), emitted by `build_scripts/rngstd.py`
verbatim and asserted byte-for-byte before writing. Q2 of the selection test answers it: the same
situation must give the same answer on a later evaluation (dialog reopen, save/reload), so **no draw
at all**. Q3 agrees independently — the site is in `AoWz.exe`, which has **0 SYNC sites** and does not
import `TAoWHSMap.Random` (`rng_audit.py AoWz.exe --functions` → `SYNC: 0 / RAW: 1`), so P1 was never
available here; `System.RandInt` (thunk `0x401030`, IAT `0x45D374`) draws from the per-process
`System.RandSeed` and would re-roll on reload. Consequences: the columns cannot shimmer under the
cursor, a save/reload cannot re-roll the offer, every peer computes the same set — **and it adds no
`ReadWrite` field.**

Inputs, in this fixed order:

1. `map[+0x22C]`, the per-game salt — `[[0x0045DF7C]] + 0x22C` in these two exes. ⚠ **Both
   dereferences are nil-guarded and fall through to salt 0**; the value is 0 until
   `TPlayerControl.NewDay` runs on day 1, and FNV mixes 0 fine.
2. `[hero+0x18]` — the network unit id, dword; serialised by `TAbstractUnit.ReadWrite @0x557820E4`
   at `0x55782116` under tag `0xFFFFFFFF`.
3. `movzx [hero+0x4C]` — the serialised level cache, **one byte, not four**. Deliberate: the offer
   re-rolls at every level, so the variable band changes shape each level-up.
4. the ability id.

Then `fmix32()` and `range_n(100)`; `cmp edx, pct ; jb accept`. `mul` clobbers EDX:EAX, so the pct and
the ability id are **pushed across the hash** rather than parked in registers. EBX (form), ESI (loop
index) and EBP (host frame) all survive — rngstd touches only EAX/EDX/ECX/flags.

**The cave adds no draw**, so `rng_audit.py --owners` is unchanged (24 modded sites before and after);
`--hash` is what proves the site exists: it lists `006280A9 rngstd.fmix32 <- build_heroskill_race.py`
in both exes. These are the project's first P4 sites and the first in an exe.

**⚠ `TABLE_DEFAULT = 100` — fail open, and it is load-bearing.** The table is id-indexed, so an
ability with no line in `heroskill_races.py` reads whatever the cell holds. At 0 a newly minted
ability would be silently never offered with nothing to see anywhere; at 100 it is always offered and
the omission shows up in the dialog instead. The mirror of the `herodlg_cats.py` `DEFAULT_CAT` trap
that cost QA a finding on 2026-08-27. (`build_reformingflesh.py`'s id 177 has no `Ability.pfs` record
and is riding on exactly this today.)

⚠ **Since the second retune of 2026-09-10, `TABLE_DEFAULT` is the only 100 left in the table** — the
ladder's top rung is 60. So an **unknown** ability is offered more often than any ability
deliberately marked a race's signature. That is still the right fail-open, for the reason above, but
it is a new asymmetry: it inverts the intuition that the loudest cells in the table are the authored
ones. It also means a mistyped or newly minted id shows up as an ability offered at *every* level,
which is a sharper tell than it used to be.

**The offered set is re-derived live**, never hard-coded: `Release/Ability.pfs` tag 9 with **both**
`0x100` (b8 Hero upgrade) and `0x200` (b9 THero, labelled "Editor" in AoWDevEd) — **103** abilities
today, all real and named, against vanilla's 23. Column split: Wayfaring 25 / Resistances 17 / Melee
21 / Ranged 20 / Magic 20.

⚠⚠ **`Ability.pfs` record id = ability id + 10.** Joining record ids straight to ability ids produces a
completely wrong analysis that reads as entirely reasonable; it survived two rounds of review on
2026-09-08 before a screenshot caught it. `heroskill_races.py` asserts the join on every run against
two records checked in AoWDevEd: ability 97 (Webbed) → record 107, tag 9 `0x03E`, tag 6 0; ability 88
(Black Breath) → record 98, tag 9 `0x3FF`, tag 6 20. (`re_tools/abmask.py`'s docstring says record ids
"are NOT ability ids — do not join it to ability ids"; it is right that they differ and wrong to imply
no join exists. The `+10` rule is the join, and `build_shield.py` and `build_vision9.py` both ship on
it.)

⚠ Tag 9 is a **u16**. `pfs.u32` returns its default on a 2-byte field, so reading it that way yields 0
for every record and the conclusion "no ability is offered at all".

**⚠⚠ `build_herodlg_columns.py --apply` WOULD UNLINK THIS — it is now taught to re-chain.** That
script calls `undo()` and regenerates `cave_fill` from source, restoring the vanilla
`8b 45 f4 8b 40 0c` and moving it: the Magebane/Shield failure mode, and silent. Three changes there:

1. `SQUATTER_FLOOR` lowered `0x0062A000` → **`0x00628000`**, with this cave added to its squatter
   list, so its existing `assert D["code"] + len(code) < SQUATTER_FLOOR` protects the table for free.
2. `relink_racegate()` runs between `apply_to()` and `save()` and calls
   `build_heroskill_race.relink_bytes()`, which re-locates the site by the **same** pattern search and
   rewrites the 6-byte hook and both tail jumps into the in-memory image. Prints
   `race-offer gate: re-chained` or `not installed` — **never nothing**, and shouts if the module will
   not even import.
3. `undo()` unchanged: restoring the vanilla fill loop correctly leaves the gate cave inert.

Both scripts derive the three addresses the same way, so either apply order works and re-running
either is idempotent — verified: two consecutive `build_herodlg_columns.py --apply` runs over an
installed gate produced byte-identical exes.

**The AI is unaffected and that is structural, not incidental.** `THero.ValidateHeroUpgrade @0x55787D54`
calls `ExecuteUpgradeHeroAI @0x55787A24` directly when `player[+0xA7] != 0`, never touching the dialog,
so an AI hero still picks from all 103. Filtering the AI too would be a **second patch in
`AoWEPACK.dpl`** — and that path *is* in the SYNC list (`0x55787C35 → call 0x5577827C`, feeding
`RandomChanceItemB` at `0x55787C46`), so it would need the synced generator or this same hash. Out of
scope.

**Multi-level catch-up is already resolved:** `ValidateHeroUpgrade` sets the level cache straight to the
final level and emits **one** `THeroUpgradeEventLog` carrying `(oldLevel, newLevel)`. A hero gaining
three levels at once gets one dialog at the final level — so the gate evaluates once, and a big XP award
narrows the offer set exactly as much as a single level-up does.

**Reusable machinery, re-verified 2026-09-09** — `THeroUpgradeDlg` VMT `0x4458C8`, singleton
`[0x45A0F0]`, instance size **`0x240`** = 576 (grown from `0x1E0` by the columns feature; byte-checked at `[VMT-0x1C]` = `[0x004458AC]` 2026-09-09 — an earlier revision of this line said `0x230` and was wrong); `Setup @0x446268`
unhooked and byte-intact, one caller at `0x44F1F3`; `PopulateLists @0x446954` with 3 callers
(`0x4462DB`, `0x447122`, `0x4471B3`); `DoneClick @0x4472AC` builds the synchronised `THeroUpgradeTE`,
and the offered list is never transmitted.

**Zero-code alternative, still open and independent:** the 103-vs-23 gap is entirely `Ability.pfs`
tag 9, 2 bytes in every record — a length-preserving write needing no property-table rebuild
(`build_pfs_typos.py` is the existing writer). It gives no per-race variation, but it is the cheapest
global lever on "too many choices" and composes with this feature rather than competing with it.

**Static checks that passed (2026-09-09).** Both `Ability.pfs` join asserts; each of the three patterns
matching exactly once per exe; the cave disassembly read instruction by instruction (no `div`;
`69 c0 6b ca eb 85` and `69 c0 35 ae b2 c2` once each; the only absolute operands are `[0x0045DF7C]`
and the table base `0x00629000`); the four nil guards and the `cmp eax,0x100` fail-open present; the
emitted hash byte-identical to `rngstd.basis() + 4×mix() + fmix32() + range_n(100)`; `.reloc` empty
across the whole of `.hcol` and in particular in `[cf_gate, cf_gate+6)`; no branch landing inside the
displaced bytes; `AoWz.exe`/`AoWzCompat.exe` differing at exactly one offset (`0x3BB7C`);
`0x0062417C..0x00628000` still all-zero; `build_skylevel_ui.py`'s cave at `0x0062A000` untouched;
`AoWEPACK.dpl`, `AoWDevEd.exe` and `HSEPack.dpl` md5-unchanged; the re-chain round-trip both ways;
`--undo` restoring the 6 bytes and leaving `0x0062417C..0x0062A000` all-zero; the live table byte-equal
to `heroskill_races.table()` with every cell in 0..100.

**Re-applied 2026-09-09 to bake the seeded JSON + derived row 15.** `stale` → `on` on both exes.
1062 of 4096 table bytes moved — 963 in rows 0–11 (the seed's quantisation, 5→0, 10→15, 25→15, 30→40)
and 99 in row 15 (all-100 → derived) — and **nothing else**: diffed against
`backups\*.pre-heroskillrace` the whole footprint of the feature is the 6-byte hook at `cf_gate` (then `0x00623E5D`)
plus bytes inside `0x00628000..0x0062A000`, 3901 bytes per exe, zero outside. Cave code (201 B),
both tails, the `RGT1` magic and the hook are byte-identical across the re-apply; only data moved.
File length and section table unchanged; the two exes still differ at exactly `0x3BB7C`; the backups
were not touched by the re-apply (they held the `orig` state) — ⚠ **they have since been deleted with
`<root>/backups/` on 2026-09-10, so the `--undo` reference is now the script's own recorded original
bytes, not a file**. md5s at the time of that re-apply
`c0504136be44aa4fee1ee0e745fe431d` / `5e3a568bae16d9eed6adea3fc790913c`; `AoWEPACK.dpl`,
`AoWDevEd.exe`, `HSEPack.dpl` md5-unchanged. ⚠ Those two md5s are **superseded** — the files were
renamed to `AoWz.exe` / `AoWzCompat.exe` and re-derived later the same day; the canonical pair is
`301a071399f34dfd3f7df0c5470a12bb` / `6636685e8ca976b916de339b073fe6d7` (2026-09-09).

**⚠ Still needs the user's in-game test:**

⚠⚠ **Since the second retune of 2026-09-10 the top rung is 60, so no single level-up proves
anything about a signature ability.** Every "always" test below became a *frequency* test and needs
several level-ups. The only checks that still fail on one dialog are the **0 %** ones — an ability a
race can never be offered.

1. Level a hero of each of two or three **different races** and confirm the Upgrades columns differ in
   a race-appropriate way — an Elf sees Archery and Forestry at 60 % each; a Dwarf sees
   Mountaineering, Cave Crawling and Tunneling at 60 % each. Over four or five level-ups each
   should turn up roughly three times in five; never appearing across five is worth a second look,
   once, not a bug report.
2. **Turn Undead is still the sharp check, but only in the negative direction.** It must be
   **absent at every level** for the four grid races whose cell is 0 (Lizardmen, Frostlings, Orcs
   and Goblins) — one sighting there is a real defect. It is 60 % for High Men, Dark Elves and the
   Undead, 25 % for Humans, Azracs, Elves, Halflings and Dwarves, and 25 % for a **raceless** hero
   (the derived row rounds the twelve's mean of 25.4 to 25), so a raceless Turn Undead is correct
   and not a leak.
3. **The set must not shimmer.** Add an ability, then Remove it, then Cancel and reopen the dialog —
   the *available* list must be identical every time. (This is what reading `[ebx+0x1D8]` buys.)
4. **Save mid-level-up, reload, reopen** — the same abilities must be offered. A different set means
   the salt or one of the hash inputs is not what it is thought to be.
5. Level the **same** hero again and confirm the set *does* change — the level byte is a hash input,
   so a hero who saw one set of ~18 at level 5 should see a different ~18 at level 6.
6. Confirm the columns still fill, sort and scroll normally, and that Add/Remove/Done still work — the
   gate sits inside `build_herodlg_columns.py`'s fill loop.
7. A **raceless** hero (Mind Vessel, Dragon Golem) must be offered a *generic* list — roughly 17
   of 103 — not all 103 and not none. That exercises the `min(race,15)` clamp
   **and** the derived row 15. All 103 means the derivation did not reach the table.
8. Count the offers on a few heroes. Per-race means are **15.6–22.1** (raceless 17.0) and
   single-dialog counts run **6 to 35** (raceless 6 to 30), so a correct install legitimately shows
   8 or 32 and neither indicts anything. Only a dialog of **0–2 or 60+** points at the table index.
   Judge across several heroes, not one. ⚠ **20–30 is not a target, a floor or a band** — it is a
   direction the owner sketched once, it gates nothing, and ten of the thirteen rows sit under it
   (§2.8a). Do not read a count of 14 as a fault.

#### Feature 2 — restore multi-level Leadership (superseded)

This investigation proposed raising the cap to a *safe* 3 levels (the vanilla attack/defence bonus
tables are packed only 4 bytes apart, so a naive 4th level would read into adjacent data without
relocating them) and populating cost-list entries 2/3 via a cave redirecting the ctor's single
`TIntegerList.Put`. **Superseded by the as-built 4-level version** (subsection C), which took the extra
step of relocating both tables — the only genuinely reusable fact here is *why* 3 looked like the clean
ceiling before that relocation was done.

#### Feature 3 — Leadership disabled under a hero's aura → its own doc

Moved to subsection B in full.

### B. The disable-bug root cause and fix

**Status: ✅ CONFIRMED WORKING (2026-07-20)**, validated in-game. Script `build_leadership_fix.py` —
**has** a surgical `--undo` (added 2026-09-02: restores both call sites, zeroes the cave, touches no
backup); the `.pre-leadershipfix` snapshot no longer exists and was never a safe revert path.

**Summary:** a unit/hero that earns Leadership *while standing in another leader's aura* never receives
its own inherent record — only the borrowed aura record. When the aura later goes away, the aura
garbage-collector deletes that record **and clears the ability bit**, so the unit permanently loses
Leadership it legitimately earned. Two independent defects combine: **Defect A** (the grant is masked)
and **Defect B** (the cleanup can't distinguish a masked-but-real grant from a genuine loan). Neither is
harmful alone.

**The two stores disagree.** Per-owner state splits into an enabled bitset and an ability-data record
(A's model, above); the level accessors read *only* the record (`GetAbilityLevel`/`GetLevel` return 0
with no record, never touch the bitset) — so "has the bit" and "has a level" are different questions,
and a bare bit reads as level 0.

**The aura recompute — `TArmy.UpdateFormation @0x5578D034`**, called only from `TArmy.Update` (any
stack change) and `TCombatUnit.SetParty` (combat start): **pass 1** resets every unit's external source
(`ResetExternalSource`) then finds the army's Leadership maximum; **pass 2**, only if that max is
positive, propagates it to every unit below it via `SetExternalSource` (creates a record with
`[+0x0C]=0` if the owner has none, sets the bit, writes `[+0x10]`=borrowed level).
`ResetExternalSource @0x557662E4`: if `data[+0x0C]!=0` (genuinely inherent) it just clears the borrowed
fields — benign; **if `data[+0x0C]==0`** it calls `SetAb(...,0)` (clears the bit) and
`RemoveAbilityData` — **destructive**.

**Defect A — the masked grant.** `TAbilityOwner.UpdateDefaultAbilities @0x5574F518` (the medal/chassis
grant) skips copying the inherent record whenever `unit.GetAbSet(id)` is already true **and**
`template.GetAbLevel(id) <= unit.GetAbLevel(id)`. The level comparison uses `GetAbLevel` (owner
`VMT+0x84`), which is the ability's **effective** level (`max(own, borrowed)`) — not
`GetInherentLevel` (`data[+0x0C]` only), which exists and simply wasn't used here. So a unit standing
in a level-1 aura the instant it earns a medal already reads effective level 1 (bit set by the aura,
own=0), the comparison `1<=1` skips the copy, and the unit ends up with only the aura record.

**Defect B — permanent loss.** Once the masked unit leaves the aura (or the leader dies), pass 1 finds
`data[+0x0C]==0` and takes the destructive branch: bit cleared, record freed, and pass 2 doesn't run
(`runningMax` from that unit's own perspective is now 0 for it). **Nothing restores it** — every
re-grant path is one-shot: rank-change grant only fires on an actual rank change (never again at gold
medal, the classic trigger case), `NewDay`'s full rebuild is gated to **day 1 only**. Heroes are
vulnerable identically (their own bitset/record accessors are exactly the terms compared). It looks
intermittent because the trigger is invisible at the moment it happens — the card still shows
Leadership (bit set) for as long as the unit stays in the aura; the loss only surfaces later, on
separation.

**Separate data defect found in passing — Crown of Kings.** A full `.pfs` sweep found bit/record
correlation perfect everywhere *except* one bare-bit Leadership grant at `ITEMS.PFS 0x54B` (Crown of
Kings): the item sets the bit with no accompanying record, so its Leadership reads as level 0 (no
attack/defence bonus, no aura projected). Different bug from the above — "never worked," not "becomes
disabled" — and a **data** fix (add a level-1 record in `ITEMS.PFS`), not a code one. Not yet fixed.

**The fix implemented:** both `GetAbLevel` call sites in `UpdateDefaultAbilities` (`0x5574F54D`,
`0x5574F55B`, each an 8-byte `mov ecx,[eax]`+`call [ecx+0x84]`) now route through **`cave_abinherent`
@`0x5580F100`**, dispatching ability `VMT+0x94` (`GetInherentLevel`) instead of `+0x70`
(`GetLevel`/effective) — 3 `nop` pad each. Blast radius nil for **bit-only** abilities: base
`TAbility.GetLevel`/`GetInherentLevel` both return a constant 0, so plain abilities compare 0-vs-0
either way; `TMultiLevelAbility` descendants strictly improve (a unit with inherent 1 + borrowed 3,
granted a level-2 template, now correctly upgrades to 2 instead of being skipped). Defect B's
`own==0` test in `ResetExternalSource` was deliberately left alone — once A stops discarding the
inherent record, that test correctly identifies genuinely-borrowed records again, which is what it was
written for.

#### B′. The fix had a regression — Turn Undead and Dispel Magic levels were never applied — FIXED

**Status: 🔨 APPLIED, UNTESTED (2026-09-10).** Script `build_inherent_level_fix.py`, surgical `--undo`,
snapshot `backups\AoWEPACK.dpl.pre-inherentlevelfix`. Found by reading a fellow modder's follow-up
script (`Inioch/share2/patch_inherent_level_fix_v1.py`); he hit it **in-game** on AoWx, which carries
the identical `cave_abinherent` patch. Our binary had the same two call sites and the same VMT values.
⚠ The defect itself was never reproduced in Ziggurat in-game — it is byte-verified and the mechanism is
certain, but the *symptom* was inferred, not observed here.

**The mechanism.** The safety argument above holds only for two populations: bit-only abilities (both
accessors return 0) and `TMultiLevelAbility` descendants (both overridden). **Two leveled classes are
in neither** — they implement their own level machinery and inherit the base `GetInherentLevel`, which
is `return 0`:

| class | `+0x70 GetLevel` | `+0x94 GetInherentLevel` |
|---|---|---|
| `AoWE..TTurnUndeadAbility` VMT `0x5571FDFC` | `0x5576AE8C` own | `0x5574E954` **base → 0** |
| `AoWE..TDispelMagicAbility` VMT `0x55721D78` | `0x5576CEFC` own | `0x5574E954` **base → 0** |

So where vanilla compared *real level vs real level* at `0x5574F54D`/`0x5574F55B`, we now compare
**0 vs 0** for those two. `0 <= 0` takes the `jle` at `0x5574F565` and the record copy is skipped, so
the level never reaches the owner. The comparison is only reached when the owner **already has the
bit**, which is exactly "buying level II or above":

```
vanilla  5574F54D  8b 08 ff 91 84 00 00 00   mov ecx,[eax]; call [ecx+0x84]   ; effective level
live     5574F54D  e8 ae fb 0b 00 90 90 90   call cave_abinherent + nop*3     ; inherent -> 0 for TU/DM
```
Verified against **both** pristine references (game root and `AoWEPACK_original_backup.dpl`); the two
VMT slots read base in vanilla *and* live, so this is the patch meeting pre-existing class shape, not a
VMT edit of ours.

**Blast radius.** Hero level-up purchases of Turn Undead II+ / Dispel Magic II+ deduct the skill points
and apply nothing (`THeroUpgradeTE.Execute @0x557854E0` applies a purchase by handing
`UpdateDefaultAbilities` a template owner). Unit medal rank-ups whose templates carry TU/DM levels fail
the same way. Both abilities are leveled *in Ziggurat specifically* — `build_dispelmagic5.py` raised the
Dispel Magic cap to V — so this is live, not theoretical.

**As built:** two dwords, no cave, no hook, no assembler — `+0x94` is set to the SAME function as that
class's `+0x70`.

| VA | class | was | now |
|---|---|---|---|
| `0x5571FE90` | `TTurnUndeadAbility` VMT+0x94 | `0x5574E954` | `0x5576AE8C` |
| `0x55721E0C` | `TDispelMagicAbility` VMT+0x94 | `0x5574E954` | `0x5576CEFC` |

Exactly **6** bytes change (each dword keeps its high byte `0x55`). sha256 `9583c631…` → `57d4e636…`.
Both slots carry `.reloc` type 3, so the value swap stays rebase-correct; both targets are byte-identical
to vanilla. `--undo` round-trips to the exact pre-patch sha256 and `--apply` is idempotent.

Why each class's **own** getter rather than `TMultiLevelAbility.GetInherentLevel`: `TDispelMagicAbility`
stores its level at **`[rec+0xD]`**, not `[rec+0xC]` — for `TDispelMagicAbilityData` (ClassID `0x202CD`)
`+0xC` is the *enabled* flag. MLA's accessor would have read the wrong byte. ⚠ `TDispelMagicAbility.GetLevel`
also tests the self-only bit `[owner.vmt+0x4C]` first and returns **1** when the bit is set with no record.
Neither is a regression: vanilla's `+0x84 GetAbLevel` reached the same function, and `GetAbLevel @0x5574FD44`
is byte-identical to `cave_abinherent` but for `+0x70` vs `+0x94`.

⚠⚠ **The second consumer is in the EXEs, and the first analysis missed it** (QA, 2026-09-10 — the analysis
had already been called complete). `TAbstractUnit.GetInherentAbilityLevel @0x5577F5A8` dispatches `+0x94`
at `0x5577F5D1`. A scan of `AoWEPACK.dpl`/`AoWTCPCK.dpl`/`aowInt.dpl` finds no `TAbstractUnit` receiver —
but `AoWz.exe`/`AoWzCompat.exe` carry **four**, all in `THeroUpgradeDlg`, because `THero` VMT
`0x55711FEC + 0xBC` *is* that function. Each is a before/after pair over one ability id
(`[dlg+0x1d8]` = the hero as he was, `[dlg+0x1dc]` = the working copy):

```
00446AE5..00446B09  ability-list fill : equal -> print the label, differ -> print the cost delta
00447185..004471AB  RemoveBtnClick    : equal -> REFUSE to remove, differ -> allow + RemoveAbility
```

Vanilla returned 0 from both sides for TU/DM, so the dialog always took the "equal" arm: label shown,
Remove permanently refused. Now both sides return the real level, so a level bought in *this* dialog
session shows a cost delta and can be un-bought — which is what the six `MLA-94` classes always did, and
what the before/after comparison exists for (it protects levels the hero already held). Corrective, but a
behaviour change **versus vanilla at a destructive control**, so it carries its own checklist item below.
⭐ **This is the project's per-binary rule biting: verify the call path in EVERY binary, not just the one
that owns the function.** A DLL-only scan cannot see a dialog that lives in the exe.

⭐ **The generalisable audit**, and the reason one was missed: `GetLevel` and `GetInherentLevel` are
**not** guaranteed to be overridden together. Any patch that swaps a level accessor for its sibling must
sweep every ability VMT for the pair. `build_inherent_level_fix.py --audit` is that sweep, and it runs as
part of the no-args verify. It walks every VMT structurally (self-pointer at `VMT-0x40`, name at
`VMT-0x20`) and keys membership on **descent from `TAbility`** (parent pointer at `VMT-0x18`) rather than
on the value in `+0x94` — a value whitelist silently drops any future class that overrides `+0x94` with
its own function. The 82 `TAbility` descendants fall in exactly three buckets:

| count | shape | verdict |
|---|---|---|
| 74 | base `+0x70` + base `+0x94` | harmless, 0 vs 0 either way |
| 6 | own `+0x70` + MLA `+0x94` | `TMultiLevelAbility`, `TTransport`, `TLeadership`, `TSpellCasting`, `TVision`, `TMarksmanship` |
| 2 | own `+0x70` == own `+0x94` | `TTurnUndead`, `TDispelMagic` — **ours** |

**Cost and cap are untouched:** TU and DM override `GetSkillPoints`, `CanExpand`, `ExpandCost`, `Expand`
and `Remove`, and not one of those reads `+0x94`. `build_dispelmagic5.py`'s cap edits at `0x5576D163`
and `0x5576D1D0` sit outside `GetLevel`'s extent and still verify.

**Data this bites on** (`pfs.py`, levels 2+): Turn Undead on Human Priest, Elf/Halfling/Dwarf Cleric,
Highman Chanter, Highman Paladin, Valkyrie, Dark Elf Storm Priest, Frost Queen, Azrac Yakamajal, hero
Caspar the Pious, item Ankh of Turning. Dispel Magic on Human Priest, Human Charlatan, Frost Queen, Elf
Cleric, Elf Druidess, Halfling Cleric, Leprechaun, Dwarf Cleric, Highman Chanter, Dark Elf Storm Priest,
Undead Doom Priest. ⚠ Separate authored-data defect found in passing: Astra, Druid, Necromancer and Hydra
carry a `TDispelMagicAbilityData` record with the `0x3C` bit **not set**, and Highman Chariot the same for
Turn Undead — `GetLevel` returns 0 without the bit, so those records are inert.

**In-game checklist (the user's test):**
1. Hero with Turn Undead I buys **TU II** — points spent *and* the level reads II afterwards, and still II
   after save/reload. Then III, to prove it is not a one-off.
2. Hero with Dispel Magic I buys **DM II** — displayed level, and the dispel strength actually changes in
   combat (its level byte is `[rec+0xD]`, a different byte from every other multi-level ability).
3. ⭐ **The level-up dialog itself** (the exe finding above). With a hero already holding TU I or DM I, open
   the dialog: the **Cost column** for that row should read like Leadership/Vision/Marksmanship, and
   **Remove** should un-buy only a level bought in this session. *Wrong* = Remove strips the ability
   entirely including the pre-existing level, or a cost number appears with nothing bought.
4. **Medal rank-up** — take a Human Priest, Elf/Halfling/Dwarf Cleric, Highman Chanter or Valkyrie to
   silver then gold; TU/DM must step 2 → 3 → 4. Units cache stat modifiers and heroes recompute, so both
   1 and 4 are needed.
5. Repeat 1 and 3 **while the hero is stacked under a Leadership aura** — the condition
   `build_leadership_fix.py` exists for. The masking must not return.
6. Leadership, Vision, Marksmanship and Spell Casting still level normally (they share the patched
   comparison but not the patched slots).
7. Equip the **Ankh of Turning** (TU level 2, with a record) on a hero already holding TU I; effective
   level must be sane.

**Why Leadership is never removed from the ruleset — the mechanism, not superstition.**
`UpdateFormation`'s per-unit loop has **two unguarded dereferences**: `GetAbility(0x2E)` returns nil
silently for an unregistered id, and the immediately following `ResetExternalSource(nil, unit)` call
takes that nil as `Self`; further down, `GetAbilityOwner` is dereferenced with no nil check either.
Byte-verified identical to pristine — this is vanilla fragility, not something any Ziggurat patch
introduced. ⭐ The aura is **derived, not persisted** (no stored value in a save could be orphaned), so
for the *unregistered-id* route the sufficient mitigation is simply: never unregister id `0x2E`.

⚠⚠ **The second unguarded deref has a WIDER trigger than an unregistered id, and the earlier "not a
live concern" ruling (2026-08-28) covered only the narrow one.** Pass 1 re-reads the level *after*
`ResetExternalSource` has possibly deleted the record, then fetches the owner and derefs it blind:

```
5578D0B9  call ResetExternalSource      ; may clear the bit AND free the record
5578D0BE  mov edx,0x2E / call [ecx+0x144]   ; GetAbilityLevel   <- re-read AFTER the delete
5578D0CD  cmp eax,[ebp-8] / jle skip
5578D0D5  mov edx,0x2E / call [ecx+0x154]   ; GetAbilityOwner   <- nil when no bit anywhere
5578D0E4  lea edx,[ebp-0xC] / mov ecx,[eax] ; *** UNGUARDED — AV on nil ***
5578D0E7  call [ecx+0x60]                   ; GetOwnerName
```

The crash condition is a **disagreement between the two queries**: `GetAbilityLevel > 0` while
`GetAbilityOwner == nil`. On a hero they resolve differently on purpose — `THero.GetAbilityLevel
@0x5578831C` falls back to *the hero itself* when the superlative search finds nobody
(`0x55788330 test ebx,ebx / jne / mov ebx,esi`), so it answers from the hero's own record; whereas
`THero.GetAbilityOwner @0x55788274 → GetSuperlativeAbOwner @0x557881DC` answers from **bitsets only**
and returns nil. Vanilla keeps them consistent because `TLeadershipAbility.GetLevel @0x557661C4` reads
*only* the record, and every path that creates or destroys a Leadership record sets or clears the bit in
the same breath. **Ziggurat is not exposed** (checked 2026-09-10: `GetLevel` is vanilla-shaped, and our
backpack widenings in `build_useitems.py` / `build_item_hpmv.py` all keep the `item+0x34==6` gate, so
level and owner agree).

⭐⭐ **The rule this yields: any patch that widens a LEVEL query must widen the matching OWNER query by
the same predicate.** Widen one only and the engine dereferences the disagreement here. The live example
is a fellow modder's AoWx: `Inioch/share4/patch scripts/build_item_ability_levels.py` gives
`TLeadershipAbility.GetLevel` an item-record fallback that searches **carried and inventory** items when
the owner has no record, while `GetSuperlativeAbOwner` still applies the type-6 gate — so an **unequipped
wearable** supplies a level that can never be returned as an owner. His player's repro needed all three
of: an unequipped wearable carrying Leadership, at a level **below** a second source, and that second
source being an **aura** (whose `own==0` record is what pass 1 deletes one instruction earlier, creating
the recordless window the fallback fires in). See `Inioch.md`.

⚠ **Why the symptom is permanent and shows up far from the aura: `TArmy.Update @0x5578D1B0` has NO
exception frame** (byte-checked: no `64 ff 30` / `64 89 20` anywhere in it, while `UpdateFormation` does
have one and merely re-raises through `@HandleFinally`). It takes `TEChangeNotifyNode.LockChanged` at
`0x5578D1C5` and releases it at `0x5578D231`. An exception in between **leaks the lock**, and
`TArmy.Update`'s own first instruction is `cmp dword [ebx+0xC],0 / jne exit` — that dword *is* the lock
depth. So one AV inside `UpdateFormation` wedges that army forever: no further aura recompute, no
`UpdateConcealment`, no `UpdateIndependentRelation`, no `TriggerOnUpdateEvent`/`ArmyChanged`. Anything
downstream of an army update appears to "stop working" on the world map with no further errors.

### C. As-built: four levels (I–IV) + aura instant-refresh

**Status: ✅ CONFIRMED WORKING (2026-07-20)** for the 4-level ability itself, user-validated ("All
working"), covering both this and B's fix together. Cost subsequently re-tuned 20→**10**/level the same
day — re-verified by disassembly; the 10-point cost specifically has not been separately play-tested
beyond that. Script `build_leadership4.py` — ⚠ **still has no `--undo`** (the one place in this cluster
where a rollback needs manual work, below). Aura instant-refresh: `build_leadership_aura.py` — **has** a
surgical `--undo` (added 2026-09-02). Both functionally independent of B (disjoint patch addresses,
disjoint caves), and independent of each other, but their designs compound: raising the cap widens the
window Defect A could have masked, so B's fix matters *more* with 4 levels installed than it would have
at 1.

**Three things pinned Leadership to one level, all lifted:**

| # | vanilla | now |
|---|---|---|
| 1 | `Create @0x5576616C` calls the base ctor (sets cap `[+0x28]=4`) then **stomps it to 1** @`0x55766187` | cap = **4** |
| 2 | ctor populates only `cost[1]=20` | `cost[1..4] = 10` each |
| 3 | `GetLevelName @0x557663D0` ignores its level argument, always "Leadership" | appends ` I`/` II`/` III`/` IV` |

**Chosen curve (user decision 2026-07-19, re-tuned 2026-08-20, confirmed in-game 2026-08-24):**

| Level | ATK | DEF | Cost | Cumulative | hit-chance impact |
|---|---|---|---|---|---|
| I | +1 | +1 | 10 | 10 | +5pp |
| II | +2 | +2 | 10 | 20 | +10pp |
| III | +3 | +3 | 10 | 30 | +15pp |
| IV | +4 | +4 | 10 | 40 | +20pp |

These are raw table values on the doubled-stat scale — **Leadership is a deliberate exception, never
touched by `build_statdouble.py`**, so this table alone sets its strength. ⚠ This re-balances level 1
*downward* **in effect, not in magnitude**: vanilla's single level was **+1/+1** (byte-read
2026-09-09 from `LeadershipAttackProgression @0x558E83E8` / `LeadershipDefenseProgression
@0x558E83EC` in `AoWEPACK_original_backup.dpl`, cap 1 — `re_tools/enchant_mods.py
leadership_table()` reads either DLL). Level I matches it numerically but is worth half as much,
because vanilla paid 10pp per point and Ziggurat pays 5, so **level II** is the equivalent of
vanilla's one level. Existing level-1 grants (medals, chassis) get weaker; the new ceiling is
higher. Re-tune via `ATK_BONUS`/`DEF_BONUS`/`COST_EACH` in the
script and re-`--apply` — the free-space guard (fixed 2026-08-20) recognises its own signature block
and rewrites the curve bytes in front of it in place; **no revert-and-reapply, ever** (an earlier
version of this doc's procedure said to revert `.pre-leadership4` first — by the time anyone checked
again that snapshot no longer existed; nothing in the doc changed when it stopped being right, which is
the whole argument for surgical/in-place patching over backup-based procedures).

**The bonus tables were relocated**, not left at their cramped vanilla spacing (4 bytes apart — reading
index 4 would read into the other table). Both moved into the cave block as 5-byte tables (levels 0–4)
at `0x5580F0C0` (attack) / `0x5580F0C8` (defence), values emitted from `ATK_BONUS`/`DEF_BONUS` — read
them live (`python build_scripts/build_leadership4.py` with no args prints `[data] 5580F0C0 atk=... def=...`)
rather than trusting a number in this doc, since a prior version of this table went stale for 12 days
after a re-tune. Both displacements carry `.reloc` entries (verified: 63 883 total in the file, both
present) — **the reusable trick**: an existing absolute operand with a reloc can be repointed anywhere
in the image and stays rebase-correct, only the *value* changes.

**Level names reuse the game's own idiom** — `GetLevelName`'s vanilla peers
(`TMarksmanshipAbility`/`TVisionAbility`) call `LoadResString`→`TranslateRStr`→`LStrCat3` with a
per-level suffix literal; `cave_lsname @0x5580F000` borrows the game's own `" I"`/`" II"`/`" III"`/
`" IV"` constant AnsiStrings (`0x557BBF18`/`24`/`30`/`40`) rather than minting new ones, by calling the
*original* `GetLevelName` into a stack temp (keeping resource loading + SEH in vanilla code) then
`LStrCat3`ing the suffix. Hooked via **VMT `+0x10C` repoint** (`0x55722114`, verified the *only*
reference to `GetLevelName` in the module) rather than an entry hook, because the cave calls the
original and an entry hook would recurse.

**Position independence:** `cave_lscosts` is rel32-only; `cave_lsname`/`cave_abinherent` need absolute
data (suffix table, `AoWHSSet` global `0x558FA044`) and compute the load delta with the standard
`call $+5; pop reg; sub reg,<link addr>` trick, asserted at build time against the expected `pop`
opcode so the trick can't silently drift if the prologue is edited.

**Revert:** feature C's 4-level ability has **no `--undo`** — manually restore the cap byte at
`0x5576618A` (`04`→`01`), the cost-`Put` call at `0x557661A2` to its original single-entry form, the
`GetLevelName` VMT slot `0x55722114` to `0x557663D0`, and zero the three cave zones
(`0x5580EFC0`/`0x5580F000`/`0x5580F0C0`). Adding a real `--undo` (copying B's `patches` table shape,
where each entry's `orig` is the vanilla run and each cave zeroes to all-zero) is flagged as the right
fix if a rollback is ever actually needed.

**Regression checks passed 2026-07-20** (re-run after any re-tune): gold-medal a Leadership-capable
unit *while stacked under* a Leadership hero, then split it off — the ability must survive (this is B's
fix, the point of testing it here too); a unit ranking up **alone** gets exactly one level; a unit with
no Leadership standing under a leader still loses the *borrowed* Leadership on leaving (the aura GC
must still work for genuine loans); skill points buy II/III/IV at cost 10 each, `CanExpand` stops at
IV, card/dialog read "Leadership I…IV"; the level-IV attack/defence deltas match the curve table; the
level byte round-trips a save/load.

#### Aura instant-refresh (§8 of the original doc)

**Status: 🔨 APPLIED, UNTESTED (2026-07-20).** Idea and original implementation from a fellow modder
(`patch_leadership_aura_refresh_v1.py`), re-verified against this DLL and adapted as
`build_leadership_aura.py`.

**Problem:** after buying a Leadership level in the hero level-up UI, party units don't get the new aura
bonus until the army next updates (a move, or next turn) — the level applies immediately, only the
*aura* is stale. **Fix:** `THeroUpgradeTE.Execute`'s closing call to `UpdateDefaultAbilities`
(@`0x557854E0`) is repointed to **`cave_auraup` @`0x5580F140`**, which runs the original then, if the
hero's army `IsClass(TArmy)`, calls `TArmy.UpdateFormation` on it directly — the same routine that
already runs on move/turn, just immediate. Verified against this DLL rather than assumed: the `TArmy`
classref global resolves to VMT `0x557130EC`, Delphi name "TArmy"; the `IsClass` guard is vanilla's own
idiom, seen elsewhere (`TAbstractUnit.MovedTo`, `UpdateMoraleValue`). MP-safe: `THeroUpgradeTE` is
already network-distributed and `UpdateFormation` is deterministic (no RNG), so every peer recomputes
the identical aura.

⚠ **The donor's own cave address could not be reused** — `0x5580E120` now holds live
`build_assassin.py` code in this DLL; applying the fellow modder's script unmodified would have
silently destroyed the Monster-Slaying feature. **General lesson: never trust a cave address from
another modder's build — re-scan for free space in your own binary first.** This build sits at
`0x5580F140` instead.

**Revert:** `build_leadership_aura.py --undo` — surgical, repoints the hooked call back to
`UpdateDefaultAbilities` and zeroes `cave_auraup`, touches no backup.

**In-game checklist:** buy a Leadership level on a hero standing in a stack; the other units' attack/
defence should update *immediately* on their cards, without moving or ending the turn.

### D. Leadership IV grants the stack Fearless

**Status: 🔨 APPLIED, UNTESTED (2026-09-01).** Script `build_leadership_fearless.py` (surgical
`--undo`). Binary `AoWEPACK.dpl` only — Fearless is queried by no other module (`AoW.exe`,
`AoWTCPCK.dpl`, `aowInt.dpl` all checked), so no AoWCompat/exe lockstep half exists. Backup
`AoWEPACK.dpl.pre-leadfearless` — use `--undo`, not the backup. Threshold `LEAD_LEVEL=4`, tunable.
Fearless id `0x43`, Panicked `0x6C`, Cause Fear `0x33`.

**What Fearless is:** a plain bit-only passive with no ability class and no data record. It means
exactly one thing — "cannot be given the Panicked status" (the only producers of `0x6C` are the melee
Cause Fear strike and the two Terror CAs; there is no morale-driven panic to be immune to).
`TAbstractUnit.ExecuteLifeMasteryFearRole @0x55780B90` already exempts any Leadership holder from
strategic-map Life Mastery fear **at every level** — that site needs no patch.

**Propagation is free — do not build a new aura.** `TArmy.UpdateFormation` pass 2 (subsection B) runs
over every unit in the army with **no gate**: any member below the army's Leadership maximum already
reads `GetAbilityLevel(unit,0x2E)` at that maximum. `TCombatUnit.SetParty` re-runs `UpdateFormation` at
combat start, so the borrowed level is live in tactical **and** auto-resolve, at zero extra cost — the
same scope Leadership's ATK/DEF bonus already has. ⚠ Consequence: since `UpdateFormation` only runs at
`SetParty`, immunity persists for the **whole battle** even if the Leadership-IV hero dies mid-combat —
consistent with how vanilla already treats the ATK/DEF bonus, not a defect.

**Why NOT to grant the Fearless bit directly** (rejected approach): Fearless has no data record at
all, so there is no `data[+0x0C]` to distinguish "borrowed from the aura" from "inherent" — the *exact*
shape of the Leadership disable bug (B), but strictly worse, since even the `own==0` discriminator
doesn't exist here. A bug in an ad-hoc shadow store could permanently strip *native* Fearless from
undead/elementals. **User ruling 2026-08-31: effect only, no card entry** — accepted cost, since
`ListAbilitiesEx` builds the card from the real bitset and there is no cheap display-only hook.

**Design: five sites, one cave.** Every consumer that matters is byte-identical to pristine, the same
15-byte run (`mov edx,<id>` / `mov eax,<reg>` / `mov ecx,[eax]` / `call [ecx+0xA8]`):

| # | VA | function | id | gates |
|---|---|---|---|---|
| 1 | `0x557668F5` | `TStrikeCA.Generate+0x41` | `0x43` | melee Cause Fear |
| 2 | `0x557F983D` | `TFastCombatTerrorCA.Generate+0x5D` | `0x43` | Terror, auto-resolve |
| 3 | `0x557F99C1` | `TTacticalCombatTerrorCA.Generate+0x29` | `0x43` | Terror, tactical |
| 4 | `0x557F9D4E` | `TTerror.tcGetDamageValueEx+0x0A` | `0x6C` | AI value, tactical |
| 5 | `0x557F9B64` | `TTerror.fcPrefetchCombatCommands+0x44` | `0x6C` | AI value, fast |

Sites 1–3 are the effect; 4–5 are the AI's "is this target worth counting" test — vanilla checks only
Panicked there, never Fearless, so routing them through the same cave both makes the AI correctly
deprioritise a Leadership-IV stack **and** incidentally fixes that pre-existing vanilla gap for
natively-Fearless units too (user ruling 2026-08-31: include 4–5). Each site's `mov edx,<id>` stays; the
following `mov eax,<reg>`/`call [ecx+0xA8]` (7 B) becomes `call CAVE` + 3 nops (still 15 B total).

**The cave** (EAX=combat object, EDX=original id in → AL out, ~40 B, no absolute references at all —
every dispatch is an indirect VMT call, so PIC is free):

```asm
push ebx / mov ebx,eax / mov ecx,[eax] / call [ecx+0xA8]   ; original query (Fearless or Panicked)
test al,al / jne .true
mov  eax,ebx / mov ecx,[eax] / call [ecx+0xB8]              ; GetAbilityOwner -> TAbstractUnit or nil
test eax,eax / je .false
mov  edx,0x2E / mov ecx,[eax] / call [ecx+0x144]             ; GetAbilityLevel(Leadership)
cmp  eax,4 / jl .false
.true:  mov al,1 / pop ebx / ret
.false: xor eax,eax / pop ebx / ret
```

⚠⚠ **The trap: `+0xB0 GetAbilityLevel` cannot be used here — it crashes.** It is not nil-guarded, and
the project's rule ("call `+0xB0` only directly behind a `+0xA8` gate on the same object") is subtler
than it looks: `+0xA8` returns 0 for *both* "nil `[obj+0x4C]`" and "ability not enabled," and this cave
calls its second query precisely when the first returned **false** — so a false `+0xA8` result is *not*
proof of a non-nil owner. **The fix is `+0xB8 GetAbilityOwner`, which is nil-safe on both `TCombatUnit`
and `TCombatObject`** (walls/structures) — test EAX, then dispatch `GetAbilityLevel` on the strategic
unit if non-nil. **Generalisable: a nil-guarded accessor returning false does not discharge the guard
for its ungated sibling** — when a cave needs the same object twice and the first query may
legitimately return false, reach for the pointer-returning accessor and test it, rather than inferring
safety from a boolean.

**Cave `0x5582C000`**, span asserted zero-or-ours to `0x5582C080`. ⚠ The first-choice address
`0x5582B200` was wrong — `build_item_hpmv.py` owns `0x5582B000`–`0x5582B200` and that *is* its
`CAVE_END`; re-scan for free space at build time, don't trust a stated zero-run, since a script's
declared span extends past its last emitted byte.

**Collision audit (all clear, 2026-08-31):** no overlap with `build_lifesteal_roundattack.py`
(`0x5580DCD0`–`E7` region), `build_terror_oncepercombat.py` (`0x557F9B20`/VMT `0x557F625C`, or its caves
`0x5582A000`–`0x5582A16D`), `build_panic_nomelee.py` (`0x55828000`–`68`), or `build_item_hpmv.py`
(`0x5582B000`–`200`). **`C_WRAPTC` interaction with the Terror-once-per-combat feature checked and
benign**: that feature's tactical wrapper is `value = max(1, value>>6)`, which would have re-inflated an
immune target's fresh 0 back to 1 — but its cave short-circuits first (`test eax,eax; je done`
@`0x5582A151`), so a zero stays zero. ⭐ **Generalisable trap from the same feature, worth restating
here since it governs whether sites 4–5 above are worth gating at all**: Terror also overrides VMT
`+0x98` (`fcGetDamageValueEx`) but that override is **dead code** — `fcPrefetchCombatCommands`
accumulates its value inline and never calls it. *An ability overriding a value method is not evidence
that the value method is on the call path* — check the actual caller before gating any virtual.

**Acceptance criteria — checkable without the game:** all five sites read the expected 15 vanilla
bytes pre-write, then `ba<id> / 8b c6|c3 / e8<rel32> / 90 90 90` post-write; the cave disassembles with
`[ecx+0xB8]` (not `+0xB0`) as its second dispatch — the single most important byte in the patch; no
absolute address constant anywhere in the cave span, no drive-letter path; `--undo` restores all five
runs and zeroes the cave, idempotent; `rng_audit.py --owners` prints `ok` (the cave makes no draw); the
neighbouring seven features in the collision audit all still verify as applied afterwards. All of the
above passed 2026-09-01, plus an `--undo`/re-`--apply` sha256 round-trip match.

**In-game checklist (the user's test):** a unit in a Leadership-IV stack, hit by melee Cause Fear, never
becomes Panicked (a Leadership-III stack still does); same for Terror, tactical and auto-resolve; the
hero itself is immune too; a natively-Fearless unit (undead) still shows the Fearless card entry and
stays immune after leaving the stack (the bit was never touched); the AI does not keep re-targeting a
Leadership-IV stack with Terror; save/load — no change expected, nothing is serialised.

### E. Leadership buffs only the OTHER units in the party

**Status: 🔨 APPLIED, UNTESTED (2026-09-16).** Script `build_leadership_others.py`
(`AoWEPACK.dpl`; surgical `--undo`; snapshot `Ziggurat\backups\AoWEPACK.dpl.pre-leadershipothers`,
minted on `--apply` only). Ported from Inioch's `patch_leadership_others_v1.py`
(`Modding Resources/Inioch/share7/patch scripts/`) and his RE note `aowx-leadership.md`.

**Rule:** a unit's Leadership bonus is the highest **own** Leadership level among the **other** units
in its party — never its own. Two leaders buff each other; a leader travelling alone with ordinary
troops gains nothing itself. The ability card splits the two: `Leadership III (+IV received)`, or
`Leadership (+IV received)` for a follower with no own level.

| | site | before | after |
|---|---|---|---|
| A | `0x557661FC` attack-bonus getter | `8b 08 ff 51 70` (`mov ecx,[eax]; call [ecx+0x70]`) | `e8 ff 3d 0e 00` → `cave_blevel` |
| A | `0x55766210` defence-bonus getter | same 5 bytes | `e8 eb 3d 0e 00` → `cave_blevel` |
| B | `0x5578D128` `UpdateFormation` pass 2 | `83 7d f8 00 7e 58` | `e9 13 cf 0b 00 90` → `cave_pass2` |
| C | `0x55722060` `TLeadershipAbility` VMT+0x58 (`GetName`) | `98 52 76 55` (`0x55765298`) | `80 a1 84 55` (`cave_lname`) |

Caves — `0x5584A000`, exclusive `0x400`, new high-water mark (previous: `combatunitguard.py`
`0x55849000`): `cave_blevel 0x5584A000` (28 B), `cave_pass2 0x5584A040` (226 B),
`cave_lname 0x5584A180` (264 B, code + the four suffix literals; pointer table at `0x5584A214`).

- **A** — the bonus level is the owner record's **borrowed** field `[+0x10]` only, never
  `max(own, borrowed)`. `cave_blevel(EAX=ability, EDX=owner)` = `GetAbilityData(owner, [abil+0x0C])`
  then `movzx eax,[rec+0x10]`, 0 if there is no record. The `mov al,[eax+0x5580F0C0/C8]` ladders two
  instructions later belong to `build_leadership4.py` and are untouched; the `.reloc`-covered disp32
  at `0x55766207` is outside the 5-byte window.
- **B** — pass 2 is replaced wholesale. Loop 1 counts the holders of `max1` and finds `max2`, the
  highest own level below it; loop 2 gives each unit `max1`, except the **sole** holder of `max1`,
  which gets `max2`. `SetExternalSource` creates the record and sets the bit but writes the borrowed
  field only when `own < level`, so the cave then forces `[rec+0x10] := target` and **re-fires the
  unit's `VMT+0x90` AbilitiesChanged** — `TUnit` caches its ability bonuses in `[unit+0x44..0x47]`
  and `SetExternalSource` already fired `+0x90` *before* that direct write, so without the re-fire a
  non-hero top leader never sees its received bonus. Own levels are read through `VMT+0x144`
  `GetAbilityLevel`, as pass 1 does, so item-granted Leadership (Crown of Kings) still projects.
  ⚠ Only the **first 6 bytes** are displaced: `0x5578D162` carries a `.reloc` entry (the sole one in
  `0x5578D128..0x5578D186`), so the vanilla pass-2 body stays in place, dead, and the cave resumes at
  the function's shared exit `0x5578D186`. The host pushes EBX/ESI but **not EDI**, so the cave saves
  EDI (also its PIC anchor) and restores ESP exactly before that jump — `0x5578D186` unwinds the SEH
  frame with `pop edx/pop ecx/pop ecx`.
- **C** — `cave_lname` reads the record itself (`own [+0x0C]`, `borrowed [+0x10]`), renders the own
  level by dispatching `GetLevelName` through `VMT+0x10c` (which is `build_leadership4.py`'s
  `cave_lsname @0x5580F000`, so neither feature pins the other's address), and appends
  `" (+<roman> received)"` when the borrowed field is set. The four suffixes are embedded Delphi
  AnsiStrings (refcount −1) reached through a PIC pointer table, the same idiom `cave_lsname` uses
  for the game's own `" I".." IV"`. They are new English text with no vanilla counterpart, so an
  in-DLL constant is the right home — no `ResStr.mld` entry to extend, and a `.pfs` description
  record could not reach a label built by code at query time.

**⚠ Deliberate deviation: Inioch's third change is NOT ported.** He made
`TLeadershipAbility.GetLevel` return the own level only. Here that would break **D** above:
"Leadership IV makes the stack Fearless" derives its answer from `GetAbilityLevel(unit, 0x2E) >= 4`
(`VMT+0x144` → `GetLevel`), which for a *follower* is exactly the borrowed level — own-only would
silently drop every follower out of the Fearless stack, and the leader itself now usually holds
`max2` rather than IV. His motivations do not transfer either: our `CanExpand @0x557663A8` and
`GetInherent @0x55766384` already read `[record+0x0C]` directly, so the hero level-up cap never saw a
borrowed level, and `build_leadership_fix.py` already routes the grant comparison through
`GetInherentLevel`. Consequence kept knowingly: the map editor's ability list still shows a
follower's effective level, as it did in vanilla. His caves (`0x55815D00`) are not reused — his
addresses are picked against his own build and have collided with live Ziggurat code before.

**Coupled text, all updated 2026-09-16:** `Ability.pfs` record 56 tag 5 (via `build_pfs_typos.py`, a
re-tuned row with a tuple `old`) and four hand-written passages in `build_ziggurat_manual.py` (the
design bullet, the ability bullet, `HERO_CHASSIS_LEAD` and `HERO_NOTE_FIX`).

**Checked without the game:** all four sites read their originals pre-write and the patch bytes
after; caves verified all-zero before writing and the `0x5584A288..0x5584A400` growth zone asserted
zero; no `.reloc` entry inside any hook window or cave (the VMT slot is reloc'd by design — the value
is repointed, the entry kept); every cave disassembled and read; `--undo` → re-`--apply` round-trip
reproduces the pre-apply and post-apply md5 exactly; `build_relocfix.py --audit` total 0; no draw, so
`rng_audit.py --owners` is unmoved.

**In-game checklist (the user's test):**
1. Lone Leadership-III hero: card reads `Leadership III`, no ATK/DEF from it.
2. Same hero with three ordinary units: the units read `Leadership (+III received)` and gain +3/+3;
   the hero gains nothing.
3. Leadership-III hero stacked with a Leadership-I hero: III reads `Leadership III (+I received)`
   (+1/+1), I reads `Leadership I (+III received)` (+3/+3), the troops +3/+3.
4. Two leaders at the **same** level: both receive that level.
5. Buying a level in the hero level-up dialog still refreshes the aura at once, numerals still I–IV.
6. A Leadership-IV stack is still Fearless throughout — the coupling the deviation above protects.
7. Crown of Kings on a hero: the party still receives the aura.
8. Split/move/end turn/save-reload: bonuses recompute, no stale "received" text.
9. Auto-resolve: the bonus applies there too.
10. Map editor: assigning and removing Leadership still behaves.

---

## Open items

- ⚠ **`build_turnundead_res.py` has a broken self-verifier.** Running it with no arguments reports
  `[x] cave zone 5580E2A0 not free` against **its own installed patch** — a keystone encoding
  difference: the script's re-verification pass assembles `shr eax,1` as 2 bytes, but the actually
  installed cave (from an earlier re-tune of the DAM formula) has it as 3 bytes, so the byte-for-byte
  comparison fails even though the feature is applied and correct. **Feature A (0.5×level×casterRES) is
  confirmed working in-game (2026-07-16) — this is a verifier defect, not a feature regression.** The
  script does carry a `_variants()` fallback that tries several `(round, shift, scaled)` encodings
  precisely to absorb this class of difference, but it does not currently cover the exact installed
  encoding. Recorded here so a future session doesn't treat the `[x]` as a real alarm; fixing the
  variant generator (or simply widening it to also try the 3-byte `shr eax,1` encoding) would close it.
- Crown of Kings (`ITEMS.PFS 0x54B`) grants Leadership as a bare bit with no data record, so it
  currently confers no bonus and projects no aura — a data fix (add a level-1 record), not yet applied.
  See the Leadership B section above.
- The Command-abilities cross-battle nerf remains unbuilt (SPECULATIVE); if it is ever built, it must
  walk the same 4-entry `CommandAbilityIDs` array the Turn Undead evil-command feature installed at
  `0x5583225C`, not the vanilla 3-entry `0x558E84E4`, or it will silently ignore the new controller id.
- Vision, Dispel Magic and the Leadership-4 ability all deliberately avoid rescaling installed unit/hero
  data to match their new ceilings (author decisions in each case) — if that policy is ever revisited,
  it touches three independent `.pfs`/DLL surfaces, not one.
- Whether `AoWDevEd.exe` shares any of the per-binary call paths touched in this file (Turn Undead,
  debuff cache) has been flagged as unverified in each case, never checked — per the project's
  per-binary rule, do not assume it does or doesn't.

## Failed approaches — do not retry

- **True Seeing v1: a +3 melee/+1 ranged ATK *bonus* for the counter-ability** (2026-07-16,
  `build_trueseeing.py`), superseded in place by the v2 penalty design the same three caves now hold.
  Wrong because vanilla gives invisibility no combat effect at all — buffing True Seeing against an
  inert baseline made *being invisible* a pure liability (only ever got you hit harder, never helped).
  **Generalises: when the base mechanic is inert, buffing its counter is a net nerf to the thing
  itself.**
- **Editing `GetTurnUndeadDamage` itself** to read the caster's RES — impossible, it only ever receives
  the ability level, never the caster; any such fix must hook the *call site* where the caster is still
  in a register. (Turn Undead A.) Also: keystone's `ks.asm()` rejects `;` inline comments in the asm
  source (`KS_ERR_ASM_INVALIDOPERAND`) — keep cave source comment-free.
- **Redirecting `TTurnUndeadAbility` VMT `+0xA4` at `TCommandAbility.fcExecuteCombatCommand`** for the
  evil-command feature — a tidy one-slot swap that inherits Command's retaliation rule for free, but
  routes the to-hit roll through `CombatTouchRole`, which uses the cloned ability's own
  `GetTouchAttack`/`GetLevel` (a constant 6) instead of Turn Undead's real stun chance. Would need a
  private VMT to fix, against the project's PIC rule. (Turn Undead B, §B4.) Kept as the right hook if
  the chance requirement is ever relaxed.
- **Extending Vision's `GetLevelName` jump table** instead of repointing its VMT slot — the table's five
  entries carry `.reloc` entries a cave-hosted replacement would lack, going stale on rebase. **Repoint
  the VMT slot, not the jump table, whenever a lookup table is itself relocated.**
- **Zeroing `TMeleeRound.Calculate`'s `round+0x28` strike count** to block panicked melee — makes
  swings whiff instead of making the order illegal, and `+0x28` belongs to whichever side initiated, so
  it misfires on retaliation rounds (the one case Panic must *not* break).
- **Adding Panicked `0x6C` to `TCombatUnit.GetLocked`** — `GetLocked` is tested for both sides of a
  melee round, so this kills the panicked unit's retaliation too, the exact behaviour the feature exists
  to preserve. **Never express a one-sided "can't initiate" rule via a symmetric incapacity gate.**
- **Patching `AoWE.CreateStrikeCA` ("melee1")** as a Panic injection site — not on the ordinary melee
  path at all (corrected during the Shield/Retaliation facing work).
- **Granting the Fearless bit directly to a Leadership-IV stack** — Fearless has no data record at
  all, so there is no `own==0`-style discriminator to tell "borrowed" from "inherent" when un-granting
  it; a bug in a bespoke shadow store could permanently strip *native* Fearless from undead. Strictly
  worse than the Leadership disable bug it resembles. Read the borrowed level at query time instead
  (Leadership D).
- **Calling `TCombatUnit.GetAbilityLevel` (`VMT+0xB0`) directly behind a `+0xA8` gate that returned
  false** — `+0xB0` is not nil-guarded, and a false `+0xA8` result does not prove the underlying owner
  pointer is non-nil (it returns false for *both* "disabled" and "nil owner"). Use the nil-safe
  `GetAbilityOwner` (`+0xB8`) and test its result instead. (Leadership D, §the trap.)
- **Gating a spell/ability's fast-combat AI value through a VMT slot it overrides**, without checking
  whether that override is actually on the call path — Terror's `fcGetDamageValueEx` (`+0x98`) is a
  perfect-looking override that is dead code; `fcPrefetchCombatCommands` accumulates its value inline
  and never calls it. **An override is not evidence the method is on the path** — a wrapper on a dead
  VMT slot assembles, verifies, and does nothing.
- **"Dark Gift already lifesteals on round attack"** — disproven in-game; it rides the same
  `CA+0x15`-gated first block as vanilla LifeStealing and fails for the identical structural reason.
- **Rewriting the old lifesteal cave to check `GetAbilityEnabled(0x76)` directly under a shared
  offensive gate**, self-contained, no builder changes — tempting because it touches only code the
  project already owned, but fixes only the flag-source half of the problem; the heal still sits in
  Execute's `CA+0x15`-gated first block, which reads 0 for round-attack strikes regardless of the flag.
  Any working fix must move the heal out of that block entirely.
- **Leadership: reverting a `.pre-leadership*` snapshot to re-tune, then re-applying** — this project's
  own procedure, written once when it was true, went stale within days as other features stacked on the
  same DLL, and by the time anyone next needed it the named snapshots no longer existed at all. **Never
  write "revert and re-apply" as a re-tune procedure for anything; rewrite the cave in place instead**
  (verify against either the installed or the new bytes, overwrite, assert the growth zone stays zero).
- **Stopping `ResetExternalSource` from ever clearing the Leadership bit**, as a primary fix for the
  disable bug — by the time that cleanup runs, `UpdateDefaultAbilities` has already discarded the
  inherent record, so there is nothing left to test; this can only limit *future* damage, never repair
  a case that already happened. Fix the grant (Defect A), not the cleanup (Defect B).
