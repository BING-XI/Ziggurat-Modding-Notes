# Abilities added from scratch

This file covers abilities that did not exist before this project minted them — **Path of Sand**,
**Assassin** (plus the ranged-slayer extension it justified), **Drillmaster**, **Magebane**, the four
**Caster Cost abilities** (Evoker / Conjurer / Enchanter / Ritualist), and **Copper Medal**'s fourth
ability-owner slot — plus the general *mechanics* of adding an ability at all: the id budget, the
registration recipe, the tactical-AI/UI ceilings, and the two places a level-up cost can live.

**Not here:** changes to pre-existing abilities (Slayer/Champion re-grades, the Invisibility penalty,
Turn Undead, morale, etc.) are `02-abilities-modded.md`. Spell registration, the spell-id budget and
the `SpellTypes[0..130]` ceiling are `05-spells-added.md` — the ability and spell id-ceiling stories
share one investigation (the 2026-09-01 crash) but are otherwise independent mechanisms, and the ~4
spell rows of the ceiling census live there, not here. Shield's combat maths (the protected arc, the
auto-resolve roll, the ranged-penalty magnitude) is `01-combat-maths.md`; this file records only the
one fact about Shield that matters here — its ability id and the cave it shares with Magebane. The
canonical cross-project cave-ownership map is `12-re-toolchain.md`.

## Status table

| feature | status | owning script | binary |
|---|---|---|---|
| Path of Sand — new terrain-drying passive (`0x9F`) | ✅ CONFIRMED WORKING (2026-07-08) | `build_path_sand.py` | AoWEPACK.dpl |
| Assassin / Hero Slaying, melee (`0x38`) | ✅ CONFIRMED WORKING (2026-07-08) | `build_assassin.py` | AoWEPACK.dpl |
| **Wall-target AV fix — shared `TCombatUnit` guard for Assassin + Magebane** | 🔨 APPLIED, UNTESTED (2026-09-11) | `combatunitguard.py` + `build_assassin.py` + `build_magebane.py` | AoWEPACK.dpl |
| Ranged slayer support — Assassin, Monster Slaying, Holy/Unholy Champion | ✅ CONFIRMED WORKING (2026-07-08) | `build_ranged_slayers.py` | AoWEPACK.dpl |
| Drillmaster — per-stack XP aura (`0xAB`) | ✅ CONFIRMED WORKING (2026-08-08, v4) | `build_drillmaster.py` | AoWEPACK.dpl + `Release/Ability.pfs` |
| Magebane — enchantment-scaling ATK/DMG (`0xAA`) | 🔨 APPLIED, UNTESTED (2026-08-29 re-tune) | `build_magebane.py` | AoWEPACK.dpl |
| Magebane description text (record 180) | 🔨 APPLIED, UNTESTED (2026-08-29) | `build_magebane_desc.py` | `Release/Ability.pfs` |
| Evoker / Conjurer / Enchanter / Ritualist — casting-cost discount (`0xAC`–`0xAF`) | ✅ CONFIRMED WORKING (2026-08-27, at 50%) | `build_caster_cost.py` | AoWEPACK.dpl + `Release/Ability.pfs` |
| Caster Cost discount 50% → 40% (`DISCOUNT_MUL = 0x999A`, ×0.6 truncating) | 🔨 APPLIED, UNTESTED (2026-09-25) | `build_caster_cost.py` | AoWEPACK.dpl |
| Manual: "Caster" row on every spell card (from tag `0x12`), ability texts at 40% | 🔨 BUILT, NOT PUBLISHED (2026-09-25) | `build_ziggurat_manual.py` | manual |
| Caster Cost — family as data (`Spells.pfs` tag `0x12` → `[spell+0x23]`), data classifier | 🔨 APPLIED, UNTESTED (2026-09-25) | `build_spell_family.py` + `build_caster_cost.py` | AoWEPACK.dpl + `Release/Spells.pfs` |
| Caster wallet — instant gate and every hero charge use `CastingMana` | 🔨 APPLIED, UNTESTED (2026-09-25) | `build_caster_wallet.py` | AoWEPACK.dpl |
| Seven Weakness abilities — Fire/Cold/Lightning/Magic/Poison/Death/Holy (`0xB3`–`0xB9`) | 🔨 APPLIED, UNTESTED (2026-09-25) | `build_weakness.py` + `build_weakness_pfs.py` | AoWEPACK.dpl + `Release/Ability.pfs` |
| Liquid Body — Swimming + Physical Protection + no Burning (`0xBA`) | 🔨 APPLIED, UNTESTED (2026-09-25) | `build_liquidbody.py` + `build_liquidbody_pfs.py` | AoWEPACK.dpl + `Release/Ability.pfs` |
| Bound (`0xBB`) and Commanding (`0xBC`) — the command-ability bond and its RES cost; design and checklist in `02-abilities-modded.md` "Command abilities — bound thralls" | 🔨 APPLIED, UNTESTED (2026-09-25) | `build_command_bond.py` + `build_command_bond_pfs.py` | AoWEPACK.dpl + `Release/Ability.pfs` |
| Copper Medal — rank ladder, stat bonus, icon | ✅ CONFIRMED WORKING (2026-07-30) | `build_copper_medal.py` | AoWEPACK.dpl + `Images/*Combat.ILB` |
| Copper Medal — 4th ability-owner slot (copper bonus abilities) | 🔨 APPLIED, UNTESTED (2026-07-30) | `build_copper_medal.py` (`COPPER_GRANTS_ABILITIES=True`) | AoWEPACK.dpl + `AoWDevEd.exe` |
| Ability-id ceiling — 4× `TCAI.EvalBattle` scans + item/hover banner popups | 🔨 APPLIED, UNTESTED (ladder at `0xB3`, 2026-09-01) | `build_abilityid_ceilings.py` | AoWTCPCK.dpl + AoWz.exe + AoWzCompat.exe |
| Ability-id ceiling — in-combat unit panel (`CreateTCAbList`) | 🔨 APPLIED, UNTESTED (ladder at `0xB2`, 2026-08-28) | `build_tcablist_ceiling.py` | AoWTCPCK.dpl |
| `AbilTypes` relocation — 170→256-entry table, bound `{0,169}`→`{0,255}` | ✅ CONFIRMED WORKING (2026-09-02) | `build_abiltypes_relocate.py` | AoWTCPCK.dpl |

The two id-ceiling scripts are QA-verified byte-for-byte and their triggering symptom ("Shield absent
from the hover popup", "Error during Create Unit List") no longer reproduces, but no session has
recorded an explicit user in-game confirmation of the AI actually *scoring* a high-id ability in
battle — hence `APPLIED, UNTESTED` rather than confirmed, per the status ladder's own rule that only
the user's play earns the green tag.

---

## Adding a new ability — the mechanics

Everything in this section is engine-side and reusable by any future ability, not specific to any one
feature below.

### The registration recipe

Abilities are compiled Delphi flyweight singletons in one global registry: `TAbilityControl` at
`AoWHSSet+0x80` (spells parallel it via `TSpellControl` at `AoWHSSet+0x84`). `RegisterAbility
@0x55750238` parks the object at `TList[id]`, nil-padding as needed, so **the list index *is* the
ability id** and the `Ability.pfs` record id is `id + 10`. A duplicate id raises `'Ability already
registered ('` (string `@0x55750390`), which Delphi surfaces as a bare, unhelpful **`Runtime error
217`** before the main window — nothing in the message names the ability system.

Every shipped ability of this kind is created the same way, and the recipe is small enough to quote
whole (the exact shape every feature below uses, modulo the id/name/mask):

```asm
; entry: EBX = the ability control (true at every splice site inside RegisterPassiveAbilities)
call 0x55750238        ; replay the vanilla call this cave displaced
call $+5                ; PIC anchor -- see the keystone trap below
pop  eax                 ; EAX = this instruction's own runtime address
lea  edx, [eax + (name_blob - anchor)]   ; -> the AnsiString bytes
mov  cx, 0x03FF          ; TAbilitySelectionTypes -- see "the selection-mask trap"
mov  eax, <id>
call 0x5576601C          ; AoWE.CreateEnhancementAbility -> EAX = the ability object
mov  edx, eax
mov  eax, ebx
call 0x55750238          ; TAbilityControl.RegisterAbility
ret
; then the AnsiString literal: FF FF FF FF <u32 len> <bytes> NUL   (refcount -1, LStrAsg shares it)
```

`AoWE.CreateEnhancementAbility @0x5576601C` (byte-identical live and pristine): `EAX` = id →
`[ability+0x0C]`; `EDX` = name AnsiString → `LStrAsg` into `[ability+0x08]`; **`CX`** (the low word of
what's loaded into `ECX`) = the selection mask → stored as a **word** at `[ability+0x20]`; returns
`EAX` = the ability object. This is the *same* field the selection-mask trap below decodes bit by
bit — some sources call it a "category word" because `ListAbilities` also filters enumeration
requests by ANDing a caller-supplied mask against it (e.g. the vanilla Paths all pass `0x37` at
`[0x557BCFC0]`, which is why cloning that value makes a new ability list wherever the Paths already
do), but it is the one `TAbilitySelectionType` set, not two mechanisms. **Do not confuse either of
these with the unrelated `AbilTypes` tactical-AI category *byte*** described further down — that one
lives in a completely different table, in a different binary, and only matters for a *selectable*
ability minted above id 169.

**Splice site.** `PassiveAb.RegisterPassiveAbilities @0x557BC1CC` sets `EBX := Self` in its prologue
and contains roughly 90–149 vanilla `call RegisterAbility` sites (the exact count drops by one per
feature that claims one), every one immediately preceded by `mov eax,ebx` — so `EBX` liveness is
total across the window `0x557BC000`–`0x557BD200`, and any free site works. **Sites already consumed
and never to be reused:** `0x557675C4` (Assassin — outside the window, a *different* registration
function, see below), `0x557BC9E9` (Path of Sand), `0x557BCF04` (Caster Cost, all four), `0x557BCF39`
(Drillmaster), `0x557BCF6E` (Magebane), `0x557BCECF` (Shield — not owned here, see the Magebane
section). Each build script's `check_id_free()`-style scan prints which sites are already repointed;
clone that check into any new script rather than trusting a stale address list, this one included.

**⚠ Two ability-construction factories exist, and only one is usable for a combat-facing passive.**
`CreateEnhancementAbility @0x5576601C` builds a `TEnhancementAbility`, whose raw ability-bit
`GetAbilityEnabled` check is what every combat cave (`CreateStrikeCA`, `CreateRangedAttackCA`, …)
actually tests. The other factory, the strike-factory `FUN_5576727C` (→
`TStrikeEnhancementAbility`), looked like the natural choice for a new strike-conditional bonus
(Assassin was meant to sit alongside Monster Slaying) — but an ability registered through it shows
correctly everywhere in the UI and on the unit card, and its combat-side `GetAbilityEnabled(id)`
call **always returns FALSE**, proven with a `--diag` build that dropped the gate and watched
nothing fire. Register a new combat-facing ability through `CreateEnhancementAbility`, not the
strike factory, unless there is a specific reason to do otherwise (found and fixed during the
Assassin/Slayer work — see Failed approaches).

**Keystone gotcha, load-bearing:** `call $+5` written as *source* assembles to **nothing** — keystone
silently emits zero bytes for it, and the PIC-anchor search then finds whatever earlier `E8` happens
to sit five bytes before a matching `pop` and zeroes **that** instruction's rel32 instead (in one
case, the just-replayed `call RegisterAbility`, which would have called into the middle of the new
cave — a startup crash from an instruction that looks correct in the source). Always emit the raw
bytes `E8 00 00 00 00`, and disassemble every cave with capstone before writing; that is the only way
this class of bug has ever been caught.

**Four registrations in one cave (e.g. the Caster Cost abilities) must recompute the anchor per
ability**, not reuse one value: `mov eax, <id>` destroys `EAX` between registrations, and
`RegisterPassiveAbilities`'s prologue pushes only `EBX`, so `ESI`/`EDI` are not safe parking either.
Six bytes of anchor per ability, zero cross-registration register-lifetime assumptions.

### Picking a free id — measure it, never quote it

**⚠ Any documented "free band" goes stale the moment another feature registers an id**, and it has
gone stale repeatedly and silently in this project's own history: `0xAA`, then `0xAB`, were each in
turn documented as "the first free id" and each was wrong within days once the next feature landed;
`0xB0` (Shield), `0xB1` (Reforming Flesh) and `0xB2` (Embrittled) — none of them owned by this file —
kept shrinking the same band further still, one of them (`0xB0`) appearing mid-session during this
file's own Caster Cost work with no advance notice in any doc. A stale id collides, and a collision
is a bare `Runtime error 217` before the main window, with nothing naming the ability system.
**The only safe procedure is dynamic, on every run, from at least
two independent sources**, exactly what `build_scripts/build_drillmaster.py`'s `check_id_free()`
does — clone it into every new script rather than trusting a number written in any doc, this one
included:

1. Scan the DLL for `mov eax,<id>; call CreateEnhancementAbility` (catches every
   `TEnhancementAbility`-style registration, including all of the features in this file).
2. Scan `Release/Ability.pfs` record keys (`key = id + 10`).
3. Cross-check with `re_tools/ability_names.py`'s **constructor** scan, which catches
   **class-based** registrations the `mov eax,<id>` idiom above misses entirely (66 ctor-derived
   ids as of the last count) — this is the one the other two scans cannot see, so skipping it has
   previously undercounted usage.

**Why a "static sweep of apparent gaps" is fiction, not a shortcut.** A sweep of constructor
immediates plus `CreateEnhancementAbility` call-site arguments recovers ids `0x01`–`0xA9` and *looks*
like it proves ~116 free slots below the hard ceiling. It is a **lower bound only**: it provably
missed real vanilla ids (Tunneling `0x2A`, Monster Slaying `0x70`, Life Stealing `0x76`, and the
mod-added Path of Sand `0x9F`), and it produces false positives too (`0xFA` matches the constructor
byte pattern but is unrelated city-AI code, not an ability). **The only trustworthy test for an
apparent gap is dynamic** — register it and watch for the `"Ability already registered"` assert.
`0x38` (Assassin) and `0x9F` (Path of Sand) were claimed exactly this way.

**Measured 2026-09-25, for orientation only — re-derive before trusting it:** highest id in use
`0xBC` (Commanding). Verified remaining nil slots below the vanilla top (`0xA9`): `0x21, 0x4E`–`0x55, 0x5B,
0x66`–`0x69, 0x6E, 0x85`–`0x87, 0x97` (19 gaps; a nil registry slot is necessary but not sufficient —
per-id verification means scanning both binaries for `mov edx,<id>` / `push <id>` feeding an ability
call, since cut content can still reference an id that nothing currently registers). Free above the
current max, under the hard ceiling described next: `0xBD`–`0xCD` (17 ids). Roughly **36 stateful
slots** and, if the untested bit-only band below turns out to be sound, another **50 passive** slots
— that is the shape of the budget, not a number to bank on unchanged.

**The hard ceiling — corrected.** The original derivation called `id ≤ 0xCD`
(205) a **save-format** limit. That is false, and the correct mechanism matters because it changes
what "untested" means here: `Engine.TPropertyTable.SaveToStream @0x5550FD0C` (`Enginep.dpl`) tests
`tag > 0x7F` or `offset > 0xFF` at `0x5550FD32` and, when either is true, writes a **wide** `(u32
tag, u32 offset)` entry instead of the narrow one, flagging the record header with `or al, 0x80`.
`Release/Unitres.pfs` already round-trips wide keys past `0x11D` in the wild — **the container
format itself has no id ceiling**. What actually produces `0xCD` is narrower and more local:
`TAbilityOwner.ReadWrite @0x5574F318` serialises each per-owner ability-*data* record (the kind
multi-level/stateful abilities like Leadership or Spellcasting carry) under a property tag computed
as `0x32 + abilityID` (`add eax, 0x32 @0x5574F484`), and that computed tag is what gets compared and
stored as a byte *within this one function*, independent of the generic wide-encoding escape. So
`0x32 + id ≤ 0xFF ⇒ id ≤ 0xCD` is real, but it is a **convention specific to
`TAbilityOwner.ReadWrite`**, not a property-table format limit — and **nothing above `0xCD` has
actually been run in-game**, so treat that band as *untested*, not proven-safe, in either direction.
Verified empirically against a real owner's property table in `Release/Unitres.pfs` (file offset
`0x87C`): `05 | 02 00 | 03 04 | 31 0a | 52 1a | 60 26` decodes as `count, (tag,offset)×5`, with tag
`0x52` = id `0x20` (Marksmanship) and tag `0x60` = id `0x2E` (Leadership) — `0x32 + id` confirmed on
two known ids.

