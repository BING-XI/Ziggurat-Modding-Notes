#!/usr/bin/env python3
r"""
ITEM PROPERTIES GETS "Hit Points" AND "Movement" SPINNERS   (AoWDevEd.exe -> AoWzEd.exe)

`build_item_hpmv.py` (applied) gave `TItem` two signed bonus bytes -- `item+0x4A` HP and
`item+0x4B` MV -- and taught `TItem.ReadWrite` to stream them as tags 0x17 / 0x18.  Nothing
in the editor could author them.  This adds two rows to the **Item Properties** dialog's
Statistics panel, alongside the four that already exist for ATK / DEF / DAM / RES, and
gives the two new rows the same left-hand stat icons the other four carry.

    target   Ziggurat\AoWDevEd.exe          (then build_zigeditor.py --apply -> AoWzEd.exe)
    cave     0x00599000 .. 0x005993FF       1024 B reserved, `.nmg` page slack above
                                            build_deved_newmapgen.py's body
    globals  0x00599000 G_FORM / 0x00599004 G_HPSPIN / 0x00599008 G_MVSPIN  (12 B, inside
             the cave span so `--undo` is one contiguous zero-fill; `.nmg` is RWX)
    dfm      TITEMEDITFORM relocated to 0x00599400 (rva 0x199400, immediately above the
             cave), grown by the two TImage nodes; `.nmg` grown to hold it
    roll     NONE.  This feature draws no random number and inherits none, so there is no
             pattern from the closed taxonomy to name.  It creates VCL controls, copies a
             byte into a spinner and a spinner's value back into a byte; the icon half
             injects NO CODE AT ALL -- it is a resource edit.  (`rng_audit.py
             AoWDevEd.exe --functions` prints SYNC: 0 / RAW: 3 -- all three
             build_party_random.py's -- before and after; `TAoWHSMap.Random` is not
             imported by this binary at all.)

WHY RUNTIME CONTROL CREATION AND NOT A DFM EDIT
  * The DFM cannot GROW.  `TITEMEDITFORM` is RCDATA at file 0x000697A8, 0x1D3F bytes, and
    `TITEMEXPLORATIONSITEEDITFORM` starts at 0x0006B4E8 -- one pad byte behind it.  (And
    re-encoding vaInt16 to buy room is a measured dead end: Delphi already writes the
    smallest encoding.)
  * A DFM-named `OnChange` needs a matching PUBLISHED method.  `TReader` rejects the whole
    form over one unresolvable ident, so two new handlers would mean relocating the
    published method table.  A runtime-assigned `TMethod` needs no published slot at all.
  * The LOAD path is four UNROLLED sequences (0x00413371..0x004133B2) -- there is no
    generic loop to name a fifth and sixth control into.

  So: three `call rel32` OPERAND RETARGETS (4 bytes each, nothing displaced, no instruction
  truncated) into one cave, plus a length-neutral DFM re-pitch that makes room for two more
  rows inside the panel that is already there.

THE THREE RETARGETS                            (all VAs, ImageBase 0x400000, fixed base)
  A 0x004137DC  E8 3B FA FF FF -> cave_enter   the `call UpdateControls` in
                `TItemEditForm.Execute @0x00413750` (view mode).  EAX = Self.
  B 0x0041389F  E8 78 F9 FF FF -> cave_enter   the `call UpdateControls` in
                `TItemEditForm.Edit @0x00413810` (edit mode).  EAX = Self.
  C 0x004133AE  E8 35 FD FE FF -> cave_load    the RES `call TSpin.SetValue`, the LAST of
                the four unrolled loads, inside `UpdateControls` itself.

  ⚠ The other two `UpdateControls` callers -- `ItemTypeBoxChange @0x00413A1D` and
    `AbilityBtnClick @0x00413B6E` -- are deliberately NOT retargeted.  They are refreshes
    of a form that already exists; routing them through cave_enter would build a second set
    of controls on every item-type change.  They still reach cave_load (it is inside
    UpdateControls), so the two spinners refresh with everything else.

  Each cave body runs the displaced original FIRST and then does its own work, so `--undo`
  is three dwords.  Audited: the base-relocation directory (10780 fixups) puts nothing in
  any of the three operand windows, nothing in the cave, and nothing anywhere in `.nmg`.
  ⚠ PIC is not required and must not be built -- `AoWDevEd.exe` has ImageBase 0x400000 and
  DllCharacteristics 0, so absolute operands are correct here.  The `call $+5 / pop / sub`
  anchor belongs to the rebasing `.dpl` packages.

THE CAVE                                        (entry points, in file order)
  cave_change  the shared `OnChange`.  EAX = TMethod.Data = the form, EDX = Sender.
               Guards `EAX == G_FORM`, dispatches `EDX` against G_HPSPIN / G_MVSPIN (and
               returns if it matches NEITHER -- never "else it must be MV"), nil-checks
               `[form+0x27C]`, calls `TSpin.GetValue`, saturates to [-128, 127] in 32 bits
               and stores the byte.  Preserves EBX/ESI.
  cave_load    runs the displaced `TSpin.SetValue(ResistanceEdit, item[0x49])` with EAX/EDX
               already loaded by vanilla, then -- with ESI = the item and EBX = the form
               still live, because `TSpin.SetValue` pushes/pops EBX and ESI and never
               touches EDI -- loads `item+0x4A` and `item+0x4B` into the two cached spins.
               Guards `EBX == G_FORM` before dereferencing either cached pointer.
  cave_enter   EAX = Self.  Invalidates the three globals FIRST, builds TLabel + TSpin
               twice against `[form+0x224]` StatisticsPnl, applies the read-only colour
               when `[form+0x280] != 0`, publishes G_FORM, wires both `OnChange`s LAST, and
               tail-jumps to `0x0041321C` with EAX = Self.  Every failure path leaves
               G_FORM = 0, which switches cave_load and cave_change off.

  ⭐ There is deliberately NO "already built?" test.  `TItemEditForm` is constructed and
  freed per use at all EIGHT of its construction sites (0x004203D9, 0x00413DC0,
  0x004164xx twice, 0x00417DF0, 0x00420A60, 0x0042B0A0, 0x0042B100), each of which is
  `Create -> (Edit XOR Execute) exactly once -> Free`, so cave_enter runs exactly once per
  instance.  A `G_FORM == form` skip would be strictly WORSE: Delphi's heap hands back the
  same form address, so it would pass on a NEW instance whose spins are the FREED ones of
  the old -- the dangling-pointer trap.  Building unconditionally has no such failure: the
  pathological double call would stack two harmless orphan controls that the panel frees
  with everything else.

VCL TOOLKIT -- everything is already imported, nothing new is added to `.idata`
  `SpinEdit..TSpin` class ref   IAT 0x0043357C   instsize 0x150
  `StdCtrls..TLabel` class ref  IAT 0x00432654   instsize 0x0C4
  virtual constructor           VMT +0x24  -- BOTH classes override it
                                (`TSpin.Create @0x00403034`, `TCustomLabel.Create`), so
                                construction is `mov eax,[iat] / mov dl,1 / xor ecx,ecx /
                                call [eax+0x24]`.  ECX is AOwner: the flag byte occupies
                                DL, which pushes the declared parameter one register along
                                (verbatim from `TMainForm.GameSettingsClick @0x0042D3DC`).
  SetParent                     VMT +0x3C.  Both classes hold `Controls.TControl.SetParent`
                                there, i.e. the exe thunk 0x00401540 would be equivalent;
                                dispatched virtually anyway so the call cannot go stale.
  SetBounds                     VMT +0x4C -- ⚠ TSpin holds `TWinControl.SetBounds` there,
                                an OVERRIDE, so this one MUST be virtual.
                                EDX = Left, ECX = Top, `push Width` then `push Height`,
                                callee `ret 8`.
  TSpin.SetValue / GetValue     exe thunks 0x004030E8 / 0x004030E0
  TControl.SetText / SetColor   exe thunks 0x00401568 / 0x004015A0

TSpin FIELDS -- read out of the class's own published RTTI, not guessed
  MinValue +0x130   MaxValue +0x134   Increment +0x138   EditorEnabled +0x140
  OnChange TMethod  Code +0x128, Data +0x12C
  ⚠ EditorEnabled is +0x140, NOT +0x120 -- +0x120 is `AutoSelect` (confirmed twice: the
    RTTI table, and `TSpin.IsValidChar @0x00403279` reading `[esi+0x140]`).
  ⚠ A freshly constructed TSpin is NOT zero-initialised in the way it looks:
    `TSpin.Create` sets MaxValue := 0x0FFFFFFF (0x004030E0), Increment := 1 and
    EditorEnabled := True.  MinValue alone stays 0.  Both ceilings are therefore set
    explicitly here, and EditorEnabled is cleared to match the four DFM spinners, which
    all carry `EditorEnabled False`.

  ⚠ `TSpin.SetValue` calls `CheckValue @0x004036EC` BEFORE setting the text, so a stored
    byte outside [MinValue, MaxValue] is clamped on display -- and `SetText` raises
    EN_CHANGE, which fires `OnChange`, which writes the clamped number back.  With
    MinValue 0 (the owner's call: "no negative/cursed authoring") a NEGATIVE `item+0x4A`
    or `+0x4B` can therefore be clamped to 0 by the UI.  That is not new behaviour
    introduced here: the four existing spinners have MinValue 0 over the equally signed
    `+0x46..+0x49`, so this matches them exactly.  Stated as a finding, built as specified.
    ⚠ It does NOT happen merely on opening the dialog, as this note used to claim.
    `cave_enter` and the first `cave_load` both run BEFORE `ShowModal`, so the spins have
    no window handle: `TControl.SetText` with FHandle = 0 routes WM_SETTEXT to
    `TControl.DefaultHandler`, which raises no EN_CHANGE, and `TCustomEdit.CNCommand
    @0x4134FA54` additionally gates on `[eax+0x124]` (FCreating).  The write-back needs a
    POST-show `UpdateControls` (item-type change, ability edit) or a spin-button click.
    And `TItemEditForm.Edit @0x00413810` Assigns the working copy back only on mrOk
    (`dec eax / sete [ebp-1] / cmp byte [ebp-1],0 / je 0x4138F8`), so Cancel discards it.

  ⚠ AOwner is nil, deliberately.  The four controls are not in `form.Components`, so
    `FindComponent` will not see them and the form's `TIvTranslator` (+0x278) will not
    touch their captions -- they stay English.  They ARE freed:
    `Controls.TWinControl.Destroy @0x4134316C` destroys every child control of
    StatisticsPnl regardless of ownership.

LAYOUT -- a length-neutral DFM re-pitch; the MASTER resource does not move
  StatisticsPnl is 397x161 at (20,156) inside GeneralSheet and its four rows sit on a 32 px
  pitch (spins Top 24/56/88/120, Height 26).  Re-pitched to 24 px with 22 px spins -- the
  same geometry `TUnitResourceEditForm`'s GroupBox2 already uses -- rows become 16/40/64/88
  and the cave puts HP at 112 and MV at 136, both inside the existing 161 px panel.
  Labels sit at spin+3, icons at spin + (22 - icon height)//2.
  Sixteen Int8 values change (Top on 4 spins / 4 labels / 4 images, Height on the 4 spins);
  every one is Int8 before AND after, so the re-pitch is byte-neutral and is written into
  the ORIGINAL `.rsrc` copy at file 0x000697A8.  The resource is LOCATED through the
  resource directory on every run, not trusted to a baked offset.

  Every value is asserted to be either the vanilla number or ours before anything is
  written, so a half-applied state repairs and a foreign value aborts.

THE TWO ICONS -- art COPIED out of THEROEDITFORM, never authored
  "Hero Properties" already carries the two bitmaps this needs, as `TImage` children of its
  own stat panel.  They are lifted verbatim:

      src TImage   row    file span (whole object)   Picture.Data payload   bitmap
      Image11      Hits   0x0005BC0F..0x0005BF93     834 B                  16x16x24, 822 B
      Image12      Moves  0x0005CDD1..0x0005D3F6     1506 B                 32x15x24, 1494 B

  Proof they are the right siblings: the four icons already on Item Properties
  (`Image6/7/10/8`) are BYTE-IDENTICAL to THEROEDITFORM's `Image9/7/10/8` -- same md5 over
  each 834 B payload -- so this is one icon set and Image11/Image12 are its HP and MV
  members.  Both source spans are identical in `AoWzEd.exe` at the same offsets.

  Format: DFM vaBinary (0x0A) + u32 len + shortstring 'TBitmap' + u32 gsize + a plain BM
  DIB.  Only the `Picture.Data` PROPERTY BYTES are copied; Left/Top/Width/Height are
  re-emitted so the smallest integer encoding is used for the new values.

  ⚠ `Image12` carries no `Stretch` and no `Center`, so its 32 px bitmap is CLIPPED to the
  17x16 control.  Copied verbatim on purpose: Item Properties then shows exactly what Hero
  Properties shows.  Do not "fix" it.
  ⚠ `Image11` is the 17 px HIGH control and `Image12` the 16 px one -- the opposite of what
  the bitmap sizes suggest.  Top is therefore DERIVED, `spin + (22 - height)//2`, which
  reproduces the existing four exactly (H17 -> spin+2, H16 -> spin+3) instead of baking two
  numbers that are easy to swap.

  NO FIELD-TABLE CHANGE IS NEEDED, and this is proved by existence inside this same exe:
  `Panel1` is a TITEMEDITFORM DFM component with NO published field on `TItemEditForm` (the
  field table has `OKBtn`/`CancelBtn` but not their parent), and the form loads today.
  `TComponent.SetReference` -> `TObject.FieldAddress` returns nil and does nothing.  So the
  field table stays at 40 entries and InstanceSize at 0x284; both are asserted every run.

RELOCATING THE RESOURCE, AND GROWING `.nmg`
  TITEMEDITFORM cannot grow in place: RCDATA at file 0x000697A8, 0x1D3F bytes, with
  `TITEMEXPLORATIONSITEEDITFORM` starting at 0x0006B4E8 -- one pad byte behind.  So the
  grown form is written ELSEWHERE and the resource directory's data entry is repointed.
  Prior art in this very binary: `TMAINFORM` already loads from `.ctp` (rva 0x12ECF4) and
  `TNEWMAPDLG` from `.nmg` (rva 0x196A60).  The Win32 resource loader returns
  `module base + OffsetToData`; nothing requires the data to sit inside `.rsrc`.

  The `.rsrc` original is LEFT IN PLACE, dead but intact.  It stays the master the grown
  copy is derived from, and it makes `--undo` a directory-entry rewrite rather than a
  7487-byte restore.  ⚠ Zeroing it would break idempotency; see the forward hazard about
  editing the live copy.

FOUR STATES, AND THE DAMAGED ONE
  pristine   3 calls vanilla, cave blank, DFM un-pitched, entry in `.rsrc`, `.nmg` ungrown
  fully ours everything installed and current -- the only state that prints "chain intact"
  DAMAGED    the entry ALREADY points into `.nmg`, so the editor reads whatever is there,
             but the section is not grown / VirtualSize does not declare it / the DFM or
             the cave is not ours / a call site does not point at the cave.  Item
             Properties is BROKEN.  `--apply` repairs it in place; `--undo` is reachable.
  foreign    a call operand, a DFM byte or the entry holds a third value -> ABORT.

  ⚠ `grown` asks only "does the FILE carry the bytes?" -- SizeOfRawData and the file
  length -- and `vsz_declared` asks separately whether VirtualSize covers the region.
  Requiring both in one predicate (`assert grown or ungrown` over the whole quadruple)
  made the newmapgen-rebuild state unreachable by BOTH `--apply` and `--undo`: the assert
  sat above the `if args.undo:` block, so the binary was left broken with its own script
  refusing to act in either direction.  Recovery would have needed the snapshot.

  `.nmg` is the last section and its raw data ends exactly at EOF, so it grows in place:

      VirtualSize  0x5DD6 (vanilla) / 0x6E00 (spinners only) -> 0x8C00
      SizeOfRawData             0x6E00                       -> 0x8C00
      SizeOfImage               0x0019A000                    -> 0x0019C000
      file length               0x00192200                    -> 0x00194000   (+0x1E00)

  ⚠ SizeOfImage is an RVA-space quantity: align(0x193000 + 0x8C00, 0x1000) = 0x19C000.
  The spec drafted `0x59C000`, which is that number with ImageBase folded in; writing it
  would declare a 5.8 MB image.  0x19C000 is used.
  Free zeroed space in `.nmg` before this change was only 554 + 124 + 2816 = 3494 B against
  the 9958 B the grown DFM needs, which is why the section has to be extended at all.

  Layout inside `.nmg`, all verified against the section table on every run:
      rva 0x193000..0x198DD6   build_deved_newmapgen.py's body (its own DFM ends here)
      rva 0x199000..0x1993FF   this script's cave      (1024 B reserved, 644 used)
      rva 0x199400..0x19BAE6   the grown TITEMEDITFORM (9958 B)
      rva 0x19BAE6..0x19BC00   zero slack

  Nothing is displaced anywhere: the file only gains bytes at EOF, and the only in-place
  writes outside the cave are 16 DFM Int8s, 3 call operands, 3 PE header dwords and the
  8-byte resource data entry.  Audited: the base-relocation directory has ZERO fixups
  anywhere in `.rsrc` and zero anywhere in `.nmg`, so nothing here can strand a reloc.
  (The PE CheckSum field was already stale before this script existed -- computed
  0x194E35 against a stored 0xDE30B -- and Windows does not verify it for a user-mode exe,
  so it is left alone, as every other script in this project leaves it.)

TItem.SetItemType's ASYMMETRY IS PRESERVED ON PURPOSE
  `TItem.SetItemType @0x5579457C` zeroes `+0x46..+0x49` on a type change and deliberately
  does NOT zero `+0x4A/+0x4B`.  So changing an item's type resets the four combat bonuses
  and KEEPS HP/MV.  That is the second reason `ItemTypeBoxChange` must not be a creation
  hook: it re-runs UpdateControls, which reloads all six spinners, and the two new ones
  must show the values that survived.

PERSISTENCE NEEDS NOTHING HERE, AND Zig.ail IS NOT TOUCHED
  `AoWDevEd.exe` imports AoWEPACK / EngineP / VCLADDON by bare name and runs from
  `Ziggurat\`, so it loads the PATCHED packages.  `TItem` does not override Assign/Copy and
  `Engine.TEObject.Assign @0x555191F4` is a stream round-trip, so both the dialog's
  Copy-edit-Assign and the library save run through the patched `TItem.ReadWrite`; tags
  0x17/0x18 round-trip for free.  This script writes to exactly one file.

⚠ FORWARD HAZARDS
  ⚠⚠ `build_deved_newmapgen.py --apply` REBUILDS `.nmg` in place -- `del d[exist_raw:]`,
    then the fresh body plus zero padding out to SizeOfRawData, then
    VirtualSize := len(body).  Since the icons landed that no longer erases a cave and a
    header field; it erases a LIVE RESOURCE.  The directory entry would still point at
    rva 0x199400 and Item Properties would fail to OPEN with a `TReader` error, not merely
    lose its icons.  Its `rawsz = max(exist_rawsz, ...)` keeps SizeOfRawData at 0x8C00, so
    the file length and SizeOfImage survive -- only VirtualSize and the bytes do not.
    That asymmetry is exactly the DAMAGED state this script now recognises: re-run
    `build_deved_itemhpmv.py --apply` (it repairs in place) and then
    `build_zigeditor.py --apply`.
    ⚠ Its `--undo` (newmapgen lines 1486-1508) is surgical -- rel32, three VMT slots and
    its own resource entry -- and explicitly leaves `.nmg` alone, so it is NOT a hazard.
    ⚠ And the hazard is LATENT, not live: newmapgen `--apply` refuses while applied
    ("already applied (OKBtnClick -> 0x593000)") and its `--undo` needs
    `Ziggurat\backups\AoWDevEd.exe.pre-newmapgen`, which does not exist.  Neither half can
    run today.  Recorded so a future session that recreates that snapshot knows the order.

  ⚠ ANY EDIT MADE ONLY TO THE LIVE `.nmg` COPY IS SILENTLY REVERTED BY THE NEXT --apply.
    `build_new_dfm()` rebuilds the live copy from the `.rsrc` MASTER every run, so a script
    that correctly walks the resource directory (build_editor_toolbar.py,
    build_deved_terrainpal.py, build_deved_toolbar_trim.py, build_deved_heroprune.py,
    build_deved_newmapgen.py all do) edits only the copy -- and this script throws that
    away.  The verify path would print "DRY RUN", not name the problem.  A future edit to
    TITEMEDITFORM must go into the master at file 0x000697A8, or into this script.
  ⚠ TITEMEDITFORM's DFM now exists TWICE in the exe: the dead master in `.rsrc` and the
    live copy in `.nmg`.  Any whole-file DFM scanner sees both.  The one that matters today
    is `build_editor_spinners.py`, which regex-scans for `\x08MaxValue\x02` and names its
    owner from the preceding text: it now reports 4 extra sites (AttackEdit / DefenseEdit /
    ResistanceEdit / DamageEdit) and patches both copies to the same value, so the two
    compose -- but a future scanner that asserts a site COUNT will trip.
  * `build_useitems.py` already patches `UpdateControls`, at 0x0041349C
    (`cmp byte [eax+0x34],6` -> `0x7F`, the itUse grey-out).  No byte overlap with the
    three operand windows here, and it is located by signature rather than address, so the
    two compose; noted because the same function now has two owners.
  * `build_editor_spinners.py` owns the DFM `MaxValue` ceilings on this form (all four = 60)
    and matches its owners by SUBSTRING across the whole exe.  The two new spinners are
    runtime-created and have no DFM MaxValue, so they are invisible to it -- and must stay
    that way: do not give a future DFM control a name containing `HitsEdit` or `MovesEdit`.
  * `.nmg` code is NOT shared: the only other script with a cave in it is
    build_deved_newmapgen.py (the section owner).  `grep -rl '\.nmg'` across build_scripts/
    returns FOUR files, not two -- build_deved_levelnav.py names it in prose only (its cave
    is `.tres @0x00592080`).
  ⚠ The fourth is `build_editor_autosave.py`, and it is a forward hazard.  It APPENDS a new
    PE section (`.asv`) to its targets.  It is not applied to either editor binary today
    (no `.asv` in either section table), but if it ever is, `.nmg` stops being the last
    section and its raw data stops ending at EOF.  That invariant is what
    build_deved_newmapgen.py's `'.nmg is not the last section ... cannot grow'` assert
    tests, and what this cave's "regrow behind a newmapgen rebuild" story depends on.
    Apply autosave to an editor binary and BOTH .nmg scripts need re-checking.

⚠⚠ AFTER --apply YOU MUST RUN `build_zigeditor.py --apply`
  This patches `AoWDevEd.exe`, the editor patch SOURCE.  The editor the owner runs is
  `AoWzEd.exe`, derived from it.  Skipping the rebuild leaves the patch verifying clean
  against a binary nobody launches -- and it bites `--undo` exactly as hard.

USAGE
    python build_scripts/build_deved_itemhpmv.py            # dry run + verify
    python build_scripts/build_deved_itemhpmv.py --dis      # + cave disasm + icon nodes
    python build_scripts/build_deved_itemhpmv.py --apply    # write
    python build_scripts/build_deved_itemhpmv.py --undo     # surgical revert

`--undo` is surgical and EXACT: it restores the 3 call operands, the 16 DFM bytes, the
resource entry, the 3 PE header dwords, zeroes the cave AND the relocated DFM, and cuts the
file back to 0x192200 -- the pre-apply MD5 including file length.  ⚠ Zeroing before cutting
is load-bearing: the relocated DFM starts at file 0x191800, BELOW the old EOF, so 2560 of
its bytes would otherwise survive the truncation.

Needs `pip install keystone-engine capstone`.
"""
import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# <game>/Ziggurat/Modding Resources/build_scripts/ -> two levels up is <game>/Ziggurat
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
RE_TOOLS = os.path.join(GAME, "Modding Resources", "re_tools")

