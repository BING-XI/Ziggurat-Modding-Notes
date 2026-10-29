# Spells added from scratch

This file covers the two tactical-combat spells built in the 2026-09-01/03 session that stand as the
project's worked examples for adding spell-like content: **Embrittle** (spell id 109, a genuinely new
tier-3 Earth combat spell, with its own **Embrittled** status ability `0xB2`) and **Grip of Winter**
(spell id `0xA`, formerly *Freeze Water* — not new content, but a ground-up rebuild of an existing
spell using the identical "clone-and-relabel a vanilla class instance" recipe, and the second half of a
cave-space-and-coupling story that runs through both features). Both are `🔨 APPLIED, UNTESTED` —
nobody has played either yet — so both feature sections end in a full in-game checklist that must not
be dropped.

Out of scope, covered elsewhere: the general ability-id budget and the ceiling-ladder mechanism itself
(only the one re-run Embrittle forced is covered here); the raise-terrain / underground-earth side of
the Grip of Winter coupling, which belongs to `09-terrain-movement.md`; and general `.pfs`/`.mld`
container-format documentation beyond the splicing rules both features actually exercise.

## Status table

| feature | status | owning script | binary / file |
|---|---|---|---|
| Regeneration spell (id 79, Water tier 1) + its enchantment (ability `0x53`) | applied 2026-10-22, launch-proved | `build_regen_spell.py`, `build_regen_spell_pfs.py`, `build_regen_spell_icon.py` | `AoWEPACK.dpl`, `Release\Spells.pfs` record 89, `Release\Ability.pfs` record 93, `Images\SpellIcn.ILB` entry 129 |
| Embrittle spell (id 109) + Embrittled status (ability `0xB2`) — mechanics | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_embrittle.py` | `AoWEPACK.dpl` (7 hooks + 1 cave), `AoWTCPCK.dpl` (1 byte) |
| Embrittle spellbook icon (cracked-bone stamp, reuses dead entry 128) | 🔨 APPLIED, UNTESTED (2026-09-01; v3 art and the half-res twin 2026-10-27) | `build_embrittle_icon.py` | `Images/SpellIcn.ILB`, `Images/_SpellIcn.ILB` |
| Embrittle `Spells.pfs` record 119 + `Ability.pfs` record 188 | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_embrittle_pfs.py` | `Release/Spells.pfs`, `Release/Ability.pfs` |
| Ability-id ceiling ladders extended `0xB2`→`0xB3` (forced by Embrittled's new id) | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_abilityid_ceilings.py`, `build_tcablist_ceiling.py` | `AoWTCPCK.dpl`, `AoWz.exe` |
| Grip of Winter binary rework (cooling ladder, land targeting, temporary-terrain marker) | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_gripofwinter.py` | `AoWEPACK.dpl` |
| Grip of Winter rename ("Freeze Water" → "Grip of Winter") | 🔨 APPLIED, UNTESTED (2026-09-01)\* | `build_resstr_names.py` | `Dict/ResStr.mld` + `.txt` |
| Grip of Winter spellbook description | 🔨 APPLIED, UNTESTED (2026-09-01)\* | `build_pfs_typos.py` | `Release/Spells.pfs` record 20 tag 10 |
| Grip of Winter manual prose (shipyard-income section) | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_ziggurat_manual.py:2720` | generated Ziggurat Manual |

\* `build_resstr_names.py` and `build_pfs_typos.py` are shared, multi-feature batch scripts — dozens of
other renames/descriptions live in the same row lists. Their `--undo` reverts *every* row they currently
own, surgically and in reverse order, not only Grip of Winter's row. See "The data half" under Grip of
Winter.

All eight rows were re-verified live against the install on 2026-09-03 while writing this file (dry-run
of all three Embrittle scripts: `AoWEPACK state: APPLIED`, cave zone 357/768 B, `.reloc` coverage clean,
both `.pfs` records present and matching; dry-run of `build_gripofwinter.py`: `state: MIXED` — six caves
`PATCHED`, `C_SHOW` reads `*** FOREIGN ***`, which is the coupling described below, not a defect).

## The recipe: clone the instance, not the class

Both features avoid the expensive path for adding spell-like content — a brand-new `TObject` descendant
needs a unique save/network `ClassID` through `RegisterEClasses`, because a combat action or an ability
is a serialised object. Neither script does that. The recipe, in the order you actually apply it:

1. **Find a vanilla class that already does the mechanic you want.** Check whether what makes it "that
   specific spell" is structural (a genuinely different code path) or just a handful of hard-coded
   constants. `TSlow` qualifies for Embrittle: every method is generic except three sites that assume
   ability id `0x84`. `TFreezeWater` qualifies even more directly for Grip of Winter — not cloned at
   all; six of its methods simply gain a few extra bytes of behaviour.
2. **⭐ Clone the INSTANCE, not the class.** Call the vanilla constructor, then overwrite the id, the
   name and the tunables on the resulting object. Embrittle *is* a `CombatSpells.TSlow` instance with a
   different `[+0x10]` id — no VMT clone, no new class, no `RegisterEClasses` call, and
   serialisation/network identity/replay are untouched because the class itself never changed.
3. **The hard-coded constant almost always has its replacement already sitting in a register** at every
   site that reads it. `TSlow.CreateCA`/`TSlowCA.Execute` already hold the spell id, or the combat
   action's own `[+0x18]` field, exactly where they compare against `0x84` — so the "new archetype"
   collapses into three or four small caves that recompute the comparison against the object's *own* id.
4. **If the clone needs a bit of state the vanilla class doesn't expose**, check what the class's
   declared instance size covers versus what its methods actually reference — Delphi alignment padding
   is frequently free storage, with no resize and no save-format change. See "A class's spare alignment
   padding is free instance storage" under Grip of Winter.
5. **A spell that can be aimed has at least two gates**, not one: whether a cast at a given target is
   *valid*, and what the cursor is willing to *highlight*. See "Two gates" under Grip of Winter.
6. **Registering the new id must chain onto the LAST still-direct call in the registration loop**, never
   an address another feature already repointed — re-measure at build time, don't trust a comment (see
   "Registration sites" under Embrittle).
7. **Anything a cave does at package/DLL init — before any exception handler exists — must be proved by
   launching the executable, not by static verification.** The headline lesson of this file; see the
   callout under Embrittle.
8. **The spell/ability's tunables live in a `.pfs` record keyed off the id**, not in the cave. Clone an
   existing record of the same class/tactical-type and re-key it; see "The `.pfs` / `.ail`
   record-splicing rules" near the end of this file.
9. **The auto-combat overrides take different EDX objects.** `+0x90 fcPrefetchCombatCommands` gets a
   `TFastCombatCommandList` (`TFastCombatCommandList.Create @0x5574390C`: `+4` caster, `+8` own side,
   `+0xC` enemy side, `+0x10` TFastCombat). `+0x94 fcExecuteCombatCommand` and `+0x98
   fcGetDamageValueEx` get the acting combat object, whose `+8` is the TFastCombat; `+0x98`'s out
   record is `[esp+4]`, the wall situation `[esp+8]`. Reading the list's `+8` as the TFastCombat
   crashed every auto-resolved battle with Taint the Flame in the hero's book (fixed 2026-10-28).

Both features below instantiate this recipe end to end; read them for the byte-level version.

## Embrittle — new tactical spell (id 109) + Embrittled status (ability `0xB2`)

**🔨 APPLIED, UNTESTED (2026-09-01).** Mechanics, icon and `.pfs` records are all written; the game
launches cleanly with all of it installed (see "Checks already done"). Nothing beyond that is confirmed.

Backups `.pre-embrittle` exist for both binaries. **Revert with `--undo`, never by copying them** — the
`AoWTCPCK.dpl.pre-embrittle` snapshot predates the ability-id ceiling bump this feature also forced, so
restoring it would silently undo that too.

```
python build_scripts/build_embrittle.py            # dry run + verify + disassembly
python build_scripts/build_embrittle.py --apply     # write it
python build_scripts/build_embrittle.py --undo      # restore all 7 hooks, zero the cave
python build_scripts/build_embrittle_icon.py --apply    Images/(_)SpellIcn.ILB ) run icon
python build_scripts/build_embrittle_pfs.py  --apply    Release/Spells.pfs    ) BEFORE pfs
```

⚠ Apply order matters (icon before pfs — the record's icon field points at the ILB entry the icon
script rewrites). **`--undo` order does not**: each of the three scripts targets an independent
file/byte-range and none of them byte-compares another's output, unlike the Grip of Winter coupling
below — run any of the three `--undo`s in any order, or just the one you need.

### What it does

Cast in tactical combat at a single enemy unit, opposed by the target's Resistance exactly like Slow. On
a hit the target gains the **Embrittled** passive for the rest of that combat; while it holds, every
incoming damage roll whose damage-type mask includes the physical bit does **×1.5, rounded up**, as the
Weakness abilities do (owner, 2026-10-27; it was ×2):

| target has | result |
|---|---|
| Embrittled only | `(3·dmg + 1) >> 1` |
| Embrittled **+ Physical Protection** (the halve fires) | doubled, then `(2·dmg + 1) >> 1` = **dmg**, exact cancellation |
| Physical Protection only | `(dmg + 1) >> 1` (vanilla, unchanged) |
| Physical **Immunity** | 0, as vanilla — and the cast fizzles rather than applying (below) |

The cave reads the protection mask itself to choose: doubling when the halve will fire (every type in
the hit protected), ×1.5 otherwise. Spectral Wings (`0x97`) answers the Embrittled query, so winged
units take the same in battle. ⚠ Forward hazard — the same ×1.5 lives in other caves, so a re-tune
here needs them too: `build_razorplate.py`'s AI estimate (`dv_body`'s E[cut] of 48; the cut itself
goes through this routine since 2026-10-29, after its copy trailed at ×2 for a day), and `build_airwater_ench.py`'s
`cave_pw` is Spectral Wings' own world-map ×1.5 (in battle it borrows this cave through the
Embrittled query). `build_weakness.py`'s seven Weaknesses use the same factor in both engines.

Design decisions were the user's (2026-09-01): Earth sphere, tier 3 research, a physical weakness on any
hit carrying a physical component, cancels exactly against Physical Protection, refused (fizzles) on Physical Immunity
targets, resisted the same way as Slow. `SPELL_POWER` (`= 9`, `[spell+0x34]`) is the one-line tuning
knob if it lands too often or too rarely — already on the Ziggurat scale, left at Slow's own value
deliberately. Every hook re-derives Slow's own ability id `0x84` for any spell id that is not
Embrittle's. (Slow is now Lethargy, `build_lethargy.py`, `04-spells-modded.md`; that script also gives
both spells an AI value through `TSlow`'s VMT slots `+0x98` (auto-resolve) and `+0x84` (manual combat),
so the zero-value `TSlow.GetCombatDamageValueEx` below is no longer on either path.)

### The effect site — one function, every combat system

```
AoWE.TCombatObject.ExecuteDamageRole    @0x557269F0   VMT +0x110   mask at [ebp+0x08]
AoWE.TCombatObject.ExecuteDamageRoleEx  @0x55726A6C   VMT +0x114   mask at [ebp+0x0C]
```

These are the **only** damage roll in the game; `Ex` differs solely in picking Resistance (VMT `+0x74`)
over Defence (`+0x70`). Neither is overridden anywhere — `TCombatObject` and `TCombatUnit` both carry
`0x557269F0` at `+0x110` (`12-re-toolchain.md`), and `AoWTCPCK`'s `TTacticalCombatUnit` reaches them
through an import thunk — so **one patch covers manual tactical combat, auto-resolve and the strategic
map alike**. Hooking the shared implementation instead of a VMT slot is the same reasoning
`build_reformingflesh.py` uses for the round-tick dispatch.

Vanilla tail, with the hooked 10 bytes marked (`mov eax,ebx` / `mov edx,[eax]` / `call [edx+0x80]`):

```
55726A38  mov  edi, eax                ; EDI = the rolled damage
55726A3A  mov  eax, ebx                 } HOOKED at 0x55726A3A (Role) / 0x55726ACF (RoleEx)
55726A3C  mov  edx, [eax]               }
55726A3E  call [edx+0x80]              ; TCombatObject.GetProtectionTypes -> AX
55726A44  not  eax
55726A46  and  ax, si                  ; ESI = ~immunity & damage-type mask (already live)
55726A49  mov  dx, [0x55726A68]        ; a zero word constant
55726A50  cmp  dx, ax
55726A53  jne  0x55726A5D              ; not every bit covered -> no halve
55726A55  inc edi / sar edi,1 / ...    ; (dmg+1)>>1 = Physical Protection's halve
```

Both hook sites replace the same 10 bytes (`8b c3 8b 10 ff 92 80 00 00 00`) with `mov ax,[ebp+disp]`
(4 B) + `call cave_dmg` (5 B) + `nop`, `disp` = `0x08` for `ExecuteDamageRole` and `0x0C` for
`ExecuteDamageRoleEx` — the only per-site difference; the cave itself (53 B, live-disassembled and
verified 2026-09-03) is shared.

⚠ **The doubling goes BEFORE the halve, and that ordering is the feature.** `cave_dmg` doubles EDI and
then tail-jumps into the vanilla `GetProtectionTypes` call, so the halve — if it fires — sees the
already-doubled figure and cancels it exactly. Doubling *after* would give `((dmg+1)>>1)×2`: 5 damage
would come back as 6, not 5. Do not "simplify" the add below the call.

⚠ The halve is an **all-bits** test (`(~prot & ~imm & mask) == 0`, every damage type in the mask must be
covered); the doubling is an **any-bit** test (`mask & 0x80`), by design. A fire+physical strike on a
unit with Physical Protection alone is therefore doubled and *not* halved — correct, because that
protection genuinely does not apply to that hit in vanilla either.

⚠ `TCombatWall` is also a `TCombatObject`. It answers the ability query through
`TCombatObject.GetAbilityEnabled @0x557268D4` (`xor eax,eax; ret`), so walls can never be embrittled and
need no type test — the same free type-gate `build_reformingflesh.py` relies on.

**The damage-type bit order**, fixed by `TAbilityOwner.GetAbProtectionTypesAll @0x5574F97C` and
`GetAbImmunityTypesAll @0x5574FADC` (the two functions that build these masks):

| bit | type | | bit | type |
|---|---|---|---|---|
| `0x01` | Fire | | `0x10` | Poison |
| `0x02` | Cold | | `0x20` | Death |
| `0x04` | Lightning | | `0x40` | Holy |
| `0x08` | Magic | | `0x80` | **Physical** |

Physical Protection = ability `0x4D` or `0xA6` → bit `0x80`; Physical Immunity = ability `0x0D` → bit
`0x80`.

**The damage clamp is 126, not 49.** `TCombatObject.ExecuteDamage @0x55726C58` asserts `damage < 0x7F`
("Invalid Damage Value"). Vanilla was `0x31` (49); Ziggurat already raised it to `0x7F` as part of the
general DAM/HP doubling pass — easy to get backwards if this function is read from a Ghidra decompile,
whose image is pristine vanilla. `cave_dmg` clamps at 126 so a doubling can never turn a big hit into an
assert dialog; reachable only in absurd cases, it is insurance, not a live constraint.

### The spell — no new class, no new save/network ClassID

`TSlow` hard-codes ability id `0x84` in exactly three places, every one of which already has the spell
id or the combat action's own id field in a register:

| site | vanilla | hooked as | discriminator |
|---|---|---|---|
| `TSlow.CreateCA @0x557F89B3` | `mov edx, 0x84` | left alone — the next site's cave recomputes EDX | — |
| `TSlow.CreateCA @0x557F89BC` | `call [ecx+0xA8]` (6 B) | `call cave_createca` + `nop` | `[esi+0x10]` = spell id |
| `TSlowCA.Execute @0x557F884F` | `mov edx, 0x84` (5 B) | `call cave_absel` | `[ebx+0x18]` = spell id |
| `TSlowCA.Execute @0x557F8863` | `mov edx, 0x84` (5 B) | `call cave_absel` | `[ebx+0x18]` = spell id |

`[CA+0x18]` is stamped by `TSlow.CreateCA @0x557F89A1`, copying `[spell+0x10]`. Serialisation, network
identity and replay are untouched: **every Embrittle combat action is a bit-for-bit ordinary `TSlowCA`**
— simply built from a spell object whose id is 109 instead of `0x84`'s own spell, 110.

Registration hooks chain onto the **last still-direct call** in each loop, re-measured rather than
trusted from a comment:

| what | registers as | hook site | vanilla instruction |
|---|---|---|---|
| ability `0xB2` | `PassiveAb.TAbilityControl.RegisterAbility @0x55750238` | `0x557BCE65` | `call RegisterAbility` (5 B) |
| spell 109 | `AoWE.TSpellControl.RegisterSpell @0x55779B40` | `0x557FA83F` | `call RegisterSpell` (5 B) |

Fields poked on the cloned `TSlow` instance after calling its vanilla constructor (everything else is
inherited): `[+0x10]` id `109`, `[+0x14]` mana `14`, `[+0x18]` research cost `80`, `[+0x20]` sphere `3`
(`msEarth`), `[+0x21]` tier `3`, `[+0x34]` power `9`. `TMagicSphere`: `0` Cosmos, `1` Life, `2` Death,
`3` Earth, `4` Air, `5` Fire, `6` Water. Mana and research were calibrated against **Tremors**, the other
Earth tier-3 combat spell (also mana 14, research 80). **Free spell ids are now 80–99** (79 is Regeneration), and `0xB2` was
the first free ability id at the time (`0xB1` Reforming Flesh was the prior top).

