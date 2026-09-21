# Hero level-up dialog — 5 category columns (10 lists)

**Status: CONFIRMED WORKING 2026-07-31** — user-tested in-game across four rounds (columns →
two-box re-layout → knotwork bands → per-column sorting), each round validated in play before the
next. Scripts: `build_scripts/build_herodlg_columns.py` + `build_scripts/herodlg_cats.py`.
Binaries: **AoW.exe + AoWCompat.exe** (lockstep, still 1 byte apart). **Revert with `--undo`**
(surgical), never with a backup copy.

⚠ **`<exe>.pre-herodlgcolumns` is NOT a pristine exe** — the 2026-08-08 rebuild wrote it *after*
the feature was already installed, so it is a snapshot of the previous patched build. As of that
date the game root holds no unpatched exe at all; the only pristine source for the two ranges this
patch blanks is **`Ziggurat upload/AoW.exe`** (2025-03-21, vanilla field table). The script tries
candidates in order and **byte-checks each against the `ORIG_AT` fingerprints** before trusting
one, so a patched "backup" is rejected rather than silently used. Before that check existed, the
missing reference surfaced as `TypeError: object of type 'NoneType' has no len()` from inside
`Exe.wr` — a real failure wearing a nonsense message. Keep an unpatched exe somewhere.

Supersedes `HeroUpgradeDlg_Tall.md` as the owner of this dialog's geometry.

## 1. What it does

The single "Upgrades" list becomes **five category columns, each with its own Cost column** — ten
list columns — arranged as **two framed boxes** inside the one dialog. Dialog 407×432 → **960×860**.

```
+-- box A "StatePnl" -- the hero as he is ------------------------------------+
| [portrait + banner]        [ Current Abilities .......... | Cost ]          |
| [six stat rows]            [ (11 rows, wide name column)              ]     |
+-----------------------------------------------------------------------------+
+-- box B "UpgradePnl" -- what you can pick ----------------------------------+
| [Remove] [Add]                                       [Done] [Cancel]        |
| Wayfaring |C| Resistances |C| Melee |C| Ranged |C| Magic |C                  |
| ...27 rows...                                                               |
+-----------------------------------------------------------------------------+
```

Both boxes are the same width and stacked, so no horizontal space is wasted — this replaced a
first version (1190×864, one box) where the hero-state block sat centred in a sea of empty
texture. **Add / Remove / Done / Cancel are now box B's header row**, per the requested design.
Box A's Current Abilities list also gained a much wider name column (467 px vs 124), so long names
like "Water Concealment (Fixed)" no longer clip.

| Column | n | contents |
|---|---|---|
| Wayfaring | 27 | movement, terrain, the 8 Concealments, vision/invisibility |
| Resistances | 17 | 8 Immunities, 8 Protections, Fearless |
| Melee | 20 | the 7 Strikes, Charge/Parry/Round Attack/Extra Strike/…, the Slayings |
| Ranged | 20 | Archery/Marksmanship, thrown+shot, the 5 Breaths, the 5 Bolts |
| Magic | 16 | Spell Casting, mind control, Healing, Leadership/Bard's, Doom Gaze |

100 abilities; **27 rows are visible and the biggest column is exactly 27** ⇒ no scrolling anywhere,
with zero spare. `layout()` asserts this and refuses to build if the tallest category no longer
fits, so growing Wayfaring past 27 is a build-time error naming the flag to raise, not a silent
truncation — the scrollbar would also reappear on its own (`VanishWhenFull`). Unlisted ids
(mod-added abilities) fall into `DEFAULT_CAT` (Magic) so they can never become invisible.

Category assignment is a **design decision, not a decode** — the game has no category data at all
(`Ability.pfs` has no such tag; the word "Wayfaring" appears in no game file). Edit
`herodlg_cats.py` and re-run `--apply` to change it.

### ⚠ "My new ability doesn't appear" is almost never the category table

The default-to-Magic path was confirmed working 2026-08-07 (Drillmaster, id `0xAB`: the live
`AoW.exe` category-table byte at index 171 reads 4). If an ability is missing from the dialog,
the cause is upstream of this feature — the fill loop never reached it. In order of likelihood:

