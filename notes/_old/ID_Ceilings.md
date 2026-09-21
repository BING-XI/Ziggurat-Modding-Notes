# Ability and spell ID ceilings — the complete bound map

**Status: ⚠ PARTLY SUPERSEDED 2026-09-02 — read this box before anything below.**

The headline claim that follows was **falsified in game on 2026-09-01**: a tactical battle threw
`Error during TCAI Create Unit List`, a genuine range-check error from the `[0..169]` `BOUND`.
Cause: `build_abilityid_ceilings.py` raised four `TCAI.EvalBattle` ability-scan loops to `0xB3` on
the reasoning quoted below — that only *selectable* abilities reach that bound. **That reasoning
holds in `CreateTCAbList` and is false in those four scans**, which have no selectability gate
between `GetAbilityEnabled` and the `bound`. Any unit carrying an enabled id 170–178 crashed.

**Fixed by `build_scripts/build_abiltypes_relocate.py`** (CONFIRMED WORKING 2026-09-02): `AbilTypes`
now lives at **`0x00469440`, 256 entries**, with all 13 references repointed and all **9** limit
pairs at `{0,255}`. Rows A1/A3/A4/A5 below and the forward hazard are rewritten accordingly.

⭐ **The durable lesson:** a gate that makes one call path safe is not evidence that a *different*
path is safe. Enumerate the callers of the bound, not the abilities.

**Status of the rest: CONFIRMED against the live binaries 2026-08-28.** Written after adjudicating Inioch's
id-ceiling claims (checklist rows S5N-151, S5F-103, S5P-132, S5N-137, S5F-104, S5N-82, S5P-71,
S5P-33, S5P-32, S5N-80, S5N-81, S5F-66, S5F-83, S5P-118, S5N-136).

## The headline

~~**Ziggurat ships nothing that exceeds a real, enforced engine limit.**~~ **FALSE — see the box at
the top.** It shipped nine ids (`0xAA`–`0xB2`, 170–178) above the `[0..169]` hardware `BOUND`, and
from the moment the AI scan loops were raised to `0xB3` that was a live crash, not a near miss.

The selectability gate below is real and still governs the **map-click** path. It was never the
only reader of the bound, and presenting it as the whole story is what shipped the defect:

```
; AoWTCPCK.dpl  SelectAbility -- deciding HEAD (selectable) vs TAIL (display-only)
004234E1  call dword ptr [ecx + 0x98]     ; TAbility.GetControlType
004234E7  test al, 2                      ; acCombatAction?
004234E9  je   0x423539                   ;   no  -> TList.Add  = TAIL
0042350B  call dword ptr [ecx + 0x84]     ; TAbility.GetCombatMode
00423511  cmp  al, 1
00423513  je   0x423539                   ;         -> TAIL
00423524  call TList.Insert at index [self+0x3c]
0042352C  add  dword ptr [eax + 0x3c], 1  ; HEAD, count++

; and the only writer of the bounded field refuses anything past the head count:
00422FFB  cmp  eax, dword ptr [ebp - 0x14]
00422FFE  jle  0x4231bd                   ; index >= head count -> BAIL, [+0x34] stays -1
```

`[TTacticalCombatUnitHS+0x34]` is **the only ability-id value that ever reaches a `BOUND`**. All
seven Ziggurat ids are plain `TEnhancementAbility` — verified: Shield's registration cave at
`0x5582313E` is `mov eax,0xB0` / `call 0x5576601C CreateEnhancementAbility` — and
`TAbility.GetControlType @0x5574E730` is `mov al,[0x5574E738]` with that byte **= 0x00**. So
`test al,2` is false, they go to the tail, they are never selectable, and `+0x34` never holds
170–176.

⚠ **This is a property of the ABILITY CLASS, not of the id.** See the forward hazard below.

## Every real limit

Only `AoWTCPCK.dpl` was compiled with range checks on; `AoW.exe`, `AoWEPACK.dpl` and `aowInt.dpl`
contain no real `BOUND` instructions at all.

