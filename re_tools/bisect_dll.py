#!/usr/bin/env python3
r"""
bisect_dll.py -- binary-search the AoWEPACK.dpl backup stack to find WHICH LAYER introduced a bug.

WHY
---
Every `AoWEPACK.dpl.pre-<feature>` is a WHOLE-FILE snapshot of the DLL immediately before that
feature was applied. Restoring `.pre-X` therefore gives you "every layer older than X, and nothing
newer". That makes the stack a sorted array we can binary-search: ~33 layers -> ~6 tests instead of
33. Each test is a plain yes/no ("does the bug still happen?").

SAFETY -- READ THIS
-------------------
Restoring a snapshot DESTROYS every feature applied after it (that is the whole point here, but it
is also how people lose work). So this tool NEVER touches the live DLL until you have run
`--save-current`, which parks a copy in `_bisect/CURRENT.dpl`. `--restore-current` puts it back
exactly. The snapshots themselves are only ever READ, never written.

USAGE
-----
    python bisect_dll.py --save-current      # do this FIRST -- parks today's DLL
    python bisect_dll.py --list              # ordered layers, oldest first, with the search state
    python bisect_dll.py --test <name>       # install .pre-<name> (i.e. state BEFORE that feature)
    python bisect_dll.py --good <name>       # record: bug ABSENT at that layer -> search newer
    python bisect_dll.py --bad  <name>       # record: bug PRESENT at that layer -> search older
    python bisect_dll.py --next              # install the next midpoint to test
    python bisect_dll.py --restore-current   # put today's DLL back, whatever state we're in

The good/bad marks live in `_bisect/state.json`, so the search survives closing the terminal.

INTERPRETING THE RESULT
-----------------------
"bug ABSENT at .pre-X" + "bug PRESENT at .pre-Y" where Y is the very next layer after X means the
feature **X** introduced it -- X is the patch applied between those two snapshots.

CAVEAT worth keeping in mind: this finds the layer whose APPLICATION made the bug observable. That is
usually the culprit, but it can also be a layer that merely exposed an older latent defect (e.g. by
making a code path reachable). Confirm by reading what that feature actually changed.
"""
import json, os, shutil, sys, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zignames import zigexe

HERE  = os.path.dirname(os.path.abspath(__file__))
GAME  = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
DLL   = os.path.join(GAME, "AoWEPACK.dpl")
WORK  = os.path.join(GAME, "_bisect")
SAVED = os.path.join(WORK, "CURRENT.dpl")
STATE = os.path.join(WORK, "state.json")

def layers():
    """All .pre-* backups, OLDEST FIRST (mtime order == application order; shutil.copy2 preserves it)."""
    out = []
    for f in os.listdir(GAME):
        if f.startswith("AoWEPACK.dpl.pre-"):
            p = os.path.join(GAME, f)
            out.append((os.path.getmtime(p), f[len("AoWEPACK.dpl.pre-"):], p))
    out.sort()
    return [(n, p) for _m, n, p in out]

def load():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"good": [], "bad": []}

def save(st):
    os.makedirs(WORK, exist_ok=True)
    json.dump(st, open(STATE, "w"), indent=1)

def locked():
    """Which mod binary is holding Ziggurat\\AoWEPACK.dpl open, if any.

    ⚠ The MOD names only. The root's vanilla AoW.exe / AoWCompat.exe load the ROOT's copy of every
    package, so one of those running does not lock this DLL and must not stop a swap."""
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True).stdout
    except Exception:
        return None
    for exe in zigexe.ALL_EXES:
        if exe.lower() in out.lower():
            return exe
    return None

def install(path, label):
    who = locked()
    if who:
        sys.exit("[x] %s is running and locks the DLL. Close it and retry." % who)
    if not os.path.exists(SAVED):
        sys.exit("[x] refusing: run --save-current first (nothing would be recoverable otherwise).")
    shutil.copy2(path, DLL)
    print("[ok] installed %s -> AoWEPACK.dpl  (%d bytes)" % (label, os.path.getsize(DLL)))

