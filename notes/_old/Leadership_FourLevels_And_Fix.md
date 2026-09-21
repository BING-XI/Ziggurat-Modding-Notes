# Leadership — 4 levels (I/II/III/IV) + the disable-bug fix

**Status: CONFIRMED WORKING (2026-07-20)** — validated in-game by the user ("All working"), covering
both the 4-level ability and the disable-bug fix. Skill cost subsequently re-tuned 20 → **10** per
level on the same day (see §1); that re-tune was applied by a revert-and-re-apply route which is no
longer available (see **Revert** below) and re-verified by disassembly, but the 10-point cost itself has
not been separately play-tested.

| # | Feature | Script | Revert | Caves |
|---|---|---|---|---|
| 1 | 4-level Leadership | `build_scripts/build_leadership4.py` | ⚠ **no `--undo` yet** — see below | `0x5580EFC0`, `0x5580F000`, data `0x5580F0C0` |
| 2 | Disable-bug fix | `build_scripts/build_leadership_fix.py` | `--undo` (surgical, added 2026-09-02) | `0x5580F100` |
| 3 | Aura instant-refresh (§8) | `build_scripts/build_leadership_aura.py` | `--undo` (surgical, added 2026-09-02) | `0x5580F140` |

**Revert — ⚠ there are no snapshots. Use the scripts' `--undo`.** All three `.pre-leadership*` files are
**gone**: they were moved into `Modding Resources/backups/` on 2026-07-29/30, and that whole directory
was deleted on 2026-08-08 (see CLAUDE.md). Do not go looking for them, and disregard any doc that still
quotes their layer numbers — a snapshot restore was never a safe route here anyway, because each was a
layered image whose restore destroyed every feature applied after it.

To remove or re-tune these features:
- **Undo surgically — features 2 and 3 now do this for you.** `build_leadership_fix.py --undo` restores
  both 8-byte call sites and zeroes `cave_abinherent`; `build_leadership_aura.py --undo` repoints the
  hooked call back at `TAbilityOwner.UpdateDefaultAbilities` and zeroes `cave_auraup`. Both verify
  before writing (every byte must read as either ours or vanilla), abort on anything foreign, no-op
  when already vanilla, and touch no backup. Round-tripped byte-identical (sha256) on 2026-09-02.
- ⚠ **Feature 1 still has no `--undo`.** Reverting the 4-level ability by hand means restoring its five
  hook sites and zeroing all three cave zones. Adding a real `--undo` is the right fix if a rollback is
  ever needed — copy the shape from `build_leadership_fix.py`, whose `patches` table already encodes the
  undo (each entry's `orig` is the vanilla run for a hook and all-zeroes for a cave, so reverting is
  just writing `orig` everywhere).
- **Re-tune the curve/costs by rewriting the caves in place** — accept either the installed or the new
  bytes, overwrite, assert the growth zone is still zero. Pattern:
  `build_scripts/build_invis_penalty.py`; `build_leadership4.py` already does exactly this (see §1).
  Caves do resize when constants change, so the free-space assert still matters.
- ⚠ **Never a revert-and-re-apply.** Kept as the worked example of how such a procedure rots: this doc
  once said "revert `.pre-leadership4` first, delete the two later backups, re-apply 1 → 2 → 3". That
  was right the day it was written; by 2026-07-21 three unrelated layers had stacked on the DLL, by
  2026-07-30 it cost 24 features, and by 2026-08-08 the snapshots it named did not exist. Nothing in
  the doc changed when it stopped being right — which is the whole argument for surgical `--undo`.

**Follow-on (2026-09-01, APPLIED / UNTESTED): Leadership IV also makes the whole stack count as
Fearless** — `build_scripts/build_leadership_fearless.py`, full write-up in
`Leadership4_Grants_Fearless.md`. It writes nothing to any unit: it derives the answer at query
time from the borrowed level this doc's aura already propagates, so it is independent of all
three features above and shares no cave with them.

Both features are functionally independent (disjoint patch addresses, disjoint caves). All addresses
are AoWEPACK.dpl preferred-base VAs (base `0x55700000`); the package rebases at runtime, so every cave
is position-independent.

---

## 1. What shipped vs what we changed

Leadership (id `0x2e`) is `TLeadershipAbility : TMultiLevelAbility : TAbility` — it already sat on the
engine's multi-level framework (working `CanExpand`/`Expand`/`ExpandCost`/`GetSkillPoints`, a per-level
cost `TIntegerList`, and a per-owner record whose `+0x0c` byte is the level, already serialised to
saves). Three things pinned it to one level, all now lifted:

