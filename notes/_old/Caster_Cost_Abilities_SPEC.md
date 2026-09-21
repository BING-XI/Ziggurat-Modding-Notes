# Caster cost abilities — BUILD SPEC

**Status: BUILT AND CONFIRMED WORKING 2026-08-27.** Kept as the design record — the
membership tables, per-site derivations and register analyses behind
`build_scripts/build_caster_cost.py`. Current state lives in `Caster_Cost_Abilities.md`. Dated 2026-08-26.
Supersedes `Caster_Abilities_Feasibility_2026-08-25.md` §3 entirely (Evoker is a *cost* ability now,
not a damage ability; there are no upkeep patches).

---

# BUILD-READY SPEC — `build_caster_cost.py`
### Evoker / Conjurer / Enchanter / Ritualist — four bit-only cost-halving hero abilities

**Status: SPECIFICATION ONLY — nothing applied. Supersedes §3a of `Modding Resources/Zig notes/Caster_Abilities_Feasibility_2026-08-25.md` and replaces its §3b/§3c/§3d/§3e entirely.**

*All addresses are `AoWEPACK.dpl` preferred-base VAs unless another binary is named. Every byte quoted below was re-read from the live install on 2026-08-26 (`AoWEPACK.dpl`, 2 785 792 B, mtime **2026-08-26 03:37**) and byte-compared against `Modding Resources/AoWEPACK_original_backup.dpl`. ⚠ **The live DLL changed after all four probes ran** — see §7.*

---

## 1. SCOPE

Four new bit-only `TEnhancementAbility` hero passives, ids `0xAC`–`0xAF`, each halving the **initial casting cost** (`[spell+0x14]`, `Spells.pfs` tag `0x0D`) of one spell family: **Evoker** → the 30 `TCombatSpell` classes, **Conjurer** → the 13 `TSummonSpell` classes, **Enchanter** → the 18 `TUnitSpell` classes, **Ritualist** → the 12 `TGlobalEnchantmentSpell` classes. The discount is proportional (`shr 1`), applied once per cost evaluation inside `THero.CastingMana`, floored at 1 unless the spell's base cost is genuinely 0. Explicitly **OUT OF SCOPE**: any damage change (Evoker is a cost ability now, not a damage ability — the four `CreateCA` arg-site hooks of the old §3e are cancelled), any per-turn upkeep change (`SetupEnchantment @0x557EF914` and `TUnitEnchantmentAbility.Expand @0x55765894` are **not** touched), any research-cost change, any icon, any level table, any per-owner data record, and any patch to `AoW.exe` / `AoWCompat.exe` / `AoWTCPCK.dpl` / `aowInt.dpl`. Only `AoWEPACK.dpl` and `Release/Ability.pfs` are written.

---

## 2. MEMBERSHIP TABLE

Derived this session from the live DLL: 857 VMTs found by the Delphi self-pointer at `VMT−0x40`; 117 carry `[VMT+0x18] == 0x55779234` (`AoWE.TSpell.ReadWrite`, un-overridden across the whole subtree); 108 of those have a concrete spell id read from their own `<Unit>.<Class>.Create` (`mov dword ptr [reg+0x10], imm32`). Names from `Modding Resources/Zig notes/spell_names.json` (**zero class mismatches** against the VMT walk); mana from `Release/Spells.pfs` tag `0x0D`, record id = spell id + 10.

Counts: **COMBAT 30 · SUMMON 13 · UNITSPELL 18 · GLOBALENCH 12 · none 35 = 108.**

### EVOKER — `0xAC` — combat spells (30)

| id | name | mana | id | name | mana | id | name | mana |
|---|---|---|---|---|---|---|---|---|
| 100 | Solar Flare | 3 | 110 | Slow | 1 | 120 | Frost Beam | 17 |
| 101 | Turn Undead | 11 | 111 | Entangle | 6 | 121 | Vaporize | 11 |
| 102 | High Prayer | 12 | 112 | Tremors | 14 | 122 | Stoning | 2 |
| 103 | Death Rays | 4 | 113 | Call Flames | 2 | 123 | **Flaming Arrow** | **0 (no tag 0x0D)** |
| 104 | Disease Cloud | 4 | 114 | Fire Breath | 8 | 124 | Ooze | 1 |
| 105 | Terror | 10 | 115 | Swarm | 6 | 125 | Sacred Wrath | 17 |
| 106 | Mind Decay | 12 | 116 | Great Hail | 24 | 126 | Winds of Fury | 3 |
| 107 | Chain Lightning | 5 | 117 | Triple Fireball | 5 | 127 | Shock Wave | 11 |
| 108 | Cold Breath | 8 | 118 | Geyser | 8 | 128 | Sacrificial Flame | 21 |
| — | *(109 is a registry hole)* | | 119 | Ice Shards | 6 | 129 | Recall Spirits | 16 |
| | | | | | | 130 | Animate Dead | 20 |

### CONJURER — `0xAD` — summons (13)
20 Summon Black Spider (12) · 21 Summon Fire Sprites (36) · 22 Summon Frog (18) · 23 Summon Great Eagle (33) · 24 Summon Syron (240) · 25 Summon Gold Dragon (120) · 26 Summon Black Dragon (120) · 27 Summon Air Elemental (60) · 28 Summon Earth Elemental (60) · 29 Summon Fire Elemental (60) · 30 Summon Water Elemental (60) · 31 Summon Boar (9) · 78 Craft Aether Barge (150)

### ENCHANTER — `0xAE` — unit spells (18)
8 Dispel Magic (20) · 15 Haste (15) · 16 Enchant Weapon (20) · 17 Stone Skin (8) · 32 Free Movement (12) · 33 Fury (4) · 35 Remedy (8) · 36 Holy Champion (24) · 37 Unholy Champion (24) · 39 Concealment (8) · 40 Fire Halo (15) · 42 Water Walking (7) · 43 Wind Walking (11) · 49 Liquid Form (30) · 55 Healing Water (5) · 56 Bless (20) · **59 Cosmagic Scrying (15)** · 77 Dark Gift (24)

> The old study excluded ids 8 / 35 / 55 (Dispel Magic, Remedy, Healing Water) via `[spell+0x3c] == 0`. **Do not carry that filter over.** It was a *damage/duration* filter, irrelevant to a cost discount, and `[spell+0x3c] == 0` is the common case file-wide (`TCombatSpell.Create` writes 0 to it at `0x557F723A`). All 18 `TUnitSpell` classes are in.

### RITUALIST — `0xAF` — global enchantments (12)
44 Enchanted Roads (120) · 45 Water Mastery (250) · 46 Hatred (110) · 47 Tranquility (60) · 48 Power Leak (100) · 50 Flood (90) · 60 Air Mastery (250) · 61 Life Mastery (220) · 62 Death Mastery (200) · 63 Fire Mastery (200) · 64 Earth Mastery (250) · 65 Spell Ward (100)

### NOT COVERED (35)
1 Conceal Area · 2 Bird's View · 3 Fire Storm · 4 Ice Storm · 5 Death Storm · 6 Divine Storm · 7 Lightning Storm · 9 Pestilence · 10 Freeze Water · 11 Fire Barrier · 12 Poison Plants · 13 Holy Woods · 14 Evil Woods · 18 Level Terrain · 19 Raise Terrain · 34 Warp Party · 38 Town Gate · 41 Desiccate · 51 Disjunction · 52 Pyre of Vitality · 53 Gold Rush · 54 Anti Magic Shell · 57 Watcher · 58 Warmonger · 66 Resurrect Hero · 67 Animate Hero · 68 Tornado · 69 Call Hero · 70 Vortex · 71 Town Quake · 72 Anarchy · 73 Healing Showers · 74 Cloud of Ashes · 75 Crusade · 76 Animate Ruins

### Overlap and precedence

**There is no overlap and it is structural, not coincidental.** `TCombatSpell`, `TSummonSpell`, `TUnitSpell` and `TGlobalEnchantmentSpell` are four *sibling* branches directly under `TSpell` in a single-inheritance hierarchy (measured from `vmtParent` at `VMT−0x18`, double-deref). No spell can be in two, so **the cave's test order is free and cannot misclassify**. Id ranges are disjoint too (combat ≥ 100, everything else ≤ 78).

One semantic caveat the coder should not act on but should know: 18 non-combat spells *are* castable during tactical combat (`AoWTC.SpellTypes[id] != 0`, `AoWTCPCK.dpl` DATA `@0x4672F4`) — 17 unit spells (⚠ **not** 18: `SpellTypes[59] = 0`, Cosmagic Scrying is not combat-castable) plus 41 Desiccate. This spec uses the **class** reading of "combat spell", which is the one with a clean exclusive runtime test and zero Evoker/Enchanter collision.

---

## 3. THE CLASSIFICATION TESTS

All four are rebase-invariant **slot differences** — the difference of two VMT slots cancels the load delta, so no `call $+5; pop; sub` anchor is needed. The anchor slot `VMT+0x18` holds `AoWE.TSpell.ReadWrite @0x55779234` for **all 117** subtree classes (exactly one distinct value — verified live).