**What is NOT the limit — everything else auto-grows:** the registry itself (`GetAbility
@0x557501C0` is a bounds-checked `TList`, `RegisterAbility` grows it and nil-pads); the per-owner
ability *bitset* (`SetAbSet @0x5574E0BC` auto-grows on `id >= count`, asserting only against
`0x7FFFFFF`); the bitset's own serialisation (count under tag 2, bits under tag 3 as raw
`(count+7)/8` bytes, width scales with the highest id set). Consequence: a **bit-only** passive
(no per-owner data record — every feature in this file except the multi-level abilities in
`02-abilities-modded.md`) is not bound by the `0xCD` figure *in principle*. It is untested above
`0xCD` regardless; a full save/load round trip (and an MP sync test if relevant) is the thing that
would settle it, and as of this writing nobody has run one.

**Recommended range for a new stateful ability today: `0xB3`–`0xCD` (27 contiguous ids)**, above
everything registered and under the hard ceiling. This shrinks by one every time any feature —
inside or outside this file — claims an id; re-measure, do not quote it even from this paragraph.
Freeze the chosen id before shipping: ids are serialised into saves as bitset indices and every MP
peer must run byte-identical binaries.

### The tactical-AI / UI ceiling — a second, independent constraint

This is unrelated to the `0xCD` save-tag ceiling above; it governs whether an id is *visible and
usable in tactical combat*, and it bit this project in-game on 2026-09-01.

Vanilla's highest ability id was `0xA9`, so every "iterate ids 1..N, ask `GetAbilityEnabled`" loop
in `AoWTCPCK.dpl` and `AoWz.exe` was written with the terminator `cmp <counter>, 0xAA` — exactly big
enough, never revisited. Seven such loops exist across the two binaries (nine sites counting
`AoWzCompat.exe`'s lockstep copy): four `TCAI.EvalBattle` battle-scoring scans, the in-combat unit
panel (`CreateTCAbList`), and the item-banner and unit-hover popups. **`build_tcablist_ceiling.py`**
raised the panel's terminator alone (diagnosed 2026-08-27 from the user's report that Shield was
missing from the embedded in-combat card while present in the full Unit dialog);
**`build_abilityid_ceilings.py`** raised the other six. Both recompute "highest registered id + 1"
from the live data on every run and abort if their target has drifted, so **append** to each
script's `LADDER`, never replace the prior value — the ladder is also the verify-before-write
whitelist that makes a bump an in-place rewrite instead of a revert-and-reapply this project
deliberately does not have. *Both scripts' `LADDER`s must move together and stay on the same value.*

**The symptom when this ceiling is missed, so it is never re-diagnosed from scratch:** the ability
**works perfectly** — it registers, it fires its effect, it appears in the full Unit dialog and the
hero level-up dialog (both derive their bound from `GetCount`, not from a hard-coded immediate) —
and is simply **absent from the in-combat panel, the banner popups, and invisible to the tactical
AI's battle scoring.** "Works but is listed nowhere" is this ceiling, every time, and it is silent —
no crash, no error.

**⚠⚠ The crash this project actually shipped was the opposite failure mode, and the two must not be
conflated.** `AoWTCPCK.dpl`'s `AoWTC.AbilTypes @0x00467248` is a genuinely bounds-checked 170-byte
table (hardware `BOUND eax,(0,169)` at 15 sites) holding one AI-category byte per ability id
0–169. `build_abilityid_ceilings.py` raised the four `EvalBattle` scan-loop terminators to `0xB3`
on the theory that "our ids are safe above the vanilla bound because they are `TEnhancementAbility`
and so never become *selectable*". **That reasoning is true of the map-click selection path and
false of these four AI scan loops** — there is no `GetControlType` gate anywhere between the
enabled-test and the `bound` inside `TCAI.EvalBattle`:

```
0041870D  mov  edx, [ebp-0x14]      ; the ability id, the raised counter
00418715  call [ecx+0xA8]           ; GetAbilityEnabled(id)
0041871B  test al,al / je next      ; not enabled -> skip
00418723  cmp  [ebp-0x14], 0x34     ; the ONLY other test on the path
...
004188E9  bound eax, [0x41B03C]     ; {0,169} -- reached by ANY enabled id
004188EF  cmp  byte [eax+0x467248], 0
```

So any unit carrying an enabled ability with id 170–178 (Magebane `0xAA` through Embrittled `0xB2`)
crashed the scan with `#BR`, which Delphi turns into a range-check error and the caller swallows
into the modal **"Error during Create Unit List"** — observed in game 2026-09-01, on an AI turn
with priest heroes present, and reproduced with an unrelated same-day feature reverted to rule it
out as the cause.

**The fix, `build_abiltypes_relocate.py` (✅ CONFIRMED WORKING 2026-09-02):** copies `AbilTypes` to a
new **256-entry table at `0x00469440`** (ids 0–169 verbatim, 170–255 zeroed), repoints all **13**
references (12 direct `[reg+disp32]` displacements plus one pointer cell, all `.reloc`-covered, plus
the DLL's own `.edata` export entry, which carries no `.reloc`), and widens all **nine** distinct
`{0,169}` limit words to `{0,255}`. The old table at `0x00467248` is left byte-identical and simply
unreferenced, so the change stays reversible and anything a census might have missed keeps vanilla
behaviour. **Chosen over a widen-in-place fix deliberately**: `AbilTypes` ends at `0x004672F1` and
`AoWTC.SpellTypes` begins at `0x004672F4`, with two bytes of `8B C0` alignment padding between them.
A widen-only fix reads straight through that padding and into `SpellTypes`: measured against the
pre-patch file, id `0xAA` (Magebane) would have read padding byte `0x8B` (139) and `0xAB`
(Drillmaster) `0xC0` (192) as its AI category — both **nonzero**, i.e. both would have cleared every
`cmp cat,0` gate in the engine and been scored as attack actions of an undefined kind, and `0xB6`
would have reached real `SpellTypes` data. Relocating was necessary, not tidy.

**⚠⚠ The relocation and the ladder raise are an atomic, ordered pair, in both directions.** Raising
the AI-scan ladder *without* the relocation is strictly worse than the crash it removes — it drives
ids straight into six `BOUND` sites instead of failing safe. `build_abilityid_ceilings.py --undo`
therefore refuses while `build_abiltypes_relocate.py` is not applied (it would restore ladder terminators past `0xAA`
with the table still at 170 entries), and `build_abiltypes_relocate.py --undo` refuses while the AI
ladder still scans past `0xAA` (it would restore the 170-entry table under loops still reaching
`0xB2`). **Apply order: relocate `AbilTypes` first, then raise the ladders. Undo order: lower the
ladders first, then the relocation.**

**⚠⚠ "The bound no longer blocks the id" is only half of "the ability works above 169".** Every
entry from 170 up in the new table is category **0**, which is **inert at every one of the fifteen
consumers** — deliberate (it reproduces pre-crash behaviour for the passives that exist today) but
not a blank cheque for a *new* selectable ability. A selectable ability minted at id ≥ 170 would be
admitted everywhere and then do nothing usable: the AI still skips it in every `EvalBattle` read,
`TRangedPathHS.Show` draws no path, and clicking it on the map calls `SelectAbility(-1)` and
**deselects it on the spot**:

```
0041EC66  mov  al, [eax+0x469440]   ; the category byte
0041EC72  sub  al, 1
0041EC74  jb   0x41EC7F             ; CF set <=> category == 0
0041EC7F  or   edx, 0xFFFFFFFF      ; -1
0041EC85  call 0x00422F0C           ; TTacticalCombatUnitHS.SelectAbility(-1) = DESELECT
```

⇒ **After minting a selectable ability at any id ≥ 170, set `[0x00469440 + id]` to its real
category** — the live table uses `1/2/3/5/7/11` for the various attack categories and `4` for
touch/command (decoded from the consumer's own test shape: `sub al,1; jb` ⇒ 0, then `sub al,3; je`
⇒ 4). None of the features in this file need this — Path of Sand, Assassin, Drillmaster, Magebane
and the four Caster Cost abilities are all plain `TEnhancementAbility` passives whose
`GetControlType` returns 0, so they were never selectable and never reached this bound at all, on
either side of the relocation. It applies only to a *future* selectable ability above id 169.

**If a new ability should draw a persistent overhead status icon** (the crossed-swords/skull-style
marker over a unit, not the level-up dialog or the unit card), that is a *third*, unrelated
mechanism: `TAbstractUnit.ShowEx @0x557812EC` draws status icons only for a **hard-coded chain** of
explicit `if GetAbilityEnabled(unit,id) then ShowLooped(...)` blocks, in this fixed order: `0x60,
0x62, 0x5D, 0x91, 0x04, 0x30` (Seduced), `0x96` (Dominated), `0x95` (Charmed), `0x61, 0x5C, 0x5F,
0x5E, 0x7F, 0x6B` (Possessed), `0x22` (Turned Undead), `0x46`. An ability absent from this chain
draws no overhead icon, however good its data or its `Ability.pfs` record — the `.pfs` tag-8 image
sequence is only the *supply*, this chain is the sole *consumer*. Adding a slot means a `call
rel32`-retarget cave hooked at the function's epilogue (`0x55781A2E`); the worked example is a
different feature's `cave_ankh` (`build_turnundead_evilcommand.py`, not owned in this file).

**So: beyond a free id and registration, a new ability may additionally cost** an `Ability.pfs`
record (minted by a DevEd assign-and-save round trip, key = id + 10 — no build script can create
one, see the level-up-cost section below); if it is selectable and minted above id 169, a category
byte in the relocated `AbilTypes` table; and if it should draw a persistent status icon, its own
block in the `ShowEx` chain. None of these apply to a plain passive below id 170.

### Ability *levels* are a different resource from ability *ids*

A recurring scoping question: does raising a multi-level ability's cap (Leadership I→IV, Dispel
Magic III→V) eat into the id budget above? **No — a level is a byte inside the ability's existing
per-owner data record, not a new id.** `TMultiLevelAbility.Expand @0x55765378` is the whole model:
the first time an owner gets the ability, a data object is created holding the ability id at
`+0x0E` and the level (starting at 1) at `+0x0C`; on a later level-up the level byte is simply
incremented in place. No extra registry slot, no extra bitset bit, no extra save property tag
(§ above's `0x32+id` is per *id*, not per level) — the level serialises as tag 10 of
`TMultiLevelAbilityData.ReadWrite @0x55765124`, inside the record that already exists, so raising a
cap is save-compatible by construction.

What a level costs is local to the one ability: the **cap** lives at `ability[+0x28]`, a dword set
in that ability's own `Create` (base `TMultiLevelAbility.Create @0x55765168` defaults it to 4) — but
**not every levelled ability uses this field**: Dispel Magic ignores `[+0x28]` entirely and
hard-codes a `cmp` against 3 in *both* `CanExpand @0x5576D163` and `Expand @0x5576D1D0`, keeping its
own level at `+0x0D` rather than the base class's `+0x0C` (which on that class is a per-turn enabled
toggle instead). **Always find the real cap by reading `CanExpand`/`Expand`, never by assuming the
base-class field is honoured.** The **per-level skill-point cost** lives at `ability[+0x2C]`, a
`TIntegerList` read by `ExpandCost @0x557652E4` as `costList[currentLevel+1]` — it must be populated
up to the new cap or levelling reads past the end. The **per-level effect data** (e.g. Leadership's
atk/def bonus tables) is usually the real constraint in practice, since such tables are often
fixed-size in DATA; relocating them to fresh DATA space is the standard fix. Two confirmed worked
examples: Leadership's cap raised 1→4, and (Inioch's) Dispel Magic 3→5 — the fact that Leadership's
feature worked with only `Create` changed is the empirical proof that **the code-side cap is
authoritative** and `Ability.pfs` does not override it the way it overrides the selection mask below.

