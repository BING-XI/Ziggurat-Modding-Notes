#!/usr/bin/env python3
r"""
DEVELOPER -> GAME SETTINGS BECOMES A "Game" TAB INSIDE MAP SETTINGS  (AoWDevEd.exe)

The editor shipped two dialogs over the same map record: `Map Settings`
(`TMapSettingsDlg`, four tabs: General / Settings / Players / Diplomacy) and a separate
`Developer -> Game Settings` (`TGameSettingsDlg`, one tab).  This patch REPARENTS the
second into the first as a FIFTH tab named `Game`, and hides the menu item that used to
open it.

⭐ **The form is reparented, not rebuilt.**  Nothing is moved control-by-control, no DFM
grows, no RCDATA is relocated and no published field table is touched.  `TGameSettingsDlg`
is constructed as a normal, never-shown form owned by the Map Settings dialog; a fresh
`TTabSheet` is inserted into `MainPageControl`; and the game-settings form's `ClientPnl`
gets `Parent := sheet`, `Align := alClient`.  Its `OKBtnClick` is then driven from Map
Settings' own OK, and the form is freed in `TMapSettingsDlg.FormDestroy`.

    target   Ziggurat\AoWDevEd.exe        (then build_zigeditor.py --apply -> AoWzEd.exe)
    cave     0x0058F280 .. 0x0058F3FF     384 B reserved, `.ctp` page slack
    global   0x004E0520                   one dword, `.dlgd` page slack (loader-zeroed)
    roll     none.  This feature draws no random number and inherits none; there is no
             pattern to name.  (`rng_audit.py AoWDevEd.exe --functions` prints SYNC: 0 /
             RAW: 3 site(s) in 1 function -- all three build_party_random.py's -- before
             and after.  `TAoWHSMap.Random` is not imported by this binary at all.)

WHY FOUR CALL-RETARGETS AND NOT AN E9 HOOK
  Every insertion point is already a 5-byte `call rel32` whose callee needs to run anyway,
  so the patch is four rewritten rel32 operands: 4 bytes each, nothing displaced, no
  instruction truncated, no `.reloc` entry disturbed (audited: no type-3 fixup lands in
  any of the four operand windows, in the cave, or at the global).  Each cave body calls
  the displaced original first and then does its own work, so `--undo` is four dwords.

  ⚠ PIC is NOT required and must NOT be built.  `AoWDevEd.exe` is a fixed-base image
  (`ImageBase 0x400000`, DYNAMIC_BASE clear), so absolute operands are correct here.  The
  `call $+5 / pop / sub` anchor belongs to the rebasing `.dpl` packages, not to this exe.

THE FOUR SITES                                            (all VAs, ImageBase 0x400000)
  # site         file      vanilla bytes        original callee          cave
  1 0x004230E8   0x224E8   E8 43 FE FF FF       0x00422F30               cave_build
      last call in `TMapSettingsDlg.FormCreate` before its SEH teardown; EAX = Self
      (`004230E6 mov eax,edi`).  The DFM has streamed, so `MainPageControl` is live.
  2 0x00423730   0x22B30   E8 33 F5 FF FF       0x00422C68               cave_commit
      inside `TMapSettingsDlg.OKBtnClick`, in the VerifyRaces-succeeded branch
      (`test bl,bl / je 0x423777`), EAX = Self (`0042372E mov eax,esi`).  Runs before the
      site's own `THSMap.SetModified` at 0x00423735.
  3 0x0042315F   0x2255F   E8 DC DE FD FF       0x00401040 (TObject.Free) cave_free
      the THIRD `TObject.Free` in `TMapSettingsDlg.FormDestroy`, freeing `[ebx+0x2F8]`;
      EBX = Self.
  4 0x004284B2   0x278B2   E8 91 93 FD FF       0x00401848 (SetVisible)   cave_menu
      `TMainForm.FormCreate`, `DeveloperItems.Visible := True`; EBX = Self, EAX =
      `[ebx+0x358]`, DL = 1.  Unconditional: the `ParamStr(1)` compare at 0x00428471
      branches `jne 0x00428490`, and 0x00428490 is also where the matching path falls
      through, so both reach 0x004284AA.

  Registers on entry are already what the caves want, so no site needs a shim.  Every cave
  preserves EBX/ESI/EDI/EBP per the Delphi register convention; EAX is dead at all four
  return points (`xor eax,eax`, `mov eax,[0x43289c]`, `pop ebx/ret`, `mov eax,[ebx+0x22c]`).

CALL MECHANICS
  * **Constructor ABI: the declared parameter is in ECX, not EDX.**  Delphi's alloc flag
    occupies DL, which pushes `AOwner` one register along.  Copied verbatim from the site
    this feature replaces, `TMainForm.GameSettingsClick @0x0042D3B4`:
        0042D3DC  mov ecx, esi          ; AOwner
        0042D3DE  mov dl, 1             ; alloc flag
        0042D3E0  mov eax, [0x0042D9D8] ; TGameSettingsDlg class ref (-> VMT 0x0042DA18)
        0042D3E5  call 0x00401228       ; Forms.TCustomForm.Create thunk
  * **`TTabSheet` needs a VIRTUAL construction.**  A Delphi package exports a class symbol
    AT the VMT address, so the IAT slot `0x00432C94` (`ComCtrls..TTabSheet`) holds the
    class reference itself -- one indirection, not two.  Read back from vcl30.dpl, that
    address (`0x4135DDE8`) reads as `name='TTabSheet', instsize=0x120`.  `TTabSheet`
    OVERRIDES `Create` (its VMT+0x24 is `ComCtrls.TTabSheet.Create @0x41366B80`, not
    `Forms.TCustomForm.Create @0x41336300`), so the cave dispatches through the slot:
        mov eax,[0x00432C94] ; mov dl,1 ; mov ecx,<AOwner> ; call dword ptr [eax+0x24]
    Create is VMT+0x24 on every Delphi 3 form class here -- `TGameSettingsDlg` (VMT
    0x0042DA18) and `TMapSettingsDlg` (VMT 0x004220E8) both hold the thunk 0x00401228
    there; `TMainForm` (VMT 0x00425D00) holds its own override 0x0042815C.
  * **`ComCtrls.TTabSheet.SetPageControl` is NOT imported by this exe**, and adding an
    import descriptor to a 124-byte `.idata` tail is recorded as fragile.  The IAT-delta
    idiom reaches it with no new import:
        mov ecx, [0x00432210]   ; runtime Forms.TCustomForm.Create
        add ecx, 0x000309C0     ; -> ComCtrls.TTabSheet.SetPageControl
    ⚠ That constant is RECOMPUTED from the live `Ziggurat\vcl30.dpl` export table on every
    run and asserted against the baked value, never trusted blind.  It is stable against
    `build_wheel_vclpump.py`, which retargets one 5-byte call at 0x4133BA6D and appends
    caves in vcl30's CODE zero tail from 0x413A8A00 -- neither export moves.
  * ⚠ `Parent := MainPageControl` is NOT a substitute for `SetPageControl`.  vcl30's
    `TTabSheet` overrides CMTextChanged, Create, CreateParams, Destroy, GetPageIndex,
    GetTabIndex, ReadState, SetPageControl, SetPageIndex, SetTabVisible -- and NOT
    `SetParent`.  `TPageControl.FPages` is only touched by InsertPage/RemovePage, reached
    from `SetPageControl`.  Parent alone yields a panel with no tab.
  * The `Game` caption is set AFTER `SetPageControl`, so the `CMTextChanged` override has
    a page control to repaint.

IMPORTED THUNKS USED (all `jmp dword ptr [iat]`, all verified live)
    Forms.TCustomForm.Create              0x00401228   iat 0x00432210
    System.TObject.Free                   0x00401040   iat 0x0043212C
    Controls.TControl.SetParent           0x00401540   iat 0x004323AC
    Controls.TControl.SetAlign            0x004014E8   iat 0x004323D8
    Controls.TControl.SetVisible          0x00401548   iat 0x004323A8
    Controls.TControl.SetText  (Caption)  0x00401568   iat 0x00432398
    Menus.TMenuItem.SetVisible            0x00401848   iat 0x00432494

FIELD OFFSETS -- read out of the published field tables, not guessed
    TMapSettingsDlg   VMT 0x004220E8  instsize 0x300  fieldtable 0x00422168
        +0x1DC ClientPnl   +0x1E0 MainPageControl   +0x1E4 GeneralSheet
        FormCreate 0x00422FDC   OKBtnClick 0x004236CC   FormDestroy 0x00423140
        private +0x2F4 TPlayerList  +0x2F8 TRaceList  +0x2FC TSonglist
        ⚠ Fields run to 0x300 = instsize, so the class has NO instance slack.  The
          embedded-form pointer therefore has to be a global (`G_GSDLG`), which is sound
          because the dialog is modal and there is only ever one: its sole construction
          site is `0x0042A99C`, inside the guarded opener `0x0042A960`.
    TGameSettingsDlg  VMT 0x0042DA18  instsize 0x238  classref cell 0x0042D9D8
        +0x1DC BottomPnl   +0x1E0 ClientPnl   +0x1EC MainPageControl
        published methods, all three of them: FormCreate 0x0042DE6C,
        OKBtnClick 0x0042DF2C, GameTypeCBChange 0x0042E158.
        ⭐ There is no FormShow and no FormDestroy, so everything the dialog displays is
        seeded in FormCreate -- which is exactly why constructing it without ever showing
        it works.
    TMainForm         VMT 0x00425D00  +0x358 DeveloperItems  +0x544 GameSettingsMI

WHY IT IS SAFE TO CONSTRUCT TGameSettingsDlg HERE
  `TGameSettingsDlg.FormCreate @0x0042DE6C` dereferences the map at `[[0x0043289C]]`
  unguarded (`mov esi,[0x43289c] / mov eax,[esi] / mov dl,[eax+0x11A]`).  The opener this
  patch replaces guards that itself (`0x0042D3B9 cmp dword ptr [eax],0 / je`).  Map
  Settings carries the SAME guard, and it is the only way in:
      0042A976  cmp byte ptr [esi+0x1BC], 0   ; a document is open
      0042A983  mov eax,[0x0043289C] / cmp dword ptr [eax],0 / je 0x42AA08
  so by the time `TMapSettingsDlg.FormCreate` runs, a map is guaranteed non-nil.

LIFETIME -- correct in both directions
  `Forms.TCustomForm.Destroy @0x4133659C` fires `OnDestroy` at 0x4133661C (gated on the
  Assigned test at 0x413365FE) and only reaches `inherited Destroy` at 0x413366A7.  So
  `TMapSettingsDlg.FormDestroy` -- and therefore `cave_free` -- runs long before any child
  control is torn down.  That ordering is load-bearing: `Controls.TWinControl.Destroy
  @0x4134316C` destroys every child control regardless of ownership (loop
  0x413431A5..0x413431CC), and freeing the embedded form first means that loop never sees
  `ClientPnl`.  Freeing the form also runs `TComponent.DestroyComponents`, which takes
  `ClientPnl` (still an owned component of the embedded form, merely re-parented) out of
  the tab sheet's control list.  The sheet itself is owned by Map Settings and dies with it.

TGameSettingsDlg.OKBtnClick IS CALLED WHOLE (0x0042DF2C), NOT REPLICATED
  ⚠ "call it but stop before the field-write block ends" is impossible: the routine
  installs an SEH frame at 0x0042DF3E..0x0042DF47 that is only torn down at 0x0042E108.
  Read end to end it is also safe to call from a non-modal context -- it never touches
  ModalResult, never calls Close/Hide, never reads its own window handle or Application:
    0x0042DF4A..0x0042DFDD  writes the eight settings into `[[0x0043289C]]+0x18C` etc.
    0x0042DFDE              ExtractFileExt([[0x0042F0A8]]+0x22C -> +0x1E4)
    0x0042DFF9..0x0042E034  CompareText vs '.csm' (0x0042E134) then '.hsm' (0x0042E144);
                            neither matches -> jne 0x0042E101, straight to SetModified
    0x0042E03A..0x0042E0FC  on a match: LStrPos('.'), copy the head into map[+0x7C],
                            GameTypeCB.ItemIndex -> map[+0x11A], re-append the extension,
                            THSMEdit.SetHSMapFilename
    0x0042E101              THSMap.SetModified
  Idempotent when Game Type is unchanged, because `TGameSettingsDlg.FormCreate` seeds
  `GameTypeCB.ItemIndex := map[+0x11A]` first thing (0x0042DE7A..0x0042DE86).
  Note `map[+0x11A]` is written INSIDE the extension guard, so for a never-saved map whose
  extension is neither `.csm` nor `.hsm` the Game Type is silently not committed.  Vanilla
  behaviour, deliberately unchanged.

⚠ INHERITED VANILLA DEFECT, NEWLY REACHABLE -- NOT FIXED HERE
  0x0042E052 uses `System.@LStrPos` (FIRST '.'), not a last-delimiter scan, so a map whose
  PATH contains a dot is truncated: `...\maps\v1.2\foo.hsm` -> `...\maps\v1.hsm`.
  MEASURED, answering the open question: `[THSMEdit+0x1E4]` holds a **full path**, not a
  bare filename.  `THSMEdit.LoadHSM @0x556150E4` assigns `[ebx+0x1E4] := edx` straight from
  its argument, and the exe hands it `TOpenDialog.FileName` verbatim
  (`TMainForm.OpenBtnClick 0x0042986...` -> 0x004296D4 -> LoadHSM);  `THSMEdit.SaveAs
  @0x55614E6D` likewise stores the save dialog's returned FileName.  Only a never-saved
  document holds a bare name (`noname.hsm`, the literal `THSMEdit.Save @0x55614EE3`
  compares against).  So the defect is reachable whenever any directory in the map's path
  contains a dot.  It fires today on Developer -> Game Settings OK; after this patch it
  also fires on every Map Settings OK.  Pre-existing, out of scope, recorded in
  `Zig notes/08-editor.md`.

CAVE ALLOCATION -- no new section, no section header touched, file length unchanged
  `.ctp`  VA 0x0052E000  file 0x00128E00  VirtualSize = SizeOfRawData = 0x61400
      last non-zero byte file 0x18A079 = VA 0x0058F279 (end of build_deved_heroprune.py)
      0x0058F27A..0x0058F27F   6 bytes, left alone (heroprune's alignment tail)
      0x0058F280..0x0058F3FF   384 B, verified all-zero      <<< this patch >>>
  Section characteristics 0x60000020 = CODE|EXECUTE|READ -- **read-only at runtime**, which
  is why the one mutable dword cannot live here.
  `.dlgd` VA 0x004E0000  SizeOfRawData 0x400  VirtualSize 0x520  chars 0xE0000060 (R/W/X)
      G_GSDLG = 0x004E0520, four bytes.  ⚠⚠ It is past SizeOfRawData AND one byte past
      VirtualSize, so it has NO FILE OFFSET: naive `raw + (rva - va)` arithmetic yields
      0xDC720, which is inside `.mtb`'s raw data.  `va2off()` below is therefore bounded by
      `rsz`, never `max(vsz, rsz)`, and REFUSES this address -- asserted by construction.
      The loader still commits the whole page (the section owns 0x004E0000..0x004E0FFF
      outright, `.mtb` starts at 0x004E1000) and zero-fills everything past the raw data,
      so the dword starts at 0 and `--undo` has nothing to zero there.

⚠ FORWARD HAZARDS
  * `.ctp` tenancy is now FOUR scripts and the apply order is
        build_deved_terrainpal.py -> build_deved_toolbar_trim.py
          -> build_deved_heroprune.py -> build_deved_gamesettings_tab.py
    ⚠⚠ `build_deved_heroprune.py` zeroes `.ctp`'s whole tail out to file 0x18A200
    (`zero_to = ctp_raw + ctp_rsz`) on BOTH `--undo` AND `--apply`.  --apply over an
    already-applied file prints "rebuilding IN PLACE (strip, then lay down again)" and
    calls the same strip() first, so this is NOT an --undo-only hazard.  Either will
    DESTROY this cave without saying so -- and heroprune's own "the .ctp tail is not all
    zero" guard then PASSES, because strip() just erased the evidence.  Symptom: four
    call rel32 sites pointing at zeroed memory, one inside TMainForm.FormCreate, so
    AoWzEd.exe AVs at STARTUP.  Re-run this script, then build_zigeditor.py --apply,
    behind either operation.  Deleting `.ctp`
    to re-run `build_deved_terrainpal.py` destroys all three later scripts the same way.
    heroprune had 390 spare tail bytes; this claims 384 of them, leaving it no growth room.
  * `build_dlgdirs.py` and this script are ADJACENT in `.dlgd` page slack: dlgdirs owns
    PATHBUF 0x004E0400..0x004E051F, this owns 0x004E0520..0x004E0523.  No overlap **today**
    only because AoWDevEd.exe's entry in that script has `engfb=None`.  ⚠ Its v3 DIRBUF
    constant is `DIRBUF_OFF = PATHBUF_OFF + PATHBUF_SIZE = 0x520` -- giving AoWDevEd.exe an
    `engfb` entry would put DIRBUF's StrRec exactly on top of G_GSDLG.  If that ever
    happens, move G_GSDLG to 0x004E0630 or later (slack runs to 0x004E0FFF).
  * No other script references 0x0042841C, 0x00422FDC, 0x004236CC, 0x00423140, 0x0042D3B4,
    0x0042DF2C, 0x0042DE6C, 0x0042DD14, 0x00432C94 or 0x004323AC.
  * `build_deved_toolbar_trim.py` already removed `MBGameSettings` from the live toolbar
    (the string survives only at file 0x1262D8, inside the dead `.mtb` DFM), so hiding the
    menu item is the whole of the entry-point removal -- there is no second way in.

⚠⚠ AFTER --apply YOU MUST RUN `build_zigeditor.py --apply`
  This patches `AoWDevEd.exe`, the editor patch SOURCE.  The editor the owner runs is
  `AoWzEd.exe`, derived from it.  Skipping the rebuild leaves the patch verifying clean
  against a binary nobody launches.  `AoWzEd.exe` is not a byte copy (~4.4 KB of `.rsrc`
  icon differs), so compare the hook sites and the cave region, never the file hash.

USAGE
    python build_scripts/build_deved_gamesettings_tab.py            # dry run + verify
    python build_scripts/build_deved_gamesettings_tab.py --dis      # + disassemble the cave
    python build_scripts/build_deved_gamesettings_tab.py --apply    # write
    python build_scripts/build_deved_gamesettings_tab.py --undo     # surgical revert

Needs `pip install keystone-engine capstone`.
"""
import os
import shutil
import struct
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
# <game>/Ziggurat/Modding Resources/build_scripts/ -> two levels up is <game>/Ziggurat
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
RE_TOOLS = os.path.join(GAME, "Modding Resources", "re_tools")

