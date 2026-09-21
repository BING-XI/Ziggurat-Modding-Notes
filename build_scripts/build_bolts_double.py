#!/usr/bin/env python
r"""
build_bolts_double.py -- the DAM/HP + 5% passes missed the five bolt attacks. Double them.

WHAT WAS MISSED (user report 2026-08-27, confirmed by byte-diff against the pristine DLL).
Black, Holy, Frost, Lightning and Magic Bolts still carry vanilla-scale ATTACK and DAMAGE
while every other attack in the game doubled. All ten immediates are byte-identical to
`Modding Resources/AoWEPACK_original_backup.dpl`, so neither pass ever touched them.

⚠ WHY THEY WERE MISSED -- worth reading before assuming any other family is covered.
The DAM pass caught eleven ranged attacks under the family "Ranged ability damage
registrations (11)": Javelin, BlackJavelin, HurlStones, FireMusket, FireCannon, HurlBoulder,
VenomousSpit, CallFlames, Archery, PoisonDarts, DoomGaze. Those are `TRangedAttackAbility`,
built by the constructor at **0x5576ED48**, in one contiguous block of eleven call sites
spaced 0x3F apart, each with its damage as the FIRST `push imm8`.

The bolts are a different class -- `AoWE.TBoltsAbility` -- built by a *different*
constructor at **0x5576EDE8**, in a *separate* block spaced 0x39 apart that sits immediately
BEFORE the ranged block, and their attack does not arrive as a stack push at all: it comes
in **ECX**. A sweep keyed on "first push imm8 of a 0x5576ED48 call site" therefore cannot
see them, and a sweep for the pushed values finds only their damage-TYPE argument. Both
passes' manifests contain zero bolt entries.

FIELD IDENTIFICATION (do not guess -- the three pushed values are NOT atk/dam):
    AoWE.TRangedAttackAbility.GetDamageRA @0x5576E614  ->  mov bl, [eax+0x29]   DAMAGE
    AoWE.TRangedAttackAbility.GetAttackRA @0x5576E65C  ->  mov bl, [eax+0x2a]   ATTACK
    (GetRangeRA -> +0x28, GetAttackRepeatRA -> +0x2d, GetDamageTypesRA -> word +0x2b)
The ctor at 0x5576EDE8 writes `[ebp+0x10]` (the first push) to +0x29 and ECX to +0x2a. The
other two pushes are the damage-TYPE element fed through @SetElem into the word at +0x2b
(Black 5, Magic 3, Frost 1, Lightning 2, Holy 6) and a sound/effect index -- **doubling
either of those would change a bolt's damage type or its sound, not its strength.**

`Release/Ability.pfs` records 130-134 (= ability id + 10) carry ZERO tags, so nothing in the
data files overrides these; the code immediates are authoritative.

WHAT THIS SCRIPT WRITES -- ten immediates in AoWEPACK.dpl, x2, nothing else:

    bolt              ATTACK  mov ecx,imm32          DAMAGE  push imm8
    Black Bolts       0x5576F326   6 -> 12           0x5576F305   3 -> 6
    Magic Bolts       0x5576F35F   7 -> 14           0x5576F33E   3 -> 6
    Frost Bolts       0x5576F398   6 -> 12           0x5576F377   3 -> 6
    Lightning Bolts   0x5576F3D1   6 -> 12           0x5576F3B0   3 -> 6
    Holy Bolts        0x5576F40A   6 -> 12           0x5576F3E9   3 -> 6

Both destination fields are BYTES (+0x29, +0x2a), so every value must stay under 128 -- 14
is nowhere near the wall, but a future re-tune must respect it. The `mov ecx, imm32`
encoding is five bytes regardless of value and `push imm8` is two, so nothing moves and no
jump displacement changes. No addresses are involved, so position independence is not a
concern even though the .dpl rebases, and no displaced byte carries a .reloc entry.

⚠ LAYERING -- the DAMAGE ladders carry a THIRD value, 7. `build_ranged_damage.py` (user
ruling 2026-08-27) adds +1 to every ranged-family attack, so these five sites legitimately
read 7 once it is applied. Without 7 in the ladder this script ABORTS rather than writing --
which is the ladder model working, but it makes a routine verify run look like a failure.
**Undo order: revert build_ranged_damage.py FIRST, then this script.** Reverting this one
directly from 7 also works and lands on vanilla 3; it simply skips the intermediate step.

LADDER MODEL (as build_morale_scale.py): each site lists every value it has legitimately
held, oldest first, target last. Anything off-ladder ABORTS and writes nothing.
`--undo` writes ladder[0] -- the vanilla value -- everywhere.

USAGE
    python build_scripts/build_bolts_double.py            verify / dry run (writes nothing)
    python build_scripts/build_bolts_double.py --apply    double them
    python build_scripts/build_bolts_double.py --undo     restore the vanilla values
"""
import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-boltsdouble")
IMAGE_BASE = 0x55700000

