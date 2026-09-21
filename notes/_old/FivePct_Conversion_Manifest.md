# 5% increment conversion — decisions and state

**Status: CONFIRMED WORKING (2026-08-24)** — validated in-game by the user. Conversion complete and
applied 2026-08-20.
**2026-08-24: the DAM/HP congruence pass now layers on this** — every damage source and HP pool
doubled, six conversion defects repaired in the same session. Master record:
`DamHP_Double_Decisions.md`. 64 of this manifest's `UNCHANGED` entries were superseded there
(their rulings carry the pointer).
176/176 code immediates at target across two binaries, 651 `.pfs` data bytes, 127/127 assert-only
entries verified untouched, both `.pfs` CRCs valid, Magebane chain intact. **Zero unstaged writable
entries remain** - everything is staged or explicitly `UNCHANGED`. The last structural item,
Marksmanship, landed 2026-08-20 (`build_marksmanship_atk2.py`).

The two halves agree for the first time: every ATK/DEF/RES source is doubled and the to-hit slope is
halved, so hit chances and the whole damage distribution are unchanged - the gain is half-step
expressibility. **Nothing here has ever been run.** To play unconverted, `--undo` every owner in the
table below plus `build_hitslope5.py` and `build_statdouble.py`.

Backups: `AoWEPACK.dpl.pre-hitslope5`, `AoWEPACK.dpl.pre-statdouble`,
`AoWTCPCK.dpl.pre-statdouble`, `Release/Unitres.pfs.pre-statdouble`,
`Release/HERORES.PFS.pre-statdouble`.
Live tracking doc for the 10 pp → 5 pp to-hit conversion. The site inventory for the slope itself is in
`HitChance_Increment_Audit.md`; this doc holds the **decisions**, the doubling-manifest state, and the open
items. Read both before building.

---

## 1. The core result

**Doubling every ATK/DEF/RES source and halving the slope is a PERFECT IDENTITY.** Verified by enumeration:
hit chance *and* the complete damage distribution are bit-identical across all damage ratings and all
differences −12..+12. `T = 10 − 2d` becomes `T = 10 − d'` with `d' = 2d`, so `T` is unchanged and stays
even; `50 + 10d ≡ 50 + 5d'`.

So the change buys exactly two things:

1. **Half-steps become expressible** — a net +1 is 55%, previously unreachable (only 50% or 60%).
2. **Whatever is deliberately NOT doubled** becomes half as influential.

## 2. Decisions taken (user, 2026-08-18)

| # | decision | consequence |
|---|---|---|
| D1 | **Preserve balance, unlock half-steps** | double everything by default; exceptions are deliberate |
| D2 | **Do NOT double: items, medal ranks, morale, Leadership** | these four become half as influential |
| D3 | **Hero skill costs halve** (ATK 6→3, DEF 12→6, RES 4→2) | with D4, a clean identity |
| D4 | **Hero caps DOUBLE** — `SetUnit*` ATK 30→60, DEF 20→40, RES 20→40; `THero.Get*` clamps 30→60 | ⚠ **REVERSES** an earlier "cap stays 30". 26 pts × 6 SP today ≡ 52 pts × 3 SP after — heroes are a pure identity; the hero nerf considered earlier is **not** happening |
| D5 | **Two scripts, applied together, never tested apart** | `build_hitslope5.py` + `build_statdouble.py` |
| D6 | **Existing saves: accept breakage, new games only** | no save-fixer. See §4 — the sharpest edge in the change |

**Boundary reading of D2** (stated, not contradicted): "modifier stack" = items, medal rank progressions,
morale modifiers, Leadership tables **only**. Ability buffs/debuffs (Bless, Curse, Fury, Bloodlust,
Poisoned, Vertigo, Stone Skin…) and Parry / Charge / slayers / invisibility **DO** double.

## 3. Scope

- **The slope**: **seven** 2-byte edits, `add r32,r32` → `90 90` (4 engine + 3 log-display caves). Table in
  `HitChance_Increment_Audit.md` §1. Census complete across 11 modules.
  ⚠ **`TEnchantment.DispelChance @0x5577C1A4` was removed from the set 2026-08-18** — same clamp *shape*, but
  its difference is ability level vs enchantment strength, neither of which doubles. Halving it is a pure
  dispel buff and cannot be made an identity. `GetDispelMana` (both copies) stays too.
- **The doubling**: 245 manifest entries from the first pass (unit/hero `.pfs` bases, engine clamps,
  ability modifiers, fixed effect powers, touch attacks, strategic hazards, ranged constants), **plus
  eleven further families found by audit** and being enumerated — AoWTCPCK constants, 25 more
  combat-spell powers, wall/adjustable-unit stats, the second skill-point cost copy, stat-derived damage
  caves, `comb_res.pfs`, and `GetCombatInfo` hard-coded attacks.

## 3a. STAGED BUILD PLAN (adopted 2026-08-18)

