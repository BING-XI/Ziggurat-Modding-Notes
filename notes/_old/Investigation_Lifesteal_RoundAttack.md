# Lifesteal on Round Attack — deep-dive (supersedes the Combat doc's lifesteal section)

> **IMPLEMENTED — CONFIRMED WORKING IN-GAME (2026-07-08)** (both LifeStealing and Dark Gift lifesteal on
> round-attack hits, validated by the user). `build_scripts/build_lifesteal_roundattack.py`,
> backup `AoWEPACK.dpl.pre-lsround`. Two position-independent caves in the clean block at `0x5580DC80`:
> `cave_lsgen` (Generate hook @`0x557668E2`) sets `CA+0x18 |= 0x08`/`0x10` for LifeStealing(0x76)/Dark
> Gift(0xA9) — offensive-only (`CA+0xc`), hit-gated (inside Generate's `CA+0x10!=0`); `cave_lsround`
> (Execute hook @`0x5576678C`) heals the attacker +2 per flag then `jmp 0x557667CF`, **skipping the old
> first-block cave** (`0x5580C150` now unreachable → no double-heal; kept as a revert fallback). Heal
> amounts tunable via `LS_HEAL`/`DG_HEAL` in the script. **Test in-game:** LifeStealing unit AND Dark
> Gift unit both heal on round-attack hits (and normal melee), NOT on defensive/retaliation, NOT ranged.
> Revert: ⚠ **not by snapshot.** `.pre-lsround` was **moved** to `Modding Resources/backups/` on
> 2026-07-29/30 (not deleted) but is layer **7 of 47** — copying it over the DLL would destroy 39 later
> features. Undo surgically instead: restore the `0x5576678C` Execute hook's original bytes and zero the
> cave. (The unreachable old first-block cave @ `0x5580C150` is kept as an in-place fallback.)


**Status: IMPLEMENTED & CONFIRMED WORKING IN-GAME (2026-07-08)** — see the banner above for the
as-built patch. Anchored on the user's own notes about their existing (undocumented) lifesteal work,
then verified instruction-by-instruction against the live DLL + vanilla. This refines/corrects
`Investigation_Combat.md` Feature-2 (that agent didn't have the user's notes and assumed the flag was
the only mechanism).

## The user's existing lifesteal setup (documented here for the first time)
The heal lives in **`TStrikeCA.Execute` @ `0x55766738`** — the per-strike *resolution* method that runs
for **every** melee strike combat-action (normal, round, defensive). Register map at the hook:
`ebx` = the StrikeCA; `edi` = **attacker** (`FindID(CA+0xd)`); `esi` = **target** (`FindID(CA+0xe)`).
The heal is reached only when: strike **landed** (`CA+0x15≠0`), target **IsClass TCombatUnit**, and
target `[0x114]()≠2`.

User's patches (verified live-vs-vanilla):
- **`0x55766796`**: vanilla `je skip` (`74 37`) → **`90 90`** (NOP) — deletes the "must have the
  LifeStealing flag set" gate so units *without* the flag (Dark Gift) still fall through to the heal.
- **`0x557667B8`**: vanilla inline heal (`edi.GetHP()+1 → SetHP`) → **`call 0x5580C150`**.
- **`cave_5580C150`** (heals `edi` = attacker):
  - if `CA+0x18 & 2` (**LifeStealing flag**) → `SetHP(GetHP + 2)`  *(heal amount byte @ `0x5580C162`)*
  - if `CA+0xc & 1 == 0` (**offensive only**) AND `GetAbilityEnabled(edi, 0xA9)` (**Dark Gift**) →
    `SetHP(GetHP + 2)`  *(heal amount byte @ `0x5580C194`)*

So the two abilities use **different gates**: Dark Gift checks the ability directly (offensive-gated);
LifeStealing depends on the `CA+0x18` bit-2 **flag**.

## Does round attack reach this code? YES (verified)
`TRoundAttackAbility.fcExecuteCombatCommand @ 0x55769458` builds each hit with the **global**
`CreateStrikeCA @ 0x557665E4` (arg3 = **0**) and runs it via `TCombat.ExecuteCombatAction` → the CA's
`Execute` VMT = **`TStrikeCA.Execute`**. So the user's cave *does* run on every round-attack hit.
And arg3=0 → `TSingleTargetCA.SetDefensive(CA, 0)` @ `0x557299e4` → `CA+0xc` bit0 **clear** = offensive.

## The root cause (2026-07-08, confirmed by user in-game test): NEITHER works on round attack
The user confirmed in-game that **neither LifeStealing nor Dark Gift heals on round attack**. A deeper
trace (verified at the bit level) found the real, structural reason, and how the *working* effects
(Cursed) differ.

### The confirmed mechanism — two ways an on-hit effect is wired
Every strike CA runs **Generate** (`TStrikeCA.Generate @ 0x557668b4`) then **Execute**. Effect flags
live in `CA+0x18`:
| Effect | Flag set in | Bit | Applied in Execute |
|---|---|---|---|
| stun-ish (attacker ability **0x33**) | **Generate** (hit-gated) | **0x01** (`DAT_55766970`) | block @ `0x557667cf` — flag-only gate |
| **Cursed (Death Strike, attacker 0x77)** | **Generate** (hit-gated) | **0x04** (`DAT_55766974`) | block @ `0x55766806` — flag-only gate |
| **LifeStealing (attacker 0x76)** | **the melee builder** `TMeleeRound.CreateStrikeCA` (normal only) | **0x02** (`DAT_55767f54`) | **first block** (the cave) — gated on `CA+0x15` (strike-result) + target check |

**Why Cursed works on round attack:** its flag is set in **Generate**, which runs for *every* strike
(round included), and it's applied in a plain flag-block. **Why lifesteal doesn't:** its flag is set
**only in the normal-melee builder** (round attack uses the *global* `CreateStrikeCA @ 0x557665E4`,
arg3=0, which sets no `CA+0x18` bits), AND the heal sits in the more-gated first block. Dark Gift rides
that same first block, so it fails too. `TSingleTargetCA.SetDefensive` (`0x557299e4`) sets the
offensive/defensive bit `CA+0xc & 0x01` (`DAT_55729a08`).

### The real fix — make lifesteal an on-hit effect exactly like Cursed
1. **`TStrikeCA.Generate @ 0x557668b4`** — beside the `0x33`/`0x77` checks, add (offensive-only,
   `CA+0xc & 1 == 0`): `HasAbility(0x76) → CA+0x18 |= 0x08`; `HasAbility(0xA9) → CA+0x18 |= 0x10`
   (free bits). Already hit-gated (inside Generate's `if CA+0x10≠0`).
2. **`TStrikeCA.Execute`** — add a flag-block like Cursed's (NOT `CA+0x15`-gated): `if CA+0x18 & 0x08
   → heal attacker +2`; `if CA+0x18 & 0x10 → heal attacker +2`.
This works on all **offensive** strikes (normal + round), stays offensive-only, **retires the current
cave/NOP hack** (the `0x02` path goes vestigial → no double-heal), and needs no HSEPack analysis since
it reuses the proven Cursed path. Confidence ~90%.

---

## Superseded first-pass proposals — do NOT re-try as-is

Both were disproven; kept only so they aren't re-derived.

- **"Dark Gift lifesteal already works on round attack."** Wrong — the user tested it in-game and it
  does not. Dark Gift rides the same `CA+0x15`-gated first block as LifeStealing, so it fails for the
  same reason. (The companion claim, that LifeStealing does *not* work on round attack, was correct.)
- **"Rewrite `cave_5580C150` so the LifeStealing branch checks `GetAbilityEnabled(0x76)` directly,
  under a shared offensive gate — self-contained, no builder changes."** Tempting, because it touches
  only the cave the user already owns and is behaviour-preserving for normal melee. But it does **not**
  work: it fixes only the *flag-source* half of the problem and ignores the other half — the heal still
  sits in Execute's **first block, gated on the strike result `CA+0x15`, which is 0 for round strikes**
  (they resolve before Execute). Any working fix must move the heal out of that block, which is what
  the implemented Cursed-style design does.

Still-valid alternative, rejected on scope alone: hook the global `CreateStrikeCA @ 0x557665E4` to
`or CA+0x18, 2` when `GetAbilityEnabled(0x76)`. That would work and keeps the cave as-is, but adds a
second cave and affects every caller of the global builder instead of staying contained to the
resolution path.