### Level-up cost — two sources, decided by the ability's kind

This is a distinct number from the per-level skill-point cost above: it is the **hero level-up
dialog's point cost to acquire the ability at all** (or its first level), and which mechanism sets
it depends entirely on what kind of ability it is:

| kind | level-up cost lives in |
|---|---|
| **multi-level** (Leadership, Marksmanship, Dispel Magic, Spellcasting, …) | **code** — the class overrides `ExpandCost`. `TDispelMagicAbility.ExpandCost @0x5576D130` is literally `return 5`; `Ability.pfs` tag 6 is not even read for these. |
| **single-level / bit-only** (every feature in this file) | **`Ability.pfs` tag 6.** They all inherit the base `TAbility.ExpandCost @0x5574E908` = `return [ability+0x14]`. |

**For a bit-only ability, the registration cave's `mov dword ptr [ability+0x14], N` cannot set the
in-game cost, and this was found the hard way**: the four Caster Cost abilities shipped with their
cave writing 20/40/40/40 into `+0x14` at registration, and all four read as **0** (i.e. free) in
game until tag 6 was authored by hand in DevEd afterwards. The mechanism: `TAbility.ReadWrite
@0x5574F07C` hands the property reader the **address** of `[ability+0x14]` for tag 6 —

```c
(**(code **)(*tbl + 0x2c))(tbl, ability + 0x14, 6);   // reads INTO [ability+0x14]
```

— and that read runs **after** registration, on **every registered ability, whether or not the file
holds a record for it**. `TAbilityControl.ReadWrite @0x55750164` walks the ability list by index and
calls `rwEObject(ability, tag = index + 10)`; `TEReadStorageStream.rwEObject @0x555116B0` finds no
such tag, skips only the sub-stream open, and **still** calls `MainReadWrite → [VMT+0x18] =
TAbility.ReadWrite`. So `rwInteger` runs for tag 6 with nothing to read:

```
55510F08  cmp esi,-1              ; TPropertyTable.FindOffset(tag 6) said "absent"
55510F0B  je  0x55510F39
55510F39  xor eax,eax
55510F3B  mov dword ptr [edi],eax ; *** THE FIELD IS EXPLICITLY ZEROED ***
```

⚠⚠ **A MISSING TAG IS NOT "LEAVE THE FIELD ALONE" — FOR TAG 6 IT IS "WRITE THE DEFAULT", AND THE
DEFAULT IS 0.** The data file therefore wins **unconditionally**, not merely once a record exists,
and **no registration-time store of `[ability+0x14]` can ever survive**. `THero.UsedSkillPoints
@0x55786CC8` sums `ExpandCost` across an owner's abilities, so this is not a display glitch: the
ability is **permanently free** to take.

⚠ **THE TWO ADJACENT TAGS BEHAVE OPPOSITELY, WHICH IS WHY THIS LOOKS IMPOSSIBLE FROM THE SYMPTOM.**

| tag | primitive | missing tag does |
|---|---|---|
| 6 — `FExpandCost` | `rwInteger @0x55510EF4` | **zeroes the field** |
| 9 — selection mask | `rwData @0x5551128C` | `je` to the epilogue, **buffer untouched** |
| 5 — description | `rwStrings @0x555111F4` | passed by value; constructor's default stands |

So a record-less ability keeps the mask its cave registered — it *is* offered at hero level-up —
and loses the cost its cave registered. Offered, and free. That is exactly what Reforming Flesh
(`0xB1`) did for ten days; see its section below for the fix, which is a hook in
`TAbility.ReadWrite` **after** the tag-6 read, not a bigger store at registration.

**A build script CAN mint an `Ability.pfs` record** — `build_commandedundead_pfs.py` mints records
146 and 147 (abilities `0x88`/`0x89`) and removes them again on `--undo`, and `build_vision9.py`
does the same class of length-changing write. It is the riskiest data operation in this project
(every later record offset shifts and the CRC must be repaired), so it is not the default answer;
`build_drillmaster.py`'s abort message still describes the cheap route: *"ABORT: Ability.pfs has no
record %d for ability %#04x. Assign the ability to something in AoWDevEd and save, so the editor
creates one."*

