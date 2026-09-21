#!/usr/bin/env python3
r"""build_itembanner_hpmv.py -- the item banner shows HITS and MOVES beside ATK / DAM / DEF / RES.

`build_item_hpmv.py` (applied, AoWEPACK.dpl) made items grant bonus hit points and movement,
stored as two signed bytes inside the existing TItem allocation:

    item+0x4A = HP bonus        item+0x4B = MV bonus        both SIGNED (-128..127)

Nothing in the interface ever showed them. The right-click item banner popup renders exactly four
icon+value pairs and stops. This script adds the fifth and sixth, in the same grid, from the same
two bytes.

ROLL: NONE. This feature draws no random number and inherits none -- it reads two already-stored
bytes and paints them. `TItemBanner.IBannerPopupShow` makes no draw of its own, neither cave calls
anything that does, and no replicated state is written. So there is no pattern to pick from the
P1..P5 taxonomy; `rng_audit.py AoWz.exe --owners` and `--hash` are unchanged by this patch, and
that is the expected result, not an oversight.

================================================================================
WHERE THE CODE IS
================================================================================
`TItemBanner` exists ONLY in AoWz.exe / AoWzCompat.exe -- the class name appears in no .dpl and in
neither editor binary (checked 2026-09-13). Its stat renderer is the published `OnShow` of the
`IBannerPopup` menu:

    TItemBanner           VMT 0x00406950   instsize [VMT-0x1C] 0x78
                          field table [VMT-0x2C] 0x00406978  (13 entries, 210 B, ends at the
                          method table 0x00406A4A -- so it CANNOT grow in place)
    IBannerPopupShow      0x00406AE8 .. 0x00406E5D

    +0x44 ItemNameLbl  +0x48 IBannerPopup  +0x4C AttackIcon  +0x50 DefenseIcon
    +0x54 DamageIcon   +0x58 ResistanceIcon  +0x5C Attack  +0x60 Defense  +0x64 Damage
    +0x68 Resistance   +0x6C DrawBox  +0x70 AbLB  +0x74 AbVSB

The renderer is UNROLLED, not a table: four ~0x7A-byte identical blocks in the order
ATK 0x46 / DAM 0x48 / DEF 0x47 / RES 0x49, each

    cmp byte [item+0xNN],0 / je next
    IntToStr(movsx byte) -> TAOWLabel.SetGText @0x403254
    SetVisible(label,True) ; SetVisible(icon,True)          VMT +0x6C, DL = bool
    SetLeft(icon, esi+0x0A) ; SetLeft(label, esi+0x1E)      VMT +0x58, EDX = int
    SetTop (icon, y)        ; SetTop (label, y+5)           VMT +0x5C, EDX = int
    add esi,0x32 / cmp esi,0x82 / jne next / esi = 0x1E / y += 0x14

esi is the column x (starts 0x1E), [ebp-8] is the row y (starts 0x64), [ebp-4] is the item and
[ebp-0xC] the IntToStr scratch AnsiString (cleared by the function's own finally). The wrap is
`cmp esi,0x82` after `add esi,0x32` from 0x1E, so the grid is 2 columns x N rows and ALREADY
flows to a third row and repositions the ability listbox below it. The layout needed no change to
take two more rows.

================================================================================
WHAT THIS SCRIPT CHANGES  (2 hooks + 2 caves, per exe)
================================================================================
1. NEW RWX SECTION `.ibnr` at VA 0x00630000, 0x3000 B, appended after `.pyar`.
   SizeOfImage 0x230000 -> 0x233000.

   /!\ THIS TAKES THE LAST FREE SECTION-HEADER SLOT IN THE EXE. The section table starts at file
   0x1F8 and SizeOfHeaders is 0x400, so 13 headers end at exactly 0x400 with zero slack. After
   this patch AoWz.exe has NO room for a 14th section: a future feature needing exe cave space
   must squat in `.ibnr`'s or `.hcol`'s zero tail (or `--undo` here, which REMOVES the section
   and gives the slot back). `add_section()` asserts this rather than silently corrupting the
   first section's raw data.

2. THE DFM GROWS BY FOUR COMPONENTS, byte-cloned out of `TUNITBANNER` -- the same banner, already
   built with six pairs (VMT 0x00403D84, BannerPopupShow @0x00403F60). Measured spans:

       HitsIcon   565 B   MovesIcon  566 B   Hits  461 B   Moves  462 B   = 2054 B

   TITEMBANNER is 0x1CF3 B at file 0x000FD6B8 and walks clean with no padding; the grown form is
   ~0x2500 B and is relocated into `.ibnr` with the resource directory entry repointed. The
   original bytes stay untouched in `.rsrc`, which is what makes `--undo` a pure repoint.

   Edits applied to each clone (everything else is copied verbatim, so the new nodes carry the
   donor's ImageLib / CurrentImage / WinWidth and cannot drift from the unit banner):
     * `AOWWindow` 'BannerPopup' -> 'IBannerPopup'   (the only cross-form reference in the nodes;
       it is a LOCAL reference resolved by TReader.FixupReferences after the whole root is read,
       so the insertion point does not have to follow the menu)
     * `Masked` on the two labels True -> False, matching the item banner's OWN four labels
       (the unit banner's are True; its four item-banner siblings are all False)
     * WinLeft / WinTop / Alignment.TopOffset / Left / Top -> row-2 design coordinates
   NO class-table change: `TAOWImage` is already class index 2 and `TAOWLabel` index 0 in
   TItemBanner's table, and `ImageLib` is a name reference the reader resolves as a global fixup
   exactly as `IntGfxMod.UnitIcons` is today.

   The icons need NO ILB edit -- both already exist (verified against the live libraries):
       Hits   Int\Icons.ILB    'IntGfxMod.UnitIcons'  index 4    (ids 0..6)
       Moves  Int\IconMove.ILB 'IntGfxMod.MoveIcons'  index 16   (ids 0..19, all 32x17)
   /!\ `Int\Icons.ILB` index 5 is MANA, not movement. The movement glyph is 32 px wide and lives
   in a different library.

3. FIELD TABLE 13 -> 17 entries, relocated into `.ibnr` (the original is wedged against the
   method table). [VMT-0x2C] repointed; [VMT-0x1C] 0x78 -> 0x88.

       +0x78 HitsIcon   +0x7C MovesIcon   +0x80 Hits   +0x84 Moves

   Delphi's InitInstance zero-fills InstanceSize bytes, so the four new fields start nil and no
   `Create` override is needed -- the same precedent as build_arena.py (TArena) and
   build_herodlg_columns.py (THeroUpgradeDlg 480 -> 576). Class indices are taken from the
   existing `AttackIcon` / `Attack` rows rather than hard-coded.

4. cave_hpmv -- FOUR SetVisible(False) calls, then two more copies of the stat block:
       HITS   item+0x4A -> icon +0x78, label +0x80, icon at esi+0x0A
       MOVES  item+0x4B -> icon +0x7C, label +0x84, icon at esi+0x03

   /!\ THE HIDE IS NOT OPTIONAL, AND LEAVING IT OUT IS INVISIBLE TO EVERY STATIC CHECK.
   Caught by QA 2026-09-13 on the first build of this script, which showed the controls and never
   hid them. `AoWComp.TAoWComponent.Create @0x59802318` does `mov byte [esi+0x75],1`, so every
   component is CONSTRUCTED VISIBLE, and none of the popup's children carries a `Visible` property
   in the DFM (only `IBannerPopup` itself does). `AoWComp.TAoWComponent.SetVisible @0x59803004`
   writes only `[self+0x75]` and walks no child list, so hiding the popup does not reset its
   children either. That is exactly why vanilla opens with the eight-call reset sweep at
   0x00406B39..0x00406B88 -- the item bonuses are OPTIONAL. (`TUnitBanner.BannerPopupShow` has no
   such sweep at all, because a unit always has all six stats. Do not read the absence there as
   permission to skip it here.) Without the hide: on a fresh launch the first popup for ANY item
   draws both icons at their DFM positions with blank labels, on top of the stat rows; and after
   one bonus item the icon and its stale number persist on every later item that lacks the bonus.

   /!\ WHY THERE IS NO THIRD HOOK ON THE SWEEP ITSELF. The hide sits at the head of this cave
   rather than in an E9 over 0x00406B89, because the two are provably equivalent here and one hook
   is cheaper to verify and to undo. Measured on the live function with capstone:
     * EBX is written ONCE, at 0x00406AF6 (`mov ebx,eax`, Delphi EAX = Self), and never again
       through 0x00406D7D -- so `[ebx+0xNN]` is the same base the sweep itself uses.
     * EVERY branch edge landing in [0x406B89, 0x406D82] originates at >= 0x00406B9C, i.e. after
       the sweep; ZERO edges land inside the sweep; and the only edge from before it is
       `0x00406B25 je 0x00406E3A`, the nil-item exit, which skips the whole body.
   => every path that reaches 0x00406D7D has already run all eight SetVisible(False) calls, so
   running four more at the top of the cave has the same predecessors and the same guarantee.
   Re-run that sweep if this function is ever re-hooked.
   /!\ THE -7. The moves glyph is 32 px wide where the other five are 15, and TUnitBanner's own
   DFM gives the rule: its 15-px icons sit at WinLeft 30 with the label at 50, its 32-px MovesIcon
   at WinLeft 23 with the label still at 50. So the wide icon is drawn at slot-7 and the label
   does not move: 0x0A - 7 = 0x03.

   Reached by a 5-byte E9 over 0x00406D7D..0x00406D81 (`cmp esi,0x1E` + `je 0x406D86`, bytes
   `83 fe 1e 74 04`). The cave runs the two blocks, replays the two displaced instructions and
   jumps to 0x00406D86. The `add dword [ebp-8],0x14` at 0x00406D82 is NOT displaced; it simply
   becomes unreachable, which keeps `--undo` a 5-byte restore with no pristine-exe dependency.

5. cave_clamp -- the popup height clamp follows the extra row. MEASURED, not guessed:
       AbLB is Alignment.AlignHeight = ahBoth with BottomOffset 24, and the renderer writes its
       TopOffset := y + 10 at 0x00406DA3, so the visible ability list is
           popupHeight - (y + 10) - 24
       0x00406E19 sets the popup height to count*ItemHeight + y + 0x32 and 0x00406E24 then clamps
       it DOWN to 0xC8 = 200. With four stats y is 140 and the list gets 200-150-24 = 26 px = two
       12-px rows. A fifth or sixth stat puts y at 160 and the list gets 200-170-24 = **6 px, i.e.
       no rows at all** -- any item carrying an HP or MV bonus AND an ability would have shown an
       empty ability list.
   So the clamp becomes `max(200, y + 60)`, which is 200 for every y <= 140 and therefore
   BIT-IDENTICAL for every item that does not gain a row, and 220 for the 5/6-stat case -- exactly
   the 26 px a four-stat item gets today. Reached by a 5-byte E9 over 0x00406E21..0x00406E25;
   0x00406E26..0x00406E39 is left intact but unreachable (nothing jumps into it; the only inbound
   edges are to 0x00406E3A).

6. Every byte is mirrored into AoWzCompat.exe, and the one-byte-difference invariant
   (file 0x3BB7C only) is asserted after writing.

================================================================================
SAFETY
================================================================================
* PIC is NOT used and NOT wanted. These are exe caves at the fixed base 0x400000, so absolute
  addresses are correct here (same reasoning as build_deved_gamesettings_tab.py). The .dpl
  position-independence rule does not apply.
* .reloc: ZERO fixups in either hook window. Scanned the whole table (11902 entries): the five in
  this function are at 0x406AFC / 0x406B07 / 0x406B15 / 0x406DBD / 0x406E43, all outside
  0x406D7D..0x406D82 and 0x406E21..0x406E26. Nothing is displaced or moved, so no stale-reloc
  risk -- run `build_relocfix.py --audit` anyway.
* /!\ 0x00406DEF IS OWNED BY build_abilityid_ceilings.py (`cmp esi,0xB3`, was 0xAA) and sits
  INSIDE this function, 0x6D bytes past our first hook. Nothing here moves or displaces it;
  `--apply` asserts it still reads `81 fe b3 00 00 00` afterwards and aborts before save if not.
* `.ibnr` at 0x00630000 is claimed by no other script (`grep -rl` over build_scripts/ finds only
  this file). It is past `.pyar` (ends 0x00630000) and nowhere near `.hcol`'s squatters.
* THE RELOCATED FIELD TABLE CARRIES ONE ABSOLUTE WITH NO .reloc ENTRY, deliberately: its header
  word at fieldtable+2 is the class-table VA 0x00406AA0, and the original at 0x0040697A DID have a
  HIGHLOW entry that `.ibnr` does not reproduce. That is precedent, not an oversight --
  `build_herodlg_columns.py` relocates THeroUpgradeDlg's table with the byte-identical shape and is
  CONFIRMED WORKING -- and it is safe because AoWz.exe is RELOCS_STRIPPED=0 / DYNAMIC_BASE=0
  (DllCharacteristics 0x0000), so the image always loads at 0x00400000 and the table is never
  relocated. /!\ `build_relocfix.py` detects only STALE relocations, never a MISSING one, so its
  clean audit says nothing about this either way.
* Item bytes are SIGNED, and the blocks use `cmp byte,0` + `movsx` exactly like the four vanilla
  ones, so a cursed -2 item shows "-2" rather than being hidden.

================================================================================
USAGE
================================================================================
    (no args)   verify the state of both exes -- writes nothing
    --apply     patch both exes (an UNPATCHED exe is first snapshotted to
                backups/<exe>.pre-itembannerhpmv; a patched one is NOT -- a .pre-* of a patched
                file is a lie)
    --undo      surgical: repoint the resource, restore [VMT-0x2C] / [VMT-0x1C], restore both
                5-byte hooks, and REMOVE the .ibnr section (it is the last one, so the header
                slot comes back)
    --dis       disassemble both caves at their real VAs and exit -- writes nothing
                (--show is an alias)

Needs `pip install capstone keystone-engine`.
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import time

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dfm_edit                                        # noqa: E402
import zigexe                                          # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_32       # noqa: E402

EXES = list(zigexe.EXES)                               # AoWz.exe + AoWzCompat.exe
BACKUP_SUFFIX = ".pre-itembannerhpmv"
BACKUP_DIR = os.path.join(GAME, "backups")             # never the game root -- rule 2026-09-03

SECNAME = b".ibnr\0\0\0"
SEC_VA = 0x00630000            # first free VA past .pyar (0x0062F000 + 0x1000)
SEC_SIZE = 0x3000              # DFM ~0x2500 + field table 0x108 + caves ~0x110, rounded up

# ---- the class -------------------------------------------------------------------------------
VMT = 0x00406950
VMT_FIELDTABLE = VMT - 0x2C    # 0x00406924
VMT_INSTSIZE = VMT - 0x1C      # 0x00406934
ORIG_FIELDTABLE = 0x00406978
ORIG_FIELDCOUNT = 13
ORIG_INSTSIZE = 0x78
NEW_INSTSIZE = 0x88            # 0x78 + 4 fields

# new published fields, and the existing field whose class index each one borrows
NEW_FIELDS = [(0x78, "HitsIcon", "AttackIcon"),
              (0x7C, "MovesIcon", "AttackIcon"),
              (0x80, "Hits", "Attack"),
              (0x84, "Moves", "Attack")]
F_HITSICON, F_MOVESICON, F_HITS, F_MOVES = 0x78, 0x7C, 0x80, 0x84

# ---- the resources ---------------------------------------------------------------------------
# File offsets inside .rsrc. TITEMBANNER's directory entry is repointed by --apply, so the
# PRISTINE form can only be found by its fixed position in .rsrc; both are checked by SHA1.
ITEM_DFM_FILEOFF = 0x000FD6B8
ITEM_DFM_SIZE = 0x1CF3
ITEM_DFM_SHA1 = "c8eaef82f1bac2ab2ad248ce101b46c3aa3357a7"
UNIT_DFM_SHA1 = "0a1971172ebb343e42aed99cc2cf9973fe742b24"

# donor components in TUNITBANNER, and the design-time geometry each clone gets in TITEMBANNER.
# (Design geometry is cosmetic -- the renderer calls SetLeft/SetTop on every control it makes
# visible, and never draws a hidden one -- but the item banner's own rows are 59/77 for icons and
# 64/82 for labels, so row 2 is 95/100 and these keep the form consistent if anyone opens it.)
CLONES = [
    # donor        new name     WinLeft WinTop  designer Left/Top   label?
    ("HitsIcon",   "HitsIcon",   30,  95,  32, 168, False),
    ("MovesIcon",  "MovesIcon",  76,  95, 104, 168, False),   # 32 px wide -> 83 - 7
    ("Hits",       "Hits",       50, 100, 200, 168, True),
    ("Moves",      "Moves",     103, 100, 280, 168, True),
]
INSERT_AFTER = "Resistance"    # keep the new pairs in the same band as the four they join

# ---- the hooks -------------------------------------------------------------------------------
H_ROWEND = 0x00406D7D                       # cmp esi,0x1E ; je 0x406D86
ORIG_ROWEND = bytes.fromhex("83fe1e7404")
RESUME_ROWEND = 0x00406D86

H_CLAMP = 0x00406E21                        # mov eax,[ebx+0x48] ; cmp dword [eax+0x80],0xC8 (head)
ORIG_CLAMP = bytes.fromhex("8b434881b880")[:5]
# the full original run, kept as a fingerprint only -- --undo restores just the first 5 bytes
ORIG_CLAMP_FULL = bytes.fromhex("8b434881b880000000c80000007e0abac80000008b08ff5164")
RESUME_CLAMP = 0x00406E3A

# build_abilityid_ceilings.py's site, inside this same function. Never moved, always asserted.
CEILING_VA = 0x00406DEF
CEILING_BYTES = bytes.fromhex("81feb3000000")

# ---- engine entry points the caves call ------------------------------------------------------
INTTOSTR = 0x004013AC                       # VCL30.dpl!SysUtils.IntToStr  (EAX=value, EDX=@result)
SETGTEXT = 0x00403254                       # aowInt.dpl!TAOWLabel.SetGText (EAX=self, EDX=string)
V_SETLEFT, V_SETTOP, V_SETHEIGHT, V_SETVISIBLE = 0x58, 0x5C, 0x64, 0x6C

FLD_POPUP = 0x48                            # TItemBanner.IBannerPopup
CTL_HEIGHT = 0x80                           # TAOWControl height field (SetHeight writes it)
ITEM_HP, ITEM_MV = 0x4A, 0x4B               # build_item_hpmv.py's two signed bytes
CLAMP_FLOOR = 0xC8                          # vanilla's 200 px popup ceiling
CLAMP_BIAS = 0x3C                           # y + 60 == 0xC8 + (y - 0x8C): one row's worth per row


# =================================================================== PE container
class Exe:
    def __init__(self, path):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        self.pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        self.optsize = struct.unpack_from("<H", self.d, self.pe + 20)[0]
        self.opt = self.pe + 24
        self.sectbl = self.opt + self.optsize
        self.base = struct.unpack_from("<I", self.d, self.opt + 28)[0]

    @property
    def nsec(self):
        return struct.unpack_from("<H", self.d, self.pe + 6)[0]

    def sections(self):
        out = []
        for i in range(self.nsec):
            s = self.sectbl + 40 * i
            nm = bytes(self.d[s:s + 8]).rstrip(b"\0").decode("latin1")
            vsz, va = struct.unpack_from("<II", self.d, s + 8)
            rsz, raw = struct.unpack_from("<II", self.d, s + 16)
            out.append((nm, va, vsz, raw, rsz, s))
        return out

    def sec(self, name):
        for n, va, vsz, raw, rsz, s in self.sections():
            if n == name:
                return (va, vsz, raw, rsz, s)
        return None

    def rva2off(self, rva):
        for _n, va, vsz, raw, rsz, _s in self.sections():
            if va <= rva < va + max(vsz, rsz):
                return raw + (rva - va)
        raise ValueError("RVA 0x%X unmapped" % rva)

    def off(self, va):
        return self.rva2off(va - self.base)

    def rd(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def wr(self, va, blob):
        o = self.off(va)
        self.d[o:o + len(blob)] = blob

    def u32(self, va):
        return struct.unpack_from("<I", self.d, self.off(va))[0]

    def w32(self, va, v):
        struct.pack_into("<I", self.d, self.off(va), v)

    # ---- resources
    def _res_entries(self, diroff, rsrc):
        nn = struct.unpack_from("<H", self.d, diroff + 12)[0]
        ni = struct.unpack_from("<H", self.d, diroff + 14)[0]
        out = []
        for i in range(nn + ni):
            e = diroff + 16 + 8 * i
            nm, val = struct.unpack_from("<II", self.d, e)
            if nm & 0x80000000:
                no = self.rva2off(rsrc + (nm & 0x7FFFFFFF))
                ln = struct.unpack_from("<H", self.d, no)[0]
                nm = self.d[no + 2:no + 2 + 2 * ln].decode("utf-16le")
            else:
                nm = "#%d" % nm
            out.append((nm, val))
        return out

    def dfm_entry(self, name):
        """-> (file offset of the RCDATA data entry, dfm rva, dfm size)"""
        rsrc = struct.unpack_from("<I", self.d, self.opt + 112)[0]
        rc = next(v for n, v in self._res_entries(self.rva2off(rsrc), rsrc) if n == "#10")
        ent = next(v for n, v in self._res_entries(self.rva2off(rsrc + (rc & 0x7FFFFFFF)), rsrc)
                   if n == name)
        lang = self._res_entries(self.rva2off(rsrc + (ent & 0x7FFFFFFF)), rsrc)[0][1]
        de = self.rva2off(rsrc + (lang & 0x7FFFFFFF))
        rva, size = struct.unpack_from("<II", self.d, de)
        return de, rva, size

    def orig_item_dfm_rva(self):
        """RVA of the PRISTINE TITEMBANNER bytes, which never leave .rsrc."""
        va, _vsz, raw, _rsz, _s = self.sec(".rsrc")
        return va + (ITEM_DFM_FILEOFF - raw)

    def pristine_item_dfm(self):
        blob = bytes(self.d[ITEM_DFM_FILEOFF:ITEM_DFM_FILEOFF + ITEM_DFM_SIZE])
        got = hashlib.sha1(blob).hexdigest()
        assert got == ITEM_DFM_SHA1, (
            "the TITEMBANNER bytes at file 0x%X are not the expected pristine form "
            "(sha1 %s, want %s) -- refusing to build a DFM from an unknown source"
            % (ITEM_DFM_FILEOFF, got, ITEM_DFM_SHA1))
        return blob

    def unit_dfm(self):
        _de, rva, size = self.dfm_entry("TUNITBANNER")
        blob = self.rd(self.base + rva, size)
        got = hashlib.sha1(blob).hexdigest()
        assert got == UNIT_DFM_SHA1, (
            "TUNITBANNER is not the expected donor form (sha1 %s, want %s)" % (got, UNIT_DFM_SHA1))
        return blob

    # ---- sections
    def add_section(self, name, va, size):
        want = name.rstrip(b"\0").decode("latin1")
        if self.sec(want):
            return False
        hdr_end = self.sectbl + 40 * (self.nsec + 1)
        sizeofheaders = struct.unpack_from("<I", self.d, self.opt + 60)[0]
        assert hdr_end <= sizeofheaders, (
            "no spare section-header slot: %d headers would end at 0x%X, past SizeOfHeaders 0x%X"
            % (self.nsec + 1, hdr_end, sizeofheaders))
        filealign = struct.unpack_from("<I", self.d, self.opt + 36)[0]
        raw = len(self.d)
        assert raw % filealign == 0, "EOF 0x%X not file-aligned" % raw
        assert size % filealign == 0, "section size 0x%X not file-aligned" % size
        s = self.sectbl + 40 * self.nsec
        rva = va - self.base
        struct.pack_into("<8sIIII", self.d, s, name, size, rva, size, raw)
        struct.pack_into("<IIHHI", self.d, s + 24, 0, 0, 0, 0, 0xE0000060)   # RWX, initialised
        self.d += bytearray(size)
        struct.pack_into("<H", self.d, self.pe + 6, self.nsec + 1)
        self._fix_sizeofimage()
        return True

    def drop_section(self, name):
        """Remove a section that is LAST in both the header table and the file. -> bool."""
        want = name.rstrip(b"\0").decode("latin1")
        hit = self.sec(want)
        if not hit:
            return False
        va, vsz, raw, rsz, s = hit
        idx = (s - self.sectbl) // 40
        if idx != self.nsec - 1 or raw + rsz != len(self.d):
            print("    !! %s is no longer the last section -- zeroing it instead of removing it"
                  % want)
            self.d[raw:raw + rsz] = b"\0" * rsz
            return False
        self.d[s:s + 40] = b"\0" * 40
        struct.pack_into("<H", self.d, self.pe + 6, self.nsec - 1)
        del self.d[raw:]
        self._fix_sizeofimage()
        return True

    def _fix_sizeofimage(self):
        secalign = struct.unpack_from("<I", self.d, self.opt + 32)[0]
        top = 0
        for _n, va, vsz, _raw, rsz, _s in self.sections():
            top = max(top, va + max(vsz, rsz))
        top = (top + secalign - 1) // secalign * secalign
        struct.pack_into("<I", self.d, self.opt + 56, top)


# =================================================================== DFM surgery
def enc_int(prop, val):
    """Property bytes: shortstring name + smallest Delphi integer encoding (matches TWriter)."""
    if -128 <= val <= 127:
        return dfm_edit.shortstr(prop) + bytes([dfm_edit.I8]) + struct.pack("<b", val)
    if -32768 <= val <= 32767:
        return dfm_edit.shortstr(prop) + bytes([dfm_edit.I16]) + struct.pack("<h", val)
    return dfm_edit.shortstr(prop) + bytes([dfm_edit.I32]) + struct.pack("<i", val)


def enc_ident(prop, val):
    return dfm_edit.shortstr(prop) + bytes([dfm_edit.IDENT]) + dfm_edit.shortstr(val)


def enc_bool(prop, val):
    return dfm_edit.shortstr(prop) + bytes([dfm_edit.TRUE if val else dfm_edit.FALSE])


def comp_spans(w):
    starts = [(p[0].split("/")[-1], p[3]) for p in w.props if p[1] == "$class"]
    out = {}
    for i, (nm, s) in enumerate(starts):
        out[nm] = (s, starts[i + 1][1] if i + 1 < len(starts) else w.consumed - 1)
    return out


def comp_props(w):
    out = {}
    for path, nm, t, s, e, v in w.props:
        out.setdefault(path.split("/")[-1], {})[nm] = (s, e, t, v)
    return out


def obj_name_pos(blob):
    p = 1 if (blob[0] & 0xF0) == 0xF0 else 0
    assert p == 0 or not (blob[0] & 0x02), "ffChildPos component not handled"
    p2 = p + 1 + blob[p]                       # skip the class-name shortstring
    return p2, blob[p2 + 1:p2 + 1 + blob[p2]].decode("latin1")


def clone(dfm, span, props, newname, edits):
    """Copy a component out of `dfm`, rename it, replace/append properties. -> bytes."""
    s, e = span
    blob = bytearray(dfm[s:e])
    npos, oldnm = obj_name_pos(blob)
    blob[npos:npos + 1 + len(oldnm)] = dfm_edit.shortstr(newname)
    delta = len(newname) - len(oldnm)
    reps, appends = [], b""
    for pname, nb in edits.items():
        if pname in props:
            ps, pe, _t, _v = props[pname]
            reps.append((ps - s + delta, pe - s + delta, nb))
        else:
            appends += nb
    out, pos = bytearray(), 0
    for ps, pe, nb in sorted(reps):
        assert pos <= ps, "overlapping clone edits on %s" % newname
        out += blob[pos:ps] + nb
        pos = pe
    out += blob[pos:]
    if appends:
        assert out[-2:] == b"\0\0", "unexpected component tail on %s" % newname
        out = out[:-2] + appends + out[-2:]
    return bytes(out)


def build_dfm(item_dfm, unit_dfm):
    """pristine TITEMBANNER + TUNITBANNER -> the six-pair TITEMBANNER (grown)."""
    iw = dfm_edit.walk(item_dfm)
    uw = dfm_edit.walk(unit_dfm)
    ispans, iprops = comp_spans(iw), comp_props(iw)
    uspans, uprops = comp_spans(uw), comp_props(uw)

    for donor, _new, _l, _t, _dl, _dt, _lab in CLONES:
        assert donor in uspans, "TUNITBANNER has no %s to clone" % donor
        assert uprops[donor]["AOWWindow"][3] == "BannerPopup", \
            "%s does not hang off BannerPopup -- the donor form changed" % donor
    for _d, new, *_ in CLONES:
        assert new not in ispans, "TITEMBANNER already has a %s component" % new

    blobs = []
    for donor, new, wl, wt, dl, dt, is_label in CLONES:
        edits = {
            "AOWWindow": enc_ident("AOWWindow", "IBannerPopup"),
            "WinLeft": enc_int("WinLeft", wl),
            "WinTop": enc_int("WinTop", wt),
            "Alignment.TopOffset": enc_int("Alignment.TopOffset", wt),
            "Left": enc_int("Left", dl),
            "Top": enc_int("Top", dt),
        }
        if is_label:
            edits["Masked"] = enc_bool("Masked", False)      # match the item banner's own labels
        blobs.append(clone(unit_dfm, uspans[donor], uprops[donor], new, edits))

    at = ispans[INSERT_AFTER][1]
    out = item_dfm[:at] + b"".join(blobs) + item_dfm[at:]

    # a grown DFM that does not walk clean is a corrupt form the reader will desync on
    w = dfm_edit.walk(out)
    assert w.consumed == len(out), \
        "grown TITEMBANNER desyncs: %d parsed of %d" % (w.consumed, len(out))
    got = comp_spans(w)
    for _d, new, *_ in CLONES:
        assert new in got, "%s missing from the grown form" % new
    gp = comp_props(w)
    for _d, new, wl, wt, _dl, _dt, _lab in CLONES:
        assert gp[new]["AOWWindow"][3] == "IBannerPopup", "%s still points at BannerPopup" % new
        assert gp[new]["WinLeft"][3] == wl and gp[new]["WinTop"][3] == wt
    assert gp["HitsIcon"]["ImageLib"][3] == "IntGfxMod.UnitIcons"
    assert gp["HitsIcon"]["CurrentImage"][3] == 4
    assert gp["MovesIcon"]["ImageLib"][3] == "IntGfxMod.MoveIcons"
    assert gp["MovesIcon"]["CurrentImage"][3] == 16
    assert gp["MovesIcon"]["WinWidth"][3] == 32, "the moves glyph must stay 32 px wide"
    return out


# =================================================================== field table
def build_field_table(exe):
    """-> the 17-entry published field table, ready to drop in .ibnr."""
    ft = ORIG_FIELDTABLE
    cnt = struct.unpack_from("<H", exe.d, exe.off(ft))[0]
    classtab = struct.unpack_from("<I", exe.d, exe.off(ft + 2))[0]
    assert cnt == ORIG_FIELDCOUNT, "field table already altered (count %d)" % cnt
    p, donor = ft + 6, {}
    for _ in range(cnt):
        off_ = struct.unpack_from("<I", exe.d, exe.off(p))[0]
        cls = struct.unpack_from("<H", exe.d, exe.off(p + 4))[0]
        ln = exe.d[exe.off(p + 6)]
        nm = bytes(exe.d[exe.off(p + 7):exe.off(p + 7) + ln]).decode("latin1")
        donor[nm] = (off_, cls)
        p += 7 + ln
    assert p == 0x00406A4A, "field table ends at 0x%X, not at the method table" % p
    orig = exe.rd(ft, p - ft)
    new = b""
    for off_, nm, src in NEW_FIELDS:
        assert off_ >= ORIG_INSTSIZE and off_ + 4 <= NEW_INSTSIZE, \
            "field %s at +0x%X falls outside the grown instance" % (nm, off_)
        new += struct.pack("<IH", off_, donor[src][1]) + dfm_edit.shortstr(nm)
    return struct.pack("<HI", cnt + len(NEW_FIELDS), classtab) + orig[6:] + new


# =================================================================== caves
def hide_block():
    """SetVisible(False) on the four new controls -- the twelfth..ninth calls vanilla's own reset
    sweep would make if it knew about them. Shape copied verbatim from 0x00406B39: EDX = 0,
    EAX = the control, ECX = its VMT, call VMT+0x6C."""
    return "".join(f"""
    xor edx, edx
    mov eax, [ebx + {f}]
    mov ecx, [eax]
    call [ecx + {V_SETVISIBLE}]
