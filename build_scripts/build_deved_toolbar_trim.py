#!/usr/bin/env python3
r"""
AoW1 EDITOR TOOLBAR TRIM  --  AoWDevEd.exe only (DFM resource edit, no code changes).

WHAT IT DOES
  build_editor_toolbar.py injected TWO captioned toolbar rows (MBRowA Top=50,
  MBRowB Top=82) exposing nearly every menu sub-option as a flat TSpeedButton.
  User ruling 2026-09-06: most of those buttons are never used.  This trims the
  pair down to ONE row and deletes the second panel outright:

      File | New Open Save "Save As"
      Developer | "Open Mapset" "Fog of War"
      Help | About

  Deleted labels:  Edit, Options, Preview (MBLabMBRowAEdit / ...Options /
                   ...Preview)
  Deleted buttons: MBCut MBCopy MBPaste MBDelete
                   MBMapSettings MBPlayerInfo MBScanner MBRemLevel MBAddLevel
                   MBPrev640 MBPrev800 MBPrev1024 MBPrev1280
                   MBNewCombat MBNewMapset MBGameSettings MBMapsetSettings
                   MBEditMapText MBExportText MBImportText MBMultilizer
                   MBDebugMode MBExportAbil MBRemLeaders
  The three survivors from row B (MBLabMBRowBDeveloper, MBOpenMapset,
  MBFogOfWar, MBLabMBRowBHelp, MBAbout) are MOVED into MBRowA and the MBRowB
  TPanel is deleted.  Every survivor's Left is recomputed with the same spacing
  rules build_editor_toolbar.py used (CHAR_W/GROUP_GAP/BTN_GAP/LAB_TOP/BTN_TOP),
  so the row reads left-to-right with no gaps.  Panel1 is alClient and reflows,
  so the map view starts 31 px higher.

  The component names are unchanged (MBRowA survives as the marker, so
  build_editor_toolbar.py still reports itself applied; the row-B survivors keep
  their MBLabMBRowB* names -- renaming them would buy nothing and risk a typo).
  Nothing else in the DFM references any deleted name (asserted at build time by
  a length-prefixed shortstring scan over the whole blob), and every surviving
  OnClick name is re-verified against TMainForm's published method table -- the
  one build_deved_terrainpal.py relocated into .ctp, read live through
  VMT-0x28 rather than assumed.

HOW
  The live TMAINFORM DFM is NOT the .rsrc copy and NOT the .mtb copy: it lives
  in .ctp (build_deved_terrainpal.py relocated it there and repointed the
  IMAGE_RESOURCE_DATA_ENTRY).  This script always locates it through the
  resource entry, never by string search.  The trimmed blob is strictly SMALLER,
  so it is written back IN PLACE at the same file offset, the freed tail is
  zero-filled up to the old length, and only the data entry's Size field is
  updated (OffsetToData untouched).  No section header is touched -- which
  matters, because AoWDevEd's section table is full (13 headers ending at file
  0x400, where CODE begins).

  The DFM ends exactly at the end of .ctp's virtual size, so the zero-filled
  tail overlaps nothing.

  build_trimmed() is state-agnostic: it collects the survivors from MBRowA and
  from MBRowB-if-present and emits one MBRowA.  Fed the original blob it
  deletes; fed its own output it is a byte-identical no-op.  That makes
  re-tuning the spacing an IN-PLACE rewrite (change the constants, --apply
  again) rather than a revert-and-reapply.

CONVENTIONS: dry-run by default; --apply to write; idempotent; verify before
write; --undo is surgical.  The original live blob is snapshotted, ONLY when the
live blob is proved to still be the untrimmed one (MBRowB present with all 24
deleted components), to
    <game dir>\backups\AoWDevEd.TMAINFORM.pre-toolbartrim.dfm
Editor-only: AoW.exe / AoWCompat.exe / AoWEd.exe are untouched.
Close AoWDevEd.exe first (the script reports a lock rather than half-writing).

FORWARD HAZARD
  Re-running build_deved_terrainpal.py --apply, or anything else that rebuilds
  TMAINFORM from the .mtb copy, resurrects all 24 deleted buttons -- those
  scripts read whatever the resource entry points at only when their own section
  is absent, and the .mtb blob still carries the full two-row layout.

Usage:
  python build_deved_toolbar_trim.py            # dry-run + verify current state
  python build_deved_toolbar_trim.py --show     # print the resulting layout
  python build_deved_toolbar_trim.py --apply
  python build_deved_toolbar_trim.py --undo
"""
import argparse, hashlib, os, struct, sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE = "AoWDevEd.exe"
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, "AoWDevEd.TMAINFORM.pre-toolbartrim.dfm")

