#!/usr/bin/env python3
"""Cross-check the computed mod manifest against the March-2026 `Ziggurat upload/` folder.

Three buckets:
  ONLY-PREV   shipped last time, not in CHANGED+ADDED now
              -> either over-shipped (byte-identical to vanilla) or a genuine gap
  ONLY-NOW    in CHANGED+ADDED, absent from the last release
              -> everything built since March 2026
  BOTH        and whether the live file still matches what was shipped
"""
import hashlib
import json
import os
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PREV = os.path.join(GAME, "Ziggurat upload")


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


man = json.load(open(sys.argv[1]))
now = {p.lower(): p for p in man["changed"] + man["added"]}

prev = {}
for root, _d, files in os.walk(PREV):
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), PREV).replace("\\", "/")
        prev[rel.lower()] = rel

only_prev = sorted(prev[k] for k in prev if k not in now)
only_now = sorted(now[k] for k in now if k not in prev)
both = sorted(now[k] for k in now if k in prev)

# Of the ONLY-PREV files, which are actually identical to the live install?
identical, differing, gone = [], [], []
for rel in only_prev:
    live = os.path.join(GAME, rel.replace("/", os.sep))
    if not os.path.exists(live):
        gone.append(rel)
    elif md5(live) == md5(os.path.join(PREV, rel.replace("/", os.sep))):
        identical.append(rel)
    else:
        differing.append(rel)

changed_since, same_since = [], []
for rel in both:
    live = os.path.join(GAME, rel.replace("/", os.sep))
    p = os.path.join(PREV, rel.replace("/", os.sep))
    (changed_since if md5(live) != md5(p) else same_since).append(rel)


def bydir(paths):
    g = {}
    for p in paths:
        g.setdefault(os.path.dirname(p) or "<root>", []).append(p)
    return sorted(g.items())


print("prev release: %d files | manifest now: %d files" % (len(prev), len(now)))
print("\n=== ONLY-PREV, live copy is byte-identical to it (%d) ===" % len(identical))
print("    over-shipped last time: vanilla files that never needed to move")
for d, ps in bydir(identical):
    print("  %-28s %d" % (d + "/", len(ps)))

print("\n=== ONLY-PREV, live copy DIFFERS (%d) -- investigate ===" % len(differing))
for p in differing:
    print("  %s" % p)

print("\n=== ONLY-PREV, absent from live install (%d) ===" % len(gone))
for p in gone:
    print("  %s" % p)

print("\n=== ONLY-NOW (%d) -- new mod content since March 2026 ===" % len(only_now))
for d, ps in bydir(only_now):
    print("  %s/  (%d)" % (d, len(ps)))
    for p in ps:
        print("      %s" % os.path.basename(p))

print("\n=== BOTH, changed since the last release (%d) ===" % len(changed_since))
for d, ps in bydir(changed_since):
    print("  %s/  (%d)  %s" % (d, len(ps), ", ".join(os.path.basename(x) for x in ps[:8])
                               + (" ..." if len(ps) > 8 else "")))
print("\n=== BOTH, unchanged since the last release: %d ===" % len(same_since))
