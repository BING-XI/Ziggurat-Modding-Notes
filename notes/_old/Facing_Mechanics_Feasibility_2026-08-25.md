# Facing Mechanics — Feasibility (units face a hex direction; turn costs; rear-attack bonus; Shield)

**Status: SPECULATIVE — NOTHING APPLIED, NOTHING BUILT. Investigated 2026-08-25.**

No binary was modified and no build script exists for any of this. Every address below was read
out of the **live Ziggurat-patched install** (or, where marked, the pristine
`AoWEPACK_original_backup.dpl`) during a read-only investigation. Nothing here has been tested
in-game, because there is nothing to test yet.

## ⚠ SCOPE DECISION — user, 2026-08-26: TACTICAL COMBAT ONLY

**Facing is intended purely as a tactical-combat mechanic.** The strategic map is explicitly out of
scope: units do **not** need a per-unit facing there, facing does **not** need to persist between
battles, and the fact that strategic facing is per-*stack* (`TArmyHS`, one instance per army,
created from `TArmy.ReadWrite @0x5578EA0B`) is **fine as-is and must not be "fixed"**.

This decision deletes the single largest cost in this document. Everything below marked as
strategic-map work is retained for reference only — **do not build it**:

- the new `TUnit` field, its fresh property id, and the strategic↔tactical facing bridge (§3/F1);
- the three-surface strategic MP coupling — `TAbstractUnit.MovedTo`, the flood/path cost bytes, and
  the live v4 move-predictor caves — together with its four booby traps (§3/F2, §4 item 3);
- `TMoveControl.ProcessHexagon`'s nine `.reloc` entries and the `CalculateMovePointLine` insertion
  point (§4 item 2's flood-side defects), since the flood is only reached for strategic routing;
- the strategic turn-in-place hotkey via `TAoWHSMapKeyboard` (§4 item 9);
- the strategic AI movement-budget concern (§4 item 2 of the AI lane).

**What survives the narrowing and still needs deciding or building:** the melee auto-re-facing
deletion (§4 item 1 — still the hard precondition for any melee rear bonus); the tactical path
surcharge via the `0x00412AC8` VMT slot; the pathfinder's inability to *route* with facing, which
applies to tactical paths too because `AoWE.TMoveControl.CalculatePathEx @0x557460B0` serves both
maps; the ≤ 0 MP activation cliff in `TAoWCombatMap.GetNextUnit`; the three strike-site chains for
F3/F4; Shield's registration and its `0xAC` id contention; the tactical AI's pre-move scoring; the
tactical turn-in-place gesture (likely mouse-only — AoWTCPCK exports no keyboard class); and the
**auto-resolve policy question**, which the narrowing does *not* remove, because auto-resolved
battles are still battles (§5 Q1).

---

Derived by a 12-agent sweep (8 RE lanes + 3 adversarial verifiers + synthesis); 17 lane claims
were **refuted** by the verifiers and have been deleted rather than annotated, per the project's
superseded-analysis rule. §7 lists what remains genuinely unproven — read it before building.

### ⚠ Ability-id contention with the proposed caster abilities

§3/F4 proposes ability id **`0xAC`** for *Shield*. `Caster_Abilities_Feasibility_2026-08-25.md`
proposes **`0xAC`–`0xAF`** for Evoker / Conjurer / Enchanter / Ritualist. Only four ids were
measured free. **These five proposals cannot all ship as written** — whoever builds first must
re-measure with `check_id_free` and the loser must be re-numbered. Neither doc's id is reserved.

### Tooling note for the next session

The Ghidra MCP bridge was **up** throughout (port 8089, project `AoW1-vanilla`, program
`AoWEPACK_vanilla.dpl`, 221 tools registered) and `list_instances` / `connect_instance` /
`check_tools` answered normally — but the dynamically-registered analysis tools
(`decompile_function`, `get_xrefs_to`, …) never entered a **subagent's** tool list, so subagents
could not call them even after `connect_instance`. The main session's `ToolSearch` loaded them
fine, so this is a per-subagent tool-registration quirk, not an outage.

**Workaround, and it works completely:** drive Ghidra over its plain HTTP API —
`curl 'http://127.0.0.1:8089/decompile_function?address=0x5578480C'`, `/get_function_xrefs`,
`/read_memory`; the endpoint catalogue is at `/mcp/schema`. This matters: the one lane that gave
up and fell back to raw capstone produced this report's single worst error (a per-section
file-offset mistake that invented a fictional "the HN tables are BSS and read as zero" blocker,
refuted in §2).

Related: a DATA xref to a method **is** its VMT entry, so `slot base = xref − slot offset`
resolves a Delphi VMT in seconds. Trap: `AoWE..TStrikeCA` (two dots) is the VMT itself;
`ptr->AoWE..TStrikeCA` is only a pointer slot holding it.

---

# Facing, Turn Costs, Rear Attacks and Shield — Feasibility Report

*Synthesis of eight RE lanes plus three adversarial verification passes. Where a lane and a verifier disagreed, the verifier wins. Claims the verifiers refuted have been deleted, not footnoted. Addresses are from the LIVE Ziggurat-patched install unless marked vanilla.*

---

## 1. Bottom line

The engine is already a six-facing game. A persistent direction byte exists, is serialised, is maintained by movement on both maps, is rendered from six distinct sprite sets, and already has a hexagon-shaped radio group in the map editor. The expensive parts of this proposal are not "add facing" — they are (a) deleting a piece of vanilla behaviour that makes rear attacks unreachable in melee, (b) the fact that the pathfinder's cost field cannot represent facing, so turn costs can be made *correct* but never *optimal*, and (c) three abstraction layers (auto-resolve, the combat predictor, the tactical AI's pre-move scoring) that cannot see hex geometry the way manual combat does.

| Sub-feature | Verdict | Rough effort | The single thing that decides it |
|---|---|---|---|
| **F1 — units have a facing** | **Feasible — already exists** | None | Per-unit tactical facing is already real: `TTacticalCombatUnitHS` is one object per unit, each with its own `TUnitHS+0x14`. Nothing to build, nothing to serialise. (Strategic facing is per-*stack* on `TArmyHS` — **out of scope**.) |
| **F2 — turning costs movement points** | Feasible with caveats (approximate routing) | Medium | Tactical charges the path node's cost byte **unclamped**, so surcharging the finished path works end to end through one VMT slot (`0x00412AC8`). The residual caveat is that `CalculatePathEx` still cannot *route* with facing in mind, so costs are exact but the chosen route is occasionally not the cheapest. The strategic three-surface job is **out of scope**. |
| **F3 — rear attacks do extra damage** | Feasible with caveats | Medium | Vanilla forcibly spins the melee defender to face its attacker *before* the strike resolves (`0x004092C4`–`0x0040931B`). Until that is deleted or gated, a melee rear bonus is unreachable for every attacker after the first. Ranged is unaffected |
| **F4 — "Shield" frontal damage reduction** | Feasible | Small–Medium | Nothing new is needed: ability id `0xAC` is free, registration is the Drillmaster recipe verbatim, and the damage-time query is one `call [vmt+0xA8]`. It is gated only on F3's arc test existing |

