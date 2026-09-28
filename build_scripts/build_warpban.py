#!/usr/bin/env python3
r"""
WARP PARTY BAN -- a per-map "Disable Warp Party" switch  (AoWEPACK.dpl + AoWDevEd.exe)

A map or saved game can forbid casting Warp Party.  The switch is a checkbox on the editor's
Map Settings > Game tab; it is stored in the map/save itself, so a match in progress gets it by
opening its `.asg` in AoWzEd, ticking the box and saving.  Research is untouched: the spell can
still be researched and sits in the book, greyed, with the refusal as its reason.  Owner request
2026-09-27.

    targets  Ziggurat\AoWEPACK.dpl        (game AND editor load it)
             Ziggurat\AoWDevEd.exe        (then build_zigeditor.py --apply -> AoWzEd.exe)
    roll     none.  Nothing here draws from either generator; no pattern to name.

STORAGE -- one byte of vanilla padding, saved as property id 0x61
  `TAoWHSMap+0x193`.  +0x190 and +0x191 are byte fields (0x191 = Demo Map, id 0x3E) and nothing
  in ANY module's code addresses +0x192 or +0x193 on the map: a capstone sweep of every exe and
  package for memory operands with those displacements found none in an AoW module (the only
  +0x192 hits are vcl30 word compares on other classes).  No FillChar/Move in the map's methods
  spans it.  InitInstance zero-fills it, so a new map starts "allowed".
  Streamed by `c_rw` with rwByte (stream VMT +0x30, EAX=stream EDX=ptr ECX=id).  rwByte ZEROES
  the target when the id is absent, so every older map and save reads 0 = allowed, and a map
  object reused for a second load cannot inherit the first file's switch.  Id 0x61: the class
  chain uses 2..7 and 0xB..0x3F (TAoWHSMap.ReadWrite + THSMap.ReadWrite), build_maplevel4.py
  adds 0x60, TEObject.ReadWrite writes nothing.

  H1  0x55777239  TAoWHSMap.ReadWrite, the Demo Map property's first two instructions
                  8D 93 91 01 00 00 B9 3E 00 00 00   lea edx,[ebx+0x191] / mov ecx,0x3E
               -> E9 <c_rw> 90 90 90 90 90 90
      c_rw streams +0x193 as 0x61, replays the two instructions and jumps to 0x55777244
      (`mov eax,esi`).  The site is unconditional (every stream mode reaches it), holds no
      .reloc entry, and no jump lands inside it.  EBX = map, ESI = stream; EDI is reloaded by
      the host at 0x55777246, so clobbering it is free.

THE GATE -- Warp Party's own CanActivate slot
  H2  0x557E9634  TWarpParty VMT (0x557E95CC) +0x68, CanActivate: 0x557792D0 (TSpell.CanActivate,
                  inherited) -> c_ban.  The slot keeps its .reloc entry: the new value is another
                  address inside this image, so the rebase delta still applies.
  Every strategic cast reaches CanActivate through this slot -- the cast book's offer, the exe's
  THero.CastSpell re-check at execution, and unit spellcasting (06-unit-spellcasting.md) -- so
  one slot covers them all.  Only TWarpParty is affected; no other class inherits this VMT.
  c_ban: if [AoWHSMap] is non-nil and map+0x193 != 0, Reason := TranslateRStr(MSG) and return
  False; otherwise tail-jump to TSpell.CanActivate, so Astral Ward (build_spellward_rescope.py,
  whose cave sits INSIDE TSpell.CanActivate) still applies when the map allows the spell.
  CanActivate is register-only (EAX self, EDX, ECX = var Reason), so c_ban needs no frame.
  The map global is read through a call/pop anchor (PIC).  The AI never casts Warp Party
  (its AIPrefetchCastSpellActions is the TSpell stub), so no AI path needs gating.
  MSG = "Warp Party is disabled on this map".  TranslateRStr falls back to the English text when
  Dict has no row for it.

THE EDITOR -- a checkbox on Map Settings > Game (TGameSettingsDlg, embedded by
build_deved_gamesettings_tab.py)
  AoWDevEd.exe has no free file-backed executable bytes (every section tail is claimed), so
  the code lives in the DLL and the exe carries only a 14-byte stub:
    S   0x0042EFF0  push dword [0x0043289C] / add dword [esp], ed_disp-0x558FA040 / ret
        [0x0043289C] is the exe's data import of AoWE.AoWHSMap (runtime &map global), and the
        global and ed_disp rebase together, so the sum is ed_disp's runtime address.  `ret`
        leaves the site's own return address on the stack: ed_disp is entered exactly as if
        the site had called it.  It lives in CODE's raw tail (vanilla ends 'AoWEd',0 at
        0x0042EFED); CODE VirtualSize is raised 0x2DFF0 -> 0x2E000 (= SizeOfRawData, same
        page, SizeOfImage unchanged) so the loader maps it.  The absolute 0x0043289C carries
        no .reloc entry: AoWDevEd.exe is fixed-base (precedent: build_levelset.py's stubs).
    E1  0x0042DF21  TGameSettingsDlg.FormCreate's last call, `call 0x0042DD14` -> call S
    E2  0x0042E103  TGameSettingsDlg.OKBtnClick's `call THSMap.SetModified` -> call S
        (reached on both of OKBtnClick's paths; EAX = map there)
  ed_disp dispatches on the return address: 0x0042DF26 -> ed_create, else ed_commit.
  ⚠ FormCreate runs TWICE per Map Settings dialog: once as OnCreate, once more from
  build_deved_gamesettings_tab.py's cave_build (0x0058F2F9, re-seeding after the reparent).
  Measured live: without a guard the tab carried two stacked checkboxes.  ed_create therefore
  builds only when G_CB is not in the dialog's own Components list (TComponent.FComponents
  +0x10; TList FList +4, FCount +8, read from vcl30), and re-seeds the tick on every call.  A
  bare `G_CB != 0` test would be wrong: the heap hands a new dialog a freed one's address.
  ed_create runs 0x0042DD14, then TCheckBox.Create(owner = the dialog) through the IAT class
  ref 0x00432638 (VMT +0x24), SetParent(GeneralSheet = dlg+0x1F0) (+0x3C), SetBounds
  L128 T320 W170 H17 (+0x4C) -- the row under Demo Map (T292 H17) -- caption "Disable Warp
  Party" via TControl.SetText, and SetChecked(map+0x193 != 0).  The checkbox pointer goes to
  G_CB 0x004E0524 (.dlgd page slack, free per 12-re-toolchain.md).  ed_commit writes
  GetChecked into map+0x193 and tail-jumps to SetModified.  Slots verified against vcl30:
  +0x24 TCustomCheckBox.Create, +0x3C TControl.SetParent, +0x4C TWinControl.SetBounds.
  The ed_* code holds absolute EXE addresses only (fixed base); every DLL-internal reference
  is rel32 or anchor-relative, so the DLL caves stay position-independent.

LAYOUT  0x55851C00..0x55851DFF (exclusive, 362 B used)  MSG literal, CAP literal, c_rw, c_ban,
        ed_disp (ed_commit falls through from it, ed_create follows).

FORWARD HAZARDS
  * The exe stub jumps into the DLL: undoing the DLL half alone would leave the editor jumping
    into zeroes when the Game tab opens.  This script always undoes both halves together;
    re-run build_zigeditor.py --apply after --apply AND after --undo.
  * A game or editor running a DLL WITHOUT this patch drops id 0x61 when it re-saves (it does
    not write what it does not know).  Every player in a match must run the patched DLL, or
    the switch vanishes after the first unpatched turn.

MEASURED LIVE 2026-09-27 (AoWzEd, a copy of Save/autosave.asg)
  One checkbox on the Game tab; tick -> OK -> Save -> restart -> reopen reads ticked.  Ticked
  and unticked editor re-saves differ only in the map's top-level count (0x20 -> 0x21).

UNPROVEN
  * ⚠ An editor re-save of a GAME save is not the game's own save: the game wrote count 0x22,
    the editor 0x20, and the rest of the payload shifts.  Whether game state is lost is not
    established -- do not route a live match through the editor until it is.
  * The in-game refusal itself has not been seen.

USAGE   python build_warpban.py [--apply | --undo | --dis]    (then build_zigeditor.py --apply)
        --undo is surgical: restores H1/H2/E1/E2 and CODE VirtualSize, zeroes the DLL slot and
        the stub.  No snapshot is written.
"""
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
if not os.path.isdir(os.path.join(GAME, "Release")):
    sys.exit("ABORT: %s has no Release\\ -- not the mod directory" % GAME)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
