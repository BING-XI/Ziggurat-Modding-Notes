#!/usr/bin/env python
r"""
build_unit_ai.py -- a "Unit AI" checkbox beside "Auto" in the tactical combat bar.  While it is
ticked, right-clicking one of your own units hands it to the AI -- or the whole selection, when the
clicked unit is part of it -- until the AI has nothing left to do with them; then the turn is the
player's again.  Unticked, right-click is vanilla.  AoWTCPCK.dpl + AoWz.exe.
(Owner rulings 2026-09-27: plain right-click on an own unit; the box arms the gesture; clicked unit,
or the selection if the clicked unit is in it.)

VANILLA
    "Auto" is TTBWindow.AutoBtn (TAOWCheckBox, field +0x12C) with OnChange = AutoBtn2Click 0x457F48,
    which calls AoWTC.TTacticalCombatPlayer.SetAuto 0x430B68: player[+0xC] := checked, and
    TCAI.Reset 0x413574 when the seated side ([map+0xEC]) is the side to move ([map+0xED]).
    TAoWCombatMap.NewFrame 0x41C440 then drives TCAI ([map+0x118]) for any side whose player[+0xC]
    is set: state [cai+0x36] 0 -> BeginTurn, 1 -> ContinueTurn, 2 (the AI has nothing left) ->
    EndTurn(1) at 0x41C629.  While player[+0xC] is set the map ignores the mouse (MouseDownEvent,
    MouseMoveEvent, UpdateCursor all test it).
    TCAI.EvalBattle 0x418170 state 0 re-sorts every combat object on each action: own side and
    owner == [TCombatData+0x31] -> cai[+8], the units it moves (0x41842A); own side, other owner ->
    cai[+0xC], which is filled and logged and nothing else (0x4184AF); other side -> cai[+0x10].
    The selection is TCombatUnitSelectionControl [map+0x100]; its [+8] is a TMoveSettingsList
    (count = VMT+0x54, item = GetMoveSettings thunk 0x40275C), ms[+0x10] = TTacticalCombatUnitHS,
    whose [+0x1C] is the TCombatObject.
    TTCMapEvents.TCMapSeatedPlayerChanged 0x458B38 (the exe) re-syncs AutoBtn.Checked from
    player[+0xC]; it is the only listener on [map+0xF8] (via TAoWCombatMapControl.
    SeatedPlayerChanged 0x436D54) and fires from SetSeatedCombatPlayer 0x41BAB8.
    TAOWCheckBox.SetChecked (VMT+0xAC, aowInt 0x59811B38) does NOT fire OnChange.
    Right-click on the battle map: TCombatUnitSelectionControl.MouseDownEvent 0x41EE28, after its
    own-turn and not-on-Auto gates, tests the THSMapMouse button [mouse+0x10] == 1 at 0x41EE7F and
    then cancels the selected unit's armed ability (SelectAbility(-1), when [tcu+0x34] > -1) or
    else Unselects (VMT+0x1C).  Nothing else in AoWTCPCK or HSEngine's map mouse reads the right
    button.  The unit under the cursor is found as left-click does (0x41EF79-0x41EFEB): mouse
    GetXhx/GetYhx, TMapContainer.GetField([map+0x10], x, y, level [map+0x88]), field VMT+0x80 with
    filter 0x220104 -> TTacticalCombatUnitHS; own when [hs+0x1C][+0x45] == [map+0xEC].

THIS SCRIPT
    Exe: the TTBWINDOW DFM gains `UnitAIBtn`, a clone of AutoBtn ("Unit AI", slot 4 of TCPnl:
    LeftOffPercent 56 / LeftOffset 8, one to the right of Auto) whose OnChange is the same
    AutoBtn2Click entry; field +0x148 appended (class index 9 = TAOWCheckBox), instance size
    0x148 -> 0x14C.  Two published-method entries are retargeted, no code bytes touched:
        AutoBtn2Click (code dword at VA 0x457281) -> uai_click: Sender == UnitAIBtn -> cmd(its
            Checked): 1 arms, 0 disarms and cancels a run; anything else (the Auto box) -> cmd(2),
            cancel a run only, then vanilla 0x457F48.  UnitAIBtn.Checked is re-read from the armed
            flag afterwards.
        TCMapSeatedPlayerChanged (code dword at VA 0x4580B9) -> seat_wrap: vanilla, then the same
            re-sync (and AutoBtn unchecked while a run is active).
    The exe reaches the DLL by the rebase delta of an import it already has: [IAT 0x45EBAC] is the
    live SetAuto, so live X = [0x45EBAC] + (X - 0x430B68).
    DLL (all PIC, state in BSS page slack 0x46C800: +0 active, +1 armed, +4 player, +8 map, +0xC n,
    +0x10 TCombatObject[64]).  `armed` persists across battles, as the checkbox does:
        cmd(al)     0 disarm + cancel, 1 arm, 2 cancel only.  Cancel: if active, active := 0 and
                    SetAuto(player, 0).
        start(edx)  the seated side is the side to move and its player is not on Auto -> snapshot
                    ([edx+0x1C] alone, or every TCombatObject of the selection when edx = 0),
                    active := 1, SetAuto(player, 1).
        0x41EE7F    rclick (6 B): right button, armed, no ability armed on the selected unit, and an
                    own unit under the cursor -> start(that unit, or 0 when IndexOfMoveObject finds
                    it in the selection) and leave MouseDownEvent (0x41F6D4) without deselecting.
                    Anything else -> vanilla right-click 0x41EE85.
        0x418421    filter (9 B): while active for this map and the side-to-move player, an own unit
                    not in the snapshot goes to cai[+0xC] (0x4184AF) instead of cai[+8].
        0x41C629    done (10 B): while active for this map and player, instead of EndTurn(1):
                    active := 0, SetAuto(player, 0), TCAI.Reset, fire [map+0xF8] so the exe
                    re-syncs Auto; resume 0x41C67F with the turn still the player's.
        0x41BAB8    SetSeatedCombatPlayer head (6 B): active := 0 -- runs at every combat start
                    before the event fires, so a flag left by a combat that ended mid-run never
                    reaches the next one.  No dereference: the saved player may be freed.
        0x41BB30    NewTurn head (6 B): if active for this map, active := 0, SetAuto(player, 0) --
                    a turn that ends mid-run (turn timer) does not leave the side on Auto.

Rolls: none.  The AI runs locally exactly as under vanilla Auto; its actions travel as tokens.

WHERE
    AoWTCPCK.dpl  code zone 0x43A700-0x43ABFF (exclusive), BSS 0x46C800-0x46C90F (no file bytes;
                  BSS VirtualSize is 0xA1, the rest of the page is loader-zeroed RW).
    AoWz.exe  tenant above build_taskbar_coords.py: grows .ibnr 0xD000 -> 0x17000
                  (SizeOfImage 0x23D000 -> 0x247000); grown DFM at 0x0063D000, then the field table,
                  then the code.  The resource entry, field-table pointer and instance size it
                  repoints are build_taskbar_coords.py's own sites, so that script reads FOREIGN and
                  refuses to --apply or --undo while this one is installed: --undo this first.
    Apply order DLL then exes; --undo exes then DLL (the exe calls into the DLL zone).

USAGE
    python build_unit_ai.py            verify / dry run
    python build_unit_ai.py --dis      also disassemble the caves
    python build_unit_ai.py --apply
    python build_unit_ai.py --undo
"""
import os, sys, struct
sys.dont_write_bytecode = True
import zigexe
import aowepack_patch as P
from aowepack_patch import asm, kill_aow, show

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BASE = 0x400000
DLL = os.path.join(GAME, "AoWTCPCK.dpl")
P.TARGET, P.IMAGE_BASE = DLL, BASE

