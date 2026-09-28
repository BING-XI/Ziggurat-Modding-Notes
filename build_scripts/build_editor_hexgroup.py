#!/usr/bin/env python3
r"""
EDITOR HEX-GROUP SELECTION + AREA COPY/PASTE  --  HSEPack.dpl, Images\General.ilb, Images\_General.ilb

WHAT IT DOES (editor only -- every hook sits in THSMEdit, which AoWz.exe never runs)
  * Shift + RIGHT-click a hex toggles that hex in or out of a "group". Joining selects every
    eligible object on the hex into the editor's ordinary multi-object selection
    (THexagonSpriteSelection [+8]); leaving unselects them. The hex's terrain hexagon is the
    membership token: if it is selected the click removes, otherwise it adds.
  * Group hexes are drawn with the game's own 3-D hex-selector glow (General.ilb ids 7 back /
    6 front, `3dHex.BMP`), recoloured purple (+55 deg hue) and stored as NEW ids 60 / 61.
  * Ctrl+C / Ctrl+X copy the whole selection (vanilla already did) AND put a second clipboard
    format, "Ziggurat.HexPositions", beside the component stream: one (x, y) int16 pair per
    object, in stream order. Registered with RegisterClipboardFormatA, so it survives between two
    editor processes (build_deved_multi_instance.py) exactly like the vanilla format does.
  * Ctrl+V (after left-clicking the destination hex, as in vanilla) places every object at its
    offset from the copied set's anchor instead of stacking the lot on one hex. Anchor = the
    leftmost column's topmost TERRAIN HEXAGON, flagged by bit 14 of the stored x; only a copy
    holding no hexagon falls back to all objects. Taking every object would anchor on a mountain
    whose base lies outside the group -- a TMountainMO sits in the field of each hex it covers,
    so grouping a hex selects mountains based a column away. Offsets are taken in CUBE coordinates, because the grid is
    odd-q (HXtoHP: x*32+8, y*32+(x&1)*16) and a raw (dx, dy) shifts shape whenever the column
    parity of source and destination differ. An object landing off the map is refused through
    vanilla's own failure path (free + MessageBeep). A clipboard with no position block, or one
    whose count disagrees with the component stream, falls back to vanilla stacking -- and a
    single-hex copy pastes exactly as vanilla did, since every delta is zero.
  * Esc clears everything: group, location selection and the paste ghost (H8). Vanilla Esc only
    hid the preview window -- vanilla's deselect key is SPACE (UnselectAll + drop the place brush),
    and the 2026-09-26 claim that Esc cleared the group was never true. In preview mode Esc still
    only hides the preview.
  * A plain left-click drops the group (H1): every HS in [sel+8] but not in the location list
    [sel+0x10] is unselected, then vanilla's click runs. The location list is kept so vanilla's
    click-again-to-cycle-through-a-stack still works. Shift+left-click keeps the group.
  * Del and Ctrl+X act on the whole selection, which deletes every object except terrain --
    DeleteHS gates on HS vmt+0x64 (misexported as TAbstractHexagon.GetLevel; returns 0). Vanilla
    CutHS walked the LOCATION list only (identical to the whole list in vanilla); CUT_SITES
    repoints its five `mov eax,[edi+0x10]` at [edi+8], so Ctrl+X cuts the group as Ctrl+C copies it.
  * PasteHS empties the selection with TECustomNode.QuickClear, which drops group members without
    calling their Unselect, so their selected bit stays set. Harmless: TMapObject.MainRemove then
    finds no list entry, and the next Select sets the bit again.

ELIGIBILITY (owner ruling 2026-09-26: everything except armies, cities and events)
  An object joins a group iff
    CanSelect(hs, hex-centre px, py)   HS vmt+0xF8 -- the vanilla click test. Rejects border
                                       hexagons and TDynamicIsometricHexagon (both return 0)
    and not IsClass(hs, THPBasedHS)    engine display sprites (selection markers)
    and no ancestor class is named TUnitHS / TCity / TFlagEvent / TMoveOnEvent.
  The last test walks the VMT parent chain by NAME (name @ VMT-0x20, parent classref @ VMT-0x18)
  because those classes live in AoWEPACK.dpl, which HSEPack.dpl must not import. Matching TCity
  exactly matters: TCity -> TPlayerCropStructure -> TPlayerStructure -> TStructure, and
  TPlayerStructure also covers mines and nodes, which DO travel.
  Paste semantics: layer on top (owner ruling). Terrain replaces terrain because
  TAbstractHexagon.PlaceHX (0x5560A6D4) frees the hex's existing hexagon itself.

HOOKS (none overlaps a .reloc entry -- checked on every run)
  H1 0x556144C2 THSMEdit.MouseDown+0x3A  `cmp byte [esi+0x1D4],0` (7B) -> jmp cave_md + 2 nop
     Runs after the inherited DCPACK MouseDown. Shift+Right: toggle, then jump to the function's
     common tail 0x556145FC, skipping both the map-mouse Down (which would UnselectLocation) and
     the right-click popup. Plain left: clear_group, then vanilla. Anything else re-runs the
     displaced cmp and resumes at 0x556144C9.
  H8 0x556135AD THSMEdit.KeyDown, the VK_ESCAPE jump-table case `cmp byte [ebx+0x1E8],1` (7B)
     -> jmp cave_esc + 2 nop. Preview mode -> 0x556135B6 (vanilla HidePreview); otherwise
     UnselectAll, ghost off, rotation 0 -> 0x556135BD (the case's common exit).
  H9 CUT_SITES, five one-byte displacement changes in CutHS: [edi+0x10] -> [edi+8].
  H2 0x55613151 CopyHS  `call TECopyComponent.CopyToClipboard` -> call cave_copy
  H3 0x5561302E CutHS   same call                                  -> call cave_copy
  H4 0x5561322D PasteHS `call TECopyComponent.PasteFromClipboard`  -> call cave_pfc
  H5 0x5561329E PasteHS `call THSMap.Place` (EBX = list index)     -> call cave_place
  H7 0x5560BAAB THexagonSpriteSelection.Select `call TList.Add` -> `call cave_seladd`, which
     adds only when the HS is absent (see DOUBLE-FREE below), plus the one byte at SELLOC_VA.
  H6 0x55614219 ShowSelection per-HS loop `mov eax,[eax]; call [eax+0xE8]` (8B) -> jmp cave_ss
     An HS in the location list [sel+0x10] (a plain click or a fresh paste) keeps the vanilla
     marker. Any other selected HS is a group member: a terrain hexagon draws the purple glow,
     everything else draws nothing, so one glow per hex whatever the hex holds.

  cave_copy also removes duplicate entries from the copy list before streaming it: left-clicking
  a hex already in a group adds its top object to the selection TList a second time (vanilla
  Select does not check), which would otherwise paste it twice.

THE GLOW
  Two one-shot TLibraryHS per visible group hex, built with the editor's own
  THSLibrary.CreateHS(HSEditModule[+0x48], 0) -- so creation, the HSBrushes list and
  self-destruction after Show are exactly vanilla's marker lifecycle -- then SetImage'd to
  General.ilb id 60 (back, prio level 0x1D) / 61 (front, 0x1E) and placed through the sprite's
  Place virtual (vmt+0xC0) at HXtoHP - (8, 0x1E): the offset TAbstractAoWHSMap.Show{Back,Front}
  HexagonSelector (0x557732F4 / 0x5577338C) use in the game. Everything dynamic draws over the
  static scene, so the column is a translucent overlay rather than wrapping the hex's objects.
  The library is fetched with the engine's own call, LinkToIL([[engine+0x38]+0x2C], 1,
  'GENERAL.ILB') -- flag 1 = only libraries the resource set declares, which GENERAL.ILB is --
  once per ShowSelection pass (loop index <= last index => new pass), and ImageExist gates both
  ids: a General.ilb without them draws no glow instead of reading past the image table
  (TCustomImageLibrary.Get has no bounds check).

PASTE PREVIEW + WHEEL ROTATION (added 2026-09-26)
  * A ghost of the pending paste follows the cursor: one purple glow column per terrain hexagon in
    the copied set, at its rotated offset from the hovered hex. It is armed by Ctrl+C / Ctrl+X
    (G_GHOST, rotation reset to 0) and disarmed by Ctrl+V and Esc; a copy holding fewer than two
    terrain hexagons (G_NHEX) shows none. Until 2026-09-28 it never disarmed and the wheel re-armed
    it from whatever was on the clipboard, so an identical-looking purple copy of the last group
    followed the cursor for the rest of the session. It is drawn by `cave_preview`, which
    takes over UpdateFrame's `call ShowSelection` (0x55614B12) and tail-jumps into it, so the ghost
    and the group highlight are the same sprites in the same frame. Nothing is placed on the map --
    a real-content ghost would have to place the clipboard objects per frame, and placing a terrain
    hexagon FREES the one already there (TAbstractHexagon.PlaceHX), so the shape is what is shown.
  * The mouse wheel rotates the pending paste 60 deg per notch, `G_ROT` 0..5. `cave_place` rotates
    each object's cube delta by that before placing, so the preview and the paste cannot disagree.
    Rotation is in CUBE space (odd-q: r = y - (x - (x&1))/2); one notch is (q,r) -> (-r, q+r).
    Six notches return the set to its starting shape (verified against the same arithmetic in
    Python). Multi-hex structures rotate their BASE hex only -- no rotated artwork exists.
  * The wheel arrives by SUBCLASSING the map window: `ensure_subclass` (called each frame from
    cave_preview) does SetWindowLongA(GWL_WNDPROC) once per handle, keeping the old proc in
    G_OLDPROC, and `cave_wndproc` handles WM_MOUSEWHEEL and passes everything else to
    CallWindowProcA. ⚠ This only works because no ancestor of THSMEdit has WS_VSCROLL/WS_HSCROLL:
    build_wheel_editor.py's WH_MOUSE hook swallows a wheel only when it FINDS a scrollable window
    in the parent chain, and here it finds none, so the message reaches the window proc. Give any
    ancestor a scroll style and this silently stops working.
  * The preview needs the positions before a paste happens, so `load_positions` is called from
    cave_copy (right after the block is on the clipboard) and from the wheel handler. The wheel
    acts only while the ghost is armed, so a copy made in another editor instance pastes with its
    shape but shows no ghost. cave_pfc still reloads at paste time and is the only one that also
    checks the count against the component stream.
  ⚠ The wheel handler is reached ONLY when the map view has focus, because Windows sends
    WM_MOUSEWHEEL to the focus window, not the window under the cursor. Click the map first.

THE DOUBLE-FREE THIS PATCH HAD TO CLOSE (crash reported 2026-09-26, fixed same day)
  Vanilla keeps two lists in a THexagonSpriteSelection -- [sel+8] every selected HS, [sel+0x10]
  the "location" subset -- and they are always EQUAL, because `Select` has exactly one caller,
  `SelectLocationHS`, and `SelectLocation` unselects the previous location before selecting.
  So vanilla's unconditional `TList.Add` in `Select` can never produce a duplicate.

  A group puts an HS in [sel+8] ALONE. Left-click that same hex and `SelectLocation`'s
  "already selected?" test looks in [sel+0x10], misses it, and `Select` adds a SECOND copy to
  [sel+8]. `DeleteHS` (Del) and `CutHS` (Ctrl+X) then walk [sel+8] by index calling each entry's
  destructor -- so the object is freed TWICE. That corrupts the Delphi heap free-list, and the
  EAccessViolation surfaces later in an unrelated allocation (reported at VCL30 0x41301E3C,
  `mov [edx],eax` in the free-block linker -- i.e. nowhere near the real fault).

  Two fixes, both tiny: `cave_seladd` makes the Add idempotent, which covers every path into
  `Select`; and SELLOC_VA makes a click on a grouped hex a no-op rather than an eviction.
  ⚠ The duplicate was invisible to the 2026-09-26 apply-time testing because every check read
  the selection after grouping and pasting, never after a plain click on an already-grouped hex.

CLIPBOARD
  Raw user32 calls, reached through VCL30.dpl's own IAT (HSEPack imports none of them):
    vcl_delta = [HSEPack IAT slot of Classes.TList.IndexOf] - IndexOf's preferred VA in VCL30
    fn        = [VCL30 IAT slot + vcl_delta]
  The block is appended AFTER vanilla's SetComponent has closed the clipboard: OpenClipboard(
  Application.Handle), SetClipboardData, CloseClipboard -- no EmptyClipboard, so the component
  format stays. TClipboard.SetAsHandle is NOT usable for this: it re-opens, and its Adding()
  empties the clipboard once per open session.

STATE lives in the new R/W/X section `.hxg` (per-process copy-on-write): 0x2C bytes of globals,
constant strings, the code, then a 64 KB position buffer beyond the raw data (loader-zeroed),
MAXN = 16384 objects per copy.

FORWARD HAZARD: `.hxg` is appended AFTER `.rgt`. build_editor_rendergate.py's in-place retune
asserts `.rgt` is the last section and will refuse; to retune the render gate, `--undo` this,
retune, re-apply. build_dlgdirs.py's `.dlgd` is unaffected.

CONVENTIONS: dry-run by default; --apply writes; --undo reverts surgically (restores every hook site,
drops `.hxg` while it is still the last section, splices ids 60/61 back out of both ILBs);
idempotent; verify-before-write. The DLL is locked by AoWz.exe, AoWzCompat.exe and AoWzEd.exe.
No .pre-* snapshot is minted: the --undo is the revert path.

Roll pattern: none -- no randomness.
Needs: pip install keystone-engine capstone
"""
import argparse, os, struct, sys, colorsys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
import ilb as ilbmod

