# Panicked units cannot initiate melee (but still retaliate)

**Status: APPLIED 2026-08-31 — UNTESTED. Needs the user's in-game test (§9).**
Built by `build_scripts/build_panic_nomelee.py`; five hooks across two `.dpl`s, surgical `--undo`.
Every address below was derived from the live binaries; the AoWEPACK sites were byte-diffed against
`AoWEPACK_original_backup.dpl` and were **pristine** before patching. The AoWTCPCK sites were
unclaimed by any existing `build_*.py` (grepped) and held their vanilla instruction bytes.

```bash
python "Modding Resources/build_scripts/build_panic_nomelee.py" --undo
```

**Goal (user's words):** Panicked units cannot initiate melee strikes, but can still retaliate —
"rather like how melee walkers cannot attack flyers offensively, but can retaliate."

**Verdict: FEASIBLE, and the analogy is exact.** The flying rule is implemented the way the user
guessed, and copying its design gives the retaliation behaviour *for free*, with no change to any
combat arithmetic.

---

## 1. The load-bearing fact

> **`AoWE.TMeleeRound.Calculate @0x55767D24` contains no flying test at all.**

The whole flying rule lives in the "may I *initiate*?" gates upstream. Once a melee round is
built, both sides' strike counts are computed from their own properties only:

| field | meaning | forced to 0 by |
|---|---|---|
| `round+0x28` | attacker strike count (2, +1 for ExtraStrike `0x73`) | `MeleeDamageTypes == 0`, or `GetLocked` (VMT `+0x64`) |
| `round+0x2C` | defender strike count (2, **no** ExtraStrike) | `MeleeDamageTypes == 0`, or `GetLocked` |

So a ground unit *does* get its two retaliation strikes against a flyer that attacked it — nothing
in the round knows or cares that the reverse attack would have been illegal. **Panic gated the same
way inherits the same property.** Verified byte-identical to pristine.

This is also why the round is the *wrong* place to patch: zeroing `round+0x28` would make the
panicked unit's swings whiff rather than making the order illegal, and it would fire on
retaliation rounds too (where the panicked unit is the *defender*, and `+0x28` belongs to whoever
initiated).

## 2. ⚠ The trap: do NOT add `0x6C` to `GetLocked`

`AoWE.TCombatUnit.GetLocked @0x55724BA4` is vanilla's "this unit is incapacitated" predicate —
true if the unit has ability `0x5F`, `0x61`, `0x5C`, `0x5E` (Entangled) or `0x22`. It is the
obvious-looking place to add Panicked `0x6C`, and it is **wrong for this feature**: `Calculate`
consults it for *both* sides, so a panicked unit would stop retaliating as well. `GetLocked` is
the "webbed/frozen/stunned" mechanism — total incapacity. Panic is not that.

## 3. How the flying rule actually works — all six sites

Ability id **1 = Flying**, queried through `TCombatObject` VMT `+0xA8` `GetAbilityEnabled`
(item-aware; forwards to `[cu+0x4c].vtable[0x148]`). Found exhaustively with
`re_tools/abquery.py <module> --id 0x01`.

There are **two different rules**, and they are easy to confuse:

### 3a. One-way "can't hit what's above you" — the rule this feature copies

Shape: `if target.Flying and not attacker.Flying → forbidden`.

| # | module | site | gates |
|---|---|---|---|
| 1 | AoWTCPCK | `AoWTC.TCombatUnitSelectionControl.UpdateMoveCursor @0x0041FA7F` | the human player's attack cursor |
| 2 | AoWTCPCK | `AoWTC.TCAI.CheckUnit @0x00415478` | the tactical AI's melee evaluation |
| 3 | AoWEPACK | `AoWE.TStrikeAbility.CanExecuteMelee @0x55766B75` | auto-resolve melee command prefetch |
| 4 | AoWEPACK | `AoWE.TStrikeAbility.fcGetDamageValueEx @0x55766CA7` | auto-resolve target scoring (DV := 0) |
| 5 | AoWEPACK | `AoWE.TTouchAbility.CanTouch @0x55768346` | touch abilities, **tactical and fast** (no `fc` prefix) |

Site 4 is already written up in `Raze_CombatPredictor_Analysis.md` (with the consequence that a
melee-only unit's combat value against a flyer is 0, so it drops out of the raze simulation
entirely). Sites 1, 2, 3 and 5 were previously undocumented.

⚠ **All of them test `id 1` only.** Floating (`0x3B`) and WindWalking are not covered — noted in
the raze doc, still true.

### 3b. Two-way "same altitude" — a *different* rule, do not confuse with the above

Shape: `if attacker.Flying != target.Flying → no engagement`. These govern incidental melee, not
deliberate attacks:

| module | site | governs |
|---|---|---|
| AoWTCPCK | `CombatTE.TCombatMoveTE.ExecuteDefaultMove @0x00408749` | the free / opportunity swing taken when a unit moves past an enemy |
| AoWTCPCK | `AoWTC.TTacticalCombatUnitHS.CanMoveOn @0x00420BE9` | the zone-of-control move-cost surcharge (`+0x1E`, clamped to `0x7F`) |

### 3c. There is no hard gate, and vanilla doesn't need one

`AoWTC.TTacticalCombatUnitHS.MeleeMoveTC @0x00422CD8` is the **single creation point for every
deliberate tactical melee** — `re_tools/xref.py AoWTCPCK.dpl 0x422cd8` gives exactly two callers:

- `AoWTC.TCAI.EvalBattle+0x2a04 @0x0041AB74` (the AI)
- `AoWTC.TCombatUnitSelectionControl.MoveSelectedRoute+0x1ca @0x0041E1E6` (the player)

and it contains **no flying test**. Vanilla enforces the rule purely by never letting an illegal
order be constructed: the cursor refuses it for the player, `CheckUnit` never scores it for the AI.
`MeleeMoveTC` is nonetheless available as a belt-and-braces hard gate (see §5).

`CanMoveOn` does **not** block pathing onto a flyer's hex — its first arm marks an enemy-occupied
hex as an attack (`*out = 0`) whenever the occupant can fight back at the mover's altitude, and
routes a flyer *over* a ground unit as ordinary movement. It is not part of rule 3a.

## 4. Panicked `0x6C` is a normal, queryable ability

Applied to the defender on a Cause Fear (`0x33`) hit; a `TDurationAbility` (a timer with no owner,
so Dispel Magic cannot strip it). Its only current mechanical effect is a **−80 morale value**,
which always lands the unit in the terrible band — on this install that is **ATK −4 / RES −6 /
DEF 0** (see `aow1-morale-three-stats`). It has no stat row of its own.

Existing consumers, from `abquery.py --id 0x6c` — proof the query idiom works in exactly the
contexts this feature needs:

| site | API | what it does |
|---|---|---|
| `CombatSpells.TTacticalCombatTerrorCA.Generate+0x1F @0x557F99B7` | `+0xa8` | **tactical combat**, on a `TCombatUnit` — the template |
| `CombatSpells.TFastCombatTerrorCA.Generate+0x53 @0x557F9833` | `+0xa8` | the fast-combat twin |
| `AoWE.THealingAbility.CanTouch+0x91 / CanTouchUnit+0x66 / HealUnit+0xB1` | both | healing cures panic |
| `AoWE.TAbstractUnit.GetUnitMoraleValue+0xE7 @0x5577EFBF` | `+0x148` | the −80 |
| `UnitSpells.TRemedy.ValidTargetUnit+0x5E` | `+0x148` | Remedy targets it |

`AoWTCPCK.dpl` currently queries `0x6C` nowhere.

### 4a. It works on heroes as well as units (checked 2026-08-31)

**Applying it.** `AoWE.TStrikeCA.Generate @0x557668B4` only sets a flag bit in `CA+0x18`; the
ability is applied later by `AoWE.TStrikeCA.Execute @0x55766738`:

```c
if (CA->dwEffect_flags & 1) {                       // Cause Fear landed
    if (IsClass(target, TCombatUnit)) {              // "is this a unit at all", NOT hero-vs-unit
        ab = TAbilityControl.GetAbility(..., 0x6c);
        ab->vmt[0xd0](ab, target[0x13]);             // target+0x4c = the STRATEGIC object
    }
}
```

`target+0x4c` is the `THero` for a hero and the `TUnit` for a unit, so both get the status by the
same path. ⚠ **`TFastCombatUnit` is a *descendant* of `TCombatUnit`** (instance `0x64` vs `0x5C`),
so that `IsClass` gate passes in auto-resolve too — panic is inflicted in both battle kinds.

**Reading it.** All five gates go `+0xA8` → `TCombatUnit.GetAbilityEnabled @0x55725004` →
`pStrategic_unit->vmt[0x148]`. For a hero that is `THero.GetAbilityEnabled @0x5578827C`, which
calls `TAbstractUnit.GetAbilityEnabled` on the hero's **own** set first, then items — so a hero's
own Panicked is found at the first step. This is the **item-aware** API; the self-only `+0x88`
would have been the silent-failure choice (see `Investigation_Items.md` §0.6). Independent
confirmation that the chain works on heroes: the −80 morale penalty already reads `0x6C` this way
in `TAbstractUnit.GetUnitMoraleValue+0xE7`.

⚠ **`Fearless 0x43` blocks Cause Fear outright** at `0x557668F5`. A hero that never panics probably
has Fearless — that is data, not a defect in this patch.

⚠ The project's standing "always test on a non-hero" caution (`aow1-status-debuff-stat-cache`) does
**not** apply to this feature: that trap is about units *caching* ability stat modifiers while
heroes recompute live, and these gates read ability **presence**, not a cached stat.

## 5. The patch — five hooks, all the same shape

Every gated site begins with **`BA 01 00 00 00` (`mov edx,1`)** — the head of the vanilla flying
test, exactly five bytes, so an `E9 rel32` hook displaces one whole instruction and nothing else.
**All five verified `.reloc`-free** before patching.

| site | module | hook VA | forbidden target | resume |
|---|---|---|---|---|
| `cursor` | AoWTCPCK.dpl | `0x0041FA7F` | `0x0041FABE` (cursor `0x59`, state `0x100` — the same treatment as pointing at your own unit) | `0x0041FA84` |
| `ai` | AoWTCPCK.dpl | `0x00415478` | `0x004158AF` (AI skips this candidate) | `0x0041547D` |
| `freeswing` | AoWTCPCK.dpl | `0x00408749` | `0x0040880E` (no free swing) | `0x0040874E` |
| `autoresolve` | AoWEPACK.dpl | `0x55766B75` | `0x55766B9B` (`xor eax,eax` → return 0) | `0x55766B7A` |
| `touch` | AoWEPACK.dpl | `0x5576833D` | `0x55768363` (`xor eax,eax` → return 0) | `0x55768342` |

**Which object is the attacker at each site** (this is the bit that is easy to get backwards):

| site | attacker | target |
|---|---|---|
| `cursor` | `[ebp-0x10]` → `+0x1c` (selected unit's HS → its `TCombatUnit`) | `[ebp-0x14]` → `+0x1c` (hovered hex's occupant) |
| `ai` | `[ebp+0x14]` | `[ebp+0x10]` |
| `freeswing` | `[ebp-0x10]` → `+0x1c` (the **stationary** unit that would swing) | `[ebp+8]` → `[-4]` → `+0x1c` (the mover) |
| `autoresolve` | **`ESI`** (= `EDX` at entry = `param_2`) | **`EDI`** (= `ECX` at entry = `param_3`) |
| `touch` | **`EDI`** (= `EDX` at entry = `param_2`) | **`ESI`** (= `ECX` at entry = `param_3`) |

`autoresolve`'s register map is confirmed from the prologue (`MOV EDI,ECX; MOV ESI,EDX; MOV EAX,ESI;
CALL GetSide`) cross-checked against the sole caller `fcPrefetchCombatCommands`, which passes
`CanExecuteMelee(self, [cmdlist+4] /*the acting unit*/, piVar2 /*candidate from the enemy side*/)`.
`touch` is the **mirror image** (`MOV ESI,ECX; MOV EDI,EDX`) — see the warning in §5a.
`freeswing`'s attacker is pinned by `0x0040878B`/`0x0040879A`, which store `[ebp-0x10]`'s unit into
the *mover's* TE at `+0x2c`/`+0x30` as the unit that will swing.

Cave body (`cursor` shown; the others differ only in how the attacker is loaded and where they
branch). `EBP` is intact inside the cave, so frame-relative loads work:

```asm
    push eax
    push ecx
    push edx
    mov  eax, [ebp-0x10]        ; attacker HS
    mov  eax, [eax+0x1c]        ; its TCombatUnit
    mov  edx, 0x6C              ; Panicked
    mov  ecx, [eax]
    call dword ptr [ecx+0xa8]   ; GetAbilityEnabled
    test al, al
    pop  edx                    ; pops do not touch flags
    pop  ecx
    pop  eax
    jnz  forbidden
    mov  edx, 1                 ; the displaced instruction
    jmp  0x0041FA84             ; resume
forbidden:
    jmp  0x0041FABE
```

- **PIC:** `jmp/call rel32` + register-indirect only, no absolute memory refs — safe for a
  rebasing `.dpl`. EAX/ECX/EDX are caller-saved under Delphi's register convention; EBX/ESI/EDI/EBP
  are preserved, which matters at the two AoWEPACK sites where `ESI`/`EDI`/`EBX` are live across
  the hook.
- **RNG:** no cave draws a random number, so the SYNCED/RAW rule does not apply. Re-run
  `re_tools/rng_audit.py --owners` after `--apply` regardless — it is the standing check.
- **Cave space:** AoWTCPCK `CODE` has a zero run from **`0x00438240` to `0x00466C00`**
  (190 912 bytes free; `0x00438100`–`0x0043823F` is already claimed by the facing/shield work, and
  something owns `0x00466C00`). Allocate from `0x00438300`. Section characteristics `0x60000020`
  (`CNT_CODE|MEM_EXECUTE|MEM_READ`).
- **No exe lockstep edit.** Both patched files are `.dpl`s loaded by every binary, so the
  `AoW.exe`/`AoWCompat.exe` pairing rule does not apply here.

### 5a. What was actually built (2026-08-31)

`build_panic_nomelee.py` — dry-run by default, `--dis` to disassemble the caves, `--apply`,
surgical `--undo` (restores the five `mov edx,1` instructions, zeroes its own five caves, touches
no backup). Idempotent; aborts if any hook site holds bytes that are neither vanilla nor its own.

Caves (hooks, resumes and attacker loads are in §5):

| site | file | cave VA | size |
|---|---|---|---|
| `cursor` | AoWTCPCK.dpl | `0x00438300` | 44 B |
| `ai` | AoWTCPCK.dpl | `0x00438340` | 41 B |
| `freeswing` | AoWTCPCK.dpl | `0x00438380` | 44 B |
| `autoresolve` | AoWEPACK.dpl | `0x55828000` | 40 B |
| `touch` | AoWEPACK.dpl | `0x55828040` | 40 B |

Backups: `AoWTCPCK.dpl.pre-panicnomelee`, `AoWEPACK.dpl.pre-panicnomelee` (one layer deep, but
`--undo` is the revert path — do not restore by copying).

⭐ **Each cave repeats the vanilla flying test's own object load verbatim, changing only the
ability id.** That is what makes the register and type assumptions safe: if the vanilla test could
reach `+0xA8` on that object, so can ours. Caves push/pop EAX/ECX/EDX (Delphi's caller-saved set)
and touch nothing else, which matters at the two AoWEPACK sites where EBX/ESI/EDI are live across
the hook.

⚠ **`ESI` and `EDI` swap roles between the two AoWEPACK sites.** `CanExecuteMelee` does
`MOV EDI,ECX; MOV ESI,EDX` (so ESI = param_2 = attacker); `TTouchAbility.CanTouch` does
`MOV ESI,ECX; MOV EDI,EDX` (so EDI = param_2 = attacker). They are mirror images. Read the
prologue, never pattern-match the flying test's own `mov eax,esi` / `mov eax,edi`.

Checks run after `--apply`: `--undo` round-trip back to five vanilla states and re-apply; all five
hooks re-disassembled in situ from the live files; `rng_audit.py --owners` shows no new RNG site
(no cave draws); PIC assertion (no absolute memory operand in any cave) built into the script;
profile-path scan clean on both binaries and both new backups.

## 6. Scope decisions — settled 2026-08-31

Answers given by the user; §6.1/§6.2 are built, §6.4 was declined.

1. **Free / opportunity swings — BLOCKED.** Site `freeswing`.
2. **Touch abilities — BLOCKED.** Site `touch`, in `TTouchAbility.CanTouch`. Placed inside the
   `side(attacker) != side(target)` arm, so **friendly touch abilities are unaffected — a panicked
   healer still heals**. Charm and Seduce are covered transitively (their `CanTouch` calls
   `TCommandAbility.CanTouch`, which calls the base). ⚠ `TSelfDestructAbility.CanTouch
   @0x55768EC4` does **not** call the base and carries no flying gate in vanilla either, so a
   panicked unit can still self-destruct.
3. **Enforcement — matches vanilla exactly**: cursor + AI + auto-resolve. No hard gate.
4. **`MeleeMoveTC @0x00422CD8` hard gate — NOT built** (declined). Still available if a hole turns
   up. ⚠ If ever added, the cursor and AI hooks must stay — a refused order that the AI still
   scores as its best move risks an activation loop.
5. **Ranged — not gated.** Out of scope by the wording; a panicked archer keeps shooting.
6. **Still to do: `Ability.pfs` text.** Record 118 ("Panicked") reads `(Atk-4, Res-6)` after
   `build_pfs_typos.py`; it wants the new restriction appended. Cause Fear is record 61.

## 7. What this does not do

- No change to any damage, to-hit or morale number. The morale band penalty stays exactly as it is.
- No effect on the **raze combat predictor** — it has no concept of panic, and `CheckUnit`-style
  gating is not in that code path.
- Panic remains invisible to `Floating`/`WindWalking`-style edge cases in the same way the flying
  rule is.

## 8. Failed / rejected approaches (do not re-try)

- **Zeroing `round+0x28` in `TMeleeRound.Calculate`.** Makes swings whiff instead of making the
  order illegal, and `+0x28` is the *initiator's* count regardless of who is panicked, so it
  misfires on retaliation rounds. §1.
- **Adding `0x6C` to `TCombatUnit.GetLocked`.** Kills retaliation too — the exact thing the
  feature is supposed to preserve. §2.
- **Patching `AoWE.CreateStrikeCA @0x557665E4` ("melee1").** Not on the ordinary melee path at all
  — see the correction in `Shield_And_Retaliation_Facing_Spec_2026-08-26.md` §the shared brief.

## 9. In-game test checklist — NOTHING here is confirmed until the user runs it

Nobody in the build loop can launch the game. Setup: get a unit Panicked by hitting it with a Cause
Fear (`0x33`) attacker; the status shows on its card. Test on **both a unit and a hero** — §4a says
heroes are covered, and step 11 is the check of that claim.

1. **Deliberate melee, panicked attacker.** Select the panicked unit, hover an adjacent enemy.
   PASS: the "no" cursor (the same one you get hovering your own unit) and no attack is possible.
   FAIL, attack proceeds: the `cursor` hook is not reached — the cursor path taken is a different one.
2. **Retaliation, panicked defender.** ⭐ **The whole point.** Attack the panicked unit with a
   normal melee unit. PASS: it hits back for its usual two strikes at its usual (morale-penalised)
   numbers. FAIL, no retaliation: something is gating `TMeleeRound` — say so, that is not this
   patch's design and would mean a hook fired on the wrong side.
3. **Panic wears off.** When the timer expires (or a Healing/Remedy cures it) the unit attacks
   normally again. FAIL: the ability is not being cleared, which is a vanilla `TDurationAbility`
   matter, not this patch.
4. **The AI does not stall.** Give an AI stack a panicked melee unit and end turn. PASS: the AI
   plays its turn at normal speed; the panicked unit moves/holds but never attacks. FAIL, the turn
   hangs or takes far longer: the `ai` hook is refusing a candidate the AI still scores as best —
   this is the activation-loop risk in §6.4 and the `ai` hook needs re-siting.
5. **Free swing suppressed.** Walk an enemy past the panicked unit. PASS: no opportunity swing.
6. **Touch attacks suppressed.** A panicked Web/Entangle/Turn Undead/Dominate unit cannot use it
   on an **enemy**.
7. **⭐ Friendly touch still works.** A panicked **healer** can still heal an ally, and a panicked
   Command/Leadership unit still works. FAIL: the `touch` hook has escaped the
   `side(attacker) != side(target)` arm and is blocking friendly abilities too.
8. **Auto-resolve.** Resolve a battle containing a panicked melee unit with the fast-combat button.
   PASS: no crash; the panicked unit contributes no offensive melee but still takes and returns
   blows as a defender.
9. **Ranged unaffected.** A panicked archer still shoots (deliberate, by §6.5).
10. **Nothing else changed.** A battle with no panicked units on either side plays exactly as
    before — same damage numbers, same retaliation, same AI behaviour.
11. **⭐ Heroes.** Panic a **hero** and repeat steps 1 and 2: it cannot initiate melee, and it still
    retaliates when attacked. PASS confirms §4a. FAIL, the hero attacks normally: first check the
    hero does not have **Fearless** `0x43` (which blocks Cause Fear entirely, so it was never
    panicked); only if it genuinely shows the Panicked status is this a defect — and then it means
    `THero.GetAbilityEnabled @0x5578827C` is not seeing the hero's own set, which would be a
    surprise given the morale penalty already reads it that way.

If anything fails, revert first and report which numbered step:

```bash
python "Modding Resources/build_scripts/build_panic_nomelee.py" --undo
```

---

**Related:** `Investigation_Combat.md` (ability ids, the melee round),
`HOWTO_Lifesteal_RoundAttack.md` (the `CA+0x0c` bit0 offensive/retaliation flag),
`Shield_And_Retaliation_Facing_Spec_2026-08-26.md` (the tactical melee TE state machine),
`Raze_CombatPredictor_Analysis.md` (the predictor's copy of the flying rule).