1. **Its selection mask lacks `0x100 astHeroUpgrade` or `0x200 astEditor`.** Two separate gates:
   the fill cave tests `astHeroUpgrade`, and `TAbility.CanExpand` tests the mask against
   `THero.GetAbilitySelectionTypes` = `astEditor`. And `Release/Ability.pfs` **tag 9 overwrites**
   whatever `CreateEnhancementAbility` was passed. Full decode: `Drillmaster_Ability.md`.
2. **No tag 6** (hero level-up cost) on its `Ability.pfs` record — set it in DevEd.
3. The hero already has it and it is not multi-level (`CanExpand` returns false via `GetAbSet`).

Check with `re_tools/pfs.py`, not by eye: record key = ability id + 10.

## 2. Structure

Column 0 reuses the existing `AvailableAbilities` / `…Cost` / `…SB` / `…Sort` / `…CostSort`.
Columns 1–4 are **byte-clones** of those five components with a new name, x, height and caption —
built by copying the donor's byte span out of the DFM and patching individual properties, so every
one of their ~40 properties stays exactly as the originals'.

⭐ **The clones keep the ORIGINAL event-handler names.** `OnChange=AvailableAbilitiesChange`,
`OnClick=AvailableAbilitiesSortClick`, `OnMouseDown=AvailableAbilitiesMouseDown`,
`OnChange=AvailableAbilitiesSBChange` — the same handlers, on all five columns. Those handlers are
then rewritten by caves to read **EDX = Sender** (Delphi's register calling convention puts Sender
there, and it is still live at every hook site because the prologues only touch EAX/EBX). Result:
**no method-table extension, no new published methods** — the single biggest simplification in the
whole feature.

### The knotwork bands (how the swirl is actually made)

The tessellating celtic swirl is **two stacked components**, not one:

- **`TCeltL` / `BCeltL`** — a `TAoWFrame` with `FrameType = frHorizLine`, `ILLine =
  IntGfxMod.CeltDeco`, `ILIndexLine = 55`: a horizontal rule that tiles image 55 across its width.
- **`TCelt`** — a `TAOWImage` of `CeltDeco` image **3** (a 27×27 medallion) stretched to 349 px,
  which the toolkit **tiles**, producing the continuous swirl.

Vanilla's *bottom* band had the rule but, instead of one wide tiled image, three discrete
medallions (`CeltL`/`CeltM`/`CeltR`) flanking the Done/Cancel buttons. That is why the bottom
looked bare once the buttons moved into box B. Fixed by cloning `TCelt` → **`BCelt`** (`ahBottom`,
full width) so the bottom mirrors the top exactly, and setting `Visible = False` on the three loose
medallions — leaving them would collide with the tiling phase and make the band look doubled.

A third copy (**`MCeltL` + `MCelt`**) sits *behind box B's header row*, so Remove/Add/Done/Cancel
rest on knotwork exactly the way vanilla's Done/Cancel rested on the bottom bar. It shares the
button row's vertical space, so it costs no extra dialog height.

⚠ **Higher `Priority` draws on top** (vanilla proves it: Done = 250 over CeltM = 100 over
BCeltL = 0). `TCelt`'s inherited 100 would have **tied** with `RemoveBtn`'s 100, so `MCelt` is
forced to Priority 1. Check the donor's priority whenever you clone a control into a new z-context.

### The two boxes

`UpgradePnl` is **reused** as box B; box A (`StatePnl`) is a clone of it. A box is made visible by
giving the panel `ILFrame = IntGfxMod.GenericF` + `ILIndexFrame = 88` — GenericF is a catalogue of
**8-image frame sets** (corner/edge/corner ×2 + sides), so `ILIndexFrame` selects a *set*, not one
image. Useful sets, with their border thickness: **32 `DialogFr` 22 px** (the dialog window's own
ornate frame), **40 `FrThin` 1 px** (what the listboxes use), 48 `FrameLight` 2–4 px,
56 `FrGoldSq` 3 px, 64 `ScenFr` 1 px (the stat rows), 72 `STGrFr` 2 px, **88 `NGFrOut` 3 px** —
literally the New-Game screens' *outer grouping* frame, which is why it was chosen — 96 `NGFrThin`
1 px, 105 `FrThinD` 2 px. `FRAME_IDX` in the script is one line to change.
⚠ A panel needs **both** `ILFrame` and `ILIndexFrame`: `StatisicsPnl` carries `ILIndexFrame=96`
but no `ILFrame` and therefore draws no frame at all.

