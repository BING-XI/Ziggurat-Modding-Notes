#!/usr/bin/env python
r"""
build_wizardtower_dual_exe.py -- the Wizard's Tower dialog shows either of a tower's two offers
(AoWz.exe half of build_wizardtower_dual.py).  Owner's ruling 2026-10-25: one panel with a "Next"
toggle between the two offers.

THE FORM (TWIZARDSTOWERDLG, RCDATA at VA 0x00600D80 = file 0x1FCF80, 0x242F B; byte-identical to
  the root AoW.exe's, which is the --undo source).  Length-neutral rewrite:
    + a TAOWButton "NextBtn" (GenericB 19/22/25, Age10, "Next", WinLeft 116, WinTop 287,
      WinWidth 84, OnClick = BuyBtnClick: the form's method table has no spare name, so
      BuyBtnClick tells the two apart by Sender);
    - Buy WinWidth 120 -> 84, WinLeft / Alignment.LeftOffset 32 -> 22; Cancel WinWidth 120 -> 84,
      WinLeft 164 -> 210, Alignment.RightOffset 32 -> 22 (all same-width values);
    - paid for by the designer-only Left/Top of every component and the root's
      Left/Top/Height/Width (TComponent DesignInfo; readers keep defaults for absent props) and
      Buy's and Cancel's ToolTip (neither has ToolTipText).  The stream is zero-padded to its old
      length.  NextBtn has no Alignment: TAOWControl.Create leaves awNone/ahNone, so WinLeft/WinTop
      stand; it has no published field and is found by name (TComponent.FComponents +0x10, FName
      +8).

STATE  G_SLOT 0x0062D400 (dword): the offer on show, 0 = the tower's +0x34, 1 = its +0x38.

SITES
  open   0x0044F312  TheMapExecuteEventLog's `call TWizardsTowerDlg.Show` (rel32) -> cave_open:
         G_SLOT = 0, Show, then NextBtn visible only when the tower has a second offer.
  esi    0x0044B999  Show's `mov eax,[ebx+0x90] / mov esi,[eax+0x18]` (9 B) -> call cave_esi + 4
         nop: ESI = tower + 4*G_SLOT, so Show's two `[esi+0x34]` reads see the chosen offer (ESI
         is the tower nowhere else; BuyCost gets the real tower from EAX).
  cost   0x0044B9B9  Show's `call BuyCost` (rel32) -> cave_cost: G_SLOT 1 swaps +0x34/+0x38 around
         the call (local, synchronous, nothing else runs in between).
  icon   0x0044BCA5  SpellIcnDraw's `mov edx,[eax+0x34] / test edx,edx` -> call cave_icon.
  click  0x0044BBF8  BuyBtnClick's entry (5 B) -> jmp cave_click: Sender = NextBtn (anything but
         BuyBtn) flips G_SLOT when the tower has a second offer and re-runs Show (its extra
         AddRef of the event log released again); BuyBtn replays the entry.
  buy    0x0044BC35  BuyBtnClick's `call Buy` (rel32) -> cave_buy: G_SLOT 1 swaps around Buy,
         whose DLL hook writes the swapped-in spell into the token (TE+0x24), and the DLL's
         ExecuteTE matches it against both offers on every peer.

Slot 0x0062D400-0x0062D5FF (.hcol, RWX), exclusive.  Absolute addresses (the exe never rebases).
Needs build_wizardtower_dual.py applied (the token's TE+0x24).

    python build_scripts/build_wizardtower_dual_exe.py            dry run + state
    python build_scripts/build_wizardtower_dual_exe.py --apply
    python build_scripts/build_wizardtower_dual_exe.py --undo
    python build_scripts/build_wizardtower_dual_exe.py --dis
"""
import hashlib, os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
from exe_patch import asm, run, GAME
import dfm_edit as D

SLOT = (0x0062D400, 0x0062D600)
G_SLOT = 0x0062D400