ROW_A_NAME, ROW_B_NAME = "MBRowA", "MBRowB"

# ---- what survives, in final left-to-right order --------------------------------
# (group label component name, group caption, [button component names])
KEEP = [
    ("MBLabMBRowAFile",      "File",      ["MBNew", "MBOpen", "MBSave", "MBSaveAs"]),
    ("MBLabMBRowBDeveloper", "Developer", ["MBOpenMapset", "MBFogOfWar"]),
    ("MBLabMBRowBHelp",      "Help",      ["MBAbout"]),
]
# every component the trim removes -- asserted present before a snapshot is taken
DELETE = [
    "MBLabMBRowAEdit", "MBLabMBRowAOptions", "MBLabMBRowAPreview",
    "MBCut", "MBCopy", "MBPaste", "MBDelete",
    "MBMapSettings", "MBPlayerInfo", "MBScanner", "MBRemLevel", "MBAddLevel",
    "MBPrev640", "MBPrev800", "MBPrev1024", "MBPrev1280",
    "MBNewCombat", "MBNewMapset", "MBGameSettings", "MBMapsetSettings",
    "MBEditMapText", "MBExportText", "MBImportText", "MBMultilizer",
    "MBDebugMode", "MBExportAbil", "MBRemLeaders",
]

# ---- layout constants: identical to build_editor_toolbar.py ---------------------
BTN_H, BTN_TOP = 23, 4
LAB_TOP   = 9
CHAR_W    = 6           # approx px/char @ MS Sans Serif -10
GROUP_GAP = 22
BTN_GAP   = 2


# ---- DFM primitives -------------------------------------------------------------
def ss(s):
    b = s.encode("latin1")
    assert len(b) < 256
    return bytes([len(b)]) + b


def v_int(n):
    if -128 <= n <= 127:     return b"\x02" + struct.pack("<b", n)
    if -32768 <= n <= 32767: return b"\x03" + struct.pack("<h", n)
    return b"\x04" + struct.pack("<i", n)


def prop(name, val):
    return ss(name) + val


# ---- DFM parser (offset + property tracking) ------------------------------------
class DfmParser:
    def __init__(self, data):
        self.d = data

    def rstr(self, o):
        n = self.d[o]
        return self.d[o + 1:o + 1 + n].decode("latin1"), o + 1 + n

    def value(self, o):
        d = self.d
        vt = d[o]; o += 1
        if vt == 0:  return o
        if vt == 2:  return o + 1
        if vt == 3:  return o + 2
        if vt == 4:  return o + 4
        if vt == 5:  return o + 10
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
            return o + 1
        if vt == 12: return o + 4 + struct.unpack_from("<I", d, o)[0]
        if vt == 15: return o + 4
        if vt in (16, 17): return o + 8
        if vt == 18: return o + 4 + 2 * struct.unpack_from("<I", d, o)[0]
        if vt == 14:
            while d[o] != 0:
                if d[o] in (2, 3, 4): o = self.value(o)
                assert d[o] == 1
                o += 1
                while d[o] != 0:
                    _, o = self.rstr(o); o = self.value(o)
                o += 1
            return o + 1
        raise ValueError(f"valuetype {vt} @ {o - 1:#x}")

    def obj(self, o):
        """dict(cls,name,start,prop_end,props={name:(nstart,vstart,vend)},children,end)"""
        d = self.d
        start = o
        if (d[o] & 0xF0) == 0xF0:
            o += 1
            if d[start] & 0x02: o = self.value(o)
        cls, o = self.rstr(o)
        name, o = self.rstr(o)
        props = {}
        while True:
            pn, o2 = self.rstr(o)
            if pn == "":
                prop_end = o          # offset of the 0x00 props terminator
                o = o2
                break
            nstart = o
            o = self.value(o2)
            props[pn] = (nstart, o2, o)
        children = []
        while d[o] != 0:
            c = self.obj(o)
            children.append(c)
            o = c["end"]
        return dict(cls=cls, name=name, start=start, prop_end=prop_end,
                    props=props, children=children, end=o + 1)