⚠⚠ **AND THE DevEd ROUND TRIP CAN GO TO THE WRONG TREE, SILENTLY.** No editor binary in this
install carries the registry-isolation patch — neither `Ziggurat\AoWDevEd.exe` nor
`Ziggurat\AoWzEd.exe` contains the string `Age of Wonders Z` — so each resolves its startup
directory from `HKCU\Software\Triumph Studios\Age of Wonders` and reads/writes
**`<root>\Release\`**, while the game reads `Ziggurat\Release\`. Measured 2026-09-10: an editor
session minted all **13** mod-ability records (66, 146, 147, 169, 180–188), tag 6 and all, into
`<root>\Release\Ability.pfs` — the vanilla data root — where nothing loads them. The symptom is
"the editor silently refused my edit"; the reality is that it saved perfectly, somewhere else.
**Check the file's timestamp before believing an edit landed.**

### The selection-mask trap

`CreateEnhancementAbility(id, name, X)`'s third argument is **not an icon index** — every feature in
this file's own history got this wrong at least once before decoding it. It is a
`TAbilitySelectionType` **set**, stored as the word at `[ability+0x20]`, named from the live Delphi
RTTI enum (`tkEnumeration` at file offset `0x826C`/VA `~0x55708E6C`, members from file offset
`0x8291`):

| bit | | bit | |
|---|---|---|---|
| `0x001` astUnit | `0x002` astHeadItem | `0x004` astTorsoItem | `0x008` astAttackItem |
| `0x010` astDefenseItem | `0x020` astRingItem | `0x040` astUseItem | `0x080` astCustomizeLeader |
| `0x100` astHeroUpgrade | `0x200` astEditor | | |

**The hero level-up dialog demands *both* of the top two bits, tested in two different places** —
which is exactly why half a correct-looking mask still silently fails:

- `TAbility.CanExpand @0x5574E8B8` first checks the owner's **self-only** ability set
  (`owner->vmt[0x4C] GetAbSet(id)` — so a hero wearing an *item* that grants the ability is still
  offered it at level-up only if the item-aware bit is also considered further down), then ANDs
  `[ability+0x20]` against `owner->vmt[0x8C] GetAbilitySelectionTypes()`; `THero`'s override
  (`@0x55786B10`) returns the fixed word `0x0200` (**astEditor**).
- The dialog's own fill loop, separately, tests `astHeroUpgrade` (`0x100`) directly.

A mask with `astHeroUpgrade` set and `astEditor` clear (`0x0137`, an early Drillmaster build)
registers fine, is assignable in DevEd, shows correctly on the unit card, and grants its effect
correctly — and is **never offered at hero level-up**, because it fails the second, independent
gate. **Use `0x03FF`** (all ten bits — what 80 of the 101 vanilla level-up abilities carry, and what
every feature in this file ships with) unless an ability is deliberately meant to be unavailable in
some context.

⚠ **`Release/Ability.pfs` tag 9 overwrites whatever mask the cave passed, once a record exists** —
`TAbility.ReadWrite` loads tag 9 into `[ability+0x20]` *after* registration, and measured across all
21 vanilla `CreateEnhancementAbility` sites, **0 of 21 agree with their own data file**. For a
brand-new id with no record yet, the cave's mask stands (`TPropertyTable.FindOffset @0x5550FE70`
returns −1 and the reader skips); the moment a DevEd round trip creates the record, re-verify tag 9
survived as intended. A heuristic seen elsewhere in this project's tooling, `(mask & 0x80) and (mask
& 0x100)`, happens to select the same 96 vanilla abilities as the real test — because every stock
ability with `astHeroUpgrade` also happens to carry `astCustomizeLeader` — but the bit the engine
actually tests is `0x200`, so the heuristic silently mislabels any *new* ability that doesn't
happen to share that vanilla correlation. Test `0x100 | 0x200` directly, never the `0x80` proxy.

### Two ability-query APIs — check which one before hooking any consumer

Every unit/hero class exposes **two parallel families** of ability accessors, and picking the wrong
one is how an ability registers, assigns and displays correctly and then simply never fires:

| | self-only | item-aware |
|---|---|---|
| ability set | `+0x4C` GetAbSet | `+0x14C` GetAbilitySet |
| count | `+0x54` GetAbCount | `+0x158` GetAbilityCount |
| level | `+0x84` GetAbLevel | `+0x144` GetAbilityLevel `@0x5578831C` |
| enabled | `+0x88` GetAbEnabled | **`+0x148` GetAbilityEnabled `@0x5578827C`** |

`+0x148` on `THero` chains self (`TAbstractUnit.GetAbilityEnabled @0x5577F5E0`) → equipped items
(`THeroItems @0x55786674`) → the itUse inventory bag (`THeroInventory @0x55786154`) — so querying
through it means an ability-granting item works for free, with no extra code. **Use the item-aware
pair (`+0x144`/`+0x148`) for any strategic/hero-facing ability consumer** unless there is a specific
reason an item should not be able to grant the effect. `TAbstractUnit` and `TUnit` both hold
`0x5577F5E0` in the same `+0x148` slot, so it is equally safe for plain unit casters, not just
heroes.

**⚠ Never hand a `TCombatUnit` (or `TFastCombatUnit`) to `+0x148` directly** — their VMTs are
shorter and the read lands past the end, in class-name/RTTI data, not a function pointer:

| class | VMT | `+0x148` resolves to |
|---|---|---|
| `THero` | `0x55711FEC` | `0x5578827C` `THero.GetAbilityEnabled` |
| `TLeader` | `0x55712238` | `0x5578827C` |
| `TUnit` | `0x55710CAC` | `0x5577F5E0` `TAbstractUnit.GetAbilityEnabled` |
| `TAbstractUnit` | `0x55710740` | `0x5577F5E0` |
| `TAdjustableUnit` | `0x55712A54` | `0x5577F5E0` |
| `TWallUnit` | `0x55712C84` | `0x5577F5E0` |
| ⚠ `TCombatUnit` | `0x55715A94` | `0x55715BE0` — **past the end of the VMT, an RTTI blob** |
| ⚠ `TFastCombatUnit` | `0x5571D4BC` | `0x74696E55` — **the ASCII bytes `'Unit'`** |

On the combat side, the correct forwarder is `TCombatUnit.GetAbilityEnabled @0x55725004` at combat
`VMT+0xA8`, which internally bridges to the strategic unit via `[combatObject+0x4C]` (nil-guarded)
and lands on the item-aware query for you — every combat-facing cave in this file's features
(Assassin's melee/ranged blocks, Magebane's enchantment count) reaches enchantments and abilities
this way, never through `+0x148` directly. `GetAbilityEnabled` is also **not cheap** — two nested
virtual calls plus a linear registry search — so classify what you're checking first and query
once per evaluation, not once per candidate; a cost-cave or damage-cave that queries three times
where one classify-then-query would do is three times the cost inside a function the AI may hammer
in an affordability or scoring loop.

---

## Path of Sand — new terrain-drying passive (`0x9F`)

**✅ CONFIRMED WORKING in-game (2026-07-08).** `build_scripts/build_path_sand.py`. The first
from-scratch ability in this project, and the recipe every later one above was validated against.

A moving unit carrying Path of Sand dries the terrain it crosses toward Desert, using the same
progression as the user's Desiccate spell — a 4th Path alongside vanilla Life (`0x45`) / Decay
(`0x44`) / Frost (`0x6D`). Footprint: inner disk 100%, 25% proc on the outer ring (radius 2),
identical to the other three Paths.

**Terrain progression** (read-once per proc, no cascade; Desert is terminal): `Grass(1)→Steppe(4)`,
`Snow(3)→Grass(1)`, `Steppe(4)→Desert(2)`, `Wasteland(5)→Desert(2)`, `Dirt(C)→Steppe(4)`. Cloned into
Sand's own `cave_sand_cb`, deliberately **not** calling Desiccate's original function
(`FUN_5580c001`), so that retuning or reverting Desiccate can never silently change what Sand does —
mirror any future Desiccate retune here by hand.

**Registration** repoints the Path-of-Frost `RegisterAbility` call `@0x557BC9E9` to `cave_sandreg`,
which replays Frost's own registration first, then creates and registers Sand with selection mask
`0x37` (the same word the vanilla Paths pass — this is what makes `ListAbilities` enumerate Sand
wherever the Paths are already listed, since `[ability+0x20]` is what that enumeration filters by;
see the selection-mask trap in the general mechanics section for the full bit decode).
**Behaviour** hooks `TAbstractUnit.MovedTo @0x55780328` at `0x557804B7` — the `mov edx,0x6D` that
starts the vanilla Frost check, reached for every non-transported move — so Sand becomes an
independent 4th branch that replays the displaced instruction and falls into Frost's own check
afterwards.

**Cave map:** `cave_sand_cb @0x5580DF00`, `proc_sand @0x5580DF40`, `cave_sanddispatch
@0x5580DFA0`, `cave_sandreg @0x5580E000` (name literal `@0x5580E02C`).

**⚠ Dependency, and the revert order it forces.** `proc_sand` reuses `build_path_outerring.py`'s
`cave_stash` (BSS scratch at `0x558FA800`, the move's centre x/y) and its outer-ring gate; the build
aborts if that mod's stash hook at `0x5578041E` is not present. **Revert order: undo Path of Sand
before undoing the outer-ring mod, never the other way round.** Separately, `build_path_sand.py`
does nothing to make Sand fire on transported units — that fix (a shared vanilla gate, see below) is
a different script's job and covers all four Paths at once.

**Icons: none, by design, not a gap.** Abilities have no icon anywhere in AoW1's UI (text only);
`RegisterAbility` does call `LinkToIL(ability+0x1C)` and build an empty image-sequence list, but
nothing ever draws it for an ability (contrast `TSpell+0x2C`, the mirror-shaped field that *is*
drawn). Don't chase icon binding for a new ability — there is nothing on the other end.

### Failed diagnosis, kept because the wrong theory is genuinely tempting

The very first build (id `0xB0`, before `0x9F` was chosen) registered, listed and was assignable in
DevEd — and then did **nothing** in-game. The width-checked unit ability bitset
(`TAbstractUnit.GetAbilitySet @0x5577F618` = `if id < unit+0xC: bit(id) else 0`) looked like a hard
cap at the vanilla-era count, and would be the obvious thing to blame. **It was not the cause, and
is not a cap at all** — the setter `SetAbSet @0x5574E0BC` auto-grows on any `id >= width`, so a high
id was never the problem; DevEd persists them fine. The two *real* causes, found with a `--diag`
build that dropped the ability-enabled gate entirely and watched every unit terraform: (1) the test
unit had the Transport ability, and `MovedTo` gates **every** Path — vanilla's Life/Decay/Frost
included — behind "does this unit's army have a transporter", vanilla behaviour Sand simply
inherited; (2) the test map was desert/lava-themed, and Desiccate's mapping is a no-op on
Desert/Lava/Water/Ice by design. Both had to be fixed (or ruled out as vanilla-consistent) before
the ability's actual effect was visible at all. **Fixed for all four Paths** (not just Sand) by a
separate script that zeroes the transport-block result specifically when the transporter found *is*
the moving unit itself, so the transporter leaves a trail while its passengers stay blocked —
confirmed working in-game the same day. Kept here because "assignable but does nothing" will look
like an id problem again to the next person who hits it, and it usually will not be one.

---

## Assassin (Hero Slaying) and the ranged slayer extension

**✅ CONFIRMED WORKING in-game (2026-07-08), both phases.** Idea credit: fellow modder Inioch.
Phase 1 — `build_scripts/build_assassin.py`. Phase 2 — `build_scripts/build_ranged_slayers.py`.

**Assassin (id `0x38`)** is a new melee/ranged bonus keyed on the target's built-in hero-ness rather
than a marker ability — the same "alignment-keyed" shape vanilla already uses for Holy/Unholy
Champion, just keyed on class instead of alignment. Hero detection needed no new marker:
`underlying = *(combatTarget+0x4C); IsClass(underlying, THero)`, which **must** be preceded by
`IsClass(combatTarget, TCombatUnit)` (`THero` classref cell `0x55711FAC`, `TCombatUnit` classref
cell `0x55715A54`, `IsClass @0x557010C0`).

**Registered via `CreateEnhancementAbility`, not the strike factory** — see the general mechanics
section above for why the other factory silently disables the combat check. Cave `cave_asnreg
@0x5580E0E0` repoints the last strike `RegisterAbility` call `@0x557675C4`.

**Melee bonus: +5 ATK / +5 DAM per matching bonus, uniform with Monster Slaying and the Champions**
(a 2026-08-24 re-grade alongside the general DAM/HP doubling pass; the design notes that shaped the
feature originally proposed +3/+3, superseded — the live cave constants are `MELEE_ATK_BONUS=5`,
`MELEE_DAM_BONUS=5`). **Ranged/breath bonus: +2 ATK / +2 DAM per matching bonus**, uniform across
all four slayer-style bonuses (Assassin, Monster Slaying, Holy Champion, Unholy Champion) — live
constants `RANGED_ATK_BONUS=2`, `RANGED_DAM_BONUS=2`. Both stack per matching bonus and are
uncapped.

### KEY FINDING — melee has TWO parallel strike-creation tables, and a conditional-attack mod must hook both

The single most reusable piece of RE from this feature: AoW1's melee "vs-type" bonuses (Monster
Slaying, the Champions, now Assassin) are duplicated across **three** functions, and which one a
given attack reaches depends on *how the attack was delivered*, not on anything about the ability
itself:

| function | reached by | operates on | Assassin cave |
|---|---|---|---|
| global `CreateStrikeCA @0x557665E4` (block `@0x557666A1`) | Round Attack, attacks-of-opportunity, ability strikes (Possess/Web/…) | combat objects, `GetAbilityEnabled` at `VMT+0xA8` | `cave_melee @0x5580E070` |
| `TMeleeRound.CalculateStrikes @0x55767B24` (block `@0x55767C5C`) | the **deliberate** melee attack, both the attacker's strike and the defender's retaliation | combat objects, same `VMT+0xA8`, alignment `VMT+0x90` | `cave_melee3 @0x5580E120` |
| `TMeleeRound.CalculateUnitStrikes @0x557677CC` (block `@0x55767904`) | `CalculateFreeUnitSwing` / `CalculateUnit` — the opportunity/combat-*predictor* path only | **strategic** units, `VMT+0x148`, alignment `VMT+0xFC` | *not hooked — see below* |

Both hooked caves reach enchantments/abilities via the item-aware forwarder at combat `VMT+0xA8`
(never `+0x148` directly, per the general mechanics section), and reach the target hero through
`guard_hero` in the shared cave — `IsClass(target, TCombatUnit)` **first**, then `*(target+0x4C)`,
then `IsClass(·, THero)`. ⚠ A null guard alone is NOT enough; see the next subsection.

### ⚠⚠ KEY FINDING — `combat + 0x4C` on a WALL is garbage, not nil. Fixed 2026-09-11.

🔨 **APPLIED, UNTESTED (2026-09-11).** Root-caused from a live in-game capture, not from analysis.

**Symptom.** Attacking a walled enemy structure with any Assassin carrier (Orc Assassin, Shadow)
raised, via the `build_te_exception_detail.py` diagnostic:

```
Exception EAccessViolation in module VCL30.dpl at 00003A18. Read of address 00002802.
```

then, on the next combat attempt, `Exception in module AoWEPACK.dpl at 000787AE. Combat already
created.` ⚠ **The second dialog is fallout, not a second bug**: the AV aborts the turn execution,
the half-built combat is never torn down, and `TAoWHSMap.CreateCombat @0x557787AE` then trips its
own guard and the armies are lost. Do not chase it.

**Why `0x2802`.** The class tree, walked live from the VMTs:

| class | VMT | instsize | `+0x4C` is |
|---|---|---|---|
| `TCombatObject` | `0x557158EC` | `0x4C` | *nothing — the object ends here* |
| `TCombatUnit` | `0x55715A94` | `0x5C` | the strategic unit pointer |
| `TFastCombatUnit` | `0x5571D4BC` | `0x64` | inherited (auto-resolve) |
| `TCombatWall` | `0x55715C40` | `0x50` | **packed data**: `+0x4C` wall type, `+0x4D` wall HP |

`TCombatWall` is a **sibling** of `TCombatUnit`, not a descendant. A Ziggurat stone wall (type 2,
HP `0x28` = 40) therefore reads back as the dword `0x00002802` — small, non-zero, and so a
`test eax,eax` nil guard passes it straight through.

⚠⚠ **`System.@IsClass` is nil-safe but NOT garbage-safe — and its entry is `0x41303A14`, not the
`0x41303A18` the dialog names.** The export `System.@IsClass` resolves to RVA **14868 = `0x3A14`**,
and the `ret` at `0x41303A13` ends the previous function:

```
41303A14  85 c0      test eax,eax        <- ENTRY: nil test
41303A16  74 10      je  0x41303A28      ;  -> ret with EAX==0, so AL==0
41303A18  8b 00      mov eax,[eax]       ;  @@loop -- the reported fault address
41303A1A  39 d0      cmp eax,edx
41303A1C  74 08      je  0x41303A26
41303A1E  8b 40 e8   mov eax,[eax-0x18]  ;  vmtParent, a PPClass
41303A21  85 c0      test eax,eax
41303A23  75 f3      jne 0x41303A18      ;  back-edge into @@loop
41303A25  c3         ret                 ;  EAX==0 here, so AL==0
41303A26  b0 01      mov al,1
41303A28  c3         ret
```

So `IsClass(nil, C)` returns **False** safely. What it has no test for is a **non-nil pointer that
is not an object** — it goes straight to `mov eax,[eax]` to read the VMT. **The defect class here
is a garbage object pointer, not a nil one.** ⚠ `0x41303A18` is the **loop body** and the back-edge
target of the `jne` at `0x41303A23`, which is both why a fault gets reported there and why an
earlier attempt to hook this function's entry died with runtime 216 — the back-edge lands inside
the displaced bytes.

The shared guard still nil-checks before calling `@IsClass`, deliberately: it lets the caller test
one result instead of leaning on a convention that reads as undefined at the call site, and it is
the house pattern `build_replaylog.py` / `build_combatlog_dll.py` / `build_ranged_slayers.py`
already use. (vmtParent at `VMT-0x18` holds a *pointer to a classref cell*, which is why the walk
loops back onto `mov eax,[eax]`; class name `VMT-0x20`, instsize `VMT-0x1C`, selfptr `VMT-0x40`.)

**The false premise that caused it**, quoted from the script's own docstring and now deleted:
*"CreateStrikeCA's callers are all melee-strike commands … never walls, so combat+0x4c is a valid
unit-or-null; the null-check covers the rest."* **A wall is a legal melee AND ranged target.**

**The fix** is `build_scripts/combatunitguard.py`, a shared cave at **`0x55849000`** (98 B, exclusive
reservation `0x55849000`–`0x558490FF`) with two entry points:

| entry | contract |
|---|---|
| `guard_unit` `0x55849000` | EAX = combat object → EAX = `[obj+0x4C]` iff `IsClass(obj, TCombatUnit)`, else 0. Nil in, 0 out. |
| `guard_hero` `0x55849040` | EAX = combat object → AL = 1 iff that strategic unit is a `THero`, else 0. |

Both clobber **EAX and flags only** — a caller's ECX/EDX/EBX/ESI/EDI/EBP all survive, which
`cave_melee` (live PIC anchor in EDI, attack in BL) and `cave_melee3` (strike record in EBX) need.
Position-independent: both classrefs come through a `call $+5`/`pop` anchor.

**Five sites carried the defect; all five are fixed.**

| cave | site | owner | reached by |
|---|---|---|---|
| `cave_melee` | `0x5580E0B7` | `build_assassin.py` | `CreateStrikeCA` — round attack / opportunity |
| `cave_melee3` | `0x5580E160` | `build_assassin.py` | `CalculateStrikes` — deliberate melee |
| `melee1` | `0x558129F3` | `build_magebane.py` | `CreateStrikeCA` |
| `melee3` | `0x55812A23` | `build_magebane.py` | `CalculateStrikes` |
| `ranged` | `0x55812A5D` | `build_magebane.py` | `CreateRangedAttackCA` |

Magebane had never been seen to crash only because no Magebane carrier had yet swung at a wall; its
`cave_count` then dereferences the garbage directly (`mov ebp,eax / mov ecx,[eax] / call [ecx+0x148]`).

**Why a helper call rather than an in-place byte splice.** `mov eax,[reg+0x4c]; test eax,eax;
je skip` is 7 bytes and `mov eax,<reg>; call helper` is also 7, so a surgical splice would have
fitted. It was not used because the brief — and CLAUDE.md's re-tuning rule — require the **source**
to stop being able to emit the broken bytes, so the cave *generators* were fixed and the bodies
regenerated whole. That is what makes the next paragraph's layout work necessary.

⭐ **Where the guard goes is a layout decision, not a style one.** In Assassin the call replaced the
whole hero test and both caves got *shorter*; they are nop-padded back to 106 B / 104 B so
`cave_asnreg`, the name literal and `cave_melee3` keep the addresses `build_trueseeing.py` /
`build_invis_penalty.py` document. In Magebane a `call` at each of the three sites costs **4 bytes
more** than the `mov eax,[reg+0x4C]` it replaces, which pushed the ranged block past
`build_shield.py`'s `RNG_TAIL` pin `0x55812A7B` — so the guard went into **`cave_count`** instead
(which now takes the combat object, not the strategic unit), making every site *shorter*, and
`cave_count`'s 14 bytes of alignment slack absorbed the 10 bytes it added. Not one address moved.
⚠ `build_shield.py` also asserts on magebane's **melee1 tail** `M1_TAIL = 0x55812A09` and aborts
entirely when it is wrong — the first pass shortened melee1 by one byte and bricked it. Both melee
blocks are now length-pinned (`M1_LEN_PIN = 46`, `M3_LEN_PIN = 48`).

**Sibling sweep of all mod cave space** (`0x5580B000`–`0x558E7918`, every `mov r32,[r32+0x4C]` plus
every `call @IsClass`), verdicts for the 20 surviving hits:

- **Correct already** — `IsClass(TCombatUnit)` precedes the read: `build_ranged_slayers.py`
  `0x5580E272`, `build_replaylog.py` `0x5580F22A`/`0x5580F28B`, `build_combatlog_dll.py`
  `0x558110FF`/`0x5581115E`/`0x558116B4`/`0x55811715`, `build_razebattle_tower.py` `0x5580D003`,
  `build_minddecay_oos.py` `0x55842023`/`36`/`4A`/`5E` (its cave *is* vanilla's own gate, relocated —
  the cave's first instruction is the `call @IsClass` vanilla made at `0x557F8623`, and AL survives
  the PIC prologue to the `test al,al` at `0x5584201F`).
- **Vanilla parity, no mod-introduced exposure** — `build_debuffcache.py` `0x5580F906`/`26`/`46`:
  vanilla `TWebCA.Execute` itself does an unguarded `mov edx,[ebx+0x4c]` at `0x5576A09C`, one
  instruction before the hook, and the Entangle twins the same. If a wall could reach those CAs,
  vanilla would already fault. Same for `build_turnundead_evilcommand.py` `0x5583216B`/`0x55832176`/
  `0x5583224B`, which replays `TTurnUndeadCA.Execute`'s own unguarded `[ebx+0x4c]` reads at
  `0x5576AC4F`/`0x5576AC5A` with EBP/EDI substituted.
- **Not object fields** — none (both `[ebp+0x4c]` hits above are on a saved-register object, not a
  stack frame; adjudicated as vanilla parity instead).
- **Unreferenced** — `0x5580C050`, a hand-authored cave with **no caller at all**: no `call`/`jmp`
  rel32 in CODE reaches it and the dword `0x5580C050` appears nowhere in the file. Dead code that
  happens to contain the pattern. Left alone; worth tracing if anyone ever revives that pocket.

**Revert.** `build_assassin.py` had no `--undo` at all; it now has two, both surgical, neither
touching a backup:
- `--undo-wallguard` rewrites the two caves with their exact pre-fix bodies and drops the shared
  guard **only if `build_magebane.py` no longer calls it**. Round-tripped 2026-09-11: apply → undo →
  apply returns the DLL to the identical SHA-1.
- `--undo` removes the whole feature (three hook byte-runs restored, four caves + the name literal
  zeroed) and **refuses while a downstream cave is spliced into either exit jump**, naming it. With
  invisibility and Magebane installed it refuses today, which is the correct answer.

`build_magebane.py --undo` is unchanged apart from also dropping the shared guard when nothing else
calls it.

⚠ Both scripts' snapshot gates were wrong and are fixed: `if not os.path.exists(BACKUP)` would have
minted a `.pre-assassin` / `.pre-magebane` **from the already-patched DLL**. Both now require every
hook site to still hold its vanilla byte-run.

**Failed approaches, kept because both are exactly the shape a future conditional-attack mod will
reach for first:**

- **Hooking only the global `CreateStrikeCA`.** Assassin fired correctly on attacks-of-opportunity
  and Round Attacks but **never on an ordinary deliberate melee attack** — deliberate melee simply
  does not route through the global builder at all. Diagnosed by tracing the actual call chain
  (`fcExecuteCombatCommand → TMeleeRound.Calculate → CalculateStrikes`) rather than guessing which
  builder was "the" melee path.
- **Hooking `CalculateUnitStrikes` as a second, "strategic twin".** This changed nothing observable
  — that function serves the opportunity/predictor evaluation, not the actual strike that lands, and
  patching it was reverted once the real deliberate-attack path (`CalculateStrikes`, not
  `CalculateUnitStrikes` — note the very similar names) was found.

**Ranged has a single builder, no twin**, which is why Phase 2 needed only one hook. Both
`TRangedAttackAbility.fcExecuteCombatCommand @0x5576EB70` and
`TBreathAbility.fcExecuteCombatCommand @0x5576F182` call `CreateRangedAttackCA @0x5576EAE4` once
**per shot** (the outer loop runs `GetAttackRepeatRA` times), so one hook at `0x5576EB34` — the
`push eax` of the already-computed damage byte, with the attack byte already pushed just before it
— covers ranged and breath together, and the bonus lands per shot. `CA+0x18 = ability+0xC` is a red
herring worth flagging: it looks like it could be the damage field but is actually the ability id,
read only by `TRangedAttackCA.Play` to pick the attack sound — don't bump it.

**Composes cleanly with the user's existing ranged reworks.** Marksmanship scaling and the
Cave/Depths −2 no-Night-Vision malus both live *upstream*, inside `GetAttackRA @0x5576E65C`'s own
cave, before `CreateRangedAttackCA` is ever called — so base, Marksmanship, the terrain malus and
the slayer bonuses all simply add in sequence with no interaction to manage.

---

## Drillmaster — per-stack XP aura (id `0xAB`)

**✅ CONFIRMED WORKING (2026-08-08, v4).** `build_scripts/build_drillmaster.py` — AoWEPACK.dpl
**and** `Release/Ability.pfs`, both with a surgical `--undo`.

A stack containing a Drillmaster grants **+1 XP per turn to every other unit in the stack, and the
effect stacks** — N Drillmasters give +N to everyone else. Drillmasters do not train each other
(trainers don't train each other) and heroes are excluded (they already have their own XP trickle
and would otherwise double-dip). Both choices are one-line changes if ever wanted otherwise; the
tally is uncapped but self-limiting (a stack holds at most 8 units, so the ceiling is +7/turn for a
lone trainee among seven Drillmasters).

**Built from two already-existing patterns, nothing new engine-side:** the per-turn hook is
`TArmy.NewTurn @0x5578F79C` (one call per army per turn — and an army *is* the stack); the stack
walk mirrors the Leadership aura's own (`count = [[army+8]+8]`, `items = [[army+8]+4]`, `unit =
[items + i*4]` — **the count lives on the list at `+8`, not on the army itself**, the standing trap
for iterating any engine list this way). The ability test uses the **item-aware** accessor pair
(`+0x144`/`+0x148`), not the self-only pair — so a Drillmaster *item* already works with no further
code, for free.

**Cave layout:** `cave_reg @0x55816000` (42 B) + name literal, `cave_turn @0x55816040` (173 B),
claimed from the free run starting `0x5581546D`. Registration repoints the *last* vanilla
`RegisterAbility` call in `RegisterPassiveAbilities` (`0x557BCF39`) — deliberately not the same call
Path of Sand already owns (`0x557BC9E9`); any third ability sharing this function needs yet another
free call site, and the script prints which are already taken. `TArmy.NewTurn`'s entry (6 bytes,
`53 8B D8 3A 53 12`) is replaced with a `jmp` to `cave_turn`, which re-executes the displaced
`push ebx; mov ebx,eax; cmp dl,[ebx+0x12]` **last**, immediately before jumping back, because the
resume point's `jne` consumes that comparison's flags — the cave has to reproduce the state the
jump destination expects, not just "do its thing and return".

**Category:** `herodlg_cats.py` sends every id it doesn't explicitly list to `DEFAULT_CAT` = Magic,
and the live table byte for `0xAB` reads 4 — Drillmaster needed no dialog-category work at all.

### Version history — three bugs found by playing it, kept as the reusable lessons

- **v1 — id `0xAA` collided, `Runtime error 217` before the main window.** Built on the strength of
  a documented "guaranteed safe" band that had gone stale the moment `0xAA` was claimed by another
  feature first. Fixed by adopting the dynamic `check_id_free()` procedure described in the general
  mechanics section — this is the origin of that procedure, now cloned into every later script.
- **v2 — `TArmy.NewTurn` is called once per PLAYER, not once per turn**, and the cave's first
  version did its work *above* the function's own `cmp dl,[army+0x12]` player-filter guard. Result:
  every unit in a Drillmaster stack gained +1 XP per player per turn — +3 a turn in a three-player
  game. Fixed by repeating the same comparison before scanning and re-executing it for the host
  function's own benefit afterwards. **Any cave hooking a per-object `NewTurn`/`NewDay` entry point
  should assume the same per-player shape and check for it explicitly** — it is not visible from the
  function's name.
- **v3 — the ability never appeared at hero level-up**, despite registering, being assignable, and
  granting XP correctly once assigned. This is the selection-mask trap described in the general
  mechanics section (`0x0137`, missing `astEditor`) — Drillmaster is where that trap was first
  decoded, from first principles, by reading the live RTTI enum.

Two things considered and rejected along the way: **`call $+5` as a PIC anchor** — covered in the
general mechanics section, this is where the trap was first caught (it would have zeroed the just-
replayed `RegisterAbility` call's rel32 instead of the intended anchor, a startup crash from
source that looks correct). **Testing hero-ness by VMT instance size** (`[VMT-0x1C]`: `0x48` for
`TUnit` vs `0x9C` for `THero`) — rebase-free and tempting, but rejected because a class's instance
size has already grown once elsewhere in this project's history (Copper Medal's `TUnitResource`),
so a size check is one refactor away from silently breaking; `IsClass` costs one delta-trick and
handles `TLeader` for free, at negligible extra cost.

---

## Magebane — enchantment-scaling ATK/DMG (id `0xAA`)

**🔨 APPLIED, UNTESTED (2026-08-29 re-tune; first applied 2026-07-30).**
`build_scripts/build_magebane.py`, backup `AoWEPACK.dpl.pre-magebane`. Cave
`0x55812900`–`0x55812AB4` (437 of a 512-byte reservation).

A unit with Magebane gains **+2 ATK and +2 DMG for every enchantment currently sustained on its
target** (re-graded 2026-08-24 from an original +1/+1, one knob covering both the DAM/HP doubling
and the 5% slope conversion's missed ATK half — the bonus is a *count*, not a raw immediate, so
neither conversion pass could see it automatically), stacking and uncapped by default. Covers
deliberate melee, retaliation, round/opportunity/ability strikes, and ranged + breath per shot.

### ⚠⚠ BOOBY TRAP — Magebane's ranged cave and Shield's ranged penalty share one tail jump

**Treat `build_magebane.py` as unsafe to touch in either direction — apply or undo — without
checking Shield's state first, and undo Shield before touching Magebane's ranged cave.** The two
features are chained: Magebane's ranged block sits between the ranged-slayers/invisibility chain
and the engine, and **Shield hooks the END of Magebane's own ranged cave**, replacing its tail `jmp`
with one into Shield's own sub-cave, which then resumes at the original address itself. The full
chain is `ranged slayers → invisibility → Magebane's ranged block → Shield → engine`. A version of
`build_magebane.py` that emits its old, unconditional stock tail (`jmp 0x5576EB39`) **silently
unlinks Shield's ranged penalty with no error anywhere** — `caves match: False` on an otherwise
healthy-looking Magebane state means *look at the tail jump, not the body*. This is exactly the
kind of coupling this project's own convention warns is the single most expensive thing to
rediscover, and it has already made the script briefly un-runnable in practice between 2026-08-26
(when Shield's chain was built) and 2026-08-29 (when the mitigation below landed).

**The mitigation actually shipped, 2026-08-29:** the script no longer hard-codes either tail. It
inspects the fixed byte range where Shield's ranged sub-cave would live
(`SHIELD_RANGED_CAVE = 0x558230D0`) and, if any byte there is non-zero (Shield installed), chains
into it; if the range reads all-zero (Shield `--undo`ne), it emits the plain stock tail back to the
engine instead (`ranged_tail()` in the script). This is a detection heuristic over a fixed memory
window, not a hard invariant enforced by anything else — treat a green `--verify` after any Magebane
apply as necessary, not sufficient, exactly per this project's standing rule that static
verification is not proof (a cave that ran cleanly at package init and passed every static check
still broke startup elsewhere in this project's history). **The direction the mitigation does *not*
cover is `--undo`**: Magebane's `--undo` zeroes its *entire* cave unconditionally, which — if
Shield is still installed and chained through it — leaves Shield's own sub-cave at `0x558230D0`
with nothing calling it any more. This is silent, not a crash: Shield's ranged penalty simply stops
firing.

**The standing safe procedure, regardless of which direction you need:** undo Shield
(`build_shield.py --undo`) before applying, re-tuning, or undoing Magebane's ranged cave; re-apply
Shield afterwards if it should stay installed. `build_shield.py`'s own retune path re-detects a
moved Magebane sub-cave and re-points into it rather than aborting, so re-applying Shield after
Magebane is safe. Two pinned addresses make the coupling brittle in a way worth knowing about even
with the mitigation in place: `RNG_TAIL_PIN = 0x55812A7B` is the exact address `build_shield.py`
hard-codes as the 5-byte site it rewrites, so Magebane's own ranged block is padded to make its tail
land exactly there on every rebuild, with a hard error if it ever cannot; and `build_shield.py`'s
own retired-melee-site guard checks one of Magebane's melee tail addresses by value, so a future
Magebane re-tune that moves that tail must be cross-checked against Shield's script too, not just
verified in isolation.

### What counts as an "enchantment"

Exactly the abilities a unit carries whose class is `TUnitEnchantmentAbility` — the class that
creates a real `TEnchantment` object with an **owning player**, an **upkeep**, and a **dispel**
path (i.e. a sustained magical effect a caster pays for and Dispel Magic can strip). This is *not*
the same grouping as buff-vs-debuff or duration: `TDurationAbility` (Burning, Panicked, Poisoned,
Cursed, Vertigo, Crusader) is just a timer with no owner and never counts, even though some of those
are conventionally "magical". **Excluded by design despite technically qualifying:** Slow `0x84`,
Entangled `0x5E`, Frozen `0x5F`, Turned Undead `0x22` — enemy crowd control on the Magebane unit's
own target should not feed the Magebane unit's own damage. **Summoned `0x9B` counts, deliberately**
— it is a permanent `TUnitEnchantmentAbility` on every summoned creature (applied by
`TSummonSpellTE.Process`), so Magebane gets a bonus against summons "for free" via the same loop
that counts Bless or Haste.

`cave_count @0x55812920` mirrors `TAbstractUnit.RegisterEnchantments @0x5577F29C` exactly: walk the
global ability-type list (`[[HSSet+0x80]+0x1C]`), keep only `IsClass(ability, TUnitEnchantmentAbility)`
entries not on the exclusion list, and count those the item-aware `GetAbilityEnabled` confirms are
active on the target. The loop is O(all registered abilities) with two calls each — roughly 170
iterations — but only runs once the *attacker* is confirmed to have Magebane, so every other unit in
the game pays nothing.

### Injection — chained onto three existing caves, not new hook sites

Rather than rewrite the strike-creation bodies that Assassin/ranged-slayers/invisibility already own,
this feature repoints **each of those caves' final exit jump** into a small Magebane block that does
its work and then jumps to the original return address — 4 bytes of rel32 per site:

| site | exit jmp | returns to |
|---|---|---|
| `CreateStrikeCA` (round/opportunity/ability strikes) | `0x5580E399` | `0x557666CF` |
| `TMeleeRound.CalculateStrikes` (deliberate + retaliation) | `0x5580E3D9` | `0x55767C89` |
| `CreateRangedAttackCA` (ranged + breath, per shot) | `0x5580E298` | `0x5576EB39` (see the booby trap above) |

**⚠ Cross-script coupling, independent of the Shield trap above:** all three exit jumps live *inside
caves owned by other scripts* (`build_assassin.py`, `build_ranged_slayers.py`,
`build_invis_penalty.py`). **Re-running any of those three rewrites its own cave and silently drops
the Magebane chain** — `build_magebane.py --verify` reports the state of all three (plus the Shield
link) in one line; re-run `build_magebane.py --apply` after any of the other three to restore it.
Register liveness at each exit was read from the **live** binary, not any design doc: melee1/melee3
leave `EAX`/`ECX`/`EDX` dead at the resume point, but the ranged exit does not (`0x5576EB39` is
`call [edx+0xB8]`), so that block saves and restores `EAX`/`EDX` around its work and its three pushes
shift the two argument slots to `[esp+12]`/`[esp+16]`.

### Registration and the open id-risk this feature is the decisive test of

Hooks `0x557BCF6E`, the **last** vanilla `RegisterAbility` call in `RegisterPassiveAbilities`
(selection mask `0x37`, the same Path of Sand uses, confirmed to make an ability listable in the
editor). **Id `0xAA`** was the first free id above vanilla's own maximum (Dark Gift `0xA9`) at the
time this shipped; a third-party report of a `Localize.dpl` crash for ids above `0xA9` on a
different modder's build was unresolved when Magebane applied and remains so — both possible
failure modes (a duplicate-id assert, or the reported Localize crash) are loud and immediate at
startup, so simply launching the game once is the decisive test for this specific risk. If either
fires, `MAGEBANE_ID` is a top-of-script constant; change it to a verified free id and re-run — the
script rewrites its own cave in place, no revert needed for a re-tune. **The icon will be blank**,
expected for any brand-new id with no ILB entry.

### Summoned is worth +5/+5 on its own — a top-up, not a separate arm

User ruling, 2026-08-29: a target with Summoned should take **+5/+5** total from Magebane, not the
ordinary +2/+2. Implemented as a top-up rather than a duplicate code path, in `cave_count`'s tail:
after the ordinary count is multiplied by the per-enchantment bonus, a second, independent
`GetAbilityEnabled(target, 0x9B)` check adds the *difference* (`SUMMONED_BONUS − BONUS_PER = 3`) on
top. Because Summoned is *also* still counted by the ordinary loop, a bare summon with no other
enchantment reads exactly **+5/+5** (2 from the ordinary count, +3 top-up) and a hasted summon reads
**+7/+7** (5, plus one further ordinary +2 for Haste) — the arithmetic composes correctly without
double-applying. Moving the multiply itself from the three strike blocks into `cave_count` was
incidental to this change but is worth keeping in mind as the reason the cave sizes shifted: all
three strike sites now share one copy of the arithmetic and cannot drift apart from each other.

### Description text

`Ability.pfs` record 180 (id `0xAA + 10`), **🔨 APPLIED, UNTESTED (2026-08-29)**,
`build_scripts/build_magebane_desc.py` (backup `Release/Ability.pfs.pre-magebanedesc`, byte-exact
`--undo`): *"+2/2 ATK/DAM against units per enchantment they have, and +5/5 ATK/DAM against summoned
units"*. This could not go through the shared text-rewrite tool (`build_pfs_typos.py`), because that
tool only *replaces* text in a tag that already exists, and Magebane's record — as DevEd created it
— had no tag 5 at all (only 6/7/8/9). Adding a field that did not previously exist means growing the
record's directory by one small entry and appending the new u32-prefixed string to the payload,
which the description-writer script does directly, reusing (not reimplementing)
`build_pfs_typos.py`'s own field-layout and CRC-repair helpers. **Design points worth reusing for
any other field being added, not just edited, to a `.pfs` record:** append the new bytes at the very
end of the payload so every existing field keeps its offset unchanged; the small-directory-entry
offset is a single byte, so the new field's offset and every later field's offset must be checked
against that ceiling, not truncated; and the record's trailing 4-byte CRC must be stripped before any
"nothing else changed" comparison, or the CRC repair itself reads as unexplained collateral damage.

---

## Caster Cost abilities — Evoker / Conjurer / Enchanter / Ritualist (`0xAC`–`0xAF`)

**✅ CONFIRMED WORKING (2026-08-27), validated in-game by the user.**
`build_scripts/build_caster_cost.py`. Each ability **cuts the initial casting cost of one spell
family by 40%** (×0.6, `imul ebx,ebx,0x999A / shr ebx,16` = ⌊3x/5⌋ exactly for x < 32768;
owner ruling 2026-09-25, was `shr ebx,1` = 50%; 🔨 APPLIED, UNTESTED — in-game: a 60-mana
Conjurer spell costs 36, a 25-mana one 15) and does nothing else — no damage change, no upkeep change, no research-cost change, no
icon, no level table, no per-owner data record (all four are plain bit-only passives).

| ability | id | family (spell classes) | count | intended cost (cave) | **live cost** (`Ability.pfs` tag 6) |
|---|---|---|---|---|---|
| Evoker | `0xAC` | `TCombatSpell` | 30 | 20 | **20** |
| Conjurer | `0xAD` | `TSummonSpell` | 13 | 40 | **40** |
| Enchanter | `0xAE` | `TUnitSpell` | 18 | 40 | **30** ⚠ |
| Ritualist | `0xAF` | `TGlobalEnchantmentSpell` | 12 | 40 | **30** ⚠ |

The family column above is the original class seed. Since 2026-09-25 the family is per-spell data
authored in AoWzEd (Settings > Spells > Caster), and the owner has assigned every spell. The
manual's spell cards show it as a "Caster" row. Evoker was
originally scoped as a spell-*damage* ability; the user rescoped all four to cost-only on
2026-08-26, before anything but the classification research had been built.

### Families are data, and the wallet (🔨 APPLIED, UNTESTED 2026-09-25)

**Family = data.** `build_spell_family.py` streams a new `Spells.pfs` byte tag `0x12` into spell
byte `+0x23` (alignment padding; `TSpell` instance size `0x34`, no method of the 117 classes
touches it): 0 none, 1 Evoker, 2 Conjurer, 3 Enchanter, 4 Ritualist, ability `0xAB + family`.
- Hook: `TSpell.ReadWrite` tail `0x557792BB` (8 B, `lea edx,[ebx+0x21]; mov ecx,0x11`) → `cave_rw`
  `0x5584D2C0` (34 B), which replays tag `0x11` and streams tag `0x12` through the same
  `[stream+0x30]` = `rwByte` (`TEReadStorageStream` VMT, `0x55510F44`). Shared by game load and
  editor save. A record without the tag loads **0** (`rwByte`'s not-found arm zeroes the byte).
- Data: all 109 records seeded from the class rule below — **31 Evoker (incl. Embrittle 109, a
  `TSlow` instance), 13 Conjurer, 18 Enchanter, 12 Ritualist, 35 none**. Wide entry appended after
  tag `0x11`, 9 B per record, file 80 475 → 81 456 B. `--apply` only adds a missing tag, never
  overwrites an authored one. Snapshot `<game dir>\backups\Spells.pfs.pre-spellfamily`.
- Classifier: `build_caster_cost.py`'s `cave_cost` (`0x55820800`) rewritten in place to
  `movzx edx,byte [esi+0x23]; dec edx; cmp edx,3; ja skip; add edx,0xAC; call [ecx+0x148]` —
  51 B inside the pinned 120-B slot, so `cave_floor`..`cave_reg` do not move. `--classic --apply`
  restores the class test.
- **Order:** `build_spell_family.py --apply` before the data classifier (the classifier's
  `--apply` aborts otherwise); `build_caster_cost.py --classic --apply` before
  `build_spell_family.py --undo` (which aborts otherwise).

**Wallet.** `build_caster_wallet.py` turns a cost equal to `[spell+0x14]` into
`CastingMana(hero, spell)` at `THero.CanCastSpellInstantly` `0x5578964A`, the hero branch of
`TSpell.CastingDone` `0x557794D6` and of `TSpell.CombatCastingDone` `0x55779517` (caves
`0x5584D300` 78 B / `0x5584D360` 28 B / `0x5584D3A0` 30 B). Exact, not `min()`, so the ×1.5
opposed-sphere surcharge now reaches instant casts. Full table in `04-spells-modded.md` (sphere
Mastery coupling section).

**In-game checklist:**
1. Fire Mastery hero, Cloud of Ashes, 4–5 casting points left: the spell now casts (it used to
   start and do nothing).
2. Opposed Mastery (e.g. Water Mastery hero casting a Fire spell instantly): the ×1.5 cost is
   charged, and matches the spellbook.
3. Evoker hero in tactical combat with casting points below a combat spell's raw cost but at or
   above the discounted (×0.6) cost: the spell is offered and casts.
4. Conjurer on a summon and Ritualist on a global enchantment: discount unchanged from before.
5. Launch `AoWzEd.exe`, save the spell set, and check every spell's family survives the round trip.

### The class rule — the seed of tag `0x12`, and `--classic`; a rebase-invariant idiom worth reusing anywhere a spell/ability's class matters

All four families are identified by a **VMT slot difference**, which needs no PIC anchor at all
because the load-address delta cancels out of the subtraction: `[VMT+0x6C] − [VMT+0x18]`, where
`VMT+0x18` is `TSpell.ReadWrite @0x55779234`, un-overridden across the entire 117-class spell
subtree (verified: exactly one distinct value across all of them). Constants: Summon
`0x0006B27C`, Global enchantment `0x000767E0`, Unit spell `0x00001FF4`, Combat (pre-filter, shared
with the never-registered abstract `TSpell` base) `0x00000120`, confirmed exclusively as combat by a
second slot difference `[VMT+0x80] − [VMT+0x18] == 0x0007E034`. The four branches are structurally
disjoint siblings directly under `TSpell` in a single-inheritance hierarchy, so no spell can match
two of them and the cave's test order cannot misclassify. **Do not use** any of: `[spell+0x22]==2`
(that is `stGlobal`, shared by 60 of 108 spells, not "global enchantment" — and on the companion
`*TE` classes the same offset is a hex map coordinate, not this field at all); `[spell+0x3C]==0`
(the "instantaneous" filter an earlier study proposed — it is simply the common default,
`TCombatSpell.Create` writes 0 there for every combat spell); instance size (unique inside the
subtree but not file-wide — 45 DLL-wide classes share the combat-spell instance size); or
`System.@IsClass` with a classref (needs a new `.reloc` entry or a much longer parent walk for no
benefit over the slot-difference test).

### The cost cave — two hooks, and why a floor cannot live in the prologue

**The one correction worth internalising from this feature, reusable anywhere a value needs a floor
applied downstream of another feature's own cave:** a floor enforced where the value first enters
the function does **not** survive the function if something else rescales it afterwards. Here,
`THero.CastingMana`'s entry hands control to `build_mastery_cost.py`'s own cave, which rescales the
cost by ×0.75 or ×1.5 and *then* jumps to the shared vanilla epilogue at `0x55789510`. A floor
applied at entry would already be baked into the pre-rescale value; `(1×3)>>2 = 0` still happens
downstream regardless. **So the floor hooks the function's single, five-byte, three-arrival
epilogue instead** (`0x55789510`: `mov eax,ebx; pop esi; pop ebx; ret` — confirmed the *only*
convergence point in the whole function via a full-file scan for anything branching into it), fully
orthogonal to the mastery cave: either feature can be undone without breaking the other, because
neither one's verify-before-write touches the other's bytes.

**HOOK 1** — the function's 7-byte entry (`0x557894EC`) — classifies the spell (see above), and, for
a matching family, queries the item-aware `GetAbilityEnabled` (VMT `+0x148`, per the general
mechanics section) exactly once and applies the discount (×0.6 since 2026-09-25), applying **no floor here on
purpose**. **HOOK 2** — the shared epilogue (`0x55789510`) — enforces the floor: cost 0 stays 0 only
if the spell's *base* cost was genuinely 0 (`Flaming Arrow`, id 123, is the one spell in the game
with no `Spells.pfs` mana-cost tag at all — an unconditional floor would turn its intentional free
cast into a nerf), otherwise any nonzero base cost that rounds down to 0 is floored to 1. **A zero
cost reaching the caller is not harmless**: `THero.CastingDone` then subtracts 0 from both mana and
casting points, i.e. genuinely unlimited casting, not merely a display of 0.

### Registration

Splices `0x557BCF04` (the highest still-free `RegisterAbility` call in the window used by every
feature in this file), replaying the displaced call, then registering all four abilities in one
cave using the general recipe — four repeats of the per-ability block, each **recomputing its own
PIC anchor** (see the general mechanics section's warning about why one shared anchor across
multiple registrations is unsafe). Mask `0x03FF` on all four.

### The wallet bug — a genuine pre-existing vanilla defect this feature's investigation surfaced and fixed

`THero.CastSpell` takes an **instant-cast** branch whenever `CastingMana ≤` the caster's casting
points. On that branch, three spell-family `Activate`/`Process` sites (`TSummonSpell.Activate
@0x557E44F8`, `TGlobalEnchantmentSpell.Activate @0x557EFA7C`, `TSummonSpellTE.Process
@0x557E4353`) re-read the spell's cost **raw**, from `[spell+0x14]`, instead of calling
`CastingMana` — skipping not just this feature's discount but vanilla's own sphere-Mastery ×2
penalty too (`GetSphereManaDoubled @0x5577E230` has exactly one code caller in the whole DLL, and it
is inside `CastingMana`). **This is original 1999 behaviour, proven vanilla**: all three sites are
byte-identical between the live DLL and the pristine backup.

**Why a 27-year-old bug never surfaced until a discount was added, and why the direction of the
modifier is what decides whether a gate/re-check mismatch is invisible or fatal — a generally
reusable diagnostic:** `TSpellTE.Validate` independently re-checks the same **raw** cost against the
same casting-points budget. Vanilla's ×2 penalty makes the *instant-branch* gate **stricter** than
that re-check (`2R ≤ P` implies `R ≤ P`), so the re-check can never fail — the only symptom is a
silently under-charged penalty on a handful of cheap summons, invisible unless someone is counting
mana closely. **A ×0.5 discount pushes the same gate the other way**, opening a band `D ≤ P < R`
where the instant branch is entered, the spell is accepted, and the independent raw re-check then
**rejects it** — the caster is charged nothing and nothing happens, with no error of any kind. At
casting level 5 (the top of the 10/20/40/60/90 ladder) this was not a corner case: 3 of 13 summons
and 4 of 12 global enchantments would have done nothing at all, including Summon Gold Dragon,
Summon Black Dragon, Craft Aether Barge, Enchanted Roads, Hatred, Power Leak and Spell Ward.
**Fixed with three sites** (two caves at the `Activate` calls, one pure in-place instruction
substitution at `TSummonSpellTE.Process` swapping a raw-field read for a use of the already-computed
discounted value) — all `.reloc`-free, all verified byte-identical to pristine before patching. User
sign-off, 2026-08-26: the fix also means `build_mastery_cost.py`'s own multiplier now reaches
instantly-cast summons and global enchantments for the first time, which is a real cost increase on
the opposed-sphere case as well as a real decrease on the matching-sphere one — a deliberate,
signed-off side effect, not a bug.

Water Mastery's raw charge (`TWaterMastery.ExecuteTE @0x557F0A88`) and Cosmagic Scrying's raw TE
cost (`0x557E85F9`) are closed by the wallet above (2026-09-25).

### Verified without the game, and the follow-ups that remain after confirmation

All six touched windows were `.reloc`-free and byte-identical to vanilla pre-patch; the diff against
the pre-apply backup was exactly the six sites plus one contiguous cave block, nothing else in the
2.7 MB file. `--undo` → `--apply` round-trips byte-exact by hash. `check_ids_free` on the patched
file reports no clash for `0xAC`–`0xAF`.

Two small, explicitly non-blocking follow-ups remain open even though the feature as a whole is
confirmed: **tag 5 (description) is empty on all four** records, and **Enchanter/Ritualist read a
live level-up cost of 30, not the 40 the design intended** (see the table above) — both are DevEd
edits, not script bugs, since the cave cannot set either value (per the general level-up-cost
section). **A fifth ability, `0xB0`, appeared in the registry mid-way through this feature's own
build session, registered by unrelated concurrent work** — it turned out to be Shield (see the
Magebane section above for the cave it shares); noted here only because it is a concrete
demonstration of why the id-freshness procedure in the general mechanics section has to be run on
every single invocation, not cached from a prior session.

---

## Copper Medal — third unit rank, and a fourth ability-owner slot

Two independently-tracked pieces under one script, `build_scripts/build_copper_medal.py`
(AoWEPACK.dpl + `Images/*Combat.ILB`, plus `AoWDevEd.exe` for the ability-owner half): the rank
ladder/stat-bonus/icon (**✅ CONFIRMED WORKING, 2026-07-30**) and a genuinely new ability-mechanics
feature, a **fourth per-unit ability-owner slot** so Copper can grant its own bonus-ability set the
way Silver and Gold already do (**🔨 APPLIED, UNTESTED, 2026-07-30**). This section covers the
ability-mechanics half in depth and the ladder only as necessary context; the full stat-table
history and the icon art pipeline belong to the combat-maths / UI files.

Units rank None → Copper (1) → Silver (2) → Gold (3), inserted below the pre-existing Silver/Gold.
**Ladder:** copper = tier×2, silver = tier×6, gold = tier×15 XP; **all three ranks grant the same
flat +1 ATK / +1 RES** (Gold's old +2 is gone). Rank is *derived* from the XP byte on every call
(`TUnit.GetRank`), never cached or serialised, so old saves load unchanged and simply re-derive a
(possibly lower) medal against the new thresholds.

### The fourth ability-owner slot — what made it cheap, and the one blocker

Silver and Gold's bonus abilities are already per-unit data: `Unitres.pfs` tags `0x1E`/`0x1F`,
loaded into two of `TUnitResource`'s contiguous ability-owner slots at `type+0x38 + i*4`. Three
things made a fourth slot cheap rather than a rewrite: the **editor already indexes owners
generically** (`AoWDevEd.exe 0x00410F40` does `eax = [resource + tabIndex*4 + 0x38]` — not hard-coded
to three tabs, so adding a fourth DFM tab is enough for the editor side); `Unitres.pfs` tag `0x20`
was free (highest tag in use across all 180 unit records was `0x1F`); and the DLL's grant/create/
destroy loops are plain counted loops (`do {...} while (count != 3)`), not unrolled code, so raising
one loop bound in three places was the entire code-side change.

**The one real blocker:** the fourth contiguous slot (`type+0x44`) was already occupied — by the
**transport-capacity byte** (`Unitres.pfs` tag `0x18`). Confirmed by data (only 11 of 180 units carry
tag `0x18`, all transports) and by an exhaustive reference sweep
(`re_tools/fieldrefs.py`, written for this and validated against a field known to be read): capacity
is touched in exactly **three** places total, across both binaries — the accessor
`TUnitResource.GetTransportCapacity @0x55784D24` (`mov dl,[ebx+0x44]`), `TUnitResource.ReadWrite`'s
tag-`0x18` handler (`lea edx,[edi+0x44]`), and one `AoWDevEd.exe` spin-control write
(`mov [esi+0x44],al`) — and every one of the accessor's ten call-site xrefs goes through the
accessor, never the raw field. **Resolved by moving transport capacity to `type+0x32`**, a 6-byte
gap in `TUnitResource` (instance size `0x54`) that no pfs tag maps to and the constructor never
initialises — freeing `+0x44` for the fourth owner slot with the `.pfs` format for capacity
completely unchanged (still tag `0x18`, just a different in-memory offset).

⚠ **`ImageLib.TCustomImageLibrary.Get` has no bounds check** — worth stating plainly since it means
the copper medal's new icon (id 8, a disc-only recolour of Silver's id-5 sprite) was not cosmetic
polish but a correctness requirement: pointing the painter at an absent image id reads straight past
the image table.

### ⚠ Slot order IS rank order — the bug this got wrong once, and why it looked fine at first

Both the grant loops and the editor index owners as `[unitres + rank*4 + 0x38]`, so the four slots
must read, in order, base / copper / silver / gold. **The first build appended copper at the far
end (`+0x44`) instead and left silver/gold where they already were.** This compiles, applies, and
*looks* correct — but shifts every rank's data by one slot: in the editor, the Copper tab listed
Silver's abilities, Silver listed Gold's, and Gold was empty; in-game a copper-medal unit would have
received silver's ability set. Caught by the user in the editor before it ever reached a save file.
**Fixed by moving silver's serialisation offset to `+0x40`** (a one-byte change) so the layout
becomes base `+0x38` / copper `+0x3C` (new) / silver `+0x40` / gold `+0x44`, with the script now
deriving every offset from one ordered table and asserting rank order on every run so the two
representations (grant-loop cave, editor tab index) cannot drift apart again. Existing
`Unitres.pfs` data needed no migration: tag `0x1E` still means silver and `0x1F` still means gold —
only the in-memory slot each lands in changed.

**⚠ VA-to-file-offset is per PE *section*, not a single project-wide constant — the trap that caught
the very first build attempt on this feature.** `AoWEPACK.dpl` CODE resolves as `file_offset +
0x55700C00`, but the rank stat-bonus tables patched here are in **DATA**, which resolves as
`file_offset + 0x55701200` — a 0x600 difference. Using the CODE delta on a DATA address reads
0x600 bytes past the intended table; verify-before-write caught it immediately, but any future
script touching a DATA-section address (the rank stat tables and everything past them) must resolve
it through the PE section table, never assume one blanket delta for the whole file.

**Editor DFM constraint, reusable for any future dialog change:** the `TUNITRESOURCEEDITFORM`
resource is packed with zero padding against its neighbour, so the new fourth tab's caption had to
be paid for from *inside the same form* — found by deleting one now-redundant explicit
`TabOrder = 0` property (the control is already first in creation order, so the property was a
no-op) rather than by any resource-directory surgery.

### In-game checklist (this half only — the ladder/stat/icon half is already confirmed)

1. Add an ability under the new Copper tab in DevEd, save, reopen — confirm it persisted; then
   in-game confirm a copper-medal unit gains it and a rank-0 unit does not.
2. **Verify transport capacity survived the `+0x44` → `+0x32` move** — check a Galley (4) / Carrack
   (7) / Giant Frog (1) in the editor, and that a transport still carries the right capacity in-game.
   This is the one thing the field move could plausibly have broken.
3. Sanity-check that dropping `AbilityRankTabs.TabOrder` did not disturb keyboard tab order on the
   unit-resource form (expected: no change).

---

## Unowned caves on the spellcasting economy (context for Conjurer, and for future work)

Found incidentally during the Caster Cost investigation; **no script under `build_scripts/`
references any of these, none has a backup or an `--undo`, and none is currently documented
anywhere else.** Recorded here because they directly bound on this file's features (Conjurer
especially) and because "no script references this address" was already proven, elsewhere in this
project's history, to be a statement about a moment in time rather than a safe assumption:

| site | live behaviour |
|---|---|
| `SummonSpells.TSummonSpell.SetupSummonSpellTE @0x557E4484` | entirely replaced by `jmp 0x5580C500`; the cave makes summon unit id `0xE4` spawn `RandInt(5)+3` copies for one mana payment |
| `0x557885EC` (reached from `TLeader.GetPowerGeneration @0x5578B461`) | the Spellcasting mana-income ladder, currently 10/20/40/60/90 (vanilla was level×5+5) |
| `0x5580BF00` (reached from `THero.GetCastingPointsMax @0x55788639`) | the casting-points ladder, currently 10/20/40/60/90 (vanilla was level×10) |

The summon multiplier is directly material to Conjurer: one summon spell already yields 3–7 units
for a single (now-halved) mana payment, so the discount compounds with an existing multiplier that
nothing currently owns or documents outside this paragraph. If either ladder is ever retuned,
whoever does it should claim these addresses with a proper script rather than hand-editing them.

---

## Weakness abilities — the inverse of the Protections (`0xB3`–`0xB9`)

**🔨 APPLIED, UNTESTED (2026-09-25).** Scripts `build_weakness.py` (mechanics and registration,
AoWEPACK slot `0x5584DB00`–`0x5584DEFF`) and `build_weakness_pfs.py` (records). The design is
Inioch's AoWx one (share8 `weakness-abilities-SHELVED.md`, done and confirmed in his game despite
the file name); every site was re-derived on ours. By owner's ruling there is no Physical
Weakness: Embrittled `0xB2` already doubles physical damage.

