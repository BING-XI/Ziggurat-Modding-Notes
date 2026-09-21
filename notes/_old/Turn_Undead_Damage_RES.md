# Turn Undead damage = 0.5 × (ability level) × (caster RES)

**Status: CONFIRMED WORKING (2026-07-16)** — user validated in-game. Build:
`build_scripts/build_turnundead_res.py` (`--apply`). Binary: `AoWEPACK.dpl`.
**Revert: ⚠ not by snapshot.** `AoWEPACK.dpl.pre-turnundead` sits in the **game root** (dated
2026-08-20; re-verified 2026-09-01 — `Modding Resources/backups/` no longer exists, so any doc
pointing there is stale). **38 newer `AoWEPACK.dpl.pre-*` snapshots** post-date it, so restoring it
would destroy that many later layers. Derive that count fresh — never quote it:

```bash
ls -la --time-style=+"%Y-%m-%d %H:%M" AoWEPACK.dpl.pre-* | awk '$6" "$7 > "2026-08-20 00:57"' | wc -l
```

The script has no `--undo` mode; to remove the feature, restore its patch sites to the original bytes
listed below and zero its cave, verify-before-write.

⚠ **This feature has been SUPERSEDED IN PART — read `TurnUndead_EvilCommand_Design.md` §4a-ter first.**
Applied 2026-09-01 (untested) by `build_scripts/build_turnundead_resroll.py`: the attacker term of the
damage roll is no longer `GetTouchAttack(level)` (the flat 9/10/11/12 table) but
**`casterRES × (4 + level) / 5`** — i.e. caster Resistance scaled 1 / 1.2 / 1.4 / 1.6 for Turn Undead
I–IV — making roll 2 an opposed `casterRES − targetRES` check.

- Combat: 6 bytes at **`0x5576B57C`** → `call cave_atk @0x55831000` + `nop`.
- Info card: 6 bytes at **`0x5580E31B`**, *inside* the Part-2 cave described below, → `cave_info
  @0x55831030` + `nop`, so displayed ATK still equals what is rolled.

The DAM formula below (`0.5 × level × casterRES`) is **unchanged** and still current. But note the
two now compound: caster RES drives both the damage rating *and* the roll's ramp position, so damage
output scales with RES far more steeply than this doc's tables suggest. **Those tables predate the
change — do not quote them as live.**

## Request
Turn Undead's ATK and DAM were both pure functions of the *ability level*. Change the **damage** to
scale with the caster's RES. Current formula (after the 2026-07-16 `0.5·lvl·RES` revision — this
superseded the earlier `level×RES` and `level×max(RES−3,1)` versions):

> **DAM = clamp( round(0.5 × level × RES),  127 )**,  RES = the resistance of the unit using the ability.

Implemented in integer math as `(level·RES + 1) >> 1` (round half-up; RES 0 ⇒ 0). ATK is deliberately
left on the vanilla level table (9..12). Two parts: **(1)** the damage actually dealt in combat,
**(2)** the ability info-card's displayed DAM, so the shown number matches what is dealt.

| RES | L1 | L2 | L3 | L4 |
|---|---|---|---|---|
| 2 | 1 | 2 | 3 | 4 |
| 4 | 2 | 4 | 6 | 8 |
| 6 | 3 | 6 | 9 | 12 |
| 8 | 4 | 8 | 12 | 16 |
| 10 | 5 | 10 | 15 | 20 |
| 15 | 8 | 15 | 23 | 30 |

## Vanilla mechanics (TTurnUndeadAbility, AoWEPACK.dpl)
Turn Undead is a **touch attack** (class `TTurnUndeadAbility`, VMT ptr `0x5571FDFC`). Its base ATK/DAM
are level lookups:

| method | addr | level 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| `GetTouchAttack` (ATK) | `0x5576B1F4` | 9 | 10 | 11 | 12 |
| `GetTurnUndeadDamage` (DAM) | `0x5576B214` | 4 | 8 | 12 | 16 |

`GetTurnUndeadDamage` = **level × 4**. It receives only `edx = level` (no caster), so it cannot see
RES on its own — the fix must go at a *call site* where the caster is in scope.

