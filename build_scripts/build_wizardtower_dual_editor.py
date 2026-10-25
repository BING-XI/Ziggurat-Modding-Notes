#!/usr/bin/env python
r"""
build_wizardtower_dual_editor.py -- Wizard's Tower Properties (AoWDevEd.exe -> AoWzEd.exe): levels
become checkboxes and Life and Death can no longer both be ticked.  Editor half of
build_wizardtower_dual.py (owner's rulings 2026-10-25: level checkboxes; Life and Death exclusive;
existing towers keep their spheres; new towers get a random sphere set, which the DLL half's
cave_create does).

THE FORM (TWizardsTowerEditForm; EBX = form, ESI = tower [form+0x20C] at every site)
  ed_create  0x0041C8FF  FormCreate's last call, `call TCustomComboBox.SetItemIndex` (rel32) ->
             replays it, clears LevelRG's Items (TRadioGroup.FItems +0x120, TStrings.Clear
             VMT +0x40), builds four TCheckBox "Level 1".."Level 4" in LevelRG (Create VMT +0x24
             owner = form, SetParent +0x3C, SetBounds +0x4C at L16 T22+24n W80 H17) ticked from
             the tower's level set +0x3C (0 = the single level +0x33), chains them through Tag
             (LevelRG.Tag = Level 1, each Tag = the next), sets LifeCB's and DeathCB's OnClick
             (TControl +0xA4 code / +0xA8 data) to ed_ldclick, then runs the enable routine.
             The spheres are not touched here: a tower that already has both keeps them.
  ed_ok      0x0041CA8B  OKBtnClick's `call <enable routine 0x0041CACC>` -> writes the ticked
             levels into +0x3C (none ticked keeps the tower's set, or level 2) and the lowest one
             into +0x33 (vanilla's own write there is ItemIndex+1 = 0 once the items are gone),
             then the enable routine.
  ed_enable  0x0041CBB3  the enable routine's last `call TControl.SetEnabled` (rel32) -> replays
             it, then enables the level boxes when Random is chosen (RandomRB.Checked +0x11D).
             The routine also runs from FormCreate's own SetChecked before the boxes exist:
             LevelRG.Tag = 0 then, so nothing is touched.
  ed_ldclick ticking Life unticks Death and the other way round.

CODE  0x0050F000..0x0050F7FF  `.mtb`, inside the DEAD TMAINFORM DFM master (file 0x10A600), above
      build_deved_abcolumns.py's window ("free above it" in 12-re-toolchain.md).  Read + execute
      (build_deved_listarrows.py's bit); the AnsiString captions are refcount -1 literals, never
      written.  Original bytes embedded; --undo restores them.  No globals.  No RNG.

Patch source AoWDevEd.exe; then `build_zigeditor.py --apply` derives the live AoWzEd.exe.

    python build_scripts/build_wizardtower_dual_editor.py            dry run + state
    python build_scripts/build_wizardtower_dual_editor.py --apply    then build_zigeditor.py --apply
    python build_scripts/build_wizardtower_dual_editor.py --undo     then build_zigeditor.py --apply
    python build_scripts/build_wizardtower_dual_editor.py --dis
"""
import base64, hashlib, os, struct, sys, zlib
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zigexe                                               # noqa: E402
from exe_patch import asm, run, GAME, va2off, sections, show     # noqa: E402

