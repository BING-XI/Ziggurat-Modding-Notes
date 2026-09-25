#!/usr/bin/env python
r"""
build_ai_touch_herovalue.py -- AI hero/leader touch moves valued x50 instead of x1.

WHAT
----
In `AoWTC.TCAI.CheckUnit`'s touch handler (AbilTypes category 4: Healing, Turn Undead, Dominate,
Web, Seduce, Entangle, Possess, Charm ...), the AddMove multiplier for an adjacent touch is chosen
at 0x4171DD and passed to `TCAI.MultDEV 0x414418` (EDX = DEV, ECX = multiplier, stack divisor 1):

    004171DD  8B 45 14              mov  eax,[ebp+0x14]        ; SELF (the mover)
    004171E0  8B 40 4C              mov  eax,[eax+0x4c]        ; its strategic unit
    004171E3  8B 15 14 E9 46 00     mov  edx,[0x46e914]        ; THero (TLeader inherits)
    004171E9  E8 6A 9E FE FF        call System.@IsClass
    004171EE  84 C0 / 74 09         test al,al / je 0x4171FB
    004171F2  C7 45 EC 01 00 00 00  mov  dword [ebp-0x14], 1   <-- hero/leader: x1   (this script)
    004171F9  EB 44                 jmp  0x41723F
    ...       C7 45 EC 0A 00 00 00  mov  dword [ebp-0x14], 10  ; wall, breached, after round 1
    00417238  C7 45 EC 64 00 00 00  mov  dword [ebp-0x14], 100 ; every other mover
    0041723F  ... 8B 4D EC ... E8 -> MultDEV                   ; ECX = [ebp-0x14]

A unit's touch is worth DEV x 100, a hero's DEV x 1, so an AI hero or leader walks up to a wounded
friend or an undead enemy (the non-adjacent approach move at 0x417276 has no hero term) and then never
uses the ability: every other proposal outranks it by two orders of magnitude.  Hero MELEE uses x50
(`0x415729`: `C7 45 EC 32 00 00 00`), and none of MultDEV's other callers passes 1.  Inioch's AoWx 410
changelog calls it the same bug ("pulling a '1' flag as a 0.01 multiplier").

THE CHANGE -- one byte, the low byte of the imm32
    004171F5  01 -> 32                                          ; x1 -> x50, hero melee's value

Nothing is displaced: an immediate inside an existing instruction, so no cave, no E9, and no .reloc
under it (--apply refuses otherwise).  The upper three imm bytes stay 00.  His AoWx port replaced the
block with a heal-tier cave at 0x4171DD; that is not ported -- only the multiplier.

Not a roll: no draw of either generator is added, moved or gated.

TUNING / RE-TUNE
    HERO_TOUCH_PCT below.  --apply over an installed value rewrites the byte in place (the whole
    block is anchored, the imm masked), so a re-tune never needs --undo first.

USAGE
    python build_ai_touch_herovalue.py            verify / dry run (writes nothing)
    python build_ai_touch_herovalue.py --apply    write HERO_TOUCH_PCT
    python build_ai_touch_herovalue.py --undo     restore vanilla 1
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "AoWTCPCK.dpl")
FEATURE = "aitouchhero"
BACKUP_DIR = os.path.join(GAME, "backups")        # never beside the target (rule 2026-09-03)

# ---- tunable ------------------------------------------------------------------------------------
HERO_TOUCH_PCT = 50       # multiplier for a hero/leader touch move; vanilla 1, units 100, hero melee 50

# ---- engine facts (vanilla AoWTCPCK.dpl, preferred base 0x400000) --------------------------------
VANILLA_PCT = 1
SITE = 0x004171F2         # mov dword [ebp-0x14], imm32   (C7 45 EC imm32)
IMM = SITE + 3            # 0x004171F5
BLOCK_LO, BLOCK_HI = 0x004171DD, 0x00417253     # IsClass(THero) test .. call MultDEV, anchored whole
BLOCK = (                                                 # hex text; the imm32 is masked
    "8b4514" "8b404c" "8b1514e94600" "e86a9efeff" "84c0" "7409"
    "c745ec" "XXXXXXXX"                                   # <- the imm32
    "eb44" "8b4510" "8b15fce84600" "e84f9efeff" "84c0" "742b"
    "a164c04600" "8b80e4000000" "8b400c" "80784d00" "7417"
    "a164c04600" "83b83401000001" "7e09"
    "c745ec0a000000" "eb07" "c745ec64000000"
    "8b45f4" "50" "6a01" "8b4dec" "8b559c" "8b45fc" "e8c5d1ffff")
MULTDEV = 0x00414418
HERO_MELEE = (0x00415729, bytes.fromhex("c745ec32000000"))   # reference value, read only

AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")


# ---- PE helpers ---------------------------------------------------------------------------------
def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    for i in range(nsec):
        s = e + 24 + opt + 40 * i
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, s + 8)
        yield d[s:s + 8].rstrip(b"\0").decode("latin1"), vaddr, max(vsize, rsize), raw


def image_base(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    return struct.unpack_from("<I", d, e + 24 + 28)[0]


def va2off(d, va):
    rva = va - image_base(d)
    for _n, vaddr, size, raw in sections(d):
        if vaddr <= rva < vaddr + size:
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def relocs_in(d, lo, hi):
    """VAs of type!=0 base relocations whose 4-byte target overlaps [lo, hi)."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    if not size:
        return []
    ib = image_base(d)
    off = va2off(d, ib + rva)
    end, hits = off + size, []
    while off < end:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * k)[0]
            if ent >> 12:
                va = ib + page + (ent & 0xFFF)
                if va < hi and va + 4 > lo:
                    hits.append(va)
        off += blk
    return hits


