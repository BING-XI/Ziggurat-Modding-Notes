#!/usr/bin/env python3
r"""The release date as the version number -- `Dict/ResStr.mld` + `Dict/ResStr.txt`.

    python build_scripts/build_version_stamp.py 2026.09.28            # dry run
    python build_scripts/build_version_stamp.py 2026.09.28 --apply
    python build_scripts/build_version_stamp.py --check 2026.09.28    # exit 1 unless stamped so
    python build_scripts/build_version_stamp.py --undo                # back to "Ziggurat %s"

Owner ruling 2026-09-28: the version number is the release date, the same `YYYY.MM.DD` string as
the installer's AppVer and the release tag. Run it in §13.1a before staging;
`installer/build_installer.py` refuses to build when the STAGED dictionary carries another date.

WHERE THE VERSION TEXT COMES FROM
  Both screens that show a version format the resourcestring `AoWE.VersionXRStr` ("Version: %s"),
  translated through this dictionary, whose [US] slot Ziggurat set to "Version: Ziggurat %s":
    * game title screen   TTitleScene.TitleSceneCreate (AoWz.exe 0x41A35B) passes
                          TAoWEngine.GetVersionStr = "M.mm.bbbb" from the engine dword.
    * editor About box    TAboutDlg.FormCreate -> 0x42800C (AoWzEd.exe) passes a HARD-CODED
                          IntToStr(1) + "." + IntToStr(0x24) + "." + TAoWEngine.GetBuildNumber,
                          i.e. "1.36.<build>" whatever the engine says.
  So the two screens disagreed (live: title "20.21.0078", About "1.36.78"). Writing the date into
  the translation itself, with no %s, makes both read "Version: Ziggurat <date>" -- AoWE.Format
  ignores the surplus argument. No binary changes.

THE ENGINE NUMBER IS LEFT ALONE
  TAoWEngine.Create (AoWEPACK 0x55797C13) calls SetVersion(major, minor, build) -> dword
  [engine+0x58] = major<<24 | minor<<16 | build (clamped 99 / 99 / 9999). Vanilla 1.36.53; live
  Ziggurat 20.21.78, set by no script in this tree. Its only other reader is the multiplayer
  handshake, TSetupControl.ValidateCompatibleVersion (0x557DFCAC), which compares the top 16 bits
  (major.minor). Leaving it fixed keeps every Ziggurat release able to join every other; a date
  there would not fit the clamps as a readable number anyway. Saves and maps do not store it.

The other languages' slots ([DE] [FR] [IT] [ES]) keep "Version: %s" and still show the engine
number; the mod ships English only.

Revert: --undo restores "Version: Ziggurat %s" in both files. No snapshot is taken.
Roll pattern: none -- no randomness.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_resstr_names as R   # noqa: E402  (walk / find / slot helpers, MLD / TXT paths)

NATIVE = "Version: %s"
TEMPLATE = "Version: Ziggurat %s"          # pre-stamp text, and what --undo restores
STAMP = "Version: Ziggurat {}"
DATE = re.compile(r"\d{4}\.\d{2}\.\d{2}")


def read(game=None):
    mld = os.path.join(game, "Dict", "ResStr.mld") if game else R.MLD
    txt = os.path.join(game, "Dict", "ResStr.txt") if game else R.TXT
    d = bytearray(open(mld, "rb").read())
    lines = open(txt, encoding="latin1", newline="").read().split("\n")
    R.check_invariants(d, mld)
    _s, fields = R.find(R.walk(d)[0], d, NATIVE)
    j = R.txt_slot(lines, NATIVE)
    cur, tcur = R.get_slot(d, fields), R.txt_get(lines, j)
    if cur != tcur:
        sys.exit(f"ABORT: {NATIVE!r} out of sync -- .mld {cur!r}, .txt {tcur!r}")
    return mld, txt, d, lines, fields, j, cur


def stamped_version(game=None):
    """-> the date in the [US] slot, or None when it is not stamped."""
    cur = read(game)[-1]
    m = re.fullmatch(r"Version: Ziggurat (\d{4}\.\d{2}\.\d{2})", cur)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--check", metavar="VER")
    ap.add_argument("--game", help="read another tree (e.g. the staged payload) -- --check only")
    a = ap.parse_args()

    if a.check:
        got = stamped_version(a.game)
        print(f"stamped: {got}")
        sys.exit(0 if got == a.check else 1)

    if a.undo:
        new = TEMPLATE
    else:
        if not a.version or not DATE.fullmatch(a.version):
            sys.exit("usage: build_version_stamp.py YYYY.MM.DD [--apply] | --undo | --check VER")
        new = STAMP.format(a.version)

    mld, txt, d, lines, fields, j, cur = read()
    ok_before = cur == TEMPLATE or re.fullmatch(r"Version: Ziggurat \d{4}\.\d{2}\.\d{2}", cur)
    if not ok_before:
        sys.exit(f"ABORT: [US] of {NATIVE!r} is {cur!r} -- neither the template nor a stamp")
    print(f"[US] {NATIVE!r}: {cur!r} -> {new!r}")
    if cur == new:
        print("already there -- no-op")
        return
    d = R.set_slot(d, fields, new)
    R.check_invariants(d, "after")
    R.txt_set(lines, j, new)
    if not (a.apply or a.undo):
        print("dry run -- re-run with --apply")
        return
    try:
        open(mld, "wb").write(bytes(d))
        open(txt, "w", encoding="latin1", newline="").write("\n".join(lines))
    except PermissionError:
        sys.exit("ERROR: Dict/ResStr.* is locked -- close the AoW binaries")
    print("written: Dict/ResStr.mld + Dict/ResStr.txt")


if __name__ == "__main__":
    main()
