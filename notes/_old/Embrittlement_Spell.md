# Embrittle — new tactical combat spell (id 109) + the Embrittled status (ability 0xB2)

**Status: APPLIED 2026-09-01 — mechanics + icon + Spells.pfs record. UNTESTED IN PLAY.**
The game launches cleanly with all of it installed (verified, see below); nothing beyond that
is confirmed — see the in-game checklist at the bottom.

Scripts: `build_embrittle.py` (mechanics) + `build_embrittle_icon.py` (artwork) +
`build_embrittle_pfs.py` (record 119) — all dry-run by default, all with a surgical `--undo`.
⚠ Apply the icon BEFORE the pfs record: the record's icon field points at the ILB entry the
icon script rewrites.
Binaries: `AoWEPACK.dpl` (7 hooks + one cave zone) and `AoWTCPCK.dpl` (**one byte**).
Backups `.pre-embrittle` exist for both, but **revert with `--undo`, never by copying them** —
the AoWTCPCK snapshot predates the ceiling bump below and restoring it would silently undo it.

---

## What it does

Cast in tactical combat at a single enemy unit, opposed by the target's Resistance exactly like
Slow. On a hit the unit gains the **Embrittled** passive for the rest of that combat; while it
holds, every incoming damage roll whose damage-type mask includes the **physical** bit is
**doubled**.

It is the mirror of Physical Protection (which halves), deliberately at the same magnitude:

| target has | result |
|---|---|
| Embrittled only | `2 × dmg` |
| Embrittled **+ Physical Protection** | `(2·dmg + 1) >> 1` = **dmg** — exact cancellation |
| Physical Protection only | `(dmg + 1) >> 1` (vanilla) |
| Physical **Immunity** | 0, as vanilla — and the cast is refused up front (see the fizzle) |

**Slow is untouched.** Every hook re-derives Slow's own ability id `0x84` for any spell id that
is not ours.

Design decisions were the user's (2026-09-01): Earth sphere, tier 3 research, doubles any hit
carrying a physical component, cancels exactly against Physical Protection, refused on Physical
Immunity targets. Resisted-vs-automatic was not specified; built **resisted** to match Slow —
`SPELL_POWER` in the script is the one-line knob.

---

## The effect site — one function, every combat system

```
AoWE.TCombatObject.ExecuteDamageRole   @0x557269F0   VMT +0x110   mask at [ebp+8]
AoWE.TCombatObject.ExecuteDamageRoleEx @0x55726A6C   VMT +0x114   mask at [ebp+0xC]
```

These are the **only** damage roll in the game; `Ex` differs solely in picking Resistance
(VMT `+0x74`) over Defence (`+0x70`). Neither is overridden — `Ghidra_VMT_Layouts.md` shows
TCombatObject *and* TCombatUnit both carrying `0x557269F0` at `+0x110`, and AoWTCPCK's
`TTacticalCombatUnit` reaches them through an import thunk. So **one patch covers manual tactical
combat, auto-resolve and the strategic map**. Same reasoning `build_reformingflesh.py` records
for hooking the round-tick dispatch rather than a VMT slot.

Vanilla tail, with the hooked run marked:

```
55726A38  mov  edi,eax                 ; EDI = the rolled damage
55726A3A  mov  eax,ebx                 ; \
55726A3C  mov  edx,[eax]               ;  } HOOKED, 10 bytes
55726A3E  call [edx+0x80]              ; /  GetProtectionTypes -> AX
55726A44  not  eax
55726A46  and  ax,si                   ; ESI = ~immunity & damage-type mask, LIVE
55726A49  mov  dx,[0x55726A68]         ; a zero word constant
55726A50  cmp  dx,ax
55726A53  jne  0x55726A5D              ; not every bit covered -> no halve
55726A55  inc edi / sar edi,1 / ...    ; (dmg+1)>>1 = Physical Protection's halve
```

⚠ **The doubling goes BEFORE the halve, and that ordering is the feature.** `cave_dmg` doubles
EDI and then *tail-jumps* into the vanilla `GetProtectionTypes` call, so the halve — if it fires —
sees the already-doubled figure and cancels it exactly. Doubling *after* would give
`((dmg+1)>>1)*2`: 5 damage would come back as 6, not 5. Do not "simplify" the add below the call.

