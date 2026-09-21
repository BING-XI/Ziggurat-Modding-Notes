#!/usr/bin/env python3
r"""Audit this install for STALE REVERT instructions.

A `.pre-<feature>` backup is a snapshot of the WHOLE file, so restoring it destroys every feature
applied to that file afterwards. Only the NEWEST backup for a given file is a safe one-layer revert.
A "revert X then re-apply" procedure is therefore correct the day it is written and becomes destructive
the moment anyone patches that file again -- silently, with no warning in the doc.

Backups can also MOVE. On 2026-07-29/30 the 42 older `AoWEPACK.dpl.pre-*` layers were relocated from the
game root into `Modding Resources/backups/`; the move preserved mtimes, so the layer order is intact and
every one of those snapshots is still a valid (if deep) revert target. This script scans BOTH directories
-- looking only in the root made 42 of 47 layers appear deleted.

A revert instruction naming a backup that exists in NEITHER place has no revert path at all: the reader
plans a rollback around a file that does not exist. Until 2026-07-30 that class was invisible here
(mentions of absent backups were skipped silently); it is now reported first, as MISSING.

This prints, for every patched binary, the true layer order, then scans `Modding Resources/` (docs AND
build scripts) for revert instructions and flags the ones that have gone stale or gone missing.

Layer order is derived from backup mtimes: `shutil.copy2` preserves mtime, so a backup's mtime is the
live file's state at the moment it was taken -- sorting by mtime reproduces the application order.

⚠ LIMIT OF THAT HEURISTIC: two backups can share an mtime exactly (HSEPack.dpl's `.pre-dlgdirs` and
`.pre-mapcursor` both read 2026-07-06 20:01:42.659 yet differ in content). Ties are now called out
explicitly -- when you see one, resolve the real order by byte-diffing the backups against the features'
documented patch sites, as `Editor_Modernization_DialogDirs_Toolbar.md` does. Sorting alone gets it wrong.

    python revert_audit.py            # summary: layer order + missing/stale/safe counts
    python revert_audit.py --all      # also list every individual finding

Read-only. Never writes anything.
"""
import os, re, sys, time
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# tools dir + game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
MR = os.path.join(GAME, "Modding Resources")
VERBOSE = "--all" in sys.argv

# ---- layer inventory ---------------------------------------------------------------------------
# Backups live in TWO places. On 2026-07-29/30 the older AoWEPACK.dpl layers were MOVED out of the
# game root into `Modding Resources/backups/` (mtimes preserved by the move, so layer order survives).
# Scanning only the root made 42 of 47 layers look deleted -- scan both, and report which dir each is in.
BACKUP_DIRS = [(GAME, "root"), (os.path.join(MR, "backups"), "moved")]

layers = defaultdict(list)                       # target file -> [(mtime, feature, where)]
for d, where in BACKUP_DIRS:
    if not os.path.isdir(d):
        continue
    for fn in os.listdir(d):
        if ".pre-" not in fn:
            continue
        base, _, feat = fn.partition(".pre-")
        p = os.path.join(d, fn)
        if os.path.isfile(p):
            layers[base].append((os.path.getmtime(p), feat, where))
for k in layers:
    layers[k].sort()
order = {k: [f for _m, f, _w in v] for k, v in layers.items()}
newest = {k: v[-1] for k, v in order.items()}
whereof = {(k, f): w for k, v in layers.items() for _m, f, w in v}

print("=" * 96)
print("LAYER ORDER  (oldest first; only the LAST is a safe single revert)")
print("=" * 96)
ties = []            # (base, [features]) where mtimes are equal -> order below is NOT trustworthy
for base in sorted(layers):
    nmoved = sum(1 for _m, _f, w in layers[base] if w == "moved")
    extra = f"  ({nmoved} in Modding Resources/backups/)" if nmoved else ""
    print(f"\n{base}   [{len(order[base])} layers]{extra}")
    seen_m = defaultdict(list)
    for i, (m, feat, where) in enumerate(layers[base]):
        seen_m[m].append(feat)
        mark = "  <-- safe single revert" if i == len(layers[base]) - 1 else ""
        loc = "" if where == "root" else "  [moved]"
        print(f"  {i+1:2d}. {time.strftime('%Y-%m-%d %H:%M', time.localtime(m))}  "
              f".pre-{feat}{loc}{mark}")
    for m, feats in seen_m.items():
        if len(feats) > 1:
            ties.append((base, feats))
            print(f"      ^^ ⚠ TIED mtimes: {', '.join('.pre-'+f for f in feats)} -- the order shown")
            print( "         is ALPHABETICAL, not real. Resolve by byte-diffing the backups against")
            print( "         each feature's documented patch sites; do not trust this listing.")

