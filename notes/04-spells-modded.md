# Spells modded, and the spell research/economy systems

This file covers changes to spells that **already existed in vanilla** AoW1 — the sphere-tier
research rework, the Sphere Mastery casting-cost rework, the Crusade spawn-table rework, and the
storm/poison-plant debuff protection fix — plus the underlying spell-registry mechanics and ID
budget that any spell mod (old or new) has to work within. It does **not** cover: brand-new spells
(`05-spells-added.md`), abilities (`03-abilities-added.md`), or the separate unit-spellcasting
feature (`06-unit-spellcasting.md`, built from `06-unit-spellcasting.md` and its linked docs —
do not duplicate that material here).

All addresses are `AoWEPACK.dpl` preferred-base VAs (base `0x55700000`) unless a section says
otherwise; `AoWz.exe`/`AoWzCompat.exe` addresses are fixed-base `0x400000` absolutes. The DPL never
loads at its preferred base at runtime, so every DLL cave below is position-independent (rel32
jumps/calls, or the `call $+5; pop; sub` load-delta idiom for absolute data).

## Status table

| Feature | Status | Owning script(s) | Binary/file |
|---|---|---|---|
| Sphere-tier spell research (grant-whole-tier, flat cost, grouped picker UI) | ✅ **CONFIRMED WORKING (2026-07-18)** | `build_tierresearch_dll.py`, `build_tierresearch_exe.py`, `build_glowilb.py` | `AoWEPACK.dpl`, `AoWz.exe` + `AoWzCompat.exe`, `Int\Scenes\BookWin.ILB` |
| Spellbook hover-glow 2× boost (double-composite redraw) | 🛑 **WITHDRAWN (2026-07-18) — do not apply** | `build_glowboost.py` (script still on disk, never run) | `aowInt.dpl` |
| Sphere Mastery casting-cost rework (opposed ×1.50 / own ×0.75) | 🔨 APPLIED, UNTESTED (2026-07-30) | `build_mastery_cost.py` | `AoWEPACK.dpl` |
| Vanilla instant-cast raw-cost bug (coupled to Mastery, see below) | ✅ CONFIRMED WORKING (2026-08-27), per its own doc — owned elsewhere | `build_caster_cost.py` — **not one of this file's scripts**; full spec in `03-abilities-added.md` | `AoWEPACK.dpl` |
| Crusade spawn-table rework (mixed-tier rosters, 3 weighted outcomes) | 🔨 APPLIED, UNTESTED (2026-07-29) | `build_crusade_spawns.py` | `AoWEPACK.dpl` |
| Storm / Poison Plant debuff — roll vs Resistance | 🔨 APPLIED, UNTESTED (2026-07-30) | `build_stormeffectroll.py` | `AoWEPACK.dpl` |
| Storm debuff hard protection-block (design not shipped) | superseded pre-build by the roll-vs-RES design | — never built — | — |
| Animate Dead — permanent undead (`0x82` grant nop-ed) + Archer/Swordsman unit-type cave | 🔨 APPLIED, UNTESTED (recorded 2026-09-04) — **pre-convention hand-edit, no owning script, no `--undo`** | *(none)* — cave `0x5580C290` | `AoWEPACK.dpl` |
| Astral Ward (ex Spell Ward) — rescoped to block Town Gate + Warp Party only, and renamed | ✅ **CONFIRMED WORKING (2026-09-07)** (rename applied same day, untested) | `build_spellward_rescope.py` (+ `build_resstr_names.py`, `build_pfs_typos.py`, `build_ziggurat_manual.py`) | `AoWEPACK.dpl`, `Dict\ResStr.mld`+`.txt`, `Release\Spells.pfs` |
| Power Leech (ex Power Leak) — steal 25% of rival node power | 🔨 APPLIED, UNTESTED (2026-09-07; income row 2026-09-09) | `build_powerleech.py`, `build_powerleech_ui.py` (+ `build_resstr_names.py`, `build_pfs_typos.py`, `build_ziggurat_manual.py`) | `AoWEPACK.dpl`, `AoWz.exe`+`AoWzCompat.exe`, `Dict\ResStr.mld`+`.txt`, `Release\Spells.pfs` |
| Terror — spell ATK 16 → 12 (five immediates, all move together) | 🔨 APPLIED, UNTESTED (2026-09-09) | `build_terror_atk12.py` | `AoWEPACK.dpl` |
| Per-unit intrinsic spellbook | SPECULATIVE (feasible/hard, 72%) | none | `AoWEPACK.dpl` + `AoWz.exe`/`AoWzCompat.exe` |
| HP/MV casting cost (extra sacrifice on top of points) | SPECULATIVE (85% "in addition", 60% "instead of") | none | `AoWEPACK.dpl` |
| Unit-enchantment cost/upkeep scaled by target level | SPECULATIVE (85% upkeep, 55% cast-cost) | none | `AoWEPACK.dpl` |

Spell-registry mechanics and the spell-ID budget (below) are infrastructure reference, not a
feature with a status of its own — every row above depends on them.

---

## Sphere-tier spell research

**One entry per (sphere, tier)** in the research book — sphere icon, title "**Fire II**"
(sphere name + Roman numeral), member spells listed in the memo — and researching it grants
**every** unresearched spell of that sphere+tier at once, for a flat per-tier cost. User-approved
design, iterated v1→v7.9 across eight rounds of in-game feedback, **✅ CONFIRMED WORKING
(2026-07-18)**.

### Design decisions (resolved by the user, 2026-07-18)
1. Cost model: **flat per-tier ladder 100/200/400/800** (not summed member costs).
2. Cosmos included as its own tier ladder; day-1 grant avoids it when the leader has other picks.
3. Tomes still grant a single spell.
4. Title = sphere name + **Roman numeral** ("Fire I"), built from the RStr table so non-English
   installs stay correct.
5. Day-1 freebies: instead of 3 random spells, **one full tier-1 sphere** (random among picked
   spheres; Cosmos only if the leader has no picks at all).

### Vanilla mechanics this sits on top of

**`TSpell` registry entry** (via `TSpellControl.GetSpell(*(AoWHSSet+0x84), id)` @`0x55779AC8`):

| Offset | Type | Meaning |
|---|---|---|
| +0x10 | int | spell ID |
| +0x14 | int | base mana cost |
| +0x18 | int | research cost (points) |
| +0x20 | byte | sphere (0 Cosmos, 1 Life, 2 Death, 3 Earth, 4 Air, 5 Fire, 6 Water) |
| +0x21 | byte | research tier 1–4 (0 = not researchable) |
| +0x22 | byte | category (research uses categories 0,1,2) |
| +0x30 | int | AI research-weight value |
| vmt+0x64 | fn | enabled/valid predicate |

**`TPlayerMagicControl`** (`player+0x54`): `+0x24` mana pool, `+0x2c` research % of power
income, `+0x30` `TIntegerList` of researched spell IDs, `+0x34` current research spell ID (0 =
none), `+0x38` research points remaining. **`TLeader+0xa0`** = sphere-pick list (byte per pick);
`GetSpherePicks(sphere)` @`0x5578B17C` hard-returns **4** for Cosmos, otherwise counts picks.

`ValidResearchSpell(spell)` @`0x5577CFF0` — a spell is researchable iff **all** of: (1) picks
gate `tier ≤ GetSpherePicks(sphere)`; (2) not already researched; (3) tier-ladder gate — per
sphere, 2 researched spells of tier N unlock tier N+1 of *that sphere* (Cosmos has its own
ladder); (4) `AoWEngine+0x6e` quirk forces the ladder to a flat 2 when set (demo/unregistered-
version cap machinery, irrelevant on a registered install). Opposed-sphere restrictions live
entirely in sphere **picking** (`TLeader.CanAddSphere` @`0x5578B1F8`), never in research.

`NewTurn` @`0x5577CC2C`: on **day 1** only, grants one random tier-1 spell per category (0,1,2)
from spheres the leader has ≥1 pick in (direct list `Add`, bypassing `ExecuteSpellResearched`).
Every other turn: `+0x38 -= GetNetPowerToResearch()`; on completion, overshoot refunds to mana, an
event-log entry fires, then `ExecuteSpellResearched(id)` @call site `0x5577CDC4`.

**The cast picker and research picker are the same form**, `TSpellBook` (AoW.exe, VMT
`0x42DDA8`). Mode byte `book+0x220`: 0 cast-global, 1 cast-combat, **2/3 research**, ≥4 info.
Candidate list `book+0x224`. 8 slots/spread; population @`0x42EF14` → research branch @`0x42EF63`
calls `ListResearchSpells(mask=0x07)` @`0x42EF9D` → `SortOnLevel` @`0x42EFA8`; per-slot fill is
`FillSlot` @`0x42E8E0`; icon draw is `SpellIconDraw` @`0x4304C8`; select dispatches to
`ResearchSpell(id)` @`0x4307EF` with **no confirm dialog**. Sphere icons live in
`IntGfxMod.GenericI`: Life=27, Death=30, Earth=33, Air=36, Fire=42, Water=39 (+1 down/+2 lit);
Cosmos has none.

### As built — DLL layer (`build_tierresearch_dll.py`, `AoWEPACK.dpl`, backup `.pre-tierresearch`)

| Cave | VA | Hook | Behaviour |
|---|---|---|---|
| `cave_grant` | `0x5580ED80` (136 B) | `call` @**`0x5577CDC4`** (NewTurn completion site only) | runs `ExecuteSpellResearched`, then grants every registry spell with the same sphere+tier word (`+0x20`/`+0x21`), category ≤ 2, `vmt+0x64` true. Tomes and day-1 use other paths and stay single-spell. |
| `cave_cost` | `0x5580EE10` (28 B) | 6 B @**`0x5577D569`** → call+nop | `+0x38 = 100 << clamp(tier-1, 0..3)` → 100/200/400/800 |
| `cave_day1` | `0x5580EE30` (186 B; v2 182 B + 4 zero) | 7 B @**`0x5577CC72`** → jmp+2nop, exits `jmp 0x5577CD4A`. **v2 (2026-09-24)**: `call`+2nop, the routine ends `add esp,8 ; ret`, and `0x5577CC79` → `jmp 0x5577CD4A`; `build_pbem_leadersetup.py`'s `C_APPLY` calls it for a PBEM leader's deferred turn-1 grant (`07-ui.md` §10.6) | picked spheres (`GetSpherePicks>0`, s=1..6) → `Map.Random` picks one (Cosmos if none) → adds ALL its tier-1, category ≤2, enabled, unresearched spells directly to the researched list |
| `cave_evtext` | `0x5580EEF0`+ | 6 B @**`0x5577C4B4`** in `TPlayerMagicEventLog.GetText` → call+nop | research popups/log read "**Death I** researched" (sphere RStr + Roman) instead of the representative spell's name |

Caves end `0x5580EEEA` (zone limit `0x5580F400`). Globals (`[0x558FA044]` AoWHSSet,
`[0x558FA040]` AoWHSMap) reached via the call/pop rebase-delta idiom; in-module calls rel32.

### As built — EXE layer (`build_tierresearch_exe.py`, both exes, backup `.pre-tierresearch`)

New section **`.tres`** @ VA `0x611000` (9th section, RVA `0x211000`, `SizeOfImage`
`0x211000→0x212000`, `NumberOfSections` 8→9). Blob `0x390` B: ROMTAB (8 ptrs) @`0x611000`,
Roman-numeral literals @`0x611020`+, ICONTAB @`0x61105C` (`0,27,30,33,36,42,39,0`).

| Cave | VA | Hook | Behaviour |
|---|---|---|---|
| `cave_group` | `0x611070` | call @`0x42EFA8` (research `SortOnLevel`) | snapshots enabled candidates to a BSS side buffer (`0x45B330`/count `0x45B320`, cap 500), replicates the vanilla `id≥100` SpellTypes filter, then arranges representatives into a **nil-padded list of 8-slot spreads** (sphere 0..6 × tier 1..4 order), written back into the same `TSpellList` object |
| `cave_title` | `0x611110` | call @`0x42E926` (name `SetGText`) | modes 2/3: "{SphereRStr} {roman}" |
| `cave_class` | `0x611170` | 13 B @`0x42E991` → jmp+8nop | modes 2/3: blank the class label (was a duplicate of the title) |
| `cave_memo` | `0x611190` | call @`0x42EAAC` (memo `SetFStrings`) | modes 2/3: Clear the memo's `TStringList` (`+0x118`, vmt`+0x40`), then `Add` (vmt`+0x34`) member names from the side buffer, greedy ", "-joined, flush ≥30 chars |
| `cave_turns` | `0x611290` | 5 B @`0x42ED93` → call | `ecx = 100<<(tier-1)` (edx=perTurn preserved) so the displayed turn count matches the DLL flat cost |
| `cave_icon` (v2) | `0x6112C0` (~236 B) | 5 B @`0x4304C8` → jmp | modes 2/3: no left icon; draws **tier-count sphere icons side by side** under the entry text at full opacity (v5 dropped the earlier 40%-blend watermark idea — see version history); Cosmos draws nothing |
| `cave_costskip` | `0x6113B0` | 7 B @`0x42EAB1` → jmp+2nop | modes 2/3: skip the "Cost:"/"Upkeep:" mana sections |
| nil-pushes | — | 4 byte patches @`0x42EDA7`/`AD`/`0x42EE0D`/`13` | research turns label reads just "Turns: N" |

**Revert:** each script's own `--undo` (surgical, zeroes its cave and restores the displaced
bytes, touches no backup). The exe presentation layer only makes sense with the DLL mechanics
layer active (grant-on-complete + flat cost) — undo the exe half first, or both together; don't
leave the exe grouping cave live against a reverted DLL.

### ⚠ Do not apply `build_glowboost.py` — WITHDRAWN, still on disk

A separate, earlier attempt at the same "make the hover-glow stronger" goal, targeting
`aowInt.dpl` (backup `.pre-glowboost`): it drew the BookWin lit strip **twice** per hover
(translucent double-composite) via two caves on `TAOWBaseButton`'s lit-draw sites
(`DrawILLh`/`DrawILI`). **The book never repaints the parchment under a button between paints**,
so any extra translucent layer accumulates — the double-draw caused unbounded ghost buildup
("whack-a-mole" brightening of unhovered entries). It was applied, tested, found broken, and
**reverted** on 2026-07-18; `.pre-glowboost` was restored *at that time*. **Do not restore that
backup now** — `.pre-bltprobe` has since been layered onto `aowInt.dpl`, so `.pre-glowboost` is no
longer the newest layer and restoring it would undo the Blt-error probe work. The **correct**
fix — one-time data edits to the stored ILB image, no extra compositing — is what actually
shipped: `build_glowilb.py` below.

### Glow art — `build_glowilb.py`, `Int\Scenes\BookWin.ILB`, backup `.pre-glowilb`

Two idempotent data edits to image 26 ("SBBtn.BMP", class `0x16 TSprite16`, the hover lit strip),
verified against the current script: **intensity 20% → 70%** (`img+0x3C` percent byte, mode
`02 03` = INTENSITY blend), **height 82px → 100px** (raw 16-bit pixel data, `254×NEW_H`, built by
duplicating a middle row and appending the new data at EOF; every other image's offset is
untouched). `NEW_H=100` in the live script and `HILITE_H=100` in `build_tierresearch_exe.py`
agree — this is the confirmed final value; the version history below documents intermediate
values (82→96) that a mid-iteration doc snapshot can show but that are **not** the shipped state.

