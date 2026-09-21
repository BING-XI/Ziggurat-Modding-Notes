# Getting in-combat SPELL CASTS into the combat log

**Status 2026-07-25: replay-side spell recording (§2) CONFIRMED WORKING in-game** (user tested an
Event-History replay; spell lines appear). `build_replaylog.py`, backup `AoWEPACK.dpl.pre-replayspell`.
The live-log spell labelling remains applied-untested.

### ⛔ No stats tail on replay lines — DECIDED 2026-07-25, do not revisit without new information

Replay lines are `Valkyrie casts Fire Bolt on Shadow for 5 damage`, with **no `(N%, A ATK vs D DEF)`
tail, ever** — and this is now a **closed decision**, not an outstanding gap. The reasoning, so a future
session doesn't re-derive it and "helpfully" add one:

* **The attack value does not survive the battle.** It is a transient stack argument to
  `Generate`/`GenerateEx`, is never written into the CA, and `TDamageCA.ReadWrite` does not persist it.
  At replay the CA holds only ids, rolled damage and the effect word.
* **The defending stat read at replay is the battle-START snapshot.** The replay rebuilds objects from
  the logbook roster, so `GetDefense`/`GetResistance` return pre-battle values. **A Curse, Bless or any
  other stat-affecting effect landing mid-battle makes both the stat AND the derived hit% wrong** — and
  wrong in the worst way, since the numbers are right often enough to be trusted (user's observation,
  2026-07-25).
* **A spell-only partial tail was considered and rejected.** Spell ATK *is* recoverable exactly
  (static `TSpell+0x34`, reached via the gated `CA+0x18` → `GetSpell` path §3), so
  `(N%, 10 ATK vs 4 RES)` could be printed with only the RES side being the snapshot — but that inherits
  the same silent-wrongness under debuffs, and it would need the cave relocated first (only 24 B of the
  zone remain, see §2). An ATK-only annotation was also weighed: always truthful, but it just restates a
  static spell property, so it does not earn the work.
* **This costs nothing that matters:** the LIVE tactical log prints the full tail with true
  at-the-moment values, which is where combat-math verification should happen anyway.

| | live tactical battle | replay from Event History |
|---|---|---|
| script | `build_combatlog_dll.py` | `build_replaylog.py` |
| hooks | `TDamageCA.Generate`/`GenerateEx` epilogues | `TDamageCA.Play` @`0x55729D97` **+ `TCombatSpellCA.Play` @`0x557F6A72`** |
| line ends in | `  (60%, atk 6 vs def 3)` | nothing (no stats tail) |
| spell labelling | **applied, UNTESTED** | **CONFIRMED WORKING 2026-07-25** |

(Replay logging only streams while **Play** runs — the slider/step buttons use the silent Execute path.)

Telling them apart matters: a line with no `(…%, atk … vs …)` tail came from the REPLAY log. A whole
round of this investigation was spent extending the wrong one because I didn't check that first.

---

## 1. THE BUG — `TCombatSpellCA` overrides `Play` and never calls base

`TDamageCA.Play` is VMT slot **`+0x54`**.

| class | VMT | `+0x54` |
|---|---|---|
| `TDamageCA` | `0x557162F4` | `0x55729D78` (base) |
| **`TCombatSpellCA`** | `0x557F3CC8` | **`0x557F6A6C` — override, does NOT call base** |
| `TTurnUndeadCA` | `0x5571FD18` | `0x5576ACE8` (calls base) |

`build_replaylog.py` hooks `0x55729D97`, which is *inside* `TDamageCA.Play`. Spells never enter it,
so the replay log emits nothing for them — labelling downstream could never have helped.

**The invalidated claim, now corrected at source in that script's docstring:** *"The three Play
overrides (TStrikeCA, TTurnUndeadCA, TRangedAttackCA) all call base, so this one hook covers every
damage action."* The survey found three overrides and missed the fourth, which is also the only one
that doesn't chain to base. **When a hook's coverage rests on "all overrides call base", enumerate the
VMT slot across every descendant rather than spot-checking the ones you happen to know about.**

