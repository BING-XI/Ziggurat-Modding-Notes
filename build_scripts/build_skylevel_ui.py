"""Firmament map level, v3 -- the AoWz.exe / AoWzCompat.exe (UI) half.

A 4th map level is stored at index 3 and DISPLAYED ABOVE Surface, captioned "Firmament".
(The *terrain* on it is still called Sky -- only the level strip's caption is Firmament.)
Nothing about storage changes here; this script only remaps the World Map level strip's
slot<->level correspondence in the four exe sites that assume `slot == level`.

    display order (more than 3 levels):   slot 0 1 2 3  ->  level 3 0 1 2      ("Firmament | Surface | Caverns | Depths")
    display order (3 levels or fewer):    identity                             ("Surface | Caverns | Depths")

The DLL half (level count, generation, serialisation, terrain) lives in
`build_maplevel4.py` and is NOT touched here.  This script writes only to the canonical mod
exes `Ziggurat/AoWz.exe` and `Ziggurat/AoWzCompat.exe` (names from `zigexe.py`).
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

Level count is read live, so a 3-level map keeps exactly three tabs and vanilla behaviour:

    &TheMap  = [0x0045DF7C]            (an import slot holding the address of AoWEPACK's global)
    TheMap   = [[0x0045DF7C]]
    count    = [[TheMap + 0x10] + 0x14]      (+0x10 = TMapContainer, +0x14 = level count)

Inside the caption handler `ebx = [0x0045A1C0]` (&TSWindow) and `esi = [0x0045DF7C]`
(&TheMap) are already loaded by the function prologue at 0x00454D2C, so cave_caps reuses
them exactly as the vanilla block does.

--------------------------------------------------------------------------------------
THE FOUR SITES  (all addresses AoWz.exe, image base 0x400000, byte-verified 2026-09-06;
                 same build as vanilla AoW.exe, so the addresses are unchanged by the rename)
--------------------------------------------------------------------------------------

1. Caption fill -- inside the function at 0x00454D2C (the nearest published export is
   `TGeneral.ManagerDebugMessage @0x004548F4`, which is a different, smaller routine).

   hook 0x00454FED, 11 bytes:
       before  8b 80 14 01 00 00   mov  eax, [eax+0x114]     ; ScannerTab.Strings
               8b 10               mov  edx, [eax]
               ff 52 40            call [edx+0x40]           ; TStrings.Clear
       after   e9 <rel32 cave_caps>  90 90 90 90 90 90
   Cave does Clear, then Add("Firmament") when count > 3, then the three vanilla Adds, then
   `jmp 0x0045508F` (the vanilla `SetIndex(0)` tail, left untouched).

   ⚠ FAILED APPROACH -- do NOT hook at 0x00454FF8.  That is the natural-looking site (the
   start of the first Add block) but a 5-byte E9 there covers 0x00454FFC, which carries a
   type-3 base relocation (the `0x45a0c0` dword of `mov eax,[0x45a0c0]`).  A rebased load
   would apply the fixup on top of the jump.  0x00454FED..0x00454FF7 carries no relocation
   at all -- verified against the .reloc directory, which holds exactly one entry in
   0x00454FE0..0x00455000, at 0x00454FFC.

   The dead vanilla block 0x00454FF8..0x0045508E is left in place so its three relocations (RVA 0x54FFC, 0x55032, 0x55068)
   stay valid.  Verified unreachable: zero external branches into it, zero absolute dwords
   anywhere in the image pointing into it.

2. `TSWindow.ScannerTabChange @0x00451BC8` -- the three-way slot dispatch.
   On entry to the hook eax = TSWindow, edx = slot (from [[TSWindow+0x4C]+0x118]).

   hook 0x00451BDC, 5 bytes:
       before  83 ea 01            sub  edx, 1
               72 07               jb   0x00451BE8
       after   e9 <rel32 cave_tabsel>
   Cave bounds-checks the slot against the live level count, maps slot->level, invalidates
   the scanner cache (`[Scanner+0x17C] = -1`, Scanner = [TSWindow+0x5C]), then calls
   `THSMap.ViewLevel` (VMT +0xB8) with edx = level, and `jmp 0x00451C4C` (the function's
   `ret`).  All three vanilla arms (0x00451BE8/0x00451C08/0x00451C2B) become dead code; they
   are left in place.

   ⚠ THE WHITELIST IS LOAD-BEARING (v1 defect, fixed 2026-09-06).  Vanilla's
   `sub edx,1 / jb / je / dec edx / je / jmp 0x451C4C` is not just a dispatch, it is a
   whitelist: *any* index other than 0/1/2 falls through to the bare `ret`, and the cache
   invalidation lives INSIDE each accepted arm, so a rejected index does nothing whatever.
   v1 of this cave dropped that -- after the optional ORDER[] lookup it called ViewLevel
   unconditionally.  `THSMap.ViewLevel @0x5560C1B0` rejects `edx >= count` but has NO
   negative check, and a `TAOWTabPanel` with nothing selected reports index -1, so with
   count > 3 the `cmp edx,3 / ja` guard sent -1 straight through to the view-level event.
   v2 does `test edx,edx / js Tret` and `cmp edx,ecx / jge Tret` (ecx = count, already
   loaded for the `>3` test) before anything else, and moves the invalidation after the
   bounds check so an unreachable slot is a no-op exactly as in vanilla.

3. `TMWindow.MapViewerSceneChanged @0x00450F8C` -- pressed-tab sync.
   0x00451145 `e8 9a 20 fb ff` = `call 0x004031E4` (aowInt `TAOWTabPanel.SetIndex`),
   eax = ScannerTab, edx = viewer level.  Only the rel32 is retargeted to cave_setidx,
   which maps level->slot and tail-jumps to 0x004031E4.  4 bytes changed, nothing displaced.

4. `TMWindow.MapWindowKeyDown @0x004512E4` -- PgUp / PgDn.
   eax = [[0x0045B298]+0x48] (THSMapViewer), edx = [viewer+0x38] (current level).
       0x004514BF  4a  dec edx  -> 90        + call rel32 at 0x004514C1 -> cave_lvlup
       0x004514D5  42  inc edx  -> 90        + call rel32 at 0x004514D7 -> cave_lvldn
   Both call `HSEngine.THSMapViewer.SetSceneL @0x00401E54`.  Each cave converts level->slot,
   steps the SLOT by -1 / +1 clamped to [0, count-1], converts back to a level and tail-jumps
   to SetSceneL with eax (the viewer) untouched.  The clamp also removes vanilla's
   `SetSceneL(-1)` / `SetSceneL(count)` underflow/overflow at the ends of the strip.

--------------------------------------------------------------------------------------
CAVE
--------------------------------------------------------------------------------------
0x0062A000..0x0062A3FF, in section `.hcol` (RVA 0x212000, file 0x20C200, characteristics
0xE0000060 = read/write/execute).  File offset of the cave is 0x00224200.  Verified all
zero before install and inside the section's 0x8E84-byte zero run starting at 0x0062417C.
No other build script references any address in 0x0062xxxx below 0x0062417B.

    0x0062A000  ORDER[4]   slot  -> level   = 3, 0, 1, 2
    0x0062A010  RORDER[4]  level -> slot    = 1, 2, 3, 0
    0x0062A020  Delphi 3 const AnsiString caption: ff ff ff ff (refcount -1),
                <length> 00 00 00, then the NUL-terminated chars at 0x0062A028.
                v3 = "Firmament" (len 9, record 0x20..0x31); v1/v2 = "Sky" (len 3, 0x20..0x2B)
    CODE_BASE   code blocks, packed in order and dword-aligned.  v3's longer caption record
                pushed CODE_BASE from 0x0062A030 to 0x0062A040:

                       v3 (2026-09-06)      v2 (superseded)      v1 (superseded)
        cave_caps      0x0062A040  199 B    0x0062A030  199 B    0x0062A030  199 B
        cave_tabsel    0x0062A108   72 B    0x0062A0F8   72 B    0x0062A0F8   64 B
        cave_setidx    0x0062A150   36 B    0x0062A140   36 B    0x0062A138   36 B
        cave_lvlup     0x0062A174   65 B    0x0062A164   65 B    0x0062A15C   65 B
        cave_lvldn     0x0062A1B8   72 B    0x0062A1A8   72 B    0x0062A1A0   72 B
        end            0x0062A200           0x0062A1F0           0x0062A1E8
        used           512 of 1024 B        496 of 1024 B        488 of 1024 B

    The blocks are assembled sequentially, so a layout shift moves every one of the five
    replacement byte-runs with it (the E9 at 0x00454FED and 0x00451BDC, and the three
    retargeted rel32s at 0x00451145, 0x004514C0 and 0x004514D6).  All five are derived from
    the assembled layout, so an --apply over an installed v1 or v2 rewrites them along with
    the cave.  The script keeps the v1 and v2 layouts only in order to RECOGNISE those
    states (reported as "needs re-tune", never as "patched") and to accept them for
    verify-before-write.  Re-tuning is an in-place cave rewrite; no backup is touched and
    there is no revert-and-reapply step.

Refcount -1 makes the literal a Delphi constant string: `TStrings.Add` assigns it through
_LStrAsg, which skips the increment for a negative refcount, and _LStrClr skips the
decrement, so it is never written and never freed.  Same idiom as build_vision9.py.
There is no translated resource id for the 4th level (the exe's STRINGTABLE block
65524/65525/65526 is full), hence an English cave literal.

Exe caves may use absolute addresses -- the exe has the fixed base 0x400000.
The cave contains no resolved filesystem path and no username.

RNG: this feature makes no random draw of any kind.

--------------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------------
    python build_skylevel_ui.py            dry run: verify the current state of both exes
    python build_skylevel_ui.py --apply    patch both exes (backup to <game>\\backups\\)
    python build_skylevel_ui.py --undo     surgical restore: the 11 displaced bytes, the
                                           5 displaced bytes, 4a / 42, the three rel32s,
                                           and zero the 0x400-byte cave.  Touches no backup.
    python build_skylevel_ui.py --dis      capstone-disassemble every cave block

AoWz.exe and AoWzCompat.exe get byte-identical writes; the script asserts afterwards that the
two files still differ in exactly one byte, at file offset 0x0003BB7C.
"""

