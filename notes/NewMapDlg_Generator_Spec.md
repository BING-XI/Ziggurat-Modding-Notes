# New map dialog -> Ziggurat Map Generator — RE spec

Status: **SPECULATIVE** (analysed, nothing applied). Target: `AoWDevEd.exe` only.
Goal: the existing New map dialog offers "Blank map" vs "Generated map"; the second
runs `Zig Modding Tools\zig_mapgen.py` and opens the result.

## Verified addresses

| what | value |
|---|---|
| `TNewMapDlg` VMT | `0x004031D0` |
| InstanceSize (VMT−0x1C) | **552 = 0x228** |
| FieldTable (VMT−0x2C) | `0x00403250`, 19 entries |
| MethodTable (VMT−0x28) | `0x00403382`, 1 entry |
| class-name shortstring | file `0x2795` (immediately after the method table — neither can grow in place) |
| `OKBtnClick` | `0x004034E4` — a 5-byte thunk: `call 0x4033F0; ret` |
| real OK body | `0x004033F0` |
| DFM | file `0xCE7D4`, 2043 bytes, inside `.rsrc` |

Form fields used by the vanilla OK body, and the `Checked` byte offset:

    [self+0x200] LargeRB   [self+0x204] MediumRB   [self+0x208] SmallRB
    [self+0x218] OneLevel  [self+0x21C] TwoLevels
    TRadioButton.Checked = instance +0x11D  (byte)
    sizes 0x30 / 0x40 / 0x60 / 0x7F   (48 / 64 / 96 / 127 — note 127, not 128)

Map open/save, from `TMainForm.OpenBtnClick` @ `0x00429820`:

    0x004296D4   load map by filename.  eax = TMainForm, edx = AnsiString path
    0x00402E58   HSMEdit.THSMEdit.Close  (eax = [MainForm+0x22C]); al=0 => user cancelled
    0x00402E48   HSMEdit.THSMEdit.Save
    [MainForm+0x22C] THSMEdit instance
    [THSMEdit+0x1E4] current map FILENAME -- proven at 0x0042DFE1, which calls
                     SysUtils.ExtractFileExt on it. (+0x1DC, an earlier guess, is wrong.)

**`[[0x0042F0A8]]` = the TMainForm instance** (global; read at `0x0042DFE1`). The cave runs
as a `TNewMapDlg` method, so this is how it reaches the main form to load the map.

## Everything the cave calls is already imported, with a ready-made thunk

    00401A90  StdCtrls.TCustomComboBox.GetItemIndex   eax = combo   -> index in eax
    00401AA0  StdCtrls.TCustomComboBox.SetItems
    00401560  Controls.TControl.GetText
    004016D8  Controls.TWinControl.GetHandle
    00401468  user32!SendMessageA        (jmp [00432248])
    00401158  kernel32!GetModuleFileNameA
    004017E0  SysUtils.ExtractFilePath
    00401008  System.ParamStr
    00401aa8  StdCtrls.TCustomCheckBox.GetChecked
    Sleep IAT slot 004322A0

So there is **no shellcode**: no kernel32 base walk, no GetProcAddress, no export parsing.

