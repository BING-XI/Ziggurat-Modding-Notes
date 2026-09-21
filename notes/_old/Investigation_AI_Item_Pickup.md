# AoW1 — Do AI heroes pick up items? Investigation

**Status: INVESTIGATION ONLY (2026-07-21).** The verdict and the engine analysis below still stand
and are the substrate for everything since; the mod sketch in §7 is SPECULATIVE **and has been
superseded twice over.** All addresses are AoWEPACK.dpl preferred-base VAs (base `0x55700000`,
rebased at runtime → any cave must be position-independent) unless marked **[exe]**, which are
AoW.exe / AoWCompat.exe fixed base `0x400000`.

> ⭐ **What was actually built — read `AI_Sites_And_Loot.md`.** `build_ai_itemloot.py`
> (🔨 APPLIED, UNTESTED 2026-09-03) supersedes both `build_ai_itempickup.py` (confirmed 2026-07-21,
> empty slots only; **`--undo`'d 2026-09-02 and must stay inert**) and `build_ai_itemtarget.py`
> (reverted 2026-07-22). It adds upgrade-swap by item value, carry items into the backpack, and a
> group-aware answer to AI-target broadcast `0x1200`. The companion feature
> `build_ai_sitesearch.py` walks through the other door this doc left open —
> `TStructure.ExecuteAI @0x5575E698` was a `xor eax,eax; ret` stub.

Companion docs:
- `Investigation_Items.md` — item struct/field map, stat bonuses, scroll + HP/MV features.
- **`AI_ItemPickup_Engine_Mechanics.md`** — the engine substrate this patch rests on: engine
  collection layout (the count is *not* at `list+8`), the two list-removal modes, the equip slot
  tables, ground-list lifetime, and the asynchronous token pipeline + `GetBusy` gate that makes the
  token route unusable from an engine-side hook. Every §6b design choice traces to it.

This doc covers only the **AI-reachability** question.

⚠ **Addresses in the `0x558xxxxx` range are ambiguous** — `Network.dpl` (base `0x55800000`) overlaps
`AoWEPACK.dpl`'s CODE section. Unmarked addresses here are AoWEPACK.dpl. See
`AI_ItemPickup_Engine_Mechanics.md` §1.

---

## 1. Verdict

**No. There is no code that allows AI heroes to pick up items — and none that lets them acquire an
item by any runtime means at all.**

An AI hero's equipment is exactly *what the scenario author gave it, minus whatever it permanently
drops on death*. Static and monotonically decreasing. It cannot pick up ground items, cannot loot a
site, and cannot re-equip what it dropped.

Two **independent** doors block it, either fatal on its own:

| # | Door | Why the AI can't pass |
|---|------|----------------------|
| 1 | `TExplorationSite.Search@0x557c1e5c` (VMT+0x200) | AI never initiates a site search ⇒ loot is never even generated |
| 2 | `THero.PlaceItem@0x55788e94` | sole producer of the "place item" token — the only route an item takes *into* a live hero |

**The asymmetry is the whole story: items leave a hero engine-side, but can only enter one through
AoW.exe.**

---

## 2. Door 2 — item acquisition is UI-only

### 2.1 The token path

```
AoW.exe TUnitWindow drag/drop                            [UI — human only]
  └─► THero.PlaceItem@0x55788e94            ← ZERO code callers in the DLL (VMT slot 0x5590c960 only)
        ├─ THero.CanPlaceItem@0x55788d08
        ├─ TPlayer.GetBusy@0x557516d0                    (gate, see §2.3)
        └─ THero.CreateHeroUpdateTE@0x55788c60
              └─► [network → all peers]
                    └─► THeroUpdateTE.Execute@0x55789cdc [engine-side]
                          cmd 0 → THero.ExecutePlaceItem@0x5578907c
                          cmd 1 → THero.ExecuteSwapItem@0x55788f10
                          cmd 2 → THero.ExecuteStartCasting@0x55789130
                          cmd 3 → THero.ExecuteCancelCasting@0x5578932c
```

Wire format in `THeroUpdateTE.ReadWrite@0x55789c80` (tags 0x14–0x17): TE+0x10 unit id, +0x14 cmd,
+0x18 arg1, +0x1c arg2.

**`CreateHeroUpdateTE` is minted from exactly four sites** — `PlaceItem`, `SwapItem`, `CastSpell`,
`CancelCasting`. All four are UI entry points. Nothing engine-side ever mints an item token.

**Slot encoding** (arg to `ExecutePlaceItem`): **0–5** equip (`THeroItems.PlaceItem@0x55786788`) ·
**6–13** backpack (`TItem.SetArrayOwner@0x55794274` via `item->vmt+0x48`, slot−6) · **14 (0xE)** drop
to ground (`map->vmt+0x108` = `DropHeroItem@0x55773770`).

### 2.2 The three item commands have no engine-side callers

| Function | Addr | Callers |
|---|---|---|
| `THero.PlaceItem` | `0x55788e94` | VMT `0x5590c960` only |
| `THero.SwapItem` | `0x55788e1c` | VMT `0x5590c964` only |
| `THero.UseItem` | `0x55788ce0` | VMT `0x5590c970` only |
| `THero.CanUseItem` | `0x55788ca8` | VMT `0x5590c974` only |
| `THero.GetItemsOnGround` | `0x55788c7c` | VMT `0x5590c978` only |
| `TItem.Use / CanUse / ExecuteUse` | `0x557941b4 / 0x557940ac / 0x55793f68` | VMT only |
| `TAbstractAoWHSMap.GetHeroItemsOnGround` | `0x557737a8` | VMT only |

### 2.3 **[exe]** Where the UI lives, and its four human-only gates

Hero item screen = **`TUnitWindow`**, DFM `'UnitWindow'` at foff `0x1E8B9C`, VMT `0x0040710C`.
(AoW.exe ≡ AoWCompat.exe except 1 byte at foff `0x3BB7C`, so all addresses apply to both.)

| Handler | Addr | Item API called |
|---|---|---|
| `TUnitWindow.Gnd1Change` | `0x0040A344` | `SwapItem` @`0x40A3CF`; `PlaceItem` ×14 @`0x40A3ED`–`0x40A57A` |
| `TUnitWindow.UseItemClick` | `0x00409FFC` | `CanUseItem` @`0x40A05A`, `UseItem` @`0x40A078` |
| `TUnitWindow.PreDrawAbilityItem` | `0x00407BA8` | `THeroItems.GetPositionItem` ×12, `GetItemsOnGround` ×12 |
| `TItemsFoundDlg` (VMT `0x0044C8D0`) | `0x0044CD9C`, `0x0044CF51` | `TItemControl.FindItem` |

Dispatch is by **direct named import, not VMT**. Thunks: `0x402774` PlaceItem, `0x40276C` SwapItem,
`0x402764` UseItem, `0x40275C` CanUseItem, `0x402754` GetItemsOnGround.

Slot map (`TUnitWindow` field offset → control → position arg):
```
+0x0FC BP1→6  +0x104 BP2→7  +0x108 BP3→8  +0x10C BP4→9
+0x110 BP5→A  +0x114 BP6→B  +0x118 BP7→C  +0x11C BP8→D
+0x128 Head→1 +0x12C Torso→4 +0x130 Attack→0 +0x134 Defend→2
+0x138 RingL→3 +0x13C RingR→5      anything else (Gnd1..Gnd5) → 0xE = drop
+0x164 ItemUseBtn
```
Selection state = `TGeneral` singleton `[0x0045A420]` (+0xC0 displayed unit, +0xA4 selected army
list); drag state in BSS `[0x0045B074]`.

**Four independent gates, any one sufficient:**
1. Only AoW.exe/AoWCompat.exe import these symbols — **not** AoWTCPCK.dpl, aowInt.dpl, HSEPack.dpl
   or AoWDevEd.exe. All AI code is in AoWEPACK.dpl, which never calls them.
2. Entry is a DFM mouse-event handler — only a local click produces one.
3. `Gnd1Change` bails at `0x40A37D` on `TPlayer.GetBusy@0x557516d0` (no busy lock `player+0x48`;
   turn ownership `map+0xA4 == player+0xA6`; `player+0x44 == 0` not game-over;
   `TPlayer.GetLocal@0x55753720`).
4. `PlaceItem` re-runs `CanPlaceItem` + `GetBusy` before emitting; `THeroUpdateTE.Execute` refuses
   unless `map+0xA4 == hero+0x24`. A forged token can't equip out of turn.

---

## 3. Door 1 — the AI never searches an exploration site

### 3.1 The reward path (engine-side, but it only ever reaches the *ground*)

```
AoW.exe Info-Window button click                          [UI — human only]
  └─► TExplorationSite.Search@0x557c1e5c    ← ZERO code callers in DLL (VMT+0x200)
        └─► token ─► ExecuteTE@0x557c1d28 ─► ExecuteSearch@0x557c1a20      [engine-side]
              ├─ no defenders → vmt+0x1f8 directly
              └─ CreateCombat → SetupCombat@0x557c1960
                    combat[0xb] = CombatExecuted@0x557c1894
                      └─► vmt+0x1f8 = ExecuteSearchDone
                            └─► TItemExplorationSite.ExecuteSearchDone@0x557c29e0
                                  per item: TItem.PlaceOnMap@0x55794730   ◄── ON THE GROUND
```

Fires on combat result code 3 or 6, logs `ItemsFoundRStr`. Items are pre-stocked at map-gen by
`Generate@0x557c2944` → `TItemControl.GenerateItem@0x55794f40` (weighted random by rarity byte
`item+0x45`, filtered by category mask + obtain-value range).

Five classes share this reward (VMT+0x1f8 → `0x557c29e0`): `TItemExplorationSite`, Monsterlair,
Crypt, Ruin, Pyramid. `TDungeon` overrides separately at `0x557c5ad4` and grants **prisoner units**,
not items.

### 3.2 Why the AI never enters that path

**`TStructureAIPA.Process@0x557625f4` IS the AI's per-structure hook.** Each AI turn it walks a
structure-ID list (`this+0x18`), resolves each via `TStructureControl.FindID`, and calls
**`vmt+0x1c0` = `ExecuteAI`**, passing `player+0xA6` and the phase (`this+0x14`; 1 = Phase1,
2 = Phase2).

**Crucially, that list is UNFILTERED — every structure on the map.** `TStructureAIPA.Activate@0x55762594`
(verified 2026-07-21) skips only player 0, then loops `TStructureControl.GetCount/GetStructure` over
`map+0x100` adding every `structure+0x1c` ID. So **`ExecuteAI` is already invoked on every exploration
site, for every AI player, every AI turn** — reachability was never the problem, only the empty stub
is. Ownership is the *implementor's* job: `TAltar.ExecuteAI@0x557cf2b0` opens with
`if (playerIdx == structure+0x30 && (phase==1||phase==2))`, i.e. it does its own owner check, so a
site implementation is free to gate on "is this player's army standing on me?" instead.
Loop protocol: each iteration is gated on `GetProcessTimeLeft > 0` **and `TPlayer.GetBusy == 0`;**
`ExecuteAI` returning 0 deletes the entry and continues, nonzero keeps it and breaks.

For **all seven exploration-site VMTs** — `0x557c1600`, `0x557c257c`, **`0x557c2ee4`
(`TItemExplorationSite`)**, `0x557c573c`, `0x557c6690`, `0x557c6abc`, `0x557c6ee0` — slot `+0x1c0`
resolves to `TStructure.ExecuteAI@0x5575e698`, which decompiles to:

```c
undefined4 TStructure_ExecuteAI(void) { return 0; }
```

A bare stub. (Slot arithmetic cross-check: `ExecuteAI` +0x1c0, `ExecuteSearch` +0x1fc, `Search`
+0x200 — the VMT xref sets differ by exactly 0x3c / 0x40 as expected.) Only `TAltar.ExecuteAI@0x557cf2b0`
(storm-casting via `TStorm.GetBestTarget` + AI budget) and a couple of others implement it for real.

**[exe] There is exactly one `call [reg+0x200]` in the entire binary** —
`TIWindow.MainBtnClick@0x00442328` (+0x11d), the Info Window context-action button:

```
0044242D  mov  edx, [0x45e650]   ; ExploreS..TExplorationSite classref
00442433  call @IsClass
0044243A  je   0x442450
00442441  mov  eax, ebx          ; Self = selected structure ([[0x45A420]]+0xA8)
00442443  mov  edx, [eax]
00442445  call [edx + 0x200]     ; TExplorationSite.Search  <-- THE ONLY ONE
```

Zero `call [reg+0x1fc]` (`ExecuteSearch`) anywhere. AoW.exe imports **`CanSearch`** (IAT `0x0045E64C`)
but **not `Search`**. The button-enable logic hard-wires the local player:

```
00442FFE  mov  dl,  [eax + 0xa5]   ; map+0xA5 = LOCAL PLAYER INDEX
00443011  call TExplorationSite.CanSearch(site, localPlayer)
0044301D  call [ecx + 0x6c]        ; MainBtn.SetEnabled(result)
```

The exe cannot even *ask the question* on behalf of anyone but the local client's player.

### 3.3 `TItemHS` (ground item) can never be an AI target

AI target discovery broadcasts map-field message **`0x1200`**; `TAoWMapField.GetAITarget@0x55771d84`
sends it, `TStructure.MapFieldMsgProc@0x5575f730` answers via `UpdateAITarget` (vmt+0x1c4).
`TItemHS` fails at three independent levels:

**It never answers the broadcast.** Making it answer looked like ONE VMT slot rather than three doors
— **but that was tried and did not work** (§6b-2, reverted 2026-07-22). The most likely reason is that
the premise below is wrong at its root: it is **unproven that `TItemHS` receives msg `0x1200` at all**,
because `SendMapFieldMsg` lives in HSEPack.dpl which Ghidra does not have. Treat everything in this
subsection as *verified structure* + *one unverified delivery assumption*.

`TItemHS` **does have a `MapFieldMsgProc` slot** — it inherits `THexagonSprite`'s, which ignores
`0x1200`. It was absent from the implementor list only because it never *overrides*, which was misread
as never *receiving*; whether it actually *receives* is the open question. Verified against the file:

- `0x55710138` is the **vmtSelfPtr cell**, not the VMT. The real **VMT base is `0x55710178`**, length
  **`0x110` (68 slots)** — the `\x07TItemHS` name shortstring sits at `+0x110`, so **slot `+0x1C4`
  does not exist on this class**.
- **`MapFieldMsgProc` is slot `+0xCC` in all 94 classes that have it** (introduced by the common
  ancestor `THexagonSprite`; zero offset variance). `TItemHS` VMT`+0xCC` = **`0x55710244`**
  (file offset `0xF644`) currently holds `0x55701D4C` = `JMP [0x558FC078]`, the HSEPack thunk.
  `TStructure` VMT`+0xCC` = `0x5575F730` — same slot index.
- ⚠ **Do NOT point `TItemHS`'s slot at `TStructure.MapFieldMsgProc`.** That handler calls `+0x1C4`,
  `+0x188`, `+0x184`, `+0x180`, `+0x170`, `+0x16C` — all past the end of a 68-slot VMT, landing in the
  *next class's* VMT — and reads `self+0x2C`, past the 20-byte instance. Catastrophic, not merely wrong.
- **No new virtual slot is needed.** `TArmyHS.MapFieldMsgProc@0x55791C30` is the template: a
  non-structure hotspot that chains to its parent, guards on `msg[6]==0`, and for `0x1200` calls
  `TArmy.UpdateAITarget@0x55790618` **directly**, then sets `msg[7]=1` (stop-propagation) if the
  priority came back negative. A `TItemHS` handler can compute its priority inline the same way.
  ⚠ **This analogy was the basis of the failed §6b-2 attempt and may not hold.** `TArmyHS` may receive
  `0x1200` because the *army* is registered with the map field in a way a passive item hot-spot is not.
  Settle delivery with a counter stub before building on it again.
- All 68 slots carry `.reloc` HIGHLOW fixups, so repointing `+0xCC` to a cave VA rebases correctly —
  the sanctioned "reuse a VMT slot that already has a reloc entry" pattern.

**Message record layout** (`TAoWMapField.GetAITarget@0x55771D84` zeroes 24 bytes, broadcasts, returns
`record[0] != 0`): msg `+0x00` msgid · `+0x04` TMapField* · `+0x08` query ctx · `+0x0C` result rec ·
`+0x10` TAIGroupControl* · `+0x18` hex sub-index · `+0x1C` stop-propagation. Query ctx (3 bytes) =
`[0]` player, `[1]` relation, `[2]` **mode** (0 for normal target search). Result rec `+0x00`
**priority** → lands at `TAIGroupControlTarget+0x18`, sorted **descending** by
`SortOnPriority@0x557381AC`; `+0x08`/`+0x0C` gold/mana cost — **leave these zero** or the AI will try
to spend resources it does not owe via `MakeTargetExpense`.

**Priority scale observed:** `TPlayerStructure` 10 flat · `TAltar` `byte[+0x41]*10+10` · enemy army 50 ·
army with hero 100 · army with wizard 300 · enemy/neutral city `(size-1)*10+100` = 100–130 · own-city
defence (mode 5) 600–1000+. Items should score ~10–30 so they win only when nothing else is near.
Use **max-combine** (`if (*out < p) *out = p`), as `TCity` does — not plain assignment.

`TItemHS.MsgProc@0x55795fc0` handles exactly **one** message: `0x20020001` (map init, gated on
`AoWHSMap+0x174 == 1`) → `GenerateItems`. That is its entire reactive surface.

**Every reference to the `TItemHS` classref `0x55710138` in the module:** `TItem.PlaceOnMap@0x557947d2`
(creates it), `TAoWEngine.Create@0x55797dfa` (registration), and
**`MapCtrl.TAoWMapControl.SelectHS@0x5580602f` / `DeselectHS@0x55806121`** — human mouse selection.
Pickup is *literally* mouse-only; there is no programmatic path at all.

**Exploration sites are NOT AI movement targets either.** `TStructure.UpdateAITarget@0x5575e69c` is a
**bare empty procedure** (`void f(void){return;}` — verified 2026-07-21), so a site *inheriting* it is
exactly equivalent to not implementing it: the priority record stays 0 and `GetAITarget` returns
false. All 13 real `UpdateAITarget` implementors are economic/strategic (City, Farm, Mine, Gems,
ManaCrystals, PowerNode, ProductionPlace, Shipyard, Tower, WizardsTower, PlayerStructure, Army); no
exploration-site class implements it. Contrast `TMine.UpdateAITarget@0x557b4498`, which max-accumulates
into `*out` — `0x32` neutral, `0x19..0x4b` for an enemy scaled by diplomatic relation, `0x14` for
mode 6 — signature `(EAX=self, EDX=asker[3] = player/?/mode, ECX=int* out)`.

Site defenders are spawned *by* `ExecuteSearch` from stored data (not standing armies), so the AI
cannot reach the loot by ordinary attack either. **⚠ This is also the central hazard for any future
"make the AI seek sites" work**: the target tile reads as EMPTY to `TCombatPredictor` /
`GetRequiredStrength`, so superiority is unbounded and the AI would send a lone scout into a
dragon-stocked dungeon — the same class of defect as the AI suicide-raze vetoes.

---

## 4. The AI has no item concept anywhere

- **`THero.ExecuteUpgradeHeroAI@0x55787a24`** is the AI's *entire* hero brain: a weighted-random
  pick over 8 options — ATK (needs ≥4 skill pts, cap 10) / DEF (≥16, cap 10) / RES (≥8, cap 10) /
  DAM (≥8, cap 10) / HP (≥3, cap 30) / abilities `0x2E` (w 10), `0x7A` (w 10), `0x34` (w 100 or
  9999 = effectively a priority pick) — looping while skill points remain. **No item reference.**
- **`TItem.GetObtainValue@0x557945b4`** (the "what is acquiring this worth" hook that AI-targetable
  objects implement) is called only by `TItem.GetCampaignTransferPoints`, `TItemControl.GenerateItem`
  and `GenerateItems` — i.e. random-item generation value budgeting. **No AI caller.**
- **`TAbstractUnit.MovedTo@0x55780328`** (hex arrival) does move-point cost, the Path abilities
  (Life `0x45` / Decay `0x44` / Frost `0x6d`) and Trail of Darkness (`0x1a`). **No pickup** — there
  is no automatic pickup for *anyone*.
- **AI behaviour vocabulary** (17 `ProcessStates` overrides; canonical `TNormalAGC@0x557dd3c8`,
  state var `this+0x16c`): defend · find move-target · recruit · find production location ·
  select/attack target · raze · defend-target · combine idle groups. **No loot/treasure state.**
- Equipment *does* reach AI strength math implicitly — `THeroItems.GetAttack@0x55786354` is folded
  into `THero.GetAttack@0x557883a0` — but no AI function enumerates or values items as objects.

---

## 5. Every route by which any hero comes to hold an item

Only three primitives ever write `hero+0x70` (THeroItems) / `hero+0x74` (THeroInventory):
`THeroItems.PlaceItem@0x55786788` (2 callers), `TItem.SetArrayOwner@0x55794274` (vtable-only), and
`THero.ReadWrite@0x55788880` (property tags **0x24** inventory / **0x25** equipment).

| # | Route | AI? |
|---|---|-----|
| R1 | In-game drag/drop + Use — `TUnitWindow.Gnd1Change@0x0040A344` → `PlaceItem` → token → `ExecutePlaceItem` | **No** |
| R2 | **Map-editor authored gear** — AoWDevEd `THeroEditForm.AddItemBtnClick@0x00416364` → `THeroItems.CanPlaceItem`@`0x004163D0` → `ItemGrid.TItemGrid.AddItem@0x55802bf8` → `SetArrayOwner`. Positional branch taken because `THeroItems`/`THeroInventory.GetControlStyle` OR in `0x08` (bytes at `0x55786338`/`0x55786058`). Owner set by `TArmyEditForm.PlayerComboBoxChange@0x00419EB0` → `TArmy.SetPlayer` | **YES** |
| R3 | **Hero-pool emergence / hero-for-hire** — `TPlayer.MakeHeroEmerge@0x55752520`, `UpdateHeroJoin@0x5575295c` place an unowned `THeroControl` hero for *any* player; only the event-log popup is human-gated. Carries whatever R2 attached | **YES** |
| R4 | Campaign transfer — `ExecuteSelection@0x55731894` → `THero.AutoPlaceItem@0x5578901c` | **No** — target player found by walking down **while `player+0xA7 != 0`**, i.e. it deliberately stops at the first *human*; `Retrieve@0x55731000` harvests only from that human |
| R5 | Save/load round-trip (`THero.ReadWrite` tags 0x24/0x25) | persistence, not acquisition |

**Verified non-routes:** exploration sites / treasure (§3) · hero death (`THero.Killed@0x55787164`
calls `ExecutePlaceItem(hero, id, 0xE)` for all 8 backpack then 6 equip slots — **removal only**,
and note it does so *directly, with no token*, so unbinding is fully engine-side and works fine for
AI heroes) · `TItemList.AddChild@0x557948ec` (sole caller `TItemLibrary.AddChild@0x5579520c`,
library authoring) · AoWTCPCK.dpl and aowInt.dpl have **no item imports at all**, so there is no
combat-side acquisition.

---

## 6. Useful facts established along the way

- **`map+0xA4` = current-turn player · `map+0xA5` = local player index · `player+0xA7 == 0` = human.**
  Confirmed from `TAbstractAoWHSMap.SetCurrentPlayer@0x55772a80` (writes exactly +0xA4) and
  `TPlayer.MakeHeroEmerge@0x55752520`. **The `THeroUpdateTE.Execute` guard is `map+0xA4`, i.e. the
  current-turn player, NOT the local human** — so the *execution* half of the item path is already
  AI-safe; only token creation is blocked. (Don't confuse with the `map+0xA5` local-human gate used
  by `cave_razemode`.)
- **The AI turn loop is entirely `TAIExecuter` inside AoWEPACK.dpl.** AoW.exe imports **zero**
  `TAIExecuter` symbols (its only AI-named imports are `GetUnitIndexAIPriority` and the
  `TUnitSelectorAAI` classref). Driver: `TAIExecuter.Process@0x55734780` ←
  `TAoWHSMap.NewFrame@0x55777d26`; `ActivatePlayer@0x55734504` ← `TTurnPlayerControl.NewTurn@0x55756a52`,
  `TSimultaniousPlayerControl.NewTurn@0x557590f3`, both `StartLoadedMapEx`,
  `TAoWHSMapKeyboard.KeyDown@0x55773f0b`. **⇒ for this subsystem "UI-only" is equivalent to
  "human-only", and the equivalence holds generally.**
- `TStructure.ExecuteAI@0x5575e698` being a stub is a **general** AI gap, not an item-specific one —
  it is the AI's only per-structure action hook and almost nothing implements it.

---

## 6b. IMPLEMENTED — AI ground-item pickup (`build_ai_itempickup.py`, **CONFIRMED WORKING 2026-07-21**)

**Status: applied and confirmed in-game by the user 2026-07-21.** Backup `.pre-aipickup`.
Test that confirmed it: two AI heroes trapped on one hex, one holding an item killed → the survivor
picked the item up. **Hero-death drops land on the strategic hex — from tactical deaths as well as
strategic-map deaths** (heroes can be killed on the strategic map too). Do not re-derive the opposite
from the `map[0x47]` preference in `ExecutePlaceItem`'s drop branch — see the caution in §6d.

Scope deliberately narrow: an AI-owned hero **standing on** a hex with a ground item takes it into an
**empty equip slot of the matching type**. No backpack fallback (an AI can never re-equip, so a
stashed item is dead weight). This does *not* address §3 — the AI still never searches sites.

**Two hooks, one shared worker, caves at `0x55810000` (verified-zero tail, see §6c).**

| Piece | VA | Notes |
|---|---|---|
| `cave_pickup` | `0x55810000` (183 B) | shared worker, `EAX = THero*` |
| `cave_nt` | `0x55810100` (24 B) | hook A wrapper |
| `cave_moved` | `0x55810140` (46 B) | hook B wrapper |
| **hook A** | `0x55787FD7` | `E8 70 8D FF FF` → `call cave_nt`; cave performs the displaced `TAbstractUnit.NewTurn@0x55780D4C` then rets to `0x55787FDC` |
| **hook B** | `0x5578051B` | `5F 5E 5B 59 5D` → `jmp cave_moved`; cave replays the popped registers + the untouched `ret 4` |

Worker logic — **slots are the OUTER loop**, ground list refetched per slot, break on success:

```
gate: map+0x11c == 0 (strategic only) · GetPlayers(map+0x140, hero+0x24) non-null ·
      player+0xA7 != 0 (AI) · hero+0x70 (THeroItems) non-null
for p in 0..5:
    list = THero.GetItemsOnGround(hero)        # NULL on a hex with no hot-spot -> bail
    for i in 0..: item = TItemList.GetItem(list,i)   # bounds-checked, 0 past end
        if THeroItems.CanPlaceItem(hero+0x70, item, p):
            THero.ExecutePlaceItem(hero, [item+0x14], p); break   # list may now be FREED
```

**Why it is shaped this way** (each point is a defect found and fixed during design):

- **`THeroItems.CanPlaceItem@0x5578674c` IS the predicate** — it already enforces `pos < 6`, slot
  empty, and type match. Nothing hand-rolled. (Disassembly: Mechanics §4.)
- **`GetItemTypePosition@0x55786740` deliberately NOT used.** Unchecked 7-byte table read, and the
  tables are asymmetric: **type 4 owns slots 3 AND 5**, while the forward table can only return 3 —
  so slot 5 is unreachable via the lookup. The 0..5 scan reaches it because `CanPlaceItem` maps
  position→type and compares, instead of indexing by type. Full tables + the out-of-bounds read:
  Mechanics §4.
- **Refetch-per-slot, break-on-success** — `TItemHS.ItemsChanged@0x55795d10` calls `[VMT-4]`
  (Destroy) when the list empties, **freeing the TItemHS and its TItemList**. The list pointer is
  dead the instant a pickup succeeds. Only item **IDs** (integers) cross a mutation boundary.
  The ground list also *compacts* on removal (style `0x01`), so a naive `i++` would skip items —
  both hazards and the exact self-destruct condition: Mechanics §3, §5.
- **Iterate with `TItemList.GetItem` until it returns 0; never read a count.** The count is at
  `[[list+8]+8]`, **not** `list+8` — reading the latter yields garbage and walks off the heap.
  Mechanics §2.
- **`GetItemsOnGround` returns NULL** on nearly every hex — null-checked (an unchecked deref here
  would crash on the first AI hero to take a turn).
- **`TPlayerList.GetPlayers` is bounds-checked** and returns 0 out of range — null-checked.
- Hook B gates on `IsClass(unit, THero)` via `@IsClass@0x557010C0` + classref cell `0x55711FAC`,
  since `MovedTo` fires for every unit. `TLeader` parents to `THero` (VMT `0x55712238` →
  `0x55711FEC`) so the wizard is included; `TUnit` parents to `TAbstractUnit` and is rejected.

**Direct `ExecutePlaceItem`, not a token — and this is MP-safe at these two sites specifically:**
both injection points run on **every peer**. `THero.NewTurn` is reached by message broadcast
(`TAbstractUnit.MsgProc@0x55781238`, msg `0x20020002` → unit VMT `+0x13c`) downstream of
`TEndTurnTE.Execute@0x557473c4`, with no locality gate anywhere (at `0x55747431` the
`CALL [ECX+0x84]` result is discarded, not tested). `TAbstractUnit.MovedTo` is reached from
`TMoveArmyTE.ExecuteMove@0x557481fc` → `TArmyHS.MoveTo@0x55791068` → `TArmy.MovedTo@0x5578de24`,
which iterates army members calling each `VMT+0x18c` — **so a hero inside a moving army does get it**,
and the hot-spot has already been re-linked to the destination square, so `GetItemsOnGround` reads
the *new* hex. `ExecutePlaceItem` is side-effect-clean (no RNG / event log / sound / dialog / token /
`map+0xA5` read); its only non-state effect is `THero.Changed` (VMT `+0x90`), which
`TAbstractUnit.Killed` already calls unconditionally on all peers. Precedent for untokenised
placement: `THero.Killed@0x55787164`.

⚠ **A manual token mint would be actively WRONG here** — since the injection points run on every
peer, every peer would mint the token ⇒ N pickups, or an exception on the non-authoritative peers.

⚠ **…and it could not work anyway.** `THero.PlaceItem` re-checks `TPlayer.GetBusy`, which reports
busy whenever the player's token control has *any* queued event **or** the executer is mid-pass
(`executer+0x24 & 2`, held across the entire drain loop). So a token-minting pickup hooked anywhere
downstream of token execution is **silently refused — no error, no effect**, and even outside
execution only the first call per pass would land. Tokens are also *asynchronous*: `AddEvent` only
enqueues. So direct `ExecutePlaceItem` is not a convenience preference, it is the only route that
functions. Disassembly and polarity warning: `AI_ItemPickup_Engine_Mechanics.md` §6–§7.

**Non-collisions verified:** Path of Sand hooks `0x557804B7` (inside `MovedTo`, rejoins vanilla flow
and still reaches the epilogue) — different address. `build_spellcast_multiturn.py` uses
`0x55787FEC` as a live `jmp` target; hook A sits at `0x55787FD7` and ends at `0x55787FDC`, well clear.

## 6d. Hero-death drops — a caution against a tempting wrong reading

`ExecutePlaceItem`'s drop branch (pos `0xE`) prefers `map[0x47]` (= `map+0x11c`, non-nil in combat)
over the main map, then places at `GetLocation(hero)` via `DropHeroItem@0x55773770`. That reads as
"a tactical death drops onto the combat map and the loot is lost". **That inference is WRONG —
confirmed in-game: tactical deaths drop on the strategic hex, and so do strategic-map deaths.**
`TCombatUnit.KillUnit@0x557256e4` is a one-liner calling `[combatUnit+0x4c]->VMT+0x1ac`, i.e. the
*strategic* hero's `Killed`, so tactical deaths genuinely run that path. **UNRESOLVED:** whether
`map+0x11c` is nil at that moment, or the combat map's `DropHeroItem` resolves back to the strategic
hex. Don't assert either without tracing it. (The other drop path,
`THero.DropItemsOnMap@0x557870d4`, takes an explicit map + x/level/y and is used by
`TFastCombatUnit.KillUnit@0x55743ab2`.)

