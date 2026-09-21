# `Error - FCWin` / `Blt Error` on every hit to a combat wall

**Status: CONFIRMED WORKING (2026-07-22)** — user-validated in-game after the fix below.

Feature: `build_scripts/build_replaylog.py` (cave `0x5580F180`, hook `0x55729D97`, `AoWEPACK.dpl`).
Diagnostic tooling built for this: `build_scripts/build_bltprobe.py`, `build_scripts/build_bltprobe_exe.py`,
`re_tools/read_bltprobe.py`. All three are DIAGNOSTIC-ONLY and revert cleanly.

---

## 1. Symptom

A modal `Error - FCWin` dialog with body `Blt Error`, on **any** damage to a combat wall — confirmed
with cannons, so not specific to touch abilities, and not to overkill (the repro was a d6 against a
25 HP wall). Not resolution-dependent. Damage still landed; the dialog was cosmetic but constant.

The user reported from the outset that it began with the combat-log work. That was correct, and it
took far too long to act on — see §5.

## 2. Root cause

`build_replaylog.py`'s cave fetched combatant names for the replay line:

```
mov  eax, [ebp-0x20]        ; the combat object from FindID
test eax, eax
jz   fallback
mov  eax, [eax+0x4C]        ; -> strategic unit          <-- UNGUARDED BY TYPE
test eax, eax               ; NIL check only
jz   fallback
mov  ecx, [eax]             ; -> unit VMT                <-- ACCESS VIOLATION on a wall
call dword ptr [ecx+0xF8]   ; GetName
```

`TCombatObject+0x4C` is the strategic-unit link, but **the field is `TCombatUnit`-only**.
`TCombatWall` has a smaller instance and reuses offset `0x4C` for packed bytes. On a wall the read
returns nonzero garbage, sails through the NIL test, and the dereference faults.

### Fix

The `System.@IsClass` type gate, applied **before** the `+0x4C` read:

```
mov  eax, [ebp-0x20]
test eax, eax
jz   fallback
lea  edx, [edi - 0xF970C]   ; TCombatUnit VMT 0x55715A94, PIC via the cave's call/pop anchor
call 0x557010C0             ; System.@IsClass  -> AL
test al, al
jz   fallback               ; not a unit -> "?" name, touch nothing
mov  eax, [ebp-0x20]
mov  eax, [eax+0x4C]
```

Constants: `IS_CLASS = 0x557010C0` (EAX=obj, EDX=classref **value**), `TCOMBATUNIT_VMT = 0x55715A94`.
The DLL rebases, so the classref must be reached from the cave's anchor, never as an absolute.
`@IsClass` follows the Delphi register convention and preserves EDI, so the anchor survives the call.

Cave rewritten **in place** (825 B, ceiling 1152 B); no revert — `.pre-replaylog` is layer **27 of 47**
on `AoWEPACK.dpl` and restoring it would destroy 19 later features. (It also **moved** to
`Modding Resources/backups/` on 2026-07-29/30 — present, just not in the game root. The "9th of 35"
figure written here originally was correct in 2026-07-22; the stack has grown since, which is exactly why
rewriting in place was the right call.)

## 3. Why the message was useless — two nested catch-alls

```
build_replaylog cave           AV (access violation)
  └─ AoW.exe 0x435E7C  TFastCombatForm.FCWinDrawSurface
       except @0x435F26:  Exception.Create('Exception during FastCombatWin.DrawSurface')
                          @RaiseExcept          <-- ORIGINAL EXCEPTION DESTROYED
         └─ aowInt 0x59807BC6..0x59807D48  (the component draw try)
              except @0x59807D55:  MessageBox(body = literal "Blt Error",
                                              caption = "Error - " + component.Name)
```

Neither layer reports what failed. The aowInt routine has **five** such arms, each with a fixed label:
`"Verify Surface Error"` (`0x598077F4`), `"Draw Error"` (`0x59807967`), `"Blt Error"` (`0x59807D55`),
`"SB Draw Events Error"` (`0x59807EA5`), `"Exception during DrawSurface"` (`0x59807EE8`).