The conversion **cannot be applied in pieces** -- the slope is one global function, so any stat source
not yet doubled is immediately half-strength. But it can be **built and verified** in pieces, with a
single apply at the end. That is the adopted approach.

`build_statdouble.py` is manifest-driven: it reads `build_scripts/fivepct_manifest.json` and writes
ONLY entries carrying a `stage` field that has been explicitly verified. Unstaged entries are ignored.
`--status` prints which stages are green. Nothing is applied until every stage is green.

| stage | scope | entries | state |
|---|---|---|---|
| 0 | slope (`build_hitslope5.py`, separate script) | 7 | **CONFIRMED 2026-08-24** |
| 1 | stat clamps + hero skill economy | 16 | **CONFIRMED 2026-08-24** |
| 2 | `.pfs` base stats (Unitres + HERORES) + CRC repair | 651 | **CONFIRMED 2026-08-24** |
| 3 | ability stat modifiers | 21 | **CONFIRMED 2026-08-24** |
| 4 | fixed effect powers + protection knobs | 17 | **CONFIRMED 2026-08-24** |
| 5 | touch attacks | 12 | **CONFIRMED 2026-08-24** |
| 6 | strategic hazard attacks | 12 | **CONFIRMED 2026-08-24** |
| 7 | combat-spell powers | 32 | **CONFIRMED 2026-08-24** |
| 8 | ranged constants + slayers (**engine-side only**) | 21 | **CONFIRMED 2026-08-24** |
| 9 | AoWTCPCK tactical constants (**2nd binary**) | 4 | **CONFIRMED 2026-08-24** |
| 10 | "misc" bucket -- inspected; 1 dropped, 1 dead-flagged | 27 | **CONFIRMED 2026-08-24** |
| 11 | edits made BY their owning scripts (see below) | 13 | **CONFIRMED 2026-08-24** |
| 12 | underground ranged malus (unowned cave -> statdouble) | 1 | **CONFIRMED 2026-08-24** |
| 12 | final apply: hitslope5 + statdouble + the 3 owned edits, together | -- | |

**Stage 11 edits must be made by the owning script, never by `build_statdouble.py`** -- each owns and
verifies its cave, and a foreign write breaks its re-apply/undo path. ⚠ **Grew from 3 to 14 entries when
stage 8 was re-examined**: a third of the "ranged + slayers" family turned out to live inside other
scripts' caves. Ownership was established from the `CAVE*` constants declared across `build_scripts/`,
not by guessing:

| owner | entries | cave range |
|---|---|---|
| `build_assassin.py` | 4 | `0x5580E070`-`0x5580E190` |
| `build_ranged_slayers.py` | 4 | `0x5580E190`-`0x5580E2A0` |
| `build_invis_penalty.py` | 3 | `0x5580E370`-`0x5580E440` (3 caves) |
| `build_turnundead_res.py` | 2 | `0x5580E2A0`-`0x5580E370` -- plus the `shr eax,1` -> `shr eax,2` structural edit |
| `build_marksmanship8.py` | 1 | hooks the undocumented cave at `0x5580C240`; the ATK doubling itself is **`build_marksmanship_atk2.py`** - see below |

**Idempotence:** BSS is NOT file-backed (raw size 0), so the planned marker location is unusable --
verified. The marker goes in the free CODE zone at `0x55818000` (853 KB of zeros from `0x55817505`,
file-backed at offset `0x117400`). `build_hitslope5.py` needs no marker: `90 90` at its seven addresses
is unambiguous. `build_statdouble.py` does, because two sites have doubled == pristine.
⚠ `--undo` must restore the RECORDED LIVE values, never pristine -- e.g. `TDiseaseCloud` damage is
live 7 / pristine 3.


### Applied-state verification (2026-08-18, independent byte-diff -- not the scripts' own reports)

- `Unitres.pfs`  541 bytes changed = 537 stat bytes + 4 CRC. Size unchanged, CRC residue valid,
  re-parses to 179 records / 537 fields, every stat byte exactly x2.
- `HERORES.PFS`  118 = 114 + 4 CRC. Same checks, 38 / 114.
- `AoWEPACK.dpl` 21 bytes = 16 stage-1 immediates + 4 marker magic + 1 mask byte. Every stage-1
  immediate holds its target value; nothing outside those ranges moved. Stage-0 slope still `90 90`.
- `--undo` round-tripped **byte-identical to backups on all three files** (proven on scratch copies
  before the live apply).



### ⚠⚠ STAGE 11: THE CAVES ARE CHAINED ACROSS SCRIPTS (found 2026-08-18)

Stage 11 is not "14 byte pokes in 5 scripts". The caves form a **chain**, and several scripts repoint
each other's exit jumps. Re-running an owner in isolation silently deletes whatever chained onto it.

    hook 0x5576EB34 -> cave_ts_rng (invis, 0x5580E400) -> cave_rng (ranged_slayers, 0x5580E190)
                    -> [magebane repoints the exit at 0x5580E298 into its own cave 0x55812A20]
    assassin cave_melee3 (0x5580E120) exit -> cave_ts_melee3 (invis, 0x5580E3B0)
                    -> [magebane repoints the exit at 0x5580E3D9]

