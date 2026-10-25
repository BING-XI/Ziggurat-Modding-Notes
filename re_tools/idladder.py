# -*- coding: utf-8 -*-
r"""idladder.py -- find every compiled `case` that treats one ability id differently from a new one.

    idladder.py <module> [--id 0x39] [--new 0xBE] [--all] [--ceilings]

Delphi compiles `case AbilityID of` into a ladder of relative tests on one register, not into
`cmp reg, 0x39`:

    cmp eax,0x34 / jg hi / sub eax,0x16 / je lob / add eax,-2 / sub eax,2 / jb lob ...

so a search for the immediate misses it (AoWTC.MakeAbilPath @0x004271EC never contains 0x39, yet
it gives Shoot Bolt its arc). This tool runs every ladder head in the module's CODE section with
the probe id and with ids nothing registers, and prints the ladders where the probe leaves by a
different exit. That is the list of places a clone of the probe ability must be added to.

Also followed: `jmp [reg*4+table]` jump tables and the byte-indexed two-level form
`mov al,[reg+bytes] / jmp [eax*4+table]`.

Heads come from a linear sweep of CODE plus everything reachable from the exports, direct branch
targets and jump-table entries: data inside CODE throws a linear sweep out of step, and the jump
table at 0x429EF7 hid the projectile switch at 0x429FC1 (two path steps per tick) until
2026-10-22. A hook cave that replays a ladder's first test becomes its head; the report names
the vanilla code its path jumps back to.

Output per site: the function, the head address, the probe's exit and the new id's exit, and
which other ids in 0..255 share the probe's exit -- {0x30..0x39} is a digit switch (noise);
{0x39, 0x3A, 0x2C, 0x2D} is an ability switch. `--all` also prints sites where the probe and
the new id agree.  `--ceilings` adds `id < N` tests with N between the probe and the new id (most
hits are data decoded as code; the real ceilings use memory counters and are not seen at all).

LISTs: tables of ids walked in a loop, such as the battlefield status icons (vanilla 0x4675B8,
ours 0x43C400 since build_ankh_battlefield.py) that a new status ability must join. Found only
behind Delphi's range check `bound idx, [limits]` right before the read, whose limits give the
exact length -- AoWTCPCK is the one module compiled with range checks; AoWEPACK and the exe
have none. A table is reported when it holds the probe and is read as an id (compared, or loaded
into EDX and passed to a call); `--all` adds the rest, such as the breath hex table 0x467498.

Not covered: an id compared after arithmetic on a *different* register, a list in AoWEPACK or
the exe, and bit-set tests (`bt`). Those are found by abquery.py (the `mov edx,<id>` +
VMT-call idiom) and by grepping the immediate.
"""
import bisect
import os
import struct
import sys

import capstone
from capstone import x86

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
from aowsyms import get_symbols

REG32 = ["eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"]
SUB = {"eax": ("ax", "al"), "ecx": ("cx", "cl"), "edx": ("dx", "dl"), "ebx": ("bx", "bl"),
       "esi": ("si", None), "edi": ("di", None), "ebp": ("bp", None)}
WIDTH = {}
for r32, (r16, r8) in SUB.items():
    WIDTH[r32] = (r32, 32)
    WIDTH[r16] = (r32, 16)
    if r8:
        WIDTH[r8] = (r32, 8)

JCC = {"je", "jne", "jb", "jae", "ja", "jbe", "jl", "jge", "jg", "jle", "js", "jns", "jo", "jno"}


def code_section(pe):
    for nm, vaddr, vsize, raw, rsize in pe.sections:
        if nm in ("CODE", ".text"):
            return vaddr, min(vsize, rsize), raw
    sys.exit("no CODE section")


