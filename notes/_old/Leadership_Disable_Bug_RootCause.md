# Leadership "permanently disabled" bug — root cause

**Status: FIXED — CONFIRMED WORKING IN-GAME (2026-07-20)** — `build_scripts/build_leadership_fix.py`.
Revert with `--undo` (surgical, added 2026-09-02: restores both call sites, zeroes the cave, touches no
backup); the `.pre-leadershipfix` snapshot no longer exists and was never a safe revert path. As-built
detail and regression checklist: **`Leadership_FourLevels_And_Fix.md`**.

All addresses are AoWEPACK.dpl preferred-base VAs (base `0x55700000`; rebased at runtime).
Leadership ability id = `0x2e`.

---

## 1. Summary

> A unit or hero that earns Leadership **while standing in another leader's aura** never receives its
> own inherent Leadership record. It only holds the *borrowed* aura record. When the aura later goes
> away, the aura garbage-collector deletes that record **and clears the ability bit** — so the unit
> loses the Leadership it legitimately earned, permanently, and separating it does not bring it back.

Two independent defects combine:

- **Defect A — the grant is masked.** `TAbilityOwner.UpdateDefaultAbilities` compares *effective*
  ability levels (own ∪ borrowed) instead of *inherent* levels, so an active aura makes the recipient
  look like it already has Leadership, and the real grant is skipped.
- **Defect B — the cleanup can't tell the difference.** `TLeadershipAbility.ResetExternalSource`
  uses "own level == 0" as its test for "this record is aura-borrowed, delete it." A masked unit's
  record is own-level 0, so it is deleted along with the ability bit.

Neither defect is harmful alone. A masks the grant; B then destroys the only remaining evidence.

---

## 2. The two stores, and how they disagree

Per-owner ability state is split across **two independent stores**:

| Store | Accessor | Notes |
|---|---|---|
| enabled **bitset** | `TAbstractUnit.GetAbilitySet` @ `0x5577F618` (VMT `+0x14c`), `GetAbSet` (VMT `+0x4c`) | plain `bt` on a bit array |
| ability-**data record** list | `TAbilityOwner.GetAbilityData` @ `0x5574F1C4` | head `owner+0x10`, next `data+0x8` |

`TLeadershipAbilityData`: `+0x0c` own/inherent level (byte), `+0x0e` id (word), `+0x10` borrowed
level (byte), `+0x14` source name (Delphi string).

The two can disagree, and the level accessors read only the **record**:

- `TAbstractUnit.GetAbilityLevel` @ `0x5577F658` (VMT `+0x144`) → `ability.GetLevel` — **never touches
  the bitset**. No record ⇒ level 0.
- `TLeadershipAbility.GetLevel` @ `0x557661C4` → `max(data[+0x0c], data[+0x10])`; returns 0 when no
  record (`xor eax,eax` @ `0x557661F2`).
- `TAbstractUnit.GetAbilityEnabled` @ `0x5577F5E0` (VMT `+0x148`) → bitset **and** `ability.GetEnabled`.

So **"has the bit" and "has a level" are different questions**, and a bare bit reads as level 0.

The engine's own marker for "this is genuinely mine" is `TLeadershipAbility.GetInherent`
@ `0x55766384` — literally `data && data[+0x0c] != 0`. An inherent grant that never got a record is
therefore indistinguishable from an aura loan.

---

## 3. The aura recompute — `TArmy.UpdateFormation` @ `0x5578D034`

Called **only** from `TArmy.Update` @ `0x5578D1F9` (any stack change) and `TCombatUnit.SetParty`
@ `0x557250D6` (combat start). It is the sole caller of both external-source functions
(verified by xref).

**Pass 1** — reset, then find the army maximum (`0x5578D069`–`0x5578D122`):

```
gate: if !GetAbilityEnabled(u,0x2e) && GetAbilityLevel(u,0x2e) <= 0 -> next   ; 0x5578D083/0x5578D098
      lead.ResetExternalSource(u)                                             ; 0x5578D0B9
      lvl = GetAbilityLevel(u,0x2e)          ; re-read AFTER the reset
      if lvl > runningMax: runningMax = lvl; capture source name
```

**Pass 2** — propagate the maximum (`0x5578D12E`–`0x5578D184`), **only if `runningMax > 0`**:

```
for every unit u in the army (no gate — all units):
    if GetAbilityLevel(u,0x2e) < runningMax:
        lead.SetExternalSource(u, runningMax, srcName)                        ; 0x5578D17B
```