**Required order for any stage-11 re-tune:**
1. `build_magebane.py --undo`  (it has a surgical `--undo` and a `--verify` that reports the chain)
2. re-run the owning script
3. `build_magebane.py --apply` then `--verify`

**DONE (7/14):**
- `build_ranged_slayers.py` -- 4 entries. ⚠ One constant fed BOTH attack and damage; split into
  `RANGED_ATK_BONUS=2` / `RANGED_DAM_BONUS=1`. **Which operand is which took tracing**: the header
  describes the stack AT THE HOOK, but cave entry is `push edi; push eax`, so in the BODY
  `[esp]`=damage and `[esp+8]`=attack. Getting it backwards doubles ranged damage.
- `build_invis_penalty.py` -- 3 entries, `MELEE_PENALTY 1->2`, `RANGED_PENALTY 3->6`. All three are
  pure ATTACK penalties, no damage involvement. ⚠ Its accept-list held only the v1 True-Seeing body
  and the NEWLY generated body -- not **its own previously-installed body with the old constant**, so
  a re-tune wedged it. Now regenerates variants across penalties 1..12.

**BLOCKED (7/14)** -- these need chain-aware surgery, not a constant tweak:
- `build_assassin.py` (4) -- constants split to `MELEE_ATK_BONUS=6` / `MELEE_DAM_BONUS=3` and an
  in-place accept-list added, but it still refuses: its cave terminators have been **repointed by
  `build_invis_penalty.py`**, so the generated body (with the stock destination) never matches the
  installed one. ⚠ And `build_invis_penalty.py` only **verifies** that chain, it does not write it --
  so rewriting assassin's caves with stock terminators would make invis refuse to run at all.
  The owner must learn to PRESERVE the installed terminator instead of forcing its own.
- `build_turnundead_res.py` (2 + the `shr eax,1`->`shr eax,2` structural edit) -- no in-place support yet.
- `build_marksmanship8.py` (1 + an inserted `add al,al`; no immediate exists to double) -- **DONE 2026-08-20** by a new owner script, see the Marksmanship section.



### The redesign that made stage 11 possible (2026-08-18)

Five owner scripts had the same structural defect: **they could not re-tune themselves.** Each verified
its cave against "zeroed (first install)" or "byte-identical to what I am about to write", so changing a
constant produced a third state -- its own body with the OLD value -- that matched neither, and the
script refused to write. Three fixes, now applied to `build_ranged_slayers.py`, `build_invis_penalty.py`,
`build_assassin.py` and `build_turnundead_res.py`:

1. **Accept-variants.** Regenerate our own body across the plausible constant range and accept any of
   them as the installed state. (`_variants()` / `CAVE_VARIANTS` in each script.)
2. **Prefix comparison + growth assertion.** A re-tune can CHANGE THE BODY LENGTH -- `shr eax,1` is two
   bytes, `shr eax,2` is three -- so compare variants by prefix and separately assert the bytes the cave
   grows into are still zero. A length-equal comparison silently never matches.
3. ⭐ **Terminator preservation (`preserve_terminator`).** A cave's exit `jmp` is a CHAIN LINK, not a
   private detail: downstream features splice themselves in by repointing it. Regenerating with the
   stock destination silently deletes everything downstream -- and since `build_invis_penalty.py` only
   VERIFIES its chain rather than writing it, it would then refuse to run at all. Owners now keep
   whatever exit target is installed and log `[chain] <cave> exit kept at <target>`.

**Also learned:** one constant feeding both the ATTACK and DAMAGE halves of a bonus is only safe while
they are equal. Three scripts did this (`RANGED_BONUS`, `MELEE_BONUS`, and the Turn Undead formula);
all are now split. Deciding which operand was which required tracing in every case -- in
`build_ranged_slayers.py` the header describes the stack AT THE HOOK, but the cave's own
`push edi; push eax` prologue means `[esp]` is damage and `[esp+8]` is attack inside the body.

### Marksmanship ATK scaling -- DONE 2026-08-20 (`build_marksmanship_atk2.py`)

The only entry in the whole conversion with **no immediate to double**: `Marksmanship` grants +1 ATK
per level via `add bl, al`, where AL *is* the ability level. Doubling it needs an inserted
`add al, al` (`00 C0`), and those two bytes sit at the very START of an **unowned** cave -- so the
entire 0x48-byte body had to move down 2.

```
before                                 after
5580C240  02 D8  add bl, al            5580C240  00 C0  add al, al   <-- inserted
5580C242  56     push esi              5580C242  02 D8  add bl, al
   ... Cave/Depths -4 malus ...           ... body shifted +2 ...
5580C273  E8 1C 2B F7 FF  call ..ED94  5580C275  E8 1A 2B F7 FF  call ..ED94  <-- rel32 -2
5580C287  C3     ret                   5580C289  C3     ret
```

