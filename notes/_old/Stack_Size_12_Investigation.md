# Stack size 8 → 12 — investigation

**Status: SHELVED — the user decided against the feature (2026-08-16). Nothing applied, no build
script exists. The research stands and is fully verified; §1 (`TGeneral` slot overflow) and
`Command_DoubleStack_Bug.md` describe VANILLA bugs worth fixing regardless of the cap.**
Date: 2026-08-15. Seven parallel RE passes over AoWEPACK.dpl, AoW.exe, AoWTCPCK.dpl, aowInt.dpl,
the editors, the `.pfs` data and the `.HSM` maps.

**Verification pass, same day.** Claims marked ✅ or "VERIFIED 2026-08-15" were independently
re-checked against the live binaries and data files. What that pass changed:

| claim | outcome |
|---|---|
| 6 cap immediates (§2) | ✅ byte-exact, and live == pristine (none pre-patched) |
| 13 tactical deployment sites (§8a) | ✅ 13/13 byte-exact |
| 4 count→mask tables + overflow bytes (§3b) | ✅ exact, incl. `0x558E8DC0`'s padding running into `0x558E8DCC` |
| `TArmy+0x2B` free? (§3a) | ✅ **yes** as a `TArmy` field — 19 hits, none on `TArmy`. `+0x29` **not** free (vision) |
| `Unitres.pfs` tag `0x18` (§5) | ✅ 11 units, now listed by name — **6 sit at the max of 7** |
| `Flags.ilb` ids 49–51 missing (§6b) | ✅ confirmed — next id after 48 is **70**, so 49–69 is a free gap |
| `tcunits.ILB` = 57 images (§8e) | ✅ confirmed |
| **`TGeneral` overflow severity (§1)** | ⚠ **CORRECTED — it is a 10-unit bug, not a 9-unit one** |
| **`TUnitGrid` 8 cols vs DFM 4×2 (§10)** | ⚠ **not a contradiction — a 14th patch site found at `0x55803391`** |

**No prior art.** An exhaustive sweep of `Modding Resources/**`, all 89 `build_*.py`, `re_tools/`,
the project memory files and `.claude/agents/` found no previous attempt, investigation or recorded
failure for a stack-size change. Nothing here is being re-trodden.

---

## 0. The one thing to understand first

**8 is almost never a capacity constant in this codebase. It is the width of a byte.**

The unit collection itself is fine — `TArmy` inherits a dynamic `TList` from `TUnitList` with a
32-bit count, and takes 12 without complaint. Saves and maps take 12 with no format change.
Auto-resolve takes 12 without truncating. What cannot take 12 is every **selection mask**: which
units in the stack are picked, concealed, loaded into a transport, deserting, or being enchanted.
Those are `byte` **by type** — byte locals, byte returns, byte stored fields, byte serialised
event-log fields, `1 << i` builders, `>> 1` consumer loops, and `0xFF` as the literal "all units"
sentinel at dozens of call sites.

Consequence: patching only the four cap immediates **appears to work** — 12 units enter the stack —
but units 9–12 can never be concealed, individually selected, split, joined, transported or
enchanted, and vanish from every `TArmyView` snapshot. Silent wrong behaviour, not a crash.

**Hard ceiling for the whole game: 16 units per stack.** `TCombatUnit+0x46` packs
`party<<4 | slot_in_party` into one byte (`0x80` = wall sentinel). The slot nibble holds 0–15, so 12
is free, but 16+ corrupts the party nibble. Written by `TCombat.AddArmy @0x55727804`; uniqueness
asserted by `TCombatData.AddObject @0x55728CE0` ("CombatObject Position/ID double defined").

---

## 1. ⚠ Fix this first — a latent overflow that already exists

**VERIFIED 2026-08-15** by disassembling `0x0044EC30..0x0044ECB0` in the live `AoW.exe`.

`TMapEvents.TheMapArmySelected @0x0044EC30` fills `TGeneral`'s slot array:

```
0044EC3C  xor  ebx, ebx
0044EC45  mov  dword [General + ebx*4 + 0x84], -1
0044EC51  cmp  ebx, 8                                ; clear loop IS bounded
0044EC54  jne  0x44ec3e
0044EC5A  call [edx + 0x54]                          ; army.Count -> esi
0044EC65  xor  ebx, ebx                              ; ebx = unit index
0044EC67  loop:
0044EC7A    call [ebp + 0xb8]                        ; GetUnitConcealedForPlayer(idx, seated)
0044EC82    jne  0x44ec98                            ; concealed -> no slot
0044EC8B    mov  edx, dword [esp]                    ; slot counter
0044EC8E    mov  dword [General + edx*4 + 0x84], ebx ; *** NO UPPER BOUND ***
0044EC95    inc  dword [esp]
0044EC98    inc  ebx ; dec esi ; jne loop            ; bounded only by army.Count
0044ECA3  mov  dword [General + 0xa4], edi           ; army pointer written AFTER the loop
```

`TGeneral` (VMT `0x00453FC4`, instance size `0xCC`) holds `array[0..7] of Integer` at `+0x84..+0xA0`
with `+0xA4` = the selected `TArmy` pointer. The fill loop is bounded **only by the army's unit
count**, and only *visible* (non-concealed) units consume a slot.

⚠ **Severity, corrected.** An earlier reading claimed a 9-unit stack corrupts the army pointer. It
does not: the 9th visible unit writes to `+0xA4`, but `0x0044ECA3` rewrites `+0xA4` with the correct
army two instructions later, so **9 visible units is harmless**. The first *unrepaired* corruption is
at **10 visible units**, which writes `+0xA8`; 11 → `+0xAC`; 12 → `+0xB0`. Since 12 is the target,
this still must be fixed before the cap moves — but it is a 10-unit bug, not a 9-unit one, and it is
gated on units being visible.

### ✅ The overflow targets, identified 2026-08-15

Field table at `[VMT-0x2C]` = `0x00453FEC` lists only **2 published** fields (`+0x44 Manager`,
`+0x48 ToolTip`), so identification came from taint-tracking every `mov r,[0x0045A420]; mov r2,[r]`
load plus backward provenance on the bare hits — two independent scans agreeing exactly:
**27** genuine `+0xA8` sites, **1** `+0xAC`, **6** `+0xB0` (the rest belong to other classes).

| offset | what it is | stray small integer written here |
|---|---|---|
| **`+0xA8`** | `SelectedStructure : AoWE.TStructure` — **live object pointer** | 💥 **CRASH** — 26 read sites, all `mov edx,[eax]` / `@IsClass` / virtual dispatch |
| **`+0xAC`** | previous selected structure — saved from `+0xA8` in `TheMapStructureSelected @0x0045001C` and **never read anywhere in `AoW.exe`**. Dead field | ✅ **HARMLESS** — write-only, never dereferenced or freed |
| **`+0xB0`** | `SelectedCity : City.TCity` — **live object pointer** | 💥 **CRASH**, narrower window (needs a city window open) |

Proof for `+0xA8`: `TheMapStructureSelected` does `mov eax,[General+0xa8]` → `mov [General+0xac],eax`
→ `mov [General+0xa8],edx`. `TheMapStructureDeselected @0x0044FF18` nils `+0xA8/+0xB0/+0xB4/+0xB8/+0xBC`
— **`+0xAC` deliberately not among them**. The virtual slots the exe calls on `[General+0xA8]` match
`AoWE.TStructure`'s VMT (`0x55713C18`) exactly: `+0x70 GetSelected`, `+0x74/78/7C GetXhx/Yhx/Lhx`,
`+0x144 GetDescription`, `+0x1D0 CanDblClick`; plus `TExplorationSite.CanSearch` at `0x00443011` and
`@IsClass` against `TCity`/`TProductionPlace`/`TWizardsTower`. `+0xB0` takes
`City.TCity.Loot` at `0x004506FF` and `TStructure.Raze`/`CanRaze` via `[ecx+0x1e8]`/`[esi+0x1ec]`.

**Why it is a HARD crash.** The write stores `ebx` = the unit's index, and reaching slot 9 requires
`ebx >= 9`, so `+0xA8` receives 9/10/11 — **never nil**. Every consumer guards with a nil test
(`test ebx,ebx / je skip`), which non-nil garbage sails straight through into `mov edx,[eax]` on
address `0x00000009`. Unguarded derefs also exist at `0x00442BA9`, `0x00442F4D`, `0x004421EA` — the
structure-info-window populate helpers, i.e. the panel that repaints whenever the selected
structure's display refreshes. `TheMapArmySelected` never heals `+0xA8`, so the bad value persists
until the next structure select/deselect. Secondary defect: `TheMapStructureDestroyed @0x0044FFC8`
gates on `edx == [General+0xA8]`, so with garbage there it silently fails to deselect a destroyed
structure, leaving a dangling pointer in the open window.

**Net effect at cap 12:** the 10th visible unit writes `+0xA8` (💥), the 11th `+0xAC` (inert), the
12th `+0xB0` (💥).

⚠⚠ **THIS IS LIVE IN VANILLA TODAY, not introduced by the cap change** — it only needs an army with
≥10 visible units, and §2 records a vanilla route to one: the unbounded merge in
`TArmyCombatMoveTE.ExecuteCombat @0x55749A48`. The cap change does not create this bug; it makes it
routine.

### ✅ Verdict: bound the loop. Do NOT relocate the array.

Bounding `0x0044EC8E` at 8 is **necessary and sufficient** to stop the corruption — and it is
semantically right, not merely defensive: the slot array is the model behind the on-screen unit bar,
and `TControlWin` has exactly 8 DFM component sets. Units 9–12 have nowhere to be drawn regardless.
Displaying slots 9–12 is the separate, much larger §6a feature.

**Hook budget at the fix site.** `.reloc` entries in `TheMapArmySelected` sit at `0x0044EC3F`,
`0x0044EC68`, `0x0044EC85`, `0x0044EC9D`, `0x0044ECAA` (the absolute operands of the
`mov eax,[0x45xxxx]` loads). **`0x0044EC89..0x0044EC97` is 15 contiguous reloc-free bytes**, and the
only inbound branch in the area targets `0x0044EC98`:

```
0044EC89  8B 00                 mov eax,[eax]
0044EC8B  8B 14 24              mov edx,[esp]
0044EC8E  89 9C 90 84 00 00 00  mov [eax+edx*4+0x84], ebx
0044EC95  FF 04 24              inc dword [esp]
```

An in-place `cmp edx,8 / jae` needs 17–19 bytes and does **not** fit — use `E9 rel32` + 10 × `0x90`
into a cave. ⚠ **Do not start the hook at `0x0044EC84`** — that instruction's operand carries the
reloc at `0x0044EC85`. Patch `AoWCompat.exe` in lockstep (same bytes, same addresses).

### ⚠ The slot-array site list is 21, not 18 — and a `*4 + 0x84` grep misses one

| function | sites |
|---|---|
| slot painter `0x00405D98` | `405DA9 405E31 405E80 405ECF 405F20 405F5C 405F98` — 7 |
| `TControlWin.Unit1FrameMouseDown 0x00406040` | `406065 406079 40609A` — 3 |
| `TUnitWindow.PPrevClick 0x0040ABF0` | `40AC3D` (literal `+0x84`), `40AC5A`, `40AC6B` — 3 |
| `TUnitWindow.PNextClick 0x0040AC9C` | `40ACED 40AD00` — 2 |
| `TheMapArmySelected 0x0044EC30` | `44EC45 44EC8E` — 2 (the only writes anywhere) |
| `TGeneral.GetSlotOfUnit 0x00454100` | `45410B` (literal `+0x84`), `45411F`, `454138` — 3 |
| **`0x00407E84`** in `0x00407DB8` | `cmp dword [General+0x88], -1` — **a literal slot-1 reference** gating the prev/next buttons |

**`lea`/`add` audit is clean**, with a trap worth recording: the only address-take through the
`General` global is `add eax, 0x68` (at `0x00405F15`, `0x004348D9`, `0x0044A1E5`) — the byte record at
`+0x68`, not the slot array. So in this exe the address-take idiom is `add reg, imm`, **not `lea`**;
a future field-move audit that greps only for `lea` will miss it.

