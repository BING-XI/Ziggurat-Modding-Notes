#!/usr/bin/env python
r"""
build_tcpck_damhp.py -- the DAM/HP pass for AoWTCPCK.dpl (manual tactical combat).

WHY THIS EXISTS. `build_damhpdouble.py` never wrote a single byte to AoWTCPCK.dpl: all 145 of its
manifest entries are module "AoWEPACK.dpl". The 5% conversion DID write here (exactly 4 bytes), so
the module was left half-converted -- every ATK/DEF value on the new scale, every DAMAGE and HP
value on the old one. Whole-file diff live vs .pre-statdouble is those 4 bytes and nothing else:
  0x004ED8 FE->FC, 0x00FD3F FE->FC, 0x0661A4 06->0C, 0x0661A8 0A->14.
Found 2026-08-26; user approved a full sweep of the module.

THE VISIBLE SYMPTOM (now resolved -- kept because it explains the numbers). The game holds THREE
independent wall-HP representations, and the DAM/HP pass doubled two while missing this module's:

    representation                            vanilla   was      NOW
    TWallUnit.SetWallType   (predictor)        10 / 5   20 / 10  40 / 10
    TCombatWall.GetHits     (auto-resolve)     10 / 5   48 / 16  40 / 10
    AoWTC.WallMaxHP         (manual tactical)    --     13 / 7   40 / 10   <-- this module

A stone wall had 13 HP in the fight you played by hand, 20 in the predictor that forecast it, and 48
if you auto-resolved the same siege -- against damage that had doubled everywhere. TCityWall's own
GetDefense had already been doubled -2 -> -4 by fivepct, so the same object's Defence was on the new
scale while its HP pool was not.

⚠ USER RULING 2026-08-26: all three are now UNIFIED at 40 stone / 10 wood. That is a BALANCE
decision, not a x2 of anything -- do not "restore" it to a doubling of vanilla or of Ziggurat.
The AoWEPACK halves are owned by damhp_manifest (0x55725C37/0x55725C3A auto-resolve,
0x5578362D/0x55783633 predictor; 0x5578362D also appears in fivepct and both were retargeted so the
two manifests agree). Only the AoWTC.WallMaxHP pair below is owned by THIS script.
⚠ Both AoWEPACK halves store wall HP in a BYTE ([TCombatWall+0x4D], [TWallUnit+0x3E]) read with
movsx -- 40 is safely under the 127 signed wall, but do not raise this above 127.

⚠⚠ SINGLE-APPLY CONGRUENCE GROUP. The damages and the HP pools they eat MUST land together.
Doubling only the damages makes walls and structures crumble twice as fast; doubling only the HP
makes manual Wall Crushing and fire half as effective (a 1-damage fire hex would need 26 turns to
burn a stone wall). Doubling all of them is behaviourally IDENTICAL. Never stage this across two
patches.

⚠ MANIFEST WIDTH DEFECTS -- do NOT inherit them. fivepct_manifest.json records "WallMaxHP[0..1]" as
ONE entry at 0x004675F8 with "width": 1. They are TWO separate int32 words (0x004675F8 = 7 wooden,
0x004675FC = 13 stone); a width-1 write leaves stone walls at vanilla HP. It records TCDamage[0]
with width 1 too -- also int32. Everything here is int32.
⚠ Its "NO-DOUBLE"/"UNCHANGED" rulings on 0x004675F8 and on the terrain HP are the STAT pass
correctly saying "not an ATK/DEF/RES value". They are NOT a DAM/HP adjudication and must not be
read as a rejection.

⚠ PATCH THE ARRAY VALUES, NEVER THE POINTER SLOTS. The Delphi package reaches these tables through
IMPORTEDDATA indirection (`mov edx,[<slot>]; mov edx,[edx+idx*4]`). The slots 0x004693C4 (TCAttack),
0x004693FC (TCDamage), 0x004693D0 (WallMaxHP), 0x00469408 (WallISIndex) ARE in .reloc; the array
values are not. This script asserts that every address it writes is absent from .reloc.
⚠ ADJACENCY TRAPS on every side of these tables -- WallISIndex[0..1] @0x004675F0 (image-sequence
base indices, and ImageLib.Get has NO bounds check), clusterChk @0x00467600, StatusAbils @0x004675B8
(ability ids up to 163), raDir @0x004671B4 (direction codes). A scan that overruns an 8-byte extent
lands in one of them. This script uses explicit addresses only, never a range.
⚠ A literal-address xref scan finds NOTHING for the real consumers (the indirection above), so
"no xrefs" is never proof a table is dead here.

NOT TOUCHED, deliberately:
  * TCAttack[0]/[1] @0x004671A4/A8 -- ALREADY doubled by fivepct (6->12, 10->20). Asserted below;
    doubling again would quadruple them.
  * Ranged Wall Crushing (msg 0x31003) -- takes all its numbers from AoWEPACK ability data, already
    doubled. Nothing here to patch; it is a regression check, not a target.
  * MakeHitBlood band 3 -- see the note beside SITES. Briefly widened to 0x7F on 2026-08-26 and
    REVERTED the same day on the author's ruling; the ladder keeps 0x7F so the state verifies.

NO SIGNED-BYTE-127 HAZARD IN THIS MODULE. Every HP path is 32-bit end to end (WallMaxHP is an int32
array read as dwords; terrain HP is `C7 /0 imm32`; the structure sites are `mov edx, imm32`), and
there is no upper clamp on wall, structure or terrain HP anywhere. The 127 wall lives on the
AoWEPACK side and is already handled there.

USAGE
    python build_scripts/build_tcpck_damhp.py            verify / dry run (writes nothing)
    python build_scripts/build_tcpck_damhp.py --apply    write every row's target
    python build_scripts/build_tcpck_damhp.py --undo     write every row's ladder[0]
"""
import os, sys, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWTCPCK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-tcpckdamhp")
IMAGE_BASE = 0x400000