EXE = "AoWDevEd.exe"
VCL = "vcl30.dpl"
IMAGE_BASE = 0x400000

BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP_SUFFIX = ".pre-gstab"

# ---- cave + global -----------------------------------------------------------------
CAVE_VA = 0x0058F280
CAVE_END = 0x0058F400                 # exclusive reservation, 384 B
CAVE_LEN = CAVE_END - CAVE_VA
G_GSDLG = 0x004E0520                  # `.dlgd` page slack; NO file offset (see docstring)

DLGD_VA = 0x004E0000
DLGD_RAWSIZE = 0x400

# ---- the four retarget sites -------------------------------------------------------
#   (name, site VA, vanilla 5 bytes, original callee VA)
SITES = [
    ("cave_build",  0x004230E8, bytes.fromhex("E843FEFFFF"), 0x00422F30),
    ("cave_commit", 0x00423730, bytes.fromhex("E833F5FFFF"), 0x00422C68),
    ("cave_free",   0x0042315F, bytes.fromhex("E8DCDEFDFF"), 0x00401040),
    ("cave_menu",   0x004284B2, bytes.fromhex("E89193FDFF"), 0x00401848),
]

# ---- imported thunks (jmp dword ptr [iat]) -----------------------------------------
T_FORM_CREATE = 0x00401228            # Forms.TCustomForm.Create
T_FREE = 0x00401040                   # System.TObject.Free
T_SETPARENT = 0x00401540              # Controls.TControl.SetParent
T_SETALIGN = 0x004014E8               # Controls.TControl.SetAlign
T_SETVISIBLE = 0x00401548             # Controls.TControl.SetVisible
T_SETTEXT = 0x00401568                # Controls.TControl.SetText  (Caption setter)
T_MENUVISIBLE = 0x00401848            # Menus.TMenuItem.SetVisible

