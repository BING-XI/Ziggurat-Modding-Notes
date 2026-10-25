r"""World Map level strip, v5 -- the AoWz.exe (UI) half of the Firmament and Abyss map levels.

The World Map window's level strip (`TSWindow.ScannerTab`, a `TAOWTabPanel`) is a fixed grid of
two rows of three cells (owner ruling 2026-09-27, built 2026-10-21):

        Surface  | Firmament | Faery          cell 0 1 2  ->  level 0 3 5
        Caverns  | Depths    | Abyss          cell 3 4 5  ->  level 1 2 4

A cell is BLANK (the empty tab button, no caption, not clickable) unless its level exists on the
map, is not switched off in the map's level mask ([TAoWHSMap+0x41C], build_maplevel4.py v4) and has at least one hex
explored by the seated player.  The level being viewed is always drawn.  Faery (level 5) does not
exist yet, so its cell is always blank.  PgUp / PgDn walk Firmament 3 / Surface 0 / Caverns 1 /
Depths 2 / Abyss 4 and skip blank levels.  Storage is untouched: this script only maps cells and
keys onto level indices.  The DLL half is build_maplevel4.py.

--------------------------------------------------------------------------------------
THE FIVE HOOK SITES  (AoWz.exe, image base 0x400000; same build as vanilla AoW.exe)
--------------------------------------------------------------------------------------
1. Caption fill, in the function at 0x00454D2C (ebx = &TSWindow, esi = &TheMap, ebp = its frame).
   hook 0x00454FED, 11 B  `8b8014010000 8b10 ff5240` (Strings.Clear) -> `E9 cave_caps` + 6x90.
   cave_caps gives the strip its own VMT (below), flags it for re-alignment ([tab+0x2D] = 0;
   vanilla's tail clears +0x2E, so the next Setup runs SetSize -> ReAlign -> SetSize), fills the
   six captions in cell order (Surface/Caverns/Depths through the vanilla LoadResString ->
   TranslateRStr -> Add sequence, Firmament/Faery/Abyss as cave const strings), drops the
   explored-levels cache, and `jmp 0x0045508F` (vanilla's SetIndex(0) tail).
   /!\ Do not hook 0x00454FF8 instead: a 5-byte E9 there covers the .reloc entry at 0x00454FFC.
   The dead vanilla block 0x00454FF8..0x0045508E keeps its three relocations; nothing reaches it.
2. `TSWindow.ScannerTabChange @0x00451BC8`, hook 0x00451BDC, 5 B `83ea01 7207` -> `E9 cave_tabsel`.
   edx = cell.  Cell outside 0..5, or its level >= the level count -> `jmp 0x00451C4C` (ret)
   untouched; else [Scanner+0x17C] = -1 and THSMap.ViewLevel (VMT +0xB8).  The rejection is
   load-bearing: vanilla's three-arm dispatch was also a whitelist, and ViewLevel has no lower
   bound (a tab panel with nothing selected reports -1).
3. `TMWindow.MapViewerSceneChanged`, call rel32 at 0x00451145 (-> aowInt TAOWTabPanel.SetIndex
   thunk 0x004031E4) retargeted to cave_setidx: level -> cell (-1 above level 7).
4./5. `MapWindowKeyDown` PgUp 0x004514BF `4a`+call / PgDn 0x004514D5 `42`+call (call SetSceneL
   0x00401E54): `dec`/`inc` become `90`, the calls go to cave_lvlup / cave_lvldn, which step along
   CHAIN to the next drawn level (or stay) and tail-jump to SetSceneL.

--------------------------------------------------------------------------------------
THE GRID -- a per-instance VMT, nothing in aowInt.dpl changes
--------------------------------------------------------------------------------------
TAOWTabPanel (aowInt.dpl, VMT 0x59817714 at the preferred base, InstanceSize 0x130) lays tabs out
in one row; it is shared by six controls, so the class is left alone.  do_swap copies the
instance's VMT (-0x40..+0xA4, 0xE4 B; +0xA4 is the class-name string) into cave B, makes the
copy a subclass of the original (vmtSelfPtr -> copy; vmtParent -> G_PCELL -> original VMT, the
D3 indirect parent cell) and points three slots at cave code:
    +0x30 SetSize        original, then [tab+0x80] *= 2: the control's rect covers two rows, so
                         ReAlign (ahBottom: y = parentH - BottomOffset - height) grows it upward
                         and the vanilla MouseUp/MouseMove bounds checks cover both rows.
    +0x80 Draw           calls the original Draw once per cell with x +0x84, y +0x88,
                         width +0x7C, height +0x80, captions +0x114 and pressed index +0x118
                         set to that cell, then restores them.  A blank cell is drawn unpressed
                         with the font +0x8C nil: Draw tests the font and skips the caption, so
                         the cell is the empty button (owner 2026-10-21: no bare background).  The captions are a fake
                         one-entry TStrings (FAKE: VMT +0x14 Count = 1, +0x0C Get forwards to the
                         real list's Get with the cell index), so the original's own geometry,
                         images, fonts and pressed state draw each cell.  The last column takes
                         the remainder of width div 3.
    +0x84 CheckMouseDown inherited (TAOWControl, through the parent VMT's +0x84), the vanilla
                         bounds test, cell = row*3 + col from both coordinates, SetIndex only
                         for a drawn cell, then the OnMouseDown event (ScannerTabMouseDown) as
                         vanilla.  A click on a blank cell is consumed and does nothing.
The original methods are reached through G_ORIG, read from the live instance, so aowInt's load
address does not matter.  The swap is guarded on InstanceSize 0x130 and the class name.  All
three methods are only ever reached through the VMT (byte scan of aowInt.dpl and AoWz.exe:
no direct call or absolute reference outside the VMT).

Drawn levels (vis_levels): exist ((1 << count) - 1), minus the mask byte [map+0x41C], AND
(explored by the seated player OR the viewer's level [[[0x0045B298]+0x48]+0x38]).  Explored = any
field of the level with bit (p-1) of [field+0x18] set (TAoWMapField.GetExplored), p = byte
[map+0xA5]; fields at [level+0x2C], stride [level+0x28], count = level VMT +0x54 (the
TAoWMapLevel.ResetFog walk); level = [[[container+8]+4]+L*4] (TMapContainer.GetMapLevel).  No
seated player (p = 0 or > 32, e.g. 0xFF) -> no exploration filter.  Explored levels are cached in
G_SEEN, keyed on (TheMap, p) and dropped by cave_caps; exploration is monotone, so only unexplored
levels are rescanned on a draw.

--------------------------------------------------------------------------------------
FORM DATA (TSWindow DFM, RCDATA at file 0x001C4F48; each value rewritten in place, same type)
--------------------------------------------------------------------------------------
    Scanner.Alignment.BottomOffset   file 0x1C61F4  vaInt8   32 -> 47   (map ends above row 1)
    ScannerWindow.MinHeight          file 0x1C527A  vaInt16 216 -> 231  (minimum map size kept)
    ScannerWindow.WinHeight          file 0x1C52B8  vaInt16 216 -> 231
A row is 15 px: the strip's design WinTop is 182 in a 216 px window with BottomOffset 19.

--------------------------------------------------------------------------------------
CAVES (`.hcol`, RVA 0x212000, file 0x20C200, read/write/execute; absolute addressing, fixed base)
--------------------------------------------------------------------------------------
    A 0x0062A000..0x0062A3FF  tables CELL2LVL[6], LVL2CELL[8], CHAIN[5]; const AnsiStrings
                              (refcount -1, never freed) Firmament / Faery / Abyss; cave_caps,
                              cave_tabsel, cave_setidx, cave_lvlup, cave_lvldn.
    B 0x0062B600..0x0062BBFF  globals G_ORIG / G_PCELL / G_MAP / G_PLR / G_SEEN, FAKE + its VMT,
                              the VMT copy (written at run time; zero on disk), the class-name
                              guard, then fs_get, fs_count, vis_levels, cell_mask, my_setsize,
                              my_draw, my_mdown, do_swap.
Every cross-block reference is backward, so each block assembles in one pass.

v4 (one row, Firmament | Surface | Caverns | Depths | Abyss) and the first v5 build (blank cells
left undrawn, 2026-10-21) are recognised by their cave hashes and are rewritten in place by --apply.

RNG: none.  No resolved filesystem path, no username.

USAGE
    python build_skylevel_ui.py            dry run: report the state of AoWz.exe
    python build_skylevel_ui.py --apply    install v5 (from unpatched or v4)
    python build_skylevel_ui.py --undo     surgical: the five sites, the three form values, both
                                           caves zeroed.  Touches no backup.
    python build_skylevel_ui.py --dis      disassemble the caves
"""

