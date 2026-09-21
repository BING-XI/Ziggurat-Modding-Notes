# Shield + deferred-retaliation facing — BUILD SPEC

## S1 (facing re-timing) — CONFIRMED WORKING (2026-08-27), THEN REVERTED BY CHOICE

**The user tested `build_facing_retal.py` in-game on 2026-08-27 and confirmed it works.** All three
parts behaved as designed: a melee victim no longer spins when struck, it turns to face its
attacker just before its retaliation swing, and touch victims no longer spin.

**It was then reverted the same day — not because of any defect.** Shield moved to ranged-only
(see below), which removed the reason the defender's melee-time facing needed preserving. The
script is kept on disk as a **working, re-appliable technical option**:

```
python "Modding Resources/build_scripts/build_facing_retal.py" --apply     # bring it back
```

Sites it patches (all byte-verified while installed): `0x004092B9` = `EB 65 90`;
`0x00409BB3` = `E9 48 E6 02 00 90` -> cave `0x00438200` (51 B); `0x00409F2A` = `E9 3D 01 00 00 90`.
It supports `--parts a|b|c` so any single part can be applied or reverted alone.

⚠ **If it is ever re-applied, re-check the interaction below** — it did not exist while Shield was
melee-capable.

### ⭐ The interaction that reverting S1 creates (with Shield ranged-only)

Vanilla re-faces a melee victim towards its attacker. With Shield now defending only against
**ranged** attacks, that vanilla behaviour becomes mechanically live: **engaging a unit in melee
rotates its shield arc**, because the victim turns to face whoever meleed it. A melee unit can
therefore be used to spin a shielded target's front/front-left arc towards or away from friendly
archers. This is emergent from restoring vanilla, not something that was designed — but it is a
real tactical lever and should be judged on purpose rather than discovered as a surprise.
Re-applying S1 would remove it.

## S2 (Shield) — ⭐ CONFIRMED WORKING (2026-08-27)

**The user tested it in-game on 2026-08-27 and confirmed it works, explicitly including that
front and front-left are the ONLY protected directions.** That closes the one link static analysis
could not: the sprite-index-to-hex-direction transform on screen. **HN handedness is now proven end
to end** — map maths, pixel bearings, and what the player actually sees all agree.

⚠ **Scope of the confirmation:** the **manual tactical** ranged arc is confirmed. The
**auto-resolve 75% per-shot rule is still statistically untested** — it needs repeated
auto-resolves of the same matchup to observe, and a single battle cannot show it.

**Ranged attacks only** (user ruling: vanilla **Parry `0x71`** already grants a melee DEF buff —
live magnitude **−8**, not the −4 older docs claimed — so a melee Shield duplicates it).
Id `0xB0`, mask `0x03FF`, **−5 on the shooter's attack** (≡ +5 DEF, **−25 percentage points** on the
live 5 pp slope). Two arms, converging on a single `sub byte [esp+4],5` so they cannot drift:

| mode | gate | rule |
|---|---|---|
| **manual tactical** (`TTacticalCombatUnit`, instsize `0x68`) | geometric | fires when `(D−F) mod 6 ∈ {0,5}` — front and front-**left** |
| **auto-resolve** (`TFastCombatUnit`, instsize `0x64`) | probabilistic | **75% per shot** — no facing exists there |

Live sites: `0x557BCECF` (registration → `cave_reg`, moved to `0x55823128`) and `0x55812A7B`
(ranged link → `0x558230D0`). Cave `0x55823000`–`0x5582316B`, 363 B. Manual arc byte-identical to
the 2026-08-26 build.

⭐ **Ranged-only is STRUCTURAL, not a flag test.** Melee builds its combat action through a
different constructor (`CreateStrikeCA`); the hooked ranged constructor serves only
`TRangedAttackAbility`, `TBoltsAbility`, `TBreathAbility` and `TFlameThrowingAbility`. Melee never
reaches the code at all.

⭐ **The class discriminator must be EXACT.** `cmp ecx,0x68 / jb` sends anything smaller to the
auto-resolve arm, which then tests `cmp ecx,0x64 / jne` — **equality, not `jae`**. An inclusive
`jae` would have put a die roll on the manual path, which is reached from a UI message handler.

### ⭐ The RNG / determinism answer (recorded because it is easy to get wrong twice)

`call 0x55701080` → `VCL30.dpl!System.@RandInt` — **the identical primitive the existing to-hit
roll (`HitRole @0x55725DC0`) and damage roll already use**, not an analogue. `RandInt(4)` returns
the top two bits of the advanced seed, so `< 3` is **exactly 75.000%**, no modulo bias.

**Adding a roll to a path every peer executes identically is NOT a desync risk** — combat already
rolls constantly off this seed. The failure mode is a *conditionally* executed roll, where one peer
draws and another does not. Here the gate reads only game state (victim non-nil, has Shield, is a
fast-combat unit); nothing touches fog, a timer, a pointer value or UI state.

Three further facts that close it:
- `System.RandSeed` is re-anchored once per combat by `TCombat.Execute @0x557282C8`
  (`RandSeed := AoWHSMap.Random($FFFFFF)`, a single draw from the network-synchronised stream);
  `TFastCombat.Execute @0x55744A0C` calls that first and then runs the battle off it.
- ⭐ **The combat predictor draws no random numbers at all** — no predictor address appears among
  the ~115 references to `@RandInt`. It is a pure arithmetic simulator that never builds a combat
  action. So speculative AI evaluation cannot consume draws, and no gate was needed.
- ⭐ **`@RandInt` does not advance `[map+0x230]`**, the value the out-of-sync comparator reads, so
  this patch cannot trip a false desync alarm either.

