#!/usr/bin/env python
r"""
build_deved_itemneg.py -- Item Properties accepts negative Attack / Defence / Damage / Resistance.
AoWDevEd.exe (then build_zigeditor.py --apply).  From Inioch's share8
patch_devx_item_negative_stats.py, rescaled: his -10 mirrors vanilla's ceiling 10, ours -60
mirrors our ceiling 60 (build_editor_spinners.py).

The engine already treats item stats as signed: the dialog loader reads them with movsx, the
banner and the AI valuation read them signed, and hero stat sums are signed adds under the
floor clamps of build_hero_clamps.py.  The only blocker was the four TSpin controls' DFM
`MinValue 0` (vaInt8 `08 MinValue 02 00`).  This sets them to -60 (`02 C4`), length-neutral.

TITEMEDITFORM exists twice (08-editor.md, "relocated forms"): the dead MASTER in .rsrc at file
0x000697A8, which build_deved_itemhpmv.py rebuilds the live copy from on every --apply, and that
live copy in .nmg (rva 0x199400).  Both are patched, so an itemhpmv re-apply keeps the value.
The Hit Points / Movement spinners are runtime controls; their minima (-60 / -50) live in
build_deved_itemhpmv.py (HP_MIN / MV_MIN).

Dry run by default; --apply; --undo writes 0 back.  Sites are found by pattern inside the two
known DFM spans, never by absolute offset.
"""
import os, re, struct, sys
sys.dont_write_bytecode = True
import zigexe
from aowepack_patch import kill_aow

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
EXE = os.path.join(GAME, zigexe.SRC_EDITOR)
MASTER = (0x000697A8, 0x1D3F)             # .rsrc master (build_deved_itemhpmv.DFM_FILE_OFF/LEN)
LIVE_VA, LIVE_LEN = 0x00599400, 0x26E6    # the relocated live copy in .nmg
NAMES = (b"AttackEdit", b"DefenseEdit", b"ResistanceEdit", b"DamageEdit")
MIN_OLD, MIN_NEW = 0x00, (-60) & 0xFF


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    sec = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        vs, rva, rs, ra = struct.unpack_from("<IIII", d, sec + 40 * i + 8)
        if rva <= va - 0x400000 < rva + rs:
            return ra + va - 0x400000 - rva
    sys.exit("ABORT: %08X has no file bytes" % va)


def sites(d):
    out = []
    for label, (lo, ln) in (("master", MASTER), ("live", (va2off(d, LIVE_VA), LIVE_LEN))):
        blob = bytes(d[lo:lo + ln])
        assert blob[:4] == b"TPF0", "%s TITEMEDITFORM is not a DFM at file %#x" % (label, lo)
        for nm in NAMES:
            i = blob.find(b"\x05TSpin" + bytes([len(nm)]) + nm)
            assert i >= 0, "%s: %s not found" % (label, nm)
            m = re.compile(rb"\x08MinValue\x02(.)", re.S).search(blob, i, i + 200)
            assert m, "%s: %s has no MinValue" % (label, nm)
            out.append((lo + m.start(1), label, nm.decode()))
    return out


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    d = bytearray(open(EXE, "rb").read())
    ss = sites(d)
    print("build_deved_itemneg -- %s" % EXE)
    for off, label, nm in ss:
        v = d[off]
        st = "0" if v == MIN_OLD else "-60" if v == MIN_NEW else "FOREIGN %d" % v
        print("  %-6s %-15s MinValue @file %#x: %s" % (label, nm, off, st))
    if any(d[o] not in (MIN_OLD, MIN_NEW) for o, _l, _n in ss):
        sys.exit("ABORT: a MinValue holds an unexpected value")
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    want = MIN_NEW if apply_ else MIN_OLD
    if all(d[o] == want for o, _l, _n in ss):
        print("\nnothing to do")
        return
    kill_aow()
    with open(EXE, "r+b") as f:
        for off, _l, _n in ss:
            f.seek(off)
            f.write(bytes([want]))
    print("\n%s -- now run build_zigeditor.py --apply" % ("APPLIED" if apply_ else "UNDONE"))


if __name__ == "__main__":
    main()
