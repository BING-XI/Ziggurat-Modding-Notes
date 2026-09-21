# HOW-TO: Make Lifesteal work on Round Attack (AoW1 / AoWEPACK.dpl)

A self-contained guide to making a lifesteal-style on-hit heal fire on **Round Attack** hits in
Age of Wonders 1, by reimplementing it the way the engine's *own* working on-hit effects (Cursed
from Death Strike, etc.) are wired. Written so another modder can reproduce it in any toolchain.

All addresses are AoWEPACK.dpl **preferred-base VAs** (image base `0x55700000`). The DLL is rebased at
runtime, so **any code cave must be position-independent** (register-relative + rel32 only; no fresh
absolute memory operands). Everything below satisfies that.

---
## 1. The combat-strike model you need to understand

A melee hit is a **`TStrikeCA`** ("strike combat action") object. Two of its methods matter:

- **`TStrikeCA.Generate` @ `0x557668B4`** — the *planning* pass. Resolves the attack (to-hit/damage) and
  **sets on-hit *effect flags*** in the strike's flag byte at **`CA+0x18`**, based on the *attacker's*
  abilities. It runs for **every** strike — normal, round attack, and retaliation.
- **`TStrikeCA.Execute` @ `0x55766738`** — the *apply* pass. Re-reads those flags and applies the
  effects (curse the target, etc.). Registers on entry to the effect section: **`EBX` = the CA**,
  **`EDI` = attacker**, **`ESI` = target** (both resolved via `FindID` from `CA+0xd`/`CA+0xe`).

Relevant CA fields:
| Field | Meaning |
|---|---|
| `CA+0x0c` bit `0x01` | **defensive** flag (set by `TSingleTargetCA.SetDefensive` @ `0x557299E4`). 0 = offensive strike, 1 = defensive/retaliation. |
| `CA+0x10` (byte) | strike **damage**; `0` means the hit did nothing. Generate only sets effect flags inside `if CA+0x10 != 0`, so effects are inherently **hit-gated**. |
| `CA+0x15` (byte) | strike **result**, written in Execute. **This is the trap** — see §2. |
| `CA+0x18` (byte) | **effect flag bits** (below). |

How the engine wires the built-in effects (this is the template to copy):
| Attacker ability | Set in | `CA+0x18` bit | Applied in Execute |
|---|---|---|---|
| **Cause Fear `0x33`** → Panicked `0x6c` | **Generate** | `0x01` | flag-block @ `0x557667CF` (gate = flag only) |
| **Entangle Strike `0x77`** → Entangled `0x5e` | **Generate** | `0x04` | flag-block @ `0x55766806` (gate = flag only) |

> **⚠ NAMING CORRECTION (2026-07-16, verified against the ability registrar).** Earlier revisions of this
> table mislabelled these two rows. The verified ids are: `0x33` = **Cause Fear** (not "stun-type"; it is
> gated on the target lacking `0x43` **Fearless**, and applies `0x6c` **Panicked**); `0x77` = **Entangle
> Strike** (NOT "Death Strike" — that is `0x12`), applying `0x5e` **Entangled** (NOT "Cursed" — Cursed is
> `0x5d` and is inflicted by **Death damage type `0x20`** via the *effects word* `CA+0x13`, an entirely
> different mechanism from these `CA+0x18` strike flags). Full type/status tables:
> [`Combat_Log_Implementation_Design.md`](Combat_Log_Implementation_Design.md) §0/§1.
>
> **Live bit map of `CA+0x18` after this mod is applied** (so a future reader does not misread `0x02`):
> `0x01` Cause Fear→Panicked (vanilla) · `0x02` vanilla LifeStealing — **still SET by
> `TMeleeRound.CreateStrikeCA` @0x55767EDA but never READ any more**, because this mod's `jmp 0x5580DC80`
> @`0x5576678C` bypasses the vanilla consumer block (`0x55766792`–`0x557667BD`) ⇒ **vestigial, do not use
> it as a lifesteal signal** · `0x04` Entangle Strike→Entangled (vanilla) · **`0x08` = THIS MOD's
> LifeStealing `0x76`** (set by cave @`0x5580DCE9`, healed @`0x5580DC80`) · **`0x10` = THIS MOD's Dark Gift
> `0xA9`** (set @`0x5580DD00`, healed @`0x5580DC9F`). Both mod bits are gated on `¬CA+0x0c` bit0, i.e.
> offensive strikes only, never retaliations.

Key point: these effects are set in **Generate** and applied in **plain flag-blocks** that gate on the
`CA+0x18` bit and nothing else. That is *why they work on round attack* — Generate runs for round-attack
strikes, and the apply-block doesn't care how the strike was produced.

---
## 2. Why a "normal" lifesteal misses round attacks (root cause)

The vanilla lifesteal (LifeStealing ability `0x76`) is wired *differently* from the effects above:
- Its flag (`CA+0x18` bit `0x02`) is set **only by the normal-melee builder** `TMeleeRound.CreateStrikeCA`
  @ `0x55767E68`. **Round attack uses a different builder** — the global `CreateStrikeCA` @ `0x557665E4`
  (called from `TRoundAttackAbility.fcExecuteCombatCommand` @ `0x55769458`) — which **never sets it**.
