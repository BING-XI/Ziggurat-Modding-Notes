#!/usr/bin/env python
r"""
aowepack_patch.py -- shared helpers for small AoWEPACK.dpl hook scripts (2026-09-24).

Used by build_defeat_enchant_guard.py, build_mpresume_customize.py and build_vortex_reseed.py.
Each of those scripts owns its own sites and cave slot; this module only reads and writes the
bytes it is told to.  Conventions (project CLAUDE.md): dry run by default, verify-before-write,
in-place r+b writes of owned bytes only, no snapshot (the --undo is surgical), kill any running
AoW binary before writing.
"""
import os, sys, struct, subprocess

sys.dont_write_bytecode = True
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
IMAGE_BASE = 0x55700000
AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")


def asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


def kill_aow():
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    return e, [struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8) for i in range(nsec)]


def va2off(d, va):
    rva = va - IMAGE_BASE
    for vsize, vaddr, rsize, raw in sections(d)[1]:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def relocs_in(d, lo, hi):
    e = sections(d)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    if not size:
        return []
    off = va2off(d, IMAGE_BASE + rva)
    end, hits = off + size, []
    while off < end:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * k)[0]
            va = IMAGE_BASE + page + (ent & 0xFFF)
            if ent >> 12 and va < hi and va + 4 > lo:
                hits.append(va)
        off += blk
    return hits


def rel32_into(d, lo, hi):
    """VAs of any E8/E9 rel32 anywhere in the file that lands strictly inside (lo, hi)."""
    hits = []
    for vsize, vaddr, rsize, raw in sections(d)[1]:
        for i in range(raw, raw + min(vsize or rsize, rsize) - 5):
            if d[i] in (0xE8, 0xE9):
                src = IMAGE_BASE + vaddr + (i - raw)
                t = src + 5 + struct.unpack_from("<i", d, i + 1)[0]
                if lo < t < hi:
                    hits.append(src)
    return hits


def short_into(d, lo, hi, fn_lo, fn_hi):
    """Relative jumps inside [fn_lo, fn_hi) (capstone) whose target falls strictly inside (lo, hi).
    Jumps that start inside [lo, hi) are the replaced bytes' own and are ignored.  fn_lo must be an
    instruction boundary."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    o = va2off(d, fn_lo)
    bad = []
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(bytes(d[o:o + fn_hi - fn_lo]), fn_lo):
        if lo <= ins.address < hi:
            continue
        if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            if lo < t < hi:
                bad.append(ins.address)
    return bad


def jmp_to(src, dst, length):
    return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (length - 5)


def show(blobs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for name, va, blob in blobs:
        print("\n  ---- %s @%08X (%d B)" % (name, va, len(blob)))
        for ins in md.disasm(blob, va):
            print("    %08X  %-22s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def run(title, hooks, caves, slot, interior_checks, argv=None, reloc_ok=()):
    """hooks: [(va, vanilla, installed)]; caves: [(name, va, blob)]; slot: (lo, hi) owned zone.
    interior_checks: [(lo, hi, fn_lo, fn_hi)] hook ranges that must receive no foreign jumps.
    reloc_ok: VAs whose .reloc entry is expected and kept -- a repointed VMT slot, whose new
    value is another address inside this image, so the rebase delta still applies to it."""
    import argparse
    ap = argparse.ArgumentParser(description=title)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args(argv)

    d = bytearray(open(TARGET, "rb").read())
    print("%s -- %s" % (title, TARGET))
    lo, hi = slot
    assert all(lo <= va and va + len(b) <= hi for _n, va, b in caves), "cave outside its slot"
    spans = sorted((va, va + len(b), n) for n, va, b in caves)
    for (a0, a1, an), (b0, b1, bn) in zip(spans, spans[1:]):
        assert a1 <= b0, "caves overlap: %s ends %08X, %s starts %08X" % (an, a1, bn, b0)
    states = []
    for va, van, new in hooks:
        o = va2off(d, va)
        cur = bytes(d[o:o + len(van)])
        st = "vanilla" if cur == van else "installed" if cur == new else "FOREIGN " + cur.hex(" ")
        states.append(st)
        print("  hook %08X  %s" % (va, st))
    zo, zh = va2off(d, lo), va2off(d, hi)
    zone = bytes(d[zo:zh])
    ours = all(bytes(d[va2off(d, va):va2off(d, va) + len(b)]) == b for _n, va, b in caves)
    print("  slot %08X-%08X: %s" % (lo, hi, "zero" if not any(zone) else "our caves" if ours else "NOT ZERO"))
    rl = [v for va, van, _ in hooks for v in relocs_in(d, va, va + len(van))] + relocs_in(d, lo, hi)
    missing = [v for v in reloc_ok if v not in rl]
    if missing:
        sys.exit("ABORT: expected .reloc entry missing at %s" % ", ".join("%08X" % v for v in missing))
    rl = [v for v in rl if v not in reloc_ok]
    inner = []
    for ilo, ihi, flo, fhi in interior_checks:
        inner += rel32_into(d, ilo, ihi) + short_into(d, ilo, ihi, flo, fhi)
    print("  .reloc under hooks/slot: %s" % (", ".join("%08X" % v for v in rl) or "none"))
    print("  jumps into a hook's interior: %s" % (", ".join("%08X" % v for v in inner) or "none"))
    if a.dis:
        show(caves)
    state = "VANILLA" if all(s == "vanilla" for s in states) else \
        "INSTALLED" if all(s == "installed" for s in states) and ours else "MIXED"
    print("state: %s" % state)
    if any(s.startswith("FOREIGN") for s in states):
        sys.exit("ABORT: a hook site holds foreign bytes")
    if rl or inner:
        sys.exit("ABORT: a .reloc entry or an interior jump conflicts with a hook")
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    if a.apply and state == "INSTALLED":
        print("\nalready installed -- nothing to do")
        return
    if a.undo and state == "VANILLA" and not any(zone):
        print("\nalready vanilla -- nothing to do")
        return
    if a.apply and any(zone) and not ours and all(s == "vanilla" for s in states):
        sys.exit("ABORT: slot %08X-%08X is not zero" % (lo, hi))
    kill_aow()
    with open(TARGET, "r+b") as f:
        f.seek(zo)
        f.write(b"\0" * (zh - zo))
        if a.apply:
            for _n, va, blob in caves:
                f.seek(va2off(d, va))
                f.write(blob)
        for va, van, new in hooks:
            f.seek(va2off(d, va))
            f.write(new if a.apply else van)
    back = open(TARGET, "rb").read()
    for va, van, new in hooks:
        o = va2off(back, va)
        assert back[o:o + len(van)] == (new if a.apply else van), "%08X did not stick" % va
    print("\n%s" % ("APPLIED" if a.apply else "UNDONE -- hooks vanilla, slot zeroed"))
