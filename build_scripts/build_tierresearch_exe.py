#!/usr/bin/env python3
r"""
AoW1 TIER RESEARCH -- EXE presentation layer, on the canonical mod exes
`Ziggurat\AoWz.exe` + `Ziggurat\AoWzCompat.exe` (names from `zigexe.py`).
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

Turns the Research Book (TSpellBook modes 2/3) into a per-(sphere,tier) picker:
one entry per open sphere-tier, titled "Fire II" (sphere name + Roman numeral), sphere icon,
member spell names listed in the slot memo, turns computed from the flat 100/200/400/800 cost.
Cast modes (0/1) and info view are untouched, so the two books finally look different.

Adds a new `.tres` section (9th) @ VA 0x611000 with 6 caves + literals:

  cave_group  <- call-hook @0x42EFA8 (research branch's TSpellList.SortOnLevel):
      runs SortOnLevel, snapshots the (enabled) candidates to a BSS side buffer
      [0x45B330]/count [0x45B320], then compacts the visible list to the FIRST spell per
      (sphere,tier), ordered sphere 0..6 then tier 1..4. Replicates the vanilla id>=100 filter
      ([0x45EBEC] = import of AoWTC.SpellTypes, byte[0..130] tactical-class table; 0 = not a
      castable spell) so such ids neither represent nor get listed.
  cave_title  <- call-hook @0x42E926 (slot name SetGText): research mode -> "{SphereName} {I..IV}"
      (sphere RStr table [0x45E034] via TranslateRStr, Roman literal table in .tres).
  cave_class  <- jmp-hook @0x42E991 (13-byte marker block): research mode -> blank the class
      label (it duplicated the title); other modes keep vanilla behaviour (markers on mode 2).
  cave_memo   <- call-hook @0x42EAAC (slot memo SetFStrings): research mode -> memo's own
      TStringList (TAOWMemo+0x118, Clear@vmt+0x40 / self-refreshing Add@vmt+0x34, proven by the
      combat-log window) filled with the group's member names from the side buffer, greedily
      packed "A, B" per line (flush at >=30 chars). Scratch line/tmp LStrs @0x45B324/0x45B328
      (BSS, always LStrClr'd -> leak-free).
  cave_turns  <- call-hook @0x42ED93 (research turns source `mov ecx,[spell+0x18]`):
      ecx = 100 << (tier-1) so the displayed turn count matches the DLL-side flat cost.
      (The in-progress displays read magic+0x38 and need no patch.)
  cave_icon   <- jmp-hook @0x4304C8 (TSpellBook.SpellIconDraw entry): research mode -> NO left
      icon at all (v2); instead draws TIER-many sphere icons side by side underneath the entry
      text at BLEND_PCT opacity: table = GetLookupTables([[0x45D6A8]] AlphaBlendTable, pct)
      (thunk 0x4018DC), img = Get(GenericI=[[0x45A4A0]]+0x78, ICONTAB[sphere]) (thunk 0x401ACC),
      then `call [imgvmt+0x94]` = ShowBlended(img, x, y, [clip ctx], [table]) — the exact idiom
      of the vanilla 65%-blend site @0x40D667. Icons at panel.abs + (57 + i*34, 6).
      Cosmos entries draw nothing (no sphere icon exists). Cast modes -> vanilla path.
  cave_costskip <- jmp-hook @0x42EAB1 (cost-label build head): research mode -> skip the mana
      "Cost:" and "Upkeep:" sections entirely (jmp 0x42ECB1); other modes re-execute the caster
      cmp and resume at the original jne @0x42EAB8 (flags survive the jmp).
  + 4 byte patches @0x42EDA7/0x42EDAD/0x42EE0D/0x42EE13: nil the LStrCatN concat bases in the
      research turns append (push [edi+0x90] / push ' ' -> push 0), so the label reads just
      "Turns: N" (research-only code path, mode 2/3 guarded upstream @0x42ED55).

DEPENDS on build_tierresearch_dll.py for the mechanics (grant-on-completion + flat cost);
without it the picker looks grouped but researches only the representative spell.
Backups: a fresh mint lands in Ziggurat\backups\ as AoWz.exe.pre-tierresearch (BACKUP_DIR, :63).
This docstring used to say "beside the exe" -- that was the pre-2026-09-03 behaviour and the code
no longer does it.  ⚠ No .pre-tierresearch snapshot exists today: the old pair kept the pre-rename
names AoW.exe/AoWCompat.exe.pre-tierresearch and went with <root>\backups\ on 2026-09-10.  Revert is
this script's own verify-before-write path, never a snapshot restore.
Dry-run by default; --apply to write. Idempotent, verify-before-write.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                       # mod binary names (AoWz.exe / AoWzCompat.exe)
EXES = list(zigexe.EXES)
BACKUP_DIR = os.path.join(GAME, "backups")   # ⚠ backups/, never the game root -- rule 2026-09-03

IB = 0x00400000

SEC_VA   = 0x00611000
SEC_RVA  = SEC_VA - IB
SEC_FOFF = 0x20B200          # current EOF of both exes (asserted)
EXP_NSEC = 8
EXP_SOI  = 0x211000

# thunks / helpers in the exe
T_SORTONLEVEL = 0x4025D4
T_SETGTEXT    = 0x403254
T_SETFSTRINGS = 0x4036F4
T_TRANSLATE   = 0x4021E4
T_LSTRCATN    = 0x401128
T_LSTRCLR     = 0x4010D8
T_SL_GETCOUNT = 0x4025BC     # TSpellList.GetCount(eax=list)
T_SL_GETSPELL = 0x4025B4     # TSpellList.GetSpell(eax=list, edx=i)
T_SC_GETSPELL = 0x4025A4     # TSpellControl.GetSpell(eax=registry, edx=id) -> spell|nil (id>=count)
T_IL_GET      = 0x401ACC     # TCustomImageLibrary.Get(eax=lib, edx=idx) -> img
T_IL_SHOWCLIP = 0x401A74     # TLibraryImage.ShowClipped(eax=img, edx=x, ecx=y, [stk]=ctx*)
T_GETLOOKUP   = 0x4018DC     # TLookupBlendTableCollection100.GetLookupTables(eax=coll, edx=pct)
ALPHATAB_GVAR = 0x45D6A8     # import slot: [[slot]] = GFXE.AlphaBlendTable collection
BLEND_PCT     = 40           # (v5: unused — icons draw at full opacity now)
T_TLIST_ADD   = 0x4014B4     # Classes.TList.Add(eax=TList, edx=item) — grows capacity
T_LSTRCOPY    = 0x401148     # System.@LStrCopy(eax=src, edx=index1based, ecx=count, [&dest])
T_LOADRES     = 0x401180     # System.LoadResString(eax=rec, edx=&dest)
T_INTTOSTR    = 0x4013AC     # SysUtils.IntToStr(eax=int, edx=&dest)
T_FONT_COLOR  = 0x401A84     # TImageLibraryFont.SetColor(eax=font, edx=rgb)
T_FONT_TEXTC  = 0x401A94     # TImageLibraryFont.SetTextCentered(eax=font, edx=cx, ecx=y, [str],[ctx])
FONTMOD_GVAR  = 0x45A210     # [[gvar]]+0x44 = FontModule.Age8 (the book's small font)
RSTR_RESPTS   = 0x45E2B0     # "Research Points" resourcestring rec (info page uses it)
COLON_LIT     = 0x4301DC     # existing ": " Delphi literal (info-page constant pool)
NAME_COLOR    = 1254460      # slot text color (same value as SxSpell/SxMemo TextColor)
NAME_MAXCHARS = 10           # names longer than this try a 2-line split at the middle space
ICON_Y_SLOT   = 32           # icon row y in a slot (title 3, turns 16 on class lbl, icons 32, names 70+)
ICON_Y_RPNL   = 20           # icon row y in ResearchPnl (title 3, icons 20, names 58/69, status 85)

SPHERE_RSTRTAB = 0x45E034    # [tab] -> array of sphere-name RStr, index = sphere byte
CUSTOM_DISABLE = 0x45EBEC    # import of AoWTC.SpellTypes: [tab]+id -> class byte, 0 = not castable
INTGFXMOD_GVAR = 0x45A4A0    # [[gvar]]+0x78 = GenericI TInterfaceIL
SPACE_LIT      = 0x42EEB0    # existing ' ' Delphi literal in FillSlot's constant pool

# BSS slack allocations (combat log ends at 0x45B30F; slack page ends 0x45C000)
BSS_SIDECNT = 0x45B320
BSS_LINE    = 0x45B324
BSS_TMP     = 0x45B328
BSS_SIDEBUF = 0x45B330       # dword TSpell* array, cap 500 (ends 0x45BB00)
BSS_ARRLEN  = 0x45BB04       # arranged-list length A (dword)
BSS_COST    = 0x45BB08       # flat tier cost stashed by cave_turns for the label append
BSS_CELL    = 0x45BB0C       # per-member cell width (262/M)
BSS_ARR     = 0x45BB10       # arranged slot layout, max 7 spreads * 8 dwords (ends 0x45BBF0)
BSS_CX      = 0x45BBF0       # current member's icon/name center x
BSS_L1      = 0x45BBF4       # wrapped-name line 1 LStr (always LStrClr'd)
BSS_L2      = 0x45BBF8       # wrapped-name line 2 LStr
BSS_BEST    = 0x45BBFC       # best split index during space scan
BSS_BESTD   = 0x45BC00       # best split distance
BSS_CAP     = 0x45BC10       # 1 once the vanilla panel/button heights are captured
BSS_PNLH    = 0x45BC14       # captured vanilla slot-panel height
BSS_BTNH    = 0x45BC18       # captured vanilla slot-button height

HILITE_H    = 100            # research slot panel+button height = the taller BookWin img 26
                             # (build_glowilb.py rebuilds that sprite 254x82 -> 254x100); the
                             # strip draws UNSCALED and is clipped by these rects, so both the
                             # panel and the button must be at least this tall for a wrapped
                             # second name line to sit inside the highlight.
SLOT_PNLS = (0x4C, 0x64, 0x7C, 0x94, 0xB4, 0xCC, 0xE4, 0xFC)
SLOT_BTNS = (0x114, 0x140, 0x144, 0x148, 0x14C, 0x150, 0x154, 0x158)

# hook sites (original bytes verified 2026-07-18)
HOOK_GROUP = 0x42EFA8; ORIG_GROUP = bytes.fromhex("e8 27 36 fd ff".replace(" ", ""))
HOOK_TITLE = 0x42E926; ORIG_TITLE = bytes.fromhex("e8 29 49 fd ff".replace(" ", ""))
HOOK_CLASS = 0x42E991; ORIG_CLASS = bytes.fromhex("80 be 20 02 00 00 02 0f 85 08 01 00 00".replace(" ", ""))
HOOK_MEMO  = 0x42EAAC; ORIG_MEMO  = bytes.fromhex("e8 43 4c fd ff".replace(" ", ""))
HOOK_TURNS = 0x42ED93; ORIG_TURNS = bytes.fromhex("8b 4b 18 8b c6".replace(" ", ""))
HOOK_ICON  = 0x4304C8; ORIG_ICON  = bytes.fromhex("53 56 57 55 83".replace(" ", ""))
HOOK_COSTSKIP = 0x42EAB1; ORIG_COSTSKIP = bytes.fromhex("83 be 2c 02 00 00 00".replace(" ", ""))
CLASS_RET  = 0x42EAA6
COSTSKIP_RESUME = 0x42EAB8    # original `jne` consuming the re-executed cmp's flags
COSTSKIP_SKIPTO = 0x42ECB1    # past mana-cost + upkeep sections
ICON_BACK_CAST   = 0x4304E0   # re-entry for cast modes (esi rewritten there)
# research-only turns-append: nil the concat bases so the label is just "Turns: N"
NILPUSH = [
    (0x42EDA7, bytes.fromhex("ff b7 90 00 00 00".replace(" ", "")), b"\x6a\x00" + b"\x90"*4),
    (0x42EDAD, bytes.fromhex("68 b0 ee 42 00".replace(" ", "")),    b"\x6a\x00" + b"\x90"*3),
    (0x42EE0D, bytes.fromhex("ff b7 90 00 00 00".replace(" ", "")), b"\x6a\x00" + b"\x90"*4),
    (0x42EE13, bytes.fromhex("68 b0 ee 42 00".replace(" ", "")),    b"\x6a\x00" + b"\x90"*3),
]

ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---------------- .tres data blob ----------------
blob = bytearray()
def align(n):
    while len(blob) % n: blob.append(0)
def lit(s):
    """Delphi AnsiString literal: dd -1, dd len, bytes, NUL. Returns VA of the char data."""
    align(4)
    off = len(blob)
    blob.extend(struct.pack("<ii", -1, len(s)))
    ptr = SEC_VA + len(blob)
    blob.extend(s.encode("latin1") + b"\x00")
    return ptr

ROMTAB = SEC_VA  # 8 dwords, filled after literals exist
blob.extend(b"\x00" * 32)
p_i, p_ii, p_iii, p_iv = lit("I"), lit("II"), lit("III"), lit("IV")
p_comma = lit(", ")
align(4)
ICONTAB = SEC_VA + len(blob)
blob.extend(bytes([5, 27, 30, 33, 36, 42, 39, 0]))   # sphere id -> image idx (0=Cosmos: mana crystal)
LIBOFFTAB = SEC_VA + len(blob)
blob.extend(bytes([0x80, 0x78, 0x78, 0x78, 0x78, 0x78, 0x78, 0x78]))  # IntGfxMod field: 0=UnitIcons, else GenericI
roman = [p_i, p_i, p_ii, p_iii, p_iv, p_iv, p_iv, p_iv]   # index 1..4 real, rest safe fallback
struct.pack_into("<8I", blob, 0, *roman)
align(4)
# panel WinTop tables (page-relative): research = 3 entries/page at 112px pitch; cast = vanilla
YTAB_RESEARCH = SEC_VA + len(blob)
blob.extend(struct.pack("<4i", 16, 120, 224, 328))
YTAB_VANILLA = SEC_VA + len(blob)
blob.extend(struct.pack("<4i", 30, 110, 190, 270))

def add_cave(name, src):
    align(16)
    va = SEC_VA + len(blob)
    code = bytes(ks.asm(src(va), va)[0])
    blob.extend(code)
    print(f"{name} @ {va:08X} ({len(code)} bytes)")
    return va

# ---- cave_group ----
CAVE_GROUP = add_cave("cave_group", lambda va: f"""
    call 0x{T_SORTONLEVEL:X}
    push ebx
    push esi
    push edi
    push ebp
    mov eax, [ebx+0x224]
    mov esi, [eax+4]
    xor ecx, ecx
    xor edx, edx
