# Magebane — new ability: +2/+2 per enchantment, +5/+5 vs Summoned

**Status: APPLIED, UNTESTED (2026-07-30).** All RE verified against the live binary; the patch is
applied but **not yet validated in-game**. Two things are unproven until you launch — the ability
id (§5) and the ranged stack arithmetic (§3). Promote to `CONFIRMED WORKING` only after §7.

**Build script:** `build_scripts/build_magebane.py` · **Backup:** `AoWEPACK.dpl.pre-magebane`
**Ability id:** `0xAA` · **Cave:** `0x55812900`–`0x55812A94` (405 B of a 512 B reservation)

A unit with Magebane gains **+1 ATK and +1 DMG for every enchantment currently sustained on its
target**, stacking and uncapped. Covers deliberate melee, retaliation, round/opportunity/ability
strikes, and ranged + breath (per shot).

`VA = file_offset + 0x55700C00`.

---

## 1. What the engine counts as an "enchantment"

A unit's enchantments are exactly its abilities whose class is **`TUnitEnchantmentAbility`**. That
class creates a real `TEnchantment` object carrying an **owning player**, an **upkeep**, and a
**dispel** path — i.e. *a sustained magical effect a caster is paying for and Dispel Magic can
strip*.

This is why the grouping looks odd at first glance. **`TDurationAbility`** — Burning `0x7F`,
Panicked `0x6C`, Poisoned, Cursed, Vertigo, Crusader `0x65` — is just a **timer with no owner**, so
none of those count. The discriminator is *ownership and dispellability*, **not** buff-vs-debuff and
**not** duration (`TUnitEnchantmentAbility` even has a `CombatDone` hook, so enchantments can be
combat-scoped).

**The 21 `TUnitEnchantmentAbility` classes:**

| group | abilities |
|---|---|
| counted (buffs) | Haste `0x98`, Stone Skin, Fire Protection `0xA7`, Enchanted Weapon, Fury `0x9C`, Free Movement `0x9D`, Holy Champion, Unholy Champion, Blessed, Dark Gift `0xA9`, Concealment `0xA2`, Fire Aura, Water Walking `0xA4`, Wind Walking `0xA5`, Liquid Form `0xA6`, Cosmetic Surgery |
| counted (marker) | **Summoned `0x9B`** — permanent on every summoned creature, so Magebane gets a flat +1/+1 vs summons. `INCLUDE_SUMMONED = False` drops it. |
| **EXCLUDED by choice** | Slow `0x84`, Entangled `0x5E`, Frozen `0x5F`, Turned Undead `0x22` — they *are* enchantments, but your own crowd control should not feed your damage. |

## 2. The counting helper

`cave_count @0x55812920` (151 B), `EAX` = strategic unit → `AL` = count. Mirrors
`TAbstractUnit.RegisterEnchantments @0x5577F29C` exactly:

```
list = [[HSSet+0x80] + 0x1C]                    ; TAbilityTypeList  (HSSet ptr @0x558E92E8)
for i = [list+8]-1 downto 0:
    ab = TAbilityTypeList.GetAbility(list, i)   ; 0x557500AC
    if !IsClass(ab, TUnitEnchantmentAbility): continue   ; 0x557010C0, class-ptr var @0x55722324
    id = ab[0x0C]
    if id in {0x84,0x5E,0x5F,0x22}: continue     ; the exclusion list
    if target.vmt[0x148](id): count++            ; GetAbilityEnabled
```

Preserves `EBX/ESI/EDI/EBP` (melee3 needs `EBX` as its slot pointer); clobbers only `EAX/EDX/ECX`.
PIC via the standard `call/pop; sub` delta.

**Cost note:** the loop is O(all registered abilities) ≈ 170 iterations with two calls each — but it
only runs **after** confirming the *attacker* has Magebane, so every other unit in the game pays a
single virtual call. Negligible in practice.

## 3. Injection — chained onto the existing caves

