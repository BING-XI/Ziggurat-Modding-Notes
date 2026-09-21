# AI and structures

This file covers the AI's behaviour toward items, exploration sites, and razing; the structures
that behaviour acts on (exploration sites, the six non-city razeable structure types, cities, the
Arena, Shipyards); and the combat/dialog machinery that raze, rebellion, loot and arena battles all
share. It does **not** cover item stat layout or the scroll/HP/MV item features (`11-engine-internals.md`),
unit spellcasting (`06-unit-spellcasting.md`), spell or terrain mechanics
(`04-spells-modded.md`/`05-spells-added.md`/`09-terrain-movement.md`), or the combat-log GUI
implementation (`07-ui.md`) — two of that system's bugs are noted here (§4.5) only because they were
found *during* the raze investigation and share its `+0x4C` wall-aliasing root cause; their owning
docs and scripts live in `07-ui.md`.

This is the largest single topic in the corpus. The raze combat predictor and the raze-as-real-battle
rework it grew into are the project's biggest piece of analysis and iteration: nine call-stack layers
of AI decision-making, a predictor with a genuine exploit, and an eleven-stage build that turned
razing, city rebellion and city looting into real fought battles. That version history — why each
stage exists, what the previous stage got wrong, which approaches were tried and abandoned — is kept
at length below because it exists nowhere else; the build script itself only shows the final bytes.

## Status table

| feature | status | owning script | binary |
|---|---|---|---|
| ⭐ Tactical-combat AI per-frame work budget 1 → 16 (the inter-move pause) — §9 | ✅ CONFIRMED WORKING (2026-09-12) — 0.5 s+ of the ~0.7 s stall gone | `build_combat_ai_budget.py` | `AoWTCPCK.dpl` |
| AI paths to and searches exploration sites | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_ai_sitesearch.py` | `AoWEPACK.dpl` |
| AI heroes pick up / upgrade-swap ground items; items become AI targets | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_ai_itemloot.py` | `AoWEPACK.dpl` |
| AI item pickup, empty equip slots only (superseded) | ✅ CONFIRMED WORKING (2026-07-21) — superseded, `--undo`'d 2026-09-02, must stay inert | `build_ai_itempickup.py` | `AoWEPACK.dpl` |
| Items as AI targets, group-blind priority (v1) | 🛑 REVERTED (2026-07-22) — caused AI loitering next to unusable loot; superseded by `cave_target` | `build_ai_itemtarget.py` | `AoWEPACK.dpl` |
| Exploration-site / dungeon defender roster variation | 🔨 APPLIED, UNTESTED (2026-07-29) | `build_sitedefender_vary.py` | `AoWEPACK.dpl` |
| Non-city structure raze-defender roster variation | 🔨 APPLIED, UNTESTED (2026-07-10) | `build_razeroster_vary.py` | `AoWEPACK.dpl` |
| AI raze-evaluation timing fix (the accidental 4th gate) | 🔨 APPLIED, UNTESTED (2026-07-12) | `build_razeeval_timing.py` | `AoWEPACK.dpl` |
| ⚠⚠ **`--want-open` diagnostic lever left live** (AI razed friendly / own-race cities) — §3.6 | 🛑 REVERTED (2026-09-11) — byte `0x557D7414` `05`→`01`; fix itself 🔨 APPLIED, UNTESTED | `build_razediag.py` | `AoWEPACK.dpl` |
| `razeok` re-entry leak fix (v5) | ✅ CONFIRMED WORKING (2026-07-12) | `build_razebattle_tower.py` (`cave_forcefail`) | `AoWEPACK.dpl` |
| AI non-city scorched-earth raze allowance (v6) | 🔨 APPLIED, UNTESTED (2026-07-12) — first engineered test was inconclusive; see Open items | `build_razebattle_tower.py` (`cave_forcefail`) | `AoWEPACK.dpl` |
| `simfly` — fast-combat-equivalent flying economics in `TCombatPredictor` | ✅ CONFIRMED WORKING (2026-07-09) | `build_simfly.py` | `AoWEPACK.dpl` |
| Raze-as-real-battle: tower/structure plumbing (Stage 1) | ✅ CONFIRMED WORKING (2026-07-10) | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| Raze-as-real-battle: result gate, avengers removed, combat log, no-force block (Stages 2–2.2) | 🔨 APPLIED, UNTESTED (2026-07-10) | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| Raze-as-real-battle: manual/tactical combat-type choice (Stage 3) | 🔨 APPLIED, UNTESTED (2026-07-10) | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| Raze-as-real-battle: generalised to all six non-city razeable structures (Stage 8) | 🔨 APPLIED, UNTESTED | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| City raze as a real battle (Stage 9) | 🔨 APPLIED, UNTESTED | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| Rebellion as a real battle + rebellion-chance table (Stage 10/10b) | 🔨 APPLIED, UNTESTED (2026-07-12) | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| Loot as a real battle + fast/manual payout timing (Part C) | 🔨 APPLIED, UNTESTED (2026-07-12/13) | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| Survivor re-homing, Guard AG, roster substitution on a loss (Design A / Stage 11) | 🔨 APPLIED, UNTESTED | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| Combat-type dialog shown to a non-participant + modal freeze (4 defects) | 🔨 APPLIED, UNTESTED (2026-07-21) | `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| BSS flag collision: `simfly`/`razeok` vs `build_path_outerring.py` | 🔨 APPLIED, awaiting confirmation (2026-07-22) | `build_simfly.py` + `build_razebattle_tower.py` | `AoWEPACK.dpl` |
| City loot gold multiplier (9×→10×) | 🔨 APPLIED, UNTESTED (2026-07-12) | `build_loot_multiplier.py` | `AoWEPACK.dpl` |
| Replay assertion on an enchanted off-map (never-activated) unit | 🔨 APPLIED, UNTESTED (2026-07-30) | `build_enchant_assert.py` | `AoWEPACK.dpl` |
| Arena: persistent state, real battle, flat gold/XP/item rewards (Stages 1–3) | ✅ CONFIRMED WORKING (2026-07-31) | `build_arena.py` | `AoWEPACK.dpl` |
| Arena: three selectable categories + box art (Stage 4a/4b) | 🔨 APPLIED, UNTESTED (2026-07-31) | `build_arena.py` | `AoWEPACK.dpl` |
| Arena: empty-state map sprite + notice (part of G1/G2) | 🔨 APPLIED, UNTESTED (2026-07-31) | `build_arena.py` | `AoWEPACK.dpl` |
| Arena: dialog re-layout, three category rows | 🔨 APPLIED, UNTESTED (2026-08-02) | `build_arenadlg.py` | `AoWz.exe` + `AoWzCompat.exe` |
| Arena: tactical combat | SPECULATIVE — hardening contract designed (§5.5), nothing built | — | — |
| Shipyard water income (1 gold / 5 hexes, divided per water body) | ✅ CONFIRMED WORKING (2026-08-26) · 🔨 v2 MAX_LEVELS=4 re-tune APPLIED, UNTESTED (2026-09-06) | `build_shipyard_income.py` | `AoWEPACK.dpl` |
| Shipyard income display (map panel gate + Realm-window row) | ✅ CONFIRMED WORKING (2026-08-26) | `build_shipyard_income_display.py` | `AoWz.exe` + `AoWzCompat.exe` |
| Terror — one cast per combat, per side | 🔨 APPLIED, UNTESTED (2026-08-31, v2 per-side) | `build_terror_oncepercombat.py` | `AoWEPACK.dpl` |
| AI combat-spell anti-spam — Turn Undead / Terror / Slow / Ooze | reference only — a third party's confirmed build; no build script here, nothing applied | — | — |
| Combat create/destroy + raze diagnostic file logger | diagnostic tool, additive; current live/removed state not re-verified for this merge | `build_combatdiag.py` | `AoWEPACK.dpl` |
| Combat log vs. wall crash (`+0x4C` read off a `TCombatWall`) | ✅ CONFIRMED WORKING (2026-07-22) — owned by `build_combatlog_dll.py` (`07-ui.md`); recorded here as the raze investigation's own find | — (`07-ui.md`) | `AoWEPACK.dpl` |
| "Blt Error" on wall hits (`+0x4C` read, second independent copy) | ✅ CONFIRMED FIXED (2026-07-22) — owned by `build_replaylog.py` (`07-ui.md`) | — (`07-ui.md`) | `AoWEPACK.dpl` |

---

## 1. AI item acquisition: why it didn't work, and what was built

### 1.1 The verdict that started this (2026-07-21): no code let an AI hero acquire an item

Static analysis established flatly: **no code allowed an AI hero to pick up an item, loot a site, or
re-equip anything it dropped.** An AI hero's equipment was exactly what the scenario author gave it,
minus whatever it permanently lost on death — static and monotonically decreasing. Two independent
doors blocked it, either fatal alone:

| # | door | why the AI couldn't pass |
|---|---|---|
| 1 | `TExplorationSite.Search @0x557C1E5C` (VMT `+0x200`) | the AI never initiated a site search, so loot was never even generated |
| 2 | `THero.PlaceItem @0x55788E94` | the sole producer of the "place item" token — the only route an item took *into* a live hero |

The asymmetry was the whole story: items *left* a hero engine-side (`THero.Killed` →
`ExecutePlaceItem(hero, id, 0xE)` on all 14 slots, unconditionally, no token — which is also why a
hero's death-drop works fine for an AI hero), but could only *enter* one through `AoW.exe`'s
`TUnitWindow` drag-and-drop UI. Both doors have since been opened — `build_ai_sitesearch.py` (§1.4)
and `build_ai_itemloot.py` (§1.5) — but the reachability proof from 2026-07-21 is worth keeping
because every later cave's shape traces back to it.

**Door 2 in detail — item acquisition was UI-only.** The wire path from a human's drag-drop to the
engine:

```
AoW.exe TUnitWindow drag/drop                              [UI — human only]
  └─► THero.PlaceItem@0x55788E94         ← ZERO code callers in the DLL (VMT slot 0x5590C960 only)
        ├─ THero.CanPlaceItem@0x55788D08
        ├─ TPlayer.GetBusy@0x557516D0                        (gate — see the token-pipeline §2.4)
        └─ THero.CreateHeroUpdateTE@0x55788C60
              └─► [network → all peers]
                    └─► THeroUpdateTE.Execute@0x55789CDC [engine-side]
                          cmd 0 → THero.ExecutePlaceItem@0x5578907C
                          cmd 1 → THero.ExecuteSwapItem@0x55788F10
                          cmd 2 → THero.ExecuteStartCasting@0x55789130
                          cmd 3 → THero.ExecuteCancelCasting@0x5578932C
```

`CreateHeroUpdateTE` is minted from exactly those four UI entry points and nowhere else — nothing
engine-side ever minted an item token. Slot encoding for `ExecutePlaceItem`'s position argument:
**0–5** equip (`THeroItems.PlaceItem@0x55786788`) · **6–13** backpack
(`TItem.SetArrayOwner@0x55794274`, slot−6) · **14 (`0xE`)** drop to ground
(`map→vmt+0x108 = DropHeroItem@0x55773770`). `AoW.exe`'s hero item screen (`TUnitWindow`, VMT
`0x0040710C`) dispatches by direct named import, not VMT — only `AoW.exe`/`AoWCompat.exe` import
`PlaceItem`/`SwapItem`/`UseItem`/`CanUseItem`/`GetItemsOnGround` at all, and every handler re-checks
`TPlayer.GetBusy` and turn ownership before emitting.

**Door 1 in detail — the AI already visits every exploration site; only the action was a stub.**
`TStructureAIPA.Process@0x557625F4` is the AI's per-structure hook, and its worklist
(`TStructureAIPA.Activate@0x55762594`) is **unfiltered — every structure on the map**, including
every exploration site, for every AI player, every AI turn. So `ExecuteAI` (VMT `+0x1C0`) was already
being *called* on sites; it just did nothing:

```c
undefined4 TStructure_ExecuteAI(void) { return 0; }   // 0x5575E698 — a bare stub
```

Ownership of what to do with that call is the implementor's job — `TAltar.ExecuteAI@0x557CF2B0` is
the one real vanilla implementation (storm-casting) and does its own `structure+0x30 == playerIdx`
check rather than relying on any pre-filtering. **This looked like a small hook, not a fight with
gating**, and that's exactly how `build_ai_sitesearch.py` (§1.4) built it two months later.

Two structural facts closed off the tempting shortcuts:

- `TStructure.UpdateAITarget@0x5575E69C` (VMT `+0x1C4`) — the slot that would make a site an AI
  *movement* target via the `0x1200` broadcast — is a **bare empty procedure**, inherited by every
  exploration-site class, so a site's priority record never gets written and `GetAITarget` returns
  false. None of the 13 real `UpdateAITarget` implementors (City, Farm, Mine, Gems, ManaCrystals,
  PowerNode, ProductionPlace, Shipyard, Tower, WizardsTower, PlayerStructure, Army) is an exploration
  site.
- `TItemHS` (the ground-item hot-spot) can never answer that broadcast either: it inherits
  `THexagonSprite`'s `MapFieldMsgProc` (VMT `+0xCC`, ignores `0x1200`), and its own message surface is
  exactly one message (`0x20020001`, map-init → `GenerateItems`). The only references to its classref
  anywhere in the module are `TItem.PlaceOnMap` (creates it), engine registration, and
  `MapCtrl.TAoWMapControl.SelectHS`/`DeselectHS` — **human mouse selection**. Pickup was *literally*
  mouse-only.

### 1.2 The engine substrate every cave here rests on

Four low-level facts about how AoW1's engine collections and its token pipeline actually behave,
discovered while designing the pickup patch. They are reusable by any feature that walks an engine
list or mints a token, not just item pickup — they are filed here only because this is where they
were derived.

⚠ **Address ambiguity.** `Network.dpl` (preferred base `0x55800000`) is entirely contained inside
`AoWEPACK.dpl`'s CODE range (`0x55701000`–`0x558E7918`), so a bare `0x558xxxxx` address is
ambiguous between the two modules — e.g. `0x55810000` is both a genuine AoWEPACK cave-space anchor
*and* the start of Network.dpl's `.reloc` section. Both modules rebase at runtime so this never
matters in play, but every address in this range needs its module named when read or written up.
`Enginep.dpl` (`0x555xxxxx`) does not overlap either module.

**Collection layout — the element count is NOT at `list+8`.** `TItemList` and every
`TEChangeNotifyNode` descendant holds a pointer to a plain VCL `TList` at `+8`; the count is one
further indirection down, at `[[list+8]+8]`:

```
node + 8                → TList*
[node + 8] + 4          → element array   (TList.FList — TItem**)
[node + 8] + 8          → element count   (TList.FCount)
```

`Engine.TEChangeNotifyNode.GetCount@0x5551A2F4` is exactly that double dereference, dispatched
**virtually at VMT `+0x54`**. Reading `node+8` directly as a count looks plausible (a small
integer-sized slot at a typical count offset) and instead yields a huge garbage value that walks a
cave off the end of the heap. `TItemList.GetItem@0x55794A2C` is bounds-checked in both directions and
returns 0 past the end — **the safe idiom is `for i = 0,1,2… : GetItem(list, i)` until it returns
0**, no count read, no layout assumption, and it self-corrects if the list mutates under you. This is
what every list-walking cave in this section does.

**List removal has two modes, selected by `GetControlStyle() & 8`.**
`Engine.TEChangeNotifyNode.RemoveChild@0x5551A554` branches on a virtual style byte
(`Engine.TEObject.GetControlStyle` returns `0x01` at the base):

| style bit 8 | behaviour | effect on indices |
|---|---|---|
| clear | compacting `TList.Remove` | later elements shift down; count decreases |
| set | slot nulled in place | indices stable; count unchanged; **holes** |

The ground `TItemList` (an item hot-spot's list) has style `0x01` — **compacting**. `THeroItems`
(equip array) and `THeroInventory` (backpack) both OR in `0x08` (bytes at `0x55786338` /
`0x55786058`) → style `0x09` — **sparse, fixed-size, NIL holes**. The two behave *oppositely*, and a
cave touching both must not carry an assumption across: iterating the hero equip array by index 0..5
is correct and a NIL is expected, never end-of-list; iterating the ground list while removing from it
is the classic compaction bug (taking item *i* shifts everything after it down one, so a naive `i++`
skips the next item) — every pickup cave here dodges it by **refetching the list and restarting the
scan after every successful pickup**.

**Hero equip slot tables are asymmetric, and one accessor has no bounds check.** Two adjacent
6-and-7-byte DATA tables at `0x558E8DB0`/`0x558E8DB8`:

```
0x558E8DB0  02 00 03 04 01 04                position -> type   (6 entries)
0x558E8DB8  01 04 00 02 03 0F 0F              type -> position   (7 entries; the 7th 0F is real data)
```

Position→type shows `04` at **both** position 3 and position 5 — item type 4 (rings) owns two slots
— but the forward (type→position) table can only ever answer **3**, so **slot 5 is unreachable
through `THeroItems.GetItemTypePosition@0x55786740`**, which is additionally a four-instruction
function with **no bounds check at all** on its `type` input (reads up to 249 bytes past the table
for `type ≥ 7`, and the instruction encoding is an absolute memory operand, so it cannot even be
copied verbatim into a position-independent cave). `THeroItems.CanPlaceItem@0x5578674C` is the
correct predicate instead: it checks `position < 6`, the slot is empty, and maps *position → type* to
compare — a scan of positions 0..5 through `CanPlaceItem` reaches slot 5 correctly, which is exactly
why every equip-scanning cave here scans positions rather than looking a position up from an item's
type.

**The ground-item list is live, self-freeing, and the pointer dies the instant the list empties.**
`THero.GetItemsOnGround@0x55788C7C` returns the hot-spot's *own* `TItemList`, or `0` on the (nearly
universal) case of no item hot-spot on that hex — the caller must never free it, and must never hold
it across a removal. `TItemHS.ItemsChanged@0x55795D10` calls `[VMT−4]` (`Destroy`) on the hot-spot —
**freeing the `TItemHS` and its `TItemList`** — the moment the list's count reaches 0 (unconditional
enough that a cave should treat "may free" as certain rather than lean on the exact guard condition).
**Taking the last item on a hex frees the list you are iterating.** Only item **IDs** (plain
integers) may ever cross a mutation boundary — never the list or item pointers. Every pickup cave
here refetches the list per slot and breaks to the next slot on success.

**Token dispatch is asynchronous, and `GetBusy` rate-limits it to one call per pass.**
`TTokenControl.AddEvent@0x55803868` **[Network.dpl]** only validates and enqueues — nothing happens
until `TTokenExecuter.Process@0x55803FD0` drains the queue on a later pass. `TPlayer.GetBusy
@0x557516D0` **[AoWEPACK.dpl]** delegates to `TTokenManager` vmt `+0x14` at `0x55804310`
**[Network.dpl]**, a *ready* predicate (**1 = can accept, 0 = cannot**) that `GetBusy` negates — do
not copy that routine into a cave as if it returned "busy". It reports busy whenever **any** event is
already queued for the player, or the executer is mid-drain (`executer+0x24` bit `0x02`, held for the
*entire* drain loop). Two consequences follow directly:

1. Calling `THero.PlaceItem` from *inside* token execution is **silently refused** — no error, no
   effect — because `PlaceItem` re-checks `GetBusy` and the drain-loop flag is set for the whole pass.
2. Even *outside* execution, only the **first** `PlaceItem` call per pass succeeds; the queued event
   makes every subsequent call in the same pass report busy.

So an engine-side hook that mints an item token cannot equip a hero's worth of items in one pass
regardless of where it sits in the call graph — this is the mechanical reason every AI item cave in
this section calls `THero.ExecutePlaceItem` **directly**, never through the token API. That is not a
convenience shortcut; the token route provably cannot work from an engine-side hook.

⚠ **Never mint a token from an engine-side hook.** Both the pickup and loot hooks below run on
*every* MP peer already (broadcast-reached, no locality gate), and `ExecutePlaceItem` is
side-effect-clean (no RNG, log, sound, dialog or token) — that is what makes calling it directly both
correct and MP-safe. Minting a token from the same site would have every peer independently mint one,
multiplying the effect by the peer count or throwing on the non-authoritative peers.

### 1.3 `build_ai_itempickup.py` — ✅ CONFIRMED WORKING (2026-07-21); superseded, kept inert

The first attempt, deliberately narrow: an AI-owned hero **standing on** a hex with a ground item
takes it into an **empty** equip slot of the matching type only — no backpack fallback (an AI can
never re-equip, so a stashed item would be dead weight), no upgrade-swap. It did **not** address §1.1
door 1 — the AI still never searched sites, so this only ever mattered for hero-drop loot.

Two hooks, one shared worker, caves originally at `0x55810000`:

| piece | VA | role |
|---|---|---|
| `cave_pickup` | `0x55810000` (183 B) | shared worker, `EAX = THero*` |
| `cave_nt` | `0x55810100` (24 B) | hook A wrapper |
| `cave_moved` | `0x55810140` (46 B) | hook B wrapper |
| hook A | `0x55787FD7` | `E8 70 8D FF FF` → `call cave_nt`; cave replays the displaced `TAbstractUnit.NewTurn@0x55780D4C` |
| hook B | `0x5578051B` | `5F 5E 5B 59 5D` → `jmp cave_moved`; cave replays the popped registers + the untouched `ret 4` |

Worker: slots are the **outer** loop, the ground list is refetched per slot —

```
gate: map+0x11C == 0 (strategic only) · GetPlayers(map+0x140, hero+0x24) non-null ·
      player+0xA7 != 0 (AI) · hero+0x70 (THeroItems) non-null
for p in 0..5:
    list = THero.GetItemsOnGround(hero)              # NULL on a hex with no hot-spot -> bail
    for i in 0..: item = TItemList.GetItem(list,i)    # bounds-checked, 0 past end
        if THeroItems.CanPlaceItem(hero+0x70, item, p):
            THero.ExecutePlaceItem(hero, [item+0x14], p); break   # list may now be FREED
```

**Confirmed 2026-07-21**: two AI heroes trapped on one hex, one holding an item killed — the survivor
picked the item up. Hero-death drops were confirmed to land on the **strategic** hex from both
tactical and strategic deaths (an earlier, tempting misreading of `ExecutePlaceItem`'s drop branch —
"a tactical death drops onto the combat map and the loot is lost" — is **wrong**, disproved in-game;
`TCombatUnit.KillUnit@0x557256E4` is a one-liner that calls the *strategic* hero's `Killed`, so
tactical deaths genuinely run the strategic drop path).

**Superseded 2026-09-03 by `build_ai_itemloot.py` (§1.5).** `build_ai_itempickup.py` never shipped
with a surgical `--undo` (there was never an `AoWEPACK.dpl.pre-aipickup` on disk either) — one was
added to it on 2026-09-03 purely so the handover to `build_ai_itemloot.py` could be done cleanly, and
it was then run: **`--undo`'d 2026-09-02, and must stay inert.** `build_ai_itemloot.py` refuses to
apply while the old script still owns hook sites `0x55787FD7`/`0x5578051B` (it decodes the `E8`/`E9`
at each site and checks whether the target falls in `0x55810000..0x55810180`), so the two scripts
cannot silently double-own a hook.

### 1.4 `build_ai_sitesearch.py` — 🔨 APPLIED, UNTESTED (2026-09-03): AI searches exploration sites

Closes door 1 from §1.1. Two VMT overrides on seven exploration-site classes:

| VMT slot | vanilla | now | why |
|---|---|---|---|
| `+0x1C0` `ExecuteAI` | `0x5575E698` stub | `cave_execai @0x55834000` | mints the search token event |
| `+0x0CC` `MapFieldMsgProc` | `0x5575F730` `TStructure.MapFieldMsgProc` | `cave_msgproc @0x55834400` | answers the `0x1200` AI-target broadcast with a priority |
| `+0x1C4` `UpdateAITarget` | `0x5575E69C` stub | **left as the stub, deliberately** | see below |

| class | VMT | `+0x1C0` | `+0x0CC` |
|---|---|---|---|
| `TExplorationSite` | `0x557C1440` | `0x557C1600` | `0x557C150C` |
| `TItemExplorationSite` | `0x557C23BC` | `0x557C257C` | `0x557C2488` |
| `TMonsterlair` | `0x557C2D24` | `0x557C2EE4` | `0x557C2DF0` |
| `TDungeon` | `0x557C557C` | `0x557C573C` | `0x557C5648` |
| `TCrypt` | `0x557C64D0` | `0x557C6690` | `0x557C659C` |
| `TRuin` | `0x557C68FC` | `0x557C6ABC` | `0x557C69C8` |
| `TPyramid` | `0x557C6D20` | `0x557C6EE0` | `0x557C6DEC` |

14 slots rewritten, all carrying HIGHLOW `.reloc` entries (the script refuses to write any slot that
lacks one); `pristine_check()` additionally confirms all 21 slots (14 + the 7 left-alone `+0x1C4`)
are vanilla in `AoWEPACK_original_backup.dpl`.

**⚠ Why `MapFieldMsgProc +0xCC` and not `UpdateAITarget +0x1C4`.** The obvious slot is a trap:
`+0x1C4` receives only the query context and the result record — the *asking* `TAIGroupControl* `
(needed for the strength ladder below) lives at `[msg+0x10]`, one level up, and is unreachable from
`+0x1C4`. So the override sits at `+0xCC` instead and chains the inherited `TStructure.MapFieldMsgProc`
first, keeping every other message (`0x1106/0x1124/0x1102/0x1103/0x1131/0x1122/0x1126/0x1127/0x110C`)
working. `pristine_check()` asserts the seven `+0x1C4` stubs stay vanilla.

`cave_execai` (`0x55834000`, 199 B): called with `EAX` = structure, `DL` = AI player index, `ECX` =
pass number (1 or 2, matching the only real vanilla implementor, `TAltar.ExecuteAI`). Gate:
`TExplorationSite.CanSearch@0x557C1E1C` (loot remains **and** this player's army is standing on the
site, via `FindOwnedChild(field, TArmyHS)`); strength gate `3·S_army ≥ 2·S_def` (≥ 1.5×, undefended
always mints); then mints the search TE **verbatim from the engine's own no-dialog branch** of
`TExplorationSite.Search` — `CreateTE`→`SetupTE`→`TE[+0x18]=0` (search)→`TE[+0x20]=1` (auto-resolve)
→submit via the token control→release. **Copying the engine's own token mint is what makes this
MP-safe**: the token serialises through the same stream vanilla uses, and `ExecuteSearch` revalidates
through `CanSearch` on every peer independently.

`cave_msgproc` (`0x55834400`, 250 B): chains the vanilla handler, replicates its terrain-gate exactly,
then a strength ladder gated on `[ctx+2]==0` (normal mode) and `[ctx+0]!=0` (no neutral raiders):

```
S_def = TUnitList.GetStrength(site+0x34, 0)
S_grp = TAIGroupControl.GetStrengthMax([msg+0x10], 1)

    S_def == 0          ->  100   free loot, city-tier draw
    2*S_grp <  3*S_def  ->  nothing at all   (no straggler gathering)
    S_grp   >= 10*S_def ->  100
    S_grp   >=  5*S_def ->   75
    S_grp   >=  3*S_def ->   45
    S_grp   >=  2*S_def ->   30
    else (>= 1.5x)      ->   15
