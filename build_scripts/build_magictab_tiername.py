#!/usr/bin/env python
r"""
build_magictab_tiername.py -- the Magic tab and the Power Distribution dialog name the research
GROUP ("Cosmos II" + its member spells), not the representative spell.  AoWz.exe + AoWzCompat.exe
(lockstep, exe_patch.py).

Tier research (build_tierresearch_dll.py / _exe.py) researches a whole (sphere, tier) group, but
[magic+0x34] still holds one representative spell id.  The spell book was re-labelled; these two
surfaces were not and showed that one spell's name, class line and casting cost.

SITES (each a `call TAOWLabel.SetGText` @0x403254 retargeted -- 4 bytes, nothing displaced)
    TMagicWin research panel, fill routine 0x42CDE8 (ebx = the representative TSpell there):
      0x42D0AD  SpellName  [win+0xBC]  -> cave_mw_name   "{sphere RStr} {I..IV}"
      0x42D119  SpellClass [win+0xD0]  -> cave_mw_line0  members, line 1 (was "Cosmos, Level 2")
      0x42D185  SpellCost  [win+0xD8]  -> cave_mw_line1  members, line 2+ (was "Casting Cost: N Mana")
    TPowerDlg preview (0x42BCB8 frame; research id in [ebp-0xC]):
      0x42BDFC  [dlg+0x70]             -> cave_pd_name   "{sphere RStr} {I..IV}"

MEMBERS = registry spells with the representative's sphere+tier word (+0x20/+0x21), category <= 2,
enabled (vmt+0x64), passing the vanilla id>=100 SpellTypes filter ([0x45EBEC]), and NOT already in
the player's researched list ([magic+0x30], TIntegerList.IndexOf thunk 0x401B4C) -- i.e. what
completing the research will add.  Same predicate as build_tierresearch_dll.py's cave_grant plus
the spell book's filters.  Names are ", "-joined and wrapped greedily: line 1 holds what fits in
(SpellPnl width - label x - 6) / 6 px per Age8 character (floor 16); everything else goes on line 2,
which the panel clips if it overflows.

Frame temps are the host's own managed LStrs, cleared by its LStrArrayClr: TMagicWin -0x10/-0x14/
-0x18, TPowerDlg -0x20/-0x24.

ICON  TMagicWin.SpellIcnDraw 0x42D89C: the 5-byte `mov edx,0xA` at 0x42D8F5 (just after vanilla's
nil-checked GetSpell; ebx = spell, esi = the 40x35 SpellIcn control, [esp] = the draw-context
copy) -> jmp cave_mw_icon.  It draws the sphere's spell-icon background disc, then the Roman tier
numeral centred on it in FontModule.AoW15WhiteGrey, white over a black 1-px shadow.
  The disc: Images\SpellIcn.ILB entries are composites (TImageNode, ClassID 0x100, layers at
  [img+0x40]): layer 0 the 40x35 sphere-coloured disc, layer 1 the monochrome spell stamp.  The
  library is taken from the representative spell's own icon sequence (TImageSequenceList [spell+
  0x2C], sequence 10, [seq+0x10]); the entry from DISCTAB, one icon per sphere whose disc is that
  sphere's majority disc over every installed spell: Cosmos 120 (purple), Life 80 (yellow), Death
  20 (pink-grey), Earth 40 (green), Air 0 (ice), Fire 60 (orange), Water 100 (blue).  Only layer 0
  is drawn, at the box origin.
Labels set their own font colour in TAOWLabel.Draw, so recolouring the font does not leak.  Any nil
(sequence, library, image, layer, font) replays `mov edx,0xA` and resumes the vanilla spell icon at
0x42D8FA (a nil font after the disc just skips the numeral).

Slot 0x0062A520-0x0062A9FF in .hcol's free run, exclusive.  No randomness.

USAGE
    python build_magictab_tiername.py [--dis]   verify / dry run
    python build_magictab_tiername.py --apply
    python build_magictab_tiername.py --undo    surgical
"""
import struct
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, run

SLOT = (0x0062A520, 0x0062AA00)