If the array is ever relocated: `+0xC8..+0xCB` is the only dword in the instance never touched through
the global, and `0xCC` is past the end — grow the class by patching instance size at
`[0x00453FC4-0x1C]` (`0xCC` → **`0xFC`** — 12 dwords at +0xCC, corrected 2026-08-16) so `NewInstance` allocates and zero-fills the tail. `TGeneral`
uses the standard VCL allocation path, so that works.

18 sites read/write `[... *4 + 0x84]`: 7 in the slot painter, 3 in `Unit1FrameMouseDown`, 4 in
`TUnitWindow.PPrev/PNextClick`, 2 in `TheMapArmySelected`, 2 in `TGeneral.GetSlotOfUnit`. Growing the
array in place would overwrite `+0xA4`, so either move it to a new tail region (`0xCC..0xFB`) and
repoint all 18, or shift every field above `+0xA0` — and in that case audit for `lea` as well as
`mov` (the field-move trap from `Copper_Medal_Design.md`).

---

## 2. The cap itself — four immediates (AoWEPACK.dpl)

**VERIFIED 2026-08-15** — all six rows below read byte-exact in the live DLL **and** are identical to
`AoWEPACK_original_backup.dpl` (none already patched):

```
5578DEFB TArmy.MaxSize              BF08000000            OK  live==pristine
5578E4A4 TArmy.CanAddUnits          83FB08                OK  live==pristine
5578E666 TArmy.CanAddUnitSelection  83F808                OK  live==pristine
5579086B TArmy.CanCombine           C744240408000000      OK  live==pristine
5575FDF1 GenerateRazeDefenders trim 83F808                OK  live==pristine
5573ECC6 AI ValidateSelection clamp 83F8087E05B808000000  OK  live==pristine
```

| VA | file off (raw = VA − 0x55700C00, byte-verified 2026-08-16) | function | encoding |
|---|---|---|---|
| `0x5578DEFB` | `0x08D2FB` | `TArmy.MaxSize @0x5578DEF4` | `BF 08 00 00 00` `MOV EDI,8` |
| `0x5578E4A4` | `0x08D8A4` | `TArmy.CanAddUnits @0x5578E3CC` | `83 FB 08` `CMP EBX,8` |
| `0x5578E666` | `0x08DA66` | `TArmy.CanAddUnitSelection @0x5578E55C` | `83 F8 08` `CMP EAX,8` |
| `0x5579086B` | `0x08FC6B` | `TArmy.CanCombine @0x55790814` | `C7 44 24 04 08 00 00 00` |

⚠⚠ **CORRECTED 2026-08-16 — the four immediates are only the NO-TRANSPORTER fallback branch.**
`TArmy.CanCombine @0x55790814`, `CanAddUnits @0x5578E3CC` and `CanAddUnitSelection @0x5578E55C` all
take their ceiling from `Transporter(self,0xFF) == nil ? 8 : capacity+1`. The `mov [esp+4],8` at
`0x5579086B` (and the `< 9` literals) apply **only when no transporter is present**.

**Consequence, and it inverts an earlier plan item:** poking `Unitres.pfs` tag `0x18` from 7 to 11
raises the effective ceiling to 12 for boat stacks **ahead of every safeguard** — silent selection
breakage plus the `TGeneral+0xA8` crash at 10 visible units.
**The transport data edit must land LAST, not first.** (§5 previously implied the opposite.)

⚠ Narrowed on re-verification 2026-08-16: the *natural* direction — walking units INTO a boat
stack — **stays 8-capped** by the mover-side `CanCombine` in `TMoveArmyTE.CanMoveNext @0x5574830C`
(same function, opposite `Self`s; QA must exercise both directions). The **proven** >8 route is the
**Town Gate spell** (`TTownGate.ExecuteTE` calls `AddUnitSelection` directly); the teleporter is
probable; walking a boat onto a plain-stack hex is contingent on `TArmyHS.CanMoveOn` dispatch
(HSEPack, unresolved). Build >8 test stacks via Town Gate, not walk-joins.

`MaxSize` is the canonical cap but **only `TArmy.CanAddUnit @0x5578E2F8` (VMT `+0xA4`) calls it** —
the other three carry their own literal and never consult it. Patching `MaxSize` alone does nothing
for join / merge / multi-add.

`TArmy.AddUnit @0x5578E86C` and `TUnitList.AddUnit @0x55782F1C` are **unbounded** — they just
reparent. All gating is in the `Can*` functions.

⚠ **There is a LIVE over-cap producer in vanilla** (found 2026-08-15 while diagnosing the
Seduce/Charm/Dominate double-stack bug). `TArmyCombatMoveTE.ExecuteCombat @0x55749A48` merges a
second army sharing the mover's hex straight in with `myArmy->vmt[0xAC](myArmy, unit)` and **no
`CanAddUnit` call**. So armies above the cap can already exist today without any patch. At cap 12
this does not go away — it just relocates the threshold into the byte-mask breakage of §3.
Any stack-size work must decide whether to bound this site or accept over-cap armies.
*(Inference from the code; the case was not constructed in-game.)*

The normal placement path is properly gated and does **not** overfill: `TAbstractUnit.Place
@0x557810FC` → `CanPlace @0x55781008` → `TArmy.CanAddUnit` (VMT `+0xA4`) → `MaxSize`. When the
destination is full, `Place` spirals via `WalkToNextHN` to a **different hex** (up to ring 30) and
creates the new army there — it never makes a second army on the same hex.
`TArmyHS.PlaceHX @0x557911F8` independently refuses a same-hex second army unless
`TUnitHS.GetEditMode @0x55784000` is true (editor only).

**No named constant exists.** The DLL's 10,041 exported symbols contain no `MaxUnits`, `MAXARMY`,
`PartySize` or `TArmy.UnitCount`. `AoWE.TArmy.MaxSize` is the only "max size" symbol.

### Class layout (measured, `[VMT-0x1C]`)

| class | VMT | instance size | parent |
|---|---|---|---|
| `TUnitList` | `0x55710EC8` | `0x10` | Engine chain |
| `TArmy` | `0x557130EC` | `0x2C` | `TUnitList` |
| `TArmyView` | `0x55713210` | `0x60` | `TArmy` |
| `TArmyHS` | `0x557133A0` | `0x24` | `TUnitHS` |
| `TSelectedArmy` | `0x5570DD70` | `0x28` | `TMoveSelector` |
| `TUnitSpellCaster` | `0x55723318` | `0x1C` (size dword at `0x557232FC`) | — |
| `TGeneral` (AoW.exe) | `0x00453FC4` | `0xCC` | — |
| `TControlWin` (AoW.exe) | `0x00404910` | `0x17C` | — |
| `TCastUnitSpellDlg` (AoW.exe) | `0x00431ACC` | `0xE4` | — |
| `TUnitSelectionDlg` (AoW.exe) | `0x004449D4` | `0xB0` | — |

Unit list: `TUnitList+0x08` → `TList`; count `[[army+8]+8]`, items `[[army+8]+4]`, unit
`[items + i*4]`. `TUnitList.GetUnit @0x5578309C` is bounds-checked against Count.

`TArmy` fields: `+0x08` TList · `+0x10` flags (bit0 live, bit2 draw banner, bit4 fully concealed,
bit5 extra icon) · `+0x12` player index · `+0x13/14/15` X/Y/L · `+0x24` behaviour · `+0x29`
vision nibble pair · **`+0x2A` per-unit concealed bitmask (1 byte)** · size `0x2C`.

---

## 3. The selection mask — the bulk of the work

### 3a. Stored byte fields

- **`TArmy+0x2A`** — concealed-units bitmask. `TArmy.UpdateConcealedUnits @0x5578CBA0`:
  `0x5578CBB7 C6 43 2A 00` (`MOV byte[EBX+0x2A],0`), `0x5578CBE2 D0 63 2A` (`SHL byte[EBX+0x2A],1`),
  `0x5578CBF9 80 4B 2A 01`. Bits past 8 shift out. Popcounted by
  `TArmy.ConcealedUnitsCount @0x5578CB84`. **Not serialised** (`TArmy.ReadWrite @0x5578E8EC`
  persists only `+0x11,+0x12,+0x13,+0x14,+0x15,+0x24,+0x25,+0x26,+0x27,+0x28`).
  Disassembly re-verified 2026-08-15: the loop counts **down** (`dec esi`), shifting left each pass.

  ✅ **`+0x2B` IS FREE as a `TArmy` field — RESOLVED 2026-08-15** via
  `fieldrefs.py AoWEPACK.dpl 0x29 0x2A 0x2B --validate 0x2F` (scanner alive, 52 validation hits).
  19 accesses to `+0x2B` exist in the DLL but **none is in a `TArmy` method** — all are `TUnit`,
  `TUnitResource`, `THero`, `TRangedAttackAbility`, `TBoltsAbility`, `TBreathAbility`,
  `TFlameThrowingAbility`, `TTransportMEC`, `TFarmResource`, or resource-string misdisassembly.
  **Widening `+0x2A` to a word therefore needs no class growth.**
  ⚠ Caveat the tool states about itself: it is *"good for proving PRESENCE, weak for proving
  ABSENCE"* — a disp8 of `0x2B` is `0x2B` for every class, and a computed or `lea`-based access could
  hide. Strong evidence, not proof.

  ❌ **`+0x29` is NOT free** — three `TArmy` hits confirm the vision nibble pair:
  `UpdateVisibilityRanges+0x4F` (`mov [esi+0x29], bl`), `VisibilityRange`, `TrueVisionRange`.

  Two `+0x2A` hits at `0x5580E00B` / `0x5580E0EB` (attributed `Finalize+0x2233/+0x2313`, inside the
  cave zone) are **false positives** — disassembling `0x5580DFF0` shows zero-fill decoded as code
  (`les esp, ...`, `hlt`). **No existing mod cave reads `TArmy+0x2A`.**
- **`TUnitSpellCaster`** — `+0x18` selection mask, `+0x19` multi-select flag, `+0x1A` valid-target
  mask. All bytes. Exactly one spare byte at `+0x1B` inside the `0x1C` instance.
- **`TUnitSelector`** — `+0x14` mask, `+0x15` multi flag, `+0x16` valid mask. All bytes.
- **`TSelectedArmy`** — `GetSelection @0x5579240C` reads a byte from `TMoveSettings+0x20`;
  `SetSelection @0x55792430` writes a **dword** there, but the value comes from
  `ValidateMoveSelection` which returns a byte. Storage is already 4 bytes wide — only the producer
  and the byte read narrow it. Cheapest widening point in the chain.
- **`TArmyInfoEventLog+0x1C`** — serialised desertion mask, `ReadWrite @0x5578BFC4`, stream id
  `0x11`, **length 1**. Wire-format change (acceptable — no compat constraint).
- **`TEnterArenaEventLog+0x1C/+0x1D`** — selection / trainable masks. ⚠ May be moot: the Arena has
  already been reworked away from unit training on this install (`aow1-arena-rework`), and
  `TArenaDlg`'s `U1..U8` are repurposed as three tier rows. The code still reads the byte mask.

### 3b. The count→mask lookup tables — `00 01 03 07 0F 1F 3F 7F FF`

Nine entries (index = count 0..8), each padded to 12 bytes with `8D 40 00` (`lea eax,[eax+0]`).
Four copies, all in DATA, none exported:

| VA | file off | consumer | clamped? |
|---|---|---|---|
| `0x558E84F0` | `0x1E72F0` | `TAIMoveExecuterUnitList.ValidateSelection @0x5573ECD0` | **yes** |
| `0x558E8DA4` | — | `TUnitSpell.ValidateUnitSelection @0x5577ACCA` | **no** |
| `0x558E8DC0` | `0x1E7BC0` | `TArmy.ValidateSelection @0x5578D446`; `TArmyHS.MapFieldMsgProc @0x55791D74` | **no** |
| `0x558E8DCC` | `0x1E7BCC` | `TArmy.SelectionCount @0x5578D456` | **no** |