`SetExternalSource` @ `0x55766224`: when the owner has **no** record it calls `SetAb(...,1)`
(@`0x55766261`, sets the **bit**) and creates a record with **`[+0x0c] = 0`** (@`0x5576627E`), then
writes `[+0x10] = level` and the source name.

`ResetExternalSource` @ `0x557662E4`:

```
data = GetAbilityData(owner,0x2e); if !data: return
if data[+0x0c] != 0:  LStrClr(data+0x14); data[+0x10] = 0        ; benign - keeps inherent
else:                 SetAb(owner,0x2e,0); RemoveAbilityData()   ; DESTRUCTIVE - bit + record gone
```

Normal churn: every non-leader in the stack gets a bit+record in Pass 2 and has it destroyed in the
next Pass 1, then immediately recreated in that same Pass 2. Self-consistent — **for units that never
had inherent Leadership.**

---

## 4. Defect A — the masked grant (`UpdateDefaultAbilities` @ `0x5574F518`)

This is the medal / chassis grant. Structure:

```
for each ability id:
    if !template.GetAbSet(id): continue
    if unit.GetAbSet(id):                                   ; unit already has the BIT
        if template.GetAbLevel(id) <= unit.GetAbLevel(id):  ; 0x5574F563 cmp / jle 0x5574F5A2
            continue                                        ; <-- GRANT SKIPPED
    data = template.GetAbilityData(id)
    if data: unit.RemoveAbilityDataID(id); AddAbilityData(TEObject.Copy(data))   ; CONDITIONAL
    unit.SetAbilityEnabled(id, 1)                           ; 0x5574F597 - UNCONDITIONAL
```

The level comparison uses VMT `+0x84` = `TAbilityOwner.GetAbLevel` @ `0x5574FD44`, which calls the
ability's `GetLevel` (VMT `+0x70`) — i.e. **`max(own, borrowed)`, the effective level.**

The inherent-only getter `TMultiLevelAbility.GetInherentLevel` @ `0x55765200` (returns just
`data[+0x0c]`) **exists and is not used here.** That is the bug: the comparison should be
inherent-vs-inherent.

Consequence, for a unit standing in a level-1 hero aura at the moment it earns a Leadership medal:

| Term | Value | Why |
|---|---|---|
| `unit.GetAbSet(0x2e)` | **true** | `SetExternalSource` set the bit in Pass 2 |
| `unit.GetAbLevel(0x2e)` | **1** | `max(own 0, borrowed 1)` |
| `template.GetAbLevel(0x2e)` | 1 | rank template's own record |
| `1 <= 1` | → **skip** | the inherent record is never copied |

The unit now shows Leadership on its card (bit set) but holds only the aura record (own = 0).

Note the second half of the same function is the mirror-image hazard: the data copy is conditional
(`je 0x5574F597`) while `SetAbilityEnabled(id,1)` is unconditional — so a template that grants
Leadership *without* a record produces a bare bit, i.e. level 0. See §7.

---

## 5. Defect B — the destruction, and why it is permanent

Once the masked unit leaves the aura (or the leader dies / the stack is recomputed with
`runningMax` back to 0):

1. Pass 1 gate passes (the bit is set).
2. `ResetExternalSource` finds the record with `[+0x0c] == 0` → takes the destructive branch →
   `SetAb(0x2e, 0)` **clears the bit** and `RemoveAbilityData` **frees the record**.
3. Pass 2 does not run (`runningMax == 0`), so nothing is recreated.

The unit now has neither bit nor record. **Nothing restores it**, because the re-grant paths are all
one-shot (xrefs to `0x5574F518`):

| Caller | When | Restores the loss? |
|---|---|---|
| `TUnit.SetExperience` @ `0x557828FA` | **only on rank change** (`GetRank` before ≠ after, `0x557828DE`) | **No** at gold/max rank — there is no further rank-up |
| `TUnit.NewDay` @ `0x55782CDB` | **day 1 only** — gated `cmp dword [AoWHSMap+0x174], 1; jne` @ `0x55782CA9` | **No** |
| `TUnit.SetUnitResource` @ `0x55782C27` | unit type change | rare |
| `THeroUpgradeTE.Execute` @ `0x557854E0` | hero level-up | see §6 |
| `THero.Loaded` @ `0x557879AB` | hero load | heroes only |

`TUnit.NewDay` is worth reading carefully — it *does* do a full rebuild (`SetAbCount(0)` then
re-apply every rank template 0..rank), which would have healed this, but the day-counter gate at
`0x55782CA9` restricts it to day 1. It is an initialisation/migration path, not a daily repair.