""" for f in (F_HITSICON, F_MOVESICON, F_HITS, F_MOVES))


def stat_block(item_off, icon_fld, label_fld, icon_dx, tag):
    """One copy of the vanilla ~0x7A-byte icon+value block, verbatim but re-targeted."""
    return f"""
    mov eax, [ebp - 4]
    cmp byte ptr [eax + {item_off}], 0
    je {tag}_end
    lea edx, [ebp - 0x0c]
    mov eax, [ebp - 4]
    movsx eax, byte ptr [eax + {item_off}]
    call {INTTOSTR}
    mov edx, [ebp - 0x0c]
    mov eax, [ebx + {label_fld}]
    call {SETGTEXT}
    mov dl, 1
    mov eax, [ebx + {label_fld}]
    mov ecx, [eax]
    call [ecx + {V_SETVISIBLE}]
    mov dl, 1
    mov eax, [ebx + {icon_fld}]
    mov ecx, [eax]
    call [ecx + {V_SETVISIBLE}]
    lea edx, [esi + {icon_dx}]
    mov eax, [ebx + {icon_fld}]
    mov ecx, [eax]
    call [ecx + {V_SETLEFT}]
    lea edx, [esi + 0x1e]
    mov eax, [ebx + {label_fld}]
    mov ecx, [eax]
    call [ecx + {V_SETLEFT}]
    mov edx, [ebp - 8]
    mov eax, [ebx + {icon_fld}]
    mov ecx, [eax]
    call [ecx + {V_SETTOP}]
    mov edx, [ebp - 8]
    add edx, 5
    mov eax, [ebx + {label_fld}]
    mov ecx, [eax]
    call [ecx + {V_SETTOP}]
    add esi, 0x32
    cmp esi, 0x82
    jne {tag}_end
    mov esi, 0x1e
    add dword ptr [ebp - 8], 0x14
{tag}_end:
"""


def cave_sources():
    """-> ordered [(name, asm source)]. Neither cave calls the other, so one pass is exact."""
    return [
        # ebx = TItemBanner, esi = column x, [ebp-4] = item, [ebp-8] = row y,
        # [ebp-0x0c] = the IntToStr scratch string (freed by the host function's finally).
        # eax/ecx/edx/edi are dead here; ebp and ebx must survive, and esi/[ebp-8] are the
        # grid cursor the tail and the ability listbox both read.
        ("cave_hpmv",
         hide_block()
         + stat_block(ITEM_HP, F_HITSICON, F_HITS, "0x0a", "hp")
         + stat_block(ITEM_MV, F_MOVESICON, F_MOVES, "0x03", "mv")
         + f"""
    cmp esi, 0x1e
    je resume
    add dword ptr [ebp - 8], 0x14