The three strike sites already carry our Assassin / slayer / true-seeing caves. Rather than rewrite
those bodies, this repoints **each cave's final exit jump** into a Magebane block that does its work
and jumps to the original return — 4 bytes of rel32 each.

| site | exit jmp | returns to | ATK slot | DMG slot | target |
|---|---|---|---|---|---|
| `CreateStrikeCA` (round / opportunity / ability strikes) | `0x5580E399` | `0x557666CF` | `BL` | `byte[esp+3]` | `ESI` |
| `TMeleeRound.CalculateStrikes` (deliberate + retaliation) | `0x5580E3D9` | `0x55767C89` | `dword[EBX]` | `dword[EBX+4]` | `EDI` |
| `CreateRangedAttackCA` (ranged + breath, per shot) | `0x5580E298` | `0x5576EB39` | `[esp+4]`→`[esp+16]` | `[esp]`→`[esp+12]` | `[EBP-4]` |

Register liveness was read from the **live** binary, not the design docs:
- **melee1/melee3:** `EAX/ECX/EDX` are dead at the return (`0x557666CF` immediately does
  `xor ecx,ecx` / `mov dl,1` / `mov eax,[abs]`), so the block clobbers them freely.
- **⚠ ranged:** `EAX` and `EDX` are **live** — `0x5576EB39` is `call [edx+0xb8]`. The block pushes
  `eax/edx/ecx`, which shifts the two stack slots by 12, hence `[esp+12]` / `[esp+16]`. **This is
  the one piece of arithmetic that in-game testing must confirm**; getting it wrong corrupts a
  pointer rather than just miscounting.

Target enchantments live on the **strategic** unit, reached from the combat object via
`[combat+0x4C]` — the same bridge the Assassin block already uses.

## 4. Registration

Hooks **`0x557BCF6E`** — the **last vanilla `call RegisterAbility`** in `RegisterPassiveAbilities`
(145 of 149 call sites are still vanilla; the 4 patched ones are our Assassin/slayer registrations).
`EBX` holds the ability control there and every vanilla ability is already registered by that point.

`cave_reg @0x55812A60` re-issues the displaced call, then `CreateEnhancementAbility(id=0xAA,
name="Magebane", cat=[0x557BCFC0]=0x37)` → `RegisterAbility` → `jmp 0x557BCF73`.

Category `0x37` is the one Path of Sand uses and is confirmed to make an ability appear in the
editor's assignable list. (The neighbours at this site use `[0x557BCFC8]` = `0x237`; not used.)

**This registration is independent of Path of Sand** — it does not chain onto that cave, so the two
features can be applied and reverted in any order.

## 5. ⚠ The ability id is the open risk