⚠ The halve is an **all-bits** test (`(~prot & ~imm & mask) == 0`); the doubling is an
**any-bit** test (`mask & 0x80`). So a fire+physical strike on a unit with Physical Protection
alone is doubled and *not* halved — correct, because that protection genuinely does not apply to
that hit in vanilla either.

⚠ TCombatWall is also a TCombatObject. It answers through
`TCombatObject.GetAbilityEnabled @0x557268D4` (`xor eax,eax; ret`), so walls can never be
embrittled and need no type test — the same free type-gate reformingflesh relies on.

### The damage-type bit order (and where it is defined)

`TAbilityOwner.GetAbProtectionTypesAll @0x5574F97C` and `GetAbImmunityTypesAll @0x5574FADC` are
the two functions that *build* these masks, and they fix the numbering:

```
0x01 Fire   0x02 Cold   0x04 Lightning  0x08 Magic
0x10 Poison 0x20 Death  0x40 Holy       0x80 PHYSICAL
```

Physical Protection = ability `0x4D` **or** `0xA6` → bit `0x80`; Physical Immunity = ability
`0x0D` → bit `0x80`.

### The damage clamp is 126, not 49

`TCombatObject.ExecuteDamage @0x55726C58` asserts `damage < 0x7F` ("Invalid Damage Value").
**Vanilla was `0x31` (49); Ziggurat already raised it to `0x7F` as part of the DAM/HP doubling.**
`cave_dmg` clamps at 126 so a doubling can never turn a big hit into an assert dialog. Reachable
only in absurd cases — it is insurance, not a live constraint.

---

## The spell — no new class, no new save/network ClassID

`Adding_New_Spells_Abilities_2026-07-05.md` rates "a combat spell that applies its own unit
enchantment" as Tier 2/3, because a cloned `TSlowCA` is a save- and wire-serialized object needing
a unique ClassID through `RegisterEClasses`. **That is avoided entirely.**

Embrittle *is* a `CombatSpells.TSlow` instance with a different id, name, sphere, tier and
cost, and it produces genuine `TSlowCA` combat actions. The only thing that must differ is which
ability id the machinery applies, and TSlow hard-codes `0x84` in exactly three places — every one
of which already has the spell id in a register:

| site | vanilla | hooked as | discriminator |
|---|---|---|---|
| `TSlow.CreateCA @0x557F89B3` | `mov edx,0x84` | **left alone** (the cave recomputes EDX) | — |
| `TSlow.CreateCA @0x557F89BC` | `call [ecx+0xA8]` (6 B) | `call cave_createca` + `nop` | `[esi+0x10]` = spell id |
| `TSlowCA.Execute @0x557F884F` | `mov edx,0x84` (5 B) | `call cave_absel` | `[ebx+0x18]` = spell id |
| `TSlowCA.Execute @0x557F8863` | `mov edx,0x84` (5 B) | `call cave_absel` | `[ebx+0x18]` = spell id |

`[CA+0x18]` is stamped by `TSlow.CreateCA @0x557F89A1`. Serialization, network identity and replay
are untouched: **every Embrittle CA is a bit-for-bit ordinary TSlowCA.**

⭐ This is the generalisable trick: *when a vanilla class already carries everything you need and
only a constant differs, clone the INSTANCE and make the constant a function of state the code
already holds.* It converts a Tier-3 "new archetype" into four small caves.

---

## The ability — instantiate TSlowEnchantmentAbility, do not build a class

`PassiveAb.TSlowEnchantmentAbility` (classref ptr `0x557B96B8`, `Create @0x557B9E78`) overrides
only `Create`, `CreateEnchantment` and `CombatDone`, and each is driven by the ability's **own id
field**, not a constant:

```
CombatDone @0x557B9F24   owner := combatUnit.GetAbilityOwner()   ; VMT +0xB8
                         owner.RemoveAbility([self+0x0C])        ; VMT +0x98
```

so a second instance with `[+0x0C] = 0xB2` removes `0xB2` at end of combat entirely on its own.
No VMT clone, no new class, no `RegisterEClasses`.