Lp1:
    cmp ecx, [esi+8]
    jge Lp1d
    cmp edx, 500
    jge Lp1d
    mov eax, [esi+4]
    mov eax, [eax+ecx*4]
    mov edi, [eax+0x10]
    cmp edi, 100
    jl Lkeep
    mov ebp, [0x{CUSTOM_DISABLE:X}]
    cmp byte ptr [ebp+edi], 0
    je Lskip
Lkeep:
    mov [0x{BSS_SIDEBUF:X}+edx*4], eax
    inc edx
Lskip:
    inc ecx
    jmp Lp1
Lp1d:
    mov [0x{BSS_SIDECNT:X}], edx
    xor edi, edi
    xor ecx, ecx
Ls:
    mov edx, 1
Lt:
    mov eax, ecx
    mov ah, dl
    xor ebp, ebp
Lscan:
    cmp ebp, [0x{BSS_SIDECNT:X}]
    jge Lnom
    mov ebx, [0x{BSS_SIDEBUF:X}+ebp*4]
    cmp word ptr [ebx+0x20], ax
    je Lmatch
    inc ebp
    jmp Lscan
Lmatch:
    push eax
    mov eax, [esi+4]
    mov [eax+edi*4], ebx
    pop eax
    inc edi
Lnom:
    inc edx
    cmp edx, 5
    jl Lt
    inc ecx
    cmp ecx, 7
    jl Ls
    mov [esi+8], edi
    mov eax, edi
    add eax, 5
    xor edx, edx
    mov ecx, 6
    div ecx
    shl eax, 3
    mov [0x{BSS_ARRLEN:X}], eax
    xor ecx, ecx