# Sites already on the new scale -- refuse to run if these are not as expected, because doubling
# the damage half while the attack half is stale would be worse than doing nothing.
PRECONDITION = [(0x004671A4, 4, 12, "TCAttack[0] (fivepct 6->12)"),
                (0x004671A8, 4, 20, "TCAttack[1] (fivepct 10->20)")]

#      VA          width  ladder (oldest..target)  description
SITES = [
    (0x004671AC, 4, (6, 12), "TCDamage[0]   melee Wall Crushing vs a wall"),
    (0x004671B0, 4, (1, 2), "TCDamage[1]   burning fire hex, per combat turn"),
    (0x004675F8, 4, (7, 14, 10), "WallMaxHP[0]  wooden wall AND every city door -- unified 10"),
    (0x004675FC, 4, (13, 26, 40), "WallMaxHP[1]  stone wall -- unified 40"),
    (0x0041092B, 4, (3, 6), "TCombatTerrain HP (inert -- see note)"),
    (0x00432849, 4, (5, 10), "TCombatStructure HP 1/3 (Create)"),
    (0x0043290E, 4, (5, 10), "TCombatStructure HP 2/3 (Activate, governs play)"),
    (0x0043291D, 4, (5, 10), "TCombatStructure HP 3/3 (Activate, editor preview)"),
    (0x0040996C, 1, (3, 6), "MakeHitBlood band 1 width (small splat)"),
    (0x00409971, 1, (4, 8), "MakeHitBlood band 2 width (medium splat)"),
    (0x00409976, 1, (0x5D, 0x7F, 0x5D), "MakeHitBlood band 3 width -- REVERTED to 0x5D, see note"),
]

# MakeHitBlood @0x00409966 is a Delphi range-case on the DAMAGE value:
#     dec eax                       ; 0-based
#     sub eax,6  / jb -> [XYZ+0xc]=1    small   (damage 1..6,   was 1..3)
#     sub eax,8  / jb -> [XYZ+0xc]=2    medium  (damage 7..14,  was 4..7)
#     sub eax,5D / jb -> [XYZ+0xc]=3    large   (damage 15..107, unchanged)
#     call 0x437FA0                 ; the Ziggurat blood-type cave
# The three immediates are band WIDTHS, not boundaries. The tier lands in [XYZ+0xc] of the aowFX
# TXYZList entry just added, and the Ziggurat cave then ADDS a per-blood-type offset to it
# (+5 / +0x2E / +0x20), so the final sprite index is tier + offset. If no band matched, the tier
# would stay 0 and the cave would yield sprite offset+0 -- a WRONG sprite, not "no blood".
#
# BAND 3 IS DELIBERATELY LEFT AT 0x5D (author's ruling 2026-08-26). It was briefly raised to 0x7F on
# the theory that the raised `Invalid Damage Value` assert ceiling (127) made damage 108..126
# reachable; it does not. A single hit's damage is bounded by the DAM stat (unit ceiling 60), so
# 15..107 already covers every attainable value -- the 127 assert is a safety margin, not a damage
# a unit can deal. The 0x7F rung stays in the ladder so that state still verifies.
# ⚠ Band 3 could not be DOUBLED in any case: 0x5D*2 = 0xBA does not fit the signed imm8 of
# `83 E8 ib` -- writing it assembles as `sub eax,-70` and SILENTLY INVERTS the range test. A true
# doubling needs `2D imm32` (5 bytes where there are 3), displacing two instructions and the
# `72 1a` / `eb 22` short jumps. Do not retry that without re-encoding the whole chain.

