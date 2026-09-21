#!/usr/bin/env python3
"""mod_manifest.py -- what, exactly, does the Ziggurat mod consist of?

Answers it by MD5 against the GOG installer's own manifest, `goggame-1207658883.hashdb`,
which ships in the game root and records one MD5 per pristine-install file (975 of them).
That file is the only complete vanilla reference on disk -- `Modding Resources/` holds only
per-file baselines (AoWEPACK_original_backup.dpl, Release - Vanilla/).

hashdb format: 12-byte header `<III` = (headerSize=12, version=1, count), then `count`
records of 1056 bytes = 1024-byte NUL-padded relative path (backslash separators) + 32
ASCII hex chars of MD5.

Output classes
  CHANGED  in hashdb, present on disk, MD5 differs   -> must ship
  MISSING  in hashdb, absent on disk                 -> the mod deletes it (rare; flag it)
  ADDED    on disk, not in hashdb                    -> must ship IF it is mod content
  SAME     byte-identical to the GOG install         -> never ship

ADDED is noisy: saves, logs, editor state, the whole modding workshop. Everything under
IGNORE_DIRS / IGNORE_GLOBS is dropped from ADDED before reporting.

Usage
  python mod_manifest.py                 # summary + CHANGED/MISSING, ADDED grouped
  python mod_manifest.py --all           # also list every ADDED file individually
  python mod_manifest.py --json out.json # machine-readable manifest
  python mod_manifest.py --stage DIR     # copy CHANGED + curated ADDED into DIR, tree intact
"""
import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import struct
import sys
import zipfile

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

def _find_hashdb():
    """The GOG manifest describes the VANILLA install, so since the 2026-09-09 overlay
    split it lives one level ABOVE the mod: GAME is <root>/Ziggurat, the hashdb is in
    <root>. Comparing Ziggurat/ against it is still exactly right -- CHANGED means
    "differs from stock", ADDED means "new" -- only the file's location moved.
    ⚠ Missing it degrades SILENTLY: the report comes back empty and the exit code is 0."""
    name = "goggame-1207658883.hashdb"
    for d in (GAME, os.path.dirname(GAME)):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return os.path.join(GAME, name)          # keep the old path for the error message


HASHDB = _find_hashdb()

# Directories that are never mod content, whatever is in them.
IGNORE_DIRS = {
    "Modding Resources",   # the workshop: RE notes, scripts, Ghidra project
    # ⚠ 1Scenario is a MAP COLLECTION, not the rules mod: 620 files, 46 MB, 37% of the
    # download, and much of it is other people's maps (AoWHeaven's MP pack, Gibson, Groll,
    # And G, Inioch) with the same redistribution question as any third-party material.
    # Owner ruling 2026-09-11: ship it separately, not inside the installer. It used to sit
    # in ALWAYS_SHIP_DIRS, which ALSO disabled the junk filters for it -- 14 ipxwrapper.log
    # and stray .txt/.zip files were going out with the maps.
    "1Scenario",
    "Zig Modding Tools",   # map generator, in development
    "AoWx Modding Tools",  # third-party tools, not ours to redistribute
    "ZigMod",              # loose source art (bmp) for terrain tiles
    "Ziggurat upload",     # the PREVIOUS release staging folder (March 2026)
    "Ziggurat release",    # the CURRENT release staging folder, written by --stage
    "backups",             # .pre-* snapshots
    ".claude",
    "Save",                # player saves
    "EmailIn", "EmailOut", # PBEM working dirs
    "Microsoft.VC80.CRT",
    "__pycache__",
    "Scenario",            # player maps + map-generator output
    "Faces - Copy",        # working copy of Images/Faces
}

# Directories shipped WHOLE, exempt from IGNORE_GLOBS. Needed because these hold
# nothing but the very extensions the glob list drops (*.hsm, *.zip).
ALWAYS_SHIP_DIRS = set()   # empty since 2026-09-11: 1Scenario moved to IGNORE_DIRS.
# ⚠ If anything is ever put back here, note that ignored() checks this BEFORE IGNORE_GLOBS,
# so an entry exempts the directory from the junk filters too (*.log, *.ini, *.txt), not
# just from the extension filter it was added for. That is how 14 ipxwrapper.log files ended
# up in the release payload.

# Files that are mod content but are deliberately NOT shipped. Applies to CHANGED
# as well as ADDED -- IGNORE_GLOBS does not, so a patched file cannot be dropped
# by accident here.
NEVER_SHIP = {
    "AoWEd.exe",           # superseded by AoWDevEd.exe (owner ruling 2026-09-07)
    # The manual is hosted on GitHub Pages; shipping it too put 28 MB (22% of the download)
    # into every install to duplicate a web page. Owner ruling 2026-09-11.
    "Ziggurat Manual.exe",
    "Ziggurat Manual.html",
    # ...and with the manual gone, its builder and build cache have nothing to act on.
    # 313 KB of authoring code plus a sidecar keyed to a page that is not in the payload.
    # Owner ruling 2026-09-13.
    "build_ziggurat_manual.py",
    "Ziggurat Manual.html.build.json",
    # The author's prose overrides for a manual that is not in the payload. It appears the
    # moment anyone uses "Edit text", so it joined the payload on its own in 2026-09-18's
    # staging and would have shipped unnoticed.
    # ⚠⚠ THIRD time a companion of a withheld file has crept in this way. NEVER_SHIP works,
    # but it only withholds what it is told about: a *new* file that merely relates to the
    # manual is ordinary ADDED content sitting at the root of Ziggurat/, and the WITHHELD
    # report does not list it either, because that section covers withheld CHANGED files.
    # Read the root-level staged listing every release -- 13 entries, a wrong one is obvious
    # there and invisible everywhere else.
    "manual_text.json",
    # ⚠ The updater's version marker is written by the INSTALLER at ssPostInstall, from its
    # own AppVer. Staging a copy would ship whatever version the last --stage happened to
    # catch, and the updater would then compare GitHub against a stale number and either nag
    # forever or claim to be current when it is not.
    "version.txt",
}