Lz:
    cmp ecx, eax
    jge Lzd
    mov dword ptr [0x{BSS_ARR:X}+ecx*4], 0
    inc ecx
    jmp Lz
Lzd:
    mov ebp, [esi+4]
    xor ebx, ebx
    xor edx, edx
Lsp:
    mov eax, edi
    sub eax, ebx
    jle Lgrow
    cmp eax, 6
    jle Lhavet
    mov eax, 6
Lhavet:
    push eax
    inc eax
    shr eax, 1
    push eax
    xor ecx, ecx
Lleft:
    cmp ecx, [esp]
    jge Lrightp
    lea eax, [ebx+ecx]
    mov eax, [ebp+eax*4]
    push ebx
    lea ebx, [edx+ecx]
    mov [0x{BSS_ARR:X}+ebx*4], eax
    pop ebx
    inc ecx
    jmp Lleft
Lrightp:
    xor ecx, ecx
Lright:
    mov eax, [esp+4]
    sub eax, [esp]
    cmp ecx, eax
    jge Lspnext
    mov eax, [esp]
    add eax, ebx
    add eax, ecx
    mov eax, [ebp+eax*4]
    push ebx
    lea ebx, [edx+4]
    add ebx, ecx
    mov [0x{BSS_ARR:X}+ebx*4], eax
    pop ebx
    inc ecx
    jmp Lright
Lspnext:
    pop eax
    pop eax
    add ebx, eax
    add edx, 8
    jmp Lsp
Lgrow:
    mov eax, [0x{BSS_ARRLEN:X}]
Lg:
    cmp [esi+8], eax
    jge Lgd
    push eax
    xor edx, edx
    mov eax, esi
    call 0x{T_TLIST_ADD:X}
    pop eax
    jmp Lg
Lgd:
    mov ebp, [esi+4]
    xor ecx, ecx
Lcp:
    cmp ecx, eax
    jge Lcpd
    mov edx, [0x{BSS_ARR:X}+ecx*4]
    mov [ebp+ecx*4], edx
    inc ecx
    jmp Lcp
Lcpd:
    mov [esi+8], eax
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
""")

# ---- cave_title ----
CAVE_TITLE = add_cave("cave_title", lambda va: f"""
    cmp byte ptr [esi+0x220], 2
    jb Lorig
    cmp byte ptr [esi+0x220], 3
    ja Lorig
    push eax
    movzx eax, byte ptr [ebx+0x20]
    mov edx, [0x{SPHERE_RSTRTAB:X}]
    mov eax, [edx+eax*4]
    lea edx, [ebp-0x10]
    call 0x{T_TRANSLATE:X}
    push dword ptr [ebp-0x10]
    push 0x{SPACE_LIT:X}
    movzx eax, byte ptr [ebx+0x21]
    and eax, 7
    mov eax, [0x{ROMTAB:X}+eax*4]
    push eax
    lea eax, [ebp-0xC]
    mov edx, 3
    call 0x{T_LSTRCATN:X}
    mov edx, [ebp-0xC]
    pop eax
Lorig:
    jmp 0x{T_SETGTEXT:X}
""")

# ---- cave_class ----
CAVE_CLASS = add_cave("cave_class", lambda va: f"""
    mov al, [esi+0x220]
    cmp al, 2
    jb Ldone
    cmp al, 3
    ja Ldone
    xor edx, edx
    mov eax, [ebp+0x14]
    call 0x{T_SETGTEXT:X}