import os, sys, struct, shutil

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))

from pescan import PE
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import zigexe                                      # mod binary names

TARGETS = [os.path.join(GAME, n) for n in zigexe.EXES]   # AoWz.exe + AoWzCompat.exe
COMPAT_DIFF_OFF = zigexe.COMPAT_BYTE  # the single byte that makes AoWzCompat AoWzCompat

BACKUP_DIR = os.path.join(GAME, "backups")


def require(cond, msg):
    if not cond:
        sys.exit("ABORT: " + msg)


# ---------------------------------------------------------------- engine addresses
MAPSLOT   = 0x0045DF7C     # holds &TheMap (AoWEPACK global, reached via an import slot)
RS_SURF   = 0x0045A0C0     # PResStringRec slots for Surface / Caverns / Depths
RS_CAV    = 0x0045A288
RS_DEP    = 0x0045A3F8
LOADRES   = 0x00401180     # VCL30  System.LoadResString   (eax = PResStringRec, edx = @result)
TRANSL    = 0x004021E4     # AoWEPACK AoWE.TranslateRStr   (eax = source, edx = @result)
SETIDX    = 0x004031E4     # aowInt  TAOWTabPanel.SetIndex (eax = self, edx = index)
SETSCENEL = 0x00401E54     # HSEPack THSMapViewer.SetSceneL(eax = self, edx = level)