---

## 2. What the engine already gives you

### The facing byte

`AoWE.TUnitHS+0x14` — one byte, legal steady-state range **0..6** (0 = none, 1..6 = the six hex neighbours), default **3**.

| Thing | Address |
|---|---|
| `TUnitHS` VMT / instance size | `0x5570EED0` / `0x1C` |
| `TUnitHS.Create` (writes default 3) | `0x55783DA4`, store at `0x55783DC3` |
| `TUnitHS.SetDirection` | `0x5578480C` |
| `TUnitHS.MoveFirst` (a **second**, SetDirection-bypassing writer) | `0x55784830`, store at `0x55784854` |
| `TUnitHS.ReadWrite` — streams `+0x14` as property **id 9** | `0x55783ED4` |
| `TArmyHS` VMT / size / ReadWrite (adds id `0x0A`) | `0x557133A0` / `0x24` / `0x55790D88` |
| `AoWTC.TTacticalCombatUnitHS` VMT / size / parent cell | `0x00412D08` / `0x48` / `0x0046E924` → `AoWEPACK.dpl!AoWE..TUnitHS` |

Persistence is real and was verified end to end: stream VMT slot `+0x30` is `rwByte(ptr, id)` (`Engine.TEWriteStorageStream.rwByte @0x55510184`, one byte, `ECX` = property id), and `TArmyHS` is a registered streamable class instantiated through `rwCreateEObject` from `HSEngine.TMapField.ReadWrite @0x55607128`.

Two corrections that matter:

- **Direction 0 does not survive a save.** `rwByte` skips zero bytes entirely (`cmp byte [edi],0; je` at `0x5551019B`), so the id is absent on load and the legacy fix-up at `0x55783EFD`–`0x55783F03` rewrites the field to 3. Do not use 0 as a meaningful sentinel.
- **The spare bits of `+0x14` are not spare.** Vanilla melee transiently writes 7, 8 and 9 into the byte and wraps on the following instruction (`add edx,3` at `0x004092C7`, `sub edx,6` at `0x00409302`). Any hook on `SetDirection` will observe out-of-range values; bit-packing there would corrupt vanilla behaviour.

### The hex geometry library

`HSEPack.dpl`, unit `HSEngine`, preferred base `0x55600000`, 1040 exports. **Not in Ghidra.** The map is a true 6-neighbour hex grid in **odd-q offset layout** (`x` = column = the parity axis). Direction numbering is HN 1..6 clockwise from N; **opposite = `d+3` wrapped into 1..6**, so pairs are (1,4), (2,5), (3,6).

| Function | HSEPack VA | AoWEPACK thunk | AoWTCPCK thunk |
|---|---|---|---|
| `dHXtoHNfast` (direction of B from A; **exact only for adjacent hexes**) | `0x5560E338` | `0x557026AC` | *not imported* |
| `dHXtoHN` (exact spiral index at any range) | `0x5560E308` | `0x557026A4` | `0x004022B4` |
| `dHXtoRad` (hex distance) | `0x5560DCF4` | `0x5570266C` | `0x004022A4` |
| `HNtoRad` / `RadToHN` (ring decomposition) | `0x5560DED8` / `0x5560DF0C` | `0x5570267C` / `0x55702684` | — |
| `InvHN` | `0x5560DF24` | *not imported* — use `((hn+2) mod 6)+1` inline | — |
| `HNtoHP` (walk pixel offset) | `0x5560E448` | `0x557026C4` | `0x004022CC` |

The lookup tables `HNtoXYTable 0x5562E024`, `HNtoRadTable 0x5562E0A4`, `InvHNTable 0x5562E0CC` (= `00 04 05 06 01 02 03`), `HNtoHXTable 0x5562E0F4`, `RadToHNTable 0x5562E21C` are in **file-backed DATA** (`0x5562E000`, raw size `0x600`) with correct contents — an earlier lane's "they are BSS and read as all zero" claim was a per-section file-offset mistake and has been struck. They rebase with the package, so reach them position-independently or just call the exports.

Tactical side has its own adjacency-exact clone: `AoWTC.GetMeleeDirIndex @0x00430C58` (`EAX` = x of the reference hex, `EDX` = x1−x2, `ECX` = y1−y2 → `AX` = 1..6). `AoWTC.GetRangedDirIndex @0x00430D48` is a **missile sprite angle, not a hex direction** — do not use it for arc logic.

Ready-made rotation tables in AoWEPACK DATA: CCW `0x558E8CF4` (stride 8), CW `0x558E8CF8` (stride 8), opposite `0x558E8D38` (stride 4). Directional-cone precedent in AoWTCPCK: `AoWTC.BreathHN @0x00467498` (12 hexes per facing), `AoWTC.BreathDir @0x004673A8` (HN → sector, rings 1–4).

### Facing is already maintained, rendered and edited

- **40+ write sites**, exactly enumerated: 6 in AoWEPACK (all three `*MoveTE.ExecuteMove` variants, `0x5574829A`/`0x557482A6`, `0x5574867D`/`0x55748689`, `0x5574A114`/`0x5574A120`), **34** rel32 calls to the AoWTCPCK thunk `0x00402AF4`, plus `AoWDevEd.exe`'s own import (IAT `0x004327AC`). Both original lane counts (31, ~28) were undercounts.
- **Rendering**: `TArmyHS.Show @0x557914D8` and `AoWTC.TTacticalCombatUnitHS.Show @0x00421EE0` index a 12-entry image-sequence list as `Items[dir-1]` idle / `Items[dir+5]` walking — six idle + six walk sequences per unit, already in the art.
- **Editor**: `AoWDevEd.exe` ships `TArmyEditForm.DirectionChanged @0x0041A528` with six radio buttons `Dir1..Dir6` laid out as a hexagon in the DFM, and an identical group on `TTCUnitPositionEditForm`. **Editor support for facing needs zero work.**
- **A rotate-in-place primitive already exists**: `TTacticalCombatUnitHS.MapFieldMsgProc` message `0x3100F` turns a unit one hex clockwise (`0x00421586`–`0x004215B3`).
- **Deployment facing** comes from the strategic approach direction: `TCombat.GetPartyPosition @0x55727764` returns HN 1..6 (7 = centre hex), packed into `TCombatUnit+0x46` as `pos*0x10 + unitIndex`, unpacked at `0x0042675E`–`0x0042677C` into `+0x64`/`+0x65`, with a **7→1 remap** at `0x00426782`, and consumed by `AoWTC.TRndTacHsm.SetupUnit @0x00426D1C`.