**Reparenting is just the `AOWWindow` ident.** TopPnl / StatisicsPnl / the Selected* group were
moved to `StatePnl`, and Done / CancelBtn (previously children of `Dlg`) into `UpgradePnl`.
Children of a moved panel follow automatically, and forward references are fine — the DFM reader
resolves component references by name after the whole form is read (vanilla already does this:
`HeaderLbl`, component 14, references `InfoPnl`, component ~94).

Geometry is computed once in `layout()` and asserted there: columns are pitched evenly across the
box (182 px at 960 wide), each name list 126 px, cost list 46 px at +123, scrollbar 17 px
overlaying the cost list's right edge (the vanilla arrangement). Lists are `ahBoth` anchored to
their box, so their height follows the box rather than being hard-coded. Everything else is
`awLeft`/`ahTop` at an explicit offset with every percentage zeroed — no control stretches
unpredictably. `layout()` refuses sizes where the columns, the header buttons or the Current
Abilities column would not fit, naming which one and which flag to raise.

## 3. Class surgery

- **DFM grows 52 987 → 70 540 B** (121 components) and is relocated to a new RWX section
  **`.hcol` @ VA 0x612000** (0x1C000). The original bytes stay untouched in `.rsrc`, which is what
  makes `--undo` a pure repoint of the resource data entry.
- **Field table rebuilt** in `.hcol` (96 → **120** entries, same class palette) and `[VMT-0x2C]`
  repointed; **instance size `[VMT-0x1C]` 480 → 576**. New fields:
  `+0x1E0..0x1EC AvailAb2..5`, `+0x1F0..0x1FC AvailCost2..5`, `+0x200..0x20C AvailSB2..5`,
  `+0x210..0x21C AvailSort2..5`, `+0x220..0x22C AvailCSort2..5`, `+0x230 StatePnl`,
  `+0x234/+0x238/+0x23C BCelt/MCeltL/MCelt`. (The knotwork bands are referenced by nothing and
  would have worked unbound; fields cost 12 bytes and keep everything uniform.)
- No class-palette work: the form's 10 palette entries are exactly the 10 classes it already uses,
  which covers every class a new column or band needs.

**Two idempotency traps, both hit and fixed** — they matter to anyone re-running this script:

- `state_of()` deliberately does **not** pin the exact instance size — only that it differs from
  vanilla — so `--apply` can upgrade an older version of this same patch in place. Pinning it cost
  one failed apply the moment the layout gained a control.
- `--apply` does **not** short-circuit when the dialog is already at the requested size. **Size is
  not a fingerprint of the build**: a layout or taxonomy change rewrites the DFM at the same width
  and height, and the short-circuit silently skipped it (it looked like the edit had no effect).
  It always undoes and rebuilds; that is idempotent and cheap.

## 4. Caves (in `.hcol` @ 0x623D30, ~912 B; exact VAs shift when the block is rebuilt)

| Cave | Replaces | Does |
|---|---|---|
| `cave_fill` | `0x446972..0x446A53` (the whole available-fill loop) | clears all 10 lists, walks ability ids, filters on `CanExpand` + `[ability+0x21]&1`, looks the category up from `[ability+0xC]`, adds name (with the ability id as the item object) and cost to that column's pair |
| `cave_setfmax` | `0x446BB2..0x446BD1` | `SetFMax(count-1)` on all five scrollbars |
| `cave_sortone` | (new, called by the three below) | sorts **one** column by that column's own mode |
| `cave_sortall` | `sub_4468A0` | loops `cave_sortone` over all five — only used by the refill |
| `cave_sortclick_name` / `cave_sortclick_cost` | `AvailableAbilitiesSortClick` @0x447238 / `AvailableAbilityCostSortClick` @0x447270 | identify the clicked column from Sender, toggle **that** column's mode, re-sort **only** it |
| `cave_change` | `AvailableAbilities(Cost)Change` @0x447008/@0x44701C | identifies the column from Sender, mirrors the index onto its cost list, **clears the other four**, records the active column |
| `cave_sbchange` | `AvailableAbilitiesSBChange` @0x447030 | identifies the column from Sender, `SetListOff` on its name+cost lists |
| `cave_activelist` | the `mov esi,[ebx+0x80]` at `0x4470E3` | returns the **active** column's name list, so Add adds the right thing |

