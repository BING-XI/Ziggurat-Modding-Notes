# Invisibility → attacker ATK penalty, negated by True Seeing

**Status: v2 APPLIED, UNTESTED (2026-07-21).** Build: `build_scripts/build_invis_penalty.py` (`--apply`).
Binary: `AoWEPACK.dpl`. Backup: `AoWEPACK.dpl.pre-invispenalty`.
**v1 (True Seeing → +ATK *bonus*) is superseded — see §7 for why.**

Current rule: **target has Invisibility `0x36` AND attacker lacks True Vision `0x29` → −1 melee ATK /
−3 ranged ATK.** Attack only, no damage change, no floor clamp.

Test: attack a Shadow / Djinn / Air Elemental (see §5) with an ordinary unit and read the combat-log
line — melee should show 1 less ATK and 10pp less hit chance, ranged 3 less. Repeat with a True-Seeing
unit (Priest, Elf Cleric, Beholder…) and the numbers should be unmodified. Verify Monster Slaying /
Champions / Assassin still fire.

## 1. Ability IDs (verified)
| ability | id | role | proof |
|---|---|---|---|
| **True Vision** ("True Seeing") | **`0x29`** | negates the penalty | `TAbstractUnit.TrueVisionRange @0x55780F80`; resourcestring `AoWE.TrueVisionRStr` via `RegisterPassiveAbilities @0x557BC1CC` |
| **Invisibility** | **`0x36`** | triggers the penalty | `TAbstractUnit.ConcealedOnMapF @0x55780524`; resourcestring `AoWE.InvisibilityRStr` |

**Scope = `0x36` only** (user decision, twice). Excluded: the Concealment *enchantment* `0xa2` (what the
Concealment **spell** actually grants — no spell grants `0x36`), and terrain concealments `0x8a–0x91`.
Widening to full `ConcealedOnMapF` semantics would take the trigger from 9 unit types to **68** (8×).

## 2. Vanilla context — invisibility has NO combat effect at all
Exhaustive: every constant-ID `call [reg+0xA8]` (combat `GetAbilityEnabled`) site in the vanilla DPL was
enumerated — 68 of them. The complete set of ability IDs tactical combat ever tests is

```
01 15 33 35 3B 3F 43 5E 60 61 6A 6B 6C 6F 70 71 73 74 76 77 80 81 84 92 93 A0 A1
```

`0x36`, `0x29`, `0x8a–0x91`, `0xa2` are **all absent**. Neither has an ability class (no
`TInvisibilityAbility`); they are inert markers, structurally identical to the Dragon marker `0x3F`. In
vanilla an invisible unit in a tactical battle is a completely ordinary unit. **This mod is the first
combat consequence invisibility has ever had.**

Vanilla's actual payoff is strategic and narrow:
- `TArmy.UpdateConcealment @0x5578C98C` → FullyConcealed **only if every unit in the army is concealed**;
  `TArmyHS.VisibleForSeatedPlayer @0x55790960` then hides the hotspot. One escort breaks it.
- **`TrueVisionRange @0x55780F80` returns 1 for units WITHOUT the ability** — everyone detects invisibles
  at range 1. True Vision buys *range* (→ full sight), not detection. Negation is per-observer, resolved
  on the map, never on the target — the same shape as this mod's per-attacker negation.
- `TPlayerStructure.TrueVisionRange @0x55761060` returns 0 → cities/towers/mines never detect invisibles.

That adjacency rule is **why melee is −1 and ranged −3**: in vanilla the adjacent attacker already sees
you fine, so the distant shooter is the one who should struggle.

## 3. Injection points — three sites, and one trap
Melee has **two** tables (the confirmed "only opportunities worked" lesson); ranged has one. All three
already carried the v1 caves, so v2 only rewrote the cave bodies — the chain plumbing is untouched.

