#!/usr/bin/env python3
r"""
AoW1 editor MENU TOOLBAR ROWS + START MAXIMIZED  --  binary patch for
AoWDevEd.exe (DFM resource edit, no code changes).

WHAT IT DOES
  Adds two always-visible toolbar rows under the existing icon toolbar, exposing
  (nearly) every menu sub-option as a captioned flat button, grouped and
  labelled by the menu it lives in:
    Row 1:  File | New Open Save "Save As"
            Edit | Cut Copy Paste Delete
            Options | "Map Settings" "Player Info" Scanner "Remove Level"
                      "Add Level"   Preview: 640 800 1024 1280
    Row 2:  Developer | "New Combat Map" "New Mapset" "Open Mapset"
                        "Game Settings" "Mapset Settings" "Edit Map Text"
                        "Export Text" "Import Text" Multilizer "Debug Mode"
                        "Fog of War" "Export Abilities" "Remove Leaders"
            Help | About
  The category names (File/Edit/Options/Preview/Developer/Help) are UNDERLINED
  TLabels so they read as section headers, not buttons.
  Also sets the main form to open MAXIMIZED (WindowState=wsMaximized) --
  useful on a 4K screen (the default was a 916x696 centered window) -- and adds
  a Ctrl+S ShortCut to the File>Save menu item (it had none), so Ctrl+S saves
  from anywhere in the editor (KeyPreview is on).
  Skipped on purpose: File>Close and File>Exit (misclick risk), Players menu
  (built at runtime, per-map), the Preview-mode CHECK state and Debug/Fog/Scanner
  check marks (buttons fire the same handlers; the check state still shows in the
  menus, which remain fully functional).

HOW
  Delphi forms are DFM resources (RCDATA "TMAINFORM", a serialized component
  tree). Event handlers in a DFM are resolved BY NAME against the form's
  published method table at load time, so new components can be wired to
  EXISTING handlers with zero new code. The injected classes (TPanel,
  TSpeedButton, TLabel) are all in TMainForm's streaming class table, so
  TReader can instantiate them. All 32 handler names were verified against
  TMainForm's published method table; every exposed handler either self-guards
  (checks map-loaded etc. -- verified in disasm) or is exactly as reachable
  from the always-enabled menu today.

  The enlarged DFM cannot fit in place, so:
    - the new blob is written to a new PE section ".mtb"
    - the IMAGE_RESOURCE_DATA_ENTRY for TMAINFORM (located dynamically by
      walking .rsrc) gets its OffsetToData/Size repointed to the new section
  The original blob stays in .rsrc as dead data. Layout notes: the new panels
  are alTop with Top=50/82 so the VCL stacks them under the existing Panel2
  (Top=0); Panel1 is alClient and reflows automatically.

CONVENTIONS: dry-run by default; --apply to write; idempotent; verifies the
DFM parses and the marker is absent before writing; auto-backup to
`<game dir>\backups\AoWDevEd.exe.pre-modtoolbar`. Close the editor before --apply.
Revert: NOT by snapshot -- a .pre-modtoolbar restore is a WHOLE-FILE copy, so it drops every other
AoWDevEd feature (terrainpal, valgoto, partyrnd, timerres, dlgdirs, coppermedal). There is no --undo
here: undo surgically, or to re-tune the toolbar rewrite the DFM in place rather than reverting to
clear the .mtb marker.
⚠ build_deved_terrainpal.py reads whatever DFM the resource entry currently points at, so it must
run AFTER this script.

Usage:
  python build_editor_toolbar.py                # dry-run, prints layout
  python build_editor_toolbar.py --apply
  python build_editor_toolbar.py --no-maximize  # skip WindowState change
"""
import argparse, os, shutil, struct, sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE  = "AoWDevEd.exe"
BACKUP_SUFFIX = ".pre-modtoolbar"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
SECT_NAME = b".mtb\0\0\0\0"
MARKER = b"MBRowA"          # a component name only this patch creates

