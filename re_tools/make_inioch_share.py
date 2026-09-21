"""Collect every script/note changed since a cutoff into a zip for a fellow modder.

Selection:
  Modding Resources/build_scripts/  (excluding __pycache__)
  Modding Resources/Zig notes/      (excluding _old/, the pre-2026-09-03 corpus that
                                     was consolidated into the twelve thematic files)
  Modding Resources/re_tools/       (excluding __pycache__)
  Modding Resources/build_ziggurat_manual.py

Deliberately NOT collected: Inioch/ (his own shares, coming back at him), New Faces/*.png,
Sept 2026 backup/*.dpl, Ziggurat Manual.log (carries the username), the generated
contact sheets and Ziggurat Manual.html, and any .pyc (Python bakes the absolute
source path into them).

Usage:
    python make_inioch_share.py --since "2026-08-29 10:33" [--out <path.zip>] [--apply]
Dry-run by default: prints the manifest and the username-leak scan, writes nothing.
"""
import argparse
import datetime
import os
import sys
import zipfile

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MR = os.path.join(GAME, "Modding Resources")

ROOTS = [
    os.path.join(MR, "build_scripts"),
    os.path.join(MR, "Zig notes"),
    os.path.join(MR, "re_tools"),
]
EXTRA = [
    os.path.join(MR, "build_ziggurat_manual.py"),
    # resolves a citation of any pre-2026-09-03 note name to its thematic file
    os.path.join(MR, "Zig notes", "_old", "REDIRECTS.md"),
]
SKIP_DIRS = {"__pycache__", "_old"}


def collect(cutoff_ts):
    out = []
    for root in ROOTS:
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for f in fn:
                if f.endswith(".pyc"):
                    continue
                p = os.path.join(dp, f)
                st = os.stat(p)
                if st.st_mtime > cutoff_ts:
                    out.append(p)
    for p in EXTRA:
        if os.path.exists(p) and os.stat(p).st_mtime > cutoff_ts:
            out.append(p)
    return sorted(out, key=lambda p: os.stat(p).st_mtime)


def leak_scan(paths):
    """Every file must be free of the user's profile name -- see CLAUDE.md."""
    needles = {n.encode() for n in
               {os.environ.get("USERNAME", ""), os.path.basename(os.path.expanduser("~"))}
               if n}
    hits = []
    for p in paths:
        with open(p, "rb") as fh:
            blob = fh.read()
        for n in needles:
            if n in blob or n.lower() in blob.lower():
                hits.append(p)
                break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help='local time, "YYYY-MM-DD HH:MM"')
    ap.add_argument("--out", default=None)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    cutoff = datetime.datetime.strptime(a.since, "%Y-%m-%d %H:%M")
    files = collect(cutoff.timestamp())
    total = sum(os.stat(p).st_size for p in files)

    for p in files:
        rel = os.path.relpath(p, MR).replace("\\", "/")
        m = datetime.datetime.fromtimestamp(os.stat(p).st_mtime)
        print(f"{m:%Y-%m-%d %H:%M}  {os.stat(p).st_size:>9}  {rel}")
    print(f"\n{len(files)} files, {total // 1024} KB uncompressed, cutoff {cutoff}")

    hits = leak_scan(files)
    if hits:
        print(f"\nLEAK SCAN: {len(hits)} file(s) contain the profile name -- fix before sending")
        for p in hits:
            print("   ", os.path.relpath(p, MR))
        return 1
    print("LEAK SCAN: clean")

    out = a.out or os.path.join(
        GAME, f"AoW-notes-{cutoff:%Y%m%d}-to-{datetime.date.today():%Y%m%d}.zip")
    if not a.apply:
        print(f"\ndry run -- would write {out}\nre-run with --apply")
        return 0

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            arc = os.path.relpath(p, MR).replace("\\", "/").replace("Zig notes/_old/", "Zig notes/")
            z.write(p, arc)
    print(f"\nwrote {out}  ({os.stat(out).st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
