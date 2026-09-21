#!/usr/bin/env python
r"""
build_hero_chassis_atkdam.py -- per-stat multiplier on the hero chassis (HERORES.PFS).

CURRENT TUNING (user, 2026-08-20):  ATTACK x1 (unchanged)   DAMAGE x2 (doubled)

    "double all the ATK/DAM values of the hero chassis"  -> both doubled
    "don't quadruple ATK"                                -> ATK returned to x1, DAMAGE kept at x2

Multipliers are relative to the PRE vectors recorded below, which are the values as
`build_statdouble.py` stage 2 left them. Change FACTOR and re-run --apply; the script rewrites in
place from whatever multiple is currently installed.

WHAT A "HERO CHASSIS" IS
------------------------
`THeroResource` -- the 38 records in `<game>/Release/HERORES.PFS`. Each is the stat template a hero
is built from; `THero.LinkToResource @0x55787984` hangs it off `THero.dwResource`, and a hero's live
stat is chassis + bought bonus + item + ability.

FIELD MAP -- confirmed by DECOMPILE, not inferred from the skill-point cost multipliers
---------------------------------------------------------------------------------------
Tag -> field offset is from `THeroResource.ReadWrite @0x55789FD4`; each field is then pinned by the
getter that actually reads it:

  | tag  | field  | stat        | proved by                                            | cost |
  |------|--------|-------------|------------------------------------------------------|------|
  | 0x0F | +0x24  | **ATTACK**  | `THero.GetInherentAttack @0x55788354`  res+0x24       |  x5  |
  | 0x10 | +0x25  | Defence     | `THero.GetInherentDefense @0x557883DC`                |  x5  |
  | 0x11 | +0x26  | **DAMAGE**  | `THero.GetInherentDamage @0x55788478`  res+0x26, and  | x10  |
  |      |        |             | `THero.GetDamage @0x55788484` sums res+0x26           |      |
  | 0x12 | +0x27  | Hit points  | `THero.GetHits @0x5578859C`            res+0x27       |  x5  |
  | 0x13 | +0x28  | Movement    | `THero.GetMoves @0x557885C0`           res+0x28       |  x2  |
  | 0x14 | +0x29  | Resistance  | `THero.GetInherentResistance @0x55788500`            |  x5  |

⚠ Do NOT identify these by cost multiplier alone. The costs (5/5/10/5/5/2 in
`THeroResource.UsedSkillPoints @0x55789F50`) are ambiguous between damage and hit points; the getters
are decisive. The 24..36 range of +0x28 is MOVEMENT -- exactly the trap `build_statdouble.py`
documents (applying the Unitres tag map to HERORES doubles movement and misses resistance).

⚠ CHASSIS DEFENCE AND RESISTANCE ARE ALREADY DOUBLED -- DO NOT TOUCH THEM HERE
------------------------------------------------------------------------------
Stage 2 of the 5% conversion doubled chassis ATK, DEF and RES (DEF 1..4 -> 2..8, RES 2..6 -> 4..12).
Doubling DEF/RES again would QUADRUPLE them, which is exactly what "don't quadruple ATK" ruled out.
This script therefore owns only ATK and DAM, and holds ATK at x1 so the conversion's own doubling is
the only one applied to it.

DAMAGE, by contrast, is NOT part of the conversion identity -- only ATK/DEF/RES double, damage never
does. So the x2 here is a deliberate balance change, roughly doubling hero base damage output.
Recorded so nobody later mistakes it for conversion damage and "fixes" it.

HEADROOM (checked against the LIVE clamps)
------------------------------------------
  * `THero.GetDamage` upper clamp is 30 live (`cmp ax,0x1e` @0x557884EC; vanilla was 10). Chassis
    damage max 4 -> 8, comfortably clear. `build_hero_clamps.py` deliberately leaves this at 30.
  * Hero ATK/DEF/RES clamps were raised 30 -> 40 by `build_hero_clamps.py` (2026-08-20).
  * Signed-byte safe: max value written is 8.

⚠ UNDO ORDER -- THIS SCRIPT LAYERS ON TOP OF `build_statdouble.py` STAGE 2
--------------------------------------------------------------------------
Stage 2 owns the same 38 ATK bytes (and DEF/RES). While ATK's factor here is 1 this script writes
them back to exactly the stage-2 value, so the two agree; if ATK is ever raised above 1 again the
ordering below matters:

  undo:     this script `--undo`            THEN  `build_statdouble.py --undo`
  re-apply: `build_statdouble.py --apply`   THEN  this script `--apply`

`build_statdouble.py --undo` halves ATK/DEF/RES and does NOT touch DAM, so a wrong order leaves a
mixed file. The vector check detects that and aborts with a diagnosis, but cannot repair it.

IDEMPOTENCE
-----------
A scaled stat looks exactly like a legitimate stat, so there is no in-band marker. The script matches
each stat's full 38-value vector against PRE x1 and PRE x2 and refuses anything else. Human-readable
cross-check: DAMAGE holds 24 odd values at x1 and none at x2.

The `.pfs` edit is an in-place 1-byte poke per site (no length change, no directory re-emit), then
the trailing CRC-32 is repaired. HERORES.PFS does carry the `1C DF 44 21` magic and a CRC; the
resolver refuses to touch a file whose residue is already wrong.

USAGE
    python build_hero_chassis_atkdam.py            verify / dry run (writes nothing)
    python build_hero_chassis_atkdam.py --apply    write PRE x FACTOR for each stat
    python build_hero_chassis_atkdam.py --undo     return every stat to PRE x1
"""
import os, sys, zlib, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# reuse the proven .pfs resolver rather than writing a second parser that could drift
from build_statdouble import pfs_sites, PFS_RESIDUE, kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "Release", "HERORES.PFS")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-herochassis")