Ldone:
    jmp 0x{CLASS_RET:X}
""")

# ---- cave_memo (v6: names now drawn under each icon; slot memo just cleared) ----
CAVE_MEMO = add_cave("cave_memo", lambda va: f"""
    cmp byte ptr [esi+0x220], 2
    jb Lorig
    cmp byte ptr [esi+0x220], 3
    ja Lorig
    mov eax, [eax+0x118]
    mov edx, [eax]
    call dword ptr [edx+0x40]
    ret
Lorig:
    jmp 0x{T_SETFSTRINGS:X}
""")

# ---- cave_turns (also stashes the flat cost for cave_turnstext) ----
CAVE_TURNS = add_cave("cave_turns", lambda va: f"""
    movzx ecx, byte ptr [ebx+0x21]
    dec ecx
    js Lc
    cmp ecx, 3
    jle Ls
    mov ecx, 3
Ls:
    mov eax, 100
    shl eax, cl
    mov ecx, eax
    jmp Ld
Lc:
    mov ecx, 100
Ld:
    mov [0x{BSS_COST:X}], ecx
    mov eax, esi
    ret
""")

# ---- cave_turnstext: "Turns: N Research Points: C" onto the CLASS label (y16, tighter than
# the cost label's y28); the cost label (edi, this call's original target) is blanked ----
CAVE_TURNSTEXT = add_cave("cave_turnstext", lambda va: f"""
    push edx
    push 0x{SPACE_LIT:X}
    lea edx, [ebp-0x14]
    mov eax, [0x{RSTR_RESPTS:X}]
    call 0x{T_LOADRES:X}
    mov eax, [ebp-0x14]
    lea edx, [ebp-0x10]
    call 0x{T_TRANSLATE:X}
    push dword ptr [ebp-0x10]
    push 0x{COLON_LIT:X}
    mov eax, [0x{BSS_COST:X}]
    lea edx, [ebp-0x14]
    call 0x{T_INTTOSTR:X}
    push dword ptr [ebp-0x14]
    lea eax, [ebp-0x18]
    mov edx, 5
    call 0x{T_LSTRCATN:X}
    mov edx, [ebp-0x18]
    mov eax, [ebp+0x14]
    call 0x{T_SETGTEXT:X}
    xor edx, edx
    mov eax, edi
    jmp 0x{T_SETGTEXT:X}
""")

# ---- shared watermark row: every member spell's own book icon, blended side by side ----
# Expects: eax = representative TSpell*, edi = the TAOWImage control, frame = 4 pushes +
# `add esp,-0x44` with the 0x3C-byte draw-ctx copy at [esp+8]. Ends via Lepi (also the target
# for early-outs in the cave front) and `ret`. Walks each member's icon TImageSequenceList
# (spell+0x2C, sequence 10): per static layer (mode byte +0x19==0) frame=[seq+0x20],
# lib=[seq+0x10], img=Get(lib,frame) (nil-safe), ShowBlended via [imgvmt+0x94] at
# x+[seq+0x24], y+[seq+0x28]; next layer = [seq+0xC]. Animated layers are skipped.
T_GETIMGSEQ = 0x401AAC   # TImageSequenceList.GetImageSequence(eax=list, edx=id) -> seq|0
def row_asm(yoff):
    """Member icons distributed evenly across the 262px panel width, each with its name
    centered underneath in Age8 (2-line middle-space wrap past NAME_MAXCHARS chars).
    Expects eax=rep spell, edi=control, 4-push/-0x44 frame with ctx copy at [esp+8]."""
    return f"""
    movzx ecx, word ptr [eax+0x20]
    push ecx
    xor ebx, ebx
    xor ebp, ebp
Lcnt:
    cmp ebx, [0x{BSS_SIDECNT:X}]
    jge Lcntd
    mov eax, [0x{BSS_SIDEBUF:X}+ebx*4]
    mov edx, [esp]
    cmp word ptr [eax+0x20], dx
    jne Lcnt1
    inc ebp
Lcnt1:
    inc ebx
    jmp Lcnt
Lcntd:
    test ebp, ebp
    jnz Lhavem
    xor ebx, ebx
    xor ebp, ebp
Lrb:
    cmp ebx, 512
    jge Lrbd
    mov edx, ebx
    mov eax, [0x45DF78]
    mov eax, [eax]
    mov eax, [eax+0x84]
    call 0x{T_SC_GETSPELL:X}
    test eax, eax
    jz Lrbn
    mov edx, [esp]
    cmp word ptr [eax+0x20], dx
    jne Lrbn
    cmp byte ptr [eax+0x22], 2
    ja Lrbn
    mov edx, [eax+0x10]
    cmp edx, 100
    jl Lrb1
    push eax
    mov ecx, [0x{CUSTOM_DISABLE:X}]
    cmp byte ptr [ecx+edx], 0
    pop eax
    je Lrbn
Lrb1:
    push eax
    mov ecx, [eax]
    call dword ptr [ecx+0x64]
    test al, al
    pop eax
    jz Lrbn
    mov [0x{BSS_SIDEBUF:X}+ebp*4], eax
    inc ebp
    cmp ebp, 500
    jge Lrbd
Lrbn:
    inc ebx
    jmp Lrb
Lrbd:
    mov [0x{BSS_SIDECNT:X}], ebp
    test ebp, ebp
    jz Lpopepi
Lhavem:
    mov eax, 262
    xor edx, edx
    div ebp
    mov [0x{BSS_CELL:X}], eax
    mov dword ptr [edi+0x7C], 262
    mov dword ptr [edi+0x80], 104
    mov edx, [edi+0x10c]
    mov eax, [edx+0x84]
    mov [esp+0x1C], eax
    add eax, 262
    mov [esp+0x24], eax
    mov eax, [edx+0x88]
    mov [esp+0x20], eax
    add eax, 160
    mov [esp+0x28], eax
    mov esi, [edx+0x84]
    mov edi, [edx+0x88]
    add edi, {yoff}
    mov eax, [0x{FONTMOD_GVAR:X}]
    mov eax, [eax]
    mov eax, [eax+0x44]
    mov edx, {NAME_COLOR}
    call 0x{T_FONT_COLOR:X}
    lea eax, [esp+0xC]
    push eax
    xor ebx, ebx
    xor ebp, ebp