DFM_VA, DFM_FILE, DFM_LEN = 0x00600D80, 0x1FCF80, 0x242F
DFM_SHA1 = "58d64d77c05f83ea1246cd03539a17d213318568"
ROOT_EXE = os.path.join(GAME, "..", "AoW.exe")

SHOW = 0x0044B95C
BUYCOST_THUNK, BUY_THUNK = 0x00402E34, 0x00402E3C
CLICK_RESUME = 0x0044BBFD

SITES = {
    "open":  (0x0044F312, bytes.fromhex("e845c6ffff")),
    "esi":   (0x0044B999, bytes.fromhex("8b83900000008b7018")),
    "cost":  (0x0044B9B9, bytes.fromhex("e87674fbff")),
    "icon":  (0x0044BCA5, bytes.fromhex("8b503485d2")),
    "click": (0x0044BBF8, bytes.fromhex("558bec6a00")),
    "buy":   (0x0044BC35, bytes.fromhex("e80272fbff")),
}


# ---- the form -----------------------------------------------------------------------------------
def ss(s):
    return D.shortstr(s)


def prop(name, typ, payload):
    return ss(name) + bytes([typ]) + payload


def next_button():
    i8 = lambda v: struct.pack("<b", v)
    i16 = lambda v: struct.pack("<h", v)
    b = ss("TAOWButton") + ss("NextBtn")
    b += prop("Priority", D.I32, struct.pack("<i", 99999))
    b += prop("WinLeft", D.I16, i16(116))
    b += prop("WinTop", D.I16, i16(287))
    b += prop("AOWWindow", D.IDENT, ss("Dlg"))
    b += prop("AOWFont", D.IDENT, ss("FontModule.Age10"))
    b += prop("BorderHeight", D.I8, i8(8))
    b += prop("BorderHeightSelected", D.I8, i8(9))
    b += prop("ILButton", D.IDENT, ss("IntGfxMod.GenericB"))
    b += prop("ILIndexDown", D.I8, i8(22))
    b += prop("ILIndexLit", D.I8, i8(25))
    b += prop("ILIndexUp", D.I8, i8(19))
    b += prop("Text", D.STR, ss("Next"))
    b += prop("TextColor", D.IDENT, ss("clBlack"))
    b += prop("TextSelColor", D.IDENT, ss("clWhite"))
    b += prop("WinWidth", D.I8, i8(84))
    b += prop("OnClick", D.IDENT, ss("BuyBtnClick"))
    return b + b"\x00\x00"


def build_dfm(van):
    w = D.walk(van)
    assert w.consumed == len(van), "the vanilla form does not walk cleanly"
    edits = []                     # (start, end, replacement)
    sets = {("BuyBtn", "WinWidth"): 84, ("CancelBtn", "WinWidth"): 84,
            ("BuyBtn", "WinLeft"): 22, ("BuyBtn", "Alignment.LeftOffset"): 22,
            ("CancelBtn", "WinLeft"): 210, ("CancelBtn", "Alignment.RightOffset"): 22}
    seen, dlg_at = set(), None
    for path, name, typ, s, e, val in w.props:
        comp = path.split("/")[-1]
        if name == "$class":
            if comp == "Dlg":
                dlg_at = s
            continue
        root = path == "/WizardsTowerDlg"
        if name in ("Left", "Top") or (root and name in ("Height", "Width")) or \
                (name == "ToolTip" and comp in ("BuyBtn", "CancelBtn")):
            edits.append((s, e, b""))
        elif (comp, name) in sets:
            v = sets[(comp, name)]
            nm = van[s:s + 1 + van[s]]
            body = van[s + 1 + van[s]:e]
            if body[0] == D.I8:
                rep = nm + bytes([D.I8]) + struct.pack("<b", v)
            elif body[0] == D.I16:
                rep = nm + bytes([D.I16]) + struct.pack("<h", v)
            else:
                raise AssertionError("%s.%s is not an Int8/Int16" % (comp, name))
            assert len(rep) == e - s, "%s.%s would change length" % (comp, name)
            edits.append((s, e, rep))
            seen.add((comp, name))
    assert seen == set(sets), "missing: %s" % (set(sets) - seen)
    assert dlg_at is not None
    # the object record of Dlg starts at its class name (no filer prefix in this form)
    assert van[dlg_at - 2:dlg_at] == b"\x00\x00", "Dlg is not preceded by BuyBtn's two terminators"
    edits.append((dlg_at, dlg_at, next_button()))
    out = bytearray(van)
    for s, e, rep in sorted(edits, key=lambda t: (t[0], t[1]), reverse=True):
        out[s:e] = rep
    assert len(out) <= len(van), "the form grew by %d B" % (len(out) - len(van))
    spare = len(van) - len(out)
    out += b"\x00" * spare
    w2 = D.walk(bytes(out))
    names = [(p.split("/")[-1], n) for p, n, *_ in w2.props]
    assert ("NextBtn", "OnClick") in names and ("Dlg", "$class") in names
    return bytes(out), spare


