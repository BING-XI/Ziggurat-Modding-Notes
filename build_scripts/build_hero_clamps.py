#!/usr/bin/env python
r"""
build_hero_clamps.py -- owns every bound (ceiling AND floor) in THero.GetAttack / GetDefense /
GetResistance / GetDamage / GetHits, plus the HITS purchase cap in THero.SetUnitHits.

HISTORY
  2026-08-20  ATK/DEF/RES/DAM ceilings 30 -> 40 (closing the 5% conversion's D4 contradiction).
  2026-08-24  DAM/HP congruence pass (Zig notes/DamHP_Double_Decisions.md): DAM ceiling 40 -> 60
              (decision H4), GetHits ceiling 80 -> 120 (H5: signed-byte wall at 127, 120 chosen),
              GetDamage and GetHits floors 1 -> 2 (identity), and the script was rebuilt on a
              LADDER model so historical states verify and --undo returns to the pre-script state.
  2026-08-31  HP ceiling 120 -> 100 (user ruling: reclaim margin under the 127 signed-byte wall,
              which every HP note keeps flagging). BOTH halves of the HITS Set == Get pair move
              together: the GetHits ceiling ladder gains 100, and **this script now also owns the
              purchase cap THero.SetUnitHits (cmp @0x557878BC, mov @0x557878C0)**.
              ⚠ WHY OWNERSHIP MOVED, and why the 2026-08-26 note above says not to claim such pairs
              here: the damhp_manifest route CANNOT express a re-target. `entry_state` in
              build_damhpdouble.py is strictly two-state (byte == `live` or byte == `newValue`);
              changing a `newValue` while the byte holds the OLD newValue makes the entry read
              FOREIGN and aborts the whole stage, so `--repair` can never reach it. A ladder can.
              The manifest's two entries were re-pointed to 100 so damhpdouble still verifies clean
              and its `--undo` still writes the true pre-state 80 (same as this ladder's [0]).
              Vanilla is 30/30 here (pristine DLL); `.pre-heroclamps` holds 80/80 -- both ladder
              rows therefore start at 80, so --undo remains byte-identical to that backup.
              ⚠ Do NOT re-tune the GetHits ceiling without the SetUnitHits cap: a crossed pair lets
              a hero spend skill points on HP the getter then clamps away -- points silently eaten.
  2026-08-26  DAM ceiling 60 -> 40 (user ruling), restoring vanilla's Set == Get invariant: the
              purchase cap THero.SetUnitDamage is 40, so a 60 ceiling meant 20 points reachable
              only through items/abilities. Byte-checked against the pristine DLL: vanilla is
              Set == Get for ALL five pairs (ATK/DEF/DAM/RES 10/10, HITS 30/30). The ATK half of
              the same ruling (purchase cap 60 -> 40) is NOT owned here -- its two immediates live
              in fivepct_manifest (cmp @0x557877D8) and damhp_manifest (mov @0x557877DC); they were
              re-targeted there and written with the new --repair flag. Do not claim them here.
              ⚠ CONSEQUENCE, recorded deliberately: TUnit.GetDamage ceiling is 60, so heroes now
              cap BELOW units on damage. Vanilla had both at 10. Raise this ladder's target back to
              60 if that is unwanted.

⚠ EVERY BOUND IS A PAIR OF IMMEDIATES. The test and the value written when it trips are separate
instructions, both carrying the bound. Patching one half gives silent discontinuities (31..40 pass,
41+ snaps back -- the bug class found live in the conversion's stage-1 unit clamps).

⚠ TWO ENCODING SHAPES. ATK/DEF/RES/DAM use `cmp ax,imm8` (66 83 F8) + `mov byte [esp],imm8`
(C6 04 24). GetHits uses `cmp dx,imm8` (66 83 FA) + `mov al,imm8` (B0). The shape is checked
per row -- a mismatch means the site moved and NOTHING is written.

LADDER MODEL. Each row lists every value it has legitimately held, oldest first; the target is the
last. Any mix of ladder values verifies (half-applied states are repaired by writing the target);
any byte off the ladder aborts. --undo writes ladder[0] everywhere = the true pre-script state,
byte-identical to AoWEPACK.dpl.pre-heroclamps.

The DAMAGE ceiling and both floors move as part of the DAM/HP doubling session -- do not re-tune
them in isolation or hero damage output and the rest of the game disagree.

USAGE
    python build_hero_clamps.py            verify / dry run (writes nothing)
    python build_hero_clamps.py --apply    write every row's target
    python build_hero_clamps.py --undo     write every row's ladder[0]
"""
import os, sys, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-heroclamps")
IMAGE_BASE = 0x55700000

