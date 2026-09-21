# Unit Spellcasting — Implementation Log (2026-07-05)

Implements the plan in `Unit_Spellcasting_Feasibility_2026-07-05.md`. Phases 0, 1, and the
enable-side of Phase 2 are **APPLIED and byte-verified**; the two remaining Phase-2 caves
(multi-turn progress, save persistence) are **specified and staged** for a test-gated follow-up.

Everything was verified against the live binaries (VMT offsets, gate encodings, `.reloc`
coverage, cave space) before writing. Rebase-safe by construction (all caves are
register/immediate/rel32 only — no absolute memory refs; overwritten VMT slots already carry
`.reloc` entries). Idempotent, verify-before-write, per-module backups.

## Files / build / revert

| Script (in Modding Resources) | Module | Backup (install dir) | Applies |
|---|---|---|---|
| `build_spellcast.py` | AoWEPACK.dpl | `AoWEPACK.dpl.pre-spellcast` | Phase 1a + strategic enable (18 patches) |
| `build_spellcast_tcpck.py` | AoWTCPCK.dpl | `AoWTCPCK.dpl.pre-spellcast` | Phase 1b tactical gate (5 patches) |

- Re-run either script with no args to **verify** (idempotent; refuses on byte mismatch),
  or `--apply` to write. Both currently report fully applied.
- **Revert spellcasting only:** ⚠ **not by snapshot for the DLL.**
  `AoWEPACK.dpl.pre-spellcast` was **moved** to `Modding Resources/backups/` on 2026-07-29/30 and is the
  **oldest of 47** layers — copying it back destroys 46 later features. `AoWTCPCK.dpl.pre-spellcast` is
  still in the game root and is that file's **only** layer, so it *is* a safe single revert. Undo the DLL
  half surgically; that also keeps the movement-predictor fix intact.
- **Revert everything:** the truly pristine pre-modding DLL is
  `Modding Resources/AoWEPACK_original_backup.dpl` (md5 `08149246…`). Note
  `Modding Resources/backups/AoWEPACK.dpl.bak` is **not** the same file (md5 `a4a4ad7f…`, dated
  2026-04-06) — it is a mid-modding snapshot, so don't treat it as vanilla. For TCPCK, the vanilla copy is
  `Backups/AoWTCPCK - vanilla.dpl` (`AoWTCPCK.dpl.bak` in the root is *not* verified vanilla).
- MP: both peers must run identically patched binaries.

## Phase 0 — EXE / TCPCK triage (done)

Disassembled AoW.exe and AoWTCPCK.dpl with capstone (they are not in the Ghidra project).

- **AoW.exe strategic casting UI is caster-generic.** All casting calls operate on a
  UI-held object pointer with **no `is THero` gate**: `CastSpell` ×3 (0x43087D/0x4308B8/0x430F83),
  `CastCombatSpell` (0x4308EC), `CanCastSpellInstantly` (0x42EB8E), `ListSpells` ×5. The 7
  `is THero` sites in the EXE are hero-panel / combat-map highlight / wizard-tower / face
  display — **not** casting gates. ⇒ **No EXE patch needed** for strategic casting; enabling the
  ability button (AoWEPACK G1) is sufficient.
- **AoWTCPCK.dpl tactical "can cast" check is gated.** 22 `is THero` sites; the 4 that matter
  each read `combatUnit+0x4C` (the strategic unit) under `cmp ability,0x34; jne` and feed
  `THero.CanCastSpellInstantly`. Those are the Phase-1b targets (below). `CombatSpellCast`
  itself is generic.

## Phase 1a — auto / fast combat  (APPLIED, AoWEPACK)

- **D1/D2** grow `TUnit` (VMT 0x55710CAC, size word 0x55710C90) and `TAdjustableUnit`
  (0x55712A54 / 0x55712A38) instance size **0x48 → 0x94**, so every unit carries the hero
  casting cluster at THero's own offsets (+0x7C..+0x93), zero-filled by the allocator.
- **D3/D4/D5** redirect VMT slots **+0x128 GetCastingPointsMax, +0x12C GetCastingPoints,
  +0x130 SetCastingPoints** (both classes) from the TAbstractUnit `return 0` stubs to THero's
  class-agnostic impls (0x55788614 / 0x55788644 / 0x5578864C).
- **C1 (refill)** installs `cave_unit_newturn` at VMT **+0x13C**: calls `TAbstractUnit.NewTurn`
  then, on the owner's turn, `points(+0x80) := GetCastingPointsMax()` — exactly THero's refill
  line, nothing hero-only. Level→points table 10/20/40/60/90.
- **Gates → `cave_iscaster`** (returns `obj.GetAbilityEnabled(0x34)`; walls & non-casters fail
  cleanly, no OOB): **G2** fcPrefetchCombatCommands (0x5576E418), **G3** CanCastBreachWallSpell
  (0x5576DF17), **G5** CombatCastingDone (0x5577950C), **G7** CombatSpell.fcPrefetch (0x557F76EB),
  **G4** strategic CastingDone (0x557794CD).
- Cave at **0x5580D900** (after the move-fix cave): `cave_iscaster` (13 B) + `cave_unit_newturn`
  (46 B).

Result: a unit with Spellcasting casts the player's researched combat spells in auto-resolve
and fast combat, with per-turn point refill and correct point/mana accounting.

## Phase 1b — manual / tactical combat  (APPLIED, AoWTCPCK)

- Retarget the 4 `call @IsClass 0x401058` tactical "can-cast" gates
  (**0x418739, 0x418B86, 0x418F71, 0x4195D4**) to a TCPCK-local `cave_iscaster` at **0x438100**
  (same 3-instruction GetAbilityEnabled thunk; the gated object is `combatUnit+0x4C`, a
  TAbstractUnit descendant, so `vtable+0x148` is valid).