import os, sys, struct, hashlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))

from pescan import PE
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import zigexe                                      # mod binary names

TARGETS = [os.path.join(GAME, n) for n in zigexe.EXES]   # AoWz.exe


def require(cond, msg):
    if not cond:
        sys.exit("ABORT: " + msg)


# ---------------------------------------------------------------- engine addresses
MAPSLOT   = 0x0045DF7C     # holds &TheMap (AoWEPACK global, via an import slot)
VIEWSLOT  = 0x0045B298     # global: [ +0x48] = THSMapViewer, [viewer+0x38] = viewed level
RS_SURF   = 0x0045A0C0     # PResStringRec slots for Surface / Caverns / Depths
RS_CAV    = 0x0045A288
RS_DEP    = 0x0045A3F8
LOADRES   = 0x00401180     # VCL30  System.LoadResString   (eax = PResStringRec, edx = @result)
TRANSL    = 0x004021E4     # AoWEPACK AoWE.TranslateRStr   (eax = source, edx = @result)
SETIDX    = 0x004031E4     # aowInt  TAOWTabPanel.SetIndex (eax = self, edx = index)
SETSCENEL = 0x00401E54     # HSEPack THSMapViewer.SetSceneL(eax = self, edx = level)

RET_CAPS  = 0x0045508F     # resume: the vanilla SetIndex(0) tail
RET_TAB   = 0x00451C4C     # resume: ScannerTabChange's ret

MASK_OFF  = 0x41C          # TAoWHSMap: disabled-levels mask byte (build_maplevel4.py v4)
SEAT_OFF  = 0xA5           # TAoWHSMap: seated player

# TAOWTabPanel instance / VMT
T_X, T_Y, T_W, T_H = 0x84, 0x88, 0x7C, 0x80
T_PARENT, T_STR, T_SEL, T_HIT = 0x10C, 0x114, 0x118, 0x78
T_ALIGNED = 0x2D
T_FONT = 0x8C                              # AOWFont; Draw skips the caption when nil
V_SETSIZE, V_DRAW, V_MDOWN = 0x30, 0x80, 0x84
VMT_LO, VMT_HI = -0x40, 0xA4               # copied span of the class VMT
TABPANEL_INSTSIZE = 0x130

# ---------------------------------------------------------------- the grid
CELL2LVL = (0, 3, 5, 1, 2, 4)             # Surface Firmament Faery / Caverns Depths Abyss
LVL2CELL = tuple(CELL2LVL.index(l) if l in CELL2LVL else -1 for l in range(8))
CHAIN    = (3, 0, 1, 2, 4)                # PgUp <- -> PgDn
CAPTIONS = {1: b"Firmament", 2: b"Faery", 5: b"Abyss"}   # cells with a cave literal

