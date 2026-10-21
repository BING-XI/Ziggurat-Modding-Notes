#!/usr/bin/env python3
r"""
ABILITY LISTS IN CATEGORY COLUMNS   (AoWDevEd.exe -> AoWzEd.exe)

Owner's request 2026-10-20: wherever the editor lists all abilities, split them the way the hero
level-up dialog does -- Wayfaring, Resistances, Melee, Ranged, Magic -- plus a sixth column,
Effects, for statuses and spell effects (owner's choice), shown only where they can occur.

    Ability Editor (TAbilitySelectionDlg: Unit Properties, Hero Resource, Item Properties)
        the Available list becomes side-by-side columns with headings; the dialog grows
    Hero Properties (THeroEditForm)
        the same columns, to the right of the Stats page at its full height; the form grows
    Settings > Abilities (TMainForm, the 124-px list in the right-hand panel)
        no room for columns: the one list is regrouped under headings ("— Melee —"),
        alphabetical within each; a heading is never left selected

THE CATEGORY TABLE  (256 bytes, CATTBL, id -> 0..5; other ids -> Magic)
    herodlg_cats.ABILITY_CATS (the in-game level-up's own table) first, then EXTRA below for the
    ids the level-up never offers.  Editing either changes nothing until this script is re-run
    with --undo then --apply.

COLUMNS (Ability Editor, Hero Properties) -- the vanilla list stays as a hidden MASTER, so every
vanilla routine still fills it, reads its ItemIndex and runs its OnClick unchanged:
    col_build  once per form: one TLabel + one TListBox per column (AOwner = the form, Parent =
               the master's parent, Color = the master's), chained through Tag: master.Tag ->
               column 0, column k.Tag -> column k+1.  Column OnClick = (col_click, master).
               Effects is a column only when some Effects ability passes the owner's selection
               mask (eff_possible); otherwise none can be listed.
    col_sync   after every master fill: each master row i goes to its category's column with
               object i.  Selection: the column and row last clicked in this master (globals),
               clamped -- so after Add/Delete it stays in the column being worked in -- else the
               master's own selection, mirrored.
    col_click  selects master row = the clicked row's object, clears the other columns, calls the
               master's OnClick (vanilla: enables Add).
SETTINGS > ABILITIES -- the real list is regrouped, so build_deved_listarrows.py's arrow keys
    (keyed on this listbox's handle) keep working:
    set_fill   ListAbilities with Sorted on (alphabetical), copy to a TStringList, Sorted off,
               refill: a heading (object HDR_OBJ) before each non-empty category, then its entries.
               TCustomListBox.SetSorted is not imported: VCL30 is reached by the rebase delta
               [IAT GetItemIndex] - link(GetItemIndex) + link(SetSorted / SetColor).
    set_click  at AbilityListBoxClick's entry, so every caller is covered: a heading row moves
               the selection one row down, or one row up when the previous selection was the
               row below it (Up arrow); then the displaced prologue and the original body.

HOOKS
    A  0x00410094  TAbilitySelectionDlg VMT +0x80 (Available fill) 0x004102D4 -> dlg_fill
    B  0x00413F00  THeroEditForm VMT +0x80 (Available fill) 0x00414BBC -> hero_fill
    C1 0x0042A624  HSSEditActivate's `call ListAbilities` -> set_fill (operand only)
    C2 0x0042C33C  AbilityListBoxClick entry, 6 B `push ebp / mov ebp,esp / add esp,-14h` ->
                   jmp set_click + nop
    A and B keep their .reloc entries (new values are in the image).  Audited each run: no
    .reloc entry in C1, C2 or the cave; no branch into C2's interior.
    code   0x0050E400 .. 0x0050EFFF  `.mtb`, inside the DEAD TMAINFORM DFM master (file
           0x109A00), directly above build_deved_medalfilter.py's window.  No `TPF0`, no
           `MaxValue`; original bytes embedded, --undo restores them.  Needs `.mtb` executable
           (build_deved_listarrows.py).
    data   .tres page slack 0x00592F10 G_LASTM, 0x00592F14 G_LASTK, 0x00592F18 G_LASTR,
           0x00592F1C G_SETPREV (RWX, loader-zeroed, not file-backed).
    roll   NONE.

Couplings: build_deved_medalfilter.py's hooks sit inside the dialog fill this wraps (F1/F2) and
on AddBtnClick; neither touches the other's bytes.  build_deved_listarrows.py must stay applied
(`.mtb` execute bit).  The Settings list's heading rows carry object HDR_OBJ (0x7FFFFFFF): any future code that
walks AbilityListBox.Items must skip them.

    python build_scripts/build_deved_abcolumns.py            dry run + state
    python build_scripts/build_deved_abcolumns.py --apply    then: build_zigeditor.py --apply
    python build_scripts/build_deved_abcolumns.py --undo     then: build_zigeditor.py --apply
    python build_scripts/build_deved_abcolumns.py --dis
"""
import argparse, base64, hashlib, os, struct, subprocess, sys, zlib

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
import zigexe                       # noqa: E402
import herodlg_cats as HC           # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(GAME, zigexe.SRC_EDITOR)
LIVE = os.path.join(GAME, zigexe.LIVE_EDITOR)
BASE = 0x00400000

CAVE, CAVE_END, CAVE_FILE = 0x0050E400, 0x0050F000, 0x00109A00
WIN_SHA = "c4c271bba143eebc"
WIN_ORIG_B64 = (
    "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")
G_LASTM, G_LASTK, G_LASTR, G_SETPREV = 0x00592F10, 0x00592F14, 0x00592F18, 0x00592F1C

