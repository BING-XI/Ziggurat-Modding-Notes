#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""unit_portraits.py — extract every unit's face portrait from the installed game data.

    python unit_portraits.py              write "Modding Resources/Unit_Portraits_ContactSheet.html"
                                          (self-contained; every face labelled with record id +
                                          race/name; misses listed at the bottom) + coverage stats
    python unit_portraits.py --png <dir>  also write one PNG per unit as unit_<id>.png

As a module:
    portraits()  -> {Unitres.pfs record id: PNG bytes}
    data_uris()  -> {Unitres.pfs record id: "data:image/png;base64,..."}
    misses()     -> [(record id, display name, reason)] for units with no decodable face

MAPPING (verified on this install, 2026-08-08):
    Unitres.pfs record  (classid 0x20212)
        tag 8, first dword = graphics id.  Absent on exactly one unit here (id 10, Human
                             Archer): the graphics id then defaults to the record id itself.
        tag 10 / tag 11    = race / name.  Raceless units keep the whole display name in
                             tag 10; two units (239 Necromancer, 240 Hydra) instead carry it
                             in tag 11 with no tag 10 at all — read both.
    -> Unitgfx.pfs record whose id == the graphics id  (classid 0x20210)
        tag 6 = face ILB path, ShortString, e.g. "FACES\UNITS.ILB"  (under <game>/Images)
        tag 8 = u32 face index into that ILB; absent = 0
        (tag 7 is a legacy display name — stale vanilla text on this install, diagnostics only)
    -> the ILB directory entry whose ENTRY ID equals that face index.

    ⚠ The face index is the ILB directory ENTRY ID, not the position in file order.  The two
    coincide when ids are dense from 0 (R_FACES, UNITS, ZIGFACES here), but H_FACES carries 67
    entries with ids 0..395 and L_FACES 26 with ids 0..63 — a positional read is out of range
    for most of their references.  This also dissolves the face_offset.json gotcha in Inioch's
    notes: a custom pack whose entry ids start at 1 merely *looks* 1-based to a positional
    reader.  Looked up by entry id, no correction is needed.  For parity with his convention a
    face_offset.json ({"FACES\\PACK.ILB": -1}) found next to this script or in
    Modding Resources/ is still honoured (added to the entry id); none exists on this install.

PIXEL DATA — two encodings, both from Inioch's notes; this install exercises only the first
(all 238 face entries are type 16, raw, 103x128):
    raw          size == w*h*2   literal RGB565 rows, decoded opaque (no face here contains
                                 the transparent key, measured over every entry)
    row-encoded  otherwise       per row [len:u16][xstart:u16][(len-4)/2 pixels]; the stride
                                 is len rounded UP to a multiple of 4 (the pad word looks like
                                 a pixel — classic shear trap); RGB565 0x4D2B = transparent

