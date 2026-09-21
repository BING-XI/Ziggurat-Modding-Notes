# Engine internals — item system, save/data formats, and shelved analyses

This file covers everything that is a **mechanism or a file format**, not a single game feature: the
item system (equip slots, the two ability-query APIs, scrolls, item-granted HP/MV), the property-table
serialisation format shared by every `.pfs`/save/map container and its CRC, the `.mld` text-dictionary
rename mechanism, the Mind Decay multiplayer-determinism fix, and the shelved stack-size-12
investigation together with the vanilla bugs it turned up. It does **not** cover combat maths or the
RNG rule (`01-combat-maths.md`), unit spellcasting (`06-unit-spellcasting.md`), or any single-cave
ability/spell mod (`02-/03-abilities-*.md`, `04-/05-spells-*.md`) — this one holds what several other
features all had to learn about the engine underneath them.

## Status table

| feature | status | owning script | binary |
|---|---|---|---|
| Item system (shared RE: `TItem`, ability-query APIs, equip slots) | reference material | — | — |
| Scrolls — restore as playable data | SPECULATIVE (nothing authored) | none (data-only) | `Release/ITEMS.PFS`, `ITEMGFX.PFS` |
| Scroll as a permanent per-hero spellbook grant | 🔨 APPLIED, UNTESTED (2026-07-31; cave extended 2026-09-03) | `build_scroll_spellbook.py` | `AoWz.exe`, `AoWzCompat.exe`, `AoWEPACK.dpl` |
| Scroll icon fix (retype `ITEMGFX.PFS` 316–319) | 🛑 **DO NOT APPLY** — confirmed harmful in-game (2026-08-01) | `build_scroll_gfx.py` | `Release/ITEMGFX.PFS` |
| Scroll "cast once" alternative design | SPECULATIVE, not built | none | `AoWEPACK.dpl` |
| Item ability fixes, 4 groups (Healing/Dispel owner, ranged item-aware, immunity/protection/movetype, flat ATK/DEF/DAM/RES bytes) | 🔨 APPLIED, UNTESTED (2026-08-02) | `build_useitems.py` | `AoWEPACK.dpl`, `AoWDevEd.exe`, `AoWEd.exe` |
| Item-granted ability usable from the overland unit window | ✅ CONFIRMED WORKING (2026-08-28) | `build_unitwin_ability.py` + a dispatch fix inside `build_spellcast_multiturn.py`'s `cave_tiergate` | `AoWz.exe`, `AoWzCompat.exe`, `AoWEPACK.dpl` |
| Turn-event re-check gate (Healing/Dispel Magic) | ✅ CONFIRMED WORKING (2026-08-28) | `build_abilityte_itemgrant.py` | `AoWEPACK.dpl` |
| Healing per-turn re-arm | ✅ CONFIRMED WORKING (2026-08-28) | `build_healing_rearm.py` | `AoWEPACK.dpl` |
| Item-granted HP / MV bonuses | 🔨 APPLIED, UNTESTED (2026-08-31) | `build_item_hpmv.py` + `build_item_hpmv_data.py` | `AoWEPACK.dpl`, `User/Zig.ail` |
| Item HP/MV via the ability system instead (Route 2) | SPECULATIVE, not built | none | `AoWEPACK.dpl` |
| Item banner shows Hits + Moves (two more icon+value pairs) | 🔨 APPLIED, UNTESTED (2026-09-13) | `build_itembanner_hpmv.py` — full record in `07-ui.md` §9 | `AoWz.exe`, `AoWzCompat.exe` |
| Renaming spells / abilities / UI text | ✅ CONFIRMED WORKING (2026-08-29) | `build_resstr_names.py` | `Dict/ResStr.mld`, `Dict/ResStr.txt` |
| `.pfs` string/typo edits (generic tool) | tool, not a feature | `build_pfs_typos.py` | any `.pfs` |
| `Unitres.pfs` ability-record-list repair | ✅ CONFIRMED WORKING (2026-08-14) | `build_unitres_reclist.py` | `Release/Unitres.pfs` |
| Mind Decay — MP determinism + nil-check | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_minddecay_oos.py` | `AoWEPACK.dpl` |
| Stack size 8 → 12 | SPECULATIVE / **SHELVED** (2026-08-16, owner decided against it) | none | `AoWEPACK.dpl`, `AoWz.exe`, `AoWzCompat.exe`, `AoWTCPCK.dpl`, `AoWDevEd.exe`, `AoWEd.exe` |
| `TGeneral` slot-array overflow (vanilla bug, found while researching the above) | SPECULATIVE — fix fully specified, nothing built | `build_generalslots.py` (does not exist yet) | `AoWz.exe`, `AoWzCompat.exe` |
| Movement-predictor fix (context only — see the booby trap below) | 🔨 APPLIED, UNTESTED (2026-07-05, never retested) | `build_patch.py` — **never re-`--apply`** | `AoWEPACK.dpl` |
| Seduce / Charm / Dominate → two stacks on one hex | SPECULATIVE — mechanism diagnosed (v2), unconfirmed in-game | none | `AoWEPACK.dpl` |
| Transport-boarding "units vanish" bug | SPECULATIVE — static analysis only | none | `AoWEPACK.dpl` |
| Map/save instances are frozen ability snapshots | informational — ruled "not a bug" | none | `.hsm` / `.asg` / `.csm` |
| Firmament map level (a 4th map level, index 3) | 🔨 APPLIED, UNTESTED (2026-09-06) — DLL half, v2; editor New-Map dialog and the map-gen tools still to do | `build_maplevel4.py` (v2), plus in-place re-tunes of `build_shipyard_income.py` and `build_waterheal.py` (v6); UI half `build_skylevel_ui.py` | `AoWEPACK.dpl` (+ `AoWz.exe`/`AoWzCompat.exe` for the UI half) |
| Registry isolation — own settings tree, so a Ziggurat install can sit beside vanilla | 🔨 APPLIED, UNTESTED (2026-09-09) | `build_regiso.py` | `AoWEPACK.dpl`, `AoWSetup.exe` |
| AoWSetup install-check `'.'` fallback (companion to the above) | ✅ CONFIRMED WORKING (2026-09-09) | `build_aowsetup_installcheck.py` | `AoWSetup.exe` |
| Ziggurat exe icon — purple, mirrored | 🔨 APPLIED, UNTESTED (2026-09-09) | `build_icon_purple.py` | `AoWz.exe`, `AoWzCompat.exe` |
| Overlay layout — Ziggurat runs entirely out of `Ziggurat\` over a vanilla root | 🔨 APPLIED, UNTESTED (2026-09-09) — launch-verified, not yet played | none (no patch needed; registry only) | `Ziggurat\AoWz.exe` + registry |
| Ziggurat-oriented editor, purple hexes | 🔨 APPLIED, UNTESTED (2026-09-09) — launches, no map opened | `build_zigeditor.py` | `Ziggurat\AoWzEd.exe` |

## ⚠⚠ Booby traps — read before running anything in this file

**Never run `build_patch.py --apply`.** It is the AoW1 **movement-predictor** fix (three hooks:
`TMoveArmyTE.Setup@0x55747B01`, `MoveArmyEx@0x5574A36E`, `TSelectedArmy.Update@0x557936A3`, cave at
`0x5580D700`) — not a stack-size script, despite being easy to reach for while chasing stack-size or
double-stack bugs. At the bottom of its `--apply` path, unconditionally, it runs
`shutil.copyfile(DPL, BACKUP)` where `BACKUP` is `AoWEPACK_original_backup.dpl` **in the game root —
the pristine vanilla reference**. This runs even when every patch site already reads "ALREADY PATCHED"
(the mismatch abort only fires on a genuine byte disagreement), so re-running `--apply` on an
already-applied install still overwrites the pristine backup with whatever the current, heavily
layered DLL happens to be. **It also has no `--undo`.** Verified 2026-09-03: the pristine backup is currently intact, and
this script is confirmed to be the movement-predictor fix, not anything to do with stack size — say so
plainly so this isn't re-derived. The live cave at `0x5580D700` is additionally a later PIC build the
script itself can neither verify nor rebuild (see the Seduce/Charm/Dominate section below), so treat
it as **applied, frozen, and untouchable** — analysis only from here on.

**Never run `build_scroll_gfx.py --apply`** (or re-apply it if it is ever found applied). Retyping
`ITEMGFX.PFS` records 316–319 from `itUse` (6) to `itScroll` (5) is **confirmed harmful in-game
(2026-08-01)**: blank hero portrait, no spell icons, every spell cost displayed as nonsense (1, 5, 0)
— with no error dialog — for reasons not pinned down (`TItemGFX+0x20` is read by more than
`FindItemTypeGFX`'s type filter). Isolated by a clean single-variable A/B: reverting this one file,
cave untouched, made every symptom vanish. The script's own docstring now opens with a "DO NOT APPLY"
banner. If a scroll needs an icon, use one of the two untested alternatives instead — see
[Scrolls](#scrolls) below.

---

## The item system — shared reverse-engineering foundation

Everything below is read from the installed `AoWEPACK.dpl` (2026-07-30 / 2026-08-28 passes) and is the
foundation every item feature in this file builds on. Offsets are class-keyed; canonical copy is
`12-re-toolchain.md`. **Regular `TUnit`s never equip items** — only `THero`/`TLeader`, via
`THeroItems`. Every item→stat and item→use path therefore lives on `THero`.

### `TItem` object — VMT `0x5570FAFC`, instance size `0x4C` (76 bytes), parent `TAbilityOwner`

| off | type | meaning |
|---|---|---|
| `+0x14` | int | item instance id |
| `+0x18` | str | name/drop text (tag 8) |
| `+0x1c` | byte | flags, bit0 = activated |
| `+0x20` | int | `==1` marks a registered library item |
| `+0x24` | int | array-owner/owner index (tag `0x15`, default −1) |
| `+0x2c` | int | obtain value (tag `0x13`; `GetObtainValue` = `max(+0x2c,10)`) |
| `+0x30` | str | library id/name (tag 9) |
| **`+0x34`** | byte | **item type 0–7** (tag `0xF`) |
| **`+0x38`** | int | **spell id**, for useable items (tag `0x14`) |
| `+0x3c` | TStringList | ability list |
| `+0x40` | int | item gfx index, −1 = "use type default" (tag 7) |
| `+0x44` | ? | unused spare (tag `0x10`; written, read by nothing in the use path) |
| `+0x45` | byte | rarity / random-gen weight (tag `0xA`) |
| **`+0x46`/`+0x47`/`+0x48`/`+0x49`** | byte | **ATK / DEF / DAM / RES bonus** (tags `0xB`/`0xC`/`0xD`/`0xE`) |
| `+0x4a`, `+0x4b` | — | **free, zero-init** — claimed by the HP/MV feature below |

`TItem.ReadWrite@0x557945c8` full tag map: `7→+0x40, 8→+0x18, 9→+0x30, 0xA→+0x45, 0xB→+0x46 ATK,
0xC→+0x47 DEF, 0xD→+0x48 DAM, 0xE→+0x49 RES, 0xF→+0x34 type, 0x10→+0x44, 0x11→+0x14 id,
0x12→+0x3c abilities, 0x13→+0x2c obtain value, 0x14→+0x38 spell, 0x15→+0x24, 0x16→+0x28`.
**Last tag is `0x16`** — `0x17`+ is free (claimed by HP/MV, below). Byte fields go through the reader
`stream.vtable[0x30]`.

### Item type enum and equip slots

`TItemTypes` RTTI name table ships in AoWEPACK.dpl CODE at VA `0x55708C50` (file `0x8050`):

| value | name | equip slot | count in `ITEMS.PFS` |
|---|---|---|---|
| 0 | `itHead` | 1 | 8 |
| 1 | `itTorso` | 4 | 14 |
| 2 | `itAttack` | 0 | 28 |
| 3 | `itDefense` | 2 | 14 |
| 4 | `itRing` | 3 | 9 |
| **5** | **`itScroll`** | `0x0F` = none | **0 — cut content, see [Scrolls](#scrolls)** |
| 6 | `itUse` | `0x0F` = none | 10 |

Two tables govern placement, **and they are not inverses**: `GetItemTypePosition@0x55786740` reads
type→default-position at `0x558e8db8` (`01 04 00 02 03 0f 0f`); `GetPositionItemType@0x55786734`
reads position→required-type at `0x558e8db0` (`02 00 03 04 01 04`). Decoded: pos0 `itAttack`, pos1
`itHead`, pos2 `itDefense`, pos3 `itRing`, pos4 `itTorso`, **pos5 `itRing` again — the hero's second
ring slot**, reachable only by manual placement (`AutoPlaceItem` only tries the forward table's
position 3 for a ring). `THeroItems.CanPlaceItem@0x5578674c` requires `slot < 6` **and** the slot empty
**and** `GetPositionItemType(slot) == item.type` — **every equip position is type-locked; there is no
generic wearable slot.** Unequippable items (scrolls, use items) fall back through
`THero.AutoPlaceItem@0x5578901c` to `THeroInventory.GetFreeSlot` — the 8-slot backpack at `hero+0x74`,
distinct from the equipped aggregate `THeroItems` at `hero+0x70`.

### Two independent routes from item to hero stat (§0.4)

**Route A — four flat bonus bytes, equipped slots only (vanilla).** `THeroItems` exposes one
aggregator per stat, each summing one item byte across the equipped array:
`GetAttack@0x55786354`→Σ`+0x46`, `GetDefense@0x55786388`→Σ`+0x47`, `GetDamage@0x557863bc`→Σ`+0x48`,
`GetResistance@0x557863f0`→Σ`+0x49`. **No `GetHits`/`GetMoves` exist in this set** — the origin of the
HP/MV feature below. `THeroInventory` (the backpack) has **no** stat aggregators at all in vanilla.

**Route B — abilities carried on the item, equipped *and* use-slot.** Each `THero.GetX` getter also
loops every ability id via `THero.GetSuperlativeEnabledAbOwner@0x55788144` (self → equipped →
inventory) and adds that owner's per-ability term — `+0x68 GetAbAttack, +0x6c GetAbDefense,
+0x70 GetAbResistance, +0x74 GetAbDamage` (`TAbilityOwner` base impls). This is why e.g. an
Enchanted-Weapon item (ability `0x9A`) works from either slot type while its `+0x46` byte does not.

Hero effective-stat getters (clamps re-verified live 2026-08-31, `build_hero_clamps.py`):

| stat | getter (VMT) | formula | clamp | items |
|---|---|---|---|---|
| Attack | `GetAttack@0x55788360` (+0xC4) | res+0x24 + Σability + `THeroItems.GetAttack` + hero+0x6a | [0,40] | Route A¹ + B |
| Defense | `GetDefense@0x557883e8` | res+0x25 + Σability + items + hero+0x6b + morale | [0,40] | Route A¹ + B |
| Damage | `GetDamage@0x55788484` | res+0x26 + Σability + items + hero+0x1b | [2,40] | Route A¹ + B |
| Resistance | `GetResistance@0x5578850c` | res+0x29 + Σability + items + hero+0x6f + morale | [0,40] | Route A¹ + B |
| **Max HP** | **`GetHits@0x5578859c`** (+0xD0) | res+0x27 + hero+0x6d | [2,**100**] | **NONE (vanilla)** |
| **Max MV** | **`GetMoves@0x557885c0`** (+0xD4) | res+0x28 + hero+0x6e | [1,80] | **NONE (vanilla)** |

¹ **`build_useitems.py` changed the Route-A slot rule** (below): all four `THeroItems.GetX`
aggregators are now stubs into a shared cave that walks the worn list *and* the `itUse` backpack list,
so an `itUse` item's flat bytes now reach the hero too. `hero`'s HP ceiling was 120 (DAM/HP doubling)
and was lowered to 100 on 2026-08-31 to buy overflow margin — see the HP/MV trap below.
`THero`/`TLeader` VMTs both point at the same `GetHits`/`GetMoves` impls, so one hook pair covers
heroes and the wizard/leader; `TCombatUnit.GetHits@0x5572504c`/`GetMoves@0x55724fe0` read straight
through `[src+0x4c].vtable[0xD0]/[0xD4]`, so tactical combat and auto-resolve inherit any DLL-side fix
for free. `TAbstractUnit.NewTurn@0x55780d4c` opens with `SetMovePoints(GetMoves())` (MV lands on the
next refill) and then heals a fraction of `GetHits` (so an HP bonus also speeds healing).

### §0.6 ⚠ THE BIG ONE — two parallel ability-query APIs, only one sees items

The single most important fact for any item- or ability-related mod, and the root cause behind every
"the ability is on the item but nothing happens" report:

| query | self-only (`TAbilityOwner`) | item-aware (`THero`/`TAbstractUnit`) |
|---|---|---|
| has ability? | **+0x4c** `GetAbSet` → `TCustomAbilityList.GetAbSet@0x5574e0e0` | **+0x14c** `THero.GetAbilitySet@0x557882ac` |
| level | **+0x84** `TAbilityOwner.GetAbLevel@0x5574fd44` | **+0x144** `THero.GetAbilityLevel@0x5578831c` |
| enabled | **+0x88** `TAbilityOwner.GetAbEnabled@0x5574fd68` | **+0x148** `THero.GetAbilityEnabled@0x5578827c` |
| count | +0x54 `TCustomAbilityList.GetAbCount` | **+0x158** `THero.GetAbilityCount@0x55788114` |

`THero`/`TLeader` **never override** the low (self-only) slots — verified from the live VMTs. Both sets
funnel through `THero.GetSuperlativeAbOwner@0x557881dc` /
`GetSuperlativeEnabledAbOwner@0x55788144`, which pick the best owner across
**self → `THeroItems`(+0x70) → `THeroInventory`(+0x74)**. On `TUnit`/`TItem` themselves the low set is
correct, because those classes *are* the ability owner. A third, deliberately items-blind accessor
exists too: `THero.GetUnitAbilityEnabled@0x5578810c`, used where only innate abilities should count.
`TCombatUnit` forwards through the strategic unit: **+0xa8 GetAbilityEnabled@0x55725004** is
nil-guarded on `[cu+0x4c]`; **+0xb0 GetAbilityLevel@0x55725028 is NOT** — legal only directly behind an
`+0xa8`-family gate on the same object (a nil-guarded family degrades safely to 0 on a wall; the naked
`+0xb0` does not).

### §0.7 Equipped vs. use-slot — what an item can and cannot grant (vanilla)

`THeroInventory` implements only the *ability* half of the protocol and gates every method on
`item.type == 6`; `THeroItems` runs the same loops with **no type gate**:

| grants | equipped (0–4) | backpack `itUse` (6) | backpack `itScroll` (5) |
|---|---|---|---|
| Abilities | YES | YES | **NO** — gate is `==6` |
| ATK/DEF/DAM/RES bytes | YES | NO — no aggregator | NO |
| ATK/DEF/DAM/RES via a carried ability | YES | YES (Route B) | NO |
| Immunity / Protection / Move types | YES | NO | NO |
| Max HP / Max MV | NO (nothing reads items) | NO | NO |

### §3.0 Why `itUse` behaves differently — a bitmask handshake, by design

Ability *acquisition* is gated by `TAbility.CanExpand@0x5574e8b8`:
`(owner.GetAbilitySelectionTypes() & ability[+0x20]) != 0`, rejecting an ability the owner already
has. Owner masks: `TAbilityOwner` base `0x0000`; `TAbstractUnit` (all units) **`0x0001`**; `THero`
**`0x0200`**; `TItem` — one bit per type: Head `0x0002`, Torso `0x0004`, Attack `0x0008`, Defense
`0x0010`, Ring `0x0020`, **Use `0x0040`**, **Scroll → the `default:` arm = `0x0000` — no ability may
ever live on a scroll**, which is exactly why `THeroInventory`'s gate is `==6` and not `>=5`.

Every ability class carrying bit 6 (dump with `re_tools/abmask.py --use`) is **activatable/targeted**
— touch/ranged/web/entangle abilities, Wall-Crushing, **Healing `0x2F` and Dispel Magic `0x3C`**, Turn
Undead. Passive stat-shaped abilities (Marksmanship, Vision, Immunity, Protection, Movement,
Strike) are explicitly excluded from `itUse` and routed to the wearable slots instead. The installed
`ITEMS.PFS` agrees exactly — all 10 `itUse` items carry one active ability each, zero passives — strong
confirmation the rule was actually followed, not incidental.

**⚠ …but the mask is never enforced at runtime for items.** The enforcer,
`TAbilityOwner.ValidateOwnerTypeAbilities@0x5574f154`, has **exactly one caller**:
`TUnitResource.ReadWrite@0x55784f5e`. Nothing ever validates a `TItem`. So an ability the mask forbids
on an item is kept and silently ignored (no consumer sees it), not stripped — and an ability the mask
*allows* is not thereby guaranteed to work (Marksmanship is declared legal on Head/Torso/Defense/Ring
yet was invisible there too, until §3.1 below). The mask states intent; it neither strips illegal
grants nor guarantees legal ones function — check both sides before trusting either.

### Hero ability acquisition — the level-up mask gate, and a vanilla Expand defect (2026-08-28)

A **second**, level-up-specific mask handshake, surfaced while adjudicating Inioch's
`build_item_healing_daily.py`. `THeroUpgradeDlg`'s available-abilities fill requires **both**
`TAbility.CanExpand(hero)` (as above) **and** the ability's own selection-type bit `0x0100`
(`astHeroUpgrade`, tag 9 in `Ability.pfs`) — so a hero needs `0x0100` **and** `0x0200` together. In
the shipped `Ability.pfs` all 102 abilities carrying `0x100` also carry `0x200`; the two gates never
disagree in practice. ⚠ Never read the DLL's `ExpandCost` as evidence of purchasability —
`TDispelMagicAbility.ExpandCost@0x5576D130` returns 5 and is dead code on the level-up path.

A real, **vanilla**, byte-diff-confirmed defect exists in `TDispelMagicAbility.Expand@0x5576D180`: its
record-present arm increments the stored level but never sets the ability *bit* — so a call can
silently bump a level with zero visible effect. It is **unreachable in normal play** (every caller of
`ExpandAbility` was enumerated; both purchase screens are mask-blocked, and every spell/mastery/damage
route passes a hard-coded non-`0x3C` id). ⚠ One plausible-but-unconfirmed exception: AoWDevEd's
`TAbilitySelectionDlg`/`THeroEditForm` "Add" click calls `ExpandAbility` with **no mask test**, and
`Astra`/`Druid`/`Necromancer`/`Hydra` already carry Dispel Magic level records with no bit set — an
editor click on one of those could reproduce it. Needs a live probe of the dialog's owner class; not
done. ⚠ **`ExpandAbility` does not call `CanExpand`** — every caller must gate itself, which matters
for any future "let the AI learn more skills" patch. Data anomalies noted in passing in `Unitres.pfs`
(none patched): the four Dispel Magic records above; Highman Chariot's bitless Turn Undead record;
Carrack gold's corrupt tag-`0x32` sub-record.

*(Tool-bug note, so it isn't hit twice: `re_tools/pfs.py`'s `tags` CLI once ignored
`Ability.pfs`/`Spells.pfs`'s no-classid shape, returning `0 tags` or a parse error for some records.
Reading that silence as "no tag 6" flipped an early draft's conclusion about Healing vs. Dispel Magic
purchasability exactly backwards. Fixed; **a record that reports zero tags or fails to parse is a
parser mismatch, not an empty record.**)*

---

## Scrolls

### Verdict: cut content, not missing code

`itScroll` (item type 5) is a **complete, shipped feature with zero data**: engine, in-game UI, editor
authoring UI and artwork are all present; the only reason no player has ever seen one is that
`Release/ITEMS.PFS` contains **zero** type-5 items, plus one deliberate one-byte lockout in the
random-item generator.

**What a scroll does in the shipped engine: a one-shot spell *tome*, not a cast.** `TItem.Use` → a
networked `TItemTE` token → `TItem.ExecuteUse@0x55793f68`: if `type==5`, calls
`TPlayerMagicControl.ExecuteSpellResearched` (permanently researches the spell for the *player*), then
**frees the item** (one-shot consume). `TItem.CanUse@0x557940ac` requires `type==5 && spell!=0 &&`
not already researched.

**The in-game UI is wired but its panel may be dead** *(open item, needs one in-game check)*.
`TUnitWindow`'s `ItemUsePnl` (AoW.exe, field `+0x160`) is declared `Visible=False` in the DFM (file
`0x1F3EB2`, value byte `0x08`=`vaFalse` at `0x1F3EBD`) and **no code anywhere in AoW.exe touches
field `+0x160`** — so the Use button's parent panel probably never becomes visible even with a scroll
selected (`TAOWBaseWindow.DrawSurface` early-outs on an invisible parent before walking children).
Verification is cheap: author a scroll, select it, see whether a Use button appears. If not, the fix
is either the DFM byte `0x08→0x09` (risk: the panel covers the unit window — `Alignment.AlignWidth =
awBoth`) or extending the handler at `0x40A65D`/`0x40A66C` to toggle `+0x160` alongside `+0x164`.

**The editor already authors scrolls with no patch needed** — `EItem.TItemEditForm` (AoWDevEd.exe /
AoWEd.exe): the type combo's 6th entry is literally "Scroll", picking it sets `item+0x34=5`, a
`ScrollPnl` with a spell combobox appears (writing the picked spell's id into `item+0x38`), and the
ATK/DEF/DAM/RES panel hides for that type.

**Artwork ships but is registered under the wrong type.** `Images/ITEMS/I_Scroll.ILB` exists;
`Release/ITEMGFX.PFS` registers 4 scroll icons as records 316–319 — but their type tag (tag 8) reads
**6** (`itUse`), and there is no type-5 gfx record at all, so a freshly authored scroll gets gfx index
−1 (no icon) until this is fixed. **Do not fix it by retyping those four records** — see the booby
trap above; use the item's own gfx index (`item+0x40`, tag 7) or append new type-5 records instead.

**`itAll` masks the scroll bit out of random generation** — the clearest evidence this is deliberately
cut, not merely unauthored. `TItemControl.GenerateItem`'s two callers (item hotspots, exploration-site
loot) both filter by the global set `AoWE.itAll` (VA `0x558E803C`, file `0x1E6E3C`), whose live value
is `0x5F` = `{Head,Torso,Attack,Defense,Ring,Use}` — bit 5 (Scroll) cleared. `0x5F → 0x7F` restores it;
one DATA byte, no cave, no relocation. Skip this if scrolls should be hand-placed only.

**Restoring scrolls (dependency order, all data-only, none done yet):** (1) author type-5 items in
`Release/ITEMS.PFS` or `User/Zig.ail`; (2) retype `ITEMGFX.PFS` 316–319's tag 8 from 6→5 **only via a
route other than the confirmed-harmful one**, or leave scrolls iconless; (3) `itAll` byte, optional;
(4) verify the `ItemUsePnl` defect above — *irrelevant if [the spellbook-grant redesign](#scroll-as-a-permanent-spellbook-grant) below is what ships*, since that redesign disables the vanilla Use path entirely.

### Cast variant — making a scroll cast once instead of teaching (alternative, SPECULATIVE, not built)

Not what shipped (see below), kept as a design alternative. Casting = `TSpellControl.GetSpell(id)` →
`spell.CanActivate(caster,&msg)` (vt+0x68) → `spell.Activate(caster)` (vt+0x6c); calling these directly
bypasses the mana/casting-points/research gate `THero.CanCastSpell` normally enforces — exactly what a
free one-shot wants. Sketch: in `ExecuteUse`'s `type==5` branch, replace the
`ExecuteSpellResearched` call with `GetSpell`→`CanActivate`→`Activate`, gating the item's one-shot free
on `CanActivate` succeeding; in `CanUse`, drop the "already researched" rejection. Open risk: which
spells resolve cleanly outside a target-selection UI (strategic self/global spells should; combat-only
or targeted spells hit the same castability constraints unit-spellcasting documented elsewhere); the AI
never calls `UseItem` at all (UI-only), so this is human-player-only regardless.

### Scroll as a permanent spellbook grant

**Status: 🔨 APPLIED, UNTESTED.** Original build 2026-07-31; the shared cave was **extended again
2026-09-03** for an unrelated ruling (below) — nobody has tested either state in-game yet.

| | |
|---|---|
| build script | `build_scripts/build_scroll_spellbook.py` |
| binaries | `AoWz.exe`, `AoWzCompat.exe` (cave in `.sc`), `AoWEPACK.dpl` (3 gate bytes) |
| revert (drop everything, both this feature and the 2026-09-03 hero-tier ruling) | `python build_scripts/build_spellcast_herotier.py --undo --apply` (DLL first) **then** `python build_scripts/build_scroll_spellbook.py --undo --apply` (exes second) |
| revert (drop only scrolls, keep the 2026-09-03 hero-tier exemption) | **not possible via `--undo`** — re-apply this script with `--append-upto=0` instead, which keeps the current (hero-exempt) prune and emits no scroll append |

**Behaviour:** while a hero *carries* an `itScroll` item, that item's spell (`item+0x38`) appears in
*that hero's* spellbook and is castable even though the player hasn't researched it — nothing is
consumed, nothing becomes globally known, drop the scroll and the spell goes with it. Design decisions
(user, 2026-07-30): the tier gate is **retained** for scrolls (`TSpell+0x21 <= hero's Spellcasting
level`); **Spellcasting heroes only** (explicit `level != 0` test, belt-and-braces —
`GetCastingPointsMax` already returns 0 without the ability).

**Why it works at all — research is a book-only concept.** `TPlayerMagicControl.ListSpells` *is* the
researched-id list; neither `THero.CanCastSpell`/`CanCastCombatSpell` nor the cast token ever consult
research. A spell only has to *appear* in the book; everything downstream casts it normally.

**⚠⚠ CROSS-FEATURE COUPLING (2026-09-03) — this cave now belongs to TWO features.**
`cave_bookfilter@0x0060C0A8` was originally the unit-spellcasting book filter
(`build_spellcast_book_exe.py`), absorbed verbatim when this script rewrote it in place 2026-07-30.
On 2026-09-03, per the user ruling *"Spellcasting level should only restrict tier of spell that's
castable for units, not heroes"*, this script's own stage-1 prune was changed to make the tier
restriction **unit-only**; the paired DLL-side half of that ruling
(`build_spellcast_herotier.py`, retargeting the 4 displacement bytes of the existing
`cave_tiergate` hook at `0x5578974E` to a new `cave_herotier@0x55846000` that lets heroes/leaders
skip the tier compare entirely) is a **separate, independent script** — full detail belongs in
`06-unit-spellcasting.md`, not here. What matters for this file: **`--undo` on this script silently
restores the OLD 130-byte filter, which re-tier-limits heroes too, with no error and nothing logged**
— see the revert table above for the two different intents.

**As built (2026-07-30, revised 2026-09-03) — `cave_bookfilter` rewritten in place, 130 → ~330 bytes,
inside `.sc`'s exhausted 344-byte span (0 bytes free after this build).** The five `TSpellBook →
ListSpells` call sites (`0x0042F0F9/0x0042F20C/0x00430D58/0x00430DDE/0x00430EDD`) were already
redirected here by `build_spellcast_book_exe.py` and are untouched — covering all three book tabs
(Combat/Unit/Global) with one cave. Stage 1 (the absorbed prune, now unit-only for the tier test) then
stage 2:

```
if !heroFamily || level == 0            -> done          ; Spellcasting heroes only
inv = [caster+0x74]; if !inv            -> done
n   = inv.vtable[0x54](inv)             ; THeroInventory.GetCount
for i in 0..n-1:
    item = items[i]
    skip unless [item] == TItem's VMT   ; ⭐ CLASS GUARD, see below — not a type-byte test
    skip if byte[item+0x34] != 5 or !dword[item+0x38]
    spell = TSpellControl.GetSpell(caster, item+0x38)
    skip if byte[spell+0x21] > level                     ; tier gate, retained
    skip if byte[spell+0x22] >= 8 or !(mask >> cat & 1)  ; book-tab category
    TSpellList.Add([&collector], spell)                  ; no dedupe (see below)