class Module:
    def __init__(self, name):
        self.pe, self.base, self.names, _ = get_symbols(name)
        self.vaddr, self.size, self.raw = code_section(self.pe)
        self.cbase = self.base + self.vaddr
        self.blob = self.pe.data[self.raw:self.raw + self.size]
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        self.md.detail = True
        self.cache = {}
        sym = sorted(self.names.items())
        self.saddr = [a for a, _ in sym]
        self.sname = [n for _, n in sym]

    def at(self, va):
        if va in self.cache:
            return self.cache[va]
        off = va - self.cbase
        if not (0 <= off < len(self.blob)):
            return None
        for i in self.md.disasm(self.blob[off:off + 16], va, 1):
            self.cache[va] = i
            return i
        self.cache[va] = None
        return None

    def in_code(self, va):
        return self.cbase <= va < self.cbase + len(self.blob)

    def successors(self, i):
        """Code addresses `i` hands control to: a direct branch or call target, or every entry of
        the table of a `jmp [reg*4 + table]` (read until an entry leaves CODE)."""
        t = target(i)
        if t is not None and (i.mnemonic in JCC or i.mnemonic in ("jmp", "call", "loop", "loope", "loopne")):
            return [t] if self.in_code(t) else []
        o = ops(i)
        if i.mnemonic == "jmp" and len(o) == 1 and o[0].type == x86.X86_OP_MEM:
            mem = o[0].mem
            if mem.index and mem.scale == 4 and not mem.base and self.in_code(mem.disp):
                out = []
                for k in range(1024):
                    v = self.u32(mem.disp + 4 * k)
                    if v is None or not self.in_code(v):
                        break
                    out.append(v)
                return out
        return []

    def sweep(self):
        """Every instruction a linear sweep of CODE decodes, then every instruction reached from a
        seed it decoded out of step: the exports, direct branch and call targets, and jump-table
        entries. Data inside CODE throws a linear sweep out of step for a stretch: the jump table
        at 0x429EF7 hid the projectile switch at 0x429FC1 from it until 2026-10-22."""
        starts = set()
        pos = 0
        while pos < len(self.blob):
            moved = False
            for i in self.md.disasm(self.blob[pos:], self.cbase + pos):
                self.cache[i.address] = i
                starts.add(i.address)
                yield i
                pos = (i.address - self.cbase) + i.size
                moved = True
            if not moved:
                pos += 1
        seeds = [a for a in self.names if self.in_code(a)]
        for a in list(starts):
            seeds += self.successors(self.cache[a])
        while seeds:
            a = seeds.pop()
            if a in starts or not self.in_code(a):
                continue
            off = a - self.cbase
            for i in self.md.disasm(self.blob[off:off + 0x4000], a):
                if i.address in starts:
                    break
                self.cache[i.address] = i
                starts.add(i.address)
                yield i
                seeds += self.successors(i)
                if i.mnemonic in ("ret", "jmp"):
                    break

    def u32(self, va):
        off = self.pe.rva2off(va - self.base)
        if off is None or off + 4 > len(self.pe.data):
            return None
        return struct.unpack_from("<I", self.pe.data, off)[0]

    def u8(self, va):
        off = self.pe.rva2off(va - self.base)
        if off is None or off >= len(self.pe.data):
            return None
        return self.pe.data[off]

    def owner(self, va):
        k = bisect.bisect_right(self.saddr, va) - 1
        if k < 0 or va - self.saddr[k] > 0x4000:
            return "?"
        return self.sname[k].replace("@23EDC2EF", "") + "+0x%X" % (va - self.saddr[k])


def ops(i):
    return i.operands if i.operands else []


def reg_imm(i):
    """(regname, imm) for `op reg, imm`, else None."""
    o = ops(i)
    if len(o) == 2 and o[0].type == x86.X86_OP_REG and o[1].type == x86.X86_OP_IMM:
        return i.reg_name(o[0].reg), o[1].imm
    return None


def single_reg(i):
    o = ops(i)
    if len(o) == 1 and o[0].type == x86.X86_OP_REG:
        return i.reg_name(o[0].reg)
    return None


def target(i):
    o = ops(i)
    if len(o) == 1 and o[0].type == x86.X86_OP_IMM:
        return o[0].imm
    return None


