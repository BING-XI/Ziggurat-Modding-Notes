# Elemental terrain heal — elementals heal moving over their element

**Status: ✅ CONFIRMED WORKING 2026-08-30** (user in-game test of v4). Script
`build_scripts/build_waterheal.py` (filename kept from v1 for continuity; output label "elemheal").
Patches **`AoWEPACK.dpl` only** — no exe patch, no AoWCompat lockstep, no `.pfs` edit. Backup
`AoWEPACK.dpl.pre-waterheal` (taken from byte-proven vanilla state; the backup gate is
vanilla-AND-absent so it is never re-minted). **Revert = `--undo`** (surgical: restores the 8 hook
bytes, zeroes the cave, touches no backup). Fully independent of the other features hooked into the
same function — see "Co-residents" below.

All addresses are AoWEPACK.dpl preferred-base VAs (base `0x55700000`, rebased at runtime → cave is
position-independent, per `[[aow1-dpl-rebasing]]`).

## What it does

Once per hex **entered** during strategic movement, on the moving unit's **own** movement only:

| Elemental | Unitres id | heals on | HP/hex | chime volume |
|---|---|---|---|---|
| Water | 227 (0xE3) | terrain Water `0x00` or cave water `0x0A` (any level; ice `0x06` is NOT water) | +2 | 50/100 |
| Air | 224 (0xE0) | **any terrain** on the surface level (`level == 0`) | +1 | 25/100 |
| Earth | 225 (0xE1) | any underground hex (`level != 0`) OR mountain overlay (any level) | +1 | 25/100 |
| Fire | 226 (0xE2) | terrain Lava `0x09` | +4 | 50/100 |

Shared rules (user rulings 2026-08-29/30):

- **Own movement only** — carried-in-a-transport movement does not heal, mirroring how Path
  abilities gate. The gate is **army-level**: an elemental in an army that contains a transporter
  counts as transported (unless it IS the transporter), even if it could swim itself.
- Heal only if `hp < max`; `SetHitPoints` clamps at max anyway. Amounts are in displayed
  (post-DAM/HP-doubling) HP.
- The Healing ability's chime plays **iff a heal actually happened** AND the hex is visible to the
  local player. **The heal itself is never fog-gated** (MP determinism — fog is only consulted for
  presentation). The sound path calls VCL RandInt on watching clients only, same as the engine's own
  presentation sounds — not a desync vector.