def find_node(node, name):
    for c in node["children"]:
        if c["name"] == name:
            return c
        r = find_node(c, name)
        if r:
            return r
    return None


def int_prop(blob, node, key):
    ns, vs, ve = node["props"][key]
    b = blob[vs:ve]
    if b[0] == 2: return struct.unpack_from("<b", b, 1)[0]
    if b[0] == 3: return struct.unpack_from("<h", b, 1)[0]
    if b[0] == 4: return struct.unpack_from("<i", b, 1)[0]
    raise ValueError(f"{key} is not an integer value ({b[0]})")


def str_prop(blob, node, key):
    if key not in node["props"]:
        return None
    ns, vs, ve = node["props"][key]
    b = blob[vs:ve]
    assert b[0] in (6, 7), f"{key} is not a string/ident"
    return b[2:2 + b[1]].decode("latin1")


# ---- PE helpers ------------------------------------------------------------------
def load_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((va, vsz, raw, rsz, b, bytes(d[b:b + 8]).rstrip(b"\0").decode("latin1")))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs)


def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError(hex(rva))


def find_tmainform_entry(d, F):
    """Walk .rsrc; return (file_off_of_data_entry, data_rva, data_size)."""
    rsrc_rva, _ = struct.unpack_from("<II", d, F["opt"] + 96 + 2 * 8)
    ro = rva2off(F["secs"], rsrc_rva)

    def name_at(v):
        off = ro + (v & 0x7FFFFFFF)
        n = struct.unpack_from("<H", d, off)[0]
        return d[off + 2:off + 2 + 2 * n].decode("utf-16le")

    hits = []

    def walk(diroff, path):
        nn, ni = struct.unpack_from("<HH", d, ro + diroff + 12)
        for i in range(nn + ni):
            eo = ro + diroff + 16 + i * 8
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


def find_vmt(d, F, want):
    """Delphi 3 VMT: self-pointer at vmt-0x40, class-name pointer at vmt-0x20."""
    base = 0x400000
    for va0, vsz, raw, rsz, b, nm in F["secs"]:
        if nm != "CODE":
            continue
        limit = min(vsz, rsz)
        for off in range(raw, raw + limit - 4, 4):
            va = base + va0 + (off - raw)
            if struct.unpack_from("<I", d, off)[0] != va + 0x40:
                continue
            vmt = va + 0x40
            npos = struct.unpack_from("<I", d, rva2off(F["secs"], vmt - 0x20 - base))[0]
            if not npos:
                continue
            try:
                no = rva2off(F["secs"], npos - base)
            except ValueError:
                continue
            n = d[no]
            if d[no + 1:no + 1 + n].decode("latin1", "replace") == want:
                return vmt
    raise RuntimeError(f"VMT for {want} not found")


