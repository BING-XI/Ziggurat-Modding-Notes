# AoW1 "Units vanish when boarding transports" — static code analysis (2026-07-05)

Analysis only — no patch applied. Reported symptoms: units (especially
leader-heroes) rarely disappear when moving into transports; seems
correlated with movement direction and with whether the leader is alone.
No known repro; findings below are from reading AoWEPACK.dpl in Ghidra.

## The boarding pipeline (verified)

1. **Path time** — entering an occupied friendly hex is allowed by
   `TArmyHS.CanMoveOver` (55790E48) via
   `CanCombine(hexArmy, mover, selectionMask)` (55790814): capacity =
   transporter carry capacity + 1 (or 8), compared against
   hexArmy.count + popcount(selection).
2. **Move split** — `TMoveArmyTE.InitializeMove` (55747E7C): if the
   selection != whole army, a NEW TArmyHS is created and the selected
   units transferred into it (PlacePrivate on the source hex — two armies
   briefly coexist there); otherwise the ORIGINAL armyHS walks.
   Sets army flag +0x11 |= 0x04 ("moving").
3. **Per hex** — `TMoveArmyTE.ExecuteMove` (557481FC) calls
   `TArmyHS.MoveTo(hs, destField)` (55791068), which:
   - broadcasts field msg 0x1140 (may-I-leave) / 0x1141 (may-I-enter);
     either may VETO -> MoveTo returns 0 with the HS still on the old field
   - `TUnitHS.MoveTo` (557843EC) — the reparent; unconditional, returns 1
   - `TArmy.Validate` (5578CF7C) — culls dead units (Undying -> Ghost swap);
     if the army empties, `TArmyHS.ArmyUpdated` (55790B74) SELF-DESTRUCTS
     the armyHS synchronously
   - `TArmy.MovedTo` — MP deduction, terrain triggers
   - broadcast 0x1142 (entered) — this is how STORMS deal damage (msgs
     0x1150/0x1151 in TArmyHS.MapFieldMsgProc, 55791C30)
   **ExecuteMove IGNORES MoveTo's return value.** It then calls
   `field.FindChildIndex(armyHS)` (VMT+0x84 = Engine.TECustomNode.
   FindChildIndex) and, on -1, sets te.army = NULL and ends the move
   (state 3). This conflates two very different situations:
   - army legitimately dissolved (died en route / merged) — intended
   - **MoveTo was VETOED and the army still sits on the OLD field** — the
     TE abandons it silently; because FinishMove's entire cleanup is
     guarded by `te.army != 0`, the army's moving flag 0x04 is NEVER
     CLEARED in this case.
4. **Arrival** — `TMoveArmyTE.FinishMove` (55747FBC):
   - detaches the mover, calls `GetNoneMovingArmyHS` (557479D4) to find
     the combine partner — **which SKIPS any army with flag 0x04 set**,
     reattaches the mover;
   - if a partner was found: `AddUnitSelection(partner.army, mover.army,
     0xFF)` (5578E6B4) — which internally re-validates via
     `CanAddUnitSelection` (5578E55C) and **does NOTHING if that fails —
     and FinishMove IGNORES the returned failure code**;
   - then re-points te.army to the partner and clears flag 0x04 **on the
     re-pointed army (the transport!), not on the mover**.

## Failure modes that produce a "vanished" unit

**A. Silent merge failure at arrival.** The path-time check (CanCombine,
selection mask, state at click time) and the arrival-time check
(CanAddUnitSelection, mask 0xFF, state at arrival) are DIFFERENT CODE
evaluated at DIFFERENT TIMES. If army composition or transporter capacity
drifted in between (multi-hex/multi-turn moves, simultaneous-turn
multiplayer, AI processing order, mid-path storm losses, another army
merging into the transport first), the final check can fail: no units
transfer, no error, and the mover is left as a SECOND army stacked on the
transport's hex — with its moving flag 0x04 leaked set (cleared on the
wrong army, see above). Consequences: `TAoWMapField.GetArmyHS` returns
only the first army child, so clicking the hex reaches only one of the
two; and the flagged mover is invisible to every future
GetNoneMovingArmyHS, so nothing can ever merge with it again.

**B. Transport busy / flag deadlock.** If the transport itself has flag
0x04 at the mover's arrival (own move in progress, or a leaked flag from
scenario C), GetNoneMovingArmyHS returns NULL: no merge is even attempted
and the mover parks as a hidden second army on the hex.

**C. Vetoed move mid-path.** Any 0x1140/0x1141 veto makes MoveTo fail;
ExecuteMove misreads it as "army dissolved", abandons the army on its old
hex WITH flag 0x04 stuck (FinishMove cleanup skipped). The army may still
be drawn but is permanently un-mergeable — and it is the seed for the
compound scenario below.

**Compound: the cursed transport.** If a TRANSPORT ever goes through
scenario C (or otherwise leaks flag 0x04), it keeps the flag forever.
From then on, EVERY army that boards it hits scenario B: the passengers
pile up as hidden second armies on its hex, "eaten" one after another.
A single rare event thereafter produces repeated vanishings around one
specific boat — matching a rare, hard-to-reproduce, location-flavored bug.

## How the observed clues map

- **Rare**: needs state drift between the two checks, a veto, or a
  flag leak — all uncommon.
- **Direction-dependent**: approach direction changes the flood-fill
  path — which hexes are crossed (storms, friendly stacks, structures,
  vetoing HS), how many hexes remain this turn (drift window), and which
  hex the move actually terminates on. Direction is a proxy, not a cause.
- **Leader alone vs. not**: decides the InitializeMove fork — whole-army
  moves walk the ORIGINAL armyHS (with its accumulated flag history);
  sub-selection moves walk a FRESH one. Different susceptibility to
  leaked flags and different HS lifecycle at arrival.

## Hardening candidates (NOT applied; would need testing)

1. In FinishMove: check AddUnitSelection's result; on failure, at minimum
   clear flag 0x04 on the MOVER (clear it before the te.army swap).
2. In ExecuteMove: use MoveTo's return value; on veto (0), keep te.army
   and finish the move normally on the old hex so FinishMove cleanup runs.
3. In FinishMove: if GetNoneMovingArmyHS returns NULL on a hex that
   contains a same-player army, retry ignoring flag 0x04 (or clear a
   stale flag when the flagged army has no active move TE).

All three are small cave patches in the same style as the movement fix,
but each changes behavior in a code path with network/AI implications, so
none should ship untested.