| # | module | site(s) | limit | guards | above it | ours? |
|---|---|---|---|---|---|---|
| A1 | AoWTCPCK | 15 `bound` reads, 9 distinct pairs | **`[0..255]`** | **`AoWTC.AbilTypes @0x00469440` (256 B)** — relocated; `0x467248` (170 B) left intact, unreferenced | `BOUND` #BR → range-check error | **ours** — `build_abiltypes_relocate.py`, CONFIRMED 2026-09-02. ⚠ Was `[0..169]` and a **live crash** once A3 was raised — *reachable by any enabled id*, not just selectable ones |
| A2 | AoWTCPCK | `0x0042354A` `cmp [ebp-8],0xB3` | ids 1..0xB2 | `CreateTCAbList` loop | id silently unlisted | **ours** — `build_tcablist_ceiling.py`, now 0xB3 |
| A3 | AoWTCPCK | `0x418A73 0x418D1F 0x4190FA 0x41977F` `cmp …,0xB3` | ids ≤ 0xB2 | four `TCAI.EvalBattle` scan loops | **the tactical AI never sees the ability** | **ours** — `build_abilityid_ceilings.py`. ⚠ **Requires A1's relocation** — these loops reach the `bound` with no selectability gate; with A1 at `[0..169]` any enabled id 170–178 crashed |
| A4 | AoW.exe | `0x00406DEF` `cmp esi,0xB3` | ids ≤ 0xB2 | `TItemBanner.IBannerPopupShow` | omitted from the item banner popup | **ours** — `build_abilityid_ceilings.py` (AoWCompat in lockstep). No `bound` in AoW.exe — safe without A1 |
| A5 | AoW.exe | `0x00455DE1` `cmp ebx,0xB3` | ids ≤ 0xB2 | unit hover banner popup | omitted from the hover popup | **ours** — `build_abilityid_ceilings.py` (AoWCompat in lockstep). Same note as A4 |
| A6 | AoWTCPCK | `0x4227AD`/`0x4227D3` | 14-entry whitelist | `AoWTC.StatusAbils @0x004675B8` | no status overlay icon | vanilla |
| A7 | AoWEPACK | `TAbilityControl.GetAbility @0x557501C0` | `id<0` / `id>=Count` | registry TList | negative → assertion `'Invalid AbilityID'`; **≥Count → nil, silent** | vanilla |
| A8 | AoWEPACK | `RegisterAbility @0x55750238` | **no upper bound**; nil-pads to `id` | registry | **duplicate id → runtime 217** | vanilla |
| A9 | AoWEPACK | `0x5577F618`, `0x5574E0E0` | `cmp edx,[eax+0xC]; jae` | per-owner bitset | returns False — no wild read | vanilla |
| S1 | AoWTCPCK | 13 reads, 9 pairs | `[0..130]` | `AoWTC.SpellTypes @0x004672F4` (131 B) | `BOUND` #BR → range-check error | vanilla |
| S2 | AoWTCPCK | `0x4188D4 0x418C9B 0x419076 0x4196F4` `cmp …,0x83` | ids ≤ 130 | `TCAI.EvalBattle` spell scans | AI never evaluates the spell | vanilla |
| S3 | AoW.exe | `0x0042F30D` | `id≥100` needs `SpellTypes[id]≠0` | spellbook page builder | **spell silently deleted from the book** | the neighbouring `jl` at `0x42F2F5` is `build_tierresearch_exe.py`'s cave call |
| S4 | AoWEPACK | `RegisterSpell @0x55779B40` | none — TList grows | spell registry | `GetSpell` → nil past count | vanilla |

## The true ceilings today

**Abilities — highest working id 178 (`0xB2`, Embrittled).** 160 ids in use, 0…178, with 19 vanilla
gaps (`33, 78–85, 91, 102–105, 110, 133–135, 151`; measured live 2026-09-02 — `136`/`137` were gaps and are
now `0x88`/`0x89`). Sparseness is harmless — A7/A9 fail closed and
A8 nil-pads.

⚠ **The forward hazard — REWRITTEN 2026-09-02.** The old rule here was *"above 169, passives only"*.
That is obsolete: `build_abiltypes_relocate.py` moved `AbilTypes` to `0x00469440` with 256 entries
and raised all nine limit pairs to `{0,255}`, so **the bound no longer blocks any id ≤ 255** — for
selectable and passive abilities alike.

