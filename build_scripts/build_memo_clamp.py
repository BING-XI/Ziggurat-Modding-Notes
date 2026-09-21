#!/usr/bin/env python3
r"""Stop a TAOWMemo storing a NEGATIVE first-line index -- the "Exception during Draw" bug.

THE BUG (vanilla, latent in two shipped Ziggurat features)
----------------------------------------------------------
`AoWMemo.TAOWMemo.SetListOff @0x59819298` (aowInt.dpl) is the setter for the memo's first visible
line, `[self+0x128]`. It clamps the UPPER bound only:

    59819298  push ebx / push esi
    5981929A  mov  esi, edx              ; the requested first-line index
    5981929C  mov  ebx, eax              ; Self
    5981929E  mov  eax,[ebx+0x188]       ; the wrapped-lines list
    598192A4  mov  edx,[eax] / call [edx+0x14]      ; -> Count
    598192A9  cmp  esi, eax
    598192AB  jl   0x598192BB            ; requested < Count -> STORE IT AS-IS   <-- no lower clamp
    598192AD  mov  eax,[ebx+0x188]       ; (recomputes Count -- redundant, see below)
    598192A4  mov  edx,[eax] / call [edx+0x14]
    598192B8  mov  esi, eax
    598192BA  dec  esi                   ; Count-1  -- and if Count == 0 that is -1
    598192BB  cmp  esi,[ebx+0x128] / store + invalidate layout

So there are two ways to store a negative:

  1. **Scroll up past the top.** Any negative request is `< Count`, takes the `jl`, and is stored
     verbatim. Inioch hit this by wheel-scrolling a city text box: it stored -3.
  2. **An EMPTY memo.** `Count == 0` takes the other arm and stores `Count-1` = **-1**.

`AoWMemo.TAOWMemo.Draw @0x598198AE` then does `mov eax,[eax+0x128] / add eax,ebx` per visible row,
i.e. it indexes `Lines[FirstLine + i]`. A negative FirstLine indexes before the start of the list
-> `EListError` -> the widget stops painting and you get an "Exception during Draw" dialog naming
the memo. ⚠ And per the `aow1-blt-error-wall-4c-alias` memory, AoW's nested catch-alls destroy the
real exception, so that dialog's text tells you nothing.

WHY THIS MATTERS TO US even though we have no mouse-wheel patch
---------------------------------------------------------------
The wheel merely *exposed* it. We drive `TAOWMemo` programmatically in two shipped features:

  * `build_shipyard_income_display.py` appends a sixth row to a five-line page, and its own notes
    (lines 90-91) record that the scrollbar "does become live at 6 items vs a page of 5".
  * the combat log (`Zig notes/Combat_Log_Implementation_Design.md`) -- `+0x118` FStrings,
    `+0x120` linked scrollbar, `+0x188` wrapped list, `+0x2E` layout-valid flag.

A combat-log memo cleared to empty is exactly case 2. Neither feature knows the setter is
one-sided.

THE FIX -- in place, no cave, length-neutral
--------------------------------------------
The function calls the list's `Count` **twice**, and the second call is redundant: on the
fall-through path `EAX` still holds the Count returned by the first call, and only a `cmp` has run
since. That gives 11 free bytes to spend on the missing clamp without needing a cave.

    OLD  7c 0e | 8b 83 88 01 00 00  8b 10  ff 52 14 | 8b f0 | 4e
         jl +14  <recompute Count -- redundant>       mov esi,eax  dec esi

    NEW  7c 03 | 89 c6 | 4e | 85 f6 | 79 02 | 31 f6 | 90 90 90 90 90
         jl +3   mov esi,eax  dec esi  test esi,esi  jns +2  xor esi,esi   <pad>

Both arms now converge on `0x598192B0` and pass through the lower clamp:

  * requested < Count  -> `jl` jumps to the clamp; a negative becomes 0.
  * requested >= Count -> falls through to `mov esi,eax / dec esi` (Count-1, using the Count
    already in EAX), then the clamp turns the empty-list -1 into 0.

⭐ **Clamping to 0 is provably safe for an empty memo**, and not by argument: `[self+0x128]` is 0
in a freshly constructed memo (Delphi zero-initialises), and Count is 0 before any text is added,
so "FirstLine 0, Count 0" is the state every memo in the game starts in and draws in every day.
The bug is only ever the negative.

The 16-byte run is length-neutral, so nothing moves. Verified: **no `.reloc` entry covers
`0x598192AB..0x598192BB`**, and no other build script in this tree touches `SetListOff` (ten
scripts patch `aowInt.dpl`, none of them this function).

⚠ Behaviour change worth stating: scrolling up from the top now pins at line 0 instead of storing
a negative. That is the only user-visible difference, and it is the intended one.

Usage:
  python build_scripts/build_memo_clamp.py           dry run + report state
  python build_scripts/build_memo_clamp.py --apply   patch aowInt.dpl
  python build_scripts/build_memo_clamp.py --undo    restore the vanilla bytes
  python build_scripts/build_memo_clamp.py --dis     disassemble old vs new
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "aowInt.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-memoclamp")
IMAGE_BASE = 0x59800000

FUNC = 0x59819298                       # AoWMemo.TAOWMemo.SetListOff
SITE = 0x598192AB                       # the jl, i.e. FUNC + 0x13
OLD = bytes.fromhex("7c0e" "8b83 88010000" "8b10" "ff5214" "8bf0" "4e".replace(" ", ""))
NEW = bytes.fromhex("7c03" "89c6" "4e" "85f6" "7902" "31f6" "9090909090".replace(" ", ""))

# A signature for the rest of the function, so we know we are in the right place and that the
# store/invalidate tail is untouched.
TAIL = 0x598192BB
TAIL_EXPECT = bytes.fromhex("3bb328010000" "740d" "89b328010000" "c683a400000000")


def va2off(d, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        if IMAGE_BASE + rva <= va < IMAGE_BASE + rva + max(vsz, rsz):
            off = ro + (va - IMAGE_BASE - rva)
            assert off < ro + rsz, "%08X past raw data" % va
            return off
    raise AssertionError("VA %08X in no section" % va)


def disassemble(blob, va, title):
    try:
        import capstone
    except ImportError:
        return ["  %s: %s" % (title, blob.hex(" "))]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    out = ["  --- %s ---" % title]
    out += ["    %08X  %-20s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str)
            for i in md.disasm(blob, va)]
    return out


def main(argv):
    assert len(OLD) == len(NEW) == 16, "the run must stay 16 bytes"

    if "--dis" in argv:
        print("\n".join(disassemble(OLD, SITE, "vanilla")))
        print("\n".join(disassemble(NEW, SITE, "patched")))
        return 0

    apply_, undo = "--apply" in argv, "--undo" in argv
    d = bytearray(open(DLL, "rb").read())
    off = va2off(d, SITE)
    cur = bytes(d[off:off + len(OLD)])

    tail = bytes(d[va2off(d, TAIL):va2off(d, TAIL) + len(TAIL_EXPECT)])
    assert tail == TAIL_EXPECT, ("the tail of SetListOff is not what this script expects "
                                 "(%s) -- aborting" % tail.hex())

    state = "vanilla" if cur == OLD else ("applied" if cur == NEW else "foreign")
    print("aowInt.dpl  %08X  %-8s  %s" % (SITE, state, cur.hex(" ")))
    if state == "foreign":
        print("\nABORT: neither vanilla nor ours -- someone else owns this run.")
        return 2

    if undo:
        if state == "vanilla":
            print("\nalready vanilla -- nothing to undo")
            return 0
        d[off:off + len(OLD)] = OLD
        open(DLL, "wb").write(bytes(d))
        print("reverted (16 bytes restored, no backup touched)")
        return 0

    if state == "applied":
        print("\nalready applied")
        return 0

    print()
    print("\n".join(disassemble(OLD, SITE, "vanilla")))
    print("\n".join(disassemble(NEW, SITE, "patched")))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write")
        return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup written: %s" % os.path.basename(BACKUP))
    before = len(d)
    d[off:off + len(NEW)] = NEW
    assert len(d) == before, "length changed -- must never happen"
    open(DLL, "wb").write(bytes(d))
    d2 = bytearray(open(DLL, "rb").read())
    assert bytes(d2[va2off(d2, SITE):va2off(d2, SITE) + len(NEW)]) == NEW, "read-back failed"
    print("patched aowInt.dpl; read-back verified.")
    print("\nIN-GAME TEST NEEDED -- this script cannot confirm anything:")
    print("  1. Open a city view with a text box and scroll it UP past the top repeatedly.")
    print("     Before: 'Exception during Draw' and the box stops painting. After: pins at line 0.")
    print("  2. The combat log: let it fill, scroll to the top, keep scrolling up.")
    print("  3. An EMPTY combat log (new battle, nothing logged yet) must render blank, not throw.")
    print("  4. The shipyard income panel at 6+ rows -- scroll it to the top and past.")
    print("  5. Normal scrolling down and back must be unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