def read_method_names(d, F, mt_va):
    """{name} from the published method table: word count, then
       {word size-incl-itself}{dword code va}{shortstring name}."""
    off = rva2off(F["secs"], mt_va - 0x400000)
    count = struct.unpack_from("<H", d, off)[0]
    p = off + 2
    names = []
    for _ in range(count):
        size = struct.unpack_from("<H", d, p)[0]
        assert size >= 7, "corrupt method table"
        nlen = d[p + 6]
        names.append(d[p + 7:p + 7 + nlen].decode("latin1"))
        p += size
    return count, names


# ---- the trim --------------------------------------------------------------------
def collect(blob, root):
    """Return (rowA_node, rowB_node_or_None, {name: node}) for the two rows."""
    kids = {c["name"]: c for c in root["children"]}
    assert ROW_A_NAME in kids, f"{ROW_A_NAME} not found -- build_editor_toolbar.py not applied?"
    rowA = kids[ROW_A_NAME]
    rowB = kids.get(ROW_B_NAME)
    comps = {}
    for panel in (rowA, rowB):
        if panel is None:
            continue
        for c in panel["children"]:
            assert c["name"] not in comps, f"duplicate component {c['name']}"
            comps[c["name"]] = c
    return rowA, rowB, comps


def build_trimmed(blob):
    """State-agnostic: returns (new_blob, layout_lines).  Idempotent."""
    root = DfmParser(blob).obj(4)
    assert root["cls"] == "TMainForm", root["cls"]
    rowA, rowB, comps = collect(blob, root)

    order = []
    for lab_name, caption, buttons in KEEP:
        order.append(lab_name)
        order.extend(buttons)
    for n in order:
        assert n in comps, f"survivor {n} not present in {ROW_A_NAME}/{ROW_B_NAME}"

    # nothing outside its own definition may name a component we delete
    for n in DELETE:
        if n in comps:
            assert blob.count(ss(n)) == 1, \
                f"{n} is referenced elsewhere in the DFM -- deleting it would break a link"

    lines = []
    kids = b""
    x = 6
    for lab_name, caption, buttons in KEEP:
        lab = comps[lab_name]
        lw = CHAR_W * len(caption) + 4
        assert str_prop(blob, lab, "Caption") == caption, \
            f"{lab_name}.Caption is {str_prop(blob, lab, 'Caption')!r}, expected {caption!r}"
        assert int_prop(blob, lab, "Width") == lw, \
            f"{lab_name}.Width is {int_prop(blob, lab, 'Width')}, layout says {lw}"
        assert int_prop(blob, lab, "Top") == LAB_TOP
        kids += set_left(blob, lab, x)
        lines.append(f"    [{x:4}] {caption + ' |':<14} ({lab_name})")
        x += lw + 6
        for bname in buttons:
            b = comps[bname]
            cap = str_prop(blob, b, "Caption")
            bw = max(34, CHAR_W * len(cap) + 14)
            assert int_prop(blob, b, "Width") == bw, \
                f"{bname}.Width is {int_prop(blob, b, 'Width')}, layout says {bw}"
            assert int_prop(blob, b, "Top") == BTN_TOP
            assert int_prop(blob, b, "Height") == BTN_H
            kids += set_left(blob, b, x)
            lines.append(f"    [{x:4}]   {cap:<16} -> {str_prop(blob, b, 'OnClick')}")
            x += bw + BTN_GAP
        x += GROUP_GAP
    lines.append(f"    one row, {len(order)} components, content width ~{x - GROUP_GAP}px")

    # MBRowA keeps its own properties verbatim; only its child list is replaced
    new_rowA = blob[rowA["start"]:rowA["prop_end"] + 1] + kids + b"\x00"
    end = (rowB if rowB is not None else rowA)["end"]
    out = blob[:rowA["start"]] + new_rowA + blob[end:]
    return bytes(out), lines


def set_left(blob, node, left):
    """That component's serialised bytes with Left rewritten to `left`."""
    s = node["start"]
    ns, vs, ve = node["props"]["Left"]
    return (blob[s:ns] + prop("Left", v_int(left)) + blob[ve:node["end"]])