# ---- AoWTCPCK.dpl --------------------------------------------------------------------------
ZONE = (0x0043A700, 0x0043AC00)
BSS, MAXN = 0x0046C800, 64
G_COMBATMAP = 0x0046C064
MAPVAR = G_COMBATMAP - BSS
GETPLAYERS, SETAUTO, CAI_RESET, ENDTURN = 0x430BF0, 0x430B68, 0x413574, 0x41C064
GETOBJECTS, GETMS, TRIGGER = 0x402634, 0x40275C, 0x401374
H_FILTER, VAN_FILTER, OWN, ALLY = 0x418421, bytes.fromhex("3a42310f8585000000"), 0x41842A, 0x4184AF
H_DONE, VAN_DONE, DONE_SKIP, DONE_RET = 0x41C629, bytes.fromhex("b2018b45fce831faffff"), 0x41C67F, 0x41C633
H_SEAT, VAN_SEAT, SEAT_RET = 0x41BAB8, bytes.fromhex("558bec83c4f8"), 0x41BABE
H_TURN, VAN_TURN, TURN_RET = 0x41BB30, bytes.fromhex("558bec83c49c"), 0x41BB36
GETXHX, GETYHX, GETFIELD, INDEXOFMO, GETTCUNITHS = 0x402164, 0x40216C, 0x401E6C, 0x402764, 0x41D2E8
UNIT_FILTER = 0x220104
H_RCLICK, VAN_RCLICK, LEFT, RIGHT, MD_EXIT = 0x41EE7F, bytes.fromhex("80781001753c"), 0x41EEC1, 0x41EE85, 0x41F6D4
EVALBATTLE, NEWFRAME, MOUSEDOWN = (0x418170, 0x41AFCD), (0x41C440, 0x41C69A), (0x41EE28, 0x41F6D9)