EXE = "AoWDevEd.exe"
IMAGE_BASE = 0x400000

BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP_SUFFIX = ".pre-itemhpmv"

# ---- cave ---------------------------------------------------------------------------
CAVE_VA = 0x00599000
CAVE_END = 0x00599400                       # exclusive reservation, 1024 B.  Raised from
                                            # 768 B when the relocated DFM moved in above
                                            # it, so the two can never meet.
CAVE_LEN = CAVE_END - CAVE_VA

G_FORM = CAVE_VA + 0x00
G_HPSPIN = CAVE_VA + 0x04
G_MVSPIN = CAVE_VA + 0x08
LIT_VA = CAVE_VA + 0x10                     # two AnsiString literals live here
CODE_VA = CAVE_VA + 0x40                    # 16-byte aligned, clear of the literals

NMG_VA = 0x00593000                         # .nmg, rva 0x193000
NMG_VSZ_ORIG = 0x5DD6                       # build_deved_newmapgen.py's body length
NMG_VSZ_SPIN = 0x6E00                       # what v1 (spinners only) raised VirtualSize to
NMG_RSZ_ORIG = 0x6E00                       # SizeOfRawData before the icons
NMG_SZ_OURS = 0x8C00                        # VirtualSize == SizeOfRawData afterwards
SECT_ALIGN = 0x1000
FILE_ALIGN = 0x200
SIZEOFIMAGE_ORIG = 0x0019A000               # align(0x193000 + 0x6E00, 0x1000)
SIZEOFIMAGE_OURS = 0x0019C000               # align(0x193000 + 0x8C00, 0x1000).  ⚠ RVA
                                            # space -- NOT 0x59C000, which is this number
                                            # with ImageBase folded in.