⚠ **There is a FIFTH consumer, added 2026-08-16:** `0x55791D74` in `TArmyHS.MapFieldMsgProc`, which
**compares** a mask against the table for equality (`cmp dl, byte[ecx+0x558E8DC0]`) rather than
masking with it. Any "no mask is ever compared, only ANDed" assumption is wrong — a widening that
only fixes `and` sites will silently break the fully-concealed test.
(DATA VA `0x558E8000` ↔ raw `0x1E6E00`; the earlier `0x0029C0`/`0x0029CC` file offsets were wrong.)

12 units needs 13 entries, and the values are bytes anyway, so extension is not the fix — the
tables must be **relocated to a cave and widened to words**, or replaced with a computed
`(1 << count) - 1`. The `0x558E8DC0`/`0x558E8DCC` pair is contiguous (`0x558E8DC0`–`0x558E8DD7`,
with `City.CityUpgradeCost` at `0x558E8DE0`), so neither can grow in place.

**Measured effect of the unclamped read at 12 units** (bytes following `0x558E8DA4`):

| stack size | byte read | effect on the spell dialog |
|---|---|---|
| 9 | `0x8D` (filler) | only slots 1, 3, 4, 8 stay ticked |
| 10 | `0x40` | only slot 7 |
| 11 | `0x00` | **nothing selectable at all** |
| 12 | `0x02` (next table) | only slot 2 |

`ValidateUnitSelection` runs on **every checkbox click**, so checkboxes visibly untick themselves and
`CanCast` reports "No unit selected". This breaks unit-spell casting on full stacks **the moment the
cap is raised**, even with the dialog still at 8 slots.

Clamp idiom to copy (the AI's, at `0x5573ECC6`): `83 F8 08 / 7E 05 / B8 08 00 00 00`
(`cmp eax,8; jle +5; mov eax,8`). That is a **stopgap only** — a byte mask can never express 12.

### 3c. Byte-mask APIs (AoWEPACK.dpl)

Each does `(mask & 0xFF) >> 1` per unit, or builds with `1 << i`:

`TArmy`: `ValidateSelection 0x5578D440` · `ValidateMoveSelection 0x5578D478` ·
`SelectionCount 0x5578D450` · `SelectionUnit 0x5578E8B4` · `GetCanJoinSelection 0x5578FA04` ·
`GetJoinSelection 0x5578FA74` · `JoinAmount 0x5578FAD0` · `GetGroupSelection 0x5578C548` ·
`GetPartyMoves 0x5578DA60` · `GetPartyStatus 0x5578F584` · `MovePoints 0x5578D8D0` ·
`MoveTypes 0x5578D9E8` · `Moves 0x5578D95C` · `ObtainValue 0x5578D884` ·
`GetStrengthEx 0x5578C248` · `ImmunityTypes 0x5578D82C` · `HealUnits 0x5578C3EC` ·
`Kill 0x5578C1FC` · `Desert 0x5578F0E0` · `MakeIndependent 0x5578EA9C` ·
`Transporter 0x5578E00C` · `IndexOfTransporter 0x5578E05C` · `UnitsInTransporter 0x5578E0A4` ·
`ValidateTerrainEx 0x5578CC9C` (drown mask) · `CanAddUnitSelection 0x5578E55C` ·
`AddUnitSelection 0x5578E6B4` · `CanCombine 0x55790814` · `TArmyView.Setup 0x5578B9B8`

AI: `TAIMoveExecuterUnitList.ValidateSelection 0x5573ECC0` / `.SelectionCount 0x5573ECDC` ·
`TAIMoveExecuterMove.AddUnits 0x5573EF0C` · `TAIGroupControl.RetrieveGroupArmy 0x55738B14`
(takes a `uint` and stores into a **byte** out-param)

Spells/abilities: `TUnitSpell.ValidateUnitSelection 0x5577ACB0` ·
`TUnitSpellCaster.SetSelection 0x5577A43C` / `.GetSelectionCount 0x5577A484` / `.Cast 0x5577A6F8` /
`.CanCast 0x5577A578` · `TUnitSelector.Setup 0x5574D804` / `.SetSelection 0x5574D740` /
`.GetSelectionCount 0x5574D748` / `.CanSelect 0x5574D760` · `THealingUnitSelector.Select 0x5576C89C`

⚠⚠ **THIS LIST IS TOO SMALL, NOT TOO LARGE — corrected 2026-08-16.** A mechanical byte-pattern
census of just **2 of the 12 idioms** found **30** enclosing functions where this list names 16, and
~15 appear in no document at all: `TArmy.Hero`, `.Leader`, `.SetBehavior`, `.CreateID`, `.GetGroup`,
`.GetRace`, `.CreateMovePointTable`, `.GetUnitsConcealedForPlayer`, and the whole
`TAIMoveExecuter*` family. **Do not plan against any count in this section** until a mechanical
census across all 12 idioms, in **both** binaries, has been run and committed as a file the build
script asserts against.

**Remove from the list** (verified width-correct or not masks at all):
`GetGroupSelection @0x5578C548` — builds with `add edx,edx / or dl,1` into a 32-bit EDX and returns
`mov eax,edx`, already correct, **zero edits**. `GetJoinSelection @0x5578FA74` and
`GetCanJoinSelection @0x5578FA04` — DL is a **1-based player index**, not a mask.
`ValidateTerrainEx @0x5578CC9C` — flags, not a unit mask.

**Cross-binary ABI — also corrected.** Not "exactly two". `AoW.exe` has **nine** imports, **plus**
VMT-slot calls, **plus raw field reads by displacement** that no import scan can find:
`TUnitSelector+0x14/0x15/0x16` at ten sites in `TUnitSelectionDlg.U1Change`;
`TUnitSpellCaster+0x18/0x19/0x1A` at `0x004323D5`, `0x004323E4`, `0x00432424`, `0x0043234B`;
`TEnterArenaEventLog+0x1C/0x1D`. `AoWTCPCK.dpl` imports only the unrelated
`TMoveSelector.ValidateSelection`.

⚠ **A live cave is also a mask consumer.** `build_patch.py`'s cave at `0x5580D700` does
`movzx edx, byte[ebp-5]` (`0x5580D708`) and `movzx edx, byte[ebp-1]` (`0x5580D716`), reading locals
owned by `TMoveArmyTE.Setup @0x55747ADD` and `MoveArmyEx @0x5574A35E`. Widen either host local and
the cave silently reads the wrong byte — wrong movement overlay, **no crash**. Invisible in Ghidra
(vanilla image). Fold it and both hosts into the inventory as first-class sites.

**Strategy note:** widen byte → **DWORD in flight** (registers/locals/params/returns), not → word.
The opcode pairs are all one-for-one length-preserving: `8A↔8B`, `88↔89`, `22↔23`, `0A↔0B`,
`0F B6↔8B` — verified at real sites in both binaries.

**44 `shl _, cl` byte-shift sites in AoW.exe** build slot bits from a control's Tag (count confirmed;
five apparent extras at `0x4068B3`, `0x40A58C`, `0x40A6B1`, `0x432414`, `0x43CF7E` are desync
artefacts). ⚠ **≥7 `0xFF` "all units" sentinels in AoW.exe, not 1.**

### 3d. `TArmyView` — two fixed 8-element serialised arrays

`TArmyView.ReadWrite @0x5578BAC4` (the fog-of-war snapshot of an enemy stack):

```
TArmy.ReadWrite(...)
stream.vmt[0x1C](self+0x2C, 0x10, 0x28);   ; 16 B = array[0..7] of Word
stream.vmt[0x34](self+0x3C,       0x29);   ; single field (purpose undetermined)
stream.vmt[0x1C](self+0x40, 0x20, 0x2A);   ; 32 B = array[0..7] of Longint
```

- `+0x2C + idx*2` — per-unit "concealed for player" word mask
  (`SetUnitConcealedForPlayer 0x5578B988`, `GetUnitConcealedforPlayer 0x5578B970`)
- `+0x40 + idx*4` — per-unit copy of `unit[+0x26]` (`Setup 0x5578B9B8`, `MainReadWrite 0x5578BB0C`)
- ✅ **`+0x3C` RESOLVED 2026-08-16** — the **army-level** ConcealedForPlayer **word** bitmask
  (`GetConcealedforPlayer @0x5578B93C`: `movzx eax, word[eax+0x3c]` @`0x5578B940`;
  `or`/`and word[eax+0x3c],dx` @`0x5578B95E`/`0x5578B967`). Already a word — no widening needed.
- ⚠ **Displacement trap:** `0x5578BA56 mov [ebx+eax*4+0x3c], esi` writes the **`+0x40` Longint
  array**, not `+0x3C`. A field-move audit keyed on the literal `0x3C` will mis-attribute it.

`0x2C + 16 + 4 + 32 = 0x60` exactly — **no slack**. Twelve needs **`0x78`** (corrected 2026-08-16): grow
the class, move the second array `+0x40 → +0x48`, and change the two serialised record lengths
`0x10→0x18` and `0x20→0x30`. Stream ids are id-indexed so *adding* fields is compatible, but these
are **length changes to existing ids** — old saves would under-fill the widened fields. Acceptable
given no compat constraint.

---

## 4. Persistence — no work needed

**Saves and maps are entirely safe. No format change, no migration.**

An army's unit list is a **nested property-table directory whose loop bound is its own entry count**:

| step | VA | module |
|---|---|---|
| `TArmy.ReadWrite` | `0x5578E8EC` | AoWEPACK — tagged scalars only, **writes no units** |
| `TUnitList.MainReadWrite` | `0x55783118` | AoWEPACK — loops `[[this+8]+8]` children |
| `TECustomNode.ReadWriteChildren` | `0x55519608` | Enginep |
| `TEWriteStorageStream.rwChildren` | `0x55510940` | Enginep — `for i := 0 to Count-1`, key = index |
| `TEReadStorageStream.rwChildren` | `0x555115A4` | Enginep — **loop bound = directory entry count** |

Directory format (same as `.pfs`): `u8 n` (`n & 0x7F` = small count, bit `0x80` ⇒ a `u32` wide count
follows), then `(u8 key, u8 offset)` small entries or `(u32,u32)` wide, then payload. Keys 0–11 stay
"small"; a payload past 255 bytes migrates to wide automatically.

The load path **never consults `CanAddUnit` or `MaxSize`** (`rwCreateEObject 0x55511434` →
`SetOwner` → `TArmy.AddChild 0x5578E810` → `TENode.AddChild 0x55519DDC` = `TList.Add`), so an
unpatched build would *load* a 12-stack without dying — the downstream logic is what misbehaves.

Containers: `.hsm` (593) / `.csm` (72) / `.asg` (23) are `"CFS\0"` + one mode byte + raw zlib, **no
CRC**; `.acg` / `.CAM` are uncompressed property streams. Hand-editable:

```python
import zlib
raw = zlib.decompress(open(r"<game dir>\Save\autosave.asg","rb").read()[5:])
open(path,"wb").write(b"CFS\0\x02" + zlib.compress(raw))
```

Also clean: `TCombat/TCombatData/TCombatParty/TPlayer/TAoWHSMap/TAoWMapField/TArmyHS.ReadWrite`,
`TAoWMapCampaignSettings.ReadWrite 0x55730C0C`, `TAoWCampaignTransferSettings.ReadWrite 0x55730DB4`.
No hardcoded 8 in campaign, scenario or victory data. No "army full" string in the DLL.

**Useful escape hatch:** the property table means a per-army cap byte could be added as a new tagged
field with zero compatibility cost (old files lack the id → `FindOffset` returns −1 → zero-init).
That is the clean route if the cap ever needs to be per-map or per-scenario.

---

## 5. Transport capacity — the "7"

Not a separate cap. `TArmy.MaxSize` is:

```
result := 8
for each unit: c := unit.GetTransportCapacity()   ; TAbstractUnit VMT +0x104, base 0x5577FCCC = 0
               if c <> 0 and c+1 < result then result := c+1
```

So a transport **lowers** the ceiling, never raises it: capacity 7 + the transport itself = 8, which
is why the two numbers coincide. `TUnit.GetTransportCapacity 0x55782BA0` returns
`max(Transport-ability level, TUnitResource capacity byte)`; the Transport ability (id `0x32`) is
level-capped at 7 by its constructor `[self+0x28]`.

