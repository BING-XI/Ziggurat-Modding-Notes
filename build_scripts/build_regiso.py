#!/usr/bin/env python3
r"""
REGISTRY ISOLATION  --  give Ziggurat its own per-user settings tree.

    HKCU\Software\Triumph Studios\Age of Wonders     (vanilla, shared by every mod)
 -> HKCU\Software\Triumph Studios\Age of Wonders Z   (ours alone)

WHY
  The engine's data root is seeded from  General\"Startup Directory"  in that key
  (AoWReg.TAoWRegistry.GetStartupDirectory; the value name lives at file 0x4674 of
  AoWEPACK.dpl, and AoWSetup's Developer tab is what writes it).  Two installs that
  share the key share one data root: run vanilla's AoWSetup, then launch Ziggurat,
  and Ziggurat reads vanilla's folder.  Video mode, hotkeys, player name and the
  cheat flags collide the same way.  Isolating the key makes a Ziggurat install
  coexist with a vanilla install -- and with Inioch's AoWx, which already sits on
  its own "Age of Wonders X" key (Modding Resources/Inioch/share3/Registry Isolation.md).

  Nothing else is needed for coexistence: the packages resolve from the exe's own
  directory, so two install FOLDERS are otherwise independent.  This is why neither
  we nor AoWx rename any game file -- see Zig notes/11-engine-internals.md.

MECHANISM -- Inioch's lengthen-a-Delphi-const-in-place trick, no cave, no hook
  A Delphi 3 AnsiString constant is laid out

      [refcount = -1 : dword] [length : dword] [chars ...] [NUL] [pad 00 ...]

  and these particular constants carry 2-3 spare 00 bytes after the terminator.
  So the string can gain characters without moving: bump the length dword, write
  the extra chars into the pad.  The string's START address never changes, so every
  `mov edx,<addr>` that loads it keeps working and is NOT touched.

  Footprint, per site:  old 41 chars + NUL + 2 pad = 44 bytes
                        new 43 chars + NUL         = 44 bytes    <- exact fit
  The \General copy has 48 + NUL + 3 pad = 52 against 50 + NUL = 51, one byte spare.
  ==> the ceiling is 43 characters.  " Z" is what fits; "Ziggurat" appended does not
  (50 chars).  Rewriting the whole path shorter would also fit but changes more bytes
  for no gain.

SITES -- all nine verified against the live binaries 2026-09-09, and the six in
AoWEPACK.dpl verified byte-identical to Modding Resources/AoWEPACK_original_backup.dpl

  AoWEPACK.dpl   (VA = file + 0x55700C00)      len   the mov edx that loads it
    0x002FEC / VA 0x55703BEC                    41   0x55703B60
    0x0030DC / VA 0x55703CDC                    41   0x55703C50
    0x0031D4 / VA 0x55703DD4                    41   0x55703D40
    0x0032C8 / VA 0x55703EC8                    41   0x55703E38
    0x0035BC / VA 0x557041BC                    41   0x5570410D
    0x003ABC / VA 0x557046BC  (...\General)     48   0x55704670

  AoWSetup.exe   (base 0x400000)
    0x066480 / VA 0x00466480                    41
    0x066570 / VA 0x00466570                    41
    0x066668 / VA 0x00466668                    41

  AoWSetup.exe is OURS, not Inioch's: his Registry Isolation.md states the string
  exists only in AoWEPACK and that the game exe and both editors route through
  TAoWRegistry.  The first half is wrong here -- AoWSetup statically links its own
  copies of the rw* helpers.  The second half holds: AoW.exe, AoWCompat.exe,
  AoWEd.exe and AoWDevEd.exe carry NO copy of the path (scanned, zero hits), so the
  two files below are the whole patch.  Miss AoWSetup and the setup program writes
  the startup dir and video mode into the OLD tree while the game reads the new one,
  and settings silently stop sticking.

  Launcher.exe has its own unrelated key (Software\Triumph Studios\AoWLauncher) and
  is left alone.  So are the .hsm/AOWMAP file associations that
  TAoWRegistry.AssociateAoWMap writes into HKCU\Software\Classes -- per-user,
  last-run-wins, cosmetic.

SETTINGS ARE NOT MIGRATED BY THIS SCRIPT.  Seed the new tree once, before playing:

    reg copy "HKCU\Software\Triumph Studios\Age of Wonders" \
             "HKCU\Software\Triumph Studios\Age of Wonders Z" /s /f

  Non-destructive -- it creates the new key and leaves the old one untouched.
  Skip it and the game just builds the tree with defaults on first run (which means
  re-picking the video mode in AoWSetup).

RE-TUNING
  SUFFIX below is the only knob.  It must keep the total at or under 43 characters,
  i.e. at most 2 bytes.  The script verifies the zero-run at every site before it
  writes, so a longer suffix aborts rather than eating the next constant.

--undo is surgical: it rewrites the nine constants back to the vanilla 41/48-char
form and re-zeroes the pad.  Nothing else in either file is touched, so it composes
with every other patch.

STATUS: applied 2026-09-09, UNTESTED -- see Zig notes/11-engine-internals.md for the
in-game checklist.

Needs no third-party packages.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")

SUFFIX = b" Z"                       # <= 2 bytes; see RE-TUNING above

VANILLA = b"\\Software\\Triumph Studios\\Age of Wonders"
GENERAL = b"\\General"
OLD_BARE = VANILLA + b"\\"                       # 41
NEW_BARE = VANILLA + SUFFIX + b"\\"              # 43
OLD_GEN = VANILLA + b"\\" + b"General"           # 48
NEW_GEN = VANILLA + SUFFIX + b"\\" + b"General"  # 50

# file -> (expected bare-copy offsets, expected \General offsets)
TARGETS = {
    "AoWEPACK.dpl": ([0x002FEC, 0x0030DC, 0x0031D4, 0x0032C8, 0x0035BC], [0x003ABC]),
    "AoWSetup.exe": ([0x066480, 0x066570, 0x066668], []),
}

LOCKERS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd", "AoWSetup")


def kill_running():
    """The editor and AoWSetup lock these files; CLAUDE.md grants standing leave."""
    names = "|".join(LOCKERS)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } "
         "| Stop-Process -Force" % names],
        capture_output=True)


def find_sites(data):
    """Locate every registry-path constant, in either the vanilla or patched state.

    Returns [(chars_off, is_general, patched)] sorted by offset.  A site is only
    accepted when the Delphi header is intact -- refcount -1 and a length dword that
    matches the string actually present -- so a stray copy of the text in a data
    blob cannot be mistaken for a constant.
    """
    out = []
    i = 0
    while True:
        i = data.find(VANILLA, i)
        if i < 0:
            break
        rc, ln = struct.unpack("<iI", data[i - 8:i])
        if rc == -1:
            for s, gen, patched in ((OLD_GEN, True, False), (NEW_GEN, True, True),
                                    (OLD_BARE, False, False), (NEW_BARE, False, True)):
                if ln == len(s) and data[i:i + ln] == s and data[i + ln] == 0:
                    out.append((i, gen, patched))
                    break
        i += 1
    return out


def check(path, verbose=True):
    """Report state; returns (data, sites, n_patched, n_vanilla) or exits on mismatch."""
    name = os.path.basename(path)
    exp_bare, exp_gen = TARGETS[name]
    data = bytearray(open(path, "rb").read())
    sites = find_sites(data)

    got_bare = sorted(o for o, g, _ in sites if not g)
    got_gen = sorted(o for o, g, _ in sites if g)
    if got_bare != sorted(exp_bare) or got_gen != sorted(exp_gen):
        print("  !! %s: site layout does not match the record" % name)
        print("     expected bare %s general %s"
              % ([hex(o) for o in exp_bare], [hex(o) for o in exp_gen]))
        print("     found    bare %s general %s"
              % ([hex(o) for o in got_bare], [hex(o) for o in got_gen]))
        sys.exit(2)

    n_patched = sum(1 for _, _, p in sites if p)
    if verbose:
        for off, gen, patched in sites:
            ln = len(data[off:data.index(b"\x00", off)])
            print("     0x%06X  len %2d  %-6s  %s"
                  % (off, ln, "PATCHED" if patched else "vanilla",
                     bytes(data[off:off + ln]).decode()))
    return data, sites, n_patched, len(sites) - n_patched


def rewrite(data, off, gen, to_patched):
    """Rewrite one constant in place.  Aborts unless the trailing zero-run is big
    enough to hold the new chars + NUL -- the check that keeps a longer SUFFIX from
    silently overrunning into the next constant."""
    old = (OLD_GEN if gen else OLD_BARE)
    new = (NEW_GEN if gen else NEW_BARE)
    cur, want = (old, new) if to_patched else (new, old)

    assert data[off:off + len(cur)] == cur, "site 0x%06X: unexpected current bytes" % off
    # footprint currently owned by this constant: chars + NUL + pad
    end = off + len(cur)
    pad = 0
    while data[end + pad] == 0:
        pad += 1
    room = len(cur) + pad
    if len(want) + 1 > room:
        print("  !! site 0x%06X: need %d bytes, constant owns %d -- SUFFIX too long"
              % (off, len(want) + 1, room))
        sys.exit(2)

    struct.pack_into("<I", data, off - 4, len(want))
    data[off:off + room] = want + b"\x00" * (room - len(want))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true", help="surgical revert to vanilla")
    args = ap.parse_args()

    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")
    if len(NEW_BARE) > 43:
        ap.error("SUFFIX %r makes the path %d chars; the pad allows 43"
                 % (SUFFIX, len(NEW_BARE)))

    to_patched = not args.undo
    want = NEW_BARE if to_patched else OLD_BARE
    print("target tree: HKCU%s\n" % want.decode().rstrip("\\"))

    plan = []
    for name in TARGETS:
        path = os.path.join(GAME, name)
        if not os.path.isfile(path):
            print("  !! missing: %s" % path)
            sys.exit(2)
        print("  %s" % name)
        data, sites, n_patched, n_vanilla = check(path)
        todo = [(o, g) for o, g, p in sites if p != to_patched]
        print("     -> %d patched, %d vanilla, %d to change\n"
              % (n_patched, n_vanilla, len(todo)))
        plan.append((path, data, todo))

    if not any(todo for _, _, todo in plan):
        print("nothing to do -- already in the requested state.")
        return
    if not (args.apply or args.undo):
        print("dry run.  Re-run with --apply (or --undo) to write.")
        return

    kill_running()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for path, data, todo in plan:
        if not todo:
            continue
        name = os.path.basename(path)
        backup = os.path.join(BACKUP_DIR, name + ".pre-regiso")
        if args.apply and not os.path.exists(backup):
            shutil.copyfile(path, backup)
            print("  backup -> backups\\%s" % os.path.basename(backup))
        for off, gen in todo:
            rewrite(data, off, gen, to_patched)
        with open(path, "wb") as f:
            f.write(data)
        print("  %s: %d constants rewritten" % (name, len(todo)))

    print("\nre-verifying live files:")
    for name in TARGETS:
        print("  %s" % name)
        check(os.path.join(GAME, name))

    if to_patched:
        key = "HKCU\\Software\\Triumph Studios"
        print("\nSeed the new tree once (non-destructive -- the old key is untouched):")
        print('  reg copy "%s\\Age of Wonders" "%s\\%s" /s /f'
              % (key, key, want.decode().rstrip("\\").rsplit("\\", 1)[-1]))


if __name__ == "__main__":
    main()
