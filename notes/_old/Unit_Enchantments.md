# Unit enchantments — the re-grade, and the manual section that reads them live

**Status: CONFIRMED WORKING (2026-08-24)** — validated in-game by the user the same day.
Scripts `build_scripts/build_buff_regrade.py`
(22 engine immediates, surgical `--undo`, backup `AoWEPACK.dpl.pre-buffregrade`) and
`build_scripts/build_assassin.py` (cave copies). Extractor `re_tools/enchant_mods.py`. Manual
section `Unit Enchantments` in `build_ziggurat_manual.py`.

## Why

The 5% conversion doubled every stat, so every buff landed on an **even** number — a vanilla +2
became +4, a vanilla +3 became +6. The finer slope existed precisely to make the in-between grades
usable, and nothing was spending that headroom. This re-grade drops the affected buffs one notch
onto odd values they could not previously express.

## Decisions (user, 2026-08-24)

| # | decision |
|---|---|
| E1 | Enchanted Weapon → **+3/+3** ATK/DAM (explicitly, not the mechanical +4/+4) |
| E2 | Enchantment buffs one notch down: Stone Skin +3, Frozen +3, Blessed DEF +1 / RES +3, Nature's Blessing DEF +1 / RES +3, Bloodlust +3/+3, Dark Gift +3, Fury ATK +5 |
| E3 | Combat boosts (Monster Slaying, Assassin, Charge) → **+5**, and grouped in the manual as a *Combat Boosts* subsection alongside Parry |
| E4 | Debuffs: **only** Vertigo and Poisoned soften, to −3/−3. Cursed, Entangled, Stunned, Webbed stay −4; Bloodlust DEF and Fury DEF stay −2 |
| E6 | **Invisibility to-hit penalties**: ranged −6 → **−5**; melee went −2 → −1 → **−2 again** (restored the same day). Owner `build_invis_penalty.py` (`RANGED_PENALTY` / `MELEE_PENALTY`). Not in `build_statdouble`'s scope — these are stage-11 rows, and stage 11 is excluded from `STAGES_ENABLED` precisely because owner scripts hold them, so no manifest sync is needed |
| E7 | **Holy and Unholy Champion melee → +5/+5**, matching Monster Slaying and Assassin. **12 immediates** — each champion's bonus is applied in THREE strike builders (`StrikeDV` and both `TMeleeRound` tables), ATK and DAM in each. Their **ranged** branch was already +2/+2 and is untouched |
| E5 | **High Prayer Blessing matched to Blessed's effect**: DEF +2 → **+1**, RES +2 → **+3**. ⚠ Not a "one notch down" like the rest — DEF moves DOWN and RES moves UP. Only the STAT EFFECT is equalised: the two remain in different families (Blessed is a dispellable enchantment, High Prayer a combat-duration status), so duration and dispellability still differ |

## ⚠⚠ TWO FAMILIES — and the class NAMES lie about which is which

Corrected 2026-08-24 after a hierarchy audit (VMT ancestry walked for all 854 classes in the image;
independently re-derived twice). The engine's own test is
`TAbstractUnit.AbilityToEnchantment @0x5577F3B4`, an `IsClass` against **`TUnitEnchantmentAbility`**
(VMT `0x55722364`). That predicate — nothing else — defines a unit enchantment.

| family | root VMT | count | dispellable |
|---|---|---|---|
| **Unit enchantments** | `TUnitEnchantmentAbility` `0x55722364` | **21** | yes |
| **Temporary statuses** | `TDurationAbility` `0x5571DD68` | **13** | no |

**Eight `...Ability`-suffixed classes that read like enchantments are statuses:** Bloodlust, Cursed,
High Prayer Blessing, Nature's Blessing, Poisoned, Stunned, Vertigo, Webbed. And the look-alike
pairs straddle the split — **Webbed (status) vs Entangled (enchantment)**, **Stunned (status) vs
Frozen (enchantment)**. Never bucket these by name.

**14 of the 21 enchantments carry no stat modifier at all** (Haste, Concealment, Free Movement,
Water/Wind Walking, Liquid Form, Fire Halo, Fire Protection, Summoned, Cosmetic Surgery, Slow,
Turned Undead, Holy/Unholy Champion). Their effect is an ability-id test at a consumer site. They
belong in the section regardless — a list that dropped them would be a list of numbers, not a list
of enchantments. The two Champions appear again under Combat Boosts, where their +4/+4 actually
lives.

⚠ **`TBlessedEnchantment` and `THighPrayerBlessingAbility` both resolve to the resource string
"Blessed"** in game — different families, same display name. The manual disambiguates the second.
Since E5 they also carry the **same stat effect** (DEF +1 / RES +3), so in play they differ only in
how they arrive and how they end: Blessed is cast, permanent and dispellable; High Prayer's version
is granted for the combat and cannot be dispelled. Three description strings now read identically
(`Ability.pfs` recs 109, 110, 168) — which is why the `FIXES` table must key on **record id**.

## What the binary actually holds now

Read at any time with `python re_tools/enchant_mods.py` — it walks the class hierarchy and
disassembles the getters, so it cannot go stale.

