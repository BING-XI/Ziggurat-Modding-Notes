#!/usr/bin/env python3
r"""
SETTINGS > SPELLS GETS A "Caster:" DROP-DOWN   (AoWDevEd.exe -> AoWzEd.exe)

Spells carry a per-spell byte, the CASTER FAMILY, at spell object field `+0x23`:

    0 None   1 Evoker   2 Conjurer   3 Enchanter   4 Ritualist

The AoWEPACK half (a separate script, not this one) makes `TSpell.ReadWrite` stream it as
`Spells.pfs` tag 0x12.  The editor loads the same patched `AoWEPACK.dpl`, so whatever this
editor writes into `+0x23` is saved with the mapset.  This script is only the authoring
control: a "Caster:" label and a csDropDownList combo in the Settings group of the Spells
page, filled when a spell is selected and written back on change -- the way the vanilla
Sphere combo (`SphereEdit`, `[spell+0x20]`) works.

    target   Ziggurat\AoWDevEd.exe          (then build_zigeditor.py --apply -> AoWzEd.exe)
    hook     0x0042C0B8  E8 2B 70 FD FF     the tier `call TSpin.SetValue` in
                                            `TMainForm.SpellListBoxClick @0x0042BF60`;
                                            operand retarget, 4 bytes, nothing displaced
    cave     0x0052D6A0 .. 0x0052D7FF       352 B reserved, `.mtb` page slack above
                                            build_deved_listarrows.py's cave
    globals  0x004E0700  G_COMBO            the combo, once built
             0x004E0704  G_ID               the spell id last shown in it
                                            both in `.dlgd` page slack: loader-zeroed,
                                            writable, NO file offset -- nothing to undo
    dfm      4 Int16 values in the LIVE TMAINFORM (`.ctp`), length-neutral -- the layout
    roll     NONE.  This feature draws no random number and inherits none, so there is no
             pattern from the closed taxonomy to name.

WHY RUNTIME CONTROLS
  A DFM-named control with a DFM-named `OnChange` would need the form to GROW and a new
  published method.  A runtime-assigned TMethod needs neither.  Recipe:
  `Zig notes/08-editor.md` §12 (build_deved_itemhpmv.py).

WHY THE LAYOUT IS A DFM EDIT AND NOT RUNTIME SetTop CALLS
  GroupBox3 "Settings" is full (five rows, 32 px pitch, H185) and has GroupBox4 7 px
  below it, so a sixth row means GroupBox3 grows by 32 and the three groups beneath move
  down 32.  At runtime that is four setter calls, 57 B of code, and `.mtb`'s 352 B of
  slack is the only unowned file-backed executable space left in AoWDevEd.exe -- the
  controls, the handler and the literals already take 347 of it.  The four values are
  all vaInt16 before and after, so the edit is byte-for-byte length-neutral:

      Panel9/GroupBox3.Height        185 -> 217
      Panel9/GroupBox4.Top           368 -> 400
      Panel9/GroupBox5.Top           440 -> 472
      Panel9/SpellInfoGroup.Top      512 -> 544

  They are located by WALKING THE DFM every run (never a baked offset) through the
  resource directory entry, i.e. the LIVE copy in `.ctp` -- which is edited in place by
  build_deved_toolbar_trim.py and build_deved_heroprune.py too, both of which preserve
  unrelated bytes.  Each value must read vanilla or ours before anything is written.

THE HOOK                                        (ImageBase 0x400000, fixed base, no PIC)
  0x0042C0B8  call TSpin.SetValue(SphereLevelEdit, spell[+0x21]) -- the last control
  SpellListBoxClick fills before it restores the description memo's OnChange at
  0x0042C0BD.  Retargeted to `cave_load`, which runs the displaced SetValue FIRST.  There
  EBX = TMainForm and ESI = the selected spell's id (Delphi's register convention keeps
  both across SetValue; vanilla reuses ESI at 0x0042C102).  The cave preserves
  EBX/ESI/EDI.  `.reloc`: no fixup in the operand window, in `.mtb` or in `.dlgd`, and
  none in `.ctp` -- re-checked every run.

THE CAVE                                        (in file order)
  lit_label    "Caster:" as a Delphi 3 AnsiString literal (refcount -1): TControl.SetText
               compares it with LStrCmp, which reads the length word, so it needs one.
  getsp        EDX = id -> `TSpellControl.GetSpell([[0x432898]]+0x84, id)`, tail jump.
  cave_change  the combo's OnChange.  EAX = TMethod.Data = the form, EDX = Sender.
               map-loaded guard `[[0x432898]] != 0`; SpellListBox ItemIndex != -1 (the
               same guard vanilla `SphereEditChange @0x0042C9F8` uses); spell :=
               getsp(G_ID); nil check; `byte [spell+0x23] := ItemIndex` when >= 0.
  mk           EAX = class ref -> a new control, AOwner nil, parented to GroupBox3.
  cave_load    the displaced SetValue; if G_COMBO = 0, build once (below); then
               G_ID := id and `ItemIndex := [spell+0x23]` (-1, blank, for any value > 4).
               CB_SETCURSEL raises no CBN_SELCHANGE, so populating never fires cave_change.
  build        TLabel "Caster:" at (16,184) 37x13; TComboBox, SetStyle(csDropDownList),
               SetBounds (80,176) 121x21, `Items.SetTextStr(lit_items)`, OnChange :=
               (cave_change, form); publish G_COMBO.  GroupBox3 nil -> nothing built.
  lit_items    "None\nEvoker\nConjurer\nEnchanter\nRitualist\0" -- a bare NUL-terminated
               run, no StrRec: `TStrings.SetTextStr @0x4131F9B8` walks chars to #0 and
               never reads the length.  One call adds all five items.

  WHY G_ID, AND WHY IT IS SAFE.  cave_change used to re-derive the id from the listbox the
  way vanilla does (40 B); the id cave_load was given is the same number, because every
  selection change runs SpellListBoxClick first.  The listbox-index guard is kept, so a
  refilled list (index -1) still blocks a write, exactly as in vanilla.

  BUILD ONCE -- a stored-pointer guard is valid HERE, unlike on Item Properties.
  TMainForm is the application's main form: created once, alive until the process ends,
  so G_COMBO can never point at a freed combo on a new form.  AOwner is nil (as in
  build_deved_itemhpmv.py); both controls are children of GroupBox3 and are freed with it
  by `TWinControl.Destroy`.  They are not in `Components`, so the form's translator never
  touches the caption.

VCL TOOLKIT -- all already imported, nothing added to `.idata`
  class refs      StdCtrls..TLabel IAT 0x00432654, StdCtrls..TComboBox IAT 0x00432640
  Create          VMT +0x24 (TCustomLabel.Create / TCustomComboBox.Create), AOwner in ECX
  SetParent       VMT +0x3C = Controls.TControl.SetParent for both
  SetStyle        VMT +0x88 = TCustomComboBox.SetStyle.  csDropDownList = 2.
  SetBounds       TLabel's +0x4C is TControl.SetBounds -> thunk 0x004014F0;
                  TComboBox's +0x4C is TWinControl.SetBounds -> `call [0x00432300]` (IAT).
  TStrings        +0x2C SetTextStr, +0x18 GetObject (vanilla's id lookup)
  TComboBox       Items +0x118, Style +0x121, OnChange Code +0x150 / Data +0x154, from
                  vcl30.dpl's published RTTI.  `TCustomComboBox.Change @0x413511A4` calls
                  it Data in EAX, Sender in EDX.
  Every one of those slots, fields and IAT names is ASSERTED against vcl30.dpl / the
  import table on every run, so a direct call can never silently diverge from the
  virtual one.
  thunks          SetText 0x00401568, CB.SetItemIndex 0x00401A98, CB.GetItemIndex
                  0x00401A90, LB.GetItemIndex 0x00401AC0, TSpellControl.GetSpell 0x00401D28

LAYOUT                                          (client coordinates, DFM pixels)
      Label  "Caster:"   in GroupBox3   L16  T184  (37x13, AutoSize)   under "Upkeep:"
      Combo  Caster      in GroupBox3   L80  T176  W121 H21            SphereEdit's column
      GroupBox3          L120 T176 W217  H 185 -> 217   (bottom 361 -> 393)
      GroupBox4 SFX      T 368 -> 400
      GroupBox5 GFX      T 440 -> 472
      SpellInfoGroup     T 512 -> 544   (bottom 713 -> 745)
  ⚠ SpellInfoGroup's bottom was already below the 696 px design client height before
  this change; it now reaches 32 px further.

⚠ FORWARD HAZARDS
  * ⚠⚠ The cave depends on `.mtb` header state that build_deved_listarrows.py OWNS:
    VirtualSize 0x4C800 and Characteristics 0x60000040 (MEM_EXECUTE).  This script never
    writes either, and refuses to apply unless both are at listarrows' values.
    `build_deved_listarrows.py --undo` puts them back to 0x4C63B / 0x40000040, leaving this
    cave past VirtualSize in a non-executable section.  Undo THIS script first, or
    re-apply listarrows straight after.
  * `.mtb` 0x0052D6A0..0x0052D7FF is exclusive to this script.  `.mtb` has no free
    file-backed slack left (0x0052D63B..0x0052D63F, 5 B, is all).
  * ⚠ The 4 DFM values live in the LIVE TMAINFORM in `.ctp`.  Anything that rebuilds that
    copy from a master (only build_deved_terrainpal.py, and only after `.ctp` is deleted)
    reverts them; the combo row then sits clipped at the bottom of a 185 px group.  This
    script's dry run reports it and `--apply` repairs it.
  * G_COMBO/G_ID 0x004E0700..0x004E0707, `.dlgd` page slack.  build_dlgdirs.py owns
    PATHBUF 0x004E0400..0x004E051F, build_deved_gamesettings_tab.py owns 0x004E0520 and
    may move to 0x004E0630 "or later" if dlgdirs ever grows a DIRBUF; 0x004E0700 is clear.
  * build_deved_listarrows.py also patches SpellListBoxClick (0x0042BF94, one byte) --
    no overlap.  Keyboard: listarrows' `Application.OnMessage` gate passes arrow keys only
    to the two listboxes, so the new combo, like the vanilla Sphere combo, is mouse-driven.

⚠⚠ AFTER --apply OR --undo YOU MUST RUN `build_zigeditor.py --apply`
  This patches `AoWDevEd.exe`, the editor patch SOURCE.  The editor the owner runs is
  `AoWzEd.exe`, derived from it.

USAGE
    python build_scripts/build_deved_casterfamily.py            # dry run + verify
    python build_scripts/build_deved_casterfamily.py --dis      # + cave disassembly
    python build_scripts/build_deved_casterfamily.py --apply    # write (or re-tune in place)
    python build_scripts/build_deved_casterfamily.py --undo     # surgical revert

`--undo` restores the 4-byte call operand and the 4 DFM values and zeroes the 352-byte
cave reservation.  It touches no backup, no section header and no global.

Needs `pip install keystone-engine capstone`.
"""
import argparse
import os
import shutil
import struct
import sys

