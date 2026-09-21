# Unit Spellcasting — Polish Investigation (2026-07-06)

Post-MVP polish research for the unit-spellcasting mod (see `Unit_Spellcasting_INDEX.md`).
Two topics investigated in Ghidra against **vanilla** `AoWEPACK.dpl` (base `0x55700000`; the live
game file is separately patched, so Ghidra shows pre-patch bytes — e.g. gate G6 still reads
`CALL @IsClass` here):

1. **Detection primitives** — how to read a unit's Spellcasting *ability level* and a spell's
   *research tier* (needed for a "level ≥ tier" casting rule).
2. **Multi-turn channelling diagnosis** — why unit casters can *start* but never *progress* a
   multi-turn spell, and exactly what a fix requires.

All addresses are preferred-base VAs.

> **STATUS: APPLIED 2026-07-06** (all units **and** heroes; verified/idempotent):
> - **M1 multi-turn accrual + M2 "level ≥ tier" enforcement gate** → `AoWEPACK.dpl` via
>   `build_spellcast_multiturn.py` (5 patches, backup `AoWEPACK.dpl.pre-multiturn`).
> - **C2 save/load persistence of casting state** → `AoWEPACK.dpl` via `build_spellcast_persist.py`
>   (3 patches, backup `AoWEPACK.dpl.pre-persist`, §7).
> - **M3 hide too-high-tier spells + M4 hide Cosmos spells from *unit* books** → `AoW.exe` +
>   `AoWCompat.exe` via `build_spellcast_book_exe.py` (backups `*.pre-bookfilter`). *An earlier
>   DLL-side M3 was inert and superseded — see §5.*
>
> **✅ ALL CONFIRMED WORKING in-game (user, 2026-07-06):** M1 multi-turn channels progress and
> *complete* over several turns; M2 level-gate holds; C2 casting state survives save→load (§7); a
> low-level caster's "Cast Global Spell" book no longer lists too-high-tier spells (M3); a *unit*'s
> book lists no **Cosmos** spells while heroes and the player's leader keep them (M4, §6). *Test in
> the actual game (`AoW.exe`/`AoWCompat.exe`) — the editor `AoWDevEd.exe` uses a different lister and
> is **not** patched.*
> DLL state: Phase-1 + M1 + M2 + C2 (the superseded DLL-M3 bytes were reverted 2026-07-06).

---

## 1. Detecting the Spellcasting ability level (I–V)

**Use `TAbstractUnit.GetAbilityLevel(unit, abilityID)` @ `0x5577f658`.** Pass `abilityID = 0x34`
(Spellcasting); it returns the level as a byte, or **0 if the unit lacks the ability**. Defined on
the shared base class, so it works on heroes *and* our grown `TUnit`s. It is virtual — unit VMT
slot **`+0x144`** — so a cave can reach it by direct call or vtable dispatch.

Mechanism (traced):
- `GetAbilityLevel` → `TAbilityControl.GetAbility(*(AoWHSSet+0x80), 0x34)` returns the
  `TSpellCastingAbility` flyweight (a `TMultiLevelAbility`), then calls its `GetLevel(unit)`.
- `TMultiLevelAbility.GetLevel` @ `0x557651d8`:
  `data = GetAbilityData(unit, ability[+0xc]); return data ? *(byte*)(data+0xc) : 0;`
  → the level is a **byte at `abilityData + 0xc`** in the unit's per-ability record.

**Range is 1–5**, confirmed by `TSpellCastingAbility.GetLevelName` @ `0x5576dc74` — a switch with
cases 0–5 (a bare name plus five "I"…"V" suffixes). Level 0 = ability absent.

---

## 2. Detecting a spell's research tier

Resolve a spell ID → `TSpell*` with **`TSpellControl.GetSpell(*(AoWHSSet+0x84), spellID)` @
`0x55779ac8`** (the global spell registry; same pattern our other caves use).

`TSpell` field map (recovered from `ValidResearchSpell`, `CastingMana`, `CanCastSpell`):

| Offset | Type | Meaning | Witness |
|---|---|---|---|
| `+0x14` | int  | **base mana cost** | `CastingMana` @ `0x557894ec` |
| `+0x20` | byte | **sphere** (Air/Fire/…) | `ValidResearchSpell`, `CastingMana` |
| `+0x21` | byte | **research tier / level** | `ValidResearchSpell` @ `0x5577cff0` |
| `+0x22` | byte | spell category (`2` = global enchantment) | `TSpell.CanActivate`, `THero.CanCastSpell` |