RET_CAPS  = 0x0045508F     # resume: the vanilla SetIndex(0) tail
RET_TAB   = 0x00451C4C     # resume: ScannerTabChange's ret

# ---------------------------------------------------------------- hook sites
H_CAPS    = 0x00454FED
H_CAPS_N  = 11
ORIG_CAPS = bytes.fromhex("8b8014010000" "8b10" "ff5240")

H_TAB     = 0x00451BDC
H_TAB_N   = 5
ORIG_TAB  = bytes.fromhex("83ea01" "7207")

C_SETIDX  = 0x00451145     # call rel32 -> SETIDX
C_UP_B    = 0x004514BF     # `dec edx` byte
C_UP_C    = 0x004514C0     # call rel32 -> SETSCENEL
C_DN_B    = 0x004514D5     # `inc edx` byte
C_DN_C    = 0x004514D6     # call rel32 -> SETSCENEL

# ---------------------------------------------------------------- cave layout
CAVE       = 0x0062A000
CAVE_BLOCK = 0x400
ORDER      = CAVE + 0x00           # slot  -> level
RORDER     = CAVE + 0x10           # level -> slot
CAP_REC    = CAVE + 0x20           # AnsiString header
CAP_PTR    = CAP_REC + 8           # the char data -- this is the Delphi string pointer