Lmember:
    cmp ebx, [0x{BSS_SIDECNT:X}]
    jge Ldone
    mov eax, [0x{BSS_SIDEBUF:X}+ebx*4]
    mov edx, [esp+4]
    cmp word ptr [eax+0x20], dx
    jne Lnextm
    mov eax, [0x{BSS_CELL:X}]
    imul eax, ebp
    add eax, esi
    mov edx, [0x{BSS_CELL:X}]
    shr edx, 1
    add eax, edx
    mov [0x{BSS_CX:X}], eax
    mov eax, [0x{BSS_SIDEBUF:X}+ebx*4]
    mov edx, [eax+0x2C]
    test edx, edx
    jz Lname
    push ebx
    mov eax, edx
    mov edx, 10
    call 0x{T_GETIMGSEQ:X}
    mov ebx, eax
Llayer:
    test ebx, ebx
    jz Llayd
    cmp byte ptr [ebx+0x19], 0
    jnz Lnl
    mov edx, [ebx+0x20]
    test edx, edx
    js Lnl
    mov eax, [ebx+0x10]
    test eax, eax
    jz Lnl
    call 0x{T_IL_GET:X}
    test eax, eax
    jz Lnl
    push ebx
    push dword ptr [esp+8]
    mov edx, [0x{BSS_CX:X}]
    sub edx, 20
    add edx, [ebx+0x24]
    mov ecx, edi
    add ecx, [ebx+0x28]
    call 0x{T_IL_SHOWCLIP:X}
    pop ebx
Lnl:
    mov ebx, [ebx+0xC]
    jmp Llayer
Llayd:
    pop ebx
Lname:
    mov eax, [0x{BSS_SIDEBUF:X}+ebx*4]
    mov eax, [eax+8]
    test eax, eax
    jz Lmdone
    mov edx, [eax-4]
    cmp edx, {NAME_MAXCHARS}
    jle Lsingle
    mov dword ptr [0x{BSS_BEST:X}], 0
    mov dword ptr [0x{BSS_BESTD:X}], 999
    mov ecx, 1
Lsc:
    cmp ecx, edx
    jge Lscd
    cmp byte ptr [eax+ecx-1], 0x20
    jne Lsc1
    push edx
    push eax
    mov eax, edx
    shr eax, 1
    sub eax, ecx
    jns Labs
    neg eax
Labs:
    cmp eax, [0x{BSS_BESTD:X}]
    jge Lsc2
    mov [0x{BSS_BESTD:X}], eax
    mov [0x{BSS_BEST:X}], ecx
Lsc2:
    pop eax
    pop edx
Lsc1:
    inc ecx
    jmp Lsc
Lscd:
    cmp dword ptr [0x{BSS_BEST:X}], 0
    je Lsingle
    push eax
    mov ecx, [0x{BSS_BEST:X}]
    dec ecx
    mov edx, 1
    push 0x{BSS_L1:X}
    call 0x{T_LSTRCOPY:X}
    mov eax, [esp]
    mov edx, [0x{BSS_BEST:X}]
    inc edx
    mov ecx, 999
    push 0x{BSS_L2:X}
    call 0x{T_LSTRCOPY:X}
    pop eax
    push dword ptr [0x{BSS_L1:X}]
    push dword ptr [esp+4]
    mov ecx, edi
    add ecx, 38
    mov edx, [0x{BSS_CX:X}]
    mov eax, [0x{FONTMOD_GVAR:X}]
    mov eax, [eax]
    mov eax, [eax+0x44]
    call 0x{T_FONT_TEXTC:X}
    push dword ptr [0x{BSS_L2:X}]
    push dword ptr [esp+4]
    mov ecx, edi
    add ecx, 49
    mov edx, [0x{BSS_CX:X}]
    mov eax, [0x{FONTMOD_GVAR:X}]
    mov eax, [eax]
    mov eax, [eax+0x44]
    call 0x{T_FONT_TEXTC:X}
    mov eax, 0x{BSS_L1:X}
    call 0x{T_LSTRCLR:X}
    mov eax, 0x{BSS_L2:X}
    call 0x{T_LSTRCLR:X}
    jmp Lmdone
Lsingle:
    push eax
    push dword ptr [esp+4]
    mov ecx, edi
    add ecx, 40
    mov edx, [0x{BSS_CX:X}]
    mov eax, [0x{FONTMOD_GVAR:X}]
    mov eax, [eax]
    mov eax, [eax+0x44]
    call 0x{T_FONT_TEXTC:X}
Lmdone:
    inc ebp
Lnextm:
    inc ebx
    jmp Lmember
Ldone:
    pop eax
Lpopepi:
    pop eax
Lepi:
    add esp, 0x44
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""

# ---- cave_icon (v4: no left icon; member spell icons blended under the text) ----
CAVE_ICON = add_cave("cave_icon", lambda va: f"""
    push ebx
    push esi
    push edi
    push ebp
    add esp, -0x44
    mov esi, ecx
    lea edi, [esp+8]
    mov ecx, 0xF
    rep movsd dword ptr es:[edi], dword ptr [esi]
    mov edi, edx
    mov ebx, eax
    mov al, [ebx+0x220]
    cmp al, 2
    jb Lback
    cmp al, 3
    ja Lback
    mov esi, [ebx+0x228]
    shl esi, 3
    mov eax, [edi+0xC]
    and eax, 0xF
    add esi, eax
    mov eax, [ebx+0x224]
    call 0x{T_SL_GETCOUNT:X}
    cmp esi, eax
    jge Lepi
    mov edx, esi
    mov eax, [ebx+0x224]
    call 0x{T_SL_GETSPELL:X}
    test eax, eax
    jz Lepi
{row_asm(ICON_Y_SLOT)}
Lback:
    jmp 0x{ICON_BACK_CAST:X}
""")

