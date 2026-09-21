# Handover — `build_facing_retal` and `build_shield`

**Both patches are applied to the live install and both passed QA. Nothing is confirmed working** — QA is a static, byte-level check only; neither the coder nor QA can run the game. Everything below is *applied, untested*.

One thing to be aware of before you start: this round also rewrote **one byte in each of `AoW.exe` and `AoWCompat.exe`** (Shield's hero level-up category). That write was outside the track statement's original scope ("AoWEPACK.dpl only, no exe touched"), and no fresh snapshot was taken for it — the only exe backups are the pre-existing `.pre-herodlgcolumns` pair, which per project convention are themselves *patched* snapshots and are not a pristine reference. The lockstep invariant was re-checked after the write: the two exes still differ at exactly `0x3BB7C` (`0F` / `05`) and nowhere else.

---

## 1. Status

| script | target binary | applied? | QA pass? | rounds needed |
|---|---|---|---|---|
| `build_facing_retal.py` | `AoWTCPCK.dpl` | yes | **PASS** (0 blockers, 0 majors, 2 minors) | 0 |
| `build_shield.py` | `AoWEPACK.dpl` | yes | **PASS** (0 blockers, 0 majors, 3 minors) | 1 |
| `build_herodlg_columns.py` (re-run on Shield's behalf) | `AoW.exe` + `AoWCompat.exe` | yes | covered by the Shield round | — |

`Release/Ability.pfs` is **byte-unchanged** (`crc32(d[4:]) = 0x2144DF1C`, 151 records, ids 10–181; record 186 absent). That is the outstanding manual step — section 5.

Not run at all this round: `build_magebane.py` (standing booby trap — leave it alone).

---

## 2. What changed

### `build_facing_retal.py` → `AoWTCPCK.dpl`

Diff against `AoWTCPCK.dpl.pre-facingretal`: **exactly 4 runs, 66 bytes**, nothing else in the file.

| VA | file offset | original | written |
|---|---|---|---|
| `0x004092B9` | `0x0086B9` | `8B 45 FC` | `EB 65 90` — `jmp 0x00409320` (part a: melee defender re-face skipped) |
| `0x00409BB3` | `0x008FB3` | `8B 45 FC 8B 40 34` | `E9 48 E6 02 00 90` — `jmp 0x00438200` (part b: deferred retaliation turn) |
| `0x00409F2A` | `0x00932A` | `8B 45 FC 8B 40 1C` | `E9 3D 01 00 00 90` — `jmp 0x0040A06C` (part c: touch-victim re-face skipped) |
| `0x00438200` | `0x037600` | 51 zero bytes | the 51-byte cave |

The cave, read back from the live file (17 instructions): `pushal` → load the melee TE's attacker `[+0x1C]` → its HS `[+0x60]` → facing byte `[+0x14]` → `add 3`, wrap mod 6 **before** the call → load the defender `[+0x28]` → its HS `[+0x60]` → `call 0x00402AF4` (IAT thunk to `AoWEPACK.dpl!AoWE.TUnitHS.SetDirection`) → `popal` → re-issue the two displaced instructions → `jmp 0x00409BB9`. Bytes `0x00438233`–`0x0043823F` are the reserved tail and are still zero.

Both skipped spans were **jumped over, not NOPped** — they carry live relocations. Reloc count unchanged at 8,824; zero relocations anywhere in `0x00438000`–`0x004387FF`. No absolute memory operand in the cave (mandatory: this module rebases).

Deliberately left alone and byte-verified unmodified: `0x0040AAAF` (Possess / appearance-swap), `0x004092B4` (melee attacker re-face — load-bearing for part b's `+3` idiom), `0x00409E60` (touch actor re-face). The Wall Crushing block at `0x00409F9A` is still reached by both of its guards and its bytes are unchanged.

No exe was written by this script.

### `build_shield.py` → `AoWEPACK.dpl`

Diff against `AoWEPACK.dpl.pre-shield`: **exactly 6 runs, 438 bytes**, all inside the five hook windows plus `0x55823000`–`0x558231D9`.

| VA | what |
|---|---|
| `0x55823000`–`0x558231DB` | the cave, 475 bytes |
| `0x557BCECF` | `E8 C4 62 06 00` → `cave_reg` at `0x55823198` (was `E8 64 33 F9 FF` → `RegisterAbility`) |
| `0x55767EBA` | 6 bytes → 5-byte `E9` + `90`, into sub-cave `csca_a` (resumes `0x55767EC0`) |
| `0x55767F2A` | 6 bytes → 5-byte `E9` + `90`, into sub-cave `csca_b` (resumes `0x55767F30`) |
| `0x558129EC` | 5-byte `E9` into the cave |
| `0x55812A7B` | 5-byte `E9` into the cave |

The last two sit inside the existing strike caves (the invisibility-penalty / ranged-slayers chain) and route into Shield's `melee1` and `ranged` sub-caves, which resume at `0x557666CF` and `0x5576EB39`. `0x55812A80` (magebane) and `0x55812A2E` (melee3 tail) are untouched — Shield does not link to the shared accumulator, so nothing clamps it.

Sub-caves, each disassembled from the live file to 100% coverage: `GETHEX` 38 B (`ret`), `SHIELD_ARC` 166 B (`ret 8`), `csca_a` 52 B, `csca_b` 52 B, `melee1` 42 B, `ranged` 51 B, `cave_reg` 49 B (`ret`), plus alignment padding and the name blob at `0x558231CC` (`FF FF FF FF 06 00 00 00 'Shield' 00`, refcount −1, blob+8 = `0x558231D4`, reached via a `call $+5 / pop / lea` PIC anchor).

Behaviour: ability id **176 (`0xB0`)**, selection mask `0x3FF`, penalty **−4 to attack**, applied when the incoming bearing is the defender's **front or front-left** (`(D−F) mod 6 ∈ {0, 5}`; the cave literally tests `{-1, 0, 5}`). Level-up cost baked into the cave as **6 — a placeholder chosen by the build, not by you** (see section 5). The penalty is stored as `0xFC` and read with `movsx`, so it reads as −4 and cannot wrap.

PIC-clean: zero absolute memory operands, every `0x55xxxxxx` reference is an `E8`/`E9` rel32. External targets are only `0x5570266C` (`dHXtoRad` thunk), `0x557026A4` (`dHXtoHN` thunk), `0x55750238` (`RegisterAbility`, ×2), `0x5576601C` (`CreateEnhancementAbility`) plus the four resume addresses. Zero `.reloc` entries in the cave page or in any displaced window.

### `build_herodlg_columns.py` → `AoW.exe`, `AoWCompat.exe`

One byte each, file offset `0x21DE40` (category-table base + 176): `04` (Magic) → `02` (Melee). Full byte-diff confirms exactly one changed byte per file; sizes unchanged; lockstep re-verified.

---

## 3. How to undo

The revert path is each script's **surgical `--undo`** — never a `.pre-*` copy. Copying a backup over the file would wipe every other feature layered onto it afterwards. All commands are run from anywhere; paths are relative to the game directory.

```
python "Modding Resources/build_scripts/build_facing_retal.py" --undo
python "Modding Resources/build_scripts/build_shield.py" --undo
```

`build_facing_retal.py --undo` restores the three displaced runs and zeroes exactly its own 51 bytes at `0x00438200`, leaving the reserved tail and everything past it alone. It never reads, writes or deletes `AoWTCPCK.dpl.pre-facingretal`. Round-tripped by QA to a byte-exact match, then re-applied to the identical patched hash.

`build_shield.py --undo` restores the five hook sites and zeroes only its own emitted length. QA round-tripped it to **0 differing bytes across the whole 2.7 MB file**, then re-applied to the identical hash. It does **not** touch the exes or `Release/Ability.pfs`.

Both accept `--parts` (facing_retal: `a`, `b`, `c`) so a single part can be reverted independently. A dry run with no arguments verifies and reports current state without writing.

**The exe byte has no `--undo` of its own.** To revert it, delete the `176: (2, "Shield")` entry from `ABILITY_CATS` in `Modding Resources/build_scripts/herodlg_cats.py`, then re-run:

```
python "Modding Resources/build_scripts/build_herodlg_columns.py" --apply
```

Editing `herodlg_cats.py` alone changes nothing — the table lives in the exes and only that script rebuilds it.

**Revert-order note:** the two features are in different files and are independent of each other. But the BloodTypes installer at `<game dir>\Modding Resources\AoW1 Modding\Projects\BloodTypes\install_blood_mod.py` has **no** surgical revert — its uninstall restores a full-file `.backup` of `AoWTCPCK.dpl`, which would silently wipe all three facing edits and the cave. If it is ever run, re-run `build_facing_retal.py --apply` afterwards.

---

## 4. In-game test checklist

Ordered so that a failure kills the cheapest test first. Steps 1–2 need no combat; 3–11 are the facing patch; 12–17 are Shield. **You can get a Shield unit before the DevEd round-trip by levelling a hero and taking Shield from the Melee column** — the ability is registered from the cave, so it works without `Ability.pfs`.

1. **Boot the game.**
   PASS: the main window comes up normally.
   FAIL: a bare `Runtime error 217` before the main window, or "Ability already registered (176)" — that is what a duplicate ability id looks like. Cause: id `0xB0` is not actually free. `build_shield.py --undo` and report.

2. **Hero level-up dialog — Shield appears in the MELEE column, beside Parry.**
   PASS: it is in Melee, and the dialog lays out normally (5 columns, no clipping).
   FAIL, appears in Magic: the 256-byte table in the exe is stale — re-run `build_herodlg_columns.py --apply`. FAIL, dialog broken/clipped: the extra Melee row (21 now) overflowed; report before doing anything else.

3. **Attack a unit from behind or the flank in manual tactical combat — it must NOT spin.**
   PASS: the victim keeps its original facing through your blow; the hit/blood animation still plays correctly.
   FAIL, still spins: part a did not take — check `0x004092B9` reads `EB 65 90`. FAIL, blank frame / sideways swing / "Blt Error": the victim's facing is out of the sprite set's valid range at hit time. Note that AoW1's error dialogs are labels on catch-all handlers, so the dialog *text* diagnoses nothing — report what you were doing, not what it said.

4. **Same, against a unit that has not moved or attacked yet this battle** (straight from deployment).
   PASS: correct sprite, correct hit animation.
   FAIL, wrong or missing sprite: some units can sit at facing 0, and vanilla's re-face was masking it. Indirect evidence says this cannot happen (the idle sprite would already be broken), but it costs one attack to rule out.

5. **Strike a unit that is still animating a move.**
   PASS: nothing sticks mid-animation, slides, or ends on the wrong hex.
   FAIL: vanilla's defender re-face implicitly called `TUnitHS.CancelMove`; part a no longer does. This is a theory QA could not measure without the running game — if it reproduces, the fix is to re-issue the cancel.

6. **Attack a unit that WILL retaliate.**
   PASS: it stays turned away for your blow, then snaps to face you immediately before its own swing, and the retaliation animates in the right direction.
   FAIL, snaps to the OPPOSITE side: the `+3` idiom is reading the wrong unit's facing — say so, it is a one-line cave change. FAIL, never turns: part b's hook at `0x00409BB3` is not being reached, or the retaliation path taken is a different one.

7. **Attack something that CANNOT retaliate** (locked, no melee damage, or killed outright by the first blow).
   PASS: it never turns at any point.
   FAIL: the cave is running on a branch it should not — report which of the three cases.

8. **Multi-strike exchange (2 or 3 strikes).**
   PASS (by design): your later blows land on the defender's **new** front, because it turned to retaliate. This is the deliberate per-strike consequence of the ruling — it is a design decision to accept or reject, not a defect. Say now if it does not feel right.

9. **First Strike defender** — fight something that swings before the attacker.
   PASS: it still turns correctly and nothing desyncs.

10. **Touch ability** (web / entangle / turn undead).
    PASS: the victim does **not** spin to face whoever touched it; the **toucher still turns**.
    FAIL, victim spins: part c did not take. FAIL, toucher stops turning: the wrong site was edited — `0x00409E60` should be untouched.

11. **Wall Crushing (ability `0x75`) against a wall, plus Possess / appearance-swap, plus a free swing during movement, plus a ranged shot.**
    PASS: all four behave exactly as they did before. Wall Crushing is the branch part c deliberately routes around; `0x0040AAAF` (Possess) was left alone; the free-swing and ranged victims never spun in vanilla either, so the new behaviour should now read as consistent across melee, touch and ranged.
    FAIL on Wall Crushing: the `0x00409F2A` jump is landing in the wrong place.

12. ⭐ **Shield from each of the six bearings.** Give a unit Shield, then attack it in melee from all six directions relative to *its* facing and read the combat-log attack number each time.
    PASS: the number is **4 lower** from the **front** and the **front-left** only; unchanged from the other four bearings.
    FAIL, the protected pair is front and front-**right**: the map maths is settled (direction 1 = North, numbering clockwise, so 5 is one step anticlockwise = left) — what no static reading can settle is the sprite-index-to-hex-direction transform on screen. Flip `ARC` to `(0, 1)` in `build_shield.py` and re-apply; it is a one-line change and the cave is rewritten in place.
    FAIL, protected on three or more bearings, or on none: report the exact bearings — that distinguishes a bad arc constant from a bad facing read.

13. **Ranged at long range due north** (large dy, dx = 0 or ±1) against the Shield unit, from several bearings.
    PASS: the protected arc tracks the true bearing, not a 90° quadrant.
    FAIL: the cave's `r`/sector maths is disagreeing with the engine's `dHXtoRad`.

14. **Ranged edge cases:** shoot so the missile is intercepted by an intervening unit or wall (the blocker's own arc is evaluated), and shoot into scenery so it is absorbed (nil victim).
    PASS: no crash in either case.

15. **Touch ability and a free swing against a Shield unit from the front.**
    PASS: the same −4, no crash against walls or scenery.

16. **Ranged and melee both hitting the same Shield unit in one turn.**
    PASS: the penalty is −4, never −8. No double-application was found statically (the three chains are disjoint), but only play proves it.

17. **Auto-resolve a battle involving a Shield unit, then a full manual battle including a siege with walls, then Shield placed on an item and equipped by a hero.**
    PASS: auto-resolve does not crash and Shield does nothing (expected — `TFastCombatUnit`, instance size `0x64`, is rejected by the class guard, though it does pass the ability query first, so that path is exercised for real). The siege completes with no "Exception occurred during …" dialog. The item-borne Shield still applies (that query goes through the item-searching ability API).

**Design consequence to accept or reject:** an *attacking* Shield unit always gets its shield against the retaliation, because vanilla already turned it to face its target at `0x004092B4` before the retaliation combat action is built.

**Multiplayer:** both peers load `AoWTCPCK.dpl` and `AoWEPACK.dpl`, so both must carry the identical patches.

---

## 5. The manual step still outstanding — the AoWDevEd round-trip

Shield exists in the code but has no record in `Release/Ability.pfs`. Record 186 cannot be minted by a script; the editor has to create it.

**Decide the level-up cost first.** `EXPAND_COST = 6` is the build's placeholder, not your decision. Once DevEd writes record 186, `Ability.pfs` tag 6 wins permanently and the cave's value stops mattering. Reference points read out of the live file: Parry 8, Drillmaster 10, Magebane free (no tag 6 at all), the four caster abilities 20/40/40/40. If you want a different number, change `EXPAND_COST` in `build_shield.py` and `--apply` before the round-trip, so the placeholder and the data agree.

Then:

1. Launch **AoWDevEd**. Confirm "Shield" appears in the ability list and can be assigned to a unit.
2. Assign it and **save**. That mints `Release/Ability.pfs` record 186.
3. Close the editor (it locks `AoWEPACK.dpl`), then run:

```
python "Modding Resources/build_scripts/build_shield.py" --apply
```

That second apply writes tag 9 = `0x03FF` (the selection mask) into record 186 and repairs the file's CRC-32 — without the repair the game dies silently on load. Until record 186 exists, every run of the script prints the round-trip TODO and continues without touching the `.pfs`.

4. Re-boot the game, confirm it still loads, and confirm tag 6 carries the cost you chose.

---

## 6. Known gaps / what QA could not check

**Not checkable without the game — this is the whole point of both features:**

- Whether the right unit turns, at the right moment, facing the right way (facing_retal, all three parts).
- The **screen** side Shield protects. The map maths is proven twice from the binaries (`dHXtoHNfast` sign classifier and `HNtoHXTable` ring 1 both give direction 1 = North, clockwise), but the sprite-set-index to hex-direction transform is the one link no static read settles. That is test 12.
- Whether the hero level-up dialog actually reads the category table (the table is byte-correct in both exes; the dialog reading it is not provable statically).

**Open risks and record-keeping gaps:**

- **The exes were rewritten this round with no fresh snapshot.** The only exe backups are `AoW.exe.pre-herodlgcolumns` / `AoWCompat.exe.pre-herodlgcolumns`, which are snapshots of a previous *patched* build, not pristine. The revert path is the `herodlg_cats.py` edit + re-apply described in section 3, not a copy.
- Part a silently removes a side effect that is not purely cosmetic: vanilla's defender re-face called `SetDirection`, which calls `CancelMove` on a mid-move HS. Part b restores it, but only for a *retaliating* defender and only when the direction actually changes. This is a theory, not a measured defect — test 5 is the falsifying measurement.
- `build_shield.py`'s `cave_state()` only enforces Shield's whole-page reservation on the `clean` and `prior` paths. Once the state is `done` the rest of the page is never re-checked, so the script cannot detect a foreign write into its own reservation.
- Shield's class guard is a lower bound (`jb`), not an equality test, so it would also admit classes larger than `0x68` whose `+0x60` is not a hex-state pointer. None is known to reach these call sites.
- `check_id_free()` excludes Shield's own cave, so after `--apply` it still prints "id `0xB0` free to register". That line is **not** a post-apply uniqueness proof, and its DLL scan is shape-specific.
- `build_facing_retal.py`'s reserved-tail zero assertion (`0x00438233`–`0x0043823F`) runs unconditionally, including on the `--undo` path. If a future feature ever claims those 13 bytes, `--undo` would abort and this feature would have no scripted revert path at all.
- An `--apply` that is a clean no-op returns before printing the test checklist, so re-running it to re-read the list just prints "already installed".
- **Master index is stale.** `Modding Resources/Zig notes/Unit_Spellcasting_INDEX.md` still records the facing feature as "SPEC WRITTEN, nothing built" (line 131) and "SPECULATIVE" (line 214), while three code sites and a 51-byte cave say otherwise. A future session reading the index would believe the install is vanilla at those addresses. Per the recording convention the pre-confirmation status is "applied, untested", not silence — this should be fixed now, independently of your in-game test.
- The cave claim at `0x00438200` and the `AoWTCPCK.dpl` tail-occupancy map exist **only** inside `build_facing_retal.py`'s docstring. A doc-level grep for cave space will not find it. Two small inaccuracies in that map: the free zero run is `0x0043810B`–`0x00466BFF` (the docstring's stated end runs 16 bytes past the last zero byte and past CODE's virtual size, which ends at `0x00466BAC`), and `build_spellcast_tcpck.py`'s cave's non-zero bytes stop at `0x0043810A`.
- Abilities 170–175 (Magebane, Drillmaster, the four caster abilities) are still uncategorised in `herodlg_cats.py` — separate work, each owning feature's call.
- Four unrelated build scripts exit non-zero in the regression sweep. None is caused by either patch; flagged so they are not later mistaken for a regression from this round.
- `AoWEPACK.dpl` carries an mtime from this session with no matching `.pre-*` snapshot at that time. `build_facing_retal.py` provably cannot have written it (it opens only `AoWTCPCK.dpl` and its own backup), so it belongs to some other `AoWEPACK` layer.
- The standing project-wide check `grep -rn "C:\Users" "Modding Resources/"` is not clean: six binary blobs inside the Ghidra repositories carry the profile path. They are Ghidra internals — no build script and no `.md` leaks a path, and none of the scripts touched this round does.

**Docs and the master index should be updated only after your in-game test**, per the recording convention — except the stale index status above, which is wrong *now* and is exactly the investigation trap the project memory warns about.

---

# ADDENDUM 2026-08-27 (later) — Shield: auto-resolve 75% + magnitude 5

# Shield — auto-resolve ranged protection + magnitude increase

**Applied to `AoWEPACK.dpl`, untested in game.** Nothing here has been played; every claim below comes from reading the live binary, not from a battle.

---

## 1. Status

**Ranged-only was achieved.** The auto-resolve rule fires on the ranged-attack constructor only, so it is ranged-only *by construction* rather than by a flag test — melee never reaches the code at all. No compromise was needed and no melee side-effect exists to watch for.

The one thing that did fail is cosmetic and post-write:

| Change | State | QA |
|---|---|---|
| ⚠ `--apply` exits **1** with a `UnicodeEncodeError` **after** a successful write, truncating over half of its own printed checklist | Cosmetic defect, not fixed | Non-blocking — the bytes on disk are correct and complete; re-run with no arguments to get a clean `rc=0` verification |
| Shield applies at **75% per shot against ranged attacks in auto-resolve** (previously inert there) | Applied, untested | PASS |
| Bonus **+4 → +5 DEF** (a −5 on the shooter's attack byte) | Applied, untested | PASS |
| Manual tactical arc (front / front-left only) left untouched | Byte-identical to the 2026-08-26 build | PASS |
| `--undo` is surgical (no backup restore) | Verified: 327 bytes in 18 runs, all inside the cave and the two link rel32s | PASS |
| Multiplayer lockstep | Argued safe from static reading only | Not falsifiable without a live two-peer test |

QA ran zero remediation rounds. Five findings, none blocking.

---

## 2. What the live binary holds

Only `AoWEPACK.dpl` changed. `AoW.exe`, `AoWCompat.exe`, `AoWTCPCK.dpl` and `Release/Ability.pfs` are all byte-identical to before (the two exes still differ from each other at exactly one offset, `0x3BB7C`, as they should).

**Byte runs written**

| VA | Before | After |
|---|---|---|
| `0x557BCECF` | `e8 30 62 06 00` | `e8 54 62 06 00` — registration link re-pointed, cave_reg moved `0x55823104` → `0x55823128` |
| `0x55812A7B` | `e9 50 06 01 00` | unchanged — the ranged link still enters at `0x558230D0` |
| `0x558230D0` | 51 B | 86 B (the `ranged` sub-cave, below) |
| `0x55823128` | — | cave_reg, 49 B, relocated with identical content |

Whole cave grew **327 → 363 B**. `0x5582316B`–`0x55824FFF` re-read all zero, so the growth zone was genuinely free. Zero `.reloc` type-3 entries anywhere on the cave page or in either displaced span. A capstone operand scan over all 363 bytes (133 instructions) found **no** absolute memory operands — the cave is position-independent, as the rebasing DLL requires.

**Cave layout — the new `ranged` sub-cave, read back from the file**

```
558230E8  8b 45 fc              mov  eax,[ebp-4]         ; victim
558230EB  8b 08                 mov  ecx,[eax]
558230ED  8b 49 e4              mov  ecx,[ecx-0x1c]      ; instance size
558230F0  83 f9 68              cmp  ecx,0x68
558230F3  72 0f                 jb   0x55823104          ; not manual -> fast path
558230F5  56 / ff 75 fc         push esi / push [ebp-4]
558230F9  e8 2a ff ff ff        call 0x55823028          ; SHIELD_ARC (ret 8) — unchanged
558230FE  84 c0 / 74 1b         test al,al / je out
55823102  eb 14                 jmp  0x55823118
55823104  83 f9 64              cmp  ecx,0x64            ; EXACT equality, not jae
55823107  75 14                 jne  0x5582311d
55823109  b8 04 00 00 00        mov  eax,4
5582310E  e8 6d df ed ff        call 0x55701080          ; System.@RandInt
55823113  83 f8 03              cmp  eax,3
55823116  73 05                 jae  0x5582311d          ; the 25% skip
55823118  80 6c 24 04 05        sub  byte [esp+4],5      ; SHARED by both arms
5582311D  89 f0 / 8b 10         mov  eax,esi / mov edx,[eax]
55823121  e9 13 ba f4 ff        jmp  0x5576eb39
```

Both the manual arc arm and the new roll arm converge on **one** `sub byte [esp+4],5`, so the two modes cannot drift apart in magnitude. `[esp+4]` is a private per-action stack slot (argument 3 of `TDamageCA.Generate @0x55729C20`, read once as `movsx byte ptr [ebp+0x10]` at `0x55729C46`) — a signed byte, no shared accumulator, no clamp, and no route to wrapping into a bonus.

**Why manual combat can never take the new branch.** `TFastCombatUnit` (auto-resolve) has instance size `0x64`; `TTacticalCombatUnit` (manual, and it lives in `AoWTCPCK.dpl`) has `0x68`. `0x64` is unique across both modules, and the branch tests exact equality rather than `jae`, so a manual victim always falls through to the geometric arc. This matters more than it looks: the manual path *is* reached from a UI message handler, so an inclusive `jae` here would have put a die roll on a client-local code path.

**Ranged-only, structurally.** Melee builds its action through a different constructor (`CreateStrikeCA`), imported separately by `AoWTCPCK.dpl`. The four ability classes routed through the hooked constructor are `TRangedAttackAbility`, `TBoltsAbility`, `TBreathAbility` and `TFlameThrowingAbility`. The three retired melee Shield sites were re-checked against the pristine `AoWEPACK_original_backup.dpl` and byte-match vanilla.

---

## 3. How the 75% roll works

**Which RNG.** `call 0x55701080`, which is `jmp [0x558FB6DC]` into the import table → `VCL30.dpl!System.@RandInt` (body at `0x41303384`). That is the *same primitive* the existing to-hit roll (`HitRole @0x55725DC0`) and damage roll (`ExecuteDamageRole`) already use — not an analogy, the identical instruction. It is a multiply-shift LCG on `System.RandSeed`, clobbering only EAX/EDX/flags, so ESI, EBP and the stack slot survive the call with no save/restore.

`RandInt(4)` returns the top two bits of the advanced seed, uniform over {0,1,2,3}. `< 3` is therefore **exactly 75.000%** — no modulo bias to argue about.

**Where the draw sits.** Inside the ranged-attack constructor, after the victim nil-check and the ability query, and only on the `0x64` (auto-resolve) arm. `System.RandSeed` is re-anchored once per combat by `TCombat.Execute @0x557282C8`, which is nothing but `System.RandSeed := AoWHSMap.Random($FFFFFF)` — a single draw from the network-synchronised map stream. `TFastCombat.Execute @0x55744A0C` calls it first, then runs the whole battle synchronously off the re-anchored stream.

**The predictor question, plainly: the roll cannot reach the AI's speculative evaluation.** The combat predictor is a separate arithmetic simulator. It never builds a combat action, never dispatches an ability, and draws no random number of any kind — no predictor address appears among the ~115 references to `@RandInt`. Three independent proofs back this: the hooked constructor has exactly two in-DLL callers, both auto-resolve execution bodies; the ability slot that reaches them has exactly one call site in the whole DLL (`TFastCombatUnit.fcExecute @0x5574445E`); and `TCombatPredictor.ExecuteCombatRound` calls only its own unit's `ExecuteRound` and `TList.Delete`. So no gate was emitted, and none is needed.

**The draw-count question, plainly: every peer draws the same number of times.** The roll fires if and only if the victim is non-nil, has Shield, and is a fast-combat unit. None of those reads fog, a timer, a pointer value, a UI state or a local setting — the ability set comes from the strategic unit and its items, and the class is fixed by which combat engine is running. The containing chain is turn-event driven and seeded once per combat, so all machines walk the identical sequence. The roll is **per shot**, not per action: a repeat-fire archer rolls independently for each shot, and a breath attack rolls once per generated action. Both counts are shared game state.

**Multiplayer lockstep — is it affected?** On the static reading, no, and the choice of RNG is deliberately the conservative one. `@RandInt` does **not** advance `[map+0x230]`, the value the out-of-sync comparator reads, so this patch cannot trip a false desync alarm the way a synchronised draw could. The flip side, stated plainly: because it does not touch that value, a hypothetical draw-count divergence here would go *undetected* rather than being caught — the combat would silently diverge. That exposure is not new; it is already true of every existing combat roll, including vanilla's to-hit. What static analysis cannot rule out is client-local animation code disturbing `System.RandSeed` mid-combat. Only a live two-peer test can falsify this.

---

## 4. Undo / re-tune

All commands run from the `Modding Resources` folder; the script resolves the game directory from its own location, so any working directory works.

```
python build_scripts/build_shield.py            # verify current state (rc=0, no writes)
python build_scripts/build_shield.py --dis      # disassemble the installed cave
python build_scripts/build_shield.py --sim      # arc self-test (60/60 expected)
python build_scripts/build_shield.py --apply    # write; idempotent, verify-before-write
python build_scripts/build_shield.py --undo     # surgical revert
```

`--undo` restores the two link rel32s and zeroes the cave. It touches no backup file — proven by the fact that the undone file still differs from `AoWEPACK.dpl.pre-shield` by 92 bytes elsewhere (other features layered since). **Do not revert by copying `.pre-shield`**; it would wipe those other features.

Re-tuning is an **in-place rewrite** — edit the constants and re-run `--apply`. The script now classifies a link pointing at a moved sub-cave of its own as `prior` and re-points it rather than aborting, so no undo step is needed first. This was proven in a sandbox seeded with the old layout: it re-pointed, took 0.4 s, and produced a byte-identical result.

| Dial | Where | Now | Note |
|---|---|---|---|
| **Arc** | `ARC` at the top of `build_shield.py`, passed as `build_cave(arc=…)` | `(0, 5)` — front and front-left | Set `(0, 1)` if it looks mirrored in play |
| **Magnitude** | `pen=` | `5` | Emits `80 6c 24 04 05`; keep it well under 127 (signed byte) |
| **Probability** | the `auto=` argument to `build_cave` | 3-in-4 | Emits `mov eax,<denominator>` / `cmp eax,<threshold>` / `jae skip`. `auto=None` reproduces the old manual-only cave |
| **Level-up cost** | `cost=` | `6` | Overridden in play — see §6 |

If a build binary is locked, kill it and retry; that is standing procedure here, not something to ask about.

---

## 5. In-game checklist

1. **Boot.** Main window with no `Runtime error 217` and no "Ability already registered" dialog.
2. **One full manual battle including a siege with walls, and one auto-resolved battle**, both to completion with no exception dialog.
3. **Auto-resolve, the new behaviour — this needs the most eyes.** Auto-resolve a battle where a shielded unit is shot at repeatedly, several times over, and compare against the same battle unshielded. The shielded side should do measurably worse for the attacker — but *not* by the full −5 on every shot, because it is 75% of shots. One battle proves nothing; this is statistical by construction.
4. **Melee must still be inert in auto-resolve.** Normal attacks, retaliation, free swings taken during movement, and touch abilities (web, entangle, turn undead) auto-resolved: Shield must make no difference to any of them.
5. **Manual combat still protects front and front-left only.** Shoot a shielded unit from its rear and flanks and confirm nothing changed there. If the protected side reads as front-*right*, the arc is mirrored — set `ARC = (0, 1)` and re-run `--apply`.
6. **Confirm the bonus is now 5.** Front / front-left shots should miss noticeably more than yesterday: **−25 percentage points, up from −20**. If it feels identical, the re-tune did not take.
7. **Bearing is irrelevant in auto-resolve** — there are no hexes and no facing there. Do not read a position-dependent result as a bug.
8. **Per shot, not per action.** A repeat-fire archer getting partial protection within one attack is correct.
9. **Breath and flame throwing** now get Shield in auto-resolve as well as manual. Confirm that is wanted.
10. **Nil victim** — a missile absorbed or intercepted before it lands must not crash.
11. **Multiplayer, only if MP is played with this build.** Auto-resolve the same battle on two peers and confirm no out-of-sync. This is the only test that can falsify §3.

---

## 6. Still outstanding

- **No tag 5 description on `Ability.pfs` record 186.** Shield carries no description text, so nothing in game will tell a player about the arc, the 75%, or the +5. Adding one is a **length-changing** `.pfs` write and needs `AoWDevEd`, not a build script. Record 186 currently holds tags 6, 7, 8 and 9 only (re-parsed this session; the file is byte-unchanged by this work, CRC residue verified).
- **Tag 6 level-up cost is 8, the same as Parry.** The `.pfs` value wins over the script's `cost=6`, so the script constant is inert here. Shield is now a ranged defence that also has a geometric arc in manual combat; whether 8 is still the right price against Parry's 8 is a balance decision. Changing it is an editor edit.
- **Shield still sits in the Melee level-up column** of the hero dialog. Now that it defends against missiles and breath and does nothing to melee at all, that placement is arguably wrong. Moving it is a separate change to the hero-dialog category work, not to `build_shield.py`.
- **AI targeting is deliberately unchanged.** The auto-resolve AI will keep shooting shielded units as though unshielded. Teaching it would mean hooking `fcGetDamageValueEx @0x5576E8D4`, which runs during speculative command prefetch — the one genuinely unsafe place to put anything resembling a roll. It was left out on purpose. If the AI's indifference reads as wrong in play, say so and it becomes its own patch.

---

## 7. Known gaps

- **Nothing is confirmed.** Every statement above is derived from reading the live bytes. No battle has been fought.
- **Multiplayer safety is a static argument only.** It cannot rule out client-local animation code perturbing `System.RandSeed` between combat actions. The indirect evidence is strong (the existing to-hit rolls would already be diverging if it happened), but it has not been measured.
- **The out-of-sync comparison itself lives in `Network.dpl`**, which is not in the Ghidra project and was not disassembled. The comparator's semantics were taken from this project's own live-instrumented desync notes.
- **`--apply` exits 1** after a successful write and truncates its own printed checklist. Harmless, but a wrapper script keying on the exit code would misread it as a failure.
- **A live doc now contradicts the live binary** — it still states that Shield does nothing in auto-resolve. That should be corrected when the feature doc is written up, which per the recording convention happens only after the in-game test.
- **The script's docstring claims a defence-in-depth guard against the predictor that the emitted code does not contain.** No guard is needed (§3), but the docstring should be corrected so a future session does not go looking for it.
- **Standing hazard, unchanged by this work:** Shield's ranged link lives inside `build_magebane.py`'s cave. `build_magebane.py` must not be run in any mode — that is the existing cave-collision trap, and it now has a second feature depending on those bytes.
- **Unresolved from the RNG analysis:** what sets bit 3 of the map's flags byte, which would suppress the synchronised generator's seed bookkeeping. It does not affect this patch (which never uses that generator) but is unanswered.
- **Not investigated:** whether the 75% should also apply to the auto-resolve *damage* half. The cave touches only the attack byte, which matches manual behaviour.