| family | test | constant | matching VMTs | file-wide false positives |
|---|---|---|---|---|
| Summon | `[VMT+0x6C] − [VMT+0x18]` | `0x0006B27C` | 14 (base + 13) | 0 |
| Global ench. | `[VMT+0x6C] − [VMT+0x18]` | `0x000767E0` | 13 (base + 12) | 0 |
| Unit spell | `[VMT+0x6C] − [VMT+0x18]` | `0x00001FF4` | 19 (base + 18) | 0 |
| Combat (pre-filter) | `[VMT+0x6C] − [VMT+0x18]` | `0x00000120` | 32 (abstract `TSpell` + 31 combat) | 0 |
| Combat (confirm) | `[VMT+0x80] − [VMT+0x18]` | `0x0007E034` | 31 (base + 30) | **0 across all 857 VMTs in the file** |

Measured `VMT+0x6C` difference histogram over the 117-class subtree (live file, reproduced digit-for-digit from the probes): `0x120`×32, `0x1FF4`×19, `0x255B0`×14, `0x37818`×10, `0x54AEC`×7, `0x6B27C`×14, `0x767E0`×13, plus 8 singletons. `VMT+0x80` histogram: `0x258`×86, `0x7E034`×31.

Slot identities: `VMT+0x6C` = `TSpell.Activate @0x55779354`; `VMT+0x80` = `TSpell.GetCombatDamageValue @0x5577948C`, overridden to `CombatSpells.TCombatSpell.GetCombatDamageValue @0x557F7268` (file offset `0x0F6668`) and inherited unchanged by all 30 subclasses. `0x557F7268 − 0x55779234 = 0x0007E034`.

**Every one of those slots, on every one of the 117 classes, is byte-identical between the live DLL and the pristine backup.** Nothing here is Ziggurat-patched.

**Why the combat test is two-stage.** `TCombatSpell` does *not* override `Activate`, so its `+0x6C` difference is `0x120` — shared with the abstract `TSpell` base. `TSpell` is never registered and can never reach `CastingMana`, so `0x120` alone would work; the `+0x80` confirmation costs 15 bytes and makes the test provably exclusive. Use both.

**Do NOT use these fallbacks** (all measured, all worse):
- `cmp byte ptr [esi+0x22], 1` for unit spells — works today but `+0x22` is a *default* value, not a marker (`TCombatSpell.Create` writes 0 at `0x557F721B`, which a zeroed instance already has).
- `[spell+0x22] == 2` for global enchantments — `stGlobal` is carried by 60 of 108 spells including every summon.
- Instance size `[VMT−0x1C] == 0x40` for combat — unique inside the subtree but **not** file-wide (45 classes DLL-wide, 14 outside the spell subtree, e.g. `TAgeOfWondersEngine`, `TCrypt`, `TFireStorm`).
- `System.@IsClass` with a classref — needs either a new `.reloc` entry or a 30-byte parent walk.

**Register clobbers of the whole classification block: `ECX` and `EDX` only.** `EAX` (caster), `EBX` (base cost) and `ESI` (spell) survive. Both are dead at the resume point (the mastery cave writes `EDX` in full at `0x55812886` and `ECX` at `0x55812895` before reading either; and `EAX` is reloaded from the global at `0x557894F3`).

---

## 4. THE COST CAVE

### 4.1 Architecture — TWO hooks, not one

> ⚠ **This is the single most important correction in this spec.** A floor applied in the prologue **does not survive the function**. Live `THero.CastingMana` hands control at `0x557894F8` to `build_mastery_cost.py`'s cave at `0x55812880`, which then *rescales EBX*: `imul eax,ebx,3 / shr eax,2` (×0.75) at `0x558128A7` or `imul eax,ebx,3 / shr eax,1` (×1.5) at `0x558128B1`, then `jmp 0x55789510`. **EBX = 1 through the ×0.75 arm yields `3 >> 2 = 0`.** So the floor must be enforced at the function **exit**.

The exit is a single, clean, 5-byte convergence point.

```
55789510  8b c3     mov eax, ebx      \
55789512  5e        pop esi            |  the whole vanilla epilogue, exactly 5 bytes
55789513  5b        pop ebx            |
55789514  c3        ret               /
```

Verified this session, whole-file scan of every `E8`/`E9`/`Jcc8`/`Jcc32`/absolute-dword reference:

- Only **three** arrivals, and **all three target `0x55789510` exactly** — fall-through from `0x5578950E`, `je 0x55789510` at `0x55789508`, and `jmp 0x55789510` at `0x558128B8` (the mastery cave). Nothing lands mid-range.
- **Zero** `.reloc` entries in `0x55789510..0x55789514` (full walk, 63 883 type-3 entries; nearest neighbours `0x557894F4` and `0x55789654`).
- **Zero** absolute dword references in CODE or DATA.
- Bytes are byte-identical to the pristine backup, and the only build-script mention is two comment lines in `build_mastery_cost.py` (lines 64 and 102) — not a claim.

This makes the two halves **fully orthogonal to `build_mastery_cost.py`**: if mastery is later `--undo`'d, the vanilla tail falls through to `0x55789510` and the floor still runs; if *this* feature is `--undo`'d, the mastery cave's `jmp 0x55789510` lands on the restored epilogue. Neither script's verify-before-write touches the other's bytes.

### 4.2 HOOK 1 — `0x557894EC` (7 bytes)

| | |
|---|---|
| Site | `AoWE.THero.CastingMana` entry, file offset `0x0888EC` |
| Displaced | `53 56 8B F2 8B 5E 14` (7 bytes = `push ebx; push esi; mov esi,edx; mov ebx,[esi+0x14]`) |
| Replacement | `E9 <rel32>` + `90 90` |
| Resume | `0x557894F3` (`mov eax,[0x558FA040]`, whose imm32 reloc at `0x557894F4` is untouched) |
| `.reloc` in window | **none** |
| Live == vanilla | **yes** |

Entry state: `EAX` = Self (caster), `EDX` = spell, stack = `[ret]`. **`EAX` is not always a `THero`** — `TUnitSpellCaster.GetRequiredMana @0x5577A49C` passes a `TUnit` from `TUnitControl.FindUnit`, and `TCombatSpell.CreateCA` passes `[combatUnit+0x4C]`.

### 4.3 `cave_cost` — assembled, 120 bytes

Assembled with keystone at `0x55820800` and capstone round-tripped. The first 7 bytes are the **literal displaced bytes**, not re-assembled (⚠ keystone renders `mov esi,edx` as `89 D6`, not the original `8B F2`; a re-assembled replay would fail any byte-for-byte verifier and the `--undo` comparison).

```asm
cave_cost:                              ; EAX=caster  EDX=spell
  53                    push  ebx                    ; \
  56                    push  esi                    ;  | EXACT replay of the
  8b f2                 mov   esi, edx               ;  | displaced 7 bytes
  8b 5e 14              mov   ebx, [esi+0x14]        ; /  EBX = base cost, ESI = spell
; ---- guards (see §10) --------------------------------------------------
  85 c0                 test  eax, eax
  74 68                 jz    .back                  ; nil Self
  8b 08                 mov   ecx, [eax]             ; Self VMT
  39 49 c0              cmp   [ecx-0x40], ecx        ; Delphi vmtSelfPtr sanity
  75 61                 jne   .back
; ---- classification: one +0x6C difference for three families ----------
  8b 0e                 mov   ecx, [esi]             ; spell VMT
  8b 51 6c              mov   edx, [ecx+0x6c]
  2b 51 18              sub   edx, [ecx+0x18]
  81 fa 7c b2 06 00     cmp   edx, 0x0006B27C
  74 30                 je    .conj
  81 fa e0 67 07 00     cmp   edx, 0x000767E0
  74 2f                 je    .ritu
  81 fa f4 1f 00 00     cmp   edx, 0x00001FF4
  74 2e                 je    .ench
  81 fa 20 01 00 00     cmp   edx, 0x00000120        ; combat pre-filter
  75 39                 jne   .back
  8b 91 80 00 00 00     mov   edx, [ecx+0x80]        ; combat confirm
  2b 51 18              sub   edx, [ecx+0x18]
  81 fa 34 e0 07 00     cmp   edx, 0x0007E034
  75 28                 jne   .back                  ; abstract TSpell lands here
  ba ac 00 00 00        mov   edx, 0xAC              ; Evoker
  eb 13                 jmp   .query
.conj:
  ba ad 00 00 00        mov   edx, 0xAD              ; Conjurer
  eb 0c                 jmp   .query
.ritu:
  ba af 00 00 00        mov   edx, 0xAF              ; Ritualist
  eb 05                 jmp   .query
.ench:
  ba ae 00 00 00        mov   edx, 0xAE              ; Enchanter
.query:                                              ; EXACTLY ONE query per cast
  8b 08                 mov   ecx, [eax]             ; caster VMT (EAX still the caster)
  ff 91 48 01 00 00     call  dword ptr [ecx+0x148]  ; item-aware GetAbilityEnabled
  84 c0                 test  al, al
  74 02                 jz    .back
  d1 eb                 shr   ebx, 1                 ; NO floor here — see cave_floor
.back:
  e9 <rel32>            jmp   0x557894F3
```

