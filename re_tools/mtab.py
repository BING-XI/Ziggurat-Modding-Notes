"""Dump a Delphi class's published *method table* (handler name -> code VA).

Usage: mtab.py <module> <vmt-va-hex>
Empirical AoW/Delphi3 VMT layout is standard-minus-0xC, so method table = [VMT-0x28].
Format: {Count:word} then Count x {EntrySize:word, Code:dword, Name:shortstr}.
"""
import sys, os, struct
TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, TOOLS)
from pescan import PE

pe = PE(os.path.join(GAME, sys.argv[1]))
base = pe.image_base
vmt = int(sys.argv[2], 16)

name_ptr = pe.u32(vmt - 0x20 - base)
cname = pe.shortstr(name_ptr - base) if name_ptr else "?"
mt = pe.u32(vmt - 0x28 - base)
print(f"class {cname} VMT={vmt:08X} methodtable={mt:08X}" if mt else f"class {cname}: no method table")
if not mt:
    sys.exit(0)
off = pe.rva2off(mt - base)
d = pe.data
count = struct.unpack_from("<H", d, off)[0]
print(f"{count} published methods")
p = off + 2
for i in range(count):
    size, code = struct.unpack_from("<HI", d, p)
    nlen = d[p+6]
    nm = d[p+7:p+7+nlen].decode("latin1", "replace")
    print(f"  {code:08X}  {nm}")
    p += size