#### Registration sites — chain, never re-use

Measured live 2026-09-01 inside `PassiveAb.RegisterPassiveAbilities @0x557BC1CC` (length `0xE00`): 83 of
87 calls were still direct; the four already repointed were `0x557BCE9A` (→ reformingflesh's cave),
`0x557BCECF` (→ shield's), `0x557BCF04` (→ caster_cost's), `0x557BCF39` (→ drillmaster's). `0x557BCE65`
was the last still-direct one and is what this feature took. The equivalent scan of
`CombatSpells.RegisterCombatSpells @0x557FA50C` found `0x557FA83F` still vanilla.

⚠ **Taking a site another feature already repointed is the documented silent-unlink failure** — the
earlier feature's cave simply stops being called, and nothing reports it (the Magebane/Shield chain
trap). The script's `assert_sites()` re-measures both loops at build time rather than trusting the table
above; keep that pattern when a third ability/spell is added. At both sites EBX holds the control object
for the whole enclosing function, and the instruction immediately before the call is `mov eax,ebx` —
which is what each cave's own `mov eax,ebx` relies on.

### The ability — instantiate `TSlowEnchantmentAbility`, do not build a class

`PassiveAb.TSlowEnchantmentAbility` (classref ptr `0x557B96B8`, `Create @0x557B9E78`) overrides only
`Create`, `CreateEnchantment` and `CombatDone`, and every one is driven by the ability's **own id
field**, not a constant:

```
CombatDone @0x557B9F24   owner := combatUnit.GetAbilityOwner()   ; VMT +0xB8
                         owner.RemoveAbility([self+0x0C])        ; VMT +0x98
```

so a second instance with `[self+0x0C] = 0xB2` removes `0xB2` at the end of combat entirely on its own —
no VMT clone, no new class, no `RegisterEClasses`. The cave calls the vanilla constructor, overwrites the
id and the name literal, and registers it.

⚠⚠ **NOT `CreateEnhancementAbility` — the trap that makes the "just clone Path of Sand" instinct wrong
here; don't retry it as-is.** A plain `TEnhancementAbility` has the wrong `AbilityDataClass`:
`TSlowCA.Execute @0x557F8863` does `GetAbilityData(unit, id)` and then calls `+0x54`/`+0x58` on
`[data+0x10]`, which only *exists* because `TUnitEnchantmentAbility`'s data class carries a
`TUnitEnchantment` there. Registering `0xB2` as a plain enhancement would fault, or silently no-op, the
moment `TSlowCA.Execute` ran.

The constructor leaves `[self+0x20]` (the `TAbilitySelectionType` mask) at 0, so Embrittled is never
offered in the editor, on items, or at hero level-up — exactly like Slow's `0x84`. That is also why no
`FExpandCost` store is emitted here (unlike `build_reformingflesh.py`): an ability nobody can select
cannot be bought.

### Physical Immunity — a fizzle, not a UI gate

**Manual tactical combat has no damage-based target gate at all.** Proof: `TSlow.GetCombatDamageValueEx
@0x557F8948` returns an all-zero struct and Slow is still freely castable; `TSpell.tcGetDamageValueEx`
(`+0x88`) just forwards to it and nothing consults the result for validity. Only **fast** combat (auto
resolve) gates on a value — `TCombatSpell.fcPrefetchCombatCommands @0x557F76BC` skips a target whose
`fcGetDamageValueEx` first dword is 0. Since `build_lethargy.py` that value is `cave_fcval`, which
returns 0 for a Physical Immunity target, so auto-resolve never picks one.

So the engine's own idiom for "this spell does not apply to that target" is a fizzle inside `CreateCA`,
not a target-selection gate, and `CombatSpells.TTurnUndead` is the vanilla worked example:
`TTurnUndead.CreateCA @0x557F7C50` builds the combat action and only wires up the hit-roll if the target
is undead — casting Turn Undead at a living unit is permitted and simply does nothing.

`cave_createca` copies that idiom exactly: on a Physical Immunity target it returns `AL=1` — "already has
the ability", the existing vanilla path for re-casting Slow on an already-slowed unit. The caller skips
`HitRole`, `[CA+0x14]` stays 0, and `TSlowCA.Execute` does nothing.

⚠ **The cast is still spent** — mana and casting points go, consistent with re-casting Slow on a slowed
unit in vanilla, but it is a fizzle, not a greyed-out target. A hard UI gate would need surgery on
`AoWTCPCK`'s targeting (`TTacticalCombatUnitHS.SelectSpell` and friends) and was descoped as a separate
feature — see "Open items." Physical Immunity already makes the ability inert on its own
(`ExecuteDamageRole` returns 0 before reaching the cave whenever `~immunity & mask` is empty), so the
fizzle exists to avoid wasting the cast, not for correctness.

### AoWTCPCK — `SpellTypes[109]`, the byte that stops the spell vanishing

`AoWTC.SpellTypes @0x004672F4` (`AoWTCPCK.dpl` DATA, file offset `0x662F4`) is `byte[0..130]`, one
tactical-combat class per spell. A spell with id ≥ 100 whose byte is 0 is **silently deleted from the
research list** by `AoW.exe @0x0042F304` (`03-abilities-added.md` §S3). 109 was the vanilla registry hole, so
its byte was 0.

Set to `0x07` — measured, not guessed: `SpellTypes[110]` (Slow) and `SpellTypes[111]` (Entangle) are
both `0x07`, the single-enemy-unit-target tactical class, exactly what Embrittle is. Own-module DATA at
a fixed base (element address `0x00467361` for index 109), so no `.reloc` concern and no cave needed.

### Ability-id ceiling — two other scripts had to move, and their failure mode is silence

Vanilla's highest ability id was `0xA9`, so nine `cmp <counter>, 0xAA` loop terminators exist across
`AoWTCPCK.dpl`, `AoWz.exe`. Registering `0xB2` made both ceiling ladders one short.
Extended and re-applied 2026-09-01:

```
build_abilityid_ceilings.py   LADDER = (0xAA, 0xB1, 0xB2, 0xB3)   6 sites
build_tcablist_ceiling.py     LADDER = (0xAA, 0xB1, 0xB2, 0xB3)   1 site
```

Both derive their target list from `re_tools/ability_names.py`, so `0xB2: "Embrittled"` was added to its
`MODDED` map as part of this feature — **a registration cave is invisible to that module's own
constructor scan** (it only sees Slow's hard-coded `0x84`), so without the map entry the ability prints
as `?` and neither ladder script would know to move. **Shield shipped four days before anyone noticed
this exact omission for its own ability id** — a standing trap for every future ability, not a one-off.
Left unraised, the ability still works but is invisible to the tactical AI's battle scoring, the item
banner popup, the unit hover popup, and `CreateTCAbList`.

### The data half — icon and `.pfs` records

Two more scripts, both data-only. **Apply order matters — icon before `.pfs`** — the record's icon field
points at the ILB entry the icon script rewrites.

#### The icon — a cracked-bone stamp, reusing a dead entry, no format surgery

The shipped `SpellIcn.ILB` held 111 entries (ids 0–155), of which only 108 were referenced by any spell;
**128, 129 and 155 were dead.** Entry 128 (a Dragon on a Cosmos-purple disc, cut content) is reused
rather than appended, in `SpellIcn.ILB` and in its half-resolution twin `_SpellIcn.ILB` (since
2026-10-27; the twin had kept the Dragon). All three writes per twin are exact-size:

| write | length (full / half twin) |
|---|---|
| frame pixels ← the same twin's icon 52 (Slow), the real `SI-Earth.BMP` disc, read live | 2800 B / 720 B |
| frame `transparent` field (directory record, `clip_off + 16` = `0x4FFD` in both): `0x00000000` → `0x00004148` | 4 B |
| sub-entry pixels (34×29 at (2, 3), the same size in both twins) ← the cracked-bone artwork | 1972 B |

⚠ The pixel offsets are found by walking the file on every run. `build_dual_spell_icons.py` inserts
directory records, which moves all pixel data; the first version stored offsets (`0x8B4C5`, `0x8BFB5`)
and read FOREIGN by 2026-10-27.

⚠ **The `transparent` write is not cosmetic.** Entry 128's frame declares `0x0000` (pure black) while
the real Earth frame contains 113 pure-black pixels; any blitter honouring the colour key would punch
113 holes through the disc. Every genuine Earth icon declares `0x4148` — a value absent from its own
pixels, i.e. "key nothing" — so matching it makes the new entry behave byte-for-byte like a known-good
Earth icon instead of resting on an assumption about whether the engine even honours the field.

The art is stored in the script as a literal 34×29 character grid over a 6-level grey ramp — reviewable
in a diff, hand-editable, and immune to a PIL version silently changing its resampling.

⚠⚠ **v1 of the icon shipped 1-bit art and that was wrong — read the measurement before "cleaning up" any
future icon's edges.** The mistake was reading a prior tool's note that "25 pixels in the entire file
are off-grey" as *not black or white*, when it actually means *off-neutral* (off the r=g=b axis). A
measurement across all 110 vanilla spell overlays (133,984 px) found black/mid-tone/white shares of
17.3% / 14.1% / 68.6%, with the mid-tone band running 8–17% per icon (Slow 8.1%, Entangle 7.9%, Tremors
10.1%, Stone Skin 11.9%) — those mid-tones are the soft anti-aliased outline every vanilla icon has, so a
hard-edged 1-bit stamp reads as visibly foreign next to them. v3 (2026-10-27, the owner's pick, draft C
of four, after v2 ran edge to edge with a break that was hard to see) is a whole bone at about 80 % of
v2's span with a white branching crack along the shaft: 16.0% black / 10.9% mid-tone. The background
stays exactly `0xFFFF`, the sub-entry's own declared transparent value.

`--undo` restores the vanilla Dragon/Cosmos entry: `SpellIcn.ILB`'s from a zlib+base64 blob embedded in
the script (the GOG root's `SpellIcn.ILB` has no entry 128), `_SpellIcn.ILB`'s from the root's
`_SpellIcn.ILB`.

#### `Spells.pfs` record 119 and `Ability.pfs` record 188

Both cloned from Slow's own records rather than hand-authored — see "The `.pfs` / `.ail`
record-splicing rules" near the end of this file for the shared mechanism. Specifics, verified live
2026-09-03:

**Spell record 119** (= spell id 109 + 10), cloned from **record 120 (Slow)**: same class, sphere,
tactical class and targeting; six fields patched — description, `SPELLICN.ILB` icon index `52 → 128`,
mana `14`, research `80`, sphere `3`, tier `3`. The 1008-byte nested `TImageSequenceList` (cast
animation) and the `TSFXLibrary` node are inherited from Slow wholesale. Installed description:

> *"Makes a target's body brittle, causing it to suffer double damage from physical attacks for the
> duration of combat."*

**Ability record 188** (= ability id `0xB2` + 10), cloned from **Slow's own ability record 142**, the
deliberate mirror of vanilla Physical Protection's wording:

> Physical Protection — *"Reduces the damage inflicted upon the unit by physically-based attacks by
> 50%."*
> **Embrittled** — *"Doubles the damage inflicted upon the unit by physically-based attacks, for the
> duration of combat."*

⚠⚠ **Slow is the donor specifically because its tag 9 is `00 00`.** Tag 9 is the `TAbilitySelectionType`
mask, and `Ability.pfs` **overwrites the registration cave's value with it** once the record exists.
Cloning Physical Protection's record instead would have shipped tag 9 = `0x03FF` and made Embrittled
selectable in the editor, on items and at hero level-up — a status ability offered as a purchasable
perk. Slow's `0` keeps it status-only, matching what the constructor sets. **This is a general rule for
any status-only ability clone: check the donor's tag 9, not just its class.**

Once record 119 exists, **the data file wins** for tags `0x0A`–`0x11`: `build_embrittle.py`'s
mana/research/sphere/tier constants become decorative, and the spell is re-tuned in the `.pfs` (or in
AoWDevEd) from now on, exactly like any vanilla spell.

Verified: 108 → 109 `Spells.pfs` records, every other record byte-identical field-by-field, CRC residue
correct, `--undo` restores both files byte-identically, and an independent reader (`re_tools/pfs.py`)
re-parses the result the same way. (In passing, this work found and fixed a silent path bug in
`re_tools/spell_icons.py` — it looked for `spell_names.json` in the wrong directory, guarded by an
`os.path.exists` check, so the contact sheet rebuilt cleanly and simply captioned every icon "no spell
with this id"; also use `grep -o | wc -l`, not `grep -c`, on that tool's one-line HTML output.)

### ⚠⚠ v1 broke STARTUP — "Runtime error 216 at 00003924" — and every static check had passed

**This is the most important lesson in this file.** Fixed 2026-09-01, roughly an hour after the first
apply. Read it before writing any cave that assigns a string.

**The bug.** A Delphi `AnsiString` variable holds a pointer to the string's **first character**: the
refcount lives at `pointer − 8` and the length at `pointer − 4`. The literal blob this cave writes into
its zone is laid out `[refcount = −1][length][chars][NUL]`, so the value that must be handed to
`System.@LStrAsg` is **blob address + 8**, not the blob's own address.

v1 passed the blob address itself. `@LStrAsg` therefore read "the refcount" from the 8 bytes *before*
the literal — the zero padding at the front of the cave zone — saw `0`, and because `0 ≥ 0` means "a
live string, not a compile-time literal" to `@LStrAsg`, it performed an `InterlockedIncrement` on that
location. That is a **write into the read+execute CODE section**, executed during package init at DLL
load, before any exception handler exists. Access violation ⇒ **"Runtime error 216 at 00003924"** on
startup, from both `AoW.exe` and the editor — the game never reached its main menu.

⚠ **216 is a GPF. 217 is the separate duplicate-ability-id error** (`RegisterAbility` raising before a
handler exists — see `03-abilities-added.md`). The two are easy to confuse when diagnosing a startup failure;
this one had nothing to do with ids, and chasing the id ceiling instead would have wasted the session.
`build_reformingflesh.py` had the `+8` right all along, and even says so in an inline comment — the cave
*shape* was copied from that precedent, but the `+8` was not carried across with it.

**⭐⭐ The real lesson: every static check passed anyway.** Byte-level verify-before-write, the `.reloc`
coverage scan, the PIC audit, the `--undo` round-trip proving byte-identical restoration,
`rng_audit.py --owners`, the profile-path scan — **all green, on a build that could not start the
game.** None of them can see a pointer that looks correct but is 8 bytes early.

**So: a cave that runs at package/DLL init must be proved by LAUNCHING THE EXECUTABLE, and that is not
an "in-game test" to hand to the owner — it is a build-time check the author owes.** Launch, wait about
ten seconds, assert the process is alive, responding, and that no window titled "Error" exists. It is a
few seconds of work and it is the only check that would have caught this.

**The guard now in the script.** `build_zone()` decodes the address the assembled cave actually resolves
for each name literal and asserts it equals `header + 8`, and that the dword at `ptr − 8` is the `−1`
literal refcount. The broken v1 layout is kept as `PRIOR_ZONES[0]` so verify-before-write recognises it
as one of the script's own legitimate pre-states and **rewrites the cave in place** — never a revert, per
the project's layering rule (a `.pre-*` restore would wipe every feature layered on afterwards). Nothing
needed migrating: v1 never ran long enough to reach a save, so no save can contain spell 109 or ability
`0xB2` in the broken layout.

### Version history (cave layout)

| version | name | header bias | outcome |
|---|---|---|---|
| v1 (2026-09-01, ~1 h) | Embrittlement | `0` (header address passed directly — the bug) | GPF at startup, "Runtime error 216." Never worked; no save can reference it. |
| v2 | Embrittlement | `8` (correct) | Launches. Superseded for the name only. |
| v3 (to 2026-10-21) | **Embrittle** | `8` (correct) | `cave_reg_abil` called `TSlowEnchantmentAbility.Create` with ECX = the classref cell, which `TEObject.Create` stores as the owner. No symptom (the owner callbacks it reaches do nothing); Inioch's Slow clone died of the same garbage owner with "Runtime error 216" (share9). |
| v4 — current, shipped | **Embrittle** | `8` (correct) | `xor ecx,ecx` before the constructor, as vanilla does at `0x557BCAD4` and as `cave_reg_spell` already did. Fits the same 16-byte slot; no other cave moved. The owner launched the game successfully the same day. |

**Why "Embrittle", not "Embrittlement"** (decided 2026-09-01, after checking vanilla rather than
assuming): vanilla inflects a status name away from its spell's — `PassiveAb.TBlessedEnchantment.Create`
loads `BlessedRStr`, not `BlessRStr` (spell *Bless*, status *Blessed*), and abilities `0x28`/`0x5E` ship
as separate "Entangle"/"Entangled" resourcestrings. Entangle is Embrittle's closest sibling in every
respect that matters for naming — Earth sphere, tactical combat, single enemy target, applies a status —
and it is an imperative verb; 27 of 109 vanilla spell names are one word, verbs well represented (Bless,
Desiccate, Entangle, Slow, Stoning, Vaporize). "Embrittlement" would have been the only `-ment` abstract
process-noun in the list, so the spell became **Embrittle** and the status stayed **Embrittled** — the
Entangle/Entangled shape. (`re_tools/ability_names.py` prints names like "Blessed Enchantment" — those
are class-derived artefacts of its constructor scan, not the in-game names, and not evidence of a
convention.)

⚠ Renaming was an **in-place cave rewrite, not a revert**: a name is a variable-length literal, so
changing it moves every cave placed after it in the zone. `build_zone()` takes `spell_name`/`abil_name`
parameters precisely so `PRIOR_ZONES` can reproduce the older layouts byte-for-byte and
verify-before-write recognises them as legitimate history rather than "foreign" bytes. Names are not
serialised — the id is — so the rename itself has no save or multiplayer consequence.

### Addresses

| what | address |
|---|---|
| cave zone | `0x5582D000..0x5582D300` (357 B used of 768 reserved) |
| ↳ `Embrittled` / `Embrittle` name literals | `0x5582D000` / `0x5582D014` |
| ↳ `cave_reg_abil` / `cave_reg_spell` | `0x5582D030` / `0x5582D070` |
| ↳ `cave_createca` / `cave_absel` / `cave_dmg` | `0x5582D0D0` / `0x5582D110` / `0x5582D130` |
| ability registration hook | `0x557BCE65` |
| spell registration hook | `0x557FA83F` |
| `TSlowEnchantmentAbility.Create` / classref | `0x557B9E78` / `0x557B96B8` |
| `TSlow.Create` / classref | `0x557F8890` / `0x557F4DC0` |
| `TAbilityControl.RegisterAbility` / `TSpellControl.RegisterSpell` | `0x55750238` / `0x55779B40` |
| `System.@LStrAsg` thunk | `0x55701150` |
| `AoWTC.SpellTypes` base (AoWTCPCK DATA) | VA `0x004672F4`, file offset `0x662F4` (index 109 element: `0x00467361`) |
| `ExecuteDamageRole` hook / `ExecuteDamageRoleEx` hook | `0x55726A3A` / `0x55726ACF` |
| damage clamp assert | `TCombatObject.ExecuteDamage @0x55726C58` |

Cave placement: `0x5582D000` is page-aligned, above every address any build script claimed as of
2026-09-01 (highest prior claim `0x5582C080`), with 764,416 zero bytes ahead of it and no `.reloc` entry
in the zone. ⚠ **Do not "reclaim" the apparent gap below it** — `build_rng_lockstep.py`'s rng_sync stub
and `build_panic_nomelee.py` sit inside what looks like one enormous free run; a zero run is not proof a
zone is unclaimed, it is usually another feature's growth reservation (on record three times in this
folder). Don't quote either script's raw address in a new comment either: `rng_audit.py --owners`
attributes an RNG site to every build script whose *text* contains the address, so naming another
feature's cave here previously made the audit misreport this feature as owning a synced draw.

### Checks already done (static, 2026-09-01; re-verified live 2026-09-03)

- All 7 `AoWEPACK.dpl` sites plus the `AoWTCPCK.dpl` byte read back `applied` (`AoWEPACK state: APPLIED`);
  every displaced run and the cave zone are `.reloc`-clean; caves are position-independent (register-only,
  `call`/`jmp rel32`, `call <addr>; pop ecx` delta anchors for the two literal/classref addresses); the
  zone holds no absolute address and no drive-letter path, only the two name literals.
- `--undo` round-trip: `AoWEPACK.dpl` comes back byte-identical (SHA-256) to its pre-patch state;
  `AoWTCPCK.dpl` differs by exactly the 5 ceiling bytes applied afterwards, nothing else.
- `rng_audit.py --owners`: owns **no** RNG site, adds no draw (`HitRole` is called by the untouched
  host); no profile-path leak in any binary or edited script (`grep -laF`, with `-a`).
- **The game launches**: `AoW.exe` ran 71 s (68 s CPU), `Responding=True`, main window titled "Age of
  Wonders", no window titled "Error" anywhere. (Window rect reads 0×0 — DirectDraw exclusive fullscreen,
  so a screen-grab tool can't capture it; process health is the usable signal.)
- `Spells.pfs`/`Ability.pfs`: 109 and 159 records respectively, both CRC OK, both target records present
  and matching this build.

### In-game checklist — nothing below is checkable from the files

1. **Embrittle** appears in the Earth sphere, tier 3, of the research list; its spellbook page shows the
   broken-bone icon, the description above, and a cost of 14 mana.
2. Every *other* spell still shows its own icon and text (the `.pfs` byte audit proves the bytes are
   untouched, not that the game agrees).
3. Once researched, it is castable in tactical combat at a single enemy unit for 14 mana, and lands or
   is resisted the way Slow is.
4. A unit it hits shows **Embrittled** in its ability list for the rest of that combat, and the status is
   gone at the start of the next battle.
5. A melee hit on that unit does roughly double its normal damage.
6. On a unit that also has Physical Protection, damage is back to normal.
7. Casting it at a Physical Immunity unit does nothing (mana is still spent — the documented fizzle, not
   a bug).
8. Lethargy (ex Slow) works on its own spell and its own status — its checklist is in
   `04-spells-modded.md`.
9. Auto-resolving a battle involving an embrittled unit raises no assert dialog.
10. Ranged and elemental-strike weapons against an embrittled unit are doubled too (the mask test is
    any-bit, so a physical+elemental strike should double as well).

## Grip of Winter (ex–Freeze Water) — terrain-cooling rebuild

**🔨 APPLIED, UNTESTED (2026-09-01).** All four pieces (binary, rename, description, manual prose) are
installed and byte-verified; nothing is confirmed until it is played. Every address below was read out
of the **live** `AoWEPACK.dpl`; the design decisions are the user's (2026-08-31). Part of the terrain
system — see `09-terrain-movement.md` for the raise-terrain / underground-earth side this feature is
coupled to.

```
python build_scripts/build_gripofwinter.py            # verify only
python build_scripts/build_gripofwinter.py --dis      # + cave disassembly
python build_scripts/build_gripofwinter.py --apply
python build_scripts/build_gripofwinter.py --undo     # surgical, no backup touched
```

Revert is `--undo` — surgical, verified byte-exact, touches no backup. **⚠⚠ But see "Coupling with
`build_raiseterrain_ug_earth.py`" below: while that script is installed, this one can neither `--apply`
nor `--undo`.** Live-verified 2026-09-03: a dry run of this script currently reports `state: MIXED` —
six caves `PATCHED`, `C_SHOW` reads `*** FOREIGN ***` — which is exactly that coupling, not a defect.

### What is being built

Freeze Water becomes **Grip of Winter**: it keeps its ice, gains a temperature-cooling ladder, and
becomes castable on any hex rather than water only. The cooling is temporary and reverts, the same way
the ice already melts back.

| | |
|---|---|
| Ladder (one step per cast) | Desert(2) → Steppe(4) → Grass(1) → Snow(3) |
| Water arm (unchanged) | Water(0) → Ice(6); CaveWater(A) → CaveIce(D) |
| Footprint | unchanged — radius 1, the target hex and its six neighbours |
| Duration | temporary, same timer and melt path as the ice |
| Target gate | widened from water-only to any explored hex with no structure and no army |
| Binaries touched | `AoWEPACK.dpl` only, plus `Dict/ResStr.*` and `Release/Spells.pfs` |

Snow is the floor — nothing cools past it, and Wasteland/Lava/Dirt/Ice are deliberately not on the
ladder (a wider "cool lava and wasteland too" variant was offered and declined by the user).

### Baseline — one pre-existing orphan byte that `--undo` must not touch

Every Freeze Water function is byte-identical to `AoWEPACK_original_backup.dpl` except one byte:
`0x5579E96B`, `mov edx,0xB` in the pristine DLL vs. `mov edx,0x20` in the live one — the **initial
freeze countdown range**: pristine `Random(0xB)` gives 1–4 turns, live `Random(0x20)` gives 2–8 turns.
It is a **pre-convention orphan edit with no owning build script**; nothing re-derives it if it is ever
lost, and `build_gripofwinter.py` restores *that* byte on `--undo`, not the pristine one. The hook this
feature adds sits `0x19` bytes past it and does not displace it. Verified still `0x20` after every
apply/undo round-trip.

### The five vanilla functions involved

```
GlobalTargetSpells.TFreezeWater.Create                    0x5579EAE8   name + id 0xA + cost 5
GlobalTargetSpells.TFreezeWater.ValidTargetMapF            0x5579EB8C   water-only gate #1
GlobalTargetSpells.TFreezeWater.ValidTargetSelectionMapF   0x5579EBDC   water-only gate #2
GlobalTargetSpells.TFreezeWaterTE.ChangeTerrain            0x5579E884   per-hex mutate callback
GlobalTargetSpells.TFreezeWaterTE.TerrainChanged           0x5579E900   per-hex commit callback
AoWE.TFrozenWaterHS.*                                      0x55764AA0+  the temporary-terrain marker
```

`TFreezeWaterTE.Process @0x5579E994` drives it all: map VMT `+0xD4` (`ChangeTerrainEx`, area form),
`push 1` (radius 1) at `0x5579EA99`, with the two callbacks above.

### The cooling ladder

`TFreezeWaterTE.ChangeTerrain @0x5579E884` (`EAX` = TE, `EDX` = map field, `ECX` = → terrain byte,
`RET 4`). Vanilla only ever branches on 0/6/A/D and falls through to nothing for every other terrain —
that fall-through is the gap the ladder fills:

```
5579E890  call GetArmyHS(field)     ; an army on the hex -> nothing happens at all
5579E899  jne  0x5579E8F7           ;   (epilogue)
5579E89B  movsx eax,[ebx]           ; <-- HOOK, 6 bytes (0F BE 03 66 85 C0)
5579E89E  test ax,ax                ;     0 Water     -> 6 Ice
5579E8A8  cmp  ax,0xA               ;     A CaveWater -> D CaveIce
5579E8B3  sub al,6 / sub al,7       ;     already 6/D -> refresh the melt timer
5579E8BB  jne  0x5579E8F7           ;     EVERYTHING ELSE -> nothing        <-- the gap
```

Hooked at `0x5579E89B` with `E9 rel32` + `NOP` — the identical 6-byte `movsx`/`test` idiom
`build_icestorm_lava.py` already uses on `TIceStorm.ChangeStormTerrain`. The cave (`C_COOL`, 47 B) tests
Desert→Steppe, Steppe→Grass, Grass→Snow in turn, writes through ECX and jumps to the epilogue on a hit,
or replays the original `movsx`/`test` pair and resumes vanilla on a miss. Register-only + rel32, so
position-independent, as every cave in a rebasing `.dpl` must be.

Placing the hook *after* the `GetArmyHS` gate makes cooling inherit the spell's existing "not under an
army" rule for free. No RNG is added — note this function already draws from the **synced** generator
(`TAoWHSMap.Random @0x5577827C`, called at `0x5579E8DC` for the water arm's variant roll), so a roll
could safely be added to the ladder later if ever wanted.

**One step per cast, no cascade.** `ChangeTerrainEx` makes a single pass per cast (unlike storms, which
pass over their centre four times via `TBlastStorm.UpdateStorm`), and the callback reads the original
terrain byte once. Desert → Snow therefore takes three separate casts — the same pacing as Healing
Showers and Desiccate.

### ⚠ A targetable spell has TWO gates, and they must move together

The base `TGlobalTargetSpell.ValidTargetMapF @0x5579E4A8` is just `mov al,1; ret` — the water
restriction lives entirely in two identical 15-byte fragments on `TFreezeWater` itself:

```
ValidTargetMapF           0x5579EBA0   movsx edi,[ebx+0x14]; test di,di; je ok; cmp di,0xA; jne reject
ValidTargetSelectionMapF  0x5579EBF0   the same test, on [esi+0x14]
```

**`ValidTargetMapF` decides whether a cast is valid at all; `ValidTargetSelectionMapF` decides what the
cursor is willing to highlight.** Both were widened so any terrain passes — patch only one and the spell
becomes either uncastable (cursor allows it, engine rejects it) or untargetable (cursor never offers it,
regardless of engine validity). This is the general shape for widening *any* targetable spell's terrain
gate, not just this one.

The surviving gates need no change and are worth keeping: `FindNoneTransparentHS(TStructure)` must be
null (no structure on the hex), `GetArmyHS` must be null (no army on the hex), and
`ValidTargetSelectionMapF`'s base call additionally requires the hex be explored.

### The temporary-terrain marker, and how the cooling reverts

`AoWE.TFrozenWaterHS` (ClassID `0x2016C`, VMT `0x557147B4`, classref slot `0x55714774`) is the existing
"this terrain change reverts" marker, and it already does all the hard work — a per-turn countdown, an
owner, save/load, and a melt that goes through `ChangeTerrainEx` so transitions, roads and bridges update
correctly. Measured layout:

| field | offset | meaning |
|---|---|---|
| instance size `[VMT−0x1C]` | — | `0x10` |
| map field | `+0x04` | the hex this marker sits on |
| countdown | `+0x0C` | decremented on the owner's turn |
| owner | `+0x0D` | caster's player tag |
| **restore terrain** | **`+0x0E`** | new field — see below |
| **set terrain** | **`+0x0F`** | new field — see below |

#### ⭐ A class's spare alignment padding is free instance storage

Every one of `TFrozenWaterHS`'s eight methods (`ClassID`, `GetLevel`, `ReadWrite`, `MeltIce`,
`TerrainChanged`, `NewTurn`, `MsgProc`, `Show`) was disassembled, and **none references `+0x0E` or
`+0x0F`** — Delphi's own alignment padding, sitting unused inside an instance size the class already
declares. (The only `+8` displacement anywhere in the family is `[ebx+8]` inside `TerrainChanged`, and
that is the incoming notification struct in `EDX`, not `Self`.) So the whole feature needed **no class
resize, no allocation change, and no new save-format version**: two bytes of storage the class was
already carrying, doing nothing, became `+0x0E` = "the terrain to restore" and `+0x0F` = "the terrain
this marker set." `0` at `+0x0E` means "a plain vanilla ice marker" — which is also vanilla's own restore
value for Ice(6), so the sentinel is semantically free, `InitInstance` zero-fills it, and every marker
that exists in a save from before this feature reads 0 and behaves exactly as it always did.

**This generalises past Grip of Winter**: before adding a field to any engine class, disassemble every
method and check what the declared instance size covers versus what is referenced. Alignment padding is
common in Delphi 3's default record layout and is often free storage with zero migration cost — an old
save never wrote it, and an id-indexed property table (below) loads it back as its zero default.

#### The four edits that add and consume the two new fields

**a. `TFreezeWaterTE.TerrainChanged @0x5579E900`** (`C_TCCLS` + `C_TCFIN`, hooks at `0x5579E90E`,
11 B, and `0x5579E984`, 6 B) — the commit-pass callback that creates markers. It is already handed the
**old terrain in CL** (`mov [ebp-1],cl` at `0x5579E907`) and the field carries the new terrain at
`[esi+0x14]`, so both new fields are available with no extra plumbing. Vanilla creates a marker only when
the new terrain is 6/D and the old one was not; widened to also create one when the cooling ladder
fired, stamping `+0x0E` = old terrain and `+0x0F` = new. The existing countdown (`Random(0x20)` → 2–8
turns, synced RNG, correct for this context) and owner assignment are reused as-is.

**b. `TFrozenWaterHS.MeltIce @0x55764AE0`** (`C_MELT`, hook 6 B) — vanilla restores Water(0) from Ice(6)
and CaveWater(A) from CaveIce(D), then frees itself. Given a land arm that pushes `[self+0x0E]` instead
of the hard-coded `0`/`0xA` into the same `ChangeTerrainEx` call (map VMT `+0xD0`, single-hex form). Note
vanilla does *not* explicitly destroy the marker after restoring — the terrain write itself fires
`TerrainChanged`, which sees the hex is no longer its terrain and destroys the marker there; the land arm
inherits that behaviour for free.

**c. `TFrozenWaterHS.TerrainChanged @0x55764B6C`** (`C_HSTC`, hook 9 B) — currently destroys the marker
whenever the hex is no longer 6/D. Left alone, this fires on the feature's *own* cooling and kills the
marker instantly, making the change permanent. Widened to also survive when `+0x0E != 0` and the new
terrain equals `+0x0F`. **This is the load-bearing edit for re-casting** — see the wrinkle below.

**d. `TFrozenWaterHS.Show @0x55764BD0`** (`C_SHOW`, hook 6 B) — see "C_SHOW" as its own subsection below;
it gates the shimmer, not a separate ice sprite.

#### Known wrinkle: re-casting on an already-cooled hex

Cast twice on the same hex (desert → steppe → grass) and there is only ever **one** marker. The commit
order inside `ChangeTerrainEx`'s pass 3 is: write the terrain bytes → `TMapField.TerrainChanged` (which
notifies the marker, i.e. edit (c) above) → the spell's own commit callback (edit (a)). So on the second
cast the marker sees grass ≠ its own `+0x0F` (steppe) and, unless edit (c) is written correctly, destroys
itself *before* the spell's callback runs — a fresh marker would then be created recording "restore
steppe," and one step of cooling would silently become permanent.

**Decided (user, 2026-08-31): the marker remembers the ORIGINAL terrain.** Edit (c) therefore does more
than survive: when `+0x0E != 0` and the new terrain is the next step down the same ladder, it **keeps
`+0x0E` unchanged**, updates `+0x0F` to the new terrain, and does not destroy the marker. A hex cooled
desert → steppe → grass then reverts straight back to **desert** in one hop, however many times it is
re-cast — it can never be terraformed permanently by repeated casting.

⚠ Because `TerrainChanged` notifies the marker *before* the spell's own commit callback runs, edit (c) is
the *only* place that ever sees a second cast while `+0x0E` still holds the original value — getting it
wrong there means the marker is already gone by the time edit (a) could have preserved anything.

### C_SHOW — an all-or-nothing gate on the sparkle, not a separable ice sprite

`TFrozenWaterHS.Show` makes exactly **one** outbound call: `ImageLib.TImageSequenceList.ShowLoopedEx`
(via thunk `0x5570291C`) — a looped animation driven by the global animation tick with a per-hex phase of
`hexX + 3·hexY`, so adjacent hexes don't pulse in step. That call is the Freeze Water **shimmer**, and it
is the *only* thing `Show` draws: there is no separate ice sprite anywhere in the class. The ice *look*
itself comes from the terrain byte (6 / `0xD`) painted by the terrain renderer, not from `Show`. Because
the shimmer is the whole of what `Show` draws, gating it (`C_SHOW`, 20 B: `[eax+0x0E] != 0` → `ret 4`
immediately, i.e. draw nothing) is necessarily all-or-nothing — there is nothing narrower to suppress.
That is the correct behaviour for cooled land (desert/steppe/grass/snow should not shimmer like ice), and
cooled land plus water/ice are the only two marker states this feature itself can ever produce.

⚠ **Coupling this created**: `build_raiseterrain_ug_earth.py` (applied 2026-09-03) also stamps
`TFrozenWaterHS` markers, for temporary underground-Earth hexes, and wants *its* markers to shimmer too.
Because `C_SHOW`'s gate is genuinely all-or-nothing on `+0x0E != 0`, that feature could not just reuse it
— it rewrites `C_SHOW`'s first six bytes to add one more clause (`+0x0F == Earth(7)` also shimmers). See
"Coupling with `build_raiseterrain_ug_earth.py`" below for the mechanics and the resulting apply/undo
ordering rule; the terrain side of that feature is documented in `09-terrain-movement.md`.

⚠ **If Earth is ever added to *this* feature's own cooling ladder**, the `+0x0F == Earth(7)`
discriminator the other feature relies on breaks, because Grip of Winter would then legitimately write
`+0x0F = 7` too — a cooled land hex would start shimmering like ice. Fixing it would need the
discriminator to also test `+0x0E == Dirt`, i.e. distinguish "cooled all the way to Earth" (impossible
today) from "raised Earth over Dirt" by what the marker promises to restore, not just what it currently
holds.

### ⚠⚠ Coupling with `build_raiseterrain_ug_earth.py` — apply/undo order is fixed

**Direction 1 (raise-terrain depends on Grip of Winter):** the underground-earth feature reuses the
`+0x0E`/`+0x0F` scheme, `C_RW`, `C_MELT` and `C_HSTC` wholesale, and its own script **refuses to apply**
if this script's four `TFrozenWaterHS` hooks are not already present — without them, its raised earth
would be permanent (no save/load, no melt, no survive-own-change logic).

**Direction 2 (raise-terrain rewrites a Grip of Winter cave):** it also rewrites the first six bytes of
this script's `C_SHOW` cave at `0x5582A4E0` (`jmp C_SHOWGATE` + `nop`, replacing the `cmp`/`jne` pair),
adding the Earth-marker clause described above. `build_gripofwinter.py` byte-compares the *whole* 20-byte
`C_SHOW` blob before it will touch anything, so **while `build_raiseterrain_ug_earth.py` is installed,
`build_gripofwinter.py` can neither `--apply` nor `--undo`** — both abort before writing, with "cave
`0x5582A4E0` is foreign." Nothing is corrupted by the abort; it is the safe failure, and it is exactly
what the live dry run shows today (`state: MIXED`, `C_SHOW *** FOREIGN ***`). The remaining 14 bytes of
`C_SHOW` are untouched and still the code that executes; both of this feature's own marker states still
end on its own bytes at `0x5582A4E6` (vanilla replay) and `0x5582A4F1` (`ret 4`).

**The required order, stated plainly:**

> **Undo `build_raiseterrain_ug_earth.py` BEFORE `build_gripofwinter.py`.** Once that is done, this
> script's own `--undo` comes straight back.

There is no way to avoid this coupling short of editing `build_raiseterrain_ug_earth.py` itself — every
insertion point available to it (this cave, or the `E9` at the `Show` hook `0x55764BD0`) is a run this
script byte-compares. Owning the change on the raise-terrain side rather than duplicating
`TFrozenWaterHS` a second time was the deliberate choice; this fixed ordering is the cost of it. Full
derivation of the raise-terrain half — why it needed the shimmer at all, the marker-state proof that Grip
of Winter's own appearance is provably unchanged, and the rest of that feature's mechanics — is in
`09-terrain-movement.md`.

### Cave-space neighbour: `0x5582A200` is a deliberate abutment with `build_terror_oncepercombat.py`, not a clash

Both scripts' own cave-placement constants name the literal `0x5582A200`, which could read as a
collision:

```
build_terror_oncepercombat.py:   CAVE_BASE = 0x5582A000   CAVE_END = 0x5582A200
build_gripofwinter.py:           CAVE_BASE = 0x5582A200   CAVE_END = 0x5582A600
```

**It is not a clash.** Both scripts use `CAVE_END` as an exclusive, Python-slice-style upper bound —
`build_terror_oncepercombat.py` reads its own span as `d[off(CAVE_BASE):off(CAVE_END)]`, which in Python
includes byte `0x5582A1FF` and stops *before* `0x5582A200`. `build_gripofwinter.py`'s span then begins
exactly at `0x5582A200` inclusive. The two reservations partition the address range with no byte in
common, and `build_gripofwinter.py`'s own docstring says so explicitly: its span starts "above the
preceding span `0x5582A000..0x5582A200`, reserved by `build_terror_oncepercombat.py`." Terror's own
actual highest occupied byte is `0x5582A16D` — well inside its `[0x5582A000, 0x5582A200)` reservation, so
there is slack on both sides of the boundary as well as at it. **Verdict: deliberate abutment, correctly
handled by both scripts' own verify-before-write (each asserts its own span is "zero-or-ours" before
writing) — no action needed, and nothing to fix.** (The cross-feature cave-ownership table belongs in
`12-re-toolchain.md`; this entry is the source material for its `0x5582A000..0x5582A600` row.)

### Save/load

`TFrozenWaterHS.ReadWrite @0x55764ACB` (`C_RW`, hook 15 B) persists `+0x0C` as property id `0x1E` and
`+0x0D` as `0x1F` (`EDX` = field address, `ECX` = property id, `EAX` = archive, through
`[archive_vmt+0x3C]`). Add `+0x0E` as `0x20` and `+0x0F` as `0x21`.

⭐ **Property ids are a per-class running counter, not a global namespace.** A survey of all 223
`ReadWrite` methods in the module found every class numbering its own fields upward from `0x0A`;
`TFrozenWaterHS`'s ancestors consume `0x0A..0x1D`, so its own two new fields are simply next in its own
sequence, regardless of what any other class uses. Because the property table is **id-indexed, not
positional**, an old save that lacks ids `0x20`/`0x21` loads both bytes as their zero default — a plain
vanilla ice marker — with no format-version bump anywhere.

⚠ `C_RW` re-assembles the displaced run using **EDI**, not EBX, as the archive-vtable scratch register.
Vanilla's own last field does `mov ebx,[eax]`, destroying `Self`, and gets away with it only because
nothing follows; two more fields do here, so the register choice had to change.

### The data half — rename and description

Neither is in `build_gripofwinter.py`; both are rows in shared, multi-feature batch scripts.

**The rename** is a pure data-row change, no binary surgery. Spell names are Delphi resourcestrings, but
every one is routed through a translation dictionary before display: `TFreezeWater.Create` loads
`FreezeWaterRStr`, calls `System.LoadResString`, then `AoWE.TranslateRStr @0x557249FC → Dict/ResStr.mld`.
`Dict/ResStr.mld`/`.txt` row: NATIVE `"Freeze Water"`, `[US]` slot changed from empty to `"Grip of
Winter"`. Applied by `build_resstr_names.py` (already a confirmed mechanism from earlier renames; this is
one more row in its list), whose own `--undo` is surgical, per-row, reverse order, across both `.mld` and
`.txt`, touching no backup — but it reverts **every row the script currently owns**, not only this one,
because rename rows all live in one shared list. ⚠ Do not touch the `.rsrc` resourcestring directly — the
UTF-16 block has no slack, and growing one entry shifts every entry after it.

**The description** — `Release/Spells.pfs` record 20, tag 10 (record id = spell id `0xA` + 10) — is one
row in `build_pfs_typos.py`, changed from:

> *"Freezes a small area of water, rendering it solid enough to walk over."*

to:

> *"Brings winter to the land, and temporarily freezes water to ice."*

(2026-10-03.) The 2026-09-01 text (189 characters) was clipped by the spellbook, which shows three
word-wrapped lines: 146 characters fitted, ending at "…grass to snow. The ice". The row keeps that
text as a second accepted `old`, so `--undo` still restores vanilla.

Same caveat as the rename: `build_pfs_typos.py --undo` is surgical and per-fix but reverts every fix it
owns, in reverse order, not just this row.

**The manual** — `build_ziggurat_manual.py:2720`, one line in the shipyard-income section, already
updated to name "Grip of Winter" instead of "Freeze Water."

### Addresses

| what | address |
|---|---|
| `TFreezeWaterTE.ChangeTerrain` / hook | `0x5579E884` / `0x5579E89B` (6 B) |
| `TFreezeWaterTE.TerrainChanged` / hooks | `0x5579E900` / `0x5579E90E` (11 B), `0x5579E984` (6 B) |
| `TFrozenWaterHS.ReadWrite` / hook | `0x55764ACB` (15 B) |
| `TFrozenWaterHS.MeltIce` / hook | `0x55764AE0` (6 B) |
| `TFrozenWaterHS.TerrainChanged` / hook | `0x55764B6C` / `0x55764B8B` (9 B) |
| `TFrozenWaterHS.Show` / hook | `0x55764BD0` (6 B) |
| `TFreezeWater.ValidTargetMapF` | `0x5579EBA0` (15 B) |
| `TFreezeWater.ValidTargetSelectionMapF` | `0x5579EBF0` (15 B) |
| `TFrozenWaterHS` VMT / classref slot | `0x557147B4` / `0x55714774` |
| `AoWE.AoWHSMap` (map object pointer) | `0x558FA040` — **not** `0x558E9494`, which needs one more dereference |
| orphan freeze-duration byte | `0x5579E96B` (`0x20` live, `0x0B` pristine — leave alone) |
| cave span | `0x5582A200..0x5582A600` (7 caves, **418 B** used — see cave table) |

Cave table (sizes live-verified 2026-09-03 by dry-running the script; they sum to 418 B, not the 394 B a
stale summary line elsewhere once claimed — trust this table and the script's own `--dis` output):

| cave | address | bytes | role |
|---|---|---|---|
| C_COOL | `0x5582A200` | 47 | the cooling ladder |
| C_TCCLS | `0x5582A260` | 73 | does this hex earn a marker? |
| C_TCFIN | `0x5582A2C0` | 47 | stamp `+0x0E`/`+0x0F` once the marker exists |
| C_RW | `0x5582A320` | 50 | persist `+0x0E`/`+0x0F` |
| C_MELT | `0x5582A3A0` | 110 | restore `[self+0x0E]` for a land marker |
| C_HSTC | `0x5582A460` | 71 | survive re-cooling; remember the original terrain |
| C_SHOW | `0x5582A4E0` | 20 | gate the shimmer (first 6 B now owned by `build_raiseterrain_ug_earth.py`) |

### Checks that passed (static, 2026-09-01)

- `--undo` is byte-exact against the pre-apply snapshot (SHA-256 match); `--apply` is idempotent; the
  orphan freeze-duration byte at `0x5579E96B` still reads `0x20`, not the pristine `0x0B`.
- No `.reloc` entry falls inside any displaced run and no branch in CODE targets the middle of one; the
  only absolute dword pointing at a run start is `0x55764BD0` (`Show`'s own VMT slot, `+0xA8`), and calls
  through it land on the `E9` and take the hook.
- `rng_audit.py --owners`: still 23 modded sites, none inside the new cave span — the caves add no draw.
  No profile-path leak anywhere in the game-root binaries or in any file this feature touched; the cave
  span holds no drive-letter path and no printable string at all.
- `build_pfs_typos.py` collateral check: 108 records parse, every one but the edited row byte-identical,
  CRC residue `0x2144DF1C` intact.

### In-game checklist — nothing below is checkable from the files

1. **The ladder.** Cast on desert → steppe; on steppe → grass; on grass → snow. Snow must not cool
   further.
2. **Castable on land** — the cursor highlights land hexes, and the cast goes through. Structures and
   occupied hexes must still refuse it.
3. **The water arm is unchanged** — water still freezes, the ice still looks like ice, and it still melts
   back on its own timer.
4. **The cooling reverts** after a few turns, with no shimmer over cooled land (see C_SHOW above — there
   is no separate ice sprite to check). Water/ice hexes must still shimmer as they always did.
5. **Re-cast on an already-cooled hex**: desert → steppe → grass, then wait. It must revert straight back
   to desert, not stop at steppe.
6. **Load an existing save** made before this patch: old `TFrozenWaterHS` markers must melt normally
   (their `+0x0E` reads 0 by default). A save made *after* the patch must reload with its land markers
   intact — the only exercise of the new property ids `0x20`/`0x21`.
7. **The AI.** Both target gates are what AI spell targeting consults, and they are now much wider —
   watch an AI wizard that has the spell for casts on arbitrary land.
8. **Forested / decorated hexes.** `ChangeTerrainEx`'s validate pass polls `CanChangeTerrain` (virtual
   `+0x98`), which `TILTerrainMO`/`TFixedILTerrainMO` override — a forested grass hex may simply refuse to
   cool. Confirm whether it does, and whether that reads as a bug or as scenery (see "Open items").
9. **The name and description** — the spellbook should read "Grip of Winter" with the new text.

## The `.pfs` / `.ail` record-splicing rules

Both features add records to a `.pfs` container (`Release/Spells.pfs`, `Release/Ability.pfs`), and both
do it the same way — written once here rather than twice above.

**Why a record has to exist at all.** A spell or ability registered by a cave exists in memory the moment
`RegisterAbility`/`RegisterSpell` runs at package init, which is *before* the `.pfs` loader pass. Until a
record exists for it: its `TImageSequenceList` (book icon, cast animation) is empty, and `ImageLib.Get`
has **no bounds check** — asking an empty list for an icon is a real fault risk, not a cosmetic gap; it
has no spellbook/status description at all; and it runs on whatever cost/sphere/tier constants the cave
itself hard-codes. **The moment a record exists, the data file wins** for every tag the record defines —
the cave's own constants become decorative, and the content is tuned like any vanilla spell/ability from
then on (in the `.pfs` directly, or from AoWDevEd).

**Record id = the registered id + 10.** `TSpellControl.ReadWrite @0x55779A6C` streams every spell under
property tag `spell id + 10` (Embrittle 109 → record 119; Freeze Water/Grip of Winter `0xA` → record 20).
The same `+10` offset applies to `Ability.pfs` (Embrittled `0xB2` → record 188). The id itself is **not**
stored in the record body — it is the index key, so re-keying a cloned record to the target id is what
makes it "belong" to the new spell/ability; nothing inside the bytes says so.

**Clone a donor record of the same shape; never hand-author one.** Pick a vanilla record of the same
class, sphere/tactical-type and targeting, and patch only the fields that must differ (description, icon
index, mana, research, sphere, tier for a spell; just the description for a status-only ability). A
donor's nested `TImageSequenceList`/`TSFXLibrary` structures are hundreds of bytes of format that would be
a project to hand-author and cannot be structurally wrong when copied wholesale. Embrittle's spell record
clones Slow's (120); its ability record deliberately clones Slow's *ability* record (142) rather than
Physical Protection's, specifically because Slow's tag 9 (the `TAbilitySelectionType` selection mask) is
`00 00` — cloning a selectable donor would silently make a status-only ability purchasable, because
`Ability.pfs` **overwrites whatever the registration cave set for tag 9**. Check a donor's tag 9 before
trusting its shape for any status-only ability.

**Full-text fields use a different encoding than names.** A description (`Spells.pfs` tag `0x0A`,
`Ability.pfs` tag 5) is **u32-length-prefixed**, not the u8 Pascal-string form the NAME fields use — using
the wrong reader/writer silently misparses or truncates. Every vanilla description also ends `CRLF`;
match it, because it is what keeps the in-game memo control's line handling identical to a stock entry
(the first cut of Embrittle's record 119 omitted it and had to be corrected).

**⭐⚠ A `.pfs` record directory cannot be re-derived — it is append-only in practice.** The index is
`<u8 small_count>[<u32 wide_count>] small(u8 key,u8 off)* wide(u32 key,u32 off)*`, and **every offset is
relative to the END of the directory**, which is what makes an insertion tractable at all: growing the
index by one wide entry moves the payload base by exactly 8, so records before the insertion point keep
their offsets unchanged, records after it gain `len(new body)`, the wide count goes up by one, and the
trailing CRC-32 is recomputed to the fixed residue `0x2144DF1C`. **The directory's own widths and
ordering are not derivable from a rule and must never be regenerated from scratch** — the same lesson
`build_item_hpmv_data.py` recorded for the `.ail` item library. The only safe operation is a *splice*
into the existing directory: read it, find the correct insertion point, patch offsets and counts, write
it back. Never rebuild one from a fresh model of "what the format should look like."

**Records are sorted by id AND by offset, and both orders must agree.** The index-locating probe both
scripts use depends on this invariant to even find the directory in the first place, so a splice that
breaks it makes the file unreadable to the tooling and, presumably, the game. The insertion point is
therefore **the first record with a larger id**, not the donor's own position and not the end of the
file — Embrittle's spell record 119 lands *between* 118 and 120 (mid-file); its ability record 188 lands
at the *end*, because 186 was the prior maximum. One code path serves both, because the splice point is
derived purely from id order.

**`AoWDevEd` rewrites a `.pfs` whole whenever its author saves the set.** None of this machinery is
hard-coded to a file offset — the index, the donor record and the icon field are all re-derived on every
run, so a build script still works after an editor save. But a save *after* applying one of these scripts
bakes the new record in permanently from the editor's point of view; `--undo` afterwards removes what is,
mechanically, the editor's own record rather than the script's — which is fine, because both are keyed on
the same id.

## Regeneration — a Water enchantment that heals fully each turn (spell 79, 2026-10-22)

Owner's design: Water, tier 1, 20 mana, upkeep 2; the enchanted unit heals as a unit with the
Regeneration ability (`0x31`) does — fully, at the start of each turn. World map only: id 79 is a
strategic id, `SpellTypes[79]` = 0, and Regeneration acts at `TAbstractUnit.NewTurn` anyway.

The recipe of this file, twice over (`build_regen_spell.py`):
- **The spell is a `TStoneSkin` instance** (class cell `0x557E5624`) with id 79, name, mana, upkeep
  (`[+0x1C]`), research, sphere and tier poked; registered at `0x557E8E3A`. Stone Skin hard-codes
  its enchantment `0x99` in `ExecuteSpell` (two `mov edx,0x99`, EBX = the spell) and in
  `ValidTargetUnit`, whose spell pointer is lost before its test — so that one is hooked at entry:
  for id 79 it runs `TUnitSpell.ValidTargetUnit`, then refuses a unit holding `0x31` or `0x53`.
- **The enchantment `0x53` is a `TUnitEnchantmentAbility` instance** built by the base constructor
  (class pointer = VMT `0x55722364`, reached by delta) with name and id poked — no subclass, so no
  `Remove` override; registered at `0x557BCC6D`. Id from the verified gaps (`03-abilities-added.md`).
- **The effect** is one hook on `NewTurn`'s Regeneration query (`0x55780DA6`): `0x31` or `0x53`
  takes the full-heal branch.
- Data: `Spells.pfs` record 89 cloned from Stone Skin's 27 (so the cast animation is Stone Skin's)
  and `Ability.pfs` record 93 from Stone Skin's enchantment 163 (tag 9 `00 00`). Book icon: dead
  `SpellIcn.ILB` entry 129 repainted — Water disc from icon 100, heart in a circular arrow, 24×29
  (`build_regen_spell_icon.py`, original bytes embedded for `--undo`).
- No RNG. Unproven: that the AI casts it (Stone Skin's inherited AI, weight 5).

## Dual-sphere spells — the owner's tier rule (planned, 2026-10-22, revised 2026-10-24)

Death/Fire is built (2026-10-25, below); the other 13 pairs are planned. The plan is to bring in most of Inioch's AoWx 1.37.420 pair spells
(`Inioch/Inioch_Share9_Catalogue.md` §2.5, his plumbing in §4.3), under a rule that differs from his:

- **Dual-sphere tiers are 1–3, and they are never researched.** A pair's tier N is granted
  automatically once the player has researched **tier N of both** spheres: Water 2 and Life 2 grant
  Life/Water 2 (owner, 2026-10-24). Researching tier N needs N picks in that sphere (the picks gate
  in `ValidResearchSpell`), so tier N in effect needs N+N picks. (His: picks(A) + picks(B) − 1,
  researched, tiers 1–4.)
- For Spellcasting a dual tier N counts as single tier N+1 (owner, 2026-10-25).
- 14 pairs: Life and Death each with Earth, Air, Fire and Water, plus the six element pairs. Life and
  Death never pair. **Earth+Air and Fire+Water share at most 4 picks** (`TLeader.CanAddSphere
  0x5578B1F8`, read from the live dll 2026-10-22), so under this rule those two pairs stop at tier 2.

**The planning document is the manual's Planned Spells tab** (Single sphere and Dual sphere), written
by the owner in the page (Edit text) and stored in `manual_text.json` as
`PLAN.DUAL.<a>_<b>.t<N>.extra.<n>.0/.1` and `PLAN.<sphere>.t<N>.extra.<n>.0/.1` (name, notes; N =
the tier shown). It is the owner's alone: renames and builds are not carried into it (owner,
2026-10-25). Nothing in the game or the build writes the `PLAN.*` keys (`12-re-toolchain.md` §14.4b).
Spells → Dual sphere shows only what the game has: the pair grid, then each built pair's cards
(icon, caster, stats; the tier row names the two tiers that grant it) and `DUAL_SPELL_NOTES`. A
built spell needs:
- a pair block in `manual_data.json`;
- its record in `Zig notes/spell_names.json`, which supplies the card's icon and caster;
- its note in `DUAL_SPELL_NOTES`. On 2026-10-24 the 35 dual
entries were moved from `DUAL.<a>_<b>.t<N+1>` to these keys as plain text. Copy of the file before
the move: `Ziggurat/backups/manual_text.pre-plannedspells.2026-10-24.json`.

**Review page for Inioch's set:** `Inioch/dual_sphere_review.html`, built by `Inioch/build_dual_review.py`
from `share9/changelog_1.37.420.txt` (54 spells, 14 pairs). There is one card per spell with his level,
costs and effects, the owner's current plan entries beside each pair, and the Ziggurat equivalents
from the catalogue. Each card is marked T1 / T2 / T3 / Maybe / Drop and takes a note; T3 is disabled
for the two opposed pairs. Verdicts stay in the browser's localStorage (`zig-dual-review-v2`). Export
and Import move them as JSON (format 2 wraps them with `"version": 2`). Format 1, a bare object with
tiers `t2`–`t4`, is migrated on load and on Import. Copy gives a plain-text summary to paste into a
session. The page reads `manual_text.json` at build time and never writes it.

**The owner's verdicts:** `Inioch/dual_sphere_review.json` (format 2, 2026-10-22) holds 25 of the
54 spells: 6 at tier 1, 6 at tier 2, 9 at tier 3 and 4 dropped. Several carry rework notes, such as
Ice Age renamed Fimbulwinter and Arms Race made to duplicate machine productions.

### Death/Fire — the first pair: agreed design (owner, 2026-10-25; built the same day)

Built in two stages: the owner rules on the design, then it is implemented. In-game testing is ad hoc.
Death/Fire also carries the groundwork every pair will use.

**Every dual-sphere spell**
- Granted with no research when tier N of both spheres is known. The event log names the spells
  gained. The check runs at every turn start, so saves and scenarios that already hold both tiers
  get them too.
- Unit Spellcasting gate (units only; heroes are ungated): a dual tier-N spell needs Spellcasting N+1.
- Mastery costs: both spheres' modifiers apply and multiply (opposed ×1.5, own ×0.75).
- Caster family follows the class rule (combat Evoker, summon Conjurer, unit Enchanter, global Ritualist).
- Spellbook icon: a new glyph per spell over a glow. A dual spell's glow is a yin-yang of its two
  spheres' colours, the first-named sphere on the left, without the two dots (owner, 2026-10-26:
  they distracted from the glyph). Glyphs,
  glows and effects are previewed to the owner before they are written.
- Combat effects are data: `Spells.pfs` tag `0xC` lists frame sequences from effect libraries with
  anchor offsets, and the spell's combat class decides which slot plays where. Geyser (id 118, class
  30) is sparkles at the caster, then frames 0–4 and 2–4 of `Effects\Storm1.ILB` (320×480) over a
  single target. Call Flames is `Effects\ExplTC.ILB` (27 frames of a rising fire column); High Prayer
  draws `Effects\Magic.ILB` 89–109 on every unit it affects. Green-purple flame is made by recolouring
  the game's own flame frames at native size, in palette B (owner, 2026-10-25): purple flame, green
  edge, for both spells.

