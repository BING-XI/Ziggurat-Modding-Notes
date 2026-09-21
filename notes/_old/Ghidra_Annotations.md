# Ghidra annotations — the record

Ghidra holds the **pristine vanilla** `AoWEPACK.dpl` (see `Ghidra_Toolchain.md`). Annotations added to
it — comments, names, structs, enums — live inside a 46 MB project file that is not shared, not in the
backup rotation, and lost on any re-import.

**So this doc is the source and the Ghidra project is the output.** Everything below can be rebuilt into
a fresh project with one command. Never annotate Ghidra by hand and leave it only there.

| layer | status | source of truth | applied by |
|---|---|---|---|
| 1. patched-site markers | ✅ applied 2026-08-03 | *derived* — live-vs-pristine byte diff | `re_tools/ghidra_annots.py --apply` |
| 2. struct catalogue + structs | ✅ applied 2026-08-03 | `re_tools/ghidra_fields.py` | `ghidra_fields.py --apply` |
| 3. enums | ✅ applied 2026-08-03 | `re_tools/ghidra_types.py` | `ghidra_types.py --apply` |
| 4. doc cross-links | ✅ applied 2026-08-03 | — | 17 concentrated docs now point at the catalogue |

Rebuild everything into a fresh project with three commands:

```bash
python "Modding Resources/re_tools/ghidra_annots.py" --apply && python "Modding Resources/re_tools/ghidra_types.py" --apply && python "Modding Resources/re_tools/ghidra_fields.py" --apply
```

---

## 1. Patched-site markers — where the live DLL differs from what Ghidra shows

**The problem this solves.** Reading a vanilla decompile and concluding "X is unpatched" is this
project's most expensive recurring mistake — it produced a confidently wrong
`TCity.GenerateRebelUnits` verdict that survived a week, and a wrong road-cost claim that propagated
into three files. The image gives no hint that it is 443 patches behind the installed game.

**The fix.** Every site where the live DLL differs from pristine now carries a comment in Ghidra, in
both the decompiler and the listing:

```
[LIVE-PATCH] live DLL differs here (1B): 0a -> 05 | named in: road_build_cost_by_decoration_patch.py
| VANILLA SHOWN - verify with re_tools/dasm.py AoWEPACK.dpl 557710F3 0x1
```

Nothing is hand-maintained. `ghidra_annots.py` derives the site list from the bytes and the
attribution by grepping the project, so it is correct the day a new feature is applied — just re-run it.

```bash
python "Modding Resources/re_tools/ghidra_annots.py"          # dry run: inventory only
```

`--apply` writes, `--undo` clears only its own comments, `--json FILE` dumps the inventory. Ghidra must
be running with the vanilla program open; the script refuses to write into any other program. **Save the
program in Ghidra afterwards** — the plugin does not auto-save.

### What it found (2026-08-03)

| | count |
|---|---|
| patched sites with a vanilla counterpart | **443** |
| ├ named by a `build_scripts/` script | 183 |
| ├ named only by a doc | 31 |
| └ **named by neither** | **229** |
| cave runs skipped (no vanilla code there) | 75 |
| distinct build scripts implicated | 81 |

**The 229 unnamed sites are Ziggurat, and that is expected.** The Ziggurat mod was built **by hand,
2020–2025** — hex-edited over five years, long before this project's build-script + doc convention
existed (author, 2026-08-03). So there is no script and no doc behind those bytes and there never was
one to lose. They are deliberate balance edits, not corruption and not another modder's work.

Two consequences:

- **Don't reverse-engineer their intent — ask.** The author is available; one question replaces an
  hour of analysis. This supersedes the "undocumented older city mods, archaeology pending" note in
  the raze analysis: it is not archaeology, it is undocumented authorship.
- **This is nonetheless the first complete inventory of Ziggurat's binary footprint.** Five years of
  hand edits, never listed anywhere. `--json` dumps it.

### Two implementation traps worth keeping

- **A diff run starts at the first byte that DIFFERS, which is usually mid-instruction.** The road cost
  is `sub eax,0xa` at `0x557710F3` but the differing byte is the immediate at `0x557710F5`. Ghidra only
  renders a comment at a code-unit boundary, so unsnapped addresses produce comments that silently never
  appear — **268 of 443 sites needed snapping**, i.e. 60% would have been invisible. The script decodes
  forward from several lead-ins and takes the most common containing instruction, since x86 cannot be
  decoded backwards.
