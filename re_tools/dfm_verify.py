#!/usr/bin/env python3
r"""Cross-check a patched Delphi form: its DFM resource against its VMT tables.

    python dfm_verify.py AoWDevEd.exe TNewMapDlg

WHY
  "A form whose DFM, field table or InstanceSize is wrong fails at LOAD, and every
  static check still passes" is the standing hazard of every dialog patch in this
  project. This closes most of that gap without launching anything. It checks:

    * the DFM parses as TReader will, consuming the resource EXACTLY -- a stream that
      ends early or runs past means a malformed property, which is the failure mode a
      hand-emitted DFM actually produces
    * every published FIELD (VMT-0x2C) binds to exactly one component of that name --
      a field with no component stays nil and any cave reading it faults; a duplicate
      name means the later one wins silently
    * every On* handler value resolves to a published METHOD (VMT-0x28) -- otherwise
      TReader raises at load
    * InstanceSize (VMT-0x1C) covers the last field slot
    * no child hangs below its parent panel, which clips rather than complains

  It CANNOT prove the form loads: it does not know which properties each class
  publishes. Pair it with rtti_props.py, which does.
"""
import os
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


class Img(object):
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        d = self.d
        e = struct.unpack_from('<I', d, 0x3C)[0]
        nsec = struct.unpack_from('<H', d, e + 6)[0]
        optsz = struct.unpack_from('<H', d, e + 20)[0]
        self.opt = e + 24
        self.base = struct.unpack_from('<I', d, self.opt + 28)[0]
        self.secs = []
        for i in range(nsec):
            b = self.opt + optsz + i * 40
            vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b + 8)
            self.secs.append((va, vsz, raw, rsz))

    def rva2off(self, r):
        for va, vsz, raw, rsz in self.secs:
            if va <= r < va + max(vsz, rsz):
                return raw + (r - va)
        raise ValueError('rva %#x is in no section' % r)

    def va2off(self, va):
        return self.rva2off(va - self.base)

    def find_vmt(self, cls):
        """VMT-0x20 points at the class-name ShortString; nothing else does."""
        tag = bytes([len(cls)]) + cls.encode('latin1')
        for at in _all(self.d, tag):
            for va, vsz, raw, rsz in self.secs:
                if raw <= at < raw + rsz:
                    name_va = self.base + va + (at - raw)
                    ptr = struct.pack('<I', name_va)
                    for at2 in _all(self.d, ptr):
                        for va2, vsz2, raw2, rsz2 in self.secs:
                            if raw2 <= at2 < raw2 + rsz2:
                                return self.base + va2 + (at2 - raw2) + 0x20
        raise ValueError('no VMT whose -0x20 slot names %s' % cls)

    def resource(self, name):
        rrva = struct.unpack_from('<I', self.d, self.opt + 96 + 2 * 8)[0]
        ro = self.rva2off(rrva)
        hits = []

        def nm_at(v):
            off = ro + (v & 0x7FFFFFFF)
            n = struct.unpack_from('<H', self.d, off)[0]
            return self.d[off + 2:off + 2 + 2 * n].decode('utf-16le')

        def walk(diroff, path):
            nn, ni = struct.unpack_from('<HH', self.d, ro + diroff + 12)
            for i in range(nn + ni):
                eo = ro + diroff + 16 + i * 8
                v, off = struct.unpack_from('<II', self.d, eo)
                label = nm_at(v) if v & 0x80000000 else '#%d' % v
                if off & 0x80000000:
                    walk(off & 0x7FFFFFFF, path + [label])
                elif any(p.upper() == name.upper() for p in path + [label]):
                    hits.append(struct.unpack_from('<II', self.d, ro + off))

        walk(0, [])
        assert len(hits) == 1, '%s: %d resource entries' % (name, len(hits))
        rva, size = hits[0]
        o = self.rva2off(rva)
        return self.d[o:o + size]