**This is why gold medal is the classic case:** at the terminal rank there is no future rank-up, so
the one path that would re-grant Leadership never fires again.

---

## 6. Heroes are vulnerable to the same thing

`THero` overrides the ability accessors, but **not in a way that protects it**:

- `THero.GetAbSet` @ `0x55788104` → `TCustomAbilityList.GetAbSet` — the hero's **own** bitset.
- VMT `+0x84` → the inherited `TAbilityOwner.GetAbLevel` — the hero's **own** record, effective level.

Both are exactly the terms `UpdateDefaultAbilities` compares, and `SetExternalSource` sets the hero's
own bit. So a hero that gains Leadership from a chassis/level-up grant **while inside another
leader's aura** is masked identically, then stripped identically. This matches the "maybe it happens
to heroes too" half of the report.

(The item union lives in a *different* slot — `THero.GetAbilitySet` @ `0x557882AC`, VMT `+0x14c`,
which ORs hero ∪ `THeroItems` ∪ `THeroInventory`. It is not consulted by `UpdateDefaultAbilities`.)

---

## 7. Separate defect found in passing — Crown of Kings

A data sweep of `Release\` (property-table parse + byte-pattern scan, two methods agreeing) found
bit/record correlation is **perfect** in every unit and hero template file:

| File | Leadership bit | Leadership record | bare bit | levels |
|---|---|---|---|---|
| `Unitres.pfs` | 12 | 12 | 0 | all 1 |
| `HERORES.PFS` | 14 | 14 | 0 | all 1 |
| `HEROES.PFS` | 6 | 6 | 0 | all 1 |
| `ITEMS.PFS` | 1 | **0** | **1** | — |

The single bare-bit Leadership grant in the shipped data is at `ITEMS.PFS 0x54B`, in the item-name
run containing **Crown of Kings**.

Because `GetLevel` returns 0 with no record, the Crown's Leadership reads as **level 0**: it confers
no attack/defence bonus (`GetAttack` @ `0x557661FC` indexes `byte[0x558E83E7 + 0]` = `0`) and never
raises `runningMax`, so it projects **no aura**. This is a *different* bug from §1 — not "becomes
disabled" but "never worked" — and it is a **data** defect, fixable in `ITEMS.PFS` by giving the
grant a level-1 record rather than by patching code.

Caveat: the structural parser was deliberately conservative and under-counts owners in `HEROES.PFS`
(6 parsed vs 12 found by pattern scan). That can only hide bare-bit hits, not invent them, so the
"zero bare bits in templates" claim carries a small residual risk for `HEROES.PFS` specifically.

---

## 8. Why it looks intermittent

The trigger is **where the unit was standing at the instant it earned the ability**, which the player
has no reason to connect to the loss:

- Ranks up **alone / with no other leader** → `runningMax` is 0, no aura record exists, the grant
  applies normally with own-level 1 → permanently safe thereafter.
- Ranks up **inside a leader's aura** → masked → lost as soon as it leaves.

The loss also does not surface at the moment of masking — the card still shows Leadership (the bit is
set) for as long as the unit stays in the aura. It only visibly disappears later, on separation,
which is why it reads as "being stacked with the hero broke it."

---

## 9. The fix — implemented

**Option 1 below was implemented** (`build_leadership_fix.py`; see `Leadership_FourLevels_And_Fix.md`
§4 for the as-built detail and §6 for the test plan).

1. **Compare inherent levels in the grant — CHOSEN.** In `UpdateDefaultAbilities`, both VMT `+0x84`
   (`GetAbLevel`) call sites at `0x5574F54D` / `0x5574F55B` now route through a cave that dispatches
   ability VMT `+0x94` → `TMultiLevelAbility.GetInherentLevel` @ `0x55765200`, so a borrowed aura no
   longer masks a real grant. The "affects every multi-level ability" risk turned out to be a non-issue:
   base `TAbility.GetLevel` @ `0x5574E9B0` and `GetInherentLevel` @ `0x5574E954` **both return 0**, so
   plain abilities compare 0 vs 0 either way, and leveled ones strictly improve.

Alternatives, kept in case the fix needs revisiting:

2. **Force the record copy when the unit's record is aura-only.** Let the `unit.GetAbSet` early-out
   still skip, but proceed with the copy when the template has a record and the unit's is `own == 0`.
   Equivalent effect, marginally tighter blast radius; rejected as more fiddly for no real gain once
   option 1's blast radius was shown to be nil.
3. **Stop `ResetExternalSource` clearing the bit — do NOT re-try as the primary fix.** By the time the
   GC runs, Defect A has already discarded the inherent record, so there is no surviving marker to
   test; this can only limit future damage, never repair the case.
4. **Data-only mitigation.** Not available for the masking (it is code). Still open for §7 (Crown of
   Kings): add the missing level-1 record in `ITEMS.PFS`.

---

## 10. Address quick-reference

| Symbol | VA | Role |
|---|---|---|
| `TArmy.UpdateFormation` | `0x5578D034` | two-pass aura recompute; sole caller of Set/ResetExternalSource |
| `TArmy.Update` / `TCombatUnit.SetParty` | `0x5578D1F9` / `0x557250D6` | the two triggers |
| `TLeadershipAbility.SetExternalSource` | `0x55766224` | creates record with **own = 0** + sets bit |
| `TLeadershipAbility.ResetExternalSource` | `0x557662E4` | **destructive when own == 0** |
| `TLeadershipAbility.GetLevel` | `0x557661C4` | `max(own, borrowed)`; 0 if no record |
| `TLeadershipAbility.GetInherent` | `0x55766384` | `data && data[+0x0c] != 0` |
| `TMultiLevelAbility.GetInherentLevel` | `0x55765200` | own level only — **exists, unused by the grant** |
| `TAbilityOwner.UpdateDefaultAbilities` | `0x5574F518` | **Defect A**; level cmp @ `0x5574F563` |
| `TAbilityOwner.GetAbLevel` | `0x5574FD44` | VMT `+0x84`; effective level (the wrong term) |
| `TAbstractUnit.GetAbilityLevel` / `GetAbilityEnabled` / `GetAbilitySet` | `0x5577F658` / `0x5577F5E0` / `0x5577F618` | VMT `+0x144` / `+0x148` / `+0x14c` |
| `TUnit.SetExperience` | `0x557828B4` | rank-change grant (`UpdateDefaultAbilities` @ `0x557828FA`) |
| `TUnit.NewDay` | `0x55782C98` | full rebuild, **day-1 gated** @ `0x55782CA9` |
| `THero.GetAbilitySet` / `GetAbilityLevel` / `GetAbSet` | `0x557882AC` / `0x5578831C` / `0x55788104` | item union is `+0x14c` only |
| leadership atk/def tables | `0x558E83E7` / `0x558E83EB` | `[0,+2,+2,+2]` / `[_,+1,+1,+1]` |

## Why "never strip an ability from the ruleset" is a hard rule (mechanism, 2026-08-28)

The project avoids removing an ability from the ruleset once units carry it. That policy dates to a
map-breaking bug years ago; here is the machine code behind it, byte-verified **identical to
pristine**, i.e. vanilla and untouched by any Ziggurat script.

`TArmy.UpdateFormation @0x5578D034` is the engine's **sole** aura recomputer — it runs on every move
and every turn, and `build_leadership_aura.py` also calls it directly so a purchased level applies
at once. Per unit in the army:

```
5578D07C  mov edx,0x2E / call [unit.vmt+0x148]   ; Leadership enabled? (item-aware)
5578D08F  mov edx,0x2E / call [unit.vmt+0x144]   ; ...or level > 0?      (item-aware)
5578D0A2  call TAbilityControl.GetAbility(0x2E)  ; ⚠ NIL if the id is unregistered
5578D0B7  mov edx,ebx / call TLeadershipAbility.ResetExternalSource   ; ⚠ EAX = that, no nil check
5578D0DE  mov edx,0x2E / call [unit.vmt+0x154]   ; GetAbilityOwner -- the ATTRIBUTION step
5578D0E7  mov ecx,[eax]                          ; ⚠⚠ dereferenced with NO nil check
```

**Two unguarded dereferences on one path.** The first is the ruleset-removal case: `GetAbility`
returns nil silently for an unregistered id (it asserts only on a *negative* id — see
`ID_Ceilings.md`), and `ResetExternalSource` takes it as `Self`. The second is the attribution case:
the unit has already passed the enabled-or-level gate, so the code assumes an owner exists and derefs
whatever `GetAbilityOwner` returns.

⭐ **The aura is DERIVED, not persisted.** `UpdateFormation` re-queries the live registry every time,
so there is no stored aura value in a save that could be orphaned. That is what makes the policy
sufficient: keep `0x2E` registered and every instance re-resolves cleanly, whatever its level.

**Status: not a live concern** (author's ruling 2026-08-28) — the never-strip policy closes it, and
no Ziggurat feature removes an ability from the ruleset. Recorded so the policy is not mistaken for
superstition, and so the two missing nil checks are known if that ever changes.
