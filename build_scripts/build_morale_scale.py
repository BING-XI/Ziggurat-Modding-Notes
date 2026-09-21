#!/usr/bin/env python
r"""
build_morale_scale.py -- put the morale modifiers back on the doubled stat scale.

BACKGROUND. The 5% conversion carried an explicit exception: "D2 MORALE is an explicit exception --
leave unchanged (becomes half as influential)". Every ATK/DEF/RES source around it doubled, so on
the new scale a morale swing bites half as hard as it used to, while the Ziggurat Manual still
prints the old numbers. User ruling 2026-08-26: reverse that exception and double them.

WHAT ZIGGURAT ACTUALLY MODIFIES (verified against AoWEPACK_original_backup.dpl, 2026-08-26) --
this is NOT the vanilla arrangement, and the difference matters:

  ATTACK  -- a Ziggurat ADDITION. Vanilla has no morale->ATK link at all. TUnit.GetAttack
             @0x557829EC is hooked out to a cave at 0x5580C0FC which reads morale from [ebx+0x26]
             and applies a five-band ladder, then clamps ATK to [0,40]. Bands (morale < 0x15 /
             0x29 / 0x3D / 0x51 / else) give -2 / -1 / 0 / +1 / +2.
             ⚠ BONUSES AT HIGH MORALE, not just penalties at low -- so this is NOT a "penalty
             table" and must not be re-tuned as though only the negative end mattered.
  RESIST  -- AoWE.MoraleResistanceModifier @0x558E83D8. Vanilla [-2,-1,0,0,0]; Ziggurat widened it
             to [-3,-2,-1,0,+1], again adding a bonus at the top. Read by TUnit.GetResistance
             @0x55782AF7 and THero.GetResistance @0x5578856D.
  DEFENCE -- AoWE.MoraleDefenseModifier @0x558E83E0, vanilla [-2,-1,0,0,0], zeroed to
             [0,0,0,0,0] on the user's ruling of 2026-08-27: morale is an ATTACK and
             RESISTANCE mechanic in Ziggurat and Defence is out of it. Three readers --
             TUnit.GetDefense @0x55782A6B, THero.GetDefense @0x55788449 and a cave
             @0x5580BFCE -- all go neutral together, because zeroing the table needs no code
             change at any of them. `--undo` puts the vanilla run back.
             (Until this row existed the table sat at vanilla while everything around it had
             doubled, so morale's Defence component was quietly half-strength rather than
             deliberately mild. It was never an intended tuning.)

SCOPE NOTE. Heroes take the ATK ladder through their own hook -- `build_morale_hero_atk.py`,
which caves off THero.GetAttack. This script owns the *values*; that one owns the hero *path*.
Re-tuning the ATK bands here changes units only, so keep the two in step by hand.

ENCODING NOTE. Two of the four ATK rungs have no immediate to double: `dec al` (FE C8) and
`inc al` (FE C0). They are re-encoded in place as `sub al,2` (2C 02) and `add al,2` (04 02) --
both two bytes, so the cave does not move and no jump displacement changes.

LADDER MODEL (as build_hero_clamps.py): each row lists every byte-run it has legitimately held,
oldest first, target last. Any ladder entry verifies; anything off-ladder ABORTS and writes
nothing. --undo writes ladder[0] everywhere.

USAGE
    python build_scripts/build_morale_scale.py            verify / dry run (writes nothing)
    python build_scripts/build_morale_scale.py --apply    write every row's target
    python build_scripts/build_morale_scale.py --undo     write every row's ladder[0]
"""
import os, sys, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-moralescale")
IMAGE_BASE = 0x55700000


def sbytes(vals):
    return bytes((v & 0xFF) for v in vals)


#      VA          ladder of byte-runs (oldest .. target)                      description
SITES = [
    # --- Resistance table: [-3,-2,-1,0,+1] -> [-6,-4,-2,0,+2]
    (0x558E83D8, (sbytes([-3, -2, -1, 0, 1]), sbytes([-6, -4, -2, 0, 2])),
     "MoraleResistanceModifier[5]"),

    # --- Attack ladder inside the GetAttack cave (Ziggurat addition; bonuses at the top)
    (0x5580C114, (b"\x04\x02", b"\x04\x04"), "morale->ATK  band 5 (>=81):  add al,+2 -> +4"),
    (0x5580C118, (b"\x2c\x02", b"\x2c\x04"), "morale->ATK  band 1 (<21):   sub al,2  -> 4"),
    (0x5580C11C, (b"\xfe\xc8", b"\x2c\x02"), "morale->ATK  band 2 (<41):   dec al    -> sub al,2"),
    (0x5580C120, (b"\xfe\xc0", b"\x04\x02"), "morale->ATK  band 4 (<81):   inc al    -> add al,2"),

    # --- Defence table: vanilla [-2,-1,0,0,0] -> [0,0,0,0,0]. User ruling 2026-08-27:
    #     morale is an ATTACK and RESISTANCE mechanic; Defence is out. Zeroing the table
    #     neutralises all THREE readers at once (TUnit.GetDefense @0x55782A6B,
    #     THero.GetDefense @0x55788449, cave @0x5580BFCE) with no code change, so there is
    #     no hook to keep in step and nothing to make position-independent.
    (0x558E83E0, (sbytes([-2, -1, 0, 0, 0]), sbytes([0, 0, 0, 0, 0])),
     "MoraleDefenseModifier[5]"),
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


def show(run):
    return run.hex(" ")


def main():
    ap = argparse.ArgumentParser(description="scale the morale ATK/RES ladders to the doubled scale")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())

    print("build_morale_scale -- morale ATK + RES ladders on the doubled scale\n")
    rows, bad, dirty = [], False, 0
    for va, ladder, name in SITES:
        n = len(ladder[0])
        assert all(len(x) == n for x in ladder), "%08X: ladder runs differ in length" % va
        off = va2off(d, va)
        if off is None:
            print("  %-44s %08X  <== NOT IN ANY SECTION" % (name, va)); bad = True; continue
        cur = bytes(d[off:off + n])
        target = ladder[-1]
        on_ladder = cur in ladder
        if cur != target:
            dirty += 1
        print("  %-44s %08X  %-16s %s%s"
              % (name, va, show(cur),
                 "AT TARGET" if cur == target else "-> %s" % show(target),
                 "" if on_ladder else "   <== OFF LADDER"))
        bad |= not on_ladder
        rows.append((off, ladder))

    if bad:
        sys.exit("\nABORT: a site holds bytes off its ladder. Nothing written.")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written; %d row(s) not at target)" % dirty)
        print("\nHeroes take the ATK ladder through build_morale_hero_atk.py, which caves off\n"
              "THero.GetAttack. Re-tuning the ATK bands HERE moves units only -- keep the two in\n"
              "step by hand. The DEF row zeroes one table read from three places at once.")
        return

    want = [(lad[0] if a.undo else lad[-1]) for _o, lad in rows]
    if all(bytes(d[off:off + len(v)]) == v for (off, _l), v in zip(rows, want)):
        print("\nalready there -- nothing to do (idempotent).")
        return

    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    for (off, _l), v in zip(rows, want):
        d[off:off + len(v)] = v
    open(TARGET, "wb").write(bytes(d))
    print("\n%s -- %d site(s) written."
          % ("UNDONE (ladder[0] everywhere)" if a.undo else "APPLIED (targets)", len(rows)))


if __name__ == "__main__":
    main()