⚠ **NOT `CreateEnhancementAbility`.** A plain `TEnhancementAbility` has the wrong
`AbilityDataClass`: `TSlowCA.Execute @0x557F8863` does `GetAbilityData(unit, id)` and then calls
`+0x54`/`+0x58` on `[data+0x10]`, which only exists because `TUnitEnchantmentAbility`'s data class
carries a `TUnitEnchantment` there. Registering `0xB2` as an enhancement would fault or silently
no-op. This is the trap that makes the "just clone Path of Sand" instinct wrong here.

The constructor leaves `[+0x20]` (the `TAbilitySelectionType` mask) at 0, so Embrittled is never
offered in the editor, on items, or at hero level-up — same as Slow's `0x84`. Hence **no
`FExpandCost` store**, unlike `build_reformingflesh.py`: an ability that cannot be selected cannot
be bought.

---

## Physical Immunity — a fizzle, not a UI gate

**Manual tactical combat has no damage-based target gate.** Proof: `TSlow.GetCombatDamageValueEx
@0x557F8948` returns an all-zero struct and Slow is still freely castable. `TSpell`'s
`tcGetDamageValueEx` (`+0x88`) just forwards to `GetCombatDamageValueEx` (`+0x84`) and nothing
consults it for validity. Only **fast** combat gates on a value —
`TCombatSpell.fcPrefetchCombatCommands @0x557F76BC` skips a target whose `fcGetDamageValueEx`
first dword is 0.

So the engine's own idiom for "this spell does not apply to that target" is a fizzle in
`CreateCA`, and `CombatSpells.TTurnUndead` is the vanilla worked example: `TTurnUndead.CreateCA
@0x557F7C50` builds the CA and only calls the hit-roll setup if the target is undead — casting
Turn Undead at a living unit is permitted and simply does nothing.

`cave_createca` copies that: on a Physical Immunity target it returns `AL=1`, i.e. "already has
the ability", which is the *existing vanilla path* for re-casting Slow on a slowed unit. The
caller skips `HitRole`, `[CA+0x14]` stays 0, `TSlowCA.Execute` does nothing.

⚠ **The cast is still spent** (mana and casting points go). Consistent with vanilla re-casting,
but it is a fizzle, not a greyed-out target. A hard UI gate means surgery on AoWTCPCK's targeting
(`TTacticalCombatUnitHS.SelectSpell` and friends) and is a separate feature.

Physical Immunity already makes the ability inert on its own — `ExecuteDamageRole` returns 0
before reaching the cave when `~immunity & mask` is empty — so the fizzle is about not wasting the
cast, not about correctness.

---

## Addresses

| what | address |
|---|---|
| cave zone | `0x5582D000..0x5582D300` (357 B used of 768 reserved) |
| ↳ `Embrittled` literal / `Embrittle` literal | `0x5582D000` / `0x5582D014` |
| ↳ `cave_reg_abil` / `cave_reg_spell` | `0x5582D030` / `0x5582D070` |
| ↳ `cave_createca` / `cave_absel` / `cave_dmg` | `0x5582D0D0` / `0x5582D110` / `0x5582D130` |
| ability registration hook | `0x557BCE65` (last still-direct `call RegisterAbility`) |
| spell registration hook | `0x557FA83F` (last `call RegisterSpell` in `RegisterCombatSpells`) |
| `TSlowEnchantmentAbility.Create` / classref ptr | `0x557B9E78` / `0x557B96B8` |
| `TSlow.Create` / classref ptr | `0x557F8890` / `0x557F4DC0` |
| `TAbilityControl.RegisterAbility` / `TSpellControl.RegisterSpell` | `0x55750238` / `0x55779B40` |
| `System.@LStrAsg` thunk | `0x55701150` |
| `AoWTC.SpellTypes` (AoWTCPCK DATA) | `0x004672F4`, file offset `0x662F4` |

Spell fields poked after `TSlow.Create` (everything else inherited): `+0x10` id 109, `+0x14` mana
14, `+0x18` research 80, `+0x20` sphere 3 (msEarth), `+0x21` tier 3, `+0x34` power 9.
`TMagicSphere` = 0 Cosmos, 1 Life, 2 Death, 3 Earth, 4 Air, 5 Fire, 6 Water.

Costs were calibrated against **Tremors** (the other Earth tier-3 combat spell: mana 14,
research 80), read from `Spell_Records_Dump.txt`. ⚠ That dump's `id` column is the **.pfs record
id = spell id + 10**, not the spell id — Slow is row `id 120`.

### Registration sites — chain, never re-use