# ---- the three retarget sites --------------------------------------------------------
#   (name, site VA, vanilla 5 bytes, original callee VA, cave entry key)
SITES = [
    ("hookA_view", 0x004137DC, bytes.fromhex("E83BFAFFFF"), 0x0041321C, "enter"),
    ("hookB_edit", 0x0041389F, bytes.fromhex("E878F9FFFF"), 0x0041321C, "enter"),
    ("hookC_load", 0x004133AE, bytes.fromhex("E835FDFEFF"), 0x004030E8, "load"),
]
UPDATECONTROLS = 0x0041321C

# ---- imported thunks (jmp dword ptr [iat]) -------------------------------------------
T_SETVALUE = 0x004030E8                     # VCLADDON SpinEdit.TSpin.SetValue  EAX,EDX
T_GETVALUE = 0x004030E0                     # VCLADDON SpinEdit.TSpin.GetValue  EAX -> EAX
T_SETTEXT = 0x00401568                      # VCL30 Controls.TControl.SetText   EAX,EDX
T_SETCOLOR = 0x004015A0                     # VCL30 Controls.TControl.SetColor  EAX,EDX
THUNK_IAT = {
    T_SETVALUE: 0x00433574, T_GETVALUE: 0x00433578,
    T_SETTEXT: 0x00432398, T_SETCOLOR: 0x0043237C,
}

IAT_TSPIN = 0x0043357C                      # holds the SpinEdit..TSpin class ref itself
IAT_TLABEL = 0x00432654                     # holds the StdCtrls..TLabel class ref itself

V_CREATE = 0x24                             # virtual constructor, overridden by both
V_SETPARENT = 0x3C
V_SETBOUNDS = 0x4C                          # TSpin: TWinControl.SetBounds -- an override

SP_MINVALUE = 0x130
SP_MAXVALUE = 0x134
SP_EDITORENABLED = 0x140                    # NOT 0x120; 0x120 is AutoSelect
SP_ONCHANGE_CODE = 0x128
SP_ONCHANGE_DATA = 0x12C

# ---- TItemEditForm, from the published field table at 0x00412DC0 ---------------------
VMT_ITEMEDITFORM = 0x00412D40
INSTSIZE_ITEMEDITFORM = 0x284
F_STATISTICSPNL = 0x224
F_ITEM = 0x27C                              # private: the working TItem copy
F_READONLY = 0x280                          # private: 1 = view mode
ITEM_HP = 0x4A
ITEM_MV = 0x4B
CL_BTNFACE = 0x8000000F

# ---- geometry -----------------------------------------------------------------------
# ⭐ ONE rule for all six rows.  The four existing rows are re-pitched by the DFM edits
# below and the two new ones are built by the cave, so the numbers used to live in two
# places; they are now derived from `row_y` / `label_y` / `icon_y` everywhere, including
# `make_icon_node`.  Change ROW_PITCH or SPIN_H and all six move together.
ROW_PITCH = 24
ROW0_Y = 16                                 # the first spin's Top
SPIN_H = 22
VAN_SPIN_H = 26                             # vanilla, on the 32 px pitch
SPIN_X, SPIN_W = 124, 50
LBL_X, LBL_W, LBL_H = 28, 90, 16
LBL_DY = 3                                  # a 16 px label centred on a 22 px spin
PANEL_H = 161                               # StatisticsPnl, unchanged
HP_MAX = 60                                 # owner's call: mirror the existing four
MV_MAX = 50


def row_y(i):
    """Top of row i's spinner.  Rows 0..3 are the vanilla four, 4 = HP, 5 = MV."""
    return ROW0_Y + i * ROW_PITCH


def label_y(spin_y):
    return spin_y + LBL_DY


def icon_y(spin_y, height):
    """An icon centred on its spinner, as far as integer division allows.

    Reproduces all four existing rows exactly -- H17 -> spin+2, H16 -> spin+3 -- and is
    the ONLY place the rule is written.  ⚠ `height` is the CONTROL's height, read out of
    the DFM; it is not guessable from the bitmap (THEROEDITFORM's 16x16 Hits bitmap sits
    in a 17 px control and its 32x15 Moves bitmap in a 16 px one).
    """
    return spin_y + (SPIN_H - height) // 2


HP_ROW, MV_ROW = 4, 5
HP_Y = row_y(HP_ROW)                        # 112
MV_Y = row_y(MV_ROW)                        # 136
assert MV_Y + SPIN_H <= PANEL_H, \
    "row %d (Top %d, %d high) overflows the %d px StatisticsPnl -- the panel would clip it" \
    % (MV_ROW, MV_Y, SPIN_H, PANEL_H)
CAP_HP = b"Hit Points:"
CAP_MV = b"Movement:"

# ---- the DFM re-pitch ---------------------------------------------------------------
DFM_RES_TYPE = 10                           # RT_RCDATA
DFM_RES_NAME = "TITEMEDITFORM"
DFM_FILE_OFF = 0x000697A8                   # asserted against the resource directory
DFM_RVA_ORIG = 0x0006D1A8                   # ... and so is this
DFM_LEN = 0x1D3F
DFM_NEW_VA = CAVE_END                       # the relocated copy starts where the cave ends