def kill_aow():
    if os.environ.get("AOW_GAME_DIR"):       # scratch copy: never kill the user's real game
        return
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


# ---- checks -------------------------------------------------------------------------------------
def check_block(d):
    """Anchor the whole IsClass(THero) -> pct -> MultDEV block; return the live imm32."""
    lo = va2off(d, BLOCK_LO)
    live = bytes(d[lo:lo + (BLOCK_HI - BLOCK_LO)])
    k = BLOCK.index("XXXXXXXX")
    want_head = bytes.fromhex(BLOCK[:k])
    want_tail = bytes.fromhex(BLOCK[k + 8:])
    if len(want_head) + 4 + len(want_tail) != BLOCK_HI - BLOCK_LO:
        sys.exit("ABORT: internal -- anchor length mismatch")
    head, imm, tail = live[:len(want_head)], live[len(want_head):len(want_head) + 4], \
        live[len(want_head) + 4:]
    if head != want_head or tail != want_tail:
        sys.exit("ABORT: the touch-multiplier block at %08X..%08X is not the one this script knows"
                 % (BLOCK_LO, BLOCK_HI))
    if BLOCK_LO + len(want_head) != IMM:
        sys.exit("ABORT: internal -- imm offset mismatch")
    call_at = BLOCK_HI - 5
    tgt = call_at + 5 + struct.unpack_from("<i", tail, len(tail) - 4)[0]
    if tgt != MULTDEV:
        sys.exit("ABORT: the block's call goes to %08X, not MultDEV %08X" % (tgt, MULTDEV))
    return struct.unpack("<I", imm)[0]


def show(d):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return
    o = va2off(d, 0x004171E9)
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(bytes(d[o:o + 0x12]), 0x004171E9):
        mark = "  <--" if ins.address == SITE else ""
        print("    %08X  %-22s %s %s%s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic,
                                         ins.op_str, mark))


def main():
    ap = argparse.ArgumentParser(description="AI hero/leader touch moves valued x%d" % HERO_TOUCH_PCT)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    if not (2 <= HERO_TOUCH_PCT <= 0x7F):
        sys.exit("HERO_TOUCH_PCT must be 2..127 (one byte, upper imm bytes stay 00)")

    d = bytearray(open(TARGET, "rb").read())
    cur = check_block(d)
    ho = va2off(d, HERO_MELEE[0])
    melee_ok = bytes(d[ho:ho + 7]) == HERO_MELEE[1]
    print("build_ai_touch_herovalue -- %s" % TARGET)
    print("hero/leader touch multiplier @%08X = %d   (vanilla %d, units 100, hero melee %s)"
          % (SITE, cur, VANILLA_PCT, "50 @0x415729" if melee_ok else "?? (0x415729 differs)"))
    if cur > 0x7F:
        sys.exit("ABORT: imm32 %#x is not a value this script writes" % cur)
    state = "vanilla" if cur == VANILLA_PCT else "applied" if cur == HERO_TOUCH_PCT else \
        "installed at another value (%d) -- --apply re-tunes in place" % cur
    print("state: %s" % state.upper())
    show(d)

    want = HERO_TOUCH_PCT if a.apply else VANILLA_PCT if a.undo else None
    if want is None:
        print("\n(dry run -- nothing written; --apply writes %d, --undo restores %d)"
              % (HERO_TOUCH_PCT, VANILLA_PCT))
        return
    if cur == want:
        print("\nalready %d -- nothing to do" % want)
        return
    hits = relocs_in(d, SITE, SITE + 7)
    if hits:
        sys.exit("ABORT: .reloc covers %s inside the instruction" % ", ".join("%08X" % v for v in hits))

    kill_aow()
    # ⚠ Snapshot only a file PROVED unpatched at this site, and only on --apply.
    if a.apply and cur == VANILLA_PCT:
        backup = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-" + FEATURE)
        if not os.path.exists(backup):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TARGET, backup)
            print("\nbackup -> %s" % backup)

    # in place: re-read, re-verify, write the one byte only (other agents may be patching this file)
    fresh = open(TARGET, "rb").read()
    if check_block(fresh) != cur:
        sys.exit("ABORT: the site changed under us -- re-run")
    o = va2off(fresh, IMM)
    with open(TARGET, "r+b") as f:
        f.seek(o)
        f.write(bytes([want]))
    back = open(TARGET, "rb").read()
    got = check_block(back)
    assert got == want, "write did not stick: %d" % got
    print("\n%s: %08X = %02X  (multiplier %d -> %d)"
          % ("APPLIED" if a.apply else "UNDONE", IMM, want, cur, want))
    show(back)


if __name__ == "__main__":
    main()