## 6b-2. TRIED AND REVERTED — items as AI targets (`build_ai_itemtarget.py`, 2026-07-21/22)

**Status: built, applied, produced no observable effect, REVERTED 2026-07-22. Do not re-apply as-is.**
The script is kept (with a working `--revert` mode) because the analysis under it is sound and the one
failed assumption is cheap to test directly.

**What it did:** repointed `TItemHS` VMT `+0xCC` (VA `0x55710244`, file offset `0xF644`) from the
inherited HSEPack thunk `0x55701D4C` to a 174-byte cave at `0x55810200`. The cave chained to the
inherited handler, then answered AI-target broadcast `0x1200` with
`priority = 10 + min(maxObtainValue/10, 20)` (10–30), max-combined into `record[0]`. Modelled on
`TArmyHS.MapFieldMsgProc@0x55791C30`. Deliberately no fog gate (vanilla AI targeting has none —
`TMine`/`TCity` gate on ownership/relation only) and only `record[0]` written (`+0x08`/`+0x0C` are
gold/mana cost; writing them would make the AI spend resources it does not owe).

**Result: the AI showed no sign of pathing to items.** Not diagnosed further.

**Prime suspect — the one assumption that was never provable statically (~90% at build time):**
`SendMapFieldMsg` lives in **HSEPack.dpl, which Ghidra does not have**, so it was never proven that
msg `0x1200` is delivered to a `TSingleHS` hot-spot at all. The supporting evidence was analogy:
`TArmyHS` is a single-hex `THexagonSprite` descendant that receives `0x1200` at the same `+0xCC` slot
and demonstrably works. **The analogy may simply not hold** — `TArmyHS` may be reached because the
*army* is registered with the map field differently than a passive item hot-spot.