DLL = os.path.join(GAME, "HSEPack.dpl")
VCL = os.path.join(GAME, "VCL30.dpl")
ILBS = [os.path.join(GAME, "Images", "General.ilb"), os.path.join(GAME, "Images", "_General.ilb")]
SECT_NAME = b".hxg\0\0\0\0"
PREF_BASE = 0x55600000

# ---- HSEPack.dpl facts (bytes verified below on every run) ----------------------------------
H1_VA, H1_ORIG, H1_RESUME, MD_TAIL = 0x556144C2, bytes.fromhex("80bed401000000"), 0x556144C9, 0x556145FC
H6_VA, H6_ORIG, SS_RESUME, SS_SKIP = 0x55614219, bytes.fromhex("8b00ff90e8000000"), 0x55614221, 0x5561435F
PREVIEW_VA, PREVIEW_ORIG_TARGET = 0x55614B12, 0x556141B4   # UpdateFrame's `call ShowSelection`
CALL_SITES = {            # site -> original call target
    0x55613151: 0x556020D4,   # CopyHS  -> TECopyComponent.CopyToClipboard
    0x5561302E: 0x556020D4,   # CutHS   -> TECopyComponent.CopyToClipboard
    0x5561322D: 0x556020DC,   # PasteHS -> TECopyComponent.PasteFromClipboard
    0x5561329E: 0x5560CFB4,   # PasteHS -> THSMap.Place
    PREVIEW_VA: PREVIEW_ORIG_TARGET,   # UpdateFrame -> ShowSelection (preview runs just before it)
    0x5560BAAB: 0x556013D4,   # THexagonSpriteSelection.Select -> TList.Add   (dedupe, see DOUBLE-FREE)
}
# One byte, in THexagonSpriteSelection.SelectLocation's "already selected?" test: look in the
# ALL list [sel+8] instead of the location list [sel+0x10].  Identical in vanilla (the two lists
# are always equal there -- Select has exactly ONE caller, SelectLocationHS); with a group live it
# makes a plain left-click on a grouped hex a no-op instead of quietly evicting it from the group.
SELLOC_VA, SELLOC_ORIG, SELLOC_NEW = 0x5560BCBA, bytes.fromhex("8b4010"), bytes.fromhex("8b4008")
# KeyDown's VK_ESCAPE case (jump-table target): `cmp byte [ebx+0x1E8],1` -> jmp cave_esc + 2 nop
ESC_VA, ESC_ORIG, ESC_PREVIEW, KD_EXIT = 0x556135AD, bytes.fromhex("80bbe801000001"), 0x556135B6, 0x556135BD
# CutHS: every `mov eax,[edi+0x10]` (location list) -> `mov eax,[edi+8]` (whole selection)
CUT_SITES, CUT_ORIG, CUT_NEW = (0x55612FBE, 0x55612FDD, 0x55612FE9, 0x55613037, 0x55613043), \
    bytes.fromhex("8b4710"), bytes.fromhex("8b4708")