| id | name | damage bit | status effect |
|---|---|---|---|
| `0xB3` | Fire Weakness | `0x01` | Burning |
| `0xB4` | Cold Weakness | `0x02` | Frozen |
| `0xB5` | Lightning Weakness | `0x04` | Stunned |
| `0xB6` | Magic Weakness | `0x08` | — (Magic has none, as with its Protection) |
| `0xB7` | Poison Weakness | `0x10` | Poisoned |
| `0xB8` | Death Weakness | `0x20` | Cursed |
| `0xB9` | Holy Weakness | `0x40` | Vertigo |

**Effect.**
- **Damage:** ×1.5, rounded up ((3d+1)>>1, capped at 126 like Embrittled), when a hit carries a
  type the unit is weak to and not protected against.
- **Resistance:** −4 on the Resistance check against that type's status effect and on typed
  resistance rolls, the mirror of our Protection's +4.
- **Cancelling:**
  - Protection and Weakness of one type cancel. The halving is dropped, the ×1.5 is skipped, and
    the +4 and −4 sum to 0.
  - Immunity wins, because an immune type is stripped from the hit first.
  - All protection and immunity sources (items, enchantments, Fire Halo, Blessed, Liquid Form)
    arrive through the engine's own GetProtectionTypes / GetImmunityTypes, so all of them count.

