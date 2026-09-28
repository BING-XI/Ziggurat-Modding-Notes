#!/usr/bin/env python
r"""
build_levelset.py -- the editor's MAP LEVELS popup: switch each map level on or off.
AoWEPACK.dpl (the popup and all its logic) + AoWDevEd.exe (a redirect in two handlers; the
live editor AoWzEd.exe is rebuilt from it by build_zigeditor.py).  Owner request 2026-09-27.

WHAT THE USER SEES
    Options > Add Map Level, Options > Remove Map Level, and the Add Level / Remove Level
    toolbar buttons all open one modal popup, "Map Levels": a checkbox per level laid out like
    the game's two-row World Map strip --
        Surface    Firmament   (Faery, later)
        Caverns    Depths      Abyss
    -- plus OK / Cancel.  Surface is always on and greyed.  OK applies the set:
      * a level switched OFF is cleared in place (every object on it destroyed, terrain
        re-filled) after a "Delete everything on the X?" confirmation; answering No keeps it;
      * a level switched ON that exists as a placeholder is simply re-enabled (it is blank);
      * a level switched ON beyond the map's level count is appended with AddMapLevel, and
        any level skipped on the way becomes a disabled placeholder;
      * trailing disabled levels are removed, so the count is always highest-enabled + 1;
      * no level ever changes its index.  (Vanilla Remove Level deleted the VIEWED level and
        renumbered every level after it -- which would move the Firmament and the Abyss.)
    Afterwards every cave pair whose two mouths no longer meet under the new level set is
    deleted (both mouths), and the view returns to the previous level, or Surface.

STORAGE -- build_maplevel4.py v4 owns it: the DISABLED mask is the byte [TAoWHSMap+0x41C],
saved as property id 0x60; cave links (and build_fly_levels.py's flying) skip disabled levels.
This script only edits that byte and the level list.

THE EDITOR SIDE -- AoWDevEd.exe, 28 bytes, no cave of its own (the exe has no room for one)
    TMainForm.AddMapLevelClick @0x0042BDC8 keeps its first three instructions, the third being
    `mov eax,[0x0043289C]` = the runtime address of AoWEPACK's map global.  Then:
      0x0042BDD0  mov edx,ebx / add eax,(levelset - 0x558FA040) / call eax     (9 B, was cmp+je)
      0x0042BDD9  vanilla `mov eax,[0x0043289C]` runs unchanged (its dword carries a .reloc)
      0x0042BDDE  test edx,edx / js 0x0042BE87 / jmp 0x0042BE07 + 5 nops       (18 B)
    The DLL routine returns EDX = the level to view, or -1 (cancelled / nothing changed).
    0x0042BE07 is vanilla's own refresh tail: SetSceneLevel(EDX), the two SetEnabled calls on
    the count-dependent controls, the palette page flip, THSMap.SetModified.  0x0042BE87 is the
    handler's `pop ebx / ret`.  The difference between two addresses in one DLL is rebase
    invariant, so the `add` needs no relocation.
    TMainForm.RemoveMapLevelClick @0x0042BCB8: `jmp 0x0042BDC8` (5 B).
    Every overwritten byte is .reloc-free (checked on every run from the exe's own table).

THE DLL SIDE -- slot 0x55850800..0x558517FF (exclusive), PIC via one call/pop anchor
    VCL30 and HSEPack routines the DLL does not import are reached through the load delta of an
    import it does have: vcl30 = [StdCtrls..TButton IAT] - 0x4BFD0, HSEPack =
    [THSMap.SetModified IAT] - 0xC3C0.  Used: TCheckBox (VMT 0x4C64C), Get/SetChecked
    (0x51800/0x51820), TControl.SetEnabled (0x42048), TCustomForm.SetBorderStyle (0x37228) /
    SetPosition (0x376E4), TButton.SetDefault (0x51558); HSMEdit.THSMEdit.SetSceneLevel
    (0x140B8), TMapLevel.DestroyHS (0x897C), THSMap.RemoveMapLevel (0xC0B4).  VMT slots
    verified on vcl30: +0x24 Create, +0x3C SetParent, +0x4C SetBounds, -4 Destroy.  TButton
    fields from vcl30's RTTI: ModalResult +0x120, Cancel +0x11D.  A bare TForm.Create loads no
    resource (TCustomForm.Create skips InitInheritedComponent when ClassType = TForm).
    Cave repair walks TStructureControl [map+0x100] (GetCount 0x55762390 / GetStructure
    0x55762364), keeps TCave objects (VMT 0x557B3018) whose partner -- twin_strict
    0x55844100, GetField, FindHS 0x2037E -- exists with the opposite polarity, and destroys the
    rest through [vmt-4]; it restarts after each destroy because a mouth takes its partner.

Rolls: none.  Runs only from the editor's menu/toolbar, never at package init.
USAGE   python build_levelset.py [--apply | --undo | --dis]    (then build_zigeditor.py --apply)
"""
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
EXE = os.path.join(GAME, zigexe.SRC_EDITOR)
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---- DLL ---------------------------------------------------------------------
DLL_BASE = 0x55700000
SLOT = (0x55850800, 0x55851800)
MAPGLOBAL = 0x558FA040
IAT_TBUTTON, IAT_TFORM, IAT_APP = 0x558FBB2C, 0x558FBAC8, 0x558FBAC0
IAT_SETTEXT, IAT_SHOWMODAL, IAT_MSGDLG = 0x558FBA2C, 0x558FBA70, 0x558FBAE8
IAT_FREE, IAT_SETMODIFIED = 0x558FB6C0, 0x558FBC54
V_TBUTTON, V_TCHECKBOX = 0x4BFD0, 0x4C64C                  # vcl30 RVAs
V_GETCHK, V_SETCHK, V_SETENABLED = 0x51800, 0x51820, 0x42048
V_BORDER, V_POSITION, V_SETDEFAULT = 0x37228, 0x376E4, 0x51558
H_SETMODIFIED, H_SETSCENE, H_DESTROYHS, H_REMOVE = 0xC3C0, 0x140B8, 0x897C, 0xC0B4
GETMAPLEVEL, GETFIELD = 0x557020EC, 0x557020FC
INITMAPLEVEL = 0x557773CC                                   # TAoWHSMap.InitializeMapLevel
SC_COUNT, SC_GET = 0x55762390, 0x55762364                    # TStructureControl
TCAVE_VMT, TCAVE_ID = 0x557B3018, 0x2037E
TWIN_STRICT = 0x55844100                                     # build_maplevel4.py (v4)
MASK_OFF = 0x41C
NAMES = {0: "Surface", 1: "Caverns", 2: "Depths", 3: "Firmament", 4: "Abyss"}
# (level, x, y) -- the World Map strip's grid; row 1 col 3 is kept for the Faery
GRID = [(0, 16, 16), (3, 108, 16), (1, 16, 42), (2, 108, 42), (4, 200, 42)]
CB_W, CB_H = 88, 17
# ---- New Map dialog (TNewMapDlg, fields from its live field table) ---------------------
NM_PANEL, NM_RADIOS = 0x210, (0x218, 0x21C, 0x220)         # MapLevelPnl; One/Two/ThreeLevels
# (level, x, y, width) -- the middle column is wider: "Firmament" clipped at 72 px
NM_GRID = [(0, 8, 40, 70), (3, 80, 40, 82), (1, 8, 66, 70), (2, 80, 66, 82), (4, 164, 66, 60)]
G_CB = 0x558FAEE0                                          # BSS: checkbox[level 0..4]
V_SETVISIBLE, V_RADIO_SETCHK = 0x4200C, 0x51B6C
ONCLICK = 0xA4                                             # TControl.FOnClick (Code, Data)
FORM_W, FORM_H = 306, 142
BTN_W, BTN_H, BTN_Y = 80, 25, 74
OK_X, CANCEL_X = 116, 204