- **Grep proves a file *mentions* an address, not that it *wrote* it.** Hence "named in:", not "patched
  by". `road_build_cost_by_decoration_patch.py` is another modder's reference script that cites the road
  site this project never patched there — the flat-5 baseline came from Ziggurat.

---

## 2. Struct catalogue — `Ghidra_Field_Catalogue.md`

**Built. `re_tools/ghidra_fields.py` is the source; `Ghidra_Field_Catalogue.md` is generated.**
17 classes, 139 instance fields, each tagged **M** (measured by decompile this session, 30),
**D** (doc-stated, 108) or **S** (speculative, 1). VMT slots are deliberately absent — those are
fully derived in `Ghidra_VMT_Layouts.md` and are not hand-curated at all.

```bash
python "Modding Resources/re_tools/ghidra_fields.py" --md
```

**Keyed by class, never by offset** — five separate aliasing traps were found in one session, so a
table sorted by offset would invite the exact mistake it exists to prevent. The catalogue opens with
the alias list.

### The bounds check makes it self-policing

Field *meanings* cannot be derived from the binary, but **instance sizes can** (RTTI `[VMT-0x1C]`),
and a field at or past its class's instance size is provably wrong or belongs to a subclass. Every
entry is checked on every run. Current state: 3 flagged, all correctly identified as **mod-grown**
(`TUnit+0x7C` casting cluster past vanilla `0x48`; `TArena+0x30/+0x34` past vanilla `0x30`) — which
is exactly the vanilla-vs-installed distinction the catalogue records rather than an error.

The same check condemns three claims in the wider inventory that were **not** admitted to the
catalogue, since a measured instance size beats a doc:

| claim | instance size | verdict |
|---|---|---|
| `TAbility+0x24` cosmetic category byte | `TAbility` = **0x24** | past the end — belongs to a subclass |
| `TCombatPredictor+0x34` loop object | `TCombatPredictor` = **0x34** | past the end (was flagged S anyway) |
| `TAbility+0x28` max level / `+0x2C` cost list | `TAbility` = **0x24** | these are `TMultiLevelAbility` (0x30), not `TAbility` |

Coverage is the core ~139 facts of the inventory's ~400. The rest are UI/editor and one-off records;
they can be added incrementally, and the bounds check will vet each addition automatically.

### Applied to Ghidra (2026-08-03)

`ghidra_fields.py --apply` creates the structs and types the member functions. **17 structs, 708
functions typed**, saved. Decompiles now read `param_1->bDef_modifier_cache` instead of
`*(char *)(param_1 + 0x45)`, and Ghidra tracks inheritance (calls to a base method show
`(TAbstractUnit *)param_1`).

⚠ **Delphi does not use `__thiscall`, so `set_function_this_type` does NOT work here.** The
`register` convention passes `Self` in **EAX**, so Ghidra sees no implicit `this` and that endpoint
refuses with *"calling convention 'unknown'"*. `Self` is simply **parameter 0** — type it with
`set_parameter_type` on `param_1`. This is the single most useful thing in this section: the obvious
API is the wrong one.

⚠ **Symbols are `<DelphiUnit>.<Class>.<Method>@hash` and the unit is not always `AoWE`** — the
hexagon classes live in `AoWHex`. Matching on an `AoWE.` prefix silently typed 0 functions for them.
Match the *class component* instead. Also note `search_functions` is a **substring** match, so
`TUnit.` returns `TAbstractUnit.*` too; filter on the exact component.

**Still outstanding:** the pointer chain. `TUnit.resource` is still `undefined4`, so decompiles show
`param_1->dwResource + 0x2a` rather than `param_1->resource->base_defense`. The struct was created
before the pointer types were added and `create_struct` refuses to overwrite an existing type; the
`recreate_struct` fallback did not take. Fix by deleting the affected structs and re-running, or by
`modify_struct_field_type` per field — not yet done.

### Working notes from the conflict pass

