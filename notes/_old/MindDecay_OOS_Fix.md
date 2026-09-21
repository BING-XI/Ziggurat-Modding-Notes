# Mind Decay — unconditional RNG draw (MP determinism) + the nil check vanilla lacks

> **Status: 🔨 APPLIED, UNTESTED (2026-09-03).** Written to the live `AoWEPACK.dpl`, verified
> byte-for-byte, cave disassembled and read. **Nobody has played it, and the multiplayer half needs
> two machines.** Promote to `✅ CONFIRMED WORKING` only on the user's test (§8).

| | |
|---|---|
| script | `build_scripts/build_minddecay_oos.py` → `AoWEPACK.dpl` (that binary only) |
| backup | `AoWEPACK.dpl.pre-minddecayoos` (taken 2026-09-03 from a file proved free of this feature) |
| revert | `python build_scripts/build_minddecay_oos.py --undo` — surgical, writes immediately, touches no backup |
| couplings | **none.** No shared cave, no shared hook, no ordering constraint with any other feature |
| rule it implements | `RNG_Lockstep_Rule.md` §2, "inside combat the DRAW COUNT is the invariant" |

`VA = file_offset + 0x55700C00` (CODE). ⚠ The script's own docstring still opens
`STATUS: built and dry-run verified, NOT APPLIED` — that line is stale; the live DLL says otherwise
(§7).

---

## 1. The defect, and that it is vanilla's

AoW1 has two generators sharing one seed variable. `AoWE.TCombat.Execute @0x557282C8` is a
one-liner — `System.RandSeed := TAoWHSMap.Random(map, $FFFFFF)` — so a battle **re-anchors the raw
seed from one synchronised draw** and then runs the whole fight off raw draws, deterministically, on
every peer.

The consequence: **raw combat draws are invisible to the out-of-sync comparator (which watches
`[map+0x230]`), but they only reproduce across machines if every peer consumes the SAME NUMBER of
draws.** A *conditional* raw draw therefore diverges silently — different to-hit results, different
deaths, and an OOS dialog raised much later and far from the cause.

`CombatSpells.TMindDecay.CreateCA @0x557F85DC` has the widest such surface of any combat spell. Its
one `HitRole` call sits behind **five** gates, four of which dereference the target's strategic unit
`[combatunit+0x4C]` (by contrast `TSlow` / `TEntangle` gate on a single check through the combat
unit's own virtuals):

| # | gate | reached via |
|---|---|---|
| 1 | `IsClass(target, TCombatUnit)` | `0x557010C0` (thunk `ff 25 bc b6 8f 55` → VCL30 `System.@IsClass`); classref cell `0x55715A54` → VMT `0x55715A94` |
| 2 | `u.GetUnitType() == 2` | `u = [target+0x4C]`; `[u_vmt+0x114]` |
| 3 | `u.GetRace() == 0x0B` | `[u_vmt+0xA4]` |
| 4 | `u.GetAbilityEnabled(0x81)` (Animated) | `[u_vmt+0x148]` |
| 5 | `IsClass(u, TLeader)` | classref cell `0x557121F8` → VMT `0x55712238` |

⚠ **`CombatSpells.TMindDecay.CreateCA 0x557F85DC..0x557F869C` is byte-identical to
`AoWEPACK_original_backup.dpl`** — re-verified 2026-09-03. The whole gate chain is vanilla on our
DLL. **This is a stock AoW1 defect; neither Ziggurat nor Inioch's tree introduced it.** Assume other
conditional combat draws exist; `HitRole`'s callers are the place to look (list in
`RNG_Lockstep_Rule.md` §2).

**Second defect, same function:** vanilla dereferences `[target+0x4C]` at `0x557F862C` guarded only
by gate 1. A combat unit with no strategic twin AVs there. `TCombatUnit` instance size is 92
(`0x5C`) so `+0x4C` is in bounds — the field is simply allowed to be nil.

---

## 2. The fix — hoist the DRAW, gate only the STORE

```
<the same five gates, no early exit>   -> eligible = 0/1
eligible ? res = target.GetResistance() : res = 0
ALWAYS   eax = [spell+0x34] - res ; call HitRole      (exactly one @RandInt)
eligible ? [ca+0x14] = al : leave it 0, as vanilla
```