def astr(s):
    b = struct.pack("<iI", -1, len(s)) + s.encode("ascii") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def data_block(base):
    """Strings, the checkbox table (12 B/record: level, x u16 @+2, y u16 @+4, caption @+8)
    and the confirmation table (5 dwords, by level).  All pointers are LINK VAs; the code
    adds the load delta."""
    d = bytearray()
    addr = {}

    def s(key, text):
        addr[key] = base + len(d) + 8
        d.extend(astr(text))
    s("title", "Map Levels")
    s("ok", "OK")
    s("cancel", "Cancel")
    for lv, n in NAMES.items():
        s(("name", lv), n)
        if lv:
            s(("ask", lv), "Delete everything on the %s?" % n)
    addr["cbtab"] = base + len(d)
    for lv, x, y in GRID:
        d.extend(struct.pack("<BBHHHI", lv, 0, x, y, 0, addr[("name", lv)]))
    addr["asktab"] = base + len(d)
    for lv in range(5):
        d.extend(struct.pack("<I", addr.get(("ask", lv), 0)))
    return bytes(d), addr


def nm_table(addr):
    """New Map checkbox records, same shape as the popup's; appended AFTER the code so the
    popup's own layout (and its installed bytes) never moves."""
    return b"".join(struct.pack("<BBHHHI", lv, 0, x, y, w, addr[("name", lv)])
                    for lv, x, y, w in NM_GRID)


def button(a, cap, x, mr, default):
    tail = (f"""
    mov  eax, edi
    mov  dl, 1
    mov  ecx, [esp+0x28]
    add  ecx, {V_SETDEFAULT:#x}
    call ecx""" if default else """
    mov  byte ptr [edi+0x11d], 1""")
    return f"""
    mov  eax, [ebp+{IAT_TBUTTON:#x}]
    mov  dl, 1
    mov  ecx, esi
    call dword ptr [eax+0x24]
    mov  edi, eax
    mov  edx, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x3c]
    mov  eax, edi
    lea  edx, [ebp+{a[cap]:#x}]
    call dword ptr [ebp+{IAT_SETTEXT:#x}]
    push ebx
    mov  ebx, [edi]
    push {BTN_W}
    push {BTN_H}
    mov  edx, {x}
    mov  ecx, {BTN_Y}
    mov  eax, edi
    call dword ptr [ebx+0x4c]
    pop  ebx
    mov  dword ptr [edi+0x120], {mr}{tail}
"""