| # | Vanilla | Now |
|---|---|---|
| 1 | `TLeadershipAbility.Create` @ `0x5576616C` calls the base ctor (which sets cap `[+0x28] = 4`) then **stomps it to 1** @ `0x55766187` | cap = **4** |
| 2 | The ctor populates only `cost[1] = 20`; levels 2-4 had no defined cost | `cost[1..4] = 10` each |
| 3 | `TLeadershipAbility.GetLevelName` @ `0x557663D0` **ignores its level argument**, always returning bare "Leadership" | appends ` I` / ` II` / ` III` / ` IV` |

### Chosen curve and cost (user decision, 2026-07-19; cost re-tuned 2026-07-20)

| Level | Attack | Defense | Cost | Cumulative | hit chance |
|---|---|---|---|---|---|
| I | +1 | +1 | 10 | 10 | +5 pp |
| II | +2 | +2 | 10 | 20 | +10 pp |
| III | +3 | +3 | 10 | 30 | +15 pp |
| IV | +4 | +4 | 10 | 40 | +20 pp |

**Re-tuned 2026-08-20** (user) from ATK `+1/+1/+2/+2`, DEF `+0/+1/+1/+2`; the re-tuned curve is
**CONFIRMED WORKING in game 2026-08-24**. These are RAW table values
on the post-conversion **doubled** stat scale: Leadership is a D2 exception, deliberately not doubled
by `build_statdouble.py`, so this table is the only place its strength is set. One point now buys
5 pp, making the curve a flat ramp and putting level IV back at vanilla's effective +20 pp.

Cost was 20/level as first built (80 to reach IV) and re-tuned to **10** (40 to reach IV) after the
in-game test. Change cost via `COST_EACH` and the curve via `ATK_BONUS` / `DEF_BONUS` in
`build_leadership4.py`, then just re-run it with `--apply`.

⚠ **The old instruction here said the free-space guard refuses to overwrite a populated cave, so a
re-tune needed a revert first. That is no longer true and was never the right procedure** (the revert
would now cost 24 later features). The guard was fixed 2026-08-20: it identifies the 16-byte suffix-VA
block at `DATA_TAB+0x10` as this script's own signature, and when it matches, treats the curve bytes
in front of it as ours to rewrite whatever they hold. It prints `[~ ] ... re-tuning in place` and the
old→new curve. Re-tuning is now a one-command, in-place operation with no backup involved.

⚠ **This deliberately re-balances level 1 downward.** Vanilla level 1 was +2/+1 — that is now level
**III**. Existing level-1 leaders (hero chassis, medal units) get *weaker*; the ceiling rises to +2/+2.
Intentional, but it is the thing to sanity-check first in-game.

---

## 2. The bonus tables (and the trap in them)

`GetAttack` @ `0x557661FC` / `GetDefense` @ `0x55766210` are:

```
mov ecx,[eax] / call [ecx+0x70]     ; GetLevel
test eax,eax / je -> return 0       ; level 0 never indexes the table
mov al, byte ptr [eax + <TABLE>]    ; <-- disp32, has a .reloc entry
```

**Vanilla packs the two tables back-to-back, 4 bytes apart** — attack at `0x558E83E7`, defense at
`0x558E83EB`. So `attack[4]` would read `defense[0]`. ⚠ **CORRECTION 2026-09-10:** those are the **LIVE** bytes, recorded from an already-patched DLL.
**Vanilla Leadership was +1 ATK / +0 DEF, with only ONE functional level** (owner, 2026-09-10):
vanilla's MAX_LEVEL is 1, so only index 1 was ever read. The raw bytes continue as attack
`[_,1,1,2]` / defense `[_,0,1,1]`, but indices 2..4 are dead data — not a vanilla ramp. Index 0 is
dead in both because of the early return.

Curiosity worth recording: the bytes immediately past each vanilla table are `02` and `01`, so a
naive cap-raise to 4 with **no** table change would have read `+2/+1` at level IV purely by
adjacency — correct-looking, but accidental. We did not rely on it.

**Both tables were relocated** into the cave block as 5-byte tables and the two disp32 fields
repointed:

| Table | New VA | Bytes (levels 0..4) |
|---|---|---|
| attack | `0x5580F0C0` | `00 01 02 03 04` |
| defense | `0x5580F0C8` | `00 01 02 03 04` |