### The actual-damage path
`fcExecuteCombatCommand @0x5576B5C0` → **`CreateTurnUndeadCA @0x5576B528`** bakes the CA's stats, then
`TCombat.ExecuteCombatAction` → `TTurnUndeadCA.Execute @0x5576AC00` → `TDamageCA.Execute` applies them.
Inside `CreateTurnUndeadCA` (verified by tracing; `ESI`=attacker combat obj, `EBP`=target — proven by the
to-hit calc `ESI.GetAttack[vmt+0x6c] − EBP.GetDefense[vmt+0x70]`):

```
5576B56C  call [ESI.vmt+0xb0]     ; GetAbilityLevel(TurnUndead) -> level
5576B57C  call [this.vmt+0x10c]   ; GetTouchAttack(level)      -> CA attack   (UNCHANGED)
5576B589  call 0x5576B214         ; GetTurnUndeadDamage(level) -> CA damage    <-- REPOINTED
```

At `0x5576B589`: `EDX = level (1..4)`, **`ESI = attacker combat object = the unit using the ability`**,
`EAX = this`. The caller needs `ESI/EDI/EBP/EBX` preserved afterward.

### Why 127 clamp
`TDamageCA.GenerateEx @0x55729C98` reads the CA damage as **`movsx ecx, byte [ebp+0x10]`** — a *signed*
byte. Damage > 127 flips negative. `level(≤4) × RES(realistically ≤~30)` stays well under 127, so the
clamp is invisible in practice; it only guards the pathological buffed-RES corner.

## The patch — Part 1: damage dealt
Repoint the 5-byte `call GetTurnUndeadDamage` @ `0x5576B589` → cave `0x5580E2A0`
(`e8 86 fc ff ff` → `e8 12 2d 0a 00`). Cave (36 B, register/immediate-only ⇒ position-independent):

```
5580E2A0  push esi                 ; preserve caster for the caller
5580E2A1  push edx                 ; save level
5580E2A2  mov  eax, esi
5580E2A4  mov  edx, [eax]
5580E2A6  call [edx+0x74]          ; TCombatUnit.GetResistance -> AL (no args)
5580E2A9  movzx eax, al            ; eax = casterRES (0..255)
5580E2AC  pop  edx
5580E2AD  movzx edx, dl            ; edx = level
5580E2B0  imul eax, edx            ; eax = level * RES
5580E2B3  add  eax, 1              ; round half-up:
5580E2B6  shr  eax, 1             ;   eax = (level*RES + 1) >> 1
5580E2B8  cmp  eax, 0x7f
5580E2BB  jle  0x5580e2c2
5580E2BD  mov  eax, 0x7f           ; clamp to signed-byte max
5580E2C2  pop  esi
5580E2C3  ret
```

**RES source** = combat-object `VMT+0x74` = `TCombatUnit.GetResistance` (forwards to the strategic unit's
`GetResistance` @ strat `VMT+0xcc`); takes no args, returns AL. This is the caster's *effective* RES
(includes buffs/debuffs), which is the natural reading of "the RES attribute of the unit."
`add eax,1; shr eax,1` is round-half-up integer `÷2` (`shr` is safe — the value is always ≥ 0).

The result is the **damage rating** fed to `ExecuteDamageRoleEx`; final HP loss still rolls that rating vs
the *target's* RES, exactly as vanilla.

## The patch — Part 2: displayed DAM (info card)
`GetCombatInfo @0x5576B234` builds the ability info-card struct (`+0`=byte, `+1`=ATK, `+2`=DAM,
`+3`=type word, `+5`=1) and calls `GetTurnUndeadDamage @0x5576B257` for the DAM. The owner isn't in a
register there (passed in `EDX`, consumed by `GetLevel`, then lost), so instead of a surgical repoint the
whole function is **replaced**: a 5-byte `jmp` at its entry (`53 56 57 8b d9` → `e9 c7 30 0a 00`)
redirects to **cave `0x5580E300`** (101 B), which keeps the owner in `EBP` throughout:

```
5580E300  push ebx/esi/edi/ebp
          mov ebx,ecx(outbuf)  mov esi,eax(this)  mov ebp,edx(owner)
          <edx=owner>  call [this.vmt+0x70]   -> edi = GetLevel(owner)
          <edx=level>  call [this.vmt+0x10c]  -> [ebx+1] = GetTouchAttack(level)   (ATK unchanged)
          test ebp,ebp; jz -> dmg=0
          mov eax,ebp; call [owner.vmt+0xcc]  -> AL = owner GetResistance
          movzx eax,al; imul eax,edi(level); add eax,1; shr eax,1  -> round(0.5*level*RES)
          clamp 0x7F -> [ebx+2] = DAM
          mov ax,0x0040; mov [ebx+3],ax   mov byte[ebx+5],1   mov al,0x02; mov [ebx],al
          pop ebp/edi/esi/ebx; ret
```

The two struct constants (`word 0x0040` @`0x5576B278`, `byte 0x02` @`0x5576B27C`) are embedded as
immediates ⇒ no absolute data reads ⇒ position-independent. Owner RES via strategic `VMT+0xcc` equals the
combat path's `ESI.GetResistance` (combat `VMT+0x74` forwards to it), so **display == damage dealt**. The
original body from `0x5576B239` is now dead code. Null-owner ⇒ DAM 0 (matches vanilla `GetLevel(nil)=0`).

## Scope / what is NOT changed (by design)
`GetTurnUndeadDamage`'s **third** caller is left alone:
- `GetOffensiveStrength @0x5576AEDA` — AI unit-strength heuristic; damage there is already **capped at 5**
  (`if dmg>5: dmg=5`), so `level×RES` would just always clamp — not worth changing.
- The separate DV/predictor preview (`GetDamageValueEx @0x5576B2F4` / `fcGetDamageValueEx @0x5576B424`,
  ability `VMT+0xD8/0xDC/0xE4`) uses a different float×stat formula, not `GetTurnUndeadDamage` — untouched.
  (Affects only the AI's pre-battle odds estimate, never the damage actually applied.)

## Key addresses
- `TTurnUndeadAbility` VMT ptr `0x5571FDFC`; combat-obj VMT (`TCombatUnit` @ `0x55715A94`):
  `+0x6c`=GetAttack `+0x70`=GetDefense **`+0x74`=GetResistance** `+0x78`=GetDamage `+0xa8`=GetAbilityEnabled
  **`+0xb0`=GetAbilityLevel**. Strategic-unit VMT (TUnit/TAbstractUnit/THero/TAdjustableUnit):
  `+0xc0`=GetAttack **`+0xcc`=GetResistance**.
- Part 1 (combat): hook `0x5576B589` (call) · cave `0x5580E2A0` (36 B, ends `..E2C3`).
- Part 2 (display): hook `0x5576B234` (entry jmp) · cave `0x5580E300` (101 B, ends `..E364`).
- Both caves in the free tail zone past slayer `cave_rng` (@`..E287`); avoid the documented occupied
  bands (`0x5580C000–C3FF`, raze caves `..CE90–D2E0`, session caves `..D900+`).
- **History / re-tuning:** the formula has been revised twice (`level×RES` → `level×max(RES−3,1)` →
  `0.5×level×RES`). Cave sizes/addresses shift with each formula, so re-applying over an old layout
  would trip the free-space guard and/or leave stale bytes.
  ⚠ **The old instruction here was "revert to `.pre-turnundead` first, then `--apply`". DO NOT** — the
  snapshot had seven features stacked on it by 2026-07-21 and **38 by 2026-09-01**; restoring it
  destroys all of them. The count only ever grows, so derive it (command at the top of this doc)
  rather than trusting any figure written here.
  **Re-tune by rewriting the caves in place instead:** make the script accept *either* the installed cave
  bytes *or* the new ones at `..E2A0`/`..E300`, overwrite, assert the growth zone is still zero, and take
  a fresh `.pre-<feature>` backup. See `build_scripts/build_invis_penalty.py` for the pattern and
  `re_tools/revert_audit.py` to re-check layering. Part 2 sits at `..E300` (not adjacent `..E2C0`) so the
  Part 1 cave has room to grow.

## Failed approaches / notes
- Editing `GetTurnUndeadDamage` itself is impossible for this feature — it only receives the level, never
  the caster. Must hook at the call site where `ESI` = attacker.
- Keystone `ks.asm()` rejects `;` inline comments in the asm string (KS_ERR_ASM_INVALIDOPERAND) — keep the
  cave source comment-free.