**Cheapest next diagnostic if this is ever resumed:** point `+0xCC` at a stub that does nothing but
bump a counter in BSS slack (or write one combat-log line) and see whether it fires at all. That
settles delivery in one test and costs ~20 bytes. Only if it *does* fire is the priority/So-what
logic worth revisiting.

⚠ **Do NOT re-derive the `TStructure.MapFieldMsgProc` shortcut** — see §3.3: that handler calls VMT
slots past the end of `TItemHS`'s 68-slot VMT and reads past its 20-byte instance. Catastrophic.

**Second-order note:** even with delivery working, an AI hero that walks to an item it *cannot* equip
(wrong type, or slot full — the pickup patch fills only an empty matching equip slot) leaves it on the
ground where it stays a valid target, a potential oscillation. Mitigation would be to return 0 unless
some hero in the asking group can actually take the item.

### ⚠ Revert-layer lesson (the reason this entry exists in this form)

The header of `build_ai_itemtarget.py` originally said "Revert = copy `AoWEPACK.dpl.pre-aiitemtarget`
over `AoWEPACK.dpl`". **That instruction was correct when written and became destructive within ~7
hours.** By revert time `.pre-aiitemtarget` was **5th** in the stack, with `.pre-razedlgfix`,
`.pre-combatdiag`, `.pre-clogtypegate` and `.pre-hpbarclamp` applied on top of it — restoring it would
have silently wiped all four. The revert was instead done **surgically in place**: restore the VMT
slot to `0x55701D4C`, zero the 256-byte cave zone, verify-before-write, no backup layer disturbed
(`--revert --apply`). Verified afterwards that the pickup patch's two hooks and three caves, and the
later feature's cave at `0x55811000`, were all untouched.

