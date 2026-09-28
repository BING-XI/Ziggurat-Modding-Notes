#!/usr/bin/env python3
r"""
AoW1 mod -- Monster Slaying rework (owner's design, 2026-09-26; melee +4 -> +5 on 2026-09-28).

    melee   +5 DAM against a Monster, +5 DEF when a Monster strikes the unit   (was +5 ATK / +5 DAM)
    ranged  +2 DAM against a Monster, +2 DEF against a Monster's shot/breath   (was +2 ATK / +2 DAM)

The DEF applies to every melee strike -- deliberate, retaliation, opportunity, Round Attack -- and
breath counts as ranged. The rule, the numbers, the delivery (DEF as an ATK reduction on the
Monster's strike, Parry's own mechanism) and the byte-vs-dword clamp policy are documented once,
in monsterslay.py.

RNG: none. The rework adds no draw and moves none (the bonus is a pure stat adjustment, before
the engine's own roll), so the four-pattern selection test does not apply.

WHAT THIS SCRIPT OWNS
---------------------
    ms_test   0x5584F300   the shared test (monsterslay.blob()); also installed zero-or-ours by
                           build_assassin.py and build_ranged_slayers.py, whose caves call it
    cave_sdv  0x5584F380   StrikeDV @0x55766564 (the AI's strike value, combat objects,
                           EDI=attacker ESI=target BL=ATK [ESP]=DAM) -> resumes 0x55766591
    cave_cus  0x5584F3C0   TMeleeRound.CalculateUnitStrikes @0x55767904 (strategic units,
                           VMT+0x148, ESI=attacker EDI=target EBX=strike record) -> 0x55767931

Both hooks overwrite only the 5-byte `mov edx,0x70` that opens vanilla's Monster Slaying block;
the rest of the block (its `add` immediates, still +5 from build_buff_regrade.py) is dead code
behind the jump. No `.reloc` entry falls in either 5-byte window, and the only jumps into the
blocks target their first byte.

The other three sites live in caves owned by build_assassin.py (cave_melee, cave_melee3) and
build_ranged_slayers.py (cave_rng); their generators switch on monsterslay.REWORK. Apply all three
scripts; order does not matter, because each one installs ms_test before writing a caller.

RE-TUNE: change the numbers in monsterslay.py and re-run --apply here and in build_assassin.py.
Both accept their own bodies built with any number in monsterslay.RETUNE.

USAGE
    build_monster_slaying.py            dry run: verify state, print the caves
    build_monster_slaying.py --apply    write
    build_monster_slaying.py --undo     SURGICAL: restore both hooks, zero both caves, and zero
                                        ms_test only when no cave outside this zone still calls it
                                        (set monsterslay.REWORK = False and re-apply the two owner
                                        scripts first to remove those callers)
"""
import os, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monsterslay as ms

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)
DLL_BASE = 0x55700000

HOOK_ORIG = bytes.fromhex("ba 70 00 00 00")          # mov edx, 0x70

SDV_INJ, SDV_CONT, CAVE_SDV = 0x55766564, 0x55766591, ms.ZONE_VA + 0x80
CUS_INJ, CUS_CONT, CAVE_CUS = 0x55767904, 0x55767931, ms.ZONE_VA + 0xC0

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]; n = struct.unpack_from("<H", data, e + 6)[0]
    op = struct.unpack_from("<H", data, e + 20)[0]; s = e + 24 + op; secs = []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", data, s + 8); secs.append((va, vs, raw, rs)); s += 40
    return secs

def va2off(secs, va):
    rva = va - DLL_BASE
    for va0, vs, raw, rs in secs:
        if va0 <= rva < va0 + max(vs, rs): return raw + (rva - va0)
    raise ValueError(hex(va))

def jmp(src, dst): return b"\xE9" + struct.pack("<i", dst - (src + 5))

def asm(src, va): return bytes(ks.asm(src, va)[0])

def build_sdv(dam, dfn):
    return asm(ms.call_text("edi", "esi", 0xA8)
               + ms.apply_text("_sd", "byte ptr [esp]", "bl", dam, dfn, clamp=True)
               + f"\n    jmp 0x{SDV_CONT:X}\n", CAVE_SDV)

def build_cus(dam, dfn):
    return asm(ms.call_text("esi", "edi", 0x148)
               + ms.apply_text("_cu", "dword ptr [ebx+4]", "dword ptr [ebx]", dam, dfn, clamp=False)
               + f"\n    jmp 0x{CUS_CONT:X}\n", CAVE_CUS)