def vanilla_dfm():
    r = open(ROOT_EXE, "rb").read()[DFM_FILE:DFM_FILE + DFM_LEN]
    if hashlib.sha1(r).hexdigest() != DFM_SHA1:
        sys.exit("ABORT: the root AoW.exe's TWIZARDSTOWERDLG is not the expected vanilla form")
    return r


# ---- caves --------------------------------------------------------------------------------------
def build_vis(va):
    """EAX = dialog: NextBtn.Visible := the tower has a second offer."""
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, dword ptr [ebx + 0x10]
        test esi, esi
        je   v_out
        mov  edi, dword ptr [esi + 8]
    v_loop:
        dec  edi
        js   v_out
        mov  eax, dword ptr [esi + 4]
        mov  eax, dword ptr [eax + edi*4]
        test eax, eax
        je   v_loop
        mov  edx, dword ptr [eax + 8]
        test edx, edx
        je   v_loop
        cmp  dword ptr [edx - 4], 7
        jne  v_loop
        cmp  dword ptr [edx], 0x7478654e
        jne  v_loop
        cmp  dword ptr [edx + 4], 0x006e7442
        jne  v_loop
        xor  edx, edx
        mov  ecx, dword ptr [ebx + 0x90]
        test ecx, ecx
        je   v_set
        mov  ecx, dword ptr [ecx + 0x18]
        test ecx, ecx
        je   v_set
        cmp  dword ptr [ecx + 0x38], 0
        setne dl
    v_set:
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x6c]
    v_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def build_swap(va):
    return asm("""
        push edx
        mov  edx, dword ptr [eax + 0x34]
        xchg edx, dword ptr [eax + 0x38]
        mov  dword ptr [eax + 0x34], edx
        pop  edx
        ret
    """, va)


def build_open(va, at):
    """Replaces `call Show` (EAX dialog, EDX event log, [esp+4] callback code, [esp+8] data)."""
    return asm(f"""
        push ebx
        mov  ebx, eax
        mov  dword ptr [{G_SLOT:#x}], 0
        push dword ptr [esp + 0xc]
        push dword ptr [esp + 0xc]
        mov  eax, ebx
        call {SHOW:#x}
        mov  eax, ebx
        call {at['vis']:#x}
        pop  ebx
        ret  8
    """, va)


def build_esi(va):
    return asm(f"""
        mov  eax, dword ptr [ebx + 0x90]
        mov  esi, dword ptr [eax + 0x18]
        mov  ecx, dword ptr [{G_SLOT:#x}]
        and  ecx, 1
        lea  esi, [esi + ecx*4]
        ret
    """, va)