# Files that are never mod content, wherever they sit.
IGNORE_GLOBS = [
    "*.pre-*",             # snapshot layers next to their target
    "*.orig", "*.bak", "*.tmp", "*.log",
    "*.pyc",
    "goglog.ini", "*_LastDirs.ini", "*.ini",
    "vanilla_out.txt",
    "CLAUDE.md", "rule.md", "aow emails.txt",
    "AoWEPACK.dll",        # stale duplicate of the .dpl, not loaded
    "webcache.zip",
    "*.hsm", "*.HSM",      # maps: shipped separately, not part of the rules mod
    "*.sav", "*.SAV",
    # GOG install furniture -- absent from the hashdb because the installer writes it,
    # but it is the vanilla install's, not the mod's.
    "unins000.*", "goggame-*", "*.ico", "*.lnk", "EULA.txt", "Readme.txt",
    "regs.cmd", "QuickStart.pdf",
    # loose tools and archives that live in the game tree but are not game content
    "mld_conv.exe", "AoWxBard.exe", "*.zip", "*.7z", "*.exe.config",
]


def parse_hashdb(path):
    raw = zipfile.ZipFile(path).read(os.path.basename(path))
    hsize, _ver, count = struct.unpack("<3I", raw[:12])
    out = {}
    for i in range(count):
        rec = raw[hsize + i * 1056: hsize + (i + 1) * 1056]
        name = rec[:1024].split(b"\x00")[0].decode("cp1252")
        out[name.replace("\\", "/").lower()] = (name.replace("\\", "/"),
                                                rec[1024:1056].decode("ascii").lower())
    return out


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ignored(rel):
    parts = rel.split("/")
    if rel in NEVER_SHIP or parts[-1] in NEVER_SHIP:
        return True
    if any(p in ALWAYS_SHIP_DIRS for p in parts[:-1]):
        return False
    if any(p in IGNORE_DIRS for p in parts[:-1]):
        return True
    return any(fnmatch.fnmatch(parts[-1], g) for g in IGNORE_GLOBS)


def walk_game():
    for root, dirs, files in os.walk(GAME):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            full = os.path.join(root, f)
            yield os.path.relpath(full, GAME).replace("\\", "/"), full


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="list every ADDED file")
    ap.add_argument("--json", metavar="FILE", help="write the manifest as JSON")
    ap.add_argument("--stage", metavar="DIR", help="copy CHANGED + ADDED into DIR")
    args = ap.parse_args()

    if not os.path.exists(HASHDB):
        sys.exit("no hashdb at %s" % HASHDB)
    db = parse_hashdb(HASHDB)
    print("hashdb: %d pristine-install files" % len(db))

    changed, same, added, missing, withheld = [], [], [], [], []
    seen = set()

    for rel, full in walk_game():
        key = rel.lower()
        seen.add(key)
        if key in db:
            try:
                differs = md5(full) != db[key][1]
            except OSError as e:
                print("  ! unreadable %s: %s" % (rel, e))
                continue
            if not differs:
                same.append(rel)
            elif rel in NEVER_SHIP or rel.split("/")[-1] in NEVER_SHIP:
                withheld.append(rel)
            else:
                changed.append(rel)
        elif not ignored(rel):
            added.append(rel)

    for key, (orig, _h) in db.items():
        if key not in seen and not ignored(orig):
            missing.append(orig)

    changed.sort(); added.sort(); missing.sort()

    def group(paths):
        g = {}
        for p in paths:
            g.setdefault(os.path.dirname(p) or "<root>", []).append(p)
        return g

    print("\n=== CHANGED (%d) -- differ from the GOG install ===" % len(changed))
    for d, ps in sorted(group(changed).items()):
        print("  %s/" % d)
        for p in ps:
            print("      %s  (%s)" % (os.path.basename(p),
                                      fmt(os.path.getsize(os.path.join(GAME, p)))))

    print("\n=== MISSING (%d) -- in the install, gone from disk ===" % len(missing))
    for p in missing:
        print("  %s" % p)

    print("\n=== ADDED (%d) -- new files, after filtering ===" % len(added))
    for d, ps in sorted(group(added).items()):
        print("  %s/  (%d)" % (d, len(ps)))
        if args.all or len(ps) <= 12:
            for p in ps:
                print("      %s  (%s)" % (os.path.basename(p),
                                          fmt(os.path.getsize(os.path.join(GAME, p)))))

    print("\n=== WITHHELD (%d) -- patched, deliberately not shipped ===" % len(withheld))
    for p in withheld:
        print("  %s" % p)

    print("\nSAME: %d files byte-identical to the GOG install" % len(same))
    total = sum(os.path.getsize(os.path.join(GAME, p)) for p in changed + added)
    print("CHANGED + ADDED payload: %s" % fmt(total))

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"changed": changed, "added": added,
                       "missing": missing, "same_count": len(same)}, f, indent=2)
        print("wrote %s" % args.json)

    if args.stage:
        for p in changed + added:
            dst = os.path.join(args.stage, p.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(GAME, p), dst)
        print("staged %d files into %s" % (len(changed) + len(added), args.stage))


def fmt(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return "%.1f %s" % (n, u)
        n /= 1024.0


if __name__ == "__main__":
    main()