| enchantment | live | vanilla |
|---|---|---|
| Blessed | DEF +1, RES +3 | +1 / +1 |
| Bloodlust | ATK +3, DEF −2, DAM +3 | +1 / −1 / +2 |
| Cursed | DEF −4, RES −4 | −2 / −2 |
| Dark Gift | DAM +3 | +1 |
| Enchanted Weapon | ATK +3, DAM +3 | +1 / +1 |
| Entangled | DEF −4 | −2 |
| Frozen | DEF +3 | **−2** (Ziggurat flipped the sign) |
| Fury | ATK +5, DEF −2 | +2 / −1 |
| High Prayer Blessing | DEF +1, RES +3 (E5: matched to Blessed) | +1 / +1 |
| Nature's Blessing | ATK **0**, DEF +1, RES +3 | +1 / +1 / +1 |
| Poisoned | ATK −3, DEF **0**, RES **0**, DAM −3 | −1 / −1 / −1 / −1 |
| Stone Skin | DEF +3 | +2 |
| Stunned / Webbed | DEF −4 | −2 |
| Vertigo | ATK −3, DEF −3 | −2 / −2 |

Combat boosts, now split melee/ranged in the manual because the two differ:

| bonus | melee | ranged |
|---|---|---|
| Monster Slaying | +5 / +5 | +2 / +2 |
| Assassin | +5 / +5 | +2 / +2 |
| Holy Champion | +5 / +5 | +2 / +2 |
| Unholy Champion | +5 / +5 | +2 / +2 |
| Charge | DAM +5 | — |
| Parry | −8 to the attacker | — |
| Invisible target (attacker lacks True Vision) | −2 ATK | −5 ATK |

Leadership +1/+2/+3/+4 both stats, by level.
⚠ The four slayer-style bonuses' **ranged** branch is one shared cave (`build_ranged_slayers.py`
@`0x5580E190`) covering Monster Slaying `0x70`, Holy Champion `0x92`/`0xA0`, Unholy Champion
`0x93`/`0xA1` and Assassin `0x38`; their **melee** branches are separate engine sites per builder.
⚠ In that cave `[esp]` is DAMAGE and `[esp+8]` is ATTACK — an operand-swap trap the script documents.
⚠ `0x55767C82` in `CalculateStrikes` still reads `add dword [ebx], 3` — that is the **dead** Monster
Slaying block, superseded by the cave at `0x5580E148`. Do not "fix" it to 5.

## ⚠ Answering "wasn't Bloodlust zeroed in Ziggurat?" — no, but something was

Byte-diffed live vs `AoWEPACK_original_backup.dpl`, and checked for a VMT repoint (single pointer
each at `0x557B5A1C/A20/A28` — the getters are live, not dead code). **Bloodlust was never zeroed:**
vanilla ATK +1, and Ziggurat *raised* it to +2. What Ziggurat **did** zero:

- **Nature's Blessing ATK**: vanilla +1 → **0**
- **Poisoned DEF and RES**: vanilla −1 each → **0**

Those are the zeroed slots the recollection was about. They are preserved as zeros. The manual
prints a **dash** for them (user, 2026-08-24) — same glyph as a stat the class does not modify at
all, because the distinction is not worth a column of `+0`s. The information is not lost: the
vanilla/Ziggurat switch still shows `–` against vanilla's `+1`/`−1`, so a zeroed slot is visible by
comparison.

⚠ The dash must be passed as the **glyph**, not as an empty string. `dcell()` treats an empty
Ziggurat side as *"not stated in the design workbook"* and renders a `?` with that tooltip — correct
for the workbook-sourced tables, nonsense for a number read out of the binary.

## The manual section

The section renders **three** tables — Unit Enchantments (21), Temporary Statuses (13), Combat
Boosts — matching the engine's own taxonomy rather than a convenient grouping. Its tab lives in the
**Units & Heroes** group (user, 2026-08-24), after *New Abilities*; the body is emitted in the same
position so reading order matches the tab bar.

`read_enchantments()` calls `re_tools/enchant_mods.py` against **both** binaries — the live DLL for
the Ziggurat column and `AoWEPACK_original_backup.dpl` for the vanilla one — so the page's existing
compare switch works on the new section for free. No number is written by hand.

The extractor is **hierarchy-driven, with no hardcoded class list**: it enumerates every VMT
(class-name ShortString → the dword pointing at it is `vmtClassName` → VMT base = that + `0x20`),
walks ancestry via `vmtParent` at **VMT−0x18** (a pointer TO the parent's VMT pointer — deref
twice), and reads modifiers from the fixed stat slots **+0x5C ATK, +0x60 DEF, +0x64 RES, +0x68 DAM**.
A slot still holding `TAbility`'s own `33 C0 C3` means "no modifier". Add an enchantment to the game
and it appears in the manual with no edit here.

⚠ Traps the extractor has to handle, all of them live in this binary:

- **Two getter encodings**: `B0 nn` (`mov al`) and `83 C8 nn` (`or eax`, sign-extended — Poisoned
  ATK/DAM, Fury DEF). A reader keyed on one silently reports garbage for the other, so
  `decode_getter` **raises** on anything it does not positively recognise rather than guessing.
- **Non-uniform immediate offsets** in the combat-boost adds: `80 44 24 dd nn` puts a displacement
  byte *before* the immediate. Reading `+3` there yields the displacement (3), not the value — that
  bug shipped once during this work and is why every row carries its own offset.
- **Duplicate copies**: most conditional bonuses exist in two strike tables. `combat_boosts()` reads
  every copy and **raises if they disagree** — a divergence means a partial re-tune.
- **Leadership has two storage schemes**: vanilla flat tables at `0x558E83E8/EC`, Ziggurat a
  per-level cave at `0x5580F0C0/C8`. Reading the cave from a pristine DLL yields zeros, so the
  extractor falls back — and slices the ramp to the ability's real **level cap** (read from
  `mov dword [esi+0x28], N` @`0x55766187`), because vanilla capped Leadership at ONE level and
  printing its raw 4-entry table as a ramp would claim a progression the game never offered.

## ⚠ Three verifiers were crying wolf — all three now fixed

`build_assassin.py`, `build_invis_penalty.py` and `build_ranged_slayers.py` all generate their cave
bodies ending `jmp <stock exit>` and then compare against the installed bytes. But
**`build_magebane.py` splices itself into those exits** (ts_melee → `0x558129C0`, ts_melee3 →
`0x55812A00`, cave_rng → `0x55812A40`), so no generated variant could ever match and two of the
three reported a FALSE `[x]` for months:

- *"holds neither the v1 True-Seeing body nor ours"* (invis)
- *"has our prologue but no `jmp 5576EB39` terminator — refusing to guess its extent"* (ranged)

Both now accept the stock exit **or** a known chain exit, report `[chain] … exit kept at …`, and
re-terminate the body they write so the chain survives a re-tune. `build_assassin.py` had already
been given the same `preserve_terminator` helper. **A verifier that cries wolf is a defect** — it
trains you to ignore the one time it is right.

⚠ Rebinding a module-level cave body inside `process()` needs an explicit `global`, or the earlier
reference in the same function raises `UnboundLocalError`.

## ⚠ Parent-manifest coupling

Every byte the re-grade moves is also a row in `fivepct_manifest.json` and/or `damhp_manifest.json`,
whose verifiers accept only "recorded live" or "recorded target". `build_buff_regrade.py` therefore
rewrites those rows' `newValue` on apply and restores them on undo (the
`build_marksmanship_atk2.py` precedent). Two rows need more: re-grading +2 → **+1** lands the byte
back on the pre-doubling value, which `build_statdouble.py` counts as *at-live* and reports as a
DESYNC. Those rows are flipped to `UNCHANGED` while the re-grade is installed — a verifier that
cries wolf is a defect, not a nuisance.

## Description texts

All 62 affected strings in `Ability.pfs` / `Spells.pfs` were re-derived and applied via
`build_pfs_typos.py`.

⚠ **Two structural lessons paid for here:**

1. **Resolve by RECORD ID, not text uniqueness.** Three blessing descriptions are near-identical
   ("Increases the unit's Defense (+N) and Resistance (+N)" / "Gives the unit increased …"). An
   earlier pass matched them by text and mislabelled two: Nature's Blessing got High Prayer's
   numbers. The ids settle it — Blessed `0x9E`→rec 168, High Prayer `0x64`→rec 110, Nature's
   Blessing `0x63`→rec 109 (record id = ability id + 10).
2. **`FIXES` rows must be ONE FULL-TEXT ROW PER FIELD.** The table had accumulated *chained* rows
   (the doubling edited a description, the re-grade edited it again); after both applied, neither
   row could find its `old` or its `new` and the script refused. Naive "collapse consecutive rows"
   is also wrong — several records hold **independent** edits (Marksmanship's record has eight level
   strings; Charm's has a typo fix *and* a power number), and merging those destroys edits. The
   table is now rebuilt as one row per record/tag, `old` = the whole field at the `.pre-typos`
   baseline, `new` = the whole field now. Round-tripped: `--undo --apply` restores both files
   byte-identically to their baselines, and re-applying restores every edit.

## Verified in-game (2026-08-24)

The user confirmed this works in-game ("Write this all up as working"). The checks that
confirmation covers:

0. The **Unit Enchantments** tab lists 21 enchantments, 13 statuses and 7 combat boosts, and the
   vanilla/Ziggurat switch flips every number.
1. Blessed and High Prayer Blessing both read **+1 DEF / +3 RES** on the unit card, but only
   Blessed can be dispelled.
2. A unit under Bloodlust reads +3 attack / +3 damage / −2 defence; Fury +5/−2; Stone Skin +3.
3. A Monster Slayer's bonus vs monstrous units reads +5, and Charge +5 on the opening strike.
4. Ability/spell description numbers match what the unit card computes.
5. The manual's **Unit Enchantments** tab matches the game, and its vanilla/Ziggurat switch works.