T_SETGTEXT  = 0x403254   # TAOWLabel.SetGText(eax=label, edx=str)
T_TRANSLATE = 0x4021E4   # AoWE.TranslateRStr(eax=rstr, edx=&dest)
T_LSTRCATN  = 0x401128   # System.@LStrCatN(eax=&dest, edx=n, n pushed args, callee-cleaned)
T_LSTRCLR   = 0x4010D8   # System.@LStrClr(eax=&str)
T_GETSPELL  = 0x4025A4   # TSpellControl.GetSpell(eax=registry, edx=id)
T_GETPLAYER = 0x402464   # TPlayerList.GetPlayers(eax=list, edx=index)
T_INDEXOF   = 0x401B4C   # Engine.TIntegerList.IndexOf(eax=list, edx=value) -> index | -1
G_HSSET     = 0x45DF78   # [[g]]+0x84 = TSpellControl registry
G_MAP       = 0x45DF7C   # [[g]]+0xA5 = player at the keyboard, +0x140 = TPlayerList
SPHERE_RSTR = 0x45E034   # [tab] -> sphere-name RStr, index = sphere byte
SPELLTYPES  = 0x45EBEC   # [tab]+id -> class byte, 0 = not castable (the book's id>=100 filter)
CHAR_PX     = 6          # Age8 average advance
MIN_CHARS   = 16
T_IL_GET    = 0x401ACC   # TCustomImageLibrary.Get(eax=lib, edx=idx) -> img | nil
T_SHOWCLIP  = 0x401A74   # TLibraryImage.ShowClipped(eax=img, edx=x, ecx=y, push ctx*), ret 4
T_FONTCOLOR = 0x401A84   # TImageLibraryFont.SetColor(eax=font, edx=TColor)
T_TEXTC     = 0x401A94   # TImageLibraryFont.SetTextCentered(eax=font, edx=cx, ecx=y,
                         #   push str, push ctx*), ret 8
T_GETIMGSEQ = 0x401AAC   # TImageSequenceList.GetImageSequence(eax=list, edx=id) -> seq | nil
G_FONTMOD   = 0x45A210   # [[g]]+0x5C = FontModule.AoW15WhiteGrey
FONT_FIELD  = 0x5C
ICON_HOOK   = 0x0042D8F5  # TMagicWin.SpellIcnDraw: `mov edx,0xA` after the nil-checked GetSpell
ICON_RESUME = 0x0042D8F5  # vanilla spell-icon path (hook bytes replayed in the cave)
ICON_EXIT   = 0x0042D93D  # SpellIcnDraw epilogue
NUM_CX, NUM_Y = 20, 10   # numeral centre x / top y inside the 40x35 SpellIcn box (15 px font)

# ---------------- data: literals + Roman table ----------------
data = bytearray()


def lit(s):
    """Delphi AnsiString literal (refcount -1); returns the VA of its first character."""
    while len(data) % 4:
        data.append(0)
    data.extend(struct.pack("<ii", -1, len(s)))
    va = SLOT[0] + len(data)
    data.extend(s.encode("latin1") + b"\0")
    return va


ROMTAB = SLOT[0]
data.extend(b"\0" * 32)
p1, p2, p3, p4 = lit("I"), lit("II"), lit("III"), lit("IV")
P_SPACE, P_COMMA = lit(" "), lit(", ")
struct.pack_into("<8I", data, 0, p1, p1, p2, p3, p4, p4, p4, p4)   # tier & 7; 1..4 real

# sphere 0..6 -> a SpellIcn.ILB entry id carrying that sphere's typical background disc
DISCTAB = SLOT[0] + len(data)
data.extend(bytes([120, 80, 20, 40, 0, 60, 100]))

caves = []
cur = SLOT[0] + len(data)


def add(name, src):
    global cur
    cur = (cur + 15) & ~15
    code = asm(src(cur) if callable(src) else src, cur)
    caves.append((name, cur, code))
    va = cur
    cur += len(code)
    return va


# ---- tiername: (eax = TSpell, edx = &result, ecx = &tmp) -> result = "Cosmos II" ----
TIERNAME = add("tiername", f"""
    push ebx
    push esi
    push edi
    mov ebx, eax
    mov esi, edx
    mov edi, ecx
    movzx eax, byte ptr [ebx+0x20]
    mov edx, dword ptr [{SPHERE_RSTR:#x}]
    mov eax, dword ptr [edx+eax*4]
    mov edx, edi
    call {T_TRANSLATE:#x}
    push dword ptr [edi]
    push {P_SPACE:#x}
    movzx eax, byte ptr [ebx+0x21]
    and eax, 7
    push dword ptr [{ROMTAB:#x}+eax*4]
    mov eax, esi
    mov edx, 3
    call {T_LSTRCATN:#x}
    pop edi
    pop esi
    pop ebx
    ret
""")