**Sites.**
- **Damage, combat:** both `TCombatObject` strike funnels. The hooks are the 6 vanilla bytes right
  after `build_embrittle.py`'s `call 0x5582D130`, which returns the protection mask:
  `0x55726A43`, `0x55726AD8`. Abilities are tested through the combat object's GetAbilityEnabled
  (VMT +0xA8).
- **Damage, strategic:** `TAbstractUnit.ExecuteDamageRole`'s protection call `0x55781B14`.
- **Status effects:** the six `mov eax,0xA / sub eax,edi` in `ExecuteDamageEffectsRole`
  (`0x55781C30/C90/CE2/D34/D86/DE6`).
- **Typed resistance rolls:** `ExecuteResistanceRole` after its protection `sub edi,4`
  (`0x55781B84`).
- Strategic abilities are tested through VMT +0x148.

**Registration.**
- **Splice:** `0x557BCDFB`, a free `call RegisterAbility` in `RegisterPassiveAbilities`.
  Registration is seven `CreateEnhancementAbility` calls, one anchor each.
- **Mask:** `0x027F` = astUnit + item slots + astEditor. Weaknesses are assignable to units, items
  and heroes in the editor, and never offered at level-up or leader customisation.
- **Records:** keys 189–195, cloned from the matching Protection's record: SFX and empty image
  list kept, mask `7F 02`, no tag 6.