def _all(d, sub):
    at = -1
    while True:
        at = d.find(sub, at + 1)
        if at < 0:
            return
        yield at


# ---- the DFM walk ------------------------------------------------------------------

def parse_dfm(dfm):
    comps, props = [], []

    def rstr(p):
        n = dfm[p]
        return dfm[p + 1:p + 1 + n].decode('latin1'), p + 1 + n

    def value(p):
        vt = dfm[p]
        p += 1
        if vt == 0:
            return None, p
        if vt == 1:                                       # vaList
            out = []
            while dfm[p]:
                v, p = value(p)
                out.append(v)
            return out, p + 1
        if vt == 2:
            return struct.unpack_from('<b', dfm, p)[0], p + 1
        if vt == 3:
            return struct.unpack_from('<h', dfm, p)[0], p + 2
        if vt == 4:
            return struct.unpack_from('<i', dfm, p)[0], p + 4
        if vt == 5:
            return 'extended', p + 10
        if vt in (6, 7):                                  # vaString / vaIdent
            return rstr(p)
        if vt in (8, 9):                                  # False / True
            return vt == 9, p
        if vt == 10:                                      # vaBinary
            n = struct.unpack_from('<I', dfm, p)[0]
            return 'binary[%d]' % n, p + 4 + n
        if vt == 11:                                      # vaSet
            out = []
            while dfm[p]:
                s, p = rstr(p)
                out.append(s)
            return out, p + 1
        if vt == 12:                                      # vaLString
            n = struct.unpack_from('<I', dfm, p)[0]
            return dfm[p + 4:p + 4 + n].decode('latin1'), p + 4 + n
        if vt == 13:                                      # vaNil -- no payload
            return None, p
        if vt == 14:                                      # vaCollection
            out = []
            while dfm[p]:
                if dfm[p] in (2, 3, 4):                   # optional item index
                    _i, p = value(p)
                assert dfm[p] == 1, 'malformed collection item at %#x' % p
                p += 1
                item = {}
                while dfm[p]:
                    pn, p = rstr(p)
                    item[pn], p = value(p)
                p += 1
                out.append(item)
            return out, p + 1
        if vt == 15:                                      # vaSingle
            return struct.unpack_from('<f', dfm, p)[0], p + 4
        if vt in (16, 17):                                # vaCurrency / vaDate
            return 'currency' if vt == 16 else 'date', p + 8
        if vt == 18:                                      # vaWString
            n = struct.unpack_from('<I', dfm, p)[0]
            return dfm[p + 4:p + 4 + 2 * n].decode('utf-16le'), p + 4 + 2 * n
        raise ValueError('unknown value type %d at %#x' % (vt, p - 1))

    def comp(p, depth, parent):
        cls, p = rstr(p)
        nm, p = rstr(p)
        comps.append((depth, cls, nm, parent))
        while dfm[p]:
            pn, p = rstr(p)
            v, p = value(p)
            props.append((nm, pn, v))
        p += 1
        while dfm[p]:
            p = comp(p, depth + 1, nm)
        return p + 1

    return comps, props, comp(4, 0, None)


# ---- the VMT tables ----------------------------------------------------------------

def fields_of(img, vmt):
    ft = struct.unpack_from('<I', img.d, img.va2off(vmt - 0x2C))[0]
    if not ft:
        return []
    o = img.va2off(ft)
    n = struct.unpack_from('<H', img.d, o)[0]
    p, out = o + 6, []
    for _ in range(n):
        offs = struct.unpack_from('<I', img.d, p)[0]
        ln = img.d[p + 6]
        out.append((offs, img.d[p + 7:p + 7 + ln].decode('latin1')))
        p += 7 + ln
    return out