IAT_FORM_CREATE = 0x00432210          # runtime address of Forms.TCustomForm.Create
IAT_TABSHEET = 0x00432C94             # holds the ComCtrls..TTabSheet CLASS REF itself

# thunk VA -> the IAT slot it must jump through, asserted before writing
THUNK_IAT = {
    T_FORM_CREATE: 0x00432210, T_FREE: 0x0043212C, T_SETPARENT: 0x004323AC,
    T_SETALIGN: 0x004323D8, T_SETVISIBLE: 0x004323A8, T_SETTEXT: 0x00432398,
    T_MENUVISIBLE: 0x00432494,
}

CLASSREF_GSDLG = 0x0042D9D8           # static cell holding TGameSettingsDlg's VMT
VMT_GSDLG = 0x0042DA18
VMT_CREATE_SLOT = 0x24                # Delphi 3 virtual constructor
GS_OKBTNCLICK = 0x0042DF2C
GS_FORMCREATE = 0x0042DE6C            # re-seed every control from the map; see RESEED below

# field offsets, from the published field tables
MS_MAINPAGECONTROL = 0x1E0            # TMapSettingsDlg.MainPageControl
GS_BOTTOMPNL = 0x1DC                  # TGameSettingsDlg.BottomPnl
GS_CLIENTPNL = 0x1E0                  # TGameSettingsDlg.ClientPnl
MF_GAMESETTINGSMI = 0x544             # TMainForm.GameSettingsMI