**`Release/Unitres.pfs` tag `0x18`** is the capacity byte. Reaches instance `+0x44` in vanilla;
`build_copper_medal.py` moved the *in-memory* offset to `+0x32` (live patch at `0x55784D44`), but
**the pfs tag is still `0x18`**.

**VERIFIED 2026-08-15 — the complete list (11 of 179 records):**

| pfs id | unit | capacity | passengers today | at cap 12 |
|---|---|---|---|---|
| 7 | Air Galley | **7** | 7 | raise to 11 |
| 26 | Sandworm | **7** | 7 | raise to 11 |
| 114 | Dwarven Balloon | 5 | 5 | judgement call |
| 231 | Aether Barge | 5 | 5 | judgement call |
| 236 | Giant Frog | 1 | 1 | leave |
| 258 | Dragon Ship | 2 | 2 | leave |
| 259 | Cog | **7** | 7 | raise to 11 |
| 260 | Galley | 4 | 4 | judgement call |
| 261 | Carrack | **7** | 7 | raise to 11 |
| 263 | Guild Zeppelin | **7** | 7 | raise to 11 |
| 285 | Supply Caravan | **7** | 7 | raise to 11 |

**Six units sit at the current maximum of 7** and are the ones that visibly stop scaling. The other
five are deliberate Ziggurat balance values below the ceiling and probably should not move —
this is a balance decision, not a mechanical one.

⚠ **Raising the code immediate alone leaves every boat and wagon stack capped at 8.** The transport
half is a pure data edit: length-preserving byte write plus CRC-32 repair over `d[4:-4]`
(`PFS_Format_CRC.md`). No garrison / army / party-size field exists anywhere in `Release/`.

---

## 6. Strategic UI (AoW.exe) — the largest single chunk

### 6a. `TControlWin` — the army bar

VMT `0x00404910` · instance `0x17C` · field table `0x00404938` (77 entries) · DFM
`TControlWin 'ControlWin'` at file `0x0B1BF0`, **46,033 bytes** in `.rsrc` · instance gvar
`[0x0045B054]` via `[0x0045A084]`.

**Six families of 8 controls, all driven by fully unrolled 8× code — not loops, not tables.**

| family | field offsets | parent | WinLeft per row | size |
|---|---|---|---|---|
| `Unit1..8Frame` (TAoWFrame) | `+0x50..+0x6C` | T1/T3Pnl | 1, 49, 97, 145 | 46×49 / 46×48 |
| `Unit1..8Gge` (TAoWGauge) | `+0xBC..+0xD8` | T1/T3Pnl | 12, 60, 108, 156 | 24×2 |
| `Unit1..8Chk` (TAOWCheckBox) | `+0xDC,E0,E4,`**`F4`**`,E8,EC,F0,`**`F8`** | T2/T4Pnl | 1, 49, 97, 145 | W 46 |
| `U1..8MIcon` (TAOWImage) | `+0x80..+0x9C` | T2/T4Pnl | 3, 51, 99, 147 | 32×17 |
| `Emp1..8Fr` (TAoWFrame) | `+0xFC..+0x118` | T1/T3Pnl | 1, 49, 97, 145 | 46×49/48 |
| `Emp1..8Chk` (TAoWFrame) | `+0x11C..+0x138` | T2/T4Pnl | 1, 49, 97, 145 | 46×18 |

⚠ **The `Unit#Chk` field order is scrambled** — `Unit4Chk` at `+0xF4`, `Unit8Chk` at `+0xF8`, after
5/6/7 — and the unrolled code follows that order literally. Any table-driven rewrite must preserve
it or fix every consumer.

| VA | what | at 12 |
|---|---|---|
| `0x00404F58` | `Update` — 8 unrolled fill blocks, ~0x101 B each | rewrite as a cave loop over a 12-entry field-offset table |
| `0x00406130` | `CheckStart` — unrolled ×8 + `shl bl, cl` | loop + wider mask |
| `0x004062A0` | `CheckEnd` — unrolled ×16 (8 checks + 8 `SetILFIndex` 0x1A/0x0C) | loop + wider mask |
| `0x00405D98` | slot painter — index-generic (`[General + ebx*4 + 0x84]`) | **free** |
| `0x00406040` | `Unit1FrameMouseDown` — reads `Sender.Tag` at `[Sender+0x0C]`, no `cmp ,8` | **free** |
| `0x0040674C` | `Unit1FramePreDraw` — index-generic | **free** |
| `0x004060D8` | `Unit1ChkChange` → CheckStart / SetSelection / CheckEnd | |
| `0x004066BC` | `Unit1ChkMouseDown` — button 1 inverts whole mask (`not dl`) | wider mask |
| `0x00454151` | `TGeneral.GetSlotOfUnit @0x00454100` — `cmp ebx, 8` | one byte |
| `0x0040AC4B` / `0x0040ACDF` | `TUnitWindow.PPrevClick` / `PNextClick` wrap — `mov ebx,7` / `cmp ebx,7` | 7 → 11 |

⚠⚠ **CORRECTED 2026-08-16 — the slots are laid out by INTEGER ALIGNMENT PERCENTAGES, not by
`WinLeft` pixels.** Every pixel costing in this section is therefore in the wrong unit. The practical
consequence flips the layout comparison: **3 rows × 4 reuses the existing 0/75, 25/50, 50/25, 75/0
quadruple verbatim**, while 2 rows × 6 needs rounded percents + pixel offsets — **feasible but
uneven (~1–2 px per column; vanilla's own 12.5% dialogs use exactly that trick — corrected
2026-08-16 from "infeasible")**. So 3×4 is the cheaper *and* cleaner option. Same applies to
`THeroInfoDlg @0x00447CEC` / `TArmyInfoDlg @0x004475A0`. ⚠ The Info/Join dialogs are scrambled
**differently** from `TControlWin`: their order is `U1,U2,U4,U5,U3,U6,U7,U8`.

**Geometry (pixel figures below are indicative only — see the percentage note above).**
ControlWindow (440,216) 200×216, **Max 400×432**, resizable, `awRight/ahTop`. Row
panels 192 wide; slot pitch 48 → `1 + 4*48 = 193`, i.e. **exactly four across, no room for a fifth**.
Row pitch 74 (T1@21, T3@95). **3 rows × 4 → ~290 tall — inside its own Max and inside the 640×432
manager clamp.** (2 rows × 6 → ~300 wide, also fine.) ⚠ raise `MinWidth`/`MinHeight` in lockstep.

**Art is free.** Frame `ILIndexFrame` 12 normal / 26 selected are nine-patch *frame sets* (N..N+7,
TL/T/TR/L/R/BL/B/BR) from `Int\Units.ILB` — twelve frames reuse indices 0/12/26 unchanged. Portraits
come from `Int\UnitBgs.ILB` (8 × 100×100 backdrops indexed by `unit.[VMT+0xFC] & 0x7F`, bounds-checked)
— index-generic.

**No drag-and-drop exists.** No slot control has a drag handler; splitting is tick-checkboxes-then-PMove.

⚠ The DFM is immediately followed in `.rsrc` by `TDeformFaceDlg` (`0x0BCFC4`) — **cannot grow in
place**. +26 controls ≈ **+15.8 KB** → ~62 KB, needing **its own new PE section** (`.hcol` at VA
`0x612000` size `0x1C000` has only ~40 KB free). Per-control DFM sizes: Frame 646 B, Chk 790 B,
Gge 598 B, MIcon 564 B, EmpFr 567 B, EmpChk 539 B. Clones keep the original handler names
(`Unit1FrameMouseDown` etc. already read `Sender`), so no method-table extension.

### 6b. The map-hex stack number

`TArmyHS.Show @0x557914D8` encodes the count into a banner sprite index at **eight sites, in two
families** — four branches each (normal / concealed / alpha-blended / blinking). Concealed variants
use `Count − ConcealedUnitsCount`.

| family | index | sites | bytes |
|---|---|---|---|
| per-race banner, from `TRaceResourceList.GetRaceResource(AoWHSSet[+0x54], armyHS[+0x16])->[+0x1C]` | `Count + 0x1D` | `0x55791718`, `0x55791880`, `0x55791998`, `0x55791AF7` | `83 C0 1D` / `83 C2 1D` |
| independent banner, from `AoWHSSet[+0x78]->[+0x10]` (`Flags.ILB`) | `Count + 0x27` | `0x55791797`, `0x5579192E`, `0x55791A29`, `0x55791B79` | `83 C2 27` |
| extra overlay (when `army[+0x10] & 0x20`) | `armyHS[+0x16] + 0x50` | `0x55791762`, `0x557918CA`, `0x557919E2`, `0x55791B3D` | `83 C2 50` |

Count via `call [edx+0x54]` on `armyHS[+0x1C]`; blitted at `(x−5, y−12)` through image VMT `+0x84`
(opaque) / `+0x94` (alpha). Library bound in `TFlagControl.Create @0x5575A10C` via
`LinkToIL('Flags.ILB')` (string at `0x5575A17C`).

**Art — VERIFIED 2026-08-15 with `re_tools/ilb.py --all`.** `<game dir>\Images\Flags.ilb` (27,747 B)
and its half-res twin `_Flags.ilb` (13,483 B), **61 images each**, identical id maps. The relevant
`PartyShield.BMP` run, by **image id** (which is what `ImageLib.Get` takes — not array index):

| ids | what | sprite bytes |
|---|---|---|
| 38, 39 | PartyShield, counts −1 / 0 (unused) | 148 / 180 |
| **40 … 47** | **counts 1 … 8** — the digits | 380 each |
| 48 | count 9 — exists, reads as blank | 380 |
| **49, 50, 51** | **DO NOT EXIST — next id in the file is 70** | — |
| 70 … 75 | `TCUIcon.BMP` 12×11 | 264 |
| 80 … 91 | **12** further PartyShield sprites, purpose unconfirmed (12 = the player-colour count, cf. GREYB01-12 / GREYS01-12 at ids 10–21 / 22–33) | 196–216 |

Geometry: 21×19 canvas, 11×14 clip at (5,3), glyphs ~5×7 in `#003008`; low-res twin 11×10 canvas,
5×7 clip. `ImageLib.Get` has **no bounds check**, so ids 49–51 read whatever follows.

⚠ Note the shield range is contiguous 38…48 then jumps to 70, so **ids 49–51 can be appended without
colliding with anything** — the gap is 49–69, 21 free ids.

### ✅ Family B fully scoped 2026-08-15 — 14 libraries, 42 sprites, AND a code cave

