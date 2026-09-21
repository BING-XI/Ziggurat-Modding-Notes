# Terror — one cast per combat (AI anti-spam)

**Status: APPLIED 2026-08-31 (v2, per-side), UNTESTED IN GAME.** Not confirmed — the user's in-game test decides.
**Script:** `build_scripts/build_terror_oncepercombat.py` — dry-run default, `--apply`, `--dis`,
surgical `--undo`. **Binary:** `AoWEPACK.dpl` only (no exe half, so no AoW.exe/AoWCompat lockstep).
**Backup:** `AoWEPACK.dpl.pre-terroronce` — *do not use it to revert*, use `--undo`.

**One-line:** the AI re-casts Terror every combat turn it can afford; Terror does not stack usefully,
so every re-cast is a wasted casting action. Cap it at one per battle **per side**, in both combat modes.

**Prior art:** third-party, tactical arm only —
`Modding Resources/Inioch/share1/Inioch_AI_Combat_Spell_Architecture.md` and
`Zig notes/AI Combat-Spell Anti-Spam.md`. Both describe a build confirmed working in *his* binary.
**None of his addresses were reused** — see "What was NOT copied" below; three of them would have
collided with live Ziggurat features.

---

## 1. The two combat contexts (the reusable finding)

AoW1 scores and casts combat spells through two completely separate paths, with **different value
methods, different cast points, and different driver semantics**. A hook that works in one does not
fire in the other. This split is the whole difficulty of any AI combat-spell mod.

| | value path | cast point | "drop this candidate" rule |
|---|---|---|---|
| **Tactical** (player watches) | VMT **+0x88** `CombatSpells.TTerror.tcGetDamageValueEx` @`0x557F9D44` | `CombatSpells.TTacticalCombatTerrorCA.Execute` @`0x557F990C` | driver picks the single **highest-priority** action ⇒ **shrinking the value is enough** |
| **Fast / auto-resolve** | `CombatSpells.TTerror.fcPrefetchCombatCommands` @`0x557F9B20` | `CombatSpells.TTerror.fcExecuteCombatCommand` @`0x557F9BE8` (VMT +0x94) | a queued command is dropped **only at value exactly 0**; any value ≥ 1 stays queued and still wins when the AI has nothing better |

Terror is one of the few combat spells with a **dedicated CA in both modes**
(`TTacticalCombatTerrorCA` / `TFastCombatTerrorCA`), which is why it needs no
`TSpell.CombatCastingDone` + VMT-identity machinery. Spells that inherit the generic
`TCombatSpellCA` / `TExclusiveCombatSpellCA` / `TMultiTargetCombatSpellCA` do — that is the hard
case (Ooze, Slow), documented in the two prior-art files.

### ⚠ `TTerror.fcGetDamageValueEx` is DEAD CODE — do not gate VMT +0x98

The prior-art table lists Terror's fast-combat value slot as "—", which reads as "Terror has no
+0x98 override". That is not true, and the truth matters more:

- Terror **does** override VMT **+0x98** → `CombatSpells.TTerror.fcGetDamageValueEx` @`0x557F9C2C`,
  slot at `0x557F626C`, and the slot carries a `.reloc` entry. It looks like a perfect gate.
- It is **never called**. `TTerror.fcPrefetchCombatCommands` accumulates the value **inline** into
  `EBP` (`call [edx+0x58]` per candidate unit, `add ebp,eax`), tests `ebp` itself at `0x557F9BA8`,
  and writes it straight into the command at `[cmd+0x10]`.
- Verified module-wide: `fcGetDamageValueEx` @`0x557F9C2C` has **0 direct rel32 refs** and exactly
  **1 absolute dword ref** — its own VMT slot.

**A wrapper on +0x98 would assemble, verify, disassemble correctly, byte-check clean, and do
nothing.** This is the generalisable trap: *a spell overriding a value method is not evidence that
the value method is on the path.* Check the caller before gating a virtual — an override can be
vestigial.

### ⚠ Terror's VMT base is `0x557F61D4`, not `0x557F61D8`

Slot arithmetic from the wrong base silently renames every slot by one. The DLL's own export table
settles it — `CombatSpells..TTerror` (double dot = the VMT) is at `0x557F61D4`, so `0x557F625C` is
**+0x88** (`tcGetDamageValueEx`), not +0x84. Confirmed by every neighbouring slot resolving to its
documented name (`+0x78` = `CreateCA`, `+0x90` = `fcPrefetchCombatCommands`, `+0x94` =
`fcExecuteCombatCommand`, `+0x98` = `fcGetDamageValueEx`).

**Never derive a VMT base by subtracting an assumed slot offset.** `re_tools/aowsyms.py` reads the
10,036-name export table; the `..Class` symbol *is* the VMT base.