**This is the general pattern to copy: a feature whose footprint is a VMT slot + an exclusively-owned
cave zone can always be undone surgically. Prefer that to any backup restore.**

## 6c. Cave space — the DLL is not short of it (measured 2026-07-21)

`AoWEPACK.dpl` CODE = VA `0x55701000`, vsize `0x1E6918` (virtual end **`0x558E7918`**), rawsize
`0x1E6A00`, chars `0x60000020`. **rawsize ≥ vsize ⇒ the whole section is file-backed** — patching the
tail changes no headers and no file size. Last non-zero byte: **pristine shipped DLL `0x5580BDEE`**;
live DLL `0x5580F959` ⇒ **884,670 verified-zero bytes** available. Every cave this project has ever
written lives in that tail (~16.7 KB used), so it is proven usable in-game. Allocate upward from
`0x55810000`; ceiling `0x558E7918` (DATA starts `0x558E8000`). Still read+execute — mutable state
belongs in BSS slack from `0x558FA800`. See the correction note in `Investigation_INDEX_2026-07-08.md`
§1; the "~20 bytes of slack" claim in `Investigation_Abilities_Leadership.md` §1.4 is about **AoW.exe**
and remains correct there.

## 7. Further work (SPECULATIVE — nothing built or tested)

`THero.AutoPlaceItem@0x5578901c` is a **ready-made, correctly-shaped engine-side "give item to hero"
primitive**: try the correct equip slot via `THeroItems.GetItemTypePosition` + `CanPlaceItem`, else
first free `THeroInventory` slot via `GetFreeSlot@0x5578601c`, returns bool. Vanilla wires it up in
exactly one place (campaign carry-over). **The missing piece is a caller, not the mechanism.**