TAGMAP = {0x0F: "ATK", 0x11: "DAM"}       # confirmed by the getters -- see the table above
N_RECORDS = 38
FACTOR = {"ATK": 1, "DAM": 2}             # <-- the tuning knob; multiples of PRE
ALLOWED = (1, 2)                          # factors the state machine can recognise

# The stage-2 values this script was built against, in file order. Verify-before-write is
# all-or-nothing against PRE x f for f in ALLOWED; anything else aborts.
PRE = {
    "ATK": [4, 8, 6, 8, 8, 6, 6, 6, 6, 6, 8, 4, 4, 8, 6, 8, 8, 6, 6,
            6, 8, 6, 8, 4, 4, 6, 4, 6, 6, 4, 4, 4, 4, 4, 6, 2, 2, 4],
    "DAM": [3, 3, 3, 3, 2, 2, 3, 3, 2, 4, 2, 3, 3, 3, 3, 3, 2, 2, 3,
            3, 2, 4, 2, 3, 3, 3, 3, 3, 2, 3, 3, 3, 3, 4, 2, 3, 1, 4],
}
MAX_BYTE = 127


def read_state():
    d, recs, sites = pfs_sites(TARGET, TAGMAP)
    if len(recs) != N_RECORDS:
        sys.exit("ABORT: HERORES.PFS parsed %d records, expected %d -- not the file this script was "
                 "verified against." % (len(recs), N_RECORDS))
    cur, off = {k: [] for k in PRE}, {k: [] for k in PRE}
    for o, name, val in sites:
        cur[name].append(val); off[name].append(o)
    for k in cur:
        if len(cur[k]) != N_RECORDS:
            sys.exit("ABORT: found %d %s bytes, expected %d." % (len(cur[k]), k, N_RECORDS))
    factor = {}
    for k in PRE:
        factor[k] = next((f for f in ALLOWED if cur[k] == [v * f for v in PRE[k]]), None)
    return d, cur, off, factor


def write(d, off, factor):
    out = bytearray(d)
    n = 0
    for k in PRE:
        for o, base, old in zip(off[k], PRE[k], (None,) * N_RECORDS):
            nv = base * factor[k]
            assert 0 <= nv <= MAX_BYTE, "%s at %s would leave a byte's range" % (k, hex(o))
            if out[o] != nv:
                out[o] = nv; n += 1
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE, "CRC repair failed"
    open(TARGET, "wb").write(bytes(out))
    return n


def main():
    ap = argparse.ArgumentParser(description="scale hero chassis ATTACK and DAMAGE")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d, cur, off, factor = read_state()
    want = {k: 1 for k in PRE} if a.undo else FACTOR

    print("build_hero_chassis_atkdam -- HERORES.PFS, %d chassis" % N_RECORDS)
    print("target: %s\n" % "  ".join("%s x%d" % (k, want[k]) for k in sorted(want)))
    for k in sorted(PRE):
        f = factor[k]
        odd = sum(1 for v in cur[k] if v % 2)
        state = ("x%d" % f) if f else "UNRECOGNISED"
        arrow = ""
        if f is not None and f != want[k]:
            arrow = "  ->  x%d (%d..%d)" % (want[k], min(PRE[k]) * want[k], max(PRE[k]) * want[k])
        elif f is not None:
            arrow = "  (already at target)"
        print("  %-4s min %2d  max %2d  odd %2d   currently %-12s%s"
              % (k, min(cur[k]), max(cur[k]), odd, state, arrow))

    bad = [k for k, f in factor.items() if f is None]
    if bad:
        print()
        sys.exit("ABORT: %s vector(s) match no recognised multiple of the recorded stage-2 state.\n"
                 "Something else has changed HERORES.PFS -- investigate before writing.\n"
                 "(If `build_statdouble.py --undo` was run while this script was applied, ATK will\n"
                 " sit at the stage-2 pre-state while DAM stays scaled. Restore\n"
                 " HERORES.PFS.pre-herochassis, re-apply build_statdouble stage 2, then this script.)"
                 % ", ".join(bad))

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return

    if factor == want:
        print("\nalready at the target tuning -- nothing to do (idempotent).")
        return
    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP); print("  backup -> %s" % os.path.basename(BACKUP))
    n = write(d, off, want)
    print("\n%s -- %d bytes rewritten, CRC repaired. Now: %s"
          % ("UNDONE" if a.undo else "APPLIED", n,
             "  ".join("%s x%d" % (k, want[k]) for k in sorted(want))))
    if not a.undo and want.get("DAM", 1) != 1:
        print("Chassis DAMAGE is NOT part of the 5% conversion identity -- this is a balance change.")


if __name__ == "__main__":
    main()