# ---- AoWz.exe ---------------------------------------------------------------
SEC = b".ibnr"
IBNR_VA, COORDS_SIZE, NEW_SIZE = 0x00630000, 0xD000, 0x17000
GROW_VA = IBNR_VA + COORDS_SIZE
RES_ENTRY_FO, VMT_FT_FO, VMT_SIZE_FO = 0x731A0, 0x56080, 0x56090
COORDS_RES = (0x233000, 0x8C53)                  # build_taskbar_coords.py's grown DFM
COORDS_FT, COORDS_FT_LEN, COORDS_FT_COUNT = 0x63BC60, 900, 61
OLD_INST, NEW_INST, NEW_FIELD, CLS_CHECKBOX = 0x148, 0x14C, 0x148, 9
AUTO_FIELD, CHECKED, VMT_SETCHECKED = 0x12C, 0xB0, 0xAC
G_TBWINDOW, IAT_SETAUTO = 0x45B2C8, 0x45EBAC
MT_CLICK_VA, VAN_CLICK = 0x457281, 0x457F48       # published-method code dwords
MT_SEAT_VA, VAN_SEATCHG = 0x4580B9, 0x458B38
BTN_NAME, BTN_TEXT = b"UnitAIBtn", b"Unit AI"
BTN_TIP = b"Toggles whether right-clicking your units hands them to the AI."
SLOT_PCT, SLOT_OFS = 56, 8


def blk(src, va):
    return asm(src, va)