Why the relocation is safe, enumerated rather than assumed:

| kind | count | effect of a uniform +2 shift |
|---|---|---|
| internal rel8 jumps (all -> the `pop esi`) | 4 | source and target both move; displacement **unchanged** |
| external rel32 (`call 0x5577ED94`, GetLocation) | 1 | source moves, target does not: displacement **-2** -- the only fix-up |
| memory operands (`[esi+4]`, `[ecx+0x148]`, `[esp+N]`) | all | register-relative, no `.reloc`, PIC-safe |
| entry points | 1 | `call 0x5580C240` @`0x5576E689` still lands on the new first instruction |

Body grows 72 -> 74 B, ending at `0x5580C28A`; 5 of the 8 slack bytes remain, real code resumes at
`0x5580C290`. The script asserts the growth zone is zero before writing.

**`build_marksmanship8.py` needed no change** -- it checks only that `0x5576E689` starts with `E8`,
that `0x5576E641` is `D1 E8 01 C3`, and that the call target is `0x5580C240`. It never inspects the
cave body, so the relocation is invisible to it. (Verified after applying: it still reports
"chain intact"; `build_magebane.py` still reports "caves match: True".)

⚠ **The Cave/Depths ranged malus rides along in the same cave** (gated on Night Vision `0x27`),
already doubled to `sub bl, 4` by stage 12. The relocation preserves it verbatim and does **not**
re-tune it; do not double it twice.

`--undo` shifts the body back, restores the rel32 and re-zeroes the two slack bytes -- round-tripped
and byte-identical to `AoWEPACK.dpl.pre-marksatk2`.


⚠⚠ **The relocation moved a byte that another script owns.** The malus immediate is
`build_statdouble.py` **stage 12** (`0x5580C285` -> `0x5580C287`, file `0x10B685` -> `0x10B687`).
Left alone, `build_statdouble.py` aborts with *"1 sites in stage 12 hold bytes that are neither the
live nor the target value"*. `build_marksmanship_atk2.py` therefore **rewrites that one manifest
entry itself**, in both directions, and reconciles even when the binary needs no change:

| run | binary | `fivepct_manifest.json` stage 12 |
|---|---|---|
| `--apply` | body shifted +2 | `0x5580C285` -> `0x5580C287` |
| `--undo` | body shifted back | `0x5580C287` -> `0x5580C285` |
| no flag | untouched | reports the drift, writes nothing |

It is address-guarded: it rewrites only the single stage-12 entry, only when that entry already
holds one of the two known addresses, and reports rather than guesses otherwise. Round-tripped:
stage 12 stays *at-target* through `--undo` then `--apply`.


### ⚠ A later balance change now LAYERS on stage 2 (2026-08-20)

`build_hero_chassis_atkdam.py` doubles HERORES.PFS **ATTACK** (tag `0x0F`) and **DAMAGE** (tag `0x11`)
again, on top of stage 2. Doc: `Hero_Chassis_ATK_DAM_Double.md`. Two consequences for this conversion:

- **Chassis DAMAGE is 2x** -- a deliberate user balance change, NOT part of the identity (damage never
  doubles). Do not "correct" it back. Chassis ATTACK was briefly 4x on the same day and was **returned
  to x1**, i.e. exactly where stage 2 put it, so the two scripts now write identical ATK bytes.
- ⚠ **Undo order.** Both scripts write the same 38 ATK bytes, and `build_statdouble.py --undo` halves
  ATK/DEF/RES without touching DAM. Undo the chassis script **first**; re-apply it **last**. A wrong
  order leaves HERORES mixed (ATK at the pre-state, DAM doubled); the chassis script detects that and
  aborts with a diagnosis, but cannot repair it.

`build_statdouble.py --status` still passes either way -- its `.pfs` check verifies record/field
counts and the CRC, not values, so it cannot see this layering. That is the reason it is written down
here.

### ⚠ D4's clamp contradiction -- RESOLVED 2026-08-20 at 40

The three `THero.Get*` STAT clamps sat at **30** live while D4 said 30->60; the manifest carried them
`UNCHANGED 30->30` with no ruling, RES annotated "DECISION REQUIRED". The user settled it at **40**
(not 60). Applied by `build_hero_clamps.py` -- write-up in `Hero_Stat_Clamps_40.md`.

**REPAIRED 2026-08-24:** the six missing `mov` twins (three `TUnit.Get*` clamps, three `SetUnit*`
caps), the Self-Destruct execute `push 8→16`, the breath/FlameThrowing attack 7→14 gaps and
Magebane's missed ATK half (count-register, no immediate — `BONUS_PER` now 2) all landed with the
DAM/HP doubling (`DamHP_Double_Decisions.md`, `build_damhpdouble.py` stage 1). The conversion's
clamps are monotonic again.

