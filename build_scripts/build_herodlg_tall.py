#!/usr/bin/env python3
"""build_herodlg_tall.py -- Hero level-up dialog: double the height, extra space to the ability lists.

Vanilla `THeroUpgradeDlg` (RCDATA resource 'THEROUPGRADEDLG' in AoW.exe) is a 407x432 TAOWWindow.
The two ability lists (SelectedAbilities / AvailableAbilities + their cost columns) are 107 px tall
(ItemHeight 17 -> ~6 visible rows), so assigning upgrades is a scroll-fest. The layout lives
ENTIRELY in the DFM stream -- the unit's code has no geometry constants (checked: every imm-432 hit
in AoWHeroUpgradeDlg's code range 0x4458B0..0x447528 is a `[reg+0x1B0]` field displacement).

The patch edits the DFM stream in place (the next resource starts right after, so it must not grow):

  Dlg.WinHeight                              432 -> TARGET_H   (864 default = exactly 2x)
  UpgradePnl.WinHeight                       150 -> +extra     (bottom-anchored panel holding the lists)
  4 list boxes + 2 scrollbars    WinHeight   107 -> +extra     (539 px -> 31 rows at the default)
  AddAbilityBtn / RemoveBtn      WinTop      125 -> +extra     (UpgradePnl-relative, under the lists)
  Done / CancelBtn / BCeltL / CeltM / CeltL / CeltR
                                 WinTop      395 -> +extra     (window-bottom button/knotwork row)

Every moved control is also bottom-anchored via its Alignment.* props and the dialog itself is
screen-centered (awCenter/ahCenter), so the stored geometry and the anchor pass agree whichever the
runtime actually uses. The scrollbars have VanishWhenFull=True -> they disappear once a list fits.

Byte budget: 8 values grow Int8->Int16 (+8 bytes); funded by deleting the root data-module's four
designer-only props Left/Top/Height/Width (-33 bytes; absent props just keep their defaults --
deleting is always safe, it's UNKNOWN props that raise EReadError). Net -25 bytes, zero-padded;
the DFM reader stops at the root terminator, so the pad is never read (dfm_edit calls this state
"CLEAN + zero pad").

State handling: the pristine slot is recognised by SHA1; a patched slot (any height) is recognised
by inverse-transforming it and SHA1-checking the result. So the script can re-tune to a new
--height in place -- from any of its own states, touching no backup. The canonical mod exes
`Ziggurat/AoWz.exe` and `Ziggurat/AoWzCompat.exe` (names from `zigexe.py`) are patched in lockstep
(their slots are byte-identical).

  (no args)          verify: report the state of both exes
  --apply            patch both exes (first run makes <exe>.pre-herodlgtall backups)
  --apply --height N re-tune to dialog height N (433..2400; default 864)
  --undo             surgical restore of the pristine DFM slot (no backup file involved)

NB: at 864 the dialog needs a >=900-px-tall game resolution to fit. The editor AoWDevEd.exe has its
own separate hero-upgrade dialog and is NOT touched by this script.
"""
import argparse
import hashlib
import os
import struct
import shutil
import subprocess
import sys
import time

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dfm_edit
import zigexe                                      # mod binary names

EXES = list(zigexe.EXES)                           # AoWz.exe + AoWzCompat.exe
BACKUP_SUFFIX = ".pre-herodlgtall"
BACKUP_DIR = os.path.join(GAME, "backups")         # ⚠ never the game root -- rule 2026-09-03
RESNAME = "THEROUPGRADEDLG"
BASE_H = 432
DEFAULT_H = 864
ORIG_SIZE = 0xCEFB
ORIG_SHA1 = "66435ee7a6642236a0aedcd9472511a10af2a687"
# The root's four designer-only props (Left=257, Top=1, Height=643, Width=871), verbatim.
# Deleted by the patch to pay for the Int8->Int16 growth; re-inserted by --undo.
ROOT_PROPS = bytes.fromhex(
    "044c65667403010103546f70020106486569676874038302055769647468036703")

# (path suffix, property, vanilla value); patched value = vanilla + (target_h - BASE_H)
GEOM = [
    ("/Dlg",                    "WinHeight", 432),
    ("/UpgradePnl",             "WinHeight", 150),
    ("/AvailableAbilities",     "WinHeight", 107),
    ("/AvailableAbilitiesSB",   "WinHeight", 107),
    ("/AvailableAbilitiesCost", "WinHeight", 107),
    ("/SelectedAbilities",      "WinHeight", 107),
    ("/SelectedAbilitiesSB",    "WinHeight", 107),
    ("/SelectedAbilitiesCost",  "WinHeight", 107),
    ("/AddAbilityBtn",          "WinTop",    125),
    ("/RemoveBtn",              "WinTop",    125),
    ("/Done",                   "WinTop",    395),
    ("/CancelBtn",              "WinTop",    395),
    ("/BCeltL",                 "WinTop",    395),
    ("/CeltM",                  "WinTop",    395),
    ("/CeltL",                  "WinTop",    395),
    ("/CeltR",                  "WinTop",    395),
]