*In progress.* A sweep of `Modding Resources/` found ~400 recorded offset facts and **16 direct
conflicts** — same class, same offset, two meanings. Those are being resolved **by measurement, not by
majority vote**, before anything is written into the catalogue: a vote is exactly how a wrong claim
becomes permanent (this doc exists partly because a wrong road-cost claim propagated into three files).

### Method — the DLL names its own methods

`AoWEPACK.dpl` is Delphi and ships full RTTI, so a VMT slot can be identified beyond argument:

1. Find the class VMT from the class-name ShortString — `[VMT-0x20]` points at it, so the dword that
   points to the string is `VMT-0x20`. `[VMT-0x1C]` is the instance size, which cross-checks the hit.
2. Read the slot, decompile the target. Ghidra prints the real symbol,
   e.g. `AoWE.TUnit.GetDefense@23EDC2EF`.

No inference, no voting. (The probe that does step 1 is a dozen lines; see the session scratch or
re-derive — `re_tools/vmt_find.py` does the equivalent for `AoW.exe` only.)

### Resolved so far (measured 2026-08-03)

| conflict | verdict |
|---|---|
| `TAbstractUnit`/`TUnit` VMT **`+0xC4`** | **`GetDefense`**. `+0xC0` GetAttack, `+0xC8` GetDamage, `+0xCC` GetResistance. `dump_exe.py` and the majority were right; **`Fire_Heals_FireUnits_Design.md` mislabels `+0xC4` as GetResistance** — fix at that source. |
| `TAbstractUnit` VMT **`+0x13C`** | **`NewTurn`**, definitively (`AoWE.TAbstractUnit.NewTurn`). The claim that msg `0x20020002`/MovedTo dispatches through this slot is wrong. ✅ **This clears `build_spellcast.py`**, which repoints `+0x13C` — it is not intercepting movement messages. |
| `TUnitResource` base stats | **Both claims are right, for different classes — this is a trap, not an error.** See below. |

### ⚠ TUnit and THero read their stats from DIFFERENT resource layouts

Both classes hold a resource pointer at **`+0x40`**, but the stat blocks are **5 bytes apart**:

| stat | via `TUnit.Get*` | via `THero.Get*` |
|---|---|---|
| Attack | `[[unit+0x40]+0x29]` | — |
| Defense | `[[unit+0x40]+0x2A]` | `[[hero+0x40]+0x25]` |
| Resistance | `[[unit+0x40]+0x2E]` | — |

So `re_tools/pfs.py`'s map (`+0x29` ATK, `+0x2A` DEF, `+0x2B` DMG, `+0x2C` HP, `+0x2D` Move, `+0x2E`
RES) is the **TUnit** layout and is correct; the `+0x24`/`+0x25`… map in `Investigation_Items.md` and
`Investigation_Abilities_Leadership.md` is the **THero** layout and is also correct. Neither doc says
which class it means. **A cave written against one and run on the other reads the wrong byte** — the
same family of bug as the `+0x4C` alias. Any catalogue entry must name the class.

Confirmed in passing: `TUnit+0x44/+0x45/+0x46` are the ATK/DEF/RES caches; `THero+0x6B` is the DEF
bonus term; `THero+0x70` is `THeroItems`; VMT `+0x158` is the item-aware ability count and `+0x6C` is
`GetAbDefense`.

| conflict | verdict |
|---|---|
| combat-object VMT **`+0x90`** | **`GetAlignment`**, not `GetUnitSize`. `AoWE.TCombatObject.GetAlignment` returns a constant 6; `TCombatUnit.GetAlignment` forwards to `[cu+0x4C]->vmt[0xFC]`. **`Slayer_Abilities_Design.md` was right, `Investigation_Combat.md` was wrong.** Confirms in passing that `TCombatUnit+0x4C` is the strategic-unit pointer and `TAbstractUnit` VMT `+0xFC` is `GetAlignment`. |
| `TRangedAttackAbility` VMT **`+0x110`** | **`GetDamageRA`** (`+0x114` = attack). **`Slayer_Abilities_Design.md` was right; `Investigation_Combat.md` and `Investigation_Items.md` were wrong.** |
| `TAbstractUnit` VMT **`+0x108`** | **`GetTransporter`** — a bool, which calls `+0x104` for the capacity. `build_path_transportgate.py` labels `+0x108` "GetTransportCapacity", which is one slot off in meaning. |
| `TAoWHexagon` VMT end | **Confirmed.** `TAoWHexagon`'s VMT ends at `+0x120` — reading `+0x124` returns `6F41540B`, which is not an address but the bytes of a ShortString. `TAoWWaterHexagon` (instsize 0x20 vs 0x14) has a real `+0x124` = `ShowDynamic`. `Chasm_Sky_Terrain_Design.md` was right. |

