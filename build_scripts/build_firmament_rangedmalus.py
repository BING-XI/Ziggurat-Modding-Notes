#!/usr/bin/env python
r"""
build_firmament_rangedmalus.py -- the Firmament is exempt from the underground ranged malus.

WHAT
----
A ranged attacker without Night Vision (0x27) takes -4 ATK below the surface: the Cave/Depths
malus, `sub bl,4`, doubled by stage 12 of the 5% conversion.  The test deciding "below the surface"
predates the Firmament and reads `level != 0`, so level 3 counted as underground.  Owner ruling
2026-09-24: exclude the Firmament.  Afterwards the malus applies on levels 1 (Caverns) and 2
(Depths) only -- the same surface-or-Firmament split `build_maplevel4.py` uses for vision and for
global-target casting.

THE SITE -- the unowned cave 0x5580C240 (12-re-toolchain.md cave table), clean layout
    5580C273  E8 1C 2B F7 FF  call TAbstractUnit.GetLocation   ; [esp]=x [esp+1]=y [esp+2]=level
    5580C278  8A 44 24 02     mov  al, [esp+2]
    5580C27C  83 C4 03        add  esp, 3
    5580C27F  3C 00           cmp  al, 0              <-- this script
    5580C281  74 03           je   0x5580C286         <-- this script
    5580C283  80 EB 04        sub  bl, 4              ; malus, fivepct_manifest.json stage 12
    5580C286  5E              pop  esi
    5580C287  C3              ret

THE CHANGE -- 4 bytes in place, same length, same jump target
    5580C27F  84 C0           test al, al
    5580C281  7A 03           jp   0x5580C286         ; PF=1 -> skip the malus

`test al,al` sets PF when the level byte has an even number of set bits:

    level  bits  PF  malus
      0    00    1   no     surface
      1    01    0   yes    Caverns
      2    10    0   yes    Depths
      3    11    1   no     Firmament

That is "level 0 or level 3" for the four levels the engine has; model() asserts it.  An explicit
compare pair needs 6 bytes, and the only spare bytes (the 8 at 0x5580C288..0x5580C28F) are the
growth zone `build_marksmanship_atk2.py` asserts is zero.

COUPLING
    * build_marksmanship_atk2.py (not applied; its dry run says CLEAN) moves this body +2 by
      copying it verbatim.  A rel8 jump moves with its target, so this change survives the move,
      and this script finds its site in either layout: 0x5580C27F when the cave starts `02 D8`,
      0x5580C281 when it starts `00 C0 02 D8`.
    * build_marksmanship8.py hooks the cave (`call 0x5580C240` @0x5576E689); untouched.
    * The malus immediate (site + 6) is fivepct_manifest.json's stage-12 row; untouched.

Not a roll.  No absolute operand.  --apply refuses if a .reloc entry covers the 4 bytes.

USAGE
    python build_firmament_rangedmalus.py            verify / dry run (writes nothing)
    python build_firmament_rangedmalus.py --apply    write the new test
    python build_firmament_rangedmalus.py --undo     restore `cmp al,0 / je`
"""
import os, sys, struct, argparse, subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
IMAGE_BASE = 0x55700000

CAVE = 0x5580C240
SITE_CLEAN = 0x5580C27F              # cave starts 02 D8        (add bl,al)
SITE_ATK2 = 0x5580C281               # cave starts 00 C0 02 D8  (atk2's add al,al inserted)
HEAD_CLEAN = b"\x02\xD8"
HEAD_ATK2 = b"\x00\xC0\x02\xD8"

PRE = bytes.fromhex("8A442402" "83C403")        # mov al,[esp+2] ; add esp,3
OLD = bytes.fromhex("3C007403")                  # cmp al,0 ; je +3
NEW = bytes.fromhex("84C07A03")                  # test al,al ; jp +3

AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")


def model():
    """The predicate NEW implements, checked against the ruling for every level."""
    for level in range(4):
        skip = bin(level).count("1") % 2 == 0          # PF after test al,al
        assert skip == (level in (0, 3)), level
    return True


