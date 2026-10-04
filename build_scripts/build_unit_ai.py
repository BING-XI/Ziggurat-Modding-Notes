#!/usr/bin/env python
r"""
build_unit_ai.py -- tactical combat: SPACE hands the current selection to the combat AI until the AI
has nothing left to do with it, then the turn is the player's again; SPACE during a run, or clicking
Auto, cancels it.  RIGHT-CLICK arms the selected unit's first usable ability (ranged attack,
spellcasting, ...); with an ability already armed, or none usable, right-click is vanilla.
AoWTCPCK.dpl + AoWz.exe.
(Owner rulings 2026-10-03, v2: Space instead of right-click, no checkbox; right-click acts on the
selected unit wherever it is clicked.  v1 2026-09-27 was a "Unit AI" checkbox arming right-click on
an own unit; this script migrates a v1 install in place.)

VANILLA
    "Auto" is TTBWindow.AutoBtn (TAOWCheckBox, field +0x12C) with OnChange = AutoBtn2Click 0x457F48,
    which calls AoWTC.TTacticalCombatPlayer.SetAuto 0x430B68: player[+0xC] := checked, and
    TCAI.Reset 0x413574 when the seated side ([map+0xEC]) is the side to move ([map+0xED]).
    TAoWCombatMap.NewFrame 0x41C440 then drives TCAI ([map+0x118]) for any side whose player[+0xC]
    is set: state [cai+0x36] 0 -> BeginTurn, 1 -> ContinueTurn, 2 (the AI has nothing left) ->
    EndTurn(1) at 0x41C629.  While player[+0xC] is set the map ignores the mouse.
    TCAI.EvalBattle 0x418170 state 0 re-sorts every combat object on each action: own side and
    owner == [TCombatData+0x31] -> cai[+8], the units it moves (0x41842A); own side, other owner ->
    cai[+0xC], which is filled and logged and nothing else (0x4184AF); other side -> cai[+0x10].
    The selection is TCombatUnitSelectionControl [map+0x100]; its [+8] is a TMoveSettingsList
    (count = VMT+0x54, item = GetMoveSettings thunk 0x40275C), ms[+0x10] = TTacticalCombatUnitHS,
    whose [+0x1C] is the TCombatObject.
    TTCMapEvents.TCMapSeatedPlayerChanged 0x458B38 (the exe) re-syncs AutoBtn.Checked from
    player[+0xC]; it is the only listener on [map+0xF8].
    KEYS: TMWindow.MapWindowKeyDown 0x4512E4 (the exe) handles combat keys in a compare chain on
    the VK in AX: N/P SelectNextUnit, M MoveUnits, Ctrl+E / Ctrl+Enter EndTurn, arrows, PgUp/PgDn,
    F3-F8.  VK_SPACE (0x20) matches nothing and leaves by the out-of-range `jmp 0x45189C` at
    0x4513AB, which only VKs in 0x0D..0x26 that match no case reach.  Handled keys set
    [Sender+0x78] := -1 (Sender = [ebp-4]).
    ABILITIES: the unit panel's ability list (TTCUnit.UAbilLBMouseDown 0x434938) shows
    [tcu+0x40], a TList of entries whose [+4] is the ability id, in list order, and a left-click
    calls TTacticalCombatUnitHS.SelectAbility 0x422F0C (eax = tcu, edx = id).  SelectAbility
    clears [tcu+0x34] to -1, then applies every gate itself (seated side to move, unit has moves,
    entry index < [tcu+0x3C], full moves for target types 3..5 and for 0x34 Spellcasting) and on
    success stores the id in [tcu+0x34]; it returns the entry index or -1.
    RIGHT-CLICK on the battle map: TCombatUnitSelectionControl.MouseDownEvent 0x41EE28, after its
    own-turn and not-on-Auto gates, tests the button [mouse+0x10] == 1 at 0x41EE7F, then cancels the
    selected unit's armed ability (SelectAbility(-1) when [tcu+0x34] > -1) or else Unselects.

THIS SCRIPT
    DLL (all PIC, state in BSS page slack 0x46C800: +0 active, +4 player, +8 map, +0xC n,
    +0x10 TCombatObject[64]; +1 was v1's `armed` and is unused):
        cancel      if active: active := 0 and, for the same map, SetAuto(player, 0).
        space       (from the exe) active -> cancel; else start.
        start       the seated side is the side to move and its player is not on Auto -> snapshot
                    every TCombatObject of the selection, active := 1, SetAuto(player, 1).
        0x41EE7F    rclick (6 B): right button, a selected unit with no ability armed -> try
                    SelectAbility on each [tcu+0x40] entry in order; the first that sets [tcu+0x34]
                    ends MouseDownEvent (0x41F6D4).  Anything else -> vanilla right-click 0x41EE85.
        0x418421    filter (9 B): while active for this map and the side-to-move player, an own unit
                    not in the snapshot goes to cai[+0xC] (0x4184AF) instead of cai[+8].
        0x41C629    done (10 B): while active for this map and player, instead of EndTurn(1):
                    active := 0, SetAuto(player, 0), TCAI.Reset, fire [map+0xF8] so the exe
                    re-syncs Auto; resume 0x41C67F with the turn still the player's.
        0x41BAB8    SetSeatedCombatPlayer head (6 B): active := 0 at every combat start.  No
                    dereference: the saved player may be freed.
        0x41BB30    NewTurn head (6 B): if active for this map, active := 0, SetAuto(player, 0).
    Exe (absolute addresses; the exe never rebases), cave in .hcol 0x0062AA00:
        0x4513AB    key: the default jmp's rel32 -> cave.  Plain Space (no Shift/Ctrl/Alt) with a
                    combat map up -> DLL `space`, Sender[+0x78] := -1; then the vanilla 0x45189C.
        AutoBtn2Click published entry (code dword at VA 0x457281) -> DLL `cancel`, then vanilla.
        TCMapSeatedPlayerChanged entry (code dword at VA 0x4580B9) -> vanilla, then AutoBtn
                    unchecked while a run is active.
    The exe reaches the DLL by the rebase delta of an import it already has: [IAT 0x45EBAC] is the
    live SetAuto, so live X = [0x45EBAC] + (X - 0x430B68).

Rolls: none.  The AI runs locally exactly as under vanilla Auto; its actions travel as tokens.  The
snapshot and the active flag are local to the machine that pressed Space.

WHERE
    AoWTCPCK.dpl  code zone 0x43A700-0x43ABFF (exclusive), BSS 0x46C800-0x46C90F (no file bytes).
    AoWz.exe      .hcol 0x0062AA00-0x0062AAFF (exclusive), the 0x4513AB rel32, two published-method
                  dwords.  v1 grew .ibnr 0xD000 -> 0x17000 above build_taskbar_coords.py and
                  repointed that script's TTBWINDOW resource entry, field table and instance size;
                  v2 restores all of those and shrinks .ibnr back, so the coupling is gone.
    Apply order DLL then exe; --undo exe then DLL (the exe calls into the DLL zone).
    Any DLL hook that is a jmp into the zone counts as ours, so a retune rewrites in place.

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
import exe_patch as X

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
GETTCUNITHS, SELECTABILITY = 0x41D2E8, 0x422F0C
H_FILTER, VAN_FILTER, OWN, ALLY = 0x418421, bytes.fromhex("3a42310f8585000000"), 0x41842A, 0x4184AF
H_DONE, VAN_DONE, DONE_SKIP, DONE_RET = 0x41C629, bytes.fromhex("b2018b45fce831faffff"), 0x41C67F, 0x41C633
H_SEAT, VAN_SEAT, SEAT_RET = 0x41BAB8, bytes.fromhex("558bec83c4f8"), 0x41BABE
H_TURN, VAN_TURN, TURN_RET = 0x41BB30, bytes.fromhex("558bec83c49c"), 0x41BB36
H_RCLICK, VAN_RCLICK, LEFT, RIGHT, MD_EXIT = 0x41EE7F, bytes.fromhex("80781001753c"), 0x41EEC1, 0x41EE85, 0x41F6D4
EVALBATTLE, NEWFRAME, MOUSEDOWN = (0x418170, 0x41AFCD), (0x41C440, 0x41C69A), (0x41EE28, 0x41F6D9)

# ---- AoWz.exe ---------------------------------------------------------------
CAVE_EXE = (0x0062AA00, 0x0062AB00)
G_COMBATMAP_IAT = 0x45EBDC                        # exe import slot -> the DLL's combat-map variable
G_TBWINDOW, IAT_SETAUTO, AUTO_FIELD, VMT_SETCHECKED = 0x45B2C8, 0x45EBAC, 0x12C, 0xAC
H_KEY, KEY_DEFAULT, VK_SPACE = 0x4513AB, 0x45189C, 0x20
MT_CLICK_VA, VAN_CLICK = 0x457281, 0x457F48       # published-method code dwords
MT_SEAT_VA, VAN_SEATCHG = 0x4580B9, 0x458B38

# v1 (2026-09-27), kept only to migrate or undo it.  v1 grew .ibnr above build_taskbar_coords.py.
V1_IBNR_VA, V1_COORDS_SIZE, V1_SIZE = 0x00630000, 0xD000, 0x17000
V1_SITES = [  # (file offset or VA, old bytes, v1 bytes)
    ("fo", 0x731A0, struct.pack("<II", 0x233000, 0x8C53), struct.pack("<II", 0x23D000, 36698)),
    ("fo", 0x56080, struct.pack("<I", 0x63BC60), struct.pack("<I", 0x645F60)),
    ("fo", 0x56090, struct.pack("<I", 0x148), struct.pack("<I", 0x14C)),
    ("va", MT_CLICK_VA, struct.pack("<I", VAN_CLICK), struct.pack("<I", 0x646320)),
    ("va", MT_SEAT_VA, struct.pack("<I", VAN_SEATCHG), struct.pack("<I", 0x646360)),
]


def build_dll():
    """Returns [(name, va, blob)], the hooks, and the `space` / `cancel` entry VAs (the exe calls them)."""
    caves, va = [], ZONE[0]

    def put(name, src):
        nonlocal va
        b = asm(src(va), va)
        caves.append((name, va, b))
        at = va
        va = (va + len(b) + 15) & ~15
        return at

    bss_ptr = put("bss_ptr", lambda v: f"""
        call b1
    b1: pop ecx
        add ecx, {BSS - (v + 5):#x}
        ret""")
    cancel = put("cancel", lambda v: f"""
        push edi
        call {bss_ptr:#x}
        mov edi, ecx
        cmp byte ptr [edi], 0
        je c_out
        mov byte ptr [edi], 0
        mov eax, dword ptr [edi + {MAPVAR}]
        cmp eax, dword ptr [edi + 8]
        jne c_out
        mov eax, dword ptr [edi + 4]
        xor edx, edx
        call {SETAUTO:#x}
    c_out:
        pop edi
        ret""")
    start = put("start", lambda v: f"""
        push ebx
        push esi
        push edi
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
    space = put("space", lambda v: f"""
        call {bss_ptr:#x}
        cmp byte ptr [ecx], 0
        jne {cancel:#x}
        jmp {start:#x}""")
    rclick = put("rclick", lambda v: f"""
        cmp byte ptr [eax + 0x10], 1
        jne {LEFT:#x}
        mov eax, dword ptr [ebp - 4]
        call {GETTCUNITHS:#x}
        test eax, eax
        je {RIGHT:#x}
        cmp dword ptr [eax + 0x34], -1
        jg {RIGHT:#x}
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, dword ptr [ebx + 0x40]
        test esi, esi
        je r_van
        xor edi, edi
    r_loop:
        cmp edi, dword ptr [esi + 8]
        jge r_van
        mov eax, dword ptr [esi + 4]
        mov eax, dword ptr [eax + edi*4]
        test eax, eax
        je r_next
        mov edx, dword ptr [eax + 4]
        mov eax, ebx
        call {SELECTABILITY:#x}
        cmp dword ptr [ebx + 0x34], -1
        jg r_done
    r_next:
        inc edi
        jmp r_loop
    r_done:
        pop edi
        pop esi
        pop ebx
        jmp {MD_EXIT:#x}
    r_van:
        pop edi
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
    return caves, hooks, space, cancel


def zone_image(d, caves):
    zo = P.va2off(d, ZONE[0])
    img = bytearray(ZONE[1] - ZONE[0])
    for _n, va, b in caves:
        o = P.va2off(d, va) - zo
        img[o:o + len(b)] = b
    return bytes(img)


def hook_is_ours(cur, va, n):
    """Any version's hook: E9 into the zone, NOP-padded."""
    if len(cur) != n or cur[0] != 0xE9 or cur[5:] != b"\x90" * (n - 5):
        return False
    return ZONE[0] <= va + 5 + struct.unpack_from("<i", cur, 1)[0] < ZONE[1]


def dll_state(d, caves, hooks):
    states = []
    for va, van, new in hooks:
        o = P.va2off(d, va)
        cur = bytes(d[o:o + len(van)])
        states.append("vanilla" if cur == van else "installed" if cur == new
                      else "older" if hook_is_ours(cur, va, len(van)) else "FOREIGN " + cur.hex(" "))
    zo, zh = P.va2off(d, ZONE[0]), P.va2off(d, ZONE[1])
    zone = bytes(d[zo:zh])
    if all(s == "vanilla" for s in states) and not any(zone):
        st = "VANILLA"
    elif all(s == "installed" for s in states) and zone == zone_image(d, caves):
        st = "INSTALLED"
    elif all(s in ("vanilla", "installed", "older") for s in states):
        st = "OLDER"                     # our hooks/zone from another version: rewrite in place
    else:
        st = "MIXED"
    return st, states, zone


def dll_checks(d, hooks):
    rl = [v for va, van, _ in hooks for v in P.relocs_in(d, va, va + len(van))] + P.relocs_in(d, *ZONE)
    inner = []
    for va, van, _ in hooks:
        fn = {H_FILTER: EVALBATTLE, H_DONE: NEWFRAME, H_RCLICK: MOUSEDOWN}.get(va, (va, va + 0x40))
        inner += P.rel32_into(d, va, va + len(van)) + P.short_into(d, va, va + len(van), *fn)
    return rl, inner


# ---- exe half ---------------------------------------------------------------------------------
def build_exe_code(space, cancel):
    d_space = (space - SETAUTO) & 0xFFFFFFFF
    d_cancel = (cancel - SETAUTO) & 0xFFFFFFFF
    d_active = (BSS - SETAUTO) & 0xFFFFFFFF
    key = CAVE_EXE[0]
    b_key = asm(f"""
        cmp ax, {VK_SPACE:#x}
        jne {KEY_DEFAULT:#x}
        test byte ptr [ebp + 8], 7
        jne {KEY_DEFAULT:#x}
        mov eax, dword ptr [{G_COMBATMAP_IAT:#x}]
        cmp dword ptr [eax], 0
        je {KEY_DEFAULT:#x}
        mov ecx, dword ptr [{IAT_SETAUTO:#x}]
        add ecx, {d_space:#x}
        call ecx
        mov eax, dword ptr [ebp - 4]
        mov dword ptr [eax + 0x78], -1
        jmp {KEY_DEFAULT:#x}""", key)
    click = (key + len(b_key) + 15) & ~15
    b_click = asm(f"""
        push eax
        push edx
        mov ecx, dword ptr [{IAT_SETAUTO:#x}]
        add ecx, {d_cancel:#x}
        call ecx
        pop edx
        pop eax
        jmp {VAN_CLICK:#x}""", click)
    seat = (click + len(b_click) + 15) & ~15
    b_seat = asm(f"""
        call {VAN_SEATCHG:#x}
        mov edx, dword ptr [{IAT_SETAUTO:#x}]
        cmp byte ptr [edx + {d_active:#x}], 0
        je w_ret
        mov eax, dword ptr [{G_TBWINDOW:#x}]
        test eax, eax
        je w_ret
        mov eax, dword ptr [eax + {AUTO_FIELD:#x}]
        test eax, eax
        je w_ret
        xor edx, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {VMT_SETCHECKED:#x}]
    w_ret:
        ret""", seat)
    blob = bytearray(seat + len(b_seat) - key)
    blob[0:len(b_key)] = b_key
    blob[click - key:click - key + len(b_click)] = b_click
    blob[seat - key:seat - key + len(b_seat)] = b_seat
    assert key + len(blob) <= CAVE_EXE[1], "exe cave overflows its slot"
    return bytes(blob), key, click, seat


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
        return X.va2off(self.d, va)

    def ibnr(self):
        s = list(self.secs())
        n, va, vs, rs, ra, o = s[-1]
        assert n == b".ibnr" and va == V1_IBNR_VA - BASE, "%s: .ibnr is not the last section" % self.name
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
        struct.pack_into("<I", self.d, self.opt + 56, V1_IBNR_VA - BASE + size)

    def v1_sites(self):
        return [((o if kind == "fo" else self.off(o)), old, new) for kind, o, old, new in V1_SITES]


def exe_plan(x, space, cancel):
    d = x.d
    blob, key, click, seat = build_exe_code(space, cancel)
    sites = [
        (x.off(H_KEY), P.jmp_to(H_KEY, KEY_DEFAULT, 5), P.jmp_to(H_KEY, key, 5), "key default jmp"),
        (x.off(MT_CLICK_VA), struct.pack("<I", VAN_CLICK), struct.pack("<I", click), "AutoBtn2Click entry"),
        (x.off(MT_SEAT_VA), struct.pack("<I", VAN_SEATCHG), struct.pack("<I", seat), "TCMapSeatedPlayerChanged entry"),
    ]
    co = x.off(CAVE_EXE[0])
    region = bytes(d[co:co + CAVE_EXE[1] - CAVE_EXE[0]])
    img = blob + bytes(CAVE_EXE[1] - CAVE_EXE[0] - len(blob))
    st = []
    for off, old, new, _desc in sites:
        cur = bytes(d[off:off + len(old)])
        st.append("vanilla" if cur == old else "installed" if cur == new else "FOREIGN " + cur.hex())
    rs = x.ibnr()[1]
    v1 = rs == V1_SIZE and all(bytes(d[o:o + len(new)]) == new for o, _old, new in x.v1_sites())
    if v1 and st[0] == "vanilla" and not any(region):
        state = "V1"
    elif all(s == "vanilla" for s in st) and not any(region) and rs == V1_COORDS_SIZE:
        state = "VANILLA"
    elif all(s == "installed" for s in st) and region == img and rs == V1_COORDS_SIZE:
        state = "INSTALLED"
    else:
        state = "MIXED"
    return state, st, img, sites, (key, click, seat, len(blob))


def exe_undo_v1(x):
    for o, old, _new in x.v1_sites():
        x.d[o:o + len(old)] = old
    x.resize(V1_COORDS_SIZE)


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    print("build_unit_ai v2 (Space hands over the selection; right-click arms the first usable ability)")

    dd = bytearray(open(DLL, "rb").read())
    caves, hooks, space, cancel = build_dll()
    dst, dsts, zone = dll_state(dd, caves, hooks)
    print("  AoWTCPCK.dpl    %-9s  %s" % (dst, ", ".join(s.split()[0] for s in dsts)))
    if dst == "MIXED":
        sys.exit("ABORT: foreign bytes at a DLL hook: %s" % dsts)
    if dst == "VANILLA" and any(zone):
        sys.exit("ABORT: zone %08X-%08X is not zero" % ZONE)
    rl, inner = dll_checks(dd, hooks)
    print("    .reloc under hooks/zone: %s | jumps into a hook interior: %s"
          % (", ".join("%08X" % v for v in rl) or "none", ", ".join("%08X" % v for v in inner) or "none"))
    if rl or inner:
        sys.exit("ABORT: .reloc entry or interior jump conflicts with a hook")
    print("    caves: " + ", ".join("%s %08X (%d B)" % (n, va, len(b)) for n, va, b in caves)
          + " | ends %08X" % (caves[-1][1] + len(caves[-1][2])))

    plans = []
    for name in zigexe.EXES:
        x = Exe(name)
        state, st, img, sites, info = exe_plan(x, space, cancel)
        print("  %-15s %-9s  %s" % (x.name, state, ", ".join(s.split()[0] for s in st)))
        if state == "MIXED":
            sys.exit("ABORT: %s is neither vanilla, v1 nor v2 at its sites" % x.name)
        erl = X.relocs_in(x.d, H_KEY, H_KEY + 5)
        if erl:
            sys.exit("ABORT: .reloc entry under the key hook: %s" % erl)
        plans.append((x, state, img, sites, info))
    key, click, seat, n = plans[0][4]
    print("    exe cave: key %08X, auto_click %08X, seat_wrap %08X | ends %08X" % (key, click, seat, key + n))
    if "--dis" in sys.argv:
        show(caves)
        show([("exe cave", key, plans[0][2][:n])])
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return

    kill_aow()
    if apply_:
        if dst != "INSTALLED":
            img = zone_image(dd, caves)
            with open(DLL, "r+b") as f:
                f.seek(P.va2off(dd, ZONE[0]))
                f.write(img)
                for va, _van, new in hooks:
                    f.seek(P.va2off(dd, va))
                    f.write(new)
        for x, state, img, sites, _info in plans:
            if state == "INSTALLED":
                continue
            if state == "V1":
                exe_undo_v1(x)
            co = x.off(CAVE_EXE[0])
            x.d[co:co + len(img)] = img
            for off, _old, new, _desc in sites:
                x.d[off:off + len(new)] = new
            open(x.path, "wb").write(x.d)
    else:
        for x, state, img, sites, _info in plans:
            if state == "VANILLA":
                continue
            if state == "V1":
                exe_undo_v1(x)
            else:
                co = x.off(CAVE_EXE[0])
                x.d[co:co + len(img)] = bytes(len(img))
                for off, old, _new, _desc in sites:
                    x.d[off:off + len(old)] = old
            open(x.path, "wb").write(x.d)
        if dst != "VANILLA":
            with open(DLL, "r+b") as f:
                for va, van, _new in hooks:
                    f.seek(P.va2off(dd, va))
                    f.write(van)
                f.seek(P.va2off(dd, ZONE[0]))
                f.write(bytes(ZONE[1] - ZONE[0]))

    back = open(DLL, "rb").read()
    for va, van, new in hooks:
        o = P.va2off(back, va)
        assert back[o:o + len(van)] == (new if apply_ else van), "%08X did not stick" % va
    for name in zigexe.EXES:
        state = exe_plan(Exe(name), space, cancel)[0]
        assert state == ("INSTALLED" if apply_ else "VANILLA"), "%s reads %s after writing" % (name, state)
    print("\n%s AoWTCPCK.dpl and %s" % ("APPLIED to" if apply_ else "UNDONE on", ", ".join(zigexe.EXES)))


if __name__ == "__main__":
    main()