CAPTION      = b"Firmament"        # v3
CAPTION_OLD  = b"Sky"              # v1 / v2
CODE_BASE    = CAVE + 0x40         # v3   (the 18-byte caption record ends at 0x0062A031)
CODE_BASE_12 = CAVE + 0x30         # v1 / v2

ORDER_VALS  = (3, 0, 1, 2)
RORDER_VALS = (1, 2, 3, 0)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def rel32(src_end, dst):
    return struct.pack("<i", dst - src_end)


def call_rel(at, dst):
    """Bytes of `call dst` placed at `at`."""
    return b"\xE8" + rel32(at + 5, dst)


def jmp_rel(at, dst):
    return b"\xE9" + rel32(at + 5, dst)


# ---------------------------------------------------------------- cave source
def _tab_read_count(reg):
    """Assembly that leaves the level count in `reg`."""
    return f"""
        mov  {reg}, dword ptr [{MAPSLOT:#x}]
        mov  {reg}, dword ptr [{reg}]
        mov  {reg}, dword ptr [{reg}+0x10]
        mov  {reg}, dword ptr [{reg}+0x14]
    """


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


def src_caps(cap_ptr):
    return f"""
        /* entry: eax = ScannerTab, ebx = &TSWindow, esi = &TheMap, ebp = caller frame */
        mov  eax, dword ptr [eax+0x114]
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0x40]            /* TStrings.Clear */

        mov  eax, dword ptr [esi]
        mov  eax, dword ptr [eax+0x10]
        cmp  dword ptr [eax+0x14], 3
        jle  Lsurface
        mov  edx, {cap_ptr:#x}               /* the const AnsiString caption */
        mov  eax, dword ptr [ebx]
        mov  eax, dword ptr [eax+0x4c]
        mov  eax, dword ptr [eax+0x114]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0x34]            /* TStrings.Add */
Lsurface:
        {_add_resource(RS_SURF)}

        mov  eax, dword ptr [esi]
        mov  eax, dword ptr [eax+0x10]
        cmp  dword ptr [eax+0x14], 1
        jle  Ldone
        {_add_resource(RS_CAV)}

        mov  eax, dword ptr [esi]
        mov  eax, dword ptr [eax+0x10]
        cmp  dword ptr [eax+0x14], 2
        jle  Ldone
        {_add_resource(RS_DEP)}
Ldone:
        jmp  {RET_CAPS:#x}
"""

SRC_TABSEL = f"""
        /* entry: eax = TSWindow, edx = slot */
        {_tab_read_count('ecx')}
        test edx, edx
        js   Tret                                       /* vanilla's whitelist: an index   */
        cmp  edx, ecx                                   /* outside [0,count) does NOTHING, */
        jge  Tret                                       /* not even a cache invalidation.  */
        cmp  ecx, 3
        jle  Tgo
        cmp  edx, 3
        ja   Tgo
        mov  edx, dword ptr [edx*4 + {ORDER:#x}]
Tgo:
        mov  ecx, dword ptr [eax+0x5c]                  /* TScanner */
        mov  dword ptr [ecx+0x17c], 0xffffffff          /* invalidate the surface cache */
        mov  eax, dword ptr [{MAPSLOT:#x}]
        mov  eax, dword ptr [eax]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0xb8]                       /* THSMap.ViewLevel(edx) */
Tret:
        jmp  {RET_TAB:#x}
"""

