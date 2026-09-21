"""Delphi DFM binary walker with byte spans, for surgical in-place form edits.

`dfm_parse.py` pretty-prints a form's control tree; this one records the exact byte span of every
property value so a patch script can replace or delete individual properties and reason about the
byte budget.

WHY THE BUDGET MATTERS: the DFM lives in an RCDATA resource whose data entries are packed with
**zero padding** in AoWDevEd.exe (the next form's `TPF0` starts immediately), so a DFM cannot simply
grow.  Either keep the total length the same -- pay for a longer string by deleting a redundant
property elsewhere in the same form -- or relocate/grow the resource, which means fixing
`OffsetToData` in the resource directory.  Length-neutral edits need no resource work at all.

FORMAT (Delphi 3):
  "TPF0" then one object.  Object = [optional filer-prefix byte: (b & 0xF0) == 0xF0 -> flags, and
  ffChildPos (0x02) adds a position value], ClassName (shortstring), Name (shortstring),
  properties until a 0 byte, then nested objects until a 0 byte.
  Property = Name (shortstring) + typed value.
  ⚠ Missing the filer-prefix byte makes the walk desync after ~250 bytes and silently report almost
  nothing -- always check `consumed == len(dfm)`.

Delphi writes the SMALLEST integer encoding already (vaInt8 when it fits), so hunting for
re-encodable vaInt16 values as a source of free bytes is a dead end -- measured, zero candidates.

Usage:
  dfm_edit.py <exe> <start_hex> <size_hex>          -- list properties with spans
Importable:
  walk(dfm) -> W with .props = [(path, name, type, start, end, value)] and .consumed
  shortstr(s) / string_list(names) -- encoders
"""
import struct
import sys

NULL, LIST, I8, I16, I32, EXT, STR, IDENT, FALSE, TRUE, BIN, SET_, LSTR, NIL, COLL = range(15)
NAMES = {NULL: "Null", LIST: "List", I8: "Int8", I16: "Int16", I32: "Int32", EXT: "Extended",
         STR: "String", IDENT: "Ident", FALSE: "False", TRUE: "True", BIN: "Binary",
         SET_: "Set", LSTR: "LString", NIL: "Nil", COLL: "Collection"}


def shortstr(s):
    b = s.encode("latin1")
    assert len(b) < 256, "shortstring too long: %r" % s
    return bytes([len(b)]) + b


def string_list(names):
    """Encode a DFM `vaList` payload of vaString items, WITHOUT the leading LIST type byte."""
    return b"".join(bytes([STR]) + shortstr(n) for n in names) + b"\x00"


class W:
    def __init__(self, d, o=0):
        self.d, self.o = d, o
        self.props = []

    def u8(self):
        v = self.d[self.o]; self.o += 1; return v

    def sstr(self):
        n = self.u8()
        s = self.d[self.o:self.o + n]; self.o += n
        return s.decode("latin1", "replace")

    def value(self, path, name):
        start = self.o
        t = self.u8()
        val = None
        if t in (NULL, FALSE, TRUE, NIL):
            pass
        elif t == I8:
            val = struct.unpack_from("<b", self.d, self.o)[0]; self.o += 1
        elif t == I16:
            val = struct.unpack_from("<h", self.d, self.o)[0]; self.o += 2
        elif t == I32:
            val = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4
        elif t == EXT:
            self.o += 10
        elif t in (STR, IDENT):
            val = self.sstr()
        elif t == LIST:
            val = []
            while self.d[self.o] != 0:
                before = len(self.props)
                self.value(path, name)
                val.append(self.props[before][5] if len(self.props) > before else None)
            self.o += 1
        elif t == SET_:
            val = []
            while True:
                s = self.sstr()
                if s == "":
                    break
                val.append(s)
        elif t in (BIN, LSTR):
            n = struct.unpack_from("<I", self.d, self.o)[0]; self.o += 4 + n
        elif t == COLL:
            while self.d[self.o] != 0:
                if self.d[self.o] in (I8, I16, I32):
                    self.value(path, name)
                while self.d[self.o] != 0:
                    p = self.sstr()
                    self.value(path, p)
                self.o += 1
            self.o += 1
        else:
            raise ValueError("unknown DFM value type %d at 0x%X" % (t, start))
        self.props.append((path, name, t, start, self.o, val))
        return t

    def obj(self, path):
        start = self.o
        if (self.d[self.o] & 0xF0) == 0xF0:          # filer prefix, not a name length
            flags = self.u8() & 0x0F
            if flags & 0x02:                         # ffChildPos
                self.value(path, "$childpos")
        cls = self.sstr()
        nm = self.sstr()
        here = path + "/" + (nm or cls)
        self.props.append((here, "$class", -1, start, self.o, cls))
        while self.d[self.o] != 0:
            p = self.sstr()
            pstart = self.o - 1 - len(p)
            self.value(here, p)
            self.props[-1] = self.props[-1][:3] + (pstart,) + self.props[-1][4:]
        self.o += 1
        while self.d[self.o] != 0:
            self.obj(here)
        self.o += 1


def walk(dfm):
    assert dfm[:4] == b"TPF0", "not a DFM (starts %r)" % dfm[:4]
    w = W(dfm, 4)
    w.obj("")
    w.consumed = w.o
    return w


def find(w, path_suffix, name):
    """-> (start, end) span of one property, INCLUDING its name bytes."""
    hits = [p for p in w.props if p[0].endswith(path_suffix) and p[1] == name]
    assert len(hits) == 1, "expected 1 %s.%s, found %d" % (path_suffix, name, len(hits))
    return hits[0][3], hits[0][4]


def main():
    path, start, size = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
    dfm = open(path, "rb").read()[start:start + size]
    w = walk(dfm)
    tail = dfm[w.consumed:]
    if not tail:
        state = "CLEAN"
    elif all(b == 0 for b in tail):
        # a shrunk-in-place DFM leaves zero padding inside its fixed-size resource; the reader stops
        # at the form's terminator, so this is expected, not a parse failure
        state = "CLEAN + %d zero pad" % len(tail)
    else:
        state = "DESYNC -- %d unparsed non-zero bytes" % len(tail)
    print("%d bytes, consumed %d (%s), %d entries" % (len(dfm), w.consumed, state, len(w.props)))
    want = sys.argv[4] if len(sys.argv) > 4 else ""
    for pth, nm, t, a, b, v in w.props:
        if want and want.lower() not in pth.lower():
            continue
        print("  +0x%04X..%04X %-40s %-16s %-10s %r" % (a, b, pth[-39:], nm, NAMES.get(t, "obj"), v))


if __name__ == "__main__":
    main()
