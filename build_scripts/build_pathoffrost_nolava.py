#!/usr/bin/env python
r"""
build_pathoffrost_nolava.py -- Path of Frost no longer turns lava into wasteland.

WHAT
----
`PathOfFrostTerrainChange @0x557801E4` (the Path of Frost ability's per-hex terrain change) carried
an unowned hand-edit: its surface land->snow arm at 0x55780231 was replaced by
`call 0x5580BFA0` + 16 NOPs.  That 31-byte cave replays the vanilla arm and adds lava (9) ->
wasteland (5) on every level.  Owner ruling 2026-09-24: only the relevant spells and altars turn
lava into wasteland, never Path of Frost.  This script puts the 21 vanilla bytes back, so the
function is byte-identical to the root reference again: water -> ice (0 -> 6), 0x0A -> 0x0D, and
on the surface only grassland-type terrains 1/2/4/5 -> snow 3.

    live (hand-edit)                          vanilla (restored)
    55780231  E8 6A BD 08 00  call 5580BFA0   55780231  8A 01        mov  al,[ecx]
    55780236  90 x 16         nop             55780233  48 / 2C 02   dec eax / sub al,2
                                              55780236  72 05        jb   5578023D
                                              55780238  48 / 2C 02   dec eax / sub al,2
                                              5578023B  73 09        jae  55780246
                                              5578023D  80 7F 12 00  cmp  byte [edi+12h],0
                                              55780241  75 03        jne  55780246
                                              55780243  C6 01 03     mov  byte [ecx],3

The cave at 0x5580BFA0 (31 B) is left in place with no caller -- the scan in this script proves
0x55780231 is its only one -- so --undo can re-link it.  It is not free space while --undo is a
possible path.

No absolute operand on either side, no .reloc in the 21 bytes (checked on --apply).  Not a roll.

USAGE
    python build_pathoffrost_nolava.py            verify / dry run (writes nothing)
    python build_pathoffrost_nolava.py --apply    restore the vanilla land arm
    python build_pathoffrost_nolava.py --undo     re-install `call 0x5580BFA0` + 16 NOPs
"""
import os, sys, struct, argparse, subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
IMAGE_BASE = 0x55700000

SITE = 0x55780231
CAVE = 0x5580BFA0
VANILLA = bytes.fromhex("8A01482C027205482C02730980 7F120075 03C60103".replace(" ", ""))
HANDEDIT = b"\xE8" + struct.pack("<i", CAVE - (SITE + 5)) + b"\x90" * 16
CAVE_BODY = bytes.fromhex("8A01482C027205482C027309807F1200750CC601036683F8037503C60105C3")

AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")


def kill_aow():
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    return e, [struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8) for i in range(nsec)]


def va2off(d, va):
    rva = va - IMAGE_BASE
    for vsize, vaddr, rsize, raw in pe(d)[1]:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def relocs_in(d, lo, hi):
    e = pe(d)[0]
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


def callers(d, target):
    """VAs of every E8/E9 rel32 in any section that lands on `target` (per-section mapping)."""
    hits = []
    for vsize, vaddr, rsize, raw in pe(d)[1]:
        for i in range(raw, raw + min(vsize or rsize, rsize) - 5):
            if d[i] in (0xE8, 0xE9):
                va = IMAGE_BASE + vaddr + (i - raw)
                if va + 5 + struct.unpack_from("<i", d, i + 1)[0] == target:
                    hits.append(va)
    return hits


def main():
    ap = argparse.ArgumentParser(description="Path of Frost: no lava -> wasteland")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    assert len(VANILLA) == len(HANDEDIT) == 21
    d = bytearray(open(TARGET, "rb").read())
    o = va2off(d, SITE)
    cur = bytes(d[o:o + 21])
    st = "applied" if cur == VANILLA else "clean" if cur == HANDEDIT else "foreign"
    c = va2off(d, CAVE)
    cave_ok = bytes(d[c:c + len(CAVE_BODY)]) == CAVE_BODY
    who = callers(d, CAVE)
    print("build_pathoffrost_nolava -- %s" % TARGET)
    print("site %08X: %s" % (SITE, {"applied": "vanilla land arm (lava untouched)",
                                    "clean": "call %08X (lava -> wasteland)" % CAVE,
                                    "foreign": cur.hex(" ")}[st]))
    print("cave %08X: %s; callers %s" % (CAVE, "intact" if cave_ok else "CHANGED",
                                         ", ".join("%08X" % v for v in who) or "none"))
    print("state: %s" % st.upper())
    if st == "foreign":
        sys.exit("ABORT: site holds neither the vanilla arm nor the hand-edit")
    if set(who) - {SITE}:
        sys.exit("ABORT: the cave has callers other than %08X -- restoring the arm would not "
                 "retire it" % SITE)

    want = VANILLA if a.apply else HANDEDIT if a.undo else None
    if want is None:
        print("\n(dry run -- nothing written)")
        return
    if cur == want:
        print("\nalready %s -- nothing to do" % ("applied" if a.apply else "undone"))
        return
    if a.undo and not cave_ok:
        sys.exit("ABORT: the cave body changed -- re-linking it would call unknown code")
    hits = relocs_in(d, SITE, SITE + 21)
    if hits:
        sys.exit("ABORT: .reloc covers %s inside the site" % ", ".join("%08X" % v for v in hits))
    kill_aow()
    with open(TARGET, "r+b") as f:
        f.seek(o)
        f.write(want)
    assert open(TARGET, "rb").read()[o:o + 21] == want, "write did not stick"
    print("\n%s: %08X = %s" % ("APPLIED" if a.apply else "UNDONE", SITE, want.hex(" ")))


if __name__ == "__main__":
    main()