* **Eligible target** — identical outcome, identical draw order, and an identical call graph: the
  gate virtuals and `GetResistance` are called exactly where vanilla calls them.
* **Ineligible target** — one extra `@RandInt` is consumed and discarded, **uniformly on every
  machine**, since every peer runs this same DLL. No balance effect; the stream is random.
* Plus the nil check on `[target+0x4C]`, which falls through to "ineligible" instead of AVing.

**Honest scope.** This removes the one concrete, mechanically verifiable RNG asymmetry unique to
Mind Decay. The gates read synced state, so on two correctly-synced machines they *should* already
agree — meaning this stops a divergence from **cascading** through every later combat roll, and is
**not** a proven root-cause fix for any specific reported desync. It cannot make things worse (the
extra draw is uniform on every peer) and it removes a real crash path on the way. Deliberately not
done: anything else in the OOS investigation. `TSlow` / `TEntangle` / the other `HitRole` callers
are untouched.

---

## 3. ⚠ Why only the CALL is hoisted, and not `GetResistance` — FOR INIOCH

Draw-count invariance depends on the **number of `HitRole` calls**, not on their inputs.
`AoWE.HitRole @0x55725D98` is straight-line with exactly one unconditional `call 0x55701080`
(`@RandInt`); its two forward branches only clamp the chance to 10..90, and the draw is
`@RandInt(100)` whatever the input. So passing a different (and discarded) input on the ineligible
path costs exactly one draw and nothing else. **The script re-asserts that property against the live
bytes at write time** and refuses to patch if `HitRole` ever stops making exactly one `@RandInt`
call.

⚠⚠ **The roll's other input is NOT safe to hoist.** The resistance comes from VMT slot `+0x74`, and
it is true that the slot is a `TCombatObject` base-class slot — **but `TCombatUnit` overrides it,
and the override is nothing but a forward through the strategic unit:**

```
AoWE.TCombatUnit.GetResistance @0x557254A8      (VMT 0x55715A94, slot +0x74)
  557254A8  8b 40 4c           mov  eax, [eax + 0x4C]      <-- THE STRATEGIC UNIT
  557254AB  8b 10              mov  edx, [eax]
  557254AD  ff 92 cc 00 00 00  call [edx + 0xCC]           ; TUnit.GetResistance
  557254B3  c3                 ret
AoWE.TCombatObject.GetResistance @0x55726864  =  33 c0 c3   (xor eax,eax; ret)   -- harmless
```

Calling `GetResistance` unconditionally would access-violate on **exactly the nil-`[target+0x4C]`
case the new nil check exists to fix**, and would additionally call `TUnit.GetResistance` on a path
where vanilla never calls it.

⚠⚠ **Inioch's shipped `Inioch/share6/patch scripts/build_minddecay_oos.py` hoists `GetResistance`
out of the gate**, on the stated premise that "resistance comes from the target's own VMT+0x74 …
NOT from `[target+0x4C]`". **The premise is false**, as shown above — and his tree and ours agree
**byte-for-byte** on `0x557254A8` (re-checked live and pristine, 2026-09-03). His version therefore
carries a latent AV on any combat unit with a nil strategic twin: the very crash his own nil check
was added to remove. Ours hoists **only the `HitRole` call** and substitutes `res = 0` on the
ineligible path — same objective, strictly smaller behavioural delta. **Worth sending back to him.**

---

## 4. The hook site — chosen because it is reloc-free

```
557F861B  8b c3               mov  eax, ebx              <- left intact
557F861D  8b 15 54 5a 71 55   mov  edx, [0x55715A54]     <- left intact
557F8623  e8 98 8a f0 ff      call 0x557010C0            <- becomes `jmp cave` (5 for 5)
```

Patch: `0x557F8623` `e8 98 8a f0 ff` → `e9 d8 99 04 00` (`jmp 0x55842000`). A `call rel32` carries
no base relocation, so **the `.reloc` directory is byte-identical before and after `--apply`**.
There are no orphan bytes (5 for 5), and vanilla loads the `TCombatUnit` classref for us, so the
cave needs one PIC reference instead of two.

