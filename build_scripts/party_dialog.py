r"""Stage-2 dialog for build_party_random.py -- the "Random Party" configuration dialog.

Kept in its own module because it is mostly a control table + a long cave; build_party_random.py
imports LAYOUT/BEHAVIOURS/dialog_source() and splices the result into the .pty section.

The dialog is built AT RUNTIME out of real VCL controls (TCustomForm.CreateNew + virtual
constructors) rather than from a DFM resource: that avoids inventing a new Delphi form class and
rebuilding the PE resource tree, and it lets the race check-boxes take their captions from the
loaded mapset instead of hard-coded English names.

Everything is reached through two runtime rebase deltas -- no new imports:
    vcl_delta = [0x432210] - 0x41336300      (exe IAT slot for Forms.TCustomForm.Create)
    dll_delta = [0x432898] - 0x558FA044      (exe IAT slot for the AoWEPACK var AoWE.AoWHSSet)
"""

# ---- VCL30 (preferred base 0x41300000) ------------------------------------------
VCL_BASE          = 0x41300000
IAT_TCUSTOMFORM_CREATE = 0x432210          # exe IAT slot -> Forms.TCustomForm.Create
VCL_ANCHOR_RVA    = 0x36300                # ...whose VCL30 rva this is

R_CREATENEW       = 0x36490                # TCustomForm.CreateNew   EAX=class DL=1 ECX=owner
R_SETPARENT       = 0x41F88                # TControl.SetParent      EAX=self EDX=parent
R_SETTEXTBUF      = 0x4208C                # TControl.SetTextBuf     EAX=self EDX=PChar
R_SETVISIBLE      = 0x4200C                # TControl.SetVisible     EAX=self DL=bool
R_GETCHECKED_CB   = 0x51800                # TCustomCheckBox.GetChecked  EAX=self -> AL
R_SETCHECKED_CB   = 0x51820                # TCustomCheckBox.SetChecked  EAX=self DL=bool
R_SETCHECKED_RB   = 0x51B6C                # TRadioButton.SetChecked     EAX=self DL=bool
R_SETITEMINDEX    = 0x50568                # TCustomComboBox.SetItemIndex EAX=self EDX=idx
R_SETSTYLE        = 0x50760                # TCustomComboBox.SetStyle     EAX=self DL=style
R_SETBORDERSTYLE  = 0x37228                # TCustomForm.SetBorderStyle   EAX=self DL=style
R_SETPOSITION     = 0x376E4                # TCustomForm.SetPosition      EAX=self DL=pos

V_CREATE          = 0x24                   # TComponent.Create   (virtual constructor) VMT slot
V_SETBOUNDS       = 0x4C                   # TControl.SetBounds  VMT slot
V_STRINGS_ADD     = 0x34                   # TStrings.Add        VMT slot

# class VMTs (rva)
C_FORM            = 0x340EC
C_GROUPBOX        = 0x49990
C_RADIOBUTTON     = 0x4CBD0
C_CHECKBOX        = 0x4C64C
C_COMBOBOX        = 0x4B878
C_BUTTON          = 0x4BFD0

F_RB_CHECKED      = 0x11D                  # TRadioButton.Checked   (field-backed, byte)
F_BTN_MODALRESULT = 0x120                  # TButton.ModalResult    (field-backed, dword)
F_CB_ITEMS        = 0x118                  # TCustomComboBox -> its TStrings
CS_DROPDOWNLIST   = 2
BS_DIALOG         = 3                      # TFormBorderStyle bsDialog
PO_SCREENCENTER   = 4                      # TPosition poScreenCenter
MR_OK             = 1

# exe import thunks already present
T_SHOWMODAL       = 0x4012E8
T_FREE            = 0x401040
T_GETITEMINDEX    = 0x401A90               # TCustomComboBox.GetItemIndex

# AoWEPACK (preferred VAs, + dll_delta)
IAT_AOWHSSET      = 0x432898
AOWHSSET_PREF     = 0x558FA044
HSSET_RACERESLIST = 0x54                   # HSSet -> TRaceResourceList
FN_GETRACERES     = 0x5575A0C4             # TRaceResourceList.GetRaceResource EAX=list EDX=idx
RACERES_NAME      = 0x24                   # -> AnsiString (NUL-terminated, usable as PChar)

# ---- dialog geometry -------------------------------------------------------------
FORM_W, FORM_H = 500, 356      # wide enough for the longest Strength caption
MAX_RACES = 12
RACE_COLS, RACE_ROWS = 3, 4