# v1, superseded 2026-09-06 -- no slot whitelist, so a tab index of -1 reached ViewLevel.
# Kept ONLY so the script can identify an installed v1 cave and re-tune it in place.
SRC_TABSEL_V1 = f"""
        mov  ecx, dword ptr [eax+0x5c]
        mov  dword ptr [ecx+0x17c], 0xffffffff
        {_tab_read_count('ecx')}
        cmp  ecx, 3
        jle  Tgo
        cmp  edx, 3
        ja   Tgo
        mov  edx, dword ptr [edx*4 + {ORDER:#x}]
Tgo:
        mov  eax, dword ptr [{MAPSLOT:#x}]
        mov  eax, dword ptr [eax]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0xb8]
        jmp  {RET_TAB:#x}
"""

SRC_SETIDX = f"""
        /* entry: eax = ScannerTab, edx = level; ecx is scratch */
        {_tab_read_count('ecx')}
        cmp  ecx, 3
        jle  Sout
        cmp  edx, 3
        ja   Sout
        mov  edx, dword ptr [edx*4 + {RORDER:#x}]
Sout:
        jmp  {SETIDX:#x}
"""


def _src_step(name, up):
    """PgUp / PgDn: level -> slot, step the slot, clamp, slot -> level."""
    step = f"""
        cmp  edx, 0
        jg   {name}dec
        xor  edx, edx
        jmp  {name}clamped
{name}dec:
        dec  edx
{name}clamped:
    """ if up else f"""
        inc  edx
        lea  eax, [ecx-1]                               /* count-1 (eax is saved) */
        cmp  edx, eax
        jle  {name}hi
        mov  edx, eax
{name}hi:
        cmp  edx, 0
        jge  {name}clamped
        xor  edx, edx
{name}clamped:
    """
    return f"""
        /* entry: eax = THSMapViewer, edx = current level */
        push eax
        {_tab_read_count('ecx')}
        cmp  ecx, 3
        jle  {name}slot
        cmp  edx, 3
        ja   {name}slot
        mov  edx, dword ptr [edx*4 + {RORDER:#x}]       /* level -> slot */
{name}slot:
        {step}
        cmp  ecx, 3
        jle  {name}out
        cmp  edx, 3
        ja   {name}out
        mov  edx, dword ptr [edx*4 + {ORDER:#x}]        /* slot -> level */
{name}out:
        pop  eax
        jmp  {SETSCENEL:#x}
"""


SRC_LVLUP = _src_step("U", True)
SRC_LVLDN = _src_step("D", False)

def _blocks(tabsel_src, cap_ptr):
    return [("cave_caps",   src_caps(cap_ptr)),
            ("cave_tabsel", tabsel_src),
            ("cave_setidx", SRC_SETIDX),
            ("cave_lvlup",  SRC_LVLUP),
            ("cave_lvldn",  SRC_LVLDN)]


BLOCK_NAMES = ["cave_caps", "cave_tabsel", "cave_setidx", "cave_lvlup", "cave_lvldn"]


# ---------------------------------------------------------------- assemble
def build_cave(tabsel_src, caption, code_base):
    """Assemble every block sequentially from `code_base`.  No forward references exist
    between blocks, so one pass is exact."""
    require(CAP_PTR - CAVE + len(caption) + 1 <= code_base - CAVE,
            "the %d-byte caption record overruns the code base" % (len(caption) + 9))
    addrs, blobs, va = {}, {}, code_base
    for name, src in _blocks(tabsel_src, CAP_PTR):
        b = bytes(ks.asm(src, va)[0])
        addrs[name] = va
        blobs[name] = b
        va += len(b)
        va = (va + 3) & ~3                       # keep the next block dword-aligned
    require(va - CAVE <= CAVE_BLOCK,
            "cave content is %d B, larger than the %d B reserved block" % (va - CAVE, CAVE_BLOCK))

    blob = bytearray(CAVE_BLOCK)
    for i, v in enumerate(ORDER_VALS):
        struct.pack_into("<I", blob, (ORDER - CAVE) + i * 4, v)
    for i, v in enumerate(RORDER_VALS):
        struct.pack_into("<I", blob, (RORDER - CAVE) + i * 4, v)
    raw = caption + b"\x00"
    struct.pack_into("<iI", blob, CAP_REC - CAVE, -1, len(caption))
    blob[(CAP_PTR - CAVE):(CAP_PTR - CAVE) + len(raw)] = raw
    for name in addrs:
        o = addrs[name] - CAVE
        blob[o:o + len(blobs[name])] = blobs[name]
    return bytes(blob), addrs, blobs, va - CAVE


