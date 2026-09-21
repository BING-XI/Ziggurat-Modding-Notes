# Crusade spell — spawn lists and why they repeat

**Status: APPLIED, UNTESTED (2026-07-29).** RE by Ghidra decompilation + capstone; tables read from
the live `AoWEPACK.dpl`; unit names resolved against the installed `Release/Unitres.pfs`. The rework
in §5 is applied but **not yet validated in-game** — promote to `CONFIRMED WORKING` only after the
test in §5.4.

**Build script:** `build_scripts/build_crusade_spawns.py` · **Backup:** `AoWEPACK.dpl.pre-crusadespawns`

`VA = file_offset + 0x55700C00` (CODE) · DATA: `off = VA - 0x55701200`.

> **Not the same defect as the exploration-site rosters.** Crusade routes **every** roll through
> `AoWE.TAoWHSMap.Random @0x5577827C`, which correctly advances the map's persistent RNG state — so
> two casts genuinely differ. The repetitiveness is **hardcoded table size**, i.e. design, not a
> seeding bug. See `Investigation_Site_Defender_Rosters.md` for the seeding family.

---

## 1. The class

`GlobalSpells.TCrusade` — spell id **`0x22`** (used for its own image sequence lookup).

| Method | VA |
|---|---|
| `Create` | `0x557ED148` |
| `PlaceParty` | `0x557ED1EC` |
| `ExecuteTE` | `0x557ED340` |
| `Activate` | `0x557ED664` |

Every summoned unit is granted ability **`0x65`** via unit vtable `+0x94` —
`PassiveAb.TCrusaderAbility` (`Create @0x557BA16C` sets `[obj+0xC] = 0x65`). It descends from
`TDurationAbility`, so crusaders are **temporary** (`GetTotalDuration @0x557BA230`,
`NewTurn @0x557BA238`, `Remove @0x557BA214`).

`PlaceParty` only *places* an already-built army: it picks a random hex within `RadToHN(0x14)`
(radius 20) of the caster via `TAoWHSMap.Random`, calls `TArmyHS.PlaceEx`, sets army behaviour
`10`, and plays the spell's image sequence if the hex is watched. It does **not** choose units.

## 2. What `ExecuteTE` actually does

```c
GetLocation(caster) -> x, y, level
ValidateObservation(...); AddEffect(...)              // the visual

roll = TAoWHSMap.Random(map, 100);                    // 0..99
if (roll < 20) {                                      // --- 20% branch ---
    army = TArmyHS.Create(); SetPlayer(army, 0);
    idx = TAoWHSMap.Random(map, 1);                   // *** ALWAYS 0 ***
    x1 { unit = TUnit.Create();
         SetUnitResource(unit, GetUnitResource(list, TABLE_A[idx]));
         unit.vtbl+0x94(0x65);                        // grant Crusader
         army.AddUnit(unit); }
    PlaceParty(...);
} else {                                              // --- 80% branch ---
    x2 { army = Create; SetPlayer(0);
         n = TAoWHSMap.Random(map, 3) + 4;            // 4..6 units
         xN { idx = TAoWHSMap.Random(map, 2);         // rolled INSIDE the loop -> mixed stack
              unit from TABLE_B[idx]; grant 0x65; }
         PlaceParty(...); }

    army = Create; SetPlayer(0);
    idx = TAoWHSMap.Random(map, 3);                   // rolled ONCE -> homogeneous stack
    count = (idx == 2) ? 3 : 2;
    xcount { unit from TABLE_C[idx]; grant 0x65; }
    PlaceParty(...);
}
CastingDone(...); play SFX
```

## 3. The spawn tables

Six contiguous dwords in DATA at `0x558E8E98`, read from the live DLL and resolved against the
installed `Unitres.pfs`:

| VA | id | unit | table | selected by |
|---|---|---|---|---|
| `0x558E8E98` | 133 | **Astra** | A[0] | `Random(1)` — **always index 0** |
| `0x558E8E9C` | 132 | **Valkyrie** | C[0] | `Random(3)`, once per cast |
| `0x558E8EA0` | 134 | **Highman Avenger** | C[1] | ” |
| `0x558E8EA4` | 128 | **Highman Paladin** | C[2] | ” |
| `0x558E8EA8` | 129 | **Highman Legionary** | B[0] | `Random(2)`, per unit |
| `0x558E8EAC` | 126 | **Highman Archer** | B[1] | ” |

⚠ The tables overlap in address space by design — `TABLE_A` is one dword, `TABLE_C` the next three,
`TABLE_B` the last two. Anything written into that region affects more than one table.

⚠ Unit ids are indices into `Unitres.pfs`, which is **Ziggurat data**. These names describe the
installed game; the ids would mean different units on another data set.

## 4. Why it feels repetitive — three independent causes

1. **The bulk of a cast is only two unit types.** In the 80% branch the two big armies are
   4–6 units each, every one drawn from a **2-entry** table — Legionary or Archer. That is 8–12 of
   the ~10–15 units summoned.
2. **`Random(1)` is a dead roll.** The 20% branch computes an index that can only ever be 0, so
   that branch is *always* a single Astra. The code is shaped as though the table was meant to have
   more entries.
3. **The third army is homogeneous.** Its type index is rolled **once, outside** the loop, so it is
   always 2 Valkyries, 2 Avengers, or 3 Paladins — never mixed. (Contrast the big armies, which roll
   per-unit.)