def source(a):
    """Locals, from esp: +0 form, +4..+0x17 checkbox[level 0..4], +0x18 TMainForm,
    +0x1C result, +0x20 wanted bits, +0x24 old bits, +0x28 vcl30 base, +0x2C HSEPack base,
    +0x30 loop index, +0x34 record, +0x38 accepted, +0x3C level being viewed."""
    return f"""
levelset:
    push ebp
    push ebx
    push esi
    push edi
    sub  esp, 0x40
    mov  esi, edx
    mov  edi, esp
    xor  eax, eax
    mov  ecx, 0x10
    cld
    rep stosd
    mov  [esp+0x18], esi
    or   dword ptr [esp+0x1c], -1
    call _a
_a:
    pop  ebp
    sub  ebp, _a
    mov  ebx, [ebp+{MAPGLOBAL:#x}]
    test ebx, ebx
    je   _out
    mov  eax, [ebp+{IAT_TBUTTON:#x}]
    sub  eax, {V_TBUTTON:#x}
    mov  [esp+0x28], eax
    mov  eax, [ebp+{IAT_SETMODIFIED:#x}]
    sub  eax, {H_SETMODIFIED:#x}
    mov  [esp+0x2c], eax
    mov  eax, [esp+0x18]
    mov  eax, [eax+0x22c]
    movsx eax, byte ptr [eax+0x21d]
    mov  [esp+0x3c], eax
    call cur_bits
    mov  [esp+0x24], eax

    mov  eax, [ebp+{IAT_APP:#x}]
    mov  ecx, [eax]
    mov  eax, [ebp+{IAT_TFORM:#x}]
    mov  dl, 1
    call dword ptr [eax+0x24]
    mov  esi, eax
    mov  [esp], eax
    lea  edx, [ebp+{a['title']:#x}]
    call dword ptr [ebp+{IAT_SETTEXT:#x}]
    mov  eax, esi
    mov  dl, 3
    mov  ecx, [esp+0x28]
    add  ecx, {V_BORDER:#x}
    call ecx
    mov  eax, esi
    mov  dl, 4
    mov  ecx, [esp+0x28]
    add  ecx, {V_POSITION:#x}
    call ecx
    push ebx
    mov  ebx, [esi]
    push {FORM_W}
    push {FORM_H}
    xor  edx, edx
    xor  ecx, ecx
    mov  eax, esi
    call dword ptr [ebx+0x4c]
    pop  ebx

    mov  dword ptr [esp+0x30], 0
_cb:
    mov  eax, [esp+0x28]
    add  eax, {V_TCHECKBOX:#x}
    mov  dl, 1
    mov  ecx, esi
    call dword ptr [eax+0x24]
    mov  edi, eax
    mov  eax, [esp+0x30]
    lea  eax, [eax+eax*2]
    lea  eax, [ebp+eax*4+{a['cbtab']:#x}]
    mov  [esp+0x34], eax
    movzx eax, byte ptr [eax]
    mov  [esp+eax*4+4], edi
    mov  eax, edi
    mov  edx, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x3c]
    mov  eax, [esp+0x34]
    mov  edx, [eax+8]
    add  edx, ebp
    mov  eax, edi
    call dword ptr [ebp+{IAT_SETTEXT:#x}]
    push ebx
    mov  ebx, [edi]
    push {CB_W}
    push {CB_H}
    mov  eax, [esp+0x34+0xc]
    movzx edx, word ptr [eax+2]
    movzx ecx, word ptr [eax+4]
    mov  eax, edi
    call dword ptr [ebx+0x4c]
    pop  ebx
    mov  eax, [esp+0x34]
    movzx ecx, byte ptr [eax]
    mov  eax, [esp+0x24]
    bt   eax, ecx
    setb dl
    mov  eax, edi
    mov  ecx, [esp+0x28]
    add  ecx, {V_SETCHK:#x}
    call ecx
    mov  eax, [esp+0x34]
    cmp  byte ptr [eax], 0
    jne  _cbn
    mov  eax, edi
    xor  edx, edx
    mov  ecx, [esp+0x28]
    add  ecx, {V_SETENABLED:#x}
    call ecx
_cbn:
    inc  dword ptr [esp+0x30]
    cmp  dword ptr [esp+0x30], {len(GRID)}
    jb   _cb
{button(a, 'ok', OK_X, 1, True)}
{button(a, 'cancel', CANCEL_X, 2, False)}
    mov  eax, esi
    call dword ptr [ebp+{IAT_SHOWMODAL:#x}]
    cmp  eax, 1
    jne  _free
    xor  edi, edi
    mov  dword ptr [esp+0x30], 0
_rd:
    mov  ecx, [esp+0x30]
    mov  eax, [esp+ecx*4+4]
    test eax, eax
    je   _rdn
    mov  ecx, [esp+0x28]
    add  ecx, {V_GETCHK:#x}
    call ecx
    test al, al
    je   _rdn
    mov  ecx, [esp+0x30]
    bts  edi, ecx
_rdn:
    inc  dword ptr [esp+0x30]
    cmp  dword ptr [esp+0x30], 5
    jb   _rd
    or   edi, 1
    mov  [esp+0x20], edi
    mov  byte ptr [esp+0x38], 1
_free:
    mov  eax, esi
    call dword ptr [ebp+{IAT_FREE:#x}]
    cmp  byte ptr [esp+0x38], 1
    jne  _out
    mov  eax, [esp+0x20]
    cmp  eax, [esp+0x24]
    je   _out

    mov  dword ptr [esp+0x30], 1
_cf:
    mov  ecx, [esp+0x30]
    mov  eax, [esp+0x24]
    bt   eax, ecx
    jae  _cfn
    mov  eax, [esp+0x20]
    bt   eax, ecx
    jb   _cfn
    mov  eax, [ebp+ecx*4+{a['asktab']:#x}]
    add  eax, ebp
    push 0
    mov  dl, 3
    mov  ecx, 3
    call dword ptr [ebp+{IAT_MSGDLG:#x}]
    cmp  ax, 6
    je   _cfn
    mov  ecx, [esp+0x30]
    mov  eax, [esp+0x20]
    bts  eax, ecx
    mov  [esp+0x20], eax
_cfn:
    inc  dword ptr [esp+0x30]
    cmp  dword ptr [esp+0x30], 5
    jb   _cf
    mov  eax, [esp+0x20]
    cmp  eax, [esp+0x24]
    je   _out

    mov  eax, [esp+0x18]
    mov  eax, [eax+0x22c]
    xor  edx, edx
    mov  ecx, [esp+0x2c]
    add  ecx, {H_SETSCENE:#x}
    call ecx

    mov  dword ptr [esp+0x30], 1
_cl:
    mov  ecx, [esp+0x30]
    mov  eax, [esp+0x24]
    bt   eax, ecx
    jae  _cln
    mov  eax, [esp+0x20]
    bt   eax, ecx
    jb   _cln
    mov  eax, [ebx+0x10]
    mov  edx, ecx
    call {GETMAPLEVEL:#x}
    mov  ecx, [esp+0x2c]
    add  ecx, {H_DESTROYHS:#x}
    call ecx
    mov  edx, [esp+0x30]
    mov  eax, ebx
    call {INITMAPLEVEL:#x}
_cln:
    inc  dword ptr [esp+0x30]
    cmp  dword ptr [esp+0x30], 5
    jb   _cl

    mov  eax, [esp+0x20]
    not  eax
    and  eax, 0x1f
    mov  byte ptr [ebx+{MASK_OFF:#x}], al
_tr:
    mov  eax, [ebx+0x10]
    mov  ecx, [eax+0x14]
    cmp  ecx, 1
    jle  _grow
    dec  ecx
    mov  eax, [esp+0x20]
    bt   eax, ecx
    jb   _grow
    mov  edx, ecx
    mov  eax, ebx
    mov  ecx, [esp+0x2c]
    add  ecx, {H_REMOVE:#x}
    call ecx
    jmp  _tr
_grow:
    mov  eax, [esp+0x20]
    bsr  ecx, eax
    mov  eax, [ebx+0x10]
    cmp  ecx, [eax+0x14]
    jl   _mask
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0xac]
    test al, al
    jne  _grow
_mask:
    mov  eax, [ebx+0x10]
    mov  ecx, [eax+0x14]
    mov  eax, 1
    shl  eax, cl
    dec  eax
    mov  edx, [esp+0x20]
    not  edx
    and  eax, edx
    mov  byte ptr [ebx+{MASK_OFF:#x}], al
    call repair

    mov  eax, [esp+0x3c]
    cmp  eax, 3
    je   _v0
    mov  ecx, [ebx+0x10]
    cmp  eax, [ecx+0x14]
    jae  _v0
    mov  ecx, [esp+0x20]
    bt   ecx, eax
    jae  _v0
    mov  [esp+0x1c], eax
    jmp  _out
_v0:
    mov  dword ptr [esp+0x1c], 0
_out:
    mov  edx, [esp+0x1c]
    add  esp, 0x40
    pop  edi
    pop  esi
    pop  ebx
    pop  ebp
    ret

cur_bits:
    mov  eax, [ebx+0x10]
    mov  ecx, [eax+0x14]
    cmp  ecx, 5
    jbe  _c1
    mov  ecx, 5
_c1:
    mov  eax, 1
    shl  eax, cl
    dec  eax
    movzx edx, byte ptr [ebx+{MASK_OFF:#x}]
    not  edx
    and  eax, edx
    ret

repair:
    push esi
    push edi
_rs:
    mov  eax, [ebx+0x100]
    call {SC_COUNT:#x}
    mov  edi, eax
    xor  esi, esi
_ri:
    cmp  esi, edi
    jge  _rdone
    mov  eax, [ebx+0x100]
    mov  edx, esi
    call {SC_GET:#x}
    inc  esi
    test eax, eax
    je   _ri
    lea  ecx, [ebp+{TCAVE_VMT:#x}]
    cmp  [eax], ecx
    jne  _ri
    push eax
    movzx edx, byte ptr [eax+0x30]
    cmp  edx, 1
    ja   _rok
    mov  ecx, [eax+4]
    movsx eax, byte ptr [ecx+0x12]
    call {TWIN_STRICT:#x}
    test eax, eax
    js   _rorph
    mov  ecx, [esp]
    push eax
    movsx edx, byte ptr [ecx+0x10]
    movsx ecx, byte ptr [ecx+0x11]
    mov  eax, [ebx+0x10]
    call {GETFIELD:#x}
    test eax, eax
    je   _rorph
    mov  edx, {TCAVE_ID:#x}
    mov  ecx, [eax]
    call dword ptr [ecx+0x80]
    test eax, eax
    je   _rorph
    mov  ecx, [esp]
    movzx edx, byte ptr [ecx+0x30]
    xor  edx, 1
    cmp  byte ptr [eax+0x30], dl
    jne  _rorph
_rok:
    pop  eax
    jmp  _ri
_rorph:
    pop  eax
    mov  dl, 1
    mov  ecx, [eax]
    call dword ptr [ecx-4]
    jmp  _rs
_rdone:
    pop  edi
    pop  esi
    ret
"""


