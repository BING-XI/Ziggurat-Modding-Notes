# Storm debuff protections/immunities — RE investigation (Pestilence / Death Storm / Divine Storm)

**Status: PATCHED 2026-07-30 — APPLIED, UNTESTED.** The RE below (2026-07-08) is confirmed. The fix
that shipped is **not** the hard-block design originally proposed in §5; it is the *probabilistic
resist* alternative that §5 listed and did not build — see **§7**. All addresses are `AoWEPACK.dpl`
preferred-base VAs (base `0x55700000`, rebased at runtime → any cave must be position-independent per
`[[aow1-dpl-rebasing]]`).

**Build script:** `build_scripts/build_stormeffectroll.py` · **Backup:** `AoWEPACK.dpl.pre-stormeffectroll`

> **⚠ Correction to §3 (made 2026-07-30).** The "ground damager" column below lists which ground
> object deals that *damage type* — it does **not** mean those objects apply the debuff.
> `THolyGround.TriggerArmyDamage @0x557C7E18` only calls `ExecuteDamageRole` for typed damage and
> subtracts HP; it never calls `ExecuteDamageEffects` and never applies vertigo. Same for Unholy
> Ground. `DAT_557C8050 = 0x40` is the holy **damage type**, not an effect mask.
> **The complete caller list for `ExecuteDamageEffects` is: `ExecuteStormDamage` and
> `TPoisonPlant.TriggerArmyDamage`.** (xref-verified.)

---

## 1. The storm damage + debuff pipeline (per unit)

`TArmy.IncommingStorm(army, stormIdx, caster)` @ `0x557904b4` → for each unit calls
`TAbstractUnit.ExecuteStormDamage(unit, stormIdx)` @ `0x55780668`, which does two separable things:

1. **Base damage** (respects immunity + protection): builds a 1-bit damage-type set from
   `StormDamageType[stormIdx]` (table @ `0x558e8330`) and calls
   `TAbstractUnit.ExecuteDamageRole(unit, role, strength, typeSet)` @ `0x55781ac4` (`CALL` @ `0x557807c2`).
   `ExecuteDamageRole` internally checks `GetImmunityTypes` (VMT +0xEC) → **0 damage if immune**, and
   `GetProtectionTypes` (VMT +0xF0) → **half damage if protected**. (Same chokepoint documented in
   `Fire_Heals_FireUnits_Design.md`.)
2. **The DEBUFF** (the subject of this feature): *only if* the clamped base damage `> 0`
   (`TEST ESI,ESI; JLE` @ `0x557807e7`), it selects a per-storm **effect mask** and calls
   **`TAbstractUnit.ExecuteDamageEffects(unit, effectMask)` @ `0x55781e28`** (`CALL` @ `0x55780811`).
   **This is the per-unit debuff application** — distinct from the terrain change (per-storm virtual
   `ChangeStormTerrain`, see `Terrain_Changing_Spells_Map.md`) and from the raw damage above.

### Storm index → class → base-damage type → debuff
Storm index is the 2nd arg to `ExecuteStormDamage`/`IncommingStorm`. Confirmed: `StormType` virtuals
return the index (`TDeathStorm.StormType@0x557cd34c`→2, `TDivineStorm@0x557cd728`→3,
`TIceStorm@0x557ccf70`→4, `TBlastStorm@0x557ccaac`→0); `TPoisonCloud.ArmyPlaced@0x557cab2f` calls
`IncommingStorm(army, 6, …)` → Pestilence = **6**. Fire=1, Lightning=5 by elimination (switch bodies).

| idx | Storm | base dmg type (`StormDamageType[]`) | base role/str | **effect mask** | **debuff applied** |
|----|-------|--------------------------------------|---------------|-----------------|--------------------|
| 0 | Blast | bit9 = 0x200 | 0 / 0 | — | none |
| 1 | Fire | bit0 = **0x01** (fire) | 8 / 5 | — | none |
| 2 | **Death** | bit5 = **0x20** (death) | 8 / 4 | **0x20** (imm. `MOV DX,0x20`) | **Cursed** (ability `0x5d`) |
| 3 | **Divine** | bit6 = **0x40** (holy) | 8 / 5 | **0x40** (imm. `MOV DX,0x40`) | **Vertigo** (ability `0x62`) |
| 4 | Ice | bit1 = 0x02 (cold) | 8 / 5 | — | none |
| 5 | Lightning | bit2 = 0x04 (lightning) | 8 / 6 | — | none |
| 6 | **Pestilence** | bit4 = **0x10** (poison) | 7 / 1 | **[0x55780844] = 0x10** | **Poisoned** (ability `0x60`) |

