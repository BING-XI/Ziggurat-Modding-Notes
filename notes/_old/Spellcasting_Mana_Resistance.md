# Hero mana generation = Resistance × Spellcasting level

**Status: CONFIRMED WORKING (2026-08-27)** — user-tested in game.
Script: `build_scripts/build_spellcast_manares.py` · Binary: `AoWEPACK.dpl` **only** ·
Backup: `AoWEPACK.dpl.pre-spellcastmanares` · **Revert: `--undo`** (surgical, touches no backup).

A hero's per-turn mana income was a flat five-entry table keyed on Spellcasting level. It now
scales with the hero's Resistance as well:

| | I | II | III | IV | V |
|---|---:|---:|---:|---:|---:|
| vanilla (`level*5 + 5`) | 10 | 15 | 20 | 25 | 30 |
| Ziggurat, until 2026-08-27 | 10 | 20 | 40 | 60 | 90 |
| **now** | \|—— `level × RES` ——\| | | | | |

Worked values: RES 4 → 4/8/12/16/20 · RES 6 → 6/12/18/24/30 · RES 8 → 8/16/24/32/40 ·
RES 12 → 12/24/36/48/60 · RES 20 → 20/40/60/80/100 · RES 40 (the clamp) → 40/80/120/160/200.

At the chassis Resistances the game actually ships (4–12, see below) this is a **net nerf** against
the old table and lands near *vanilla* levels; it only overtakes 10/20/40/60/90 from about RES 18.
The user chose the 1× multiplier deliberately after seeing a 3× table.

---

## 1. How hero mana income is produced

Mana income is **power generation**. The path, all in `AoWEPACK.dpl`:

```
THero.SetPlayer  @0x55787388  \  register a THeroPowerSource with
THero.Activate   @0x55787512  /  TPlayerMagicControl.RegisterPowerSource @0x5577D3C0
TPlayerMagicControl.GetPower  @0x5577CA00   sum Power() over TPowerSourceList
  THeroPowerSource.Power      @0x557867D0   -> hero.vtable[+0x134]
    TLeader.GetPowerGeneration @0x5578B43C  (THero's slot @0x557885E4 tail-calls this)
        GetAbilityEnabled(0x34) via vtable[+0x148]     item-aware
        GetAbilityLevel(0x34)   via vtable[+0x144]     item-aware
        call 0x557885EC                               <-- the only patched bytes
GetManaIncome @0x5577C95C -> GetNetPowerToMana @0x5577CEE4 (research share, player-type factor)
```

`GetNetPower @0x5577CEC4` **halves** the total when bit 3 of `[globalmagic+0x10]` is set, and
`GetNetPowerToMana` then multiplies by a per-player-type factor off `[player+0xA7]`. Both sit above
this change and are untouched.

## 2. The patch

22 bytes, replacing the lookup table in place. No cave, no hook, no displaced host bytes.

```
557885EC  0f b6 c0           movzx eax, al             ; Spellcasting level
557885EF  50                 push  eax
557885F0  89 d8              mov   eax, ebx            ; self (THero / TLeader)
557885F2  8b 10              mov   edx, [eax]
557885F4  ff 92 cc 00 00 00  call  [edx + 0xCC]        ; THero.GetResistance -> al
557885FA  0f b6 c0           movzx eax, al
557885FD  5a                 pop   edx
557885FE  0f af c2           imul  eax, edx            ; RES * level
55788601  c3                 ret
```

Trailing 18 bytes of the zone are zeroed. `MULTIPLIER` in the script emits an extra `add`/`lea`/
`imul` tail if it is ever raised above 1 — that is the only edit needed to re-tune.

### Why no cave was needed — and why that is safe

`0x557885EC..0x55788613` is **40 bytes of in-function slack**, hard-bounded by
`THero.GetCastingPointsMax @0x55788614`. The script re-proves all of this on every run rather than
trusting it:

- a **full-file sweep** for rel32 `E8`/`E9` targets and absolute dwords finds **exactly one**
  reference into the range — the `call` at `0x5578B461`. Nothing else can land in it;
- the range carries **no `.reloc` entries**, so nothing relocates into it at load;
- `THero`/`TLeader` VMT `+0x134` still point at `0x557885E4`/`0x5578B43C`;
- `TUnit`/`TAdjustableUnit` VMT `+0x134` still point at the zero stub;
- the caller's 44 bytes are byte-compared (see the register contract below);
- `THero.GetCastingPointsMax` still starts at `0x55788614`.

Because no cave is allocated, this feature **cannot** collide with a cave allocator — contrast the
Magebane / dispelmagic5 collision.

### Register contract — the one implicit dependency

At `0x557885EC` the code relies on `ebx = self`, set by `mov ebx,eax` at `0x5578B43D` and surviving
both vtable calls because **EBX is callee-saved under the Delphi register convention** (the caller's
own `pop ebx` at `0x5578B466` depends on the same thing). `eax` is the level.

⚠ This is why the script byte-compares the **whole caller body**, not just the call site: if a future
patch ever displaces that prologue, `ebx` could stop being self and the cave would call a vtable on
garbage. It refuses rather than reading a stale register.

## 3. Which Resistance, and what that implies

`vtable[+0xCC]` is `THero.GetResistance @0x5578850C` for **both** `THero` and `TLeader` (checked:
identical pointers), so one `call [edx+0xCC]` serves heroes and the leader.

It is the number on the hero card: chassis `[hero+0x40]+0x29` + bought points `[hero+0x6f]` +
ability modifiers (`GetSuperlativeEnabledAbOwner` loop) + `THeroItems.GetResistance` +
`MoraleResistanceModifier`, then **clamped to [0, 40]** at `0x55788586` and returned in **AL**.