**Tier range is 1–4.** `TPlayerMagicControl.ValidResearchSpell` buckets researched spells by
`+0x21` into slots `[1..4]` and caps the unlockable tier at `iVar3 < 4`. Matches "Storm = tier 4"
(the maximum). Research is gated two ways: `spell[+0x21] ≤ sphere-picks` **and** `spell[+0x21] ≤`
(highest tier with >1 spell already researched at every lower tier).

`CastingMana(spell)` = `spell[+0x14]`, **doubled** if `GetSphereManaDoubled(spell[+0x20])` — it
touches no hero state, so it already yields the right cost for units.

---

## 3. The "level ≥ tier" casting rule

Directly computable — every primitive exists:

```
castable  ⟺  GetAbilityLevel(unit, 0x34)  ≥  *(byte*)(GetSpell(reg, spellID) + 0x21)
```

**Injection point:** `THero.CanCastSpell` @ `0x55789710` — the exe calls it *generically* on the
caster object (hero or grown unit), and it already resolves the `TSpell` into a register and
returns an error string. Add the compare right after the resolve; it gates both instant and
multi-turn casts (`CastSpell` calls `CanCastSpell` first).

**Two open design decisions (need user sign-off before implementing):**

- **Heroes too, or units only?** In vanilla, a hero's Spellcasting *level* gates casting
  **points/speed**, *not eligibility* — a Spellcasting-I hero may channel a tier-4 spell over many
  turns. `CanCastSpell` is shared, so an unconditional rule would be a **new restriction on
  heroes**. To preserve vanilla heroes, scope the gate to non-heroes (inverted `cave_iscaster`
  idiom).
- **1–5 vs 1–4 mapping.** Because tiers cap at 4, **Spellcasting IV already unlocks every spell**;
  V would add only points, not eligibility. Coherent, but confirm it's intended.

---

## 4. Multi-turn channelling — why it's frozen, and the fix

### Casting cluster (grown unit / hero, shared layout)
| Offset | Type | Meaning |
|---|---|---|
| `+0x80` | byte | current casting points |
| `+0x84` | int  | spell-in-progress ID (`0` = idle) |
| `+0x88` | int  | progress (accumulated points) |
| `+0x8C` | int  | required (= total `CastingMana`) |
| `+0x90` | int  | ready-event log id |

### The three phases and where units stand

- **Start — WORKS for units.** `THero.CastSpell` @ `0x55789854`, when `points < CastingMana`,
  emits a `THeroUpdateTE(type 2, spellID)`; executing it runs `THero.ExecuteStartCasting` @
  `0x55789130`, which **deducts the full mana up front**, sets `+0x8C = CastingMana`,
  `+0x88 = current points`, `+0x84 = spellID`. No class gate (TEs are unit-ID based) → the channel
  starts and the UI shows "preparing," which is what we observe.

- **Accrual — MISSING (the freeze).** The per-turn advance lives **only in `THero.NewTurn` @
  `0x55787fcc`**, not in the base:
  ```c
  TAbstractUnit.NewTurn(u, turn);            // base: movement/HP only — NO casting
  if (turn == owner) {
      THero.ValidateHeroUpgrade(u);          // hero-only (see landmine below)
      pts = GetCastingPointsMax();
      u[+0x80] = pts;                         // refill
      if (u[+0x84]!=0 && u[+0x88] < u[+0x8C]) {   // ← our unit cave never runs this block
          u[+0x88] += pts;                    // progress accrues
          u[+0x80]  = 0;
          if (u[+0x88] > u[+0x8C]) { u[+0x80] = u[+0x88]-u[+0x8C]; u[+0x88] = u[+0x8C]; }
          if (u[+0x88] == u[+0x8C])           // ready → create TSpellCastEventLog,
              …AddEvent + conditional Execute; // AddEvent to eventbook, Execute now if viewer
      }
  }
  ```
  Our `cave_unit_newturn` (VMT slot `+0x13C`) calls the **base** `TAbstractUnit.NewTurn` @
  `0x55780D4C` + a bare refill, so `+0x88` never advances and `CastingReady` is never true.
  Predicates: `Casting` @ `0x89598` (`+0x84!=0`); `CastingReady` @ `0x895a4`
  (`+0x84!=0 && +0x88==+0x8C`); `CastingDone` @ `0x893e8` (clears cluster; mana already paid).