def flags_sub(a, b, w):
    m = (1 << w) - 1
    a &= m; b &= m
    r = (a - b) & m
    sa, sb, sr = a >> (w - 1), b >> (w - 1), r >> (w - 1)
    return r, dict(zf=r == 0, cf=a < b, sf=bool(sr), of=bool((sa != sb) and (sr != sa)))


def flags_add(a, b, w):
    m = (1 << w) - 1
    a &= m; b &= m
    t = a + b
    r = t & m
    sa, sb, sr = a >> (w - 1), b >> (w - 1), r >> (w - 1)
    return r, dict(zf=r == 0, cf=t > m, sf=bool(sr), of=bool((sa == sb) and (sr != sa)))


def cond(mn, f):
    zf, cf, sf, of = f["zf"], f["cf"], f["sf"], f["of"]
    return {"je": zf, "jne": not zf, "jb": cf, "jae": not cf, "ja": not cf and not zf,
            "jbe": cf or zf, "jl": sf != of, "jge": sf == of, "jg": (not zf) and sf == of,
            "jle": zf or sf != of, "js": sf, "jns": not sf, "jo": of, "jno": not of}[mn]


def run(mod, head, reg32, value, limit=80):
    """Simulate the ladder at `head` with reg32 = value. Returns (exit_va, visited)."""
    val = value & 0xFFFFFFFF
    flags = None
    va = head
    visited = []
    for _ in range(limit):
        i = mod.at(va)
        if i is None:
            return va, visited
        mn = i.mnemonic
        ri = reg_imm(i)
        if ri and ri[0] in WIDTH and WIDTH[ri[0]][0] == reg32 and mn in ("cmp", "sub", "add"):
            w = WIDTH[ri[0]][1]
            m = (1 << w) - 1
            if mn == "add":
                r, flags = flags_add(val, ri[1], w)
            else:
                r, flags = flags_sub(val, ri[1], w)
            if mn != "cmp":
                val = (val & ~m) | r
            visited.append(va); va += i.size
            continue
        sr = single_reg(i)
        if sr and sr in WIDTH and WIDTH[sr][0] == reg32 and mn in ("dec", "inc"):
            w = WIDTH[sr][1]
            m = (1 << w) - 1
            cf = flags["cf"] if flags else False
            r, flags = (flags_sub if mn == "dec" else flags_add)(val, 1, w)
            flags["cf"] = cf
            val = (val & ~m) | r
            visited.append(va); va += i.size
            continue
        if mn == "test":
            o = ops(i)
            if (len(o) == 2 and o[0].type == o[1].type == x86.X86_OP_REG and o[0].reg == o[1].reg
                    and i.reg_name(o[0].reg) in WIDTH and WIDTH[i.reg_name(o[0].reg)][0] == reg32):
                w = WIDTH[i.reg_name(o[0].reg)][1]
                r = val & ((1 << w) - 1)
                flags = dict(zf=r == 0, cf=False, sf=bool(r >> (w - 1)), of=False)
                visited.append(va); va += i.size
                continue
        if mn in JCC and flags is not None and target(i) is not None:
            visited.append(va)
            va = target(i) if cond(mn, flags) else va + i.size
            continue
        if mn == "jmp":
            t = target(i)
            if t is not None:
                visited.append(va); va = t
                continue
            o = ops(i)
            if len(o) == 1 and o[0].type == x86.X86_OP_MEM:
                mem = o[0].mem
                if mem.index and i.reg_name(mem.index) == reg32 and mem.scale == 4 and not mem.base:
                    t = mod.u32((mem.disp + 4 * val) & 0xFFFFFFFF)
                    if t is None:
                        return va, visited
                    visited.append(va); va = t
                    continue
        if mn in ("mov", "movzx") and len(ops(i)) == 2:
            o = ops(i)
            # mov al, byte ptr [reg + table]  /  jmp [eax*4 + table2]
            if (o[0].type == x86.X86_OP_REG and o[1].type == x86.X86_OP_MEM and o[1].size == 1
                    and o[1].mem.base and i.reg_name(o[1].mem.base) == reg32 and not o[1].mem.index):
                b = mod.u8((o[1].mem.disp + val) & 0xFFFFFFFF)
                nxt = mod.at(va + i.size)
                dst = WIDTH.get(i.reg_name(o[0].reg), (None,))[0]
                if b is not None and nxt is not None and nxt.mnemonic == "jmp":
                    no = ops(nxt)
                    if (len(no) == 1 and no[0].type == x86.X86_OP_MEM and no[0].mem.index
                            and WIDTH.get(nxt.reg_name(no[0].mem.index), (None,))[0] == dst
                            and no[0].mem.scale == 4):
                        t = mod.u32((no[0].mem.disp + 4 * b) & 0xFFFFFFFF)
                        if t is None:
                            return va, visited
                        visited += [va, nxt.address]; va = t
                        continue
        return va, visited
    return va, visited