def anchor(tag):
    return f"""
    call {tag}
{tag}:
    pop  ebp
    sub  ebp, {tag}
"""


def src_nm_click():
    """OnClick of every New Map level checkbox (EAX = Data = the dialog, EDX = Sender):
    mirror the set onto the hidden vanilla radios -- Depths on -> ThreeLevels, else Caverns on
    -> TwoLevels, else OneLevel -- which is what the generated-map path still reads."""
    return f"""
    push ebp
    push ebx
    push esi
    {anchor('_k')}
    mov  ebx, eax
    mov  esi, [ebp+{IAT_TBUTTON:#x}]
    sub  esi, {V_TBUTTON:#x}
    mov  eax, [ebp+{G_CB + 8:#x}]
    test eax, eax
    je   _k1
    lea  ecx, [esi+{V_GETCHK:#x}]
    call ecx
    test al, al
    je   _k1
    mov  eax, [ebx+{NM_RADIOS[2]:#x}]
    jmp  _k3
_k1:
    mov  eax, [ebp+{G_CB + 4:#x}]
    test eax, eax
    je   _k2
    lea  ecx, [esi+{V_GETCHK:#x}]
    call ecx
    test al, al
    je   _k2
    mov  eax, [ebx+{NM_RADIOS[1]:#x}]
    jmp  _k3
_k2:
    mov  eax, [ebx+{NM_RADIOS[0]:#x}]
_k3:
    mov  dl, 1
    lea  ecx, [esi+{V_RADIO_SETCHK:#x}]
    call ecx
    pop  esi
    pop  ebx
    pop  ebp
    ret
"""


