# Casting Points on the Unit Card — Implementation (2026-07-06)

**Goal:** make a mundane unit's info card show its casting points, the way a hero's card does.

**Result:** WORKING. A unit with the Spellcasting ability now shows `current/max` casting
points (plus the icon) in the cell to the right of its upkeep — rendered by the game's *own*
display code, just un-hidden for units.

**Live patch script:** `build_spellcast_card_v2.py` (this folder). Patches **AoW.exe** and
**AoWCompat.exe** (either can be the launcher). Backups: `AoW.exe.pre-cardv2`,
`AoWCompat.exe.pre-cardv2` — ⚠ **these are the OLDEST of 8 exe layers as of 2026-07-30; copying them over
the live files destroys all 7 features applied since** (`bookfilter`, `firefeed`, `combatlog`,
`tierresearch`, `clogfix`, `clogwinhide`, `bltprobe`). There is no safe snapshot revert for this feature;
undo it surgically from the build script, and check
`python "Modding Resources/re_tools/revert_audit.py"` first.

> This is a UI add-on to the functional unit-spellcasting mod
> (`Unit_Spellcasting_Implementation_2026-07-05.md`, which patches AoWEPACK.dpl / AoWTCPCK.dpl).
> It depends on that mod's **D3 patch** (TUnit VMT slot +0x128 redirected to
> `THero.GetCastingPointsMax`), because the display reads casting points through that vtable slot.

---

## 1. The key realisation

The unit card is drawn by **one big paint function in AoW.exe at `0x407DB8`** (a method of the
`TUnitWindow` form). That function **already contains a complete casting-points display**: at
`0x4087C0` it reads `GetCastingPointsMax(unit)`, and if `> 0` it builds `"current/max"` and writes
it to the card's **Mana label** — control field `+0x70`, positioned at L416, which is exactly the
cell a hero uses for its casting points.

So the card can already show casting points; the display was simply switched off for units. Two
things kept it hidden:

1. **It's driven by `edi`**, which an `is THero` gate at `0x407E43` sets to the unit for heroes and
   to `nil` for units → the display block is skipped for units.
2. Even if you reach the display, the Mana label and its icon are **hidden by default** for
   non-wizard units; the game explicitly calls `SetVisible(true)` on them before writing.

## 2. What did NOT work (do not repeat)

Recorded so future work doesn't retread these:

| Approach | Why it failed |
|---|---|
| Patch the hero window `0x433A40` | That's a *different* form (the hero/`THeroInfoDlg` side). Not the unit card. |
| Force `edi = unit` at the hero window | Same wrong window; no effect on units. |
| **Flip the `is THero` gate at `0x407E43`** | **CRASHES** (access violation, garbage vtable dispatch). At that gate the tested object is *not* guaranteed to be a `TAbstractUnit`, so calling the virtual `GetAbilityEnabled` at `[vtable+0x148]` on it jumps to garbage. Worse, `edi` is entangled with the paint's hero logic — making a hero-without-Spellcasting get `edi=nil` makes downstream code dereference nil. **Never patch this gate.** |
| Append casting points to the **Upkeep** label (+0x1D8) via a code cave | Worked, but the Upkeep label's render viewport clips at the cell boundary, so the number was guillotined; it also centres its text (custom anchor `AlignWidth=awCenter`), causing symmetric overflow. Cosmetic dead-end. |