Result: the tactical-combat "can this unit cast" check passes for Spellcasting units. If the
cast *button/target UI* turns out to be gated by an additional TCPCK `is THero` site (one of the
other 18), that surfaces as "button doesn't appear" — report it and it's the same one-line fix.

## Phase 2 (enable side) — strategic casting  (APPLIED, AoWEPACK)

- **G1** SpellCastingAbility.CanActivate (0x5576DEB7) → `cave_iscaster`: **enables the strategic
  Spellcasting ability button** for units. Because the EXE casting UI is generic (Phase 0), the
  spellbook then opens and casts on the unit via the existing `THero.CastSpell` path (verified
  to touch only the cluster + virtuals).
- **G6** SpellCastEventLog.Execute (0x5577A25C) → `cave_iscaster`: recast-ready handler accepts
  units (inert until multi-turn progress lands).

Result: a unit can cast **instant** strategic spells — any spell whose cost ≤ the unit's current
casting points. See limitation below for multi-turn.

## Remaining Phase 2 — STAGED (not applied; need test feedback)

These are deliberately not blind-applied: they are the higher-consequence, untestable-by-me
caves, and the move-fix history shows in-game testing is where the real bugs surface. Apply after
the applied pieces are confirmed working.

1. **C1-progress (multi-turn strategic casting).** Extend `cave_unit_newturn` to replicate
   THero.NewTurn's progress block: pour refilled points into `+0x88` toward `+0x8C`, and on
   completion raise `TSpellCastEventLog{owner,+0x18 unitID,+0x84 spellID}` (needs `AoWHSMap`
   0x558FA040 + the event class ptr via the call/pop delta trick — rebase rule). Until this lands,
   **starting an unaffordable (multi-turn) strategic cast leaves the unit "casting" with no
   progress** — it does not crash and is cancellable, but avoid it while testing.
2. **C2-persistence.** Wrap `TUnit.ReadWrite` (VMT +0x18, currently 0x55782CEC) to serialize the
   5 cluster fields with fresh tags (THero uses 0x0D/0x0E/0x1F/0x22/0x23; TUnit's stream is free
   from tag 0x0B up). Save format is tag+default+version-guarded, so old saves load with a zeroed
   cluster. Until this lands, **casting points reset to full on load and an in-progress strategic
   cast is lost on save/reload** (cosmetic/minor).

## UI — casting points on the unit card  (APPLIED, AoW.exe + AoWCompat.exe)

`build_spellcast_card.py` (backups `AoW.exe.pre-spellcast`, `AoWCompat.exe.pre-spellcast`;
run with an exe name arg, default AoW.exe). The unit-info window at 0x433A64 computed
`edi = (unit is THero) ? unit : nil` and only drew the casting-points number + diamond when
`edi<>nil` (and `GetCastingPointsMax > 0`). Mundane units failed `is THero`, hiding their now-real
points. Fix: retarget the `call @IsClass` at 0x433A6C to a **nil-safe** `cave_iscaster`
(`GetAbilityEnabled(0x34)`) in the CODE end-padding (0x459FEC, exactly 20 B). The display
condition becomes "has Spellcasting" — units with Spellcasting now show `cur/max`, and
heroes-without-Spellcasting stay hidden as before. The gated object can be nil here (unlike the
combat gates), hence the cave's `test eax,eax` guard. Both EXEs patched since either can launch.

## Scope decisions (2026-07-05, user)

- **Multi-turn channelling for units: leave disabled** — not a bug to fix; single-turn-only casting
  may be desirable. So the staged **C1-progress cave is on hold indefinitely** (not just deferred).
- **Mana generation for unit casters: never enable** — would wreck the economy. Phase 3 below
  (`D6`/`C3`) is **cancelled**, not deferred. Units cast using the *player's* mana pool, throttled
  by their own casting points; they must not become mana *sources*.

## Phase 3 — mana generation  (CANCELLED — do not implement)

`D6` (VMT +0x134 GetPowerGeneration) + `C3` (THeroPowerSource lifecycle). **Intentionally never
applied** per the scope decision above — unit casters must not generate mana.

## Test plan (in priority order)

Prereqs: unit given the Spellcasting ability (editor/library); the **player has researched
spells** (units cast from the *player's* spellbook, like heroes); confirm the unit shows casting
points (level 1 = 10).

1. **Auto/fast combat (1a):** army with a Spellcasting unit auto-resolves a fight → unit casts
   affordable combat spells; points deplete; heroes unaffected.
2. **Manual tactical (1b):** enter tactical combat with the unit → cast option available; cast an
   affordable combat spell.
3. **Strategic instant (2):** select the unit on the map → Spellcasting button **enabled** →
   open spellbook → cast a spell with cost ≤ the unit's points → resolves, mana/points deducted.
   **Do not** start an expensive (multi-turn) cast yet (would hang, cancellable).
4. **Regressions:** heroes cast normally (combat + strategic); non-caster units & walls behave as
   before; existing saves load; both MP peers patched.

Report which steps work; that gates applying the staged C1-progress / C2-persistence caves.

## Provenance

capstone 5.0.7 / keystone 0.9.2 for EXE/TCPCK analysis and cave assembly; Ghidra MCP for
AoWEPACK. Verification scripts in session scratchpad (sc_verify / reloc_check / triage*/tcpck_gate).
Cluster offsets, VMT slots, gate encodings and `.reloc` coverage all confirmed on the live files.