**In this codebase an error string beside a MessageBox is a label on an `except` arm, not a
description of the fault. Do not interpret it — probe the handler.**

### The aowInt try body, for future reference

```
59807BC6  mov fs:[eax],esp              <-- TRY BEGIN
59807BCC  cmp byte [self+0x102],0
59807BD3  je   59807D35                 -- "not dirty": ONLY the virtual call below runs
59807BDC  cmp dword [self+0xE4],0
59807BE3  jle  59807D43                 -- no BltRects: exits the try having executed NOTHING
59807C0F  call [self+0x110]             -- pre-draw event   (guard: word [self+0x112] <> 0)
59807C32..59807D07                      -- the BltRect blit loop
59807D2D  call [self+0x108]             -- post-draw event  (guard: word [self+0x10A] <> 0)
59807D3D  call [self.VMT+0x9C]          -- the "not dirty" path's virtual draw
59807D48  mov fs:[eax],edx              <-- try end
```

`[self+0xE4]` is the BltRect **count**; `[self+0xDC]` the list; `[self+0x18C]` the source surface;
`[self+0xD8]` selects plain (`[ebx+0x18]`) vs colour-keyed (`[ebx+0x20]`) blit.

## 4. How it was actually found — the probe technique (reusable)

Static reading produced three wrong theories in a row. What worked was instrumenting both handlers:

* **`build_bltprobe.py`** — cave in `aowInt.dpl`, hooked on the `"Blt Error"` except arm.
* **`build_bltprobe_exe.py`** — cave in `AoW.exe`, hooked on `FCWinDrawSurface`'s except arm at
  `0x435F26`, i.e. **before** `Exception.Create` destroys the original.
* **`re_tools/read_bltprobe.py`** — reads both out of the live process.

Design rules that made it safe and that are worth copying:

* **Dumb cave, smart reader.** The cave records *raw pointers and a raw stack image* and dereferences
  almost nothing. A stray read inside an except arm is a nested exception, which in Delphi 3 is a hard
  failure. All pointer-chasing happens out-of-process over `ReadProcessMemory`, which returns an error
  instead of faulting.
* **The dialog is modal, so the process holds still** — no debugger needed. The captured values also
  persist in memory after the dialog is dismissed; only exiting the game loses them.
* **Dump the stack, not just what you think you need.** The break came from a return address in the
  stack image landing in `AoWEPACK.dpl+10F1A0` — a cave that had no business being in that call path.
  That single dword identified the culprit after everything else had failed.
* **EAX is NOT the exception object at a bare `except`.** Delphi passes it for `except on E: ... do`,
  but these are bare `except` arms and `@HandleAnyException` makes no such guarantee. Measured: EAX
  held `0x00858E20`, whose first dword was in no loaded module and so was not a VMT. Hunt the stack
  for a pointer whose class metadata validates instead. (Beware: that scan also surfaces ordinary
  live objects — it returned a `TDamageCA` — so check the class before believing it.)

### Cave/scratch real estate found along the way

| Module | Purpose | Address | Notes |
|---|---|---|---|
| `aowInt.dpl` | code cave | `0x59823000` | CODE zero tail, free from `0x598227C7` (~109 KB) |
| `aowInt.dpl` | **writable** scratch | `0x5983E100` | DATA declares VirtualSize `0x24` but has `0x200` raw → `0x5983E024..0x5983E1FF` is mapped, writable, raw-backed slack |
| `AoW.exe` | code cave | `0x00610720` | `.clog` tail `0x610714..0x610800`; section chars `E0000060` (EXEC+WRITE) |
| `AoW.exe` | **writable** scratch | `0x0045A640` | DATA raw slack `0x45A634..0x45A800`, 460 B |

