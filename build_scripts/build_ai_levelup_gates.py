#!/usr/bin/env python
r"""
build_ai_levelup_gates.py -- the AI hero level-up offers a stat whenever it can afford it.

WHAT
----
`THero.ExecuteUpgradeHeroAI @0x55787A24` builds the AI's shortlist of stat purchases.  Per stat:

    55787A49  call THero.GetSkillPoints        ; level*10 + 10 - UsedSkillPoints (- write-off)
    55787A4E  mov  esi, eax
    55787A50  cmp  esi, N        ; <-- gate: unspent points on hand
    55787A53  jl   next
    55787A55  movsx eax, byte [ebx+0x6A]       ; bought ATK
    ...       + chassis ATK
    55787A62  cmp  eax, 0x14     ; cap 20
    55787A65  jge  next
    ...       offer (weight in ecx, stat index in edx)

Vanilla's N (5/5/5/10/5) equals vanilla's price for one point of each stat, so the gate means "can
afford it".  Ziggurat had carried a hand-edit 4/16/8/8/3, read on 2026-09-08 as per-stat target
levels.  The code never used them that way: they are points-on-hand thresholds, so DEF was offered
only while the AI held 16+ unspent points.  Owner ruling 2026-09-24: match the prices.

    gate VA (imm)   field   stat   hand-edit   price (UsedSkillPoints imul)
    0x55787A52      +0x6A   ATK        4        3   @0x55786CD3
    0x55787A77      +0x6B   DEF       16        6   @0x55786CDA
    0x55787A9F      +0x6F   RES        8        2   @0x55786CEE
    0x55787AC7      +0x6C   DAM        8        4   @0x55786CE5
    0x55787AEF      +0x6D   HP         3        2   @0x55786CF7

The prices are READ from `THero.UsedSkillPoints @0x55786CC8`, never hard-coded, so this script
stays right after a re-price: its dry run reports DRIFT and --apply re-syncs in place.  The caps
(`cmp eax,M`, live 20/20/20/20/60) are not touched.

COUPLING
    * fivepct_manifest.json holds an UNCHANGED row for 0x55787A52 only.  build_statdouble.py loads
      DOUBLE/HALVE rows only, so that row is not verified and needs no sync.
    * Every price edit (build_heroskill_*.py, any future re-price) must be followed by a run of
      this script.

Not a roll.  Five 1-byte immediates, each inside a verified `83 FE ib / 7C rel8 / 0F BE 43 fld`.

USAGE
    python build_ai_levelup_gates.py            verify / dry run (writes nothing)
    python build_ai_levelup_gates.py --apply    gates := live prices
    python build_ai_levelup_gates.py --undo     gates := the hand-edit 4/16/8/8/3
"""
import os, sys, struct, argparse, subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
IMAGE_BASE = 0x55700000

#        stat   gate insn VA  field  hand-edit  price field-load VA  price imul VA   imul bytes
ROWS = [("ATK", 0x55787A50, 0x6A, 4,  0x55786CCD, 0x55786CD1, b"\x6B\xF8"),
        ("DEF", 0x55787A75, 0x6B, 16, 0x55786CD4, 0x55786CD8, b"\x6B\xC0"),
        ("RES", 0x55787A9D, 0x6F, 8,  0x55786CE8, 0x55786CEC, b"\x6B\xC0"),
        ("DAM", 0x55787AC5, 0x6C, 8,  0x55786CDD, 0x55786CE3, b"\x6B\xC0"),
        ("HP",  0x55787AED, 0x6D, 3,  0x55786CF1, 0x55786CF5, b"\x6B\xC0")]

AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")


def kill_aow():
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    sec, rva = e + 24 + opt, va - IMAGE_BASE
    for i in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 40 * i + 8)
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def read_rows(d):
    """-> [(stat, imm file offset, gate value, price)], aborting on any structural mismatch."""
    out = []
    for stat, gate, fld, _old, pload, pimul, imul in ROWS:
        g = va2off(d, gate)
        ins = bytes(d[g:g + 9])
        if ins[:2] != b"\x83\xFE" or ins[3] != 0x7C or ins[5:9] != bytes([0x0F, 0xBE, 0x43, fld]):
            sys.exit("ABORT: %s gate %08X is not `cmp esi,ib / jl / movsx eax,[ebx+%02X]` (%s)"
                     % (stat, gate, fld, ins.hex(" ")))
        p = va2off(d, pload)
        if bytes(d[p:p + 4]) != bytes([0x0F, 0xBE, 0x46, fld]):
            sys.exit("ABORT: UsedSkillPoints %08X does not load [esi+%02X] (%s)"
                     % (pload, fld, bytes(d[p:p + 4]).hex(" ")))
        q = va2off(d, pimul)
        if bytes(d[q:q + 2]) != imul:
            sys.exit("ABORT: UsedSkillPoints %08X is not `imul r,eax,ib` (%s)"
                     % (pimul, bytes(d[q:q + 3]).hex(" ")))
        out.append((stat, g + 2, d[g + 2], d[q + 2]))
    return out


def main():
    ap = argparse.ArgumentParser(description="AI level-up stat gates = live prices")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--apply", action="store_true")
    grp.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    d = bytearray(open(TARGET, "rb").read())
    rows = read_rows(d)
    print("build_ai_levelup_gates -- %s" % TARGET)
    print("    stat  gate  price  hand-edit")
    for (stat, _o, gate, price), row in zip(rows, ROWS):
        print("    %-4s  %4d  %5d  %9d" % (stat, gate, price, row[3]))
    at_price = all(g == p for _s, _o, g, p in rows)
    at_old = all(g == row[3] for (_s, _o, g, _p), row in zip(rows, ROWS))
    print("state: %s" % ("APPLIED" if at_price else "CLEAN (hand-edit)" if at_old else
                         "DRIFT -- gates match neither the prices nor the hand-edit"))

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    want = [p for _s, _o, _g, p in rows] if a.apply else [row[3] for row in ROWS]
    if all(g == w for (_s, _o, g, _p), w in zip(rows, want)):
        print("\nalready %s -- nothing to do" % ("applied" if a.apply else "undone"))
        return
    for w in want:
        assert 1 <= w <= 30, "implausible gate value %d" % w
    kill_aow()
    with open(TARGET, "r+b") as f:
        for (stat, off, g, _p), w in zip(rows, want):
            if g != w:
                f.seek(off)
                f.write(bytes([w]))
                print("  %-4s gate %2d -> %2d" % (stat, g, w))
    back = open(TARGET, "rb").read()
    for (stat, off, _g, _p), w in zip(rows, want):
        assert back[off] == w, "%s write did not stick" % stat
    print("%s" % ("APPLIED -- gates = live prices" if a.apply else "UNDONE -- gates = 4/16/8/8/3"))


if __name__ == "__main__":
    main()