# (imm VA, width, opcode VA, expected opcode byte, ladder, description)
#   width 1 = the imm8 of `push imm8` (6A xx)
#   width 4 = the imm32 of `mov ecx, imm32` (B9 xx xx xx xx)
SITES = [
    (0x5576F326, 4, 0x5576F325, 0xB9, (6, 12), "Black Bolts      ATTACK"),
    (0x5576F305, 1, 0x5576F304, 0x6A, (3, 6, 7), "Black Bolts      DAMAGE"),
    (0x5576F35F, 4, 0x5576F35E, 0xB9, (7, 14), "Magic Bolts      ATTACK"),
    (0x5576F33E, 1, 0x5576F33D, 0x6A, (3, 6, 7), "Magic Bolts      DAMAGE"),
    (0x5576F398, 4, 0x5576F397, 0xB9, (6, 12), "Frost Bolts      ATTACK"),
    (0x5576F377, 1, 0x5576F376, 0x6A, (3, 6, 7), "Frost Bolts      DAMAGE"),
    (0x5576F3D1, 4, 0x5576F3D0, 0xB9, (6, 12), "Lightning Bolts  ATTACK"),
    (0x5576F3B0, 1, 0x5576F3AF, 0x6A, (3, 6, 7), "Lightning Bolts  DAMAGE"),
    (0x5576F40A, 4, 0x5576F409, 0xB9, (6, 12), "Holy Bolts       ATTACK"),
    (0x5576F3E9, 1, 0x5576F3E8, 0x6A, (3, 6, 7), "Holy Bolts       DAMAGE"),
]

BYTE_FIELD_MAX = 127        # +0x29 / +0x2a are single bytes


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    sec, rva = e + 24 + opt, va - IMAGE_BASE
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
        sec += 40
    return None


def read(d, off, width):
    return d[off] if width == 1 else struct.unpack_from("<I", d, off)[0]


def write(d, off, width, val):
    if width == 1:
        d[off] = val
    else:
        struct.pack_into("<I", d, off, val)


def main():
    ap = argparse.ArgumentParser(description="double the five bolt attacks (AoWEPACK.dpl)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    print("build_bolts_double -- Black / Magic / Frost / Lightning / Holy Bolts ATK+DAM x2")
    print("target: %s\n" % TARGET)

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())
    pris = open(PRISTINE, "rb").read() if os.path.exists(PRISTINE) else None

    rows, bad, dirty = [], False, 0
    for imm_va, width, op_va, op_byte, ladder, name in SITES:
        io_, oo = va2off(d, imm_va), va2off(d, op_va)
        if io_ is None or oo is None:
            print("  %-24s %08X  <== NOT IN ANY SECTION" % (name, imm_va))
            bad = True
            continue
        if d[oo] != op_byte:
            print("  %-24s %08X  <== opcode at %08X is %02X, expected %02X"
                  % (name, imm_va, op_va, d[oo], op_byte))
            bad = True
            continue
        cur, target = read(d, io_, width), ladder[-1]
        on_ladder = cur in ladder
        if cur != target:
            dirty += 1
        note = ""
        if pris is not None:
            pv = read(pris, va2off(pris, imm_va), width)
            if pv != ladder[0]:
                note = "   <== pristine says %d, ladder[0] is %d" % (pv, ladder[0])
                bad = True
        if target > BYTE_FIELD_MAX:
            note += "   <== %d exceeds the byte field" % target
            bad = True
        print("  %-24s %08X  %-4d %s%s"
              % (name, imm_va, cur,
                 "AT TARGET" if cur == target else "-> %d" % target,
                 note if note else ("" if on_ladder else "   <== OFF LADDER")))
        bad |= not on_ladder
        rows.append((io_, width, ladder))

    if bad:
        sys.exit("\nABORT: a site failed its checks. Nothing written.")

    print("\n  %d of %d site(s) not at target\n" % (dirty, len(SITES)))

    if not (a.apply or a.undo):
        print("(dry run -- nothing written.  --apply to patch, --undo to revert)")
        return

    want = [(lad[0] if a.undo else lad[-1]) for _o, _w, lad in rows]
    if all(read(d, o, w) == v for (o, w, _l), v in zip(rows, want)):
        print("  already %s -- nothing to do." % ("at vanilla" if a.undo else "applied"))
        return

    kill_aow()
    if a.apply and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    for (o, w, _l), v in zip(rows, want):
        write(d, o, w, v)
    open(TARGET, "wb").write(bytes(d))
    print("  %s -- %d site(s) written." % ("UNDONE (vanilla)" if a.undo else "APPLIED (x2)",
                                           len(rows)))
    if a.apply:
        print("\n  NEEDS THE USER'S IN-GAME TEST -- nothing here is confirmed:")
        print("    1. a bolt-armed unit's card shows the doubled ATK/DAM")
        print("    2. the combat log prints the new ATK against the target's DEF")
        print("    3. bolts still deal their own damage TYPE (Black/Magic/Frost/Lightning/")
        print("       Holy) -- the type set lives beside these immediates and must be intact")
        print("    4. Shoot Bolt (id 0x39, a different class) is unchanged by this script")


if __name__ == "__main__":
    main()