- **Completion — ALREADY UNBLOCKED for units.** `TSpellCastEventLog.Execute` @ `0x5577a1c8`
  resolves the caster and, if ready, fires the cast via the Spellcasting flyweight's vtable
  `+0xb4`. Its `IsClass(unit, THero)` check is at **`0x5577a25c` = gate G6**, already retargeted to
  `cave_iscaster` in the live game. So once a unit reaches "ready" *and* a ready-event exists, the
  cast completes.

### Landmine — do NOT just repoint the NewTurn slot to `THero.NewTurn`
`THero.ValidateHeroUpgrade` @ `0x55787d54` is deeply hero-specific: it reads/writes experience via
vtable slots `+0x15c`/`+0x160`, indexes `HeroExperienceTable`, mutates the level cache at `+0x4C`,
and fires `THeroUpgradeEventLog`. On a unit those vtable slots are **not** experience accessors →
garbage dispatch (the same crash class the card-mana attempt hit), plus spurious "hero levelled
up" popups. It does **not** early-out for owned units (its `owner==0` guard fails for real
players). So the whole-function redirect is unsafe.

### The fix (feasible; = the previously-shelved "C1-progress cave")
Extend `cave_unit_newturn` to replicate **only** `THero.NewTurn`'s casting block (the `if
(u[+0x84]…)` above) — the accrual arithmetic **and** the ready-event creation — while **omitting
`ValidateHeroUpgrade`**. All fields are in the grown region; `GetCastingPointsMax` is already
redirected on units; the ready-event helpers (`EventLog.Create` / `TEventLogbook.AddEvent` /
`GetPlayers`, then `eventLog.vtable[0x70]` Execute and `+0x2c`) transcribe directly from
`THero.NewTurn` @ `0x55787fcc`. **No new gates needed** — G6 already covers completion.

Pairs naturally with §3: gate channel *start* with the level≥tier rule at `CanCastSpell`, and let
this cave drive *progress*.

### Note on prior scope
This is the "C1-progress cave" that was **shelved on 2026-07-05** ("leave multi-turn disabled").
This investigation re-opened that decision; the user chose **enable + tier-gate (units and heroes)**
on 2026-07-06, and it is now implemented (§5).

---

## 5. Implementation — `build_spellcast_multiturn.py` (APPLIED 2026-07-06)

Self-contained AoWEPACK.dpl patcher; **requires `build_spellcast.py` (Phase 1) applied first**
(it checks TUnit instance size `0x94` + the Phase-1 C1 pointer, and aborts otherwise). Dry-run by
default, `--apply` to write, idempotent, verify-before-write. Backup: `AoWEPACK.dpl.pre-multiturn`
(= Phase-1 state, pre-multi-turn). 5 patches:

**M1 — multi-turn accrual.** New `cave_unit_newturn` @ `0x5580D940` (30 B): replicates the NewTurn
prologue (`push ebx/esi/edi`; base `TAbstractUnit.NewTurn` @ `0x55780D4C`; owner check), then
`jmp 0x55787FEC` — into `THero.NewTurn` just past `ValidateHeroUpgrade`. The hero's own
refill+accrual+ready-event code runs in place; its epilogue (`POP EDI/ESI/EBX/RET`) balances our
matching pushes. C1 (VMT `+0x13C`, both `TUnit` `0x55710CAC` and `TAdjustableUnit` `0x55712A54`)
repointed from the old Phase-1 cave (`0x5580D90D`) to `0x5580D940`; the old cave is left as dead
bytes. Completion rides on Phase-1 gate **G6** (already unblocked for units).

**M2 — level ≥ tier gate (enforcement).** New `cave_tiergate` @ `0x5580D95E` (47 B), entered from a
6-byte inject at `0x5578974D` in `THero.CanCastSpell` (right after `GetSpell`; overwrites
`mov esi,eax; movsx edx,[ebx+0x24]` → `jmp cave; nop`). The cave replicates `mov esi,eax`, calls
`GetAbilityLevel(caster,0x34)` (regs preserved via push/pop), compares to `TSpell+0x21`; if
`level < tier` it blocks via the function's own fail exit (`xor ebx,ebx; jmp 0x55789826`), else
restores `edx=owner` and continues at `0x55789753`. **Applies to units AND heroes** (unconditional
— `CanCastSpell` is the shared strategic chokepoint; xrefs confirm the player's *global* spellbook
casting goes through `TPlayerMagicControl`, not here, so the wizard is unaffected). Gates instant +
channel-start + **AI** casting (the AI lists via `TPlayerMagicControl.ListSpells` directly, so M2 is
its only tier check — keep it even though M3 hides the spells from humans).

**M3 — hide too-high-tier spells from the casting book (UX). Lives in the EXE, not the DLL.**
`build_spellcast_book_exe.py` → `AoW.exe` + `AoWCompat.exe` (backups `*.pre-bookfilter`).

*Why the first attempt (DLL, superseded) was wrong:* the "Cast Global Spell" book is filled by the
**exe calling `TPlayerMagicControl.ListSpells` directly** (import thunk `0x402654`); the exe never
imports/calls `THero.ListSpells`. So the DLL hook on `THero.ListSpells`' internal call was **inert**
(it never runs). Confirmed via `re_tools/pescan.py iatrefs`: the exe has exactly one `ListSpells`
import — `TPlayerMagicControl.ListSpells` — and 5 call sites.

*The working fix:* the book-population sites carry no caster level, **but** the current caster is in
the window object at `[window+0x22C]` (proven: the `CastSpell`/`CanCastSpellInstantly` sites in the
same functions call `THero.CastSpell([window+0x22C],…)`). At every `ListSpells` call site
`EDX = &collector = window+0x224`, so **`caster = [EDX+8]`**. We redirect all 5 `call 0x402654`
sites (`0042F0F9 / 0042F20C / 00430D58 / 00430DDE / 00430EDD`) to `cave_bookfilter` @ `0x0060C0A8`
(84 B, in the card patch's `.sc` section). The cave: runs the real `ListSpells` (fills the
collector), reads `caster=[EDX+8]`, gets `level = caster.vtable[+0x144](0x34)` (GetAbilityLevel),
then **compacts the collector's `TSpellList` in place** (`list=[EDX]`; `TList=[list+4]`;
`count=[TList+8]`; `items=[TList+4]`), dropping every entry with `TSpell+0x21 > level`. No DLL calls
(pure field access + one vtable call), null-caster guarded, `ebx/esi/edi` preserved.

Filters by *whoever the current caster is*: a low-level unit/hero loses the too-high tiers; a
max-level caster (Spellcasting V) keeps everything. Consistent with M2. Depends on the card patch's
`.sc` section (shared cave region).

### Caveats / follow-ups
- **M2 block is silent** if ever reached (no error string) — but with M3 hiding the spells, a human
  shouldn't hit it. A message is now optional. (Chosen over hunting the bottom-screen
  error-string/thunk plumbing, per user 2026-07-06.)
- **Strategic only.** Combat (TCPCK) tier-gating, if wanted, is a separate patch.
- **Editor not covered.** `AoWDevEd.exe` uses `TSpellControl.ListSpells` (a different, caster-less
  enumerator) for its book — M3 would need a separate, harder patch there. The game exes are the
  target.
- **M3 depends on the card patch** (its cave sits in the card's `.sc` section). Revert order below.
- **Hero behaviour change:** a hero with Spellcasting < a researched spell's tier can no longer
  cast/channel it (vanilla allowed slow channelling regardless). Intended per the user's choice; to
  restore vanilla heroes, drop M2's inject (or scope it to non-heroes via inverted `cave_iscaster`).
- **Save-persistence (C2) still open** — an in-progress channel's cluster isn't serialized, so a
  mid-channel spell is lost on save/load and the mana paid up front is forfeited.

### Test (in-game, needed)
1. Give a unit **Spellcasting** (any level) and research a spell whose per-turn cost exceeds the
   unit's casting points (so it must channel). Start the cast → confirm progress advances each turn
   and completes (spell fires, "casting ready"/effect) instead of freezing.
2. Tier gate + book filter (in the **game**, `AoW.exe`/`AoWCompat.exe`): a **Spellcasting-II**
   caster's "Cast Global Spell" book should **not list** tier-3/4 spells (e.g. Summon Gold Dragon,
   Life L4) but should list tier-1/2 (e.g. Disjunction, Cosmos L1); **Spellcasting-IV/V** lists all.
   Verify a low-skill **hero**'s book is likewise pruned. (M2 is the AI/backstop.)

### Revert — ⚠ none of these routes is usable as written; verify layering first
Run `python "Modding Resources/re_tools/revert_audit.py"` before acting on any bullet below.

- **Book filter (M3) only:** ~~copy `AoW.exe.pre-bookfilter` / `AoWCompat.exe.pre-bookfilter`~~ — those
  backups still exist, but they are **2nd of 8** exe layers as of 2026-07-30. Restoring them destroys
  the 6 features applied since (`firefeed`, `combatlog`, `tierresearch`, `clogfix`, `clogwinhide`,
  `bltprobe`). Undo surgically from `build_spellcast_book_exe.py` instead.
- **Multi-turn + gate (M1/M2) only:** ⚠ `AoWEPACK.dpl.pre-multiturn` was **moved** to
  `Modding Resources/backups/` on 2026-07-29/30 (not deleted) — but it is layer **2 of 47**, so
  restoring it destroys 45 later features. Undo surgically from `build_spellcast_multiturn.py`
  (restore the patched sites, zero its caves) instead.
- **Card + book together:** ~~copy `*.pre-cardv2` over the exes~~ — `.pre-cardv2` is the **oldest of 8**
  exe layers; restoring it wipes all 7 features above it. M3's cave lives in the card `.sc` section, so
  the two are entangled; undo both surgically from their build scripts rather than by snapshot.
- **DLL-M3 cleanup — DONE 2026-07-06** (historical). The superseded DLL M3 (redirected `CALL` @
  `0x55787A15` + dead `cave_listfilter` @ `0x5580D98D`) was removed at the time by
  `copy AoWEPACK.dpl.pre-multiturn AoWEPACK.dpl` + `python build_spellcast_multiturn.py --apply`.
  **Do not repeat that command** — `.pre-multiturn` is now layer 2 of 47 and restoring it would wipe
  44 features. Verified then: `0x55787A15` = original `E8 2E 57 FF FF`, the 68-byte cave region
  all-zero, M1+M2 intact (idempotency 5/5).

---

## 6. Spell spheres + "Cosmos uncastable by units" (M4) — ✅ CONFIRMED WORKING in-game (user, 2026-07-06)

### How spheres are determined
- **`TSpell + 0x20` = sphere index (byte).** Enumeration (from `TLeader.GetSpherePicks`
  @ `0x5578B17C` and `CanAddSphere` @ `0x5578B1F8`): **0 = Cosmos**; 1–6 = the six elemental/L-D
  spheres in three opposed pairs (Life↔Death, Air↔Earth, Fire↔Water). Six magic-node classes exist
  (Air/Death/Earth/Fire/Life/Water); Cosmos has no node.
- **Cosmos (0) is special:** `GetSpherePicks(leader, 0)` **hard-returns 4** (max tier); every other
  sphere returns the count of that sphere in the leader's picks. That is *exactly* the "Cosmos is
  researchable regardless of sphere picks" rule — `ValidResearchSpell`'s `tier ≤ GetSpherePicks(sphere)`
  is always satisfied for Cosmos (tiers are 1–4). Sphere 0 also can't be manually picked
  (`CanAddSphere` requires `sphere != 0`).
- So **a Cosmos spell ⟺ `*(byte*)(TSpell+0x20) == 0`**.

### The rule: Cosmos castable by heroes (and the leader) only, not units
"Hero-family" must include **TLeader** — it's a **subclass of THero** (VMT `0x55712238`, the player's
wizard, and the owner of `GetSpherePicks`). It *overrides* `ClassID` (`0x5578B0C8`), so an exact
`ClassID == THero(0x20230)` test would wrongly exclude the leader. Use **`IsClass(caster, THero)`**
instead (true for THero + TLeader, false for `TUnit`/`TAdjustableUnit`).

### Implementation — extended `cave_bookfilter` (exe), `build_spellcast_book_exe.py`
The M3 exe cave now drops a spell when **`tier > level` OR (`sphere==0` AND `!IsClass(caster,THero)`)**.
The hero-family test: `mov edx,[0x45DFC4]` (exe THero classref) + `call 0x401070` (@IsClass) — both
absolute-safe (exe is fixed-base 0x400000). Cave grew 84→130 B (still in the card `.sc` section);
`.sc` VirtualSize bumped to `0x12A`. Re-applied to `AoW.exe` + `AoWCompat.exe` (restore
`*.pre-bookfilter` then `--apply`; same backup covers it).

**Net:** a unit's "Cast Global Spell" book hides all Cosmos spells (e.g. Disjunction) *and* its
too-high tiers; a hero's or the leader's book keeps Cosmos. Correctly preserves the player's own
(leader) casting — IsClass covers the TLeader subclass.

### Scope decision — AI gap accepted (WON'T FIX, user 2026-07-06)
The **AI can still cast Cosmos with units** — it lists candidates via `TPlayerMagicControl.ListSpells`
*directly* (DLL), bypassing this exe cave. The user has decided this is **not a problem**, so the
DLL-side enforcement is **not being built** (it would need the THero classref inside a rebasing DLL
cave — a riskier position-independent `call/pop` delta — for no user-visible benefit). The exe filter
governs all human play, which is the intent.

### Test result (in-game, 2026-07-06)
✅ Confirmed: a Spellcasting **unit**'s book shows **no Cosmos spells** (Disjunction, etc.) at any
level; a **hero**'s and the **player's own (leader)** book still show Cosmos.

---

## 7. Save/load persistence of casting state (C2) — ✅ CONFIRMED WORKING in-game (user, 2026-07-06)

`build_spellcast_persist.py` → `AoWEPACK.dpl` (backup `AoWEPACK.dpl.pre-persist`; independent of
M1/M2 so it can be reverted alone). 3 patches.

**Problem:** `TUnit`/`TAdjustableUnit` ReadWrite (the object serializer) never wrote the casting
cluster, so on load a unit's points reset (to 0 → refills next turn) and any in-progress channel was
lost. `THero.ReadWrite` @ `0x55788880` *does* serialize those fields; we mirror it for units.

**Save format = property table** (`TPropertyTable.PropertyExist`): every field has a numeric TAG;
on read a missing tag falls back to a default. So appending new tagged fields is compatible **both
ways** — an old/pre-mod save lacks the tags (unit loads with cleared casting state), and a mod-made
save loaded by an *unpatched* game simply ignores the extra properties (no corruption). THero's
casting tags (`0xd,0xe,0x1f,0x22,0x23`) don't collide with TUnit's (`7/8/9/0xa`) or the base chain
(`TAbstractUnit 4/5/6/0x2f`, `TAbilityOwner 0x31/0x32+`) — they already coexist inside THero.

**Fields persisted** (exact transcription of THero's tagged stream calls): `+0x80` points (byte, tag
`0xd`, stream vtable `+0x30`); `+0x84` in-progress spell id (int, `0xe`, `+0x2c`); `+0x88` progress
(int, `0x1f`, `+0x2c`); `+0x8c` mana required (int, `0x22`, `+0x2c`); `+0x90` ready-event id (int,
default `-1`, tag `0x23`, `+0x40`). **Not** persisted: `+0x7C` power-source ptr (THero doesn't
persist it either — runtime-only; units use the player mana pool).

**Mechanism:** redirect the ReadWrite VMT slot `+0x18` of each unit class to a thin wrapper that
calls the **original** ReadWrite (different per class!) then a shared `cave_cast_fields` that appends
the 5 tagged fields. Caves @ `0x5580D990` (register/rel32 only). Note `TUnit` VMT `+0x18` =
`TUnit.ReadWrite` (`0x55782CEC`) but `TAdjustableUnit` VMT `+0x18` = `TAbstractUnit.ReadWrite`
(`0x557820E4`) — hence two wrappers. One cave (bidirectional) handles both save *and* load because
the stream methods read or write per the stream's mode byte (same as THero.ReadWrite).

### Test result (in-game, 2026-07-06)
✅ Confirmed: a unit's casting state (points / in-progress spell / progress) survives a save→load
round-trip. (Reminder: in **MP**, both peers need the patched DLL, as with all patches.)

### Revert
- ⚠ `AoWEPACK.dpl.pre-persist` (which dropped only C2, keeping M1+M2) was **moved** to
  `Modding Resources/backups/` on 2026-07-29/30 — it exists, but as layer **3 of 47** it would destroy
  43 later features. To remove C2, undo it surgically: restore the two `ReadWrite` VMT wrappers to
  `0x55782CEC` / `0x557820E4` and zero the cave at `0x5580D990`, verify-before-write.