Consequences that are behaviour, not bugs:

- `movzx eax, al` is provably safe — the clamp makes a negative impossible. Max output 5 × 40 = 200.
- **Income moves with morale**, because the card RES does. An unhappy hero earns less mana.
- **RES items raise mana income.** Item-granted *Spellcasting* also still counts, because the site
  uses the item-aware `+0x148`/`+0x144` pair (the self-only `+0x84`/`+0x88` pair would not).
- `GetInherentResistance @0x55788500` (`+0xB4`) was the considered alternative — chassis + bought
  points only, no items, no morale, unclamped, 3 bytes cheaper. **Not taken**: the user asked for
  "the hero's RES stat", which is the card value.

Chassis Resistance across the 38 `HERORES.PFS` records (tag `0x14`, per
`build_hero_chassis_atkdam.py`): RES 4 ×7, RES 6 ×15, RES 8 ×13, RES 10 ×1, RES 12 ×2.

## 4. Units are unaffected, for free

`TUnit` and `TAdjustableUnit` VMT `+0x134` still point at `TAbstractUnit.GetPowerGeneration
@0x5577FDB4` = `xor eax,eax; ret`. `build_spellcast.py` deliberately never redirected that slot
("Phase 3 — cancelled"; see the LOCKED scope decision in `Unit_Spellcasting_INDEX.md`). The
constraint holds with no work, and the script asserts it on every run — if either slot ever moves
off the stub it aborts rather than turning units into mana sources.

## 5. One binary only

`AoW.exe`, `AoWCompat.exe`, `AoWTCPCK.dpl`, `aowInt.dpl` and `AoWDevEd.exe` carry **neither** a copy
of the formula (searched for the vanilla `8d 04 80 83 c0 05` idiom) **nor** any
`call [reg+0x134]` (all four modrm forms). The exe drives the magic window through the imported
`GetPower` / `GetNetPower` / `GetManaIncome` / `TPowerSourceList.GetItems` and calls `Power()`
through the source's own VMT — so **every display and the AI budget follow this change for free**.
No `AoW.exe`/`AoWCompat.exe` lockstep edit exists for this feature.

## 6. ⭐ The 10/20/40/60/90 table was an ORPHAN — no script owned it

Byte-diffing the live DLL against `AoWEPACK_original_backup.dpl` before patching turned this up, and
it is the reusable finding here:

- **Vanilla** `TLeader.GetPowerGeneration` computed `lea eax,[eax+eax*4]; add eax,5` = `level*5 + 5`
  **inline**, and `THero.GetPowerGeneration @0x557885E4` was a full **duplicate copy** of the same
  body.
- A **pre-convention Ziggurat patch** collapsed `THero`'s copy into `call TLeader...; ret` (6 bytes),
  freeing 40 bytes, and spent them on the 10/20/40/60/90 jump table — retargeting TLeader's tail from
  the inline arithmetic to `call 0x557885EC`.
- **No script under `build_scripts/` referenced either address.** `grep -rlin '5578B43C\|557885EC'`
  found only `build_spellcast.py`, and only in a comment disclaiming the slot.

Lesson: *a live-vs-pristine byte-diff of the target function is worth doing before every patch, not
only when something looks wrong.* Without it this would have been recorded as "changing vanilla's
`level*5+5`", and `--undo` would have restored the wrong thing.

⚠ **`--undo` restores the TABLE (10/20/40/60/90), not vanilla.** That is deliberate: it returns the
install to its pre-feature Ziggurat state. There is no script that restores vanilla's `level*5 + 5`.

## 7. Data + manual, updated 2026-08-27

- **`Release/Ability.pfs` record 62 tag 5** (Spell Casting; record id = ability id `0x34` + 10) —
  the old text claimed *"5/15/30/50/75 mana generation"*, which was **already wrong before this
  change** (the code gave 10/20/40/60/90). Now reads:
  *"Enables Spellcasting, with 10/20/40/60/90 spellcasting points for levels I / II / III / IV / V.
  On a hero, mana generation per turn equals Resistance x Spellcasting level."*
  Written by a `FIXES` row in `build_scripts/build_pfs_typos.py` (148 → 177 B, 104 later offsets
  +29, CRC residue `0x2144DF1C` re-verified, collateral check clean).
- **`build_ziggurat_manual.py`** — two `MISC_OVERRIDES` entries, because the row is workbook-derived
  and the workbook is a frozen historical snapshot that must not be edited:
  - `Mana income per lvl Spellcasting` → vanilla `10/15/20/25/30`, Ziggurat `RES x level`;
  - `Leader Bonus mana` → note that vanilla's flat `+5` reached **every** Spellcaster, not only the
    leader. The workbook had split `level*5 + 5` across these two rows, which is why its
    `5/10/15/20/25` looked like a plausible vanilla value and was not.
  - the hand-written `UNIT_CASTING` bullet now ends *"…only heroes do, at Resistance × Spellcasting
    level per turn."*
- `Ziggurat Manual.exe` needs **no** rebuild — it is a thin runner that executes the on-disk builder,
  and no new import was added.

## 8. What was checked in game (2026-08-27, user)

Income scales with level × card RES for heroes and the leader; raising RES raises income; units with
Spellcasting still generate nothing; hiring a hero and loading a save both work — that last one
mattered because `RegisterPowerSource` calls `TPlayerMagicControl.Update @0x5577D248` during
`THero.Activate`, so `GetResistance` can run mid-activation. `Update` only triggers notify events
(it does not call `GetPower` itself), and the pre-existing code already ran item-aware ability
queries at the same moment, so the object was always required to be well-formed there.
