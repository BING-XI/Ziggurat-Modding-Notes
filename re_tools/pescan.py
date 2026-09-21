"""Minimal PE parser for AoW1 Delphi packages:
1) dump imports-from-AOWEPACK of UI modules (filtered)
2) read Delphi VMT metadata (class name, instance size, parent chain) from AoWEPACK.dpl
"""
import struct, sys, re, os

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

class PE:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        d = self.data
        e_lfanew = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[e_lfanew:e_lfanew+4] == b"PE\0\0", "bad PE"
        coff = e_lfanew + 4
        (machine, nsec, tds, psym, nsym, opt_size, chars) = struct.unpack_from("<HHIIIHH", d, coff)
        opt = coff + 20
        magic = struct.unpack_from("<H", d, opt)[0]
        assert magic == 0x10B, "not PE32"
        self.image_base = struct.unpack_from("<I", d, opt + 28)[0]
        nrva = struct.unpack_from("<I", d, opt + 92)[0]
        self.dirs = []
        for i in range(nrva):
            self.dirs.append(struct.unpack_from("<II", d, opt + 96 + i*8))
        self.sections = []
        sec = opt + opt_size
        for i in range(nsec):
            name = d[sec:sec+8].rstrip(b"\0").decode(errors="replace")
            vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
            self.sections.append((name, vaddr, vsize, raw, rsize))
            sec += 40

    def rva2off(self, rva):
        for name, vaddr, vsize, raw, rsize in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return raw + (rva - vaddr)
        return None

    def read(self, rva, n):
        off = self.rva2off(rva)
        if off is None:
            return None
        return self.data[off:off+n]

    def u32(self, rva):
        b = self.read(rva, 4)
        return struct.unpack("<I", b)[0] if b else None

    def cstr(self, rva, maxlen=512):
        off = self.rva2off(rva)
        if off is None: return None
        end = self.data.index(b"\0", off, off + maxlen)
        return self.data[off:end].decode(errors="replace")

    def shortstr(self, rva):
        b = self.read(rva, 1)
        if not b: return None
        n = b[0]
        return self.read(rva + 1, n).decode(errors="replace")

    def imports(self):
        """yield (dllname, [names...])"""
        rva, size = self.dirs[1]
        if rva == 0: return
        i = 0
        while True:
            ent = self.read(rva + i*20, 20)
            if ent is None or ent == b"\0"*20: break
            oft, ts, fc, name_rva, ft = struct.unpack("<IIIII", ent)
            dll = self.cstr(name_rva)
            names = []
            thunk = oft or ft
            j = 0
            while True:
                v = self.u32(thunk + j*4)
                if not v: break
                if v & 0x80000000:
                    names.append(f"#ord{v & 0xFFFF}")
                else:
                    names.append(self.cstr(v + 2, 2048))
                j += 1
            yield dll, names
            i += 1

    def exports(self):
        """yield (name, rva)"""
        rva, size = self.dirs[0]
        if rva == 0: return
        base = self.read(rva, 40)
        (flags, ts, maj, minr, name_rva, ord_base, nfunc, nnames,
         addr_tbl, name_tbl, ord_tbl) = struct.unpack("<IIHHIIIIIII", base)
        for i in range(nnames):
            nrva = self.u32(name_tbl + i*4)
            name = self.cstr(nrva, 2048)
            ordn = struct.unpack("<H", self.read(ord_tbl + i*2, 2))[0]
            frva = self.u32(addr_tbl + ordn*4)
            yield name, frva


def vmt_info(pe, vmt_va):
    """Empirical AoW1/Delphi3 layout: VMT-0x20 name ptr, -0x1C instance size, -0x18 parent class-ref ptr"""
    base = pe.image_base
    rva = vmt_va - base
    name_ptr = pe.u32(rva - 0x20)
    size = pe.u32(rva - 0x1C)
    parent_ref = pe.u32(rva - 0x18)  # points to parent's class-ref slot (holds parent VMT)
    name = pe.shortstr(name_ptr - base) if name_ptr else None
    return name, size, parent_ref