AL_CLIENT = 5                         # TAlign: alNone,alTop,alBottom,alLeft,alRight,alClient

TAB_CAPTION = b"Game"

# ComCtrls.TTabSheet.SetPageControl - Forms.TCustomForm.Create, both in vcl30.dpl.
# RECOMPUTED from the live export table on every run and asserted against this value.
VCL_DELTA_SETPAGECONTROL = 0x000309C0


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
                imagebase=struct.unpack_from("<I", d, opt + 28)[0])


def va2off(F, va):
    """VA -> file offset, RESTRICTED TO EACH SECTION'S RAW DATA.

    !! The usual `max(vsz, rsz)` form would happily map an address in a section's page
    slack -- e.g. G_GSDLG at 0x004E0520, past `.dlgd`'s 0x400 raw bytes -- onto the NEXT
    section's raw data (0xDC720, inside `.mtb`).  Refuse instead.
    """
    rva = va - F["imagebase"]
    for s in F["secs"]:
        if s["va"] <= rva < s["va"] + s["rsz"]:
            return s["raw"] + (rva - s["va"])
    raise ValueError("VA %#x has no raw file bytes" % va)


def count_import_descriptors(d, F):
    idir = struct.unpack_from("<I", d, F["opt"] + 104)[0]
    o = va2off(F, F["imagebase"] + idir)
    n = 0
    while any(d[o + n * 20:o + n * 20 + 20]):
        n += 1
    return n