# kinds
K_PLAIN, K_STRENGTH, K_RACE, K_COMBO, K_OK, K_CANCEL = 0, 1, 2, 3, 4, 5

BEHAVIOURS = [          # (caption, engine id) -- ids verified from <AG>.Behavior in AoWEPACK
    ("Auto",       0),
    ("Patrol",     1),
    ("Guard",      2),
    ("Guard Area", 3),
    ("Scout",      4),
    ("Refuge",     5),
    ("Raid",       6),
    ("Suicidal",  10),  # NOTE: 10, not 7 -- the list order is not the id order
]
DEFAULT_BEHAVIOUR = 2   # Guard

STRENGTH_CAPTIONS = [
    "Weak  (3-4 x level 1)",
    "Medium  (3-5 x lvl 1, 2 x lvl 2)",
    "Large  (4 x lvl 1, 2-3 x lvl 2, 1 x lvl 3)",
]


def build_layout():
    """-> list of dicts, one per control, in creation order."""
    L = []
    L.append(dict(vmt=C_GROUPBOX, x=10, y=8, w=272, h=100, parent=-1,
                  kind=K_PLAIN, idx=0, cap="Strength"))
    for i, cap in enumerate(STRENGTH_CAPTIONS):
        L.append(dict(vmt=C_RADIOBUTTON, x=12, y=20 + i * 24, w=252, h=20, parent=0,
                      kind=K_STRENGTH, idx=i, cap=cap))
    L.append(dict(vmt=C_GROUPBOX, x=290, y=8, w=197, h=100, parent=-1,
                  kind=K_PLAIN, idx=0, cap="Behaviour of placed party"))
    L.append(dict(vmt=C_COMBOBOX, x=12, y=28, w=173, h=24, parent=4,
                  kind=K_COMBO, idx=0, cap=None))
    L.append(dict(vmt=C_GROUPBOX, x=10, y=116, w=477, h=152, parent=-1,
                  kind=K_PLAIN, idx=0, cap="Eligible races"))
    races_gb = len(L) - 1
    for i in range(MAX_RACES):
        col, row = i % RACE_COLS, i // RACE_COLS
        L.append(dict(vmt=C_CHECKBOX, x=12 + col * 154, y=22 + row * 30, w=148, h=20,
                      parent=races_gb, kind=K_RACE, idx=i, cap=None))
    L.append(dict(vmt=C_BUTTON, x=294, y=282, w=90, h=28, parent=-1,
                  kind=K_OK, idx=0, cap="OK"))
    L.append(dict(vmt=C_BUTTON, x=394, y=282, w=90, h=28, parent=-1,
                  kind=K_CANCEL, idx=0, cap="Cancel"))
    return L


ENTRY_SIZE = 20      # vmt(4) x(2) y(2) w(2) h(2) parent(2) kind(1) idx(1) caption(4)


def emit_data(layout, base_va, off):
    """Emit strings + control table. Returns (blob, table_va, strings_map, next_off)."""
    import struct
    blob = bytearray()
    strs = {}

    def put_cstr(s):
        if s in strs:
            return strs[s]
        va = base_va + off + len(blob)
        strs[s] = va
        blob.extend(s.encode('latin1') + b'\0')
        return va

    def put_ansistring(s):
        """Delphi 3 literal: [allocSiz][refCnt=-1][length] then chars + NUL; ptr = chars."""
        nonlocal blob
        while (off + len(blob)) % 4:
            blob.append(0)
        b = s.encode('latin1')
        blob.extend(struct.pack('<iii', len(b) + 13, -1, len(b)))
        va = base_va + off + len(blob)
        blob.extend(b + b'\0')
        return va

    caps = {c['cap']: put_cstr(c['cap']) for c in layout if c['cap']}
    title_va = put_cstr("Random Party Generator")
    behav_vas = [put_ansistring(n) for n, _ in BEHAVIOURS]

    while (off + len(blob)) % 4:
        blob.append(0)
    behav_id_va = base_va + off + len(blob)
    blob.extend(bytes(i for _, i in BEHAVIOURS))
    while (off + len(blob)) % 4:
        blob.append(0)
    behav_ptr_va = base_va + off + len(blob)
    for v in behav_vas:
        blob.extend(struct.pack('<I', v))

    while (off + len(blob)) % 4:
        blob.append(0)
    table_va = base_va + off + len(blob)
    for c in layout:
        blob.extend(struct.pack('<IhhhhhBBI', c['vmt'], c['x'], c['y'], c['w'], c['h'],
                                c['parent'], c['kind'], c['idx'],
                                caps[c['cap']] if c['cap'] else 0))
    return bytes(blob), dict(table=table_va, title=title_va, behav_id=behav_id_va,
                             behav_ptr=behav_ptr_va), off + len(blob)