def src_nm_show(a, click):
    """Before TNewMapDlg.ShowModal (EDX = the dialog): hide the three level radios and put a
    checkbox per level in MapLevelPnl, laid out like the World Map strip, initialised from the
    radios, Surface greyed."""
    return f"""
    push ebp
    push ebx
    push esi
    push edi
    {anchor('_n0')}
    mov  ebx, edx
    mov  esi, [ebp+{IAT_TBUTTON:#x}]
    sub  esi, {V_TBUTTON:#x}
    mov  edi, 1
    mov  eax, [ebx+{NM_RADIOS[1]:#x}]
    cmp  byte ptr [eax+0x11d], 0
    je   _n1
    mov  edi, 3
_n1:
    mov  eax, [ebx+{NM_RADIOS[2]:#x}]
    cmp  byte ptr [eax+0x11d], 0
    je   _n2
    mov  edi, 7
_n2:
    push edi
    mov  eax, [ebx+{NM_RADIOS[0]:#x}]
    xor  edx, edx
    lea  ecx, [esi+{V_SETVISIBLE:#x}]
    call ecx
    mov  eax, [ebx+{NM_RADIOS[1]:#x}]
    xor  edx, edx
    lea  ecx, [esi+{V_SETVISIBLE:#x}]
    call ecx
    mov  eax, [ebx+{NM_RADIOS[2]:#x}]
    xor  edx, edx
    lea  ecx, [esi+{V_SETVISIBLE:#x}]
    call ecx
    push 0
_n3:
    lea  eax, [esi+{V_TCHECKBOX:#x}]
    mov  dl, 1
    mov  ecx, ebx
    call dword ptr [eax+0x24]
    mov  edi, eax
    mov  eax, [esp]
    lea  eax, [eax+eax*2]
    lea  eax, [ebp+eax*4+{a['nmtab']:#x}]
    push eax
    movzx eax, byte ptr [eax]
    mov  [ebp+eax*4+{G_CB:#x}], edi
    mov  eax, edi
    mov  edx, [ebx+{NM_PANEL:#x}]
    mov  ecx, [eax]
    call dword ptr [ecx+0x3c]
    mov  eax, [esp]
    mov  edx, [eax+8]
    add  edx, ebp
    mov  eax, edi
    call dword ptr [ebp+{IAT_SETTEXT:#x}]
    push esi
    mov  esi, [edi]
    mov  eax, [esp+4]
    movzx eax, word ptr [eax+6]
    push eax
    push {CB_H}
    mov  eax, [esp+0xc]
    movzx edx, word ptr [eax+2]
    movzx ecx, word ptr [eax+4]
    mov  eax, edi
    call dword ptr [esi+0x4c]
    pop  esi
    mov  eax, [esp]
    movzx ecx, byte ptr [eax]
    mov  eax, [esp+8]
    bt   eax, ecx
    setb dl
    mov  eax, edi
    lea  ecx, [esi+{V_SETCHK:#x}]
    call ecx
    mov  eax, [esp]
    cmp  byte ptr [eax], 0
    jne  _n4
    mov  eax, edi
    xor  edx, edx
    lea  ecx, [esi+{V_SETENABLED:#x}]
    call ecx
_n4:
    lea  eax, [ebp+{click:#x}]
    mov  [edi+{ONCLICK:#x}], eax
    mov  [edi+{ONCLICK + 4:#x}], ebx
    pop  eax
    inc  dword ptr [esp]
    cmp  dword ptr [esp], {len(NM_GRID)}
    jb   _n3
    add  esp, 8
    pop  edi
    pop  esi
    pop  ebx
    pop  ebp
    ret
"""