# ---- cave_layout: per-mode slot-panel Y positions (call-hook on GetCount @0x42F2D7) ----
# Runs once per book population for EVERY mode. Research (2/3): 3 entries per page at 104px
# pitch; other modes: vanilla 30/110/190/270. v7.1: the slot panels have alignment NONE, so
# the align pass is a NO-OP for them — the +0x88 field must hold the FINAL ABSOLUTE Y. We
# compute it ourselves: [pnl+0x88] = [page(+0x10C parent)+0x88] + ytab[i]; align-valid byte
# untouched (nothing re-derives these). Panel refs: left [ebx+0x4C/0x64/0x7C/0x94], right
# [ebx+0xB4/0xCC/0xE4/0xFC]. Preserves eax (the GetCount result the caller consumes).
def _layout_stores():
    # Panel parent = [pnl+0xCC] (TAoWComponent parent field, per ReAlign) — NOT +0x10C, which
    # is the CONTROL-level AOWWindow field (nil for panels; caused the v7.1 AV @ +0x88).
    # The S-panels use Alignment ahTop with TopOffset ([pnl+0xD4]+0x20) = the DFM Ys; the
    # first-Show ReAlign recomputes +0x88 from that and re-absolutizes (+0xA4 pass), which
    # reverted v7.2's positions on the FIRST open. Write BOTH: the alignment TopOffset (page-
    # relative) so any ReAlign lands on our layout, and +0x88 (absolute) for draws before one.
    left  = (0x4C, 0x64, 0x7C, 0x94)
    right = (0xB4, 0xCC, 0xE4, 0xFC)
    src = ""
    n = 0
    for i in range(4):
        for fld in (left[i], right[i]):
            src += f"""
    mov eax, [ebx+0x{fld:X}]
    test eax, eax
    jz Lskip{n}
    mov edx, [eax+0xD4]
    test edx, edx
    jz Lnoal{n}
    push ecx
    mov ecx, [ecx+{i*4}]
    mov [edx+0x20], ecx
    pop ecx
Lnoal{n}:
    mov edx, [eax+0xCC]
    test edx, edx
    jz Lskip{n}
    mov edx, [edx+0x88]
    add edx, [ecx+{i*4}]
    mov [eax+0x88], edx
Lskip{n}:
"""
            n += 1
    return src

def _icon_size_stores():
    # v7.5: the slot ICON controls' rects are enlarged to 262x104 during research draws (the
    # hover-erase fix) but must shrink back to the vanilla 40x35 for CAST mode — stale huge
    # rects made neighbouring repaints re-composite translucent button images (ghost buildup).
    icons = (0x60, 0x78, 0x90, 0xA8, 0xC8, 0xE0, 0xF8, 0x110)
    src = ""
    for n, fld in enumerate(icons):
        src += f"""
    mov eax, [ebx+0x{fld:X}]
    test eax, eax
    jz Lisz{n}
    mov [eax+0x7C], edx
    mov [eax+0x80], esi
Lisz{n}:
"""
    return src

def _height_stores():
    # Panel + button heights per mode: research = HILITE_H (so the taller glow sprite isn't
    # clipped away — children clip to their panel, and DrawILI clips to the button rect),
    # cast = the captured vanilla values.
    src = ""
    for n, fld in enumerate(SLOT_PNLS):
        src += f"""
    mov eax, [ebx+0x{fld:X}]
    test eax, eax
    jz Lph{n}
    mov [eax+0x80], edi
Lph{n}:
"""
    for n, fld in enumerate(SLOT_BTNS):
        src += f"""
    mov eax, [ebx+0x{fld:X}]
    test eax, eax
    jz Lbh{n}
    mov [eax+0x80], esi
Lbh{n}:
"""
    return src

CAVE_LAYOUT = add_cave("cave_layout", lambda va: f"""
    call 0x{T_SL_GETCOUNT:X}
    push eax
    push esi
    push edi
    cmp dword ptr [0x{BSS_CAP:X}], 0
    jne Lnocap
    mov eax, [ebx+0x4C]
    test eax, eax
    jz Lnocap
    mov edx, [eax+0x80]
    mov [0x{BSS_PNLH:X}], edx
    mov eax, [ebx+0x114]
    test eax, eax
    jz Lnocap
    mov edx, [eax+0x80]
    mov [0x{BSS_BTNH:X}], edx
    mov dword ptr [0x{BSS_CAP:X}], 1
Lnocap:
    mov ecx, 0x{YTAB_VANILLA:X}
    mov edi, [0x{BSS_PNLH:X}]
    mov esi, [0x{BSS_BTNH:X}]
    cmp byte ptr [ebx+0x220], 2
    jb Lset
    cmp byte ptr [ebx+0x220], 3
    ja Lset
    mov ecx, 0x{YTAB_RESEARCH:X}
    mov edi, {HILITE_H}
    mov esi, {HILITE_H}
Lset:
{_height_stores()}
{_layout_stores()}
    mov edx, 40
    mov esi, 35
    cmp ecx, 0x{YTAB_RESEARCH:X}
    jne Lsz
    mov edx, 262
    mov esi, 104
Lsz:
{_icon_size_stores()}
    pop edi
    pop esi
    pop eax
    ret
""")

# ---- cave_dlgupd: self-healing layout (entry-hook on TSpellBook.DlgUpdate @0x431270) ----
# On the FIRST open the population runs before the page panel is absolutized (the book
# window's 14px border isn't in yet), so cave_layout computes short positions; nothing
# repaints until the next population (reopen / event). Fix: every update tick, if S1Pnl's Y
# != page.abs + ytab[mode][0], re-run the population fn 0x42EF14 — which redoes layout with
# the now-correct page position AND repaints (SetGText invalidations). Converges to a no-op.
CAVE_DLGUPD = add_cave("cave_dlgupd", lambda va: f"""
    push ebx
    mov ebx, eax
    mov eax, [ebx+0x1C4]
    test eax, eax
    jz Lorig
    cmp byte ptr [eax+0x75], 0
    je Lorig
    mov ecx, 0x{YTAB_VANILLA:X}
    cmp byte ptr [ebx+0x220], 2
    jb Lsel
    cmp byte ptr [ebx+0x220], 3
    ja Lsel
    mov ecx, 0x{YTAB_RESEARCH:X}
Lsel:
    mov eax, [ebx+0x4C]
    test eax, eax
    jz Lorig
    mov edx, [eax+0xCC]
    test edx, edx
    jz Lorig
    mov edx, [edx+0x88]
    add edx, [ecx]
    cmp [eax+0x88], edx
    je Lorig
    mov eax, ebx
    call 0x42EF14
Lorig:
    mov eax, [ebx+0x1C4]
    jmp 0x431279
""")

# ---- cave_nilguard: nil-safe head of the vanilla id>=100 SpellTypes filter loop @0x42F2F1 ----
# The arranged list contains nil slot-gaps; the vanilla loop read [spell+0x10] unguarded (the
# v5 crash: AV read of 0x10). Nil or id<100 -> skip the entry (return-address swap to 0x42F320,
# the loop-continue); else fall back to the caller's table check @0x42F2F7. No Deletes ever fire
# in research mode (reps are pre-filtered), so slot alignment is preserved.
CAVE_NILGUARD = add_cave("cave_nilguard", lambda va: f"""
    test eax, eax
    jz Lskip
    cmp dword ptr [eax+0x10], 0x64
    jl Lskip
    ret
Lskip:
    add esp, 4
    jmp 0x42F320
""")

