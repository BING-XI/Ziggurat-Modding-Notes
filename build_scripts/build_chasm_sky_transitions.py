#!/usr/bin/env python3
r"""
AoW1 mod -- Chasm & Sky terrain, STEP 3: real CLIFF edges.  (v2, 2026-07-27)

WHAT THE EDGES SHOULD BE
  In `Images/HexTrans.ILB` the transition images are keyed by IMAGE ID and the id
  space is exactly `terrain*16 + k` (k 0..2 = neighbour-side, 3..5 = own-side drawn
  displaced, 6..14 = generic land-land blend).  Measured with re_tools/ilb.py:
     ids 0xA0..0xA5 = `tu_xx-wa.BMP`  -- the CAVE-WATER cliff (underground water
                                         sits below the floor, so its edge is a
                                         drop-off / cliff face)
     ids 0x90..0x95 = `tu_xx-la.BMP`  -- the same idea for lava
     ids 0xB6..0xBE = `tu_wl.BMP`     -- the underground-WASTELAND generic blend,
                                         a soft edge, NOT a cliff
  v1 of this patch pointed Sky at 0xB6 (and Chasm reached it by the generic
  formula), which is why the edges came out as a soft dark band rather than a cliff.

THIS PATCH (v2)
  Remap the two working terrain values inside TAoWHexagon.UpdateTransition so that
  Chasm (0xB) and Sky (0xE) are treated as CaveWater (0xA) for edge selection only:

      O (own terrain, EBP) : 0xB / 0xE -> 0xA
      N (neighbour, EDI)   : 0xB / 0xE -> 0xA

  Everything downstream then falls out for free, because the vanilla rule table
  already knows how to draw a cave-water edge from both sides:
      O==CaveWater -> id 0xA3+d, flagged "draw displaced onto the neighbour"
      N==CaveWater -> id 0xA0+d  (the LAND hex draws the cliff face in place)
  and the combinations keep working too (Lava beside a Chasm hits the shared
  0xB6 lava<->cave-liquid block; CaveIce beside one hits 0xD0+d).
  Chasm next to Sky compares equal after the remap, so no edge is drawn between
  them -- correct, they are both "void".

  This only rewrites EBP/EDI inside the edge-selection routine; the hex's own tile
  art still comes from its real terrain byte via GetRndResource.

SITES
  hook  0x5579AA92: `movsx ebp,al` + `cmp ebp,edi` (5 bytes) -> jmp cave,
        cave redoes both, remaps, re-issues the cmp and jumps back to 0x5579AA97
        (a jmp does not disturb the flags the following `je` reads).
  undo  0x5579AC74: v1's redirect is restored to `mov edx,ebp / shl edx,4`.  This
        is REQUIRED, not cosmetic -- v1 jumped into the same cave address this
        patch reuses, so leaving it would run the new code with the wrong resume.
  cave  0x55812000 (verified zero region in CODE, 8KB).
  Register-only + rel32 => position independent, which AoWEPACK requires.

Idempotent (accepts pristine, v1 or v2 state), verify-before-write, auto-backup to
AoWEPACK.dpl.pre-skytrans2, dry-run by default -- pass --apply.
Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first (all three lock the DLL).
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-skytrans2")
DLL_BASE = 0x55700000

CHASM, SKY, CAVEWATER = 0x0B, 0x0E, 0x0A

HOOK      = 0x5579AA92                          # movsx ebp,al ; cmp ebp,edi
HOOK_ORIG = bytes.fromhex("0fbee83bef")
RESUME    = 0x5579AA97                          # the `je` that follows the cmp
CAVE      = 0x55812000

V1_SITE   = 0x5579AC74                          # v1 hook, must be reverted
V1_ORIG   = bytes.fromhex("8bd5c1e204")         # mov edx,ebp ; shl edx,4
V1_PATCHED = b"\xE9" + struct.pack("<i", CAVE - (V1_SITE + 5))


def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize; secs = []
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr, vsize, raw, rsize)); sec += 40
    return secs


def va2off(secs, va):
    rva = va - DLL_BASE
    for vaddr, vsize, raw, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    raise ValueError(f"VA {va:08X} not mapped")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    ks, cs = Ks(KS_ARCH_X86, KS_MODE_32), Cs(CS_ARCH_X86, CS_MODE_32)

    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)

    cave_src = f"""
        movsx ebp, al
        cmp ebp, {SKY}
        je _map_o
        cmp ebp, {CHASM}
        jne _chk_n
    _map_o:
        mov ebp, {CAVEWATER}
    _chk_n:
        cmp edi, {SKY}
        je _map_n
        cmp edi, {CHASM}
        jne _done
    _map_n:
        mov edi, {CAVEWATER}
    _done:
        cmp ebp, edi
        jmp 0x{RESUME:X}
    """
    cave = bytes(ks.asm(cave_src, CAVE)[0])
    redir = b"\xE9" + struct.pack("<i", CAVE - (HOOK + 5))
    assert len(redir) == len(HOOK_ORIG) == 5

    h_off, c_off, v_off = (va2off(secs, HOOK), va2off(secs, CAVE),
                           va2off(secs, V1_SITE))
    cur_hook = bytes(data[h_off:h_off+5])
    cur_cave = bytes(data[c_off:c_off+len(cave)])
    cur_v1   = bytes(data[v_off:v_off+5])

    print(f"AoWEPACK.dpl  hook {HOOK:#x} (file {h_off:#x}); cave {CAVE:#x} "
          f"({len(cave)}B); v1 site {V1_SITE:#x}")
    for a, sz, mn, op in cs.disasm_lite(cave, CAVE):
        print(f"    {a:08X}  {mn:<6} {op}")

    if cur_hook == redir and cur_cave == cave and cur_v1 == V1_ORIG:
        print("already at v2 - idempotent no-op"); return 0
    if cur_hook not in (HOOK_ORIG, redir):
        print(f"ABORT: hook bytes unexpected: {cur_hook.hex()}"); return 1
    if cur_v1 not in (V1_ORIG, V1_PATCHED):
        print(f"ABORT: v1 site bytes unexpected: {cur_v1.hex()}"); return 1
    zone = bytes(data[c_off+len(cave):c_off+len(cave)+0x20])
    if zone.strip(b"\x00"):
        print(f"ABORT: cave tail not zero: {zone.hex()}"); return 1

    print(f"    hook  {cur_hook.hex()} -> {redir.hex()}")
    if cur_v1 != V1_ORIG:
        print(f"    v1 revert {cur_v1.hex()} -> {V1_ORIG.hex()} (its cave is reused)")
    if not args.apply:
        print("dry run - re-run with --apply to write"); return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP); print(f"    backup -> {os.path.basename(BACKUP)}")
    data[v_off:v_off+5] = V1_ORIG                       # undo v1 FIRST
    data[c_off:c_off+len(cave)] = cave
    data[c_off+len(cave):c_off+0x40] = b"\x00" * (0x40 - len(cave))
    data[h_off:h_off+5] = redir
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        print("LOCKED - close AoW.exe / AoWCompat.exe / AoWDevEd.exe and retry"); return 1
    print("applied: Chasm(0xB) and Sky(0xE) now use the CaveWater cliff edges "
          "(ids 0xA0+d neighbour-side / 0xA3+d own-side)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