Measured live 2026-09-01 inside `PassiveAb.RegisterPassiveAbilities @0x557BC1CC` (len `0xE00`):
83 of the calls are still direct; four are already repointed —
`0x557BCE9A` (reformingflesh → `0x55826000`), `0x557BCECF` (shield → `0x55823128`),
`0x557BCF04` (caster_cost → `0x558208B4`), `0x557BCF39` (drillmaster → `0x55816000`).
`0x557BCE65` is the last still-direct one and is what this feature took.
⚠ Taking a site another feature already repointed is the documented **silent-unlink** failure.
The script re-measures rather than trusting this list.

At both registration sites EBX holds the control object for the whole enclosing function, and the
instruction immediately before is `mov eax,ebx` — which is what `mov eax,ebx` in each cave uses.

### Cave placement

`0x5582D000`: page-aligned, above every address claimed by any build script (highest prior claim
`0x5582C080`), 764,416 zero bytes ahead, no `.reloc` entry in the zone.
⚠ **Do not "reclaim" the apparent gap below it** — `build_rng_lockstep.py`'s rng_sync stub and
`build_panic_nomelee.py` both sit inside what looks like one enormous free run. A zero run is not
proof a zone is unclaimed; it is usually another feature's growth reservation. That mistake is on
record three times in this folder.

---

## AoWTCPCK — SpellTypes[109], the byte that stops the spell vanishing

`AoWTC.SpellTypes` is `byte[0..130]` = each spell's tactical-combat class. `ID_Ceilings.md` S3:
a spell with id ≥ 100 whose byte is **0 is silently deleted from the research list** by
`AoW.exe @0x0042F304`. 109 is the vanilla registry hole, so its byte was 0.

Set to `0x07` — **measured, not guessed**: `SpellTypes[110]` (Slow) and `[111]` (Entangle) are
both `0x07`, the single-enemy-unit-target tactical class, which is exactly what Embrittle is.
Own-module DATA at a fixed base, so no reloc concern and no cave.

---

## ⚠ Two other scripts had to move — their failure mode is silence

Vanilla's highest ability id was `0xA9`, so nine `cmp <counter>, 0xAA` loop terminators exist
across AoWTCPCK.dpl, AoW.exe and AoWCompat.exe. Registering `0xB2` made both ladder scripts one
short. **Both were extended `0xB2 → 0xB3` and re-applied on 2026-09-01:**

```
build_abilityid_ceilings.py   LADDER = (0xAA, 0xB1, 0xB2, 0xB3)   6 sites + 2 lockstep twins
build_tcablist_ceiling.py     LADDER = (0xAA, 0xB1, 0xB2, 0xB3)   1 site
```

Both derive their target from `re_tools/ability_names.py`, so **`0xB2: "Embrittled"` was added to
its `MODDED` map** — a registration cave is invisible to that module's constructor scan (it sees
only Slow's own `0x84`). Without the entry the ability prints as `?` and the ladders would not
know to move. Shield shipped four days before anyone noticed that omission.

Left unraised, the ability works but is invisible to the tactical AI's battle scoring, the item
banner popup, the unit hover popup, and `CreateTCAbList`.

---

## The data half — icon and Spells.pfs record 119 (added 2026-09-01)

Two more scripts, both data-only. **Run them in this order** — the record's icon field points at
the ILB entry the icon script rewrites.

    python build_scripts/build_embrittle_icon.py --apply     Images/SpellIcn.ILB
    python build_scripts/build_embrittle_pfs.py  --apply     Release/Spells.pfs

### `build_embrittle_icon.py` — a broken-bone icon, in place, no format surgery

SpellIcn.ILB has 111 entries (ids 0–155) of which only **108 are referenced by a spell**; 128,
129 and 155 are dead. **Entry 128** (a Dragon on a Cosmos disc, cut content) is reused. Three
exact-size writes, so the directory, every `off` field and the file length are untouched — an
append would have meant rewriting all three:

| offset | len | write |
|---|---|---|
| `0x8B4C5` | 2800 | frame pixels ← icon 52 (Slow), i.e. the real `SI-Earth.BMP` green disc |
| `0x4FFD` | 4 | frame `transparent` `0x00000000` → `0x00004148` |
| `0x8BFB5` | 1972 | sub pixels ← the 34×29 anti-aliased broken-bone stamp |

