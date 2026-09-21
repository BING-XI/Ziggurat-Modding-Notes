# Sphere Mastery casting-cost rework

**Status: APPLIED, UNTESTED (2026-07-30).** RE verified against the binary; the patch is applied to
`AoWEPACK.dpl` but not yet validated in-game. Promote to `CONFIRMED WORKING` only after §6.

**Build script:** `build_scripts/build_mastery_cost.py` · **Backup:** `AoWEPACK.dpl.pre-masterycost`

| | opposed sphere | same sphere |
|---|---|---|
| vanilla | **×2.00** | ×1.00 (no effect) |
| now | **×1.50** | **×0.75** |

Rationale: doubling the opposed sphere is a hard lockout rather than a cost; +50% still stings
without being anti-fun, and the same-sphere discount makes a Mastery feel like *your* sphere's
mastery instead of purely a denial tool.

`VA = file_offset + 0x55700C00`.

---

## 1. The mechanic

`TGlobalMagicControl` lives at **`[[0x558FA040] + 0x188]`** and holds a **per-sphere counter array
at `mc + 0x18 + sphere*4`**. `TGlobalMagicControl.GetSphereManaDoubled @0x5577E230` is simply
`counter != 0`. `IncDoubleSphereManaCount @0x5577E220` / `DecDoubleSphereManaCount @0x5577E228`
adjust it.

**Sphere enum** (as in `Investigation_Storm_Protections.md` / the sphere-combining notes):
`0 Cosmos, 1 Life, 2 Death, 3 Earth, 4 Air, 5 Fire, 6 Water`. A spell's sphere is `[spell+0x20]`;
its base casting cost is `[spell+0x14]`.

### ⭐ The key finding — the discount needs no new state
The **only** callers of `IncDoubleSphereManaCount` are the six Mastery enchantments' `Activate`
methods, and **each flags its own opposite** (all six verified):

| Mastery | own sphere | flags |
|---|---|---|
| `TLifeMasteryEnchantment.Activate` @`0x557F2043` | Life (1) | Death (2) |
| `TDeathMasteryEnchantment.Activate` @`0x557F2499` | Death (2) | Life (1) |
| `TEarthMasteryEnchantment.Activate` @`0x557F338B` | Earth (3) | Air (4) |
| `TAirMasteryEnchantment.Activate` @`0x557F03DF` | Air (4) | Earth (3) |
| `TFireMasteryEnchantment.Activate` @`0x557F2BA7` | Fire (5) | Water (6) |
| `TWaterMasteryEnchantment.Activate` @`0x557F08DB` | Water (6) | Fire (5) |

Therefore, for a spell of sphere `S`:
- **an opposed Mastery is active** ⟺ `doubled[S] != 0` (what vanilla already tests), and
- **a Mastery of S itself is active** ⟺ `doubled[opposite(S)] != 0`,

with `opposite(s) = s+1 if s odd else s-1` (Cosmos 0 has no opposite). No new field, no extra
bookkeeping, nothing to serialize — the discount is derivable from the state vanilla already keeps.

## 2. The cost chokepoint

**`THero.CastingMana @0x557894EC`** (vanilla):

```
557894EC  push ebx ; push esi
557894EE  mov  esi, edx                  ; esi = spell
557894F0  mov  ebx, [esi+0x14]           ; ebx = base cost
557894F3  mov  eax, [0x558FA040]         ; map        <-- the function's ONLY .reloc (@0x557894F4)
557894F8  mov  eax, [eax+0x188]          ; TGlobalMagicControl
557894FE  mov  dl, [esi+0x20]            ; spell sphere
55789501  call GetSphereManaDoubled
55789506  test al,al ; je 0x55789510
5578950A  mov eax,ebx ; add eax,eax ; mov ebx,eax    ; cost *= 2
55789510  mov eax,ebx ; pop esi ; pop ebx ; ret      ; epilogue
```

**It is a single chokepoint with 20+ callers** — `CanCastSpell`, `CanCastCombatSpell`, `CastSpell`,
`ExecuteStartCasting`, `CastingTurns`, `TSpell.CombatSpellCast`, `TCombatSpell.CreateCA`,
`TUnitSpellCaster.GetRequiredMana` (our unit-spellcasting feature), and every combat-spell
`CreateCA`. So one patch covers every cost preview, every AI affordability check and every actual
charge.