# ---- members: eax = rep TSpell; stack: &res, &tmp, target line (0 / 1), label; ret 0x10 ----
# locals: [ebp-0x10] sphere+tier word, [ebp-0x14] budget chars, [ebp-0x18] current line length,
#         [ebp-0x1c] current line (0 / 1), [ebp-0x20] separator flag
MEMBERS = add("members", f"""
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    sub esp, 0x14
    movzx eax, word ptr [eax+0x20]
    mov dword ptr [ebp-0x10], eax
    mov ecx, dword ptr [ebp+0x14]
    mov edx, dword ptr [ecx+0x10c]
    mov eax, {MIN_CHARS}
    test edx, edx
    je Lbud
    mov eax, dword ptr [edx+0x7c]
    sub eax, dword ptr [ecx+0x84]
    sub eax, 6
    cdq
    mov ecx, {CHAR_PX}
    idiv ecx
    cmp eax, {MIN_CHARS}
    jge Lbud
    mov eax, {MIN_CHARS}
Lbud:
    mov dword ptr [ebp-0x14], eax
    xor eax, eax
    mov dword ptr [ebp-0x18], eax
    mov dword ptr [ebp-0x1c], eax
    mov eax, dword ptr [ebp+8]
    call {T_LSTRCLR:#x}
    xor esi, esi
Lloop:
    mov eax, dword ptr [{G_HSSET:#x}]
    mov eax, dword ptr [eax]
    mov eax, dword ptr [eax+0x84]
    mov edx, dword ptr [eax+8]
    cmp esi, dword ptr [edx+8]
    jge Ldone
    mov edx, esi
    call {T_GETSPELL:#x}
    mov ebx, eax
    test ebx, ebx
    je Lnext
    movzx eax, word ptr [ebx+0x20]
    cmp eax, dword ptr [ebp-0x10]
    jne Lnext
    cmp byte ptr [ebx+0x22], 2
    ja Lnext
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0x64]
    test al, al
    je Lnext
    mov edi, dword ptr [ebx+0x10]
    cmp edi, 100
    jl Lcast
    mov eax, dword ptr [{SPELLTYPES:#x}]
    cmp byte ptr [eax+edi], 0
    je Lnext
Lcast:
    mov eax, dword ptr [{G_MAP:#x}]
    mov eax, dword ptr [eax]
    movsx edx, byte ptr [eax+0xa5]
    mov eax, dword ptr [eax+0x140]
    call {T_GETPLAYER:#x}
    mov eax, dword ptr [eax+0x54]
    mov eax, dword ptr [eax+0x30]
    mov edx, edi
    call {T_INDEXOF:#x}
    inc eax
    jne Lnext
    mov edi, dword ptr [ebx+8]
    xor ecx, ecx
    test edi, edi
    je Llen
    mov ecx, dword ptr [edi-4]
Llen:
    mov dword ptr [ebp-0x20], 0
    mov eax, dword ptr [ebp-0x18]
    test eax, eax
    je Lput
    lea edx, [eax+ecx+2]
    cmp edx, dword ptr [ebp-0x14]
    jle Lsep
    cmp dword ptr [ebp-0x1c], 0
    jne Lsep
    mov dword ptr [ebp-0x1c], 1
    xor eax, eax
    jmp Lput
Lsep:
    mov dword ptr [ebp-0x20], 1
    add eax, 2
Lput:
    add eax, ecx
    mov dword ptr [ebp-0x18], eax
    mov eax, dword ptr [ebp-0x1c]
    cmp eax, dword ptr [ebp+0x10]
    jne Lnext
    mov eax, dword ptr [ebp+8]
    push dword ptr [eax]
    mov edx, 2
    cmp dword ptr [ebp-0x20], 0
    je Lcat
    push {P_COMMA:#x}
    mov edx, 3
Lcat:
    push edi
    mov eax, dword ptr [ebp+0xc]
    call {T_LSTRCATN:#x}
    mov eax, dword ptr [ebp+8]
    mov ecx, dword ptr [ebp+0xc]
    mov edx, dword ptr [eax]
    xchg edx, dword ptr [ecx]
    mov dword ptr [eax], edx
Lnext:
    inc esi
    jmp Lloop
Ldone:
    add esp, 0x14
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret 0x10
""")

# ---- TMagicWin fill (ebx = rep spell, eax = label) ----
C_MW_NAME = add("cave_mw_name", f"""
    push eax
    mov eax, ebx
    lea edx, [ebp-0x18]
    lea ecx, [ebp-0x10]
    call {TIERNAME:#x}
    mov edx, dword ptr [ebp-0x18]
    pop eax
    jmp {T_SETGTEXT:#x}
""")