⚠ **The `transparent` write is not cosmetic.** Entry 128's frame declares `0x0000` (pure black)
and the Earth frame contains **113 pure-black pixels**, so any blitter honouring the key would
punch 113 holes through the disc. Every real Earth frame declares `0x4148` — a value absent from
its own pixels, i.e. "key nothing". Matching it makes the entry behave exactly like a known-good
Earth icon rather than resting on an assumption about whether the engine honours the field.
(`spell_icons.py` concluding the field is unusable for *rendering* is a statement about the tool,
not about the engine.)

The art is stored in the script as a literal 34×29 character grid over a 6-level grey RAMP —
reviewable in a diff, hand-editable, and immune to a PIL version changing its resampling.

⚠⚠ **THE ART MUST BE ANTI-ALIASED. v1 shipped it 1-bit and that was wrong.** The mistake was
reading `spell_icons.py`'s "25 pixels in the entire file are off-grey" as *not black or white*;
it means *off-neutral* (off the r=g=b axis). Measured across all 110 vanilla overlays
(133,984 px): **17.3% black, 14.1% mid-tone, 68.6% white** — per-icon the mid-tone share runs
8–17% (Slow 8.1, Entangle 7.9, Tremors 10.1, Stone Skin 11.9). Those mid-tones ARE the soft
semi-black outline every vanilla icon has, so a hard-edged stamp reads as foreign next to them.
The engine evidently composites by luminance rather than by a pure colour key — which is also
why `ink_alpha()` renders these correctly. The shipped stamp is **16% black / 8.0% mid**.
⚠ The background must still be *exactly* `0xFFFF`, the sub's declared transparent value.

v1's knobs were also too broad (end-height ≈ 3.2× the shaft). v2 is ≈ 2.3×, with a visible
notch between the two lobes at each end — that notch is what makes it read as a bone rather
than a blob at 34×29.

`--undo` restores the vanilla Dragon/Cosmos entry from a zlib+base64 blob embedded in the script,
so the revert path needs no backup file.

### `build_embrittle_pfs.py` — record 119, cloned from Slow's

`TSpellControl.ReadWrite @0x55779A6C` streams each spell under **tag = spell id + 10**, so spell
109's record is **119**. It is cloned from **record 120 (Slow)** — same class, sphere, tactical
class and targeting — with six fields patched: `0x0A` description, `0x0C` icon index 52 → 128,
`0x0D` mana 14, `0x0F` research 80, `0x10` sphere 3, `0x11` tier 3. Slow's 1008-byte nested
TImageSequenceList and its TSFXLibrary node are inherited wholesale; hand-authoring either is a
project, cloning both cannot be structurally wrong. ⚠ The spell id is **not** in the body — it is
the index key, so re-keying the clone to 119 is what makes it spell 109's record.

**The insert is a splice, not a directory rebuild.** Index offsets are relative to the *end* of
the directory, so growing the index by one wide entry moves the payload base by 8 automatically:
records before the splice keep their offsets, records after gain `len(body)`, the wide count goes
up by one, and the trailing CRC-32 is repaired to residue `0x2144DF1C`. ⚠ Records are sorted by
id **and** by offset and both orders must agree — `index_layout()` probes for exactly that
invariant — so 119 goes *between* 118 and 120, never appended at the end.

Verified: 108 → 109 records, every other record byte-identical (audited field-by-field), CRC
residue correct, `--undo` restores the file byte-identically, and `re_tools/pfs.py` re-reads it
independently. **Free spell ids are now 79–99.**

⚠ Once record 119 exists **the data file wins** for tags `0x0A`–`0x11`, so
`build_embrittle.py`'s mana/research/sphere/tier constants are now decorative — re-tune the spell
here (or in AoWDevEd), not in the cave.

### Ability.pfs record 188 — the Embrittled status text

Added 2026-09-01 by the same script. Cloned from **Slow's ability record 142** and the wording
is the deliberate mirror of vanilla Physical Protection's own:

> Physical Protection — *"Reduces the damage inflicted upon the unit by physically-based attacks by 50%."*
> **Embrittled** — *"Doubles the damage inflicted upon the unit by physically-based attacks, for the duration of combat."*