# ---- the toolbar definition ----------------------------------------------------
# (label, [(name, caption, hint, handler), ...])  hint = menu path (tooltip)
ROW_A = [
    ("File", [
        ("MBNew",       "New",          "File > New",             "NewItemClick"),
        ("MBOpen",      "Open",         "File > Open",            "OpenBtnClick"),
        ("MBSave",      "Save",         "File > Save",            "SaveBtnClick"),
        ("MBSaveAs",    "Save As",      "File > Save As...",      "SaveAsItemClick"),
    ]),
    ("Edit", [
        ("MBCut",       "Cut",          "Edit > Cut (Ctrl+X)",    "CutItemClick"),
        ("MBCopy",      "Copy",         "Edit > Copy (Ctrl+C)",   "CopyItemClick"),
        ("MBPaste",     "Paste",        "Edit > Paste (Ctrl+V)",  "PasteItemClick"),
        ("MBDelete",    "Delete",       "Edit > Delete (Del)",    "DeleteItemClick"),
    ]),
    ("Options", [
        ("MBMapSettings",  "Map Settings", "Options > Map Settings",     "MapSettingsClick"),
        ("MBPlayerInfo",   "Player Info",  "Options > Player Info",      "PlayerInfoClick"),
        ("MBScanner",      "Scanner",      "Options > Scanner (toggle)", "ScannerItemClick"),
        ("MBRemLevel",     "Remove Level", "Options > Remove Map Level", "RemoveMapLevelClick"),
        ("MBAddLevel",     "Add Level",    "Options > Add Map Level",    "AddMapLevelClick"),
    ]),
    ("Preview", [
        ("MBPrev640",   "640",  "Options > Preview Mode > 640x480",   "N640x480Click"),
        ("MBPrev800",   "800",  "Options > Preview Mode > 800x600",   "N800x600Click"),
        ("MBPrev1024",  "1024", "Options > Preview Mode > 1024x768",  "N1024x768Click"),
        ("MBPrev1280",  "1280", "Options > Preview Mode > 1280x1024", "N1280x1024Click"),
    ]),
]
ROW_B = [
    ("Developer", [
        ("MBNewCombat",      "New Combat Map",   "Developer > New Combat Map",    "NewCombatMapClick"),
        ("MBNewMapset",      "New Mapset",       "Developer > New Mapset",        "NewMapsetClick"),
        ("MBOpenMapset",     "Open Mapset",      "Developer > Open Mapset",       "OpenMapsetClick"),
        ("MBGameSettings",   "Game Settings",    "Developer > Game Settings",     "GameSettingsClick"),
        ("MBMapsetSettings", "Mapset Settings",  "Developer > Mapset Settings",   "MapSetSettingsClick"),
        ("MBEditMapText",    "Edit Map Text",    "Developer > Edit Map Text",     "MapTextEditorMIClick"),
        ("MBExportText",     "Export Text",      "Developer > Export Text",       "ExportTextClick"),
        ("MBImportText",     "Import Text",      "Developer > Import Text",       "ImportTextClick"),
        ("MBMultilizer",     "Multilizer",       "Developer > Export for Multilizer", "ExportForMultilizerClick"),
        ("MBDebugMode",      "Debug Mode",       "Developer > Debug Mode (toggle)",   "DebugModeClick"),
        ("MBFogOfWar",       "Fog of War",       "Developer > Fog of War (toggle)",   "FogofWarClick"),
        ("MBExportAbil",     "Export Abilities", "Developer > Export Ability Info",   "ExportAbilityInfoClick"),
        ("MBRemLeaders",     "Remove Leaders",   "Developer > Remove Leaders",        "RemoveLeadersMIClick"),
    ]),
    ("Help", [
        ("MBAbout",     "About",        "Help > About",           "About1Click"),
    ]),
]

PANEL_H   = 31          # toolbar row height
BTN_H, BTN_TOP = 23, 4
LAB_TOP   = 9
CHAR_W    = 6           # approx px/char @ MS Sans Serif -10
GROUP_GAP = 22
BTN_GAP   = 2

# ---- DFM primitives ------------------------------------------------------------
def ss(s):
    b = s.encode("latin1")
    assert len(b) < 256
    return bytes([len(b)]) + b

def v_int(n):
    if -128 <= n <= 127:   return b"\x02" + struct.pack("<b", n)
    if -32768 <= n <= 32767: return b"\x03" + struct.pack("<h", n)
    return b"\x04" + struct.pack("<i", n)