**Register safety across the query — measured, not assumed.** `THero.GetAbilityEnabled @0x5578827C` opens `push ebx; push esi` and closes `pop esi; pop ebx; ret`; so does `TAbstractUnit.GetAbilityEnabled @0x5577F5E0`. Neither touches `EDI` or `EBP`. `EBX` (cost) and `ESI` (spell) therefore survive; `EAX`/`ECX`/`EDX` are clobbered and all three are dead at `0x557894F3`. (The tail is an indirect `call [ecx+0x74]` → `TAbility.GetEnabled @0x5574EEF4`, four instructions; preservation there rests on the Borland ABI, which every other cave in this project already relies on.)

**`VMT+0x148` is correct for every Self that reaches this site** — measured live:

| class | VMT | `+0x148` |
|---|---|---|
| `THero` | `0x55711FEC` | `0x5578827C` `THero.GetAbilityEnabled` |
| `TLeader` | `0x55712238` | `0x5578827C` |
| `TUnit` | `0x55710CAC` | `0x5577F5E0` `TAbstractUnit.GetAbilityEnabled` |
| `TAbstractUnit` | `0x55710740` | `0x5577F5E0` |
| `TAdjustableUnit` | `0x55712A54` | `0x5577F5E0` |
| `TWallUnit` | `0x55712C84` | `0x5577F5E0` |
| ⚠ `TCombatUnit` | `0x55715A94` | `0x55715BE0` — **past the end of its VMT, RTTI blob** |
| ⚠ `TFastCombatUnit` | `0x5571D4BC` | `0x74696E55` — **ASCII `'Unit'`** |

A `TCombatUnit` never reaches `CastingMana` (`TCombatSpell.CreateCA` bridges through `[combatUnit+0x4C]` at `0x557F730A` first), so `+0x148` is safe here — but the two garbage rows are why the `vmtSelfPtr` guard is in the cave and why nobody may copy this call into a combat-side hook. On the combat side the forwarder is `TCombatUnit.GetAbilityEnabled @0x55725004` at combat `VMT+0xA8`.

### 4.4 HOOK 2 — `0x55789510` (5 bytes) and `cave_floor` — 20 bytes

| | |
|---|---|
| Site | shared vanilla epilogue, file offset `0x88910` |
| Displaced | `8B C3 5E 5B C3` (exactly 5 bytes) |
| Replacement | `E9 <rel32>` |
| `.reloc` in window | **none** |
| Live == vanilla | **yes** |

```asm
cave_floor:                             ; EBX = final cost, ESI = spell
  85 db                 test  ebx, ebx
  75 0b                 jnz   .out
  83 7e 14 00           cmp   dword ptr [esi+0x14], 0
  74 05                 je    .out            ; base cost genuinely 0 -> stays 0
  bb 01 00 00 00        mov   ebx, 1
.out:
  89 d8                 mov   eax, ebx        ; \
  5e                    pop   esi             ;  | the vanilla epilogue,
  5b                    pop   ebx             ;  | executed here
  c3                    ret                   ; /
```

`ESI` is provably the spell at every arrival: `mov esi,edx` at `0x557894EE`, and nothing in the function or in the mastery cave rewrites `ESI`.

**Why the floor is conditional.** Spell 123 **Flaming Arrow costs 0 mana today** — `TFlamingArrow.Create @0x557F94D8` sets the id at `0x557F952D` and never writes `[obj+0x14]`, and `Spells.pfs` record 133 is the **only one of 108** with no tag `0x0D`. An unconditional floor would raise it from 0 to 1, i.e. the "discount" would nerf it. The `cmp [esi+0x14], 0` guard keeps it free.