import zigexe

HERE = os.path.dirname(os.path.abspath(__file__))
# <game>/Ziggurat/Modding Resources/build_scripts/ -> two levels up is <game>/Ziggurat
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
RE_TOOLS = os.path.join(GAME, "Modding Resources", "re_tools")

EXE = zigexe.SRC_EDITOR                     # AoWDevEd.exe -- the PATCH SOURCE
LIVE = zigexe.LIVE_EDITOR                   # AoWzEd.exe   -- reported, never written
VCL = "vcl30.dpl"
IMAGE_BASE = 0x400000

BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP_SUFFIX = ".pre-casterfamily"

# ---- hook ---------------------------------------------------------------------------
HOOK = 0x0042C0B8
HOOK_ORIG = bytes.fromhex("E82B70FDFF")     # call 0x004030E8  TSpin.SetValue (tier row)

# ---- cave + globals ------------------------------------------------------------------
CAVE_VA = 0x0052D6A0
CAVE_END = 0x0052D800                       # exclusive; = .mtb's raw end
CAVE_LEN = CAVE_END - CAVE_VA
HOST = b".mtb"
HOST_VSZ = 0x0004C800                       # build_deved_listarrows.py's values -- REQUIRED
HOST_CHARS = 0x60000040

G_COMBO = 0x004E0700                        # .dlgd page slack, loader-zeroed
G_ID = 0x004E0704
GHOST = b".dlgd"