⚠ **`Investigation_Combat.md` is the common factor in two wrong VMT claims** (`+0x90` and `+0x110`).
Treat its other unverified slot claims as suspect until measured — it is the one doc here whose VMT
table has now failed twice.

Also observed while measuring: `TRangedAttackAbility.GetDamageRA` queries Marksmanship (`0x20`) through
the **self-only** `+0x88`/`+0x84` accessors — the exact defect [[aow1-two-ability-query-apis]] records,
and what `build_useitems.py` repoints. The live-patch comments show that patch in place.

### ⚠ `+0x30` is past the end of TStructure — every subclass means something different by it

`TStructure`'s instance size is **0x30**, so its own fields stop at `+0x2F`. Measured sizes:

| class | instsize | what it puts at `+0x30` |
|---|---|---|
| `TStructure` | **0x30** | nothing — this is one past the end |
| `TArena` | **0x30** | nothing in vanilla; the mod **grows it to 0x38** and claims `+0x30`/`+0x34` |
| `TExplorationSite` | 0x38 | defender-strength byte (`+0x34` = the hidden defenders army) |
| `TDungeon` | 0x40 | inherits the site layout, adds prisoners at `+0x38`/`+0x3C` |
| `TReflectingPool`, `TTower` | 0x40 | their own fields |

So C9 was never a contradiction: **three sibling classes each own that byte independently.** The
consequence is the important part — a cave that reads `structure[+0x30]` behaves differently depending
on which subclass it is handed: an arena's mod flags, a site's defender strength, or a city's owner.
This is the `+0x4C` alias hazard again, and it is currently latent in the record because the docs all
say "TStructure". **Any catalogue entry for `+0x30` must name the concrete subclass**, and any cave
touching it needs the same class gate the `+0x4C` sites needed.

