#!/usr/bin/env python
r"""
build_ranged_damage.py -- +1 damage to every ranged-family attack, and close the BREATH gap.

TWO CHANGES, both user rulings of 2026-08-27, applied as one congruence group because they
land in the same family and the same descriptions:

1. **+1 damage to every ranged attack.** The doubling preserved hit chance and the damage
   *distribution*, but not the AVERAGE at the bottom of the scale: a damage rating of 1 going
   to 2 is a 50% rise in mean output, not 100%, because the roll's floor does not scale with
   it. Rather than special-case the small ones, every ranged-family attack gains +1.

2. **Breath damage was never doubled.** `TBreathAbility.Create @0x5576EE6B` sets DAM for
   Fire, Cold, Black, Divine AND Poison Breath from ONE shared byte -- the registration ctor
   `0x5576EE84` takes only an ability id, a name and a damage TYPE, no numbers. Its ATTACK was
   doubled 7 -> 14; the damage sat at vanilla 5. Same defect class as the five bolts.
   ⚠ Four of those five descriptions ALREADY read "(14/10)" -- the 2026-08-24 text pass
   doubled the STRING while the code stayed at 5. So this is not only a balance fix, it makes
   four shipped descriptions true for the first time.

   Flame Throwing overrides the shared byte with its own (`0x5576F23E`), and was likewise
   missed: its ATTACK doubled 4 -> 14 while its DAMAGE went the other way, 3 -> 2.

Final damage = (doubled-where-it-was-missed) + 1, so breath lands on 11 and Flame Throwing
on 4.

⚠ LAYERING WITH build_bolts_double.py. That script doubled the five bolts' damage 3 -> 6
earlier the same day; this one takes them 6 -> 7. Its ladders were widened to (3, 6, 7) so it
still verifies green afterwards. **Undo order matters: revert THIS script first, then
build_bolts_double.py**, or the bolt sites read 7 while that script expects 6 and it will
abort rather than write.

FIELD IDENTIFICATION -- derived, never assumed. `+0x29` is DAMAGE and `+0x2a` is ATTACK,
proven by `TRangedAttackAbility.GetDamageRA @0x5576E614` (`mov bl,[eax+0x29]`) and
`GetAttackRA @0x5576E65C` (`mov bl,[eax+0x2a]`). Three construction routes reach them:
  * ranged ctor `0x5576ED48` -- damage is the FIRST `push imm8` of the block, attack is CL
  * bolt ctor   `0x5576EDE8` -- damage is the FIRST `push imm8`, attack is ECX
  * `TBreathAbility.Create` -- both written directly as `mov byte [esi+0x29/0x2a], imm8`
⚠ The other pushes in a block are the damage-TYPE element and a sound id. Changing one of
those alters an attack's element or its noise, not its strength.

Every value below was byte-read from the live DLL; `pristine` is
`Modding Resources/AoWEPACK_original_backup.dpl`. Nothing here is an address operand, so
position independence is not in play even though the .dpl rebases, and no displaced byte
carries a .reloc entry.

USAGE
    python build_scripts/build_ranged_damage.py            verify / dry run (writes nothing)
    python build_scripts/build_ranged_damage.py --apply    write every target
    python build_scripts/build_ranged_damage.py --undo     write ladder[0] everywhere
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
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-rangeddamage")
IMAGE_BASE = 0x55700000

BYTE_MAX = 127          # +0x29 is a single byte read back sign-extended

# (imm VA, opcode VA, expected opcode byte, ladder oldest..target, label)
#   0x6A = push imm8 (ctor routes); 0xC6 = mov byte [reg+disp8], imm8 (breath route)
SITES = [
    # -- the 11 TRangedAttackAbility registrations, +1 each
    (0x5576F533, 0x5576F532, 0x6A, (6, 7), "Shoot Bolt"),
    (0x5576F572, 0x5576F571, 0x6A, (8, 9), "Throw Javelin"),
    (0x5576F5B1, 0x5576F5B0, 0x6A, (2, 3), "Hurl Stones"),
    (0x5576F5F0, 0x5576F5EF, 0x6A, (8, 9), "Fire Musket"),
    (0x5576F62F, 0x5576F62E, 0x6A, (24, 25), "Fire Cannon"),
    (0x5576F66E, 0x5576F66D, 0x6A, (12, 13), "Hurl Boulder"),
    (0x5576F6AD, 0x5576F6AC, 0x6A, (6, 7), "Poison Spit"),
    (0x5576F6EC, 0x5576F6EB, 0x6A, (4, 5), "Call Flames"),
    (0x5576F72B, 0x5576F72A, 0x6A, (4, 5), "Archery"),
    (0x5576F76A, 0x5576F769, 0x6A, (2, 3), "Poison Darts"),
    (0x5576F7A9, 0x5576F7A8, 0x6A, (8, 9), "Doom Gaze"),

    # -- the five bolts, already 3 -> 6 by build_bolts_double.py, now +1
    (0x5576F305, 0x5576F304, 0x6A, (6, 7), "Black Bolts"),
    (0x5576F33E, 0x5576F33D, 0x6A, (6, 7), "Magic Bolts"),
    (0x5576F377, 0x5576F376, 0x6A, (6, 7), "Frost Bolts"),
    (0x5576F3B0, 0x5576F3AF, 0x6A, (6, 7), "Lightning Bolts"),
    (0x5576F3E9, 0x5576F3E8, 0x6A, (6, 7), "Holy Bolts"),

    # -- the breath family. ONE byte serves Fire/Cold/Black/Divine/Poison Breath.
    #    5 (vanilla, never doubled) -> 10 (the doubling it missed) -> 11 (+1).
    (0x5576EE6E, 0x5576EE6B, 0xC6, (5, 11), "Breath x5 (shared: Fire/Cold/Black/Divine/Poison)"),
    #    Flame Throwing overrides the shared byte. Vanilla 3, Ziggurat cut it to 2, never
    #    doubled; user set it to 3 on 2026-08-27, then +1.
    (0x5576F241, 0x5576F23E, 0xC6, (2, 4), "Flame Throwing"),
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


def main():
    ap = argparse.ArgumentParser(description="+1 ranged damage, and the breath doubling gap")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    print("build_ranged_damage -- ranged/bolt/breath DAMAGE (+0x29)")
    print("target: %s\n" % TARGET)
    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())

    rows, bad, dirty = [], False, 0
    for imm_va, op_va, op_byte, ladder, name in SITES:
        io_, oo = va2off(d, imm_va), va2off(d, op_va)
        if io_ is None or oo is None:
            print("  %-50s %08X  <== NOT IN ANY SECTION" % (name, imm_va)); bad = True; continue
        if d[oo] != op_byte:
            print("  %-50s %08X  <== opcode at %08X is %02X, expected %02X"
                  % (name, imm_va, op_va, d[oo], op_byte)); bad = True; continue
        cur, target = d[io_], ladder[-1]
        if target > BYTE_MAX:
            print("  %-50s %08X  <== target %d exceeds the byte field" % (name, imm_va, target))
            bad = True; continue
        on = cur in ladder
        if cur != target:
            dirty += 1
        print("  %-50s %08X  %-3d %s%s"
              % (name, imm_va, cur, "AT TARGET" if cur == target else "-> %d" % target,
                 "" if on else "   <== OFF LADDER (legit: %s)" % ", ".join(map(str, ladder))))
        bad |= not on
        rows.append((io_, ladder))

    if bad:
        sys.exit("\nABORT: a site failed its checks. Nothing written.")
    print("\n  %d of %d site(s) not at target\n" % (dirty, len(SITES)))

    if not (a.apply or a.undo):
        print("(dry run -- nothing written.  --apply to patch, --undo to revert)")
        return

    want = [(lad[0] if a.undo else lad[-1]) for _o, lad in rows]
    if all(d[o] == v for (o, _l), v in zip(rows, want)):
        print("  already %s -- nothing to do." % ("at ladder[0]" if a.undo else "applied"))
        return

    kill_aow()
    if a.apply and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    for (o, _l), v in zip(rows, want):
        d[o] = v
    open(TARGET, "wb").write(bytes(d))
    print("  %s -- %d site(s) written."
          % ("UNDONE (ladder[0])" if a.undo else "APPLIED", len(rows)))
    if a.undo:
        print("\n  ⚠ Undo build_bolts_double.py AFTER this, not before -- it expects 6 at the")
        print("    five bolt sites and would abort while they still read 7.")
    else:
        print("\n  NEEDS THE USER'S IN-GAME TEST -- nothing here is confirmed:")
        print("    1. every ranged attack's card shows one more damage than before")
        print("    2. all five breaths read 14/11 and actually deal it (they shared one byte)")
        print("    3. Flame Throwing reads 14/4")
        print("    4. no attack changed its damage TYPE or its sound (adjacent immediates)")


if __name__ == "__main__":
    main()