⚠⚠ **A clamp here is a PAIR of immediates, and this manifest only lists one of each.** The test and
the value written when it trips are separate instructions, both carrying the ceiling:
`cmp ax, N` (imm at `0x557883CB` etc.) **and** `mov byte [esp], N` (imm at `0x557883D1` etc.).
Patching only the `cmp` gives a silent discontinuity -- 31..40 pass, >40 snaps back to 30. That state
was actually reached during this work and caught only by disassembling the result. **Treat every
`UNCHANGED` clamp entry in this manifest as under-specified until its `mov` twin is located.**
`THero.GetDamage` (`0x557884EF`) was ALSO raised to 40 the same day — a separate explicit decision, not implied by the conversion, since damage is not a doubled stat. Only `TUnit.GetDamage` (`0x55782AD7`) stays at 30, and ⚠ it uses a DIFFERENT encoding (`cmp dx,imm8` + `mov al,imm8`).


### Traps found by staging (each would have been invisible in a bulk apply)

- ⚠⚠ **Relocating a cave body invalidates every OTHER script's address inside it.** The Marksmanship
  insert shifted 70 bytes by 2, and one of those bytes was `build_statdouble.py`'s stage-12 entry --
  which then aborted the whole verify with "neither the live nor the target value". Nothing warned:
  the byte was still correct, just 2 bytes further on. **Before relocating anything, grep every
  build script and manifest for addresses inside the range you are about to move**, and make the
  relocating script own the fix-up in both directions rather than hand-editing once.
- ⚠ **`build_invis_penalty.py` and `build_ranged_slayers.py` report `[x]` even though their bytes are
  correct.** Both verify their cave *including the trailing terminator*, and `build_magebane.py` has
  repointed those terminators (`0x5580E399` -> `0x558129C0`, `0x5580E3D9` -> `0x558129F0`). Verified
  by disassembly that the installed constants are right: `sub bl,2` / `sub bl,2` / `sub [esp+4],6`
  for invis, `add [esp+8],2` + `add [esp],1` at all four ranged sites. `build_assassin.py` already
  has the `preserve_terminator()` fix and reports clean; these two have not been given it yet. **A
  false `[x]` here is a script defect, not a byte defect -- do not "repair" the binary over it.**
- ⚠⚠ **Stage 10 — BACKWARD instruction decoding is unreliable in BOTH directions.** Stage 8 added
  "prefer the longest non-branch decode" to dodge spurious `jmp` matches. That heuristic then picked
  the **wrong** instruction here: `MakeDefaultLevelUnit`'s DEF write is `C6 43 3D 02`, and the `3D`
  displacement byte is also the `cmp eax,imm32` opcode, so a 5-byte `cmp` outscored the correct 4-byte
  `mov`. **Neither shortest nor longest is safe. Decode FORWARD from a known instruction boundary.**
  A forward sweep confirmed all 12 tier anchors and showed `+0x40` (DAMAGE) and `+0x3F` (HITS) sitting
  immediately after each RES write -- correctly excluded.
- **Stage 10 — one entry DROPPED.** `0x55760493` decoded with an `fs:` segment override (implausible for
  a Delphi field write) and the adversarial recheck had independently ruled it out: `+0x45` is a
  "not set" SENTINEL, not a defence bonus, and the owning class was never proven.
- **Stage 10 — an ambiguity resolved by TRACING, not by value.** `TWallCrushingAbility.fcExecuteCombat
  Command` passes `push 6` AND `mov ecx,6` to `CreateDamageCA`; both are 6. `CreateDamageCA` pushes its
  ECX arg FIRST, landing at `[ebp+0x10]` in `TDamageCA.Generate`, which reads `[ebp+0x10]` as ATTACK and
  `[ebp+0xC]` as DAMAGE. So `mov ecx,6` (`0x557688F8`) is the attack; `push 6` (`0x557688EF`) is the
  damage and stays. Guessing would have doubled Wall Crushing's damage output.
- ⚠ **Verifiers must accept SIGNED or UNSIGNED readings.** A post-apply sweep flagged three assert-only
  entries as "moved"; all three were byte-identical to the backup. One (`0x557680CD`) records its live
  value unsigned (246) while the check read signed (-10). Two others (`0x55786355`, `0x5576B235`) carried
  **garbage recorded values** from the re-anchoring -- they are prose about a hook, not immediates. Both
  are now corrected and marked `badAnchor`.


- **Stage 9 — the script only knew one binary.** `code_state` and both write loops indexed a single
  buffer, so every AoWTCPCK entry would have been read and written **at that offset inside
  AoWEPACK.dpl**. Now module-keyed off each entry's own `module` field, with a backup per touched file.
- **Stage 9 — the marker covers only AoWEPACK.** AoWTCPCK carries none, so a restore of one file
  without the other desyncs silently, and re-running `--apply` would NOT repair it (the stage is no
  longer pending). Added a **DESYNC warning**: any stage marked applied whose sites are back at their
  live values is reported. Stage 9's own values are self-distinguishing (−2→−4, 6→12, 10→20), so a
  second marker was not needed — but stage 10 should re-check that assumption.
