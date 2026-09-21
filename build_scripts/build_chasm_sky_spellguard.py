#!/usr/bin/env python3
r"""
AoW1 mod -- Chasm & Sky terrain, STEP 4: keep spells from terraforming them away.

Chasm (terrain 0xB) and Sky (terrain 0xE) are appropriated ids, so every vanilla
"convert any land to X" effect happily overwrites them.  This adds an exclusion for
both ids to the SEVEN effects that actually threaten them.

AUDITED -- the seven that DO threaten them
  1. Death Storm   `TDeathStorm.ChangeStormTerrain`  557CD304  any land except 0/6 -> Wasteland
  2. Divine Storm  `TDivineStorm.ChangeStormTerrain` 557CD6DC  any land except 0/6 -> Grass
  3. Ice Storm     `TIceStorm.ChangeStormTerrain`    557CCEF0  catch-all else -> Snow
  4. Flood         `TFloodControl.Flood`             557F1474  floodable unless terrain in
                                                              {0,6,F} or overlay in {0,2,7}
  5. Raise Terrain `TRaiseTerrain.ValidTargetMapF`   557A35CB  rejects only 0/6/A/D, so a
                                                              mountain could be raised on one
  6. Path of Life  `TAbstractUnit.PathOfLifeTerrainChange`  557801A4  any land except 0/6 -> Grass
  7. Path of Decay `TAbstractUnit.PathOfDecayTerrainChange` 557801C4  any land except 0/6 -> Wasteland
     (both are movement-triggered: a unit with the ability rewrites terrain as it walks.
      They are additionally gated to map level 0 by `cmp byte [edx+0x12],0`, so they only
      threaten a SURFACE Chasm/Sky -- but the palette can place either terrain on any level,
      so both ids are excluded regardless.)

AUDITED CLEAN -- deliberately NOT patched (they test specific ids, never 0xB/0xE)
  Fire Storm (helper 5580BE74: only 6, D, 2), Healing Showers (5580BF2F: 2, 4, 5, 9),
  Rejuvenate/"Desiccate" (5580C001: 1, 3, 4, 5, C), Blast Storm (557CCAB0: empty),
  Freeze Water (5579E884: only 0 and A, plus a 6/D frozen-marker refresh), Level Terrain
  (5579F068: only EarthWall 7 -> Dirt), **Path of Frost** (557801E4: only 0 -> 6 and A -> D,
  plus the 6/D refresh) and **Path of Sand** (this mod's own ability, callback cave 5580DF00:
  only 1, 3, 4, 5, C).  Sand and Frost are safe for the same reason as their spell cousins --
  they enumerate source terrains instead of using a catch-all else.

HOW
  Death/Divine Storm are tiny self-contained functions, so their cave is the WHOLE
  rewritten function (entry replaced by `jmp cave`; the cave returns directly) with
  0xB/0xE added to the skip list.
  Path of Life/Decay are the same shape (whole-function caves) plus the vanilla level-0 gate.
  The remaining three (Ice Storm, Flood, Raise Terrain) are 5-byte guards that re-do the
  displaced instructions, test the two ids, and either jump to the site's own "leave it alone"
  target or fall back into the original flow.  A `jmp` does not disturb the flags the
  following `je` reads.

  ⚠ Ice Storm is ALREADY modded by build_icestorm_lava.py (entry gate cave 5580DB40,
  else-path cave 5580DB20).  This patch takes over only the 5-byte `jmp 5580DB20` at
  557CCEF0 and CHAINS: not Chasm/Sky -> jmp 5580DB20 (that feature runs untouched);
  Chasm/Sky -> jmp epilogue 557CCF39.  No byte of the other feature's caves is written.

Caves live at 0x55812100+ (verified zeros), clear of the transition cave at 0x55812000.
Register-only + rel32 => position independent, which AoWEPACK requires.

Idempotent, verify-before-write, auto-backup AoWEPACK.dpl.pre-spellguard, dry-run by
default -- pass --apply.  Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first.

REVERT: NOT by snapshot -- restoring the whole file would wipe every feature applied after the
snapshot was taken, and there is no snapshot layer at all now (both stacks were purged,
2026-08-08 and 2026-09-09).  This feature's footprint is 7 hook sites + one cave zone, so undo it
surgically: restore the original 5 bytes listed in SITES and zero 0x55812100..0x55812220.
Any snapshot this script mints goes to <game dir>\backups\.
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-spellguard")
DLL_BASE = 0x55700000
CHASM, SKY = 0x0B, 0x0E
CAVE_BASE = 0x55812100

# site VA -> (original 5 bytes, label)
SITES = {
    0x557CD304: ("558bec0fbe", "Death Storm"),
    0x557CD6DC: ("558bec0fbe", "Divine Storm"),
    0x557CCEF0: ("e92b0c0400", "Ice Storm else-path"),
    0x557F1474: ("8a431484c0", "Flood floodable test"),
    0x557A35CB: ("8a431484c0", "Raise Terrain target"),
    0x557801A4: ("558bec0fbe", "Path of Life"),
    0x557801C4: ("558bec0fbe", "Path of Decay"),
}


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

    # ---- assemble the caves, laid out back to back ----
    def storm_cave(newterrain):
        return f"""
            push ebp
            mov ebp, esp
            movsx eax, byte ptr [ecx]
            test ax, ax
            je _skip
            cmp ax, 6
            je _skip
            cmp ax, {CHASM}
            je _skip
            cmp ax, {SKY}
            je _skip
            mov byte ptr [ecx], {newterrain}
        _skip:
            pop ebp
            ret 4
        """
    def path_cave(newterrain):
        """PathOfLife/Decay: same shape as the storms but with the level-0 gate."""
        return f"""
            push ebp
            mov ebp, esp
            movsx eax, byte ptr [ecx]
            cmp ax, 6
            je _skip
            test ax, ax
            je _skip
            cmp ax, {CHASM}
            je _skip
            cmp ax, {SKY}
            je _skip
            cmp byte ptr [edx + 0x12], 0
            jne _skip
            mov byte ptr [ecx], {newterrain}
        _skip:
            pop ebp
            ret 4
        """

    srcs = [
        ("death",  0x557CD304, storm_cave(5)),
        ("divine", 0x557CD6DC, storm_cave(1)),
        ("ice",    0x557CCEF0, f"""
            cmp ax, {CHASM}
            je _skip
            cmp ax, {SKY}
            je _skip
            jmp 0x5580DB20
        _skip:
            jmp 0x557CCF39
        """),
        ("flood",  0x557F1474, f"""
            mov al, byte ptr [ebx + 0x14]
            cmp al, {CHASM}
            je _skip
            cmp al, {SKY}
            je _skip
            test al, al
            jmp 0x557F1479
        _skip:
            jmp 0x557F1506
        """),
        ("raise",  0x557A35CB, f"""
            mov al, byte ptr [ebx + 0x14]
            cmp al, {CHASM}
            je _bad
            cmp al, {SKY}
            je _bad
            test al, al
            jmp 0x557A35D0
        _bad:
            jmp 0x557A35F6
        """),
        ("pathlife",  0x557801A4, path_cave(1)),
        ("pathdecay", 0x557801C4, path_cave(5)),
    ]
    caves, addr = [], CAVE_BASE
    for name, site, src in srcs:
        code = bytes(ks.asm(src, addr)[0])
        caves.append((name, site, addr, code))
        addr += (len(code) + 15) & ~15               # 16-byte spacing
    total = addr - CAVE_BASE

    print(f"AoWEPACK.dpl  caves at {CAVE_BASE:#x}..{addr:#x} ({total} bytes)")
    for name, site, cva, code in caves:
        print(f"  {SITES[site][1]:22} site {site:#x} -> cave {cva:#x} ({len(code)}B)")

    # ---- verify + stage every write ----
    cave_off = va2off(secs, CAVE_BASE)
    zone = bytes(data[cave_off:cave_off + total + 0x20])
    patched_zone = any(c for _, _, _, code in caves for c in code)
    writes, done = [], 0
    for name, site, cva, code in caves:
        s_off = va2off(secs, site)
        cur = bytes(data[s_off:s_off+5])
        orig = bytes.fromhex(SITES[site][0])
        redir = b"\xE9" + struct.pack("<i", cva - (site + 5))
        c_off = va2off(secs, cva)
        cur_cave = bytes(data[c_off:c_off+len(code)])
        if cur == redir and cur_cave == code:
            done += 1; continue
        if cur != orig:
            print(f"ABORT: {SITES[site][1]} site bytes unexpected: {cur.hex()} "
                  f"(want {orig.hex()})")
            return 1
        if cur_cave.strip(b"\x00") and cur_cave != code:
            print(f"ABORT: cave for {name} not zero/expected: {cur_cave.hex()}")
            return 1
        writes.append((s_off, redir, c_off, code, SITES[site][1], cur))

    print(f"  {done} site(s) already patched, {len(writes)} to patch")
    for _, redir, _, _, label, cur in writes:
        print(f"    {label:22} {cur.hex()} -> {redir.hex()}")
    if not writes:
        print("nothing to do - idempotent no-op"); return 0
    if not args.apply:
        print("dry run - re-run with --apply to write"); return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP); print(f"  backup -> {os.path.basename(BACKUP)}")
    for s_off, redir, c_off, code, label, _ in writes:
        data[c_off:c_off+len(code)] = code
        data[s_off:s_off+5] = redir
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        print("LOCKED - close AoW.exe / AoWCompat.exe / AoWDevEd.exe and retry"); return 1
    print(f"applied: {len(writes)} spell(s) now leave Chasm(0xB)/Sky(0xE) alone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