def build_dll():
    """Returns [(name, va, blob)], the hooks and the cmd entry VA (the exe calls it)."""
    caves, va = [], ZONE[0]

    def put(name, src):
        nonlocal va
        b = blk(src(va), va)
        caves.append((name, va, b))
        at = va
        va = (va + len(b) + 15) & ~15
        return at

    bss_ptr = put("bss_ptr", lambda v: f"""
        call b1
    b1: pop ecx
        add ecx, {BSS - (v + 5):#x}
        ret""")
    cmd = put("cmd", lambda v: f"""
        push ebx
        push esi
        push edi
        mov bl, al
        call {bss_ptr:#x}
        mov edi, ecx
        cmp bl, 2
        je c_cancel
        mov byte ptr [edi + 1], bl
        test bl, bl
        jne c_out
    c_cancel:
        cmp byte ptr [edi], 0
        je c_out
        mov byte ptr [edi], 0
        mov esi, dword ptr [edi + {MAPVAR}]
        cmp esi, dword ptr [edi + 8]
        jne c_out
        mov eax, dword ptr [edi + 4]
        xor edx, edx
        call {SETAUTO:#x}
    c_out:
        pop edi
        pop esi
        pop ebx
        ret""")
    start = put("start", lambda v: f"""
        push ebx
        push esi
        push edi
        mov ebx, edx
        call {bss_ptr:#x}
        mov edi, ecx
        cmp byte ptr [edi], 0
        jne t_out
        mov esi, dword ptr [edi + {MAPVAR}]
        test esi, esi
        je t_out
        mov al, byte ptr [esi + 0xEC]
        test al, al
        js t_out
        cmp al, byte ptr [esi + 0xED]
        jne t_out
        cmp dword ptr [esi + 0xE4], 0
        je t_out
        mov dl, al
        mov eax, dword ptr [esi + 0xE0]
        call {GETPLAYERS:#x}
        test eax, eax
        je t_out
        cmp byte ptr [eax + 0xC], 0
        jne t_out
        mov dword ptr [edi + 4], eax
        mov dword ptr [edi + 0xC], 0
        test ebx, ebx
        je t_sel
        mov eax, dword ptr [ebx + 0x1C]
        test eax, eax
        je t_out
        mov dword ptr [edi + 0x10], eax
        mov dword ptr [edi + 0xC], 1
        jmp t_go
    t_sel:
        mov eax, dword ptr [esi + 0x100]
        test eax, eax
        je t_out
        mov ebx, dword ptr [eax + 8]
        test ebx, ebx
        je t_out
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        push eax
        xor ecx, ecx
        mov dword ptr [edi + 0xC], 0
    t_loop:
        cmp ecx, dword ptr [esp]
        jge t_end
        cmp dword ptr [edi + 0xC], {MAXN}
        jge t_end
        push ecx
        mov edx, ecx
        mov eax, ebx
        call {GETMS:#x}
        pop ecx
        test eax, eax
        je t_next
        mov eax, dword ptr [eax + 0x10]
        test eax, eax
        je t_next
        mov eax, dword ptr [eax + 0x1C]
        test eax, eax
        je t_next
        mov edx, dword ptr [edi + 0xC]
        mov dword ptr [edi + edx*4 + 0x10], eax
        inc dword ptr [edi + 0xC]
    t_next:
        inc ecx
        jmp t_loop
    t_end:
        pop eax
    t_go:
        cmp dword ptr [edi + 0xC], 0
        je t_out
        mov dword ptr [edi + 8], esi
        mov byte ptr [edi], 1
        mov eax, dword ptr [edi + 4]
        mov dl, 1
        call {SETAUTO:#x}
    t_out:
        pop edi
        pop esi
        pop ebx
        ret""")
    rclick = put("rclick", lambda v: f"""
        cmp byte ptr [eax + 0x10], 1
        jne {LEFT:#x}
        call {bss_ptr:#x}
        cmp byte ptr [ecx + 1], 0
        je {RIGHT:#x}
        mov eax, dword ptr [ebp - 4]
        call {GETTCUNITHS:#x}
        test eax, eax
        je r_look
        cmp dword ptr [eax + 0x34], -1
        jg {RIGHT:#x}
    r_look:
        push ebx
        push esi
        call {bss_ptr:#x}
        mov esi, dword ptr [ecx + {MAPVAR}]
        mov eax, dword ptr [esi + 0xC]
        call {GETXHX:#x}
        cmp eax, -1
        je r_van
        mov ebx, eax
        mov eax, dword ptr [esi + 0xC]
        call {GETYHX:#x}
        cmp eax, -1
        je r_van
        mov ecx, eax
        push dword ptr [esi + 0x88]
        mov edx, ebx
        mov eax, dword ptr [esi + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        je r_van
        mov edx, {UNIT_FILTER:#x}
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je r_van
        mov ebx, eax
        mov eax, dword ptr [ebx + 0x1C]
        test eax, eax
        je r_van
        mov al, byte ptr [eax + 0x45]
        cmp al, byte ptr [esi + 0xEC]
        jne r_van
        mov eax, dword ptr [ebp - 4]
        mov eax, dword ptr [eax + 8]
        mov edx, ebx
        call {INDEXOFMO:#x}
        xor edx, edx
        cmp eax, -1
        jne r_start
        mov edx, ebx
    r_start:
        call {start:#x}
        call {bss_ptr:#x}
        cmp byte ptr [ecx], 0
        je r_van
        pop esi
        pop ebx
        jmp {MD_EXIT:#x}
    r_van:
        pop esi
        pop ebx
        jmp {RIGHT:#x}""")
    filt = put("filter", lambda v: f"""
        cmp al, byte ptr [edx + 0x31]
        jne f_ally
        call {bss_ptr:#x}
        cmp byte ptr [ecx], 0
        je f_own
        push ebx
        mov ebx, ecx
        mov eax, dword ptr [ebx + {MAPVAR}]
        cmp eax, dword ptr [ebx + 8]
        jne f_own_pop
        mov dl, byte ptr [eax + 0xED]
        mov eax, dword ptr [eax + 0xE0]
        call {GETPLAYERS:#x}
        cmp eax, dword ptr [ebx + 4]
        jne f_own_pop
        mov eax, dword ptr [ebp - 0x68]
        mov eax, dword ptr [eax + 0xC]
        mov edx, dword ptr [ebp - 8]
        call {GETOBJECTS:#x}
        mov ecx, dword ptr [ebx + 0xC]
    f_lp:
        dec ecx
        js f_ally_pop
        cmp eax, dword ptr [ebx + ecx*4 + 0x10]
        jne f_lp
    f_own_pop:
        pop ebx
    f_own:
        jmp {OWN:#x}
    f_ally_pop:
        pop ebx
    f_ally:
        jmp {ALLY:#x}""")
    done = put("done", lambda v: f"""
        call {bss_ptr:#x}
        cmp byte ptr [ecx], 0
        je d_van
        push ebx
        mov ebx, ecx
        mov eax, dword ptr [ebp - 4]
        cmp eax, dword ptr [ebx + 8]
        jne d_van_pop
        mov dl, byte ptr [eax + 0xED]
        mov eax, dword ptr [eax + 0xE0]
        call {GETPLAYERS:#x}
        cmp eax, dword ptr [ebx + 4]
        jne d_van_pop
        mov byte ptr [ebx], 0
        xor edx, edx
        call {SETAUTO:#x}
        mov eax, dword ptr [ebp - 4]
        mov eax, dword ptr [eax + 0x118]
        call {CAI_RESET:#x}
        mov eax, dword ptr [ebp - 4]
        movsx edx, byte ptr [eax + 0xED]
        mov eax, dword ptr [eax + 0xF8]
        call {TRIGGER:#x}
        pop ebx
        jmp {DONE_SKIP:#x}
    d_van_pop:
        pop ebx
    d_van:
        mov dl, 1
        mov eax, dword ptr [ebp - 4]
        call {ENDTURN:#x}
        jmp {DONE_RET:#x}""")
    seat = put("seat", lambda v: f"""
        call {bss_ptr:#x}
        mov byte ptr [ecx], 0
        push ebp
        mov ebp, esp
        add esp, -8
        jmp {SEAT_RET:#x}""")
    turn = put("turn", lambda v: f"""
        push eax
        push edx
        call {bss_ptr:#x}
        cmp byte ptr [ecx], 0
        je n_go
        mov byte ptr [ecx], 0
        cmp eax, dword ptr [ecx + 8]
        jne n_go
        mov eax, dword ptr [ecx + 4]
        xor edx, edx
        call {SETAUTO:#x}
    n_go:
        pop edx
        pop eax
        push ebp
        mov ebp, esp
        add esp, -0x64
        jmp {TURN_RET:#x}""")
    assert va <= ZONE[1], "DLL caves overflow the zone"
    hooks = [(H_FILTER, VAN_FILTER, P.jmp_to(H_FILTER, filt, len(VAN_FILTER))),
             (H_DONE, VAN_DONE, P.jmp_to(H_DONE, done, len(VAN_DONE))),
             (H_SEAT, VAN_SEAT, P.jmp_to(H_SEAT, seat, len(VAN_SEAT))),
             (H_TURN, VAN_TURN, P.jmp_to(H_TURN, turn, len(VAN_TURN))),
             (H_RCLICK, VAN_RCLICK, P.jmp_to(H_RCLICK, rclick, len(VAN_RCLICK)))]
    return caves, hooks, cmd