# TCombatTerrain HP is INERT: TCombatTerrain.SetHitPoints @0x00410138 is an 0x18-byte stub that
# DISCARDS its edx argument (it only sets the sound-played flag at [eax+0x1c]), so terrain HP is
# written once in Activate and never decremented. It is included purely because its DEFENCE sibling
# four instructions later (`mov dword [eax+0x20],-2` @0x0041093C) WAS doubled by fivepct, and
# leaving one half of a two-field initialiser behind is the exact asymmetry this sweep removes.


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    out, sec = [], pe + 24 + opt
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        out.append((vaddr, raw, max(vsize, rsize)))
        sec += 40
    return pe, opt, out


def va2off(d, va):
    _pe, _o, secs = sections(d)
    rva = va - IMAGE_BASE
    for vaddr, raw, size in secs:
        if vaddr <= rva < vaddr + size:
            return raw + (rva - vaddr)
    return None


def reloc_rvas(d):
    """Every RVA carrying a base relocation -- the pointer slots we must never write."""
    pe, opt, secs = sections(d)
    dd = pe + 24 + 96          # PE32 optional header: data directory starts at +96
    rva, size = struct.unpack_from("<II", d, dd + 5 * 8)   # entry 5 = BASERELOC
    if not rva or not size:
        return set()
    out, off = set(), None
    for vaddr, raw, sz in secs:
        if vaddr <= rva < vaddr + sz:
            off = raw + (rva - vaddr)
    if off is None:
        return set()
    end = off + size
    while off < end - 8:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for i in range((blk - 8) // 2):
            e = struct.unpack_from("<H", d, off + 8 + i * 2)[0]
            if (e >> 12) != 0:
                out.add(page + (e & 0xFFF))
        off += blk
    return out


def main():
    ap = argparse.ArgumentParser(description="DAM/HP pass for AoWTCPCK.dpl (manual tactical combat)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())
    relocs = reloc_rvas(d)

    print("build_tcpck_damhp -- DAM/HP pass for AoWTCPCK.dpl (%d sites)\n" % len(SITES))

    for va, w, want, name in PRECONDITION:
        off = va2off(d, va)
        cur = int.from_bytes(d[off:off + w], "little")
        if cur != want:
            sys.exit("ABORT: precondition failed -- %s @%08X is %d, expected %d.\n"
                     "The 5%% conversion must be applied to this module first; doubling the damage\n"
                     "half against a stale attack half would be worse than doing nothing." % (name, va, cur, want))
        print("  precondition OK   %08X = %-3d  %s" % (va, cur, name))
    print()

    rows, bad, dirty = [], False, 0
    for va, w, ladder, name in SITES:
        off = va2off(d, va)
        if off is None:
            print("  %-52s %08X  <== NOT IN ANY SECTION" % (name, va)); bad = True; continue
        if (va - IMAGE_BASE) in relocs:
            print("  %-52s %08X  <== IN .reloc -- THIS IS A POINTER SLOT, REFUSING" % (name, va))
            bad = True; continue
        cur = int.from_bytes(d[off:off + w], "little")
        target = ladder[-1]
        on_ladder = cur in ladder
        if cur != target:
            dirty += 1
        print("  %-52s %08X = %-3d ladder %-8s %s%s"
              % (name, va, cur, "/".join(map(str, ladder)),
                 "AT TARGET" if cur == target else "-> %d" % target,
                 "" if on_ladder else "   <== OFF LADDER"))
        bad |= not on_ladder
        rows.append((off, w, ladder))

    if bad:
        sys.exit("\nABORT: a site is off its ladder, missing, or relocated. Nothing written.")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written; %d row(s) not at target)" % dirty)
        print("\nThis is a SINGLE-APPLY CONGRUENCE GROUP: the damages and the HP pools they eat must\n"
              "land together, or walls/structures crumble at half or double the intended rate.")
        return

    want = [(lad[0] if a.undo else lad[-1]) for _o, _w, lad in rows]
    if all(int.from_bytes(d[off:off + w], "little") == v for (off, w, _l), v in zip(rows, want)):
        print("\nalready there -- nothing to do (idempotent).")
        return

    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    for (off, w, _l), v in zip(rows, want):
        assert 0 <= v < (1 << (8 * w)), "value %d does not fit %d byte(s)" % (v, w)
        d[off:off + w] = int(v).to_bytes(w, "little")
    open(TARGET, "wb").write(bytes(d))
    print("\n%s -- %d immediates written."
          % ("UNDONE (ladder[0] everywhere)" if a.undo else "APPLIED (targets)", len(rows)))
    print("\nAoW.exe / AoWCompat.exe are NOT affected -- this module is loaded by both, and both\n"
          "peers in a multiplayer game must carry the identical patch (standing no-mixed-mod rule).")


if __name__ == "__main__":
    main()