EXE = os.path.join(GAME, "AoWDevEd.exe")
DLL_BASE, EXE_BASE = 0x55700000, 0x00400000

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---- shared facts ----------------------------------------------------------------------------
FLAG = 0x193                        # TAoWHSMap+0x193, vanilla padding
PROP_ID = 0x61
MAPGLOBAL = 0x558FA040              # AoWE.AoWHSMap (DLL BSS)
MAP_INSTSIZE_VA = 0x5570E858        # TAoWHSMap VMT - 0x1C

# ---- DLL -------------------------------------------------------------------------------------
SLOT = (0x55851C00, 0x55851E00)
H1_VA = 0x55777239
H1_VAN = bytes.fromhex("8d9391010000b93e000000")
H1_RET = 0x55777244
RW_FN = (0x55776D60, 0x557772A0)    # TAoWHSMap.ReadWrite
WP_VMT = 0x557E95CC
H2_VA = WP_VMT + 0x68
SPELL_CANACT = 0x557792D0
TRANSLATE = 0x557249FC
DLL_ASSERTS = [                      # (va, bytes) facts this design stands on
    (0x557EB0F3, bytes.fromhex("c7461022000000")),       # TWarpParty.Create: id := 0x22
    (WP_VMT + 0x20, struct.pack("<I", 0x557EB0A0)),      # slot +0x20 = TWarpParty.Create
    (WP_VMT + 0x6C, struct.pack("<I", 0x557EB454)),      # slot +0x6C = TWarpParty.Activate
    (TRANSLATE, bytes.fromhex("5356")),                  # AoWE.TranslateRStr: push ebx/push esi
    (SPELL_CANACT, bytes.fromhex("558bec6a006a00")),     # TSpell.CanActivate prologue
    (0x55777244, bytes.fromhex("8bc68b38ff5738")),       # host resumes: mov eax,esi / rwBool
]

