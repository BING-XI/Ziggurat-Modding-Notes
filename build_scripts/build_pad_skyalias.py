#!/usr/bin/env python3
r"""
AoW1 mod -- structures can stand on SKY: TPad reads Sky (0x0E) as Chasm (0x0B).

THE PROBLEM
  Placing any structure on a Sky hex silently converted the terrain -- to Grass
  in vanilla, and to Water in Ziggurat once PAD1 gained a Water entry.

  `AoWE.TStructureResource.Create @0x5576046C` sets `res[0x44] = 1` for every
  structure resource, so placement always runs through the pad:
      AoWE.TStructure.CanPlace @0x5575ECC8 -> TPadControl.CanPlacePad @0x5574B958
      AoWE.TStructure.PlaceHX  @0x5575ED10 -> TPadControl.PlacePad    @0x5574B9B0
  Both the pad and the structure then resolve their own terrain through
  `ILTer.TILTerrainMO.CanPlace` / `PlaceHX` (HSEPack 0x55618A04 / 0x55618B80),
  which call VMT[0x134] `GetValidTerrainType @0x55618780`:

      t = GetTerrainType(hex)
      if ValidTerrainType(t): return t                 <- VMT[0x128]
      f = ForceTerrainType(...)                        <- VMT[0x130]
      if ValidTerrainType(f): return f
      for t in 0 .. terraincount-1: if ValidTerrainType(t): return t   <- the scan
      return -1

  and `ValidTerrainType` (HSEPack 0x5561873C) is just "does an image sequence
  exist at VMT[0x12C] GetTerrainTypeImage(t)".  The base mapping
  (`ILTer.TILTerrainMO.GetTerrainTypeImage`, HSEPack 0x5561883C) is the identity
  -- literally `mov eax,edx / ret` -- so **a pad's image-sequence slot index IS
  the terrain id**.

  Pad slot lists are 13 long (indices 0..12).  Terrain 0x0E (ex-Coast, now SKY)
  is past the end and cannot be authored: AoWzEd's index list is driven by the
  stored count, so there is no row 14 to fill in.  Hence the scan, which finds
  slot 0 first and converts the hex to Water.

THE PATCH -- one 10-byte cave and one VMT slot
  `Pad.TPad`'s VMT is at 0x557FE6C8.  Slot +0x12C (GetTerrainTypeImage) holds
  0x5570353C, the HSEPack import thunk for the shared identity mapping.  Point
  that ONE slot at a cave that maps Sky to Chasm and is otherwise the identity:

      CAVE @0x55819100
        80 FA 0E    cmp dl, 0x0E     ; Sky
        75 02       jne +2
        B2 0B       mov dl, 0x0B     ; -> Chasm (ex-uWasteland)
        89 D0       mov eax, edx
        C3          ret

  Register-only, so position-independent as AoWEPACK.dpl requires.  The slot
  already carries a `.reloc` entry (it held an absolute in-module VA), and the
  new value is another in-module VA, so the relocation stays correct at load --
  verified before writing, and worth re-checking with build_relocfix.py --audit.

  Because ValidTerrainType routes through GetTerrainTypeImage, this one slot
  fixes validity AND drawing at once: a pad on Sky is legal, the hex keeps its
  terrain, and the pad draws whatever Chasm's slot 11 holds.

WHY ONLY THE PAD, NOT TStructure
  `AoWE.TStructure.GetTerrainTypeImage @0x5575E6A0` is left alone deliberately.
  The Teleporter has its own authored index-14 complex, so its sprite still comes
  from that; aliasing structure-side would throw that work away and would quietly
  hand Sky placement to every structure carrying Chasm art.  Structures without a
  slot 14 keep converting the hex exactly as before -- no behaviour spreads.

  Consequence worth knowing: CanPlace (= CanPlacePad) now succeeds on Sky for
  every structure, because every pad has a slot 11.  A structure with no slot 14
  then resolves its own terrain and converts the hex to its first valid terrain,
  as it already did.  The visible difference for those is Grass instead of Water.

PAIRS WITH
  build_pad_transparent.py, which blanks pad slot 11 (Chasm) so nothing is drawn
  under the structure.  Apply that too or Sky inherits the `Padu_wl` mound.

TARGET   <game>/Ziggurat/AoWEPACK.dpl   (the live package; never the vanilla root)

USAGE
  build_pad_skyalias.py           -- verify current state (default, no write)
  build_pad_skyalias.py --apply   -- write
  build_pad_skyalias.py --undo    -- restore the thunk and zero the cave
Close every AoW binary first -- they all lock the .dpl.
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: never beside the target
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
from pescan import PE                                                  # noqa: E402

TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-padskyalias")

TPAD_VMT = 0x557FE6C8
SLOT = TPAD_VMT + 0x12C          # GetTerrainTypeImage
ORIG_THUNK = 0x5570353C          # HSEPack import thunk, the identity mapping
CAVE_VA = 0x55819100             # free zero run; highest table entry is 0x55819000
CAVE_LIMIT = 0x40
SKY, CHASM = 0x0E, 0x0B


def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = (f"cmp dl, {SKY}; jne skip; mov dl, {CHASM}; skip: mov eax, edx; ret")
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE_VA)
    code = bytes(code)
    # keystone has bitten this project before (a `push imm8` silently encoding -1),
    # so assert the exact encoding rather than trusting the assembler.
    # keystone picks `89 d0` (MOV r/m32,r32) over the equally valid `8b c2`
    # (MOV r32,r/m32) -- same length, same effect; pinned so a keystone upgrade
    # that switches forms is caught rather than shipped.
    assert code == bytes.fromhex("80fa0e7502b20b89d0c3"), "unexpected encoding: " + code.hex()
    assert len(code) <= CAVE_LIMIT
    return code


def show(code, data, pe):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CAVE_VA):
        print(f"    {i.address:08X}  {i.mnemonic:<6} {i.op_str}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    args = ap.parse_args()

    pe = PE(TARGET)
    data = bytearray(pe.data)
    off = lambda va: pe.rva2off(va - pe.image_base)
    code = assemble()

    slot_off, cave_off = off(SLOT), off(CAVE_VA)
    cur = struct.unpack_from("<I", data, slot_off)[0]
    cave_now = bytes(data[cave_off:cave_off + len(code)])
    patched = cur == CAVE_VA
    print(f"TPad VMT {TPAD_VMT:#010x} slot +0x12C @ {SLOT:#010x} = {cur:#010x} "
          f"({'our cave' if patched else 'vanilla thunk' if cur == ORIG_THUNK else 'UNKNOWN'})")
    if cur not in (ORIG_THUNK, CAVE_VA):
        print(f"ABORT: slot holds {cur:#010x}, expected {ORIG_THUNK:#010x} or {CAVE_VA:#010x} "
              f"-- another patch owns this slot")
        return 1

    print(f"cave {CAVE_VA:#010x}:")
    show(code, data, pe)

    if args.undo:
        if not patched and cave_now != code:
            print("already reverted (no-op)")
            return 0
        new_slot, new_cave = ORIG_THUNK, bytes(len(code))
        what = "restore thunk, zero the cave"
    else:
        if patched and cave_now == code:
            print("already applied (idempotent no-op)")
            return 0
        if not patched:
            tail = bytes(data[cave_off:cave_off + CAVE_LIMIT])
            if tail != bytes(CAVE_LIMIT):
                print(f"ABORT: {CAVE_VA:#010x} is not a {CAVE_LIMIT}-byte zero run "
                      f"-- first bytes {tail[:16].hex()}")
                return 1
        new_slot, new_cave = CAVE_VA, code
        what = f"write {len(code)}-byte cave, repoint the VMT slot"

    print(f"  {what}")
    if not args.apply:
        print("dry run - re-run with --apply to write")
        return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print(f"  backup -> {os.path.basename(BACKUP)}")

    n = len(data)
    data[cave_off:cave_off + len(new_cave)] = new_cave
    struct.pack_into("<I", data, slot_off, new_slot)
    assert len(data) == n, "the .dpl changed length -- it must not"
    try:
        open(TARGET, "wb").write(bytes(data))
    except PermissionError:
        print("LOCKED - close every AoW binary and retry")
        return 1
    print(f"applied: slot {SLOT:#010x} = {new_slot:#010x}; "
          f"cave {CAVE_VA:#010x} = {new_cave.hex() or '(zeroed)'}")
    print("  now re-run build_relocfix.py --audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