def dll_state(d, caves, hooks):
    states = []
    for va, van, new in hooks:
        o = P.va2off(d, va)
        cur = bytes(d[o:o + len(van)])
        states.append("vanilla" if cur == van else "installed" if cur == new else "FOREIGN " + cur.hex(" "))
    zo, zh = P.va2off(d, ZONE[0]), P.va2off(d, ZONE[1])
    zone = bytes(d[zo:zh])
    ours = all(bytes(d[P.va2off(d, va):P.va2off(d, va) + len(b)]) == b for _n, va, b in caves)
    if all(s == "vanilla" for s in states) and not any(zone):
        st = "VANILLA"
    elif all(s == "installed" for s in states) and ours:
        st = "INSTALLED"
    else:
        st = "MIXED"
    return st, states, zone, ours


def dll_checks(d, hooks):
    rl = [v for va, van, _ in hooks for v in P.relocs_in(d, va, va + len(van))] + P.relocs_in(d, *ZONE)
    inner = []
    for va, van, _ in hooks:
        fn = {H_FILTER: EVALBATTLE, H_DONE: NEWFRAME, H_RCLICK: MOUSEDOWN}.get(va, (va, va + 0x40))
        inner += P.rel32_into(d, va, va + len(van)) + P.short_into(d, va, va + len(van), *fn)
    return rl, inner


# ---- exe half ---------------------------------------------------------------------------------
def ss(s):
    return bytes([len(s)]) + s


def obj_span(d, o):
    def skip_val(p):
        t = d[p]
        p += 1
        if t in (0, 8, 9, 13):
            return p
        if t == 1:
            while d[p] != 0:
                p = skip_val(p)
            return p + 1
        if t == 2:
            return p + 1
        if t == 3:
            return p + 2
        if t == 4:
            return p + 4
        if t == 5:
            return p + 10
        if t in (6, 7):
            return p + 1 + d[p]
        if t in (10, 12):
            return p + 4 + struct.unpack_from("<I", d, p)[0]
        if t == 11:
            while d[p] != 0:
                p += 1 + d[p]
            return p + 1
        raise ValueError("DFM value type %d at %#x" % (t, p))
    p = o + 1 + d[o]
    p += 1 + d[p]
    while d[p] != 0:
        p += 1 + d[p]
        p = skip_val(p)
    p += 1
    while d[p] != 0:
        p = obj_span(d, p)
    return p + 1