def src_nm_apply():
    """After the vanilla New Map OK built a blank map (it is the map global by then, not yet
    adopted or saved): read the checkboxes, trim trailing unwanted levels, append up to the
    highest wanted one, and mark the rest disabled.  A fresh map holds nothing to clear."""
    return f"""
    push ebp
    push ebx
    push esi
    push edi
    {anchor('_p0')}
    mov  ebx, [ebp+{MAPGLOBAL:#x}]
    test ebx, ebx
    je   _pout
    cmp  dword ptr [ebp+{G_CB:#x}], 0
    je   _pout
    mov  esi, [ebp+{IAT_TBUTTON:#x}]
    sub  esi, {V_TBUTTON:#x}
    xor  edi, edi
    push 0
_p1:
    mov  ecx, [esp]
    mov  eax, [ebp+ecx*4+{G_CB:#x}]
    test eax, eax
    je   _p2
    lea  edx, [esi+{V_GETCHK:#x}]
    call edx
    test al, al
    je   _p2
    mov  ecx, [esp]
    bts  edi, ecx
_p2:
    inc  dword ptr [esp]
    cmp  dword ptr [esp], 5
    jb   _p1
    add  esp, 4
    or   edi, 1
    xor  eax, eax
    mov  [ebp+{G_CB:#x}], eax
    mov  [ebp+{G_CB + 4:#x}], eax
    mov  [ebp+{G_CB + 8:#x}], eax
    mov  [ebp+{G_CB + 12:#x}], eax
    mov  [ebp+{G_CB + 16:#x}], eax
_p3:
    mov  eax, [ebx+0x10]
    mov  ecx, [eax+0x14]
    cmp  ecx, 1
    jle  _p4
    dec  ecx
    bt   edi, ecx
    jb   _p4
    mov  edx, ecx
    mov  eax, ebx
    mov  ecx, [ebp+{IAT_SETMODIFIED:#x}]
    sub  ecx, {H_SETMODIFIED - H_REMOVE:#x}
    call ecx
    jmp  _p3
_p4:
    bsr  ecx, edi
    mov  eax, [ebx+0x10]
    cmp  ecx, [eax+0x14]
    jl   _p5
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0xac]
    test al, al
    jne  _p4
_p5:
    mov  eax, [ebx+0x10]
    mov  ecx, [eax+0x14]
    mov  eax, 1
    shl  eax, cl
    dec  eax
    mov  edx, edi
    not  edx
    and  eax, edx
    mov  byte ptr [ebx+{MASK_OFF:#x}], al
_pout:
    pop  edi
    pop  esi
    pop  ebx
    pop  ebp
    ret
"""


def check_code(code, va):
    ins = list(cs.disasm(code, va))
    assert sum(x.size for x in ins) == len(code), "block at %08X does not fully disassemble" % va
    for i, x in enumerate(ins):
        if "ptr [0x55" in x.op_str:
            sys.exit("ABORT: absolute memory operand at %08X: %s %s"
                     % (x.address, x.mnemonic, x.op_str))
        # the anchor's `sub` must name the address its call returns to
        if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
            sub = ins[i + 2]
            assert sub.mnemonic == "sub" and int(sub.op_str.split(",")[1], 0) == x.address + 5


def build():
    data, a = data_block(SLOT[0])
    va = (SLOT[0] + len(data) + 0xF) & ~0xF
    blob = bytearray(data + b"\0" * (va - SLOT[0] - len(data)))
    entries = {}
    for name, fn in (("levelset", lambda: source(a)), ("nm_click", src_nm_click),
                     ("nm_apply", src_nm_apply), ("nmtab", None),
                     ("nm_show", lambda: src_nm_show(a, entries["nm_click"]))):
        if fn is None:                               # data: the New Map checkbox table
            a["nmtab"] = va
            code = nm_table(a)
            entries[name] = va
            blob += code
            nxt = (va + len(code) + 0xF) & ~0xF
            blob += b"\0" * (nxt - va - len(code))
            va = nxt
            continue
        code = bytes(ks.asm(fn(), va)[0])
        check_code(code, va)
        entries[name] = va
        blob += code
        nxt = (va + len(code) + 0xF) & ~0xF
        blob += b"\0" * (nxt - va - len(code))
        va = nxt
    assert SLOT[0] + len(blob) <= SLOT[1], "levelset outgrew its slot"
    return bytes(blob), entries


BLOB, ENTRIES = build()
ENTRY = ENTRIES["levelset"]

# ---- AoWDevEd.exe ------------------------------------------------------------
EXE_BASE = 0x400000
ADD_HOOK1, ADD_ORIG1 = 0x0042BDD0, bytes.fromhex("8338000f84ae000000")
ADD_HOOK2, ADD_ORIG2 = 0x0042BDDE, bytes.fromhex("8b008b10ff92ac00000084c00f8497000000")
REM_HOOK, REM_ORIG = 0x0042BCB8, bytes.fromhex("558bec6a00")
TAIL_REFRESH, TAIL_RET, ADD_ENTRY = 0x0042BE07, 0x0042BE87, 0x0042BDC8