def mw_line(n):
    return f"""
    push eax
    push eax
    push {n}
    lea edx, [ebp-0x14]
    push edx
    lea edx, [ebp-0x10]
    push edx
    mov eax, ebx
    call {MEMBERS:#x}
    mov edx, dword ptr [ebp-0x10]
    pop eax
    jmp {T_SETGTEXT:#x}
"""


C_MW_LINE0 = add("cave_mw_line0", mw_line(0))
C_MW_LINE1 = add("cave_mw_line1", mw_line(1))

# ---- TPowerDlg preview (research id in [ebp-0xC], eax = label) ----
C_PD_NAME = add("cave_pd_name", f"""
    push eax
    mov eax, dword ptr [{G_HSSET:#x}]
    mov eax, dword ptr [eax]
    mov eax, dword ptr [eax+0x84]
    mov edx, dword ptr [ebp-0xc]
    call {T_GETSPELL:#x}
    lea edx, [ebp-0x24]
    lea ecx, [ebp-0x20]
    call {TIERNAME:#x}
    mov edx, dword ptr [ebp-0x24]
    pop eax
    jmp {T_SETGTEXT:#x}
""")

# ---- TMagicWin.SpellIcnDraw: sphere disc + Roman tier numeral (ebx = spell, esi = the SpellIcn
# control, [esp] = the 0x3C-byte draw-context copy).  Any nil falls back to the vanilla spell icon.
BOX_XY = """
    mov ecx, dword ptr [esi+0x10c]
    mov edx, dword ptr [ecx+0x84]
    add edx, dword ptr [esi+0x84]
    mov ecx, dword ptr [ecx+0x88]
    add ecx, dword ptr [esi+0x88]
"""


def numeral(dxy, colour):
    return f"""
    mov eax, edi
    mov edx, {colour:#x}
    call {T_FONTCOLOR:#x}
    mov eax, esp
    movzx edx, byte ptr [ebx+0x21]
    and edx, 7
    push dword ptr [{ROMTAB:#x}+edx*4]
    push eax
{BOX_XY}
    add edx, {NUM_CX + dxy}
    add ecx, {NUM_Y + dxy}
    mov eax, edi
    call {T_TEXTC:#x}
"""


C_MW_ICON = add("cave_mw_icon", f"""
    movzx edi, byte ptr [ebx+0x20]
    cmp edi, 6
    ja Lvan
    mov eax, dword ptr [ebx+0x2c]
    test eax, eax
    je Lvan
    mov edx, 0xa
    call {T_GETIMGSEQ:#x}
    test eax, eax
    je Lvan
    mov eax, dword ptr [eax+0x10]
    test eax, eax
    je Lvan
    movzx edx, byte ptr [{DISCTAB:#x}+edi]
    call {T_IL_GET:#x}
    test eax, eax
    je Lvan
    push eax
    mov edx, dword ptr [eax]
    call dword ptr [edx+0x68]
    cmp eax, 0x100
    pop eax
    jne Lplain
    mov eax, dword ptr [eax+0x40]
    test eax, eax
    je Lvan
    mov eax, dword ptr [eax]
    test eax, eax
    je Lvan
Lplain:
    mov ecx, esp
    push ecx
    push eax
{BOX_XY}
    pop eax
    call {T_SHOWCLIP:#x}
    mov eax, dword ptr [{G_FONTMOD:#x}]
    mov eax, dword ptr [eax]
    mov edi, dword ptr [eax+{FONT_FIELD:#x}]
    test edi, edi
    je Lexit
{numeral(1, 0x000000)}
{numeral(0, 0xFFFFFF)}
Lexit:
    jmp {ICON_EXIT:#x}
Lvan:
    mov edx, 0xa
    jmp {ICON_RESUME + 5:#x}
""")

caves.insert(0, ("data", SLOT[0], bytes(data)))


def call_to(site, dst):
    return b"\xE8" + struct.pack("<i", dst - (site + 5))


hooks = [(site, call_to(site, T_SETGTEXT), call_to(site, cave))
         for site, cave in ((0x0042D0AD, C_MW_NAME), (0x0042D119, C_MW_LINE0),
                            (0x0042D185, C_MW_LINE1), (0x0042BDFC, C_PD_NAME))]
hooks.append((ICON_HOOK, bytes.fromhex("ba0a000000"),
               bytes([0xE9]) + struct.pack("<i", C_MW_ICON - (ICON_HOOK + 5))))

if __name__ == "__main__":
    run("build_magictab_tiername", hooks, caves, SLOT)