⚠ **`Release/Ability.pfs` record 186 exists** (minted by the user's AoWDevEd session): tag 6
(level-up cost) = **8** — the same as Parry — and tag 9 = `0x03FF`. **There is no tag 5**, so Shield
has no info-card description; adding one changes the record length and needs the editor, not a
byte-patching script. The cave's own `EXPAND_COST = 6` is now decorative: `TAbility.ReadWrite
@0x5574F07C` makes the data file win.
⚠ **`AoW.exe` / `AoWCompat.exe`** each carry one byte at file offset `0x21DE40` = `02`, putting
Shield in the **Melee** level-up column — chosen while it was a melee ability, so probably now the
wrong column ("Resistances" holds the 17 mitigation abilities). No `--undo`: edit `ABILITY_CATS` in
`build_scripts/herodlg_cats.py` and re-run `build_herodlg_columns.py --apply`.
⚠ **Console encoding fix, 2026-08-27**: the script printed U+26A0 and died with a
`UnicodeEncodeError` *after* writing its bytes, exiting 1 — which reads as a failed patch. A
`sys.stdout.reconfigure(errors="replace")` guard was added; `--apply` now exits 0.


Independently byte-verified 2026-08-27 while S1+S2 were both installed (not taken on QA's word):
all three AoWTCPCK edits; `0x004092B4` / `0x00409E60` / `0x0040AAAF` still untouched `E8` calls;
exe lockstep exactly one byte (`0x3BB7C`, `0F`/`05`); and the arc cave testing `{-1, 0, 5}`.

---

Derived by a 5-agent sweep (3 RE lanes + adversarial verification + synthesis); 5 claims were
refuted and corrected in place. §7 lists what is still unproven — read it before building.

---

# SPEC — Facing-deferred retaliation (S1) + "Shield" directional ability (S2)

Target: Age of Wonders 1, live install. Binaries touched: `AoWTCPCK.dpl` (S1), `AoWEPACK.dpl` (S2), `Release/Ability.pfs` (S2 data half).
Status of every claim below: derived from live-binary disassembly and confirmed by an adversarial verification pass, **except** items explicitly marked *must check first*.

---

## 1. Feasibility verdict

**The engine has a distinct, first-class retaliation step**, so S1 is not a re-architecture — it is a move of one existing operation to a site that already exists and is reached exactly once per retaliation strike. `AoWE.TMeleeRound` builds a single *interleaved* strike array (stride `0x14`, base `round+0x0C`) in which every record carries an explicit side byte at `+0x0C` (0 = attacker delivers, 1 = defender retaliates), written at `0x55767B8F` (`mov byte [ebx+0xc],al`). `TMeleeRound.Calculate @0x55767D24` keeps separate per-side strike counts at `round+0x28` / `round+0x2C`, can make the defender strike **first** when it has First Strike (`0x74`) and the attacker does not, and `CalculateStrikes @0x55767B24` alternates A,D,A,D. `TMeleeRound.CreateStrikeCA @0x55767E68` even stamps retaliation CAs with `TSingleTargetCA.SetDefensive(1)`. S2 is likewise cheap: `+4 DEF` and `−4 ATK` are *arithmetically the same edit* because the roll only ever sees `d = attack − defence`, formed by one unclamped `sub eax,edx` at `0x55726A2C`; vanilla already implements the defensive ability Parry (`0x71`) exactly this way. The expensive part of S2 is not the `+4` — it is the arc test that gates it, and that is fully solved for both melee and ranged.

| Item | Verdict | Deciding fact |
|---|---|---|
| **S1** — no turn on being hit; turn only just before a retaliation strike | **FEASIBLE** | Retaliation is explicit (side byte at strike record `+0x0C`). Removal edit is 3 bytes at `0x004092B9`; the new turn goes at `0x00409BB3`, the head of `ExecuteStrike`'s `side != 0` arm, reached once per retaliation strike and never otherwise. Both sites `.reloc`-free. |
| **S2** — Shield ability, +4 DEF vs front & front-LEFT | **FEASIBLE** | `−4` on the attack accumulator ≡ `+4 DEF` bit-for-bit. Three existing chain tails (`0x558129EC`, `0x55812A2E`, `0x55812A7B`) accept a new link; ability id space has 34 contiguous free ids (`0xAC`–`0xCD`); the last intact vanilla `call RegisterAbility` at `0x557BCF04` is unclaimed. |
| **Ranged inside Shield** | **FEASIBLE — recommended to include** | Vanilla never re-faces a ranged victim (`TCAbRangedTE.NextStrike` `0x0040F31D/2F/41/53/65/77` all re-face the **shooter** only), so including ranged deletes no behaviour. The retargeted blocker *is* the object passed to `CreateRangedAttackCA`, so the shooter's hex is the true incoming bearing. The exact sector formula was validated 60/60 against the engine's own `BreathDir` table. |

**Not feasible / out of scope by construction:** Shield in **auto-resolve**. `TFastCombatUnit` (instance size `0x64`) has no hex and no per-unit facing, and its `+0x60` field is *not* an HS. The mandatory class guard (§4) excludes it. Shield will silently do nothing in auto-resolved battles — a design consequence the user must accept or reject (§8, Q8).

---

## 2. What the engine does today

### 2.1 The melee exchange, in order (all VAs in `AoWTCPCK.dpl` unless noted)

`CombatTE.TCMeleeMoveTE.LastMove @0x0040905C` is a 9-state machine on `[this+0x31]`, dispatched via the jump table at `0x00409091` (state 0 = `0x004090B5`, 1 = `0x0040976C`, 2 = `0x00409356`, 3 = `0x0040939F`, 4 = `0x0040965B`, 5/6/7 = `0x00409785` **(the exit/teardown epilogue, not a no-op)**, 8 = `0x00409376`).

| # | Site | What happens |
|---|---|---|
| 1 | `0x004090D0` | `TUnitHS.CancelMove` on the attacker |
| 2 | `0x0040916C`–`0x004091CF` | resolve the target hex → `TMapLevel.GetField` → field VMT `+0x80` (mask `0x220104`) → defender stored at `[this+0x28]`; nil ⇒ result 3 bail at `0x004091D9` |
| 3 | `0x004091EB` | `TMeleeRound.Create` → `[this+0x38]` |
| 4 | **`0x00409208`** | `AoWE.TMeleeRound.Calculate` (thunk `0x0040280C`) → `CalculateStrikes @0x55767B24` fills **every** strike record for the whole round: `+0x00` attack delta, `+0x04` damage delta, `+0x08` DV, `+0x0C` side flag |
| 5 | `0x0040922D` | `SetAction(attacker, 6)` |
| 6 | `0x00409232`–`0x0040929D` | `AoWTC.GetMeleeDirIndex @0x00430C58` (EAX=attackerX, EDX=Δx, ECX=Δy) |
| 7 | **`0x004092B4`** | `SetDirection(attackerHS, dir)` — **the attacker turns to face its target. Keep this.** |
| 8 | **`0x004092B9`–`0x0040931F`** | **the defender re-face — this is what S1 deletes.** Loads attacker facing, `add edx,3`, `SetDirection(defenderHS)` at `0x004092E0`, then the mod-6 fix-up (`cmp byte [defHS+0x14],6 / jbe 0x409320`, `sub edx,6`, second `SetDirection` at `0x0040931B`). One logical operation plus its wrap. `SetDirection @0x5578480C` range-checks nothing, so the facing byte transiently holds 7/8/9 between the two calls. |
| 9 | `0x00409320` | join point: state := 2, fall into epilogue |
| 10 | state 2 `0x00409356` | poll attacker HS `+0x25` (action complete) → `ExecuteStrike` |
| 11 | **`ExecuteStrike @0x00409B1C`** | `0x00409B45` `Random(0xFFFFFF)`; **`0x00409B5E` `TMeleeRound.CreateStrikeCA(round, idx)`** → `[this+0x34]`; `0x00409B78` `GetMeleeStrike`, side flag → `[ebp-0xc]`; `0x00409B7D cmp byte [ebp-0xc],0 / jne 0x00409BB3`; flag 0 ⇒ `SetAction(attacker,1\|2)`, flag ≠ 0 ⇒ `SetAction(defender,1\|2)` at `0x00409BCA/0x00409BDC`; `idx++`; state := 3 |
| 12 | state 3 `0x0040939F` | blood/`SetAction(4)` on the receiving side |
| 13 | state 4 `0x0040965B` | `TCombat.ExecuteCombatAction(combat, [this+0x34])` at `0x004096C8/0x00409721` — **the actual damage** — then victim VMT `+0x60 GetEnabled`; dead ⇒ state 1, alive ⇒ `NextStrike` |
| 14 | `NextStrike @0x00409A68` | skips strikes whose owner VMT `+0x64 GetLocked` is true; state := 8 with `[this+0x20] = 3` if strikes remain |

### 2.2 The numbers

`CreateStrikeCA @0x55767E68` composes the final CA **per strike**: `0x55767EB7 call [edx+0x6c]` (GetAttack) `+ byte [edi]`, `0x55767EC2 call [edx+0x78]` (GetDamage) `+ byte [edi+4]`. Note the deltas are written as **dwords** by `CalculateStrikes` but read back as **signed bytes** here — any cave-added delta must stay within ±127.

The roll: `TCombatObject.ExecuteDamageRole @0x557269F0` → `call [edx+0x70]` (GetDefense) → `movsx eax,al` (`0x55726A24`) → `sub eax,edx` (`0x55726A2C`, **unclamped**) → `AoWE.ExecuteDamageRole @0x55725EAC` sees only `d`. On this install the slope is **5 percentage points per point of `ATK−DEF`** (byte-diffed against the pristine DLL: `0x55725ED7` is `nop;nop` live vs vanilla `add eax,eax`; `HitRole @0x55725D9D` is `nop;nop; imul eax,eax,5` vs vanilla `add eax,eax; lea eax,[eax+eax*4]`), clamped 10 %–90 % at `d = ∓8`.

### 2.3 Facing consumers

`TTacticalCombatUnitHS.Show @0x00421EE0` dispatches on the action byte `[this+0x24]` (jump table `0x00422230`) and every arm computes the sprite index as `facing + K` (K = −1 idle, +5 walking, +0x0B, +0x0F, +0x11). The only bounds check is the assert at `0x00421F1F`, which tests the *raw* facing, not `facing+K`. Second consumer: `HSEngine.CenterHNtoHX @0x004220B4` (draw-order/occlusion only). Third: `HSEngine.HNtoHP @0x0042226F`, gated on `[HS+0x15] != 0xFF` (mid-move interpolation), not reached during a strike.

### 2.4 What the melee path does **not** do

`re_tools/xref.py` on the `SetDirection` thunk `0x00402AF4` gives 35 call sites module-wide; inside the melee TE there are exactly three — `0x004092B4` (attacker), `0x004092E0` and `0x0040931B` (defender). `NextStrike` and `ExecuteStrike` contain none. **Nothing else writes the defender's facing.**

---

## 3. S1: the change

Build script: **`build_scripts/build_facing_retal.py`**, target `AoWTCPCK.dpl`, cave zone **`0x00438200`** (inside the `0x2EAF5`-byte zero run starting `0x0043810B`; section `CODE` characteristics `0x60000020` = `MEM_EXECUTE|MEM_READ|CNT_CODE`, verified; zero `.reloc` entries in `0x00438100`–`0x00438400`).

### 3.1 Site A — remove the on-being-hit turn

| | |
|---|---|
| Address | `0x004092B9` |
| Live bytes | `8B 45 FC` (`mov eax,[ebp-4]`) |
| Replace with | `EB 65 90` (`jmp short 0x00409320` ; `nop`) |
| Arithmetic | `0x00409320 − (0x004092B9 + 2) = 0x65` |
| Reloc | none in `0x004092B9`–`0x004092BB` |

The skipped span `0x004092B9`–`0x0040931F` is entered only by fall-through from `0x004092B4`. Its only inbound edges are the two internal `jno` fix-ups at `0x004092CA` and `0x00409305`. `0x00409320` is a genuine join — already the target of the `jbe` at `0x004092F2` and of the two result-3 bails at `0x004091DF` and `0x0040921D` — and its body is `mov eax,[ebp-4]; mov byte [eax+0x31],2; …; jmp 0x409785`. The two `.reloc` entries inside the dead span (`0x004092D3`, `0x0040930E`, the `bound edx,[0x409898]` disp32s) stay physically present and loader-fixed; they are simply never executed. **Do not NOP the whole span instead** — that would let the loader rewrite those two dwords into confusing garbage.

**This changes no vanilla combat number.** All strike deltas and DVs are precomputed at `0x00409208`, and nothing in `Calculate` / `CalculateStrikes` / `CreateStrikeCA` / `StatisticsToDV` reads hex geometry (no `GetXhx`, no `GetYhx`, no field lookup, no direction call anywhere in the chain). Facing is consumed only by the renderer. *(Precise wording matters here: it is **not** true that "all damage arithmetic happens before any facing change" — `CreateStrikeCA` composes `GetAttack + delta` and `GetDamage + delta` per strike at `0x00409B5E`, after the state-0 facing writes. The correct statement is that the **deltas are precomputed and no facing consumer exists in the chain**.)*

### 3.2 Site B — add the just-before-retaliation turn

| | |
|---|---|
| Address | `0x00409BB3` (head of `ExecuteStrike`'s `side flag != 0` arm; only inbound edge is the `jne` at `0x00409B81`) |
| Live bytes | `8B 45 FC 8B 40 34 80 78 10 00 75 12` |
| Displace | first **6** bytes (`8B 45 FC 8B 40 34`) → `E9 <rel32 to cave>` + `90`; resume `0x00409BB9` |
| Reloc | only 2 in the whole function, at `0x00409B3A` and `0x00409B4C`, both well ahead of the hook. No branch target lands in `0x00409BB4`–`0x00409BB8`. |

Register state: **nothing live** (the previous instruction is the `call` to `GetMeleeStrike`, whose result went to the stack). `EBP` is `ExecuteStrike`'s own frame, so `[ebp-4] = this` is directly readable. `ExecuteStrike`'s prologue is only `push ebp; mov ebp,esp; add esp,-0x18; mov [ebp-4],eax` — it does **not** push `EBX/ESI/EDI`, and its caller `LastMove` does (`0x00409062`–`0x00409064`). A cave clobbering them would corrupt `LastMove`'s saved registers, so **`pushad`/`popad` is mandatory** — and free, since nothing is live.

`[this+0x28]` is proven non-nil (state 0 bails at `0x004091D9` otherwise) and vanilla dereferences `[this+0x28]+0x60` four instructions later.

```asm
cave_retal_turn:                  ; 0x00438200
    pushad
    mov   eax, [ebp-4]            ; TCMeleeMoveTE
    mov   eax, [eax+0x1C]         ; attacker TTacticalCombatUnit
    mov   eax, [eax+0x60]         ; attacker HS
    movzx edx, byte [eax+0x14]    ; attacker facing, 1..6
    add   edx, 3
    cmp   edx, 6
    jbe   .ok
    sub   edx, 6                  ; wrap BEFORE the call — SetDirection has no range check
.ok:
    mov   eax, [ebp-4]
    mov   eax, [eax+0x28]         ; defender TTacticalCombatUnit
    mov   eax, [eax+0x60]         ; defender HS
    call  0x00402AF4              ; AoWE.TUnitHS.SetDirection thunk (EAX=self, DL=dir)
    popad
    mov   eax, [ebp-4]            ; re-issue the displaced 6 bytes
    mov   eax, [eax+0x34]
    jmp   0x00409BB9
```

`SetDirection @0x5578480C` is idempotent (`cmp bl,[esi+0x14]; je out`), takes the direction in `DL` only, callee-saves `EBX/ESI`, clobbers `EAX` alone, and does not repaint — so calling it once per retaliation strike is free.

**Dependency to be aware of:** the `+3` idiom reads the *attacker's* facing byte, which is only the direction defender→attacker because `0x004092B4` re-faced the attacker at its target one step earlier, and because the two units are adjacent. Site A does not touch `0x004092B4`, so this holds. If that ever changes, the self-contained alternative is to recompute with `AoWTC.GetMeleeDirIndex @0x00430C58` (EAX = defenderX, EDX = defenderX − attackerX, ECX = defenderY − attackerY), taking the hexes from `HS+0x04` → `TMapField`, `X = byte [field+0x10]`, `Y = byte [field+0x11]`.

### 3.3 Animation consequence

**A defender that never turns animates correctly, not wrongly.** Every action has a full six-direction sprite block and facing is the only selector. S1 keeps facing in 1..6 and **deletes** the transient 7/8/9 that vanilla writes between `0x004092E0` and `0x0040931B`, so the sprite index range is unchanged or narrower. The visible change is: a unit struck from behind keeps its back to the attacker and takes the hit; if it retaliates it snaps round on the swing.

Under the hook as written, **the defender stays turned after retaliating** — the attacker's later strikes in the same exchange therefore land on the defender's new front. Turning it back would need a second cave in the state-4 / exit path and would read as a visual stutter. See §8, Q2.

### 3.4 Touch abilities

**They do not need the same treatment for correctness — only for consistency.** Touch has no retaliation, so there is nowhere to move the turn to; the choice is keep-or-delete.

- `0x00409E60` re-faces the **actor** at the target hex — the mirror of `0x004092B4`. **Keep.**
- `0x00409F51` + `0x00409F90` re-face the **target** to actorFacing+3 with the identical wrap — the true mirror of `0x004092E0`/`0x0040931B`, already gated by `[this+0x28] != 0` (`0x00409F1F`) and `[this+0x3c] != 0x75` Wall Crushing (`0x00409F24`).
  Optional removal: at `0x00409F2A` (live bytes `8B 45 FC 8B 40 1C`) write `E9 3D 01 00 00 90`, jumping to the join `0x0040A06C`. `0x0040A06C − (0x00409F2A + 5) = 0x13D`. The displaced 6 bytes carry no reloc. **Note:** the jumped-over *address range* holds **four** reloc entries, not two — `0x00409F44` and `0x00409F83` (the `bound` disp32s, truly dead) plus `0x00409FCD` and `0x0040A026`, which sit inside the still-reachable `0x75` Wall-Crushing block. The edit is still safe because that block is reached only via the guards at `0x00409F1F`/`0x00409F28`, which jump to `0x00409F9A`.
- ⚠ **Do not touch `0x0040AAAF`.** It is the *opposite* assignment — it copies the target's facing onto the **actor** (`0x0040AAA3 mov dl,[targetHS+0x14]`; `0x0040AAAC` loads the actor's HS) as part of the Possess / appearance-swap path that also calls `SetUnitGFXResourceIndex` at `0x0040AA67`.

### 3.4b Touch re-face removal — VERIFIED IN THE LIVE BINARY 2026-08-26

**Decision: the touch TARGET no longer turns. The touch ACTOR still turns to face what it touches**
(`0x00409E60`), because that is the exact mirror of melee's `0x004092B4`, which S1 keeps. If the
actor's turn is also unwanted that is a separate, equally small edit — say so.

| | |
|---|---|
| Address | `0x00409F2A` |
| Live bytes | `8B 45 FC 8B 40 1C` (`mov eax,[ebp-4]` / `mov eax,[eax+0x1c]`, 3+3, next insn `0x00409F30`) |
| Replace with | `E9 3D 01 00 00 90` (`jmp 0x0040A06C` ; `nop`) |
| Arithmetic | `0x0040A06C − (0x00409F2A + 5) = 0x13D` |
| Reloc on displaced bytes | none |

**Disassembly confirming the control flow (checked with `re_tools/dasm.py`, not inferred):**

```
00409F1B  cmp dword [eax+0x28], 0
00409F1F  je  0x00409F9A            ; no target        -> Wall-Crushing re-test
00409F24  cmp dword [eax+0x3c], 0x75
00409F28  je  0x00409F9A            ; Wall Crushing    -> Wall-Crushing re-test
00409F2A  mov eax,[ebp-4]           ; <-- EDIT SITE. Falls through only here.
00409F2D  mov eax,[eax+0x1c]        ;     ACTOR
00409F30  mov eax,[eax+0x60]        ;     actor HS
00409F35  mov dl,[eax+0x14]         ;     actor facing
00409F38  add edx,3                 ;     opposite
00409F42  bound edx,[0x0040B104]
00409F4B  mov eax,[eax+0x28]        ;     TARGET
00409F51  call 0x00402AF4           ; <-- TARGET re-face #1
00409F5F  cmp byte [eax+0x14], 6
00409F63  jbe 0x0040A06C            ; <-- normal exit
00409F77  sub edx,6                 ;     mod-6 wrap
00409F81  bound edx,[0x0040B104]
00409F90  call 0x00402AF4           ; <-- TARGET re-face #2
00409F95  jmp 0x0040A06C            ; <-- wrapped exit
00409F9A  cmp dword [eax+0x3c], 0x75  ; NOT a plain join — a Wall-Crushing branch head
00409FA1  jne 0x0040A068
```

⚠ **Jump to `0x0040A06C`, NOT to `0x00409F9A`.** The two guards land at `0x00409F9A` because those
cases still need the Wall-Crushing test; `0x00409F9A` re-tests `0x75` and only then falls to
`0x0040A068`. The re-face block's own two exits both target **`0x0040A06C`**, so that is the
"block ran and finished" continuation and the only correct destination. Sending the edit to
`0x00409F9A` would wrongly re-enter the Wall-Crushing test.

⚠ **Do not NOP the span instead.** Four `.reloc` entries lie inside it: `0x00409F44` and
`0x00409F83` (the two `bound edx,[0x0040B104]` disp32s, which become genuinely dead) plus
`0x00409FCD` (`mov eax,[0x00469420]`, an `A1` moffs32 form so the disp is at +1) and `0x0040A026`.
The latter two sit inside the Wall-Crushing block at `0x00409F9A`–`0x0040A067`, which **remains
reachable** via the two guards — the edit removes only the fall-through path. NOPping would let
the loader rewrite the dead dwords into confusing garbage.

⚠ **Do not touch `0x0040AAAF`.** It is the opposite assignment — it copies the *target's* facing
onto the **actor** as part of the Possess / appearance-swap path (which also calls
`SetUnitGFXResourceIndex` at `0x0040AA67`).

**User check in-game:** a webbed / entangled / turn-undead victim no longer spins to face whoever
touched it. Wall Crushing (ability `0x75`) behaves exactly as before. The toucher still turns.

---

---

## 4. S2: the change

Build script: **`build_scripts/build_shield.py`**, target `AoWEPACK.dpl` + `Release/Ability.pfs`, cave zone **`0x55822A00`** (inside the `0xC50D9`-byte zero run starting `0x55822927`; `CODE` characteristics `0x60000020` over `0x55701000`–`0x558E7918`; zero `.reloc` entries in `0x55822800`–`0x558D0000`; unclaimed by any of the 103 existing build scripts).

> ⚠ **Do not use `0x5580E440`** — claimed by `build_combatlog_dll.py` as `LEGACY_CAVE` with `LEGACY_LIMIT = 0x5580ED80`, and its `--vacate` path *zeroes* that range. `build_invis_penalty.py` also uses `0x5580E440` as `RNG_LIMIT`.
> ⚠ **Do not use `0x55822000`** — occupied in the live install (first 32 bytes are `01 00 00 00 00 … 01 00 00 00 FF FF FF FF …`). Docs claiming "809,240 free bytes from `0x55822000`" are stale.
> ⚠ **Do not use `0x55812AB5`–`0x55812FFF`** — that is `build_magebane.py`'s growth room.

### 4.1 The arc test — convention, stated explicitly

**Handedness (PROVEN, three independent legs):**

1. `HSEngine.HNtoXYTable @0x5562E024` — two 8-entry parity blocks. Even column: `1=(0,−1) 2=(+1,−1) 3=(+1,0) 4=(0,+1) 5=(−1,0) 6=(−1,−1)`. Odd column: `1=(0,−1) 2=(+1,0) 3=(+1,+1) 4=(0,+1) 5=(−1,+1) 6=(−1,0)`. Odd-q layout, odd columns pushed down.
2. `HSEngine.HXtoHP @0x5560E3B4` — `px = (x<<5)+8`, `py = (y<<5)+((x&1)<<4)`. Applying it to those six deltas gives pixel bearings **0°, 63°, 117°, 180°, 243°, 297°** — strictly increasing clockwise, identical for both parities.
3. `AoWTC.GetMeleeDirIndex @0x00430C58`, decoded exhaustively, returns exactly the `HNtoXYTable` index of the neighbour, and its result is written straight into `HS+0x14` at `0x004092B4` — so the facing byte lives in the same index space.

Corroborated by AoWEPACK's own rotation tables: `[0x558E8CF8 + 8d] = d+1` (CW), `[0x558E8CF4 + 8d] = d−1` (CCW), `[0x558E8D38 + 4d] = d+3` (opposite); `InvHNTable @0x5562E0CC = 00 04 05 06 01 02 03`.

**Convention adopted:** `HN` 1..6 is **clockwise from North**. `HS+0x14` means *"the direction I am looking"*. **`D` = direction from DEFENDER to ATTACKER**; relative bearing `b = (D − F) mod 6`, with `b = 0` = attacker directly in front. **Shield arc = `b ∈ {0, 5}`** — **front and front-LEFT**, where front-left = `F−1` = one step ANTIclockwise (user, 2026-08-26).

> **Must check first (two residuals, one in-game look each, ~20 minutes total):**
> - The above proves handedness in **map coordinates**. "Clockwise *on screen*" additionally assumes the display transform is orientation-preserving.
> - The ILB **sprite-set index → HN** correspondence is unverified visually. If set *n* does not correspond to HN *n*, the maths would be right while the sprites look wrong. Strong indirect evidence it is 1:1: vanilla sets the attacker's facing to `GetMeleeDirIndex(attacker→target)` immediately before playing the attack animation and nobody has ever reported units swinging sideways.
> - ~~Does "front-right" mean screen-clockwise?~~ **ANSWERED 2026-08-26: the user meant front and front-LEFT.** Arc is `(D−F) mod 6 ∈ {0,5}`, i.e. `F` and `F−1`. The handedness proof below still decides which physical side that is — it is now load-bearing in the opposite direction.

**Test cost:** with `D−1` in `EAX` and `F−1` in memory, `sub eax,<F-1>` leaves `−5..5`; the front-left arc is `test eax,eax; jz hit; cmp eax,5; je hit; cmp eax,-1; je hit` — 6 instructions, no memory table, no PIC anchor. A 6- or 36-entry table is strictly worse in a `.dpl` cave, because reaching any absolute address costs a `call/pop` anchor and a register first.

**Getting the hexes.** ⚠ **Read the fields directly; do not use VMT `+0x74`/`+0x78` on the combat unit.** On `TTacticalCombatUnit` (VMT `0x00412B4C`) slot `+0x74` is `GetResistance` and `+0x78` is `GetDamage`. `GetXhx`/`GetYhx` live at those offsets on the **HS** classes (`TTacticalCombatUnitHS` VMT `0x00412D08`, `TUnitHS` VMT `0x5570EED0`). Feeding Resistance and Damage into the direction maths would shield the wrong arc **with no crash**. The correct chain is `obj → [obj+0x60] = HS → [HS+0x04] = TMapField (nil-check it) → X = byte [field+0x10], Y = byte [field+0x11]`. `TUnitHS.GetXhx @0x55783F50` is literally `mov eax,[eax+4]; mov al,[eax+0x10]; ret`, so the direct read is equivalent and cheaper.

**Mandatory class guard.** `[obj+0x60]` is an HS **only** for `TTacticalCombatUnit`. Instance sizes from `VMT−0x1C`: `TCombatObject 0x4C`, `TCombatUnit 0x5C`, `TCombatWall 0x50`, `TFastCombatUnit **0x64** (has a +0x60 field that is NOT an HS)`, `TCombatPredictorUnit 0x54`, `TTacticalCombatUnit **0x68**`. A parent-chain walk over all 1,987 exported class VMTs confirms those are the only candidates. Guard: `mov ecx,[obj]; cmp dword [ecx-0x1C],0x68; jb skip`. This is PIC-safe and module-agnostic — `AoWEPACK` cannot name `TTacticalCombatUnit`'s VMT, which lives in `AoWTCPCK`.

### 4.2 Melee vs ranged primitive

- **Melee (adjacent):** `dHXtoHNfast` — AoWEPACK thunk **`0x557026AC`** → `HSEngine.dHXtoHNfast @0x5560E338`. Args `EAX=x1, EDX=y1, ECX=x2, [esp]=y2`, `ret 4`, clobbers `EAX` + flags only. Exact for adjacency; branch tree verified against both parity blocks.
- **Ranged (any distance):** `dHXtoHNfast` is **genuinely wrong** at range — it branches only on the *signs* of dx and dy, so sectors 1 and 4 require `dx == 0` exactly and 2/3/5/6 are 90° quadrants. Worked example: defender (10,20), shooter (11,10) → returns **2 (NE)**; the true bearing is **1 (N)**. Measured disagreement over all deltas with r ≤ 12 at both parities: **276/936 = 29.5 %**.
  The exact route is `rad = dHXtoRad` (thunk `0x5570266C`), `hn = dHXtoHN` (thunk `0x557026A4`, returns a **spiral index**, `RadToHN(r) = 3r(r−1)+1`), then `k = hn − (3r(r−1)+1)`, `sector = ((k + ((r−1) div 2)) div r) mod 6`, `direction = sector + 1`. Verified against **all 60 entries** of `AoWTC.BreathDir @0x004673A8`. All three primitives take the identical arg tuple, `ret 4`, return in `EAX`, and preserve `EBX/ESI/EDI/EBP`.
  ⚠ `HXtoHN` (reached via `dHXtoHN`) raises a Delphi exception `'arithemetic error!'` at `0x5560E03A` on a malformed delta — one more reason the nil/class guards must run first. (No exception fires over all 40,400 deltas within ±100, so this is defence in depth.)
  Prefer `dHXtoRad` over `HNtoRad @0x5560DED8`, which goes through `fild`/`fsqrt`/`System.@TRUNC` for `rad ≥ 4`.

Recommendation: **use the exact path at all three sites.** It removes the "is the melee1 attacker always adjacent?" question entirely, and the max quotient before the `mod 6` is exactly 6 over r = 1..60, so a single `cmp/sub` suffices.

### 4.3 The shared arc cave

```asm
SHIELD_ARC:                       ; ret 8 ; [ebp+8]=defender obj, [ebp+0xC]=attacker obj -> AL
    push  ebp
    mov   ebp, esp
    sub   esp, 0x14
    push  ebx
    push  esi
    push  edi
    ; --- defender ---
    mov   esi, [ebp+8]
    call  GETHEX                  ; -> ESI=HS, EBX=x, EDI=y, CF=1 on failure
    jc    .fail
    movzx eax, byte [esi+0x14]    ; facing F
    dec   eax
    cmp   eax, 6
    jae   .fail                   ; rejects 0 and any 7/8/9 transient
    mov   [ebp-0x14], eax         ; F-1
    mov   [ebp-0x04], ebx         ; xD
    mov   [ebp-0x08], edi         ; yD
    ; --- attacker ---
    mov   esi, [ebp+0x0C]
    call  GETHEX
    jc    .fail
    mov   [ebp-0x0C], ebx         ; xA
    mov   [ebp-0x10], edi         ; yA
    ; --- radius ---
    push  dword [ebp-0x10]
    mov   eax, [ebp-0x04]
    mov   edx, [ebp-0x08]
    mov   ecx, [ebp-0x0C]
    call  0x5570266C              ; dHXtoRad thunk
    test  eax, eax
    jz    .fail                   ; same hex
    mov   ebx, eax                ; r
    ; --- spiral index ---
    push  dword [ebp-0x10]
    mov   eax, [ebp-0x04]
    mov   edx, [ebp-0x08]
    mov   ecx, [ebp-0x0C]
    call  0x557026A4              ; dHXtoHN thunk
    ; k = hn - (3r(r-1)+1)
    mov   ecx, ebx
    dec   ecx
    imul  ecx, ebx
    lea   ecx, [ecx+ecx*2]
    inc   ecx
    sub   eax, ecx
    ; round to nearest corner: += (r-1) >> 1
    mov   ecx, ebx
    dec   ecx
    shr   ecx, 1
    add   eax, ecx
    xor   edx, edx
    div   ebx
    cmp   eax, 6
    jb    .nowrap                 ; ⚠ LABEL, never `jb $+4`
    sub   eax, 6
.nowrap:
    sub   eax, [ebp-0x14]         ; (D-1) - (F-1)  in -5..5
    ; want b = (D-F) mod 6 in {0,5} = front and front-LEFT
    test  eax, eax
    jz    .hit                    ; b = 0  (dead ahead)
    cmp   eax, 5
    je    .hit                    ; b = 5  (front-left)
    cmp   eax, -1
    je    .hit                    ; b = 5, wrapped
    jmp   .fail
.hit:
    mov   eax, 1
    jmp   .done
.fail:
    xor   eax, eax
.done:
    pop   edi
    pop   esi
    pop   ebx
    mov   esp, ebp
    pop   ebp
    ret   8

GETHEX:                           ; ESI=combat obj -> ESI=HS, EBX=x, EDI=y ; CF=1 on failure
    test  esi, esi
    jz    .bad
    mov   ecx, [esi]              ; VMT
    cmp   dword [ecx-0x1C], 0x68  ; instance size — rejects TFastCombatUnit (0x64), TCombatWall (0x50)
    jb    .bad
    mov   esi, [esi+0x60]         ; HS
    test  esi, esi
    jz    .bad
    mov   ecx, [esi+0x04]         ; TMapField
    test  ecx, ecx
    jz    .bad
    movzx ebx, byte [ecx+0x10]    ; X
    movzx edi, byte [ecx+0x11]    ; Y
    clc
    ret
.bad:
    stc
    ret
```

⚠ **Two assembly defects in the circulating draft are corrected above and must not be copied back in:** `jb $+4` skips only 2 of the 3 bytes of `sub eax,6` and lands mid-instruction — use a label. And the "melee-only fast variant" as posted passes the wrong four argument registers (`EBX/EDI` hold the *attacker's* x/y and `ESI` holds a pointer at that point) — it is dropped here in favour of the exact path at all three sites.

### 4.4 The three strike sites and their chain tails

All three chains are owned by `build_magebane.py`; Shield appends a new link on each tail. All three 5-byte windows are `.reloc`-free (checked against all 63,883 type-3 entries).

| Chain | Hook | Full chain | **Tail to repoint** | Slack after tail |
|---|---|---|---|---|
| melee1 — `AoWE.CreateStrikeCA @0x557665E4` | `0x557666A1` | `0x5580E070` (slayers) → `0x5580E370` (invis) → `0x558129C0` (magebane) → `jmp 0x557666CF` | **`0x558129EC`** | 3 zero bytes |
| melee3 — `AoWE.TMeleeRound.CalculateStrikes @0x55767B24` | `0x55767C5C` | `0x5580E120` → `0x5580E3B0` → `0x55812A00` → `jmp 0x55767C89` | **`0x55812A2E`** | 3 zero bytes |
| ranged — `AoWE.TRangedAttackAbility.CreateRangedAttackCA @0x5576EB34` | `0x5576EB34` | `0x5580E400` (invis) → `0x5580E190` (slayers) → `0x55812A40` (magebane) → `jmp 0x5576EB39` | **`0x55812A7B`** | ⚠ **ZERO** — `0x55812A80` is live magebane code (`E8 B3 D7 F3 FF`) |

⚠ **Correction to the shared brief: `AoWE.CreateStrikeCA @0x557665E4` ("melee1") is NOT on the ordinary melee path.** Thunk `0x004027F4` has exactly three callers in `AoWTCPCK`: `0x004089F1` (`TCombatMoveTE.DefaultMove`, the free swing during movement) and `0x0040A540` / `0x0040ABBE` (`TCAbTouchMoveTE.LastMove`). Ordinary melee uses `TMeleeRound.Calculate` (thunk `0x0040280C`, callers `0x00409208` and `TCAI.CheckUnit @0x004154C6`) and `TMeleeRound.CreateStrikeCA` (thunk `0x00402814`, single caller `0x00409B5E`). **A rule living only on melee1 would miss every normal melee blow.**

Coverage split:
- **melee3** = deliberate melee **and retaliation** (`CalculateStrikes` swaps striker/victim per strike, so one link handles both directions), plus **auto-resolve** (`TStrikeAbility.fcExecuteCombatCommand @0x55767097`) — except the class guard excludes `TFastCombatUnit` — plus the tactical AI's per-strike scoring, because the attack delta feeds `StatisticsToDV`.
- **melee1** = free swing, touch, and ability strikes. Invisible to the AI.
- **ranged** = ranged attacks. Invisible to the AI.

#### Per-site register contracts and edits

**melee1 tail `0x558129EC`** — `EBP` = attacker, `ESI` = target, `BL` = attack accumulator (byte), `[esp+3]` = damage byte. `EAX/ECX/EDX/EDI` all dead (the resume at `0x557666CF` is `xor ecx,ecx; mov dl,1; mov eax,[0x5571E304]`, and `EDI` is overwritten at `0x557666DD`).

```asm
shield_melee1:
    mov   edx, 0xB0
    mov   eax, esi                ; the DEFENDER's combat object
    mov   ecx, [eax]
    call  dword [ecx+0xA8]        ; TCombatUnit.GetAbilityEnabled @0x55725004
    test  al, al
    je    .done
    push  ebp                     ; attacker
    push  esi                     ; defender
    call  SHIELD_ARC
    test  al, al
    je    .done
    sub   bl, 4
.done:
    jmp   0x557666CF
```
⚠ `EBP` is a *data* register here; `SHIELD_ARC` preserves it. ⚠ `BL` is an absolute byte and can in principle underflow — matches the invisibility precedent `sub bl,2` at `0x5580E396`.

**melee3 tail `0x55812A2E`** — `EBX` = strike record (`+0x00` attack delta dword, `+0x04` damage delta dword, `+0x08` DV, `+0x0C` side flag; stride `0x14`), `ESI` = striker of *this* strike, `EDI` = victim of *this* strike. `EAX/ECX/EDX` free (resume `0x55767C89` is `mov eax,edi; mov edx,[eax]; call [edx+0x70]`).

```asm
shield_melee3:
    mov   edx, 0xB0
    mov   eax, edi                ; victim of THIS strike
    mov   ecx, [eax]
    call  dword [ecx+0xA8]
    test  al, al
    je    .done
    push  esi                     ; attacker
    push  edi                     ; defender
    call  SHIELD_ARC
    test  al, al
    je    .done
    sub   dword [ebx], 4          ; ATTACK delta only
.done:
    jmp   0x55767C89
```
⚠ **Never touch `[ebx+4]`** (the damage delta) and **never clamp `[ebx]`** — it is a shared signed accumulator with Monster Slaying, Assassin, Charge and Parry.

**ranged tail `0x55812A7B`** — ⚠ **different contract from the ranged *hook*.** `EAX = ESI = shooter` and `EDX = [shooter]` are both **LIVE**, because `0x5576EB39` is `call [edx+0xb8]`. `ESI` = shooter, `EBX` = ability, `[EBP-4]` = victim and **can be NIL** (missile absorbed by scenery/wall). With no pushes live, `[esp]` = damage dword, `[esp+4]` = the absolute attack pushed at `0x5576EB1D`. ⚠ **The replacement at the tail must be exactly 5 bytes.**

```asm
shield_ranged:
    mov   eax, [ebp-4]
    test  eax, eax
    je    .done                   ; nil victim
    mov   edx, 0xB0
    mov   ecx, [eax]
    call  dword [ecx+0xA8]
    test  al, al
    je    .done
    push  esi                     ; shooter
    push  dword [ebp-4]           ; victim
    call  SHIELD_ARC              ; ret 8 — stack balanced before the [esp+4] write
    test  al, al
    je    .done
    sub   byte [esp+4], 4         ; the attack from 0x5576EB1D
.done:
    mov   eax, esi                ; ⚠ MANDATORY — restore the live pair
    mov   edx, [eax]
    jmp   0x5576EB39
```

The ability query `mov edx,0xB0; mov ecx,[eax]; call [ecx+0xA8]` is `TCombatUnit.GetAbilityEnabled @0x55725004` — O(1), item-aware, polymorphic. A `TCombatWall` falls through to `TCombatObject.GetAbilityEnabled @0x557268D4` (`xor eax,eax; ret`) and can never reach `SHIELD_ARC`. **Query the ability first** so the geometry work runs only for shielded units.

### 4.5 +4 DEF vs −4 ATK — the decision, and the magnitude

**They are the same edit.** `ExecuteDamageRole` forms `d = attack − defence` with one unclamped 32-bit `sub` and the consumer sees only `d`. Hit chance, the damage roll, the damage **floor** and the RNG draw count are all functions of `d` alone. The floor is `1 + trunc(((M−1)(R−T) + (D>>1))/D)` with `T = 10−d`, `D = 18−T = 8+d`, and only exceeds 1 once `d > 8` on the live scale — moving `d` by −4 lowers it identically whichever side supplies the points.

**Decision: implement as `−4` on the attack accumulator.** Reasons:
1. Vanilla does exactly this for **Parry (`0x71`)**: `sub dword [ebx],8` at `0x55767BE1`, keyed on `EDI` = the defender. That is the exact structural precedent.
2. There is **no attacker-aware defence hook**. `TCombatUnit.GetDefense @0x5572549C` is a one-argument forwarder to `strategicUnit->vmt[0xC4]`; hooking it (or `TAbstractUnit.GetDefense @0x5577FD98` and its four overrides) would apply Shield unconditionally to every incoming attack. `TMeleeRound.GetDefenderDV/GetAttackerDV` (`0x55768064`/`0x5576804C`) are cached AI-valuation outputs, not roll inputs.

**Magnitude on this install.** `P(nonzero) = 0.10 + clamp(18 − max(10−d, 2), 0, 16)/20`, i.e. **5 pp per point**. So **+4 DEF = −20 percentage points of hit chance** (the same 20 pp as +2 DEF on the vanilla 10 pp scale). Measured over all 32,041 ordered unit pairs from live `Release/Unitres.pfs` (179 records; tags `0x0E` ATK / `0x0F` DEF / `0x10` DAM):

| Metric | Value |
|---|---|
| Mean hit-chance drop | **−18.3 pp** |
| Full 20 pp realised | 88.1 % of pairs |
| **Zero effect** (already clamped) | 4.6 % of pairs |
| Mean expected damage per strike | 2.556 → **1.854 (−27.4 %)** |
| Median matchup (ATK 8 / DEF 6 / DAM 6) | 60 % → 40 % hit; E[dmg] 2.35 → 1.55 (−34 %) |

Live unit DEF is 2..20, median 6, mean 6.44, **all even** — so +4 is **+67 % on the median unit**. Relative to live Parry (`−8`, −40 pp, but **first strike of each side only**), Shield at −4 **on every strike in 2 of 6 directions** is roughly comparable in round-total and far more situational.

⚠ **Dead weight outside `−4 ≤ d ≤ +8`.** Below `d = −8` the roll is pinned at 10 % hit / auto-maximum damage (`0x55725ECC cmp ecx,0x12 / jl` tested *before* `T` is computed; `0x55725EE2 cmp esi,ecx / jg` zeroes every middle roll once `T > 17`). Extra defence there does literally nothing.

**Player-visible difference from a true defence-side implementation:** a `−4` attack delta shows in the combat log as a *lowered attack number*, because the log worker is fed `movsx eax, byte ptr [ebp+0x10]` at `0x558114A0` — the post-modification value. (Same behaviour as the invisibility penalty, which prints as `A-2`.) The defender's unit card is unaffected either way: `TStrikeAbility.GetCombatInfo @0x55766F60` reads base stats. This is the argument for the optional dedicated log line (§6, step 7).

### 4.6 Ability registration recipe

**Id: `0xB0`.** Free ids re-measured on the live install by scanning `AoWEPACK.dpl` for `B8 <imm32> E8 → 0x5576601C` (25 live sites, 21 vanilla, zero orphan calls) unioned with `Release/Ability.pfs` record keys (151 records, ids `0x00`–`0xAB`): free = `0x21`, `0x4E`–`0x55`, `0x5B`, `0x66`–`0x69`, `0x6E`, `0x85`–`0x89`, `0x97`, then **`0xAC`–`0xCD` unbroken (34 ids)**. Mod-added ids in use: `0x38`, `0x9F` (Path of Sand), `0xAA` (Magebane), `0xAB` (Drillmaster). `0xAC` is contested — `Facing_Mechanics_Feasibility` proposes it for Shield while `Caster_Abilities_Feasibility` recommends `0xAC`–`0xAF` for Evoker/Conjurer/Enchanter/Ritualist; neither is reserved. **`0xB0` is free in both the DLL scan and `Ability.pfs`** and leaves both documents' numbering intact.

**Abilities have no icons in AoW1** — they render as text only. `TAbility` (VMT `0x5570F254`, instsize `0x24`) has no icon field: `+0x08` FName, `+0x0C` FAbilityID, `+0x10` FDescription, `+0x14` FExpandCost, `+0x18` FSFX, `+0x1C` FAnimation, `+0x20` FSelectionTypes. The name is a **DLL-side literal, never serialised** (`TAbility.ReadWrite @0x5574F07C` streams tags 5,6,7,8,9 only — `FName` is absent). A description is optional tag 5; Path of Sand and Magebane ship without one.

**Hook site:** `0x557BCF04` in `PassiveAb.RegisterPassiveAbilities` (function base `0x557BC1CC`) — the last still-intact vanilla `call TAbilityControl.RegisterAbility`, live bytes `E8 2F 33 F9 FF` → `0x55750238`, `.reloc`-clear. It registers vanilla ability `0x8F` (`mov eax,0x8F` @ `0x557BCEF6`). `EBX` holds the `TAbilityControl` throughout the function. Four vanilla sites are already claimed by mods (`0x557675C4` ranged slayers, `0x557BC9E9` Path of Sand, `0x557BCF39` Drillmaster, `0x557BCF6E` Magebane).

Displace `E8 2F 33 F9 FF` → `E9 <rel32 to cave_reg>`:

```asm
cave_reg:
    call  0x55750238              ; re-issue the displaced RegisterAbility (ability 0x8F)
    call  ANCHOR                  ; ⚠ emit a REAL call; fix_pic zeroes this rel32
ANCHOR:
    pop   eax
    lea   edx, [eax + PH_NAME]    ; -> Delphi AnsiString body for "Shield"
    mov   ecx, 0x03FF             ; FSelectionTypes mask (CX)
    mov   eax, 0xB0               ; ability id
    call  0x5576601C              ; AoWE.CreateEnhancementAbility
    mov   edx, eax
    mov   eax, ebx                ; the TAbilityControl
    call  0x55750238              ; AoWE.TAbilityControl.RegisterAbility
    jmp   0x557BCF09
```

Name literal blob: `struct.pack('<iI', -1, len(name)) + name + b'\x00'`; the pointer is `blob + 8` (refcount −1 so `LStrAsg` shares and never frees).

⚠ **Never write `call $+5` as the PIC anchor in keystone** — it assembles to nothing and the fixer latches onto the wrong `E8`, silently rewriting `call RegisterAbility` into a call into the middle of the cave. `build_drillmaster.py:fix_pic` carries this warning naming the exact function it bit.

⚠ A duplicate ability id fails **loudly**: `'Ability already registered (n)'` / Delphi Runtime error 217 before the main window appears. The build script must `check_id_free` first.

**No work is needed in `AoWTCPCK.dpl`** — its 145-entry import table carries the ability *query* API (`GetAbility`, `GetAbilityEnabled`, `SetAbilityEnabled`, `GetAbilityLevel`, `GetAbilityOwner`, `GetAbilityCount`) but neither `RegisterAbility` nor `CreateEnhancementAbility`.

### 4.7 The AoWDevEd round-trip dependency — a mandatory manual step

⚠ **`Release/Ability.pfs` tag 9 OVERWRITES whatever mask the cave passed** (`TAbility.ReadWrite` loads tag 9 straight into the word at `[ability+0x20]` *after* `CreateEnhancementAbility` set it). 0 of 21 vanilla sites agree with their own data. 81 of 151 live records carry `0x03FF`. Get this wrong and Shield registers, assigns and works but is **never offered** at hero level-up.

`Ability.pfs` record `0xB0 + 10 = 186` does not exist and **cannot be created by script**. Required sequence:

1. `build_shield.py --apply` — the DLL half only.
2. Boot the game once to prove the id registers (no "Ability already registered", no RTE 217).
3. Open **AoWDevEd**, assign Shield to something, and **save** — the editor writes the record.
4. Re-run `build_shield.py --apply` to write tag 9 = `0x03FF` and repair the CRC.

The script must abort with a clear message at step 4 if step 3 was skipped (`build_drillmaster.py` does exactly this). CRC handling: `Release/Ability.pfs` is currently intact — measured `crc32(d[4:])` of the live 29,054-byte file is exactly `0x2144DF1C`, matching `build_drillmaster.py`'s `PFS_RESIDUE`. The tag-9 write is length-preserving; repair with `struct.pack_into('<I', d, len(d)-4, zlib.crc32(d[4:-4]))` and **re-verify the residue before writing** (use `sys.exit`, not `assert`, so `python -O` cannot strip it).

If mask `0x03FF` is chosen, **also add `0xB0` to `build_scripts/herodlg_cats.py` `ABILITY_CATS`** or Shield silently lands in level-up column 4.

---

## 5. Ranged

**Is ranged directionality more complicated? Yes — but only in one specific way, and it is fully solved.**

The complication is **not** the hook (the ranged chain tail already exists and works — invisibility `−5`, magebane and ranged slayers all live on it) and **not** retargeting. It is that the cheap direction primitive `dHXtoHNfast` is a *sign-of-dx/dy quadrant classifier*, exact only for adjacent hexes. Beyond adjacency, sectors 1 and 4 collapse to one-column-wide slivers and 2/3/5/6 become 90° quadrants. Measured disagreement against the true bearing over all deltas with r ≤ 12 at both column parities: **29.5 %** (r=1: 0/12, r=4: 14/48, r=10: 38/120). Players would experience that as *"the shield randomly works"*.

**Recommended primitive:** `dHXtoRad` (`0x5570266C`) + `dHXtoHN` (`0x557026A4`) + the inline ring decomposition
```
k      = hn − (3·r·(r−1) + 1)
sector = ((k + ((r−1) div 2)) div r) mod 6
dir    = sector + 1
```
≈ 20 instructions + 2 calls, executed **once per strike creation**, not per frame. This reproduces the engine's own `BreathDir` table exactly (60/60), so a Shield arc and a breath-weapon cone can never visually disagree.

**Sector-boundary behaviour:** on a ring of radius `R`, the hex `b` steps clockwise of corner `d_i` belongs to `d_i` iff `2b ≤ R`. Even `R` therefore has exactly one tie hex per sextant, and it resolves to the **lower** direction index (verified at r=2 k=1 → dir 1; r=4 k=2 → dir 1; r=3 k=17 → dir 1 by wrap). It is a pure integer function of the offset: **no hysteresis, no dependence on move order or on who computes it** — which also makes it safe for MP lockstep.

**Recommendation: INCLUDE ranged.**
1. Thematic — a shield that stops swords but not arrows is backwards.
2. Free mechanically — `TCAbRangedTE.NextStrike` re-faces only the shooter, so a ranged victim's facing is untouched by vanilla; **no behaviour is deleted**, unlike melee.
3. Safe under retargeting — `TCAbRangedTE.Execute @0x0040C437` passes `[missile+0x2C]` (the field `NextStrike` overwrites with `blocker[+0x1C]` on interception) as the victim and `[[ebp-4]+0x10]` as the shooter into `CreateRangedAttackCA @0x5576EAE4`, whose prologue puts the actual victim in `[ebp-4]` and the shooter in `ESI`. Both hexes are read live from the two objects actually passed.

If the extra code is unwanted, the honest alternative is to **restrict Shield to melee (r = 1)** — *not* to use the fast classifier at range.

---

## 6. Build order

Two independent binaries, so S1 and S2 can be tested separately. Every step is `--apply` / `--undo`, dry-run by default, verify-before-write, and takes a fresh feature-named backup. **Neither the coder nor QA can test the game** — every step ends with a user checklist.

| Step | Change | Script / files | **User must check in-game** |
|---|---|---|---|
| **1** | S1 removal only: `EB 65 90` at `0x004092B9` | `build_facing_retal.py --apply --remove-only`, `AoWTCPCK.dpl` | Attack a unit from behind/flank in tactical combat. The victim **does not spin** to face you. Its sprite still animates the hit correctly (no blank frame, no sideways swing). Nothing else about the exchange changed. |
| **2** | S1 retaliation turn: cave at `0x00438200`, hook `0x00409BB3` | same script, `--apply` | Attack a unit that **will** retaliate: it stays turned away for your blow, then **snaps to face you immediately before its own swing**, and the retaliation animation plays in the right direction. Attack a unit that **cannot** retaliate (locked, no melee damage, killed by the first blow): it **never** turns. Multi-strike exchange: confirm your 2nd/3rd blows now land on its new front (see §8 Q2). |
| **3** | S2 registration only: `0xB0` "Shield" at `0x557BCF04`, cave `0x55822A00` | `build_shield.py --apply` (DLL half), `AoWEPACK.dpl` | Game boots with **no** "Ability already registered" and **no** Delphi RTE 217. "Shield" appears in AoWDevEd's ability list. |
| **3b** | *Manual, not automatable* | AoWDevEd | Assign Shield to a test unit and **save**. Then re-run `build_shield.py --apply` to write `Ability.pfs` tag 9 = `0x03FF` and repair the CRC. Re-boot; if `0x03FF` was chosen, Shield is offered at hero level-up in the expected column. |
| **4** | S2 arc test + **melee3** link (tail `0x55812A2E`) | `build_shield.py --apply --melee3` | Attack the Shield unit from its **front** and **front-left** — noticeably more misses; the combat log shows the attack number **4 lower**. Attack from the other four directions — no change. Confirm front-left is the side you actually see protected. Confirm retaliation also benefits. |
| **5** | S2 **melee1** link (tail `0x558129EC`) | `--apply --melee1` | Free swing during movement, and a touch ability (web/entangle) against the Shield unit from the front — same reduction. No crash on walls or scenery. |
| **6** | S2 **ranged** link (tail `0x55812A7B`) | `--apply --ranged` | Shoot the Shield unit from a **long** distance directly north of it (large dy, dx = 0 or ±1) — the arc classification must match what you see, not a 90° quadrant. Shoot so the missile is **intercepted** by an intervening unit or wall — no crash, and the blocker's own shield arc is used. Shoot into scenery so the missile is absorbed (nil victim) — no crash. |
| **7** *(optional)* | Touch-path re-face removal at `0x00409F2A` | `build_facing_retal.py --apply --touch` | A webbed/entangled/turn-undead victim no longer spins to face its toucher. Wall Crushing (ability `0x75`) still behaves as before. |
| **8** *(optional)* | Combat-log line for Shield | clone `build_effectroll.py`'s ring-writer | A line appears when Shield fires. |

**Undo path:** each script gets a surgical `--undo` — restore the 3/5/6 displaced bytes, restore the chain tail's original `jmp`, zero its own cave zone, verify-before-write, touch no backup. **Do not write "revert and re-apply" as a re-tune procedure**; make the script rewrite its caves in place.

**Revert order** matters only for the three shared chains: Shield's links sit on the **tails** of `build_magebane.py`'s caves, so undo Shield **before** undoing Magebane.

### Notes for step 7 (optional log line)

⚠ **Do not take `TDamageCA.Generate`'s epilogue at `0x55729C8C`** — it is already `jmp 0x558114A0`, `build_combatlog_dll.py`'s damage-line worker. Clone `build_effectroll.py`'s `_emit` at `0x5580F605` instead (do not call it — its effect-name table is hard-coded to six ids). Ring at `0x60D000` (AoW.exe-side absolute, so DLL-rebase-safe), magic `0x31474C43`, 64 slots × 128 bytes, WR/RD at `+4`/`+8`, payload `[u8 len][text]`, built with `LStrLAsg 0x55701158` / `LStrCat 0x55701188` / `IntToStr 0x5570158C`. Guards before writing: exe probe `mov eax,[0x40003C]; cmp dword [eax+0x400050],0x20E000; jb skip`, then the ring magic, then `mov eax,[0x60D004]; sub eax,[0x60D008]; cmp eax,63; jae skip`. Wrap in `pushad`/`popad`. Payload capped at 127 bytes, and the emitter **must** run the same `_check_wire()` assertion shared by `build_combatlog_dll.py` / `build_combatlog_exe.py` / `build_effectroll.py`.

---

## 7. Risks and must-check-first

### Must check first (unproven)

1. **Sprite-set index → HN mapping is visually unverified.** The geometry is proved; if set *n* does not correspond to HN *n*, the maths is right and the sprites look wrong. One 20-minute in-game look at a single unit's facing 1 vs facing 4 closes it. Do this **before freezing the arc constant**.
2. **"Clockwise on screen" assumes the display transform is orientation-preserving.** Handedness is proven in *map* coordinates only. Same in-game look closes both this and (1).
3. ~~front-right handedness~~ **RESOLVED: front + front-LEFT, arc `{0,5}`, `F` and `F−1`.** The remaining risk is items (1) and (2) above: if the sprite/screen handedness is anticlockwise, the constant must flip back to `{0,1}` to protect the side the player actually sees.
4. **`TMeleeStrike` record byte `+0x10`** (5th dword of the `0x14`-byte record) is unresolved. `GetMeleeStrike` copies it; nothing observed reads it. Worth five minutes before any cave writes into the record. *(Neither S1 nor S2 writes it as specced.)*
5. **`AoWE.TMeleeRound.CalculateSingleSide @0x55767DF4`** has no caller in AoWEPACK and is not imported by AoWTCPCK. If it is dead, the free-swing path is entirely `AoWE.CreateStrikeCA` via `DefaultMove @0x004089F1` and needs no S1 treatment — but that was **inferred, not proved**.
6. **Nobody has claimed `0xB0` in an unmerged branch.** Ability ids are serialised into saves (`Ability.pfs` record key = id + 10; unit bitset tag 3 bit index == id) and every MP peer must run byte-identical binaries. Confirm before freezing.
7. **The melee3 hook `0x55767C5C` `.reloc` status was not re-verified this session.** The existing occupant (`build_assassin.py`) proves the 4 displaced bytes are usable — but Shield does not re-displace that hook, it appends at the tail, and the tail *was* verified. Confirm before extending anything at the hook itself.

### Known traps that apply

- ⚠ **`TTacticalCombatUnit` VMT `+0x74` = `GetResistance`, `+0x78` = `GetDamage`.** `GetXhx`/`GetYhx` live at those offsets on the **HS** classes. A cave built from the wrong field map feeds stats into the direction maths and shields the wrong arc **silently, with no crash**. This is the offset-aliasing trap the project docs warn about. Read the field bytes directly (`HS+0x04` → field, `+0x10`/`+0x11`).
- ⚠ **`[obj+0x60]` is an HS only for instance size `0x68`.** `TFastCombatUnit` is `0x64` and has a `+0x60` field that is not an HS — dereferencing it would corrupt or crash auto-resolved battles. Guard is mandatory.
- ⚠ **Ranged tail `0x55812A7B` has ZERO byte slack and leaves `EAX`/`EDX` live.** A script that assumes slack, or forgets `mov eax,esi; mov edx,[eax]` before the `jmp`, crashes on the first shot.
- ⚠ **Never clamp `[ebx]` at melee3** — shared accumulator with Monster Slaying, Assassin, Charge and Parry.
- ⚠ **Deltas are written as dwords and read back as signed bytes** by `CreateStrikeCA` (`0x55767EB7`/`0x55767EC2`). Keep within ±127.
- ⚠ **keystone `push` imm8 trap** and **`call $+5` assembling to nothing** — disassemble every cave you assemble (`--dis`); never trust the round-trip.
- ⚠ **Caves in `.dpl` must be position-independent** — the packages rebase. All calls above are `rel32` to in-module thunks; the IAT slots are loader-fixed, so nothing in the caves needs a relocation.
- ⚠ **`AoW.exe` / `AoWCompat.exe` / `AoWDevEd.exe` / `AoWEd.exe` lock the binaries.** Standing authorisation: kill them and retry, do not ask.
- ⚠ **Cave-space facts in circulating docs are stale.** `0x55822000` is occupied; `0x5580E440` is claimed by `build_combatlog_dll.py` (`LEGACY_CAVE`, `--vacate` zeroes `0x5580E440`–`0x5580ED80`) and by `build_invis_penalty.py` (`RNG_LIMIT`). Fix at source in the feasibility doc before a build script trusts them.
- ⚠ **`AoWCompat.exe` must stay in lockstep.** Neither S1 nor S2 touches an exe, so nothing to do here — but note it if the scope ever grows.

### Documentation debts to fix at source (not blockers)

- `Facing_Mechanics_Feasibility` §3/F4 proposes `0xAC` for Shield; `Caster_Abilities_Feasibility` recommends `0xAC`–`0xAF`. Neither is reserved. Record `0xB0` for Shield.
- The Parry site is `0x55767BE1` and the live magnitude is **8** (`83 2B 08`), not the 2 (vanilla) or 4 that Ghidra's `[LIVE-PATCH]` annotation records. Establish which script last re-tuned it and fix the annotation.
- The "only four free ability ids" claim is a misreading of the Caster doc's four-ability *recommendation*. There are 34 contiguous plus 21 gaps.
- The alignment-bonus attribution at melee1 (`add bl,4` @ `0x55766699`) and melee3 (`add dword [ebx],5` @ `0x55767C55/58`) is **correct** — `0x92`/`0x93`/`0xA0`/`0xA1` are Holy/Unholy Champion — but the 5-vs-4 asymmetry between the two sites is real and is a separate known defect. Do not "fix" it as part of this work.
- Cosmetic: "states 5/6/7 are the no-op exit" — `0x00409785` is the teardown epilogue, not a no-op. Vanilla at `0x55767C5C` is `BA 70 00 00 00` (5 bytes), not 4.

---

## 8. Open decisions for the user

**Q1 — When is the Shield arc evaluated: once per round, or once per strike?**
- **(a) Per round** — the link at the melee3 tail `0x55812A2E`. All strikes in the exchange are scored in one pass at `0x00409208`, *before* any facing change, so the defender's pre-attack facing governs the whole round. Consistent; comes free for auto-resolve and the AI's `CheckUnit` scoring.
- **(b) Per strike** — a link inside `TMeleeRound.CreateStrikeCA @0x55767E68`. The defender's S1 mid-exchange turn then makes the attacker's 2nd and 3rd blows frontal.
- *(a) is what §4 specs.* This changes the feel materially and is a rule decision, not an implementation detail.

**Q2 — After it retaliates, does the defender stay turned, or turn back?**
- **(a) Stay turned** *(as specced)* — one cave, no stutter; the attacker's later blows land on the new front.
- **(b) Turn back** — needs a second cave in the state-4 / exit path and will read as a visual stutter.
- Note the interaction with Q1(a): under per-round evaluation the arc is already fixed before any turn, so (a) vs (b) is **purely cosmetic**. Under Q1(b) it is mechanical.
- Also note a consequence of S1 either way: because `0x004092B4` faces the **attacker** at its target, an attacker carrying Shield **always** has the retaliation arriving on its front — its shield always works against retaliation. That may be exactly right; confirm it is intended.

**Q3 — ~~Which side?~~ ANSWERED 2026-08-26: front and front-LEFT.** Arc = `(D−F) mod 6 ∈ {0,5}` = `F` and `F−1`. Matches the conventional shield-on-the-left-arm model. Still gated on the sprite/screen handedness check (§7 items 1-2) before the constant is frozen.

**Q4 — Is +4 the intended magnitude?**
- **(a) 4** — −20 pp of hit chance, mean −18.3 pp, −27.4 % expected damage across the roster; exactly half live Parry but on every strike instead of the first only.
- **(b) 2** — −10 pp; now expressible thanks to the half-steps the 5 % conversion unlocked.
- **(c) something else.**

**Q5 — Should Shield be hero-buyable?**
- **(a) Mask `0x03FF`** (Drillmaster's, and 81 of 151 live abilities) — offered at hero level-up **and** creatable as an item. Requires adding `0xB0` to `herodlg_cats.py` `ABILITY_CATS`.
- **(b) Mask `0x37`** (Path of Sand's and Magebane's) — unit / editor / item only, never a hero upgrade.

**Q6 — Include ranged?**
- **(a) Include with the exact primitive** *(recommended)* — third cave, different register contract, ~20 extra instructions.
- **(b) Melee only (r = 1)** — halves the work; "archers must be flanked" is the cost.
- **(c) Include with `dHXtoHNfast`** — **not offered**; 29.5 % of long shots would land in the wrong sector.

**Q7 — Remove the touch-ability target re-face (`0x00409F2A`)?**
- **(a) Remove** — a webbed/entangled/turn-undead victim no longer spins to face its toucher; consistent with S1.
- **(b) Keep** — there is no retaliation on the touch path, so there is nowhere to move the turn to; this is purely aesthetic. One 6-byte reloc-free edit either way.

**Q8 — Auto-resolve: accept that Shield does nothing there?**
- **(a) Accept** — `TFastCombatUnit` has no hexes and no facing; the class guard excludes it. Cost: Shield is strictly worse in auto-resolve, which nudges players toward manual fights.
- **(b) Approximate** — substitute a party-bearing rule (`party+0x19`) for the hex arc in fast combat. Not designed here; would need its own investigation.

**Q9 — Should the AI know about Shield?**
- At the melee3 tail the −4 delta feeds `StatisticsToDV`, so the **tactical** AI's per-strike scoring sees it. At melee1 and ranged it is invisible, and the strategic combat predictor (`GetCombatValue @0x5577F9A8`) never sees it at all.
- **(a) Accept the partial visibility** *(as specced)*.
- **(b) Consistent valuation** — would need averaged mitigation at `TAbility.GetDamageValueEx` (VMT `+0xDC`, `0x5574E744`) and `fcGetDamageValueEx` (VMT `+0xE4`, `0x5574E764`). Separate piece of work.

**Q10 — Combat-log line?**
- **(a) None** — the `−4` already shows as a lowered attack number in the existing damage line.
- **(b) Bare `"Shield"`.**
- **(c) Named direction, e.g. `"Shield: front-left, -4 ATK"`** — payload capped at 127 bytes; must run the shared `_check_wire()` assertion.