- **Ceiling LADDERs:** `build_abilityid_ceilings.py` / `build_tcablist_ceiling.py` → `0xBA`.
- **Names:** `re_tools/ability_names.py` `MODDED`.

**MP:** no draw is added or moved; only amounts and thresholds change.

**In-game checklist** (assign weaknesses in the editor, then fight):
1. A Fire-Weak unit hit by fire takes about half as much again, and is set Burning more often.
2. With Fire Protection as well: normal damage and normal odds.
3. With Fire Immunity: no fire damage at all.
4. A Magic-Weak unit under Magic Bolts takes ×1.5 with no status effect.
5. The ability shows on the unit card and in the in-combat panel with its description.
6. It is not offered at hero level-up.
7. The AI's turn with such units raises no "Error during Create Unit List".
8. A strategic hit (a storm spell on the world map) on a weak unit is also ×1.5.
9. A save with weak units reloads with the abilities intact.

## Liquid Body — Swimming, Physical Protection and no Burning (`0xBA`)

**🔨 APPLIED, UNTESTED (2026-09-25).** Scripts `build_liquidbody.py` (AoWEPACK.dpl) and
`build_liquidbody_pfs.py` (`Release/Ability.pfs` key 196). The script docstring is the full record.
Owner's design: Water Elementals get Liquid Body in place of Swimming + Physical Protection, so they
can't be set Burning without the lava walking Fire Immunity brings. The owner assigns it in the editor.