### Movement-point machinery

| | Strategic | Tactical |
|---|---|---|
| MP field | `TUnit+0x3D`, `THero+0x79` (signed byte) | `TTacticalCombatUnit+0x5C` (dword) |
| Accessors | VMT `+0xD4` GetMoves / `+0xD8` GetMovePoints / `+0xDC` SetMovePoints | VMT `+0x94` = `AoWE.TCombatUnit.GetMoves` (slot at `0x00412BE0`) |
| Refill | `TAbstractUnit.NewTurn @0x55780D4C` | `TTacticalCombatUnit.NewTurn @0x0041CF44`, store `0x0041CF80` |
| Deduction | `TAbstractUnit.MovedTo @0x55780328`, `sub dl,al` at `0x557803AE` | `TTacticalCombatUnit.MovedTo @0x0041CF88`, `sub dword [edx+0x5c],eax` at `0x0041CF9D` |
| Charge rule | **`min(unitOwnCost, pathByte)`** — clamps at `0x55780345`/`0x5578034E`, plus a second "cost ≥ MP → set MP 0" test at `0x5578038E` | **the path cost byte, verbatim, no clamp** (`0x004082FF`–`0x00408317`) |

Every path in the game is produced by `AoWE.TMoveControl.CalculatePathEx @0x557460B0`, which writes each node's signed cost byte (bits 24–31 of the packed XYL dword) as a difference of flood-field values at `0x5574631A`. `TMoveControl.ProcessMove @0x557466F8` is Activate → `while(Process())` → CalculatePathEx → Deactivate: **one call = one complete search**, so a wrapper fires once per path and needs no idempotence guard.

---

## 3. What has to be built

### F1 — facing

Nothing, *if* per-stack strategic facing plus per-battle tactical facing is acceptable. That is the state today, and it is coherent: the stack sprite faces where it last moved, and every unit in a battle is deployed facing the stack's approach bearing.

If **per-unit persistent facing** is required:

1. Grow `TUnit` (live instance size `0x94`, already grown once by `build_spellcast.py`) and add a `rwByte` in `TUnit.ReadWrite @0x55782CEC` with a **fresh** property id. ⚠ Do **not** follow the "avoid 9 and 0x0A" guidance — that is the `TArmyHS` chain. On the `TUnit` chain ids **4, 6, 7, 8, 9, 10 and 0x2F** are already taken (id 9 is current hit points); a duplicate raises `TEWriteStorageStream.PropertyExistError @0x5551009C`.
2. Bridge `TUnit` facing → `TTacticalCombatUnitHS+0x14` at deployment (`TRndTacHsm.SetupUnit @0x00426D1C`, overriding the party-bearing constants) and back out at combat end. `TTacticalCombatUnitHS` is constructed fresh per battle (`0x00426D30`) and is **not** a registered streamable class — its facing dies with the combat and can never be persisted directly.

Order: bridge first (it is testable in a single battle), field second.

### F2 — turn costs

**Tactical (the clean design).** Repoint the relocated VMT slot `AoWTC.TCombatMoveControl +0x04` at `0x00412AC8` (currently `→ 0x0041D038`) into a cave that calls the original and then walks the finished path adding a rotation surcharge to each node's cost byte. `EAX` = the control, `EDX` = `TMoveControlSettings`; `settings+0x9C` = the moving `TTacticalCombatUnitHS` (facing at `+0x14`, `+0x1C` → `TTacticalCombatUnit`, MP at `+0x5C`); `settings+0x68` = the produced `TXYLList`. This single slot covers the player path and all 11 AI path sites (dispatch pattern `A1 64 C0 46 00 8B 80 FC 00 00 00`, 12 hits). Every downstream consumer — the preview, both truncators (`TCombatMoveTE.Setup @0x0040815C`, `MoveCombatUnit @0x0040F584`), the charge, and all 16 AI cost reads — inherits it for free.

Cave must tolerate a **1-node list**: when source == destination `ProcessMove` early-outs at `0x55746798` without calling `CalculatePathEx`.

**Strategic (the hard job).** Three surfaces must move together or the game lies to the player:

1. The deduction — `TAbstractUnit.MovedTo`, displacing `8B D0 8B C7 2A D0` at `0x557803AA` (reloc-free; no collision with `build_path_outerring.py`'s `0x5578041E` or `build_ai_itempickup.py`'s `0x5578051B`). Alternatively `TArmyHS.MoveTo @0x55791162` (both hexes and the stale old facing are live). ⚠ `ESI` (source field) **can be NULL** there — three in-function guards at `0x55791080`/`0x557910A5`/`0x557910EB` prove first-placement/summon/teleport reach it.
2. The flood / path cost bytes — see the pathfinder notes below.
3. The **live v4 move-predictor caves**: hooks `0x55747B01 → 0x5580D700`, `0x5574A36E → 0x5580D711`, `0x557936A3 → 0x5580D71F`, `0x55792A18 → 0x5580D87F`, shared core `true_reach 0x5580D75A` / `unit_walk 0x5580D7DB`. `unit_walk` uses the unit's own cost table and does *not* reproduce `MovedTo`'s min-clamp, so predictor and charge already disagree slightly today.

Order: tactical first (self-contained, one slot, low risk), then decide whether the strategic map is worth the three-surface job at all.

### F3 — rear-attack bonus

Mandatory precondition: **delete or gate the defender re-facing** in `CombatTE.TCMeleeMoveTE.LastMove` — the `SetDirection` calls at `0x004092E0` and `0x0040931B` (the mod-6 wrap pair). Mirror sites in `TCAbTouchMoveTE.LastMove` (`0x00409E60`, `0x00409F51`, `0x00409F90`, `0x0040AAAF`). Ranged (`TCAbRangedTE.NextStrike`, `0x0040F31D`–`0x0040F377`) only ever re-faces the **shooter** — verified by exhaustion over all 34 tactical `SetDirection` sites — so ranged needs no such edit.