# ---- EXE -------------------------------------------------------------------------------------
STUB = 0x0042EFF0
STUB_END = 0x0042F000
CODE_VSIZE_OLD, CODE_VSIZE_NEW = 0x2DFF0, 0x2E000
E1_VA, E1_ORIG = 0x0042DF21, 0x0042DD14
E2_VA, E2_ORIG = 0x0042E103, 0x00401FF0
E1_RET = E1_VA + 5
MAPSLOT = 0x0043289C                # exe data import: &AoWE.AoWHSMap
G_CB = 0x004E0524                   # .dlgd page slack
IAT = {                             # slot: expected import
    0x00432638: "VCL30.dpl!StdCtrls..TCheckBox",
    0x004325D0: "VCL30.dpl!StdCtrls.TCustomCheckBox.SetChecked",
    0x004325D4: "VCL30.dpl!StdCtrls.TCustomCheckBox.GetChecked",
    0x00432398: "VCL30.dpl!Controls.TControl.SetText",
    0x004329DC: "HSEPack.dpl!HSEngine.THSMap.SetModified",
    MAPSLOT: "AoWEPACK.dpl!AoWE.AoWHSMap",
}
DLG_SHEET = 0x1F0                   # TGameSettingsDlg.GeneralSheet (published field table)
CB_L, CB_T, CB_W, CB_H = 128, 320, 170, 17

MSG = "Warp Party is disabled on this map"
CAP = "Disable Warp Party"