⚠⚠ **Slow is the donor specifically because its tag 9 is `00 00`.** Tag 9 is the
TAbilitySelectionType mask and `Ability.pfs` **overwrites the registration cave's value with
it**. Cloning Physical Protection's record instead would have shipped tag 9 = `0x03FF` and made
Embrittled selectable in the editor, on items and at hero level-up — a status ability offered
as a purchasable perk. Slow's 0 keeps it status-only, matching what the ctor sets.

⚠ Record 188 is past the current maximum (186), so it splices at the **end** of the payload,
whereas spell 119 splices mid-file before 120. One code path serves both because the splice
point is derived from the **id order** (first record with a larger id, else end), not from the
donor's position.

⚠ Every vanilla description ends **CRLF**; the first cut of record 119 did not, and was
rewritten to match. `pstr32()` appends it.

### Still not done

Nothing outstanding on the data side.

### ⭐ A pre-existing tool bug this uncovered

`re_tools/spell_icons.py` looked for `spell_names.json` in `Modding Resources/` when it actually
lives in `Modding Resources/Zig notes/`. Because the whole labelling block is guarded by
`if os.path.exists(npath)`, the miss was **silent**: the contact sheet rebuilt cleanly and simply
captioned all 111 icons "no spell with this id". Fixed to try both paths and to print a warning
when neither is found. ⚠ It also means `grep -c` is the wrong counter for that file — the HTML is
one long line, so `grep -c` reports 1 whether one caption or all 111 are broken; use `grep -o | wc -l`.

---

---

## Naming — why "Embrittle", not "Embrittlement"

Settled 2026-09-01 after checking what vanilla actually does, rather than assuming.

**Vanilla inflects the status name.** `PassiveAb.TBlessedEnchantment.Create` loads
**`BlessedRStr`**, not `BlessRStr` — the spell is *Bless*, the status is *Blessed*. And both
forms ship as separate abilities elsewhere: `0x28` is **Entangle**, `0x5E` is **Entangled**.
Where a name already works unchanged as a state (Slow, Fire Protection, Concealment, Liquid
Form, Dark Gift) vanilla simply reuses it — `TSlowEnchantmentAbility` loads `SlowRStr`.

⚠ `re_tools/ability_names.py` shows names like "Fire Protection Enchantment" and "Blessed
Enchantment". Those are **class-derived artefacts of its constructor scan, not the in-game
names** — the game displays whatever resourcestring the ctor loads. Do not cite that table as
evidence of a naming convention.

**Entangle is this spell's closest sibling** — Earth sphere, tactical combat, single enemy
target, applies a status — and it is an imperative verb. Of 109 spell names 27 are one word,
and verbs are well represented (Bless, Desiccate, Entangle, Slow, Stoning, Vaporize).
"Embrittlement" would have been the only `-ment` abstract process-noun in the whole list.

So: spell **Embrittle** (imperative verb), status **Embrittled** (past participle) — exactly
the Entangle/Entangled shape.

⚠ Renaming was an **in-place cave rewrite**, not a revert: a name is a variable-length literal,
so changing it moves every cave after it. `build_zone()` therefore takes `spell_name`/`abil_name`
so PRIOR_ZONES can reproduce the older layouts byte-for-byte and verify-before-write recognises
them. Names are not serialised (the id is), so there is no save or MP consequence.

---

## ⚠⚠ v1 SHIPPED A GAME THAT WOULD NOT LAUNCH — "Runtime error 216 at 00003924"

**Fixed 2026-09-01, ~1h after apply. Read this before writing any cave that assigns a string.**

### The bug

A Delphi `AnsiString` variable holds a pointer to the **first character**. The refcount is at
`ptr-8` and the length at `ptr-4`. The literal blob written into the cave is
`[refcount=-1][length][chars][NUL]`, so the value handed to `System.@LStrAsg` must be
**blob address + 8**.

v1 passed the blob address itself. `@LStrAsg` therefore read the refcount from the 8 bytes
*before* the literal — the zero padding at the front of the cave zone — saw `0`, and since
`0 >= 0` means "a live string, not a literal", it did an `InterlockedIncrement` on it. That is a
**write into the read+execute CODE section**, executed during package init at DLL load.

Access violation before any exception handler exists ⇒ **`Runtime error 216 at 00003924`** on
startup, from `AoW.exe` and the editor alike. The game never reached its menu.

