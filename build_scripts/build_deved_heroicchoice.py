#!/usr/bin/env python3
r"""
UNIT PROPERTIES GETS THREE "HEROIC" TABS AND AN "ALWAYS" TAB   (AoWDevEd.exe -> AoWzEd.exe)

Owner's design 2026-10-20: a unit type's heroic-medal choices are edited exactly like its medal
ability grants.  Unit Properties > Statistics > Rank Abilities gains four tabs after
None / Copper / Silver / Gold -- "Heroic 1", "Heroic 2", "Heroic 3", "Always".  Each Heroic tab
is an option: the same list and the same Edit button open the same Ability Editor on that
option's ability set, and six spinners beside the list hold the option's stat deltas (Attack,
Defense, Resistance, Damage, Hits, Moves; -10..+10).  An option holds at most three distinct
abilities: the Ability Editor's Add refuses a fourth on a Heroic tab, while adding an ability
the option already has still raises its level.  "Always" (tab G.ALWAYS_TAB) is the set every
heroic unit of the type gains besides its option: a plain ability list like a medal tab, no
spinners, no cap.  The data lives in TUnitResource (build_heroicchoice_data.py, which this
script requires) and is saved with Unitres.pfs.

    target   Ziggurat\AoWDevEd.exe          (then build_zigeditor.py --apply -> AoWzEd.exe)
    code     0x0050D200 .. 0x0050DFFF       `.mtb`, inside the DEAD TMAINFORM DFM master
             (file 0x108800), directly above build_deved_pngdrop.py's window.  The window
             holds no `TPF0` and no `\x08MaxValue\x02` (build_editor_spinners.py scans the
             file for it); its original bytes are embedded below and --undo restores them.
    data     0x00592F00 G_CAPDLG            `.tres` page slack (RWX, loader-zeroed, past
             VirtualSize 0x200; build_deved_abcolumns.py holds 0x592F10..0x592F1F)
    roll     NONE -- no random number is drawn or inherited.

THE FORM GROWS
    TUnitResourceEditForm instance size (VMT-0x1C, 0x004107D4) 0x2DC -> 0x30C:
    +0x2DC..+0x2F3 the six spinners, +0x2F4..+0x30B their labels.  Nothing inherits the form.
    Keeping the controls in the instance, not in globals, means a new form can never see a
    freed one's controls (the dangling-pointer trap build_deved_itemhpmv.py documents).

HOOKS                                          (ImageBase 0x400000, fixed; absolute operands)
    H1 0x004107D4  instance size 0x2DC -> 0x30C
    H2 0x00410F0C  FormCreate's `call 0x410F40` (fill tab 0) -> cave_formcreate: three tabs
                   added to AbilityRankTabs.Tabs ([tabs+0x118], TStrings.Add = VMT +0x34);
                   the form, Rank Abilities box and tab strip widened by DW; Edit, OK and
                   Cancel re-centred; the twelve controls built hidden (AOwner nil, parent =
                   the tab strip, OnChange = cave_spin with Data = the form); then the
                   original call.
    H3 0x004111F2  AbilityRankTabsChange's `call 0x410F40` -> cave_tabs: the original call
                   (lists the tab's set and stores the tab in [form+0x2D8]), then cave_sync:
                   on a Heroic tab the list leaves alClient for a fixed box and the twelve
                   controls show, each spinner loaded from its delta; on a medal tab the
                   list goes back to alClient and the controls hide.
    H4 0x00410FEB  AbilityBtnClick's `call ShowModal` -> cave_modal: G_CAPDLG = the Ability
                   Editor while it is modal for a Heroic tab, 0 again the moment it returns
                   (OK or Cancel), so the cap can never key on a freed dialog.
    S1 0x00410F5F  \  the four `mov r,[form+0x214] / mov r,[res+idx*4+0x38]` pairs (10 B
    S2 0x00410FD1   | each) -> `call r<n>` + 5 nop.  Tabs 0-3 still read +0x38+4*idx;
    S3 0x00410FFB   | tabs 4-6 read the option owners at +0x54/+0x58/+0x5C, tab 7 the
    S4 0x0041101F  /  Always owner at +0x74.  S1 is the list fill, S2-S4 the Edit button
                      (dialog source, assign-back, refresh).  The cap (H4) is tabs 4-6 only.
    H9 0x004106AE  TAbilitySelectionDlg.AddBtnClick's ExpandAbility call (16 B) -> `call
                   cave_add` + 11 nop: unless this dialog is G_CAPDLG and the owner already
                   holds MAX_ABILITIES abilities without this one, ExpandAbility as before.
    Audited by the script on every run: no .reloc entry in any hook window, and no branch
    anywhere in CODE lands strictly inside S1-S4 or H9.

VCL (all already imported; nothing added to .idata)
    TSpin IAT 0x0043357C, TLabel IAT 0x00432654, constructor VMT +0x24 (EAX=class, DL=1,
    ECX=AOwner nil), SetParent VMT +0x3C, SetBounds VMT +0x4C (EDX=L, ECX=T, push W, push H),
    TControl.SetVisible [0x004323A8], SetLeft [0x004323D0], SetWidth [0x004323C8],
    SetAlign [0x004323D8], SetText thunk 0x00401568, TSpin.SetValue / GetValue thunks
    0x004030E8 / 0x004030E0.  TSpin: MinValue +0x130, MaxValue +0x134, Increment +0x138,
    EditorEnabled +0x140, OnChange Code +0x128 / Data +0x12C.  TControl: Left +0x30,
    Width +0x38 (vcl30 RTTI).  TTabControl.Tabs = field +0x118 (vcl30 RTTI).  Writes go to
    [form+0x214], the resource the dialog edits -- the same object the medal tabs' ability
    edits go to, so OK and Cancel treat the deltas exactly as they treat abilities.

Couplings: requires build_heroicchoice_data.py (asserted: TUnitResource instance size 0x74).
build_copper_medal.py owns the DFM's Tabs.Strings (None/Copper/Silver/Gold); this adds its
three tabs at runtime and edits no DFM byte.  Undo this before build_heroicchoice_data.py.

    python build_scripts/build_deved_heroicchoice.py            dry run + state
    python build_scripts/build_deved_heroicchoice.py --apply    then: build_zigeditor.py --apply
    python build_scripts/build_deved_heroicchoice.py --undo     then: build_zigeditor.py --apply
    python build_scripts/build_deved_heroicchoice.py --dis
"""
import argparse, base64, hashlib, os, struct, subprocess, sys, zlib

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zigexe                       # noqa: E402
import heroicchoice as G              # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(GAME, zigexe.SRC_EDITOR)
LIVE = os.path.join(GAME, zigexe.LIVE_EDITOR)
DPL = os.path.join(GAME, "AoWEPACK.dpl")
BASE = 0x00400000

