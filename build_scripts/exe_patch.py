#!/usr/bin/env python
r"""
exe_patch.py -- shared helpers for small hook scripts on the mod game exe PAIR (2026-09-25).

Every run patches Ziggurat\AoWz.exe AND Ziggurat\AoWzCompat.exe (names from zigexe.EXES) in
lockstep, then asserts the two still differ at exactly zigexe.COMPAT_BYTE.  Conventions as in
aowepack_patch.py: dry run by default, verify-before-write, in-place r+b writes of owned bytes only,
surgical --undo (no snapshot), kill any running AoW binary before writing.

The exe always loads at 0x00400000 (DllCharacteristics 0, no DYNAMIC_BASE), so caves may use
absolute addresses; its .reloc is still scanned so no hook displaces a fixup.  AoWz.exe has no
spare section-header slot: take a free run from the cave table in Zig notes/12-re-toolchain.md.
"""
import os, sys, struct

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zigexe                                               # noqa: E402
from aowepack_patch import asm, kill_aow, show, jmp_to      # noqa: E402,F401

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BASE = 0x00400000


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    return e, [struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8) for i in range(nsec)]


def va2off(d, va):
    rva = va - BASE
    for vsize, vaddr, rsize, raw in sections(d)[1]:
        if vaddr <= rva < vaddr + rsize:
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X has no file bytes" % va)


def relocs_in(d, lo, hi):
    e = sections(d)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    if not size:
        return []
    off = va2off(d, BASE + rva)
    end, hits = off + size, []
    while off < end:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * k)[0]
            va = BASE + page + (ent & 0xFFF)
            if ent >> 12 and va < hi and va + 4 > lo:
                hits.append(va)
        off += blk
    return hits


def run(title, hooks, caves, slot, argv=None, targets=None):
    """hooks: [(va, vanilla, installed)]; caves: [(name, va, blob)]; slot: (lo, hi) owned zone.
    targets: exe names in GAME; default zigexe.EXES, which also gets the lockstep check.
    Returns "apply" / "undo" when it wrote, else None."""
    targets = targets or zigexe.EXES
    import argparse
    ap = argparse.ArgumentParser(description=title)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args(argv)
    lo, hi = slot
    assert all(lo <= va and va + len(b) <= hi for _n, va, b in caves), "cave outside its slot"
    spans = sorted((va, va + len(b), n) for n, va, b in caves)
    for (a0, a1, an), (b0, b1, bn) in zip(spans, spans[1:]):
        assert a1 <= b0, "caves overlap: %s ends %08X, %s starts %08X" % (an, a1, bn, b0)
    print(title)
    plan, fatal = {}, False
    for exe in targets:
        path = os.path.join(GAME, exe)
        d = bytearray(open(path, "rb").read())
        states = []
        for va, van, new in hooks:
            o = va2off(d, va)
            cur = bytes(d[o:o + len(van)])
            states.append("vanilla" if cur == van else "installed" if cur == new
                          else "FOREIGN " + cur.hex(" "))
        zone = bytes(d[va2off(d, lo):va2off(d, lo) + (hi - lo)])
        ours = all(bytes(d[va2off(d, va):va2off(d, va) + len(b)]) == b for _n, va, b in caves)
        rl = [v for va, van, _ in hooks for v in relocs_in(d, va, va + len(van))] + relocs_in(d, lo, hi)
        state = ("VANILLA" if all(s == "vanilla" for s in states) and not any(zone) else
                 "INSTALLED" if all(s == "installed" for s in states) and ours else "MIXED")
        print("  %-15s %s   hooks: %s   slot %08X-%08X: %s   .reloc: %s"
              % (exe, state, ", ".join(s.split()[0] for s in states), lo, hi,
                 "zero" if not any(zone) else "our caves" if ours else "NOT ZERO",
                 ", ".join("%08X" % v for v in rl) or "none"))
        if any(s.startswith("FOREIGN") for s in states) or rl or (any(zone) and not ours):
            fatal = True
        plan[exe] = (path, d, state)
    if a.dis:
        show(caves)
    if fatal:
        sys.exit("ABORT: foreign bytes at a hook, a .reloc under a hook/slot, or a slot not ours")
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    kill_aow()
    for exe, (path, d, state) in plan.items():
        if (a.apply and state == "INSTALLED") or (a.undo and state == "VANILLA"):
            continue
        with open(path, "r+b") as f:
            f.seek(va2off(d, lo))
            f.write(b"\0" * (hi - lo))
            if a.apply:
                for _n, va, blob in caves:
                    f.seek(va2off(d, va))
                    f.write(blob)
            for va, van, new in hooks:
                f.seek(va2off(d, va))
                f.write(new if a.apply else van)
    verb = "APPLIED to" if a.apply else "UNDONE on"
    if list(targets) != list(zigexe.EXES):
        print("\n%s %s" % (verb, ", ".join(targets)))
        return "apply" if a.apply else "undo"
    x, y = (open(os.path.join(GAME, e), "rb").read() for e in zigexe.EXES)
    diff = [i for i in range(len(x)) if x[i] != y[i]] if len(x) == len(y) else None
    assert diff == [zigexe.COMPAT_BYTE], "lockstep broken: %s vs %s differ at %s" % (
        zigexe.EXES[0], zigexe.EXES[1], diff if diff is None else [hex(i) for i in diff[:8]])
    print("\n%s both exes; lockstep holds (they differ only at file 0x%X)"
          % (verb, zigexe.COMPAT_BYTE))
    return "apply" if a.apply else "undo"