# ---- imported thunks (jmp dword ptr [iat]) and IAT cells --------------------------------
T_SETVALUE = 0x004030E8
T_SETTEXT = 0x00401568
T_CTL_SETBOUNDS = 0x004014F0
T_CB_SETIDX = 0x00401A98
T_CB_GETIDX = 0x00401A90
T_LB_GETIDX = 0x00401AC0
T_GETSPELL = 0x00401D28
THUNKS = {
    T_SETVALUE: "SpinEdit.TSpin.SetValue",
    T_SETTEXT: "Controls.TControl.SetText",
    T_CTL_SETBOUNDS: "Controls.TControl.SetBounds",
    T_CB_SETIDX: "StdCtrls.TCustomComboBox.SetItemIndex",
    T_CB_GETIDX: "StdCtrls.TCustomComboBox.GetItemIndex",
    T_LB_GETIDX: "StdCtrls.TCustomListBox.GetItemIndex",
    T_GETSPELL: "AoWE.TSpellControl.GetSpell",
}
IAT_TLABEL = 0x00432654
IAT_TCOMBO = 0x00432640
IAT_WC_SETBOUNDS = 0x00432300               # Controls.TWinControl.SetBounds, called [IAT]
IATS = {
    IAT_TLABEL: "StdCtrls..TLabel",
    IAT_TCOMBO: "StdCtrls..TComboBox",
    IAT_WC_SETBOUNDS: "Controls.TWinControl.SetBounds",
}

MAPVAR = 0x00432898                         # [[MAPVAR]] = the editor's map; +0x84 spells
MAP_SPELLS = 0x84

# ---- VMT slots / fields (asserted against vcl30.dpl) ---------------------------------
V_CREATE, V_SETPARENT, V_SETBOUNDS, V_SETSTYLE = 0x24, 0x3C, 0x4C, 0x88
V_STR_SETTEXTSTR = 0x2C
CB_ITEMS, CB_STYLE, CB_ONCHANGE = 0x118, 0x121, 0x150
CS_DROPDOWNLIST = 2

# ---- TMainForm (published field table 0x00425D92) -------------------------------------
F_SPELLLIST = 0x4DC
F_GROUPBOX3 = 0x4F8
SPELL_FAMILY = 0x23
N_FAMILIES = 5

# ---- layout ---------------------------------------------------------------------------
DY = 32                                     # GroupBox3's own row pitch
ROW_T = 16 + 5 * DY                         # 176: the sixth row
CB_X, CB_Y, CB_W, CB_H = 80, ROW_T, 121, 21         # SphereEdit's column and size
LBL_X, LBL_Y, LBL_W, LBL_H = 16, ROW_T + 8, 37, 13  # Label5 "Sphere:" is T24 against T16
CAP_LABEL = b"Caster:"
ITEMS = [b"None", b"Evoker", b"Conjurer", b"Enchanter", b"Ritualist"]
assert len(ITEMS) == N_FAMILIES

DFM_NAME = "TMAINFORM"
#: (object path, property, vanilla, ours) -- all vaInt16 before and after
DFM_EDITS = [
    ("/MainForm", "GroupBox3", "Height", 185, 185 + DY),
    ("/MainForm", "GroupBox4", "Top", 368, 368 + DY),
    ("/MainForm", "GroupBox5", "Top", 440, 440 + DY),
    ("/MainForm", "SpellInfoGroup", "Top", 512, 512 + DY),
]
SPELLS_PARENT = "/Panel9/"                  # every edited object is a child of Panel9


# ====================================================================================
# PE helpers
# ====================================================================================
def load_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[e:e + 4] == b"PE\0\0", "bad PE header"
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    secs = []
    for i in range(nsec):
        b = opt + optsz + i * 40
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append(dict(name=bytes(d[b:b + 8]).rstrip(b"\0"), va=va, vsz=vsz, raw=raw,
                         rsz=rsz, chars=struct.unpack_from("<I", d, b + 36)[0], hdr=b))
    return dict(opt=opt, secs=secs, imagebase=struct.unpack_from("<I", d, opt + 28)[0])