# ---------------------------------------------------------------- hook sites
H_CAPS, H_CAPS_N = 0x00454FED, 11
ORIG_CAPS = bytes.fromhex("8b8014010000" "8b10" "ff5240")
H_TAB, H_TAB_N = 0x00451BDC, 5
ORIG_TAB = bytes.fromhex("83ea01" "7207")
C_SETIDX = 0x00451145
C_UP_B, C_UP_C = 0x004514BF, 0x004514C0
C_DN_B, C_DN_C = 0x004514D5, 0x004514D6

# ---------------------------------------------------------------- form data (file offsets)
DFM_SITES = [  # (label, file offset of the value-type byte, original bytes, new bytes)
    ("Scanner.BottomOffset 32->47",  0x1C61F3, bytes.fromhex("0220"),   bytes.fromhex("022f")),
    ("ScannerWindow.MinHeight 216->231", 0x1C5279, bytes.fromhex("03d800"), bytes.fromhex("03e700")),
    ("ScannerWindow.WinHeight 216->231", 0x1C52B7, bytes.fromhex("03d800"), bytes.fromhex("03e700")),
]
DFM_NAMES = {0x1C61F3: b"\x16Alignment.BottomOffset", 0x1C5279: b"\x09MinHeight",
             0x1C52B7: b"\x09WinHeight"}

# ---------------------------------------------------------------- cave A layout
CAVE_A, CAVE_A_N = 0x0062A000, 0x400
A_CELL2LVL = CAVE_A + 0x00              # 6 dwords
A_LVL2CELL = CAVE_A + 0x18              # 8 dwords
A_CHAIN    = CAVE_A + 0x38              # 5 dwords
A_STR      = {1: CAVE_A + 0x4C, 2: CAVE_A + 0x60, 5: CAVE_A + 0x70}   # caption records
A_CODE     = CAVE_A + 0x80

# ---------------------------------------------------------------- cave B layout
CAVE_B, CAVE_B_N = 0x0062B600, 0x600
G_ORIG   = CAVE_B + 0x00                # original TAOWTabPanel VMT (run time)
G_PCELL  = CAVE_B + 0x04                # parent cell of the copy -> original VMT (run time)
G_MAP    = CAVE_B + 0x08                # explored-levels cache key: TheMap
G_PLR    = CAVE_B + 0x0C                #                            seated player
G_SEEN   = CAVE_B + 0x10                # explored-levels bitmask
FAKE     = CAVE_B + 0x14                # +0 VMT (static), +4 real TStrings, +8 cell
FAKE_VMT = CAVE_B + 0x20                # 0x18 B: +0x0C Get, +0x14 Count
CLONE    = CAVE_B + 0x40                # VMT copy, 0xE4 B (run time)
CLONE_VMT = CLONE - VMT_LO
NAME     = CAVE_B + 0x130               # "TAOWTabPanel" -- the swap guard
B_CODE   = CAVE_B + 0x140

V4_CAVE_SHA = "638a5984c455600b09cc2e91a76b94acfe5e9df7433341f47470f64535fa7171"
V5A_CAVE_SHA = ("604c50daf249778f6a4dd46af17dc559a7e45c16197768fc28a129a01e1eea28",   # cave A
                "a3952d353ff307a883f35f1dded6f0f2ac63068024f3bfe6425afbf3a0c0724d")   # cave B
V4_SITES = [bytes.fromhex("e96e501d00909090909090"), bytes.fromhex("e96b851d00"),
            bytes.fromhex("e84a901d00"), bytes.fromhex("90e8f38c1d00"),
            bytes.fromhex("90e8218d1d00")]

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def rel32(src_end, dst):
    return struct.pack("<i", dst - src_end)


def call_rel(at, dst):
    return b"\xE8" + rel32(at + 5, dst)


def jmp_rel(at, dst):
    return b"\xE9" + rel32(at + 5, dst)


# ---------------------------------------------------------------- cave B source
def src_fs_get():
    return """
        /* fake TStrings.Get: eax = FAKE, ecx = @result -> real.Get(cell, @result) */
        push ebx
        mov  ebx, dword ptr [eax+4]
        mov  edx, dword ptr [eax+8]
        mov  eax, ebx
        mov  ebx, dword ptr [ebx]
        call dword ptr [ebx+0xC]
        pop  ebx
        ret
    """


def src_fs_count():
    return """
        mov  eax, 1
        ret
    """