# ---- the two icons, lifted out of THEROEDITFORM --------------------------------------
ICON_RES_NAME = "THEROEDITFORM"
ICON_SRC_OFF = 0x0005ACE4                   # asserted against the resource directory
ICON_SRC_LEN = 0x5E68
#: (source TImage, new name, row index, expected Picture.Data payload length)
#: ⚠ the new names are 7 characters, exactly as long as the sources': a DFM name is a
#: shortstring, so an equal length keeps the copy a pure byte substitution.
ICONS = [("Image11", "Image13", HP_ROW, 834),   # 16x16x24 BMP -- but a 17 px HIGH control
         ("Image12", "Image14", MV_ROW, 1506)]  # 32x15x24 BMP, CLIPPED to a 17x16 control
ICON_AFTER = "Image6"                       # insert straight after the last existing icon
ICON_LEFT = 4                               # the column the existing four sit in
#: the four already on the form, as a cross-check that this is one icon set: each is
#: byte-identical to the THEROEDITFORM TImage named here
ICON_TWINS = [("Image6", "Image9"), ("Image7", "Image7"),
              ("Image10", "Image10"), ("Image8", "Image8")]

# ---- the DFM re-pitch, TOP TO BOTTOM -------------------------------------------------
#: (spinner, label, icon, vanilla spin Top, vanilla label Top, vanilla icon Top)
#: ⚠ the icon's HEIGHT is deliberately NOT listed: it is read out of the DFM and fed to
#: `icon_y`, so all six icons follow one rule.  Baking 18/42/66/91 here -- as this list
#: used to -- meant the two new icons tracked a ROW_PITCH change and the four existing
#: ones silently did not.
ROWS = [("AttackEdit",     "Label2", "Image6",  24,  28,  28),
        ("DamageEdit",     "Label7", "Image7",  56,  60,  60),
        ("DefenseEdit",    "Label5", "Image10", 88,  92,  94),
        ("ResistanceEdit", "Label6", "Image8", 120, 124, 126)]
assert len(ROWS) == HP_ROW, "the new rows must come straight after the existing ones"