CAVE_BLOB, CAVE_ADDR, CAVE_PARTS, CAVE_USED = build_cave(SRC_TABSEL,    CAPTION,     CODE_BASE)
V2_BLOB,   V2_ADDR,   _V2_PARTS, V2_USED    = build_cave(SRC_TABSEL,    CAPTION_OLD, CODE_BASE_12)
V1_BLOB,   V1_ADDR,   _V1_PARTS, V1_USED    = build_cave(SRC_TABSEL_V1, CAPTION_OLD, CODE_BASE_12)

# The growth zone: everything an installed v1 or v2 could have left beyond the v3 body must
# be zero, so overwriting the cave in place cannot leave stale bytes behind the new one.
require(V1_USED <= CAVE_USED and V2_USED <= CAVE_USED,
        "a superseded cave body is longer than v3 -- in-place rewrite unsafe")
require(set(CAVE_BLOB[CAVE_USED:]) <= {0} and set(V2_BLOB[CAVE_USED:]) <= {0}
        and set(V1_BLOB[CAVE_USED:]) <= {0},
        "cave tail beyond the v3 body is not zero")


# ---------------------------------------------------------------- patch table
ORIG_SETIDX = call_rel(C_SETIDX, SETIDX)
ORIG_UP     = b"\x4A" + call_rel(C_UP_C, SETSCENEL)
ORIG_DN     = b"\x42" + call_rel(C_DN_C, SETSCENEL)


def _new_bytes(addrs):
    """The five replacement byte-runs implied by one assembled cave layout."""
    return [jmp_rel(H_CAPS, addrs["cave_caps"]) + b"\x90" * (H_CAPS_N - 5),
            jmp_rel(H_TAB, addrs["cave_tabsel"]),
            call_rel(C_SETIDX, addrs["cave_setidx"]),
            b"\x90" + call_rel(C_UP_C, addrs["cave_lvlup"]),
            b"\x90" + call_rel(C_DN_C, addrs["cave_lvldn"])]


NEW_V3 = _new_bytes(CAVE_ADDR)
NEW_V2 = _new_bytes(V2_ADDR)
NEW_V1 = _new_bytes(V1_ADDR)

require(len(ORIG_CAPS) == H_CAPS_N and len(NEW_V3[0]) == H_CAPS_N, "caption patch length")
require(len(ORIG_TAB) == H_TAB_N and len(NEW_V3[1]) == H_TAB_N, "tabsel patch length")

# (label, VA, original bytes, v3 bytes, v2 bytes, v1 bytes)
SITES = [
    ("caption fill  0x%08X" % H_CAPS,   H_CAPS,   ORIG_CAPS,   NEW_V3[0], NEW_V2[0], NEW_V1[0]),
    ("tab change    0x%08X" % H_TAB,    H_TAB,    ORIG_TAB,    NEW_V3[1], NEW_V2[1], NEW_V1[1]),
    ("SetIndex call 0x%08X" % C_SETIDX, C_SETIDX, ORIG_SETIDX, NEW_V3[2], NEW_V2[2], NEW_V1[2]),
    ("PgUp  dec+call0x%08X" % C_UP_B,   C_UP_B,   ORIG_UP,     NEW_V3[3], NEW_V2[3], NEW_V1[3]),
    ("PgDn  inc+call0x%08X" % C_DN_B,   C_DN_B,   ORIG_DN,     NEW_V3[4], NEW_V2[4], NEW_V1[4]),
]