CAVE, CAVE_END, CAVE_FILE = 0x0050D200, 0x0050E000, 0x00108800
G_CAPDLG = 0x00592F00
WIN_SHA = "ae4ec96b70e68bc0"
WIN_ORIG_B64 = (
    "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")

# form layout (TUnitResourceEditForm field table at 0x00410874, TResourceEditForm at 0x0040BA30)
F_RES, F_GROUP1, F_TABS, F_LIST, F_BTN, F_CURTAB = 0x214, 0x23C, 0x2C8, 0x2CC, 0x2D0, 0x2D8
F_CANCEL, F_OK = 0x1E0, 0x1E4
F_SPINS, F_LABELS = 0x2DC, 0x2F4
INST_OLD, INST_NEW = 0x2DC, 0x30C
INSTSIZE_VA = 0x004107D4

# VCL
IAT_TSPIN, IAT_TLABEL = 0x0043357C, 0x00432654
IAT_SETVISIBLE, IAT_SETLEFT, IAT_SETWIDTH, IAT_SETALIGN = 0x004323A8, 0x004323D0, 0x004323C8, 0x004323D8
TH_SETTEXT, TH_SPIN_SET, TH_SPIN_GET, TH_SHOWMODAL = 0x00401568, 0x004030E8, 0x004030E0, 0x004012E8
FILL_TAB = 0x00410F40
AL_NONE, AL_CLIENT = 0, 5