These are the **live** bytes, re-read from `AoWEPACK.dpl` on 2026-09-02 and matching §1's re-tuned
+1/+2/+3/+4 curve. They are emitted from `ATK_BONUS` / `DEF_BONUS` in the script, so they change
whenever the curve is re-tuned — read them out rather than quoting this table:

```bash
python "Modding Resources/build_scripts/build_leadership4.py"   # prints `[data ] 5580F0C0 atk=... def=...`
```

(The pre-2026-08-20 curve was attack `00 01 01 02 02` / defense `00 00 01 01 02`. This table went
stale for twelve days because §1 was updated at the re-tune and §2 was not — hence the read-it-out
command above.)

Both displacements carry `.reloc` entries (verified by parsing `.reloc`: 63883 entries, both present),
so the loader keeps fixing them up after the rebase — we changed only the *value*, never removed the
relocation. This is the reusable trick: **an existing absolute operand with a reloc can be repointed
anywhere in the image and stays rebase-correct.**

---

## 3. Level names — reusing the game's own idiom

`TMultiLevelAbility.GetName` @ `0x55765298` is `GetLevelName(GetLevel(owner))`, and `ExpandName`
@ `0x557652BC` is `GetLevelName(level+1)`. So fixing `GetLevelName` feeds both the unit card and the
hero level-up dialog for free.

