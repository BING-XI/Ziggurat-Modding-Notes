# -*- coding: utf-8 -*-
"""
spell_icons.py — extract the spell icons from Images/SpellIcn.ILB.

    python spell_icons.py                 write a labelled contact sheet (HTML)
    python spell_icons.py --png <dir>     also write one PNG per icon

FORMAT NOTES (worked out 2026-08-07; ilb.py could not read this file at all before,
because it stops at the first composite and every icon here is one).

A spell icon is a COMPOSITE entry plus exactly one sub-entry:
    composite header   40x35, clip [40,35,0,0]   -- the frame/background
    sub-entry          e.g. 35x28, clip [35,28,2,4] -- the icon art, inset at (x,y)
Both are Sprite16 (type 22): pixel data is UNCOMPRESSED RGB565 of the clip rectangle,
exactly clipw*cliph*2 bytes, and pixels equal to `transparent` are skipped when blitted.

Directory layout, which is what ilb.py got wrong:
  * a composite header carries FIVE trailing dwords ([clipw,cliph,clipx,clipy,transparent]),
    not four, and has NO trailer of its own -- its sub-entries follow immediately;
  * each SUB-entry has the same record shape minus the leading id, plus a trailer dword;
  * the sub-entry list is terminated by -1.
Walking SpellIcn.ILB this way consumes the directory to exactly `imgdir` (21657), which is
the check that the layout is right.

SPELL -> ICON (solved 2026-08-07). Each Spells.pfs record's image list (tag 0x0C) contains
the path "SPELLICN.ILB" followed by three filler bytes and a u32 icon index into this file.
All 108 spells carry one, every index resolves to an entry here, and no two spells share an
index. It is NOT the spell id and NOT the record id: Conceal Area is spell id 1, record 11,
icon 150. Testing id-equals-id fitted 88 of 108, which is exactly the kind of near-miss that
would have shipped wrong icons on twenty spells.
"""
import os, struct, sys, base64, io

TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
ILB = os.path.join(GAME, "Images", "SpellIcn.ILB")


def walk(d):
    """[(record, [sub-records])] for every top-level entry, in file order."""
    imgdir = struct.unpack_from("<I", d, 16)[0]
    o = 28

    def i32():
        nonlocal o
        v = struct.unpack_from("<i", d, o)[0]
        o += 4
        return v

    def rec(has_id):
        nonlocal o
        iid = i32() if has_id else None
        comp = False
        if has_id and struct.unpack_from("<i", d, o)[0] == 256:
            comp = True
            o += 4
        typ = i32()
        if typ == 0:
            i32()
            typ = i32()
        info = d[o]; o += 1
        nlen = i32()
        name = d[o:o + nlen].decode("latin1", "replace"); o += nlen
        w, h = i32(), i32()
        i32(); i32(); i32()                       # xshift, yshift, subid
        o += 1
        size = i32()
        off = i32() if info != 1 else None
        totw, toth = i32(), i32()
        r = dict(id=iid, typ=typ, info=info, name=name, w=w, h=h, size=size,
                 off=off, totw=totw, toth=toth, comp=comp)
        if typ in (16, 17, 18, 22):
            if info == 3:
                i32(); i32()
            i32()                                  # pixfmt marker 0x56509310
            if typ in (17, 18):
                r["clip"] = [i32() for _ in range(4)]
                r["transparent"] = i32(); i32()
        if typ == 22:
            r["clip_off"] = o          # file offset of the 5-dword [clipw,cliph,clipx,clipy,
            s = [i32() for _ in range(5)]   # transparent] block -- needed to PATCH a record,
            r["clip"], r["transparent"] = s[:4], s[4]   # not just read it.
        if info == 1 and size:
            o += size
        return r

    out = []
    while o < imgdir - 3:
        if struct.unpack_from("<i", d, o)[0] == -1:
            o += 4
            continue
        top = rec(True)
        subs = []
        if top["comp"]:
            while o < imgdir - 3:
                if struct.unpack_from("<i", d, o)[0] == -1:
                    o += 4
                    break
                subs.append(rec(False))
                i32()                              # sub trailer
        else:
            i32()                                  # trailer
        out.append((top, subs))
    if o != imgdir:
        raise ValueError("directory walk ended at %d, expected %d" % (o, imgdir))
    return out, imgdir


INK_FLOOR = 6               # alpha below this is invisible; skip the pixel entirely


def ink_alpha(v):
    """Overlay pixels are an INK MASK on white, not colour art — return 0-255 coverage.

    Measured over all 110 overlays: 25 pixels in the entire file are off-grey, against
    104,685 in the frames. The overlays are pure greyscale, ~80k pixels at full white and
    ~20k at full black, so each one is a monochrome stamp meant to be inked onto the
    coloured sphere disc underneath.

    Reading it as luminance -> alpha removes the halo *by construction*: the anti-aliasing
    ramp becomes a smooth fade to transparent instead of light-grey pixels sitting on a
    dark disc. Four colour-key rules were tried first and all of them fought the same
    symptom instead of the cause:
      * the record's `transparent` field  — wrong on half the file (55 overlays declare
        0x4148, a colour absent from their own pixels);
      * a hardcoded 0xFFFF               — missed five overlays cut against 0xFFDF;
      * the majority corner colour       — keys one shade of a dithered background;
      * band + halo erosion              — got close, but still thinned the artwork by
        eroding real edge pixels, and left 141 light pixels behind.
    Do not reintroduce a colour key here.
    """
    r = ((v >> 11) & 31) * 255 // 31
    g = ((v >> 5) & 63) * 255 // 63
    b = (v & 31) * 255 // 31
    return 255 - int(0.30 * r + 0.59 * g + 0.11 * b)