⚠ **REJECTED ALTERNATIVE — `0x557F861B`. Do not "improve" this back.** Hooking the two instructions
above instead (the `je` target from `0x557F8613`) displaces the imm32 of that `mov`, which carries a
**type-3 HIGHLOW base relocation at `0x557F861F`** — inside the five bytes a jmp would overwrite.
Verified on the live DLL, 2026-09-03: scanning `.reloc` over `0x557F8600..0x557F8640` returns
**exactly one entry, `0x557F861F` type 3**, and **none** inside `0x557F8623..0x557F8627`. The loader
would apply that fixup on top of our rel32 on any rebased load, and `AoWEPACK.dpl` never loads at
its preferred base — this project's most expensive bug class ("crashes on his machine, not mine,
identical files"). It *can* be handled by neutralising the entry type 3 → 0 on apply and restoring
it on undo, and an earlier revision of this script did exactly that and round-tripped cleanly. It
was dropped anyway: **eliminating the category beats handling it correctly.** Inioch's script uses
that site and does the reloc surgery; ours does not need to.

⚠ **The cave depends on the two instructions above the hook.** It is entered with `EAX` = target and
`EDX` = the `TCombatUnit` classref, both set up by vanilla at `0x557F861B..0x557F8622`, and its
first instruction is the `IsClass` call it displaced. The script pins those 8 bytes
(`8b c3 8b 15 54 5a 71 55`) on every run and refuses to write if anything else has hooked them.

**Branch sweep** (byte-aligned `E8`/`E9`/`0F8x`/`7x`/`EB` scan of the whole CODE section): nothing
anywhere branches into `0x557F8623..0x557F8627`, so those 5 bytes are entered only by fall-through
from `0x557F861D`. (The `je` at `0x557F8613` lands on `0x557F861B`, which is left intact.)
`0x557F8628..0x557F868E` becomes unreachable; its only inbound branches come from within itself. The
shared tail at `0x557F868F` stays live and is where the cave returns.

### Version pins asserted on every run

| VA | bytes | why |
|---|---|---|
| `0x557F861B` | `8b c3 8b 15 54 5a 71 55` | the cave's entry state (load-bearing, not decoration) |
| `0x557F8628` | `84 c0` | dead once hooked, but pins the build |
| `0x557F868F` | `8b c6 5f 5e 5b 59 5d c2 04` | the tail the cave returns to |
| `0x557010C0` | `ff 25 bc b6 8f 55` | the `@IsClass` thunk |
| `0x55725D98` | `53` | `HitRole` entry, plus the one-`@RandInt` assertion |

Instance sizes checked: `TCombatUnit` 92 (`+0x4C` in bounds), `TMindDecay` 64 (`+0x34` in bounds),
`TMindDecayCA` 28 (`+0x14` in bounds).

---

## 5. `cave_mdroll` @ `0x55842000` — 171 bytes in a 256-byte reservation

Entry: `EAX` = target combat object, `EDX` = `TCombatUnit` classref; `EBX` = target, `ESI` = the
`TMindDecayCA`, `EDI` = the `TMindDecay` spell, `EBP` = the caller frame. EBX/ESI/EDI/EBP survive
every call below (Delphi register convention; vanilla relies on exactly that across the same calls).
Frame: `[esp+0]` = PIC load delta, `[esp+4]` = the eligible flag.