def src_vis_levels():
    return f"""
        /* eax = bitmask of the levels to draw; keeps ebx esi edi ebp */
        push ebx
        push esi
        push edi
        push ebp
        xor  ebp, ebp
        mov  ebx, dword ptr [{MAPSLOT:#x}]
        mov  ebx, dword ptr [ebx]
        test ebx, ebx
        jz   Vdone
        mov  esi, dword ptr [ebx+0x10]               /* TMapContainer */
        test esi, esi
        jz   Vdone
        mov  ecx, dword ptr [esi+0x14]               /* level count */
        cmp  ecx, 8
        jbe  Vc
        mov  ecx, 8
    Vc:
        mov  ebp, 1
        shl  ebp, cl
        dec  ebp                                     /* levels that exist */
        movzx eax, byte ptr [ebx+{MASK_OFF:#x}]
        not  eax
        and  ebp, eax                                /* ... and are switched on */
        movzx edi, byte ptr [ebx+{SEAT_OFF:#x}]      /* seated player */
        cmp  ebx, dword ptr [{G_MAP:#x}]
        jne  Vreset
        cmp  edi, dword ptr [{G_PLR:#x}]
        je   Vkeyed
    Vreset:
        mov  dword ptr [{G_MAP:#x}], ebx
        mov  dword ptr [{G_PLR:#x}], edi
        mov  dword ptr [{G_SEEN:#x}], 0
    Vkeyed:
        lea  eax, [edi-1]
        cmp  eax, 31
        ja   Vdone                                   /* nobody seated: no exploration filter */
        xor  eax, eax
        push eax                                     /* [esp] = L */
    Vlevel:
        mov  ecx, dword ptr [esp]
        bt   ebp, ecx
        jnc  Vnext
        bt   dword ptr [{G_SEEN:#x}], ecx
        jc   Vnext
        mov  eax, dword ptr [esi+8]
        mov  eax, dword ptr [eax+4]
        mov  eax, dword ptr [eax+ecx*4]              /* TAoWMapLevel L */
        test eax, eax
        jz   Vnext
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0x54]                    /* field count */
        pop  edx
        test eax, eax
        jle  Vnext
        mov  ecx, eax
        push ebx
        mov  ebx, dword ptr [edx+0x28]               /* field stride */
        mov  edx, dword ptr [edx+0x2C]               /* first field */
        lea  eax, [edi-1]                            /* explored bit of the seated player */
    Vscan:
        bt   dword ptr [edx+0x18], eax
        jc   Vfound
        add  edx, ebx
        dec  ecx
        jnz  Vscan
        pop  ebx
        jmp  Vnext
    Vfound:
        pop  ebx
        mov  ecx, dword ptr [esp]
        bts  dword ptr [{G_SEEN:#x}], ecx
    Vnext:
        inc  dword ptr [esp]
        cmp  dword ptr [esp], 8
        jb   Vlevel
        pop  eax
        mov  eax, dword ptr [{G_SEEN:#x}]
        mov  ecx, dword ptr [{VIEWSLOT:#x}]
        test ecx, ecx
        jz   Vcur
        mov  ecx, dword ptr [ecx+0x48]               /* THSMapViewer */
        test ecx, ecx
        jz   Vcur
        mov  ecx, dword ptr [ecx+0x38]               /* the viewed level is always drawn */
        cmp  ecx, 7
        ja   Vcur
        bts  eax, ecx
    Vcur:
        and  ebp, eax
    Vdone:
        mov  eax, ebp
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """


def src_cell_mask(a):
    return f"""
        /* eax = bitmask of the cells to draw */
        push ebx
        call {a['vis_levels']:#x}
        mov  ebx, eax
        xor  eax, eax
        xor  ecx, ecx
    Cm:
        mov  edx, dword ptr [ecx*4+{A_CELL2LVL:#x}]
        bt   ebx, edx
        jnc  Cn
        bts  eax, ecx
    Cn:
        inc  ecx
        cmp  ecx, 6
        jb   Cm
        pop  ebx
        ret
    """


def src_my_setsize():
    return f"""
        push ebx
        mov  ebx, eax
        mov  ecx, dword ptr [{G_ORIG:#x}]
        call dword ptr [ecx+{V_SETSIZE:#x}]
        shl  dword ptr [ebx+{T_H:#x}], 1             /* two rows */
        pop  ebx
        ret
    """


def src_my_draw(a):
    return f"""
        /* eax = self, edx = draw descriptor */
        push ebp
        mov  ebp, esp
        sub  esp, 0x30
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  dword ptr [ebp-0x04], edx
        mov  eax, dword ptr [ebx+{T_X:#x}]
        mov  dword ptr [ebp-0x08], eax
        mov  eax, dword ptr [ebx+{T_Y:#x}]
        mov  dword ptr [ebp-0x0C], eax
        mov  eax, dword ptr [ebx+{T_W:#x}]
        mov  dword ptr [ebp-0x10], eax
        mov  eax, dword ptr [ebx+{T_H:#x}]
        mov  dword ptr [ebp-0x14], eax
        mov  eax, dword ptr [ebx+{T_STR:#x}]
        mov  dword ptr [ebp-0x18], eax
        mov  eax, dword ptr [ebx+{T_SEL:#x}]
        mov  dword ptr [ebp-0x1C], eax
        mov  eax, dword ptr [ebx+{T_FONT:#x}]
        mov  dword ptr [ebp-0x2C], eax
        call {a['cell_mask']:#x}
        mov  dword ptr [ebp-0x20], eax               /* cells with a level */
        mov  eax, dword ptr [ebp-0x10]
        cdq
        mov  ecx, 3
        idiv ecx
        mov  dword ptr [ebp-0x24], eax               /* cell width */
        mov  eax, dword ptr [ebp-0x14]
        sar  eax, 1
        mov  dword ptr [ebp-0x28], eax               /* row height */
        mov  dword ptr [ebx+{T_H:#x}], eax
        mov  eax, dword ptr [ebp-0x18]
        mov  dword ptr [{FAKE + 4:#x}], eax
        mov  dword ptr [ebx+{T_STR:#x}], {FAKE:#x}
        xor  edi, edi
    Dcell:
        mov  eax, edi
        xor  edx, edx
        mov  ecx, 3
        div  ecx                                     /* eax = row, edx = column */
        imul eax, dword ptr [ebp-0x28]
        add  eax, dword ptr [ebp-0x0C]
        mov  dword ptr [ebx+{T_Y:#x}], eax
        mov  eax, edx
        imul eax, dword ptr [ebp-0x24]
        add  eax, dword ptr [ebp-0x08]
        mov  dword ptr [ebx+{T_X:#x}], eax
        mov  eax, dword ptr [ebp-0x24]
        cmp  edx, 2
        jne  Dwid
        mov  eax, dword ptr [ebp-0x10]               /* last column takes the remainder */
        sub  eax, dword ptr [ebp-0x24]
        sub  eax, dword ptr [ebp-0x24]
    Dwid:
        mov  dword ptr [ebx+{T_W:#x}], eax
        mov  dword ptr [{FAKE + 8:#x}], edi
        mov  eax, dword ptr [ebp-0x2C]
        or   ecx, -1                                 /* not pressed */
        bt   dword ptr [ebp-0x20], edi
        jc   Dlvl
        xor  eax, eax                                /* blank: no font, so Draw skips the caption */
        jmp  Dset
    Dlvl:
        cmp  edi, dword ptr [ebp-0x1C]
        jne  Dset
        xor  ecx, ecx                                /* pressed */
    Dset:
        mov  dword ptr [ebx+{T_FONT:#x}], eax
        mov  dword ptr [ebx+{T_SEL:#x}], ecx
        mov  edx, dword ptr [ebp-0x04]
        mov  eax, ebx
        mov  ecx, dword ptr [{G_ORIG:#x}]
        call dword ptr [ecx+{V_DRAW:#x}]             /* the original Draw, one cell */
    Dnext:
        inc  edi
        cmp  edi, 6
        jb   Dcell
        mov  eax, dword ptr [ebp-0x08]
        mov  dword ptr [ebx+{T_X:#x}], eax
        mov  eax, dword ptr [ebp-0x0C]
        mov  dword ptr [ebx+{T_Y:#x}], eax
        mov  eax, dword ptr [ebp-0x10]
        mov  dword ptr [ebx+{T_W:#x}], eax
        mov  eax, dword ptr [ebp-0x14]
        mov  dword ptr [ebx+{T_H:#x}], eax
        mov  eax, dword ptr [ebp-0x18]
        mov  dword ptr [ebx+{T_STR:#x}], eax
        mov  eax, dword ptr [ebp-0x1C]
        mov  dword ptr [ebx+{T_SEL:#x}], eax
        mov  eax, dword ptr [ebp-0x2C]
        mov  dword ptr [ebx+{T_FONT:#x}], eax
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """


def src_my_mdown(a):
    return f"""
        /* eax = self, dl = button, cl = shift, [ebp+0xC] = X, [ebp+8] = Y; ret 8 */
        push ebp
        mov  ebp, esp
        push ecx
        push ebx
        push esi
        push edi
        mov  byte ptr [ebp-2], cl
        mov  byte ptr [ebp-1], dl
        mov  ebx, eax
        mov  esi, dword ptr [ebp+0xC]
        push esi
        push dword ptr [ebp+8]
        mov  cl, byte ptr [ebp-2]
        mov  dl, byte ptr [ebp-1]
        mov  eax, dword ptr [{G_ORIG:#x}]
        mov  eax, dword ptr [eax-0x18]               /* parent cell */
        mov  edi, dword ptr [eax]                    /* TAOWControl VMT */
        mov  eax, ebx
        call dword ptr [edi+{V_MDOWN:#x}]            /* inherited CheckMouseDown */
        xor  eax, eax
        mov  dword ptr [ebx+{T_HIT:#x}], eax
        mov  eax, dword ptr [ebx+{T_PARENT:#x}]
        mov  edx, dword ptr [eax+0x84]
        add  edx, dword ptr [ebx+{T_X:#x}]
        mov  ecx, esi
        sub  ecx, edx                                /* dx */
        js   Mout
        cmp  ecx, dword ptr [ebx+{T_W:#x}]
        jge  Mout
        mov  edx, dword ptr [eax+0x88]
        add  edx, dword ptr [ebx+{T_Y:#x}]
        mov  edi, dword ptr [ebp+8]
        sub  edi, edx                                /* dy */
        js   Mout
        cmp  edi, dword ptr [ebx+{T_H:#x}]
        jge  Mout
        mov  dword ptr [ebx+{T_HIT:#x}], 0xffffffff
        cmp  byte ptr [ebp-1], 0
        jne  Mevent
        push ecx
        mov  eax, dword ptr [ebx+{T_W:#x}]
        cdq
        mov  ecx, 3
        idiv ecx
        mov  ecx, eax                                /* cell width */
        pop  eax
        test ecx, ecx
        jle  Mevent
        cdq
        idiv ecx                                     /* column */
        cmp  eax, 2
        jle  Mc
        mov  eax, 2
    Mc:
        push eax
        mov  ecx, dword ptr [ebx+{T_H:#x}]
        sar  ecx, 1                                  /* row height */
        xor  eax, eax
        test ecx, ecx
        jle  Mr
        mov  eax, edi
        cdq
        idiv ecx                                     /* row */
        cmp  eax, 1
        jle  Mr
        mov  eax, 1
    Mr:
        lea  eax, [eax+eax*2]
        pop  edx
        add  eax, edx
        mov  edi, eax                                /* cell */
        call {a['cell_mask']:#x}
        bt   eax, edi
        jnc  Mevent                                  /* blank cell: consumed, no selection */
        mov  edx, edi
        mov  eax, ebx
        call {SETIDX:#x}
    Mevent:
        cmp  word ptr [ebx+0x46], 0
        je   Mout
        mov  al, byte ptr [ebp-2]
        push eax
        push esi
        push dword ptr [ebp+8]
        mov  cl, byte ptr [ebp-1]
        mov  edx, ebx
        mov  eax, dword ptr [ebx+0x48]
        call dword ptr [ebx+0x44]                    /* OnMouseDown */
    Mout:
        pop  edi
        pop  esi
        pop  ebx
        pop  ecx
        pop  ebp
        ret  8
    """