**Why not Liquid Form (`0xA6`).** It already gives Swimming + Physical Protection, but it is a spell
enchantment: its mask is `0x0000` (the editor never offers it), `TUnitEnchantmentAbility.GetSourceName
@0x55765784` reads the cast record without a nil check, and a unit that merely starts with the
enchantment has no cast record. Magebane also counts it as an enchantment.

**What it does.**
- **Swimming and Physical Protection:** the `0xA6` queries in `GetAbMoveTypesAll` (`0x5574F80B`) and
  `GetAbProtectionTypesAll` (`0x5574F9A3`) become "`0xA6` or `0xBA`", through one shared cave.
- **No Burning:** `TAbstractUnit.ExecuteCombatDamageEffects @0x55781ED8` is the only place Burning
  (`0x7F`) is added: fire bit 0 of the effect mask, after `~immunity & mask`. A unit with `0xBA` skips
  that block. Fire damage is unchanged, the upstream fire roll still happens (draw count unchanged), and
  fire no longer thaws a Frozen Liquid Body unit, since vanilla only thaws when Burning lands.
- **Registration:** `CreateEnhancementAbility` spliced at the vanilla `call RegisterAbility`
  `0x557BCDC6` (the Crusader registration). Mask `0x0201` = astUnit | astEditor: units only, never
  items, level-up or leader customisation. **Proved by launching `AoWz.exe` to the main menu with no
  error dialog, 2026-09-25.**
- **Record:** cloned from Physical Protection's (key 87): SFX and empty image list kept, mask `01 02`,
  no tag 6.
- **Ceiling LADDERs:** `0xBB` in both scripts. **Names:** `re_tools/ability_names.py` `MODDED`
  (the ceiling scripts read the highest id from there).

Caves `0x5584E200` (`cave_or` 28 B), `0x5584E220` (`cave_burn` 37 B), `0x5584E250` (`cave_reg` 64 B
with the name). Surgical `--undo` on both scripts.

**In-game checklist** (give a Water Elemental Liquid Body in place of Swimming + Physical Protection):
1. It swims and enters water exactly as before, and cannot cross lava.
2. Physical hits do half damage, as with Physical Protection.
3. Fire hits damage it but never set it Burning (Fire Bolt, a fire-striking melee unit, fire hexes).
4. The same in auto-combat.
5. The ability shows on the unit card with its description, and the editor offers it for units but
   not items.
6. A save with the unit reloads with the ability intact.

## Open items

- **Every `🔨 APPLIED, UNTESTED` row in the status table** needs the user's in-game pass before it
  can move to confirmed — see each feature's own section for what specifically to check. Magebane
  and its description are the oldest untested pair in this file (first applied 2026-07-30).
- **The bit-only-passive band above the `0xCD` save-tag ceiling (`0xCE`–`0xFF`) is unverified in
  either direction.** Nothing in this project has shipped an ability up there yet. A full save/load
  round trip (and an MP sync test, if relevant) with a bit-only ability registered at, say, `0xD0`
  would settle it either way and is a cheap, self-contained experiment.
- **Whether the engine tolerates a registered ability with no `Ability.pfs` record at all**, on the
  very first launch after `--apply` and before any DevEd round trip, is asserted safe only by
  precedent (Path of Sand, Assassin, Magebane, Drillmaster and the four Caster Cost abilities all
  went through this state and none crashed) — nobody has actually recorded it as a targeted test.
- **Copper Medal's ability-owner slot**: no unit currently carries `Unitres.pfs` tag `0x20`, so the
  whole mechanism is exercised only by the editor round trip described in that section's checklist,
  never yet in a real battle.
- **Caster Cost's two non-blocking follow-ups** (empty tag-5 descriptions on all four; Enchanter and
  Ritualist reading a live cost of 30 instead of the intended 40) remain open DevEd edits.
- **The spellcasting-economy caves above are unowned.** Claiming them with a real script (address,
  `--undo`, a doc row) is worth doing before either ladder is next retuned, so the change has a
  revert path.
- **Whether the tactical AI actually *scores* a battle correctly with a high-id ability enabled**,
  post-`AbilTypes`-relocation, has not been explicitly re-confirmed in a real battle — only that the
  visual symptom that first found the gap (Shield missing from a popup) no longer reproduces. A
  battle where the AI controls a unit carrying Magebane, Drillmaster, or one of the four Caster Cost
  abilities would close this.

## Failed approaches — do not retry

- **Registering a combat-facing ability through the strike factory (`FUN_5576727C` →
  `TStrikeEnhancementAbility`) instead of `CreateEnhancementAbility`.** The ability registers, lists,
  and displays correctly everywhere in the UI — and its combat-side `GetAbilityEnabled` always
  returns FALSE, so no combat bonus can ever fire. Proven with a `--diag` build that dropped the
  gate and watched nothing happen. Always use `CreateEnhancementAbility` for a new combat-facing
  passive.
- **Hooking only the global `CreateStrikeCA` for a melee "vs-type" bonus.** Covers Round Attack,
  attacks-of-opportunity and ability strikes, but never a normal deliberate melee attack — that path
  routes through the separate `TMeleeRound.CalculateStrikes`. Both must be hooked; see Assassin's
  "two parallel tables" finding above for the full map of which of the three duplicate functions
  each kind of attack actually reaches.
- **Hooking `TMeleeRound.CalculateUnitStrikes` as a believed "strategic twin" of the deliberate-melee
  path.** Changed nothing observable — that function serves the opportunity/predictor evaluation
  only, operates on strategic rather than combat objects, and is not on the path a landed strike
  takes. Removed once the actually-correct function (`CalculateStrikes`, easily confused by name
  with `CalculateUnitStrikes`) was identified by tracing the real call chain.
- **Believing "our ids are safe above the vanilla tactical bound because they're all
  `TEnhancementAbility` and therefore never selectable."** True of the map-click selection path
  (`SelectAbility`), and false of the four `TCAI.EvalBattle` AI-scoring scan loops, which have no
  selectability gate of any kind between the enabled-test and the hardware `BOUND`. Acted on as if
  it were universally true, this shipped and crashed in a real game on 2026-09-01
  ("Error during Create Unit List"). Fixed by relocating `AbilTypes` to a wider table rather than by
  re-deriving a safety argument about selectability a second time — enumerate the actual *callers*
  of a bound, never generalise from one caller that happens to be safe.
- **Testing hero-ness by VMT instance size** (`0x48` vs `0x9C`) instead of `IsClass`. Rebase-free and
  tempting, but a class's instance size in this project has already grown once mid-project
  (`TUnitResource`, for the Copper Medal ability-owner slot above) — a size check is one future
  refactor away from silently misclassifying every unit. `IsClass` costs one extra delta-trick and
  is correct by construction.
- **Treating a static constructor/call-site sweep of ability ids as a reliable free-id list.** It is
  a lower bound only: it has provably missed real vanilla ids (Tunneling, Monster Slaying, Life
  Stealing, and the mod's own Path of Sand) and has produced at least one false positive from
  unrelated city-AI code matching the same byte pattern. Only a dynamic registration probe (attempt
  to register, watch for the duplicate-id assert) is trustworthy for an apparent gap.
- **Widening `AoWTCPCK.dpl`'s `AbilTypes` bound in place instead of relocating the table.** The two
  bytes of alignment padding immediately after the 170-byte table, and the whole of the adjacent
  `SpellTypes` table beyond that, would have been read as ability-AI-category data for any id ≥ 170
  — two specific ids in this project's own range would have read nonzero "fake" categories and been
  scored by the AI as attack actions of an undefined kind. Relocating to a fresh 256-entry table was
  necessary, not a tidiness preference.
