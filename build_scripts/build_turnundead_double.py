#!/usr/bin/env python
r"""
build_turnundead_double.py -- Turn Undead damage from level x RES/2 to level x RES.

User ruling 2026-08-27. `build_turnundead_res.py` made Turn Undead's damage scale off the
caster's Resistance instead of a per-level constant; the 2026-08 doubling then took it to
`level x RES / 2`. This doubles it again, to `level x RES`.

THE ARITHMETIC. Both caves compute the same thing from RES in EAX and level in EDX:

    imul eax, edx        ; RES * level
    add  eax, 2          ;  \  round(RES*level / 4)
    shr  eax, 2          ;  /
    add  eax, eax        ; x2      => 2 * round(R*L/4)  ~= R*L/2
    cmp  eax, 0x7f ...   ; clamp to 127 (the field is a signed byte)

Changing the pair `add 2 / shr 2` to `add 1 / shr 1` gives `2 * round(R*L/2)` = **R*L**,
rounded up to even. Keeping the trailing `add eax,eax` is deliberate: it holds the result on
even numbers, which is what the doubled stat scale expects, and it leaves the 127 clamp
untouched. At RES 20 the four levels go 10/20/30/40 -> 20/40/60/80.

⚠ THE CLAMP NOW BINDS. 127 is the ceiling and a level-4 caster reaches it at RES 32
(4 x 32 = 128). Above that, damage stops rising. That is a real behaviour change, not a
rounding detail -- hero Resistance caps at 40, so a level-4 Turn Undead hero at RES 33+ is
clamped. Left as-is because the byte cannot hold more.

⚠ TWO CAVES, ONE INVARIANT. The damage cave and the info-card cave duplicate this
arithmetic; if they drift, the card lies about what the attack does. Both are patched
together and the script REFUSES to write unless both read the same state, so they can never
be half-applied.

    0x5580E2A0  damage    reads TCombatUnit.GetResistance via [vmt+0x74]
                          add imm @0x5580E2B5, shr imm @0x5580E2B8
    0x5580E300  display   reads TAbstractUnit.GetResistance via [vmt+0xCC]
                          add imm @0x5580E33C, shr imm @0x5580E33F

Attack is NOT touched: `TTurnUndeadAbility.GetTouchAttack @0x5576B1F4` already returns the
doubled 18/20/22/24 and is correct.

Neither immediate is an address, so nothing here needs to be position-independent and no
displaced byte carries a .reloc entry.

USAGE
    python build_scripts/build_turnundead_double.py            verify / dry run
    python build_scripts/build_turnundead_double.py --apply    level x RES
    python build_scripts/build_turnundead_double.py --undo     back to level x RES/2
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
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-turnundeaddouble")
IMAGE_BASE = 0x55700000

# (imm VA, instruction VA, expected first two opcode bytes, ladder, label)
SITES = [
    (0x5580E2B5, 0x5580E2B3, b"\x83\xc0", (2, 1), "damage cave  add eax, imm"),
    (0x5580E2B8, 0x5580E2B6, b"\xc1\xe8", (2, 1), "damage cave  shr eax, imm"),
    (0x5580E33C, 0x5580E33A, b"\x83\xc0", (2, 1), "display cave add eax, imm"),
    (0x5580E33F, 0x5580E33D, b"\xc1\xe8", (2, 1), "display cave shr eax, imm"),
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
    ap = argparse.ArgumentParser(description="double Turn Undead damage (AoWEPACK.dpl)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    print("build_turnundead_double -- damage level x RES/2 -> level x RES")
    print("target: %s\n" % TARGET)
    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())

    rows, bad, states = [], False, set()
    for imm_va, insn_va, opc, ladder, name in SITES:
        io_, oo = va2off(d, imm_va), va2off(d, insn_va)
        if io_ is None or oo is None:
            print("  %-28s %08X  <== NOT IN ANY SECTION" % (name, imm_va)); bad = True; continue
        if bytes(d[oo:oo + len(opc)]) != opc:
            print("  %-28s %08X  <== opcode at %08X is %s, expected %s"
                  % (name, imm_va, insn_va, bytes(d[oo:oo + len(opc)]).hex(" "), opc.hex(" ")))
            bad = True; continue
        cur, target = d[io_], ladder[-1]
        on = cur in ladder
        states.add(cur)
        print("  %-28s %08X  %-3d %s%s"
              % (name, imm_va, cur, "AT TARGET" if cur == target else "-> %d" % target,
                 "" if on else "   <== OFF LADDER"))
        bad |= not on
        rows.append((io_, ladder))

    # The whole point of the pair: the card must never disagree with the damage dealt.
    if len(states) > 1:
        print("\n  <== THE TWO CAVES DISAGREE (values seen: %s)" % sorted(states))
        bad = True
    if bad:
        sys.exit("\nABORT: refusing to write a half-applied or drifted state.")

    cur = states.pop()
    print("\n  state: %s   (damage at RES 20 = %s by level)"
          % ("APPLIED" if cur == 1 else "level x RES/2",
             "/".join(str(20 * L // (1 if cur == 1 else 2)) for L in (1, 2, 3, 4))))

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written.  --apply to patch, --undo to revert)")
        return

    want = rows[0][1][0] if a.undo else rows[0][1][-1]
    if cur == want:
        print("\n  already there -- nothing to do.")
        return

    kill_aow()
    if a.apply and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    for o, lad in rows:
        d[o] = lad[0] if a.undo else lad[-1]
    open(TARGET, "wb").write(bytes(d))
    print("  %s -- 4 site(s) written, both caves in step."
          % ("UNDONE" if a.undo else "APPLIED"))
    if a.apply:
        print("\n  NEEDS THE USER'S IN-GAME TEST -- nothing here is confirmed:")
        print("    1. the info card and the damage actually dealt still agree")
        print("    2. at RES 20 a level-1 Turn Undead does ~20, a level-4 ~80")
        print("    3. a level-4 caster above RES 32 is clamped at 127 (expected, not a bug)")


if __name__ == "__main__":
    main()
