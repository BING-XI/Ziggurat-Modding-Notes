# AI exploration-site searching + AI item loot

> **Status: 🔨 APPLIED, UNTESTED (2026-09-03)** — both features. Written to the live
> `AoWEPACK.dpl`, every static check passes, **nobody has played either of them.** Promote to
> `✅ CONFIRMED WORKING` only on the user's in-game test (§8).

Two features in one doc because they are companions: exploration sites are the game's main item
source, so before this the AI neither *generated* loot (it never searched a site) nor *collected*
it (its heroes could not pick anything up). Together they close the loop. They also share an
audience, a message (`0x1200`), a priority scale, and a set of traps.

| Feature | Script | Binary | Backup | Revert |
|---|---|---|---|---|
| AI paths to and searches exploration sites | `build_scripts/build_ai_sitesearch.py` | `AoWEPACK.dpl` | `.pre-aisitesearch` | `--undo` (surgical) |
| AI heroes equip / upgrade-swap ground items; items become AI targets | `build_scripts/build_ai_itemloot.py` | `AoWEPACK.dpl` | `.pre-aiitemloot` | `--undo` (surgical) |

`VA = file_offset + 0x55700C00` for the CODE section. ImageBase `0x55700000`; the package rebases
at runtime, so every cave here is rel32 / register-only or uses the `call $+5; pop reg` anchor.

Prior art, still valid as substrate: `Investigation_AI_Item_Pickup.md` (the two doors),
`AI_ItemPickup_Engine_Mechanics.md` (collection layout, list-removal, ground-list lifetime, the
token pipeline), `Investigation_Items.md` (item struct/field map),
`Investigation_Site_Defender_Rosters.md` (the defender rosters these searches will fight).
Design credit: both were ported from Inioch's share6 scripts
(`Inioch/Inioch_Share6_Catalogue.md` §3 Tier 1). **His cave VAs were not reused and every engine
address below was re-derived on our binaries.**

---

## 1. What was wrong in vanilla

