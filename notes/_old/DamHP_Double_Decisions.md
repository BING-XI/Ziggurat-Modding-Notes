# DAM/HP doubling — decisions and pre-verified sites

**Status: CONFIRMED WORKING (2026-08-24) except for ONE defect found in later play and fixed
2026-08-26 — that fix is APPLIED, UNTESTED IN GAME.**

> **⚠ 2026-08-31 — THE HP CEILING IS NOW 100, NOT 120 (applied, UNTESTED IN GAME).**
> User ruling: reclaim margin under the 127 signed-byte wall. All four families moved together —
> `THero.GetHits` ceiling and the `THero.SetUnitHits` purchase cap (both now owned by
> `build_hero_clamps.py`, ladder **80/120/100**), the unit computed-HP cap cave
> (`build_medal_hpmv.py` **v4**, `0x55818086`/`0x5581808B`), and the editor `HitsEdit` spinners
> (`build_editor_spinners.py`, ladder 50/120/100, 4 sites across both editor exes).
> `Set == Get` is preserved at **100/100**; margin under the wall is now **27**, not 7.
> Ownership of the SetUnitHits pair moved OUT of `damhp_manifest.json` because `entry_state`
> is two-state and cannot express a re-target — a byte holding the previous target reads
> FOREIGN and aborts the stage, so `--repair` can never reach it. The manifest's two entries
> were re-pointed to 100 so stage 1 still verifies clean (35/35) and `--undo` still writes 80.
> Everything below this box that says 120 describes the 2026-08-24 session as it happened.
>
> ⚠ **EXISTING SAVES: a hero already above 100 HP loses the excess, and the skill points
> spent on it stay spent.** `hero+0x6d` stores the PURCHASED bonus, not the total; `GetHits`
> now clamps `base + 0x6d` to 100, so a hero at base 30 + 90 purchased reads 100 and the top
> 20 points (40 skill points at 2/point) are dead. Nothing corrupts and nothing wraps — the
> next `SetHitPoints` just clamps current HP down to the new max. New purchases are refused
> past 100 because the `SetUnitHits` cap moved in lockstep. **This is the thing to look at
> first when testing in an existing game.** No unit or hero BASE exceeds 100 (`Unitres.pfs`
> HITS max 44, `HERORES.PFS` max 30), so the cap only ever truncates totals. Two changes landed that day, both untested: the HP-120 fix, and the hero Set==Get reconciliation
(ATK purchase cap 60->40, DAM ceiling 60->40). The defect: every unit that had gained
experience displayed HP 120. It was in the v2 HP-cap cave, not in the doubling itself; root cause,
the exact trigger and the fix are in the last section of this file. Everything else stands as
validated. This file is the master record of the DAM/HP doubling: the decisions (H1–H9 + adopted defaults), the verified byte model, and the
implementation inventory below. Manifest: `build_scripts/damhp_manifest.json` (147 entries, every
one byte-verified against the live binaries both before and after the write).

## The goal

Extend the 5% conversion's identity to damage and hit points: **every damage source ×2, every HP
pool ×2** → time-to-kill unchanged, half-step damage/HP become expressible. Congruence with the
ATK/DEF/RES doubling (`FivePct_Conversion_Manifest.md`).

## Decisions (user, 2026-08-24)

| # | decision | consequence |
|---|---|---|
| H1 | **Item DAM stays unchanged** (`ITEMS.PFS` tag `0x0D`, values 1..3) | item damage bonuses become half as influential — consistent with the D2 item exception for stats |
| H2 | **Medal DAM → `[0,0,1,2]`** (`DamageRankProgression @0x558E83CC`, currently `[0,0,1,1]`) | not a straight ×2 — a chosen curve; gold medal damage rises, silver stays half-step. ⚠ owned by `build_copper_medal.py` `STAT_TABLES` — change it THERE and append the current tuning to `PRIOR_TUNINGS`, or its verify refuses |
| H3 | **Level-up prices halve, from the LIVE (Ziggurat) values** | live prices are all even — DAM 8→4, HP 4→2. ⚠ The vanilla ×10/×5 quoted from the Ghidra decompile were wrong for this install; Ziggurat re-tuned the prices before the note-taking era. Never derive prices from the vanilla image |
| H4 | **Damage caps → 60** | `TUnit.GetDamage` 30→60 and `THero.GetDamage` 40→60 (both are cmp+mov pairs, addresses below) |
| H5 | **HP cap → "whatever is safe"** | pending the workflow's byte-width audit: HP fields are byte-wide and some read paths may be `movsx`, so the ceiling candidate is ≤127 (likely 120); blocked on the shared-with-GetMoves question at manifest entry `0x557885b8` |

## Pre-verified byte model (live disassembly, 2026-08-24)

### Prices — ⚠ every price is TWO immediates, every cap is TWO immediates

Same trap as the stat clamps (`Hero_Stat_Clamps_40.md`): the affordability check and the deduction
are separate instructions. `fivepct_manifest.json` lists only one of each — under-specified.

| what | site(s) | live | target |
|---|---|---|---|
| DAM price (UsedSkillPoints copy) | `imul eax,eax,4` imm `0x55786CE5` (an `add eax,eax` at `0x55786CE1` makes the effective price 8) | 4 | **2** (effective 8→4) |
| DAM price (SetUnitDamage) | `sub eax,8` imm `0x5578788A` + `cmp eax,8` imm `0x5578788D` | 8, 8 | **4, 4** |
| HP price (UsedSkillPoints copy) | `imul eax,eax,4` imm `0x55786CF7` | 4 | **2** |
| HP price (SetUnitHits) | `sub eax,4` imm `0x557878D6` + `cmp eax,4` imm `0x557878D9` | 4, 4 | **2, 2** |
| DAM purchase total cap (SetUnitDamage) | `cmp edx,0x14` imm `0x55787870` + `mov bl,0x14` imm `0x55787874` | 20, 20 | **40, 40** — denominated in damage points, which double; identity, proposed not yet ruled |
| HP purchase total cap (SetUnitHits) | `cmp edx,0x50` imm `0x557878BC` + `mov bl,0x50` imm `0x557878C0` | 80, 80 | **H5** — 160 overflows a signed byte; must land at the safe ceiling |

⚠ If prices halve and their twins don't, purchases are refused or skill points leak — the exact
failure class the stage-1 "second copy" trap documented for ATK/DEF/RES.

### Damage caps (H4) — cmp+mov pairs, two different encodings

| site | imms | live | target |
|---|---|---|---|
| `THero.GetDamage` | `0x557884EF` + `0x557884F5` (`cmp ax,imm8` / `mov byte [esp],imm8`) | 40 | **60** — owned by `build_hero_clamps.py`; re-tune it there (NEW=60 for the DAM row) |
| `TUnit.GetDamage` | `0x55782AD7` + `0x55782ADB` (⚠ different shapes: `cmp dx,imm8` / **`mov al,imm8`**) | 30 | **60** — the script's shape check must be widened before adding it to `SITES` |

### The `0x5580C800` cave — checked, no dependency

`THero.UsedSkillPoints` contains a `call 0x5580C800` to an **undocumented pre-existing Ziggurat
cave** (no build script owns it). Body: `movsx eax,[esi+0x6e]; imul eax,eax,3; ret` — it prices the
**movement** bonus at ×3/point. Movement never doubles, so its price never changes: the cave is not
touched by this work. Recorded because any future price edit must know that call is there.

## Discovery complete (2026-08-24) — verified findings

Draft manifest: session scratchpad `damhp_manifest_draft.json` (~250 sites across 6 stages). The
five most serious claims were **re-verified by live disassembly in the main session** — all held:

| finding | evidence | consequence |
|---|---|---|
| ⚠⚠ **Stage-1 clamp `mov` twins were never doubled** | `TUnit.GetAttack` cave: `cmp dx,0x28` but `mov al,0x14` @`0x5580C136`; `GetDefense`: `cmp dx,0x3c` / `mov al,0x1e` @`0x55782A86`; `GetResistance`: same @`0x55782B2E`; `SetUnitDefense` twin `mov bl,0x14` @`0x55787827`; `SetUnitResistance` twin @`0x55787957` | **live non-monotonic clamps**: ATK past 40 snaps to 20, DEF/RES past 60 snap to 30 — the same paired-immediate bug later found on the hero clamps, present in the applied conversion since stage 1 |
| **Self-Destruct attack half-strength** | `push 8` @`0x55768E67` (the arg actually passed to CreateSelfDestructCA) never doubled; stage 10 only got the display/valuation copies | SD hits at half to-hit vs doubled DEF |
| **≥50-damage assert** | `cmp ebx,0x32` @`0x55726C64` + Delphi assert path (`Combat.pas` string @`0x55726CE0`) | fine today (rolls ≤ ~30); **fires an assert dialog once damage doubles** — raise to 0x7F in the same apply |
| **Regeneration 8-bit wrap — latent VANILLA bug** | heal floor `mov bl,1` @`0x55780DD6`; heal applied by `add dl,bl` @`0x55780DF2`, uncapped | high-XP Regeneration units can wrap past 127 and land near 0 HP **today**; the overheal fix (cap heal at missing HP) is what makes HP cap 120 safe |
| **hpbar low-clamp fix NOT installed** | `0x5575A824` holds the original 12 bytes; the documented cave `0x55812000` was reclaimed by the conversion | re-apply at a fresh cave in S6 |

**H5 resolved by the audit:** with the overheal fix in, the true HP ceiling is 127; the chosen safe
cap is **120** (both hero HP cap pairs 80→120). Without the fix it would be 64 for Regeneration
carriers — the fix is therefore part of the same apply, not optional.

## Second decision round (user, 2026-08-24, via question set)