- Worse, the heal itself sits in Execute's **first block**, which is gated on the strike-result byte
  **`CA+0x15`**. For round-attack strikes that byte reads `0` in Execute (the strike resolves before
  this block), so the whole block — and therefore *any* heal in it, including one that checks the
  attacker's ability directly — is **skipped**. Meanwhile the flag-blocks further down (Cursed) still run.

Net: a lifesteal built the "normal" way fails on round attack twice over (flag never set **and** the
heal lives in a `CA+0x15`-gated block that round attacks skip).

**Fix: stop fighting it — wire lifesteal exactly like Cursed.** Set a fresh flag in `Generate`; apply
the heal in a plain flag-block (no `CA+0x15`).

---
## 3. The implementation (offensive: normal + round attack)

Two position-independent caves, two 5–6 byte redirects. Free bits `0x08`/`0x10` in `CA+0x18` are used.

### Cave A — set the flags in Generate  (hook `0x557668E2`)
`0x557668E2` sits **inside** Generate's `if CA+0x10 != 0` block (so already hit-gated). Original bytes
`BA 33 00 00 00` (`mov edx,0x33`). Redirect with `E9 <rel32>` (5 bytes) to the cave; the cave sets the
flags, then replays `mov edx,0x33` and jumps back to `0x557668E7`.

```asm
cave_lsgen:                     ; EBX=CA, EDI=attacker, ESI=target
    test byte [ebx+0x0c], 1     ; OFFENSIVE-ONLY GATE (see §5 to drop for defensive)
    jnz  _replay                ;   defensive strike -> set no flag
    mov  edx, 0x76              ; LifeStealing ability id
    mov  eax, edi
    mov  ecx, [eax]
    call [ecx+0xa8]             ; TCombatUnit.GetAbilityEnabled(0x76)
    test al, al
    jz   _dg
    or   byte [ebx+0x18], 0x08  ; LifeStealing flag
_dg:
    mov  edx, 0xA9              ; Dark Gift enchantment id (change to your ability)
    mov  eax, edi
    mov  ecx, [eax]
    call [ecx+0xa8]
    test al, al
    jz   _replay
    or   byte [ebx+0x18], 0x10  ; Dark Gift flag
_replay:
    mov  edx, 0x33              ; replay the displaced instruction
    jmp  0x557668E7
```

### Cave B — heal in Execute  (hook `0x5576678C`)
`0x5576678C` is the very start of Execute's effect section. Original bytes `80 7B 15 00 74 3D`
(`cmp byte [ebx+0x15],0` + `jz 0x557667CF`). Redirect with `E9 <rel32> 90` (6 bytes). The cave heals the
attacker per flag, then jumps to `0x557667CF` — **skipping the old `CA+0x15`-gated first block entirely**
(so any previous lifesteal heal in that block is bypassed — no double-heal).

```asm
cave_lsround:                   ; EBX=CA, EDI=attacker
    test byte [ebx+0x18], 0x08  ; LifeStealing flag?
    jz   _dg
    mov  eax, edi
    mov  edx, [eax]
    call [edx+0x88]             ; TCombatUnit.GetHitPoints
    add  eax, 2                 ; <-- LifeStealing heal amount
    mov  edx, eax
    mov  eax, edi
    mov  ecx, [eax]
    call [ecx+0x8c]             ; TCombatUnit.SetHitPoints (clamps to [0,max])
_dg:
    test byte [ebx+0x18], 0x10  ; Dark Gift flag?
    jz   _done
    mov  eax, edi
    mov  edx, [eax]
    call [edx+0x88]
    add  eax, 2                 ; <-- Dark Gift heal amount
    mov  edx, eax
    mov  eax, edi
    mov  ecx, [eax]
    call [ecx+0x8c]
_done:
    jmp  0x557667CF
```

Why it's safe: the heal calls (`GetHitPoints`/`SetHitPoints`, vtable `+0x88`/`+0x8c`) and
`GetAbilityEnabled` (`+0xa8`) are Delphi register methods → they preserve `EBX`/`ESI`/`EDI`/`EBP`, so the
CA/target/attacker survive into the following flag-blocks. `SetHitPoints` clamps, so no HP overflow. The
flag already means "damaging offensive hit", so **no `CA+0x15` check is needed** in the heal.

### Result
LifeStealing **and** Dark Gift lifesteal on **all offensive strikes — normal melee and round attack** —
and NOT on defensive/retaliation (the `CA+0x0c` gate) and NOT on ranged (ranged is a different CA class
whose Execute this cave never runs in).

---
## 4. Building / applying