def src_do_swap(a):
    return f"""
        /* eax = the strip; give it the grid VMT once */
        push ebx
        push esi
        push edi
        mov  ebx, eax
        test ebx, ebx
        jz   Sret
        mov  esi, dword ptr [ebx]
        cmp  esi, {CLONE_VMT:#x}
        je   Sret
        cmp  dword ptr [esi-0x1C], {TABPANEL_INSTSIZE:#x}
        jne  Sret
        mov  eax, dword ptr [esi-0x20]               /* class name */
        cmp  byte ptr [eax], 12
        jne  Sret
        mov  edx, dword ptr [eax+1]
        cmp  edx, dword ptr [{NAME:#x}]
        jne  Sret
        mov  edx, dword ptr [eax+5]
        cmp  edx, dword ptr [{NAME + 4:#x}]
        jne  Sret
        mov  edx, dword ptr [eax+9]
        cmp  edx, dword ptr [{NAME + 8:#x}]
        jne  Sret
        mov  dword ptr [{G_ORIG:#x}], esi
        mov  dword ptr [{G_PCELL:#x}], esi
        lea  esi, [esi{VMT_LO:+#x}]
        mov  edi, {CLONE:#x}
        mov  ecx, {(VMT_HI - VMT_LO) // 4:#x}
    Scopy:
        mov  eax, dword ptr [esi]
        mov  dword ptr [edi], eax
        add  esi, 4
        add  edi, 4
        dec  ecx
        jnz  Scopy
        mov  dword ptr [{CLONE_VMT - 0x40:#x}], {CLONE_VMT:#x}
        mov  dword ptr [{CLONE_VMT - 0x18:#x}], {G_PCELL:#x}
        mov  dword ptr [{CLONE_VMT + V_SETSIZE:#x}], {a['my_setsize']:#x}
        mov  dword ptr [{CLONE_VMT + V_DRAW:#x}], {a['my_draw']:#x}
        mov  dword ptr [{CLONE_VMT + V_MDOWN:#x}], {a['my_mdown']:#x}
        mov  dword ptr [ebx], {CLONE_VMT:#x}
    Sret:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """


# ---------------------------------------------------------------- cave A source
def _add_resource(slot):
    """Mirror of one vanilla LoadResString/TranslateRStr/Add block, verbatim."""
    return f"""
        lea  edx, [ebp-0x14]
        mov  eax, dword ptr [{slot:#x}]
        call {LOADRES:#x}
        mov  eax, dword ptr [ebp-0x14]
        lea  edx, [ebp-0x10]
        call {TRANSL:#x}
        mov  edx, dword ptr [ebp-0x10]
        mov  eax, dword ptr [ebx]
        mov  eax, dword ptr [eax+0x4c]
        mov  eax, dword ptr [eax+0x114]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0x34]
    """


def _add_literal(cell):
    return f"""
        mov  edx, {A_STR[cell] + 8:#x}
        mov  eax, dword ptr [ebx]
        mov  eax, dword ptr [eax+0x4c]
        mov  eax, dword ptr [eax+0x114]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0x34]                    /* TStrings.Add */
    """


def src_caps(b):
    return f"""
        /* eax = ScannerTab, ebx = &TSWindow, esi = &TheMap, ebp = the caller's frame */
        call {b['do_swap']:#x}
        mov  eax, dword ptr [ebx]
        mov  eax, dword ptr [eax+0x4c]
        mov  byte ptr [eax+{T_ALIGNED:#x}], 0        /* re-align: the height doubles */
        mov  eax, dword ptr [eax+0x114]
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0x40]                    /* TStrings.Clear */
        {_add_resource(RS_SURF)}
        {_add_literal(1)}
        {_add_literal(2)}
        {_add_resource(RS_CAV)}
        {_add_resource(RS_DEP)}
        {_add_literal(5)}
        mov  dword ptr [{G_MAP:#x}], 0               /* drop the explored-levels cache */
        jmp  {RET_CAPS:#x}
    """


def src_tabsel():
    return f"""
        /* eax = TSWindow, edx = cell */
        cmp  edx, 5
        ja   Tret
        mov  edx, dword ptr [edx*4+{A_CELL2LVL:#x}]
        mov  ecx, dword ptr [{MAPSLOT:#x}]
        mov  ecx, dword ptr [ecx]
        mov  ecx, dword ptr [ecx+0x10]
        cmp  edx, dword ptr [ecx+0x14]
        jge  Tret
        mov  ecx, dword ptr [eax+0x5c]
        mov  dword ptr [ecx+0x17c], 0xffffffff       /* invalidate the scanner surface */
        mov  eax, dword ptr [{MAPSLOT:#x}]
        mov  eax, dword ptr [eax]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0xb8]                    /* THSMap.ViewLevel(edx) */
    Tret:
        jmp  {RET_TAB:#x}
    """


def src_setidx():
    return f"""
        /* eax = ScannerTab, edx = level */
        cmp  edx, 7
        ja   Sneg
        mov  edx, dword ptr [edx*4+{A_LVL2CELL:#x}]
        jmp  {SETIDX:#x}
    Sneg:
        or   edx, -1
        jmp  {SETIDX:#x}
    """


def src_step(b, name, up):
    step = f"""
        dec  eax
        js   {name}out
    """ if up else f"""
        inc  eax
        cmp  eax, {len(CHAIN)}
        jae  {name}out
    """
    return f"""
        /* eax = THSMapViewer, edx = viewed level */
        push eax
        push ebx
        push edx
        call {b['vis_levels']:#x}
        mov  ecx, eax
        pop  edx
        xor  eax, eax
    {name}find:
        cmp  edx, dword ptr [eax*4+{A_CHAIN:#x}]
        je   {name}step
        inc  eax
        cmp  eax, {len(CHAIN)}
        jb   {name}find
        jmp  {name}out
    {name}step:
        {step}
        mov  ebx, dword ptr [eax*4+{A_CHAIN:#x}]
        bt   ecx, ebx
        jnc  {name}step
        mov  edx, ebx
    {name}out:
        pop  ebx
        pop  eax
        jmp  {SETSCENEL:#x}
    """