Plus two 6-byte in-place edits in `AvailableAbilitiesMouseDown` (`0x4473EC`, `0x4473FB`):
`mov reg,[ebx+0x80]` → `mov reg,edx`, i.e. use Sender directly for the right-click info popup.

The cave data area holds the 256-byte category table (indexed straight by ability id), the column
instance-offset tables, the sort-function table, `activecol`, and a **`calltmp` slot** used to stage
virtual-call targets — necessary because EAX/EDX/ECX are all argument registers for `GetName` and
`AddObject`, so the vtable pointer has nowhere else to live. That slot is why the section is RWX.

**No recursion risk** from `cave_change` calling `SetIndex` on the other columns: `SetIndex` does
not raise `OnChange` (proven by vanilla's own `sub_446C58`, which would otherwise loop forever).

### ⚠ Column sorting — two bugs the first version shipped

Both were reported from play and are fixed; both are the kind that only surface in use.

1. **The sort mode is 0..3, not 1..4.** Read it off the vanilla click handlers, not the dispatch:
   `AvailableAbilitiesSortClick` @0x447238 toggles `+0x1D4` **0↔1** (name asc/desc) and
   `AvailableAbilityCostSortClick` @0x447270 toggles it **2↔3** (cost asc/desc). `sub_4468A0`'s
   `sub edx,1; jb` reads like a 1-based ladder but the `jb` arm *is* mode 0. The first cave did
   `dec edi` to compensate for a ladder that was never 1-based, so every mode landed one step out
   of phase — clicking **Cost** sorted by **name descending**.
2. **A shared mode sorts every column.** Vanilla has one list, so one mode field is fine; with five
   independent columns the mode has to be **per column** (`colmode[5]` in the cave data), and the
   click handlers must resolve *which* column from **Sender in EDX** — matched against the
   `colsort` / `colcsort` tables of header-button instance offsets — instead of acting globally.

The click caves also reproduce vanilla's click-feedback call (`[0x45A420]` → `+0` → `call
0x455DFC` with edx=0); dropping it would silently lose the button sound.

Cross-cave calls (`cave_sortclick_* → cave_sortone`) made the assembler **two-pass**: pass one
sizes the block with placeholder targets, pass two emits with real VAs. It converges because a
`call rel32` is 5 bytes regardless of target.

## 4b. Surviving a game-window resize (`cave_geom`)

**Applied 2026-08-08, untested in play.** Symptom: shrink the game window and enlarge it again and
the dialog comes back mangled — outer frame gone, box A sitting *inside* box B — and no amount of
resizing brings it back.

**Cause, measured live** (`re_tools/dlg_geom.py --tree`, taken with the broken dialog on screen):

| control | design | after the resize |
|---|---|---|
| `Dlg` | 960×860 | **640×432** |
| `StatePnl` | 908×224 @26,53 | **640**×224 @**0**,53 |
| `UpgradePnl` | 908×530 @26,285 | **640×432 @0,0** |

Every difference fits one rule: **an axis that overflows the parent is reset to offset 0 and the
parent's full extent.** `StatePnl`'s bottom (277) still fitted inside 432, so its Top and Height
survived — which is exactly what drops box A into the middle of box B on screen. 640×432 is the
window manager's client area at the 640×480 minimum resolution, less its 48 px toolbar strip
(`mgr+0x120`); it is not a vanilla value (vanilla `Dlg` is 407×864 after the tall patch, 407×432
before it). The clamp writes the rects **in place** and nothing restores them.

⚠ **This is not `ReAlign`.** `Dlg` is `awCenter/ahCenter` and the boxes are `awLeft/ahTop` with
every percentage zeroed, so `ReAlign` (aowInt `0x598030FC`) only ever rewrites Left/Top and would
have put `Left` back to 26. It reads 0. Some other pass writes the sizes. It was not worth hunting
further — the clamp is presumably what keeps the blitter inside its surface, and this project has
already paid for one out-of-bounds "Blt Error" hunt (`Blt_Error_Wall_Damage.md`).

**Fix: self-heal on open, rather than fighting the clamp.** `cave_geom` runs from the head of
`cave_fill`, i.e. on every `FillLists`, and rewrites the three panel rects from a
`{field offset, W, H, Left, Top}` table (`D["geom"]`, generated by `geom_table()` from `layout()`,
so `--width`/`--height` can never drift between the resource and the heal). Restoring those three
is enough — everything else is anchored and recomputes; the `ahBoth` lists were already doing
correct arithmetic against the wrong box (`381 = 432 − 47 − 4`). It then zeroes `+0x2d` (aligned)
and `+0x2e` (sized) on each panel and `+0x2d` on each of their children, the toolkit's
"re-lay-me-out" signal. Closing and reopening the dialog now repairs it; when the window really is
too small the clamp simply re-fires, which is correct.

Field offsets, read out of the live field table: `Dlg` **+0x44**, `UpgradePnl` **+0x74**,
`StatePnl` **+0x230**. Left/Top for `Dlg` are stored as −1 = "leave alone" — it is centred, so
`ReAlign` owns its origin and writing one would fight the centring.

⚠ **Generalises to every oversized AoW dialog.** Any window bigger than the manager's client area
at 640×480 will be flattened the same way, permanently. A patch that enlarges a dialog should
carry a heal like this one.

## 5. Relocations

Two base relocations (`0x446995`, `0x4469B8` — the absolute `mov eax,[0x45DF78]` operands) fall
inside the displaced fill loop. They are set to type 0 (ABSOLUTE/no-op) on apply and back to type 3
on undo, keyed by target VA. The image is not `/DYNAMICBASE` so they would never be applied anyway,
but no stale relocs are left pointing into rewritten bytes.
**Generalisable:** always scan `.reloc` for the ranges you displace in an *exe*, not just a DLL.

## 6. Re-tuning

`--apply --width W --height H` (default **960×860**) re-derives everything from the pristine DFM —
it internally undoes first, so it is safe to run repeatedly, and it never touches a backup. To
change the taxonomy, edit `herodlg_cats.py` and re-run `--apply`; to change the box frame, the
column widths or the band positions, edit the layout constants at the top of the build script.

## 7. What was verified, and how

**In-game (the user, across four rounds — all confirmed working):** the lists populate into the
right columns; Add / Remove / the right-click info popup work against any column; the header
captions survive `TIvTranslator` untouched; the two framed boxes and all three knotwork bands
render; per-column sorting behaves.

**Static + live process (per build, before each hand-off):**
- all 11 hook sites byte-match vanilla before patching (verify-before-write; hand-transcribed
  expectations were wrong at 5 of the first 9 sites and were replaced with bytes read off the
  binary — **do not transcribe hook bytes by hand**);
- the rebuilt DFM reparses with `consumed == len`, 121 components, every clone present;
- apply → undo → re-apply round-trips, and undo restores every hook site and both VMT dwords;
- AoW.exe and AoWCompat.exe still differ by exactly the one build-number byte at 0x3BB7C;
- **the game launches and reaches its main window**, which means the grown DFM parsed — all 78
  forms are constructed at startup, so a malformed DFM or a bad field binding would abort there;
- ⭐ **live-process read of the form instance shows all 24 new fields non-null** (instance found via
  the `CreateForm` stanza @0x459DB4 → DATA slot 0x45A0F0 → instance global 0x45B228). The DFM
  reader really did create and bind the cloned controls;
- ⭐ **the reparenting is confirmed live too**: a control's parent pointer sits at **control +0xCC**
  (calibrated by finding UpgradePnl's address inside AvailableAbilities). TopPnl, StatisicsPnl and
  the whole Selected* group report `StatePnl`; the five columns, the four header buttons and the
  middle knotwork band report `UpgradePnl`;
- the sort tables (`colsort`/`colcsort`/`colmode`/`sortfns`) read back correctly live, and all ten
  header buttons are distinct pointers so the Sender→column lookup cannot be ambiguous.

**The live-memory recipe is the reusable part here** — it turns "the game didn't crash" into real
evidence about the patch, without needing to reach the dialog in play. See `re_tools/` and the
snippet pattern above: instance global → field offsets → `ReadProcessMemory`.

⚠ **A background launch check can race.** One run reported "GAME NOT RUNNING" and looked like a
crash regression; running the exe in the foreground showed it was fine and the check had simply
polled at the wrong moment. Confirm a startup failure in the foreground before believing it.

**Resolution requirement:** 960×860 needs a game window at least that big — 230 px narrower than
the first version. `--width`/`--height` re-tune; `layout()` refuses a size that cannot hold the
columns, the header buttons or the tallest category (currently 27 rows).
