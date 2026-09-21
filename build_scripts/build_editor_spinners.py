#!/usr/bin/env python
r"""
build_editor_spinners.py -- raise the stat-spinner MaxValue ceilings in the editor's DFM resources.

WHY (and why this was ALREADY a live bug before the DAM/HP pass)
----------------------------------------------------------------
The unit / hero-chassis / item edit forms in AoWDevEd.exe clamp their stat spinners
via DFM `MaxValue` properties: ATK/DEF/RES/DAM = 10, Hits/Moves = 50. The 5% conversion doubled
unit stats to 20+ and the DAM/HP pass doubled damage (to 20) and hits (to 60) -- **opening a unit
in the editor and re-saving silently clamps every doubled stat back to the spinner ceiling.**
That corruption path has been live since the stat conversion; this closes it.

New ceilings: ATK/DEF/RES/DAM -> 60, Hits -> 100, Moves -> 50 (movement never scaled; max 44).
All fit the DFM i8 encoding (<= 127).
  2026-08-31  Hits 120 -> 100, tracking the engine HP ceiling (build_hero_clamps.py ladder
              80/120/100 for BOTH THero.GetHits and the SetUnitHits purchase cap, and
              build_medal_hpmv.py v4 for the unit computed-HP cap cave). The script moved to a
              LADDER model in the same edit -- the old two-state (old, new) rule reads the previous
              target as foreign and aborts, so it could not express a re-target at all.

HOW SITES ARE FOUND -- dynamically, never by fixed offset
---------------------------------------------------------
Each site is the value byte of a `\x08MaxValue\x02<i8>` DFM property. The owner is the nearest
preceding `<name>Edit` component-name marker. (The discovery workflow's fixed offsets were off by
ten bytes -- the pattern scan is what actually verified.) Only owners matching the table below are
touched; every other MaxValue in the exe (Height spinners, percent spinners...) is left alone.

================================================================================
⚠⚠ THE EDITOR EXE TRAP -- an editor patch is TWO steps
================================================================================
`Ziggurat\AoWDevEd.exe` (zigexe.SRC_EDITOR) is the PATCH SOURCE, and nothing runs it. The
editor the owner actually launches is `Ziggurat\AoWzEd.exe` (zigexe.LIVE_EDITOR), which
`build_zigeditor.py` REBUILDS from AoWDevEd.exe. Skip the second step and the patch sits in
a file no one loads -- silently:

    python build_editor_spinners.py --apply    # patches Ziggurat\AoWDevEd.exe
    python build_zigeditor.py       --apply    # rebuilds -> Ziggurat\AoWzEd.exe

(build_zigeditor.py takes --apply / --undo / --png PATH; no args = dry run.)

⚠ `AoWEd.exe` is NO LONGER A TARGET. The 2026-09-09 move left no copy in the overlay -- only
the game root's stock one, which is VANILLA and must never be patched. This script used to
patch both editors in one run "so they stay in lockstep"; there is nothing left to lock step
with. Sites are still located by PATTERN, never by address, which is what made a second
target cheap and is worth keeping if one ever returns.

USAGE
    python build_editor_spinners.py            verify / dry run
    python build_editor_spinners.py --apply
    python build_editor_spinners.py --undo     restore 10/50

REVERT is `--undo`, surgical: it writes ladder[0] back into each spinner. There is no snapshot
layer to fall back on -- both `.pre-*` stacks were purged (2026-08-08, 2026-09-03).
"""
import os, re, sys, shutil, argparse

import zigexe

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")
EXES = [zigexe.SRC_EDITOR]
SUFFIX = ".pre-spinners"

# owner-substring -> LADDER of every ceiling this spinner has legitimately held, oldest first;
# the target is the last. Any ladder value verifies (half-applied states repair to the target);
# anything off the ladder aborts. --undo writes ladder[0] = the pre-script editor state.
# Same model as build_hero_clamps.py, and for the same reason: a two-state (old, new) rule cannot
# express a RE-TARGET -- the byte holding the previous target reads as foreign and aborts.
RULES = [("AttackEdit", (10, 60)), ("DefenseEdit", (10, 60)), ("ResistanceEdit", (10, 60)),
         ("DamageEdit", (10, 60)), ("HitsEdit", (50, 120, 100))]
# MovesEdit deliberately absent: movement never scales (max 44 < 50).
# HitsEdit 120 -> 100 on 2026-08-31 tracks the engine ruling; the spinner ceiling MUST match
# THero.GetHits / SetUnitHits (build_hero_clamps.py) and the unit cap cave (build_medal_hpmv.py v4)
# or the editor lets an author type an HP the engine then clamps away on the next re-save.

PAT = re.compile(rb"\x08MaxValue\x02(.)", re.S)
NAME = re.compile(rb"([A-Za-z][A-Za-z0-9_]{3,24}Edit)")


def sites_for(d):
    out = []
    for m in PAT.finditer(d):
        voff = m.start(1)
        names = NAME.findall(d[max(0, m.start() - 400):m.start()])
        owner = names[-1].decode() if names else "?"
        for key, ladder in RULES:
            if key in owner:
                out.append((voff, owner, ladder))
                break
    return out


def main():
    ap = argparse.ArgumentParser(description="editor stat-spinner ceilings")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    plans, bad = {}, False
    for exe in EXES:
        path = os.path.join(GAME, exe)
        if not os.path.isfile(path):
            print("== %s : MISSING -- skipped" % exe)
            continue
        d = bytearray(open(path, "rb").read())
        found = sites_for(d)
        print("== %s : %d spinner site(s)" % (exe, len(found)))
        for voff, owner, ladder in found:
            cur = d[voff]
            ok = cur in ladder
            print("   0x%06x  %-22s %3d  ladder %-12s %s%s"
                  % (voff, owner, cur, "/".join(map(str, ladder)),
                     "AT TARGET" if cur == ladder[-1] else "-> %d" % ladder[-1],
                     "" if ok else "   <== UNEXPECTED"))
            bad |= not ok
        plans[path] = (d, found)
    if bad:
        sys.exit("\nABORT: a spinner holds a value off its ladder. Investigate.")
    if not plans:
        sys.exit("\nABORT: no editor binary found to patch.")
    counts = {os.path.basename(p): len(f) for p, (_d, f) in plans.items()}
    if len(set(counts.values())) != 1:
        sys.exit("\nABORT: the targets matched different site counts %s -- the forms should "
                 "mirror each other; re-derive before writing." % counts)

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    for path, (d, found) in plans.items():
        # PROVED unpatched = every spinner still on ladder[0]. Tested BEFORE `d` is mutated, and
        # against the state on disk -- a snapshot taken during --undo or a re-target would preserve
        # our own earlier output under a name that claims to be the original.
        pristine = all(d[voff] == ladder[0] for voff, _o, ladder in found)
        n = 0
        for voff, owner, ladder in found:
            want = ladder[0] if a.undo else ladder[-1]
            if d[voff] != want:
                d[voff] = want; n += 1
        if n:
            # Snapshot goes in <game dir>\backups\, never beside the binary (CLAUDE.md 2026-09-03).
            bp = os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)
            if not pristine:
                print("no backup taken (%s is not in the pre-script state)"
                      % os.path.basename(path))
            elif not os.path.exists(bp):
                os.makedirs(BACKUP_DIR, exist_ok=True)
                shutil.copy2(path, bp); print("backup -> %s" % bp)
            open(path, "wb").write(bytes(d))
        print("%s: %d byte(s) written." % (os.path.basename(path), n))
    print("\n%s." % ("UNDONE" if a.undo else "APPLIED"))


if __name__ == "__main__":
    main()