The two families are **mutually exclusive, not layered**: `armyHS[+0x16] == 0x20` (unowned) → Family A
(`Flags.ilb`, `count + 0x27`); otherwise → Family B (the owner's **race** ILB, `count + 0x1D`).
(The nearby third `Get` — `Flags.ilb` id `flagID + 0x50`, ids 80–91 — is a per-race overlay drawn when
`army[+0x10] & 0x20`. Not count-indexed. **No work there**, and it explains what those 12 sprites are.)

**Family B is one ILB per race, bound from DATA not code.** `TRaceResource.LinkToIL @0x55759CDC`
sets `[+0x1C]` from a per-instance filename at `[+0x20]`, set by `SetImageLibraryName @0x55759DB0`
and serialised as **property id 8** in `TRaceResource.ReadWrite @0x55759F68`. The 12 names live in
`Release\Release.hss` at `0x29AFFA..0x29B6D1`: `RACES\{RHUMAN, RLIZARDS, RFROSTL, RELF, RHALFLNG,
RDWARF, RHIGHMAN, RDARKELF, RORC, RGOBLIN, RUNDEAD, RAZRAC}.ILB`.

| | libraries | new sprites | encoding |
|---|---|---|---|
| Family A | `Flags.ilb` + `_Flags.ilb` | 6 (ids 49,50,51 — **all free**) | type 17 RLESprite16 (`re_tools/ilb_rle16.py`) |
| Family B | 12 × `Images\Races\R*.ILB` | 36 | **type 22 Sprite16** (uncompressed RGB565 — trivial to author) |

**No half-res twin exists for Family B** — there is no `_R*.ILB` anywhere in the install. So 12, not 24.
Encodings differ between families, so the same source image cannot be dropped into both.

⚠⚠ **THE BLOCKER: race ILB ids 40 and 41 are ALREADY the city border art** (`BCS_*.BMP`).
`count + 0x1D` for counts 11 and 12 lands exactly there. Ids 40–45 are actively read by
`TCity.GetTopBorderImage @0x557AD824`, `GetMiddleBorderImage @0x557AD8D4`,
`GetTopCityActionImage @0x557ADACC` (ids `0x28`/`0x2B`, `0x29`/`0x2C`, `0x2A`/`0x2D`).
**You cannot simply append ids 39–41 to the race ILBs.** Family B therefore needs a **code cave on
the four `+0x1D` sites** (`add eax,0x1d` at `0x55791718`, `0x55791880`, `0x55791998`;
`add edx,0x1d` at `0x55791AF7` — all verified intact in the live DLL): for `count >= 10`, substitute a
different base so 10/11/12 land in a free block.

**Free id block to target: `24..27`** — free in all 12 race ILBs and read by nothing (4 slots, 3
needed). Also safe: `46..48`. **Avoid `39`** (free in 11 races, occupied in `RLIZARDS.ILB`) and
anything from ~49 up, which sits inside the `TRaceResource.GetCityImage @0x55759EBC` probe band.

**Family A needs no code change at all** — append 49/50/51 and the existing `count + 0x27` reaches them.

### ⚠ What happens at cap 12 with NO art work

`ImageLib.TCustomImageLibrary.Get` (ILPACK `0x5521A8B8`) is a raw `mov ecx,[[eax+0x48]+edx*8]` — no
bounds check, **no nil check** — and `TArmyHS.Show` immediately virtual-calls through the result
(`(**(code**)(*result + 0x94))(...)`). A bounds-checked twin `GetSafe @0x5521A8E0` exists; `Show`
does not use it. So *(inference from static analysis, not observed in-game)*:

| stack | result |
|---|---|
| count 9, any owner | **safe today** — race id 38 / `Flags` id 48 both exist as a deliberate **blank shield**. The original devs left a graceful overflow at 9 |
| owned, count 10 | **NULL deref → access violation** in 11 of 12 races (Lizardmen instead draws a 12×10 `TCUIcon.BMP`) |
| owned, count 11 | draws race id 40 = `BCS_*.BMP`, a 57×2 city-border strip |
| owned, count 12 | draws race id 41 = `BCS_*.BMP`, a **57×50 city-border block** blitted at (x−5, y−12) over the hex |
| independent, count 10–12 | **NULL deref** — `Flags.ilb` 49/50/51 don't exist |

### Two-digit glyph feasibility

Canvas is **21×19** on every frame in every library; the digit box is **5×7 at (8,5)** in 10 of 12
races and in `Flags.ilb` (Dwarf 5×7 at (8,6)). Usable interior is 9–11 px wide (the outer 1 px each
side is badge rim). **Two 4×6 glyphs + 1 px gap = 9 px — fits every race**, but needs a bespoke
narrow digit set. Tightest: Elf / Highmen / Dark Elf narrow to 9 px from the fifth digit row down.
Roomiest: Dwarf (13 px) and Goblin (13×13 disc).

❌ **Half-res `_Flags.ilb` cannot do two digits** — canvas 11×10, clip 5×7@(3,2), existing glyphs are
3×3 (a "1" is 1×3). That frame needs a different treatment: a marker glyph, a dot, or reuse the blank.

⚠ Race ids **28/29** and `Flags` ids **38/39** occupy the `count −1` / `count 0` slots and hold
non-shield art (a cyan splash; a pair of grey wedges). The concealed branch
(`count − ConcealedUnitsCount + 0x1D`) **can reach id 29 at zero**, so they are **not** free to
overwrite. *(Inference — no call site found that reads them deliberately.)*

**No editor work.** `TArmyHS.Show` is a VMT method on a class constructed inside `AoWEPACK.dpl`; no
exe imports it by name (checked `AoW.exe`, `AoWDevEd.exe`, `AoWEd.exe`, `AoWTCPCK.dpl`, `aowInt.dpl`).
One DLL cave plus the art files covers game and editor together. `AoWTCPCK.dpl` references neither
`Flags.ILB` nor `RACES\` nor `PartyShield` — no stack-count banner in tactical combat.

All 14 files parse cleanly with `ilb.py` and are **md5-identical to `Ziggurat upload\Images\`**.
⚠ `re_tools/ilb_rle16.py` fails to decode `Flags.ilb` ids **38, 39, 86, 90** (`row N: L+M+R != width`)
— a codec limitation on multi-literal-span rows, not a directory desync. Ids 40–48 (the whole count
series you clone from) decode cleanly at 380 bytes each with an identical silhouette.

⚠ So the art job is four new count frames (9–12) in `Flags.ilb`, `_Flags.ilb` **and every race's
banner library** (the `Count + 0x1D` family) — the race ILBs were not enumerated and should be
scoped before committing. "10/11/12" are two digits in an 11×14 glyph box: needs a narrower font, a
larger clip inside the 21×19 canvas (there is slack), or bitmap-font text.

`TFlagControl.ShowFlag`/`ShowStructureFlag` (player-colour banners on cities, `mod 12` into
GREYS01..12, ids 22..33) are a different mechanism and unaffected.

### 6c. The other `U1..U8` dialogs

Runtime rect fields: `TAoWComponent +0x0C` Tag · `+0x7C` W · `+0x80` H · `+0x84` Left · `+0x88` Top ·
`+0xCC` parent AOWWindow. `TAOWCheckBox +0xB0` checked; VMT `+0xAC` SetChecked, `+0x6C` SetVisible.
DFM `Left`/`Top` are designer-only — use `WinLeft`/`WinTop`.

| dialog | VMT | DFM foff | window | slot panel | 12 in one row | verdict |
|---|---|---|---|---|---|---|
| `TArmyInfoDlg` | `0x4475A0` | `0x079B60` | 440×270 | `UnitPnl` (35,171) 370×61, U at 0..323 pitch 46, 45×54 | 553 → 624 | fits, but **2 rows of 6** safer |
| `TPartyJoinDlg` | `0x437734` | `0x13D814` | 440×270 | same | same | same |
| `THeroInfoDlg` | `0x447CEC` | `0x0E9554` | 480×376 | `UnitPnl` (70,235) 345×60, pitch 43, ~42×53 | 516 → **652 > 640 ✗** | **no room** — 2 rows needs ~434 vs 432 ceiling. Needs shrunk icons or real re-layout |
| `THeroJoinDlg` | `0x4382E8` | `0x0EBCC8` | same | same | same | same |
| `TRealmWin` | `0x4484F0` | — | — | `Unit1LB..Unit8LB` are **table columns**, Tag = column | — | not a stack surface, but truncates a 12-stack |
| `TArenaDlg` | `0x44BDA8` | — | — | already repurposed by this project's Arena rework | — | U1..U3 = tier rows, U4..U8 `Visible=False` |

Handlers for the Info/Join dialogs are already Tag-driven and `TUnitList.Count`-bounded
(`0x00447940`, `0x00447ABC`); their `U1..U8` fields are contiguous (`+0x48..+0x64`, `+0x68..+0x84`).
Roughly +587 B per cloned control (~2.3 KB per dialog), +16 B instance size.

**`aowInt.dpl` needs nothing** — 35 classes, 558 exports, zero Party/Army/Unit/Stack/Slot symbols,
one generic `TDialog` DFM. It supplies widget classes only (`TAOWCheckBox` VMT `0x598119BC`,
instance `0x140`, `SetChecked 0x59811B38`).

**Confirmed not affected:** `Int\Units.ILB` "8"s (nine-patches) · `Int\UnitBgs.ILB` (backdrops) ·
`Images\tcunits.ILB` 7×8 (facings) · `TUnitWindow BP1..BP8` (backpack) ·
`TFastCombatWindow Party1..7Pnl` (7 army panels) · `TSpellBook S1..S8` (spell page slots) ·
`TGamePlayDlg Sim1..8CB` (options) · `TCityScreen`/`TProductionScreen` (no garrison list — the city
garrison uses the normal party bar; there is no "transfer units" screen) · `TUnitBanner`/`TInfoBanner`
(single-unit hover cards) · `TMWindow`.

---

## 7. Enchantment / ability targeting (AoW.exe)

Two structurally identical dialogs. **Both must change or the ability path stays at 8.**

| dialog | purpose | VMT | field table | instsize | DFM foff | RCDATA |
|---|---|---|---|---|---|---|
| `TCastUnitSpellDlg` | unit spells / enchantments cast at a stack | `0x00431ACC` | `0x00431AF4` (39) | `0xE4` → `0xF4` | `0x08D694` | `TCASTUNITSPELLDLG` RVA `0x91494` size `0x56B5` |
| `TUnitSelectionDlg` | unit abilities at a stack (Healing, Dispel Magic) | `0x004449D4` | `0x004449FC` (25) | `0xB0` → `0xC0` | `0x1E53FC` | `TUNITSELECTIONDLG` RVA `0x1E91FC` size `0x379E` |

Eight discrete `TAOWCheckBox` `U1..U8` parented to `UnitPnl` via the `AOWWindow` ident property, all
sharing one `OnChange` (`U1Change`) and one `OnPreDraw` (`U1PreDraw`), distinguished by `Tag` 0..7.
The unit portrait is painted into the checkbox by the PreDraw handler; the checkbox's `Checked` state
is the selection. Fields `U1..U8` at `+0xA0..+0xBC` / `+0x68..+0x84`.

**Call path:** `TUnitSpell.SetupTargetSelection 0x5577B014` → `TargetPartySelected 0x5577B1DC` →
`SetupUSC 0x5577AD34` (fills the caster: `+0x08` spell id, `+0x0C` target unit, `+0x14` unit list,
`+0x19` multi flag, `+0x1A` valid mask) → notify list `AoWHSMap+0x1E0` →
`TMapEvents.TheMapCastSpell 0x004500F0` → dialog show `0x00431E40`.
Ability path: `THealingAbility.Activate 0x5576C558` / `TDispelMagicAbility.Activate 0x5576D59C` →
`TUnitSelectorAAI` → `AoWHSMap+0x1E4` → `TheMapActivateAbility 0x0044E94C` → show `0x00444CE0`.

**Click → bit** (`U1Change @0x004323B0`, `Sender` in EDX): read `Sender.Tag` at `[esi+0x0C]`; if
checked and multi-flag `[caster+0x19] == 0` → `SetSelection(1 << tag)` (radio) else
`SetSelection((1<<tag) | old)`; unchecked → `SetSelection(~(1<<tag) & old)`. Then resync all 8
checkboxes from mask bits, click sound (`0x455DFC`), `CanCast` (VMT `+0x4C`) → label colour + mana.
No re-entrancy risk: `SetChecked` only fires `RadioChange` when `RadioIndex > 0`, and all eight are 0.

⚠ `SetSelection` does not just store — it round-trips through `ValidateUnitSelection` (§3b) and
stores the *filtered* result. That is why a bad table byte makes checkboxes untick themselves.

| VA | what | at 12 | `.reloc`? |
|---|---|---|---|
| `0x00432090`–`0x0043210F` | 8 unrolled `Ux.SetChecked(false)`, 16 B each | loop, 128 B reclaimable | **none** |
| `0x0043241E`–`0x004324F5` | 8 unrolled resync, bit consts `01 02 04 08 10 20 40 80`, 27 B each | loop + 16-bit test, 216 B | **none** |
| `0x004323EA / FA / 0x0043240C` | `mov dl,1 ; shl dl,cl` (`B2 01 / D2 E2`) | 16-bit shift | |
| `0x00432342`–`0x00432353` | `movzx eax, byte[caster+0x1A]; shr eax,cl; test al,1` → "forbidden" overlay (ImageLib idx 7) | 16-bit read | |
| `0x004326A4` `U1PreDraw`, `0x0043222C` `DrawUnitSlot` | already index-generic, guarded on `GetUnitCount` | **free** | ⚠ `DrawUnitSlot` has **4 `.reloc` entries — do not displace** |
| `0x00444C61`–`0x00444CCE` | `TUnitSelectionDlg` 8 unrolled SetChecked | loop, 110 B | **none** |
| `0x00445068`–`0x0044512D` | 8 unrolled resync from `byte[selector+0x14]` | loop, 198 B | **none** |
| `0x0044503A / 47 / 57` | byte `shl dl,cl` | 16-bit | |
| `0x00444F9F` | `movzx eax, byte[selector+0x16]` valid mask | 16-bit | |

**Geometry — 3×4 fits with room to spare.** `Dlg` 492×236 (Modal, `awCenter/ahCenter`,
`Resizable=False`, Max 0). `UnitPnl` (28,115) **437×60**; U1..U8 WinLeft **0, 55, 110, 165, 220, 275,
330, 386**, WinWidth 50; portrait clip `(X+5,Y+4)`–`(X+46,Y+56)`. `SelectionInfoPnl` (28,180) 437×20;
bottom band WinTop 198, `ahBottom BottomOffset=11`.

- 8 slots occupy 435 of 437 px — **exactly full, a 9th does not fit.**
- 12 in one row = 655 px content → `Dlg` ≈ 711 px → **over the 640 clamp. Ruled out.**
- **3 rows × 4 at full size:** content 215 px wide (centre at WinLeft 111/166/221/276), rows at
  WinTop 0/62/124 → 184 px tall. `UnitPnl` 60→**186**, `SelectionInfoPnl` 180→**306**, bottom band
  198→**324**, `Dlg` 236→**362**. Width unchanged. **492×362 vs 640×432 — 70 px vertical / 148 px
  horizontal headroom. No clamp risk, and no geometry-healing cave needed.**
  (2 rows × 6 is the cheaper alternative: 492×298.)
- Free budget: the eight `TAoWGauge` `Unit1Gge..Unit8Gg` (`+0x44..+0x60`, WinTop 62, 30×2) are
  `Visible=False` **and referenced by zero bytes of code** in `0x431E40..0x4327E4` — dead leftovers
  copied from `TControlWin`. Do not replicate them. *(Inference from a disassembly-wide field scan +
  the DFM flag; not proven by running the game.)*
- ⚠ **Neither DFM can grow in place**: `TCASTUNITSPELLDLG` occupies `0x8D694..0x92D49` with
  `TCHATWINDOW` at `0x92D4C` — **3 bytes of slack**; `TUNITSELECTIONDLG` has 2. Deleting the root's
  designer-only `Left/Top/Height/Width` frees only 33 B vs the ~2.6 KB four checkboxes need.
  **Relocate to a new PE section**, as `build_herodlg_columns.py` already does. `TAOWCheckBox` is
  already in the class palette — no palette work.

**Owner: `AoW.exe` alone** (+ `AoWCompat.exe` in lockstep). Both dialog names are **absent** from
`AoWDevEd.exe` and `AoWEd.exe` — the editor has no spell-targeting UI. `AoWTCPCK.dpl` has **no DFM
forms at all**, so there is no combat-side equivalent. Live `AoW.exe` byte-diffed against
`Ziggurat upload/AoW.exe` over both dialogs' code and DFMs: **0 differing bytes.**

**Other targeting surfaces checked and clear:** `TTargetSelectionDlg 0x4445D8` (on-map prompt, no
slots) · `TDisjunctionDlg 0x43285C` (listbox) · `TDeformFaceDlg 0x445340` (one hero) ·
`TMagicWin 0x42C190` (listboxes) · `TSpellBook 0x42DDA8` (`S1..S8` = spells per page) · combat spell
targeting (`TTCMapEvents.TCMapCastSpell 0x458C80`, hex/unit via listbox). There is **no** "confirm
which units to enchant" second step — `CastButClick 0x4321AC` goes straight `CanCast` → `Cast`.

---

## 8. Tactical combat (AoWTCPCK.dpl)

**The tactical engine does not care how many units are in a stack** — every container is a
`TList`/`TByteList`/`TENode`. The only structural blocker is deployment position lookup.

### 8a. `TUnitPositionControl` — the deployment table

Instance `0xC`; holds an `HSEngine.TXYLList` at `[self+8]` of packed dwords
`x | y<<8 | 0<<16 | facing<<24`. **Index = `party*8 + slot`, party 0..6, slot 0..7 → 56 entries.**
Addresses at preferred base `0x00400000` (rebases — caves must be PIC).

| VA | file off | bytes | role |
|---|---|---|---|
| `0x00428964` | — | — | `GetUnitPosition(EAX=self, EDX=party, ECX=slot)` |
| `0x00428973` | `0x27D73` | `6B 45 F8 `**`08`** | stride |
| `0x004289C0` | — | — | `SetUnitPosition` |
| `0x004289CF` | `0x27DCF` | `83 7D F8 `**`07`** | party bound — **keep at 7** |
| `0x004289D5` | `0x27DD5` | `83 7D F4 `**`08`** | **slot cap — silently drops slot ≥ 8** |
| `0x004289DB` | `0x27DDB` | `6B 55 F8 `**`08`** | stride |
| `0x00428A04` | — | — | `ValidatePosition` (editor free-slot finder) |
| `0x00428A19` / `A64` / `ACD` | `0x27E19` / `E64` / `ECD` | `6B D0 `**`08`** | stride ×3 |
| `0x00428A92` / `A9E` / `AFB` / `B07` | `0x27E92` / `E9E` / `EFB` / `F07` | `66 83 F8 `**`08`** | slot wrap ×4 |
| `0x00428B34` | `0x27F34` | `66 83 F8 `**`07`** | party wrap — keep |
| `0x00428CB2` | `0x280B2` | `6B C0 `**`08`** | `TUnitPositionHS.UpdateImageIndex` sprite index |

All thirteen are single imm8 bytes (`08`→`0C`), **none carrying a `.reloc` entry**.

**The data is not in the binary.** It comes from `TUnitPositionHS` markers (ClassID `0x220103`) on
the tactical map, registered by `Activate @0x00428CD8`, cleared by `Deactivate @0x00428DF4`. Marker
fields: `+0xC` party (HSM tag `0x19`), `+0xD` slot (tag `0x1A`), `+0x18` facing (tag `0x1B`);
`ReadWrite @0x00428EE8`. Created only by the editor (`MsgProc @0x00428B44`, msg `0x10005`) or
deserialisation.

**Marker census across `<game dir>\TCMaps\*.HSM` (59 files, `"CFS\0"` + version byte + zlib):**

| coverage | files |
|---|---|
| 56 = parties 0–6 × slots 0–7 | **43** (corrected 2026-08-16; the earlier table summed to 65 against 59 actual files) |
| 48 = parties 1–6 | `CiyW1.HSM` (siege — party 0 uses the hard-coded table below) |
| 24 = parties 0–2 | `eCrpt000`, `eDung000` |
| 18–20 | `base_struct`, `eCrpt001`, `eMrLr000..003`, `eRuin000/001`, `eZigg000/001` |
| 16 = parties 0–1 | `CaveE000`, `Telep000`, `eDung001` |

No map defines a slot above 7. Doing this properly = **+4 markers per defined party across all 59
maps** (56 → 84 on most). Loaded via `TRndTacHsm.RandomMap` → `THSEngine.LoadHSMEx @0x00424F96`;
filename assembled from the string table at `0x004263A8`+.

### 8b. `DefPosX` / `DefPosY` — the 6 × 8 siege table

| symbol | VA | file off | size |
|---|---|---|---|
| `AoWTC.DefPosX` | `0x00467024` | `0x66024` | 48 signed dwords |
| `AoWTC.DefPosY` | `0x004670E4` | `0x660E4` | 48 signed dwords |

48 = 6 attack directions × 8 slots. Used by `TRndTacHsm.SetupUnit @0x00426D1C` **only** for side 1 /
party 0 (the city garrison) in wall combat:

```
0x00426E3B  imul eax, eax, 8            ; (attackDirection-1) * 8
0x00426E45  add  eax, [ebp-0x24]        ; + slot
0x00426E4F  bound eax, [0x4271DC]       ; 0..47
0x00426E55  mov  eax, [eax*4 + 0x467024]   ; DefPosX  (.reloc at 0x00426E58)
0x00426E88  mov  eax, [eax*4 + 0x4670E4]   ; DefPosY  (.reloc at 0x00426E8B)
```

Values cluster on map centre (32,29): X 26–38, Y 26–32. The two tables are adjacent and immediately
followed by `TCAttack @0x004671A4` — **cannot grow in place, must be relocated**. Both referencing
displacements already carry `.reloc` entries, so a relocated table works under rebasing.

⚠⚠ **CORRECTED 2026-08-16 — `DefPosX`/`DefPosY` is NOT siege/city-garrison only.**
`[TRndTacHsm+8]` is set from `RandomMap @0x00424661`, so this table governs the **centre-hex
defending party in ordinary battles too**. The `bound {0,47}` range-check therefore faults at
slot ≥ 8 in the **common case**, not just in sieges. This raises the table's priority from
"siege polish" to "must ship with the cap".

Also in `SetupUnit`: a per-slot default-facing jump table with exactly 8 cases
(`cmp eax,7 / ja` at `0x00426EAD`, table at `0x00426EBD`). Slots 8–11 fall through to no
`SetDirection` — harmless.

### 8c. ⭐ The escape hatch — placement already spirals

`SetupUnit` does **not** place a unit at its marker hex. It runs an uncapped spiral
(`0x00427082`–`0x004270F8`):

```
n = 0
repeat (hx,hy) = CenterHNtoHX(markerX, markerY, n); n++
until  field(hx,hy).overlay != 8 (Obstacle) and field(hx,hy).Get(0x220104 TTacticalCombatUnitHS) == nil
PlaceHX(...)
```

Duplicate deployment hexes are therefore already tolerated and resolved by displacement.
**Minimal viable version: patch the stride to 12 and make slots 8–11 fall back to `slot mod 8` — no
`.HSM` editing at all.** Cost: sloppier formations, and `TTacticalCombatUnit.GetPosValue @0x0041CE94`
(`atk + dam + def + hits/3`, used at `0x004268CE` to give the strongest units the low slots) stops
meaning much for the extras.

⚠⚠ **THE .HSM MARKER PASS IS TECHNICALLY BLOCKED, NOT A TASTE CALL** (found 2026-08-16, narrowed on
re-verification same day). `PlaceCombatUnits`' item-scatter block indexes an 8-entry local by
**`Random(XYLList.Count − 17)`**, range-checked by `bound {0,7}` at `0x00426C3C` / `0x00426C54`.
Adding markers to a map — **or widening the stride** — pushes that index out of range and produces a
range-check fault on entering a **Crypt / Monster Lair / Ruin / Ziggurat** battle *(Dungeon is
exempt — its branch never arms `[self+4]`)*, when the marker count reaches ≥ 25 **and** the site
holds ≥ 1 item. The spiral fallback avoids this entirely and costs nothing.
**Recommendation: skip the marker pass permanently** unless that block is patched too. Note the
scatter block's own constants (`0x426BC1`, `0x426BFA`, `0x426C25`, the party-2 sites, and the bound
pair at `0x426D14`) sit **outside** the §8a 13-site inventory.

### 8d. What happens today without the fallback

- `TXYLList.Put` auto-grows (`SetCount(idx+1)`, HSEPack `0x556058AC`/`0x556059F0`), filling new
  entries with the default set by `TUnitPositionControl.Create @0x004288B8` = `PackXYL(-1,-1,-1)` =
  `0x00FFFFFF`. `TXYLList.Get @0x55605680` returns that default out of range — no exception.
- **Parties 0–5, slots 8–11** → `party*8 + 8..11` lands on the **next party's slots 0–3**. Units
  deploy inside a neighbouring stack's formation; the spiral scatters them off. Wrong-looking,
  non-fatal.
- **Party 6, slots 8–11** → index 56–59 ≥ Count(56) → `0xFFFFFF` → `hx = hy = −1`.
  `HSEngine.TMapLevel.GetField @0x556087B8` is **completely unchecked**
  (`[level+0x78][y*4] + [level+0x74][x*4]`) → garbage `TMapField*` → the following
  `movsx eax, byte[field+0x15]` and virtual call `[field]->vmt[0x80]` at `0x004270B2`/`0x004270DA`
  will almost certainly access-violate. *(Inference — the OOB reads are measured, the AV is not.)*
- **It fires in the pre-battle overview too**, i.e. at the tactical/auto choice dialog, before combat
  starts: `OverviewUnit.PlaceOverviewUnit @0x004378A8` calls the same `GetUnitPosition` at
  `0x004378E2`; AoW.exe call sites `0x0043B09C` and `0x0043F32E`.

### 8e. Room, ceilings, containers

- Combat map **65 × 59** (`TAoWNewCombatMapSettings.Create @0x0041B270`: `+4 = 0x41`, `+8 = 0x3B`,
  `+0xC = 1`), with a 6-hex border painted by `InitializeNewMap @0x0041B884` → **~53 × 47 ≈ 2,490
  playable hexes** for what is today 56 units. Space is a non-issue.
- **Per-battle ceiling is 56 today, 84 at 12.** A battle covers the centre hex + its 6 neighbours:
  `TCombat.AddAdjacentArmies @0x5572760C` walks `while radius < 2`;
  `TCombat.GetPartyPosition @0x55727764` returns the hex number (0 = centre, 1..6 = ring, 7 = not
  adjacent, remapped to 1 by `PlaceCombatUnits @0x00426782`). Next ceiling above that:
  `TCombat.CreateUniqueCOID @0x557272D4` = 255 combat objects per battle. 84 is fine.
- Instance sizes: `TAoWCombatMap 0x138`, `TTacticalCombat 0x50`, `TTacticalCombatUnit 0x68`
  (base `TCombatUnit` `0x5C`; `+0x64` slot, `+0x65` party set in `PlaceCombatUnits @0x0042675B`),
  `TTacticalCombatUnitHS 0x48`, `TUnitPositionHS 0x1C`, `TRndTacHsm 0xE7C`.
- `TAoWCombatMap+0x12A` is an **8-byte party→side array** (init at `0x0041B573`, written
  `0x00426851`) — indexed by party, **not** by unit. Unaffected.
- **No unit-indexed `[8]` array exists in the tactical module.** All 11 `bound 0..7` pairs index
  either that party array or `PlaceCombatUnits`' local `used[8]`. The ~28 `cmp ,7` sites in `TCAI.*`,
  `CombatRoad.*`, `CombatHex.*` are `for i := 0 to 6` over the hex neighbourhood.
- Turn order is not an array: player order = `TCombatData+0x40` `TByteList`
  (`TTacticalCombat.Initialize @0x00429088`); unit order = `TAoWCombatMap.GetNextUnit @0x0041C1B8`,
  a linear walk over `TCombatData.GetCount/GetObjects`.
- **No reinforcement mechanic** — `AddAdjacentArmies` runs once from
  `TCombat.InitDefaultArmies @0x55727C85`. Flee locations (`FleeLoc.TFleeLocation`, ClassID
  `0x220528`, 10–30 per map) are ordinary map objects, not party/slot indexed.
  `TTacticalCombat.Finalize @0x00429418` iterates dynamically.
- ⚠ **Editor art:** `UpdateImageIndex @0x00428CA4` uses `party*8 + slot` as an index into
  `Images\tcunits.ILB`, which holds **exactly 57 images**. At 12 slots the index reaches 83 and
  `ImageLib.Get` has no bounds check → garbage or a crash in `AoWEd.exe`. ⚠ **id 60 is already
  occupied**, so a naive "extend to 85 frames" collides — clamp the index instead, or pick a free
  id block. (Corrected 2026-08-16.)
- **Live file is clean here.** Live `AoWTCPCK.dpl` vs `Ziggurat upload\AoWTCPCK.dpl` (2025-03-21):
  24 bytes over 6 runs, all in `TCAI.EvalBattle` (`0x418xxx`) and `0x438100`.
  `TUnitPositionControl`, `SetupUnit`, `PlaceCombatUnits` and `DefPosX/Y` are byte-identical.
  ⚠ Neither copy is provably pristine — there is no vanilla `AoWTCPCK.dpl` on disk.

---

## 9. Auto-resolve and AI — clean

`TFastCombat` (`Create 0x55744500`, `Execute 0x55744A0C`, `ExecuteCombatRound 0x5574482C`) descends
`TCombat` and holds nothing fixed-size. Objects live in `TCombatData` (`GetCount 0x55728BEC`,
`AddObject 0x55728CE0`), a `TList`; initiative is a `TByteList` at `TCombatData+0x40`;
`TCombatSide` (`Create 0x55726D60`) is a bare `TENode`. `TCombat.AddArmy @0x55727804` loops
`for i := army.Count-1 downto 0`, unbounded. **A 12-unit stack neither truncates nor overflows in
auto-resolve.**

`TAIGroup` is a plain `TUnitList` (`AddUnit 0x557377B4`, `AddUnits 0x55737840`,
`TAIGroupControl.Split 0x55738F18`, `CombineIdleGroups 0x55738B7C`) — no 8 anywhere. What breaks is
the group→map bridge: `RetrieveGroupArmy 0x55738B14` (byte truncation) and the move executer's hard
clamp + byte masks.

`TAIMoveExecuter.CreateArmies 0x5574251C` uses a Delphi `set of 0..7` — but over the **transport
status enum**, not unit slots. Harmless (same idiom in `PlaceRandomUnits` and
`TArmyInfoEventLog.Execute`).

**Stack generators and their caps:**

| generator | VA | cap |
|---|---|---|
| `TStructure.GenerateRazeDefenders` | `0x5575FD1C` (trim at `0x5575FDF1`, `83 F8 08`) | **≤8, independent of `TArmy`** ⚠ prologue is live-patched by `build_razebattle_tower.py` / `build_razeroster_vary.py`; the trim itself is vanilla |
| `TCity.GenerateRazeDefenders` → `GenerateRebelUnits` | `0x557AB408` → `0x557ABCAC` | none — gold budget (25 × size) |
| `TCity.GenerateDefenders` → `PlaceRandomUnits` | `0x557AB6DC` → `0x5575AEF8` | none — budget only, packed indirectly via `CanPlace` |
| `FillWithRandomUnits` | `0x5575B160` | none (live-patched at `0x5575B2C9` by `build_arena.py`) |
| `TCrusade.PlaceParty` | `0x557ED1EC` | none — `build_crusade_spawns.py:91 ARMY_CAP = 8` is a **Python warning constant only**, no binary counterpart |
| `TAIMoveExecuterUnitList.ValidateSelection` | clamp at `0x5573ECC6` + `0x5573ECCB` | **AI hard clamp to 8** — the AI can only ever act with units 0–7 |

⚠ **`GenerateRazeDefenders`' ≤8 would NOT follow a `TArmy` cap change.** Left alone, defender and
rebellion rosters stay at 8 while player stacks reach 12 — a silent balance tilt toward the player,
and exactly what the raze predictor was calibrated against.

**No separate city garrison cap exists.** A city's defence is whatever `TArmy`s stand on its hexes
(`TCity.InitCombat 0x557ACD58` → `TCombat.InitDefaultArmies 0x55727BCC` → `AddAdjacentArmies`), so
garrison size = hexes × `MaxSize`. `TCity.GetDefenseRequirements 0x557AA454` reasons in gold, not
head-count.

**Network:** `Network.dpl` (196 exports) and `aowDPlay.dpl` (130) contain **zero** army/unit/
selection/party/combat symbols — a generic transport layer. The game-level wire format is the
EventLog system inside AoWEPACK, where the byte masks of §3a live.

---

## 10. The editors

`TArmyEditForm` "Army Properties" uses a `TUnitGrid` with the limits **baked into the DFM**:

```
TUnitGrid 'UnitGrid'  W203 H117
  ColCount=4 RowCount=2  MinColCount=4 MinRowCount=2  MaxColCount=4 MaxRowCount=2
  GrowDirection=ilHorizontal  ScrollBars=ssNone
  DefaultColWidth=48 DefaultRowHeight=54 GridLineWidth=2
```

`TArmyEditForm.AddBtnClick @0x0041A344` (AoWDevEd.exe) thunks into
`UnitGrid.TUnitGrid.AddUnit @0x558036B4` (AoWEPACK.dpl), which opens with:

```
cells := self[0x73] * self[0x74];                     ; MaxColCount × MaxRowCount
if cells <> 0 and unitList.Count >= cells then exit;  ; silent refusal
... then CanAddUnit ([list+0xA4]) and AddUnit ([list+0xAC])
```

✅ **PROVEN, not inferred (2026-08-16):** `SetMaxRowCount @0x55214F10` writes `[+0x1CC]` and
`SetMaxColCount @0x55214F2C` writes `[+0x1D0]`. ⚠ Also: `TCustomGrid.Create` defaults `ScrollBars`
to **`ssBoth`**, and the delete-then-re-add edit costs **+23/−19 bytes** against 2/0/0 bytes of
slack — so the `ScrollBars` half of option 2 does **not** fit in place in two of the three forms.

**Three forms clamped to 4×2 = 8, in both editors — six edits:**

| form | control | AoWDevEd.exe | AoWEd.exe |
|---|---|---|---|
| `TArmyEditForm` | `GroupBox1/UnitGrid` | `0x48588` | `0x477C8` |
| `TDungeonEditForm` | `PrisonersSheet/…/PrisonersGrid` | `0x4AFD8` | `0x4A218` |
| `TExplorationSiteEditForm` | `DefendersSheet/…/DefendersGrid` | `0x4BBB0` | `0x4ADF0` |

Two options, both in-place RCDATA DFM edits:

1. `MaxRowCount 2→3` (4×3 = 12) + geometry: grid `H117→~171`, `GroupBox1 H153→~207`, form
   `ClientHeight 332→~386`, buttons at `T20/64/108` re-spaced. Five numbers per form.
2. **`MaxColCount→0`** to disable the grid cap and let `TArmy.CanAddUnit`/`MaxSize` be the single
   gate — then also `GrowDirection→ilVertical`, `ScrollBars→ssVertical` (mirroring the uncapped
   `TUnitIndexGrid` forms) so extra rows are reachable. Fewer magic numbers, survives a later cap
   change.

⚠ **A 14th code-side site, found during verification 2026-08-15.**
`UnitGrid.TUnitGrid.Create @0x55803358` sets a **runtime default of 1 row × 8 columns**:

```
5580338C  call ImageLib.TCustomImageDrawGrid.SetRowCount   ; edx = 1
55803391  mov  edx, 8                                      ; BA 08 00 00 00
55803398  call ImageLib.TCustomImageDrawGrid.SetColCount   ; <-- default 8 columns
5580339D  mov  edx, 0x30 -> SetDefaultColWidth  (48)
558033A9  mov  edx, 0x30 -> SetDefaultRowHeight (48)
```

This resolves an apparent contradiction between two passes: the **constructor** defaults to 8
columns / 48×48 cells, and the editor **DFM then overrides** it to 4×2 / 48×54 with
`MaxColCount=4 MaxRowCount=2`. Both observations were correct. Any `TUnitGrid` created *without* a
DFM override therefore still lays out 8 columns — patch `0x55803391` too, or accept the default.

Resource-side grids (`TExplorationSiteResourceEditForm/DefendersGrid`,
`TConstructionResourceEditForm/RazeDefendersGrid`, `TDungeonResourceEditForm/PrisonersGrid`) are
`TUnitIndexGrid` with `MaxRowCount=0` — already uncapped; they hold unit *types*, not armies.

These forms are plain VCL, so the 640×432 manager clamp does **not** apply. ⚠ `build_copper_medal.py`
already patches an AoWDevEd.exe byte in this area (`CAP_DEVED_VA`, the transport-capacity spin write)
— don't fight it.

**`AoW.exe` has no VCL grids at all** (custom AOW window toolkit), so this DFM work is editor-only.

---

## 11. Balance consequences

**Scales automatically (dynamic list walk — ~50% stronger at 12):**

| feature | mechanism | effect |
|---|---|---|
| **Drillmaster** (`0xAB`) | `TArmy.NewTurn @0x5578F79C` cave counts Drillmasters, +N XP/turn to each non-Drillmaster | ceiling **+7 → +11 XP/turn**. `Drillmaster_Ability.md:151`'s "self-limiting, but clampable" justification fails — revisit |
| **Leadership** (`0x2E`, 4 levels) | `TArmy.UpdateFormation @0x5578D034` two-pass max-override aura | beneficiaries 7 → 11 per leader; aura is max-override not additive, so per-unit strength is unchanged but stack value rises ~50% |
| **Vision 9 levels** | `TArmy.UpdateVisibilityRanges @0x5578E10C` takes the stack **maximum** | max-of-N: higher expected max. ⚠ `[army+0x29]` nibble pair has no clamp — base + cap must stay ≤ 15 |
| **Concealment / True Seeing** | `TArmy.UpdateConcealment @0x5578C98C` — fully concealed only if **every** unit is | strictly **harder** at 12 |
| **Movement prediction** | `MovePoints 0x5578D8D0` = MIN across units; `CreateMovePointTable 0x5578DC40` = element-wise MAX | O(units) — the flood-fill perf rejection in `older/AoW_Movement_Prediction_Bug_Analysis.md` is an 8× argument, becomes 12× |
| **Command abilities** (Seduce/Charm/Dominate) | `TCommandAbility` data holds a `TIntegerList` at `data[+0x10]` — no fixed capacity | scales; stolen units get ~50% more room. Nothing applied yet |

**Needs a deliberate decision:**

- `GenerateRazeDefenders` ≤8 (§9) — raise to 12 or accept the tilt.
- `Raze_CombatPredictor_Analysis.md:533`'s "Lone Great Eagle vs max-size city militia (8 units, 2
  archers): DENIED" is a **named regression test** that needs re-baselining. The whole suicide-raze
  model (`AI_Raze_Decision_CodeMap.md:270`) is calibrated on 8-vs-8.
- `build_crusade_spawns.py` — `ARMY_CAP = 8` at line 91, and the hand-tuned `SPEC` table
  (lines 110–124; line 123 notes a stack was trimmed from 9 to "the 8-unit army cap"). Stacks become
  under-full at 12.
- `build_party_random.py:105` — `[(1,4,1),(2,2,2),(3,1,1)]` "Large" maxes at exactly 4+3+1 = 8.
  Implicit, unnamed. Mirrored in `party_dialog.py:88`'s caption text.
- `build_arenadlg.py:63,174,176` — hard-coded `U1..U8` control list, `HIDE` list for U4–U8. Needs
  re-deriving if the Arena is ever reverted to unit training.
- Transport capacity values in `Release/Unitres.pfs` (§5) — Ziggurat-tuned against a ceiling of 8.

**Docs that become wrong and need fixing at source:** `Drillmaster_Ability.md:151` ·
`Investigation_Crusade_Spell.md:147-151` · `Arena_Rework_Feasibility.md:53,181,254,276,293,553,880` ·
`AI_Raze_Decision_CodeMap.md:270` · `Raze_CombatPredictor_Analysis.md:533,1208` ·
`Party_Random_Generator.md:241,246` · `older/AoW_Movement_Prediction_Bug_Analysis.md:60,64,277,280`.

---

## 12. Cave space (as of 2026-08-15)

| binary | highest used | allocate from | ceiling |
|---|---|---|---|
| `AoWEPACK.dpl` CODE | `0x55817800` (end of `build_marksmanship8.py`'s reserved block) | **`0x55818000`** | `0x558E7918`; stay under `0x558E7000` |
| `AoWEPACK.dpl` BSS (mutable state) | `0x558FA960` (combatdiag) | `0x558FA844`–`0x558FA900` and `0x558FA964`–`0x558FB000` | `.idata` at `0x558FB000` |
| `AoW.exe` | `0x0062E000` (`.hcol` = `0x612000 + 0x1C000`) | **3 header slots free** (e_lfanew `0x100`, optsz `0xE0`, section table `0x1F8..0x388`, nsec 10, SizeOfHeaders `0x400`, first raw `0x400` — 120 zero bytes spare). Cave home = the **`.hcol` tail**: 40,580 zero bytes from `0x62417C`, RWX | 3 more sections max. ⚠ `.tres`'s 302-byte tail is past VirtualSize **and** inside `build_tierresearch_exe.py`'s verified blob — do NOT use it. `AoWCompat.exe` headers byte-identical; `AoWDevEd.exe` has 1 slot, `AoWEd.exe` 7 |
| `AoWTCPCK.dpl` | `~0x0043810C` (`build_spellcast_tcpck.py`, `CAVE_BASE 0x00438100`) | from there | ~`0x00467000` (191 KB zero run at `0x438080`) |
| `aowInt.dpl` | `0x59823200` (`build_bltprobe.py`) | above | CODE content ends `~0x598227C6` |

⚠ Two hazards on record: `Drillmaster_Ability.md:55-56` — "`0x55814000` and `0x55815000` were both
already occupied, so **do not assume a round address is free** — scan." And `build_hpbar_clamp.py:78`
and `build_chasm_sky_transitions.py:64` **both declare `0x55812000`** — byte-check before trusting
either. For BSS: `grep -rn '0x558FA8' build_scripts/` misses computed claims (`SCRATCH+1`) — read the
assignments, not just the literals.

DLL caves must be PIC (`call $+5; pop; sub`). AoWTCPCK rebases too. AoW.exe (fixed base `0x400000`)
may use absolutes.

---

## 13. Order of work — REVISED 2026-08-16 after an adversarial readiness review

**Readiness verdict: four of five domains are ~half a day from ready. Do NOT start the mask widening
today. DO start Bug 1 today.**

### Blocking before any mask code (~half a day total, all tooling exists)

| # | gap | how to close |
|---|---|---|
| B1 | **The mask inventory is incomplete and reads as complete** — a census of 2 of 12 idioms found 30 enclosing functions where §3c names 16; ~15 are in no doc | mechanical census of all 12 idioms across **both** binaries, emitted as a symbol-keyed file the build script asserts against (~3h) |
| B2 | **`build_patch.py`'s live cave is a byte-mask consumer** coupled to two host stack frames (§3c) | fold the cave + both hosts into the inventory as first-class sites (~1h) |
| B3 | **The exe reads DLL struct masks by raw displacement through VMT calls** — no import scan finds them (§3c) | `fieldrefs.py` on the DLL + a disp-scan on AoW.exe; settle new layouts before either binary is edited (~2h) |
| B4 | **`TGeneral`'s slot array must be relocated before any 12-slot UI** — tags 8–11 read live pointers, never −1 | write the relocation spec: instsize `0xCC`→**`0xFC`**, 21 sites incl. the `add eax,0x68` address-take (~2h) |
| B5 | **Unknown: what the property stream does when a stored record is shorter than the reader's length** | decompile `rwBuffer` behind stream VMT `+0x1C`/`+0x34` from `TArmyView.ReadWrite @0x5578BAC4` (30 min) |

### Staging

1. **`build_generalslots.py`** — AoW.exe + AoWCompat.exe. Hook the 15 reloc-free bytes at
   `0x0044EC89` (**`E9` jmp entry**, + 10 NOPs) into a ~25-byte cave in the **`.hcol` tail** —
   start at **`0x624180`+**, not `0x62417C` (herodlg's code ends *exactly* there; leave margin), RWX,
   ~40,580 zero bytes; bound the slot store at `SLOTS = 8` and let the counter saturate. Surgical
   `--undo`; **re-verify the cave after any `build_herodlg_columns.py` re-apply**.
   *In-game: "nothing changed" regression pass only.* ✅ Confirmed writable today by independent
   re-verification (2026-08-16).
2. **Close B1–B5**, then `build_maskcount.py` — replace all **five** count→mask table consumers with
   one clamped computed helper. *In-game: nothing changed at cap 8.*
3. **Mask widening in flight** (byte → **dword**, not word), DLL + AoW.exe + AoWCompat in lockstep,
   **cap still 8**. Struct growth split out per B5. *In-game: nothing changed; a new game is required
   if struct growth is included.*
4. **`TGeneral` array relocation** to 12 slots, then re-run step 1 with `SLOTS = 12`. In parallel:
   `build_tacdeploy12.py` step 1 (`GetUnitPosition @0x00428964`, 76 reloc-free bytes, no cave).
   *The tactical half is independently testable here — a 3-stack Ruin battle.*
5. **UI** — one new PE section (~165 KB: **seven** DFMs, not three), relocate the DFMs, clone slots,
   grow field tables, rewrite the unrolled loops in `Update`/`CheckStart`/`CheckEnd`.
   *First visible change in-game.*
6. **Raise the cap** — the six imm8s, `Unitres.pfs` capacities (**last**, see §2), banner art ids
   24–26, editor grid DFMs, the raze trim, `DefPos`. *First real 12-stack test.*

⚠ **Do NOT make the transport `.pfs` edit the first patch.** It is not a no-op — see §2. It raises
the effective cap to 12 immediately, ahead of every safeguard.

⚠ **Bug 2 (Seduce double-stack) is a separate track and is NOT writable yet.** First A/B
`build_patch.py` out (it patches three functions on the move/attack path and has **no `--undo`**),
then instrument `TMoveArmyTE.FinishMove @0x55747FBC`. See `Command_DoubleStack_Bug.md`.

`AoW.exe` and `AoWCompat.exe` must be patched in lockstep (they differ by exactly one byte at file
offset `0x3BB7C`).

## 14. Open questions

*(Resolved items moved into the body — see the ✅ markers in §1, §2, §3a, §5, §6b, §8a, §10.)*

- ✅ **`TGeneral+0xA8/+0xAC/+0xB0` — RESOLVED**, see §1. `SelectedStructure` (crash) / dead field /
  `SelectedCity` (crash). Bounding the loop is necessary and sufficient.
- **Is the vanilla ≥10-unit crash reproducible?** §1 + §2 together predict that an army built past 9
  by the unbounded merge at `0x55749A48`, once selected, corrupts `TGeneral.SelectedStructure` and
  faults in the structure-info panel. Never tested. If it reproduces, it may be a known long-standing
  AoW1 crash with a now-known cause.
- ✅ **Race banner libraries — RESOLVED**, see §6b. 14 libraries, 42 sprites, and Family B needs a
  code cave because ids 40/41 are the city border art. `Flags.ilb` ids 80–91 also identified (the
  per-race `flagID + 0x50` overlay, not count-indexed).
- What `Flags.ilb` ids **38, 39, 86, 90** contain — `ilb_rle16.py` cannot decode them. Only matters
  if those frames are ever edited; ids 40–48 decode fine.
- **`TArmyView+0x3C`** (4 bytes, stream id `0x29`) — purpose undetermined.
- **`TArmyHS+0x14`/`+0x15`** semantics — established only that they are *not* a per-unit stack index.
- Whether `Flags.ilb` id 48 is a blank shield or a "9" glyph (pixel decode read as blank, not
  independently verified), and what the 12 `PartyShield` sprites at ids 80..91 are.
- Whether `AddChild` overfilling produces a visible 9th unit today — never tested in-game.
- `Int\ScanTile.ilb`, `Int\Celtdeco.ilb`, `Images\Cursors.ilb`, `Int\Icons.ILB` past index 6 —
  `ilb.py` desyncs on composite entries, so those directories are unread. None is a likely stack
  surface, but they were not ruled out.
- `TArmyEventLog` (`Create 0x5578BB6C`, `GetText 0x5578BD04`, `PartyDestroyed 0x5578BD84`) and
  `TArmyInfoEventLog.GetText 0x5578C048` — text builders, not decompiled.
- No exhaustive `cmp …,8` sweep was done across the whole of `AoWEPACK.dpl`; the search was scoped
  to add/join/merge/render/AI paths.

---

## 15. Side finding (unrelated, worth recording)

`PFS_Format_CRC.md` records the property-table small/wide entry rule as "small iff `tag<256 and
offset<256`". The engine writer's actual test is **`key > 0x7F → wide`**
(`TPropertyTable.SaveToStream @0x5550FD0C`). Latent only — the installed `Unitres.pfs` has no
top-level tag above `0x20` and no ability-owner sub-tag above `0x7F`. It would bite the Ziggurat
Manual's JS re-serialiser the day someone mints an ability with id ≥ `0x4E`, since owner records are
tagged `0x32 + id`.