def methods_of(img, vmt):
    mt = struct.unpack_from('<I', img.d, img.va2off(vmt - 0x28))[0]
    if not mt:
        return []
    o = img.va2off(mt)
    n = struct.unpack_from('<H', img.d, o)[0]
    p, out = o + 2, []
    for _ in range(n):
        size = struct.unpack_from('<H', img.d, p)[0]
        ln = img.d[p + 6]
        out.append(img.d[p + 7:p + 7 + ln].decode('latin1'))
        p += size
    return out


def main():
    if len(sys.argv) < 3:
        print('usage: dfm_verify.py <module.exe|.dpl> <TFormClass> [RESOURCENAME]')
        return 2
    mod, cls = sys.argv[1], sys.argv[2]
    res = sys.argv[3] if len(sys.argv) > 3 else cls.upper()
    path = mod if os.path.isabs(mod) else os.path.join(GAME, mod)
    img = Img(path)
    vmt = img.find_vmt(cls)
    inst = struct.unpack_from('<I', img.d, img.va2off(vmt - 0x1C))[0]
    dfm = img.resource(res)
    bad = 0

    print('%s  %s  VMT %#010x  InstanceSize %#x' % (mod, cls, vmt, inst))
    if dfm[:4] != b'TPF0':
        print('  resource %s is not a DFM (%r)' % (res, dfm[:4]))
        return 1
    comps, props, end = parse_dfm(dfm)
    ok = end == len(dfm)
    bad += 0 if ok else 1
    print('  DFM %d B, walk consumed %d -> %s | %d components, %d properties'
          % (len(dfm), end, 'EXACT' if ok else 'MISMATCH', len(comps), len(props)))

    fields = fields_of(img, vmt)
    methods = methods_of(img, vmt)
    names = [c[2] for c in comps]
    miss = [n for _o, n in fields if names.count(n) != 1]
    print('  fields %d: %s' % (len(fields),
                               'all bind to exactly one component' if not miss
                               else 'NO SINGLE COMPONENT FOR %s' % miss))
    bad += 1 if miss else 0

    # not every On* property is a handler binding -- TMainForm's HeroControlGrid
    # publishes a boolean OnlyFreeHeroes, and sorting it against method names throws
    handlers = [(c, p, v) for c, p, v in props
                if p.startswith('On') and isinstance(v, str)]
    # TReader resolves through TObject.MethodAddress, which compares CASE-INSENSITIVELY.
    # TMainForm relies on that: the DFM binds OnClick = 'OpenMapsetClick' while the
    # published method is 'OpenMapSetClick'.  A case-sensitive check calls that unresolved
    # and buries any real one.
    lower = {m.lower() for m in methods}
    unknown = sorted({v for _c, _p, v in handlers if v.lower() not in lower})
    print('  methods %s | %d handler bindings%s'
          % (methods or '(none)', len(handlers),
             '' if not unknown else ' -- UNRESOLVED: %s' % unknown))
    bad += 1 if unknown else 0

    if fields:
        top = max(o for o, _n in fields)
        print('  last field +%#x, InstanceSize %#x -> %s'
              % (top, inst, 'covers it' if top + 4 <= inst else 'TOO SMALL'))
        bad += 0 if top + 4 <= inst else 1

    # a windowed parent CLIPS its children rather than complaining, so a control that
    # hangs below one is simply invisible at run time
    box = {}
    for c, p, v in props:
        box.setdefault(c, {})[p] = v
    kids = {}
    for _depth, _cls, nm, parent in comps:
        kids.setdefault(parent, []).append(nm)
    for _depth, _cls, nm, _parent in comps:
        h = box.get(nm, {}).get('Height')
        if h is None:
            continue
        low = [(k, box[k]['Top'] + box[k].get('Height', 0))
               for k in kids.get(nm, []) if 'Top' in box.get(k, {})]
        if not low:
            continue
        who, bot = max(low, key=lambda t: t[1])
        mark = 'CLIPPED' if bot > h else 'fits'
        print('  %-12s height %4d, lowest child %s ends at %d -> %s'
              % (nm, h, who, bot, mark))
        bad += 1 if bot > h else 0
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
