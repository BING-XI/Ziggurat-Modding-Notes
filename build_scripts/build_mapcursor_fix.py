#!/usr/bin/env python3
"""
AoW1 fix: strategic-map cursor/clicks dead on the right (and bottom) of a SMALL map
when the window is wider (taller) than the map — HSEPack.dpl

Root cause (see Cursor_RightSide_LargeWindow_Bug.md): a map smaller than the viewport
is CENTERED by a negative scroll origin ([map+0x80]/[+0x84] = -margin). The real map
then occupies viewport-x in [margin, margin+mapWidth]. But HSEngine.THSMapMouse.Move
@ 0x5560B8F8 rejects the mouse on  viewport-x > GetMaxXhp  (GetMaxXhp @ 0x5560C3EC =
the MAP's pixel width, ignoring the centering offset) and stores the invalid sentinel
0x80000000. That pre-empts the CORRECT, world-based checks in GetXhx/GetYhx/GetXhp/
GetYhp (which do worldX = scroll + mouseX, then column/edge range) — so the map's right
portion (real hexes) reads "no hex" and the cursor freezes + clicks die. Dead-strip
width = the left margin = (viewport-map)/2, growing with window width. Large maps
(>= viewport) are never centered, so no bug.

THE FIX: neuter ONLY Move's two upper-bound rejections so it stores the real mouse
whenever x,y >= 0; the four accessors then validate correctly (identical to how the
map's LEFT side already works). The x>=0 / y>=0 lower-bound checks are LEFT INTACT.

  @ 0x5560B917  jg 0x5560B92D (x > GetMaxXhp) ; 7F 14  -->  90 90 (nop nop)
  @ 0x5560B923  jg 0x5560B92D (y > GetMaxYhp) ; 7F 08  -->  90 90 (nop nop)

In-place, 4 bytes, position-independent (HSEPack.dpl rebases at runtime; no abs refs).
Idempotent, verify-before-write, auto-backup HSEPack.dpl.pre-mapcursor.

Usage:
  python build_mapcursor_fix.py            # verify current state (dry-run)
  python build_mapcursor_fix.py --apply    # apply (backs up first); close all AoW binaries
  python build_mapcursor_fix.py --revert   # !! NOT SURGICAL: whole-file copy from .pre-mapcursor,
                                          #    which is layer 2/3 on HSEPack.dpl -- this DESTROYS the
                                          #    rendergate fix. Prefer writing back the 2 original
                                          #    words by hand (7F 14 @0x5560B917, 7F 08 @0x5560B923).
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
# re_tools is a SIBLING of build_scripts, not a child. `HERE/re_tools` never existed and the
# import died on ModuleNotFoundError before this file could do anything.
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
from pescan import PE
try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    _HAVE_CS = True
except Exception:
    _HAVE_CS = False

# ⚠ ONE dirname short: this resolved to `Modding Resources\`, so TARGET was
# `Modding Resources\HSEPack.dpl` (nonexistent) and BACKUP_DIR was the `Modding Resources\backups\`
# deleted 2026-08-08. Two `..` from build_scripts\ is the project idiom -> <root>\Ziggurat.
GAME   = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(GAME, "HSEPack.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here
BACKUP = os.path.join(BACKUP_DIR, "HSEPack.dpl.pre-mapcursor")

# (VA, original bytes, patched bytes, human note)
EDITS = [
    (0x5560B917, b"\x7F\x14", b"\x90\x90", "jg (x>GetMaxXhp) -> nop nop"),
    (0x5560B923, b"\x7F\x08", b"\x90\x90", "jg (y>GetMaxYhp) -> nop nop"),
]
FUNC_VA, FUNC_LEN = 0x5560B8F8, 0x46          # THSMapMouse.Move, for the disasm review

def _fileoff(pe, va):
    off = pe.rva2off(va - pe.image_base)
    if off is None:
        sys.exit(f"! VA {va:#x} not in any section")
    return off

def _disasm(data, base, label):
    if not _HAVE_CS:
        print(f"  ({label}: install capstone to see disasm)"); return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print(f"  --- {label} ---")
    for i in md.disasm(data, base):
        print(f"  {i.address:08X}: {i.mnemonic:8s} {i.op_str}")

def main():
    apply  = "--apply"  in sys.argv[1:]
    revert = "--revert" in sys.argv[1:]

    if not os.path.exists(TARGET):
        sys.exit(f"! not found: {TARGET}")
    if revert:
        if not os.path.exists(BACKUP):
            sys.exit(f"! no backup to revert from: {BACKUP}")
        shutil.copyfile(BACKUP, TARGET)
        print(f"[reverted] {BACKUP} -> {TARGET}")
        return

    pe = PE(TARGET)
    with open(TARGET, "rb") as f:
        blob = bytearray(f.read())

    print(f"target : {TARGET}")
    states = []
    for va, orig, patch, note in EDITS:
        off = _fileoff(pe, va)
        cur = bytes(blob[off:off+len(orig)])
        if cur == patch:   st = "PATCHED"
        elif cur == orig:  st = "ORIGINAL"
        else:              st = "UNEXPECTED"
        states.append(st)
        print(f"  {va:08X}  {' '.join(f'{b:02X}' for b in cur)}  [{st}]  {note}")

    # disasm review of the whole Move function, before + simulated after
    foff = _fileoff(pe, FUNC_VA)
    win = bytes(blob[foff:foff+FUNC_LEN])
    _disasm(win, FUNC_VA, "current")
    sim = bytearray(win)
    for va, orig, patch, note in EDITS:
        sim[va-FUNC_VA:va-FUNC_VA+len(patch)] = patch
    _disasm(bytes(sim), FUNC_VA, "after patch")

    if "UNEXPECTED" in states:
        sys.exit("! refusing to touch: some bytes are neither original nor our patch "
                 "(wrong file/version, or another patch present).")

    if all(s == "PATCHED" for s in states):
        print("\n[ok] already fully patched.")
        return
    if not apply:
        print("\n[dry-run] would apply the edits above. Re-run with --apply "
              "(close AoW.exe / AoWCompat.exe / AoWDevEd.exe first).")
        return

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True); shutil.copyfile(TARGET, BACKUP); print(f"[backup] {BACKUP}")
    else:
        print(f"[backup] exists, kept: {BACKUP}")
    for va, orig, patch, note in EDITS:
        off = _fileoff(pe, va)
        blob[off:off+len(patch)] = patch
    try:
        with open(TARGET, "wb") as f:
            f.write(blob)
    except PermissionError:
        sys.exit("! PermissionError — HSEPack.dpl is locked. Close AoW.exe / "
                 "AoWCompat.exe / AoWDevEd.exe and retry.")
    print("[applied] map-cursor small-map fix written.")
    print("Revert: python build_mapcursor_fix.py --revert")

if __name__ == "__main__":
    main()