# ---- categories -------------------------------------------------------------------------------
CATEGORIES = HC.CATEGORIES + ["Effects"]
EFFECTS = len(HC.CATEGORIES)
EXTRA = {   # ids the level-up table never needed; placed by kinship (2026-10-20)
    23: 0, 26: 0, 50: 0, 159: 0,                         # Sailing, Mantle of Gloom, Transport, Path of Sand
    179: 1, 180: 1, 181: 1, 182: 1, 183: 1, 184: 1, 185: 1, 186: 1,   # the Weaknesses, Liquid Body
    56: 2, 63: 2, 65: 2, 170: 2,                         # Assassin, Dragon, Self Destruct, Magebane
    60: 4, 171: 4, 172: 4, 173: 4, 174: 4, 175: 4,       # Dispel Magic, Drillmaster, the casters
    # Effects: statuses and spell enchantments
    **{i: EFFECTS for i in (34, 48, 53, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 107, 108, 126,
                            127, 128, 129, 130, 131, 132, 136, 137, 149, 150, 152, 153, 154, 155,
                            156, 157, 158, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 178,
                            187, 188)},
}
assert not set(EXTRA) & set(HC.ABILITY_CATS), "EXTRA re-places a level-up id"


def cat_table():
    t = bytearray(HC.lookup_table())
    for aid, c in EXTRA.items():
        t[aid] = c
    return bytes(t)


# ---- editor addresses (thunks verified against the import table on every run) -----------------
TH = {"GetItemIndex": (0x00401AC0, "StdCtrls.TCustomListBox.GetItemIndex"),
      "SetItemIndex": (0x00401AC8, "StdCtrls.TCustomListBox.SetItemIndex"),
      "GetCount": (0x00401C10, "AoWE.TAbilityControl.GetCount"),
      "GetAbility": (0x00401C18, "AoWE.TAbilityControl.GetAbility"),
      "ListAbilities": (0x00401C20, "AoWE.TAbilityControl.ListAbilities"),
      "ObjCreate": (0x00401038, "System.TObject.Create"),
      "ObjFree": (0x00401040, "System.TObject.Free"),
      "LStrClr": (0x004010B0, "System.@LStrClr"),
      "SetText": (0x00401568, "Controls.TControl.SetText")}
IAT = {"SetVisible": (0x004323A8, "Controls.TControl.SetVisible"),
       "SetLeft": (0x004323D0, "Controls.TControl.SetLeft"),
       "SetTop": (0x004323CC, "Controls.TControl.SetTop"),
       "BeginUpdate": (0x004324F4, "Classes.TStrings.BeginUpdate"),
       "EndUpdate": (0x004324F0, "Classes.TStrings.EndUpdate"),
       "IndexOfObject": (0x004324EC, "Classes.TStrings.IndexOfObject"),
       "GetItemIndexVCL": (0x004325C8, "StdCtrls.TCustomListBox.GetItemIndex"),
       "TListBox": (0x00432630, "StdCtrls..TListBox"),
       "TLabel": (0x00432654, "StdCtrls..TLabel"),
       "TStringList": (0x00432518, "Classes..TStringList")}
VCL_LINK = {"StdCtrls.TCustomListBox.GetItemIndex": 0x413522F0,
            "StdCtrls.TCustomListBox.SetSorted": 0x4135252C,
            "Controls.TControl.SetColor": 0x4134221C}
D_SETSORTED = VCL_LINK["StdCtrls.TCustomListBox.SetSorted"] - VCL_LINK["StdCtrls.TCustomListBox.GetItemIndex"]
D_SETCOLOR = VCL_LINK["Controls.TControl.SetColor"] - VCL_LINK["StdCtrls.TCustomListBox.GetItemIndex"]
HSSET_CELL = 0x00432898

# VCL30 instance layout (RTTI / disassembly): TComponent Owner +4, Tag +0xC; TControl Parent +0x24,
# Left/Top/Width/Height +0x30..+0x3C, Color +0x54, OnClick +0xA4 code / +0xA8 data; TListBox
# Items +0x118.  VMT: constructor +0x24, SetParent +0x3C, SetBounds +0x4C.  TStrings VMT: Assign
# +0x8, Get +0xC, Count +0x14, GetObject +0x18, AddObject +0x38, Clear +0x40.
O_OWNER, O_TAG, O_PARENT, O_LEFT, O_TOP, O_W, O_H, O_COLOR = 4, 0xC, 0x24, 0x30, 0x34, 0x38, 0x3C, 0x54
O_ONCLICK, O_ITEMS = 0xA4, 0x118

# forms
DLG = dict(fill=0x004102D4, slot=0x00410094, master=0x204, sel=0x200, hdr=0x208, add=0x1F8,
           delete=0x1FC, sheet=0x1F4, client=0x1EC, ok=0x1E4, cancel=0x1E8, owner=0x214)
HERO = dict(fill=0x00414BBC, slot=0x00413F00, master=0x32C, hdr=0x330, client=0x1E8, ok=0x1E0,
            cancel=0x1E4, owner=0x384)
SET_LIST = 0x4A0
SET_CALL, SET_CLICK, SET_CLICK_BODY = 0x0042A624, 0x0042C33C, 0x0042C342
# Geometry is read off the live controls, so a control another script has moved stays in step.  A
# column is as wide as the vanilla Available list, Effects a quarter wider; the dialog's lists
# become DLG_TALL times the vanilla height.
GAP, DLG_TALL = 4, 3
# A Settings heading row's item data.  ⚠ Never -1: TListBoxStrings.GetObject reads LB_GETITEMDATA
# and raises "List index out of bounds" when the data equals LB_ERR (-1), so a -1 heading made
# every mapset load fail with "Error loading ..." (2026-10-20).
HDR_OBJ = 0x7FFFFFFF

HOOKS = {   # name: (va, original bytes as read off the binary)
    "A": (DLG["slot"], struct.pack("<I", DLG["fill"])),
    "B": (HERO["slot"], struct.pack("<I", HERO["fill"])),
    "C1": (SET_CALL, bytes.fromhex("e8f775fdff")),
    "C2": (SET_CLICK, bytes.fromhex("558bec83c4ec")),
}
INTERIOR = ("C2",)


def asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


def lstr(s):
    raw = s.encode("cp1252")
    blob = b"\xff\xff\xff\xff" + struct.pack("<I", len(raw)) + raw + b"\0"
    return blob + b"\0" * (-len(blob) % 4)


class Layout:
    def __init__(self):
        self.va, self.parts, self.sym = CAVE, [], {}

    def add(self, name, blob, align=16):
        self.sym[name] = self.va
        self.parts.append((name, self.va, blob))
        self.va = (self.va + len(blob) + align - 1) & ~(align - 1)

    def blob(self):
        out = bytearray()
        for _n, va, b in self.parts:
            out += b"\xcc" * (va - CAVE - len(out)) + b
        assert CAVE + len(out) <= CAVE_END, "cave overflows its window"
        return bytes(out)


def build():
    L = Layout()
    t = {k: v[0] for k, v in TH.items()}
    i = {k: v[0] for k, v in IAT.items()}
    L.add("cattbl", cat_table())
    hdr = []
    for c in CATEGORIES:
        L.add("lit:" + c, lstr(c), 4)
        hdr.append(L.sym["lit:" + c] + 8)
    hdr2 = []
    for c in CATEGORIES:
        L.add("lit2:" + c, lstr("— %s —" % c), 4)
        hdr2.append(L.sym["lit2:" + c] + 8)
    L.add("hdrs", b"".join(struct.pack("<I", v) for v in hdr), 4)
    L.add("hdrs2", b"".join(struct.pack("<I", v) for v in hdr2))
    TBL, HDRS, HDRS2 = L.sym["cattbl"], L.sym["hdrs"], L.sym["hdrs2"]
    ABCTL = f"""
        mov  eax, dword ptr [{HSSET_CELL:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x80]"""

    # ---- cat_of: EAX = ability id -> EAX = category ------------------------------------------
    L.add("cat_of", asm(f"""
        cmp  eax, 0xff
        ja   dflt
        movzx eax, byte ptr [{TBL:#x} + eax]
        ret
    dflt:
        mov  eax, {HC.DEFAULT_CAT}
        ret
    """, L.va))
    cat_of = L.sym["cat_of"]

    # ---- vsetbounds: virtual SetBounds; EAX = control, EDX = L, ECX = T, pushed W then H --------
    L.add("vsetbounds", asm("""
        push eax
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x4c]
        xchg eax, dword ptr [esp]
        ret
    """, L.va))
    vsb = L.sym["vsetbounds"]

    # ---- col_at: EAX = master, EDX = k -> EAX = column k (chain walk) ---------------------------
    L.add("col_at", asm(f"""
        mov  eax, dword ptr [eax + {O_TAG:#x}]
    walk:
        test edx, edx
        je   done
        test eax, eax
        je   done
        mov  eax, dword ptr [eax + {O_TAG:#x}]
        dec  edx
        jmp  walk
    done:
        ret
    """, L.va))
    col_at = L.sym["col_at"]

    # ---- select_in: EAX = master, EDX = column, ECX = row --------------------------------------
    L.add("select_in", asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        mov  edi, edx
        mov  ebp, ecx
        mov  esi, dword ptr [ebx + {O_TAG:#x}]
    each:
        test esi, esi
        je   master
        or   edx, -1
        cmp  esi, edi
        jne  set
        mov  edx, ebp
    set:
        mov  eax, esi
        call {t['SetItemIndex']:#x}
        mov  esi, dword ptr [esi + {O_TAG:#x}]
        jmp  each
    master:
        or   edx, -1
        test edi, edi
        je   setm
        test ebp, ebp
        jl   setm
        mov  edx, ebp
        mov  eax, dword ptr [edi + {O_ITEMS:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x18]
        mov  edx, eax
    setm:
        mov  eax, ebx
        call {t['SetItemIndex']:#x}
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    select_in = L.sym["select_in"]

    # ---- col_click: EAX = master (event Data), EDX = the column (Sender) ------------------------
    L.add("col_click", asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  eax, esi
        call {t['GetItemIndex']:#x}
        test eax, eax
        jl   out
        mov  edi, eax
        xor  ecx, ecx
        mov  eax, dword ptr [ebx + {O_TAG:#x}]
    find:
        test eax, eax
        je   out
        cmp  eax, esi
        je   found
        mov  eax, dword ptr [eax + {O_TAG:#x}]
        inc  ecx
        jmp  find
    found:
        mov  dword ptr [{G_LASTM:#x}], ebx
        mov  dword ptr [{G_LASTK:#x}], ecx
        mov  dword ptr [{G_LASTR:#x}], edi
        mov  eax, ebx
        mov  edx, esi
        mov  ecx, edi
        call {select_in:#x}
        mov  ecx, dword ptr [ebx + {O_ONCLICK:#x}]
        test ecx, ecx
        je   out
        mov  eax, dword ptr [ebx + {O_ONCLICK + 4:#x}]
        mov  edx, ebx
        call ecx
    out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    col_click = L.sym["col_click"]

    # ---- col_build: EAX = master, EDX = x0, ECX = ncols; stack (pushed last to first):
    #      [ebp+8] label top, [ebp+12] list top, [ebp+16] colw, [ebp+20] last colw, [ebp+24] height
    L.add("col_build", asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x14
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  dword ptr [ebp - 4], edx
        mov  dword ptr [ebp - 8], ecx
        mov  dword ptr [{G_LASTM:#x}], 0
        lea  esi, [ebx + {O_TAG:#x}]
        xor  edi, edi
    next:
        cmp  edi, dword ptr [ebp - 8]
        jae  done
        mov  eax, dword ptr [ebp - 8]
        dec  eax
        cmp  edi, eax
        mov  eax, dword ptr [ebp + 16]
        jne  have_w
        mov  eax, dword ptr [ebp + 20]
    have_w:
        mov  dword ptr [ebp - 12], eax
        mov  ecx, dword ptr [ebx + {O_OWNER:#x}]
        mov  dl, 1
        mov  eax, dword ptr [{i['TLabel']:#x}]
        call dword ptr [eax + 0x24]
        mov  dword ptr [ebp - 16], eax
        mov  edx, dword ptr [ebx + {O_PARENT:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x3c]
        push dword ptr [ebp - 12]
        mov  eax, dword ptr [ebp + 12]
        sub  eax, dword ptr [ebp + 8]
        push eax
        mov  edx, dword ptr [ebp - 4]
        mov  ecx, dword ptr [ebp + 8]
        mov  eax, dword ptr [ebp - 16]
        call {vsb:#x}
        mov  edx, dword ptr [{HDRS:#x} + edi*4]
        mov  eax, dword ptr [ebp - 16]
        call {t['SetText']:#x}
        mov  ecx, dword ptr [ebx + {O_OWNER:#x}]
        mov  dl, 1
        mov  eax, dword ptr [{i['TListBox']:#x}]
        call dword ptr [eax + 0x24]
        mov  dword ptr [ebp - 16], eax
        mov  dword ptr [esi], eax
        lea  esi, [eax + {O_TAG:#x}]
        mov  edx, dword ptr [ebx + {O_PARENT:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x3c]
        push dword ptr [ebp - 12]
        push dword ptr [ebp + 24]
        mov  edx, dword ptr [ebp - 4]
        mov  ecx, dword ptr [ebp + 12]
        mov  eax, dword ptr [ebp - 16]
        call {vsb:#x}
        mov  edx, dword ptr [ebx + {O_COLOR:#x}]
        mov  eax, dword ptr [ebp - 16]
        mov  ecx, dword ptr [{i['GetItemIndexVCL']:#x}]
        add  ecx, {D_SETCOLOR}
        call ecx
        mov  eax, dword ptr [ebp - 16]
        mov  dword ptr [eax + {O_ONCLICK:#x}], {col_click:#x}
        mov  dword ptr [eax + {O_ONCLICK + 4:#x}], ebx
        mov  eax, dword ptr [ebp - 12]
        add  eax, {GAP}
        add  dword ptr [ebp - 4], eax
        inc  edi
        jmp  next
    done:
        mov  eax, ebx
        xor  edx, edx
        call dword ptr [{i['SetVisible']:#x}]
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  20
    """, L.va))
    col_build = L.sym["col_build"]

    # ---- col_sync: EAX = master ---------------------------------------------------------------
    L.add("col_sync", asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x10
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  dword ptr [ebp - 4], 0
        cmp  dword ptr [ebx + {O_TAG:#x}], 0
        je   out
        xor  edi, edi
        mov  esi, dword ptr [ebx + {O_TAG:#x}]
    clear:
        test esi, esi
        je   cleared
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x40]
        inc  edi
        mov  esi, dword ptr [esi + {O_TAG:#x}]
        jmp  clear
    cleared:
        mov  dword ptr [ebp - 16], edi
        mov  eax, dword ptr [ebx + {O_ITEMS:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x14]
        mov  dword ptr [ebp - 12], eax
        mov  dword ptr [ebp - 8], 0
    row:
        mov  eax, dword ptr [ebp - 8]
        cmp  eax, dword ptr [ebp - 12]
        jge  rows_done
        mov  edx, eax
        mov  eax, dword ptr [ebx + {O_ITEMS:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x18]
        call {cat_of:#x}
        cmp  eax, dword ptr [ebp - 16]
        jb   k_ok
        mov  eax, dword ptr [ebp - 16]
        dec  eax
    k_ok:
        mov  edx, eax
        mov  eax, ebx
        call {col_at:#x}
        mov  esi, eax
        lea  ecx, [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  eax, dword ptr [ebx + {O_ITEMS:#x}]
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0xc]
        mov  edx, dword ptr [ebp - 4]
        mov  ecx, dword ptr [ebp - 8]
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x38]
        inc  dword ptr [ebp - 8]
        jmp  row
    rows_done:
        cmp  dword ptr [{G_LASTM:#x}], ebx
        jne  mirror
        mov  edx, dword ptr [{G_LASTK:#x}]
        mov  eax, ebx
        call {col_at:#x}
        test eax, eax
        je   none
        mov  esi, eax
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x14]
        dec  eax
        jl   none
        mov  ecx, dword ptr [{G_LASTR:#x}]
        cmp  ecx, eax
        jle  r_ok
        mov  ecx, eax
    r_ok:
        mov  dword ptr [{G_LASTR:#x}], ecx
        mov  edx, esi
        mov  eax, ebx
        call {select_in:#x}
        jmp  out
    mirror:
        mov  eax, ebx
        call {t['GetItemIndex']:#x}
        test eax, eax
        jl   none
        mov  edi, eax
        mov  edx, eax
        mov  eax, dword ptr [ebx + {O_ITEMS:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x18]
        call {cat_of:#x}
        cmp  eax, dword ptr [ebp - 16]
        jb   mk_ok
        mov  eax, dword ptr [ebp - 16]
        dec  eax
    mk_ok:
        mov  edx, eax
        mov  eax, ebx
        call {col_at:#x}
        mov  esi, eax
        mov  edx, edi
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        call dword ptr [{i['IndexOfObject']:#x}]
        test eax, eax
        jl   none
        mov  ecx, eax
        mov  edx, esi
        mov  eax, ebx
        call {select_in:#x}
        jmp  out
    none:
        xor  edx, edx
        or   ecx, -1
        mov  eax, ebx
        call {select_in:#x}
    out:
        lea  eax, [ebp - 4]
        call {t['LStrClr']:#x}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, L.va))
    col_sync = L.sym["col_sync"]

    # ---- eff_possible: EAX = ability owner -> EAX = 1 when some Effects ability fits its mask ---
    L.add("eff_possible", asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        test ebx, ebx
        je   no
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x8c]
        movzx edi, ax
        {ABCTL}
        call {t['GetCount']:#x}
        mov  esi, eax
    each:
        dec  esi
        js   no
        cmp  esi, 0xff
        ja   each
        cmp  byte ptr [{TBL:#x} + esi], {EFFECTS}
        jne  each
        {ABCTL}
        mov  edx, esi
        call {t['GetAbility']:#x}
        test eax, eax
        je   each
        test word ptr [eax + 0x20], di
        je   each
        mov  eax, 1
        jmp  out
    no:
        xor  eax, eax
    out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    eff_possible = L.sym["eff_possible"]

    # ---- grow: EAX = form, EDX = client panel, ECX = dW, stack dH; ret 4 ----------------------
    L.add("grow", asm(f"""
        push ebp
        mov  ebp, esp
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  edi, ecx
        mov  eax, dword ptr [ebx + {O_W:#x}]
        add  eax, edi
        push eax
        mov  eax, dword ptr [ebx + {O_H:#x}]
        add  eax, dword ptr [ebp + 8]
        push eax
        mov  eax, edi
        sar  eax, 1
        mov  edx, dword ptr [ebx + {O_LEFT:#x}]
        sub  edx, eax
        jns  l_ok
        xor  edx, edx
    l_ok:
        mov  eax, dword ptr [ebp + 8]
        sar  eax, 1
        mov  ecx, dword ptr [ebx + {O_TOP:#x}]
        sub  ecx, eax
        jns  t_ok
        xor  ecx, ecx
    t_ok:
        mov  eax, ebx
        call {vsb:#x}
        mov  eax, dword ptr [esi + {O_W:#x}]
        add  eax, edi
        push eax
        mov  eax, dword ptr [esi + {O_H:#x}]
        add  eax, dword ptr [ebp + 8]
        push eax
        mov  edx, dword ptr [esi + {O_LEFT:#x}]
        mov  ecx, dword ptr [esi + {O_TOP:#x}]
        mov  eax, esi
        call {vsb:#x}
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  4
    """, L.va))
    grow = L.sym["grow"]

    # ---- shift_left: EAX = control, EDX = dx ---------------------------------------------------
    L.add("shift_left", asm(f"""
        add  edx, dword ptr [eax + {O_LEFT:#x}]
        jmp  dword ptr [{i['SetLeft']:#x}]
    """, L.va))
    shift_left = L.sym["shift_left"]

    # ---- cols_total: EAX = colw, EDX = last colw, ECX = ncols -> EAX = width of all columns ----
    L.add("cols_total", asm(f"""
        add  eax, {GAP}
        dec  ecx
        imul eax, ecx
        add  eax, edx
        ret
    """, L.va))
    cols_total = L.sym["cols_total"]

    # ESI = master, EDI = ncols -> [ebp-4] = colw (the master's width), [ebp-8] = last column's
    WIDTHS = f"""
        mov  eax, dword ptr [esi + {O_W:#x}]
        mov  dword ptr [ebp - 4], eax
        cmp  edi, {len(CATEGORIES)}
        jne  same_w
        mov  ecx, eax
        sar  ecx, 2
        add  eax, ecx
    same_w:
        mov  dword ptr [ebp - 8], eax"""

    # ---- A: dialog ----------------------------------------------------------------------------
    D = DLG
    L.add("dlg_build", asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  eax, dword ptr [ebx + {D['owner']:#x}]
        call {eff_possible:#x}
        lea  edi, [eax + {len(HC.CATEGORIES)}]
        mov  esi, dword ptr [ebx + {D['master']:#x}]
        {WIDTHS}
        mov  eax, dword ptr [esi + {O_H:#x}]
        imul eax, eax, {DLG_TALL}
        mov  dword ptr [ebp - 12], eax
        mov  ecx, dword ptr [ebx + {D['add']:#x}]
        mov  eax, dword ptr [ecx + {O_TOP:#x}]
        sub  eax, dword ptr [esi + {O_TOP:#x}]
        sub  eax, dword ptr [esi + {O_H:#x}]
        mov  dword ptr [ebp - 16], eax
        mov  edx, dword ptr [ebx + {D['sheet']:#x}]
        mov  eax, dword ptr [edx + {O_H:#x}]
        sub  eax, dword ptr [ecx + {O_TOP:#x}]
        sub  eax, dword ptr [ecx + {O_H:#x}]
        mov  dword ptr [ebp - 20], eax
        mov  eax, dword ptr [edx + {O_W:#x}]
        sub  eax, dword ptr [esi + {O_LEFT:#x}]
        sub  eax, dword ptr [esi + {O_W:#x}]
        mov  dword ptr [ebp - 24], eax
        push dword ptr [ebp - 12]
        push dword ptr [ebp - 8]
        push dword ptr [ebp - 4]
        push dword ptr [esi + {O_TOP:#x}]
        mov  eax, dword ptr [ebx + {D['hdr']:#x}]
        push dword ptr [eax + {O_TOP:#x}]
        mov  ecx, edi
        mov  edx, dword ptr [esi + {O_LEFT:#x}]
        mov  eax, esi
        call {col_build:#x}
        mov  eax, dword ptr [ebx + {D['hdr']:#x}]
        xor  edx, edx
        call dword ptr [{i['SetVisible']:#x}]
        mov  eax, dword ptr [ebx + {D['sel']:#x}]
        push dword ptr [eax + {O_W:#x}]
        push dword ptr [ebp - 12]
        mov  edx, dword ptr [eax + {O_LEFT:#x}]
        mov  ecx, dword ptr [eax + {O_TOP:#x}]
        call {vsb:#x}
        mov  eax, dword ptr [esi + {O_TOP:#x}]
        add  eax, dword ptr [ebp - 12]
        add  eax, dword ptr [ebp - 16]
        mov  dword ptr [ebp - 28], eax
        mov  edx, eax
        mov  eax, dword ptr [ebx + {D['add']:#x}]
        call dword ptr [{i['SetTop']:#x}]
        mov  edx, dword ptr [ebp - 28]
        mov  eax, dword ptr [ebx + {D['delete']:#x}]
        call dword ptr [{i['SetTop']:#x}]
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  ecx, edi
        call {cols_total:#x}
        add  eax, dword ptr [esi + {O_LEFT:#x}]
        add  eax, dword ptr [ebp - 24]
        mov  ecx, dword ptr [ebx + {D['sheet']:#x}]
        sub  eax, dword ptr [ecx + {O_W:#x}]
        mov  dword ptr [ebp - 32], eax
        mov  edx, dword ptr [ebx + {D['add']:#x}]
        mov  eax, dword ptr [ebp - 28]
        add  eax, dword ptr [edx + {O_H:#x}]
        add  eax, dword ptr [ebp - 20]
        sub  eax, dword ptr [ecx + {O_H:#x}]
        push eax
        mov  ecx, dword ptr [ebp - 32]
        mov  edx, dword ptr [ebx + {D['client']:#x}]
        mov  eax, ebx
        call {grow:#x}
        mov  edx, dword ptr [ebp - 32]
        mov  eax, dword ptr [ebx + {D['ok']:#x}]
        call {shift_left:#x}
        mov  edx, dword ptr [ebp - 32]
        mov  eax, dword ptr [ebx + {D['cancel']:#x}]
        call {shift_left:#x}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, L.va))
    L.add("dlg_fill", asm(f"""
        push ebx
        mov  ebx, eax
        call {D['fill']:#x}
        mov  eax, dword ptr [ebx + {D['master']:#x}]
        cmp  dword ptr [eax + {O_TAG:#x}], 0
        jne  sync
        mov  eax, ebx
        call {L.sym['dlg_build']:#x}
    sync:
        mov  eax, dword ptr [ebx + {D['master']:#x}]
        call {col_sync:#x}
        pop  ebx
        ret
    """, L.va))

    # ---- B: hero editor ------------------------------------------------------------------------
    H = HERO
    L.add("hero_build", asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  eax, dword ptr [ebx + {H['owner']:#x}]
        call {eff_possible:#x}
        lea  edi, [eax + {len(HC.CATEGORIES)}]
        mov  esi, dword ptr [ebx + {H['master']:#x}]
        {WIDTHS}
        mov  eax, dword ptr [ebx + {H['hdr']:#x}]
        mov  eax, dword ptr [eax + {O_H:#x}]
        mov  ecx, eax
        sar  ecx, 1
        mov  dword ptr [ebp - 12], ecx
        lea  eax, [eax + ecx + 2]
        mov  dword ptr [ebp - 16], eax
        mov  edx, dword ptr [esi + {O_PARENT:#x}]
        mov  eax, dword ptr [edx + {O_H:#x}]
        sub  eax, dword ptr [ebp - 16]
        sub  eax, dword ptr [ebp - 12]
        push eax
        push dword ptr [ebp - 8]
        push dword ptr [ebp - 4]
        push dword ptr [ebp - 16]
        push dword ptr [ebp - 12]
        mov  ecx, edi
        mov  edx, dword ptr [edx + {O_W:#x}]
        mov  eax, esi
        call {col_build:#x}
        mov  eax, dword ptr [ebx + {H['hdr']:#x}]
        xor  edx, edx
        call dword ptr [{i['SetVisible']:#x}]
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  ecx, edi
        call {cols_total:#x}
        add  eax, dword ptr [ebp - 12]
        mov  dword ptr [ebp - 24], eax
        push 0
        mov  ecx, eax
        mov  edx, dword ptr [ebx + {H['client']:#x}]
        mov  eax, ebx
        call {grow:#x}
        mov  edx, dword ptr [ebp - 24]
        mov  eax, dword ptr [ebx + {H['ok']:#x}]
        call {shift_left:#x}
        mov  edx, dword ptr [ebp - 24]
        mov  eax, dword ptr [ebx + {H['cancel']:#x}]
        call {shift_left:#x}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, L.va))
    L.add("hero_fill", asm(f"""
        push ebx
        mov  ebx, eax
        call {H['fill']:#x}
        mov  eax, dword ptr [ebx + {H['master']:#x}]
        cmp  dword ptr [eax + {O_TAG:#x}], 0
        jne  sync
        mov  eax, ebx
        call {L.sym['hero_build']:#x}
    sync:
        mov  eax, dword ptr [ebx + {H['master']:#x}]
        call {col_sync:#x}
        pop  ebx
        ret
    """, L.va))

    # ---- C: Settings > Abilities ---------------------------------------------------------------
    L.add("set_fill", asm(f"""
        push esi
        push edi
        push ebp
        sub  esp, 0x10
        mov  dword ptr [esp], 0
        mov  esi, dword ptr [ebx + {SET_LIST:#x}]
        push eax
        push edx
        push ecx
        mov  eax, esi
        mov  dl, 1
        mov  ecx, dword ptr [{i['GetItemIndexVCL']:#x}]
        add  ecx, {D_SETSORTED}
        call ecx
        pop  ecx
        pop  edx
        pop  eax
        call {t['ListAbilities']:#x}
        mov  dl, 1
        mov  eax, dword ptr [{i['TStringList']:#x}]
        call {t['ObjCreate']:#x}
        mov  edi, eax
        mov  edx, dword ptr [esi + {O_ITEMS:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 8]
        mov  eax, esi
        xor  edx, edx
        mov  ecx, dword ptr [{i['GetItemIndexVCL']:#x}]
        add  ecx, {D_SETSORTED}
        call ecx
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        call dword ptr [{i['BeginUpdate']:#x}]
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x40]
        xor  ebp, ebp
    cat:
        cmp  ebp, {len(CATEGORIES)}
        jae  cats_done
        mov  dword ptr [esp + 4], 0
        mov  dword ptr [esp + 8], 0
    item:
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x14]
        cmp  dword ptr [esp + 8], eax
        jge  next_cat
        mov  edx, dword ptr [esp + 8]
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x18]
        mov  dword ptr [esp + 12], eax
        call {cat_of:#x}
        cmp  eax, ebp
        jne  next_item
        cmp  dword ptr [esp + 4], 0
        jne  have_hdr
        mov  dword ptr [esp + 4], 1
        mov  edx, dword ptr [{HDRS2:#x} + ebp*4]
        mov  ecx, {HDR_OBJ:#x}
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        push ebx
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x38]
        pop  ebx
    have_hdr:
        mov  ecx, esp
        mov  edx, dword ptr [esp + 8]
        mov  eax, edi
        push ebx
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0xc]
        pop  ebx
        mov  edx, dword ptr [esp]
        mov  ecx, dword ptr [esp + 12]
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        push ebx
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x38]
        pop  ebx
    next_item:
        inc  dword ptr [esp + 8]
        jmp  item
    next_cat:
        inc  ebp
        jmp  cat
    cats_done:
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        call dword ptr [{i['EndUpdate']:#x}]
        mov  eax, edi
        call {t['ObjFree']:#x}
        mov  eax, esp
        call {t['LStrClr']:#x}
        mov  dword ptr [{G_SETPREV:#x}], 0
        add  esp, 0x10
        pop  ebp
        pop  edi
        pop  esi
        ret
    """, L.va))
    L.add("set_click", asm(f"""
        push eax
        push edx
        push ebx
        push esi
        mov  esi, dword ptr [eax + {SET_LIST:#x}]
        mov  eax, esi
        call {t['GetItemIndex']:#x}
        test eax, eax
        jl   done
        mov  ebx, eax
        mov  edx, eax
        mov  eax, dword ptr [esi + {O_ITEMS:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x18]
        cmp  eax, {HDR_OBJ:#x}
        jne  remember
        lea  eax, [ebx + 1]
        cmp  eax, dword ptr [{G_SETPREV:#x}]
        jne  go
        lea  eax, [ebx - 1]
        test eax, eax
        jge  go
        lea  eax, [ebx + 1]
    go:
        mov  ebx, eax
        mov  edx, eax
        mov  eax, esi
        call {t['SetItemIndex']:#x}
    remember:
        mov  dword ptr [{G_SETPREV:#x}], ebx
    done:
        pop  esi
        pop  ebx
        pop  edx
        pop  eax
        push ebp
        mov  ebp, esp
        add  esp, -0x14
        jmp  {SET_CLICK_BODY:#x}
    """, L.va))
    return L


def hook_bytes(L):
    s = L.sym
    rel = lambda va, op, dst, n: bytes([op]) + struct.pack("<i", dst - (va + 5)) + b"\x90" * (n - 5)
    return {"A": struct.pack("<I", s["dlg_fill"]),
            "B": struct.pack("<I", s["hero_fill"]),
            "C1": rel(SET_CALL, 0xE8, s["set_fill"], 5),
            "C2": rel(SET_CLICK, 0xE9, s["set_click"], 6)}


class PE:
    def __init__(self, path):
        self.d = bytearray(open(path, "rb").read())
        e = struct.unpack_from("<I", self.d, 0x3C)[0]
        n = struct.unpack_from("<H", self.d, e + 6)[0]
        opt = struct.unpack_from("<H", self.d, e + 20)[0]
        self.e = e
        self.secs = [(bytes(self.d[e + 24 + opt + 40 * i:e + 32 + opt + 40 * i]).rstrip(b"\0"),)
                     + struct.unpack_from("<IIII", self.d, e + 24 + opt + 40 * i + 8)
                     + struct.unpack_from("<I", self.d, e + 24 + opt + 40 * i + 36)
                     for i in range(n)]

    def sec(self, va):
        for s in self.secs:
            if s[2] <= va - BASE < s[2] + max(s[1], s[3]):
                return s
        sys.exit("ABORT: VA %08X is in no section" % va)

    def off(self, va):
        _nm, _vs, vaddr, rs, raw, _ch = self.sec(va)
        assert va - BASE - vaddr < rs, "VA %08X has no file bytes" % va
        return raw + va - BASE - vaddr

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def relocs_in(self, lo, hi):
        rva, size = struct.unpack_from("<II", self.d, self.e + 24 + 136)
        out = []
        o = self.off(BASE + rva) if size else 0
        end = o + size
        while o < end:
            page, blk = struct.unpack_from("<II", self.d, o)
            if blk < 8:
                break
            for k in range((blk - 8) // 2):
                ent = struct.unpack_from("<H", self.d, o + 8 + 2 * k)[0]
                va = BASE + page + (ent & 0xFFF)
                if ent >> 12 and va < hi and va + 4 > lo:
                    out.append(va)
            o += blk
        return out

    def code(self):
        for nm, vs, vaddr, rs, raw, _ch in self.secs:
            if nm == b"CODE":
                return BASE + vaddr, bytes(self.d[raw:raw + min(vs, rs)])


def interior_jumps(pe, windows):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    base, code = pe.code()
    hits = []
    for k in range(len(code) - 5):
        if code[k] in (0xE8, 0xE9):
            tgt = base + k + 5 + struct.unpack_from("<i", code, k + 1)[0]
            hits += [base + k for lo, hi in windows if lo < tgt < hi]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for lo, hi in windows:
        for ins in md.disasm(code[lo - 0x200 - base:hi + 0x200 - base], lo - 0x200):
            if lo <= ins.address < hi or not (ins.mnemonic.startswith("j") or ins.mnemonic == "call"):
                continue
            try:
                tgt = int(ins.op_str, 16)
            except ValueError:
                continue
            if lo < tgt < hi and ins.size < 5:
                hits.append(ins.address)
    return sorted(set(hits))


def check_imports():
    """Every thunk and IAT slot used is the import this script believes it is."""
    from aowsyms import get_symbols
    pe, _b, _e, iat = get_symbols(zigexe.SRC_EDITOR)
    bad = []
    p = PE(TARGET)
    for name, (va, want) in TH.items():
        b = p.read(va, 6)
        slot = struct.unpack_from("<I", b, 2)[0] if b[:2] == b"\xff\x25" else None
        if slot is None or not str(iat.get(slot, "")).endswith(want):
            bad.append("%s thunk %08X" % (name, va))
    for name, (va, want) in IAT.items():
        if not str(iat.get(va, "")).endswith(want):
            bad.append("%s IAT %08X -> %s" % (name, va, iat.get(va)))
    _p, _b, vexp, _i = get_symbols("VCL30.dpl")
    for nm, va in VCL_LINK.items():
        if vexp.get(va) != nm:
            bad.append("VCL30 %s not at %08X" % (nm, va))
    return bad


def kill_aow():
    if os.environ.get("AOW_GAME_DIR"):
        return
    for n in zigexe.LOCKING_PROCESSES:
        subprocess.run(["taskkill", "/F", "/IM", n + ".exe"], capture_output=True)


def state(pe, L, new):
    blob = L.blob()
    win = pe.read(CAVE, CAVE_END - CAVE)
    orig = zlib.decompress(base64.b64decode(WIN_ORIG_B64))
    assert hashlib.sha256(orig).hexdigest()[:16] == WIN_SHA, "embedded window is corrupt"
    cave = ("original" if win == orig else
            "ours" if win[:len(blob)] == blob and win[len(blob):] == orig[len(blob):] else "FOREIGN")
    hooks = {}
    for k, (va, o) in HOOKS.items():
        cur = pe.read(va, len(o))
        hooks[k] = "vanilla" if cur == o else "installed" if cur == new[k] else "FOREIGN " + cur.hex(" ")
    return cave, hooks, orig


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    L = build()
    new = hook_bytes(L)
    pe = PE(TARGET)
    cave, hooks, orig = state(pe, L, new)
    print("build_deved_abcolumns -- %s" % TARGET)
    print("  code window %08X-%08X: %s (%d B of %d used)" % (CAVE, CAVE_END, cave, len(L.blob()),
                                                          CAVE_END - CAVE))
    for k, st in hooks.items():
        print("  %-3s %08X  %s" % (k, HOOKS[k][0], st))
    windows = {k: (va, va + len(o)) for k, (va, o) in HOOKS.items()}
    rl = [v for k in ("C1", "C2") for v in pe.relocs_in(*windows[k])] + pe.relocs_in(CAVE, CAVE_END)
    inner = interior_jumps(pe, [windows[k] for k in INTERIOR])
    bad = check_imports()
    mtb = pe.sec(CAVE)
    print("  .reloc under C1/C2/cave: %s" % (", ".join("%08X" % v for v in rl) or "none"))
    print("  jumps into a hook's interior: %s" % (", ".join("%08X" % v for v in inner) or "none"))
    print("  imports: %s" % ("; ".join(bad) or "all as expected"))
    print("  %s execute: %s" % (mtb[0].decode(), bool(mtb[5] & 0x20000000)))
    if pe.off(CAVE) != CAVE_FILE or b"TPF0" in orig or b"\x08MaxValue\x02" in orig:
        sys.exit("ABORT: the code window is not where, or what, this script expects")
    if os.path.exists(LIVE):
        lc, lh, _ = state(PE(LIVE), L, new)
        print("  %s (read-only): code %s, hooks %s" % (zigexe.LIVE_EDITOR, lc,
              "installed" if all(s == "installed" for s in lh.values()) else
              "vanilla" if all(s == "vanilla" for s in lh.values()) else "MIXED"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, va, b in L.parts:
            if name.startswith(("lit", "hdrs", "cattbl")):
                continue
            print("\n  ---- %s @%08X (%d B)" % (name, va, len(b)))
            for ins in md.disasm(b, va):
                print("    %08X  %-24s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic,
                                                 ins.op_str))
    st = "VANILLA" if cave == "original" and all(s == "vanilla" for s in hooks.values()) else \
        "INSTALLED" if cave == "ours" and all(s == "installed" for s in hooks.values()) else "MIXED"
    print("state: %s" % st)
    if cave == "FOREIGN" or any(s.startswith("FOREIGN") for s in hooks.values()):
        sys.exit("ABORT: foreign bytes at the cave or a hook site")
    if rl or inner or bad:
        sys.exit("ABORT: a .reloc entry, an interior jump or an import does not match")
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    if a.apply and not mtb[5] & 0x20000000:
        sys.exit("ABORT: .mtb is not executable -- build_deved_listarrows.py is not applied")
    if a.apply and st == "INSTALLED":
        print("\nalready installed -- nothing to do")
        return
    if a.undo and st == "VANILLA":
        print("\nalready vanilla -- nothing to do")
        return
    kill_aow()
    with open(TARGET, "r+b") as f:
        f.seek(CAVE_FILE)
        f.write(L.blob() + orig[len(L.blob()):] if a.apply else orig)
        for k, (va, o) in HOOKS.items():
            f.seek(pe.off(va))
            f.write(new[k] if a.apply else o)
    c2, h2, _ = state(PE(TARGET), L, new)
    want = "installed" if a.apply else "vanilla"
    assert c2 == ("ours" if a.apply else "original") and all(s == want for s in h2.values()), \
        "write did not stick"
    print("\n%s" % ("APPLIED" if a.apply else "UNDONE -- hooks vanilla, window restored"))
    print("    !! NOW RUN:  python build_zigeditor.py --apply   (rebuilds %s)" % zigexe.LIVE_EDITOR)


if __name__ == "__main__":
    main()