def va2off(F, va):
    """VA -> file offset, bounded by RAW size: an address in page slack past SizeOfRawData
    (G_COMBO) has no file bytes and is refused, never mapped onto the next section."""
    rva = va - F["imagebase"]
    for s in F["secs"]:
        if s["va"] <= rva < s["va"] + s["rsz"]:
            return s["raw"] + (rva - s["va"])
    raise ValueError("VA %#x has no raw file bytes" % va)


def section(F, name):
    s = [x for x in F["secs"] if x["name"] == name]
    assert len(s) == 1, "expected one %s section, found %d" % (name, len(s))
    return s[0]


def section_of(F, va):
    rva = va - F["imagebase"]
    for s in F["secs"]:
        if s["va"] <= rva < s["va"] + max(s["vsz"], s["rsz"]):
            return s["name"]
    return None


def iat_names(d, F):
    """{IAT cell VA: imported name without the @hash}."""
    ib = F["imagebase"]
    irva = struct.unpack_from("<I", d, F["opt"] + 96 + 8)[0]
    o = va2off(F, ib + irva)
    out = {}
    while True:
        ilt, _ts, _fc, name, iat = struct.unpack_from("<IIIII", d, o)
        o += 20
        if name == 0:
            return out
        t, i = ilt or iat, 0
        while True:
            e = struct.unpack_from("<I", d, va2off(F, ib + t) + 4 * i)[0]
            if e == 0:
                break
            if not e & 0x80000000:
                p = va2off(F, ib + e) + 2
                out[ib + iat + 4 * i] = bytes(d[p:d.index(b"\0", p)]).decode("latin1").split("@")[0]
            i += 1