def verify(blob, tag):
    """Re-parse a trimmed blob and check the shape."""
    root = DfmParser(blob).obj(4)
    assert root["end"] == len(blob), f"{tag}: trailing garbage after the root object"
    names = [c["name"] for c in root["children"]]
    assert ROW_A_NAME in names, f"{tag}: {ROW_A_NAME} marker lost"
    assert ROW_B_NAME not in names, f"{tag}: {ROW_B_NAME} still present"
    rowA = next(c for c in root["children"] if c["name"] == ROW_A_NAME)
    got = [c["name"] for c in rowA["children"]]
    want = []
    for lab_name, _, buttons in KEEP:
        want.append(lab_name); want.extend(buttons)
    assert got == want, f"{tag}: row contents {got}"
    for n in DELETE:
        assert find_node(root, n) is None, f"{tag}: {n} survived"
        assert ss(n) not in blob, f"{tag}: {n} still named in the blob"
    return root, rowA


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---- main ------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--show", action="store_true", help="print the resulting layout")
    args = ap.parse_args()

    path = os.path.join(GAME, EXE)
    orig_file = open(path, "rb").read()
    d = bytearray(orig_file)
    F = load_sections(d)
    print(f"[{EXE}] sha256 before: {sha(orig_file)}")

    entry_off, dfm_rva, dfm_size = find_tmainform_entry(d, F)
    dfm_off = rva2off(F["secs"], dfm_rva)
    sect = next(s for s in F["secs"] if s[0] <= dfm_rva < s[0] + max(s[1], s[3]))
    blob = bytes(d[dfm_off:dfm_off + dfm_size])
    assert blob[:4] == b"TPF0", "TMAINFORM resource does not start with TPF0"
    print(f"    live TMAINFORM: section {sect[5]}, rva {dfm_rva:#x} size {dfm_size:#x} "
          f"(file {dfm_off:#x}); data entry @ file {entry_off:#x}")

    root = DfmParser(blob).obj(4)
    rowA, rowB, comps = collect(blob, root)
    untrimmed = rowB is not None and all(n in comps for n in DELETE)
    trimmed_now = rowB is None

    # the published method table (relocated by build_deved_terrainpal.py) -- read live
    vmt = find_vmt(d, F, "TMainForm")
    mt_va = struct.unpack_from("<I", d, rva2off(F["secs"], vmt - 0x28 - 0x400000))[0]
    count, mnames = read_method_names(d, F, mt_va)
    print(f"    TMainForm VMT {vmt:#x}; published method table {mt_va:#x} ({count} entries)")

    new_blob, lines = build_trimmed(blob)
    verify(new_blob, "build")

    # every surviving handler must still resolve by name at form-load time
    root2 = DfmParser(new_blob).obj(4)
    rowA2 = next(c for c in root2["children"] if c["name"] == ROW_A_NAME)
    # Delphi's TObject.MethodAddress folds case, so the lookup is case-insensitive.
    # MBOpenMapset's DFM name really is "OpenMapsetClick" against a table entry
    # "OpenMapSetClick" -- a typo in build_editor_toolbar.py that has always worked.
    lower = {n.lower(): n for n in mnames}
    handlers = []
    for c in rowA2["children"]:
        h = str_prop(new_blob, c, "OnClick")
        if h is None:
            continue
        assert h.lower() in lower, f"handler {h} ({c['name']}) not in the method table"
        handlers.append(h if lower[h.lower()] == h else f"{h} (table: {lower[h.lower()]})")
    print(f"    {len(handlers)} handlers verified against the method table: "
          f"{', '.join(handlers)}")

    if args.show or not (args.apply or args.undo):
        for l in lines:
            print(l)

    already = (new_blob == blob)
    print(f"    state: {'TRIMMED (live blob == build output)' if already else 'UNTRIMMED' if untrimmed else 'UNEXPECTED'}"
          f"; DFM {len(blob):#x} -> {len(new_blob):#x} bytes ({len(new_blob) - len(blob):+d})")

    # ---------------- undo -------------------------------------------------------
    if args.undo:
        if not os.path.exists(BACKUP):
            print(f"[{EXE}] no snapshot at {BACKUP} - nothing to undo"); return 1
        snap = open(BACKUP, "rb").read()
        assert snap[:4] == b"TPF0", "snapshot is not a DFM"
        rebuilt, _ = build_trimmed(snap)
        if not already:
            print(f"[{EXE}] live blob is not the trimmed output - refusing to undo"); return 1
        assert rebuilt == blob, ("the live blob is not what THIS script would produce from "
                                 "the snapshot - refusing to undo")
        assert len(snap) >= len(blob), "snapshot is smaller than the live blob"
        d[dfm_off:dfm_off + len(snap)] = snap
        struct.pack_into("<I", d, entry_off + 4, len(snap))
        changed = write_and_diff(path, orig_file, d, entry_off, dfm_off, len(snap))
        print(f"[{EXE}] UNDONE: original TMAINFORM restored ({len(snap):#x} bytes), "
              f"data-entry Size {len(blob):#x} -> {len(snap):#x}; {changed} bytes changed")
        return 0

    # ---------------- apply ------------------------------------------------------
    if already:
        print(f"[{EXE}] already trimmed - idempotent no-op"
              f"{'' if os.path.exists(BACKUP) else ' (WARNING: no snapshot on disk, --undo unavailable)'}")
        return 0
    assert untrimmed, ("the live blob is neither the untrimmed two-row layout nor this "
                       "script's output - refusing to touch it")

    if not args.apply:
        print(f"[{EXE}] dry-run OK - re-run with --apply to write")
        return 0

    # snapshot ONLY from a blob proved to be the untrimmed original
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(BACKUP):
        open(BACKUP, "wb").write(blob)
        print(f"    snapshot -> backups\\{os.path.basename(BACKUP)} ({len(blob):#x} bytes)")
    else:
        assert open(BACKUP, "rb").read() == blob, \
            "an existing snapshot differs from the live untrimmed blob - refusing to overwrite"

    d[dfm_off:dfm_off + len(new_blob)] = new_blob
    # zero-fill the freed tail (the DFM ends at the end of the section's virtual size)
    d[dfm_off + len(new_blob):dfm_off + len(blob)] = b"\x00" * (len(blob) - len(new_blob))
    struct.pack_into("<I", d, entry_off + 4, len(new_blob))   # Size only; OffsetToData kept
    changed = write_and_diff(path, orig_file, d, entry_off, dfm_off, len(blob))
    print(f"[{EXE}] written in place: TMAINFORM {len(blob):#x} -> {len(new_blob):#x} bytes, "
          f"tail zero-filled, data-entry Size updated; {changed} bytes changed")
    print(f"[{EXE}] applied, untested - revert with --undo")
    return 0


def write_and_diff(path, before, d, entry_off, dfm_off, span):
    """Write, then assert every changed byte is in the DFM span or the Size dword."""
    after = bytes(d)
    assert len(after) == len(before), "file length changed - it must not"
    allowed = set(range(entry_off + 4, entry_off + 8)) | set(range(dfm_off, dfm_off + span))
    changed = [i for i in range(len(before)) if before[i] != after[i]]
    stray = [i for i in changed if i not in allowed]
    assert not stray, f"{len(stray)} bytes changed outside the DFM/Size window, first {stray[0]:#x}"
    try:
        open(path, "wb").write(after)
    except PermissionError:
        print(f"[{EXE}] LOCKED - close AoWDevEd.exe and retry"); sys.exit(1)
    written = open(path, "rb").read()
    assert written == after, "read-back mismatch"
    print(f"[{EXE}] sha256 after:  {sha(written)}")
    return len(changed)


if __name__ == "__main__":
    sys.exit(main())
