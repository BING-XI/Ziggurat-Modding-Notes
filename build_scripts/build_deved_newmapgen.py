#!/usr/bin/env python3
r"""
AoW1 EDITOR "NEW MAP -> GENERATED MAP"  --  AoWDevEd.exe only.

WHAT IT DOES
  The existing New map dialog gains a "New blank map" / "New generated map" choice plus
  the generator's controls (style + eight terrain prevalences). Blank behaves exactly as
  before. Generated runs Zig Modding Tools\devedgen.bat with the dialog's Map size and
  Map levels, waits for it, and opens the map it produced.

HOW
  * OKBtnClick @0x004034E4 is a five-byte THUNK -- `call 0x4033F0; ret`. So the hook is a
    CALL RETARGET of the rel32 at 0x004034E5 (see aow1-call-retarget-thunk): four bytes,
    nothing displaced, no .reloc exposure, trivial --undo. Blank maps re-enter the vanilla
    body at 0x004033F0 unchanged.
  * A DFM component only gets stored into the form instance if the class has a published
    FIELD of that name, and the compiled class cannot grow. So the cave could not read any
    new control without also growing the class. This patch therefore RELOCATES AND EXTENDS
    the field table (VMT-0x2C, 19 -> 30 entries), extends its class table (8 -> 9, the new
    entry pointing at the EXISTING TComboBox VMT import slot 0x00432640 so no new import is
    needed) and bumps InstanceSize (VMT-0x1C) 0x228 -> 0x254 so the object is allocated
    large enough to hold the new slots. Same shape as the method-table relocation in
    build_deved_terrainpal.py, applied to a second table.
    ⚠ Neither table can grow in place: field table, method table and the class-name
    shortstring sit packed back to back at file 0x2782.
* The generation controls all carry ONE handler, GenChanged, so that touching any of
    them selects "New generated map" and refreshes the sea slider's readout; the form's
    OnShow carries a second, GenInit, which sets the dropdown selections a Delphi 3 DFM
    cannot express. A DFM can only bind a handler the class publishes, so the METHOD
    table (VMT-0x28, 1 -> 3 entries) is relocated and extended exactly as the field
    table is.
  * Nothing is shelled out to that is not already imported. TCustomComboBox.GetItemIndex
    @0x00401A90, GetModuleFileNameA @0x00401158, FileExists @0x004017D8,
    TApplication.ProcessMessages @0x00401320, Sleep via [0x004322A0].
    WinExec is NOT in AoWDevEd's IAT; it is reached through vclx30.dpl, whose base the cave
    recovers from an import it already has:
        vclx30_base = [0x004332E4] - 0x19604      (checklst.TCheckListBox.GetChecked)
        WinExec     = [vclx30_base + 0x243F8]
  * ⚠ The game directory is derived at RUNTIME with GetModuleFileNameA and never baked in
    (aow1-no-machine-specific-paths; build_dlgdirs.py is the patch that got this wrong).
  * The generated path comes back through Zig Modding Tools\last_map.txt, which the bridge
    deletes before it starts, so a failed run cannot make the editor re-open the previous
    map and look as if it worked.
  * ⚠ The blank container is written with HSEngine.THSEngine.SaveHSM, reached as
    [0x004329C0] - 0x25C (the IAT slot for NewHSM, which this exe already imports, minus
    the two functions' fixed RVA difference). The map's own VMT has NO save method --
    slot 0xAC on TAoWHSMap is AddMapLevel -- and THSMEdit.Save cannot be used because the
    editor has not adopted the map yet at OKBtnClick time.

CONVENTIONS: dry-run by default, --apply to write, --undo to revert surgically, idempotent,
verify-before-write. Backup to backups\AoWDevEd.exe.pre-newmapgen. Editor only; AoW.exe and
AoWCompat.exe are untouched. Close AoWDevEd.exe first.

⚠⚠ A form whose DFM, field table or InstanceSize is wrong fails at LOAD, and every static
check in this script would still pass. This must be proved by LAUNCHING THE EDITOR and
opening File > New.
"""
import argparse
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE = "AoWDevEd.exe"
SECT_NAME = b".nmg\0\0\0\0"
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
BACKUP_NAME = EXE + ".pre-newmapgen"

# ---- verified addresses (Zig notes/NewMapDlg_Generator_Spec.md) --------------------
VMT = 0x004031D0
VMT_FIELDTABLE = VMT - 0x2C
VMT_METHODTABLE = VMT - 0x28
VMT_INSTSIZE = VMT - 0x1C
FIELDTABLE_VA = 0x00403250
METHODTABLE_VA = 0x00403382    # 1 entry: OKBtnClick
CLASSTABLE_VA = 0x004033A0
INSTSIZE_OLD = 0x228
OK_THUNK = 0x004034E4          # call 0x4033F0 ; ret
OK_BODY = 0x004033F0
DFM_FILE_OFF = 0xCE7D4

T_COMBOBOX_SLOT = 0x00432640   # StdCtrls..TComboBox VMT, already imported
CB_GETITEMINDEX = 0x00401A90
GETMODULEFILENAME = 0x00401158
FILEEXISTS = 0x004017D8
PROCESSMESSAGES = 0x00401320
SLEEP_SLOT = 0x004322A0
MAINFORM_GLOBAL = 0x0042F0A8   # [[this]] = TMainForm
LOADMAP = 0x004296D4           # eax=TMainForm edx=AnsiString
HSMEDIT_CLOSE = 0x00402E58     # eax=[MainForm+0x22C]; al=0 => cancelled
MAINFORM_HSMEDIT = 0x22C
VCLX_SLOT = 0x004332E4         # checklst.TCheckListBox.GetChecked
VCLX_EXPORT_RVA = 0x00019604
VCLX_WINEXEC_RVA = 0x000243F8
RADIO_CHECKED = 0x11D
GETHANDLE = 0x004016D8         # Controls.TWinControl.GetHandle
SENDMESSAGE = 0x00401468       # user32!SendMessageA thunk
T_EDIT_SLOT = 0x00432648       # StdCtrls..TEdit VMT, already imported
T_SCROLLBAR_SLOT = 0x0043262C  # StdCtrls..TScrollBar VMT, already imported
SBM_GETPOS = 0x00E1            # a TScrollBar is a real Windows SCROLLBAR
SETCHECKED = 0x00401AB8        # StdCtrls.TRadioButton.SetChecked: eax=ctl, dl=bool
SETTEXT = 0x00401568           # Controls.TControl.SetText: eax=ctl, edx=AnsiString
HANDLER_NAME = 'GenChanged'    # the DFM binds the handlers to this BY NAME
INIT_NAME = 'GenInit'          # the FORM's OnShow
CB_SETCURSEL = 0x014E
LSTRASG = 0x004010C0           # System.@LStrAsg: eax=dest var, edx=src
HSMEDIT_SAVE = 0x00402E48      # THSMEdit.Save; eax=THSMEdit
HSMEDIT_FILENAME = 0x1E4       # THSMEdit's current filename (AnsiString).
                               # Verified in HSEPack THSMEdit.Save @55614ED0:
                               # it reads [ebx+0x1E4] and hands it straight to
                               # the map's save method; empty falls to SaveAs.
HSMEDIT_HASMAP = 0x1BC         # 0 => THSMEdit.Save returns without doing anything
ENGINE_GLOBAL = 0x00432894     # [[this]] = THSEngine
ENGINE_HSM = 0x3C              # engine's CURRENT map -- NewHSM sets it, SaveHSM reads it
NEWHSM_SLOT = 0x004329C0       # IAT: HSEngine.THSEngine.NewHSM, which the vanilla body calls
SAVEHSM_DELTA = 0x25C          # SaveHSM = [NEWHSM_SLOT] - this. Same module, so the
                               # difference is rebase-invariant: NewHSM is rva 0x10698
                               # and SaveHSM rva 0x1043C in HSEPack.dpl.

# existing form fields we read for size / levels
F_LARGE, F_MEDIUM, F_SMALL = 0x200, 0x204, 0x208
F_ONELEVEL, F_TWOLEVELS = 0x218, 0x21C
F_XLARGE = 0x1FC               # the size radios, in the cave's own 0..3 order
F_THREELEVELS = 0x220

TERRAINS = ('Grass', 'Steppe', 'Desert', 'Snow',
            'Wasteland', 'Lava', 'Chasm', 'Sky')
GRADES = ('None', 'Very Low', 'Low', 'Medium', 'High', 'Very High')
#: default grade index per terrain, in TERRAINS order
TERRAIN_DEFAULT = (2, 0, 0, 0, 0, 0, 0, 0)     # Grass Low, the rest None

#: the world dials, in zig_mapgen.DIALS order -- the bridge passes them straight
#: through, so this list and GRADE_SCALES must stay in the same order
#: the graded dials, in the order the bridge expects them. Sea is NOT here: it is
#: a slider, because it is the one knob worth more than six positions.
DIALS = (('Sea ice', 2), ('Rivers', 3), ('Lakes', 3), ('Relief', 3),
         ('Erosion', 4), ('Structure', 4), ('Rain shadow', 3),
         ('Valley cutting', 2), ('River greening', 3),
         ('Mountains', 4), ('Hills', 3), ('Islands', 2))

WATER_DEFAULT = 30          # per cent of the map under sea, the slider's start

#: which end of the map is cold. The far end gets the desert -- one temperature
#: gradient does both halves, see zig_mapgen.COLD_DIRS.
COLD_DIRS = ('None', 'North', 'South', 'East', 'West', 'Random')
COLD_DEFAULT = 1            # North

#: the dialog's own defaults for the two vanilla radio groups. The cave reads both
#: by ELIMINATION -- nothing checked among Small/Medium/Large means XL, nothing among
#: One/Two means three levels -- so moving Checked in the DFM is the whole change.
SIZE_DEFAULT = 'ExtraLargeRB'
LEVEL_DEFAULT = 'ThreeLevels'

INFO_NAME = 'GenInfo'          # the info button's OnClick