**The rule that replaces it:** the bound is no longer the constraint, the *table contents* are.
Every entry from 170 up is **category 0**, and category 0 is **inert at all fifteen consumers** —
verified site by site. So a new ability above 169 will be admitted everywhere and then do nothing:
the AI skips it in all six `EvalBattle` reads, `TRangedPathHS.Show` draws no path, and clicking it
in the panel calls `SelectAbility(-1)` and **deselects it**. ⇒ **After minting an ability at any id,
set `[0x00469440 + id]` to its category** — 1/2/3 ranged, 4 touch/command, 5 breath, 7/11 special —
or it is invisible to the AI and unusable by the player.

⚠ **Migration trap:** with the scan loops at `0xB3` and the relocation *not* applied, even a
**passive** above 169 crashes. `build_abiltypes_relocate.py --undo` therefore refuses unless the
ceilings are lowered first.

**Spells — highest working id 130.** 108 ids in use, 1…130; free ids are **79–99 and 109** (22).
Every shipped id ≥ 100 has a non-zero `SpellTypes` byte, so none is hidden by S3.

⚠ **131 is a genuine wall, and widening it is worse than hitting it.** `AoWTC.SpellTypes` is sized
to exactly 131 bytes and the next byte is live data (`AoWTC.BreathHit @0x467378`, then
`BreathDir @0x4673A8`). Raising the nine `[0..130]` bound pairs converts a loud `ERangeError` into
a **silent read of the breath tables**, and *writing* a `SpellTypes` byte past 130 corrupts them.
Going past 130 honestly means relocating the array — 12 disp32 refs, the DATA pointer
`0x004693F8`, nine bound pairs, the export RVA, and `AoW.exe`'s IAT slot `0x0045EBEC`.

**New-spell build rule:** any new spell id ≥ 100 must be given a non-zero `SpellTypes[id]` byte or
it vanishes from the spellbook without a word (S3).

## Claims examined and rejected

- **"A sparse ability id crashes at startup with runtime error 216."** False, and Inioch retracts
  it himself (his real cause was a wrong base classref). We ship 21 vanilla gaps that boot fine.
  The correct pair: **217 = duplicate id** (`RegisterAbility` raises before a handler exists);
  **216 in this project's records is heap corruption from the combat-log length-byte over-read**,
  nothing to do with ability ids. **Density does not matter; uniqueness does.**
- **"`SpellTypes` is bound-limited, not size-limited"** — refuted. The export gap to `BreathHit`
  is 132 bytes for a declared 131. `SpellTypes[200]` does not read 0; it reads 6.
- **"He had a spell working at id 202"** — he has a latent range-check error, not a working spell.
  `SpellTypes[202]` is byte 2 of `BreathDir` element 6; `EvalBreath @0x4151B2` then computes
  `n*12+off-12` and bounds it to `[0..71]`, which 7 already overflows.
- **"Ability ids must stay ≤ 171"** — an artefact of where he stopped zeroing pad bytes, not an
  engine property. The real constraint is the class rule above.
- **"pfs key ↔ spell id is not closed-form"** — refuted. `key = id + 10`, 108/108 in our data,
  and code-derived from `TSpellControl.ReadWrite @0x55779A6C` (`lea ecx,[ebx+0xA]`).

## Resolved 2026-09-02 — the three unraised `0xAA` ceilings, and a wrong theory kept for the record

A3/A4/A5 (the four `TCAI.EvalBattle` scans, the item banner popup, the unit hover popup) were raised
to `0xB3` by `build_abilityid_ceilings.py`, and the symptom that found them — Shield present in the
full unit dialog but absent from the hover popup — no longer reproduces.

⚠ **Don't re-derive this: raising A3 did NOT make the AI "see" the new abilities, and never could.**
This section used to call the AI's blindness "a balance defect, not cosmetic". Raising A3 only lets
the scan *reach* those ids; each is then looked up in `AbilTypes`, where every id ≥ 170 is category
**0** — "not an AI action" — and skipped. All nine are `TEnhancementAbility` passives, and the scan
never consumed passives for any id. What raising A3 actually did was expose the A1 range check, which
then crashed (see the box at the top). An ability the AI should *act on* needs a real category byte at
`[0x00469440 + id]`; a passive is correctly 0, and is correctly invisible to that scan.