# New Map: two stubs in reloc-free runs of the now-dead RemoveMapLevelClick body (its entry
# jumps to AddMapLevelClick), the ShowModal call retarget, and a hook after map.New.
MAPSLOT = 0x0043289C                       # holds the runtime address of AoWEPACK's map global
NM_SHOWCALL = 0x00429A70                   # TMainForm.NewItemClick: call TCustomForm.ShowModal
SHOWMODAL = 0x004012E8
NM_SHOWCALL_ORIG = bytes.fromhex("e87378fdff")
NM_NEWCALL, NM_NEWCALL_ORIG = 0x004034DB, bytes.fromhex("ff91cc000000")   # call [ecx+0xCC]
S1_VA = 0x0042BD01                         # 48 reloc-free bytes (0x42BD01..0x42BD30)
S1_WIN = bytes.fromhex("e83a54fdff8b55fcb1038bc3e8d2feffff6683f8060f85860000008b832c0200000fbeb01d02000033d2e80871fdffa1")
S2_VA = 0x0042BD43                         # 61 reloc-free bytes (0x42BD43..0x42BD7F)
S2_WIN = bytes.fromhex("8b008b4010837814010f9fc28b8300060000e8f657fdff8b83000600008a50458b83fc050000e8e257fdff8b93440200008b8340020000e87166fdffa1")


def delta_call(target):
    """eax = [MAPSLOT] (runtime &map global); add the in-DLL difference; call it."""
    return "mov eax, dword ptr [%#x]; add eax, %#x; call eax" % (
        MAPSLOT, (target - MAPGLOBAL) & 0xFFFFFFFF)


def exe_sites():
    h1 = bytes(ks.asm("mov edx, ebx; add eax, %#x; call eax" % ((ENTRY - MAPGLOBAL) & 0xFFFFFFFF),
                      ADD_HOOK1)[0])
    h2 = bytes(ks.asm("test edx, edx; js %#x; jmp %#x" % (TAIL_RET, TAIL_REFRESH), ADD_HOOK2)[0])
    h2 += b"\x90" * (len(ADD_ORIG2) - len(h2))
    rm = bytes(ks.asm("jmp %#x" % ADD_ENTRY, REM_HOOK)[0])
    assert len(h1) == len(ADD_ORIG1) and len(rm) == len(REM_ORIG) and len(h2) == len(ADD_ORIG2)
    s1 = bytes(ks.asm("push eax; mov edx, eax; %s; pop eax; jmp %#x"
                      % (delta_call(ENTRIES["nm_show"]), SHOWMODAL), S1_VA)[0])
    s2 = bytes(ks.asm("call dword ptr [ecx+0xcc]; %s; ret" % delta_call(ENTRIES["nm_apply"]),
                      S2_VA)[0])
    assert len(s1) <= 48 and len(s2) <= 61
    show = bytes(ks.asm("call %#x" % S1_VA, NM_SHOWCALL)[0])
    new = bytes(ks.asm("call %#x" % S2_VA, NM_NEWCALL)[0]) + b"\x90"
    return [("Add handler call", ADD_HOOK1, ADD_ORIG1, h1),
            ("Add handler tail", ADD_HOOK2, ADD_ORIG2, h2),
            ("Remove -> Add   ", REM_HOOK, REM_ORIG, rm),
            ("NewMap stub S1  ", S1_VA, S1_WIN[:len(s1)], s1),
            ("NewMap stub S2  ", S2_VA, S2_WIN[:len(s2)], s2),
            ("NewMap ShowModal", NM_SHOWCALL, NM_SHOWCALL_ORIG, show),
            ("NewMap after New", NM_NEWCALL, NM_NEWCALL_ORIG, new)]


EXE_SITES = exe_sites()

# ---- the live TMAINFORM DFM (in .ctp, found through the resource directory) -----------
# Length-neutral: the Add item's caption keeps its 14 characters, and the Remove item keeps its
# NAME (so its published field still binds) but trades Caption + OnClick (56 B) for
# Visible False + a 40-space Hint (56 B).  The Add/Remove toolbar buttons are already gone from
# the live DFM (build_deved_toolbar_trim.py), so these two menu items are all that is left.
DFM_ORIG = (b"\x0eRemoveMapLevel"
            b"\x07Caption\x06\x11&Remove Map Level"
            b"\x07OnClick\x07\x13RemoveMapLevelClick\x00\x00"
            b"\x09TMenuItem\x0bAddMapLevel"
            b"\x07Caption\x06\x0e&Add Map Level"
            b"\x07OnClick\x07\x10AddMapLevelClick\x00\x00")
DFM_NEW = (b"\x0eRemoveMapLevel"
           b"\x07Visible\x08"
           b"\x04Hint\x06\x28" + b" " * 40 + b"\x00\x00"
           b"\x09TMenuItem\x0bAddMapLevel"
           b"\x07Caption\x06\x0e&Map Levels..."
           b"\x07OnClick\x07\x10AddMapLevelClick\x00\x00")
assert len(DFM_ORIG) == len(DFM_NEW)


def live_tmainform(d):
    """(file offset, size) of the TMAINFORM RCDATA the resource directory points at."""
    e = sections(d)[0]
    rsrc_rva = struct.unpack_from("<I", d, e + 24 + 96 + 2 * 8)[0]
    ro = va2off(d, EXE_BASE, EXE_BASE + rsrc_rva)
    hits = []

    def name_at(v):
        o = ro + (v & 0x7FFFFFFF)
        n = struct.unpack_from("<H", d, o)[0]
        return d[o + 2:o + 2 + 2 * n].decode("utf-16le")

    def walk(diroff, path):
        nn, ni = struct.unpack_from("<HH", d, ro + diroff + 12)
        for i in range(nn + ni):
            nm, off = struct.unpack_from("<II", d, ro + diroff + 16 + i * 8)
            label = name_at(nm) if nm & 0x80000000 else "#%d" % nm
            if off & 0x80000000:
                walk(off & 0x7FFFFFFF, path + [label])
            elif "TMAINFORM" in [p.upper() for p in path + [label]]:
                rva, size = struct.unpack_from("<II", d, ro + off)
                hits.append((va2off(d, EXE_BASE, EXE_BASE + rva), size))
    walk(0, [])
    assert len(hits) == 1, "TMAINFORM entries: %d" % len(hits)
    return hits[0]