# ====================================================================================
# vcl30 export delta -- recomputed, never trusted blind
# ====================================================================================
def vcl_delta():
    sys.path.insert(0, RE_TOOLS)
    from aowsyms import get_symbols
    _pe, _base, exp, _iat = get_symbols(VCL)
    inv = {}
    for va, name in exp.items():
        inv.setdefault(name, va)
    try:
        create = inv["Forms.TCustomForm.Create"]
        setpc = inv["ComCtrls.TTabSheet.SetPageControl"]
    except KeyError as ex:
        raise SystemExit("vcl30.dpl does not export %s - cannot compute the delta" % ex)
    return setpc - create, create, setpc


# ====================================================================================
# the cave
# ====================================================================================
def cave_source(lit_va, delta):
    """Four independent bodies, in the order the SITES table retargets them."""
    build = f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax                                   /* ebx = TMapSettingsDlg */
        call {SITES[0][3]:#x}                           /* the displaced original */

        /* gs := TGameSettingsDlg.Create(MapSettingsDlg)  -- AOwner is in ECX */
        mov  ecx, ebx
        mov  dl, 1
        mov  eax, dword ptr [{CLASSREF_GSDLG:#x}]
        call {T_FORM_CREATE:#x}
        mov  esi, eax
        mov  dword ptr [{G_GSDLG:#x}], esi

        /* sheet := TTabSheet.Create(MapSettingsDlg)  -- virtual, TTabSheet overrides it */
        mov  ecx, ebx
        mov  dl, 1
        mov  eax, dword ptr [{IAT_TABSHEET:#x}]
        call dword ptr [eax + {VMT_CREATE_SLOT:#x}]
        mov  edi, eax

        /* sheet.PageControl := MapSettingsDlg.MainPageControl  (IAT-delta, not imported) */
        mov  ecx, dword ptr [{IAT_FORM_CREATE:#x}]
        add  ecx, {delta:#x}
        mov  eax, edi
        mov  edx, dword ptr [ebx + {MS_MAINPAGECONTROL:#x}]
        call ecx

        /* sheet.Caption := 'Game'  -- AFTER SetPageControl, so CMTextChanged has a host */
        mov  eax, edi
        mov  edx, {lit_va:#x}
        call {T_SETTEXT:#x}

        /* gs.BottomPnl.Visible := False */
        mov  eax, dword ptr [esi + {GS_BOTTOMPNL:#x}]
        xor  edx, edx
        call {T_SETVISIBLE:#x}

        /* gs.ClientPnl.Parent := sheet */
        mov  eax, dword ptr [esi + {GS_CLIENTPNL:#x}]
        mov  edx, edi
        call {T_SETPARENT:#x}

        /* gs.ClientPnl.Align := alClient */
        mov  eax, dword ptr [esi + {GS_CLIENTPNL:#x}]
        mov  dl, {AL_CLIENT:#x}
        call {T_SETALIGN:#x}

        /* RESEED.  gs.FormCreate ran inside Create, BEFORE the reparent above.
           SetParent destroys and recreates the child window handles, and Delphi 3's
           TCustomComboBox keeps ItemIndex in the WINDOW (CB_SETCURSEL), not in a field
           -- DestroyWnd saves Items but not the selection, so GameTypeCB came back
           blank while every TSpin and TCheckBox kept its value (they store state in
           fields).  Confirmed in-game 2026-09-12: five tabs, all values right, Game
           Type empty.  Re-running FormCreate re-seeds all eight controls from the map
           and re-runs the enable/disable pass; it only reads map fields and writes
           controls, so it is idempotent. */
        mov  eax, esi
        call {GS_FORMCREATE:#x}

        pop  edi
        pop  esi
        pop  ebx
        ret
"""
    commit = f"""
        call {SITES[1][3]:#x}                           /* the displaced original */
        mov  eax, dword ptr [{G_GSDLG:#x}]
        test eax, eax
        jz   cc_skip
        xor  edx, edx                                   /* Sender - OKBtnClick never reads it */
        call {GS_OKBTNCLICK:#x}
    cc_skip:
        ret
"""
    free = f"""
        call {SITES[2][3]:#x}                           /* the displaced original Free */
        mov  eax, dword ptr [{G_GSDLG:#x}]
        test eax, eax
        jz   cf_skip
        call {T_FREE:#x}
    cf_skip:
        xor  eax, eax
        mov  dword ptr [{G_GSDLG:#x}], eax
        ret
"""
    menu = f"""
        call {SITES[3][3]:#x}                           /* DeveloperItems.Visible := True */
        mov  eax, dword ptr [ebx + {MF_GAMESETTINGSMI:#x}]
        xor  edx, edx
        call {T_MENUVISIBLE:#x}                         /* GameSettingsMI.Visible := False */
        ret
"""
    return [build, commit, free, menu]


def literal_blob():
    """Delphi 3 immutable AnsiString: refcount -1, length, chars, NUL, 4-byte aligned.
    Same shape as the shipped '.csm' at 0x0042E134.  EDX gets the address of the CHARS."""
    body = struct.pack("<iI", -1, len(TAB_CAPTION)) + TAB_CAPTION + b"\0"
    while len(body) % 4:
        body += b"\0"
    return body, 8                                      # blob, offset of the chars


def assemble(ks, delta):
    """Two-pass: the 'Game' literal sits after the code, and cave_build needs its address.
    `mov edx, imm32` has no short form, so pass 2 cannot change any length -- asserted."""
    lit_blob, lit_chars_off = literal_blob()

    def pass_(lit_va):
        entries, blobs, va = [], [], CAVE_VA
        for src in cave_source(lit_va, delta):
            enc, _ = ks.asm(src, va)
            enc = bytes(enc)
            entries.append(va)
            blobs.append(enc)
            va += len(enc)
        return entries, blobs

    entries, blobs = pass_(0x11111111)
    code_len = sum(len(b) for b in blobs)
    pad = (-code_len) % 4
    lit_va = CAVE_VA + code_len + pad + lit_chars_off
    entries2, blobs2 = pass_(lit_va)
    assert [len(b) for b in blobs] == [len(b) for b in blobs2], \
        "literal address changed an instruction length - two-pass did not converge"
    assert entries == entries2
    cave = b"".join(blobs2) + b"\0" * pad + lit_blob
    return cave, entries2, code_len, CAVE_VA + code_len + pad, lit_va


def disassemble(cave, entries, code_len, lit_off_va, lit_va):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    labels = {va: name for va, (name, _s, _o, _c) in zip(entries, SITES)}
    code = cave[:code_len]
    seen = 0
    for i in cs.disasm(code, CAVE_VA):
        mark = "    <<< %s" % labels[i.address] if i.address in labels else ""
        print("  %08X  %-22s %-7s %s%s"
              % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str, mark))
        seen += i.size
    if seen != len(code):
        print("  !! capstone stopped after %d of %d code bytes - TRUNCATED INSTRUCTION"
              % (seen, len(code)))
    pad = lit_off_va - CAVE_VA - code_len
    if pad:
        print("  %08X  %s%s; %d alignment byte(s)"
              % (CAVE_VA + code_len, cave[code_len:code_len + pad].hex(" "),
                 " " * (24 - 3 * pad), pad))
    blob = cave[lit_off_va - CAVE_VA:]
    print("  %08X  %s   ; AnsiString literal, chars at %#010x = %r"
          % (lit_off_va, blob.hex(" "), lit_va, TAB_CAPTION.decode()))
    return seen == len(code)


def check_cave(cave, entries, code_len, lit_off_va, delta):
    """Read the emitted bytes back rather than trusting the assembler (keystone's imm8
    trap: `push 0xFFFF` silently becomes `6A FF`)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    code = cave[:code_len]
    ins = list(cs.disasm(code, CAVE_VA))
    assert sum(i.size for i in ins) == len(code), "cave does not disassemble end to end"
    want = {"ret": 4, "call dword ptr [eax + 0x24]": 1}
    got_ret = sum(1 for i in ins if i.mnemonic == "ret")
    assert got_ret == want["ret"], "expected 4 rets, got %d" % got_ret
    assert any(i.mnemonic == "call" and i.op_str == "dword ptr [eax + 0x24]" for i in ins), \
        "the virtual TTabSheet.Create dispatch is missing"
    add = [i for i in ins if i.mnemonic == "add" and i.op_str.startswith("ecx,")]
    assert len(add) == 1 and int(add[0].op_str.split(",")[1], 16) == delta, \
        "add ecx, <vcl delta> did not encode %#x: %r" % (delta, [i.op_str for i in add])
    # every rel32 call must land on a real target, never inside our own cave by accident
    for i in ins:
        if i.mnemonic == "call" and i.op_str.startswith("0x"):
            t = int(i.op_str, 16)
            assert not (CAVE_VA <= t < CAVE_END), \
                "call at %#x targets our own cave (%#x)" % (i.address, t)
    # literal shape
    blob = cave[lit_off_va - CAVE_VA:]
    assert blob[:8] == struct.pack("<iI", -1, len(TAB_CAPTION)), \
        "literal header is not FF FF FF FF <len>: %s" % blob[:8].hex()
    assert blob[8:8 + len(TAB_CAPTION)] == TAB_CAPTION and blob[8 + len(TAB_CAPTION)] == 0
    assert len(cave) <= CAVE_LEN, \
        "cave is %d B, reservation is %d B" % (len(cave), CAVE_LEN)


# ====================================================================================
# state
# ====================================================================================
def read_state(d, F, entries):
    st = []
    for (name, site, orig, _callee), cave_va in zip(SITES, entries):
        off = va2off(F, site)
        now = bytes(d[off:off + 5])
        patched = b"\xE8" + struct.pack("<i", cave_va - (site + 5))
        # "ours" = the operand lands anywhere INSIDE our exclusive reservation, not just
        # at this build's entry point.  Re-tuning a cave shifts every entry point after
        # the edit, and the project rule is an in-place rewrite, never revert-and-reapply
        # (CLAUDE.md, "Re-tuning is an in-place cave rewrite").  Keying on the range lets
        # --apply overwrite a PREVIOUS build of this same feature, while still rejecting a
        # genuinely foreign call.  Safe because 0x0058F280..0x0058F3FF is exclusively ours.
        ours = False
        if now[:1] == b"\xE8":
            tgt = site + 5 + struct.unpack("<i", now[1:5])[0]
            ours = CAVE_VA <= tgt < CAVE_VA + CAVE_LEN
        st.append(dict(name=name, site=site, off=off, now=now, orig=orig,
                       patched=patched, is_orig=now == orig, is_ours=ours,
                       is_current=now == patched))
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true",
                    help="surgical revert: restore the four calls, zero the cave")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the cave")
    args = ap.parse_args()
    if args.apply and args.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    # --- the vcl30 delta, recomputed ------------------------------------------------
    delta, vcl_create, vcl_setpc = vcl_delta()
    print("[vcl30.dpl] Forms.TCustomForm.Create %#010x  "
          "ComCtrls.TTabSheet.SetPageControl %#010x" % (vcl_create, vcl_setpc))
    print("            delta %#x  (baked %#x)  %s"
          % (delta, VCL_DELTA_SETPAGECONTROL,
             "MATCH" if delta == VCL_DELTA_SETPAGECONTROL else "*** MISMATCH ***"))
    assert delta == VCL_DELTA_SETPAGECONTROL, (
        "vcl30.dpl moved: SetPageControl - Create is %#x, this script bakes %#x. "
        "Re-derive before applying." % (delta, VCL_DELTA_SETPAGECONTROL))

    cave, entries, code_len, lit_off_va, lit_va = assemble(ks, delta)
    check_cave(cave, entries, code_len, lit_off_va, delta)

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    orig_len = len(d)
    F = load_sections(d)

    # --- allocation sanity ----------------------------------------------------------
    ctp = next(s for s in F["secs"] if s["name"] == b".ctp")
    assert ctp["chars"] == 0x60000020, ".ctp characteristics changed: %#x" % ctp["chars"]
    assert CAVE_VA - F["imagebase"] >= ctp["va"], "cave is below .ctp"
    assert CAVE_END - F["imagebase"] <= ctp["va"] + ctp["rsz"], \
        "cave runs past .ctp's raw data"
    dlgd = next(s for s in F["secs"] if s["name"] == b".dlgd")
    assert dlgd["chars"] & 0x80000000, ".dlgd is not writable: %#x" % dlgd["chars"]
    assert F["imagebase"] + dlgd["va"] == DLGD_VA, ".dlgd moved to %#x" % dlgd["va"]
    assert dlgd["rsz"] == DLGD_RAWSIZE, ".dlgd SizeOfRawData is %#x, not %#x" % (
        dlgd["rsz"], DLGD_RAWSIZE)
    assert G_GSDLG - DLGD_VA >= dlgd["rsz"], "G_GSDLG is inside .dlgd's raw data"
    assert G_GSDLG + 4 <= DLGD_VA + 0x1000, "G_GSDLG is past .dlgd's page"

    # --- thunks + class refs still where the docstring says -------------------------
    for thunk, iat in sorted(THUNK_IAT.items()):
        o = va2off(F, thunk)
        assert d[o] == 0xFF and d[o + 1] == 0x25 and \
            struct.unpack_from("<I", d, o + 2)[0] == iat, \
            "thunk %#x no longer jumps through %#x: %s" % (thunk, iat, bytes(d[o:o + 6]).hex())
    assert struct.unpack_from("<I", d, va2off(F, CLASSREF_GSDLG))[0] == VMT_GSDLG, \
        "TGameSettingsDlg class ref cell %#x no longer holds %#x" % (CLASSREF_GSDLG, VMT_GSDLG)

    cave_off = va2off(F, CAVE_VA)
    cave_now = bytes(d[cave_off:cave_off + CAVE_LEN])
    st = read_state(d, F, entries)
    n_orig = sum(1 for s in st if s["is_orig"])
    n_ours = sum(1 for s in st if s["is_ours"])
    cave_installed = cave_now.startswith(cave) and not any(cave_now[len(cave):])
    cave_blank = not any(cave_now)

    print("\n[%s] %d bytes   cave %#010x..%#010x  file %#08x"
          % (EXE, orig_len, CAVE_VA, CAVE_END - 1, cave_off))
    print("     emitted %d B of %d reserved (%d spare); literal '%s' chars @ %#010x"
          % (len(cave), CAVE_LEN, CAVE_LEN - len(cave), TAB_CAPTION.decode(), lit_va))
    for s, cv in zip(st, entries):
        tag = "VANILLA" if s["is_orig"] else ("OURS" if s["is_ours"] else "*** FOREIGN ***")
        print("     %-11s %#010x  %s -> %s  [%s]  cave %#010x"
              % (s["name"], s["site"], s["now"].hex(), s["patched"].hex(), tag, cv))
    print("     cave region: %s"
          % ("blank" if cave_blank else
             ("installed, current" if cave_installed else
              "non-zero and NOT our current build (%d non-zero bytes)"
              % sum(1 for b in cave_now if b))))

    if args.dis:
        print("\n---- cave disassembly ----")
        disassemble(cave, entries, code_len, lit_off_va, lit_va)

    # ================================ undo =========================================
    if args.undo:
        if n_orig == 4 and cave_blank:
            print("\n[%s] already vanilla at all four sites and the cave is blank - no-op" % EXE)
            return 0
        for s in st:
            assert s["is_orig"] or s["is_ours"], \
                "%s @ %#x is neither vanilla nor ours (%s) - refusing to undo" \
                % (s["name"], s["site"], s["now"].hex())
        for s in st:
            d[s["off"]:s["off"] + 5] = s["orig"]
        cleared = sum(1 for b in cave_now if b)
        d[cave_off:cave_off + CAVE_LEN] = b"\0" * CAVE_LEN
        assert len(d) == orig_len
        write(path, d)
        print("\n[%s] UNDONE: four calls restored, %d non-zero cave bytes cleared in "
              "%#010x..%#010x.  No backup touched, no section header changed."
              % (EXE, cleared, CAVE_VA, CAVE_END - 1))
        print("     G_GSDLG %#010x is loader-zeroed page slack - nothing on disk to clear."
              % G_GSDLG)
        print("     !! Re-run `build_zigeditor.py --apply` so AoWzEd.exe follows.")
        return 0

    # ============================== verify / apply ==================================
    if n_orig == 4 and cave_installed:
        pass                                            # fresh install, everything vanilla
    elif n_ours == 4 and cave_installed:
        print("\n[%s] already patched and up to date - no-op" % EXE)
        return 0
    for s in st:
        assert s["is_orig"] or s["is_ours"], (
            "%s @ %#x is neither vanilla (%s) nor ours (%s): %s - ABORT"
            % (s["name"], s["site"], s["orig"].hex(), s["patched"].hex(), s["now"].hex()))
    assert cave_blank or cave_now.startswith(cave) or n_ours, (
        "the cave holds bytes this script did not write - ABORT")
    if not cave_blank and not cave_installed and n_ours == 0:
        raise SystemExit("cave is dirty but no site points at it - ABORT, investigate %#x"
                         % CAVE_VA)

    if not args.apply:
        print("\n  DRY RUN -- nothing written. Re-run with --apply.")
        if n_ours == 4 and cave_installed:
            print("  (chain is intact)")
        return 0

    # --- snapshot: ONLY on --apply, ONLY over a proven-unpatched file ---------------
    backup = os.path.join(BACKUP_DIR, EXE + BACKUP_SUFFIX)
    pristine = (n_orig == 4 and cave_blank)
    if pristine and not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print("\n    backup -> %s   (all four sites vanilla, cave blank)" % backup)
    elif not pristine:
        print("\n    re-tune over an existing install - NO snapshot minted "
              "(the current file is this script's own output, not a pre-patch state)")
    else:
        print("\n    snapshot already exists - left alone: %s" % backup)

    d[cave_off:cave_off + CAVE_LEN] = cave + b"\0" * (CAVE_LEN - len(cave))
    for s in st:
        d[s["off"]:s["off"] + 5] = s["patched"]
    assert len(d) == orig_len, "file length changed"
    write(path, d)

    print("[%s] APPLIED: %d B cave at %#010x, four calls retargeted." % (EXE, len(cave), CAVE_VA))
    print("     !!!! NOW RUN: python build_scripts/build_zigeditor.py --apply")
    return 0


def write(path, d):
    try:
        open(path, "wb").write(bytes(d))
    except PermissionError:
        raise SystemExit(
            "[%s] LOCKED - an AoW binary is running. Kill it and retry:\n"
            "  Get-Process | Where-Object { $_.ProcessName -match "
            "'^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd)$' } | Stop-Process -Force"
            % os.path.basename(path))


if __name__ == "__main__":
    sys.exit(main())