def blit(img, d, r, base, mode):
    """Paint one Sprite16 record. mode="frame" draws every pixel; mode="ink" treats the
    tile as a monochrome stamp and composites it as black with luminance-derived alpha.

    ⚠ The record's own `transparent` field is unusable in this file — frames declare four
    different values (0xFFFF, 0x4148, 0x00FF, 0x0000) while containing no white at all, so
    honouring it punches holes in the disc. Frames are opaque backgrounds, full stop.
    """
    from PIL import Image
    if r["typ"] != 22 or r["off"] is None:
        return
    cw, ch, cx, cy = r["clip"]
    need = cw * ch * 2
    if need != r["size"]:
        return                                     # not raw RGB565: skip rather than guess
    raw = d[base + r["off"]: base + r["off"] + need]
    tile = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    put = tile.load()
    for y in range(ch):
        row = y * cw * 2
        for x in range(cw):
            v = raw[row + x * 2] | (raw[row + x * 2 + 1] << 8)
            if mode == "ink":
                a = ink_alpha(v)
                if a >= INK_FLOOR:
                    put[x, y] = (0, 0, 0, a)
            else:
                put[x, y] = (((v >> 11) & 31) * 255 // 31,
                             ((v >> 5) & 63) * 255 // 63,
                             (v & 31) * 255 // 31, 255)
    img.alpha_composite(tile, (cx, cy))


def render(d, top, subs, base):
    from PIL import Image
    img = Image.new("RGBA", (top["totw"] or top["w"], top["toth"] or top["h"]), (0, 0, 0, 0))
    blit(img, d, top, base, "frame")
    for s in subs:
        blit(img, d, s, base, "ink")
    return img


def main():
    if not os.path.exists(ILB):
        sys.exit("not found: %s" % ILB)
    d = open(ILB, "rb").read()
    entries, base = walk(d)
    print("SpellIcn.ILB: %d top-level entries, %d sub-images"
          % (len(entries), sum(len(s) for _t, s in entries)))

    outdir = None
    if "--png" in sys.argv:
        outdir = sys.argv[sys.argv.index("--png") + 1]
        os.makedirs(outdir, exist_ok=True)

    # Labels come from the REAL mapping: each Spells.pfs record's images list (tag 0x0C)
    # names SPELLICN.ILB and stores the icon index as a u32 three bytes after the path.
    # All 108 resolve and none collide. It is NOT the spell id -- Conceal Area is spell 1,
    # icon 150.
    import json
    byid = {}
    # ⚠ spell_names.json lives in "Zig notes/". This path used to point one directory up,
    # and since `if os.path.exists(npath)` guards the whole labelling block, the miss was
    # SILENT: the contact sheet rebuilt fine and simply captioned all 111 icons
    # "no spell with this id". Found 2026-09-01 only because a new icon failed to pick up
    # its name. Try both locations and say so when neither is found.
    npath = os.path.join(GAME, "Modding Resources", "Zig notes", "spell_names.json")
    if not os.path.exists(npath):
        npath = os.path.join(GAME, "Modding Resources", "spell_names.json")
    if not os.path.exists(npath):
        print("  !! spell_names.json not found -- icons will be unlabelled")
    if os.path.exists(npath):
        import importlib.util
        mspec = importlib.util.spec_from_file_location(
            "mb", os.path.join(GAME, "Modding Resources", "build_ziggurat_manual.py"))
        mb = importlib.util.module_from_spec(mspec); mspec.loader.exec_module(mb)
        names = json.load(open(npath, encoding="utf-8"))
        for g in mb.read_game_spells():
            v = names.get(str(g["id"]))
            if v and g.get("icon") is not None:
                byid[g["icon"]] = v["name"]

    cells = []
    for top, subs in entries:
        img = render(d, top, subs, base)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        nm = byid.get(top["id"])
        cells.append('<figure class="%s"><img src="data:image/png;base64,%s" alt="icon %s">'
                     '<figcaption><b>%s</b><span>%s</span></figcaption></figure>'
                     % ("" if nm else "nomatch", b64, top["id"],
                        top["id"], nm or "&mdash; no spell with this id"))
        if outdir:
            img.save(os.path.join(outdir, "icon_%03d.png" % top["id"]))

    html = ("""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>SpellIcn.ILB contact sheet</title><style>
body{background:#e9dcc0;color:#332a1a;font-family:"Segoe UI",Arial,sans-serif;margin:24px}
h1{font-family:Georgia,serif;font-weight:400;color:#1d6a4f}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}
figure{margin:0;text-align:center;background:#faf4e6;border:1px solid #cebc95;
 border-radius:8px;padding:6px}
figure.nomatch{background:#f2e2d6;border-color:#c08a6a}
img{image-rendering:pixelated;width:80px;height:70px;object-fit:contain}
figcaption{font-size:11px;color:#332a1a;margin-top:3px;line-height:1.25}
figcaption b{display:block;font-size:10px;color:#7a6a4c;font-weight:400}
figcaption span{display:block}
</style></head><body><h1>SpellIcn.ILB &mdash; %d icons</h1>
<p>Each icon is captioned with its ILB entry id and, the spell that owns it, read from each
spell record's own icon index. Shaded cells are ILB entries no spell points at.</p><div class="grid">%s</div></body></html>"""
            % (len(cells), "".join(cells)))
    out = os.path.join(GAME, "Modding Resources", "Spell_Icons_ContactSheet.html")
    open(out, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB)" % (out, len(html.encode()) / 1024.0))
    if outdir:
        print("wrote %d PNGs to %s" % (len(cells), outdir))


if __name__ == "__main__":
    main()