# ====================================================================================
# PE helpers
# ====================================================================================
def load_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[e:e + 4] == b"PE\0\0", "bad PE header"
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        name = bytes(d[b:b + 8]).rstrip(b"\0")
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        chars = struct.unpack_from("<I", d, b + 36)[0]
        secs.append(dict(name=name, va=va, vsz=vsz, raw=raw, rsz=rsz, chars=chars, hdr=b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                imagebase=struct.unpack_from("<I", d, opt + 28)[0],
                salign=struct.unpack_from("<I", d, opt + 32)[0],
                falign=struct.unpack_from("<I", d, opt + 36)[0])


def align_up(x, a):
    return (x + a - 1) // a * a


def va2off(F, va):
    """VA -> file offset, bounded by each section's RAW data.

    Bounded by `rsz`, never `max(vsz, rsz)`: the loose form happily maps an address in one
    section's page slack onto the NEXT section's raw bytes.  Everything this script writes
    is file-backed, so a refusal here is a real error, not a case to work around.
    """
    rva = va - F["imagebase"]
    for s in F["secs"]:
        if s["va"] <= rva < s["va"] + s["rsz"]:
            return s["raw"] + (rva - s["va"])
    raise ValueError("VA %#x has no raw file bytes" % va)


def find_rcdata(d, F, want_name):
    """Locate an RCDATA resource by name -> (entry file offset, data rva, size).

    The ENTRY offset is what makes relocation possible: rewriting the `(OffsetToData, Size)`
    pair there moves the resource without touching a byte of the data.  Same three-level
    walk `build_deved_newmapgen.py`'s `find_dfm_entry()` does; generalised to take the
    resource name rather than hard-coding TNEWMAPDLG.

    ⚠ Returns the RVA, not a file offset: after relocation the data lives in `.nmg`, and a
    caller that wants file bytes must convert once the section header has been grown.
    """
    rsrc_rva = struct.unpack_from("<I", d, F["opt"] + 96 + 2 * 8)[0]
    base = va2off(F, F["imagebase"] + rsrc_rva)

    def entries(off):
        nnamed, nid = struct.unpack_from("<HH", d, off + 12)
        out = []
        for i in range(nnamed + nid):
            nm, sub = struct.unpack_from("<II", d, off + 16 + i * 8)
            if nm & 0x80000000:
                p = base + (nm & 0x7FFFFFFF)
                ln = struct.unpack_from("<H", d, p)[0]
                nm = bytes(d[p + 2:p + 2 + ln * 2]).decode("utf-16-le")
            out.append((nm, sub))
        return out

    for tname, tsub in entries(base):
        if tname != DFM_RES_TYPE or not (tsub & 0x80000000):
            continue
        for rname, rsub in entries(base + (tsub & 0x7FFFFFFF)):
            if rname != want_name or not (rsub & 0x80000000):
                continue
            for _lname, lsub in entries(base + (rsub & 0x7FFFFFFF)):
                assert not (lsub & 0x80000000), "unexpected 4th resource level"
                rva, size = struct.unpack_from("<II", d, base + lsub)
                return base + lsub, rva, size
    raise SystemExit("resource RCDATA/%s not found" % want_name)


# ====================================================================================
# DFM emit + walk
# ====================================================================================
def ss(text):
    """A Delphi shortstring: one length byte then the characters."""
    b = text.encode("latin1")
    assert len(b) < 256, text
    return bytes([len(b)]) + b


def v_i(n):
    """The SMALLEST integer encoding, which is what Delphi itself writes.  ⚠ vaInt8 is
    SIGNED: 139 does not fit, so the MV icon's Top is a vaInt16 while the HP icon's is a
    vaInt8.  Getting that wrong desyncs the whole form, not just one property."""
    if -128 <= n <= 127:
        return b"\x02" + struct.pack("<b", n)
    if -32768 <= n <= 32767:
        return b"\x03" + struct.pack("<h", n)
    return b"\x04" + struct.pack("<i", n)


def dfm_prop(name, val):
    return ss(name) + val


def walk_objs(dfm):
    """dfm_edit.walk, plus the END offset of every object.

    dfm_edit records a `$class` pseudo-property spanning [object start .. after Name] but
    stops there, and an insertion point has to be an object BOUNDARY: a DFM object is
    `[filer prefix] ClassName Name props 0x00 children 0x00`, so its end is only known
    after its children have been walked.
    """
    sys.path.insert(0, RE_TOOLS)
    import dfm_edit

    class _Objs(dfm_edit.W):
        def __init__(self, d, o=0):
            dfm_edit.W.__init__(self, d, o)
            self.objs = []

        def obj(self, path):
            start = self.o
            if (self.d[self.o] & 0xF0) == 0xF0:
                if self.u8() & 0x02:                    # ffChildPos
                    self.value(path, "$childpos")
            cls = self.sstr()
            nm = self.sstr()
            here = path + "/" + (nm or cls)
            self.props.append((here, "$class", -1, start, self.o, cls))
            rec = [here, cls, nm, start, None]
            self.objs.append(rec)
            while self.d[self.o] != 0:
                p = self.sstr()
                pstart = self.o - 1 - len(p)
                self.value(here, p)
                self.props[-1] = self.props[-1][:3] + (pstart,) + self.props[-1][4:]
            self.o += 1
            while self.d[self.o] != 0:
                self.obj(here)
            self.o += 1
            rec[4] = self.o

    assert dfm[:4] == b"TPF0", "not a DFM (starts %r)" % dfm[:4]
    w = _Objs(dfm, 4)
    w.obj("")
    w.consumed = w.o
    assert w.consumed == len(dfm), \
        "DFM walk consumed %d of %d bytes -- desync, refusing to edit" % (w.consumed, len(dfm))
    return w


def one_obj(w, name):
    """-> (start, end) of the single object called `name`."""
    hits = [o for o in w.objs if o[2] == name]
    assert len(hits) == 1, "expected 1 object named %s, found %d" % (name, len(hits))
    return hits[0][3], hits[0][4]


def one_prop(w, obj_name, prop):
    """-> (start, end) of one property INCLUDING its name bytes."""
    hits = [p for p in w.props if p[0].endswith("/" + obj_name) and p[1] == prop]
    assert len(hits) == 1, "expected 1 %s.%s, found %d" % (obj_name, prop, len(hits))
    return hits[0][3], hits[0][4], hits[0][5]


def make_icon_node(src, src_w, src_name, new_name, spin_y):
    """Rebuild one TImage: `Picture.Data` copied byte for byte, geometry re-emitted.

    -> (node bytes, payload length, width, height, top)
    """
    a, b, _v = one_prop(src_w, src_name, "Picture.Data")
    pic = bytes(src[a:b])
    n = pic[0]
    assert pic[1:1 + n] == b"Picture.Data" and pic[1 + n] == 0x0A, \
        "%s.Picture.Data is not a vaBinary property" % src_name
    plen = struct.unpack_from("<I", pic, 2 + n)[0]
    assert len(pic) == 1 + n + 1 + 4 + plen, "%s.Picture.Data length is inconsistent" % src_name
    # the payload's own header, so a foreign resource cannot slip through as "a bitmap"
    k = pic[6 + n]
    assert pic[7 + n:7 + n + k] == b"TBitmap", "%s does not hold a TBitmap" % src_name
    bm = 6 + n + 1 + k + 4
    assert pic[bm:bm + 2] == b"BM", "%s's TBitmap payload is not a DIB" % src_name

    _ca, _cb, cls = one_prop(src_w, src_name, "$class")
    assert cls == "TImage", "%s is a %s, not a TImage" % (src_name, cls)
    _wa, _wb, width = one_prop(src_w, src_name, "Width")
    _ha, _hb, height = one_prop(src_w, src_name, "Height")
    # ⚠ DERIVED, not baked -- and through the SAME `icon_y` the existing four go through
    # (H17 -> spin+2, H16 -> spin+3).  Image11 is the 17 px one and Image12 the 16 px one,
    # which is the opposite of what their bitmap sizes suggest.
    top = icon_y(spin_y, height)
    node = (ss("TImage") + ss(new_name)
            + dfm_prop("Left", v_i(ICON_LEFT)) + dfm_prop("Top", v_i(top))
            + dfm_prop("Width", v_i(width)) + dfm_prop("Height", v_i(height))
            + pic + b"\x00" + b"\x00")
    return node, plen, width, height, top


def build_new_dfm(d, dfm_fields):
    """The relocated TITEMEDITFORM: the `.rsrc` master with our 16 re-pitch values forced
    in and the two TImage nodes inserted after `ICON_AFTER`.

    The master on disk may be at vanilla or at ours (or half-way); the values are forced
    here rather than read, so the emitted resource is the same bytes either way and
    `--apply` is idempotent from any accepted state.
    """
    master = bytearray(d[DFM_FILE_OFF:DFM_FILE_OFF + DFM_LEN])
    for f in dfm_fields:
        master[f["off"] - DFM_FILE_OFF] = f["ours"] & 0xFF
    w = walk_objs(bytes(master))

    src = bytes(d[ICON_SRC_OFF:ICON_SRC_OFF + ICON_SRC_LEN])
    src_w = walk_objs(src)
    # this is one icon set, not two: prove it before copying anything out of the hero form
    for item_name, hero_name in ICON_TWINS:
        ia, ib, _ = one_prop(w, item_name, "Picture.Data")
        ha, hb, _ = one_prop(src_w, hero_name, "Picture.Data")
        assert bytes(master[ia:ib]) == src[ha:hb], \
            "item %s and hero %s are not the same icon -- re-derive before copying" \
            % (item_name, hero_name)

    nodes, info = b"", []
    for src_name, new_name, row, want_len in ICONS:
        assert not any(o[2] == new_name for o in w.objs), \
            "%s already exists on TITEMEDITFORM" % new_name
        assert len(new_name) == len(src_name), "%s is not the same length as %s" \
            % (new_name, src_name)
        node, plen, wd, ht, top = make_icon_node(
            src, src_w, src_name, new_name, row_y(row))
        assert plen == want_len, "%s payload is %d B, expected %d" % (src_name, plen, want_len)
        nodes += node
        info.append(dict(src=src_name, new=new_name, payload=plen, w=wd, h=ht, top=top,
                         size=len(node)))

    _oa, at = one_obj(w, ICON_AFTER)                    # insert at an object BOUNDARY
    out = bytes(master[:at]) + nodes + bytes(master[at:])
    # the rebuilt form must re-parse, and gain exactly the two objects
    w2 = walk_objs(out)
    assert len(w2.objs) == len(w.objs) + len(ICONS), "object count is %d, expected %d" \
        % (len(w2.objs), len(w.objs) + len(ICONS))
    for _s, new_name, _r, _l in ICONS:
        assert sum(1 for o in w2.objs if o[2] == new_name) == 1, "%s is not present once" % new_name
        assert one_obj(w2, new_name)[0] > one_obj(w2, "StatisticsPnl")[0], \
            "%s landed outside StatisticsPnl" % new_name
        assert [o for o in w2.objs if o[2] == new_name][0][0].endswith(
            "/StatisticsPnl/" + new_name), "%s is not a child of StatisticsPnl" % new_name
    return out, info


# ====================================================================================
# the cave
# ====================================================================================
def ansistring(text):
    """Delphi 3 immutable AnsiString literal, exactly the shape the compiler emits here
    (the shipped '.csm' at 0x0042E134 is `FF FF FF FF 04 00 00 00 '.csm' 00`): refcount -1,
    length, chars, NUL, padded to 4.  The pointer handed to SetText is the CHARS."""
    body = struct.pack("<iI", -1, len(text)) + text + b"\0"
    while len(body) % 4:
        body += b"\0"
    return body, 8                                      # blob, offset of the chars


def mk_control(classref_iat, x, y, w, h, fail_label):
    """Create one VCL control owned by nobody, parent it to EDI, and place it.
    Leaves the control in ESI.  Clobbers EAX/EDX/ECX/EBX."""
    return f"""
        xor  ecx, ecx                                   /* AOwner = nil, deliberately */
        mov  dl, 1
        mov  eax, dword ptr [{classref_iat:#x}]
        call dword ptr [eax + {V_CREATE:#x}]
        mov  esi, eax
        test esi, esi
        jz   {fail_label}
        mov  eax, esi                                   /* Parent := StatisticsPnl */
        mov  edx, edi
        mov  ebx, dword ptr [esi]
        call dword ptr [ebx + {V_SETPARENT:#x}]
        mov  eax, esi                                   /* SetBounds({x},{y},{w},{h}) */
        mov  edx, {x}
        mov  ecx, {y}
        push {w}
        push {h}
        mov  ebx, dword ptr [esi]
        call dword ptr [ebx + {V_SETBOUNDS:#x}]
"""


def cave_bodies(lit_hp, lit_mv, change_va):
    """Three independent bodies, emitted in this order: cave_change (so its VA is CODE_VA
    and needs no fixup pass), cave_load, cave_enter."""
    change = f"""
        /* ---- cave_change: shared TSpin.OnChange.  EAX = form (Data), EDX = Sender ---- */
        push ebx
        push esi
        cmp  eax, dword ptr [{G_FORM:#x}]
        jne  cc_done
        cmp  edx, dword ptr [{G_HPSPIN:#x}]
        je   cc_hp
        cmp  edx, dword ptr [{G_MVSPIN:#x}]
        jne  cc_done                                    /* neither -> do nothing at all */
        mov  ecx, {ITEM_MV:#x}
        jmp  cc_go
    cc_hp:
        mov  ecx, {ITEM_HP:#x}
    cc_go:
        mov  ebx, dword ptr [eax + {F_ITEM:#x}]         /* the working TItem copy */
        test ebx, ebx
        jz   cc_done
        mov  esi, ecx                                   /* GetValue clobbers ECX/EDX */
        mov  eax, edx
        call {T_GETVALUE:#x}
        cmp  eax, 127                                   /* saturate, never wrap */
        jle  cc_lo
        mov  eax, 127
    cc_lo:
        cmp  eax, -128
        jge  cc_store
        mov  eax, -128
    cc_store:
        mov  byte ptr [ebx + esi], al
    cc_done:
        pop  esi
        pop  ebx
        ret
"""
    load = f"""
        /* ---- cave_load: inside UpdateControls, ESI = item, EBX = form ---- */
        call {T_SETVALUE:#x}                            /* the displaced RES SetValue */
        cmp  ebx, dword ptr [{G_FORM:#x}]
        jne  cl_done
        mov  eax, dword ptr [{G_HPSPIN:#x}]
        test eax, eax
        jz   cl_done
        movsx edx, byte ptr [esi + {ITEM_HP:#x}]
        call {T_SETVALUE:#x}
        mov  eax, dword ptr [{G_MVSPIN:#x}]
        test eax, eax
        jz   cl_done
        movsx edx, byte ptr [esi + {ITEM_MV:#x}]
        call {T_SETVALUE:#x}
    cl_done:
        ret
"""
    enter = f"""
        /* ---- cave_enter: EAX = TItemEditForm.  Tail-jumps to UpdateControls. ---- */
        push ebp
        mov  ebp, esp
        push eax                                        /* [ebp-4] = the form */
        push ebx
        push esi
        push edi

        xor  eax, eax                                   /* invalidate BEFORE building */
        mov  dword ptr [{G_FORM:#x}], eax
        mov  dword ptr [{G_HPSPIN:#x}], eax
        mov  dword ptr [{G_MVSPIN:#x}], eax

        mov  eax, dword ptr [ebp - 4]
        mov  edi, dword ptr [eax + {F_STATISTICSPNL:#x}]
        test edi, edi
        jz   ce_done
{mk_control(IAT_TLABEL, LBL_X, HP_Y + 3, LBL_W, LBL_H, "ce_done")}
        mov  eax, esi                                   /* Caption := 'Hit Points:' */
        mov  edx, {lit_hp:#x}
        call {T_SETTEXT:#x}
{mk_control(IAT_TSPIN, SPIN_X, HP_Y, SPIN_W, SPIN_H, "ce_done")}
        mov  dword ptr [esi + {SP_MINVALUE:#x}], 0
        mov  dword ptr [esi + {SP_MAXVALUE:#x}], {HP_MAX}
        mov  byte ptr [esi + {SP_EDITORENABLED:#x}], 0
        mov  dword ptr [{G_HPSPIN:#x}], esi
{mk_control(IAT_TLABEL, LBL_X, MV_Y + 3, LBL_W, LBL_H, "ce_done")}
        mov  eax, esi                                   /* Caption := 'Movement:' */
        mov  edx, {lit_mv:#x}
        call {T_SETTEXT:#x}
{mk_control(IAT_TSPIN, SPIN_X, MV_Y, SPIN_W, SPIN_H, "ce_done")}
        mov  dword ptr [esi + {SP_MINVALUE:#x}], 0
        mov  dword ptr [esi + {SP_MAXVALUE:#x}], {MV_MAX}
        mov  byte ptr [esi + {SP_EDITORENABLED:#x}], 0
        mov  dword ptr [{G_MVSPIN:#x}], esi

        /* read-only (Execute): the same clBtnFace UpdateControls gives the other four.
           It disables GeneralSheet [form+0x1E4] rather than the spins, and our controls
           are inside it, so there is nothing else to mirror. */
        mov  eax, dword ptr [ebp - 4]
        cmp  byte ptr [eax + {F_READONLY:#x}], 0
        je   ce_publish
        mov  eax, dword ptr [{G_HPSPIN:#x}]
        mov  edx, {CL_BTNFACE:#x}
        call {T_SETCOLOR:#x}
        mov  eax, dword ptr [{G_MVSPIN:#x}]
        mov  edx, {CL_BTNFACE:#x}
        call {T_SETCOLOR:#x}
    ce_publish:
        mov  eax, dword ptr [ebp - 4]
        mov  dword ptr [{G_FORM:#x}], eax               /* publish LAST */
        mov  edx, dword ptr [{G_HPSPIN:#x}]
        mov  dword ptr [edx + {SP_ONCHANGE_CODE:#x}], {change_va:#x}
        mov  dword ptr [edx + {SP_ONCHANGE_DATA:#x}], eax
        mov  edx, dword ptr [{G_MVSPIN:#x}]
        mov  dword ptr [edx + {SP_ONCHANGE_CODE:#x}], {change_va:#x}
        mov  dword ptr [edx + {SP_ONCHANGE_DATA:#x}], eax
    ce_done:
        pop  edi
        pop  esi
        pop  ebx
        mov  eax, dword ptr [ebp - 4]                   /* UpdateControls wants EAX = Self */
        mov  esp, ebp
        pop  ebp
        jmp  {UPDATECONTROLS:#x}
"""
    return [("cave_change", change), ("cave_load", load), ("cave_enter", enter)]


def strip_comments(src):
    """keystone's Intel parser has no comment syntax.  `/* ... */` here SPANS LINES, so a
    per-line `split('/*')` leaves the continuation lines behind and they assemble as
    garbage operands -- strip the whole span."""
    out, i = [], 0
    while True:
        a = src.find("/*", i)
        if a < 0:
            out.append(src[i:])
            break
        out.append(src[i:a])
        b = src.find("*/", a)
        assert b > 0, "unterminated /* comment in the cave source"
        i = b + 2
    return "".join(out)


def build_cave(ks):
    """-> (cave bytes, {name: VA}, code_len, literal map).  Single pass: the literals sit
    at fixed addresses below CODE_VA and cave_change is first, so nothing needs fixing up."""
    hp_blob, hp_chars = ansistring(CAP_HP)
    mv_blob, mv_chars = ansistring(CAP_MV)
    lit = bytearray()
    lit_hp = LIT_VA + hp_chars
    lit += hp_blob
    lit_mv = LIT_VA + len(lit) + mv_chars
    lit += mv_blob
    assert LIT_VA + len(lit) <= CODE_VA, "the literals overflow into the code"

    entries, blobs, va = {}, [], CODE_VA
    for name, src in cave_bodies(lit_hp, lit_mv, CODE_VA):
        enc, _ = ks.asm(strip_comments(src), va)
        enc = bytes(enc)
        entries[name] = va
        blobs.append(enc)
        va += len(enc)
    assert entries["cave_change"] == CODE_VA, "cave_change must be first -- its VA is baked"

    code = b"".join(blobs)
    cave = bytearray(CAVE_LEN)
    cave[LIT_VA - CAVE_VA:LIT_VA - CAVE_VA + len(lit)] = lit
    cave[CODE_VA - CAVE_VA:CODE_VA - CAVE_VA + len(code)] = code
    used = CODE_VA - CAVE_VA + len(code)
    assert used <= CAVE_LEN, "cave needs %d B, reservation is %d B" % (used, CAVE_LEN)
    return bytes(cave), entries, len(code), used, dict(hp=lit_hp, mv=lit_mv)


def disassemble(cave, entries, code_len, lits):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    print("  %08X  %s ; G_FORM / G_HPSPIN / G_MVSPIN%s"
          % (CAVE_VA, cave[:12].hex(" "), "" if any(cave[:12]) else "  (all zero)"))
    for nm, va in (("Hit Points:", lits["hp"]), ("Movement:", lits["mv"])):
        o = va - CAVE_VA - 8
        n = 8 + len(nm) + 1
        print("  %08X  %-44s ; AnsiString %r, chars @ %#010x"
              % (CAVE_VA + o, cave[o:o + n].hex(" "), nm, va))
    labels = {va: nm for nm, va in entries.items()}
    code = cave[CODE_VA - CAVE_VA:CODE_VA - CAVE_VA + code_len]
    seen = 0
    for i in cs.disasm(code, CODE_VA):
        mark = "    <<< %s" % labels[i.address] if i.address in labels else ""
        print("  %08X  %-26s %-7s %s%s"
              % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str, mark))
        seen += i.size
    if seen != code_len:
        print("  !! capstone stopped after %d of %d code bytes - TRUNCATED INSTRUCTION"
              % (seen, code_len))
    return seen == code_len