CHECKS = {                # VA -> expected bytes (anchors the addresses the caves call/jump to)
    MD_TAIL:   bytes.fromhex("c686d401000000"),
    SS_RESUME: bytes.fromhex("a802"),
    SS_SKIP:   bytes.fromhex("ff442404"),
    ESC_VA + 7: bytes.fromhex("7507"),             # jne KD_EXIT, skipped by the hook
    ESC_PREVIEW: bytes.fromhex("8bc3e8"),          # mov eax,ebx; call HidePreview
    KD_EXIT:   bytes.fromhex("66833e0d"),          # cmp word [esi],VK_RETURN
}
F = dict(
    CopyToClipboard=0x556020D4, PasteFromClipboard=0x556020DC, CC_GetCount=0x556020C4,
    CC_GetEObject=0x556020BC, HSMap_Place=0x5560CFB4, HSMap_Viewing=0x5560D1A4,
    ShowSelection=0x556141B4, MM_GetXhx=0x5560B6B0, MM_GetYhx=0x5560B718, GetField=0x55608D84,
    Sel_Select=0x5560BAA0, Sel_Unselect=0x5560BA44, Sel_UnselectLocation=0x5560BD14,
    Sel_UnselectAll=0x5560BAC8,
    IsClass=0x556010B0, TList_IndexOf=0x556013F4, TList_Delete=0x556013E4,
    TList_Add=0x556013D4,
    Lib_CreateHS=0x55611878, LHS_SetImage=0x556114A4, ShowMsg=0x55613D50,
    GetHandle=0x55601834,
    IL_Get=0x556019DC, IL_ImageExist=0x556019E4, IL_LinkToIL=0x5560195C,
)
THUNKS = {                # thunk VA -> imported name it must jump through
    0x556020D4: "Engine.TECopyComponent.CopyToClipboard",
    0x556020DC: "Engine.TECopyComponent.PasteFromClipboard",
    0x556020C4: "Engine.TECopyComponent.GetCount",
    0x556020BC: "Engine.TECopyComponent.GetEObject",
    0x556010B0: "System.@IsClass",
    0x556013F4: "Classes.TList.IndexOf",
    0x556013E4: "Classes.TList.Delete",
    0x556013D4: "Classes.TList.Add",
    0x55601834: "Controls.TWinControl.GetHandle",
    0x556019DC: "ImageLib.TCustomImageLibrary.Get",
    0x556019E4: "ImageLib.TCustomImageLibrary.ImageExist",
    0x5560195C: "ImageLib.TImageLibraryManager.LinkToIL",
}
FUNC_HEADS = {            # own functions: first bytes as disassembled 2026-09-26
    0x5560CFB4: "558bec538b5d0c53",       # THSMap.Place
    0x5560D1A4: "55",                     # THSMap.Viewing
    0x5560B6B0: None, 0x5560B718: "535683c4f8",
    0x55608D84: "558bec538b40088b4004",   # TMapContainer.GetField
    0x5560BAA0: "53568bf28bd8",           # THexagonSpriteSelection.Select
    0x5560BA44: "5356578bf28bd8",         # .Unselect
    0x5560BD14: "53568bd8",               # .UnselectLocation
    0x5560BAC8: "538bd8eb0e",             # .UnselectAll
    0x55613D50: "558bec5153",             # THSMEdit.ShowMsg
    0x55611878: "5356578bfa8bf0",         # THSLibrary.CreateHS
    0x556114A4: "5356578bfa8bd8",         # TLibraryHS.SetImage
}
VMT_AHEX, VMT_HPB = 0x556047CC, 0x55603F08       # TAbstractHexagon, THPBasedHS (self-ptr checked)
HSEDMOD_VAR = 0x5562F860                           # HSEdMod.HSEditModule (BSS var)
SLOT_INDEXOF = 0x556305B8                          # HSEPack IAT: VCL30!Classes.TList.IndexOf

ID_BACK, ID_FRONT = 60, 61        # new General.ilb ids (from 7 = back walls, 6 = front walls)
SRC_BACK, SRC_FRONT = 7, 6
HUE_SHIFT = 55 / 360.0
MAGIC = 0x5058485A                # 'ZHXP'
MAXN = 0x4000
HEXFLAG, XMASK = 0x4000, 0x3FFF  # x word: bit 14 marks a terrain hexagon (map x is 0..127)
FMT_NAME = b"Ziggurat.HexPositions\0"

# section layout
G_VALID, G_COUNT, G_AX, G_AR, G_ROT, G_LIB = 0x00, 0x04, 0x08, 0x0C, 0x10, 0x14
G_OLDPROC, G_HWND, G_SELF = 0x18, 0x1C, 0x20
G_GHOST, G_NHEX = 0x24, 0x28   # ghost armed (copy/cut -> 1, paste/Esc -> 0); hexagons in the block
S_FMT, S_GEN, S_NAMES, S_ROT, CODE = 0x40, 0x68, 0x78, 0xC0, 0x200
POS = 0x2000
ROTSTR = 0x1C               # bytes per rotation message (StrRec 8 + text + NUL, padded)


