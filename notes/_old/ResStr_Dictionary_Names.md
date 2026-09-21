# Renaming spells, abilities and UI text — `Dict/ResStr.mld`

**Status: ✅ CONFIRMED WORKING (2026-08-29)** — validated in-game by the user.

| | |
|---|---|
| build script | `Modding Resources/build_scripts/build_resstr_names.py` |
| targets | `Dict/ResStr.mld` **and** `Dict/ResStr.txt` (written in lockstep) |
| backups | `ResStr.mld.pre-resstrnames`, `ResStr.txt.pre-resstrnames` |
| revert | `python build_scripts/build_resstr_names.py --undo` (surgical, per-row, both files) |

## ⚠ Start here: a spell's name is NOT in the `.pfs`

`Spells.pfs` and `Ability.pfs` have **no name field**. Only the *description* is there
(`Spells.pfs` tag `0x0A`, `Ability.pfs` tag `5`) — edit those with `build_pfs_typos.py`.

The **name** is a Delphi resourcestring compiled into `AoWEPACK.dpl`'s `.rsrc` as UTF-16 — e.g.
"Summon Fire Sprite" at file offset `0x298D9A`, inside a packed RT_STRING block of
`<u16 len><wchar…>` entries back to back with **no slack**:

```
… 12 00 "Summon Fire Sprite"   0B 00 "Summon Boar"   0B 00 "Summon Frog" …
```

Growing one by a character means growing the resource block and shifting everything after it.
**Don't** — the engine already gives you a supported route.

## The mechanism: every resourcestring passes through a dictionary

```
AoWE.TranslateRStr @0x557249FC
  └─ AoWE.TAoWEngine.TranslateRStr @0x55797B30
        if [[engine+0x78]+0x44] < 1 : return the source string unchanged
        else                        : IvDictio.TIvDictionary.Translate(dict, source, dest)
```

`Dict/ResStr.mld` is that dictionary, **keyed on the native English string**. A blank target slot
falls back to the source, which is why 1148 of the 1164 records are empty.

⭐ **Ziggurat already uses this as its rename mechanism** — the 16 non-empty `[US]` slots in the
shipped file are all renames, which is the proof the route works and is the intended one:

| NATIVE | `[US]` |
|---|---|
| Fireball | Triple Fireball |
| Summon Mermaid | Craft Aether Barge |
| Invoke Death | Reap Soul |
| Flame Throwing | Witchfire |
| Fountain Of Life | Pyre of Vitality |
| Cosmagic Surgery | Cosmagic Scrying |
| Dragon / Dragon Slaying | Monster / Monster Slaying |
| Rejuvenate | Desiccate |
| Shoot Javelin / Shoot Black Javelin | Shoot Bolt / Throw Javelin |
| Pure Good / Pure Evil | Lawful / Chaotic |
| Underground Concealment | Cave Concealment |
| Undead(plural) | Undead |
| Version: %s | Version: Ziggurat %s |

So renaming anything the game displays from a resourcestring is a **one-row data edit**, never
binary surgery.

## The `.mld` format (Multilizer v3) — re-derived, not guessed

Header, little-endian, byte offsets:

```
 0  "MLD" | 3 version(3) | 4 byte_order | 5 char_set | 6 context | 7..11 reserved
12  u2 language_count      14  u4 language_offset
18  u2 translation_count   20  u4 translation_offset
24  u2 locale_count        26  u4 locale_offset
30  u2 info_size           32  u4 info_offset
36..41 reserved                                          (header ends at 0x2A = language_offset)
```

Translations start at `translation_offset` and are **packed sequentially with no index**. Each
record is 8 `<u16 len><bytes>` strings:

```
NATIVE, FORM, COMPONENT, [US], [DE], [FR], [IT], [ES]
```

(`language_count` 6 = Native + 5; the `[US]` slot is index 3.) In this install: 1164 records from
`0x118`, landing exactly on `info_offset`, and `info_offset + info_size == filesize`.

⇒ **A length change needs exactly one fix-up: `info_offset` moves by the delta.** Nothing else
references a position past the edit, and **there is no checksum** — contrast `.pfs`, which has one
(`PFS_Format_CRC.md`). The script asserts both invariants after every write.

## Traps

- ⚠ **`Dict/ResStr.txt` must be edited in lockstep, and it is not cosmetic.** The `.txt` is the
  human-editable source that `mld_conv.exe` converts back into the `.mld`. If the two drift, the
  next TXT→MLD round trip **silently reverts** the rename. The script edits both and refuses to run
  if they disagree.
- ⚠ **The `.txt` is CRLF.** Reading it in Python's default universal-newline mode and writing it
  back converts all **10612** line endings to LF — a 10 KB diff from a one-word edit. Read with
  `newline=""` and preserve each line's trailing `\r`. This bit once during this build; the
  `--undo` byte-exactness check is what caught it.
- ⚠ **`mld_conv.exe` is a GUI program** (PE subsystem 2 — "MLD Converter v1.1", Convert MLD↔TXT
  buttons). It takes a file argument but still waits for a click, so it **hangs a shell**. Don't
  invoke it from a script; the build script writes both files directly instead.
- The `_HEADER_` block in the `.txt` is left untouched — `mld_conv` recomputes those values, and
  the copy on disk is already stale against the `.mld` (`info_offset` differs).
- `Ziggurat upload/Dict/` holds a **pristine** copy of both files. It does not receive this edit
  unless asked.

## Row applied 2026-09-01

`Freeze Water` → **`Grip of Winter`**.

`build_gripofwinter.py` gave the spell a terrain-cooling ladder and made it castable on land, so the
old name no longer described it. `Release/Spells.pfs` record 20 tag 10 was rewritten to match in the
same pass (`build_pfs_typos.py`) — the two always move together, since the name comes from here and
the description from the `.pfs`. See `GripOfWinter_Design.md`.

## Row applied 2026-08-29

`Summon Fire Sprite` → **`Summon Fire Sprites`**.

The spell really does summon 3–7, so the singular name was the only thing wrong. `Spells.pfs`
record 31 tag `0x0A` already read `"Summons 3-7 Fire Sprites.\r\n"` and needed no change, and the
count comes from an existing cave — `SummonSpells.TSummonSpell.SetupSummonSpellTE @0x557E4484` is
replaced by `jmp 0x5580C500`, whose body is:

```
5580C51E  cmp  esi, 0xE4          ; summon unit id (Unitres.pfs 228 = Fire Sprite)
5580C524  jne  0x5580C547         ; everything else: add one copy
5580C526  mov  eax, 5
5580C52B  call System.@RandInt    ; RandInt(5) + 3  ->  3..7 copies
5580C530  add  eax, 3
```

(That cave is one of the three unowned, undocumented caves catalogued in
`Caster_Abilities_Feasibility_2026-08-25.md` §9 — this identifies what it does.)
