#!/usr/bin/env python3
r"""Readable save-game timestamps: an ISO date in the Load/Save dialog's Date column.

THE BUG (vanilla, and LIVE on this machine)
-------------------------------------------
The Date column (`DateLB`, `TFileDlgWindow+0xE8`) is filled in one loop: for each save found by
`FindFirst`, `FileDateToDateTime(SearchRec.Time)` is stashed (call at `0x0041F716`) and each entry
is later rendered by `SysUtils.DateTimeToStr` -- a single call site at `0x0041F89E`, through thunk
`0x00401434`, IAT slot `0x0045D404`.

`DateTimeToStr` builds `ShortDateFormat + ' ' + LongTimeFormat`, both taken from the Windows
locale. In 1999 that gave `7/31/98 6:46:09 PM` (~18 chars). Modern short-date defaults use a
four-digit year, so on this machine (en-AU, `d/MM/yyyy` + `h:mm:ss tt`) it renders

    29/08/2026 8:27:32 AM        <- 21 characters, measured 2026-08-28

which overruns the 130px `DateLB` in font Age8 (digit advance 5px) and shows a garbled tail. The
':' glyph is 1px wide and reads as a space, so the overflow looks like stray numbers rather than a
clipped date.

THE FIX
-------
Call `SysUtils.DateTimeToString(var Result; const Format; DateTime)` with an explicit,
locale-independent format instead. Its convention is `DateTimeToStr`'s (EAX = ^Result, TDateTime
pushed, callee-cleaned) **plus EDX = Format**, so the existing call site needs only an EDX load in
front of it.

    yyyy-mm-dd hh:nn:ss   ->  "2026-08-29 08:27:32"

19 chars but ~88px in Age8 (2px colons), comfortably inside 130px, and it sorts as it reads in
every locale. (Delphi `nn` = minutes; `hh` without an am/pm marker is 24-hour.)

Four edits, all verified against the live files 2026-08-28:

  1. A hint/name entry `\0\0 "SysUtils.DateTimeToString@73F58862" \0` -- vcl30.dpl exports that
     symbol (checked against its export table, 5751 names).
  2. IAT slot `0x0045D404` repointed from name-RVA `0x0005F88E` (DateTimeToStr) to ours.
     ⚠ Safe because **Borland links with OriginalFirstThunk = 0** -- every VCL30 import descriptor
     in this exe has it -- so the IAT *is* the ILT and the loader reads this slot as a hint/name
     RVA, then overwrites it with the resolved address. And `0x0045D404` has **exactly one
     reference in the whole file** (the thunk), so nothing else changes meaning.
  3. A 10-byte stub: `mov edx, <format literal>` / `jmp 0x00401434`.
  4. The call at `0x0041F89E` retargeted from the thunk to the stub.

The format literal is a proper Delphi AnsiString -- `refcount = -1`, `length = 19`, chars, NUL --
because `DateTimeToString` reads the length from `[ptr-4]`. Refcount -1 marks it a constant, so
Delphi never tries to free or realloc it.

⚠ WHY NOT THE CODE/DATA TAIL. Inioch's original puts the stub at `0x00459FEC` and the name entry in
the DATA tail. Both sit **past their section's VirtualSize** (CODE vsz ends exactly at `0x459FEC`;
DATA vsz ends at `0x0045A634` with the slack beyond it). That works in practice because Windows
maps SizeOfRawData, but it is a needless bet. Everything here goes in `.hcol` instead, where
`vsz == rawsz == 0x1C000`, the section is RWX, and the range is verified zero.

⚠ Absolute addresses are used deliberately (`mov edx, imm32`). `AoWz.exe` is fixed-base `0x400000`
and `DllCharacteristics = 0x0000`, i.e. **ASLR is off**, so per CLAUDE.md exe caves may use them.
Do not copy this into an AoWEPACK cave, which must stay position-independent.

Usage:
  python build_scripts/build_savedate_format.py           dry run + report state
  python build_scripts/build_savedate_format.py --apply   patch Ziggurat\AoWz.exe + AoWzCompat.exe
                                                          ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)
  python build_scripts/build_savedate_format.py --undo    surgical revert (restore, zero the cave)
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)
EXES = zigexe.EXES
SUFFIX = ".pre-savedate"
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03
BASE = 0x00400000

CALL_SITE = 0x0041F89E                 # the only DateTimeToStr caller
THUNK = 0x00401434                     # jmp [0x45D404]
IAT_SLOT = 0x0045D404
OLD_NAME_RVA = 0x0005F88E              # -> "SysUtils.DateTimeToStr@0B3E54BB"
IMPORT_NAME = b"SysUtils.DateTimeToString@73F58862"
FORMAT = b"yyyy-mm-dd hh:nn:ss"

CAVE = 0x0062D020                      # .hcol, after build_unitwin_ability.py's cave (ends 0x62D01B)
CAVE_MAX = 0x80
NAME_VA = CAVE                         # hint/name entry
LIT_VA = CAVE + 0x30                   # Delphi string header
STR_VA = LIT_VA + 8                    # the pointer DateTimeToString receives
STUB_VA = CAVE + 0x50


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        name = bytes(d[s:s + 8]).rstrip(b"\0").decode("latin1")
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        chars = struct.unpack_from("<I", d, s + 36)[0]
        yield name, rva, vsz, ro, rsz, chars


def va2off(d, va):
    rva = va - BASE
    for name, srva, vsz, ro, rsz, _c in sections(d):
        if srva <= rva < srva + max(vsz, rsz):
            off = ro + (rva - srva)
            assert off < ro + rsz, "%08X past %s's raw data" % (va, name)
            return off
    raise AssertionError("VA %08X in no section" % va)


def build_blob():
    """-> the whole cave image, so one compare covers name + literal + stub."""
    b = bytearray(CAVE_MAX)
    ent = b"\x00\x00" + IMPORT_NAME + b"\x00"          # hint(0) + name + NUL
    b[0:len(ent)] = ent
    lit = struct.pack("<ii", -1, len(FORMAT)) + FORMAT + b"\x00"
    o = LIT_VA - CAVE
    b[o:o + len(lit)] = lit
    stub = (b"\xBA" + struct.pack("<I", STR_VA) +                       # mov edx, format
            b"\xE9" + struct.pack("<i", THUNK - (STUB_VA + 5 + 5)))     # jmp thunk
    o = STUB_VA - CAVE
    b[o:o + len(stub)] = stub
    return bytes(b)


def call_bytes(target):
    return b"\xE8" + struct.pack("<i", target - (CALL_SITE + 5))


def main(argv):
    apply_, undo = "--apply" in argv, "--undo" in argv
    blob = build_blob()
    assert len(IMPORT_NAME) + 3 <= 0x30, "name entry overruns the literal"
    assert 8 + len(FORMAT) + 1 <= STUB_VA - LIT_VA, "literal overruns the stub"

    if "--dis" in argv:
        print("cave %08X (%d B): name @%08X, literal @%08X (string ptr %08X), stub @%08X"
              % (CAVE, CAVE_MAX, NAME_VA, LIT_VA, STR_VA, STUB_VA))
        print("  name    %s" % blob[:len(IMPORT_NAME) + 3].hex(" "))
        print("  literal %s" % blob[LIT_VA - CAVE:LIT_VA - CAVE + 8 + len(FORMAT) + 1].hex(" "))
        print("  stub    %s   ; mov edx,%08X / jmp %08X"
              % (blob[STUB_VA - CAVE:STUB_VA - CAVE + 10].hex(" "), STR_VA, THUNK))
        print("  IAT     %08X: %08X -> %08X" % (IAT_SLOT, OLD_NAME_RVA, NAME_VA - BASE))
        print("  call    %08X: %s -> %s"
              % (CALL_SITE, call_bytes(THUNK).hex(), call_bytes(STUB_VA).hex()))
        return 0

    blobs, states = {}, []
    for fn in EXES:
        p = os.path.join(GAME, fn)
        if not os.path.exists(p):
            print("MISSING: %s" % p)
            return 1
        d = bytearray(open(p, "rb").read())
        blobs[fn] = d
        iat = struct.unpack_from("<I", d, va2off(d, IAT_SLOT))[0]
        call = bytes(d[va2off(d, CALL_SITE):va2off(d, CALL_SITE) + 5])
        cave = bytes(d[va2off(d, CAVE):va2off(d, CAVE) + CAVE_MAX])
        if iat == OLD_NAME_RVA and call == call_bytes(THUNK):
            st = "vanilla"
        elif iat == NAME_VA - BASE and call == call_bytes(STUB_VA) and cave == blob:
            st = "applied"
        else:
            st = "foreign"
        states.append(st)
        print("%-14s %-8s IAT=%08X  call=%s" % (fn, st, iat, call.hex()))

    if "foreign" in states:
        print("\nABORT: unrecognised state -- neither vanilla nor ours. Someone else owns the\n"
              "IAT slot, the call site or the cave. Resolve that before patching.")
        return 2
    if len(set(states)) != 1:
        print("\nABORT: the two exes disagree (%s); they must stay in lockstep." % states)
        return 2
    state = states[0]

    if undo:
        if state == "vanilla":
            print("\nalready vanilla -- nothing to undo")
            return 0
        for fn, d in blobs.items():
            struct.pack_into("<I", d, va2off(d, IAT_SLOT), OLD_NAME_RVA)
            o = va2off(d, CALL_SITE)
            d[o:o + 5] = call_bytes(THUNK)
            o = va2off(d, CAVE)
            d[o:o + CAVE_MAX] = b"\x00" * CAVE_MAX
            open(os.path.join(GAME, fn), "wb").write(bytes(d))
            print("reverted %s (IAT, call site, cave zeroed -- no backup touched)" % fn)
        return 0

    if state == "applied":
        print("\nalready applied -- IAT, call site and cave all verified")
        return 0

    print("\nformat %r -> e.g. \"2026-08-29 08:27:32\" (%d chars)" % (FORMAT.decode(), len(FORMAT)))
    print("cave %08X: name @%08X, literal @%08X (ptr %08X), stub @%08X"
          % (CAVE, NAME_VA, LIT_VA, STR_VA, STUB_VA))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write")
        return 0

    for fn, d in blobs.items():
        o = va2off(d, CAVE)
        assert bytes(d[o:o + CAVE_MAX]) == b"\x00" * CAVE_MAX, "%s: cave is not zero" % fn
        # Snapshot only from a file PROVED unpatched: control only reaches here with
        # state == "vanilla" (IAT still points at DateTimeToStr, the call site still hits the
        # thunk), asserted again by the zero-cave check above. "No backup file exists yet" is not
        # that proof -- after the 2026-09-09 rename no AoWz.exe.pre-savedate can exist, so a
        # gate on the file's absence alone would happily snapshot a patched exe.
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bak = os.path.join(BACKUP_DIR, fn + SUFFIX)
        if not os.path.exists(bak):
            shutil.copy2(os.path.join(GAME, fn), bak)
            print("backup written: %s" % bak)
        d[o:o + CAVE_MAX] = blob
        struct.pack_into("<I", d, va2off(d, IAT_SLOT), NAME_VA - BASE)
        o = va2off(d, CALL_SITE)
        d[o:o + 5] = call_bytes(STUB_VA)
        open(os.path.join(GAME, fn), "wb").write(bytes(d))
        print("patched %s" % fn)

    for fn in EXES:
        d = bytearray(open(os.path.join(GAME, fn), "rb").read())
        assert struct.unpack_from("<I", d, va2off(d, IAT_SLOT))[0] == NAME_VA - BASE
        assert bytes(d[va2off(d, CALL_SITE):va2off(d, CALL_SITE) + 5]) == call_bytes(STUB_VA)
    print("read-back verified in both exes.")
    print("\nIN-GAME TEST NEEDED -- this script cannot confirm anything:")
    print("  1. open Load Game: the Date column must read like 2026-08-29 08:27:32,")
    print("     fully inside the column, no garbled tail.")
    print("  2. sort by Date if the dialog allows it -- ISO sorts as it reads.")
    print("  3. ! the IAT repoint means the game now imports DateTimeToString instead of")
    print("     DateTimeToStr. If the exe fails to START, that is the import -- --undo at once.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