TARGET_EXE = zigexe.SRC_EDITOR
WIN, WIN_END = 0x0050F000, 0x0050F800
WIN_SHA = "9b782f8b5c2407ae"
WIN_ORIG_B64 = (
    "eNqVVcmO40QYfi0GaebSXOaExA0NTce7XS6Xq7zES9zpJE7i2FkcZ+1ZhMSBF+DAgQtPgUCj6WET78FX3RJIo9EAURQpsfPXt/7W"
    "Bqn44f+87l7/XLrqJrROGW08tbsOxkSthXUqeMONQ0K6xOsyPjCvFp52TL1jzipurCMyo1qXeZWnFcYlvqbasyFRFr5+HARtYB0z"
    "v+HmKrQbYaUh+49g/nj7Bv89F/42cpqAzLm98I1jxiqmdTGpuL7L/DmzSvvqq0l86HtLYY6JXro6Tml8veY6ALSpN7R7lW8sGN5a"
    "F1klUdo+3cR003dPA94lNA7Iv4L589e7bWRtYqfizoyZm9hdCWsTOZWn174584zDIKh9Yx/a20QiKakOlbqItMKYU2Xu6WOi1IE9"
    "ti7nTFtBk9ybuiqw7W/6la8dEvqqHKxDe+pqbZ8EzPogmLdgN2N6LewVtw4plJdkl76x5GYT2CVR5dGRvYycNvEq3z7mHNJBwAnp"
    "zag+tpXKM2DWjKi3A7FP2UI4Xe4vQIebh4wtA3uGmZ62FtbcN5AKz1HfC+b3t2/kHG7dFrzyTRgt38Lap94qIscBPxRilzIoVvt2"
    "6RkQ/DyKAWPs9ODshOiHTCq2il38fsjFiJj7IsD9U6o13KoFgexwfBPa0BDU6vtTFm7PJ9o7YH5783op7NthOGdgqmCynOCb65js"
    "c3+fsVXkVsxYCXviKKXT2ycUJk6pjtvWkrIBp6ZE2Q38FicieMJqEwokU1fP9atGkIYZJdGAX04g6txVZvYl0oXYQzTm6v8E+Je7"
    "kuiAMSEqfNkmdCsrw8+FWIUOEJZUXaE+3Jp5WuMb25jWzNj2HRRwRhX0bg8YCW1Csg4dpAIBmzNzIhXQj4WAtjOqjuzeja0k6jOA"
    "aagKFhAHHOeesQ6sLnYfjLv76cfc+ALvG/sKl7rUOxdBF7loJYI0cZWuD4WtsQ1evZUwtimrudH1Kcbiatt3n4/iLqWQ5ZQz9H3B"
    "zRGVXUMN8YnYyGh5UEaB1PARjAAAgKHtIecvhmHXRwbMOdMvP//s++++rZiOYp4yDnHWwp6hDuYVWCPP54y1keQLOm3i7nK2Sxys"
    "IKgBlQAeSdvnbJ95UzTLUfAJT3Hig19LbuDQ0u2dr4OlgL9aLTeAjn7hv3sssYQCyZj00ESk4tOnF5Dom69foUcV1WtmogjbPuli"
    "G+1ofMliI5mybZ9CittBsAwdZOlUBKdhiN9fjCIsQOQH8VsH5JAwFBMZbgIHvkPbXULWKRs5vQfWYHfI6LHg0BMcd1BGFsdCUJ9e"
    "PP47Qu1yjjK+HEWnQmzvKwAANdOgJ+5shXW/hL0jrExc6AaCCCHStYk9TG5juuBy9b2Y5FNmoshAgj2A2KCbKHgjTKQRyDH8+SjC"
    "fzEfqiKoh5yB6SdPHr1TselNBpU2CDB2ft/GiaecH2SPbPCFLye4P+CNtN5YBs4+5zfWl+jv2MFTAzsKy8EpXQ2s8VxA2LDbgQSx"
    "ARg0/V4HE/qsQrLp03VEIQsSNWPGxeNH711Bk5sM1i8DE71oQwuwkSgYhMidC3QEDwUFmtdceo2rSMLc05a+BrOqe9k3wkTrgR9o"
    "ZYN87HP+UH80qArk4tpkPuogJ+Orq148/ugDK3oyTDEWp6DR54H/suDna1FR9dq6woaXVgpzdz9wE5irwJDzEexEPnbBAsTPwxAJ"
    "lPGISeObK1lGMsJTlTtd6iNyt9cBxC8cFev3kycfvwfEX8bdEEs=")

