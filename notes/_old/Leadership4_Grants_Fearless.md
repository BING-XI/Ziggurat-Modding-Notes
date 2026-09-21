# Leadership IV grants Fearless to the stack

**Status: APPLIED 2026-09-01, UNTESTED IN GAME.** Not confirmed — the user's in-game test decides
(§7). Every address, byte run and register contract below was verified against the live
`AoWEPACK.dpl` and byte-diffed against `Modding Resources/AoWEPACK_original_backup.dpl`.

**Script:** `build_scripts/build_leadership_fearless.py` — dry-run default, `--apply`, `--dis`,
surgical `--undo`. **Binary:** `AoWEPACK.dpl` only — Fearless is not queried by `AoW.exe`,
`AoWTCPCK.dpl` or `aowInt.dpl` (`abquery.py --id 0x43` on all four modules), so there is no
AoW.exe/AoWCompat lockstep half. **Backup:** `AoWEPACK.dpl.pre-leadfearless` — *do not use it to
revert*, use `--undo`.

**As built:** cave `C_FEAR` @ `0x5582C000`, 58 bytes (span asserted zero-or-ours to `0x5582C080`);
five 15-byte site patches; threshold `LEAD_LEVEL = 4`, a tunable at the top of the script.

**Post-apply checks run 2026-09-01, all green:** the installed cave disassembles from the live file
to §4 exactly, with `call [ecx+0xB8]` as the second dispatch (§5); `--undo` restores the DLL
**byte-for-byte identical** (sha256 match against `.pre-leadfearless`) and re-`--apply` is
idempotent; `rng_audit.py --owners` lists 23 modded sites and **none at `0x5582C000`** — the cave
makes no draw; no drive-letter path and no absolute VA anywhere in the cave span; and
`build_terror_oncepercombat`, `build_panic_nomelee`, `build_lifesteal_roundattack`,
`build_item_hpmv`, `build_leadership4`, `build_leadership_fix` and `build_leadership_aura` all
still verify as applied afterwards.

Preferred-base VAs, base `0x55700000`. Leadership id `0x2E`, Fearless id `0x43`,
Panicked id `0x6C`, Cause Fear id `0x33`.

---

## 1. What Fearless actually is

A **plain bit-only passive** — registered by `PassiveAb`, no ability class, no per-owner data
record. A module-wide byte scan for `mov edx,0x43` finds six sites: four queries and two
registration-table entries (`PassiveAb.UnregisterPassiveAbilities+0x1D4`,
`GlobalSpells.UnregisterGlobalSpells+0x68` — the latter is a *spell* id, different namespace).

**Fearless means exactly one thing: "cannot be given the Panicked status."** Scanning the
producers of `0x6C` confirms the only ones are the melee Cause Fear strike and the two Terror
CAs. There is no morale-driven panic to be immune to — `TAbstractUnit.GetUnitMoraleValue+0xDE`
only *reads* Panicked (a panicked unit has worse morale, not the reverse).

### The strategic-map site already exempts Leadership — leave it alone

`AoWE.TAbstractUnit.ExecuteLifeMasteryFearRole @0x55780B90` tests Fearless at `+0x26` and then
tests **Leadership at `+0x39`** (`mov edx,0x2E` @`0x55780BC9`, `jne` out). Vanilla already makes
any Leadership holder immune to Life Mastery fear on the strategic map, at every level. This
site needs no patch, and patching it would be redundant.

---

## 2. The propagation is free — do not build an aura

`AoWE.TArmy.UpdateFormation @0x5578D034` pass 2 runs over **every unit in the army with no
gate**: `if GetAbilityLevel(u,0x2E) < armyMax: SetExternalSource(u, armyMax, srcName)`
(@`0x5578D17B`). So every member of a Leadership-IV stack — the leader included — already reads
`GetAbilityLevel(unit, 0x2E) == 4`.

`AoWE.TCombatUnit.SetParty @0x557250D6` re-runs `UpdateFormation` on the party's army at combat
start, so the borrowed level is live in tactical **and** fast/auto-resolve combat. The scope is
therefore identical to Leadership's existing ATK/DEF bonus, for free.

Full detail of the aura machinery: `Leadership_Disable_Bug_RootCause.md` §3.

⚠ **Consequence to expect in game:** `UpdateFormation` runs at `SetParty` only, so the immunity
persists for the whole battle even if the Leadership-IV hero dies mid-combat. That is exactly how
vanilla already treats the ATK/DEF bonus — consistent, not a defect.

---

## 3. Why NOT to grant the Fearless bit

Rejected approach: set `SetAbilityEnabled(u, 0x43, 1)` on stack members from `UpdateFormation`.

Fearless is **bit-only — it has no data record**, so there is no `data[+0x0c]` own-level byte to
distinguish "borrowed from the aura" from "inherent". That is the exact shape of the Leadership
disable bug (`Leadership_Disable_Bug_RootCause.md`), but strictly worse: the aura GC's
`own == 0` discriminator does not exist here at all. Un-granting would need a bespoke shadow
store, and a bug in it **permanently strips native Fearless from undead, elementals and every
other unit that ships with it**.

