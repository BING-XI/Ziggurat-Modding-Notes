# Hero stat bounds — history of the THero.Get* clamps

⚠ **Partially superseded 2026-08-24 by the DAM/HP doubling** (`DamHP_Double_Decisions.md`):
`build_hero_clamps.py` was rebuilt on a LADDER model and now owns EIGHT bounds — ATK/DEF/RES
ceilings **40**, DAM ceiling **40** (raised to 60 by H4 on 2026-08-24, then returned to 40 on
2026-08-26 to restore Set == Get), HITS ceiling **100** (2026-08-31; was 120), DAM and HITS
floors **2**, and — new on 2026-08-31 — the **HITS purchase cap in `THero.SetUnitHits`**
(`cmp` @`0x557878BC` / `mov` @`0x557878C0`, ladder 80/120/100), moved here from
`damhp_manifest.json` because a two-state manifest entry cannot express a re-target. The
paired-immediate trap documented below still holds and now covers floors too (a floor is a
cmp/mov pair exactly like a ceiling). The 30→40 story below is kept for the derivation.

# (2026-08-20) Hero ATK / DEF / RES / DAM ceilings raised 30 → 40

**Status: CONFIRMED WORKING (2026-08-24)** — validated in-game by the user; applied 2026-08-20.
Script `build_scripts/build_hero_clamps.py`
(dry-run default, `--apply`, `--undo`), backup `AoWEPACK.dpl.pre-heroclamps`.

Closes the contradiction flagged in `FivePct_Conversion_Manifest.md` §5 / `Hero_Chassis_ATK_DAM_Double.md`.

## Why

`THero.GetAttack` / `GetDefense` / `GetResistance` each end with a hard ceiling. Vanilla capped them
at 10; Ziggurat had already raised them to **30** before the 5% conversion. The conversion then
doubled every stat **but left these ceilings alone**, so the hero stat ceiling was silently halved in
effect: 30 post-conversion points buy what 15 pre-conversion points did.

That contradicts recorded decision **D4** ("`THero.Get*` clamps 30→60"). The three **stat** sites are
in `fivepct_manifest.json` marked `UNCHANGED 30→30` with **no ruling recorded**, and the resistance
one is annotated *"DECISION REQUIRED"* — the decision was never taken and `UNCHANGED` was the default.
(The damage site was correctly `UNCHANGED`; it moved for a different reason, below.)

**User decision 2026-08-20: 40**, not the 60 that D4 implied.

**Damage followed the same day**, by a separate explicit decision. Damage is *not* a doubled stat, so
its ceiling was not implied by the conversion at all — but hero chassis damage was doubled
(`Hero_Chassis_ATK_DAM_Double.md`), and 40 keeps it in line with the other three.

## ⚠ Each clamp is a PAIR of immediates, not one

This is the trap worth remembering. The test and the value written when it trips are separate
instructions, and **both** carry the ceiling:

```
557883C8  66 83 F8 28   cmp ax, 0x28        <- imm at +3
557883CC  7E 04         jle  short
557883CE  C6 04 24 28   mov byte [esp], 0x28 <- imm at +3
```

Patching only the `cmp` produces a silent discontinuity: values 31–40 pass through correctly, but
anything above 40 snaps back to **30**. That half-patched state was actually reached during this work
and caught by disassembling the result rather than trusting the write. `build_hero_clamps.py` now
owns both immediates, detects a half-applied state explicitly, and repairs it by writing the target.

⚠ **`fivepct_manifest.json` lists only the `cmp` immediates** (`0x557883cb`, `0x55788465`,
`0x55788589`) — it models these clamps incompletely. Same class of error as modelling a 4-byte
progression table as a single 1-byte entry.

| site | `cmp` imm | `mov` imm | before | after |
|---|---|---|---|---|
| `THero.GetAttack` | `0x557883CB` | `0x557883D1` | 30 | **40** |
| `THero.GetDefense` | `0x55788465` | `0x5578846B` | 30 | **40** |
| `THero.GetResistance` | `0x55788589` | `0x5578858F` | 30 | **40** |
| `THero.GetDamage` | `0x557884EF` | `0x557884F5` | 30 | **40** |

Encoding is `66 83 F8 nn` = `cmp ax, imm8` sign-extended; 40 = `0x28` still fits in imm8, so this is
a 1-byte poke per immediate — no length change, no re-encoding, no `.reloc` involvement.

## Deliberately not touched — `TUnit.GetDamage`

`TUnit.GetDamage` @`0x55782AD4` (imms `0x55782AD7` / `0x55782ADB`) stays at **30**. Unit damage was
not doubled by anything; only the *hero chassis* damage was, so only the hero ceiling needed room.

⚠ **It also has a DIFFERENT ENCODING from the four hero clamps** — `cmp dx, imm8` is `66 83 FA nn`,
and the value is written by `mov al, imm8` (`B0 nn`, two bytes) rather than `mov byte [esp], imm8`.
If it is ever added to `SITES`, the script's shape check must be widened first; do not assume the
hero encoding carries over.

A byte scan for every `cmp ax,0x1e` / `cmp dx,0x1e` encoding across CODE found **exactly five** sites —
the four hero clamps plus this one — so there is no hidden second copy of a hero clamp. That scan
matters: `TUnit.GetAttack`'s clamp genuinely does have a live duplicate inside Ziggurat cave
`0x5580C0F7`, and only a scan catches that class of miss.

## Where the ceilings now sit

| getter | ceiling (2026-08-24 state) | set by |
|---|---|---|
| `THero.GetAttack` / `GetDefense` / `GetResistance` | **40** | this script |
| `THero.GetDamage` | **40** | this script (H4 raised it to 60; user ruling 2026-08-26 returned it to 40) |
| `THero.GetHits` | **100** | this script (H5 set 120; user ruling 2026-08-31 lowered it to 100); floors 2 |
| `THero.SetUnitHits` purchase cap | **100** | this script since 2026-08-31 (ladder 80/120/100) — must equal `GetHits` or skill points are silently eaten |
| `TUnit.GetAttack` | 40 | conversion stage 1 — two copies; `mov` twins REPAIRED 2026-08-24 |
| `TUnit.GetDefense` / `GetResistance` | 60 | conversion stage 1; `mov` twins repaired |
| `TUnit.GetDamage` | **60** | `build_damhpdouble.py` (H4) |
| unit computed HP total | **100** | `build_medal_hpmv.py` **v4** cap cave (v2 introduced it at 120; v3 fixed the quotient bug; v4 lowered it) |

So hero attack is now level with unit attack, and hero defence/resistance sit below the unit ceiling.

## Verified in-game (2026-08-24)

The user confirmed this works in-game ("Write this all up as working"). The checks that
confirmation covers:

1. A heavily-equipped high-level hero can exceed 30 attack and keeps climbing to 40 — and does **not**
   snap back to 30 past the cap (that is the specific failure the paired-immediate bug caused).
2. Defence, resistance and damage behave the same way.
3. Unit damage still tops out at 30 (only the hero ceilings moved).