⚠ `aowInt.dpl`'s CODE section is `60000020` — **read+execute only**. Cave-local mutable state is
impossible there; that is why the scratch lives in DATA.
⚠ `0x60D004..0x60F020` in `AoW.exe` scans as free but is the **live combat-log ring buffer**. Never
allocate there.
⚠ `aowInt.dpl` is loaded by `AoWDevEd.exe` too, which has no `.clog`. An aowInt cave that writes to an
`AoW.exe` address would be a wild store in the editor — keep a module's scratch inside that module.

## 5. Why this took so long — the methodology failure

An A/B run reported **"all seven combat-log DLL hooks off → error persists"**, and that was written up
as *"the DLL half is EXONERATED"*. Three mechanism theories were then built on top of it.

The test was measuring the wrong thing. `build_touchlog_gate.py` knows only the seven hooks owned by
`build_combatlog_dll.py`. **`build_replaylog.py` is a separate feature with its own hook at
`0x55729D97`, and it stayed live through every isolation run.** The "exoneration" was an artefact of
the gate tool's inventory, not a fact about the code.

Two lessons, both general:

1. **A gate tool's negative result is only as good as its inventory.** Derive "what is patched in this
   binary" from the binary or from the whole `build_scripts/` set — never from one script's notion of
   its own hooks. A gate that silently covers a subset produces confident false negatives.
2. **When an A/B contradicts the user's direct observation of *when* a symptom appeared, suspect the
   test before discarding the observation.** The user said "it doesn't happen before the combat log
   addition" and was right; the test said otherwise and was wrong. Reported-history evidence is not
   soft evidence — it is a constraint the explanation has to satisfy.

Related earlier failure, same shape: an even earlier A/B pinned the error *on* the combat log
("all off → no error"), a **false negative from a single RNG-dependent trial** where the control simply
never triggered the condition. Both directions of this A/B were wrong for different reasons.

## 6. Sibling risk — the same idiom elsewhere

Two independent caves had this identical defect (`build_combatlog_dll.py`, fixed in
`Raze_Dialog_Freeze_Fix.md` §8; `build_replaylog.py`, fixed here). **When a bug comes from a reusable
idiom, grep every cave for the idiom the same day.**

Sites reading or writing `+0x4C` off an object, as of 2026-07-22:

| Script | Line | Gated? |
|---|---|---|
| `build_combatlog_dll.py` | 351, 371, 787, 807 | ✅ `IS_CLASS` before the read |
| `build_replaylog.py` | 178 | ✅ fixed 2026-07-22 |
| `build_ranged_slayers.py` | 150 | ⚠ uses `ISCLASS` but **after** the `+0x4C` read, and against `THero` not `TCombatUnit` |
| `build_debuffcache.py` | 120 | ⚠ NIL check only, then `mov edx,[eax]` |
| `build_simfly.py` | 179 | ⚠ **writes** (`sub dword [eax+0x4C], edx`) — different field meaning? |
| `build_tierresearch_exe.py` | 829, 889 | exe-side, non-combat object — believed unrelated |

Audit status: see §7. Note `grep IS_CLASS` alone is not a reliable gate check — `build_ranged_slayers.py`
spells the constant `ISCLASS` and still has the ordering wrong.

## 7. Audit outcome (2026-07-22)