KNOWN_SITE_BYTES = [(o, n3, n2, n1) for _, _, o, n3, n2, n1 in SITES]
KNOWN_CAVES = (CAVE_BLOB, V2_BLOB, V1_BLOB, b"\x00" * CAVE_BLOCK)


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


STATE_TEXT = {
    "orig":       "unpatched",
    "patched":    "applied (v3 -- caption %r)" % CAPTION.decode(),
    "patched-v2": "applied (v2 -- caption 'Sky') -- needs re-tune, run --apply",
    "patched-v1": "applied (v1 -- 'Sky', NO SLOT WHITELIST) -- needs re-tune, run --apply",
    "partial":    "half-written / mixed -- run --apply to normalise",
    "unknown":    "unrecognised bytes",
}


def state(img):
    """'orig', 'patched' (v3), 'patched-v2', 'patched-v1', 'partial' or 'unknown'."""
    bad = []
    orig_all = v3_all = v2_all = v1_all = True
    for label, va, o, n3, n2, n1 in SITES:
        cur = img.read(va, len(o))
        if cur != o:
            orig_all = False
        if cur != n3:
            v3_all = False
        if cur != n2:
            v2_all = False
        if cur != n1:
            v1_all = False
        if cur not in (o, n3, n2, n1):
            bad.append("%s: %s" % (label, cur.hex(" ")))
    cave = img.read(CAVE, CAVE_BLOCK)
    cave_zero = cave == b"\x00" * CAVE_BLOCK
    cave_ours = cave == CAVE_BLOB
    if bad:
        return "unknown", bad, cave_zero, cave_ours
    if orig_all and cave_zero:
        return "orig", [], cave_zero, cave_ours
    if v3_all and cave_ours:
        return "patched", [], cave_zero, cave_ours
    if v2_all and cave == V2_BLOB:
        return "patched-v2", [], cave_zero, cave_ours
    if v1_all and cave == V1_BLOB:
        return "patched-v1", [], cave_zero, cave_ours
    return "partial", [], cave_zero, cave_ours


# ---------------------------------------------------------------- reporting
def show_state():
    for path in TARGETS:
        img = Image(path)
        st, bad, cz, co = state(img)
        print("%-14s  %-10s %s   (cave zero=%s  cave==v3=%s)"
              % (os.path.basename(path), st, STATE_TEXT.get(st, ""), cz, co))
        for label, va, o, n3, n2, n1 in SITES:
            cur = img.read(va, len(o))
            tags = [t for t, b in (("ORIG", o), ("v3", n3), ("v2", n2), ("v1", n1)) if cur == b]
            print("    %-24s %-9s %s" % (label, "=".join(tags) or "?????", cur.hex(" ")))
        for b in bad:
            print("    !! " + b)


def disassemble():
    print("cave 0x%08X..0x%08X, %d of %d bytes used\n" % (CAVE, CAVE + CAVE_BLOCK - 1,
                                                          CAVE_USED, CAVE_BLOCK))
    print("  ORDER  slot->level @0x%08X = %s" % (ORDER, list(ORDER_VALS)))
    print("  RORDER level->slot @0x%08X = %s" % (RORDER, list(RORDER_VALS)))
    print("  caption %r @0x%08X  refcnt=%d len=%d  ptr=0x%08X\n"
          % (CAPTION.decode(), CAP_REC, struct.unpack_from("<i", CAVE_BLOB, CAP_REC - CAVE)[0],
             struct.unpack_from("<I", CAVE_BLOB, CAP_REC - CAVE + 4)[0], CAP_PTR))
    for name in BLOCK_NAMES:
        va, b = CAVE_ADDR[name], CAVE_PARTS[name]
        print("---- %s @0x%08X (%d B) ----" % (name, va, len(b)))
        for i in cs.disasm(b, va):
            print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
        print()
    print("---- displaced-site replacements ----")
    for label, va, o, n3, n2, n1 in SITES:
        print("  %-24s  %s  ->  %s" % (label, o.hex(" "), n3.hex(" ")))
    print("\n---- superseded layouts (recognised, never written) ----")
    for name in BLOCK_NAMES:
        print("  %-12s v2 @0x%08X   v1 @0x%08X" % (name, V2_ADDR[name], V1_ADDR[name]))
    print("  v2 %d B / v1 %d B of %d B used" % (V2_USED, V1_USED, CAVE_BLOCK))