def astr(s):
    b = s.encode("latin-1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def assemble(lines, base, fixed):
    """Assemble `lines` (labels end with ':') until label addresses settle.  `{expr}` is a
    Python expression over labels and `fixed`, substituted as hex before keystone sees it."""
    import re
    names = [ln[:-1] for ln in lines if ln.endswith(":")]
    labels = {n: base for n in names}
    for _ in range(8):
        va, out, new = base, bytearray(), {}
        env = dict(fixed)
        env.update(labels)
        for ln in lines:
            if ln.endswith(":"):
                new[ln[:-1]] = va
                continue
            src = re.sub(r"\{([^}]+)\}", lambda m: hex(eval(m.group(1), {}, env) & 0xFFFFFFFF), ln)
            enc = bytes(ks.asm(src, va)[0])
            out += enc
            va += len(enc)
        if new == labels:
            return bytes(out), labels
        labels = new
    sys.exit("BUG: assembly did not settle")


def build():
    msg_va = SLOT[0]
    cap_va = msg_va + ((len(astr(MSG)) + 3) & ~3)
    code_va = (cap_va + len(astr(CAP)) + 0xF) & ~0xF
    data = bytearray(astr(MSG))
    data += b"\0" * (cap_va - msg_va - len(data))
    data += astr(CAP)
    data += b"\0" * (code_va - msg_va - len(data))
    fx = dict(MAPG=MAPGLOBAL, MSGC=msg_va + 8, CAPC=cap_va + 8)
    lines = [
        # ---- c_rw: stream map+0x193 as id 0x61, replay the Demo Map setup -----------------
        "c_rw:",
        "lea edx, [ebx + %#x]" % FLAG,
        "mov ecx, %#x" % PROP_ID,
        "mov eax, esi",
        "mov edi, dword ptr [eax]",
        "call dword ptr [edi + 0x30]",
        "lea edx, [ebx + 0x191]",
        "mov ecx, 0x3e",
        "jmp %#x" % H1_RET,
        # ---- c_ban: TWarpParty.CanActivate --------------------------------------------------
        "c_ban:",
        "push eax",
        "call {a1}",
        "a1:",
        "pop eax",
        "mov eax, dword ptr [eax + {MAPG - a1}]",
        "test eax, eax",
        "je {ban_no}",
        "cmp byte ptr [eax + %#x], 0" % FLAG,
        "je {ban_no}",
        "pop eax",
        "mov edx, ecx",
        "call {a2}",
        "a2:",
        "pop eax",
        "add eax, {MSGC - a2}",
        "call %#x" % TRANSLATE,
        "xor eax, eax",
        "ret",
        "ban_no:",
        "pop eax",
        "jmp %#x" % SPELL_CANACT,
        # ---- ed_disp: entered from the exe stub, site return address on the stack ---------
        "ed_disp:",
        "cmp dword ptr [esp], %#x" % E1_RET,
        "je {ed_create}",
        # ed_commit: EAX = map
        "push eax",
        "mov eax, dword ptr [%#x]" % G_CB,
        "test eax, eax",
        "je {ed_c1}",
        "call dword ptr [0x004325d4]",
        "mov edx, dword ptr [esp]",
        "mov byte ptr [edx + %#x], al" % FLAG,
        "ed_c1:",
        "pop eax",
        "jmp dword ptr [0x004329dc]",
        # ed_create: EAX = TGameSettingsDlg
        "ed_create:",
        "push ebx",
        "push esi",
        "push edi",
        "mov ebx, eax",
        "mov ecx, %#x" % E1_ORIG,
        "call ecx",
        # FormCreate runs TWICE per Map Settings dialog (OnCreate, then cave_build re-seeds):
        # build only if G_CB is not already one of THIS dialog's owned components.  A stale
        # G_CB from a freed dialog cannot be in a live Components list, even when the heap
        # hands the new dialog the old one's address.
        "mov esi, dword ptr [%#x]" % G_CB,
        "test esi, esi",
        "je {ed_new}",
        "mov ecx, dword ptr [ebx + 0x10]",          # TComponent.FComponents (TList or nil)
        "test ecx, ecx",
        "je {ed_new}",
        "mov edx, dword ptr [ecx + 8]",             # TList.FCount
        "mov ecx, dword ptr [ecx + 4]",             # TList.FList
        "ed_scan:",
        "dec edx",
        "js {ed_new}",
        "cmp dword ptr [ecx + edx*4], esi",
        "jne {ed_scan}",
        "jmp {ed_seed}",
        "ed_new:",
        "mov eax, dword ptr [0x00432638]",
        "mov ecx, ebx",
        "mov dl, 1",
        "call dword ptr [eax + 0x24]",
        "mov esi, eax",
        "mov dword ptr [%#x], eax" % G_CB,
        "mov edx, dword ptr [ebx + %#x]" % DLG_SHEET,
        "mov eax, esi",
        "mov edi, dword ptr [esi]",
        "call dword ptr [edi + 0x3c]",
        "mov eax, %d" % CB_W,
        "push eax",
        "mov eax, %d" % CB_H,
        "push eax",
        "mov eax, esi",
        "mov edx, %d" % CB_L,
        "mov ecx, %d" % CB_T,
        "call dword ptr [edi + 0x4c]",
        "call {a3}",
        "a3:",
        "pop edx",
        "add edx, {CAPC - a3}",
        "mov eax, esi",
        "call dword ptr [0x00432398]",
        "ed_seed:",
        "mov eax, dword ptr [%#x]" % MAPSLOT,
        "mov eax, dword ptr [eax]",
        "cmp byte ptr [eax + %#x], 0" % FLAG,
        "setne dl",
        "mov eax, esi",
        "call dword ptr [0x004325d0]",
        "pop edi",
        "pop esi",
        "pop ebx",
        "ret",
    ]
    code, lab = assemble(lines, code_va, fx)
    blob = bytes(data) + code
    assert SLOT[0] + len(blob) <= SLOT[1], "cave overruns its slot"
    check_dll_code(code, code_va, lab)
    return blob, lab


def check_dll_code(code, va, lab):
    ins = list(cs.disasm(code, va))
    assert sum(x.size for x in ins) == len(code), "cave does not fully disassemble"
    for x in ins:
        if "ptr [0x55" in x.op_str or x.op_str.startswith("0x55") and x.mnemonic in ("mov", "push"):
            sys.exit("ABORT: absolute DLL address at %08X: %s %s" % (x.address, x.mnemonic, x.op_str))
        if x.mnemonic == "push" and x.op_str.startswith("0x"):
            sys.exit("ABORT: push imm at %08X (keystone imm8 trap)" % x.address)
    # the anchors: each `call $+5` must be followed by the pop its displacement assumes
    for x in ins:
        if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
            assert x.address + 5 in (lab["a1"], lab["a2"], lab["a3"]), "stray call $+5"


def stub_bytes(ed_disp):
    k = (ed_disp - MAPGLOBAL) & 0xFFFFFFFF
    b = bytes(ks.asm("push dword ptr [%#x]; add dword ptr [esp], %#x; ret" % (MAPSLOT, k), STUB)[0])
    assert b[:6] == b"\xff\x35" + struct.pack("<I", MAPSLOT) and b[6:9] == b"\x81\x04\x24" \
        and struct.unpack_from("<I", b, 9)[0] == k and b[13:] == b"\xc3", "stub encoding"
    return b


# ---- PE helpers --------------------------------------------------------------------------------
def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    st = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    return e, st, [(st + 40 * i,) + struct.unpack_from("<IIII", d, st + 40 * i + 8) for i in range(nsec)]


def va2off(d, base, va):
    for _h, vsz, vaddr, rsz, raw in sections(d)[2]:
        if vaddr <= va - base < vaddr + max(vsz, rsz):
            return raw + va - base - vaddr
    sys.exit("ABORT: %08X is in no section" % va)


def relocs(d, base):
    e = sections(d)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    out = set()
    if not size:
        return out
    o = va2off(d, base, base + rva)
    end = o + size
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


def reloc_hits(rl, lo, hi):
    return sorted(v for v in rl if v < hi and v + 4 > lo)


def jumps_into(d, base, lo, hi, fn_lo, fn_hi):
    o = va2off(d, base, fn_lo)
    bad = []
    for x in cs.disasm(bytes(d[o:o + fn_hi - fn_lo]), fn_lo):
        if lo <= x.address < hi:
            continue
        if x.mnemonic.startswith("j") or x.mnemonic == "call":
            try:
                t = int(x.op_str, 16)
            except ValueError:
                continue
            if lo < t < hi:
                bad.append(x.address)
    return bad


def e8(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def kill_aow():
    for n in ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup"):
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"], capture_output=True).returncode == 0:
            print("  killed running %s.exe" % n)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Warp Party ban (per map)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    blob, lab = build()
    c_rw, c_ban, ed_disp = lab["c_rw"], lab["c_ban"], lab["ed_disp"]
    stub = stub_bytes(ed_disp)
    dll = bytearray(open(DLL, "rb").read())
    exe = bytearray(open(EXE, "rb").read())
    bad = []

    # ---------------- DLL facts ----------------
    print("AoWEPACK.dpl -- %s" % DLL)
    for va, want in DLL_ASSERTS:
        o = va2off(dll, DLL_BASE, va)
        if bytes(dll[o:o + len(want)]) != want:
            bad.append("DLL %08X expected %s, found %s" % (va, want.hex(" "), dll[o:o + len(want)].hex(" ")))
    inst = struct.unpack_from("<I", dll, va2off(dll, DLL_BASE, MAP_INSTSIZE_VA))[0]
    if inst < FLAG + 1:
        bad.append("TAoWHSMap instance size %#x does not cover +%#x" % (inst, FLAG))
    h1_new = b"\xE9" + struct.pack("<i", c_rw - (H1_VA + 5)) + b"\x90" * 6
    h2_van, h2_new = struct.pack("<I", SPELL_CANACT), struct.pack("<I", c_ban)
    dll_hooks = [("H1 ReadWrite", H1_VA, H1_VAN, h1_new), ("H2 VMT+0x68", H2_VA, h2_van, h2_new)]
    exe_hooks = [("E1 FormCreate", E1_VA, e8(E1_VA, E1_ORIG), e8(E1_VA, STUB)),
                 ("E2 OKBtnClick", E2_VA, e8(E2_VA, E2_ORIG), e8(E2_VA, STUB))]

    def states(d, base, hooks):
        out = []
        for name, va, van, new in hooks:
            o = va2off(d, base, va)
            cur = bytes(d[o:o + len(van)])
            st = "vanilla" if cur == van else "installed" if cur == new else "FOREIGN " + cur.hex(" ")
            print("  %-14s %08X  %s" % (name, va, st))
            out.append(st)
        return out

    dst = states(dll, DLL_BASE, dll_hooks)
    so, se = va2off(dll, DLL_BASE, SLOT[0]), va2off(dll, DLL_BASE, SLOT[1])
    zone = bytes(dll[so:se])
    dll_ours = zone == blob + b"\0" * (len(zone) - len(blob))
    # an earlier build of this cave: same literals, c_rw and c_ban (so H1/H2/the stub are
    # unchanged), different ed_* tail.  --apply re-tunes it in place; --undo zeroes it.
    pre = ed_disp - SLOT[0]
    dll_prior = not dll_ours and zone[:pre] == blob[:pre] and any(zone[pre:])
    print("  slot %08X-%08X  %s" % (SLOT[0], SLOT[1], "zero" if not any(zone) else "ours" if dll_ours
                                     else "an earlier build of this cave" if dll_prior else "NOT ZERO"))
    rl = relocs(dll, DLL_BASE)
    r1 = reloc_hits(rl, H1_VA, H1_VA + len(H1_VAN)) + reloc_hits(rl, *SLOT)
    if r1:
        bad.append(".reloc under H1/slot: " + ", ".join("%08X" % v for v in r1))
    if H2_VA not in rl:
        bad.append("expected .reloc entry at the VMT slot %08X is missing" % H2_VA)
    j1 = jumps_into(dll, DLL_BASE, H1_VA, H1_VA + len(H1_VAN), *RW_FN)
    if j1:
        bad.append("jumps into H1: " + ", ".join("%08X" % v for v in j1))

    # ---------------- EXE facts ----------------
    print("AoWDevEd.exe -- %s" % EXE)
    from aowsyms import get_symbols
    _pe, _b, _exp, iat = get_symbols("AoWDevEd.exe")
    for slot, want in IAT.items():
        if iat.get(slot) != want:
            bad.append("IAT %08X is %r, expected %r" % (slot, iat.get(slot), want))
    est = states(exe, EXE_BASE, exe_hooks)
    _e, st, secs = sections(exe)
    code_hdr, code_vsz, code_va, code_rsz, _raw = secs[0]
    print("  CODE VirtualSize %#x (raw %#x)" % (code_vsz, code_rsz))
    if code_vsz not in (CODE_VSIZE_OLD, CODE_VSIZE_NEW) or code_rsz != CODE_VSIZE_NEW \
            or EXE_BASE + code_va + code_rsz != STUB_END:
        bad.append("CODE section is not the measured shape")
    xo = va2off(exe, EXE_BASE, STUB)
    sz = bytes(exe[xo:xo + STUB_END - STUB])
    stub_ours = sz == stub + b"\0" * (len(sz) - len(stub))
    print("  stub %08X-%08X  %s" % (STUB, STUB_END, "zero" if not any(sz) else "ours" if stub_ours else "NOT ZERO"))
    tail = bytes(exe[xo - 8:xo])
    if tail != b"AoWEd\0\0\0":
        bad.append("CODE tail before the stub changed: %s" % tail.hex(" "))
    erl = relocs(exe, EXE_BASE)
    r2 = reloc_hits(erl, STUB, STUB_END) + reloc_hits(erl, E1_VA, E1_VA + 5) + reloc_hits(erl, E2_VA, E2_VA + 5)
    if r2:
        bad.append(".reloc under the exe sites/stub: " + ", ".join("%08X" % v for v in r2))

    if a.dis:
        print("\n  ---- DLL slot %08X (%d B; MSG, CAP, then code)" % (SLOT[0], len(blob)))
        for name in ("c_rw", "c_ban", "ed_disp"):
            print("    %-8s %08X" % (name, lab[name]))
        code_va0 = lab["c_rw"]
        for x in cs.disasm(blob[code_va0 - SLOT[0]:], code_va0):
            print("    %08X  %-24s %s %s" % (x.address, x.bytes.hex(" "), x.mnemonic, x.op_str))
        print("\n  ---- exe stub %08X" % STUB)
        for x in cs.disasm(stub, STUB):
            print("    %08X  %-24s %s %s" % (x.address, x.bytes.hex(" "), x.mnemonic, x.op_str))

    all_st = dst + est
    if any(s.startswith("FOREIGN") for s in all_st):
        bad.append("a hook site holds foreign bytes")
    if any(zone) and not (dll_ours or dll_prior):
        bad.append("DLL slot holds bytes that are not this script's cave")
    if any(sz) and not stub_ours:
        bad.append("exe stub zone holds bytes that are not this script's stub")
    if bad:
        print("\nABORT:\n  " + "\n  ".join(bad))
        sys.exit(1)

    installed = all(s == "installed" for s in all_st) and dll_ours and stub_ours \
        and code_vsz == CODE_VSIZE_NEW
    vanilla = all(s == "vanilla" for s in all_st) and not any(zone) and not any(sz) \
        and code_vsz == CODE_VSIZE_OLD
    print("\nstate: %s" % ("INSTALLED" if installed else "VANILLA" if vanilla else "MIXED"))
    if not (a.apply or a.undo):
        print("(dry run -- nothing written)")
        return
    if (a.apply and installed) or (a.undo and vanilla):
        print("already %s -- nothing to do" % ("installed" if a.apply else "vanilla"))
        return

    kill_aow()
    with open(DLL, "r+b") as f:
        f.seek(so)
        f.write(b"\0" * (se - so))
        if a.apply:
            f.seek(so)
            f.write(blob)
        for _n, va, van, new in dll_hooks:
            f.seek(va2off(dll, DLL_BASE, va))
            f.write(new if a.apply else van)
    with open(EXE, "r+b") as f:
        f.seek(xo)
        f.write(b"\0" * (STUB_END - STUB))
        if a.apply:
            f.seek(xo)
            f.write(stub)
        f.seek(code_hdr + 8)
        f.write(struct.pack("<I", CODE_VSIZE_NEW if a.apply else CODE_VSIZE_OLD))
        for _n, va, van, new in exe_hooks:
            f.seek(va2off(exe, EXE_BASE, va))
            f.write(new if a.apply else van)

    d2, x2 = open(DLL, "rb").read(), open(EXE, "rb").read()
    for _n, va, van, new in dll_hooks:
        o = va2off(d2, DLL_BASE, va)
        assert d2[o:o + len(van)] == (new if a.apply else van), "%08X did not stick" % va
    for _n, va, van, new in exe_hooks:
        o = va2off(x2, EXE_BASE, va)
        assert x2[o:o + len(van)] == (new if a.apply else van), "%08X did not stick" % va
    print("%s.  Now run: python build_scripts/build_zigeditor.py --apply"
          % ("APPLIED" if a.apply else "UNDONE -- sites restored, slot and stub zeroed"))


if __name__ == "__main__":
    main()