def cmd_vmt(slot_vas):
    pe = PE(os.path.join(GAME, "AoWEPACK.dpl"))
    print("image_base=%08X" % pe.image_base)
    for slot_va in slot_vas:
        vmt = pe.u32(slot_va - pe.image_base)
        print(f"\nslot@{slot_va:08X} -> VMT {vmt:08X}")
        cur = vmt
        depth = 0
        while cur and depth < 15:
            name, size, parent_ref = vmt_info(pe, cur)
            print(f"  VMT {cur:08X}  name={name!r}  instsize={size:#x}")
            if not parent_ref: break
            cur = pe.u32(parent_ref - pe.image_base)  # deref parent slot -> parent VMT
            depth += 1


def cmd_classes(pat):
    """find exported bare class symbols and print their VMT info"""
    pe = PE(os.path.join(GAME, "AoWEPACK.dpl"))
    rx = re.compile(pat)
    for name, frva in pe.exports():
        if rx.search(name):
            va = frva + pe.image_base
            print(f"{name}  @ {va:08X}")


def cmd_imports(fname, pat):
    pe = PE(os.path.join(GAME, fname))
    rx = re.compile(pat, re.I)
    for dll, names in pe.imports():
        if "AOWEPACK" not in dll.upper():
            continue
        hits = [n for n in names if n and rx.search(n)]
        print(f"{fname}: imports {len(names)} symbols from {dll}, {len(hits)} match")
        for h in sorted(hits):
            print("   ", h)


def cmd_subclasses(slot_vas):
    """scan AoWEPACK for VMTs whose parent-ref points to one of the given class slots"""
    pe = PE(os.path.join(GAME, "AoWEPACK.dpl"))
    base = pe.image_base
    targets = {v: None for v in slot_vas}
    # label targets
    for v in list(targets):
        vmt = pe.u32(v - base)
        n, s, p = vmt_info(pe, vmt)
        targets[v] = n
    d = pe.data
    import struct as st
    found = []
    for name, vaddr, vsize, raw, rsize in pe.sections:
        limit = min(vsize, rsize)
        for off in range(0, limit - 4, 4):
            val = st.unpack_from("<I", d, raw + off)[0]
            if val in targets:
                # candidate: this dword is at VMT-0x18 (parent ref). VMT = pos + 0x18
                vmt_va = base + vaddr + off + 0x18
                cname, csize, cparent = vmt_info(pe, vmt_va)
                if cname and 2 < len(cname) < 40 and cname[0] == "T" and csize and csize < 0x1000:
                    found.append((cname, csize, targets[val], vmt_va))
    for cname, csize, pname, vmt_va in sorted(found):
        print(f"{cname:<30} size={csize:#5x} parent={pname:<15} VMT={vmt_va:08X}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "vmt":
        cmd_vmt([int(a, 16) for a in sys.argv[2:]])
    elif cmd == "classes":
        cmd_classes(sys.argv[2])
    elif cmd == "imports":
        cmd_imports(sys.argv[2], sys.argv[3])
    elif cmd == "subclasses":
        cmd_subclasses([int(a, 16) for a in sys.argv[2:]])
    elif cmd == "iatrefs":
        # count code references to the IAT slot of imports matching a pattern
        pe = PE(os.path.join(GAME, sys.argv[2]))
        rx = re.compile(sys.argv[3], re.I)
        base = pe.image_base
        # find IAT slots: walk import descriptors, use FT (first thunk) array VAs
        rva_dir, size = pe.dirs[1]
        i = 0
        slots = {}  # name -> iat slot VA
        while True:
            ent = pe.read(rva_dir + i*20, 20)
            if ent is None or ent == b"\0"*20: break
            oft, ts, fc, name_rva, ft = struct.unpack("<IIIII", ent)
            thunk = oft or ft
            j = 0
            while True:
                v = pe.u32(thunk + j*4)
                if not v: break
                if not (v & 0x80000000):
                    nm = pe.cstr(v + 2, 2048)
                    if nm and rx.search(nm):
                        slots[nm] = base + ft + j*4
                j += 1
            i += 1
        d = pe.data
        for nm, slot_va in sorted(slots.items()):
            needle = struct.pack("<I", slot_va)
            count = d.count(needle)
            print(f"{count-0:3d} refs  IAT@{slot_va:08X}  {nm}")
    elif cmd == "dlls":
        pe = PE(os.path.join(GAME, sys.argv[2]))
        for dll, names in pe.imports():
            print(f"{dll}: {len(names)}")