⚠ The game directory must be derived at runtime -- `GetModuleFileNameA(0, buf, MAX_PATH)`
then scan back to the last `\` -- and never baked into the binary
([[aow1-no-machine-specific-paths]], and `build_dlgdirs.py` is the patch that got this wrong).

### Reaching WinExec

AoWDevEd's own IAT has no process API. vclx30.dpl has `WinExec`, and AoWDevEd imports
`checklst.TCheckListBox.GetChecked` from it, whose vclx30 export RVA is `0x00019604`:

    vclx30_base = [0x004332E4] - 0x00019604
    WinExec     = [vclx30_base + 0x000243F8]

Three instructions, no new imports (the rebase-delta idiom from
[[aow1-party-random-generator]]). `GetProcAddress` is at vclx30 IAT RVA `0x00024418` if a
richer launch API is ever wanted.

### TComboBox class VMT

A new class-table entry points at the **existing** IAT slot `0x00432640`
(`StdCtrls..TComboBox@9F046888`). No import surgery.

## The hook is free

`OKBtnClick` is a thunk, so the patch is a **call-retarget** ([[aow1-call-retarget-thunk]]):
rewrite the rel32 at `0x004034E5` to reach the cave. Four bytes, nothing displaced, no
`.reloc` exposure, trivial `--undo`. The cave falls through to `0x004033F0` for a blank map.

## ⚠ The crux: new controls need a FIELD TABLE entry, not just a DFM entry

A component added to the DFM is created by `TReader`, but its pointer is only stored into
the form instance if the class has a **published field of that name**. The compiled class
cannot grow — so a cave cannot read a new control via `[self+offset]` unless the field
table grows too. That is why this is bigger than the terrain-palette patch, whose new
buttons only ever *reused* existing handlers and never had to be read.

Delphi 3 field table layout, confirmed against the raw bytes:

    <u16 count><u32 classtable_ptr>  then count * { <u32 offset><u16 classindex><shortstring name> }

    raw head: 13 00 | a0334000 | dc010000 0000 06 "Panel1"
                                | e0010000 0100 09 "CancelBtn"
                                | e4010000 0100 05 "OKBtn" ...

19 entries starting at +0x1DC, four bytes apart, ending exactly at 0x228 = InstanceSize.

So adding N controls means: relocate and extend the field table, extend the class table at
`0x004033A0` with any class not already listed, and **bump InstanceSize (VMT−0x1C) by 4N**
so the object is allocated large enough to hold the new slots. Same shape as the method
table relocation in `build_deved_terrainpal.py`, applied to a second table.

## The field table's class references are IAT slots

The `<u16 classindex>` in each field entry indexes a class table at `0x004033A0`
(8 entries), and **every entry points into `.idata`** — they are VMT pointers imported
from the DPLs, not addresses inside the exe:

    [0] slot@004033A2 -> 00432680   [4] slot@004033B2 -> 00432688
    [1] slot@004033A6 -> 0043263C   [5] slot@004033B6 -> 00432634  (TRadioButton)
    [2] slot@004033AA -> 00432C90   [6] slot@004033BA -> 00432654  (TLabel)
    [3] slot@004033AE -> 00432C94   [7] slot@004033BE -> 004332D4

So a control of a class *not* already in this form's table needs a new class-table entry.
That would mean a new import — except that the classes are already imported elsewhere in
the exe for other forms. Confirmed present as package import symbols:

    TComboBox@  TRadioGroup@  TGroupBox@  TEdit@  TRadioButton@  TListBox@   (TSpinEdit@ absent)

A new class-table entry can therefore point at the **existing** IAT slot. No PE import
surgery, no `.idata` growth.

## Widget constraint

**`TTrackBar` is not linked into AoWDevEd** (zero occurrences) — a DFM naming an
unregistered class fails to load the entire form, so sliders are impossible here.
`TScrollBar` exists but would need an `OnChange` handler to show a readout.
Grades therefore go in `TComboBox` dropdowns: already imported, six `Items.Strings` baked
into the DFM, `ItemIndex` read by the cave, and no handler required.

⚠ `TComboBox.ItemIndex`'s instance offset is still UNKNOWN and must be derived before the
cave can read it — unlike `TRadioButton.Checked` at `+0x11D`, which the vanilla OK body
proves. Deriving it from an existing editor form that reads a combo is the next RE step.

`GeneralSheet` has `TabVisible = False`, so `MainPageControl` renders as a plain panel —
a second tab would change the dialog's look. A `TRadioGroup`/`TRadioButton` pair matches
the requested "listed as blank contra generated" better.

## Launch path

AoWDevEd imports no process API: kernel32 gives it only `Sleep`, `GetLastError`,
`CreateFileMappingA`, `CloseHandle`, and there is no shell32 import. `vclx30.dpl` — already
loaded, AoWDevEd imports 5 symbols from it — imports **`WinExec`** and `GetProcAddress`;
a cave reads that IAT slot. No new imports needed (the rebase-delta idiom from
[[aow1-party-random-generator]]).

Handshake: `zig_mapgen.py` writes the absolute path of the map it produced to
`Zig Modding Tools\last_map.txt` (implemented). The cave polls with `Sleep` until the
child exits, reads that file, then calls `0x004296D4`.

## Skeleton coverage

The generator needs a container map of the chosen size and level count. Verified available
at >=55% playable area for every combination:

    48:  1lv 2   2lv 5   3lv 14        96:  1lv 2   2lv 16  3lv 9
    64:  1lv 3   2lv 8   3lv 6        127:  1lv 4   2lv 10  3lv 24

`zig_mapgen.py --levels N` now picks a container with exactly N levels (implemented).

## Order of work

1. DFM rebuild into a new `.nmg` section + repoint the `TNEWMAPDLG` resource entry.
2. Field table relocate/extend + class table extend + InstanceSize bump.
3. Method table relocate/extend — the controls share one published handler, `GenChanged`.
4. Cave: read the radio, blank -> `jmp 0x4033F0`; generated -> build argv, `WinExec`,
   poll, read handshake, `Close`, `0x004296D4`.
5. Retarget the rel32 at `0x004034E5`.

⚠ Must be proved by LAUNCHING THE EDITOR — a form whose DFM or field table is wrong fails
at load, and every static check would still pass.

**BUILT — `build_deved_newmapgen.py`.** This file is the design record; the as-built state,
the three relocated tables, `GenChanged`'s streaming guard, the published-property RTTI check
and the in-game checklist are `08-editor.md` §9.