def window(st, names):
    """Remaining candidate span: (lo, hi) indices into `names`, inclusive."""
    lo, hi = 0, len(names) - 1
    for g in st["good"]:
        if g in names:
            lo = max(lo, names.index(g))          # bug absent here -> culprit is NEWER
    for b in st["bad"]:
        if b in names:
            hi = min(hi, names.index(b) - 1)      # bug present here -> culprit is OLDER (or this one)
    return lo, hi

def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    names = [n for n, _p in layers()]
    paths = dict(layers())
    st = load()

    # An empty stack used to reach `names[lo]` with lo=0, hi=-1 and die on IndexError. It is the
    # NORMAL state now: both snapshot stacks were purged (2026-09-03 and 2026-09-09), and the
    # 2026-09-09 move repointed GAME at Ziggurat\, where no .pre-* has ever been written.
    # --save-current / --restore-current need no layers, so they run regardless.
    if not names and not ({"--save-current", "--restore-current"} & set(a)):
        sys.exit("[x] no AoWEPACK.dpl.pre-* snapshots in %s -- nothing to bisect.\n"
                 "    There is currently no layer history at all; revert is each build script's\n"
                 "    surgical --undo, not a snapshot restore." % GAME)

    if "--save-current" in a:
        os.makedirs(WORK, exist_ok=True)
        if os.path.exists(SAVED):
            print("[= ] %s already exists -- NOT overwriting (it is your only restore point)." % SAVED)
        else:
            shutil.copy2(DLL, SAVED)
            print("[ok] parked current AoWEPACK.dpl -> %s (%d bytes)" % (SAVED, os.path.getsize(SAVED)))
        return

    if "--restore-current" in a:
        who = locked()
        if who:
            sys.exit("[x] %s is running. Close it and retry." % who)
        if not os.path.exists(SAVED):
            sys.exit("[x] no saved copy at %s" % SAVED)
        shutil.copy2(SAVED, DLL)
        print("[ok] restored today's AoWEPACK.dpl (%d bytes)" % os.path.getsize(DLL))
        return

    if "--list" in a:
        lo, hi = window(st, names)
        print("layers oldest -> newest (restoring .pre-X = state BEFORE X):\n")
        for i, n in enumerate(names):
            mark = ""
            if n in st["good"]: mark = "  GOOD (bug absent)"
            if n in st["bad"]:  mark = "  BAD  (bug present)"
            cur = " <-- candidate window" if lo <= i <= hi and not mark else ""
            print("  %2d  %-16s%s%s" % (i, n, mark, cur))
        print("\ncandidate window: %s .. %s  (%d layers left)"
              % (names[lo], names[hi], max(0, hi - lo + 1)))
        return

    for flag, key in (("--good", "good"), ("--bad", "bad")):
        if flag in a:
            n = a[a.index(flag) + 1]
            if n not in names:
                sys.exit("[x] unknown layer %r" % n)
            if n not in st[key]:
                st[key].append(n)
            save(st)
            lo, hi = window(st, names)
            print("[ok] marked %s = %s" % (n, key.upper()))
            if hi < lo:
                print("\n*** CONVERGED: the culprit is the feature applied at layer %r ***" % names[lo])
            else:
                mid = (lo + hi) // 2
                print("next to test: %s   (window %s .. %s)" % (names[mid], names[lo], names[hi]))
            return

    if "--test" in a:
        n = a[a.index("--test") + 1]
        if n not in paths:
            sys.exit("[x] unknown layer %r" % n)
        install(paths[n], ".pre-" + n)
        print("     -> this is the state BEFORE '%s' was applied." % n)
        print("     Play, then run:  --good %s   (bug gone)   or   --bad %s   (bug still there)" % (n, n))
        return

    if "--next" in a:
        lo, hi = window(st, names)
        if hi < lo:
            print("*** CONVERGED: culprit = %r ***" % names[lo]); return
        mid = (lo + hi) // 2
        install(paths[names[mid]], ".pre-" + names[mid])
        print("     -> state BEFORE '%s'. Play, then --good/--bad %s" % (names[mid], names[mid]))
        return

    sys.exit(__doc__)

if __name__ == "__main__":
    main()