(`TSpell` instsize 0x34 also settles C10: `+0x18` is a real field, and the "set to 1 by `Create`"
note is just the constructor's default for the research cost. One fact, not two.)

### `map+0x174` is the DAY COUNTER — and one decompile confirmed nine other map fields

`AoWE.TPlayerControl.NewDay` contains `AoWHSMap[0x5D]++`, and `0x5D * 4 = 0x174`. The value is then
formatted into the "Day %d" event-log line and compared against the turn limit. **"Init state" was a
mis-generalisation from testing `> 0`**; `Arena_Rework_Feasibility.md`'s "≠0 ⇒ in-game not editor" is a
true consequence of it, not a separate meaning.

That same function independently confirms a row of previously single-sourced `TAoWHSMap` fields:

| offset | field | note |
|---|---|---|
| `+0x140` | `TPlayerList` | ✅ confirmed |
| `+0x144` | `TRaceList` | previously just "(second list)" — now named |
| `+0x158` | turn limit | compared against the day counter; triggers `GameOver` |
| `+0x16C` | turn-order mode | `== 2` ⇒ `GenerateNewTurnOrder` |
| `+0x174` | **day counter** | the field in question |
| `+0x19C` | notify event list | |
| `+0x22C` / `+0x230` | seed constant / seed state | ✅ both confirmed, day-1 write visible |
| `+0x13A` | scenario flag | ✅ confirmed — gates the day-1 `Randomize` |
| `+0xA5` | seated player | ✅ confirmed — passed to `GameOver` |

Message `0x20020001` is confirmed as **NewDay** (`InitMsg(msg, 0x20020001)` right there), settling the
"NewDay vs map-init" reading in the enum inventory.

### C3 — transport capacity: vanilla vs post-medal, both right

`AoWE.TUnit.GetTransportCapacity` takes the **max** of the item-aware ability level for id `0x32`
(Transport) and `TUnitResource.GetTransportCapacity`. So vanilla reads it from the resource (the
`+0x44` claim), and the copper-medal mod's relocation to `+0x32` is the *installed* layout. Not a
contradiction — the catalogue needs a **vanilla / installed** column for this field, as
`Copper_Medal_Design.md` already says. Also confirms Transport = ability id `0x32`.

### C7 — the water mask IS a land-neighbour mask (and the first verdict here was wrong)

**RETRACTED AND CORRECTED 2026-08-03.** This section first concluded "open-water mask" and
"corrected" `Chasm_Sky_Terrain_Design.md` accordingly. That was wrong; the Chasm/Sky doc was right,
and both it and this section have been put back.

`UpdateTransitions` sets bit d only when the neighbour owns **no `TLowerIsometricHexagon` and no
`TBorderHexagon`**. The error was assuming `TLowerIsometricHexagon` is the *land* family. It is the
**water** family: `TAoWWaterHexagon`'s own parent classref is `0x558FCD70` — the very classref passed
to `FindOwnedHS`. No water hexagon in the neighbour ⇒ the neighbour is land ⇒ bit set. So
**`+0x14` bit d = "neighbour in direction d+1 IS land"**.

⚠ **The lesson is bigger than the field.** The refuting evidence was sitting in my own probe output
(`TAoWWaterHexagon parentref=558FCD70`) at the moment the wrong call was made — a decompile was read
correctly and the *class identity* of a constant in it was assumed rather than checked. When a
`FindOwnedHS`/class-compare decides a polarity, resolve the classref before trusting the sense of the
test. Caught by an independent agent re-deriving the same field.

Confirmed alongside: `+0x15` low 6 bits = "neighbour terrain differs from mine" (the `& 0xC0` preserves
the top two bits), and `+0x19+dir` takes 0x28 for a Snow neighbour, 0x50 for Wasteland, else 0 — the
per-direction shore tint.

### C8 — `+0x10` really is both, on sibling classes

`TAoWWaterHexagon.UpdateTransitions` ends with `if (self[+0x10] == nil) self[+0x10] = <create dynamic
companion>`, so on **that** class `+0x10` is a pointer. On `TAoWHexagon` it cannot be: instance size
0x14 means `+0x10..+0x13` are its last four bytes, the three per-edge transition image bytes plus
flags. The two classes have **different parent classrefs** — they are siblings under a common ancestor
of ≤0x10 bytes, not parent and child — which is exactly what lets one byte range mean two things.

Verified `TAoWWaterHexagon` layout (totals 0x20, matching its instance size):
`+0x10` dynamic companion ptr · `+0x14` open-water mask · `+0x15` differing-terrain mask ·
`+0x18` signed frame counter · `+0x19` rolled animation id · `+0x1A..+0x1F` per-direction shore bytes.

That is the **fourth** aliasing trap in this set. The pattern is now unambiguous: in this codebase an
offset means nothing without its class, and the docs almost never say which one they mean.

### The two that did not resolve — stated honestly

- **C12 (field VMT `+0x84`) — NOT MEASURABLE with this toolchain.** `TMapField` is **not in
  `AoWEPACK.dpl`**; it lives in HSEngine, which Ghidra does not have (AoWEPACK only *imports* it —
  `HSEngine.TMapField.FindOwnedHS` etc.). Only `TAoWMapField` is local. Resolving this needs capstone
  against the owning module. Until then the three claims (move-entry handler / `FindChildIndex` /
  `UnitResourceIndex`) stay flagged, and note they are probably three different classes anyway.
- **C16 (`map+0x120`) — reconciled but NOT measured.** `TAbstractUnit.GetMoveTypes` turns out to be a
  bare forward to `GetAbMoveTypesAll` with no map check at all, so the tunneling strip happens
  somewhere further down the path code, which was not located. The likely reading — one field meaning
  "a combat is in progress", with "no tunneling during combat" as its consequence — is consistent with
  both docs but is **inference, not measurement**. Labelled as such.

C13/C14/C15 are documentation staleness, not measurable disputes — fix at the source.

### Score

16 conflicts: **14 measured**, 1 reconciled by inference, 1 unmeasurable without another module.
Of the 14 — **8 were plain documentation errors**, and **4 were latent class-aliasing traps** where
both sides were right about different classes (`TUnit`/`THero` stats, `TStructure+0x30`,
hexagon `+0x10`, and the `+0x4C` family already known). **No shipped cave was found to be wrong**; in
every case the defect was in the doc describing the code, not the code.

## 2b. VMT layouts are DERIVED, not transcribed — `Ghidra_VMT_Layouts.md`

The conflict pass showed the docs' **VMT tables** were the least reliable offset source in the
project (8 of 14 measured errors lived there). They are no longer a source at all.

`re_tools/ghidra_structs.py` derives them from the binary: the DPL is a Delphi package, so nearly
every method is **exported under its `unit.class.method` name**. Locate the VMT via RTTI, read each
slot, look the target up in the export table — the slot names itself. Regenerate any time:

```bash
python "Modding Resources/re_tools/ghidra_structs.py" --md
```

Output (2026-08-03): **36 classes, 2581 slots, 1642 self-named (63%)** → `Ghidra_VMT_Layouts.md`.
The unnamed 37% are methods inherited from base classes in *other* modules, which this DLL does not
export; they are marked, not guessed.

**Where a VMT ends is found exactly**, because the class-name ShortString immediately follows the last
slot (`TStructure`'s ends `…7453540A` = `\x0A"TStructure"`). Reading past it is not a bad method
pointer — it is a jump into a string.

Bulk verification of 103 doc claims: **89 pass, 3 fail, 5 not exported, 6 past the VMT end.**

| doc claim | derived | source |
|---|---|---|
| `TAbstractUnit+0x50` SetAbilityEnabled | **`TAbilityOwner.SetAbSet`** | Investigation_Abilities_Leadership.md |
| `TAbstractUnit+0x11C` CreateEnchantment | **`TAbstractUnit.CanAddToList`** | Investigation_Spellcasting_Extra.md |
| `TAbstractUnit+0x1AC` KillUnit | **`TAbstractUnit.Killed`** | Investigation_AI_Item_Pickup.md |

### ⚠ Trap 5 — the "TStructure VMT" table is a union of three incompatible classes

`Inioch_Structure_Raze_Framework.md` lists `+0x1F0 SetPlayer`, `+0x1FC ExecuteSearch`, `+0x200 Search`,
`+0x204/+0x208/+0x220 Update*` as `TStructure` slots. **`TStructure`'s VMT ends at `+0x1EC`**
(`CanRaze` is its last slot). Measured extents:

| class | VMT ends | `+0x1F0` | `+0x1FC` | `+0x200` |
|---|---|---|---|---|
| `TStructure`, `TArena` | `+0x1EC` | — | — | — |
| `TExplorationSite`, `TDungeon` | `+0x200` | `GetExplored` | `ExecuteSearch` | `Search` |
| `TTower`, `TReflectingPool` | `+0x220` | **`SetPlayer`** | `Update…` | `Visibility…` |

So `+0x1F0` is `GetExplored` on one branch and `SetPlayer` on another, and **does not exist at all**
on `TStructure` or `TArena`. This is worse than the field aliases: a cave calling
`structure->vmt[0x1F0]` either calls the wrong method or jumps into the RTTI string. Always take the
slot list from `Ghidra_VMT_Layouts.md` for the **concrete** class.

### Bonus: the live DLL's VMT hooks, derived for free

Comparing pristine against live slot-by-slot yields the **15 VMT slots the installed game repoints** —
an inventory that did not previously exist. Notably `TUnit`/`TAdjustableUnit` `+0x128/+0x12C/+0x130`
are repointed to `THero`'s casting-point getters (the unit-spellcasting feature), and `+0x13C`
(`NewTurn`) and `+0x018` (`ReadWrite`) go to caves. `TArena` repoints three slots; `TTower` repoints
`ExecuteRaze`. Full list in the generated file.

## 3. Enums

*Pending.* Ability IDs, spell IDs, terrain/overlay IDs, player-type enum (independent = 4), raze result
codes {3,4,6}, item types, medal ranks, message IDs.

---

## Consolidation rule

When a struct or enum moves into this doc, its **old copies are edited at the source in the same
sitting** — not left in place under a precedence banner. A reader who arrives by grep never sees the
banner; they see a plausible offset table and use it. That is exactly how the `+0x4C` type-alias bug
came to have two independent copies.

The status table at the top of this doc says which structs are consolidated. A precedence claim scoped
to that list is checkable; a blanket "this doc wins" is not.