def build_dfm(dfm):
    key = b"\x0cTAOWCheckBox\x07AutoBtn"
    i = dfm.find(key)
    assert i >= 0 and dfm.count(key) == 1, "AutoBtn not found once"
    assert ss(BTN_NAME) not in dfm, "UnitAIBtn already in the DFM"
    e = obj_span(dfm, i)
    raw = dfm[i:e]
    out = raw[:13] + ss(BTN_NAME) + raw[13 + 8:]
    tip = b"Toggles whether your army fights under AI control."
    for old, new in ((b"\x04Text\x06\x04Auto", b"\x04Text\x06" + ss(BTN_TEXT)),
                     (b"\x06" + ss(tip), b"\x06" + ss(BTN_TIP)),
                     (b"\x18Alignment.LeftOffPercent\x02\x2a", b"\x18Alignment.LeftOffPercent\x02" + bytes([SLOT_PCT])),
                     (b"\x14Alignment.LeftOffset\x02\x06", b"\x14Alignment.LeftOffset\x02" + bytes([SLOT_OFS])),
                     (b"\x08OnChange\x07\x0dAutoBtn2Click", b"\x08OnChange\x07\x0dAutoBtn2Click"),
                     (b"\x07Checked\x08", b"\x07Checked\x08")):
        assert out.count(old) == 1, old
        out = out.replace(old, new)
    return dfm[:e] + out + dfm[e:]


def build_field_table(ft):
    out = bytearray(ft) + struct.pack("<IH", NEW_FIELD, CLS_CHECKBOX) + ss(BTN_NAME)
    struct.pack_into("<H", out, 0, COORDS_FT_COUNT + 1)
    return bytes(out)


def build_exe_code(va, cmd):
    d_cmd = (cmd - SETAUTO) & 0xFFFFFFFF
    d_active = (BSS - SETAUTO) & 0xFFFFFFFF
    d_armed = (BSS + 1 - SETAUTO) & 0xFFFFFFFF
    sync = va
    src_sync = f"""
        mov eax, dword ptr [esi + {NEW_FIELD:#x}]
        test eax, eax
        je s_ret
        mov edx, dword ptr [{IAT_SETAUTO:#x}]
        movzx edx, byte ptr [edx + {d_armed:#x}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {VMT_SETCHECKED:#x}]
    s_ret:
        ret"""
    b_sync = asm(src_sync, sync)
    click = (sync + len(b_sync) + 15) & ~15
    b_click = asm(f"""
        push ebx
        push esi
        mov esi, eax
        mov ebx, edx
        mov ecx, dword ptr [{IAT_SETAUTO:#x}]
        add ecx, {d_cmd:#x}
        cmp ebx, dword ptr [esi + {NEW_FIELD:#x}]
        jne c_auto
        mov al, byte ptr [ebx + {CHECKED:#x}]
        call ecx
        call {sync:#x}
        pop esi
        pop ebx
        ret
    c_auto:
        mov al, 2
        call ecx
        call {sync:#x}
        mov eax, esi
        mov edx, ebx
        pop esi
        pop ebx
        jmp {VAN_CLICK:#x}""", click)
    seat = (click + len(b_click) + 15) & ~15
    b_seat = asm(f"""
        call {VAN_SEATCHG:#x}
        push esi
        mov esi, dword ptr [{G_TBWINDOW:#x}]
        test esi, esi
        je w_ret
        call {sync:#x}
        mov edx, dword ptr [{IAT_SETAUTO:#x}]
        cmp byte ptr [edx + {d_active:#x}], 0
        je w_ret
        mov eax, dword ptr [esi + {AUTO_FIELD:#x}]
        test eax, eax
        je w_ret
        xor edx, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {VMT_SETCHECKED:#x}]
    w_ret:
        pop esi
        ret""", seat)
    blob = bytearray(seat + len(b_seat) - va)
    blob[0:len(b_sync)] = b_sync
    blob[click - va:click - va + len(b_click)] = b_click
    blob[seat - va:seat - va + len(b_seat)] = b_seat
    return bytes(blob), click, seat