(Terrain bonus: if the unit stands on the storm's "on-type" terrain, base strength is currently ×4 —
`IMUL ESI,2; IMUL ESI,2` @ `0x5578079a`. See §6: this was ×8 before a prior patch.)

Debuff ability IDs verified via each ability's `Create` (`+0xc` = ability ID):
`TPoisonedAbility.Create@0x557b9dc0`→**0x60**, `TCursedAbility.Create@0x557bac64`→**0x5d**,
`TVertigoAbility.Create@0x557babac`→**0x62**.

---

## 2. Where the debuff bypasses protection — `ExecuteDamageEffects` @ `0x55781e28`

Disassembly (annotated). Called with `EAX`=unit(Self), `DX`=effectMask; `RET`s applied-set in AX.

```
55781e2c  MOV [ESP],DX                  ; save effect mask
55781e3d  CALL [EDX+0xEC]               ; GetImmunityTypes(unit)
55781e45  NOT EBX ; AND BX,[ESP]        ; mask &= ~immunity   <-- IMMUNITY IS RESPECTED
55781e51  CMP AX,BX ; JZ done           ; nothing left -> return
55781e56  TEST BL,0x10 ; JZ .+          ; bit0x10 poison
55781e5b    MOV EDX,0x60 ; CALL [ECX+0x94]   ; ExpandAbility(0x60)=Poisoned
55781e79  TEST BL,0x20 ; JZ .+          ; bit0x20 death
55781e7e    MOV EDX,0x5d ; CALL [ECX+0x94]   ; ExpandAbility(0x5d)=Cursed
55781e9c  TEST BL,0x40 ; JZ done        ; bit0x40 holy
55781ea1    MOV EDX,0x62 ; CALL [ECX+0x94]   ; ExpandAbility(0x62)=Vertigo
```

**Finding (the crux):** `ExecuteDamageEffects` masks the effect set with `~GetImmunityTypes`
(VMT +0xEC) but **never reads `GetProtectionTypes` (VMT +0xF0)**. Therefore:

- **IMMUNITY already fully blocks the storm debuff** — twice over: an immune unit takes **0 base
  damage** (`ExecuteDamageRole` early-out) so the `if (dmg>0)` guard @ `0x557807e9` is false and the
  debuff is never reached; and even if reached, the `~immunity` mask here clears the bit. So *no patch
  is needed for immunities* (the task premise that immunity is bypassed is **incorrect** — verified).
- **PROTECTION does NOT block the storm debuff.** A poison/death/holy-*protected* (not immune) unit
  takes **half** base damage (`>0`) → the debuff is dispatched → `ExecuteDamageEffects` applies it at
  full because protection is never consulted. **This is the gap the feature must close.**

`VMT +0x94 = TAbilityOwner.ExpandAbility(id)` @ `0x5574f5b4` (applies an ability by registry index to
the unit). `ExecuteDamageEffects` @ `0x55781e28` is shared with `TPoisonPlant.TriggerArmyDamage`
(`CALL` @ `0x557c41d2`) — see §5 for why we hook the *storm call site*, not this function.

> The richer sibling `TAbstractUnit.ExecuteDamageEffectsRole` @ `0x55781ba4` **does** check protection
> (per-bit `GetAbilityEnabled` immunity-ability + `GetProtectionTypes` + a resisted `HitRole`), but it
> only *rolls* which effects pass — it does **not** apply them (no `+0x94` call) — and it is called
> **only** from the tactical-combat path (`TCombatUnit.ExecuteDamageEffectsRole@0x55724c3c`). The
> strategic-map storms/grounds use the simpler immunity-only `ExecuteDamageEffects`.

---

## 3. Effect-type bit map + protection/immunity ability IDs (all verified against the binary)

