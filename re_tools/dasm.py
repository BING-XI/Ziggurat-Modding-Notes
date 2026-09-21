"""Annotated capstone disassembler for any AoW module (exe or dpl).

Usage: dasm.py <module> <va-hex> [len-hex]
       dasm.py <module> sym <substring>     -- disassemble the export matching substring
Resolves: own exports, import thunks (jmp [iat]), IAT slots, string/data refs.
"""
import sys, os, struct, re, bisect
TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, TOOLS)
from pescan import PE
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowsyms import get_symbols

def load(modname):
    pe, base, exp, iat = get_symbols(modname)
    exp_sorted = sorted(exp)
    return pe, base, exp, exp_sorted, iat

def main():
    modname = sys.argv[1]
    pe, base, exp, exp_sorted, iat = load(modname)

    if sys.argv[2] == "sym":
        pat = sys.argv[3].lower()
        matches = [(va, n) for va, n in exp.items() if pat in n.lower()]
        matches.sort()
        if not matches:
            print("no match"); return
        if len(matches) > 1 and len(sys.argv) < 5:
            for va, n in matches:
                print(f"{va:08X} {n}")
            va, name = matches[0]
            print(f"-- disassembling first: {name}")
        else:
            va, name = matches[0]
        # length: to next export
        i = bisect.bisect_right(exp_sorted, va)
        length = (exp_sorted[i] - va) if i < len(exp_sorted) else 0x200
        length = min(length, 0x1000)
    else:
        va = int(sys.argv[2], 16)
        if len(sys.argv) > 3:
            length = int(sys.argv[3], 16)
        else:
            i = bisect.bisect_right(exp_sorted, va)
            length = min((exp_sorted[i] - va) if i < len(exp_sorted) else 0x200, 0x1000)

    def sym(addr):
        """Best-effort name for an address."""
        if addr in exp:
            return exp[addr]
        if addr in iat:
            return f"[{iat[addr]}]"
        return None

    def thunk_target(addr):
        """If addr is a jmp-[iat] thunk, return import name."""
        b = pe.read(addr - base, 6)
        if b and b[:2] == b"\xff\x25":
            slot = struct.unpack("<I", b[2:6])[0]
            if slot in iat:
                return iat[slot]
        return None

    def data_note(addr):
        """Try to identify a data ref: iat slot, export, or string."""
        if addr in iat:
            return f"IAT:{iat[addr]}"
        if addr in exp:
            return exp[addr]
        raw = pe.rva2off(addr - base)
        if raw is not None:
            d = pe.data
            # Delphi shortstring or pascal string literal?
            n = d[raw]
            if 2 < n < 64 and raw+1+n <= len(d):
                s = d[raw+1:raw+1+n]
                if all(32 <= c < 127 for c in s):
                    return f"shortstr'{s.decode('latin1')}'"
            s = d[raw:raw+32]
            txt = s.split(b"\0")[0]
            if len(txt) >= 4 and all(32 <= c < 127 for c in txt):
                return f"str'{txt.decode('latin1')}'"
            v = struct.unpack_from("<I", d, raw)[0] if raw+4 <= len(d) else None
            if v is not None and (v in exp):
                return f"ptr->{exp[v]}"
        return None

    code = pe.read(va - base, length)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = False
    hdr = exp.get(va)
    print(f"; ==== {modname} {va:08X} len={length:#x}" + (f"  {hdr}" if hdr else "") + " ====")
    for ins in md.disasm(code, va):
        line = f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}"
        note = ""
        m = re.match(r"^0x([0-9a-f]+)$", ins.op_str)
        if ins.mnemonic in ("call", "jmp") and m:
            tgt = int(m.group(1), 16)
            t = sym(tgt) or thunk_target(tgt)
            if t:
                note = f" ; {t}"
            if ins.mnemonic == "jmp" and not t and not (va <= tgt < va + length):
                note = " ; out-of-range"
        else:
            for hexm in re.finditer(r"0x([0-9a-f]{7,8})", ins.op_str):
                addr = int(hexm.group(1), 16)
                dn = data_note(addr)
                if dn:
                    note += f" ; {addr:08X}={dn}"
        # label exported targets inside the listing
        if ins.address in exp:
            print(f"\n; ---- {exp[ins.address]} ----")
        print(line + note)

main()