def dfm_state(d):
    lo, size = live_tmainform(d)
    blob = bytes(d[lo:lo + size])
    no, nn = blob.count(DFM_ORIG), blob.count(DFM_NEW)
    if (no, nn) == (1, 0):
        return "vanilla", lo + blob.find(DFM_ORIG)
    if (no, nn) == (0, 1):
        return "installed", lo + blob.find(DFM_NEW)
    return "FOREIGN (orig x%d, new x%d)" % (no, nn), None


# ---- PE plumbing ---------------------------------------------------------------
def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    return e, [struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8) for i in range(n)]


def va2off(d, base, va):
    for vs, vaddr, rs, raw in sections(d)[1]:
        if vaddr <= va - base < vaddr + max(vs, rs):
            return raw + va - base - vaddr
    sys.exit("ABORT: VA %08X unmapped" % va)


def relocs(d, base):
    e = sections(d)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    o = va2off(d, base, base + rva)
    end, out = o + size, set()
    while o < end:
        page, blk = struct.unpack_from("<II", d, o)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            w = struct.unpack_from("<H", d, o + 8 + 2 * k)[0]
            if w >> 12:
                out.add(base + page + (w & 0xFFF))
        o += blk
    return out


def kill_aow():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | "
                    "Stop-Process -Force" % "|".join(zigexe.LOCKING_PROCESSES)],
                   capture_output=True)


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    print("build_levelset -- Map Levels popup: DLL slot %08X-%08X (%d B used, entry %08X), "
          "3 editor sites" % (SLOT[0], SLOT[1], len(BLOB), ENTRY))
    if "--dis" in sys.argv:
        code = BLOB[ENTRY - SLOT[0]:]
        for ins in cs.disasm(code, ENTRY):
            print("  %08X  %-24s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))
        for label, va, o, n in EXE_SITES:
            print("\n  %s %08X  %s\n  %s" % (label, va, o.hex(" "), " " * 26 + n.hex(" ")))
        return
    dll = bytearray(open(DLL, "rb").read())
    exe = bytearray(open(EXE, "rb").read())
    zo = va2off(dll, DLL_BASE, SLOT[0])
    zone = bytes(dll[zo:zo + SLOT[1] - SLOT[0]])
    k = ENTRIES["nm_click"] - SLOT[0]          # v1 (popup only) ended before the New Map part
    dll_st = ("zero" if not any(zone) else
              "ours" if zone[:len(BLOB)] == BLOB and not any(zone[len(BLOB):]) else
              "ours, v1 (no New Map part)" if zone[:k] == BLOB[:k] and not any(zone[k:]) else
              # the slot is exclusive; an older New Map part behind an identical popup is ours
              "ours, older New Map part" if zone[:k] == BLOB[:k] else
              "FOREIGN")
    print("  DLL slot: %s" % dll_st)
    rel = relocs(exe, EXE_BASE)
    st = []
    for label, va, o, n in EXE_SITES:
        cur = bytes(exe[va2off(exe, EXE_BASE, va):][:len(o)])
        s = "vanilla" if cur == o else "installed" if cur == n else "FOREIGN"
        hit = [x for x in rel if va - 3 <= x < va + len(o)]
        st.append(s)
        print("  %s %08X  %s%s" % (label, va, s, "  !! .reloc %s" % [hex(x) for x in hit] if hit else ""))
        if hit:
            sys.exit("ABORT: a displaced editor range carries a base relocation")
    dst, dat = dfm_state(exe)
    st.append(dst)
    print("  TMAINFORM menu items       %s%s" % (dst, "" if dat is None else " (file %#x)" % dat))
    if any(s.startswith("FOREIGN") for s in st) or dll_st == "FOREIGN":
        sys.exit("ABORT: foreign bytes -- inspect before writing")
    state = ("VANILLA" if all(s == "vanilla" for s in st) and dll_st == "zero" else
             "INSTALLED" if all(s == "installed" for s in st) and dll_st == "ours" else "MIXED")
    print("state: %s" % state)
    if not (apply_ or undo):
        print("(dry run -- nothing written)")
        return
    if (apply_ and state == "INSTALLED") or (undo and state == "VANILLA"):
        print("nothing to do")
        return
    dll[zo:zo + SLOT[1] - SLOT[0]] = (BLOB + bytes(SLOT[1] - SLOT[0] - len(BLOB))) if apply_ \
        else bytes(SLOT[1] - SLOT[0])
    for label, va, o, n in EXE_SITES:
        at = va2off(exe, EXE_BASE, va)
        exe[at:at + len(o)] = n if apply_ else o
    exe[dat:dat + len(DFM_NEW)] = DFM_NEW if apply_ else DFM_ORIG
    kill_aow()
    open(DLL, "wb").write(dll)
    open(EXE, "wb").write(exe)
    print("%s -- now run build_zigeditor.py --apply to rebuild %s"
          % ("APPLIED" if apply_ else "UNDONE", zigexe.LIVE_EDITOR))


if __name__ == "__main__":
    main()