# ---------------------------------------------------------------- assemble
def _assemble(blocks, base, limit, label):
    addrs, parts, va = {}, {}, base
    for name, srcf in blocks:
        src = srcf(addrs) if srcf.__code__.co_argcount else srcf()
        enc = bytes(ks.asm(src, va)[0])
        addrs[name], parts[name] = va, enc
        va = (va + len(enc) + 3) & ~3
    require(va <= limit, "%s overruns its block (%08X > %08X)" % (label, va, limit))
    return addrs, parts, va


B_ADDR, B_PARTS, B_END = _assemble(
    [("fs_get", src_fs_get), ("fs_count", src_fs_count), ("vis_levels", src_vis_levels),
     ("cell_mask", src_cell_mask), ("my_setsize", src_my_setsize), ("my_draw", src_my_draw),
     ("my_mdown", src_my_mdown), ("do_swap", src_do_swap)],
    B_CODE, CAVE_B + CAVE_B_N, "cave B")

A_ADDR, A_PARTS, A_END = _assemble(
    [("cave_caps", lambda: src_caps(B_ADDR)), ("cave_tabsel", src_tabsel),
     ("cave_setidx", src_setidx), ("cave_lvlup", lambda: src_step(B_ADDR, "U", True)),
     ("cave_lvldn", lambda: src_step(B_ADDR, "D", False))],
    A_CODE, CAVE_A + CAVE_A_N, "cave A")


def _blob(base, size, parts, addrs):
    blob = bytearray(size)
    for name, enc in parts.items():
        o = addrs[name] - base
        blob[o:o + len(enc)] = enc
    return blob


A_BLOB = _blob(CAVE_A, CAVE_A_N, A_PARTS, A_ADDR)
for i, v in enumerate(CELL2LVL):
    struct.pack_into("<i", A_BLOB, A_CELL2LVL - CAVE_A + 4 * i, v)
for i, v in enumerate(LVL2CELL):
    struct.pack_into("<i", A_BLOB, A_LVL2CELL - CAVE_A + 4 * i, v)
for i, v in enumerate(CHAIN):
    struct.pack_into("<i", A_BLOB, A_CHAIN - CAVE_A + 4 * i, v)
_end = A_CHAIN + 4 * len(CHAIN)
for cell, text in CAPTIONS.items():
    rec = A_STR[cell]
    require(rec >= _end, "caption record %08X overlaps the data before it" % rec)
    struct.pack_into("<iI", A_BLOB, rec - CAVE_A, -1, len(text))
    A_BLOB[rec - CAVE_A + 8:rec - CAVE_A + 9 + len(text)] = text + b"\0"
    _end = rec + 9 + len(text)
require(_end <= A_CODE, "caption records overrun the code base")
A_BLOB = bytes(A_BLOB)

B_BLOB = _blob(CAVE_B, CAVE_B_N, B_PARTS, B_ADDR)
struct.pack_into("<I", B_BLOB, FAKE - CAVE_B, FAKE_VMT)
struct.pack_into("<I", B_BLOB, FAKE_VMT + 0x0C - CAVE_B, B_ADDR["fs_get"])
struct.pack_into("<I", B_BLOB, FAKE_VMT + 0x14 - CAVE_B, B_ADDR["fs_count"])
B_BLOB[NAME - CAVE_B:NAME - CAVE_B + 12] = b"TAOWTabPanel"
require(CLONE + (VMT_HI - VMT_LO) <= NAME, "the VMT copy overruns the name guard")
require(not any(B_BLOB[CLONE - CAVE_B:CLONE - CAVE_B + (VMT_HI - VMT_LO)]), "VMT copy area not zero")
require(FAKE_VMT + 0x18 <= CLONE, "FAKE VMT overruns the copy area")
B_BLOB = bytes(B_BLOB)

# ---------------------------------------------------------------- patch table
ORIG_SITES = [ORIG_CAPS, ORIG_TAB, call_rel(C_SETIDX, SETIDX),
              b"\x4A" + call_rel(C_UP_C, SETSCENEL), b"\x42" + call_rel(C_DN_C, SETSCENEL)]
NEW_SITES = [jmp_rel(H_CAPS, A_ADDR["cave_caps"]) + b"\x90" * (H_CAPS_N - 5),
             jmp_rel(H_TAB, A_ADDR["cave_tabsel"]),
             call_rel(C_SETIDX, A_ADDR["cave_setidx"]),
             b"\x90" + call_rel(C_UP_C, A_ADDR["cave_lvlup"]),
             b"\x90" + call_rel(C_DN_C, A_ADDR["cave_lvldn"])]
SITE_VAS = [H_CAPS, H_TAB, C_SETIDX, C_UP_B, C_DN_B]
SITE_LABELS = ["caption fill", "tab change", "SetIndex call", "PgUp", "PgDn"]
for o, n, v4 in zip(ORIG_SITES, NEW_SITES, V4_SITES):
    require(len(o) == len(n) == len(v4), "site length mismatch")


# ---------------------------------------------------------------- file helpers
class Image:
    def __init__(self, path):
        self.path = path
        self.pe = PE(path)
        self.data = bytearray(self.pe.data)
        require(self.pe.image_base == 0x400000, "%s: unexpected image base" % path)

    def off(self, va):
        o = self.pe.rva2off(va - 0x400000)
        require(o is not None, "VA %08X is not mapped in %s" % (va, self.path))
        return o

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.data[o:o + n])

    def write(self, va, b):
        o = self.off(va)
        self.data[o:o + len(b)] = b

    def save(self):
        with open(self.path, "wb") as f:
            f.write(self.data)