**Wizard's Towers** (the only random-spell source)
- Price stays at 3/8 of the spell's research cost (the owner's own hand-edit). A dual tier-N spell
  takes the research figure of a typical single tier N+1 spell (80 / 160 / 240), so 30 / 60 / 90 gold.
- A dual spell is eligible when both its spheres are ticked; it counts as level N+1.
- Offers are drawn only from spells whose own enabled test passes (Bird's View and Conceal Area need
  fog of war), never Warp Party on a map with "Disable Warp Party" (`map+0x193`, build_warpban.py).
  The two offers may share a sphere; they only have to be different spells.
- A Custom tower (one hand-picked spell) offers that one spell and never re-rolls. Every other tower
  offers two spells, each player may buy each once, and re-rolls both every d20 turns. On each
  re-roll the tower's hex changes to a different terrain from Grass, Desert, Snow, Steppe, Wasteland
  and Dirt (any map level; never Water), but not Grass when the new offer holds a Death spell and not
  Wasteland when it holds a Life spell (a dual spell's spheres count). The day-1 roll keeps the map's
  terrain. A Random tower in an older save rolls its second spell, and schedules its first re-roll,
  on the next turn.
- Editor: levels become checkboxes (any mix of 1–4); Life and Death can never both be ticked. Towers
  already on maps keep their spheres as they are (Life and Death together included). A newly placed
  tower starts with a random set of spheres, never Life and Death together.
- The tower dialog keeps one panel and switches between the two offers (a toggle).
- The AI buys the cheaper offer, then the other if it can still afford it.

**Taint the Flame** (tier 1, battle, Evoker): no target, 8 mana. Every Burning (`0x7F`) or Living
Flame (`0x52` / `0xA3`) unit on the field, on both sides, takes a Death attack, 12/12 against RES,
with Death damage's usual Cursed roll. Fire Mastery's granted Living Flame counts (it is the counter
to Fire Mastery, and those units also heal from fire). No other side effect. Small flames recoloured
green-purple play on each unit hit, drawn the way High Prayer draws its aura. The AI casts it only when the enemy has more targets than its own side.
In auto-combat it hits every unit that qualifies. Spellbook text: "Strikes every unit that's burning
or has Living Flame ability with Death damage."

**Pillar of Banefire** (tier 2, battle, Evoker): range 8, AoE radius 2 (19 hexes), everyone inside.
Death + Fire + Wall (the Wall bit as in Triple Fireball), 10/15 × 2 against RES, the normal fire
chance to set Burning. 16 mana. Animation: Geyser's burst in green-purple, reordered so it descends
rather than rises, and without Geyser's knock-back: no unit is moved. One burst; each unit in the
area is struck twice. No burning ground. 4 targets in auto-combat. The AI casts it as it casts
Fireball. Spellbook text:
"The flame of the underworld burns the essence and can even destroy stone walls."

**Enmity of Nine Hells** (named Demon Curse until 2026-10-25; tier 3, world map, Enchanter): 40 mana, upkeep 10, range 12. Curses a unit owned
by another player (never an independent: the engine will not let a hunt chase one), one curse per
unit; heroes and leaders may be targets. Dispel Magic makes its normal roll against it. Demons may
appear on water (they fly). A party on the Hunt behaviour can never be recruited by anyone. Rolled at the start of the caster's turn while the
upkeep is paid: the curse's first turn has no chance; then 1/32, 1/16, 1/8, 1/4, and 1/2 every turn
after, with no reset after a wave. Each time
it succeeds, d(X/2) Demons (rounded down, capped at d6, X = the turns the curse has been active)
appear on a random valid hex 8–16 hexes from the victim on its map level (none that turn if there
is no such hex), and the curse goes on rolling. They are
independent and stay independent, with a hunt behaviour that chases cursed units (any curse, so one
pack may be drawn off to another victim) and turns to Raid once none is left; it attacks whatever
the odds. Any Demon unit on the map, players' own included, strikes any unit under Enmity of Nine Hells at +5/+5
ATK/DAM, attacking or defending. Demons get no ability for this: the party AI and the unit-type
check against the curse do it. Dispel Magic or
the death of the unit that cast it lifts the curse. No overhead marker: it shows in the unit's
ability list. The event log reports the cast to both players and says nothing when demons appear.
The AI casts it at the enemy's strongest unit. Spellbook text (proposed): "Curses an enemy unit.
Sooner or later demons manifest to hunt it down, striking it with +5 attack and damage."

### Death/Fire — as built (2026-10-25)

Every script's docstring carries its sites, caves, RNG sites and `--undo`. Apply order is the list
order; undo in reverse.

| Script | Binary | What |
|---|---|---|
| `build_dual_sphere.py` | AoWEPACK `0x558B6000` | side table + `dual_find` (pinned), turn-start grant, unit tier gate, two-sphere Mastery |
| `build_dual_sphere_exe.py` | AoWz.exe `0x0062BC00` | "Death/Fire" sphere name in the book, research and tower windows; book tier |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icons 156–158 (both twins); revised by the owner: Taint as the skull of AoW2's Death Storm icon with two swaying flames on each side (2026-10-26), Pillar without its top bar, Enmity as the face of AoW2's Damnation icon at 90 % (2026-10-26; halo and drops removed) |
| `build_banefire_fx.py` | `Images/Effects/BANEFIRE.ILB` | palette-B flame, sparkle, spray and burst frames |
| `build_deathfire_pfs.py` | `Spells.pfs` 90, 91 | Taint (High Prayer's record), Pillar (Geyser's) |
| `build_deathfire_combat.py` | AoWEPACK `0x558B6800` | spells 80 and 81 registered from TDeathRay / TFireBall instances |
| `build_deathfire_tc.py` | AoWTCPCK `0x0043E800` | class aliases, AI, targeting, Pillar's landing and descending spray |
| `build_demon_curse.py` | AoWEPACK `0x558B7000` | spell 82 + enchantment `0x5B`, roll, spawn, hunt AI, +5/+5, AI casting |
| `build_demon_curse_pfs.py` | `Spells.pfs` 92, `Ability.pfs` 101 | Dark Gift's records, re-numbered |
| `build_wizardtower_dual.py` | AoWEPACK `0x558B8000` | two offers, eligibility, re-roll + terrain, slot-aware buy, AI |
| `build_wizardtower_dual_exe.py` | AoWz.exe `0x0062D400` + the tower form | Next button (length-neutral DFM rewrite), slot-aware display and Buy |
| `build_wizardtower_dual_editor.py` | AoWDevEd.exe `0x0050F000` (then `build_zigeditor.py`) | level checkboxes, Life/Death exclusive |

`build_spellcast_herotier.py`, `build_mastery_cost.py` and `build_scroll_spellbook.py` accept the
dual-sphere retargets as their applied state and refuse `--undo` while they are in place.

Choices made in the build, not in the design:
- Enmity of Nine Hells' enchantment level is 4 (a dual tier 3 counts as a single tier 4), which sets Dispel's
  roll. Its caster's unit id lives in the enchantment's alignment padding (24 bits); its turn count in
  the ability data's spare byte.
- A demon pack is marked in its AI group's padding byte (`+0x4F` = `0xDC`, saved). The mark moves to
  the Raid group; recruitment is refused for any Hunt party and any marked party.
- Tower text and price come from the swapped-in offer; the token carries the bought spell, so a buy
  that crosses a re-roll is refused instead of buying the wrong spell.

Unproven: whether the hunt finder's 200-point search reaches a victim 16 hexes away over hard
terrain; a Raid pack split by the AI loses its mark (and its recruitment block). The Next button has
no alignment props (DFM budget), so it relies on `awNone` keeping its stored position.

Fixed 2026-10-28: an auto-resolved battle crashed ("Exception occured during TArmyCombatMoveTE",
`AoWEPACK.dpl at 001B68D9`, read of `0x26`; reported by a player on an AI turn under hidden
movement) whenever a hero's player knew Taint the Flame and had the mana for it. Its `+0x90`
override took the caster's side from the command list's `+8` as if it were the TFastCombat
(`build_deathfire_combat.py`, one byte at `0x558B6941`). Releases 2026.10.25 and 2026.10.27 carry the
bug.

Changed after the build (owner, 2026-10-25): Regeneration (79) and Enmity of Nine Hells (82) are
castable in battle, as every vanilla unit enchantment but Cosmagic Scrying is; Dwarven Satchels (84)
was built that way. Built the same day:
- `build_battlecast_unitspells.py` sets `SpellTypes[79]`, `[82]` and `[84]` to 7 (`AoWTCPCK.dpl`
  data). The spells already carry the combat flag (`[spell+0xC] = 3` from their class constructors).
- A battle cast ends in the spell's own `ExecuteSpell` (`TUnitSpell.ExecuteCA` → VMT `+0xB4`) on the
  units behind the combat units, and its first step is `ValidTargetUnit` (VMT `+0x9C`). So every
  hook of both spells works in battle, and a refused target fizzles.
- Battle targeting takes its side from GetCombatInfo byte 7 (1 friendly, 2 enemy;
  `MouseDownEvent` `0x0041F5C3`). Every unit spell reports 1, so `build_demon_curse.py`'s
  `cave_info` makes Enmity report 2. Enmity cast in battle curses an enemy unit; its demons still
  appear on the world map.
- `build_spell_unit_target.py`'s `UNIT_ONLY` lists all three, so an empty hex refuses the cast. It
  now tests a 128-bit set; its two other caves are pinned so the list can grow in place.
- The tactical AI casts none of them in battle. Its spell loop (`0x00418740`) skips a spell whose
  combat info byte 7 lacks bit 2. Enmity passes that test and is then valued at 0 by
  `tcGetDamageValueEx`.

### Earth/Fire — agreed design (owner, 2026-10-25; partly built, see "as built so far")

The general rules above apply (grant, Spellcasting N+1, both Masteries, class caster families,
tower research figures 80 / 160 / 240, yin-yang glow icons previewed before writing). None of the
three is from AoWx. Inioch's Pyroclasm (AoWx Fire tier 4; `Inioch/share9/patch scripts/
patch_pyroclasm_v1.py`, `_pyroclasm*_integration.txt`, `patch_terrain_armyhooks_v1.py`) is prior
art for the volcano. It swaps medium and large mountains for the volcano art. It found that
`TArmyHS.CanChangeTerrain` vetoes a terrain change under an army, and that once that veto is lifted,
`ValidateTerrainEx 0x5578CC9C` kills units that cannot stand on the new terrain.

**Dwarven Satchels** (tier 1, unit enchantment, Enchanter): 16 mana, no upkeep, castable on one of
your units on the world map or in battle; one per unit, kept across battles until thrown.
- In battle the unit throws it by clicking Dwarven Satchels in its ability list, then a hex within
  4. A unit that already shoots keeps its own ranged attack.
- The throw costs what a ranged attack costs, and using it ends the enchantment.
- Throw Explosive Flask flies a steep lob like Hurl Boulders. Units in its path occasionally catch
  it, and then it bursts on them instead: the game's own interception at a lob's arc.
- Blast radius 1 (7 hexes). Every unit there is struck once, own units included: 10 ATK against
  DEF, 15 fire damage, the normal fire chance to set Burning. Walls are unharmed.
- The flask is unwieldy, after Myth's satchel charges (owner, after the build): it lands on the
  aimed hex 4 times in 10 and on each of its six neighbours once in 10. Aiming shows those chances
  as numbers on the seven hexes (40, 10, …). Both ability texts say "unwieldy" and give the
  damage; the spell text does not.
- AI: it casts it on its strongest units that have no ranged attack and no satchel. AI units and
  auto-combat throw where the blast hits the most enemies.
- Spellbook: "Gives a unit one expendable alchemical flask which can be thrown in battle."

**Surtr's Chasm** (tier 2, world map, Ritualist): 35 mana, one-off, permanent, range 12.
- It opens a jagged line of up to 6 Chasm hexes from the cast hex. Each new hex grows from the
  last one, in a semi-random direction, and touches no other hex of this cast. The line stops early
  when no valid next hex is left.
- A valid hex is land with no unit or structure; forests, hills and roads are swallowed and lava
  counts. Water, mountains and Sky are skipped.
- Beneath each new chasm hex, Rock becomes Earth; other terrain stays.
- Castable on the Surface and the three cave levels, never the Firmament. Faery, once it exists, is
  to be allowed too. On the lowest enabled level the chasm is a bottomless pit: nothing climbs or
  flies down through it.
- The AI never casts it.
- Spellbook: "Tears a jagged chasm into the ground. Climbers can scale its edges between map levels."
- Added after the first cast (owner): water next to the new chasm drains to Dirt; a ship there is
  either destroyed or stranded (the build strands it); the cast sounds as Tremors does, louder; the
  hexes open one at a time, about 0.4 s apart.

**Mountaineering climbs chasm edges** (any Chasm hex, map-placed ones included). In the path search
these are links, as caves, teleporters and one-hex bridges are (`TMoveControl.ProcessHexagon
0x557456F8` → `TMapField.MoveExclusive` → `ExecuteExternalMove 0x55745928`). In this list C is a
chasm hex, C′ the hex beneath it, and A a land hex beside C.
- Down from A to C′, and up from C′ to A.
- Up the wall from X′ to X, where X is land beside a chasm and X′ the hex beneath X, and back down.
- The landing hex is priced with the party's own movement table, so it needs Tunneling for Earth,
  Swimming for water, and so on. It must be empty or hold the party's own side, as at a cave.
- A climb needs at least 4 movement points and uses all of them; a longer path continues next turn.
- Every moving unit needs Mountaineering, and the landing hex must suit them all. A transport carries
  its passengers, as with flying.
- The party is never shown on the chasm: it vanishes at the edge and reappears.
- The AI climbs, since it routes with the same search.
- The move is executed as cave travel; `build_fly_levels.py` already widened `ValidPath` for
  two-node vertical paths. This replaces the click-Mountaineering idea.

**Awaken Volcano** (tier 3, world map ritual, Ritualist): 40 mana, upkeep 5 from the cast until the
spreading ends, range 12 from the caster. The AI never casts it.
- Targets a 4-hex mountain, which becomes the small volcano (`Mountain\WL_VOLCS.ILB`, 140×96, 10
  frames), or a 9-hex one, which becomes the large (`WL_VOLCL.ILB`, 186×134). The game has only
  1-, 4- and 9-hex mountains; 1-hex ones are refused. The mountain's hexes turn to Wasteland.
- Lava starts after d3 turns (rolled at the cast). Then for 10 turns it spills d2 lava hexes a
  turn. Each new hex touches the volcano or this volcano's earlier lava, with a preference, less
  strict than the chasm's, for linear flow lines over a rounded pool.
- Lava forms on any land without a city or structure. Forests, hills and roads burn away and units
  are no barrier; water, ice, mountains and Sky are skipped. Snow next to new lava becomes Steppe,
  and Ice next to it becomes Water, permanently.
- Units on a hex that turns to lava:
  - Units that can stand on lava (Fire Immune, flying, floating) stay, unharmed.
  - Each other unit takes d20 fire damage, rolled per unit, through the map damage routine with
    the roll forced (`build_flight_fall.py`'s `FORCE`, 2026-10-29), so Fire Immunity, Protection
    (rounded up), Weakness, Living Flame and Mistform apply as to any fire hit; until then the cave
    halved rounding down and applied Weakness itself. It is moved to an adjacent hex it can enter. That hex is
    never lava, and must be empty or hold its own side's party with room; a friendly ship there
    takes it aboard. A party may split across several hexes.
  - A unit with no such hex dies.
- The volcano and the spell's lava carry Grip of Winter's glitter while the ritual runs. When the
  spreading ends, or the upkeep goes unpaid, the ritual ends: the lava and the volcano stay for
  good, the glitter goes and the upkeep stops.
- Spellbook: "Wakes a mountain into a volcano that spills lava over the land around it."

Left to the build, unless the owner rules otherwise:
- The order in which a shunted unit's hexes are tried (random).
- Whether "touches no other hex" in Surtr's Chasm also counts chasm hexes that were already there
  (read as: only this cast's).
- The flask's projectile and blast art, previewed first.

### Earth/Fire — as built so far (2026-10-25)

All four are built.

| script | where | what |
|---|---|---|
| `build_chasm_climb.py` | AoWEPACK `0x558B9000` | climb links at the path search's three link points, the per-unit walk's climb rule, the drain after a climb |
| `build_surtrs_chasm.py` | AoWEPACK `0x558B9800` | spell 83 (a TLevelTerrain instance): registration, validity, one-hex cursor, the chasm line |
| `build_surtrs_chasm_pfs.py` | `Spells.pfs` 93 | Level Terrain's record 28, re-numbered; book icon 159 |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icon 159: Tremors' glyph mirrored (owner, 2026-10-25; it replaced draft D); icon 160: a satchel with a flask cut out of it (draft B, the owner's pick, redrawn at 65 % of its first size: the first was oversized); icon 161: a volcano cone with a glowing crater, one lava stream and embers (draft A, the owner's pick) |
| `build_satchels.py` | AoWEPACK `0x558BA800` | spell 84 (a TEnchantWeapon instance), the enchantment `0x4E` and the attack `0x4F` (run-time VMT copies), the AI's choice of target unit, the auto-combat throw |
| `build_satchels_tc.py` | AoWTCPCK `0x0043F000` | manual combat: the attack's category, the lob, the scatter, the 7-hex burst, the satchel used up, the AI's aim, the landing chances drawn while aiming |
| `build_satchels_pfs.py` | `Spells.pfs` 94, `Ability.pfs` 88/89 | Enchant Weapon's records 26 and 164 and Hurl Flaming Skull's 201, re-numbered, with the owner's texts; book icon 160; Hurl Boulder's sprite slots; the impact sound |
| `build_flask_sound.py` | `Sfx\Zatk\FlaskBurst.wav` | the impact sound, mixed from `Ice.WAV` and `Explod1.wav` |
| `build_battlecast_unitspells.py` | AoWTCPCK data | `SpellTypes[84] = 7` |
| `build_awaken_volcano.py` | AoWEPACK `0x558BB000` | spell 85 (a TLevelTerrain instance): target test, the mountain-to-volcano swap, the ritual record (a re-typed `TSpellWardEnchantment`) with its turn hook, save block and end hook, the lava, the units' shunts, the glitter; Surtr's Chasm's TLevelTerrain caves dispatch id 85 to it |
| `build_awaken_volcano_pfs.py` | `Spells.pfs` 95 | Level Terrain's record 28, re-numbered; Surtr's Chasm's sound; book icon 161 |
| `build_dual_sphere.py` | its `TABLE` | rows `(83, EARTH, FIRE)`, `(84, EARTH, FIRE)`, `(85, EARTH, FIRE)` |

Choices made in the build, not in the design:
- "Touches no other hex of this cast" counts only this cast's hexes, so a new line may meet a chasm
  that was already there. Each new hex is picked uniformly among the valid neighbours of the last
  one that touch no earlier hex of the line. That rule alone keeps the line from curling back.
- The cast hex must itself be valid; the cursor marks only that hex.
- Climbing is a property of any Chasm hex, map-placed ones included. A climb is priced in the
  path search as the rest of the current turn (or the rest plus a whole turn when fewer than 4
  points would be left), so the path's turn markers after a climb fall where the party really
  stops. The search only considers climbing for a party whose cost table lets it onto a mountain
  (Mountaineering or Flying), then checks every mover for Mountaineering.
- The drain after a climb lives in the move transaction (`TMoveArmyTE.ExecuteMove`), not in
  `TAbstractUnit.MovedTo`: Warp Party moves armies through `MovedTo` too, and must keep its
  movement.
- The cast plays Level Terrain's effect (its `Spells.pfs` slots are copied unchanged) with Tremors'
  sound made louder (`Sfx\Zsp\SurtrQk.wav`, a soft-limited copy of `Tremors.wav`, +4.7 dB RMS;
  `build_chasm_sound.py`). Level Terrain's own sound list is empty.
- The opening is paced by the event itself: the line is planned in `Process` and stored in the
  event (its instance grown from 0x24 to 0x40 bytes), and the event's `Execute` keeps returning
  "running" while it opens one hex every 12 map frames (0.4 s at the game's 30), as an army's move
  event does. The token queue waits for it, so every peer ends in the same state.
- The drain takes Water and underground Water alike. A water hex holding an army, a structure or a
  bridge keeps its water, so a ship is stranded in a one-hex pool: `TArmyHS.CanChangeTerrain` vetoes
  a change its army cannot stand on, and the engine has no ship-on-land state to fall back to.
- The owner's first cast looked as if the chasm spread over the sea. The line refuses water by the
  hex's terrain byte at every step (`cave_vt`, then Level Terrain's own test), so what showed was
  most likely shore art next to new chasm hexes; the drain removes those shores.
- The satchel is two abilities: the enchantment E (`0x4E`, "Dwarven Satchels") and the attack F
  (`0x4F`, "Throw Explosive Flask"). E's Expand and Remove set and clear F, so F lasts exactly as
  long as E, through saves, dispel and the throw.
- Auto-combat has no hexes: the throw strikes its target and up to two other units of the target's
  side, picked at random (P2 combat raw).
- In manual combat every standing unit on the 7 hexes is struck the way vanilla strikes a missile's
  target, with its damage icons, flinch and blood. The ground is not set alight. The satchel is
  removed when the flask lands, if the thrower still stands. The first build sent Flame Throwing's
  message `0x31012` to the seven fields instead: in the owner's first throw only the target was
  hurt, and its strikes showed nothing but a flinch.
- The AI aims as vanilla's Triple Fireball AI does: at the target unit or one of its six neighbours,
  whichever blast is worth more, own units counting against.
- With the flask armed, a click on one of your own units selects that unit (the attack's combat
  info says "enemy"); any other hex in range, empty or not, is a target.
- Extra Shots never gives the flask a second throw (`build_extrashots.py` excludes `0x4F`).
- The scatter is one synced draw (P1) in `NextStrike`, before the path is built, so a unit in the
  path can still catch the flask on its way to a scattered hex. A neighbour off the level, in
  column 0, on Border terrain or under the thrower keeps the flask on the aimed hex, and the
  numbers count that tenth on the aimed hex. Auto-combat does not scatter: a flask that lands beside
  its target still bursts on it.
- The numbers appear with the ranged path, after the first click on a hex, on the same round sign
  and in the same font as vanilla's interception chances; on a hex that also shows an interception
  sign, ours sits 12 px further right and down.
- The flask is a category-2 missile (`AbilTypes` 2, Hurl Boulder's). The category picks the flight
  sprite: category 1 (arrows, bolts, javelins) draws image slot [fx+0x20], the flight direction,
  and category 2 draws slot 0. As category 1 the flask, which has only slot 0, flew unseen (the
  owner's first test).
- The flask flies Hurl Boulder's tumbling boulder (the owner: Fire Cannon's ball read as a
  cannonball) and lands with `Sfx\Zatk\FlaskBurst.wav`: Ice Shards' shatter (`Ice.WAV`) over a
  quieter `Explod1.wav`, mixed by `build_flask_sound.py`. The throw keeps Hurl Boulder's catapult
  sound.

- The volcano is the mountain object itself with the volcano resource swapped in, as
  `TTerrainMO.ChangeTerrain` swaps resources; the object saves its resource id, so it reloads as
  a volcano. The volcano resource is the one whose covered slots match the mountain's.
- The ritual is a global-magic record, so the Magic window lists it, upkeep is charged by the
  engine's own sum, unpaid upkeep, Disjunction and the Magic window's remove end it, and saves keep
  it. It is a `TSpellWardEnchantment` re-typed to `0x56`: no vanilla code indexes anything by a
  record's type, and type 8 or above is never refused as "already active". Its state (delay, spill
  turns, every hex it owns) lives in the instance, grown from 0x24 to 0xA8 bytes, and is saved as
  one block.
- It spills on the turn the d3 delay reaches 0 and on the 9 turns after, so upkeep is paid for
  delay + 9 turns.
- "Linear flows": a land hex beside the ritual's hexes weighs 3 where it continues a lava hex in
  the direction that hex was reached, otherwise 1. The volcano's own hexes count as sources with no
  direction.
- A hex the map refuses to turn to lava (an army there still unable to stand on it) is flagged and
  spreads nothing.
- Shunted units: a joining unit needs a friendly party that is not moving, with room, on a hex the
  unit can stand on or with a transporter; a new party needs an empty hex with no owner and no
  structure that the unit can stand on. The six neighbours are tried in a synced shuffled order.
  Units leave by the engine's unit-selection transfer, as the vanilla split does, not by a move.
- Fire Weakness is tested by ability `0xB3` (`build_weakness.py`); Fire Protection and Fire
  Weakness together cancel, as in that script.
- The glitter is Freeze Water's shimmer marker (`TFrozenWaterHS`) on every hex of the ritual, owned
  by no player (`0xFF`), so it never melts; Grip of Winter's Show gate is bypassed for those
  markers only. Ending the ritual removes them.
- The cast plays Level Terrain's effect with Surtr's Chasm's louder Tremors sound.

Unproven:
- In game: neither climbing, the chasm line, a flask throw nor a volcano has run yet.
- Awaken Volcano: the swap's redraw, where the shimmer draws against the volcano sprite, shunts
  onto hexes `PlaceEx` refuses, and new parties of AI players (no AI group).
- How the AI weighs a throw against walking up to melee; its scoring ignores the scatter.
- Where the numbers sit on screen.
- What the player's view does when a pathed climb takes the selected army to another level.
- Road graphics next to a freed road hex.

### Death/Water — agreed design (owner, 2026-10-25; Lethe and Stygia built the same day)

From the owner's plan (Planned Spells: Curse of Lethe t1, Blessing of Stygia t2, Plague t3 "as
AoWx"); the rulings below are for the first two. The general rules above apply. Proposed figures
the owner did not change are marked (proposed).

**Curse of Lethe** (tier 1, battle, Evoker): range 8, radius 1 (7 hexes), 12 mana (proposed).
- Every unit in the area makes a Resistance check against sleep, at power 10 as against any
  elemental status. Elves and Dark Elves get +4 on it. Own units in the area are affected too.
- Never affected: Magic Immunity, Undead, war machines.
- Asleep: a new status, a copy of Stunned (as Petrified is): the unit cannot act or retaliate and
  has Stunned's −4 Defence. It lasts 4 of the unit's own combat turns (duration mode 2), and any
  damage that lands wakes it (the damage funnel `build_panic_cleardamage.py` already hooks).
- Auto-combat: the target and up to two other units (proposed). The AI casts it when at least two
  more enemies than own units would be caught (proposed). Sleepers show Stunned's overhead
  animation (proposed).

**Blessing of Stygia** (tier 2, world-map global enchantment, Ritualist): 30 mana, upkeep 5
(proposed).
- At the start of each turn of the caster or an ally, each of that player's units that stands on
  Water or underground Water, or beside it, on the world map gains the status Blessing of Stygia:
  Physical Protection until that unit's next turn starts (duration mode 1, one day). Ice does not
  count. Water on battle maps plays no part (owner, 2026-10-25). A unit that already has Physical
  Protection gains nothing from it.
- While it lasts, every water hex on the map has a purple-black tint, seen by every player.
- It ends when its upkeep goes unpaid or Disjunction takes it; statuses already given run out.
- The tint: water only slightly darker and purpler than normal, surface and cave water alike (owner,
  2026-10-25, after rejecting three stronger and three medium drafts).

### Death/Water — as built (2026-10-25)

| script | where | what |
|---|---|---|
| `build_lethe.py` | AoWEPACK `0x558BD000` | spell 86 (a TEntangle instance: its single-target status CA and Resistance roll) with a VMT copy for the sleep filter, roll, AI values and auto-combat gate; the status Asleep `0x50` (a TStunnedAbility instance, VMT copy: 5 ticks); its grant in `TEntangleSpellCA.Execute`, being locked, the unit-panel icon, waking on damage, and its removal by Remedy and Dispel Magic |
| `build_lethe_tc.py` | AoWTCPCK `0x0043D000` | the battle map: Geyser's class (`SpellTypes[86]=0x1E`), the class aliases, the 7-hex preview, the AI's area search and gate, the landing that applies the spell's CA to each unit on the 7 hexes |
| `build_lethe_pfs.py` | `Spells.pfs` 96, `Ability.pfs` 90 | Geyser's record 128 re-numbered (its burst and sounds), icon 162; Asleep from Stunned's record 102 (its dazed-stars frames) |
| `build_ankh_battlefield.py` | AoWTCPCK `0x0043C400` | the battlefield status-icon list gains `0x50` (16 entries) |
| `build_blessing_stygia.py` | AoWEPACK `0x558BD800` | spell 87 (a TSpellWard instance) whose record is a re-typed `TSpellWardEnchantment` (type `0x57`), one per caster; the day status `0x51`; the turn grant in `TAbstractUnit.NewTurnDone`; Physical Protection through `GetAbProtectionTypesAll` |
| `build_blessing_stygia_pfs.py` | `Spells.pfs` 97, `Ability.pfs` 91 | Astral Ward's record 75 re-numbered, icon 163; the status from Nature's Blessing's record 109 |
| `build_stygia_tint.py` | `Waterhex.ILB` + `_Waterhex.ILB` ids 224–307, AoWEPACK `0x558BE000` | the tinted twins and the entry exchange around the world map's two scene draws |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icons 162 (a crescent moon over waves, mirrored 2026-10-26 so the moon sits off the glow's yin-yang border) and 163 (a goblet over waves), the owner's picks; the Water disc is icon 115's |
| `build_dual_sphere.py` | its `TABLE` | rows `(86, DEATH, WATER)`, `(87, DEATH, WATER)` |

Choices made in the build, not in the design:
- Curse of Lethe rides Geyser's battle class as Pillar of Banefire does: Geyser's burst and spray at
  the target hex, no target unit, so no knock-back. Its landing applies the spell's own action to
  each unit on the 7 hexes, both sides; walls, terrain and structures are never touched.
- Each sleeper counts its 4 turns on its own side's turns, whichever side cast it.
- The roll is HitRole(10 − (RES + 4 for Elves and Dark Elves)) = 100 − 5·RES' %, clamped 10–90.
  Undead means Turn Undead's test: the Undead race or the Animated ability.
- The AI rule "at least two more enemies than own units" counts units that can sleep on the 7 hexes
  around its chosen centre. Auto-combat casts it only when at least two enemies can sleep; its two
  extra targets come from the target's side, and an immune pick fizzles.
- The blow that wakes a sleeper gets no retaliation that round: who can retaliate is fixed when the
  round starts.
- Remedy and Dispel Magic remove Asleep, Dispel Magic without a roll, as for Petrified (owner,
  2026-10-25, after the build).
- Blessing of Stygia: one per caster ("is already active" otherwise). The AI never casts it.
- The status lasts until the unit's own next turn start and is renewed then while the unit is by
  water. It is not an enchantment, so Dispel Magic and Remedy do not remove it. A unit with
  Physical Protection already gets no status.
- The tint keeps no state of its own: every frame reads whether a Blessing of Stygia record is
  active, so loads and endings need nothing. The minimap stays blue; the animated glints and the
  ice and cave-water edges against Sky or Chasm are not tinted.

- Fixed 2026-10-26: Curse of Lethe's auto-combat value override (VMT +0x98) read its out record from
  the wall-situation argument, a write to address 0 or 1 once auto-combat weighed it against a unit that
  cannot sleep; it now reads [esp+4] (Taint the Flame and Mist had the same slip, fixed with it).

Unproven:
- In game: neither spell has been cast yet; the tint has not been seen.
- Whether the half-size image files ever draw the map.

### Air/Water — agreed design (owner, 2026-10-26; built the same day)

From the owner's plan (Planned Spells: Mistform t1, Mist t2, Static Shield t3). The general rules
above apply. Figures marked (proposed) are mine.

**Mistform** (tier 1, unit enchantment, Enchanter): 12 mana, upkeep 1, research 80. Cast on your
unit on the world map or in battle.
- The unit has Floating while enchanted.
- The next damage that lands on it, in battle or on the world map (storms, map fire, holy ground and
  the like), does nothing to it and ends Mistform instead. A miss, or a hit absorbed to nothing,
  does not use it up. The absorbed blow carries no effects either (poison, burning, freezing,
  stuns).
- A unit that loses Mistform that way over water, chasm or sky falls as when Wind Walking is
  dispelled there.

**Mist** (tier 2, battle, Evoker): 15 mana, research 160. For the rest of the battle (proposed),
every enemy unit without True Seeing sees 3 hexes less in combat, at least 1. It is line of sight
only: the battle AI sees everything and auto-resolve has no sight, so against the AI it changes
nothing (owner's ruling).

**Static Shield** (tier 3, unit enchantment, Enchanter): 45 mana, upkeep 5, research 240. Cast on
your unit on the world map or in battle.
- The unit has Lightning Immunity while enchanted.
- Each melee strike that lands on it, retaliation included, lets it stun the striker: the striker
  resists at power 10, as against a lightning stun (Lightning Protection +4, Lightning Weakness −4,
  Lightning Immunity never stunned). Ranged attacks and spells do not trigger it.
- The stun lasts as a lightning stun does: a striker stunned in its own turn loses its remaining
  strikes and its retaliations until its next turn; one stunned in the holder's turn (a retaliation)
  also loses its next turn.

### Air/Water — as built (2026-10-26)

| script | where | what |
|---|---|---|
| `build_airwater_ench.py` | AoWEPACK `0x558BE400`, BSS `0x558FAD24`–`0x558FAD3F` | spells 88 and 90 (TWindWalking instances) and their enchantments `0x54` (a TWindWalkingEnchantment instance) and `0x55` (a TUnitEnchantmentAbility instance); Floating and Lightning Immunity through the move and immunity aggregators and `GetAbilityEnabled`; Mistform's absorb in combat damage, self-destruct and world-map damage; the absorbed blow's effects dropped; the terrain check deferred to the army's next validation |
| `build_staticshield.py` | AoWEPACK `0x558BEC00` | the stun: `TStrikeCA`'s Generate, Execute and ReadWrite VMT slots |
| `build_mist.py` | AoWEPACK `0x558BF400` | spell 89 (a TDeathRay instance, Taint the Flame's recipe) with a VMT copy worth nothing to either AI and never queued by auto-resolve |
| `build_mist_tc.py` | AoWTCPCK `0x0043CC40` (entry pinned) | High Prayer's instant class (`SpellTypes[89]=0x25`); the cast marks the enemy side in `TTacticalCombat+0x4D`; the sparkle loop keeps misted units, the aura loop none; the sight cut |
| `build_tactical_los.py` | its `csight` routine | calls Mist's entry while it starts with E9 |
| `build_airwater_pfs.py` | `Spells.pfs` 98–100, `Ability.pfs` 94–95 | Wind Walking's record 53 (Mistform, Static Shield) and High Prayer's record 112 (Mist) re-numbered, icons 164–166; the enchantments from Wind Walking's enchantment record 175 |
| `build_battlecast_unitspells.py`, `build_spell_unit_target.py` | AoWTCPCK | 88 and 90 castable in battle on a unit |
| `build_panic_cleardamage.py` | its damage cave | no recovery roll on a blow Mistform absorbs |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icons 164 (the Holy Champion knight with five curls), 165 (five mist lines), 166 (AoW2's Static Shield flipped), the owner's picks; the Air disc is icon 0's |
| `build_dual_sphere.py` | its `TABLE` | rows `(88, AIR, WATER)`, `(89, AIR, WATER)`, `(90, AIR, WATER)` |

Choices made in the build, not in the design:
- Enchantment levels: Mistform 2, Static Shield 4. Every dual enchantment's level is its equivalent
  single tier, dual tier + 1, as Dwarven Satchels (2) and Enmity of Nine Hells (4) (owner,
  2026-10-26). Dispel's chance is strength + 50 − 10 × level, clamped 10–90 %.
- The world-map AI casts Static Shield (owner, 2026-10-26): AI weight 225, Bless's and Dark Gift's,
  on the highest-level unit of the caster's army that is no war machine. It never casts Mistform or
  Mist, and the battle AI casts no friendly unit spell.
- A unit already holding the enchantment cannot be given it again. Wind Walking and Mistform can be
  cast on each other's units (owner, 2026-10-26), so a unit can float on after Mistform absorbs a
  hit: Wind Walking's own test asks for native Floating only.
- Static Shield: a war machine that strikes the holder catches fire instead of being stunned, as
  with any lightning stun (`build_lightning_ignites.py`). A killing blow on the holder still
  stuns. A striker already stunned is not rolled again. A Round Attack sweep goes on after the
  stun, as with a lightning stun. A blow Mistform absorbs still counts as landed.
- Mist: a second cast in the same battle changes nothing but costs its mana. Its sparkles on the
  misted units are Particle.ILB's pale glows.
- The fall after an absorb over water happens at the army's next validation: right after the
  damage on the world map; after a battle, at the first army move or map damage anywhere.

Unproven:
- In game: none of the three has been cast yet.
- Mist's instant effect with no auras to land; the misted view in a multiplayer battle.
- The fall's timing after a battle fought over water.

### Entangle to Life/Earth, Weight of the World — agreed design (owner, 2026-10-26; built the same day)

**Entangle** leaves Earth (tier 2) for Life/Earth dual tier 1, its behaviour and numbers unchanged
(the owner's plan: "as present"). As a dual spell it is granted, never researched; research 80 only
prices Wizard's Tower offers.

**Weight of the World** (Earth tier 2, battle; AoWx's Gravity Well, an Earth/Air tier-3 spell, made a
pure Earth spell and renamed by the owner): 10 mana, research 80. It takes Entangle's place in Earth.
- Cast at a hex within 8. Every unit within 6 hexes of it (AoE 6, up to 127 hexes), friend and foe
  alike, takes one strike: 14 ATK / 4 DMG Physical, +50 % damage against Flying, Floating (Mistform
  included) and Wind Walking units. Walls, gates and structures are untouched.
- The area stays for the rest of the battle. Inside it every unit's movement costs double, and
  Flying, Floating and Wind Walking units are grounded while they are in it: they walk, and ground
  units and Tremors can hit them. Overlapping areas do not stack.
- An animation of slow-moving force lines, moving inwards and fading, marks the area.
- The battle AI casts it when the enemy units in the area outweigh its own; auto-combat strikes
  enemy units only.
- The cast itself is a faint glow, no debris: it is energy manipulation (owner).

### Entangle to Life/Earth, Weight of the World — as built (2026-10-26)

| script | where | what |
|---|---|---|
| `build_entangle_dual_pfs.py` | `Spells.pfs` 121 | Entangle: sphere 7, tier 1, research 80, icon 167 (its own glyph on the Life/Earth glow) |
| `build_wotw.py` | AoWEPACK `0x558C0000` | spell 91 (a TTremors instance) with a VMT copy: DMG 6 instead of 4 against natural flyers in the roll and both AI values |
| `build_wotw_tc.py` | AoWTCPCK `0x00444000` | Geyser's battle class, the landing (one strike per unit within 6, the caster last; then the field mark), the AI (EvalArea to radius 6), the 127-hex preview, no spray |
| `build_wotw_field.py` | AoWEPACK `0x558C1000` | doubled field-hex costs in every route search; the walker-table flag |
| `build_wotw_field_tc.py` | AoWTCPCK `0x00445000` | doubled step costs in player and AI paths; grounding (flyer tests, the movement table, Tremors) |
| `build_wotw_anim.py` | AoWTCPCK `0x00446000` | the amber contour animation |
| `build_wotw_pfs.py` | `Spells.pfs` 101 | Geyser's record 128 re-numbered, Particle.ILB glows for the cast, MAGICC01 + TREMORS sounds, icon 168 |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icons 167 (Entangle, Life/Earth) and 168 (wings pressed down to the ground, Earth) |
| `build_dual_sphere.py` | its `TABLE` | row `(111, LIFE, EARTH)` |

Choices made in the build, not in the design:
- +50 % is DMG 4 -> 6 for the roll (damage is rolled up to DMG). Airborne means the unit's own
  Flying, Floating (Mistform counts) or Wind Walking, so a flyer already grounded by a field still
  takes it.
- Auto-combat: vanilla's extra-target rule with 0x7F extras -- the target and every eligible unit on
  its side.
- The field is marked after every strike has landed. Grounding is decided where a unit stands when it
  moves: a grounded flyer walks its whole move (terrain costs, walls, zone of control, free swings,
  melee from ground units, Tremors); a flyer starting outside flies and pays double on field hexes. A
  flyer over water, chasm or lava inside a field is not grounded there, so it is never stranded.
- Doubling applies to a hex's terrain cost, not to the zone-of-control surcharge; Skirmisher's flat
  attack cost is not a hex and stays.
- The animation: four contours per field, 4 s from edge to centre, phase from the centre so fields
  drift apart; drawn under units and covered by the fog of war.

Unproven:
- In game: nothing cast yet; the AI's cost of 7 x 127 hex evaluations per aimed unit; the cast's
  glow placement; the sound list's layout (copied from Geyser's two-cue list).

### Earth/Air: Meteor Storm — agreed design (owner, 2026-10-26; built the same day)

From the owner's plan ("2-turn delay to its arrival, strategic storm spell, physical damage").
**Meteor Storm** (Earth/Air tier 2, world map): 60 mana, research 160.
- Cast like the storms: a target hex, the storms' range and their map-level rule (surface and
  Firmament).
- The meteors land at the start of the caster's second turn after the cast: one strike of 16 ATK /
  20 DMG Physical on every unit within 4 hexes, as every storm strikes.
- Nothing shows on the map until then. When it is cast, every player's event log reads "A Meteor
  Storm has been summoned!".
- Only the caster's defeat stops it: it is no global spell, so Disjunction and the Magic window cannot
  reach it.
- The AI casts it as it casts the other storms, at armies inside the area now.
- At impact: twelve meteors fall from the upper left and burst across the area, then a large one near
  the centre.

### Earth/Air: Meteor Storm — as built (2026-10-26)

| script | where | what |
|---|---|---|
| `build_meteor_storm.py` | AoWEPACK `0x558C2000`, BSS `0x558FAED4` | spell 92 (a TFireStormSpell instance) on storm type 0, vanilla's unused Blast Storm slot (physical, 16/20; AI estimate 8/10; "Meteor Storm" in the army event log); the cast through a bare TBlastStorm, whose own VMT is free; the marker: a TFrozenWaterHS VMT copy registered as ClassID `0x2E001`, which counts down at its owner's turn start, strikes and draws the impact |
| `build_meteor_storm_pfs.py` | `Spells.pfs` 102 | Fire Storm's record 13 re-numbered; MAGICC01 (cast, the caster's seat only) + BLAST (impact) sounds; slot 0 the impact chain; icon 169 |
| `build_meteor_fx.py` | `Images\Effects\METEOR.ILB` (new) | the falling meteors, 8 frames each at two sizes, additive like the bursts (Destr, ExplBig) |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icon 169, three meteors falling (the owner's pick, B of three) |
| `build_dual_sphere.py` | its `TABLE` | row `(92, EARTH, AIR)` |

Choices made in the build, not in the design:
- The storm tail is vanilla's: the x4 strength rule for a flyer over terrain it cannot stand on, half
  damage under Physical Protection, no strike on an army under a magic shield.
- The marker sits on the target hex; terrain changes there do not remove it. It is freed at the
  owner's turn after the impact, once the animation has played. A defeated caster's marker stays,
  unseen and inert.
- The impact animation is drawn by the marker itself (TImageSequenceList.Show at the frame counted
  from the impact), so it plays wherever the target hex is on screen, under the fog of war. It runs
  69 map frames.

Unproven:
- In game: nothing cast yet; the animation's speed (the map's frame rate was not measured); loading a
  save with a pending storm.

### Imbue Altar and Imbue Spring — agreed design (owner, 2026-10-26; built the same day)

From the owner's plan: Death/Earth tier 2 "Ritual: places a Bloodlust Altar on the map" and
Life/Earth tier 2 "Ritual: places a Sacred Spring on the map" -- the game's own Blood Shrine and
Spring of Life (the spring that gives Nature's Blessing).
- Both: 60 mana, Ritualist, cast at a hex as Surtr's Chasm is; the structure is placed there.
- The structure is neutral and works as a map-placed one: every army that enters it is blessed,
  enemies included.
- The Spring of Life is never placed on Snow or Wasteland, where it would not bless.

### Imbue Altar and Imbue Spring — as built (2026-10-26)

| script | where | what |
|---|---|---|
| `build_imbue.py` | AoWEPACK `0x558C3000` (entries pinned) | spells 93 and 94 (TLevelTerrain instances), registered on Watcher's `call RegisterSpell`; the target test (construction's site rules over the structure's footprint) and the cast (clear the footprint, then the resource's PlaceResourceUser) |
| `build_surtrs_chasm.py` | its TLevelTerrain caves | ids 93 and 94 sent to `build_imbue.py`'s entries, with the one-hex cursor |
| `build_imbue_pfs.py` | `Spells.pfs` 103–104 | Level Terrain's record 28 re-numbered; Magic.ILB's red burst (altar) and green sparkle (spring) for the cast; ENCHP02, the structures' own blessing sound; icons 170 and 171 |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icons 170 (the horned Blood Shrine, Death/Earth) and 171 (a willow over a pool, Life/Earth), the owner's picks |
| `build_dual_sphere.py` | its `TABLE` | rows `(93, DEATH, EARTH)`, `(94, LIFE, EARTH)` |

Choices made in the build, not in the design:
- The structures are found at cast time in the set's resource list by class (TBloodShrineResource
  `0x20131`, TSpringOfLifeResource `0x20101`); the Release set holds one of each.
- The site follows engineers' construction rules on every footprint hex (Grass, Desert, Snow, Steppe,
  Wasteland or Dirt; no mountain, no structure, nobody's hex) and Level Terrain's own (no army, no
  structure on the target). Forests and decorations on the footprint are cleared, as construction
  clears them.

Unproven:
- In game: nothing cast yet; the cast effect's position (Magic.ILB's canvas offsets measured, not
  seen); that an army stepping onto a ritual-placed structure is blessed as on a map-placed one.

### Air/Fire: Blazing Moon — agreed design (owner, 2026-10-27)

From the owner's plan (Air/Fire tier 3: "Causes the Moon to shine almost as brightly as the sun,
gradually turning the lands to desert and granting females +4 Dam"; AoWx's Drought).
**Blazing Moon** (Air/Fire tier 3, world-map global enchantment): 80 mana, upkeep 20.
- Each turn while it lasts, on the Surface and the Firmament, every hex rolls on its own: Snow 10 %
  to Grass; Grass and Dirt 10 % to Steppe; Steppe 10 % to Desert; Wasteland 5 % to Desert; Ice 25 %
  to Water. Water, lava and the other levels are untouched. The land stays changed after the spell
  ends.
- Every female unit and hero on the map, every player's, has +4 DAM.
- While it lasts the Surface and Firmament views have a warm light, seen by every player: red ×1.11,
  green ×0.98, blue ×0.78 (option F of six).
- It ends when its upkeep goes unpaid, Disjunction takes it or its caster removes it in the Magic
  window.
- Proposed: Ritualist; one per caster; the hexes roll once a day however many Blazing Moons are
  active; a hex the map refuses (an army that cannot stand on the new terrain) keeps its terrain that
  turn; the AI never casts it.

### Air/Fire: Blazing Moon — as built (2026-10-27)

| script | where | what |
|---|---|---|
| `build_blazing_moon.py` | AoWEPACK `0x558C5000`, BSS `0x558FAED8`–`0x558FAEDF` | spell 95 (a TSpellWard instance, registered on Water Mastery's `call RegisterSpell`) whose record is a re-typed `TSpellWardEnchantment` (type `0x58`), one per caster; the daily drying in the record's MsgProc; +4 DAM in `TUnit.GetDamage` and `THero.GetDamage` before their clamps; the warm light over the drawn map frame |
| `build_blazing_moon_pfs.py` | `Spells.pfs` 105 | Astral Ward's record 75 re-numbered (its cast effect and sound), Ritualist, icon 172 |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icon 172, a full moon with three craters ringed by twelve sun rays (the owner's pick, A of three) |
| `build_dual_sphere.py` | its `TABLE` | row `(95, AIR, FIRE)` |

Choices made in the build, not in the design:
- The day's rolls run at the turn start of the caster of the first active Blazing Moon in the global
  magic list, after upkeep, field by field in row order (one synced roll per eligible hex). A level
  the map lacks is skipped.
- Forests and other terrain objects on a changed hex re-skin to the new terrain or remove themselves,
  as under any terrain change; roads and rivers stay.
- The +4 is added when DAM is read, not cached, so it starts and ends with the spell with nothing to
  refresh. It still meets each getter's clamp (units 2–60, heroes 2–40).
- The light is applied to the finished map frame after armies are drawn and before fog, the grid
  and the selection markers, through a 64K colour table built on first use (RGB565 or RGB555; other
  screen formats are left alone).
- Chained in front of Blessing of Stygia's create and CanActivate caves and Awaken Volcano's message
  cave; those scripts accept the chain as their applied state and refuse `--apply`/`--undo` while it
  is in place.

Unproven:
- In game: nothing cast yet; how the light looks; how long a day's drying takes on a large map;
  forests' re-skins.

### Life/Air: Spectral Wings — agreed design (owner, 2026-10-27)

From the owner's plan (Life/Air tier 3: "Enchantment: Physical Weakness and Flying"; AoWx's Angel
Wings, which the owner's version strips to these two; the plan's "Size-cost" note is dropped).
**Spectral Wings** (Life/Air tier 3, unit enchantment): 50 mana, upkeep 5, cast on the world map or
in battle on one of your own units that cannot fly.
- The unit has Flying while enchanted.
- It has Physical Weakness: physical hits on it do ×1.5, rounded up, as the other Weaknesses do;
  Physical Protection cancels it.
- The AI never casts it.
- With it, Embrittled is cut from ×2 to ×1.5 (owner, 2026-10-27).

### Life/Air: Spectral Wings — as built (2026-10-27)

| script | where | what |
|---|---|---|
| `build_airwater_ench.py` | AoWEPACK `0x558BE400` (re-laid out) | spell 96 (a TWindWalking instance) and enchantment `0x97` (a TWindWalkingEnchantment instance), beside Mistform and Static Shield; the target test; Flying through `GetAbMoveTypesAll`'s Wind Walking query; the query widening (Flying and Embrittled answer for `0x97`); the world-map physical ×1.5 |
| `build_embrittle.py` | its `cave_dmg` | ×1.5 instead of ×2; Physical Protection still cancels exactly |
| `build_airwater_pfs.py` | `Spells.pfs` 106, `Ability.pfs` 161 | Wind Walking's records re-numbered; Enchanter; icon 173 |
| `build_battlecast_unitspells.py`, `build_spell_unit_target.py` | AoWTCPCK | castable in battle, on a unit only |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icon 173, spread wings with a pale quill down each feather (the owner's pick, B of three) |
| `build_dual_sphere.py` | its `TABLE` | row `(96, LIFE, AIR)` |

Choices made in the build, not in the design:
- "Cannot fly" refuses Flying (natural, or these wings) and Wind Walking; a floater (Mistform included)
  may take the wings.
- A winged unit counts as a flyer for every Flying test (Weight of the World's +50 % and its grounding
  included) and as Embrittled for damage; Embrittle cast on it is refused as already applied.
- The physical ×1.5 also applies on the world map (Meteor Storm and other physical map damage), where
  Embrittled never lasts.
- Ability `0x97` was a nil registry slot no binary used as a constant; the launch proved it free.
- Embrittle's texts in `Spells.pfs` 119 and `Ability.pfs` 188 were edited in place for ×1.5.

Unproven:
- In game: nothing cast yet; flight gained and lost mid-battle; the fall when the wings end over water.

### Healing Showers, Ooze, Disease Cloud, Pestilence to dual tiers — as built (owner, 2026-10-29)

Owner: "They're just being reassigned": each keeps its behaviour, numbers and mana, and its tier.

| spell | was | now |
|---|---|---|
| Healing Showers (73) | Water tier 1 | Life/Water tier 1 |
| Ooze (124) | Water tier 1 | Earth/Water tier 1 |
| Disease Cloud (104) | Death tier 2 | Death/Air tier 2 |
| Pestilence (9) | Death tier 3 | Death/Air tier 3 |

| script | where | what |
|---|---|---|
| `build_dual_moves_pfs.py` | `Spells.pfs` 83, 134, 114, 19 | sphere 7, the tier kept, research 80 / 80 / 160 / 240 (the dual tier figures), icons 175-178 |
| `build_dual_sphere.py` | its `TABLE` and `MOVED` | rows `(73, LIFE, WATER)`, `(124, EARTH, WATER)`, `(104, DEATH, AIR)`, `(9, DEATH, AIR)`; research already aimed at one moves to Water I, Death II or Death III |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icons 175-178: each spell's vanilla glyph cut to the glyph box (Entangle's recipe) on its pair's glow |

Consequences of the dual rule, not choices of this build: the four are granted at turn start once tier
N of both spheres is known, never researched; units need Spellcasting tier + 1 to cast them; both
spheres' Mastery prices apply. Players who already know a spell keep it. Water tier 1, Death tier 2
and Death tier 3 each keep three or more spells.
Unproven: in game, nothing checked beyond the launch.

### Vafur Flames — agreed design (owner, 2026-10-29)

Named for the flickering fire of the Norse sagas that rings the Valkyrie's mountaintop.
**Vafur Flames** (Fire tier 2, battle): 7 mana.
- A wall of fire one hex thick: a jagged line of up to 6 hexes from the target hex, spreading as
  Surtr's Chasm does (each new hex a valid neighbour of the last that touches no other hex of the
  cast; it stops early). Fire, not a terrain change, drawn with the flames Fire Barrier shows on the
  world map.
- Valid hexes: open ground, with or without units on them.
- The flames strike 10/5 fire (ATK 10, DMG 5) through the generic damage handlers, so Fire Immunity
  and Fire Protection apply, with the fire strike's chance to set Burning. Struck: units in a hex
  when it ignites, any unit that steps in, units standing in it at turn start.
- After 2 rounds each flame has a 25 % chance to go out, each round.
- Units cross normally, at the cost of the strike (vanilla fire adds no movement cost).
- Not cast in auto-combat; the battle AI never casts it.

### Vafur Flames — as built (2026-10-29)

| script | where | what |
|---|---|---|
| `build_vafur_flames.py` | AoWEPACK `0x558C8800` | spell 97 (a TDeathRay instance): mana 7, research 80, sphere 5, tier 2, Evoker, ATK 10 / DMG 5 fire, range 8; a VMT copy with both AI values 0 and no auto-combat command (Mist's recipe) |
| `build_vafur_flames_tc.py` | AoWTCPCK `0x00449000` | Geyser's battle class with no target and no spray; the landing plans the line, places the flames (TCombatFire objects marked in their padding) and strikes the units on them; the flames' turn start (extinguish roll, strike); the strike on entry; FIRESM / FIRELG drawing |
| `build_vafur_flames_pfs.py` | `Spells.pfs` 107 | Geyser's record 128 re-numbered, FIRELG frames for the cast, FIRESTRT for both sound cues, icon 174 |
| `build_dual_spell_icons.py` | `SpellIcn.ILB` + `_SpellIcn.ILB` | icon 174: Call Flames' flame (icon 72's glyph without the figure) at 62 %, three times, each 3 rows lower than the one on its left, on the Fire disc (the owner's pick of nine drafts) |
| `build_spell_unit_target.py` | its `pred` | the cursor and the click refuse an empty target hex that is not open ground |

Choices made in the build, not in the design:
- Open ground: the Walking move table allows the hex's terrain and overlay, and the hex holds no
  fire, standing wall, gate, structure or obstacle. The line starts at the target hex; a cast at an
  enemy standing where a walker could not (a flyer over water) forms nothing.
- Turn start is the start of the caster's side's turn, as vanilla fire acts on its lighter's turn, so
  every unit gets a turn to leave a flame before it burns again.
- After 2 rounds: from the caster's third turn after the cast each flame rolls 25 % before it strikes;
  one that goes out does not strike.
- Friend and foe alike, the caster last, as Weight of the World does. A unit stepping into a flame is
  struck after the step, without the hurt pose; one killed by it ends its move, as a free swing's
  victim does.
- Range 8, the project's battle-spell range. Ooze puts the flames out. The battle AI's paths avoid
  them as they avoid vanilla fire (+20; +10 with Fire Protection, 0 with Fire Immunity).
- The flames alternate small and large fire by hex parity; Fire Barrier picks at random.
- The combat image list ([HSSet+0x94]) is the 71-sequence list at the end of `Release.hss`, indexed
  from 0: 23 is `EFFECTS\FIRESM.ILB`, 24 `FIRELG.ILB`, 60 (vanilla fire's) `FIRESM2.ILB`. Ooze's
  25-27 and THouse's 50 confirm the numbering.

Unproven:
- In game: nothing cast yet; where the fire frames and the cast's flare sit on a combat hex (anchored
  by reasoning from the combat list's offsets); a flame's strike killing a unit mid-walk.

## Open items

- **Does a forested/decorated grass hex actually refuse to cool under Grip of Winter?**
  `ChangeTerrainEx`'s validate pass polls `CanChangeTerrain` (virtual `+0x98`), overridden by
  `TILTerrainMO`/`TFixedILTerrainMO` (forests, decorations); the design doc flags this as plausible but
  unconfirmed, and even its *interpretation* is open — a refusal could read as a deliberate scenery
  exception or as a bug. **Check:** cast Grip of Winter at a forested/decorated grass hex in-game and
  observe whether it cools; if it silently no-ops, decide with the owner whether that is acceptable or
  whether the spell should message the caster.
- **Is a vetoed melt retry visible to the player?** If `CanChangeTerrain` vetoes a restore,
  `TFrozenWaterHS.NewTurn` keeps decrementing the countdown past zero and calling `MeltIce` again every
  subsequent turn — vanilla ice has the same property, so this is not a regression, but nobody has
  confirmed it produces no visible symptom (a message, a stall, a repeated sound). **Check:** engineer a
  veto (place something that survives on a cooled hex before its timer expires, or simply watch a cooled
  hex for many turns past its expected reversion) and confirm nothing untoward is visible.
- **Whether Physical Immunity should eventually get a hard UI target gate** instead of a spend-and-fizzle
  for Embrittle. Currently a deliberate descope, not a defect — surgery on `AoWTCPCK`'s
  `TTacticalCombatUnitHS.SelectSpell` and friends would be required, and nobody has scoped that as its own
  feature. **Check (if ever prioritised):** whether the same targeting surgery already exists for any
  other immunity-gated spell, which would make this a re-use rather than from-scratch UI work.

## Failed approaches — do not retry

- **Embrittle v1 (2026-09-01): passed the cave's name-literal blob's HEADER address to `@LStrAsg`
  instead of `header + 8`.** A Delphi `AnsiString` points at its first character, with the refcount at
  `ptr−8`; `@LStrAsg` read the refcount from the zero padding ahead of the cave, treated it as a live
  string, and wrote an `InterlockedIncrement` into the read-only CODE section during package init — a GPF
  before any handler exists ("Runtime error 216 at 00003924"), on both `AoW.exe` and the editor. **Every
  static check passed** (byte-verify, `.reloc` scan, PIC audit, `--undo` round-trip, `rng_audit`,
  profile-path scan) — none of them can see a pointer that is correct-looking but 8 bytes early. Never
  worked; no save can reference it. Full mechanism and the guard now in the script: see "v1 broke
  STARTUP" under Embrittle above.
- **Registering `Embrittled` as a plain `TEnhancementAbility`** (the "just clone Path of Sand" instinct).
  Wrong `AbilityDataClass`: `TSlowCA.Execute` reads `[data+0x10]`, a field that only exists because
  `TUnitEnchantmentAbility`'s data class carries a `TUnitEnchantment` there — a plain enhancement would
  fault or silently no-op the first time the ability actually applied. Use `TSlowEnchantmentAbility` (or
  any `TUnitEnchantmentAbility` descendant that already does what is needed) instead.
- **Icon v1 (2026-09-01): 1-bit (hard-edged) broken-bone art**, on a misreading of an existing tool's "25
  pixels are off-grey" note as "not black or white" rather than its actual meaning, "off-neutral."
  Produced an icon that visibly did not match vanilla's anti-aliased overlays (measured 17.3% black /
  14.1% mid-tone / 68.6% white across all 110 vanilla spell icons). Re-rendered anti-aliased at 16% black
  / 8.0% mid-tone before shipping; any future hand-drawn icon should measure against that same baseline
  rather than eyeballing "looks dark enough."