| # | decision | consequence |
|---|---|---|
| H6 | **HEROES.PFS: double ALL FIVE bonus tags** (`0x10` ATK, `0x11` DEF, `0x12` DAM, `0x13` HP, `0x15` RES) | closes the conversion's long-open library-hero item; predefined heroes keep their designed edge. ⚠ NOT fixed-stride, tag `0x12` is DAM here (the known trap); NO CRC on this file |
| H7 | **Hero chassis DAM stays ×2 (parity)** | the 2026-08-20 hero buff dissolves into the global doubling; `build_hero_chassis_atkdam.py` FACTOR unchanged, HERORES DAM must NOT double again |
| H8 | **Medal HP doubles** (`build_medal_hpmv.py` K 1→2) | medal HP keeps its worth vs doubled pools; rides in the same cave rewrite that adds the unit HP total cap |
| H9 | **Marksmanship DAM → smooth ramp 1/2/3/4** (drop the `shr eax,1` in `build_marksmanship8.py`'s hook) | Leadership-style flat ramp rather than exact 0/2/2/4; odd levels gain slightly over strict ×2 |

## Standing recommendations adopted (no user question needed)

- **HP caps 80→120** (hero `GetHits` pair + `SetUnitHits` cap pair). GetHits/GetMoves have SEPARATE
  pairs (audit) — no shared immediate, no cave needed. Unit computed-HP cave cap also lands at 120.
- **NewTurn overheal fix** — mandatory (fixes the latent live Regeneration wrap AND lifts the ceiling).
- **Assert `cmp ebx,0x32` → `0x7F`** — mandatory before any doubled damage lands.
- **Floors 1→2**: GetDamage floors (unit+hero), GetHits floor, NewTurn regen floor, Resurrect+Animate.
- **Turn Undead**: exact ×2 — keep `(x+2)>>2`, append `add eax,eax` (no rounding drift).
- **Prices**: DAM via NOP of `add eax,eax` @`0x55786CE1` (live `03 C0` — engine encoding, not a cave's
  `01 C0`); HP `imul` 4→2; SetUnit price pairs 8→4 / 4→2; caps 20→40 / 80→120.
- **Conversion repairs ride along**: the five clamp `mov` twins + `SetUnitAttack` twin, Self-Destruct
  `push 8→16`, breath/FlameThrowing attack gaps, Magebane `BONUS_PER 1→2` (fixes its missed ATK half
  and the new DAM half with one knob).
- **AI**: budget gates stay (precedent); `UpdateDefensiveStrength` +10 anchors double; TU AI ladder
  doubles; saturation skew accepted.
- **Walls**: predictor keeps its existing ratio (10/5→20/10) — the mismatch vs executing walls is
  pre-existing and preserved, not widened.
- **Healing Showers 3→6** (preserves the user's own hand-edit ratio).
- **Editor spinner MaxValues**: poke both editors' DFMs — also fixes the ALREADY-LIVE re-save
  corruption of doubled stats (spinner ceiling 10 vs stats up to 20).
- **Old saves/scenarios**: accept breakage, new games only (D6 precedent). No migration tool.
- **Item family unchanged** includes the 5 engine-side bolt damage immediates.

## Superseded during discovery (kept for the pointers)

- The full DAM/HP site manifest (draft to be written to the session scratchpad, then reviewed).
- The HP width/`movsx` audit → resolves H5's actual number.
- Whether `THero.GetHits`/`GetMoves` share one clamp immediate (entry `0x557885b8`, live 80) — if
  shared, splitting it needs a small cave, since movement must not double.
- The healing/regeneration constant inventory (must double with HP or healing halves in effect).
- The Turn Undead re-tune: `(level × RES + 2) >> 2` → `(level × RES + 1) >> 1` via
  `build_turnundead_res.py` constants (`DMG_ROUND=1`, `DMG_SHIFT=1`).
- ⚠ `HERORES.PFS` DAM (tag `0x11`) is **already ×2** (`build_hero_chassis_atkdam.py`) — under the
  global doubling it becomes part of the identity, and it must NOT double again. Its HP (tag `0x12`)
  is *not* yet doubled and joins the data stage.


## IMPLEMENTED 2026-08-24 — the full inventory

**147 code immediates** (`build_damhpdouble.py`, marker `Z5DH`+mask @file `0x117408`, 4 stages,
surgical `--undo`) + **527 `.pfs` data bytes** (Unitres DAM tag `0x10` + HITS `0x11`, HERORES HP
`0x12`, HEROES.PFS all five bonus tags — CRC repaired where the file has one; HEROES/ITEMS have
none) + **62 description strings** (`build_pfs_typos.py`) + structural work:

| piece | script | note |
|---|---|---|
| clamps/prices/AI/assert + conversion repairs | `build_damhpdouble.py` stage 1 | assert `0x32→0x7F`; SetUnit DAM cap 20→40, HP cap 80→120, prices 8→4/4→2 (both twins each); UsedSkillPoints DAM via NOP of `add eax,eax` (`03 C0→90 90`), HP `imul` 4→2; AI DAM/HITS thresholds 10→20/30→60; DefStrength anchors 10→20; TU AI cap 5→10; **repairs**: 3 unit stat-clamp `mov` twins, 3 SetUnit* twins, SD `push 8→16`, breath+FlameThrowing attack 7→14, Marksmanship DMG rider `shr`→NOPs |
| HP + healing immediates | stage 2 | Healing 5→10 (4 cmp/mov pairs), DispelMagic AI 5→10, High Prayer 5→10 ×6, Remedy, Showers 3→6, walls (TCombatWall, TWallUnit, TCPCK tables + scenery + structures), MakeDefaultLevelUnit HITS ×4, Resurrect/Animate 1→2, NewTurn regen floor 1→2 |
| engine damage immediates | stage 3 | 85 sites: 22 spell `+0x35` bytes (+8 zero-verified), 11 ranged registrations, breaths, slayer/champ/charge adds, Wall Crushing ×10 + Self-Destruct ×8 (all 6→12), hazards ×7, storms ×6, 4 PassiveAb GetDamage, MakeDefaultLevelUnit DAM |

> ⚠ **CORRECTED 2026-08-26.** This row previously also claimed stage 3 covered **"Burning/Decay
> ticks"** and **"AoWTCPCK TCDamage"**. Neither is true, and the false claim is exactly what would
> make a future session conclude those sites were handled:
> - No Burning or Decay tick address appears in `damhp_manifest.json` or anywhere in `build_scripts/`.
>   `TBurningAbility.NewCombatTurn`'s damage (`0x557BA475`) and `TDecayAbility.NewCombatTurn`'s
>   (`0x557BA772`) were never doubled.
> - **`build_damhpdouble.py` never wrote a single byte to `AoWTCPCK.dpl`** — the module is
>   byte-identical to `AoWTCPCK.dpl.pre-damhp` across all 549,376 bytes. The 5% pass DID write to it
>   (4 bytes), so every DAMAGE and HP value in the manual-tactical-combat module is un-doubled while
>   its power siblings and its auto-resolve twins are doubled.
| data | stage 4 | 527 bytes; gated on the `HPC2` marker; parity all-even after |
| NewTurn overheal wrap fix | `build_newturn_healcap.py` | **fixes a latent VANILLA bug** (Regeneration 8-bit wrap to ~0 HP); 24-byte hook → PIC cave @`0x55818040`; lifts the HP ceiling to 127 |
| unit computed-HP cap 120 | `build_medal_hpmv.py` v2 | tail `jmp` → cap cave @`0x55818080`; K_HP 1→2 (H8); stamps `HPC2` @file `0x117410` |
| hero bounds | `build_hero_clamps.py` (ladder rewrite) | DAM ceiling 40→60 (H4), HITS ceiling 80→120 (H5), both floors 1→2; ATK/DEF/RES stay 40 |
| cave retunes | assassin 3→6, ranged_slayers 1→2, lifesteal/DarkGift 2→4, turnundead `DMG_SCALE=2` (exact ×2, `add eax,eax` after the shr), magebane `BONUS_PER 1→2` (closes its missed ATK half too), copper_medal Damage `[0,0,1,2]` (H2, v6 archived) | magebane dance: `--undo` (at BONUS_PER=1) → owners → `--apply` (at 2) |
| editor spinners | `build_editor_spinners.py` | 14 sites per editor, both exes, dynamic discovery by owner name (the audit's fixed offsets were off by ten bytes); ATK/DEF/RES/DAM→60, Hits→120, Moves untouched — **also fixes the pre-existing re-save clamp corruption** |
| hpbar low clamp | `build_hpbar_clamp.py` re-homed to `0x558180C0` | its old cave `0x55812000` had been silently reclaimed while the fix was not installed |
| manual | `build_ziggurat_manual.py` + `build_manual_exe.py` re-run | renders from live data, so doubled stats flow through |

New cave/marker map in the `0x55818xxx` zone: `Z5PC` @`0x117400`, `Z5DH` @`0x117408`, `HPC2`
@`0x117410`, healcap cave @`0x55818040` (49 B), medal cap cave @`0x55818080` (17 B), hpbar cave
@`0x558180C0`.

### Undo order (all surgical, no `.pre-*` restores)

`build_damhpdouble.py --undo` → `build_pfs_typos.py --undo` → owner retunes individually (magebane
dance for assassin/ranged/turnundead) → `build_medal_hpmv.py --undo` (returns to **v0**, not v1!) →
`build_hero_clamps.py --undo` (ladder[0] = pre-2026-08-20 state) → `build_newturn_healcap.py --undo`
→ `build_editor_spinners.py --undo` → `build_hpbar_clamp.py --revert`.

### Traps this pass paid for

- **`;` is a statement separator to keystone, not a comment** — an assembled-cave source with
  `; comments` fails with `KS_ERR_ASM_INVALIDOPERAND`.
- **A "floor" is a cmp/mov pair exactly like a ceiling** — the draft under-specified every floor.
- **Two of my own caves nearly overlapped** (healcap zone 0x60 reached the medal cap cave at +0x40);
  the free-zone assert caught it. Keep the cave/marker map above current.
- **The audit's editor-DFM offsets pointed at the property NAME, not the value byte** (+10 off) —
  dynamic pattern discovery beat fixed offsets, again.
- **`Ability.pfs`/`Spells.pfs` are `top=False`** — `build_statdouble.pfs_fields` (top=True) parses
  them wrong silently; the string locator needed its own directory walk.
- **Double ownership detected by "at-target before apply"**: two lifesteal imms appeared in both the
  damhp manifest and the owner script; the manifest rows were removed. Watch for that signature.

### Verified in-game (2026-08-24)

The user confirmed this works in-game ("Write this all up as working"). The checks that
confirmation covers:

1. **Combat feel is unchanged** — DAM×2 against HP×2 is an identity, so time-to-kill should match
   memory. Any obvious change means a family was missed or double-applied.
2. **No assert dialog on big hits** — a high-damage attack (doubled rolls reach 40+) would have
   fired the `Invalid Damage Value` assert if the 0x7F raise were missing.
3. **A Regeneration unit at high HP rests safely** — the old wrap made cur+max>127 snap to ~0.
   (This was broken in vanilla; it should now be fixed even at doubled pools.)
4. **Healing restores visibly the same fraction** (Healing +10 vs doubled pools).
5. **Hero level-up**: DAM price 4/point (cap 40 spent), HP price 2/point (cap 120), no refusals,
   no negative skill points; the exe-side price *display* was not traced — if a stale number shows
   there, that is the known bounded follow-up, not a data bug.
6. **Editor round-trip**: open a unit in AoWDevEd, save, reopen — stats must survive (spinner fix).
7. Turn Undead numbers on the info card still match dealt damage (both caves scaled together).
8. Medal HP +2/+4/+6; gold-medal damage +2 (H2 curve).
9. Old saves load with visibly halved current HP (accepted, D6/H16 precedent — new games only).


## 2026-08-24 (later) — the user's two challenges, and what they caught

### Self-Destruct: coverage re-proven by enumeration

All 19 `TSelfDestruct*` exports enumerated from the symbol table; every function disassembled in
the live DLL and every immediate tallied. Verdict: **complete.**

- ATK sites (6, all = 16): `GetDamageValue`/`GetDamageValueEx`/`fcGetDamageValueEx` `mov eax,0x10`,
  `GetCombatInfo` `[ebx+1]`, `GetOffensiveStrength`, and the execute `push 0x10` (the stage-10 gap,
  repaired). DAM sites (8, all = 12) likewise; the `imul eax,eax,0x64` is the ×100 MaxDamage
  scaling, not a stat.
- The word `0x0101` loaded everywhere = **dtFire|dtWall** — the "fire and wall damage" type mask.
  `Create`'s `[esi+0x24]=3` is a generic `TAbility` field (46 constructors set it, values 0..4/255).
- `TSelfDestructCA.Execute` reads only CA fields populated from the patched pushes — auto-scales.
- **No `tcGetDamageValueEx` exists for Self-Destruct** (unlike Wall Crushing) — the 10-vs-8 imm
  asymmetry is real, not a miss.
- AoWTCPCK's only reference is an **import of `CreateSelfDestructCA`** — tactical combat funnels
  through the patched engine creator. `aowInt`/`AoW.exe`: nothing.

### Regeneration wrap — corrected framing, and a sweep that caught real misses

**Correction:** the 8-bit overheal add is a **vanilla CODE defect that vanilla DATA could never
reach.** Pristine DLL: hero HP ceiling 30 (`cmp/mov` @0x557885B8/BC), purchase cap 30, no XP-hits
cave — cur+max ≤ ~60, no wrap possible. It became reachable when **Ziggurat** raised the hero HP
ceiling to 80 (cur+max up to 160) and added uncapped XP-hits growth; the HP doubling would have made
it routine. Mechanism verified by decompile: `TUnit/THero.SetHitPoints` clamps to max and floors
negatives at 0 — so a wrapped (negative) sum becomes **0 HP from resting/healing**.

**"Is 120 safe?" — the cap is not what makes it safe; the fixed adders are.** Without fixes, no cap
≥ 64 is regen-safe (cur+max ≤ 127 needs max ≤ 63) — i.e. the wrap class predates the doubling and
lowering the cap could not have fixed it. A systematic sweep of ALL 92 `SetHitPoints` call sites
(vmt+0xE4/+0x8C byte patterns, boundary-aligned disassembly, false positives on other classes
discarded) found exactly three remaining wrap-idiom sites, plus two heal doublings this pass had
MISSED (the draft carried them as singular-`imm` rows the converter skipped):

| site | was | now (`build_healwrap_fixes.py`) |
|---|---|---|
| High Prayer fast @0x557F7DE3 | `add dl,10` uncapped | 32-bit + 127 pre-clamp cave @0x55818100 |
| High Prayer tactical @0x557F7EC6 | same | cave @0x55818130 |
| Healing Showers @0x557A1DDD | `add dl,3` uncapped **and un-doubled** | cave @0x55818160, heal **6** |
| Remedy imm @0x557E739F | 5 (missed) | **10** (wrap-safe shape: 32-bit, max-clamped) |

Safe-by-construction (verified): HealUnit caps at missing HP first; HealingWater/CallHero/
HealUnits/NaturesBlessing set cur = max; lifesteal adds 32-bit + setter clamp; damage subtraction
floors at 0; the uncapped add in cave_5580C150 is DEAD code (bypassed by lifesteal_roundattack).

⚠ **Converter trap recorded:** the draft manifest used `imms` (dict) for most families but
singular `imm`/`edits` keys for structural rows — the converter only walked the dicts. Remedy and
Showers fell through that gap and were found only by the setter-callsite sweep. When consuming a
generated manifest, enumerate its KEY SHAPES first.

With these, every path that raises current HP is 32-bit and clamped — **the cap was safe at 120,
and 127 would have been safe too.** Lowered to **100** on 2026-08-31 by user ruling, which is
strictly safer again and buys 27 points of headroom for future additive terms (e.g. item HP
bonuses — see `Investigation_Items.md` FEATURE 2, whose 8-bit `add dl,[eax+0x6d]` trap is
exactly what that headroom protects).


### Charge: coverage re-proven by enumeration (2026-08-24, user challenge #3)

Charge (ability `0x6F`) has **no class** — only `ChargeRStr` exists; it is a generic enhancement
ability. So unlike Self-Destruct there is no per-class GetDamageValue / GetCombatInfo /
GetOffensiveStrength family to miss: its entire mechanical footprint is where the id is tested.

Every encoding of the id (`mov edx/ecx/dl/cl, 0x6F`, `push 0x6F`) swept across BOTH DPLs — nine
candidates, all triaged by boundary-aligned disassembly:

| site | verdict |
|---|---|
| `0x5576785F` + `0x55767BB7` | **the real thing**: `GetAbilityEnabled(0x6F)` → `add dword [ebx+4], 6` in BOTH melee strike tables — live-verified at 6, damage-only (no ATK component, matching the description), each followed by Parry's `0x71` test |
| `0x5576761B`, `0x557FA94A` | bulk **unregister** lists — and the second is the SPELL namespace (spell id `0x6F` ≠ ability id) |
| `0x5576F5BD` | Hurl Stones' registration icon/arg — coincidental byte. Led to verifying the whole registration block: 11 damage pushes (this pass) + 11 attack `mov cl` constants (stat pass) all owned; the remaining `push` middles are static range/ammo metadata, which never scales |
| `0x5575A61E`, `0x557DEF75`, `0x557E6F31` | IntToStr/format text, string data, misaligned false hit |
| `0x5574C9C2` | a serialisation field tag inside `TAoWHSSet.ReadWrite` |

AoWTCPCK.dpl: zero references (tactical executes engine-built strikes). No cave tests `0x6F`.
Display: with no class, the info card shows only the description text — already updated to (+6).
The First Strike interaction (defender reorder skips Charge) is ordering logic with no constants.


## 2026-08-26 — DEFECT FOUND IN PLAY: every unit with experience showed HP 120

**Symptom** (user, in-game): *"when my units gained any XP, their HP maxxed out to 120."*

**Root cause — the v2 cap cave compared a register that was only 8 bits wide.**
`TUnit.GetHits` is a pre-existing cave at `0x5580BE15` computing `rank*K + base + XP/(level+1)`:

```
5580BE38  call TUnit.GetExperience   ; movzx eax, byte [eax+0x3c]  -> EAX = 0..200, CLEAN
5580BE3E  mov  edx, 0                ; zeroes EDX, NOT the upper bits of EAX
5580BE43  div  cl                    ; 8-BIT divide: AL = quotient, AH = REMAINDER
5580BE46  jmp  0x55818080            ; -> the v2 cap cave
```

`div cl` divides **AX** by CL and writes only **AL** (quotient) and **AH** (remainder); it never
touches the rest of EAX. v2's cave then did `mov ebx,eax` / `add eax,ebx` / `cmp eax,120` at **full
32-bit width**, so the comparison saw `remainder<<8 | quotient`. Any non-zero remainder contributes
at least 256, so the clamp fired and HP became exactly 120.

The error is therefore a clean, deterministic multiple of 256 — not "a huge number". Bits 16-31 are
**zero**, because `TUnit.GetExperience @0x557828AC` is `movzx eax, byte [eax+0x3c]` and
`SetExperience` clamps XP to 200 (`cmp edi,0xC8`). **AH is the sole contaminant**, and it is enough.
Incidentally `mov edx,0` at `0x5580BE3E` is entirely dead — `DIV r/m8` never reads or writes EDX —
so nine bytes of no-op sit directly in front of the bug. ⚠ And `div cl` is **mandatory, not
incidental**: `TUnit.GetUnitLevel` returns a pointer-dirty EAX and only CL is clean, so "tidying" it
to `div ecx` (`F7 F1`, same length) would divide by a pointer.

**Exact trigger: `XP mod (level+1) != 0`.** Not literally *any* XP — experience that divided exactly
still computed correctly — but with divisors of 2..5 that is most XP values, and it re-rolls on
every XP change. Simulated across both cave versions:

| base | rank | level | XP | v2 (broken) | v3 (fixed) | XP mod (level+1) |
|---|---|---|---|---|---|---|
| 20 | 0 | 1 | 0 | 20 | 20 | 0 |
| 20 | 0 | 1 | 1 | **120** | 20 | 1 |
| 20 | 0 | 1 | 2 | 21 | 21 | 0 |
| 20 | 1 | 1 | 51 | **120** | 47 | 1 |
| 30 | 0 | 3 | 99 | **120** | 54 | 3 |
| 60 | 3 | 4 | 200 | 106 | 106 | 0 |

**Why it then stuck.** `build_newturn_healcap.py`'s cave asks the same `GetHits` (vmt+0xD0) for the
maximum and heals the unit up to it. Once the maximum read 120, the next turn topped the unit to
120 and it stayed there.

**Why it was invisible before the cap existed.** The result is consumed as a **byte**, which
truncated everything above bit 7, so the identical dirty add in the pre-clamp tail never showed.

⚠ **This is NOT a vanilla defect — an earlier draft of this section said it was, and that was
wrong.** `0x5580BE00..0x5580BE73` is **all zero** in `AoWEPACK_original_backup.dpl`: the whole cave
pair is mod-authored, and vanilla `TUnit.GetHits @0x55782B68` was a medal-table lookup at
`0x558E83D4` plus base HP, with **no XP term at all**. What *is* vanilla is the byte-return
**convention** that hid it — `TUnit.GetMovementPoints @0x55782B84` and `TUnit.GetUnitLevel
@0x55782B8C` both return EAX with a resource pointer in bits 8-31 and only AL meaningful (byte-
identical pristine and live). Per this project's own rule, never call something a vanilla bug
without byte-diffing the pristine DLL first.

> ⚠ **THE GENERAL LESSON, worth more than this bug.** Widening an 8-bit computation to a 32-bit
> compare does not merely *add a clamp* — it **promotes every previously-truncated dirty bit into
> the comparison**. Before putting a 32-bit `cmp` on a value, prove the whole 32 bits are defined.
> Zero-extend the 8-bit source explicitly (`movzx`), always. The compare is the new consumer, and
> it is stricter than the old one.

**Fix — `build_medal_hpmv.py` v3, applied 2026-08-26, UNTESTED IN GAME.** The cave's first
instruction becomes `movzx ebx, al` (`0F B6 D8`), so only the quotient byte enters the sum:

```
55818080  movzx ebx, al        ; was: mov ebx, eax
55818083  pop   eax            ; partial sum (rank*K + base) -- provably clean, <= 133
55818084  add   eax, ebx
55818086  cmp   eax, 0x78
55818089  jle   0x55818090     ; lands exactly on pop ebx after the 1-byte shift
5581808B  mov   eax, 0x78
55818090  pop   ebx
55818091  ret
```

Body 17 -> 18 B; zone `0x55818092..0x558180C0` re-verified all-zero (46 B spare); the version ladder
gained a v3 column, `TARGET_V = 3`, and `--undo` still restores v0 surgically.

### Two constraints found while auditing the siblings

- ⚠ **The HP cap must stay <= 127.** `build_newturn_healcap.py`'s cave narrows both HP values with
  `movsx ecx, al` / `movsx edx, al` — **sign**-extension. A cap above 127 would make those bytes
  negative and invert the heal clamp. 120 is safe; do not raise it without changing those two
  instructions to `movzx`.
- The heal cave itself is **correct**: it explicitly narrows to the byte before extending, so no
  dirty bits reach its 32-bit compare. The neighbouring `build_hpbar_clamp.py` cave at `0x558180C0`
  is also correct — its input comes from a **32-bit `idiv ebx`**, which fully defines EAX. That
  contrast is the whole diagnostic: `idiv ebx` defines all 32 bits, `div cl` defines only 8.

### Headroom check (why 120 is not squeezing)

`Release/Unitres.pfs` HITS after doubling: 179 records, min 6, **max 60**, mean 20. Worst realistic
total is `60 + rank 3*2 + 200/5 = 106` — under the cap. The cap legitimately binds only for a
maximum-XP low-level unit, which is itself evidence that every 120 seen in play was this defect.

⚠ **Open congruence question for the user.** Base HP was doubled but the **XP-to-HP term was
not** (`XP/(level+1)`, decision H5/H8). A veteran therefore now gains proportionally *less* HP from
experience than before the conversion — the identity holds for base HP but not for the XP bonus.
Doubling that term too would push the worst case to ~206 and break the <=127 byte wall, so it is a
real design choice, not an oversight to fix silently.


## 2026-08-26 — defect-class audit: every cave added in this pass, swept for the same shape

Nine independent read-only agents disassembled each cave and each clamp site and asked one question:
*does 32-bit arithmetic or comparison here run over a register whose upper bits could be dirty from
an 8-bit operation?* Results, worst first.

### LIVE — hero ATK: skill points bought above 40 are silently discarded

Byte-verified live, and **independent of the HP bug** — the audit found it, not the user.

| | address | value |
|---|---|---|
| `THero.SetUnitAttack` purchase cap | `0x557877D6` `cmp edx,0x3c` / `0x557877DB` `mov bl,0x3c` | **60** |
| `THero.GetAttack` effective ceiling | `0x557883C8` `cmp ax,0x28` / `0x557883CE` `mov [esp],0x28` | **40** |

A hero may spend 3 skill points per attack point all the way to a total of **60**, but the getter
clamps the returned value to **40**. Every point bought past 40 costs skill points and does nothing;
items and abilities above 40 are dead too. **Vanilla held Set == Get for all six stats.** This is a
half-finished migration: the 5% conversion's D4 entry raised the *purchase* cap 30 -> 60, and the
*getter* ceiling was separately hand-set to 40 on 2026-08-20; nobody reconciled them.

Full Set/Get table, read from the live binary:

| stat | purchase cap (`SetUnit*`) | effective ceiling (`Get*`) | |
|---|---|---|---|
| Attack | 60 | **40** | ⚠ wasted points |
| Defence | 40 | 40 | ok |
| Damage | 40 | 60 | benign drift — the extra 20 is item/ability-only, nothing is wasted |
| Resistance | 40 | 40 | ok |
| Hits | 120 | 120 | ok |
| Moves | 80 | 80 | ok |

**RESOLVED 2026-08-26 (user ruling): option (a) for ATK, and DAM matched at 40.** Live state is now
`Set == Get` for all five pairs — ATK/DEF/DAM/RES **40/40**, HITS **100/100** (120/120 until 2026-08-31) — byte-verified.
⚠ The audit's claim "vanilla held Set == Get for all six stats" was checked against the pristine
DLL and is **true**: vanilla is 10/10 for ATK/DEF/DAM/RES and 30/30 for HITS. (The `live` fields in
`fivepct_manifest.json` are pre-doubling **Ziggurat** values, not vanilla — reading them as vanilla
is a trap, and it briefly misled this analysis.)
⚠ **Consequence recorded deliberately:** `TUnit.GetDamage` ceiling is **60**, so heroes now cap
**below** units on damage. Vanilla had both at 10. One line in `build_hero_clamps.py` reverses it
(ladder target back to 60) if that turns out to be unwanted in play.

The two repairs, for the record — they were not balance-equivalent:
- **(a) lower the purchase cap to 40** — write `0x28` at `0x557877D8`/`0x557877DC`. Preserves the
  2026-08-20 decision that ATK tops out at 40. ⚠ These immediates are **owned by the
  fivepct/damhp manifest chain**, so re-tune them in `build_statdouble.py`/`build_damhpdouble.py`
  and extend that entry's ladder — do **not** let `build_hero_clamps.py` reach across and claim them.
- **(b) raise the getter ceiling to 60** — extend `build_hero_clamps.py`'s GetAttack ladder from
  `(30, 40)` to `(30, 40, 60)`. Preserves the D4 doubling. 60 < 127, so the encoding is fine.

Also decide explicitly whether Damage's Set 40 / Get 60 split is intended, and record the ruling.

### LATENT, highest priority — the MV twin is one edit away from the same bug

`0x5580BE6D` (the movement tail, reached from the MV entry `0x5580BE00` via `jmp 0x5580BE4D`) is
still `89 C3 58 01 D8 5B C3` — the identical `mov ebx,eax` / 32-bit `add`, fed by its own `div cl`
at `0x5580BE6A`. `TUnit.GetMoves` therefore returns `(remainder<<8)|value` **today**. It is harmless
only because every consumer truncates to a byte (~30 sites checked; `TCombatUnit.GetMoves`
`@0x55724FE0` even launders it with `movsx`). **Adding any movement cap or 32-bit consumer here
reproduces the HP bug verbatim** — it must use `movzx ebx,al` from the outset. The v2 docstring's
"the MV cave is untouched" read as reassurance when it is a landmine; that wording is now fixed.

### LATENT, benign by accident — the Regeneration heal cave

`0x55818040` sanitises both of its **own** byte-returning virtual calls (`movsx ecx,al` `@0x5581804B`,
`movsx edx,al` `@0x55818059`) but then does a 32-bit `add edx,ebx` `@0x5581805E` over an **EBX it
inherits from the host and never sanitises**. On the Regeneration branch that EBX comes from
`mov ebx,eax` `@0x55780DE4` straight off a byte-returning `GetHits`, which for
THero/TLeader/TAdjustableUnit/TWallUnit carries object-pointer bits above bit 7.

It does not misbehave, for two independent reasons: `LARGE_ADDRESS_AWARE` is clear, so heap pointers
are < 0x80000000 and the dirt is always large-and-**positive**; and the clamp maps every
large-positive sum to exactly ECX = max HP, which is the intended Regeneration result anyway.
Optional hardening (not required, sequence it as its own `--apply`): insert `movsx ebx, bl`
(`0F BE DB`) after `pop ebx`. Use **movsx**, not movzx — HP is a signed byte throughout
`SetHitPoints`. The cave grows 49 -> 52 B, still inside its 0x40 zone. Do **not** fix it at the
source (`mov ebx,eax` -> `movzx ebx,al` at `0x55780DE4` would overrun into the hook's `E8`).

⚠ Related re-tune trap: `mov bl,2` `@0x55780DD6` is safe only because the multiplier at
`0x55780E1C` is exactly 0.1. Raise it to >= 2.02 and a round result of exactly 256 gives `BL == 0`,
`EBX = 0x102`, and the 32-bit add turns "+2" into "heal to full".

### LATENT — the 127 encoding wall, now enforced instead of remembered

The `cmp` half of every `build_hero_clamps.py` bound is `66 83 F8 ib` (opcode `83 /7`), whose imm8 is
**sign-extended**, and the stored byte is read back with `movsx`. A ceiling of 150 (`0x96`) becomes
**-106**: `jle` is then false for every non-negative value, the clamp fires on every call, and the
getter returns a constant 150 — **the clamp inverts from a cap into a force**. HITS at 100 sits
**27** below the wall (it sat 7 below at 120 until 2026-08-31), and that headroom is load-bearing. The write loop accepted any byte 0..255; it now
carries `assert 0 <= w <= 0x7F` with the reason inline.

### CLEAN — audited and correct, listed so nobody "fixes" them

- **The three healwrap caves** (`0x55818100`, `0x55818130`, `0x55818160`) and the Remedy immediate.
  All three face the *same* dirty-EAX hazard — arguably worse dirt, since their input comes from
  `mov al,[eax+0x3e]` etc., so bits 8-31 are object-pointer bytes — and all three neutralise it with
  `movsx edx, al` as their **very first instruction**. This is the correct template.
- **`build_hpbar_clamp.py`'s cave** (`0x558180C0`): its input comes from a **32-bit `idiv ebx`**,
  which fully defines EAX. That contrast is the whole diagnostic — `idiv ebx` defines all 32 bits,
  `div cl` defines only 8.
- **The seven THero clamp sites**: every compared value is produced by `movsx r32, r/m8`, a full
  32-bit write, so the `div cl` failure mode has no analogue. 16-bit compares are provably wide
  enough.

⚠ **Do NOT "harmonise" the widening instruction across caves.** The medal cap cave narrows an
**unsigned** `div` quotient, so `movzx`. The healwrap caves narrow a **signed** HP byte
(`SetHitPoints` floors with `test bl,bl / jge`), so `movsx`. They are correctly different.

### Trap note — the vmt+0xD0 return-width contract

The cap cave now makes `TUnit.GetHits` return a genuinely clean 32-bit value, but the **other
overrides in the same slot do not**: `THero.GetHits @0x5578859C` ends `mov eax,edx` with a resource
pointer in the top bits, and `TCombatWall.GetHits @0x55725C30`, `TAdjustableUnit.GetHits
@0x55783858` and `TWallUnit.GetHits @0x55783660` are the same shape — **all of it vanilla**, which is
itself the proof that byte-width is the engine's contract for these getters. The hazard is that the
fix makes "GetHits returns a clean 32-bit int now" *look* true. Any new consumer of vmt+0xD0 must
launder AL with `movsx`/`movzx`, never read EAX. (`TCombatUnit.GetMoves @0x55724FE0` launders;
`TCombatUnit.GetHits @0x5572504C` forwards the dirty EAX unchanged.)


## 2026-08-26 — the gaps BOTH passes missed, and the morale re-scale

Prompted by the mod author asking whether Burning, the elemental RES check and the fear/entangle
checks had been handled. Two of the three were already correct; the question exposed a defect class.

### The defect class

> A paired **(POWER, DAMAGE)** site where the POWER fell in the 5% conversion's scope and was
> caught, while the DAMAGE ten to twenty bytes later fell in the DAM/HP pass's scope and was never
> enumerated — so **neither manifest contains it and both scripts report a clean all-clear**.

`build_damhpdouble.py` reporting "85/85 at-target" is true and worthless for these: the addresses
are not in its manifest. This is why a coverage claim must be derived from the manifest, never
written by hand — see the corrected stage-3 row above.

### ⭐ The worst instance: both passes patched DEAD CODE

`build_firefeed.py` overwrites `TriggerFireDamage`'s immunity gate at `0x5579020C` with
`jmp 0x5580DAD0`, so the original body at `0x55790211..0x55790227` **never executes**. Both passes
wrote their doubled values into that dead body:

| | dead body (skipped) | live cave |
|---|---|---|
| attack | `0x5579021D` = **12** (5% pass) | `0x5580DB07` = **6** |
| damage | `0x55790218` = **6** (DAM/HP pass) | `0x5580DB02` = **3** |

Because DEFENCE doubled **and** the to-hit slope halved, an undoubled attack is a **net loss**, not
a halving — burn chance against a DEF-5 unit fell from roughly 65% to 35%. With the stale damage on
top, strategic map fire was running about **4× too weak**, and the Fire-feeds-Fire "+N" heal was
halved too because `cave_fireheal` reuses this caller's ECX/EDX verbatim.

Fixed 2026-08-26 in `build_firefeed.py` (`MAPFIRE_ATK`/`MAPFIRE_DAM` = 12/6). The script's
verify-before-write now accepts **a list of prior cave bodies**, so the cave can be re-tuned in
place per CLAUDE.md instead of reverted — `PREV_MAPFIRE` holds the older (3, 6) body.
⚠ Never "fix" this by restoring `TRIG_ORIG` to make the doubled body live: that reverts
fire-heals-fire. ⚠ A foreign byte-poke into the cave is silently reverted by the next `--apply`.

### `build_damhp_gapfix.py` — the six AoWEPACK immediates in neither manifest

Ladder model, verify-before-write, surgical `--undo`, backup `.pre-damhpgapfix`.

| site | address | was | now |
|---|---|---|---|
| Burning tick damage | `0x557BA475` | 2 | **4** |
| Decay tick damage | `0x557BA772` | 1 | **2** |
| Turn Undead AI damage L1–L4 | `0x5576B223/226/229/22C` | 4/8/12/16 | **8/16/24/32** |

- **Burning** is the textbook case: its POWER twin at `0x557BA464` **is** in fivepct (10→20,
  applied) while the damage 17 bytes later was in nothing. Vanilla 1, Ziggurat 2.
- **Decay** is the purest case — there is no `HitRole` on that path at all, so no POWER half ever
  existed to drag it into a manifest. Mind Decay's spell ATTACK `0x557F8581` was doubled 6→12
  while this, its entire damage output, was untouched.
- **Turn Undead** is AI-only: real damage flows through `build_turnundead_res.py`'s caves
  (`0x5580E2A0`/`0x5580E300`), which do carry the ×2. The one live caller of the stale function is
  the AI heuristic `GetOffensiveStrength @0x5576AEDA`, so the AI was **under-valuing** Turn Undead.
  ⚠ Smoking gun for the class: the DAM/HP pass doubled that heuristic's **ceiling** 5→10
  (`0x5576AEE6`/`0x5576AEEA`) but never doubled the value being clamped. Fix the input, not the
  ceiling.

### Morale re-scaled — `build_morale_scale.py` (user ruling, reverses the D2 exception)

The 5% conversion deliberately left morale unscaled ("becomes half as influential"). On the doubled
scale a morale swing bit half as hard while the Manual still printed the old numbers. Reversed.

⚠ **Ziggurat's arrangement is NOT vanilla's, and the difference decides what to edit:**

- **ATTACK is a Ziggurat ADDITION** — vanilla has no morale→ATK link at all. `TUnit.GetAttack` is
  hooked to a cave at `0x5580C0FC` reading morale from `[ebx+0x26]`, five bands, then clamps ATK to
  [0,40]. Ladder was `-2/-1/0/+1/+2`, now **`-4/-2/0/+2/+4`**.
  ⚠ **It has BONUSES at high morale, not only penalties at low** — do not re-tune it as if only the
  negative end mattered.
  ⚠ Two rungs had **no immediate to double**: `dec al` (`FE C8`) and `inc al` (`FE C0`) were
  re-encoded in place as `sub al,2` (`2C 02`) and `add al,2` (`04 02`) — both 2 bytes, so the cave
  does not move and no jump displacement changes.
- **RESISTANCE** — `MoraleResistanceModifier @0x558E83D8`, vanilla `[-2,-1,0,0,0]`, Ziggurat
  `[-3,-2,-1,0,+1]`, now **`[-6,-4,-2,0,+2]`**. Read by `TUnit.GetResistance @0x55782AF7` and
  `THero.GetResistance @0x5578856D`.
- **DEFENCE deliberately NOT changed.** `MoraleDefenseModifier @0x558E83E0` is still vanilla
  `[-2,-1,0,0,0]` and still **live** — three readers (`TUnit.GetDefense @0x55782A6B`,
  `THero.GetDefense @0x55788449`, and a cave `@0x5580BFCE`). The ruling named Attack and Resistance,
  so morale's DEFENCE component remains half as influential. Adding a row for it is trivial (same
  encoding as the RES table) if that is ever unwanted.

### Verified correct — do NOT "fix" these

- **The elemental RES check is right**: six effect-roll powers at `0x55781C31/C91/CE3/D35/D87/DE7`
  are **10** (were 5), six Protection bonuses at `0x55781C20/C80/CD2/D24/D76/DD6` are **+4** (`83 C7
  04` live vs `83 C7 02` pristine), plus `sub edi,4 @0x55781B83`. Byte-checked, not taken on trust.
- **Every fear/entangle/touch check was doubled.** Entangle 14, Entangle Strike 14, Web 14, Possess
  14, Terror 16, Cause Fear 10, Holy Fear 8, Charm/Dominate/Seduce 10, Invoke Death 18. They differ
  only because their pre-doubling Ziggurat values differed.
  ⚠ **Cause Fear has no class of its own** — it is a flag set in `TStrikeCA.Generate`: roll
  `10 - defender stat` (`mov eax,0xa @0x55766914`), gated by Fearless `0x43`, then set the Panicked
  bit. **Entangle Strike's power sits 0x3A bytes later in the same function** at `0x5576694E` — that
  adjacency is why 14 and 10 get confused.
- **Nothing in the fear family has a damage half**: `TTouchAbility.GetCombatInfo` hard-writes
  DAMAGE = `0xFF` ("none") `@0x55768101`, and Terror's `spell+0x35` is 0 in vanilla and live.
- **Durations must never double** — Burning 2, Entangled 2, Frozen 3, Webbed 3, Stunned 1,
  Holy Fear 3, Vertigo 3, Cursed 3, `TDurationAbility` default 4 `@0x55764D0D`.
- **The touch-fail sentinel** `-10 @0x557680CD` and its three guards (`0x557681FE`, `0x5576817E`,
  `0x5576827D`) must stay mutually consistent — doubling the sentinel alone would make **every**
  touch ability silently start succeeding.
- **The buff/debuff regrade is one notch BELOW the doubled value on purpose** (user decision
  2026-08-24). Bloodlust +3, Poisoned -3, Enchanted Weapon +3/+3, Dark Gift +3, Blessed +1/+3,
  Stone Skin +3, Fury +5/-2, Vertigo -3/-3. A naive sweep reads these as un-doubled. They are not.
- **The two dead map-fire copies** (`0x55790218`=6, `0x5579021D`=12) are already doubled and
  unreachable. Leave them.

### ⭐ Standing check this earned — "is the site still reachable?"

Scanning all 383 AoWEPACK manifest addresses for an `E9` cave hook within 40 bytes **before** the
site returns exactly four hits: `0x55790218` + `0x5579021D` (this defect), `0x55782A1B` (already
flagged `dead:true`) and `0x5580E2B5` (already ruled owner-edited). Cheap to run, and it is the one
check that would have caught the map-fire miss. Worth adding to the QA agent.


## 2026-08-26 — AoWTCPCK.dpl: the module the DAM/HP pass never wrote to

`build_damhpdouble.py` has 145 manifest entries and **every one is module `AoWEPACK.dpl`**. The 5%
conversion *did* write here — exactly four bytes — so manual tactical combat was left
half-converted: every ATK/DEF value on the new scale, every DAMAGE and HP value on the old one.
Whole-file diff live vs `.pre-statdouble` was those four bytes and nothing else
(`0x004ED8`, `0x00FD3F`, `0x0661A4`, `0x0661A8`).

Script: `build_scripts/build_tcpck_damhp.py` (ladder model, verify-before-write, surgical `--undo`,
backup `.pre-tcpckdamhp`). **APPLIED 2026-08-26, UNTESTED IN GAME.**

### ⭐ The symptom: the game holds THREE independent wall-HP representations

The DAM/HP pass doubled two of them and missed the third:

| representation | where | vanilla | before | **now (unified)** |
|---|---|---|---|---|
| `TWallUnit.SetWallType` | combat **predictor**, AoWEPACK | 10 / 5 | 20 / 10 | **40 / 10** |
| `TCombatWall.GetHits` | **auto-resolve**, AoWEPACK | 10 / 5 | 48 / 16 | **40 / 10** |
| `AoWTC.WallMaxHP` | **manual tactical**, AoWTCPCK | — | 13 / 7 | **40 / 10** |

A stone wall had 13 HP in the fight you play by hand, 20 in the predictor that forecast it, and 48
if you auto-resolved the same siege — against damage that had doubled everywhere. Manual sieges
razed walls roughly **2× faster than the predictor promised and 3.7× faster than auto-resolve**.
`TCityWall.GetDefense` had already been doubled −2 → −4 by fivepct, so the same object's Defence was
on the new scale while its HP pool was not.

⭐ **USER RULING 2026-08-26: all three UNIFIED at 40 stone / 10 wood.** The x2 rescale landed
first (26/14), then the author ruled the three tables should simply agree. This is a **BALANCE
decision, not a doubling** — do not "restore" it to a x2 of vanilla (which was 10/5) or of
Ziggurat. Owners: the four AoWEPACK halves are `damhp_manifest` entries `0x55725C37`/`0x55725C3A`
(auto-resolve) and `0x5578362D`/`0x55783633` (predictor), retargeted and written with `--repair`;
`0x5578362D` also appears in `fivepct_manifest` and BOTH were retargeted so the two agree. The
`AoWTC.WallMaxHP` pair is owned by `build_tcpck_damhp.py`.
⚠ Both AoWEPACK halves store wall HP in a **byte** (`[TCombatWall+0x4D]`, `[TWallUnit+0x3E]`)
read with `movsx` — 40 is safely under the 127 signed wall; never raise it past 127.

### What was written (10 immediates, all int32 except the two blood bands)

| site | address | was | now |
|---|---|---|---|
| `TCDamage[0]` melee Wall Crushing | `0x004671AC` | 6 | **12** |
| `TCDamage[1]` burning fire hex / turn | `0x004671B0` | 1 | **2** |
| `WallMaxHP[0]` wooden wall **and every city door** | `0x004675F8` | 7 | **10** (unified) |
| `WallMaxHP[1]` stone wall | `0x004675FC` | 13 | **40** (unified) |
| `TCombatTerrain` HP | `0x0041092B` | 3 | **6** |
| `TCombatStructure` HP ×3 | `0x00432849`/`0x0043290E`/`0x0043291D` | 5 | **10** |
| `MakeHitBlood` band widths 1–2 (splat size) | `0x0040996C`/`0x00409971` | 3 / 4 | **6 / 8** (band 3 left at 93) |

`--undo` round-tripped exactly: the module then differs from `.pre-statdouble` by precisely the four
fivepct bytes and nothing else.

### ⚠ Traps this pass had to survive — all still live for anyone editing this module

- **SINGLE-APPLY CONGRUENCE GROUP.** The damages and the HP pools they eat must land together.
  Damages only → walls and structures crumble twice as fast. HP only → manual Wall Crushing and fire
  become half as effective (a 1-damage fire hex would need 26 turns to burn a stone wall). All
  together is behaviourally **identical**. Never stage it across two patches.
- **MANIFEST WIDTH DEFECTS — do not inherit them.** `fivepct_manifest.json` records
  `WallMaxHP[0..1]` as **one** entry at `0x004675F8` with `"width": 1`. They are **two separate
  int32 words**; a width-1 write leaves stone walls at vanilla HP. It records `TCDamage[0]` as
  width 1 as well. Everything here is int32.
- **A "NO-DOUBLE"/"UNCHANGED" ruling in fivepct is not a DAM/HP rejection.** It is the *stat* pass
  correctly saying "not an ATK/DEF/RES value". Both `0x004675F8` and the terrain HP carry one.
- ⚠ **PATCH THE ARRAY VALUES, NEVER THE POINTER SLOTS.** The package reaches these tables by Delphi
  IMPORTEDDATA indirection (`mov edx,[<slot>]; mov edx,[edx+idx*4]`). Slots `0x004693C4` (TCAttack),
  `0x004693FC` (TCDamage), `0x004693D0` (WallMaxHP), `0x00469408` (WallISIndex) **are** in `.reloc`;
  the values are not. The script parses `.reloc` and refuses to write any relocated address.
- ⚠ **ADJACENCY TRAPS on every side.** `WallISIndex[0..1]` `@0x004675F0` sits **8 bytes before**
  WallMaxHP and shares its `{type-1}` index expression — and `ImageLib.Get` has **no bounds check**,
  so corrupting it wrecks wall art or reads off the end of the image list. `clusterChk` `@0x00467600`
  sits immediately after; `raDir` `@0x004671B4` immediately after TCDamage; `StatusAbils`
  `@0x004675B8` holds ability ids up to 163, the same numeric band as HP. Use explicit addresses,
  never a range scan.
- ⚠ **"No xrefs" is never proof a table is dead here.** A literal-address scan finds **nothing** for
  the real consumers because of that indirection — it finds only the five AI-side reads and misses
  `Activate @0x00405716` and `SetHitPoints @0x00405C32/@0x00405C64` entirely. Both verification
  passes made this mistake before catching it.
- ⚠ **HP-shaped decoys inside the very functions that set HP**: `mov dword [eax+0x28],0x20`
  `@0x00405733` is an owner-player sentinel; `mov byte [eax+0x4d],1` `@0x00405B27` is a
  "wall breached this combat" **boolean** — and `+0x4D` is exactly the offset of the hit-point byte
  in AoWEPACK's *different* `TCombatWall`. The literal `6` at `0x00405BB8` is byte-for-byte
  `TCDamage[0]`'s value and sits inside the wall HP setter — it is a **rubble-sprite Z offset**.
- ⭐ **`MakeHitBlood` selects the blood-spray SIZE.** `@0x00409966` is a Delphi range-case on the
  DAMAGE value; the three immediates are band **widths**, not boundaries. Each band writes a tier
  into `[XYZ+0xc]` of the aowFX `TXYZList` entry, and the **Ziggurat cave at `0x437FA0` then ADDS
  a per-blood-type offset** (+5 / +0x2E / +0x20), so the final sprite index is `tier + offset`.
  If no band matched, the tier would stay 0 and the cave would yield sprite `offset+0` — a WRONG
  sprite, not "no blood".
  Bands now: **1..6 small, 7..14 medium, 15..107 large** (were 1..3 / 4..7 / 8..100).
  ⚠ **Band 3 is deliberately LEFT at `0x5D`** (author's ruling). It was briefly raised to `0x7F` on
  the theory that the raised `Invalid Damage Value` ceiling (127) made damage 108..126 reachable —
  **it does not**: a single hit's damage is bounded by the DAM stat (unit ceiling 60), so 15..107
  already covers every attainable value. The 127 assert is a safety margin, not a dealable damage.
  The `0x7F` rung stays in the script's ladder so that state still verifies. **Failed approach,
  recorded so it is not retried.**
  ⚠ Band 3 could not be DOUBLED in any case: `0x5D×2 = 0xBA` does not fit the signed imm8 of
  `83 E8 ib` — it assembles as `sub eax,-70` and **silently inverts the range test**. A true
  doubling needs `2D imm32` (5 bytes where there are 3), displacing two instructions and the
  `72 1a` / `eb 22` short jumps.

### Safe by construction — recorded so nobody "fixes" them

- **No signed-byte-127 hazard anywhere in this module.** Every HP path is 32-bit end to end and
  there is no upper clamp on wall, structure or terrain HP. The 127 wall lives on the AoWEPACK side.
- **Wall damage art rescales for free.** `TCityWall.SetHitPoints` derives the four stages as a pure
  **ratio** (state 0 if HP == max, 1 if HP > max div 2 via `sar eax,1`, 2 if HP > 0, else 3) — no
  hard-coded threshold.
- **No AI edit needed.** All five AI readers (`TCAI.EvalHex`, `TCAI.EvalBattle`) index the live
  array rather than carrying a copy, so the AI's model of wall toughness tracks automatically. It
  had been *over*-estimating its breach speed, weighing already-doubled damage against 7/13 walls.
- **`TCombatTerrain` HP is INERT.** `TCombatTerrain.SetHitPoints @0x00410138` is an 0x18-byte stub
  that **discards its edx argument**. Doubling it changes nothing observable; it is in because its
  DEFENCE sibling four instructions later was already doubled, and half-converted initialisers are
  the exact asymmetry this sweep removes.
- **`TCombatObstacle` has no HP field at all** — obstacles are indestructible in manual tactical
  combat. Checked, not missed.
- **Ranged Wall Crushing** (msg `0x31003`) takes every number from AoWEPACK ability data, already
  doubled. Nothing to patch — it is a regression check. Wall Crushing has **two executors** in this
  module; the melee one hard-codes `TCDamage[0]`, the ranged one reads AoWEPACK.

### Expected, not a bug: fire gets slightly slower

`ExecuteDamageRole` computes `((dmg-1)*(roll-esi) + (0x12-esi)/2)/(0x12-esi) + 1`. At `dmg == 1`
that degenerates to exactly 1 on every successful roll; at `dmg == 2` it averages ~1.5. So
`TCDamage[1]` 1→2 against doubled pools leaves fire roughly **25–33% slower** than before rather
than neutral. Generic to the DAM/HP programme at tiny magnitudes.

### Needs the user's in-game test

1. **Manual siege, stone walls** — count hits to breach. Should be the **same as before**: the whole
   pass is a rescale, so any change in hit count is a bug, not a feature.
2. Same for **wooden walls** and separately a **city door** (doors use `WallMaxHP[0]`).
3. **Predictor vs reality**: the forecast should now match the manual siege.
4. **Auto-resolve the same siege** — manual should no longer raze walls dramatically faster.
5. **Wall damage art**: all four stages still appear, at the same relative points.
6. **Wall Crushing in melee**: hits-to-destroy unchanged, and the damage the info card shows should
   now **agree** with what lands (they previously disagreed — display 12, executor 6).
7. **Fire in tactical combat** against a wall, a burnable terrain feature and a structure. It must
   still destroy them. ⚠ Expect ~25–33% **slower** (see above). A bug would be fire doing nothing,
   or destroying things in half the turns.
8. **Combat structures** (house, townhall) should no longer die to half the hits.
9. **Map editor**: place a structure, preview a battle — HP must match the game (all three
   initialisers moved together).
10. **Tactical AI during a siege**: should neither abandon breaching nor over-commit.
11. **Save/load** a battle with a partially damaged wall.
12. **Regression**: one ordinary non-siege tactical battle end to end. This module had never been
    patched before, so a plain smoke test is worth one battle.