class Exe:
    def __init__(self, name):
        self.name = name
        self.path = os.path.join(GAME, name)
        self.d = bytearray(open(self.path, "rb").read())
        d = self.d
        self.e = struct.unpack_from("<I", d, 0x3C)[0]
        self.nsec = struct.unpack_from("<H", d, self.e + 6)[0]
        self.opt = self.e + 24
        self.tbl = self.opt + struct.unpack_from("<H", d, self.e + 20)[0]

    def secs(self):
        for i in range(self.nsec):
            o = self.tbl + 40 * i
            vs, va, rs, ra = struct.unpack_from("<IIII", self.d, o + 8)
            yield self.d[o:o + 8].rstrip(b"\0"), va, vs, rs, ra, o

    def off(self, va):
        for _n, sva, vs, rs, ra, _o in self.secs():
            if sva <= va - BASE < sva + rs:
                return ra + va - BASE - sva
        sys.exit("ABORT: %s %08X has no file bytes" % (self.name, va))

    def ibnr(self):
        s = list(self.secs())
        n, va, vs, rs, ra, o = s[-1]
        assert n == SEC and va == IBNR_VA - BASE, "%s: .ibnr is not the last section" % self.name
        assert ra + rs == len(self.d), "%s: .ibnr does not run to EOF" % self.name
        return vs, rs, ra, o

    def resize(self, size):
        vs, rs, ra, hdr = self.ibnr()
        if size > rs:
            self.d += bytes(size - rs)
        else:
            del self.d[ra + size:]
        struct.pack_into("<I", self.d, hdr + 8, size)
        struct.pack_into("<I", self.d, hdr + 16, size)
        struct.pack_into("<I", self.d, self.opt + 56, IBNR_VA - BASE + size)