def state(img):
    """('orig' | 'v4' | 'v5' | 'mixed', problems)"""
    probs = []
    sites = []
    for lab, va, o, n, v4 in zip(SITE_LABELS, SITE_VAS, ORIG_SITES, NEW_SITES, V4_SITES):
        cur = img.read(va, len(o))
        # a set: v4 and v5 assemble cave_lvldn at the same address, so PgDn matches both
        sites.append({t for t, b in (("orig", o), ("v5", n), ("v4", v4)) if cur == b})
        if not sites[-1]:
            probs.append("%s @%08X: %s" % (lab, va, cur.hex(" ")))
    dfm = []
    for lab, fo, o, n in DFM_SITES:
        nm = DFM_NAMES[fo]
        require(bytes(img.data[fo - len(nm):fo]) == nm, "%s: property name not where expected" % lab)
        cur = bytes(img.data[fo:fo + len(o)])
        dfm.append("orig" if cur == o else "v5" if cur == n else None)
        if dfm[-1] is None:
            probs.append("%s @file %X: %s" % (lab, fo, cur.hex(" ")))
    a = img.read(CAVE_A, CAVE_A_N)
    b = img.read(CAVE_B, CAVE_B_N)
    ha, hb = hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest()
    ca = ("zero" if not any(a) else "v5" if a == A_BLOB else "v4" if ha == V4_CAVE_SHA else
          "v5a" if ha == V5A_CAVE_SHA[0] else None)
    cb = ("zero" if not any(b) else "v5" if b == B_BLOB else
          "v5a" if hb == V5A_CAVE_SHA[1] else None)
    if ca is None:
        probs.append("cave A %08X holds bytes this script did not write" % CAVE_A)
    if cb is None:
        probs.append("cave B %08X holds bytes this script did not write" % CAVE_B)
    if probs:
        return "unknown", probs
    def all_sites(tag):
        return all(tag in s for s in sites)
    if all_sites("orig") and set(dfm) == {"orig"} and ca == "zero" and cb == "zero":
        return "orig", []
    if all_sites("v4") and set(dfm) == {"orig"} and ca == "v4" and cb == "zero":
        return "v4", []
    if all_sites("v5") and set(dfm) == {"v5"} and ca == "v5" and cb == "v5":
        return "v5", []
    if all_sites("v5") and set(dfm) == {"v5"} and ca == "v5a" and cb == "v5a":
        return "v5a", []
    return "mixed", []


STATE_TEXT = {"orig": "unpatched", "v4": "v4 (one row) -- --apply rewrites it in place",
              "v5a": "first v5 build (blank cells undrawn) -- --apply rewrites it in place",
              "v5": "applied (v5 -- two-row grid)", "mixed": "half-written -- run --apply",
              "unknown": "unrecognised bytes"}


def show_state():
    for path in TARGETS:
        img = Image(path)
        st, probs = state(img)
        print("%-10s %s" % (os.path.basename(path), STATE_TEXT[st]))
        for lab, va, o in zip(SITE_LABELS, SITE_VAS, ORIG_SITES):
            print("    %-14s %08X  %s" % (lab, va, img.read(va, len(o)).hex(" ")))
        for lab, fo, o, n in DFM_SITES:
            print("    %-34s file %X  %s" % (lab, fo, bytes(img.data[fo:fo + len(o)]).hex(" ")))
        for p in probs:
            print("    !! " + p)


def disassemble():
    for label, base, parts, addrs in (("A", CAVE_A, A_PARTS, A_ADDR), ("B", CAVE_B, B_PARTS, B_ADDR)):
        for name, enc in parts.items():
            print("---- cave %s  %s @%08X (%d B) ----" % (label, name, addrs[name], len(enc)))
            n = 0
            for i in cs.disasm(enc, addrs[name]):
                print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
                n += i.size
            require(n == len(enc), "%s does not disassemble cleanly" % name)
            print()
    print("cave A used %d of %d B, cave B used %d of %d B"
          % (A_END - CAVE_A, CAVE_A_N, B_END - CAVE_B, CAVE_B_N))


def apply_all(undo=False):
    for path in TARGETS:
        img = Image(path)
        st, probs = state(img)
        require(not probs, "%s: %s" % (os.path.basename(path), "; ".join(probs)))
        print("%s: %s" % (os.path.basename(path), STATE_TEXT[st]))
        if (undo and st == "orig") or (not undo and st == "v5"):
            print("    nothing to do")
            continue
        for va, o, n in zip(SITE_VAS, ORIG_SITES, NEW_SITES):
            img.write(va, o if undo else n)
        for lab, fo, o, n in DFM_SITES:
            img.data[fo:fo + len(o)] = o if undo else n
        img.write(CAVE_A, b"\0" * CAVE_A_N if undo else A_BLOB)
        img.write(CAVE_B, b"\0" * CAVE_B_N if undo else B_BLOB)
        img.save()
        back = Image(path)
        want = "orig" if undo else "v5"
        require(state(back)[0] == want, "%s: did not read back as %s" % (path, want))
        print("    written, reads back as %s" % want)
    print()
    show_state()


def main():
    args = sys.argv[1:]
    print("World Map level strip v5 (%s): cave A %08X %d/%d B, cave B %08X %d/%d B\n"
          % (", ".join(zigexe.EXES), CAVE_A, A_END - CAVE_A, CAVE_A_N,
             CAVE_B, B_END - CAVE_B, CAVE_B_N))
    if "--dis" in args:
        disassemble()
    elif "--undo" in args:
        apply_all(undo=True)
    elif "--apply" in args:
        apply_all(undo=False)
    else:
        show_state()
        print("\n(dry run -- nothing written; use --apply)")


if __name__ == "__main__":
    main()
