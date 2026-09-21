#!/usr/bin/env python3
r"""
AoWSetup: point it at AoWz.exe instead of aow.exe  --  Ziggurat\AoWSetup.exe ONLY.

THE SYMPTOM
  `Ziggurat\AoWSetup.exe` shows only Install/Exit -- no Play!, no Settings, no Editor --
  even though the game is plainly installed around it.

THE CAUSE, and why the earlier '.' fallback does not cover it
  `TLoaderForm.IsInstalled @0x00468618` reads `General\Root Directory` (now
  `…\Ziggurat\`, via the isolated `Age of Wonders Z` key) and tests
  `FileExists(root + '\aow.exe')`.  The mod's exe was renamed to `AoWz.exe` on
  2026-09-09, so `Ziggurat\aow.exe` does not exist and the test fails.

  ⚠ `build_aowsetup_installcheck.py`'s `'.'` fallback does NOT help here: it substitutes
  only when the registry read comes back **nil**, and here the read succeeds and returns a
  perfectly good directory. The two patches are independent and both are wanted -- that one
  covers "no registry", this one covers "the file is called something else".

THE PATCH -- two Delphi string constants, in place
  Both are `\aow.exe`, len 8, refcount -1, each with 4 spare `00` bytes after the
  terminator, so `\AoWz.exe` (9) fits with room to spare (needs 10 of the 13 owned bytes):

      file 0x067AA0 / VA 0x004686A0   the INSTALL CHECK   (loaded at 0x00468652)
      file 0x067CE0 / VA 0x004688E0   the PLAY! BUTTON    (loaded at 0x00468864)

  Both must move together. Fixing only the check would give a full menu whose Play! button
  then launches a file that is not there. `\aowed.exe` @0x004689CC is left alone -- the
  Editor button is a separate question (`Ziggurat\AoWzEd.exe`), not this patch.

  Same lengthen-in-place idiom as `build_regiso.py`: bump the length dword, write the new
  characters over the terminator and pad. The string's start address never moves, so the
  `mov edx,<addr>` load sites are untouched.

⚠ The ROOT `AoWSetup.exe` is VANILLA and must keep pointing at `\aow.exe` -- it configures
the vanilla install, whose exe really is called that. This script only ever touches the
copy in `Ziggurat\`.

STATUS: applied 2026-09-09, UNTESTED (the owner has not reopened setup).

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
EXE = "AoWSetup.exe"
BACKUP = os.path.join(BACKUP_DIR, EXE + ".pre-exename")

BS = chr(92)
OLD = (BS + "aow.exe").encode()          # 8
NEW = (BS + "AoWz.exe").encode()         # 9
SITES = [(0x067AA0, "install check"), (0x067CE0, "Play! button")]


def read(path):
    return bytearray(open(path, "rb").read())


def state(d):
    """(n_old, n_new) at the recorded sites; anything else is a layout surprise."""
    old = new = 0
    for off, _ in SITES:
        ln = struct.unpack_from("<I", d, off - 4)[0]
        cur = bytes(d[off:off + ln])
        if ln == len(OLD) and cur == OLD:
            old += 1
        elif ln == len(NEW) and cur == NEW:
            new += 1
    return old, new


def rewrite(d, off, to_new):
    want, other = (NEW, OLD) if to_new else (OLD, NEW)
    ln = struct.unpack_from("<I", d, off - 4)[0]
    cur = bytes(d[off:off + ln])
    if cur == want:
        return False
    if cur != other:
        sys.exit("!! 0x%06X holds %r -- neither form; stop" % (off, cur))
    # the constant owns chars + NUL + pad; make sure the new one still fits
    end, pad = off + ln, 0
    while d[end + pad] == 0:
        pad += 1
    if len(want) + 1 > ln + pad:
        sys.exit("!! 0x%06X: need %d bytes, constant owns %d" % (off, len(want) + 1, ln + pad))
    struct.pack_into("<I", d, off - 4, len(want))
    d[off:off + ln + pad] = want + b"\x00" * (ln + pad - len(want))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true", help="back to \\aow.exe")
    args = ap.parse_args()
    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")

    path = os.path.join(GAME, EXE)
    if not os.path.isfile(path):
        sys.exit("missing %s" % path)
    d = read(path)
    old, new = state(d)
    print("%s: %d site(s) on %s, %d on %s"
          % (EXE, old, OLD.decode(), new, NEW.decode()))
    for off, what in SITES:
        ln = struct.unpack_from("<I", d, off - 4)[0]
        print("   0x%06X  %-14s len %d  %r" % (off, what, ln, bytes(d[off:off + ln]).decode()))

    to_new = not args.undo
    if (new == len(SITES)) == to_new:
        print("\nnothing to do -- already in the requested state.")
        return
    if not (args.apply or args.undo):
        print("\ndry run.  Re-run with --apply (or --undo) to write.")
        return

    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object { $_.ProcessName -eq 'AoWSetup' } "
                    "| Stop-Process -Force"], capture_output=True)
    if to_new:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.exists(BACKUP):
            shutil.copyfile(path, BACKUP)
            print("  backup -> backups\\%s" % os.path.basename(BACKUP))
    n = sum(rewrite(d, off, to_new) for off, _ in SITES)
    open(path, "wb").write(d)
    print("  %d constant(s) rewritten" % n)

    d2 = read(path)
    for off, what in SITES:
        ln = struct.unpack_from("<I", d2, off - 4)[0]
        print("  verify 0x%06X %-14s %r" % (off, what, bytes(d2[off:off + ln]).decode()))


if __name__ == "__main__":
    main()
