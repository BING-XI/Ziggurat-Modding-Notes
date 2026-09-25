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
| Embrittle spell (id 109) + Embrittled status (ability `0xB2`) — mechanics | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_embrittle.py` | `AoWEPACK.dpl` (7 hooks + 1 cave), `AoWTCPCK.dpl` (1 byte) |
| Embrittle spellbook icon (broken-bone stamp, reuses dead entry 128) | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_embrittle_icon.py` | `Images/SpellIcn.ILB` |
| Embrittle `Spells.pfs` record 119 + `Ability.pfs` record 188 | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_embrittle_pfs.py` | `Release/Spells.pfs`, `Release/Ability.pfs` |
| Ability-id ceiling ladders extended `0xB2`→`0xB3` (forced by Embrittled's new id) | 🔨 APPLIED, UNTESTED (2026-09-01) | `build_abilityid_ceilings.py`, `build_tcablist_ceiling.py` | `AoWTCPCK.dpl`, `AoWz.exe`, `AoWzCompat.exe` |
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
python build_scripts/build_embrittle_icon.py --apply    Images/SpellIcn.ILB    ) run icon
python build_scripts/build_embrittle_pfs.py  --apply    Release/Spells.pfs    ) BEFORE pfs
```

⚠ Apply order matters (icon before pfs — the record's icon field points at the ILB entry the icon
script rewrites). **`--undo` order does not**: each of the three scripts targets an independent
file/byte-range and none of them byte-compares another's output, unlike the Grip of Winter coupling
below — run any of the three `--undo`s in any order, or just the one you need.

### What it does

Cast in tactical combat at a single enemy unit, opposed by the target's Resistance exactly like Slow. On
a hit the target gains the **Embrittled** passive for the rest of that combat; while it holds, every
incoming damage roll whose damage-type mask includes the physical bit is **doubled**. It is the
deliberate mirror of Physical Protection (which halves):

| target has | result |
|---|---|
| Embrittled only | `2 × dmg` |
| Embrittled **+ Physical Protection** | `(2·dmg + 1) >> 1` = **dmg**, exact cancellation |
| Physical Protection only | `(dmg + 1) >> 1` (vanilla, unchanged) |
| Physical **Immunity** | 0, as vanilla — and the cast fizzles rather than applying (below) |

Design decisions were the user's (2026-09-01): Earth sphere, tier 3 research, doubles any hit carrying a
physical component, cancels exactly against Physical Protection, refused (fizzles) on Physical Immunity
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
Earth tier-3 combat spell (also mana 14, research 80). **Free spell ids are now 79–99**, and `0xB2` was
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
`AoWTCPCK.dpl`, `AoWz.exe` and `AoWzCompat.exe`. Registering `0xB2` made both ceiling ladders one short.
Extended and re-applied 2026-09-01:

```
build_abilityid_ceilings.py   LADDER = (0xAA, 0xB1, 0xB2, 0xB3)   6 sites + 2 lockstep twins
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

#### The icon — a broken-bone stamp, reusing a dead entry, no format surgery

`SpellIcn.ILB` holds 111 entries (ids 0–155), of which only 108 are referenced by any spell; **128, 129
and 155 are dead.** Entry 128 (a Dragon on a Cosmos-purple disc, cut content) is reused rather than
appended — appending a 112th entry would mean rewriting the directory, every `off` field after the
insertion point and the file length; overwriting a dead entry needs none of that, because all three
writes below are exact-size:

| offset | length | write |
|---|---|---|
| `0x8B4C5` | 2800 B | frame pixels ← icon 52 (Slow), the real `SI-Earth.BMP` disc, read live so it always matches whatever Earth frame is installed |
| `0x4FFD` | 4 B | frame `transparent` field: `0x00000000` → `0x00004148` |
| `0x8BFB5` | 1972 B | sub-entry pixels (34×29) ← the broken-bone artwork |

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
hard-edged 1-bit stamp reads as visibly foreign next to them. The shipped v2 stamp sits inside that band
(verified live 2026-09-03: 16% black / 8.0% mid-tone), with the end lobes re-proportioned (≈2.3× the
shaft width, not v1's ≈3.2×) and a visible notch between the lobes so it reads as a bone rather than a
blob at this size. The background stays exactly `0xFFFF`, the sub-entry's own declared transparent
value.

`--undo` restores the vanilla Dragon/Cosmos entry from a zlib+base64 blob embedded in the script, so the
revert path needs no backup file.

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
| v3 — current, shipped | **Embrittle** | `8` (correct) | Current live layout. |

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

> *"Freezes a small area of water solid enough to walk over, and chills the land it touches: desert to
> steppe, steppe to grass, grass to snow. The ice and the chill both thaw after a few turns."*

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