Record layout (image 26's record @ file offset `0xA50`): `+0x16` idx, `+0x1A` classid, `+0x1E`
ver(3), namelen+name, `w1@0xA66`/`h1@0xA6A`, `size@0xA7B`, `dataoff@0xA7F`, `w2@0xA83`/`h2@0xA87`,
`showinfo@0xA8B` (mode bytes) + `pct@0xA8F`, `pixfmt@0xA93` (`0x56509310`), `w3@0xA97`/`h3@0xA9B`,
…, terminator `FFFFFFFF`. The taller sprite only shows if the slot panel/button rects allow it —
`build_tierresearch_exe.py` sets both to `HILITE_H` in research mode (cast mode keeps vanilla).

### Version history (v1 → v7.9)

Compressed; the full reasoning for each fix is preserved in `_old/` if ever
needed again.

- **v1→v2** (first in-game screenshot feedback): dropped the initial `ShowClipped` left-icon
  approach — Cosmos had no icon and fell back to a spell icon, inconsistent with every other
  sphere. Removed slot Cost/Upkeep text (Turns only); added a blended tier-icon row instead.
- **v3** (2nd feedback round): "Currently Researching" page still named the individual spell —
  tier-ified via 4 hook-reused caves (title/class/cost/memo/icon). Watermark was invisible
  because the test wizard had only Cosmos entries (no Cosmos sphere icon exists) — fixed with a
  **Cosmos icon = mana crystal** fallback (`IntGfxMod.UnitIcons+0x80`, index 5, the unit-window
  ManaIcon). Also decoded and fixed **clip inflation**: the draw context's clip rect was being
  left at the icon control's small size, clipping the watermark away — caves now overwrite their
  stack copy of `ctx+0x10..0x1C` to the full panel area.
- **v4** (user clarification): v3 **misread the intent** — the watermark was meant to be each
  *member spell's own icon* side by side, not sphere icons. Replaced both icon caves' row logic
  with a shared fragment walking each member's `TImageSequenceList` (sequence 10 = book icon),
  static frames only, blended blit per layer.
- **v5** (3rd feedback round): dropped the 40%-blend "watermark" framing entirely — full-opacity
  icons in their own space, cost/turns balanced across pages. Introduced the **slot-arranged
  nil-padded list** compaction (see Reusable machinery). Required **19 DFM byte patches** moving
  the S-slot memos down/taller (`WinTop`/`WinHeight`, both exes) — **this broke the CAST book**
  in v7 (see below), because the S-slots are shared between cast and research modes.
  - **v5.1** (crash fix): vanilla's `id≥100` SpellTypes filter loop @`0x42F2D1` ran *after*
    `cave_group`'s now-nil-padded list and read `[spell+0x10]` unguarded → AV. Fixed with a
    nil-guard hook @`0x42F2F1` that redirects nil/`id<100` entries past the filter.
- **v6** (4th feedback round): names were invisible — the memo at y84 was **clipped by its 80px
  parent panel** (child controls clip to panel bounds; cave-blitted icons bypass that, which is
  why *they* showed). Panels grown 80→127px (the vaInt8 DFM ceiling). Added "Turns: N Research
  Points: C" text and **per-icon names drawn under each icon** using `TImageLibraryFont` (see
  Reusable machinery) — memos became redundant and were reduced to a `Clear` only.
- **v7** (5th feedback round): v6's *static* DFM patches broke the cast book (taller panels +
  moved memos overlapped cast entries, since the S-slots are shared). **v7 removes all DFM
  patches** — cast view goes back to byte-exact vanilla — and handles research geometry **at
  runtime** instead: `cave_layout` writes each slot panel's `WinTop` directly (inlined
  `TAoWComponent.SetWinTop`) once per population, 3 entries/page at 112px pitch for research,
  vanilla spacing otherwise.
  - **v7.1** (6th feedback round): mixed/overlapping layout, and hovering one entry erased the
    row above's names. Root causes: (a) the panels have alignment **NONE**, so v7's
    relative-write-then-realign approach was a no-op — fixed by writing **final absolute** `Y`
    directly; (b) partial redraws only re-fire a control's `OnDraw` if the **control's own rect**
    intersects the dirty region, and the icons/names extended past the tiny 40×35 icon box — fixed
    by also writing the icon control's size fields so its rect covers the whole entry.
  - **v7.2** (crash fix): AV in `cave_layout` reading `nil+0x88`. Cause: **panels are
    window-class objects whose parent lives at `[obj+0xCC]`**, not the `+0x10C` control-level
    parent field that worked for `TAoWImage` — a genuine aliasing trap between sibling classes.
    Fixed with nil guards on the correct field.
  - **v7.3** (first-open pitch bug): vanilla pitch on the very first book open only. The S-panels
    have `Alignment ahTop` with `TopOffset` stored at `[pnl+0xD4]+0x20`; the first `Show` runs
    `ReAlign`, which recomputes from `TopOffset` and clobbers the population-time value. Fix:
    `cave_layout` writes **both** the alignment object's `TopOffset` (so any future `ReAlign`
    recomputes to the new layout) and the absolute `[pnl+0x88]`.
  - **v7.4** (first-open *offset* bug — self-healing fix): the very first population still ran
    before the page panel was absolutized, so titles landed ~14px high. Fixed with
    `cave_dlgupd`, an entry-hook on `TSpellBook.DlgUpdate` @`0x431270` (the dialog's per-tick
    update) that re-runs the population function whenever a panel's position doesn't match the
    expected value — converges to a no-op check and self-heals any future external disturbance
    within one tick (see Reusable machinery).
  - **v7.5** (7th feedback round): **glow-boost reverted** (see the warning box above — this is
    where that revert happened chronologically). Also restored the icon controls' size fields
    per-mode (research 262×104, cast back to vanilla 40×35) — the huge research rects had leaked
    into cast mode, amplifying the ghosting further. Added `cave_evtext` (research popups/log
    now name the tier, not the representative spell).
  - **v7.6** (8th feedback round): `cave_evtext` had a bug — `TMagicSphereRStr` holds loaded
    string **values**, not resourcestring records, but v7.5's cave `LoadResString`'d them anyway,
    reading record fields from a plain string → AV inside a try-frame → the popup silently
    disappeared. Fixed by passing the values straight to `TranslateRStr`. Also tier-ified the
    "Researched:" completion view (4 more hook-reused caves) and shipped the **glow ILB edit**
    (intensity 20%→40% at that point).
  - **v7.7**: the "Researched:" view showed only the tier name with no icons/names, because the
    completed tier's members are (by definition) researched and absent from the *candidate* side
    buffer. Fixed with a fallback: when the buffer has no matches, rebuild it directly from the
    **spell registry** (ids 0..511) instead of the candidate list.
  - **v7.8**: 40% intensity "seemed unchanged" — on bright parchment a 40% **intensity**
    (brightening) blend is nearly invisible. Raised to **70%**.
  - **v7.9** (taller highlight): wrapped two-line names ("Disease Cloud") spilled outside the
    lit strip, because `TInterfaceIL.DrawILI` draws it **unscaled** at its stored pixel size
    (254×82). Rebuilt the ILB image to 254×96 (documented at the time as 96px; the script's
    current, confirmed-applied value is **100px** — see the ILB section above) by duplicating a
    middle row, and made `cave_layout` also drive the **panel and button heights** per mode
    (`HILITE_H`), captured against a one-time BSS snapshot of the vanilla cast-mode values so cast
    mode is unaffected.

### Resolved 2026-09-03 — "can't research sphere X tier N" is a vanilla UI lock, not a bug

Reported twice (2026-07-18 and 2026-09-03): a tier appeared to be un-clickable until a
*different* tier finished researching. **Root cause, `TSpellBook.FillSlot`, `AoW.exe`
`0x0042EB97`–`0x0042EC0D`:** while any research is in progress (`magic+0x34 ≠ 0`), the book
greys **every** research entry's text (`SetTextColor(0x4C4C4C)` ×4) **and hides its slot button**
(`SetVisible(FALSE)` on `[ebx+0x114]`-family via vtable `+0x6C`) — leaving text that looks present
with nothing clickable behind it. Tier research didn't introduce this; it made it far more
visible, because one entry now stands for a whole tier's worth of spells.

Byte-verified **vanilla**: `0x42EB40`–`0x42EC10` is identical to `Ziggurat upload/AoW.exe` and
between `AoWz.exe`/`AoWzCompat.exe`. Why vanilla does it: `TPlayerMagicControl` has exactly **one**
progress counter (`+0x38`) — no per-spell progress map exists anywhere in the serialization
(`ReadWrite @0x5577C748` only emits ids `0x14` mana / `0x16` researched list / `0x17` current /
`0x18` points) — so `ExecuteResearchSpell` overwrites `+0x38` unconditionally on a switch,
**forfeiting every point accumulated on the abandoned research.** Greying the book makes that
deliberate. A workaround already ships: `CancelResearchBtnClick @0x004311FC` →
`ResearchSpell(0)` clears `+0x34` and un-greys the book instantly — cancel, then pick; the
forfeiture is identical either way, so it's a discoverability problem, not a mechanical one.

**✅ User ruling 2026-09-03: leave it as vanilla. No patch. Do not re-propose this.** If ever
revisited (the user's call): *fully clickable* = **one byte**, `0x0042EB9E` `75`→`EB` (it is a
**short** `jne`, `75 6f` — not the 6-byte near form `dasm.py`'s mnemonic printout might suggest;
byte-check before quoting a size), silently forfeiting progress on every switch. *Greyed but
still clickable* = NOP **10 bytes** `0x0042EBFC`–`0x05`, `33 d2 8b 45 1c 8b 08 ff 51 6c`→`90`×10.
Both exe-only, must move in lockstep across `AoWz.exe`/`AoWzCompat.exe`; neither preserves progress
(that needs a new per-spell field + a ReadWrite tag, a materially bigger feature).

⭐⭐ **Ask this first on any future research complaint — there are THREE cases, not two:**

| symptom | path to audit |
|---|---|
| entry **ABSENT** | the list path — `ListResearchSpells` → `ValidResearchSpell` (picks gate `tier ≤ GetSpherePicks`, the per-sphere ladder, already-researched) → `cave_group`. ⚠ Also check pagination: >6 open tier entries spill to the next spread. |
| entry **PRESENT but GREYED** | the enable path — `FillSlot` `0x42EB97`–`0x42EC0D`. **All-or-nothing**: it greys *every* research entry and hides *every* slot button iff `magic+0x34 ≠ 0`. It can never grey some entries and not others. |
| entry **PRESENT, normal-looking, but the CLICK DOES NOTHING** | the **click path** — see below. This is a *silent* failure with no sound, no dialog and no state change. |

Reading a live save is cheap for the first two: `re_tools/save_research.py` decodes every
player's researched list, current research and points from a `.asg`/`.acg`.

### ⭐ ROOT CAUSE — the slot BUTTONS were never moved with their panels (fixed 2026-09-06)

**Reported as "some sphere researches were selectable and others were not."** A *simultaneous
mix* is the diagnostic fingerprint: it rules out both the greying lock (all-or-nothing) and
`GetBusy` (per-player, kills every click at once). Only per-slot **geometry** can do it.

⚠⚠ **The DFM lies about the hierarchy — measure this, never infer it.** The DFM lists `SxPnl` and
`SxBtn` as *flat siblings of the form* with identical Tops. **At runtime each `SxBtn` is
re-parented to become a CHILD of its own `SxPnl`.** A live dump
(`re_tools/spellbook_geom.py`, written for exactly this) proves it — every button reports
`parent = its own panel`:

```
slot 0  pnl T=27  H=100 TopOff=16    btn T=27  H=100 TopOff=16   parent=THIS-PANEL
slot 1  pnl T=131 H=100 TopOff=120   btn T=131 H=100 TopOff=120  parent=THIS-PANEL
slot 2  pnl T=235 H=100 TopOff=224   btn T=235 H=100 TopOff=224  parent=THIS-PANEL
```

So a button's `Top`/`TopOffset` are **relative to its panel**, and the panel is only **100 px
tall** (`HILITE_H`). The values actually stored there are **page-level Ys** — the vanilla
`30/110/190/270` pitch, or the research `16/120/224/328` pitch. Any row whose value is ≥ the panel
height is clipped entirely outside its parent and can never be hit:

| row | stored TopOffset | vs panel H=100 | result |
|---|---|---|---|
| 0 | 16 (or 30) | inside | **clickable** |
| 1 | 120 (or 110) | outside | dead |
| 2 | 224 (or 190) | outside | dead |

Slots 0 and 4 are row 0 of the left and right page, so exactly two entries survive — reported
first as "some selectable, others not" and then as "only the first row is selectable". Those are
the *same* defect described twice. `cave_layout` never touches `SLOT_BTNS` positions at all
(`_height_stores()` sets their **height** only), so the wrong page-level value simply persists.

⭐ **The hover "bake" is the tell.** An unresponsive entry still lights up and grows progressively
whiter on repeated mouse-over, because the panel *is* under the cursor and the book never repaints
the parchment between paints, so the translucent lit strip accumulates. Glow without response
means the **panel** is live and the **button** is clipped — not that the control is missing.

⚠⚠ **FAILED FIX — do not retry: `btn.Top = pnl.Top`.** It is the obvious move if you trust the
DFM's sibling hierarchy, and it is precisely wrong: it writes a page-level Y into a panel-relative
field. Measured result — identical symptom, row 0 only. The button must be positioned relative to
its **panel**, i.e. `Top = 0`.

**Fixed by `build_tierresearch_btnfix.py`** 🔨 APPLIED, UNTESTED (2026-09-08), `AoWz.exe` +
`AoWzCompat.exe`. 6-byte hook at **`0x0042F2DC`** (`mov esi,eax / dec esi / cmp esi,0`,
`.reloc`-free) → cave at **`0x00611F00`** with a slot table at `0x00611EE0`, both in the `.tres`
section's 288-byte slack. In research modes only, it makes each button exactly fill its own panel
— `Top = 0`, `TopOffset = 0`, `Height = panel height` — then replays the three displaced
instructions (`cmp` **last**, and `jmp` does not touch flags) and returns to `0x0042F2E2`. Zero is
unambiguously right: the button already has `L=0, W=254` inside a `W=262` panel. Cast/info modes
are untouched. `--undo` restores the 6 bytes and zeroes the cave.

⚠⚠ **Do NOT "simplify" this by retargeting the `call cave_layout` at `0x42F2D7`.** That call is
one of `build_tierresearch_exe.py`'s verified HOOKS; retargeting it was tried and reverted,
because the tier script then fails its own "already applied" check and **ABORTS** — and it has no
`--undo`. `0x42F2DC` sits between its two verified sites in this function (`0x42F2D7` and the
`0x42F2F1` nilguard) and is claimed by neither, so **both scripts verify clean**.

⚠ `build_tierresearch_exe.py` cannot re-apply over changed content at all (it aborts on any blob
or hook difference). If it is ever rebuilt, re-run `build_tierresearch_btnfix.py` afterwards.

### ⚠ Two further silent no-ops on the click path (vanilla — not this bug, but real)

Both were found while chasing the above and are genuine silent-failure modes worth knowing.
`ExecuteSpellResearched @0x5577CBF8` zeroes **both** `+0x38` (points) and `+0x34` (current) on
completion, and `cave_grant` calls it first before granting the rest of the tier — so the book is
*not* greyed after a completion, and neither of these explains a per-entry mix.

1. **`TPlayerMagicControl.ResearchSpell @0x5577D588` bails on `TPlayer.GetBusy @0x557516D0`.**
   Busy = the player does not hold the turn-event **token** (`TokenManager` vmt `+0x14`), or
   `player+0x48` busy-lock is set, or it is not their active turn, or the turn timer expired.
   On busy it returns false having done nothing. The exe's click handler tests it —
   `0x004307F4 test al,al / 0x004307F6 je 0x00430925` — and jumps to the handler's exit with **no
   feedback of any kind**. The spellbook never calls `GetBusy` (its only four call sites in
   `AoW.exe` are `0x40A376`, `0x40A755`, `0x4472DB`, `0x452BB0` — none in the book), so the entry
   still looks perfectly selectable. **Research completion is peak token traffic** (it happens
   inside `NewTurn` and fires a `TPlayerMagicEventLog` that is itself distributed as a TE), which
   is why clicking immediately after the "research complete" popup is the reliable repro.
2. **`ExecuteResearchSpell @0x5577D538` returns 0** if the chosen spell is already in the
   researched list. With tier grants adding a whole tier at once, a book populated *before* a
   grant can still offer an entry that is now already researched — clicking it does nothing.

⚠ **A stalled TE pipeline makes case 1 permanent.** Anything that leaves turn processing frozen
(e.g. the Death-altar exception holding `TArmy.IncommingStorm`'s change-notify lock — see the
storm section above) means the token is never released, so research can never be selected again
for the rest of that session. If research selection goes *permanently* dead, suspect a stalled TE,
not the spellbook.

**Left as-is.** The busy gate must stay — it enforces turn/token ordering and bypassing it would
dispatch TEs out of order in multiplayer. If the silence ever needs fixing, the cheap option is to
hook `0x004307F4` so a false return plays the standard denial sample (`Sound.PlaySample` is
already imported and called in this same unit at `0x0042E7D0`) before falling through to
`0x00430925`. Not built — the geometry fix above was the actual defect.

**Pagination is real** (>6 open tier entries page via `cave_group`'s `ceil(R/6)*8` arrangement,
sphere-major Cosmos→Water) — do not mistake a later sphere sitting on page 2 for a missing entry.

### Reusable machinery from this build

- **ILB image edit recipe** (from `build_glowilb.py`): raw 16-bit pixel data can be resized by
  duplicating a middle row N times (keeps soft top/bottom edges), appending the new data at EOF,
  and repointing just that record's `dataoff`/`size`/three `w,h` pairs — every other image's
  offset is untouched. Fits any ILB image edit, not just this one.
- **Blend machinery**: exe imports `GFXE.AlphaBlendTable` @`0x45D6A8` (100 per-percent 5-bit
  LUTs) and `IntensityBlendTable` @`0x45D6A4`; `TLookupBlendTableCollection100.GetLookupTables`
  thunk @`0x4018DC` (eax=collection, edx=pct) → a `TBlendTable`; any `TLibraryImage` then draws
  translucently via `[vmt+0x94]` (eax=img, edx=x, ecx=y, clip-ctx pushed first, table second,
  callee `ret 8`). `TLibraryImage.Show` @`0x5520E468` dispatches on `img+0x38` (0 opaque, 1
  transparent, 2 → jumptable on `img+0x39`: 0 explicit table, 1 Alpha, 3 Intensity, 4 Shadow, 5
  LinearAlpha, percent at `img+0x3C`). `TSprite16.ShowTransparent` is a hardcoded 50% alpha blend.