| path | function → cave | attacker | target | ATK slot | penalty |
|---|---|---|---|---|---|
| melee (round/opportunity/ability) | `CreateStrikeCA` → `cave_melee` @`0x5580E070` → exit @`0x5580E0D5` → **`cave_ts_melee` @`0x5580E370`** (46 B) | `EBP` | `ESI` | `BL` — **absolute** | −1 |
| melee (deliberate + retaliation) | `TMeleeRound.CalculateStrikes` → `cave_melee3` @`0x5580E120` → exit @`0x5580E183` → **`cave_ts_melee3` @`0x5580E3B0`** (46 B) | `ESI` | `EDI` | `dword [EBX]` — **DELTA** | −1 |
| ranged + breath (per shot) | hook @`0x5576EB34` → **`cave_ts_rng` @`0x5580E400`** (51 B) → `cave_rng` @`0x5580E190` | `ESI` | `[EBP-4]` | `[ESP+4]` after its one push — **absolute** | −3 |

⚠ **THE TRAP — site 2's slot is a delta, not a value.** `dword [EBX]` is a modifier accumulator: the base
is fetched separately and the delta added (`call [edx+0x6c]; movsx eax,al; add eax,[ebx]` @`0x55767CC7`,
folded 8-bit in `TMeleeRound.CreateStrikeCA` @`0x55767EBA`). A floor clamp here would wipe out Monster
Slaying/Assassin rather than floor the attack. **Never clamp site 2.**

⚠ **Ranged slot offsets differ by frame depth.** At the hook `0x5576EB34` the attack is at `[ESP]`
(pushed @`0x5576EB1D`, = `vmt+0x114` minus the wall penalty). `cave_rng` reaches it as `[esp+8]` because
of its own `push edi; push eax`; `cave_ts_rng` reaches it as `[esp+4]` after one `push eax`. Note
`cave_rng`'s `add byte [esp],1` targets the **damage**, not the attack.

## 4. Why no clamp — the engine is signed end to end
`TDamageCA.Generate @0x55729C46` `movsx edx, byte [ebp+0x10]` (GenerateEx `@0x55729CC2`) →
`TCombatObject.ExecuteDamageRole @0x557269F0`: `GetDefense`, `movsx eax,al` @`0x55726A24`, 32-bit signed
`sub eax,edx` @`0x55726A2C` → `ExecuteDamageRole @0x55725EAC`, every compare signed. There is **no MOVZX
on this path**, so an underflowed `0xFE` reads back as −2, not 254 — the "wraps to always-hits" bug
cannot occur. Attack is never stored in the CA at all (only the rolled damage, at `CA+0x10`), so it is
never serialized or re-read. `hit% = clamp(50+10×(atk−def), 10, 90)` floors a hopeless margin at 10%.
No zero special-case exists — the only `jle → return 0` guard @`0x55725EB3` is on **damage**.

**Vanilla's own three attack penalties are all unclamped, and we copy that idiom:**
- **Parry (`0x71`) @`0x55767BE1`: `sub dword ptr [ebx], 4`** — at site 2, keyed on `EDI` (the *defender*).
  This is literally our mechanic: defender's ability subtracts from attacker's attack. `cave_ts_melee3`
  is that block with `0x71`→`0x36`, −4→−1, plus the True Vision clause. (Vanilla Parry hooks site 2
  **only** — it does not apply to opportunity strikes or ranged. Ours covers all three deliberately.)
- Wall penalty @`0x5576EB1A`: `sub al, [ebp+8]`, = 2 iff `GetWallSituation()==2` (−2 ranged behind walls).
- Vertigo @`0x557BAC5C` / Poisoned @`0x557B9E68` return −2 from `GetAttack` (ability ATK is ShortInt).

⚠ **Do NOT port this to the damage slot** (`[esp+3]` / `dword[ebx+4]` / `[esp]`): damage ≤ 0 hits the hard
`test/jle → 0` guard, so it means *guaranteed zero*, not a reduced hit.

## 5. Prevalence in the installed data (decoded, `re_tools/pfs.py`)
⚠ **The installed `.pfs` data is the Ziggurat mod, not vanilla — no vanilla copy exists on disk.**
(Ability 46 Leadership reads "+2 Attack", the Ziggurat value; vanilla/TS136 is +1.) Binaries are stock.