- ⚠ **The marker mask is a u32, not a byte.** Stage 9 is bit 8, so a byte-level read of the mask shows
  `0xFF` and looks complete at stage 8. Read all four bytes (`0x1FF` = stages 1–9).
- **Stage 9 offset aliasing held.** `[this+0x20]` is DEFENCE on `TCombatTerrain` but **HIT POINTS** on
  `TCityWall` and `TCombatStructure`. Only the `TCombatTerrain.Activate` write was touched; the HP
  write 20 bytes away (`0x41092B` = 3) and `WallMaxHP` stayed `UNCHANGED` and were verified after.


- ⚠⚠ **Stage 8 — a backward instruction search finds SPURIOUS SHORT DECODES.** Two entries appeared to
  be `jmp` displacements (which must never be written -- doubling one changes a branch target). They were
  not: `sub bl,2` is `80 EB 02`, and decoding from +1 lands on `EB 02` = `jmp +2`, whose "immediate" also
  lands on the target byte. **Always prefer the LONGEST non-branch decode**, and reject any owning
  instruction that is a branch. A naive search validates the wrong instruction.
- ⚠⚠ **Stage 8 — a third of the family belonged to other scripts.** 11 of 32 candidates sat inside caves
  owned by `build_assassin.py`, `build_ranged_slayers.py`, `build_invis_penalty.py` or the cave
  `build_marksmanship8.py` hooks. Writing them from `build_statdouble.py` would have broken those
  scripts' verify/undo paths. **Check cave ownership by address range before every stage**, using the
  `CAVE*` constants declared across `build_scripts/`.


- **Stage 7 — scope by ADDRESS RANGE, not keywords.** After three keyword mis-scopes, stage 7 was
  assigned by the `CombatSpells.*` namespace bounds from `.edata` (`0x557F3CC8`–`0x557FAA70`). That is
  objective and cannot over-match. It caught all **five** Terror power copies in one group.
- **Stage 7 — the +0x34 / +0x35 adjacency held.** Spell power and spell damage sit **4 bytes apart** in
  the same `mov byte [eax],imm8` pair. All 30 damage neighbours verified `UNCHANGED` before and after
  the write. Anchors re-confirmed by decoding each owning instruction and checking the immediate lands
  exactly on the target byte (27/27 `c6 00 xx`).
- ⚠ **A display artefact is not a defect.** A quick disassembly loop starting at `immVA-1` rendered every
  spell site as `add byte ptr [eax], cl` — alarming, but purely a mid-instruction decode. Decoding from
  the true instruction start showed clean `mov byte ptr [eax], N`. Always resolve the *owning*
  instruction (search back until `imm_offset` lands on the target) before concluding an anchor is wrong.
- **`TDeathRay` idempotence collision is handled** — live 4, doubled 8, pristine 8. Safe because
  verify-before-write keys on the **live** value, never pristine, and the marker records applied state.


- **Stage 6 — "Underground" contains "ground".** A hazard-family regex matching `ground` pulled the
  ranged Underground/Cave ATK malus into the strategic-hazard stage. Caught by a **register-role check**
  (every stage-6 immediate must target EDX/EBP = attack, never ECX/ESI = damage) — the intruder decoded
  to a `jmp`, not a `mov reg,imm`. **Stage regexes must be anchored at the start of the description**;
  loose keyword matching has now mis-scoped three times (`Fury`->`TWindsOfFury`, `ground`->`Underground`).
- **Stage 5 — the fail sentinel held.** `TTouchAbility.GetTouchAttack` base returns −10 (`0xF6`), tested
  for *equality* at `0x557681FC`. It is correctly `UNCHANGED`; doubling it to −20 would have made every
  touch ability that does not override `GetTouchAttack` silently start succeeding instead of failing.
  Verified still `0xF6` after the apply.


- **Stage 1 — direction, not value.** `THero.UsedSkillPoints` holds a second copy of every skill price.
  A name-based classifier read "skill-point price", matched a stat, and scheduled a **doubling** — while
  its `SetUnit*` twin was correctly **halving**. Live bytes all matched; only checking which way the
  arrow pointed caught it. Shipped, `GetSkillPoints` would have gone negative and refused every purchase.
  **Every stage must include a direction check, not just a value check.**
- **Stage 2 — tag maps are per file.** `Unitres.pfs` uses `0x0E/0x0F/0x13` for ATK/DEF/RES; in
  `HERORES.PFS` **`0x13` is MOVES**. Reusing the map would have doubled hero movement to 48-72 and left
  resistance alone. Verified two independent ways before writing.
- **Stage 3/4 — a false "self-validated" anchor.** The re-anchoring pass resolved the LifeMastery Fear
  power to `0x55780BEC` (the 2nd byte of an imm32) and passed its own value check only because `0`
  appeared in the claim set. **`0` is too low-information to validate against.** True immediate is
  `0x55780BEB` = 4 -> 8. 22 entries resolved to value 0; only that one was scheduled to write, and the
  other 21 are assert-only — but their "verified" status is soft and must not be relied on if any is
  ever promoted to a write.