#: what the info button shows. The dialog itself stays controls-only.
INFO_TEXT = (
    "Terrain prevalence\r\n"
    "    Each terrain's share of the land, from None to Very High.\r\n"
    "    The map decides WHERE each one goes; these decide HOW MUCH.\r\n"
    "    None removes a terrain from the map entirely.\r\n"
    "\r\n"
    "World\r\n"
    "    Sea %            how much of the map lies under water\r\n"
    "    Sea ice          how much of that sea freezes, at the cold end\r\n"
    "    Rivers           total length of the river network\r\n"
    "    Lakes            how much water collects in hollows\r\n"
    "    Relief           height of the ridged mountain relief\r\n"
    "    Erosion          higher wears the land flatter and smoother\r\n"
    "    Structure        strength of the overarching plan: rifts,\r\n"
    "                     sweeps, spirals, domes, caldera and fault lines\r\n"
    "    Rain shadow      how dry the downwind side of high ground gets\r\n"
    "    Valley cutting   how deeply the rivers carve their valleys\r\n"
    "    River greening   how far the fertile band beside a river reaches\r\n"
    "    Mountains        share of the land under mountain\r\n"
    "    Hills            share of the land under hills, which fringe\r\n"
    "                     the mountains and pad out the broken ground\r\n"
    "    Islands          share of the open sea filled in with islands,\r\n"
    "                     added after the mainland is finished\r\n"
    "\r\n"
    "Island size (hexes)\r\n"
    "    Smallest island kept and largest island added. 0 = no limit.\r\n"
    "    Anything smaller than the minimum is drowned.\r\n"
    "\r\n"
    "Cold direction\r\n"
    "    Which end of the map holds the snow and the sea ice.\r\n"
    "    The opposite end gets the desert. Random picks one per map.\r\n"
    "    None spreads both by climate noise instead.\r\n"
    "\r\n"
    "Settings are remembered from the last map you generated.\r\n")
MSGBOX = 0x00401348            # Forms.TApplication.MessageBox: eax=Self, edx=Text,
                               # ecx=Caption, Flags on the stack, ret 4
APP_SLOT = 0x00432224          # IAT: Forms.Application -- a VARIABLE, so [[slot]]
SBM_SETPOS = 0x00E0
WM_HSCROLL = 0x0114
SB_THUMBPOSITION = 4
CI_PANEL = 0                   # existing class-table index, as Panel1/ClientPnl use
WM_SETTEXT = 0x000C
CI_BUTTON = 1                  # existing class-table index, as OKBtn/CancelBtn use

#: the saved-settings markers the bridge writes, one empty file per slot named
#: <key><digit>. Order here IS the slot order, and deved_bridge.STATE_KEYS must match.
#: ⚠ EVERY KEY MUST DIFFER WITHOUT REGARD TO CASE. Windows compares filenames
#: case-insensitively, so an earlier 'abcd'/'efgh' tail silently answered the probes for
#: 'ABCD'/'EFGH': Desert came back as the island minimum's digit and Sky as the maximum's.
#: Letters then digits keeps all 33 first characters distinct with no case in play.
#: ⚠ A key's CHARACTER carries its meaning across a rebuild, so a new dial takes an
#: unused character at its own slot rather than re-lettering the ones after it. Markers
#: left in lastgen\ by an older build then still mean what they meant.
STATE_KEYS = ('ABCDEFGH'          # W0..W7, the terrain prevalences
              'IJKLMNOPQR7S'      # D0..D11, the world dials -- Hills, inserted at
                                  # D10, took the unused '7' so 'S' still means Islands
              'T'                 # ColdCB
              'UV'                # map size, map levels
              'WXY'               # sea %, as three digits
              'Z012'              # island minimum, right-aligned digits
              '3456')             # island maximum
STATE_DIR = 'Zig Modding Tools\\lastgen\\'
GENPNL_TOP = 198
GENPNL_HEIGHT = 100 + (len(DIALS) - 1) * 30 + 24 + 18

#: new published fields, in the order they get instance slots from 0x228 up
#: the last published field is the streaming sentinel GenChanged reads -- see there
NEW_FIELDS = (['BlankMapRB', 'GenMapRB']
              + ['W%d' % i for i in range(len(TERRAINS))]
              + ['WaterSB']
              + ['D%d' % i for i in range(len(DIALS))]
              + ['SeaVal', 'IslMin', 'IslMax', 'ColdCB', 'IslNote'])
CI_RADIOBUTTON = 5          # existing class-table index for TRadioButton
CI_LABEL = 6                # existing class-table index for TLabel
CI_COMBOBOX = 8             # appended: points at T_COMBOBOX_SLOT
CI_EDIT = 9                 # appended: points at T_EDIT_SLOT
CI_SCROLLBAR = 10           # appended: points at T_SCROLLBAR_SLOT
FORM_WIDTH = 700            # ClientWidth 447 -> room for three columns
#: ⚠ DERIVED, not a constant: the panel clips its children and the form clips the
#: panel, so both have to clear the LAST dial row. Eleven dials overflowed a 412-high
#: panel; the twelfth would have overflowed the 680-high form the same way, silently --
#: a clipped combo is simply not there, it does not error.
FORM_HEIGHT = GENPNL_TOP + GENPNL_HEIGHT + 40


# ---- DFM emit helpers --------------------------------------------------------------

def ss(s):
    b = s.encode('latin1')
    assert len(b) < 256, s
    return bytes([len(b)]) + b


def v_i(n):
    if -128 <= n <= 127:
        return b"\x02" + struct.pack("<b", n)
    if -32768 <= n <= 32767:
        return b"\x03" + struct.pack("<h", n)
    return b"\x04" + struct.pack("<i", n)


def v_str(s):
    return b"\x06" + ss(s)


def v_id(s):
    return b"\x07" + ss(s)


def v_true():
    return b"\x09"


def v_list_str(items):
    return b"\x01" + b"".join(v_str(i) for i in items) + b"\x00"


def prop(name, val):
    return ss(name) + val


def obj(cls, name, props, children=b""):
    return ss(cls) + ss(name) + props + b"\x00" + children + b"\x00"


def _label(name, x, y, w, text):
    return obj("TLabel", name, (
        prop("Left", v_i(x)) + prop("Top", v_i(y)) + prop("Width", v_i(w)) +
        prop("Height", v_i(16)) + prop("Caption", v_str(text))))


def _combo(name, x, y, w, tab, items, sel):
    """A csDropDownList combo. ItemIndex cannot be set here -- Delphi 3 leaves it
    public rather than published -- so Text carries the initial display, which only
    works because Items.Strings is streamed before it. The cave still substitutes the
    same default when GetItemIndex reports -1."""
    return obj("TComboBox", name, (
        prop("Left", v_i(x)) + prop("Top", v_i(y)) + prop("Width", v_i(w)) +
        prop("Height", v_i(24)) + prop("Style", v_id("csDropDownList")) +
        prop("ItemHeight", v_i(16)) + prop("TabOrder", v_i(tab)) +
        # ⚠ Items.Strings FIRST: Text picks the matching item, so streamed against an
        # empty list it selects nothing and the combo shows blank with ItemIndex -1.
        prop("Items.Strings", v_list_str(list(items))) +
        prop("Text", v_str(items[sel])) +
        # both, because a csDropDownList combo reports a selection change as OnClick
        # in some Delphi 3 builds and as OnChange in others. GenChanged is idempotent,
        # so firing twice costs nothing and firing never would be fatal.
        prop("OnChange", v_id(HANDLER_NAME)) +
        prop("OnClick", v_id(HANDLER_NAME))))


def build_genpnl():
    """The generation block appended to the New map form.

    Only TPanel, TLabel, TRadioButton, TComboBox and TEdit are used. TTrackBar is not
    linked into this binary at all, so the island range is two numeric edits rather
    than a dual slider, and every grade is a dropdown rather than a slider.
    """
    kids = [
        obj("TRadioButton", "BlankMapRB", (
            prop("Left", v_i(12)) + prop("Top", v_i(8)) + prop("Width", v_i(180)) +
            prop("Height", v_i(17)) + prop("Caption", v_str("New blank map")) +
            prop("TabOrder", v_i(0)))),
        # generated is the DEFAULT (user ruling 2026-09-06). GenChanged's streaming guard
        # still matters: it stops a load-time event LEAVING this state, and the two edits
        # do raise one while GenInit puts the saved settings back.
        obj("TRadioButton", "GenMapRB", (
            prop("Left", v_i(200)) + prop("Top", v_i(8)) + prop("Width", v_i(200)) +
            prop("Height", v_i(17)) + prop("Caption", v_str("New generated map")) +
            prop("Checked", v_true()) + prop("TabOrder", v_i(1)) +
            prop("TabStop", v_true()))),
        _label("TerrHdr", 12, 36, 120, "Terrain prevalence"),
        _label("DialHdr", 236, 36, 120, "World"),
        _label("IslHdr", 470, 36, 160, "Island size (hexes)"),
    ]
    tab = 2
    for i, terr in enumerate(TERRAINS):
        y = 60 + i * 30
        kids.append(_label("TL%d" % i, 12, y + 4, 70, terr))
        kids.append(_combo("W%d" % i, 86, y, 130, tab, GRADES, TERRAIN_DEFAULT[i]))
        tab += 1
    # Sea gets a slider rather than a dropdown: it is the single most consequential
    # number on the map, and six positions is not enough resolution for it.
    # ⚠ TTrackBar is not linked into this binary, so this is a TScrollBar -- which is
    # a real Windows SCROLLBAR, so both the cave and GenChanged read it with SBM_GETPOS.
    # A scrollbar displays no value of its own, so SeaVal is its readout.
    kids.append(_label("SeaL", 236, 64, 56, "Sea %"))
    kids.append(_label("SeaVal", 296, 64, 34, str(WATER_DEFAULT)))
    kids.append(obj("TScrollBar", "WaterSB", (
        prop("Left", v_i(336)) + prop("Top", v_i(62)) + prop("Width", v_i(118)) +
        prop("Height", v_i(16)) + prop("Kind", v_id("sbHorizontal")) +
        prop("Min", v_i(0)) + prop("Max", v_i(100)) +
        prop("Position", v_i(WATER_DEFAULT)) +
        # Delphi 3 does not publish PageSize (it arrived in D4), and TReader
        # rejects the whole form over one unknown property. Published on D3
        # TScrollBar: Kind, Min, Max, Position, LargeChange, SmallChange.
        prop("LargeChange", v_i(10)) + prop("SmallChange", v_i(1)) +
        prop("OnChange", v_id(HANDLER_NAME)) +
        prop("TabOrder", v_i(tab)))))
    kids.append(_label("SeaLo", 336, 80, 20, "0"))
    kids.append(_label("SeaHi", 434, 80, 24, "100"))
    tab += 1
    for i, (name, sel) in enumerate(DIALS):
        y = 100 + i * 30
        kids.append(_label("DL%d" % i, 236, y + 4, 96, name))
        kids.append(_combo("D%d" % i, 336, y, 118, tab, GRADES, sel))
        tab += 1
    kids.append(_label("IslMinL", 470, 64, 90, "Smallest"))
    kids.append(obj("TEdit", "IslMin", (
        prop("Left", v_i(566)) + prop("Top", v_i(60)) + prop("Width", v_i(100)) +
        prop("Height", v_i(24)) + prop("TabOrder", v_i(tab)) +
        prop("OnChange", v_id(HANDLER_NAME)) + prop("Text", v_str("1")))))
    kids.append(_label("IslMaxL", 470, 94, 90, "Largest"))
    kids.append(obj("TEdit", "IslMax", (
        prop("Left", v_i(566)) + prop("Top", v_i(90)) + prop("Width", v_i(100)) +
        prop("Height", v_i(24)) + prop("TabOrder", v_i(tab + 1)) +
        prop("OnChange", v_id(HANDLER_NAME)) + prop("Text", v_str("0")))))
    # ⚠ The house rule is controls and data only, no inline prose. This button is the
    # user's own request (2026-09-05): the explanations live behind it, not on the form.
    kids.append(obj("TButton", "InfoBtn", (
        prop("Left", v_i(566)) + prop("Top", v_i(196)) + prop("Width", v_i(100)) +
        prop("Height", v_i(25)) + prop("Caption", v_str("Explain settings")) +
        prop("TabOrder", v_i(tab + 3)) + prop("OnClick", v_id(INFO_NAME)))))
    kids.append(_label("ColdL", 470, 164, 90, "Cold direction"))
    kids.append(_combo("ColdCB", 566, 160, 100, tab + 2, COLD_DIRS, COLD_DEFAULT))
    # ⚠ LAST, and a TLabel: GenChanged uses it as its streaming sentinel, so nothing
    # that can raise an event may be appended after this line
    kids.append(_label("IslNote", 470, 122, 200, "0 = no limit"))

    return obj("TPanel", "GenPnl", (
        prop("Left", v_i(8)) + prop("Top", v_i(GENPNL_TOP)) + prop("Width", v_i(684)) +
        prop("Height", v_i(GENPNL_HEIGHT)) + prop("BevelOuter", v_id("bvNone")) +
        prop("TabOrder", v_i(2))), b"".join(kids))


