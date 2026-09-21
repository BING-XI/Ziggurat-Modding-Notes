"""Find code xrefs to VAs in a module: E8/E9 rel32 calls/jmps + absolute dword refs.

Usage: xref.py <module> <va-hex> [<va-hex> ...]
Labels each hit with the nearest preceding export symbol.
"""
import sys, os, struct, re, bisect
TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, TOOLS)
from pescan import PE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowsyms import get_symbols
pe, base, exp, _iat = get_symbols(sys.argv[1])
d = pe.data
exp_vas = sorted(exp)

def owner(va):
    i = bisect.bisect_right(exp_vas, va) - 1
    if i >= 0:
        return f"{exp[exp_vas[i]]}+{va - exp_vas[i]:#x}"
    return "?"

targets = set(int(a, 16) for a in sys.argv[2:])
code_secs = [(vaddr, vsize, raw, rsize) for name, vaddr, vsize, raw, rsize in pe.sections
             if name in ("CODE", ".text", ".itext")]

for tva in sorted(targets):
    print(f"\n=== xrefs to {tva:08X} {exp.get(tva,'')} ===")
    hits = 0
    for vaddr, vsize, raw, rsize in code_secs:
        limit = min(vsize, rsize)
        sec = d[raw:raw+limit]
        # rel32 call/jmp
        for i in range(limit - 5):
            b = sec[i]
            if b == 0xE8 or b == 0xE9:
                src_va = base + vaddr + i
                rel = struct.unpack_from("<i", sec, i+1)[0]
                if (src_va + 5 + rel) == tva:
                    kind = "call" if b == 0xE8 else "jmp "
                    print(f"  {kind} @ {src_va:08X}  in {owner(src_va)}")
                    hits += 1
        # absolute refs
        needle = struct.pack("<I", tva)
        j = sec.find(needle)
        while j >= 0:
            src_va = base + vaddr + j
            print(f"  abs  @ {src_va:08X}  in {owner(src_va)}")
            hits += 1
            j = sec.find(needle, j+1)
    if not hits:
        print("  (none in code sections)")