**`build_ranged_slayers.py:150` — WAS VULNERABLE, now FIXED (applied, untested in-game).**
Hook `0x5576EB34` inside `TRangedAttackAbility.CreateRangedAttackCA` @`0x5576EAE4`; `[ebp-4]` is the
**target**, and a target can be a wall. Chain, verified: `TCombat.Initialize` → `TCombatWall.Setup`
writes `[wall+0x45]` = defending player, so `TCombatObject.Activate` @`0x55726708` adds the wall to the
defending `TCombatSide`'s object list; `TRangedAttackAbility.fcPrefetchCombatCommands` @`0x5576EC10`
enumerates that list into `[cmd+0x18]`; `TCombatWall.fcRoundDistance` @`0x55725B78` is
`xor eax,eax; ret` so the wall is **always in range**. Only the Assassin block actually faulted — the
other three slayers are accidentally safe (wall `VMT+0xA8` returns 0, `VMT+0x90` returns alignment 6).
Fixed by gating on `IsClass(target, TCombatUnit)` **before** the `+0x4C` read.
⚠ Note the idiom differs from the combat log's: here the classref is loaded from a **cell**
(`[0x55715A54] = 0x55715A94`, verified), matching the script's existing `THero` pattern — contrast
`0x5571D4BC`, which is a VMT **base** needing `lea`. Getting that backwards makes the gate inert.

**`build_debuffcache.py:120` — SAFE.** The three CA paths (`TWebCA`, `TEntangleCA`,
`TEntangleSpellCA`) are all unreachable with a wall: `TWebAbility.CanTouch` @`0x5576A254` and
`TEntangleAbility.CanTouch` @`0x5576A858` each perform a double `IsClass(TCombatUnit)` gate — the
engine does our check for us — and the spell path is blocked by wall immunity (below). Corroborating:
**vanilla itself dereferences `[ebx+0x4c]` immediately before our patched call at all three sites**, so
if a wall could arrive there, stock AoW1 would already fault. Our cave adds no new exposure.
*Residual uncertainty:* the Entangle-**spell** conclusion assumes that spell's damage-type word
(`spell+0x36`) lacks bit `0x0100`; that is `.pfs` data and the install is the Ziggurat mod. The two
ability paths depend on no data at all.

**`build_simfly.py:179` — SAFE, and `+0x4C` means something else entirely.** The hook is inside
`TCombatPredictorUnit.ExecuteRound` @`0x5572AAA0` — not combat-object code. `EAX` is a target
`TCombatPredictorUnit`, and `+0x4C` there is a **signed HP integer**, not a pointer: vanilla precedes
the `sub` with `cmp dword [eax+0x4c],0 / jle` (a signed test, meaningless on a pointer) and
`ResetCombat` @`0x5572A91C` does `[+0x4c] = [+0x10]` (current := max). Walls are wrapped by
`TCombatPredictor.AddWall` @`0x5572B28C` into a `TWallUnit` (an ordinary `TAbstractUnit`), so they
arrive as normal predictor units with a valid strategic unit at `+4`. No pointer corruption.

### ⚠ Still open: `build_assassin.py` `cave_melee` / `cave_melee3`
`cave_melee3` hooks `0x55767C5C` inside `TMeleeRound.CalculateStrikes` @`0x55767B24` and does
`mov eax,[edi+0x4c]` behind **only a NIL check**. `ESI`/`EDI` are the round's two combat objects from
`[mr+0x10]`/`[mr+0x14]`, and the block runs **twice with them swapped**, so `EDI` is the target in one
direction. Whether a `TMeleeRound` is ever built with a `TCombatWall` was NOT traced — this is a lead,
not a verdict — but melee wall attacks demonstrably exist (`TWallCrushingAbility`,
`TFastCombat.AttackerCanCrushWall`). The script's own comment ("*CreateStrikeCA's callers … never
walls*", "*with a null guard for walls*") is exactly the reasoning that has now failed three times.

### Reusable: when CAN a wall be the target?
`TCombatWall.GetImmunityTypes` @`0x55725C40` computes `~0x0100 & allTypes` (mask word at
`0x55725C58` = `0x0100`; all-types word at `0x558E8044` = `0x03FF`) — **a wall is immune to every
damage type except bit `0x0100`**, the siege/wall-damage bit. `StatisticsToLimitedDV` @`0x55726094`
returns 0 on full immunity. So for any damage-value-gated path the answer is: **only attacks carrying
`0x0100` can target a wall.** That single fact answers "can a wall reach here?" for most call sites.