⚠ **But it inherits the slot-5 blind spot.** Because it routes through `GetItemTypePosition`, a
type-4 item can only ever be offered ring slot **3** — if that slot is full it falls through to the
backpack even when ring slot **5** is empty (`AI_ItemPickup_Engine_Mechanics.md` §4). For an AI that
is a real loss, since an AI can never re-equip out of its backpack. Any AutoPlaceItem-based design
should either pre-scan 0..5 with `CanPlaceItem` first, or accept that AI heroes fill only one ring.

Two separable pieces of work — note that **fixing pickup alone accomplishes nothing**, because
without a search the loot never spawns:

1. **Make the AI search sites** (the deeper gap, and arguably the bigger AI improvement independent
   of items). Implement `ExecuteAI` for the exploration-site VMTs (slot `+0x1c0`, currently the
   `return 0` stub) to call `vmt+0x200` (`Search`).
   - **Key enabler:** `Search` is written **player-agnostically** — it takes no player parameter and
     derives the actor from whichever army occupies the tile (army hotspot `0x20217`). Traced through
     `GetBusy` for an AI player *during its own turn* (`map+0xA4` == that player, `player+0x44 == 0`,
     `GetLocal` true in single-player, turn-timer check skipped because `player+0xA7 != 0`), it
     returns not-busy and the search **would proceed and dispatch normally**. So the correct framing
     is *"nothing ever calls it on an AI path"*, **not** *"the engine refuses AI searches"* — this
     looks like a small hook rather than a fight with the gating.
   - **⚠ Known hazard:** `Search`'s second branch raises a **`TCombatTypeRequestEventLog`** (the
     fast/tactical ask dialog) when the human-player count is 1 or `map+0x139 != 0`. That is the
     **same dialog family as the AI-raze dialog freeze** fixed on 2026-07-11 via
     `cave_razemode@0x5580D100` (forces AI/remote razes FAST via the local-human gate
     `map[+0xA5]==player && GetPlayers[+0xA7]==0`). Expect to need the same treatment, or AI searches
     will stall the turn.
