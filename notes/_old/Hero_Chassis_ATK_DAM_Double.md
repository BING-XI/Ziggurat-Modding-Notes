# Hero chassis — DAMAGE doubled (attack left at the conversion's own doubling)

**Status: CONFIRMED WORKING (2026-08-24)** — validated in-game by the user; applied 2026-08-20.
Script `build_scripts/build_hero_chassis_atkdam.py`
(dry-run default, `--apply`, `--undo`), backup `Release/HERORES.PFS.pre-herochassis`.
**Current tuning: ATTACK ×1, DAMAGE ×2** (multiples of the values stage 2 of the 5% conversion left).

Two user instructions, in order:
1. *"double all the ATK/DAM values of the hero chassis"* → both doubled.
2. *"don't quadruple ATK"* → **attack returned to ×1**, damage kept at ×2.

38 damage bytes are scaled; the 38 attack bytes are written back to exactly the stage-2 value, so
this script and `build_statdouble.py` agree on them. In-place 1-byte pokes, trailing CRC-32 repaired.

| stat | tag | field | stage-2 value | now |
|---|---|---|---|---|
| ATTACK | `0x0F` | `THeroResource+0x24` | 2..8 | **2..8** (×1) |
| DAMAGE | `0x11` | `THeroResource+0x26` | 1..4 | **2..8** (×2) |

The multiplier is the `FACTOR` dict at the top of the script; edit it and re-run `--apply`, which
rewrites in place from whatever multiple is currently installed.

⚠ **Chassis DEFENCE and RESISTANCE are already doubled** by stage 2 (DEF 1..4 → 2..8, RES 2..6 →
4..12; every value even). Doubling them here would **quadruple** them — the thing "don't quadruple
ATK" ruled out. This script deliberately owns only ATK and DAM.

## What a hero chassis is

`THeroResource` — the 38 records in `<game>/Release/HERORES.PFS`. Each is the stat template a hero is
built from. `THero.LinkToResource @0x55787984` hangs it off `THero.dwResource`; a hero's live stat is
`chassis + bought bonus + item + ability`.

## Field map — proved by decompile, not by cost multiplier

Tag → field offset comes from `THeroResource.ReadWrite @0x55789FD4`. Each field is then pinned by the
getter that actually reads it, which is what makes the identification safe:

| tag | field | stat | proved by | SP cost |
|---|---|---|---|---|
| `0x0F` | `+0x24` | **ATTACK** | `THero.GetInherentAttack @0x55788354` | ×5 |
| `0x10` | `+0x25` | Defence | `THero.GetInherentDefense @0x557883DC` | ×5 |
| `0x11` | `+0x26` | **DAMAGE** | `THero.GetInherentDamage @0x55788478`, and `THero.GetDamage @0x55788484` sums `res+0x26` | ×10 |
| `0x12` | `+0x27` | Hit points | `THero.GetHits @0x5578859C` | ×5 |
| `0x13` | `+0x28` | Movement | `THero.GetMoves @0x557885C0` | ×2 |
| `0x14` | `+0x29` | Resistance | `THero.GetInherentResistance @0x55788500` | ×5 |

⚠ **Do not identify these by the cost multipliers alone.** The 5/5/10/5/5/2 in
`THeroResource.UsedSkillPoints @0x55789F50` is suggestive but ambiguous between damage and hit points.
The `+0x28` range of 24..36 is **movement** — exactly the trap `build_statdouble.py` documents
(applying the Unitres tag map to HERORES doubles hero movement and misses resistance).

## ⚠ The damage doubling is a balance change, not part of the 5% identity

Under the conversion identity only ATK/DEF/RES double; **damage never does**. So chassis damage at ×2
is a deliberate balance change that roughly doubles hero base damage output. Recorded so a later
session does not mistake it for conversion damage and "fix" it back. See
`FivePct_Conversion_Manifest.md` for the identity this deviates from.

Attack, by contrast, is now exactly where the conversion put it — ×2 vanilla, like every other stat.
It was briefly ×4 on 2026-08-20 and reverted the same day.

## Headroom — checked against the LIVE clamps

| clamp | live value | effect |
|---|---|---|
| `THero.GetAttack` / `GetDefense` / `GetResistance` / `GetDamage` upper | **40** | all four raised from 30 on 2026-08-20 — see `Hero_Stat_Clamps_40.md` |
| signed byte | 127 | max written value 8 |

**Resolved 2026-08-20.** This change surfaced a contradiction — the three `THero.Get*` stat clamps
were still 30, against decision D4's "30→60" — and the user settled it at **40**. Applied by
`build_hero_clamps.py`; full write-up including the paired-immediate trap in `Hero_Stat_Clamps_40.md`.
The hero **damage** ceiling was raised to 40 the same day by a separate explicit decision — not implied
by the conversion (damage is not a doubled stat), but it gives the doubled chassis damage room.

## ⚠ Undo order

Both this script and `build_statdouble.py` stage 2 write the **same 38 ATTACK bytes**.
`build_statdouble.py --undo` halves ATK/DEF/RES and does **not** touch DAMAGE.

```
undo:     build_hero_chassis_atkdam.py --undo   THEN   build_statdouble.py --undo
re-apply: build_statdouble.py --apply           THEN   build_hero_chassis_atkdam.py --apply
```

**While ATK's factor is ×1 the two scripts write identical ATK bytes, so the order is currently
harmless.** It matters the moment ATK is raised above ×1 again: get it wrong then and HERORES lands
in a mixed state (ATK at the stage-2 value, DAM still scaled). The script's all-or-nothing vector
check detects exactly that and aborts with a diagnosis rather than corrupting the file — but it
cannot repair it.

## Idempotence

A doubled stat looks exactly like a legitimate stat, so there is no in-band marker. The script
matches each stat's full 38-value vector against `PRE ×1` and `PRE ×2` and refuses anything else.
Human-readable cross-check: **DAMAGE holds 24 odd values at ×1 and none at ×2.**

## Verified in-game (2026-08-24)

The user confirmed this works in-game ("Write this all up as working"). The checks that
confirmation covers:

1. A recruited hero's card shows roughly double the **damage** it did before, and **unchanged
   attack** (attack was briefly doubled and reverted — if it still looks doubled, this script did not
   re-run).
2. Heroes are not silently pinned at attack 30 — see `Hero_Stat_Clamps_40.md`, the ceiling is now 40.
3. `AoWDevEd`'s hero chassis editor still opens and saves. The chassis "skill points used" figure it
   displays will rise (damage is priced ×10, and it doubled); that readout is display-only — one
   caller, no comparison, no budget gate — so it cannot block a save.