def exe_plan(x, cmd):
    d = x.d
    vs, rs, ra, _hdr = x.ibnr()
    assert rs in (COORDS_SIZE, NEW_SIZE), \
        "%s: .ibnr is %#x B, expected %#x (build_taskbar_coords.py applied) or %#x" % (x.name, rs, COORDS_SIZE, NEW_SIZE)
    o = x.off(BASE + COORDS_RES[0])
    dfm = bytes(d[o:o + COORDS_RES[1]])
    assert dfm[:4] == b"TPF0", "build_taskbar_coords.py's TTBWINDOW copy is not a DFM"
    fo = x.off(COORDS_FT)
    ft = bytes(d[fo:fo + COORDS_FT_LEN])
    assert struct.unpack_from("<H", ft, 0)[0] == COORDS_FT_COUNT, "unexpected TTBWindow field table"
    assert ft.endswith(struct.pack("<IH", 0x144, 4) + ss(b"CoordLbl"))
    new_dfm, new_ft = build_dfm(dfm), build_field_table(ft)
    off_ft = (len(new_dfm) + 15) & ~15
    off_code = (off_ft + len(new_ft) + 15) & ~15
    code, click, seat = build_exe_code(GROW_VA + off_code, cmd)
    blob = bytearray(off_code) + code
    blob[:len(new_dfm)] = new_dfm
    blob[off_ft:off_ft + len(new_ft)] = new_ft
    assert COORDS_SIZE + len(blob) <= NEW_SIZE, "blob %d B does not fit" % len(blob)
    sites = [
        (RES_ENTRY_FO, struct.pack("<II", *COORDS_RES), struct.pack("<II", GROW_VA - BASE, len(new_dfm)),
         "TTBWINDOW resource entry"),
        (VMT_FT_FO, struct.pack("<I", COORDS_FT), struct.pack("<I", GROW_VA + off_ft), "TTBWindow field table"),
        (VMT_SIZE_FO, struct.pack("<I", OLD_INST), struct.pack("<I", NEW_INST), "TTBWindow instance size"),
        (x.off(MT_CLICK_VA), struct.pack("<I", VAN_CLICK), struct.pack("<I", click), "AutoBtn2Click entry"),
        (x.off(MT_SEAT_VA), struct.pack("<I", VAN_SEATCHG), struct.pack("<I", seat), "TCMapSeatedPlayerChanged entry"),
    ]
    st = []
    for off, old, new, _desc in sites:
        cur = bytes(d[off:off + len(old)])
        st.append("vanilla" if cur == old else "installed" if cur == new else "FOREIGN " + cur.hex())
    grown = rs == NEW_SIZE
    region = bytes(d[ra + COORDS_SIZE:ra + COORDS_SIZE + len(blob)]) if grown else b""
    if all(s == "vanilla" for s in st) and not grown:
        state = "VANILLA"
    elif all(s == "installed" for s in st) and grown and region == bytes(blob):
        state = "INSTALLED"
    else:
        state = "MIXED"
    return state, st, bytes(blob), sites, (off_ft, off_code, click, seat, len(new_dfm))


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    print("build_unit_ai")

    dd = bytearray(open(DLL, "rb").read())
    caves, hooks, cmd = build_dll()
    dst, dsts, zone, ours = dll_state(dd, caves, hooks)
    print("  AoWTCPCK.dpl    %-9s  %s   zone %s" % (dst, ", ".join(s.split()[0] for s in dsts),
          "zero" if not any(zone) else "our caves" if ours else "NOT ZERO"))
    if any(s.startswith("FOREIGN") for s in dsts):
        sys.exit("ABORT: foreign bytes at a DLL hook: %s" % dsts)
    rl, inner = dll_checks(dd, hooks)
    print("    .reloc under hooks/zone: %s | jumps into a hook interior: %s"
          % (", ".join("%08X" % v for v in rl) or "none", ", ".join("%08X" % v for v in inner) or "none"))
    if rl or inner:
        sys.exit("ABORT: .reloc entry or interior jump conflicts with a hook")
    if dst == "VANILLA" and any(zone):
        sys.exit("ABORT: zone %08X-%08X is not zero" % ZONE)
    print("    caves: " + ", ".join("%s %08X (%d B)" % (n, va, len(b)) for n, va, b in caves)
          + " | ends %08X" % (caves[-1][1] + len(caves[-1][2])))

    exes = [Exe(n) for n in zigexe.EXES]
    plans = []
    for x in exes:
        state, st, blob, sites, info = exe_plan(x, cmd)
        print("  %-15s %-9s  %s" % (x.name, state, ", ".join(s.split()[0] for s in st)))
        if any(s.startswith("FOREIGN") for s in st):
            sys.exit("ABORT: foreign bytes at an exe site (is build_taskbar_coords.py installed?)")
        plans.append((x, state, blob, sites, info))
    off_ft, off_code, click, seat, dfm_len = plans[0][4]
    print("    DFM %d B (+%d) @%08X | field table @%08X | uai_click %08X | seat_wrap %08X | ends %08X"
          % (dfm_len, dfm_len - COORDS_RES[1], GROW_VA, GROW_VA + off_ft, click, seat,
             GROW_VA + len(plans[0][2])))
    if "--dis" in sys.argv:
        show(caves)
        show([("exe code", GROW_VA + off_code, plans[0][2][off_code:])])
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return

    kill_aow()
    if apply_:
        if dst != "INSTALLED":
            with open(DLL, "r+b") as f:
                zo, zh = P.va2off(dd, ZONE[0]), P.va2off(dd, ZONE[1])
                f.seek(zo)
                f.write(bytes(zh - zo))
                for _n, va, b in caves:
                    f.seek(P.va2off(dd, va))
                    f.write(b)
                for va, _van, new in hooks:
                    f.seek(P.va2off(dd, va))
                    f.write(new)
        for x, state, blob, sites, _info in plans:
            if state == "INSTALLED":
                continue
            if x.ibnr()[1] != NEW_SIZE:
                x.resize(NEW_SIZE)
            _vs, _rs, ra, _h = x.ibnr()
            x.d[ra + COORDS_SIZE:ra + NEW_SIZE] = bytes(NEW_SIZE - COORDS_SIZE)
            x.d[ra + COORDS_SIZE:ra + COORDS_SIZE + len(blob)] = blob
            for off, _old, new, _desc in sites:
                x.d[off:off + len(new)] = new
            open(x.path, "wb").write(x.d)
    else:
        for x, state, blob, sites, _info in plans:
            if state == "VANILLA":
                continue
            for off, old, _new, _desc in sites:
                x.d[off:off + len(old)] = old
            x.resize(COORDS_SIZE)
            open(x.path, "wb").write(x.d)
        if dst != "VANILLA":
            with open(DLL, "r+b") as f:
                for va, van, _new in hooks:
                    f.seek(P.va2off(dd, va))
                    f.write(van)
                zo, zh = P.va2off(dd, ZONE[0]), P.va2off(dd, ZONE[1])
                f.seek(zo)
                f.write(bytes(zh - zo))

    back = open(DLL, "rb").read()
    for va, van, new in hooks:
        o = P.va2off(back, va)
        assert back[o:o + len(van)] == (new if apply_ else van), "%08X did not stick" % va
    print("\n%s AoWTCPCK.dpl and %s" % ("APPLIED to" if apply_ else "UNDONE on", ", ".join(zigexe.EXES)))


if __name__ == "__main__":
    main()
