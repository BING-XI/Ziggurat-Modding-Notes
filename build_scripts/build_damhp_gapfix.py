#!/usr/bin/env python
r"""
build_damhp_gapfix.py -- the DAMAGE immediates the DAM/HP pass never enumerated.

Found 2026-08-26 by a defect-class sweep prompted by the mod author asking whether the Burning
damage roll had been doubled. It had not. The defect class is:

    a paired (POWER, DAMAGE) site where the POWER fell inside the 5% conversion's scope and was
    caught, while the DAMAGE 10-20 bytes later fell inside the DAM/HP pass's scope and was never
    enumerated -- so NEITHER manifest contains it and BOTH scripts report a clean all-clear.

`build_damhpdouble.py` reports 85/85 stage-3 sites at target; that is true and useless, because
these addresses are not in its manifest. `Zig notes/DamHP_Double_Decisions.md` additionally CLAIMED
stage 3 covered "Burning/Decay ticks" -- it did not, and that false line is corrected at source.

NOT OWNED HERE, deliberately:
  * Strategic map fire (power 6->12 @0x5580DB07, damage 3->6 @0x5580DB02) lives inside
    build_firefeed.py's cave C. Both passes wrote their doubled values into the DEAD original body
    at 0x55790218/0x5579021D, which `jmp 0x5580DAD0` @0x5579020C skips entirely. The fix belongs in
    that script's caveC_src or its next --apply silently reverts it.
  * AoWTCPCK.dpl TCDamage[0]/[1] -- that module never received the DAM/HP pass at all and is being
    swept separately.
  * The morale ladders -- build_morale_scale.py (a fresh user decision, not a missed doubling).

LADDER MODEL (same as build_hero_clamps.py): each row lists every value it has legitimately held,
oldest first, target last. Any ladder value verifies; anything off-ladder ABORTS and writes nothing.
--undo writes ladder[0] everywhere.

USAGE
    python build_scripts/build_damhp_gapfix.py            verify / dry run (writes nothing)
    python build_scripts/build_damhp_gapfix.py --apply    write every row's target
    python build_scripts/build_damhp_gapfix.py --undo     write every row's ladder[0]
"""
import os, sys, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-damhpgapfix")
IMAGE_BASE = 0x55700000

# va, width, expected preceding opcode bytes, ladder (oldest..target), description
SITES = [
    # --- Burning: POWER @0x557BA464 was doubled 10->20 by fivepct; this is its DAMAGE twin.
    #     vanilla 1, Ziggurat 2. `mov edx, imm32` (BA) then call [ecx+0x124] ExecuteDamage.
    (0x557BA475, 4, b"\xBA", (2, 4), "Burning tick damage (per combat turn)"),

    # --- Decay: purest instance -- no HitRole on this path at all, so no POWER half existed to
    #     drag it into either manifest. vanilla 1, never touched by anyone.
    #     (Mind Decay's spell ATTACK @0x557F8581 WAS doubled 6->12 while this, its entire damage
    #     output, was not.)
    (0x557BA772, 4, b"\xBA", (1, 2), "Decay tick damage (per combat turn)"),

    # --- Turn Undead, AI-only. Real damage flows through build_turnundead_res.py's caves
    #     (0x5580E2A0 / 0x5580E300) which DO carry the x2. The one surviving live caller of this
    #     function is the AI heuristic GetOffensiveStrength @0x5576AEDA, so the effect of leaving
    #     it is that the AI UNDER-VALUES Turn Undead.
    #     Smoking gun: damhp doubled that heuristic's CEILING 5->10 (@0x5576AEE6/0x5576AEEA) but
    #     never doubled the value being clamped. Fix the input, not the ceiling.
    (0x5576B223, 1, b"\xB0", (4, 8), "TurnUndead AI damage, level 1"),
    (0x5576B226, 1, b"\xB0", (8, 16), "TurnUndead AI damage, level 2"),
    (0x5576B229, 1, b"\xB0", (12, 24), "TurnUndead AI damage, level 3"),
    (0x5576B22C, 1, b"\xB0", (16, 32), "TurnUndead AI damage, level 4"),
]


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


def read(d, off, w):
    return int.from_bytes(d[off:off + w], "little", signed=False)


def main():
    ap = argparse.ArgumentParser(description="damage immediates both doubling passes missed")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())

    print("build_damhp_gapfix -- %d damage immediates missed by BOTH passes\n" % len(SITES))
    rows, bad, dirty = [], False, 0
    for va, w, opc, ladder, name in SITES:
        off = va2off(d, va)
        if off is None:
            print("  %-40s %08X  <== NOT IN ANY SECTION" % (name, va)); bad = True; continue
        cur = read(d, off, w)
        ins = bytes(d[off - len(opc):off])
        shape_ok = ins == opc
        on_ladder = cur in ladder
        target = ladder[-1]
        if cur != target:
            dirty += 1
        print("  %-40s %08X = %-3d  ladder %-9s %s%s"
              % (name, va, cur, "/".join(map(str, ladder)),
                 "AT TARGET" if cur == target else "-> %d" % target,
                 "" if (shape_ok and on_ladder) else "   <== UNEXPECTED SHAPE OR VALUE"))
        bad |= not (shape_ok and on_ladder)
        rows.append((off, w, ladder))

    if bad:
        sys.exit("\nABORT: a site is off its ladder or its instruction shape moved. Nothing written.")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written; %d row(s) not at target)" % dirty)
        print("\nNOT covered here -- see the docstring: strategic map fire (build_firefeed.py's\n"
              "cave C), AoWTCPCK.dpl TCDamage, and the morale ladders (build_morale_scale.py).")
        return

    want = [(lad[0] if a.undo else lad[-1]) for _o, _w, lad in rows]
    if all(read(d, off, w) == v for (off, w, _l), v in zip(rows, want)):
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


if __name__ == "__main__":
    main()