**Lesson:** replacing an `is THero` check with a `GetAbilityEnabled` virtual call is only safe where
the object is *known* to be a TAbstractUnit (e.g. the combat gates, where it's `combatUnit+0x4C`).
It is **not** safe at a general gate whose object could be any class.

## 3. What DID work — the safe approach

Instead of touching the entangled gate, hook a spot in the same function that is **known-safe**:
the **upkeep caption-set**. When the paint sets the upkeep number it does
`SetGText(eax = UpKeep label, edx = upkeep string)` at two sites — `0x40916A` (upkeep > 0) and
`0x4091A6` (upkeep ≤ 0) — and at both, `EBX = the unit` (a valid TAbstractUnit) and `ESI = &form`.
An earlier experiment already proved a cave here runs and calls `GetAbilityEnabled(ebx)` without
crashing.

Both `SetGText` calls are retargeted to a code cave that:

1. does the **original** upkeep `SetGText` (upkeep still shows);
2. if `ebx.GetAbilityEnabled(0x34)` (has Spellcasting):
   - **shows** the Mana label — `SetVisible(true)` via `control.vtable+0x6c`;
   - builds `"current/max"` from `GetCastingPoints` (+0x12C) and `GetCastingPointsMax` (+0x128);
   - writes it to the Mana label (`[[esi]+0x70]`) via `SetGText`;
   - **shows** the Mana icon (`[[esi]+0x6c]`) the same way;
   - frees its temporary strings.

This changes **no** existing hero/unit logic — it only *adds* a display for casters — so the crash
path is never touched. The game's own Mana writer (`0x408824`) is `edi`-gated (off for units), so
there's no conflict.

### The cave (in a new `.sc` PE section, runtime VA `0x60C000`)

```
push ebp; mov ebp,esp; sub esp,0x0C          ; frame + 3 AnsiString locals
call 0x403254                                ; original SetGText(UpKeep, upkeepStr)
xor eax,eax; mov [ebp-4],eax; mov [ebp-8],eax; mov [ebp-0xC],eax   ; nil the locals
mov eax,ebx; mov ecx,[ebx]; mov edx,0x34; call [ecx+0x148]   ; GetAbilityEnabled(unit,0x34)
test al,al; jz cdone
; --- show Mana label ---
mov eax,[esi]; mov eax,[eax+0x70]; mov dl,1; mov ecx,[eax]; call [ecx+0x6c]   ; SetVisible(true)
; --- build "cur/max" ---
mov eax,ebx; mov ecx,[ebx]; call [ecx+0x12C]; movsx eax,al; lea edx,[ebp-4];  call 0x4013AC  ; cur
mov eax,ebx; mov ecx,[ebx]; call [ecx+0x128]; movsx eax,al; lea edx,[ebp-8];  call 0x4013AC  ; max
push [ebp-4]; push 0x404234; push [ebp-8]; lea eax,[ebp-0xC]; mov edx,3; call 0x401128       ; LStrCatN
; --- write + show ---
mov edx,[ebp-0xC]; mov eax,[esi]; mov eax,[eax+0x70]; call 0x403254           ; SetGText(Mana, cur/max)
mov eax,[esi]; mov eax,[eax+0x6c]; mov dl,1; mov ecx,[eax]; call [ecx+0x6c]   ; show Mana icon
lea eax,[ebp-0xC]; mov edx,3; call 0x4010E0                                   ; LStrArrayClr (free temps)
cdone:
mov esp,ebp; pop ebp; ret
```

Register contract at the hook (same as `SetGText`): preserves `EBX/ESI/EDI/EBP`, clobbers
`EAX/ECX/EDX`. The cave keeps `EBX` (unit) and `ESI` (&form) intact throughout (all the helpers it
calls are Delphi register-convention callee-save).

## 4. Reference — addresses & fields (AoW.exe, image base 0x400000)

| Thing | Address / value |
|---|---|
| Unit-card paint function | `0x407DB8` (TUnitWindow method) |
| Upkeep `SetGText` hooks (EBX=unit, ESI=&form) | `0x40916A`, `0x4091A6` |
| `TAOWLabel.SetGText` thunk | `0x403254` |
| `SysUtils.IntToStr` thunk (val EAX → AnsiString @EDX) | `0x4013AC` |
| `System.@LStrCatN` thunk (dest EAX, count EDX, strings pushed; first-push = leftmost; callee cleans) | `0x401128` |
| `System.@LStrArrayClr` thunk (EAX=@first, EDX=count) | `0x4010E0` |
| `"/"` AnsiString literal | `0x404234` |
| **control `vtable+0x6c` = `SetVisible(dl)`** (dl=1 show, dl=0 hide) | — |
| unit `vtable+0x128` = GetCastingPointsMax, `+0x12C` = GetCastingPoints, `+0x148` = GetAbilityEnabled | — |
| `TUnitWindow` form fields — UpkeepIcon `+0x1D4`(L144), ManaIcon `+0x6C`(L216), UpKeep `+0x1D8`(L320), **Mana `+0x70`(L416)** | — |
| Game's own CP-in-Mana block (reference for the render) | `0x4087CE .. 0x408832` |

The cave lives in a **new executable PE section** (`.sc`) appended to the EXE, because the code
section has almost no free padding. The section-adding logic (new section header after the section
table, bump `NumberOfSections` + `SizeOfImage`, append raw at file end, mark `0x60000020` =
CODE|EXEC|READ) is in `build_spellcast_card_v2.py`. Verified the result is still a structurally
valid PE (correct section table, image size, cave bytes, both hooks pointing at the cave).

## 5. Reusable RE techniques discovered along the way

- **Delphi forms** are enumerable in `.rsrc` by the `TPF0` signature; each begins with the form
  class name then instance name (short strings).
- **Published field table** (offset → control name) is at `[VMT − 0x2C]`: `{Count:word}
  {ClassTable:dword}` then entries `{Offset:DWORD}{ClassIndex:word}{Name:shortstring}`. This is how
  a form field like `+0x70` was resolved to the `Mana` control.
- **VMT layout (this Delphi build):** self-ptr at `[VMT−0x40]`, class-name ptr at `[VMT−0x20]`,
  instance-size at `[VMT−0x1C]`, parent-ref at `[VMT−0x18]`, field-table at `[VMT−0x2C]`.
- **keystone gotchas** (for hand-built caves): it has no `;` comment support (strip comments
  first); labels must be at column 0; avoid the label name `done` (reserved); use a non-zero
  immediate for `push` so it encodes as `imm32` (keeps cave length stable across passes).

## 6. Build / apply / revert

```
cd "Modding Resources"
python build_spellcast_card_v2.py AoW.exe            # dry-run (verifies, no write)
python build_spellcast_card_v2.py AoW.exe --apply
python build_spellcast_card_v2.py AoWCompat.exe --apply
```

Idempotent (detects an existing `.sc` section and no-ops). ⚠ **To change the cave, do NOT "revert first
then re-apply"** — `*.pre-cardv2` is the oldest of 8 exe layers and restoring it wipes 7 later features.
Make the script **rewrite the `.sc` cave in place** instead: accept either the installed or the new bytes,
overwrite, and assert the growth zone is still zero (pattern: `build_scripts/build_invis_penalty.py`).

(The superseded experiment scripts from §2 — `card`, `card2`, `card3`, `card_mana` — have been
deleted. Their reusable parts survive: the PE-section-adding + cave logic is in
`build_spellcast_card_v2.py`, and the DFM/field-table/disassembly helpers are in `re_tools/`.)