def build_cost(va, at):
    return asm(f"""
        cmp  dword ptr [{G_SLOT:#x}], 0
        je   {BUYCOST_THUNK:#x}
        push ebx
        mov  ebx, eax
        call {at['swap']:#x}
        mov  eax, ebx
        call {BUYCOST_THUNK:#x}
        push eax
        mov  eax, ebx
        call {at['swap']:#x}
        pop  eax
        pop  ebx
        ret
    """, va)


def build_icon(va):
    return asm(f"""
        mov  edx, dword ptr [{G_SLOT:#x}]
        and  edx, 1
        mov  edx, dword ptr [eax + edx*4 + 0x34]
        test edx, edx
        ret
    """, va)


def build_click(va, at):
    """BuyBtnClick(EAX dialog, EDX Sender)."""
    return asm(f"""
        test edx, edx
        je   k_buy
        cmp  edx, dword ptr [eax + 0x58]
        je   k_buy
        push ebx
        mov  ebx, eax
        mov  eax, dword ptr [ebx + 0x90]
        test eax, eax
        je   k_out
        mov  eax, dword ptr [eax + 0x18]
        test eax, eax
        je   k_out
        cmp  dword ptr [eax + 0x38], 0
        je   k_out
        xor  dword ptr [{G_SLOT:#x}], 1
        mov  eax, dword ptr [ebx + 0x90]
        push eax
        push dword ptr [ebx + 0x8c]
        push dword ptr [ebx + 0x88]
        mov  edx, eax
        mov  eax, ebx
        call {SHOW:#x}
        pop  eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        mov  eax, ebx
        call {at['vis']:#x}
    k_out:
        pop  ebx
        ret
    k_buy:
        push ebp
        mov  ebp, esp
        push 0
        jmp  {CLICK_RESUME:#x}
    """, va)


def build_buy(va, at):
    """Replaces BuyBtnClick's `call Buy` (EAX tower, DL player, ECX &error) -> AL."""
    return asm(f"""
        cmp  dword ptr [{G_SLOT:#x}], 0
        je   {BUY_THUNK:#x}
        push ebx
        mov  ebx, eax
        call {at['swap']:#x}
        mov  eax, ebx
        call {BUY_THUNK:#x}
        push eax
        mov  eax, ebx
        call {at['swap']:#x}
        pop  eax
        pop  ebx
        ret
    """, va)


def layout():
    caves, at, va = [], {}, SLOT[0] + 0x10

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("vis", build_vis(va))
    put("swap", build_swap(va))
    put("open", build_open(va, at))
    put("esi", build_esi(va))
    put("cost", build_cost(va, at))
    put("icon", build_icon(va))
    put("click", build_click(va, at))
    put("buy", build_buy(va, at))
    return at, caves


def main():
    at, caves = layout()
    rel = lambda src, dst, op: bytes([op]) + struct.pack("<i", dst - (src + 5))
    hooks = [
        (SITES["open"][0], SITES["open"][1], rel(SITES["open"][0], at["open"], 0xE8)),
        (SITES["esi"][0], SITES["esi"][1], rel(SITES["esi"][0], at["esi"], 0xE8) + b"\x90" * 4),
        (SITES["cost"][0], SITES["cost"][1], rel(SITES["cost"][0], at["cost"], 0xE8)),
        (SITES["icon"][0], SITES["icon"][1], rel(SITES["icon"][0], at["icon"], 0xE8)),
        (SITES["click"][0], SITES["click"][1], rel(SITES["click"][0], at["click"], 0xE9)),
        (SITES["buy"][0], SITES["buy"][1], rel(SITES["buy"][0], at["buy"], 0xE8)),
    ]
    van = vanilla_dfm()
    new, spare = build_dfm(van)
    print("  form: %d B, NextBtn %d B, %d B zero-padded" % (len(van), len(next_button()), spare))
    hooks.append((DFM_VA, van, new))
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in at.items()))
    run("build_wizardtower_dual_exe -- the two-offer tower dialog", hooks, caves, SLOT, sys.argv[1:])


if __name__ == "__main__":
    main()
