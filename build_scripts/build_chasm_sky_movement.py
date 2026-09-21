#!/usr/bin/env python3
r"""
AoW1 mod -- Chasm & Sky terrain, STEP 1: movement rows + Coast water-family filter.

Repurposes two unused terrain IDs (user ruling, they authored the installed Ziggurat mod:
never used by any map or spell):
    Chasm = terrain 0xB (ex-uWasteland, cave level)
    Sky   = terrain 0xE (ex-Coast, surface level)
Design doc: Modding Resources/Chasm_Sky_Terrain_Design.md
Table reference: Modding Resources/Movement_Tables_Terrain_Types.md

PATCH A -- movement rows (pure data, AoWEPACK.dpl .data)
  8 base ability tables (16x16 = terrain x overlay, cost = table[0x31 + t*16 + ov],
  0xFF = impassable) at 558E84FC..558E8BFC. Rows 0xB and 0xE are rewritten:
    - Fly/Float table (558E86FC): [None]=4, every overlay column 0xFF
    - all other 7 tables:        entire row 0xFF
  The startup generator (55744B2C) rebuilds MovePointTables (558EA040) from these, so
  every unit, the AI and the path preview follow automatically. Expected "before" bytes
  are the INSTALLED (Ziggurat) values -- both rows were live-configured (uWasteland fully
  walkable, Coast a water clone) though never used on maps.

PATCH B -- neutralize the Coast water special-case (2 bytes)
  TAoWHexagon.TerrainChanged (5579A94C) fires for new terrain in {0,6,0xE} and replaces
  the land hexagon with a TAoWWaterHexagon (the 0xE branch even substitutes terrain 0).
  Filter tail at 5579A95F: 80 EA 08 (sub dl,8) ; 75 78 (jne +0x78 -> ret path).
  Patch the JNE 75->EB (jmp): values other than 0/6 now ALWAYS skip -- 0xE stops being
  water-family. Water(0)/Ice(6) take their branch earlier and are untouched.
  NOTE: TAoWHexagon.ChangeTerrain (5579A89C) has a fallback that also water-replaces when
  GetRndResource(newTerrain) finds no land resource -- harmless until terrain 0xB/0xE
  actually appears on a map, which requires the resource-registration step (STEP 2) anyway.

In-game test after STEP 2 gives Chasm/Sky resources (or via any hex whose terrain byte is
poked to 0xB/0xE): walkers/ships refuse entry, flyers+floaters cross at 4 MP.

Idempotent (accepts old or new state per site), verify-before-write (aborts on unknown
bytes), auto-backup AoWEPACK.dpl.pre-chasmsky, dry-run by default -- pass --apply.
Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first (all lock the DLL).
Revert: NOT by snapshot -- a whole-file .pre-* restore wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09).
Surgically restore the sites below instead -- they are plain data + 2 code bytes, so this is easy.
Any snapshot this script mints goes to <game dir>\backups\.
"""
import shutil, sys, struct, os

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-chasmsky")
DLL_BASE = 0x55700000

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def va2off(secs, va):
    rva = va-DLL_BASE
    for vaddr,vsize,raw,rsize in secs:
        if vaddr <= rva < vaddr+max(vsize,rsize):
            return raw+(rva-vaddr)
    raise ValueError(f"VA {va:08X} not mapped")

# ⚠ TRAP, hit 2026-09-20: the backup below is minted by an `if not exists` guard that
# is NOT gated on the target being unpatched, so the v2 re-tune wrote a snapshot of the
# ALREADY-v1-PATCHED dll under the name `.pre-chasmsky`.  It was renamed by hand to
# `.pre-chasmskymovement-v2`, which is what it actually is.  A genuine pre-chasm-sky
# AoWEPACK.dpl no longer exists anywhere; the revert path is this script's own
# verify-against-either logic, not the snapshot.  See CLAUDE.md, "A snapshot must be
# minted on --apply ONLY".
TABLES = [0x558E84FC, 0x558E85FC, 0x558E86FC, 0x558E87FC,
          0x558E88FC, 0x558E89FC, 0x558E8AFC, 0x558E8BFC]
FLY = 0x558E86FC
CHASM, SKY = 0xB, 0xE
BLOCK_ROW = b"\xff"*16
FLY_ROW   = b"\x04" + b"\xff"*15           # v1: [None]=4 MP, all overlay combos blocked

# ---------------------------------------------------------------- v2, 2026-09-20
# v1's rows made a Chasm/Sky hex carrying ANY overlay impassable to everything --
# including flyers, and including overlay 7 Structure.  Since `TStructure.GetOverlay
# @0x5575EBF0` returns 7, a teleporter standing on Chasm or Sky could not be reached
# at all, and a razed one (overlay 6 Rubble) left a permanent hole.  v2:
#   Fly/Float  -- the WHOLE row is 4: flyers cross a Chasm/Sky hex whatever is on it.
#   Bridge column (overlay 5 -> index 6) = 3 in the five walking-family tables, so a
#     bridge spanning a chasm is actually crossable.  This mirrors what vanilla's
#     Coast row (0xE) carried before this feature appropriated it, and what the live
#     Water / Lava / CaveWater / CaveIce rows carry today.
#   Swim (1) and Tunnel (7) stay fully blocked -- ships do not sail a void and
#     tunnellers do not burrow through one.
# ⚠ The bridge cells are inert until a bridge RESOURCE exists for terrain 0xB/0xE
# (one resource serves exactly one terrain) -- see build_hss_addresource.py.
FLY_ROW_V2   = b"\x04"*16
BRIDGE_TABLES = (0, 3, 4, 5, 6)            # Walking, Forestry, CaveCrawl, Mountaineer, FireImm