- **Stage 3 — substring over-match.** A family regex containing `Fury` also matched `TWindsOfFury`,
  pulling three combat-spell powers into the ability-modifier stage. Stage boundaries must key on the
  class namespace (`PassiveAb.*.Get(Attack|Defense|Resistance)`), not loose keywords.
- **The script's own `--undo` was not byte-perfect** — it left four magic bytes behind. Caught only by
  byte-diffing against the backup rather than trusting its "UNDONE" message.

## 4. ⚠⚠ SAVE-GAME BREAKAGE — accepted, but it is silent

`TUnit` stores only a **resource index** (tag `0x0A`), so units re-read `Release/Unitres.pfs` on load and
pick up the doubling automatically. **Heroes do not.** `THero.ReadWrite @0x55788880` serialises bought
stats as tags `0x10` (+0x6A ATK), `0x11` (+0x6B DEF), `0x15` (+0x6F RES).

A hero in a pre-conversion save loads as `2×base + bought` instead of `2×(base + bought)` — 1–3 points
light on each stat, i.e. **5–15 pp of to-hit in the wrong direction**, with no visible symptom. It also
recomputes spend at the halved costs, silently refunding roughly half of every hero's spent skill points.

Measured in this install's own saves: `autosave.asg` 8 of 12 hero records carry bought stats;
`testAI.asg` ~85 of ~92; `Test.asg` ~84 of ~90.

**D6: accepted. Pre-conversion saves are invalid — start a new game.** Not fixed, by choice.
(For the record, a fixer would be straightforward if ever wanted: `.asg` is `"CFS\0\x02"` + raw zlib with
**no checksum**, and the edit is a 1-byte in-place poke per hero record. It would need its own idempotence
marker so it cannot double twice.)

## 5. Open items -- ALL CLOSED (2026-08-20)

| # | item | resolution |
|---|---|---|
| O1 | `THeroResource.UsedSkillPoints @0x55789F50` charges the chassis at x5/x5/x10/x5/x5/x2 via **LEA scale/index -- not one immediate byte**. A 3/3/3 chassis reports 45 today, 90 after. | **COSMETIC, EDITOR ONLY -- accepted.** Zero rel32 callers inside AoWEPACK; imported by `AoWDevEd.exe` / `AoWEd.exe` only (never `AoW.exe`), each with exactly **one** caller: `0x00412725` in AoWDevEd. That function does `UsedSkillPoints -> SysUtils.IntToStr -> Engine.ReplaceText -> Controls.TControl.SetText` and returns -- **no comparison, no conditional branch, no budget check anywhere**. It does not gate saving a chassis. The displayed figure simply doubles, which is arguably correct under the new scale. If it ever wants halving, one `shr eax,1` on the total suffices (the x5 terms cannot be halved individually). |
| O2 | `comb_res.pfs` -- is `TCombatTerrain+0x20` one of tags `0x14`-`0x17` (314 records)? | **NO STAT FIELDS -- the premise was wrong.** `TCombatTerrain` does not exist: no such export, no such class. `comb_res.pfs` parses `top=True`, 581/581 records; the "314 records" are the class-word `67012200` group, which is combat-map **scenery** -- Rock, Tree, Shrubs, Dead Tree, Stones, Bones, Throne, Crops, Cactus, Plants... Its one-byte tags are a category index (`0x11`: 1-5,12), a sprite/variant index (`0x12`: 1-16) and percentages (`0x15`: 20/25/40/50/70/100). Nothing on the +-10 stat scale, nothing opposed by a to-hit roll. The only attackable scenery in tactical combat is the city wall, whose defence lives in **code** and is already covered (audit S4a). No `.pfs` change needed. |
| O3 | Turn Undead damage = `(level x casterRES + 1) >> 1`. Doubling RES doubles its damage. | **DONE** -- `build_turnundead_res.py` now emits `DMG_ROUND=2`, `DMG_SHIFT=2`, i.e. `(level x RES + 2) >> 2`. The general sweep for other stat-derived damage caves found no further sites. |
| O4 | Idempotence: at least two sites where **doubled == pristine** (`TDeathRay` 4->8, Doom Gaze 3->6). | **DONE** -- `build_statdouble.py` carries a marker dword (`Z5PC` + a u32 stage mask) at `0x55818000` (file offset `0x117400`), plus all-or-nothing vector matching per stage. `marker_clear()` on undo restores byte-identity. |
| O5 | Marksmanship needs a structural edit inside a cave owned by `build_marksmanship8.py`. **Must be made by that script, or its verify/undo path breaks.** | **DONE, and the "must be that script" claim was wrong.** The cave at `0x5580C240` is unowned; `build_marksmanship8.py` verifies only the hook site and the call target, never the body. A separate owner, `build_marksmanship_atk2.py`, does the relocation cleanly -- see the Marksmanship section. Both `build_marksmanship8.py` and `build_magebane.py` still verify green afterwards. |