```
`TSpellList.Add@0x5577a03c` is not imported by the exe — reached via the runtime rebase-delta trick
(`dll_delta = [IAT slot for AoWE.AoWHSSet] − its preferred VA`, from `08-editor.md`),
avoiding the manual-append `TList` capacity edge case.

**The bug found by five rounds of in-game bisection (fixed, kept because the lesson generalises):**
the hero's inventory array can hold entries that are **not live `TItem` objects** — these engine lists
are sparse (removal is sparse-or-compacting), so a dead slot need not be NULL. The original scan tested
only `byte[entry+0x34]==5`, matched a stale slot, and fed a garbage id into `GetSpell`; the resulting
bogus `TSpell*` broke the book's icon draw and froze the game — **a poisoned list, not a crash**, so
every static check passed. Fixed by requiring the entry's **VMT** to equal `TItem`'s before touching
`+0x34` at all (`cmp [entry], 0x5570FAFC+dll_delta`), paid for by dropping the dedupe pass (`.sc` was
full) — the only cost is a scroll whose spell is *also* researched now appears twice in the book.
**⭐ Generalise: any cave that walks an engine list and identifies entries by a data byte is unsafe.
Identify by class first.** The bisect ladder that found it (`--append-upto N`, results in-game):
`0 prune only` ✅ · `2 +count+null` ✅ · `3 +array walk` ✅ · `4 +null+type-byte read` ✅ ·
`5 full` ❌ — narrowing the fault to exactly what N=5 alone adds.

**Consume-on-use killed.** Both vanilla type-5 gates retargeted to item type **7** (nothing uses it):
DLL `TItem.CanUse` `80 7e 34 05`→`07`; DLL `TItem.ExecuteUse` `8a 43 34 2c 05`→`07`; **[exe]**
`0x0040A657` `80 7f 34 05`→`07` (Use button never appears).

**Icons: still unresolved — do not retype `ITEMGFX.PFS`.** See the booby trap above; untested
alternatives are the item's own gfx index or appended type-5 records.

**Needs the user's in-game test (nothing here has been played):** author a scroll, give it to a
Spellcasting hero, confirm the spell lists unresearched and casts at normal cost on all three book
tabs; confirm a non-Spellcasting hero sees nothing, a scroll above the hero's Spellcasting level is
not listed, dropping the scroll removes the spell, and no Use button appears.

**Remaining gaps (both fixable, neither built):** **AI heroes get nothing**, for two independent
reasons — (1) acquisition: `build_ai_itempickup.py` only fills equip slots via `CanPlaceItem`, which
rejects scrolls outright (no equip slot); needs `THero.AutoPlaceItem` instead; (2) candidate list: the
AI's spell prefetch (`TCastSpellAIPA.PrefetchCastSpellActions@0x5577ba54`) builds its own list inside
the DLL and never runs the exe-side cave — but that function receives the hero, so the identical
`hero+0x74` scan could append there DLL-side with the in-module `TSpellList.Add`, no rebase-delta
trick needed (easier than the exe side). **MP:** the book is client-side but the cast token carries a
plain spell id the DLL executes with no research check, so peers stay in sync automatically.

---

## Abilities on items — why some do nothing, or misbehave

**Status: root causes confirmed by code against the installed binaries.** Two reports triggered this:
*"Healing on a use-slot item is infinitely castable in fast combat"* and *"Marksmanship on an item
does nothing"*. Neither is actually use-slot-specific — both trace to the same self-only/item-aware
API split (§0.6) and reproduce identically on an *equipped* item (5-minute in-game A/B: put
Marksmanship on an equipped Attack item and read the card — predicted still no bonus; put Healing on
an equipped item and fast-resolve a long combat — predicted also infinite; put a `+0x46` byte **and**
Marksmanship on the same `itUse` item — predicted neither shows, but a carried ability with its own
`GetAbAttack` term, e.g. Enchanted Weapon, does).

### Marksmanship — the ranged getters query the wrong pair, and are already hooked by something else

`TRangedAttackAbility.GetAttackRA@0x5576e65c`/`GetDamageRA@0x5576e614` both query the **self-only**
pair (`owner.GetAbEnabled`/`GetAbLevel`, +0x88/+0x84) with `owner` pinned to `[cu+0x4c]` — the source
unit, never an item. `hero.GetAbEnabled(0x20)` is false for an item-granted Marksmanship, so the whole
level ladder is skipped. **Affects equipped and use-slot items identically**, and is not
fast-combat-specific — `AoWTCPCK.dpl` (manual tactical combat) imports the same
`CreateRangedAttackCA` and is equally blind.

⚠ **This site is already hooked by a separate, pre-existing, previously undocumented rework**
(`cave_5580C240`) — the self-only `test/jz` at `0x5576E678` is NOP'd and `0x5576E689` already calls
that cave, which therefore receives level 0 for an item-granted Marksmanship and adds nothing. Fixed
inside `build_useitems.py` (below) by swapping `[ecx+0x88]`→`[ecx+0x148]` and `[ecx+0x84]`→`[ecx+0x144]`
— both already `call [ecx+disp32]`, so it is a pure displacement edit, no length change, no cave.

**⚠ The fix does have one real leak, audited and scoped.** A *passive* ability authored onto an
`itUse` item (Marksmanship's mask says "not legal on Use") would, after this fix, start working while
merely carried in the backpack — because the inventory gate only checks `item.type==6`, never the
ability's own legality mask (§3.0b). Today this is **zero-exposure**: every shipped `itUse` item
carries exactly one legal active ability. It only bites if someone later authors a passive onto a use
item; the guard, if ever needed, is `ability[+0x20] & 0x0040` added to the four `THeroInventory` gates.
The same decision point applies to the HP/MV feature's backpack arm below — Route 1 there deliberately
chose equipped-only to avoid exactly this asymmetry outside of `build_useitems.py`'s own scope.

### Healing and Dispel Magic — the once-per-turn flag is written to the hero, read from the item

Only two ability classes in the whole DLL have a `SetEnabled` at all — `THealingAbility@0x2F` and
`TDispelMagicAbility@0x3C` — and **both are broken identically**, so this is the complete bug class.
`GetEnabled` tests the self-only bit first (false, for an item grant) and then, only on that path,
checks a `TAbilityOwner` **data record** — `AddAbilityData`/`GetAbilityData` — and **if no record
exists, returns ENABLED**. `THealingCA.Execute` writes the spent flag to `[healerCU+0x4c]` — the
**hero** — while `THero.GetAbilityEnabled` (item-aware, what the fast-combat driver actually gates on)
resolves the highest-level owner and finds the **item**, which never got a record written to it.
⇒ **the flag is written to one object and read from another, so it never latches — one heal per round,
forever.** `NewTurn`'s own refresh path is separately gated `IsClass(owner,TAbstractUnit)`, so even a
record created on the item would never be reset by it.

**Deeper still: items never get per-turn upkeep at all, for a second, independent reason** — the
new-turn/new-day broadcast never reaches a carried `TItem` in the first place.
`THero.MsgProc`/`TAbstractUnit.MsgProc` run the ability-trigger chain **on the hero only** and never
forward to `hero+0x70`/`+0x74`; `TItemControl` is a plain `TEObject` with no `MsgProc` override and
does not fan out to its registered items; the map's broadcaster hits six explicit control lists, none
of which include carried items. `TItem.MsgProc` *chains into* the trigger and looks fully wired — it
is simply never sent the message. **Generalisation: any per-turn/per-day ability state on an item is
dead in this engine** (`TDurationAbility.NewTurn`/`TUnitEnchantmentAbility.NewTurn` tick the same way —
an item-carried duration ability would never expire either). There is a two-hop back-pointer from item
to hero (`[[item+4]+4]`, guarded by an `IsClass` check on the container) that would make "read the flag
from the item's holder" a real fix option if this is ever revisited; not built.

### The four-stage fix chain — item-granted ability usable from the overland unit window

**Status: ✅ CONFIRMED WORKING (2026-08-28), all four stages, verified in-game by the owner.** Kept in
full because each stage's symptom was only visible once the previous stage's fix was live — this is
exactly the "chain, not a bug" shape worth remembering for any future item/ability report.

**Symptom 0.** A hero with no *innate* Spell Casting, wearing/carrying an item that grants it, sees the
ability **listed** in the overland unit window (that list is built through the item-aware
`ListAbilityInfo`) — but double-clicking it does nothing. ⚠ Two independent DFM bindings reach
`UseAbility` (the button's `OnClick` **and** the ability listbox's `OnDoubleClick` on all three window
variants); a code-xref scan sees only the button and had (wrongly) called an earlier patch attempt
"inert" — DFM bindings resolve by name and are invisible to that scan. The list row is what you click;
the button's visibility is irrelevant on that route.

| stage | reported after | root cause | fix | script |
|---|---|---|---|---|
| 1 | (initial report) | `TUnitWindow.UseAbility@0x00409EF7` gates on the **self-only** `ability.vmt+0x74`, with no item leg at all | one site hooked → 27-byte cave `0x0062D000` in `.hcol`; runs the original virtual first, falls back to item-aware `+0x148` only on false | `build_unitwin_ability.py` (AoWz.exe + AoWzCompat.exe) |
| 2 | spellbook now opens, but casting a listed spell still silently fails | `cave_tiergate` (`build_spellcast_multiturn.py` M2, in `THero.CanCastSpell`) fetched the caster's Spell Casting level via a **static call to the BASE `TAbstractUnit.GetAbilityLevel`**, bypassing `THero`'s item-aware `+0x144` override entirely — item-granted level resolves to 0, every spell fails `level>=tier`, fail arm returns with no message | dispatch through the vtable slot instead of calling the base statically (+1 byte, re-tuned in place) | `build_spellcast_multiturn.py` (DLL) |
| 3 | Healing: "I can issue a heal order but it does nothing" | `Activate` only opens targeting; the actual apply runs in a **turn event** (`THealingTE.Execute`/`TDispelMagicAbilityTE.Execute`) which re-resolves the ability and **re-tests the same self-only gate** a second time | one shared 27-byte cave `0x55818240`, same run-original-then-fall-back-to-`+0x148` shape, on both TE `Execute`s | `build_abilityte_itemgrant.py` (DLL) |
| 4 | Healing works once, then sticks at "Healing (used)" forever | `TAbilityOwner.TriggerNewTurn` enumerates **self-only** (`GetAbCount`/`GetAbSet`) to decide which abilities get `NewTurn()` — the hero holds the per-turn-flag *record* but not the ability *bit* (that's on the item), so `THealingAbility.NewTurn` is never invoked with the hero | re-arm via the hero's **data-record chain** directly (`owner+0x10` list, walk via `GetAbilityID` to the `0x2F` record, `record+0xC=1`) — no ability object, fully PIC | `build_healing_rearm.py`: `E9` hook on `TriggerNewTurn`'s prologue → 44-byte cave `0x55818260` |

**Revert, in reverse-stage order** (each is a separate script; undoing out of order re-exposes the
symptom the later stage was written against, though it does not corrupt anything): `python
build_scripts/build_healing_rearm.py --undo`, then `build_abilityte_itemgrant.py --undo`, then
`build_spellcast_multiturn.py --undo` (⚠ this also removes the M2 tier gate it was originally built for
— see that feature's own record before touching it), then `build_unitwin_ability.py --undo`. All four
are surgical and touch no backup.

Stage 1's script **aborts unless `build_useitems.py` P1's two `GetEnabled` hooks are present** — a
real coupling, not a suggestion. Stage 3's fix explicitly does **not** touch `GetEnabled` itself (it is
legitimately called with an item as owner elsewhere in the engine); it patches only the two call sites
where the receiver is known to be a unit. Stage 4's scope is **Healing `0x2F` only** by the owner's
ruling — Dispel Magic has identical machinery but nothing grants it yet; a one-byte `HEAL_ID` edit
covers it if that changes.

⭐ **The general trap from stage 2, worth more than the fix:** a cave that calls a base implementation
**statically** silently defeats every override of it — invisible to an ability-id census, because that
matches on the callee, not on how it was reached. The audit that finds it is a scan for direct calls to
a base method that some descendant overrides: across the whole live DLL there are exactly three, and
the other two are legitimate call-inherited legs inside `THero`'s own overrides.

⭐ **The general trap from stage 3:** an "activate" that resolves through a turn event has **two**
gates — one where the order is issued, one where it executes — and the second is invisible until the
first is fixed. A census of `[ability.vmt+0x74]` dispatches across all four modules found 13 sites;
after triage only two were apply-gates (two more are the identical blindness in the *name* text —
cosmetic, unpatched, and the likely reason an item-granted Healing never shows "(used)" in its name).

### Two propagation facts (2026-08-28, no patch needed — explains "the data changed but the panel didn't")

- **`TAbstractUnit.ListAbilityInfo@0x5577FA50` hands the *granting object* to the ability's name/text
  builder — for an item grant that object is the `TItem`, not the hero.** The overland unit window's
  ability list is item-aware for *membership* (which ids to show) but item-scoped for *identity* (whose
  name/description gets built) — the only slot in the whole census that returns an *owner* rather than a
  bool/level (`+0x154`, `GetAbilityOwner`). A decorator hook keyed on "owner is a `THero`" is silently
  skipped in this one panel while a panel using the merged hero-side query shows correctly.
- **`TAbilityOwner.UpdateDefaultAbilities@0x5574F518`** — the merge that reconciles the several live
  copies of a unit — **is bit-gated**: it skips any ability id the *source* doesn't have the set bit
  for, even though a bit-less data record legitimately exists and carries a level. A data record
  without its owner bit therefore **never propagates to any other live copy**, even though it survives
  save/load and direct assignment. Audited: none of this project's three participants in this function
  (`build_leadership_fix.py`, `build_leadership_aura.py`, `build_copper_medal.py`) depend on bit-less
  records reaching it, and nothing here mints one (`ExpandAbility`/`SetAbSet` always set the bit) — a
  documented vanilla trap, not a live defect. **Do not loosen this gate** if Inioch's (or anyone else's) patch
  proposes it — the medal/rank grant logic depends on controlling exactly which records propagate.

### Settled odds and ends (2026-08-28)

- Item ability *levels* are **data**, not evidence of a rule: sparse in vanilla `ITEMS.PFS` (2 of 83
  records carry a level sub-record) but routine in `User/Zig.ail` (61 items / 76 sub-records, three
  ClassIDs — `0x00022001` generic multi-level, `0x00022002`, `0x000202CE`). No item in either file
  grants Marksmanship.
- `THealingAbility.GetEnabled`/`TDispelMagicAbility.GetEnabled` are **already hooked by
  `build_useitems.py` P1** (`0x5576BF40`→cave `0x55815060`, `0x5576CE6C`→`0x55815070`) — any future
  change must extend that cave in place; a second 5-byte owner on either site would silently clobber it.
- Unverified, recorded as Inioch's claim only: the game may keep several live objects per hero
  (server/world, client/UI, transient window copies) beyond the strategic/`TFastCombatUnit` twins
  already documented elsewhere. Not confirmed. First thing to test with `re_tools/live_ui.py` if a
  future symptom looks like "the data changed but this panel didn't".

### As built — `build_useitems.py`

**Status: 🔨 APPLIED, UNTESTED (2026-08-02).** All four groups built and applied in one script.

| | |
|---|---|
| binaries | `AoWEPACK.dpl` (13 sites + one cave at `0x55815000`, reserved `0x600`), `AoWDevEd.exe` + `AoWEd.exe` (1 byte each, **located by an 11-byte signature, not by address** — the two editors are different builds and the itUse-grey gate sits at different offsets in each) |
| revert | `python build_scripts/build_useitems.py --undo` — surgical: restores all 13 sites + the editor byte, zeroes only its own cave, touches no backup |

| group | sites | mechanism |
|---|---|---|
| P1 — Healing/Dispel per-turn flag reads from the hero, not the item | `0x5576BF40`, `0x5576CE6C` | `jmp` to a stub re-issuing the displaced pair then calling a shared `resolve_holder`, returning past the original site |
| P2 — ranged atk/dam see item abilities | `0x5576E628/3B/70/83` | in-place disp32 edit, `+0x88→+0x148`, `+0x84→+0x144`, no cave, no length change |
| P3 — immunities/protections/movetypes | `0x55786470/C0/424` | full-function replacement: worn loop + a second `type==6` backpack loop |
| P4 — flat ATK/DEF/DAM/RES bytes | `0x55786354/88/BC/F0` | same two-pass replacement pattern |
| P4 authoring | `AoWDevEd.exe`/`AoWEd.exe` | the itUse grey-out branch's compared type `6→0x7F`, so `itUse` items get normal editable spinners |

**Why full-function replacement was safe:** every one of the seven `THeroItems` aggregators has
**exactly one caller** (verified by whole-module rel32 xref scan) — its matching `THero.GetX` — and
both `THeroItems+0x4`/`THeroInventory+0x4` hold the owning hero, so the cave reaches the backpack as
`[[this+4]+0x74]` with no new imports. **`resolve_holder`** (`0x55815000`, 90 bytes): `IsClass(owner,
TItem)` → `container=[owner+4]` → `IsClass(container, THeroItems|THeroInventory)` →
`[container+4]`; any failure falls back to the original owner unchanged (a `TUnit`, a map-lying
`TItemHS`, a library item all behave exactly as before).

**Deliberate scope decision:** the `THeroInventory` type gate (`item.type==6`) is kept — this widens
what a *use* item delivers without letting a spare helmet in the backpack do anything. The ability
legality mask (§3.0) is **not** enforced by this patch, on purpose — that is the point of the change.

**Needs the user's in-game test:** Healing/Dispel on a use item in long fast-resolve combat — heals at
most once per round, then stops until next turn; Marksmanship on a use item and on a Ring raises both
ranged attack and damage (the Ring path was broken in vanilla too); a use item with an
Immunity/Flying/Protection shows on the card and in combat; a use item with `+2 ATK` authored in the
editor raises hero ATK, and the editor's four stat spinners are no longer greyed for `itUse`;
regression — a spare helmet **in the backpack** still grants nothing, an equipped helmet is unchanged.

---

## Item-granted HP and MV bonuses

**Status: 🔨 APPLIED, UNTESTED (2026-08-31).**

| | |
|---|---|
| build scripts | `build_item_hpmv.py` (engine, `AoWEPACK.dpl` only) + `build_item_hpmv_data.py` (data, `User/Zig.ail`, 32 records) |
| revert | `python build_scripts/build_item_hpmv.py --undo` — surgical, byte-identical round-trip proven against its own backup |
| couplings | shares the `THeroItems` aggregator pattern with `build_useitems.py` (clones its cave at `0x55815080`, does not edit it); **must not** touch `build_medal_hpmv.py`'s separate `TUnit.GetHits` cave at `0x5580BE00` — different class, different feature, see below |

**As built — 3 hooks + 5 caves, span `0x5582B000..0x5582B200`:**

| site | VA | displaced | cave |
|---|---|---|---|
| `THero.GetHits` | `0x5578859C` | 6 B (`mov edx,[eax+0x40]; mov dl,[edx+0x27]`) + 1 NOP | `cave_gethits @0x5582B140` |
| `THero.GetMoves` | `0x557885C0` | 6 B (analogous) | `cave_getmoves @0x5582B180` |
| `TItem.ReadWrite` | `0x55794712` | 6 B (`mov eax,esi; mov edx,[eax]; call [edx]`) + 1 NOP | `cave_readwrite @0x5582B1C0` |

plus `agg_hp@0x5582B000`/`agg_mv@0x5582B0A0` (134 B each), cloned from `build_useitems.py`'s cave at
`0x55815080`: worn list, then the `item.type==6` backpack list. Storage `item+0x4A` HP / `+0x4B` MV,
**signed** (a cursed item can carry a penalty); persistence tags **`0x17`/`0x18`**, old-save-safe
(absent tags default to 0). The getter caves re-enter vanilla just above the clamp pair
(`0x557885A7`), so `build_hero_clamps.py` keeps sole ownership of the clamp immediates and the two
features compose independently.

**Reach, verified by construction:** `THero`/`TLeader` share VMT `+0xD0`/`+0xD4`;
`TCombatUnit.GetHits/GetMoves` forward through `[src+0x4c].vtable[0xD0]/[0xD4]`; `AoWTCPCK.dpl` makes
**74** calls through that slot. So strategic card, tactical combat and auto-resolve are all covered by
the two DLL hooks alone — no exe or TCPCK patch needed.

### ⚠ THE TRAP — the getter sums in 8 bits, and the sum was already near the ceiling

`GetHits` computes `add dl,[eax+0x6d]` as an **8-bit add**, only afterwards `movsx`-ing to a signed
16-bit compare against the clamp. `hero+0x6d` is the skill-point-purchased HP upgrade, and a maxed hero
sits at `base + 0x6d == ceiling`. **At the old 120 ceiling, an item bonus of just 8 overflowed** (128
wraps to −128, the floor clamp fires, the hero reads 2 HP). The HP ceiling was lowered 120→**100** on
2026-08-31 partly to buy this margin back — the wrap now needs a **+28** item — but the margin is not
the fix, only a bigger cushion; a strong item or a second additive term stacked on top walks straight
back into it, silently, only on high-level heroes. **So the cave does the arithmetic in 32 bits**
(`movzx` each term, add as dwords, clamp, return AL) rather than extending the 8-bit chain. `GetMoves`
has the same shape (ceiling 80, needs +48 to wrap) and got the same treatment. Same defect class as
`build_medal_hpmv.py`'s v2→v3 fix and the general DAM/HP-doubling lesson: **a clamp is a stricter
consumer than the byte store sitting in front of it — prove all 32 bits, or narrow explicitly first.**

### Three findings that cost real time — do not re-derive

1. **`TItem.ReadWrite`'s tail is not hookable.** At `0x55794726` the function overwrites the item
   pointer with the stream vtable (`mov ebx,[eax]`), so at the shared `ret`, EBX is the item on one
   path and a vtable pointer on the other. Hook the head (`0x55794712`) instead, where EBX is the item
   on both paths, and replay the displaced run inside the cave.
2. **The `.pfs`/`.ail` directory does not require ascending tag keys** — hooking before tag `0x16`
   would emit `0x17`/`0x18` out of order, and that's fine: **50 of 50** `HERORES.PFS` records and 2 of
   83 `ITEMS.PFS` records already ship non-ascending. The reader is a keyed scan, not a binary search.
3. ⭐ **A record's directory cannot be re-derived — only appended to.** Entry widths and order follow
   no rule recoverable from the data (`Zig.ail` record 12 stores one tag wide where a small entry would
   fit, with its other entries in neither key nor payload order). Because offsets are relative to the
   directory's *end*, appending is safe and moves nothing: copy every existing entry verbatim, append
   new ones. A first-cut "rebuild bodies small-if-it-fits" writer produced a plausible-looking, silently
   wrong file — caught only by its own self-test.

**Tag space in an item record:** `0x00-0x06` `TAbilityOwner` base; `0x07-0x16` `TItem`'s own fields
(`0x16` is the last vanilla writes); **`0x17-0x30` free** (`0x17` HP, `0x18` MV, this feature);
`0x31` the ability-id list the loader drives off; `0x32+` per-ability data sub-records. Neither `.ail`
nor `ITEMS.PFS` carries a magic header or CRC (unlike `Unitres.pfs`/`HERORES.PFS`) — never stamp one.

**The authored table (32 items in `User/Zig.ail`, user-signed-off):** **+MV** (6): Stolen Angel Wings
6, Invisibility Boots 6, Ethereal Boots 4, Windbearer Shield 4, Sphere of Wind 2, Ranger Boots 2 —
every one already carries a mobility ability. **+HP** (26): Robe of Life/Ring of Life Power/Elixir of
Life 12, Ring of Health/Ring of Regeneration/Amulet of Blood 4, physical armour tiered by obtain value
(≥100→6, 50–99→4, <50→2); robes/cloaks/tunics (the RES-bearing caster line) get nothing. ⚠ Pure
name-matching would have wrongly picked three items whose abilities are actually extra-attacks or a
snare, not mobility/vitality — resolve ability ids before extending the table, never trust the name.
⚠ **Six of the 32 are `itUse`** (Elixir of Life, Amulet of Blood, Sphere of Wind, and the Ethereal /
Invisibility / Ranger Boots — counted live in `Zig.ail` 2026-09-13) — their bonuses reach the hero only
because `build_useitems.py` is applied **and** `P_BACKPACK = True` in this script; revert either and
those six go silently inert while the 26 worn items keep working. Reviewed 2026-09-13 and **kept
deliberately**: `itUse` has no equip position (`GetItemTypePosition` = `0x0F`), so the backpack is the
only place such an item can sit, and the 8 backpack slots are interchangeable — eight Elixirs of Life
is +96 HP into a ceiling of 100. That stacking is accepted.

⚠ **`build_useitems.py` P4 is data-inert**: all 73 `itUse` records in `Zig.ail` are zero on the four
flat bytes `0x46..0x49`, so these six HP/MV values are the only flat stat any backpack item grants.

**Needs the user's in-game test:** a hero wearing one of the 26 worn items — card HP/MV rises by the
tabled amount, removing it drops the max (current HP clamps down on the next write, expected); a hero
carrying one of the 6 `itUse` items, from the backpack; **a high-level hero at the HP ceiling
specifically** — the overflow trap's configuration, confirm a maxed hero plus a +12 item reads 100, not
2; MV lands on the *next* turn refill, not immediately; tactical combat and auto-resolve both show the
bonus; save/reload with a bonus item equipped, and loading an *old* save (absent tags must default to
0, not corrupt).

### Route 2 (unbuilt alternative) and the display gap

**Route 2 — go through the ability system instead of a flat item byte** remains the better choice if
the goal ever grows to "gear *and* spells/medals/skills that grant HP/MV" rather than "a number on an
item": equipped + use-slot coverage, no new item field, no `ReadWrite`/editor/`.pfs` change, at the
cost of an ability-id→value table living cave-side. It also extends naturally to regular `TUnit`s,
which Route 1 (as built) never can — `TUnit.GetHits` is a different implementation, already caved by
`build_medal_hpmv.py` (`0x5580BE00`–`0x5580BE73` + a cap cave at `0x55818080`; **do not touch that
cave from an item patch** — it has its own documented landmine, an MV twin at `0x5580BE6D` that still
returns a dirty EAX). The two routes are not exclusive; Route 1's getter-cave hook point is the same
one Route 2 would use.

**Display — `TItemBanner` (AoWz.exe/AoWzCompat.exe) — BUILT 2026-09-13, `build_itembanner_hpmv.py`;
full record in `07-ui.md` §9.** The paint routine (`TItemBanner.IBannerPopupShow @0x00406AE8`) hides
all eight stat controls, then runs four ~0x7A-byte identical blocks, one icon+label per **non-zero**
byte among ATK/DAM/DEF/RES. It is a **2-column × N-row flow layout** (`cmp esi,0x82` after
`add esi,0x32` from `0x1E`) that already reached a third row and already repositioned the ability
listbox under it, so two more blocks needed no layout work: a 5-byte `E9` at `0x00406D7D` runs them
and rejoins at `0x00406D86`. The cost is in the plumbing, not the paint — four new published fields
(`+0x78..+0x84`) mean relocating both the grown `TITEMBANNER` DFM and the 13-entry field table into a
new `.ibnr` section and bumping `[VMT-0x1C]` to `0x88`. Both icons already exist (`IntGfxMod.UnitIcons`
index 4, `IntGfxMod.MoveIcons` index 16), so no ILB is touched, and `TUnitBanner` supplied the donor
DFM nodes verbatim.

⚠ The two rejected cheap options, and why: appending plain text lines to the ability listbox
(`AbLB`) needs no DFM surgery but puts the numbers in a different visual language from the four
bonuses they sit beside — and it is the listbox whose space the 200 px popup clamp was already
eating. Stretching the existing four controls to six by re-tagging them is impossible: the renderer
is unrolled, so each pair is hard-bound to one field offset.

The DLL-side mechanic works with or without this — the hero's own card shows the new totals already,
since `GetHits`/`GetMoves` are patched at source. **Route 2 above, if ever built, does not change the
banner**: the display reads `item+0x4A`/`+0x4B` directly, so a Route 2 rewrite would have to keep
those bytes populated or re-point these two blocks.

---

## Property-table serialisation — the format behind every `.pfs`, save and map

**⭐ Corrects a load-bearing false claim seen elsewhere: there is no `0xCD` "save-format ceiling" on
ability ids.** `Engine.TPropertyTable.SaveToStream@0x5550FD0C` (in `Enginep.dpl`) tests
`tag > 0x7F` **or** `offset > 0xFF` at `0x5550FD32`, and on either condition writes a **wide**
`(u32 tag, u32 offset)` entry instead of the small `(u8,u8)` form, flagging the header byte with
`or al, 0x80`. The engine already handles ids well past `0xCD`; whatever ceiling exists lives
elsewhere (ability-registration budget, not the property format). ⚠ Nothing above `0xCD` has actually
been run in-game — that is a separate, still-open question; this only rules out the save format as the
cause.

**Growing a class is backward-compatible, because saves are id-indexed, not positional.** A property
table is `[ctrl:u8]` → small `(tag:u8,off:u8)` pairs, plus (if `ctrl&0x80`) a `u32` count of wide
`(tag:u32,off:u32)` pairs — **offsets relative to the table's end**. The reader is tag-indexed: an
absent id just isn't in the directory, so old saves loading into a class that has since grown new
`ReadWrite` fields simply default those fields to zero. **Instance size is `[VMT−0x1C]`.**

**The container format is shared across every `.pfs`, save and map.** `.hsm`/`.asg`/`.csm` are
`"CFS\0"` + one mode byte + a raw zlib stream:
```python
import zlib
payload = zlib.decompressobj().decompress(open(path, "rb").read()[5:])
```
`re_tools/pfs.py`'s `parse_dir` then works **verbatim** on the decompressed payload — the directory
shape is the engine's general serialisation format, not something `.pfs`-specific. Objects inside are
`<u32 ClassID><directory>`, parsed with `top=True`. (`.acg` has a leading index and does *not* open
this way — not cracked. `.acg`/`.CAM` are uncompressed property streams instead.) Hand-editing:
```python
raw = zlib.decompress(open(path, "rb").read()[5:])
open(path, "wb").write(b"CFS\0\x02" + zlib.compress(raw))
```

### Map/save instances are frozen ability snapshots, not stale data to "fix"

**Status: ruled "not a bug" (owner, 2026-08-28).** A map or save stores each unit's ability *bitset*
as it stood **when the instance was written**; editing the ruleset afterwards does not retroactively
touch existing instances. Scanned across 28 files (`Save/*.asg`, scenarios, PBEM in/out): 58,887
`TUnit`, 13,374 `THero`, 1,185 `TLeader`, 12,082 `TItem` ability owners. Abilities the chassis grants
*today* that some instances lack: Spell Casting `0x34` (6,386 instances), Vision `0x40` (3,225),
Assassin `0x38` (798), Shield `0xB0` (711), Leadership `0x2E` (24).

⚠ **The staleness runs the opposite direction from the obvious hypothesis.** The expected shape — a
unit with the Leadership *bit* but no level record (the "bare name" pattern, see the `Unitres.pfs`
section below) — does not occur here; every `0x2E` record in every scanned file resolves to a real
level. Instead, stale instances have **lost the ability bit entirely**, invisible to a bit-only census.
Dated by content, not mtime: the base Ziggurat data file already carries the current (larger) ability
set, so any instance missing a bit was written *before* that data change and simply froze the old one.

**Why some files heal and others don't:** `TUnit.NewDay` rebuilds a unit's ability set (`SetAbCount(0)`
then re-grants base+rank) **only on day 1** (`cmp [AoWHSMap+0x174],1`). A fresh game off any map
repairs itself on its first day; an in-progress save past day 1 never does — consistent with the
data (`autosave.asg` has zero stale units; two named test saves, both multi-day, are stale).

Two things noted in passing, neither chased: **45 records resolve to Leadership level 254** (an
unsigned read of −2, concentrated in third-party-authored PBEM files — `TArmy.UpdateFormation`
propagates the stack maximum with **no clamp** against the cap of 4; origin of the negative untraced).
And the seven `Zig.ail` items granting Leadership are all level 1 (the cap was 1 until 2026-07-20) —
a hand-curation job to re-tier 1–4, not a patch; `Zig.ail` carries no description text in any of its
325 records, so there's nothing written to contradict a re-tier. ⚠ `TLeadershipAbility.GetLevel` is
`max(own, external/aura)` — an own-level-0 record with a nonzero external is normal runtime state, not
a missing grant; don't read `[rec+0x0C]` alone and conclude a level is absent.

---

## The `.pfs` container in detail

**Status: format confirmed 2026-08-07** — AoWDevEd's own re-save of `Unitres.pfs` validated against
the formula below, proving the *writer* maintains the checksum, not merely that shipped files happen to
carry one. ⚠ Whether the *reader* rejects a deliberately bad one is still untested (inferred from the
`.hss` precedent; doesn't matter in practice — repair the checksum regardless).

A `.pfs` beginning with magic `1C DF 44 21` ends with a **CRC-32 of `data[4:-4]`** (standard reflected
CRC-32, same algorithm as `.hss`'s `Engine.GetCRC32`):
```python
import zlib, struct
d = open("Release/Unitres.pfs", "rb").read()
stored = struct.unpack_from("<I", d, len(d) - 4)[0]
calc   = zlib.crc32(d[4:-4]) & 0xFFFFFFFF        # stored == calc
```
⚠ **The covered region differs from `.hss`**, which checksums `d[:-4]` — passing a `.pfs` to
`re_tools/hss_crc.py` reports a false mismatch and "fixes" it with a wrong value. Not interchangeable.
`Ability.pfs`, `FACERES.PFS`, `HERORES.PFS`, `ITEMGFX.PFS`, `Spells.pfs`, `TEXT.pfs`, `Unitgfx.pfs`,
`Unitres.pfs`, `comb_res.pfs` all carry the magic and a valid CRC; `General.pfs`, `HEROES.PFS`,
`ITEMS.PFS`, `RulesV.pfs` have **no magic, no CRC** — the rule is the magic, not the extension.

`0x2144DF1C` is not really "a magic number" — it is the **CRC-32 residue constant**: running CRC-32
over any message with its own little-endian CRC appended always yields this value. So one line
validates a file with no length lookup: `zlib.crc32(d[4:]) & 0xFFFFFFFF == 0x2144DF1C`.

**Always check the CRC first, before touching a byte, and gate every code path that reaches the file —
not just the write path** — or a "repair" silently stamps a valid checksum over pre-existing damage,
destroying the one piece of evidence anything was ever wrong:
```python
if zlib.crc32(d[4:]) & 0xFFFFFFFF != 0x2144DF1C:
    sys.exit("ABORT: already damaged before any edit — refusing to rewrite")   # sys.exit, never assert
```
Honest limits: the residue catches incoherent damage (a flipped byte, a nudged offset, a truncation) —
it **misses a coherent-but-wrong layout** that was re-CRC'd after the fact. Nothing cheap catches that.

### Editing scalars is safe; editing the tag map per-file is not

Fixed-size stats on a `Unitres.pfs` unit record (child classid `0x20212`) write in place with no
table rewrite: `0x0E` ATK, `0x0F` DEF, `0x10` DAM, `0x11` HP, `0x12` MV, `0x13` RES (bytes, 255=no
melee), `0x14` level (byte), `0x1B` gold cost (u32). **The order is not the design workbook's** — the
workbook reads ATK DAM DEF RES HP MV; the record stores ATK DEF DAM HP MV RES.

⚠⚠ **`HERORES.PFS` is `Unitres.pfs`'s sequence shifted one tag up — reusing the map mislabels all six
columns while still producing plausible numbers.** Read off `THeroResource.ReadWrite@0x55789FD4`, not
guessed, and not confirmed from a single hero's card (a level-2 Lizard's info-card stats fit a
*rotated* map just as convincingly, because level-ups/morale/items blur the tell — that coincidence is
how the wrong map shipped once already):

| tag | `Unitres.pfs` | `HERORES.PFS` |
|---|---|---|
| `0x0D` | — | alignment/race group (0–6, clamped >6→3) |
| `0x0E` | ATK | (unused) |
| `0x0F` | DEF | **ATK** |
| `0x10` | DAM | **DEF** |
| `0x11` | HP | **DAM** |
| `0x12` | MV | **HP** |
| `0x13` | RES | **MV** |
| `0x14` | level | **RES** — no starting-level field on a hero chassis |

**Derive a new file's tag map from its own `ReadWrite`; never inherit one, never confirm from one
sample.** `HERORES.PFS` has **38 records** in three 12-race blocks (mounted hero 0–11, infantry hero
18–29, leader 36–47 — leader block's tag `0x0C`=2, others 0) plus two specials (Mind Vessel, Dragon
Golem, 54–55); key by **position**, not name (`Lizard` vs `Lizardman` disagree with themselves across
blocks). Anything that **changes a record's length** (renaming, editing a description) is a different,
harder job — rebuilding its table, every later offset, and the root index; use the editor for that.

### Editing ability sets on a unit — length-changing edits are tractable, and one already shipped broken

The Ziggurat Manual ships an in-browser ability editor (add/remove per medal owner, assign levels,
rebuild the CRC — a full property-table re-serialiser in JS, self-tested by re-emitting an untouched
file and asserting byte-identical). Verified twice against Python (2026-08-09): a length-preserving
edit differed from the original by exactly one content byte plus the CRC; a length-changing edit (178
of 179 records byte-identical) matched an independent from-scratch Python reconstruction exactly. What
makes length-changing edits tractable: **the root index is friendly** — record 0 is the only small
(`u8`-offset) entry and always sits at offset 0, so growing any *other* record only shifts `u32`
offsets, no small/wide reshuffle; and a directory re-emits byte-exact if entry order (small-first,
then wide) and each entry's small/wide flag are preserved (new entries: small iff `tag<256 and
offset<256`).

**Every unit record carries four ability-set owners** (`top=False` sub-directories): tag `0x19` base,
`0x20` copper, `0x1E` silver, `0x1F` gold. Inside one: tag `2` = capacity, tag `3` = the ability
bitset (bit index = ability id), **tag `0x31`** = the record-id list, tag `0x32+id` = that ability's
data record.

⚠⚠ **Tag `0x31` — the loader reads only the records this list names.** `TAbilityOwner.ReadWrite`
does **not** scan for `0x32+id` tags; it reads the `TIntegerList` at tag `0x31`
(`[u32 0][u32 count][u32 ids…]`, insertion order arbitrary — verified across 670 AoWEd-authored
owners) and deserialises exactly those ids. **A record not listed is dead bytes** — the bit still
grants the ability, so the unit gets it at **level 0**: a bare name on the card, no effect, easy to
mistake for a display bug. Worse, **the write path also emits only listed records**, so an AoWEd
re-save *permanently deletes* any unlisted record. This broke **71 owners across 40 units** when the
Manual's editor shipped without syncing the list on every commit — both ends fixed and
**✅ CONFIRMED WORKING (2026-08-14)**: `build_scripts/build_unitres_reclist.py` reconciles every
owner's list to its records (dry-run default, `--apply`; ⚠ **`--undo` is not surgical** — it restores
`Unitres.pfs.pre-reclist` wholesale, wiping any Unitres edit made after `--apply`, because the broken
lists carry no information the records themselves don't. ⚠⚠ **That snapshot does not currently
exist**, so `--undo` has no revert path at all until a fresh `--apply` mints one into
`Ziggurat/backups/`), and the Manual's editor now syncs the list
on every commit. ⚠ **A unit already granted the broken state in a SAVE keeps its level-0 copy** —
grants are one-off snapshots (below); the file repair reaches existing units only on their next
rank-up re-grant.

⚠⚠ **A `Unitres.pfs` medal edit does not reach units already in a save.** The grant is copied once via
`TAbilityOwner.UpdateDefaultAbilities` and then serialised with the unit — its only callers that
matter are unit creation, a rank actually changing, and (day-1 only) `NewDay`'s full rebuild.
**An ongoing game never re-reads `Unitres.pfs` for a unit that already holds its medal.** Symptom: the
unit shows the ability at its **old level** — a numeral, just the previous one; that's the tell that
distinguishes it from the tag-`0x31` bug above, whose symptom is a **bare name with no numeral at all**
(level 0). Heroes refresh on load (`THero.Loaded` calls the same function); regular units do not. The
grant loop also **never downgrades and never removes** — lowering a level in the data leaves existing
units on the old, higher one; a unit already at gold can never rank again in that save.

**The level is a tagged field inside the record's own directory — never index from either end.**
`0x00022001`/`0x000202CE` (Marksmanship, Turn Undead, Transport, Spell Casting, Vision, Leadership):
level at tag `0x0A` (u8), id at `0x0B`. `0x000202CD` (Dispel Magic): level at tag `0x0B`. ⚠ Do not use
record *length* to find the level — a record's span runs to the next field's offset, so one at the end
of its owner picks up trailing slack (vanilla Galleon's 16-byte Marksmanship record has `[-3]` land on
an unrelated byte); clone a template harvested from the file and set the level byte, never fabricate
one from a guessed offset.

**Seven levelled abilities, capped per the live DLL** (not hard-coded — this project already raised
Leadership 1→4): Marksmanship `0x20` (4), Turn Undead `0x26` (4), Leadership `0x2E` (4), Transport
`0x32` (7 — this "level" is carrying capacity), Spell Casting `0x34` (5), Dispel Magic `0x3C` (3),
Vision `0x40` (4). Two ctor families must both be walked: `TMultiLevelAbility` descendants (cap is an
immediate in `Create`) and the two non-`TMultiLevelAbility` levelled classes, `TTurnUndeadAbility` and
`TDispelMagicAbility` (hard-coded `cmp eax,imm` in their own `GetLevel`-consuming `CanExpand`) — chasing
only the first family silently drops the second. ⚠ A `0x32+id` record existing does not itself prove
an ability is levelled (`Walking 0x00` has no multi-level ctor at all, yet one owner carries a stray
tag `0x32` holding an unrelated datum) — trust a ctor-reachability scan, not the tag's mere presence.

### Editing a string field — `build_scripts/build_pfs_typos.py`

The generic, table-driven writer for text corrections (file, record id, tag, old substring, new
substring — one row per fix). Handles the full length-changing dance (body directory, every later
index offset, the CRC); dry-run default, `--apply`, surgical `--undo`, `--dis` to print the strings.
Three things it knows that a one-off script tends not to: **a record body directory can mix small and
wide entries** (high bit on `body[0]` means a `u32` wide count follows the small ones — a Ziggurat
Charm record has 4 small + 1 wide, past the u8 offset ceiling; a writer that refuses wide bodies simply
cannot touch that record — say which shape you handle and abort on the other, don't guess); **two
string forms exist and must be sniffed, not assumed** — descriptions (tag 5) are `u32`-length-prefixed,
names (tag 10) are `u8` Pascal; sniff by whether `4+n` or `1+n` equals the field length and refuse
anything that's neither; and **fields must tile the rebuilt payload exactly**, no gap or overlap — an
off-by-one in the offset shift shows up as a hole (this is *not* the circular check below — lengths
come from the old offsets, placement from the new ones). Two state guards make "is this applied?"
answerable: the target substring must occur exactly once, and old/new must not be substrings of each
other. The `.pre-typos` snapshot is taken **only on the first apply** and never overwritten, so a later
run against an already-patched file can't mint the lying backup CLAUDE.md warns about.

### Failed/rejected approaches — do not retry

- **Treating the leading dword as a plain magic constant and ignoring the tail.** Fine for reading;
  silently loses the checksum on any write.
- **Reusing `hss_crc.py` on a `.pfs` directly.** Wrong covered region (`d[:-4]` vs `d[4:-4]`) — its
  `--fix` writes a checksum the engine will not accept.
- **⚠ "Verifying" a rebuilt layout by tiling record bodies backwards from EOF and comparing to the
  index offsets.** Looks like an integrity check and is **circular — it can never fail**: the index
  parser derives each body as a slice *at* the very offset being re-derived, so backwards-tiling
  reproduces the same start by construction; it proves slicing is deterministic and nothing else. Two
  scripts carried this (one with a deliberate +3 offset nudge that it still passed); both replaced with
  the CRC gate above on 2026-08-09, both now carry a comment not to bring it back — the temptation is
  that it *reads* like the check you want.

**Related tools:** `re_tools/pfs.py` (reader), `build_scripts/build_pfs_typos.py` (string writer),
`re_tools/reconcile_units.py` (workbook vs. `Unitres.pfs` diff — remember the workbook itself is
historical, see the project's own top-level notes), `build_ziggurat_manual.py` (reads `Unitres.pfs`
live for the Manual), `re_tools/hss_crc.py` (the `.hss` sibling algorithm).

### Building a data-driven tool off this data (from the shared AoWx manual builder)

Reusable per-file tag references, useful for any future tool that reads game data directly rather than
through `re_tools/pfs.py`:

- **`Unitres.pfs`** (child classid `0x20212`): tag `0xA` race name (or the unit name itself, if `0xB`
  is absent — independents/monsters); `0xB` unit name; `0xE–0x13` ATK/DEF/DAM/HP/MV/RES (as above);
  `0x14` level; `0x1A` description (`u32` length-prefixed); `0x1B` gold; `0x19`/`0x1E`/`0x1F`
  base/silver/gold ability owners; `0x8` first dword = portrait gfx id chain root.
- **`Ability.pfs`**: root key = ability id + 10. Tag `5` description (`u32` length, cp1252, includes
  the level-numeral text), `6` hero level-up cost (absent = not learnable), `9` the 2-byte
  `TAbilitySelectionTypes` set (bit0 unit, bits1–5 per-wearable-slot, bit6 use item, bit7 Customize
  Leader, bit8 Hero Upgrade, bit9 editor — the level-up handshake described above). ⚠ Some ability ids
  are runtime-assigned at registration and can differ between installs with different registered
  custom abilities.
- **`Spells.pfs`**: records are tables directly (no classid prefix, like `Ability.pfs`). Tag `0xA`
  description, `0xD` casting cost, `0xF` research cost. **Names are not in the game files** — they are
  UI resourcestrings; see [Renaming text](#renaming-spells-abilities-and-ui-text--dictresstrmld) below.
- **Portraits — `Unitgfx.pfs` chain + ILB decoding.** Unit tag-8 gfx id → `Unitgfx.pfs` child
  (classid `0x20210`): tag `6` face ILB path, tag `8` face index within it, tag `5` unit sprite ILB.
  ⚠ Index base differs per face file (0-based for the shipped face packs; some custom packs are
  1-based). ILB frames are located by pixel-format marker `0x56509310`; three pixel formats exist (raw
  16bpp, row-encoded 16bpp with stride rounded **up** to a multiple of 4, and 8bpp RLE for unit
  sprites with 72-record direction sets — front/front-right/back-right/back/back-left/front-left, no
  row-alignment). Transparent key colour = RGB565 `0x4D2B`.

---

## Registry isolation — a Ziggurat install that can sit beside vanilla

**Status: 🔨 APPLIED, UNTESTED (2026-09-09)**

| | |
|---|---|
| build script | `build_scripts/build_regiso.py` |
| targets | `AoWEPACK.dpl` (6 constants), `AoWSetup.exe` (3 constants) |
| revert | `python build_scripts/build_regiso.py --undo` — surgical, rewrites the nine constants back |
| backups | `Ziggurat/backups/AoWEPACK.dpl.pre-regiso`, `Ziggurat/backups/AoWSetup.exe.pre-regiso` ⚠ neither currently exists — the pre-move snapshots were in `<root>/backups/`, deleted 2026-09-10 |

`HKCU\Software\Triumph Studios\Age of Wonders` → `...\Age of Wonders Z`.

**Why it matters, and it is not cosmetic.** The engine's data root is seeded from
`General\"Startup Directory"` in that key (`AoWReg.TAoWRegistry.GetStartupDirectory`; the value name
is at file `0x4674` of `AoWEPACK.dpl`, and AoWSetup's Developer tab is what writes it). Two installs
sharing the key share one data root — run vanilla's AoWSetup, then launch Ziggurat, and Ziggurat
reads vanilla's folder. Video mode, hotkeys, player name and the cheat flags collide identically.

**⭐ What it unlocks — this is the point, not settings hygiene.** Ziggurat overwrites vanilla in
place; there is one folder, and `AoWEPACK.dpl` and `Release/` are either vanilla or modded. Copying
the folder did not previously produce two installs, because both copies' binaries read
`Startup Directory` from the same key — whichever install wrote it last won, and *both* folders
loaded `Release/`, `Dict/` and `Images/` from that one directory. The registry key was the thing
making side-by-side impossible. Moving Ziggurat off it is what makes the copy-paste work.

**⚠ Which key a folder uses is a property of the FILES in it, not of its path.** Copy the Ziggurat
folder today and you get two `Age of Wonders Z` installs sharing one data root again. The vanilla side
needs unpatched binaries — which then use the plain key with no patch at all. That is more than
restoring `AoWEPACK.dpl`: `aowInt.dpl`, `AoWTCPCK.dpl`, `HSEPack.dpl`, `Dcpack.dpl`, `AoWz.exe`,
`AoWzCompat.exe`, `AoWDevEd.exe` and `AoWEd.exe` are all modified here too. A fresh vanilla install into
the second folder is cleaner than reconstructing one.

**Nothing else is required to coexist.** The packages resolve from the exe's own directory, so two
install *folders* are otherwise independent. This is why neither we nor AoWx renames any game file —
see "Coexistence does not need renamed binaries" below.

### The sites — all nine verified live, the six in the DLL also against the pristine backup

`AoWEPACK.dpl`, `VA = file + 0x55700C00`:

| chars | length dword | the `mov edx` that loads it (**never touched**) | len |
|---|---|---|---|
| `0x002FEC` / `0x55703BEC` | `0x002FE8` | `0x55703B60` | 41 |
| `0x0030DC` / `0x55703CDC` | `0x0030D8` | `0x55703C50` | 41 |
| `0x0031D4` / `0x55703DD4` | `0x0031D0` | `0x55703D40` | 41 |
| `0x0032C8` / `0x55703EC8` | `0x0032C4` | `0x55703E38` | 41 |
| `0x0035BC` / `0x557041BC` | `0x0035B8` | `0x5570410D` | 41 |
| `0x003ABC` / `0x557046BC` (`…\General`) | `0x003AB8` | `0x55704670` | 48 |

`AoWSetup.exe` (base `0x400000`): `0x066480`, `0x066570`, `0x066668`, all 41.

Applied delta: 30 bytes over 13 runs in the DLL, 12 bytes over 6 runs in AoWSetup — length dword
`0x29→0x2B` (or `0x30→0x32`) and the trailing `5C 00 00` → `20 5A 5C`.

### Mechanism — lengthen a Delphi const in place (Inioch's trick, `Inioch.md` §3)

A Delphi 3 AnsiString constant is `[refcount −1][length][chars][NUL][pad 00…]`, and these carry 2–3
spare pad bytes. Bump the length dword, write the extra chars into the pad: the string's **start
address never moves**, so every `mov edx,<addr>` keeps working and none is edited.

⚠ **The ceiling is 43 characters.** Old footprint is 41 + NUL + 2 pad = 44; new is 43 + NUL = 44, an
exact fit. `…\Age of Wonders Ziggurat\` (50) does not fit; `" Z"` is what does. The `\General` copy
has one byte spare (52 against 51). `build_regiso.py` measures the zero-run at every site before
writing and aborts rather than eating the next constant, so a longer `SUFFIX` fails loudly.

### ⚠ AoWSetup.exe carries three copies — Inioch's write-up misses this

`Inioch/share3/Registry Isolation.md` states the path exists only in `AoWEPACK` and that everything
else routes through `TAoWRegistry`. The second half holds — `AoW.exe`, `AoWCompat.exe`, `AoWEd.exe`
and `AoWDevEd.exe` carry **no** copy (scanned, zero hits). The first half does not: `AoWSetup.exe`
statically links its own `rw*` helpers with three copies of the constant. Patch the DLL alone and
AoWSetup writes the startup dir and video mode into the **old** tree while the game reads the new
one — settings silently stop sticking. If his AoWSetup has them too, AoWx has this bug live; flagged
for the next `To Inioch/` drop.

### Seeding, and what stays shared

Settings are not migrated by the patch. Seeded once on 2026-09-09 (non-destructive — creates the new
key, leaves the old one alone):

```
reg copy "HKCU\Software\Triumph Studios\Age of Wonders" "HKCU\Software\Triumph Studios\Age of Wonders Z" /s /f
```

Deliberately left shared: the `.hsm`/`AOWMAP` associations `TAoWRegistry.AssociateAoWMap` writes into
`HKCU\Software\Classes` (per-user, last-run-wins, cosmetic), and `Launcher.exe`'s own unrelated key
`Software\Triumph Studios\AoWLauncher`.

### 🔜 The three-install goal — plan agreed 2026-09-09, DEFERRED by the owner

Target: vanilla, AoWx and Ziggurat all installed at once.

| install | folder | registry key | who patched it |
|---|---|---|---|
| vanilla | its own, from **GOG** (owner's choice) | `…\Age of Wonders` | nobody — unpatched binaries use it by default |
| AoWx | `…\Age of Wonders X` | `…\Age of Wonders X` | Inioch, 2026-07-22, ships in his build |
| Ziggurat | the current game dir | `…\Age of Wonders Z` | `build_regiso.py`, this file |

The registry half is done; no further binary work is needed for coexistence. Sequence when it resumes:

1. **Vanilla from GOG into its own folder** — must come first, because the AoWx installer copies *from*
   a vanilla folder. ⚠ `HKCU\…\Age of Wonders\General\Startup Directory` currently points at the
   Ziggurat folder (it was the seed source); the GOG installer overwrites it, a hand-copied folder
   would not.
2. **Run `Inioch/AoWx Installer (version 1.37.407)/`**, point it at the vanilla folder, choose
   *Installing over vanilla* → *Make a separate folder*. `PrepareToInstall` does
   `DirectoryCopy(vanilla → sibling)` then overlays. Vanilla is left untouched.
   ⚠⚠ **Never point it at the Ziggurat folder.** It builds its target as a *sibling* of the selected
   folder named `Age of Wonders X` and copies that folder's contents first, so it would clone
   Ziggurat's modified binaries and data and overlay AoWx on top — a silent hybrid.
3. **Ziggurat stays put.** Nothing to do.

**Rebuilding vanilla from this repo is not viable** — `ziggurat_manifest.json` records 52 changed
files and 910 added; `Modding Resources/Release - Vanilla` holds 15 of them, and there is no pristine
`aowInt.dpl`, `AoWTCPCK.dpl`, `HSEPack.dpl` or `Dcpack.dpl`. Do not attempt it.

### ✅ The overlay layout — BUILT AND RUNNING 2026-09-09

Owner's design: the game folder **is** a vanilla install; Ziggurat rides on top as one extra exe and
one subfolder. Chosen over three full copies of the game.

**⭐⭐ Verified live** by enumerating the running process's modules: `Ziggurat\AoWz.exe` maps
**20 packages, every one from `Ziggurat\`, none from the vanilla root**, and starts clean.
It needs no patching at all — the exe sits in the folder holding its packages, so the loader
resolves them from its own directory.

⚠ **That rests on `Ziggurat\` holding a COMPLETE package set — all 33, not just the 6 modified
ones.** Strip the 27 unmodified copies to save space and every Ziggurat exe dies with
`STATUS_DLL_NOT_FOUND`, naming nothing.

**Superseded 2026-09-09: the root-exe indirection.** The first build put `AoWz.exe` at the vanilla
root with its 175 import descriptors rewritten to `Ziggurat\<pkg>.dpl`, because `Ziggurat\` then
held only the 6 modified packages. Copying the full set in for `AoWzEd.exe` removed the need, and
`build_overlay.py` plus the two root exes were retired. The RE is worth keeping and lives in
`12-re-toolchain.md` §13a — including the finding that made the partial redirect survivable at
all: **the loader dedupes by base name**, so the 15 shared packages importing bare `vcl30.dpl`
matched the already-loaded `Ziggurat\VCL30.dpl` instead of mapping a second VCL runtime.

**⭐ This also settled the standing registry unknown.** The game reached
`…\Ziggurat\Int\GenericT.ilb`, which means `Ziggurat\AoWEPACK.dpl` read `Startup Directory` out of the
`Age of Wonders Z` key correctly. **AoWEPACK does read the isolated tree.** Whatever made Delphi's
`TRegistry` fail inside AoWSetup does not affect the engine's own `rw*` helpers. The AoWSetup cause
remains unknown, but it is now a contained curiosity rather than a risk to the isolation.

⚠⚠ **`Ziggurat release\` alone is NOT enough to run from.** It is the release *payload* — only the 962
files that differ from stock. The engine has one data root and does **not** fall back to the parent
folder, so a payload-only subfolder dies on the first unmodified asset (observed:
`Error loading: …\Ziggurat\Int\GenericT.ilb`, repeating). The subfolder needs the **complete** data
tree: copy the payload in first, then merge the vanilla data with `cp -rn` so the modified files win.
373 MB duplicated; 1883/1883 files verified present afterwards. Exact commands in
`CLAUDE.md`. ⚠ `Scenario\` (vanilla campaigns) is easy to miss — it is distinct
from Ziggurat's `1Scenario\`.

```
<game>\                     a vanilla GOG install
   AoW.exe                  vanilla, untouched          -> plays vanilla
   AoWEPACK.dpl  …          vanilla packages, SHARED
   Release\ Dict\ Images\   vanilla data, SHARED
   AoWz.exe                 Ziggurat (purple dragon)    -> plays Ziggurat
   AoWzCompat.exe
   Ziggurat\
      AoWEPACK.dpl  AoWTCPCK.dpl  HSEPack.dpl  Ilpack.dpl  aowInt.dpl  vcl30.dpl
      Release\ Dict\ Images\ Int\ Sfx\ 1Scenario\ User\ Save\
```

Two mechanisms, one per half of the 962 modified files:

- **The 6 modified packages** — rewrite `AoWz.exe`'s import names to `Ziggurat\<name>.dpl`. Proven to
  work; full evidence and mechanics in `12-re-toolchain.md` §13a. Each of the 6 also imports the
  others, so all 8 binaries (2 exes + 6 packages) get the same transform. Unredirected modules
  (`Localize`, `SoundP`, `EngineP`, `ims`, `VideoP`, `Network`, `GFXEPACK`, `aowDPlay`, `vclx30`,
  `DCPACK`, `aowFXpck`) keep resolving from the top level and are shared with vanilla.
- **The 954 data files** — point `Startup Directory` in the isolated `Age of Wonders Z` key at
  `<game>\Ziggurat\`. ⭐ This is what the registry isolation was for; the two features are one design.

**⚠ Blocked:** the end state needs a vanilla install in the main folder, which the owner deferred
(GOG, later). The current folder is Ziggurat-over-vanilla-in-place, so there is nothing to overlay
*onto* yet.

**⚠ Two things to settle before building:**

1. **Does every data path derive from `[engine+0x2C]`?** `Release/`, `Dict/`, `Images/`, `Int/`,
   `Sfx/`, `Songs/`, `Scenario/`, `Save/`, `User/`. Any path built from the current directory or the
   module path instead would silently resolve to the **vanilla** copy at top level — a hybrid with no
   error. Needs a path-construction audit before the data move, not after.
2. **The editor.** `AoWDevEd.exe`/`AoWEd.exe` load the modified packages too; under the overlay they
   would pick up vanilla's unless given the same import rewrite. Either mint `AoWzEd.exe` or accept an
   editor that edits vanilla.

⚠⚠ **And the open registry unknown now gates this feature, not just AoWSetup.** The data half depends
entirely on `Startup Directory` being read correctly out of the Z key — the same read that
inexplicably returned nil inside AoWSetup. Settle that first; see the checklist above.

### Two editors — `AoWzEd.exe` in the subfolder, `AoWDevEd.exe` left on vanilla

Owner's ruling 2026-09-09: the top-level `AoWDevEd.exe` stays **vanilla-oriented**; a purple
Ziggurat-oriented copy lives in the subfolder. `build_zigeditor.py` builds
`Ziggurat\AoWzEd.exe`.

**⭐ It needs no import patching at all.** `AoWz.exe` had to be rewritten because it sits at the top
level, where the loader resolves packages against the vanilla folder. The editor lives *inside*
`Ziggurat\`, so the application directory already **is** `Ziggurat\`. Verified live: it maps **18
packages, all from `Ziggurat\`, none from the top level.**

That requires `Ziggurat\` to hold every package — 33 of them now. ⚠⚠ **Git Bash globbing is
case-sensitive and this install has nine UPPERCASE Delphi packages** (`IBEVNT30.DPL`, `QRPT30.DPL`,
`TEE30.DPL`, `TEEDB30.DPL`, `TEEUI30.DPL`, `VCLDB30.DPL`, `VCLDBX30.DPL`, `VCLSMP30.DPL`,
`VCLX30.DPL`). `cp -n *.dpl *.dll` matches none of them; the editor imports `vclx30` and pulls in
`vcldb30`, so the first build died instantly with `STATUS_DLL_NOT_FOUND` naming nothing. NTFS is
case-insensitive so the *game* finds them; only the copy was short. Both commands are needed:

```
cp -n *.dpl *.dll Ziggurat/
cp -n *.DPL      Ziggurat/
```

**Data follows automatically.** `AoWzEd.exe` loads `Ziggurat\AoWEPACK.dpl`, which carries the regiso
patch, so it reads the `Age of Wonders Z` tree and edits the mod's data. The top-level `AoWDevEd.exe`
loads vanilla packages, reads the plain key, and edits vanilla data. ⚠ **Both are the same modded
binary** — `AoWDevEd.exe` is a mod-*added* file the vanilla installer never touched, so it survived
the reinstall. Only the folder they run from decides which content they edit; the top-level one keeps
this project's editor work (render gate, terrain palette, validation goto, hero prune) while pointing
at vanilla.

**Icon:** `RT_ICON` id 1, file `0x0446C4`, 4264 bytes — 40 B header + 4096 B XOR + 128 B AND, 32×32
**32bpp BGRA**, no palette. ⚠ A different format from the game icon's 4bpp+palette, so the two
scripts' icon code is not interchangeable. 152 pixels remapped: saturation > 0.20 and hue 80–170°
(the green hex field) → 270–300°, saturation and value preserved. The dragon is greyscale so it falls
below the gate, and the red outline and yellow highlights are outside the band and kept as accents.
Alpha is untouched.

### The exe icon — purple, mirrored

**Status: 🔨 APPLIED, UNTESTED (2026-09-09).** `build_icon_purple.py`, backups
`Ziggurat/backups/AoWz.exe.pre-purpleicon` + `AoWzCompat.exe.pre-purpleicon`, `--undo` exact (the flip is its own
inverse; round-tripped byte-identical). Applied to **both** exes in lockstep — the script asserts they
differ only at `0x3BB7C` before and after.

One icon: `RT_ICON` id 1, file `0x00073AEC`, **744 bytes**, from `RT_GROUP_ICON` id 6360. 32×32 4bpp,
`biHeight` 64 (32 image + 32 mask), bottom-up, 40 B header + 64 B palette + 512 B XOR + 128 B AND.
Nothing changes size, so it is an in-place `.rsrc` write — no directory rebuild, no section growth.

Only two palette entries move: `#800000`→`#3A006B` and `#FF0000`→`#A838E8`. The spine stays gold on
purpose — a uniform hue rotation sends yellow to pink and the highlight disappears. ⚠ **There is no
white in this icon** (index 15 is unused); the pale S-curve inside the coil is the *transparent* field
(488 px), not a drawn glyph, so mirroring costs nothing there. It only looks like a letter when a
preview is rendered on a light background.

⚠ The XOR bitmap is 4bpp — rows mirror by **nibble**, not by byte; the AND mask mirrors by bit. Row
order is untouched: a horizontal flip does not affect bottom-up storage.

### Coexistence does not need renamed binaries

AoWx's own answer is **a separate install folder plus this same key edit** — its installer offers
"make a separate *Age of Wonders X* folder (your vanilla folder is copied and left untouched)" or
"overwrite my vanilla installation (the folder is renamed)"
(`Inioch/share6/patch scripts/installer/AoWxInstaller.iss:687`). Inioch renames exactly two files,
`AoW.exe`→`AoWx.exe` and `AoWEd.exe`→`AoWDevX.exe`, and both are **branding** (taskbar caption, title
bar, icon), not isolation. `AoWEPACK`, `aowInt.dpl`, `VCL30.dpl`, `HSEPack.dpl`, `AoWSetup.exe`,
`Release/*.PFS`, `Dict/*.mld`, `Images/` and `Int/` all keep vanilla names and are overwritten in
place. His V-suffixed alternates (`Dict\AoWVan.MLD`, `Dict\ResStrV.mld`, `Release\TEXTVAN.PFS`) are
additive and exist only for his vanilla-campaign switch, not for coexistence.

**Do not rename our packages.** It buys nothing once the folders are separate — Windows resolves the
`.dpl`s from the exe's own directory first — and the cost is broad: `AoW.exe`'s import table names 17
`.dpl`s, every package that imports `AoWEPACK` names it too, and `aow.exe`/`aowsetup.exe` are
hard-coded strings inside `AoWEPACK.dpl` (`0x5608`, `0x574F`) and `Launcher.exe`. Renaming `AoW.exe`
alone would touch three binaries to buy a nicer taskbar entry.

### ⚠⚠ It broke AoWSetup's install check — cause NEVER PINNED DOWN

Applying the isolation collapsed AoWSetup's home screen to **Install/Exit** — no Play!, no Settings,
no Editor. `TLoaderForm.IsInstalled @0x00468618` reads `General\Root Directory` through
`GetRootDirectory @0x00467584` and tests `FileExists(root + '\aow.exe' @0x004686A0)`; an empty read
means "not installed".

**Everything that would explain it was measured and ruled out**, so do not re-run these:

- the patched constant is well-formed — `refcount −1`, `len 43`, NUL in place, next function intact;
- `Root Directory` (`0x004675B0`) and `General` (`0x004675C8`) are untouched;
- the value reads correctly out of `…\Age of Wonders Z\General` (Python `winreg`, same user);
- `aow.exe` exists at the path it names;
- no `RUNASADMIN` AppCompat layer on it, so no elevated-hive split;
- launching AoWSetup creates **no** unexpected key — and `OpenKey` is called with `CanCreate=1`, so a
  wrong key name would have materialised. `TRegistry.OpenKey` on the Z path therefore succeeds.

By the disassembly the check should pass. It did not.

**⭐ What the fix then proved.** The `'.'` fallback below substitutes *only* when the getter's
out-string is nil — and it cured the symptom. So **the registry read really was returning nil inside
AoWSetup**, for a key/value that reads correctly from another process, as the same user, at the same
moment. The failure is therefore inside `TRegistry.OpenKey`/`ValueExists` against the Z path, not in
the constant, the key's existence, or the value's presence. Nothing measured so far explains that, and
the mechanism **is still unknown** — do not record this as solved. The next step is the live process,
not more static analysis.

⚠⚠ **This is a live risk to the isolation itself, not just to AoWSetup.** AoWEPACK's `TAoWRegistry`
reads the same tree. If the same failure mode applies there, the game runs on defaults and
`Startup Directory` comes back empty — which is exactly the value the whole feature exists to
separate. AoWSetup statically links its own Delphi `TRegistry` while AoWEPACK has its own `rw*`
helpers, so they may well differ, but **this is unverified**. Checklist items 2 and 3 below are what
settle it; treat the isolation as unproven until they pass.

### The fallback — `build_aowsetup_installcheck.py`, adopted from Inioch

**Status: ✅ CONFIRMED WORKING (2026-09-09)** — user tested; the full home screen returned.
Backup `Ziggurat/backups/AoWSetup.exe.pre-setupcheck`; surgical `--undo` (restores the call, zeroes the cave,
restores VirtualSize) — round-tripped byte-identical.

Gives `GetRootDirectory` a `'.'` fallback when the read comes back nil, so the check becomes
`FileExists('.\aow.exe')` and **stops depending on the registry at all**. Inioch shipped the same fix
on 2026-08-13 after the identical symptom hit an AoWx player
(`Inioch/share6/memory/aowsetup-installcheck-devtab.md`); his cause was understood and different — a
*fresh* AoWx install has no isolated tree yet, so the read genuinely returns nil.

- **Hook:** the `call 0x0046719C` at `0x004675A0` retargeted to the cave — a call-rel32 retarget,
  4 bytes of operand, nothing displaced, no `.reloc` concern.
- ⚠ `0x0046719C` is **`ret 8`** (epilogue `0x0046725D`), so the cave re-pushes both args
  (`push [esp+8]` twice) and returns `ret 8` itself. eax is clobbered deliberately — neither caller
  (`0x00468636`, `0x00468A70`) uses the return value, both read the out-parameter.
- ⚠ Storing straight into the out-var is safe **only because it is nil there**, which the cave tests.
  The `'.'` image is a refcount −1 literal, so the later `LStrCat` allocates fresh and `LStrClr` skips
  it — no RTL call needed to assign it.
- **Cave re-derived on our binary, not reused from his** (`Inioch.md` §1, standing rule 2 — his was
  `0x004698E0`/`0x004698EC`). CODE VirtualSize `0x6880C` ends at VA `0x0046980C`, SizeOfRawData runs
  to `0x00469A00` ⇒ 500 bytes of verified-zero tail, characteristics `0x60000020` = CODE|EXECUTE|READ.
  Allocated: `'.'` image `0x0046980C` (chars `0x00469814`), body `0x00469820` (31 B).
  **Next free AoWSetup cave: `0x00469840`.** ⚠ **R-X, not writable** — code and read-only constants
  only. VirtualSize bumped `0x6880C`→`0x68A00`; DATA starts at `0x0046A000`, SizeOfImage unchanged.
  `DllCharacteristics` is `0x0000` — no `DYNAMIC_BASE` — so absolute addresses are legal here.
- **Independent of `build_regiso.py`**: the cave (file `0x68C0C`+) and the path constants
  (file `0x6647C`/`0x66668`) do not overlap, so either reverts alone in any order.
- **Known limit:** `'.'` is relative to the working directory. Launched from the game folder it
  resolves; launched with some other CWD it does not, and the check falls back to the registry answer.
  `GetModuleFileNameA` would be robust but needs a writable buffer, and this section is R-X with only
  ~5 bytes of BSS free past `[0x0046BA34]`. Not worth a new section for a fallback path.
- Smoke-tested: AoWSetup launches and survives, so the cave's stack discipline is right.

### In-game checklist — the user still needs to run this

1. ~~Launch `AoWSetup.exe` from the game folder; the full home screen must be back.~~ **PASSED
   2026-09-09.**
2. ⚠ **The one that matters — change something in AoWSetup (e.g. Auto Save), OK, reopen.** It must persist, and
   `reg query "HKCU\Software\Triumph Studios\Age of Wonders Z\General"` must show it while the old
   `Age of Wonders` key stays frozen. This is the check that catches a half-applied patch.
3. **Launch `AoWz.exe` and load a save.** Data must load from the Ziggurat folder; the player name and
   window position should be the familiar ones.
4. **Launch `AoWzEd.exe`.** It loads `Ziggurat\AoWEPACK.dpl` too — confirm no runtime error 216 at startup
   and that it finds its map directory.
5. **The real proof:** install vanilla into a second folder, run its AoWSetup, then relaunch
   Ziggurat. Ziggurat must still read its own folder.

## Renaming spells, abilities and UI text — `Dict/ResStr.mld`

**Status: ✅ CONFIRMED WORKING (2026-08-29)**, validated in-game.

| | |
|---|---|
| build script | `build_scripts/build_resstr_names.py` |
| targets | `Dict/ResStr.mld` **and** `Dict/ResStr.txt`, written in lockstep |
| revert | `python build_scripts/build_resstr_names.py --undo` — surgical, per-row, both files |

**Start here: a spell's name is not in any `.pfs`.** `Spells.pfs`/`Ability.pfs` have no name field, only
a description (tags `0xA`/`5` respectively — edit those with `build_pfs_typos.py`). The name is a
Delphi resourcestring compiled into `AoWEPACK.dpl`'s `.rsrc` as UTF-16, packed back-to-back with no
slack (`<u16 len><wchar…>` entries) — growing one in place means shifting every string after it in the
block. **Don't.** The engine already ships a supported route:

```
AoWE.TranslateRStr @0x557249FC → AoWE.TAoWEngine.TranslateRStr @0x55797B30
    if [[engine+0x78]+0x44] < 1 : return the source string unchanged
    else                        : IvDictio.TIvDictionary.Translate(dict, source, dest)
```

`Dict/ResStr.mld` is that dictionary, keyed on the **native English** string; a blank target slot falls
back to the source (1148 of 1164 shipped records are empty). ⭐ Ziggurat already uses this mechanism for
its own renames — the 16 non-empty `[US]` slots in the shipped file (Fireball→Triple Fireball,
Summon Mermaid→Craft Aether Barge, Dragon/Dragon Slaying→Monster/Monster Slaying, Pure Good/Evil→
Lawful/Chaotic, and others) are the proof the route works and is the intended one.

**The `.mld` format (Multilizer v3), re-derived, not guessed.** Little-endian header: `"MLD"`, version
byte(3), byte order, char set, context, reserved; `u2` language count @12 / `u4` language offset @14;
`u2` translation count @18 / `u4` translation offset @20; `u2` locale count @24 / `u4` locale offset
@26; `u2` info size @30 / `u4` info offset @32 (header ends at `0x2A`). Translations pack sequentially
from `translation_offset` with **no index** — each record is 8 `<u16 len><bytes>` strings, `NATIVE,
FORM, COMPONENT, [US], [DE], [FR], [IT], [ES]` (`[US]` is index 3). In this install: 1164 records
starting at `0x118`, landing exactly on `info_offset`, with `info_offset + info_size == filesize`.
⇒ **a length change needs exactly one fix-up — `info_offset` moves by the delta.** Nothing else
references a position past the edit, and **there is no checksum** (unlike `.pfs`).

**Traps:** `Dict/ResStr.txt` must move in lockstep — it's the human-editable source `mld_conv.exe`
round-trips back into the `.mld`; if the two drift, the next TXT→MLD conversion silently reverts the
rename, so the script edits both and refuses to run if they disagree. ⚠ **The `.txt` is CRLF** —
reading it in Python's default universal-newline mode and writing it back converts all 10,612 line
endings to LF, a 10 KB diff from a one-word edit; read with `newline=""` and preserve each line's
trailing `\r` (caught only by the `--undo` byte-exactness check the first time). ⚠ `mld_conv.exe` is a
GUI program that still waits for a click even with a file argument — it **hangs a shell**; the build
script writes both files directly and never invokes it. The `_HEADER_` block in the `.txt` is left
untouched (already stale against the `.mld`; `mld_conv` recomputes it). `Ziggurat upload/Dict/` holds a
pristine copy of both files, untouched unless asked.

⚠ **A MODDED `Dict/ResStr.txt` is sitting in the pristine vanilla game ROOT** (found 2026-09-10, not
fixed — a state question for the owner, not a docs one). Measurements:

| file | md5 | content |
|---|---|---|
| `Ziggurat/Dict/ResStr.txt` | `3d2e2864…` | **modded** — carries `[US] = [Power Leech]`, `[Version: Ziggurat %s]` |
| `<root>/Dict/ResStr.txt` | `3d2e2864…` | **identical to it — so also modded** |
| `Ziggurat/Dict/ResStr.mld` | `be626704…` | modded |
| `<root>/Dict/ResStr.mld` | `be93c453…` | vanilla — neither string present |

So **`Ziggurat/`'s pair is in lockstep and healthy** — `build_resstr_names.py` dry-runs clean, all
five managed rows "already there", and it aborts on any `.mld`/`.txt` disagreement, so that clean run
*is* the lockstep proof. The defect is at the root, whose `.txt` is Ziggurat's while its `.mld` is
stock. It is inert today (the game reads `.mld`; the `.txt` is `mld_conv` source only) and invisible
to `mod_manifest.py`'s CHANGED count, because **`Dict\ResStr.txt` is not in the GOG manifest at all**
— the hashdb contains exactly one `ResStr` entry, `Dict\ResStr.mld`, so the `.txt` classifies as
ADDED, which is why the root still reports `CHANGED(0)`. ⚠ The live hazard: a TXT→MLD round trip run
*at the root* would push Ziggurat's names into the vanilla dictionary. Deleting `<root>/Dict/ResStr.txt`
is the obvious repair; it is the owner's call.

**Rows applied:** `Freeze Water` → `Grip of Winter` (2026-09-01, paired with `Release/Spells.pfs`
record 20 tag 10 via `build_pfs_typos.py` in the same pass — name and description always move
together). `Summon Fire Sprite` → `Summon Fire Sprites` (2026-08-29 — the spell already summons 3–7 via
a pre-existing, previously unowned cave: `SummonSpells.TSummonSpell.SetupSummonSpellTE@0x557E4484`
replaced by `jmp 0x5580C500`, whose body does `cmp esi,0xE4` (Fire Sprite's `Unitres.pfs` id) then
`RandInt(5)+3` copies for that unit only, `+1` for everything else — so only the singular name was
wrong).

---

## Mind Decay — unconditional RNG draw (MP determinism) + a nil check vanilla lacks

**Status: 🔨 APPLIED, UNTESTED (2026-09-03).** Written to the live `AoWEPACK.dpl`, byte-verified, cave
disassembled and read. Nobody has played it, and the multiplayer half needs two machines.

| | |
|---|---|
| script | `build_scripts/build_minddecay_oos.py` → `AoWEPACK.dpl` only |
| backup | `AoWEPACK.dpl.pre-minddecayoos` (taken from a file proved free of this feature) |
| revert | `python build_scripts/build_minddecay_oos.py --undo` — surgical, no backup touched |
| couplings | **none** — no shared cave, no shared hook, no ordering constraint with anything else |
| rule it implements | a cave draws from the generator its host function already uses; inside combat that's RAW, and **draw *count*, not draw value, is the invariant** that must match across peers |

⚠ The script's own docstring still opens `STATUS: built and dry-run verified, NOT APPLIED` — that line
is stale; the live DLL says otherwise.

### The defect, and that it is vanilla's

A battle re-anchors `System.RandSeed` from one synchronised draw (`TCombat.Execute@0x557282C8`:
`RandSeed := TAoWHSMap.Random(map,$FFFFFF)`) and then runs the whole fight off **raw** draws,
deterministically, on every peer. Consequence: raw combat draws are invisible to the out-of-sync
comparator, but only reproduce across machines if every peer consumes the **same number** of draws — a
*conditional* raw draw diverges silently, and the resulting OOS dialog fires much later and far from
the cause. `CombatSpells.TMindDecay.CreateCA@0x557F85DC` has the widest such surface of any combat
spell: its one `HitRole` call sits behind **five** gates, four of which dereference the target's
strategic unit `[combatunit+0x4C]`. **Byte-identical to `AoWEPACK_original_backup.dpl`, re-verified
2026-09-03 — this is a stock AoW1 defect**, not introduced by this project. A second, related defect in
the same function: vanilla dereferences `[target+0x4C]` guarded only by the first gate, and that field
is legitimately allowed to be nil (in-bounds for `TCombatUnit`'s 92-byte instance, just unpopulated).

### The fix — hoist the draw, gate only the store

```
<the same five gates, no early exit>          -> eligible = 0/1
eligible ? res = target.GetResistance() : res = 0
ALWAYS   eax = [spell+0x34] - res ; call HitRole      (exactly one @RandInt, always)
eligible ? [ca+0x14] = al : leave it 0, as vanilla
```
Eligible target: identical outcome, identical draw order, identical call graph — the gates and
`GetResistance` run exactly where vanilla calls them. Ineligible target: one extra `@RandInt` is
consumed and discarded **uniformly on every machine** (same DLL, same code path) — no balance effect,
the stream is random. Plus the nil check on `[target+0x4C]`, falling through to "ineligible" instead of
crashing. Honest scope: this removes the one concrete, mechanically verifiable RNG asymmetry unique to
Mind Decay — it is not a proven root-cause fix for any specific reported desync, and every other
`HitRole` caller (`TSlow`, `TEntangle`, …) is untouched.

**⚠ Why only the `HitRole` call is hoisted, and not `GetResistance` too — worth recording because
Inioch's script gets this wrong.** `HitRole@0x55725D98` is straight-line with exactly one
unconditional `@RandInt` call regardless of its input, so passing a discarded input on the ineligible
path costs exactly one uniform draw and nothing else — the script re-asserts this against the live
bytes at write time and refuses to patch if that ever stops holding. **The *other* input is not safe to
hoist**: `TCombatUnit.GetResistance@0x557254A8` (the VMT `+0x74` override) is nothing but
`mov eax,[eax+0x4C]` followed by a virtual call through it — calling it unconditionally would
access-violate on exactly the nil-strategic-twin case the new nil check exists to fix, and would call
`TUnit.GetResistance` on a path vanilla never reaches. **Inioch's shipped
`build_minddecay_oos.py` hoists `GetResistance` out of the gate**, on the stated (and false) premise
that resistance "comes from the target's own VMT+0x74, not from `[target+0x4C]`" — his tree and ours
agree byte-for-byte on `0x557254A8`, so his version carries a latent AV on any combat unit with a nil
strategic twin, the very crash his own nil check was meant to remove. Ours hoists only the `HitRole`
call and substitutes `res=0` on the ineligible path instead — same objective, strictly smaller
behavioural delta. Worth sending back to him.

### The hook site, and a rejected alternative

Hooked at `0x557F8623` (`call 0x557010C0`, the displaced `@IsClass` thunk call) → `jmp 0x55842000`, 5
bytes for 5. A `call rel32` carries no base relocation, so `.reloc` is byte-identical before and after.
**⚠ REJECTED — do not "improve" this back to hooking `0x557F861B` instead.** That would displace the
imm32 of the preceding `mov edx,[0x55715A54]`, which carries a **type-3 HIGHLOW base relocation** at
`0x557F861F` — inside the five bytes a jmp there would overwrite. Verified live: exactly one `.reloc`
entry in the whole `0x557F8600..0x557F8640` span, at `0x557F861F`, and none inside the chosen hook
range. Handling it correctly (neutralise the entry on apply, restore on undo) was tried in an earlier
revision and round-tripped cleanly, but was dropped anyway: **eliminating the reloc-adjacency hazard
category beats handling it correctly** — Inioch's script uses the other site and does the
reloc surgery; this one simply doesn't need to. The cave's first instruction replays the displaced
`IsClass` call, so it depends on the two vanilla instructions immediately above the hook
(`mov eax,ebx; mov edx,[0x55715A54]`) staying intact, which the script pins and re-checks on every run.
A branch sweep of the whole CODE section confirmed nothing else jumps into the 5 displaced bytes.

`cave_mdroll@0x55842000` (171 bytes in a 256-byte reservation, own zone, verified all-zero, no `.reloc`
inside it, claimed by no other script) replicates the five gates (`IsClass→TCombatUnit`, the nil check,
`GetUnitType==2`, `GetRace==0x0B`, `GetAbilityEnabled(Animated 0x81)`, `IsClass→TLeader`), sets
`res=0`/eligible-flag accordingly, always calls `HitRole`, and stores the result only when eligible —
one PIC anchor (`call $+5/pop edx/sub`, **`pop edx` not `pop eax`** — AL carries the `IsClass` result at
that point), the `TLeader` classref reached delta-relative. Instance sizes checked in bounds:
`TCombatUnit` 92 (`+0x4C`), `TMindDecay` 64 (`+0x34`), `TMindDecayCA` 28 (`+0x14`).

### Two live-vs-pristine deltas a future session would otherwise trip on

Both re-measured 2026-09-03 by byte-diff against the pristine backup:

1. **`HitRole@0x55725D98` is itself modded**, by `build_hitslope5.py` — pristine
   `03 c0 8d 04 80` (`add eax,eax; lea eax,[eax+eax*4]`, ×10) is live `90 90 6b c0 05` (two NOPs then
   `imul eax,eax,5`) — the 10pp→5pp to-hit slope conversion. **The pristine decompile is the wrong
   reference for this function.** What this patch depends on (straight-line, exactly one unconditional
   `@RandInt(100)`, two forward clamp branches, neither skipping the draw) is unaffected, and the script
   prints the measured counts on every run.
2. **`CombatSpells.TMindDecay.Create` is modded (3 bytes) even though `CreateCA` is vanilla** — the
   spell's strength constant at `[spell+0x34]` (`05→0C`, the DAM/HP-doubling pass) plus two more
   single-byte deltas at `+0x39`/`+0x3A`. Still a compile-time constant written once in `Create`, never
   derived from the target — the hoist reads whatever `Create` stored either way.

### RNG audit — why the modded-site count doesn't move, and must not be forced to

The cave calls `HitRole`, which is a *caller* of the RNG, not an entry point, so `rng_audit.py --owners`
correctly reports the same 24-site total as before this patch — a cave reaching the generator through a
caller adds no site the audit can see, so **the audit proves the right generator was picked, not that
the draw count is symmetric.** The draw stays **RAW**, which is correct here (tactical combat, riding
the seed `TCombat.Execute` re-anchored) — ⚠ do **not** "fix" it to SYNCED; a synced draw here would trip
the `GetSynchronised` guard *and* perturb `[map+0x230]`. The point of this patch is draw-count symmetry,
not a different generator.

### Needs the user's in-game test

Cast Mind Decay on a valid target (unchanged behaviour expected); on each ineligible class in turn — a
Leader, an Animated unit, a race-`0x0B` unit, a `GetUnitType==2` target (nothing happens, nothing
crashes — this is the path that now consumes and discards a draw); on a combat unit with no strategic
twin if one can be produced (vanilla AVs there; this must not); a long tactical battle with several
casts (no drift in unrelated to-hit results, no "Invalid AoWHSMap.Random use" popup); auto-resolve as
well as manual combat; and — the only test that exercises the actual point of the patch — **a two-machine
MP battle** in which Mind Decay is cast at least once on an ineligible target, checked for desync.

---

## Stack size 8 → 12 — SHELVED

**Status: SPECULATIVE / SHELVED (2026-08-16) — the owner decided against the feature. Nothing applied,
no build script exists.** Seven parallel RE passes over every module, the editors, the `.pfs` data and
the `.HSM` maps (2026-08-15), independently re-verified the next day. Kept because it holds two
diagnosed **vanilla** bugs worth fixing regardless of the cap decision, and a large amount of reusable
`TArmy`/UI/cave-space machinery. No prior art existed anywhere in the project before this pass.

### The one thing to understand first

**8 is almost never a capacity constant in this codebase — it is the width of a byte.** The unit
collection itself is fine (`TArmy`'s `TList` has a 32-bit count; saves, auto-resolve and maps all take
12 without complaint). What cannot take 12 is every **selection mask** — which units are picked,
concealed, transported, deserting, enchanted — because those are `byte`-typed throughout: locals,
returns, stored fields, `1<<i` builders, `>>1` consumer loops, and `0xFF` as the "all units" sentinel at
dozens of sites. Patching only the cap immediates therefore *appears* to work — 12 units join the stack
— while units 9–12 silently can't be concealed, selected, split, transported or enchanted, and vanish
from every `TArmyView` fog-of-war snapshot. **Hard ceiling for the whole game is 16**:
`TCombatUnit+0x46` packs `party<<4 | slot` into one byte (`0x80`=wall sentinel), so 16+ corrupts the
party nibble regardless of any `TArmy` cap.

### ⚠ Bug 1 — `TGeneral` slot-array overflow (VANILLA, live today, independent of any cap change)

**A crash that already exists in the shipped game** — the stack-12 research merely makes it routine
(the wide merge described in the [double-stack section](#seduce--charm--dominate--two-stacks-on-one-hex)
below is a proven vanilla route to ≥10 visible units today). Fix is fully specified; **no build script
exists yet** — this is the "do first, independent of the cap decision" item.

`TMapEvents.TheMapArmySelected@0x0044EC30` (AoW.exe) fills `TGeneral`'s slot array (`array[0..7] of
Integer` at instance `+0x84..+0xA0`, VMT `0x00453FC4`, instance `0xCC`) with a loop bounded only by the
army's unit count — **no upper bound on the write index**:
```
0044EC65  xor ebx,ebx                          ; unit index
0044EC7A    call [ebp+0xb8]                     ; GetUnitConcealedForPlayer — concealed units skip a slot
0044EC8E    mov [General+edx*4+0x84], ebx       ; *** NO UPPER BOUND on edx (the slot counter) ***
0044ECA3  mov [General+0xa4], edi               ; selected-army pointer, written AFTER the fill loop
```
**Severity, precisely:** the 9th *visible* unit writes `+0xA4` but that's immediately overwritten with
the correct army pointer two instructions later — harmless. The first **unrepaired** corruption is the
**10th** visible unit, writing `+0xA8`; 11th → `+0xAC`; 12th → `+0xB0`.

| offset | field | effect of a stray small integer |
|---|---|---|
| `+0xA8` | `SelectedStructure: TStructure` — live object pointer, 26 read sites | 💥 **CRASH** — every reader does `mov edx,[eax]` / virtual dispatch / `@IsClass` with no nil-safe path for a small non-nil garbage value |
| `+0xAC` | previous selected structure, write-only, **never read anywhere in AoW.exe** | harmless — dead field |
| `+0xB0` | `SelectedCity: TCity` — live object pointer | 💥 **CRASH**, narrower window (needs a city window open) |

Every consumer nil-guards (`test ebx,ebx / je skip`), but the corrupted value is **never nil** (it's the
unit's index, ≥9), so it sails straight through into a dereference of address `0x00000009`-ish.
`TheMapArmySelected` never heals `+0xA8` itself, so the bad value persists until the next
structure select/deselect; `TheMapStructureDestroyed` also silently fails to deselect a destroyed
structure while garbage sits there, leaving a dangling pointer in an open window.

**Fix: bound the loop at 8. Do not relocate the array** — the slot array is the model behind the
8-control unit bar (`TControlWin` has exactly 8 DFM component sets), so units 9–12 have nowhere to draw
regardless; displaying them is a separate, much larger UI feature (below). Hook budget: 15
`.reloc`-free bytes at `0x0044EC89..0x0044EC97`, entered only by fall-through — `E9 rel32` + NOPs into a
small cave (an in-place `cmp/jae` needs 17–19 bytes and doesn't fit). Patch `AoWzCompat.exe` in
lockstep. If the array is ever widened instead of merely bounded: instance size lives at
`[0x00453FC4-0x1C]` (`0xCC→0xFC`, 12 dwords), and 18 further read/write sites across the slot painter,
mouse handlers and prev/next-click wraparound would need repointing — not needed for the bugfix alone.

**Open:** whether the vanilla ≥10-unit crash is reproducible has never been tested in-game — build the
overcap army via the double-stack mechanism below, select it, and watch the structure-info panel.

### Bug 2 — Seduce/Charm/Dominate double-stack

Diagnosed but unconfirmed; kept in its own section since it stands on its own —
see [below](#seduce--charm--dominate--two-stacks-on-one-hex). **Treat the two as one defect for
scoping purposes**: the same unbounded merge this section's overflow bug depends on
(`TArmyCombatMoveTE.ExecuteCombat`, no `CanAddUnit` call) is *also* the double-stack bug's prime
suspect for how a stack exceeds its cap in the first place.

### Reusable machinery

**The four cap immediates, and what they actually gate.** `TArmy.MaxSize@0x5578DEF4` (`mov edi,8`,
`0x5578DEFB`), `CanAddUnits@0x5578E3CC` (`cmp ebx,8`, `0x5578E4A4`), `CanAddUnitSelection@0x5578E55C`
(`cmp eax,8`, `0x5578E666`), `CanCombine@0x55790814` (`mov [esp+4],8`, `0x5579086B`) — all four
byte-exact and identical to pristine as of the 2026-08-15 pass. ⚠⚠ **These are only the
no-transporter fallback branch** — `CanCombine`/`CanAddUnits`/`CanAddUnitSelection` actually take their
ceiling from `Transporter(self,0xFF)==nil ? 8 : capacity+1`, and **`MaxSize` is the canonical cap but
only `TArmy.CanAddUnit` (VMT `+0xA4`) calls it** — the other three carry their own literal and never
consult it, so patching `MaxSize` alone does nothing for join/merge/multi-add.

**Transport capacity is a *lowering* mechanism, not a separate cap** — it's why 7 (a boat's capacity)
and 8 (the base cap) coincide: `MaxSize` starts at 8 and is lowered to `capacity+1` if any unit in the
stack has nonzero transport capacity. That capacity byte is **`Unitres.pfs` tag `0x18`**
(instance `+0x44` vanilla, `+0x32` after `build_copper_medal.py` moved it — the pfs tag is unchanged).
⚠ **Raising this tag ahead of the code immediates is a dangerous edit** — it silently raises the
*effective* cap for boat stacks to 12 immediately, ahead of every byte-mask safeguard below, so **the
transport data edit must land last in any staged build, never first.** Six of eleven transport-capable
units (Air Galley, Sandworm, Cog, Carrack, Guild Zeppelin, Supply Caravan) already sit at the current
max of 7 and are the ones that would visibly stop scaling; five more are deliberate Ziggurat balance
values below 7 and are a balance call, not a mechanical one.

**The byte-mask surface is large, and any inventory of it should be treated as incomplete until
mechanically re-derived** — a spot census of just 2 of 12 known masking idioms across the DLL found 30
enclosing functions where an earlier hand-built list named 16; roughly 15 appear in no document at all.
Known mask-bearing fields: `TArmy+0x2A` (concealed-units bitmask, 1 byte, not serialised — `+0x2B` is
free, confirmed by `fieldrefs.py --validate`, but `+0x29` is not, it's the vision-range nibble pair);
`TUnitSpellCaster+0x18/0x19/0x1A` (selection/multi-flag/valid-target masks, one spare byte at `+0x1B`);
`TUnitSelector+0x14/0x15/0x16` (same shape); `TSelectedArmy`'s selection storage is already a dword,
only the producer and one byte-read narrow it — cheapest widening point in that chain; and four
DATA-section count→mask lookup tables (`00 01 03 07 0F 1F 3F 7F FF`, 9 entries padded to 12 bytes) feeding
`ValidateSelection`/`SelectionCount` at three addresses, only one of which clamps — an unclamped read at
12 units returns whichever stray byte follows the table, observed to untick every checkbox or select
none at all. ⚠ A **live mod cave** is also a mask consumer: `build_patch.py`'s cave at `0x5580D700`
reads two byte-sized locals owned by the very functions it hooks — widening either host local without
updating the cave would silently read the wrong byte (no crash, just a wrong movement overlay), and this
is invisible in Ghidra (vanilla image). **Strategy, if ever revisited:** widen byte→**dword** in flight
everywhere (not word) — the opcode pairs are all one-for-one length-preserving (`8A↔8B`, `88↔89`, etc.).

**Persistence needs no work at all.** An army's unit list is a nested property-table directory whose
loop bound is its own entry count (same directory format as `.pfs`, see above) — the load path never
consults `CanAddUnit`/`MaxSize`, so an unpatched build would *load* a 12-stack without dying; only the
downstream selection/UI logic misbehaves. No hardcoded 8 exists anywhere in campaign/scenario/victory
data.

**Cave-space budget, as of 2026-08-15 (re-derive before trusting any of this — it is a moving
target):** `AoWEPACK.dpl` CODE highest-used `0x55817800`, allocate from `0x55818000`, ceiling
`0x558E7000`; BSS mutable state around `0x558FA844..0x558FB000`. `AoWz.exe`: **3 PE header slots free**
(120 zero bytes spare in the section table), plus the `.hcol` tail — 40,580 zero RWX bytes from
`0x62417C` — good for 3 more sections; `AoWDevEd.exe` has 1 header slot, `AoWEd.exe` 7.
`AoWTCPCK.dpl`: 191 KB zero run from `0x438080`. Two recorded near-misses: two unrelated scripts both
independently picked `0x55812000` as "obviously free" — **never assume a round address is free, scan
first** — and a BSS grep for the literal `0x558FA8` misses computed claims like `SCRATCH+1`.

**Race-banner ILB id maps (the map-hex stack-count digit).** Two mutually exclusive families:
unowned stacks draw from `Flags.ilb`/`_Flags.ilb` at `count+0x27` (ids 40–48 = counts 1–9, **49–51 do
not exist** — next id is 70, so 49–69 is a genuinely free 21-id gap); owned stacks draw from the
army's **race** ILB (one of 12, `Images/Races/R*.ILB`) at `count+0x1D`. ⚠⚠ **The blocker**: race ILB
ids 40/41 — exactly where counts 11/12 would land — are **already the city-border art**
(`BCS_*.BMP`), actively read elsewhere. Counts 10–12 for owned stacks therefore need a code cave
redirecting to a free block instead of a simple append; **ids 24–27 are free in all 12 race ILBs and
read by nothing** — the safe target. The unowned family needs no code change at all, just 3 appended
sprites. `ImageLib.Get` has no bounds check and no nil check, so an unhandled count ≥10 for an owned
stack today would access-violate in 11 of 12 races (inference from static analysis, not observed).

**The `.HSM` tactical-deployment marker pass — a genuine technical blocker, not a taste call.**
Deployment position is `TUnitPositionControl`, indexed `party*8+slot` (13 all-imm8, all
`.reloc`-free sites, stride `08`→`0C` trivially) — but `PlaceCombatUnits`' item-scatter block
separately indexes an 8-entry local by `Random(XYLList.Count−17)`, range-checked `bound{0,7}`.
**Adding markers to a map, or merely widening the stride, pushes that index out of range** and faults
entering a Crypt/Monster-Lair/Ruin/Ziggurat battle (Dungeon is exempt) once the marker count reaches
≥25 **and** the site holds ≥1 item. ⭐ **The escape hatch: placement already spirals.**
`SetupUnit` does not place a unit at its marker hex — it runs an uncapped spiral search for the nearest
free, non-obstacle hex. So the minimal viable version needs **no `.HSM` editing at all**: patch the
stride to 12, fall slots 8–11 back to `slot mod 8`, and let the existing spiral resolve the resulting
duplicate deployment hexes (cost: sloppier formations only). **Recommendation if this is ever
revisited: skip the marker pass permanently** rather than patch the scatter block too.

**Balance consequences that scale automatically** (dynamic list walks, ~50% stronger at 12 with no
code change): Drillmaster's per-turn XP aura (ceiling +7→+11 XP/turn), Leadership's beneficiary count,
Vision's stack-maximum. **Consequences needing a deliberate decision**: `GenerateRazeDefenders`'s
raze/rebellion roster stays hard-capped at 8 (`83 F8 08` trim, independent of `TArmy`) — a silent
balance tilt toward the player if the player cap moves and this doesn't; the raze combat predictor's
calibration and named regression tests are built on 8-vs-8 and would need re-baselining;
`build_crusade_spawns.py`'s `ARMY_CAP=8` and its hand-tuned spawn table; `build_party_random.py`'s
"Large" party composition, which implicitly maxes at exactly 8.

---

## Seduce / Charm / Dominate → two stacks on one hex

**Status: SPECULATIVE — mechanism diagnosed (v2), no patch, not tested in-game.** Reported symptom:
acquiring a unit via a Command ability *sometimes* leaves multiple stacks on the same hex.

⚠⚠ **The v1 finding ("vanilla behaviour, not a Ziggurat regression") was wrong and is retracted** — it
checked only the 20 functions on the capture path itself. **Three functions on the *move/attack* path
are live-patched by the movement-predictor script** (see the booby trap above) — `TMoveArmyTE.Setup
@0x55747B01`, `MoveArmyEx@0x5574A36E`, `TSelectedArmy.Update@0x557936A3` — and that patch's cave at
`0x5580D700` reads byte-sized locals owned by two of those hosts' stack frames. So **whether this bug
reproduces in unmodified vanilla, or is entangled with that patch, is unconfirmed** — the diagnosed
mechanism below is real and code-verified (`FinishMove` really does ignore a merge refusal), but
settling "vanilla or regression" needs an A/B with that script's cave manually zeroed first
(**never** via `--apply`/`--undo` — see the booby trap), which has not been done.

### The mechanism (v2)

Arrival **does** attempt to merge, in `TMoveArmyTE.FinishMove@0x55747FBC`: it finds a stationary army
on the destination hex (`GetNoneMovingArmyHS`) and calls `AddUnitSelection(stationary, moving, 0xFF)`.
That call is **all-or-nothing behind `CanAddUnitSelection`** (0=OK, non-zero=refusal code) — and
**`FinishMove` ignores the return value** (instrumentation point: `0x5574802D`), then clears the
"moving" flag on the *wrong* army regardless. When the merge is refused — because the combined count
exceeds the cap — the result is two `TArmyHS` left on one hex, with the loser flagged "moving"
(`army[+0x11] & 4`) and therefore **invisible to every future `GetNoneMovingArmyHS`** — it can never be
merged away while the flag stands. ⚠ Not permanent: `TArmy.ReadWrite` force-clears bit 4 on every save
load, so "reloading fixes the stuck army but not the doubled hex" is exactly what this mechanism
predicts. A Command capture supplies exactly the extra unit needed to push a merge over the cap, which
is the "sometimes".

**Why two armies on one hex is possible at all:** a map field holds a *list* of hotspot children, and
`Get(classid)` returns only the first match — two armies per field is legal and designed (`ExecuteCombat`
deliberately detaches itself from its own field so `GetArmyHS` returns *the other* army there).
`TArmyHS.PlacePrivate@0x55791278` is the **only** same-hex placement bypass in the game, with exactly
two deliberate callers (a partial-stack move's temporary split, and this post-combat re-split);
everywhere else, `PlaceHX` refuses a same-hex second army outside the editor.

**The consequence is the opposite of the obvious guess — it doesn't crash combat, it hides from it.**
`TCombat.AddAdjacentArmies` calls `field.Get(classid)` once per hex, so the second army is **never
added to the combat at all** — attack a doubled hex and only one of the two stacks defends, the other
sits untouched on contested ground. 43 sites across the DLL use the same classid and every one sees
only the first army in the field's list — this is the sharpest available in-game test of the whole
diagnosis (no code changes needed to try it).

**The over-cap producer, now the prime suspect for how a stack exceeds its cap in the first place:**
`TArmyCombatMoveTE.ExecuteCombat@0x55749A48` merges a second army sharing the mover's hex via
`myArmy->vmt[0xAC]` with **no `CanAddUnit` call** — an army above the cap can already exist in vanilla
today, with no patch. `FinishMove`'s refusal-ignoring merge then can't merge it away and misfiles the
flag. *(Inference from the code; the case has not been constructed in-game.)* Shared with
[the `TGeneral` overflow bug](#-bug-1--tgeneral-slot-array-overflow-vanilla-live-today-independent-of-any-cap-change)
above as one defect for scoping purposes.

**Ruled out — do not re-derive:** "`Place` spills into a second army on the same hex" — `Place`/`CanPlace`
create a new army only where the destination field is empty; a full destination spirals to a *different*
hex instead (up to ring 30), never a same-hex second army. "The capture path calls `AddUnit` without
`CanAddUnit`" — unreachable on that path without `CanAddUnit` passing first. "Raising the cap to 12
fixes the double-stack bug" — it only makes the triggering refusal *rarer* (masked, not fixed); the
refusal-ignoring code itself is untouched either way. A v1 theory involving a stale bit on the wrong hex
(`TCombatData+0x08/0x0C/0x10` is the *target* hex; the post-combat split re-acquires at the *origin*)
was also wrong and is not worth re-deriving; msg `0x1141` has no handler anywhere in the DLL and is not
a delivery path for anything.

**Corrections made at source in a related doc (2026-08-15):** a nerf design for Command abilities had
two errors that changed its feasibility verdict — the controller's victim list is a `TByteList` of
**per-battle combat-object ids**, not persistent unit ids, so it does not survive a battle and must be
rebuilt by any nerf; and it stores the victim's original **side**, not player, so a nerf must separately
stash the owning player.

---

## Transport-boarding "units vanish" bug

**Status: SPECULATIVE — static code analysis only, no patch, no known repro.** Reported symptoms: units
(especially lone leader-heroes) rarely disappear when moving into a transport; seems correlated with
movement direction and whether the leader is travelling alone.

This shares its root cause's DNA with the double-stack bug above — both go through
`TMoveArmyTE`/`FinishMove`/`GetNoneMovingArmyHS` and the same "moving" flag (`army[+0x11] & 0x04`),
diagnosed independently on 2026-07-05 (this bug) and 2026-08-15/16 (double-stack v2); the two source
analyses never cross-referenced each other, but the mechanisms are clearly siblings within one
under-checked subsystem.

**The pipeline:** at path-time, entering an occupied friendly hex is allowed by
`CanCombine(hexArmy, mover, selectionMask)` — capacity check against transporter capacity+1 (or 8).
Per hex, `TMoveArmyTE.ExecuteMove` calls `TArmyHS.MoveTo`, which broadcasts field messages 0x1140
(may-I-leave)/0x1141 (may-I-enter) — either may **veto**, leaving the army HS on the old field — then
reparents, validates (culling dead units), and broadcasts 0x1142 (entered — how storms deal damage).
**`ExecuteMove` ignores `MoveTo`'s return value** and conflates two different situations: the army
legitimately dissolved (died en route/merged, intended) vs. **the move was vetoed and the army still
sits on the OLD field** — the TE abandons it silently, and because `FinishMove`'s cleanup is guarded by
`te.army != 0`, the moving flag is **never cleared** in the veto case. At arrival, `FinishMove` detaches
the mover, finds a combine partner via `GetNoneMovingArmyHS` (**skips any army with the moving flag
set**), and merges — silently doing nothing on refusal, exactly as in the double-stack mechanism above,
but this time re-pointing `te.army` to the partner and clearing the flag **on the transport, not on the
mover** if a partner was found at all.

**Three failure modes, each producing a "vanished" unit:**

- **(A) Silent merge failure at arrival.** The path-time capacity check and the arrival-time check are
  different code evaluated at different times; if army composition or capacity drifted between them
  (multi-hex/multi-turn moves, simultaneous-turn MP, mid-path storm losses, another army merging into
  the transport first), the final check can fail with no transfer, no error, and the mover left as a
  second, hidden army on the transport's hex — with its moving flag leaked set, per the mechanism above.
- **(B) Transport busy / flag deadlock.** If the transport itself already carries the moving flag at the
  mover's arrival, `GetNoneMovingArmyHS` returns NULL — no merge is even attempted.
- **(C) Vetoed move mid-path.** Any 0x1140/0x1141 veto abandons the army on its old hex with the flag
  stuck, per `ExecuteMove`'s conflation above — permanently unmergeable, and the seed for the compound
  scenario below.
- **Compound — "the cursed transport":** if a transport itself ever goes through scenario C (or
  otherwise leaks the flag), it keeps it forever; from then on, *every* army that subsequently boards it
  hits scenario B and piles up as hidden second armies on its hex, one after another — a single rare
  event producing repeated, location-flavoured vanishings around one specific boat, which matches the
  reported symptom shape well.

**How the reported clues map:** rare — needs state drift, a veto, or a flag leak, all uncommon
individually; direction-dependent — approach direction changes the flood-fill path (which hexes are
crossed, how many moves remain this turn, where the move actually terminates) — direction is a proxy,
not a cause; leader-alone-vs-not — decides whether `InitializeMove` walks the *original* armyHS (with
its accumulated flag history) or a *fresh* one for a sub-selection move, giving each case different
susceptibility to a leaked flag.

**Hardening candidates (none applied, none tested, and each touches a code path with
network/AI implications, so none should ship untested):** in `FinishMove`, check
`AddUnitSelection`'s result and clear the moving flag on the *mover* on failure, before the `te.army`
swap; in `ExecuteMove`, use `MoveTo`'s return value — on veto, keep `te.army` and finish the move
normally on the old hex so `FinishMove`'s cleanup actually runs; in `FinishMove`, if
`GetNoneMovingArmyHS` returns NULL on a hex that visibly contains a same-player army, retry ignoring the
flag (or clear a stale flag when the flagged army has no active move TE). All three are small,
same-style cave patches to the movement code.

---

## Firmament map level — a 4th map level at index 3

**Display name: Firmament.** The level is deliberately named apart from the Sky *terrain* (`0x0E`)
that fills it; `build_maplevel4.py` / `build_skylevel_ui.py` keep their filenames, and every
user-visible string says Firmament.

🔨 **APPLIED, UNTESTED (2026-09-06)** — DLL half, **v2**. `build_maplevel4.py` (cave `0x55844000`,
250 B, eight hooks + the cap byte), plus in-place cave re-tunes of `build_shipyard_income.py` and
`build_waterheal.py` (**v6**).

### Firmament level, UI half — `build_skylevel_ui.py` 🔨 APPLIED, UNTESTED (2026-09-06)

The four exe sites that assumed `slot == level` now go through a display-order table.
Storage is unchanged: the Firmament is level index 3; only the strip's ordering moves.

| levels on the map | slot 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| more than 3 | 3 (Firmament) | 0 (Surface) | 1 (Caverns) | 2 (Depths) |
| 3 or fewer | identity — vanilla behaviour, three tabs |

Count is read live every time, from `[[[0x0045DF7C]] + 0x10] + 0x14` (`0x0045DF7C` is the
import slot holding **&TheMap**, `+0x10` its `TMapContainer`, `+0x14` the level count), so a
3-level map is untouched by this patch. Written to **`AoWz.exe` and `AoWzCompat.exe`**, byte-identical.

**Sites** (AoWz.exe VAs, base `0x400000`; all byte-verified against the live file before patching):

| site | before | after |
|---|---|---|
| caption fill, hook `0x00454FED` (11 B) | `8b 80 14 01 00 00 8b 10 ff 52 40` (`mov eax,[eax+0x114]` / `mov edx,[eax]` / `call [edx+0x40]`) | `e9 4e 50 1d 00` + 6×`90` → `cave_caps` |
| `TSWindow.ScannerTabChange @0x00451BC8`, hook `0x00451BDC` (5 B) | `83 ea 01 72 07` (`sub edx,1` / `jb 0x00451BE8`) | `e9 27 85 1d 00` → `cave_tabsel` |
| `TMWindow.MapViewerSceneChanged`, `call` at `0x00451145` | `e8 9a 20 fb ff` (→ `TAOWTabPanel.SetIndex 0x004031E4`) | `e8 06 90 1d 00` → `cave_setidx` |
| `MapWindowKeyDown`, `0x004514BF` | `4a e8 8f 09 fb ff` (`dec edx` / `call SetSceneL 0x00401E54`) | `90 e8 af 8c 1d 00` → `cave_lvlup` |
| `MapWindowKeyDown`, `0x004514D5` | `42 e8 79 09 fb ff` (`inc edx` / `call SetSceneL`) | `90 e8 dd 8c 1d 00` → `cave_lvldn` |

The containing function of the caption block is **`0x00454D2C`**, not the published export
`TGeneral.ManagerDebugMessage @0x004548F4` (that is a separate, smaller routine). Its prologue loads
`ebx = [0x0045A1C0]` (&TSWindow) and `esi = [0x0045DF7C]` (&TheMap) and never reloads either, so
`cave_caps` reuses both exactly as the vanilla block does, along with the AnsiString temporaries
`[ebp-0x14]` / `[ebp-0x10]` and the function's own finally block. Its string handling is a verbatim
mirror of the vanilla `LoadResString` → `TranslateRStr` → `Add` sequence, three times over.

**Cave `0x0062A000..0x0062A3FF`** — section `.hcol` (RVA `0x212000`, file `0x20C200`,
characteristics `0xE0000060` = read/write/execute), file offset **`0x00224200`**. Verified all zero,
and inside that section's `0x8E84`-byte zero run starting at `0x0062417C`. 512 of 1024 bytes used (v3, 2026-09-06 — see the v3 note below for the layout history).
Absolute addressing throughout (exe, fixed base). No RNG draw of any kind; no resolved filesystem path.

| offset | contents |
|---|---|
| `0x0062A000` | `ORDER[4]` slot→level = 3, 0, 1, 2 |
| `0x0062A010` | `RORDER[4]` level→slot = 1, 2, 3, 0 |
| `0x0062A020` | Delphi 3 const AnsiString "Firmament": `ff ff ff ff` (refcount −1), `09 00 00 00`, chars at `0x0062A028` (record ends `0x0062A031`) |
| `0x0062A040` | `cave_caps` (199 B) — Clear, `Add("Firmament")` when count > 3, then the three vanilla resource Adds, `jmp 0x0045508F` |
| `0x0062A108` | `cave_tabsel` (72 B, since v2) — slot `< 0` or `≥ count` → `jmp 0x00451C4C` untouched (vanilla’s whitelist; a `TAOWTabPanel` with nothing selected reports −1 and `THSMap.ViewLevel` has no lower bound); else slot→level, `[Scanner+0x17C] = −1`, `call [vmt+0xB8]` (`THSMap.ViewLevel`), `jmp 0x00451C4C`. The no-arg run reports an installed v1 as "needs re-tune", never as applied |
| `0x0062A150` | `cave_setidx` (36 B) — level→slot, tail-`jmp 0x004031E4` |
| `0x0062A174` | `cave_lvlup` (65 B) — level→slot, slot−1 clamped ≥ 0, slot→level, tail-`jmp 0x00401E54` |
| `0x0062A1B8` | `cave_lvldn` (72 B) — level→slot, slot+1 clamped ≤ count−1, slot→level, tail-`jmp 0x00401E54` |

Refcount −1 makes the literal a Delphi constant string: `_LStrAsg` skips the increment on a negative
refcount and `_LStrClr` skips the decrement, so it is never written and never freed. There is no
translated resource id for "Sky" — AoW.exe's STRINGTABLE block (65524/65525/65526, `PResStringRec`s
`0x00403414/1C/24`) is full — hence an English cave literal, in contrast to Surface/Caverns/Depths
which still go through `TranslateRStr` against `Dict/ResStr.mld`.

The PgUp/PgDn caves clamp the **slot** before the slot→level conversion, which is required because
the `ORDER` table is not monotonic in level — `SetSceneL @0x5560EDD0` itself already clamps both
ends, so the caves are not removing a vanilla clamp, they are adding one earlier in the pipeline
that the level remap makes necessary.

**Dead code left in place, deliberately.** The vanilla caption block `0x00454FF8..0x0045508E` keeps
its three base relocations (`0x00454FFC`, `0x00455032`, `0x00455068`), and the three vanilla
`ScannerTabChange` arms
(`0x00451BE8` / `0x00451C08` / `0x00451C2B`) keep theirs. Verified unreachable: zero branches from
outside into either region, and zero absolute dwords anywhere in the image pointing into them.

**⚠ Do not hook the caption fill at `0x00454FF8`.** It is the obvious site — the head of the first
`Add` block — but a 5-byte `E9` there covers `0x00454FFC`, which carries a type-3 base relocation
(the `0x45a0c0` dword of `mov eax,[0x45a0c0]`); a rebased load would apply the fixup on top of the
jump. `0x00454FED..0x00454FF7` carries no relocation at all: the `.reloc` directory holds exactly one
entry in `0x00454FE0..0x00455000`, and it is `0x00454FFC`. `0x00451BDC..0x00451BE0`, `0x004514BF`,
`0x004514D5` and all three retargeted rel32 operands are likewise relocation-free.

**`--undo`** is surgical and touches no backup: it restores the 11 displaced bytes, the 5 displaced
bytes, `4a`, `42`, all three rel32s, and zeroes the 1024-byte cave — refusing if the cave holds bytes
the script did not write. Round-tripped 2026-09-06: the undone files are SHA-256-identical to
`Ziggurat\backups\AoWz.exe.pre-skylevelui` / `Ziggurat\backups\AoWzCompat.exe.pre-skylevelui`.

**In-game checklist (needs the user):**

- [ ] On a 4-level map the World Map strip reads **Firmament | Surface | Caverns | Depths**, left to right.
- [ ] On a 3-level map it still shows exactly three tabs, **Surface | Caverns | Depths**, and the
      captions are the translated ones.
- [ ] Clicking **Firmament** shows level 3; clicking Surface/Caverns/Depths shows 0/1/2.
- [ ] The pressed tab follows a level change made by any other route (scrolling, a unit selection,
      PgUp/PgDn) — not just by clicking.
- [ ] **PgUp** from Surface goes to the Firmament; **PgDn** from the Firmament returns to Surface.
- [ ] **PgUp** while on the Firmament does nothing; **PgDn** while on Depths does nothing.
- [ ] On a 3-level map PgUp/PgDn still walk Surface ↔ Caverns ↔ Depths and stop at the ends.
- [ ] Both `AoWz.exe` and `AoWzCompat.exe` still launch.

---


The whole vanilla ceiling was one immediate byte; every other layer is count-driven off
`TMapContainer+0x14`. The Firmament is **level index 3**, filled with terrain `0x0E` (SKY, flyer-only + bridges
— `09-terrain-movement.md`), and is treated as **surface** by vision and by the global-target spell
gate. User rulings: the 6-hex border ring stays, earth elementals do not heal there, **air
elementals do**, and storm spells and Bird's View follow the global-target ruling. **Towers can be
built on it**, as they can on every level — the tower gate is dead on this install (below).

### UI half, v3 — the caption is "Firmament"

`build_skylevel_ui.py` v3 (`AoWz.exe` + `AoWzCompat.exe`). Status `🔨 APPLIED, UNTESTED
(2026-09-06)`. The level strip's 4th tab now reads **Firmament**. The *terrain* on that
level is still called **Sky** — only the World Map tab caption changed.

The caption is a Delphi 3 constant AnsiString in the cave (`refcount = -1`, then the length,
then NUL-terminated characters). Growing "Sky" (3) to "Firmament" (9) grew the record from
12 to 18 bytes, so the code base moved `0x0062A030 → 0x0062A040` and every one of the five
replacement byte-runs moved with it — the script derives all five from the assembled layout,
so this was a plain in-place cave rewrite with no revert step and no backup touched.

    cave 0x0062A000..0x0062A3FF (section .hcol, file offset 0x00224200), 512 of 1024 B used

    0x0062A000  ORDER[4]   slot  -> level  = 3, 0, 1, 2
    0x0062A010  RORDER[4]  level -> slot   = 1, 2, 3, 0
    0x0062A020  ff ff ff ff  09 00 00 00  "Firmament\0"     (record 0x20..0x31)
    0x0062A040  cave_caps    199 B     (was 0x0062A030 in v1/v2)
    0x0062A108  cave_tabsel   72 B
    0x0062A150  cave_setidx   36 B
    0x0062A174  cave_lvlup    65 B
    0x0062A1B8  cave_lvldn    72 B     end 0x0062A200

The five sites are unchanged from v2; only their rel32s moved:

| site | v2 bytes | v3 bytes |
|---|---|---|
| caption fill `0x00454FED` (11 B) | `e9 3e 50 1d 00` + 6× `90` | `e9 4e 50 1d 00` + 6× `90` |
| tab change `0x00451BDC` (5 B) | `e9 17 85 1d 00` | `e9 27 85 1d 00` |
| SetIndex call `0x00451145` (5 B) | `e8 f6 8f 1d 00` | `e8 06 90 1d 00` |
| PgUp `0x004514BF` (6 B) | `90 e8 9f 8c 1d 00` | `90 e8 af 8c 1d 00` |
| PgDn `0x004514D5` (6 B) | `90 e8 cd 8c 1d 00` | `90 e8 dd 8c 1d 00` |

`cave_caps`'s only content change is `mov edx, 0x62a028` now pointing at `'F'` of
"Firmament" instead of `'S'` of "Sky" — the pointer VA is the same because the record header
is still at `0x0062A020`.

**v3 recognises three installed states.** `--apply` accepts `orig`, `v1`, `v2` or `v3` at
every site and rewrites the cave in place; the report calls v1 and v2 "needs re-tune", never
"patched". `--undo` restores the five original byte-runs and zeroes the 0x400-byte cave, and
refuses if the cave holds bytes none of the three builds would have written.

Hashes: `AoWz.exe` `6cac62eb…b096b` (v2) → `70eb5570…a924c` (v3); `AoWzCompat.exe`
`6dc0f192…cf4b6b` (v2) → `8b9d87eb…fd0d70` (v3). The two files still differ in exactly one
byte, file offset `0x0003BB7C` (the script asserts this after every write). A full
`--undo` / `--apply` round trip was run and reproduced the pre-feature backups exactly
(`3cde90f2…` / `c3cd753f…`).

### Editor Level Up / Level Down follow the display order

`build_deved_levelnav.py` — new, `AoWDevEd.exe` **and** `AoWEd.exe`. Status
`🔨 APPLIED, UNTESTED (2026-09-06)`.

**The report.** After Add Level, the editor's Level Up / Level Down speed buttons put the
new level below Depths: they step the *stored* level by ∓1, and the 4th level is stored at
index 3. With the game showing it above Surface, Firmament was unreachable from Surface in
the editor.

**The fix.** Both handlers now step the *slot*: level → slot (RORDER), slot ∓1 clamped to
`[0, count−1]`, slot → level (ORDER); identity when the map has 3 levels or fewer, so a
3-level map is byte-for-byte vanilla behaviour. Level count is read live from
`[[[MAPGLOB]] + 0x10] + 0x14` — the exact chain vanilla's own Level Down already walks.

Shared facts for both handlers: `THSMEdit = [TMainForm+0x22C]`; the current level is the
**signed byte** `[THSMEdit+0x21D]`; both hook sites sit after vanilla's "map loaded" guard
`[THSMEdit+0x1BC] != 0`, so the map pointer chain is known valid.

`AoWEd.exe` carries the same handler bodies at **AoWDevEd address − 0x64** in this region,
but different import thunks and a different map global, so every site is declared and
byte-verified per binary.

| | AoWDevEd.exe | AoWEd.exe |
|---|---|---|
| map global | `0x0043289C` | `0x00432898` |
| `TPageControl.SetActivePage` thunk | `0x004023F0` | `0x004023E8` |
| `THSMEdit.SetSceneLevel` thunk | `0x00402E38` | `0x00402E28` |
| `LevelUpBtnClick` | `0x00429ED8` | `0x00429E74` |
| `LevelDownBtnClick` | `0x00429D80` | `0x00429D1C` |
| `SetMapLevel` | `0x00429C68` | `0x00429C04` |

**The four hook sites** (AoWDevEd addresses; `AoWEd` in brackets):

1. **Level Up compute** — hook `0x00429F06` [`0x00429EA2`], **30 bytes** → `E9 <cave_up>` +
   25 nops.
   Replaced: `cmp byte [eax+0x21d],0 / je noop / movsx edx,byte [eax+0x21d] / sub edx,1 /
   jno / call System.@IntOver`
   (`80b81d020000000f84c80000000fbe901d02000083ea017105e8fc70fdff`).
   The cave maps level→slot, refuses at slot 0 by jumping to the function's own no-op exit
   `0x00429FDB` [`0x00429F77`], else steps the slot down, maps back and resumes at
   `0x00429F24` [`0x00429EC0`] — vanilla's `bound edx,[0x0042A00C] / call SetSceneLevel`,
   left intact.
   ⚠ **The displaced range stops at `0x00429F23` deliberately.** `0x00429F26` is the
   absolute dword of `bound edx,[0x0042A00C]` and carries a type-3 base relocation; a longer
   displacement would have the loader apply that fixup on top of cave code. `0x00429F06..
   0x00429F23` carries none. The script re-derives this from the `.reloc` directory of each
   binary on **every** run (dry run included) and aborts if it ever stops being true.

2. **Level Down compute** — hook `0x00429DAE` [`0x00429D4A`], **17 bytes** → `E9 <cave_dn>` +
   12 nops. Replaced: `movsx edx,byte [eax+0x21d] / add edx,1 / jno / call System.@IntOver`
   (`0fbe901d02000083c2017105e86172fdff`).
   The cave maps level→slot, refuses when `slot+1 >= count` by jumping to `0x00429E9F`
   [`0x00429E3B`], else steps the slot up, maps back and resumes at **`0x00429DE4`**
   [`0x00429D80`]. That skips vanilla's `level+1 == count` test *and* its second copy of the
   increment, `0x00429DBF..0x00429DE3`, which become dead code — **left in place** so their
   relocation at `0x00429DC1` stays valid, exactly as `build_skylevel_ui.py` leaves its own
   dead caption block for the same reason.

3. **Level Up's page-control flip** — hook `0x00429FB5` [`0x00429F51`], **9 bytes** →
   `E9 <cave_upflip>` + 4 nops. Replaced: `cmp byte [eax+0x21d],0 / jne` (`80b81d020000007511`).
   Vanilla activates the surface page `[TMainForm+0x244]` only when the new level is 0; the
   cave activates it when the new level is 0 **or 3** (`mov dl,[eax+0x21d] / dec dl /
   cmp dl,1 / ja set`), so Firmament shows the surface page rather than the underground one.
   Both of vanilla's own branch targets are re-used — `0x00429FBE` sets the page,
   `0x00429FCF` leaves it — so no code is duplicated.
   **Level Down's flip is deliberately NOT touched.** A down step can only ever land on
   levels 0..2, and vanilla's `cmp byte,0 / jle` already leaves the surface page alone for 0
   and picks the underground page for 1 and 2.

4. **`TMainForm.SetMapLevel`'s flip** — hook `0x00429D14` [`0x00429CB0`], **23 bytes** →
   `E9 <cave_smp>` + 18 nops. Replaced: `test esi,esi / jle surface / mov edx,[ebx+0x284] /
   mov eax,[ebx+0x240] / call SetActivePage / jmp`
   (`85f67e138b93840200008b8340020000e8c786fdffeb11`).
   `esi` is the requested level. The cave becomes `lea eax,[esi-1] / cmp eax,1 / ja surface`
   = "1 or 2 is underground, anything else is the surface page" — identical to vanilla for
   every level a 3-level map can hold (negatives included, since the comparison is unsigned),
   and level 3 now gets the surface page. `eax` is dead there (the preceding
   `TStatusPanel.SetText` return is read by neither branch). Both vanilla branch targets are
   re-used unchanged: `0x00429D2B` [`0x00429CC7`] surface, `0x00429D3C` [`0x00429CD8`] after.
   ⚠ The up/down handlers do **not** call `SetMapLevel` — each inlines its own copy of the
   status-bar update and page flip. That is why sites 3 and 4 both exist.

**Cave — 0x180 bytes, homed differently in the two binaries.**

    cave+0x000  ORDER[4]   slot  -> level  = 3, 0, 1, 2
    cave+0x010  RORDER[4]  level -> slot   = 1, 2, 3, 0
    cave+0x020  cave_up 70 B, cave_dn 70 B, cave_upflip 23 B, cave_smp 35 B  (236 B in all)
    cave+0x100  40 B: the section-table slot the new section displaced (AoWEd only)

- **`AoWEd.exe` — a new PE section `.lvn` @`0x004DF000`**, characteristics `0xE0000060`.
  AoWEd is stock (6 sections) and has 7 free header slots.
- **`AoWDevEd.exe` — page slack inside `.tres` @`0x00592080`.**
  ⚠⚠ **AoWDevEd.exe cannot take another section.** `e_lfanew` is `0x100` and its 13 section
  headers end at exactly `0x400`, which is where CODE's raw data begins — not one spare byte
  for a 14th descriptor. The seven custom sections already there (`.dlgd` dlgdirs, `.mtb`
  toolbar, `.ctp` terrain palette, `.vgo` validation-goto, `.pty` party random, `.tres` timer
  resolution, `.nmg` new map gen) used the room up. **Any future AoWDevEd cave must live in
  an existing section's page slack, or move the PE header block down into the DOS stub.**
  `.tres` was chosen as host: already read/write/execute, its owner
  `build_editor_timerres.py` uses a fixed 118 (`0x76`) bytes of a 512-byte raw block and has
  no growth path, and every byte from `0x76` to `0x200` was verified zero before writing. The
  cave starts at `+0x80` (a 10-byte gap above the timerres cave) and `.tres`'s VirtualSize
  was raised `0x76 → 0x200` so the bytes are formally inside the section rather than relying
  on the loader mapping past VirtualSize. `--undo` zeroes the window and restores `0x76`.

Both editor exes have the fixed base `0x400000`, so the caves use absolute addresses and are
not position-independent — correct here, and neither cave needs a relocation of its own.
No filesystem path and no username is baked into either cave. No random draw is made.

**Undo** is surgical and touches no backup: restore the four original byte-runs, then reclaim
the cave — drop `.lvn` in AoWEd (refused unless it is both the last section header and the
last raw block), zero the `.tres` window and restore its VirtualSize in AoWDevEd.
⚠ Dropping `.lvn` **restores the 40 bytes the header slot held before**, parked at
`cave+0x100` at apply time, rather than zeroing it: AoWEd.exe's 7th slot carries stale bytes
from its own build (6 non-zero bytes in `0x2F5..0x30F`), and zero-filling it made the
round trip differ from the original by exactly those 6 bytes. With the save/restore, a full
`--apply` / `--undo` round trip reproduces both editor exes bit for bit.

Hashes: `AoWDevEd.exe` `dbd52aec…be7601` → `907dc7eb…458604`; `AoWEd.exe` `7b2f1b25…e8ecdb`
→ `a7588f0c…45a51e`.

⚠ **Forward hazard.** `build_editor_timerres.py --apply` over an installed state rebuilds
`.tres` with `d = d[:raw] + body + zeros`, i.e. it **truncates the file at `.tres`'s raw
offset**. It is already guarded by its own `assert raw + rsz >= len(d) - falign` (".tres is
not the last section — refusing"), which now fails because `.nmg` follows it, so it aborts
rather than corrupting anything — but that assert is the only thing standing between a
timerres re-apply and the loss of both `.nmg` and this cave. Do not weaken it.

#### In-game checklist — UI caption + editor level navigation

Nothing below can be checked without launching the binaries.

**Game (`AoWz.exe`, and `AoWzCompat.exe` if used):**
1. Open a map with 4 levels. The World Map level strip reads
   **Firmament | Surface | Caverns | Depths**, in that order, left to right.
2. Click each of the four tabs: the view goes to Firmament / Surface / Caverns / Depths
   respectively, and the pressed tab matches the level shown.
3. PgUp from Surface → Firmament; PgDn from Firmament → Surface. PgUp on Firmament and PgDn
   on Depths do nothing (no blank level, no crash).
4. Open a 3-level map: exactly three tabs, **Surface | Caverns | Depths**, and PgUp/PgDn
   behave as they always did.

**Editor (`AoWDevEd.exe`):**
5. Load a 3-level map. Level Up / Level Down step Surface ↔ Caverns ↔ Depths as before, and
   stop at both ends. The terrain palette page still flips to the underground set below
   Surface.
6. Add Level to make it 4. **Level Up from Surface goes to Firmament**, not to Depths.
7. **Level Down from Firmament goes to Surface.**
8. Level Up on Firmament does nothing; Level Down on Depths does nothing.
9. On Firmament the palette shows the **surface** page, not the underground one.
10. The status-bar level readout still updates on every step (it prints the stored level
    number, so Firmament reads 3 — expected, not a defect).

**`AoWEd.exe`** — patched in lockstep and never yet exercised at all. If it is used, repeat
5–9 there. If it is not used, say so and the AoWEd half can simply be `--undo`ne.

⭐⭐ Both editor caves and the game cave run only from user actions, not at package init, so
no launch-only failure mode is expected — but nothing here has been run once.


### Where the level count lives

`TAoWHSMap+0x10` → `HSEngine.TMapContainer` (HSEPack.dpl, VMT `0x556026FC`, instsize `0x20`):
`+0x08` child `TList` of `TMapLevel` (`[+4]` items, `[+8]` count), `+0x0C` width, `+0x10` height,
**`+0x14` level count**, `+0x1C` engine. `TNewHSMapSettings` (`0x5560232C`, instsize `0x20`):
`+0x04` width, `+0x08` height, **`+0x0C` level count (dword)**, `+0x10` HSS name, `+0x14`/`+0x18`/
`+0x1C` map/container/level ClassIDs (`TAoWNewHSMapSettings.Create @0x55773980` sets `+0x14=0x20011`,
`+0x1C=0x20013`).

### The one cap — `TAoWHSMap.AddMapLevel @0x55777684` (VMT `+0xAC`)

```
5577768B  83 7E 14 03    cmp dword [esi+0x14], 3     ; file 0x76A8B, imm byte at 0x76A8E
5577768F  jge fail
55777691  mov edx,0x20013 ; TAoWMapLevel.ClassID → container vmt +0x8C (TMapContainer.AddLevel)
557776AD  call InitializeMapLevel(map, count-1)
```

Live was `03`, pristine `03`, unclaimed. **Now `04`** (`build_maplevel4.py`). `TMapContainer.AddLevel @0x55608DF8`
has no cap; `TMapContainer.New @0x55608E44` loops `[settings+0x0C]` times; `InitializeNewMap
@0x55777590` loops `0..count-1`; `InitializeMapLevel @0x557773CC` only distinguishes `level = 0`
(water fill) from `≠ 0` (EarthWall `7` fill), so a 4th level builds like levels 1–2.

### Everything else, verified count-driven or level-agnostic

- **Coordinates** are three separate bytes, never a bitfield: `TArmy+0x13/+0x14/+0x15` x/y/level
  (`0xFF` = nowhere); `TMapField+0x10/+0x11/+0x12`; `PackXYL @0x5560E698` = `x | y<<8 | L<<16`,
  byte 3 zero. `GetXYL`/`GetFieldXYL` sign-extend L → ceiling 127 levels; the serialised count and
  per-level index are unsigned bytes → 255. Neither is near 4.
- **Save/map format**: `TMapContainer.ReadWrite @0x55608C44` writes width/height/**count** as
  property ids 3/4/5 (bytes); levels are generic `TENode` children streamed by
  `TECustomNode.ReadWriteChildren @0x55519608`. The `.hsm` 16-byte header carries no level count.
  `zig_hsm.py` confirms the level table is a tagged directory keyed by level id — a 4th entry fits.
- **Level links**: `Cave.TCave` only. `+0x30` direction flag; `PlaceHX @0x557B36B1` twins at
  `level±1`; `EnterEx @0x557B3A95` sends to `GetLevel()±1`. No explicit target, no ceiling. Teleport
  and Town Gate take an explicit XYL. **No "deep underground" concept exists anywhere** — every gate
  is `level == 0` vs not (`TGlobalTargetSpell.CanActivate @0x5579E73C`, tower construction
  `@0x557C38D4`, terrain gates in `09-terrain-movement.md`). Level names come from `LevelXRStr`
  ("Level %d", ptr `0x55707A4C`), not a table.
- **Pathfinding/AI**: `TMoveControlSettings` keeps per-level planes as a heap array (`+0x20`, count
  `+0x78`), sized in `SetupMovePointData @0x557451C4` from `TMoveControl.Activate @0x55746501`
  passing `[container+0x14]`. `InvalidateMap @0x557725C0`, `ResetMapLevels @0x55778468` loop the
  count. Fog is per-field bits (`field+0x1B`). No fixed-bound level loop in the vanilla AI.
- **Game UI (AoW.exe)**: two paths, both count-driven. PgUp/PgDn in `TMWindow.MapWindowKeyDown
  @0x004512E4` (`0x4514BC` dec / `0x4514D5` inc of `THSMapViewer+0x38`, then `SetSceneL` via thunk
  `0x401E54`); and the World Map window's Surface/Caverns/Depths strip — see the subsection below.
  `THSMapViewer.SetSceneL @0x5560EDD0` clamps to `[0, [[viewer+0x48]+0x10]+0x14 − 1]`.
- **Editor (AoWDevEd.exe)**: `SetMapLevel @0x429C68`, `LevelUp/DownBtnClick @0x429ED8/0x429D80`,
  `AddMapLevelClick @0x42BDC8`, `RemoveMapLevelClick @0x42BCB8` all use `BOUND(−128,127)` or the
  live count; `SetMapLevel` flips between two `TPageControl` pages (`+0x244` surface, `+0x284`
  underground) on `z>0` — cosmetic. `THSMEdit.SetSceneLevel @0x556140B8` clamps to the count;
  `THSMEdit.CenterView @0x55613EC8` does **not** clamp z (caller's job — `build_validation_goto.py`'s
  `z<=7` cap is the right shape). `TMapContainer.GetMapLevel @0x55608D48` and `GetFieldXYL
  @0x55608D54` are unchecked: a stale viewport level (`THSMap+0x88`, persisted as property 6) on a
  smaller map reads past the list.

### As built — `build_maplevel4.py`, cave `0x55844000..0x558443FF` (v2, 250 B used; v1 was 150 B)

Cave verified all-zero and unclaimed before allocation (neighbours `0x55843000`, `0x55846000`).
**Fully position-independent and needs no globals at all** — every block is register/stack-only plus
rel32 jumps back into the module, so there is no call/pop anchor and not one absolute memory operand
(asserted at build time by scanning the capstone listing). **No RNG draws anywhere in the feature**,
so `rng_audit.py --owners` is unchanged. Every displaced range was checked `.reloc`-free.

| block | VA | B | hook (orig → new) |
|---|---|---|---|
| — | — | — | cap byte `0x5577768B` `83 7E 14 03` → `83 7E 14 04` (imm at `0x5577768E`, file `0x76A8E`) |
| `fillterr` | `0x55844000` | 22 | `0x5577747E` `50 6A 07 8B CE` → `E9` |
| `vis1` | `0x55844020` | 21 | `0x55780F32` `80 7C 24 02 00` → `E9` |
| `vis2` | `0x55844040` | 21 | `0x55780F4C` `80 7C 24 02 00` → `E9` |
| `spellgate` | `0x55844060` | 26 | `0x5579E78B` `80 7D F9 00 74 25` → `E9` + `90` |
| `placeguard` | `0x55844080` | 22 | `0x557B36BB` `0F BE 45 08 40` → `E9` |
| `stormcast` **[v2]** | `0x558440A0` | 26 | `0x557CDCC8` `80 7D F9 00 74 25` → `E9 D3 63 07 00 90` |
| `stormai` **[v2]** | `0x558440C0` | 26 | `0x557CDF88` `80 7D F9 00 75 66` → `E9 33 61 07 00 90` |
| `birdsview` **[v2]** | `0x558440E0` | 26 | `0x557EAB90` `80 7D F9 00 74 25` → `E9 4B 95 05 00 90` |

**`fillterr` — the Sky fill.** `TAoWHSMap.InitializeMapLevel @0x557773CC(map, DL=level)`'s `!= 0` arm
pushes its three stack params as `push ebx` (row) / `push eax` (level) / `push 7` (**terrain**) before
`call [ebp+0x50]`. Param roles read off the sibling arms, not guessed: the level-0 arm pushes
`ebx/0/0` (level 0, terrain 0 = water) and the shared border ring pushes `ebx/al/0xF`. The hook sits
at `0x5577747E` — the `push eax` — because `mov al,[esp+8]` one instruction earlier **already leaves
the level in AL**, so `0x5577747E..82` is exactly 5 bytes and the cave never re-reads the stack:
`push eax; movzx ecx,al; cmp ecx,3; je → push 0x0E; else push 7; mov ecx,esi; jmp 0x55777483`.
ECX is dead at that point (`mov ecx,esi` follows). ⚠ The loop's back-jump target `0x55777479` is
*before* the hook and untouched.

**`vis1`/`vis2` — Sky counts as surface for vision.** `TAbstractUnit.VisibilityRange @0x55780EF8`
tests the level twice: `@0x55780F32` gates the Night Vision (`0x27`) requirement, `@0x55780F4C` gates
the halving. Both 5-byte compares become `E9`; each stub sets ZF exactly as the compare would for
levels 0/1/2 **and additionally for level 3**, then jumps back to the `je`/`jne` that followed:

```
push eax
movzx eax, byte [esp+6]      ; +2 for the local, +4 for the push
cmp  eax, 3
jne  .l
xor  eax, eax                ; Sky: force 0 so the test below sets ZF
.l: test eax, eax            ; ZF = (level == 0 or level == 3)
pop  eax                     ; pop does not touch flags -- this is what makes it free
jmp  <the je/jne>
```

⚠ `build_vision9.py` owns `0x55780F12` in this same function (the `add esi,3` ceiling). Different
bytes, no overlap — do not let the two scripts' verify ranges drift together.

**`spellgate` — global-target spells allowed from Sky.** `TGlobalTargetSpell.CanActivate @0x5579E73C`
has the compare in the **disp8** form (`80 7D F9 00`, four bytes), so the hook takes cmp + `je` = 6
bytes and the cave branches itself: same predicate, then `je 0x5579E7B6` (allow) / `jmp 0x5579E791`
(refuse + `CannotCastSpellInUndergoundRStr`). The reloc'd `mov eax,[0x558E8FE4]` at `0x5579E796` is
clear of the displaced range.

**`placeguard` — `TCave.PlaceHX` cannot dig into the Sky.** `Cave.TCave.PlaceHX @0x557B3670` pairs a
cave with a twin one level away; `[esi+0x30]` is the polarity (1 = upper mouth → twin at level+1;
0 = lower mouth → twin at level−1). With four levels a flag-1 cave placed on level 2 would now
*succeed* in twinning into the Sky. Guard: `movsx eax,[ebp+8]; cmp eax,2; jge .block; inc eax;
jmp 0x557B36C0` / `.block: xor ebx,ebx; jmp 0x557B37BA`. `0x557B37BA` is the function's single
epilogue (`mov eax,ebx / pop esi / pop ebx / leave / ret 8`), so EBX=0 is a clean "placement failed",
the same shape as the engine's own failure return at `0x557B372F`. The guard fires **before** the
twin is allocated, so nothing is half-created.

⚠ **Do NOT "simplify" that guard into a jump to `0x557B373D`.** That is not a bail-out, it is the
*mirror* arm, and the two arms are not interchangeable: each one's "twin already exists" branch
asserts the **opposite** polarity on the twin it finds (flag-1 arm `0x557B371A` `cmp [twin+0x30],0 /
sete bl`; flag-0 arm `0x557B379C` `cmp [twin+0x30],1 / sete bl`). Sending a flag-1 object down the
flag-0 arm makes it create a level−1 twin that *also* carries flag 1; that twin's own PlaceHX (VMT
slot `+0x118`) then finds the original, sees the wrong polarity, `sete bl` → 0, and **destroys it**
via `[vmt−4]`. A guard that destroys the cave it was protecting is worse than the bug it fixed.

**`stormcast` / `stormai` / `birdsview` — v2, the storm and Bird's View gates.** User ruling
2026-09-06: storm spells and Bird's View follow the same rule as global-target spells — castable
while viewing the Firmament, still refused on Caverns and Depths. All three sites are the *same*
instruction pair as `spellgate` in the *same* operand form (`80 7D F9 00` = `cmp byte [ebp-7],0`,
the level local filled by a `TAbstractUnit.GetLocation` call a few instructions earlier), so each
takes a 6-byte `E9` + `90` hook and its own 26-byte stub. Re-derived from the **live** bytes with
`dasm.py` on 2026-09-06, not from a decompile; all three displaced ranges are `.reloc`-free
(63883-entry scan, nothing within ±4 bytes).

The stubs cannot be shared with `spellgate`: the predicate is identical but the two branch targets
differ per site and are baked as rel32 tails. Each is register/stack-only — `push eax` /
`movzx eax, byte [ebp-7]` / `cmp eax,3` / `jne .l` / `xor eax,eax` / `.l: test eax,eax` / `pop eax` /
`je allow` / `jmp deny` — so PIC holds with no anchor and no absolute operand.

| stub | allow | deny |
|---|---|---|
| `stormcast` (`TStormSpell.CanActivate`, `je` form) | `0x557CDCF3` | `0x557CDCCE` |
| `stormai` (`TStormSpell.AICastSpellPriority`, **`jne`** form) | `0x557CDF8E` | `0x557CDFF4` |
| `birdsview` (`TBirdsView.CanActivate`, `je` form) | `0x557EABBB` | `0x557EAB96` |

⚠ **The AI site's polarity is inverted.** `0x557CDF8C` is `jne`, so *underground* is the jump and
the allow target `0x557CDF8E` is merely the fall-through address — one byte past the hook's `90`.
Its deny target `0x557CDFF4` is the finally-epilogue, entered with `EDI = -1` from
`or edi,0xFFFFFFFF @0x557CDF74`, i.e. the engine's own "no priority" return; jumping to `0x557CDFF1`
instead would re-execute that `or` harmlessly but is one byte off the vanilla shape.

⚠ **Both `CanActivate` allow targets skip a `xor ebx,ebx`** as well as the
`CannotCastSpellInUndergoundRStr` load. EBX is the return value, so a stub that fell through to the
compare's next instruction would refuse the cast *and* leave the message set. The stubs jump to the
`je` target, never to the fall-through.

### The two in-place cave re-tunes

| script | change |
|---|---|
| `build_shipyard_income.py` | new single-source `MAX_LEVELS = 4`; the four `cmp edx,3` at `0x55822174` (entry's sanity guard) / `0x55822390` / `0x558224C4` / `0x55822540` (build_t1's dim/mark/bfs loops) now read `04`, and the three per-level dword arrays in the BSS header grow to 4 slots: `H_LABOFF +0x24`, `H_W +0x34`, `H_H +0x44`, then `H_QOFF 0x54`, `H_AOFF 0x58`, `H_COFF 0x5C`, `H_NREG 0x60`, `H_NRSLOTS 0x64`, `H_YOFF 0x68`, `H_YN 0x6C`, `H_YCOUNT 0x70`, `H_YVALID 0x74`, **`HDR_END 0x558FAB78`** — still inside the `0x80` window (neighbours end at `0x558FAA24` / start at `0x558FAF20`). Cave length unchanged at 2343 B; `--sim` 57/57 |
| `build_waterheal.py` | **v5**: the `_earth` arm gains `cmp byte [esi+0x12],3 / je _out` ahead of everything else, so earth elementals never heal on the Firmament (they would otherwise, since the arm treats "not surface" as underground). Cave 344 → 354 B. **v6 (2026-09-06)**: the `_air` arm at `0x5582407E` accepts the Firmament as well as the surface — `cmp byte [esi+0x12],0 / jne _out` becomes `cmp 0 / je _airok / cmp 3 / jne _out`, +6 B, cave 354 → **360 B**. Earth's v5 exclusion is unchanged. v1–v5 all stay as frozen recognition sources |

⚠ **FORWARD HAZARD.** `build_waterheal.py` cave `0x55824000` and `build_maplevel4.py` both encode the
level-3 predicate. Re-applying an **old revision** of waterheal alone silently reverts the earth
Firmament-skip *and* the air Firmament-heal, and nothing in `build_maplevel4.py` will notice.

Not touched: HSEPack.dpl, EngineP.dpl, coordinates, AI, fog, save format, `SetSceneL`, and the
`AoWz.exe`/`AoWzCompat.exe` UI half (`build_skylevel_ui.py`, exe cave `0x0062A000`).

Still to do, unchanged from the original analysis: `build_deved_newmapgen.py` (fourth
`TRadioButton`, field table +1, `t_level` 3→4, elimination read at `:680-688`, `:1164-1176`);
`Zig Modding Tools/deved_bridge.py:179` `(num(1) % 3) + 1` wraps "3"→1 silently;
`Zig Modding Tools/zig_mapgen.py:2319` `--levels choices=(1,2,3)`. No 4-level container exists on
disk — author one via the editor's Add Level.

### Every `level == 0` site in AoWEPACK.dpl, with a verdict

The complete enumeration (scan of the pristine DLL for `call TAbstractUnit.GetLocation @0x5577ED94`
followed within one basic block by a `cmp byte …, 0`; the `TMapObject.GetLevel` thunk `0x5570213C`
has no such call-form site). ⚠ A bare `fieldrefs.py … 0x12` sweep is nearly useless here: most
`cmp byte [x+0x12],0` hits are `TArmy+0x12` (the player byte), not `TMapField+0x12` (the level).

| site | what it gates | verdict |
|---|---|---|
| `TAbstractUnit.VisibilityRange +0x35` → `0x55780F32`, `0x55780F4C` | Night Vision requirement; the halving | **PATCHED** — Firmament = surface |
| `TGlobalTargetSpell.CanActivate +0x4A` → `0x5579E78B` | "cannot cast underground" | **PATCHED** — allowed from the Firmament |
| `Storms.TStormSpell.CanActivate +0x3F` → `0x557CDCC8` | storm spells underground | **PATCHED (v2)** — allowed from the Firmament. A *different class* from TGlobalTargetSpell, so it needed its own ruling and its own stub |
| `Storms.TStormSpell.AICastSpellPriority +0x3F` → `0x557CDF88` | the AI half of the same rule | **PATCHED (v2)** — moved with the one above, as it must, or the AI mis-values storms. ⚠ `jne` form: inverted polarity |
| `GlobalSpells.TBirdsView.CanActivate +0x3F` → `0x557EAB90` | Bird's View underground | **PATCHED (v2)** — also its own class. These three plus TGlobalTargetSpell are the *only* users of `CannotCastSpellInUndergoundRStr` (`0x558E8FE4`) |
| `Tower.TTowerConstructionControl.CanConstruct +0x34` → `0x557C390D` | tower construction underground | ⚠ **the gate is already dead on this install** — see below |
| `VMT_TBuildRoadsControl +0x400` → `0x55770EE5` | road building underground | left — no roads on the Firmament |
| `TAoWHSMap.CenterOnLeader +0x4F` → `0x55778E70` | camera centring | left — presentation only |
| `Shipyard.TShipyardConstructionControl.StructureResource +0x0F` → `0x557C769C` | picks resource `0x3C` (surface) vs `0x6B` (underground) for the shipyard's art | left — a Firmament shipyard would wear the cave sprite. Cosmetic |
| `THero.ValidateHeroUpgrade +0x16` → `0x55787D6F` | **false positive** — `ebp` is the hero object here, not a frame pointer, so `[ebp+0x24]` is a hero field; the level went to `[esp+2]` | n/a |

⚠ **Towers can be built on every level, including underground and the Firmament — the gate is dead
on this install.** Re-verified by raw byte compare 2026-09-09:

```
557C390D  80 7d fd 00   cmp byte [ebp-3], 0        ; the underground test
557C3911  75 0f         jne 0x557C3922             ; PRISTINE -- take the fail arm
557C3911  90 90         nop; nop                   ; LIVE     -- result discarded
557C3913  8b cf ...     -> CanConstruct
```

The compare still runs and its result goes nowhere, so construction always proceeds. **No build
script in `build_scripts/` claims those two bytes** — it is an undocumented live edit predating the
recording convention, same class as the `0x5580C240` Marksmanship cave and the Animate Dead hand
edit. Restoring the `jne` would be *enabling* a rule that has never been on under Ziggurat, not
repairing one; treat it as a design question for the owner, not a defect.

**Left as `!= 0 ⇒ underground` on purpose** (unchanged by this feature): Path of Life / Path of Decay
`0x557801A4` / `0x557801C4`, `TAbstractUnit.ConcealedOnMapF @0x55780564`, Raise Terrain's underground
arm, the terrain-change and road gates.

**Tactical vision needs no patch** (this was the open question in the spec).
`TCombatUnit.GetVisibilityRange @0x55724AD0` halves on `cmp byte [eax+0x40],1` with
`eax = [combatunit+8]` — and that back-pointer is the **TCombat object**, whose `+0x40` is the combat
*kind*, not a level: `1` = exploration-site interior (written at `TExplorationSite.SetupCombat
@0x557C1A17`), `2` = default armies (`TCombat.InitDefaultArmies @0x55727BF5`), read the same way by
`TAoWHSMap.DestroyCombat @0x5577894D`. The `== 1` (not `!= 0`) form is the giveaway. A Firmament field
battle is kind 2 and already gets full tactical vision.

### The in-game checklist — nobody has played this

1. **Launch `AoWz.exe` at all.** Nothing here runs at package init, but the cap byte and eight hooks
   are on load-bearing paths; a crash on startup invalidates everything below.
2. In the **editor**, Add Level four times: the fourth must be accepted (vanilla refused) and must
   come up filled with **Sky (`0x0E`)**, not EarthWall, with the 6-hex border ring at `0x0F` intact.
3. Save the 4-level map, reload it, and confirm the level survives the round trip.
4. **Vision on the Firmament**: a unit without Night Vision on level 3 must see its **full** radius — the same
   number it shows on the surface, not the halved underground one.
5. **Vision underground still halves**: same unit on level 1 or 2 must still be halved, and Night
   Vision must still lift it. (This is the regression the two-site patch could break.)
6. **Global-target spells** (the ones that error "cannot cast in the underground") must be castable
   with the caster on the Firmament, and must **still refuse** on levels 1 and 2.
7. **Storm spells (v2)**: a storm spell must be castable with the caster on the Firmament, and must
   **still refuse** on levels 1 and 2 with the usual "cannot cast in the underground" message.
8. **Bird's View (v2)**: same — castable from the Firmament, still refused on Caverns and Depths.
9. **The storm AI still values storms sanely** (`AICastSpellPriority`, the `jne`-form site): an AI
   wizard on a 4-level map must still cast storms on the surface and underground as before. A
   mis-patched inverted-polarity site shows up as the AI *never* casting storms, or casting them
   from the Depths.
10. **Caves**: place a cave entrance on level 2 in the editor. It must refuse rather than dig a
    passage into the Firmament. Entrances on levels 0 and 1 must still work normally, both mouths.
11. **Earth elemental on the Firmament**: no heal, no chime. On any underground level and on any
    Mountain hex, still +1 with the quarter-volume chime.
12. **Air elemental on the Firmament (v6)**: +1 HP with the quarter-volume chime per hex entered,
    exactly as on the surface. It must **still** heal on the surface, and **still not** on Caverns
    or Depths.
13. **Shipyard income** with water on all four levels: each level's sea must be counted, and the
    per-level totals must be independent (a Firmament lake must not merge with a surface one).
14. Movement onto Sky terrain still obeys the flyer-only rule from `build_chasm_sky_movement.py`.

### The World Map level strip — `TSWindow.ScannerTab`

The in-game "World Map" window is **`TSWindow`** (AoW.exe DFM at file `0x001C4F48`; VMT
`0x004519A0`; field table `0x004519C8` 12 entries, class table `0x00451B77` 9 slots, method table
`0x00451A99` 9 entries, InstanceSize `0x74`; global instance `[0x0045A1C0]`, toggled by
`TTBWindow.WMButtonClick @0x00457318`). `TWorldMap` is the *campaign* map, unrelated.

Surface | Caverns | Depths is **one control**, `TAOWTabPanel ScannerTab` (`aowInt.dpl`, unit
`AoWTabPanel`), `awBoth/ahBottom`, offsets L31/R24/B19 → 145 px wide at the 200×216 minimum. Layout
is AoW's own `WinLeft/WinTop/WinWidth/WinHeight` + `Alignment.*`; Delphi `Left/Top` are junk. The
map (`TScanner Scanner`, `AOWTools.dpl`) is anchored on all four edges, L30/R39/T32/B32 → 131×152.
The three icons top-right are `BuildingCheck/ArmyCheck/NaturalCheck` (`TAOWCheckBox`, `RightOffset
25`, `WinTop 37/52/67`, 15 px wide). Frame: `TAOWWindow` with `IntGfxMod.GenericF`; hollow box
`TAoWFrame ScannerFrame`.

Slot index == level index, assumed in four places:

| site | does |
|---|---|
| `0x00454FF8`–`0x0045508F` (inside the handler published as `TGeneral.ManagerDebugMessage @0x004548F4`) | clears the tab strings, adds "Surface" unconditionally, "Caverns" if `[container+0x14] > 1`, "Depths" if `> 2`; `SetIndex(0)`. The only read of the level count in this form |
| `TSWindow.ScannerTabChange @0x00451BC8` | `[ScannerTab+0x118]` → literal 0/1/2 → `[Scanner+0x17C] = −1` (cache invalidate) → `[[0x0045DF7C]].vmt[0xB8]` = `THSMap.ViewLevel @0x5560C1B0` (gate `L < count`, no lower bound, fires `OnViewLevel`) |
| `TMWindow.MapViewerSceneChanged @0x00450F8C`, at `0x00451145` | `ScannerTab.SetIndex(viewer+0x38)` — pressed state; `SetIndex @0x59817C7C` stores `+0x118`, no clamp |
| `MapWindowKeyDown` `0x004514BC`/`0x004514D5` | `dec`/`inc` |

`TAOWTabPanel.Draw @0x59817CEC` loops `0..Count−1`, `tabw = width div Count`; `CheckMouseDown
@0x5981812C` derives the slot from X only. **Structurally horizontal**, and shared by six instances
in AoW.exe (`ScannerTab`, both `HeaderTab`s, `SoundTab`, `UnitTab`, `TArmyInfoDlg.Tab1`) — a vertical
rewrite in `aowInt.dpl` must be a PIC cave gated on a per-instance sentinel.

Captions are AoW.exe's own STRINGTABLE (file `0x74094`, ids 65524/65525/65526; `PResStringRec`s
`0x00403414/1C/24`, reached via gvar slots `0x0045A0C0/0x0045A288/0x0045A3F8`), translated by
`AoWE.TranslateRStr` (thunk `0x004021E4`) against `Dict/ResStr.mld` (`ResStr.txt` #1002 Surface,
#242 Caverns, #354 Depths). No spare id in that block — a "Sky" caption is a new resource or a cave
literal.

`TScanner` holds **one** level pointer (`+0x15C`, `SetLevel @0x597025F8`) and one cached surface pair
(`+0x174/+0x178`, validity `+0x17C`); no per-level cache, nothing sized 3. `MapDrawSteps = 5`.

**Column layout (user's wish, not built).** Cheapest concrete shape: widen the left margin —
`Scanner.LeftOffset 30→78`, `BottomOffset 32→12`, `ScannerWindow.MinWidth 200→248`, three
`TAOWCheckBox` radio-style buttons `awLeft/ahTop`, `LeftOffset 4`, `WinTop 32/56/80`, 70 wide,
`ScannerTab` retired; map becomes 131×172. That is the `08-editor.md` §9.1 relocation dance on
`TSWindow` (field 12→15, method 9→12, InstanceSize `0x74→0x80`, RCDATA block relocated; class table
needs no new slot, `TAOWCheckBox` is already referenced) plus a cave of three click handlers calling
`ViewLevel`.

**Firmament level (user's design: displayed above Surface).** The display order has to become a table
(`slot → level`, reverse lookup for the pressed state, `prev[]/next[]` for PgUp/PgDn) in all four
sites above, whichever index sky gets. Once that table exists, **reserving index 3 buys nothing**: a
later deep-underground level enters as index 4 and the table becomes `[3,0,1,2,4]`. Storing sky at
index 4 today instead forces a filler level 3 that is generated, serialised, pathfound (per-level
planes in `TMoveControlSettings`), fogged and AI-scanned on every map — a permanent cost for a
level that does not exist — and moves the cap byte to `05` and the shipyard arrays to five slots.
**User ruling 2026-09-06: sky = index 3, display remap only.** Further rulings the same day:
caves are only ever placed at their upper end (surface or caverns), which auto-places the lower
twin, so every Depths entrance heads up and no cave can reach index 3 today; a cave heading DOWN
from the Firmament ("inside mountains") is a later feature; vision on the Firmament is unhalved, as
on Surface; air elementals healing there was deferred for review, and **ruled in on 2026-09-06**.

Either way `TCave` (`level±1`) cannot link surface and Firmament: a cave on Depths would open into
the Firmament (index 3) or the filler (index 4). The Firmament needs its own transition class
("inside mountains") with an explicit target, on the `TTeleport`/`TTownGate` XYL pattern, and
`TCave.PlaceHX` needs a ceiling so it never twins into the Firmament.

### Open

- A "down" cave on the bottom level indexes past the level list today at 3 levels; presumably the
  editor prevents it. Unchanged by a 4th level, worth a guard if caves are ever placed by code.
- **Air elementals on the Firmament — RULED 2026-09-06, applied.** The Firmament is open sky, so
  air elementals heal there. `build_waterheal.py` v6 widens the `_air` arm at `0x5582407E` to
  `level == 0 or 3`. Earth's v5 exclusion is unchanged, so the two arms now disagree deliberately.
- **Storm spells and Bird's View — RULED 2026-09-06, applied.** They follow the global-target
  ruling. `build_maplevel4.py` v2 patches `Storms.TStormSpell.CanActivate @0x557CDCC8`,
  `AICastSpellPriority @0x557CDF88` and `GlobalSpells.TBirdsView.CanActivate @0x557EAB90` with three
  new stubs — see the as-built section above.
- **Share hazard, profile-path rule:** `Modding Resources/Ziggurat Manual.log` carries the
  username and is caught by neither the mandatory `find … -name '*.pyc' -delete` pass nor the
  Ghidra-project exclusion — add it to whichever pre-share checklist carries that `.pyc` line.

## Open items

- **`ItemUsePnl` visibility defect** (scrolls) — needs one in-game check: author a scroll, select it,
  see whether a Use button ever appears. Moot if the spellbook-grant redesign is what ships, since it
  disables the vanilla Use path outright.
- **Scroll data authoring** — no type-5 items exist in any file yet; a prerequisite for testing the
  spellbook-grant feature at all.
- **AI heroes get neither scrolls nor item-granted activatable abilities** — each for two independent,
  identified-but-unfixed reasons (acquisition never tries backpack slots; the AI's own spell-candidate
  scan runs DLL-side and never sees the exe's book-filter cave).
- **Route 2 (ability-system HP/MV)** — unbuilt alternative, better if the feature ever needs to cover
  regular `TUnit`s or non-item sources. ⚠ It would not carry the banner display with it: that reads
  `item+0x4A`/`+0x4B` directly (`07-ui.md` §9), so a Route 2 rewrite must keep those bytes populated
  or re-point the two display blocks.
- **Whether the vanilla `TGeneral` ≥10-visible-unit crash actually reproduces** — never tested; the
  double-stack mechanism above is a plausible, unconstructed route to the precondition.
- **Whether the Seduce/Charm/Dominate double-stack reproduces independent of the movement-predictor
  patch** — needs the manual-zero A/B described in that section; never attempt via that script's own
  `--apply`/`--undo` (see the booby trap).
- **The three transport-boarding hardening candidates** — none built, none tested, each has
  network/AI implications.
- **Whether a deliberately-corrupted `.pfs` CRC is actually rejected by the reader** — inferred from the
  `.hss` precedent only, never directly tested; doesn't change practice (repair the checksum regardless).
- **What `Flags.ilb` ids 38, 39, 86, 90 contain** — `ilb_rle16.py` can't decode them (a multi-literal-span
  row codec limitation); only matters if those specific frames are ever edited.

## Failed approaches — do not retry

- **Retyping `ITEMGFX.PFS` 316–319 from `itUse` to `itScroll`** (`build_scroll_gfx.py`) — confirmed
  harmful in-game 2026-08-01 (blank portraits/icons, garbage spell costs, no error). Root cause not
  pinned down; use the item's own gfx index or append new records instead.
- **Identifying a hero's carried-item slot by a raw type-byte test alone** — the inventory array can
  hold dead (non-`TItem`) slots; a `byte[entry+0x34]==5` test matched one and fed a garbage id into
  `GetSpell`, silently poisoning the spellbook. Identify list entries by class (VMT compare) first.
- **Testing three cave changes in one pass after a clean bisect run** — made a real regression
  unattributable and cost a confusing extra round; keep one variable per test even after several clean
  rounds in a row.
- **Reusing `hss_crc.py` on a `.pfs` file** — wrong covered region (`d[:-4]` vs. `.pfs`'s `d[4:-4]`);
  its `--fix` writes a checksum the engine will not accept.
- **"Verifying" a rebuilt `.pfs` layout by tiling record bodies backwards from EOF against the index
  offsets** — circular, provably cannot fail, proves only that slicing is deterministic. Two scripts
  carried this; both replaced by the CRC-residue gate.
- **Hoisting `GetResistance` out of the Mind Decay eligibility gate** (Inioch's shipped
  variant) — premised on resistance not coming from `[target+0x4C]`, which is false; carries a latent
  access violation on exactly the nil-strategic-twin case its own nil check exists to fix.
- **Hooking Mind Decay's cave at `0x557F861B` instead of `0x557F8623`** — displaces an instruction
  carrying a type-3 base relocation, which a rebased load would apply on top of the patch. The chosen
  site (a `call rel32`) carries no relocation at all.
- **"An earlier reading called the `TGeneral` overflow a 9-visible-unit bug"** — corrected: the 9th
  write is transient and immediately overwritten by the correct pointer two instructions later; the
  first unrepaired corruption is the 10th.
- **"Raising the stack cap to 12 fixes the Seduce/Charm double-stack bug"** — it only makes the
  triggering refusal rarer; the refusal-ignoring code path is untouched either way.