cave_sdv = build_sdv(ms.MELEE_DAM, ms.MELEE_DEF)
cave_cus = build_cus(ms.MELEE_DAM, ms.MELEE_DEF)
# our bodies at every re-tunable number: an installed one is rewritten in place, not refused
VARIANTS = {va: {f(d, e) for d in ms.RETUNE for e in ms.RETUNE}
            for va, f in ((CAVE_SDV, build_sdv), (CAVE_CUS, build_cus))}
assert CAVE_SDV + len(cave_sdv) <= CAVE_CUS, "cave_sdv overruns cave_cus"
assert CAVE_CUS + len(cave_cus) <= ms.ZONE_VA + ms.ZONE_LIMIT, "cave_cus overruns the zone"
assert len(ms.blob()) <= CAVE_SDV - ms.MS_TEST

APPLY = "--apply" in sys.argv
UNDO = "--undo" in sys.argv

def show():
    ms.show()
    for name, va, b in (("cave_sdv", CAVE_SDV, cave_sdv), ("cave_cus", CAVE_CUS, cave_cus)):
        print(f"   {name} @ {va:08X} ({len(b)} B)")
        for i in cs.disasm(b, va):
            print(f"     {i.address:08X} {i.bytes.hex(' '):<24}{i.mnemonic} {i.op_str}")

def process(path):
    data = bytearray(open(path, "rb").read()); secs = load_sections(data)
    def rd(va, n): o = va2off(secs, va); return bytes(data[o:o + n])
    def wr(va, b): o = va2off(secs, va); data[o:o + len(b)] = b
    def flush():
        try: open(path, "wb").write(data)
        except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
        return True

    # (va, original, new, desc). A cave accepts zeros or any of its VARIANTS; a hook accepts stock
    # or our jmp.
    own = [
        (CAVE_SDV, cave_sdv, "cave_sdv (StrikeDV)"),
        (CAVE_CUS, cave_cus, "cave_cus (CalculateUnitStrikes)"),
    ]
    hooks = [
        (SDV_INJ, jmp(SDV_INJ, CAVE_SDV), "StrikeDV 0x55766564 -> cave_sdv"),
        (CUS_INJ, jmp(CUS_INJ, CAVE_CUS), "CalculateUnitStrikes 0x55767904 -> cave_cus"),
    ]
    bad = False
    for va, new, desc in own:
        cur = rd(va, len(new))
        if any(cur) and cur not in VARIANTS[va]:
            print(f"[x] {va:08X} {desc}: occupied by something else\n     {cur.hex(' ')}"); bad = True
    for va, new, desc in hooks:
        cur = rd(va, 5)
        if cur not in (HOOK_ORIG, new):
            print(f"[x] {va:08X} {desc}: neither stock nor ours\n     {cur.hex(' ')}"); bad = True
    st = ms.state(rd)
    print(f"[i] ms_test {ms.MS_TEST:08X}: {st}")
    if st == "foreign":
        print("[x] ms_test slot holds something that is not ours"); bad = True
    if bad:
        print("[x] mismatch -- nothing written"); return False

    if UNDO:
        for va, new, desc in hooks:
            wr(va, HOOK_ORIG); print(f"[w ] {va:08X} restored (mov edx,0x70)")
        for va, new, desc in own:
            wr(va, bytes(len(new))); print(f"[w ] {va:08X} {desc} zeroed")
        left = ms.callers(rd, exclude=((ms.ZONE_VA, ms.ZONE_VA + ms.ZONE_LIMIT),))
        if left:
            print("[i] ms_test kept -- still called from " + ", ".join(f"{v:08X}" for v in left)
                  + "\n    (set monsterslay.REWORK = False, re-apply build_assassin.py and"
                  "\n     build_ranged_slayers.py, then run --undo again to clear it)")
        else:
            wr(ms.MS_TEST, bytes(CAVE_SDV - ms.MS_TEST))
            print(f"[w ] {ms.MS_TEST:08X} ms_test zeroed -- no caller left")
        return flush()

    patches = [ms.patch_entry(rd)] + [(va, rd(va, len(n)), n, d) for va, n, d in own] \
            + [(va, rd(va, 5), n, d) for va, n, d in hooks]
    if all(rd(va, len(n)) == n for va, _o, n, _d in patches):
        print("[= ] already applied"); return True
    if not APPLY:
        print("[dry] originals verified"); return True
    for va, _o, n, d in patches:
        if rd(va, len(n)) != n:
            wr(va, n); print(f"[w ] {va:08X} {d}")
    return flush()

if "--dis" in sys.argv or not (APPLY or UNDO):
    show()
print()
ok = process(os.path.join(GAME, "AoWEPACK.dpl"))
if not (APPLY or UNDO):
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif not ok:
    print("\n[!] not written")