# ---- cave_costskip (research: no mana Cost / Upkeep on the slot cost label) ----
CAVE_COSTSKIP = add_cave("cave_costskip", lambda va: f"""
    cmp byte ptr [esi+0x220], 2
    jb Lnorm
    cmp byte ptr [esi+0x220], 3
    ja Lnorm
    jmp 0x{COSTSKIP_SKIPTO:X}
Lnorm:
    cmp dword ptr [esi+0x22c], 0
    jmp 0x{COSTSKIP_RESUME:X}
""")

# ---- cave_rtitle: "Currently Researching" name label -> "Fire I" (edi=spell here) ----
CAVE_RTITLE = add_cave("cave_rtitle", lambda va: f"""
    push eax
    movzx eax, byte ptr [edi+0x20]
    mov edx, [0x{SPHERE_RSTRTAB:X}]
    mov eax, [edx+eax*4]
    lea edx, [ebp-0x10]
    call 0x{T_TRANSLATE:X}
    push dword ptr [ebp-0x10]
    push 0x{SPACE_LIT:X}
    movzx eax, byte ptr [edi+0x21]
    and eax, 7
    mov eax, [0x{ROMTAB:X}+eax*4]
    push eax
    lea eax, [ebp-0xC]
    mov edx, 3
    call 0x{T_LSTRCATN:X}
    mov edx, [ebp-0xC]
    pop eax
    jmp 0x{T_SETGTEXT:X}
""")

# ---- cave_blank: shared "set label to empty" tail (research class/cost lines) ----
CAVE_BLANK = add_cave("cave_blank", lambda va: f"""
    xor edx, edx
    jmp 0x{T_SETGTEXT:X}
""")

# ---- cave_rmemo (v6: names drawn under icons; research memo just cleared) ----
CAVE_RMEMO = add_cave("cave_rmemo", lambda va: f"""
    mov eax, [eax+0x118]
    mov edx, [eax]
    call dword ptr [edx+0x40]
    ret
""")

# ---- cave_ricon: ResearchIcnDraw -> member spell icons blended (own frame, own ret) ----
CAVE_RICON = add_cave("cave_ricon", lambda va: f"""
    push ebx
    push esi
    push edi
    push ebp
    add esp, -0x44
    mov esi, ecx
    lea edi, [esp+8]
    mov ecx, 0xF
    rep movsd dword ptr es:[edi], dword ptr [esi]
    mov edi, edx
    mov ebx, eax
    mov eax, [0x45DF7C]
    mov eax, [eax]
    movsx edx, byte ptr [eax+0xA5]
    mov eax, [0x45DF7C]
    mov eax, [eax]
    mov eax, [eax+0x140]
    call 0x402464
    mov eax, [eax+0x54]
    mov edx, [eax+0x34]
    mov eax, [0x45DF78]
    mov eax, [eax]
    mov eax, [eax+0x84]
    call 0x4025A4
    test eax, eax
    jne Lgot
    cmp byte ptr [ebx+0x220], 3
    jne Lepi
    mov eax, [0x45DF78]
    mov eax, [eax]
    mov eax, [eax+0x84]
    mov edx, [ebx+0x234]
    call 0x4025A4
    test eax, eax
    je Lepi
Lgot:
{row_asm(ICON_Y_RPNL)}
""")

align(16)
blob_bytes = bytes(blob)
assert len(blob_bytes) <= 0x1000, f"blob too big: {len(blob_bytes):#x}"
print(f"blob total {len(blob_bytes):#x} bytes")

def rel(site, dest):
    return struct.pack("<i", dest - (site + 5))

HOOKS = [
    (HOOK_GROUP, ORIG_GROUP, b"\xE8" + rel(HOOK_GROUP, CAVE_GROUP), "SortOnLevel -> cave_group"),
    (HOOK_TITLE, ORIG_TITLE, b"\xE8" + rel(HOOK_TITLE, CAVE_TITLE), "title SetGText -> cave_title"),
    (HOOK_CLASS, ORIG_CLASS, b"\xE9" + rel(HOOK_CLASS, CAVE_CLASS) + b"\x90"*8, "class markers -> cave_class"),
    (HOOK_MEMO,  ORIG_MEMO,  b"\xE8" + rel(HOOK_MEMO,  CAVE_MEMO),  "memo SetFStrings -> cave_memo"),
    (HOOK_TURNS, ORIG_TURNS, b"\xE8" + rel(HOOK_TURNS, CAVE_TURNS), "turns cost -> cave_turns"),
    (HOOK_ICON,  ORIG_ICON,  b"\xE9" + rel(HOOK_ICON,  CAVE_ICON),  "SpellIconDraw -> cave_icon"),
    (HOOK_COSTSKIP, ORIG_COSTSKIP, b"\xE9" + rel(HOOK_COSTSKIP, CAVE_COSTSKIP) + b"\x90"*2,
     "cost-label head -> cave_costskip"),
    (0x42FB2C, b"\xE8" + rel(0x42FB2C, T_SETGTEXT), b"\xE8" + rel(0x42FB2C, CAVE_RTITLE),
     "research-info name -> cave_rtitle"),
    (0x42FB95, b"\xE8" + rel(0x42FB95, T_SETGTEXT), b"\xE8" + rel(0x42FB95, CAVE_BLANK),
     "research-info class -> blank"),
    (0x42FC08, b"\xE8" + rel(0x42FC08, T_SETGTEXT), b"\xE8" + rel(0x42FC08, CAVE_BLANK),
     "research-info casting-cost -> blank"),
    (0x42FB1E, b"\xE8" + rel(0x42FB1E, T_SETFSTRINGS), b"\xE8" + rel(0x42FB1E, CAVE_RMEMO),
     "research-info memo -> cave_rmemo"),
    (0x4310BC, bytes.fromhex("53 56 57 83 c4".replace(" ", "")),
     b"\xE9" + rel(0x4310BC, CAVE_RICON), "ResearchIcnDraw -> cave_ricon"),
    (0x42FD2E, b"\xE8" + rel(0x42FD2E, T_SETFSTRINGS), b"\xE8" + rel(0x42FD2E, CAVE_RMEMO),
     "Researched-view memo -> cave_rmemo"),
    (0x42FD3C, b"\xE8" + rel(0x42FD3C, T_SETGTEXT), b"\xE8" + rel(0x42FD3C, CAVE_RTITLE),
     "Researched-view name -> cave_rtitle"),
    (0x42FDA5, b"\xE8" + rel(0x42FDA5, T_SETGTEXT), b"\xE8" + rel(0x42FDA5, CAVE_BLANK),
     "Researched-view class -> blank"),
    (0x42FE0E, b"\xE8" + rel(0x42FE0E, T_SETGTEXT), b"\xE8" + rel(0x42FE0E, CAVE_BLANK),
     "Researched-view casting-cost -> blank"),
    (0x42F2F1, bytes.fromhex("83 78 10 64 7c 29".replace(" ", "")),
     b"\xE8" + rel(0x42F2F1, CAVE_NILGUARD) + b"\x90", "filter-loop nil guard"),
    (0x42EE06, b"\xE8" + rel(0x42EE06, T_SETGTEXT), b"\xE8" + rel(0x42EE06, CAVE_TURNSTEXT),
     "turns label SetGText -> cave_turnstext (append Research Points)"),
    (0x42F2D7, b"\xE8" + rel(0x42F2D7, T_SL_GETCOUNT), b"\xE8" + rel(0x42F2D7, CAVE_LAYOUT),
     "population GetCount -> cave_layout (per-mode panel pitch)"),
    (0x431270, bytes.fromhex("53 8b d8 8b 83".replace(" ", "")),
     b"\xE9" + rel(0x431270, CAVE_DLGUPD), "DlgUpdate entry -> cave_dlgupd (layout self-heal)"),
] + [(site, orig, new, f"nil concat base @{site:X}") for site, orig, new in NILPUSH]