2. **Deliver the loot to the hero.** Hook `TItemExplorationSite.ExecuteSearchDone@0x557c29e0` to call
   `AutoPlaceItem` on a hero in the clearing stack, in place of / alongside `TItem.PlaceOnMap`. It
   already has the searching army in hand (`param_1[1]->vmt+0x80(0x20217)`, whose `+0x1c` `+0x12` is
   the player). **MP-safe:** it runs from the combat-completion callback on every peer, behind no
   local-player gate.

Optional extra: a ground-sweep so AI heroes collect items already lying on the map (from R2 heroes
that died, or from a human's drops) — but there is no AI target path to a `TItemHS` (§3.3), so this
needs its own trigger, e.g. in the AI move/arrival code rather than target selection.

---

## 8. Open / unverified

- **R2's "AI-held" step is an inference at one joint:** the editor assigns a *player slot*, and
  whether that slot is AI is decided at game setup, not baked into the hero. Not verified in-game.
- **`THero.ReadWrite` skips both item tags when `hero+0x5d & 1` is set.** The writer of that bit was
  not located. It must be clear during normal map/save serialization or no hero would keep gear
  across a save, so it reads as a transient partial/sync-write flag — but it is unconfirmed.
- Nothing here has been tested in-game; it is all static analysis.

---

## Quick reference — addresses

**Blocked doors:** `THero.PlaceItem@0x55788e94` · `TExplorationSite.Search@0x557c1e5c` (VMT+0x200)
· `TStructure.ExecuteAI@0x5575e698` (VMT+0x1c0, `return 0` stub)

**Item→hero primitives:** `THero.AutoPlaceItem@0x5578901c` · `THero.ExecutePlaceItem@0x5578907c` ·
`THeroItems.PlaceItem@0x55786788` · `TItem.SetArrayOwner@0x55794274` · `THeroInventory.GetFreeSlot@0x5578601c`

**Token path:** `THero.CreateHeroUpdateTE@0x55788c60` · `THeroUpdateTE.Execute@0x55789cdc` ·
`THeroUpdateTE.ReadWrite@0x55789c80`

**Reward path:** `ExecuteSearch@0x557c1a20` (VMT+0x1fc) · `SetupCombat@0x557c1960` ·
`CombatExecuted@0x557c1894` · `TItemExplorationSite.ExecuteSearchDone@0x557c29e0` (VMT+0x1f8) ·
`TItem.PlaceOnMap@0x55794730` · `TItemControl.GenerateItem@0x55794f40` · `Generate@0x557c2944`

**Drop path:** `THero.Killed@0x55787164` · `THero.DropItemsOnMap@0x557870d4` ←
`TFastCombatUnit.KillUnit@0x55743ab2` · `TAbstractAoWHSMap.DropHeroItem@0x55773770` (map vmt+0x108)

**AI:** `TStructureAIPA.Process@0x557625f4` · `THero.ExecuteUpgradeHeroAI@0x55787a24` ·
`TAIExecuter.Process@0x55734780` · `TAIGroupControl.MainProcessStates@0x55739138` ·
`TNormalAGC.ProcessStates@0x557dd3c8` · `TAoWMapField.GetAITarget@0x55771d84` ·
`TStructure.MapFieldMsgProc@0x5575f730` (msg `0x1200`) · `TStructure.UpdateAITarget@0x5575e69c` (VMT+0x1c4)

**[exe] UI:** `TUnitWindow` VMT `0x0040710C`, DFM foff `0x1E8B9C` · `Gnd1Change@0x0040A344` ·
`UseItemClick@0x00409FFC` · `TIWindow.MainBtnClick@0x00442328` (the single `call [reg+0x200]` at
`0x00442445`) · thunks `0x402774`/`0x40276C`/`0x402764`/`0x40275C`/`0x402754` ·
`TGeneral` singleton `[0x0045A420]`
