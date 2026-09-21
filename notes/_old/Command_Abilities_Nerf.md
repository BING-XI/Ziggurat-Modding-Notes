# Command Abilities Nerf — design note (2026-07-12)

**Status: DESIGN NOTE / feasibility assessment. Nothing applied.** Requested by the user during the
city-rebellion work. Addresses: Seduce / Charm / Dominate (and any `TCommandAbility`-based mind control).

## The concern (user)
The current AoW1 rule is: **a mind-controlled unit is kept permanently, UNLESS the controlling unit
died during the same battle in which the control was applied.** The user considers this **OP** — once
you survive that one battle, the stolen unit is yours forever with no downside. Desired nerf: the
control should **revert (unit returns to its original owner) whenever the controlling unit dies — even
many turns / battles later.** The user explicitly asked whether such cross-battle tracking is possible.

## How the vanilla mechanism works (decoded 2026-07-12)
- **Two abilities.** The controller carries `TCommandAbility`; the victim gains `TCommandedAbility`
  (`Create` @0x5576FADC; the "Seduced" flavor `TSeducedAbility` @0x5577083C is a subclass, as are the
  Charm/Dominate variants).
- **The relationship is tracked explicitly, both directions:**
  - Controller side: `TCommandAbility` data holds at `data[+0x10]` a **`TByteList` of COMBAT-OBJECT
    ids** — *not* a list of unit ids (corrected 2026-08-15). `ResetCommandedUnits` @0x5576FF94
    resolves each entry with `TCombatData.FindID`; `Command` @0x5576FE50 / `Uncommand` @0x5576FF08
    add and remove `victimCombatObj[+0x0C]`. **Combat-object ids are per-battle**, so the controller
    side does NOT persist across battles — see the corrected persistence note below.
  - Victim side: `TCommandedAbility` data holds a **back-reference to the controlling ability** at
    `data[+0x14]` (used by `CombatObjectDestroyed` @0x5576FB6C to find and notify the controller).
- **Within-battle revert (the existing rule):** `TCommandedAbility.CombatObjectDestroyed` fires when a
  combat object dies; it resolves the controller via `data[+0x14]` and calls the controller's revert
  vcall (slot 0x130). `ResetCommandedUnits` walks the controller's commanded list and reverts each unit
  found **in the current combat** (`TCombatData.FindID` on `combat[+0xC]`). So the revert path is
  **combat-scoped** — it only knows how to reach commanded units that are objects in the *active*
  combat. `TCommandedAbility.CombatDone` @0x5576FB4C finalizes the surviving controls when combat ends.
- **Persistence:** `TCommandedAbilityData.ReadWrite` @0x5576FA8C exists — the commanded state is
  **serialized to saves**, i.e. a permanently-controlled unit *retains* its `TCommandedAbility` (and the
  `data[+0x14]` controller link) on the strategic map, across turns and saves.
  ⚠ **Corrected 2026-08-15 — only the VICTIM side persists.** The controller's commanded list at
  `data[+0x10]` holds per-battle combat-object ids (above), so it is meaningless once the battle
  ends. The earlier claim that the tracking the nerf needs "already exists and persists" was true of
  the victim→controller link only; **the controller→victims direction must be rebuilt** by the nerf
  (e.g. by scanning for units carrying a `TCommandedAbility` whose `data[+0x14]` points at the dead
  controller, rather than by walking `data[+0x10]`). This changes part 1 of the feasibility verdict:
  "check whether its commanded list is non-empty" is not a usable test outside combat.

## Feasibility verdict: **FEASIBLE, moderate effort.** Three parts:
1. **A global unit-death hook** (strategic scope): when any unit is destroyed, check whether it is a
   controller — i.e. its `TCommandAbility` data has a non-empty commanded list (`data[+0x10]`).
   (Unit-death / removal is a single chokepoint; identify it, hook it.)
2. **A strategic-scope revert** adapting `ResetCommandedUnits`: instead of `TCombatData.FindID` (combat
   objects), resolve each commanded unit id via the strategic unit registry (`TUnitControl.FindUnit`
   @0x5577E948, as used elsewhere) and revert it — restore its original owner and strip the
   `TCommandedAbility`.
3. **Confirm the original owner is recoverable.** ✅ **ANSWERED 2026-08-15 — and the answer is "no,
   you still have to stash it".** `TCommandedAbility` data *does* store a pre-control value at
   `data[+0x18]`, written by `TCommandAbility.Command` @0x5576FE50 from `victim[+0x45]` and restored
   by `Uncommand` @0x5576FF08 via `vmt[0x68]` — but that is the victim's combat **side** byte, which
   is battle-scoped. The original **player** is not stored anywhere. So the nerf must still stash the
   original owner at control time, exactly as this item anticipated (a spare byte in the ability
   data; `ReadWrite` already serializes it, so save-persistence is close to free).

## Interaction with the rebellion / raze feature (feature "converted units join the stack")
The sibling request — a garrison member converted by rebels should *join* the rebel stack rather than
wander — depends on the SAME machinery. The clean composition: converts join the winning stack on a win
(permanent per the vanilla rule), and this nerf then makes them revert if their controller later dies.
Build the "join the stack" harvest first (it only needs the winning-side conquer-units, respecting the
existing within-battle permanence); layer the cross-battle revert on top as the nerf.

## Recommendation
Worth doing, and cheaper than feared because the relationship is already tracked and serialized. Order:
(1) verify the original-owner is stored (or add it), (2) build the global death hook + strategic revert.
Defer until the raze/rebellion line settles; record here so it isn't lost.