Ordering is favourable: `TMeleeRound.Calculate` is called at `0x00409208`, strictly *before* the re-facing block, so a cave in the strike-creation chain reads the defender's pre-attack facing regardless.

The three strike-creation sites, all already owned:

| Site | Host | Hook | Registers |
|---|---|---|---|
| melee1 | `AoWE.CreateStrikeCA @0x557665E4` | `0x557666A1 → 0x5580E070`, resume `0x557666CF` | `EBP` = attacker, `ESI` = target, `BL` = attack accumulator, `[esp+3]` = damage byte; `EAX/ECX/EDX/EDI` free |
| melee3 | `AoWE.TMeleeRound.CalculateStrikes @0x55767B24` | `0x55767C5C → 0x5580E120` | `EBX` = record base (`+0x00` attack **delta** dword, `+0x04` damage **delta** dword), `ESI` = attacker, `EDI` = target; `EAX/ECX/EDX` free |
| ranged | `AoWE.TRangedAttackAbility.CreateRangedAttackCA @0x5576EAE4` | `0x5576EB34 → 0x5580E400`, resume `0x5576EB39` | `EBX` = ability, `ESI` = shooter, `[EBP-4]` = target; **`EAX` is LIVE** (the damage byte the displaced `push eax` must still push); `EDX/ECX` free |

⚠ **Chain order at melee1 is three links deep**: `0x5580E070` (slayers/assassin) → `jmp 0x5580E370` (invisibility) → `jmp 0x558129C0` (Magebane) → `jmp 0x557666CF`. Ranged has invisibility first. A new modifier goes on the **tail** of each chain, and each tail belongs to a different build script.

Per-site cave contents: class-guard with `System.IsClass(obj, &AoWE..TCombatUnit)` (idiom at `0x55766738`), exclude `TFastCombatUnit` (VMT `0x5571D4BC`), **nil-check `[HS+0x04]`** (`TUnitHS.GetXhx @0x55783F50` / `GetYhx @0x55783F58` do no such check, while their sibling `GetLhx @0x55783F60` asserts on exactly that condition), then `obj+0x60` → HS, hex from VMT `+0x74`/`+0x78`, facing from `[HS+0x14]`, direction from the `dHXtoHNfast` thunk `0x557026AC`, rear = `{f+2, f+3, f+4}`.

Alternative site for a **multiplicative** rule: `TDamageCA.Generate @0x55729C20` (prologue reloc-free and unhooked; `ECX` = target, `EDX` = attacker, `[EBP+0x10]` = absolute attack, `[EBP+0x0C]` = absolute damage). ⚠ Its VMT `+0x68` slot is **shared** with `TRangedAttackCA`, `TTurnUndeadCA`, `TSelfDestructCA`, `TCombatSpellCA` and `TTurnUndeadSpellCA` — discriminate on class or spells get a rear bonus too. And note its epilogue at `0x55729C8C` is **already hooked** (`jmp 0x558114A0`, `build_combatlog_dll.py`).

### F4 — Shield