**Why a zero cost must never reach the caller.** `THero.CastingDone @0x557893E8` does `SetMana(mana − 0)` **and** `sub byte ptr [hero+0x80], 0` — unlimited casting that consumes neither mana nor casting points. (It does *not* crash: `THero.CastingTurns @0x55789518` divides by `GetCastingPointsMax` at `VMT+0x128`, not by `CastingMana`, and early-outs at `0x55789552` before the `idiv`. The old study's reasoning here was right; its stated reason was wrong.)

> **DECIDED — shipped 2026-08-26, confirmed 2026-08-27.** `cave_floor` fires for *every* caller, including heroes with none of the four abilities, and that is intended: before it, Slow (1) and Ooze (1) cast by a hero holding the matching Sphere Mastery returned **0 mana** (`(1×3)>>2 = 0`), i.e. free and consuming no casting points — a live `build_mastery_cost.py` defect nobody had noticed. The floor repairs it as a side effect.

### 4.5 Composition order with the mastery cave

Forced by the architecture: **base → our halving → mastery multiplier → floor.** Both the halving and the mastery multiplier truncate. The two orders usually agree but not always:

| spell | base | ability + opposed-sphere Mastery | ours-first | mastery-first |
|---|---|---|---|---|
| Animate Dead | 20 | Evoker + own sphere ×0.75 | 20→10→**7** | 20→15→**7** |
| Water Walking | 7 | Enchanter + opposed ×1.5 | 7→3→**4** | 7→10→**5** |

Record the chosen order in the doc. Two mastery-cave facts the coder needs and no existing doc states: it **bypasses the vanilla sphere-doubling tail entirely** (`jmp 0x558128B8 → 0x55789510` skips `0x557894FE..0x5578950E`), and it inlines its own copy of `GetSphereManaDoubled`'s table probe **without** the `and edx,0x7F` mask that the real function at `0x5577E230` applies.

`build_mastery_cost.py` verifies only its own 6 bytes at `0x557894F8` (`HOOK_ORIG = 8b8088010000`) and reserves `CAVE_LIMIT = 0x60` bytes from `0x55812880`. **Neither of our two hooks touches either range**, so its `--apply` zero-check and its `--undo` both continue to work untouched.

---

## 5. THE REGISTRATION CAVE

### 5.1 Ids — free, verified three ways this session

- `Release/Ability.pfs`: 151 records, keys 10..181 → highest ability id in use `0xAB` (Drillmaster). **No records 182–185.**
- `call AoWE.CreateEnhancementAbility (0x5576601C)`: 25 sites, ids `{1A 25 27 29 2B 31 33 36 38 3F 43 44 45 6D 8A 8B 8C 8D 8E 8F 90 91 9F AA AB}`, max `0xAB`.
- `call AoWE.TAbilityControl.RegisterAbility (0x55750238)`: 151 `E8` sites, zero `E9`.
- **No data file grants an ability id ≥ 0xAC** — swept every `.pfs` in `Release/`: `Unitres.pfs` max 171 (`0xAB`), `HEROES.PFS`/`ITEMS.PFS` max 147, everything else lower.

Assignment: **Evoker `0xAC` · Conjurer `0xAD` · Enchanter `0xAE` · Ritualist `0xAF`.** Freeze these before anything ships — ids are serialised into saves as bit indices, and every MP peer must run byte-identical binaries. Registering a taken id raises `'Ability already registered ('` (string `@0x55750390`), which Delphi surfaces as a bare `Runtime error 217` before the main window.

> ⚠ `Modding Resources/Zig notes/Ability_ID_Budget.md` lines 19 and 124–125 still advertise "`0xAB`–`0xCD`: 35 contiguous free ids". `0xAB` is Drillmaster. Correct that doc at source.

### 5.2 Splice site — `0x557BCF04`

| | |
|---|---|
| Host | `PassiveAb.RegisterPassiveAbilities @0x557BC1CC` (prologue sets `EBX := Self` at `0x557BC1D4`; `ret` at `0x557BCF8D`) |
| Site | `0x557BCF04` = `E8 2F 33 F9 FF` = `call 0x55750238`, registering ability `0x8F` |
| Replacement | `E8 <rel32 to cave_reg>` — 5 bytes, no nops |
| `.reloc` in window | **none** (nearest `0x557BCEF2` and `0x557BCF0D`) |
| Live == vanilla | **yes** |

86 free `call RegisterAbility` sites remain in the window `0x557BC000`–`0x557BD200`, and **all 86** are immediately preceded by `8B C3` (`mov eax,ebx`) — `EBX` liveness is 86/86. `0x557BCF04` is the highest. Four sites are already consumed and must not be reused: `0x557675C4` (Assassin), `0x557BC9E9` (Path of Sand), `0x557BCF39` (Drillmaster), `0x557BCF6E` (Magebane).

### 5.3 `cave_reg` — shape and per-ability body

Copy the **Drillmaster** cave at `0x55816000`, which is the only complete precedent (see §8). Its live bytes:

```
55816000  e8 33 a2 f3 ff        call 0x55750238        ; replay the displaced call
55816005  e8 00 00 00 00        call $+5               ; PIC anchor
5581600A  58                    pop  eax               ; EAX = 0x5581600A at runtime
5581600B  8d 90 2a 00 00 00     lea  edx, [eax+0x2A]   ; -> the string bytes
55816011  b9 ff 03 00 00        mov  ecx, 0x3FF        ; only CX is read
55816016  b8 ab 00 00 00        mov  eax, 0xAB
5581601B  e8 fc ff f4 ff        call 0x5576601C        ; CreateEnhancementAbility -> EAX
55816020  89 c2                 mov  edx, eax
55816022  89 d8                 mov  eax, ebx
55816024  e8 0f a2 f3 ff        call 0x55750238        ; RegisterAbility
55816029  c3                    ret
5581602C  ff ff ff ff 0b 00 00 00 "Drillmaster" 00     ; the AnsiString literal
```

**AnsiString literal format (confirmed byte-for-byte):** `FF FF FF FF` (refcount −1 — `LStrAsg` shares it and never frees) + `<u32 length>` + the bytes + a `NUL`. **`EDX` must point at the bytes, i.e. blob + 8.**

**Four registrations, not one — do not reuse a single anchor.** `mov eax, <id>` destroys the anchor in `EAX`, and `ESI`/`EDI` are **not** saved by the host function (its prologue pushes only `EBX`), so parking the anchor there would corrupt the host's caller. **Recompute the anchor per ability** — 6 bytes each, zero register-lifetime assumptions:

```asm
cave_reg:
  e8 <rel32>            call 0x55750238        ; replay the displaced call (ability 0x8F)
  ; ---- repeat this 40-byte block four times, id/cost/name varying ----
  e8 00 00 00 00        call  $+5
  58                    pop   eax
  8d 90 <d32>           lea   edx, [eax + (name_va - anchor_va)]
  b9 ff 03 00 00        mov   ecx, 0x03FF      ; TAbilitySelectionTypes: all ten bits
  b8 ac 00 00 00        mov   eax, 0xAC
  e8 <rel32>            call  0x5576601C       ; -> EAX = the ability object
  c7 40 14 <cost32>     mov   dword ptr [eax+0x14], <cost>   ; level-up cost, see 5.5
  89 c2                 mov   edx, eax
  89 d8                 mov   eax, ebx
  e8 <rel32>            call  0x55750238
  ; ---- end block ----
  c3                    ret
  ; then the four AnsiString literals
```

`AoWE.CreateEnhancementAbility @0x5576601C` (file offset `0x06541C`, byte-identical live and vanilla): `EAX` = id → `[ability+0x0C]`; `EDX` = name AnsiString → `LStrAsg` into `[ability+0x08]`; **`CX`** = selection mask → stored as a **word** at `[ability+0x20]`; returns `EAX` = the ability. `RegisterAbility @0x55750238` parks it at `TList[[ability+0x0C]]`, padding with nils, so **the list index IS the ability id** — and therefore `Ability.pfs` record id = ability id + 10.

⚠ **Keystone:** emit `E8 00 00 00 00` as raw bytes. `call $+5` written as source assembles to nothing and the anchor search then zeroes the rel32 of whatever `E8` precedes it. Disassemble the whole cave with capstone and diff before writing.

### 5.4 Selection mask — `0x03FF`

`TAbilitySelectionType` RTTI (live, kind byte `tkEnumeration` at file `0x826C`, name at `0x826D`, members from `0x8291`): `astUnit 0x001, astHeadItem 0x002, astTorsoItem 0x004, astAttackItem 0x008, astDefenseItem 0x010, astRingItem 0x020, astUseItem 0x040, astCustomizeLeader 0x080, astHeroUpgrade 0x100, astEditor 0x200` → all ten = `0x03FF`.

**Both high bits are load-bearing and are tested in different places — never trim the mask.**
- `AoWE.TAbility.CanExpand @0x5574E8B8` ANDs `[ability+0x20]` against `owner->vmt[0x8C]`; `THero.GetAbilitySelectionTypes @0x55786B10` returns the constant word `0x0200` (**astEditor**).
- The live `AoW.exe` hero level-up fill loop tests `test byte ptr [eax+0x21], 1` at `0x00623E83` (= `0x100`, **astHeroUpgrade**).

Distribution in the live `Ability.pfs` tag 9 (read as a **u16** — `pfs.u32()` returns 0 on a 2-byte field): `0x03FF`×81, `0x0000`×32, `0x03BF`×13, `0x007E`×6, `0x007F`×4, `0x003E`×3, `0x027F`×2, `0x0381`×2, `0x0001`×2, `0x0037`×2, and one each of `0x03A1/0x003F/0x0209/0x0261`. 97 records carry `0x100`; all 97 also carry `0x200`.

### 5.5 Level-up cost — ⚠ THE CAVE CANNOT SET IT (corrected 2026-08-27)

**The original text here was wrong.** It said the cave's `mov [ability+0x14], N` "is the value that
applies on the first launch, before DevEd has minted a record — ship it anyway, it is the only thing
standing between the first playtest and four free abilities." It is not. The abilities shipped
reading **0** and had to be given tag 6 in AoWDevEd. Established from the user's in-game result and
confirmed by decompile.

**The real rule — which source wins is decided by the ability's KIND:**

| kind | where the level-up cost lives |
|---|---|
| **multi-level** (Leadership, Marksmanship, Dispel Magic, Spellcasting …) | **code.** The class overrides `ExpandCost`. `AoWE.TDispelMagicAbility.ExpandCost @0x5576D130` is literally `return 5`. `[+0x14]` and `Ability.pfs` tag 6 are both ignored. |
| **single-level / bit-only** (these four, Path of Sand, Drillmaster …) | **`Ability.pfs` tag 6.** They inherit `AoWE.TAbility.ExpandCost @0x5574E908` = `return [ability+0x14]`. |

Why the cave loses for a bit-only ability: `AoWE.TAbility.ReadWrite @0x5574F07C` hands the property
reader the **address** of the field for tag 6 —

```c
(**(code **)(*tbl + 0x2c))(tbl, ability + 0x14, 6);   // reads INTO [ability+0x14]
```

— and that load runs **after** registration. So the pfs value always overwrites the cave's, and with
no tag 6 present the field is set to **0**. Note the contrast one line above it: tag 5 is passed
`*(ability+0x10)` **by value** (the description string), tag 6 **by address**.

**Consequence:** an ability with no tag 6 is **permanently free**, not merely displayed as free —
`THero.UsedSkillPoints @0x55786CC8` sums `ExpandCost`. There is no code-side workaround for a
bit-only ability short of overriding `ExpandCost` in a cave and repointing the VMT slot, which would
convert it into the multi-level pattern for no benefit. **Author tag 6 in AoWDevEd.**

`build_caster_cost.py` keeps its `LEVEL_COST` dict only to document intent; it prints the **live tag
6** values on every run and flags any disagreement. A future rebuild of `cave_reg` should drop the
`mov [eax+0x14]` instruction entirely (7 bytes × 4).

### 5.6 ⚠ ORDERING CONSTRAINT

**The registration cave and the cost cave must ship in the same binary, applied and undone together.** `--apply` writes registration first, then the cost hooks; `--undo` removes them in the reverse order.

The precise hazard, narrower than the old study stated: `TAbstractUnit.GetAbilityEnabled` dereferences `TAbilityControl.GetAbility(id)` with **no null check** at `0x5577F60A` (`mov ecx,[eax]`; the study cites `0x5577F603`, which is the *call*). But that path is reached only past `call [ecx+0x14C]; test al,al; je 0x5577F612`, and `TAbstractUnit.GetAbilitySet @0x5577F618` opens `cmp edx,[eax+0x0C]; jae → return 0` (bit-count bound). So:

> **Querying an unregistered id on an owner that does not carry the bit returns 0 safely. The crash case is "bit set, id not registered".** Since only registration + a DevEd assignment can set the bit, and no `.pfs` grants ≥ `0xAC` today, the rule is: never ship a build that sets a bit for an id it does not register. `RegisterAbility` grows the TList so `Count` becomes id+1, which is what makes `GetAbility` safe afterwards.

Recommended sequencing for the user: apply, launch the game once (no `Runtime error 217`), do the DevEd round trips (§8), *then* playtest the discount.

---

## 6. THE WALLET QUESTION

`THero.CastSpell @0x557898B3` takes the **instant** branch when `CastingMana <= [hero+0x80]` (casting points). On the channelled branch, `THero.ExecuteStartCasting @0x55789130` deducts the whole `CastingMana` result up front (`call` at `0x557891C0`, stored at `[hero+0x8C]`, subtracted at `0x557891E5`), so **channelled casts are correct for all four abilities with no extra work**. The instant branch is where the discount can leak.

### 6.1 Four-row verdict

| ability | verdict | why |
|---|---|---|
| **Enchanter** (unit spells) | ✅ **reaches the wallet** — 17 of 18 | `TUnitSpell.CastSpell @0x5577ADFC` calls `CastingMana` at `0x5577AE3F` and stores the result at `[TE+0x1C]`; `TUnitSpellTE.Process` charges `[ebx+0x1c]` at `0x5577AC04`. `Validate` uses the same discounted value, so **no silent-fail band**. ⚠ **Exception: 59 Cosmagic Scrying** — `TCosmeticSurgery.CastSpell @0x557E87E4` overrides `VMT+0xA8` and routes through `TCosmeticSurgerySpellCaster.Cast @0x557E8524`, which pushes the **raw** `[spell+0x14]` at `0x557E85F9`. |
| **Evoker** (combat spells) | ✅ **reaches the wallet** — 24 of 30 | Tactical: `TSpell.CombatSpellCast @0x5577954C` → `CastingMana` at `0x55779557` → `CombatCastingDone @0x557794E8` → `THero.CastingDone`. Auto-resolve: `TCombatSpell.CreateCA` calls `CastingMana` at `0x557F730F` → `[CA+0x1C]`. ⚠ **Six overrides store the raw cost in auto-resolve only** — Turn Undead `0x557F7C89`, Mind Decay `0x557F8615`, Slow `0x557F89AD`, Entangle `0x557F8B59`, Recall Spirits `0x557FA2DC`, Animate Dead `0x557FA4FC`. Tactical is unaffected (`AoWTCPCK.dpl` passes charge=0 at `0x0040B98F`/`0x0040C0CF` and charges separately). No silent-fail band on this path. |
| **Conjurer** (summons) | ❌ **BROKEN both ways — MUST FIX** | Charge: `TSummonSpellTE.Process` **re-fetches the shared spell singleton** and reads the raw cost at `0x557E4353` — it never touches `[TE+0x1C]`. Validate: `TSummonSpell.Activate` writes the raw cost into `[TE+0x1C]` at `0x557E44F8`, and `TSpellTE.Validate` passes it to `CanCastSpellInstantly` at `0x557798DD`. Needs **two** sites. |
| **Ritualist** (global ench.) | ❌ **BROKEN — MUST FIX** | `TGlobalEnchantmentSpell.Activate` writes the raw cost into `[TE+0x1C]` at `0x557EFA7C`; 11 of the 12 `ExecuteTE` overrides then charge `[TE+0x1C]`. **One** site fixes charge *and* validate for 11. ⚠ `TWaterMastery.ExecuteTE @0x557F0A88` reads the raw cost directly and survives a fix at `0x557EFA7C` — but Water Mastery costs **250**, and even 250→125 (Ritualist) →93 (×0.75 Mastery) exceeds the 90-point casting ceiling, so it **can never take the instant branch**. No fix needed; record the reason. |

**The silent-fail band is the ugly part, and this feature widens it.** `TSpellTE.Validate @0x557798B8` re-checks the **raw** `[TE+0x1C]`. Both subclass `Validate` overrides (`TUnitSpellTE @0x5577AA1C`, `TGlobalEnchantmentSpellTE @0x557EF881`) call the base first. So for summons and global enchantments there are three regimes for points `P` vs raw cost `R`, discounted `D = max(1, R>>1)`:

```
P >= R        instant, RAW charged, discount invisible
D <= P < R    instant branch entered, Validate REJECTS on the raw cost -> SPELL SILENTLY DOES NOTHING
P <  D        channelled, discount correct
```

### 6.2 Instant-branch prevalence (computed live; casting-points ladder 10/20/40/60/90 from the cave at `0x5580BF00`)

| casting level | P | summons (13): raw / silent-fail / ok | global ench. (12): raw / silent-fail / ok |
|---|---|---|---|
| 1 | 10 | 1 / **2** / 10 | 0 / 0 / 12 |
| 2 | 20 | 3 / **2** / 8 | 0 / 0 / 12 |
| 3 | 40 | 5 / **4** / 4 | 0 / **1** / 11 |
| 4 | 60 | 9 / **2** / 2 | 1 / **5** / 6 |
| 5 | 90 | 9 / **3** / 1 | 2 / **4** / 6 |

At level 5, only **1 of 13 summons** and **6 of 12 global enchantments** would honour the discount, and **3 summons + 4 global enchantments would do nothing at all**. Named at L5 — silently failing: Summon Gold Dragon, Summon Black Dragon, Craft Aether Barge, Enchanted Roads, Hatred, Power Leak, Spell Ward. This is the common case, not a corner case. **Ship the fix.**

### 6.3 The fix — three sites, tier 1 (mandatory)

All three windows are `.reloc`-free and byte-identical to the pristine backup (verified this session).

**Site A — `TGlobalEnchantmentSpell.Activate`, `0x557EFA7C`.** Displace 7 bytes `8B 43 14 50 8A 4E 24`, resume `0x557EFA83`. Nearest relocs `0x557EFA6C` / `0x557EFAB3`. `EBX` = spell, `ESI` = caster (`mov esi,edx` at `0x557EFA22`).

```asm
cave_gench:                             ; 18 bytes
  89 f0                 mov   eax, esi          ; caster
  89 da                 mov   edx, ebx          ; spell
  e8 <rel32>            call  0x557894EC        ; CastingMana -> EAX
  50                    push  eax
  8a 4e 24              mov   cl, [esi+0x24]    ; replayed
  e9 <rel32>            jmp   0x557EFA83
```

**Site B — `TSummonSpell.Activate`, `0x557E44F8`.** Displace 7 bytes `8B 43 14 50 8B 45 FC`, resume `0x557E44FF`. Nearest relocs `0x557E44E6` / `0x557E4520`. `EBX` = spell, caster spilled at `[EBP-4]` (`mov [ebp-4],edx` at `0x557E44BD`). Fixes the **validate** band only.

```asm
cave_summon:                            ; 19 bytes
  8b 45 fc              mov   eax, [ebp-4]      ; caster
  89 da                 mov   edx, ebx          ; spell
  e8 <rel32>            call  0x557894EC
  50                    push  eax
  8b 45 fc              mov   eax, [ebp-4]      ; replayed
  e9 <rel32>            jmp   0x557E44FF
```

**Site C — `TSummonSpellTE.Process`, `0x557E4353`. PURE IN-PLACE, NO CAVE.** Overwrite the 7 bytes `8B 40 14 50 8B 45 FC` with `8B 45 FC FF 70 1C 90`:

```asm
557E4353  8b 45 fc      mov  eax, [ebp-4]       ; [ebp-4] is the TE (its +0x10 feeds GetSpell)
557E4356  ff 70 1c      push dword ptr [eax+0x1c]
557E4359  90            nop
557E435A  8b 50 10      mov  edx, [eax+0x10]    ; untouched — EAX is still the TE
```

Nearest relocs `0x557E4342` / `0x557E435E`. Same length, one push, `EAX` left holding the TE exactly as the original did. **Without Site C, Site B alone fixes the rejection band and leaves summons charged at full price.**

### 6.4 Tier 2 / tier 3 — optional, list them and let the user choose

- **Cosmagic Scrying (Enchanter, 1 of 18).** `0x557E85F9`, window `8B 40 14 50 8B CE 8B 53 08`. `EBX` = the spell caster, `ESI` = the caster unit (from `FindUnit` on `[ebx+0xc]` at `0x557E8573`). ⚠ **`.reloc` status of this window is UNVERIFIED — check before use.**
- **Six auto-resolve combat spells (Evoker).** Six one-line sites; each currently stores raw. Note the same gap already waives `build_mastery_cost.py`'s multiplier for those six today, so fixing it is a mastery behaviour change too.
- **AI casts charge raw on all three strategic families** — `TUnitSpell.AIExecuteCastSpellAction @0x5577B658` (raw push at `0x5577B6F0`), `TSummonSpell.AIExecuteCastSpellAction @0x557E4650`, `TGlobalEnchantmentSpell.AIExecuteCastSpellAction @0x557EFC08`. These paths are internally **raw-consistent** (budget, instant-check and charge all raw), so an AI hero suffers no silent-fail band — it simply gets no discount and no mastery scaling. Recommended: leave alone, record it.

### 6.4b THIS IS A VANILLA BUG — proven 2026-08-26

The raw-cost bypass is **original 1999 behaviour**, not something this project introduced. Proof:

1. `TSummonSpell.Activate @0x557E44F8`, `TGlobalEnchantmentSpell.Activate @0x557EFA7C` and
   `TSummonSpellTE.Process @0x557E4353` are **byte-identical** between the live DLL and
   `Modding Resources/AoWEPACK_original_backup.dpl` (`8b 43 14 50 ...` / `8b 40 14 50 ...`).
2. Vanilla `THero.CastingMana` applies the sphere penalty inline and nowhere else —
   `call GetSphereManaDoubled` at `0x55789501`, `test al,al`, `je`, then `mov eax,ebx; add eax,eax`
   at `0x5578950A`.
3. **`GetSphereManaDoubled @0x5577E230` has exactly ONE code caller** — that call site. The only
   other xrefs are its `.edata` export entry (`0x5590D1E4`, DATA) and a Ghidra entry-point artefact.
   So there is no second site that could rescue a path which skips `CastingMana`.

**Why nobody noticed, and why it matters more for us.** The direction of the modifier decides the
symptom, because `TSpellTE.Validate` re-checks the **raw** cost while `CastSpell`'s instant test
uses the **modified** one:

| | vanilla ×2 penalty | our ×0.5 discount |
|---|---|---|
| instant branch when | `2R ≤ P` | `R/2 ≤ P` |
| `Validate` re-check (`R ≤ P`) | implied by `2R ≤ P` — **cannot fail** | fails when `R/2 ≤ P < R` |
| symptom | pays `R` not `2R` — penalty silently waived | **spell does nothing at all** |

A penalty makes the gate *stricter* than the re-check, so it degrades gracefully and invisibly. A
discount loosens the gate *below* the re-check and opens a hard silent-failure band. That is the
whole reason the fix is optional-looking for Mastery and mandatory for Conjurer/Ritualist.

In vanilla the escaping spells are the cheap summons — Boar (9), Black Spider (12), Frog (18) —
while Syron (240) and the dragons (120) are too expensive to cast instantly, get channelled through
`ExecuteStartCasting`, and *are* correctly doubled. Unit spells and combat spells are unaffected:
their cast paths do call `CastingMana`.

**Consequence for scoping: Sites A–C are a vanilla bug fix, not just feature plumbing.**

### 6.5 What the fix does to `build_mastery_cost.py`

> **DECIDED — the user signed this off on 2026-08-26; shipped and confirmed 2026-08-27.** Sites A–C route instantly-cast summons and global enchantments through `CastingMana`, so the **Sphere Mastery multiplier now reaches the wallet for them, where it was previously waived in silence.** At casting level 5 that is 9 of 13 summons and 2 of 12 global enchantments newly scaled ×0.75 (own sphere) or ×1.5 (opposed sphere — a cost increase players feel). It also un-breaks mastery's own silent-fail band (`0.75R ≤ P < R`): at L5, 2 summons and 4 global enchantments that previously did **nothing at all** now work.

**MP safety:** `[TE+0x1C]` is serialised as tag `0x12` by `TSpellTE.ReadWrite @0x55779834`, so a value computed once on the casting peer is transmitted, not recomputed. **Idempotence:** `CastingMana` is pure — it recomputes from `[spell+0x14]` and never mutates the shared spell singleton — so calling it a second time for the same cast (as Sites A/B do) is safe. **Never write back into `[spell+0x14]`**: spell objects are shared singletons indexed by `TSpellControl.RegisterSpell @0x55779B40`.

---

## 7. CAVE ALLOCATION MAP — safety-critical

> ⚠ **ALL FOUR PROBES ARE STALE HERE.** They measured the last non-zero CODE byte at `0x5582040E` against a DLL with mtime 2026-08-24 23:54 (now preserved as `AoWEPACK.dpl.pre-shipyardincome`). **`build_shipyard_income.py` has since been applied** — the live DLL's mtime is 2026-08-26 03:37 and the diff against that snapshot is 96 runs / 1 813 bytes: one VMT slot at `0x557C7350` plus a new cave at **`0x55822000..0x5582283C`**, declaring an **exclusive reservation of `0x55822000..0x55822FFF` with `CAVE_LIMIT = 0x1000`** and BSS slack at `0x558FAB00`. Any doc, script comment or probe saying "nothing sits at or above `0x55820800`" is now wrong. This is precisely the failure mode that broke Dispel Magic.

### Measured live occupancy above vanilla's CODE end (`0x5580BDEE`)

Runs separated by a ≥ 0x30-byte zero gap. Owner column from `grep -ril` over `Modding Resources/build_scripts/`; "UNOWNED" means no script names the address — ⚠ **it does not mean unused**, see the note below.

| range | bytes | owner(s) |
|---|---|---|
| `5580BE00..5580BEBD` | 445* | `build_medal_hpmv.py` (calls it "a PRE-EXISTING cave pair"; **live, hooked** from `TUnit.GetMoves` `0x55782B84`, `TUnit.GetHits` `0x55782B68`, `TFireStorm.ChangeStormTerrain` `0x557CD4F0`) |
| `5580BEF0..5580BF54` | 100 | **UNOWNED but LIVE** — casting-points ladder `0x5580BF00` (from `THero.GetCastingPointsMax 0x55788639`), plus helpers called from `0x557A1B8D` and `0x557AABCC` |
| `5580BF70..5580C1A2` | 690 | arena / debuffcache / copper_medal / doubled_inventory / lifesteal_roundattack |
| `5580C211..5580C2AF` | 158 | marksmanship8 / marksmanship_atk2 |
| `5580C390..5580C456` | 134 | lifesteal_roundattack |
| `5580C500..5580C5ED` | 237 | **UNOWNED but LIVE** — replaces `TSummonSpell.SetupSummonSpellTE @0x557E4484`; makes summon unit `0xE4` spawn `RandInt(5)+3` copies |
| `5580C800..5580D4FA` | 3263 | simfly / razebattle_tower / razeroster_vary / razediag / razeeval_timing |
| `5580D550..5580D587` | 55 | **genuinely dead** — zero inbound `E8`/`E9`, zero relocated pointers |
| `5580D600..5580D650` | 80 | razeroster_vary / los_terrain |
| `5580D700..5580D8A3` | 419 | patch / spellcast |
| `5580D900..5580E433` | 2667 | spellcast / fastcast_gate / spellcast_multiturn / firefeed / icestorm_lava / raiseterrain / path_sand / lifesteal / assassin / path_transportgate / invis_penalty / ranged_slayers / turnundead_res |
| `5580ED80..5580F95A` | 2871 | tierresearch_dll / combatlog_dll / leadership4 / leadership_fix / leadership_aura / replaylog / effectroll / stormeffectroll / debuffcache |
| `55810000..5581016D` | 292 | ai_itempickup / combatlog_dll |
| `55811000..55811BCE` | 3022 | combatlog_dll / replaylog |
| `55812000..55812219` | 321 | chasm_sky_transitions / chasm_sky_spellguard / hpbar_clamp |
| `55812400..558126C1` | 479 | crusade_spawns / sitedefender_vary / stormeffectroll / arena |
| `55812800..5581281B` | 27 | stormeffectroll |
| **`55812880..558128BC`** | 61 | **`build_mastery_cost.py` — RESERVES `0x55812880..0x558128DF` (`CAVE_LIMIT = 0x60`); `--undo` zeroes all 96 and `--apply` aborts unless all 96 are zero** |
| **`55812900..55812AB4`** | 437 | **`build_magebane.py` — RESERVES `0x55812900..0x55812AFF` (`CAVE_LIMIT = 0x200`)** |
| `55813000..5581307F` | 127 | copper_medal / marksmanship_ladder |
| `55814000..55814D63` | 3137 | arena (`CAVE_LIMIT = 0x55814E00`) |
| `55815000..5581546D` | 1133 | useitems |
| `55816000..558160EC` | 237 | drillmaster |
| `55817000..55817116` | 279 | **`build_vision9.py` — RESERVES `0x55817000..0x55817400`** ("DO NOT ALLOCATE INSIDE IT") |
| `55817400..55817504` | 261 | **`build_marksmanship8.py` — RESERVES `0x55817400..0x55817800` (1 KB, `CAVE_BLOCK = 0x400`)** ⚠ *not* to `0x55820000`; the study and the probes overstate this by ~35 KB |
| `55818000..5581817A` | 379 | statdouble / damhpdouble / medal_hpmv / newturn_healcap / hpbar_clamp / healwrap |
| `55820000..5582040E` | 1039 | **`build_los_terrain.py` — RESERVES `0x55820000..0x55820800` EXCLUSIVELY** |
| **`55821000..55821057`** | **88** | **`build_dispelmagic5.py` — RESERVES `0x55821000..0x558213FF`** ← claimed 2026-08-26. Does **not** overlap this feature's `0x55820800..0x55820FFF`. |
| **`55822000..5582283C`** | **2109** | **`build_shipyard_income.py` — RESERVES `0x55822000..0x55822FFF` (`CAVE_LIMIT = 0x1000`)** ← new since the probes |

\* split by the ≥0x30 gap rule; the `5580BE00` run's true extent is `..5580BEBD`.

> ⚠ **"UNOWNED" ≠ free.** Three of the runs above are live, hooked helper caves with no owning script — overwriting them would silently break medal Move/HP scaling, the casting-points ladder, three terrain-change helpers, or the 3–7-unit summon multiplier. Only `0x5580D550..0x5580D586` is genuinely dead.

### THIS FEATURE CLAIMS

```
0x55820800 .. 0x55820FFF   (0x800 = 2048 bytes)   file offset 0x11FC00 .. 0x1203FF
```

Verified this session: **all-zero**, file-backed, **zero `.reloc` entries** in the range (nearest neighbours `0x5580BDD9` and `0x558E8010`), and it sits between `build_los_terrain.py`'s exclusive ceiling (`0x55820800`) and `build_shipyard_income.py`'s floor (`0x55822000`), touching neither. `rel32` reach from both hook sites is trivial (`+0x9730F` from `0x557894EC`, `+0x638F7` from `0x557BCF04`).

Estimated occupancy ≈ **411 bytes**: `cave_cost` 120 · `cave_floor` 20 · `cave_gench` 18 · `cave_summon` 19 · `cave_reg` 4×40 + 4 name literals ≈ 234. Ample headroom; the free run above `0x55823000` continues to the CODE vsize end at `0x558E7918`.

**Rules this script must follow, from the Dispel Magic post-mortem:**
1. Declare `CAVE_VA = 0x55820800`, `CAVE_LIMIT = 0x800` in the docstring as an **exclusive reservation**, and add it to the map above the day it is claimed.
2. `--undo` must zero **only the emitted length**, never the rounded `CAVE_LIMIT`. (That rounding is exactly what `build_magebane.py --undo` did to `build_dispelmagic5.py`.)
3. Never allocate above `0x558E7918` — the last 232 raw bytes of the CODE section are outside vsize and are not mapped.

---

## 8. OUT-OF-BAND WORK (a build script cannot do these)

1. **Four AoWDevEd assign-and-save round trips** to mint `Ability.pfs` records 182–185. No build script can create a record: `build_drillmaster.py:339` aborts with *"ABORT: Ability.pfs has no record %d for ability %#04x. Assign the ability to something in AoWDevEd and save, so the editor creates one."* `TAbilityControl.ReadWrite @0x55750164` walks the **registered list** by index and serialises each live entry under tag `index + 10`, so the moment the registration cave exists a DevEd save emits records 182–185 automatically.
2. **Tag 5 (description), tag 6 (level-up cost) and tag 9 (selection mask) are authored in AoWDevEd**, not from a script. The editor's handlers: `TMainForm.AbilityDescriptionChange @0x0042C688` (tag 5), `TMainForm.AbilityLevelPointsChange @0x0042C624` (tag 6 — it does `GetAbility; add eax,0x14; TSpin.GetValue`), `TMainForm.AbilitySelectionCLBClickCheck @0x0042C518` (tag 9), `TMainForm.AbilityListBoxClick @0x0042C33C`, `TMainForm.EditAbilityTextClick @0x0042C724`.
   ⚠ **`build_pfs_typos.py` cannot seed text into a brand-new empty tag 5** — its `plan()` requires the existing text to contain `old` exactly once, and an empty `u32` string gives count 0. It is the tool for *later wording tweaks only*. (The old study's §6 Step 1 is wrong on this.)
3. **Re-verify tag 9 after every DevEd save.** `TAbility.ReadWrite` loads tag 9 into `[ability+0x20]` *after* registration, so the data file overwrites whatever `CX` the cave passed (0 of 21 vanilla sites agree with their own record). Use `build_drillmaster.py`'s length-preserving `pfs_tag9_offset` / `pfs_write` u16 writer plus the CRC repair (`PFS_RESIDUE = 0x2144DF1C`; `crc32(d[4:]) == residue`; repair `struct.pack_into("<I", out, len(out)-4, zlib.crc32(out[4:-4]))`).
4. **`Modding Resources/re_tools/ability_names.py` line 49** — extend `MODDED` with `0xAC: "Evoker", 0xAD: "Conjurer", 0xAE: "Enchanter", 0xAF: "Ritualist"` **and `0xAA: "Magebane"`, which is already missing today** (`names()` returns 150, max `0xAB`). `build_ziggurat_manual.py:read_passive_abilities()` iterates `for aid, name in names.items()` — an unnamed id is never even considered.
5. **Ziggurat Manual** — no code change to `build_ziggurat_manual.py`, but its row filter is `if not (zc or vc or z.get("cost")): continue`, and no unit will ever carry these four (`zc = vc = 0`). **Each of the four therefore MUST end up with a non-zero `Ability.pfs` tag 6**, or it is dropped from the manual entirely. The Hero-cost column additionally requires tag 9 & `0x100`. The level column will correctly render blank. `Modding Resources/Release - Vanilla/Ability.pfs` has 147 records (rids 10..179), so the four render as Ziggurat-only additions — the intended presentation.
6. **Docs to correct at source** once confirmed: `Zig notes/Ability_ID_Budget.md` (lines 19, 124–125 hand out `0xAB`, now Drillmaster); `Caster_Abilities_Feasibility_2026-08-25.md` §7/§2 (marksmanship8 reserve overstated ~35 KB; the `0x5580BF00` casting-points ladder is described as unowned-and-inert but is live and hooked); `Unit_Spellcasting_Feasibility_2026-07-05.md:99` (describes 10/20/40/60/90 as vanilla — vanilla is level×10).
7. **`AoWCompat.exe`** — nothing to do. This feature patches no exe.

**Display, for the record — no work needed and none possible from this script.** `AoW.exe`/`AoWCompat.exe` are the only modules importing `THero.CastingMana` (IAT `0x0045DCA4`, thunk `0x0040277C`, three `E8` callers `0x0042EB05` / `0x0042FBC2` / `0x00431F7A`). Two of the three render a number and follow the discount for free; `0x0042FBC2`'s label is unconditionally blanked by `build_tierresearch_exe.py` (`0x0042FC08 → call 0x00611B50 = xor edx,edx; jmp SetGText` — re-verified live). "Turns to cast" also follows (`CastingTurns @0x55789518` calls `CastingMana` as its first act; `CastingTurnsLeft` reads the `[hero+0x8C]` snapshot). **Two displays will show the undiscounted base cost** because no caster is in scope there: `TMagicWin`'s research summary at `AoW.exe 0x0042D141` (`mov eax,[ebx+0x14]`) and `TWizardsTowerDlg` at `0x0044BABA` (`mov eax,[esi+0x14]`) — both re-verified live this session, both unhooked. Neither is a bug; both are spell-catalogue views. `AoWDevEd.exe` imports none of this and needs no display work.

---

## 9. ACCEPTANCE CRITERIA

### (a) Checkable WITHOUT launching the game

1. **Hook byte verification (all six windows).** Before write, the live bytes match exactly: `0x557894EC` = `53 56 8B F2 8B 5E 14`; `0x55789510` = `8B C3 5E 5B C3`; `0x557BCF04` = `E8 2F 33 F9 FF`; `0x557EFA7C` = `8B 43 14 50 8A 4E 24`; `0x557E44F8` = `8B 43 14 50 8B 45 FC`; `0x557E4353` = `8B 40 14 50 8B 45 FC`. Abort on any mismatch.
2. **`.reloc` assertion.** Re-walk `.reloc` (dir[5], rva `0x287000`) and assert **zero** type-3 entries in all six displacement windows and in `0x55820800..0x55821000`. The only entry near `CastingMana` is `0x557894F4` and it must remain untouched.
3. **Cave-zone zero assertion.** `0x55820800..0x55820FFF` reads all-zero before `--apply`, and `0x55812880..0x558128DF` (mastery), `0x55820000..0x558207FF` (los_terrain) and `0x55822000..0x55822FFF` (shipyard_income) are **byte-identical before and after** the run.
4. **Cave disassembly review.** Capstone-disassemble every cave and check: the first 7 bytes of `cave_cost` are the literal `53 56 8B F2 8B 5E 14` (not keystone's `89 D6` form); the four `mov edx, 0xAx` are 5-byte `BA` encodings; every `call $+5` anchor is the raw `E8 00 00 00 00`; **no absolute memory operand anywhere** (position independence — the DPL rebases); every `call`/`jmp` is a rel32 inside the module.
5. **`--undo` round trip.** Run `--apply`, then `--undo`, then byte-diff the DLL against the pre-apply copy: **zero differences**. Repeat with `build_mastery_cost.py` (no args, dry-run) both before and after — it must report *"Already applied and up to date"* in both states.
6. **Id-free check at build time.** Re-derive: no `call 0x5576601C` site preceded by `mov eax, 0xAC..0xAF`; no `Ability.pfs` records 182–185; no `.pfs` in `Release/` grants an ability id ≥ `0xAC`. Abort if any is false.
7. **`Ability.pfs` CRC gate.** `crc32(d[4:]) == 0x2144DF1C` **before** anything is written, DLL half included — a damaged file must abort the whole run.
8. **Classification self-test.** From the patched file, recompute the four slot differences over all 117 subtree VMTs and assert the bucket counts are exactly 30 / 13 / 18 / 12, and that `0x0007E034` occurs on exactly 31 VMTs file-wide.
9. **Convergence assertion.** Re-scan the whole CODE section for branches into `0x55789511..0x55789514`: must be **zero** (only the three arrivals at `0x55789510` itself).

### (b) Requires the user's in-game test

Set-up: a hero, casting level ≥ 1, **no Sphere Mastery active** for the first pass (test mastery composition separately).

| # | test | do this | expected |
|---|---|---|---|
| 1 | **Launch** | Start `AoW.exe` | No `Runtime error 217`, no "Ability already registered" box, main menu reaches normally |
| 2 | **Editor** | Open `AoWDevEd.exe`, hero ability tab | Evoker, Conjurer, Enchanter and Ritualist all appear and are assignable |
| 3 | **Level-up offer** | Level a hero | All four offered in the **Magic** column with the intended point cost and description. (No dialog work is needed: `build_herodlg_columns.py`'s 256-byte table at `AoW.exe 0x00623B90` already maps `0xAC..0xAF` to category 4 = Magic, and the tallest runtime column is Wayfaring at 25 of a 27-row budget; Magic goes 16 → 20.) |
| 4 | **Enchanter, shown + charged** | Hero **with Enchanter**, cast **Enchant Weapon** (id 16, base 20) | Spellbook shows **10**; player mana drops by exactly **10** |
| 5 | **Control** | Same hero, cast **Bless**? no — cast **Fire Storm** (id 3, base 60, not covered) | Shows **60**, charges **60** — unchanged |
| 6 | **Conjurer, the wallet fix** | Hero **with Conjurer**, casting level 1, cast **Summon Boar** (id 31, base 9) | Shows **4** and charges **4**. ⚠ *Without Sites B+C this shows 4 and charges 9.* |
| 7 | **Conjurer, the silent-fail fix** | Same hero, casting level 1 (10 points), cast **Summon Black Spider** (id 20, base 12) | The spider **appears** and 6 mana is charged. ⚠ *Without the fix the cast is accepted and then nothing at all happens.* |
| 8 | **Ritualist** | Hero **with Ritualist**, casting level 4 (60 points), cast **Tranquility** (id 47, base 60) | Shows **30**, charges **30** |
| 9 | **Ritualist, silent-fail** | Casting level 5 (90 points), cast **Enchanted Roads** (id 44, base 120) | Enchanted Roads **takes effect** and 60 is charged |
| 10 | **Evoker, tactical** | Hero **with Evoker** in manual tactical combat, cast **Great Hail** (id 116, base 24) | Shows **12**, charges **12** |
| 11 | **Evoker, auto-resolve leak** | Same hero, auto-resolve a battle casting **Turn Undead** (id 101, base 11) vs **Solar Flare** (id 100, base 3) | Solar Flare charges 1; Turn Undead charges **11** (known tier-3 leak) — confirm whether that is acceptable |
| 12 | **Floor of 1** | Evoker hero, cast **Ooze** (id 124, base 1) | Costs **1**, and casting points **do** decrease. Not 0. |
| 13 | **Free spell stays free** | Evoker hero, cast **Flaming Arrow** (id 123, base 0) | Still costs **0** — the ability must not raise it to 1 |
| 14 | **No ability** | A hero with **none** of the four, cast Enchant Weapon / Summon Boar / Tranquility / Great Hail | All show and charge the full base cost |
| 15 | **Item-granted** | Give a hero an item carrying Evoker (DevEd) | The discount applies — proves the `+0x148` item-aware query, not the self-only `+0x88` |
| 16 | **Non-hero unit caster** | A unit with Spellcasting casting a unit spell via the multi-select dialog | Behaves per the design decision in §5 — a `CastingMana` hook covers unit casters for free, and `TUnitSpellCaster.GetRequiredMana` multiplies by the selection count *after* the halving, so the total scales proportionally |
| 17 | **Mastery composition** | Enchanter hero **with an own-sphere Mastery**, cast Water Walking (id 42, base 7) | **4** (`7→3→(3×3)>>2 = 2`… for own-sphere; opposed gives `7→3→4`). Record the observed number and check it against §4.5 |
| 18 | **Mastery zero-cost repair** | Hero with a matching Mastery and **no** new ability, cast **Slow** (id 110, base 1) in combat | Costs **1** and consumes a casting point. ⚠ *Today it costs 0 and consumes nothing.* Confirm this repair is wanted. |
| 19 | **Save / load** | Save with all four assigned, quit, reload | The abilities are still on the hero. (`TCustomAbilityList.ReadWrite @0x5574E2BC` silently strips bits for unregistered ids — so this also proves the registration survived.) |
| 20 | **MP sanity** (if tested) | Two peers with byte-identical binaries | No desync. There is **no content hash** — `ValidateCompatibleVersion @0x557DFCAC` compares only the version high word, so mismatched peers connect and then desync. |

---

## 10. TRAPS

- **`0x557894F8` belongs to `build_mastery_cost.py`** (`jmp 0x55812880`). Hook the entry at `0x557894EC`; never re-hook, never "revert and re-apply" — there is no usable `.pre-masterycost`, only `--undo`.
- **A floor applied in the prologue does not survive the function** — the mastery cave rescales EBX at `0x558128A7`/`0x558128B1` and `(1×3)>>2 = 0`. Floor at the exit, `0x55789510`.
- **`.reloc` at `0x557894F4`** is `CastingMana`'s only relocation. Displacing it is the classic "works one launch, crashes the next". Scan `.reloc` before displacing anything, anywhere.
- **The entry cave cannot wrap the call** — the mastery cave owns the tail via `jmp 0x55789510`. Prologue insert only: test, replay the displaced bytes, adjust EBX, jump back.
- **Replay the displaced bytes literally, never re-assembled** — keystone renders `mov esi,edx` as `89 D6`, the original is `8B F2`.
- **Keystone `call $+5` emits nothing** as source and then zeroes the rel32 of the preceding `E8`. Emit `E8 00 00 00 00` as raw bytes and disassemble every cave you assemble.
- **`EAX` (the caster) is not always a `THero`** — `TUnitSpellCaster.GetRequiredMana @0x5577A49C` passes a `TUnit`; `TCombatSpell.CreateCA` passes `[combatUnit+0x4C]`. Never assume `THero` fields.
- **This patch introduces the first dereference of `Self` in `CastingMana`.** Vanilla never touches `EAX` (it is overwritten five bytes in). `test eax,eax / jz` plus the `cmp [ecx-0x40], ecx` vmtSelfPtr check are mandatory. ⚠ **Residual risk:** a wild non-nil `Self` faults on the `mov ecx,[eax]` load itself, which no register test can prevent. The realistic source is `[TCombatUnit+0x4C]` on a `TCombatWall` (packed bytes — the Blt Error alias); auto-resolve is the path to watch, hence in-game test 11.
- **`TCombatUnit` VMT+0x148 is `0x55715BE0` (RTTI blob) and `TFastCombatUnit`'s is `0x74696E55` ('Unit').** `+0x148` is valid *only* for `TAbstractUnit`/`TUnit`/`TAdjustableUnit`/`TWallUnit`/`THero`/`TLeader`. Never copy this call into a combat-side hook — there the forwarder is `VMT+0xA8` → `TCombatUnit.GetAbilityEnabled @0x55725004`.
- **`GetAbilityEnabled` is two nested virtual calls plus a registry search.** Classify first, query once. Three queries per cost evaluation would be three times the cost inside a function the AI hammers in affordability loops.
- **Spell objects are shared singletons** (`TSpellControl.RegisterSpell @0x55779B40` indexes a TList by `[spell+0x10]`). Never write `[spell+0x14]`; adjust the value in flight.
- **A zero cost is not harmless** — `THero.CastingDone` then consumes neither mana nor casting points. It does *not* crash (`CastingTurns` divides by `GetCastingPointsMax` at `VMT+0x128` and early-outs at `0x55789552`), but it is unlimited casting.
- **Flaming Arrow (id 123) costs 0 today** — the only one of 108 `Spells.pfs` records without tag `0x0D`. Guard the floor with `cmp dword [esi+0x14],0`.
- **`[spell+0x3c] == 0` is not an "instantaneous spell" marker** — `TCombatSpell.Create` writes 0 there at `0x557F723A`, so it is the common case file-wide. Do not port the old study's 8/35/55 exclusion.
- **`[spell+0x22] == 2` is `stGlobal`, carried by 60 of 108 spells**, not "global enchantment". And on the `*TE` companion classes `+0x22` is a hex coordinate.
- **`Ability.pfs` tag 9 overwrites the cave's mask, and tag 6 overwrites the cave's cost**, once a record exists. Re-verify after every DevEd save.
- **An ability with no tag 6 is *permanently* free**, not merely displayed as free (`THero.UsedSkillPoints` sums `ExpandCost` = `[ability+0x14]`).
- **Never set an ability bit for an id the binary does not register** — `0x5577F60A` `mov ecx,[eax]` on a nil `GetAbility` result. Registration cave and cost cave ship together.
- **`--undo` must zero only the emitted length, never a rounded reservation** — that rounding in `build_magebane.py --undo` is what destroyed `build_dispelmagic5.py`'s cave and left Dispel Magic IV/V crashing today.
- **"No script references this zero run" is a statement about a moment in time, not a reservation.** `build_shipyard_income.py` claimed `0x55822000` between the probes running and this spec being written.
- **`Spell_Records_Dump.txt` is keyed by PFS record id, not spell id** — record id = spell id + 10. Cross-checking membership against it without the shift makes a correct table look wrong.
- **Kill any running AoW binary before `--apply`** (standing authorisation): `Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWCompat|AoWDevEd|AoWEd)$' } | Stop-Process -Force`. `AoWDevEd.exe` locks `AoWEPACK.dpl` too.

---

## UNKNOWNS — explicitly not resolved

- **`.reloc` status of the Cosmagic Scrying window `0x557E85F9..0x557E8601`** — unknown; must be checked before the tier-2 fix is attempted. Every other window in this spec was walked.
- **Whether the game tolerates a registered ability with no `Ability.pfs` record** on the first launch after `--apply`, before the DevEd round trips. `TAbilityControl.ReadWrite` requests tag `index+10` per registered entry; `TPropertyTable.FindOffset` lives in `Enginep.dpl`, outside Ghidra's image. There is strong practical precedent (Path of Sand, Assassin, Magebane and Drillmaster all went through this state), but nobody has recorded it as tested — **needs in-game test 1**.
- **Which consumer reads the combat-action object's `+0x10`/`+0x1C` mana field** for the six raw-storing `CreateCA` overrides. The interactive tactical charge is confirmed unaffected; the leak is very likely fast-combat/AI accounting only. Needs one Ghidra pass on the `TCombatSpellCA` field readers if the tier-3 fix is ever taken up.
- **The exact register roles in `TWaterMastery.ExecuteTE`** (`ESI` is passed as `EDX` to `CastingDone`, so it is the caster, not the TE — where the TE lives there was not traced). Moot: Water Mastery at 250 mana can never reach the instant branch even with Ritualist plus own-sphere Mastery (93 > the 90-point ceiling).