- **Drawing text from a cave**: `FontModule.Age8 = [[0x45A210]]+0x44`; thunks `SetColor 0x401A84`,
  `SetTextCentered(font,cx,y,[str],[ctx]) 0x401A94` — the idiom is copied from the vanilla
  unit-banner number draw @`0x40D2D8`. String manipulation via imported `@LStrCopy`
  (eax=src, edx=index, ecx=count, [&dest], thunk `0x401148`) into BSS `LStr` scratch slots that
  are **always `LStrClr`'d** first — the leak-free pattern for building strings in a cave.
- **Runtime control layout**: `TAoWComponent.SetWinTop` inlines to `[pnl+0x88]=y; [pnl+0xA4]=0`
  (from `aowInt @0x59802FCC`) — the control's own align pass recomputes children's absolutes from
  that. `Alignment ahTop`'s `TopOffset` lives at `[pnl+0xD4]+0x20`; `ReAlign @0x59803274`
  computes `Y = parent.h × TopOffPct/100 + TopOffset` — write **both** the relative `TopOffset`
  and the absolute position if a future `ReAlign` might fire (first-open races this).
- **⚠ Panel parent-field trap**: a *control*'s parent lives at `+0x10C`, but a **panel** (a
  window-class object) has its parent at `[obj+0xCC]` instead — the same aliasing-by-sibling-class
  hazard the project sees repeatedly; verify the concrete class before trusting an offset.
- **Self-healing layout via a dialog's per-tick update hook**: entry-hook the dialog's own
  `DlgUpdate`/`OnUpdate` method; if a live geometry field doesn't match its expected post-
  population value, re-run the population function. Converges to a no-op check and recovers from
  any future external disturbance (e.g. an unrelated event repainting mid-display) within one
  tick — general-purpose for any dialog whose first-open population races its own layout pass.
- **Slot-arranged nil-padded list compaction**: reshape a vanilla list into fixed-size groups by
  padding with nils and writing the result back into the **same list object** every downstream
  consumer already reads (`page*8+k` indexing, `FillSlot`, `SelectSpellBtnClick`,
  `SpellIconDraw`, paging by `GetCount`) — nil slots become hidden/unclickable panels for free,
  and every one of those call sites needs zero changes. Reusable whenever a UI list needs
  regrouping without touching its consumers.
- **Self-refreshing `TStringList` control**: `Clear` (`vmt+0x40`) then `Add` per line
  (`vmt+0x34`) on a control's own backing `TStringList` (e.g. a memo's `+0x118`) redraws it with
  no extra invalidation call — proven first in the combat-log work, reused here for the research
  memo.

### Behaviour notes / limitations
- `TMagicWin`'s small magic-screen research panel still names the representative spell (a
  separate window, not tier-ified); turn counts are correct everywhere because every display
  reads `magic+0x38`.
- The NewTurn event-log/popup **is** tier-ified (`cave_evtext`, v7.5/v7.6 — see the AS-BUILT DLL
  table and version history above): it names "Death I researched", not the individual spell.
  What's still silent is the *rest* of the tier's members — only the popup's own headline names
  the tier, each additional grant fires no announcement of its own.
- AI research is mechanically unchanged (its weighted single-spell pick just now completes the
  whole tier as a side effect); its internal turns *estimate* still reads the old per-spell cost —
  cosmetic only.
- Tomes still grant a single spell (`TItem.ExecuteUse` path untouched).
- MP: peers need the patched DLL; the exe layer is per-client cosmetic.

---

## Sphere Mastery casting-cost rework

**Status: 🔨 APPLIED, UNTESTED (2026-07-30).** `build_mastery_cost.py` · `AoWEPACK.dpl` ·
backup `AoWEPACK.dpl.pre-masterycost`. (`VA = file_offset + 0x55700C00`.)

| | opposed sphere | same sphere |
|---|---|---|
| vanilla | ×2.00 | ×1.00 (no effect) |
| now | **×1.50** | **×0.75** |

Doubling the opposed sphere is a hard lockout rather than a cost; +50% still stings without being
anti-fun, and the same-sphere discount makes casting a Mastery feel like *your* sphere's mastery
instead of purely a denial tool.

### The mechanic

`TGlobalMagicControl` lives at **`[[0x558FA040]+0x188]`**, holding a per-sphere counter array at
`mc+0x18+sphere*4`. `GetSphereManaDoubled @0x5577E230` is just `counter != 0`;
`Inc/DecDoubleSphereManaCount @0x5577E220`/`0x5577E228` adjust it.

**The discount needs no new state.** The *only* callers of `IncDoubleSphereManaCount` are the six
Mastery enchantments' `Activate` methods, and each flags **its own opposite**:

| Mastery | own sphere | flags |
|---|---|---|
| `TLifeMasteryEnchantment.Activate` @`0x557F2043` | Life (1) | Death (2) |
| `TDeathMasteryEnchantment.Activate` @`0x557F2499` | Death (2) | Life (1) |
| `TEarthMasteryEnchantment.Activate` @`0x557F338B` | Earth (3) | Air (4) |
| `TAirMasteryEnchantment.Activate` @`0x557F03DF` | Air (4) | Earth (3) |
| `TFireMasteryEnchantment.Activate` @`0x557F2BA7` | Fire (5) | Water (6) |
| `TWaterMasteryEnchantment.Activate` @`0x557F08DB` | Water (6) | Fire (5) |

So for a spell of sphere `S`: an opposed Mastery is active ⟺ `doubled[S] != 0` (vanilla's own
test); a Mastery of `S` itself is active ⟺ `doubled[opposite(S)] != 0`, where
`opposite(s) = s+1` if odd else `s-1` (Cosmos 0 has none) — fully derivable from state vanilla
already keeps.

### The chokepoint and the patch

`THero.CastingMana @0x557894EC` (vanilla):
```
557894EC  push ebx ; push esi
557894EE  mov  esi, edx                  ; esi = spell
557894F0  mov  ebx, [esi+0x14]           ; ebx = base cost
557894F3  mov  eax, [0x558FA040]         ; map        <-- the function's ONLY .reloc
557894F8  mov  eax, [eax+0x188]          ; TGlobalMagicControl
557894FE  mov  dl, [esi+0x20]            ; spell sphere
55789501  call GetSphereManaDoubled
55789506  test al,al ; je 0x55789510
5578950A  mov eax,ebx ; add eax,eax ; mov ebx,eax    ; cost *= 2
55789510  mov eax,ebx ; pop esi ; pop ebx ; ret
```
Single chokepoint, **20+ callers** — `CanCastSpell`, `CanCastCombatSpell`, `CastSpell`,
`ExecuteStartCasting`, `CastingTurns`, `TSpell.CombatSpellCast`, `TCombatSpell.CreateCA`,
`TUnitSpellCaster.GetRequiredMana`, every combat-spell `CreateCA` — so one patch covers every
cost preview, AI affordability check and actual charge (unit-casting is covered for free).

**Hook `0x557894F8`** (`mov eax,[eax+0x188]`, 6 B → jmp+1 nop), **cave `0x55812880`** (61 B),
returning to `0x55789510`. Hooked *after*, not at, `0x557894F3` because that instruction carries
the function's only base-relocation — hooking earlier would need a PIC anchor; hooking after
means `eax` already holds the correctly-relocated map pointer, so the cave is register/rel32 only:
```
mov   eax,[eax+0x188]              ; replay displaced -> mc
movzx edx, byte [esi+0x20]         ; S = spell sphere
cmp   [eax+edx*4+0x18], 0
jne   opposed
test  edx, edx                     ; Cosmos has no opposite
jz    done
ecx = (S odd) ? S+1 : S-1          ; opposite(S)
cmp   [eax+ecx*4+0x18], 0
je    done
ebx = ebx*3 >> 2                   ; own Mastery -> x0.75
jmp   done
opposed:
ebx = ebx*3 >> 1                   ; opposed -> x1.50
done: jmp 0x55789510
```
Vanilla's now-unreachable `×2` block (`0x557894FE`–`0x5578950F`) is left in place; `--undo`
restores it.

### Retuning, semantics, revert

Edit the constants and re-run `--apply` (rewrites the cave in place): `OPPOSED_MUL,
OPPOSED_SHIFT = 3, 1` (×1.50), `OWN_MUL, OWN_SHIFT = 3, 2` (×0.75), `ROUND_UP = False`. Any
mul/shift pair works (×1.25=`(5,2)`, ×0.5=`(1,1)`, ×2=`(2,0)`).

- **Precedence:** if a sphere *and* its opposite both have Masteries up, the opposed penalty wins
  (tested first) — the discount is skipped.
- **No compounding:** the engine stores a count but tests `!= 0`, so stacking the same Mastery
  twice does nothing extra, same as vanilla.
- **Rounding** truncates (favours the caster both directions: a 5-mana spell → 7 opposed, 3
  same-sphere). `ROUND_UP=True` biases the other way.
- **Cosmos (0)** is unaffected in both directions.
- **⚠ GLOBAL, not per-caster.** `TGlobalMagicControl` has no owner dimension — this is vanilla's
  own design. Casting Fire Mastery makes fire spells 25% cheaper for **every** wizard on the map,
  not just the caster. Making it caster-only would need new per-player state the engine doesn't
  have — a materially bigger feature.

**In-game checklist (not yet run):** with a Mastery active, compare spellbook costs against base:
(1) an opposed-sphere spell reads **+50%** (12→18), not double; (2) a same-sphere spell reads
**−25%** (12→9); (3) an unrelated sphere and any Cosmos spell are unchanged; (4) the mana actually
charged matches the displayed cost for both a hero cast and a unit-caster cast.

**Revert:** `build_mastery_cost.py --undo` — restores the 6 displaced bytes and zeroes the cave,
touching no backup.

### Coupling — the vanilla instant-cast raw-cost bug

**Vanilla bug, byte-proven against `AoWEPACK_original_backup.dpl`; fixed and confirmed 2026-08-27
by a different feature's script** (`build_caster_cost.py`, full write-up in
`03-abilities-added.md` §6) — not this file's script, but the coupling to Sphere Mastery
is direct and belongs here.

`THero.CastSpell` takes an **instant** branch when `CastingMana(caster,spell) ≤ [hero+0x80]`
(casting points). On that branch, three sites **re-read the cost raw** (`[spell+0x14]`), bypassing
`CastingMana` — and the Mastery multiplier with it — entirely: `TSummonSpell.Activate
@0x557E44F8`, `TGlobalEnchantmentSpell.Activate @0x557EFA7C`, `TSummonSpellTE.Process
@0x557E4353`. All three are byte-identical live vs pristine — original 1999 behaviour. Nothing
rescues it: the sphere penalty is applied *inline inside* `CastingMana` (`call
GetSphereManaDoubled @0x55789501`), and `GetSphereManaDoubled @0x5577E230` has **exactly one
code caller** — that site.

**Why it was never noticed:** `TSpellTE.Validate` re-checks the **raw** cost while `CastSpell`'s
instant-branch test uses whichever cost function actually ran — so the sign of the modifier
decides the symptom:

| | vanilla ×2 penalty | Mastery's ×0.75/×1.50 (before the fix) |
|---|---|---|
| instant branch entered when | `2R ≤ P` | `0.75R ≤ P` (own-sphere case) |
| `Validate` re-check (`R ≤ P`) | implied by `2R ≤ P` — cannot fail | fails when `0.75R ≤ P < R` |
| symptom | pays `R`, not `2R` — penalty silently waived | **spell does nothing at all** |

A penalty makes the gate *stricter* than the re-check, so it degrades gracefully; a discount
loosens the gate *below* the re-check and opens a hard silent-failure band. **⭐ Generalise:
whenever a gate and a later re-check read different versions of the same number, check which
direction the modifier pushes the gate relative to the re-check** — invisible until looked for.

In vanilla only the cheap summons escaped (Boar 9, Black Spider 12, Frog 18) — Syron (240) and
the dragons (120) are too expensive to cast instantly, so they channel through
`ExecuteStartCasting` and were always correctly doubled. **Fixed 2026-08-27** (Sites A/B/C,
`build_caster_cost.py`): instant summons/global enchantments now route through `CastingMana`, so
**Sphere Mastery reaches them for the first time**, and its own silent-fail band closes too — at
casting level 5 this newly scales 9/13 summons and 2/12 global enchantments, and un-breaks 2
summons + 4 global enchantments that previously did nothing when cast at a discount.

**Left unfixed by choice** (`03-abilities-added.md` §6.4): Cosmagic Scrying
(`0x557E85F9`, `.reloc` status flagged unverified there); six Evoker auto-resolve combat spells
(each a one-line raw store); all three strategic AI cast paths (`AIExecuteCastSpellAction` on
`TUnitSpell`/`TSummonSpell`/`TGlobalEnchantmentSpell`) — internally raw-consistent throughout, so
an AI hero never hits the silent-fail band, it just never sees a Mastery discount or penalty.

**⚠ Forward hazard:** `build_caster_cost.py`'s Sites A–C are what makes instantly-cast
summons/global enchantments visible to `build_mastery_cost.py` at all — **undoing Sites A–C
silently re-exempts those spells from the Mastery multiplier**, reverting to the vanilla
silent-waive behaviour above. Not a bug in `build_mastery_cost.py` itself; expensive to re-derive.

---

## Crusade spawn-table rework

**Status: 🔨 APPLIED, UNTESTED (2026-07-29).** `build_crusade_spawns.py` · `AoWEPACK.dpl` ·
backup `AoWEPACK.dpl.pre-crusadespawns`. (`VA = file_offset + 0x55700C00` (CODE); DATA
`off = VA − 0x55701200`.)

> **Not the same defect family as the exploration-site rosters.** Crusade routes every roll
> through `AoWE.TAoWHSMap.Random @0x5577827C`, correctly advancing the map's persistent RNG state
> — two casts genuinely differ. The repetitiveness is **hardcoded table size**, design, not a
> seeding bug. (The seeding-bug family is `10-ai-and-structures.md`, out of scope
> here.)

### The class

`GlobalSpells.TCrusade` — spell id **`0x22`**. `Create @0x557ED148`, `PlaceParty @0x557ED1EC`,
`ExecuteTE @0x557ED340`, `Activate @0x557ED664`. Every summoned unit is granted ability **`0x65`**
(`PassiveAb.TCrusaderAbility`, a `TDurationAbility` — crusaders are temporary). `PlaceParty` only
*places* an already-built army (random hex within radius 20 of the caster, `TArmyHS.PlaceEx`,
behaviour `10`) — it never chooses units.

### Why it felt repetitive — three independent causes (vanilla)

```
roll = Random(100)
if roll < 20:                                   # 20% branch
    1 army, 1 unit, type = TABLE_A[Random(1)]    # Random(1) is a DEAD ROLL — always index 0
else:                                            # 80% branch
    2 armies of Random(3)+4 units, each unit TABLE_B[Random(2)]     # only 2 types, rolled per-unit
    1 army of 2-3 units, all TABLE_C[Random(3)]                     # rolled ONCE -> homogeneous
```
1. The bulk of every cast (8–12 of ~10–15 units) is drawn from `TABLE_B`'s **2 entries**
   (Legionary/Archer).
2. `Random(1)` in the 20% branch can only ever be 0 — that branch is *always* a single Astra.
3. The third army's type is rolled **once, outside** the per-unit loop — always homogeneous
   (2 Valkyries, 2 Avengers, or 3 Paladins, never mixed).

Six contiguous dwords at `0x558E8E98` hold `TABLE_A`(1)/`TABLE_C`(3)/`TABLE_B`(2) — **the tables
overlap in address space by construction**; anything written into that region touches more than
one table. Unit ids resolve against `Unitres.pfs`, which is Ziggurat data — the names below
describe this install, not a generic one.

### The rework

Replaces the entire spawn section with one table-driven cave; reproduces vanilla's per-unit
sequence exactly (`TAbstractUnit.Create` → `GetUnitResource` → `SetUnitResource` → grant `0x65` →
army `+0xAC` → post-init `+0x2C`) and reuses vanilla's own `PlaceParty`. Only *which* units appear
changes.

- **Hook `0x557ED3CC`** (`mov edx,0x64`, the `Random(100)` opening the spawn section), 5 B →
  exact 5-byte `jmp`, no padding. **Resume `0x557ED611`** (the `CastingDone` + SFX tail). The
  581 bytes of vanilla spawn code between are unreachable and left in place.
- **Cave `0x55812500`**, 768 B reserved (82 B data + 353 B code, code entry `0x55812560`).