def v_str(s):   return b"\x06" + ss(s)
def v_ident(s): return b"\x07" + ss(s)
def v_bool(b):  return b"\x09" if b else b"\x08"
def v_set(items):  # vaSet: shortstrings terminated by an empty shortstring
    return b"\x0B" + b"".join(ss(i) for i in items) + b"\x00"

# Category labels get an underlined copy of the form font so they read as
# section headers, not clickable buttons.  (Set only Style + ParentFont=False;
# Height/Name/Charset/Color replicate the form font so size is unchanged.)
def label_font_props():
    return (prop("Font.Charset", v_ident("DEFAULT_CHARSET")) +
            prop("Font.Color",   v_ident("clWindowText")) +
            prop("Font.Height",  v_int(-10)) +
            prop("Font.Name",    v_str("MS Sans Serif")) +
            prop("Font.Style",   v_set(["fsUnderline"])) +
            prop("ParentFont",   v_bool(False)))

def prop(name, val): return ss(name) + val

def obj(cls, name, props, children=b""):
    return ss(cls) + ss(name) + props + b"\x00" + children + b"\x00"

def build_row(panel_name, top, groups):
    """Return (dfm_bytes, layout_lines)."""
    kids = b""
    lay = []
    x = 6
    for label, buttons in groups:
        lw = CHAR_W * len(label) + 4
        kids += obj("TLabel", f"MBLab{panel_name}{label}",
                    prop("Left", v_int(x)) + prop("Top", v_int(LAB_TOP)) +
                    prop("Width", v_int(lw)) + prop("Height", v_int(13)) +
                    prop("Caption", v_str(label)) + label_font_props())
        x += lw + 6
        for name, caption, hint, handler in buttons:
            bw = max(34, CHAR_W * len(caption) + 14)
            kids += obj("TSpeedButton", name,
                        prop("Left", v_int(x)) + prop("Top", v_int(BTN_TOP)) +
                        prop("Width", v_int(bw)) + prop("Height", v_int(BTN_H)) +
                        prop("Caption", v_str(caption)) +
                        prop("Hint", v_str(hint)) +
                        prop("Flat", v_bool(True)) +
                        prop("OnClick", v_ident(handler)))
            lay.append(f"      [{x:4}] {caption:<18} -> {handler}")
            x += bw + BTN_GAP
        x += GROUP_GAP
    panel = obj("TPanel", panel_name,
                prop("Left", v_int(0)) + prop("Top", v_int(top)) +
                prop("Width", v_int(916)) + prop("Height", v_int(PANEL_H)) +
                prop("Align", v_ident("alTop")) +
                prop("BevelOuter", v_ident("bvNone")) +
                prop("ParentShowHint", v_bool(False)) +
                prop("ShowHint", v_bool(True)),
                kids)
    lay.insert(0, f"    {panel_name}: Top={top} H={PANEL_H} total width ~{x}px")
    return panel, lay

# ---- DFM parser (offset-tracking; subset needed for TMainForm) ------------------
class DfmParser:
    def __init__(self, data):
        self.d = data
    def rstr(self, o):
        n = self.d[o]; return self.d[o+1:o+1+n].decode("latin1"), o+1+n
    def value(self, o):
        d = self.d
        vt = d[o]; o += 1
        if vt == 0:  return o
        if vt == 2:  return o+1
        if vt == 3:  return o+2
        if vt == 4:  return o+4
        if vt == 5:  return o+10
        if vt in (6, 7):
            _, o = self.rstr(o); return o
        if vt in (8, 9, 13): return o
        if vt == 10: return o + 4 + struct.unpack_from("<I", d, o)[0]
        if vt == 11:
            while True:
                s, o = self.rstr(o)
                if s == "": return o
        if vt == 1:
            while d[o] != 0: o = self.value(o)
            return o+1
        if vt == 12: return o + 4 + struct.unpack_from("<I", d, o)[0]
        if vt == 15: return o+4
        if vt in (16, 17): return o+8
        if vt == 18: return o + 4 + 2*struct.unpack_from("<I", d, o)[0]
        if vt == 14:
            while d[o] != 0:
                if d[o] in (2, 3, 4): o = self.value(o)
                assert d[o] == 1
                o += 1
                while d[o] != 0:
                    _, o = self.rstr(o)
                    o = self.value(o)
                o += 1
            return o+1
        raise ValueError(f"valuetype {vt} @ {o-1:#x}")
    def obj(self, o):
        """Return dict(cls,name,start,prop_end,children=[child dicts],end)."""
        d = self.d
        start = o
        if (d[o] & 0xF0) == 0xF0:
            o += 1
            if d[start] & 0x02: o = self.value(o)
        cls, o = self.rstr(o)
        name, o = self.rstr(o)
        while True:
            pn, o2 = self.rstr(o)
            if pn == "":
                prop_end = o      # offset of the 0x00 props terminator
                o = o2
                break
            o = self.value(o2)
        children = []
        while d[o] != 0:
            c = self.obj(o)
            children.append(c)
            o = c["end"]
        return dict(cls=cls, name=name, start=start, prop_end=prop_end,
                    children=children, end=o+1)