# geometry (pixels; the tab strip's own client coordinates for its children)
DW = 280                                   # 8 tabs need ~400 px of strip; 185 -> 465
BTN_LEFT = (205 + DW - 66) // 2            # Edit, centred in the widened box
LIST_BOX = (4, 24, 180, 109)               # the list's own design-time box, now not alClient
SPIN_W, SPIN_H, LABEL_W, LABEL_H = 44, 22, 56, 13
ROWS = (30, 56, 82)
COLS = ((192, 254), (306, 355))            # (label x, spin x)
# display order -> (column, row, caption, delta field index in heroicchoice.STAT_FIELDS)
CONTROLS = [(0, 0, "Attack:", 0), (0, 1, "Defense:", 1), (0, 2, "Resistance:", 5),
            (1, 0, "Damage:", 2), (1, 1, "Hits:", 3), (1, 2, "Moves:", 4)]
TAB_CAPTIONS = ("Heroic 1", "Heroic 2", "Heroic 3", "Always")    # tabs 4..6, then G.ALWAYS_TAB

HOOKS = {   # name: (va, original bytes as read off the binary)
    "H1": (INSTSIZE_VA, struct.pack("<I", INST_OLD)),
    "H2": (0x00410F0C, bytes.fromhex("e82f000000")),
    "H3": (0x004111F2, bytes.fromhex("e849fdffff")),
    "H4": (0x00410FEB, bytes.fromhex("e8f802ffff")),
    "S1": (0x00410F5F, bytes.fromhex("8b86140200008b44b838")),
    "S2": (0x00410FD1, bytes.fromhex("8b93140200008b4c8238")),
    "S3": (0x00410FFB, bytes.fromhex("8b93140200008b448238")),
    "S4": (0x0041101F, bytes.fromhex("8b93140200008b448238")),
    "H9": (0x004106AE, bytes.fromhex("8bd08b8314020000"
                                     "8b08ff9194000000")),
}
INTERIOR = ("S1", "S2", "S3", "S4", "H9")


def asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


def lstr(s):
    """Delphi 3 AnsiString literal: refcount -1, length, chars, NUL.  Returns (blob, chars_off)."""
    raw = s.encode("latin1")
    blob = b"\xff\xff\xff\xff" + struct.pack("<I", len(raw)) + raw + b"\0"
    return blob + b"\0" * (-len(blob) % 4), 8


class Layout:
    """Places literals first (their addresses feed the code), then the routines in order."""

    def __init__(self):
        self.va, self.parts, self.sym = CAVE, [], {}

    def add(self, name, blob):
        self.sym[name] = self.va
        self.parts.append((name, self.va, blob))
        self.va = (self.va + len(blob) + 15) & ~15

    def blob(self):
        out = bytearray()
        for _n, va, b in self.parts:
            out += b"\xcc" * (va - CAVE - len(out)) + b
        assert CAVE + len(out) <= CAVE_END, "cave overflows its window"
        return bytes(out)