---

## 2. The implementation - a per-side flag, two writers, two gates

`F_SIDE = 0x558FAC00`, **four** bytes, indexed by combat side.

| # | site | vanilla bytes | what the cave does |
|---|---|---|---|
| 1 | `AoWE.TCombat.Create` @`0x5572708C` | `55 8B EC 51 53` | `F_SIDE[0..3] = 0` (one dword store; fires once per battle, not per turn) |
| 2 | `TTacticalCombatTerrorCA.Execute`**+0x12** @`0x557F991E` | `8B 46 0C E8 42 F3 F2 FF` (**8**) | `F_SIDE[side(target)] = 1` |
| 3 | `TTerror.fcExecuteCombatCommand` @`0x557F9BE8` | `53 56 57 8B F2` | `F_SIDE[side(actor)] = 1` |
| 4 | VMT **+0x88** slot `0x557F625C` (`->0x557F9D44`) | dword | -> `C_WRAPTC`: call the original, then if `F_SIDE[side(target)]` `value = max(1, value>>6)`, `value100 = value/100` |
| 5 | `TTerror.fcPrefetchCombatCommands` @`0x557F9B20` | `53 56 57 55 83 C4 F8` (**7**) | -> `C_FCPRE`: if `F_SIDE[side(actor)]`, `ret` immediately - no Terror command is ever queued |

**Caves** `0x5582A000`-`0x5582A16D` (`C_RESET` `0x5582A000`, `C_SETTAC` `0x5582A040`, `C_SETFC`
`0x5582A080`, `C_FCPRE` `0x5582A0C0`, `C_WRAPTC` `0x5582A120`). All position-independent:
`call $+5 / pop / sub` delta for the flag array, rel32 for every call and jump.

### The side index - `GetOpponentSide` is the whole story

There is **no `GetSide`**. `AoWE.TCombatObject.GetOpponentSide` @`0x55726688` is the accessor, and
reading it settles the data model:

```
bl = [obj+0x45]                       ; the object's player slot
if bl == 0xFF: return 2               ; object with no owning player
return [GetPlayers([[[obj+8]+0xC]+0x38], bl) + 0xA] XOR 1
```

A combat side is **`[player+0x0A]`**, and sides are exactly **{0,1}** - the `XOR 1` proves it. `2` is
the no-owner escape.

⚠ **It returns in `AL` only.** On the escape path the upper 24 bits of EAX are still the
incoming object pointer, so every site does `movzx eax, al` before masking. Masking to `0..3` against
a 4-byte array means the escape value (2, or 3 after the XOR) can never write out of bounds.

⚠ **It preserves EBX/ESI/EDI/EBP** (it push/pops EBX and ESI) and **clobbers EAX/ECX/EDX**.
Every cave is built around that - it is why `C_SETTAC` can call it with the CA in EBX and the combat
data in ESI still live for the resumed code.

Each site derives the **casting** side from whichever object it actually has:

| site | object in hand | index |
|---|---|---|
| `tcGetDamageValueEx` wrapper | `ECX` = target | `GetOpponentSide(target)` |
| `TacticalCombatTerrorCA.Execute` | `FindID(combatData, [CA+0x0D])` = target | `GetOpponentSide(target)` |
| `fcPrefetchCombatCommands` | `[EDX+4]` = actor | `GetOpponentSide(actor) ^ 1` |
| `fcExecuteCombatCommand` | `EDX` = actor | `GetOpponentSide(actor) ^ 1` |

The two tactical sites share the target-derived expression and the two fast sites share the
actor-derived one, so **each mode is self-consistent - which is all that is required**: a battle is
either watched or auto-resolved, never both, and the flags reset at `TCombat.Create`.

Target-derived is used tactically because `tcGetDamageValueEx` only ever receives the target - the
caster is not reachable from it, and the spell object is a shared flyweight that does not know its
caster. `GetOpponentSide(target)` *is* the caster's side index, so no caster object is needed.

### Why the tactical set moved off the function entry

`TTacticalCombatTerrorCA.Execute`'s prologue has no side information at all - `EAX` = the CA,
`EDX` = the combat data. The hook therefore sits **+0x12 into the function**, displacing the pair
that already resolves the target:

```
557F9919  xor edx,edx                 <- stays: edx = the target id
557F991B  mov dl,[ebx+0x0D]           <- stays
557F991E  mov eax,[esi+0x0C]          <- DISPLACED: the combat data
557F9921  call TCombatData.FindID     <- DISPLACED: -> eax = the target object
557F9926  mov edi,eax                 <- resume here
```

