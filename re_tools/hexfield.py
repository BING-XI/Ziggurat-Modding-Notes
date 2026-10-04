"""Hex-field toolkit: tile geometry, ILB record I/O, a multi-run RLESprite16 encoder, and an
offline renderer that reproduces AoW1's static/dynamic hexagon draw order.

Geometry (HSEngine.HXtoHP, HSEPack 5560E3B4): a hex's tile origin is (hx*32, hy*32 + (hx&1)*16);
the 48x32 tile silhouette widens 18 -> 48 px over rows 0..15 and narrows back, so neighbouring
tiles overlap by one pixel column.  HN directions 1..6 = N, NE, SE, S, SW, NW.

Draw order (TAbstractHexagon.GetShowPriority, HSEPack 5560A4DC): hexagons paint in (py, px)
order, each one = base tile, then its transitions (THexagonResource.Show, HSEPack 55611FA4).
A hexagon owns its three UPPER edges (NW, N, NE = HN 6, 1, 2) and draws each edge image at
(x-6, y-9) -- or at the upper neighbour's origin + (-6,-9) when the "displaced" flag is set.
Water/ice hexes then paint their shores every frame (TAoWWaterHexagon.ShowDynamic, AoWEPACK
5579AFB4), on top of the whole static scene.

ILB records: see ilb.py for the field list.  `read_records` keeps every record's raw bytes so
`record_bytes` can re-serialise a template with new geometry; the round-trip is asserted by the
callers before anything is written.

RLESprite16 rows (verified against every image in HexTrans/Waterhex/IceHex.ILB, 10003 rows):
  u32 reclen, then a mix of literal RGB565 pixels and transparent runs `u16 transparent, u16
  nbytes`; runs may sit anywhere in the row, never two in a row, never zero-length; an empty
  row is one run of the full width; the next record starts at align4(start + reclen).
"""
import math, os, re, struct, sys, collections, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ilb  # noqa: E402

# ----------------------------------------------------------------------------- geometry
ROW = [(15 - y, 32 + y) if y < 16 else (y - 16, 63 - y) for y in range(32)]
DIRV = {1: (0, -32), 2: (32, -16), 3: (32, 16), 4: (0, 32), 5: (-32, 16), 6: (-32, -16)}
VERT = {'TL': (15, 0), 'TR': (33, 0), 'R': (48, 16), 'BR': (33, 32), 'BL': (15, 32), 'L': (0, 16)}
EDGE = {1: ('TL', 'TR'), 2: ('TR', 'R'), 3: ('R', 'BR'), 4: ('BR', 'BL'), 5: ('BL', 'L'), 6: ('L', 'TL')}


def in_tile(x, y):
    return 0 <= y < 32 and ROW[y][0] <= x <= ROW[y][1]


def origin(hx, hy):
    return hx * 32, hy * 32 + (hx & 1) * 16


def px2hex(ox, oy):
    """tile origin (pixels) -> lattice coords"""
    X = ox // 32
    return X, (oy - (X & 1) * 16) // 32