def s32(v):
    return v - (1 << 32) if v is not None and v & 0x80000000 else v


def table_read(mod, i):
    """(table, width, (low, high), bound_va) when `i` reads `table[idx]` right after Delphi's
    range check `bound idx, [bound_va]` -- whose qword holds the index limits, so the table's
    length is exact. Dword tables are `[idx*4 + table]`, byte tables `[idx + table]`."""
    for o in ops(i):
        if o.type != x86.X86_OP_MEM or o.size not in (1, 4):
            continue
        mem = o.mem
        if o.size == 4 and mem.index and mem.scale == 4 and not mem.base:
            idx = i.reg_name(mem.index)
        elif o.size == 1 and mem.base and not mem.index:
            idx = i.reg_name(mem.base)
        else:
            continue
        b = mod.at(i.address - 6)
        if b is None or b.mnemonic != "bound" or b.address + b.size != i.address:
            continue
        bo = ops(b)
        if len(bo) != 2 or bo[0].type != x86.X86_OP_REG or b.reg_name(bo[0].reg) != idx:
            continue
        lo, hi = s32(mod.u32(bo[1].mem.disp)), s32(mod.u32(bo[1].mem.disp + 4))
        if lo is None or hi is None or not (0 <= lo <= hi < lo + 1024):
            continue
        return mem.disp & 0xFFFFFFFF, o.size, (lo, hi), bo[1].mem.disp
    return None


def id_use(mod, i):
    """How a table entry read by `i` is used as an id: compared, or loaded into EDX and passed to
    a call (abquery.py's `mov edx,<id>` + call idiom, e.g. HasAbility through the VMT). None for
    anything else -- hex numbers, offsets, counts."""
    if i.mnemonic == "cmp":
        return "compared"
    o = ops(i)
    if not (o and o[0].type == x86.X86_OP_REG and WIDTH.get(i.reg_name(o[0].reg), (None,))[0] == "edx"):
        return None
    va = i.address + i.size
    for _ in range(5):
        j = mod.at(va)
        if j is None:
            return None
        if j.mnemonic == "call":
            return "edx -> call"
        jo = ops(j)
        if (jo and jo[0].type == x86.X86_OP_REG and WIDTH.get(j.reg_name(jo[0].reg), (None,))[0] == "edx"
                and j.mnemonic not in ("cmp", "test", "push")):
            return None
        va += j.size
    return None