resume:
    jmp {RESUME_ROWEND}
"""),
        # The popup height clamp. edx = max(0xC8, y + 0x3C); identical to vanilla for every
        # y <= 0x8C, i.e. for every item that does not gain a third stat row.
        ("cave_clamp", f"""
    mov edx, [ebp - 8]
    add edx, {CLAMP_BIAS}
    cmp edx, {CLAMP_FLOOR}
    jge cc_have
    mov edx, {CLAMP_FLOOR}
cc_have:
    mov eax, [ebx + {FLD_POPUP}]
    cmp dword ptr [eax + {CTL_HEIGHT}], edx
    jle cc_done
    mov ecx, [eax]
    call [ecx + {V_SETHEIGHT}]
cc_done:
    jmp {RESUME_CLAMP}
"""),
    ]


def assemble(code_va):
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    va, blob, labels = code_va, b"", {}
    for name, src in cave_sources():
        labels[name] = va
        code = bytes(ks.asm(src, va)[0])
        code += b"\xCC" * ((-len(code)) % 4)
        blob += code
        va += len(code)
    return blob, labels


def show_caves(exe):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    D, dfm = plan(exe)
    code, labels = assemble(D["code"])
    order = sorted(labels.items(), key=lambda kv: kv[1])
    print("%s: DFM %d -> %d B at 0x%08X, field table 0x%08X, caves 0x%08X..0x%08X (%d B)\n"
          % (os.path.basename(exe.path), ITEM_DFM_SIZE, len(dfm), D["dfm"], D["fieldtable"],
             D["code"], D["code"] + len(code), len(code)))
    for i, (name, va) in enumerate(order):
        end = order[i + 1][1] if i + 1 < len(order) else D["code"] + len(code)
        print("--- %s @ %08X (%d B) ---" % (name, va, end - va))
        for ins in cs.disasm(code[va - D["code"]:end - D["code"]], va):
            print("  %08X  %-20s %s %s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
        print()


# =================================================================== layout of .ibnr
def plan(exe):
    dfm = build_dfm(exe.pristine_item_dfm(), exe.unit_dfm())
    va = SEC_VA
    D = {"dfm": va}
    va += (len(dfm) + 0xF) & ~0xF
    D["fieldtable"] = va
    va += 0x200                              # 17 entries = 264 B -- sized generously
    va = (va + 0xF) & ~0xF
    D["code"] = va
    return D, dfm


# =================================================================== state / apply
def _jmp_into_section(blob, frm):
    return blob[0] == 0xE9 and \
        SEC_VA <= frm + 5 + struct.unpack_from("<i", blob, 1)[0] < SEC_VA + SEC_SIZE


def state_of(exe):
    ft = exe.u32(VMT_FIELDTABLE)
    inst = exe.u32(VMT_INSTSIZE)
    _de, rva, size = exe.dfm_entry("TITEMBANNER")
    dfm_va = rva + exe.base
    rowend = exe.rd(H_ROWEND, 5)
    clamp = exe.rd(H_CLAMP, 5)
    if (ft == ORIG_FIELDTABLE and inst == ORIG_INSTSIZE and dfm_va < SEC_VA
            and rowend == ORIG_ROWEND and clamp == ORIG_CLAMP):
        return "off", size
    if (SEC_VA <= ft < SEC_VA + SEC_SIZE and inst == NEW_INSTSIZE
            and SEC_VA <= dfm_va < SEC_VA + SEC_SIZE
            and _jmp_into_section(rowend, H_ROWEND) and _jmp_into_section(clamp, H_CLAMP)):
        return "on", size
    return "unknown", size


def kill_game():
    for p in (n + ".exe" for n in zigexe.LOCKING_PROCESSES):
        subprocess.run(["taskkill", "/F", "/IM", p],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def save(exe):
    try:
        f = open(exe.path, "wb")
    except PermissionError:
        print("    locked -> killing AoW processes and retrying")
        kill_game()
        time.sleep(1.0)
        f = open(exe.path, "wb")
    with f:
        f.write(exe.d)


def hook(exe, va, orig, blob):
    got = exe.rd(va, len(orig))
    assert got == orig or _jmp_into_section(got, va), \
        "byte mismatch at 0x%X: have %s, expected vanilla %s or our own E9" \
        % (va, got.hex(), orig.hex())
    exe.wr(va, blob)


def jmp(frm, to):
    return b"\xE9" + struct.pack("<i", to - (frm + 5))


def apply_to(exe, verbose=True):
    st, _size = state_of(exe)
    if st == "on":
        undo(exe, drop=False, verbose=False)          # rebuild in place; keeps the section
    D, dfm = plan(exe)
    ft_blob = build_field_table(exe)
    code, labels = assemble(D["code"])
    assert D["fieldtable"] + len(ft_blob) <= D["code"], "field table overruns its slot"
    assert D["code"] + len(code) <= SEC_VA + SEC_SIZE, \
        "blob reaches 0x%X, past the end of .ibnr 0x%X" % (D["code"] + len(code), SEC_VA + SEC_SIZE)

    fresh = exe.add_section(SECNAME, SEC_VA, SEC_SIZE)
    # Zero the WHOLE section before writing: --apply must never leave the tail of a previous,
    # longer blob live above the new one.
    exe.wr(SEC_VA, b"\0" * SEC_SIZE)
    exe.wr(D["dfm"], dfm)
    exe.wr(D["fieldtable"], ft_blob)
    exe.wr(D["code"], code)

    de, _rva, _size = exe.dfm_entry("TITEMBANNER")
    struct.pack_into("<II", exe.d, de, D["dfm"] - exe.base, len(dfm))
    exe.w32(VMT_FIELDTABLE, D["fieldtable"])
    exe.w32(VMT_INSTSIZE, NEW_INSTSIZE)

    hook(exe, H_ROWEND, ORIG_ROWEND, jmp(H_ROWEND, labels["cave_hpmv"]))
    hook(exe, H_CLAMP, ORIG_CLAMP, jmp(H_CLAMP, labels["cave_clamp"]))

    # build_abilityid_ceilings.py lives 0x6D bytes past our first hook, inside this function.
    assert exe.rd(CEILING_VA, len(CEILING_BYTES)) == CEILING_BYTES, (
        "build_abilityid_ceilings.py's site at 0x%X no longer reads %s -- aborting before save"
        % (CEILING_VA, CEILING_BYTES.hex()))
    assert exe.rd(H_CLAMP + 5, len(ORIG_CLAMP_FULL) - 5) == ORIG_CLAMP_FULL[5:], \
        "the clamp tail at 0x%X changed -- aborting before save" % (H_CLAMP + 5)

    if verbose:
        print("    section %s, DFM %d -> %d B at 0x%08X, field table %d -> %d entries at 0x%08X,"
              % (".ibnr appended" if fresh else ".ibnr reused", ITEM_DFM_SIZE, len(dfm), D["dfm"],
                 ORIG_FIELDCOUNT, ORIG_FIELDCOUNT + len(NEW_FIELDS), D["fieldtable"]))
        print("    caves 0x%08X..0x%08X (%d B), instsize 0x%X -> 0x%X, SizeOfImage 0x%X"
              % (D["code"], D["code"] + len(code), len(code), ORIG_INSTSIZE, NEW_INSTSIZE,
                 struct.unpack_from("<I", exe.d, exe.opt + 56)[0]))
    return D


def undo(exe, drop=True, verbose=True):
    """Surgical: repoint the resource, restore the VMT pair and both hooks, drop the section."""
    de, _rva, _size = exe.dfm_entry("TITEMBANNER")
    struct.pack_into("<II", exe.d, de, exe.orig_item_dfm_rva(), ITEM_DFM_SIZE)
    exe.w32(VMT_FIELDTABLE, ORIG_FIELDTABLE)
    exe.w32(VMT_INSTSIZE, ORIG_INSTSIZE)
    exe.wr(H_ROWEND, ORIG_ROWEND)
    exe.wr(H_CLAMP, ORIG_CLAMP)
    assert exe.rd(H_ROWEND, 9) == bytes.fromhex("83fe1e74048345f814"), \
        "restored row-end bytes do not match vanilla"
    assert exe.rd(H_CLAMP, len(ORIG_CLAMP_FULL)) == ORIG_CLAMP_FULL, \
        "restored clamp bytes do not match vanilla"
    if drop:
        gone = exe.drop_section(SECNAME)
        if verbose:
            print("    .ibnr %s, SizeOfImage 0x%X"
                  % ("removed (header slot freed)" if gone else "zeroed",
                     struct.unpack_from("<I", exe.d, exe.opt + 56)[0]))


def check_lockstep():
    a = open(os.path.join(GAME, zigexe.GAME_EXE), "rb").read()
    b = open(os.path.join(GAME, zigexe.COMPAT_EXE), "rb").read()
    if len(a) != len(b):
        return "!! SIZE MISMATCH %d vs %d" % (len(a), len(b))
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if diff == [zigexe.COMPAT_BYTE]:
        return "lockstep ok: the pair differs at file 0x%X only" % zigexe.COMPAT_BYTE
    return "!! LOCKSTEP BROKEN: %d differing bytes %s" % (len(diff), [hex(x) for x in diff[:8]])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble both caves at their real VAs and exit")
    args = ap.parse_args()
    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")

    if args.dis:
        show_caves(Exe(os.path.join(GAME, zigexe.GAME_EXE)))
        return

    for name in EXES:
        path = os.path.join(GAME, name)
        exe = Exe(path)
        st, size = state_of(exe)
        if st == "off":
            print("%s: four stat pairs (unpatched); TITEMBANNER %d B in .rsrc" % (name, size))
        elif st == "on":
            print("%s: six stat pairs (Hits + Moves installed); TITEMBANNER %d B in .ibnr"
                  % (name, size))
        else:
            print("%s: UNKNOWN state -- not touching it" % name)
            print("    [VMT-0x2C]=0x%08X [VMT-0x1C]=0x%X rowend=%s clamp=%s"
                  % (exe.u32(VMT_FIELDTABLE), exe.u32(VMT_INSTSIZE),
                     exe.rd(H_ROWEND, 5).hex(), exe.rd(H_CLAMP, 5).hex()))
            continue

        if args.apply:
            # Snapshot ONLY from a file proved unpatched, and only on --apply.
            bk = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
            if st != "off":
                print("    no backup taken (already patched -- a .pre-* of a patched file is a lie)")
                print("    rebuilding in place")
            elif os.path.exists(bk):
                print("    backup already exists: %s" % bk)
            else:
                os.makedirs(BACKUP_DIR, exist_ok=True)
                shutil.copy2(path, bk)
                print("    backup -> %s" % bk)
            apply_to(exe)
            save(exe)
            print("    applied")
        elif args.undo:
            if st == "off":
                print("    already unpatched")
                continue
            undo(exe)
            save(exe)
            print("    restored")

    if args.apply or args.undo:
        print(check_lockstep())
    else:
        print("\ndry run -- use --apply to patch, --undo to revert, --dis to read the caves")


if __name__ == "__main__":
    main()