# ---- scan for revert instructions --------------------------------------------------------------
MENTION = re.compile(r"\.pre-([A-Za-z0-9_]+)")
REVERTISH = re.compile(r"revert|restore|copy .*\.pre-|roll ?back|undo", re.I)
# Lines that have already RECKONED WITH layering are not defects. Two families:
#  - explicit warnings ("do not revert X", "destructive", ...)
#  - corrected instructions that state the depth or route around it ("layer 19/47", "undo surgically",
#    "costs 27 features", "NOT by snapshot"). Naming a backup is fine once the line says what it costs.
EXEMPT = re.compile(
    r"do ?n.t .{0,30}(revert|follow)|NOT revert|NOT SURGICAL|destructive|stale|would (lose|wipe)|⚠|✗"
    r"|layer \d+ ?/ ?\d+|\b\d+/\d+\b|\d+(st|nd|rd|th) of \d+|undo(ne)? surgical|surgical(ly)?\b"
    r"|NOT by snapshot|costs? \d+|wipes|not the newest|no longer the newest|only layer"
    r"|safe single revert", re.I)
# lines that already say the backup is gone -- not defects either
GONE_OK = re.compile(r"backup deleted|no revert path|no longer exists|pruned|deleted 2026"
                     r"|does ?n.t exist|does not exist|neither the game root", re.I)
PLACEHOLDER = {"X", "Y", "N", "feature", "featurename"}   # `.pre-X` in generic examples

missing, stale, safe, exempt = [], [], [], []
for root, dirs, files in os.walk(MR):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
    for f in files:
        if not (f.endswith(".py") or f.endswith(".md")):
            continue
        rel = os.path.relpath(os.path.join(root, f), MR)
        try:
            lines = open(os.path.join(root, f), encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if not REVERTISH.search(line):
                continue
            # Judge a small CONTEXT WINDOW, not the bare line: a revert warning is usually a prose
            # block or docstring paragraph, so the "-- costs 32 features" clause routinely lands on a
            # neighbouring line. Scoring line-by-line reported every corrected multi-line block as
            # still-stale. +-3 lines is enough for every block in this folder.
            ctx = "\n".join(lines[max(0, i - 4):i + 3])
            reckoned = bool(EXEMPT.search(ctx))
            for feat in set(MENTION.findall(line)):
                if feat in PLACEHOLDER:
                    continue
                tgts = [b for b in order if feat in order[b]]
                rec = (rel, i, feat, tgts, line.strip()[:130])
                if not tgts:
                    # No backup of this name exists on ANY file -- deleted rather than moved, or never
                    # taken. Not "stale": there is no revert path at all. Exempt only if the text says so.
                    (exempt if (reckoned or GONE_OK.search(ctx)) else missing).append(rec)
                    continue
                bad = [t for t in tgts if newest[t] != feat]
                rec = (rel, i, feat, bad or tgts, line.strip()[:130])
                (exempt if (bad and reckoned) else
                 stale if bad else safe).append(rec)

print("\n" + "=" * 96)
print(f"REVERT INSTRUCTIONS:  {len(missing)} MISSING  ·  {len(stale)} STALE  ·  "
      f"{len(safe)} safe  ·  {len(exempt)} already warned")
print("=" * 96)

# ---- MISSING: the named backup does not exist on disk at all -----------------------------------
if missing:
    bad_feats = defaultdict(list)
    for rel, i, feat, _t, line in missing:
        bad_feats[feat].append((rel, i, line))
    print(f"""
*** {len(missing)} mention(s) name a backup that exists in NEITHER the game root NOR
    Modding Resources/backups/ ({len(bad_feats)} distinct feature names). These have no revert path at
    all -- the snapshot was never taken, or was deleted rather than moved. Undo surgically (script
    --undo/--revert) or rebuild from the build script. Annotate the line "backup deleted -- no revert
    path" so it stops reading as usable.
""")
    for feat in sorted(bad_feats, key=lambda f: (-len(bad_feats[f]), f))[: (99 if VERBOSE else 10)]:
        hits = bad_feats[feat]
        print(f"  .pre-{feat}  ({len(hits)} mention(s))")
        for rel, i, line in sorted(hits)[: (99 if VERBOSE else 2)]:
            print(f"      {rel}:{i}\n        | {line}")
    if not VERBOSE and len(bad_feats) > 10:
        print(f"  ... and {len(bad_feats) - 10} more distinct name(s)")

print("""
NOTE most 'stale' hits are the routine per-script line "Revert = copy the matching .pre-* backup".
That is unfixable in principle -- it is only ever true for whichever feature is currently newest.
What matters is the PROCEDURAL ones: anything telling you to revert as a STEP ("re-tune by reverting
X first, then re-apply"). Those get executed, and they destroy the layers above X.
""")
worst = defaultdict(list)
for rel, i, feat, tgts, line in stale:
    lost = max((len(order[t]) - order[t].index(feat) - 1) for t in tgts)
    worst[lost].append((rel, i, feat, line))
for lost in sorted(worst, reverse=True)[: (99 if VERBOSE else 8)]:
    print(f"\n--- would destroy {lost} later layer(s) ---")
    for rel, i, feat, line in sorted(worst[lost])[: (99 if VERBOSE else 4)]:
        print(f"  {rel}:{i}  (.pre-{feat})\n      | {line}")
if not VERBOSE:
    print("\n(run with --all for the complete list)")