`0xAA` is the first id in the range our `Ability_ID_Budget.md` recommends (`0xAA`–`0xCD`, 36 ids
above vanilla's maximum — **Dark Gift `0xA9`, independently confirmed here**). Inioch reports a
Localize.dpl crash for ids above `0xA9` on his AoW+ build; that conflict is **unresolved**, and this
feature is the decisive test.

Both failure modes are **loud and immediate at startup** — a `"Ability already registered"` assert,
or a Localize.dpl crash. If either happens, set `MAGEBANE_ID` to a verified sub-`0xA9` gap
(Inioch's candidate runs: `0x51–0x55`, `0x66–0x69`, `0x85–0x89`) and re-run.

**The icon will be blank** — expected for a brand-new id with no ILB entry, same as Path of Sand.

## 6. ⚠ Cross-script coupling

The three chained exit jumps live **inside caves owned by other scripts** —
`build_assassin.py`, `build_ranged_slayers.py`, `build_invis_penalty.py`. **Re-running any of those
rewrites its cave and silently drops the Magebane chain.** Re-run `build_magebane.py --apply`
afterwards; `--verify` reports the state of all four hooks and the caves in one line.

## 7. Test procedure (to promote to CONFIRMED)

1. **Launch.** If the game starts at all, id `0xAA` is valid — that alone settles the ID-range
   question and is worth recording either way.
2. Assign Magebane to a unit in the editor (it will have a blank icon).
3. Attack an **unbuffed** target — damage should be unchanged from vanilla.
4. Cast Bless / Haste / Stone Skin on the target and attack again — **+1/+1 per enchantment**.
5. Attack a **summoned** creature — should show +1/+1 from the permanent Summoned enchantment.
6. Slow or Entangle a target, then attack — should show **no** bonus from those (exclusion list).
7. **Test all three paths:** deliberate melee, being retaliated against / opportunity strike, and a
   ranged shot. The ranged path is the one most likely to misbehave (§3).

## 8. Tuning / revert

`BONUS_PER` (per-enchantment bonus), `CAP` (0 = uncapped), `INCLUDE_SUMMONED`, `EXCLUDED`,
`MAGEBANE_ID`, and `NAME` are all constants at the top of the script; edit and re-run with
`--apply` (it rewrites its cave in place).

`--undo` restores all four hook sites and zeroes the cave **without touching any `.pre-*` backup**,
so features applied later survive.

---

## 9. Re-tune 2026-08-29 — Summoned is worth +5/+5, and the chain trap is fixed

**Status: APPLIED, UNTESTED.** Two changes, one behavioural and one structural.

### 9.1 Summoned counts for 5, not 2

User ruling: *"Magebane should deal +5/5 damage against units with the Summoned ability."*

`Summoned 0x9B` is a real `TUnitEnchantmentAbility` permanently applied by `TSummonSpellTE.Process`,
and it was already counted by the ordinary loop — so a summon was worth `BONUS_PER` = **+2/+2**.
It is now **+5/+5**, implemented as a *top-up* rather than a separate arm:

```
cave_count tail (@0x558129AC):
    mov  eax, [esp]              ; the enchantment count
    imul eax, eax, 2             ; BONUS_PER          <-- moved here from the three call sites
    push eax
    mov  edx, 0x9B               ; Summoned
    mov  eax, ebp                ; the strategic target
    mov  ecx, [eax]
    call dword ptr [ecx + 0x148] ; GetAbilityEnabled
    test al, al
    pop  eax
    jz   no_summoned
    add  eax, 3                  ; SUMMONED_BONUS - BONUS_PER
no_summoned:
```

Because Summoned is *also* counted normally, a bare summon reads exactly **+5/+5** and a hasted
summon reads **+7/+7** (5 + one ordinary enchantment). `SUMMONED_BONUS = SUMMONED_BONUS` set equal
to `BONUS_PER` disables the special case.

⭐ The multiply moved out of the three strike blocks and into `cave_count`, so all three sites
share one copy of the arithmetic and cannot drift apart. That is why `count` grew 151 → 178 B and
`melee1`/`melee3`/`ranged` each shrank.

### 9.2 The "never run this script" trap is gone

The standing warning was that `--apply` re-emitted the ranged cave's **stock** tail
(`jmp 0x5576EB39`) and so silently unlinked `build_shield.py`'s ranged penalty, which chains itself
onto that tail. The tail is now **chain-aware**:

```python
def ranged_tail(data):
    blob = data[off(SHIELD_RANGED_CAVE) : off(SHIELD_RANGED_CAVE) + 0x60]
    return SHIELD_RANGED_CAVE if any(blob) else RANGED_RESUME
```

If Shield's cave is installed we chain into it; if Shield has been `--undo`ne (cave zeroed) we go
straight back to the engine. **Re-applying Magebane is therefore safe in both states.**

⚠ **The UNDO direction still needs ordering** — `--undo` zeroes the whole cave, which leaves
Shield's cave at `0x558230D0` with nothing calling it (silent, not a crash). Undo Shield first.

### 9.3 Two layout dependencies this exposed — both now explicit

| what | why it matters |
|---|---|
| **`RNG_TAIL_PIN = 0x55812A7B`** | `build_shield.py` hard-codes that address as the 5-byte site it rewrites. The re-tune shortened the ranged block by 3 B, which would have left Shield patching the *middle* of our jmp. The block is now padded so the tail lands exactly on the pin, with a hard error if it ever cannot. |
| **`build_shield.py`'s `M1_TAIL`** | Its retired-melee-site guard checks magebane's melee1 tail, which *did* move (`0x558129EC` → `0x55812A09`). Left stale it aborted the whole script with a false "a pre-2026-08-27 Shield is half-installed". Updated, with a note to re-read it from `--show` after any future re-tune. |

⭐ **The general shape: a cave's internal layout is part of its interface once a neighbour hooks
into it.** Pin what others patch; expect what others merely *check* to need updating.
`build_invis_penalty.py` shows the third option and the best one — its `preserve_terminator` reads
the installed target at runtime, so it needed no change at all and simply reported
`exit kept at 558129E0`.

### 9.4 State after applying

`--verify` → **APPLIED and intact**, `caves match: True`; cave 437 B of 512.
`build_shield.py` → `nothing to do -- already done`, all three retired melee sites clean.
`build_invis_penalty.py` → `already applied`, both exits re-pointed at the new blocks.

**Owed: the in-game test.** Hit a summoned creature (no other enchantments) with a Magebane unit —
the bonus should be +5 ATK / +5 DAM, melee and ranged; add Haste to it for +7/+7. And confirm
Shield's ranged penalty still fires, since its link runs through this cave.

## 10. Description — `Ability.pfs` record 180 (applied 2026-08-29, untested)

> `+2/2 ATK/DAM against units per enchantment they have, and +5/5 ATK/DAM against summoned units`

Script: `build_scripts/build_magebane_desc.py` (backup `Release/Ability.pfs.pre-magebanedesc`,
`--undo` byte-exact).

⚠ **This could not be a `build_pfs_typos.py` row.** That script rewrites a string field that
already exists — `plan()` bails with "record N has no tag T", and its whole rebuild assumes the body
directory keeps its size. Magebane's record, as the editor created it, had **no tag 5 at all**:

```
record 180 (= ability 0xAA + 10)      tag 6 = 8       hero level-up point cost
                                      tag 7 = 0x101   SFX
                                      tag 8 = 0       image list (blank icon, expected for a new id)
                                      tag 9 = 0x0037  selection mask (= the reg cave's CATWORD)
```

So the field had to be **created**: the directory gains a 2-byte small entry and the payload gains
the u32-prefixed string, 23 B → 124 B. Teaching `plan()` to do that would mean unpicking its
`dsz`-is-constant assumption on a function ~30 working rows depend on, so the insertion lives in its
own script — but it imports `index_layout` / `body_dir` / `slice_fields` / `read_str` from
`build_pfs_typos.py` rather than re-deriving them, so there is still one implementation of the
container format.

Design points worth reusing for any other *added* field:

- **Append at the end of the payload.** Every existing field then keeps its offset and only the new
  directory entry is added — nothing inside the record moves.
- **The u8 ceiling is the real constraint.** Small directory entries hold the offset in one byte, so
  the new field's offset (here 14) and every later *index* offset are range-checked; the script
  refuses rather than truncating.
- ⚠ **The final record's body swallows the trailing 4-byte CRC.** A "nothing else changed"
  verifier must strip it before comparing, or repairing the CRC reads as collateral damage on the
  last record — which is exactly how this script failed its own check on the first run.
  `build_pfs_typos.collateral()` already documents this; the verifier here mirrors it.

Verified after applying: 156 records still parse, every other record byte-identical, record 180's
other four tags unchanged, CRC residue `0x2144DF1C`, and `--undo` restores the file byte-exactly.
All three Ability.pfs writers (`build_pfs_typos.py`, `build_useitem_protections.py`, this one)
report "nothing to do" against the result.