**Data format** (offsets from cave base): `THRESH[3]` cumulative % thresholds (20, 40, 100);
`LISTOFF[6]`/`LISTLEN[6]` per-pool offset/length; `LISTS[13]` concatenated unit-id bytes;
`OUTCOMES[54]` = 3 outcomes × 3 stacks × 3 entries × (pool, count). A one-element pool is just
"always this unit"; counts of 0 are skipped.

**Pools** (installed Ziggurat unit ids): `a` tier1 `[126 Archer,127 Chanter,129 Legionary,135
Legionary]` · `b` tier2 `[128 Paladin,130 Spirit Puppet,136 Chariot]` · `c` tier3 `[131 Titan,132
Valkyrie,134 Avenger]` · `astra [133]` · `d` catapult `[251]` · `valkyrie [132]`.

**Outcomes:**

| chance | composition |
|---|---|
| 20% | Astra; 8×a; 8×a |
| 20% | 3×Valkyrie; 4b+4a; 4b+4a |
| 60% | 3b+4a+1d; 2c+5b+1d; 1c+3b+4a |

The pool index re-rolls **per unit**, so `8a` is eight units mixed across the four tier-1 types,
the opposite of vanilla's homogeneous third army. ⚠ The 60% branch's last stack was originally
specified as `1c3b5a` (9 units) — exceeds AoW1's 8-unit army cap; trimmed to `1c3b4a` at the
user's instruction. `TArmy.AddUnit @0x5578E86C` has **no explicit capacity check** (delegates to
the unit's own vtable `+8`), so an over-cap stack would most likely lose a unit silently rather
than crash — the build script validates every stack at build time and warns.

**Safety:** `EBX`/`ESI`/`EDI` are pushed by the function prologue and unread by the tail, so the
cave owns them; its own 0x18-byte frame is balanced before the resume jmp; `EBP` untouched
(`[ebp-4]`=Self/spell, `[ebp-8]`=caster, both needed by `PlaceParty`). Every global is reached via
the call/pop rebase-delta idiom (kept in the stack frame because `Random()` clobbers
`EAX/EDX/ECX`); no absolute data reference is emitted. Every roll still goes through
`TAoWHSMap.Random`, so the map RNG state advances correctly and MP peers stay in lockstep.
Verified by an image-wide rel32 scan that nothing outside jumps into the bypassed
`0x557ED3D1..0x557ED610` range (the one scan hit was a data byte whose "target" lands
mid-instruction — a false positive, not a real control-flow edge).

**In-game checklist (not yet run):** cast Crusade several times; expect the 60% outcome to
dominate; confirm tier-1 stacks are visibly mixed (not eight of one type); catapults should
appear in two of the three 60%-branch stacks; the rare Astra outcome should still yield exactly
one Astra; no stack should ever show 9 units.

**Retuning:** edit `SPEC`/`LISTS` at the top of the script, re-run `--apply` (rewrites in place).
**Revert:** `--undo` restores the vanilla 5 bytes and zeroes the cave, touching no backup — the
vanilla spawn tables at `0x558E8E98` and the vanilla spawn code are left in place and are
restored to service.

### Cave-space map for the shared free-CODE region (local excerpt)

Per this project's convention, the canonical project-wide cave-ownership table belongs in
`12-re-toolchain.md` — add to it there when allocating a new cave. This is the slice covering
this file's own four features, in the free CODE run `0x55812219..0x558E7918` (~874 KB); no single
source doc showed all four together, so this excerpt is consolidated here from each script's own
constants:

| range | owner | size |
|---|---|---|
| `0x55812400`–`0x5581247F` | `build_sitedefender_vary.py` (not in this file — AI/sites topic) | 128 B |
| `0x55812500`–`0x558127FF` | `build_crusade_spawns.py` | 768 B reserved (449 B used) |
| `0x55812800`–`0x5581283F` | `build_stormeffectroll.py` | 64 B |
| `0x55812840`–`0x5581287F` | *free* | 64 B |
| `0x55812880`–~`0x558128BD` | `build_mastery_cost.py` | 61 B |

Next free cave in this region: **`0x558128C0`** upward (or the `0x55812840` gap, if small
enough). Different free zone from tier research's `0x5580ED80..0x5580F400`.

---

## Storm & Poison Plant debuff protection — roll vs Resistance

**Status: 🔨 APPLIED, UNTESTED (2026-07-30).** `build_stormeffectroll.py` · `AoWEPACK.dpl` ·
backup `AoWEPACK.dpl.pre-stormeffectroll`.

### The pipeline (per unit)

`TArmy.IncommingStorm(army, stormIdx, caster) @0x557904b4` → for each unit,
`TAbstractUnit.ExecuteStormDamage(unit, stormIdx) @0x55780668` does two separable things:

1. **Base damage** (already respects immunity/protection): builds a damage-type set from
   `StormDamageType[stormIdx]` (`0x558e8330`) and calls `ExecuteDamageRole @0x55781ac4` — 0
   damage if immune (`GetImmunityTypes`, vmt`+0xEC`), half if protected (`GetProtectionTypes`,
   vmt`+0xF0`).
2. **The debuff** — *only if* clamped base damage `> 0`, selects a per-storm effect mask and
   calls **`ExecuteDamageEffects(unit, mask) @0x55781e28`** — the per-unit debuff applier,
   distinct from the terrain change and the raw damage above.

| idx | Storm | base dmg type | effect mask | debuff (ability id) |
|---|---|---|---|---|
| 0 | Blast | `0x200` | — | none |
| 1 | Fire | `0x01` | — | none |
| 2 | **Death** | `0x20` | `0x20` | **Cursed** (`0x5d`) |
| 3 | **Divine** | `0x40` | `0x40` | **Vertigo** (`0x62`) |
| 4 | Ice | `0x02` | — | none |
| 5 | Lightning | `0x04` | — | none |
| 6 | **Pestilence** | `0x10` | `0x10` | **Poisoned** (`0x60`) |

(Terrain bonus: standing on the storm's "on-type" terrain currently ×4 base strength — was ×8
before an earlier patch, live-verified, no `.pre-*` for it — treat `ExecuteStormDamage`'s tail as
already-modded when layering.) The **only** callers of `ExecuteDamageEffects` are
`ExecuteStormDamage` and `PoisonP.TPoisonPlant.TriggerArmyDamage @0x557C41D2` — xref-verified.
⚠ Holy/Unholy Ground's own `TriggerArmyDamage` only ever call `ExecuteDamageRole` for typed
damage; their `0x40`/`0x20` constants are **damage types**, not effect masks — they never apply a
debuff at all, despite an older note in the source material implying the "ground damager" column
meant the debuff applier.

### The vanilla gap this feature closes

`ExecuteDamageEffects @0x55781e28` masks the effect set with `~GetImmunityTypes` but **never
reads `GetProtectionTypes`**:
```
55781e3d  call [edx+0xEC]           ; GetImmunityTypes(unit)
55781e45  not ebx ; and bx,[esp]    ; mask &= ~immunity   <-- respected
55781e56  test bl,0x10 ; ... -> ExpandAbility(0x60) Poisoned
55781e79  test bl,0x20 ; ... -> ExpandAbility(0x5d) Cursed
55781e9c  test bl,0x40 ; ... -> ExpandAbility(0x62) Vertigo
```
**Immunity already fully blocked the debuff, twice over** — 0 base damage means the `dmg>0` guard
never dispatches the effect call at all, and even if it did, `~immunity` clears the bit. **But a
merely-protected unit takes half damage (`>0`) → the debuff dispatches → gets applied at full
strength, because protection is never consulted.** That is the gap.

The richer sibling `ExecuteDamageEffectsRole @0x55781ba4` *does* check protection (per-bit
`GetAbilityEnabled` immunity-ability + `GetProtectionTypes` + a resisted `HitRole`) but only
**rolls** which effects pass — it never applies them — and vanilla calls it **only** from the
tactical-combat path (`TCombatUnit.ExecuteDamageEffectsRole @0x55724c3c`). The strategic-map
storms/plants use the simpler immunity-only function. **The pattern to copy** (from Holy/Unholy
Ground's own damage-gating, which is the same shape as `ExecuteDamageRole`'s own imm/prot check):
alignment/ability-1 blanket gate first, then the type-specific imm/prot check inside the shared
damage function.

Effect-type bits: `0x10` poison, `0x20` death, `0x40` holy (plus `0x01/0x02/0x04` fire/cold/
lightning and `0x80/0x100/0x200` physical/wall/none, unused here). Immunity/Protection ability
ids (from `RegisterPassiveAbilities @0x557bc1cc`): poison `0xa`/`0x49`, death `0xb`/`0x46`, holy
`0xc`/`0x48`. **Vertigo note:** Divine Storm's Vertigo is dispatched through the **holy** bit only
— there is no dedicated vertigo resist; holy immunity/protection is what gates it, thematically
odd but how the engine models it.

### Design considered but not built — hard protection block

An earlier, simpler design (documented, never applied) would have hooked the storm debuff call
site directly (`0x5578080f`, `mov eax,edi; call ExecuteDamageEffects` → cave) and cleared each
unit's *protected* bits out of the effect mask before the call — a **hard, deterministic block**:
protection fully prevents that storm's debuff, base damage unchanged. It was **superseded before
being built** by the roll-vs-Resistance design actually shipped (§ below), which (a) covers
`TPoisonPlant` too by hooking the shared function instead of one call site, and (b) matches how
tactical combat already treats the identical mask — a probabilistic resist via `HitRole`, not a
boolean gate. The hard-block variant remains a valid fallback if probabilistic behaviour is ever
unwanted: hook the same call site, `AND` the mask with `~GetProtectionTypes(unit)` before the
`ExecuteDamageEffects` call — a handful of register-only instructions, trivial to rebuild.

### The shipped fix — roll against Resistance

**Hook `0x55781E28`** (`ExecuteDamageEffects` entry, 8 B `53 56 57 51 66 89 14 24` →
`E9 <rel32> 90 90 90`), **cave `0x55812800`** (27 B, shares the free-CODE region — see the
consolidated cave map in the Crusade section above), resume `0x55781E30`:
```
and  dx, 0x70              ; only poison/death/holy exist here
push eax                   ; preserve Self across the roll
call 0x55781BA4            ; ExecuteDamageEffectsRole(Self, mask) -> AX = survivors
mov  dx, ax
pop  eax
push ebx / esi / edi / ecx ; replay the displaced prologue
mov  word ptr [esp], dx    ; ...with the ROLLED mask
jmp  0x55781E30
```
Chains directly because `ExecuteDamageEffectsRole`'s result bits are the **same bit values** as
its input mask (verified: poison `0x10`, death `0x20`, holy `0x40`, etc.). `and dx,0x70` is the
guarantee that nothing strategic ever receives a combat-only status: `ExecuteDamageEffects`
implements *only* the three branches above, and masking to `0x70` makes that explicit and
caller-independent regardless of what a future caller might pass.

**Effect chance — corrected formula.** `clamp(50 + 5×(strength − effRES), 10, 90)` via
`HitRole @0x55725D98`. Per-type strengths in the rolled path: poison 3, death 4, holy 3 (fire 4,
cold 2, lightning 6 exist in the function but are masked out here). A matching *partial
protection* adds **+2 RES** against that type.

