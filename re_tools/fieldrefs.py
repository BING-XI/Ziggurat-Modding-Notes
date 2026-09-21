"""Find every instruction that dereferences a given object-field offset, with symbol attribution.

Answers "if I move field +0x44 of class C, what breaks?" -- the audit you need before relocating
any struct field.  Works on the DPLs (attributes hits to the nearest preceding Delphi export) and
on the exes (no exports, so hits are reported bare).

⚠ TWO TRAPS THIS TOOL EXISTS TO AVOID
 1. `capstone.disasm()` is a GENERATOR THAT STOPS at the first undecodable byte.  Disassembling a
    whole CODE section in one call looks like a full sweep but silently covers only the first few
    instructions and reports ZERO hits for everything.  This resyncs (advance 1 byte and retry).
 2. A disp8 of 0x44 is 0x44 for EVERY class.  This tool cannot tell TUnitResource+0x44 from some
    other object's +0x44 -- it is an over-approximation.  Read the symbol column and judge.
    Corollary: it is good for proving PRESENCE, weak for proving ABSENCE.

ALWAYS pass --validate <off> with a field you know is read (e.g. TUnitResource tier +0x2F) so a
zero result is distinguishable from a broken scan.

Usage:
  fieldrefs.py AoWEPACK.dpl 0x44 [0x32 0x33 ...] [--size byte|dword|any] [--validate 0x2F]
"""
import os
import re
import struct
import sys

import capstone

from pescan import PE

TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))

# The size prefix is OPTIONAL on purpose: `lea edx, [ebx + 0x44]` has none, and address-taking is
# how Delphi passes a field by reference (e.g. TUnitResource.ReadWrite handing +0x44 to the
# serialiser).  Missing those would make a field-move audit dangerously incomplete.
MEM = re.compile(r"(?:(byte|word|dword|qword) ptr )?\[(e[a-z]{2})(?: \+ (e[a-z]{2})\*\d)?"
                 r" \+ (0x[0-9a-f]+)\]")


def code_section(pe):
    for name, vaddr, vsize, raw, rsize in pe.sections:
        if name in ("CODE", ".text"):
            return raw, min(vsize, rsize) or rsize, pe.image_base + vaddr
    raise SystemExit("no CODE section")


def symbols(pe):
    """-> sorted [(va, name)] from the Delphi export table; empty for the exes."""
    out = []
    try:
        for name, frva in pe.exports():
            out.append((pe.image_base + frva, name))
    except Exception:
        pass
    return sorted(out)


def attribute(syms, va):
    if not syms:
        return ""
    lo, hi = 0, len(syms) - 1
    if va < syms[0][0]:
        return ""
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if syms[mid][0] <= va:
            lo = mid
        else:
            hi = mid - 1
    name, base = syms[lo][1], syms[lo][0]
    return "%s+0x%X" % (name, va - base)


def scan(code, base, offsets, size):
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    want = set(offsets)
    hits, pos = [], 0
    while pos < len(code):
        progressed = False
        for i in cs.disasm(code[pos:], base + pos):
            progressed = True
            pos += i.size
            m = MEM.search(i.op_str)
            if not m:
                continue
            if size != "any" and (m.group(1) or "lea") != size:
                continue
            if int(m.group(4), 16) in want:
                hits.append((i.address, int(m.group(4), 16), i.mnemonic, i.op_str))
        if not progressed:
            pos += 1
    return hits


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    path = sys.argv[1]
    size = "any"
    if "--size" in sys.argv:
        size = sys.argv[sys.argv.index("--size") + 1]
    validate = None
    if "--validate" in sys.argv:
        validate = int(sys.argv[sys.argv.index("--validate") + 1], 16)
    offs = [int(a, 16) for a in sys.argv[2:]
            if not a.startswith("--") and a not in (size, hex(validate or -1))]
    offs = [o for o in offs if o != validate]

    pe = PE(os.path.join(GAME, path))
    raw, sz, va = code_section(pe)
    code = pe.data[raw:raw + sz]
    syms = symbols(pe)
    print("%s: CODE %d bytes @%08X, %d exported symbols, size filter=%s"
          % (path, sz, va, len(syms), size))

    if validate is not None:
        n = len(scan(code, va, [validate], size))
        print("VALIDATION: field +0x%02X -> %d hits %s\n"
              % (validate, n, "(scanner alive)" if n else "*** ZERO -- SCANNER IS BROKEN ***"))
        if not n:
            return 1

    for o in offs:
        hits = scan(code, va, [o], size)
        print("=== field +0x%02X : %d access(es)" % (o, len(hits)))
        for addr, _f, mn, op in hits:
            print("   %08X  %-34s %s %s" % (addr, attribute(syms, addr), mn, op))
    return 0


if __name__ == "__main__":
    sys.exit(main())