Cost of not doing it: the stack member's unit card shows `Leadership IV` but not `Fearless`.
`AoWE.TCustomAbilityList.ListAbilitiesEx @0x5574E52C` builds the card list by iterating the
owner's **bitset** (`call [ecx+0x4C]` = `GetAbSet`, @`0x5574E56F`), so a card entry requires the
real bit — there is no cheap display-only hook. **User ruling 2026-08-31: effect only, no card
entry.**

---

## 4. The design — five sites, one cave

Every consumer that matters is the **same 15-byte run**, and all five are byte-identical to the
pristine DLL (no Ziggurat patch touches any of them):

```
ba <id> 00 00 00   mov edx, <ability id>
8b c6 / 8b c3      mov eax, esi / ebx          ; the combat object under test
8b 08              mov ecx, [eax]
ff 91 a8 00 00 00  call [ecx+0xA8]             ; TCombatUnit.GetAbilityEnabled
```

| # | VA | function | id | reg | what it gates |
|---|---|---|---|---|---|
| 1 | `0x557668F5` | `AoWE.TStrikeCA.Generate+0x41` | `0x43` | esi | melee **Cause Fear** |
| 2 | `0x557F983D` | `CombatSpells.TFastCombatTerrorCA.Generate+0x5D` | `0x43` | ebx | **Terror**, auto-resolve |
| 3 | `0x557F99C1` | `CombatSpells.TTacticalCombatTerrorCA.Generate+0x29` | `0x43` | ebx | **Terror**, tactical |
| 4 | `0x557F9D4E` | `CombatSpells.TTerror.tcGetDamageValueEx+0x0A` | `0x6C` | esi | AI value, tactical |
| 5 | `0x557F9B64` | `CombatSpells.TTerror.fcPrefetchCombatCommands+0x44` | `0x6C` | ebx | AI value, fast |

Sites 1–3 are the effect. Sites 4–5 are the AI's "is this target worth counting" test — vanilla
checks only Panicked there, never Fearless, so the AI already overvalues Terror against immune
targets. Routing them through the same cave makes the AI score a Leadership-IV stack as a
non-target **and** incidentally fixes that pre-existing vanilla case for natively-Fearless units.
(User ruling 2026-08-31: include sites 4–5.)

**Patch shape, identical at all five** — the `mov edx,<id>` stays, so one cave serves both ids:

```
ba <id> 00 00 00   mov edx, <id>        ; unchanged
8b c6 / 8b c3      mov eax, <reg>       ; unchanged
e8 <rel32>         call CAVE
90 90 90                                ; 15 bytes exactly
```

### The cave (EAX = combat object, EDX = original id → AL)

```
    push ebx
    mov  ebx, eax
    mov  ecx, [eax]
    call [ecx+0xA8]        ; the original query (Fearless or Panicked)
    test al, al
    jne  .true
    mov  eax, ebx
    mov  ecx, [eax]
    call [ecx+0xB8]        ; GetAbilityOwner -> TAbstractUnit, or nil
    test eax, eax
    je   .false
    mov  edx, 0x2E
    mov  ecx, [eax]
    call [ecx+0x144]       ; TAbstractUnit.GetAbilityLevel(Leadership) = max(own, borrowed)
    cmp  eax, 4
    jl   .false
.true:
    mov  al, 1
    pop  ebx
    ret
.false:
    xor  eax, eax
    pop  ebx
    ret
```

~40 bytes. **No absolute references and no rel32 calls at all** — every call is an indirect VMT
dispatch — so position-independence is free: no `call/pop` delta anchor is needed.

Register safety: Delphi register convention makes EAX/EDX/ECX volatile and EBX/ESI/EDI/EBP
callee-saved. All five host functions keep the object in ESI/EBX/EDI and EBP; the cave saves the
one register it uses.

**Cave `0x5582C000`, span asserted zero-or-ours to `0x5582C080`.** ⚠ `0x5582B200` was the first
choice and is **wrong**: `build_item_hpmv.py` owns `0x5582B000`–`0x5582B200`, and `0x5582B200` is
its `CAVE_END`. Other nearby claims: Terror-once `0x5582A000`–`0x5582A200`, `build_panic_nomelee.py`
`0x55828000`–`0x55828068`. `0x5582C000` is clear of all of them and was verified all-zero in the
live DLL. ⚠ Re-scan for free space at build time rather than trusting any of these figures — grep
`build_scripts/` for the address band, don't just look for a zero run, because a script's declared
span extends past its last emitted byte.

---

## 5. ⚠ The trap: `+0xB0 GetAbilityLevel` cannot be used here

The obvious cave calls `TCombatUnit.GetAbilityLevel` (VMT `+0xB0`) directly. **That crashes.**

`Ghidra_VMT_Layouts.md` records the rule — `+0xB0` is *not* nil-guarded and may only be called
"directly behind a `+0xA8` gate on the same object in the same function". The subtlety that bites
here is what "behind the gate" means:

```
55725004  +0xA8 GetAbilityEnabled:  mov ecx,[eax+0x4C] / test ecx,ecx / je -> return 0   GUARDED
55725028  +0xB0 GetAbilityLevel:    mov eax,[eax+0x4C] / mov ecx,[eax] / call [ecx+0x144]  NOT
```

`+0xA8` returns 0 for **both** "nil `[obj+0x4C]`" and "ability not enabled" — and this cave calls
its second query precisely when the first returned **false**. So a `+0xA8` call that returned
false is *not* proof of a non-nil owner; the gate the rule means is a `+0xA8` that returned
**true**. A nil `[combatobj+0x4C]` is normal engine state, not corruption, so this would be a
real intermittent crash.

**The fix — use `+0xB8 GetAbilityOwner`, which is nil-safe on both classes:**

```
55725000  TCombatUnit.GetAbilityOwner:    mov eax,[eax+0x4C] / ret     ; nil in -> nil out
557268D0  TCombatObject.GetAbilityOwner:  xor eax,eax / ret            ; walls, structures
```

Test EAX for nil, then dispatch `TAbstractUnit.GetAbilityLevel` (`+0x144`, item-aware) on the
strategic unit — the same function `+0xB0` would have forwarded to. No `IsClass`, no classref
global, no absolute reference.

**Generalisable:** *a nil-guarded accessor returning false does not discharge the guard for its
ungated sibling.* When a cave needs the same object twice and the first query may legitimately
return false, reach for the accessor that returns the pointer (`GetAbilityOwner`) and test it,
rather than inferring safety from a boolean.

---

## 6. Collision audit against live features (all clear, 2026-08-31)

| feature | its patch | overlap? |
|---|---|---|
| `build_lifesteal_roundattack.py` | `jmp 0x5580DCD0` @`0x557668E2`, cave returns to `0x557668E7` | no — site 1 is `0x557668F5` |
| `build_terror_oncepercombat.py` | entry `jmp` @`0x557F9B20` (7 B, ends `0x557F9B27`) | no — site 5 is `0x557F9B64` |
| `build_terror_oncepercombat.py` | `tcGetDamageValueEx` wrapped at **VMT slot** `0x557F625C` → `0x5582A120`; function body untouched | no — site 4 is in the body |
| `build_panic_nomelee.py` | caves `0x55828000`–`0x55828068` | no |
| `build_item_hpmv.py` | caves `0x5582B000`–`0x5582B200` | no — our cave is `0x5582C000` |

All seven neighbours (`terror_oncepercombat`, `panic_nomelee`, `lifesteal_roundattack`,
`item_hpmv`, `leadership4`, `leadership_fix`, `leadership_aura`) were re-run after `--apply` and
all still report applied.

**`C_WRAPTC` interaction checked and benign.** `Terror_OncePerCombat.md` summarises the tactical
wrapper as `value = max(1, value>>6)`, which would have inflated an immune target's fresh 0 back
to 1. The actual cave short-circuits first (`mov eax,[ebx]; test eax,eax; je done` @`0x5582A151`),
so a zero stays zero. The doc's shorthand is loose; the code is right.

**RNG:** the cave makes no draw of any kind, so the SYNC/RAW rule is satisfied vacuously. Re-run
`re_tools/rng_audit.py --owners` after `--apply` regardless — that is the standing rule.

**Saves / MP:** nothing is written to any unit, so there is no save-format interaction and no
new state to replicate. All five hooks are pure derivations of state the engine already
replicates.

---

## 7. Acceptance criteria

**Checkable without the game**

1. All five sites read the expected 15 vanilla bytes before write; after `--apply` each reads
   `ba <id> 00 00 00 / 8b c6|8b c3 / e8 <rel32 to cave> / 90 90 90`.
2. The cave disassembles to §4 exactly, with `[ecx+0xB8]` — **not** `[ecx+0xB0]` — as the second
   dispatch. This is the single most important byte in the patch (§5).
3. No absolute address constant anywhere in the cave (grep the cave extent for any dword in
   `0x557.....`/`0x558.....`); no drive-letter path.
4. `--undo` restores all five 15-byte runs and zeroes the cave; re-running the script afterwards
   reports "not applied".
5. `rng_audit.py --owners` prints `ok` for the new cave.
6. The four live features in §6 still verify as applied.

**In-game only (the user's test)**

1. A unit in a stack with a **Leadership IV** hero, hit by a Cause Fear melee attacker, never
   becomes Panicked. The same unit at **Leadership III** still does.
2. Same, for the **Terror** spell in tactical combat, and again in auto-resolve.
3. The hero itself is immune too.
4. A unit with **native** Fearless (undead) still shows Fearless on its card and is still immune
   after leaving the stack — the bit was never touched.
5. The AI does not repeatedly target a Leadership-IV stack with Terror.
6. Save/load: no change expected — nothing is serialised.