def hex_at(x, y):
    """every lattice hex whose tile silhouette contains pixel (x, y)"""
    out = []
    for hx in (x // 32 - 1, x // 32):
        ox, oy = hx * 32, ((y - (hx & 1) * 16) // 32) * 32 + (hx & 1) * 16
        if in_tile(x - ox, y - oy):
            out.append(px2hex(ox, oy))
    return out


def primary(x, y):
    """the one hex a pixel belongs to (nearest centre) -- for overlap-column pixels"""
    hs = hex_at(x, y)
    if len(hs) == 1:
        return hs[0]
    return min(hs, key=lambda h: (x + .5 - origin(*h)[0] - 24) ** 2 + (y + .5 - origin(*h)[1] - 16) ** 2)


def neighbour(hx, hy, d):
    ox, oy = origin(hx, hy)
    return px2hex(ox + DIRV[d][0], oy + DIRV[d][1])


def edge_seg(d, ox=0, oy=0):
    (ax, ay), (bx, by) = VERT[EDGE[d][0]], VERT[EDGE[d][1]]
    return (ax + ox, ay + oy), (bx + ox, by + oy)


def seg_dist(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    vx, vy = bx - ax, by - ay
    t = ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)
    tc = min(1.0, max(0.0, t))
    return math.hypot(px - ax - tc * vx, py - ay - tc * vy), t


# ----------------------------------------------------------------------------- colour
def to565(c):
    r, g, b = c[:3]
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def from565(v):
    R, G, B = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (R << 3) | (R >> 2), (G << 2) | (G >> 4), (B << 3) | (B >> 2)


# ----------------------------------------------------------------------------- RLE16
def rle_decode(data, w, h, tr):
    rows, pos = [], 0
    for _ in range(h):
        reclen = struct.unpack_from("<I", data, pos)[0]
        a, b, px = pos + 4, pos + reclen, []
        while a < b:
            v = struct.unpack_from("<H", data, a)[0]
            if v == tr:
                px += [None] * (struct.unpack_from("<H", data, a + 2)[0] // 2); a += 4
            else:
                px.append(v); a += 2
        rows.append((px + [None] * w)[:w])
        pos = (pos + reclen + 3) & ~3
    if pos != len(data) and not (len(data) - 3 <= pos <= len(data)):
        raise ValueError("RLE size mismatch")
    return rows


def rle_encode(rows, tr):
    """rows: lists of RGB565 ints / None, all the same width.  Opaque pixels must not equal tr."""
    out = bytearray()
    for px in rows:
        body, i, w = bytearray(), 0, len(px)
        while i < w:
            j = i
            if px[i] is None:
                while j < w and px[j] is None:
                    j += 1
                body += struct.pack("<HH", tr, (j - i) * 2)
            else:
                while j < w and px[j] is not None:
                    if px[j] == tr:
                        raise ValueError("opaque pixel equals the transparent colour")
                    body += struct.pack("<H", px[j]); j += 1
            i = j
        out += struct.pack("<I", len(body) + 4) + body
        while len(out) & 3:
            out += struct.pack("<H", tr)[len(out) & 1:][:1]
    return bytes(out)


# ----------------------------------------------------------------------------- ILB records
def read_records(d):
    """-> dict(hdr, recs, dir_end) ; each rec has its raw bytes and every field incl. unknowns.
    Supports what HexTrans/Waterhex/IceHex use: v4.0, no palettes, types 17/18, info 2/3."""
    assert d[:4] == b"\x04ILB"
    _, ver, hdrlen, imgdir, filelen, npal = struct.unpack_from("<IfIIII", d, 4)
    assert abs(ver - 4.0) < 1e-6 and npal == 0 and filelen == len(d), "unsupported ILB header"
    o, recs = 28, []
    def i32():
        nonlocal o
        v = struct.unpack_from("<i", d, o)[0]; o += 4; return v
    while True:
        start = o
        iid = i32()
        if iid == -1:
            break
        r = dict(id=iid, start=start)
        r['type'] = i32()
        assert r['type'] in (17, 18), "unsupported image type %d" % r['type']
        r['info'] = d[o]; o += 1
        assert r['info'] in (2, 3), "unsupported info %d" % r['info']
        n = i32(); r['name'] = d[o:o + n]; o += n
        r['w'], r['h'], r['xsh'], r['ysh'], r['subid'] = (i32() for _ in range(5))
        r['unkA'] = d[o]; o += 1
        r['size'], r['offset'], r['totw'], r['toth'] = (i32() for _ in range(4))
        if r['info'] == 3:
            r['drawmode'], r['blend'] = i32(), i32()
        r['pixfmt'], r['clipw'], r['cliph'], r['clipx'], r['clipy'], r['tr'], r['unkE'] = \
            (i32() for _ in range(7))
        assert i32() == -1, "record trailer"
        r['raw'] = d[start:o]
        recs.append(r)
    assert o == imgdir, "directory does not end at imgdir"
    return dict(imgdir=imgdir, recs=recs, term=o - 4)


def record_bytes(r):
    b = struct.pack("<ii", r['id'], r['type']) + bytes([r['info']])
    b += struct.pack("<i", len(r['name'])) + r['name']
    b += struct.pack("<5i", r['w'], r['h'], r['xsh'], r['ysh'], r['subid']) + bytes([r['unkA']])
    b += struct.pack("<4i", r['size'], r['offset'], r['totw'], r['toth'])
    if r['info'] == 3:
        b += struct.pack("<2i", r['drawmode'], r['blend'])
    b += struct.pack("<7i", r['pixfmt'], r['clipw'], r['cliph'], r['clipx'], r['clipy'], r['tr'], r['unkE'])
    return b + struct.pack("<i", -1)


def image_record(tpl, iid, name, img, tr):
    """img: RGBA PIL image (frame).  -> (record dict, RLE payload) ; clip = opaque bbox."""
    px = img.load()
    W, H = img.size
    xs = [x for x in range(W) for y in range(H) if px[x, y][3]]
    ys = [y for x in range(W) for y in range(H) if px[x, y][3]]
    if not xs:
        x0 = y0 = 0; x1 = y1 = 0
    else:
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    rows = []
    for y in range(y0, y1 + 1):
        row = []
        for x in range(x0, x1 + 1):
            c = px[x, y]
            if not c[3]:
                row.append(None)
            else:
                v = to565(c)
                row.append(v ^ 1 if v == tr else v)
        rows.append(row)
    payload = rle_encode(rows, tr)
    r = dict(tpl)
    r.update(id=iid, name=name.encode("latin1"), w=W, h=H, xsh=0, ysh=0, subid=0, size=len(payload),
             totw=W, toth=H, clipw=x1 - x0 + 1, cliph=y1 - y0 + 1, clipx=x0, clipy=y0, tr=tr)
    return r, payload


def ilb_append(d, new):
    """Append [(record, payload)] at the end of the directory and of the pixel data."""
    R = read_records(d)
    imgdir, data_len = R['imgdir'], len(d) - R['imgdir']
    recbytes, payload = bytearray(), bytearray()
    for r, p in new:
        r = dict(r); r['offset'] = data_len + len(payload)
        recbytes += record_bytes(r); payload += p
        while len(payload) & 3:
            payload += b"\x00"
    out = bytearray(d[:R['term']]) + recbytes + d[R['term']:] + payload
    struct.pack_into("<I", out, 16, imgdir + len(recbytes))
    struct.pack_into("<I", out, 20, len(out))
    return bytes(out)


def ilb_strip(d, ids):
    """Remove records whose id is in `ids`.  They must be the directory tail AND own the pixel-data
    tail (which is how ilb_append leaves them); anything else -> ValueError (refuse, never guess)."""
    R = read_records(d)
    recs = R['recs']
    k = len(recs)
    while k and recs[k - 1]['id'] in ids:
        k -= 1
    mine, keep = recs[k:], recs[:k]
    if any(r['id'] in ids for r in keep):
        raise ValueError("our images are not the directory tail -- something was appended after them")
    if not mine:
        return d
    cut = min(r['offset'] for r in mine)
    if any(r['offset'] + r['size'] > cut for r in keep):
        raise ValueError("pixel data of a foreign image lies after ours")
    dir_cut = mine[0]['start']
    shrink = R['term'] - dir_cut
    out = bytearray(d[:dir_cut]) + d[R['term']:R['imgdir']] + d[R['imgdir']:R['imgdir'] + cut]
    struct.pack_into("<I", out, 16, R['imgdir'] - shrink)
    struct.pack_into("<I", out, 20, len(out))
    return bytes(out)


def decode_image(d, rec, imgdir=None):
    """record (from read_records or ilb.parse) -> RGBA PIL image of the full frame"""
    from PIL import Image
    if imgdir is None:
        imgdir = read_records(d)['imgdir']
    tr = rec.get('tr', rec.get('transparent'))
    data = d[imgdir + rec['offset']: imgdir + rec['offset'] + rec['size']]
    im = Image.new("RGBA", (rec['w'], rec['h']), (0, 0, 0, 0))
    px = im.load()
    for y, row in enumerate(rle_decode(data, rec['clipw'], rec['cliph'], tr)):
        for x, v in enumerate(row):
            if v is not None:
                px[x + rec['clipx'], y + rec['clipy']] = from565(v) + (255,)
    return im


class Lib:
    """lazy image access by id; `extra` overrides/adds images (for previews)"""
    def __init__(self, path=None, data=None):
        self.d = data if data is not None else open(path, "rb").read()
        R = read_records(self.d)
        self.imgdir, self.recs = R['imgdir'], {r['id']: r for r in R['recs']}
        self.cache = {}

    def get(self, iid):
        if iid in self.cache:
            return self.cache[iid]
        r = self.recs.get(iid)
        if r is None:
            return None
        self.cache[iid] = decode_image(self.d, r, self.imgdir)
        return self.cache[iid]


def hss_tiles(hss_path):
    """terrain -> [48x32 RGBA tiles] in file order, from the embedded hexagon resources
    (signature `01 00 00 00 <terrain> FE` before each `\\x04ILB\\x00`)."""
    from PIL import Image  # noqa: F401
    data = open(hss_path, "rb").read()
    out = collections.defaultdict(list)
    for m in re.finditer(rb"\x04ILB\x00", data):
        s = m.start()
        if data[s - 6:s - 2] != b"\x01\x00\x00\x00" or data[s - 1] != 0xFE:
            continue
        blob = data[s:s + struct.unpack_from("<I", data, s + 20)[0]]
        try:
            P = ilb.parse(blob)
        except Exception:
            continue
        for r in P["images"]:
            if r["type"] == 17 and r["w"] == 48 and r["h"] == 32:
                out[data[s - 2]].append(decode_image(blob, r, P["hdr"]["imgdir"]))
    return out


# ----------------------------------------------------------------------------- renderer
WATERFAM, VOID = {0, 6}, {0xB, 0xE}


def _h(*a):
    return int(hashlib.md5(repr(a).encode()).hexdigest()[:8], 16)


def vanilla_rule(O, N, d, r):
    """TAoWHexagon.UpdateTransition (AoWEPACK 5579A9E0) after the remap cave -> (id, displaced)"""
    if N == O or O < 0 or N < 0 or N in (7, 8, 15) or O == 15:
        return None
    if O == 9:
        if N in (0xA, 0xD): return (0xB6 + d + 3 * r, False)
        return None if N in (7, 8) else (0x93 + d, True)
    if N == 9:
        if O in (0xA, 0xD): return (0xB6 + d + 3 * r, False)
        return None if O in (7, 8) else (0x90 + d, False)
    if O == 0xD: return (0xD0 + d, False) if N == 0xA else (0xD9 + d, True)
    if N == 0xD: return (0xD3 + d, True) if O == 0xA else (0xD6 + d, False)
    if O == 0xA: return (0xA3 + d, True)
    if N == 0xA: return (0xA0 + d, False)
    if N in (0, 6): return None
    if O == 6: return (0x60 + d, False) if N == 0 else (N * 16 + 3 + d, True)
    if O == 0: return (3 + d, True)
    return (O * 16 + 6 + d + 3 * r, False)


def shore_pieces(m, r):
    """TAoWWaterHexagon.ShowDynamic 5579B1DE..5579B546: land mask -> [(piece, dy)].
    r = per-hex variant 0..2.  Vanilla gap: masks {3,5} and {1,3,5} draw no SW piece."""
    out = []
    if not m:
        return out
    if m & 1:
        if m & 0x23 == 0x23: out.append((6, 0))
        elif m & 0x23 == 1: out.append((0xd, 0))
        if m & 7 == 7: out.append((0x19, 0))
        elif m & 3 == 3: out.append((3 + r, 0))
        if m & 0x31 == 0x31: out.append((0x18, 0))
        elif m & 0x21 == 0x21: out.append((r, 0))
    else:
        if m & 6 == 6: out.append((0xa + r, 0))
        elif m & 2: out.append((0x11, 0))
        if m & 0x30 == 0x30: out.append((7 + r, 0))
        elif m & 0x20: out.append((0x10, 0))
    if m & 8:
        if m & 0xe == 0xe: out.append((0x16, 1))
        elif m & 0xc == 0xc: out.append((0x13, 1) if r == 2 else (0x1e + r, 1))
        if m & 0x38 == 0x38: out.append((0x15, 0))
        elif m & 0x18 == 0x18: out.append((0x12, 1) if r == 2 else (0x1c + r, 0))
        if m & 0x1c == 8: out.append((0x17, 0))
    else:
        if m & 0xe == 4: out.append((0xf, 0))
        elif m & 0x38 == 0x10: out.append((0xe, 0))
    return out


# which direction's per-dir base each shore piece reads, and which edges it stands for
PIECE_BASEDIR = {**{k: 6 for k in (0, 1, 2, 16, 24)}, **{k: 2 for k in (3, 4, 5, 17, 25)},
                 **{k: 1 for k in (6, 13)}, **{k: 5 for k in (7, 8, 9, 14, 18, 21, 28, 29)},
                 **{k: 3 for k in (10, 11, 12, 15, 19, 22, 30, 31)}, 23: 4}
PIECE_EDGES = {0: {1, 6}, 1: {1, 6}, 2: {1, 6}, 3: {1, 2}, 4: {1, 2}, 5: {1, 2}, 6: {1},
               7: {5, 6}, 8: {5, 6}, 9: {5, 6}, 10: {2, 3}, 11: {2, 3}, 12: {2, 3}, 13: {1},
               14: {5}, 15: {3}, 16: {6}, 17: {2}, 18: {4, 5}, 19: {3, 4}, 21: {4, 5, 6},
               22: {2, 3, 4}, 23: {4}, 24: {1, 5, 6}, 25: {1, 2, 3}, 28: {4, 5}, 29: {4, 5},
               30: {3, 4}, 31: {3, 4}}
PIECE_DY = {18: 1, 19: 1, 22: 1, 30: 1, 31: 1}


def render(M, ht, wl, il, tiles, rule=None, shore_base=None, after_hex=None, margin=40):
    """M: {(hx,hy): terrain}.  rule(O,N,d,r) -> (id, displaced)|None ; shore_base(N) -> base|None ;
    after_hex(T, hx, hy) -> [(img, dx, dy)] drawn after a hex's transitions."""
    from PIL import Image
    rule = rule or vanilla_rule
    W = max(k[0] for k in M) + 1; H = max(k[1] for k in M) + 1
    img = Image.new("RGBA", (W * 32 + 16 + 2 * margin, H * 32 + 16 + 2 * margin), (0, 0, 0, 255))

    def T(hx, hy):
        return M.get((hx, hy), -1)

    def blit(im, x, y):
        if im is not None:
            img.paste(im, (x + margin, y + margin), im)

    def tile(t, hx, hy):
        if t in WATERFAM:
            return (wl if t == 0 else il).get(0x8C + _h('v', hx, hy) % 16)
        vs = tiles[t]
        return vs[_h('v', hx, hy) % len(vs)]

    key = lambda k: (origin(*k)[1], origin(*k)[0])
    for hx, hy in sorted(M, key=key):
        t = M[(hx, hy)]; x, y = origin(hx, hy)
        blit(tile(t, hx, hy), x, y)
        if t in WATERFAM:
            continue
        for d, dirn in enumerate((6, 1, 2)):
            N = T(*neighbour(hx, hy, dirn))
            if N < 0:
                continue
            res = rule(t, N, d, _h('r', hx, hy, d) % 3)
            if res:
                ox, oy = DIRV[dirn] if res[1] else (0, 0)
                blit(ht.get(res[0]), x - 6 + ox, y - 9 + oy)
        if after_hex:
            for im, dx, dy in after_hex(T, hx, hy):
                blit(im, x + dx, y + dy)
    for hx, hy in sorted([k for k in M if M[k] in WATERFAM], key=key):
        t = M[(hx, hy)]; x, y = origin(hx, hy)
        lib = wl if t == 0 else il
        m, base = 0, {}
        for d in range(1, 7):
            N = T(*neighbour(hx, hy, d))
            if N < 0 or N in WATERFAM or N == 15:
                continue
            m |= 1 << (d - 1)
            b = shore_base(N) if shore_base else None
            base[d] = b if b is not None else (0x28 if N == 3 else 0x50 if N == 5 else 0)
        r = _h('rr', hx, hy) % 4
        for k, dy in shore_pieces(m, 0 if r == 3 else r):
            blit(lib.get(base[PIECE_BASEDIR[k]] + k), x - 19, y - 32 + dy)
    return img


# self-check of the shore edge-set model against the transcription
for _m in range(1, 64):
    for _r in range(3):
        _u = set()
        for _k, _ in shore_pieces(_m, _r):
            _u |= PIECE_EDGES[_k]
        assert _u <= {d for d in range(1, 7) if _m >> (d - 1) & 1}