`TMarksmanshipAbility.GetLevelName` @ `0x557BBDEC` and `TVisionAbility.GetLevelName` @ `0x557B98F8`
show the engine's own pattern: `LoadResString(name)` → `TranslateRStr` → `System.@LStrCat3(out, name,
suffixLiteral)`, with a per-level literal. Their suffix literals are **constant Delphi AnsiStrings
(refcount −1)**:

| Level | VA | Value |
|---|---|---|
| 1 | `0x557BBF18` | `" I"` |
| 2 | `0x557BBF24` | `" II"` |
| 3 | `0x557BBF30` | `" III"` |
| 4 | `0x557BBF40` | `" IV"` |

`cave_lsname` @ `0x5580F000` **reuses those literals** rather than fabricating new Delphi strings. It
calls the *original* `GetLevelName` into a stack temp (so resource loading + SEH stay in vanilla code),
then `LStrCat3`s the suffix, `LStrAsg`s unchanged when the level is outside 1..4, and `LStrClr`s the
temp. Hooked by repointing **`TLeadershipAbility` VMT `+0x10c` @ `0x55722114`** — verified to be the
*only* reference to `GetLevelName` in the module, so the VMT repoint catches every caller. (Entry-jmp
hooking was not an option: the cave calls the original, which would recurse.)

Delphi string helper conventions used (worth reusing):
`@LStrCat3` @ `0x55701190` = `(EAX=dest, EDX=s1, ECX=s2)`; `@LStrAsg` @ `0x55701150` = `(EAX=&dest,
EDX=src)`; `@LStrClr` @ `0x55701140` = `(EAX=&str)`.

---

## 4. The disable-bug fix

Root cause is documented in full in **`Leadership_Disable_Bug_RootCause.md`** §4-5. In brief:
`TAbilityOwner.UpdateDefaultAbilities` @ `0x5574F518` compared **effective** ability levels
(own ∪ aura-borrowed) via VMT `+0x84` = `GetAbLevel` @ `0x5574FD44`, so a unit earning Leadership
inside another leader's aura already "looked" level 1 and its inherent record was never copied — only
the bit was set. `ResetExternalSource` @ `0x557662E4` then deleted the leftover aura-only record *and*
the bit, permanently (no re-grant path fires: `NewDay`'s rebuild is day-1 gated @ `0x55782CA9`,
`SetExperience` needs a rank change that never comes at gold medal).

**Fix: compare inherent levels.** The engine already has the right accessor and simply wasn't using it
here — `TMultiLevelAbility.GetInherentLevel` @ `0x55765200` (ability VMT `+0x94`) returns only
`data[+0x0c]`. Both call sites now route through `cave_abinherent` @ `0x5580F100`, a mirror of
`GetAbLevel` dispatching VMT `+0x94` instead of `+0x70`:

| Site | Was | Now |
|---|---|---|
| `0x5574F54D` (template level) | `mov ecx,[eax]` + `call [ecx+0x84]` (8 B) | `call 0x5580F100` + 3× `nop` |
| `0x5574F55B` (unit level) | same 8 B | same |

Register contract is identical to `GetAbLevel` (in `EAX`=owner, `EDX`=id; out `EAX`=level; `EBX`/`ESI`
preserved, `EDI`/`EBP` untouched — the loop uses all four).

**Why this is safe for every other ability.** `UpdateDefaultAbilities` loops over *all* ability ids, so
the change is global — but it is a no-op for anything not multi-level: base `TAbility.GetLevel`
@ `0x5574E9B0` and `TAbility.GetInherentLevel` @ `0x5574E954` **both `return 0`**, so plain abilities
compare 0 vs 0 either way. For genuinely multi-level abilities it is strictly better: a unit with
inherent 1 + borrowed 3, granted a level-2 template, now upgrades to 2 instead of being skipped.

Defect (B), the `own == 0` test in `ResetExternalSource`, was deliberately left alone: once (A) stops
discarding the inherent record, that test correctly identifies genuinely-borrowed records, which is
what it was written for.

### Interaction with the 4-level work

The two are independent, but the fix matters *more* now. With a cap of 4 the masking window widens:
any grant whose template level is ≤ the borrowed aura level would have been skipped, so a level-2 medal
under a level-2+ leader would have been lost exactly like a level-1 one. Raising the cap alone would
**not** have fixed the bug (the earlier "two-for-one" guess) — and the fix alone would not add levels.

---

## 5. Position independence

The `.dpl` rebases, so no cave may contain an un-relocated absolute reference.
- `cave_lscosts` — rel32 only.
- `cave_lsname` and `cave_abinherent` need absolute data (the suffix-pointer table; the `AoWHSSet`
  global `0x558FA044`). Both compute the **load delta** with the standard call/pop trick
  (`call _n; pop reg; sub reg, <link addr of _n>`) and address data as `[delta + link-time VA]`. In
  `cave_lsname` the stored suffix dwords are link-time VAs to which the same delta is added.
  The build scripts assemble the prologue separately to derive the anchor address, then `assert` the
  expected `pop` opcode lands there — so the trick can't silently drift if the prologue is edited.

---

## 6. Regression checklist (passed 2026-07-20; re-run after any re-tune)

1. **Bug fix (the point of it):** gold-medal a Leadership-capable unit **while it is stacked under a
   Leadership hero**, then split it off. The ability must survive. Under vanilla it vanishes for good.
2. **Vanilla-correct path unchanged:** rank a unit up **alone** — it should get exactly one level.
3. **Genuine aura still transient:** a unit with *no* Leadership standing under a leader should still
   lose the borrowed Leadership when it leaves (the aura GC must still work).
4. **Levels:** spend hero skill points to II / III / IV — check the cost is 10 each, `CanExpand` stops
   at IV, and the unit card / level-up dialog read "Leadership I…IV".
5. **Curve:** confirm the attack/defense deltas match §1 — +1/+1, +2/+2, +3/+3, +4/+4. Easiest read
   is a level-IV leader's unit card: +4 attack and +4 defence on every unit in the stack.
6. **Save/load:** the level byte `+0x0c` already serialised in vanilla, so a level-3 leader should
   survive a save/load round-trip.

Only the cost (item 4) changed in the 2026-07-20 re-tune; the patch set is otherwise byte-identical to
the build the user validated, so items 1-3, 5 and 6 are unaffected by it.

---

## 8. Aura instant-refresh (APPLIED, UNTESTED 2026-07-20)

**Idea and original implementation: a fellow modder** (`patch_leadership_aura_refresh_v1.py`, written
against their own build). Re-verified against our DLL and adapted — `build_leadership_aura.py`;
revert with `--undo` (surgical), **not** with the long-deleted `.pre-leadershipaura` snapshot.

**Problem it solves** (distinct from §4's bug): after buying a Leadership level in the hero level-up
UI, party units don't get the new aura bonus until the army next updates — a move, or next turn. The
level applies immediately; only the *aura* is stale.

**Fix.** `THeroUpgradeTE.Execute` @ `0x55785450` ends with:

```
557854DE  mov  eax, edi                 ; EDI = the hero
557854E0  call TAbilityOwner.UpdateDefaultAbilities    <-- repointed
557854E5  mov  byte [edi+0x54], 0       ; clear upgrade-pending (c6 47 54 00)
```

That call is repointed to `cave_auraup` @ `0x5580F140`, which runs the original and then:

```
army = [hero+0x4]
if army && IsClass(army, TArmy):  TArmy.UpdateFormation(army)
```

`UpdateFormation` @ `0x5578D034` is the engine's sole aura recomputer (§3 of the root-cause doc) — the
same routine that runs on move/turn — so behaviour is identical, just immediate. The hook is the last
thing `Execute` does before clearing the flag, and the TE's ability grant runs through that very
`UpdateDefaultAbilities` call (`EDX = [esi+0x1c]`), so it catches stat deltas *and* the level grant.

**Verified in our DLL, not assumed:**
- `[0x557130AC]` → VMT `0x557130EC`, Delphi class name **"TArmy"**.
- `[unit+0x4]` is the container, and the `IsClass(TArmy)` guard is *vanilla's own* idiom — see
  `TAbstractUnit.MovedTo+0xce` @ `0x557803EF` and `UpdateMoraleValue+0x5f` @ `0x5577F0B2`.
- The `mov byte [edi+0x54],0` following the hook is asserted at build time to pin the function version.

**MP-safe:** `THeroUpgradeTE` is a network-distributed token event executing on every peer, and
`UpdateFormation` is deterministic (no RNG), so all peers recompute the same aura.

**⚠ Their cave address could not be reused.** The original used `0x5580E120`; in our DLL that holds
live `build_assassin.py` code (`mov edx,0x70 … call [ecx+0xa8] … mov edx,0x3f` — the Monster-Slaying
test). Applying their script unmodified **would have silently destroyed the slayer feature.** Ours
sits at `0x5580F140`, in the free run starting `0x5580F131`. General lesson: *never* trust a cave
address from another modder's build — re-scan for free space in your own binary first.

Other adaptations: `.dpl` not `.dll`; real PE section mapping instead of the flat
`FILE_DELTA = 0x55700C00` (correct for CODE here, but silently wrong for any non-CODE address);
keystone-assembled with a two-pass call/pop anchor resolve plus an assert; project conventions for
dry-run/backup/idempotency.

**Composition:** wraps a *call to* `UpdateDefaultAbilities`, while §4's fix changes that function's
*internals* — disjoint, and both verified still applied afterwards.

**Test:** buy a Leadership level on a hero standing in a stack, and check the other units' attack /
defense update *immediately*, without moving or ending the turn.

---

## 7. Address quick-reference

| Symbol | VA | Role |
|---|---|---|
| `TLeadershipAbility.Create` | `0x5576616C` | ctor; cap imm32 @ `0x5576618A` (1→4); cost `call` @ `0x557661A2` |
| `TMultiLevelAbility.Create` | `0x55765168` | base ctor — sets cap `[+0x28] = 4`, allocates cost list `[+0x2c]` |
| `TLeadershipAbility.CanExpand` | `0x557663A8` | `own < cap` (auto-follows the raised cap) |
| `TMultiLevelAbility.ExpandCost` / `GetSkillPoints` | `0x557652E4` / `0x55765348` | `cost[level+1]` / sum `cost[1..level]` |
| `TLeadershipAbility.GetAttack` / `GetDefense` | `0x557661FC` / `0x55766210` | disp32 @ `0x55766207` / `0x5576621B` (both relocated) |
| `TLeadershipAbility.GetLevelName` | `0x557663D0` | original; still called by the cave |
| `TLeadershipAbility` VMT `+0x10c` | `0x55722114` | repointed to `cave_lsname` (vmt base `0x55722008`) |
| `TMultiLevelAbility.GetName` / `ExpandName` | `0x55765298` / `0x557652BC` | both route through `GetLevelName` |
| `TAbilityOwner.UpdateDefaultAbilities` | `0x5574F518` | the bug; patched @ `0x5574F54D` / `0x5574F55B` |
| `TAbilityOwner.GetAbLevel` | `0x5574FD44` | VMT `+0x84`; effective level (the wrong term) |
| `TMultiLevelAbility.GetInherentLevel` | `0x55765200` | ability VMT `+0x94`; the right term |
| `THeroUpgradeTE.Execute` | `0x55785450` | level-up applier; `call UDA` @ `0x557854E0` repointed (§8) |
| `TArmy.UpdateFormation` | `0x5578D034` | sole aura recomputer (EAX=army) |
| TArmy classref global | `0x557130AC` | → VMT `0x557130EC` "TArmy"; vanilla guard idiom |
| `System.@IsClass` | `0x557010C0` | `(EAX=obj, EDX=class) -> AL` |
| `TAbilityControl.GetAbility` | `0x557501C0` | `(EAX=control, EDX=id) -> EAX=ability` |
| `TIntegerList.Put` | `0x55702EB4` | `(EAX=list, EDX=idx, ECX=val)` |
| `AoWHSSet` global | `0x558FA044` | registry at `+0x80` |
| Marksmanship suffix literals | `0x557BBF18/24/30/40` | `" I" " II" " III" " IV"`, refcount −1 |
