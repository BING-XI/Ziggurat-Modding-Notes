# Seduce / Charm / Dominate → two stacks on one hex

**Status: DIAGNOSED (v2), UNCONFIRMED — no patch, not tested in-game.** Date 2026-08-16.
Reported symptom (user): acquiring a unit via a Command ability *sometimes* leaves **multiple stacks
on the same hex**.

## ⚠⚠ NOT VANILLA — read this before anything else

The v1 headline ("vanilla AoW1 behaviour, not a Ziggurat regression") was **wrong**, and it was wrong
because the check only covered the 20 functions on the *capture* path. **Three functions on the
move/attack path are live-patched by `build_patch.py`** (move-predictor v4, applied 2026-07-05,
**never retested, and it has NO `--undo`**):

| VA | function | note |
|---|---|---|
| `0x55747B01` | `TMoveArmyTE.Setup` | |
| `0x5574A36E` | `MoveArmyEx` | that script's own header calls it the "destination-reached check (attack/combine)" — hook address corrected 2026-08-16 (was misquoted as …6F) |
| `0x557936A3` | `TSelectedArmy.Update` | |

Its cave at `0x5580D700` is itself a **byte-mask consumer** coupled to two host stack frames
(`0x5580D708 movzx edx,byte[ebp-5]` and `0x5580D716 movzx edx,byte[ebp-1]` read locals owned by
`TMoveArmyTE.Setup @0x55747ADD` and `MoveArmyEx @0x5574A35E`). This is invisible in Ghidra, whose
image is vanilla.

**Therefore: A/B `build_patch.py` out before doing anything else on this bug.** The symptom may be
its regression, not a vanilla defect.

⚠⚠ **HOW to A/B it — and a booby trap (verified 2026-08-16):**
- **NEVER run `build_patch.py --apply`.** Its backup step writes to the pristine-reference filename
  in the game root, so re-applying would **overwrite the pristine backup with a patched DLL**.
- The script is also **stale**: the live cave at `0x5580D700` is a later PIC build that the script
  can neither verify nor rebuild.
- A/B is therefore a **manual byte restore** of the three hook sites (and cave zeroing), taking a
  fresh feature-named backup first — per the in-place-rewrite convention in `CLAUDE.md`.

---

## The mechanism (v2)

**Arrival DOES merge**, in `TMoveArmyTE.FinishMove @0x55747FBC`:

```
GetNoneMovingArmyHS @0x557479D4        ; find a stationary army on the destination hex
TArmy.AddUnitSelection(stationary, moving, 0xFF) @0x5578E6B4
```

`AddUnitSelection` is **all-or-nothing behind `CanAddUnitSelection`** (returns 0 = OK, non-zero = a
refusal code). **`FinishMove` ignores the return value**, then clears the moving flag on the *wrong*
army. So when the merge is refused — e.g. because the combined count exceeds the cap — the result is:

- two `TArmyHS` left on one hex, and
- the loser flagged "moving" (`army[+0x11] & 4`), hence **invisible to every future
  `GetNoneMovingArmyHS`** — it cannot be merged away while the flag stands.
  ⚠ *Not* permanent (corrected 2026-08-16): `TArmy.ReadWrite` **force-clears bit 4 on every save
  load**. The double stack itself persists across the reload — so "reloading fixes the stuck army
  but not the doubled hex" is consistent with, and evidence for, this mechanism.

The refusal-ignoring return is at **`0x5574802D`** — the instrumentation point.

That is the "sometimes": it needs the merge to be *refused*, which needs the combined stack to exceed
the cap. A Command capture supplies exactly that extra unit.

⚠ **This makes the unbounded merge at `TArmyCombatMoveTE.ExecuteCombat @0x55749A48` a likely CAUSE,
not an unrelated side finding** — v1 recorded it as a separate curiosity. Fix scoping must treat the
two together.

**Next step is instrumentation, not a fix**: log the two merge-refusal sites and confirm the refusal
fires and the flag lands on the wrong army.

### v1's mechanism was wrong — do not re-derive it

v1 claimed the post-combat re-split in `ExecuteCombat` stranded the captured unit in the remnant via
a stale bit 2 of `unit[+0x25]`. **It is on the wrong hex**: `TCombatData+0x08/0x0C/0x10` is the
*target* hex, and the split re-acquires at the *origin*. Also ruled out: msg `0x1141` has **no handler
anywhere** in the DLL (the constant occurs exactly once, at the send site `0x557910B4`), so it is not
a delivery path for anything.

---

## Why two armies on one hex is possible at all

A map field is a node container holding a **list** of hotspot children (`TMapField.AddHS
@0x55701FDC` / `RemoveHS` / `FindHS` / `FindOwnedHS`), and `field->vmt[0x80] Get(classid)` returns
**the first match only**. Two armies per field is legal and designed — the clinching evidence is that
`ExecuteCombat` temporarily detaches itself from its own field precisely so `GetArmyHS` returns *the
other* army on that field.

**`TArmyHS.PlacePrivate @0x55791278` is the only same-hex bypass in the game.** It calls
`TUnitHS.PlaceHX` directly with no occupancy guard. Exactly two callers, both deliberate:

- `TMoveArmyTE.InitializeMove @0x55747E7C` — partial-stack move (split, place on same hex, walk off)
- `TArmyCombatMoveTE.ExecuteCombat @0x55749924` — the post-combat re-split above

Everything else is closed: `TArmyHS.PlaceHX @0x557911F8` refuses a same-hex second army unless
`TUnitHS.GetEditMode @0x55784000` is true (editor only).