def id_lists(mod, readers, probe, news, show_all):
    """Range-checked tables holding the probe id and read as an id -- a list walked in a loop,
    such as the battlefield status icons (vanilla 0x4675B8) that a new status ability joins."""
    tables = {}
    for i in readers:
        r = table_read(mod, i)
        if r:
            table, width, bounds, bva = r
            tables.setdefault((table, width, bounds), []).append((i, bva))
    out = 0
    for (table, width, (lo, hi)), sites in sorted(tables.items()):
        get = mod.u32 if width == 4 else mod.u8
        vals = [get(table + width * k) for k in range(lo, hi + 1)]
        if None in vals or probe not in vals:
            continue
        uses = [id_use(mod, s) for s, _ in sites]
        missing = [n for n in news if n not in vals]
        if not show_all and (not missing or not any(uses)):
            continue
        out += 1
        print("%08X  LIST of %d %s, index %d..%d (bound %s): probe at [%d]; new ids absent: %s" % (
            table, len(vals), "dwords" if width == 4 else "bytes", lo, hi,
            " ".join(sorted({"%08X" % b for _, b in sites})), lo + vals.index(probe),
            " ".join("%#04x" % n for n in missing) or "none"))
        for (s, _), use in sorted(zip(sites, uses), key=lambda p: p[0][0].address):
            print("          read at %08X %-40s %-44s %s" % (
                s.address, mod.owner(s.address), s.mnemonic + " " + s.op_str, use or "not read as an id"))
        if len(vals) <= 64:
            print("          entries: %s" % " ".join("%#04x" % v for v in vals))
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    modname = sys.argv[1]
    probe = int(sys.argv[sys.argv.index("--id") + 1], 0) if "--id" in sys.argv else 0x39
    news = ([int(sys.argv[sys.argv.index("--new") + 1], 0)] if "--new" in sys.argv
            else [0xBE, 0xC6, 0xD3])
    show_all = "--all" in sys.argv
    mod = Module(modname)

    heads = []
    readers = []
    for i in mod.sweep():
        ri = reg_imm(i)
        if ri and i.mnemonic in ("cmp", "sub", "add") and ri[0] in WIDTH:
            heads.append((i.address, WIDTH[ri[0]][0]))
        if i.mnemonic in ("mov", "movzx", "movsx", "cmp") and any(o.type == x86.X86_OP_MEM for o in ops(i)):
            readers.append(i)
    inner = set()
    results = []
    for head, reg in heads:
        ep, vis = run(mod, head, reg, probe)
        if len(vis) < 2:
            continue
        en = []
        for n in news:
            e, v2 = run(mod, head, reg, n)
            en.append(e)
            inner.update(a for a in v2 if a != head)
        inner.update(a for a in vis if a != head)
        results.append((head, reg, ep, en, vis))
    out = 0
    for head, reg, ep, en, vis in results:
        if head in inner:
            continue
        differs = ep not in en
        if not differs and not show_all:
            continue
        same = [v for v in range(256) if run(mod, head, reg, v)[0] == ep]
        if len(same) > 64:
            # the probe falls into the catch-all of a ladder about other values -- unless the
            # ladder is a CEILING (`id < N` with N between the probe and the new id), which
            # a new id above it must be let through
            if not (same == list(range(len(same))) and "--ceilings" in sys.argv):
                continue
            out += 1
            print("%08X  %-50s reg %s  CEILING: ids < %#04x share the probe's exit" % (
                head, mod.owner(head), reg, len(same)))
            continue
        out += 1
        print("%08X  %-50s reg %s  probe %#04x -> %08X   new -> %s" % (
            head, mod.owner(head), reg, probe, ep, " ".join("%08X" % e for e in sorted(set(en)))))
        print("          ids sharing the probe's exit: %s" % " ".join("%#04x" % v for v in same))
        # A hook cave that replays the ladder's first test is the head now; name where it rejoins.
        jumps = [target(mod.at(a)) for a in vis if mod.at(a).mnemonic == "jmp" and target(mod.at(a)) is not None]
        if jumps:
            print("          the probe's path jumps to: %s" % " ".join("%08X" % t for t in jumps))
    print("-- %d site(s) in %s where %#04x leaves a ladder by its own exit" % (out, modname, probe))
    lists = id_lists(mod, readers, probe, news, show_all)
    print("-- %d range-checked list(s) in %s holding %#04x" % (lists, modname, probe))


if __name__ == "__main__":
    main()