Net: at most **3 distinct unit types per cast** in the 80% branch, and exactly **1** in the 20%
branch.

## 5. The rework (applied 2026-07-29)

The requested roster needs per-stack *mixed tier composition*, which vanilla's shape cannot express
by repointing tables alone — so the whole spawn section is replaced by one table-driven cave.

### 5.1 Shape
- **Hook `0x557ED3CC`** (`mov edx,0x64` — the `Random(100)` that opens the spawn section), 5 bytes →
  an **exact 5-byte `jmp`**, no padding.
- **Resume `0x557ED611`** — the tail (`CastingDone` + SFX). The 581 bytes of vanilla spawn code in
  between become unreachable and are left in place untouched.
- **Cave `0x55812500`**, 768 B reserved: 82 B data + 353 B code (code entry `0x55812560`).

The cave reproduces vanilla's per-unit sequence exactly — `TAbstractUnit.Create` →
`GetUnitResource` → `SetUnitResource` → grant `0x65` via unit vtable `+0x94` → army vtable `+0xAC`
→ post-init vtable `+0x2C` — and reuses vanilla's own `PlaceParty` for placement. Only *which*
units appear changes.

### 5.2 Data format (all offsets from the cave base)
```
THRESH[3]    cumulative % thresholds        -> 20, 40, 100
LISTOFF[6]   offset of each pool in LISTS
LISTLEN[6]   length of each pool
LISTS[13]    concatenated unit-id bytes
OUTCOMES[54] 3 outcomes x 3 stacks x 3 entries x (pool, count)
```
A "pool" of one element is just "always this unit", so specific picks (Astra, Valkyrie, Catapult)
and tier pools use the same code path. Counts of 0 are skipped.

**Pools:** `a` tier1 `[126,127,129,135]` · `b` tier2 `[128,130,136]` · `c` tier3 `[131,132,134]` ·
astra `[133]` · `d` catapult `[251]` · valkyrie `[132]`.

**Outcomes** (`;` separates army stacks):

| chance | composition |
|---|---|
| 20% | `Astra; 8a; 8a` |
| 20% | `3 Valkyries; 4b4a; 4b4a` |
| 60% | `3b4a1d; 2c5b1d; 1c3b4a` |

The pool index is re-rolled **per unit**, so `8a` is eight units mixed across the four tier-1 types
rather than eight of one — the opposite of vanilla's homogeneous third army.

> ⚠ The 60% branch's last stack was specified as `1c3b5a` = **9 units**, which exceeds AoW1's
> 8-unit army cap; trimmed to `1c3b4a` at the author's instruction. `TArmy.AddUnit @0x5578E86C`
> has **no explicit capacity check** (it delegates to the unit's own vtable `+8`), so an over-cap
> stack would most likely lose a unit silently rather than crash — the build script validates
> every stack and warns.

### 5.3 Safety
- **Registers:** `EBX/ESI/EDI` are pushed by the function prologue and are **not read by the tail**,
  so the cave owns them. It keeps its own locals in a 0x18-byte frame, balanced before the resume
  jmp. `EBP` is untouched — `[ebp-4]` = Self (spell) and `[ebp-8]` = caster are both required by
  `PlaceParty`.
- **PIC:** every global is reached through the `call $+5; pop; sub` load delta, held in the cave's
  stack frame because `Random()` clobbers `EAX/EDX/ECX`. All calls/jmps are rel32. **No absolute
  data reference is emitted** — rebase-safe.
- **RNG:** every roll still goes through `TAoWHSMap.Random`, so the map RNG state advances properly
  and MP peers stay in lockstep. All peers need the patched DLL.
- **Bypassed code:** verified by an image-wide rel32 scan that **nothing outside jumps into**
  `0x557ED3D1..0x557ED610`. (The single scan hit was a `0xE8` data byte whose "target" lands
  mid-instruction — a false positive of byte-wise scanning, not a control-flow edge.)

### 5.4 Test procedure (to promote this doc to CONFIRMED)
Cast Crusade several times. Expect the 60% outcome to dominate; check that tier-1 stacks are
visibly **mixed** (Archer / Chanter / Legionary together, not eight of one), that catapults appear
in two of the three 60%-branch stacks, and that the rare Astra outcome still yields exactly one
Astra. Confirm no stack shows 9 units.

### 5.5 Retuning
Edit `SPEC` / `LISTS` at the top of `build_crusade_spawns.py` and re-run with `--apply` — the script
rewrites its cave in place. `--undo` removes the feature surgically (restores the vanilla 5 bytes,
zeroes the cave) **without touching any `.pre-*` backup**, so later features survive.

## 6. Notes

- Crusade's randomness is already correct — do **not** apply the `sitedefender_vary` reasoning here.
- The summoned units are player 0 (independent/neutral owner slot) with army behaviour `10`, then
  granted the temporary Crusader ability; they are not permanent additions.
- **Cave space accounting** (the free CODE run is `0x55812219..0x558E7918`, ~874 KB):
  | range | owner |
  |---|---|
  | `0x55812400`–`0x5581247F` | `build_sitedefender_vary.py` |
  | `0x55812500`–`0x558127FF` | `build_crusade_spawns.py` (768 B reserved, 449 B used) |

  Allocate new caves from `0x55812800` upward.
- The vanilla tables at `0x558E8E98` are now **dead** but left in place, as is the vanilla spawn code
  at `0x557ED3D1..0x557ED610`. `--undo` restores both to service.