def dialog_source(S, layout):
    """S: dict of symbol VAs from build_party_random.gen_source (globals + table)."""
    n = len(layout)
    return f"""
; ===================== show_dialog =====================
; Builds the configuration dialog at runtime, runs it modal, and on OK writes
; g_strength / g_racemask / g_behavior.  Preserves everything.
show_dialog:
        push ebp
        mov  ebp, esp
        sub  esp, 0x30
        push ebx
        push esi
        push edi

        mov  eax, dword ptr [{IAT_TCUSTOMFORM_CREATE:#x}]
        sub  eax, {VCL_BASE + VCL_ANCHOR_RVA:#x}
        mov  dword ptr [ebp - 0x04], eax          ; vcl_delta
        mov  eax, dword ptr [{IAT_AOWHSSET:#x}]
        sub  eax, {AOWHSSET_PREF:#x}
        mov  dword ptr [ebp - 0x08], eax          ; dll_delta

        ; ---- form := TForm.CreateNew(nil) ----
        mov  eax, dword ptr [ebp - 0x04]
        add  eax, {VCL_BASE + C_FORM:#x}
        xor  ecx, ecx
        mov  dl, 1
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_CREATENEW:#x}
        call esi
        test eax, eax
        jz   sd_done
        mov  dword ptr [ebp - 0x0C], eax          ; form
        mov  ebx, eax

        mov  eax, ebx                             ; SetBounds(form, 0,0,W,H)
        xor  edx, edx
        xor  ecx, ecx
        push {FORM_W}
        push {FORM_H}
        mov  esi, dword ptr [eax]
        call dword ptr [esi + {V_SETBOUNDS:#x}]
        mov  eax, ebx                             ; BorderStyle := bsDialog
        mov  dl, {BS_DIALOG}
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETBORDERSTYLE:#x}
        call esi
        mov  eax, ebx                             ; Position := poScreenCenter
        mov  dl, {PO_SCREENCENTER}
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETPOSITION:#x}
        call esi
        mov  eax, ebx                             ; Caption
        mov  edx, {S['title']:#x}
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETTEXTBUF:#x}
        call esi

        ; ---- create every control from the table ----
        mov  dword ptr [ebp - 0x10], 0            ; i
    sd_mk:
        mov  eax, dword ptr [ebp - 0x10]
        cmp  eax, {n}
        jge  sd_mk_done
        imul eax, eax, {ENTRY_SIZE}
        add  eax, {S['table']:#x}
        mov  dword ptr [ebp - 0x14], eax          ; entry

        mov  eax, dword ptr [ebp - 0x04]          ; classref = vcl + entry.vmt
        add  eax, {VCL_BASE:#x}
        mov  esi, dword ptr [ebp - 0x14]
        add  eax, dword ptr [esi]
        mov  ecx, dword ptr [ebp - 0x0C]          ; AOwner = form
        mov  dl, 1
        call dword ptr [eax + {V_CREATE:#x}]      ; virtual constructor
        test eax, eax
        jz   sd_mk_next
        mov  edi, eax                             ; the control
        mov  eax, dword ptr [ebp - 0x10]
        mov  dword ptr [eax * 4 + {S['g_ctrls']:#x}], edi

        mov  esi, dword ptr [ebp - 0x14]          ; SetParent
        movsx edx, word ptr [esi + 12]
        cmp  edx, -1
        jne  sd_par_ctrl
        mov  edx, dword ptr [ebp - 0x0C]
        jmp  sd_par_go
    sd_par_ctrl:
        mov  edx, dword ptr [edx * 4 + {S['g_ctrls']:#x}]
    sd_par_go:
        mov  eax, edi
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETPARENT:#x}
        call esi

        mov  esi, dword ptr [ebp - 0x14]          ; SetBounds(x,y,w,h)
        movsx edx, word ptr [esi + 4]
        movsx ecx, word ptr [esi + 6]
        movsx eax, word ptr [esi + 8]
        push eax
        movsx eax, word ptr [esi + 10]
        push eax
        mov  eax, edi
        mov  esi, dword ptr [eax]
        call dword ptr [esi + {V_SETBOUNDS:#x}]

        mov  esi, dword ptr [ebp - 0x14]          ; Caption, when the entry has one
        mov  edx, dword ptr [esi + 16]
        test edx, edx
        jz   sd_mk_next
        mov  eax, edi
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETTEXTBUF:#x}
        call esi
    sd_mk_next:
        inc  dword ptr [ebp - 0x10]
        jmp  sd_mk
    sd_mk_done:

        ; ---- per-kind initialisation ----
        mov  dword ptr [ebp - 0x10], 0
    sd_init:
        mov  eax, dword ptr [ebp - 0x10]
        cmp  eax, {n}
        jge  sd_init_done
        imul esi, eax, {ENTRY_SIZE}
        add  esi, {S['table']:#x}
        mov  edi, dword ptr [eax * 4 + {S['g_ctrls']:#x}]
        test edi, edi
        jz   sd_init_next
        movzx eax, byte ptr [esi + 14]            ; kind
        movzx ebx, byte ptr [esi + 15]            ; idx

        cmp  eax, {K_STRENGTH}
        jne  sd_i_race
        mov  dl, 0                                ; Checked := (idx = g_strength)
        cmp  ebx, dword ptr [{S['g_strength']:#x}]
        jne  sd_i_rb
        mov  dl, 1
    sd_i_rb:
        mov  eax, edi
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETCHECKED_RB:#x}
        call esi
        jmp  sd_init_next

    sd_i_race:
        cmp  eax, {K_RACE}
        jne  sd_i_combo
        call sd_racecount                         ; -> eax
        cmp  ebx, eax
        jl   sd_i_race_on
        mov  eax, edi                             ; no such race -> hide
        xor  edx, edx
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETVISIBLE:#x}
        call esi
        jmp  sd_init_next
    sd_i_race_on:
        mov  eax, dword ptr [{IAT_AOWHSSET:#x}]   ; caption := race resource name
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + {HSSET_RACERESLIST:#x}]
        mov  edx, ebx
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_GETRACERES:#x}
        call esi
        test eax, eax
        jz   sd_i_race_chk
        mov  edx, dword ptr [eax + {RACERES_NAME:#x}]
        test edx, edx
        jz   sd_i_race_chk
        mov  eax, edi
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETTEXTBUF:#x}
        call esi
    sd_i_race_chk:
        mov  ecx, ebx                             ; Checked := bit idx of g_racemask
        mov  eax, dword ptr [{S['g_racemask']:#x}]
        shr  eax, cl
        and  eax, 1
        mov  edx, eax
        mov  eax, edi
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETCHECKED_CB:#x}
        call esi
        jmp  sd_init_next

    sd_i_combo:
        cmp  eax, {K_COMBO}
        jne  sd_i_ok
        mov  eax, edi                             ; Style := csDropDownList
        mov  dl, {CS_DROPDOWNLIST}
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETSTYLE:#x}
        call esi
        xor  ebx, ebx                             ; add the item strings
    sd_cb_add:
        cmp  ebx, {len(BEHAVIOURS)}
        jge  sd_cb_sel
        mov  eax, dword ptr [edi + {F_CB_ITEMS:#x}]
        test eax, eax
        jz   sd_cb_sel
        mov  edx, dword ptr [ebx * 4 + {S['behav_ptr']:#x}]
        mov  esi, dword ptr [eax]
        call dword ptr [esi + {V_STRINGS_ADD:#x}]
        inc  ebx
        jmp  sd_cb_add
    sd_cb_sel:
        xor  ebx, ebx                             ; ItemIndex := row whose id = g_behavior
    sd_cb_find:
        cmp  ebx, {len(BEHAVIOURS)}
        jge  sd_cb_set
        movzx eax, byte ptr [ebx + {S['behav_id']:#x}]
        cmp  eax, dword ptr [{S['g_behavior']:#x}]
        je   sd_cb_set
        inc  ebx
        jmp  sd_cb_find
    sd_cb_set:
        cmp  ebx, {len(BEHAVIOURS)}
        jl   sd_cb_ok
        xor  ebx, ebx
    sd_cb_ok:
        mov  eax, edi
        mov  edx, ebx
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_SETITEMINDEX:#x}
        call esi
        jmp  sd_init_next

    sd_i_ok:
        cmp  eax, {K_OK}
        jne  sd_i_cancel
        mov  dword ptr [edi + {F_BTN_MODALRESULT:#x}], 1
        jmp  sd_init_next
    sd_i_cancel:
        cmp  eax, {K_CANCEL}
        jne  sd_init_next
        mov  dword ptr [edi + {F_BTN_MODALRESULT:#x}], 2
    sd_init_next:
        inc  dword ptr [ebp - 0x10]
        jmp  sd_init
    sd_init_done:

        ; ---- run modal ----
        mov  eax, dword ptr [ebp - 0x0C]
        call {T_SHOWMODAL:#x}
        mov  dword ptr [ebp - 0x18], eax
        cmp  eax, {MR_OK}
        jne  sd_free

        ; ---- read the controls back ----
        mov  dword ptr [ebp - 0x1C], 0            ; new race mask
        mov  dword ptr [ebp - 0x10], 0
    sd_rd:
        mov  eax, dword ptr [ebp - 0x10]
        cmp  eax, {n}
        jge  sd_rd_done
        imul esi, eax, {ENTRY_SIZE}
        add  esi, {S['table']:#x}
        mov  edi, dword ptr [eax * 4 + {S['g_ctrls']:#x}]
        test edi, edi
        jz   sd_rd_next
        movzx eax, byte ptr [esi + 14]
        movzx ebx, byte ptr [esi + 15]

        cmp  eax, {K_STRENGTH}
        jne  sd_r_race
        cmp  byte ptr [edi + {F_RB_CHECKED:#x}], 0
        jz   sd_rd_next
        mov  dword ptr [{S['g_strength']:#x}], ebx
        jmp  sd_rd_next

    sd_r_race:
        cmp  eax, {K_RACE}
        jne  sd_r_combo
        call sd_racecount
        cmp  ebx, eax
        jge  sd_rd_next
        mov  eax, edi
        mov  esi, dword ptr [ebp - 0x04]
        add  esi, {VCL_BASE + R_GETCHECKED_CB:#x}
        call esi
        test al, al
        jz   sd_rd_next
        mov  ecx, ebx
        mov  eax, 1
        shl  eax, cl
        or   dword ptr [ebp - 0x1C], eax
        jmp  sd_rd_next

    sd_r_combo:
        cmp  eax, {K_COMBO}
        jne  sd_rd_next
        mov  eax, edi
        call {T_GETITEMINDEX:#x}
        test eax, eax
        js   sd_rd_next
        cmp  eax, {len(BEHAVIOURS)}
        jge  sd_rd_next
        movzx eax, byte ptr [eax + {S['behav_id']:#x}]
        mov  dword ptr [{S['g_behavior']:#x}], eax
    sd_rd_next:
        inc  dword ptr [ebp - 0x10]
        jmp  sd_rd
    sd_rd_done:
        mov  eax, dword ptr [ebp - 0x1C]          ; what you tick is what you get -- ticking
        mov  dword ptr [{S['g_racemask']:#x}], eax ; nothing is a valid "empty stack" choice

    sd_free:
        mov  eax, dword ptr [ebp - 0x0C]
        call {T_FREE:#x}
    sd_done:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret

; number of races in the mapset's race resource list, clamped to MAX_RACES -> EAX
sd_racecount:
        push edx
        mov  eax, dword ptr [{IAT_AOWHSSET:#x}]
        mov  eax, dword ptr [eax]
        test eax, eax
        jz   src_zero
        mov  eax, dword ptr [eax + {HSSET_RACERESLIST:#x}]
        test eax, eax
        jz   src_zero
        mov  eax, dword ptr [eax + 8]
        test eax, eax
        jz   src_zero
        mov  eax, dword ptr [eax + 8]
        cmp  eax, {MAX_RACES}
        jle  src_out
        mov  eax, {MAX_RACES}
        jmp  src_out
    src_zero:
        xor  eax, eax
    src_out:
        pop  edx
        ret

; ===================== Party button hook =====================
; Replaces the first 5 bytes of TMainForm.ArmyBtnClick:
;   push ebx / mov ebx,eax / mov eax,edx
armybtn_hook:
        push ebx
        mov  ebx, eax
        mov  eax, edx
        push eax
        push edx
        push ecx
        call show_dialog
        pop  ecx
        pop  edx
        pop  eax
        jmp  {0x42B6A1:#x}
"""