CREDIT: the Unitres -> Unitgfx -> face-ILB chain, both pixel encodings, the stride trap and
the transparent key colour are lifted from build_mod_manual.py by Inioch (AoWx project, 2026)
— see BUILD-YOUR-MOD-MANUAL.md alongside it.  The ILB directory walk that yields entry ids is
spell_icons.walk from this toolkit; record indexing is pfs.py.
"""
import base64
import io
import json
import os
import struct
import sys

# tools dir + game dir = two levels up from this script (<game>/Modding Resources/re_tools/);
# override with the AOW_GAME_DIR environment variable.
TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import pfs           # noqa: E402  (sys.path fix must precede)
import spell_icons   # noqa: E402  (for walk(), the ILB directory parser)

TRANSPARENT_KEY = 0x4D2B      # RGB565 key colour used by row-encoded face frames


def _face_offsets():
    """Per-ILB index corrections, Inioch's face_offset.json convention.  Unnecessary under
    entry-id lookup (see docstring) but honoured if someone ships one; {} when absent."""
    for where in (TOOLS, os.path.join(GAME, "Modding Resources")):
        p = os.path.join(where, "face_offset.json")
        if os.path.exists(p):
            try:
                return {k.upper(): int(v) for k, v in
                        json.load(open(p, encoding="utf-8")).items()}
            except (ValueError, OSError) as e:
                print("face_offset.json ignored (%s)" % e)
    return {}


def _ilb_path(rel):
    """<game>/Images/<rel> with a case-insensitive fallback per path component, so the
    tool also works on case-sensitive filesystems (paths in Unitgfx are all-caps, the
    files on disk are mixed-case)."""
    p = os.path.join(GAME, "Images", rel.replace("\\", os.sep))
    if os.path.exists(p):
        return p
    cur = os.path.join(GAME, "Images")
    for part in rel.replace("\\", "/").split("/"):
        if not os.path.isdir(cur):
            return None
        hit = next((f for f in os.listdir(cur) if f.lower() == part.lower()), None)
        if hit is None:
            return None
        cur = os.path.join(cur, hit)
    return cur


_ILB_CACHE = {}


def _ilb(rel):
    """(file bytes, {entry id: record}, data base) for a face ILB, or an error string."""
    key = rel.upper()
    if key in _ILB_CACHE:
        return _ILB_CACHE[key]
    out = "ILB not found: %s" % rel
    fp = _ilb_path(rel)
    if fp:
        try:
            d = open(fp, "rb").read()
            entries, base = spell_icons.walk(d)
            out = (d, {t["id"]: t for t, _subs in entries}, base)
        except (ValueError, struct.error, OSError) as e:
            out = "ILB walk failed for %s: %s" % (rel, e)
    _ILB_CACHE[key] = out
    return out


def _rgb565(v):
    return ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def _decode(d, base, t):
    """One face ILB entry -> PIL Image, or an error string.  Raw frames decode opaque RGB;
    row-encoded frames (none in this install's face files) decode RGBA with the key colour
    transparent, exactly per Inioch's decode_frame."""
    from PIL import Image
    if t["off"] is None:
        return "inline pixel data (info==1) not handled"
    w, h = t["w"], t["h"]
    st = base + t["off"]
    if w > 0 and h > 0 and t["size"] == w * h * 2:
        # raw 16bpp: literal RGB565, row-major
        im = Image.new("RGB", (w, h))
        px = im.load()
        raw = d[st:st + w * h * 2]
        if len(raw) < w * h * 2:
            return "pixel data truncated"
        for k in range(w * h):
            px[k % w, k // w] = _rgb565(raw[2 * k] | (raw[2 * k + 1] << 8))
        return im
    # row-encoded 16bpp: dims are the sub-image's (clip rect when the record carries one)
    cw, ch = (t.get("clip") or [w, h])[0:2]
    if not (0 < cw < 512 and 0 < ch < 512):
        return "implausible row-encoded dimensions %dx%d" % (cw, ch)
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    px = im.load()
    q, end, y = st, st + t["size"], 0
    while q + 4 <= end and y < ch:
        ln, xs = struct.unpack_from("<HH", d, q)
        if ln < 4:
            break
        for i in range((ln - 4) // 2):
            x = xs + i
            if x < cw:
                v = struct.unpack_from("<H", d, q + 4 + i * 2)[0]
                if v != TRANSPARENT_KEY:
                    px[x, y] = _rgb565(v) + (255,)
        q += (ln + 3) & ~3      # stride rounds UP to a multiple of 4 — the pad word trap
        y += 1
    return im


def unit_faces():
    """[(record id, race, name, display, face ref)] for every Unitres.pfs record, in id
    order.  face ref is (ILB path, entry id) or an explanatory string when unresolvable."""
    offs = _face_offsets()
    grecs, _gkey = pfs.load("Unitgfx.pfs")
    gfx = {}
    for rid, body in grecs:
        try:
            gfx[rid] = pfs.parse_dir(body, top=True)
        except (ValueError, IndexError):
            pass
    out = []
    urecs, ukey = pfs.load("Unitres.pfs")
    for rid, body in urecs:
        try:
            f = pfs.parse_dir(body, top=True)
        except (ValueError, IndexError):
            out.append((rid, "", "", "record %d" % rid, "Unitres record unparseable"))
            continue
        race = pfs.pstr(f.get(10, b""))
        name = pfs.pstr(f.get(11, b""))
        display = pfs.name_of(f, ukey)
        gid = pfs.u32(f.get(8, b""), rid) if 8 in f else rid
        g = gfx.get(gid)
        if g is None:
            ref = "no Unitgfx record %d" % gid
        elif 6 not in g:
            ref = "Unitgfx record %d has no face path (tag 6)" % gid
        else:
            path = pfs.pstr(g[6])
            idx = (pfs.u32(g.get(8, b""), 0) if 8 in g else 0) + offs.get(path.upper(), 0)
            ref = (path, idx)
        out.append((rid, race, name, display, ref))
    return out


_PORTRAITS = None
_MISSES = None


def _build():
    global _PORTRAITS, _MISSES
    if _PORTRAITS is not None:
        return
    _PORTRAITS, _MISSES = {}, []
    for rid, _race, _name, display, ref in unit_faces():
        if isinstance(ref, str):
            _MISSES.append((rid, display, ref))
            continue
        path, idx = ref
        ilb = _ilb(path)
        if isinstance(ilb, str):
            _MISSES.append((rid, display, ilb))
            continue
        d, byid, base = ilb
        if idx not in byid:
            _MISSES.append((rid, display, "no entry id %d in %s" % (idx, path)))
            continue
        im = _decode(d, base, byid[idx])
        if isinstance(im, str):
            _MISSES.append((rid, display, "%s #%d: %s" % (path, idx, im)))
            continue
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        _PORTRAITS[rid] = buf.getvalue()


def portraits():
    """{Unitres.pfs record id: PNG bytes} for every unit whose face resolves and decodes."""
    _build()
    return dict(_PORTRAITS)


def data_uris():
    """{Unitres.pfs record id: "data:image/png;base64,..."} — portraits() ready for HTML."""
    return {rid: "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            for rid, png in portraits().items()}


def misses():
    """[(record id, display name, reason)] for every unit portraits() could not produce."""
    _build()
    return list(_MISSES)


# ---------------------------------------------------------------- CLI: contact sheet
def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    faces = unit_faces()
    pngs = portraits()
    uris = data_uris()
    miss = misses()

    outdir = None
    if "--png" in sys.argv:
        outdir = sys.argv[sys.argv.index("--png") + 1]
        os.makedirs(outdir, exist_ok=True)

    cells = []
    for rid, _race, _name, display, ref in faces:
        if rid not in uris:
            continue
        src = "%s #%d" % (ref[0].split("\\")[-1], ref[1])
        cells.append('<figure><img src="%s" alt="unit %d"><figcaption><b>%d</b>%s'
                     '<span>%s</span></figcaption></figure>'
                     % (uris[rid], rid, rid, _esc(display), _esc(src)))
        if outdir:
            open(os.path.join(outdir, "unit_%03d.png" % rid), "wb").write(pngs[rid])

    misslist = "".join("<li><b>%d</b> %s &mdash; %s</li>" % (rid, _esc(nm), _esc(why))
                       for rid, nm, why in miss) or "<li>none</li>"
    html = ("""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Unit portraits contact sheet</title><style>
body{background:#e9dcc0;color:#332a1a;font-family:"Segoe UI",Arial,sans-serif;margin:24px}
h1{font-family:Georgia,serif;font-weight:400;color:#1d6a4f}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px}
figure{margin:0;text-align:center;background:#faf4e6;border:1px solid #cebc95;
 border-radius:8px;padding:6px}
img{width:103px;height:128px;object-fit:contain;border-radius:4px}
figcaption{font-size:12px;margin-top:3px;line-height:1.3}
figcaption b{display:inline-block;margin-right:4px;color:#7a6a4c;font-weight:400}
figcaption span{display:block;font-size:10px;color:#98865f}
ul{columns:2;font-size:13px}
</style></head><body><h1>Unit portraits &mdash; %d of %d Unitres.pfs records</h1>
<p>Chain: Unitres tag 8 (graphics id, default = record id) &rarr; Unitgfx tag 6 (face ILB)
+ tag 8 (entry id) &rarr; ILB directory entry.  Captions: record id, display name, source
ILB entry.  Generated by re_tools/unit_portraits.py.</p>
<div class="grid">%s</div>
<h2>Without a portrait</h2><ul>%s</ul></body></html>"""
            % (len(cells), len(faces), "".join(cells), misslist))

    out = os.path.join(GAME, "Modding Resources", "Unit_Portraits_ContactSheet.html")
    open(out, "w", encoding="utf-8").write(html)

    total = sum(len(p) for p in pngs.values())
    print("portraits: %d of %d Unitres records (%.1f%%)"
          % (len(pngs), len(faces), 100.0 * len(pngs) / max(1, len(faces))))
    for rid, nm, why in miss:
        print("  miss: %d %s -- %s" % (rid, nm, why))
    print("PNG bytes: %d total (%.1f KB avg); base64-inflated ~%d"
          % (total, total / 1024.0 / max(1, len(pngs)), (total + 2) // 3 * 4))
    print("wrote %s (%.0f KB)" % (out, len(html.encode("utf-8")) / 1024.0))
    if outdir:
        print("wrote %d PNGs to %s" % (len(pngs), outdir))


if __name__ == "__main__":
    main()