1. Registration: repoint the `call RegisterAbility` at `0x557BCF04` (last still-intact vanilla site; 86 remain in `PassiveAb.RegisterPassiveAbilities @0x557BC1CC`, `EBX` = the `TAbilityControl` throughout) to a ~45-byte PIC cave that re-issues the displaced call, then `CreateEnhancementAbility(EAX=0xAC, EDX=→"Shield" literal, CX=0x0301 or 0x03FF) @0x5576601C` → `RegisterAbility @0x55750238`, then `jmp 0x557BCF09`.
2. Boot once to prove the id; assign in `AoWDevEd` and save so `Release/Ability.pfs` creates record **182** (`key = id + 10`); re-run `--apply` to write tag 9 (the selection mask, which **overwrites** the cave's value), optionally tag 5 (description) and tag 6 (hero level-up cost). Repair the trailing CRC-32.
3. Damage-time query, on the **defender's combat object** in `EAX`: `mov edx,0xAC; mov ecx,[eax]; call dword ptr [ecx+0xA8]` → `TCombatUnit.GetAbilityEnabled @0x55725004`. O(1), item-aware, and polymorphic — a `TCombatWall` falls through to `TCombatObject.GetAbilityEnabled @0x557268D4` (`xor eax,eax; ret`) instead of misreading its `+0x4C`, which dodges the type-alias bug that produced "Blt Error" twice in this project.
4. ⚠ **Floor the reduction at 1.** `TCombatObject.ExecuteDamageRole @0x557269F0` contains `if (damage < 1) damage = 0` — a reduction to ≤0 means *guaranteed zero damage*, not "reduced". And at melee3 the slots are shared **delta accumulators**; never clamp them or Monster Slaying / Assassin / Charge get wiped.

Optional polish: add `0xAC` to `build_scripts/herodlg_cats.py` `ABILITY_CATS` to place it in a chosen level-up column (unlisted ids default to category 4, so omitting this degrades gracefully).

**Cave space is not a constraint.** AoWEPACK: 809,240 zero bytes `0x55822000`–`0x558E7A00` (plus `0x5581817B`–`0x5581FFFF`). AoWTCPCK: 191KB zero and reloc-free — **start at `0x00438200`**, not `0x00438110`, which is 3 bytes past `build_spellcast_tcpck.py`'s live 13-byte occupant at `0x00438100`.

---

## 4. The hard parts, ranked

**1. Vanilla destroys the defender's facing on every melee contact.** `0x004092C4` reads the attacker's facing, adds 3, and `SetDirection`s the *defender* at `0x004092E0`. Under vanilla rules every melee blow is frontal by construction. Deleting it is a two-NOP edit, but it is a **change to vanilla behaviour**, not an additive cave: every melee animation changes, and units will visibly be struck in the back. There is no way to have F3 in melee without it.

**2. The pathfinder cannot represent facing — exact turn-aware routing is Blocked.** `TMoveControlSettings` stores **one dword of cost-to-reach per (x, y, level)** (`GetMovePoints @0x557452E4`), and `CalculateMovePointLine @0x557455B4` relaxes the **minimum over all approach directions** into that single cell. Making the search optimal under turn costs needs a 6× (hex × facing) state expansion plus a rewrite of `ProcessHexagon @0x557456F8`, `CalculatePathEx @0x557460B0`, `CalculateGaps @0x55746984`, `CalculateTurnAroundMovePoints @0x55746C08`, `GetMovePointsCostFast @0x55746FEC`, `FindSubMoveOrigin @0x55745504`, `SetupSubMove @0x55745D64` and the predictor. That is a module rewrite. **The shippable design annotates the finished path**: costs and ranges become exactly right, the chosen route is occasionally not the cheapest available. Say so in the doc.

**⭐ Measured 2026-08-26 — the route-suboptimality caveat is much milder than the above implies,
and the real exposure is elsewhere.** The whole pathfinder (`CalculatePathEx`, `ProcessHexagon`,
`CalculateMovePointLine`, `CalculateGaps`, `ProcessMove`) is **byte-identical to
`AoWEPACK_original_backup.dpl`**, so the vanilla decompile is authoritative.

Two facts change the picture:

1. **The flood is ray-based.** `CalculateMovePointLine(this, field, dirIdx, ...)` walks a *straight
   line* in one direction, relaxing every hex along it until cost exceeds budget, and returns the
   run length. `ProcessHexagon` fans out and recurses. It is not a uniform frontier expansion.
2. **Path reconstruction breaks ties by a fixed direction order, and first match wins.**
   `CalculatePathEx` walks backwards; at each hex it scans directions **1..6 in numerical order**
   (`iVar10` loop, `param_1 + 0x148 + (x & 1)*0x20 + iVar10*4` — two delta tables, one per column
   parity) and accepts the **first** neighbour whose stored cost equals `currentCost - stepCost`.

Consequence: on uniform open terrain a shortest hex path uses at most **two** directions, and they
are adjacent (60° apart). Because the tie-break preference is *consistent*, the backtrack exhausts
the lower-indexed direction before switching — producing **two straight runs, i.e. exactly one
direction change**, which is already the minimum-turn shape. The naive fear (a zigzag alternating
path costing ~2·min(a,b) turns) does **not** occur.

What remains is only *which run comes first*, and since the two directions are one step apart the
engine's opening turn can be worse than optimal by **at most one 60° step — i.e. ≤ 1 MP**, against
a ~4 MP hex step and an 18–44 MP budget. Negligible. Obstacles, walls and mixed terrain break the
parallelogram and can force genuinely turn-heavy backtracks, so the caveat is real but rare, not
routine.

⚠ **The concern that actually deserves the attention is the RANGE HIGHLIGHT, not the route.**
The reachable-set list is built by the **flood**, not by path reconstruction —
`CalculateMovePointLine` appends each newly-reached field to the list at `[this+0x130]` when
`[this+0x0A] & 1` is set and the hex was previously unreached (`0xFFFFFF`). If turn costs are
applied by surcharging the *finished path*, that flood still ran turn-free, so the highlighted
"how far can I move" area will be **optimistically wrong** — the player is shown hexes they cannot
actually afford. Route suboptimality is invisible; an over-generous range highlight is a visible
lie, and it is the same failure class as the move-prediction bug this project already fixed once.
Budget for reconciling the highlight before budgeting for optimal routing.

Three specific flood-side defects to avoid, all of which fail *silently*:

- `ProcessHexagon` is **not** reloc-free. Nine type-3 entries at `0x5574572C`, `0x55745743`, `0x557457A0`, `0x557457EC`, `0x5574583C`, `0x55745847`, `0x5574585E`, `0x55745877`, `0x557458A7` — every one on the disp32 of a direction-table load. The tempting 5-byte windows each begin exactly one byte clear of a relocation, with zero margin; after rebasing, a mistake reads a wild address for the direction index.
- `0x5574563B` is **inside** the per-hex step loop (entered by `jmp 0x557456E3`, back-edge to `0x5574560E`). A surcharge there is a flat per-hex tax, not a turn tax. The once-per-ray insertion point is `0x55745603`.
- A stash written only at the four recursion sites misses `ProcessHexagon`'s own four direct `CalculateMovePointLine` calls (`0x55745734`, `0x5574574B`, `0x5574584F`, `0x55745866`), which are the majority of line launches. Also, the flood only ever turns one step at a time, so a 2- or 3-step turn cannot be expressed at a single hex at all.

**3. Strategic MP is a three-surface coupling with four booby traps.** Raising the path byte alone changes nothing (the deduction caps at it); raising the deduction alone desyncs the predictor. Then: `THero.SetMovePoints @0x5578701C` has **no ≥0 clamp** (unlike `TUnit`'s at `0x557827B4`), `TArmy.MovePoints`' min loop is signed (`0x5578D92C`), and the AoW.exe "Moves" label is `movsx` (`0x004054DD`) — one over-charged hero renders a negative stack MP on screen. `TArmy.MovedTo @0x5578DE24` has an unmentioned transporter branch at `0x5578DE4D` that charges **only the carrier**, so a per-unit surcharge loop must reproduce that. And the path cost byte is a **signed char**: a surcharge pushing any node above +127 wraps negative and makes the step free.

**4. The tactical AI sees the bonus but will not seek it, and can be starved.** `TCAI.CheckUnit @0x004152A8` scores candidate moves by building a real `AoWE.TMeleeRound` and reading `GetAttackerDV`/`GetDefenderDV` (`0x0041551A`) — so a rear bonus inside `TMeleeRound` is visible to the AI's scoring for free. But `TMeleeRound.Calculate @0x55767D24` takes **only the two unit objects, no geometry**, and at scoring time the attacker has not yet moved to the candidate hex, so the AI evaluates *pre-move* geometry and will not actually prefer rear hexes. Making it seek them means adding a term at the four approach-move families in `CheckUnit` (`0x00415766`, `0x00416BA3`, `0x0041726C`, `0x00417E62`). Separately: `TAoWCombatMap.GetNextUnit` skips units at **≤ 0** MP (`0x0041C2BF`, `0x0041C3B7`), so a rotation surcharge that drains a unit to exactly zero forfeits its **entire activation, including its attack**. With the installed roster at 18–44 MP and open ground at 4, that is a genuine balance cliff, not a soft cost.

**5. Auto-resolve and the combat predictor.** The earlier "auto-resolve has no positional model at any price" blocker is **refuted** and should not be recorded. `TFastCombat` inherits `TCombat.GetPartyPosition @0x55727764`; `TCombatPartyList.CreateParty @0x55728684` stores each party's real map X/Y/L at `+0x0C`/`+0x10`/`+0x14` and its hex bearing at `+0x19`; every combat object carries its party index in the high nibble of `+0x46`; and `TFastCombat.GetWallInBetween @0x55744600` already performs exactly that nibble→`GetParty` lookup inside the fast-combat path. So a **party-bearing** rule is available, deterministic, and meaningful in the multi-army battles `TCombat.AddAdjacentArmies @0x5572760C` creates. What genuinely does not exist there is per-unit facing.

The **combat predictor** is worse and matters more: it is position-free entirely (`Execute @0x5572B028`, scoring via `GetCombatValue @0x5577F9A8`), and it gates *whether the AI attacks at all* and *whether a structure can be razed* (`TStructure.CanRaze @0x5575FB80`). A Shield that halves frontal damage but is invisible to the predictor makes the AI systematically over-commit against shielded defenders — the same defect class as the documented Great-Eagle raze exploit. If Shield ships, an averaged mitigation belongs at `TAbility.GetDamageValueEx` (VMT `+0xDC`, `0x5574E744`) and `fcGetDamageValueEx` (VMT `+0xE4`, `0x5574E764`), with the `TStrikeAbility` overrides at `0x55766C90`/`0x55766D34`.

**6. Multiplayer determinism.** AoW1 is token-lockstep with a shared RNG, and OOS is detected by comparing the seed **value**, i.e. by draw count — one extra discarded `Random()` call has caused a confirmed desync in this engine before. A modded peer cannot play an unmodded one, and any facing rule that rolls must roll identically everywhere. Favourably: `TMoveTE.ReadWrite @0x557476C8` transmits the whole path **including the cost bytes** as property id `0x14`, so a receiving peer replays the originator's costs rather than recomputing them. And facing updates must come from TE/token execution (`TMoveTE.GetDirection @0x5574771C`), never from animation or UI code.

**7. The damage arithmetic has already been re-graded under you.** `AoWE.ExecuteDamageRole @0x55725EAC` is doubly live-patched by the 5%/DAM-HP conversion: the `RandInt` call at `0x55725EBC` redirects to a cave at `0x558114E0`, and the margin slope at `0x55725ED7` went from vanilla `add eax,eax` (−2 per point of margin) to `nop; nop` (−1). **An attack-side directional bonus now buys half the damage the pre-conversion documentation implies.** Tune against the live install, not the docs.

**8. Art and the direction census.** 250 unit ILBs (an earlier lane's 500 was a case-insensitive double count, and its per-count histogram cannot be reconciled — redo it). `HMNSP.ILB` really does decompose into six sets of twelve with six distinct payload SHA1s, so the six facings are genuinely different sprites. But at least two files break the convention (`Images/UNITS/Fro/NOrb.ILB` = 19 records with no set structure; `Images/UNITS/Dlf/LdPa.ILB` parses to 0), and the failure mode is worse than believed: `TUnitHS.Show`'s assert bounds-checks only the **idle** index; the walking index `Items[dir+5]` is read with **no bounds check at all**, so a short list dereferences garbage silently rather than asserting.

**9. Turn-in-place is the only genuinely new UI in the whole feature.** All 40 `SetDirection` sites are side effects of moving or attacking. A gesture needs: a strategic hotkey (repoint the VMT dword at `0x5570E168` → `TAoWHSMapKeyboard.KeyDown @0x55773B08`, per the project's "repoint the slot, never the jump table" rule), a tactical route (`TCombatUnitSelectionControl.MouseDownEvent @0x0041EE28`), a cursor (`Images/Cursors.ilb`, 100 records; splice recipe in `re_tools/ilb.py` + `build_copper_medal.py`), MP accounting, and — in MP — a token.

**10. The editor.** Free. Already shipped, on two forms.

---

## 5. Design decisions the user must make

**Q1 — What does auto-resolve do about facing?** Options: (a) ignore it entirely — simplest, but auto-resolve becomes numerically different from manual, and players who care will manual-fight everything; (b) assume frontal — Shield always applies, rear bonus never does, which makes Shield strictly better in auto-resolve; (c) roll 3-in-6 per strike — statistically neutral, one extra RNG draw (⚠ MP draw-count risk); (d) flat expected-value fudge — half the rear bonus, half the Shield, unconditionally; (e) **party-bearing** — evaluate the rule from each party's real approach bearing (`party+0x19`, object `+0x46` high nibble), which degenerates to "frontal" in a 1v1 but bites correctly in multi-army battles. (e) is the only option that is both deterministic and consistent with what the player sees on the strategic map; (b) or (d) are the cheap answers.

**Q2 — Do ranged attacks use facing at all?** *Yes* is cheap and safe: the ranged path never re-faces the victim, so rear shots are naturally reachable without touching vanilla behaviour, and missile retargeting does not break it (the retargeted blocker is the object actually passed to `CreateRangedAttackCA`). But `dHXtoHNfast` is a **crude quadrant classifier at range** — it compares only the signs of dx and dy, so a target one column east and ten rows north classifies as NE. An exact ranged arc needs `dHXtoHN` + `HNtoRad`/`RadToHN` ring decomposition, or a `BreathDir`-style table for rings ≤ 4. *No* keeps the feature purely a melee-positioning game and avoids "archers must be flanked" weirdness.

**Q3 — Where do turn costs apply: strategic, tactical, both, or neither?** Tactical-only is a single relocated VMT slot and materially lower risk. Strategic-only or both drags in the three-surface coupling, the hero negative-MP path, the transporter branch and the live v4 predictor caves. "Neither" is a real option: rear bonuses without turn costs make facing about *approach*, which is arguably the more interesting half.

**Q4 — Does vanilla's melee auto-re-face stay?** Keeping it means F3 is dead in melee (only the first attacker each round can ever land a rear blow, and only against a target that has not yet been engaged). Removing it means every melee animation changes and units are visibly hit from behind. There is no middle option that preserves the current look.

**Q5 — Per-stack or per-unit facing?** Per-stack is free and already persists. Per-unit costs a `TUnit` growth, a fresh property id, and a bridge in both directions across the combat boundary — and note that today *all units of a stack deploy facing the same way* (the approach bearing is per-party), so per-unit facing also means rewriting deployment.

**Q6 — Is there a turn-in-place command?** Without one, facing is entirely a consequence of movement and the feature is a pure positioning game. With one, it is a tempo game — and it is the only new UI in the proposal.

**Q7 — How is the circle divided?** Six directions is settled and not negotiable (the art, the HN algebra, and every table are 6). The open fork is the **arc split**: 3 front / 3 rear as proposed leaves no flank at all, so every attack is either bonused or shielded. Alternatives: 1 front / 2 flank / 3 rear, or 2/2/2. This is the single biggest lever on how the feature *feels*.

**Q8 — Multiplayer: supported or not?** If yes, every peer must run the identically patched `AoWEPACK.dpl` **and** `AoWTCPCK.dpl`, and no rule may consult anything client-local or draw an extra random number on one side only.

---

## 6. Recommended smallest viable slice

**Melee rear-attack bonus in manual tactical combat only. No turn costs, no Shield, no new state, no new field, no new UI.**

Three edits:

1. NOP the two defender `SetDirection` calls at `0x004092E0` and `0x0040931B` in `TCMeleeMoveTE.LastMove` (and, if touch abilities matter, the mirrors in `TCAbTouchMoveTE.LastMove`). Reversible in five bytes each.
2. Append a rear-arc term to the tail of the **melee3** chain (`AoWE.TMeleeRound.CalculateStrikes`, current tail after `0x5580E120`): class-guard, nil-guard `[HS+0x04]`, read attacker/defender hexes via `obj+0x60` → VMT `+0x74`/`+0x78`, direction via the `dHXtoHNfast` thunk `0x557026AC`, compare against `[defenderHS+0x14]`, and add a flat delta to `[EBX+4]` when the direction falls in `{f+2, f+3, f+4}`. Do **not** clamp that slot.
3. Add one line to the existing combat log (`build_combatlog_dll.py`'s cave at `0x55729C8C`; `build_effectroll.py` is the closest-shaped precedent) so the player can see the rule firing.

**Why this one.** It exercises the entire question the proposal is really asking — *is flanking fun in AoW1?* — while touching zero of the four hard parts. Facing already exists, is already set by movement, is already rendered from six real sprite sets, and is already correct at the strike site (`Calculate` runs before the re-facing). No pathfinder, no MP economy, no serialisation, no AI scoring, no auto-resolve policy, no new UI. It is one NOP pair plus one cave appended to a chain that already has three links. If it is fun, F2 (tactical-only, via the `0x00412AC8` slot) is the natural second slice and F4 the third; if it is not, nothing has been spent.

Deliberately excluded and why: **turn costs** because they force the pathfinder approximation decision and the ≤0-MP activation cliff before anyone knows the feature is worth it; **Shield** because it needs a manual DevEd round-trip and an auto-resolve/predictor policy; **strategic-map facing consequences** because that is where the three-surface coupling lives.

---

## 7. Open questions and unproven claims

Check these before building. None are blockers; all can silently waste a session.

1. **"Facing has no gameplay consumer" is UNPROVEN.** A byte-pattern sweep found **59+** byte-sized accesses to `+0x14` in AoWTCPCK against the 5 that were audited, and `+0x14` is heavily aliased (`TMapField` = terrain, `TAbility` = FExpandCost, `TAbstractUnit` = refcount, `TAoWHexagon` = land-neighbour mask, `TItem` = item id). Resolve the owning class per site before building any rule that assumes nothing else reads facing. There are also literal stores `mov byte [eax+0x14],7` at `0x0042618D` and `,8` at `0x00429644` whose class was never resolved.
2. ~~The ILB set-index to HN mapping is assumed, never verified.~~ ⭐ **CLOSED 2026-08-27 by in-game
   confirmation.** The user confirmed that Shield protects front and front-left and *only* those,
   which is possible only if the ILB set index maps 1:1 onto HN **and** map-coordinate clockwise is
   also screen clockwise. **HN handedness is proven end to end.** (The ILB *census* — 250 files, not
   500, with `Images/UNITS/Fro/NOrb.ILB` and `Images/UNITS/Dlf/LdPa.ILB` breaking the six-sets-of-
   twelve convention — is still worth redoing before anything relies on every unit having six sets,
   because `TUnitHS.Show` reads the walking index `Items[dir+5]` with **no bounds check at all**.)
3. **`GetRangedDirIndex` sector count**: one lane says 24-way (bins at `0x0D/0x29/0x4D/0x82/0xF1/0x2F8`, mirrored twice), another says 12-way (bins at `13/28/36/53/111/519`). Not load-bearing — the recommendation is to use `GetMeleeDirIndex`/`dHXtoHN` instead — but do not cite either figure until one is re-derived.
4. **Measure the signed-byte headroom** in the live path cost bytes before choosing a surcharge magnitude. Ziggurat's cost tables are already rebalanced upward; +127 is a hard wrap.
5. **Does tactical combat route keystrokes through `TAoWHSMapKeyboard` at all?** AoWTCPCK exports no keyboard class and imports no keyboard symbol. If it does not, a tactical hotkey needs a separate route and the gesture may have to be mouse-only in battle.
6. ⚠ **The v4 predictor caves are attributed to `build_scripts/build_patch.py`**, and there is a standing project warning that `build_patch.py --apply` must **never** be run (the shelved stack-size-12 work). Establish which script actually owns `0x5580D700`/`D711`/`D71F`/`D87F` before touching them.
7. **`TMoveControl+0x1E0` as an "am I in tactical combat" discriminator** at `CalculatePathEx` is plausible (set by `TCombatMoveControl.ProcessMove`) but unverified — it may be stale rather than nil on the strategic path.
8. **The Parry precedent's exact address** (`TMeleeRound.CalculateStrikes @0x55767BE1`, `sub dword [ebx],2`) was not re-verified. The idiom is confirmed; the address is not.
9. **"Strategic-map damage is out of scope"** (`TAbstractUnit.ExecuteDamageRole @0x55781AC4` has no attacker parameter) is inherited from a prior doc, not re-derived in this pass. Low risk.
10. **No pristine reference exists for `AoWTCPCK.dpl` or `HSEPack.dpl`** — only `AoWEPACK` has `Modding Resources/AoWEPACK_original_backup.dpl`. `HNtoXYTable`, `HNtoHXTable` and `BreathHN` should be byte-checked against an untouched install before anything is built on their exact contents.
11. **Incidental — BYTE-CONFIRMED defect on exactly the sites this feature would extend.**
    The alignment bonus is applied at two melee sites. In pristine
    `AoWEPACK_original_backup.dpl` both are **2**; in the live install they disagree:

    | Site | Host | Vanilla | Live |
    |---|---|---|---|
    | melee1 `0x5576665D` / `0x55766660` | `AoWE.CreateStrikeCA @0x557665E4` | `add bl,2` / `add byte [esp+3],2` | **4** / **4** |
    | melee1 `0x55766699` / `0x5576669C` | same, second arm | `add bl,2` / `add byte [esp+3],2` | **4** / **4** |
    | melee3 `0x55767C55` / `0x55767C58` | `AoWE.TMeleeRound.CalculateStrikes @0x55767B24` | `add [ebx],2` / `add [ebx+4],2` | **5** / **5** |

    Verified 2026-08-25 by byte-diff at file offsets `0x065A55`, `0x065A91`, `0x06704D`. Under the
    DAM/HP doubling 2→4 is correct, so **melee3 is one too high** — the same alignment bonus is
    worth 4 down one melee path and 5 down the other. (Monster Slaying went 3→5 at *both* sites,
    i.e. consistent, so this is not a uniform re-grade rule.) Not caused by this feature; fix it
    independently, and note that any rear-arc cave appended here inherits whichever value stands.

**Tooling note.** All three verifiers and every lane hit the same problem: the Ghidra MCP bridge answers `list_instances`/`connect_instance`/`check_tools` (port 8089, project `AoW1-vanilla`, `AoWEPACK_vanilla.dpl`, 221 tools registered) but the dynamically-registered analysis tools never enter a subagent's tool list, so `decompile_function`/`get_xrefs_to` are uncallable. **The plain HTTP API works fine** — `curl http://127.0.0.1:8089/decompile_function?address=0x...`, `/get_function_xrefs`, `/read_memory`, catalogue at `/mcp/schema`. Use it. The one lane that fell back to raw capstone without it produced the report's worst error (a per-section file-offset mistake that invented a fictional BSS blocker). Also: DATA xrefs to a method **are** its VMT entries, so `slot base = xref − slot offset` resolves a Delphi VMT in seconds. Trap: `AoWE..TStrikeCA` (two dots) is the VMT; `ptr->AoWE..TStrikeCA` is only the pointer slot holding it.

---

## 8. Prior art to reuse

Read in this order.

**Entry point and canon**

- `Modding Resources/Unit_Spellcasting_INDEX.md` — the master index; update it when this feature lands.
- `Modding Resources/Zig notes/Ghidra_Field_Catalogue.md` — class-keyed field offsets. ⚠ It has **no `TUnitHS` section**; adding one is part of this work, and any entry must name the class because `+0x14` is aliased across at least five.
- `Modding Resources/Zig notes/Ghidra_VMT_Layouts.md` — VMT slot names. ⚠ `+0xD4`/`+0xD8` mean *GetMoves/GetMovePoints* on `TAbstractUnit` but *fcRoundDistance/fcExecute* on `TCombatObject`; `+0x74`/`+0x78` are *GetResistance/GetDamage* on `TCombatUnit` but *GetXhx/GetYhx* on `TMapObject`.
- `Modding Resources/Ghidra_Toolchain.md` — Ghidra setup, startup and rollback.

**The closest-shaped features**

- `Modding Resources/Zig notes/TrueSeeing_AntiInvisible_Design.md` + `build_scripts/build_invis_penalty.py` — **the single best model for F3/F4**: a conditional per-strike modifier at all three strike sites, with the "slot semantics differ per site" trap and the in-place cave-rewrite technique.
- `Modding Resources/Zig notes/Slayer_Abilities_Design.md` + `build_scripts/build_assassin.py`, `build_ranged_slayers.py` — the three strike-creation injection sites and the "melee has TWO tables, hook both" lesson.
- `Modding Resources/Zig notes/Magebane_Ability.md` + `build_scripts/build_magebane.py` — a damage-time conditional ability end to end, and the exact register map at each of the three sites.
- `Modding Resources/Zig notes/Drillmaster_Ability.md` + `build_scripts/build_drillmaster.py` — **the F4 recipe verbatim**: registration cave, `check_id_free`, the `Ability.pfs` tag-9 write (`pfs_tag9_offset`/`pfs_write`), the DevEd-must-create-the-record dependency, and the selection-mask semantics.
- `Modding Resources/Zig notes/Ability_ID_Budget.md` — why the ability id space is a soft ceiling (`id ≤ 0xCD` only for abilities with per-owner records). ⚠ Its and `re_tools/abmask.py`'s claim that "Ability.pfs record ids are NOT ability ids" is **stale** — the join is `record_key − 10`; fix at source.

**Movement**

- `Modding Resources/Zig notes/MovePredictor_Fix_2026-07-05.md` — **mandatory before touching strategic MP**: the four live v4 hooks, `true_reach`/`unit_walk`, and the MOVZX-vs-MOVSX signed-byte bug that took three iterations.
- `Modding Resources/Zig notes/Movement_Tables_Terrain_Types.md` — the 8 ability cost tables at `0x558E84FC`, `cost = table[terrain*16 + overlay]`. ⚠ The installed tables are Ziggurat-rebalanced (277 cells differ from vanilla), and `TAbstractUnit.CreateMovePointTable @0x5577FDC4` carries three undocumented hand-edits.

**Combat maths and AI**

- `Modding Resources/Zig notes/Missile_Trajectory_And_Interception.md` — the two ranged systems, and why retargeting does not break a direction computed from live objects.
- `Modding Resources/Zig notes/Raze_CombatPredictor_Analysis.md` — the position-free predictor and the Great-Eagle exploit; the reference case for "a rule the predictor cannot see".
- `Modding Resources/Zig notes/Investigation_Status_Debuff_StatModifiers.md` — the unit stat cache. Not applicable to Shield (which must be a queried flag, not a stat modifier) but read it to understand *why*.

**Technique**

- `build_scripts/build_vision9.py` — "repoint the VMT slot, never the jump table", plus the project's first length-changing `.pfs` write.
- `build_scripts/build_herodlg_columns.py` + `herodlg_cats.py` — the `.reloc` walker (`set_reloc_types`), the ability-category table, and the exe-DFM technique.
- `build_scripts/build_combatlog_dll.py`, `build_replaylog.py`, `build_effectroll.py` — the feedback surface; `build_effectroll.py` is the closest shape for a conditional-outcome log line.
- `build_scripts/build_sitedefender_vary.py`, `build_magebane.py`, `build_mastery_cost.py` — worked examples of a **surgical `--undo`**, which is the required revert path (there is essentially no backup stack left).
- `re_tools/dasm.py`, `xref.py`, `pescan.py`, `pfs.py`, `ilb.py`, `ability_names.py`, `live_ui.py` — the capstone toolkit; `dasm.py` is how patched regions must be read, since Ghidra holds only the pristine vanilla `AoWEPACK.dpl`.