# editor addresses (fixed base)
SETITEMINDEX_CB = 0x00401A98         # thunk StdCtrls.TCustomComboBox.SetItemIndex
SETENABLED = 0x00401550              # thunk Controls.TControl.SetEnabled
ENABLE_ROUTINE = 0x0041CACC
IAT_CHECKBOX = 0x00432638            # [.] = TCheckBox
IAT_SETCHECKED, IAT_GETCHECKED = 0x004325D0, 0x004325D4
IAT_SETTEXT = 0x00432398
F_RANDOMRB, F_LIFECB, F_DEATHCB, F_LEVELRG = 0x214, 0x224, 0x23C, 0x244
RG_ITEMS = 0x120
SITES = {   # name: (va, vanilla)
    "create": (0x0041C8FF, bytes.fromhex("e89451feff")),
    "ok":     (0x0041CA8B, bytes.fromhex("e83c000000")),
    "enable": (0x0041CBB3, bytes.fromhex("e89849feff")),
}
IAT = {IAT_CHECKBOX: "VCL30.dpl!StdCtrls..TCheckBox",
       IAT_SETCHECKED: "VCL30.dpl!StdCtrls.TCustomCheckBox.SetChecked",
       IAT_GETCHECKED: "VCL30.dpl!StdCtrls.TCustomCheckBox.GetChecked",
       IAT_SETTEXT: "VCL30.dpl!Controls.TControl.SetText"}


