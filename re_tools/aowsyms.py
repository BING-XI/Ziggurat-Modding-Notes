"""Shared symbol resolution for AoW modules.

get_symbols(modname) -> (pe, base, {va: name}, iat {slot_va: name})
 - dpl: names from export table
 - exe: names from Delphi VMT scan (class names) + published method tables
"""
import os, re, struct, sys
TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, TOOLS)
from pescan import PE

def _iat(pe):
    base = pe.image_base
    iat = {}
    rva_dir, size = pe.dirs[1]
    if rva_dir:
        i = 0
        while True:
            ent = pe.read(rva_dir + i*20, 20)
            if ent is None or ent == b"\0"*20:
                break
            oft, ts, fc, name_rva, ft = struct.unpack("<IIIII", ent)
            dll = pe.cstr(name_rva)
            thunk = oft or ft
            j = 0
            while True:
                v = pe.u32(thunk + j*4)
                if not v:
                    break
                if not (v & 0x80000000):
                    nm = pe.cstr(v + 2, 2048)
                    if nm:
                        nm = re.sub(r"@[0-9A-F]{8}$", "", nm)
                    iat[base + ft + j*4] = f"{dll}!{nm}"
                j += 1
            i += 1
    return iat

def _vmts(pe):
    """scan CODE for VMT self-pointers; return [(vmt_va, classname)]"""
    base = pe.image_base
    d = pe.data
    out = []
    for name, vaddr, vsize, raw, rsize in pe.sections:
        if name not in ("CODE", ".text"):
            continue
        limit = min(vsize, rsize)
        for off in range(raw, raw + limit - 4, 4):
            va = base + vaddr + (off - raw)
            if struct.unpack_from("<I", d, off)[0] == va + 0x40:
                vmt = va + 0x40
                name_ptr = pe.u32(vmt - 0x20 - base)
                cn = pe.shortstr(name_ptr - base) if name_ptr else None
                if cn and 2 < len(cn) < 48:
                    out.append((vmt, cn))
    return out

def get_symbols(modname):
    pe = PE(os.path.join(GAME, modname))
    base = pe.image_base
    syms = {}
    for name, frva in pe.exports():
        syms[base + frva] = re.sub(r"@[0-9A-F]{8}$", "", name)
    # exe (or any module): add VMT class names + published methods
    d = pe.data
    for vmt, cn in _vmts(pe):
        syms.setdefault(vmt, f"VMT_{cn}")
        mt = pe.u32(vmt - 0x28 - base)
        if not mt:
            continue
        off = pe.rva2off(mt - base)
        if off is None:
            continue
        try:
            count = struct.unpack_from("<H", d, off)[0]
            p = off + 2
            for i in range(count):
                size, code = struct.unpack_from("<HI", d, p)
                if size < 7:
                    break
                nlen = d[p+6]
                nm = d[p+7:p+7+nlen].decode("latin1", "replace")
                syms.setdefault(code, f"{cn}.{nm}")
                p += size
        except Exception:
            pass
    return pe, base, syms, _iat(pe)