def locate_dfm(data):
    """-> (file offset, size) of the THEROUPGRADEDLG RCDATA payload.

    Full PE walk, nothing hardcoded: the RCDATA name table in these exes has already been
    repointed outside .rsrc once (combat-log clone), and directory offsets are rsrc-RVA-relative,
    so every hop is translated through the section table."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    rsrc_rva = struct.unpack_from("<I", data, opt + 112)[0]  # DataDirectory[2]
    secs = []
    soff = opt + optsize
    for i in range(nsec):
        s = soff + 40 * i
        vsz, va = struct.unpack_from("<II", data, s + 8)
        rsz, raw = struct.unpack_from("<II", data, s + 16)
        secs.append((va, vsz, raw, rsz))

    def rva2off(rva):
        for va, vsz, raw, rsz in secs:
            if va <= rva < va + max(vsz, rsz):
                return raw + (rva - va)
        raise ValueError("RVA 0x%X not in any section" % rva)

    def entries(diroff):
        nn = struct.unpack_from("<H", data, diroff + 12)[0]
        ni = struct.unpack_from("<H", data, diroff + 14)[0]
        out = []
        for i in range(nn + ni):
            e = diroff + 16 + 8 * i
            name, val = struct.unpack_from("<II", data, e)
            if name & 0x80000000:
                noff = rva2off(rsrc_rva + (name & 0x7FFFFFFF))
                ln = struct.unpack_from("<H", data, noff)[0]
                nm = data[noff + 2:noff + 2 + 2 * ln].decode("utf-16le")
            else:
                nm = "#%d" % name
            out.append((nm, val))
        return out

    root = entries(rva2off(rsrc_rva))
    rc = next(v for n, v in root if n == "#10")                       # RT_RCDATA
    names = entries(rva2off(rsrc_rva + (rc & 0x7FFFFFFF)))
    ent = next(v for n, v in names if n == RESNAME)
    langs = entries(rva2off(rsrc_rva + (ent & 0x7FFFFFFF)))
    de = rva2off(rsrc_rva + (langs[0][1] & 0x7FFFFFFF))               # data entry
    drva, dsize = struct.unpack_from("<II", data, de)
    return rva2off(drva), dsize


def enc_int(name, val):
    """Property bytes: shortstring name + smallest Delphi integer encoding (matches TWriter)."""
    if -128 <= val <= 127:
        return dfm_edit.shortstr(name) + bytes([dfm_edit.I8]) + struct.pack("<b", val)
    if -32768 <= val <= 32767:
        return dfm_edit.shortstr(name) + bytes([dfm_edit.I16]) + struct.pack("<h", val)
    return dfm_edit.shortstr(name) + bytes([dfm_edit.I32]) + struct.pack("<i", val)


def apply_edits(blob, edits):
    """edits = [(start, end, replacement)]; start==end inserts. Non-overlapping."""
    out, pos = bytearray(), 0
    for s, e, nb in sorted(edits):
        assert pos <= s <= e, "overlapping edits"
        out += blob[pos:s]
        out += nb
        pos = e
    out += blob[pos:]
    return bytes(out)


def get_int(w, suffix, prop):
    hits = [p for p in w.props if p[0].endswith(suffix) and p[1] == prop]
    assert len(hits) == 1, "%s.%s: %d hits" % (suffix, prop, len(hits))
    return hits[0][5]


def transform(orig, target_h):
    """pristine slot bytes -> patched slot bytes (same total length, zero-padded)."""
    assert hashlib.sha1(orig).hexdigest() == ORIG_SHA1
    extra = target_h - BASE_H
    w = dfm_edit.walk(orig)
    edits = []
    for prop in ("Left", "Top", "Height", "Width"):        # root designer props: delete
        s, e = dfm_edit.find(w, "/HeroUpgradeDlg", prop)
        edits.append((s, e, b""))
    for suffix, prop, van in GEOM:
        s, e = dfm_edit.find(w, suffix, prop)
        edits.append((s, e, enc_int(prop, van + extra)))
    out = apply_edits(orig[:w.consumed], edits)
    assert len(out) <= ORIG_SIZE, "stream grew -- must never happen"
    out += b"\0" * (ORIG_SIZE - len(out))
    # verify: reparses cleanly, values took, root props gone
    w2 = dfm_edit.walk(out)
    assert all(b == 0 for b in out[w2.consumed:]), "non-zero tail after transform"
    for suffix, prop, van in GEOM:
        assert get_int(w2, suffix, prop) == van + extra
    assert not [p for p in w2.props if p[0] == "/HeroUpgradeDlg" and p[1] == "Left"]
    return out


def untransform(slot):
    """patched slot bytes -> pristine candidate (caller must SHA1-verify). Raises on desync."""
    w = dfm_edit.walk(slot)
    edits = []
    root_end = next(p[4] for p in w.props if p[0] == "/HeroUpgradeDlg" and p[1] == "$class")
    edits.append((root_end, root_end, ROOT_PROPS))
    for suffix, prop, van in GEOM:
        s, e = dfm_edit.find(w, suffix, prop)
        edits.append((s, e, enc_int(prop, van)))
    out = apply_edits(slot[:w.consumed], edits)
    assert len(out) == ORIG_SIZE, "untransform length %#x != %#x" % (len(out), ORIG_SIZE)
    return out


def state_of(slot):
    """-> ('pristine', None) | ('patched', height) | ('unknown', None)"""
    if hashlib.sha1(slot).hexdigest() == ORIG_SHA1:
        return "pristine", None
    try:
        h = get_int(dfm_edit.walk(slot), "/Dlg", "WinHeight")
        if hashlib.sha1(untransform(slot)).hexdigest() == ORIG_SHA1:
            return "patched", h
    except Exception:
        pass
    return "unknown", None


def kill_game():
    # ⚠ the mod exes are AoWz*/AoWzEd since 2026-09-09; killing only the vanilla names
    # left the real lock in place. List lives in zigexe.LOCKING_PROCESSES.
    for p in (n + ".exe" for n in zigexe.LOCKING_PROCESSES):
        subprocess.run(["taskkill", "/F", "/IM", p],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write_slot(path, off, blob):
    try:
        f = open(path, "r+b")
    except PermissionError:
        print("  locked -> killing AoW processes and retrying")
        kill_game()
        time.sleep(1.0)
        f = open(path, "r+b")
    with f:
        f.seek(off)
        f.write(blob)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the patch to both exes")
    ap.add_argument("--undo", action="store_true", help="restore the pristine DFM slot")
    ap.add_argument("--height", type=int, default=DEFAULT_H,
                    help="target dialog height in px (default %d = 2x vanilla)" % DEFAULT_H)
    args = ap.parse_args()
    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")
    if not 433 <= args.height <= 2400:
        ap.error("--height must be in 433..2400 (vanilla is 432)")

    for exe in EXES:
        path = os.path.join(GAME, exe)
        data = open(path, "rb").read()
        foff, size = locate_dfm(data)
        if size != ORIG_SIZE:
            # build_herodlg_columns.py has grown and relocated this resource; it owns the dialog
            # size now (it applies the same height edits plus the category columns).
            print("%s: dialog resource is %#x B, not the vanilla %#x -- this dialog is managed by "
                  "build_herodlg_columns.py now.\n  Use that script's --height/--width instead; "
                  "this one is a no-op here." % (exe, size, ORIG_SIZE))
            continue
        slot = data[foff:foff + size]
        st, h = state_of(slot)
        desc = {"pristine": "vanilla layout (432 px)",
                "patched": "patched to %s px" % h,
                "unknown": "UNKNOWN -- foreign edit?"}[st]
        print("%s: DFM slot @0x%X+0x%X: %s" % (exe, foff, size, desc))

        if st == "unknown":
            if args.apply or args.undo:
                print("  !! not touching an unrecognised slot -- aborting this file")
            continue

        if args.apply:
            if st == "patched" and h == args.height:
                print("  already at %d px -- nothing to do" % args.height)
                continue
            base = slot if st == "pristine" else untransform(slot)
            assert hashlib.sha1(base).hexdigest() == ORIG_SHA1
            new = transform(base, args.height)
            # ⚠ backups/ , never the game root (rule 2026-09-03). --undo is surgical and
            # never reads this file, so relocating it costs nothing.
            bk = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
            if not os.path.exists(bk):
                os.makedirs(BACKUP_DIR, exist_ok=True)
                shutil.copy2(path, bk)
                print("  backup -> %s" % bk)
            write_slot(path, foff, new)
            print("  patched: dialog %d px, lists %d px (~%d rows)"
                  % (args.height, 107 + args.height - BASE_H,
                     (107 + args.height - BASE_H) // 17))
        elif args.undo:
            if st == "pristine":
                print("  already pristine -- nothing to do")
                continue
            orig = untransform(slot)
            assert hashlib.sha1(orig).hexdigest() == ORIG_SHA1
            write_slot(path, foff, orig)
            print("  restored vanilla DFM slot (surgical, no backup touched)")

    if not (args.apply or args.undo):
        print("\ndry run only -- use --apply to patch, --undo to revert")


if __name__ == "__main__":
    main()