```
55842000 e8 bb f0 eb ff          call 0x557010c0            ; the displaced @IsClass
55842005 83 ec 08                sub  esp, 8
55842008 e8 00 00 00 00          call 0x5584200d            ; PIC anchor  (+0x0D)
5584200D 5a                      pop  edx                   ; pop EDX, not EAX: AL holds IsClass
5584200E 81 ea 0d 20 84 55       sub  edx, 0x5584200d
55842014 89 14 24                mov  [esp], edx            ; park the load delta
55842017 c7 44 24 04 00 00 00 00 mov  dword [esp+4], 0      ; eligible = 0
5584201F 84 c0                   test al, al
55842021 74 58                   je   0x5584207b            ; gate 1
55842023 8b 43 4c                mov  eax, [ebx + 0x4c]
55842026 85 c0                   test eax, eax
55842028 74 51                   je   0x5584207b            ; THE NIL CHECK vanilla lacks
5584202A 8b 10                   mov  edx, [eax]
5584202C ff 92 14 01 00 00       call [edx + 0x114]         ; GetUnitType
55842032 3c 02                   cmp  al, 2
55842034 74 45                   je   0x5584207b            ; gate 2
55842036 8b 43 4c                mov  eax, [ebx + 0x4c]
55842039 8b 10                   mov  edx, [eax]
5584203B ff 92 a4 00 00 00       call [edx + 0xa4]          ; GetRace
55842041 0f be c0                movsx eax, al
55842044 66 83 f8 0b             cmp  ax, 0xb
55842048 74 31                   je   0x5584207b            ; gate 3
5584204A 8b 43 4c                mov  eax, [ebx + 0x4c]
5584204D ba 81 00 00 00          mov  edx, 0x81             ; Animated
55842052 8b 08                   mov  ecx, [eax]
55842054 ff 91 48 01 00 00       call [ecx + 0x148]         ; GetAbilityEnabled
5584205A 84 c0                   test al, al
5584205C 75 1d                   jne  0x5584207b            ; gate 4
5584205E 8b 43 4c                mov  eax, [ebx + 0x4c]
55842061 8b 14 24                mov  edx, [esp]
55842064 8b 92 f8 21 71 55       mov  edx, [edx + 0x557121f8]   ; TLeader classref, delta-relative
5584206A e8 51 f0 eb ff          call 0x557010c0
5584206F 84 c0                   test al, al
55842071 75 08                   jne  0x5584207b            ; gate 5
55842073 c7 44 24 04 01 00 00 00 mov  dword [esp+4], 1      ; eligible = 1
5584207B 31 d2                   xor  edx, edx              ; res = 0
5584207D 83 7c 24 04 00          cmp  dword [esp+4], 0
55842082 74 0a                   je   0x5584208e
55842084 89 d8                   mov  eax, ebx
55842086 8b 10                   mov  edx, [eax]
55842088 ff 52 74                call [edx + 0x74]          ; GetResistance -- eligible path ONLY
5584208B 0f be d0                movsx edx, al
5584208E 0f be 47 34             movsx eax, byte [edi + 0x34]   ; the spell's strength constant
55842092 29 d0                   sub  eax, edx
55842094 e8 ff 3c ee ff          call 0x55725d98            ; HitRole -- ALWAYS, exactly one draw
55842099 83 7c 24 04 00          cmp  dword [esp+4], 0
5584209E 74 03                   je   0x558420a3
558420A0 88 46 14                mov  [esi + 0x14], al      ; the STORE, gated
558420A3 83 c4 08                add  esp, 8
558420A6 e9 e4 65 fb ff          jmp  0x557f868f            ; the shared vanilla tail
```

**PIC.** One `call $+5 / pop edx / sub edx, <anchor VA>` at `+0x0D`, parked in a stack slot; the
`TLeader` classref cell is reached as `[delta + 0x557121F8]`. ⚠ **`pop edx`, not `pop eax`** — AL
carries the `IsClass` result at that point. Every call/jmp is rel32 within the same image; the
script asserts with capstone that no instruction has a bare `[0x........]` absolute memory operand,
and that no drive-letter path is baked in.

**Cave zone** `0x55842000..0x55843000`, exclusive. All zero before the first apply, no `.reloc`
entry anywhere in `0x55830000..0x55850000`, claimed by no other build script
(`grep -ri 55842 build_scripts/` → no hits), sitting inside the `0x558385ED..0x558E7918` zero run.
Nothing branches into it and no absolute dword constant in CODE points into it.
`0x55842100..0x55843000` is asserted still zero on every run — that is the headroom the 256-byte
reservation may grow into.

---

## 6. ⚠ Two live-vs-pristine deltas a future session will otherwise trip on

Both re-measured 2026-09-03 by byte-diff against `AoWEPACK_original_backup.dpl`.

**1. `AoWE.HitRole @0x55725D98` IS MODDED on our DLL** by `build_hitslope5.py`:

```
pristine  53 8b d8 8b c3  03 c0 8d 04 80  83 c0 32 ...   ; add eax,eax ; lea eax,[eax+eax*4]  = x10
live      53 8b d8 8b c3  90 90 6b c0 05  83 c0 32 ...   ; nop ; nop ; imul eax,eax,5         = x5
```

That is the 10 pp → 5 pp to-hit slope conversion. **The pristine decompile is the wrong reference
for that function** (`CLAUDE.md`, "the live game is on a 5 % scale"). What this patch depends on is
unaffected: still straight-line, still exactly one unconditional `@RandInt(100)`, still clamped
10..90, two forward clamp branches, neither of which skips the draw. The script prints the measured
counts on every run:
`[chk ] HitRole @55725D98: 1 unconditional @RandInt, 2 fwd clamp branches (none skips the draw)`.

**2. `CombatSpells.TMindDecay.Create` IS MODDED (3 bytes) even though `CreateCA` is vanilla:**

| VA | pristine → live | field |
|---|---|---|
| `0x557F8581` | `05` → `0C` | `[spell+0x34]` — the strength constant **this roll consumes** (DAM/HP doubling, `DamHP_Double_Decisions.md`) |
| `0x557F8598` | `0C` → `08` | `[spell+0x39]` |
| `0x557F859C` | `03` → `04` | `[spell+0x3A]` |

`[spell+0x34]` is still a compile-time constant written in `Create` and never derived from the
target, so the hoist is unaffected — the cave simply reads whatever `Create` stored, exactly as
vanilla does.

---

## 7. RNG audit — and why the count does not move

The cave calls `HitRole`, which is a **caller** of the RNG, not an RNG entry point, so
`rng_audit.py --owners` reports the same site total. Measured 2026-09-03: **24 modded sites**, none
of them in `0x55842xxx`. The draw stays **RAW**, which is **correct**: this is tactical combat,
riding the seed `TCombat.Execute` re-anchored.

⚠ **Do NOT "fix" it to SYNCED.** A synced draw here would trip the `GetSynchronised` guard *and*
perturb `[map+0x230]`. The point of this patch is draw-count symmetry, not changing the generator.

⚠ **`rng_audit.py` cannot see this class of bug at all.** It matches references to the RNG *entry
points*; a cave that reaches the generator through a caller like `HitRole` adds no site and the
count does not move. The audit proves you picked the right generator, not that your draw count is
symmetric. Full reasoning: `RNG_Lockstep_Rule.md` §2, "the second rule".

### Verification already done (does NOT make it confirmed)

* Re-run with no arguments: `hook 557F8623 ours e9 d8 99 04 00`, `cave 55842000 ours (171 B of code
  in a 256 B reservation; 55842100..55843000 zero)`, `[= ] already applied -- chain intact`.
* All five version pins verified; `CreateCA` byte-identical to pristine; the two classref cells
  resolve to VMTs whose names read `TCombatUnit` and `TLeader`.
* Cave disassembled and read end to end (§5) — per the keystone `push imm8` trap, an assembled cave
  is never trusted on the round trip alone.
* `.reloc` untouched by design; the one nearby entry (`0x557F861F` type 3) is outside the patched
  run.

---

## 8. What still needs the user's in-game test

1. **Cast Mind Decay on a valid target** (a living, non-Animated, non-Leader, non-race-0x0B combat
   unit) — it must behave exactly as before: same chance to land, same effect, same combat log.
2. **Cast it on each ineligible class** — a Leader, an Animated unit, a race-`0x0B` unit, a
   `GetUnitType == 2` target — nothing must happen, and nothing must crash. This is the path that
   now consumes and discards a draw.
3. **Cast it on a combat unit with no strategic twin** if one can be produced (a summoned or
   scripted combatant): vanilla AVs there, this must not.
4. **A long tactical battle with several Mind Decays** — no drift in unrelated to-hit results, no
   crash, no "Invalid AoWHSMap.Random use" popup.
5. **Auto-resolve** as well as manual tactical combat.
6. **The MP half needs two machines**, both running this DLL: a battle in which Mind Decay is cast
   at least once on an ineligible target must not desync. This is the only test that exercises the
   actual point of the patch.