## 2. THE FIX — CONFIRMED WORKING 2026-07-25

Hook the override's once-per-action branch:

```
557F6A6C  push ebx / push esi
557F6A6E  mov ebx, edx            ; EBX = TCombatViewer
557F6A70  mov esi, eax            ; ESI = the CA
557F6A72  cmp dword ptr [ebx+0x14], 0   ; 83 7B 14 00   <-- HOOK2 (6 B: cmp + jne, reloc-free)
557F6A76  jne 0x557F6A97          ; 75 1F  -> the trigger tick runs the block below EXACTLY ONCE
557F6A78  mov eax, [0x558E92E8]   ; A1 E8 92 8E 55 = the spell's own sound-play (GetSpell etc.)
```

* ⚠ **The design's original site `0x557F6A78` was UNUSABLE: it has a `.reloc` HIGHLOW entry at
  `0x557F6A79`** (the `A1` imm32 — verified by parsing the .reloc section). The loader's rebase fixup
  would have added the delta to a `jmp rel32` written there. General rule: in the DPLs, a hook may only
  displace **reloc-free** bytes; scan the .reloc section for the exact range before choosing a site.
* As built: hook 6 bytes @`0x557F6A72` (`83 7B 14 00 75 1F` → `E9 rel32 + 90`); the cave replicates
  the displaced trigger-tick test itself — `[ebx+0x14]==0` → log + `jmp 0x557F6A78`, else
  `jmp 0x557F6A97`. All jumps rel32 within the module ⇒ PIC. Module-wide branch scan confirmed nothing
  targets `0x557F6A72..77`.
* Register convention is identical to the existing hook (`ESI` = CA, `EBX` = viewer,
  `[[EBX+8]+0xC]` = TCombatData for `FindID`), and `TCombatSpellCA` uses the **same field layout**
  (`+0x0D` attacker id, `+0x0E` target id, `+0x10` rolled damage, `+0x13` effect word).
* Cave restructured into a **callable worker + two entry stubs** (`_entry1` at `0x5580F180` keeps the
  original hook byte-identical; `_entry2` at `0x5580F18F`; worker at `0x5580F1A4`, ends `ret`).
  Total 1128 B of the 1152 B zone. `TTurnUndeadSpellCA` inherits the override (VMT+0x54 verified) —
  covered by the same hook. TDamageCA's own Play is untouched ⇒ no double logging.

## 3. Reference — the spell path (all verified by disassembly)

```
TIceShards VMT 0x557F5874  ─┐
TFireBall  VMT 0x557F5658  ─┤ all inherit CreateCA (spell VMT+0x78) = TCombatSpell.CreateCA
TCombatSpell VMT 0x557F3FA4─┘                                          @0x557F72C0
        ↓
  mov eax,[0x557F3C88]      ; TCombatSpellCA classref cell -> 0x557F3CC8
  call 0x557298B4           ; construct
  mov eax,[ebx+0x10] ; mov [esi+0x18],eax     ; CA+0x18 := spell ID
  push [ebx+0x34] (attack) / [ebx+0x35] (damage) / word[ebx+0x36] (dmg types) / [ebx+0x3C]
  call [CAvmt+0x6C]         ; = TDamageCA.GenerateEx (NOT overridden) -> the live-log hook fires
```

* `TCombatSpellCA` chain: `TCombatSpellCA → TDamageCA → TSingleTargetCA → TCombatAction`.
  Instance size **32**, so `+0x18` (spell id) and `+0x1C` (mana) are in bounds.
* `TDamageCA.GenerateEx` @`0x55729C98` is **straight-line, single epilogue** at `0x55729D08` — no
  early return can bypass the live-combat hook.
* **Spell name = `TSpell+0x08`**, a plain LStr VALUE (no VMT call).
* `TSpellControl.GetSpell` @`0x55779AC8` (`eax`=ctrl, `edx`=id) → `TSpell`, 0 if `id >= count`.
  ⚠ **RAISES a Delphi range error on a NEGATIVE id** — always sign-check first.