## 3. The patch

**Hook `0x557894F8`** (`mov eax,[eax+0x188]`, 6 bytes → `jmp` + 1 nop), **cave `0x55812880`** (61 B),
returning to the vanilla epilogue at `0x55789510`.

```
mov   eax,[eax+0x188]              ; replay displaced -> mc
movzx edx, byte [esi+0x20]         ; S = spell sphere
cmp   [eax+edx*4+0x18], 0
jne   opposed                      ; opposed Mastery -> penalty
test  edx, edx                     ; Cosmos has no opposite
jz    done
ecx = (S odd) ? S+1 : S-1          ; opposite(S)
cmp   [eax+ecx*4+0x18], 0
je    done
ebx = ebx*3 >> 2                   ; own Mastery -> x0.75
jmp   done
opposed:
ebx = ebx*3 >> 1                   ; opposed      -> x1.50
done:
jmp   0x55789510
```

**⚠ Why the hook is at `0x557894F8` and not earlier:** the preceding
`mov eax,[0x558FA040]` carries the function's **only base-relocation** (verified: the sole reloc in
`CastingMana` is at `0x557894F4`). Displacing it would be the classic
"works one launch, crashes the next" trap. Hooking after it means **`eax` already holds the
correctly-relocated map pointer**, so the cave needs **no PIC anchor at all** — rel32 jumps and
register ops only.

The vanilla `×2` block at `0x557894FE`–`0x5578950F` is now unreachable and left in place; `--undo`
restores it.

## 4. Retuning

Edit the constants at the top of the build script and re-run with `--apply` (it rewrites its cave
in place):

```python
OPPOSED_MUL, OPPOSED_SHIFT = 3, 1     # cost * 3 >> 1 = x1.50   (vanilla: 2, 0)
OWN_MUL,     OWN_SHIFT     = 3, 2     # cost * 3 >> 2 = x0.75   (vanilla: 1, 0)
ROUND_UP = False
```

Any `mul/shift` pair works: ×1.25 = `(5,2)`, ×0.5 = `(1,1)`, ×2 = `(2,0)`.

## 5. Semantics & landmines

- **Precedence.** If a sphere *and* its opposite both have Masteries up, the **opposed penalty
  wins** (tested first); the discount is skipped.
- **No compounding.** The engine stores a *count* but tests `!= 0`, so two Masteries of the same
  sphere do not stack — same as vanilla's flat ×2.
- **Rounding** is integer and truncating, which favours the caster in *both* directions (a 5-mana
  spell → 7 opposed, 3 same-sphere). `ROUND_UP = True` biases the other way.
- **Cosmos (0) is unaffected** in both directions — it has no opposite, and no Mastery flags it.
- **⚠ GLOBAL, not per-caster.** `TGlobalMagicControl` is a single global with **no owner tracking**;
  this is vanilla's design — your Fire Mastery doubles water costs for *everyone*. The new discount
  inherits that, so casting Fire Mastery makes fire spells 25% cheaper for **every** wizard, not
  just you. Making it caster-only would need per-player state the engine does not have (the counter
  array has no owner dimension), i.e. a substantially bigger feature.
- **Unit spellcasting is covered for free** — `TUnitSpellCaster.GetRequiredMana` is one of the
  callers.

## 6. Test procedure (to promote to CONFIRMED)

With a Mastery active, open the spellbook and compare against the known base costs:
1. An **opposed-sphere** spell should read **+50%** (12 → 18), not double.
2. A **same-sphere** spell should read **−25%** (12 → 9).
3. An **unrelated sphere** (and any Cosmos spell) must be **unchanged**.
4. Check the cost actually charged matches the displayed cost, and that a combat spell cast by a
   hero and by a unit-caster both use the new number.

## 7. Revert

`build_mastery_cost.py --undo` — restores the 6 displaced bytes and zeroes the cave, touching no
`.pre-*` backup, so features applied later survive.