| | Invisibility `0x36` | True Vision `0x29` |
|---|---|---|
| unit types | **9 / 179** (5%) | **33 / 179** (18%) |
| items | Ring of Invisibility | Helm of Eyes, Ring of True Sight |
| spells | 0 | 0 |
| named heroes | 0 / 50 | 6 / 50 |
| hero level-up cost | 20 pts | **12 pts** |

Invisible units: Djinn (25), Leprechaun (97), Leshy (101), **Shadow (151)**, Incarnate (152), Air
Elemental (224), Aether Barge (231), Fairy Dragon (271), + Human Charlatan (5) at **gold medal**.
The counter is ~3× more common than the trigger and is the cheaper hero pick, so the penalty is well
counterable — *but* heroes can buy Invisibility (20 pts, believed a Ziggurat addition), so the trigger is
not limited to those nine chassis.

## 6. Where the penalty is visible
| surface | shows it? | why |
|---|---|---|
| combat log | **yes** | its tail hook already does `movsx byte [ebp+0x10]` → prints `A-2`, not 253. Both the ATK number and the % move. |
| melee-round DV preview | yes, **site 2 only** | that delta also feeds per-strike CV (`record+0x08` via `0x55726038`) → `TMeleeRound.CalculateDV @0x55767F58`. Vanilla Parry behaves identically. |
| unit info card | no | `TStrikeAbility.GetCombatInfo @0x55766F60` reads base stats (`vmt+0xC0/0xC8`) |
| **AI targeting** | no | `GetOffensiveStrength @0x55766BAC` reads the same base stats — the AI keeps attacking invisible units at full confidence and never values True Seeing |

## 7. Superseded: v1, True Seeing → +3/+1 ATK **bonus** (2026-07-16)
Same three caves, ids in the other order, `jz` polarity, `add` instead of `sub`, no negation clause.
**Why it was wrong:** since vanilla gives invisibility *no* combat effect (§2), a bonus-for-the-counter
made being invisible a **pure liability** — it could only ever get you hit harder, never help. The flip
keeps the same 1-point (melee) differential between a True-Seeing attacker and everyone else while
moving the baseline so invisibility is strictly an advantage. Kept here because the failure mode
generalises: *when the base mechanic is inert, buffing its counter is a net nerf to the thing itself.*

## 8. Revert
⚠ **The snapshots exist but the whole chain is far too deep to use.** `.pre-invispenalty`,
`.pre-trueseeing`, `.pre-assassin` and `.pre-rangedslayers` were **moved** (not deleted) to
`Modding Resources/backups/` on 2026-07-29/30, mtimes intact. Their positions in the now-46-layer
`AoWEPACK.dpl` stack:

| Backup | Layer | Restoring it destroys |
|---|---|---|
| `.pre-assassin` | 11/47 | 35 later features |
| `.pre-rangedslayers` | 12/47 | 34 |
| `.pre-trueseeing` | 20/47 | 26 |
| `.pre-invispenalty` | 26/47 | 20 |

So this doc's original unwind order (assassin → rangedslayers → trueseeing, in order) is still *coherent*
but would cost 35 features to begin. Don't.

To remove the feature now: undo it surgically — restore the three strike-creation injection sites to
their original bytes and zero this script's cave bodies, verify-before-write. `build_invis_penalty.py`
already knows every one of those sites and their original bytes (it writes only the three cave bodies),
so adding an `--undo` mode to it is a small change and the right one. Re-running the script with no args
still verifies the installed state.

**To re-tune the numbers:** edit `MELEE_PENALTY` / `RANGED_PENALTY` in the build script and re-apply —
the script **rewrites its caves in place** and never needed the backup for this (that is exactly why it
was written that way; see CLAUDE.md's worked example). The original instruction here said to restore
`.pre-invispenalty`, delete that backup, then re-apply — that would now cost 21 features and was never
necessary. The caves do resize when the constants change, so keep the free-space assert.