def build():
    L = Layout()
    # ---- literals ---------------------------------------------------------------------
    lit = {}
    for s in TAB_CAPTIONS + tuple(c[2] for c in CONTROLS):
        b, k = lstr(s)
        L.add("lit:" + s, b)
        lit[s] = L.sym["lit:" + s] + k
    L.add("fieldmap", bytes(c[3] for c in CONTROLS) + b"\0\0")
    fieldmap = L.sym["fieldmap"]

    # ---- r_owner: ECX = form, EDX = tab index -> EAX = that tab's owner -----------------
    L.add("r_owner", asm("""
        mov  eax, dword ptr [ecx + %d]
        cmp  edx, 4
        jae  opt
        mov  eax, dword ptr [eax + edx*4 + 0x38]
        ret
    opt:
        cmp  edx, %d
        jae  always
        mov  eax, dword ptr [eax + edx*4 + %d]
        ret
    always:
        mov  eax, dword ptr [eax + %d]
        ret
    """ % (F_RES, G.ALWAYS_TAB, G.OWNER_OFFS[0] - 16, G.ALWAYS_OFF), L.va))
    r_owner = L.sym["r_owner"]
    # S1: form ESI, idx EDI -> EAX.   S2: form EBX, idx EAX -> ECX.   S3/S4: -> EAX.
    L.add("r1", asm(f"mov ecx, esi\nmov edx, edi\njmp {r_owner:#x}", L.va))
    L.add("r2", asm(f"mov ecx, ebx\nmov edx, eax\ncall {r_owner:#x}\nmov ecx, eax\nret", L.va))
    L.add("r3", asm(f"mov ecx, ebx\nmov edx, eax\njmp {r_owner:#x}", L.va))

    # ---- cave_spin: OnChange.  EAX = Data = the form, EDX = Sender --------------------------
    L.add("cave_spin", asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        test ebx, ebx
        je   out
        movzx esi, byte ptr [ebx + {F_CURTAB:#x}]
        and  esi, 0x7f
        sub  esi, 4
        cmp  esi, 3
        jae  out
        xor  ecx, ecx
    find:
        cmp  dword ptr [ebx + ecx*4 + {F_SPINS:#x}], edx
        je   found
        inc  ecx
        cmp  ecx, 6
        jb   find
        jmp  out
    found:
        mov  edi, ecx
        mov  eax, edx
        call {TH_SPIN_GET:#x}
        cmp  eax, {G.DELTA_MIN}
        jge  lo_ok
        mov  eax, {G.DELTA_MIN}
    lo_ok:
        cmp  eax, {G.DELTA_MAX}
        jle  hi_ok
        mov  eax, {G.DELTA_MAX}
    hi_ok:
        mov  edx, dword ptr [ebx + {F_RES:#x}]
        test edx, edx
        je   out
        movzx ecx, byte ptr [edi + {fieldmap:#x}]
        imul esi, esi, {G.NSTATS}
        add  ecx, esi
        mov  byte ptr [edx + ecx + {G.STATS_OFF:#x}], al
    out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    cave_spin = L.sym["cave_spin"]

    # ---- cave_sync: EBX = form.  Show the option UI for a Heroic tab, else hide it ----------
    vis = "".join(f"""
        mov  eax, dword ptr [ebx + {F_SPINS + 4 * j:#x}]
        test eax, eax
        je   v{j}
        mov  edx, edi
        call dword ptr [{IAT_SETVISIBLE:#x}]
    v{j}:""" for j in range(12))
    load = "".join(f"""
        mov  eax, dword ptr [ebx + {F_SPINS + 4 * i:#x}]
        test eax, eax
        je   l{i}
        mov  edx, dword ptr [ebx + {F_RES:#x}]
        test edx, edx
        je   l{i}
        movsx edx, byte ptr [edx + esi + {G.STATS_OFF + CONTROLS[i][3]:#x}]
        call {TH_SPIN_SET:#x}
    l{i}:""" for i in range(6))
    lx, ly, lw, lh = LIST_BOX
    L.add("cave_sync", asm(f"""
        push esi
        push edi
        movzx esi, byte ptr [ebx + {F_CURTAB:#x}]
        and  esi, 0x7f
        sub  esi, 4
        xor  edi, edi
        cmp  esi, 3
        setb al
        movzx edi, al
        mov  eax, dword ptr [ebx + {F_LIST:#x}]
        test eax, eax
        je   list_done
        test edi, edi
        je   list_client
        mov  dl, {AL_NONE}
        call dword ptr [{IAT_SETALIGN:#x}]
        mov  eax, dword ptr [ebx + {F_LIST:#x}]
        push esi
        mov  esi, dword ptr [eax]
        push {lw}
        push {lh}
        mov  edx, {lx}
        mov  ecx, {ly}
        call dword ptr [esi + 0x4c]
        pop  esi
        jmp  list_done
    list_client:
        mov  dl, {AL_CLIENT}
        call dword ptr [{IAT_SETALIGN:#x}]
    list_done:
        {vis}
        test edi, edi
        je   done
        imul esi, esi, {G.NSTATS}
        {load}
    done:
        pop  edi
        pop  esi
        ret
    """, L.va))
    cave_sync = L.sym["cave_sync"]

    # ---- cave_tabs: AbilityRankTabsChange's fill call.  EAX = form, EDX = tab ---------------
    L.add("cave_tabs", asm(f"""
        push ebx
        mov  ebx, eax
        call {FILL_TAB:#x}
        call {cave_sync:#x}
        pop  ebx
        ret
    """, L.va))

    # ---- cave_formcreate: FormCreate's fill call.  EAX = form, EDX = 0 ---------------------
    tabs = "".join(f"""
        mov  eax, dword ptr [ebx + {F_TABS:#x}]
        mov  eax, dword ptr [eax + 0x118]
        mov  edx, {lit[s]:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x34]""" for s in TAB_CAPTIONS)
    widen = "".join(f"""
        mov  eax, {src}
        mov  edx, dword ptr [eax + 0x38]
        add  edx, {DW}
        call dword ptr [{IAT_SETWIDTH:#x}]""" for src in
                    ("ebx", f"dword ptr [ebx + {F_GROUP1:#x}]", f"dword ptr [ebx + {F_TABS:#x}]"))
    recentre = "".join(f"""
        mov  eax, dword ptr [ebx + {f:#x}]
        mov  edx, dword ptr [eax + 0x30]
        add  edx, {DW // 2}
        call dword ptr [{IAT_SETLEFT:#x}]""" for f in (F_OK, F_CANCEL))
    ctl = ""
    for i, (col, row, cap, _f) in enumerate(CONTROLS):
        lxx, sxx = COLS[col]
        y = ROWS[row]
        for kind, iat, slot, x, top, w, h in (
                ("lab", IAT_TLABEL, F_LABELS + 4 * i, lxx, y + 4, LABEL_W, LABEL_H),
                ("spn", IAT_TSPIN, F_SPINS + 4 * i, sxx, y, SPIN_W, SPIN_H)):
            ctl += f"""
        mov  eax, dword ptr [{iat:#x}]
        mov  dl, 1
        xor  ecx, ecx
        call dword ptr [eax + 0x24]
        mov  esi, eax
        mov  dword ptr [ebx + {slot:#x}], eax
        mov  edx, dword ptr [ebx + {F_TABS:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x3c]
        mov  eax, esi
        push {w}
        push {h}
        mov  edx, {x}
        mov  ecx, {top}
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x4c]
        mov  eax, esi
        xor  edx, edx
        call dword ptr [{IAT_SETVISIBLE:#x}]"""
            if kind == "lab":
                ctl += f"""
        mov  eax, esi
        mov  edx, {lit[cap]:#x}
        call {TH_SETTEXT:#x}"""
            else:
                ctl += f"""
        mov  dword ptr [esi + 0x130], {G.DELTA_MIN}
        mov  dword ptr [esi + 0x134], {G.DELTA_MAX}
        mov  dword ptr [esi + 0x138], 1
        mov  byte ptr [esi + 0x140], 0
        mov  dword ptr [esi + 0x128], {cave_spin:#x}
        mov  dword ptr [esi + 0x12c], ebx"""
    L.add("cave_formcreate", asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        {tabs}
        {widen}
        mov  eax, dword ptr [ebx + {F_BTN:#x}]
        mov  edx, {BTN_LEFT}
        call dword ptr [{IAT_SETLEFT:#x}]
        {recentre}
        {ctl}
        mov  eax, ebx
        xor  edx, edx
        call {FILL_TAB:#x}
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))

    # ---- cave_modal: AbilityBtnClick's ShowModal.  EAX = the Ability Editor, EBX = form ----
    L.add("cave_modal", asm(f"""
        movzx ecx, byte ptr [ebx + {F_CURTAB:#x}]
        and  ecx, 0x7f
        cmp  ecx, 4
        jb   plain
        cmp  ecx, {G.ALWAYS_TAB}
        jae  plain
        mov  dword ptr [{G_CAPDLG:#x}], eax
        jmp  show
    plain:
        mov  dword ptr [{G_CAPDLG:#x}], 0
    show:
        call {TH_SHOWMODAL:#x}
        mov  dword ptr [{G_CAPDLG:#x}], 0
        ret
    """, L.va))

    # ---- cave_add: AddBtnClick.  EAX = ability id, EBX = the dialog -------------------------
    L.add("cave_add", asm(f"""
        push esi
        push edi
        mov  esi, dword ptr [ebx + 0x214]
        test esi, esi
        je   out
        cmp  ebx, dword ptr [{G_CAPDLG:#x}]
        jne  expand
        mov  ecx, dword ptr [esi + 8]
        test ecx, ecx
        je   expand
        cmp  eax, dword ptr [esi + 0xc]
        jae  count
        bt   dword ptr [ecx], eax
        jb   expand
    count:
        xor  edi, edi
        xor  edx, edx
    cnt:
        cmp  edx, dword ptr [esi + 0xc]
        jae  counted
        bt   dword ptr [ecx], edx
        adc  edi, 0
        inc  edx
        jmp  cnt
    counted:
        cmp  edi, {G.MAX_ABILITIES}
        jae  out
    expand:
        mov  edx, eax
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x94]
    out:
        pop  edi
        pop  esi
        ret
    """, L.va))
    return L


def hook_bytes(L):
    s = L.sym
    call = lambda va, dst, n: b"\xe8" + struct.pack("<i", dst - (va + 5)) + b"\x90" * (n - 5)
    v = {k: va for k, (va, _o) in HOOKS.items()}
    return {
        "H1": struct.pack("<I", INST_NEW),
        "H2": call(v["H2"], s["cave_formcreate"], 5),
        "H3": call(v["H3"], s["cave_tabs"], 5),
        "H4": call(v["H4"], s["cave_modal"], 5),
        "S1": call(v["S1"], s["r1"], 10),
        "S2": call(v["S2"], s["r2"], 10),
        "S3": call(v["S3"], s["r3"], 10),
        "S4": call(v["S4"], s["r3"], 10),
        "H9": call(v["H9"], s["cave_add"], 16),
    }


class PE:
    def __init__(self, path):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        e = struct.unpack_from("<I", self.d, 0x3C)[0]
        n = struct.unpack_from("<H", self.d, e + 6)[0]
        opt = struct.unpack_from("<H", self.d, e + 20)[0]
        self.e = e
        self.secs = [(bytes(self.d[e + 24 + opt + 40 * i:e + 32 + opt + 40 * i]).rstrip(b"\0"),)
                     + struct.unpack_from("<IIII", self.d, e + 24 + opt + 40 * i + 8)
                     for i in range(n)]

    def off(self, va):
        rva = va - BASE
        for _nm, vs, vaddr, rs, raw in self.secs:
            if vaddr <= rva < vaddr + rs:
                return raw + rva - vaddr
        sys.exit("ABORT: VA %08X has no file bytes" % va)

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def relocs_in(self, lo, hi):
        rva, size = struct.unpack_from("<II", self.d, self.e + 24 + 136)
        out = []
        if not size:
            return out
        o = self.off(BASE + rva)
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
        for nm, vs, vaddr, rs, raw in self.secs:
            if nm == b"CODE":
                return BASE + vaddr, bytes(self.d[raw:raw + min(vs, rs)])


def interior_jumps(pe, windows):
    """rel32 call/jmp and capstone-decoded short/near branches anywhere in CODE landing strictly
    inside a window (the window's own instructions excluded)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    base, code = pe.code()
    hits = []
    for i in range(len(code) - 5):
        if code[i] in (0xE8, 0xE9):
            src = base + i
            t = src + 5 + struct.unpack_from("<i", code, i + 1)[0]
            for lo, hi in windows:
                if lo < t < hi:
                    hits.append(src)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for lo, hi in windows:
        fn_lo = lo - 0x200
        for ins in md.disasm(code[fn_lo - base:hi + 0x200 - base], fn_lo):
            if lo <= ins.address < hi:
                continue
            if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
                try:
                    t = int(ins.op_str, 16)
                except ValueError:
                    continue
                if lo < t < hi and ins.size < 5:
                    hits.append(ins.address)
    return sorted(set(hits))


def kill_aow():
    # ⚠ SCRATCH GUARD: AOW_GAME_DIR set => not the real install; never kill the user's game.
    if os.environ.get("AOW_GAME_DIR"):
        return
    for n in zigexe.LOCKING_PROCESSES:
        subprocess.run(["taskkill", "/F", "/IM", n + ".exe"], capture_output=True)


def data_layer_installed():
    d = open(DPL, "rb").read()
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        vs, vaddr, rs, raw = struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8)
        rva = 0x55710A48 - 0x55700000
        if vaddr <= rva < vaddr + rs:
            return struct.unpack_from("<I", d, raw + rva - vaddr)[0] == G.INSTSIZE
    return False


def state(pe, L, new):
    blob = L.blob()
    win = pe.read(CAVE, CAVE_END - CAVE)
    orig = zlib.decompress(base64.b64decode(WIN_ORIG_B64))
    assert hashlib.sha256(orig).hexdigest()[:16] == WIN_SHA, "embedded window is corrupt"
    if win == orig:
        cave = "original"
    elif win[:len(blob)] == blob and win[len(blob):] == orig[len(blob):]:
        cave = "ours"
    else:
        cave = "FOREIGN"
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
    print("build_deved_heroicchoice -- %s" % TARGET)
    print("  code window %08X-%08X: %s (%d B of %d used)" % (CAVE, CAVE_END, cave, len(L.blob()),
                                                          CAVE_END - CAVE))
    for k, st in hooks.items():
        print("  %-3s %08X  %s" % (k, HOOKS[k][0], st))
    windows = [(HOOKS[k][0], HOOKS[k][0] + len(HOOKS[k][1])) for k in HOOKS]
    rl = [v for lo, hi in windows for v in pe.relocs_in(lo, hi)] + pe.relocs_in(CAVE, CAVE_END)
    inner = interior_jumps(pe, [windows[list(HOOKS).index(k)] for k in INTERIOR])
    print("  .reloc under hooks/cave: %s" % (", ".join("%08X" % v for v in rl) or "none"))
    print("  jumps into a hook's interior: %s" % (", ".join("%08X" % v for v in inner) or "none"))
    print("  data layer (build_heroicchoice_data.py): %s" % ("installed" if data_layer_installed()
                                                           else "MISSING"))
    if os.path.exists(LIVE):
        lv = PE(LIVE)
        lc, lh, _ = state(lv, L, new)
        print("  %s (read-only): code %s, hooks %s" % (zigexe.LIVE_EDITOR, lc,
              "installed" if all(s == "installed" for s in lh.values()) else
              "vanilla" if all(s == "vanilla" for s in lh.values()) else "MIXED"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, va, b in L.parts:
            if name.startswith("lit:") or name == "fieldmap":
                print("\n  ---- %s @%08X  %s" % (name, va, b.hex(" ")))
                continue
            print("\n  ---- %s @%08X (%d B)" % (name, va, len(b)))
            for ins in md.disasm(b, va):
                print("    %08X  %-24s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))
    st = "VANILLA" if cave == "original" and all(s == "vanilla" for s in hooks.values()) else \
        "INSTALLED" if cave == "ours" and all(s == "installed" for s in hooks.values()) else "MIXED"
    print("state: %s" % st)
    if cave == "FOREIGN" or any(s.startswith("FOREIGN") for s in hooks.values()):
        sys.exit("ABORT: foreign bytes at the cave or a hook site")
    if rl or inner:
        sys.exit("ABORT: a .reloc entry or an interior jump conflicts with a hook")
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    if a.apply and not data_layer_installed():
        sys.exit("ABORT: build_heroicchoice_data.py is not installed in AoWEPACK.dpl")
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
    pe2 = PE(TARGET)
    c2, h2, _ = state(pe2, L, new)
    want = "installed" if a.apply else "vanilla"
    assert c2 == ("ours" if a.apply else "original") and all(s == want for s in h2.values()), \
        "write did not stick"
    print("\n%s" % ("APPLIED" if a.apply else "UNDONE -- hooks vanilla, window restored"))
    print("    !! NOW RUN:  python build_zigeditor.py --apply   (rebuilds %s)" % zigexe.LIVE_EDITOR)


if __name__ == "__main__":
    main()