def find_node(node, name):
    """Depth-first search for a component by name; returns its node dict or None."""
    for c in node["children"]:
        if c["name"] == name:
            return c
        r = find_node(c, name)
        if r:
            return r
    return None

# ---- PE helpers -----------------------------------------------------------------
def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    opt = e+24
    sectbl = opt+optsz
    secs = []
    for i in range(nsec):
        b = sectbl+i*40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt,
                salign=struct.unpack_from('<I', d, opt+32)[0],
                falign=struct.unpack_from('<I', d, opt+36)[0],
                sectbl=sectbl, secs=secs)

def align(x, a): return (x + a - 1) // a * a

def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError(hex(rva))

def find_tmainform_entry(d, F):
    """Walk .rsrc; return (file_off_of_data_entry, data_rva, data_size)."""
    rsrc_rva, _ = struct.unpack_from("<II", d, F["opt"] + 96 + 2*8)
    ro = rva2off(F["secs"], rsrc_rva)
    def name_at(v):
        off = ro + (v & 0x7FFFFFFF)
        n = struct.unpack_from("<H", d, off)[0]
        return d[off+2:off+2+2*n].decode("utf-16le")
    hits = []
    def walk(diroff, path):
        nn, ni = struct.unpack_from("<HH", d, ro + diroff + 12)
        for i in range(nn + ni):
            eo = ro + diroff + 16 + i*8
            nm, off = struct.unpack_from("<II", d, eo)
            label = name_at(nm) if nm & 0x80000000 else f"#{nm}"
            if off & 0x80000000:
                walk(off & 0x7FFFFFFF, path + [label])
            elif "TMAINFORM" in (p.upper() for p in path + [label]):
                drva, dsize = struct.unpack_from("<II", d, ro + off)
                hits.append((ro + off, drva, dsize))
    walk(0, [])
    assert len(hits) == 1, f"TMAINFORM data entries found: {len(hits)}"
    return hits[0]