⚠ **This corrects the source investigation, which quotes `50 + 10×(...)`.** That was written
2026-07-30, before the project-wide 5%-scale conversion (`build_hitslope5.py`, applied
2026-08-24) halved every to-hit-family slope in the DLL, `HitRole` included — see the project
rule (`01-combat-maths.md`) that a slope, increment or clamp must be byte-diffed against the
pristine DLL before being quoted, never taken from a decompile or an older doc. Byte-verified:
`0x55725D9D` is vanilla `03 C0` (`add eax,eax`, the doubling) and is live `90 90` (nop'd) — the
same doubling-removal pattern `01-combat-maths.md` documents for `ExecuteDamageRole`.
Worked example with the corrected formula, Death Storm (strength 4): RES 4 → 50%, RES 0 → 70%,
RES 8 → 30%; the 10% floor is reached around RES 11–12 for all three types, and the 90% cap is
**not reachable** at RES ≥ 0 for poison/death/holy (max is 65–70% at RES 0) — the investigation
doc's "RES ≤ 4 → 90% cap / RES ≥ 9 → 10% floor" illustration was computed under the pre-conversion
10pp scale and no longer applies verbatim.

**Correction — `0x55725D9F` provenance.** The same investigation doc separately flags a second
live edit a few bytes later, `lea eax,[eax+eax*4]` → `imul eax,eax,5` at `0x55725D9F`
(`HitRoleProbability+0x05` mirrors it at `0x55725DD1`), as "provenance unknown... an undocumented
hand edit." **That is wrong — it is owned by `build_hitslope5.py`**, which patches the
immediately preceding byte `0x55725D9D` as part of the same 10pp→5pp edit: vanilla computed
`diff×2` (the now-nop'd doubling) then `×5` (the original `lea` idiom) = `×10`; live computes
just `diff` then `×5` (re-encoded as a tunable `imul` imm8, same value, same length) = `×5`. Both
addresses are one coherent edit, not two unrelated ones.

**Consequences (real behaviour changes, intended):** protection now matters (+2 RES against the
matching type, closing the original gap). Divine Storm Vertigo gains the rolled path's extra
`vmt[0x114]() != 2` gate — resolved: `vmt+0x114` = `TUnit.GetUnitType @0x55782808`, reading
`byte[[unit+0x40]+0x30]` = tag `0x15` in `Unitres.pfs` (0 humanoid/racial [96 units], 1
monster/creature [61], 2 machine [23: Battering Ram, Bombard, Catapult, Air Galley, Undead Bone
Ram, …]). `!= 2` means "is not a machine" — machines cannot be given Vertigo under this path,
consistent with the same gate blocking stunned (lightning) and lifesteal healing elsewhere.
Immunity is unchanged (already blocked twice over, see above).

### ⭐⭐ The Death-altar exception was a STALE `.reloc` ENTRY — not this feature, not the combat log

**Root cause, 2026-09-11.** The Death/Divine dispatch rewrite in `ExecuteStormDamage` replaced
vanilla's `mov dx,[0x55780840]` at `0x557807F8` (which carried a base-relocation at RVA `0x807FB`)
with `jmp 0x55780816` + `mov dx,0x20`, and **left the relocation entry in the table**. The Windows
loader therefore added the rebase delta to `0x557807FB`'s dword on every launch — in memory only —
smashing `0x557807FD/FE`, i.e. the `mov dx,0x20` that is the **Death** arm. Divine (`0x55780802`)
lies past the relocated dword and Pestilence (`0x55780808`) keeps its own valid entry, which is
exactly why only the Death Altar faulted. `EExternalException … at 000807FE / 80000003` decodes as
"the second corrupted byte became an `int 3`". Fixed by `build_relocfix.py` (entry type `3 → 0`);
full decode, the six other stale entries it found, and the standing `--audit` are in
`12-re-toolchain.md` §5.2c / §6.5a.

⚠⚠ **Nothing below this line was the cause.** The two paragraphs that follow record real, separate
defects that were fixed on the way; neither is known to have changed anything the player could see.

**Cross-feature interaction — the combat-log emitter ran off the tactical path.**
`build_effectroll.py` repointed all
six of `HitRole`'s call sites **inside** `ExecuteDamageEffectsRole` to combat-log stubs that call
`HitRole` and then run the shared emitter @`0x5580F605`, so storm/plant rolls now run those stubs
too. The emitter's `'CLG1'` magic guard is **NOT** a "combat is happening" gate — the `.clog`
section carries that magic permanently, so the guard passes on the strategic map, and the emitter
(Delphi string allocations + ring writes) ran for every Death/Divine/Pestilence storm and every
auto-resolve.
**`build_effectroll_tacticalgate.py` (🔨 APPLIED, UNTESTED 2026-09-06)** hooks the emitter entry and
requires `RING_TACTICAL` (`0x60D00C`) `== 1` (set only while the tactical combat map is active), so
off the tactical path the effect still lands/resists exactly as before but nothing is emitted; in
live tactical combat the log is unchanged. Cave `0x55810500`; SizeOfImage guard runs first so the
`0x60D00C` read is never reached in `AoWDevEd`. `--undo` restores the 5 displaced bytes and zeroes
the cave.

**PIC/safety:** no absolute data references — rel32 call/jmp and register ops only, rebase-safe
with no load-delta anchor needed. No recursion (`ExecuteDamageEffectsRole` never calls
`ExecuteDamageEffects`). Tactical combat is completely untouched — it reaches the Role function
directly via combat vmt `+0x118`, never through the hooked entry point.

**In-game checklist (not yet run):** cast Pestilence / Death Storm / Divine Storm on a stack with
mixed Resistance — high-RES units should still take damage but frequently shrug off the debuff;
low-RES units should usually still get it. Verify a Poison Plant behaves the same. Confirm no
unit ever comes out frozen/burning/stunned from a strategic-map source (should be structurally
impossible per the `and dx,0x70` mask).

**Revert:** `build_stormeffectroll.py --undo` — restores the 8-byte prologue and zeroes the cave,
touching no backup.

### ⚠ Open item — which RNG generator this cave actually draws from

This project's standing rule is that a cave draws from the generator its **host function**
already uses, and that replicated game state (damage, status effects) should be SYNCED while
tactical-combat rolls are correctly RAW — `HitRole` itself is a vanilla **RAW** drawer, and that
is correct *inside combat*, because `TCombat.Execute` re-anchors `System.RandSeed` from one
synced draw at the top of every battle before running the fight deterministically off raw draws.

This feature's cave calls straight into `ExecuteDamageEffectsRole` (→ `HitRole`, RAW) from
**`ExecuteStormDamage`/`TriggerArmyDamage` on the strategic map** — outside any combat
re-anchor, and with **no reseed bridge** of the kind `build_arena.py` uses before calling
`GenerateItem` (`System.RandSeed := TAoWHSMap.Random(map,$FFFFFF)` immediately before a RAW-
drawing engine call). Live client-side rendering callbacks (`*.Show`, `*.NewFrame`, …) are
documented in `12-re-toolchain.md` (the RNG rule's full derivation — see also its condensed
form in this project's `CLAUDE.md` and `01-combat-maths.md`'s "Two RNGs" summary) as **also**
drawing RAW, at rates that differ per peer — which is presumably exactly why combat needs its own
re-anchor in the first place. Whether that contamination can reach `System.RandSeed` between the
last synced draw and a NewTurn storm-damage roll is not established either way in the source
material.

`12-re-toolchain.md`'s own RNG-site audit table lists "storm effect roll" among 13 sites
"already SYNC" — but unlike every neighbouring row in that table, it gives no per-site VA or
reasoning for that classification, and that same document states explicitly that its audit tool
**cannot see** a cave that reaches the RNG only through a caller like `HitRole` (the identical
structural situation is flagged, in that same document, as an open, untested MP-safety question
for `build_minddecay_oos.py`). Reading the actual live script confirms no reseed bridge is present.

**This is flagged, not fixed — do not invent an answer.** The concrete check that would settle
it: an actual multiplayer session, casting these storms/the poison plant repeatedly across
several turns, watching for the out-of-sync dialog firing later on an unrelated synced draw (the
documented symptom of a silent raw-stream drift). If it turns out to be a real problem, the fix
is the same one-line bridge `build_arena.py` already uses, inserted immediately before the
`call 0x55781BA4` in this cave.

---

## Animate Dead — permanent undead (undocumented pre-convention change)

**Status: 🔨 APPLIED, UNTESTED (recorded 2026-09-04)** — the change is already in the live
`AoWEPACK.dpl` and predates the recording convention. **No owning build script, no `--undo`, no
prior notes entry.** Found while investigating a freeze Inioch reported in his own build. Whether it
has ever been exercised in play is unknown, so the checklist below stands. Same class as the
`0x5580C240` Marksmanship cave (see the cave table in `12-re-toolchain.md`): an author hand-edit,
not corruption — **ask the author rather than reverse-engineering intent.**

### What the live DLL does

`CombatSpells.TAnimateDeadCA.Execute @0x557FA2F4` differs from the pristine backup in exactly two
places. `CombatSpells.TRecallSpiritCA.Execute @0x557FA0D4` is **byte-identical vanilla** and still
raises battle-only spirits (it keeps its two `0x82` grants at `0x557FA126` / `0x557FA149`).

| VA | pristine | live | effect |
|---|---|---|---|
| `0x557FA346` | `ba c9 00 00 00 e8 00 ad f8 ff` — `mov edx,0xC9; call GetUnitResource` | `e8 45 1f 01 00` + 5×`90` | unit type chosen by a cave instead of hard-coded 201 |
| `0x557FA369` | `ba 82 00 00 00 8b c3 8b 08 ff 91 94 00 00 00` (15 B) — grant ability `0x82` | 15×`90` | **the raised unit no longer gets "Combat Resurrected"** |

Cave `0x5580C290`, 31 bytes:

```
push eax / mov eax,esi / shr eax,4 / and al,3 / cmp al,3 / pop eax
je   -> mov edx,0xC6          ; 198 Archer Undead
else    mov edx,0xC9          ; 201 Swordsman Undead
call AoWE.TUnitResourceList.GetUnitResource @0x55785050 / ret
```

### Why removing `0x82` is what makes them permanent

Ability `0x82` is **"Combat Resurrected"**. `AoWE.TCombatUnit.Finalize @0x55724D44` is the point at
which a combat unit either dies or becomes a strategic unit:

```
if (dead) || unit.Has(0x82) || unit.Has(0x83):   destroy the combat unit; RETURN
if (mode == 2):                                  TAbstractUnit.Place(unit, x, y, 1, player, level)
```

`0x82` means *do not promote this unit to the strategic map*. With the grant nop-ed, the raise falls
through to the ordinary survivor branch and is `Place`d — the same call the vanilla summon path
uses — so it becomes a properly registered strategic unit with a real id and the normal
lifecycle. This is a clean way to do it, not a special case.

**No `Summoned` (`0x9B`) enchantment is attached.** Those two deltas are the only changes in the
function, no build script touches `TSummonedAbility`, and `TSummonedAbility.Remove @0x557BB210`
byte-diffs identical to pristine. A Ziggurat-animated undead is therefore a **free, permanent,
upkeep-less ordinary unit**: no mana cost, no dispel-kill, and it goes independent with the rest of
the army when its owner is defeated.

### ⚠⚠ THE DANGER — never attach a persistent enchantment to these units

**Giving these permanent undead a player-registered enchantment — Summoned plus upkeep, the
obvious "make them cost something" change — buys a hard lock at game over.**

Inioch hit exactly this in his own build (changelog 2026-09-04): *"The game froze (hard lock, both
tactical and auto combat) when a player was defeated while still owning a unit spawned by Recall
Spirits or Animate Dead in an earlier combat ... the Summoned effect ... was not linked to its unit,
so the engine could never finish removing the defeated player's enchantments."*

The mechanism, verified against our own live and pristine bytes — **all four functions are
byte-identical vanilla in the live DLL, so this is a vanilla defect, not one of ours**:

```
TPlayer.SetGameOverStatus @0x55751848              ; player status 2 = defeated
  |- TPlayerMagicControl.RemoveEnchantments @0x5577CB9C
        while (list.Count != 0)                    <- no index walk, no return-value check
            ExecuteDispelEnchantment(self, Count-1)     @0x5577D43C
              |- ench->vmt[0x68] = TUnitEnchantment.Dispel @0x55765E14
                     unit = TUnitControl.FindUnit(map[+0xFC], ench[+0x18])
                     if unit == NULL: return 0     <- nothing removed, Count never drops
```

`TUnitEnchantmentAbility.Expand @0x55765894` copies the id verbatim (`ench[+0x18] = unit[+0x18]`),
and `TAbstractUnit.Create` initialises `+0x18` to −1 — an id is only ever assigned by
`TUnitControl.RegisterUnit`, whose sole caller is `TAbstractUnit.Activate`. So an enchantment whose
unit is not resolvable spins that loop forever.

**The invariant, stated so it is not lost again:**

> Removal from the **unit side** (`RemoveAbility`, VMT `+0x98`) is **id-independent** and always
> works. Removal from the **player-list side** (`Dispel` -> `FindUnit`) needs a **resolvable id**.
> An orphan forms only when a *persistent* enchantment's unit-side removal never happens.

Combat-scoped enchantments are safe automatically, which is why Slow has never frozen a game:
`PassiveAb.TSlowEnchantmentAbility.CombatDone @0x557B9F24` (VMT `+0xFC`) does
`combatUnit.GetAbilityOwner().RemoveAbility(self[+0x0C])` at the end of every battle, reaching the
unit through the **combat object**, never through `FindUnit`. Embrittled `0xB2` is a second instance
of that same class (`build_embrittle.py`), so it inherits the identical id-driven cleanup. A
*persistent* enchantment gets neither `CombatDone` nor necessarily
`TAbstractUnit.Deactivate @0x5577FC20` — the other paired unregistration, which calls
`TUnitControl.UnRegisterUnit` **and** `TAbstractUnit.UnregisterEnchantments` together.

**If these undead are ever given an upkeep**, register the enchantment **after**
`TCombatUnit.Finalize` has `Place`d the unit, mirroring
`SummonSpells.TSummonSpellTE.Process @0x557E4353` — which calls `Place` first, checks the result
is non-nil, and only then does `SetUpkeep`/`SetSource`, discarding the unit outright if placement
failed. Inioch's fix is the same shape: link the effect when the unit joins the army, repair
affected saves on load, and add a backstop that drops any enchantment it cannot dispel instead of
spinning.

⚠ Related non-termination in the same file, unfixed and unreached:
`TPlayerMagicControl.OutOfMana @0x5577CA34` loops `while (deficit > 0 && Count != 0)`, picking the
**cheapest** enchantment and subtracting its upkeep. A zero-upkeep entry that also fails to dispel
makes no progress on either term.

### ⚠ Second hazard — the unit-type selector reads a POINTER, not a field

The cave's selector is `mov eax,esi / shr eax,4 / and al,3`, and `esi` at the call site is the
**target combat object's pointer** (set at `0x557FA32A` from `TCombatData.FindID`), not a field of
it — there is no dereference. So Archer-vs-Swordsman is decided by bits 4–5 of a heap
address.

Two readings, both worth resolving with the author:

- **a missing dereference** — the intent was presumably `mov eax,[esi+X]`, keying the raise off
  the corpse's own type or race (a dead archer raises an undead archer);
- **a deliberate ~25 % roll** — in which case it draws from neither of the project's two
  generators.

Either way it is **not reproducible and not replicated**: heap layout differs per process, so two
multiplayer peers can raise different undead from the same corpse. Per `12-re-toolchain.md`, a roll
whose subject is replicated game state must use the SYNCED generator; this uses neither. Not a
single-player correctness bug, so it is recorded rather than patched.

### Balance note

Permanent undead currently cost **nothing** — no gold, no mana upkeep. Inioch's equivalent
charges 2–15 mana/turn by unit type. Whether free permanent raises are intended is an open
design decision, not a defect.

### In-game checklist — outstanding

1. Cast Animate Dead in a tactical battle; confirm the raised undead **survives** the battle and
   appears on the strategic map afterwards.
2. Confirm it costs **no** mana upkeep on the magic panel.
3. Raise several; confirm both Swordsman Undead and Archer Undead occur, and note whether the mix
   looks random or effectively fixed — evidence for the selector reading above.
4. Cast **Recall Spirits**; confirm its spirit still **vanishes** at the end of the battle (it must
   — its `0x82` grants are untouched).
5. ⭐ Get the owning player defeated (leader killed) while holding permanent undead; confirm the
   game **does not freeze** and the undead go independent with the rest of the armies.
6. Cast Dispel Magic on a permanent undead; confirm nothing is stripped and it is **not** instantly
   killed — it carries no `Summoned`, so the dispel-kill branch must not fire.

---

## Spell registration mechanics & the ID budget

Reference material, not a feature — every spell mod (existing or new) depends on it. The
new-spell **creation recipe** (difficulty tiers, the companion-DLL option, ability registration)
belongs to `05-spells-added.md`/`03-abilities-added.md` and is not repeated here.

### How the registry works

Every spell is a **singleton object** in a global registry, `TSpellControl` at `AoWHSSet+0x84`.
Registration happens at **package init, at DLL load** — before any `.pfs` load — via per-unit
functions like `CitySpells.RegisterCitySpells @0x557B25EC`, reached from `AoWEReg.AoWEReg`. Each
registers its turn-event classes (`Engine.TEngine.RegisterEClasses`, the save/network
class-identity registry) then constructs the spell and calls `TSpellControl.RegisterSpell
@0x55779B40`: the spell's **own constructor** sets its ID at `spell+0x10` (not auto-assigned);
the registry is a `TList` indexed by ID that **grows on demand** (no fixed capacity), raising
"Spell already registered (n)" on collision; it also links the spell's graphics
(`TImageSequenceList.LinkToIL(spell+0x2C)`).

`TSpell.Create @0x55779178` sets up the fields already tabulated under "Vanilla mechanics" above
(`+0x10` ID … `+0x30` AI weight), plus three more: `+0x8` name (AnsiString), `+0xC` default byte,
`+0x1C` casting-point cost, `+0x24` description `TStringList`, `+0x28` `TSFXLibrary` node, `+0x2C`
`TImageSequenceList` (icons/animation — the field `RegisterSpell` links via `LinkToIL`, above). A
concrete spell is tiny — `CitySpells.TAnarchy.Create
@0x557B1EF8` in full is: inherited create, `name := Translate(LoadResString(...))`, `ID := 0x48`,
one payload byte. All heavy machinery (targeting UI, TE creation/validation, network sync,
animation, casting economics) lives in shared base classes.

**Everything downstream is registry-driven.** Research candidates
(`ListResearchSpells`/`ValidResearchSpell`), spellbooks (`ListSpells`), casting, saves and MP all
filter the registry by ID + metadata. A registered spell with valid metadata propagates into
research, the spellbook UI and multiplayer automatically — no UI patches needed for a simple
clone (unlike the unit-spellcasting feature, whose difficulty was entirely in gates/UI).

### The vanilla spell-ID map (measured 2026-07-30)

**Ids 1–78 = strategic spells** (11 registration units); **ids 100–130 = the CombatSpells unit**;
**109 is the only hole**. Total 108, reconciled three independent ways: 108 `RegisterSpell` call
sites, 108 ctor-sweep ids, 108 `Spells.pfs` records.

**No serialization-width ceiling**: every serialized spell-id reference is 32-bit — the researched list
(`TPlayerMagicControl+0x30`, tag `0x16`, via `TIntegerList.SaveToStream`), current research
(`+0x34`, tag `0x17`), the research/mana TE wire format (`TChangePlayerMagicTE+0x14`, tag `0x16`),
Tome items (`TItem+0x38`, tag `0x14`), hero cast state (`THero+0x84/0x88/0x8C/0x90`), and the
`.pfs` record key itself (= spell id + 10, directory supports wide u32 keys).

### ⭐ The real constraint — `AoWTC.SpellTypes`, byte[0..130] in `AoWTCPCK.dpl`

`AoWTC.SpellTypes @0x4672F4` (AoWTCPCK.dpl DATA, exported; `AoW.exe` imports it at IAT slot
`0x45EBEC`) is a **132-byte** table declared range `[0,130]` (Delphi bound-check pairs
@`0x4180E8`/`0x41B034`; byte 131 is padding). `SpellTypes[id]` = the spell's tactical-combat
class (0 = not castable in combat). Consumers: the exe research-book filter @`0x42F304` (inside
the population function whose neighbouring `id` compare @`0x42F2F1` now hosts tier research's
nilguard cave) drops `id≥100` spells whose byte is 0 from the research list — **this read has no
bound check**, so an id ≥ 131 reads whatever data follows the table; the combat AI
(`TCAI.CheckUnit`, four `EvalBattle` sites, `EvalPath`) and combat targeting/path UI all key off
the same byte. `AoWDevEd.exe` does **not** import it — editor listing is unaffected.

**Consequences — the spell-id budget: 22 safe new ids, 79–99 and 109.** Strategic-only spells:
use 79–99 (byte stays 0, ids <100 never hit the research filter). Combat-castable spells: any of
the 22, with the `SpellTypes` byte set to a donor spell's class value — a one-byte file patch in
`AoWTCPCK.dpl` DATA, own-module data, no reloc concerns. Reserve **109** for a combat-capable
spell specifically (as an id ≥100 it's dropped from research while its byte is 0, and a nonzero
byte implies a tactical class). **Any new spell id ≥ 100 must get a non-zero `SpellTypes[id]`
byte or it silently vanishes from the spellbook** — the build rule for every new-spell script.

⚠ **131 is a genuine wall, and widening it is worse than hitting it.** The table is sized to
exactly 131 bytes and the next byte is live data (`AoWTC.BreathHit @0x467378`, then
`BreathDir @0x4673A8`). Raising the nine `[0..130]` bound pairs converts a loud `ERangeError`
into a **silent read of the breath tables**, and writing a `SpellTypes` byte past 130 corrupts
them. Relocating the table properly means repointing **12 CODE disp32 refs**, the DATA pointer
`0x004693F8`, **nine bound-check pairs**, and the export RVA (the exe's IAT slot re-binds by name
automatically) — unnecessary until more than 22 new spells exist. **A worked template for exactly
this relocation already exists**: `build_abiltypes_relocate.py` moved the analogous ability table
(`AbilTypes`) to a new 256-entry buffer, repointing 13 references and 9 bound pairs — see
`03-abilities-added.md`. The same recipe (relocate → repoint disp32 refs → repoint bound pairs →
repoint export RVA) applies to `SpellTypes`, scaled to its 12 refs / 2 bound pairs.

### `Spells.pfs` record anatomy — why data-side edits reach further than expected

`TSpellControl.ReadWrite @0x55779A6C` streams every non-nil registered spell under **property
tag = spell id + 10**. `TSpell.ReadWrite @0x55779234`'s tag map:

| Tag | Field | Meaning |
|---|---|---|
| `0xA` | `+0x24` | description (spellbook memo text) |
| `0xB` | `+0x28` | SFX library node |
| `0xC` | `+0x2C` | icon/animation (sequence 10 = book icon) |
| `0xD` | `+0x14` | mana cost |
| `0xE` | `+0x1C` | casting-point cost |
| `0xF` | `+0x18` | research cost |
| `0x10` | `+0x20` | sphere (1-byte blob) |
| `0x11` | `+0x21` | research tier (0 = not researchable) |

So **cost, sphere, tier, description, sounds and icons are all data-side** — icons are a
spell-only concern (abilities never have icons; text-only ability rendering is normal AoW1
behaviour). **Not** in the record — must be set by the constructor/init cave: name `+0x8`, id
`+0x10`, category `+0x22` (base-class-determined), AI research weight `+0x30`. Because the
`ReadWrite` is symmetric, saving the development set from the editor writes a record for every
registered spell for free.

## Speculative: three unbuilt spellcasting extensions

**Status: SPECULATIVE — investigation only, nothing patched, no `--apply` run.** Extensions to
the (separately confirmed) unit-hero spellcasting mod in `06-unit-spellcasting.md`; builds on that
feature's cluster layout (`unit+0x7C..+0x93`) and the exe's `cave_bookfilter`, not reproduced here.

Shared primitives: `TUnit` `+0x18` unit id, `+0x24` owner, `+0x3d` current MV (byte), `+0x3e`
current HP (signed byte), `+0x40` `TUnitResource*`. `TUnitResource` (`unit+0x40`): `+0x04`
resource list (`list.vtable[0x84]()` = the **stable** per-species `UnitResourceIndex`, e.g. 226
Fire Elemental — the canonical species key, works identically from DLL or exe), `+0x2f` unit
level, `+0x30` unit type, `+0x44` base transport capacity. Vtable `+0xa0` `GetUnitLevel`, `+0xD0`
`GetMaxHP`, `+0xE4` `SetHitPoints`, `+0x144`/`+0x148` ability level/enabled.

### 1 — Per-unit intrinsic spellbook (cast regardless of research)

**Verdict: feasible but hard, 72%.** One non-trivial engineering problem (inserting into the
exe's spell list) plus a new data table, no fundamental blocker. **Key enabler:**
`THero.CanCastSpell @0x55789710` has **no "is this researched?" check at all** (only
not-already-casting, mana, `CanActivate`) — research gates only the *book*
(`TPlayerMagicControl.ListSpells @0x5577d148`, iterating `magic+0x30`), not casting. So a spell
made to *appear* will simply work, subject only to mana, target validity and the mod's own M2
tier gate (`level ≥ spell+0x21` @`0x5578974D`).

No per-unit spell field exists on `TUnitResource` — needs a new `{UnitResourceIndex → spellID
list}` table, looked up in an extended `cave_bookfilter` (it already has the caster, runs after
`ListSpells`). **The crux:** `AoW.exe` imports `TSpellList.GetCount/GetSpell/Clear/Delete/
Create/SortOnLevel` but **not `Add`**. Cleanest route: manual `TList` append in the cave when
`count < capacity` (Delphi over-allocates, usually true right after `ListSpells`) — accept
"hidden when exactly full" as a low-risk MVP; escalate to calling the DLL's own `TSpellList.Add
@0x5577a03c` via the rebase-delta trick (no import-table surgery) if that edge case matters.

**Risks:** the M2 gate still blocks an intrinsic spell above the caster's level; **the combat
book is not a separate form** — `TSpellBook`'s mode byte (`+0x222`) shares the same five
`ListSpells` sites, so `cave_bookfilter` already covers strategic *and* combat automatically; the
AI lists via `ListSpells` directly and won't see exe-side additions; the unit still needs the
Spellcasting ability itself (this augments a caster, doesn't create one).

### 2 — HP or MV cost for casting

**Verdict: 85% "in addition to" points, 60% "instead of."** Deduction sites: instant cast →
`THero.CastingDone @0x557893e8` (`SetMana(mana-cost); unit+0x80 -= cost`); multi-turn →
`ExecuteStartCasting @0x55789130`. HP (`unit+0x3e`, signed byte) must go through **`SetHitPoints`**
(vtable `+0xE4` — clamps `[0,GetMaxHP]`, recomputes defensive strength; never write it raw; gate
so `HP-cost ≥ 1` or accept 0-HP as "can't afford"). MV (`unit+0x3d`, byte) has no clamping
accessor — a guarded `sub` is fine.

**Recommended:** one cave after `CastingDone`'s existing deduction (mirrored in
`ExecuteStartCasting` for multi-turn, or accept "multi-turn charges points only"); gate to
units-only via `IsClass`, or apply uniformly by design choice. **"Instead of points" is harder**
— points also *gate* affordability (the instant-vs-multi-turn choice, `CanCastSpellInstantly`) at
several sites, multi-site and easy to desync from the display if redirected. Recommend "in
addition" (points stay the throttle).

### 3 — Enchantment cost/upkeep scaled by target attribute

**Verdict: upkeep 85%; cast-cost 55% (combat path needs more RE); SIZE is a dead axis** —
`GetUnitSize @0x5577f184` returns the constant **1** for every unit. Use **LEVEL**
(`vtable+0xa0` = `resource+0x2f`) — the proven template is
`TSummonedAbility.GetDefaultManaUpkeep @0x557bb1b8` = `(level+1)*2`; transport capacity is a
usable but niche second axis.

**Upkeep:** `TUnitEnchantmentAbility.Expand @0x55765894` creates the `TUnitEnchantment`
(`ench+0x18`=unit id, `+0x1c`=ability id); `TEnchantment.Create @0x5577beac` defaults
**`ench+0x10 = 1`** (the upkeep field, via `SetUpkeep @0x5577c10c`, which fires
`PlayerMagicControl.Update`); player-wide total `GetManaUpkeep @0x5577c964` sums `ench+0x10`
across `magic+0x3c` plus global enchantments. **Proposed:** a cave at the tail of `Expand`
computing `upkeep = base × f(level)` and calling `SetUpkeep` — scoped to unit enchantments only
by construction (it's `TUnitEnchantmentAbility`-specific).

**Cast-cost:** `CastingMana(spell)` never sees the target, but `TUnitSpellTE.Process
@0x5577ab24` has it in hand right before `CastingDone` — reachable **for strategic unit-target
spells only**; combat unit-enchants route through the untraced `TCombatSpellCaster` (Needs-more-RE).

**Risks:** confirm no shipped enchantment already overrides the default upkeep of 1 before
multiplying; store the *computed* upkeep on save rather than re-deriving it at load.

| Feature | Verdict | Confidence | Cleanest hook |
|---|---|---|---|
| 1 Per-unit spellbook | Feasible/Hard | 72% | extend exe `cave_bookfilter` @`0x60C0A8` + a species→spell table |
| 2 HP/MV cost | Feasible("+")/Harder("instead") | 85%/60% | cave after `THero.CastingDone @0x557893e8` (+ `ExecuteStartCasting @0x55789130`) |
| 3 Enchant upkeep/cost by attribute | Upkeep feasible; cast-cost harder | 85%/55% | upkeep: tail of `TUnitEnchantmentAbility.Expand @0x55765894` |

---

## Astral Ward (ex Spell Ward) — rescoped to Town Gate and Warp Party only

**✅ CONFIRMED WORKING (2026-09-07)** — rescope tested in-game by the user. **Renamed Spell Ward →
Astral Ward the same day** via `build_resstr_names.py` (NATIVE `Spell Ward`, `ResStr.txt:8764`);
the refusal text and the `.pfs` description were re-tuned to the new name in step, and the
rename itself is untested. The class, enchantment type code and spell id are unchanged; every
address below still applies. Owner: `build_scripts/build_spellward_rescope.py`.
Target: **`AoWEPACK.dpl` only** — `TSpell.CanActivate` is reached solely through the spell VMT
inside the DLL, and the exe's imported `THero.CastSpell` re-runs `CanActivate` at execution, so
the offer gate and the execution gate are the same function. No exe patch, so no
`AoWz.exe`/`AoWzCompat.exe` lockstep concern.

### Vanilla mechanism

`TGlobalMagicControl` hangs off `[AoWHSMap + 0x188]`; `+0x10` is a **byte set of the
global-enchantment type codes currently active**, rebuilt by
`TGlobalMagicControl.UpdateActiveEnchantments @0x5577E46C`. `TSpellWardEnchantment.Create
@0x557F374C` declares type 6, so an active ward sets bit `0x40`.

Exactly **three** sites read that bit (byte pattern `F6 4x 10 40` across the module), and all
three were byte-identical to `AoWEPACK_original_backup.dpl` before this patch:

| # | site | function | role |
|---|---|---|---|
| 1 | `0x557792F9` | `AoWE.TSpell.CanActivate @0x557792D0` | master gate |
| 2 | `0x557EF97E` | `TGlobalEnchantmentSpell.CanActivate @0x557EF938` | redundant re-check |
| 3 | `0x557EBAFA` | `TDisjunctionSpellCaster.CanCast @0x557EBA94` | Disjunction gate |

The master gate opened with `cmp byte ptr [eax+0x22], 2` / `jne 0x55779329` — **category 2 is
*any* strategic-map spell** (24 constructors set it), so vanilla's ward blocked summons, storms,
city spells, global enchantments and Disjunction alike.

### The patch — one hook, two immediates

**Site 1** `0x557792E8`, 6 bytes, reloc-free: `80 78 22 02 75 3B` → `E9 13 DD 0C 00 90`.
The two `.reloc` entries in this function (`0x557792EF` = the `AoWHSMap` operand, `0x55779303` =
the refusal-string operand) sit **outside** the displaced window and do not move.

**`cave_spellward @ 0x55847000`, 22 bytes**, PIC (rel32 and register operands only):

```
55847000  83 78 10 22     cmp dword ptr [eax+0x10], 0x22   ; Warp Party
55847004  74 06           je  0x5584700C
55847006  83 78 10 26     cmp dword ptr [eax+0x10], 0x26   ; Town Gate
5584700A  75 05           jne 0x55847011
5584700C  E9 DD 22 F3 FF  jmp 0x557792EE   ; WARDED -> the host's AoWHSMap load, unchanged
55847011  E9 13 23 F3 FF  jmp 0x55779329   ; ALLOW  -> the host's own `mov bl,1`
```

`EAX` is the `TSpell*` self pointer (the displaced `cmp byte ptr [eax+0x22],2` proves it). The
spell id is a **dword** at `[spell+0x10]`, written by each constructor as a code constant —
`TWarpParty.Create @0x557EB0A0` writes `0x22` at `0x557EB0F3`, `TTownGate.Create @0x557B0BAC`
writes `0x26` at `0x557B0BFF`. Both immediates are asserted live by the script, not assumed.
Neither exit needs `EAX` preserved: `0x557792EE` reloads it from the global and `0x55779329` is
`mov bl,1`. The category test is dropped outright — the two ids are unique in the spell table, so
an id match already implies the strategic spell.

**Site 2** `0x557EF981`: `40` → `00`, the mask immediate of `test byte ptr [eax+0x10],0x40`
@`0x557EF97E`. Its `jne 0x557EF9C4` (the deny arm) is then never taken.

**Site 3** `0x557EBAFD`: `40` → `00`, same shape at `0x557EBAFA`; its `je 0x557EBB11` is then
**always** taken, skipping the "is the selected enchantment the ward itself" special case, so
Disjunction works on every global enchantment including the Astral Ward.

Zeroing the mask rather than NOP-ing the branch keeps instruction lengths identical, leaves the
neighbouring `.reloc` entries untouched, and makes `--undo` a one-byte write per site.

**Full-file diff vs the pre-apply snapshot: exactly 8 bytes plus one contiguous 22-byte cave
block** — `0x557792E8` (6), `0x557EBAFD` (1), `0x557EF981` (1), `0x55847000` (22).
`--undo --apply` then `--apply` round-trips SHA-256 exact in both directions.

### Deliberately not done

- **`TSpellTE.Validate`** — the mid-targeting window in which a spell is committed before the
  ward goes up — is **not** gated. User ruling 2026-09-06: leave it open.
- **Mana cost and upkeep are unchanged** (100 / 10 — the live `Spells.pfs` record 75 tags
  `0x0D`/`0x0E`; the `.pfs` overrides the code constant at `[spell+0x30]`). User ruling 2026-09-06.
- **AI**: both spells' VMT `+0x5C` `AIPrefetchCastSpellActions` is the `TSpell` stub
  `0x55779824` (a bare `ret`), so no AI player ever queues Town Gate or Warp Party. Nothing to do.
- **RNG**: no path here draws from either generator; `rng_audit.py --owners` gains no site.
- `Dict/ResStr` row "Cannot dispel when Spell Ward is active" (`ResStr.txt:2175`) is left in
  place — site 3 makes it unreachable, and a dead string costs nothing. The `Dict/Release.mld`
  row keyed on the old English description (`Release.txt:4242`) is orphaned by the `.pfs` edit;
  harmless, do not chase it.

### Text, in three other scripts

| what | where | value |
|---|---|---|
| spell name | `build_resstr_names.py` — NATIVE key `Spell Ward` (`ResStr.txt:8764`) | `[US]` = "Astral Ward" |
| refusal message | `build_resstr_names.py` — `Dict/ResStr.mld` + `.txt` in lockstep, NATIVE key `Spell Ward locks all global enchantments` (`ResStr.txt:8773`); re-tuned row, `old` is a tuple | `[US]` = "Astral Ward blocks Town Gate and Warp Party" |
| spell description | `build_pfs_typos.py` — `Release/Spells.pfs` record **75** (spell id 65 + 10), tag `0x0A`; length-changing write, 128 → 109 chars (tuple `old`: vanilla + the 2026-09-06 text), CRC recomputed | "Wards the paths of the arcane. While any Astral Ward is active, no player can cast Town Gate or Warp Party." |
| manual | `build_ziggurat_manual.py` — `NEWMECH_SPELLWARD` in `r_newmech()` | seven bullets under the heading "Astral Ward". ⚠ The spell **table** still says Spell Ward: names there come from the historical workbook, which is not edited (same as Grip of Winter / Freeze Water) |

⚠ **The manual does not print spell descriptions.** `read_game_spells()` parses tag `0x0A`, but
its only consumer is `merge_spell_icons()`; the `desc` field is dropped and the spell cards render
Mana / Upkeep / Research alone. The rewritten record-75 text reaches the player through the
**in-game spell book only**. Do not expect the `.pfs` edit to show up in `Ziggurat Manual.html`.

### Revert

`python build_scripts/build_spellward_rescope.py --undo --apply` — surgical, touches no backup:
restores `80 78 22 02 75 3B` at `0x557792E8`, `0x40` at `0x557EF981` and `0x557EBAFD`, and zeroes
`0x55847000..0x558470FF`. The text edits revert independently via each script's own `--undo`
(⚠ `build_resstr_names.py --undo` reverts **every** row in its table, not just this one).

### Still untested

- [ ] The spell book lists the spell as "Astral Ward" and its description names the Astral Ward.
- [ ] The refusal reads "Astral Ward blocks Town Gate and Warp Party".

## Power Leech (ex Power Leak) — 🔨 APPLIED, UNTESTED (2026-09-07)

**The design.** Power Leak's halving is gone; the caster now steals **25% of the power income of
every magic node owned by another player** — the owner loses exactly what the caster gains. Only
one may be active map-wide, which was **already vanilla** and needed no code. Cost 100, upkeep 10,
unchanged.

Owner: `build_powerleech.py` (the mechanic, `AoWEPACK.dpl`) and `build_powerleech_ui.py` (the
Magic-window income row, `AoWz.exe` + `AoWzCompat.exe`). Text: `build_resstr_names.py` (name),
`build_pfs_typos.py` (description), `build_ziggurat_manual.py` (`NEWMECH_POWERLEECH`).

### What was written

| site | vanilla | patched |
|---|---|---|
| `0x5577CEC5` (4 B) | `E8 37 FB FF FF` → `GetPower @0x5577CA00` | `E8 37 B1 0C 00` → `cave_powerleech @0x55848000` |
| `0x5577CED8` (1 B) | `F6 42 10 08` = `test byte ptr [edx+0x10], 8` | `F6 42 10 00` — ZF always set, the halving branch never runs |
| `0x55848000` | zero | `cave_powerleech`, 379 B in a `0x400` reservation |

The rel32 site is the **opening `call` of `AoWE.TPlayerMagicControl.GetNetPower @0x5577CEC4`**, so
the cave runs with **EAX = the `TPlayerMagicControl`**. A hook placed any later cannot recover it:
`GetPower` returns the sum in EAX and restores `ebx/esi/edi`. Nothing is displaced; the only
`.reloc` entry in `0x5577CEB0..0x5577CEF0` is `0x5577CECB` (the `mov edx,[0x558FA040]` operand),
four bytes past the end of the written window.

`--undo --apply` restores both host writes and zeroes `0x55848000..0x558483FF`; the round trip was
proved SHA-256 identical to the pre-apply file. It touches no backup.

### The power pipeline

```
TPlayerMagicControl.NewTurn @0x5577CC2C
  GetManaIncome @0x5577C95C -> jmp GetNetPowerToMana @0x5577CEE4
    GetNetPower @0x5577CEC4                      <-- the halving, and the leech hook
      GetPower @0x5577CA00    sums [pmc+0x40] TPowerSourceList
        TPlayerStructurePowerSource.Power @0x55761B54 -> call [[src+8] vmt +0x1F8]
            TPowerNode.GetPower       @0x557D03C8   the seven node types
            TProductionPlace.GetPower @0x557BE468   cities
        THeroPowerSource.Power @0x557867D0          hero RES x Spellcasting
        TExternalPowerSource.Power @0x5577C2FC
```

`GetNetPower` has exactly two callers (`GetNetPowerToMana`, `GetNetPowerToResearch @0x5577CF80`)
and `GetPower` exactly one, so it is a genuine choke point. `GetNetPowerToResearch` is
`round(GetNetPower × [pmc+0x2C] × 0.01)`, so mana and research both follow the new value in the
caster's own proportion, and the AI budget with them.

⚠ **Power is NOT `GetIncome` (+0x1F4) or `GetBaseIncome` (+0x22C)** — it is the adjacent virtual
`TStructure.GetPower` = VMT **`+0x1F8`**. The shipyard finding transfers as a shape only.

Field map, all read out of live code: `[map+0x140]` TPlayerList, `[map+0x188]` TGlobalMagicControl;
`[gmc+0x10]` active-type byte-set, `[gmc+0x14]` TGlobalEnchantmentList; `[ench+0x18]` type code,
`[ench+0x19]` caster index; `[player+0x54]` pmc, `[player+0xA6]` index, `[player+0xA7]` type;
`[pmc+0x10]` TPlayer, `[pmc+0x2C]` research %, `[pmc+0x40]` TPowerSourceList; `[struct+0x30]` owner
byte (`0xFF` = none). A list's count is the virtual `[listvmt+0x54]`; items come from
`TPowerSourceList.GetItems @0x5577C2A0`, `TGlobalEnchantmentList.GetEnchantments @0x5577E13C` and
`TPlayerList.GetPlayers @0x557544D0`, all `(EAX = list, EDX = i)` — and **only GetPlayers is
bounds-checked**, so the count virtual is mandatory, not defensive.

### The cave

```
cave_powerleech(EAX = pmc) -> EAX                       @0x55848000
    base = GetPower(pmc)
    anchor: call $+5 ; pop ecx ; sub ecx, 0x77C50   -> EDI = runtime(TPowerNode.GetPower)
    map = [EDI + 0x129C78] ; gmc = [map+0x188]
    if (gmc[0x10] & 8) == 0                     -> return base
    caster = first e in [gmc+0x14] with [e+0x18]==3, take [e+0x19]; none -> return base
    if [[pmc+0x10]+0xA6] == caster              -> return base + SUM over every OTHER player of
                                                            nodepower(player) >> 2
    else                                        -> return base - nodepower(pmc) >> 2

nodepower(EAX = pmc, EDI = anchor) -> EAX               @0x5584810F
    for each source in [pmc+0x40]:
        if [srcvmt+0x50] != (EDI - 0x6E874)   continue    not a TPlayerStructurePowerSource
        s = [src+8] ; if [[s]+0x1F8] != EDI   continue    not a TPowerNode
        sum += call EDI   (EAX = s)                       the node's own GetPower
```

**Node discriminator: the VMT slot, not `IsClass` and not a seven-way ClassID compare.** All seven
node classes descend from `TPowerNode` and override only `ClassID` and `GetMagicSphere`, so all
seven share `TPowerNode.GetPower` in slot `+0x1F8` — true for exactly those seven, false for cities
and false for `TRandomNode` (a `TProductionPlace` descendant), and it survives a node type added
later.

| node | VMT | ClassID | sphere |
|---|---|---|---|
| Power | `0x557CFFE4` | `0x2019A` | — |
| Life / Death / Earth | `0x557C046C` / `0x557BFFA4` / `0x557BFAE0` | `0x20371` / `0x204AE` / `0x204CE` | 1 / 2 / 3 |
| Air / Fire / Water | `0x557C0DF4` / `0x557BF624` / `0x557C092C` | `0x2094E` / `0x203DE` / `0x204B3` | 4 / 5 / 6 |

The `+0x50` source-class test comes **first and is not optional**: a `TPowerSourceList` also holds
`THeroPowerSource` and `TExternalPowerSource`, whose `[src+8]` is not a `TStructure` at all.

Calling the node's own `GetPower` virtual (rather than assuming 12) is what makes a razed node, or
one carrying a building, yield nothing to leech — exactly as it yields nothing to its owner.

⚠ **Not a percentage of `GetPower`.** That sum also carries city production (`TProductionPlace`
registers a power source too) and hero mana generation, neither of which this design touches.

**No cache, deliberately.** Ownership changes mid-turn and `GetNetPower` runs on UI repaint, so a
day-keyed cache would be wrong. Worst case ~600 iterations, for one player.

Register safety is not an assumption: vanilla's own `GetPower` already runs the identical
`GetItems` → `[+0x50]` → `[+0x1F8]` chain with `esi`, `edi` and `ebx` live across it.

### PIC — anchor on a FUNCTION, so no `0x55xxxxxx` operand survives

`assemble_pic()` is lifted verbatim from `build_spellcast_herotier.py:132`, but the `sub` immediate
is chosen so **EDI ends up holding the runtime address of `TPowerNode.GetPower` itself**, not the
bare rebase delta. Two consequences: the node test is `cmp dword ptr [edx+0x1F8], edi` with no
immediate at all, and the other two absolutes become small signed offsets from EDI. The assembled
cave therefore contains **no `0x55xxxxxx` operand of any kind** and needs no `.reloc` entry.

All three resolved addresses are re-derived from the assembled bytes at build time and asserted:

```
anchor: pop ecx @55848018  -  sub ecx, 0x77C50  ->  EDI = 557D03C8   TPowerNode.GetPower
edi + 0x129C78 -> 558FA040   AoWE.AoWHSMap
edi - 0x06E874 -> 55761B54   TPlayerStructurePowerSource.Power
```

Guards G1..G6 in the script tie the assembled bytes back to the constants: G1 the anchor, G2 the
EDI-relative targets (**and that there are no others**), G3 no absolute operand, G4 the keystone
`push imm8` `-1` trap, G5 the sanctioned call targets, G6 both frames balance 2/2/2.

### ⚠ Node power is 12 on this install and NOTHING owns that edit

```
557D03E4  live  B8 0C 00 00 00   mov eax, 0xC   (12)
          van   B8 0A 00 00 00   mov eax, 0xA   (10)
```

`grep -rl "557D03"` over `build_scripts/` returns nothing — an undocumented pre-convention hand
edit. **`build_powerleech.py` aborts if that byte is not `0x0C`.** 25% of 12 is exactly 3, so
per-node and per-player rounding coincide today; they diverge the moment node power stops being a
multiple of 4, and the script must be re-read before that happens.

(Adjacent and owned: `TProductionPlace.GetPower @0x557BE4CC` is `picks*6 + 6` with the zero-pick
`je` nop-ed, so every city yields at least 6 — `build_shipyard_income.py:611`.)

### Requirement C — one at a time — is ALREADY VANILLA

`AoWE.TGlobalEnchantment.CanActivate @0x5577DAE8` reads `[ench+0x18]`, and for a type code in
`1..7` does `bt dword ptr [gmc+0x10], eax` and refuses if set. `[gmc+0x10]` is rebuilt from the
whole enchantment list by `UpdateActiveEnchantments @0x5577E46C` with **no per-player filter**, so
one Power Leech anywhere blocks every player including its caster. `TPowerLeakEnchantment` VMT
`+0x64` is `0x5577DAE8` — inherited, not overridden — and `+0x6C` is `TGlobalEnchantment.CanCast`
(`call [self+0x64]`), reached from `TGlobalEnchantmentSpell.CanActivate @0x557EF938`.

⚠ Type codes >= 8 are never recorded and never refused: `UpdateActiveEnchantments` writes only the
low byte of `[gmc+0x10]` while `CanActivate` guards the `bt` with `cmp al,7; ja`. Power Leech's 3 is
inside the working range — leave it.

Cast-time is sufficient: `TGlobalMagicControl.ReadWrite @0x5577E1D4` reloads the list and rebuilds
the set, so a load cannot smuggle in a second.

**The refusal string needed no work.** `%s is already active` (`ResStr.txt:465`) is formatted with
`[ench+0x1C]`, which `TPowerLeakEnchantment.Create @0x557F0FD8` loads from `AoWE.PowerLeakRStr` —
the **same ResStr row as the spell name** (`ResStr.txt:7495`). The one rename fixes all three
surfaces.

### Caster elimination ends the leech by itself — verified, not assumed

`TPlayer.SetGameOverStatus @0x55751848`, when `[player+0x44] == 2`, calls
`TGlobalMagicControl.RemovePlayerEnchantments @0x5577E37C` at `0x55751B03` with
`DL = [player+0xA6]`. That walks `[gmc+0x14]` backwards and, for every enchantment whose
`[e+0x19]` matches, calls `[evmt+0x80]`. A defeated caster's Power Leech is removed like any other
enchantment of his.

Cast and dispel already take effect immediately: `TPowerLeakEnchantment.Activate @0x557F1080` and
`Deactivate @0x557F10C8` loop every player calling `TPlayerMagicControl.Update`. ⚠ **Do not touch
them** — that loop is what makes the change visible the moment the spell lands.

`TPlayer` holds **no back-pointer to the map**: `TPlayer.Create @0x55750EA8` wires back-pointers
the other way (`pmc[+0x10] = player`, AI control `[+8] = player`, budget manager `[+8] = player`).
The map global is the only route to the player list, which is why the anchor exists at all.

### Neutral player 0 — what this build does

Player index 0 is a **real `TPlayer`**: `TPlayerList.SetNumberOfPlayers @0x557546B0` creates it like
any other (giving it `[+0xA7] = 4`), `TPlayer.Create` gives every player a `TPlayerMagicControl`
unconditionally, and `TPowerNode.SetPlayer @0x557D0584` registers a power source for any owner byte
`!= 0xFF`. The engine's own `GetNumberOfPlayers` returns `count-1` and `RaceToPlayer` starts at 1,
i.e. it treats index 0 as not-a-player.

**This cave walks the whole player list, index 0 included** — a node owned by the neutral player is
leeched like any other, and neutral's own net power drops by the same amount. The alternative would
have to skip index 0 in *both* branches or power would vanish, and uniformity is the simpler rule.
Truly ownerless nodes (`[struct+0x30] == 0xFF`) are in nobody's power-source list and give nothing,
which is the user's strict-transfer ruling. Whether any shipped or generated map actually assigns a
node to owner 0 is an in-game observable, in the checklist below.

### RNG and determinism

Nothing here draws. The result is a pure function of replicated state — the enchantment list,
`[ench+0x19]`, the player list, `[struct+0x30]` — with no draw and no cache, so it is identical on
every peer. `rng_audit.py --owners` gained **zero** sites (24 before, 24 after, none at
`0x5584xxxx`).

### AI

`AIPrefetchCastSpellActions @0x557EFBA8` and `AICanCastSpell @0x557EFB00` are real implementations,
not the `TSpell` `ret` stub, so the AI does cast this. Its budget reads `GetManaIncome`, so it
follows the new value automatically. `GetAIUpkeepPriority @0x557F1078` returns 750; left alone.

### The income row — 🔨 APPLIED, UNTESTED (2026-09-09)

Owner: `build_powerleech_ui.py`, on **`AoWz.exe` + `AoWzCompat.exe`**. `AoWEPACK.dpl` is not
touched by it, and it knows nothing about magic nodes.

The Magic window's tab 4 gains **one row at the end** of the power breakdown:

| viewing player | label | value |
|---|---|---|
| the caster | `Power Leech (gained)` | `+N` |
| any player losing power | `Power Leech (lost)` | `-N` |
| neither | *(no row)* | |

A player is either the caster or a victim, never both — `cave_powerleech` skips the caster's own
nodes — so one row with a side-dependent label and sign covers every case. `Power Base`
(`[form+0xE8]`) still shows the **raw** un-leeched total; that is vanilla behaviour, deliberately
left alone, and this row is what makes the leech visible.

**The number needs no knowledge of the mechanic and no new import:**

```
delta = TPlayerMagicControl.GetNetPower(pmc) - TPlayerMagicControl.GetPower(pmc)
```

With the halving byte dead, `GetNetPower` *is* `cave_powerleech`, so the difference is the leech
exactly. AoW.exe already imports both (IAT `0x0045DD4C` / `0x0045DD50`, thunks `0x0040262C` /
`0x00402624`, 1 ref each). ⚠ **Forward hazard:** the row is driven purely by that difference, so
restoring the vanilla halving (`build_powerleech.py --undo`) would give a non-caster a
"Power Leech (lost)" row for the *halving* — though only in a game where the halving option bit
is set, since the restored `test byte ptr [gmc+0x10], 8` gates it. Undo the two together.

| site | vanilla | patched |
|---|---|---|
| `0x0042CFD9` (7 B) | `8B C3 E8 44 56 FD FF` = `mov eax,ebx ; call 0x00402624` | `E8 CA 01 20 00 90 90` = `call cave_powerleech_ui` |
| `0x0062D100` | zero | `cave_powerleech_ui` — 0xA8 B of data, then 107 B of code at `0x0062D1A8`, in a `0x200` reservation |

`0x0042CFD9` sits immediately after the value-column loop terminator at `0x0042CFD7`, so both
lists are fully populated when the cave runs. It **is** a branch target — `0x0042CF4F
jl 0x0042CFD9` skips the loop for a player with no power sources — but it is the *first* byte of
the displaced run, so the jump still lands on the `E8`; the script sweeps every rel8/rel32 branch
in CODE and aborts on any landing strictly inside `0x0042CFDA..0x0042CFDF`. Entered by `call`,
not `jmp`, so EBP is still the host's frame: `[ebp-4]` = the `TMagicWin`, `[ebp-0xC]` = the same
managed AnsiString temp the fill loop reuses (zeroed at `0x0042CDEB`, released by
`@LStrArrayClr` at `0x0042D27B`). `mov eax,ebx / call GetPower` is not re-emitted — the cave
calls `GetPower` itself for the delta and returns that same raw value in EAX, which is what
`0x0042CFE0` consumes for `Power Base`. Zero `.reloc` entries in the written window (nearest is
`0x0042D00C`, the operand of `push 0x42D298`).

The cave lives in **`.hcol`** (`0x00612000`, VirtualSize `0x1C000`, chars `0xE0000060` =
CODE|EXEC|READ|WRITE), at the next clear `0x100`-aligned slot above the highest existing occupant
(`build_savedate_format.py` ends `0x0062D07A`); `0x0062D0A0..0x0062DFFF` is verified all-zero.
**No new PE section** — AoWz.exe has exactly one free section-header slot left (`0x3D8..0x400`
inside `SizeOfHeaders 0x400`) and a display row is not what to spend it on. `.syd` is unusable
because `build_shipyard_income_display.py` rewrites that whole page on `--apply` and reports any
foreign byte as drift.

### The label text — a literal AnsiString, not a resourcestring

Every existing row's name comes from the power source's `Name` virtual (`[srcvmt+0x4C]`); the
surrounding labels are resourcestrings via `TranslateRStr`. Minting a new resourcestring means
growing `.rsrc`. Instead the cave carries two **compiler-shaped literal AnsiStrings**, the
representation read out of this very function rather than assumed: `0x0042D00B` is
`push 0x42D298`, and `0x0042D290` holds `FF FF FF FF | 01 00 00 00 | 2D 00` — refCnt −1,
length 1, then `"-"`. StrRec skew is **8** (`[-8]` refCnt, `[-4]` length, `[0]` chars) and the
pointer passed around is the address of the chars. **refCnt −1 is what makes it safe**: Delphi's
`_LStrAsg` copies a negative-refcount string instead of incrementing it, so nothing ever tries to
free or realloc a string that lives in a PE section. (`build_skylevel_ui.py` uses the same record
shape for its "Firmament" caption.)

### ⚠⚠ The AddObject object cannot be nil — that is a crash, not a nicety

The ABI is copied verbatim from `0x0042CF7D..0x0042CFD0`: the **name** column is
`TStrings.AddObject` at `[stringsvmt+0x38]` (EAX = `[[form+0x110]+0x114]`, EDX = the AnsiString,
ECX = the associated `TObject`); the **value** column is `TStrings.Add` at `[stringsvmt+0x34]`
(EAX = `[[form+0x108]+0x114]`, EDX = the string), fed by `IntToStr` (EAX = value, EDX = @result,
thunk `0x004013AC`).

`TMagicWin.PowerSourceListDoubleClick @0x0042D944` and `TMagicWin.PowerValueListMouseDown
@0x0042D988` (right button; it reads the **name** list's ItemIndex) both do

```
call [[strings]+0x18]   TStrings.GetObject(ItemIndex)
mov  edx, [eax]         <-- unconditional, NOT nil-checked
call [edx+0x5C]         TPlayerStructurePowerSource.Select      (double-click)
call [edx+0x58]         TPowerSource.CenterToLocation           (right-click)
```

Both are index-bounds-checked and **neither is nil-checked**, so a row added with a nil object
faults the moment the player selects it and double- or right-clicks. So the row is added with a
4-byte **fake object** pointing at a 24-slot **fake VMT** (`+0x00..+0x5C`, the full VMT of
`TPlayerStructurePowerSource` read from `0x55714250`, whose class-name string begins at `+0x60`)
whose every slot is `xor eax,eax ; ret`. Both reachable slots are argument-free procedures
(verified: `Select @0x55761B94`, `CenterToLocation @0x5577C248`, both plain `ret`), so a bare
`ret` is the correct stack discipline. Clicking the Power Leech row does nothing — right, since
it is not a map object. Negative VMT slots are left zero: nothing constructs, destroys or
class-queries these objects, and `TStrings.Clear` does not free them, which is why the live power
sources can be listed at all.

The **value** column needs none of this: every one of its rows already has a nil object (the host
uses plain `Add`), and `TAOWListBox`'s drawing never reads `Objects[]`.

### Why not the realm window

`TRealmWin`'s income panel is **gold, not power** — its rows are `ExternalIncomeRStr`,
`CitiesRStr`, `FarmsRStr`, `MinesRStr`, `BuildersGuildsRStr` (label IAT slots `0x45E108`,
`0x45E11C`, `0x45E114`, `0x45E118`, `0x45E0BC`) plus `.syd`'s Shipyards, and **no power figure
appears in `IncomePnl` at all** — and it is full at six label rows. `TAOWMemo.SetSize`
(aowInt.dpl `0x598189C0`) gives `IncomeMem` `(76−6)/12 = 5`, drawn as `[+0x124]+1` = 6 rows;
`IncomeSB` cannot rescue it because `TRealmWin.IncomeSBChange @0x0044B5C0` scrolls
`[self+0x184]` = **`IncomeValue`**, so the label column has no scroll path at all. Levers, if a
gold row is ever wanted there: `ItemHeight 12 → 10` on both memos (8 rows, tighter than
`UpkeepMem`), or grow `IncomePnl`, which is `ahBoth` inside `T1Pnl` and so needs the Realm window
itself to grow.

⚠ `TMagicWin` tab 4 has no such ceiling: arbitrary length, one row per power source, and only
`PowerValueList` declares `VScrollBar` in the DFM — the two lists are kept in step by
`TMagicWin.PowerSBChange @0x0042D9E4`, which calls `TAOWListBox.SetListOff` on **both**
`[self+0x110]` and `[self+0x108]`. Do not assume a shared DFM scrollbar; without that handler
this panel would desynchronise exactly as the Realm window does.

⚠ `build_shipyard_income_display.py` currently reports `mixed — .syd present but nsec=12` for
both exes and refuses to write. Its `EXP_NSEC` guard predates `.pyar`. The feature itself is
installed; only the script's self-check is stale.

### Undo — the income row

`build_powerleech_ui.py --undo --apply` is surgical and touches no backup: `0x0042CFD9` goes back
to `8B C3 E8 44 56 FD FF` and `0x0062D100..0x0062D2FF` is zeroed, in **both** exes. Round-tripped
2026-09-09 to files byte-identical to the pre-apply snapshots, and the re-apply reproduced the
same SHA-256 in both exes. The script refuses to write when the two exes are in different states,
and re-proves after writing that `AoWz.exe` and `AoWzCompat.exe` differ in exactly one byte, at
`0x3BB7C`.

### Text and manual, as applied

| what | script | detail |
|---|---|---|
| name | `build_resstr_names.py` | NATIVE `Power Leak` (`ResStr.txt:7495`) → `[US]` `Power Leech`. One row covers the spell name, the enchantment name and the "already active" refusal |
| description | `build_pfs_typos.py` | `Spells.pfs` record **58** tag `0x0A`, 108 → 195 chars. ⚠ **Hard ceiling 205 characters**: this record's body directory is MIXED (tags 10/11/12 are u8 entries, 13..17 are u32) and tag 12 sits at offset 158, so `158 + (new − 112) ≤ 255`. Longer text aborts loudly with "exceeds the u8 directory ceiling" |
| manual | `build_ziggurat_manual.py` | `NEWMECH_POWERLEECH`, **10** bullets, beside `NEWMECH_SPELLWARD` in `r_newmech()`; the `NEWMECH_SPELLWARD` bullet that read "Power Leak and the rest" now reads Power Leech, and the tenth bullet (2026-09-09) names the two Magic-window row labels. Rebuild produced no new warnings |

Live `Spells.pfs` record 58: mana 100, upkeep 10, research 110, sphere 0, tier 4 — none changed.

### ⚠ Still untested — the user's in-game checklist

- [ ] Cast Power Leech. The spell book and the Magic window's global-enchantment list both name it
      **Power Leech**, and its description names 25%, "held by a rival" and the one-at-a-time rule.
- [ ] With a rival holding **N** magic nodes, the caster's power income rises by **3 × N** and the
      rival's falls by **3 × N**. Both numbers move on the turn the spell lands, not the next one.
- [ ] The caster's **own** nodes are not leeched — capture one of the rival's and the total moves
      by +9 net (3 stops being leeched, 12 joins the caster's own base), not by +12.
- [ ] A **razed** node, and one with a **building** on it, contribute nothing.
- [ ] Cities and heroes are untouched: a player with cities and no nodes loses nothing.
- [ ] Dispel it — both players' income returns to normal that same turn.
- [ ] **Defeat the caster** — the leech ends and the victims' income returns.
- [ ] A second player tries to cast it: refused with **"Power Leech is already active"**.
- [ ] ⭐ **Neutral-owned nodes** — find a map where a node belongs to the Independents (not merely
      unclaimed) and confirm whether it is leeched. This build says yes; nothing breaks either way,
      but the answer belongs in this section.
- [ ] Sanity: no "Invalid AoWHSMap.Random use" popup, and the Magic window's Power Base still shows
      the un-leeched raw total (vanilla behaviour, not a defect).

**The income row (`build_powerleech_ui.py`) — separate, and needs a fresh `AoWz.exe` launch:**

- [ ] ⭐ **Launch the game at all.** The cave runs on a UI repaint, not at package init, but it is
      the first thing to prove.
- [ ] Open the Magic window, tab 4 (the power breakdown), with **no** Power Leech active: the list
      ends with the last real power source and there is **no** Power Leech row.
- [ ] As the **caster**, with a rival holding N nodes: the last row reads **`Power Leech (gained)`**
      with **+3 × N**, and it lines up with its number in the right-hand column.
- [ ] As a **victim**: **`Power Leech (lost)`** with **−3 × N**, N being that player's own nodes.
- [ ] ⭐⭐ **Click the new row, then double-click it, then right-click it.** It should do nothing at
      all — no map jump, no crash. (Every other row selects and centres on its source; the new one
      carries a stub object precisely so this is inert. A nil object here would fault.)
- [ ] Scroll the list with enough power sources to overflow it — the label and value columns stay
      in step and the new row scrolls with them.
- [ ] `Power Base`, `Net Mana` and `Research` above the list still read as before.
- [ ] Repeat once in **AoWzCompat.exe**.

---

## Terror — ATK 16 → 12 — 🔨 APPLIED, UNTESTED (2026-09-09)

`build_terror_atk12.py` on `AoWEPACK.dpl`. Pure immediate rewrite: five instruction immediates
change value in place, same widths. No cave, no hook, no keystone, nothing displaced, no `.reloc`
entry over any of the five (scanned). ⚠ The `backups\AoWEPACK.dpl.pre-terroratk12` snapshot was
minted into `<root>/backups/` and went with that directory on 2026-09-10 — **it no longer exists**.
Revert is the surgical `--undo`, which restores **16**, not vanilla 6.

**The number.** User decision: Terror's ATK is **12** in the current doubled scale.

| | value |
|---|---|
| vanilla (`AoWEPACK_original_backup.dpl`) | 6 |
| live before this patch | 16 |
| live now | **12** |

⚠ The `6 → 8` step was an **undocumented pre-convention Ziggurat change** already present in the
install; the hit-chance audit sampled the *installed* DLL, recorded 8, and the doubling pass took
8 → 16. So `_old/FivePct_Doubled_Sources_Inventory.md`'s "8 → 16" was doubling a Ziggurat value, not
a vanilla one — vanilla's 6 would have doubled to 12, which is what is now installed. Those `_old/`
files and `fivepct_manifest.json` are historical records of what the conversion did, are accurate as
such, and are deliberately **not** edited. Generalised as a standing trap in `01-combat-maths.md` §3
("the conversion's 'before' column is the installed DLL, not vanilla").

### The five sites — all must move together

⚠ **Terror's power is encoded FIVE times, not two or three.** Copies 4 and 5 were missed by the
original hit-chance audit and only caught by the 5% conversion sweep
(`_old/HitChance_Increment_Audit.md:222` records the correction). **A partial edit is silent** — the
spell would use different powers in tactical vs auto-resolve vs the AI's damage estimate, and
nothing would report it. The script's state machine is therefore all-or-nothing: any disagreement
between the five reads `MIXED` and aborts.

| # | immVA | file off | w | instruction | function |
|---|---|---|---|---|---|
| 1 | `0x557F9A81` | `0x0F8E81` | 1 | `mov byte ptr [eax], 0x0C` | `TTerror.Create` — spell ATK `[self+0x34]` |
| 2 | `0x557F9887` | `0x0F8C87` | 4 | `mov eax, 0x0C` | `TFastCombatTerrorCA.Generate` (auto-resolve) |
| 3 | `0x557F9A0B` | `0x0F8E0B` | 4 | `mov eax, 0x0C` | `TTacticalCombatTerrorCA.Generate` (tactical) |
| 4 | `0x557F9CA6` | `0x0F90A6` | 4 | `mov eax, 0x0C` | `TTerror.fcGetDamageValueEx` (AI value — **dead code**) |
| 5 | `0x557F9D8F` | `0x0F918F` | 4 | `mov eax, 0x0C` | `TTerror.tcGetDamageValueEx` (AI value, tactical) |

Sites 2–5 are the identical idiom — the power, minus the defender's stat, into the to-hit roll:

```
movsx eax, al          ; defender stat
push  eax
mov   eax, POWER       ; <-- the rewritten immediate
pop   edx
sub   eax, edx
call  HitRole            (sites 2,3 -- 0x55725D98)
call  HitRoleProbability (sites 4,5 -- 0x55725DCC)
```

Site 4 is dead for Terror (VMT `+0x98` is overridden but never called — `fcPrefetchCombatCommands`
accumulates the value inline; see `10-ai-and-structures.md`). Rewritten anyway so the five never
disagree: a session that revives that path must not find a stale 16.

⚠ **Do not touch `0x557F9A85`** (`mov byte ptr [eax+1], 0`, TTerror damage `[self+0x35]`) — 0 in
both live and pristine, not an ATK site.

Verify-before-write asserts each site's **opcode prefix** (`c6 00` / `b8`), not just the immediate,
so a wrong address aborts rather than mangling a neighbouring instruction. Re-tuning is a one-line
edit (`TARGET_ATK`, plus the superseded value appended to `ACCEPT`) — never revert-and-reapply.

### Cross-feature couplings — checked, none

Both are **forward hazards to respect, not problems found**: they share the function bodies, not the
bytes.

- `build_terror_oncepercombat.py` (applied) owns hooks `0x5572708C`(5) / `0x557F991E`(8) /
  `0x557F9B20`(7) / `0x557F9BE8`(5), VMT slot `0x557F625C`(4), caves `0x5582A000`–`0x5582A200`. Its
  `C_WRAPTC` **calls** `tcGetDamageValueEx @0x557F9D44` unchanged, and site 5 sits inside that
  function — but its verifier checks hook runs, slot value and cave bytes only, none of which
  include `0x557F9D8F`. Confirmed still `APPLIED` after this patch.
- `build_leadership_fearless.py` (applied) retargets four `call rel32` + nop runs at `0x557F9844`,
  `0x557F99C8`, `0x557F9B6B`, `0x557F9D55` (8 B each). No overlap. Confirmed still `APPLIED`.

Neighbouring immediates deliberately left alone — **not** sixth copies of Terror's power:
`TSacredWrath.Create @0x557F9717` (live 12) and `TWindsOfFury.Create @0x557F9E5F` (live 16, pristine
8 — a real doubling).

No cave and no draw, so the SYNCED/RAW rule does not apply; `rng_audit.py --owners` is unchanged at
24 modded sites. `.pfs` untouched — Terror's power is code-side only. Multiplayer: a constant baked
identically into every peer's DLL.

### Needs the user's in-game test

- [ ] Cast Terror in **tactical** combat against a stack whose units have known Resistance; the
      panic rate should drop noticeably versus before (power 12 against the same defender stat).
- [ ] **Auto-resolve** a battle where the AI casts Terror — same weakening, and no crash.
- [ ] Confirm the **once-per-combat** cap still holds (AI casts Terror at most once per battle, per
      side) — sites 4/5 sit inside that feature's functions, so this is the coupling to eyeball.
- [ ] Confirm **Leadership IV / Fearless** still blocks Terror.
- [ ] Terror's info card, if it quotes a number, still reads sensibly.

---

## Open items

1. **Storm effect roll's RNG generator** (full reasoning above, under that feature) — reaches
   `HitRole` (RAW) from a non-combat, non-re-anchored context with no sanctioned reseed bridge;
   the project's own audit tool cannot see this class of bug, and the one summary table that does
   classify it gives no per-site reasoning unlike its neighbours. Settle with an in-game MP test
   across several turns, watching for a late, unrelated OOS dialog; fix (if needed) is
   `build_arena.py`'s one-line reseed bridge inserted before the cave's `call 0x55781BA4`.
2. **Enchantment upkeep scaling (§3 above):** confirm whether any shipped unit enchantment
   overrides the vanilla default upkeep of 1 before assuming a flat base to multiply — a quick
   sweep of enchantment `Create`/`Activate` methods for `SetUpkeep` calls would settle it.
3. **Combat-path cast-cost scaling (§3 above):** `TCombatSpellCaster`'s cost-commit site for
   combat-cast unit-enchantments is untraced — real gap for "more expensive to cast in tactical
   combat," Needs-more-RE.
4. **Cosmagic Scrying's raw-cost site** (`0x557E85F9`, part of the instant-cast bug's optional
   Tier 2/3 list, not fixed): its `.reloc` status is explicitly flagged unverified in
   `03-abilities-added.md` §6.4 — check before ever patching it.
5. **Per-unit intrinsic spellbook's list-insertion route (§1 above):** route (a)'s "hidden when
   the TSpellList is exactly at capacity" edge case is accepted as low-risk but untested; route
   (b) (call the DLL's `TSpellList.Add` via rebase-delta) removes it if it ever matters.

## Failed approaches — do not retry

- **Spellbook hover-glow via double-composite redraw** (`build_glowboost.py`, `aowInt.dpl`,
  targeting `TAOWBaseButton`'s lit-draw sites `DrawILLh`/`DrawILI`) — applied, tested, and
  **reverted** 2026-07-18. The book never repaints the parchment under a button between paints,
  so any extra translucent draw layer accumulates into unbounded "whack-a-mole" ghost brightening
  of unhovered entries. The correct fix edits the **stored** ILB image/blend data once
  (`build_glowilb.py`) instead of compositing extra draws at runtime.
- **v5's static DFM patches for taller research-book panels** (tier research) — the S-slot
  panels/memos are shared between the cast and research spellbook modes; moving them in the DFM
  resource leaked into the cast book too (overlapping entries). Replaced in v7 by handling all
  research-mode geometry **at runtime** in a cave, leaving the DFM (and the cast book) byte-exact
  vanilla.
- **"`SpellTypes` is bound-limited, not size-limited"** — refuted; don't re-derive. The table is
  genuinely sized to 131 bytes with live data (`BreathHit`/`BreathDir`) immediately after it, not
  merely bound-checked.
- **"The `.pfs` key ↔ spell id mapping isn't closed-form"** — refuted; don't re-derive.
  `key = id + 10` holds for all 108 spells and is code-derived, not empirical.
