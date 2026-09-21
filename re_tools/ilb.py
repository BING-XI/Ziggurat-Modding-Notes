"""ILB (Age of Wonders image library) directory parser.

Format per 'ILB desc.pdf' (bundled in IlbMaker_Release_1.0.2.7.7z).  Handles the
v3.0/v4.0 headers and walks the image directory; per-image pixel data is located
by (size, offset) so it is NOT decoded here -- this is for inventory/indexing.

Calibrated against Images/_Combat.ILB (2026-07-30): type 22 (Sprite16) carries
FIVE extra dwords after pixfmt (FOUR when the entry is composite), and they are
`[clipw, cliph, clipx, clipy, transparent]` (exposed as rec["s16"]).

**Sprite16 pixel data is UNCOMPRESSED RGB565 of the clip rectangle** -- exactly
clipw*cliph*2 bytes, row-major, with pixels equal to `transparent` skipped when
blitted.  (Verified: the 21x19 medal has clip 7x13 and size 182 = 7*13*2; the
vanilla 11x10 one has clip 3x6 and size 36.)  So re-skinning or cloning a
Sprite16 is a straight pixel rewrite -- no codec needed, unlike RLESprite16
(types 17/18), which ilb_rle16.py handles.

Image data offsets are relative to `imgdir` (the header's data-start dword), so
inserting a directory entry and bumping imgdir keeps every existing image valid.
See build_scripts/build_copper_medal.py for a worked splice.

Composite
entries (marker dword 256 after the id) are followed by SUB-entries (same record
shape but no leading id) before the -1 trailer; sub-entry walking is NOT
implemented, so the walk now STOPS at the first composite instead of silently
drifting (Combat.ILB: entries 0..126 parse, the tail after composite id 130
does not).  Image ids can skip values; the id FIELD, not the list position, is
what TCustomImageLibrary.Get() looks up.

Usage:
  ilb.py <file.ilb> [--all]              -- header + image list
  ilb.py <file.ilb> --idx 182            -- describe one image index
Also importable:  parse(bytes) -> dict(hdr=..., images=[...])
"""
import os, struct, sys

TYPES = {1: "Picture08", 2: "RLESprite08", 16: "Picture16", 17: "RLESprite16",
         18: "TransparentRLESprite16", 19: "BitMask", 20: "Shadow", 22: "Sprite16"}


def parse(d):
    assert d[0:4] == b"\x04ILB", "not an ILB (bad magic)"
    someid, ver, hdrlen = struct.unpack_from("<IfI", d, 4)
    o = 16
    hdr = dict(someid=someid, version=ver, hdrlen=hdrlen)
    if abs(ver - 4.0) < 1e-6:
        imgdir, filelen, npal = struct.unpack_from("<III", d, o)
        hdr.update(imgdir=imgdir, filelen=filelen, npal=npal)
        o += 12
        # each palette: identifier word + 256 entries (skip via the stated data start)
        pal = []
        for _ in range(npal):
            ident = struct.unpack_from("<I", d, o)[0]
            pal.append(ident)
            o += 4 + 256*4
        hdr["palettes"] = pal
        dir_end = imgdir
    else:
        hdr.update(imgdir=None, filelen=None, npal=0)
        o += 4                      # v3.0 has one trailing unknown
        dir_end = len(d)

    def i32():
        nonlocal o
        v = struct.unpack_from("<i", d, o)[0]; o += 4; return v
    def u8():
        nonlocal o
        v = d[o]; o += 1; return v

    images = []
    while o < dir_end - 3:
        start = o
        iid = i32()
        if iid == -1:
            break
        composite = False
        nxt = struct.unpack_from("<i", d, o)[0]
        if nxt == 256:
            composite = True; o += 4
            nxt = struct.unpack_from("<i", d, o)[0]
        typ = i32()
        if typ == 0:
            i32()                                   # ZeroFiller
            typ = i32()
        info = u8()
        nlen = i32()
        name = d[o:o+nlen].decode("latin1", "replace"); o += nlen
        wide, high, xsh, ysh, subid = (i32() for _ in range(5))
        u8()                                        # unknownA
        size = i32()
        offset = i32() if info != 1 else None
        totw, toth = i32(), i32()
        rec = dict(idx=len(images), id=iid, type=typ, tname=TYPES.get(typ, f"?{typ}"),
                   info=info, name=name, w=wide, h=high, xsh=xsh, ysh=ysh,
                   subid=subid, size=size, offset=offset, totw=totw, toth=toth,
                   composite=composite, dir_off=start)
        if typ in (16, 17, 18, 22):
            if info == 3:
                rec["drawmode"], rec["blend"] = i32(), i32()
            rec["pixfmt"] = i32()
            if typ in (17, 18):
                rec["clipw"], rec["cliph"] = i32(), i32()
                rec["clipx"], rec["clipy"] = i32(), i32()
                rec["transparent"] = i32()
                i32()                               # unknownE
        elif typ == 2:
            u8(); i32(); i32()
            rec["palette"] = i32()
            rec["clipw"], rec["cliph"] = i32(), i32()
            rec["clipx"], rec["clipy"] = i32(), i32()
            rec["transparent"] = i32()
            i32()
        if typ == 22:                               # Sprite16: extra dwords (4 if composite)
            rec["s16"] = [i32() for _ in range(4 if composite else 5)]
        if info == 1 and size:
            rec["inline_data"] = (o, size); o += size
        last = i32()                                # per-image trailer, always -1
        rec["trailer_ok"] = (last == -1)
        images.append(rec)
        if composite:                               # sub-entries not implemented: stop cleanly
            rec["truncated_walk"] = True
            break
    return dict(hdr=hdr, images=images, dir_consumed=o, dir_end=dir_end)


def main():
    p = sys.argv[1]
    if not os.path.isabs(p):
        p = os.path.abspath(p)
    d = open(p, "rb").read()
    r = parse(d)
    h = r["hdr"]
    print(f"{os.path.basename(p)}: {len(d)} bytes, version {h['version']:.1f}, "
          f"hdrlen {h['hdrlen']}, imgdir {h['imgdir']}, filelen {h['filelen']}, "
          f"palettes {h['npal']}")
    print(f"IMAGES: {len(r['images'])}   (directory consumed to {r['dir_consumed']}, "
          f"data starts {r['dir_end']}, clean={r['dir_consumed'] <= r['dir_end']})")
    if "--idx" in sys.argv:
        i = int(sys.argv[sys.argv.index("--idx")+1])
        for im in r["images"]:
            if im["idx"] == i:
                for k, v in im.items():
                    print(f"   {k:12} {v}")
        return
    show = r["images"] if "--all" in sys.argv else r["images"][:12]
    for im in show:
        print(f"  [{im['idx']:4}] id={im['id']:<6} {im['tname']:<22} "
              f"{im['w']:3}x{im['h']:<3} tot {im['totw']:3}x{im['toth']:<3} "
              f"off={im['offset']} size={im['size']:<6} {im['name']!r}"
              f"{' COMPOSITE' if im['composite'] else ''}")
    if not ("--all" in sys.argv) and len(r["images"]) > 12:
        print(f"  ... ({len(r['images'])-12} more; --all to list)")


if __name__ == "__main__":
    main()