# ---- main -----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-maximize", action="store_true",
                    help="do not add WindowState=wsMaximized")
    args = ap.parse_args()

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)

    if any(bytes(d[s[4]:s[4]+4]) == SECT_NAME[:4] for s in F["secs"]):
        print(f"[{EXE}] already patched (.mtb section present) - idempotent no-op")
        return

    entry_off, dfm_rva, dfm_size = find_tmainform_entry(d, F)
    dfm_off = rva2off(F["secs"], dfm_rva)
    blob = bytes(d[dfm_off:dfm_off+dfm_size])
    assert blob[:4] == b"TPF0", "TMAINFORM resource does not start with TPF0"
    if MARKER in blob:
        print(f"[{EXE}] marker already in DFM - no-op"); return

    P = DfmParser(blob)
    root = P.obj(4)
    assert root["cls"] == "TMainForm", root["cls"]
    kidmap = {c["name"]: c for c in root["children"]}
    assert "Panel2" in kidmap, "Panel2 (existing toolbar) not found"
    p2_end = kidmap["Panel2"]["end"]

    # Ctrl+S on the File>Save menu item.  ShortCut is a Word: low byte = VK,
    # high byte = shift flags; scCtrl=0x4000, 'S'=0x53 -> 0x4053 = 16467.
    save_item = find_node(root, "SaveItem")
    assert save_item is not None, "SaveItem menu item not found"
    if b"ShortCut" in blob[save_item["start"]:save_item["end"]]:
        # already present (older SaveItem never had one, but stay safe)
        shortcut = b""
    else:
        shortcut = prop("ShortCut", v_int(16467))
    # SaveItem lives in the menu, which streams AFTER Panel2 -> higher offset;
    # splicing there first keeps the lower Panel2/root offsets valid.
    assert save_item["prop_end"] > p2_end, "unexpected DFM order"

    rowA, layA = build_row("MBRowA", 50, ROW_A)
    rowB, layB = build_row("MBRowB", 82, ROW_B)
    inject = rowA + rowB

    print(f"[{EXE}] TMAINFORM: rva 0x{dfm_rva:X} size 0x{dfm_size:X} "
          f"(file 0x{dfm_off:X}); data-entry @ file 0x{entry_off:X}")
    print(f"    root props end 0x{root['prop_end']:X}; Panel2 ends 0x{p2_end:X}; "
          f"injecting {len(inject)}B after it")
    for l in layA + layB:
        print(l)

    # splice from the HIGHEST offset down so earlier offsets stay valid
    out = bytearray(blob)
    if shortcut:
        out[save_item["prop_end"]:save_item["prop_end"]] = shortcut
        print(f"    + SaveItem ShortCut=Ctrl+S ({len(shortcut)}B at 0x{save_item['prop_end']:X})")
    out[p2_end:p2_end] = inject
    if not args.no_maximize:
        ws = prop("WindowState", v_ident("wsMaximized"))
        out[root["prop_end"]:root["prop_end"]] = ws
        print(f"    + WindowState=wsMaximized ({len(ws)}B at root prop end)")

    # round-trip sanity: the modified DFM must still parse to the same shape
    P2 = DfmParser(bytes(out))
    root2 = P2.obj(4)
    names2 = [c["name"] for c in root2["children"]]
    assert root2["end"] == len(out), "modified DFM has trailing garbage"
    assert "MBRowA" in names2 and "MBRowB" in names2, names2
    idx = names2.index
    assert idx("Panel2") < idx("MBRowA") < idx("MBRowB"), names2
    si2 = find_node(root2, "SaveItem")
    assert si2 is not None and b"ShortCut" in bytes(out[si2["start"]:si2["end"]]), \
        "SaveItem ShortCut not present after splice"
    assert find_node(root2, "MBClose") is None, "Close button should be gone"
    print(f"    round-trip parse OK: {len(root2['children'])} root children "
          f"(was {len(root['children'])}), new size 0x{len(out):X}")

    if not args.apply:
        print(f"[{EXE}] dry-run OK")
        return

    backup = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print(f"[{EXE}] backup -> {backup}")

    newva = align(max(s[0] + max(s[1], s[3]) for s in F["secs"]), F["salign"])
    newraw = align(len(d), F["falign"])
    if len(d) < newraw:
        d += b"\x00" * (newraw - len(d))
    rawsz = align(len(out), F["falign"])
    d += bytes(out) + b"\x00" * (rawsz - len(out))
    b = F["sectbl"] + F["nsec"]*40
    struct.pack_into("<8sIIII", d, b, SECT_NAME, len(out), newva, rawsz, newraw)
    struct.pack_into("<IIHHI", d, b+24, 0, 0, 0, 0, 0x40000040)   # idata|read
    struct.pack_into("<H", d, F["e"]+6, F["nsec"]+1)
    struct.pack_into("<I", d, F["opt"]+56, align(newva + len(out), F["salign"]))
    # repoint the resource data entry
    struct.pack_into("<II", d, entry_off, newva, len(out))

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{EXE}] LOCKED - close the editor and retry")
        sys.exit(1)
    print(f"[{EXE}] written: .mtb section + repointed TMAINFORM. Revert: no --undo here, and copying\n"
          f"        {os.path.basename(backup)} back is NOT a revert path -- it drops every other AoWDevEd feature.")

main()