So the cave gets the target object for free, and the flag is set **only when Terror actually lands**
(the whole block is inside vanilla's `if ([CA+0x14] != 0)` guard) rather than on every invocation.

⚠ **This displaced run contains a `call rel32`, so it is RE-ASSEMBLED in the cave, not
copied.** A verbatim copy would carry the original site's displacement and call into the middle of
nowhere. The other three runs are register-only and *are* copied verbatim, which is what keeps the
keystone imm8 encoding traps out of reach. `.reloc` coverage was checked on all four runs before
displacing: none.

### Does this apply to a HUMAN player's side? Tactical no, auto-resolve yes

**Manual tactical combat: the player is untouched.** The human casts through the UI, never through
`tcGetDamageValueEx` (the AI scorer), so the gate cannot reach them. `TTacticalCombatTerrorCA.Execute`
does set `F_SIDE[human side]` when the human casts, but nothing on the human's side is ever AI-scored
in a manual battle, so that flag has no effect on them.

**Auto-resolve: the player's side IS capped**, because auto-resolve drives *both* sides through the
same AI path. Verified chain:

```
TFastCombat.Execute @0x55744A0C
  -> TFastCombat.ExecuteCombatRound @0x5574482C          (the only caller, +0x5D)
     -> TSpellCastingAbility.fcPrefetchCombatCommands @0x5576E2BC
        -> [spell VMT +0x90] @0x5576E440 / @0x5576E48D   -> TTerror.fcPrefetchCombatCommands  <-- our gate
     -> TSpellCastingAbility.fcExecuteCombatCommand @0x5576DEC8
        -> [spell VMT +0x94] @0x5576DEE7                 -> TTerror.fcExecuteCombatCommand    <-- our set
```

Our caves index by the **acting** object's side, so they apply to whichever side is acting -- human
or AI.

**Vanilla already gates humans here, partially.** `TSpellCastingAbility.fcPrefetchCombatCommands`
opens with, at `0x5576E31A`:

```
cmp byte [player+0xA7], 0      ; 0 = LOCAL INTERACTIVE HUMAN (player-type enum; independent = 4)
jne  proceed                   ; AI / independent -> always prefetch
cmp dword [hero+0x84], 0       ; the spell the hero is currently channelling
jne  bail                      ; human AND mid-cast -> queue nothing at all
proceed:
```

(`[hero+0x84]` is written by `THero.ExecuteStartCasting @0x55789275` and cleared by
`THero.ExecuteCancelCasting @0x557893BF`, so it is the in-progress strategic cast.)

So a human's wizard **does** auto-cast combat spells when auto-resolving, unless it is mid-channel --
and wherever vanilla lets it through, our per-side cap now applies to it too.

**The asymmetry this creates:** auto-resolving a battle costs you Terror casts you would have had if
you fought it manually. That is arguably the correct reading of "one Terror per side per combat", but
it is a deliberate choice, not an accident.

*To exempt human sides from the fast arm instead:* replicate the `[player+0xA7]` lookup inside
`C_FCPRE` -- `dl = [actor+0x45]`, `TCombatPlayerList.GetPlayers([[actor+8]+0xC]+0x38, dl)`,
`edx = movsx [combatPlayer+8]`, `TPlayerList.GetPlayers([[0x558FA040]+0x140], edx)`, then
`cmp byte [player+0xA7],0` -- and skip the gate when it is 0. About 30 extra cave bytes; the global
`0x558FA040` needs the delta trick. Not done: the cap currently applies to every side equally.

### Why the two arms behave differently - and why that is correct

- **Tactical: soft.** `value = max(1, value>>6)`. Floor 1, not 0, deliberately - Terror stays
  castable when it is that side's *only* combat spell, it just loses to literally anything else.
  This works as a cap **only** because that driver picks the single highest-priority action.
- **Fast: hard.** div-64 there would not cap anything (value >= 1 stays queued), so the gate is an
  early return from the prefetch, using the function's own existing "no value => queue nothing" path.

**Fast-combat ordering is self-consistent:** prefetch (flag clear) -> command queued -> execute (sets
the flag) -> next round's prefetch returns early. The set point is *downstream* of the gate, which is
the only ordering that works.

### Why a VMT slot for #4 and an `E9` hook for the rest

`tcGetDamageValueEx` has 0 direct rel32 callers and exactly 1 absolute dword ref - its VMT slot. So
repointing the slot intercepts every call, **displaces nothing**, needs no PIC (the loader rebases
our pointer using the `.reloc` entry at RVA `0x0F625C` exactly as it rebased the old one), and undoes
with a 4-byte write. Prefer this over an `E9` hook whenever a method's only reference is its slot.

### The value struct

Both value methods fill a >=0x12-byte output struct through **stack arg 1**:
`[out+0]` = value, `[out+4]` = value/100, `[out+8]` = `[out+0xC]` = 0, `[out+0x10]` = word constant.
`tcGetDamageValueEx` is `ret 4`; `fcGetDamageValueEx` is `ret 8` (two stack args). The wrapper
recomputes `[out+4]` after shrinking `[out+0]` so the derived field stays consistent - the prior-art
wrapper did not, which is harmless only while Terror's raw value stays under 100.

Neither method returns a meaningful value in EAX (the vanilla zero-path clobbers it with
`mov ax,[const]`), so the wrapper is free to use EAX. The wrapper stashes the target in **ESI**
before calling the original, because the original clobbers ECX.

## 3. What was NOT copied from the prior art, and why

**Every address was re-picked.** Three of his would have silently destroyed live Ziggurat features:

| his address | what it is | why it is unusable here |
|---|---|---|
| `0x558FAF20/21/22` | his per-combat flags | **`build_shipyard_income.py` owns `0x558FAF20`**, plus `AF24/AF40/AF60/AF98/AFA0` |
| `0x5580DCE8` | his shared reset cave | our `0x5580DD0E`, `0x5580DD20`, `0x5580DD30` are already occupied |
| `0x5580DD14` / `0x5580DD34` | his Terror set / value caves | same block |

`F_SIDE = 0x558FAC00` is fresh — nearest claimed addresses are `0x558FAB7F` below and `0x558FAF20`
above. Caves `0x5582A000+` are clear of every AoWEPACK address any build script claims (nearest below:
`0x55828000`) and were verified all-zero in the live DLL before writing.

**BSS note:** the BSS section is VA `0x558EA000`–`0x558FA231` with **rawsize 0**. The loader maps and
zero-fills the whole final page, so `0x558FA231`–`0x558FAFFF` is committed scratch. Because rawsize is
0, **BSS bytes cannot be checked in the file** — asserting on them chases a phantom, and the build
script deliberately does not try.

---

## 4. Verification done (all without launching the game)

- All five sites byte-verified pristine before writing; `--apply` aborts on any mismatch.
- `.reloc` coverage checked on all four displaced runs - **none**, so all four are safe to displace.
- Every cave disassembled with capstone (`--dis`) - jump targets confirmed as
  `TCombat.Create+5`, `TacticalCombatTerrorCA.Execute+0x1A`, `fcExecuteCombatCommand+5`,
  `fcPrefetch+7`, plus `call TTerror.tcGetDamageValueEx`, `call TCombatData.FindID` and four
  `call TCombatObject.GetOpponentSide` - every rel32 recomputed for the cave address.
- Live read-back: each hook site reads `jmp <cave>` and resumes on the correct instruction. The
  tactical hook sits at `0x557F991E` with the target-id load (`mov dl,[ebx+0x0D]`) still ahead of it
  in the function and three `nop` bytes padding to the resume point.
- Each cave asserted to fit the gap before the next one; the whole `0x5582A000`-`0x5582A200` span is
  asserted zero-or-ours before any write.
- `--undo` round-trip is **byte-identical** to `.pre-terroronce`; re-apply is byte-identical to the
  first apply (idempotent).
- `rng_audit.py --owners`: no new RNG site - no cave draws a random number, so the SYNCED/RAW rule
  does not apply here.
- Profile-path leak scan clean on the DLL, the backup and the script; zero drive-letter paths in the
  cave span.

## 5. Needs the user's in-game test

1. **Tactical combat, AI has Terror:** it casts Terror at most once per battle. If it is that side's
   *only* combat spell it may still cast it again - that is the deliberate floor-1 behaviour, not a
   failure. Tune with `SHIFT` in the script.
2. **Auto-resolve the same fight:** Terror is cast at most once. This arm is a hard stop.
3. **Second battle in the same turn:** Terror is available again (proves `TCombat.Create` resets).
4. **The per-side test - cast Terror yourself, then watch the AI.** The AI must *still* be able to
   cast its own Terror in that same battle. This is the whole point of the per-side flag; if the AI
   goes quiet after your cast, the side index is collapsing to one slot.
5. **Both sides in one battle:** each may cast Terror once; neither gets two.
6. **Auto-resolve one of YOUR OWN battles twice.** Your side is capped there too (auto-resolve runs
   the AI for both sides) -- expect at most one Terror from your own wizard. This is the intended
   asymmetry with manual combat, where you are uncapped; confirm it reads as intended rather than as
   a bug.
7. **No regression:** other AI combat spells still get cast normally; auto-resolve outcomes are not
   obviously skewed.

## 6. Revert

```bash
python "Modding Resources/build_scripts/build_terror_oncepercombat.py" --undo
```

Restores the four hook sites and the VMT slot, zeroes the five caves, touches no backup. Verify-before-write
on every byte; aborts if anything foreign is present.