def kill_aow():
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    sec = e + 24 + opt
    for i in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 40 * i + 8)
        yield vaddr, max(vsize, rsize), raw


def va2off(d, va):
    rva = va - IMAGE_BASE
    for vaddr, size, raw in sections(d):
        if vaddr <= rva < vaddr + size:
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def relocs_in(d, lo, hi):
    """VAs of base relocations whose 4-byte target overlaps [lo, hi)."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)   # data directory 5, PE32
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
            if ent >> 12:
                va = IMAGE_BASE + page + (ent & 0xFFF)
                if va < hi and va + 4 > lo:
                    hits.append(va)
        off += blk
    return hits


def locate(d):
    head = bytes(d[va2off(d, CAVE):va2off(d, CAVE) + 4])
    if head[:4] == HEAD_ATK2:
        return SITE_ATK2, "atk2 applied (+2)"
    if head[:2] == HEAD_CLEAN:
        return SITE_CLEAN, "atk2 not applied"
    sys.exit("ABORT: cave %08X starts %s -- neither layout this script knows" % (CAVE, head.hex(" ")))


def check_context(d, site):
    o = va2off(d, site)
    if bytes(d[o - 7:o]) != PRE:
        sys.exit("ABORT: %08X is not preceded by `mov al,[esp+2] / add esp,3` (%s)"
                 % (site, bytes(d[o - 7:o]).hex(" ")))
    tail = bytes(d[o + 4:o + 9])
    if tail[:2] != b"\x80\xEB" or tail[3:5] != b"\x5E\xC3":
        sys.exit("ABORT: %08X is not followed by `sub bl,imm8 / pop esi / ret` (%s)"
                 % (site, tail.hex(" ")))
    return tail[2]


def assemble_check(site):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    target = site + 7
    for src, want in (("cmp al, 0; je %#x" % target, OLD), ("test al, al; jp %#x" % target, NEW)):
        got = bytes(ks.asm(src, site)[0])
        assert got == want, "keystone: %s -> %s, expected %s" % (src, got.hex(), want.hex())


def show(d, site):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return
    o = va2off(d, site - 7)
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(bytes(d[o:o + 16]), site - 7):
        mark = "  <--" if site <= ins.address < site + 4 else ""
        print("    %08X  %-16s %s %s%s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic,
                                         ins.op_str, mark))


def main():
    ap = argparse.ArgumentParser(description="Firmament exempt from the underground ranged malus")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    model()
    d = bytearray(open(TARGET, "rb").read())
    site, layout = locate(d)
    malus = check_context(d, site)
    assemble_check(site)
    o = va2off(d, site)
    cur = bytes(d[o:o + 4])
    st = "applied" if cur == NEW else "clean" if cur == OLD else "foreign"
    print("build_firmament_rangedmalus -- %s" % TARGET)
    print("cave %08X (%s), site %08X, malus sub bl,%d" % (CAVE, layout, site, malus))
    print("state: %s" % st.upper())
    show(d, site)
    if st == "foreign":
        sys.exit("ABORT: site holds %s -- neither the vanilla-cave test nor this script's" % cur.hex(" "))

    want = NEW if a.apply else OLD if a.undo else None
    if want is None:
        print("\n(dry run -- nothing written)")
        return
    if cur == want:
        print("\nalready %s -- nothing to do" % ("applied" if a.apply else "undone"))
        return
    hits = relocs_in(d, site, site + 4)
    if hits:
        sys.exit("ABORT: .reloc covers %s inside the site" % ", ".join("%08X" % v for v in hits))
    kill_aow()
    d[o:o + 4] = want
    with open(TARGET, "r+b") as f:
        f.seek(o)
        f.write(want)
    back = open(TARGET, "rb").read()[o:o + 4]
    assert back == want, "write did not stick: %s" % back.hex()
    print("\n%s: %08X = %s" % ("APPLIED" if a.apply else "UNDONE", site, want.hex(" ")))
    show(d, site)


if __name__ == "__main__":
    main()