def check_cave(cave, entries, code_len):
    """Read the emitted bytes BACK rather than trusting keystone (the `push 0xFFFF` ->
    `6A FF` imm8 trap is silent).  Every push in this cave is a geometry value."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    code = cave[CODE_VA - CAVE_VA:CODE_VA - CAVE_VA + code_len]
    ins = list(cs.disasm(code, CODE_VA))
    assert sum(i.size for i in ins) == code_len, "cave does not disassemble end to end"

    pushes = [int(i.op_str, 0) for i in ins
              if i.mnemonic == "push" and i.op_str.lstrip("-").replace("0x", "").isalnum()
              and not i.op_str.startswith(("e", "dword"))]
    want = [LBL_W, LBL_H, SPIN_W, SPIN_H] * 2
    assert pushes == want, "SetBounds immediates decoded as %r, expected %r" % (pushes, want)

    assert sum(1 for i in ins if i.mnemonic == "ret") == 2, "expected exactly 2 rets"
    tail = [i for i in ins if i.mnemonic == "jmp" and i.op_str == hex(UPDATECONTROLS)]
    assert len(tail) == 1, "cave_enter's tail jump to UpdateControls is missing"
    assert sum(1 for i in ins if i.mnemonic == "call"
               and i.op_str == "dword ptr [eax + 0x24]") == 4, \
        "expected 4 virtual constructor dispatches"
    assert sum(1 for i in ins if i.mnemonic == "call"
               and i.op_str == "dword ptr [ebx + 0x4c]") == 4, \
        "expected 4 virtual SetBounds dispatches"
    # the two ceilings must be the ones the owner asked for
    maxes = [int(i.op_str.split(",")[1], 0) for i in ins
             if i.mnemonic == "mov" and i.op_str.startswith("dword ptr [esi + 0x134],")]
    assert maxes == [HP_MAX, MV_MAX], "MaxValue immediates are %r" % (maxes,)
    # every rel32 CALL must leave the cave (intra-body jumps legitimately do not), and
    # every branch that stays inside must land on an instruction boundary
    starts = {i.address for i in ins}
    for i in ins:
        if not i.op_str.startswith("0x"):
            continue
        t = int(i.op_str, 16)
        if i.mnemonic == "call":
            assert not (CAVE_VA <= t < CAVE_END), \
                "call at %#x targets our own cave (%#x)" % (i.address, t)
        elif CAVE_VA <= t < CAVE_END:
            assert t in starts, "%s at %#x lands mid-instruction (%#x)" % (i.mnemonic, i.address, t)
    assert entries["cave_change"] == CODE_VA


# ====================================================================================
# state
# ====================================================================================
def read_sites(d, F, entries):
    tgt = {"enter": entries["cave_enter"], "load": entries["cave_load"]}
    st = []
    for name, site, orig, _callee, key in SITES:
        off = va2off(F, site)
        now = bytes(d[off:off + 5])
        patched = b"\xE8" + struct.pack("<i", tgt[key] - (site + 5))
        # "ours" = the operand lands anywhere INSIDE our exclusive reservation, not only at
        # this build's entry point, so a re-tune that shifts the entries can overwrite its
        # own previous output in place (CLAUDE.md: re-tuning is an in-place cave rewrite).
        ours = False
        if now[:1] == b"\xE8":
            t = site + 5 + struct.unpack("<i", now[1:5])[0]
            ours = CAVE_VA <= t < CAVE_END
        st.append(dict(name=name, site=site, off=off, now=now, orig=orig, patched=patched,
                       is_orig=now == orig, is_ours=ours, is_current=now == patched))
    return st


def plan_dfm_edits(w):
    """The 16 re-pitch values, DERIVED -- (path suffix, property, vanilla, ours).

    Every Top comes out of `row_y` / `label_y` / `icon_y`, and each icon's height is read
    from the DFM rather than listed, so the four existing rows and the two new ones cannot
    drift apart.
    """
    out = []
    for i, (spin, lbl, img, v_spin, v_lbl, v_img) in enumerate(ROWS):
        y = row_y(i)
        _a, _b, h = one_prop(w, img, "Height")
        out.append(("StatisticsPnl/" + spin, "Top", v_spin, y))
        out.append(("StatisticsPnl/" + spin, "Height", VAN_SPIN_H, SPIN_H))
        out.append(("StatisticsPnl/" + lbl, "Top", v_lbl, label_y(y)))
        out.append(("StatisticsPnl/" + img, "Top", v_img, icon_y(y, h)))
    return out


def read_dfm(d, dfm_off):
    """The 16 re-pitch bytes, read out of the MASTER `.rsrc` copy (which never moves)."""
    sys.path.insert(0, RE_TOOLS)
    import dfm_edit
    dfm = bytes(d[dfm_off:dfm_off + DFM_LEN])
    w = walk_objs(dfm)
    assert w.props[0][5] == "TItemEditForm", "resource is %r, not TItemEditForm" % w.props[0][5]
    out = []
    for suffix, prop, van, ours in plan_dfm_edits(w):
        hits = [p for p in w.props if p[0].endswith(suffix) and p[1] == prop]
        assert len(hits) == 1, "expected 1 %s.%s, found %d" % (suffix, prop, len(hits))
        _p, _n, t, _a, end, val = hits[0]
        assert t == dfm_edit.I8, "%s.%s is %s, not Int8 -- a length-neutral edit is off" \
            % (suffix, prop, dfm_edit.NAMES.get(t))
        assert -128 <= ours <= 127, "%s.%s derives to %d, outside vaInt8 -- the re-pitch " \
            "would change the DFM length" % (suffix, prop, ours)
        out.append(dict(what="%s.%s" % (suffix.split("/")[-1], prop), off=dfm_off + end - 1,
                        now=val, van=van, ours=ours))
    return out


def write(path, d):
    try:
        open(path, "wb").write(bytes(d))
    except PermissionError:
        raise SystemExit(
            "[%s] LOCKED - an AoW binary is running. Kill it and retry:\n"
            "  Get-Process | Where-Object { $_.ProcessName -match "
            "'^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd)$' } | Stop-Process -Force"
            % os.path.basename(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true",
                    help="surgical revert: 3 calls, 16 DFM bytes, the resource entry, "
                         "the .nmg/SizeOfImage headers, the appended bytes, the cave")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the cave and dump the two icon nodes")
    args = ap.parse_args()
    if args.apply and args.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    cave, entries, code_len, used, lits = build_cave(ks)
    check_cave(cave, entries, code_len)

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    orig_len = len(d)
    F = load_sections(d)
    assert F["imagebase"] == IMAGE_BASE, "ImageBase moved to %#x" % F["imagebase"]

    # --- allocation sanity ----------------------------------------------------------
    nmg = next((s for s in F["secs"] if s["name"] == b".nmg"), None)
    assert nmg is not None, ".nmg is absent -- run build_deved_newmapgen.py --apply first"
    assert F["imagebase"] + nmg["va"] == NMG_VA, ".nmg moved to %#x" % nmg["va"]
    assert nmg["chars"] & 0x80000000, ".nmg is not writable: %#x" % nmg["chars"]
    assert nmg is F["secs"][-1], \
        ".nmg is no longer the last section -- it cannot be grown in place"
    assert nmg["raw"] + nmg["rsz"] == orig_len, (
        ".nmg raw data ends at %#x but the file is %#x -- it must run to EOF to grow"
        % (nmg["raw"] + nmg["rsz"], orig_len))
    assert nmg["vsz"] in (NMG_VSZ_ORIG, NMG_VSZ_SPIN, NMG_SZ_OURS), (
        ".nmg VirtualSize is %#x, expected %#x (vanilla) / %#x (spinners only) / %#x (ours)"
        " -- newmapgen's body changed size; re-derive before writing"
        % (nmg["vsz"], NMG_VSZ_ORIG, NMG_VSZ_SPIN, NMG_SZ_OURS))
    assert nmg["rsz"] in (NMG_RSZ_ORIG, NMG_SZ_OURS), (
        ".nmg SizeOfRawData is %#x, expected %#x or %#x" % (nmg["rsz"], NMG_RSZ_ORIG, NMG_SZ_OURS))
    assert CAVE_VA - F["imagebase"] >= nmg["va"] + NMG_VSZ_ORIG, "cave overlaps newmapgen's body"
    assert CAVE_END - F["imagebase"] <= nmg["va"] + nmg["rsz"], "cave runs past .nmg's raw data"
    sizeofimage = struct.unpack_from("<I", d, F["opt"] + 56)[0]
    # ⚠ SizeOfImage tracks SizeOfRawData, NOT VirtualSize -- because `.nmg` is the last
    # section and the file runs to its raw end, and because build_deved_newmapgen.py
    # writes it that way too (`align(newva + rawsz, salign)`).  Deriving it is what lets
    # the DAMAGED state below be recognised rather than tripped over.
    assert sizeofimage == align_up(nmg["va"] + nmg["rsz"], SECT_ALIGN), (
        "SizeOfImage is %#x but .nmg's raw end rounds to %#x -- the image header is "
        "inconsistent with the section table" % (sizeofimage,
                                                 align_up(nmg["va"] + nmg["rsz"], SECT_ALIGN)))
    # both baked numbers re-derived here rather than trusted, so a changed alignment or a
    # moved .nmg fails loudly instead of writing a plausible-looking wrong image size
    assert SIZEOFIMAGE_ORIG == align_up(nmg["va"] + NMG_RSZ_ORIG, SECT_ALIGN)
    assert SIZEOFIMAGE_OURS == align_up(nmg["va"] + NMG_SZ_OURS, SECT_ALIGN)
    assert NMG_SZ_OURS % FILE_ALIGN == 0, "SizeOfRawData must be FileAlignment-aligned"
    assert F["salign"] == SECT_ALIGN and F["falign"] == FILE_ALIGN, \
        "alignments are %#x/%#x, not %#x/%#x" % (F["salign"], F["falign"], SECT_ALIGN, FILE_ALIGN)

    # --- thunks + class-ref cells still where the docstring says --------------------
    for thunk, iat in sorted(THUNK_IAT.items()):
        o = va2off(F, thunk)
        assert d[o] == 0xFF and d[o + 1] == 0x25 and \
            struct.unpack_from("<I", d, o + 2)[0] == iat, \
            "thunk %#x no longer jumps through %#x: %s" % (thunk, iat, bytes(d[o:o + 6]).hex())
    assert struct.unpack_from("<I", d, va2off(F, VMT_ITEMEDITFORM - 0x1C))[0] \
        == INSTSIZE_ITEMEDITFORM, "TItemEditForm InstanceSize is no longer %#x" \
        % INSTSIZE_ITEMEDITFORM

    # --- the DFM, located rather than assumed ---------------------------------------
    # The MASTER stays in `.rsrc` forever; only the directory ENTRY moves.
    entry_off, entry_rva, entry_size = find_rcdata(d, F, DFM_RES_NAME)
    _ie, icon_rva, icon_size = find_rcdata(d, F, ICON_RES_NAME)
    assert (va2off(F, F["imagebase"] + icon_rva), icon_size) == (ICON_SRC_OFF, ICON_SRC_LEN), (
        "RCDATA/%s is at file %#x len %#x, this script bakes %#x/%#x -- re-derive"
        % (ICON_RES_NAME, va2off(F, F["imagebase"] + icon_rva), icon_size,
           ICON_SRC_OFF, ICON_SRC_LEN))
    assert d[DFM_FILE_OFF:DFM_FILE_OFF + 4] == b"TPF0", \
        "the master TITEMEDITFORM at file %#x is not a DFM any more" % DFM_FILE_OFF

    new_dfm, icon_info = build_new_dfm(d, read_dfm(d, DFM_FILE_OFF))
    new_off = nmg["raw"] + (DFM_NEW_VA - F["imagebase"] - nmg["va"])
    need = (DFM_NEW_VA - F["imagebase"] - nmg["va"]) + len(new_dfm)
    assert need <= NMG_SZ_OURS, (
        ".nmg must be %#x to hold the relocated DFM, but NMG_SZ_OURS is %#x -- raise it "
        "(FileAlignment %#x) and SIZEOFIMAGE_OURS with it" % (need, NMG_SZ_OURS, FILE_ALIGN))
    assert DFM_NEW_VA >= CAVE_END, "the relocated DFM starts inside the cave reservation"

    cave_off = va2off(F, CAVE_VA)
    cave_now = bytes(d[cave_off:cave_off + CAVE_LEN])
    st = read_sites(d, F, entries)
    dfm = read_dfm(d, DFM_FILE_OFF)
    n_orig = sum(1 for s in st if s["is_orig"])
    n_ours = sum(1 for s in st if s["is_ours"])
    cave_installed = cave_now == cave
    cave_blank = not any(cave_now)
    dfm_van = sum(1 for f in dfm if f["now"] == f["van"])
    dfm_ours = sum(1 for f in dfm if f["now"] == f["ours"])
    vsz_now, rsz_now = nmg["vsz"], nmg["rsz"]
    # ⭐ `grown` asks ONE question -- "does the file carry the bytes?" -- and that is
    # SizeOfRawData alone.  It deliberately does NOT also require VirtualSize, because
    # build_deved_newmapgen.py --apply resets VirtualSize to its own body length while
    # leaving SizeOfRawData (and therefore the file length and SizeOfImage) at ours.  An
    # `assert grown or ungrown` over the whole quadruple made that state unreachable by
    # BOTH --apply and --undo: the binary was left with Item Properties broken and its own
    # script refusing to act.  The room and the declaration are now separate facts.
    grown = rsz_now == NMG_SZ_OURS and orig_len == nmg["raw"] + NMG_SZ_OURS
    ungrown = rsz_now == NMG_RSZ_ORIG and orig_len == nmg["raw"] + NMG_RSZ_ORIG
    vsz_declared = vsz_now == NMG_SZ_OURS       # VirtualSize actually covers our region
    entry_is_orig = (entry_rva, entry_size) == (DFM_RVA_ORIG, DFM_LEN)
    # "ours" is the ADDRESS, not the size: a re-tune that changes the node set changes the
    # length, and that must repair in place rather than read as foreign (CLAUDE.md:
    # re-tuning is an in-place cave rewrite, never revert-and-reapply).
    entry_is_ours = entry_rva == DFM_NEW_VA - F["imagebase"]
    reloc_now = bytes(d[new_off:new_off + len(new_dfm)]) if grown else b""
    reloc_installed = grown and reloc_now == new_dfm and entry_size == len(new_dfm)
    reloc_blank = grown and not any(reloc_now)
    # a previous build of ours: still a DFM, at our address, just a different length
    reloc_is_ours = grown and (reloc_installed or reloc_now[:4] == b"TPF0")
    # ---- the three states -------------------------------------------------------
    # `damaged` is the EXACT complement of `fully_ours` once the entry is ours, so the two
    # are defined together rather than spelled out twice and drifting apart.
    fully_ours = (n_ours == 3 and cave_installed and dfm_ours == len(dfm)
                  and vsz_declared and grown and entry_is_ours and reloc_installed)
    pristine = (n_orig == 3 and cave_blank and dfm_van == len(dfm)
                and vsz_now == NMG_VSZ_ORIG and entry_is_orig and ungrown)
    # DAMAGED: the resource entry points into `.nmg`, so the form is ALREADY relocated and
    # the editor will read whatever is there -- but something below it is not ours.  That
    # is a live, broken binary: Item Properties raises a TReader error rather than merely
    # losing its icons.  --apply REPAIRS it and --undo must stay reachable from it, so
    # neither may assert here.  The newmapgen rebuild lands here exactly: cave zeroed,
    # DFM zone zeroed, VirtualSize back to 0x5DD6, entry still at rva 0x199400.
    damaged = entry_is_ours and not fully_ours

    print("\n[%s] %d bytes   cave %#010x..%#010x  file %#08x" %
          (EXE, orig_len, CAVE_VA, CAVE_END - 1, cave_off))
    print("     %d B used of %d reserved (%d spare): 12 B globals, %d B literals, %d B code"
          % (used, CAVE_LEN, CAVE_LEN - used, CODE_VA - LIT_VA, code_len))
    for name, va in entries.items():
        print("       %-12s %#010x" % (name, va))
    for s in st:
        tag = "VANILLA" if s["is_orig"] else ("OURS" if s["is_ours"] else "*** FOREIGN ***")
        print("     %-11s %#010x  %s -> %s  [%s]"
              % (s["name"], s["site"], s["now"].hex(), s["patched"].hex(), tag))
    print("     cave region: %s"
          % ("blank" if cave_blank else
             ("installed, current" if cave_installed else
              "non-zero and NOT our current build (%d non-zero bytes)"
              % sum(1 for b in cave_now if b))))
    print("     .nmg VirtualSize %#x -> %#x | SizeOfRawData %#x -> %#x | SizeOfImage %#x "
          "-> %#x | file %#x -> %#x   [%s]"
          % (vsz_now, NMG_SZ_OURS, rsz_now, NMG_SZ_OURS, sizeofimage, SIZEOFIMAGE_OURS,
             orig_len, nmg["raw"] + NMG_SZ_OURS,
             ("GROWN" if vsz_declared else "raw grown, VirtualSize NOT declared")
             if grown else "not grown"))
    print("     DFM re-pitch (master @ %#08x): %d/%d at vanilla, %d/%d at ours" %
          (DFM_FILE_OFF, dfm_van, len(dfm), dfm_ours, len(dfm)))
    for f in dfm:
        tag = "vanilla" if f["now"] == f["van"] else \
              ("OURS" if f["now"] == f["ours"] else "*** FOREIGN ***")
        print("       file %#08x  %-24s %3d -> %3d  [%s]"
              % (f["off"], f["what"], f["now"], f["ours"], tag))
    print("     RCDATA/%s entry @ file %#08x: rva %#x size %#x -> rva %#x size %#x  [%s]"
          % (DFM_RES_NAME, entry_off, entry_rva, entry_size,
             DFM_NEW_VA - F["imagebase"], len(new_dfm),
             "VANILLA" if entry_is_orig else ("OURS" if entry_is_ours else "*** FOREIGN ***")))
    print("     relocated DFM: %d B at VA %#010x (file %#08x), %d B slack to %#010x  [%s]"
          % (len(new_dfm), DFM_NEW_VA, new_off, NMG_SZ_OURS - need,
             F["imagebase"] + nmg["va"] + NMG_SZ_OURS,
             "installed, current" if reloc_installed else
             ("blank" if reloc_blank else ("absent (.nmg not grown)" if not grown else
                                           "non-zero and NOT our current build"))))
    for i in icon_info:
        print("       %-8s <- %s %s  %dx%d at (%d,%d)  node %d B, Picture.Data %d B"
              % (i["new"], ICON_RES_NAME, i["src"], i["w"], i["h"], ICON_LEFT, i["top"],
                 i["size"], i["payload"]))
    if damaged:
        print("     *** DAMAGED: the resource entry already points into .nmg, but %s."
              % ", ".join(w for w in (
                  None if grown else "the section is not grown",
                  None if vsz_declared else "VirtualSize does not declare the region",
                  None if reloc_installed else "the relocated DFM is not ours",
                  None if cave_installed else "the cave is not ours",
                  None if n_ours == 3 else "not all 3 call sites point at the cave",
                  None if dfm_ours == len(dfm) else
                  "the master's re-pitch bytes are not ours") if w))
        print("         Item Properties is BROKEN in this binary (TReader error on open).")
        print("         --apply repairs it in place; --undo also works from here.")
        print("         The usual cause is a build_deved_newmapgen.py --apply in between.")

    if args.dis:
        print("\n---- cave disassembly ----")
        disassemble(cave, entries, code_len, lits)
        print("\n---- icon nodes (DFM data, no code) ----")
        for i in icon_info:
            head = new_dfm.find(ss("TImage") + ss(i["new"]))
            assert head >= 0, "%s is not in the rebuilt DFM" % i["new"]
            print("  +%#06x  %s" % (head, new_dfm[head:head + 48].hex(" ")))
            print("           %r ... %d B tail is the BM DIB, copied verbatim"
                  % ("".join(chr(c) if 32 <= c < 127 else "." for c in new_dfm[head:head + 48]),
                     i["size"] - 48))

    for f in dfm:
        assert f["now"] in (f["van"], f["ours"]), (
            "%s is %d, neither vanilla %d nor ours %d - ABORT"
            % (f["what"], f["now"], f["van"], f["ours"]))
    for s in st:
        assert s["is_orig"] or s["is_ours"], (
            "%s @ %#x is neither vanilla (%s) nor ours (%s): %s - ABORT"
            % (s["name"], s["site"], s["orig"].hex(), s["patched"].hex(), s["now"].hex()))
    assert entry_is_orig or entry_is_ours, (
        "RCDATA/%s points at rva %#x size %#x, neither vanilla (%#x/%#x) nor ours "
        "(%#x/%#x) - ABORT" % (DFM_RES_NAME, entry_rva, entry_size, DFM_RVA_ORIG, DFM_LEN,
                               DFM_NEW_VA - F["imagebase"], len(new_dfm)))
    if grown:
        assert reloc_is_ours or reloc_blank, \
            "the relocated-DFM zone at %#010x holds foreign bytes - ABORT" % DFM_NEW_VA
    # ⚠ NO assert on `entry_is_ours and not reloc_is_ours` -- that IS the damaged state,
    # and asserting it here (before the --undo block) is what made a newmapgen rebuild
    # unrecoverable in both directions.  It is reported above and repaired below.

    # ================================ undo =========================================
    if args.undo:
        if (n_orig == 3 and cave_blank and dfm_van == len(dfm)
                and vsz_now == NMG_VSZ_ORIG and entry_is_orig and ungrown):
            print("\n[%s] already vanilla everywhere - no-op" % EXE)
            return 0
        for s in st:
            d[s["off"]:s["off"] + 5] = s["orig"]
        for f in dfm:
            d[f["off"]] = f["van"] & 0xFF
        struct.pack_into("<II", d, entry_off, DFM_RVA_ORIG, DFM_LEN)
        cleared = sum(1 for b in cave_now if b)
        d[cave_off:cave_off + CAVE_LEN] = b"\0" * CAVE_LEN
        struct.pack_into("<I", d, nmg["hdr"] + 8, NMG_VSZ_ORIG)         # VirtualSize
        struct.pack_into("<I", d, nmg["hdr"] + 16, NMG_RSZ_ORIG)        # SizeOfRawData
        struct.pack_into("<I", d, F["opt"] + 56, SIZEOFIMAGE_ORIG)
        # ⚠⚠ TRUNCATION ALONE IS NOT ENOUGH.  The relocated DFM starts at file 0x191800,
        # which is BELOW the old EOF (0x192200) -- the first 2560 of its bytes live inside
        # the section's ORIGINAL raw data.  Cutting the file back would leave them behind
        # and the "restores the exact pre-apply MD5" claim would be false by 2560 bytes.
        # Zero from the DFM's start to the end of the buffer, THEN cut.
        want_len = nmg["raw"] + NMG_RSZ_ORIG
        dropped = len(d) - want_len
        d[new_off:] = b"\0" * (len(d) - new_off)
        del d[want_len:]
        assert len(d) == want_len, "truncation left %d bytes, wanted %d" % (len(d), want_len)
        assert not any(d[new_off:]), "the relocated-DFM zone did not zero out"
        assert dropped in (0, NMG_SZ_OURS - NMG_RSZ_ORIG), \
            "dropped %d bytes, expected 0 or %d" % (dropped, NMG_SZ_OURS - NMG_RSZ_ORIG)
        write(path, d)                                  # NO snapshot on --undo, ever
        print("\n[%s] UNDONE: 3 calls restored, 16 DFM bytes re-pitched back, RCDATA/%s "
              "repointed to rva %#x/%#x, %d non-zero cave bytes cleared in %#010x..%#010x."
              % (EXE, DFM_RES_NAME, DFM_RVA_ORIG, DFM_LEN, cleared, CAVE_VA, CAVE_END - 1))
        print("     .nmg VirtualSize -> %#x, SizeOfRawData -> %#x, SizeOfImage -> %#x, "
              "file %d -> %d bytes (%d dropped)."
              % (NMG_VSZ_ORIG, NMG_RSZ_ORIG, SIZEOFIMAGE_ORIG, orig_len, len(d), dropped))
        print("     No backup touched.")
        print("     !! Re-run `build_zigeditor.py --apply` so AoWzEd.exe follows.")
        return 0

    # ============================== verify / apply ==================================
    if fully_ours:
        print("\n[%s] already patched and up to date - chain intact." % EXE)
        return 0
    if not cave_blank and not cave_installed and n_ours == 0:
        raise SystemExit("cave is dirty but no site points at it - ABORT, investigate %#x"
                         % CAVE_VA)

    if not args.apply:
        print("\n  DRY RUN -- nothing written. Re-run with --apply%s."
              % (" to REPAIR the damaged state above" if damaged else ""))
        return 0

    # --- snapshot: ONLY on --apply, ONLY over a PROVEN-unpatched file ---------------
    backup = os.path.join(BACKUP_DIR, EXE + BACKUP_SUFFIX)
    if pristine and not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print("\n    backup -> %s   (3 sites vanilla, cave blank, DFM un-pitched, "
              "resource entry in .rsrc, .nmg ungrown)" % backup)
    elif not pristine:
        print("\n    re-tune over an existing install - NO snapshot minted "
              "(the current file is this script's own output, not a pre-patch state)")
    else:
        print("\n    snapshot already exists - left alone: %s" % backup)

    # grow `.nmg` FIRST, so the relocated DFM has file bytes to be written into
    if not grown:
        d += b"\0" * (nmg["raw"] + NMG_SZ_OURS - len(d))
    assert len(d) == nmg["raw"] + NMG_SZ_OURS
    struct.pack_into("<I", d, nmg["hdr"] + 8, NMG_SZ_OURS)              # VirtualSize
    struct.pack_into("<I", d, nmg["hdr"] + 16, NMG_SZ_OURS)             # SizeOfRawData
    struct.pack_into("<I", d, F["opt"] + 56, SIZEOFIMAGE_OURS)

    d[cave_off:cave_off + CAVE_LEN] = cave
    # the zone the DFM grows into must be zero or our own previous copy -- never anything
    # else, and never silently overwritten
    zone = bytes(d[new_off:new_off + len(new_dfm)])
    assert not any(zone) or zone == new_dfm or zone[:4] == b"TPF0", \
        "the relocated-DFM zone at %#010x is neither blank nor our own output" % DFM_NEW_VA
    d[new_off + len(new_dfm):] = b"\0" * (len(d) - new_off - len(new_dfm))
    d[new_off:new_off + len(new_dfm)] = new_dfm
    assert not any(d[new_off + len(new_dfm):]), \
        "the .nmg slack above the relocated DFM is not zero"
    struct.pack_into("<II", d, entry_off, DFM_NEW_VA - F["imagebase"], len(new_dfm))
    for s in st:
        d[s["off"]:s["off"] + 5] = s["patched"]
    for f in dfm:
        d[f["off"]] = f["ours"] & 0xFF
    write(path, d)

    print("[%s] %s: %d B cave at %#010x, 3 calls retargeted, 16 DFM bytes re-pitched."
          % (EXE, "REPAIRED" if damaged else "APPLIED", used, CAVE_VA))
    print("     RCDATA/%s %d B -> %d B, relocated to VA %#010x (rva %#x); .nmg %#x -> %#x, "
          "SizeOfImage %#x -> %#x, file %d -> %d bytes."
          % (DFM_RES_NAME, DFM_LEN, len(new_dfm), DFM_NEW_VA, DFM_NEW_VA - F["imagebase"],
             NMG_RSZ_ORIG, NMG_SZ_OURS, SIZEOFIMAGE_ORIG, SIZEOFIMAGE_OURS, orig_len, len(d)))
    print("     !!!! NOW RUN: python build_scripts/build_zigeditor.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