⚠ **216 is a GPF. 217 is the duplicate-ability-id error** (`RegisterAbility` raising before a
handler exists) — `ID_Ceilings.md` documents 217. Do not confuse them: 216 here was nothing to do
with ids, and chasing the id ceiling would have wasted the session.

`build_reformingflesh.py:435` had it right all along and even says so in an inline comment —
`reg = build_reg(name_blob_va + 8, cost)  # +8 skips the refcount+length header`. The precedent
was read for the cave *shape* and the `+8` was not carried across.

### ⭐ The real lesson: every static check passed

Byte-level verify-before-write, the `.reloc` coverage scan, the PIC audit, the `--undo`
round-trip proving byte-identical restoration, `rng_audit --owners`, the profile-path scan — **all
green, on a build that could not start the game.** None of them can see a pointer that is
correct-looking but 8 bytes early.

**So: a cave that runs at DLL/package init must be proved by LAUNCHING THE EXECUTABLE, and that
is not an "in-game test" to hand to the user — it is a build-time check the author owes.**
Launch, wait ~10 s, assert the process is alive and responding and that no window titled `Error`
exists. That is a few seconds of work and it is the only check that would have caught this.

### The guard now in the script

`build_zone()` decodes the address the assembled cave actually resolves for its name literal and
asserts it equals `header + 8`, and that the dword at `ptr-8` is the `-1` literal refcount. The
broken layout is kept as `PRIOR_ZONES[0]` so verify-before-write recognises it as one of *our*
pre-states and rewrites the cave **in place** — no revert, no backup restore, per the project's
layering rule. Nothing needs migrating: v1 never ran, so no save can contain spell 109 or
ability `0xB2`.

---

## Checks already done (2026-09-01, from the files)

- All 7 AoWEPACK sites + the AoWTCPCK byte read back `applied`.
- Every displaced run is **`.reloc`-clean**, verified programmatically; the cave zone too.
- Caves are position-independent — register-only, `call`/`jmp rel32`, and a
  `call <addr>; pop ecx` delta anchor for the two literal/classref addresses. No absolute address
  anywhere; the cave zone contains no drive-letter path and only the two name literals.
- **`--undo` round-trip: AoWEPACK.dpl comes back byte-identical (SHA-256) to its pre-patch state**,
  and AoWTCPCK differs by exactly the 5 ceiling bytes applied afterwards — nothing else.
- `rng_audit.py --owners`: this feature owns **no** RNG site; it adds no draw (`HitRole` is called
  by the untouched host). ⚠ An earlier revision of the build script quoted another feature's cave
  address in a comment and the audit, which attributes by grepping script *text*, reported
  build_embrittle as an owner of a synced draw. Reworded. **Don't quote other features' raw
  addresses in a build script.**
- No profile-path leak in any binary or in the new/edited scripts (`grep -laF`, with `-a`).
- **The game launches.** `AoW.exe` started, ran 71 s with 68 s of CPU, `Responding=True`,
  main window `Age of Wonders`, and an enumeration of every visible top-level window found
  nothing titled `Error`. (Window rect is 0x0 — DirectDraw exclusive fullscreen — so
  `grabwin.py` cannot capture it; process health is the usable signal.)

## NEEDS THE USER'S IN-GAME TEST — nothing below is checkable from the files

1. **Embrittle** appears in the Earth sphere, tier 3, of the research list, and its spellbook
   page shows the **broken-bone icon** and the description, costing 14 mana.
1b. Every OTHER spell still shows its own icon and text — the Spells.pfs audit proves the bytes
   are untouched, not that the game agrees.
2. Once researched it is castable **in tactical combat** at a single enemy unit (14 mana), and
   lands or is resisted like Slow.
3. A unit it hits shows **Embrittled** in its ability list for the rest of that combat, and the
   status is **gone** at the start of the next battle.
4. A melee hit on that unit does **roughly double** its normal damage.
5. On a unit that *also* has Physical Protection, damage is back to **normal**.
6. Casting it at a Physical Immunity unit does nothing (the mana is still spent — the documented
   fizzle, not a bug).
7. **Slow still works exactly as before**, on its own spell and its own status.
8. Auto-resolve a battle involving an embrittled unit — no assert dialog.
9. Ranged and physical-damage spells against an embrittled unit are doubled too (the mask test is
   any-bit, so an elemental-strike weapon should also double).