# ---- DFM control repositioning (TSpellBook resource @ file 0x1B5408..next form) ----
# vaInt8 property values patched in place (no size change): slot memos drop below the icon row,
# research-panel memo/status rearranged (title 3 / icons 20 / names 60 / "N turns Left" 112).
DFM_LO, DFM_HI = 0x1B5408, 0x1C4F48
def dfm_patches(d):
    def pstr(s):
        b = s.encode('latin1'); return bytes([len(b)]) + b
    out = []
    def prop8(objname, propname, oldv, newv):
        o = d.find(pstr(objname), DFM_LO, DFM_HI)
        assert o >= 0, f"DFM object {objname} not found"
        span = d[o:o+0x300]
        key = pstr(propname) + b"\x02"
        k = span.find(key)
        assert k >= 0, f"{objname}.{propname} not found"
        off = o + k + len(key)
        assert d[off] in (oldv, newv), f"{objname}.{propname}: byte {d[off]:#x} not {oldv:#x}/{newv:#x}"
        out.append((off, bytes([oldv]), bytes([newv]), f"DFM {objname}.{propname} {oldv}->{newv}"))
    # v7: NO DFM patches. The slot controls are shared with the CAST book (v6's static moves
    # wrecked its layout); research-mode geometry is now done at runtime by cave_layout, and
    # the memos are empty so their positions never mattered. prop8 kept for future use.
    _ = prop8
    return out

def process(exe):
    path = os.path.join(GAME, exe)
    # ⚠ backups/, never the game root -- rule 2026-09-03. The mint below is reached only
    # after the "already applied" early-return and a full original-bytes check, so it is
    # positively gated on the file being unpatched.
    backup = os.path.join(BACKUP_DIR, exe + ".pre-tierresearch")
    d = bytearray(open(path, 'rb').read())
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    shdr_off = e + 24 + optsz + 40*nsec
    soi_off = e + 24 + 56

    secs = []
    sect = e + 24 + optsz
    for i in range(nsec):
        b = sect + i*40
        vs, va, rs, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((d[b:b+8].rstrip(b'\0').decode('latin1'), va, vs, raw, rs))
    def va2off(va):
        r = va - IB
        for nm, v, vs, raw, rs in secs:
            if v <= r < v + max(vs, rs):
                return raw + (r - v)
        raise ValueError(hex(va))

    dfmp = dfm_patches(d)

    applied = len(d) > SEC_FOFF
    if applied:
        if bytes(d[SEC_FOFF:SEC_FOFF+len(blob_bytes)]) == blob_bytes and \
           all(bytes(d[va2off(s):va2off(s)+len(new)]) == new for s, _, new, _ in HOOKS) and \
           all(bytes(d[o:o+1]) == new for o, _, new, _ in dfmp):
            print(f"{exe}: already applied."); return True
        print(f"{exe}: ABORT -- file extends past {SEC_FOFF:#x} with DIFFERENT content. Do NOT "
              "restore .pre-tierresearch (layer 5/8, costs 3 features): remove the conflicting "
              "trailing section surgically instead."); return False
    if len(d) != SEC_FOFF:
        print(f"{exe}: ABORT -- length {len(d):#x} != {SEC_FOFF:#x}"); return False
    if nsec != EXP_NSEC:
        print(f"{exe}: ABORT -- {nsec} sections, expected {EXP_NSEC}"); return False
    if struct.unpack_from('<I', d, soi_off)[0] != EXP_SOI:
        print(f"{exe}: ABORT -- unexpected SizeOfImage"); return False

    ok = True
    for site, orig, new, desc in HOOKS:
        cur = bytes(d[va2off(site):va2off(site)+len(orig)])
        if cur != orig:
            print(f"{exe}: MISMATCH {desc}:\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}"); ok = False
    for off, orig, new, desc in dfmp:
        if bytes(d[off:off+1]) != orig:
            print(f"{exe}: MISMATCH {desc} @foff {off:#x}"); ok = False
    print(f"{exe}: {'OK to patch' if ok else 'byte mismatches'} "
          f"({len(HOOKS)} hooks + {len(dfmp)} DFM bytes + .tres section)")
    if not ok: return False
    if '--apply' not in sys.argv: return True

    if not os.path.exists(backup):
        shutil.copyfile(path, backup); print(f"  backup -> {backup}")
    for site, orig, new, desc in HOOKS:
        off = va2off(site)
        d[off:off+len(new)] = new
    for off, orig, new, desc in dfmp:
        d[off:off+1] = new
    # new section header + count + SizeOfImage; raw data appended 0x200-aligned
    raw_len = (len(blob_bytes) + 0x1FF) & ~0x1FF
    sec_hdr = struct.pack("<8sIIIIIIHHI", b".tres", len(blob_bytes), SEC_RVA,
                          raw_len, SEC_FOFF, 0, 0, 0, 0, 0xE0000060)
    d[shdr_off:shdr_off+40] = sec_hdr
    struct.pack_into('<H', d, e+6, nsec+1)
    struct.pack_into('<I', d, soi_off, SEC_RVA + 0x1000)
    d.extend(blob_bytes + b"\x00" * (raw_len - len(blob_bytes)))
    open(path, 'wb').write(d)
    print(f"  {exe}: applied (.tres @ {SEC_VA:08X}, {len(blob_bytes):#x} bytes).")
    return True

allok = all(process(x) for x in EXES)
if '--apply' not in sys.argv and allok:
    print("\nDry run OK. Re-run with --apply to write.")
sys.exit(0 if allok else 1)