16-bit damage/effect set. ⚠ **`StormDamageType` @`0x558e8330` is a BYTE array of enum ORDINALS**
(fed to `System.@SetElem`), not a table of bitmasks — live bytes `09 00 05 06 01 02 04 90`.
Full `TDamageType` enum from RTTI (`dtFire dtCold dtLightning dtMagic dtPoison dtDeath dtHoly
dtPhysical dtWall dtNone` = bits 0..9) and the per-storm attack/damage jump table are in
**`Strategic_Map_Damage.md`** §3–§4.

| bit | type | storm base dmg | ground damager |
|----|------|----------------|----------------|
| 0x01 | fire | Fire Storm | (map fire) |
| 0x02 | cold | Ice Storm | |
| 0x04 | lightning | Lightning Storm | |
| **0x10** | **poison** | Pestilence | `TPoisonPlant` (`DAT_557c4288`=0x10) |
| **0x20** | **death** | Death Storm | `TUnHolyGround` (`DAT_557c91dc`=0x20) |
| **0x40** | **holy** | Divine Storm | `THolyGround` (`DAT_557c8050`=0x40) |
| 0x80 | **dtPhysical** | | `TTownQuake` (`DAT_557b1ddc`=0x80) |
| 0x100 | **dtWall** | | |
| **0x200** | **dtNone** | **Blast Storm** (storm idx 0, deals 0 damage) | |

Ability IDs from `RegisterPassiveAbilities` @ `0x557bc1cc` (two parallel families):

| type | **Immunity** ability (→ `GetImmunityTypes` bit) | **Protection** ability (→ `GetProtectionTypes` bit) |
|------|--------------------------------|------------------------------|
| fire | 7 | 0x47 |
| cold | 8 | 0x4c |
| lightning | 9 | 0x4a |
| **poison** | **0xa** → bit 0x10 | **0x49** → bit 0x10 |
| **death** | **0xb** → bit 0x20 | **0x46** → bit 0x20 |
| **holy** | **0xc** → bit 0x40 | **0x48** → bit 0x40 |
| physical | 0xd | 0x4d |
| magic | 6 | 0x4b |

`GetImmunityTypes`/`GetProtectionTypes` are the OR of the unit's respective ability masks
(`TAbstractUnit.GetImmunityTypes@0x5577fd54` / `GetProtectionTypes@0x5577fd74`;
`THero` overrides @ `0x55786fd8`/`0x55786ff8` — heroes handled). The immunity-ability indices
(7,8,9,0xa,0xb,0xc) are exactly what `ExecuteDamageEffectsRole` feeds to `GetAbilityEnabled` (VMT +0x148)
per bit — so those indices double as the "does the unit have <type> immunity ability" query.

**Vertigo note:** Divine Storm's debuff (Vertigo, `0x62`) is dispatched through the **holy bit (0x40)**.
There is *no* "vertigo protection/immunity"; the only thing that gates it is **holy** immunity/protection.
So holy-immune units already avoid Divine-Storm Vertigo, and the proposed patch makes holy-*protected*
units resist it too. (Thematically odd but it is how the engine models it — flag for the user.)

---

## 4. How Holy / Unholy Ground gate (evidence — the pattern to copy)

`THolyGround.TriggerArmyDamage` @ `0x557c7f61` and `TUnHolyGround.TriggerArmyDamage` @ `0x557c90ce`
apply **damage only** (no debuff), but they show the canonical per-unit immunity gate. Per unit, before
`ExecuteDamageRole`:

```
align = GetAlignment(unit)                 ; VMT +0xFC  (TAbstractUnit.GetAlignment@0x5577fc60)
if (align == 6)                    -> immune (log dmg 0, type 9[holy]/5[death])
else if (align<8 && bit(alsPureGood[0x558e9418]/alsPureEvil[0x558e9098], align)) -> immune
else if (GetAbilityEnabled(unit, 1) != 0)  -> immune          ; VMT +0x148, ability id 1
else  dmg = ExecuteDamageRole(unit, 6, 4, 0x40 holy / 0x20 death)   ; internal imm/prot check
```

`VMT +0x148 = TAbstractUnit.GetAbilityEnabled(id)` @ `0x5577f5e0` — "does the unit have ability <id>
enabled?" The grounds use a blanket gate (id 1) plus alignment; the *type-specific* immunity/protection
lives inside `ExecuteDamageRole` (imm→0, prot→half), identical to the storms' base damage. **The lesson
for the feature:** the storms' *damage* already gates on immunity+protection exactly like the grounds;
only the storms' *debuff* is missing the protection half of that gate. The faithful fix is to reproduce
`ExecuteDamageEffects`' own `~GetImmunityTypes` masking, extended with `~GetProtectionTypes`.