- Tactical-combat movement is **out of scope** (separate exe-side system,
  `TTacticalCombatUnit.MovedTo @0x41CF88` in AoW.exe — same ruling as firefeed's "tactical fire
  out"). Nature Elemental (80) excluded by ruling.

## Hook

**`0x557803BA`** in `TAbstractUnit.MovedTo @0x55780328` — the per-hex-entered chokepoint (it is the
per-hex MP-deduction site; fires once per unit per hex, see `HOWTO_PerHex_Ring_Detection.md`). At
the hook, **EBX = unit, ESI = the entered field**.

Vanilla bytes (8): `0F BE 46 14 66 83 F8 07` = `movsx eax, byte [esi+0x14]; cmp ax,7` (the
EarthWall/tunnel test on the entered terrain). Replaced by `E9 → 0x55824000` + 3 NOP. The cave
replays the displaced pair **last** — its flags feed the `jne` at the resume point — then
`jmp 0x557803C2` (flag-preserving).

⚠ **Trap: predict vanilla bytes from the file, never from mnemonics.** The planning pass predicted
`66 3D 07 00` for `cmp ax,7` — same disassembly text, wrong encoding (imm16 vs imm8 form). Caught by
byte-diffing live vs `AoWEPACK_original_backup.dpl` before patching.

⚠ Do NOT hook the `MovedTo` epilogue `0x5578051B` — owned by `build_ai_itempickup.py`
(Magebane/Shield tail-chain lesson).

## Cave — 344 B @ `0x55824000..0x55824157`

Zone `0x55823E00..0x55825200` was verified all-zero before first write; `0x55824158..0x55825200`
remains zero. No `.reloc` entries in either patched range. PIC throughout: no absolute memory
operand; globals via two `call $+5; pop` anchors; all calls rel32.

1. **Terrain/precondition fetch + entry pushes** EBX/ESI/EDI/EBP (single shared 4-pop epilogue at
   `0x55824147`; every one of the exit conditions funnels there).
2. **Transport gate** `0x55824012..0x5582403F` (anchor 1 `pop edx @0x5582400C`, classref
   `[0x557130AC]` = TArmy): owner = `[unit+4]`; `System.@IsClass` thunk `@0x557010C0`; if TArmy →
   `TArmy.Transporter @0x5578E00C` (EAX=army, **DL=0xFF** mask) → transporter ≠ 0 AND ≠ EBX ⇒ out.
   This replicates **inline** the refined truth table of `build_path_transportgate.py`'s wrapper at
   `0x5580E060` ("blocked only if the transporter isn't me") while calling the vanilla `Transporter`
   directly — so the two features are **independently undoable** (verified both ways).
   Vanilla evidence for the idiom: the Path-effect gate at `0x557803EF..0x55780418` in this same
   function (nonzero transporter ⇒ Path effects skipped).
3. **Unit identity** — the firefeed idiom: `[ebx+0x40]` → resource (null-guarded) → `[+4]` → list →
   vcall `[list_vmt+0x84]` → Unitres index. Heroes cannot misfire: max HERORES.PFS id is 55.
4. **Dispatch** `@0x55824048` on index 0xE0..0xE3 (5-byte `cmp eax,imm32` forms — no imm8
   sign-extension trap); anything else ⇒ out. Condition blocks: water `@0x55824068`, air
   `@0x5582407E`, earth `@0x5582408F`, fire `@0x558240A6`. Field bytes read: terrain `[esi+0x14]`,
   level `[esi+0x12]` (**0 = surface**; up to 8 levels), overlay `[esi+0x15]` (**0 = mountain**,
   `0xFF` = none).
5. **The EBP pack** — all four callee-saved registers were occupied (EBX unit, ESI field, EDI hp
   then anchor, EBP this), so each block sets `EBP = (chime_volume << 16) | heal`:
   `0x320002` / `0x190001` / `0x190001` / `0x320004` (Water/Air/Earth/Fire, 5-byte `BD imm32`).
   EBP survives every intervening call (Delphi callee-saved; verified through the GetHits redirect
   chain into the DAM/HP caves).
6. **HP gate** `@0x558240B5`: hp = vcall `[vmt+0xE0]` GetHitPoints, max = vcall `[vmt+0xD0]`
   GetHits. ⚠ `TUnit.GetHitPoints` is literally `mov al,[eax+0x3e]; ret` — **AL only, dirty upper
   bits**; both values are `movsx`'d before the 32-bit compare (the recorded DAM/HP dirty-bits
   lesson). `hp >= max` ⇒ out (skips heal AND sound).
7. **Heal**: vcall `[vmt+0xE4]` SetHitPoints, `EDX = movzx(bp) + hp`. The setter clamps to
   [0, GetHits] at `0x557827D4`.