# ---------------------------------------------------------------- apply / undo
def compat_check():
    a = open(TARGETS[0], "rb").read()
    b = open(TARGETS[1], "rb").read()
    require(len(a) == len(b), "%s / %s differ in length" % tuple(zigexe.EXES))
    d = [i for i in range(len(a)) if a[i] != b[i]]
    require(d == [COMPAT_DIFF_OFF],
            "%s and %s must differ in exactly one byte at 0x%08X; got %s"
            % (zigexe.EXES[0], zigexe.EXES[1], COMPAT_DIFF_OFF,
               [hex(x) for x in d[:8]]))
    print("lockstep ok: the two exes differ in exactly one byte, 0x%08X" % COMPAT_DIFF_OFF)


def backup(img):
    """Mint a .pre-skylevelui snapshot ONLY from a file positively proved unpatched."""
    st, bad, cz, co = state(img)
    if st != "orig":
        print("    no backup taken (%s is not in the original state: %s)"
              % (os.path.basename(img.path), st))
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, os.path.basename(img.path) + ".pre-skylevelui")
    if os.path.exists(dst):
        print("    backup already exists: %s" % dst)
        return
    shutil.copyfile(img.path, dst)
    print("    backup -> %s" % dst)


def apply_all(undo=False):
    for path in TARGETS:
        img = Image(path)
        st, bad, cz, co = state(img)
        require(not bad, "%s: unrecognised bytes -- %s" % (os.path.basename(path), "; ".join(bad)))
        print("%s: %s" % (os.path.basename(path), st))

        if undo:
            if st == "orig":
                print("    already unpatched, nothing to do")
                continue
            require(st in ("patched", "patched-v2", "patched-v1", "partial"),
                    "%s: refusing to undo from state %r" % (path, st))
            cur_cave = img.read(CAVE, CAVE_BLOCK)
            require(cur_cave in KNOWN_CAVES,
                    "%s: cave 0x%08X holds bytes this script did not write -- refusing to zero it"
                    % (path, CAVE))
            for label, va, o, n3, n2, n1 in SITES:
                img.write(va, o)
            img.write(CAVE, b"\x00" * CAVE_BLOCK)
        else:
            if st == "patched":
                print("    already patched, nothing to do")
                continue
            if st in ("patched-v2", "patched-v1"):
                print("    %s installed -- rewriting the cave in place (no backup touched)"
                      % st.split("-")[1])
            backup(img)
            cur_cave = img.read(CAVE, CAVE_BLOCK)
            require(cur_cave in KNOWN_CAVES,
                    "%s: cave 0x%08X is not zero and is not one of our own builds -- refusing"
                    % (path, CAVE))
            require(set(cur_cave[CAVE_USED:]) <= {0},
                    "%s: the zone the v3 cave grows into (0x%08X..0x%08X) is not zero"
                    % (path, CAVE + CAVE_USED, CAVE + CAVE_BLOCK - 1))
            for label, va, o, n3, n2, n1 in SITES:
                cur = img.read(va, len(o))
                require(cur in (o, n3, n2, n1),
                        "%s @%08X: verify-before-write failed" % (path, va))
                img.write(va, n3)
            img.write(CAVE, CAVE_BLOB)

        img.save()
        print("    written")

    print()
    compat_check()
    print()
    show_state()


def main():
    args = sys.argv[1:]
    print("Firmament map level -- UI half (%s + %s), v3" % tuple(zigexe.EXES))
    print("cave 0x%08X (%d/%d B used)  order=%s  caption=%r\n"
          % (CAVE, CAVE_USED, CAVE_BLOCK, list(ORDER_VALS), CAPTION.decode()))
    if "--dis" in args or "--show" in args:
        disassemble()
        return
    if "--undo" in args:
        apply_all(undo=True)
        return
    if "--apply" in args:
        apply_all(undo=False)
        return
    show_state()
    print("\n(dry run -- nothing written; use --apply)")


if __name__ == "__main__":
    main()