def astr(s):
    b = s.encode("latin-1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def build_lits(va):
    """Four AnsiString literals 'Level 1'..'Level 4', 16 B apart; returns (blob, [char VAs])."""
    blob, chars = b"", []
    for n in range(1, 5):
        chars.append(va + len(blob) + 8)
        s = astr("Level %d" % n)
        blob += s + b"\0" * (16 - len(s))
    return blob, chars


def build_create(va, lit0, at):
    """Replaces FormCreate's last `call SetItemIndex` (EBX = form, ESI = tower).
    Stack after pushad: [esp] = n (3..0), [esp+4] = level mask."""
    return asm(f"""
        call {SETITEMINDEX_CB:#x}
        pushad
        sub  esp, 8
        movzx eax, byte ptr [esi + 0x3c]
        test eax, eax
        jne  c_mask
        movzx ecx, byte ptr [esi + 0x33]
        dec  ecx
        cmp  ecx, 7
        ja   c_mask
        mov  eax, 1
        shl  eax, cl
    c_mask:
        mov  dword ptr [esp + 4], eax
        mov  eax, dword ptr [ebx + {F_LEVELRG:#x}]
        mov  eax, dword ptr [eax + {RG_ITEMS:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x40]
        xor  ebp, ebp
        mov  dword ptr [esp], 3
    c_loop:
        mov  eax, dword ptr [{IAT_CHECKBOX:#x}]
        mov  dl, 1
        mov  ecx, ebx
        call dword ptr [eax + 0x24]
        mov  esi, eax
        mov  edx, dword ptr [ebx + {F_LEVELRG:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x3c]
        mov  ecx, dword ptr [esp]
        imul ecx, ecx, 24
        add  ecx, 22
        push 80
        push 17
        mov  edx, 16
        mov  eax, esi
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x4c]
        mov  eax, dword ptr [esp]
        shl  eax, 4
        lea  edx, [eax + {lit0:#x}]
        mov  eax, esi
        call dword ptr [{IAT_SETTEXT:#x}]
        mov  ecx, dword ptr [esp]
        mov  eax, dword ptr [esp + 4]
        bt   eax, ecx
        setc dl
        mov  eax, esi
        call dword ptr [{IAT_SETCHECKED:#x}]
        mov  dword ptr [esi + 0xc], ebp
        mov  ebp, esi
        dec  dword ptr [esp]
        jns  c_loop
        mov  eax, dword ptr [ebx + {F_LEVELRG:#x}]
        mov  dword ptr [eax + 0xc], ebp
        mov  ecx, {at['ldclick']:#x}
        mov  eax, dword ptr [ebx + {F_LIFECB:#x}]
        mov  dword ptr [eax + 0xa4], ecx
        mov  dword ptr [eax + 0xa8], ebx
        mov  eax, dword ptr [ebx + {F_DEATHCB:#x}]
        mov  dword ptr [eax + 0xa4], ecx
        mov  dword ptr [eax + 0xa8], ebx
        mov  eax, ebx
        call {ENABLE_ROUTINE:#x}
        add  esp, 8
        popad
        ret
    """, va)


def build_ok(va):
    """Replaces OKBtnClick's `call <enable routine>` (EAX = EBX = form, ESI = tower)."""
    return asm(f"""
        pushad
        mov  eax, dword ptr [ebx + {F_LEVELRG:#x}]
        mov  edi, dword ptr [eax + 0xc]
        test edi, edi
        je   o_done
        xor  ebp, ebp
        push 1
    o_loop:
        test edi, edi
        je   o_fin
        mov  eax, edi
        call dword ptr [{IAT_GETCHECKED:#x}]
        test al, al
        je   o_nb
        or   ebp, dword ptr [esp]
    o_nb:
        shl  dword ptr [esp], 1
        mov  edi, dword ptr [edi + 0xc]
        jmp  o_loop
    o_fin:
        pop  eax
        test ebp, ebp
        jne  o_set
        movzx ebp, byte ptr [esi + 0x3c]
        test ebp, ebp
        jne  o_set
        mov  ebp, 2
    o_set:
        mov  eax, ebp
        mov  byte ptr [esi + 0x3c], al
        bsf  eax, ebp
        inc  eax
        mov  byte ptr [esi + 0x33], al
    o_done:
        popad
        jmp  {ENABLE_ROUTINE:#x}
    """, va)


def build_enable(va):
    """Replaces the enable routine's last `call SetEnabled` (EBX = form)."""
    return asm(f"""
        call {SETENABLED:#x}
        push esi
        mov  eax, dword ptr [ebx + {F_LEVELRG:#x}]
        mov  esi, dword ptr [eax + 0xc]
    e_loop:
        test esi, esi
        je   e_out
        mov  eax, dword ptr [ebx + {F_RANDOMRB:#x}]
        mov  dl, byte ptr [eax + 0x11d]
        mov  eax, esi
        call {SETENABLED:#x}
        mov  esi, dword ptr [esi + 0xc]
        jmp  e_loop
    e_out:
        pop  esi
        ret
    """, va)


def build_ldclick(va):
    """OnClick of LifeCB and DeathCB: EAX = form (data), EDX = Sender."""
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        mov  eax, esi
        call dword ptr [{IAT_GETCHECKED:#x}]
        test al, al
        je   l_out
        mov  eax, dword ptr [ebx + {F_DEATHCB:#x}]
        cmp  esi, dword ptr [ebx + {F_LIFECB:#x}]
        je   l_unc
        mov  eax, dword ptr [ebx + {F_LIFECB:#x}]
    l_unc:
        xor  edx, edx
        call dword ptr [{IAT_SETCHECKED:#x}]
    l_out:
        pop  esi
        pop  ebx
        ret
    """, va)


def layout():
    caves, at = [], {}
    lits, chars = build_lits(WIN)
    caves.append(("lits", WIN, lits))
    va = WIN + len(lits)

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("ldclick", build_ldclick(va))
    put("ok", build_ok(va))
    put("enable", build_enable(va))
    put("create", build_create(va, chars[0], at))
    assert va <= WIN_END
    return at, caves


def main():
    path = os.path.join(GAME, TARGET_EXE)
    d = open(path, "rb").read()
    orig = zlib.decompress(base64.b64decode(WIN_ORIG_B64))
    assert len(orig) == WIN_END - WIN and hashlib.sha1(orig).hexdigest()[:16] == WIN_SHA
    e, secs = sections(d)
    mtb = [s for s in range(len(secs)) if secs[s][1] == 0xE1000]
    assert mtb, "no .mtb section at rva 0xE1000"
    o = e + 24 + struct.unpack_from("<H", d, e + 20)[0] + 40 * mtb[0]
    if not struct.unpack_from("<I", d, o + 36)[0] & 0x20000000:
        sys.exit("ABORT: .mtb is not executable -- build_deved_listarrows.py must be applied")
    at, caves = layout()
    blob = bytearray(orig)
    for _n, va, b in caves:
        blob[va - WIN:va - WIN + len(b)] = b
    rel = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
    hooks = [(SITES["create"][0], SITES["create"][1], rel(SITES["create"][0], at["create"])),
             (SITES["ok"][0], SITES["ok"][1], rel(SITES["ok"][0], at["ok"])),
             (SITES["enable"][0], SITES["enable"][1], rel(SITES["enable"][0], at["enable"])),
             (WIN, orig, bytes(blob))]
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in at.items()))
    if "--dis" in sys.argv:
        show([c for c in caves if c[0] != "lits"])
    run("build_wizardtower_dual_editor -- level checkboxes, Life/Death exclusive", hooks, [],
        (WIN, WIN), [a for a in sys.argv[1:] if a != "--dis"], targets=[TARGET_EXE])


if __name__ == "__main__":
    main()