## 6. Traps already paid for

- ⚠ **`THero.UsedSkillPoints @0x55786CC8` holds a SECOND copy of every skill cost** (imm `0x55786CD3`=6,
  `0x55786CDA`=12, `0x55786CEE`=4). Halve only `SetUnit*` and `GetSkillPoints` returns **negative** —
  every later purchase refused, AI gates fail, the level-up dialog shows a negative balance.
- ⚠ **AI skill-point BUDGET gates must NOT halve** (`0x55787A52`/`A77`/`A9F`/`AC7`/`AEF`). They are
  denominated in skill points, a currency the reform does not rescale. The **three** stat thresholds
  (`0x55787A64`/`A89`/`AB1` = ATK/DEF/RES) **do** double. ⚠ `0x55787AD9` (DAM) and `0x55787B01` (Hits)
  **stay** — an earlier draft of this line wrongly listed the DAM one as doubling.
- ⚠ **`HEROES.PFS` is NOT fixed-stride** — zero-valued fields are omitted, and **tag `0x12` = hero DAMAGE
  sits inside the stat run**. The "RES = ATK_off + 5" rule holds for `Unitres.pfs` / `HERORES.PFS` only;
  on `HEROES.PFS` it writes into the hero's LEVEL. Resolve every field through its own body directory.
- ⚠ **The morale→ATK ladder lives in the same cave as the unit ATK clamp** (`0x5580C0F7`). The clamp
  doubles (imm `0x5580C133`/`0x5580C137`); the morale bands (`0x5580C115`, `0x5580C119`, and the
  `dec al`/`inc al` at `0x5580C11C`/`0x5580C120`) are **excepted per D2 — leave them**.
- ⚠ Two ability modifiers are **not** `mov al,imm8`: `TPoisonedAbility.GetAttack @0x557B9E68` and
  `TFuryAbility.GetDefense @0x557BB360` are `or eax,-N` (`83 C8 xx`), immediate at **VA+2**, not VA+1.
  `TBloodlustAbility.GetDefense` is `B0 FF` live but `83 C8 FF` pristine — a pristine-keyed patcher misses it.
- ⚠ **`.pfs` writes are in-place 1-byte pokes** — no length change, no directory re-emit. But
  `Unitres.pfs` and `HERORES.PFS` carry a trailing **CRC-32** that must be recomputed; `ITEMS.PFS` and
  `HEROES.PFS` have **no magic and no CRC** — appending one would destroy 4 real data bytes. Gate the CRC
  repair on the `1C DF 44 21` magic, and **abort** (never stamp a fresh CRC) if the existing residue is
  already wrong.
- ⚠ **`TTouchAbility.GetTouchAttack` = −10 is a FAIL SENTINEL**, tested for equality at `0x557681FC`.
  Leave it and its guards alone. Same class: `GetCombatInfo` writes `0xFF` to mean "hide this line" —
  doubling it would print "Attack: −2" on every ability with no attack.
- ⚠ **`TAbstractUnit.ExecuteResistanceRole @0x55781B48` is dead code** — zero rel32 callers, not in any
  VMT, not imported. Editing it is a harmless no-op; do not treat it as evidence the family is covered.
- ⚠ **Tactical wall defence is −2, not 0.** `CityWall.TCityWall.GetDefense @0x00405AD5` (AoWTCPCK) returns
  −2; only AoWEPACK's auto-resolve wall classes are `xor eax,eax`. Corrected in the audit doc §4a.

## Cross-references

- **`FivePct_Doubled_Sources_Inventory.md` — the itemised list of every doubled ATK/DEF/RES source**,
  stage by stage, plus what was deliberately NOT doubled (D2) and the one undecided item
  (`HEROES.PFS`). **Generated** by `build_scripts/gen_doubled_inventory.py --write` from the manifest,
  so it cannot drift; re-run it after any manifest edit.
- `Hero_Chassis_ATK_DAM_Double.md` — the 2026-08-20 chassis ATK/DAM doubling that layers on stage 2,
  and the undo-order rule it introduces.
- `Hero_Stat_Clamps_40.md` — all four `THero.Get*` ceilings raised 30 → 40, closing D4's
  contradiction, and the **clamp-is-a-pair-of-immediates** trap this manifest under-specifies.
- `HitChance_Increment_Audit.md` — the slope site inventory. ⚠ its §4c and §4g are **void** under this plan.
- `Excess ATK minimum damage bonus.md` — ⚠ its tables assume the 10 pp slope; under the identity they stay
  valid in *old-scale* terms, but every quoted `d` doubles.
- `Strategic_Map_Damage.md` — the seven hazard attack values.
- Memory: `[[aow1-hitchance-slope-sites]]`, `[[aow1-combat-math-decoded]]`.