```

⚠ **`[rec+8]`/`[rec+0xC]` are the AI's gold/mana cost fields — never written here**, or the AI's
economics get corrupted through `MakeTargetExpense`. ⚠ **The ladder is a pure ratio, scale-free —
never rescale it for the 5%/doubled-stat conversion.** Both sides read the same engine metric
(`TUnitList.GetStrength`), so Ziggurat's stat doubling moves them together.

Neither cave draws from either RNG generator — the search's own rolls happen later, inside
`ExecuteSearch`, on the engine's existing synchronised stream — confirmed by `rng_audit.py --owners`
showing no site for this feature. Cave zone `0x55834000..0x55835FFF` (8 KB), exclusive, verified
all-zero in both the live DLL and the pristine backup, no `build_scripts/*.py` reference inside
`0x55834000..0x5583FFFF`.

### 1.5 `build_ai_itemloot.py` — 🔨 APPLIED, UNTESTED (2026-09-03): pickup, upgrade-swap, targeting

Supersedes both §1.3 and the reverted §1.6 attempt. Adds upgrade-swap by item value, carrying items
into the backpack, and a group-aware answer to the AI-target broadcast.

| site | vanilla | now |
|---|---|---|
| `0x55787FD7` hook A — `THero.NewTurn`'s `call TAbstractUnit.NewTurn` | `E8 70 8D FF FF` | `E8 A4 05 0B 00` → `cave_nt` |
| `0x5578051B` hook B — `TAbstractUnit.MovedTo` epilogue pops | `5F 5E 5B 59 5D` | `E9 A0 80 0B 00` → `cave_moved` |
| `0x55710244` — `TItemHS` VMT `+0xCC` (VMT base `0x55710178`, HIGHLOW reloc) | `0x55701D4C` (inherited thunk) | `0x55838400` `cave_target` |

Cave zone `0x55838000..0x5583C000` (16 KB), exclusive, verified all-zero and reloc-free in both live
and pristine.

| cave | VA | size / budget | role |
|---|---|---|---|
| `cave_value` | `0x55838000` | 242 / 256 | `value(item)`: EAX = `TItem*` → EAX = worth |
| `cave_wouldtake` | `0x55838100` | 196 / 256 | would this hero take it? EAX=hero, EDX=item, ECX=value → AL |
| `cave_pickup` | `0x55838200` | 472 / 512 | pickup / upgrade-swap worker; EAX = `THero*` |
| `cave_target` | `0x55838400` | 329 / 384 | `TItemHS.MapFieldMsgProc`; EAX=self, EDX=msg |
| `cave_nt` | `0x55838580` | 24 / 64 | hook A wrapper |
| `cave_moved` | `0x558385C0` | 46 / 64 | hook B wrapper |

**The value metric** — `5·ATK + 10·DEF + 10·DAM + 5·RES + Σ ExpandCost` over the item's granted
abilities. Stat bytes `[item+0x46..0x49]` (ATK/DEF/DAM/RES), re-derived on *this* install rather than
assumed: the live DLL hooks `THeroItems.GetAttack/GetDefense/GetDamage/GetResistance` out to caves
that sum exactly those four (signed) bytes (`build_useitems.py`). `TItem` is an ability **owner**, not
a list — `[item+8]` is a bitset pointer, `[item+0xC]` its bit capacity (`TCustomAbilityList.GetAbSet
@0x5574E0E0`); each set bit indexes the global ability registry and its cost is the virtual
`ExpandCost` (VMT `+0xC8`, the same number the hero level-up dialog shows). ⚠ `ExpandCost` never
writes `EDX`, so a garbage `EDX` flows into `GetInherentLevel` and chases an ability-owner vtable off
a wild pointer — the cave explicitly zeroes `EDX` (a nil unit correctly returns level 0 → the level-1
cost).

**Pickup / upgrade-swap** — runs for AI heroes on the strategic map, gated on `map+0x11C==0`
(strategic only), owner `player+0xA7 != 0` (AI, left to the UI otherwise), hero placed and holding a
`THeroItems`. Pass 1 fills a free backpack slot (6..13); pass 2 scans equip slots 0..5 through
`THeroItems.GetPositionItemType@0x55786734` and replaces a worn item only with a **strictly better**
one of the same type (equal value → no switch, so the AI can't thrash between equivalents; empty slot
→ any matching item). ⭐ **Why drop-before-place works at all**: `ExecutePlaceItem` re-validates
through `THero.CanPlaceItem`, which on the strategic map requires the item and the hero to report the
*same hex* — and the base `TItemList.GetLocation` just writes the "nowhere" sentinel, which would
make every drop a silent no-op. It works only because `THeroItems`/`THeroInventory` **override**
`GetLocation` to forward to the owning hero's own location. **If a future change ever re-points
either `+0x90` slot, the swap stops working silently** — no error, the item simply never leaves the
slot.

**Targeting — `cave_target`, and why it is not the 2026-07 patch (§1.6).** Answers `0x1200` only if
some hero or leader in the *asking group* would actually take the item, using the same
`cave_wouldtake` predicate the pickup worker applies — both live in one script deliberately, so a
cross-script call into another script's cave never couples the two `--undo` paths. The group is
walked from the message (`[msg+0x10]` is the `TAIGroupControl`, `[gc+0xC]` its `TAIGroup`, which *is*
a `TUnitList`), candidates filtered by `@IsClass(unit, THero)` (admits `TLeader`, rejects `TUnit`):

```
priority = 10 + min(bestQualifyingValue / 2, 65)   ->  10..75, max-combined into [rec+0]
```

Calibrated against the **live** item library `User/Zig.ail` (325 records, not vanilla `ITEMS.PFS`):
median value 19, p75 32, p90 48, max 114. Divisor 2 leaves ~1.5× headroom before the 65-point cap
bites (the measured distribution *understates* the true metric, since 231 of the ability references
on items have no `Ability.pfs` tag-6 cost) — divisor 1 was rejected because it would have put a third
of the library above the enemy-army priority line and had loot outbid combat.

**MP safety** — both pickup hooks run on every peer already (broadcast-reached), and
`ExecutePlaceItem` is side-effect-clean, so results are identical everywhere; the targeting cave only
writes an AI query result, no state. No cave in this script draws from either RNG generator
(`selfcheck()` asserts it; `rng_audit.py --owners` confirms).

⭐ **A real defect this script's own self-checks caught before it shipped**: the first draft
hand-counted `cave_value`'s PIC anchor **0x4C short**, pointing the `TAbility` classref and the
`AoWHSSet` global at the wrong addresses. It assembled, verified and installed clean — and would have
silently read the wrong memory forever. `selfcheck()` now resolves every anchor-relative reference
back to its VA and asserts it lands on a global the feature actually uses, and `with_anchor()`
assembles each cave twice (once to *measure* where the anchor lands, once with the true value).
**Never hand-count an anchor offset.**

### 1.6 `build_ai_itemtarget.py` — 🛑 REVERTED (2026-07-22): the first targeting attempt

**What it did:** repointed `TItemHS` VMT `+0xCC` to a 174-byte cave that answered `0x1200` with a
flat `priority = 10 + min(maxObtainValue/10, 20)` (10–30), ignoring *who was asking*. **Result: the
AI showed no sign of pathing to items** — not diagnosed further at the time.

**Prime suspect, never resolved statically:** `SendMapFieldMsg` lives in `HSEPack.dpl`, which Ghidra
does not have, so it was never proven that message `0x1200` reaches a `TSingleHS` hot-spot at all —
the supporting evidence was analogy to `TArmyHS`, which receives it at the same slot and demonstrably
works, and that analogy might simply not hold (an army may be registered with the map field
differently than a passive item hot-spot).

**The real defect, found later:** even with delivery working, a *group-blind* priority attracts
stacks that cannot use the loot — a group with no hero, or whose heroes are all better equipped,
walks to an item it will never take and then loiters beside it. `cave_target` (§1.5) is the fix:
gate the answer on "would the asker actually consume this?", never on the target's intrinsic worth
alone.

Revert was **surgical**, not a backup restore, and the reason recorded is worth generalising: the
script's header originally said "revert = copy `AoWEPACK.dpl.pre-aiitemtarget` over `AoWEPACK.dpl`" —
correct when written, and it became destructive within about seven hours, once four more features had
been applied on top of that backup. The actual revert restored the VMT slot to the inherited thunk
and zeroed the 256-byte cave zone, verify-before-write, touching no backup layer — confirmed
afterwards that every feature applied since was untouched. **A feature whose footprint is a VMT slot
plus an exclusively-owned cave zone can always be undone surgically; prefer that over any backup
restore, always.**

⚠ **Do not re-derive the `TStructure.MapFieldMsgProc` shortcut for `TItemHS`.** That handler calls
VMT slots (`+0x1C4`, `+0x188`, `+0x184`, `+0x180`, `+0x170`, `+0x16C`) past the end of `TItemHS`'s
68-slot VMT and reads past its 20-byte instance — catastrophic, not merely wrong. `TItemHS`'s real
`MapFieldMsgProc` slot is `+0xCC` (same index as every other `THexagonSprite` descendant), currently
`cave_target`.

---

## 2. Defender roster variation — every site/structure of a type spawned the same garrison

### 2.1 The symptom and the map's persistent RNG

Every exploration site of the same structure type and the same Defenders→Strength setting spawned an
**identical** unit set, in every instance across the map, for a given match — sites set to Strength
**Random** additionally all resolved to the same strength. Different matches produced a different
set, but again uniform within that match.

The map object carries a persistent RNG state field at **`map[+0x230]`**. The correct accessor,
**`AoWE.TAoWHSMap.Random@0x5577827C`** (`EAX`=map, `EDX`=range → `EAX`=value), installs the saved
state as `System.RandSeed`, draws, and **writes the advanced seed back** — that write-back is the
whole point, it is what makes the next caller get a different number. It has two non-default paths
(a map flag `byte[[0x558FA040]+0x3C] & 8` that skips the saved-seed machinery, and an internal check
that can return 0) — both pre-existing behaviour shared by every correct caller, so patches that use
this accessor take on no new risk from them.

### 2.2 Six roster generators, two independent bug patterns

Taking the union of the callers of `TUnitIndexListCollection.GetRndCollection@0x557835B4`,
`FillWithRandomUnits@0x5575B160` and `PlaceRandomUnits@0x5575AEF8` gives **six** roster generators
(xref-verified in Ghidra). An earlier pass that counted only `GetRndCollection`'s direct callers
undercounted at four — the two `TCity` generators reach the fill/place helpers without going through
`GetRndCollection` — so always union all three helpers' xrefs when re-auditing this family.

| function | VA | seeding | verdict |
|---|---|---|---|
| `AoWE.TStructure.GenerateRazeDefenders` | `0x5575FD1C` | `X + map[0x22C] + Y` | **position-frozen** — fixed by `build_razeroster_vary.py` |
| `City.TCity.GenerateRebelUnits` | `0x557ABCAC` | `X·10 + map[0x22C] + Y` (+ `map[0x174]` in the live build) | position-frozen in vanilla — **already fixed** by `build_razebattle_tower.py`'s `cave_cityseed` (§4) |
| `City.TCity.GenerateDefenders` | `0x557AB6DC` | `TAoWHSMap.Random(map, 0xFFFFF)` | correct |
| `PrdPlace.TProductionPlace.GenerateDefenders` | `0x557BF1A8` | `TAoWHSMap.Random(map, 0xFFFFF)` | correct |
| `ExploreS.TExplorationSite.GenerateDefenders` | `0x557C1FC0` | `RandSeed = map[0x230]`, never advanced | **fixed** by `build_sitedefender_vary.py` |
| `Dungeon.TDungeon.GeneratePrisoners` | `0x557C5C2C` | `RandSeed = map[0x230]`, never advanced | **fixed** by `build_sitedefender_vary.py` |

Two distinct defects, not one: `GenerateRazeDefenders`/vanilla `GenerateRebelUnits` are
**position-frozen** — a pure formula of the structure's coordinates and a per-game constant, with no
persistent-state concept at all, so the fix is to fold in a term that actually changes (the game-day
counter). `TExplorationSite.GenerateDefenders`/`TDungeon.GeneratePrisoners` instead **read the
persistent RNG state and never advance it** — a raw six-byte read-and-install with the write-back
step simply missing:

```
557C1FCB  A1 94 94 8E 55        mov eax,[0x558E9494]     ; -> ptr to map control   [.reloc]
557C1FD0  8B 00                 mov eax,[eax]             ; -> the map object
557C1FD2  8B 80 30 02 00 00     mov eax,[eax+0x230]       ; read persistent RNG state
557C1FD8  8B 15 20 B7 8F 55     mov edx,[0x558FB720]      ; &System.RandSeed         [.reloc]
557C1FDE  89 02                 mov [edx],eax             ; install -- never written back
```

`TDungeon.GeneratePrisoners` is the identical shape with the strength byte at `+0x3C` and the
collection at `[site+8]+0x68`. Field map for `TExplorationSite`: `site[+0x30]` defender strength
(0=none, 1–3 fixed, **4 = the editor's "Random"**), `site[+0x34]` target list, `site[+0x64]` (on the
resource) defender collection; combat strength = `tier × 0x32` (50).

**When it runs:** `ExploreS.TExplorationSite.NewDay@0x557C20A4` is the only caller —
`if (map[0x174]==1 && site[0x30]!=0) GenerateDefenders(self)` — so rosters are rolled **once, on
game day 1**, for every site in turn, each installing the identical constant seed.

### 2.3 The corrected fact: rosters are produced on day 1, not by `ExecuteSearch`

An earlier note in this corpus read: *"site defenders are spawned by `ExecuteSearch` from stored
data."* That is imprecise in a way that matters: **the roster is produced here, on day 1, once, for
the whole game.** `ExecuteSearch` (§4) only ever *spawns what already exists* — it resolves combat
against a roster that was fixed 200+ turns earlier, it does not generate one at search time. Item
*loot* is a separate system and is unaffected by any of this: `TExplorationSite.Generate@0x557C2944`
seeds correctly via `TAoWHSMap.Random`, so treasure already varied per site before this fix touched
anything.

### 2.4 `build_sitedefender_vary.py` — 🔨 APPLIED, UNTESTED (2026-07-29)

Does what the correct siblings already do: take the seed from `TAoWHSMap.Random`, which advances the
shared state.

**Mode `vary` (applied, default).** Hooks the 6-byte `mov eax,[eax+0x230]` — at that point `EAX`
already holds the map object, loaded by the two preceding instructions, which are **left in place**
(they carry the `.reloc` entries the following `mov edx,[&RandSeed]` needs):

| hook VA | orig | cave |
|---|---|---|
| `0x557C1FD2` | `8b 80 30 02 00 00` | `0x55812400` (15 B) |
| `0x557C5C3A` | `8b 80 30 02 00 00` | `0x55812440` (15 B) |

```
mov edx, 0xFFFFFF
call 0x5577827C          ; TAoWHSMap.Random -> fresh value, advances map[0x230]
jmp  <resume>             ; into the existing "mov edx,[&RandSeed]; mov [edx],eax"
```

Introduces **no absolute data references at all** — rel32 call + rel32 jmp only, no delta anchor
needed. Cave space measured on the live DLL: one contiguous zero run
`0x55812219..0x558E7918` (874,239 B); `0x55812400` sits well inside it.

⚠ **Side effect: Strength now varies too**, because the tier roll happens *after* the seed install —
this is what the editor's "Random" strength dropdown implies, and it was already broken the same way,
but it does change the strength distribution of any existing map.

**Mode `keep` (implemented, not applied)** hooks *after* the tier roll instead (`0x557C1FF4` /
`0x557C5C5C`), preserving today's strength outcome and varying only the unit set — needs the PIC delta
trick, since the map pointer is not live there. Switch with `--undo` then `--apply --mode keep`.

**Other consequences:** advancing `map[+0x230]` once more per site shifts every later consumer of the
map RNG, so a game started under this patch will not reproduce a vanilla draw sequence — harmless for
a new game, and exactly what the correct sibling generators already do. **MP-safe**: `NewDay` is a
synchronised turn event and every peer makes the same calls in the same order, same as the existing
correct callers; no new desync surface, but every peer needs the patched DLL.

**Test procedure (to promote to CONFIRMED):** start a **new game** (rosters roll on day 1, so an
existing save keeps what it already generated); find two or more sites of the same type and compare
garrisons; check a dungeon's prisoner reward across two dungeons.

**Revert:** `--undo` (surgical, restores the vanilla bytes and zeroes the caves, touches no backup).

### 2.5 `build_razeroster_vary.py` — 🔨 APPLIED, UNTESTED (2026-07-10)

Fixes the position-frozen pattern in `TStructure.GenerateRazeDefenders@0x5575FD1C` (non-city raze
militia): adds the current-day counter (`Map[+0x174]`) to the existing seed formula, so a raze
attempt on a later turn faces a freshly-rolled grouping while a same-turn re-click still sees the
*same* roster (required so the `CanRaze` preview always matches what the fought battle actually
spawns — see §4).

```
RandSeed := MOVSX(GetX) + Map[+0x22C] + Map[+0x174] + MOVSX(GetY)     ; was: without the day term

0x5575FD36  ADD ESI,[EAX+0x22C]     ; per-game seed add  <-- HOOK SITE (6 bytes)
```

Naturally position-independent with **no delta anchor at all**: at the hook site `EAX` already holds
the (runtime-relocated) map pointer, loaded by the preceding instruction; the cave only reads
`[EAX+off]` and writes `ESI`, and both jumps (hook→cave, cave→resume) are same-module rel32.

Scope: `TStructure.GenerateRazeDefenders` is shared by every non-city razeable structure (towers,
mines, farms, …). `TCity.GenerateRazeDefenders` is a **separate** function (`= GenerateRebelUnits +
ret 1`) and is fixed independently by `build_razebattle_tower.py`'s `cave_cityseed` (§4) — the two
patches are twins, not duplicates.

**Cave-sharing note (settles a flagged ambiguity):** this cave lives at `0x5580D600` (17 B), the very
top of the same free-zero window `build_razebattle_tower.py` grows its own caves into from below. The
scripts cooperate rather than collide — see §4.6.3 for the full picture, including
`build_razeeval_timing.py`'s reservation at `0x5580D200`.

**Revert:** no `--undo` flag exists in this script — it only ever applies forward. To undo by hand:
restore the 6 original bytes at `0x5575FD36` (`03 b0 2c 02 00 00`) and zero `0x5580D600..0x5580D610`
(17 B). Do not restore a `.pre-razeroster` snapshot instead — a later feature may have grown into the
same file since.

---

## 3. AI raze decision-making — the vanilla pipeline, and why the mod deranged it without touching AI code

Two facts used throughout this section and the next, decoded once and reused everywhere below:
**`map[+0xA5]` is the seated/local player index**, sole writer
`TAbstractAoWHSMap.SetSeatedPlayer@0x55772A78` (in single-player this is pinned to the local human for
the whole game; distinct from `map[+0xA4]`, the *current-turn* player, written only by
`SetCurrentPlayer@0x55772A80`); **`player[+0xA7]` is a player-*type* enum, not an "is remote" bit** —
`0` = local interactive human, `4` = independent, `1/2/3/6/7` = AI levels (proof:
`TSetupControl.RemoveIndependentPlayers@0x557E0AB4` tests `==4`; player 0 is assigned type 4 at setup
and again on every load).

### 3.1 The vanilla pipeline, top to bottom

Every piece of code the AI uses to decide whether to raze something, in call order. All addresses are
`AoWEPACK.dpl` VAs; slot numbers are VMT offsets.

**Target discovery.** `TAoWMapField.GetAITarget@0x55771D84` fills a descriptor and broadcasts
MapFieldMsg `0x1200`, carrying a scan-type byte that selects which action the finder wants. Structure
`MapFieldMsgProc` (slot `0xCC`) dispatches to the class's `UpdateAITarget` (slot `0x1C4`);
`TPlayerStructure.UpdateAITarget@0x557615B4` (the base for mine/farm/node/altar) answers scan-type 0
only and marks a structure a target if not razed, not owned by the requester, and either unowned or
hostile to the owner — **no raze/capture distinction is emitted here.** The default scan-type
(`TAIGroupTargetFinder.Setup` writes 0) finds both mines and cities alike.

**Target selection.** `TAIGroupTargetSelector.Process@0x5573D2C0` is a state machine (state var
`[+0x18]`, output status `[+0x1C]`). Round 1 runs `TCombatPredictor` per target; if the group can take
it alone, bit `0x02` is set. Round 2 picks the best can-take-alone target: if no
recruit/production/cooperation bit claimed it, bit `0x20` ("raze route") is set and the group is sent
to the target hex (state `0x14`→`0x15`). **State `0x15` runs *after* the group has moved to and taken
the hex**: `IndexOf(target in the enemy-target list) == -1` (the target is gone, because it's been
taken) → **`status = 5`**; still listed (not taken) → status 3. So **status 5 means "the group has
just captured this,"** not "go raze this" — raze is a follow-on decision on what was just captured,
never the reason the group went there. `TAIGroup.SetupTarget@0x55737648` records the mission type (1
capture / 2 raze-route) verbatim from the state machine — no city/non-city check anywhere in this
layer.

**Mission attachment.** Every behaviour AGC's `ProcessStates` state 5 reads `selector[+0x1C]`:
`==5` → attach `TAIGroupRazeControl`. `RazeControl` mode byte `[+0x20]` defaults to `0x01` (force
gate only); **Scorcher** additionally ORs in `0x02` (unconditional hostile-city raze) and lowers its
city factor to 1.5.

**Raze validation.** `TAIGroupRazeControl.Process@0x557D74E4` finds *any* `TStructure` on the
just-taken field and checks **`GetRazeable` (slot `0x154`) FIRST — before either validator, before
`CanRaze`.** `GetRazeable@0x5575EDDC` is `return *(byte*)([self+8]+0x58)` — **a per-template DATA
byte, identical code for every class.** If the just-captured structure isn't flagged razeable in its
template, `Process` does nothing and the structure simply stays captured. Everything downstream of
`GetRazeable` is force/relation and would pass for a strong AI.

**⇒ This is the single force-independent fact that explains "more force never makes vanilla AI raze
mines":** mine/farm/node templates are flagged non-razeable (`[template+0x58]==0`), so the AI
captures them for income and never reaches a raze decision at all, regardless of force. Cities/towers
*are* flagged razeable, so the AI does reach the raze decision for them, where the two validators
below take over. This is data, not a code gate — a template byte, not a function.

**The two validators**, both byte-verified:

- `ValidateRazeStructure@0x557D74B4` (non-city): `round(ownStrength₁₅ × factor) < hostile+neutral
  strength₁₅` — a pure **scorched-earth** test ("I am about to lose this to another player"). Bucket
  math over a 15-hex radius (`RetrieveBattleFieldInfo@0x55778AD4`): own bucket = self-player strength
  only, hostile bucket = hostile+neutral strength; **allied strength counts in neither**, and
  **independents are excluded entirely** — the raze test throws out every player-0 unit from both
  buckets before any relation math, so indie-dense maps never trigger AI razing. `factor` defaults to
  2.0 (own forces must be halved by the hostile tally to fail), which is why a *dominant* vanilla AI
  essentially never trips this test.
- `ValidateRazeCity@0x557D7440` (city): `relation < 2` (hostile) → raze if `mode&0x02` (Scorcher,
  **unconditional**) or `mode&0x01 && round(relation−2) < hostile strength₁₅`. `relation ≥ 2` → never.
  **Scorcher's `0x02` bit is not a lower bar, it is NO bar** — regional dominance is never consulted
  for a Scorcher AI against a hostile-race city.

**`CanRaze@0x5575FB80`** then simulates the razer against the structure's own template raze-militia
via `TCombatPredictor` (§4 covers the predictor itself, including its flying exploit). Vanilla veto:
refuse iff the militia would win (`result==3`, whose superiority is always ≥100); `result==4` (razer
wins) passes with superiority = razer's loss-% < 100 — a *permissive* rule (the origin of the
"one Great Eagle razes a metropolis" exploit vanilla itself shipped with).

### 3.2 The two-gate synthesis — why vanilla players almost never saw a non-city AI raze

Vanilla non-city AI razing is governed by two nearly-disjoint gates working *together*, and neither
alone explains the outcome:

1. **Want-gate** (`ValidateRazeStructure`): fires when the group is locally **outnumbered** — by
   construction it selects weak, desperate groups; a strong group almost never trips it.
2. **Feasibility-gate** (`CanRaze`'s predictor sim): rejects exactly the weak groups the want-gate
   selects, because they lose to the militia.

The intersection — desperate *and* still able to beat ~8 militia — is vanishingly small, which is why
players essentially never saw an AI mine raze even though nothing in the code forbids it outright.
Two engine details sharpen why the intersection is empty in practice, not just in theory:

- **The selector budgets force to the target.** `GetRequiredStrength`/
  `GetRequiredCombatPredictorSuperiority` (selector round 1) size the assigned group against the
  target's *actual defenders*, so the units standing on a just-taken mine are systematically the ones
  least able to also beat its raze-militia.
- **Raze is evaluated post-capture only**, at the group's weakest moment — a battle-worn stack that
  just fought its way onto the hex is exactly the stack least likely to also clear the fresh militia.

### 3.3 The `razeok` re-entry leak (v4→v5) — ✅ CONFIRMED WORKING (2026-07-12)

Building raze-as-real-battle (§4) required `CanRaze` to be re-entered *after* a battle already won,
without re-vetoing it — solved with a BSS flag, `FLAG_RAZEOK` (originally `0x558FA801`, since moved —
see §4.6), set around the post-win call into `ExecuteRaze` and cleared after. An earlier revision of
this feature (**v4**, `cave_forcefail`) used that flag to gate an AI-vs-non-city veto — "AI may only
raze cities" — and the AI was observed to still raze a mine and attempt a raze on a node in a single
turn (2 of ~11 non-city structure captures), despite v4 supposedly making that impossible.

**Root cause: `razeok` leaked across structures, one leak per throw.** Every setter followed the
shape `set=1 → call EXECUTE_RAZE → set=0`, with **no `try`/`finally`**.
`TStructure.ExecuteRaze@0x5575FFC8` does a great deal (re-calls `CanRaze`, destroys the structure,
transfers income, generates and places raze-defenders, fires event-logs) — if *any* of that raised a
Delphi exception, it unwound to the SEH frame `Raze` installs (caught silently, no crash), and the
`mov [razeok],0` immediately after the call **never ran.** `razeok` stuck at 1 across every subsequent
raze *decision* in the session (it is BSS, so it also survives across turns): the very next non-city
`CanRaze` call saw `razeok=1`, bypassed the city-only gate, and passed on forces alone — exactly one
leaked raze per stuck flag, since that structure's own `cave_towerraze` entry-heal then cleared the
flag again for the next one. A short chain of throwing razes produces precisely "1 mine razed + 1
node attempted, rest kept."

**Ruled out, so as not to re-investigate:** the human/AI test (`player+0xA7`) — vanilla `Raze` itself
uses the identical test, so a fault there would be systematic, not sporadic; the `IsClass(TCity)` gate
misfiring — same argument; `simfly` (§4.2) — it can only make the predictor *harsher*, never create a
raze; cross-module code — `aowInt.dpl` has zero raze/AI strings and `AoW.exe` has only the human raze
button, no `CanRaze`/`TAIGroup` at all.

**Fix (v5, confirmed):** replaced the leaky flag read with a **structural re-entry test** — bypass
iff `CanRaze`'s return address (delta-normalised) lies inside `[ExecuteRaze, Raze)`, the only two
legitimate `CanRaze` re-entry call sites (capstone-verified) — a rebase-proof, un-spoofable range
compare that a stuck flag can no longer influence. Paired with a **first-entry heal**: every
non-re-entrant `CanRaze` call clears `razeok` before anything reads it, protecting a later reader
(`cave_skipavenger`, §4.4) from the same class of stuck-flag bug. Two design options were explicitly
rejected: **(A) SEH-safe clear** (wrap the call in a proper finally) — sound, but unused, kept as a
fallback if v5 ever proves insufficient; **(C) one-shot consume** (clear `razeok` immediately after
honouring it) — **rejected, do not retry**: it breaks `cave_skipavenger`, which reads the flag *after*
a second `CanRaze` re-entry inside `PlaceRazeDefenders`.

**User retest passed** (2026-07-12): AI captured mines/nodes with zero raze attempts; city/human
razing unchanged.

### 3.4 The non-city scorched-earth restoration (v6) — 🔨 APPLIED, UNTESTED, first test inconclusive

v4/v5 made AI non-city razing **impossible**, which is stricter than vanilla's letter (vanilla did
theoretically allow a "strong but locally doomed" scorched-earth mine raze — see §3.1 — it just never
manifested in play). Once the leak was understood, the user chose to restore that designed behaviour
with a corrected feasibility gate rather than leave the outright ban in place. `cave_forcefail`'s
non-city AI branch now allows the raze iff **all three** hold:

1. `ValidateRazeStructure` already fired upstream (reaching `CanRaze` at all implies this);
2. the simfly'd predictor says the razer **decisively wins**: result byte `== 4` exactly (not the
   stalemate `2`, which is what sank an earlier revision — see below);
3. the win is **cheap**: `GetSuperiority@0x5572B798 < 50` (for result 4 this is the razer's own
   predicted loss-strength %; a looser strength-proxy test is what sank another earlier revision).

Two prior revisions of this same idea are worth recording so they are not retried: an earlier version
routed predictor stalls (`result==2`) as passing, which is not "decisively wins"; another used a
strength-ratio proxy that let strong-but-doomed groups pass and then actually lose the fight. Neither
survived contact with the corrected understanding above.

**First engineered test (2026-07-12): no raze — inconclusive, three live hypotheses.** Setup: ~48
hostile dragons/astras (far exceeding the AI's total force) near the AI; the AI captured a guarded
mine with a small stack, **all at red HP after the capture battle**. In order of likelihood:

- **(A) one-shot-at-weakest-moment (probably the design working as intended):** the raze question is
  asked exactly once, immediately after capture, with a fresh ≤8-unit militia pitted against a
  *just-fought, HP-depleted* stack — the evaluation moment is systematically the moment of maximum
  damage, which is also part of why vanilla non-city razes never manifested. **Isolating test:**
  repeat with an *undefended* mine (strip its guards) so the stack arrives at full HP — a raze there
  confirms (A); no raze still points at (B) or (C).
- **(B) assignment gap:** raze is only evaluated when the captured structure was the group's assigned
  selector target; an incidental capture en route to another target never attaches `RazeControl` at
  all.
- **(C) want-gate miss:** the hostile stack sat farther than the 15-hex radius from the *mine itself*,
  or was not hostile/neutral relation to the AI (allied strength counts as nothing).

This isolating test was not run in the source material for this merge — it remains the next concrete
step (see Open items).

### 3.5 The accidental fourth gate — raze-evaluation timing bug — 🔨 APPLIED, UNTESTED (2026-07-12)

A gate that has nothing to do with force, relation, or razeability at all: **whether the raze
question gets *asked* in the first place depended on incidental pump timing.**

Selector state `0x15` (§3.1) decides "captured" vs. "still an enemy" by `IndexOf` against the
control's target list — relying on a *validation* pass (`TAIGroupControlTargetList.Validate`) having
already pruned the now-owned structure from that list. But validation only interleaves with the state
pump if `TAIGroupControlPlugin.MainProcess` **broke** between arrival and state `0x15`. **Capture
battles break the pump deterministically** (deferred combat events); **walk-in (undefended) captures
usually resolve within the same pump**, so the list is still stale, `IndexOf` still finds the target,
status stays 3, and **the raze question is never asked at all** — the structure is now owned and can
never be a target again. Net effect: only *fought-for* captures ever got raze-evaluated; walk-in mines
almost never did, except by the stochastic luck of an AI time-slice or turn boundary landing in the
right place. A fourth, wholly accidental gate on top of the three deliberate ones in §3.1–3.2.

**Fix:** hook state `0x15`'s entry to run `TAIGroupControlTargetList.Validate@0x55738208` on the
control's list **before** the `IndexOf`, at `0x5573DC6A` (displacing `mov eax,[esi+0x10]; mov
eax,[eax+0x24]`, 6 bytes, resume `0x5573DC70`). Cave `cave_valfix @0x5580D200` (18 B, naturally
position-independent — same-module rel32 only): replays the displaced load, calls `Validate`, jumps
to resume. Safety: the identical validate-then-`IndexOf` sequence already exists in
`TAIGroupTargetSelector.Validate@0x5573CEC4`, and `IndexOf` only ever compares pointers, never
dereferences a pruned target — double-validation is harmless.

⚠ **Deliberate side effect:** Scorcher AIs now raze *undefended* hostile cities they simply walk into
— vanilla's timing bug had been accidentally skipping this case too, and the fix restores the
design's letter for it along with everything else.

**Revert:** no `--undo` flag in this script — it only ever applies forward. To undo by hand: restore
the 6 bytes at `0x5573DC6A` (`8b 46 10 8b 40 24`) and zero `0x5580D200..0x5580D212` (18 B) — but see
§4.6 first, since `build_razebattle_tower.py` treats this exact range as a reservation for its own
cave growth ceiling.

### 3.6 ⚠⚠ A diagnostic lever shipped live for two months — AI razed friendly and own-race cities

**🔨 APPLIED, UNTESTED (2026-09-11)** — `build_razediag.py --revert` on `Ziggurat/AoWEPACK.dpl`:
one byte, `0x557D7414` `05` → `01`, verify-before-write, staged copy refreshed in lockstep.

**Symptom, found by playtest:** in the first Cult of Storms mission the elven AI razed elven
settlements — cities of its *own race*, which vanilla protects absolutely.

**Cause.** `DAT_557D7414` is the mode-default constant `TAIGroupRazeControl.Reset@0x557D73E0` loads
into every raze-control instance (`mov al,[0x557D7414]` / `mov [ebx+0x20],al`). It read **`05`**
instead of vanilla's `01`. Bit `0x04` is the **unconditional** bit, and it short-circuits both
validators:

| validator | with mode `01` | with mode `05` |
|---|---|---|
| `ValidateRazeCity@0x557D7440` | `relation ≥ 2` → **never raze** | `relation ≥ 2` → `return (mode & 4) != 0` = **always raze** |
| `ValidateRazeStructure@0x557D74B4` | scorched-earth test only | seeds `true` from `mode & 4` — **want-gate gone** |

So race relation stopped protecting anything, for **every** behaviour AGC (Normal, Aggressor,
Defender, Expander, Scorcher all attach `TAIGroupRazeControl` in state 5; only Scorcher ORs in `0x02`).
`TAIGroupRazeControl.Process@0x557D74E4` razes whatever razeable structure sits on the *group's own
hex* and has **no ownership test anywhere in it** — the relation check was the only thing that ever
kept it off a friendly or own city. §3.5's `cave_valfix` makes status 5 fire far more often than
vanilla, so the question was also asked far more often.

**Provenance.** `build_razediag.py`'s `--want-open` lever, the escalation rung of the 2026-07-12 v6
ladder (§3.4). Its own docstring says "the AI will try to raze EVERYTHING it captures (cities
included) — test-map use only". Its two `--gate-open` levers (`0x5580D1D7`, `0x5580D1E4`) read
**STOCK**, so v6's feasibility gate was never disabled — only the want side.

⭐ **This already showed itself once and was mis-attributed.** §4.5.1's opening line — *"an AI razed
one of its own cities"*, 2026-07-21 — is this bug. That session chased the combat-type dialog and the
freeze downstream of it and never asked why the raze happened at all.

⚠⚠ **Reverting the byte does not rescue a save already in progress.** `TCity.ExecuteRaze@0x557AB414`
subtracts **30** from the razed city's race→player relation *value*, and
`StatusValueToStatus@0x5575AC78` bands it `<21 → 0 · 21–40 → 1 · 41–60 → 2 · 61–80 → 3 · ≥81 → 4` off
a 50 baseline. **One** razed elven city puts Elf→that player at 20 = status 0, which is `< 2` — after
which vanilla's own rule keeps that AI razing that race's cities legitimately, forever. Restart the
mission to test the fix.

⚠ Note the arithmetic on the `relation < 2` branch: `ROUND(relation − 2)` is `−2` or `−1`, which is
below any non-negative strength tally, so `mode & 0x01`'s "regional dominance" clause is satisfied
unconditionally there. A hostile-race city is raze-eligible to **any** AI, not just a Scorcher — that
is vanilla, and it is what makes the −30 snowball self-sustaining.

**Why it survived.** Nothing in `Zig notes/` recorded the lever as live: `build_razediag.py` had no
status-ladder row, no entry in this file's status table, and no mention outside its own source. The
only grep hits for "razediag" in the corpus are `build_combatdiag.py`'s **log filename**
(`Save\razediag.log`), which reads like the same tool and is not.

**Also fixed the same day:** the script minted its `.pre-razediag` snapshot on *every* write path
including `--revert`, so reverting would have snapshotted the **patched** DLL under a "pre-" name —
the exact trap closed in three other scripts on 2026-09-10. Now gated on the apply path.

**In-game checklist:**
1. **Start the first Cult of Storms mission fresh** (not a save from the affected session) and play
   past the point where the elven AI took settlements — no elven settlement razed by an elf.
2. Confirm an AI still razes a city of a race that genuinely hates it (Scorcher especially), i.e. the
   revert removed the bug, not the feature.
3. Confirm the v6 non-city scorched-earth path still behaves as §3.4 describes — the `--gate-open`
   levers were untouched, so nothing there should have moved.
4. Check the Race Relations screen on any older save before reusing it: a race sitting at status 0 or
   1 with an AI player is the snowball above and will keep razing regardless of this fix.

---

## 4. The raze combat predictor, and razing/rebellion/looting as real battles

This is the project's largest single piece of analysis and its largest build. §4.1–4.3 are the
predictor exploit and the design reasoning behind why razing ever ran its own combat logic in the
first place; §4.4 is the eleven-stage build that turned razing, rebellion and looting into real
fought battles; §4.5 is the dialog/freeze investigation that build surfaced; §4.6–4.7 are the
cross-feature bookkeeping every future raze/combat change needs. `map[+0xA5]`/`player[+0xA7]` — the
seated-player index and the player-type enum — are decoded once at the start of §3 and used
throughout both sections without redefinition.

### 4.1 The predictor's flying exploit — "the Great Eagle razes a metropolis"

`TStructure.CanRaze@0x5575FB80` (VMT `0x1EC`) builds a `TCombatPredictor`, adds the razer's units as
side 1 (`AddOpponent`) and the template's raze-militia as side 0 (`AddUnit`), runs it, and vetoes iff
`result ∈ {3,4,6}` and `GetSuperiority ≥ 100` — see §3.1 for the vanilla verdict this produces.

`TCombatPredictor` (`Create@0x5572ABA8`, `Execute@0x5572B028`, `FinishCombat@0x5572AF4C`,
`GetSuperiority@0x5572B798`) is an abstract, position-free slugfest: no hexes, no movement, no
morale, **no round cap, and — the load-bearing detail — no retaliation.** Each unit's combat value
(`TAbstractUnit.GetCombatValue@0x5577F9A8`) is `a²÷(d+a)` from `GetDamageValueEx` (VMT `0xDC`);
`SetupRoundTargets` **deletes any target with `CV < 1`** from a unit's round-target list, and a unit
whose round-target list ends up empty **never even enters the active-unit list** — it isn't "beaten,"
it simply isn't in the simulation.

`TStrikeAbility.GetDamageValueEx@0x55766C90` (the slot `GetCombatValue` calls) zeroes both attacker
and defender DV whenever the **defender** has ability id **1 (Flying)** and the **attacker** doesn't
— melee-only vs. a flyer. Consequences: a melee-only militia's `CV` against a flyer is 0, the flyer is
dropped from its target list, and it never enters combat at all; a flyer's own attacks (whether melee
or, more commonly, ranged — `TRangedAttackAbility.GetDamageValueEx@0x5576E7FC` has no flying check
and no retaliation discount at all) proceed against a stack that, to the predictor, isn't fighting
back. The predictor's own sort (`SortRoundTargets`, priority favours targets that can hurt you) makes
the flyer kill the archers first and mop up the harmless melee units last — so the flyer takes damage
only from ranged defenders, grinds everything else down for free, reaches `result = 4` (attacker
wins) with near-zero self-damage, and `CanRaze` passes.

**Verdict on the "Great Eagle" folk theory, precisely:** the mechanism is real (there is a genuine
simulated combat, and the flyer really does win it cost-free), but the framing of "the eagle must
forbear from attacking" is wrong — there is no attacker/defender asymmetry and no withdraw logic; the
eagle attacks with total impunity because retaliation was never modelled at all, only folded into the
melee `CV` formula as a fuzzy discount. A predictor-only tweak never fixes this alone: tightening the
superiority threshold barely touches an eagle whose superiority is already ~0; blocking result-2
draws leaves result-4 (the eagle's actual outcome) untouched; removing the flying gate unconditionally
leaks into every other predictor consumer — `TCombatPredictorUnit.UpdateTargets`/`UpdateWallTargets`
(**all** AI attack planning), `TCombatUnit.GetTargetWallCV` (real tactical combat), and
`GetUnitIndexAIPriority` (AI build priority) all share `GetDamageValueEx`, so AI behaviour would shift
game-wide. The fix that actually works scopes the change to the predictor's three "hypothetical
militia" call sites only — §4.2.

**A second, related bug in the same predictor: "Oppressed" cities with no garrison.**
`TCity.GetCivilStatus@0x557AC14C` runs the identical predictor — side 0 = loyal garrison
(morale ≥ 41), side 1 = `GenerateRebelUnits` ghosts + disloyal garrison — and grants a loyalty bonus
(+25/+50/+75) when the sim returns `result == 3`. When **both sides are empty** (a degenerate roster,
functionally unreachable for standard races — see below), `FinishCombat`'s tie-break yields `result =
3` and `GetSuperiority`'s `0==0` special case returns **999**, which reads as a *maximal* garrison
bonus for a city with **zero troops in it.** Likelihood correction: `FillWithRandomUnits` only gives
up after 50 consecutive invalid draws, and every standard race roster has enough tier-1/2 units that
this path is unreachable in practice (≈6×10⁻⁷ at worst) — it remains real only for a degenerate
editor-authored race with an empty valid roster. The everyday "Oppressed with no garrison" sighting
players actually reported has a mundane, fully-vanilla explanation instead: the internal "loyalty"
score this system computes is really an **unrest** score (higher = worse), and it **also scales with
wall type and upgrade level** (`+WallType×5 + UpgradeLevel×5`, plus ±10 for terrain) — so a developed,
walled city pushes that score up *with no garrison and no sim at all*: fortification and development
literally suppress the populace in vanilla's own design. (⚠ On *this* live build that
wall/upgrade/terrain contribution was already zeroed by an earlier, undocumented city-loyalty mod
predating this project's conventions — so on this build, loyalty is relation base + garrison bonus
only, and the vanilla no-garrison-Oppressed case does not currently apply; the flyer-garrison bug and
the 999-on-empty edge case both still apply here, since they run through the shared predictor.) The
Patch-E idea for the empty-roster edge (grant the loyalty bonus only when `result==3` **and** the
garrison side is genuinely non-empty) was designed but never built — see Open items.

### 4.2 `simfly` — ✅ CONFIRMED WORKING (2026-07-09): fast-combat-equivalent flying economics

Scopes the fix to exactly the three "hypothetical militia" `Execute` call sites, leaving every real
AI/tactical/auto-resolve consumer of the same DV formula byte-identical:

```
TStructure.CanRaze            Execute call @ 0x5575FC8B
TCity.GetCivilStatus          Execute call @ 0x557AC3AB
TCity.ListCivilStatusInfo     Execute call @ 0x557ABFD2
```

Three caves, all rel32/delta-addressed, gated by a single BSS flag byte (originally `0x558FA800`,
moved 2026-07-22 — see §4.6):

- **`cave_exec`** replaces each `CALL TCombatPredictor.Execute`: set the flag, call `Execute`, clear
  the flag, return.
- **`cave_cv`** replaces `CALL TMeleeRound.GetDefenderDV@0x55766CED` inside
  `TStrikeAbility.GetDamageValueEx`: flag clear → tail-jump to the real function unchanged; flag set →
  return 0, so `GetCombatValue`'s formula yields **raw AttackerDV** for melee. Rationale: `a²÷(a+d)`
  *is* vanilla's own fuzzy retaliation discount — once retaliation is charged as real damage (next
  bullet), keeping the discount too would double-count it. **The flying gate itself stays 100%
  vanilla** — melee still cannot target a flyer, exactly as in every real combat engine; only the
  *economics of melee that can already act* change.
- **`cave_retal`** replaces the `ExecuteRound` damage site (`SUB [target+0x4C],dmg; MOV BL,1`, exactly
  5 bytes): replicates those two instructions, then — flag set, attacker has Strike, and this melee
  attack was in fact the attacker's chosen (max-CV) action — recomputes the pair's `TMeleeRound` and
  subtracts the target's `GetDefenderDV` from the **attacker's** HP. Per pair per round this equals
  one real fast-combat exchange: deal `AttackerDV`, eat `DefenderDV` — exactly what
  `fcExecuteCombatCommand` does in real auto-resolve, which **does** execute the defender's strikes
  too (verified: autocombat pays retaliation for every melee attack a flyer makes against ground
  units; the flying-attack gate is identical in both engines, so this closes an *inconsistency*, it
  does not introduce a new asymmetry between the sim and real combat).

**Hard-won lesson from a v1 crash:** the CODE-section cave space is mapped **read+execute only** —
reading data there is fine, **writing is an access violation.** v1 put the flag byte in a CODE cave
and crashed on the very first city click ("Access violation … Write of address …"). Mutable cave state
must live in a writable section — BSS page slack is the answer used throughout this project.

**Confirmed in-game (2026-07-09):** even 4 Great Eagles could not reliably suppress a 3-hex city;
city selection was stable after the BSS-flag fix in §4.6.

### 4.3 Why the raze check runs its own combat logic at all — design archaeology

Worth keeping in full: the raze gate was never designed as raze-specific logic. **It reuses the AI's
general battle-outcome estimator**, and that estimator cannot be the fast-combat engine for
structural reasons that were true in 1999 and mostly still hold today.

`TCombatPredictor.Create`'s verified callers: every `TAIGroupControl` (one predictor instance per AI
army group), `TAIGroupTargetSelector.ValidateTargetRequirements` (AI attack-decision sizing),
`TArmy.GetPartyStatus` (army status estimate), `TCity.GetCivilStatus`/`ListCivilStatusInfo` (civil
unrest = garrison vs. hypothetical rebels), and `TStructure.CanRaze`. The raze gate is simply one more
consumer of a general planning primitive that cities already used for the identical pattern ("real
units vs. a ghost `GenerateRebelUnits` militia") for their civil-status display.

Four reasons the predictor exists *separately* from `TFastCombat`, each load-bearing on its own:

1. **It must be a pure, deterministic function; fast combat is not.** `CanRaze` runs up to three times
   per raze command and must return the identical verdict on every MP client. `TFastCombat` executes
   real `TCombatAction`s — strikes, deaths, XP, logbook entries, animations, flees — and consumes the
   MP-lockstep RNG stream. Using it as a query would need a full deep-copied combat context plus a
   forked RNG; the predictor instead wraps *references* in lightweight proxy objects with their own HP
   counters — zero side effects, zero dice.
2. **It runs on the AI's own CPU budget.** `Execute` ends by billing `rounds×58` to
   `TAIExecuter.UseProcessTime` — it was engineered to run in bulk on 1999 hardware, hence closed-form
   expected damage instead of simulated rounds.
3. **The opposition may not exist yet.** Raze defenders and civil-status rebels are ghost units
   created and freed inside the check; the AI evaluates fights between armies that are not even
   adjacent. Fast combat needs an instantiated battlefield.
4. **The output is a margin, not a verdict.** AI thresholds need "how superior am I" as a scalar plus
   "which units do I need" — an analytic estimate answers both in one pass; a stochastic resolver
   would need Monte Carlo.

**Could raze call real fast combat instead, today?** Mostly yes, with a harness — most of the 1999
reasons above rank differently on modern hardware (CPU budget is irrelevant now; margin-not-verdict
only matters for the AI's own force-sizing, not a human-facing raze verdict; ghost units already
exist). The genuinely remaining obstacle is **context**: `CanRaze`'s first call runs in UI context on
one client only, before any synchronised command exists — firing a real fast combat there would
consume the lockstep RNG on a single client (desync, and `TAoWHSMap.Random` asserts outside
synchronised context — the exact popup this project has hit doing other terrain work) and would emit
real side effects nobody asked for yet. A "headless fast combat" harness (save/restore `RandSeed`,
suppress action/event/XP emission, construct a `TCombat`/`TCombatData` context programmatically) is
all patchable in principle, but the `TCombat`-construction reverse-engineering alone exceeds
everything in §4.2 — which is exactly why §4.2 gets fast-combat *economics* into the existing safe
estimator for ~200 bytes instead of replacing the estimator itself. §4.4 below takes the complementary
path: it doesn't touch the *estimator* at all, it makes the **outcome that follows a raze decision** a
real battle.

### 4.4 Raze, rebellion and loot as real battles — the twelve-stage build

All of this is `build_razebattle_tower.py` (+ `build_loot_multiplier.py`, `build_enchant_assert.py`
for two closely-coupled fixes). One script, no `--undo` flag anywhere in it — see §4.4.11 for what
that means for reverting. It rewrites its own caves in place on every re-run (an `_own_prior` helper
accepts a script-owned region's *current* live bytes as a valid "before" state, gated on the razebattle
VMT hook already pointing at `cave_towerraze` — proof the region is this script's own, not foreign
data), so re-tuning a stage never needs a revert.

#### 4.4.1 The blueprint: exploration sites already do this

`TExplorationSite.ExecuteSearch@0x557C1A20` is the exact shape raze battles transplant: build a
combat via `TAoWHSMap.CreateCombat(map, flag)` (`0x202B0` fast / `0x220110` tactical — the latter goes
**modal**, its slot `0x64` returning `AL==1` and the real result arriving later through the
`combat[+0x2C]` completion callback), `SetupCombat` wires `combat[+0x2C]`=callback,
`combat[+0x30]`=context, `TCombat.AddArmy` (visiting army, side 0) and `TCombat.AddArmyEx` (the
site's *hidden*, never-placed `TDefendersArmy`, side 1, position `(-1,-1,-1)` = no map field), then
`CombatExecuted@0x557C1894` reads the result byte `combat[+0x14]` — **`{3,6}` = attacker (searcher)
won** (3 = defender wiped, 6 = pre-round walkover) — and dispatches the reward. This precedent proved
two things the whole rework rests on: a structure *can* own a hidden, never-activated army that fights
a real combat with a completion callback, and that combat can resolve fast or tactical using the
engine's own machinery with no bespoke combat construction of our own.

#### 4.4.2 Stage 1 — plumbing — ✅ CONFIRMED WORKING (2026-07-10)

Repoints `TTower` VMT slot `0x1B0` (`ExecuteRaze`, base `0x557C31A8`, verified type-3 HIGHLOW reloc so
a cave VA rebases correctly and the repoint is tower-only) to `cave_towerraze @0x5580C910`: build a
hidden `TDefendersArmy` militia via `GenerateRazeDefenders` (VMT `0x1A8`), construct a **fast**
`TCombat`, run it synchronously (`Init/Activate/Execute/Deactivate/Finalize`, wrapped in
`LockExecuted`/`UnlockExecuted` + `LockGameOverEvent`/`UnlockGameOverEvent`), then **always**
re-entered the original `ExecuteRaze@0x5575FFC8` regardless of outcome (gated by the new BSS flag
`razeok` so `CanRaze` would not re-veto the re-entry). Confirmed: a real fast battle ran (the razing
stack took HP damage and gained XP from the militia), the tower razed, no crash — validating the
riskiest part (combat construction + re-entry) with the fewest moving parts. Two known gaps, both
closed in Stage 2: the battle was silent (no combat-log entry) and vanilla's raze-avenger militia
still spawned afterward regardless of outcome.

Two deliberate Stage-1 simplifications that persist through every later stage: the throwaway militia
army is **leaked, not freed** (a never-touched `TArmy` cannot fault; the unverified `TDefendersArmy`
destructor could double-free combat-owned units), and there is **no SEH frame** around the combat
lifecycle (justified as vanilla-equal risk in Stage 2, §4.4.3).

#### 4.4.3 Stages 2 / 2.1 / 2.2 — result gate, avengers removed, combat log, no-force block — 🔨 APPLIED, UNTESTED (2026-07-10)

Four additions in one pass:

- **(A) Result gate.** Latches `combat[+0x14]` after the outer `UnlockExecuted`, before
  `DestroyCombat`; razes only on `{3,6}` (razer won / walkover). ⚠ **This is deliberately NOT the
  predictor's `{3,4,6}+GetSuperiority` test** — `TFastCombat`'s result byte is a *different enum*
  written by `TCombat.UpdateStatus@0x557282E4` (2/3/4/5/9) and `TFastCombat.Execute` (6 = walkover),
  where `4` means the *razer* was wiped — the opposite polarity from the predictor's `4`. Reusing the
  predictor's test here would raze on a loss. This is byte-for-byte vanilla `ExecuteSearchDone`'s own
  `{3,6}` test.
- **(B) Avengers removed.** New hook on the `PlaceRazeDefenders` vcall (slot `0x1AC`,
  `0x557601F0`) → `cave_skipavenger`: when `razeok` is set (our post-battle re-entry) the vanilla
  second-wave avenger spawn is skipped — the militia already fought; when clear, the cave replicates
  the vanilla vcall byte-exact. `SetRazed(1)` already fired earlier in `ExecuteRaze`, so skipping this
  never leaves the tile un-razed.
- **(C) Combat log — `AoWE.DistributeCombatEvent@0x5572928C`** (EAX = `TCombatLogbook` =
  `combat[+0x18]`, DL = show-to-local-human), called in the same window: after the run, before
  `DestroyCombat`. It loops players `1..count-1` and files a `TCombatEventLog` for every player who
  can **see** the combat hex (`TAoWHSMap.VisibleForPlayer@0x557778A4`) **or participated**
  (`TCombatPlayerList.IndexOfPlayer@0x557288B8`), then replays it for the local human when `DL != 0`
  and `map[+0xA5]==player && player[+0xA7]==0 && finaldata[+0x30]!=6`, releasing via slot `0x2C`.
  Vanilla's own fast-combat call site is `TArmyCombatMoveTE.ExecuteCombat+0x2b5@0x55749BD9` —
  `mov eax,[esi+0x18]; mov dl,1; call 5572928c`, gated on `IsClass(combat, TFastCombat)` — so the
  cave is byte-for-byte the vanilla form, `DL=1` included. The `DL` value is the named constant
  `EVENTLOG_SHOW`; `1 → 0` is the one-byte re-tune that keeps filing reports for every witness but
  stops them opening themselves.

  ⚠ **A WALKOVER FILES THE REPORT BUT NEVER AUTO-OPENS IT — this is vanilla, not a bug, and it will
  look like one during testing.** The last term of the replay gate is
  `cmp byte ptr [eax+0x30],6 / je 0x5572937E` at `0x55729367`, which skips the slot-`0x70` Show and
  drops straight to the slot-`0x2C` release. `finaldata[+0x30]` is a **verbatim copy of the result
  byte** the win gate tests — `0x55727F77`: `mov al,[combat+0x14]` / `mov edx,[combat+0x18]` /
  `mov edx,[edx+0x10]` / `mov [edx+0x30],al`. The win gate accepts `{3,6}` and **6 is the walkover**
  (`TFastCombat.Execute`'s pre-round short-circuit: the defending side had zero conquer objects). So a
  rebellion, raze or loot won against an **undefended** target still files an entry for every witness,
  and nobody gets a popup. Ordinary fast army combats are suppressed by the same byte, so this is
  vanilla-equal. **Test the replay against a defended target** — an undefended one proves nothing.

  ⚠ **Stage 12b (2026-09-12) replaced a single-player hand-rolled block with this.** Stage 2 built one
  `TEventLog.Create`→`SetCombatLogbook`→`GetPlayers`→`AddEvent`→show→release chain into the *razing*
  player's logbook only, so a fast rebellion battle filed **no report for anyone else** — including the
  player who had just lost a city to rebels. Raze and loot had the identical gap and are fixed by the
  same four instructions. ⚠ The other `TEventLog.Create@0x557FD398` in `cave_towerraze`, in
  `L3_askdialog`, is the combat-**type** request dialog and must survive; after Stage 12b the cave
  holds exactly one `call 0x5572928c` and zero calls to `0x55728F2C` / `0x557FDB90`.
  **Stage 12d (2026-09-12) closed the tactical half** — see §4.4.3a. Together they cover every
  resolve mode; there is no path left that resolves a raze, rebellion or loot battle silently.
- **(D) SEH — deliberately deferred**, with the reasoning recorded rather than just the decision: since
  (C) introduces no managed string, there is nothing left for a hand-rolled `FS:[0]` frame to protect
  beyond guaranteeing `DestroyCombat`/`UnlockGameOverEvent` on a mid-combat exception — and vanilla's
  *own* `ExecuteSearch` doesn't protect those either (its `try`/`finally` only covers its own AnsiString
  local). So the exposure here is provably **vanilla-equal**, whereas hand-rolling a rebased,
  reloc-free `FS:[0]` frame (the handler pointer must be load-delta-computed, not a raw immediate) was
  judged itself more likely to regress the confirmed-working Stage 1 than to fix anything. **Symptom to
  watch if this is ever revisited:** any later, unrelated battle raising "Combat already created" means
  a throw skipped teardown here and `map[+0x120]` is stuck non-null — reopen (D) then.

Stage 2.1/2.2 refinements: **(req1)** a raze with **no attacker forces present** is now blocked
*before* the confirm dialog, exactly like vanilla — a dedicated `cave_forcefail` hook at the `CanRaze`
result-decode (`0x5575FC90`) checks the predictor's attacker-side (side 1) unit count and, if zero,
routes into `CanRaze`'s own "not enough forces" message path (reworded to **"Your forces aren't
present"**, kept at the original 29-char width so the RT_STRING block doesn't shift). **(req2)** a
**failed** raze battle (`combat[+0x14] ∉ {3,6}`) now flags the structure to the independents
(`TPlayerStructure.SetPlayer(tower, 0)`) instead of leaving it razer-owned and undamaged.

#### 4.4.3a Stage 12d — the TACTICAL (modal) path files a combat report — 🔨 APPLIED, UNTESTED (2026-09-12)

Stage 12b fixed only `cave_towerraze`'s synchronous fast run. A raze resolved in **modal tactical
combat** returns from `cave_towerraze` the moment `Execute` reports `AL=1`, and finishes later through
`cave_razedone`, the `combat[+0x2C]` completion callback — which filed no event log at all, for
anybody. Stage 12d adds the distribution there.

⚠ **Scope: this is the human RAZE path only — rebellion and loot cannot reach it.** Both pack a
combat-type choice of **1 = fast** into the `ExecuteRaze` argument (`cave_rebellion` passes
`owner|0x50`, `cave_lootbattle` `owner|0x90`; bits 4–5 are the choice), and `cave_towerraze` uses the
packed choice in preference to the registry setting (`0x5580CA0F`: `cmp [ebp-0x20],0 / jne
L3_modeset`). So `[ebp-0x20]` is 1 for both and `L3_tactical` is unreachable — which is also why
§4.5.1 could rule them out of the Ask-dialog investigation. The tactical branch is entered only by a
**local human razing a structure or city** with Combat Resolve Mode = *Tactical*, or = *Ask* answered
*manual* (`cave_typechosen` re-issues the TE with choice 2). Stage 12b already covers rebellion and
loot in full.

**The window is the same one, and it is traced rather than assumed.** `TCombat.Initialize` **locks**
at its own `+0x8` (`0x55727C9C` → `TCombat.LockExecuted@0x55728100`, `inc combat[+0x28]`) and
`TCombat.Finalize` **unlocks** at its tail (`0x55728084`). `TCombat.UnlockExecuted@0x55728104`
decrements, and on reaching 0 with a callback installed does
`mov edx,combat / mov eax,[combat+0x30] / call [combat+0x2c]`. The "is a callback installed" test is
`cmp word ptr [combat+0x2e],0` — a **high-half non-nil test on the `[+0x2c]` pointer itself**; there
is no separate field. So:

| path | `combat[+0x28]` | where `cave_razedone` fires |
|---|---|---|
| tactical | Initialize `0→1`, Finalize's tail `1→0` | **inside `Finalize`** |
| fast | `cave_towerraze` `0→1`, Initialize `1→2`, Finalize's tail `2→1`, `cave_towerraze`'s own unlock `1→0` | at `cave_towerraze`'s `UnlockExecuted` |

Either way the callback runs **after** the `SetFinalData` call at `Finalize+0xa0` = `0x55727ED8`
(the function itself is `TCombatLogbook.SetFinalData@0x55728E44`) and after
`finaldata[+0x30] = combat[+0x14]` (`0x55727F83`), and **before** any `DestroyCombat` — so
`combat[+0x18]` and both its `TCombatData` members are populated, which is exactly what
`DistributeCombatEvent` dereferences (`logbook[+0x10]` for the hex, `logbook[+0xc][+0x38]` for the
participant list).

**The edit** sits immediately after the `FLAG_RAZEASYNC` one-shot clear — under the `jz Ldone`
razeasync gate, so the fast path can never reach it, and above the result decode, so it covers
**every** tactical outcome including the 2/5 standoffs that fall straight to `Ldone`:

```
push ecx                        ; the load delta
mov eax,[ecx+0x558E9494] / mov eax,[eax]   ; map, via the delta anchor (PIC)
push eax / call 0x557755F8      ; TAoWHSMap.SynchroniseBegin
mov eax,[esi+0x18]              ; combat[+0x18] = TCombatLogbook
mov dl,0                        ; EVENTLOG_SHOW_MODAL
call 0x5572928C                 ; AoWE.DistributeCombatEvent
pop eax / call 0x55775600       ; TAoWHSMap.SynchroniseEnd
pop ecx
```

⚠⚠ **The `SynchroniseBegin`/`End` pair is load-bearing, not vanilla mimicry — omit it and the modal
path ASSERTS.** `DistributeCombatEvent` files each witness's entry through
`TEventLogbook.AddEvent@0x557FDB90`, whose **first act** is `GetSynchronised(map)@0x55775608` followed
by `System.@Assert` on false (`EventLog.pas:0x2c0`). `GetSynchronised` is true iff **any** of:
`map[+0x234] != 0` (the counter `SynchroniseBegin`/`End` inc/dec — `0x557755F8`/`0x55775600`, one
instruction each), `[[map+0x23C]+4][+0x48] != 0` (a token event is currently executing), or
`map[+0x3C] & 2`. Stage 12b's call site is **inside the raze TE**, so the token-event term already
holds and it needs no wrapper; this callback fires when the **combat screen closes, outside the TE**,
where only the counter can hold. That asymmetry is precisely why vanilla wraps its modal site and not
its fast one, and it is the reason a naive "same four instructions, different cave" transcription of
Stage 12b would have been wrong. (Exposure, recorded rather than fixed: a throw between the two would
leak the counter, leaving `GetSynchronised` permanently true. That *weakens* an assertion rather than
breaking anything, and vanilla's own pair at `0x557498F5`–`0x5574990E` carries no `try`/`finally`
either — **vanilla-equal**, the same standard (D) above is held to.)

⚠ **`DL = 0` here, not `EVENTLOG_SHOW`'s 1 — deliberate, and it is vanilla's own value.** Vanilla's
`combat[+0x2C]` callback for an ordinary army combat is
`TArmyCombatMoveTE.CombatExecuted@0x557496D4`, installed at `0x55749B2C`; its **first** act is
`IsClass(combat, TFastCombat)` with true jumping straight to the epilogue (`0x55749913`), so its tail
runs **only for a non-fast combat** — and that tail is `SynchroniseBegin / xor edx,edx /
mov eax,[ebx+0x18] / call 0x5572928c / SynchroniseEnd` (`0x557498F5`–`0x5574990E`). The tactical raze
is only ever reached by the **local human** (`cave_razemode` forces every AI/remote raze to fast), who
has just watched the battle in person; `DL=1` would auto-replay it at them the instant it ended.
Entries still file for every witness — `DL` controls only the replay. `0 → 1` is the one-byte re-tune
(`EVENTLOG_SHOW_MODAL`).

**No double-filing, established by scan rather than inspection.** A module-wide search of every
`E8`/`E9` rel32 and every absolute dword in every section finds exactly **three** callers of
`0x5572928C` before this change — `0x55749904` (vanilla modal), `0x55749BD9` (vanilla fast) and
`0x5580CBA2` (Stage 12b) — and **no other module imports the symbol**. Vanilla's modal filer cannot
run for our combat at all, because `cave_towerraze` overwrites `combat[+0x2C]` with `cave_razedone`
at setup time.

**Relocation, and two orphans absorbed.** The block took `cave_razedone` from 138 B to 174 B, past the
144 B its old slot had before `cave_rebelchance@0x5580D460`, so the cave **moved
`0x5580D3D0` → `0x5580D500`** (reservation `0x100`, ending exactly on `CAVE_SEED_RESV = 0x5580D600`)
and the vacated slot is **zero-filled by its own patch-table entry**. `cave_lootbattle` took a `0x60`
reservation at the same time. Both reservations swallow dead bytes the Stage-12c sweep never reached
because they sit *above* the caves it was auditing:

| orphan | what it is |
|---|---|
| `0x5580D4E3`–`0x5580D4FA` (23 B) | tail of a pre-Part-C-v2 `cave_lootbattle` (the old body tested the loot-win flag with `cmp byte [ecx+0x558FA80C],0`; the live one uses `movzx` plus a shorter branch). Starts **mid-instruction**, so it could not even be entered |
| `0x5580D550`–`0x5580D586` (55 B) | a complete pre-Stage-10 copy of `cave_rebelchance`, byte-identical to the live one apart from its two tail jumps |

Both were proved dead the same way: zero `E8`/`E9` rel32 and zero absolute-dword references in **any**
section, and zero `.reloc` entries. The script now carries a positive guard for the relocation —
the new home must be zeros, our own applied blob, or *only* that identified `cave_rebelchance` copy;
anything else aborts before writing rather than being silently absorbed.

⚠ `src_towerraze_stage1` was pinned to a new **frozen** constant `CAVE_RAZEDONE_S1 = 0x5580D3D0`. It
exists solely to reproduce the bytes accepted as a Stage-1 prior, so letting it track `CAVE_RAZEDONE`
would silently redefine "what a Stage-1 file looks like" every time the cave moves. (Prior length
unchanged at 483 B across the relocation.)

`rng_audit`: **adds zero draws.** `DistributeCombatEvent` draws nothing and
`Synchronise{Begin,End}` are a single `inc`/`dec dword [map+0x234]` each. ⚠ Being a no-draw change it
is invisible to `rng_audit --owners` by construction — the site count does not move.

**In-game checklist — the user still needs to run this:**

1. Set **Combat Resolve Mode = Tactical**, raze a **defended** tower/mine/node of your own. Fight the
   modal battle through to a result. On exit, the combat report must be **in your event log** and must
   **not** auto-open (that is `DL=0` working, not a failure).
2. Repeat with a **neighbour's unit standing in sight of the hex but not in the fight** — that player
   must get an entry too (this is the whole point of `DistributeCombatEvent` over Stage 2's
   single-player block). Hotseat is the cheapest way to check the second player's log.
3. **Lose** a tactical raze (result 4) and confirm the report still files *and* the loss garrison still
   spawns as a Guard stack with the literal survivors — the report is filed before the garrison, so a
   regression here would show as a missing garrison, not a missing report.
4. Force a **stalemate** (result 2 — flyer vs melee-only walkers). Vanilla's gate files nothing on a
   walkover popup but the entry must still exist; this is the outcome Stage 12b could not reach at
   all.
5. **Combat Resolve Mode = Ask**, pick *manual*, and confirm the same. Then pick *quick* and confirm the
   fast path is unchanged (Stage 12b behaviour, one report per witness, auto-replay on a defended
   target).
6. **A tactical CITY raze** as well as a structure — same cave, but `cave_razedispatch` takes the −30
   relation branch afterwards, so it is the path where the report and the raze most easily fall out of
   step. (Rebellion and loot need no tactical test: they are fast-only by construction, see above.)
7. ⚠ **Watch for a `D:\AoWDev\AoWE\EventLog.pas` assertion dialog** at the moment the combat screen
   closes. That is the `GetSynchronised` assert, and it would mean the Synchronise wrapper is not
   holding — the single most likely failure mode of this stage.
8. Sanity: any battle *anywhere* afterwards raising **"Combat already created"** means a throw skipped
   teardown — see (D) above, not this stage.

#### 4.4.3b Stage 12f — `L3_tactical` passed the COMBAT to `DestroyCombat` — 🔨 APPLIED, UNTESTED (2026-09-12)

A **pre-existing** defect (byte-identical in `backups\AoWEPACK.dpl.pre-panicnomelee`, so it predates
Stage 12), found by QA during the Stage-12d pass and deliberately left for its own pass. The
sub-branch of `L3_tactical` reached when a tactical `Execute` (VMT slot `0x64`) returns `AL != 1` ended:

```
5580CC6A  8b 45 e8   mov eax,[ebp-0x18]     ; the COMBAT
5580CC6D  e8 ...     call 0x557787F8        ; TAoWHSMap.DestroyCombat
```

`DestroyCombat` is `mov esi,eax / cmp dword [esi+0x120],0 / je bail` — **EAX is the map**. `[ebp-0x14]`
is the map throughout the cave and `[ebp-0x18]` is the combat; the fast path three instructions earlier
always had it right (`0x5580CBB5`: `mov eax,[ebp-0x14]`).

⭐ **Vanilla settles the operand.** `TArmyCombatMoveTE.ExecuteCombat` carries the byte-identical
`cmp al,1 / je` at `0x55749BAB`, and its `AL != 1` fall-through does
`mov eax,[0x558fa040] / call 0x557787f8` at `0x55749D09` — the map. Our cave is a transplant of that
function; only this operand diverged.

**The edit is one operand**, `[ebp-0x18]` → `[ebp-0x14]`. Both encode in 3 B (`8b 45 e8` → `8b 45 ec`),
so the cave is size-neutral (1042 B code, `TOWERRAZE_RESV = 1152` unaffected) and both `DestroyCombat`
call sites kept their addresses (`0x5580CBB8` fast, `0x5580CC6D` tactical).

##### The branch is reachable — established before patching

⚠ **The tactical path does not run `TCombat.Execute`.** `CreateCombat(map, 0x220110)` builds a
**`TTacticalCombat`** — `AoWTCPCK.dpl` VMT `0x00413314`, instance size `0x50`, the only `TCombat`
descendant outside `AoWEPACK.dpl` (an 857-VMT scan of `AoWEPACK.dpl` finds just `TCombat` and
`TFastCombat`). Its slot `0x64` is `TTacticalCombat.Execute@0x004295E8`, which sets its return value
to **1 at exactly one instruction, `0x00429992`**, and only after `TAoWCombatMap.NewTurn` — i.e. only
once the modal screen is genuinely up. Three exits precede it, all returning non-1:

| return | condition | reachable for a raze? |
|---|---|---|
| `8` | `ValidateWallCombat@0x429540` false | **No.** It returns `party0[+0x18] == 0`, and the Stage-5 wall fix (`0x5580CB0B`) zeroes exactly that byte, so it is true. Consistent with "8/9 are impossible since the wall fix" |
| `2` | `side1.GetCount() == side1[+0x18]` @`0x00429667` | **yes — the only live exit** |
| `6` | `side1.GetCount() == 0` @`0x004296B9` | **no — dead code**, see below |

`combat[+0x20]` is side 1 (the militia side; `+0x1C` is side 0, per `TCombat.UpdateStatus`), and slot
`0x54` is `Engine.TENode.GetCount` via thunk `0x557031DC`, counting the `side[+8]` object list.

⭐ **`side[+0x18]` is written in exactly one place**, `TCombatSide.UpdateSettings@0x55727038` (reached
only from `TCombat.UpdateSidesSettings@0x55727424`, itself called from `TCombat.NewTurn+0x2c` and
**`TCombat.Activate+0x8d` = `0x557281B1`**). It zeroes `side[+0x14]`/`side[+0x18]`, then walks the same
`side[+8]` list `GetCount()` counts and does `inc dword [side+0x18]` (`0x5572707E`) for each object with
`[[obj+0x14]+8] > 0` **and** `[obj+0x30] == 0`. Both `[obj+0x10]` and `[obj+0x14]` are
`Engine.TQuadItemList`s allocated in `TCombatObject.Create` (`0x5572613F`/`0x5572614E`).
`cave_towerraze` calls `Activate` (slot `0x70`) before `Execute`, so the field **is** populated — exit 2
is a semantic test, not merely an emptiness test.

⚠ **That also makes exit 3 unreachable.** `side[+0x18]` is zeroed and then incremented at most once per
entry of the very list `GetCount()` counts, so `GetCount() == 0` forces `side[+0x18] == 0`, exit 2
matches first and returns **2**. Nothing runs between `Activate` and `Execute` that could remove objects
and leave a stale count. So an empty militia side short-circuits with result **2**, never 6, and
`0x004296BD` (`mov byte [ebp-5],6`) can never execute. `cave_towerraze`'s `Lempty` screens a militia
**army** with zero units, but not a militia **side** that lands zero combat objects out of `Initialize`,
and it does not screen the general `AL=2` case at all.

⚠ **What `[obj+0x14]`/`[obj+0x30]` mean in player-facing terms is NOT yet decoded**, so there is no
known in-game recipe for forcing exit 2 on a non-empty side. ⚠⚠ **A flyer-vs-melee-walkers standoff is
NOT this case** — that is a *fought* stalemate, where `Execute` returned 1, the modal screen opened, and
`TCombat.UpdateStatus` wrote result 2 after rounds elapsed; it finishes through `cave_razedone` at modal
close and never reaches this branch. Same result byte, different point in the lifecycle. All three exits
above fire **before** `TRndTacHsm.RandomMap@0x004296DC` has even generated the tactical map.

**What the old code did.** `TTacticalCombat` is `0x50` B, so `[combat+0x120]` is `0xD0` B **past the
end of the object** — an out-of-bounds heap read. Reads zero ⇒ `DestroyCombat` bails at
`0x55778819`, `map[+0x120]` stays non-null, and every later battle raises "Combat already created"
(the §4.5.2 symptom). Reads non-zero ⇒ it dereferences that garbage as a `TCombat` and calls its VMT
slots `0x74`/`0x6C` — a virtual call through a wild pointer.

##### ⚠ `FLAG_RAZEASYNC` is **not** left set on this path

The Open-items note claimed it was, on the reasoning that the one-shot clear lives only in
`cave_razedone`. `cave_razedone` **does** fire here. `TTacticalCombat.Initialize` chains to
`TCombat.Initialize` at `0x00429094` (which locks at `0x55727C9C`) and `TTacticalCombat.Finalize`
chains to `TCombat.Finalize` at `0x0042952D` (whose tail unlocks at `0x55728084`), so the `Finalize`
call two instructions above the bug takes `combat[+0x28]` `1→0` and fires `combat[+0x2C]` — exactly
the tactical row of §4.4.3a's window table. The flag is cleared, the Stage-12d combat report is filed
and the result gate runs the raze/garrison. **Only the `DestroyCombat` operand was ever wrong; an
extra clear on this path would be dead code.**

`rng_audit`: adds zero draws (`--owners` clean, 24 modded sites, unchanged).
`build_relocfix.py --audit`: **0** — the edit displaces nothing.

**In-game checklist — the user still needs to run this:**

1. **Combat Resolve Mode = Tactical**, raze a defended tower/mine/node. The battle must open modally
   (that is `AL=1`, the path this fix does *not* touch); confirm nothing regressed there first.
2. The fix's own path needs an **instant** tactical resolve — `Execute` returning before the screen
   opens, i.e. side 1 satisfying exit 2. ⚠ **No reliable in-game recipe is known** (see the exit table:
   `[obj+0x14]`/`[obj+0x30]` are undecoded, and the empty-side case is already screened upstream by
   `Lempty`). Do **not** substitute a flyer-vs-walkers standoff — that is a fought stalemate on the
   modal path and exercises nothing here. If the branch is ever hit, the tell is the next battle
   *anywhere* raising "Combat already created"; that symptom disappearing is the only observable this
   fix has. Treating it as a latent-defect fix verified against vanilla's template (`0x55749D09`) is
   the recommended position unless a repro turns up.
3. Repeat 1–2 for a **city** raze (`cave_razedispatch`'s −30 branch).
4. Regression: a tactical raze that goes modal and is fought to a result must still raze/garrison and
   file its report as per §4.4.3a's checklist — the two paths share everything but this operand.

#### 4.4.4 Stage 3 — manual/tactical combat-type choice — 🔨 APPLIED, UNTESTED (2026-07-10)

Honours the player's global combat-resolve setting (`AoWReg.GetCombatResolveMode@0x557056A4`: 0 ask /
1 fast / 2 tactical) instead of hard-forcing fast. Tactical `CreateCombat(map, 0x220110)` goes modal —
the setup function returns immediately and the true result arrives later via the `combat[+0x2C]`
callback (`cave_razedone`), so the result-gate/raze logic that lived entirely inside
`cave_towerraze`'s straight-line flow for the fast path had to be duplicated into the callback for the
tactical one. v1 (this stage) is launch + callback gate/raze with **no combat log for the tactical
path and no ask-mode dialog yet**. The ask-mode dialog (and the freeze it caused) is §4.5; the
missing tactical combat log stayed open until **Stage 12d, §4.4.3a**.

#### 4.4.5 Stage 8 — generalised to every non-city razeable structure — 🔨 APPLIED, UNTESTED

Audited every class implementing `GetRazed`/`SetRazed` (855-VMT scan): six non-city structures all
inherit every collaborator the caves touch (coordinate slots, `RazeEx`, `SetupRazeDefenderAG`,
`CreateTE`/`SetupTE`, `GenerateRazeDefenders`, `PlaceRazeDefenders`, `ExecuteRaze`=vanilla
`0x5575FFC8`, `Raze`, `CanRaze`) with **one divergence**: five of the six override `SetPlayer` (slot
`0x1F0`, income re-registration etc.) but `TTeleport` (a direct `TStructure` child, unowned) has no
`SetPlayer` slot at all — handled by an `IsClass`-gated **virtual** `SetPlayer` call inside
`cave_lossgarrison` rather than assuming the slot exists. VMT slot `0x1B0` repointed to
`cave_towerraze` on all six:

```
TAltar 0x557CE7C4 · TFarm 0x557B281C (via TPlayerCropStructure) · TMine 0x557B4020 ·
TPowerNode 0x557CFFE4 · TProductionPlace 0x557BD68C · TTeleport 0x557A4A28
```

No other class descends from a razeable one, so this closes the set. `TCity` is deliberately excluded
here (its `ExecuteRaze`/`GenerateRazeDefenders`/`SetupRazeDefenderAG` all differ) — Stage 9 handles it
separately.

#### 4.4.6 Stage 9 — city raze as a real battle — 🔨 APPLIED, UNTESTED

`TCity.ExecuteRaze@0x557AB414` is a thin wrapper — base `TStructure.ExecuteRaze` plus a **−30
race-relation penalty on success** — so the win path routes through `cave_razedispatch`
(`IsClass(TCity) ?` the city wrapper `:` the base function) purely to preserve that diplomacy hit.
`TCity.GenerateRazeDefenders@0x557AB408` **is** `GenerateRebelUnits+ret 1` (budget `25×GetSize`,
level ≤2, type-mask `0x03`) — the same rebel mob the rebellion system uses (§4.4.7) — so the militia
`cave_towerraze` fights via VMT `0x1A8` is automatically the city's own rebel-mob roster; no new
roster code was needed. Repoints: slot `0x1A8` → `cave_citygenraze` (survivor substitution, mirrors
§4.4.9's Design A), slot `0x15C` → `cave_cityguard` (razeguard-gated Guard AG for a loss-garrison,
else the vanilla city fn including its own 1/8-chance kind-5 raider flavour on avenger spawns).

⚠ **Bugfix within Stage 9: multi-hex razer lookup.** `cave_towerraze` originally read only the
structure's *centre* field for the razing army — correct for single-hex structures, wrong for a city,
whose garrison often sits on a non-centre footprint hex, so the lookup returned null and raze silently
did nothing. `cave_findrazer` walks the **whole footprint** exactly like
`TStructure.ListUnits@0x5575F37C` (the same lister `CanRaze` itself uses to find attacker forces —
which is precisely why `CanRaze` was passing while the battle cave found nobody), and single-hex
structures still resolve to the centre field as before.

**Day-term seeding for the city mob:** `cave_cityseed` hooks the map-seed add inside
`GenerateRebelUnits` (`0x557ABCD5`, `add ebp,[eax+0x22C]` — a **register-relative** operand, no
`.reloc`, unlike the seed-*store* four instructions later at `0x557ABCE7`, whose absolute operand does
carry a reloc and must never be touched — displacing a reloc-bearing operand is the "works one launch,
crashes the next" trap) and appends `Map[+0x174]` (the day counter), mirroring
`build_razeroster_vary.py`'s fix for the same seed formula on non-city structures (§2.5). Because
`TCity.GenerateRazeDefenders` **is** `GenerateRebelUnits`, this single hook re-rolls **both** the city
raze militia and the rebellion mob (§4.4.7) per day.

#### 4.4.7 Stage 10 / 10b — rebellion as a real battle — 🔨 APPLIED, UNTESTED (2026-07-12)

**The convergence that makes this cheap:** a city rebellion is mechanically a city raze where "the
garrison wins" means *hold* instead of *raze* — the loss and stalemate outcomes are identical to a
city raze, and the rebel mob **is** the raze-militia (§4.4.6). So rebellion reuses `cave_towerraze`
via a **rebellion bit** packed into the `ExecuteRaze` argument (`DL` bit 6 = `0x40`; low nibble =
player; bits 4–5 = combat-type choice) rather than any new combat-construction code.
`CheckRebellion@0x557AB534`'s rebellion branch is edited three ways: the garrison-eviction call
(`MoveArmiesOutOfCity`, `0x557AB5AC`) is NOP'd out so the **garrison stays to defend** instead of being
shoved aside first; the "Rebellion in X!" event log is kept; and the vanilla flip+spawn
(`0x557AB632` onward) is replaced by `cave_rebellion`, which runs the battle and branches: garrison
wins → the rebellion bit tells `cave_towerraze`'s win branch to **skip the raze** (city held); loss
(undefended city) → `cave_lossgarrison` flips it to the rebels via the same machinery a raze loss
uses.

**Stage 10b — rebellion chance table.** Vanilla only rolled rebellion at civil status < 2 (Unruly
75% / Unrest 25%). `cave_rebelchance` replaces the status gate and threshold with the user's model:
**Unruly 30% / Unrest 20% / Oppressed 10% / everything else 0%**. This tracks the fact that, on this
live build, the wall/upgrade/terrain loyalty terms are already zeroed (§4.1) — an under-garrisoned
suppressed city now drifts toward Unrest/Unruly on garrison strength alone and can genuinely revolt,
and (via this same battle rework) can actually **win** against a weak garrison rather than always
flipping automatically.

**Stage 12 (2026-09-12) — two rebellion defects, one pass** (and a **tactical** rebellion files its
report too since 12d, §4.4.3a). A fast rebellion battle now files a
combat report for **every witness**, not only the razing player: `DistributeCombatEvent@0x5572928C`
replaced Stage 2's single-player block, so the city's owner sees the fight they just lost (§4.4.3).
And a victorious rebel garrison is now **buyable** — it gets no AI group at all, exactly as vanilla's
own rebel placement does, because a Guard AG (behaviour 2) makes `CanJoin@0x557821AC` refuse and the
gold offer never appears (§4.4.9).

#### 4.4.8 Part C — loot as a real battle, with fast/manual payout timing — 🔨 APPLIED, UNTESTED (2026-07-12/13)

Looting a captured city queues a 1-turn "loot" production; the gold is awarded when it **completes**,
in `TCityProductionControl.NewTurn@0x557A82A8` case 5, computed as `citySize × MULT` twice (message
text and the actual `SetGems` payout — both a 3-byte `LEA reg,[reg+reg*8]` = ×9 in vanilla). The
delay *is* the intended penalty (you cannot fight-then-immediately-move-away), so the battle fires at
**production completion**, mechanically a city raze whose "looter WON" branch awards gold **instead
of** razing; loss and stalemate are identical to a city raze, and the populace **is** the raze-militia.
Loot therefore also reuses `cave_towerraze`, via a **loot bit** (`DL` bit 7 = `0x80`).

**A v1 bug, fixed in v2 the same day — do not retry the v1 shape.** v1 read the owner via city
*slot `0x7C`* — but on a structure, slots `0x74`/`0x78`/`0x7C` are the **X/Y/LEVEL coordinate
accessors**; `0x7C` is `GetPlayer` only on the *production control* object, a different class that
happens to share the slot index. Every surface city therefore read "level 0" as its owner, tripped the
`owner==0` safety guard, and skipped the battle entirely — gold paid straight, no injury or XP trace
(an underground city, level ≥1, would have "worked" by accident). v2 reads the correct `city[+0x30]`
owner byte instead (the same byte `cave_rebellion`/`CheckRebellion`/`SetPlayer` already use).

**Outcomes** (vanilla loot semantics preserved, user-confirmed): **win** (looter side 0 wins, `{3,6}`)
→ the real vanilla case-5 code runs in full — gold, "City looted" message, **and `SetRazed(1)`**
(vanilla loot always razed the city to ownerless ruins; the battle just gates whether you pull it
off). **Loss** (looter wiped, `4`) → `cave_lossgarrison` flips the city independent with the surviving
populace as its garrison, no gold. **Stalemate** (`2`/`5`) → nothing changes; production stays queued
and it re-fights next turn. The payout path is always the **real** vanilla case-5 code
(`cave_lootbattle` jumps into it), never a hand-transcribed copy, so gold/message/raze stay
byte-identical to vanilla when they fire.

**Loot is fast-only in the current build — a fast/manual choice was tried and reverted the same day.**
`cave_lootbattle` always resolves synchronously; `LOOT_FAST` (`0x90`) hard-codes the fast-resolve bit
into every loot's `ExecuteRaze` argument regardless of the player's combat-resolve setting.
`FLAG_LOOTWIN@0x558FA80C` (set by the win branch, read immediately after the synchronous battle to
gate the payout) is the only loot-specific flag still live. An approach-A design honouring the
player's Tactical/Ask setting — a manual fight unwinds the turn-processing stack before finishing, so
its payout was made to ride the real case-5 code on the owner's **next** turn instead, via two more
flags (`FLAG_LOOTASYNC`/`FLAG_LOOTWIN2`) — was built and applied on 2026-07-13, then **reverted the
same day after regressions** (the source material for this merge does not record what regressed).
`0x558FA80D`/`0x80E` are free again as a result. **Do not re-derive this without checking the current
script state first** — the design itself may still be sound; what is known is that its first
implementation had to be backed out.

**City loot gold multiplier — `build_loot_multiplier.py`, 🔨 APPLIED, UNTESTED (2026-07-12).**
Independent of the battle rework (own two sites, own backup). Both ×9 `LEA` sites
(`0x557A8600` message text, `0x557A86BE` gold award) become `imul reg,reg,imm8` — also exactly 3
bytes, register-only, no `.reloc` hazard, no cave. `NEW_MULT` is a single named constant at the top of
the script (shipped at 15×, retuned to **10×** the same day); the patch table accepts either the
vanilla ×9 `LEA` or any earlier `imul` at the site as a valid prior, so retuning never needs a revert
first — just edit the constant and re-run `--apply`.

#### 4.4.9 Design A / Stage 11 — survivor re-homing, Guard AG, roster substitution on a loss — 🔨 APPLIED, UNTESTED

User-requested refinement to what happens after a **lost** raze/rebellion/loot battle. The original
req2 behaviour (vanilla `PlaceRazeDefenders`) was wrong on two counts the user identified directly:
avengers spawned on an **adjacent** tile with **wandering** orders, when the intent was the literal
damaged survivors, placed **on** the contested hex, set to **Guard**.

- **Adjacent-placement cause, and the one-line fix:** `PlaceRazeDefenders` was being called *before*
  `SetPlayer(independent)`, so the structure was still razer-owned and `Place` shunted the new
  independent units off to an adjacent hex. Reordering to `SetPlayer` first fixed it.
- **Wandering-orders cause:** `SetupRazeDefenderAG` (slot `0x15C`) creates an AI group of kind `0xD` =
  `AoWE.THuntAG` (`Behavior@0x55739694` = `mov al,0xd`) — hence the wandering. `cave_setupguard` hooks
  its entry and swaps the requested kind to **`2`** (`TGuardAG`) whenever a new BSS flag `razeguard`
  is set — set only around the specific `PlaceRazeDefenders` call that places a loss-garrison, so
  every *other* call (normal raze-defender placement) is untouched.

  ⭐ **The kind argument IS the behaviour value.** `TAIGroupManager.CreateGroup@0x55737EB4` walks its
  registered class list and picks the one whose **class method** `Behavior()` (VMT `+0xD0`) equals the
  pushed kind (`call [eax+0xd0]` / `cmp bl,al` / `sete al` @`0x55737EDB`). There is no separate kind
  enum to look up. Byte-verified map:

  | kind | class | kind | class | kind | class |
  |---|---|---|---|---|---|
  | 1 | `TPatrolAG` | 7 | `TAggressorAG` | `0xE` | `TExpanderAG` |
  | 2 | `TGuardAG` | 8 | `TDefenderAG` (`@0x557DD6F4`) | `0xF` | `TScorcherAG` |
  | 3 | `TGuardAreaAG` | 9 | `TFortifyAG` | `0x10` | `TNormalAG` |
  | 4 | `TScoutAG` | `0xA` | `TSuicidalAG` | `0x11` | `TSkirmishAG` |
  | 5 | `TRefugeAG` | `0xB` | `TPassiveAG` | `0x12` | `TTransportAG` |
  | 6 | `TRaidAG` | `0xD` | `THuntAG` (`@0x55739694`) | | |

- ⚠ **Stage 12a (2026-09-12) narrowed this: CITIES now get NO AI GROUP AT ALL; structures keep Guard
  kind 2.** A Guard AG made a victorious city rebel garrison **unbuyable**.
  `TAbstractUnit.CanJoin@0x557821AC` reads the unit's group *before* any race-relations logic and
  refuses behaviours 2 and 3:

  ```
  557821B5  mov ebx,[esi+0x20]  /  test ebx,ebx  /  je 557821CE   ; NO group -> gate SKIPPED
  557821BE  call [eax+0xD0]                                       ; group.Behavior()
  557821C4  add al,0xFE / sub al,2 / jb 55782318                  ; behaviour 2 or 3 -> FALSE
  ```

  The gold offer has exactly one path — `TCity.GetMoveAction` / `IncommingNegotiateRequest` /
  `IncommingNegotiateOffer` → `TCity.JoinAmount@0x557ACF98` → `TArmy.GetCanJoinSelection@0x5578FA04`
  → VMT `0x194` `CanJoin` — and an empty selection means no offer is ever presented. Vanilla
  `CheckRebellion@0x557AB63E–0x557AB6A5` (still in the live file, unreachable behind our `jmp`
  @`0x557AB632`) places rebels with `TUnitList.Create` → `GenerateRebelUnits` →
  `TAbstractUnit.Place` and **never calls `SetupRazeDefenderAG`**, so vanilla rebels have no group.
  Exact parity is the fix: `cave_cityguard`'s razeguard branch now ends `ret` instead of
  `jmp 0x5575FE0C`. Scope is every **city** loss-garrison (rebellion, lost city-raze, lost city-loot),
  all of which funnel `cave_lossgarrison@0x5580CE90` → vcall `0x1AC` → `TCity` slot `0x15C`.
  Structures never reach `cave_cityguard` (it exists only in `TCity`'s VMT). The garrison is still the
  literal damaged survivors — `FLAG_RAZEGUARD`'s other readers, `cave_genraze@0x5580D080` and
  `cave_citygenraze@0x5580D260`, are untouched — now merely buyable.

  ⚠ **Not kind 5 `TRefugeAG`.** `TAbstractUnit.JoinAmount@0x55782324` special-cases behaviour 5
  (`cmp al,5` / `jne` / `xor eax,eax`) → cost **0**, i.e. free rebels. And do not patch `CanJoin`
  itself: the behaviour-2/3 gate is vanilla and correct.

  ⚠⚠ **The vanilla-parity claim is byte-verified for PLACEMENT ONLY — post-placement behaviour is
  not.** What the pristine root's `CheckRebellion` proves (`0x557AB652..0x557AB6A3`) is the *absence*
  of a group: `GenerateRebelUnits` → `TUnitList.GetUnit` → `TAbstractUnit.Place`, with no
  `SetupRazeDefenderAG` and no `call [reg+0x15C]` anywhere in the run. Nothing in the binary says what
  a group-less independent garrison then *does* each turn. Stage 11 added the Guard AG specifically
  because kind `0xD` `THuntAG` made these units **wander off**, so the failure mode to watch for is a
  group-less city garrison drifting off the city hex, or failing to defend it — which would make
  group-less strictly worse than the Guard AG it replaced, and would mean the fix has to move to
  `CanJoin`'s consumers instead (offer the join on a Guard garrison) rather than to the group.
  **This is an in-game observation over several turns; no static check can settle it.**
- **Survivor re-homing** (`cave_rehome`, called from the callback before `DestroyCombat`): a faithful
  transplant of the verified re-home model in vanilla `TExplorationSite.CombatExecuted` — walk
  `combat[+0xC]`'s combat-data by its **fixed initial** `GetCount` (`SetUnit(0)` does not shrink the
  list mid-walk), keep objects that are `IsClass(TCombatUnit)`, are a **conquer object**
  (`obj[+0x48]` bit 0 — see the Stage-11 note below) and are still alive (`obj[+0x47]` bit 0 clear),
  and for each run the mandatory refcount order `AddRef(slot 0x28)` → `SetUnit(0)(slot 0x134)`
  (detach) → destination-army `AddUnit(slot 0xAC)` → `Release(slot 0x2C)`. The harvested army is
  stashed in a new BSS dword, `FLAG_RAZESURVIVORS`, and substituted for the fresh roster the next time
  `GenerateRazeDefenders` runs on that structure (`cave_genraze`, an entry hook on
  `GenerateRazeDefenders@0x5575FD1C` that **composes** cleanly with `build_razeroster_vary.py`'s own
  seed hook further down the same function — the passthrough case replays the same 7-byte prologue and
  jumps to the same resume point the seed hook expects, so the day-term seed variation still runs
  untouched on every path that isn't substituting survivors).

  ⚠ **Stage-11 refinement to the harvest filter, recorded because it fixed a real gap:** the harvest
  originally kept `GetPlayer()==0` (independent) survivors. That missed **permanently-converted**
  units — a garrison member seduced/charmed/dominated mid-battle still reads as the *loser's* player
  at harvest time, so it wandered off alone instead of joining the winning militia. The fix reads the
  **conquer-object flag** (`obj[+0x48]` bit 0) instead — the flag the engine itself uses to mean "a
  unit the winning side keeps," which correctly includes both the militia/rebels *and* any convert.

- **No-flee for the razer** (`cave_noflee`, a passthrough hook on the fast-combat flee-gate predicate
  at `0x557444A9`, gated by BSS flag `razenoflee`): forces the razing side to fight to a decisive
  result rather than withdrawing mid-battle, since "razers count as defenders" was the intended framing
  once walls entered the picture.

Every new BSS flag from Stages 1–11 lives in the page slack starting at `0x558FA801` (post-move, see
§4.6): `razeok` (`0x861`), `combathappened` (`0x802`, vestigial Stage-1 proof), `razeasync`/
`razeplayer` (`0x803`/`0x804`, Stage-3 tactical-callback routing), `razeguard` (`0x805`), `razenoflee`
(`0x806`), `razesurvivors` (`0x808`, dword), `lootwin` (`0x80C`, Part C — the only loot flag still in
use; `0x80D`/`0x80E` were the reverted fast/manual-choice flags and are free again, see §4.4.8). Free
BSS for the *next* feature in this cluster starts at `0x558FA844`.

#### 4.4.10 The 2026-07-30 replay assertion — `build_enchant_assert.py`, 🔨 APPLIED, UNTESTED

Not part of the raze-battle stage sequence, but a defect the stage sequence's own hidden-defender
pattern exposed, and one fix repairs it for every feature that uses that pattern. Rewinding a
fast-combat record that enchanted a hidden defender raised
`"Assertion failure (…AoWAb.PAS, line 46181)"` — non-fatal, but it disabled the replay transport
arrows for the rest of the session.

**Root cause:** `AoWE.TUnitEnchantmentAbility.Expand@0x55765894` asserts `unit[+0x18] > 0` (the unit
id) before creating enchantment ability-data. `TAbstractUnit.Create` initialises `+0x18` to **−1**;
an id is only ever assigned by `TUnitControl.RegisterUnit`, whose **sole caller** is
`TAbstractUnit.Activate` — i.e. a unit gets an id only when it is placed on the map. **Every hidden
defender stack in the game — exploration-site defenders, dungeon prisoners, the raze militia, the
arena militia (§5) — is joined via `AddArmyEx(-1,-1,-1)`, "no map field," and never activated, so it
keeps id −1 forever.** The assert therefore fires the moment *any* enchantment (Entangled, Panicked,
a cast buff/debuff) is expanded onto one of them. It surfaces on replay rather than live play because
the live fast combat carries the enchantment on the `TCombatUnit`, while rewinding re-drives the
strategic-side `Expand`.

**Fix — one byte, `0x557658DA`: `7F`→`EB`** (`jg short` → `jmp short`, same target, same length),
skipping the assert unconditionally. This is exactly right, not merely expedient: a registered unit's
id is **always** ≥ 1 (`TUnitControl.Create` starts its counter at 1 and `GetFreeID` wraps to 1, never
0), so `id ≤ 0` is precisely "never registered" — skipping the assert loses no debug coverage for any
reachable legitimate case. Sibling sweep: of 56 `System.@Assert` sites in the module, exactly this one
is guarded by the unit-id invariant; the assert two lines above it (the `owner is TAbstractUnit` type
check, same function) is a real check and is left alone.

**Provenance-checked before writing:** the whole 26-byte assert block is byte-identical between the
live DLL and the pristine backup — vanilla code, no other feature owns this site.

#### 4.4.11 Reverting this feature — there is no `--undo` flag

`build_razebattle_tower.py` has **no `--undo`/`--revert` argument anywhere in its ~2,300 lines** — it
only ever applies forward, re-tuning by rewriting its own caves in place (§4.4, `_own_prior`). Its own
printed apply message says "Revert: undo surgically," but that is guidance, not a switch. A genuine
surgical revert of this feature means, by hand, for every stage that was actually applied: restoring
`VMT_ORIG` at the `0x1B0` slot of `TTower` and all six Stage-8 structure classes (§4.4.5) plus
`TCity`'s three repointed slots (`0x1A8`/`0x15C`/`0x1B0`, §4.4.6), restoring every hook site's original
bytes (`CANRAZE_ENTRY`, `AVENGER_HOOK`, `SETUPAG_HOOK`, `NOFLEE_HOOK`, `GENRAZE_HOOK`,
`FORCEFAIL_HOOK`, `CITYSEED_HOOK`, `EVICT_NOP_HOOK`, `FLIP_HOOK`, `REBELCHANCE_HOOK`,
`NEWTURN_LOOT_HOOK`), restoring the reworded raze message string, and zeroing every cave in
`0x5580C910..0x5580D600` (Stage 12d pushed the top of the used region up to the seed reserve; the old
`0x5580D4EA` figure predates it). This is exactly the kind of large, easy-to-get-wrong manual revert the
project's surgical-`--undo` convention exists to avoid — **flagged here rather than attempted**; see
Open items.

⭐ **Stage 12c made the in-place rewrite safe in the SHRINKING direction too.** `process()` writes
exactly `len(new)` bytes, so any stage that shrinks a cave leaves the tail of the longer blob live on
disk — unreachable, but bytes that disassemble as garbage and that a later grow-back would collide
with. Both caves now carry a **fixed reservation** — `TOWERRAZE_RESV = 1152`
(`0x5580C910..0x5580CD90`, landing exactly on `CAVE_CANRAZE`), `CITYGUARD_RESV = 33`
(`0x5580D2B0..0x5580D2D1`) — and the emitted blobs are zero-padded to it. ⚠ `towerraze_s1_prior` is
padded to `TOWERRAZE_RESV`, **not** to `len(cave_towerraze)`: those were equal only while the cave
grew, and the "is this a clean Stage-1 file?" test would otherwise read short.

⭐ **Stage 12d extended the doctrine to a RELOCATION, and found two more orphans doing it.**
`RAZEDONE_RESV = 0x100` (`0x5580D500..0x5580D600`) and `LOOTBATTLE_RESV = 0x60`
(`0x5580D4A0..0x5580D500`); the slot `cave_razedone` vacated (`0x5580D3D0..0x5580D460`) is zero-filled
by its own patch-table entry rather than left live. The orphans absorbed — 23 B of a pre-Part-C-v2
`cave_lootbattle` at `0x5580D4E3` (mid-instruction, unenterable) and a complete 55 B pre-Stage-10 copy
of `cave_rebelchance` at `0x5580D550` — show that the 12c sweep audited only the caves it was editing.
⚠ **So did 12d's**, which is what Stage 12e below was chartered to finish.
⚠ **A relocation needs a stronger prior than `_own_prior` gives.** `_own_prior` accepts whatever sits
at an address purely because the VMT hook is ours, which is right for a cave we have always owned and
too loose for one we have never written to; 12d adds a positive guard that the new home is zeros, our
own applied blob, or *only* that identified `cave_rebelchance` copy, and aborts otherwise.
⚠ `src_towerraze_stage1` is pinned to a **frozen** `CAVE_RAZEDONE_S1`, not to `CAVE_RAZEDONE` — it
exists only to reproduce Stage-1 bytes, so tracking the live constant would redefine the accepted
prior every time a cave moves.

⭐⭐ **Stage 12e closed the region — 🔨 APPLIED, UNTESTED (2026-09-12).** 12c and 12d each reserved
only the caves they happened to be editing, so three shrink-tails outlived both sweeps. Found by QA on
the 12d pass, absorbed by three more fixed reservations that each land exactly on the next cave's
first byte:

| VA | size | what it was | absorbed by |
|---|---|---|---|
| `0x5580CDA0` | 11 B | a **complete, instruction-aligned, enterable** duplicate of `cave_canraze` (`push ebp; mov ebp,esp; add esp,-0x1C; jmp 0x5575FB86`) — identical to the live cave but for the `0x10` delta in its rel32; unlike the `0x5580D4E3` orphan it does **not** start mid-instruction | `CANRAZE_RESV = 0x20` → `0x5580CDB0` |
| `0x5580CDE0` | 27 B | the pre-relocation `cave_forcefail` (tail jumps `0x5575FCB3` / `0x5575FCB7`), stranded when the cave moved to `0x5580D150` and outgrew this slot — the script's own `CAVE_FORCEFAIL` comment had called the region dead since that move, but nothing ever zeroed it | `SKIPAVENGER_RESV = 0x60` → `0x5580CE10` |
| `0x5580D040` | 5 B | `pop ebx; mov esp,ebp; pop ebp; ret` — the tail of a 197 B `cave_rehome` that shrank to 192 | `REHOME_RESV = 0x100` → `0x5580D080` |

The deadness proof was **re-run at 12e, not inherited**: every `E8`/`E9` rel32 in `CODE`, every literal
dword in every section of the whole file, and all 63,880 `.reloc` entries — zero references into any of
the three spans. ⚠ **A linear rel8 scan throws false positives and both of 12e's needed adjudicating:**
`0x5580CDEB` is the forcefail orphan's *own* internal `je` (target `0x5580CDF4`, inside the same dead
blob), and `0x5580CFEC` is not an instruction boundary at all — it is byte 3 of the displacement in
`mov edx,[edx+0x55715a54]` at `0x5580CFE8`. Neither is a reference. No fall-through reaches any span
either: `cave_canraze` ends in `jmp`, `cave_skipavenger` in `ret` @`0x5580CDCE`, `cave_rehome` in `ret`
@`0x5580D03F`.

⭐ **12d's positive on-disk guard generalised to all three.** `_own_prior` would accept whatever sits in
a newly-widened span purely because the VMT hook is ours — too loose for bytes the script has never
written. So 12e states positively what is allowed in each growth zone: zeros, our own applied bytes,
or *only* the one identified orphan; anything else (a foreign cave that moved in, or an unaudited
shrink-tail of our own) aborts before writing. ⭐ **The exemption lapses once applied** — the zone must
then be entirely zero — so a later re-run re-proves the orphans are still gone rather than permanently
whitelisting their addresses.

**Verified after the apply** (2026-09-12): the script reports "already applied"; all three spans read
zero; all three growth zones read zero end to end; all eleven of this script's caves plus both foreign
neighbours (`cave_valfix` @`0x5580D200`, the seed cave @`0x5580D600`) are byte-unchanged;
`build_relocfix.py --audit` reports 0; the file size is unchanged. ⭐ A sweep of the whole owned region
`0x5580C910..0x5580D640` now finds **zero non-zero bytes outside a known cave span** — the region is
covered end to end by fixed-length reservations and nothing in it is left to the writer's `len(new)`.
⚠ This is a byte-hygiene change with **no gameplay effect** — no cave's own code moved or changed, so
there is nothing new to test in-game beyond confirming the raze/rebellion/loot features still behave as
they did before.

⚠ **This had already bitten once before Stage 12, which is why the reservation is 1152 and not 1140.**
An earlier stage shrank `cave_towerraze` from **1152 → 1140** and orphaned 12 bytes of live code at
`0x5580CD84`:

```
5580CD84  8b 45 fc        mov   eax,[ebp-4]
5580CD87  0f b6 55 f8     movzx edx,byte ptr [ebp-8]
5580CD8B  e8 00 01 00 00  call  0x5580CE90   ; cave_lossgarrison, then FALLS INTO cave_canraze
```

Found by QA on the Stage-12 apply and **not** a Stage-12 regression: byte-identical in
`Ziggurat\backups\AoWEPACK.dpl.pre-panicnomelee`, taken 17 minutes earlier. Proved dead before being
overwritten — a module-wide scan for the absolute dword `0x5580CD84..0x5580CD8F` and for every
`E8`/`E9` rel32 in every CODE section found **no reference**, and no branch inside `cave_towerraze`
targets anything at or above `0x5580CD22`. Raising the reservation to 1152 zeroes it; `cave_canraze`
at `0x5580CD90` verified byte-unchanged (`55 89 e5 83 c4 e4 e9 eb 2d f5 ff`) afterwards. ⭐ The
general lesson: **a shrunken cave's orphaned tail is invisible to every check this script runs** —
the pad is genuinely zero, the asserts pass, and the dead code sits past the end. Only a disassembly
of the gap between a cave's reservation and the next cave's address finds it.

⚠ **The backup line minted a fake prior once, on 2026-09-12, and is now gated.** The guard was
`if not os.path.exists(bpath)`, which is not a freshness test: with no `--undo`, this script's only
re-tune path is `--apply` over an existing install, so the file on disk is its **own previous stage**.
When `Ziggurat\backups\` was purged the short-circuit stopped hiding it and the Stage-12 apply wrote
`AoWEPACK.dpl.pre-razedlgfix` containing a **Stage-11 patched** image (verified: VMT `0x557C3358` read
`10 c9 80 55`, not vanilla `c8 ff 75 55`). That file was deleted. The gate is now a positive test
against the original bytes — a snapshot is minted only while `VMT_SLOT` still holds `VMT_ORIG` — and
`os.makedirs(BACKUP_DIR)` fires only on a genuine mint. The pristine reference for this DLL is the
vanilla game root, never anything in `backups/`.

### 4.5 The raze combat-type dialog and modal-combat freezes — 🔨 APPLIED, UNTESTED (2026-07-21)

Four related defects, found via one in-game freeze, plus two *unrelated* freezes that were chased
down the same trail and turned out not to be raze bugs at all. All fixes live in
`build_razebattle_tower.py` except the last two, which belong to `07-ui.md`'s combat-log scripts and
are recorded here only because their root cause is a variant of one this section already explains.

#### 4.5.1 The symptom and what it wasn't

In-game: an AI razed one of its own cities under **simultaneous turns**, `Combat Resolve Mode = Ask`,
one human player. The **local human**, not a participant, was shown the quick-vs-tactical
combat-type dialog for that battle; accepting it froze the game (screen stopped, sound still
running — an idle wait, not an access violation).

Ruled out first, so as not to re-investigate: the fast-force gate (`cave_razemode`, tests
`map[+0xA5]==razePlayer && GetPlayers(razePlayer)[+0xA7]==0` — both halves verified against the
installed bytes using the `map[+0xA5]`/`player[+0xA7]` decode at the top of §3; a player-0/independent
razer or an AI razer fails this gate on either half, so neither can reach the dialog); collision with
any other recently-applied feature (checked, nearest cave/hook ~8 KB away); rebellion or loot reaching
the ask branch (`cave_rebellion` passes `owner|0x50` and `cave_lootbattle` `owner|0x90`, so their
choice nibble is always in `{1,3}`, never 0=Ask).

#### 4.5.2 Root cause — three defects in `cave_typechosen`, one missing invariant

Only four sites in the whole live DLL can raise a `TCombatTypeRequestEventLog`: two vanilla
`TArmyCombatMoveTE.SetupCombat` sites (one seat-checked, one **not** — guarded only by
`PlayerTypeInvolved`), vanilla `TExplorationSite.Search` (**unguarded**, safe in vanilla only because
the AI never searched sites before this feature and its companion`
§1.4 opened that door), and this feature's own `cave_towerraze` (guarded by `cave_razemode`). The map's
event-log distribution slot (`TAoWHSMap.TriggerExecuteEventLog@0x55776624`) does an **immediate,
re-entrant notify with no player filter at all**, and this event-log class is absent from the
simultaneous-turn popup suppression mask — so *anything* that reaches the dialog-raising site pops it
on the local machine regardless of who is involved. Since the fast-force gate held, the dialog must
have come from **`cave_typechosen`**, the callback that re-issues the raze TE after a choice. Measured
against vanilla's own handler for this exact event log (`RequestCombatTypeCallBack@0x557489CC`):

1. **A dword read of a byte field.** The cave read `[eventlog+0x18]` as a dword, but only `+0x18`
   itself is the choice byte — `+0x19` (acting player), `+0x1A` (defender), `+0x1B/1C/1D` (x/y/l) are
   live bytes above it. A **cancel** (choice 0) with any nonzero player byte read back nonzero and was
   actioned as a pick; worse, the shift used on the misread value cleared the low byte, so the
   re-issued TE carried **choice 0 = Ask again** — cancelling **re-raised the dialog forever**, minting
   a fresh token event from inside an event-log callback each time.
2. **No request-live check.** Vanilla gates on `[eventlog+0x24] != 0` before acting; the cave never
   checked it, so stale or replayed event logs were actioned.
3. **The player came from a racing global.** `FLAG_RAZEPLAYER` was written by `cave_towerraze` on
   **every** entry, before the mode decision — since the dialog is asynchronous, any forced-fast raze
   (AI/rebellion/loot) landing between raising the dialog and answering it retargeted the answer to a
   *different player's* raze. Under simultaneous turns this race is routine. The event log already
   carries the acting player at `+0x19`; vanilla reads it from there.

**The freeze itself is a separate, missing invariant.** Vanilla refuses a manual resolve unless a
type-0 local human is actually a party to the combat
(`TCombat.PlayerTypeInvolved@0x5572724C`); `cave_towerraze` checked neither that nor
`DefendersAvailable`, so it could open a modal combat with nothing the local human controlled — and a
**tactical `CreateCombat` disables the map turn timer**, which under simultaneous turns is what keeps
the world moving, hence frozen-with-sound. Compounding it: `CreateCombat` raises "Combat already
created" whenever `map[+0x120] != 0`, and with no SEH frame on the cave, an unwind from anywhere in
this path skips `DestroyCombat`/`UnlockGameOverEvent` and leaves `map[+0x120]` stuck — after which
**every** later battle raises too.

#### 4.5.3 The fix

`cave_typechosen` 115→123 B; `cave_towerraze` 1101→1140 B (two sub-revisions, see below).

1. `cmp byte [eventlog+0x24],0; jz done` — honour the request-live flag first.
2. `movzx ecx, byte [eventlog+0x18]` — a byte read; a cancel is now a cancel.
3. `movzx ebp, byte [eventlog+0x19]` at entry, used at pack time — player from the event log, never
   from the racing global.
4. Before `cave_razemode`: require the army that will actually be `AddArmy`'d as side 0 to belong to
   the player named in the raze TE, else force fast. (`cave_findrazer`, §4.4.6, returns the *first*
   army on the footprint, which for a multi-hex city need not be the razer — this check was added with
   a NIL screen because it dereferences the army earlier than the original code did.)
5. Before `CreateCombat`: `cmp dword [map+0x120],0; jne <epilogue>` — never build a second combat; the
   structure simply stands this time (AI `RazeControl` is one-shot; a human can re-click).

**Why the gate sits *before* `CreateCombat`, not after `AddArmy` the way a literal transcription of
vanilla would place it:** by the time a tactical `CreateCombat` has run, the turn timer is already
disabled — a combat we created and then declined to run modal would leave the world stopped, the exact
symptom being fixed. Checking the army's owner *before* creation enforces the same invariant strictly
earlier.

**Regression introduced and fixed the same day.** Hardening step 1 added the request-live check but
missed that our own event log never *set* `+0x24` in the first place — so every raze choice silently
did nothing (dialog appears, you pick, nothing happens). Fixed by adding `mov byte [eventlog+0x24],1`
in `cave_towerraze`'s dialog-raising block, right after the existing `+0x19`/`+0x1A` writes.
**Lesson: before adopting a caller-side check copied from vanilla, verify the producer side actually
sets the field it checks — copying half of a contract is worse than copying none of it.**

**Test plan:** an AI-razed city with no participant present shows **no dialog at all**; razing your own
structure under Ask still shows the dialog, Cancel now genuinely cancels (it previously re-raised
forever), and either choice fights the battle normally; repeat during simultaneous turns while AI
razes happen elsewhere, to exercise the former race; rebellion and loot battles still resolve fast and
unchanged.

**Still open, not touched:** `TExplorationSite.Search`'s own unguarded dialog-raising site remains
exactly as dangerous as it always was — safe today only because nothing routes an AI into it (§1.4's
`build_ai_sitesearch.py` mints its search TE with `TE[+0x20]=1`, forcing auto-resolve, specifically to
avoid this). Any future feature that lets an AI reach a **manual** search would need to copy this
section's hardening, not vanilla's `Search` pattern. `cave_towerraze` still has no SEH frame; step 5
removes the main way to *reach* the "Combat already created" raise, but a throw from anywhere inside
`ExecuteRaze` still leaks `map[+0x120]`.

### 4.6 Two unrelated freezes chased down the same trail, plus the BSS collision that mattered here

#### 4.6.1 BSS flag collision: `simfly`/`razeok` vs. `build_path_outerring.py` — 🔨 APPLIED, awaiting confirmation (2026-07-22)

After §4.5's fix the user hit a **different** freeze signature: "Exception occured during
TArmyCombatMoveTE," both stacks deleted, frozen with sound running, reproducible on reload — and it is
**not a raze bug at all.**

**How it was found:** not more static analysis, but `build_combatdiag.py` (§6), a purely additive
file-logging probe hooking `CreateCombat`/`DestroyCombat`/`TStructure.Raze` and writing one closed
line per event to a log that survives killing the frozen process. Three static hypotheses died against
the first two logs: the raze feature being involved (zero `RAZE` records — both hung combats came from
vanilla `TArmyCombatMoveTE.ExecuteCombat`); `map[+0x120]` leaking (it read `00000000` at *every*
`CreateCombat`); and the freeze being a modal wait (the resolve flag showed quick-resolve — the hang
was inside an *auto-resolved* battle).

**The actual cause:** a probe revision also dumped the mod's own BSS dword at `0x558FA800` per combat,
and it read map **coordinates**, not flags, across three battles. `build_path_outerring.py`'s
`cave_stash` (hooked in `TAbstractUnit.MovedTo`) writes the move's centre x/y to `SCRATCH=0x558FA800`
on **every unit move** — directly over `simfly`'s flag (`0x800`, §4.2) and `razeok` (`0x801`, §4.4.2).
Consequence: `simfly`'s `cave_cv` (zeroes melee CV under the flag) and `cave_retal` (injects
retaliation) were **silently active in every ordinary battle** whenever a recent unit move happened to
leave the right byte pattern in place. A zeroed combat value is exactly what makes `SetupRoundTargets`
drop a target, and a fast-combat round pump can reach a state where nothing can act and never
terminates. Two of three logged battles survived the corruption; the third hung. This also
retroactively falsified an earlier "simfly cannot leak into the AI" claim — that reasoning traced
`simfly`'s own code correctly but assumed nothing else ever wrote the same byte.

**Fix:** moved both flags off the collision — `simfly`'s flag `0x558FA800`→**`0x558FA860`**;
`razeok` `0x558FA801`→**`0x558FA861`** (the address used throughout §4.4 above already reflects this
move). `build_path_outerring.py` keeps `0x800`/`0x801` — it claimed them first, and its `SX`/`SY`
naming is a cross-script contract also read by a Path-of-Sand feature, so moving *those* would need
both re-applied together instead. Both victim scripts rewrite their own caves in place, so the upgrade
needed no revert; verified afterwards that `0x558FA801` has zero remaining cave references and the new
bytes are referenced from every `simfly`/razebattle site that used to read the old ones. **Retest**:
the diagnostic in `build_combatdiag.py` now watches the new address, and every logged combat's flag
field must read `00000000` there.

Free BSS in this cluster after the move: `0x558FA844..0x558FA85F` and `0x558FA862` upward (to
`.idata` at `0x558FB000`). Claimed ranges: `0x800/0x801` (`build_path_outerring.py`, first claim) ·
`0x801..0x80C`+`0x80D/0x80E` (this feature, §4.4.9/§4.4.8, minus the moved `razeok`) ·
`0x810/0x820/0x82C` (`07-ui.md`'s combat log) · `0x840` (unit-spellcasting tier research) ·
`0x860/0x861` (`simfly` + `razeok`, post-move) · `0x900..0x958` (`build_combatdiag.py`).

#### 4.6.2 Two `07-ui.md` bugs found on the same trail, recorded here only for the shared root cause

Both are owned by scripts outside this file's scope, but both share one exact defect this section
already explains in full, so only the shared lesson is kept here — read `07-ui.md` for the fixes
themselves.

- **Combat log vs. a wall — ✅ CONFIRMED WORKING (2026-07-22).** `build_combatlog_dll.py`'s
  name-lookup worker read `combatObject+0x4C` (the strategic-unit back-pointer) and NIL-checked it,
  but **`+0x4C` is a `TCombatUnit`-only field** — `TCombatWall` (instance size `0x50`) reuses that
  offset for its own packed setup/hitpoint bytes, so on a wall the read returns nonzero garbage, passes
  the NIL check, and access-violates on the next dereference — on *every* hit to a wall. It only
  surfaced now because this section's raze battles are deliberately wall-less, so weeks of raze-battle
  testing never sent a wall through the log; ordinary AI assaults on walled cities finally exercised it.
  Fixed by gating every `+0x4C` read on `IsClass(obj, TCombatUnit)` first. ⚠ `TFastCombatUnit`
  **derives from** `TCombatUnit`, so this type gate does not by itself exclude fast-combat units —
  excluding those needs its own explicit check if it's ever wanted.
- **"Blt Error" on wall hits — ✅ CONFIRMED FIXED (2026-07-22).** `build_replaylog.py` had an
  **independent second copy** of the exact same `+0x4C`-off-a-wall defect, fixed the same way. Two
  copies of one idiom existed because nobody had checked whether any *other* cave used it — worth
  repeating as a general rule: **when a `+0x4C`-off-a-combat-object defect is found and fixed in one
  cave, grep for the same idiom in every other cave that touches combat objects**, don't assume a
  single fix closes the class. (The dialog shown for this bug named neither the fault nor the
  component — two nested generic `except` handlers between the fault and the message box swallow the
  real exception; do not reason about what a `MessageBox` string here means, it is usually a label on
  a `catch`, not a description.)

#### 4.6.3 Cave-sharing in the shared free-zero window — resolves a flagged ambiguity

Three scripts allocate caves out of the same contiguous free-zero run below `0x5580D640`:
`build_razebattle_tower.py` (growing upward from `0x5580C910`), `build_razeeval_timing.py`
(`cave_valfix` at `0x5580D200`), and `build_razeroster_vary.py` (its seed cave at `0x5580D600`, §2.5).
Two addresses could be misread as a clash between scripts: `0x5580D200` and `0x5580D600`/`0x5580D640`.
Read directly from all three scripts' own source (not just their docstrings), neither is a clash —
both are **declared, mutually-respected reservations**:

- **`0x5580D200`** is `cave_valfix`'s own address, owned outright by `build_razeeval_timing.py`, which
  asserts its own cave fits in `CAVE + len(cave) <= 0x5580D600` — i.e. it self-limits to the range
  below the *next* script's territory. `build_razebattle_tower.py` never writes there; it only
  *reads* the address, as a named constant `CAVE_VALFIX_RESV = 0x5580D200`, used purely as a ceiling
  so its own `cave_forcefail` (relocated to `0x5580D150` after it outgrew an earlier, smaller slot)
  cannot grow upward into `build_razeeval_timing.py`'s territory. The script's own comment records
  that this ceiling check was *added* after the fact — the original assert only checked the
  `0x5580D600` reservation below, and at one point there were only **8 bytes** of clearance between
  `cave_forcefail`'s end and `cave_valfix`'s start, which growing `cave_forcefail` without this second
  assert would have silently overwritten.
- **`0x5580D600`** is `build_razeroster_vary.py`'s own seed cave (§2.5), parked deliberately at the
  *top* of the shared window so `build_razebattle_tower.py` can grow upward from `0x5580C910` without
  colliding. `build_razebattle_tower.py` never writes there either; it references it as
  `CAVE_SEED_RESV = 0x5580D600`, the ceiling its own caves (most recently `CAVE_LOOTBATTLE @
  0x5580D4A0`) must stay below. `0x5580D640` is `build_razeroster_vary.py`'s **own** declared ceiling
  in turn (`CAVE_LIMIT`) — the start of a *fourth*, unrelated feature's cave further up (vision-range
  work; not covered by this file), which both raze scripts also independently respect as the hard top
  of the whole shared window.

So the three scripts form a chain of self-limiting reservations — `build_razebattle_tower.py` grows up
to `0x5580D200`(`valfix`), `build_razeeval_timing.py` occupies up to just short of `0x5580D600`
(`razeroster`'s cave), and `build_razeroster_vary.py` occupies up to `0x5580D640` (the next unrelated
feature) — each one's own source code asserting the boundary rather than merely documenting it. No
live collision exists at either address as of this merge. Any future feature that wants to allocate
inside `0x5580C900..0x5580D640` must read all three scripts' current cave-end addresses first, since
`build_razebattle_tower.py`'s own end-of-window keeps moving as it grows (`cave_towerraze` alone has
grown from ~500 B at Stage 1 to over 1000 B by Stage 10).

### 4.7 Cross-cutting constraints for any future raze/combat/auto-resolve feature

**⚠ Combat object lifetime: after `TCombat.Finalize`, only the OFF-MAP party's combat objects still
exist.** `TCombatUnit.Finalize@0x55724D44` destroys every combat object belonging to a party that
**has** a map field (it re-places the strategic survivor first, then calls `vmt−4` `Destroy` on the
combat object) and leaves untouched only the off-map party's objects (`party[+0xC] == -1`, exactly
what `AddArmyEx`'s `(-1,-1,-1)` produces). This was discovered the hard way in the Arena rework (§5):
a first implementation tried to award XP by walking `combat[+0xC]`'s combat data after the run — gold
worked, XP silently did nothing, because by the time that code ran every one of the player's own
combat objects had already been freed; only the hidden militia's objects (off-map) were still alive.
**Post-combat work on the player's own units must go through the strategic army list** (e.g.
`army[+0x1C]` + `vmt+0x54`/`TUnitList.GetUnit`), never through the combat-data proxy objects, once
`Finalize` has run. This is also *why* vanilla `TExplorationSite.CombatExecuted` only ever touches
`GetPlayer()==0` objects when re-homing survivors — that reads like a thematic filter and is actually
a lifetime constraint: those are the only objects still alive at that point.

**⚠ The action-stream autocombat trap.** Auto-resolved combat replays from a recorded action stream —
`AddAction`/`TCombat.ExecuteCombatAction@0x55727224` is the point every real combat action (a strike,
a cast, a death) is appended to that stream, and the replay transport (§4.4.10) drives entirely off
it. **A cave that pokes a unit's HP or state directly, bypassing this stream, is invisible to the
replay** — the live outcome is correct but the recorded battle silently doesn't show why. Audited
2026-09-02 against every cave in this cluster: nothing currently shipped writes HP or unit state
without going through a real combat action, so nothing here is affected — but it is a standing
constraint for the *next* auto-resolve-adjacent feature, and worth checking explicitly before any
cave writes combat state directly rather than through `TCombat`'s own action machinery.

### 4.8 City raze + rebellion design notes — status corrected

The source document's own header called this whole area **"DESIGN — nothing applied,"**
which was already wrong when written (its own body records two patches applied-untested that same
day) and is now wrong on a much larger scale: essentially everything that document designed — city
raze as a real battle, rebellion as a real battle, loot as a real battle — has since been built and
applied as Stages 9/10/Part C above (§4.4.6–§4.4.8). The one design element from that document that
remains genuinely undecided is the day-variation question for the city roster's seed, which §4.4.6
resolved (day term added); its other open questions (rebellion participants beyond the main-hex
garrison; whether a crushed rebellion should carry a loyalty consequence) were never explicitly ruled
on and are carried into Open items below.

---

## 5. The Arena rework

Vanilla Arena: park an army on the hex, double-click, get a training dialog listing your ≤8 units;
ticking units and pressing Select pays gold and instantly promotes each ticked unit to its next medal.
The rework replaces this outright: the Arena becomes a place that stocks a **hidden independent
militia** in one of three tiers (weak/medium/strong), empties when fought, restocks with ~10%/day
odds, and pays flat gold + XP + (strong-tier) an item on a win. Unit training is **abolished**, not
kept alongside — every training-path function becomes dead code once the battle path is live.

`TArena` is the thinnest structure subclass in the game — VMT `0x557D6240`, instance size `0x30`,
**identical to its parent `TStructure`**, adding no fields of its own; whole feature footprint before
this rework was ~3.7 KB of code. Byte-diffed against the pristine backup: exactly **one** pre-existing
byte differs (`0x557D673A`, a rank-3 clamp from an earlier medal-tier insertion) — the Arena was
otherwise untouched vanilla going in.

**The decisive precedent this rework transplants wholesale**: `TExplorationSite`'s hidden-army/
real-combat/completion-callback pattern (§4.4.1) is already confirmed working via
`build_razebattle_tower.py`, so nothing about "a structure running a real battle" needed re-deriving —
only the Arena-specific state (empty/seeded flags, roster tiers, reward tables) and UI were new.

### 5.1 Design decisions locked before the build (2026-07-30)

| # | question | decision |
|---|---|---|
| 1 | reward shape | flat per tier: +100/200/300 gold, +5/10/15 XP to every survivor |
| 2 | gold on a loss? | no — win only, gated on `combat[+0x14] ∈ {3,6}` |
| 3 | combat mode | tactical, with the §4.5-equivalent hardening contract (not yet built — §5.4) |
| 4 | refill cadence | `NewDay`, once per game day, 10% |
| 5 | keep unit training? | no — abolished, freeing all 8 checkboxes and the existing TE command |
| 6 | roster source | a hardcoded index table in the build script, no `Release.hss` dependency |

Choosing flat rewards over per-kill gold/XP deleted the single riskiest item in the original plan —
rewriting another feature's existing kill-XP cave (`cave_5580C390`, hooked from
`TCombatObject.DoDamage`) — entirely; the flat design does everything in one place, the combat
completion point.

### 5.2 As built — Stages 1–3, ✅ CONFIRMED WORKING (2026-07-31)

**Stage 1 — persistent state.** Two new fields (instance size `0x30`→`0x38`): `arena[+0x30]` byte
(bit0 `EMPTY`, bit1 `SEEDED`), `arena[+0x34]` dword (roster seed). New property ids `0x70`/`0x71`
(collision-scanned clear against the whole `TArena` inheritance chain first). Old saves simply lack
the ids and the zero-init default reads as "stocked, unseeded" — correct for free, no `Create`
override needed. `cave_newday` (VMT `+0x174`, was a bare `ret`) seeds an unseeded arena and, if empty,
rolls `TAoWHSMap.Random(map,10)==0` to restock with a fresh seed — the MP-safe RNG, same call the
vanilla item roller uses.

**Stage 2 — the battle, fast-only, one hard-coded tier.** `TArena.UnitTrainCost` becomes
`xor eax,eax; ret` (every unit reports training cost 0), which — through entirely vanilla downstream
logic — makes every checkbox enable and the existing Select button drive a real battle with **zero
`AoWz.exe` changes**: `TArena.ExecuteTE` is hooked to build a `TDefendersArmy` from a hardcoded roster
table, run a synchronous fast `TCombat` (transplanted verbatim from the confirmed `cave_towerraze`
sequence), and set `EMPTY` afterward. Wall-less (party flag cleared on `AddArmy`, the same trick raze
battles use) — kept deliberately even though the reward walk in Stage 3 no longer needs it, because it
is exactly what avoided the `TCombatWall`/`+0x4C` alias that had already frozen the game twice
elsewhere (§4.6.2).

**Stage 3 — rewards, in the callback-free fast path directly.** ⚠ **The one real defect found and
fixed here: XP must come from the strategic army list, never from combat data.** The first
implementation walked `combat[+0xC]` after the run, filtering on `IsClass(TCombatUnit)` +
`GetPlayer()`; gold worked, XP silently did nothing — root-caused to exactly the combat-object-lifetime
rule in §4.7: by the time this code ran, `TCombatUnit.Finalize` had already freed every one of the
player's own combat objects. Re-fetching the visiting army from the arena's field and walking its
`TUnitList` directly fixed it, and — because vanilla's own `SetExperience` virtual slot drives the
rank-up path — awarding XP that way (never a raw field write) is also what makes it actually produce a
medal. Item drop (strong tier, win only) reuses `TItemControl.GenerateItem` verbatim — it turned out
not to *construct* an item at all, only pick one from the existing unplaced pool, so `PlaceOnMap` alone
completes the award with no ownership fix-up.

### 5.3 As built — Stage 4a/4b, dialog, empty-state — 🔨 APPLIED, UNTESTED (2026-07-31 / 2026-08-02)

**Stage 4a — three selectable categories, zero `AoWz.exe` code changes.** `TArenaDlg.U1Change` is one
shared handler for all eight vanilla checkboxes; owning the three DLL exports it calls
(`SetSelection`/`Train`/`CanTrain`/`GetSelectionInfo`, plus setting the "trainable" mask before Show)
owns the whole interaction. `SetSelection` becomes a **radio**: a newly-set bit keeps only its lowest
set bit (`x & -x`), so ticking one category automatically unticks the others without touching the exe.
The old training-command TE field (`TE[+0x18]==1`) is reused for the battle command, nibble-packed
with the category — the same packing convention the raze rework uses (§4.4.7).

**Stage 4b — box artwork, DPL-only.** The vanilla box painter draws a real `TUnit`'s sprite
(`vmt+0x1A4` `ShowEx`), not an image-library index — `cave_avail` builds one throwaway `TUnit` per
category via the same `Create`+`SetUnitResource` pair `FillWithRandomUnits` itself uses, and stores
the raw pointers directly in the event log so the painter's normal `GetUnit` returns them.
`TAbstractUnit.ShowEx` was checked to do no player/map-field dereference, so an unregistered throwaway
unit renders safely.

⚠ **Bug found and fixed here: a rejoining hook must resume *past* its own displaced bytes, not into
them.** In-game crash on pressing Train: `Arena.TEnterArenaEventLog.Destroy+0x6`. The hook displaced 5
bytes but the function's 4th instruction *ends* mid-way through byte 5 — so the cave's resume address
landed **inside its own `E9`'s relative-offset operand**, making the cave jump into its own jump and
run garbage as code with a wrecked register. Fixed by displacing 6 bytes instead of 5 (covering the
whole 4th instruction) and replaying all four prologue instructions before resuming past them. The
script now asserts this for every rejoining hook it installs: the resume address must never fall
inside the range it just displaced.

**Empty state.** `TArena` VMT `+0x12C` (`GetTerrainTypeImage`) gets a cave keyed on the `EMPTY` bit
that looks up an alternate image sequence at `base index + 100` (the general engine convention for
"alternate look," confirmed from `TExplorationSite`'s identical idiom) and **falls through to
`TStructure`'s own implementation** when none exists — deliberately better than the exploration-site
version, which loses its razed/under-construction imagery entirely. This is a no-op today (no art
exists yet at `+100`) by design — the slot is ready and needs no rebuild once art is added. A second
cave on `TArena.Enter` shows a "the arena is empty" notification and returns without opening the
dialog at all when fought out.

**A pre-existing engine defect, diagnosed here but not caused by the Arena — CONFIRMED FIXED
2026-07-30.** The Arena's first battle triggered the *same* replay assertion documented in §4.4.10
(`build_enchant_assert.py`) — this is where that fix was actually discovered, since the Arena's
militia is another instance of the identical hidden/never-activated-defender pattern. Confirmed
generic (not Arena-specific) by reproducing the identical assert on a guarded exploration site's
replay before the fix, and confirming the same one-byte fix resolves both.

**Dialog re-layout — `build_arenadlg.py`, `AoWz.exe` + `AoWzCompat.exe` lockstep.** Reuses the
`HeroUpgradeDlg`-style in-place DFM edit recipe verbatim (imported functions, not copied): the dialog
grows 328→420 px tall, the eight checkboxes collapse to three labelled rows (`U4..U8` hidden), the
info panel moves beside the column and switches to left-aligned multi-line text, captions become
"Fight in the Arena" / "Fight". Byte-budget-neutral (a DFM resource cannot grow in place — the next
resource starts immediately after it) via 122 B freed from deleting designer-only properties
(root `Left`/`Top`/`Height`/`Width`, a non-visual component's design-time position, the five hidden
checkboxes' `Left`/`Top`) against ~50 B spent on `Visible=False` flags and three `Int8`→`Int16`
promotions crossing 127.

⚠ **`TAOWLabel` is strictly single-line — an earlier note claiming otherwise was wrong and has been
corrected here rather than repeated.** The claim rested on `ImageLib.ParseFontText`, which really does
split on CR/LF/space — but has **zero callers anywhere in the code section**; it is dead code. The
renderer actually reached (`TAOWLabel.Draw`) is a per-character loop that indexes a glyph table by
byte value and silently **skips** any byte with no glyph, CR and LF included — so a CRLF-joined
three-line string draws as one long line that runs off the panel edge. To show all three category
offers at once needs three real label controls (a DFM resource relocation, not attempted here); the
one label that does exist (`SelectionInfoLbl`) is kept to a single wrapped block instead, and its
strings were shortened to fit the panel after a first in-game screenshot showed both clipping (a
90-character line was rendered as roughly 76) and boxes drawing the *player's own* units before
Stage 4b's dedicated throwaway units were added.

### 5.4 Five traps worth carrying into any future structure-battle or dialog feature

1. **Hook-resume-inside-its-own-jump** (§5.3) — a rejoining hook's resume address must be checked
   against the *actual* instruction boundaries of what it displaced, not assumed from the displacement
   byte count; `build_arena.py` now asserts this for every such hook it installs.
2. **`TAOWLabel` is single-line** (§5.3) — `ParseFontText`'s multi-line support is dead code; only a
   real second/third label control shows a second line, never an embedded CR/LF.
3. **Cave relocation breaking hook verification, and the design that avoids it.** A cave whose
   internal stub addresses move when it grows (because it was rebuilt bigger) will fail a verifier
   that expects an exact byte match against a frozen prior image — the classic way a feature becomes
   *orphaned* (un-re-appliable without a full revert). This exact failure mode cost weeks on a
   different cave in `07-ui.md`'s combat-log feature. `build_arena.py` was built with that lesson
   already applied: it recognises "this is my own prior build" by checking that all of its hook sites
   already point where it expects, rather than by comparing a cave's bytes to a frozen snapshot — so
   every retune (roster tables, budgets, rewards) is a plain re-run, never a revert-then-reapply.
4. **The keystone `push 0xFFFF` imm8 trap, hit and fixed here.** `push 0xFFFF` assembles as the 2-byte
   `6A FF` — `push imm8 −1` (`0xFFFFFFFF`) — not the intended 5-byte `68 FF FF 00 00`. As
   `GenerateItem`'s value-cap argument this would have rejected every candidate item and silently
   awarded nothing. Fixed by routing the value through a register instead of an immediate, with the
   build asserting the encoding; a full sweep of every `build_*.py` in the tree at the time found no
   other script pushing a >imm8 literal that keystone would silently truncate this way.
5. **A reward loop must know which combat-object lifetime rule applies to it** (§5.2's XP bug, fully
   explained in §4.7) — walking `combat[+0xC]` after `Finalize` only ever sees the *off-map* side; a
   reward for the player's own units must go through the strategic army list instead.

### 5.5 Still open / not built

Tactical arena combat (design element locked in §5.1 but not built — needs the exact §4.5 hardening
contract copied, since a naive transplant of `TExplorationSite.Search`'s dialog-raising pattern is the
one that caused §4.5's freeze in the first place); whether the AI should ever use arenas (blocked on
the same `TStructure.ExecuteAI` stub §1.1 discusses, now closed for exploration sites but not for the
Arena); two overlapping sprites per box (needs a second painter call plus a six-entry display list);
the two remaining dialog captions ("Select Unit(s) to Train"/"Train" — cosmetic only, since Stage 4a
already changed the functional behaviour behind them) live in `Dict/AoW.mld`, a data-file change with
no binary patch.

---

## 6. Shipyard water income — ✅ CONFIRMED WORKING (2026-08-26), both halves · 🔨 v2 MAX_LEVELS=4 re-tune APPLIED, UNTESTED (2026-09-06)

A shipyard produces **1 gold per 5 hexes** of contiguously adjacent water (`HEXES_PER_GOLD`, a single
named constant; shipped at 10, halved to 5 the same day at the user's request — one byte,
`0x55822102` `0A`→`05`), divided between every un-razed, fully-built shipyard adjoining that body.
Razed and under-construction shipyards are excluded entirely from both the divisor and the payout;
independent/unflagged shipyards **dilute the pot but collect nothing** — ruled deliberate, not a bug
to "fix" in the cave. A shipyard touching more than one distinct water body gathers a divided share
from **each** one it touches.

```
pot(region)   = area(region) div HEXES_PER_GOLD
share         = pot div N                              (N = qualifying shipyards on the body)
income(yard)  = SUM over every distinct region the yard touches of that region's share
```

### 6.1 Why this was cheap: the whole income pipeline already existed

`Shipyard.TShipyard.GetBaseIncome@0x557C75D0` is literally `xor eax,eax; ret` — byte-identical in
live and pristine, referenced from nowhere but its own VMT slot. Every shipyard already owns a
registered `TPlayerStructureIncomeSource` (`TProductionPlace.Create` builds one because
`GetMagicSphere()` returns 8, unconditionally, unrelated to the zeroed income), so a non-zero return
reaches the treasury with no other patch: `GetIncome → GetBaseIncome → income source → UpdateIncome →
NewTurn → SetGems`.

### 6.2 ⭐ Hook `GetIncome` (`+0x1F4`), never `GetBaseIncome` (`+0x22C`) — the reusable diagnostic

**The single most important finding of the whole feature, and it is counter-intuitive.** Making
`GetBaseIncome` non-zero is *not* display-inert — a byte-sweep for every `call [reg+0x22C]` across all
five modules found consumers that change real **gameplay**, not just display: `AoW.exe` adds a live
"Merchandise" item to the shipyard's production queue on any non-zero base income, enables a
production-screen control, flips the Realm-window activity column to "Producing Merchandise", and
opens a latent nil-dereference in `ListIncomeInfo`'s gate. Repointing `GetIncome` (`+0x1F4`) instead
and leaving `GetBaseIncome` (`+0x22C`) at its vanilla zero switches all of that off at once, because
every one of those sites reads `+0x22C` specifically. It also incidentally replaces
`TProductionPlace.GetIncome`'s own `+25%`-when-idle branch outright — the reason the shown number is
stable instead of visibly dropping when a shipyard starts building a ship.

**The apparent cost of this choice was not actually a cost.** `AoW.exe`'s map structure-info panel
*gates* the gold row on `GetBaseIncome` but *prints* `GetIncome` — the gate and the value it protects
read two different virtuals. Read naively, this looks like an accepted trade-off (a hidden gold row);
the actually-correct fix is to **move the gate onto the value it already prints** (§6.4) — strictly
more correct than vanilla, not a compromise. **⭐ Generalise this:** before concluding a UI surface
"can't show" a computed value, check whether it gates on a *different* virtual than the one it
displays — the two are not guaranteed to be the same slot, and the gate is very often the one that's
wrong.

### 6.3 What counts as water, and the algorithm

Water is terrain `[field+0x14] ∈ {0x00, 0x0A}` **exactly** (the shipyard's own placement rule,
`TShipyardConstructionControl.ValidateLocation`) — overlay ignored, so a bridged water hex still
counts. ⚠ **Never use the historical "water family" `{0, 6, 0x0A, 0x0E}`** — on this install terrain
`0x0E` is **Sky** and `0x0B` is **Chasm** (`09-terrain-movement.md`), so a naive fill would count
flying-only Sky hexes as ocean; Ice (`6`) is explicitly not water by the shipyard's own rule.

Adjacency is the shipyard's own hex plus its six neighbours — the same 7-hex set
`ValidateLocation` itself validates — which sidesteps a genuine gap: a structure's true footprint hex
count is **not present in the binary** at all (it lives in `Release/Release.hss`, only read for the
placed instance); using the fixed 7-hex ring means a wider true footprint only ever causes
*under-collection*, never mis-payment, and needs no `.hss` read.

**Algorithm, keyed on the day counter (`map[+0x174]`), not recomputed per call:** naive
recompute-per-`Income()`-call is catastrophic — map load alone would perform on the order of
`Σ S(S+1)/2` calls per player. A two-tier cache instead: **tier 1** is one BFS flood-fill labelling
pass per game day (an iterative queue, never recursion — a recursive fill over a 127×127 map would
overflow the Delphi stack), keyed on `(map ptr, day, level count, level dimensions)`; **tier 2** is a
per-region shipyard count over a *cached* shipyard sub-list, refreshed whenever the registry's count
moves — but the membership bytes (`razed`/`building`/`owner`) are **re-read on every evaluation**, so
completion and razing take effect immediately rather than waiting a day. ⚠ **The structure registry's
own count is not a valid "has anything changed?" key on its own** — `TStructure.BuildingDone` (a
shipyard finishing construction) clears the builder byte without touching the registry at all, so a
registry-count-only cache key misses exactly the transition that matters most; this cost a real
over-payment bug during the build, fixed by re-reading the membership bytes unconditionally.

**Memory:** BSS page slack is far too small for a per-hex label array on a 127×127 map (16 KB+ on its
own against ~3.5 KB of slack) — the cave uses the Delphi heap instead (module-local `@GetMem`/
`@FreeMem`/`@ReallocMem`/`@FillChar` thunks), allocating and freeing per pass, leaving only a small
fixed header in BSS.

### 6.4 Display half — `build_shipyard_income_display.py`, `AoWz.exe`+`AoWzCompat.exe`, ✅ CONFIRMED WORKING

⚠⚠ **A dry run of this script reports `FAILED pre-checks -- nothing written`, and that is a FALSE
NEGATIVE, not a broken feature.** Both exes print `mixed  .syd present but nsec=12`. The feature is
fully installed; the *check* is stale. `state()` asserts `nsec == EXP_NSEC + 1`, written when `.syd`
was the 11th and last PE section. `build_unitwin_party_arrows.py` has since appended a 12th, `.pyar`
@ VA `0x0062F000`, *after* `.syd`, so the count no longer matches. Live section list, measured
2026-09-10: `CODE DATA BSS .idata .reloc .rsrc .sc .clog .tres .hcol .syd .pyar` — vanilla has the
first six only. ⚠ Do not "fix" this by running `--apply`; it will not write while the check fails,
and the feature needs no re-apply. The script's own docstring §"CROSS-SCRIPT COUPLING" carries the
full ordering rule (undo `.syd` **first** if either `.tres` or `.hcol` is ever rebuilt).

**Map structure-info panel (4 bytes).** Repoints the gate's own displacement from `0x22C` to `0x1F4`
at `0x004438A0` only — `FF 92 2C 02 00 00` → `FF 92 F4 01 00 00`. Three *other* `call [reg+0x22C]`
sites look identical and are explicitly left alone, each independently verified as something else
entirely by the same offset-aliasing pattern: an activity-caption if/else (would make every earning
shipyard read "Producing Merchandise"), the production-screen queue-item creator (§6.2), and — on
`TAltar`, a completely different class reached through the same dispatcher — `+0x22C` is
`GetRechargeDays`, not an income base at all. **Blast radius, verified narrow:** the dispatcher only
reaches this function for `TProductionPlace` descendants with `GetMagicSphere()==8`, which is exactly
`TProductionPlace`/`TShipyard`/`TBuildersGuild`/`TRandomNode` — and for the latter three,
`GetIncome==0` exactly when `GetBaseIncome==0` (the `+25%` term vanishes at base 0), so the edit is
provably inert for them; only `TShipyard`'s behaviour actually changes.

**Realm window (a genuinely new sixth row, "Shipyards").** The five vanilla income rows are an
identical five-call sequence repeated by hand; a sixth needs no geometry work, since both string-list
controls are simply `.Add`ed to. Everything needed (`GetStructure`, `GetPlayers`, `TranslateRStr`,
`IntToStr`) is already imported by `AoWz.exe` — **no new import was added**, deliberately: the vanilla
row label constant (`AoWE.ShipyardRStr`) is not among `AoWz.exe`'s 1,625 imported AoWEPACK symbols, so
the label is instead a literal Delphi AnsiString built in a new PE section and fed to `TranslateRStr`
(which accepts a plain AnsiString, not just a resource record) — it therefore stays dictionary-
translatable via the normal `Dict/ResStr.txt` path with no import-table surgery, following this
project's standing refusal to touch that table for a label ("fragile table surgery"). ⚠ **One
capacity risk flagged for future attention, not yet hit:** the values list control (`IncomeValue`) is
one row shorter than the labels list at designer size and has no scrollbar — today's function writes
at most five rows, so this new sixth row is the first thing that can ever overflow it; the lever if it
ever does is a one-byte DFM property (`BorderHeight` 4→1).

### 6.5 A recorded failed approach: any terrain-changed funnel

An earlier, unrelated feature (`build_los_terrain.py` v1) tried hooking `TAoWHSMap`'s
`TriggerTerrainChangedEvent` slot as a general "terrain changed" notification and produced
**unbounded recursion** — `MapChanged` calls that slot, `InvalidateMap` calls `MapChanged` per level,
and visibility updates end in `InvalidateMap`, so the hook re-entered itself and froze the editor on
map open. **AoWEPACK has no terrain-change-only notification; do not re-derive one from this slot.**
Recorded here because the shipyard feature shares the same terrain-adjacent cave neighbourhood and the
same author considered and rejected the identical shortcut for its own cache-invalidation needs
(landing on the day-counter key in §6.3 instead).

### 6.6 v2 re-tune — `MAX_LEVELS = 4` for the Firmament map level — 🔨 APPLIED, UNTESTED (2026-09-06)

In-place cave rewrite, not a revert-and-reapply: the entry guard and the three `build_t1` loop
bounds now read `cmp edx, 4` at `0x55822174` / `0x55822390` / `0x558224C4` / `0x55822540`, and the
per-level BSS header re-lays to hold four slots instead of three (`HDR_END` now `0x558FAB78`, 120 B
of the `0x80` window — see `11-engine-internals.md` §"The two in-place cave re-tunes" for the full
field-by-field shift; not duplicated here). Cave length unchanged. Each iteration still re-gates on
the map's own live level count, so a 3-level map's fourth slot is written zero with no
`GetMapLevel` call, and a map with fewer than 4 levels is unaffected.

**In-game check (needs the user):** on a 4-level map, income from water on every level is counted
(a Firmament lake must not merge with a surface one); on a 3-level map, shipyard income is unchanged from
before this re-tune.

---

## 7. AI combat-spell anti-spam — Terror capped at one cast per combat, per side

### 7.1 The two combat contexts — the reusable finding behind every AI combat-spell mod

AoW1 scores and casts combat spells through **two completely separate paths**, with different value
methods, different cast points, and different "drop this candidate" rules. A hook that works in one
never fires in the other, and this split is the entire difficulty of any mod in this family:

| | value path | cast point | "drop this candidate" rule |
|---|---|---|---|
| **Tactical** (player watches) | VMT `+0x88` `tcGetDamageValueEx` | the spell's dedicated tactical CA's `Execute`, or (for spells without one) `TSpell.CombatCastingDone@0x557794E8` + a VMT-identity check | driver picks the single **highest-priority** action — shrinking the score is enough |
| **Fast/auto-resolve** | `fcPrefetchCombatCommands` (VMT `+0x90`) | the spell's `fcExecuteCombatCommand` (VMT `+0x94`) | a queued command is dropped **only at value exactly 0** — any value ≥1 stays queued and can still win if nothing better is available |

Terror is one of the few spells with a **dedicated CA in both modes**
(`TTacticalCombatTerrorCA`/`TFastCombatTerrorCA`), so it needs none of the harder generic-CA
machinery — spells that inherit `TCombatSpellCA`/`TExclusiveCombatSpellCA`/`TMultiTargetCombatSpellCA`
(Ooze, Slow/Hunter's Mark) do, and are the hard case a third-party build previously solved (§7.4).

⚠ **`TTerror.fcGetDamageValueEx` (VMT `+0x98`) is DEAD CODE for Terror — do not gate it.** Terror
*does* override this slot, and the slot carries a `.reloc` entry, so it looks like a perfect gate — it
is simply never called: `fcPrefetchCombatCommands` accumulates the value **inline** into a register
and tests that directly, never dispatching through `+0x98` at all (verified: zero direct references
and exactly one absolute reference — its own VMT slot — anywhere in the module). **A wrapper on `+0x98`
would assemble, verify, disassemble cleanly, byte-check clean, and do nothing.** ⭐ Generalise this:
*a spell overriding a value method is not evidence that the value method is on the path* — always
check the caller before gating a virtual.

⚠ **Terror's VMT base is `0x557F61D4`, not `0x557F61D8`.** Slot arithmetic from an assumed base
silently renames every slot by one; the DLL's own export table settles it unambiguously — the
`..Class` symbol *is* the VMT base, confirmed here by every neighbouring slot resolving to its
documented name once the correct base is used. **Never derive a VMT base by subtracting an assumed
slot offset.**

### 7.2 `build_terror_oncepercombat.py` — 🔨 APPLIED, UNTESTED (2026-08-31, v2 per-side)

A per-**side** BSS flag array, `F_SIDE = 0x558FAC00` (4 bytes, indexed by combat side), five sites:

| # | site | role |
|---|---|---|
| 1 | `TCombat.Create@0x5572708C` | `F_SIDE[0..3] = 0` — resets once per battle |
| 2 | `TTacticalCombatTerrorCA.Execute+0x12@0x557F991E` | `F_SIDE[side(target)] = 1` |
| 3 | `TTerror.fcExecuteCombatCommand@0x557F9BE8` | `F_SIDE[side(actor)] = 1` |
| 4 | VMT `+0x88` slot (tactical value) | wraps the original: if flagged, `value = max(1, value>>6)` |
| 5 | `TTerror.fcPrefetchCombatCommands@0x557F9B20` | if flagged, returns immediately — no Terror command is ever queued |

**The side index has no dedicated accessor — `TCombatObject.GetOpponentSide@0x55726688` is the whole
story:** reads the object's player slot, maps it through `player[+0x0A]` (proven to be exactly `{0,1}`
by the accessor's own `XOR 1`), with `2` as the no-owner escape (masked safely into the 4-byte flag
array regardless). It returns in `AL` only and preserves `EBX`/`ESI`/`EDI`/`EBP` — every cave here is
built around that preservation. Each site derives the **casting** side from whichever object it
actually has in hand: the two tactical sites use `GetOpponentSide(target)` (the caster is not directly
reachable from `tcGetDamageValueEx`, but the target's opponent side *is* the caster's side), the two
fast sites use `GetOpponentSide(actor) ^ 1`. Each mode is internally self-consistent, which is all that
is required — a battle is either watched or auto-resolved, never both, and the flags reset every
`TCombat.Create`.

**Why the tactical set-site sits `+0x12` into the function, not at its entry:** the function's
prologue has no side information available at all; the hook instead sits after the two instructions
that already resolve the target object for an unrelated purpose, so the cave gets the target for free
and — because the whole block runs inside vanilla's own "did the cast actually land" guard — the flag
is set **only when Terror actually connects**, not on every invocation.

**Does the cap apply to a human player?** Tactical: no — the human casts through the UI, never through
the AI's `tcGetDamageValueEx` scorer, so the tactical gate cannot reach them (though the tactical
*set*-site does still flag the human's side when they cast, it simply has no consumer there). Fast/
auto-resolve: **yes** — auto-resolve drives both sides through the identical AI cast path
(`TFastCombat.Execute → TSpellCastingAbility.fcPrefetchCombatCommands/fcExecuteCombatCommand →` the
spell's own VMT slots), so a human auto-resolving their own battle is capped exactly like an AI. This
is a deliberate, recorded asymmetry, not an oversight: auto-resolving a battle now costs Terror casts
you would have had fighting it manually. (Vanilla already partially gates a human here on its own —
`fcPrefetchCombatCommands` skips a human hero entirely while they are mid-channelling a strategic
spell — and wherever vanilla already lets a human through, this cap now applies on top.)

Every address here was **re-picked from scratch**, not reused from the confirmed third-party build
this design is based on (§7.4) — three of its addresses would have silently destroyed live features on
this install (`0x558FAF20` collides with `build_shipyard_income.py`'s BSS header; its shared reset cave
region overlaps three already-occupied caves here). `F_SIDE`, and the caves at `0x5582A000+`, were
verified clear of every address any `build_*.py` in this tree claims before being used.

**Test checklist:** tactical combat — AI casts Terror at most once per battle, twice only if it is that
side's *only* combat spell (the deliberate floor-1 behaviour); auto-resolve — hard-capped at once;
cast Terror yourself then confirm the AI can *still* cast its own once in that same battle (proves the
side index isn't collapsing to one slot); a second battle the same turn resets the cap
(`TCombat.Create` fired again); auto-resolving your own battle twice shows the intended asymmetry
(capped there too — confirm it reads as intended, not a bug); no regression to other AI combat spells.
**Revert:** `--undo` (surgical; restores all four hook sites and the VMT slot, zeroes the five caves,
touches no backup; round-trips byte-identical to the pre-feature backup).

### 7.3 Tuning knobs

Deprioritise strength: `shr eax,6` (÷64) in the tactical wrapper. To extend the pattern to another
spell: reset its flag in the shared `TCombat.Create` cave, set it at that spell's cast point (its own
tactical CA `Execute`, or `CombatCastingDone` with a VMT-identity check if it uses a generic CA), and
wrap its `+0x84`/`+0x98`-equivalent value slot (checking first, per §7.1, that the slot is actually on
the path before wrapping it).

### 7.4 AI combat-spell anti-spam — reference only, a confirmed third-party build, nothing applied here

A fellow modder's confirmed-working build covering **four** spells (Turn Undead, Terror, Slow/Hunter's
Mark, Ooze) with the identical two-context architecture described in §7.1 — kept as an exact-byte RE
reference, not as a feature record: there is no build script for it here and none of its addresses are
applied to this install. **Every one of its cave/flag addresses collides with a live feature on this
install** (`0x558FAF20/21/22` with `build_shipyard_income.py`'s BSS header; its shared caves with
already-occupied blocks) — re-pick before ever reusing anything from it.

Two findings from that reference are worth keeping as reusable technique, distinct from Terror's own
(much simpler) case: **Ooze needed ~10 iterations** because a `÷64`-floor-1 value shrink is not enough
for a spell scored through the fast-combat *command* driver (a command is dropped only at value
*exactly* 0, unlike Terror's highest-priority-wins driver, so Ooze's fast-combat gate must **force**
the value to 0, not merely shrink it), and because Ooze's tactical cast never touches any of the
spell-specific VMT slots a naive hook would try first — only `TSpell.CombatCastingDone`, downstream of
the *generic* CA path, ever fires for it. The diagnostic that cracked both cases: **repoint a candidate
value method to return an unconditional 0 and see whether the spell stops casting entirely** — if it
does, that method really is the control point, which is worth proving *before* hunting for the harder
cast-point hook.

---

## 8. Diagnostic tooling — `build_combatdiag.py` and `build_razediag.py`

⚠⚠ **A diagnostic that changes game behaviour is not a diagnostic — give it a status row.**
`build_razediag.py`'s `--want-open` lever sat live in the shipping DLL for two months and made the AI
raze friendly and own-race cities (§3.6). It survived because it had no row here, no row in
`00-INDEX.md`, and no mention anywhere in `Zig notes/` outside its own source. Both scripts below are
now listed in this file's status table; **check both before any playtest.**

| script | live state (2026-09-11) | how to check |
|---|---|---|
| `build_razediag.py` | all three levers **STOCK** | `python build_razediag.py` (no args = dry report) |
| `build_combatdiag.py` | **not installed** | `python build_combatdiag.py` (no args) |

⚠ `build_combatdiag.py` can no longer be re-applied as written: its cave zone starts at `0x55810400`
and `build_effectroll_tacticalgate.py` now owns `0x55810500..0x5581052A` inside it. A dry run reports
`MISMATCH cave @ 55810400` and aborts, which is the **correct** output, not a broken state — relocate
the cave rather than relaxing the check.

### 8.1 `build_combatdiag.py`

An additive, `--revert`-able file-logging probe built specifically to chase the freezes in §4.5–§4.6 —
not a gameplay feature, and it changes no game behaviour on its own. Three entry hooks
(`CreateCombat`, `DestroyCombat`, `TStructure.Raze`) plus, at various points in the investigation,
temporary hooks on `TCombat.UpdateStatus` and the fast-combat lifecycle, each writing one line to
`Save\razediag.log`, **opened, appended and closed per line** so every record survives killing a frozen
process outright — the freezes under investigation left the combat-log window and the normal ring
buffer unreadable exactly when they mattered. Cave at `0x55810400`; BSS scratch at `0x558FA900`
(chosen above every claimed flag from this cluster). It was this tool's own BSS-dump revision that
found the `simfly`/`razeok` collision in §4.6.1 — a static-analysis dead end until the tool showed the
flag byte holding map coordinates instead of a flag value.

**Live state, measured 2026-09-11: NOT installed.** Its cave zone is zero apart from
`build_effectroll_tacticalgate.py`'s `0x55810500` cave, and the script's own dry run aborts on that
collision before reporting hook state (see the warning above).

---

## 9. The tactical-combat AI's pause between moves — a one-unit-per-frame budget

✅ **CONFIRMED WORKING (2026-09-12)** — `build_combat_ai_budget.py`, `Ziggurat\AoWTCPCK.dpl`,
two imm8 bytes, snapshot `backups\AoWTCPCK.dpl.pre-aibudget`, surgical `--undo`.
Owner's in-game test: **0.5 s+ of the ~0.7 s inter-move stall is gone**, no stutter, no change in
how the AI plays.

⭐ **The ~0.2 s residue is this knob's floor, and it is frame-rate bound.** States 3, 4, 5 and 0 each
cost exactly one frame *per action* whatever the budget is, so ≈4 × 33.3 ms is structural at
`FrameRate` 30. Going below it means the frame clock itself (§9.4), which is a global pace change.

### 9.1 What was measured, not guessed

The owner reported a small pause between each AI move in manual combat that "adds up across a few
dozen units". A read-only probe of a live AI turn (184 Hz sampling of the token executer, the `TCAI`
state and the display's own measured-fps field, via `ReadProcessMemory`; no patching, no debugger)
accounted for **42.6 s of one AI combat turn**:

| phase | n | median | total | share |
|---|---|---|---|---|
| **`EvalBattle` state 1 — token queue EMPTY, nothing animating** | 32 | **692 ms** | 21.2 s | **50 %** |
| `TCAbRangedTE` running (real animation) | 13 | 958 ms | 12.7 s | 30 % |
| `TCombatMoveTE` running (real animation) | 17 | 263 ms | 4.3 s | 10 % |
| `EvalBattle` states 3, 4, 5, 0 (one frame each) | 31 each | 33 ms | 4.4 s | 10 % |

Measured display fps was pinned at **30** (min 29, max 31) ⇒ **33.3 ms per frame**.

### 9.2 The mechanism

`AoWTC.TCAI.EvalBattle @0x418170` is a resumable state machine on `cai[+0x1c]` (jump table
`0x4181DB`), entered once per rendered frame from `TAoWCombatMap.NewFrame @0x41C440` via
`TCAI.ContinueTurn @0x4135A4` (both `BeginTurn` and `ContinueTurn` are one-line wrappers on it).

⚠ **The observed ring is `0 → 1 → 3 → 4 → 5 → 0` for EVERY unit action, not once per turn.** State 2
is skipped by the second `add [cai+0x1c],1` at `0x41944C`; state 5 issues one action and then resets
`cai[+0x1c]` to 0 at `0x41AF80`. Reading "state 5 contains no increment" as "state 5 is sticky" is
the wrong inference and was corrected by the live trace.

State 1 scans the combat-object list `cai[+8]`, indexed by `cai[+0x20]`, with `cai[+0x24]` as a
per-frame work counter:

```
0041925C  add dword [cai+0x20], 1     ; i++
0041926A  add dword [cai+0x24], 1     ; budget++
00419289  cmp dword [cai+0x24], 1     ; <-- the knob   (83 78 24 01)
0041928D  jl  0x418AF8                ; under budget -> another unit THIS frame
          ...                          ; else fall through; 0x41950F resets budget to 0
```

Budget starts at 0 (`0x418AB3`) and is reset on the not-finished exit (`0x41950F`), so **exactly one
unit is evaluated per rendered frame**, and the scan restarts for every action. Cost is O(units)
frames per action × O(actions) per turn — **quadratic in army size**, which is why it is invisible in
a skirmish. 692 ms ÷ 33.3 ms ≈ 21 frames ≈ the units in that battle.

### 9.3 The patch

| VA | file off | enc | scan | |
|---|---|---|---|---|
| `0x00419289` | `0x18689` | `83 78 24 01` | state 1 — the 692 ms stall | **→ 16** |
| `0x00419B2C` | `0x18F2C` | `83 78 24 01` | state 2 — same idiom | **→ 16** |
| `0x00419E78` | `0x19278` | `83 78 24 32` | state 3 — **the engine's own 50** | sentinel, never written |

⭐ **The third site is vanilla's own precedent for a larger budget**, and the script reads it as a
sentinel: if it does not decode as 50 the offsets are wrong for this build and the script refuses to
write. The edit is an immediate *inside* an existing instruction, so nothing is displaced — no cave,
no `E9` hook, no `.reloc` hazard, and position-independence is moot. `--budget N` re-tunes in place
from either the stock 1 or any value the script installed (the `83 78 24` opcode anchor proves the
byte). Verified: exactly 2 bytes differ from the snapshot, both sites disassemble as
`cmp dword ptr [eax+0x24], 0x10` with their `jl` targets unchanged, `--apply` is idempotent, and
`--undo` restores a file byte-identical to the snapshot.

**RNG:** the scan calls `TCAI.CheckUnit`, `TSpellControl.GetSpell` and `THero.CanCastSpellInstantly`
and never `TAoWHSMap.Random`, so draws are per-unit, not per-frame — the **draw count is unchanged**
by the budget and lockstep is unaffected (`12-re-toolchain.md` §4.10).

### 9.4 What this ruled out along the way — reusable machinery

- **The AI's gate is not the pause.** `EvalBattle` bails at `0x4181BF` on
  `AoWHSMap[+0x23c].vmt+0x14` = `NetworkE.TTokenManager.PlayerReady @0x55804310` (true only when the
  token-event queue is empty). During every 692 ms stall the probe read the executing flag clear and
  both event lists empty. ⚠ The live object is `TAoWTokenManager`, but its VMT `0x5570CE24` slots are
  plain thunks back to Network.dpl — **it overrides nothing**, so the base implementation is live.
- **Tactical combat reads no clock at all.** `AoWTCPCK.dpl` imports neither `timeGetTime`,
  `GetElapsedMilliSeconds` nor `GetTickCount`, so every combat delay is frame-counted. The frame
  clock is `AoWz.exe`'s main-form DFM `TDisplay.FrameRate` = **30** (property `0x12F8C9`, value byte
  `0x12F8D4`), paced by `DCPACK.dpl!DisplayC.TUpdateFrameThread.Execute @0x55104674` every
  `round(1000/fps) − 2` ms. Raising it is the *second* lever and scales all combat delays
  proportionally — but it speeds the strategic map identically, so it is a global pace change.
  ⚠ The game's frame loop has **no `Sleep(1)`**: `TMainForm.DisplayUpdateFrame @0x452E50` calls
  `Sleep(0)`, and `Sleep(1)` only under `GetDebugMode`, so the editor's 15.6 ms timer-granularity
  problem (`08-editor.md` §1.2) does **not** apply to the game.
- **`Movement Speed` is already at its floor.** Registry `…\Age of Wonders Z\General\Movement Speed`
  = `02` = `mmsTurbo`; `TTacticalCombatUnitHS.GetMoveSteps @0x420738` returns a flat **2** sub-steps
  per hex for Turbo against 6–12 for Normal.
- **Other frame-counted delays, small by comparison:** `tokDelayStrike` (enum
  `CombatTE.TTokenStep`) = 3 frames after a melee round — `TCMeleeMoveTE.NextStrike @0x409AEB` sets
  `[te+0x31]=8`, `[te+0x20]=3`, countdown at `0x409382`; and `Random(3)+4` = 4–6 frames between
  ranged strikes — `TCAbRangedTE @0x40CBAC`, countdown at `0x40CBD0`.
- ⭐ **Probe chains worth reusing.** `AoWHSMap` var `0x558FA040` (AoWEPACK) → `[+0x23c]` manager →
  `[+4]` executer; busy = `[exec+0x24] & 2` (the flag `TTokenExecuter.GetExecutingTokenEvent
  @0x55803E30` tests); lists `[exec+0x10]` active / `[exec+0x50]` pending; completed-event counter
  `[exec+0x18]`. Combat-map global `0x0046C064` (AoWTCPCK) → `[+0x118]` = `TCAI`.
  ⚠⚠ **`TTokenEventList.GetCount @0x5580339C` is `[[[L+8]+8]+8]` — THREE derefs**; stopping at two
  reads the inner `TList` pointer, which is a plausible-looking constant that never changes, so the
  queue reads "always non-empty" and the whole measurement silently inverts. `GetEvent(i)` is
  `[[[[L+8]+8]+4] + 4i]`, which names the running TE class.
  ⚠ The exe IAT slot `0x0045E998` (`DisplayC..TDisplay`) holds **the VMT itself** — Delphi's `..TFoo`
  export *is* the VMT address, so dereferencing it again yields the first virtual method and every
  instance check then fails. Live measured fps is `display[+0x17C]`, written by
  `DisplayC.TDisplayCtrl.NewFrame @0x551045FC`.

---

## Open items

- **AI non-city scorched-earth raze (v6, §3.4): the isolating test was never run.** Re-run the
  engineered scenario with an *undefended* mine (strip its guards) so the razing stack arrives at full
  HP instead of battle-worn. A raze confirms hypothesis (A) (evaluation timing is working as designed
  — the raze question is asked at the stack's weakest moment); no raze still leaves (B) assignment-gap
  and (C) want-gate-miss both live and undistinguished. Only once (A) is confirmed or excluded is v6
  ready to promote past `APPLIED, UNTESTED`.
- **`build_razebattle_tower.py` has no `--undo`** (§4.4.11). A future session that needs to back this
  feature out has to do it by hand across dozens of hook sites, VMT slots and caves — worth adding a
  proper surgical `--undo` before it is ever needed under time pressure, given the size of the manual
  alternative.
- **`TExplorationSite.Search`'s own dialog-raising site remains unguarded** (§4.5.3) — harmless only
  because nothing currently routes an AI into a *manual* search. Any future feature that lets an AI
  reach `Search` in ask/tactical mode must copy §4.5's hardening (request-live check, byte read,
  player-from-event-log, pre-creation participant check), not vanilla's own unguarded pattern.
- **`cave_towerraze` still has no SEH frame** (§4.4.2/§4.4.3(D)) — the exposure is argued vanilla-equal
  today; re-open this if a future, unrelated battle ever raises "Combat already created" after a raze.
- **City Civil Status Patch E was designed but never built** (§4.1): grant the loyalty bonus/"Strong"
  occupation label only when the predictor's `result==3` **and** the garrison side is genuinely
  non-empty, closing the 999-on-empty-roster edge case. Low priority — the everyday sighting this was
  originally chasing has a separate, fully mundane, already-vanilla explanation (wall/upgrade loyalty
  terms), and the empty-roster path itself is only reachable with a degenerate editor-authored race.
- **Two rebellion design questions were never explicitly ruled
  on** (§4.8): whether rebellion battle participants should be the main-hex garrison only or every army
  on the city's footprint, and whether a crushed rebellion should carry any consequence (a loyalty
  boost, a cooldown) beyond the rebels simply being dead.
- **Whether `map[+0x230]` (the persistent roster-RNG state, §2.1) is also consumed by map generation
  itself** was never traced — irrelevant to in-game day-1 roster rolling, but worth knowing before any
  future work touches the map editor's own generation path, since `build_sitedefender_vary.py` and
  `build_razeroster_vary.py` both advance this state more than vanilla did.
- **`build_combatdiag.py` cannot be re-applied as written** (§8) — its cave zone `0x55810400` now
  contains `build_effectroll_tacticalgate.py`'s `0x55810500` cave. Relocate the cave before the next
  time a combat trace is needed; the collision is not discovered until you want the tool.
- **Two unresolved facts from the original AI-item-acquisition investigation, neither blocking
  anything currently shipped:** whether an editor-authored hero's AI-controlled status (§1.1 route R2)
  is decided at game setup or is somehow inherent to the assigned player slot was never verified
  in-game; and the writer of `hero[+0x5D]` bit 0 — the bit that makes `THero.ReadWrite` skip both item
  tags when set — was never located, though it must clear during normal serialization or no hero would
  ever keep its gear across a save.
- **Arena tactical combat, AI arena use, and the two remaining dialog captions** (§5.5) — all designed
  or scoped, none built.

## Failed approaches — do not retry

- **Items as AI targets, group-blind priority** (`build_ai_itemtarget.py`, §1.6) — 🛑 REVERTED
  2026-07-22. Answering the AI-target broadcast with a flat value-derived priority, ignoring who was
  asking, made AI groups walk to loot they could never use and then loiter beside it. Fixed by gating
  the answer on "would some hero in the asking group actually take this?" (`cave_target`, §1.5).
- **A ported item-loot design's "carry item type == 5" filter.** Two independent derivations (the
  shipped RTTI enum, and a census of both the vanilla and live item libraries) agree this is wrong on
  both counts: `itScroll` is type 5 and exists in **zero** shipped items in either tree, while type 6
  (potions/wands) is the real carry category the filter was aimed at and would have thrown all of it
  away. The correct test is `type >= 5`.
- **Walking `[item+8]` as a `TList` of an item's children.** `TItem` is an ability *owner*, not a
  container — `[item+8]` is a bitset pointer and `[item+0xC]` its bit capacity
  (`TCustomAbilityList.GetAbSet`); reading it as a list dereferences bitmask data as a pointer and
  access-violates. When replicating an engine bit-set walk, copy the engine's own accessor including
  its bounds check, never re-derive the layout from the offset alone.
- **Probing `THeroInventory.GetFreeSlot` to ask "is this inventory full?"** It walks the inventory
  list and a fresh hero's inventory starts empty, so it reports "full" for every brand-new hero.
  `GetSlot` (0 = free, and 0 for any index past the list end) is the correct probe.
- **Guarding the AI-target answer on `[msg+0x18] == 0`.** A ported design gated on this byte being
  zero, on the untested assumption that it was a sub-hex index; it is actually the per-object *layer*
  byte `SendMapFieldMsg` copies from the field's own parallel array, and `==0` was never verified as
  the right test. The fix replicates vanilla's own entry gate (`GetTerrain(...) >= 0`) instead of
  guessing at the field's meaning.
- **Overriding `TStructure.UpdateAITarget` (VMT `+0x1C4`) for item targeting** (§1.4) — cannot see the
  asking `TAIGroupControl*`, which only reaches the message one level up, at `MapFieldMsgProc +0xCC`.
- **The old, undocumented side-swapped `CanRaze` mod that predates this project's conventions** (§4.1
  provenance note) — an earlier session's raze mod had swapped which combat-predictor side was the
  razer and which was the militia, and separately swapped the gate's pass/fail arms; net effect was
  removing vanilla's suicide-raze allowance while adding a new stalemate-passes hole, leaving the
  Great-Eagle exploit intact either way. Superseded by restoring vanilla sides as step 0 of the
  predictor fix, before `simfly` (§4.2) was layered on top.
- **A "fair-fight" flag letting melee hit flyers every round inside the raze predictor.** Rejected by
  design review, not just by testing: in a real fast combat, ground melee only ever damages a flyer via
  retaliation, one engagement at a time — letting melee freely initiate in the sim over-weights it and
  would deny razes that a real fast combat actually wins. Superseded by the fast-combat-equivalence
  design (`simfly`, §4.2), which keeps the flying gate intact and instead charges real retaliation.
- **Unconditionally removing the flying gate, or unconditionally modelling true retaliation, in
  `GetDamageValueEx`.** Both leak into every other consumer of the same virtual —
  `TCombatPredictorUnit.UpdateTargets` (all AI attack planning), `TCombatUnit.GetTargetWallCV` (real
  tactical combat), and `GetUnitIndexAIPriority` (AI build priority) — shifting AI behaviour game-wide
  for a fix that only needed to touch three "hypothetical militia" call sites. `simfly`'s flag-scoped
  approach is the fix that shipped.
- **Using `TFastCombat` directly as the raze-outcome oracle.** It executes real `TCombatAction`s —
  strikes, deaths, XP, logbook entries, animations, flees — and consumes the MP-lockstep RNG stream; it
  is not a side-effect-free query, and using it from `CanRaze`'s UI-context call (before any
  synchronised command exists) would desync. `simfly` replicates its *economics* inside the existing
  safe estimator instead of calling it.
- **The `razeok` leak's "one-shot consume" fix (option C, §3.3).** Clearing the flag immediately after
  `cave_forcefail` honours it looked like the obvious fix and was rejected: it breaks
  `cave_skipavenger`, which reads the same flag *after* a second, legitimate `CanRaze` re-entry inside
  `PlaceRazeDefenders`. The structural return-address range test (v5) was adopted instead.
- **AI non-city raze veto, earlier revisions (§3.4).** One routed the predictor's stalemate result
  (`2`) through as a pass, which is not "decisively wins"; another used a strength-ratio proxy loose
  enough that strong-but-actually-doomed groups passed and then lost the fight for real. Superseded by
  the current test: result `==4` exactly, with `GetSuperiority < 50`.
- **Loot's v1 owner read via city slot `0x7C`** (§4.4.8) — `0x74`/`0x78`/`0x7C` are the structure
  X/Y/LEVEL coordinate accessors on every other structure class; `0x7C` is only `GetPlayer` on the
  *production control* object case 5 actually receives. Every surface city read level 0 as its owner
  and skipped the loot battle entirely. Fixed by reading the correct `city[+0x30]` owner byte.
- **Loot's fast/manual choice, approach A (§4.4.8)** — built and applied 2026-07-13, reverted the same
  day after regressions the source material does not identify. Loot is fast-only in the current build.
  Re-derive only after checking what specifically regressed, not from the design description alone.
- **An earlier claim that `TDamageCA.Generate`'s epilogue used a "stale ESI"**, and a separate claim
  that a combat wall's short VMT sent a stat call "wild" — both proposed during the `07-ui.md` wall-log
  crash investigation (§4.6.2) and both wrong on inspection of the actual disassembly (`Generate` sets
  `ESI` once in its prologue and is straight-line to one epilogue; `TCombatWall` correctly overrides its
  stat-getter slots). The real cause was the `+0x4C` type-confusion this section documents in full.
- **Any terrain-changed VMT slot as a general "something on the map changed" funnel** (§6.5) — produces
  unbounded recursion through the engine's own visibility/invalidation chain. No such notification
  exists in AoWEPACK; do not go looking for one via this slot.