---

## ⚠ The consequence is the *opposite* of the obvious guess

A tempting theory is that two armies on one hex collide in combat: both map to the same party index
via `TCombat.GetPartyPosition @0x55727764`, producing duplicate `TCombatUnit+0x46` bytes and tripping
`TCombatData.AddObject @0x55728CE0`'s *"CombatObject Position/ID double defined"* assertion.

**That does not happen. Don't re-derive it.** `TCombat.AddAdjacentArmies @0x5572760C` calls
`field.Get(0x20217)` **once per hex** and adds one army. The second army on a hex is **never added to
the combat at all**.

The real consequence: **the hidden stack does not fight.** Attack a doubled hex and only one of the
two stacks defends; the other sits untouched on contested ground. Same for `InitDefaultArmies`.
This is the sharpest available test of the whole diagnosis.

43 sites use classid `0x20217` and **every one sees only the first army** — `TCombat.AddAdjacentArmies`,
`TCombat.InitDefaultArmies`, `TStructure.ListArmies`, `TCity.UpdatePlayer` / `MoveArmiesOutOfCity`,
`TTeleport.Teleport`, `TCave.Enter`, `TArena.Enter`, `TExplorationSite.Search`,
`TSelectedArmy.MouseDownEvent`, `TAbstractUnit.CanPlace` / `Place`, `TMoveArmyTE.Validate`. Order is
the field's HS-list order; `PlacePrivate` appends, so after the split the **remnant** (holding the
captured unit) is what all 43 sites see and the mover's new army is the hidden one.
*(Append-vs-prepend in `AddHS` not verified — it flips which stack is hidden, not whether one is.)*

---

## Ruled out — do not retry these

- **"`Place` spills into a second army on the same hex."** ❌ `TAbstractUnit.Place @0x557810FC` gates
  on `CanPlace @0x55781008` → `TArmy.CanAddUnit` (VMT `+0xA4`) → `MaxSize @0x5578DEF4`, and creates a
  new `TArmy` **only** where `field.Get(0x20217)` is nil. When the destination is full it
  `WalkToNextHN`s to a **different hex** (up to ring 30). ⚠ The phrase "lets the engine spill into
  new armies" in the campaign-transfer notes means **adjacent-hex** spill —
  `TAoWCampaignTransferSettings.ExecuteSelection @0x55731894` passes the same `flags=1` as the combat
  path. The wording invites the wrong reading.
- **"The capture path calls `AddUnit` without `CanAddUnit`."** ❌ On this path `AddUnit`/`AddChild`
  are unreachable without `CanAddUnit` passing first. (They *are* unbounded in themselves — but see
  the separate live over-cap producer below.)
- **"It's a stack-capacity problem, so raising the cap to 12 fixes it."** ❌ Under the v2 mechanism
  a higher cap makes `CanAddUnitSelection` refusals **rarer**, so the double stack becomes rarer —
  **masked, not fixed**. The refusal-ignoring code path is untouched.

## In-combat capture, for reference

The capture itself changes only the combat **side** byte — no army, no `Place`, no player change:

| VA | function |
|---|---|
| `0x557703C0` | `TCommandAbility.fcExecuteCombatCommand` (auto-resolve entry) |
| `0x55770358` | `TCommandAbility.CreateCommandCA` |
| `0x5576FC68` | `TCommandCA.Execute` — resolves via `TCombatData.FindID`; strips prior command by looping the 3 ids in `AoWE.CommandAbilityIDs`; if `GetSide(attacker) != GetSide(victim)` → ability `vmt+0x124` |
| `0x5576FE50` | **`TCommandAbility.Command`** — the success handler; sets `victimCombatObj->vmt[0x68](victim, commander[+0x45])` |
| `0x55727510` | `TCombat.ObjectSideChanged` (fan-out) |

Army membership changes only afterwards, in `TCombat.Finalize @0x55727E38` →
`TCombatUnit.Finalize @0x55724D44`, which branches on `party[+0x1A] == self[+0x45]` at `0x55724DBD`:
phases 0/1 place same-side units (`flags=2`, constant at `[0x55724F24]`); **a seduced unit fails that
test and is skipped in both**, then phase 2 (`flags=1`, constant at `[0x55724F28]`) places it at
`0x55724ED1` under the captor, `TCombatObject.GetPlayer @0x557268E4` resolving off the *new* side.

`Place`/`CanPlace` flag bits: bit0 = allow spiral, bit1 = ignore "hex belongs to another player",
bit2 = refuse to join an existing army.

---

## The over-cap producer — now a suspected CAUSE, not a side finding

`TArmyCombatMoveTE.ExecuteCombat @0x55749A48` merges a second army sharing the mover's hex with
`myArmy->vmt[0xAC](myArmy, unit)` and **no `CanAddUnit` call**, so it can build an army above the cap.
`FinishMove`'s refusal-ignoring merge (above) then cannot merge that army away, and flags the wrong
one as moving. Treat these as one defect. Also recorded in `Stack_Size_12_Investigation.md` §2.
*(Inference; not constructed in-game.)*

## Corrections made at source

`Command_Abilities_Nerf.md` carried two errors that changed its feasibility verdict; both fixed
2026-08-15. The controller's list at `data[+0x10]` is a **`TByteList` of per-battle combat-object
ids**, not persistent unit ids, so the controller→victims direction does *not* survive a battle and
must be rebuilt by the nerf. And `data[+0x18]` stores the victim's original **side**, not its
original **player** — so the nerf must still stash the owner itself.
