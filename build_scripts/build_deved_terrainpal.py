#!/usr/bin/env python3
r"""
AoW1 EDITOR TERRAIN PALETTE UPGRADE  --  AoWDevEd.exe only.

WHAT IT DOES
  1. Adds SKY (terrain 0xE, ex-Coast) and CHASM (terrain 0xB, ex-uWasteland) brush
     buttons to the editor's top-level tile palette -- the flying/floating-only
     terrains from Chasm_Sky_Terrain_Design.md.
  2. Makes the palette CROSS-LEVEL: every cave terrain gets a button on the
     Surface tab and every surface terrain gets a button on the Underground tab.
     (The engine never had a level restriction -- TMORTerrainControl.GetRndResource
     keys resources by terrain id only -- so this is purely a UI gap.)

  Surface tab (ToolbarPnl), rows 0-1 unchanged, two new rows:
      r2: Sky | CaveWater | Dirt | Lava | CaveIce
      r3: Earth | Rock | Chasm
  Underground tab (Panel10), rows 0-1 unchanged except the empty slot filled:
      r1: ... | Chasm            <- fills the vanilla gap (cave terrain, cave row)
      r2: Sky | Water | Grass | Steppe | Desert
      r3: Wasteland | Snow | Ice
  Both panels grow 76 -> 152 px high; the resource grid below is alClient and
  reflows itself.

HOW
  * Cross-level buttons need NO new code: DFM OnClick handlers are resolved BY
    NAME against the form's published method table at load time, so a new
    TSpeedButton can point at an existing handler (vanilla already does this --
    uArmyBtn/uItemBtn reuse ArmyBtnClick/ItemBtnClick). Their Glyph.Data blobs
    are copied verbatim from the original buttons.
  * Sky/Chasm need two new handlers. Every TMainForm.<Terrain>BtnClick is the
    same 43-byte stub differing only in one `mov dl,<terrain id>`; the cave
    stubs are assembled from that template and verified byte-identical to
    TMainForm.uWaterBtnClick (with dl=0xA) at build time.
  * To let the DFM name them, TMainForm's published method table is RELOCATED to
    the new section with 2 entries appended (it cannot grow in place -- the class
    name shortstring sits immediately after it) and the VMT's vmtMethodTable
    slot (VMT-0x28) is repointed. Delphi 3 VMT layout: selfptr -0x40,
    methodtable -0x28, classname -0x20, parent -0x18.
  * Sky/Chasm glyphs are generated from the user's art in <game>/Zigmod/
    (Sky.bmp / Chasm.bmp -- actually PNGs) masked to the exact hexagon silhouette
    of an existing terrain glyph, 48x32 24-bit BMP + 4-byte length prefix, with
    the source glyph's own transparent key colour. Chasm is darkened so the two
    are distinguishable in the palette (CHASM_DARKEN knob).

  Everything (2 stubs + method table + rebuilt DFM) goes in one new PE section
  ".ctp"; the TMAINFORM resource data entry is repointed at the new DFM. The
  copy in .mtb (build_editor_toolbar.py's section) becomes dead data, exactly as
  that patch left the original .rsrc copy dead. LAYERS ON TOP of both
  build_dlgdirs.py and build_editor_toolbar.py -- it reads whatever DFM the
  resource entry currently points at, so it must run AFTER them.

CONVENTIONS: dry-run by default, --apply to write; idempotent (no-op if .ctp
exists); verify-before-write (asserts template match, DFM round-trip, method
table round-trip); auto-backup to `<game dir>\backups\AoWDevEd.exe.pre-terrainpal`.
Editor-only -- AoW.exe/AoWCompat.exe are untouched. Close AoWDevEd.exe first.
Revert: there is no --undo here, and a .pre-terrainpal restore is NOT a revert path -- it is a
WHOLE-FILE copy, so it drops every other AoWDevEd feature (valgoto, partyrnd, timerres, modtoolbar,
dlgdirs, coppermedal) applied since. Undo surgically instead: drop the .ctp section, restore the VMT
method-table slot and the TMAINFORM resource data entry.

Needs: pip install keystone-engine pillow
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE  = "AoWDevEd.exe"
BACKUP_SUFFIX = ".pre-terrainpal"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
SECT_NAME = b".ctp\0\0\0\0"
ART_DIR   = os.path.join(GAME, "Zigmod")

# ---- terrain ids ----------------------------------------------------------------
SKY_ID, CHASM_ID = 0x0E, 0x0B
# handler thunks + object offsets, all verified against TMainForm.uWaterBtnClick
SELECT_CHANGE = 0x402DF0        # HSMEdit.THSMEdit.SelectChangeTerrain (import thunk)
SELECT_CLEAR  = 0x402DF8        # HSMEdit.THSMEdit.SelectClearTerrain
TEMPLATE_VA   = 0x42B594        # TMainForm.uWaterBtnClick (dl=0x0A) -- byte-compare source
TEMPLATE_ID   = 0x0A
STUB_LEN      = 43

# Palette-icon look.  Both source arts are the same starfield, so the icons are
# differentiated: Sky = bright open starfield, Chasm = dimmer starfield inside a
# rocky rim (reads as a pit).  Terrain TILE art is unaffected by these knobs.
SKY_BOOST   = 2.6
CHASM_BOOST = 1.7
CHASM_RIM   = (78, 64, 52)      # rock colour, RGB
CHASM_RIM_W = 3                 # px of rim shading inwards from the hex edge

# ---- palette layout -------------------------------------------------------------
COLS_X   = [0, 69, 138, 207, 276]
ROW_Y    = [0, 38, 76, 114]
BTN_W, BTN_H = 68, 37
PANEL_H_NEW  = 152              # 4 rows * 38

# (name, col, row, hint, handler, glyph-source-button | "SKY" | "CHASM")
SURFACE_NEW = [
    ("SkyBtn",       0, 2, "Sky (flying/floating only)",  "SkyBtnClick",    "SKY"),
    ("XuWaterBtn",   1, 2, "Cave Water (cross-level)",    "uWaterBtnClick", "uWaterBtn"),
    ("XDirtBtn",     2, 2, "Dirt / cave floor (cross-level)", "DirtBtnClick", "DirtBtn"),
    ("XLavaBtn",     3, 2, "Lava (cross-level)",          "LavaBtnClick",   "LavaBtn"),
    ("XuIceBtn",     4, 2, "Cave Ice (cross-level)",      "uIceBtnClick",   "uIceBtn"),
    ("XEarthBtn",    0, 3, "Earth wall (cross-level)",    "EarthBtnClick",  "EarthBtn"),
    ("XRockBtn",     1, 3, "Rock wall (cross-level)",     "RockBtnClick",   "RockBtn"),
    ("ChasmBtn",     2, 3, "Chasm (flying/floating only)", "ChasmBtnClick", "CHASM"),
]
UNDER_NEW = [
    ("uChasmBtn",     4, 1, "Chasm (flying/floating only)", "ChasmBtnClick", "CHASM"),
    ("uSkyBtn",       0, 2, "Sky (flying/floating only)",   "SkyBtnClick",   "SKY"),
    ("XWaterBtn",     1, 2, "Water (cross-level)",       "WaterBtnClick",     "WaterBtn"),
    ("XGrassBtn",     2, 2, "Grass (cross-level)",       "GrassBtnClick",     "GrassBtn"),
    ("XSteppeBtn",    3, 2, "Steppe (cross-level)",      "SteppeBtnClick",    "SteppeBtn"),
    ("XDesertBtn",    4, 2, "Desert (cross-level)",      "DesertBtnClick",    "DesertBtn"),
    ("XWastelandBtn", 0, 3, "Wasteland (cross-level)",   "WastelandBtnClick", "WastelandBtn"),
    ("XSnowBtn",      1, 3, "Snow (cross-level)",        "SnowBtnClick",      "SnowBtn"),
    ("XIceBtn",       2, 3, "Ice (cross-level)",         "IceBtnClick",       "IceBtn"),
]
NEW_HANDLERS = [("SkyBtnClick", SKY_ID), ("ChasmBtnClick", CHASM_ID)]
HEX_MASK_SRC = "GrassBtn"       # glyph whose hexagon silhouette Sky/Chasm reuse

# ---- DFM primitives -------------------------------------------------------------
def ss(s):
    b = s.encode("latin1"); assert len(b) < 256; return bytes([len(b)]) + b
def v_int(n):
    if -128 <= n <= 127:     return b"\x02" + struct.pack("<b", n)
    if -32768 <= n <= 32767: return b"\x03" + struct.pack("<h", n)
    return b"\x04" + struct.pack("<i", n)
def v_str(s):   return b"\x06" + ss(s)
def v_ident(s): return b"\x07" + ss(s)
def v_bool(b):  return b"\x09" if b else b"\x08"
def v_bin(b):   return b"\x0A" + struct.pack("<I", len(b)) + b
def prop(name, val): return ss(name) + val
def obj(cls, name, props, children=b""):
    return ss(cls) + ss(name) + props + b"\x00" + children + b"\x00"

def make_button(name, col, row, hint, handler, glyph):
    """One palette TSpeedButton, matching the vanilla ones property-for-property."""
    return obj("TSpeedButton", name,
               prop("Left",       v_int(COLS_X[col])) +
               prop("Top",        v_int(ROW_Y[row])) +
               prop("Width",      v_int(BTN_W)) +
               prop("Height",     v_int(BTN_H)) +
               prop("Hint",       v_str(hint)) +
               prop("AllowAllUp", v_bool(True)) +
               prop("GroupIndex", v_int(1)) +
               prop("Flat",       v_bool(True)) +
               prop("Glyph.Data", v_bin(glyph)) +
               prop("OnClick",    v_ident(handler)))

# ---- DFM parser (offset tracking) -----------------------------------------------
class DfmParser:
    def __init__(self, data): self.d = data
    def rstr(self, o):
        n = self.d[o]; return self.d[o+1:o+1+n].decode("latin1"), o+1+n
    def value(self, o):
        d = self.d; vt = d[o]; o += 1
        if vt == 0:  return o
        if vt == 2:  return o+1
        if vt == 3:  return o+2
        if vt == 4:  return o+4
        if vt == 5:  return o+10
        if vt in (6, 7): _, o = self.rstr(o); return o
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
                    _, o = self.rstr(o); o = self.value(o)
                o += 1
            return o+1
        raise ValueError(f"valuetype {vt} @ {o-1:#x}")
    def obj(self, o):
        d = self.d; start = o
        if (d[o] & 0xF0) == 0xF0:
            o += 1
            if d[start] & 0x02: o = self.value(o)
        cls, o = self.rstr(o)
        name, o = self.rstr(o)
        props = {}
        while True:
            pn, o2 = self.rstr(o)
            if pn == "":
                prop_end = o; o = o2; break
            vstart = o2
            o = self.value(o2)
            props[pn] = (o2 - len(ss(pn)) - 0, vstart, o)   # (name_start, val_start, val_end)
            props[pn] = (o2 - 1 - len(pn), vstart, o)
        children = []
        while d[o] != 0:
            c = self.obj(o); children.append(c); o = c["end"]
        return dict(cls=cls, name=name, start=start, prop_end=prop_end,
                    props=props, children=children, end=o+1)

def find_node(node, name):
    if node["name"] == name: return node
    for c in node["children"]:
        r = find_node(c, name)
        if r: return r
    return None

def glyph_of(node, blob):
    """Return the raw Glyph.Data bytes of a button node."""
    ns, vs, ve = node["props"]["Glyph.Data"]
    assert blob[vs] == 0x0A, "Glyph.Data is not vaBinary"
    n = struct.unpack_from("<I", blob, vs+1)[0]
    return blob[vs+5:vs+5+n]

# ---- glyph generation -----------------------------------------------------------
def build_glyph(src_blob, art_path, boost=1.0, rim=None, rim_w=0):
    """Recolour a copy of a Glyph.Data blob with art, keeping its hexagon
    silhouette and transparent key colour.  The blob is a Delphi TBitmap stream:
    4-byte size prefix + a Windows BMP (48x32 24bpp in this form).

    The art is downscaled with a max/average blend: plain averaging washes the
    stars out of a 256px starfield at 48x32, max-pooling keeps them.  `boost`
    scales brightness; `rim`/`rim_w` shade the outermost ring of the hexagon
    towards a colour (used to make Chasm read as a pit rather than open sky)."""
    from PIL import Image
    if src_blob[:2] == b"BM":
        pre, bmp = b"", bytearray(src_blob)
    else:
        assert src_blob[4:6] == b"BM", "Glyph.Data is not a TBitmap stream"
        pre, bmp = src_blob[:4], bytearray(src_blob[4:])
    dataoff = struct.unpack_from("<I", bmp, 10)[0]
    w, h = struct.unpack_from("<ii", bmp, 18)
    bpp  = struct.unpack_from("<H", bmp, 28)[0]
    assert bpp == 24 and h > 0, f"unexpected glyph format {w}x{h}@{bpp}"
    stride = (w*3 + 3) // 4 * 4
    px = bytearray(bmp[dataoff:dataoff + stride*h])
    key = bytes(px[0:3])                       # bottom-left pixel = transparent colour

    src = Image.open(art_path).convert("RGB")
    avg = src.resize((w, h), Image.LANCZOS).load()
    mx  = src.resize((w, h), Image.BOX).load()  # box first, then max-pool below
    sp, (sw, sh) = src.load(), src.size
    def maxpool(x, y):
        x0, x1 = sw*x//w, max(sw*x//w + 1, sw*(x+1)//w)
        y0, y1 = sh*y//h, max(sh*y//h + 1, sh*(y+1)//h)
        best = (0, 0, 0)
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                p = sp[xx, yy]
                if sum(p) > sum(best): best = p
        return best

    # hexagon mask + distance-to-edge (for the rim), in BMP row space
    inside = [[bytes(px[r*stride + c*3: r*stride + c*3 + 3]) != key
               for c in range(w)] for r in range(h)]
    dist = [[0]*w for _ in range(h)]
    if rim and rim_w:
        cur = [row[:] for row in inside]
        for k in range(1, rim_w+1):
            nxt = [[False]*w for _ in range(h)]
            for r in range(h):
                for c in range(w):
                    if not cur[r][c]: continue
                    ok = all(0 <= r+dr < h and 0 <= c+dc < w and cur[r+dr][c+dc]
                             for dr, dc in ((1,0), (-1,0), (0,1), (0,-1)))
                    nxt[r][c] = ok
                    if not ok and dist[r][c] == 0: dist[r][c] = k
            cur = nxt

    for row in range(h):                       # BMP rows are bottom-up
        y = h - 1 - row
        for x in range(w):
            i = row*stride + x*3
            if not inside[row][x]:
                continue                       # keep transparent surround
            a, m = avg[x, y], maxpool(x, y)
            r, g, b = (int((a[j] + m[j]) * 0.5 * boost) for j in range(3))
            if rim and dist[row][x]:
                t = 1.0 - (dist[row][x] - 1) / max(1, rim_w)   # 1 at the edge
                r = int(r*(1-t) + rim[0]*t)
                g = int(g*(1-t) + rim[1]*t)
                b = int(b*(1-t) + rim[2]*t)
            r, g, b = min(255, r), min(255, g), min(255, b)
            if (b, g, r) == tuple(key):        # never emit the key colour inside the hex
                b = min(255, b + 8)
            px[i:i+3] = bytes((b, g, r))       # BMP is BGR
    bmp[dataoff:dataoff + stride*h] = px
    return pre + bytes(bmp), key, (w, h)

# ---- PE helpers -----------------------------------------------------------------
def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    opt = e+24; sectbl = opt+optsz
    secs = []
    for i in range(nsec):
        b = sectbl+i*40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from('<I', d, opt+32)[0],
                falign=struct.unpack_from('<I', d, opt+36)[0],
                hdrsz=struct.unpack_from('<I', d, opt+84)[0])

def align(x, a): return (x + a - 1) // a * a

def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError(hex(rva))

def find_tmainform_entry(d, F):
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
            if off & 0x80000000: walk(off & 0x7FFFFFFF, path + [label])
            elif "TMAINFORM" in (p.upper() for p in path + [label]):
                drva, dsize = struct.unpack_from("<II", d, ro + off)
                hits.append((ro + off, drva, dsize))
    walk(0, [])
    assert len(hits) == 1, f"TMAINFORM data entries: {len(hits)}"
    return hits[0]

def find_vmt(d, F, want):
    """Delphi 3 VMT: self-pointer at vmt-0x40, class name ptr at vmt-0x20."""
    base = 0x400000
    for va0, vsz, raw, rsz, b in F["secs"]:
        if bytes(d[b:b+4]) != b"CODE": continue
        limit = min(vsz, rsz)
        for off in range(raw, raw + limit - 4, 4):
            va = base + va0 + (off - raw)
            if struct.unpack_from("<I", d, off)[0] != va + 0x40: continue
            vmt = va + 0x40
            npos = struct.unpack_from("<I", d, rva2off(F["secs"], vmt-0x20-base))[0]
            if not npos: continue
            try: no = rva2off(F["secs"], npos - base)
            except ValueError: continue
            n = d[no]
            if d[no+1:no+1+n].decode("latin1", "replace") == want:
                return vmt
    raise RuntimeError(f"VMT for {want} not found")

def read_method_table(d, F, mt_va):
    off = rva2off(F["secs"], mt_va - 0x400000)
    count = struct.unpack_from("<H", d, off)[0]
    p = off + 2; entries = []
    for _ in range(count):
        size, code = struct.unpack_from("<HI", d, p)
        assert size >= 7, "corrupt method table"
        nlen = d[p+6]
        entries.append((code, d[p+7:p+7+nlen].decode("latin1")))
        p += size
    return count, entries, off, p - off      # (count, entries, file_off, total_bytes)

def mt_entry(code, name):
    nb = name.encode("latin1")
    return struct.pack("<HI", 7 + len(nb), code) + bytes([len(nb)]) + nb

# ---- main -----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)

    if any(bytes(d[s[4]:s[4]+4]) == SECT_NAME[:4] for s in F["secs"]):
        print(f"[{EXE}] already patched (.ctp section present) - idempotent no-op")
        return 0
    assert F["sectbl"] + (F["nsec"]+1)*40 <= F["hdrsz"], "no header room for a new section"

    # ---------- 1. the two new handler stubs (assembled, template-verified) -------
    def stub_src(tid):
        return f"""
            mov edx, dword ptr [eax + 0x60c]
            cmp byte ptr [edx + 0xc0], 0
            jne _clear
            mov dl, {tid}
            mov eax, dword ptr [eax + 0x22c]
            call 0x{SELECT_CHANGE:X}
            ret
        _clear:
            mov dl, {tid}
            mov eax, dword ptr [eax + 0x22c]
            call 0x{SELECT_CLEAR:X}
            ret
        """
    tmpl_off = rva2off(F["secs"], TEMPLATE_VA - 0x400000)
    tmpl_orig = bytes(d[tmpl_off:tmpl_off+STUB_LEN])
    tmpl_asm, _ = ks.asm(stub_src(TEMPLATE_ID), TEMPLATE_VA)
    assert bytes(tmpl_asm) == tmpl_orig, (
        "handler template mismatch -- the editor build differs from the one this "
        f"script was written for\n  orig {tmpl_orig.hex()}\n  asm  {bytes(tmpl_asm).hex()}")
    print(f"[{EXE}] handler template verified byte-identical to "
          f"TMainForm.uWaterBtnClick @ {TEMPLATE_VA:#x} ({STUB_LEN}B)")

    # ---------- 2. locate the DFM + the method table ------------------------------
    entry_off, dfm_rva, dfm_size = find_tmainform_entry(d, F)
    dfm_off = rva2off(F["secs"], dfm_rva)
    blob = bytes(d[dfm_off:dfm_off+dfm_size])
    assert blob[:4] == b"TPF0", "TMAINFORM resource is not a DFM"
    P = DfmParser(blob); root = P.obj(4)
    assert root["cls"] == "TMainForm", root["cls"]
    if find_node(root, "SkyBtn") is not None:
        print(f"[{EXE}] SkyBtn already in the DFM - no-op"); return 0

    vmt = find_vmt(d, F, "TMainForm")
    mt_slot_va = vmt - 0x28
    mt_va = struct.unpack_from("<I", d, rva2off(F["secs"], mt_slot_va - 0x400000))[0]
    count, entries, mt_off, mt_len = read_method_table(d, F, mt_va)
    have = {n for _, n in entries}
    print(f"    TMainForm VMT {vmt:#x}; method table {mt_va:#x} "
          f"(file {mt_off:#x}, {count} entries, {mt_len}B)")
    print(f"    TMAINFORM DFM: rva {dfm_rva:#x} size {dfm_size:#x} (file {dfm_off:#x})")

    # every handler the new buttons reference must exist (or be one we are adding)
    adding = {n for n, _ in NEW_HANDLERS}
    for lst in (SURFACE_NEW, UNDER_NEW):
        for _, _, _, _, handler, _ in lst:
            assert handler in have or handler in adding, f"handler {handler} not found"
    for n in adding:
        assert n not in have, f"{n} already in the method table"

    # ---------- 3. glyphs ---------------------------------------------------------
    mask_src = find_node(root, HEX_MASK_SRC)
    assert mask_src is not None, f"{HEX_MASK_SRC} not found"
    base_glyph = glyph_of(mask_src, blob)
    sky_art   = os.path.join(ART_DIR, "Sky.bmp")
    chasm_art = os.path.join(ART_DIR, "Chasm.bmp")
    for p in (sky_art, chasm_art):
        assert os.path.exists(p), f"missing art: {p}"
    sky_glyph, key, dims = build_glyph(base_glyph, sky_art, boost=SKY_BOOST)
    chasm_glyph, _, _    = build_glyph(base_glyph, chasm_art, boost=CHASM_BOOST,
                                       rim=CHASM_RIM, rim_w=CHASM_RIM_W)
    print(f"    glyphs: {dims[0]}x{dims[1]} 24bpp, transparent key "
          f"#{key[2]:02X}{key[1]:02X}{key[0]:02X} (from {HEX_MASK_SRC}); "
          f"Sky={len(sky_glyph)}B (boost {SKY_BOOST}) "
          f"Chasm={len(chasm_glyph)}B (boost {CHASM_BOOST}, rim {CHASM_RIM_W}px)")

    # ---------- 4. build the new buttons -----------------------------------------
    def build_panel_children(panel, spec):
        out = b""
        for name, col, row, hint, handler, gsrc in spec:
            if gsrc == "SKY":     g = sky_glyph
            elif gsrc == "CHASM": g = chasm_glyph
            else:
                src = find_node(root, gsrc)
                assert src is not None, f"glyph source {gsrc} not found"
                g = glyph_of(src, blob)
            assert find_node(root, name) is None, f"{name} already exists"
            out += make_button(name, col, row, hint, handler, g)
            print(f"      {panel:<11} {name:<15} ({COLS_X[col]:3},{ROW_Y[row]:3}) "
                  f"-> {handler:<20} glyph={gsrc}")
        return out

    print("    new buttons:")
    surf_kids  = build_panel_children("ToolbarPnl", SURFACE_NEW)
    under_kids = build_panel_children("Panel10",    UNDER_NEW)

    # ---------- 5. splice the DFM (edits applied highest-offset-first) ------------
    edits = []          # (offset, delete_len, insert_bytes)
    for pname, kids in (("ToolbarPnl", surf_kids), ("Panel10", under_kids)):
        pn = find_node(root, pname)
        assert pn is not None, f"{pname} not found"
        # children go just before the node's child-list terminator
        edits.append((pn["end"] - 1, 0, kids))
        # Height 76 -> 152 (needs int16, so the property length changes)
        ns, vs, ve = pn["props"]["Height"]
        old = blob[ns:ve]
        assert old == prop("Height", v_int(76)), f"{pname}.Height unexpected: {old.hex()}"
        edits.append((ns, ve - ns, prop("Height", v_int(PANEL_H_NEW))))
    out = bytearray(blob)
    for off, dl, ins in sorted(edits, key=lambda e: -e[0]):
        out[off:off+dl] = ins
    print(f"    DFM: {len(blob):#x} -> {len(out):#x} bytes "
          f"(+{len(out)-len(blob)}), both panels H 76 -> {PANEL_H_NEW}")

    # round-trip: the rebuilt DFM must parse to the expected shape
    root2 = DfmParser(bytes(out)).obj(4)
    assert root2["end"] == len(out), "rebuilt DFM has trailing garbage"
    for pname, spec, before in (("ToolbarPnl", SURFACE_NEW, 10), ("Panel10", UNDER_NEW, 9)):
        pn2 = find_node(root2, pname)
        names = [c["name"] for c in pn2["children"]]
        assert len(names) == before + len(spec), f"{pname}: {len(names)} children"
        for name, *_ in spec:
            assert name in names, f"{name} missing from {pname}"
        assert bytes(out[pn2["props"]["Height"][1]:pn2["props"]["Height"][2]]) \
            == v_int(PANEL_H_NEW), f"{pname}.Height not updated"
    for name, _ in NEW_HANDLERS:      # every OnClick must resolve after step 6
        pass
    print(f"    round-trip parse OK "
          f"(ToolbarPnl {10+len(SURFACE_NEW)} kids, Panel10 {9+len(UNDER_NEW)} kids)")

    if not args.apply:
        print(f"[{EXE}] dry-run OK - re-run with --apply to write")
        return 0

    # ---------- 6. lay out the new section ---------------------------------------
    newva  = align(max(s[0] + max(s[1], s[3]) for s in F["secs"]), F["salign"])
    body   = bytearray()
    stub_vas = {}
    for name, tid in NEW_HANDLERS:
        va = 0x400000 + newva + len(body)
        code, _ = ks.asm(stub_src(tid), va)
        code = bytes(code)
        assert len(code) == STUB_LEN
        stub_vas[name] = va
        body += code + b"\x90" * (align(len(code), 4) - len(code))
    body += b"\x90" * (align(len(body), 16) - len(body))

    mt_new_off_in_body = len(body)
    mt_body = struct.pack("<H", count + len(NEW_HANDLERS))
    mt_body += bytes(d[mt_off+2:mt_off+mt_len])
    for name, _ in NEW_HANDLERS:
        mt_body += mt_entry(stub_vas[name], name)
    body += mt_body + b"\x00" * (align(len(body)+len(mt_body), 4) - (len(body)+len(mt_body)))
    mt_new_va = 0x400000 + newva + mt_new_off_in_body

    dfm_new_off_in_body = align(len(body), 4)
    body += b"\x00" * (dfm_new_off_in_body - len(body)) + bytes(out)
    dfm_new_rva = newva + dfm_new_off_in_body

    # verify the rebuilt method table parses and contains the new names
    probe = bytearray(b"\x00" * (mt_new_off_in_body)) + mt_body
    c2 = struct.unpack_from("<H", probe, mt_new_off_in_body)[0]
    p = mt_new_off_in_body + 2; got = []
    for _ in range(c2):
        size, code = struct.unpack_from("<HI", probe, p)
        nlen = probe[p+6]; got.append((code, probe[p+7:p+7+nlen].decode("latin1"))); p += size
    assert c2 == count + len(NEW_HANDLERS) and p - mt_new_off_in_body == len(mt_body), \
        "rebuilt method table does not round-trip"
    assert [g[1] for g in got[:count]] == [e[1] for e in entries], "method table reordered"
    for name, _ in NEW_HANDLERS:
        assert (stub_vas[name], name) in got, f"{name} missing from rebuilt table"
    print(f"    stubs: " + ", ".join(f"{n}@{stub_vas[n]:#x}" for n, _ in NEW_HANDLERS))
    print(f"    method table -> {mt_new_va:#x} ({c2} entries, {len(mt_body)}B); "
          f"VMT slot {mt_slot_va:#x}: {mt_va:#x} -> {mt_new_va:#x}")

    backup = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup); print(f"    backup -> {backup}")

    newraw = align(len(d), F["falign"])
    d += b"\x00" * (newraw - len(d))
    rawsz = align(len(body), F["falign"])
    d += bytes(body) + b"\x00" * (rawsz - len(body))
    b = F["sectbl"] + F["nsec"]*40
    struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
    struct.pack_into("<IIHHI", d, b+24, 0, 0, 0, 0, 0x60000020)      # code|exec|read
    struct.pack_into("<H", d, F["e"]+6, F["nsec"]+1)
    struct.pack_into("<I", d, F["opt"]+56, align(newva + len(body), F["salign"]))
    # repoint: VMT method table + TMAINFORM resource data entry
    struct.pack_into("<I", d, rva2off(F["secs"], mt_slot_va - 0x400000), mt_new_va)
    struct.pack_into("<II", d, entry_off, dfm_new_rva, len(out))

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{EXE}] LOCKED - close the editor and retry"); return 1
    print(f"[{EXE}] written: .ctp @ rva {newva:#x} ({len(body)}B) = 2 stubs + "
          f"method table + DFM. Revert: no --undo here, and copying {os.path.basename(backup)} back is\n"
          f"        NOT a revert path -- it would drop every other AoWDevEd feature.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