8. **Fog gate (sound only, deliberately AFTER the heal)**: `TAoWHSMap.WatchingTerrain @0x55775ABC`
   — EAX = map object from `[0x558FA040]`, **DL = x** `[esi+0x10]`, **CL = y** `[esi+0x11]`
   (callee spills+movsx's the byte regs immediately, upper garbage never read), stack: **level
   `[esi+0x12]` pushed first**, then radius 1; returns AL. False ⇒ out.
9. **Chime** (anchor 2 `pop edi @0x558240E7`; `+0xD5F59` → `0x558FA040`, `+0xD5F5D` → `0x558FA044`):
   set = `[0x558FA044]` (AoWHSSet), ctl = `[set+0x80]`, ability =
   `TAbilityControl.GetAbility @0x557501C0` (EAX=ctl, **EDX=0x2F** Healing), lib = `[ability+0x18]`
   (all null-guarded) → **PlayEx**.
10. Epilogue pops, tail replay, `jmp 0x557803C2`.

Register liveness at the resume point was walked in both branch arms: everything after `0x557803C2`
redefines EAX/ECX/EDX before reading; only EBX/ESI/EDI/EBP and `[ebp-4]` are live, all preserved.

## ⭐ Reusable machinery discovered here

### PlayEx — play any ability SFX with per-call volume

`Sound.TSFXLibrary.PlayEx` thunk **`@0x55702CFC`** (impl `SoundP.dpl @0x5540605C`, `ret 0x14`):
`EAX` = SFX library, `EDX` = sound index within it, **`ECX` = volume on a 0–100 scale**
(engine callers pass 0x64 or −1 = default; 0x32 = half, 0x19 = quarter — half/quarter validated by
ear in-game 2026-08-30). Five stack args, **first-pushed = loop flag** (0 = one-shot), then delay,
1, 0, 0 (engine delays: 0x1E, RandInt(15); 0 = immediate). Reference sites: `0x557B1A85`,
`0x557C6420`; the plain-`Play` idiom is `THealingCA.Play @0x5576BDB8`. To get an ability's library:
`[GetAbility(id) + 0x18]`. ⚠ Do NOT use `Sound.SetSFXVolume` for per-sound volume — it is
process-global.

### Mountain is an OVERLAY, not a terrain

`[field+0x15]` overlay byte: **0 = mountain** (`TMountainMO.GetOverlay @0x557A2DC8` clamps
non-negative → 0), **0xFF = no overlay**. One compare covers surface and underground mountains.
Adversarially proven that plain hexes carry 0xFF, not 0x00: the movement-cost consumer
`TMoveControl.DefaultMoveOnMovePointProc @0x557454D8` does `movsx` on `+0x15` and indexes
`table[terrain*16 + overlay + 1]` (+1 column bias so −1 = none lands on the base column) — if plain
hexes were 0 they'd resolve to the Mountain column, which is 0xFF-impassable for Walking, i.e. the
whole map would be unwalkable.

### Other field-struct facts confirmed

`[field+0x10/0x11/0x12]` = x/y/level (level 0 = surface, editor sanity allows up to 8 levels);
`[field+0x14]` = terrain; `WatchingTerrain` is the engine's own local-visibility test for
presentation effects (mirrored from the spell-sound site `0x557B1A36..57`).

## Version history (all in-place rewrites, per the no-revert-retune convention)

- **v1** (2026-08-29): Water Elemental +2 on water, chime 50%.
- **v2**: + transport gate (user ruling: own movement only, like Path abilities).
- **v3** (2026-08-30): per-elemental dispatch — Air/Earth/Fire added.
- **v4**: per-elemental chime volume via the EBP pack (25% Air/Earth).

The script recognises vanilla/v1/v2/v3/v4 by regenerating each version's exact cave bytes;
`--apply` rewrites in place from any older state (growth zone must verify zero) and refuses
unrecognised bytes; a corrupt state refuses dry/apply/undo alike.

## Co-residents in `TAbstractUnit.MovedTo` — all verified untouched both ways

`build_path_transportgate.py` (retargeted `Transporter` call @`0x55780407` → wrapper `0x5580E060`),
`build_ai_itempickup.py` (epilogue hook @`0x5578051B`), `build_path_outerring.py` (@`0x5578041E`).
Undo order: none — this feature chains with nothing.

## Failed/rejected approaches (don't retry)

- **Delivering the heal via `ExecuteDamageRole`** (the firefeed route): imports a to-hit roll and a
  Defence dependency (the ⭐ lesson in `Fire_Heals_FireUnits_Design.md`). This heal is a plain
  `SetHitPoints` write.
- **`Sound.SetSFXVolume` for the half-volume chime**: process-global, ducks everything.
- **Fog-gating the heal**: never — MP determinism. Only the sound consults `WatchingTerrain`.
