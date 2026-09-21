# `.hsm` / `.asg` container format, and what map/save instances actually contain

Derived and verified 2026-08-28. Nothing was written to any map or save; this is read-only
knowledge. Prompted by the question "do units placed on old maps carry outdated Leadership?".

## The container — three lines of code

```
"CFS\0" <u8 2> <zlib stream>          # .hsm, .asg, .csm
```

```python
import zlib
payload = zlib.decompressobj().decompress(open(path, "rb").read()[5:])
```

`Save/Test.asg`: 20,852 bytes on disk → 198,809 decompressed, starting `HSM\0`.
⚠ `.acg` does **not** open this way (it has a leading index) and was not cracked.

**`re_tools/pfs.py`'s `parse_dir` then works VERBATIM on the payload** — the directory shape is the
engine's general serialisation format, not something specific to `.pfs`. Objects are
`<u32 ClassID><directory>`, so parse with `top=True`.

Useful tags on an ability owner inside a map/save:

| tag | meaning |
|---|---|
| `2` | ability bit count (u32) |
| `3` | the bitset, LSB-first, **bit index == ability id** |
| `0x0A` | `Unitres` record id (u16) — the actual record id, not a list position |
| `0x31` | `<u32 0><u32 n><u32 id>*n` — the id list the loader drives off |
| `id+0x32` | that ability's level sub-record |

Corpus scanned: 28 files (`Save/*.asg`, `1Scenario/**`, `EmailIn/**`, `EmailOut/**`) →
58,887 `TUnit`, 13,374 `THero`, 1,185 `TLeader`, 12,082 `TItem` ability owners.

## ⭐ The finding: instances are SNAPSHOTS of the ruleset at authoring time

This is the important part, and it is not Leadership-specific.

A map or save stores each unit's **ability bitset as it stood when the instance was written**. Edit
the ruleset afterwards and existing instances do not follow. Across those 28 files, abilities the
chassis grants *today* that instances lack:

| ability | instances missing it |
|---|---|
| `0x34` Spell Casting | 6386 |
| `0x40` Vision | 3225 |
| `0x38` Assassin | 798 |
| `0xB0` Shield | 711 |
| `0x2E` Leadership | 24 |

⚠ **So the staleness is INVERTED from the obvious hypothesis.** We went looking for instances with
the Leadership *bit* but no level record — the Crown-of-Kings shape. There are none (every `0x2E`
record in every file is `TLeadershipAbilityData` `0x000202CE`, and none resolves to 0). The stale
instances have **lost the bit entirely**, which a bare-bit census cannot see. Worked example,
verified by hand:

```
LIVE Unitres rec 6 (Cavalier) base set:  [0, 21, 46, 64, 67, 111, 113]
Save/Test.asg @0x15240  residx 6  set:   [0, 21,     64, 67, 111, 113]   missing exactly {46}
```

Dated by **content, not mtime**: `Ziggurat upload/Release/Unitres.pfs` (2026-04-04) has Cavalier's
base set as exactly the instance's bitset, so the base Leadership grant postdates that file and
every instance written earlier froze the old set.

## Why some files heal and some do not

`AoWE.TUnit.NewDay @0x55782C98`, live DLL:

```
55782C9F  call TAbstractUnit.NewDay
55782CA4  mov  eax, [AoWHSMap]
55782CA9  cmp  dword [eax + 0x174], 1     ; the day counter
55782CB0  jne  0x55782CE7                 ; ...skip the rebuild
55782CB2  call SetAbCount(0)              ; then re-apply base + rank templates
```

**The ability rebuild is gated to day 1.** So a `.hsm` started as a new game repairs itself on the
first day; an in-progress `.asg` past day 1 never does. Consistent with the data —
`Save/autosave.asg` has zero stale units, while `Test.asg` and `Test 2.hsm` are stale.
(Inferred from the code plus that correlation; not observed in game.)

## Status and residuals

**Not a bug — data to curate by hand if and when it matters** (author's ruling 2026-08-28). Fresh
games off any map repair themselves; only in-progress saves carry the stale sets, and the effect is
a missing ability rather than corruption.

Two things noted in passing, neither chased:

- ⚠ **45 records resolve to Leadership level 254** (an unsigned read of −2), concentrated in the
  PBEM `EmailIn`/`EmailOut` files and inherited from third-party maps. `TArmy.UpdateFormation`
  propagates the stack maximum with **no clamp** against the cap of 4, and each level is +1 ATK and
  +1 DEF army-wide (tables at `0x5580F0C0` / `0x5580F0C8`, both `00 01 02 03 04`). Origin of the
  negative not traced.
- The seven `User/Zig.ail` items granting Leadership are all level **1**, while Spell Casting spans
  1–5 across 31 items and Vision 2–4 across 14. The cap was 1 until 2026-07-20, so 1 was the only
  legal value when they were authored. Author's ruling: they should be tiered 1–4 by strength,
  mostly 1 and 2 — a hand-curation job, not a patch. ⚠ `Zig.ail` carries **no description text at
  all** (tag `0x12` absent in all 325 records), so there is nothing written to contradict.

⚠ `TLeadershipAbility.GetLevel @0x557661C4` is **`max(byte[+0x0C], byte[+0x10])`** — own level
versus external/aura level. A record with own 0 and external N is normal runtime state, not
corruption. Do not read `[rec+0x0C]` alone and conclude a level is missing.