AX_ESP = (b"\x66\x83\xf8", b"\xc6\x04\x24")     # cmp ax,imm8  /  mov byte [esp],imm8
DX_AL = (b"\x66\x83\xfa", b"\xb0")              # cmp dx,imm8  /  mov al,imm8
EDX_BL = (b"\x83\xfa", b"\xb3")                  # cmp edx,imm8 /  mov bl,imm8   (SetUnitHits)

#        cmp imm     mov imm     shape   ladder (oldest..target)   name
SITES = [
    (0x557883CB, 0x557883D1, AX_ESP, (30, 40),     "GetAttack     ceiling"),
    (0x55788465, 0x5578846B, AX_ESP, (30, 40),     "GetDefense    ceiling"),
    (0x55788589, 0x5578858F, AX_ESP, (30, 40),     "GetResistance ceiling"),
    (0x557884EF, 0x557884F5, AX_ESP, (30, 40, 60, 40), "GetDamage     ceiling"),
    (0x557884E1, 0x557884E7, AX_ESP, (1, 2),       "GetDamage     floor"),
    (0x557885B8, 0x557885BC, DX_AL,  (80, 120, 100), "GetHits       ceiling"),
    (0x557885AD, 0x557885B1, DX_AL,  (1, 2),       "GetHits       floor"),
    (0x557878BC, 0x557878C0, EDX_BL, (80, 120, 100), "SetUnitHits   cap (purchase)"),
]
# never written, shown for context: GetMoves has its own separate pair and movement never scales
GETMOVES = (0x557885DC, 0x557885E0)


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


def main():
    ap = argparse.ArgumentParser(description="THero stat/damage/hits bounds (ladder model)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())

    print("build_hero_clamps -- %d THero bounds (ladder model)\n" % len(SITES))
    rows, bad, dirty = [], False, 0
    for cva, mva, (cpre, mpre), ladder, name in SITES:
        co, mo = va2off(d, cva), va2off(d, mva)
        cv, mv = d[co], d[mo]
        cins = bytes(d[co - len(cpre):co])
        mins = bytes(d[mo - len(mpre):mo])
        ok = cins == cpre and mins == mpre and cv in ladder and mv in ladder
        target = ladder[-1]
        state = ("AT TARGET" if (cv, mv) == (target, target)
                 else "at %d/%d -> %d" % (cv, mv, target))
        if (cv, mv) != (target, target):
            dirty += 1
        print("  %-22s cmp %08X=%-3d mov %08X=%-3d  ladder %-13s %s%s"
              % (name, cva, cv, mva, mv, "/".join(map(str, ladder)), state,
                 "" if ok else "   <== UNEXPECTED SHAPE OR VALUE"))
        bad |= not ok
        rows.append((co, mo, ladder, target))
    print("  %-22s cmp %08X=%-3d mov %08X=%-3d  (movement -- never written)"
          % ("GetMoves      ceiling", GETMOVES[0], d[va2off(d, GETMOVES[0])],
             GETMOVES[1], d[va2off(d, GETMOVES[1])]))
    if bad:
        sys.exit("\nABORT: a site is off its ladder or its instruction shape moved. Nothing written.")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written; %d row(s) not at target)" % dirty)
        return
    want = [(lad[0] if a.undo else lad[-1]) for _c, _m, lad, _t in rows]
    if all(d[co] == w and d[mo] == w for (co, mo, _l, _t), w in zip(rows, want)):
        print("\nalready there -- nothing to do (idempotent).")
        return
    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP); print("  backup -> %s" % os.path.basename(BACKUP))
    for (co, mo, _l, _t), w in zip(rows, want):
        # HARD 127 WALL. The cmp half is `66 83 F8 ib` / `66 83 FA ib` (opcode 83 /7), whose imm8 is
        # SIGN-EXTENDED, and the value is read back with movsx. A ceiling of 150 (0x96) becomes -106:
        # `jle` is then false for every non-negative value, so the clamp fires on EVERY call and the
        # getter returns a constant 150 -- the clamp inverts from a cap into a force. HITS at 120 sits
        # 7 below the wall and that headroom is load-bearing. (damhp_manifest already hit this once:
        # "0xA0 unencodable imm8" @0x557878bc.) Above 127 you must re-encode, not just raise the byte.
        assert 0 <= w <= 0x7F, (
            "%s: value %d is not an encodable imm8 -- 83 /7 sign-extends it and movsx reads it back, "
            "which would INVERT the clamp from a cap into a force. Re-encode the site instead." % (_t, w))
        d[co] = w; d[mo] = w
    open(TARGET, "wb").write(bytes(d))
    print("\n%s -- %d bounds (%d immediates) written."
          % ("UNDONE (ladder[0] everywhere)" if a.undo else "APPLIED (targets)",
             len(rows), 2 * len(rows)))


if __name__ == "__main__":
    main()