---

## 5. Proposed patch (speculative — NOT applied)

**One position-independent cave**, hooking the storm debuff call site only. Because the effect mask in
`DX` already encodes which debuff (0x10/0x20/0x40), clearing the unit's protected bits from `DX` makes a
unit with the matching **protection** ability resist that storm's debuff — for **all three storms at
once**, without touching `ExecuteDamageEffects` (so `TPoisonPlant` is unaffected).

**Hook site** @ `0x5578080f` (verified on-disk bytes `8B C7 E8 12 16 00 00` = `MOV EAX,EDI` +
`CALL 0x55781e28`). Replace 7 bytes with `E9 <rel32 to cave> 90 90`.

**`cave_stormprot`** (register-only + rel32/rel-call; no absolute globals → rebase-safe). Suggested
placement `0x5580DC80` (free zero-fill run at `0x5580DC7A`, 1926 B, after the raise-terrain caves — the
build script must re-verify free space):

```
push edx                     ; 52            save effect mask (DX)
mov  eax, edi                ; 8B C7         unit (EDI held across ExecuteStormDamage)
mov  ecx, [eax]              ; 8B 08
call [ecx+0xF0]              ; FF 91 F0 00 00 00   GetProtectionTypes(unit) -> AX
pop  edx                     ; 5A            restore mask
not  ax                      ; 66 F7 D0
and  dx, ax                  ; 66 21 C2      DX &= ~protection   (clear protected bits)
mov  eax, edi                ; 8B C7         Self for ExecuteDamageEffects
call 0x55781e28              ; E8 <rel32>    ExecuteDamageEffects(unit, DX)
jmp  0x55780816              ; E9 <rel32>    return past the original CALL
```

`EDI`/`ESI`/`EBX` are callee-saved (Delphi register convention — `EDI` survives every virtual call in
`ExecuteStormDamage`), so `unit` is intact after `GetProtectionTypes`; `EAX/ECX/EDX` are scratch (mask
saved on stack). Net effect:
- **Poison Protection** (ability 0x49 → prot bit 0x10) → resists **Pestilence** Poisoned.
- **Death Protection** (ability 0x46 → prot bit 0x20) → resists **Death Storm** Cursed.
- **Holy Protection** (ability 0x48 → prot bit 0x40) → resists **Divine Storm** Vertigo.

Base damage is unchanged (protected units still take half); only the *debuff* is now blocked. Immunities
already worked (§2) and are unchanged.

**Variants (design choices):**
- *Per-storm control* — branch on the mask bit in `DX` (e.g. only clear 0x40 for Divine) — trivial.
- *Probabilistic resist* instead of hard block — replace the `~GetProtectionTypes` AND with the
  `ExecuteDamageEffectsRole`-style `GetAbilityEnabled(immId)` + `HitRole(5-resist)` logic (more code;
  matches tactical-combat behaviour). The hard-block version above matches the task's "resists the
  debuff" wording and the grounds' boolean-gate style.
- If poison protection should *also* stop `TPoisonPlant` debuffs, patch `ExecuteDamageEffects` itself
  (add `AND BX,~GetProtectionTypes` after `0x55781e47`) instead of the call site — out of requested scope.

---

## 6. Risks / unknowns