Reference implementation: **`build_scripts/build_lifesteal_roundattack.py`** (keystone-assembled,
capstone-reviewed, dry-run by default, `--apply` to write, idempotent, verify-before-write, auto-backup
to `AoWEPACK.dpl.pre-lsround`). Caves placed at `0x5580DC80`/`0x5580DCD0` (a clean zero block — note the
combat cave region `0x5580C1xx–0x5580C5xx` has several other caves; pick free space and let the script
verify it's zeroed). Close all AoW binaries before `--apply` (they lock the DLL). **Revert** = copy the
`.pre-lsround` backup over the DLL. Heal amounts are the two `add eax, N` bytes (script consts
`LS_HEAL`/`DG_HEAL`).

The old lifesteal path is left in place but is now unreachable (Cave B jumps over it), so reverting this
patch restores the previous behaviour.

---
## 5. DEFENSIVE LIFESTEAL (the variant a retaliation-lifesteal modder wants)

**Goal:** also heal when a unit *retaliates* (defensive strike), not just when it attacks.

**Why it's a one-line change.** Defensive/retaliation strikes are *also* `TStrikeCA`s that run through
`Generate` + `Execute` — the only thing marking them is `CA+0x0c` bit `0x01` (set via
`SetDefensive`). Cave A above deliberately **skips** them with:
```asm
    test byte [ebx+0x0c], 1
    jnz  _replay
```
Remove those two instructions and the flags get set on **every** strike — offensive *and* defensive. Cave
B is unchanged (it heals whoever the current strike's *attacker* is; for a retaliation strike that is the
**retaliating** unit, which is exactly who should lifesteal on a counter-hit).

Three equivalent ways to do it:
1. **Script switch (easiest):** in `build_lifesteal_roundattack.py` set **`DEFENSIVE = True`** and re-run
   with `--apply`. (This drops the two gate instructions from Cave A; the cave bytes change, so it's a
   real re-apply.)
2. **Rebuild the cave** without the `test`/`jnz` pair (per the asm in §3).
3. **In-place NOP (if you already applied the offensive version):** blank the offensive gate inside the
   live Cave A. In the reference build it's the first **6 bytes of `cave_lsgen` @ `0x5580DCD0`** —
   `F6 43 0C 01 75 2E` (`test byte [ebx+0x0c],1` + `jne _replay`). Overwrite those **6 bytes with `90`
   (NOP × 6)**. Then the flags are set regardless of offense/defense. (The `75 2E` displacement is
   build-specific — confirm the bytes at your cave's start before poking.)

**Behaviour after the change:** LifeStealing and Dark Gift units heal on hits they *make* (normal + round)
**and** on hits they land while *retaliating*. It stacks with the offensive heal (a unit that both
attacks and retaliates in a combat round heals on each). Still hit-gated (no heal on a whiffed
retaliation), still not ranged.

**Caveats to warn a fellow modder about:**
- Defensive lifesteal is strong on tanky, high-retaliation units (they heal every time they're attacked
  and strike back). Consider a smaller `add eax,N` for the defensive case if you want it milder — though
  note both offensive and defensive share the same heal value here.
- If you want **defensive-only** (heal on retaliation but *not* on your own attacks), invert the gate:
  keep it but flip `jnz _replay` to `jz _replay` (skip when *offensive*). Round attack would then NOT
  lifesteal — the opposite of this guide's goal.
- It applies to *both* lifesteal sources (0x76 and 0xA9) together, because both live under the same gate.
  To make only one of them defensive, split the gate so it wraps just that ability's flag-set.

---
## 6. Reference

**Ability IDs:** LifeStealing `0x76` · Dark Gift (this mod's enchantment) `0xA9` · Death Strike `0x77`
(→ applies Cursed `0x5E`) · stun-type `0x33` (→ applies `0x6C`) · Marksmanship `0x20` · Enchanted Weapon
`0x9A`. **`CA+0x18` flag bits:** `0x01` (0x33), `0x02` (old builder-set lifesteal, now vestigial),
`0x04` (Cursed), `0x08`/`0x10` (this mod's LifeStealing/Dark Gift). **`CA+0x0c` bit `0x01`** = defensive.

**Key functions:** `TStrikeCA.Generate` `0x557668B4` · `TStrikeCA.Execute` `0x55766738` (effect blocks:
lifesteal-old `0x5576678C`, `0x6c` `0x557667CF`, Cursed `0x55766806`) · global `CreateStrikeCA`
`0x557665E4` (round attack) · `TMeleeRound.CreateStrikeCA` `0x55767E68` (normal melee, sets old bit
`0x02`) · `TRoundAttackAbility.fcExecuteCombatCommand` `0x55769458` · `TSingleTargetCA.SetDefensive`
`0x557299E4`. **TCombatUnit vtable:** `GetAbilityEnabled +0xA8`, `GetHitPoints +0x88`, `SetHitPoints
+0x8c`. **Hook sites used here:** Execute `0x5576678C` (orig `80 7B 15 00 74 3D`, → `0x557667CF`);
Generate `0x557668E2` (orig `BA 33 00 00 00`, → `0x557668E7`).

*Verified & implemented 2026-07-08; offensive (normal + round) version CONFIRMED WORKING in-game. See
`Investigation_Lifesteal_RoundAttack.md` for the full RE trace.*