def new_row(ti):
    """The v2 row for table index `ti`."""
    if TABLES[ti] == FLY:
        return FLY_ROW_V2
    if ti in BRIDGE_TABLES:
        r = bytearray(BLOCK_ROW); r[6] = 3          # column 6 == overlay 5 == Bridge
        return bytes(r)
    return BLOCK_ROW


# What v1 left installed.  Accepted as a "from" state alongside EXPECT so this is an
# in-place re-tune, never a revert-and-reapply (project rule, see CLAUDE.md).
def prev_row(ti):
    return FLY_ROW if TABLES[ti] == FLY else BLOCK_ROW

# expected installed (Ziggurat) bytes, captured 2026-07-24 from the live DLL
EXPECT = {
 (0x558E84FC,CHASM): "04ffffff0403ff0603ff04ff0cffffff",
 (0x558E85FC,CHASM): "ffffffffffffffffffffffff08ffffff",
 (0x558E86FC,CHASM): "05ff05ff0505ff05050505ff0505ffff",
 (0x558E87FC,CHASM): "04ffffff0403ff0603ff04ff0cffffff",
 (0x558E88FC,CHASM): "03ff05050303ff0403ff03ff08ffffff",
 (0x558E89FC,CHASM): "ff06ffffffffffffffffffffffffffff",
 (0x558E8AFC,CHASM): "ffffffffffffffffffffffffffffffff",
 (0x558E8BFC,CHASM): "08ff0c0c0403ff0403ff04ff0cffffff",
 (0x558E84FC,SKY):   "ffffffffffff03ffffffffffffffffff",
 (0x558E85FC,SKY):   "03ffffff03ffff0303ff03ffffffffff",
 (0x558E86FC,SKY):   "04ffffff04ff0404040404ff0404ffff",
 (0x558E87FC,SKY):   "ffffffffffff03ffffffffffffffffff",
 (0x558E88FC,SKY):   "ffffffffffff03ffffffffffffffffff",
 (0x558E89FC,SKY):   "ffffffffffffffffffffffffffffffff",
 (0x558E8AFC,SKY):   "ffffffffffffffffffffffffffffffff",
 (0x558E8BFC,SKY):   "ffffffffffff03ffffffffffffffffff",
}

# PATCH B site
FILTER_SITE = 0x5579A962           # jne 0x5579a9dc  (after sub dl,8)
FILTER_ORIG = bytes.fromhex("7578")
FILTER_NEW  = bytes.fromhex("eb78")
FILTER_PFX_SITE = 0x5579A95F       # sanity anchor: sub dl,8 must precede
FILTER_PFX  = bytes.fromhex("80ea08")

def main():
    apply = "--apply" in sys.argv
    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)

    patches = []   # (va, accepted "from" states, new, label)
    for ti, va in enumerate(TABLES):
        for t in (CHASM, SKY):
            row_va = va + t*16
            froms = (bytes.fromhex(EXPECT[(va, t)]), prev_row(ti))
            patches.append((row_va, froms, new_row(ti),
                            f"{'fly' if va==FLY else 'tab'}{ti} row {t:#x}"))
    patches.append((FILTER_SITE, (FILTER_ORIG,), FILTER_NEW, "TerrainChanged 0xE filter"))

    # sanity anchor for patch B
    pfx = bytes(data[va2off(secs, FILTER_PFX_SITE):va2off(secs, FILTER_PFX_SITE)+3])
    if pfx != FILTER_PFX:
        print(f"ABORT: filter anchor mismatch at {FILTER_PFX_SITE:08X}: {pfx.hex()}"); return 1

    todo, done = [], 0
    for va, froms, new, label in patches:
        off = va2off(secs, va)
        cur = bytes(data[off:off+len(new)])
        if cur == new:
            done += 1
        elif cur in froms:
            todo.append((off, new, label, cur))
        else:
            print(f"ABORT: {label} @ {va:08X} has unexpected bytes:\n  cur  {cur.hex()}\n"
                  + "".join(f"  from {f.hex()}\n" for f in froms))
            return 1

    print(f"{done} site(s) already patched, {len(todo)} to patch.")
    for off, new, label, cur in todo:
        print(f"  {label}: {cur.hex()} -> {new.hex()}")
    if not todo:
        print("Nothing to do -- state verified."); return 0
    if not apply:
        print("Dry run only. Re-run with --apply to write."); return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print(f"Backup -> {os.path.basename(BACKUP)}")
    for off, new, label, cur in todo:
        data[off:off+len(new)] = new
    open(DLL, "wb").write(data)
    print(f"Applied {len(todo)} patch site(s). Close/reopen the game to take effect.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