# ---- PE helpers --------------------------------------------------------------------

def load_pe(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e + 6)[0]
    optsz = struct.unpack_from('<H', d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b + 8)
        secs.append((d[b:b + 8].rstrip(b'\0'), va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from('<I', d, opt + 32)[0],
                falign=struct.unpack_from('<I', d, opt + 36)[0])


def align(x, a):
    return (x + a - 1) // a * a


def rva2off(secs, rva):
    for _nm, va, vsz, raw, rsz, _b in secs:
        if va <= rva < va + max(vsz, rsz):
            return raw + (rva - va)
    raise ValueError('rva %#x not in any section' % rva)


def va2off(secs, va):
    return rva2off(secs, va - 0x400000)


def find_dfm_entry(d, F):
    """The .rsrc data entry for TNEWMAPDLG: (entry_off, data_rva, data_size)."""
    rsrc_rva, _ = struct.unpack_from('<II', d, F['opt'] + 96 + 2 * 8)
    ro = rva2off(F['secs'], rsrc_rva)

    def name_at(v):
        off = ro + (v & 0x7FFFFFFF)
        n = struct.unpack_from('<H', d, off)[0]
        return d[off + 2:off + 2 + 2 * n].decode('utf-16le')

    hits = []

    def walk(diroff, path):
        nn, ni = struct.unpack_from('<HH', d, ro + diroff + 12)
        for i in range(nn + ni):
            eo = ro + diroff + 16 + i * 8
            nm, off = struct.unpack_from('<II', d, eo)
            label = name_at(nm) if nm & 0x80000000 else '#%d' % nm
            if off & 0x80000000:
                walk(off & 0x7FFFFFFF, path + [label])
            elif any(p.upper() == 'TNEWMAPDLG' for p in path + [label]):
                drva, dsize = struct.unpack_from('<II', d, ro + off)
                hits.append((ro + off, drva, dsize))

    walk(0, [])
    assert len(hits) == 1, 'TNEWMAPDLG resource entries: %d' % len(hits)
    return hits[0]


def read_field_table(d, secs):
    fo = va2off(secs, FIELDTABLE_VA)
    count = struct.unpack_from('<H', d, fo)[0]
    ctp = struct.unpack_from('<I', d, fo + 2)[0]
    p = fo + 6
    entries = []
    for _ in range(count):
        offs = struct.unpack_from('<I', d, p)[0]
        ci = struct.unpack_from('<H', d, p + 4)[0]
        n = d[p + 6]
        entries.append((offs, ci, d[p + 7:p + 7 + n].decode('latin1')))
        p += 7 + n
    return count, ctp, entries, fo, p - fo


def read_method_table(d, secs):
    """Published methods: <u16 count> then {<u16 entrysize><u32 addr><shortstring>}."""
    mo = va2off(secs, METHODTABLE_VA)
    count = struct.unpack_from('<H', d, mo)[0]
    p = mo + 2
    entries = []
    for _ in range(count):
        size, code = struct.unpack_from('<HI', d, p)
        n = d[p + 6]
        assert size == 7 + n, 'method entry size %d, name is %d B' % (size, n)
        entries.append((code, d[p + 7:p + 7 + n].decode('latin1')))
        p += size
    return count, entries, mo, p - mo


def emit_method_table(entries):
    b = struct.pack('<H', len(entries))
    for code, name in entries:
        b += struct.pack('<HI', 7 + len(name), code) + ss(name)
    return b


def read_class_table(d, secs, ctp):
    co = va2off(secs, ctp)
    n = struct.unpack_from('<H', d, co)[0]
    slots = [struct.unpack_from('<I', d, co + 2 + 4 * i)[0] for i in range(n)]
    return n, slots, co


# ---- the cave ----------------------------------------------------------------------

def assemble_cave(cave_va, data_va, fieldoff):
    r"""eax = TNewMapDlg on entry. Blank -> vanilla body; generated -> run and open.

    The command line is <game dir>\Zig Modding Tools\devedgen.bat followed by the
    dialog's values as plain tokens: two digits for size and levels, then one digit
    per terrain and per dial, then the two island-size edits copied as text. The
    mapping from those numbers to meaning lives in deved_bridge.py, where it can
    change without touching the binary.

    The handoff back is a FIXED path, <game>\Scenario\Custom\zNewMap.hsm, because the
    editor imports no file API beyond FileExists -- no read, no delete. The bridge
    deletes that file before it starts, so the cave waits for it to go ABSENT and then
    PRESENT; that transition is the sync point.
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32

    o_gen = fieldoff['GenMapRB']
    o_w = [fieldoff['W%d' % i] for i in range(len(TERRAINS))]
    o_d = [fieldoff['D%d' % i] for i in range(len(DIALS))]
    o_water = fieldoff['WaterSB']
    o_islmin = fieldoff['IslMin']
    o_islmax = fieldoff['IslMax']
    o_cold = fieldoff['ColdCB']

    b_dir = data_va               # 320 B  "<game dir>\"
    b_cmd = data_va + 320         # 640 B  the command line
    b_tmp = data_va + 960         # 32 B   scratch for WM_GETTEXT
    b_hdr = data_va + 1000        # AnsiString header: [0]=refcount [4]=length
    b_txt = b_hdr + 8             # 320 B  the path handed to FileExists / LoadMap
    b_mhdr = data_va + 1400       # AnsiString header for the .done marker
    b_mtxt = b_mhdr + 8           # 320 B
    s_cmd = data_va + 1800        # "Zig Modding Tools\devedgen.bat"
    s_map = data_va + 1864        # "Scenario\Custom\zNewMap.hsm"
    s_done = data_va + 1928       # "Scenario\Custom\zNewMap.done"
    b_fhdr = data_va + 3200       # and the same for the FAILURE marker
    b_ftxt = b_fhdr + 8
    s_fail = data_va + 3560

    asm = []
    A = asm.append
    A("push ebx")
    A("push esi")
    A("push edi")
    A("mov  ebx, eax")

    A("mov  eax, [ebx + %d]" % o_gen)
    A("test eax, eax")
    A("jz   blank")
    A("cmp  byte ptr [eax + %d], 0" % RADIO_CHECKED)
    A("jz   blank")

    # ---- "<game dir>\" -- derived at runtime, never baked into the binary
    A("push 260")
    A("push %d" % b_dir)
    A("push 0")
    A("mov  eax, %d" % GETMODULEFILENAME)
    A("call eax")
    A("test eax, eax")
    A("jz   blank")
    A("mov  edi, %d" % b_dir)
    A("add  edi, eax")
    A("scan:")
    A("dec  edi")
    A("cmp  edi, %d" % b_dir)
    A("jbe  blank")
    A("cmp  byte ptr [edi], 0x5C")
    A("jne  scan")
    A("inc  edi")
    A("mov  byte ptr [edi], 0")

    # ---- the two paths this needs, built as Delphi AnsiString literals
    # (refcount -1 = a literal, never freed) so they can be passed to LStrAsg,
    # FileExists and the map loader directly.
    A("mov  edi, %d" % b_txt)
    A("mov  esi, %d" % b_dir)
    A("call copyz")
    A("mov  esi, %d" % s_map)
    A("call copyz")
    A("mov  byte ptr [edi], 0")
    A("sub  edi, %d" % b_txt)
    A("mov  [%d], edi" % (b_hdr + 4))
    A("mov  dword ptr [%d], 0xFFFFFFFF" % b_hdr)

    A("mov  edi, %d" % b_mtxt)
    A("mov  esi, %d" % b_dir)
    A("call copyz")
    A("mov  esi, %d" % s_done)
    A("call copyz")
    A("mov  byte ptr [edi], 0")
    A("sub  edi, %d" % b_mtxt)
    A("mov  [%d], edi" % (b_mhdr + 4))
    A("mov  dword ptr [%d], 0xFFFFFFFF" % b_mhdr)

    A("mov  edi, %d" % b_ftxt)
    A("mov  esi, %d" % b_dir)
    A("call copyz")
    A("mov  esi, %d" % s_fail)
    A("call copyz")
    A("mov  byte ptr [edi], 0")
    A("sub  edi, %d" % b_ftxt)
    A("mov  [%d], edi" % (b_fhdr + 4))
    A("mov  dword ptr [%d], 0xFFFFFFFF" % b_fhdr)

    # ---- let the VANILLA body build a genuinely blank map at the chosen size,
    # then save it to the handoff path. That is what stops a generated map
    # inheriting another mapmaker's players and hero library: the container is
    # now the editor's own New-blank output, not somebody's scenario.
    A("mov  eax, ebx")
    A("mov  edx, %d" % OK_BODY)
    A("call edx")

    A("mov  eax, [%d]" % MAINFORM_GLOBAL)
    A("mov  eax, [eax]")
    A("test eax, eax")
    A("jz   done")
    A("mov  esi, [eax + %d]" % MAINFORM_HSMEDIT)   # esi = THSMEdit
    A("test esi, esi")
    A("jz   done")
    A("lea  eax, [esi + %d]" % HSMEDIT_FILENAME)   # tell the editor its name
    A("mov  edx, %d" % b_txt)
    A("mov  ecx, %d" % LSTRASG)
    A("call ecx")

    # Write it with THSEngine.SaveHSM(engine, filename, progressproc, progressdata),
    # which saves the engine's CURRENT map -- engine[+0x3C], which THSEngine.NewHSM has
    # just set to the map the vanilla body built and sized. Verified live: that field
    # and the [0x43289C] map global hold the same object at this point.
    #
    # ⚠ NOT THSMEdit.Save: it opens `cmp byte [self+0x1BC],0 / je fail` and that flag
    # is clear here, because the editor does not adopt the map until OKBtnClick returns
    # to its caller.
    # ⚠⚠ And NOT the map's own VMT slot 0xAC. Save's tail reads
    # `mov edx,[self+0x1E4]; mov eax,esi; mov ecx,[eax]; call [ecx+0xAC]` where esi is
    # [THSMEdit+0x1C0], the editor's DOCUMENT object -- not the map. On TAoWHSMap that
    # slot is AddMapLevel, so calling it with a string pointer wrote nothing at all and
    # the generator silently reused whatever stale zNewMap.hsm was on disk. That is what
    # made an Extra Large request come back 64x64. The map's VMT has no save of its own.
    #
    # The two stack arguments are a progress callback and its Self; nil is the
    # no-progress case. SaveHSM is `ret 8`, so the callee clears them.
    A("mov  eax, [%d]" % ENGINE_GLOBAL)
    A("mov  eax, [eax]")
    A("test eax, eax")
    A("jz   done")
    A("cmp  dword ptr [eax + %d], 0" % ENGINE_HSM)
    A("jz   done")
    A("push 0")
    A("push 0")
    A("mov  edx, %d" % b_txt)
    A("mov  ecx, [%d]" % NEWHSM_SLOT)
    A("sub  ecx, %d" % SAVEHSM_DELTA)
    A("call ecx")

    A("mov  edi, %d" % b_cmd)
    A("mov  esi, %d" % b_dir)
    A("call copyz")
    A("mov  esi, %d" % s_cmd)
    A("call copyz")

    seq = [0]

    def digit(lines, default=None):
        """One ' d' token. `default` covers GetItemIndex reporting -1, which is what a
        csDropDownList says until the user picks: ItemIndex cannot be set from the DFM
        because Delphi 3 leaves it public rather than published."""
        for ln in lines:
            A(ln)
        if default is not None:
            seq[0] += 1
            lbl = "sel%d" % seq[0]
            A("test eax, eax")
            A("jns  %s" % lbl)
            A("mov  eax, %d" % default)
            A("%s:" % lbl)
        A("add  al, 0x30")
        A("mov  byte ptr [edi], 0x20")
        A("mov  [edi+1], al")
        A("add  edi, 2")

    # size: 0 S, 1 M, 2 L, else 3 XL -- read from the dialog's own radios
    A("xor  ecx, ecx")
    for f in (F_SMALL, F_MEDIUM, F_LARGE):
        A("mov eax, [ebx + %d]" % f)
        A("cmp byte ptr [eax + %d], 0" % RADIO_CHECKED)
        A("jnz size_done")
        A("inc ecx")
    A("size_done:")
    digit(["mov eax, ecx"])
    # levels: 0 one, 1 two, else 2
    A("xor  ecx, ecx")
    for f in (F_ONELEVEL, F_TWOLEVELS):
        A("mov eax, [ebx + %d]" % f)
        A("cmp byte ptr [eax + %d], 0" % RADIO_CHECKED)
        A("jnz lv_done")
        A("inc ecx")
    A("lv_done:")
    digit(["mov eax, ecx"])

    for k, off in enumerate(o_w):
        digit(["mov eax, [ebx + %d]" % off,
               "mov edx, %d" % CB_GETITEMINDEX, "call edx"],
              default=TERRAIN_DEFAULT[k])

    # the sea slider, as a THREE-DIGIT number. Always three digits, zero-padded, so
    # the cave needs no leading-zero logic: the bridge parses "030" as 30.
    A("mov  byte ptr [edi], 0x20")
    A("inc  edi")
    A("mov  eax, %d" % WATER_DEFAULT)
    A("mov  ecx, [ebx + %d]" % o_water)
    A("test ecx, ecx")
    A("jz   water_have")
    A("push eax")
    A("mov  eax, ecx")
    A("mov  edx, %d" % GETHANDLE)
    A("call edx")
    A("test eax, eax")
    A("jz   water_pop")
    A("push 0")
    A("push 0")
    A("push %d" % SBM_GETPOS)
    A("push eax")
    A("mov  eax, %d" % SENDMESSAGE)
    A("call eax")
    A("add  esp, 4")
    A("jmp  water_have")
    A("water_pop:")
    A("pop  eax")
    A("water_have:")
    A("cmp  eax, 100")
    A("jbe  water_ok")
    A("mov  eax, %d" % WATER_DEFAULT)
    A("water_ok:")
    A("xor  edx, edx")
    A("mov  ecx, 100")
    A("div  ecx")
    A("add  al, 0x30")
    A("mov  [edi], al")
    A("inc  edi")
    A("mov  eax, edx")
    A("xor  edx, edx")
    A("mov  ecx, 10")
    A("div  ecx")
    A("add  al, 0x30")
    A("mov  [edi], al")
    A("inc  edi")
    A("mov  al, dl")
    A("add  al, 0x30")
    A("mov  [edi], al")
    A("inc  edi")
    for k, off in enumerate(o_d):
        digit(["mov eax, [ebx + %d]" % off,
               "mov edx, %d" % CB_GETITEMINDEX, "call edx"],
              default=DIALS[k][1])

    # the two island-size edits, copied as TEXT. TControl.GetText returns an
    # AnsiString through a hidden var parameter, which is awkward from a cave, so the
    # window is asked directly: WM_GETTEXT into a scratch buffer. Whatever the user
    # typed is passed through verbatim and parsed in the bridge.
    for off in (o_islmin, o_islmax):
        A("mov  byte ptr [edi], 0x20")
        A("inc  edi")
        A("mov  dword ptr [%d], 0" % b_tmp)
        A("mov  eax, [ebx + %d]" % off)
        A("test eax, eax")
        A("jz   isl_skip%d" % off)
        A("mov  edx, %d" % GETHANDLE)
        A("call edx")
        A("push %d" % b_tmp)
        A("push 16")
        A("push 13")                       # WM_GETTEXT
        A("push eax")
        A("mov  eax, %d" % SENDMESSAGE)
        A("call eax")
        A("isl_skip%d:" % off)
        A("cmp  byte ptr [%d], 0" % b_tmp)
        A("jne  isl_ok%d" % off)
        A("mov  byte ptr [%d], 0x30" % b_tmp)      # empty -> "0"
        A("mov  byte ptr [%d], 0" % (b_tmp + 1))
        A("isl_ok%d:" % off)
        A("mov  esi, %d" % b_tmp)
        A("call copyz")

    digit(["mov eax, [ebx + %d]" % o_cold,
           "mov edx, %d" % CB_GETITEMINDEX, "call edx"],
          default=COLD_DEFAULT)
    A("mov  byte ptr [edi], 0")

    # ---- WinExec, via vclx30's IAT (AoWDevEd has no process API of its own)
    A("mov  eax, [%d]" % VCLX_SLOT)
    A("sub  eax, %d" % VCLX_EXPORT_RVA)
    A("mov  eax, [eax + %d]" % VCLX_WINEXEC_RVA)
    A("test eax, eax")
    A("jz   blank")
    A("push 7")
    A("push %d" % b_cmd)
    A("call eax")
    A("cmp  eax, 31")
    A("jbe  done")

    A("mov  edi, 600")                     # phase 1: wait for the stale file to go
    A("w_gone:")
    A("call pump")
    A("call exists")
    A("test al, al")
    A("jz   w_made_init")
    A("dec  edi")
    A("jnz  w_gone")
    A("jmp  done")

    A("w_made_init:")
    A("mov  edi, 12000")                   # phase 2: wait for the new one
    A("w_made:")
    A("call pump")
    A("call failed")
    A("test al, al")
    A("jnz  done")
    A("call exists")
    A("test al, al")
    A("jnz  got_it")
    A("dec  edi")
    A("jnz  w_made")
    A("jmp  done")

    A("got_it:")
    A("mov  eax, [%d]" % MAINFORM_GLOBAL)
    A("mov  eax, [eax]")
    A("test eax, eax")
    A("jz   done")
    A("mov  esi, eax")
    A("mov  eax, [esi + %d]" % MAINFORM_HSMEDIT)
    A("mov  edx, %d" % HSMEDIT_CLOSE)
    A("call edx")
    A("test al, al")
    A("jz   done")
    A("mov  eax, esi")
    A("mov  edx, %d" % b_txt)
    A("mov  ecx, %d" % LOADMAP)
    A("call ecx")
    A("jmp  done")

    A("blank:")
    A("pop  edi")
    A("pop  esi")
    A("mov  eax, ebx")
    A("pop  ebx")
    A("mov  edx, %d" % OK_BODY)
    A("jmp  edx")

    A("done:")
    A("pop  edi")
    A("pop  esi")
    A("pop  ebx")
    A("ret")

    A("copyz:")
    A("mov  al, [esi]")
    A("test al, al")
    A("jz   copyz_end")
    A("mov  [edi], al")
    A("inc  esi")
    A("inc  edi")
    A("jmp  copyz")
    A("copyz_end:")
    A("ret")

    # Sleep only. TApplication.ProcessMessages takes Self in EAX and AoWDevEd never
    # calls it anywhere, so there is no call site to learn the Application global
    # from -- calling it with a junk Self is the access violation that showed up as
    # "Oh dear, it's the end....". The dialog is modal, so the editor is meant to be
    # unresponsive here; it just does not repaint while the map is built.
    A("pump:")
    A("push 50")
    A("call dword ptr [%d]" % SLEEP_SLOT)
    A("ret")

    A("exists:")
    A("mov  eax, %d" % b_mtxt)
    A("mov  edx, %d" % FILEEXISTS)
    A("call edx")
    A("ret")

    # \u26a0 Without this the editor sat frozen for the full 12000 x 50 ms -- ten minutes --
    # whenever the generator raised, because .done never appeared. The bridge writes this
    # marker in its `except` arm, so a failure comes back in one poll instead.
    A("failed:")
    A("mov  eax, %d" % b_ftxt)
    A("mov  edx, %d" % FILEEXISTS)
    A("call edx")
    A("ret")

    text = "\n".join(asm)
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code, _ = ks.asm(text, cave_va)
    blobs = {
        s_cmd: b"Zig Modding Tools\\devedgen.bat\x00",
        s_map: b"Scenario\\Custom\\zNewMap.hsm\x00",
        s_done: b"Scenario\\Custom\\zNewMap.done\x00",
        s_fail: b"Scenario\\Custom\\zNewMap.fail\x00",
    }
    # ⚠ RUNTIME buffers: nothing is written into them at build time, so they are
    # invisible to a check that only walks `blobs`. main() reserves these too.
    reserve = {'b_dir': (b_dir, 320), 'b_cmd': (b_cmd, 640), 'b_tmp': (b_tmp, 32),
               'b_hdr': (b_hdr, 328), 'b_mhdr': (b_mhdr, 328), 'b_fhdr': (b_fhdr, 328)}
    return bytes(code), text, blobs, reserve


def assemble_handler(at_va, data_va, fieldoff):
    r"""GenChanged -- one TNotifyEvent shared by every generation control.

    eax = the form, edx = whichever control fired. It does two things:

      * ticks "New generated map". Without it the dials get set, OK is pressed, the
        radio is still on "New blank map" and the vanilla blank path runs -- which is
        the all-water map that looked like a broken generator.
      * refreshes SeaVal from the slider, because a TScrollBar displays no number.

    WARNING: controls raise OnChange while the form is STREAMING, before the user has touched
    anything: a TScrollBar fires it when Position is loaded and a TEdit when Text is. The
    guard is the last component in the DFM, IslNote -- a component is bound to its field
    as its Name is read, which precedes its own properties, so IslNote is nil for every
    event raised during loading and non-nil for every one after.

    WARNING: the sentinel must also be a control that can raise NOTHING ITSELF. IslMax was
    tried first and fails: a TEdit's Text assignment reaches CM_TEXTCHANGED -> Change
    once its own field is already bound, so it opens the guard for itself and the dialog
    comes up on "New generated map". A TLabel has no such path.
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32

    o_gen = fieldoff['GenMapRB']
    o_water = fieldoff['WaterSB']
    o_seaval = fieldoff['SeaVal']
    o_last = fieldoff['IslNote']
    b_hdr = data_va + 2048        # AnsiString header: [0]=refcount [4]=length
    b_txt = b_hdr + 8             # "0".."100" + NUL
    b_busy = data_va + 2756       # raised while GenInit is restoring

    asm = []
    A = asm.append
    A("push ebx")
    A("push edi")
    A("mov  ebx, eax")
    A("mov  eax, [ebx + %d]" % o_last)
    A("test eax, eax")
    A("jz   h_done")                      # the form is still streaming
    # While GenInit is restoring, skip the radio but STILL refresh the readout. WM_SETTEXT
    # on a TEdit reaches CM_TEXTCHANGED -> Change, so restoring the island sizes would
    # otherwise tick "New generated map" every time the dialog opened -- and since the
    # island edits are the LAST thing GenInit restores, that same event is what puts the
    # restored sea percentage on the label. Skipping the whole handler left it stale.
    A("cmp  byte ptr [%d], 0" % b_busy)
    A("jnz  h_slider")

    A("mov  eax, [ebx + %d]" % o_gen)
    A("test eax, eax")
    A("jz   h_slider")
    A("mov  dl, 1")
    A("mov  ecx, %d" % SETCHECKED)
    A("call ecx")

    A("h_slider:")
    A("mov  eax, [ebx + %d]" % o_water)
    A("test eax, eax")
    A("jz   h_done")
    A("mov  edx, %d" % GETHANDLE)
    A("call edx")
    A("test eax, eax")
    A("jz   h_done")
    A("push 0")
    A("push 0")
    A("push %d" % SBM_GETPOS)
    A("push eax")
    A("mov  eax, %d" % SENDMESSAGE)
    A("call eax")
    A("cmp  eax, 100")
    A("jbe  h_fmt")
    A("mov  eax, %d" % WATER_DEFAULT)

    # 0..100 as decimal, no leading zeros
    A("h_fmt:")
    A("mov  edi, %d" % b_txt)
    A("xor  edx, edx")
    A("mov  ecx, 100")
    A("div  ecx")
    A("test eax, eax")
    A("jz   h_tens")
    A("add  al, 0x30")
    A("mov  [edi], al")
    A("inc  edi")
    A("h_tens:")
    A("mov  eax, edx")
    A("xor  edx, edx")
    A("mov  ecx, 10")
    A("div  ecx")
    A("test eax, eax")
    A("jnz  h_put")
    A("cmp  edi, %d" % b_txt)
    A("je   h_ones")
    A("h_put:")
    A("add  al, 0x30")
    A("mov  [edi], al")
    A("inc  edi")
    A("h_ones:")
    A("mov  al, dl")
    A("add  al, 0x30")
    A("mov  [edi], al")
    A("inc  edi")
    A("mov  byte ptr [edi], 0")
    A("sub  edi, %d" % b_txt)
    A("mov  [%d], edi" % (b_hdr + 4))
    A("mov  dword ptr [%d], 0xFFFFFFFF" % b_hdr)    # refcount -1: a literal

    A("mov  eax, [ebx + %d]" % o_seaval)
    A("test eax, eax")
    A("jz   h_done")
    A("mov  edx, %d" % b_txt)
    A("mov  ecx, %d" % SETTEXT)
    A("call ecx")

    A("h_done:")
    A("pop  edi")
    A("pop  ebx")
    A("ret")

    text = "\n".join(asm)
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code, _ = ks.asm(text, at_va)
    return bytes(code), text, {'h_hdr': (b_hdr, 24), 'b_busy': (b_busy, 1)}


def assemble_init(at_va, data_va, fieldoff):
    r"""GenInit -- the form's OnShow. eax = the form, edx = the form.

    Sets each dropdown's selection, which the DFM cannot do: Delphi 3 leaves ItemIndex
    public rather than published, and Text is inert on a csDropDownList because Windows
    ignores WM_SETTEXT on CBS_DROPDOWNLIST. Without this all 19 open blank -- verified
    live, 0 of 19 had a selection -- and the user cannot see the defaults the cave will
    actually use.

    A combo that ALREADY has a selection is left alone, so re-opening the dialog keeps
    whatever was chosen last time rather than resetting to defaults.

    CB_SETCURSEL does not generate CBN_SELCHANGE, so this cannot trip GenChanged and
    move the radio off "New blank map".
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32

    combos = ([('W%d' % i, TERRAIN_DEFAULT[i]) for i in range(len(TERRAINS))]
              + [('D%d' % i, DIALS[i][1]) for i in range(len(DIALS))]
              + [('ColdCB', COLD_DEFAULT)])
    nslots = len(STATE_KEYS)
    assert nslots == len(combos) + 2 + 3 + 8, 'STATE_KEYS is %d slots' % nslots

    st_hdr = data_va + 2400        # AnsiString for FileExists
    st_txt = st_hdr + 8            # "<game dir>Zig Modding Tools\lastgen\Xd"
    b_ins = data_va + 2740         # where the two-character marker name starts
    b_vals = data_va + 2760        # one probed digit per slot, 0xFF = not saved
    b_num = data_va + 2810         # scratch: the sea value, then the edit text
    t_keys = data_va + 2830
    # ⚠ t_combo is `4 * len(combos)` bytes, so its SLOT has to leave room for the
    # dial list to grow. At eleven dials it was 80 B against an 80-B slot, and the
    # twelfth ran four bytes into t_size. Room for 40 combos now, and the assert below
    # says so plainly rather than leaving it to the overlap check further down.
    t_combo = data_va + 2880
    t_size = data_va + 3040
    t_level = data_va + 3060
    assert t_combo + 4 * len(combos) <= t_size,         '%d combos need %d B; the t_combo slot holds %d' % (
            len(combos), 4 * len(combos), t_size - t_combo)
    b_busy = data_va + 2756        # GenChanged sits out everything below
    s_state = data_va + 3080

    asm = []
    A = asm.append
    A("push ebx")
    A("push esi")
    A("push edi")
    A("mov  ebx, eax")
    A("mov  byte ptr [%d], 1" % b_busy)

    # ---- "<game dir>Zig Modding Tools\lastgen\" -- derived, never baked in
    A("push 260")
    A("push %d" % st_txt)
    A("push 0")
    A("mov  eax, %d" % GETMODULEFILENAME)
    A("call eax")
    A("test eax, eax")
    A("jz   i_defaults")
    A("mov  edi, %d" % st_txt)
    A("add  edi, eax")
    A("i_scan:")
    A("dec  edi")
    A("cmp  edi, %d" % st_txt)
    A("jbe  i_defaults")
    A("cmp  byte ptr [edi], 0x5C")
    A("jne  i_scan")
    A("inc  edi")
    A("mov  esi, %d" % s_state)
    A("i_copy:")
    A("mov  al, [esi]")
    A("test al, al")
    A("jz   i_copied")
    A("mov  [edi], al")
    A("inc  edi")
    A("inc  esi")
    A("jmp  i_copy")
    A("i_copied:")
    A("mov  [%d], edi" % b_ins)                  # the marker name goes here
    A("sub  edi, %d" % st_txt)
    A("add  edi, 2")                             # <key><digit>
    A("mov  [%d], edi" % (st_hdr + 4))
    A("mov  dword ptr [%d], 0xFFFFFFFF" % st_hdr)

    # ---- probe every slot: at most ten stat calls each
    A("xor  esi, esi")
    A("i_slot:")
    A("cmp  esi, %d" % nslots)
    A("jae  i_probed")
    A("mov  byte ptr [esi + %d], 0xFF" % b_vals)
    A("xor  edi, edi")
    A("i_val:")
    A("cmp  edi, 10")
    A("jae  i_slotnext")
    A("mov  ecx, [%d]" % b_ins)
    A("mov  al, [esi + %d]" % t_keys)
    A("mov  [ecx], al")
    A("lea  eax, [edi + 0x30]")
    A("mov  [ecx+1], al")
    A("mov  byte ptr [ecx+2], 0")
    A("push esi")
    A("push edi")
    A("mov  eax, %d" % st_txt)
    A("mov  edx, %d" % FILEEXISTS)
    A("call edx")
    A("pop  edi")
    A("pop  esi")
    A("test al, al")
    A("jz   i_valnext")
    A("mov  eax, edi")
    A("mov  [esi + %d], al" % b_vals)
    A("jmp  i_slotnext")
    A("i_valnext:")
    A("inc  edi")
    A("jmp  i_val")
    A("i_slotnext:")
    A("inc  esi")
    A("jmp  i_slot")
    A("i_probed:")

    # ---- put the saved selections back. The default pass below then only fires for
    # anything that had no marker, because it skips a combo that already has one.
    A("xor  esi, esi")
    A("i_cb:")
    A("cmp  esi, %d" % len(combos))
    A("jae  i_cbdone")
    A("movzx eax, byte ptr [esi + %d]" % b_vals)
    A("cmp  eax, 5")
    A("ja   i_cbnext")
    A("mov  edx, [esi*4 + %d]" % t_combo)
    A("mov  eax, [ebx + edx]")
    A("test eax, eax")
    A("jz   i_cbnext")
    A("push esi")
    A("mov  edx, %d" % GETHANDLE)
    A("call edx")
    A("pop  esi")
    A("test eax, eax")
    A("jz   i_cbnext")
    A("movzx ecx, byte ptr [esi + %d]" % b_vals)
    A("push esi")
    A("push 0")
    A("push ecx")
    A("push %d" % CB_SETCURSEL)
    A("push eax")
    A("mov  eax, %d" % SENDMESSAGE)
    A("call eax")
    A("pop  esi")
    A("i_cbnext:")
    A("inc  esi")
    A("jmp  i_cb")
    A("i_cbdone:")

    # ---- the two radio groups. 0xFF fails the same bound check as an out-of-range digit.
    for slot, table, count, label in ((len(combos), t_size, 4, 'size'),
                                      (len(combos) + 1, t_level, 3, 'level')):
        A("movzx eax, byte ptr [%d]" % (b_vals + slot))
        A("cmp  eax, %d" % count)
        A("jae  i_%s_skip" % label)
        A("mov  edx, [eax*4 + %d]" % table)
        A("mov  eax, [ebx + edx]")
        A("test eax, eax")
        A("jz   i_%s_skip" % label)
        A("mov  dl, 1")
        A("mov  ecx, %d" % SETCHECKED)
        A("call ecx")
        A("i_%s_skip:" % label)

    # ---- the sea slider, three digits
    sea = len(combos) + 2
    A("movzx eax, byte ptr [%d]" % (b_vals + sea))
    A("cmp  eax, 10")
    A("jae  i_sea_skip")
    A("movzx edx, byte ptr [%d]" % (b_vals + sea + 1))
    A("cmp  edx, 10")
    A("jae  i_sea_skip")
    A("movzx ecx, byte ptr [%d]" % (b_vals + sea + 2))
    A("cmp  ecx, 10")
    A("jae  i_sea_skip")
    A("imul eax, eax, 100")
    A("imul edx, edx, 10")
    A("add  eax, edx")
    A("add  eax, ecx")
    A("cmp  eax, 100")
    A("jbe  i_sea_ok")
    A("mov  eax, 100")
    A("i_sea_ok:")
    A("mov  [%d], eax" % b_num)
    # SBM_SETPOS straight at the window, which is also how the cave READS it back, so
    # the two always agree.
    # ⚠ Reflecting a WM_HSCROLL(SB_THUMBPOSITION) off the parent -- the "proper" VCL
    # route, which would also set the control's own FPosition -- was tried and MEASURED
    # to do nothing on Delphi 3: the position stayed put. Do not re-attempt it.
    A("mov  eax, [ebx + %d]" % fieldoff['WaterSB'])
    A("test eax, eax")
    A("jz   i_sea_skip")
    A("mov  edx, %d" % GETHANDLE)
    A("call edx")
    A("test eax, eax")
    A("jz   i_sea_skip")
    A("push 1")
    A("push dword ptr [%d]" % b_num)
    A("push %d" % SBM_SETPOS)
    A("push eax")
    A("mov  eax, %d" % SENDMESSAGE)
    A("call eax")
    A("i_sea_skip:")

    # ---- the two island edits. The bridge right-aligns the digits and writes no marker
    # for a leading zero, so copying only the ones that exist strips them for free.
    for k, (name, base) in enumerate((('IslMin', sea + 3), ('IslMax', sea + 7))):
        A("mov  edi, %d" % b_num)
        for j in range(4):
            A("movzx eax, byte ptr [%d]" % (b_vals + base + j))
            A("cmp  eax, 10")
            A("jae  i_e%d_%d" % (k, j))
            A("add  al, 0x30")
            A("mov  [edi], al")
            A("inc  edi")
            A("i_e%d_%d:" % (k, j))
        A("mov  byte ptr [edi], 0")
        A("cmp  edi, %d" % b_num)
        A("je   i_edone%d" % k)
        A("mov  eax, [ebx + %d]" % fieldoff[name])
        A("test eax, eax")
        A("jz   i_edone%d" % k)
        A("mov  edx, %d" % GETHANDLE)
        A("call edx")
        A("test eax, eax")
        A("jz   i_edone%d" % k)
        A("push %d" % b_num)
        A("push 0")
        A("push %d" % WM_SETTEXT)
        A("push eax")
        A("mov  eax, %d" % SENDMESSAGE)
        A("call eax")
        A("i_edone%d:" % k)

    A("i_defaults:")
    for k, (name, default) in enumerate(combos):
        skip = "i_skip%d" % k
        A("mov  eax, [ebx + %d]" % fieldoff[name])
        A("test eax, eax")
        A("jz   %s" % skip)
        A("mov  edx, %d" % CB_GETITEMINDEX)
        A("call edx")
        A("test eax, eax")
        A("jns  %s" % skip)                     # already chosen: leave it
        A("mov  eax, [ebx + %d]" % fieldoff[name])
        A("mov  edx, %d" % GETHANDLE)
        A("call edx")
        A("test eax, eax")
        A("jz   %s" % skip)
        A("push 0")
        A("push %d" % default)
        A("push %d" % CB_SETCURSEL)
        A("push eax")
        A("mov  eax, %d" % SENDMESSAGE)
        A("call eax")
        A("%s:" % skip)
    A("mov  byte ptr [%d], 0" % b_busy)
    A("pop  edi")
    A("pop  esi")
    A("pop  ebx")
    A("ret")

    text = "\n".join(asm)
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code, _ = ks.asm(text, at_va)
    blobs = {
        s_state: STATE_DIR.encode('latin1') + b"\x00",
        t_keys: STATE_KEYS.encode('latin1'),
        t_combo: b"".join(struct.pack("<I", fieldoff[n]) for n, _d in combos),
        t_size: struct.pack("<IIII", F_SMALL, F_MEDIUM, F_LARGE, F_XLARGE),
        t_level: struct.pack("<III", F_ONELEVEL, F_TWOLEVELS, F_THREELEVELS),
    }
    reserve = {'st_hdr': (st_hdr, 8 + 330), 'b_ins': (b_ins, 4),
               'b_vals': (b_vals, len(STATE_KEYS)), 'b_num': (b_num, 20),
               'b_busy': (b_busy, 1)}
    return bytes(code), text, blobs, reserve


def assemble_info(at_va, data_va):
    r"""GenInfo -- the info button. eax = the form, edx = the button.

    Forms.TApplication.MessageBox(eax=Self, edx=Text, ecx=Caption, Flags on the stack,
    ret 4). Application is an imported VARIABLE, so its IAT slot holds the address OF the
    variable and the instance is one dereference further in.
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32

    # ⚠⚠ THE INFO TEXT IS THE THING THAT GROWS, so it goes LAST in the data area and
    # everything else stays below it. It was at data+3100 while the OK cave's failure-marker
    # buffers sat at data+4500 -- i.e. INSIDE it, once a twelfth dial pushed the text past
    # 1300 bytes. The corruption is copy-on-write and in-memory only, so it appeared only
    # after a map had been generated in that session and vanished on the next launch.
    # The reservation assert in main() now covers the runtime buffers too.
    s_text = data_va + 4000       # ~2000 B of room before s_cap
    s_cap = data_va + 6000

    asm = []
    A = asm.append
    A("mov  eax, [%d]" % APP_SLOT)
    A("test eax, eax")
    A("jz   f_out")
    A("mov  eax, [eax]")
    A("test eax, eax")
    A("jz   f_out")
    A("push 0")
    A("mov  ecx, %d" % s_cap)
    A("mov  edx, %d" % s_text)
    A("call %d" % MSGBOX)
    A("f_out:")
    A("ret")

    text = "\n".join(asm)
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code, _ = ks.asm(text, at_va)
    return bytes(code), text, {s_text: INFO_TEXT.encode('latin1') + b"\x00",
                               s_cap: b"Map generation settings\x00"}


def _move_default(blob, frm, to):
    """Move Checked+TabStop from one radio button to another, in place.

    Both are `<shortstring name><vaTrue>` and a component's properties follow its name
    immediately, so the first hit after the name belongs to that component. Lengths are
    unchanged, so nothing else in the resource moves.
    """
    out = blob
    for pb in (prop("Checked", v_true()), prop("TabStop", v_true())):
        assert out.count(ss(frm)) == 1, "%s is not unique in the DFM" % frm
        assert out.count(ss(to)) == 1, "%s is not unique in the DFM" % to
        i = out.find(ss(frm))
        j = out.find(pb, i)
        assert j > i, "%s carries no %s" % (frm, pb[1:1 + pb[0]].decode('latin1'))
        out = out[:j] + out[j + len(pb):]
        k = out.find(ss(to)) + len(ss(to))
        out = out[:k] + pb + out[k:]
    assert len(out) == len(blob)
    return out


def rebuild_dfm(d, dfm_off, dfm_size, genpnl):
    """Original DFM with ClientHeight grown and the GenPnl block appended.

    The form object ends with its children terminator, a single 0 byte, so the new
    panel is inserted immediately before it. Nothing else in the resource moves.
    """
    blob = bytes(d[dfm_off:dfm_off + dfm_size])
    assert blob[:4] == b"TPF0", "TNEWMAPDLG resource is not a DFM"
    assert blob[-1] == 0, "DFM does not end with a children terminator"

    # OnShow goes in as the form's FIRST property, immediately after its class and
    # object names. Property ORDER is irrelevant to TReader, and inserting at the front
    # means never having to skip over the existing values to find the end of the block.
    p = 4
    p += 1 + blob[p]
    p += 1 + blob[p]
    out = blob[:p] + prop("OnShow", v_id(INIT_NAME)) + blob[p:]

    # the generator wants room: default to the largest map and all three levels
    out = _move_default(out, "MediumRB", SIZE_DEFAULT)
    out = _move_default(out, "OneLevel", LEVEL_DEFAULT)
    for pname, was, now in (("ClientHeight", 232, FORM_HEIGHT),
                            ("ClientWidth", 447, FORM_WIDTH)):
        old = ss(pname) + b"\x03" + struct.pack("<h", was)
        new = ss(pname) + b"\x03" + struct.pack("<h", now)
        assert out.count(old) == 1, "%s %d not found exactly once" % (pname, was)
        assert len(old) == len(new)
        out = out.replace(old, new, 1)
    return out[:-1] + genpnl + out[-1:]


def build_tables(entries, ccount, cslots):
    """New field table (old entries + NEW_FIELDS) and class table (+TComboBox, +TEdit).

    The class table entries are IAT slots, so the two new ones point at VMTs the exe
    already imports for other forms -- no new import, no .idata surgery.
    """
    assert ccount == CI_COMBOBOX, \
        'class table has %d entries, expected %d' % (ccount, CI_COMBOBOX)
    ft_entries = list(entries)
    for i, name in enumerate(NEW_FIELDS):
        offs = INSTSIZE_OLD + 4 * i
        if name == 'WaterSB':
            ci = CI_SCROLLBAR
        elif name in ('SeaVal', 'IslNote'):
            ci = CI_LABEL
        elif name == 'ColdCB':
            ci = CI_COMBOBOX
        elif name.startswith('Isl'):
            ci = CI_EDIT
        elif name.startswith('W') or name.startswith('D'):
            ci = CI_COMBOBOX
        else:
            ci = CI_RADIOBUTTON
        ft_entries.append((offs, ci, name))

    ct = struct.pack("<H", ccount + 3)
    ct += b"".join(struct.pack("<I", s) for s in cslots)
    ct += struct.pack("<I", T_COMBOBOX_SLOT)
    ct += struct.pack("<I", T_EDIT_SLOT)
    ct += struct.pack("<I", T_SCROLLBAR_SLOT)
    return ft_entries, ct, CI_COMBOBOX


def emit_field_table(entries, classtab_va):
    b = struct.pack("<H", len(entries)) + struct.pack("<I", classtab_va)
    for offs, ci, name in entries:
        b += struct.pack("<IH", offs, ci) + ss(name)
    return b


def running_editor():
    try:
        import subprocess
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % EXE],
                             capture_output=True, text=True, timeout=20).stdout
        return EXE.lower() in out.lower()
    except Exception:                                        # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser(description='AoWDevEd New map -> generated map')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--undo', action='store_true')
    ap.add_argument('--dis', action='store_true', help='disassemble the cave')
    args = ap.parse_args()

    path = os.path.join(GAME, EXE)
    backup = os.path.join(BACKUP_DIR, BACKUP_NAME)
    d = bytearray(open(path, 'rb').read())
    F = load_pe(d)
    have = any(nm == SECT_NAME.rstrip(b'\0') for nm, *_ in F['secs'])

    count, ctp, entries, fo, ftlen = read_field_table(d, F['secs'])
    ccount, cslots, co = read_class_table(d, F['secs'], ctp)
    mcount, mentries, mo, mtlen = read_method_table(d, F['secs'])
    inst = struct.unpack_from('<I', d, va2off(F['secs'], VMT_INSTSIZE))[0]
    entry_off, dfm_rva, dfm_size = find_dfm_entry(d, F)
    thunk_off = va2off(F['secs'], OK_THUNK)
    cur_rel = struct.unpack_from('<i', d, thunk_off + 1)[0]
    cur_target = OK_THUNK + 5 + cur_rel

    print('[%s] field table %#x: %d entries (%d B) | class table %#x: %d'
          % (EXE, FIELDTABLE_VA, count, ftlen, ctp, ccount))
    # mentries is always read from the COMPILED table, which --undo restores to; the
    # VMT slot is printed separately because after --apply it points elsewhere
    print('      method table %#x: %d entries (%d B) -- %s | VMT-0x28 -> %#x'
          % (METHODTABLE_VA, mcount, mtlen, ', '.join(n for _a, n in mentries),
             struct.unpack_from('<I', d, va2off(F['secs'], VMT_METHODTABLE))[0]))
    print('      InstanceSize %#x | DFM rva %#x (%d B) | OKBtnClick -> %#x | .nmg: %s'
          % (inst, dfm_rva, dfm_size, cur_target, have))

    if args.undo:
        if not os.path.exists(backup):
            print('      no backup at %s -- cannot undo' % backup)
            return 1
        if running_editor():
            print('      AoWDevEd.exe is RUNNING -- close it first')
            return 1
        b = bytearray(open(backup, 'rb').read())
        Fb = load_pe(b)
        # surgical: only the four things this patch repoints
        struct.pack_into('<i', d, thunk_off + 1,
                         struct.unpack_from('<i', b, va2off(Fb['secs'], OK_THUNK) + 1)[0])
        for va in (VMT_FIELDTABLE, VMT_METHODTABLE, VMT_INSTSIZE):
            struct.pack_into('<I', d, va2off(F['secs'], va),
                             struct.unpack_from('<I', b, va2off(Fb['secs'], va))[0])
        eo, drva, dsz = find_dfm_entry(b, Fb)
        struct.pack_into('<II', d, entry_off, drva, dsz)
        open(path, 'wb').write(d)
        print('      reverted: rel32, VMT-0x2C, VMT-0x28, VMT-0x1C,'
              ' TNEWMAPDLG resource entry.')
        print('      (the .nmg section stays behind as dead data, as the other'
              ' editor patches do)')
        return 0

    if cur_target != OK_BODY:
        print('      already applied (OKBtnClick -> %#x). --undo first to rebuild.'
              % cur_target)
        return 0

    assert inst == INSTSIZE_OLD, 'InstanceSize is %#x, expected %#x' % (inst, INSTSIZE_OLD)
    assert mcount == 1 and mentries[0][1] == 'OKBtnClick', \
        'method table is %r, expected just OKBtnClick' % (mentries,)
    assert cur_target == OK_BODY, 'OKBtnClick already retargeted to %#x' % cur_target

    genpnl = build_genpnl()
    new_dfm = rebuild_dfm(d, rva2off(F['secs'], dfm_rva), dfm_size, genpnl)
    ft_entries, new_ct, combo_ci = build_tables(entries, ccount, cslots)
    fieldoff = {n: INSTSIZE_OLD + 4 * i for i, n in enumerate(NEW_FIELDS)}
    new_inst = INSTSIZE_OLD + 4 * len(NEW_FIELDS)

    # ---- lay out the section. --undo deliberately leaves .nmg behind as dead data,
    # so a re-apply REUSES it rather than appending a second copy every cycle; it is
    # sized generously on first creation so a rebuilt cave always fits.
    existing = next((s_ for s_ in F['secs']
                     if s_[0] == SECT_NAME.rstrip(bytes([0]))), None)
    if existing is not None:
        _n, newva, _vsz, exist_raw, exist_rawsz, exist_hdr = existing
    else:
        newva = align(max(va + max(vsz, rsz) for _n, va, vsz, _r, rsz, _b in F['secs']),
                      F['salign'])
    cave_va = 0x400000 + newva
    body = bytearray()

    def place(blob, alignment=4):
        while len(body) % alignment:
            body.append(0)
        at = len(body)
        body.extend(blob)
        return 0x400000 + newva + at

    # the three handlers plus the OK cave outgrew a single page
    CODE_SPAN = 0x2000
    code, asmtext, blobs, bufs = assemble_cave(cave_va, cave_va + CODE_SPAN, fieldoff)
    body.extend(code)
    # GenChanged sits immediately after the OK cave, in the same execute+write section
    while len(body) % 16:
        body.append(0)
    handler_va = cave_va + len(body)
    hcode, hasm, hres = assemble_handler(handler_va, cave_va + CODE_SPAN, fieldoff)
    body.extend(hcode)
    while len(body) % 16:
        body.append(0)
    init_va = cave_va + len(body)
    icode, iasm, iblobs, ires = assemble_init(init_va, cave_va + CODE_SPAN, fieldoff)
    body.extend(icode)
    while len(body) % 16:
        body.append(0)
    info_va = cave_va + len(body)
    fcode, fasm, fblobs = assemble_info(info_va, cave_va + CODE_SPAN)
    body.extend(fcode)
    blobs = dict(blobs)
    blobs.update(iblobs)
    blobs.update(fblobs)
    assert len(body) < CODE_SPAN, 'code is %d B, past the data area' % len(body)
    while len(body) < CODE_SPAN:
        body.append(0)
    data_base = cave_va + CODE_SPAN
    body.extend(b'\x00' * 1200)              # b_dir / b_cmd / AnsiString header + text
    # ⚠ offsets are relative to CODE_SPAN, not a hardcoded page: when the code outgrew
    # one page and data_base moved, a stale 0x1000 here put every string 4 KB early --
    # inside the code region -- and silently broke the whole generate path.
    # ⚠⚠ BLOBS AND RUNTIME BUFFERS TOGETHER. Walking only the blobs missed the OK
    # cave's failure-marker buffers, which nothing writes at build time: at eleven dials
    # they sat past the end of the info text, and the twelfth grew the text over them.
    # Nothing failed at build, nothing failed on load, and the info box lost its last
    # third for the rest of any session in which a map had been generated.
    named = [(va, va + len(b), 'blob %#x' % va) for va, b in blobs.items()]
    for src in (bufs, hres, ires):
        for nm, (va, size) in src.items():
            named.append((va, va + size, nm))
    seen = {}
    for a0, a1, nm in named:                 # b_busy is shared by two handlers on purpose
        if nm in seen:
            assert seen[nm] == (a0, a1), '%s declared twice with different extents' % nm
    spans = sorted(dict(((nm, (a0, a1)) for a0, a1, nm in named)).items(),
                   key=lambda kv: kv[1])
    for (n0, (a0, a1)), (n1, (b0, _b1)) in zip(spans, spans[1:]):
        assert a1 <= b0, ('%s at %#x runs %d B into %s at %#x -- an overlap here is'
                          ' silent: it survives the build, survives the load, and only'
                          ' shows as corrupted text or a truncated path at runtime'
                          % (n0, a0, a1 - b0, n1, b0))
    for va, blob in sorted(blobs.items()):
        at = va - data_base
        assert at >= 0, 'blob %#x is below the data base' % va
        while len(body) < CODE_SPAN + at:
            body.append(0)
        body[CODE_SPAN + at:CODE_SPAN + at + len(blob)] = blob
    hi = max(off - data_base + len(b) for off, b in blobs.items())
    while len(body) < CODE_SPAN + hi + 16:
        body.append(0)

    new_methods = (mentries + [(handler_va, HANDLER_NAME), (init_va, INIT_NAME),
                               (info_va, INFO_NAME)])
    mt_va = place(emit_method_table(new_methods))
    ct_va = place(new_ct)
    ft_va = place(emit_field_table(ft_entries, ct_va))
    dfm_va = place(new_dfm)
    dfm_new_rva = dfm_va - 0x400000

    # ---- verify the rebuilt tables round-trip before anything is written
    probe = bytearray(b'\x00' * 0x1000) + b''
    ftb = emit_field_table(ft_entries, ct_va)
    c2 = struct.unpack_from('<H', ftb, 0)[0]
    p = 6
    got = []
    for _ in range(c2):
        o2, ci = struct.unpack_from('<IH', ftb, p)
        n = ftb[p + 6]
        got.append((o2, ci, ftb[p + 7:p + 7 + n].decode('latin1')))
        p += 7 + n
    assert c2 == count + len(NEW_FIELDS) and p == len(ftb), 'field table does not round-trip'
    assert [g[2] for g in got[:count]] == [e[2] for e in entries], 'field table reordered'
    assert got[-1][0] + 4 == new_inst, 'last field %#x does not end at InstanceSize %#x' \
        % (got[-1][0], new_inst)
    for name in NEW_FIELDS:
        assert any(g[2] == name for g in got), '%s missing from field table' % name
    assert struct.unpack_from('<H', new_ct, 0)[0] == ccount + 3
    assert struct.unpack_from('<I', new_ct, 2 + 4 * ccount)[0] == T_COMBOBOX_SLOT
    assert struct.unpack_from('<I', new_ct, 6 + 4 * ccount)[0] == T_EDIT_SLOT
    assert struct.unpack_from('<I', new_ct, 10 + 4 * ccount)[0] == T_SCROLLBAR_SLOT
    mtb = emit_method_table(new_methods)
    m2, mp = struct.unpack_from('<H', mtb, 0)[0], 2
    for _ in range(m2):
        msz = struct.unpack_from('<H', mtb, mp)[0]
        assert msz == 7 + mtb[mp + 6], 'method entry does not round-trip'
        mp += msz
    assert m2 == mcount + 3 and mp == len(mtb), 'method table does not round-trip'
    assert struct.unpack_from('<I', mtb, mp - (7 + len(INFO_NAME)) + 2)[0] == info_va
    # the DFM binds by name, so a typo here is a load-time error dialog, not a crash
    assert (ss(HANDLER_NAME) in bytes(new_dfm)), 'no control references %s' % HANDLER_NAME
    assert bytes(new_dfm).count(ss(INIT_NAME)) == 1, '%s is not bound once' % INIT_NAME
    assert bytes(new_dfm).count(ss(INFO_NAME)) == 1, '%s is not bound once' % INFO_NAME

    print('      cave %d B @ %#x | DFM %d -> %d B @ rva %#x' %
          (len(code), cave_va, dfm_size, len(new_dfm), dfm_new_rva))
    print('      field table -> %#x (%d entries, %d B) | class table -> %#x (%d)' %
          (ft_va, c2, len(ftb), ct_va, ccount + 3))
    print('      method table -> %#x (%d entries, %d B) | %s @ %#x (%d B), %d bindings'
          ' | %s @ %#x (%d B)' %
          (mt_va, m2, len(mtb), HANDLER_NAME, handler_va, len(hcode),
           bytes(new_dfm).count(ss(HANDLER_NAME)), INIT_NAME, init_va, len(icode)))
    print('      %s @ %#x (%d B) | data %#x, %d B of blobs' %
          (INFO_NAME, info_va, len(fcode), data_base, hi))
    print('      InstanceSize %#x -> %#x | rel32 @ %#x: %#x -> %#x' %
          (inst, new_inst, OK_THUNK + 1, OK_BODY, cave_va))
    print('      new fields: ' + ', '.join('%s@+%#x' % (n, fieldoff[n]) for n in NEW_FIELDS))

    if args.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        cs = Cs(CS_ARCH_X86, CS_MODE_32)
        for i in cs.disasm(code, cave_va):
            print('        %08X  %-24s %s' % (i.address, i.mnemonic, i.op_str))
        for nm, blob, va in ((HANDLER_NAME, hcode, handler_va),
                             (INIT_NAME, icode, init_va),
                             (INFO_NAME, fcode, info_va)):
            print('      --- %s ---' % nm)
            for i in cs.disasm(blob, va):
                print('        %08X  %-24s %s' % (i.address, i.mnemonic, i.op_str))

    if not args.apply:
        print('\n      DRY RUN. Nothing written. --apply to patch.')
        return 0

    if running_editor():
        print('\n      AoWDevEd.exe is RUNNING -- close it and retry.')
        return 1

    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print('      backup -> backups\\%s' % BACKUP_NAME)

    if existing is not None:
        # --undo leaves .nmg behind as dead data, so a rebuild writes into the
        # existing section instead of appending a second copy every cycle. It is the
        # LAST section and its raw data runs to the end of the file, so when a rebuilt
        # cave outgrows it the section can simply be regrown in place.
        assert exist_raw + exist_rawsz >= len(d), (
            '.nmg is not the last section (raw ends %#x, file is %#x) -- cannot grow'
            % (exist_raw + exist_rawsz, len(d)))
        rawsz = max(exist_rawsz, align(len(body) + 0x1000, F['falign']))
        del d[exist_raw:]
        d += bytes(body) + bytes(rawsz - len(body))
        struct.pack_into('<II', d, exist_hdr + 8, len(body), newva)
        struct.pack_into('<II', d, exist_hdr + 16, rawsz, exist_raw)
        struct.pack_into('<I', d, F['opt'] + 56, align(newva + rawsz, F['salign']))
        print('      reusing .nmg (%d of %d B%s)'
              % (len(body), rawsz, ', regrown' if rawsz != exist_rawsz else ''))
    else:
        newraw = align(len(d), F['falign'])
        d += bytes(newraw - len(d))
        rawsz = align(max(len(body), 0x4000), F['falign'])   # room for later rebuilds
        d += bytes(body) + bytes(rawsz - len(body))
        b = F['sectbl'] + F['nsec'] * 40
        struct.pack_into('<8sIIII', d, b, SECT_NAME, len(body), newva, rawsz, newraw)
        # code + initialised data, execute/read/WRITE: the cave needs writable buffers
        struct.pack_into('<IIHHI', d, b + 24, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into('<H', d, F['e'] + 6, F['nsec'] + 1)
        struct.pack_into('<I', d, F['opt'] + 56, align(newva + rawsz, F['salign']))

    struct.pack_into('<I', d, va2off(F['secs'], VMT_FIELDTABLE), ft_va)
    struct.pack_into('<I', d, va2off(F['secs'], VMT_METHODTABLE), mt_va)
    struct.pack_into('<I', d, va2off(F['secs'], VMT_INSTSIZE), new_inst)
    struct.pack_into('<II', d, entry_off, dfm_new_rva, len(new_dfm))
    struct.pack_into('<i', d, thunk_off + 1, cave_va - (OK_THUNK + 5))

    try:
        open(path, 'wb').write(d)
    except PermissionError:
        print('      LOCKED -- close the editor and retry')
        return 1
    print('\n      APPLIED. .nmg @ rva %#x (%d B).' % (newva, len(body)))
    # ASCII only: a cp1252 console raises UnicodeEncodeError here, AFTER the write, and
    # the traceback reads exactly like a failed patch
    print('      !! APPLIED, UNTESTED: open AoWDevEd and File > New. A wrong field table')
    print('        or InstanceSize makes the form fail to LOAD, and every check above')
    print('        still passes. Revert with --undo.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