def relocs(d, F):
    ib = F["imagebase"]
    rrva, rsz = struct.unpack_from("<II", d, F["opt"] + 96 + 5 * 8)
    o = va2off(F, ib + rrva)
    end, out = o + rsz, []
    while o < end:
        page, bs = struct.unpack_from("<II", d, o)
        if bs == 0:
            break
        for i in range((bs - 8) // 2):
            w = struct.unpack_from("<H", d, o + 8 + 2 * i)[0]
            if w >> 12:
                out.append(ib + page + (w & 0xFFF))
        o += bs
    return out


def find_rcdata(d, F, want_name):
    """RCDATA resource by name -> (data rva, size), walking the resource directory, so the
    LIVE copy is found wherever it has been relocated to."""
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
        if tname != 10 or not (tsub & 0x80000000):
            continue
        for rname, rsub in entries(base + (tsub & 0x7FFFFFFF)):
            if rname != want_name or not (rsub & 0x80000000):
                continue
            for _l, lsub in entries(base + (rsub & 0x7FFFFFFF)):
                assert not (lsub & 0x80000000), "unexpected 4th resource level"
                return struct.unpack_from("<II", d, base + lsub)
    raise SystemExit("resource RCDATA/%s not found" % want_name)


# ====================================================================================
# DFM walk -- every Delphi 3 value type, collections included (dfm_edit.py lacks 0x0E)
# ====================================================================================
class Dfm:
    def __init__(self, blob):
        self.D, self.o = blob, 4
        self.props = []                    # (object path, prop, type byte, value off, value)
        assert blob[:4] == b"TPF0", "not a DFM"
        self.obj("")
        assert self.o == len(blob), "DFM walk consumed %d of %d bytes" % (self.o, len(blob))

    def ss(self):
        n = self.D[self.o]
        s = self.D[self.o + 1:self.o + 1 + n].decode("latin1")
        self.o += 1 + n
        return s

    def val(self):
        D = self.D
        t = D[self.o]
        self.o += 1
        at = self.o
        if t == 0 or t in (8, 9, 13):
            return t, at, None
        if t == 1:
            while D[self.o] != 0:
                self.val()
            self.o += 1
            return t, at, None
        if t in (2, 3, 4):
            fmt, n = {2: ("<b", 1), 3: ("<h", 2), 4: ("<i", 4)}[t]
            self.o += n
            return t, at, struct.unpack_from(fmt, D, at)[0]
        if t == 5:
            self.o += 10
            return t, at, None
        if t in (6, 7):
            return t, at, self.ss()
        if t in (10, 12):
            self.o += 4 + struct.unpack_from("<I", D, self.o)[0]
            return t, at, None
        if t == 11:
            while self.ss():
                pass
            return t, at, None
        if t == 14:                                     # vaCollection
            while D[self.o] != 0:
                if D[self.o] in (2, 3, 4):              # optional item index
                    self.val()
                assert D[self.o] == 1, "collection item without vaList"
                self.o += 1
                while D[self.o] != 0:
                    self.ss()
                    self.val()
                self.o += 1
            self.o += 1
            return t, at, None
        raise ValueError("unknown DFM value type %d at %#x" % (t, at - 1))

    def obj(self, path):
        if (self.D[self.o] & 0xF0) == 0xF0:
            flags = self.D[self.o]
            self.o += 1
            if flags & 0x02:
                self.val()
        self.ss()
        here = path + "/" + self.ss()
        while self.D[self.o] != 0:
            p = self.ss()
            t, at, v = self.val()
            self.props.append((here, p, t, at, v))
        self.o += 1
        while self.D[self.o] != 0:
            self.obj(here)
        self.o += 1


def read_dfm(d, F):
    rva, size = find_rcdata(d, F, DFM_NAME)
    off = va2off(F, F["imagebase"] + rva)
    w = Dfm(bytes(d[off:off + size]))
    out = []
    for root, name, prop, van, ours in DFM_EDITS:
        hits = [p for p in w.props if p[0].startswith(root) and p[0].endswith(SPELLS_PARENT + name)
                and p[1] == prop]
        assert len(hits) == 1, "expected 1 %s.%s, found %d" % (name, prop, len(hits))
        _path, _p, t, at, v = hits[0]
        assert t == 3, "%s.%s is value type %d, not vaInt16" % (name, prop, t)
        assert -32768 <= ours <= 32767 and not (-128 <= ours <= 127), \
            "%s.%s = %d would not stay vaInt16" % (name, prop, ours)
        out.append(dict(what="%s.%s" % (name, prop), off=off + at, now=v, van=van, ours=ours))
    return rva, size, off, out


# ====================================================================================
# vcl30.dpl cross-check
# ====================================================================================
def check_vcl():
    """The direct calls and field offsets above are only equivalent to the virtual /
    RTTI-defined ones if vcl30.dpl says so.  Read its VMTs and RTTI and assert it."""
    sys.path.insert(0, RE_TOOLS)
    from pescan import PE
    pe = PE(os.path.join(GAME, VCL))
    d, ib = pe.data, pe.image_base
    ex = {n.split("@")[0]: a for n, a in pe.exports()}
    rev = {a: n for n, a in ex.items()}

    def slot(cls, off):
        return rev.get(struct.unpack_from("<I", d, pe.rva2off(ex[cls] + off))[0] - ib, "?")

    for cls, off, name in [
        ("StdCtrls..TLabel", V_CREATE, "StdCtrls.TCustomLabel.Create"),
        ("StdCtrls..TLabel", V_SETPARENT, "Controls.TControl.SetParent"),
        ("StdCtrls..TLabel", V_SETBOUNDS, "Controls.TControl.SetBounds"),
        ("StdCtrls..TComboBox", V_CREATE, "StdCtrls.TCustomComboBox.Create"),
        ("StdCtrls..TComboBox", V_SETPARENT, "Controls.TControl.SetParent"),
        ("StdCtrls..TComboBox", V_SETBOUNDS, "Controls.TWinControl.SetBounds"),
        ("StdCtrls..TComboBox", V_SETSTYLE, "StdCtrls.TCustomComboBox.SetStyle"),
        ("Classes..TStrings", V_STR_SETTEXTSTR, "Classes.TStrings.SetTextStr"),
        ("Classes..TStrings", 0x18, "Classes.TStrings.GetObject"),
    ]:
        got = slot(cls, off)
        assert got == name, "%s VMT +%#x is %s, expected %s" % (cls, off, got, name)

    tag = bytes([7, 9]) + b"TComboBox"             # tkClass RTTI, Delphi 3 layout
    at = d.find(tag)
    assert at >= 0, "no TComboBox RTTI in vcl30.dpl"
    p = at + len(tag) + 10
    p += 1 + d[p]
    n = struct.unpack_from("<H", d, p)[0]
    p += 2
    props = {}
    for _ in range(n):
        _pt, get, sett = struct.unpack_from("<III", d, p)
        p += 26
        props[d[p + 1:p + 1 + d[p]].decode("latin1")] = (get, sett)
        p += 1 + d[p]
    assert props["Items"][0] == 0xFF000000 | CB_ITEMS, "TComboBox.Items field moved"
    assert props["Style"] == (0xFF000000 | CB_STYLE, 0xFE000000 | V_SETSTYLE), \
        "TComboBox.Style field/setter moved"
    assert props["OnChange"][0] == 0xFF000000 | CB_ONCHANGE, "TComboBox.OnChange moved"
    # SetTextStr must stop at #0 and never read the StrRec length (lit_items has none)
    st = d[pe.rva2off(ex["Classes.TStrings.SetTextStr"]):][:0x60]
    assert bytes.fromhex("8a1384d2") in st and bytes.fromhex("80ea0a") in st, \
        "TStrings.SetTextStr no longer scans for #0/#10 the way lit_items assumes"


# ====================================================================================
# the cave
# ====================================================================================
def ansistring(text):
    """Delphi 3 immutable AnsiString literal: refcount -1, length, chars, NUL, pad to 4.
    The pointer handed over is blob + 8."""
    body = struct.pack("<iI", -1, len(text)) + text + b"\0"
    while len(body) % 4:
        body += b"\0"
    return body


def cave_source(lit_label, lit_items, change_va):
    getsp = f"""
    getsp:
        mov  eax, dword ptr [{MAPVAR:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + {MAP_SPELLS:#x}]
        jmp  {T_GETSPELL:#x}
"""
    change = f"""
    cave_change:
        mov  ecx, dword ptr [{MAPVAR:#x}]
        mov  ecx, dword ptr [ecx]
        jecxz c_ret
        push esi
        mov  esi, edx
        mov  eax, dword ptr [eax + {F_SPELLLIST:#x}]
        call {T_LB_GETIDX:#x}
        test eax, eax
        jl   c_out
        mov  edx, dword ptr [{G_ID:#x}]
        call getsp
        test eax, eax
        je   c_out
        xchg eax, esi
        call {T_CB_GETIDX:#x}
        test eax, eax
        jl   c_out
        mov  byte ptr [esi + {SPELL_FAMILY:#x}], al
    c_out:
        pop  esi
    c_ret:
        ret
"""
    mk = f"""
    mk:
        xor  ecx, ecx
        mov  dl, 1
        call dword ptr [eax + {V_CREATE:#x}]
        push eax
        mov  edx, dword ptr [ebx + {F_GROUPBOX3:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETPARENT:#x}]
        pop  eax
        ret
"""
    load = f"""
    cave_load:
        call {T_SETVALUE:#x}
        push edi
        mov  edi, dword ptr [{G_COMBO:#x}]
        test edi, edi
        je   l_build
    l_have:
        mov  dword ptr [{G_ID:#x}], esi
        mov  edx, esi
        call getsp
        test eax, eax
        je   l_done
        movzx edx, byte ptr [eax + {SPELL_FAMILY:#x}]
        cmp  edx, {N_FAMILIES - 1}
        jbe  l_set
        or   edx, 0xffffffff
    l_set:
        mov  eax, edi
        call {T_CB_SETIDX:#x}
    l_done:
        pop  edi
        ret
    l_build:
        cmp  dword ptr [ebx + {F_GROUPBOX3:#x}], 0
        je   l_done
        mov  eax, dword ptr [{IAT_TLABEL:#x}]
        call mk
        push eax
        mov  edx, {lit_label:#x}
        call {T_SETTEXT:#x}
        pop  eax
        push {LBL_X}
        pop  edx
        mov  ecx, {LBL_Y}
        push {LBL_W}
        push {LBL_H}
        call {T_CTL_SETBOUNDS:#x}
        mov  eax, dword ptr [{IAT_TCOMBO:#x}]
        call mk
        mov  edi, eax
        mov  dl, {CS_DROPDOWNLIST}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETSTYLE:#x}]
        mov  eax, edi
        push {CB_X}
        pop  edx
        mov  ecx, {CB_Y}
        push {CB_W}
        push {CB_H}
        call dword ptr [{IAT_WC_SETBOUNDS:#x}]
        mov  eax, dword ptr [edi + {CB_ITEMS:#x}]
        mov  edx, {lit_items:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_STR_SETTEXTSTR:#x}]
        mov  dword ptr [edi + {CB_ONCHANGE:#x}], {change_va:#x}
        mov  dword ptr [edi + {CB_ONCHANGE + 4:#x}], ebx
        mov  dword ptr [{G_COMBO:#x}], edi
        jmp  l_have
"""
    return getsp + change + mk + load


def build_cave(ks):
    label = ansistring(CAP_LABEL)
    lit_label = CAVE_VA + 8
    code_va = CAVE_VA + len(label)
    items = b"\n".join(ITEMS) + b"\0"
    # two passes: sizes first (placeholder addresses), then the real ones
    src = cave_source(lit_label, CAVE_END - 1, code_va + 0x7F)
    enc, _ = ks.asm(src, code_va)
    code_len = len(enc)
    lit_items = code_va + code_len
    # entry offsets: assemble prefixes to find where each label lands
    change_va = code_va + len(ks.asm(src.split("    cave_change:")[0], code_va)[0])
    src = cave_source(lit_label, lit_items, change_va)
    code = bytes(ks.asm(src, code_va)[0])
    assert len(code) == code_len, "cave size changed between passes"
    ents = {}
    for nm in ("getsp", "cave_change", "mk", "cave_load"):
        ents[nm] = code_va + len(ks.asm(src.split("    %s:" % nm)[0], code_va)[0]) \
            if src.split("    %s:" % nm)[0].strip() else code_va
    assert ents["cave_change"] == change_va
    blob = label + code + items
    assert len(blob) <= CAVE_LEN, "cave needs %d B, reservation is %d B" % (len(blob), CAVE_LEN)
    cave = blob + b"\0" * (CAVE_LEN - len(blob))
    return cave, ents, len(blob), code_va, code_len, dict(label=lit_label, items=lit_items)


def check_cave(cave, ents, code_va, code_len):
    """Read the bytes BACK (the keystone `push 0xFFFF` -> imm8 trap is silent)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    code = cave[code_va - CAVE_VA:code_va - CAVE_VA + code_len]
    ins = list(cs.disasm(code, code_va))
    assert sum(i.size for i in ins) == code_len, "cave does not disassemble end to end"
    starts = {i.address for i in ins}
    for v in ents.values():
        assert v in starts, "entry %#x is not an instruction boundary" % v
    imm = [int(i.op_str, 0) for i in ins if i.mnemonic == "push" and i.op_str[0].isdigit()]
    want = [LBL_X, LBL_W, LBL_H, CB_X, CB_W, CB_H]
    assert imm == want, "push immediates decoded as %r, expected %r" % (imm, want)
    movs = [i.op_str for i in ins if i.mnemonic == "mov" and i.op_str.startswith("ecx, 0x")]
    assert movs == ["ecx, %#x" % LBL_Y, "ecx, %#x" % CB_Y], "Top immediates are %r" % movs
    assert sum(1 for i in ins if i.mnemonic == "ret") == 3, "expected exactly 3 rets"
    for i in ins:
        if not i.op_str.startswith("0x"):
            continue
        t = int(i.op_str, 16)
        if i.mnemonic in ("call", "jmp") and not (CAVE_VA <= t < CAVE_END):
            assert t in THUNKS, "%s at %#x to %#x is not a known thunk" % (i.mnemonic, i.address, t)
        elif i.mnemonic == "call" or i.mnemonic.startswith("j"):
            assert t in starts, "%s at %#x lands mid-instruction (%#x)" % (i.mnemonic, i.address, t)
    wired = [i for i in ins if i.op_str == "dword ptr [edi + 0x150], %#x" % ents["cave_change"]]
    assert len(wired) == 1, "OnChange.Code is not wired to cave_change"


def disassemble(cave, ents, used, code_va, code_len, lits):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    print("  %08X  %s  AnsiString %r" % (CAVE_VA, cave[:16].hex(" "), CAP_LABEL.decode()))
    labels = {va: nm for nm, va in ents.items()}
    for i in cs.disasm(cave[code_va - CAVE_VA:code_va - CAVE_VA + code_len], code_va):
        mark = "    <<< %s" % labels[i.address] if i.address in labels else ""
        print("  %08X  %-24s %-6s %s%s" % (i.address, i.bytes.hex(" "), i.mnemonic,
                                          i.op_str, mark))
    o = lits["items"] - CAVE_VA
    print("  %08X  lit_items %r (%d B)" % (lits["items"], cave[o:used], used - o))


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
    ap.add_argument("--apply", action="store_true", help="write the patch / re-tune in place")
    ap.add_argument("--undo", action="store_true", help="surgical revert")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the cave")
    args = ap.parse_args()
    if args.apply and args.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    cave, ents, used, code_va, code_len, lits = build_cave(Ks(KS_ARCH_X86, KS_MODE_32))
    check_cave(cave, ents, code_va, code_len)
    check_vcl()

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)
    assert F["imagebase"] == IMAGE_BASE, "ImageBase moved to %#x" % F["imagebase"]

    # --- host sections ---------------------------------------------------------------
    mtb = section(F, HOST)
    assert IMAGE_BASE + mtb["va"] + mtb["rsz"] == CAVE_END, \
        ".mtb raw data no longer ends at %#x" % CAVE_END
    host_ok = mtb["vsz"] == HOST_VSZ and mtb["chars"] == HOST_CHARS
    dlgd = section(F, GHOST)
    assert dlgd["chars"] & 0xC0000000 == 0xC0000000, ".dlgd is not read/write"
    assert dlgd["va"] + max(dlgd["vsz"], dlgd["rsz"]) <= G_COMBO - IMAGE_BASE, \
        "G_COMBO %#x is inside .dlgd's declared bytes" % G_COMBO
    nxt = min(s["va"] for s in F["secs"] if s["va"] > dlgd["va"])
    assert G_ID + 4 - IMAGE_BASE <= nxt and G_ID + 4 - IMAGE_BASE <= dlgd["va"] + 0x1000, \
        "the globals are not in .dlgd's own page"
    for g in (G_COMBO, G_ID):
        try:
            va2off(F, g)
            raise SystemExit("global %#x unexpectedly has file bytes" % g)
        except ValueError:
            pass

    # --- imports, thunks, relocs -----------------------------------------------------
    names = iat_names(d, F)
    for iat, nm in IATS.items():
        assert names.get(iat) == nm, "IAT %#x is %r, expected %r" % (iat, names.get(iat), nm)
    for thunk, nm in THUNKS.items():
        o = va2off(F, thunk)
        iat = struct.unpack_from("<I", d, o + 2)[0]
        assert d[o:o + 2] == b"\xFF\x25" and names.get(iat) == nm, \
            "thunk %#x is not jmp [%s]" % (thunk, nm)
    rl = relocs(d, F)

    # --- DFM ---------------------------------------------------------------------------
    dfm_rva, dfm_size, dfm_off, dfm = read_dfm(d, F)
    dfm_sect = section_of(F, IMAGE_BASE + dfm_rva)
    for lo, hi, what in ((HOOK - 3, HOOK + 5, "hook operand"), (CAVE_VA - 3, CAVE_END, "cave"),
                         (IMAGE_BASE + dlgd["va"], IMAGE_BASE + dlgd["va"] + 0x1000, ".dlgd"),
                         (IMAGE_BASE + dfm_rva - 3, IMAGE_BASE + dfm_rva + dfm_size, "TMAINFORM")):
        bad = [hex(r) for r in rl if lo <= r < hi]
        assert not bad, ".reloc fixups inside the %s: %s" % (what, bad)

    # --- state -----------------------------------------------------------------------
    hoff = va2off(F, HOOK)
    hook_now = bytes(d[hoff:hoff + 5])
    hook_new = b"\xE8" + struct.pack("<i", ents["cave_load"] - (HOOK + 5))
    hook_orig = hook_now == HOOK_ORIG
    hook_ours = False
    if hook_now[:1] == b"\xE8":
        t = HOOK + 5 + struct.unpack("<i", hook_now[1:])[0]
        hook_ours = CAVE_VA <= t < CAVE_END
    coff = va2off(F, CAVE_VA)
    cave_now = bytes(d[coff:coff + CAVE_LEN])
    cave_blank = not any(cave_now)
    cave_current = cave_now == cave
    dfm_van = sum(1 for f in dfm if f["now"] == f["van"])
    dfm_ours = sum(1 for f in dfm if f["now"] == f["ours"])
    installed = hook_now == hook_new and cave_current and dfm_ours == len(dfm)

    print("\n[%s] %d bytes   cave %#010x..%#010x (file %#08x), G_COMBO %#010x, G_ID %#010x"
          % (EXE, len(d), CAVE_VA, CAVE_END - 1, coff, G_COMBO, G_ID))
    print("     %d B used of %d reserved (%d spare): %d B label literal, %d B code, "
          "%d B item list" % (used, CAVE_LEN, CAVE_LEN - used, code_va - CAVE_VA, code_len,
                              used - (code_va - CAVE_VA) - code_len))
    for nm, va in ents.items():
        print("       %-12s %#010x" % (nm, va))
    print("     hook %#010x  %s -> %s  [%s]" % (
        HOOK, hook_now.hex(), hook_new.hex(),
        "VANILLA" if hook_orig else ("OURS" if hook_ours else "*** FOREIGN ***")))
    print("     cave: %s" % ("blank" if cave_blank else "installed, current" if cave_current
                             else "non-zero, NOT this build (%d non-zero bytes)"
                             % sum(1 for b in cave_now if b)))
    print("     .mtb VirtualSize %#x chars %#x  [%s]" % (
        mtb["vsz"], mtb["chars"], "listarrows state, OK" if host_ok else
        "*** NOT build_deved_listarrows.py's %#x/%#x ***" % (HOST_VSZ, HOST_CHARS)))
    print("     RCDATA/%s live copy: rva %#x (%s), %#x B, file %#08x -- %d/%d vanilla, %d/%d ours"
          % (DFM_NAME, dfm_rva, (dfm_sect or b"?").decode(), dfm_size, dfm_off,
             dfm_van, len(dfm), dfm_ours, len(dfm)))
    for f in dfm:
        print("       file %#08x  %-22s %4d -> %4d  [%s]" % (
            f["off"], f["what"], f["now"], f["ours"],
            "vanilla" if f["now"] == f["van"] else "OURS" if f["now"] == f["ours"]
            else "*** FOREIGN ***"))
    livep = os.path.join(GAME, LIVE)
    if os.path.exists(livep):
        ld = open(livep, "rb").read()
        LF = load_sections(ld)
        lo, lc = va2off(LF, HOOK), va2off(LF, CAVE_VA)
        _r, _s, _o, ldfm = read_dfm(ld, LF)
        print("     [%s, read-only] hook %s, cave %s, DFM %d/%d ours" % (
            LIVE, "OURS" if ld[lo:lo + 5] == hook_new else
            ("VANILLA" if ld[lo:lo + 5] == HOOK_ORIG else ld[lo:lo + 5].hex()),
            "current" if ld[lc:lc + CAVE_LEN] == cave else
            ("blank" if not any(ld[lc:lc + CAVE_LEN]) else "OTHER"),
            sum(1 for f in ldfm if f["now"] == f["ours"]), len(ldfm)))

    if args.dis:
        print("\n---- cave disassembly ----")
        disassemble(cave, ents, used, code_va, code_len, lits)

    for f in dfm:
        assert f["now"] in (f["van"], f["ours"]), "%s is %d, neither vanilla %d nor ours %d" \
            " - ABORT" % (f["what"], f["now"], f["van"], f["ours"])
    assert hook_orig or hook_ours, "hook %#x holds foreign bytes %s - ABORT" % (HOOK, hook_now.hex())
    if not hook_ours:
        assert cave_blank, "cave is dirty but the hook does not point at it - ABORT"

    # ================================ undo =========================================
    if args.undo:
        if hook_orig and cave_blank and dfm_van == len(dfm):
            print("\n[%s] not applied - no-op" % EXE)
            return 0
        d[hoff:hoff + 5] = HOOK_ORIG
        d[coff:coff + CAVE_LEN] = b"\0" * CAVE_LEN
        for f in dfm:
            struct.pack_into("<h", d, f["off"], f["van"])
        write(path, d)                                  # NO snapshot on --undo, ever
        print("\n[%s] UNDONE: hook %#x restored, %d cave bytes zeroed, %d DFM values back to "
              "vanilla. No backup touched." % (EXE, HOOK, CAVE_LEN, len(dfm)))
        print("     !!!! NOW RUN: python build_scripts/build_zigeditor.py --apply")
        return 0

    # ============================== verify / apply ==================================
    if installed and host_ok:
        print("\n[%s] already patched and up to date - chain intact." % EXE)
        return 0
    if not host_ok:
        raise SystemExit(
            "\n.mtb header is not build_deved_listarrows.py's applied state; this cave needs "
            "its VirtualSize %#x + MEM_EXECUTE.  Apply build_deved_listarrows.py first."
            % HOST_VSZ)
    if not args.apply:
        print("\n  DRY RUN -- nothing written. Re-run with --apply.")
        return 0

    pristine = hook_orig and cave_blank and dfm_van == len(dfm)
    backup = os.path.join(BACKUP_DIR, EXE + BACKUP_SUFFIX)
    if pristine and not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print("\n    backup -> %s   (hook vanilla, cave blank, DFM values vanilla)" % backup)
    elif not pristine:
        print("\n    re-tune / repair over an existing install - NO snapshot minted")
    else:
        print("\n    snapshot already exists - left alone: %s" % backup)

    d[coff:coff + CAVE_LEN] = cave
    for f in dfm:
        struct.pack_into("<h", d, f["off"], f["ours"])
    d[hoff:hoff + 5] = hook_new
    write(path, d)
    print("[%s] APPLIED: %d B cave at %#010x, hook %#x -> cave_load %#010x, %d DFM values."
          % (EXE, used, CAVE_VA, HOOK, ents["cave_load"], len(dfm)))
    print("     !!!! NOW RUN: python build_scripts/build_zigeditor.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