* Route to the control: `[AoWHSSet 0x558FA044]` → `+0x84`. (Vanilla's override uses a different
  route, `[[0x558E92E8]]` → `+0x84`; both land on the same object.)

### The type-gate trap, again
`CA+0x18` is the spell id **only** on `TCombatSpellCA`. `TStrikeCA` reuses that offset for strike
flags, so an ungated read yields a garbage id and `GetSpell` then raises **inside the combat pump**.
Same family as the `combatObj+0x4C` wall bug (`Blt_Error_Wall_Damage.md`). Both loggers therefore gate
on `IsClass(CA, TCombatSpellCA)` **before** touching `+0x18`, and every subsequent step (sign check,
HSSet nil, control nil, GetSpell nil, name nil) falls back to the plain melee verb rather than risk an
exception. `TTurnUndeadSpellCA` descends from `TCombatSpellCA` so it is covered free; the Turn Undead
*ability* CA (`TTurnUndeadCA`) does not descend from it and is correctly excluded.

## 4. What is applied right now

Both loggers emit `<caster> casts <Spell> on <target> for N damage`, and
`<caster> casts <Spell> but misses <target>` (a separate connector — reusing `" on "` would have made
a miss read like a hit). Wall naming (`"Wall"` instead of `"?"`) is in both too.

* `build_combatlog_dll.py` — worker 916→1169 B, total 3022 B @ `0x55811000`. Spell slot `[ebp-0x2C]`,
  zero-initialised in the prologue and cleared by its **own** 1-element `@LStrArrayClr` (it is not
  adjacent to the 4-LStr block — `-0x20` is the raw d20, and clearing an int as a string would crash).
* `build_replaylog.py` — cave now 1128 B of the 1152 B ceiling (two entry stubs + callable worker,
  see §2). Same slot discipline at `[ebp-0x28]`. Spell labelling live via `_entry2` and **CONFIRMED
  WORKING in-game 2026-07-25**. ⚠ Only 24 B of slack left: anything further here needs a cave move.

## 5. Still open

* **Verify the live combat log in a tactical battle** (needs a full game restart — the DLL is mapped
  at process start). The funnel is confirmed reached, so it should label spells. If it does not, the
  prime suspect is the **fast-combat gate** in the worker, which bails when either combatant is a
  `TFastCombatUnit`; it was added on a theory that turned out to be wrong, fixed nothing, and has never
  been verified not to misfire. Recommended: revert it regardless.
* **Non-damaging spells produce nothing anywhere** — they never touch the damage funnel. They hang
  directly off `TCombatAction`: `TExclusiveCombatSpellCA` `0x557F3DB8`, `TMultiTargetCombatSpellCA`
  `0x557F3EAC`, `TSlowCA` `0x557F4D2C`, `TMindDecayCA` `0x557F4908`, `TEntangleSpellCA` `0x557F4F08`,
  `TAnimateDeadCA` `0x557F6828`, `TRecallSpiritCA` `0x557F662C`, `TTacticalCombatHighPrayerCA`
  `0x557F44D0`, `TFastCombatTerrorCA` `0x557F5FF4`.
  ⚠ Their field offsets **differ from each other** — `TExclusiveCombatSpellCA` has mana at `+0x10` and
  spell id at `+0x18`; `TMultiTargetCombatSpellCA` has mana at `+0x14` and spell id at `+0x1C`. One
  generic reader across both would silently read the wrong field.
  Candidate single hook covering every tactical cast (damaging or not):
  **`AoWE.TSpell.CombatSpellCast @0x5577954C`** — `EAX`=TSpell, `EDX`=caster combat object; zero
  in-module callers (only `AoWTCPCK@0x0040B44D`), so it fires exactly once per tactical cast and never
  in fast combat. **Verified safe to hook: reloc-free, nothing branches inside, but it needs SIX bytes
  displaced, not five** — the 5-byte boundary cuts `mov ebx,eax` in half; use `jmp rel32` + 1 `nop`
  and continue at `0x55779552`. It carries no target and no damage.