# ---- PE helpers ---------------------------------------------------------------------------------
def load_pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        name = bytes(d[b:b + 8])
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append(dict(name=name, va=va, vsz=vsz, raw=raw, rsz=rsz, hdr=b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                base=struct.unpack_from("<I", d, opt + 28)[0],
                salign=struct.unpack_from("<I", d, opt + 32)[0],
                falign=struct.unpack_from("<I", d, opt + 36)[0],
                hdrsz=struct.unpack_from("<I", d, opt + 60)[0],
                dirs=[struct.unpack_from("<II", d, opt + 96 + i * 8) for i in range(16)])


def align(x, a):
    return (x + a - 1) // a * a


def r2o(P, rva):
    for s in P["secs"]:
        if s["va"] <= rva < s["va"] + max(s["vsz"], s["rsz"]) and rva - s["va"] < s["rsz"]:
            return s["raw"] + rva - s["va"]
    raise ValueError(hex(rva))


def v2o(P, va):
    return r2o(P, va - P["base"])


def cstr(d, P, rva):
    o = r2o(P, rva)
    return bytes(d[o:d.index(b"\0", o)]).decode("latin1")


def import_slots(d, P):
    """{slot VA: 'dll!name'} straight from the import directory."""
    out = {}
    rva = P["dirs"][1][0]
    o = r2o(P, rva)
    while True:
        oft, _, _, nrva, ft = struct.unpack_from("<IIIII", d, o)
        if not nrva:
            break
        dll = cstr(d, P, nrva)
        lk = r2o(P, oft or ft)
        i = 0
        while True:
            v = struct.unpack_from("<I", d, lk + 4 * i)[0]
            if not v:
                break
            name = ("#%d" % (v & 0xFFFF)) if v & 0x80000000 else cstr(d, P, v + 2)
            out[P["base"] + ft + 4 * i] = dll + "!" + name
            i += 1
        o += 20
    return out


def exports(d, P):
    rva = P["dirs"][0][0]
    o = r2o(P, rva)
    nfun, nnam, afun, anam, aord = struct.unpack_from("<IIIII", d, o + 20)
    out = {}
    for i in range(nnam):
        nm = cstr(d, P, struct.unpack_from("<I", d, r2o(P, anam) + 4 * i)[0])
        ordi = struct.unpack_from("<H", d, r2o(P, aord) + 2 * i)[0]
        out[nm] = P["base"] + struct.unpack_from("<I", d, r2o(P, afun) + 4 * ordi)[0]
    return out


def relocs(d, P):
    rva, sz = P["dirs"][5]
    o, end, out = r2o(P, rva), r2o(P, rva) + sz, set()
    while o < end:
        page, bs = struct.unpack_from("<II", d, o)
        if bs == 0:
            break
        for i in range((bs - 8) // 2):
            e = struct.unpack_from("<H", d, o + 8 + 2 * i)[0]
            if e >> 12 == 3:
                out.add(P["base"] + page + (e & 0xFFF))
        o += bs
    return out


def bare(imp):
    """'VCL30.dpl!System.@IsClass@51F89FF7' -> 'System.@IsClass' (drops the package hash)."""
    name = imp.split("!", 1)[1]
    head, _, tail = name.rpartition("@")
    return head if head and len(tail) == 8 else name


# ---- VCL30 facts, derived from the shipped VCL30.dpl on every run -------------------------------
def vcl_facts():
    v = open(VCL, "rb").read()
    P = load_pe(v)
    ex = exports(v, P)
    slots = {n.split("!", 1)[1]: va for va, n in import_slots(v, P).items()}

    def ex1(prefix):
        hits = [va for n, va in ex.items() if n.startswith(prefix)]
        assert len(hits) == 1, f"VCL30 export {prefix!r}: {len(hits)} matches"
        return hits[0]
    need = ["OpenClipboard", "CloseClipboard", "GetClipboardData", "SetClipboardData",
            "RegisterClipboardFormatA", "GlobalAlloc", "GlobalLock", "GlobalUnlock", "GlobalFree",
            "SetWindowLongA", "CallWindowProcA"]
    miss = [n for n in need if n not in slots]
    assert not miss, f"VCL30 does not import {miss}"
    return dict(indexof=ex1("Classes.TList.IndexOf@"), application=ex1("Forms.Application@"),
                **{n: slots[n] for n in need})


# ---- the cave ------------------------------------------------------------------------------------
def gen_src(base_va, V, wnd_off):
    code_va = base_va + CODE
    def D(va):                                # "+ 0x.." / "- 0x..": displacement from the section base (G)
        v = va - base_va
        return f"- {-v:#x}" if v < 0 else f"+ {v:#x}"

    def glow_sprite(img_id, prio):
        return f"""
        call getG
        mov  eax, dword ptr [eax {D(HSEDMOD_VAR)}]   ; HSEditModule instance
        mov  eax, dword ptr [eax + 0x48]                 ; its THSLibrary
        xor  edx, edx
        call {F['Lib_CreateHS']:#x}
        mov  edi, eax
        mov  eax, dword ptr [ebp + {G_LIB}]
        mov  edx, {img_id}
        call {F['IL_Get']:#x}
        mov  edx, eax
        mov  eax, edi
        call {F['LHS_SetImage']:#x}
        mov  byte ptr [edi + 0x24], 1
        mov  byte ptr [edi + 0x1c], {prio:#x}
        mov  eax, dword ptr [esp + 4]
        mov  ecx, eax
        shl  ecx, 5
        and  eax, 1
        shl  eax, 4
        mov  edx, dword ptr [esp + 8]
        shl  edx, 5
        add  edx, eax
        sub  edx, 0x1e
        push edx
        push dword ptr [esp + 0x10]
        mov  eax, dword ptr [esi + 0x1c0]
        mov  eax, dword ptr [eax + 0x3c]
        mov  edx, dword ptr [eax + 0x10]
        mov  eax, edi
        mov  ebx, dword ptr [edi]
        call dword ptr [ebx + 0xc0]
"""

    return f"""
getG:
        call gg1
gg1:
        pop  eax
        sub  eax, {CODE + 5:#x}
        ret

vclptr:
        call getG
        mov  eax, dword ptr [eax {D(SLOT_INDEXOF)}]
        sub  eax, {V['indexof']:#x}
        mov  eax, dword ptr [eax + edx]
        ret

app_handle:
        mov  edx, {V['application']:#x}
        call vclptr
        test eax, eax
        je   ah_ret
        mov  eax, dword ptr [eax + 0x24]
ah_ret:
        ret

hs_is_hexagon:
        push eax
        call getG
        lea  edx, [eax {D(VMT_AHEX)}]
        pop  eax
        jmp  {F['IsClass']:#x}

excluded_name:
        push ebx
        push esi
        push edi
        mov  ebx, dword ptr [eax]
xn_cls:
        test ebx, ebx
        je   xn_no
        mov  esi, dword ptr [ebx - 0x20]
        call getG
        lea  edi, [eax + {S_NAMES:#x}]
xn_name:
        movzx ecx, byte ptr [edi]
        test ecx, ecx
        je   xn_parent
        push esi
        push edi
        inc  ecx
        repe cmpsb
        pop  edi
        pop  esi
        je   xn_yes
        movzx ecx, byte ptr [edi]
        lea  edi, [edi + ecx + 1]
        jmp  xn_name
xn_parent:
        mov  eax, dword ptr [ebx - 0x18]
        test eax, eax
        je   xn_no
        mov  ebx, dword ptr [eax]
        jmp  xn_cls
xn_yes:
        mov  al, 1
        jmp  xn_ret
xn_no:
        xor  eax, eax
xn_ret:
        pop  edi
        pop  esi
        pop  ebx
        ret

eligible:
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        shl  esi, 5
        add  esi, 0x18
        and  edx, 1
        shl  edx, 4
        shl  ecx, 5
        add  ecx, edx
        add  ecx, 0x10
        mov  edx, esi
        mov  eax, ebx
        mov  esi, dword ptr [eax]
        call dword ptr [esi + 0xf8]
        test al, al
        je   el_no
        call getG
        lea  edx, [eax {D(VMT_HPB)}]
        mov  eax, ebx
        call {F['IsClass']:#x}
        test al, al
        jne  el_no
        mov  eax, ebx
        call excluded_name
        test al, al
        jne  el_no
        mov  al, 1
        jmp  el_ret
el_no:
        xor  eax, eax
el_ret:
        pop  esi
        pop  ebx
        ret

rot_delta:                                    ; eax = dq, edi = dr, ebp = G -> rotated in place
        push ebx
        mov  ecx, dword ptr [ebp + {G_ROT}]
rd_loop:
        test ecx, ecx
        je   rd_done
        mov  ebx, edi                         ; 60 deg CW in cube space: (q,r) -> (-r, q+r)
        neg  ebx
        add  edi, eax
        mov  eax, ebx
        dec  ecx
        jmp  rd_loop
rd_done:
        pop  ebx
        ret

ensure_lib:                                   ; esi = THSMEdit, ebp = G -> G_LIB (0 = unavailable)
        mov  dword ptr [ebp + {G_LIB}], 0
        mov  eax, dword ptr [esi + 0x1c0]
        mov  eax, dword ptr [eax + 0x38]
        test eax, eax
        je   el2_ret
        mov  eax, dword ptr [eax + 0x2c]
        test eax, eax
        je   el2_ret
        lea  ecx, [ebp + {S_GEN:#x}]
        mov  dl, 1
        call {F['IL_LinkToIL']:#x}
        test eax, eax
        je   el2_ret
        push eax
        mov  edx, {ID_BACK}
        call {F['IL_ImageExist']:#x}
        test al, al
        pop  eax
        je   el2_ret
        push eax
        mov  edx, {ID_FRONT}
        call {F['IL_ImageExist']:#x}
        test al, al
        pop  eax
        je   el2_ret
        mov  dword ptr [ebp + {G_LIB}], eax
el2_ret:
        ret

draw_glow:                                    ; eax = hx, edx = hy ; esi = THSMEdit, ebp = G
        push ebx
        push edi
        sub  esp, 0x10
        mov  dword ptr [esp + 4], eax
        mov  dword ptr [esp + 8], edx
        cmp  dword ptr [ebp + {G_LIB}], 0
        je   dg_ret
        mov  eax, dword ptr [esi + 0x1c0]
        mov  eax, dword ptr [eax + 0x3c]
        movzx eax, byte ptr [eax + 0x88]      ; the map's current level
        mov  dword ptr [esp + 0xc], eax
        push eax
        mov  ecx, dword ptr [esp + 0xc]
        mov  edx, dword ptr [esp + 8]
        mov  eax, dword ptr [esi + 0x1c0]
        mov  eax, dword ptr [eax + 0x3c]
        call {F['HSMap_Viewing']:#x}
        test al, al
        je   dg_ret
{glow_sprite(ID_BACK, 0x1D)}
{glow_sprite(ID_FRONT, 0x1E)}
dg_ret:
        add  esp, 0x10
        pop  edi
        pop  ebx
        ret

group_glow:
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x10
        mov  ebx, eax
        mov  esi, ecx
        call hs_is_hexagon
        test al, al
        je   gg_ret
        call getG
        mov  ebp, eax
        lea  edx, [esp]
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xf4]          ; GetBaseHX -> packed x,y,level
        movsx eax, byte ptr [esp]
        movsx edx, byte ptr [esp + 1]
        call draw_glow
gg_ret:
        add  esp, 0x10
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

load_positions:                               ; ebp = G -> G_VALID / G_COUNT / anchor / POS
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp + {G_VALID}], 0
        mov  dword ptr [ebp + {G_NHEX}], 0
        lea  eax, [ebp + {S_FMT:#x}]
        push eax
        mov  edx, {V['RegisterClipboardFormatA']:#x}
        call vclptr
        call eax
        test eax, eax
        je   lp_ret
        mov  edi, eax
        call app_handle
        push eax
        mov  edx, {V['OpenClipboard']:#x}
        call vclptr
        call eax
        test eax, eax
        je   lp_ret
        push edi
        mov  edx, {V['GetClipboardData']:#x}
        call vclptr
        call eax
        test eax, eax
        je   lp_close
        mov  edi, eax
        push edi
        mov  edx, {V['GlobalLock']:#x}
        call vclptr
        call eax
        test eax, eax
        je   lp_close
        cmp  dword ptr [eax], {MAGIC:#x}
        jne  lp_unlock
        mov  esi, dword ptr [eax + 4]
        test esi, esi
        jle  lp_unlock
        cmp  esi, {MAXN:#x}
        ja   lp_unlock
        lea  edx, [eax + 8]
        xor  ecx, ecx
lp_cp:
        mov  ebx, dword ptr [edx + ecx*4]
        mov  dword ptr [ebp + ecx*4 + {POS:#x}], ebx
        inc  ecx
        cmp  ecx, esi
        jb   lp_cp
        mov  dword ptr [ebp + {G_COUNT}], esi
        mov  dword ptr [ebp + {G_VALID}], 1
lp_unlock:
        push edi
        mov  edx, {V['GlobalUnlock']:#x}
        call vclptr
        call eax
lp_close:
        mov  edx, {V['CloseClipboard']:#x}
        call vclptr
        call eax
        cmp  dword ptr [ebp + {G_VALID}], 0
        je   lp_ret
        mov  esi, dword ptr [ebp + {G_COUNT}]
        xor  ebx, ebx                         ; anchor over terrain hexagons when the copy has any
        xor  eax, eax
        xor  ecx, ecx
lp_h0:
        test word ptr [ebp + eax*4 + {POS:#x}], {HEXFLAG:#x}
        je   lp_h1
        inc  ecx
lp_h1:
        inc  eax
        cmp  eax, esi
        jb   lp_h0
        mov  dword ptr [ebp + {G_NHEX}], ecx
        test ecx, ecx
        je   lp_h2
        mov  ebx, {HEXFLAG:#x}
lp_h2:
        mov  ecx, 0x7fffffff
        mov  edx, 0x7fffffff
        xor  eax, eax
lp_an:
        movzx edi, word ptr [ebp + eax*4 + {POS:#x}]
        test edi, ebx
        jne  lp_ok
        test ebx, ebx
        jne  lp_annext
lp_ok:
        and  edi, {XMASK:#x}
        cmp  edi, ecx
        jl   lp_newmin
        jne  lp_annext
        movsx edi, word ptr [ebp + eax*4 + {POS + 2:#x}]
        cmp  edi, edx
        jge  lp_annext
        mov  edx, edi
        jmp  lp_annext
lp_newmin:
        mov  ecx, edi
        movsx edi, word ptr [ebp + eax*4 + {POS + 2:#x}]
        mov  edx, edi
lp_annext:
        inc  eax
        cmp  eax, esi
        jb   lp_an
        mov  dword ptr [ebp + {G_AX}], ecx
        mov  eax, ecx
        and  eax, 1
        mov  ebx, ecx
        sub  ebx, eax
        sar  ebx, 1
        sub  edx, ebx
        mov  dword ptr [ebp + {G_AR}], edx
lp_ret:
        pop  edi
        pop  esi
        pop  ebx
        ret

ensure_subclass:                              ; esi = THSMEdit, ebp = G
        mov  eax, esi
        call {F['GetHandle']:#x}
        test eax, eax
        je   es_ret
        cmp  eax, dword ptr [ebp + {G_HWND}]
        je   es_ret                           ; already ours (and the handle has not changed)
        push eax
        call getG
        add  eax, {wnd_off:#x}
        mov  edi, eax
        pop  eax
        mov  dword ptr [ebp + {G_HWND}], eax
        push edi
        push -4
        push eax
        mov  edx, {V['SetWindowLongA']:#x}
        call vclptr
        call eax
        mov  dword ptr [ebp + {G_OLDPROC}], eax
es_ret:
        ret

cave_wndproc:                                 ; stdcall (hwnd, msg, wParam, lParam)
        push ebp
        push ebx
        push esi
        push edi
        cmp  dword ptr [esp + 0x18], 0x20a    ; WM_MOUSEWHEEL
        jne  wp_pass
        call getG
        mov  ebp, eax
        cmp  dword ptr [ebp + {G_SELF}], 0
        je   wp_pass
        cmp  dword ptr [ebp + {G_GHOST}], 0   ; rotate only what is on screen
        je   wp_pass
        mov  eax, dword ptr [esp + 0x1c]
        sar  eax, 16                          ; signed wheel delta
        mov  ecx, dword ptr [ebp + {G_ROT}]
        test eax, eax
        jle  wp_ccw
        inc  ecx
        jmp  wp_wrap
wp_ccw:
        add  ecx, 5
wp_wrap:
        mov  eax, ecx
        xor  edx, edx
        mov  ecx, 6
        div  ecx
        mov  dword ptr [ebp + {G_ROT}], edx
        call load_positions                   ; the clipboard may have changed under the ghost
        mov  eax, dword ptr [ebp + {G_ROT}]
        mov  edx, {ROTSTR}
        mul  edx
        lea  edx, [ebp + eax + {S_ROT + 8:#x}]
        mov  eax, dword ptr [ebp + {G_SELF}]
        call {F['ShowMsg']:#x}
        xor  eax, eax
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  0x10
wp_pass:
        call getG
        mov  edi, dword ptr [eax + {G_OLDPROC}]
        test edi, edi
        je   wp_def
        mov  eax, dword ptr [esp + 0x20]
        push eax
        mov  eax, dword ptr [esp + 0x20]
        push eax
        mov  eax, dword ptr [esp + 0x20]
        push eax
        mov  eax, dword ptr [esp + 0x20]
        push eax
        push edi
        mov  edx, {V['CallWindowProcA']:#x}
        call vclptr
        call eax
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  0x10
wp_def:
        xor  eax, eax
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  0x10

cave_seladd:
        push eax
        push edx
        call {F['TList_IndexOf']:#x}
        test eax, eax
        pop  edx
        pop  eax
        jge  sa_dup
        jmp  {F['TList_Add']:#x}
sa_dup:
        ret

cave_md:
        cmp  byte ptr [esi + 0x1d4], 0        ; the states in which vanilla handles the click
        jne  md_orig
        cmp  byte ptr [esi + 0x1e8], 0
        jne  md_orig
        cmp  byte ptr [esi + 0x1bc], 0
        je   md_orig
        test bl, bl
        jne  md_right
        test byte ptr [ebp - 1], 1            ; Shift+left keeps the group
        jne  md_orig
        pushal
        call clear_group
        popal
        jmp  md_orig
md_right:
        cmp  bl, 1
        jne  md_orig
        test byte ptr [ebp - 1], 1
        je   md_orig
        pushal
        call do_toggle
        popal
        jmp  {MD_TAIL:#x}
md_orig:
        cmp  byte ptr [esi + 0x1d4], 0
        jmp  {H1_RESUME:#x}

do_toggle:
        mov  eax, dword ptr [esi + 0x1c0]
        mov  edi, dword ptr [eax + 0x3c]
        mov  ecx, dword ptr [ebp + 0xc]
        mov  edx, dword ptr [ebp + 8]
        test ecx, ecx
        jl   dt_ret
        test edx, edx
        jl   dt_ret
        mov  eax, dword ptr [edi + 0xc]
        mov  dword ptr [eax + 8], ecx
        mov  dword ptr [eax + 0xc], edx
        push ebp
        sub  esp, 0x10
        mov  eax, dword ptr [edi + 0xc]
        call {F['MM_GetXhx']:#x}
        cmp  eax, -1
        je   dt_out
        mov  dword ptr [esp], eax
        mov  eax, dword ptr [edi + 0xc]
        call {F['MM_GetYhx']:#x}
        cmp  eax, -1
        je   dt_out
        mov  dword ptr [esp + 4], eax
        mov  eax, dword ptr [edi + 0x18]
        call {F['Sel_UnselectLocation']:#x}
        push dword ptr [edi + 0x88]
        mov  edx, dword ptr [esp + 4]
        mov  ecx, dword ptr [esp + 8]
        mov  eax, dword ptr [edi + 0x10]
        call {F['GetField']:#x}
        test eax, eax
        je   dt_out
        mov  dword ptr [esp + 8], eax
        mov  dword ptr [esp + 0xc], 0
        mov  ebx, eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  esi, eax
        xor  ebp, ebp
dt_scan:
        cmp  ebp, esi
        jge  dt_apply
        mov  eax, dword ptr [ebx + 8]
        mov  eax, dword ptr [eax + ebp*4]
        push eax
        call hs_is_hexagon
        test al, al
        pop  eax
        je   dt_next
        mov  edx, eax
        mov  eax, dword ptr [edi + 0x18]
        mov  eax, dword ptr [eax + 8]
        call {F['TList_IndexOf']:#x}
        test eax, eax
        jl   dt_next
        mov  dword ptr [esp + 0xc], 1
        jmp  dt_apply
dt_next:
        inc  ebp
        jmp  dt_scan
dt_apply:
        xor  ebp, ebp
dt_loop:
        cmp  ebp, esi
        jge  dt_out
        mov  eax, dword ptr [ebx + 8]
        mov  eax, dword ptr [eax + ebp*4]
        push eax
        mov  edx, eax
        mov  eax, dword ptr [edi + 0x18]
        mov  eax, dword ptr [eax + 8]
        call {F['TList_IndexOf']:#x}
        cmp  dword ptr [esp + 0x10], 0
        je   dt_add
        test eax, eax
        jl   dt_skip
        pop  edx
        mov  eax, dword ptr [edi + 0x18]
        call {F['Sel_Unselect']:#x}
        jmp  dt_cont
dt_add:
        test eax, eax
        jge  dt_skip
        mov  eax, dword ptr [esp]
        mov  edx, dword ptr [esp + 4]
        mov  ecx, dword ptr [esp + 8]
        call eligible
        test al, al
        je   dt_skip
        pop  edx
        mov  eax, dword ptr [edi + 0x18]
        call {F['Sel_Select']:#x}
        jmp  dt_cont
dt_skip:
        pop  eax
dt_cont:
        inc  ebp
        jmp  dt_loop
dt_out:
        add  esp, 0x10
        pop  ebp
dt_ret:
        ret

clear_group:                                  ; esi = THSMEdit: unselect [sel+8] minus [sel+0x10]
        mov  eax, dword ptr [esi + 0x1c0]
        mov  eax, dword ptr [eax + 0x3c]
        mov  edi, dword ptr [eax + 0x18]
        mov  eax, dword ptr [edi + 8]
        mov  ebx, dword ptr [eax + 8]
cg_loop:
        dec  ebx
        jl   cg_ret
        mov  eax, dword ptr [edi + 8]
        cmp  ebx, dword ptr [eax + 8]         ; an Unselect can shrink the list by more than one
        jge  cg_loop
        mov  eax, dword ptr [eax + 4]
        mov  edx, dword ptr [eax + ebx*4]
        push edx
        mov  eax, dword ptr [edi + 0x10]
        call {F['TList_IndexOf']:#x}
        pop  edx
        test eax, eax
        jge  cg_loop                          ; the location selection stays (click-to-cycle)
        mov  eax, edi
        call {F['Sel_Unselect']:#x}
        jmp  cg_loop
cg_ret:
        ret

cave_esc:                                     ; ebx = THSMEdit, esi = ^Key
        cmp  byte ptr [ebx + 0x1e8], 1
        je   {ESC_PREVIEW:#x}                 ; preview mode: vanilla, hide the preview only
        pushal
        call getG
        mov  dword ptr [eax + {G_GHOST}], 0
        mov  dword ptr [eax + {G_ROT}], 0
        mov  eax, dword ptr [ebx + 0x1c0]
        mov  eax, dword ptr [eax + 0x3c]
        mov  eax, dword ptr [eax + 0x18]
        call {F['Sel_UnselectAll']:#x}
        popal
        jmp  {KD_EXIT:#x}

cave_copy:
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        push ecx
        push edx
        mov  esi, dword ptr [ebx + 0x28]
        mov  edi, dword ptr [esi + 8]
cd_outer:
        dec  edi
        jle  cd_done
        mov  edx, dword ptr [esi + 4]
        mov  edx, dword ptr [edx + edi*4]
        mov  eax, esi
        call {F['TList_IndexOf']:#x}
        cmp  eax, edi
        jge  cd_outer
        mov  edx, edi
        mov  eax, esi
        call {F['TList_Delete']:#x}
        jmp  cd_outer
cd_done:
        pop  edx
        pop  ecx
        mov  eax, ebx
        call {F['CopyToClipboard']:#x}
        mov  eax, ebx
        call {F['CC_GetCount']:#x}
        mov  esi, eax
        test esi, esi
        jle  cc_ret
        cmp  esi, {MAXN:#x}
        ja   cc_ret
        lea  eax, [esi*4 + 8]
        push eax
        push 0x2002
        mov  edx, {V['GlobalAlloc']:#x}
        call vclptr
        call eax
        test eax, eax
        je   cc_ret
        mov  ebp, eax
        push ebp
        mov  edx, {V['GlobalLock']:#x}
        call vclptr
        call eax
        test eax, eax
        je   cc_free
        mov  edi, eax
        mov  dword ptr [edi], {MAGIC:#x}
        mov  dword ptr [edi + 4], esi
        push 0
cc_loop:
        mov  edx, dword ptr [esp]
        cmp  edx, esi
        jge  cc_done
        mov  eax, ebx
        call {F['CC_GetEObject']:#x}
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx ecx, al
        push ecx
        mov  eax, dword ptr [esp + 4]
        call hs_is_hexagon
        pop  ecx
        test al, al
        je   cc_nohex
        or   ecx, {HEXFLAG:#x}
cc_nohex:
        mov  edx, dword ptr [esp + 4]
        mov  word ptr [edi + edx*4 + 8], cx
        pop  eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx ecx, al
        mov  edx, dword ptr [esp]
        mov  word ptr [edi + edx*4 + 0xa], cx
        inc  dword ptr [esp]
        jmp  cc_loop
cc_done:
        add  esp, 4
        push ebp
        mov  edx, {V['GlobalUnlock']:#x}
        call vclptr
        call eax
        call getG
        lea  eax, [eax + {S_FMT:#x}]
        push eax
        mov  edx, {V['RegisterClipboardFormatA']:#x}
        call vclptr
        call eax
        test eax, eax
        je   cc_free
        mov  edi, eax
        call app_handle
        push eax
        mov  edx, {V['OpenClipboard']:#x}
        call vclptr
        call eax
        test eax, eax
        je   cc_free
        push ebp
        push edi
        mov  edx, {V['SetClipboardData']:#x}
        call vclptr
        call eax
        mov  edi, eax
        mov  edx, {V['CloseClipboard']:#x}
        call vclptr
        call eax
        test edi, edi
        je   cc_free
        push ebp
        call getG
        mov  ebp, eax
        mov  dword ptr [ebp + {G_ROT}], 0     ; a fresh copy starts unrotated
        call load_positions
        mov  eax, dword ptr [ebp + {G_VALID}]
        mov  dword ptr [ebp + {G_GHOST}], eax
        pop  ebp
        jmp  cc_ret
cc_free:
        push ebp
        mov  edx, {V['GlobalFree']:#x}
        call vclptr
        call eax
cc_ret:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

cave_pfc:
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        call {F['PasteFromClipboard']:#x}
        call getG
        mov  ebp, eax
        mov  dword ptr [ebp + {G_GHOST}], 0   ; the paste consumes the ghost
        call load_positions
        cmp  dword ptr [ebp + {G_VALID}], 0
        je   pf_ret
        mov  eax, ebx
        call {F['CC_GetCount']:#x}
        cmp  eax, dword ptr [ebp + {G_COUNT}]
        je   pf_ret
        mov  dword ptr [ebp + {G_VALID}], 0   ; stream and position block disagree -> vanilla paste
pf_ret:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

cave_place:
        push ebp
        push esi
        push edi
        push eax
        push edx
        push ecx
        call getG
        mov  ebp, eax
        cmp  dword ptr [ebp + {G_VALID}], 0
        je   cp_vanilla
        cmp  ebx, dword ptr [ebp + {G_COUNT}]
        jae  cp_vanilla
        mov  eax, dword ptr [esp]
        sub  eax, 8
        sar  eax, 5
        mov  esi, eax
        and  eax, 1
        shl  eax, 4
        mov  edx, dword ptr [esp + 0x20]
        sub  edx, eax
        sar  edx, 5
        mov  eax, esi
        and  eax, 1
        mov  ecx, esi
        sub  ecx, eax
        sar  ecx, 1
        sub  edx, ecx
        movzx eax, word ptr [ebp + ebx*4 + {POS:#x}]
        and  eax, {XMASK:#x}
        movsx edi, word ptr [ebp + ebx*4 + {POS + 2:#x}]
        mov  ecx, eax
        and  ecx, 1
        neg  ecx
        add  ecx, eax
        sar  ecx, 1
        sub  edi, ecx
        sub  eax, dword ptr [ebp + {G_AX}]
        sub  edi, dword ptr [ebp + {G_AR}]
        push ebx
        call rot_delta
        pop  ebx
        add  esi, eax
        add  edx, edi
        mov  eax, esi
        and  eax, 1
        mov  ecx, esi
        sub  ecx, eax
        sar  ecx, 1
        add  edx, ecx
        mov  eax, dword ptr [esp + 8]
        mov  eax, dword ptr [eax + 0x10]
        test esi, esi
        jl   cp_fail
        test edx, edx
        jl   cp_fail
        cmp  esi, dword ptr [eax + 0xc]
        jge  cp_fail
        cmp  edx, dword ptr [eax + 0x10]
        jge  cp_fail
        mov  eax, esi
        shl  eax, 5
        add  eax, 0x18
        mov  dword ptr [esp], eax
        mov  eax, esi
        and  eax, 1
        shl  eax, 4
        shl  edx, 5
        add  edx, eax
        add  edx, 0x10
        mov  dword ptr [esp + 0x20], edx
cp_vanilla:
        pop  ecx
        pop  edx
        pop  eax
        pop  edi
        pop  esi
        pop  ebp
        jmp  {F['HSMap_Place']:#x}
cp_fail:
        add  esp, 0xc
        pop  edi
        pop  esi
        pop  ebp
        xor  eax, eax
        ret  8

cave_ss:
        push eax
        mov  edx, eax
        mov  eax, dword ptr [esp + 0x18]
        mov  eax, dword ptr [eax + 0x10]
        call {F['TList_IndexOf']:#x}
        test eax, eax
        pop  eax
        jl   ss_group
        mov  eax, dword ptr [eax]
        call dword ptr [eax + 0xe8]
        jmp  {SS_RESUME:#x}
ss_group:
        mov  ecx, dword ptr [esp]
        call group_glow
        jmp  {SS_SKIP:#x}

cave_preview:                                 ; eax = THSMEdit; tail-jumps to ShowSelection
        pushal
        mov  esi, eax
        call getG
        mov  ebp, eax
        mov  dword ptr [ebp + {G_SELF}], esi
        call ensure_lib
        call ensure_subclass
        cmp  dword ptr [ebp + {G_LIB}], 0
        je   pv_done
        cmp  dword ptr [ebp + {G_GHOST}], 0
        je   pv_done
        cmp  dword ptr [ebp + {G_VALID}], 0
        je   pv_done
        cmp  dword ptr [ebp + {G_NHEX}], 2    ; one hex has no shape to preview
        jb   pv_done
        mov  eax, dword ptr [esi + 0x1c0]
        mov  edi, dword ptr [eax + 0x3c]
        mov  eax, dword ptr [edi + 0xc]
        call {F['MM_GetXhx']:#x}
        cmp  eax, -1
        je   pv_done
        push eax                              ; [esp] = cursor hx
        mov  eax, dword ptr [edi + 0xc]
        call {F['MM_GetYhx']:#x}
        cmp  eax, -1
        je   pv_pop
        push eax                              ; [esp] = cursor hy, [esp+4] = cursor hx
        mov  eax, dword ptr [esp + 4]
        mov  edi, eax
        and  edi, 1
        sub  eax, edi
        sar  eax, 1
        mov  edi, dword ptr [esp]
        sub  edi, eax                         ; edi = cursor cube r
        push edi                              ; [esp] = dest r, [+4] = hy, [+8] = hx
        xor  ebx, ebx
pv_loop:
        cmp  ebx, dword ptr [ebp + {G_COUNT}]
        jae  pv_end
        movzx eax, word ptr [ebp + ebx*4 + {POS:#x}]
        test eax, {HEXFLAG:#x}
        je   pv_next
        and  eax, {XMASK:#x}
        movsx edi, word ptr [ebp + ebx*4 + {POS + 2:#x}]
        mov  ecx, eax
        and  ecx, 1
        neg  ecx
        add  ecx, eax
        sar  ecx, 1
        sub  edi, ecx                         ; edi = source cube r
        sub  eax, dword ptr [ebp + {G_AX}]
        sub  edi, dword ptr [ebp + {G_AR}]
        call rot_delta
        add  eax, dword ptr [esp + 8]         ; + dest q
        add  edi, dword ptr [esp]             ; + dest r
        mov  ecx, eax
        and  ecx, 1
        neg  ecx
        add  ecx, eax
        sar  ecx, 1
        add  edi, ecx                         ; back to offset y
        test eax, eax
        jl   pv_next
        test edi, edi
        jl   pv_next
        mov  edx, edi
        call draw_glow
pv_next:
        inc  ebx
        jmp  pv_loop
pv_end:
        add  esp, 8
pv_pop:
        add  esp, 4
pv_done:
        popal
        jmp  {F['ShowSelection']:#x}


"""


def build_body(base_va, V):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code_va = base_va + CODE

    def assemble(wnd_off):
        src = gen_src(base_va, V, wnd_off)
        txt = "\n".join(ln.split(";", 1)[0] for ln in src.splitlines())
        enc, _ = ks.asm(txt, code_va)
        return txt, bytes(enc)

    # ensure_subclass has to push cave_wndproc's runtime address, which is only known once the
    # cave is laid out. Two passes: the placeholder is >0x7F so both encode as `add eax, imm32`
    # and the second pass cannot shift anything (asserted).
    clean, code = assemble(0x1000)
    pre, _ = ks.asm(clean.split("\ncave_wndproc:", 1)[0], code_va)
    clean, code2 = assemble(CODE + len(pre))
    assert len(code2) == len(code), "the wndproc fixup changed the cave length"
    code = code2
    assert code[:10] == bytes.fromhex("e800000000582d") + struct.pack("<I", CODE + 5)[:3], \
        f"getG prologue is not call/pop/sub imm32: {code[:12].hex()}"
    assert CODE + len(code) <= POS, f"code ({len(code)}B) overruns the position buffer"
    labels = {}
    for name in ("cave_seladd", "cave_md", "cave_copy", "cave_pfc", "cave_place", "cave_ss",
                 "cave_preview", "cave_wndproc", "cave_esc"):
        # locate each entry by assembling the prefix up to its label
        head = clean.split(f"\n{name}:", 1)[0]
        pre, _ = ks.asm(head, code_va)
        labels[name] = code_va + len(pre)
    body = bytearray(CODE)
    body[S_FMT:S_FMT + len(FMT_NAME)] = FMT_NAME
    gen = b"GENERAL.ILB"
    body[S_GEN - 8:S_GEN] = struct.pack("<iI", -1, len(gen))       # static AnsiString header
    body[S_GEN:S_GEN + len(gen) + 1] = gen + b"\0"
    names = b"".join(bytes([len(n)]) + n for n in (b"TUnitHS", b"TCity", b"TFlagEvent",
                                                    b"TMoveOnEvent")) + b"\0"
    body[S_NAMES:S_NAMES + len(names)] = names
    assert S_NAMES + len(names) <= S_ROT and S_FMT + len(FMT_NAME) <= S_GEN - 8
    for k in range(6):                      # six static AnsiStrings, refcount -1 => never freed
        txt = b"Paste rotation %d" % (k * 60)
        at = S_ROT + k * ROTSTR
        body[at:at + 8] = struct.pack("<iI", -1, len(txt))
        body[at + 8:at + 8 + len(txt) + 1] = txt + b"\0"
        assert 8 + len(txt) + 1 <= ROTSTR
    assert S_ROT + 6 * ROTSTR <= CODE
    body += code
    return bytes(body), labels, code


def hook_bytes(labels):
    out = {H1_VA: b"\xE9" + struct.pack("<i", labels["cave_md"] - (H1_VA + 5)) + b"\x90\x90",
           H6_VA: b"\xE9" + struct.pack("<i", labels["cave_ss"] - (H6_VA + 5)) + b"\x90\x90\x90",
           ESC_VA: b"\xE9" + struct.pack("<i", labels["cave_esc"] - (ESC_VA + 5)) + b"\x90\x90",
           SELLOC_VA: SELLOC_NEW, **{va: CUT_NEW for va in CUT_SITES}}
    tgt = {0x55613151: "cave_copy", 0x5561302E: "cave_copy", 0x5561322D: "cave_pfc",
           0x5561329E: "cave_place", 0x5560BAAB: "cave_seladd",
           PREVIEW_VA: "cave_preview"}
    for va, lab in tgt.items():
        out[va] = b"\xE8" + struct.pack("<i", labels[lab] - (va + 5))
    return out


def orig_bytes():
    out = {H1_VA: H1_ORIG, H6_VA: H6_ORIG, ESC_VA: ESC_ORIG, SELLOC_VA: SELLOC_ORIG,
           **{va: CUT_ORIG for va in CUT_SITES}}
    for va, t in CALL_SITES.items():
        out[va] = b"\xE8" + struct.pack("<i", t - (va + 5))
    return out


# ---- ILB: purple copies of the 3-D hex selector -------------------------------------------------
def purple(v, tr):
    if v == tr:
        return v
    r5, g6, b5 = (v >> 11) & 31, (v >> 5) & 63, v & 31
    h, s, val = colorsys.rgb_to_hsv(r5 / 31, g6 / 63, b5 / 31)
    R, G, B = colorsys.hsv_to_rgb((h + HUE_SHIFT) % 1.0, s, val)
    out = (round(R * 31) << 11) | (round(G * 63) << 5) | round(B * 31)
    return out ^ 1 if out == tr else out


def ilb_state(data):
    r = ilbmod.parse(data)
    ids = {im["id"]: im for im in r["images"]}
    return r, ids


def ilb_payload(data, r, src):
    cw, ch, cx, cy, tr = src["s16"]
    assert src["size"] == cw * ch * 2, "Sprite16 size is not clipw*cliph*2"
    at = r["hdr"]["imgdir"] + src["offset"]
    px = struct.unpack_from("<%dH" % (cw * ch), data, at)
    return struct.pack("<%dH" % (cw * ch), *(purple(v, tr) for v in px))


def ilb_add(data):
    """-> new bytes with ids 60/61 present and current, or None if already correct."""
    r, ids = ilb_state(data)
    want = {ID_BACK: ilb_payload(data, r, ids[SRC_BACK]), ID_FRONT: ilb_payload(data, r, ids[SRC_FRONT])}
    if ID_BACK in ids or ID_FRONT in ids:
        assert ID_BACK in ids and ID_FRONT in ids, "only one of ids 60/61 present -- refusing"
        out = bytearray(data)
        for iid, pay in want.items():
            at = r["hdr"]["imgdir"] + ids[iid]["offset"]
            assert ids[iid]["size"] == len(pay)
            out[at:at + len(pay)] = pay
        return None if bytes(out) == data else bytes(out)
    imgdir, filelen = r["hdr"]["imgdir"], r["hdr"]["filelen"]
    assert filelen == len(data) and data[imgdir - 4:imgdir] == b"\xff\xff\xff\xff"
    order = sorted(im["dir_off"] for im in r["images"])
    after8 = [o for o in order if o > ids[8]["dir_off"]]
    insert_at = after8[0]                          # right after id 8: inside the parseable prefix
    recs, payload = bytearray(), bytearray()
    for new_id, src_id in ((ID_BACK, SRC_BACK), (ID_FRONT, SRC_FRONT)):
        src = ids[src_id]
        nxt = min(o for o in order if o > src["dir_off"])
        rec = bytearray(data[src["dir_off"]:nxt])
        nlen = len(src["name"])
        o_size, o_off = 13 + nlen + 21, 13 + nlen + 25
        assert struct.unpack_from("<I", rec, 0)[0] == src_id
        assert struct.unpack_from("<I", rec, o_size)[0] == src["size"]
        assert struct.unpack_from("<I", rec, o_off)[0] == src["offset"]
        struct.pack_into("<I", rec, 0, new_id)
        struct.pack_into("<I", rec, o_off, filelen - imgdir + len(payload))
        recs += rec
        payload += want[new_id]
    n = len(recs)
    out = bytearray(data)
    out[insert_at:insert_at] = recs
    struct.pack_into("<I", out, 16, imgdir + n)
    out += payload
    struct.pack_into("<I", out, 20, len(out))
    assert bytes(out[imgdir + n:filelen + n]) == data[imgdir:filelen], "pixel data moved"
    r2, ids2 = ilb_state(bytes(out))
    for i, im in ids.items():
        a = {k: v for k, v in im.items() if k not in ("idx", "dir_off")}
        b = {k: v for k, v in ids2[i].items() if k not in ("idx", "dir_off")}
        assert a == b, f"image id {i} changed"
    for iid in want:
        im = ids2[iid]
        at = r2["hdr"]["imgdir"] + im["offset"]
        assert bytes(out[at:at + im["size"]]) == want[iid]
    return bytes(out)


def ilb_remove(data):
    r, ids = ilb_state(data)
    if ID_BACK not in ids and ID_FRONT not in ids:
        return None
    imgdir, filelen = r["hdr"]["imgdir"], r["hdr"]["filelen"]
    a, b = ids[ID_BACK], ids[ID_FRONT]
    order = sorted(im["dir_off"] for im in r["images"])
    assert b["dir_off"] == min(o for o in order if o > a["dir_off"]), "ids 60/61 not adjacent"
    end = min(o for o in order if o > b["dir_off"])
    n = end - a["dir_off"]
    tail = a["size"] + b["size"]
    assert a["offset"] == filelen - imgdir - tail and b["offset"] == a["offset"] + a["size"], \
        "ids 60/61 pixel data is not the file tail -- something was appended later; refusing"
    out = bytearray(data[:filelen - tail])
    del out[a["dir_off"]:end]
    struct.pack_into("<I", out, 16, imgdir - n)
    struct.pack_into("<I", out, 20, len(out))
    return bytes(out)


# ---- main ----------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--disasm", action="store_true", help="print the whole cave")
    a = ap.parse_args()

    d = bytearray(open(DLL, "rb").read())
    P = load_pe(d)
    assert P["base"] == PREF_BASE
    imps = import_slots(d, P)
    for th, name in THUNKS.items():
        o = v2o(P, th)
        assert d[o:o + 2] == b"\xFF\x25", f"{th:#x} is not a jmp [IAT] thunk"
        got = imps.get(struct.unpack_from("<I", d, o + 2)[0], "?")
        assert bare(got) == name, f"thunk {th:#x} -> {got}, expected {name}"
    got = imps.get(SLOT_INDEXOF, "?")
    assert bare(got) == "Classes.TList.IndexOf", got
    for va, head in FUNC_HEADS.items():
        if head:
            o = v2o(P, va)
            assert bytes(d[o:o + len(head) // 2]).hex() == head, f"function head {va:#x} differs"
    for va, want in CHECKS.items():
        o = v2o(P, va)
        assert bytes(d[o:o + len(want)]) == want, f"anchor {va:#x} differs"
    for vmt in (VMT_AHEX, VMT_HPB):
        assert struct.unpack_from("<I", d, v2o(P, vmt - 0x40))[0] == vmt, f"{vmt:#x} is not a VMT"
    assert struct.unpack_from("<I", d, v2o(P, 0x5562E304))[0] == HSEDMOD_VAR
    rel = relocs(d, P)
    for va, ob in orig_bytes().items():
        hit = [r for r in rel if va - 3 <= r < va + len(ob)]
        assert not hit, f"hook {va:#x} overlaps .reloc entries {[hex(h) for h in hit]}"

    V = vcl_facts()
    sec = next((s for s in P["secs"] if s["name"] == SECT_NAME), None)
    last = P["secs"][-1]
    newva = sec["va"] if sec else align(last["va"] + max(last["vsz"], last["rsz"]), P["salign"])
    base_va = PREF_BASE + newva
    body, labels, code = build_body(base_va, V)
    patched, orig = hook_bytes(labels), orig_bytes()
    vsz = POS + MAXN * 4

    state = {}
    for va in orig:
        o = v2o(P, va)
        cur = bytes(d[o:o + len(orig[va])])
        into_hxg = bool(sec) and len(cur) >= 5 and cur[0] in (0xE8, 0xE9) and \
            cur[5:] == patched[va][5:] and \
            base_va <= va + 5 + struct.unpack("<i", cur[1:5])[0] < base_va + sec["vsz"]
        state[va] = ("orig" if cur == orig[va] else "ours" if cur == patched[va] else
                     "stale" if into_hxg else "OTHER")      # stale = an older build of this cave
    body_ok = bool(sec) and bytes(d[sec["raw"]:sec["raw"] + len(body)]) == body
    print(f"[HSEPack.dpl] .hxg {'present' if sec else 'absent'} at VA {base_va:#x}; code {len(code)}B; "
          f"body {'current' if body_ok else 'differs' if sec else '-'}")
    for va in sorted(orig):
        print(f"    {va:#x}: {state[va]}")
    for p in ILBS:
        _, ids = ilb_state(open(p, "rb").read())
        print(f"[{os.path.basename(p)}] ids 60/61: {'present' if ID_BACK in ids else 'absent'}")
    if "OTHER" in state.values():
        sys.exit("a hook site holds bytes that are neither vanilla nor ours -- refusing")

    if a.disasm or not (a.apply or a.undo):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        cs = Cs(CS_ARCH_X86, CS_MODE_32)
        if a.disasm:
            for i in cs.disasm(code, base_va + CODE):
                print(f"  {i.address:08X}  {i.mnemonic:7s} {i.op_str}")
        for k, v in labels.items():
            print(f"    {k:11s} {v:#x}")
        if not (a.apply or a.undo):
            print("dry run -- re-run with --apply to write, --undo to revert")
            return 0

    if a.undo:
        for va, ob in orig.items():
            o = v2o(P, va)
            d[o:o + len(ob)] = ob
        if sec:
            assert sec is P["secs"][-1], ".hxg is not the last section -- refusing to drop it"
            assert sec["raw"] + sec["rsz"] == len(d), "data after .hxg -- refusing"
            del d[sec["raw"]:]
            d[sec["hdr"]:sec["hdr"] + 40] = b"\0" * 40
            struct.pack_into("<H", d, P["e"] + 6, P["nsec"] - 1)
            struct.pack_into("<I", d, P["opt"] + 56, sec["va"])
        writes = [(DLL, bytes(d))]
        for p in ILBS:
            nd = ilb_remove(open(p, "rb").read())
            if nd:
                writes.append((p, nd))
    elif body_ok and set(state.values()) == {"ours"} and \
            not any(ilb_add(open(p, "rb").read()) for p in ILBS):
        print("already applied and up to date -- no-op")
        return 0
    else:
        if sec:
            assert sec is P["secs"][-1], ".hxg is not the last section -- refusing to rewrite"
            rawsz = align(len(body), P["falign"])
            d = d[:sec["raw"]] + bytearray(body) + bytearray(rawsz - len(body))
            struct.pack_into("<II", d, sec["hdr"] + 8, vsz, sec["va"])
            struct.pack_into("<II", d, sec["hdr"] + 16, rawsz, sec["raw"])
        else:
            assert P["sectbl"] + (P["nsec"] + 1) * 40 <= P["hdrsz"], "no header room for a section"
            assert last["raw"] + last["rsz"] == len(d), "file has an overlay -- refusing"
            newraw = align(len(d), P["falign"])
            d += b"\0" * (newraw - len(d))
            rawsz = align(len(body), P["falign"])
            d += body + b"\0" * (rawsz - len(body))
            b = P["sectbl"] + P["nsec"] * 40
            struct.pack_into("<8sIIII", d, b, SECT_NAME, vsz, newva, rawsz, newraw)
            struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)
            struct.pack_into("<H", d, P["e"] + 6, P["nsec"] + 1)
        struct.pack_into("<I", d, P["opt"] + 56, align(newva + vsz, P["salign"]))
        for va, pb in patched.items():
            o = v2o(load_pe(d), va)
            d[o:o + len(pb)] = pb
        writes = [(DLL, bytes(d))]
        for p in ILBS:
            nd = ilb_add(open(p, "rb").read())
            if nd:
                writes.append((p, nd))

    for p, blob in writes:
        try:
            open(p, "wb").write(blob)
        except PermissionError:
            sys.exit(f"LOCKED: {p} -- close every AoW binary and retry")
        print(f"    wrote {os.path.relpath(p, GAME)} ({len(blob)} bytes)")
    print("undone" if a.undo else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