| | |
|---|---|
| Sites | `AoWE.TStructure.ExecuteAI @0x5575E698` = `33 C0 C3` (`xor eax,eax; ret`) and `AoWE.TStructure.UpdateAITarget @0x5575E69C` = `C3`. Every exploration-site class inherits both, so an AI player never advertises a site as a move target and never searches one. Its only loot source was hero drops. |
| Items | `TItemHS` had no `MapFieldMsgProc` of its own (VMT `+0xCC` inherited the `THexagonSprite` thunk `0x55701D4C`), so a ground item never received the `0x1200` AI-target broadcast; `TAbstractUnit.MovedTo` performed no pickup; and `THero.PlaceItem @0x55788E94` — the only producer of the "place item" token — has **zero callers inside the DLL** (it is driven solely by `AoW.exe`'s `TUnitWindow` drag/drop UI). |

Items *leave* a hero engine-side (`THero.Killed` → `ExecutePlaceItem(hero, id, 0xE)` on all 14
slots) but could only *enter* one through the exe. Both features close that asymmetry for the AI
and leave the human UI untouched.

---

## 2. `build_ai_sitesearch.py` — AI searches exploration sites

### 2.1 The two overrides, on seven classes

| VMT slot | vanilla | now | why |
|---|---|---|---|
| `+0x1C0` `ExecuteAI` | `0x5575E698` stub | `cave_execai` `0x55834000` | mints the search token event |
| `+0x0CC` `MapFieldMsgProc` | `0x5575F730` `TStructure.MapFieldMsgProc` | `cave_msgproc` `0x55834400` | answers the `0x1200` AI-target broadcast with a priority |
| `+0x1C4` `UpdateAITarget` | `0x5575E69C` stub | **left as the stub, deliberately** | see §2.2 |

| Class | VMT | `+0x1C0` slot | `+0x0CC` slot |
|---|---|---|---|
| `TExplorationSite` | `0x557C1440` | `0x557C1600` | `0x557C150C` |
| `TItemExplorationSite` | `0x557C23BC` | `0x557C257C` | `0x557C2488` |
| `TMonsterlair` | `0x557C2D24` | `0x557C2EE4` | `0x557C2DF0` |
| `TDungeon` | `0x557C557C` | `0x557C573C` | `0x557C5648` |
| `TCrypt` | `0x557C64D0` | `0x557C6690` | `0x557C659C` |
| `TRuin` | `0x557C68FC` | `0x557C6ABC` | `0x557C69C8` |
| `TPyramid` | `0x557C6D20` | `0x557C6EE0` | `0x557C6DEC` |

14 slots rewritten. All 14 carry HIGHLOW `.reloc` entries, which stay valid because both new
targets are in-image VAs; the script asserts that and refuses to write if any slot lacks one.
`pristine_check()` additionally confirms all **21** slots (14 + the 7 untouched `+0x1C4`) are
vanilla in `AoWEPACK_original_backup.dpl`.

### 2.2 ⚠ Why `MapFieldMsgProc +0xCC` and NOT `UpdateAITarget +0x1C4`

The verified chain (our binaries, 2026-09-02):

```
AoWE.TAoWMapField.GetAITarget @0x55771D84     builds a 0x24-byte message on its stack
    [msg+0x00] = 0x1200
    [msg+0x04] = the map field        (filled by SendMapFieldMsg)
    [msg+0x08] = ctx                  ([0] player, [1] relation, [2] MODE)
    [msg+0x0C] = result record        (FillChar'd to 0x18 zero bytes)
    [msg+0x10] = the ASKING TAIGroupControl        <-- only visible here
    [msg+0x18] = per-object layer byte             (set by SendMapFieldMsg)
    [msg+0x1C] = stop-propagation flag
 -> HSEngine.TMapField.SendMapFieldMsg @HSEPack 0x55607944
        for each object on the field, top index down: call [obj_vmt + 0xCC]
 -> AoWE.TStructure.MapFieldMsgProc @0x5575F730
        gate: GetTerrain([self+8]->[0x28], [msg+0x18]) >= 0
        msg 0x1200: ecx=[msg+0xC], edx=[msg+8], call [vmt+0x1C4]
                    then if [rec+0] < 0 -> [msg+0x1C] = 1  (veto, stops the loop)
```

**`+0x1C4` receives only `ctx` and the result record.** The asking group — which the strength
ladder needs — lives at `[msg+0x10]` and is unreachable from there. So the override sits one level
up at `+0xCC` and chains the inherited `TStructure.MapFieldMsgProc` first, keeping messages
`0x1106 / 0x1124 / 0x1102 / 0x1103 / 0x1131 / 0x1122 / 0x1126 / 0x1127 / 0x110C` working.

Both `GetAITarget` callers were checked and both pass a real `TAIGroupControl`:
`AoWE.TAIMoveTargetSelector.ProcessStates @0x55743343` / `0x55743634` (edx = `[selector+0x24C]`,
written by `TAIMoveTargetSelector.Search @0x55743847` from the plugin's `Activate` arg, which
`TAIGroupControl.ActivatePlugin @0x557390FA` passes as edx = the gc) and
`AoWE.TAIGroupControlTarget.Validate @0x55737FF5` (edx = `[targetlist+0xC]`, set by
`TAIGroupControl.Create @0x557388FF`, where `[gc+0x24] = list` and `[list+0xC] = gc`).

### 2.3 `cave_execai` — `0x55834000`, 199 bytes (sub-zone `0x400`)

Called from `AoWE.TStructureAIPA.Process @0x55762632` with `eax` = structure, `dl` = the AI player
index, `ecx` = the pass number; `al` = 0 drops the structure from the pass worklist (the vanilla
stub's behaviour), non-zero keeps it queued **and breaks the loop**. Passes are exactly 1 and 2
(`TStructurePhase1AIPA.Create @0x557626A3` writes 1, `TStructurePhase2AIPA.Create @0x557626E3`
writes 2); both are accepted, matching `Altar.TAltar.ExecuteAI @0x557CF2C4`, the only vanilla
implementation of this slot.

1. pass in {1,2}, else return 0.
2. `ExploreS.TExplorationSite.CanSearch @0x557C1E1C` (eax=site, dl=player) — `[vmt+0x1F0]`
   `GetExplored == 0` (loot left) **and** `FindOwnedChild(field, 0x20217 TArmyHS)->[+0x1C]->[+0x12]
   == player`, i.e. this player's army is standing on the site. `[site+4]` is the `TMapField`;
   `[mapfield_vmt+0x80]` is `HSEngine.TMapField.FindOwnedChild @HSEPack 0x556077D4`.
3. Strength gate: mint only when `3 * S_army >= 2 * S_def` (≥ 1.5×). Undefended always mints.
4. Mint the search TE **verbatim** from the engine's own no-dialog branch of
   `ExploreS.TExplorationSite.Search @0x557C1F34..0x557C1F7B`:
   `[vmt+0x160]` `CreateTE` → `[vmt+0x164]` `SetupTE` (binds ClassID + x/y/l) → `[te+0x18] = 0`
   (routes `ExecuteTE` to `ExecuteSearch`) → `[te+0x20] = 1` (auto-resolve combat) →
   `GetTokenControl(map[+0x23C], movsx byte [te+0x13])` via thunk `0x5570372C` →
   `[tokenctrl_vmt+0x10]` submit → `[te_vmt+0x2C]` release.
5. Always returns 0.

⭐ **Copying the engine's own token mint is what makes this MP-safe.** The token is serialised
through the same stream vanilla uses, and `ExecuteSearch @0x557C1A20` revalidates through
`CanSearch` on every peer. (Inioch's correction, adopted: AIPAs and AI run identically on every
machine — Global players are locally simulated everywhere, not one-machine-plus-broadcast — which
is why an AI-side cave may mint a token at all.)

PIC: the map holder `0x558E9494` is reached with one `call $+5; pop ecx; mov eax,[ecx + delta]`
anchor at `0x5583409B`, displacement `0x000B53F9`. One anchor scheme, used once; no other absolute
data reference exists in either cave.

### 2.4 `cave_msgproc` — `0x55834400`, 250 bytes (sub-zone `0x400`)

1. Chain `AoWE.TStructure.MapFieldMsgProc @0x5575F730` unchanged.
2. Only `[msg+0] == 0x1200`.
3. **Replicate the vanilla entry gate exactly**: `GetTerrain([site+8]->[0x28], [msg+0x18]) >= 0`,
   through the AoWEPACK thunk `0x55701C8C` → `HSEngine.TTerrainList.GetTerrain @0x55605054`.
4. ctx gates: mode `[ctx+2] == 0`, asking player `[ctx+0] != 0` (no neutral raiders).
5. Site still holds loot: `[vmt+0x1F0]` `GetExplored == 0`.
6. Never overwrite a veto: skip if `[rec+0] < 0`.
7. Ladder, then MAX-combine into **`[rec+0]` only**.

```
S_def = AoWE.TUnitList.GetStrength      @0x55783300  (eax=[site+0x34], dl=0)
S_grp = AoWE.TAIGroupControl.GetStrengthMax @0x557389D4 (eax=[msg+0x10], dx=1)

    S_def == 0          ->  100   free loot, city-tier draw
    2*S_grp <  3*S_def  ->  nothing at all   (no straggler gathering)
    S_grp   >= 10*S_def ->  100
    S_grp   >=  5*S_def ->   75
    S_grp   >=  3*S_def ->   45
    S_grp   >=  2*S_def ->   30
    else (>= 1.5x)      ->   15
```

⚠ **`[rec+8]` and `[rec+0xC]` are the AI's gold/mana cost fields.** Writing them corrupts its
economics through `MakeTargetExpense`; only `[rec+0]` is ever touched.

⚠ **The ladder is a pure RATIO and is scale-free — do not rescale it.** Both sides use the same
engine metric, so Ziggurat's stat doubling moves `S_grp` and `S_def` together. For calibration
against vanilla's scale: a neutral mine advertises `0x32` = 50
(`Mine.TMine.UpdateAITarget @0x557B44ED`); `TArmy.UpdateAITarget @0x55790618` gives enemy army 50,
army with a hero 100, army with a wizard 300; player structure 10; city 100..130.

Both rosters are `TArmy` instances, so `TUnitList.GetStrength` applies to both — `[site+0x34]` is
the `TDefendersArmy` built by `TArmy.Create` in `ExploreS.TExplorationSite.Create @0x557C17F4`
(and is the very list `ExecuteSearch @0x557C1A78` feeds to the search combat), and `[armyHS+0x1C]`
is the `TArmy` built in `AoWE.TArmyHS.Create @0x557908E5`. `TArmy`'s VMT carries
`AoWE.TUnitList.GetStrength` unoverridden at slots `+0x90` / `+0x1B4`.

### 2.5 Cave reservation and RNG

`0x55834000..0x55835FFF`, 8 KB, exclusive; verified all-zero in **both** the live DLL and
`AoWEPACK_original_backup.dpl`, no `.reloc` entry inside it, and no `build_scripts/*.py` references
any VA in `0x55834000..0x5583FFFF`. The last non-zero byte anywhere in CODE before this feature was
`0x55832328`; CODE runs to `0x558E7918`.

**Neither cave draws.** Every function they call is RNG-free (`CanSearch`, `GetStrength`,
`GetStrengthMax`, `CreateTE`, `SetupTE`, `GetTokenControl`, `GetTerrain`,
`TStructure.MapFieldMsgProc`); the search's own rolls happen later inside `ExecuteSearch`, on the
engine's existing synchronised stream, unchanged. `rng_audit.py --owners` shows **no** site for
this feature (verified 2026-09-03).

### 2.6 Register preservation — each callee read, not assumed

| callee | saves |
|---|---|
| `TExplorationSite.CanSearch @0x557C1E1C` | ebx, esi |
| `TUnitList.GetStrength @0x55783300` | ebx, esi, edi, ebp |
| `TAIGroupControl.GetStrengthMax @0x557389D4` | esi (**ecx destroyed**) |
| `TMapField.FindOwnedChild @HSEPack 0x556077D4` | ebx, esi, edi — **the one that matters**: `cave_execai` holds `S_def` in EDI across it |
| `TTerrainList.GetTerrain @0x55605054` | 5 instructions, eax/edx only |
| `TStructure.MapFieldMsgProc @0x5575F730` | ebx, esi, edi |
| `GetExplored` (three impls `0x557C1844`, `0x557C2930`, `0x557C5A74`) | ebx |

For `CreateTE` / `SetupTE` / `GetTokenControl` / submit / release the proof is positional: vanilla
`TExplorationSite.Search` keeps EBX (the site) and ESI (the TE) live across exactly this sequence.

---

## 3. `build_ai_itemloot.py` — pickup, upgrade-swap, and items as AI targets

### 3.1 Sites written

| Site | vanilla | now |
|---|---|---|
| `0x55787FD7` hook A — `THero.NewTurn`'s `call TAbstractUnit.NewTurn` | `E8 70 8D FF FF` | `E8 A4 05 0B 00` → `cave_nt` |
| `0x5578051B` hook B — `TAbstractUnit.MovedTo` epilogue pops | `5F 5E 5B 59 5D` | `E9 A0 80 0B 00` → `cave_moved` |
| `0x55710244` — `TItemHS` VMT `+0xCC` (VMT `0x55710178`; carries a HIGHLOW reloc) | `0x55701D4C` | `0x55838400` `cave_target` |

Cave zone `0x55838000..0x5583C000` (16 KB), exclusive, verified all-zero and reloc-free in both the
live and the pristine DLL. Every displaced range is `.reloc`-swept before it is written.

| Cave | VA | size / budget | role |
|---|---|---|---|
| `cave_value` | `0x55838000` | 242 / 256 | `value(item)`; EAX = `TItem*` → EAX = worth |
| `cave_wouldtake` | `0x55838100` | 196 / 256 | would this hero take it? EAX=hero, EDX=item, ECX=value → AL |
| `cave_pickup` | `0x55838200` | 472 / 512 | pickup / upgrade-swap worker; EAX = `THero*` |
| `cave_target` | `0x55838400` | 329 / 384 | `TItemHS.MapFieldMsgProc`; EAX=self, EDX=msg |
| `cave_nt` | `0x55838580` | 24 / 64 | hook A wrapper |
| `cave_moved` | `0x558385C0` | 46 / 64 | hook B wrapper |

```
cave_nt @0x55838580                       cave_moved @0x558385C0
 55838580 e8c787f4ff  call 0x55780d4c      558385c0 60          pushal
 55838585 3a5e24      cmp bl,[esi+0x24]    558385c1 53          push ebx
 55838588 0f8509..    jne 0x55838597       558385c2 89d8        mov eax,ebx
 5583858e 60          pushal               558385c4 e800000000  call $+5
 5583858f 89f0        mov eax,esi          558385c9 5f          pop edi
 55838591 e86afcffff  call cave_pickup     558385ca 8b97e399edff mov edx,[edi-0x12661d]  ; THero classref
 55838596 61          popal                558385d0 e8eb8aecff  call 0x557010c0  ; @IsClass
 55838597 c3          ret                  558385d5 59          pop ecx
                                           558385d6 84c0        test al,al
                                           558385d8 0f8407..    je  0x558385e5
                                           558385de 89c8        mov eax,ecx
                                           558385e0 e81bfcffff  call cave_pickup
                                           558385e5 61          popal
                                           558385e6 5f5e5b595d  <replayed epilogue>
                                           558385eb c20400      ret 4
```

`cave_nt`: ESI = hero and BL = the turn player index provably survive the displaced call — vanilla
itself does `cmp bl,[esi+0x24]` on return at `0x55787FDC`. `cave_moved`: EBX = the unit
(`mov eax,ebx` at `0x55780514`, three instructions before the hook); the unit is stashed on the
stack across `@IsClass` so nothing depends on what that RTL helper preserves.

### 3.2 The value metric

```
value(item) = 5*ATK + 10*DEF + 10*DAM + 5*RES + SUM over granted abilities of ExpandCost
```

Stat bytes `[item+0x46]` ATK, `[+0x47]` DEF, `[+0x48]` DAM, `[+0x49]` RES — re-derived on **this**
install rather than taken on trust: our live DLL has
`THeroItems.GetAttack / GetDefense / GetDamage / GetResistance @0x55786354 / 88 / BC / F0` hooked
out to caves at `0x55815080 / 110 / 1A0 / 230` (`build_useitems.py`), and those caves sum exactly
`[item+0x46..0x49]`. `TItem.ReadWrite @0x557945C8` maps file tags `0x0B/0x0C/0x0D/0x0E` onto those
four bytes through the **signed** byte reader (`[stream_vmt+0x30]`), which is why the cave uses
`movsx`, not `movzx`.

Abilities: `TItem` is an ability **owner**. `TItem` VMT `+0x4C` is
`TCustomAbilityList.GetAbSet @0x5574E0E0` = `cmp edx,[item+0xC]; jae false; bt [[item+8]],edx`, so
`[item+8]` is the **bitset pointer** and `[item+0xC]` is the **bit capacity**. Each set bit's id
indexes the global registry `[[0x558FA044]+0x80]` through
`TAbilityControl.GetAbility @0x557501C0`, and the cost is the virtual `[ability_vmt+0xC8]`
`ExpandCost` — the same number the hero level-up system charges. A hard ceiling of 192 sits on top
of the engine's own `[item+0xC]` bound.

⚠ **`ExpandCost` is effectively `ExpandCost(self, unit)` and never writes EDX**, so whatever the
caller left there flows into `[vmt+0x94] GetInherentLevel(self, unit)`. With a garbage EDX,
`TMultiLevelAbility.GetInherentLevel` dereferences it as an ability owner and chases
`[x+0x10]`/`[x+8]` through the vtable. **EDX is explicitly zeroed**; a nil unit returns level 0
immediately, which yields the level-1 cost — the same value the hero level-up dialog shows.

### 3.3 Pickup / upgrade-swap

Runs for AI heroes on the strategic map, on their owner's turn (hook A) and on every move
(hook B). Gates: `[[0x558FA040]+0x11C] == 0` (no combat object → strategic map), owner
`[hero+0x24]` → `TPlayerList.GetPlayers @0x557544D0` → `[player+0xA7] != 0` (0 = human, left to the
UI), `[hero+4] != 0` (placed), `[hero+0x70] != 0` (`THeroItems`).

* **Pass 1** — one carry item into a free inventory slot (positions 6..13).
* **Pass 2** — equip slots 0..5. The slot's required type comes from the engine's own pos→type
  table, `THeroItems.GetPositionItemType @0x55786734`, table `0x558E8DB0` = `02 00 03 04 01 04`, so
  **slots 3 and 5 are both rings**. The best matching ground item that is **strictly** better than
  what is worn replaces it: drop the old with `ExecutePlaceItem(hero, oldID, 0x0E)`, then place the
  new at the slot. Equal value → no switch, so the AI cannot thrash between two equivalents.
  Empty slot → any matching item.

⭐ **Why drop-before-place works at all, and the dependency it creates.** `ExecutePlaceItem`
revalidates through `THero.CanPlaceItem @0x55788D08`, which on the strategic map requires the ITEM
and the HERO to report the same hex. `TItem.GetLocation @0x557942B4` delegates to its container's
VMT `+0x90`, and the base `TItemList.GetLocation @0x55794A5C` just writes the `0xFF` "nowhere"
sentinel — which would make every drop a silent no-op. It works because **`THeroItems` overrides
that slot**: `THeroItems.GetLocation @0x5578633C` is `[self+4]` (the owning hero) forwarded to the
hero's own location getter, and `THeroInventory` overrides it the same way. This is also why
`THero.Killed` can drop all 14 slots in vanilla. **If a future change re-points either `+0x90`
slot, the swap stops working silently** — no error, the item simply never leaves the slot.

⚠ The ground list is **refetched for every slot**, and the loop breaks to the next slot the instant
a placement succeeds: `TItemHS.ItemsChanged @0x55795D10` calls `[VMT-4] Destroy` when the list
empties, freeing the `TItemHS` *and its `TItemList`*, so the list pointer is dead the moment a
pickup lands. Only item IDs (integers) ever cross a mutation boundary, never pointers.

### 3.4 Targeting — `cave_target`, and why it is not the 2026-07 patch

`build_ai_itemtarget.py` (applied then reverted 2026-07-22) answered `0x1200` with
`10 + min(GetObtainValue/10, 20)` — a flat 10..30 that **ignored who was asking**. AI stacks with
no hero, or with heroes already better equipped, walked to the item and then loitered next to
something they could not take.

`cave_target` answers **only if some hero or leader in the asking group would actually take the
item**, using `cave_wouldtake` — the same predicate the pickup worker applies. That is why both
live in one script: a cross-script `call rel32` into another script's cave would couple the two
`--undo` paths together.

The group is walked from the message, not from the map: `[msg+0x10]` is the `TAIGroupControl` and
`[gc+0xC]` is its `TAIGroup`, which **is** a `TUnitList` (proved by `TAIGroupControl.SetupME`
calling both `TUnitList.GetUnit` and `TAIGroup.GetAdjacent` on it).
`TAIGroupControlTargetList.Validate` re-queries with the same control (`[list+0xC]`, set in
`TAIGroupControl.Create`), so a target that qualified stays valid until someone takes the item.
Candidates are filtered with `@IsClass(unit, THero classref)` — which admits `TLeader` and rejects
`TUnit`.

```
priority = 10 + min(bestQualifyingValue / 2, 65)   ->  10..75, max-combined into [rec+0]
```

Calibrated against the **live** item library `User/Zig.ail` (325 records), not vanilla
`ITEMS.PFS`: measured value distribution median 19, p75 32, p90 48, max 114 (Blade of Erebus). With
divisor 2 the 65-point cap only bites at value 130 — 14 % above the highest item that exists — so
nothing in the shipped library pins at the ceiling. That measurement **understates** the metric
(231 of the ability references on items have no `Ability.pfs` tag-6 cost because their cost is set
in code), which is the second reason for divisor 2 rather than 1: ~1.5× of headroom before the cap
flattens the top. Against the vanilla scale in §2.4 that puts the median item at 19 (above a bare
structure, well below any army) and only the best ~2 % of items above the enemy-army line. Divisor
1 would have put a third of the library above 50 and had loot outbid combat.

### 3.5 MP safety

Both pickup hooks run on **every** peer — `THero.NewTurn` is reached by broadcast with no locality
gate, and `TAbstractUnit.MovedTo` is reached from `TArmy.MovedTo` iterating army members — and
`ExecutePlaceItem` is side-effect-clean (no RNG, log, sound, dialog or token), so the result is
identical everywhere. ⚠ **Minting a token here would be WRONG**: N peers would each mint one and the
item would be placed N times. The targeting cave only writes an AI query result — no state.

**No cave in this script draws from either generator**; the script's own `selfcheck()` asserts it
(call/jmp rel32 *and* bare address constants for both `0x5577827C` and `0x55701080`), and
`rng_audit.py --owners` shows no site for this feature.

### 3.6 The script's own standing self-checks

`selfcheck()` runs before any write and refuses on failure: (1) no RNG reference in any cave;
(2) no drive-letter absolute path in any cave; (3) **position-independence checked
instruction-by-instruction** with capstone detail (a byte-window dword scan gives false positives on
displacement boundaries) — a pure-disp32 memory operand or an immediate holding a module VA is
fatal; (4) **every anchor-relative reference is resolved back to its VA** and must land on a global
this feature actually uses.

⭐ Check (4) exists because of a real defect: the first draft hand-counted `cave_value`'s anchor
**0x4C short**, which pointed the `TAbility` classref at `0x5570F260` instead of `0x5570F214` and
the `AoWHSSet` global at `0x558FA090` instead of `0x558FA044`. It assembled, it verified, it
installed — and it would have read the wrong memory forever. `with_anchor()` now assembles each
cave twice: once to *measure* where the `call $+5; pop` lands, then again with the true anchor.
**Never hand-count an anchor offset.**

---

## 4. Supersession — and the script that must stay inert

`build_ai_itemloot.py` **supersedes both** of these. Neither should be applied again.

| Superseded script | State | Note |
|---|---|---|
| `build_ai_itempickup.py` | ✅ was CONFIRMED WORKING 2026-07-21 (empty slots only); **`--undo`'d 2026-09-02, must stay inert** | It owned hook sites `0x55787FD7` and `0x5578051B` and caves `0x55810000..0x5581017F` (its `cave_nt` `0x55810100`, `cave_moved` `0x55810140`). ⭐ **A surgical `--undo` was added to it on 2026-09-03 — it never had one.** There is no `AoWEPACK.dpl.pre-aipickup` on disk and there never was. |
| `build_ai_itemtarget.py` | 🛑 REVERTED 2026-07-22 (group-blind priority → AI loitering) | Its `--revert` is surgical. Superseded by `cave_target`, §3.4. |

⚠ **`build_ai_itemloot.py` refuses to apply while `build_ai_itempickup.py` owns the two hook
sites.** It detects the old owner by decoding the `E8`/`E9` at each site and testing whether the
target falls in `0x55810000..0x55810180`; on a hit it prints the handover instructions, returns 2,
and **writes nothing**. Exactly one script may own a hook site, and it will not take one over
silently. (On `--undo` in that state it restores only what it owns — the `TItemHS` VMT slot and its
own cave zone — and leaves the hooks alone.)

The proof the handover really happened, read out of the backups on 2026-09-03:
`AoWEPACK.dpl.pre-gripofwinter` (2026-09-01) still holds `E8 24 81 08 00` at `0x55787FD7` and
`E9 20 FC 08 00` at `0x5578051B`, i.e. jumps to `0x55810100` / `0x55810140` — the old script's
caves. `AoWEPACK.dpl.pre-aisitesearch` and `.pre-aiitemloot` both hold the vanilla bytes at both
sites.

---

## 5. Revert

```
python build_scripts/build_ai_itemloot.py   --undo      # writes immediately
python build_scripts/build_ai_sitesearch.py --undo      # writes immediately
```

Both are surgical: they restore the hook sites / VMT slots they own and zero their **own** cave
zones, touching no `.pre-*` file, so features applied afterwards survive.

⚠ **The two are independent — no ordering constraint between them**, and neither shares a cave or a
hook with any other feature. Their zones (`0x55834000..0x55836000` and
`0x55838000..0x5583C000`) are disjoint from every other reservation in the tree.

⚠ **`build_ai_itempickup.py` has a DIFFERENT undo contract.** `--undo` alone is a dry run there;
the write switch is still `--apply`:

```
python build_scripts/build_ai_itempickup.py --undo            # dry run of the revert
python build_scripts/build_ai_itempickup.py --undo --apply    # actually write it
```

Read a script's flag implementation before trusting it — not every `--undo`/`--revert` in this tree
means the same thing.

⚠ **Do not revert either feature by copying a `.pre-*` snapshot.** Both snapshots were taken from a
file *proved* free of that feature (each script gates the backup on a positive test against the
feature-absent bytes, never on "no backup file exists"), so they are honest — but a restore still
wipes every layer applied afterwards. Verified layering on 2026-09-03, oldest first:
`.pre-gripofwinter` → `.pre-aisitesearch` → `.pre-aiitemloot` → `.pre-rtugearth` →
`.pre-minddecayoos`. So `.pre-aisitesearch` predates four later features.

---

## 6. Traps and failed approaches — do not retry these

### ⚠⚠ A carry item is `type >= 5`, NOT `type == 5`

The design this was ported from tests `== 5` in the pickup arm and rejects `type > 5` in the
targeting arm. **Both are wrong on both trees.** Two independent derivations agree:

1. **The RTTI enum shipped in the binary** (`TItemTypes`, names at VA `0x55708C50`) is
   `(itHead, itTorso, itAttack, itDefense, itRing, itScroll, itUse)` — so **`itScroll` = 5 and
   `itUse` = 6** — and the type→pos table at `0x558E8DB8` (`01 04 00 02 03 0F 0F`) maps **both** 5
   and 6 to `0x0F`, "no equip slot".
2. **Two censuses of the actual data**: `Release/ITEMS.PFS` has **0 of 83** items at type 5 (our
   2026-07-30 RTTI read); the live library `User/Zig.ail` has **0 of 325** at type 5 — and **73 at
   type 6**.

So `== 5` picks up an item class that exists in neither tree and silently ignores every real potion
and wand, while a targeting arm that rejects `type > 5` throws all 73 away. Our
`FIRST_CARRY_TYPE = 5` is a `>=` test on purpose. Related: `itScroll` is fully implemented cut
content (`Scrolls_are_cut_content`, `Investigation_Items.md` Feature 1b) — restoring it would create
type-5 items, and this `>=` test already handles them correctly.

### ⚠ `[item+8]` is a bitset, not a list

`TItem` is an ability **owner**, so walking `[item+8]` as a `TList` of children reads bitmask word 1
(0 for every low-id item) as a data-array pointer, and AVs. `[item+0xC]` is the bit **capacity** and
must bound every scan; a fixed 192-bit walk reads past smaller bitsets. **Rule: when replicating an
engine bit-set walk, copy the engine's own accessor including its bounds check** — here
`GetAbSet @0x5574E0E0`.

### ⚠ `THeroInventory.GetFreeSlot @0x5578601C` returns −1 on an EMPTY list

It walks the inventory *list*, and hero inventories start empty, so it reports "full" for every
fresh hero. Probe with `GetSlot @0x55786284` instead — its semantics (0 = free, and 0 for any index
past the list end) are the correct test. This was one of three AVs/logic faults in the upstream
design.

### ⚠ REJECTED: guarding `[msg+0x18] == 0` in `cave_msgproc`

The upstream v2 gates the AI-target answer on `[msg+0x18] == 0`. `[msg+0x18]` is the **per-object
layer byte** that `SendMapFieldMsg` copies out of the field's parallel byte array, **not** a sub-hex
index, so `== 0` is an untested assumption whose failure mode is the whole targeting feature
silently doing nothing. Ours replicates the vanilla gate instead:
`GetTerrain([site+8]->[0x28], [msg+0x18]) >= 0`.

### ⚠ REJECTED: overriding `UpdateAITarget +0x1C4`

It cannot see the asking group (§2.2). The seven `+0x1C4` slots are deliberately left as the
vanilla stub, and `pristine_check()` asserts they are still vanilla.

### The 2026-07 loiter failure

Group-blind item priorities attract stacks that cannot use the loot. Any future AI-target answer
should be gated on "would the asker actually consume this?", not on the target's intrinsic worth.

---

## 7. Verification already done (does NOT make it confirmed)

* Both scripts re-run with no arguments report **applied**, caves byte-identical to this build.
* `.reloc`: no entry inside either cave reservation or any displaced run; all 14 site VMT slots and
  the `TItemHS` slot carry HIGHLOW relocs, which stay valid.
* `pristine_check()`: 21 site slots vanilla and both cave zones zero in
  `AoWEPACK_original_backup.dpl`.
* `rng_audit.py --owners` (2026-09-03): 24 modded sites in total, **none** belonging to either
  feature; no cave in either script references `0x5577827C` or `0x55701080` in any form.
* No drive-letter path and no printable data run in any cave.
* Backups verified honest by byte-check, not by filename (§5).

None of that is a test. A cave can verify perfectly and still be wrong.

---

## 8. What still needs the user's in-game test

**Sites (`build_ai_sitesearch.py`)**

1. An AI stack **walks to** an unexplored exploration site instead of ignoring it — dungeon, crypt,
   ruin, pyramid, monster lair, item site and the plain site all behave.
2. Standing on the site, the AI **searches** it: combat auto-resolves and the loot is taken.
3. The strength ladder shows: an AI group far weaker than the defenders does **not** walk to a
   defended site (< 1.5×), and an undefended site draws attention like a city-tier target.
4. A **neutral/independent** player does not raid sites (the `[ctx+0] != 0` gate).
5. Sites already searched stop attracting the AI (`GetExplored`).
6. No "Invalid AoWHSMap.Random use" popup, and no visible slowdown on a large map with many sites
   (the msgproc runs per object per AI target query).

**Loot (`build_ai_itemloot.py`)**

7. An AI hero standing on a **better** item of a type it already wears swaps into it, and the old
   item is left on the ground; an equal or worse item is ignored (no thrashing).
8. An **empty** equip slot is still filled by any matching item.
9. Potions / wands (item **type 6**) go into the hero's backpack while it has room.
10. An AI group containing a hero who could use a dropped item **walks to it**; a group with no
    hero, or whose heroes are all better equipped, does **not**.
11. **Rings**: an item that fits slot 3 can also land in slot 5.
12. Humans are unaffected — `[player+0xA7] != 0` gates the whole worker.

**Both, together**

13. The loop closes: an AI searches a site, the loot appears, and its heroes then equip it.
14. Save / load across an AI turn with items on the ground and a search queued.
15. If a multiplayer test is ever run: two peers, both with this DLL, an AI player active — no OOS.