1. **Divine-Storm Vertigo IS in this DLL, and it was patched in (confirmed by version diff).**
   `ExecuteStormDamage`'s effect dispatch @ `0x557807ee`–`0x55780807` differs from `AoWEPACK - May
   2025.dpl`: the old copy had **only** Death(idx2→[0x55780840]=0x20) and Pest(idx6→[0x55780844]=0x10)
   branches — **Divine(idx3) fell through with no debuff.** The current build inserted `CMP AL,3; JZ →
   MOV DX,0x40`, routing Divine through `ExecuteDamageEffects` bit-0x40 = `ExpandAbility(0x62=Vertigo)`.
   The bit-0x40→Vertigo mapping in `ExecuteDamageEffects` is **vanilla** (byte-identical across every
   DLL copy back to May 2025); the patch is the *added dispatch branch*, not the Vertigo ability. The
   same patch also cut the terrain damage bonus ×8→×4 (byte @ `0x5578079f`: 04→02). No `.pre-*` backup
   is named for it — treat the current `ExecuteStormDamage` tail as already-modded when layering.
2. **Vertigo is gated by the holy bit only** (no vertigo-specific resist) — so "holy protection" is what
   blocks Divine-Storm Vertigo under this patch. Confirm that is the intended semantics.
3. `GetProtectionTypes` is the "half-damage" set; using it to *fully block* the debuff is a design
   choice (the task's intent). If partial/roll behaviour is wanted, see §5 variant 2.
4. Single cave blocks the debuff for all three storms uniformly (fine per the goal); per-storm scoping
   is a one-line branch if desired.
5. Tactical-combat storms use a different path (`ExecuteDamageEffectsRole`, `0x55781ba4`) that already
   respects protection + rolls — this feature concerns the **strategic-map** storm path only.
6. Cave must avoid the existing caves in `0x5580D8xx`–`0x5580DC7A` (fire-heal, ice-storm, raise-terrain
   — see `Terrain_Changing_Spells_Map.md` / `Fire_Heals_FireUnits_Design.md`); place at/after
   `0x5580DC80` and re-verify zero-fill at apply time. Backup as `AoWEPACK.dpl.pre-stormprot`.

## Key addresses (quick reference)
- `TAbstractUnit.ExecuteStormDamage` @ `0x55780668`; debuff dispatch `0x557807e7`–`0x55780816`;
  **hook site `0x5578080f`** (`MOV EAX,EDI; CALL 0x55781e28`).
- `TAbstractUnit.ExecuteDamageEffects` @ `0x55781e28` (immunity-only debuff applier).
- `TAbstractUnit.ExecuteDamageEffectsRole` @ `0x55781ba4` (protection-aware roller; tactical only).
- `TAbstractUnit.ExecuteDamageRole` @ `0x55781ac4` (base damage; imm+prot chokepoint).
- `TArmy.IncommingStorm` @ `0x557904b4`; `TPoisonCloud.ArmyPlaced` @ `0x557cab2f` (Pestilence=idx6).
- VMT (base `0x55710740`): +0x94 `ExpandAbility`(0x5574f5b4), +0xEC `GetImmunityTypes`(0x5577fd54),
  +0xF0 `GetProtectionTypes`(0x5577fd74), +0x148 `GetAbilityEnabled`(0x5577f5e0), +0xFC `GetAlignment`.
- Grounds: `THolyGround.TriggerArmyDamage` @ `0x557c7f61`, `TUnHolyGround` @ `0x557c90ce`,
  `TPoisonPlant` @ `0x557c4178`.
- Ability Create (IDs): Poisoned `0x557b9dc0`=0x60, Cursed `0x557bac64`=0x5d, Vertigo `0x557babac`=0x62.
- Constants: `StormDamageType[]`@`0x558e8330`, Pest mask `[0x55780844]`=0x10, holy `[0x557c8050]`=0x40,
  death `[0x557c91dc]`=0x20, poison `[0x557c4288]`=0x10.

---

## 7. THE SHIPPED FIX — roll against RES (applied 2026-07-30, untested)

Rather than the §5 hard block, the strategic path now runs the engine's **own rolled sibling** first
and applies only the survivors. Storms *and* Poison Plant are covered, because the hook is on the
shared function rather than on one call site.

### Hook
| VA | orig | new |
|---|---|---|
| `0x55781E28` (`ExecuteDamageEffects` entry) | `53 56 57 51 66 89 14 24` | `E9 <rel32> 90 90 90` → cave `0x55812800` |

Resume `0x55781E30`. Cave, 27 bytes:

```
and  dx, 0x70              ; only poison/death/holy exist here
push eax                   ; preserve Self across the roll
call 0x55781BA4            ; ExecuteDamageEffectsRole(Self, mask) -> AX = survivors
mov  dx, ax
pop  eax
push ebx / esi / edi / ecx ; replay the displaced prologue
mov  word ptr [esp], dx    ; ...with the ROLLED mask
jmp  0x55781E30
```

The two functions chain directly because the Role function's **result bits are the same bit values
as its input mask** (verified: fire `0x01`, cold `0x02`, lightning `0x04`, poison `0x10`,
death `0x20`, holy `0x40`).

### Effect chance
`clamp(50 + 10*(strength − effRES), 10, 90)` via `HitRole @0x55725D98`. Per-type strengths in the
rolled path: fire 4, cold 2, lightning 6, **poison 3, death 4, holy 3**. A matching *partial
protection* adds **+2 RES** against that type. So RES 5 → 50%, RES 7 → 30%, RES ≥ 9 → 10% floor,
RES ≤ 4 → 90% cap.

### Why "no frozen / burning / stunned on the strategic map" is guaranteed
`ExecuteDamageEffects` implements **only** `0x10`→Poisoned(`0x60`), `0x20`→Cursed(`0x5D`),
`0x40`→Vertigo(`0x62`). There is **no branch** for fire/cold/lightning, and no vanilla strategic
caller passes those bits. The `and dx,0x70` makes the guarantee explicit and caller-independent, so
a future caller cannot leak a combat-round-scoped status onto the strategic map.

### Consequences (intended, but real behaviour changes)
- **Protection now matters** — +2 RES against the matching type. This was §5's original goal,
  achieved as a side effect.
- **Divine Storm vertigo gains the rolled path's extra `vmt[0x114]() != 2` gate** — resolved
  2026-07-30: `vmt+0x114` is **`TUnit.GetUnitType` @0x55782808**, returning `byte [[unit+0x40]+0x30]`
  (= **tag `0x15`** in `Unitres.pfs`). Enum, from the installed data — **0 = humanoid/racial**
  (96 units), **1 = monster/creature** (61), **2 = machine** (23; Battering Ram, Bombard, Catapult,
  Air Galley, Undead Bone Ram …). Only 0–2 are used, though the roster-filter bitset supports 0–7.
  So `!= 2` means **"is not a machine"**: machines cannot be given vertigo. The same gate also
  blocks **stunned** (lightning, skipped outright) and **lifesteal** healing — see
  `Investigation_Combat.md`. Coherent: you can't make a machine dizzy, stun it, or drain life
  from it.
- **Immunity is unchanged** — it already blocked these twice over (0 damage → the `dmg>0` guard
  fails; and the `~immunity` mask clears the bit).

### ⚠ Cross-feature interaction
`build_effectroll.py` has repointed five of the six `HitRole` call sites **inside**
`ExecuteDamageEffectsRole` to combat-log stubs, so storm/plant rolls now run those stubs. The shared
emitter `@0x5580F605` guards on a `'CLG1'` ring-buffer magic and bails when absent or full, so it is
safe off the tactical path — strategic rolls simply do not log unless the combat log is up. (If the
log *is* up, storm rolls will appear in it, which is arguably a bonus.)

`HitRole` itself carries one live edit — a `lea eax,[eax+eax*4]` → `imul eax,eax,5` re-encoding at
`0x55725D9F` (and the same at `HitRoleProbability+0x05`, `0x55725DD1`). Semantically identical (×5),
same length; it makes the multiplier a tunable imm8 (`6B C0 nn`), currently left at the vanilla 5.
⚠ **Provenance unknown — it is NOT the combat-log work.** No script in `build_scripts/` writes
`0x55725D9F` (verified 2026-08-18 by grep; the four hits on `0x55725D98` are `HITROLE` *call-target*
constants). Treat it as an undocumented hand edit. See `Excess ATK minimum damage bonus.md` §7.

### PIC / safety
The cave has **no absolute data references** — rel32 `call` + rel32 `jmp` and register/immediate ops
only, so it is rebase-safe with no load-delta anchor. No recursion (`ExecuteDamageEffectsRole` never
calls `ExecuteDamageEffects`). Tactical combat is untouched — it reaches the Role function directly
via combat vmt `+0x118`.

### Test procedure (to promote to CONFIRMED)
Cast Pestilence / Death Storm / Divine Storm on a stack with mixed Resistance. High-RES units should
now take damage but frequently **shrug off** the debuff; low-RES units should still usually get it.
Check a Poison Plant does the same. Verify no unit ever comes out frozen/burning/stunned.

### Revert
`build_stormeffectroll.py --undo` — restores the 8-byte prologue and zeroes the cave, touching no
`.pre-*` backup, so features applied later survive.
