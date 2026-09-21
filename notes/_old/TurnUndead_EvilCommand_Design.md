# Turn Undead — Evil casters command the undead instead of damaging it

**Status: ✅ CONFIRMED WORKING (2026-09-02)** — user validated in game: launch, seize, revert on
caster death, permanence on survival, strip list, retaliation guard (auto-resolve), damage/info-card.

**Ankh overlay — ✅ CONFIRMED WORKING 2026-09-02**, both combat modes. Needed TWO halves, neither
sufficient alone: (1) an `Ability.pfs` record for `0x89` (key 147, `build_commandedundead_pfs.py`,
cloned from `0x22`'s SEFFECT.ILB sequence); (2) a block in **`TAbstractUnit.ShowEx @0x557812EC`**,
which draws persistent status icons from a **hard-coded chain of 16 ability ids** (`0x30` Seduced,
`0x96` Dominated, `0x95` Charmed, `0x22` Turned Undead, `0x6B` Possessed …) — there is NO generic
"draw every ability's icon" loop. `cave_ankh @0x558322B0` adds `0x89` to the chain via a `call rel32`
retarget at the epilogue (`0x55781A2E`), nil-checking `GetAbility` and asserting record 147 carries a
real image sequence. ⭐ **Any future status ability that should show an overhead icon needs its own
ShowEx block — the `.pfs` record alone draws nothing.**

⚠ A prerequisite crash fix was needed first and is **CONFIRMED WORKING 2026-09-02**:
`build_scripts/build_abiltypes_relocate.py` — unrelated to this feature, see `ID_Ceilings.md`.

**Built as** `build_scripts/build_turnundead_resroll.py`
(§4a-ter, the roll swap + info card) and `build_scripts/build_turnundead_evilcommand.py`
(§4b/§4c registration + seize, §5a strip list, §5c retaliation guard). 15 patch sites in
`AoWEPACK.dpl`; revert with each script's surgical `--undo`, never by restoring a `.pre-*`.
Binary: `AoWEPACK.dpl` only (ability logic is DLL-side; exe involvement unverified — see Open items).

## Request
When Turn Undead is used by an **Evil or Pure Evil** unit/hero, it should not deal holy damage +
stun; it should attempt to **seize control of the undead target**, like Charm / Seduce / Dominate.
Additionally: **if the Turn Undead user dies in the same battle, the seized undead reverts** to its
original allegiance.

## Verdict: FEASIBLE, and the second requirement is FREE

The revert-on-caster-death rule is **already vanilla behaviour of the `TCommandAbility` family**
(`ResetCommandedUnits`, below). Piggybacking on that machinery — which is what the user proposed —
gets it at no cost. The cost is concentrated in one place instead: making the engine *dispatch* the
command machinery for a caster that does not own a command ability (§4).

---

## 1. The two families are unrelated — Possess is a red herring

`TPossessAbility` / `TPossessCA` look relevant and are **not**. `TPossessAbility.Create @0x55769B48`
descends from `TTouchAbility`, id `0x6A`, and `TPossessCA.Execute @0x557696E0` is a **body-snatch**:
it swaps the possessor's combat object onto the victim's strategic unit, and
`TPossessedAbility.CombatObjectDestroyed @0x55769A08` rebuilds the possessor's original body from
unit resource `0x98`. Do not model the feature on it.

The mind-control family is **`TCommandAbility`** (VMT base `0x55720544`), and Dominate / Charm /
Seduce are thin subclasses that only override `Create` / `GetTouchAttack` / `CanTouch(Unit)`:

| ability | class `Create` | own id `[+0x0C]` | paired "…ed" id `[+0x28]` |
|---|---|---|---|
| Seduce | `0x557708D0` | `0x1D` (29) | `0x30` (48) |
| Dominate | `0x557705BC` | `0x1C` (28) | `0x96` (150) |
| Charm | `0x557706FC` | `0x94` (148) | — |
| **Turn Undead** | `0x5576AD20` | **`0x26` (38)** | *none — not a command ability* |

`CommandAbilityIDs @0x558E84E4` = `{0x1D, 0x1C, 0x94}` (3 entries), iterated by `TCommandCA.Execute`
and `TPossessCA.Execute` to strip any pre-existing control from the victim.

## 2. How a seize actually works

`TCommandAbility.fcExecuteCombatCommand @0x557703C0`
→ `CreateCommandCA @0x55770358` (vcall, ability VMT `+0x128`) — rolls to-hit via
  `this.vmt[0x110]` = `TTouchAbility.CombatTouchRole @0x557681B0`, stores the ability's own id into
  `[CA+0x10]`, and forces failure if the target's strategic unit `IsClass(TLeader)`
→ `TCombat.ExecuteCombatAction` → `TCommandCA.Execute @0x5576FC68`
→ on success, and only if `GetSide(attacker) != GetSide(victim)`:
  `GetAbility([CA+0x10]).vmt[0x124]` = **`TCommandAbility.Command @0x5576FE50`**

`Command(ability, commanderCO, victimCO)` does all of it:
- `victimCO.vmt[0x68]` = `SetCombatPlayer(commander's side byte `[commanderCO+0x45]`)` — **the allegiance flip**
- creates `TCommandedAbilityData` on the victim's strategic unit with
  `[+0x0C]`=commanded id, `[+0x14]`=**controller ability id**, `[+0x10]`=commander's combat-object id,
  `[+0x18]`=**victim's original side byte** (this is what a revert restores)
- sets the victim's ability bit for the commanded id (`SetAb`)
- creates or finds `TCommandAbilityData` on the **commander's** strategic unit keyed by the controller
  ability id, and appends the victim's combat-object id to its `TByteList` at `[+0x10]`

Ability VMT slots on the command family: `+0x124` Command · `+0x128` CreateCommandCA ·
`+0x12C` ResetCommandedUnits · `+0x130` Uncommand · `+0xF4` CombatObjectDestroyed · `+0xFC` CombatDone.

## 3. Where requirement #2 already lives

- `TCommandAbility.CombatObjectDestroyed @0x5576FE44` → `this.vmt[0x12C]` =
  **`ResetCommandedUnits @0x5576FF94`**: walks the commander's `TByteList`, resolves each victim with
  `TCombatData.FindID` in the *active* combat, and calls `Uncommand` on each.
- `Uncommand @0x5576FF08` restores `SetCombatPlayer(victim, data[+0x18])` — the stashed original side —
  and strips the commanded ability.
- `TCommandedAbility.CombatObjectDestroyed @0x5576FB6C` handles the mirror case (victim dies).
- `TCommandAbility.CombatDone @0x5576FE28` drops the commander's data record at end of combat, which is
  precisely why surviving control becomes **permanent**.

So "caster dies in this battle ⇒ seized undead reverts; caster survives ⇒ keep it" is the vanilla
Command contract, matching the request exactly. No new tracking is needed.

⚠ Contrast with `Command_Abilities_Nerf.md`, which asks for the *harder* cross-battle version
(revert whenever the controller dies, even turns later). That is a separate, still-unbuilt feature;
this request needs only the within-battle rule, which is free.

## 4. The one real obstacle: dispatch requires the caster to OWN a command ability

Both the notification and the revert are gated on ability **ownership**:

- `TAbilityOwner.TriggerCombatDone @0x5574FEC4` (and its destroyed-side counterpart) iterates ability
  ids and calls `owner.vmt[0x4C](owner, id)` — *does this owner have ability `id`* — before invoking
  the ability's hook. An ability the owner does not have is **never notified**.
- `ResetCommandedUnits` re-checks it itself: `commanderStrat.vmt[0x148](strat, [ability+0x0C])`
  (`GetAbilityEnabled`) and returns immediately if false.

⇒ **Reusing Dominate's id (`0x1C`) does not work.** An Evil cleric does not own Dominate, so on its
death the trigger skips Dominate entirely and the revert silently never fires — requirement #2 would
be quietly broken while everything else appeared to work. Granting the caster real Dominate is also
out: it would become a usable ability, and Dominate's `CanTouchUnit` permits *living* targets.

⇒ **`TTurnUndeadAbility` cannot be promoted into a command ability either.** Its VMT
(base `0x5571FDFC`) **ends at `+0x124`** — verified: the dwords from `+0x124` are the literal bytes
`\x12"TTurnUndeadAbility"`, the Delphi class-name shortstring. There are no `+0x124`/`+0x12C`/`+0x130`
slots to repoint. Extending it means relocating the whole VMT into a cave, which needs ~78 new
`.reloc` entries — against the project's PIC rule and not worth it.

### The workable shape

Mint a **new, hidden command ability `N`** (a cloned `TDominateAbility`/`TCommandAbility` *instance*,
per the "clone the INSTANCE, not the class" precedent in `Embrittlement_Spell.md`) plus its paired
commanded-status ability `M`. Then hook **`TTurnUndeadCA.Execute @0x5576AC00`** — *not*
`fcExecuteCombatCommand` (see "Rejected alternative" below).

**Design decision (user, 2026-09-01): the seize chance must be whatever already governs Turn
Undead's stun.** §4a shows that is a single already-computed field, so the hook reuses it verbatim
rather than reproducing any maths.

#### 4a. What governs the stun — and therefore the seize

`CreateTurnUndeadCA @0x5576B528` rolls to-hit `HitRole(attackerATK − targetDEF)`; on a hit it calls
`TDamageCA.GenerateEx @0x55729C98` with `(attacker, target, 1, 0x40, damage, touchAttack)`.
`GenerateEx` calls `target.vmt[0x114]` = `ExecuteDamageRoleEx` and stores the **rolled damage** in
**`ca[+0x10]`** — that one field is simultaneously the amount *and* the success flag.

`TTurnUndeadCA.Execute @0x5576AC00` then:
- calls `TDamageCA.Execute @0x55729D14`, which deducts HP (`attacker.vmt[0x108]`, result → `ca[+0x15]`)
  and applies damage-type statuses (`ca[+0x13]`), then
- **`if (ca[+0x10] != 0)`** and the victim's `[+0x47] & 1` is clear, grants the victim ability
  **`0x22` (34)** — the flee/panic status — stashing the attacker's player slot in `data[+0x0F]`.

⇒ **The stun fires exactly when `ca[+0x10] != 0`** (and the victim survived). Hanging the seize on
the same test makes the two chances identical by construction, with no duplicated roll and no second
RNG draw.

#### 4a-bis. The full vanilla chance chain (decoded 2026-09-01)

Two rolls stand between using the ability and the stun landing — **not one**:

1. **To-hit**, in `CreateTurnUndeadCA`: `HitRole(attackerATK − targetDEF)`.
   `HitRole @0x55725D98` = `clamp(diff × slope + 50, 10, 90)` %, then `RandInt(100) < chance`.
   ⚠ The **live** DLL is Ziggurat's 5 %/point (`6b c0 05` = `imul eax,eax,5`); vanilla was ×10.
   On a miss `GenerateEx` is never called, so `ca[+0x10]` stays 0 — no damage, no stun.
2. **Damage roll**, inside `GenerateEx` → `ExecuteDamageRoleEx @0x55726A6C`. Turn Undead passes
   `param_4 = 1`, which selects **`GetResistance` (combat VMT `+0x74`)**, not Defence — so
   `ExecuteDamageRole @0x55725EAC` is called with `diff = touchAttack − targetRES`, where
   `touchAttack` is the level table 9/10/11/12 (`GetTouchAttack @0x5576B1F4`). That routine:
   `r = RandInt(20)`; `r < 2` ⇒ **0** (flat 10 % auto-fail); `r ≥ 18` ⇒ full damage (10 % auto-max);
   otherwise a ramp against `t`, returning 0 when `r < t` or `t > 17`.
   Result halved (round up) if the target has partial protection to the holy bit.

   ⚠⚠ **`t` is `10 − diff` in the LIVE DLL, not vanilla's `10 − 2×diff`.** `build_hitslope5.py`
   halved this site as one of its seven: vanilla `8b c6 03 c0` (`mov eax,esi; add eax,eax`) is live
   `8b c6 90 90` — the `add eax,eax` **nop-ed out**. Verified by byte-diff against
   `AoWEPACK_original_backup.dpl` on 2026-09-01. Consequences, both easy to get wrong:
   - each point of stat difference is worth **5 percentage points**, not 10;
   - the roll's usable band is **diff ∈ [−8, +8]**; outside it the result pins at 10 % / 90 %.
   Any analysis that quotes the Ghidra decompile's `param_2 * -2 + 10` is describing vanilla and is
   wrong for this install.

⇒ **The target's Resistance already gates the stun**, through roll 2. A successful ATK-vs-DEF check
alone does not stun.

Then `TTurnUndeadCA.Execute` requires `(victim[+0x47] & 1) == 0`. Per `Ghidra_Field_Catalogue.md`,
`+0x47` is `state_flags` with *alive iff `(x & 0x09) == 0`* — i.e. **the victim must have survived
the damage**. Given that, the answer to "does it always stun if it lands any damage?" is **yes**:
nonzero damage + target still alive ⇒ stun, unconditionally.
⭐ In the evil branch `TDamageCA.Execute` is skipped, so the victim cannot die from this attack and
the survival clause is automatically satisfied.

#### 4a-ter. Requested change: make roll 2 an opposed RES check (BOTH branches)

**User decision 2026-09-01: swap `touchAttack` for the caster's Resistance in the existing damage
roll**, so roll 2 becomes a true opposed `casterRES − targetRES` check. Chosen over adding a third
`HitRole` gate, because roll 2 is *already* the target-RES term and a separate gate would count the
target's Resistance twice.

The insight that makes this the cheapest option: `ExecuteDamageRoleEx` is already called with
`param_4 = 1`, so the **defender's** side of roll 2 is `GetResistance`. Only the *attacker's* side is
wrong for this purpose — it is `GetTouchAttack(level)`, the flat 9/10/11/12 level table, not a stat.
Replace that one value and the opposed check exists with **no new gate and no new RNG draw**.

##### The patch site (live bytes verified 2026-09-01)

In `CreateTurnUndeadCA @0x5576B528`, live disassembly:

```
5576B565  mov  edx, [ebx+0x0c]        ; ability id (TurnUndead = 0x26)
5576B568  mov  eax, esi               ; esi = attacker combat object
5576B56A  mov  ecx, [eax]
5576B56C  call [ecx+0xb0]             ; GetAbilityLevel -> eax = level
5576B572  mov  [esp], eax
5576B575  mov  edx, [esp]             ; edx = level
5576B578  mov  eax, ebx               ; ebx = this (the ability)
5576B57A  mov  ecx, [eax]
5576B57C  call [ecx+0x10c]            ; GetTouchAttack(level) -> eax   <== REPLACE (6 B: ff 91 0c 01 00 00)
5576B582  push eax                    ; 7th arg = "attack" fed to ExecuteDamageRoleEx
5576B589  call 0x5580e2a0             ; [already patched] damage cave -> 0.5*level*casterRES
```

Register map at that point: **`ebx` = ability (this) · `esi` = attacker combat object ·
`ebp` = target combat object · `edi` = the CA.**

Replace the 6 bytes at **`0x5576B57C`** with `call rel32` + one `nop` (`E8 xx xx xx xx 90`) into a
small cave.

**Attacker term (user spec, 2026-09-01): `casterRES × mult(level)`, mult = 1 / 1.2 / 1.4 / 1.6 for
Turn Undead I–IV.** As integer maths that is exactly `casterRES × (4 + level) / 5`.
⭐ The level is already in **`EDX`** at this call site (`mov edx,[esp]` @ `0x5576B575`), so no extra
lookup is needed — which is why the level term costs nothing.

```
push  edx               ; save level (EDX = level on entry)
mov   eax, esi          ; attacker combat object
mov   edx, [eax]
call  [edx+0x74]        ; TCombatUnit.GetResistance -> AL
movzx eax, al           ; MANDATORY - returns in AL only
pop   edx
movzx edx, dl           ; level 1..4
add   edx, 4            ; 5..8
imul  eax, edx          ; casterRES * (4+level)
add   eax, 2            ; round to nearest
mov   ecx, 5
xor   edx, edx
div   ecx               ; eax = round(casterRES * mult)
ret
```

Max intermediate `255 × 8 + 2 = 2042` — no overflow, and `xor edx,edx` before `div` is mandatory.
⚠ Disassemble the assembled cave (`--dis`) before trusting it — see the keystone `push imm8` trap.

Register-only ⇒ position-independent. It clobbers only EAX/ECX/EDX, and the caller reloads both ECX
and EDX immediately afterwards, so EBX/ESI/EDI/EBP are untouched. ⭐ This is the same ABI the
existing damage cave at `0x5580E2A0` already uses successfully **from this very call site**, so the
calling convention is proven rather than assumed.

##### Resulting odds (live slope), and where they saturate

Chance the stun/seize roll lands, after a successful to-hit:

| casterRES | vs tRES | L1 | L2 | L3 | L4 |
|---|---|---|---|---|---|
| 8 | 8 | 50% | 60% | 65% | 75% |
| 8 | 20 | 10% | 10% | 10% | 15% |
| 12 | 12 | 50% | 60% | 75% | 85% |
| 12 | 20 | 10% | 20% | 35% | 45% |
| 20 | 20 | 50% | 70% | 90% | 90% |
| 20 | 12 | 90% | 90% | 90% | 90% |
| 30 | any ≤20 | 90% | 90% | 90% | 90% |

Two things this fixes and one it doesn't:

- ✅ **Level matters again** — the regression from the plain-RES swap is gone.
- ✅ **It repairs an existing Ziggurat gap.** Today's Turn Undead uses `touchAttack` 9–12, a vanilla
  1–10-scale number, against a *doubled* RES stat — so against undead with RES ≥ 20 it is floored at
  the 10 % auto-max and effectively does nothing. Current level-4 odds are 90/70/50/30/10/10/10 % at
  target RES 4/8/12/16/20/24/28. Putting caster RES on the attacker side closes that.
- ⚠ **It saturates for strong casters.** The roll's whole usable band is ±8 points of difference, and
  `casterRES × 1.6` at RES 20 already adds +12. From roughly casterRES ≥ 20 the result pins at 90 %
  against most targets and **ability level stops mattering** — exactly where high-RES heroes live.
  If that flat top is unwanted, halving the difference (`(casterRES × mult − targetRES) / 2`) spreads
  the same design across the full RES 0–40 range; it is one extra `shr` in the cave. Flagged, not
  assumed — the spec above is built as given.

##### Consequences to build alongside

- ⚠ **The info card must move with it.** `GetCombatInfo` (wholly replaced by
  `build_turnundead_res.py`'s Part-2 cave at `0x5580E300`) writes the displayed **ATK** from
  `GetTouchAttack(level)`. Once the roll uses caster RES, the card must show caster RES too, or
  display and behaviour diverge — the same "display == damage dealt" principle that doc already
  established for DAM. This is an edit *inside the existing cave*, not a new one.
- This also shifts the damage **amount** for non-evil casters: `ExecuteDamageRole` uses the same
  difference for its zero-threshold *and* its ramp. Ziggurat already scales Turn Undead damage off
  caster RES (`0.5 × level × casterRES`), so the direction is consistent, but the resulting curve is
  a genuine balance change and needs an in-game feel check.
- ⚠ `GenerateEx` takes the attack argument as a **`char`** and sign-extends it. RES above 127 would
  read negative. Not reachable at current clamps (hero RES caps at 40), and vanilla `touchAttack` had
  the identical property — noted only so it is not rediscovered as a bug.
- Turn Undead's ATK is otherwise untouched: roll 1 stays `HitRole(attackerATK − targetDEF)`.

#### 4b. The hook

Cave at `TTurnUndeadCA.Execute`; resolve the attacker with `TCombatData.FindID(combat, ca[+0x0D])`
and read combat-object VMT **`+0x90`** = `TCombatUnit.GetAlignment` (forwards to strategic `+0xFC`):

- **Not `alEvil (4)` / `alPureEvil (5)`** ⇒ fall through to vanilla, unchanged.
- **Evil** ⇒ **skip `TDamageCA.Execute` entirely** (this is what suppresses the HP loss *and* the
  damage-type statuses — "controls instead of stun/vertigo/damage"), then if `ca[+0x10] != 0`, call
  **`TCommandAbility.Command @0x5576FE50`** with `(abilityN, attackerCO, victimCO)` in place of
  granting ability `0x22`.

⭐ Calling `Command` **directly** — rather than routing through `CreateCommandCA` — is what keeps this
build small: `CombatTouchRole`, `GetTouchAttack` and `GetLevel` are never consulted, so ability `N`
needs **no private VMT** and can stay a plain cloned instance sharing `TDominateAbility`'s VMT.

Because `Command` is called directly, three things `TCommandCA.Execute @0x5576FC68` normally does
must be replicated in the cave or consciously dropped:
1. **`GetSide(attacker) != GetSide(victim)`** guard (`GetSide @0x55726660`) — **replicate**; without
   it an already-friendly undead could be "seized".
2. the two loops over `CommandAbilityIDs @0x558E84E4` calling `vmt[0x12C]`/`vmt[0x130]` on each of
   Seduce/Dominate/Charm to **strip an existing control** from the victim — replicate, or a unit
   already Dominated by a third party ends up with two controllers.
3. commander gains the victim's level as experience (`attacker.vmt[0x98]/[0x9C]`, victim `vmt[0xA0]`)
   — optional, a balance choice.

#### 4c. Setting the caster's bit is mandatory

`Command` creates the commander's *data record* keyed `N` but **never calls `SetAb` on the
commander** (real Dominate users already own the bit). So the cave must set the caster's ability bit
`N` before/at the first seize, or §4's two ownership gates both fail and the revert never fires.

The bit persists (it is serialised); that is harmless — in later battles `GetAbilityData` returns 0
and `ResetCommandedUnits` no-ops — but ability `N` must be made **invisible** on the unit card and
in level-up selection (`[+0x20]` selection mask = 0; ⚠ `Ability.pfs` tag 9 overwrites the cave's
mask — see the ability-selection-mask notes).

#### Rejected alternative: redirect `fcExecuteCombatCommand`

Repointing `TTurnUndeadAbility` VMT slot `+0xA4` (VA **`0x5571FEA0`**, holds `0x5576B5C0`; verified
**unpatched** — byte-identical `c0 b5 76 55` in the live DLL and `AoWEPACK_original_backup.dpl`) at
`TCommandAbility.fcExecuteCombatCommand @0x557703C0` with `this` swapped to ability `N` is a tidy
one-slot swap — `fcExecuteCombatCommand` is `+0xA4` in *both* classes — and it inherits Command's
retaliation rule for free. **But it routes the roll through `CreateCommandCA` → `CombatTouchRole`,
which uses `N`'s own `GetTouchAttack`/`GetLevel` and so does *not* reproduce Turn Undead's stun
chance.** Matching the stun would then require a private VMT for `N` (~78 new `.reloc` entries,
against the project's PIC rule). Keep this address recorded — it is the right hook if the chance
requirement is ever relaxed.

## 5. Targeting needs no work

`TTurnUndeadAbility.CanTouchUnit @0x5576ADC4` already gates on
`GetUnitType() < 2` **and** (`GetRace() == 0x0B` **or** `GetAbilityEnabled(0x81)`) — i.e.
**undead only**. `TCommandAbility.CanTouchUnit @0x55770068` only requires `GetUnitType() != 2`
(`utMachine`), which Turn Undead's gate already implies. Charm's gate is the exact complement
(`GetRace() != 0x0B` and not `0x81`), confirming `race 0x0B` + `ability 0x81` is the engine's
undead test. Because only the *execute* slot is redirected, the UI, AI targeting and range checks
keep using Turn Undead's own gates.

Strategic-unit VMT slots used by those gates (resolved from the export table, **not** combat-object
slots — an easy mix-up): `+0xA4` GetRace · `+0x10C` GetGender · `+0x114` GetUnitType ·
`+0x148` GetAbilityEnabled · `+0xCC` GetResistance · `+0x160` SetExperience · `+0x1AC` Killed.

`TUnitType` = {0 `utHumanoid`, 1 `utCreature`, 2 `utMachine`}.
`TAlignment` = {0 `alPureGood`, 1 `alGood`, 2 `alPureNeutral`, 3 `alNeutral`, **4 `alEvil`,
5 `alPureEvil`**, 6 `alNone`} — so the caster test is `(align - 4) <= 1` unsigned.

## 5a. The strip list — why a fourth command ability MUST be registered in it

`TCommandCA.Execute` and `TPossessCA.Execute` each run two loops over
`AoWE.CommandAbilityIDs @0x558E84E4` = `{0x1D Seduce, 0x1C Dominate, 0x94 Charm}`, calling
`vmt[0x12C]` (`ResetCommandedUnits`) then `vmt[0x130]` (`Uncommand`) on each, to strip existing
mind-control off a victim before taking it.

⭐ **Vanilla's correctness rests on that list being complete, not on the abilities sharing anything.**
Whichever ability holds the victim, the loop invokes *that ability's own* `Uncommand`, and `Uncommand`
cleans the commander's byte list keyed on `[ability+0x0C]` — its own id, which by construction matches
the commander's record. Seduce-vs-Dominate is clean for exactly this reason.

Adding a fourth command ability without adding it to the list breaks the invariant: nothing ever calls
*our* `Uncommand`, so an enemy taking a unit we hold leaves our record live and the victim's stashed
original side stale — and on the wrong death order the unit is handed permanently to the wrong player.

⚠ **There are SIX loops, not four.** `CombatSpells.TMindDecayCA.Execute` reaches the array through a
**DATA pointer cell at `0x558E91FC`** (a cross-unit imported-symbol slot), not an immediate, so a byte
scan for `mov reg, 0x558E84E4` misses it entirely. Census of all 7 pristine references:

| site | how | patched? |
|---|---|---|
| `TCommandCA.Execute` loops 1/2 | `mov esi,imm32` @ `0x5576FCD9` / `0x5576FD05` | yes |
| `TPossessCA.Execute` loops 1/2 | `mov esi,imm32` @ `0x55769717` / `0x55769743` | yes |
| `TMindDecayCA.Execute` loops 1/2 | via cell `0x558E91FC` | yes (the **cell** is retargeted) |
| `TCombatUnit.CommandingTargetPriority` | `imm32` @ `0x55725886` | **no** — AI target *scoring* |
| `TCombatUnit.CommandingTargetStrength` | `imm32` @ `0x557258DA` | **no** — AI target *scoring* |

The two AI scorers are left on the vanilla 3-entry array deliberately: adding our id there changes how
the AI *values* a target, a balance decision, not a correctness one.

The fix installs a 4-entry copy at `0x5583225C` and raises six `mov ebx,3` → `4`. The vanilla array is
left byte-identical for the AI scorers. Verified: the cell has exactly **two** readers (both the Mind
Decay loops, in live and pristine), sits in a reloc-covered per-unit import table, and is **never
written by any code in the module** — so a same-module retarget survives load.

⚠ **The array patch and the ability registration MUST apply and revert atomically.** The patched loops
call `GetAbility(0x88)` then a vcall on the result; `GetAbility` returns nil for an unregistered id and
the caller's `mov ecx,[eax]` faults. Undoing the registration alone would crash every vanilla
Dominate/Seduce/Charm/Possess/Mind Decay in ordinary play. Both live in `build_turnundead_evilcommand.py`
behind one state verdict.

⚠ **Our own cave's strip loops need the 4-entry array too** — otherwise a *second* evil Turn Undead
caster seizing what the first holds reproduces the identical defect one attacker along.

⚠ **The interaction with Mind Decay is one-directional.** Mind Decay holds its victim by granting
ability `0x83` "Decay" directly (`0x557F84F8`), with no `TCommandAbilityData` pair and no controller
ability id — so `0x83` structurally *cannot* be strip-listed. Mind Decay taking our victim strips us;
our seize does **not** clear `0x83` off a Mind-Decayed victim. Vanilla Dominate has the same gap, so
this is not a regression.

## 5b. ⭐⭐ Why the AI never fires this ability — and the constraint that keeps it that way

`TFastCombatUnit.fcExecute @0x55744268` enumerates **every enabled ability id** on the strategic unit
and calls `vmt[0xA0]` on each, so it genuinely reaches `0x88` once the caster owns the bit (`AbilTypes`
does not gate it — that table is in `AoWTCPCK.dpl` and fast combat never consults it).

It produces nothing, because `TCommandAbility.fcGetDamageValueEx @0x55770274` →
`TTouchAbility.CombatTouchRoleProbability @0x55768234` reads `vmt[0x10C]` `GetTouchAttack` and checks
it against a sentinel at `0x5576827B`:

```
55768270  call [ecx+0x10c]      ; GetTouchAttack
55768276  movsx eax, al
5576827B  cmp  ebx, -0xa        ; the sentinel
5576827E  je   0x5576829e       ; -> xor eax,eax  (probability 0.0)
```

`0x88` is a plain `TCommandAbility`, which does **not** override `GetTouchAttack`; VMT `+0x10C` is
`0x557680CC` = `mov al,0F6h; ret` = **−10**. Probability 0.0 ⇒ `fcPrefetchCombatCommands` skips every
target. `CombatTouchRole @0x557681B0` carries the identical sentinel, so a hand-queued command would
always miss too.

⭐⭐ **This safety is load-bearing on `0x88` having NO private VMT.** The design's "clone the instance,
share `TCommandAbility`'s VMT" decision is therefore a *correctness* choice, not merely a size one.
**Never give `0x88` a private VMT with a real `GetTouchAttack`** — it would instantly become a generic
Dominate that the auto-resolve AI fires at any non-machine living enemy, since
`TCommandAbility.CanTouch`/`CanTouchUnit` impose **no undead gate and no alignment gate**. The undead
restriction lives only in `TTurnUndeadAbility.CanTouchUnit`, which this path never reaches.

## 6. Traps found during this investigation

- ⚠ **Possess ≠ mind control.** `TPossessAbility` is a body-snatch; do not build on it (§1).
- ⚠ **`ResetCommandedUnits`'s ownership gate is the whole difficulty** (§4). A build that skips it
  passes every static check and fails only the in-game "kill the cleric" test.
- ⚠ **`TTurnUndeadAbility`'s VMT ends at `+0x124`** — the class-name string sits where Command's
  slots would be. Don't plan on repointing `+0x124`/`+0x12C`/`+0x130` there.
- ⚠ **`CanTouchUnit`'s `param_3` is a STRATEGIC unit; `CanTouch`'s is a COMBAT object** (it derefs
  `param_3[0x13]` = `+0x4C`). Resolving `+0x114` against the combat VMT gives `ExecuteDamageRoleEx`
  and reads as nonsense. Per the field-catalogue rule: an offset means nothing without its class.
- ⚠ **`TUnit.GetAlignment @0x55782770` returns `alPureEvil` (5) for any unit with ability `0x6B`
  (Possessed)** — a possessed unit therefore qualifies as an Evil caster. Engine quirk, cosmetic here.
- ⭐ **`ca[+0x10]` is the damage amount AND the success flag.** `TDamageCA.GenerateEx` writes
  `ExecuteDamageRoleEx`'s rolled damage there; `TDamageCA.Execute` deducts HP only when it is
  nonzero, and `TTurnUndeadCA.Execute` gates the stun on the same field. That single field is why
  "same chance as the stun" costs nothing to implement — but also why **you cannot zero the damage
  to suppress it**: a zero rating makes the roll fail and the seize never fires. Suppress the effect
  by **skipping `TDamageCA.Execute`**, never by reducing the damage input.
- ⚠⚠ **`fc`-prefixed methods are AUTO-RESOLVE ONLY — manual tactical combat re-implements them in
  `AoWTCPCK.dpl`.** This is the single most misleading thing in this feature's call graph and it
  invalidated a round of test instructions. See §5c; the guard built for retaliation governs only
  fast combat, because `fcExecuteCombatCommand` has exactly one caller in the whole package.
  ⭐ **Generalise it:** before hooking any `fc*` method, establish which combat mode it serves and
  find the manual counterpart. `cave_exec` is on *both* paths only because it hooks the **CA**
  (`TTurnUndeadCA.Execute`), which both modes reach through `TCombat.ExecuteCombatAction`.
- ⚠ **`CombatTouchRole` reads `ability.vmt[0x70] GetLevel(owner)`** and feeds it to
  `GetTouchAttack`. `TDominateAbility.GetTouchAttack @0x55770664` **ignores it and returns a constant
  6**. This is why the `CreateCommandCA` route cannot reproduce Turn Undead's stun chance without a
  private VMT for `N` — the reason that route was rejected (§4).
- ⚠ Two ability ids are needed (`N` controller + `M` commanded). **Measure them at build time** with
  `check_id_free()`; never quote a free-id number from a doc (`Ability_ID_Budget.md` has gone stale
  twice; a taken id gives a bare `Runtime error 217` at init).

## 5c. The retaliation guard — and ⚠⚠ it governs AUTO-RESOLVE ONLY

Vanilla Turn Undead retaliates whenever the target still stands (`GetEnabled`, combat VMT `+0x60`);
`TCommandAbility` retaliates only when its CA **failed** (`cmp byte [ebx+0x14],0` @ `0x557703EF`).
A successfully seized undead was therefore getting a free swing at its new owner.

**The guard** replaces the 7-byte run at **`0x5576B5EC`** (`8b c3 8b 10 ff 52 60`) with
`call cave_retal` + 2 nops; the existing `test al,al / je 0x5576B619` consumes the returned AL.
No `.reloc` entry falls inside that run. Matrix implemented:

| caster | roll | target enabled | retaliate? |
|---|---|---|---|
| any | — | no | no *(vanilla)* |
| any | failed | yes | yes *(vanilla, and Command's rule too)* |
| non-evil | succeeded | yes | yes *(vanilla, deliberately unchanged)* |
| **evil** | **succeeded** | yes | **no** ← the guard |

Both fallback paths (nil `FindID`, disabled target) fail **toward** retaliation, i.e. toward vanilla.

### ⚠⚠ Scope: this is fast combat only, and manual tactical already had the guard

`TTurnUndeadAbility.fcExecuteCombatCommand @0x5576B5C0` has **exactly one caller in the entire
package** — `AoWE.TFastCombatUnit.fcExecute @0x5574445E` — and no other module imports it.
Manual tactical combat re-implements the whole sequence:

**`AoWTCPCK.dpl` → `CombatTE.TCAbTouchMoveTE.LastMove @0x0040A7ED..0x0040ABBE`**
```
0040A811  call CreateTurnUndeadCA           ; builds the CA itself
0040A822  call TTurnUndeadCA.GetSuccessfull ; -> [TE+0x61]
0040A840  call TCombat.ExecuteCombatAction  ; -> TTurnUndeadCA.Execute -> cave_exec (the seize DOES run)
0040AB20  cmp  byte ptr [eax+0x61], 0
0040AB27  jne  0x40AC13                     ; SUCCEEDED -> no retaliation  <-- Command's rule, already
```

So manual tactical **has never** given a retaliation after a successful Turn Undead — for any
alignment. The guard closed a gap that existed only in auto-resolve, and the user-visible goal ("a
seized undead does not swing back") now holds in both modes.

⚠ **Consequence for testing, and the reason this is recorded so prominently:** testing the guard in
a *manual* battle proves nothing. The seized unit will not retaliate whether the guard works or not,
and the matrix's third row (a non-evil caster's successful stun *does* draw retaliation) will look
broken there, because manual combat never granted it. **Test the guard by auto-resolving.**

⚠ `cave_exec` can bail *after* the `ca[+0x10] != 0` test (nil victim, same side, nil `GetAbility`),
in which case no seize happened yet `cave_retal` still suppresses retaliation. That is the matrix
implemented literally, not a defect; normal targeting cannot reach the same-side case because
`TTouchAbility.CanTouch @0x557682AC` requires opposing sides.

## 7. Open items

- ~~Design: what governs the seize chance?~~ **Settled: whatever governs the stun**, `ca[+0x10] != 0` (§4a).
- ~~Opposed RES check: additive or replacing?~~ **Settled: swap `touchAttack` for caster RES** (§4a-ter).
- ~~Update the info card in the same build~~ **Done** — `build_turnundead_resroll.py` patches
  `0x5580E31B` inside the existing cave at `0x5580E300`.
- ~~Resolve the retaliation risk~~ **Done, scoped to auto-resolve** (§5c).
- ~~Two-controller / strip-list defect~~ **Done** (§5a) — 11 sites, six loops incl. Mind Decay.
- ⚠ **The evil branch skips `TDamageCA.Execute`, so roll 2 still decides the seize but deals no
  damage.** Confirm that reads correctly in play: an evil caster's seize odds are
  `HitRole(ATK−DEF)` × `ExecuteDamageRole(casterRES − targetRES)`, with the damage magnitude
  computed and then discarded.
- Decide whether the commander should gain the victim's level as XP, as `TCommandCA.Execute` does
  (§4b item 3) — a balance call, not a correctness one. Currently **omitted**.
- ⚠ Still unverified: whether any **humanoid undead has gender 0**, which would let vanilla **Seduce**
  target it. Charm cannot (it excludes undead explicitly); Seduce has no undead test at all (§5).
  The check is the gender byte at unit-resource `+0x31` for undead records in `Unitres.pfs`.
- Verify no `AoW.exe` / `AoWTCPCK.dpl` involvement in the Turn Undead ability path (per-binary rule).
- Decide whether the **Turn Undead combat spell** (`CombatSpells.TTurnUndead @0x557F7B94`, a separate
  class from the ability) should follow the same rule. Out of scope as requested; flagged so it isn't
  a surprise.
- Confirm ability `N` stays off the unit info card once its selection mask is 0.
- A cave that runs at package init must be proved by **launching the exe** — static checks cannot see
  init-time faults (Embrittle precedent: runtime error 216 with every static check green).

## Key addresses

| what | VA |
|---|---|
| **hook: `TTurnUndeadCA.Execute`** (chosen) | **`0x5576AC00`** |
| `TTurnUndeadCA.GetSuccessfull` (reads `ca[+0x10]`) | `0x5576ABF8` |
| `TDamageCA.Execute` (the call the evil branch skips) | `0x55729D14` |
| `TDamageCA.GenerateEx` (writes `ca[+0x10]`) | `0x55729C98` |
| `TTurnUndeadAbility.CreateTurnUndeadCA` (rolls to-hit) | `0x5576B528` |
| flee/panic status ability granted on stun | id `0x22` (34) |
| `TTurnUndeadAbility` VMT `+0xA4` (rejected hook) | `0x5571FEA0` (holds `0x5576B5C0`, unpatched) |
| `TTurnUndeadAbility.fcExecuteCombatCommand` | `0x5576B5C0` |
| `TTurnUndeadAbility.CanTouchUnit` (undead gate) | `0x5576ADC4` |
| `TCommandAbility.fcExecuteCombatCommand` | `0x557703C0` |
| `TCommandAbility.CreateCommandCA` | `0x55770358` |
| `TCommandAbility.Command` | `0x5576FE50` |
| `TCommandAbility.Uncommand` | `0x5576FF08` |
| `TCommandAbility.ResetCommandedUnits` | `0x5576FF94` |
| `TCommandAbility.CombatObjectDestroyed` / `CombatDone` | `0x5576FE44` / `0x5576FE28` |
| `TCommandCA.Execute` | `0x5576FC68` |
| `TCommandedAbility.CombatObjectDestroyed` / `CombatDone` | `0x5576FB6C` / `0x5576FB4C` |
| `TTouchAbility.CombatTouchRole` (to-hit) | `0x557681B0` |
| `TDominateAbility.Create` / `GetTouchAttack` | `0x557705BC` / `0x55770664` |
| `TCombatUnit.GetAlignment` (combat VMT `+0x90`) | `0x55724FF4` |
| `TAbilityControl.GetAbility` | `0x557501C0` |
| `TCombatData.FindID` | `0x55728C68` |
| `TCombatObject.GetSide` | `0x55726660` |
| `CommandAbilityIDs` (3 dwords) | `0x558E84E4` |
| `TCommandAbility` VMT base | `0x55720544` |
| `TTurnUndeadAbility` VMT base (ends `+0x124`) | `0x5571FDFC` |
